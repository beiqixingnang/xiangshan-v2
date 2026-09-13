"""Mask-destination tail-agnostic fill unit (Mgtu)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from amaranth import Elaboratable, Module, Mux, Signal


# =============================================================================
# Module Contract
# =============================================================================
# For every destination bit i, output vd[i] equals input vd[i] while i < vl;
# tail bits are forced to one. This is the exact Mgtu.scala behavior and does
# not depend on vta.
__all__ = ["MgtuConfig", "Mgtu", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class MgtuConfig:
    vlen: int = 128


# =============================================================================
# Implementation
# =============================================================================
class Mgtu(Elaboratable):
    """Fill destination tail bits with ones."""

    def __init__(self, configuration: MgtuConfig | None = None):
        config = configuration or MgtuConfig()
        if config.vlen < 1:
            raise ValueError("vlen must be positive")
        self.config = config
        self.in_vd = Signal(config.vlen, name="io_in_vd")
        self.in_vl = Signal(8, name="io_in_vl")
        self.out_vd = Signal(config.vlen, name="io_out_vd")

    def elaborate(self, platform):
        module = Module()
        for index in range(self.config.vlen):
            module.d.comb += cast(Any, self.out_vd[index]).eq(
                Mux(index < self.in_vl, self.in_vd[index], 1))
        return module


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration: MgtuConfig | None = None,
                  injected_dependencies: dict | None = None,
                  name: str = "Mgtu") -> str:
    """Emit deterministic Verilog for Mgtu."""

    del injected_dependencies
    from amaranth.back import verilog
    top = Mgtu(configuration)
    return verilog.convert(top, name=name,
                           ports=[top.in_vd, top.in_vl, top.out_vd], emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    print(build_verilog())


if __name__ == "__main__":
    main()
