"""Per-set replacement-state register bank."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from amaranth import Array, Elaboratable, Module, Signal


# =============================================================================
# Module Contract
# =============================================================================
# Reads are combinational. Valid writes update state on the active edge; when
# multiple ports write one set, the higher physical port has priority, matching
# the ordered Chisel ``when`` assignments.
__all__ = ["ReplacerStateConfig", "ReplacerState", "ReplacerStateGen",
           "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class ReplacerStateConfig:
    numSets: int = 64
    stateBits: int = 3
    numExtraReadPort: int = 1
    numExtraWritePort: int = 0


# =============================================================================
# Implementation
# =============================================================================
class ReplacerState(Elaboratable):
    """Register bank with two base and configurable extra ports."""

    def __init__(self, configuration: ReplacerStateConfig | None = None):
        config = configuration or ReplacerStateConfig()
        if config.numSets < 1 or config.stateBits < 1:
            raise ValueError("numSets and stateBits must be positive")
        if config.numExtraReadPort < 0 or config.numExtraWritePort < 0:
            raise ValueError("extra port counts cannot be negative")
        self.config = config
        index_width = max(1, (config.numSets - 1).bit_length())
        reads = 2 + config.numExtraReadPort
        writes = 2 + config.numExtraWritePort
        self.read_setIdx = [Signal(index_width, name=f"io_read_{i}_setIdx") for i in range(reads)]
        self.read_state = [Signal(config.stateBits, name=f"io_read_{i}_state") for i in range(reads)]
        self.write_valid = [Signal(name=f"io_write_{i}_valid") for i in range(writes)]
        self.write_setIdx = [Signal(index_width, name=f"io_write_{i}_bits_setIdx") for i in range(writes)]
        self.write_state = [Signal(config.stateBits, name=f"io_write_{i}_bits_state") for i in range(writes)]
        self.states = [Signal(config.stateBits, name=f"states_{i}", reset=0)
                       for i in range(config.numSets)]

    def elaborate(self, platform):
        module = Module()
        states = Array(self.states)
        for index in range(len(self.read_setIdx)):
            module.d.comb += self.read_state[index].eq(states[self.read_setIdx[index]])
        for index in range(len(self.write_valid)):
            with cast(Any, module.If(self.write_valid[index])):
                module.d.sync += states[self.write_setIdx[index]].eq(self.write_state[index])
        return module


ReplacerStateGen = ReplacerState


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration: ReplacerStateConfig | None = None,
                  injected_dependencies: dict | None = None,
                  name: str = "ReplacerState") -> str:
    del injected_dependencies
    from amaranth.back import verilog
    top = ReplacerState(configuration)
    ports = (top.read_setIdx + top.read_state + top.write_valid +
             top.write_setIdx + top.write_state)
    return verilog.convert(top, name=name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    print(build_verilog())


if __name__ == "__main__":
    main()
