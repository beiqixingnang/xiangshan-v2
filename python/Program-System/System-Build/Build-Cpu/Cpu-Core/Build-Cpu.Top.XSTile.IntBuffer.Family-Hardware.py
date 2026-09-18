"""Source-backed IntBuffer family used by the bounded XSTile closure.

The pinned XiangShan V2 hierarchy contains three elaborated instances of
``utility.IntBuffer``.  Diplomacy gives each interrupt bit one scalar input
and output; this family deliberately preserves the locked instance-specific
port order while implementing the one-stage positive-reset register pipeline
visible in the reference Verilog.  XSTile/XSCore/L2Top parent integration is
kept pending by the accompanying evidence and validator.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amaranth import ClockDomain, Elaboratable, Module, Signal
from amaranth.back import verilog

__all__ = [
    "PortSpec", "COVERED_MODULES", "SOURCE_PATHS", "LOCKED_REFERENCE_SHA256",
    "LOCKED_PORT_SPECS", "PORT_SPECS", "FamilySpec", "IntBufferFamily",
    "TopXSTileIntBufferFamily", "family_spec", "build_verilog", "main",
]

COVERED_MODULES: tuple[str, ...] = ("IntBuffer", "IntBuffer_1", "IntBuffer_2")
SOURCE_PATHS: tuple[str, ...] = (
    "upstream/utility/src/main/scala/utility/IntBuffer.scala",
    "upstream/rocket-chip/src/main/scala/diplomacy/LazyModule.scala",
)
LOCKED_REFERENCE_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"


@dataclass(frozen=True)
class PortSpec:
    name: str
    direction: str
    width: int = 1


# This order is copied from validation/v2-locked-hierarchy.json and the
# extracted reference modules.  IntBuffer_2's reordered interrupt lanes are
# intentional and must not be normalized alphabetically.
LOCKED_PORT_SPECS: dict[str, tuple[PortSpec, ...]] = {
    "IntBuffer": (
        PortSpec("clock", "input"), PortSpec("reset", "input"),
        PortSpec("auto_in_0", "input"), PortSpec("auto_out_0", "output"),
    ),
    "IntBuffer_1": (
        PortSpec("clock", "input"), PortSpec("reset", "input"),
        PortSpec("auto_in_0", "input"), PortSpec("auto_in_1", "input"),
        PortSpec("auto_out_0", "output"), PortSpec("auto_out_1", "output"),
    ),
    "IntBuffer_2": (
        PortSpec("clock", "input"), PortSpec("reset", "input"),
        PortSpec("auto_in_1_0", "input"), PortSpec("auto_in_0_0", "input"),
        PortSpec("auto_out_1_0", "output"), PortSpec("auto_out_0_0", "output"),
    ),
}
PORT_SPECS = LOCKED_PORT_SPECS


class FamilySpec:
    """Immutable selected-member view of the locked port catalog."""

    def __init__(self, module: str) -> None:
        if module not in LOCKED_PORT_SPECS:
            raise ValueError(f"unknown IntBuffer member: {module}")
        self.module = module
        self.ports = LOCKED_PORT_SPECS[module]

    def width(self, name: str) -> int:
        for port in self.ports:
            if port.name == name:
                return port.width
        raise KeyError(name)


def family_spec(module: str) -> FamilySpec:
    return FamilySpec(module)


class IntBufferFamily(Elaboratable):
    """One exact IntBuffer variant with a one-cycle resettable pipeline."""

    def __init__(self, module: str = COVERED_MODULES[0]) -> None:
        self.member = module
        self.spec = family_spec(module)
        self.ports: dict[str, Signal] = {
            port.name: Signal(port.width, name=port.name) for port in self.spec.ports
        }
        self.input_names = [p.name for p in self.spec.ports if p.name.startswith("auto_in_")]
        self.output_names = [p.name for p in self.spec.ports if p.name.startswith("auto_out_")]
        self.registers = [Signal(1, name=f"REG_{index}") for index in range(len(self.input_names))]

    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        domain = ClockDomain("sync", async_reset=True)
        domain.clk = self.ports["clock"]
        domain.rst = self.ports["reset"]
        module.domains += domain
        # Source IntBuffer uses RegNextN(..., depth=1, reset=0).  The emitted
        # reference has one ADFF per scalar lane and a direct output assignment.
        for register, input_name, output_name in zip(self.registers, self.input_names, self.output_names):
            module.d.sync += register.eq(self.ports[input_name])
            module.d.comb += self.ports[output_name].eq(register)
        return module


TopXSTileIntBufferFamily = IntBufferFamily


def build_verilog(configuration: Any = None, injected_dependencies: Any = None, name: str | None = None) -> str:
    del injected_dependencies
    member = COVERED_MODULES[0]
    if isinstance(configuration, dict):
        member = str(configuration.get("module", member))
    elif isinstance(configuration, str):
        member = configuration
    elif name is not None:
        member = name
    top = IntBufferFamily(member)
    return verilog.convert(top, name=member, ports=[top.ports[p.name] for p in top.spec.ports], emit_src=False)


def main() -> None:
    print(build_verilog({"module": COVERED_MODULES[0]}, {}))


if __name__ == "__main__":
    main()
