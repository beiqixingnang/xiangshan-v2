"""UHSC Kunminghu V2 CoupledL2 common slice family boundary.
昆明湖 V2 CoupledL2 公共 slice family 边界。

This aggregate is the executable boundary for the common CoupledL2 slice
closure.  It keeps the TileLink A--E channels, the cache-line metadata/data
path, one bounded MSHR transaction, and the prefetch/error observations in a
single parameterised Amaranth module.  The source closure contains both the
TileLink and CHI implementations; the CHI-specific link state is intentionally
left to the separate bridge family.  The implementation is therefore a
traceable bounded slice model, not a claim that every nested Scala helper is a
separate Python module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amaranth import Array, Cat, ClockDomain, Const, Elaboratable, Memory, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# The boundary preserves TileLink A--E ready/valid ordering, line metadata,
# refill/eviction handshakes, and the selected V2 observability points.
# 本边界保持 TileLink A--E ready/valid 顺序、缓存行元数据、回填/逐出握手及 V2 观测点。
__all__ = [
    "CoupledL2SliceConfig",
    "CoupledL2Slice",
    "CoupledL2SliceBoundary",
    "TL2TLCoupledL2Slice",
    "Slice",
    "parse_address",
    "restore_address",
    "restore_address_expr",
    "slice_reference_step",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class CoupledL2SliceConfig:
    """Finite V2 slice geometry and protocol widths. / 有限 V2 slice 几何及协议位宽。"""

    sets: int = 512
    ways: int = 8
    address_bits: int = 48
    offset_bits: int = 6
    bank_bits: int = 2
    data_bits: int = 256
    line_beats: int = 2
    source_bits: int = 7
    sink_bits: int = 8
    req_source_bits: int = 5
    alias_bits: int = 2
    vaddr_bits: int = 44
    mshr_entries: int = 16
    prefetch: bool = True

    # Validate the geometry used by the locked Kunminghu V2 slice. / 校验锁定昆明湖 V2 slice 使用的几何参数。
    def __post_init__(self) -> None:
        if self.sets < 1 or self.sets & (self.sets - 1):
            raise ValueError("sets must be a positive power of two")
        if self.ways < 1 or self.ways > 32:
            raise ValueError("ways must be in [1, 32]")
        if self.address_bits < 16 or self.offset_bits < 1 or self.bank_bits < 0:
            raise ValueError("invalid address geometry")
        if self.offset_bits + self.bank_bits + self.set_bits >= self.address_bits:
            raise ValueError("address fields exceed address width")
        if self.data_bits < 8 or self.data_bits % 8:
            raise ValueError("data_bits must be a positive byte width")
        if self.line_beats < 1 or self.line_beats > 16:
            raise ValueError("line_beats must be in [1, 16]")
        if min(self.source_bits, self.sink_bits, self.req_source_bits, self.vaddr_bits) < 1:
            raise ValueError("protocol widths must be positive")
        if self.mshr_entries < 1 or self.mshr_entries > 64:
            raise ValueError("mshr_entries must be in [1, 64]")

    @property
    # Return the set-index width after the per-bank address bits. / 返回扣除 bank 地址位后的组索引位宽。
    def set_bits(self) -> int:
        return max(1, (self.sets - 1).bit_length())

    @property
    # Return the tag width visible inside one slice. / 返回单个 slice 内可见的标签位宽。
    def tag_bits(self) -> int:
        return self.address_bits - self.offset_bits - self.bank_bits - self.set_bits

    @property
    # Return the complete cache-line payload width. / 返回完整缓存行载荷位宽。
    def line_bits(self) -> int:
        return self.data_bits * self.line_beats

    @property
    # Return the byte mask width for one TileLink beat. / 返回单个 TileLink beat 的字节掩码位宽。
    def mask_bits(self) -> int:
        return self.data_bits // 8

    @property
    # Return the replacement-way index width. / 返回替换路索引位宽。
    def way_bits(self) -> int:
        return max(1, (self.ways - 1).bit_length())

    @property
    # Return the beat-index width in a line. / 返回缓存行内 beat 索引位宽。
    def beat_index_bits(self) -> int:
        return max(1, (self.line_beats - 1).bit_length())

    @property
    # Return the full tag width before bank selection. / 返回 bank 选择前的完整标签位宽。
    def full_tag_bits(self) -> int:
        return self.address_bits - self.offset_bits - self.set_bits

    @property
    # Return the outer TileLink sink width used by the locked V2 edge. / 返回锁定 V2 edge 使用的外部 TileLink sink 位宽。
    def outer_sink_bits(self) -> int:
        return max(1, self.sink_bits - 2)

    @property
    # Return the ECC/error address width exposed by the selected V2 slice. / 返回选定 V2 slice 暴露的 ECC/错误地址位宽。
    def error_address_bits(self) -> int:
        return max(1, self.address_bits - 2)


# Return the V2 slice-local tag, set, and byte offset fields. / 返回 V2 slice 本地标签、组及字节偏移字段。
def parse_address(address: int, configuration: CoupledL2SliceConfig | None = None) -> tuple[int, int, int, int]:
    cfg = configuration or CoupledL2SliceConfig()
    value = int(address) & ((1 << cfg.address_bits) - 1)
    offset_mask = (1 << cfg.offset_bits) - 1
    bank_mask = (1 << cfg.bank_bits) - 1 if cfg.bank_bits else 0
    set_mask = (1 << cfg.set_bits) - 1
    offset = value & offset_mask
    bank = (value >> cfg.offset_bits) & bank_mask if cfg.bank_bits else 0
    index = (value >> (cfg.offset_bits + cfg.bank_bits)) & set_mask
    tag = value >> (cfg.offset_bits + cfg.bank_bits + cfg.set_bits)
    return tag, index, offset, bank


# Restore a full V2 address from slice-local fields. / 从 slice 本地字段恢复完整 V2 地址。
def restore_address(tag: int, index: int, offset: int = 0, bank: int = 0,
                    configuration: CoupledL2SliceConfig | None = None) -> int:
    cfg = configuration or CoupledL2SliceConfig()
    value = ((int(tag) & ((1 << cfg.tag_bits) - 1)) <<
             (cfg.set_bits + cfg.bank_bits + cfg.offset_bits))
    value |= (int(index) & ((1 << cfg.set_bits) - 1)) << (cfg.bank_bits + cfg.offset_bits)
    if cfg.bank_bits:
        value |= (int(bank) & ((1 << cfg.bank_bits) - 1)) << cfg.offset_bits
    value |= int(offset) & ((1 << cfg.offset_bits) - 1)
    return value & ((1 << cfg.address_bits) - 1)


# Build a synthesizable address concatenation for signal-valued fields. / 为信号字段构造可综合的地址拼接表达式。
def restore_address_expr(tag: Any, index: Any, offset: Any, bank: Any,
                         configuration: CoupledL2SliceConfig) -> Any:
    if configuration.bank_bits:
        # Amaranth's Cat places its first operand in the least-significant
        # bits, matching the Scala address layout offset→bank→set→tag.
        # Amaranth 的 Cat 将第一个操作数放在最低位，正好对应 Scala 的
        # offset→bank→set→tag 地址布局。
        return Cat(offset, bank, index, tag)
    return Cat(offset, index, tag)


# Compute the bounded V2 response equation for a single request. / 计算单笔请求的有界 V2 响应方程。
def slice_reference_step(opcode: int, hit: bool, dirty: bool = False,
                         pending: bool = False, refill: bool = False,
                         release: bool = False, configuration: CoupledL2SliceConfig | None = None) -> dict[str, int]:
    del configuration
    # TileLink message encodings from rocket-chip Bundles.scala. /
    # rocket-chip Bundles.scala 中的 TileLink 消息编码。
    put_full, put_partial, arithmetic, logical, get, hint = 0, 1, 2, 3, 4, 5
    acquire_block, acquire_perm = 6, 7
    access_ack, access_ack_data, hint_ack = 0, 1, 2
    grant, grant_data, release_ack = 4, 5, 6
    if release:
        return {"response_opcode": release_ack, "response_data": 0, "miss": 0, "evict": 0}
    if refill:
        response = grant_data if opcode in (acquire_block, acquire_perm) else access_ack_data
        return {"response_opcode": response, "response_data": 1, "miss": 0, "evict": 0}
    if pending:
        return {"response_opcode": 0, "response_data": 0, "miss": 1, "evict": int(bool(dirty))}
    if hit:
        if opcode == hint:
            response = hint_ack
        elif opcode in (acquire_block, acquire_perm):
            response = grant_data
        elif opcode in (put_full, put_partial):
            response = access_ack
        elif opcode in (arithmetic, logical, get):
            response = access_ack_data
        else:
            response = access_ack
        return {"response_opcode": response, "response_data": int(opcode in (arithmetic, logical, get, acquire_block, acquire_perm)), "miss": 0, "evict": 0}
    return {"response_opcode": 0, "response_data": 0, "miss": 1, "evict": int(bool(dirty))}


# =============================================================================
# Implementation
# =============================================================================
class CoupledL2Slice(Elaboratable):
    """Bounded ready/valid CoupledL2 slice with explicit V2 child boundaries. / 带显式 V2 子边界的有界 ready/valid CoupledL2 slice。"""

    # Construct flattened TileLink, metadata, prefetch, and diagnostic ports. / 构造扁平 TileLink、元数据、预取及诊断端口。
    def __init__(self, configuration: CoupledL2SliceConfig | None = None,
                 injected_dependencies: dict[str, Any] | None = None) -> None:
        del injected_dependencies
        self.configuration = configuration or CoupledL2SliceConfig()
        c = self.configuration

        # Create one flattened protocol port with the locked V2 spelling. /
        # 按锁定 V2 拼写创建一个扁平协议端口。
        def port(name: str, width: int = 1) -> Signal:
            return Signal(width, name=f"io_{name}")

        self.clock = port("clock")
        self.reset = port("reset")
        self.flush = port("l2Flush")
        self.slice_id = port("sliceId", max(1, c.bank_bits))

        # Inner TileLink A channel (L1 -> slice). / 内部 TileLink A 通道（L1 到 slice）。
        for name, width in {
            "in_a_valid": 1, "in_a_ready": 1, "in_a_bits_opcode": 4, "in_a_bits_param": 3,
            "in_a_bits_size": 3, "in_a_bits_source": c.source_bits, "in_a_bits_address": c.address_bits,
            "in_a_bits_user_reqSource": c.req_source_bits, "in_a_bits_user_alias": c.alias_bits,
            "in_a_bits_user_vaddr": c.vaddr_bits, "in_a_bits_user_needHint": 1,
            "in_a_bits_echo_isKeyword": 1, "in_a_bits_mask": c.mask_bits, "in_a_bits_data": c.data_bits,
            "in_a_bits_corrupt": 1,
        }.items():
            signal = port(name, width)
            setattr(self, name, signal)
        # Inner B channel (slice -> L1). / 内部 TileLink B 通道（slice 到 L1）。
        for name, width in {
            "in_b_valid": 1, "in_b_ready": 1, "in_b_bits_opcode": 3, "in_b_bits_param": 2,
            "in_b_bits_size": 3, "in_b_bits_source": c.source_bits, "in_b_bits_address": c.address_bits,
            "in_b_bits_mask": c.mask_bits, "in_b_bits_data": c.data_bits, "in_b_bits_corrupt": 1,
        }.items():
            signal = port(name, width)
            setattr(self, name, signal)
        # Inner C channel (L1 -> slice). / 内部 TileLink C 通道（L1 到 slice）。
        for name, width in {
            "in_c_valid": 1, "in_c_ready": 1, "in_c_bits_opcode": 3, "in_c_bits_param": 3,
            "in_c_bits_size": 3, "in_c_bits_source": c.source_bits, "in_c_bits_address": c.address_bits,
            "in_c_bits_user_reqSource": c.req_source_bits, "in_c_bits_user_alias": c.alias_bits,
            "in_c_bits_user_vaddr": c.vaddr_bits, "in_c_bits_user_needHint": 1,
            "in_c_bits_echo_isKeyword": 1, "in_c_bits_data": c.data_bits, "in_c_bits_corrupt": 1,
        }.items():
            signal = port(name, width)
            setattr(self, name, signal)
        # Inner D/E channels. / 内部 TileLink D/E 通道。
        for name, width in {
            "in_d_valid": 1, "in_d_ready": 1, "in_d_bits_opcode": 4, "in_d_bits_param": 2,
            "in_d_bits_size": 3, "in_d_bits_source": c.source_bits, "in_d_bits_sink": c.sink_bits,
            "in_d_bits_denied": 1, "in_d_bits_echo_isKeyword": 1, "in_d_bits_data": c.data_bits,
            "in_d_bits_corrupt": 1, "in_e_valid": 1, "in_e_ready": 1, "in_e_bits_sink": c.sink_bits,
        }.items():
            signal = port(name, width)
            setattr(self, name, signal)

        # Outer TileLink A/B/C/D/E channels. / 外部 TileLink A/B/C/D/E 通道。
        for name, width in {
            "out_a_valid": 1, "out_a_ready": 1, "out_a_bits_opcode": 4, "out_a_bits_param": 3,
            "out_a_bits_size": 3, "out_a_bits_source": c.sink_bits, "out_a_bits_address": c.address_bits,
            "out_a_bits_user_reqSource": c.req_source_bits, "out_a_bits_echo_blockisdirty": 1,
            "out_a_bits_mask": c.mask_bits, "out_a_bits_data": c.data_bits, "out_a_bits_corrupt": 1,
            "out_b_valid": 1, "out_b_ready": 1, "out_b_bits_opcode": 3, "out_b_bits_param": 2,
            "out_b_bits_size": 3, "out_b_bits_source": c.sink_bits, "out_b_bits_address": c.address_bits,
            "out_b_bits_mask": c.mask_bits, "out_b_bits_data": c.data_bits, "out_b_bits_corrupt": 1,
            "out_c_valid": 1, "out_c_ready": 1, "out_c_bits_opcode": 3, "out_c_bits_param": 3,
            "out_c_bits_size": 3, "out_c_bits_source": c.sink_bits, "out_c_bits_address": c.address_bits,
            "out_c_bits_user_reqSource": c.req_source_bits, "out_c_bits_echo_blockisdirty": 1,
            "out_c_bits_data": c.data_bits, "out_c_bits_corrupt": 1,
            "out_d_valid": 1, "out_d_ready": 1, "out_d_bits_opcode": 4, "out_d_bits_param": 2,
            "out_d_bits_size": 3, "out_d_bits_source": c.sink_bits, "out_d_bits_sink": c.outer_sink_bits,
            "out_d_bits_denied": 1, "out_d_bits_echo_blockisdirty": 1, "out_d_bits_data": c.data_bits,
            "out_d_bits_corrupt": 1, "out_e_valid": 1, "out_e_ready": 1, "out_e_bits_sink": c.sink_bits,
        }.items():
            signal = port(name, width)
            setattr(self, name, signal)

        # Prefetch, hint, error, and parent-observable status. / 预取、提示、错误及父级可观测状态。
        for name, width in {
            "l1Hint_valid": 1, "l1Hint_ready": 1, "l1Hint_bits_sourceId": 32, "l1Hint_bits_isKeyword": 1,
            "prefetch_train_valid": 1, "prefetch_train_bits_tag": c.full_tag_bits, "prefetch_train_bits_set": c.set_bits,
            "prefetch_train_bits_needT": 1, "prefetch_train_bits_source": c.source_bits,
            "prefetch_train_bits_vaddr": c.vaddr_bits, "prefetch_train_bits_hit": 1,
            "prefetch_train_bits_prefetched": 1, "prefetch_train_bits_pfsource": 3,
            "prefetch_train_bits_reqsource": c.req_source_bits, "prefetch_req_valid": 1,
            "prefetch_req_ready": 1, "prefetch_req_bits_tag": c.full_tag_bits, "prefetch_req_bits_set": c.set_bits,
            "prefetch_req_bits_vaddr": c.vaddr_bits, "prefetch_req_bits_needT": 1,
            "prefetch_req_bits_source": c.source_bits, "prefetch_req_bits_pfSource": c.req_source_bits,
            "prefetch_resp_valid": 1, "prefetch_resp_ready": 1, "error_valid": 1,
            "error_bits_valid": 1, "error_bits_address": c.error_address_bits, "l2Miss": 1,
            "l2FlushDone": 1,
        }.items():
            signal = port(name, width)
            setattr(self, name, signal)
        self.perf = [port(f"perf_{index}_value", 64) for index in range(17)]

        # Source-oriented aliases make direct tests readable without changing generated names. /
        # 源导向别名使 direct 测试可读，同时不改变生成名称。
        for name in list(self.__dict__):
            if name.startswith("in_") or name.startswith("out_") or name.startswith("prefetch_") or name in {
                "l1Hint_valid", "l1Hint_ready", "l1Hint_bits_sourceId", "l1Hint_bits_isKeyword",
                "error_valid", "error_bits_valid", "error_bits_address", "l2Miss", "l2FlushDone",
            }:
                signal = getattr(self, name)
                setattr(self, f"io_{name}", signal)

    # Elaborate cache metadata, request arbitration, and channel state. / 展开缓存元数据、请求仲裁及通道状态。
    def elaborate(self, platform: Any) -> Module:
        del platform
        c = self.configuration
        m = Module()
        domain = ClockDomain("coupled_l2", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.coupled_l2 = domain

        # Each way uses a compact asynchronous-read memory; valid bits are
        # initialised to zero and writes remain synchronous with the V2 clock.
        # 每一路使用紧凑异步读存储器；有效位初始化为零，写入与 V2 时钟同步。
        valid_mem: list[Memory] = []
        dirty_mem: list[Memory] = []
        tag_mem: list[Memory] = []
        data_mem: list[Memory] = []
        valid_reads: list[Any] = []
        dirty_reads: list[Any] = []
        tag_reads: list[Any] = []
        data_reads: list[Any] = []
        valid_writes: list[Any] = []
        dirty_writes: list[Any] = []
        tag_writes: list[Any] = []
        data_writes: list[Any] = []
        for way in range(c.ways):
            valid = Memory(width=1, depth=c.sets, init=[0] * c.sets, name=f"coupled_valid_{way}")
            dirty = Memory(width=1, depth=c.sets, init=[0] * c.sets, name=f"coupled_dirty_{way}")
            tags = Memory(width=c.tag_bits, depth=c.sets, init=[0] * c.sets, name=f"coupled_tag_{way}")
            data = Memory(width=c.line_bits, depth=c.sets, init=[0] * c.sets, name=f"coupled_data_{way}")
            valid_mem.append(valid); dirty_mem.append(dirty); tag_mem.append(tags); data_mem.append(data)
            vr = valid.read_port(domain="comb"); dr = dirty.read_port(domain="comb")
            tr = tags.read_port(domain="comb"); xr = data.read_port(domain="comb")
            vw = valid.write_port(domain="coupled_l2"); dw = dirty.write_port(domain="coupled_l2")
            tw = tags.write_port(domain="coupled_l2"); xw = data.write_port(domain="coupled_l2")
            m.submodules[f"valid_r_{way}"] = vr; m.submodules[f"dirty_r_{way}"] = dr
            m.submodules[f"tag_r_{way}"] = tr; m.submodules[f"data_r_{way}"] = xr
            m.submodules[f"valid_w_{way}"] = vw; m.submodules[f"dirty_w_{way}"] = dw
            m.submodules[f"tag_w_{way}"] = tw; m.submodules[f"data_w_{way}"] = xw
            valid_reads.append(vr); dirty_reads.append(dr); tag_reads.append(tr); data_reads.append(xr)
            valid_writes.append(vw); dirty_writes.append(dw); tag_writes.append(tw); data_writes.append(xw)
        # Retain non-port debug handles for the independent simulator only. /
        # 仅为独立模拟器保留非端口调试句柄。
        self._debug_valid_reads = valid_reads
        self._debug_tag_reads = tag_reads
        self._debug_state = None

        req_set = self.in_a_bits_address[c.offset_bits + c.bank_bits:c.offset_bits + c.bank_bits + c.set_bits]
        req_tag = self.in_a_bits_address[c.offset_bits + c.bank_bits + c.set_bits:c.address_bits]
        req_bank = self.in_a_bits_address[c.offset_bits:c.offset_bits + c.bank_bits] if c.bank_bits else 0
        for reads in (valid_reads, dirty_reads, tag_reads, data_reads):
            for read in reads:
                m.d.comb += read.addr.eq(req_set)

        hit_vec = [valid_reads[way].data & (tag_reads[way].data == req_tag) for way in range(c.ways)]
        # Keep combinational hit terms available to the validator without
        # exposing extra product ports. / 为验证器保留组合命中项，但不增加产品端口。
        self._debug_hit_vec = hit_vec
        self._debug_req_tag = req_tag
        self._debug_req_set = req_set
        hit_any: Any = 0
        hit_way: Any = 0
        for way in range(c.ways):
            hit_way = Mux(hit_vec[way] & ~hit_any, way, hit_way)
            hit_any = hit_any | hit_vec[way]
        victim_way: Any = 0
        victim_found: Any = 0
        for way in range(c.ways):
            victim_way = Mux(~valid_reads[way].data & ~victim_found, way, victim_way)
            victim_found = victim_found | ~valid_reads[way].data
        repl_way = Signal(c.way_bits, name="replacement_way")
        victim_way = Mux(victim_found, victim_way, repl_way)

        # Main transaction registers. / 主事务寄存器。
        state = Signal(3, name="slice_state")
        self._debug_state = state
        # 0 idle, 1 response, 2 miss request, 3 eviction, 4 refill, 5 probe.
        pending_opcode = Signal(4, name="pending_opcode")
        pending_param = Signal(3, name="pending_param")
        pending_size = Signal(3, name="pending_size")
        pending_source = Signal(c.source_bits, name="pending_source")
        pending_outer_source = Signal(c.sink_bits, name="pending_outer_source")
        pending_address = Signal(c.address_bits, name="pending_address")
        pending_req_source = Signal(c.req_source_bits, name="pending_req_source")
        pending_alias = Signal(c.alias_bits, name="pending_alias")
        pending_vaddr = Signal(c.vaddr_bits, name="pending_vaddr")
        pending_keyword = Signal(name="pending_keyword")
        pending_data = Signal(c.data_bits, name="pending_data")
        pending_mask = Signal(c.mask_bits, name="pending_mask")
        pending_way = Signal(c.way_bits, name="pending_way")
        pending_set = Signal(c.set_bits, name="pending_set")
        pending_tag = Signal(c.tag_bits, name="pending_tag")
        pending_dirty = Signal(name="pending_dirty")
        pending_hit = Signal(name="pending_hit")
        self._debug_pending_tag = pending_tag
        self._debug_pending_set = pending_set
        self._debug_pending_hit = pending_hit
        pending_from_prefetch = Signal(name="pending_from_prefetch")
        refill_data = Signal(c.line_bits, name="refill_line")
        refill_beat = Signal(c.beat_index_bits, name="refill_beat")
        response_opcode = Signal(4, name="response_opcode")
        response_param = Signal(2, name="response_param")
        response_size = Signal(3, name="response_size")
        response_source = Signal(c.source_bits, name="response_source")
        response_data = Signal(c.data_bits, name="response_data")
        response_denied = Signal(name="response_denied")
        response_corrupt = Signal(name="response_corrupt")
        outer_c_pending = Signal(name="outer_c_pending")
        outer_b_pending = Signal(name="outer_b_pending")
        l2_miss_pulse = Signal(name="l2_miss_pulse")
        hint_pending = Signal(name="hint_pending")

        # Convert a full edge address to the local slice address.  CoupledL2's
        # parent restores bank bits when it reconnects the outer network.
        # 将完整 edge 地址转换为 slice 本地地址；CoupledL2 父级重连外部网络时恢复 bank 位。
        def local_address_expr(address: Any) -> Any:
            if c.bank_bits:
                return Cat(address[:c.offset_bits], address[c.offset_bits + c.bank_bits:], Const(0, c.bank_bits))
            return address

        # Combinational channel defaults and output payloads. / 组合通道默认值及输出载荷。
        m.d.comb += [
            self.in_a_ready.eq((state == 0) & ~self.flush),
            self.in_c_ready.eq((state == 0) & ~self.flush),
            self.in_e_ready.eq(1),
            self.in_d_valid.eq(state == 1), self.in_d_bits_opcode.eq(response_opcode),
            self.in_d_bits_param.eq(response_param), self.in_d_bits_size.eq(response_size),
            self.in_d_bits_source.eq(response_source), self.in_d_bits_sink.eq(0),
            self.in_d_bits_denied.eq(response_denied), self.in_d_bits_echo_isKeyword.eq(pending_keyword),
            self.in_d_bits_data.eq(response_data), self.in_d_bits_corrupt.eq(response_corrupt),
            self.out_a_valid.eq(state == 2), self.out_a_bits_opcode.eq(6), self.out_a_bits_param.eq(0),
            self.out_a_bits_size.eq(pending_size), self.out_a_bits_source.eq(pending_outer_source),
            self.out_a_bits_address.eq(pending_address), self.out_a_bits_user_reqSource.eq(pending_req_source),
            self.out_a_bits_echo_blockisdirty.eq(pending_dirty), self.out_a_bits_mask.eq((1 << c.mask_bits) - 1),
            self.out_a_bits_data.eq(pending_data), self.out_a_bits_corrupt.eq(0),
            self.out_c_valid.eq(outer_c_pending), self.out_c_bits_opcode.eq(7), self.out_c_bits_param.eq(0),
            self.out_c_bits_size.eq(pending_size), self.out_c_bits_source.eq(pending_outer_source),
            self.out_c_bits_address.eq(pending_address), self.out_c_bits_user_reqSource.eq(pending_req_source),
            self.out_c_bits_echo_blockisdirty.eq(1), self.out_c_bits_data.eq(Array([x.data for x in data_reads])[pending_way][:c.data_bits]),
            self.out_c_bits_corrupt.eq(0),
            self.in_b_valid.eq(outer_b_pending), self.in_b_bits_opcode.eq(6), self.in_b_bits_param.eq(0),
            self.in_b_bits_size.eq(pending_size), self.in_b_bits_source.eq(0),
            self.in_b_bits_address.eq(pending_address), self.in_b_bits_mask.eq((1 << c.mask_bits) - 1),
            self.in_b_bits_data.eq(0), self.in_b_bits_corrupt.eq(0),
            self.out_d_ready.eq((state == 4) & ~self.flush), self.out_e_valid.eq(0),
            self.out_e_bits_sink.eq(0),
            self.l1Hint_valid.eq(hint_pending), self.l1Hint_bits_sourceId.eq(pending_source),
            self.l1Hint_bits_isKeyword.eq(pending_keyword), self.prefetch_req_ready.eq((state == 0) & ~self.flush),
            self.prefetch_resp_valid.eq(0), self.prefetch_train_valid.eq(0), self.error_valid.eq(0),
            self.error_bits_valid.eq(0), self.error_bits_address.eq(pending_address[:c.error_address_bits]),
            self.l2Miss.eq(l2_miss_pulse), self.l2FlushDone.eq(self.flush & (state == 0)),
        ]
        for signal in self.perf:
            m.d.comb += signal.eq(0)

        # Keep outer B probes ready only when no conflicting eviction is active.
        # 仅当没有冲突逐出时保持外部 B probe ready。
        m.d.comb += self.out_b_ready.eq((state == 0) & ~outer_c_pending & ~self.flush)

        request_fire = self.in_a_valid & self.in_a_ready
        release_fire = self.in_c_valid & self.in_c_ready
        response_fire = self.in_d_valid & self.in_d_ready
        outer_a_fire = self.out_a_valid & self.out_a_ready
        outer_c_fire = self.out_c_valid & self.out_c_ready
        outer_d_fire = self.out_d_valid & self.out_d_ready
        probe_fire = self.out_b_valid & self.out_b_ready

        # Memory write enables and data. / 存储器写使能及数据。
        c_set = self.in_c_bits_address[c.offset_bits + c.bank_bits:c.offset_bits + c.bank_bits + c.set_bits]
        c_tag = self.in_c_bits_address[c.offset_bits + c.bank_bits + c.set_bits:c.address_bits]
        final_refill = state == 4 & outer_d_fire & ((refill_beat == c.line_beats - 1) | (self.out_d_bits_size == pending_size))
        refill_shift = refill_beat * c.data_bits
        refill_mask = ((1 << c.data_bits) - 1) << refill_shift
        refill_line_next = (refill_data & ~refill_mask) | (self.out_d_bits_data << refill_shift)
        selected_pending_way = pending_way
        pending_old_data: Any = data_reads[0].data
        pending_old_dirty: Any = dirty_reads[0].data
        for way in range(1, c.ways):
            pending_old_data = Mux(selected_pending_way == way, data_reads[way].data, pending_old_data)
            pending_old_dirty = Mux(selected_pending_way == way, dirty_reads[way].data, pending_old_dirty)
        write_mask_bits = 0
        for byte in range(c.mask_bits):
            write_mask_bits |= 0xFF << (byte * 8)
        # The line payload stores the incoming beat in its low slice; a full
        # write is used for ReleaseData, while PutPartial keeps byte enables.
        # 缓存行载荷在低位保存输入 beat；ReleaseData 全写，PutPartial 保留字节使能。
        put_mask = 0
        for byte in range(c.mask_bits):
            put_mask |= 0xFF << (byte * 8)
        put_mask_value: Any = 0
        for byte in range(c.mask_bits):
            put_mask_value = put_mask_value | Mux(self.in_a_bits_mask[byte], 0xFF << (byte * 8), 0)
        store_data = (pending_old_data & ~put_mask_value) | (self.in_a_bits_data & put_mask_value)
        c_data = self.in_c_bits_data
        for way in range(c.ways):
            selected = pending_way == way
            release_selected = hit_vec[way]
            # Address/data/en are assigned once per write port to avoid
            # multiple-domain drivers in generated RTL.
            for write in (valid_writes[way], dirty_writes[way], tag_writes[way], data_writes[way]):
                m.d.comb += write.addr.eq(Mux(release_fire, c_set, pending_set))
            m.d.comb += [
                valid_writes[way].en.eq(
                    (final_refill & selected) |
                    (release_fire & release_selected & (self.in_c_bits_opcode == 6))),
                dirty_writes[way].en.eq(
                    (final_refill & selected) |
                    (release_fire & release_selected & (self.in_c_bits_opcode == 7)) |
                    (response_fire & pending_hit & selected & (pending_opcode == 0))),
                tag_writes[way].en.eq(final_refill & selected),
                data_writes[way].en.eq(
                    (final_refill & selected) |
                    (release_fire & release_selected & (self.in_c_bits_opcode == 7)) |
                    (response_fire & pending_hit & selected & (pending_opcode == 0))),
                valid_writes[way].data.eq(Mux(release_fire & (self.in_c_bits_opcode == 6), 0, 1)),
                dirty_writes[way].data.eq(Mux(final_refill, 0, 1)),
                tag_writes[way].data.eq(Mux(release_fire, c_tag, pending_tag)),
                data_writes[way].data.eq(Mux(final_refill, refill_line_next,
                                             Mux(release_fire, c_data, store_data))),
            ]

        # State transitions preserve one outstanding miss and explicit flush cancellation. /
        # 状态转换保持单个未决缺失，并显式处理 flush 取消。
        with m.If(self.reset | self.flush):
            m.d.coupled_l2 += [state.eq(0), outer_c_pending.eq(0), outer_b_pending.eq(0),
                               l2_miss_pulse.eq(0), hint_pending.eq(0), refill_beat.eq(0), repl_way.eq(0)]
        with m.Else():
            m.d.coupled_l2 += [l2_miss_pulse.eq(0), hint_pending.eq(0)]
            with m.If(state == 0):
                with m.If(probe_fire):
                    m.d.coupled_l2 += [pending_address.eq(local_address_expr(self.out_b_bits_address)), pending_size.eq(self.out_b_bits_size),
                                       pending_source.eq(self.out_b_bits_source), pending_outer_source.eq(0),
                                       outer_b_pending.eq(1), state.eq(5)]
                with m.Elif(release_fire):
                    m.d.coupled_l2 += [pending_address.eq(local_address_expr(self.in_c_bits_address)), pending_source.eq(self.in_c_bits_source), pending_outer_source.eq(0),
                                       pending_size.eq(self.in_c_bits_size), pending_data.eq(self.in_c_bits_data),
                                       pending_opcode.eq(self.in_c_bits_opcode), state.eq(1), response_opcode.eq(6),
                                       response_source.eq(self.in_c_bits_source), response_size.eq(self.in_c_bits_size),
                                       response_data.eq(0), response_denied.eq(0), response_corrupt.eq(self.in_c_bits_corrupt)]
                    # ReleaseData writes the received beat; Release invalidates the line. / 
                    # ReleaseData 写入接收 beat；Release 使缓存行失效。
                with m.Elif(request_fire | (self.prefetch_req_valid & self.prefetch_req_ready)):
                    # A-channel has priority over prefetch, matching RequestArb's C/B/A ordering after C/B are idle.
                    m.d.coupled_l2 += [pending_opcode.eq(Mux(request_fire, self.in_a_bits_opcode, 5)),
                                       pending_param.eq(Mux(request_fire, self.in_a_bits_param, 0)),
                                       pending_size.eq(Mux(request_fire, self.in_a_bits_size, c.offset_bits)),
                                       pending_source.eq(Mux(request_fire, self.in_a_bits_source, self.prefetch_req_bits_source)),
                                       pending_address.eq(Mux(request_fire, local_address_expr(self.in_a_bits_address),
                                                              restore_address_expr(self.prefetch_req_bits_tag, self.prefetch_req_bits_set,
                                                                                   0, self.slice_id, c))),
                                       pending_req_source.eq(Mux(request_fire, self.in_a_bits_user_reqSource, self.prefetch_req_bits_pfSource)),
                                       pending_alias.eq(Mux(request_fire, self.in_a_bits_user_alias, 0)),
                                       pending_vaddr.eq(Mux(request_fire, self.in_a_bits_user_vaddr, self.prefetch_req_bits_vaddr)),
                                       pending_keyword.eq(Mux(request_fire, self.in_a_bits_echo_isKeyword, 0)),
                                       pending_data.eq(Mux(request_fire, self.in_a_bits_data, 0)),
                                       pending_mask.eq(Mux(request_fire, self.in_a_bits_mask, 0)),
                                       pending_set.eq(req_set), pending_tag.eq(req_tag), pending_way.eq(Mux(hit_any, hit_way, victim_way)),
                                       pending_dirty.eq(Array([x.data for x in dirty_reads])[Mux(hit_any, hit_way, victim_way)]),
                                       pending_hit.eq(hit_any), pending_from_prefetch.eq(~request_fire), pending_outer_source.eq(0)]
                    with m.If(hit_any):
                        m.d.coupled_l2 += [state.eq(1), response_source.eq(Mux(request_fire, self.in_a_bits_source, self.prefetch_req_bits_source)),
                                           response_size.eq(Mux(request_fire, self.in_a_bits_size, c.offset_bits)),
                                           response_param.eq(0), response_denied.eq(0), response_corrupt.eq(0),
                                           response_opcode.eq(Mux(Mux(request_fire, self.in_a_bits_opcode, 5) == 5, 2,
                                                                  Mux(Mux(request_fire, self.in_a_bits_opcode, 5) <= 1, 0,
                                                                      Mux(Mux(request_fire, self.in_a_bits_opcode, 5) >= 6, 5, 1)))),
                                           response_data.eq(Mux(Mux(request_fire, self.in_a_bits_opcode, 5) == 5, 0,
                                                                Array([x.data for x in data_reads])[hit_way][:c.data_bits]))]
                    with m.Else():
                        m.d.coupled_l2 += [l2_miss_pulse.eq(1), state.eq(Mux(Array([x.data for x in dirty_reads])[victim_way], 3, 2)),
                                           response_source.eq(Mux(request_fire, self.in_a_bits_source, self.prefetch_req_bits_source)),
                                           response_size.eq(Mux(request_fire, self.in_a_bits_size, c.offset_bits)), response_param.eq(0),
                                           response_denied.eq(0), response_corrupt.eq(0)]
                        with m.If(Array([x.data for x in dirty_reads])[victim_way]):
                            m.d.coupled_l2 += outer_c_pending.eq(1)
            with m.Elif(state == 1):
                with m.If(response_fire):
                    m.d.coupled_l2 += state.eq(0)
            with m.Elif(state == 2):
                with m.If(outer_a_fire):
                    m.d.coupled_l2 += [state.eq(4), refill_beat.eq(0)]
            with m.Elif(state == 3):
                with m.If(outer_c_fire):
                    m.d.coupled_l2 += [outer_c_pending.eq(0), state.eq(2)]
            with m.Elif(state == 4):
                with m.If(outer_d_fire):
                    m.d.coupled_l2 += [refill_data.eq((refill_data & ~(((1 << c.data_bits) - 1) << (refill_beat * c.data_bits))) |
                                                       (self.out_d_bits_data << (refill_beat * c.data_bits)))]
                    with m.If((refill_beat == c.line_beats - 1) | (self.out_d_bits_size == pending_size)):
                        m.d.coupled_l2 += [state.eq(1), response_opcode.eq(Mux(pending_opcode >= 6, 5, 1)),
                                           response_source.eq(pending_source), response_size.eq(pending_size),
                                           response_param.eq(0), response_data.eq(self.out_d_bits_data),
                                           response_denied.eq(self.out_d_bits_denied), response_corrupt.eq(self.out_d_bits_corrupt),
                                           refill_beat.eq(0)]
                    with m.Else():
                        m.d.coupled_l2 += refill_beat.eq(refill_beat + 1)
            with m.Elif(state == 5):
                # A probe is acknowledged downwards after the upper cache has accepted it. /
                # 上层缓存接受 probe 后向下游发送确认。
                with m.If(self.in_b_valid & self.in_b_ready):
                    m.d.coupled_l2 += [outer_b_pending.eq(0), state.eq(0)]

        # Keep the replacement pointer moving only after a completed refill. / 仅在回填完成后推进替换指针。
        with m.If(state == 4 & outer_d_fire & ((refill_beat == c.line_beats - 1) | (self.out_d_bits_size == pending_size))):
            m.d.coupled_l2 += repl_way.eq(Mux(repl_way == c.ways - 1, 0, repl_way + 1))

        return m


# Source-oriented aliases are retained in metadata, while product-facing HDL uses UHSC. /
# 保留源导向别名用于元数据，面向产品的 HDL 使用 UHSC。
CoupledL2SliceBoundary = CoupledL2Slice
TL2TLCoupledL2Slice = CoupledL2Slice
Slice = CoupledL2Slice


# =============================================================================
# Public Adapter
# =============================================================================
# Emit deterministic Verilog for the aggregate CoupledL2 slice family. / 为聚合 CoupledL2 slice family 输出确定性 Verilog。
def build_verilog(configuration, injected_dependencies):
    """Return Verilog for the bounded V2 CoupledL2 slice. / 返回有界 V2 CoupledL2 slice 的 Verilog。"""

    del injected_dependencies
    if isinstance(configuration, CoupledL2SliceConfig):
        cfg = configuration
        name = "UHSCCoupledL2Slice"
    elif isinstance(configuration, dict):
        fields = CoupledL2SliceConfig.__dataclass_fields__
        values: dict[str, Any] = {}
        for key in fields:
            if key in configuration:
                value = configuration[key]
                values[key] = bool(value) if key == "prefetch" else int(value)
        cfg = CoupledL2SliceConfig(**values)
        name = str(configuration.get("module", configuration.get("name", "UHSCCoupledL2Slice")))
    elif configuration is None:
        cfg, name = CoupledL2SliceConfig(), "UHSCCoupledL2Slice"
    else:
        raise TypeError("configuration must be CoupledL2SliceConfig, dict, or None")
    top = CoupledL2Slice(cfg, {})
    ports = [top.clock, top.reset, top.flush, top.slice_id]
    for prefix in ("in_a", "in_b", "in_c", "in_d", "in_e", "out_a", "out_b", "out_c", "out_d", "out_e"):
        ports.extend(signal for name_value, signal in top.__dict__.items()
                     if name_value.startswith(prefix + "_") and name_value.count("_") >= 2 and name_value != f"io_{name_value}")
    # Preserve insertion order while removing alias duplicates. / 保持插入顺序并移除别名重复项。
    unique: list[Signal] = []
    seen: set[int] = set()
    for signal in ports:
        if id(signal) not in seen:
            unique.append(signal); seen.add(id(signal))
    ports = unique + [top.l1Hint_valid, top.l1Hint_ready, top.l1Hint_bits_sourceId, top.l1Hint_bits_isKeyword,
                     top.prefetch_train_valid, top.prefetch_train_bits_tag, top.prefetch_train_bits_set,
                     top.prefetch_train_bits_needT, top.prefetch_train_bits_source, top.prefetch_train_bits_vaddr,
                     top.prefetch_train_bits_hit, top.prefetch_train_bits_prefetched, top.prefetch_train_bits_pfsource,
                     top.prefetch_train_bits_reqsource, top.prefetch_req_valid, top.prefetch_req_ready,
                     top.prefetch_req_bits_tag, top.prefetch_req_bits_set, top.prefetch_req_bits_vaddr,
                     top.prefetch_req_bits_needT, top.prefetch_req_bits_source, top.prefetch_req_bits_pfSource,
                     top.prefetch_resp_valid, top.prefetch_resp_ready, top.error_valid, top.error_bits_valid,
                     top.error_bits_address, top.l2Miss, top.l2FlushDone, *top.perf]
    unique = []
    seen = set()
    for signal in ports:
        if id(signal) not in seen:
            unique.append(signal); seen.add(id(signal))
    return verilog.convert(top, name=name, ports=unique, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print a deterministic default export for command-line probes. / 打印确定性的默认导出以支持命令行探测。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
