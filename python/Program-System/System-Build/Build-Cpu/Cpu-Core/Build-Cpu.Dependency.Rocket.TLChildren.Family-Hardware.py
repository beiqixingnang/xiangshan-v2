"""Source-backed Rocket TileLink child family for TOP-L2TOP-TL2TL-003.

The selected TLXbar/TLBuffer, TLClientsMerger and BusErrorUnit children keep
their exact frozen ANSI inventories. Behavior is bounded relay only; complete
Diplomacy and the 441-port parent closure remain pending.
"""
from __future__ import annotations
import base64
import json
import re
import zlib
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, NamedTuple
from amaranth import Elaboratable, Module, Signal
from amaranth.back import verilog

__all__ = ["COVERED_MODULES", "SOURCE_PATHS", "PortSpec", "FamilySpec",
           "PORT_SPECS", "TLChildFamily", "relay_observation",
           "merge_source_ids", "bus_error_observation", "build_verilog", "main"]

COVERED_MODULES = (
    "TLXbar_7", "TLXbar_8", "TLXbar_9", "TLBuffer_27", "TLBuffer_20",
    "TLBuffer_29", "TLBuffer_22", "TLBuffer_16", "TLBuffer_2",
    "TLClientsMerger_1", "BusErrorUnit",
)
SOURCE_PATHS = {
    "TLXbar": ("upstream/rocket-chip/src/main/scala/tilelink/Xbar.scala",),
    "TLBuffer": ("upstream/rocket-chip/src/main/scala/tilelink/Buffer.scala",),
    "TLClientsMerger": ("upstream/utility/src/main/scala/utility/TLUtils/TLClientsMerger.scala",),
    "BusErrorUnit": ("upstream/rocket-chip/src/main/scala/tile/BusErrorUnit.scala",),
}

class PortSpec(NamedTuple):
    name: str
    direction: str
    width: int

_LOCKED_PORT_BLOB = "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"
_LOCKED_PORTS: dict[str, list[list[Any]]] = json.loads(
    zlib.decompress(base64.b64decode(_LOCKED_PORT_BLOB)).decode("utf-8")
)
PORT_SPECS: dict[str, tuple[PortSpec, ...]] = {
    module: tuple(PortSpec(str(name), str(direction), int(width))
                  for name, direction, width in rows)
    for module, rows in _LOCKED_PORTS.items()
}

@dataclass(frozen=True)
class FamilySpec:
    module: str
    def __post_init__(self) -> None:
        if self.module not in PORT_SPECS:
            raise ValueError(f"unknown TL child: {self.module}")
    @property
    def ports(self) -> tuple[PortSpec, ...]:
        return PORT_SPECS[self.module]
    @property
    def port_count(self) -> int:
        return len(self.ports)
    @property
    def port_bits(self) -> int:
        return sum(port.width for port in self.ports)

def _tail(name: str) -> str:
    return re.sub(r"^auto_(?:in|out)(?:_[0-9]+)?_", "", name)

class TLChildFamily(Elaboratable):
    """Exact-port bounded child relay with deterministic inactive defaults."""
    def __init__(self, module: str = COVERED_MODULES[0]) -> None:
        self.spec, self.member = FamilySpec(module), module
        self.ports = {port.name: Signal(port.width, name=port.name)
                      for port in self.spec.ports}
        for port_name, signal in self.ports.items():
            setattr(self, port_name, signal)
    def _candidates(self, output: PortSpec) -> list[Signal]:
        tail = _tail(output.name)
        return [self.ports[port.name] for port in self.spec.ports
                if port.direction == "input" and port.width == output.width
                and _tail(port.name) == tail]
    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        for output in (port for port in self.spec.ports if port.direction == "output"):
            signal, candidates = self.ports[output.name], self._candidates(output)
            if self.member == "BusErrorUnit" and output.name == "io_interrupt":
                errors = [self.ports[port.name] for port in self.spec.ports
                          if port.direction == "input" and port.name.startswith("io_errors_")
                          and port.name.endswith("_valid") and port.width == 1]
                expression: Any = errors[0] if errors else 0
                for error in errors[1:]:
                    expression = expression | error
            elif self.member == "BusErrorUnit" and output.name == "auto_in_a_ready":
                expression = 1
            elif self.member == "BusErrorUnit" and output.name == "auto_in_d_valid":
                expression = self.ports.get("auto_in_a_valid", 0)
            elif output.name.endswith("_ready"):
                expression = candidates[0] if candidates else 1
            elif output.name.endswith("_valid") and candidates:
                expression = candidates[0]
                for candidate in candidates[1:]:
                    expression = expression | candidate
            elif candidates:
                expression = candidates[0]
            else:
                expression = 0
            module.d.comb += signal.eq(expression)
        return module

def relay_observation(*, valid: bool, ready: bool, reset: bool = False) -> dict[str, int]:
    active = bool(valid) and not bool(reset)
    return {"ready": int(not bool(reset)), "valid": int(active),
            "fire": int(active and bool(ready)), "reset": int(bool(reset))}

def merge_source_ids(source_ids: Iterable[int], *,
                     starts: Iterable[int] | None = None) -> dict[str, Any]:
    values = tuple(int(value) for value in source_ids)
    if any(value < 0 for value in values):
        raise ValueError("source ids must be non-negative")
    starts_tuple = values if starts is None else tuple(int(value) for value in starts)
    if len(starts_tuple) != len(values):
        raise ValueError("starts/source_ids length mismatch")
    lo = min(starts_tuple, default=0)
    hi = max((start + size for start, size in zip(starts_tuple, values)), default=0)
    return {"min_id": lo, "max_id": hi, "source_id_width": max(0, hi - lo),
            "client_count": len(values)}

def bus_error_observation(error_valid: Iterable[bool], enabled: Iterable[bool],
                          global_interrupt: Iterable[bool],
                          local_interrupt: Iterable[bool]) -> dict[str, int]:
    errors = tuple(bool(value) for value in error_valid)
    enables = tuple(bool(value) for value in enabled)
    globals_ = tuple(bool(value) for value in global_interrupt)
    locals_ = tuple(bool(value) for value in local_interrupt)
    if not (len(errors) == len(enables) == len(globals_) == len(locals_)):
        raise ValueError("BusErrorUnit vectors must have equal length")
    pending = tuple(error and enable for error, enable in zip(errors, enables))
    return {
        "cause_valid": int(any(pending)),
        "cause": next((index for index, value in enumerate(pending) if value), 0),
        "global_interrupt": int(any(error and enable and gen
                                    for error, enable, gen
                                    in zip(errors, enables, globals_))),
        "local_interrupt": int(any(error and enable and local
                                   for error, enable, local
                                   in zip(errors, enables, locals_))),
    }

def build_verilog(configuration: Any,
                  injected_dependencies: Any) -> str:
    del injected_dependencies
    member = COVERED_MODULES[0]
    if isinstance(configuration, Mapping):
        member = str(configuration.get("module", configuration.get("name", member)))
    elif isinstance(configuration, str):
        member = configuration
    family = TLChildFamily(member)
    return verilog.convert(family, name=member,
                           ports=[family.ports[port.name] for port in family.spec.ports],
                           emit_src=False)

def main() -> None:
    print(build_verilog({"module": COVERED_MODULES[0]}, {}))

if __name__ == "__main__":
    main()
