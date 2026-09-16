"""UHSC source-named Kunminghu V2 root boundaries.
昆明湖 V2 源命名根层级边界。

The four classes in this aggregate make the mandatory Scala root names
explicit in the Python build inventory.  They are deliberately diagnostic
boundaries: ``closure_missing`` remains asserted until the complete child
closures and locked XSTop port inventory are connected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from amaranth import ClockDomain, Elaboratable, Module, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
__all__ = ["RootConfig", "XSCore", "L2Top", "XSTile", "XSTop", "root_closure_observation", "build_verilog", "main"]


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


def root_closure_observation(bound_children: Iterable[str], expected_children: Iterable[str],
                             inventory_ports: int, expected_inventory_ports: int) -> dict[str, int]:
    """Return explicit root child/inventory closure status. / 返回根层级显式闭包状态。"""

    expected = tuple(expected_children)
    bound = set(bound_children)
    missing_children = sum(name not in bound for name in expected)
    missing_inventory = int(inventory_ports != expected_inventory_ports)
    missing = missing_children + missing_inventory
    return {"missing_children": missing_children, "missing_inventory": missing_inventory,
            "missing_count": missing, "complete": int(missing == 0)}


# =============================================================================
# Implementation
# =============================================================================
class _RootBoundary(Elaboratable):
    """Common diagnostic surface shared by source-named V2 roots."""

    def __init__(self, configuration: RootConfig | None = None, root_name: str = "root",
                 injected_dependencies: dict[str, Any] | None = None) -> None:
        self.config = configuration or RootConfig()
        self.root_name = root_name
        deps = injected_dependencies if isinstance(injected_dependencies, dict) else {}
        c = self.config
        # Keep the reduced probe source-compatible while using the exact
        # ``clock``/``reset`` names required by the locked root inventories.
        # Hierarchical instances are still scoped by Amaranth, so this does
        # not create collisions when several roots are bound together.
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.cf_valid = Signal(c.fetch_width, name=f"{root_name}_cf_valid")
        self.mem_a_valid = Signal(name=f"{root_name}_mem_a_valid")
        self.mem_a_address = Signal(c.paddr_bits, name=f"{root_name}_mem_a_address")
        self.mem_d_valid = Signal(name=f"{root_name}_mem_d_valid")
        self.mem_d_ready = Signal(name=f"{root_name}_mem_d_ready")
        self.closure_missing = Signal(name=f"{root_name}_closure_missing")
        # Full root envelopes are installed only from explicit coordinator
        # metadata.  The target never reads the locked SV or scans files.
        self.full_port_specs: tuple[Mapping[str, Any], ...] = tuple(
            item for item in deps.get("full_port_specs", ())
            if isinstance(item, Mapping) and item.get("name")
        )
        self.full_inventory_inputs: list[Signal] = []
        self.full_inventory_outputs: list[Signal] = []
        self.full_inventory_ports: list[Signal] = []
        self.full_inventory: dict[str, Signal] = {}
        self._full_inventory_new_ids: set[int] = set()
        self._install_full_inventory(self.full_port_specs)

    def _install_full_inventory(self, specs: Iterable[Mapping[str, Any]]) -> None:
        """Create exact-name root ports from injected frozen metadata."""
        existing = {value.name: value for value in self.__dict__.values()
                    if isinstance(value, Signal) and value.name}
        for spec in specs:
            name = str(spec.get("name", ""))
            if not name or name in self.full_inventory:
                continue
            width_value = spec.get("width", "")
            width = 1
            if isinstance(width_value, str):
                text = width_value.strip()
                if text.startswith("[") and text.endswith("]") and ":" in text:
                    high, low = text[1:-1].split(":", 1)
                    try:
                        width = abs(int(high) - int(low)) + 1
                    except ValueError:
                        width = 1
            else:
                try:
                    width = int(width_value or 1)
                except (TypeError, ValueError):
                    width = 1
            width = max(1, width)
            signal = existing.get(name)
            if signal is None:
                signal = Signal(width, name=name)
                setattr(self, f"_full_inventory_{len(self.full_inventory):04d}", signal)
                self._full_inventory_new_ids.add(id(signal))
            elif len(signal) != width:
                raise ValueError(f"injected inventory width mismatch for {name}")
            self.full_inventory[name] = signal
            self.full_inventory_ports.append(signal)
            if str(spec.get("direction", "input")).lower() == "output":
                self.full_inventory_outputs.append(signal)
            else:
                self.full_inventory_inputs.append(signal)

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
        # Full-envelope outputs are deterministic tie-offs until the actual
        # XSCore/L2Top/XSTile/XSTop child closures are connected.  This is a
        # structural generation aid, never a behavioral-equivalence claim.
        for signal in self.full_inventory_outputs:
            if id(signal) in self._full_inventory_new_ids:
                m.d.comb += signal.eq(0)
        return m


class XSCore(_RootBoundary):
    """Source-named XSCore boundary; internal Frontend/Backend/LSU pending."""

    def __init__(self, configuration: RootConfig | None = None,
                 injected_dependencies: dict[str, Any] | None = None) -> None:
        super().__init__(configuration, "xs_core", injected_dependencies)


class L2Top(_RootBoundary):
    """Source-named L2Top boundary; full TL2/CHI closure pending."""

    def __init__(self, configuration: RootConfig | None = None,
                 injected_dependencies: dict[str, Any] | None = None) -> None:
        super().__init__(configuration, "l2_top", injected_dependencies)


class XSTile(_RootBoundary):
    """Source-named XSTile boundary; XSCore/L2Top child binding pending."""

    def __init__(self, configuration: RootConfig | None = None,
                 injected_dependencies: dict[str, Any] | None = None) -> None:
        super().__init__(configuration, "xs_tile", injected_dependencies)


class XSTop(_RootBoundary):
    """Source-named XSTop boundary; complete 204-port top pending."""

    def __init__(self, configuration: RootConfig | None = None,
                 injected_dependencies: dict[str, Any] | None = None) -> None:
        super().__init__(configuration, "xs_top", injected_dependencies)


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration: RootConfig | dict[str, Any] | None = None,
                  injected_dependencies: dict[str, Any] | None = None) -> str:
    deps = injected_dependencies if isinstance(injected_dependencies, dict) else {}
    if configuration is None:
        cfg = RootConfig()
    elif isinstance(configuration, RootConfig):
        cfg = configuration
    else:
        fields = RootConfig.__dataclass_fields__
        cfg = RootConfig(**{key: value for key, value in dict(configuration).items() if key in fields})
    root_name = str(configuration.get("root", "XSTop")) if isinstance(configuration, dict) else "XSTop"
    root_types = {"XSCore": XSCore, "L2Top": L2Top, "XSTile": XSTile, "XSTop": XSTop}
    root_type = root_types.get(root_name)
    if root_type is None:
        raise ValueError(f"unsupported root: {root_name}")
    top = root_type(cfg, deps)
    module_name = str(configuration.get("module", root_name)) if isinstance(configuration, dict) else root_name
    if top.full_port_specs:
        ports = list(top.full_inventory_ports)
    else:
        ports = [top.clock, top.reset, top.cf_valid, top.mem_a_valid,
                 top.mem_a_address, top.mem_d_valid, top.mem_d_ready,
                 top.closure_missing]
    return verilog.convert(top, name=module_name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    print(build_verilog())


if __name__ == "__main__":
    main()
