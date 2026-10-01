"""UHSC Kunminghu V2 root boundaries.
昆明湖 V2 根层级边界。

The four classes expose the processor-core, cache, tile, and system-top
interfaces. ``closure_missing`` remains asserted until every injected child
reports explicit completion and the complete parent wiring is present.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, cast

from amaranth import ClockDomain, Const, Elaboratable, Module, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
__all__ = [
    'RootConfig',
    'UHSCore',
    'L2Top',
    'UHSTile',
    'UHSCTop',
    'L2TOP_REQUIRED_CHILDREN',
    'l2top_closure_observation',
    'root_closure_observation',
    'build_verilog',
    'main',
]

# Local cache-parent role slots required to report pending closure.
L2TOP_REQUIRED_CHILDREN: tuple[str, ...] = (
    "tlxbar_7", "tlxbar_8", "bus_error_unit", "tlbuffer_inner_buffer",
    "tlbuffer_ptw_to_l2", "tlbuffer_i_mmio", "intbuffer", "tl2tl_parent",
    "bank_binder", "tlclients_merger", "tlxbar_9", "tlbuffer_inner_buffers",
    "tlbuffer_inner_buffers_1", "tlbuffer_inner_buffers_2", "tlbuffer_inner_buffers_3",
    "tlbuffer_inner_buffers_4", "tlbuffer_inner_buffers_5", "tlbuffer_inner_buffer_1",
    "reset_delay", "clint_time_delay",
)


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
                             inventory_ports: int, expected_inventory_ports: int,
                             child_status: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Separate bound child inventory from explicit behavioral closure.

    Binding every child and matching the port count proves wiring presence
    only. ``complete`` requires explicit COMPLETE status for each expected
    child. / 区分 child 接线和显式行为闭环；仅 child 齐全且端口数匹配只证明接线。
    """

    expected = tuple(str(name) for name in expected_children)
    bound = {str(name) for name in bound_children}
    status = child_status if isinstance(child_status, Mapping) else {}
    missing_names = tuple(name for name in expected if name not in bound)
    pending_names = tuple(
        name for name in expected
        if name in bound and str(status.get(name, "PENDING")) not in {"PASS_COMPLETE", "COMPLETE"}
    )
    missing_children = len(missing_names)
    missing_inventory = int(inventory_ports != expected_inventory_ports)
    binding_missing = missing_children + missing_inventory
    missing = binding_missing + len(pending_names)
    return {
        "expected_children": len(expected),
        "bound_children": len(expected) - missing_children,
        "missing_children": missing_children,
        "missing_child_names": list(missing_names),
        "pending_children": len(pending_names),
        "pending_child_names": list(pending_names),
        "missing_inventory": missing_inventory,
        "binding_missing_count": binding_missing,
        "binding_complete": int(binding_missing == 0),
        "missing_count": missing,
        "complete": int(missing == 0),
    }


