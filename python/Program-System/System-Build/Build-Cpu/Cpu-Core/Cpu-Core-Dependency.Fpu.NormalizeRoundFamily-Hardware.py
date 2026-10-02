"""Standalone CLZ and rounding primitives used by the FPU conversion paths."""

# Module Contract
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from amaranth import Cat, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog
from amaranth.hdl.ast import Value
from amaranth.lib.coding import PriorityEncoder

__all__ = [
    "COVERED_MODULES",
    "IMPLEMENTED_MEMBERS",
    "CONTRACT_ONLY_MEMBERS",
    "PORT_SPECS",
    "NormalizeRoundFamily",
    "build_verilog",
    "main",
]

# Configuration
CLZ_MEMBERS = (
    "CLZ", "CLZ_6", "CLZ_7", "CLZ_9", "CLZ_11",
    "CLZ_28", "CLZ_29", "CLZ_30", "CLZ_31",
)
ROUNDING_MEMBERS = (
    "RoundingUnit", "RoundingUnit_1", "RoundingUnit_2", "RoundingUnit_3",
    "RoundingUnit_4", "RoundingUnit_8", "RoundingUnit_9", "RoundingUnit_11",
)
COVERED_MODULES = CLZ_MEMBERS + ROUNDING_MEMBERS
IMPLEMENTED_MEMBERS = COVERED_MODULES
CONTRACT_ONLY_MEMBERS: tuple[str, ...] = ()

PortSpec = tuple[str, str, int]

CLZ_CONFIG: dict[str, tuple[int, int, bool]] = {
    "CLZ": (64, 6, False),
    "CLZ_6": (64, 7, True),
    "CLZ_7": (16, 5, True),
    "CLZ_9": (32, 6, True),
    "CLZ_11": (8, 4, True),
    "CLZ_28": (10, 4, True),
    "CLZ_29": (23, 5, True),
    "CLZ_30": (11, 4, True),
    "CLZ_31": (24, 5, True),
}
ROUNDING_CONFIG: dict[str, tuple[int, bool]] = {
    "RoundingUnit": (23, False),
    "RoundingUnit_1": (52, False),
    "RoundingUnit_2": (10, False),
    "RoundingUnit_3": (64, True),
    "RoundingUnit_4": (23, True),
    "RoundingUnit_8": (24, True),
    "RoundingUnit_9": (10, True),
    "RoundingUnit_11": (11, True),
}

PORT_SPECS: dict[str, tuple[PortSpec, ...]] = {}
for _member, (_width, _out_width, _zero_sentinel) in CLZ_CONFIG.items():
    PORT_SPECS[_member] = (("io_in", "input", _width), ("io_out", "output", _out_width))
for _member, (_width, _vector_surface) in ROUNDING_CONFIG.items():
    _inputs: tuple[PortSpec, ...] = (
        ("io_in", "input", _width),
        ("io_roundIn", "input", 1),
        ("io_stickyIn", "input", 1),
        ("io_signIn", "input", 1),
        ("io_rm", "input", 3),
    )
    if _vector_surface:
        PORT_SPECS[_member] = _inputs + (("io_inexact", "output", 1), ("io_r_up", "output", 1))
    else:
        PORT_SPECS[_member] = _inputs + (
            ("io_out", "output", _width), ("io_inexact", "output", 1), ("io_cout", "output", 1),
        )


# Implementation
class NormalizeRoundFamily(Elaboratable):
    """One exact locked CLZ or RoundingUnit module surface."""

    def __init__(self, member: str = "CLZ") -> None:
        if member not in PORT_SPECS:
            raise ValueError(f"unsupported normalize/round member: {member}")
        self.member = member
        self.specs = PORT_SPECS[member]
        self.ports = {
            name: Signal(width, name=name)
            for name, _direction, width in self.specs
        }

    def _clz(self, module: Module) -> None:
        input_width, output_width, zero_sentinel = CLZ_CONFIG[self.member]
        encoder_width = input_width + int(zero_sentinel)
        encoder = PriorityEncoder(encoder_width)
        module.submodules.encoder = encoder
        encoder_inputs: list[Value] = [Value.cast(self.ports["io_in"][input_width - bit_index - 1])
                                     for bit_index in range(input_width)]
        if zero_sentinel:
            encoder_inputs.append(Const(1, 1))
        module.d.comb += encoder.i.eq(Cat(*encoder_inputs))
        result: Value = encoder.o
        if not zero_sentinel:
            result = Mux(encoder.n, Const(input_width - 1, output_width), encoder.o)
        module.d.comb += self.ports["io_out"].eq(result)

    def _rounding(self, module: Module) -> None:
        input_width, vector_surface = ROUNDING_CONFIG[self.member]
        value = self.ports["io_in"]
        round_in = self.ports["io_roundIn"]
        sticky_in = self.ports["io_stickyIn"]
        sign_in = self.ports["io_signIn"]
        round_mode = self.ports["io_rm"]
        inexact = round_in | sticky_in
        guard = Value.cast(value[0])
        nearest_even = round_in & (sticky_in | guard)
        round_down = inexact & sign_in
        round_up = inexact & ~sign_in
        round_max_magnitude = round_in
        default_increment: Value = Const(0)
        if vector_surface:
            default_increment = Mux(round_mode == 6, inexact & ~guard, Const(0))
        increment = Mux(
            round_mode == 0,
            nearest_even,
            Mux(
                round_mode == 1,
                Const(0),
                Mux(
                    round_mode == 2,
                    round_down,
                    Mux(
                        round_mode == 3,
                        round_up,
                        Mux(
                        round_mode == 4,
                        round_max_magnitude,
                            default_increment,
                        ),
                    ),
                ),
            ),
        )
        module.d.comb += self.ports["io_inexact"].eq(inexact)
        if vector_surface:
            module.d.comb += self.ports["io_r_up"].eq(increment)
        else:
            module.d.comb += [
                self.ports["io_out"].eq(Mux(increment, value + 1, value)),
                self.ports["io_cout"].eq(increment & value.all()),
            ]

    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        if self.member in CLZ_CONFIG:
            self._clz(module)
        else:
            self._rounding(module)
        return module


# Public Adapter
def build_verilog(configuration: Any, injected_dependencies: Any) -> str:
    """Export one exact-name CLZ or rounding member."""

    del injected_dependencies
    member = "CLZ"
    if isinstance(configuration, Mapping):
        member = str(configuration.get("module", member))
    elif isinstance(configuration, str):
        member = configuration
    top = NormalizeRoundFamily(member)
    ports = [top.ports[name] for name, _direction, _width in top.specs]
    return verilog.convert(top, name=member, ports=ports, emit_src=False)


# Direct Entry
def main() -> None:
    print(build_verilog({"module": "CLZ"}, {}))


if __name__ == "__main__":
    main()
