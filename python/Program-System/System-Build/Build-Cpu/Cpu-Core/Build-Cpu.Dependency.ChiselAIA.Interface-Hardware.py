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
__all__ = ["AIAConfig", "UHSCAIAInterface", "AIAInterface", "aia_reference_step", "build_verilog", "main"]


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
