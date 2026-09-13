"""V2 ICache miss-status holding register in Amaranth.
香山 V2 指令缓存缺失状态保持寄存器的 Amaranth 重写。
"""
from __future__ import annotations

from dataclasses import dataclass

from amaranth import Elaboratable, Module, Signal


# Module Contract
# ---------------------------------------------------------------------------
# The V2 Scala class is ``ICacheMSHR`` in ICacheMissUnit.scala.  Fetch entries
# are connected with flush tied low by the parent; prefetch entries expose the
# same signal.  The Python boundary keeps both signals so one implementation
# can be exercised against either extracted specialization.
__all__ = ["MshrConfig", "ICacheMSHR", "ICacheMshr"]


# Configuration
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MshrConfig:
    """Serializable geometry for one V2 MSHR. / 单个 V2 MSHR 的可序列化几何配置。"""

    paddr_bits: int = 48
    block_off_bits: int = 6
    idx_bits: int = 8
    way_bits: int = 2
    alias_tag_bits: int = 2
    source_bits: int = 4
    latency_bits: int = 16
    block_bytes: int = 64

    # Validate the finite configuration domain. / 校验有限的配置域。
    def __post_init__(self) -> None:
        if self.paddr_bits <= self.block_off_bits:
            raise ValueError("paddr_bits must exceed block_off_bits")
        if self.idx_bits < 1 or self.way_bits < 1:
            raise ValueError("index and way widths must be positive")
        if self.alias_tag_bits < 0 or self.alias_tag_bits > self.idx_bits:
            raise ValueError("alias_tag_bits must fit in idx_bits")
        if self.source_bits < 1 or self.latency_bits < 1:
            raise ValueError("source and latency widths must be positive")
        if self.block_bytes != (1 << self.block_off_bits):
            raise ValueError("block_bytes must match block_off_bits")

    # Return the physical block-address width. / 返回物理块地址位宽。
    @property
    # Return the physical block-address width. / 返回物理块地址位宽。
    def blk_paddr_bits(self) -> int:
        return self.paddr_bits - self.block_off_bits


# Implementation
# ---------------------------------------------------------------------------
class ICacheMSHR(Elaboratable):
    """One V2 ICache miss entry. / 一个 V2 指令缓存缺失表项。"""

    # Construct the V2-visible ports. / 构造 V2 可见端口。
    def __init__(
        self,
        entry_id: int = 0,
        is_fetch: bool = True,
        cfg: MshrConfig | None = None,
    ) -> None:
        self.cfg = cfg or MshrConfig()
        self.entry_id = int(entry_id)
        self.is_fetch = bool(is_fetch)
        c = self.cfg

        self.fencei = Signal(name="io_fencei")
        self.flush = Signal(name="io_flush")
        self.wfi_req = Signal(name="io_wfi_wfiReq")
        self.wfi_safe = Signal(name="io_wfi_wfiSafe")
        self.invalid = Signal(name="io_invalid")

        self.req_valid = Signal(name="io_req_valid")
        self.req_ready = Signal(name="io_req_ready")
        self.req_blk_paddr = Signal(c.blk_paddr_bits, name="io_req_bits_blkPaddr")
        self.req_v_set_idx = Signal(c.idx_bits, name="io_req_bits_vSetIdx")

        self.acquire_ready = Signal(name="io_acquire_ready")
        self.acquire_valid = Signal(name="io_acquire_valid")
        self.acquire_opcode = Signal(3, name="io_acquire_bits_acquire_opcode")
        self.acquire_size = Signal(max(1, c.block_off_bits.bit_length()), name="io_acquire_bits_acquire_size")
        self.acquire_source = Signal(c.source_bits, name="io_acquire_bits_acquire_source")
        self.acquire_address = Signal(c.paddr_bits, name="io_acquire_bits_acquire_address")
        self.acquire_alias_tag = Signal(c.alias_tag_bits, name="io_acquire_bits_acquire_alias")
        self.acquire_v_set_idx = Signal(c.idx_bits, name="io_acquire_bits_vSetIdx")
        self.victim_way = Signal(c.way_bits, name="io_victimWay")

        self.lookup_valid = [Signal(name=f"io_lookUps_{i}_info_valid") for i in range(2)]
        self.lookup_blk_paddr = [
            Signal(c.blk_paddr_bits, name=f"io_lookUps_{i}_info_bits_blkPaddr")
            for i in range(2)
        ]
        self.lookup_v_set_idx = [
            Signal(c.idx_bits, name=f"io_lookUps_{i}_info_bits_vSetIdx")
            for i in range(2)
        ]
        self.lookup_hit = [Signal(name=f"io_lookUps_{i}_hit") for i in range(2)]

        self.info_valid = Signal(name="io_resp_valid")
        self.info_blk_paddr = Signal(c.blk_paddr_bits, name="io_resp_bits_blkPaddr")
        self.info_v_set_idx = Signal(c.idx_bits, name="io_resp_bits_vSetIdx")
        self.info_way = Signal(c.way_bits, name="io_resp_bits_way")
        self.perf_latency = Signal(c.latency_bits, name="perf_latency")

    # Elaborate the request/issue/response state machine. / 实例化请求、发出和响应状态机。
    def elaborate(self, platform) -> Module:
        del platform
        m = Module()
        c = self.cfg

        valid = Signal(name="valid")
        flush_reg = Signal(name="flush_reg")
        fencei_reg = Signal(name="fencei_reg")
        issue = Signal(name="issue")
        blk_paddr = Signal(c.blk_paddr_bits, name="blkPaddr")
        v_set_idx = Signal(c.idx_bits, name="vSetIdx")
        way = Signal(c.way_bits, name="way")
        latency = Signal(c.latency_bits, name="perf_latency_reg")

        # Fetch MSHRs receive a parent-tied-low flush in the V2 closure.
        effective_flush = self.flush & (0 if self.is_fetch else 1)

        # Compare both lookup payloads in the same cycle as the request.
        for index in range(2):
            m.d.comb += self.lookup_hit[index].eq(
                valid
                & ~fencei_reg
                & ~flush_reg
                & (self.lookup_v_set_idx[index] == v_set_idx)
                & (self.lookup_blk_paddr[index] == blk_paddr)
            )

        # Expose the decoupled request readiness exactly as V2 Chisel does.
        m.d.comb += self.req_ready.eq(~valid & ~effective_flush & ~self.fencei)
        req_fire = self.req_valid & self.req_ready

        # Record fence/flush before accepting a new request.
        with m.If(self.fencei | effective_flush):
            m.d.sync += [fencei_reg.eq(1), flush_reg.eq(1)]
            with m.If(~issue):
                m.d.sync += valid.eq(0)

        # Capture a miss request and clear stale control latches.
        with m.If(req_fire):
            m.d.sync += [
                valid.eq(1),
                flush_reg.eq(0),
                fencei_reg.eq(0),
                issue.eq(0),
                blk_paddr.eq(self.req_blk_paddr),
                v_set_idx.eq(self.req_v_set_idx),
            ]

        # Form the TileLink Get-like request while the entry is unissued.
        m.d.comb += [
            self.acquire_valid.eq(
                valid
                & ~issue
                & ~effective_flush
                & ~self.fencei
                & ~self.wfi_req
            ),
            self.acquire_opcode.eq(4),
            self.acquire_size.eq(c.block_off_bits),
            self.acquire_source.eq(self.entry_id),
            self.acquire_address.eq(blk_paddr << c.block_off_bits),
            self.acquire_v_set_idx.eq(v_set_idx),
        ]
        if c.alias_tag_bits:
            m.d.comb += self.acquire_alias_tag.eq(
                v_set_idx[c.idx_bits - c.alias_tag_bits : c.idx_bits]
            )
        else:
            m.d.comb += self.acquire_alias_tag.eq(0)
        acquire_fire = self.acquire_valid & self.acquire_ready

        # Latch the victim and start the response-latency counter on fire.
        with m.If(acquire_fire):
            m.d.sync += [issue.eq(1), way.eq(self.victim_way), latency.eq(0)]
        with m.If(valid & issue):
            m.d.sync += latency.eq(latency + 1)

        # The parent invalidates an entry after the final grant beat.
        with m.If(self.invalid):
            m.d.sync += valid.eq(0)

        # Keep response payload stable while valid, even when hidden by flush.
        m.d.comb += [
            self.info_valid.eq(valid & ~flush_reg & ~fencei_reg),
            self.info_blk_paddr.eq(blk_paddr),
            self.info_v_set_idx.eq(v_set_idx),
            self.info_way.eq(way),
            self.wfi_safe.eq(~(valid & issue)),
            self.perf_latency.eq(latency),
        ]
        return m


