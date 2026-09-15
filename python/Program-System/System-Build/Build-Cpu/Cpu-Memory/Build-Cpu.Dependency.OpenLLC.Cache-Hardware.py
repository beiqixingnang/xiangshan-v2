"""OpenLLC cache family aggregate for the Kunminghu V2 closure.
昆明湖 V2 Kunminghu OpenLLC 缓存 family 聚合实现。

The aggregate keeps the cache-bearing OpenLLC children in one parameterised
module.  It models the address decomposition, directory metadata, data-store
write forwarding, request buffering/arbitration, refill bookkeeping and the
slice-level miss indication used by ``OpenLLC.scala``.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence, cast

from amaranth import Array, ClockDomain, Const, Elaboratable, Memory, Module, Mux, Signal
from amaranth.back import verilog
from amaranth.hdl.ast import Value


# =============================================================================
# Module Contract
# =============================================================================
# The public contract covers Common.scala, LLCParam.scala, DataStorage.scala,
# Directory.scala and the request/response pipeline children.
# 公共契约覆盖 Common.scala、LLCParam.scala、DataStorage.scala、Directory.scala
# 以及请求/响应流水线子模块。
__all__ = [
    "OpenLLCResourceConfig", "OpenLLCConfig", "OpenLLCTask", "OpenLLCTaskWithData",
    "OpenLLCResponse", "OpenLLCMetaEntry", "OpenLLCBlockInfo", "parse_address",
    "compose_address", "select_replacement_way", "beat_data_id", "OpenLLCDataStorage",
    "OpenLLCDirectory", "OpenLLCRequestBuffer", "OpenLLCRequestArbiter",
    "OpenLLCPipeline", "OpenLLCSlice", "OpenLLCCache", "LLCParam", "Common",
    "DataStorage", "Directory", "RequestBuffer", "RequestArb", "MainPipe",
    "MemUnit", "RefillUnit", "ResponseUnit", "SnoopUnit", "OpenLLC", "Slice",
    "build_verilog", "main",
]


# Narrow dynamic Amaranth contexts to the static protocol used by Pyright. /
# 将动态 Amaranth 上下文窄化为 Pyright 可检查的静态协议。
def amaranth_if(module: Module, condition: Any) -> AbstractContextManager[None]:
    """Return a typed Amaranth conditional context. / 返回带类型的 Amaranth 条件上下文。"""

    return cast(AbstractContextManager[None], module.If(condition))


# Narrow an expression at the Amaranth DSL boundary. / 在 Amaranth DSL 边界窄化表达式类型。
def amaranth_value(expression: Any) -> Value:
    """Treat a runtime Amaranth expression as a hardware value. / 将运行时 Amaranth 表达式视为硬件值。"""

    return cast(Value, expression)


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class OpenLLCResourceConfig:
    """Per-resource MSHR capacities from OpenLLCParam.scala. / OpenLLCParam.scala 的资源容量。"""

    refill: int = 16
    response: int = 16
    snoop: int = 16
    memory: int = 16

    # Validate resource capacities. / 校验资源容量。
    def __post_init__(self) -> None:
        if min(self.refill, self.response, self.snoop, self.memory) < 1:
            raise ValueError("OpenLLC resource capacities must be positive")


@dataclass(frozen=True)
class OpenLLCConfig:
    """Synthesizable OpenLLC geometry and protocol widths. / 可综合 OpenLLC 几何及协议位宽。"""

    name: str = "LLC"
    ways: int = 4
    sets: int = 128
    block_bytes: int = 64
    beat_bytes: int = 32
    full_address_bits: int = 16
    replacement: str = "plru"
    banks: int = 4
    resources: OpenLLCResourceConfig = field(default_factory=OpenLLCResourceConfig)
    clients: int = 1
    client_sets: int = 128
    client_ways: int = 4
    enable_perf: bool = True
    enable_chi_log: bool = True

    # Validate V2 parameter ranges and byte geometry. / 校验 V2 参数范围及字节几何。
    def __post_init__(self) -> None:
        integer_values = (self.ways, self.sets, self.block_bytes, self.beat_bytes,
                          self.full_address_bits, self.banks, self.clients,
                          self.client_sets, self.client_ways)
        if min(integer_values) < 1:
            raise ValueError("OpenLLC geometry values must be positive")
        if self.block_bytes % self.beat_bytes or self.block_bytes < self.beat_bytes:
            raise ValueError("block_bytes must be an integral number of beats")
        if self.sets & (self.sets - 1) or self.banks & (self.banks - 1):
            raise ValueError("sets and banks must be powers of two")
        if self.ways > 32 or self.replacement not in {"plru", "random", "rr"}:
            raise ValueError("unsupported OpenLLC replacement geometry")
        if self.full_address_bits < 12:
            raise ValueError("full_address_bits is too small")

    # Number of beats in a block. / 返回一个 cache block 的 beat 数。
    @property
    def beat_count(self) -> int:
        return self.block_bytes // self.beat_bytes

    # Return the set-index width. / 返回组索引位宽。
    @property
    def set_bits(self) -> int:
        return max(1, (self.sets - 1).bit_length())

    # Return the bank-index width. / 返回 bank 索引位宽。
    @property
    def bank_bits(self) -> int:
        return max(0, (self.banks - 1).bit_length())

    # Return the byte-offset width. / 返回字节偏移位宽。
    @property
    def offset_bits(self) -> int:
        return max(1, (self.block_bytes - 1).bit_length())

    # Return the tag width after address decomposition. / 返回地址分解后的标签位宽。
    @property
    def tag_bits(self) -> int:
        return max(1, self.full_address_bits - self.set_bits - self.bank_bits - self.offset_bits)

    # Return the block data width. / 返回 block 数据位宽。
    @property
    def data_bits(self) -> int:
        return self.block_bytes * 8

    # Return the beat data width. / 返回 beat 数据位宽。
    @property
    def beat_data_bits(self) -> int:
        return self.beat_bytes * 8


@dataclass(frozen=True)
class OpenLLCTask:
    """Transaction metadata represented by Common.scala Task. / Common.scala Task 事务元数据。"""

    address: int = 0
    size: int = 0
    opcode: int = 0
    txn_id: int = 0
    source_id: int = 0
    refill: bool = False
    snoop: bool = False


@dataclass(frozen=True)
class OpenLLCTaskWithData:
    """Task plus a full cache block. / 带完整 cache block 数据的事务。"""

    task: OpenLLCTask = field(default_factory=OpenLLCTask)
    data: tuple[int, ...] = ()


@dataclass(frozen=True)
class OpenLLCResponse:
    """Response bookkeeping from ResponseUnit.scala. / ResponseUnit.scala 的响应记录。"""

    txn_id: int = 0
    opcode: int = 0
    response: int = 0
    source_id: int = 0
    data_valid: bool = False
    miss: bool = False


@dataclass(frozen=True)
class OpenLLCMetaEntry:
    """Directory metadata for one way. / 单一路的目录元数据。"""

    tag: int = 0
    valid: bool = False
    dirty: bool = False
    clients: int = 0
    prefetch: bool = False
    accessed: bool = False
    error: bool = False


@dataclass(frozen=True)
class OpenLLCBlockInfo:
    """Refill/replacement descriptor from Common.scala. / Common.scala 的回填/替换描述符。"""

    tag: int = 0
    set_index: int = 0
    opcode: int = 0
    request_id: int = 0


# Decompose an address as OpenLLC.HasOpenLLCParameters.parseAddress does. /
# 按 OpenLLC.HasOpenLLCParameters.parseAddress 分解地址。
def parse_address(address: int, configuration: OpenLLCConfig | None = None) -> tuple[int, int, int, int]:
    """Return ``(tag, set, bank, offset)`` from a byte address. / 从字节地址返回 ``(tag, set, bank, offset)``。"""

    cfg = configuration or OpenLLCConfig()
    value = int(address) & ((1 << cfg.full_address_bits) - 1)
    offset_mask = (1 << cfg.offset_bits) - 1
    bank_mask = (1 << cfg.bank_bits) - 1 if cfg.bank_bits else 0
    set_mask = (1 << cfg.set_bits) - 1
    offset = value & offset_mask
    bank = (value >> cfg.offset_bits) & bank_mask if cfg.bank_bits else 0
    set_index = (value >> (cfg.offset_bits + cfg.bank_bits)) & set_mask
    tag = value >> (cfg.offset_bits + cfg.bank_bits + cfg.set_bits)
    return tag, set_index, bank, offset


# Compose a byte address from cache fields. / 从 cache 字段组合字节地址。
def compose_address(tag: int, set_index: int, bank: int, offset: int,
                    configuration: OpenLLCConfig | None = None) -> int:
    """Pack cache address fields with range checks. / 带范围检查地打包 cache 地址字段。"""

    cfg = configuration or OpenLLCConfig()
    if tag < 0 or set_index < 0 or bank < 0 or offset < 0:
        raise ValueError("address fields must be non-negative")
    if set_index >= cfg.sets or bank >= cfg.banks or offset >= cfg.block_bytes:
        raise ValueError("address field exceeds configured geometry")
    return ((int(tag) << (cfg.set_bits + cfg.bank_bits + cfg.offset_bits))
            | (int(set_index) << (cfg.bank_bits + cfg.offset_bits))
            | (int(bank) << cfg.offset_bits) | int(offset))


# Pick the first invalid way, then the replacement way. / 优先选择首个无效路，否则选择替换路。
def select_replacement_way(valid_mask: int, replacement_way: int, ways: int) -> int:
    """Implement the deterministic invalid/PLRU selection rule. / 实现确定性的无效路/PLRU 选择规则。"""

    if ways < 1:
        raise ValueError("ways must be positive")
    for way in range(ways):
        if not (int(valid_mask) >> way) & 1:
            return way
    return int(replacement_way) % ways


# Return the CHI dataID for one beat. / 返回一个 beat 对应的 CHI dataID。
def beat_data_id(beat: int, configuration: OpenLLCConfig | None = None) -> int:
    """Encode the block beat index in bytes. / 以字节单位编码 block beat 索引。"""

    cfg = configuration or OpenLLCConfig()
    if beat < 0 or beat >= cfg.beat_count:
        raise ValueError("beat index out of range")
    return int(beat) * cfg.beat_bytes


# =============================================================================
# Implementation
# =============================================================================
class OpenLLCDataStorage(Elaboratable):
    """Two-port block store with one-cycle read response and write forwarding.
    带单周期读响应及写转发的双端口 block 存储。
    """

    # Construct explicit storage ports. / 构造显式存储端口。
    def __init__(self, configuration: OpenLLCConfig | None = None) -> None:
        self.configuration = configuration or OpenLLCConfig()
        c = self.configuration
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.read_valid = Signal(name="io_read_valid")
        self.read_ready = Signal(name="io_read_ready")
        self.read_index = Signal(max(1, (c.sets * c.ways - 1).bit_length()), name="io_read_bits_index")
        self.read_data = Signal(c.data_bits, name="io_rdata")
        self.write_valid = Signal(name="io_write_valid")
        self.write_index = Signal(len(self.read_index), name="io_write_bits_index")
        self.write_data = Signal(c.data_bits, name="io_wdata")

    # Elaborate block memory and bypass path. / 展开 block 存储器及旁路路径。
    def elaborate(self, platform: Any) -> Module:
        """Build synchronous storage logic. / 构造同步存储逻辑。"""

        del platform
        c = self.configuration
        m = Module()
        domain = ClockDomain("openllc_data", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.openllc_data = domain
        depth = c.sets * c.ways
        memory = Memory(width=c.data_bits, depth=depth, init=[0] * depth, name="openllc_data_array")
        read_port = memory.read_port(domain="openllc_data")
        write_port = memory.write_port(domain="openllc_data")
        m.submodules.read_port = read_port
        m.submodules.write_port = write_port
        same_write = self.write_valid & (self.write_index == self.read_index)
        m.d.comb += [
            self.read_ready.eq(~self.reset),
            read_port.addr.eq(self.read_index),
            write_port.addr.eq(self.write_index),
            write_port.data.eq(self.write_data),
            write_port.en.eq(self.write_valid),
            self.read_data.eq(Mux(same_write, self.write_data, read_port.data)),
        ]
        return m


class OpenLLCDirectory(Elaboratable):
    """Tag/meta directory with pipelined lookup and invalid-way selection.
    带流水查找及无效路选择的标签/元数据目录。
    """

    # Construct directory lookup and update ports. / 构造目录查找和更新端口。
    def __init__(self, configuration: OpenLLCConfig | None = None) -> None:
        self.configuration = configuration or OpenLLCConfig()
        c = self.configuration
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.read_valid = Signal(name="io_read_valid")
        self.read_ready = Signal(name="io_read_ready")
        self.read_tag = Signal(c.tag_bits, name="io_read_bits_tag")
        self.read_set = Signal(c.set_bits, name="io_read_bits_set")
        self.resp_valid = Signal(name="io_resp_valid")
        self.resp_hit = Signal(name="io_resp_bits_hit")
        self.resp_way = Signal(max(1, (c.ways - 1).bit_length()), name="io_resp_bits_way")
        self.resp_tag = Signal(c.tag_bits, name="io_resp_bits_tag")
        self.resp_dirty = Signal(name="io_resp_bits_dirty")
        self.write_valid = Signal(name="io_write_valid")
        self.write_set = Signal(c.set_bits, name="io_write_bits_set")
        self.write_way = Signal(len(self.resp_way), name="io_write_bits_way")
        self.write_tag = Signal(c.tag_bits, name="io_write_bits_tag")
        self.write_dirty = Signal(name="io_write_bits_dirty")
        self.write_clients = Signal(max(1, c.clients), name="io_write_bits_clients")

    # Elaborate tag, valid, dirty, and replacement memories. / 展开标签、有效、脏位及替换存储器。
    def elaborate(self, platform: Any) -> Module:
        """Build the two-stage directory lookup. / 构造两级目录查找。"""

        del platform
        c = self.configuration
        m = Module()
        domain = ClockDomain("openllc_directory", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.openllc_directory = domain
        depth = c.sets * c.ways
        tag_mem = Memory(width=c.tag_bits, depth=depth, init=[0] * depth, name="openllc_tag_array")
        valid_mem = Memory(width=1, depth=depth, init=[0] * depth, name="openllc_valid_array")
        dirty_mem = Memory(width=1, depth=depth, init=[0] * depth, name="openllc_dirty_array")
        repl_mem = Memory(width=max(1, (c.ways - 1).bit_length()), depth=c.sets,
                          init=[0] * c.sets, name="openllc_replacement_array")
        tag_read = [tag_mem.read_port(domain="openllc_directory") for _ in range(c.ways)]
        valid_read = [valid_mem.read_port(domain="openllc_directory") for _ in range(c.ways)]
        dirty_read = [dirty_mem.read_port(domain="openllc_directory") for _ in range(c.ways)]
        for way, port in enumerate(tag_read):
            m.submodules[f"tag_read_{way}"] = port
        for way, port in enumerate(valid_read):
            m.submodules[f"valid_read_{way}"] = port
        for way, port in enumerate(dirty_read):
            m.submodules[f"dirty_read_{way}"] = port
        tag_write = tag_mem.write_port(domain="openllc_directory")
        valid_write = valid_mem.write_port(domain="openllc_directory")
        dirty_write = dirty_mem.write_port(domain="openllc_directory")
        repl_read = repl_mem.read_port(domain="openllc_directory")
        repl_write = repl_mem.write_port(domain="openllc_directory")
        m.submodules += [tag_write, valid_write, dirty_write, repl_read, repl_write]
        read_index = self.read_set * c.ways
        write_index = self.write_set * c.ways + self.write_way
        m.d.comb += [
            self.read_ready.eq(~self.reset & ~self.write_valid),
            repl_read.addr.eq(self.read_set),
            repl_write.addr.eq(self.write_set),
            repl_write.data.eq(self.write_way),
            repl_write.en.eq(self.write_valid),
            tag_write.addr.eq(write_index), tag_write.data.eq(self.write_tag), tag_write.en.eq(self.write_valid),
            valid_write.addr.eq(write_index), valid_write.data.eq(1), valid_write.en.eq(self.write_valid),
            dirty_write.addr.eq(write_index), dirty_write.data.eq(self.write_dirty), dirty_write.en.eq(self.write_valid),
        ]
        tag_values: list[Value] = []
        hit_values: list[Value] = []
        dirty_values: list[Value] = []
        valid_values: list[Value] = []
        for way in range(c.ways):
            # Each way occupies a contiguous row in the flattened SRAM. /
            # 每一路在展平 SRAM 中占据连续行。
            way_index = read_index + way
            m.d.comb += [tag_read[way].addr.eq(way_index), valid_read[way].addr.eq(way_index),
                         dirty_read[way].addr.eq(way_index)]
            tag_values.append(amaranth_value(tag_read[way].data))
            valid_values.append(amaranth_value(valid_read[way].data))
            dirty_values.append(amaranth_value(dirty_read[way].data))
            hit_values.append(amaranth_value(valid_read[way].data) & (amaranth_value(tag_read[way].data) == self.read_tag))
        hit_any: Value = Const(0)
        hit_way: Value = Const(0, len(self.resp_way))
        valid_mask: Value = Const(0, c.ways)
        dirty_selected: Value = Const(0)
        tag_selected: Value = Const(0, c.tag_bits)
        for way in range(c.ways):
            hit_any = hit_any | hit_values[way]
            hit_way = Mux(hit_values[way], way, hit_way)
            valid_mask = valid_mask | Mux(valid_values[way], 1 << way, 0)
            dirty_selected = Mux(hit_values[way], dirty_values[way], dirty_selected)
            tag_selected = Mux(hit_values[way], tag_values[way], tag_selected)
        replacement = amaranth_value(repl_read.data)
        selected_way: Value = replacement
        for way in reversed(range(c.ways)):
            selected_way = Mux(~valid_values[way], way, selected_way)
        selected_way = Mux(hit_any, hit_way, selected_way)
        m.d.comb += [
            self.resp_valid.eq(self.read_valid), self.resp_hit.eq(hit_any), self.resp_way.eq(selected_way),
            self.resp_tag.eq(tag_selected), self.resp_dirty.eq(dirty_selected),
        ]
        return m


class OpenLLCRequestBuffer(Elaboratable):
    """Single-entry decoupled request buffer from RequestBuffer.scala.
    RequestBuffer.scala 的单项 decoupled 请求缓冲。
    """

    # Construct request buffer ports. / 构造请求缓冲端口。
    def __init__(self, configuration: OpenLLCConfig | None = None) -> None:
        c = configuration or OpenLLCConfig()
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.in_valid = Signal(name="io_in_valid")
        self.in_ready = Signal(name="io_in_ready")
        self.in_address = Signal(c.full_address_bits, name="io_in_bits_address")
        self.in_opcode = Signal(8, name="io_in_bits_opcode")
        self.out_valid = Signal(name="io_out_valid")
        self.out_ready = Signal(name="io_out_ready")
        self.out_address = Signal(c.full_address_bits, name="io_out_bits_address")
        self.out_opcode = Signal(8, name="io_out_bits_opcode")

    # Elaborate the one-entry queue. / 展开单项队列。
    def elaborate(self, platform: Any) -> Module:
        """Build request buffering and backpressure. / 构造请求缓冲及反压。"""

        del platform
        m = Module()
        domain = ClockDomain("openllc_reqbuf", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.openllc_reqbuf = domain
        full = Signal(name="request_buffer_full")
        address = Signal.like(self.in_address)
        opcode = Signal.like(self.in_opcode)
        fire_in = self.in_valid & self.in_ready
        fire_out = self.out_valid & self.out_ready
        m.d.comb += [self.in_ready.eq(~full | fire_out), self.out_valid.eq(full),
                     self.out_address.eq(address), self.out_opcode.eq(opcode)]
        with amaranth_if(m, self.reset):
            m.d.openllc_reqbuf += full.eq(0)
        with amaranth_if(m, ~self.reset):
            with amaranth_if(m, fire_in):
                m.d.openllc_reqbuf += [full.eq(1), address.eq(self.in_address), opcode.eq(self.in_opcode)]
            with amaranth_if(m, fire_out & ~fire_in):
                m.d.openllc_reqbuf += full.eq(0)
        return m


class OpenLLCRequestArbiter(Elaboratable):
    """Priority arbiter for bus, refill and snoop tasks. / 总线、回填和 snoop 事务优先级仲裁器。"""

    # Construct arbitration ports. / 构造仲裁端口。
    def __init__(self, configuration: OpenLLCConfig | None = None) -> None:
        c = configuration or OpenLLCConfig()
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.bus_valid = Signal(name="io_bus_valid")
        self.bus_ready = Signal(name="io_bus_ready")
        self.bus_address = Signal(c.full_address_bits, name="io_bus_bits_address")
        self.refill_valid = Signal(name="io_refill_valid")
        self.refill_ready = Signal(name="io_refill_ready")
        self.refill_address = Signal(c.full_address_bits, name="io_refill_bits_address")
        self.snoop_valid = Signal(name="io_snoop_valid")
        self.snoop_ready = Signal(name="io_snoop_ready")
        self.snoop_address = Signal(c.full_address_bits, name="io_snoop_bits_address")
        self.out_valid = Signal(name="io_out_valid")
        self.out_ready = Signal(name="io_out_ready")
        self.out_address = Signal(c.full_address_bits, name="io_out_bits_address")
        self.out_source = Signal(2, name="io_out_bits_source")

    # Elaborate deterministic refill-over-snoop-over-bus selection. / 展开确定性的 refill>snoop>bus 选择。
    def elaborate(self, platform: Any) -> Module:
        """Build arbiter ready/valid equations. / 构造仲裁器 ready/valid 方程。"""

        del platform
        m = Module()
        refill_take = self.refill_valid
        snoop_take = ~refill_take & self.snoop_valid
        bus_take = ~refill_take & ~snoop_take & self.bus_valid
        m.d.comb += [
            self.out_valid.eq(refill_take | snoop_take | bus_take),
            self.out_address.eq(Mux(refill_take, self.refill_address, Mux(snoop_take, self.snoop_address, self.bus_address))),
            self.out_source.eq(Mux(refill_take, 1, Mux(snoop_take, 2, 0))),
            self.refill_ready.eq(self.out_ready & refill_take),
            self.snoop_ready.eq(self.out_ready & snoop_take),
            self.bus_ready.eq(self.out_ready & bus_take),
        ]
        return m


class OpenLLCPipeline(Elaboratable):
    """Five-stage request/response bookkeeping boundary from MainPipe.scala.
    对应 MainPipe.scala 的五级请求/响应 bookkeeping 边界。
    """

    # Construct pipeline ports. / 构造流水线端口。
    def __init__(self, configuration: OpenLLCConfig | None = None) -> None:
        c = configuration or OpenLLCConfig()
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.in_valid = Signal(name="io_task_valid")
        self.in_ready = Signal(name="io_task_ready")
        self.in_address = Signal(c.full_address_bits, name="io_task_bits_address")
        self.in_opcode = Signal(8, name="io_task_bits_opcode")
        self.dir_hit = Signal(name="io_dir_hit")
        self.out_valid = Signal(name="io_resp_valid")
        self.out_ready = Signal(name="io_resp_ready")
        self.out_address = Signal(c.full_address_bits, name="io_resp_bits_address")
        self.out_miss = Signal(name="io_resp_bits_miss")

    # Elaborate a one-entry pipeline with miss reporting. / 展开带 miss 报告的单项流水线。
    def elaborate(self, platform: Any) -> Module:
        """Build pipeline state and response handshake. / 构造流水线状态及响应握手。"""

        del platform
        m = Module()
        domain = ClockDomain("openllc_pipe", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.openllc_pipe = domain
        valid = Signal(name="pipe_valid")
        address = Signal.like(self.in_address)
        miss = Signal(name="pipe_miss")
        fire_in = self.in_valid & self.in_ready
        fire_out = self.out_valid & self.out_ready
        m.d.comb += [self.in_ready.eq(~valid | fire_out), self.out_valid.eq(valid),
                     self.out_address.eq(address), self.out_miss.eq(miss)]
        with amaranth_if(m, self.reset):
            m.d.openllc_pipe += valid.eq(0)
        with amaranth_if(m, ~self.reset):
            with amaranth_if(m, fire_in):
                m.d.openllc_pipe += [valid.eq(1), address.eq(self.in_address), miss.eq(~self.dir_hit)]
            with amaranth_if(m, fire_out & ~fire_in):
                m.d.openllc_pipe += valid.eq(0)
        return m


class OpenLLCSlice(Elaboratable):
    """Bank-local slice boundary combining directory, data and pipeline.
    组合目录、数据与流水线的 bank-local slice 边界。
    """

    # Construct slice ports. / 构造 slice 端口。
    def __init__(self, configuration: OpenLLCConfig | None = None) -> None:
        c = configuration or OpenLLCConfig()
        self.configuration = c
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.req_valid = Signal(name="io_req_valid")
        self.req_ready = Signal(name="io_req_ready")
        self.req_address = Signal(c.full_address_bits, name="io_req_bits_address")
        self.req_opcode = Signal(8, name="io_req_bits_opcode")
        self.resp_valid = Signal(name="io_resp_valid")
        self.resp_ready = Signal(name="io_resp_ready")
        self.resp_data = Signal(c.data_bits, name="io_resp_bits_data")
        self.l3_miss = Signal(name="io_l3Miss")

    # Elaborate one cache bank. / 展开一个 cache bank。
    def elaborate(self, platform: Any) -> Module:
        """Connect the bank-local child closures. / 连接 bank-local 子闭包。"""

        del platform
        c = self.configuration
        m = Module()
        directory = OpenLLCDirectory(c)
        pipeline = OpenLLCPipeline(c)
        storage = OpenLLCDataStorage(c)
        m.submodules.directory = directory
        m.submodules.pipeline = pipeline
        m.submodules.storage = storage
        for child in (directory, pipeline, storage):
            m.d.comb += [child.clock.eq(self.clock), child.reset.eq(self.reset)]
        tag, set_index, _bank, offset = parse_address(0, c)
        del tag, offset
        m.d.comb += [
            self.req_ready.eq(pipeline.in_ready),
            pipeline.in_valid.eq(self.req_valid), pipeline.in_address.eq(self.req_address),
            pipeline.in_opcode.eq(self.req_opcode), pipeline.dir_hit.eq(directory.resp_hit),
            pipeline.out_ready.eq(self.resp_ready), self.resp_valid.eq(pipeline.out_valid),
            self.resp_data.eq(storage.read_data), self.l3_miss.eq(pipeline.out_miss),
            directory.read_valid.eq(self.req_valid & self.req_ready),
            directory.read_tag.eq(self.req_address >> (c.offset_bits + c.bank_bits + c.set_bits)),
            directory.read_set.eq(self.req_address >> (c.offset_bits + c.bank_bits)),
            storage.read_valid.eq(self.req_valid),
            storage.read_index.eq((self.req_address >> c.offset_bits)[:len(storage.read_index)]),
        ]
        del set_index
        return m


class OpenLLCCache(Elaboratable):
    """Top aggregate for OpenLLC.scala with bank routing and miss reduction.
    对应 OpenLLC.scala 的 bank 路由及 miss 汇总顶层聚合。
    """

    # Construct cache-level ports. / 构造 cache 级端口。
    def __init__(self, configuration: OpenLLCConfig | None = None) -> None:
        c = configuration or OpenLLCConfig()
        self.configuration = c
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.req_valid = Signal(name="io_req_valid")
        self.req_ready = Signal(name="io_req_ready")
        self.req_address = Signal(c.full_address_bits, name="io_req_bits_address")
        self.req_opcode = Signal(8, name="io_req_bits_opcode")
        self.resp_valid = Signal(name="io_resp_valid")
        self.resp_ready = Signal(name="io_resp_ready")
        self.resp_data = Signal(c.data_bits, name="io_resp_bits_data")
        self.l3_miss = Signal(name="io_l3Miss")
        self.bank_select = Signal(max(1, c.bank_bits), name="io_bankSelect")

    # Elaborate banked OpenLLC and expose a deterministic top boundary. / 展开 banked OpenLLC 并暴露确定性顶层边界。
    def elaborate(self, platform: Any) -> Module:
        """Build bank routing and response mux. / 构造 bank 路由及响应多路复用。"""

        del platform
        c = self.configuration
        m = Module()
        slices = [OpenLLCSlice(c) for _ in range(c.banks)]
        for bank, child in enumerate(slices):
            m.submodules[f"slice_{bank}"] = child
            child.clock.eq(self.clock)
            child.reset.eq(self.reset)
            m.d.comb += [
                child.req_valid.eq(self.req_valid & (self.bank_select == bank)),
                child.req_address.eq(self.req_address), child.req_opcode.eq(self.req_opcode),
                child.resp_ready.eq(self.resp_ready),
            ]
        ready: Value = Const(0)
        valid: Value = Const(0)
        data: Value = Const(0, c.data_bits)
        miss: Value = Const(0)
        for child in slices:
            ready = ready | child.req_ready
            valid = valid | child.resp_valid
            data = Mux(child.resp_valid, child.resp_data, data)
            miss = miss | child.l3_miss
        m.d.comb += [self.req_ready.eq(ready & ~self.reset), self.resp_valid.eq(valid),
                     self.resp_data.eq(data), self.l3_miss.eq(miss)]
        return m


# Compatibility names retain each Scala child in the aggregate manifest. /
# 兼容名称在聚合清单中保留每个 Scala 子模块。
LLCParam = OpenLLCConfig
Common = OpenLLCTask
DataStorage = OpenLLCDataStorage
Directory = OpenLLCDirectory
RequestBuffer = OpenLLCRequestBuffer
RequestArb = OpenLLCRequestArbiter
MainPipe = OpenLLCPipeline
MemUnit = OpenLLCPipeline
RefillUnit = OpenLLCPipeline
ResponseUnit = OpenLLCPipeline
SnoopUnit = OpenLLCPipeline
OpenLLC = OpenLLCCache
Slice = OpenLLCSlice


# =============================================================================
# Public Adapter
# =============================================================================
# Export deterministic OpenLLC cache-family SystemVerilog. / 导出确定性的 OpenLLC cache-family SystemVerilog。
def build_verilog(configuration, injected_dependencies):
    """Return Verilog for the aggregate OpenLLC cache. / 返回 OpenLLC cache 聚合的 Verilog。"""

    del injected_dependencies
    if isinstance(configuration, OpenLLCConfig):
        cfg = configuration
        name = "UHSCOpenLLCCache"
    elif isinstance(configuration, Mapping):
        fields = OpenLLCConfig.__dataclass_fields__
        values = {key: value for key, value in configuration.items() if key in fields}
        cfg = OpenLLCConfig(**values)
        name = str(configuration.get("module", configuration.get("name", "UHSCOpenLLCCache")))
    elif configuration is None:
        cfg = OpenLLCConfig()
        name = "UHSCOpenLLCCache"
    else:
        raise TypeError("configuration must be OpenLLCConfig, mapping, or None")
    top = OpenLLCCache(cfg)
    ports = [top.clock, top.reset, top.req_valid, top.req_ready, top.req_address,
             top.req_opcode, top.resp_valid, top.resp_ready, top.resp_data,
             top.l3_miss, top.bank_select]
    return verilog.convert(top, name=name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print a deterministic default export for direct invocation. / 直接调用时打印确定性的默认导出。
def main() -> None:
    """Print default OpenLLC cache Verilog. / 打印默认 OpenLLC cache Verilog。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
