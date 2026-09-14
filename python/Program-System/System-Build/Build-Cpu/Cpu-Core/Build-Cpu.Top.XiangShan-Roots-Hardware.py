"""UHSC source-named Kunminghu V2 root boundaries.
昆明湖 V2 源命名根层级边界。

The four classes in this aggregate make the mandatory Scala root names
explicit in the Python build inventory.  They are deliberately diagnostic
boundaries: ``closure_missing`` remains asserted until the complete child
closures and locked XSTop port inventory are connected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amaranth import ClockDomain, Elaboratable, Module, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
__all__ = ["RootConfig", "XSCore", "L2Top", "XSTile", "XSTop", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class RootConfig:
    xlen: int = 64
    vaddr_bits: int = 50
    paddr_bits: int = 48
    fetch_width: int = 6

    def __post_init__(self) -> None:
        if self.xlen != 64 or self.fetch_width != 6:
            raise ValueError("Kunminghu V2 requires XLEN=64 and fetch width six")
        if self.vaddr_bits < self.paddr_bits or self.paddr_bits < 8:
            raise ValueError("address widths are inconsistent")


# =============================================================================
# Implementation
# =============================================================================
class _RootBoundary(Elaboratable):
    """Common diagnostic surface shared by source-named V2 roots."""

    def __init__(self, configuration: RootConfig | None = None, root_name: str = "root") -> None:
        self.config = configuration or RootConfig()
        self.root_name = root_name
        c = self.config
        self.clock = Signal(name=f"{root_name}_clock")
        self.reset = Signal(name=f"{root_name}_reset")
        self.cf_valid = Signal(c.fetch_width, name=f"{root_name}_cf_valid")
        self.mem_a_valid = Signal(name=f"{root_name}_mem_a_valid")
        self.mem_a_address = Signal(c.paddr_bits, name=f"{root_name}_mem_a_address")
        self.mem_d_valid = Signal(name=f"{root_name}_mem_d_valid")
        self.mem_d_ready = Signal(name=f"{root_name}_mem_d_ready")
        self.closure_missing = Signal(name=f"{root_name}_closure_missing")

    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        domain = ClockDomain(f"{self.root_name}_sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        setattr(m.domains, f"{self.root_name}_sync", domain)
        m.d.comb += [
            self.mem_a_valid.eq(self.cf_valid.any() & ~self.reset),
            self.mem_a_address.eq(0),
            self.mem_d_ready.eq(~self.reset),
            self.closure_missing.eq(1),
        ]
        return m


class XSCore(_RootBoundary):
    """Source-named XSCore boundary; internal Frontend/Backend/LSU pending."""

    def __init__(self, configuration: RootConfig | None = None) -> None:
        super().__init__(configuration, "xs_core")


class L2Top(_RootBoundary):
    """Source-named L2Top boundary; full TL2/CHI closure pending."""

    def __init__(self, configuration: RootConfig | None = None) -> None:
        super().__init__(configuration, "l2_top")


class XSTile(_RootBoundary):
    """Source-named XSTile boundary; XSCore/L2Top child binding pending."""

    def __init__(self, configuration: RootConfig | None = None) -> None:
        super().__init__(configuration, "xs_tile")


class XSTop(_RootBoundary):
    """Source-named XSTop boundary; complete 204-port top pending."""

    def __init__(self, configuration: RootConfig | None = None) -> None:
        super().__init__(configuration, "xs_top")


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration: RootConfig | dict[str, Any] | None = None,
                  injected_dependencies: dict[str, Any] | None = None) -> str:
    del injected_dependencies
    if configuration is None:
        cfg = RootConfig()
    elif isinstance(configuration, RootConfig):
        cfg = configuration
    else:
        fields = RootConfig.__dataclass_fields__
        cfg = RootConfig(**{key: value for key, value in dict(configuration).items() if key in fields})
    top = XSTop(cfg)
    return verilog.convert(top, name="XSTop", ports=[top.clock, top.reset, top.cf_valid,
                           top.mem_a_valid, top.mem_a_address, top.mem_d_valid,
                           top.mem_d_ready, top.closure_missing], emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    print(build_verilog())


if __name__ == "__main__":
    main()