# Preserve the source-traceable candidate spelling as a distinct public type.
# 保留源代码可追溯的候选拼写，并将其作为独立公开类型。
class ICacheMshr(ICacheMSHR):
    """Source-spelled ICacheMSHR entry. / 使用候选源拼写的 ICacheMSHR 表项。"""


# Public Adapter
# ---------------------------------------------------------------------------
# Export a deterministic configured module. / 导出确定性配置模块。
def build_verilog(configuration, injected_dependencies):
    """Return Verilog for one V2 MSHR. / 返回单个 V2 MSHR 的 Verilog。"""
    from amaranth.back import verilog

    del injected_dependencies
    if isinstance(configuration, MshrConfig):
        cfg = configuration
    elif isinstance(configuration, dict):
        cfg_fields = {
            "paddr_bits",
            "block_off_bits",
            "idx_bits",
            "way_bits",
            "alias_tag_bits",
            "source_bits",
            "latency_bits",
            "block_bytes",
        }
        cfg = MshrConfig(**{key: value for key, value in configuration.items() if key in cfg_fields})
    else:
        cfg = MshrConfig()
    top = ICacheMSHR(
        entry_id=int(configuration.get("entry_id", 0)) if isinstance(configuration, dict) else 0,
        is_fetch=bool(configuration.get("is_fetch", True)) if isinstance(configuration, dict) else True,
        cfg=cfg,
    )
    ports = [
        top.fencei,
        top.flush,
        top.wfi_req,
        top.wfi_safe,
        top.invalid,
        top.req_valid,
        top.req_ready,
        top.req_blk_paddr,
        top.req_v_set_idx,
        top.acquire_ready,
        top.acquire_valid,
        top.acquire_opcode,
        top.acquire_size,
        top.acquire_source,
        top.acquire_address,
        top.acquire_alias_tag,
        top.acquire_v_set_idx,
        top.victim_way,
        top.info_valid,
        top.info_blk_paddr,
        top.info_v_set_idx,
        top.info_way,
        top.perf_latency,
    ]
    ports += top.lookup_valid + top.lookup_blk_paddr + top.lookup_v_set_idx + top.lookup_hit
    return verilog.convert(top, name="ICacheMSHR", ports=ports)


# Direct Entry
# ---------------------------------------------------------------------------
# Print the default configured export when invoked directly. / 直接调用时打印默认配置导出结果。
def main() -> None:
    """Print the default Verilog module. / 打印默认 Verilog 模块。"""
    print(build_verilog(None, None))


if __name__ == "__main__":
    main()
