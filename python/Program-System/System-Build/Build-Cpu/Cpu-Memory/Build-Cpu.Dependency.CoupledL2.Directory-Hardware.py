"""UHSC Kunminghu V2 CoupledL2 directory family boundary.
昆明湖 V2 CoupledL2 目录 family 边界。

This aggregate keeps the stateful Directory.scala contract in one
parameterised Amaranth module: two-stage tag/meta lookup, invalid-way and
replacement selection, MSHR occupancy exclusion, metadata/tag writes, and
refill replacement reporting.  Nested SRAM/ECC helpers remain represented by
the explicit family boundary instead of being fabricated as unrelated files.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, cast

from amaranth import Array, ClockDomain, Elaboratable, Memory, Module, Mux, Signal
from amaranth.hdl.ast import Value
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# Directory.scala performs a pipelined lookup and chooses a hit/invalid/LRU
# way; this aggregate exposes the same observable decisions and write ports.
# Directory.scala 执行流水化查找并选择命中/无效/LRU 路；本聚合暴露相同的
# 可观察决策和写端口。
__all__ = [
    "CoupledL2DirectoryConfig",
    "CoupledL2Directory",
    "Directory",
    "directory_reference_step",
    "TL2TLCoupledL2ParentConfig",
    "TL2TLCoupledL2Parent",
    "tl2tl_parent_port_contract",
    "build_verilog",
    "build_parent_verilog",
    "main",
]


# Typed wrappers preserve Amaranth's generator-based control contexts. / 类型包装保持 Amaranth 基于生成器的控制上下文。
# Convert a dynamic If context into a static context-manager protocol. / 将动态 If 上下文转换为静态上下文管理器协议。
def amaranth_if(module: Module, condition: Any) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.If(condition))


# Convert a dynamic Elif context into a static context-manager protocol. / 将动态 Elif 上下文转换为静态上下文管理器协议。
def amaranth_elif(module: Module, condition: Any) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.Elif(condition))


# Convert a dynamic Else context into a static context-manager protocol. / 将动态 Else 上下文转换为静态上下文管理器协议。
def amaranth_else(module: Module) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.Else())


# Narrowly cast dynamic Amaranth expressions at the DSL boundary. / 在 DSL 边界窄化动态 Amaranth 表达式类型。
def amaranth_value(expression: Any) -> Value:
    return cast(Value, expression)


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class CoupledL2DirectoryConfig:
    """Finite V2 directory geometry. / 有限 V2 目录几何参数。"""

    sets: int = 512
    ways: int = 8
    tag_bits: int = 31
    state_bits: int = 2
    client_bits: int = 1
    alias_bits: int = 2
    prefetch_src_bits: int = 3
    mshr_entries: int = 16
    mshr_id_bits: int = 8
    req_source_bits: int = 5
    replacement: str = "drrip"
    enable_tag_ecc: bool = False

    # Validate the locked Kunminghu V2 directory geometry. / 校验锁定昆明湖 V2 目录几何。
    def __post_init__(self) -> None:
        if self.sets < 1 or self.sets & (self.sets - 1):
            raise ValueError("sets must be a positive power of two")
        if self.ways < 1 or self.ways > 32:
            raise ValueError("ways must be in the range 1..32")
        if min(self.tag_bits, self.state_bits, self.client_bits, self.mshr_entries) < 1:
            raise ValueError("directory widths and entry count must be positive")
        if self.alias_bits < 0 or self.prefetch_src_bits < 0:
            raise ValueError("optional metadata widths must be non-negative")
        if self.replacement not in {"random", "plru", "drrip", "srrip", "rr"}:
            raise ValueError("unsupported replacement policy")

    # Return the set-index width. / 返回组索引位宽。
    @property
    def set_bits(self) -> int:
        return max(1, (self.sets - 1).bit_length())

    # Return the way-index width. / 返回路索引位宽。
    @property
    def way_bits(self) -> int:
        return max(1, (self.ways - 1).bit_length())

    # Return the packed metadata width. / 返回打包元数据位宽。
    @property
    def meta_bits(self) -> int:
        return (1 + self.state_bits + self.client_bits + self.alias_bits
                + 1 + self.prefetch_src_bits + 1 + 1 + 1)


# =============================================================================
# Implementation
# =============================================================================
# Compute the deterministic Directory.scala way equations. / 计算确定性的 Directory.scala 路选择方程。
def directory_reference_step(
    request_tag: int,
    tags: list[int],
    states: list[int],
    replacement_way: int,
    way_mask: int,
    occupied_mask: int = 0,
    cmo_all: bool = False,
    cmo_way: int = 0,
) -> dict[str, int]:
    """Compute the deterministic Directory.scala way equations.
    计算确定性的 Directory.scala 路选择方程。
    """

    ways = len(tags)
    if len(states) != ways:
        raise ValueError("tags/states length mismatch")
    valid = [int(state != 0) for state in states]
    hits = [int(valid[index] and tags[index] == request_tag) for index in range(ways)]
    hit_count = sum(hits)
    hit = int((hit_count == 1) or (cmo_all and 0 <= cmo_way < ways and valid[cmo_way]))
    invalid = next((index for index, value in enumerate(valid) if not value), 0)
    free = (~occupied_mask) & ((1 << ways) - 1)
    selected = cmo_way if cmo_all else (hits.index(1) if hit_count == 1 else replacement_way)
    selected &= (1 << max(1, (ways - 1).bit_length())) - 1
    if not (free & (1 << selected)):
        selected = next((index for index in range(ways) if free & (1 << index)), selected)
    if not (way_mask & (1 << selected)) and way_mask:
        selected = next((index for index in range(ways) if way_mask & (1 << index) and free & (1 << index)), selected)
    retry = int(free == 0)
    if hit_count > 1:
        hit = 0
    return {
        "hit": hit,
        "way": selected,
        "invalid_way": invalid,
        "retry": retry,
        "multi_hit": int(hit_count > 1),
        "hit_count": hit_count,
    }


class CoupledL2Directory(Elaboratable):
    # Resolve runtime-created Amaranth ports for static typing. / 为静态类型解析运行时创建的 Amaranth 端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Two-stage metadata directory with V2 replacement decisions.
    带 V2 替换决策的两级元数据目录。
    """

    # Construct the explicit directory lookup, write, and MSHR ports. / 构造显式目录查找、写入及 MSHR 端口。
    def __init__(self, configuration: CoupledL2DirectoryConfig | None = None) -> None:
        self.configuration = configuration or CoupledL2DirectoryConfig()
        c = self.configuration
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")

        # Read request and replacement context. / 读取请求及替换上下文。
        self.read_valid = Signal(name="io_read_valid")
        self.read_ready = Signal(name="io_read_ready")
        self.read_tag = Signal(c.tag_bits, name="io_read_bits_tag")
        self.read_set = Signal(c.set_bits, name="io_read_bits_set")
        self.read_way_mask = Signal(c.ways, name="io_read_bits_wayMask")
        self.read_replacer_channel = Signal(3, name="io_read_bits_replacerInfo_channel")
        self.read_replacer_opcode = Signal(3, name="io_read_bits_replacerInfo_opcode")
        self.read_replacer_req_source = Signal(c.req_source_bits, name="io_read_bits_replacerInfo_reqSource")
        self.read_replacer_refill_prefetch = Signal(name="io_read_bits_replacerInfo_refill_prefetch")
        self.read_refill = Signal(name="io_read_bits_refill")
        self.read_mshr_id = Signal(c.mshr_id_bits, name="io_read_bits_mshrId")
        self.read_cmo_all = Signal(name="io_read_bits_cmoAll")
        self.read_cmo_way = Signal(c.way_bits, name="io_read_bits_cmoWay")

        # Directory response. / 目录响应。
        self.resp_valid = Signal(name="io_resp_valid")
        self.resp_hit = Signal(name="io_resp_bits_hit")
        self.resp_tag = Signal(c.tag_bits, name="io_resp_bits_tag")
        self.resp_set = Signal(c.set_bits, name="io_resp_bits_set")
        self.resp_way = Signal(c.way_bits, name="io_resp_bits_way")
        self.resp_meta_dirty = Signal(name="io_resp_bits_meta_dirty")
        self.resp_meta_state = Signal(c.state_bits, name="io_resp_bits_meta_state")
        self.resp_meta_clients = Signal(c.client_bits, name="io_resp_bits_meta_clients")
        self.resp_meta_alias = Signal(c.alias_bits, name="io_resp_bits_meta_alias") if c.alias_bits else Signal(1, name="io_resp_bits_meta_alias")
        self.resp_meta_prefetch = Signal(name="io_resp_bits_meta_prefetch")
        self.resp_meta_prefetch_src = Signal(c.prefetch_src_bits, name="io_resp_bits_meta_prefetchSrc") if c.prefetch_src_bits else Signal(1, name="io_resp_bits_meta_prefetchSrc")
        self.resp_meta_accessed = Signal(name="io_resp_bits_meta_accessed")
        self.resp_meta_tag_err = Signal(name="io_resp_bits_meta_tagErr")
        self.resp_meta_data_err = Signal(name="io_resp_bits_meta_dataErr")
        self.resp_error = Signal(name="io_resp_bits_error")
        self.resp_replacer_channel = Signal(3, name="io_resp_bits_replacerInfo_channel")
        self.resp_replacer_opcode = Signal(3, name="io_resp_bits_replacerInfo_opcode")
        self.resp_replacer_req_source = Signal(c.req_source_bits, name="io_resp_bits_replacerInfo_reqSource")
        self.resp_replacer_refill_prefetch = Signal(name="io_resp_bits_replacerInfo_refill_prefetch")

        # Metadata and tag write requests. / 元数据及标签写请求。
        self.meta_write_valid = Signal(name="io_metaWReq_valid")
        self.meta_write_set = Signal(c.set_bits, name="io_metaWReq_bits_set")
        self.meta_write_way_oh = Signal(c.ways, name="io_metaWReq_bits_wayOH")
        self.meta_write_dirty = Signal(name="io_metaWReq_bits_wmeta_dirty")
        self.meta_write_state = Signal(c.state_bits, name="io_metaWReq_bits_wmeta_state")
        self.meta_write_clients = Signal(c.client_bits, name="io_metaWReq_bits_wmeta_clients")
        self.meta_write_alias = Signal(c.alias_bits, name="io_metaWReq_bits_wmeta_alias") if c.alias_bits else Signal(1, name="io_metaWReq_bits_wmeta_alias")
        self.meta_write_prefetch = Signal(name="io_metaWReq_bits_wmeta_prefetch")
        self.meta_write_prefetch_src = Signal(c.prefetch_src_bits, name="io_metaWReq_bits_wmeta_prefetchSrc") if c.prefetch_src_bits else Signal(1, name="io_metaWReq_bits_wmeta_prefetchSrc")
        self.meta_write_accessed = Signal(name="io_metaWReq_bits_wmeta_accessed")
        self.meta_write_tag_err = Signal(name="io_metaWReq_bits_wmeta_tagErr")
        self.meta_write_data_err = Signal(name="io_metaWReq_bits_wmeta_dataErr")
        self.tag_write_valid = Signal(name="io_tagWReq_valid")
        self.tag_write_set = Signal(c.set_bits, name="io_tagWReq_bits_set")
        self.tag_write_way = Signal(c.way_bits, name="io_tagWReq_bits_way")
        self.tag_write_tag = Signal(c.tag_bits, name="io_tagWReq_bits_wtag")

        # Refill/replacement response. / 回填/替换响应。
        self.repl_resp_valid = Signal(name="io_replResp_valid")
        self.repl_resp_tag = Signal(c.tag_bits, name="io_replResp_bits_tag")
        self.repl_resp_set = Signal(c.set_bits, name="io_replResp_bits_set")
        self.repl_resp_way = Signal(c.way_bits, name="io_replResp_bits_way")
        self.repl_resp_meta_dirty = Signal(name="io_replResp_bits_meta_dirty")
        self.repl_resp_meta_state = Signal(c.state_bits, name="io_replResp_bits_meta_state")
        self.repl_resp_meta_clients = Signal(c.client_bits, name="io_replResp_bits_meta_clients")
        self.repl_resp_meta_alias = Signal(c.alias_bits, name="io_replResp_bits_meta_alias") if c.alias_bits else Signal(1, name="io_replResp_bits_meta_alias")
        self.repl_resp_meta_prefetch = Signal(name="io_replResp_bits_meta_prefetch")
        self.repl_resp_meta_prefetch_src = Signal(c.prefetch_src_bits, name="io_replResp_bits_meta_prefetchSrc") if c.prefetch_src_bits else Signal(1, name="io_replResp_bits_meta_prefetchSrc")
        self.repl_resp_meta_accessed = Signal(name="io_replResp_bits_meta_accessed")
        self.repl_resp_meta_tag_err = Signal(name="io_replResp_bits_meta_tagErr")
        self.repl_resp_meta_data_err = Signal(name="io_replResp_bits_meta_dataErr")
        self.repl_resp_mshr_id = Signal(c.mshr_id_bits, name="io_replResp_bits_mshrId")
        self.repl_resp_retry = Signal(name="io_replResp_bits_retry")
        self.repl_resp_error = Signal(name="io_replResp_bits_error")

        # Flattened MSHR occupancy context; one bit per active MSHR. / 展平 MSHR 占用上下文，每个活动 MSHR 一位。
        self.mshr_valid = Signal(c.mshr_entries, name="io_msInfo_valid")
        self.mshr_set = Signal(c.mshr_entries * c.set_bits, name="io_msInfo_bits_set")
        self.mshr_way = Signal(c.mshr_entries * c.way_bits, name="io_msInfo_bits_way")
        self.mshr_block_refill = Signal(c.mshr_entries, name="io_msInfo_bits_blockRefill")
        self.mshr_dir_hit = Signal(c.mshr_entries, name="io_msInfo_bits_dirHit")
        self.mshr_will_free = Signal(c.mshr_entries, name="io_msInfo_bits_willFree")

    # Elaborate storage, lookup pipeline, replacement selection, and writes. / 展开存储、查找流水线、替换选择及写入。
    def elaborate(self, platform: Any) -> Module:
        del platform
        c = self.configuration
        m = Module()
        domain = ClockDomain("coupled_l2_directory", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.coupled_l2_directory = domain

        depth = c.sets * c.ways
        # Use synthesizable memories rather than one Signal per set/way.  The
        # former emits compact $mem cells and keeps default V2 generation
        # tractable (512 sets × 8 ways), while retaining synchronous writes
        # and asynchronous read ports expected by the directory pipeline.
        # 使用可综合存储器而不是每组/每路一个 Signal；前者生成紧凑的
        # $mem 单元，使默认 V2 生成可行，同时保留目录流水线所需的同步写
        # 与异步读端口。
        field_specs = (
            ("tag", c.tag_bits), ("dirty", 1), ("state", c.state_bits),
            ("clients", c.client_bits), ("alias", max(1, c.alias_bits)),
            ("prefetch", 1), ("prefetch_src", max(1, c.prefetch_src_bits)),
            ("accessed", 1), ("tag_err", 1), ("data_err", 1),
        )
        memories: dict[str, Any] = {}
        read_ports: dict[str, list[Any]] = {}
        write_ports: dict[str, Any] = {}
        for field, width in field_specs:
            memory = Memory(width=width, depth=depth, init=[0] * depth, name=f"directory_{field}")
            memories[field] = memory
            write_port = memory.write_port(domain="coupled_l2")
            write_ports[field] = write_port
            m.submodules[f"{field}_write"] = write_port
            reads: list[Any] = []
            for way in range(c.ways):
                read_port = memory.read_port(domain="comb")
                m.submodules[f"{field}_read_{way}"] = read_port
                reads.append(read_port)
            read_ports[field] = reads
        replacement_mem = Memory(width=c.way_bits, depth=c.sets, init=[0] * c.sets, name="directory_replacement")
        replacement_read = replacement_mem.read_port(domain="comb")
        replacement_write = replacement_mem.write_port(domain="coupled_l2")
        m.submodules.replacement_read = replacement_read
        m.submodules.replacement_write = replacement_write

        # Decode the flattened MSHR context for the current set. / 解码当前组的展平 MSHR 上下文。
        occupied_mask: Any = 0
        for index in range(c.mshr_entries):
            set_lo = index * c.set_bits
            way_lo = index * c.way_bits
            same_set = amaranth_value(self.mshr_set[set_lo:set_lo + c.set_bits]) == amaranth_value(self.read_set)
            active = amaranth_value(self.mshr_valid[index]) & ~amaranth_value(self.mshr_will_free[index])
            occupies = active & same_set & (amaranth_value(self.mshr_block_refill[index]) | amaranth_value(self.mshr_dir_hit[index]))
            way_value = self.mshr_way[way_lo:way_lo + c.way_bits]
            way_one_hot: Any = 0
            for way in range(c.ways):
                way_one_hot = way_one_hot | Mux(way_value == way, 1 << way, 0)
            occupied_mask = occupied_mask | Mux(occupies, way_one_hot, 0)

        # Writes are synchronous and block a simultaneous read, as in the V2 SRAM path.
        # 写入为同步操作并阻塞同周期读取，符合 V2 SRAM 路径。
        read_fire = self.read_valid & self.read_ready
        m.d.comb += self.read_ready.eq(~self.reset & ~self.meta_write_valid & ~self.tag_write_valid)
        meta_base = self.meta_write_set * c.ways
        write_way: Any = 0
        write_way_valid: Any = 0
        for way in range(c.ways):
            take = self.meta_write_way_oh[way] & ~write_way_valid
            write_way = Mux(take, way, write_way)
            write_way_valid = write_way_valid | self.meta_write_way_oh[way]
        meta_write_index = meta_base + write_way
        for field, value in (
            ("dirty", self.meta_write_dirty), ("state", self.meta_write_state),
            ("clients", self.meta_write_clients), ("alias", self.meta_write_alias),
            ("prefetch", self.meta_write_prefetch), ("prefetch_src", self.meta_write_prefetch_src),
            ("accessed", self.meta_write_accessed), ("tag_err", self.meta_write_tag_err),
            ("data_err", self.meta_write_data_err),
        ):
            port = write_ports[field]
            m.d.comb += [port.addr.eq(meta_write_index), port.data.eq(value), port.en.eq(self.meta_write_valid & write_way_valid)]
        tag_port = write_ports["tag"]
        m.d.comb += [tag_port.addr.eq(self.tag_write_set * c.ways + self.tag_write_way), tag_port.data.eq(self.tag_write_tag), tag_port.en.eq(self.tag_write_valid)]

        # Stage one captures all ways and request metadata at the read edge. / 一级在读取边沿捕获所有路及请求元数据。
        req1_valid = Signal(name="directory_req1_valid")
        req1_tag = Signal(c.tag_bits, name="directory_req1_tag")
        req1_set = Signal(c.set_bits, name="directory_req1_set")
        req1_way_mask = Signal(c.ways, name="directory_req1_way_mask")
        req1_refill = Signal(name="directory_req1_refill")
        req1_mshr_id = Signal(c.mshr_id_bits, name="directory_req1_mshr_id")
        req1_cmo_all = Signal(name="directory_req1_cmo_all")
        req1_cmo_way = Signal(c.way_bits, name="directory_req1_cmo_way")
        req1_channel = Signal(3, name="directory_req1_channel")
        req1_opcode = Signal(3, name="directory_req1_opcode")
        req1_req_source = Signal(c.req_source_bits, name="directory_req1_req_source")
        req1_refill_prefetch = Signal(name="directory_req1_refill_prefetch")
        tags1 = [Signal(c.tag_bits, name=f"directory_tags1_{way}") for way in range(c.ways)]
        dirty1 = [Signal(name=f"directory_dirty1_{way}") for way in range(c.ways)]
        states1 = [Signal(c.state_bits, name=f"directory_states1_{way}") for way in range(c.ways)]
        clients1 = [Signal(c.client_bits, name=f"directory_clients1_{way}") for way in range(c.ways)]
        aliases1 = [Signal(max(1, c.alias_bits), name=f"directory_aliases1_{way}") for way in range(c.ways)]
        prefetch1 = [Signal(name=f"directory_prefetch1_{way}") for way in range(c.ways)]
        prefetch_src1 = [Signal(max(1, c.prefetch_src_bits), name=f"directory_prefetch_src1_{way}") for way in range(c.ways)]
        accessed1 = [Signal(name=f"directory_accessed1_{way}") for way in range(c.ways)]
        tag_err1 = [Signal(name=f"directory_tag_err1_{way}") for way in range(c.ways)]
        data_err1 = [Signal(name=f"directory_data_err1_{way}") for way in range(c.ways)]

        # Stage two is the externally visible response stage. / 二级是对外可见的响应级。
        req2_valid = Signal(name="directory_req2_valid")
        req2_tag = Signal(c.tag_bits, name="directory_req2_tag")
        req2_set = Signal(c.set_bits, name="directory_req2_set")
        req2_way_mask = Signal(c.ways, name="directory_req2_way_mask")
        req2_refill = Signal(name="directory_req2_refill")
        req2_mshr_id = Signal(c.mshr_id_bits, name="directory_req2_mshr_id")
        req2_cmo_all = Signal(name="directory_req2_cmo_all")
        req2_cmo_way = Signal(c.way_bits, name="directory_req2_cmo_way")
        req2_channel = Signal(3, name="directory_req2_channel")
        req2_opcode = Signal(3, name="directory_req2_opcode")
        req2_req_source = Signal(c.req_source_bits, name="directory_req2_req_source")
        req2_refill_prefetch = Signal(name="directory_req2_refill_prefetch")
        tags2 = [Signal(c.tag_bits, name=f"directory_tags2_{way}") for way in range(c.ways)]
        dirty2 = [Signal(name=f"directory_dirty2_{way}") for way in range(c.ways)]
        states2 = [Signal(c.state_bits, name=f"directory_states2_{way}") for way in range(c.ways)]
        clients2 = [Signal(c.client_bits, name=f"directory_clients2_{way}") for way in range(c.ways)]
        aliases2 = [Signal(max(1, c.alias_bits), name=f"directory_aliases2_{way}") for way in range(c.ways)]
        prefetch2 = [Signal(name=f"directory_prefetch2_{way}") for way in range(c.ways)]
        prefetch_src2 = [Signal(max(1, c.prefetch_src_bits), name=f"directory_prefetch_src2_{way}") for way in range(c.ways)]
        accessed2 = [Signal(name=f"directory_accessed2_{way}") for way in range(c.ways)]
        tag_err2 = [Signal(name=f"directory_tag_err2_{way}") for way in range(c.ways)]
        data_err2 = [Signal(name=f"directory_data_err2_{way}") for way in range(c.ways)]

        # Stage one read and stage two transfer. / 一级读取及二级传递。
        m.d.coupled_l2_directory += [
            req1_valid.eq(read_fire),
            req1_tag.eq(self.read_tag),
            req1_set.eq(self.read_set),
            req1_way_mask.eq(self.read_way_mask),
            req1_refill.eq(self.read_refill),
            req1_mshr_id.eq(self.read_mshr_id),
            req1_cmo_all.eq(self.read_cmo_all),
            req1_cmo_way.eq(self.read_cmo_way),
            req1_channel.eq(self.read_replacer_channel),
            req1_opcode.eq(self.read_replacer_opcode),
            req1_req_source.eq(self.read_replacer_req_source),
            req1_refill_prefetch.eq(self.read_replacer_refill_prefetch),
            req2_valid.eq(req1_valid),
            req2_tag.eq(req1_tag),
            req2_set.eq(req1_set),
            req2_way_mask.eq(req1_way_mask),
            req2_refill.eq(req1_refill),
            req2_mshr_id.eq(req1_mshr_id),
            req2_cmo_all.eq(req1_cmo_all),
            req2_cmo_way.eq(req1_cmo_way),
            req2_channel.eq(req1_channel),
            req2_opcode.eq(req1_opcode),
            req2_req_source.eq(req1_req_source),
            req2_refill_prefetch.eq(req1_refill_prefetch),
        ]
        read_index = self.read_set
        m.d.comb += replacement_read.addr.eq(self.read_set)
        for way in range(c.ways):
            index_expr = read_index + way
            for field, stage1 in (
                ("tag", tags1[way]), ("dirty", dirty1[way]), ("state", states1[way]),
                ("clients", clients1[way]), ("alias", aliases1[way]),
                ("prefetch", prefetch1[way]), ("prefetch_src", prefetch_src1[way]),
                ("accessed", accessed1[way]), ("tag_err", tag_err1[way]),
                ("data_err", data_err1[way]),
            ):
                read_port = read_ports[field][way]
                m.d.comb += read_port.addr.eq(index_expr)
                m.d.coupled_l2_directory += stage1.eq(read_port.data)
            m.d.coupled_l2_directory += [
                tags2[way].eq(tags1[way]),
                dirty2[way].eq(dirty1[way]),
                states2[way].eq(states1[way]),
                clients2[way].eq(clients1[way]),
                aliases2[way].eq(aliases1[way]),
                prefetch2[way].eq(prefetch1[way]),
                prefetch_src2[way].eq(prefetch_src1[way]),
                accessed2[way].eq(accessed1[way]),
                tag_err2[way].eq(tag_err1[way]),
                data_err2[way].eq(data_err1[way]),
            ]

        # Hit/invalid/replacement equations at stage two. / 二级命中、无效及替换方程。
        hit_vec: list[Any] = []
        invalid_vec: list[Any] = []
        for way in range(c.ways):
            valid = states2[way] != 0
            hit_vec.append(valid & (tags2[way] == req2_tag))
            invalid_vec.append(~valid)
        hit_count = sum(hit_vec)
        multi_hit = hit_count > 1
        hit_any = (hit_count == 1) & ~multi_hit
        hit_way: Any = 0
        for way in range(c.ways):
            hit_way = Mux(hit_vec[way], way, hit_way)
        invalid_way: Any = 0
        invalid_seen: Any = 0
        for way in range(c.ways):
            take = invalid_vec[way] & ~invalid_seen
            invalid_way = Mux(take, way, invalid_way)
            invalid_seen = invalid_seen | invalid_vec[way]
        repl_way = replacement_read.data
        free_mask = (~occupied_mask) & ((1 << c.ways) - 1)
        selected_way: Any = repl_way
        selected_way = Mux(invalid_seen, invalid_way, selected_way)
        selected_way = Mux(hit_any, hit_way, selected_way)
        selected_way = Mux(req2_cmo_all, req2_cmo_way, selected_way)
        # Respect MSHR free-way exclusion and caller way mask. / 遵守 MSHR 空闲路排除及调用者路掩码。
        free_selected = free_mask.bit_select(selected_way, 1)
        first_free: Any = 0
        first_free_seen: Any = 0
        for way in range(c.ways):
            take = free_mask[way] & ~first_free_seen
            first_free = Mux(take, way, first_free)
            first_free_seen = first_free_seen | take
        selected_way = Mux(~free_selected, first_free, selected_way)
        masked_selected = self.read_way_mask.bit_select(selected_way, 1)
        first_masked: Any = 0
        first_masked_seen: Any = 0
        for way in range(c.ways):
            take = amaranth_value(self.read_way_mask[way]) & amaranth_value(free_mask[way]) & ~amaranth_value(first_masked_seen)
            first_masked = Mux(take, way, first_masked)
            first_masked_seen = amaranth_value(first_masked_seen) | amaranth_value(take)
        selected_way = Mux(~amaranth_value(masked_selected) & (amaranth_value(self.read_way_mask) != 0), first_masked, selected_way)
        retry = ~amaranth_value(free_mask.any())
        selected_meta = lambda values: Array(values)[selected_way]

        # Public response and refill response fields. / 对外响应及回填响应字段。
        m.d.comb += [
            self.resp_valid.eq(req2_valid),
            self.resp_hit.eq((amaranth_value(hit_any) | (amaranth_value(req2_cmo_all) & ~amaranth_value(Array(invalid_vec)[req2_cmo_way]))) & ~amaranth_value(multi_hit)),
            self.resp_tag.eq(selected_meta(tags2)),
            self.resp_set.eq(req2_set),
            self.resp_way.eq(selected_way),
            self.resp_meta_dirty.eq(selected_meta(dirty2)),
            self.resp_meta_state.eq(selected_meta(states2)),
            self.resp_meta_clients.eq(selected_meta(clients2)),
            self.resp_meta_alias.eq(selected_meta(aliases2)),
            self.resp_meta_prefetch.eq(selected_meta(prefetch2)),
            self.resp_meta_prefetch_src.eq(selected_meta(prefetch_src2)),
            self.resp_meta_accessed.eq(selected_meta(accessed2)),
            self.resp_meta_tag_err.eq(selected_meta(tag_err2)),
            self.resp_meta_data_err.eq(selected_meta(data_err2)),
            self.resp_error.eq((selected_meta(tag_err2) | selected_meta(data_err2) | multi_hit) & req2_valid),
            self.resp_replacer_channel.eq(req2_channel),
            self.resp_replacer_opcode.eq(req2_opcode),
            self.resp_replacer_req_source.eq(req2_req_source),
            self.resp_replacer_refill_prefetch.eq(req2_refill_prefetch),
            self.repl_resp_valid.eq(req2_valid & req2_refill),
            self.repl_resp_tag.eq(selected_meta(tags2)),
            self.repl_resp_set.eq(req2_set),
            self.repl_resp_way.eq(selected_way),
            self.repl_resp_meta_dirty.eq(selected_meta(dirty2)),
            self.repl_resp_meta_state.eq(selected_meta(states2)),
            self.repl_resp_meta_clients.eq(selected_meta(clients2)),
            self.repl_resp_meta_alias.eq(selected_meta(aliases2)),
            self.repl_resp_meta_prefetch.eq(selected_meta(prefetch2)),
            self.repl_resp_meta_prefetch_src.eq(selected_meta(prefetch_src2)),
            self.repl_resp_meta_accessed.eq(selected_meta(accessed2)),
            self.repl_resp_meta_tag_err.eq(selected_meta(tag_err2)),
            self.repl_resp_meta_data_err.eq(selected_meta(data_err2)),
            self.repl_resp_mshr_id.eq(req2_mshr_id),
            self.repl_resp_retry.eq(retry & req2_refill),
            self.repl_resp_error.eq((selected_meta(tag_err2) | selected_meta(data_err2) | multi_hit) & req2_valid),
        ]

        # Round-robin update is a deterministic bounded stand-in for V2 PLRU/DRRIP state.
        # 轮询更新是 V2 PLRU/DRRIP 状态的确定性有界实现。
        replacement_update = req2_valid & (hit_any | (req2_refill & ~retry))
        m.d.comb += [
            replacement_write.addr.eq(req2_set),
            replacement_write.data.eq(selected_way + 1),
            replacement_write.en.eq(replacement_update & ~self.reset),
        ]
        with amaranth_if(m, self.reset):
            m.d.coupled_l2_directory += [req1_valid.eq(0), req2_valid.eq(0)]

        return m


# Compact memory-backed implementation used by the public adapter.  The
# original class above documents the direct signal form; this implementation
# keeps identical ports while avoiding a per-entry mux tree at default V2
# geometry. / 公共适配器使用紧凑的存储器实现；上方类保留直接信号形式的
# 溯源文档，本实现保持相同端口并避免默认几何下逐项多路树。
_LegacyCoupledL2Directory = CoupledL2Directory


class CompactCoupledL2Directory(Elaboratable):
    # Resolve runtime-created Amaranth ports for static typing. / 为静态类型解析运行时创建的 Amaranth 端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Packed-memory CoupledL2 Directory implementation. / 打包存储器 CoupledL2 目录实现。"""

    # Construct the same public boundary as CoupledL2Directory. / 构造与 CoupledL2Directory 相同的公共边界。
    def __init__(self, configuration: CoupledL2DirectoryConfig | None = None) -> None:
        # Reuse the public port declaration without elaborating the legacy body. / 复用公共端口声明但不展开旧实现主体。
        # Invoke the declarative port constructor on a plain object so the
        # legacy Elaboratable is not registered as an unused instance.
        # 在普通对象上调用声明式端口构造器，避免将旧 Elaboratable 注册为未使用实例。
        template = type("_DirectoryPortTemplate", (), {})()
        _LegacyCoupledL2Directory.__init__(cast(_LegacyCoupledL2Directory, template), configuration)
        self.__dict__.update(vars(template))
        self.configuration = configuration or CoupledL2DirectoryConfig()

    # Elaborate packed tag/meta memories and the two-stage directory equations. / 展开打包标签/元数据存储及两级目录方程。
    def elaborate(self, platform: Any) -> Module:
        del platform
        c = self.configuration
        m = Module()
        domain = ClockDomain("coupled_l2_directory", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.coupled_l2_directory = domain
        depth = c.sets * c.ways
        alias_width = max(1, c.alias_bits)
        prefetch_width = max(1, c.prefetch_src_bits)
        offsets = {"dirty": 0, "state": 1, "clients": 1 + c.state_bits,
                   "alias": 1 + c.state_bits + c.client_bits}
        offsets["prefetch"] = offsets["alias"] + alias_width
        offsets["prefetch_src"] = offsets["prefetch"] + 1
        offsets["accessed"] = offsets["prefetch_src"] + prefetch_width
        offsets["tag_err"] = offsets["accessed"] + 1
        offsets["data_err"] = offsets["tag_err"] + 1
        meta_width = offsets["data_err"] + 1
        # Bank memories by way, matching Directory.scala's one SRAM bank per
        # way and avoiding a flattened set×way address mux. / 按路分 bank，
        # 对应 Directory.scala 每路一个 SRAM bank，并避免扁平组×路地址多路器。
        tag_mem = [Memory(width=c.tag_bits, depth=c.sets, init=[0] * c.sets, name=f"directory_tag_{way}") for way in range(c.ways)]
        meta_mem = [Memory(width=meta_width, depth=c.sets, init=[0] * c.sets, name=f"directory_meta_{way}") for way in range(c.ways)]
        replacement_mem = Memory(width=c.way_bits, depth=c.sets, init=[0] * c.sets, name="directory_replacement")
        replacement_read = replacement_mem.read_port(domain="comb")
        replacement_write = replacement_mem.write_port(domain="coupled_l2_directory")
        m.submodules.replacement_read = replacement_read
        m.submodules.replacement_write = replacement_write
        tag_reads = []
        meta_reads = []
        tag_writes = []
        meta_writes = []
        for way in range(c.ways):
            tag_read = tag_mem[way].read_port(domain="comb")
            meta_read = meta_mem[way].read_port(domain="comb")
            tag_write = tag_mem[way].write_port(domain="coupled_l2_directory")
            meta_write = meta_mem[way].write_port(domain="coupled_l2_directory")
            m.submodules[f"tag_read_{way}"] = tag_read
            m.submodules[f"meta_read_{way}"] = meta_read
            m.submodules[f"tag_write_{way}"] = tag_write
            m.submodules[f"meta_write_{way}"] = meta_write
            tag_reads.append(tag_read)
            meta_reads.append(meta_read)
            tag_writes.append(tag_write)
            meta_writes.append(meta_write)
        self._debug_tag_reads = tag_reads
        self._debug_meta_reads = meta_reads
        self._debug_tag_writes = tag_writes
        self._debug_meta_writes = meta_writes

        # Build the MSHR way occupancy mask for the requested set. / 构造请求组的 MSHR 路占用掩码。
        occupied_mask: Any = 0
        for index in range(c.mshr_entries):
            set_lo = index * c.set_bits
            way_lo = index * c.way_bits
            same_set = amaranth_value(self.mshr_set[set_lo:set_lo + c.set_bits]) == amaranth_value(self.read_set)
            active = amaranth_value(self.mshr_valid[index]) & ~amaranth_value(self.mshr_will_free[index])
            occupies = active & same_set & (amaranth_value(self.mshr_block_refill[index]) | amaranth_value(self.mshr_dir_hit[index]))
            way_value = self.mshr_way[way_lo:way_lo + c.way_bits]
            way_one_hot: Any = 0
            for way in range(c.ways):
                way_one_hot = way_one_hot | Mux(way_value == way, 1 << way, 0)
            occupied_mask = occupied_mask | Mux(occupies, way_one_hot, 0)

        # Select the first asserted metadata write way. / 选择首个置位的元数据写路。
        write_way: Any = 0
        write_way_valid: Any = 0
        for way in range(c.ways):
            take = amaranth_value(self.meta_write_way_oh[way]) & ~amaranth_value(write_way_valid)
            write_way = Mux(take, way, write_way)
            write_way_valid = amaranth_value(write_way_valid) | amaranth_value(self.meta_write_way_oh[way])
        write_index = self.meta_write_set
        payload = Signal(meta_width, name="directory_meta_write_payload")
        self._debug_meta_payload = payload
        m.d.comb += [
            payload.eq(0), cast(Signal, payload[offsets["dirty"]]).eq(self.meta_write_dirty),
            cast(Signal, payload[offsets["state"]:offsets["state"] + c.state_bits]).eq(self.meta_write_state),
            cast(Signal, payload[offsets["clients"]:offsets["clients"] + c.client_bits]).eq(self.meta_write_clients),
            cast(Signal, payload[offsets["alias"]:offsets["alias"] + alias_width]).eq(self.meta_write_alias),
            cast(Signal, payload[offsets["prefetch"]]).eq(self.meta_write_prefetch),
            cast(Signal, payload[offsets["prefetch_src"]:offsets["prefetch_src"] + prefetch_width]).eq(self.meta_write_prefetch_src),
            cast(Signal, payload[offsets["accessed"]]).eq(self.meta_write_accessed),
            cast(Signal, payload[offsets["tag_err"]]).eq(self.meta_write_tag_err),
            cast(Signal, payload[offsets["data_err"]]).eq(self.meta_write_data_err),
            replacement_read.addr.eq(self.read_set),
        ]
        for way in range(c.ways):
            m.d.comb += [
                meta_writes[way].addr.eq(write_index), meta_writes[way].data.eq(payload),
                meta_writes[way].en.eq(self.meta_write_valid & write_way_valid & (write_way == way) & ~self.reset),
                tag_writes[way].addr.eq(self.tag_write_set), tag_writes[way].data.eq(self.tag_write_tag),
                tag_writes[way].en.eq(self.tag_write_valid & (self.tag_write_way == way) & ~self.reset),
            ]

        # Request and memory-data pipeline registers. / 请求及存储数据流水寄存器。
        req1_valid = Signal(name="directory_req1_valid")
        req1_tag = Signal(c.tag_bits, name="directory_req1_tag")
        req1_set = Signal(c.set_bits, name="directory_req1_set")
        req1_way_mask = Signal(c.ways, name="directory_req1_way_mask")
        req1_refill = Signal(name="directory_req1_refill")
        req1_mshr_id = Signal(c.mshr_id_bits, name="directory_req1_mshr_id")
        req1_cmo_all = Signal(name="directory_req1_cmo_all")
        req1_cmo_way = Signal(c.way_bits, name="directory_req1_cmo_way")
        req1_channel = Signal(3, name="directory_req1_channel")
        req1_opcode = Signal(3, name="directory_req1_opcode")
        req1_req_source = Signal(c.req_source_bits, name="directory_req1_req_source")
        req1_refill_prefetch = Signal(name="directory_req1_refill_prefetch")
        req2_valid = Signal(name="directory_req2_valid")
        req2_tag = Signal(c.tag_bits, name="directory_req2_tag")
        req2_set = Signal(c.set_bits, name="directory_req2_set")
        req2_way_mask = Signal(c.ways, name="directory_req2_way_mask")
        req2_refill = Signal(name="directory_req2_refill")
        req2_mshr_id = Signal(c.mshr_id_bits, name="directory_req2_mshr_id")
        req2_cmo_all = Signal(name="directory_req2_cmo_all")
        req2_cmo_way = Signal(c.way_bits, name="directory_req2_cmo_way")
        req2_channel = Signal(3, name="directory_req2_channel")
        req2_opcode = Signal(3, name="directory_req2_opcode")
        req2_req_source = Signal(c.req_source_bits, name="directory_req2_req_source")
        req2_refill_prefetch = Signal(name="directory_req2_refill_prefetch")
        meta1 = [Signal(meta_width, name=f"directory_meta1_{way}") for way in range(c.ways)]
        tag1 = [Signal(c.tag_bits, name=f"directory_tag1_{way}") for way in range(c.ways)]
        meta2 = [Signal(meta_width, name=f"directory_meta2_{way}") for way in range(c.ways)]
        tag2 = [Signal(c.tag_bits, name=f"directory_tag2_{way}") for way in range(c.ways)]
        self._debug_tag2 = tag2
        self._debug_meta2 = meta2
        read_fire = self.read_valid & self.read_ready
        m.d.comb += self.read_ready.eq(~self.reset & ~self.meta_write_valid & ~self.tag_write_valid)
        m.d.coupled_l2_directory += [
            req1_valid.eq(read_fire), req1_tag.eq(self.read_tag), req1_set.eq(self.read_set),
            req1_way_mask.eq(self.read_way_mask), req1_refill.eq(self.read_refill),
            req1_mshr_id.eq(self.read_mshr_id), req1_cmo_all.eq(self.read_cmo_all), req1_cmo_way.eq(self.read_cmo_way),
            req1_channel.eq(self.read_replacer_channel), req1_opcode.eq(self.read_replacer_opcode),
            req1_req_source.eq(self.read_replacer_req_source), req1_refill_prefetch.eq(self.read_replacer_refill_prefetch),
            req2_valid.eq(req1_valid), req2_tag.eq(req1_tag), req2_set.eq(req1_set), req2_way_mask.eq(req1_way_mask),
            req2_refill.eq(req1_refill), req2_mshr_id.eq(req1_mshr_id), req2_cmo_all.eq(req1_cmo_all), req2_cmo_way.eq(req1_cmo_way),
            req2_channel.eq(req1_channel), req2_opcode.eq(req1_opcode), req2_req_source.eq(req1_req_source), req2_refill_prefetch.eq(req1_refill_prefetch),
        ]
        read_index = self.read_set
        for way in range(c.ways):
            m.d.comb += [tag_reads[way].addr.eq(read_index), meta_reads[way].addr.eq(read_index)]
            m.d.coupled_l2_directory += [tag1[way].eq(tag_reads[way].data), meta1[way].eq(meta_reads[way].data), tag2[way].eq(tag1[way]), meta2[way].eq(meta1[way])]

        # Calculate hit, invalid-way, free-way, and response metadata. / 计算命中、无效路、空闲路及响应元数据。
        valid_vec = [meta2[way][offsets["state"]:offsets["state"] + c.state_bits] != 0 for way in range(c.ways)]
        hit_vec = [valid_vec[way] & (tag2[way] == req2_tag) for way in range(c.ways)]
        hit_count = sum(hit_vec)
        multi_hit = hit_count > 1
        hit_any = (hit_count == 1) & ~multi_hit
        hit_way: Any = 0
        invalid_way: Any = 0
        invalid_seen: Any = 0
        for way in range(c.ways):
            hit_way = Mux(hit_vec[way], way, hit_way)
            take = ~valid_vec[way] & ~invalid_seen
            invalid_way = Mux(take, way, invalid_way)
            invalid_seen = invalid_seen | ~valid_vec[way]
        free_mask = (~occupied_mask) & ((1 << c.ways) - 1)
        selected_way: Any = replacement_read.data
        selected_way = Mux(invalid_seen, invalid_way, selected_way)
        selected_way = Mux(hit_any, hit_way, selected_way)
        selected_way = Mux(req2_cmo_all, req2_cmo_way, selected_way)
        free_selected = free_mask.bit_select(selected_way, 1)
        first_free: Any = 0
        first_free_seen: Any = 0
        for way in range(c.ways):
            take = free_mask[way] & ~first_free_seen
            first_free = Mux(take, way, first_free)
            first_free_seen = first_free_seen | take
        selected_way = Mux(~free_selected, first_free, selected_way)
        masked_selected = req2_way_mask.bit_select(selected_way, 1)
        first_masked: Any = 0
        first_masked_seen: Any = 0
        for way in range(c.ways):
            take = amaranth_value(req2_way_mask[way]) & amaranth_value(free_mask[way]) & ~amaranth_value(first_masked_seen)
            first_masked = Mux(take, way, first_masked)
            first_masked_seen = amaranth_value(first_masked_seen) | amaranth_value(take)
        selected_way = Mux(~amaranth_value(masked_selected) & (amaranth_value(req2_way_mask) != 0), first_masked, selected_way)
        retry = ~amaranth_value(free_mask.any())
        selected_tag = Array(tag2)[selected_way]
        selected_meta = Array(meta2)[selected_way]
        selected_state = selected_meta[offsets["state"]:offsets["state"] + c.state_bits]
        selected_alias = selected_meta[offsets["alias"]:offsets["alias"] + alias_width]
        selected_prefetch_src = selected_meta[offsets["prefetch_src"]:offsets["prefetch_src"] + prefetch_width]
        m.d.comb += [
            self.resp_valid.eq(req2_valid), self.resp_hit.eq((hit_any | (req2_cmo_all & Array(valid_vec)[req2_cmo_way])) & ~multi_hit),
            self.resp_tag.eq(selected_tag), self.resp_set.eq(req2_set), self.resp_way.eq(selected_way),
            self.resp_meta_dirty.eq(selected_meta[offsets["dirty"]]), self.resp_meta_state.eq(selected_state),
            self.resp_meta_clients.eq(selected_meta[offsets["clients"]:offsets["clients"] + c.client_bits]), self.resp_meta_alias.eq(selected_alias),
            self.resp_meta_prefetch.eq(selected_meta[offsets["prefetch"]]), self.resp_meta_prefetch_src.eq(selected_prefetch_src),
            self.resp_meta_accessed.eq(selected_meta[offsets["accessed"]]), self.resp_meta_tag_err.eq(selected_meta[offsets["tag_err"]]),
            self.resp_meta_data_err.eq(selected_meta[offsets["data_err"]]), self.resp_error.eq((selected_meta[offsets["tag_err"]] | selected_meta[offsets["data_err"]] | multi_hit) & req2_valid),
            self.resp_replacer_channel.eq(req2_channel), self.resp_replacer_opcode.eq(req2_opcode), self.resp_replacer_req_source.eq(req2_req_source), self.resp_replacer_refill_prefetch.eq(req2_refill_prefetch),
            self.repl_resp_valid.eq(req2_valid & req2_refill), self.repl_resp_tag.eq(selected_tag), self.repl_resp_set.eq(req2_set), self.repl_resp_way.eq(selected_way),
            self.repl_resp_meta_dirty.eq(selected_meta[offsets["dirty"]]), self.repl_resp_meta_state.eq(selected_state), self.repl_resp_meta_clients.eq(selected_meta[offsets["clients"]:offsets["clients"] + c.client_bits]), self.repl_resp_meta_alias.eq(selected_alias),
            self.repl_resp_meta_prefetch.eq(selected_meta[offsets["prefetch"]]), self.repl_resp_meta_prefetch_src.eq(selected_prefetch_src), self.repl_resp_meta_accessed.eq(selected_meta[offsets["accessed"]]), self.repl_resp_meta_tag_err.eq(selected_meta[offsets["tag_err"]]), self.repl_resp_meta_data_err.eq(selected_meta[offsets["data_err"]]),
            self.repl_resp_mshr_id.eq(req2_mshr_id), self.repl_resp_retry.eq(retry & req2_refill), self.repl_resp_error.eq((selected_meta[offsets["tag_err"]] | selected_meta[offsets["data_err"]] | multi_hit) & req2_valid),
        ]
        replacement_update = req2_valid & (hit_any | (req2_refill & ~retry))
        m.d.comb += [replacement_write.addr.eq(req2_set), replacement_write.data.eq(selected_way + 1), replacement_write.en.eq(replacement_update & ~self.reset)]
        with amaranth_if(m, self.reset):
            m.d.coupled_l2_directory += [req1_valid.eq(0), req2_valid.eq(0)]
        return m


# Public names select the compact implementation while retaining the Scala
# family alias expected by downstream manifests. / 公共名称选择紧凑实现，
# 同时保留下游台账所需的 Scala family 别名。
CoupledL2Directory = cast(type[CoupledL2Directory], CompactCoupledL2Directory)
Directory = CompactCoupledL2Directory


# =============================================================================
# TL2TL parent boundary
# =============================================================================
# The locked DefaultConfig instantiates TL2TLCoupledL2 rather than the
# conditional CHI bridge.  Keep its four-bank Diplomacy envelope in this
# aggregate so the selected top has one source-shaped parent target.
# 锁定的 DefaultConfig 实例化 TL2TLCoupledL2，而不是条件式 CHI bridge；在
# 本聚合中保留四 bank Diplomacy 包络，使选定顶层具有一个源形状父级目标。
@dataclass(frozen=True)
class TL2TLCoupledL2ParentConfig:
    """Locked V2 TL2TL parent geometry. / 锁定 V2 TL2TL 父级几何参数。"""

    banks: int = 4
    address_bits: int = 48
    bank_bits: int = 2
    offset_bits: int = 6
    data_bits: int = 256
    inner_source_bits: int = 7
    outer_source_bits: int = 8
    inner_sink_bits: int = 8
    outer_sink_bits: int = 6
    req_source_bits: int = 5
    vaddr_bits: int = 44
    perf_count: int = 68

    # Validate the generated TL2TLCoupledL2 dimensions. / 校验生成 TL2TLCoupledL2 的尺寸。
    def __post_init__(self) -> None:
        if self.banks != 4:
            raise ValueError("locked Kunminghu V2 TL2TL parent uses four banks")
        if self.address_bits != 48 or self.bank_bits != 2 or self.offset_bits != 6 or self.data_bits != 256:
            raise ValueError("locked Kunminghu V2 TL2TL parent uses 48/256-bit addresses/data")
        if self.inner_source_bits != 7 or self.outer_source_bits != 8:
            raise ValueError("locked TL2TL source widths are 7 and 8 bits")
        if self.inner_sink_bits != 8 or self.outer_sink_bits != 6:
            raise ValueError("locked TL2TL sink widths are 8 and 6 bits")
        if self.req_source_bits != 5 or self.vaddr_bits != 44:
            raise ValueError("locked TL2TL request metadata widths are 5 and 44 bits")
        if self.perf_count != 68:
            raise ValueError("locked TL2TL parent exposes 68 performance counters")


# Return the exact ordered 540-port TL2TL parent contract. / 返回精确有序的 540 端口 TL2TL 父级契约。
def tl2tl_parent_port_contract(configuration: TL2TLCoupledL2ParentConfig | None = None) -> tuple[dict[str, Any], ...]:
    """Describe the locked TL2TLCoupledL2 ANSI envelope. / 描述锁定 TL2TLCoupledL2 ANSI 包络。"""

    cfg = configuration or TL2TLCoupledL2ParentConfig()
    entries: list[dict[str, Any]] = []

    # Append one source-shaped declaration while preserving generator order. / 追加源形状声明并保持生成器顺序。
    def add(name: str, width: int, direction: str) -> None:
        """Append a normalized port row. / 追加规范化端口行。"""

        entries.append({"name": name, "width": max(1, int(width)), "direction": direction})

    add("clock", 1, "input")
    add("reset", 1, "input")
    # Temporal-prefetch metadata bridge (one Valid input and one Decoupled output). /
    # Temporal-prefetch 元数据桥（一个 Valid 输入和一个 Decoupled 输出）。
    for name, width, direction in (
        ("auto_tpmeta_sink_in_valid", 1, "input"),
        ("auto_tpmeta_sink_in_bits_hartid", 6, "input"),
    ):
        add(name, width, direction)
    for index in range(12):
        add(f"auto_tpmeta_sink_in_bits_rawData_{index}", 42, "input")
    add("auto_tpmeta_source_out_ready", 1, "input")
    for name, width in (
        ("auto_tpmeta_source_out_valid", 1),
        ("auto_tpmeta_source_out_bits_hartid", 6),
        ("auto_tpmeta_source_out_bits_set", 10),
        ("auto_tpmeta_source_out_bits_way", 4),
        ("auto_tpmeta_source_out_bits_wmode", 1),
    ):
        add(name, width, "output")
    for index in range(12):
        add(f"auto_tpmeta_source_out_bits_rawData_{index}", 42, "output")

    # Four inner (L1-facing) TileLink ports. / 四个内侧（面向 L1）的 TileLink 端口。
    for bank in reversed(range(cfg.banks)):
        prefix = f"auto_in_{bank}_"
        rows = (
            ("a_ready", 1, "output"), ("a_valid", 1, "input"),
            ("a_bits_opcode", 4, "input"), ("a_bits_param", 3, "input"),
            ("a_bits_size", 3, "input"), ("a_bits_source", cfg.inner_source_bits, "input"),
            ("a_bits_address", cfg.address_bits, "input"), ("a_bits_user_reqSource", cfg.req_source_bits, "input"),
            ("a_bits_user_alias", 2, "input"), ("a_bits_user_vaddr", cfg.vaddr_bits, "input"),
            ("a_bits_user_needHint", 1, "input"), ("a_bits_echo_isKeyword", 1, "input"),
            ("a_bits_mask", cfg.data_bits // 8, "input"), ("a_bits_data", cfg.data_bits, "input"),
            ("a_bits_corrupt", 1, "input"), ("b_ready", 1, "input"), ("b_valid", 1, "output"),
            ("b_bits_opcode", 3, "output"), ("b_bits_param", 2, "output"), ("b_bits_size", 3, "output"),
            ("b_bits_source", cfg.inner_source_bits, "output"), ("b_bits_address", cfg.address_bits, "output"),
            ("b_bits_mask", cfg.data_bits // 8, "output"), ("b_bits_data", cfg.data_bits, "output"),
            ("b_bits_corrupt", 1, "output"), ("c_ready", 1, "output"), ("c_valid", 1, "input"),
            ("c_bits_opcode", 3, "input"), ("c_bits_param", 3, "input"), ("c_bits_size", 3, "input"),
            ("c_bits_source", cfg.inner_source_bits, "input"), ("c_bits_address", cfg.address_bits, "input"),
            ("c_bits_user_reqSource", cfg.req_source_bits, "input"), ("c_bits_user_alias", 2, "input"),
            ("c_bits_user_vaddr", cfg.vaddr_bits, "input"), ("c_bits_user_needHint", 1, "input"),
            ("c_bits_echo_isKeyword", 1, "input"), ("c_bits_data", cfg.data_bits, "input"),
            ("c_bits_corrupt", 1, "input"), ("d_ready", 1, "input"), ("d_valid", 1, "output"),
            ("d_bits_opcode", 4, "output"), ("d_bits_param", 2, "output"), ("d_bits_size", 3, "output"),
            ("d_bits_source", cfg.inner_source_bits, "output"), ("d_bits_sink", cfg.inner_sink_bits, "output"),
            ("d_bits_denied", 1, "output"), ("d_bits_echo_isKeyword", 1, "output"),
            ("d_bits_data", cfg.data_bits, "output"), ("d_bits_corrupt", 1, "output"),
            ("e_ready", 1, "output"), ("e_valid", 1, "input"), ("e_bits_sink", cfg.inner_sink_bits, "input"),
        )
        for suffix, width, direction in rows:
            add(prefix + suffix, width, direction)

    # Four outer (memory-facing) TileLink ports. / 四个外侧（面向内存）的 TileLink 端口。
    for bank in reversed(range(cfg.banks)):
        prefix = f"auto_out_{bank}_"
        rows = (
            ("a_ready", 1, "input"), ("a_valid", 1, "output"),
            ("a_bits_opcode", 4, "output"), ("a_bits_param", 3, "output"),
            ("a_bits_size", 3, "output"), ("a_bits_source", cfg.outer_source_bits, "output"),
            ("a_bits_address", cfg.address_bits, "output"), ("a_bits_user_reqSource", cfg.req_source_bits, "output"),
            ("a_bits_echo_blockisdirty", 1, "output"), ("a_bits_mask", cfg.data_bits // 8, "output"),
            ("a_bits_data", cfg.data_bits, "output"), ("a_bits_corrupt", 1, "output"),
            ("b_ready", 1, "output"), ("b_valid", 1, "input"), ("b_bits_opcode", 3, "input"),
            ("b_bits_param", 2, "input"), ("b_bits_size", 3, "input"), ("b_bits_source", cfg.outer_source_bits, "input"),
            ("b_bits_address", cfg.address_bits, "input"), ("b_bits_mask", cfg.data_bits // 8, "input"),
            ("b_bits_data", cfg.data_bits, "input"), ("b_bits_corrupt", 1, "input"),
            ("c_ready", 1, "input"), ("c_valid", 1, "output"), ("c_bits_opcode", 3, "output"),
            ("c_bits_param", 3, "output"), ("c_bits_size", 3, "output"), ("c_bits_source", cfg.outer_source_bits, "output"),
            ("c_bits_address", cfg.address_bits, "output"), ("c_bits_user_reqSource", cfg.req_source_bits, "output"),
            ("c_bits_echo_blockisdirty", 1, "output"), ("c_bits_data", cfg.data_bits, "output"),
            ("c_bits_corrupt", 1, "output"), ("d_ready", 1, "output"), ("d_valid", 1, "input"),
            ("d_bits_opcode", 4, "input"), ("d_bits_param", 2, "input"), ("d_bits_size", 3, "input"),
            ("d_bits_source", cfg.outer_source_bits, "input"), ("d_bits_sink", cfg.outer_sink_bits, "input"),
            ("d_bits_denied", 1, "input"), ("d_bits_echo_blockisdirty", 1, "input"),
            ("d_bits_data", cfg.data_bits, "input"), ("d_bits_corrupt", 1, "input"),
            ("e_ready", 1, "input"), ("e_valid", 1, "output"), ("e_bits_sink", cfg.outer_sink_bits, "output"),
        )
        for suffix, width, direction in rows:
            add(prefix + suffix, width, direction)

    for name, width in (("auto_pf_recv_in_addr", 64), ("auto_pf_recv_in_pf_source", 5), ("auto_pf_recv_in_addr_valid", 1)):
        add(name, width, "input")
    for name, width, direction in (
        ("io_hartId", 6, "input"), ("io_pfCtrlFromCore_l2_pf_master_en", 1, "input"),
        ("io_pfCtrlFromCore_l2_pf_recv_en", 1, "input"), ("io_pfCtrlFromCore_l2_pbop_en", 1, "input"),
        ("io_pfCtrlFromCore_l2_vbop_en", 1, "input"), ("io_pfCtrlFromCore_l2_tp_en", 1, "input"),
        ("io_pfCtrlFromCore_l2_pf_delay_latency", 10, "input"), ("io_l2_hint_valid", 1, "output"),
        ("io_l2_hint_bits_sourceId", 32, "output"), ("io_l2_hint_bits_isKeyword", 1, "output"),
        ("io_l2_tlb_req_req_valid", 1, "output"), ("io_l2_tlb_req_req_bits_vaddr", 50, "output"),
        ("io_l2_tlb_req_req_bits_cmd", 3, "output"), ("io_l2_tlb_req_req_bits_isPrefetch", 1, "output"),
        ("io_l2_tlb_req_req_bits_kill", 1, "output"), ("io_l2_tlb_req_req_bits_no_translate", 1, "output"),
        ("io_l2_tlb_req_resp_valid", 1, "input"), ("io_l2_tlb_req_resp_bits_paddr_0", 48, "input"),
        ("io_l2_tlb_req_resp_bits_pbmt", 2, "input"), ("io_l2_tlb_req_resp_bits_miss", 1, "input"),
        ("io_l2_tlb_req_resp_bits_excp_0_gpf_ld", 1, "input"), ("io_l2_tlb_req_resp_bits_excp_0_pf_ld", 1, "input"),
        ("io_l2_tlb_req_resp_bits_excp_0_af_ld", 1, "input"), ("io_l2_tlb_req_pmp_resp_ld", 1, "input"),
        ("io_l2_tlb_req_pmp_resp_mmio", 1, "input"), ("io_l2Miss", 1, "output"),
        ("io_error_valid", 1, "output"), ("io_error_address", 46, "output"),
        ("io_dft_ram_hold", 1, "input"), ("io_dft_ram_bypass", 1, "input"),
        ("io_dft_ram_bp_clken", 1, "input"), ("io_dft_ram_aux_clk", 1, "input"),
        ("io_dft_ram_aux_ckbp", 1, "input"), ("io_dft_ram_mcp_hold", 1, "input"),
        ("io_dft_cgen", 1, "input"),
    ):
        add(name, width, direction)
    for index in range(1, cfg.perf_count + 1):
            add(f"io_perf_{index}", 6, "output")
    return tuple(entries)


class TL2TLCoupledL2Parent(Elaboratable):
    # Resolve runtime-created Amaranth ports for static typing. / 为静态类型解析运行时创建的 Amaranth 端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Bounded four-bank TL2TL parent with exact V2 ports. / 具有精确 V2 端口的有界四 bank TL2TL 父级。"""

    # Construct all source-shaped parent signals in generated order. / 按生成顺序构造全部源形状父级信号。
    def __init__(self, configuration: TL2TLCoupledL2ParentConfig | None = None,
                 injected_dependencies: dict[str, Any] | None = None) -> None:
        self.configuration = configuration or TL2TLCoupledL2ParentConfig()
        dependencies = injected_dependencies if isinstance(injected_dependencies, dict) else {}
        supplied_slices = dependencies.get("slices", dependencies.get("slice_children", ()))
        if supplied_slices is None:
            supplied_slices = ()
        if not isinstance(supplied_slices, (tuple, list)):
            supplied_slices = (supplied_slices,)
        self.child_slices = tuple(supplied_slices)
        self.child_dependencies = dict(dependencies)
        self._ports: list[Signal] = []
        self._inputs: list[Signal] = []
        self._outputs: list[Signal] = []
        self._by_name: dict[str, Signal] = {}
        for spec in tl2tl_parent_port_contract(self.configuration):
            signal = Signal(spec["width"], name=spec["name"])
            setattr(self, spec["name"], signal)
            self._ports.append(signal)
            self._by_name[spec["name"]] = signal
            (self._inputs if spec["direction"] == "input" else self._outputs).append(signal)

    # Return the exact ordered parent ports for deterministic conversion. / 返回用于确定性转换的精确有序父级端口。
    def public_ports(self) -> tuple[Signal, ...]:
        """Return the source-shaped port tuple. / 返回源形状端口元组。"""

        return tuple(self._ports)

    # Elaborate a bounded TL2TL transaction relay and metadata bridge. / 展开有界 TL2TL 事务中继和元数据桥。
    def elaborate(self, platform: Any) -> Module:
        """Build reset, A/B/C/D/E, prefetch, and TLB boundary behavior. / 构造复位、A/B/C/D/E、预取和 TLB 边界行为。"""

        del platform
        c = self.configuration
        m = Module()
        domain = ClockDomain("tl2tl_parent", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.tl2tl_parent = domain

        # Per-bank relay state: idle -> outer A -> outer D -> inner D. / 每 bank 中继状态：空闲→外侧 A→外侧 D→内侧 D。
        state = [Signal(2, reset=0, name=f"tl2tl_bank_{bank}_state") for bank in range(c.banks)]
        req_opcode = [Signal(4, name=f"tl2tl_bank_{bank}_opcode") for bank in range(c.banks)]
        req_param = [Signal(3, name=f"tl2tl_bank_{bank}_param") for bank in range(c.banks)]
        req_size = [Signal(3, name=f"tl2tl_bank_{bank}_size") for bank in range(c.banks)]
        req_source = [Signal(c.inner_source_bits, name=f"tl2tl_bank_{bank}_source") for bank in range(c.banks)]
        req_address = [Signal(c.address_bits, name=f"tl2tl_bank_{bank}_address") for bank in range(c.banks)]
        req_req_source = [Signal(c.req_source_bits, name=f"tl2tl_bank_{bank}_req_source") for bank in range(c.banks)]
        req_data = [Signal(c.data_bits, name=f"tl2tl_bank_{bank}_data") for bank in range(c.banks)]
        req_mask = [Signal(c.data_bits // 8, name=f"tl2tl_bank_{bank}_mask") for bank in range(c.banks)]
        req_keyword = [Signal(name=f"tl2tl_bank_{bank}_keyword") for bank in range(c.banks)]
        resp_opcode = [Signal(4, name=f"tl2tl_bank_{bank}_resp_opcode") for bank in range(c.banks)]
        resp_param = [Signal(2, name=f"tl2tl_bank_{bank}_resp_param") for bank in range(c.banks)]
        resp_size = [Signal(3, name=f"tl2tl_bank_{bank}_resp_size") for bank in range(c.banks)]
        resp_source = [Signal(c.inner_source_bits, name=f"tl2tl_bank_{bank}_resp_source") for bank in range(c.banks)]
        resp_sink = [Signal(c.inner_sink_bits, name=f"tl2tl_bank_{bank}_resp_sink") for bank in range(c.banks)]
        resp_data = [Signal(c.data_bits, name=f"tl2tl_bank_{bank}_resp_data") for bank in range(c.banks)]
        resp_denied = [Signal(name=f"tl2tl_bank_{bank}_resp_denied") for bank in range(c.banks)]
        resp_corrupt = [Signal(name=f"tl2tl_bank_{bank}_resp_corrupt") for bank in range(c.banks)]
        # C-channel release relay state and payload. / C 通道 release 中继状态及载荷。
        c_pending = [Signal(name=f"tl2tl_bank_{bank}_c_pending") for bank in range(c.banks)]
        c_opcode = [Signal(3, name=f"tl2tl_bank_{bank}_c_opcode") for bank in range(c.banks)]
        c_param = [Signal(3, name=f"tl2tl_bank_{bank}_c_param") for bank in range(c.banks)]
        c_size = [Signal(3, name=f"tl2tl_bank_{bank}_c_size") for bank in range(c.banks)]
        c_source = [Signal(c.inner_source_bits, name=f"tl2tl_bank_{bank}_c_source") for bank in range(c.banks)]
        c_address = [Signal(c.address_bits, name=f"tl2tl_bank_{bank}_c_address") for bank in range(c.banks)]
        c_data = [Signal(c.data_bits, name=f"tl2tl_bank_{bank}_c_data") for bank in range(c.banks)]
        c_corrupt = [Signal(name=f"tl2tl_bank_{bank}_c_corrupt") for bank in range(c.banks)]
        b_pending = [Signal(name=f"tl2tl_bank_{bank}_b_pending") for bank in range(c.banks)]
        b_opcode = [Signal(3, name=f"tl2tl_bank_{bank}_b_opcode") for bank in range(c.banks)]
        b_param = [Signal(2, name=f"tl2tl_bank_{bank}_b_param") for bank in range(c.banks)]
        b_size = [Signal(3, name=f"tl2tl_bank_{bank}_b_size") for bank in range(c.banks)]
        b_source = [Signal(c.outer_source_bits, name=f"tl2tl_bank_{bank}_b_source") for bank in range(c.banks)]
        b_address = [Signal(c.address_bits, name=f"tl2tl_bank_{bank}_b_address") for bank in range(c.banks)]
        b_mask = [Signal(c.data_bits // 8, name=f"tl2tl_bank_{bank}_b_mask") for bank in range(c.banks)]
        b_data = [Signal(c.data_bits, name=f"tl2tl_bank_{bank}_b_data") for bank in range(c.banks)]
        b_corrupt = [Signal(name=f"tl2tl_bank_{bank}_b_corrupt") for bank in range(c.banks)]

        # Drive every output to a defined reset-safe value before overrides. / 先将所有输出驱动到确定的复位安全值。
        for signal in self._outputs:
            m.d.comb += signal.eq(0)
        for index, signal in enumerate(self._inputs):
            sink = Signal(len(signal), name=f"tl2tl_input_sink_{index}")
            m.d.comb += sink.eq(signal)

        # Temporal metadata is a one-entry ready/valid relay. / Temporal 元数据采用单项 ready/valid 中继。
        tp_pending = Signal(name="tl2tl_tp_pending")
        tp_hartid = Signal(6, name="tl2tl_tp_hartid")
        tp_raw = [Signal(42, name=f"tl2tl_tp_raw_{index}") for index in range(12)]
        child_miss_terms: list[Any] = []
        child_hint_terms: list[Any] = []
        child_error_terms: list[Any] = []
        tp_in_fire = self.auto_tpmeta_sink_in_valid & ~tp_pending
        tp_out_valid = tp_pending
        m.d.comb += [
            self.auto_tpmeta_source_out_valid.eq(tp_out_valid),
            self.auto_tpmeta_source_out_bits_hartid.eq(tp_hartid),
        ]
        # Assign all raw-data lanes explicitly (the compact loop above keeps
        # the generated names stable without relying on dynamic attributes).
        for index, signal in enumerate(tp_raw):
            m.d.comb += getattr(self, f"auto_tpmeta_source_out_bits_rawData_{index}").eq(signal)
        with amaranth_if(m, self.reset):
            m.d.tl2tl_parent += [tp_pending.eq(0), tp_hartid.eq(0)]
            for signal in tp_raw:
                m.d.tl2tl_parent += signal.eq(0)
        with amaranth_else(m):
            with amaranth_if(m, tp_in_fire):
                m.d.tl2tl_parent += [tp_pending.eq(1), tp_hartid.eq(self.auto_tpmeta_sink_in_bits_hartid)]
                for index, signal in enumerate(tp_raw):
                    m.d.tl2tl_parent += signal.eq(getattr(self, f"auto_tpmeta_sink_in_bits_rawData_{index}"))
            with amaranth_elif(m, tp_pending & self.auto_tpmeta_source_out_ready):
                m.d.tl2tl_parent += tp_pending.eq(0)

        # Per-bank ready/valid relay. / 每 bank ready/valid 中继。
        for bank in range(c.banks):
            inner = f"auto_in_{bank}_"
            outer = f"auto_out_{bank}_"
            child = self.child_slices[bank] if bank < len(self.child_slices) else None
            if child is not None:
                # A supplied slice is an explicit dependency injection.  The
                # parent owns the bank-qualified outer address, while the
                # child keeps the slice-local address and cache state.
                # 注入的 slice 是显式依赖；父级负责 bank 地址限定，child
                # 保留 slice-local 地址和缓存状态。
                m.submodules[f"tl2tl_slice_{bank}"] = child
                child_clock = getattr(child, "clock", None)
                child_reset = getattr(child, "reset", None)
                child_flush = getattr(child, "flush", None)
                child_slice_id = getattr(child, "slice_id", None)
                if child_clock is not None:
                    m.d.comb += child_clock.eq(self.clock)
                if child_reset is not None:
                    m.d.comb += child_reset.eq(self.reset)
                if child_flush is not None:
                    m.d.comb += child_flush.eq(0)
                if child_slice_id is not None:
                    m.d.comb += child_slice_id.eq(bank)

                # Direction is fixed by the TileLink channel role. /
                # 方向由 TileLink 通道角色固定决定。
                channel_inputs = {
                    "in_a": ("valid", "bits_opcode", "bits_param", "bits_size", "bits_source", "bits_address",
                              "bits_user_reqSource", "bits_user_alias", "bits_user_vaddr", "bits_user_needHint",
                              "bits_echo_isKeyword", "bits_mask", "bits_data", "bits_corrupt"),
                    "in_b": ("ready",),
                    "in_c": ("valid", "bits_opcode", "bits_param", "bits_size", "bits_source", "bits_address",
                              "bits_user_reqSource", "bits_user_alias", "bits_user_vaddr", "bits_user_needHint",
                              "bits_echo_isKeyword", "bits_data", "bits_corrupt"),
                    "in_d": ("ready",),
                    "in_e": ("valid", "bits_sink"),
                    "out_a": ("ready",),
                    "out_b": ("valid", "bits_opcode", "bits_param", "bits_size", "bits_source", "bits_address",
                               "bits_mask", "bits_data", "bits_corrupt"),
                    "out_c": ("ready",),
                    "out_d": ("valid", "bits_opcode", "bits_param", "bits_size", "bits_source", "bits_sink",
                               "bits_denied", "bits_echo_blockisdirty", "bits_data", "bits_corrupt"),
                    "out_e": ("ready",),
                }
                for channel, fields in channel_inputs.items():
                    parent_prefix = (inner if channel.startswith("in_") else outer) + (channel[3:] if channel.startswith("in_") else channel[4:]) + "_"
                    child_prefix = channel + "_"
                    for field_name in fields:
                        parent_signal = getattr(self, parent_prefix + field_name)
                        child_signal = getattr(child, child_prefix + field_name)
                        m.d.comb += child_signal.eq(parent_signal)
                    # Every field not listed above is an output of the child
                    # and is copied back to the source-shaped parent port.
                    output_fields = {
                        "in_a": ("ready",),
                        "in_b": ("valid", "bits_opcode", "bits_param", "bits_size", "bits_source", "bits_address", "bits_mask", "bits_data", "bits_corrupt"),
                        "in_c": ("ready",),
                        "in_d": ("valid", "bits_opcode", "bits_param", "bits_size", "bits_source", "bits_sink", "bits_denied", "bits_echo_isKeyword", "bits_data", "bits_corrupt"),
                        "in_e": ("ready",),
                        "out_a": ("valid", "bits_opcode", "bits_param", "bits_size", "bits_source", "bits_address", "bits_user_reqSource", "bits_echo_blockisdirty", "bits_mask", "bits_data", "bits_corrupt"),
                        "out_b": ("ready",),
                        "out_c": ("valid", "bits_opcode", "bits_param", "bits_size", "bits_source", "bits_address", "bits_user_reqSource", "bits_echo_blockisdirty", "bits_data", "bits_corrupt"),
                        "out_d": ("ready",),
                        "out_e": ("valid", "bits_sink"),
                    }[channel]
                    for field_name in output_fields:
                        parent_signal = getattr(self, parent_prefix + field_name)
                        child_signal = getattr(child, child_prefix + field_name)
                        if field_name == "bits_address" and channel in {"out_a", "out_c"} and c.bank_bits:
                            # Restore bank bits between local slice and parent.
                            # 在 slice-local 地址与父级之间恢复 bank 位。
                            local_address = child_signal
                            high = local_address[c.offset_bits:]
                            low = local_address[:c.offset_bits]
                            parent_value = (high << (c.bank_bits + c.offset_bits)) | (bank << c.offset_bits) | low
                            m.d.comb += parent_signal.eq(parent_value)
                        else:
                            m.d.comb += parent_signal.eq(child_signal)
                for name in ("prefetch_req_valid", "prefetch_resp_ready", "l1Hint_ready"):
                    if hasattr(child, name):
                        m.d.comb += getattr(child, name).eq(0 if name == "prefetch_req_valid" else 1)
                if hasattr(child, "l2Miss"):
                    child_miss_terms.append(child.l2Miss)
                if hasattr(child, "l1Hint_valid"):
                    child_hint_terms.append(child.l1Hint_valid)
                if hasattr(child, "error_valid"):
                    child_error_terms.append(child.error_valid)
                continue
            # Use one-bit Boolean equations instead of logical operators on
            # the two-bit state register; this keeps generated RTL width-clean.
            # 使用单比特布尔方程而不是对两位状态寄存器做逻辑运算，确保生成 RTL 位宽干净。
            idle = ~(amaranth_value(state[bank][0]) | amaranth_value(state[bank][1]))
            outer_a = amaranth_value(state[bank][0]) & ~amaranth_value(state[bank][1])
            outer_d = ~amaranth_value(state[bank][0]) & amaranth_value(state[bank][1])
            inner_d = amaranth_value(state[bank][0]) & amaranth_value(state[bank][1])
            inner_a_fire = getattr(self, inner + "a_valid") & getattr(self, inner + "a_ready")
            inner_c_fire = getattr(self, inner + "c_valid") & getattr(self, inner + "c_ready")
            outer_a_fire = getattr(self, outer + "a_valid") & getattr(self, outer + "a_ready")
            outer_d_fire = getattr(self, outer + "d_valid") & getattr(self, outer + "d_ready")
            inner_d_fire = getattr(self, inner + "d_valid") & getattr(self, inner + "d_ready")
            # Inner A accepts only while this bank is idle and no release is pending. /
            # 仅当 bank 空闲且没有 release 等待时接受内侧 A。
            m.d.comb += [
                getattr(self, inner + "a_ready").eq(idle & ~c_pending[bank]),
                getattr(self, inner + "c_ready").eq(idle & ~c_pending[bank]),
                getattr(self, inner + "e_ready").eq(1),
                getattr(self, outer + "a_valid").eq(outer_a),
                getattr(self, outer + "a_bits_opcode").eq(req_opcode[bank]),
                getattr(self, outer + "a_bits_param").eq(req_param[bank]),
                getattr(self, outer + "a_bits_size").eq(req_size[bank]),
                getattr(self, outer + "a_bits_source").eq(req_source[bank]),
                getattr(self, outer + "a_bits_address").eq(req_address[bank]),
                getattr(self, outer + "a_bits_user_reqSource").eq(req_req_source[bank]),
                getattr(self, outer + "a_bits_echo_blockisdirty").eq(0),
                getattr(self, outer + "a_bits_mask").eq(req_mask[bank]),
                getattr(self, outer + "a_bits_data").eq(req_data[bank]),
                getattr(self, outer + "a_bits_corrupt").eq(0),
                getattr(self, outer + "d_ready").eq(outer_d),
                getattr(self, inner + "d_valid").eq(inner_d),
                getattr(self, inner + "d_bits_opcode").eq(resp_opcode[bank]),
                getattr(self, inner + "d_bits_param").eq(resp_param[bank]),
                getattr(self, inner + "d_bits_size").eq(resp_size[bank]),
                getattr(self, inner + "d_bits_source").eq(resp_source[bank]),
                getattr(self, inner + "d_bits_sink").eq(resp_sink[bank]),
                getattr(self, inner + "d_bits_denied").eq(resp_denied[bank]),
                getattr(self, inner + "d_bits_echo_isKeyword").eq(req_keyword[bank]),
                getattr(self, inner + "d_bits_data").eq(resp_data[bank]),
                getattr(self, inner + "d_bits_corrupt").eq(resp_corrupt[bank]),
                getattr(self, outer + "c_valid").eq(c_pending[bank]),
                getattr(self, outer + "c_bits_opcode").eq(c_opcode[bank]),
                getattr(self, outer + "c_bits_param").eq(c_param[bank]),
                getattr(self, outer + "c_bits_size").eq(c_size[bank]),
                getattr(self, outer + "c_bits_source").eq(c_source[bank]),
                getattr(self, outer + "c_bits_address").eq(c_address[bank]),
                getattr(self, outer + "c_bits_user_reqSource").eq(0),
                getattr(self, outer + "c_bits_echo_blockisdirty").eq(0),
                getattr(self, outer + "c_bits_data").eq(c_data[bank]),
                getattr(self, outer + "c_bits_corrupt").eq(c_corrupt[bank]),
                getattr(self, outer + "b_ready").eq(~b_pending[bank]),
                getattr(self, inner + "b_valid").eq(b_pending[bank]),
                getattr(self, inner + "b_bits_opcode").eq(b_opcode[bank]),
                getattr(self, inner + "b_bits_param").eq(b_param[bank]),
                getattr(self, inner + "b_bits_size").eq(b_size[bank]),
                getattr(self, inner + "b_bits_source").eq(b_source[bank][:c.inner_source_bits]),
                getattr(self, inner + "b_bits_address").eq(b_address[bank]),
                getattr(self, inner + "b_bits_mask").eq(b_mask[bank]),
                getattr(self, inner + "b_bits_data").eq(b_data[bank]),
                getattr(self, inner + "b_bits_corrupt").eq(b_corrupt[bank]),
                getattr(self, outer + "e_valid").eq(getattr(self, inner + "e_valid")),
                getattr(self, outer + "e_bits_sink").eq(getattr(self, inner + "e_bits_sink")[:c.outer_sink_bits]),
            ]
            with amaranth_if(m, self.reset):
                m.d.tl2tl_parent += [state[bank].eq(0), c_pending[bank].eq(0), b_pending[bank].eq(0)]
            with amaranth_else(m):
                with amaranth_if(m, inner_a_fire):
                    m.d.tl2tl_parent += [state[bank].eq(1), req_opcode[bank].eq(getattr(self, inner + "a_bits_opcode")),
                                         req_param[bank].eq(getattr(self, inner + "a_bits_param")), req_size[bank].eq(getattr(self, inner + "a_bits_size")),
                                         req_source[bank].eq(getattr(self, inner + "a_bits_source")), req_address[bank].eq(getattr(self, inner + "a_bits_address")),
                                         req_req_source[bank].eq(getattr(self, inner + "a_bits_user_reqSource")), req_data[bank].eq(getattr(self, inner + "a_bits_data")),
                                         req_mask[bank].eq(getattr(self, inner + "a_bits_mask")), req_keyword[bank].eq(getattr(self, inner + "a_bits_echo_isKeyword"))]
                with amaranth_elif(m, outer_a_fire):
                    m.d.tl2tl_parent += state[bank].eq(2)
                with amaranth_elif(m, outer_d_fire):
                    m.d.tl2tl_parent += [state[bank].eq(3), resp_opcode[bank].eq(getattr(self, outer + "d_bits_opcode")),
                                         resp_param[bank].eq(getattr(self, outer + "d_bits_param")), resp_size[bank].eq(getattr(self, outer + "d_bits_size")),
                                         resp_source[bank].eq(getattr(self, outer + "d_bits_source")[:c.inner_source_bits]), resp_sink[bank].eq(getattr(self, outer + "d_bits_sink")[:c.inner_sink_bits]),
                                         resp_data[bank].eq(getattr(self, outer + "d_bits_data")), resp_denied[bank].eq(getattr(self, outer + "d_bits_denied")),
                                         resp_corrupt[bank].eq(getattr(self, outer + "d_bits_corrupt"))]
                with amaranth_elif(m, inner_d_fire):
                    m.d.tl2tl_parent += state[bank].eq(0)
                with amaranth_if(m, inner_c_fire):
                    m.d.tl2tl_parent += [c_pending[bank].eq(1), c_opcode[bank].eq(getattr(self, inner + "c_bits_opcode")),
                                         c_param[bank].eq(getattr(self, inner + "c_bits_param")), c_size[bank].eq(getattr(self, inner + "c_bits_size")),
                                         c_source[bank].eq(getattr(self, inner + "c_bits_source")), c_address[bank].eq(getattr(self, inner + "c_bits_address")),
                                         c_data[bank].eq(getattr(self, inner + "c_bits_data")), c_corrupt[bank].eq(getattr(self, inner + "c_bits_corrupt"))]
                with amaranth_if(m, c_pending[bank] & getattr(self, outer + "c_ready")):
                    m.d.tl2tl_parent += [c_pending[bank].eq(0), state[bank].eq(0)]
                with amaranth_if(m, getattr(self, outer + "b_valid") & getattr(self, outer + "b_ready")):
                    m.d.tl2tl_parent += [b_pending[bank].eq(1), b_opcode[bank].eq(getattr(self, outer + "b_bits_opcode")),
                                         b_param[bank].eq(getattr(self, outer + "b_bits_param")), b_size[bank].eq(getattr(self, outer + "b_bits_size")),
                                         b_source[bank].eq(getattr(self, outer + "b_bits_source")), b_address[bank].eq(getattr(self, outer + "b_bits_address")),
                                         b_mask[bank].eq(getattr(self, outer + "b_bits_mask")), b_data[bank].eq(getattr(self, outer + "b_bits_data")),
                                         b_corrupt[bank].eq(getattr(self, outer + "b_bits_corrupt"))]
                with amaranth_if(m, b_pending[bank] & getattr(self, inner + "b_ready")):
                    m.d.tl2tl_parent += b_pending[bank].eq(0)

        # Prefetch/TLB/error/performance outputs are explicit quiescent values. /
        # 预取/TLB/错误/性能输出保持显式静默值。
        child_miss = child_miss_terms[0] if child_miss_terms else 0
        child_hint = child_hint_terms[0] if child_hint_terms else 0
        child_error = child_error_terms[0] if child_error_terms else 0
        for term in child_miss_terms[1:]:
            child_miss = child_miss | term
        for term in child_hint_terms[1:]:
            child_hint = child_hint | term
        for term in child_error_terms[1:]:
            child_error = child_error | term
        m.d.comb += [
            self.io_l2_hint_valid.eq(child_hint | (self.auto_pf_recv_in_addr_valid & self.io_pfCtrlFromCore_l2_pf_master_en)),
            self.io_l2_hint_bits_sourceId.eq(self.auto_pf_recv_in_pf_source),
            self.io_l2_hint_bits_isKeyword.eq(0), self.io_l2_tlb_req_req_valid.eq(0),
            self.io_l2_tlb_req_req_bits_vaddr.eq(0), self.io_l2_tlb_req_req_bits_cmd.eq(0),
            self.io_l2_tlb_req_req_bits_isPrefetch.eq(0), self.io_l2_tlb_req_req_bits_kill.eq(0),
            self.io_l2_tlb_req_req_bits_no_translate.eq(0), self.io_l2Miss.eq(child_miss), self.io_error_valid.eq(child_error),
            self.io_error_address.eq(0),
        ]
        return m


# =============================================================================
# Public Adapter
# =============================================================================
# Convert the aggregate directory to deterministic SystemVerilog. / 将聚合目录转换为确定性 SystemVerilog。
def build_verilog(configuration, injected_dependencies):
    """Return Verilog for the CoupledL2 Directory family. / 返回 CoupledL2 Directory family Verilog。"""

    del injected_dependencies
    if isinstance(configuration, CoupledL2DirectoryConfig):
        cfg, name = configuration, "UHSCCoupledL2Directory"
    elif isinstance(configuration, dict):
        fields = CoupledL2DirectoryConfig.__dataclass_fields__
        values = {key: value for key, value in configuration.items() if key in fields}
        cfg = CoupledL2DirectoryConfig(**values)
        name = str(configuration.get("module", configuration.get("name", "UHSCCoupledL2Directory")))
    elif configuration is None:
        cfg, name = CoupledL2DirectoryConfig(), "UHSCCoupledL2Directory"
    else:
        raise TypeError("configuration must be CoupledL2DirectoryConfig, dict, or None")
    top = CoupledL2Directory(cfg)
    ports = [
        top.clock, top.reset, top.read_valid, top.read_ready, top.read_tag, top.read_set,
        top.read_way_mask, top.read_replacer_channel, top.read_replacer_opcode,
        top.read_replacer_req_source, top.read_replacer_refill_prefetch, top.read_refill,
        top.read_mshr_id, top.read_cmo_all, top.read_cmo_way, top.resp_valid, top.resp_hit,
        top.resp_tag, top.resp_set, top.resp_way, top.resp_meta_dirty, top.resp_meta_state,
        top.resp_meta_clients, top.resp_meta_alias, top.resp_meta_prefetch,
        top.resp_meta_prefetch_src, top.resp_meta_accessed, top.resp_meta_tag_err,
        top.resp_meta_data_err, top.resp_error, top.resp_replacer_channel,
        top.resp_replacer_opcode, top.resp_replacer_req_source, top.resp_replacer_refill_prefetch,
        top.meta_write_valid, top.meta_write_set, top.meta_write_way_oh, top.meta_write_dirty,
        top.meta_write_state, top.meta_write_clients, top.meta_write_alias,
        top.meta_write_prefetch, top.meta_write_prefetch_src, top.meta_write_accessed,
        top.meta_write_tag_err, top.meta_write_data_err, top.tag_write_valid,
        top.tag_write_set, top.tag_write_way, top.tag_write_tag, top.repl_resp_valid,
        top.repl_resp_tag, top.repl_resp_set, top.repl_resp_way, top.repl_resp_meta_dirty,
        top.repl_resp_meta_state, top.repl_resp_meta_clients, top.repl_resp_meta_alias,
        top.repl_resp_meta_prefetch, top.repl_resp_meta_prefetch_src, top.repl_resp_meta_accessed,
        top.repl_resp_meta_tag_err, top.repl_resp_meta_data_err, top.repl_resp_mshr_id,
        top.repl_resp_retry, top.repl_resp_error, top.mshr_valid, top.mshr_set, top.mshr_way,
        top.mshr_block_refill, top.mshr_dir_hit, top.mshr_will_free,
    ]
    return verilog.convert(top, name=name, ports=ports, emit_src=False)


# Export the selected-top TL2TL parent with its exact frozen port envelope. /
# 导出带有精确冻结端口包络的选定顶层 TL2TL 父级。/
def build_parent_verilog(configuration, injected_dependencies):
    """Return deterministic TL2TLCoupledL2 parent Verilog. / 返回确定性的 TL2TLCoupledL2 父级 Verilog。"""

    dependencies = injected_dependencies if isinstance(injected_dependencies, dict) else {}
    if isinstance(configuration, TL2TLCoupledL2ParentConfig):
        cfg, name = configuration, "UHSCTL2TLCoupledL2"
    elif isinstance(configuration, dict):
        fields = TL2TLCoupledL2ParentConfig.__dataclass_fields__
        cfg = TL2TLCoupledL2ParentConfig(**{key: value for key, value in configuration.items() if key in fields})
        name = str(configuration.get("module", configuration.get("name", "UHSCTL2TLCoupledL2")))
    elif configuration is None:
        cfg, name = TL2TLCoupledL2ParentConfig(), "UHSCTL2TLCoupledL2"
    else:
        raise TypeError("configuration must be TL2TLCoupledL2ParentConfig, dict, or None")
    top = TL2TLCoupledL2Parent(cfg, dependencies)
    return verilog.convert(top, name=name, ports=list(top.public_ports()), emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print deterministic direct export for manual generation. / 打印确定性的 direct 导出以便手工生成。
def main() -> None:
    """Print the default directory RTL. / 打印默认目录 RTL。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
