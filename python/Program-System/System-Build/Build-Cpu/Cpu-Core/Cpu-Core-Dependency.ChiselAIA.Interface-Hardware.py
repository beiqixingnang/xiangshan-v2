"""UHSC Kunminghu V2 ChiselAIA interrupt interface aggregate.
昆明湖 V2 ChiselAIA 中断接口聚合边界。

The selected AIA hardware-facing behavior is condensed into one CSR/register
boundary: IMSIC pending/enable, claim/complete, and APLIC source priority.
Simulation-only device models remain outside this Build target.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Mapping, cast

from amaranth import ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
__all__ = [
    "AIAConfig",
    "UHSCAIAInterface",
    "UHSCAIAImsicAXI4",
    "AIAInterface",
    "aia_reference_step",
    "imsic_axi4_reference_step",
    "build_verilog",
    "main",
]


# Cast Amaranth generator controls to the context-manager protocol. / 将 Amaranth 生成器控制转换为上下文管理器协议。
def amaranth_if(module: Module, condition: Any) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.If(condition))


# Cast an Amaranth else branch to the context-manager protocol. / 将 Amaranth else 分支转换为上下文管理器协议。
def amaranth_else(module: Module) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.Else())


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class AIAConfig:
    irq_sources: int = 64
    hart_bits: int = 6
    addr_bits: int = 32

    def __post_init__(self) -> None:
        if self.irq_sources < 1 or self.irq_sources > 1024:
            raise ValueError("irq_sources must be in [1, 1024]")
        if self.hart_bits < 1 or self.addr_bits < 12:
            raise ValueError("invalid AIA geometry")


# =============================================================================
# Implementation
# =============================================================================
def aia_reference_step(pending: int, enable: int, source: int, claim: bool, complete: bool,
                       irq_sources: int = 64) -> dict[str, int]:
    """Return one deterministic IMSIC/APLIC transaction result."""
    mask = (1 << irq_sources) - 1
    pending &= mask; enable &= mask
    source_mask = (1 << ((int(source) - 1) % irq_sources)) if source > 0 else 0
    active = pending & enable
    interrupt = int(active != 0)
    claimed = 0
    if claim and active:
        claimed = (active & -active).bit_length()
        pending &= ~(1 << (claimed - 1))
    if complete and source > 0:
        pending |= source_mask
    return {"pending": pending & mask, "active": active, "interrupt": interrupt, "claimed": claimed}


class UHSCAIAInterface(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """CSR-facing IMSIC/APLIC interrupt register boundary."""

    def __init__(self, configuration: AIAConfig | None = None) -> None:
        self.config = configuration or AIAConfig()
        c = self.config
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.csr_valid = Signal(name="io_csr_valid")
        self.csr_write = Signal(name="io_csr_write")
        self.csr_addr = Signal(c.addr_bits, name="io_csr_addr")
        self.csr_wdata = Signal(32, name="io_csr_wdata")
        self.csr_rdata = Signal(32, name="io_csr_rdata")
        self.csr_ready = Signal(name="io_csr_ready")
        self.external_source = Signal(c.irq_sources, name="io_external_source")
        self.enable = Signal(c.irq_sources, name="io_imsic_enable")
        self.pending = Signal(c.irq_sources, name="io_imsic_pending")
        self.interrupt = Signal(name="io_interrupt")
        self.claim = Signal(12, name="io_claim")

    def elaborate(self, platform: Any) -> Module:
        del platform
        c = self.config
        m = Module()
        domain = ClockDomain("aia", async_reset=True)
        domain.clk = self.clock; domain.rst = self.reset
        m.domains.aia = domain
        pending = Signal(c.irq_sources, name="aia_pending_reg")
        enable = Signal(c.irq_sources, name="aia_enable_reg")
        active = pending & enable
        # Software claim/complete writes use a compact 12-bit source ID.  A
        # write to 0x10 clears the selected pending bit (claim), while 0x14
        # re-asserts it (complete), mirroring the IMSIC hand-off semantics.
        claim_write = self.csr_valid & self.csr_write & (self.csr_addr[2:6] == 4)
        complete_write = self.csr_valid & self.csr_write & (self.csr_addr[2:6] == 5)
        claim_id = cast(Signal, self.csr_wdata[:12])
        claim_valid = (claim_id > 0) & (claim_id <= c.irq_sources)
        claim_mask = Signal(c.irq_sources, name="aia_claim_mask")
        complete_mask = Signal(c.irq_sources, name="aia_complete_mask")
        claim_decode = Const(0, c.irq_sources)
        for index in range(c.irq_sources):
            claim_decode = Mux(claim_id == index + 1, 1 << index, claim_decode)
        m.d.comb += [claim_mask.eq(Mux(claim_valid, claim_decode, 0)),
                     complete_mask.eq(Mux(claim_valid, claim_decode, 0))]
        claim_value: Any = Const(0, 12)
        seen: Any = Const(0)
        for index in range(c.irq_sources):
            claim_value = Mux(active[index] & ~seen, index + 1, claim_value)
            seen = seen | active[index]
        read_enable = enable[:32] if c.irq_sources >= 32 else enable
        read_pending = pending[:32] if c.irq_sources >= 32 else pending
        m.d.comb += [
            self.enable.eq(enable), self.pending.eq(pending), self.interrupt.eq(active != 0),
            self.claim.eq(claim_value), self.csr_ready.eq(self.csr_valid),
            self.csr_rdata.eq(Mux(self.csr_addr[4], read_pending, read_enable)),
        ]
        with amaranth_if(m, self.reset):
            m.d.aia += [pending.eq(0), enable.eq(0)]
        with amaranth_else(m):
            m.d.aia += pending.eq((pending | self.external_source | Mux(complete_write, complete_mask, 0))
                                  & ~Mux(claim_write, claim_mask, 0))
            with amaranth_if(m, self.csr_valid & self.csr_write & (self.csr_addr[4] == 0)):
                m.d.aia += enable.eq(self.csr_wdata)
            with amaranth_if(m, self.csr_valid & self.csr_write & (self.csr_addr[4] == 1) & ~claim_write & ~complete_write):
                m.d.aia += pending.eq(pending & ~self.csr_wdata)
        return m


AIAInterface = UHSCAIAInterface


# =============================================================================
# Locked XSTop IMSIC AXI4 aggregate
# =============================================================================
def imsic_axi4_reference_step(
    pending: int,
    enable: int,
    external_source: int,
    write_word: int | None = None,
    write_data: int = 0,
    read_word: int | None = None,
    irq_sources: int = 64,
) -> dict[str, int]:
    """Reference one bounded IMSIC AXI4 register transaction.

    The helper intentionally models only the source-backed register boundary;
    AXI ordering, queueing, and multi-hart parent wiring remain outside this
    family.  Word 0 is enable, word 1 clears pending bits, word 4 claims, and
    word 5 completes (re-asserts) a source.
    """

    mask = (1 << irq_sources) - 1
    pending &= mask
    enable &= mask
    pending |= external_source & mask
    if write_word == 0:
        enable = write_data & mask
    elif write_word == 1:
        pending &= ~(write_data & mask)
    elif write_word in (4, 5):
        source = write_data & 0xFFF
        if 1 <= source <= irq_sources:
            bit = 1 << (source - 1)
            if write_word == 4:
                pending &= ~bit
            else:
                pending |= bit
    active = pending & enable
    read_data = enable if read_word == 0 else pending if read_word == 1 else active
    return {
        "pending": pending & mask,
        "enable": enable & mask,
        "active": active,
        "interrupt": int(active != 0),
        "read_data": read_data & 0xFFFFFFFF,
    }


class UHSCAIAImsicAXI4(Elaboratable):
    """Source-backed IMSIC AXI4 boundary used by the locked XSTop envelope.

    This is deliberately an aggregate boundary rather than a full SoC parent:
    it exposes the exact 40 locked ``io_*``/``imsic_axi4_*`` directions and
    provides bounded single-beat AXI4-Lite-like register behavior.  Burst and
    multi-hart routing are explicit parent-closure work.
    """

    def __init__(self, configuration: AIAConfig | None = None) -> None:
        self.config = configuration or AIAConfig()
        c = self.config
        self.io_clock = Signal(name="io_clock")
        self.io_reset = Signal(name="io_reset")
        self.io_extIntrs = Signal(c.irq_sources, name="io_extIntrs")

        # AXI4 write address channel (locked XSTop direction/width contract).
        self.imsic_axi4_awready = Signal(name="imsic_axi4_awready")
        self.imsic_axi4_awvalid = Signal(name="imsic_axi4_awvalid")
        self.imsic_axi4_awid = Signal(16, name="imsic_axi4_awid")
        self.imsic_axi4_awaddr = Signal(32, name="imsic_axi4_awaddr")
        self.imsic_axi4_awlen = Signal(8, name="imsic_axi4_awlen")
        self.imsic_axi4_awsize = Signal(3, name="imsic_axi4_awsize")
        self.imsic_axi4_awburst = Signal(2, name="imsic_axi4_awburst")
        self.imsic_axi4_awlock = Signal(name="imsic_axi4_awlock")
        self.imsic_axi4_awcache = Signal(4, name="imsic_axi4_awcache")
        self.imsic_axi4_awprot = Signal(3, name="imsic_axi4_awprot")
        self.imsic_axi4_awqos = Signal(4, name="imsic_axi4_awqos")

        # AXI4 write data channel.
        self.imsic_axi4_wready = Signal(name="imsic_axi4_wready")
        self.imsic_axi4_wvalid = Signal(name="imsic_axi4_wvalid")
        self.imsic_axi4_wdata = Signal(32, name="imsic_axi4_wdata")
        self.imsic_axi4_wstrb = Signal(4, name="imsic_axi4_wstrb")
        self.imsic_axi4_wlast = Signal(name="imsic_axi4_wlast")

        # AXI4 write response channel.
        self.imsic_axi4_bready = Signal(name="imsic_axi4_bready")
        self.imsic_axi4_bvalid = Signal(name="imsic_axi4_bvalid")
        self.imsic_axi4_bid = Signal(16, name="imsic_axi4_bid")
        self.imsic_axi4_bresp = Signal(2, name="imsic_axi4_bresp")

        # AXI4 read address channel.
        self.imsic_axi4_arready = Signal(name="imsic_axi4_arready")
        self.imsic_axi4_arvalid = Signal(name="imsic_axi4_arvalid")
        self.imsic_axi4_arid = Signal(16, name="imsic_axi4_arid")
        self.imsic_axi4_araddr = Signal(32, name="imsic_axi4_araddr")
        self.imsic_axi4_arlen = Signal(8, name="imsic_axi4_arlen")
        self.imsic_axi4_arsize = Signal(3, name="imsic_axi4_arsize")
        self.imsic_axi4_arburst = Signal(2, name="imsic_axi4_arburst")
        self.imsic_axi4_arlock = Signal(name="imsic_axi4_arlock")
        self.imsic_axi4_arcache = Signal(4, name="imsic_axi4_arcache")
        self.imsic_axi4_arprot = Signal(3, name="imsic_axi4_arprot")
        self.imsic_axi4_arqos = Signal(4, name="imsic_axi4_arqos")

        # AXI4 read response channel.
        self.imsic_axi4_rready = Signal(name="imsic_axi4_rready")
        self.imsic_axi4_rvalid = Signal(name="imsic_axi4_rvalid")
        self.imsic_axi4_rid = Signal(16, name="imsic_axi4_rid")
        self.imsic_axi4_rdata = Signal(32, name="imsic_axi4_rdata")
        self.imsic_axi4_rresp = Signal(2, name="imsic_axi4_rresp")
        self.imsic_axi4_rlast = Signal(name="imsic_axi4_rlast")

        # Observable family state, useful for bounded System-Testing.
        self.imsic_enable = Signal(c.irq_sources, name="io_imsic_enable")
        self.imsic_pending = Signal(c.irq_sources, name="io_imsic_pending")
        self.interrupt = Signal(name="io_interrupt")
        self.claim = Signal(12, name="io_claim")

    def export_ports(self) -> list[Signal]:
        """Return ports in locked-header order (40 named ports)."""

        names = (
            "io_clock", "io_reset", "io_extIntrs",
            "imsic_axi4_awready", "imsic_axi4_awvalid", "imsic_axi4_awid",
            "imsic_axi4_awaddr", "imsic_axi4_awlen", "imsic_axi4_awsize",
            "imsic_axi4_awburst", "imsic_axi4_awlock", "imsic_axi4_awcache",
            "imsic_axi4_awprot", "imsic_axi4_awqos", "imsic_axi4_wready",
            "imsic_axi4_wvalid", "imsic_axi4_wdata", "imsic_axi4_wstrb",
            "imsic_axi4_wlast", "imsic_axi4_bready", "imsic_axi4_bvalid",
            "imsic_axi4_bid", "imsic_axi4_bresp", "imsic_axi4_arready",
            "imsic_axi4_arvalid", "imsic_axi4_arid", "imsic_axi4_araddr",
            "imsic_axi4_arlen", "imsic_axi4_arsize", "imsic_axi4_arburst",
            "imsic_axi4_arlock", "imsic_axi4_arcache", "imsic_axi4_arprot",
            "imsic_axi4_arqos", "imsic_axi4_rready", "imsic_axi4_rvalid",
            "imsic_axi4_rid", "imsic_axi4_rdata", "imsic_axi4_rresp",
            "imsic_axi4_rlast",
        )
        return [cast(Signal, getattr(self, name)) for name in names]

    def elaborate(self, platform: Any) -> Module:
        del platform
        c = self.config
        m = Module()
        domain = ClockDomain("aia_axi", async_reset=True)
        domain.clk = self.io_clock
        domain.rst = self.io_reset
        m.domains.aia_axi = domain

        pending = Signal(c.irq_sources, name="imsic_pending_reg")
        enable = Signal(c.irq_sources, name="imsic_enable_reg")
        aw_pending = Signal(name="imsic_aw_pending")
        w_pending = Signal(name="imsic_w_pending")
        b_valid = Signal(name="imsic_b_valid_reg")
        r_valid = Signal(name="imsic_r_valid_reg")
        aw_addr = Signal(32, name="imsic_aw_addr_reg")
        aw_id = Signal(16, name="imsic_aw_id_reg")
        w_data = Signal(32, name="imsic_w_data_reg")
        b_id = Signal(16, name="imsic_b_id_reg")
        r_id = Signal(16, name="imsic_r_id_reg")
        r_data = Signal(32, name="imsic_r_data_reg")

        active = pending & enable
        # Lowest active source is the externally visible claim ID.
        claim_value: Any = Const(0, 12)
        seen: Any = Const(0)
        for index in range(c.irq_sources):
            claim_value = Mux(active[index] & ~seen, index + 1, claim_value)
            seen = seen | active[index]

        # AXI channels are bounded to one outstanding beat.  Sideband fields
        # are accepted for contract coverage; register behavior is word based.
        m.d.comb += [
            self.imsic_axi4_awready.eq(~aw_pending & ~b_valid),
            self.imsic_axi4_wready.eq(~w_pending & ~b_valid),
            self.imsic_axi4_bvalid.eq(b_valid),
            self.imsic_axi4_bid.eq(b_id),
            self.imsic_axi4_bresp.eq(0),
            self.imsic_axi4_arready.eq(~r_valid),
            self.imsic_axi4_rvalid.eq(r_valid),
            self.imsic_axi4_rid.eq(r_id),
            self.imsic_axi4_rdata.eq(r_data),
            self.imsic_axi4_rresp.eq(0),
            self.imsic_axi4_rlast.eq(r_valid),
            self.imsic_enable.eq(enable),
            self.imsic_pending.eq(pending),
            self.interrupt.eq(active != 0),
            self.claim.eq(claim_value),
        ]

        write_fire = aw_pending & w_pending & ~b_valid
        word = aw_addr[2:6]
        write_source = cast(Signal, w_data[:12])
        write_valid_source = (write_source > 0) & (write_source <= c.irq_sources)
        write_decode = Const(0, c.irq_sources)
        for index in range(c.irq_sources):
            write_decode = Mux(write_source == index + 1, 1 << index, write_decode)

        with amaranth_if(m, self.io_reset):
            m.d.aia_axi += [
                pending.eq(0), enable.eq(0), aw_pending.eq(0), w_pending.eq(0),
                b_valid.eq(0), r_valid.eq(0), aw_addr.eq(0), aw_id.eq(0),
                w_data.eq(0), b_id.eq(0), r_id.eq(0), r_data.eq(0),
            ]
        with amaranth_else(m):
            # External APLIC sources accumulate into IMSIC pending state.
            m.d.aia_axi += pending.eq(pending | self.io_extIntrs)
            with amaranth_if(m, self.imsic_axi4_awvalid & self.imsic_axi4_awready):
                m.d.aia_axi += [aw_pending.eq(1), aw_addr.eq(self.imsic_axi4_awaddr), aw_id.eq(self.imsic_axi4_awid)]
            with amaranth_if(m, self.imsic_axi4_wvalid & self.imsic_axi4_wready):
                m.d.aia_axi += [w_pending.eq(1), w_data.eq(self.imsic_axi4_wdata)]
            with amaranth_if(m, write_fire):
                m.d.aia_axi += [aw_pending.eq(0), w_pending.eq(0), b_valid.eq(1), b_id.eq(aw_id)]
                with amaranth_if(m, word == 0):
                    m.d.aia_axi += enable.eq(w_data)
                with amaranth_if(m, word == 1):
                    m.d.aia_axi += pending.eq((pending | self.io_extIntrs) & ~w_data)
                with amaranth_if(m, (word == 4) & write_valid_source):
                    m.d.aia_axi += pending.eq((pending | self.io_extIntrs) & ~write_decode)
                with amaranth_if(m, (word == 5) & write_valid_source):
                    m.d.aia_axi += pending.eq((pending | self.io_extIntrs) | write_decode)
            with amaranth_if(m, self.imsic_axi4_bready & b_valid):
                m.d.aia_axi += b_valid.eq(0)
            with amaranth_if(m, self.imsic_axi4_arvalid & self.imsic_axi4_arready):
                m.d.aia_axi += [r_valid.eq(1), r_id.eq(self.imsic_axi4_arid)]
                with amaranth_if(m, self.imsic_axi4_araddr[4]):
                    m.d.aia_axi += r_data.eq(pending[:32])
                with amaranth_else(m):
                    m.d.aia_axi += r_data.eq(enable[:32])
            with amaranth_if(m, self.imsic_axi4_rready & r_valid):
                m.d.aia_axi += r_valid.eq(0)
        return m


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration: AIAConfig | Mapping[str, Any] | None,
                  injected_dependencies: Mapping[str, Any]) -> str:
    del injected_dependencies
    if configuration is None:
        cfg, name = AIAConfig(), "UHSCAIAInterface"
    elif isinstance(configuration, AIAConfig):
        cfg, name = configuration, "UHSCAIAInterface"
    else:
        cfg = AIAConfig(**{k: v for k, v in dict(configuration).items() if k in AIAConfig.__dataclass_fields__})
        name = str(configuration.get("module", "UHSCAIAInterface"))
    if name in {"UHSCAIAImsicAXI4", "UHSCAIAImsicAXI4Aggregate", "XSTopAIAIOAggregate"}:
        top = UHSCAIAImsicAXI4(cfg)
        ports = top.export_ports()
        # The state taps are intentionally omitted from generated top-level
        # ports; they remain available to direct Amaranth tests on the object.
    else:
        top = UHSCAIAInterface(cfg)
        ports = [top.clock, top.reset, top.csr_valid, top.csr_write, top.csr_addr, top.csr_wdata,
                 top.csr_rdata, top.csr_ready, top.external_source, top.enable, top.pending,
                 top.interrupt, top.claim]
    return verilog.convert(top, name=name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
