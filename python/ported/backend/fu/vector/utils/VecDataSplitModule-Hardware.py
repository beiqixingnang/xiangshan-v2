"""Split packed vector data into fixed-width element views."""

from __future__ import annotations

from dataclasses import dataclass
from amaranth import Elaboratable, Module, Signal


# =============================================================================
# Module Contract
# =============================================================================
# VecDataSplitModule uses Chisel asTypeOf semantics: each output vector is a
# little-endian collection of contiguous slices of the packed input. The
# reference instance has 128 input bits and emits 16/8/4/2 elements of
# 8/16/32/64 bits respectively.
__all__ = ["VecDataSplitConfig", "VecDataSplitModule", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class VecDataSplitConfig:
    inDataWidth: int = 128


# =============================================================================
# Implementation
# =============================================================================
class VecDataSplitModule(Elaboratable):
    """Expose packed input slices at 8/16/32/64-bit granularities."""

    def __init__(self, configuration: VecDataSplitConfig | None = None):
        config = configuration or VecDataSplitConfig()
        if config.inDataWidth < 64 or config.inDataWidth % 64:
            raise ValueError("inDataWidth must be a positive multiple of 64")
        self.config = config
        width = config.inDataWidth
        self.inVecData = Signal(width, name="io_inVecData")
        self.outVec8b = [Signal(8, name=f"io_outVec8b_{i}")
                         for i in range(width // 8)]
        self.outVec16b = [Signal(16, name=f"io_outVec16b_{i}")
                          for i in range(width // 16)]
        self.outVec32b = [Signal(32, name=f"io_outVec32b_{i}")
                          for i in range(width // 32)]
        self.outVec64b = [Signal(64, name=f"io_outVec64b_{i}")
                          for i in range(width // 64)]

    def elaborate(self, platform):
        module = Module()
        packed = self.inVecData
        for index, output in enumerate(self.outVec8b):
            module.d.comb += output.eq(packed.bit_select(index * 8, 8))
        for index, output in enumerate(self.outVec16b):
            module.d.comb += output.eq(packed.bit_select(index * 16, 16))
        for index, output in enumerate(self.outVec32b):
            module.d.comb += output.eq(packed.bit_select(index * 32, 32))
        for index, output in enumerate(self.outVec64b):
            module.d.comb += output.eq(packed.bit_select(index * 64, 64))
        return module


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration: VecDataSplitConfig | None = None,
                  injected_dependencies: dict | None = None,
                  name: str = "VecDataSplitModule") -> str:
    """Emit deterministic Verilog for the splitter."""

    del injected_dependencies
    from amaranth.back import verilog
    top = VecDataSplitModule(configuration)
    ports = ([top.inVecData] + top.outVec8b + top.outVec16b +
             top.outVec32b + top.outVec64b)
    return verilog.convert(top, name=name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    print(build_verilog())


if __name__ == "__main__":
    main()