def l2top_closure_observation(
    bound_children: Iterable[str],
    expected_children: Iterable[str] = L2TOP_REQUIRED_CHILDREN,
    inventory_ports: int = 0,
    expected_inventory_ports: int = 441,
    pending_children: Iterable[str] = (),
) -> dict[str, Any]:
    """Report cache-parent child and inventory closure.

    Presence alone is deliberately insufficient: an injected child with no
    explicit ``closure_complete`` evidence is represented in
    ``pending_children`` and keeps the result incomplete. / 报告源代码对应的
    L2Top child 与 inventory 闭环；仅有注入不够，缺少显式
    ``closure_complete`` 证据的 child 保持 pending 并令结果不完整。
    """

    expected = tuple(str(name) for name in expected_children)
    bound = {str(name) for name in bound_children}
    pending = {str(name) for name in pending_children}
    missing_names = tuple(name for name in expected if name not in bound)
    pending_names = tuple(name for name in expected if name in pending)
    missing_inventory = int(int(inventory_ports) != int(expected_inventory_ports))
    missing_count = len(missing_names) + len(pending_names) + missing_inventory
    return {
        "expected_children": len(expected),
        "bound_children": len(expected) - len(missing_names),
        "missing_children": len(missing_names),
        "pending_children": len(pending_names),
        "missing_child_names": list(missing_names),
        "pending_child_names": list(pending_names),
        "inventory_ports": int(inventory_ports),
        "expected_inventory_ports": int(expected_inventory_ports),
        "missing_inventory": missing_inventory,
        "missing_count": missing_count,
        "complete": int(missing_count == 0),
    }


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
        # Keep the reduced probe interface while using the explicit
        # ``clock``/``reset`` names in injected port inventories. Hierarchical
        # instances are scoped by Amaranth, so this does
        # not create collisions when several roots are bound together.
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.injected_dependencies = deps
        self.expected_children = tuple(str(name) for name in deps.get("expected_children", ()))
        # Machine-readable binding diagnostics are populated during
        # elaboration.  They are intentionally plain Python metadata so a
        # validator can report exact edge names without widening frozen IO.
        # 展开时填充机器可读接线诊断；保持纯 Python 元数据，不扩大冻结 IO。
        self.bound_child_edges: dict[str, list[str]] = {}
        self.missing_child_edges: dict[str, list[dict[str, str]]] = {}
        self._bound_inventory_ids: set[int] = set()
        self._verified_unsupported_pin_count = 0
        self.cf_valid = Signal(c.fetch_width, name=f"{root_name}_cf_valid")
        self.mem_a_valid = Signal(name=f"{root_name}_mem_a_valid")
        self.mem_a_address = Signal(c.paddr_bits, name=f"{root_name}_mem_a_address")
        self.mem_d_valid = Signal(name=f"{root_name}_mem_d_valid")
        self.mem_d_ready = Signal(name=f"{root_name}_mem_d_ready")
        self.closure_missing = Signal(name=f"{root_name}_closure_missing")
        # These diagnostics are intentionally internal to the compact root
        # surface unless a caller asks for them explicitly.  They let parent
        # adapters aggregate real child status without changing frozen port
        # inventories. / 这些诊断默认是 compact root 内部信号，除非调用者显式请求，
        # 因此不会改变冻结端口清单；父级可据此聚合真实 child 状态。
        self.closure_missing_count = Signal(16, name=f"{root_name}_closure_missing_count")
        self.closure_complete = Signal(name=f"{root_name}_closure_complete")
        self.child_missing = Signal(name=f"{root_name}_child_missing")
        self.verified_edge_missing_count = Signal(16, name=f"{root_name}_verified_edge_missing_count")
        # Full root envelopes are installed only from explicit port metadata.
        # The target never scans directories or discovers dependencies.
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

    @staticmethod
    def _child_signal(child: Any, name: str) -> Any:
        """Return one child Signal without guessing a concrete class. /
        按明确属性返回子级 Signal，不猜测具体实现类。
        """

        value = getattr(child, name, None) if child is not None else None
        return value if isinstance(value, Signal) else None

    def _record_edge(self, child_key: str, edge: str) -> None:
        """Record one concrete parent/child edge for evidence. / 记录具体父子边。"""

        self.bound_child_edges.setdefault(child_key, []).append(edge)

    def _register_children(self, module: Module, children: Mapping[str, Any]) -> None:
        """Install injected children without inferring signal connections. / 注册子级但不推断接线。"""

        seen: set[int] = set()
        for child_key, child in children.items():
            if child is None:
                continue
            if id(child) not in seen:
                setattr(module.submodules, f"{self.root_name}_{child_key}", child)
                seen.add(id(child))

    @staticmethod
    def _endpoint_signal(endpoint: Mapping[str, Any], parent: Any,
                         children: Mapping[str, Any]) -> Signal | None:
        """Resolve one explicit endpoint without matching names heuristically.
        解析显式 endpoint，不按相似名称猜测。
        """

        port_name = str(endpoint.get("port", ""))
        if endpoint.get("kind") == "parent":
            ports = getattr(parent, "full_inventory", {})
            signal = ports.get(port_name) if isinstance(ports, Mapping) else None
            return signal if isinstance(signal, Signal) else None
        child_key = str(endpoint.get("child", ""))
        child = children.get(child_key)
        if child is None:
            return None
        for attribute in ("full_inventory", "frontend_ports", "ports"):
            ports = getattr(child, attribute, None)
            if isinstance(ports, Mapping):
                signal = ports.get(port_name)
                if isinstance(signal, Signal):
                    return signal
        named_ports = getattr(child, "_by_name", None)
        if isinstance(named_ports, Mapping):
            signal = named_ports.get(port_name)
            if isinstance(signal, Signal):
                return signal
        for _direction, signal in getattr(child, "locked_ports", ()):
            if isinstance(signal, Signal) and signal.name == port_name:
                return signal
        return None

    def _wire_verified_pin_edges(self, module: Module, children: Mapping[str, Any]) -> None:
        """Apply validator-supplied exact, equal-width port connections.
        应用验证器提供的精确同宽端口接线。
        """

        edges = self.injected_dependencies.get("verified_pin_edges", ())
        audit = self.injected_dependencies.get("verified_pin_audit", {})
        if isinstance(audit, Mapping):
            self._verified_unsupported_pin_count += max(0, int(audit.get("unsupported_pin_count", 0)))
            if not bool(audit.get("pin_table_complete", False)):
                self._verified_unsupported_pin_count += 1

        def label(endpoint: Any) -> str:
            if not isinstance(endpoint, Mapping):
                return "<invalid-endpoint>"
            return f"{endpoint.get('child', endpoint.get('kind'))}.{endpoint.get('port')}"

        def reject(edge: Mapping[str, Any], destination: Any, reason: str) -> None:
            participants = {str(item.get("child")) for item in (edge.get("source"), destination)
                            if isinstance(item, Mapping) and item.get("kind") == "child"}
            if not participants:
                participants = {"parent"}
            issue = {"source": label(edge.get("source")), "destination": label(destination),
                     "reason": reason}
            for child_key in participants:
                self.missing_child_edges.setdefault(child_key, []).append(issue)

        if not isinstance(edges, Iterable):
            self._verified_unsupported_pin_count += 1
            return
        for edge in edges:
            if not isinstance(edge, Mapping):
                self._verified_unsupported_pin_count += 1
                continue
            source_spec = edge.get("source")
            destinations = edge.get("destinations", ())
            if not isinstance(source_spec, Mapping) or not isinstance(destinations, Iterable):
                reject(edge, None, "invalid edge record")
                continue
            source = self._endpoint_signal(source_spec, self, children)
            if source is None:
                for destination_spec in destinations:
                    reject(edge, destination_spec, "source endpoint unavailable")
                continue
            if len(source) != int(edge.get("width", len(source))):
                for destination_spec in destinations:
                    reject(edge, destination_spec, "source width differs from verified width")
                continue
            for destination_spec in destinations:
                if not isinstance(destination_spec, Mapping):
                    reject(edge, destination_spec, "invalid destination endpoint")
                    continue
                destination = self._endpoint_signal(destination_spec, self, children)
                if destination is None:
                    reject(edge, destination_spec, "destination endpoint unavailable")
                    continue
                if len(destination) != len(source):
                    reject(edge, destination_spec, "endpoint width mismatch")
                    continue
                module.d.comb += destination.eq(source)
                if destination_spec.get("kind") == "parent":
                    self._bound_inventory_ids.add(id(destination))
                source_label = label(source_spec)
                destination_label = label(destination_spec)
                child_key = str(destination_spec.get("child") or source_spec.get("child") or "parent")
                self._record_edge(child_key, f"{source_label}->{destination_label}")

    def _child_missing_term(self, child: Any, child_key: str) -> Any:
        """Resolve explicit child closure status; absent children stay missing.
        解析显式子级闭环状态；缺失子级始终保持 missing。
        """

        if child is None:
            return Const(1)
        missing = getattr(child, "closure_missing", None)
        if missing is not None:
            return Const(int(missing)) if isinstance(missing, bool) else missing
        complete = getattr(child, "closure_complete", None)
        if complete is not None:
            return Const(0 if complete else 1) if isinstance(complete, bool) else ~complete
        status = self.injected_dependencies.get("child_status", {})
        explicit_complete = status.get(child_key) in {"PASS_COMPLETE", "COMPLETE"} if isinstance(status, Mapping) else False
        closed = explicit_complete or child_key in set(self.injected_dependencies.get("closed_children", ()))
        return Const(0 if closed else 1)

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
        self.bound_child_edges = {}
        self.missing_child_edges = {}
        self._verified_unsupported_pin_count = 0
        self._bound_inventory_ids = set()
        m = Module()
        domain = ClockDomain(f"{self.root_name}_sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        setattr(m.domains, f"{self.root_name}_sync", domain)
        # Resolve explicit child slots for every root.  The earlier
        # implementation registered only tile children, so other roots looked
        # tied off even when real child objects were supplied. / 为所有 root
        # 解析显式 child slot；旧实现只注册 tile 子级，其他根即使注入真实子级也像 tie-off。
        if self.root_name == "uhs_core":
            children = getattr(self, "uhs_core_children", {})
        elif self.root_name == "uhs_tile":
            children = getattr(self, "uhstile_children", {})
        elif self.root_name == "uhsc_top":
            children = getattr(self, "uhsctop_children", {})
        else:
            children = {}
        if children:
            self._register_children(m, children)
            self._wire_verified_pin_edges(m, children)

        # Child injection remains structural until a validator supplies exact
        # width-matched pin bindings extracted from the independent edge table.
        # 子级保持结构性注入；验证器按独立 pin 边表提供精确同宽接线后才连接。

        # Explicit per-child status is the closure gate.  Presence and a few
        # bound wires never promote a bounded child to complete behavior.
        expected_port_count = {
            "uhs_core": 308, "l2_top": 441, "uhs_tile": 153, "uhsc_top": 204,
        }.get(self.root_name, 0)
        missing_terms: list[Any] = []
        child_keys = self.expected_children or tuple(children)
        for child_key in child_keys:
            missing_terms.append(self._child_missing_term(children.get(child_key), child_key))
        inventory_missing = int(len(self.full_port_specs) != expected_port_count and expected_port_count != 0)
        missing_count: Any = Const(inventory_missing, 16)
        missing_any: Any = Const(inventory_missing)
        for term in missing_terms:
            missing_count = missing_count + term
            missing_any = missing_any | (term != 0)
        if child_keys and len(children) != len(child_keys):
            # An absent slot is counted by the explicit map above; retain a
            # separate inventory diagnostic for malformed child manifests.
            missing_count = missing_count + (len(child_keys) - len(children))
            missing_any = missing_any | Const(int(len(child_keys) - len(children) > 0))
        edge_missing_count = self._verified_unsupported_pin_count + sum(
            len(edges) for edges in self.missing_child_edges.values()
        )
        missing_count = missing_count + edge_missing_count
        missing_any = missing_any | Const(int(edge_missing_count > 0))
        closure_missing_expr: Any = missing_any
        closure_count_expr: Any = missing_count
        closure_complete_expr: Any = ~missing_any if child_keys else Const(0)
        m.d.comb += [
            self.mem_a_valid.eq(self.cf_valid.any() & ~self.reset),
            self.mem_a_address.eq(0),
            self.mem_d_ready.eq(~self.reset),
            self.closure_missing.eq(closure_missing_expr),
            self.closure_missing_count.eq(closure_count_expr),
            self.closure_complete.eq(closure_complete_expr),
            self.child_missing.eq(closure_missing_expr),
            self.verified_edge_missing_count.eq(edge_missing_count),
        ]
        # Full-envelope outputs are deterministic tie-offs until the actual
        # UHSCore/L2Top/UHSTile/UHSCTop child closures are connected.  This is a
        # structural generation aid, never a behavioral-equivalence claim.
        for signal in self.full_inventory_outputs:
            if id(signal) in self._full_inventory_new_ids and id(signal) not in self._bound_inventory_ids:
                m.d.comb += signal.eq(0)
        return m


class UHSCore(_RootBoundary):
    """Localized 308-port core parent with explicit child wiring."""

    def __init__(self, configuration: RootConfig | None = None,
                 injected_dependencies: dict[str, Any] | None = None) -> None:
        super().__init__(configuration, "uhs_core", injected_dependencies)
        deps = self.injected_dependencies
        nested = deps.get("children", deps.get("uhscore_children", {}))
        if isinstance(nested, Mapping):
            deps = {**deps, **dict(nested)}
        self.uhs_core_children: dict[str, Any] = {
            "frontend": deps.get("frontend") or deps.get("Frontend"),
            "backend": deps.get("backend") or deps.get("Backend"),
            "mem_block": deps.get("mem_block") or deps.get("memblock") or deps.get("MemBlock"),
        }
        self.child_aliases = {
            key: next((alias for alias in aliases if deps.get(alias) is not None), None)
            for key, aliases in {
                "frontend": ("frontend", "Frontend"),
                "backend": ("backend", "Backend"),
                "mem_block": ("mem_block", "memblock", "MemBlock"),
            }.items()
        }


class L2Top(_RootBoundary):
    """441-port cache parent with explicit child diagnostics.

    When a validator injects a bounded CoupledL2 parent, the adapter may relay
    one A/B/C/D/E bank after supplying exact pin-edge evidence. All other
    child roles remain explicit dependency slots and pending until closure.
    """

    def __init__(self, configuration: RootConfig | None = None,
                 injected_dependencies: dict[str, Any] | None = None) -> None:
        super().__init__(configuration, "l2_top", injected_dependencies)
        deps = self.injected_dependencies
        nested = deps.get("children", deps.get("l2top_children", deps.get("child_dependencies", {})))
        if isinstance(nested, Mapping):
            # Nested children use the local role names declared at this API.
            deps = {**deps, **dict(nested)}
        self.l2top_expected_children = tuple(
            str(name) for name in deps.get("expected_children", L2TOP_REQUIRED_CHILDREN)
        )
        self.l2top_children: dict[str, Any] = {
            key: deps.get(key) for key in self.l2top_expected_children
        }
        self.tl2tl_parent = self.l2top_children.get("tl2tl_parent")
        self.l2top_bound_child_count = sum(child is not None for child in self.l2top_children.values())
        self.l2top_pending_child_count = sum(
            child is None or not hasattr(child, "closure_missing") and not hasattr(child, "closure_complete")
            for child in self.l2top_children.values()
        )
        self.l2top_child_missing_vector = Signal(
            max(1, len(self.l2top_expected_children)), name="l2_top_child_missing_vector"
        )
        self.l2top_child_missing_count = Signal(16, name="l2_top_child_missing_count")
        self.l2top_pending = Signal(name="l2_top_pending")
        self.l2top_bridge_active = Signal(name="l2_top_tl2tl_bridge_active")

    # Return a source-width-safe expression for one bridge assignment. /
    # 返回适合源/目的位宽的 bridge 赋值表达式。
    @staticmethod
    def _adapt_signal(value: Any, width: int) -> Any:
        if value is None:
            return Const(0, max(1, width))
        if len(value) != width:
            return None
        return value

    # Connect one signal while adapting widths and preserving missing lanes. /
    # 连接单个信号并适配位宽；缺失 lane 保持未连接而非伪造。
    @classmethod
    def _connect_signal(cls, module: Module, destination: Any, source: Any) -> bool:
        if destination is None or source is None:
            return False
        try:
            if len(source) != len(destination):
                return False
            module.d.comb += destination.eq(source)
            return True
        except (AttributeError, TypeError, ValueError):
            return False

    # Resolve a child closure state without inferring readiness from names. /
    # 解析 child 闭环状态，不从名称推断 ready。
    @staticmethod
    def _child_missing(child: Any, closed: bool = False) -> Any:
        if child is None:
            return Const(1)
        missing = getattr(child, "closure_missing", None)
        if missing is not None:
            return Const(int(missing)) if isinstance(missing, bool) else missing
        complete = getattr(child, "closure_complete", None)
        if complete is not None:
            return ~Const(int(complete)) if isinstance(complete, bool) else ~complete
        return Const(0 if closed else 1)

    # Elaborate the bounded cache-parent bridge and diagnostics. /
    # 展开有界缓存父级桥接与闭环诊断。
    def elaborate(self, platform: Any) -> Module:
        del platform
        self.bound_child_edges = {}
        self.missing_child_edges = {}
        self._verified_unsupported_pin_count = 0
        self._bound_inventory_ids = set()
        m = Module()
        domain = ClockDomain("l2_top_sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.l2_top_sync = domain

        # Register injected child objects without inferring clock, reset, or
        # data connections. / 注册注入子级，但不推断时钟、复位或数据接线。
        unique_children: dict[int, tuple[str, Any]] = {}
        for key, child in self.l2top_children.items():
            if child is not None:
                unique_children.setdefault(id(child), (key, child))
        for child_id, (key, child) in unique_children.items():
            del child_id
            setattr(m.submodules, f"l2top_{key}", child)
        self._wire_verified_pin_edges(m, self.l2top_children)

        # Start every source-shaped output at a deterministic quiescent value;
        # verified pin edges below drive only exact matched lanes.
        # 所有输出先保持确定静默值；下方仅由精确核验的 pin 边驱动匹配端口。
        for signal in self.full_inventory_outputs:
            if id(signal) not in self._bound_inventory_ids:
                m.d.comb += signal.eq(0)
        for index, signal in enumerate(self.full_inventory_inputs):
            sink = Signal(len(signal), name=f"l2top_input_sink_{index}")
            m.d.comb += sink.eq(signal)

        bridge_connections = sum(len(edges) for edges in self.bound_child_edges.values())

        error_address_output = getattr(self, "io_error_address", None)
        tlb_valid_output = getattr(self, "io_l2_tlb_req_req_valid", None)
        hint_valid_output = getattr(self, "io_l2_hint_valid", None)
        # Child status taps stay quiescent until their exact instance-pin edges
        # are included in a verified connection table.
        if error_address_output is not None:
            m.d.comb += cast(Any, error_address_output).eq(0)
        if tlb_valid_output is not None:
            m.d.comb += cast(Any, tlb_valid_output).eq(0)
        if hint_valid_output is not None:
            m.d.comb += cast(Any, hint_valid_output).eq(0)

        # Aggregate child status.  A child with no explicit status signal is
        # pending by definition; inventory mismatch is another independent
        # blocker. / 聚合 child 状态：没有显式状态信号的 child 按定义 pending；
        # inventory 不匹配是独立 blocker。
        missing_terms: list[Any] = []
        for index, key in enumerate(self.l2top_expected_children):
            child = self.l2top_children[key]
            closed_hint = key in set(self.injected_dependencies.get("closed_children", ()))
            term = self._child_missing(child, closed_hint)
            missing_terms.append(term)
            m.d.comb += cast(Any, self.l2top_child_missing_vector[index]).eq(term)
        missing_count: Any = Const(0, 16)
        missing_any: Any = Const(0)
        for term in missing_terms:
            missing_count = missing_count + term
            missing_any = missing_any | term
        inventory_missing = Const(int(len(self.full_port_specs) != 441))
        missing_count = missing_count + inventory_missing
        bridge_missing = Const(int(bridge_connections == 0))
        missing_count = missing_count + bridge_missing
        missing_any = missing_any | inventory_missing | bridge_missing
        edge_missing_count = self._verified_unsupported_pin_count + sum(
            len(edges) for edges in self.missing_child_edges.values()
        )
        missing_count = missing_count + edge_missing_count
        missing_any = missing_any | Const(int(edge_missing_count > 0))
        m.d.comb += [
            self.l2top_child_missing_count.eq(missing_count),
            self.l2top_pending.eq(missing_any),
            self.l2top_bridge_active.eq(int(bridge_connections > 0)),
            self.closure_missing_count.eq(missing_count),
            self.closure_missing.eq(missing_any),
            self.child_missing.eq(missing_any),
            self.closure_complete.eq(~missing_any),
            self.verified_edge_missing_count.eq(edge_missing_count),
        ]
        return m


class UHSTile(_RootBoundary):
    """Source-backed UHSTile boundary with explicit child slots. / 显式子级槽位的源代码 UHSTile 边界。"""

    def __init__(self, configuration: RootConfig | None = None,
                 injected_dependencies: dict[str, Any] | None = None) -> None:
        super().__init__(configuration, "uhs_tile", injected_dependencies)
        deps = self.injected_dependencies
        nested = deps.get("children", deps.get("uhstile_children", {}))
        if not isinstance(nested, Mapping):
            nested = {}
        merged = {**deps, **dict(nested)}
        if "expected_children" in deps:
            self.uhstile_children = {str(key): merged.get(str(key)) for key in self.expected_children}
        else:
            self.uhstile_children: dict[str, Any] = {
                "uhs_core": merged.get("uhs_core") or merged.get("core"),
                "l2_top": merged.get("l2_top") or merged.get("l2top"),
                "intbuffer": merged.get("intbuffer") or merged.get("int_buffer"),
                "intbuffer_1": merged.get("intbuffer_1") or merged.get("intBuffer_1"),
                "intbuffer_2": merged.get("intbuffer_2") or merged.get("intBuffer_2"),
                "intbuffer_3": merged.get("intbuffer_3") or merged.get("intBuffer_3") or merged.get("intbuffer_1") or merged.get("intBuffer_1"),
            }
        self.child_aliases = {
            key: next((alias for alias in aliases if merged.get(alias) is not None), None)
            for key, aliases in {
                "uhs_core": ("uhs_core", "core"),
                "l2_top": ("l2_top", "l2top"),
                "intbuffer": ("intbuffer", "int_buffer"),
                "intbuffer_1": ("intbuffer_1", "intBuffer_1"),
                "intbuffer_2": ("intbuffer_2", "intBuffer_2"),
                "intbuffer_3": ("intbuffer_3", "intBuffer_3"),
            }.items()
        }


class UHSCTop(_RootBoundary):
    """Localized 204-port system wrapper with explicit child slots."""

    def __init__(self, configuration: RootConfig | None = None,
                 injected_dependencies: dict[str, Any] | None = None) -> None:
        super().__init__(configuration, "uhsc_top", injected_dependencies)
        deps = self.injected_dependencies
        nested = deps.get("children", deps.get("system_children", {}))
        if isinstance(nested, Mapping):
            deps = {**deps, **dict(nested)}
        default_children: dict[str, Any] = {
            "soc_misc": deps.get("soc_misc") or deps.get("socMisc"),
            "xstile": deps.get("xstile") or deps.get("tile"),
            "huan_cun": deps.get("huan_cun") or deps.get("l3cacheOpt") or deps.get("HuanCun"),
            "imsic_bus_top": deps.get("imsic_bus_top") or deps.get("imsic_bus_tops"),
            "axi4_map": deps.get("axi4_map") or deps.get("map"),
            "axi4_buffer": deps.get("axi4_buffer") or deps.get("axi4buf"),
            "axi4_user_yanker": deps.get("axi4_user_yanker") or deps.get("axi4yank"),
            "tl_to_axi4": deps.get("tl_to_axi4") or deps.get("tl2axi4"),
            "tl_fragmenter": deps.get("tl_fragmenter") or deps.get("fragmenter"),
            "tl_width_widget": deps.get("tl_width_widget") or deps.get("widget"),
            "intbuffer": deps.get("intbuffer") or deps.get("intBuffer"),
            "intbuffer_1": deps.get("intbuffer_1") or deps.get("intBuffer_1"),
            "valid_io_broadcast": deps.get("valid_io_broadcast") or deps.get("broadcast"),
            "reset_gen": deps.get("reset_gen") or deps.get("reset_sync_resetSync"),
            "jtag_reset_gen": deps.get("jtag_reset_gen") or deps.get("jtag_reset_sync_resetSync"),
            "ref_reset_gen": deps.get("ref_reset_gen") or deps.get("ref_reset_sync_resetSync"),
            "async_queue_sink": deps.get("async_queue_sink") or deps.get("time_sink"),
        }
        self.uhsctop_children = (
            {str(key): deps.get(str(key)) for key in self.expected_children}
            if "expected_children" in deps else default_children
        )
        self.child_aliases = {key: key for key, child in self.uhsctop_children.items() if child is not None}


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
    root_name = str(configuration.get("root", "UHSCTop")) if isinstance(configuration, dict) else "UHSCTop"
    root_types = {"UHSCore": UHSCore, "L2Top": L2Top, "UHSTile": UHSTile, "UHSCTop": UHSCTop}
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
