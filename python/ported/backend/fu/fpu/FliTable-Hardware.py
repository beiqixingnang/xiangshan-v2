"""FLI immediate lookup tables from the pinned XiangShan snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from amaranth import Const, Elaboratable, Module, Mux, Signal


# =============================================================================
# Module Contract
# =============================================================================
# FliTable decodes a 5-bit source into one of 32 16-bit immediate constants.
# The H/S/D tables below are copied from FliTable.scala's locked source; index
# values outside the listed table (none for the standard 32-entry tables) are
# represented by zero.  The generic table remains injectable for validation.
__all__ = ["FliTableConfig", "FliTable", "FliHTable", "FliSTable",
           "FliDTable", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class FliTableConfig:
    srcWidth: int = 5
    outWidth: int = 16
    table: tuple[int, ...] = ()


FLI_H = (
    0xBC00, 0x0400, 0x0100, 0x0200, 0x1C00, 0x2000, 0x2C00, 0x3000,
    0x3400, 0x3500, 0x3600, 0x3700, 0x3800, 0x3900, 0x3A00, 0x3B00,
    0x3C00, 0x3D00, 0x3E00, 0x3F00, 0x4000, 0x4100, 0x4200, 0x4400,
    0x4800, 0x4C00, 0x5800, 0x5C00, 0x7800, 0x7C00, 0x7C00, 0x7E00,
)
FLI_S = (
    0xBF80, 0x0080, 0x3780, 0x3800, 0x3B80, 0x3C00, 0x3D80, 0x3E00,
    0x3E80, 0x3EA0, 0x3EC0, 0x3EE0, 0x3F00, 0x3F20, 0x3F40, 0x3F60,
    0x3F80, 0x3FA0, 0x3FC0, 0x3FE0, 0x4000, 0x4020, 0x4040, 0x4080,
    0x4100, 0x4180, 0x4300, 0x4380, 0x4700, 0x4780, 0x7F80, 0x7FC0,
)
FLI_D = (
    0xBFF0, 0x0010, 0x3EF0, 0x3F00, 0x3F70, 0x3F80, 0x3FB0, 0x3FC0,
    0x3FD0, 0x3FD4, 0x3FD8, 0x3FDC, 0x3FE0, 0x3FE4, 0x3FE8, 0x3FEC,
    0x3FF0, 0x3FF4, 0x3FF8, 0x3FFC, 0x4000, 0x4004, 0x4008, 0x4010,
    0x4020, 0x4030, 0x4060, 0x4070, 0x40E0, 0x40F0, 0x7FF0, 0x7FF8,
)


# =============================================================================
# Implementation
# =============================================================================
class FliTable(Elaboratable):
    """Combinational 5-bit to 16-bit table decoder."""

    def __init__(self, configuration: FliTableConfig | None = None):
        config = configuration or FliTableConfig()
        if config.srcWidth < 1 or config.outWidth < 1:
            raise ValueError("table widths must be positive")
        self.config = config
        self.src = Signal(config.srcWidth, name="src")
        self.out = Signal(config.outWidth, name="out")

    def elaborate(self, platform):
        module = Module()
        result = Const(0, self.config.outWidth)
        for index in range(1 << self.config.srcWidth):
            value = self.config.table[index] if index < len(self.config.table) else 0
            result = Mux(self.src == index, Const(value, self.config.outWidth), result)
        module.d.comb += self.out.eq(result)
        return module


class FliHTable(FliTable):
    """Half-precision FLI table."""

    def __init__(self):
        super().__init__(FliTableConfig(table=FLI_H))


class FliSTable(FliTable):
    """Single-precision FLI table."""

    def __init__(self):
        super().__init__(FliTableConfig(table=FLI_S))


class FliDTable(FliTable):
    """Double-precision FLI table."""

    def __init__(self):
        super().__init__(FliTableConfig(table=FLI_D))


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration: FliTableConfig | None = None,
                  injected_dependencies: dict | None = None,
                  name: str = "FliTable") -> str:
    """Emit deterministic Verilog for one configured FLI table."""

    del injected_dependencies
    from amaranth.back import verilog
    top = FliTable(configuration)
    return verilog.convert(top, name=name, ports=[top.src, top.out], emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    print(build_verilog())


if __name__ == "__main__":
    main()
