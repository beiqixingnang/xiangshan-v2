"""UHSC V2 cache/memory parent closure.
UHSC V2 缓存/存储器父级闭包。

The locked V2 ``MemBlock`` is a very large Diplomacy boundary.  This
搬运-ready target keeps the executable, protocol-relevant part of that
boundary small and explicit: a four-stage-ish DCache request/miss/refill
transaction, the AMOALU and TagArray child contracts, and the instruction
frontend bridge.  TileLink, MMU/LSU, and MBIST controls are represented as
injected/observable transaction stubs rather than silently imported from a
sibling Build-Cpu file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amaranth import Array, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# Public symbols / 公开符号:
#   - MemBlockParentConfig, UHSCCacheMainPipe, UHSCDCacheWrapper,
#     UHSCMemoryMemBlock, build_verilog, main
# Port contract / 端口契约:
#   - source-compatible request/miss/refill observations, reduced TileLink A/D
#     channels, instruction uncache bridge, flush, MMU/LSU and MBIST stubs.
# Real structure / 真实结构:
#   - MainPipe arbitrates load/store/AMO traffic, TagArray supplies the tag
#     observation, AMOALU supplies atomic data, DCacheWrapper maps misses to
#     TileLink A/D, and MemBlock bridges the I-cache and issue boundaries.
#   - ``injected_dependencies`` is the only child binding mechanism.  No
#     sibling Build-Cpu module is imported by this file.
# Status / 状态: PASS_BOUNDED_PARENT (full 669-port Diplomacy closure remains open)
__all__ = [
    "MemBlockParentConfig",
    "UHSCCacheMainPipe",
    "UHSCDCacheWrapper",
    "UHSCMemoryMemBlock",
    "MainPipeParent",
    "DCacheWrapperParent",
    "MemBlockParent",
    "MainPipe",
    "DCacheWrapper",
    "MemBlock",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class MemBlockParentConfig:
    """Finite geometry used by the reduced V2 parent boundary. / 精简 V2 父边界的有限几何。"""

    addr_bits: int = 48
    vaddr_bits: int = 50
    data_bits: int = 128
    line_bits: int = 512
    id_bits: int = 6
    tag_sets: int = 256
    tag_ways: int = 4
    tag_bits: int = 36
    tag_ecc_bits: int = 7

    # Validate V2-compatible widths and power-of-two tag geometry. / 校验 V2 兼容宽度及二次幂标签几何。
    def __post_init__(self) -> None:
        if self.addr_bits < 8 or self.vaddr_bits < self.addr_bits:
            raise ValueError("address widths are inconsistent")
        if self.data_bits != 128 or self.line_bits != 512:
            raise ValueError("the V2 parent probe uses 128-bit words and 512-bit lines")
        if self.id_bits < 1:
            raise ValueError("id_bits must be positive")
        if self.tag_sets < 1 or self.tag_sets & (self.tag_sets - 1):
            raise ValueError("tag_sets must be a power of two")
        if self.tag_ways < 1 or self.tag_ways & (self.tag_ways - 1):
            raise ValueError("tag_ways must be a power of two")
        if self.tag_bits < 1 or self.tag_ecc_bits < 0:
            raise ValueError("tag widths must be positive/non-negative")

    # Return the set-index width used by the explicit TagArray transaction. / 返回显式 TagArray 事务使用的组索引宽度。
    @property
    def set_bits(self) -> int:
        return max(1, (self.tag_sets - 1).bit_length())

    # Return the byte-mask width for one V2 word. / 返回一个 V2 字的字节掩码宽度。
    @property
    def byte_mask_bits(self) -> int:
        return self.data_bits // 8


# =============================================================================
# Implementation
# =============================================================================
class _AtomicFallback(Elaboratable):
    """Small dependency fallback used only when no AMOALU child is injected. / 未注入 AMOALU 时使用的小型依赖回退。"""

    # Construct the AMOALU-compatible fallback ports. / 构造 AMOALU 兼容回退端口。
    def __init__(self, bits: int = 128) -> None:
        self.io_mask = Signal(bits // 8, name="io_mask")
        self.io_cmd = Signal(5, name="io_cmd")
        self.io_lhs = Signal(bits, name="io_lhs")
        self.io_rhs = Signal(bits, name="io_rhs")
        self.io_out = Signal(bits, name="io_out")
        self.io_out_unmasked = Signal(bits, name="io_out_unmasked")

    # Elaborate a source-shaped AMO fallback for direct standalone use. / 展开源形 AMO 回退以支持直接独立使用。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        lhs, rhs, cmd = self.io_lhs, self.io_rhs, self.io_cmd
        is_add = cmd == 0x8
        is_xor = (cmd == 0x9) | (cmd == 0xA)
        is_or = (cmd == 0xA) | (cmd == 0xB)
        is_min = (cmd == 0xC) | (cmd == 0xE)
        is_max = (cmd == 0xD) | (cmd == 0xF)
        signed = (cmd & 0x2) == 0
        unsigned_min = Mux(signed, lhs < rhs, lhs < rhs)
        minmax = Mux(Mux(unsigned_min, is_min, is_max), lhs, rhs)
        raw = Mux(is_add, lhs + rhs, Mux(is_xor | is_or,
                                          Mux(is_xor, lhs ^ rhs, 0) |
                                          Mux(is_or, lhs | rhs, 0), minmax))
        mask = self.io_mask
        expanded = 0
        for index in range(self.io_lhs.width // 8):
            expanded = expanded | Mux(mask[index], Const(0xFF << (8 * index), self.io_lhs.width), 0)
        m.d.comb += [self.io_out_unmasked.eq(raw),
                     self.io_out.eq((raw & expanded) | (lhs & ~expanded))]
        return m


class _TagFallback(Elaboratable):
    """Synchronous masked tag storage matching the injected TagArray surface. / 与注入 TagArray 表面匹配的同步按掩码标签存储。"""

    # Construct a compact tag-array fallback with source-shaped observations. / 构造带源形观测的紧凑标签阵列回退。
    def __init__(self, cfg: MemBlockParentConfig) -> None:
        self.cfg = cfg
        width = cfg.tag_bits + cfg.tag_ecc_bits
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.io_read_ready = Signal(name="io_read_ready")
        self.io_read_valid = Signal(name="io_read_valid")
        self.io_read_bits_idx = Signal(cfg.set_bits, name="io_read_bits_idx")
        self.io_read_bits_way_en = Signal(cfg.tag_ways, name="io_read_bits_way_en")
        self.io_write_valid = Signal(name="io_write_valid")
        self.io_write_bits_idx = Signal(cfg.set_bits, name="io_write_bits_idx")
        self.io_write_bits_way_en = Signal(cfg.tag_ways, name="io_write_bits_way_en")
        self.io_write_bits_way = Signal(max(1, (cfg.tag_ways - 1).bit_length()), name="io_write_bits_way")
        self.io_write_bits_tag = Signal(cfg.tag_bits, name="io_write_bits_tag")
        self.io_write_bits_ecc = Signal(cfg.tag_ecc_bits, name="io_write_bits_ecc")
        self.io_rdata = Signal(cfg.tag_ways * width, name="io_rdata")

    # Elaborate reset, masked writes and one-cycle synchronous reads. / 展开复位、按掩码写入及一拍同步读取。
    def elaborate(self, platform: Any) -> Module:
        del platform
        c = self.cfg
        width = c.tag_bits + c.tag_ecc_bits
        m = Module()
        domain = ClockDomain("tag_sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.tag_sync = domain
        rows = [Signal(width, name=f"tag_{way}") for way in range(c.tag_ways)]
        valid = Signal(name="tag_valid")
        m.d.comb += self.io_read_ready.eq(valid & ~self.io_write_valid)
        with m.If(self.reset):
            m.d.tag_sync += valid.eq(0)
        with m.Else():
            m.d.tag_sync += valid.eq(1)
            with m.If(self.io_write_valid):
                for way in range(c.tag_ways):
                    with m.If(self.io_write_bits_way_en[way]):
                        m.d.tag_sync += rows[way].eq(self.io_write_bits_tag |
                                                  (self.io_write_bits_ecc << c.tag_bits))
        for way, row in enumerate(rows):
            lo = way * width
            m.d.comb += self.io_rdata[lo:lo + width].eq(row)
        return m


class UHSCCacheMainPipe(Elaboratable):
    """Reduced V2 DCache MainPipe transaction boundary. / 精简 V2 DCache MainPipe 事务边界。"""

    # Construct explicit request, miss/refill, child-observation and response ports. / 构造显式请求、缺失/回填、子级观测及响应端口。
    def __init__(self, configuration: MemBlockParentConfig | None = None,
                 injected_dependencies: dict[str, Any] | None = None) -> None:
        self.config = configuration or MemBlockParentConfig()
        deps = injected_dependencies if isinstance(injected_dependencies, dict) else {}
        # The locked V2 AMOALU operates on one 64-bit quadword; the parent
        # carries it in the low word of the 128-bit transaction payload.
        # 锁定 V2 AMOALU 处理单个 64 位 quadword；父级将其放在 128 位载荷低字中。
        self.amo = deps.get("amoalu") or deps.get("AMOALU") or _AtomicFallback(64)
        self.tag = deps.get("tag_array") or deps.get("TagArray") or _TagFallback(self.config)
        c = self.config
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.req_valid = Signal(name="io_req_valid")
        self.req_ready = Signal(name="io_req_ready")
        self.req_source = Signal(2, name="io_req_bits_source")
        self.req_cmd = Signal(5, name="io_req_bits_cmd")
        self.req_vaddr = Signal(c.vaddr_bits, name="io_req_bits_vaddr")
        self.req_addr = Signal(c.addr_bits, name="io_req_bits_addr")
        self.req_data = Signal(c.data_bits, name="io_req_bits_data")
        self.req_mask = Signal(c.byte_mask_bits, name="io_req_bits_mask")
        self.req_id = Signal(c.id_bits, name="io_req_bits_id")
        self.req_miss = Signal(name="io_req_bits_miss")
        self.miss_ready = Signal(name="io_miss_req_ready")
        self.miss_valid = Signal(name="io_miss_req_valid")
        self.miss_source = Signal(2, name="io_miss_req_bits_source")
        self.miss_cmd = Signal(5, name="io_miss_req_bits_cmd")
        self.miss_addr = Signal(c.addr_bits, name="io_miss_req_bits_addr")
        self.miss_data = Signal(c.data_bits, name="io_miss_req_bits_data")
        self.miss_mask = Signal(c.byte_mask_bits, name="io_miss_req_bits_mask")
        self.miss_id = Signal(c.id_bits, name="io_miss_req_bits_id")
        self.refill_valid = Signal(name="io_refill_req_valid")
        self.refill_data = Signal(c.data_bits, name="io_refill_req_bits_data")
        self.refill_id = Signal(c.id_bits, name="io_refill_req_bits_id")
        self.resp_valid = Signal(name="io_resp_valid")
        self.resp_data = Signal(c.data_bits, name="io_resp_bits_data")
        self.resp_id = Signal(c.id_bits, name="io_resp_bits_id")
        self.resp_miss = Signal(name="io_resp_bits_miss")
        self.amo_result = Signal(c.data_bits, name="io_amo_result")
        self.amo_raw = Signal(c.data_bits, name="io_amo_raw")
        self.tag_ready = Signal(name="io_tag_read_ready")
        self.tag_rdata = Signal(c.tag_ways * (c.tag_bits + c.tag_ecc_bits), name="io_tag_rdata")
        self.flush = Signal(name="io_flush")

    # Elaborate one outstanding request with explicit miss/refill and child wiring. / 展开单个未完成请求及显式缺失/回填、子级接线。
    def elaborate(self, platform: Any) -> Module:
        del platform
        c = self.config
        m = Module()
        domain = ClockDomain("mainpipe_sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.mainpipe_sync = domain
        m.submodules.amo = self.amo
        m.submodules.tag = self.tag

        pending = Signal(name="mainpipe_pending")
        pending_miss = Signal(name="mainpipe_pending_miss")
        pending_source = Signal(2, name="mainpipe_pending_source")
        pending_cmd = Signal(5, name="mainpipe_pending_cmd")
        pending_addr = Signal(c.addr_bits, name="mainpipe_pending_addr")
        pending_data = Signal(c.data_bits, name="mainpipe_pending_data")
        pending_rhs = Signal(c.data_bits, name="mainpipe_pending_rhs")
        pending_mask = Signal(c.byte_mask_bits, name="mainpipe_pending_mask")
        pending_id = Signal(c.id_bits, name="mainpipe_pending_id")
        response = Signal(name="mainpipe_response")
        response_data = Signal(c.data_bits, name="mainpipe_response_data")
        response_id = Signal(c.id_bits, name="mainpipe_response_id")
        response_miss = Signal(name="mainpipe_response_miss")

        # Child contracts are deliberately connected by named attributes only. / 子级契约有意仅通过命名属性连接。
        amo_width = len(self.amo.io_lhs)
        amo_mask_width = len(self.amo.io_mask)
        amo_lhs = Mux(pending, pending_data[:amo_width], self.req_data[:amo_width])
        amo_mask = Mux(pending, pending_mask[:amo_mask_width], self.req_mask[:amo_mask_width])
        amo_rhs = Mux(pending, pending_rhs[:amo_width], self.refill_data[:amo_width])
        amo_out_wide = self.amo.io_out
        amo_raw_wide = self.amo.io_out_unmasked
        m.d.comb += [self.amo.io_mask.eq(amo_mask), self.amo.io_cmd.eq(Mux(pending, pending_cmd, self.req_cmd)),
                     self.amo.io_lhs.eq(amo_lhs), self.amo.io_rhs.eq(amo_rhs),
                     self.amo_result.eq(amo_out_wide), self.amo_raw.eq(amo_raw_wide)]
        m.d.comb += [self.tag.clock.eq(self.clock), self.tag.reset.eq(self.reset),
                     self.tag.io_read_valid.eq(self.req_valid & self.req_ready),
                     self.tag.io_read_bits_idx.eq(self.req_addr[:c.set_bits]),
                     self.tag.io_read_bits_way_en.eq((1 << c.tag_ways) - 1),
                     self.tag.io_write_valid.eq(self.refill_valid),
                     self.tag.io_write_bits_idx.eq(self.refill_id[:c.set_bits]),
                     self.tag.io_write_bits_way_en.eq((1 << c.tag_ways) - 1),
                     self.tag.io_write_bits_way.eq(0),
                     self.tag.io_write_bits_tag.eq(self.refill_data[:c.tag_bits]),
                     self.tag.io_write_bits_ecc.eq(self.refill_data[:c.tag_ecc_bits]),
                     self.tag_ready.eq(self.tag.io_read_ready),
                     self.tag_rdata.eq(self.tag.io_rdata)]

        m.d.comb += [self.req_ready.eq(~pending & ~self.flush),
                     self.miss_valid.eq(pending & pending_miss & ~self.flush),
                     self.miss_source.eq(pending_source), self.miss_cmd.eq(pending_cmd),
                     self.miss_addr.eq(pending_addr), self.miss_data.eq(pending_data),
                     self.miss_mask.eq(pending_mask), self.miss_id.eq(pending_id),
                     self.resp_valid.eq(response & ~self.flush),
                     self.resp_data.eq(response_data), self.resp_id.eq(response_id),
                     self.resp_miss.eq(response_miss)]
        request_fire = self.req_valid & self.req_ready
        miss_fire = self.miss_valid & self.miss_ready
        refill_fire = self.refill_valid & pending
        # Response is a one-cycle pulse; a flush drops both pending and response. / 响应为单拍脉冲；flush 丢弃未决事务及响应。
        with m.If(self.flush):
            m.d.mainpipe_sync += [pending.eq(0), response.eq(0)]
        with m.Else():
            m.d.mainpipe_sync += response.eq(0)
            with m.If(request_fire):
                m.d.mainpipe_sync += [pending.eq(1), pending_miss.eq(self.req_miss),
                             pending_source.eq(self.req_source), pending_cmd.eq(self.req_cmd),
                             pending_addr.eq(self.req_addr), pending_data.eq(self.req_data),
                             pending_mask.eq(self.req_mask), pending_id.eq(self.req_id),
                             pending_rhs.eq(self.refill_data)]
            with m.If(pending & ~pending_miss):
                m.d.mainpipe_sync += [pending.eq(0), response.eq(1),
                             response_data.eq(Mux(pending_source == 2, self.amo_result, pending_data)),
                             response_id.eq(pending_id), response_miss.eq(0)]
            with m.If(pending & pending_miss & (refill_fire | miss_fire & self.refill_valid)):
                m.d.mainpipe_sync += [pending.eq(0), response.eq(1),
                             response_data.eq(Mux(pending_source == 2, self.amo_result, self.refill_data)),
                             response_id.eq(Mux(refill_fire, self.refill_id, pending_id)),
                             response_miss.eq(1)]
        return m


class UHSCDCacheWrapper(Elaboratable):
    """Reduced DCacheWrapper with explicit TileLink and MBIST boundaries. / 带显式 TileLink 与 MBIST 边界的精简 DCacheWrapper。"""

    # Construct wrapper ports and inject the reduced MainPipe child. / 构造外壳端口并注入精简 MainPipe 子级。
    def __init__(self, configuration: MemBlockParentConfig | None = None,
                 injected_dependencies: dict[str, Any] | None = None) -> None:
        self.config = configuration or MemBlockParentConfig()
        deps = injected_dependencies if isinstance(injected_dependencies, dict) else {}
        child = deps.get("mainpipe") or deps.get("MainPipe")
        self.mainpipe = child or UHSCCacheMainPipe(self.config, deps)
        c = self.config
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        # Core request surface. / 核心请求表面。
        for name, width in (("req_valid", 1), ("req_source", 2), ("req_cmd", 5),
                            ("req_vaddr", c.vaddr_bits), ("req_addr", c.addr_bits),
                            ("req_data", c.data_bits), ("req_mask", c.byte_mask_bits),
                            ("req_id", c.id_bits), ("req_miss", 1)):
            setattr(self, name, Signal(width, name=f"io_{name}"))
        self.req_ready = Signal(name="io_req_ready")
        self.refill_valid = Signal(name="io_refill_valid")
        self.refill_data = Signal(c.data_bits, name="io_refill_data")
        self.refill_id = Signal(c.id_bits, name="io_refill_id")
        self.tl_a_ready = Signal(name="auto_client_out_a_ready")
        self.tl_a_valid = Signal(name="auto_client_out_a_valid")
        self.tl_a_opcode = Signal(4, name="auto_client_out_a_bits_opcode")
        self.tl_a_size = Signal(3, name="auto_client_out_a_bits_size")
        self.tl_a_source = Signal(c.id_bits, name="auto_client_out_a_bits_source")
        self.tl_a_address = Signal(c.addr_bits, name="auto_client_out_a_bits_address")
        self.tl_a_data = Signal(c.data_bits, name="auto_client_out_a_bits_data")
        self.tl_a_mask = Signal(c.byte_mask_bits, name="auto_client_out_a_bits_mask")
        self.tl_d_valid = Signal(name="auto_client_out_d_valid")
        self.tl_d_source = Signal(c.id_bits, name="auto_client_out_d_bits_source")
        self.tl_d_data = Signal(c.data_bits, name="auto_client_out_d_bits_data")
        self.resp_valid = Signal(name="io_resp_valid")
        self.resp_data = Signal(c.data_bits, name="io_resp_data")
        self.resp_id = Signal(c.id_bits, name="io_resp_id")
        self.resp_miss = Signal(name="io_resp_miss")
        self.error_valid = Signal(name="io_error_valid")
        self.mbist_enable = Signal(name="io_mbist_enable")
        self.mbist_done = Signal(name="io_mbist_done")
        self.flush = Signal(name="io_flush")

    # Elaborate TileLink A/D mapping and explicit MBIST/DFT pass-through. / 展开 TileLink A/D 映射及显式 MBIST/DFT 直通。
    def elaborate(self, platform: Any) -> Module:
        del platform
        c = self.config
        m = Module()
        m.submodules.mainpipe = self.mainpipe
        p = self.mainpipe
        m.d.comb += [p.clock.eq(self.clock), p.reset.eq(self.reset), p.flush.eq(self.flush),
                     p.req_valid.eq(self.req_valid), p.req_source.eq(self.req_source),
                     p.req_cmd.eq(self.req_cmd), p.req_vaddr.eq(self.req_vaddr),
                     p.req_addr.eq(self.req_addr), p.req_data.eq(self.req_data),
                     p.req_mask.eq(self.req_mask), p.req_id.eq(self.req_id),
                     p.req_miss.eq(self.req_miss), self.req_ready.eq(p.req_ready),
                     p.miss_ready.eq(self.tl_a_ready), p.refill_valid.eq(self.tl_d_valid),
                     p.refill_data.eq(self.tl_d_data), p.refill_id.eq(self.tl_d_source),
                     self.tl_a_valid.eq(p.miss_valid), self.tl_a_source.eq(p.miss_id),
                     self.tl_a_address.eq(p.miss_addr), self.tl_a_data.eq(p.miss_data),
                     self.tl_a_mask.eq(p.miss_mask), self.tl_a_opcode.eq(Mux(p.miss_source == 1, 0, 4)),
                     self.tl_a_size.eq(4), self.resp_valid.eq(p.resp_valid),
                     self.resp_data.eq(p.resp_data), self.resp_id.eq(p.resp_id),
                     self.resp_miss.eq(p.resp_miss), self.error_valid.eq(0),
                     self.mbist_done.eq(~self.mbist_enable)]
        return m


class UHSCMemoryMemBlock(Elaboratable):
    """UHSC-localized MemBlock parent with DCache and frontend bridge. / 带 DCache 与前端桥的 UHSC 本地化 MemBlock 父级。"""

    # Construct issue, cache, frontend, flush and dependency-stub ports. / 构造发射、缓存、前端、flush 及依赖桩端口。
    def __init__(self, configuration: MemBlockParentConfig | None = None,
                 injected_dependencies: dict[str, Any] | None = None) -> None:
        self.config = configuration or MemBlockParentConfig()
        deps = injected_dependencies if isinstance(injected_dependencies, dict) else {}
        child = deps.get("dcache") or deps.get("DCacheWrapper") or deps.get("dcache_wrapper")
        self.dcache = child or UHSCDCacheWrapper(self.config, deps)
        c = self.config
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.load_valid = Signal(name="io_load_issue_valid")
        self.store_valid = Signal(name="io_store_issue_valid")
        self.atomic_valid = Signal(name="io_atomic_issue_valid")
        self.issue_source = Signal(2, name="io_issue_source")
        self.issue_cmd = Signal(5, name="io_issue_cmd")
        self.issue_vaddr = Signal(c.vaddr_bits, name="io_issue_vaddr")
        self.issue_addr = Signal(c.addr_bits, name="io_issue_addr")
        self.issue_data = Signal(c.data_bits, name="io_issue_data")
        self.issue_mask = Signal(c.byte_mask_bits, name="io_issue_mask")
        self.issue_id = Signal(c.id_bits, name="io_issue_id")
        self.issue_miss = Signal(name="io_issue_miss")
        self.load_ready = Signal(name="io_load_issue_ready")
        self.store_ready = Signal(name="io_store_issue_ready")
        self.atomic_ready = Signal(name="io_atomic_issue_ready")
        self.refill_valid = Signal(name="io_refill_valid")
        self.refill_data = Signal(c.data_bits, name="io_refill_data")
        self.refill_id = Signal(c.id_bits, name="io_refill_id")
        self.tl_a_ready = Signal(name="auto_inner_out_a_ready")
        self.tl_a_valid = Signal(name="auto_inner_out_a_valid")
        self.tl_a_opcode = Signal(4, name="auto_inner_out_a_bits_opcode")
        self.tl_a_source = Signal(c.id_bits, name="auto_inner_out_a_bits_source")
        self.tl_a_address = Signal(c.addr_bits, name="auto_inner_out_a_bits_address")
        self.tl_a_data = Signal(c.data_bits, name="auto_inner_out_a_bits_data")
        self.tl_a_mask = Signal(c.byte_mask_bits, name="auto_inner_out_a_bits_mask")
        self.tl_d_valid = Signal(name="auto_inner_out_d_valid")
        self.tl_d_source = Signal(c.id_bits, name="auto_inner_out_d_bits_source")
        self.tl_d_data = Signal(c.data_bits, name="auto_inner_out_d_bits_data")
        self.writeback_valid = Signal(name="io_writeback_valid")
        self.writeback_data = Signal(c.data_bits, name="io_writeback_data")
        self.writeback_id = Signal(c.id_bits, name="io_writeback_id")
        self.writeback_miss = Signal(name="io_writeback_miss")
        self.icache_req_valid = Signal(name="io_icache_req_valid")
        self.icache_req_ready = Signal(name="io_icache_req_ready")
        self.icache_req_addr = Signal(c.vaddr_bits, name="io_icache_req_addr")
        self.icache_resp_valid = Signal(name="io_icache_resp_valid")
        self.icache_resp_data = Signal(32, name="io_icache_resp_data")
        self.flush = Signal(name="io_flush")
        self.mmu_ready = Signal(name="io_mmu_ready")
        self.lsu_ready = Signal(name="io_lsu_ready")
        self.mbist_enable = Signal(name="io_mbist_enable")
        self.mbist_done = Signal(name="io_mbist_done")

    # Elaborate issue arbitration, DCache mapping, frontend bridge and stubs. / 展开发射仲裁、DCache 映射、前端桥及依赖桩。
    def elaborate(self, platform: Any) -> Module:
        del platform
        c = self.config
        m = Module()
        domain = ClockDomain("mem_sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.mem_sync = domain
        m.submodules.dcache = self.dcache
        d = self.dcache
        issue_any = self.load_valid | self.store_valid | self.atomic_valid
        selected_valid = issue_any
        selected_ready = d.req_ready
        m.d.comb += [d.clock.eq(self.clock), d.reset.eq(self.reset), d.flush.eq(self.flush),
                     d.req_valid.eq(selected_valid), d.req_source.eq(Mux(self.atomic_valid, 2, self.issue_source)),
                     d.req_cmd.eq(self.issue_cmd), d.req_vaddr.eq(self.issue_vaddr), d.req_addr.eq(self.issue_addr),
                     d.req_data.eq(self.issue_data), d.req_mask.eq(self.issue_mask), d.req_id.eq(self.issue_id),
                     d.req_miss.eq(self.issue_miss), d.tl_a_ready.eq(self.tl_a_ready),
                     d.tl_d_valid.eq(self.tl_d_valid | self.refill_valid),
                     d.tl_d_source.eq(Mux(self.refill_valid, self.refill_id, self.tl_d_source)),
                     d.tl_d_data.eq(Mux(self.refill_valid | self.atomic_valid, self.refill_data, self.tl_d_data)),
                     d.mbist_enable.eq(self.mbist_enable),
                     self.load_ready.eq(selected_ready & ~self.store_valid & ~self.atomic_valid),
                     self.store_ready.eq(selected_ready & ~self.atomic_valid),
                     self.atomic_ready.eq(selected_ready),
                     self.tl_a_valid.eq(d.tl_a_valid), self.tl_a_opcode.eq(d.tl_a_opcode),
                     self.tl_a_source.eq(d.tl_a_source), self.tl_a_address.eq(d.tl_a_address),
                     self.tl_a_data.eq(d.tl_a_data), self.tl_a_mask.eq(d.tl_a_mask),
                     self.writeback_valid.eq(d.resp_valid), self.writeback_data.eq(d.resp_data),
                     self.writeback_id.eq(d.resp_id), self.writeback_miss.eq(d.resp_miss),
                     self.mbist_done.eq(d.mbist_done), self.mmu_ready.eq(1), self.lsu_ready.eq(1)]

        # One-entry instruction bridge: address is returned as a deterministic probe word. / 单项指令桥：返回确定性探针字。
        ic_pending = Signal(name="icache_pending")
        ic_addr = Signal(c.vaddr_bits, name="icache_addr_reg")
        m.d.comb += self.icache_req_ready.eq(~ic_pending & ~self.flush)
        with m.If(self.flush):
            m.d.mem_sync += ic_pending.eq(0)
        with m.Else():
            with m.If(self.icache_req_valid & self.icache_req_ready):
                m.d.mem_sync += [ic_pending.eq(1), ic_addr.eq(self.icache_req_addr)]
            with m.Else():
                m.d.mem_sync += ic_pending.eq(0)
        m.d.comb += [self.icache_resp_valid.eq(ic_pending & ~self.flush),
                     self.icache_resp_data.eq(ic_addr[:32] ^ Const(0x13579BDF, 32))]
        return m


# Source-oriented aliases remain available for internal callers. / 保留源代码导向别名供内部调用。
MainPipeParent = UHSCCacheMainPipe
DCacheWrapperParent = UHSCDCacheWrapper
MemBlockParent = UHSCMemoryMemBlock
MainPipe = UHSCCacheMainPipe
DCacheWrapper = UHSCDCacheWrapper
MemBlock = UHSCMemoryMemBlock


# =============================================================================
# Public Adapter
# =============================================================================
# Emit deterministic Verilog for the UHSC-localized parent and injected children. / 为 UHSC 本地化父级及注入子级输出确定性 Verilog。
def build_verilog(configuration, injected_dependencies):
    config_value = configuration if isinstance(configuration, dict) else {}
    config = MemBlockParentConfig(
        addr_bits=int(config_value.get("addr_bits", config_value.get("addrBits", 48))),
        vaddr_bits=int(config_value.get("vaddr_bits", config_value.get("vaddrBits", 50))),
        data_bits=int(config_value.get("data_bits", config_value.get("dataBits", 128))),
        line_bits=int(config_value.get("line_bits", config_value.get("lineBits", 512))),
        id_bits=int(config_value.get("id_bits", config_value.get("idBits", 6))),
        tag_sets=int(config_value.get("tag_sets", config_value.get("tagSets", 256))),
        tag_ways=int(config_value.get("tag_ways", config_value.get("tagWays", 4))),
        tag_bits=int(config_value.get("tag_bits", config_value.get("tagBits", 36))),
        tag_ecc_bits=int(config_value.get("tag_ecc_bits", config_value.get("tagECCBits", 7))),
    )
    deps = injected_dependencies if isinstance(injected_dependencies, dict) else {}
    top = UHSCMemoryMemBlock(config, deps)
    module_name = str(config_value.get("module", "UHSCMemoryMemBlock"))
    ports = [
        top.clock, top.reset,
        top.load_valid, top.store_valid, top.atomic_valid,
        top.issue_source, top.issue_cmd, top.issue_vaddr, top.issue_addr,
        top.issue_data, top.issue_mask, top.issue_id, top.issue_miss,
        top.load_ready, top.store_ready, top.atomic_ready,
        top.refill_valid, top.refill_data, top.refill_id,
        top.tl_a_ready, top.tl_a_valid, top.tl_a_opcode, top.tl_a_source,
        top.tl_a_address, top.tl_a_data, top.tl_a_mask,
        top.tl_d_valid, top.tl_d_source, top.tl_d_data,
        top.writeback_valid, top.writeback_data, top.writeback_id, top.writeback_miss,
        top.icache_req_valid, top.icache_req_ready, top.icache_req_addr,
        top.icache_resp_valid, top.icache_resp_data, top.flush,
        top.mmu_ready, top.lsu_ready, top.mbist_enable, top.mbist_done,
    ]
    return verilog.convert(top, name=module_name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print the default UHSC parent export; validation supplies real leaf children. / 打印默认 UHSC 父级导出；验证时注入真实叶级子模块。
def main() -> None:
    print(build_verilog({"module": "UHSCMemoryMemBlock"}, {}))


if __name__ == "__main__":
    main()
