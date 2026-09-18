"""UHSC source-named Kunminghu V2 root boundaries.
昆明湖 V2 源命名根层级边界。

The four classes in this aggregate make the mandatory Scala root names
explicit in the Python build inventory.  They are deliberately diagnostic
boundaries: ``closure_missing`` remains asserted until the complete child
closures and locked XSTop port inventory are connected.
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
    "RootConfig", "XSCore", "L2Top", "XSTile", "XSTop",
    "L2TOP_REQUIRED_CHILDREN", "L2TOP_SOURCE_SCALA_PATHS",
    "l2top_closure_observation", "root_closure_observation",
    "build_verilog", "main",
]


# The L2Top source creates these children in L2TopInlined.  Keep the list
# explicit so a validator can distinguish an absent child from a bounded
# child whose own closure is still pending. / L2TopInlined 创建以下 child；显式
# 保留清单，使验证器能区分缺失 child 与自身闭环仍 pending 的 bounded child。
L2TOP_REQUIRED_CHILDREN: tuple[str, ...] = (
    "tlxbar_7", "tlxbar_8", "bus_error_unit", "tlbuffer_inner_buffer",
    "tlbuffer_ptw_to_l2", "tlbuffer_i_mmio", "intbuffer", "tl2tl_parent",
    "bank_binder", "tlclients_merger", "tlxbar_9", "tlbuffer_inner_buffers",
    "tlbuffer_inner_buffers_1", "tlbuffer_inner_buffers_2",
    "tlbuffer_inner_buffers_3", "tlbuffer_inner_buffers_4",
    "tlbuffer_inner_buffers_5", "tlbuffer_inner_buffer_1",
    "reset_delay", "clint_time_delay",
)

# Source paths are evidence metadata only; the root build never scans or
# imports them at runtime. / 源路径仅用于证据元数据；root build 运行时不扫描或导入。
L2TOP_SOURCE_SCALA_PATHS: tuple[str, ...] = (
    "upstream/src/main/scala/xiangshan/L2Top.scala",
    "upstream/rocket-chip/src/main/scala/tilelink/Xbar.scala",
    "upstream/rocket-chip/src/main/scala/tilelink/Buffer.scala",
    "upstream/rocket-chip/src/main/scala/tilelink/BankBinder.scala",
    "upstream/utility/src/main/scala/utility/TLUtils/TLClientsMerger.scala",
    "upstream/rocket-chip/src/main/scala/tilelink/Arbiter.scala",
    "upstream/rocket-chip/src/main/scala/tilelink/Bundles.scala",
    "upstream/rocket-chip/src/main/scala/tilelink/Parameters.scala",
    "upstream/rocket-chip/src/main/scala/tilelink/Nodes.scala",
    "upstream/rocket-chip/src/main/scala/tilelink/BusWrapper.scala",
)


# Dependency aliases accepted by the source-backed L2Top adapter.  The
# validator may inject either source instance names or concise local names;
# no alias is treated as a child unless it is explicitly supplied. /
# source-backed L2Top adapter 接受 source instance 名或简短本地名；只有显式注入
# 的 alias 才算 child，不会凭名称臆造实例。
_L2TOP_CHILD_ALIASES: dict[str, tuple[str, ...]] = {
    "tlxbar_7": ("tlxbar_7", "inner_xbar", "TLXbar_7"),
    "tlxbar_8": ("tlxbar_8", "inner_xbar_1", "TLXbar_8"),
    "bus_error_unit": ("bus_error_unit", "inner_beu", "BusErrorUnit"),
    "tlbuffer_inner_buffer": ("tlbuffer_inner_buffer", "inner_buffer", "TLBuffer_27"),
    "tlbuffer_ptw_to_l2": ("tlbuffer_ptw_to_l2", "inner_ptw_to_l2_buffer", "TLBuffer_20"),
    "tlbuffer_i_mmio": ("tlbuffer_i_mmio", "inner_i_mmio_buffer", "TLBuffer_29"),
    "intbuffer": ("intbuffer", "inner_intBuffer", "IntBuffer"),
    "tl2tl_parent": ("tl2tl_parent", "coupled_l2", "l2cache", "inner_l2cache", "TL2TLCoupledL2"),
    "bank_binder": ("bank_binder", "inner_binder", "BankBinder_1"),
    "tlclients_merger": ("tlclients_merger", "inner_merger", "TLClientsMerger_1"),
    "tlxbar_9": ("tlxbar_9", "inner_xbar_2", "TLXbar_9"),
    "tlbuffer_inner_buffers": ("tlbuffer_inner_buffers", "inner_buffers", "TLBuffer_29_a"),
    "tlbuffer_inner_buffers_1": ("tlbuffer_inner_buffers_1", "inner_buffers_1", "TLBuffer_29_b"),
    "tlbuffer_inner_buffers_2": ("tlbuffer_inner_buffers_2", "inner_buffers_2", "TLBuffer_22_a"),
    "tlbuffer_inner_buffers_3": ("tlbuffer_inner_buffers_3", "inner_buffers_3", "TLBuffer_22_b"),
    "tlbuffer_inner_buffers_4": ("tlbuffer_inner_buffers_4", "inner_buffers_4", "TLBuffer_16_a"),
    "tlbuffer_inner_buffers_5": ("tlbuffer_inner_buffers_5", "inner_buffers_5", "TLBuffer_16_b"),
    "tlbuffer_inner_buffer_1": ("tlbuffer_inner_buffer_1", "inner_buffer_1", "TLBuffer_2"),
    "reset_delay": ("reset_delay", "inner_resetDelayN", "DelayN_334"),
    "clint_time_delay": ("clint_time_delay", "inner_io_clintTime_toCore_pipMod", "DelayNWithValid_203"),
}


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


def l2top_closure_observation(
    bound_children: Iterable[str],
    expected_children: Iterable[str] = L2TOP_REQUIRED_CHILDREN,
    inventory_ports: int = 0,
    expected_inventory_ports: int = 441,
    pending_children: Iterable[str] = (),
) -> dict[str, Any]:
    """Report source-backed L2Top child and inventory closure.

    Presence alone is deliberately insufficient: an injected child with no
    explicit ``closure_complete`` evidence is represented in
    ``pending_children`` and keeps the result incomplete. / 报告源代码对应的
    L2Top child 与 inventory 闭环；仅有注入不够，缺少显式
    ``closure_complete`` 证据的 child 保持 pending 并令结果不完整。
    """

    expected = tuple(str(name) for name in expected_children)
    # Accept source instance/class spellings in evidence while normalizing
    # them to the stable local child keys. / 证据可使用 source instance/class
    # 拼写，但统一为稳定的本地 child key。
    source_to_local = {
        alias: local for local, aliases in _L2TOP_CHILD_ALIASES.items()
        for alias in aliases
    }
    bound = {source_to_local.get(str(name), str(name)) for name in bound_children}
    pending = {source_to_local.get(str(name), str(name)) for name in pending_children}
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
        # Keep the reduced probe source-compatible while using the exact
        # ``clock``/``reset`` names required by the locked root inventories.
        # Hierarchical instances are still scoped by Amaranth, so this does
        # not create collisions when several roots are bound together.
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.injected_dependencies = deps
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
        self.closure_missing_count = Signal(8, name=f"{root_name}_closure_missing_count")
        self.closure_complete = Signal(name=f"{root_name}_closure_complete")
        self.child_missing = Signal(name=f"{root_name}_child_missing")
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
            self.closure_missing_count.eq(1),
            self.closure_complete.eq(0),
            self.child_missing.eq(1),
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
    """Source-backed 441-port L2Top bridge with honest child diagnostics.

    The selected DefaultConfig path is TL2TL.  When a validator injects a
    ``TL2TLCoupledL2Parent`` object, this adapter relays one bank's complete
    A/B/C/D/E path between the locked L2Top xbar and memory-facing ports.  All
    other Rocket Diplomacy children are explicit dependency slots; absent
    children, or children lacking explicit closure evidence, remain pending.
    """

    def __init__(self, configuration: RootConfig | None = None,
                 injected_dependencies: dict[str, Any] | None = None) -> None:
        super().__init__(configuration, "l2_top", injected_dependencies)
        deps = self.injected_dependencies
        nested = deps.get("children", deps.get("l2top_children", deps.get("child_dependencies", {})))
        if isinstance(nested, Mapping):
            # Nested child maps are metadata/injection conveniences only; copy
            # them into the same explicit namespace used by direct aliases.
            deps = {**deps, **dict(nested)}
        self.l2top_children: dict[str, Any] = {}
        self.l2top_child_aliases: dict[str, str | None] = {}
        for key in L2TOP_REQUIRED_CHILDREN:
            child = None
            alias_used: str | None = None
            for alias in _L2TOP_CHILD_ALIASES.get(key, (key,)):
                candidate = deps.get(alias)
                if candidate is not None:
                    child = candidate
                    alias_used = alias
                    break
            self.l2top_children[key] = child
            self.l2top_child_aliases[key] = alias_used
        # A compact parent alias is convenient for validators and is also
        # retained as a source-instance spelling for review tooling. /
        # validator 可使用 compact alias，同时保留 source instance 拼写供审查工具使用。
        self.tl2tl_parent = self.l2top_children["tl2tl_parent"]
        self.l2top_bound_child_count = sum(child is not None for child in self.l2top_children.values())
        self.l2top_pending_child_count = sum(
            child is None or not hasattr(child, "closure_missing") and not hasattr(child, "closure_complete")
            for child in self.l2top_children.values()
        )
        self.l2top_child_missing_vector = Signal(
            len(L2TOP_REQUIRED_CHILDREN), name="l2_top_child_missing_vector"
        )
        self.l2top_child_missing_count = Signal(8, name="l2_top_child_missing_count")
        self.l2top_pending = Signal(name="l2_top_pending")
        self.l2top_bridge_active = Signal(name="l2_top_tl2tl_bridge_active")

    # Return a source-width-safe expression for one bridge assignment. /
    # 返回适合源/目的位宽的 bridge 赋值表达式。
    @staticmethod
    def _adapt_signal(value: Any, width: int) -> Any:
        if value is None:
            return Const(0, max(1, width))
        source_width = len(value)
        if source_width == width:
            return value
        if source_width > width:
            return value[:width]
        return value

    # Connect one signal while adapting widths and preserving missing lanes. /
    # 连接单个信号并适配位宽；缺失 lane 保持未连接而非伪造。
    @classmethod
    def _connect_signal(cls, module: Module, destination: Any, source: Any) -> bool:
        if destination is None or source is None:
            return False
        try:
            source_width = len(source)
            destination_width = len(destination)
            if source_width < destination_width:
                from amaranth import Cat
                source = Cat(source, Const(0, destination_width - source_width))
            elif source_width > destination_width:
                source = source[:destination_width]
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

    # Elaborate the bounded source-backed L2Top bridge and diagnostics. /
    # 展开有界 source-backed L2Top bridge 与闭环诊断。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        domain = ClockDomain("l2_top_sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.l2_top_sync = domain

        # Every supplied child is a real dependency object.  We only fan out
        # clock/reset here unless the object is the selected TL2TL parent;
        # arbitrary locked modules are never replaced by tie-off stand-ins. /
        # 每个 supplied child 都是真实依赖对象；除选定 TL2TL parent 外这里只分发
        # clock/reset，绝不以 tie-off 冒充任意 locked module。
        unique_children: dict[int, tuple[str, Any]] = {}
        for key, child in self.l2top_children.items():
            if child is not None:
                unique_children.setdefault(id(child), (key, child))
        for child_id, (key, child) in unique_children.items():
            del child_id
            setattr(m.submodules, f"l2top_{key}", child)
            child_clock = getattr(child, "clock", None)
            child_reset = getattr(child, "reset", None)
            if child_clock is not None:
                self._connect_signal(m, child_clock, self.clock)
            if child_reset is not None:
                self._connect_signal(m, child_reset, self.reset)

        # Start every source-shaped output at a deterministic quiescent value;
        # explicit bridge assignments below override only lanes with a real
        # selected child. / 所有 source-shaped 输出先置为确定静默值；下方仅由真实
        # selected child 覆盖显式 bridge lane。
        for signal in self.full_inventory_outputs:
            m.d.comb += signal.eq(0)
        for index, signal in enumerate(self.full_inventory_inputs):
            sink = Signal(len(signal), name=f"l2top_input_sink_{index}")
            m.d.comb += sink.eq(signal)

        parent = self.tl2tl_parent
        bridge_connections = 0

        # Relay one source-backed TL2TL bank between the L2Top xbar input and
        # memory port.  This is intentionally bounded to bank zero; the
        # remaining bank/mux/merger behavior stays pending until child closure.
        # 将一个有源 TL2TL bank 在 L2Top xbar 输入与 memory port 之间中继；其余
        # bank/mux/merger 行为在 child 闭环前保持 pending。
        if parent is not None:
            inner = "auto_inner_xbar_in_0_"
            child_in = "auto_in_0_"
            outer = "auto_inner_memory_port_out_"
            child_out = "auto_out_0_"

            def bridge(dst_name: str, src_name: str) -> None:
                nonlocal bridge_connections
                if self._connect_signal(m, getattr(parent, dst_name, None), getattr(self, src_name, None)):
                    bridge_connections += 1

            def bridge_back(dst_name: str, src_name: str) -> None:
                nonlocal bridge_connections
                if self._connect_signal(m, getattr(self, dst_name, None), getattr(parent, src_name, None)):
                    bridge_connections += 1

            # L1/xbar -> TL2TL inner A/C/E and ready/response back. /
            # L1/xbar → TL2TL 内侧 A/C/E，并回传 ready/response。
            for channel, fields in {
                "a": ("valid", "bits_opcode", "bits_param", "bits_size", "bits_source",
                       "bits_address", "bits_user_reqSource", "bits_user_alias", "bits_user_vaddr",
                       "bits_user_needHint", "bits_echo_isKeyword", "bits_mask", "bits_data", "bits_corrupt"),
                "c": ("valid", "bits_opcode", "bits_param", "bits_size", "bits_source",
                       "bits_address", "bits_user_reqSource", "bits_user_alias", "bits_user_vaddr",
                       "bits_user_needHint", "bits_echo_isKeyword", "bits_data", "bits_corrupt"),
                "e": ("valid", "bits_sink"),
            }.items():
                for field in fields:
                    bridge(f"{child_in}{channel}_{field}", f"{inner}{channel}_{field}")
            for channel in ("a", "c", "e"):
                bridge_back(f"{inner}{channel}_ready", f"{child_in}{channel}_ready")

            # TL2TL inner B/D responses -> L2Top xbar. /
            # TL2TL 内侧 B/D 响应 → L2Top xbar。
            for channel, fields in {
                "b": ("valid", "bits_opcode", "bits_param", "bits_size", "bits_source",
                       "bits_address", "bits_mask", "bits_data", "bits_corrupt"),
                "d": ("valid", "bits_opcode", "bits_param", "bits_size", "bits_source",
                       "bits_sink", "bits_denied", "bits_echo_isKeyword", "bits_data", "bits_corrupt"),
            }.items():
                for field in fields:
                    bridge_back(f"{inner}{channel}_{field}", f"{child_in}{channel}_{field}")
            for channel in ("b", "d"):
                bridge(f"{child_in}{channel}_ready", f"{inner}{channel}_ready")

            # TL2TL outer A/C/E -> memory port and memory B/D -> TL2TL. /
            # TL2TL 外侧 A/C/E → memory port，memory B/D → TL2TL。
            for channel, fields in {
                "a": ("valid", "bits_opcode", "bits_param", "bits_size", "bits_source",
                       "bits_address", "bits_user_reqSource", "bits_echo_blockisdirty",
                       "bits_mask", "bits_data", "bits_corrupt"),
                "c": ("valid", "bits_opcode", "bits_param", "bits_size", "bits_source",
                       "bits_address", "bits_user_reqSource", "bits_echo_blockisdirty",
                       "bits_data", "bits_corrupt"),
                "e": ("valid", "bits_sink"),
            }.items():
                for field in fields:
                    bridge_back(f"{outer}{channel}_{field}", f"{child_out}{channel}_{field}")
            for channel in ("a", "c", "e"):
                bridge(f"{child_out}{channel}_ready", f"{outer}{channel}_ready")
            for field in ("valid", "bits_opcode", "bits_param", "bits_size", "bits_source",
                          "bits_address", "bits_mask", "bits_data", "bits_corrupt"):
                bridge(f"{child_out}b_{field}", f"{outer}b_{field}")
            for field in ("valid", "bits_opcode", "bits_param", "bits_size", "bits_source",
                          "bits_sink", "bits_denied", "bits_echo_blockisdirty", "bits_data", "bits_corrupt"):
                bridge(f"{child_out}d_{field}", f"{outer}d_{field}")
            bridge_back(f"{outer}b_ready", f"{child_out}b_ready")
            bridge_back(f"{outer}d_ready", f"{child_out}d_ready")

        # Source-level status taps remain explicit and quiet when no child
        # provides them. / 源级状态 tap 保持显式；无 child 提供时保持静默。
        l2_child = self.l2top_children["tl2tl_parent"]
        l2_miss = getattr(l2_child, "l2Miss", None) if l2_child is not None else None
        l2_error = getattr(l2_child, "error_valid", None) if l2_child is not None else None
        l2_miss_output = getattr(self, "io_l2Miss", None)
        l2_error_output = getattr(self, "io_error_valid", None)
        error_address_output = getattr(self, "io_error_address", None)
        tlb_valid_output = getattr(self, "io_l2_tlb_req_req_valid", None)
        hint_valid_output = getattr(self, "io_l2_hint_valid", None)
        if l2_miss is not None and l2_miss_output is not None:
            self._connect_signal(m, l2_miss_output, l2_miss)
        if l2_error is not None and l2_error_output is not None:
            self._connect_signal(m, l2_error_output, l2_error)
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
        for index, key in enumerate(L2TOP_REQUIRED_CHILDREN):
            child = self.l2top_children[key]
            closed_hint = key in set(self.injected_dependencies.get("closed_children", ()))
            term = self._child_missing(child, closed_hint)
            missing_terms.append(term)
            m.d.comb += cast(Any, self.l2top_child_missing_vector[index]).eq(term)
        missing_count: Any = Const(0, 8)
        missing_any: Any = Const(0)
        for term in missing_terms:
            missing_count = missing_count + term
            missing_any = missing_any | term
        inventory_missing = Const(int(len(self.full_port_specs) != 441))
        missing_count = missing_count + inventory_missing
        bridge_missing = Const(int(parent is None or bridge_connections == 0))
        missing_count = missing_count + bridge_missing
        missing_any = missing_any | inventory_missing | bridge_missing
        m.d.comb += [
            self.l2top_child_missing_count.eq(missing_count),
            self.l2top_pending.eq(missing_any),
            self.l2top_bridge_active.eq(int(parent is not None and bridge_connections > 0)),
            self.closure_missing_count.eq(missing_count),
            self.closure_missing.eq(missing_any),
            self.child_missing.eq(missing_any),
            self.closure_complete.eq(~missing_any),
        ]
        return m


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
