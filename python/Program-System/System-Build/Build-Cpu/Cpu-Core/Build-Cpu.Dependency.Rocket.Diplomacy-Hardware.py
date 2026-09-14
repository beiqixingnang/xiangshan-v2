"""UHSC Kunminghu V2 Rocket diplomacy aggregate.

This file condenses the reachable diplomacy support classes from rocket-chip
into one deterministic Python/Amaranth boundary.  It intentionally models the
pure contracts used by the V2 top (address sets/ranges, transfer and ID ranges,
resource bindings, lazy node graph resolution and address decoding) while
keeping Chisel elaboration and test-only helpers outside the hardware boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from amaranth import ClockDomain, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
__all__ = [
    "AddressSet", "AddressRange", "IdRange", "TransferSizes",
    "ResourcePermissions", "ResourceAddress", "ResourceBinding",
    "DiplomacyNode", "LazyModuleGraph", "DiplomacyConfig",
    "DiplomacyAddressRouter", "build_verilog", "main",
]


# Return true for powers of two used by TransferSizes. / 判断是否为传输尺寸要求的二次幂。
def _is_pow2(value: int) -> bool:
    return value > 0 and (value & (value - 1)) == 0


# =============================================================================
# Address and protocol value contracts
# =============================================================================
@dataclass(frozen=True, order=True)
class AddressRange:
    """Finite half-open address range ``[base, base + size)``."""

    base: int
    size: int

    # Validate and expose range end. / 校验并暴露范围终点。
    def __post_init__(self) -> None:
        if self.base < 0 or self.size <= 0:
            raise ValueError("AddressRange requires base >= 0 and size > 0")

    # Return one-past-the-end address. / 返回范围的尾后地址。
    @property
    def end(self) -> int:
        return self.base + self.size

    # Test complete containment. / 测试完整包含关系。
    def contains(self, other: "AddressRange") -> bool:
        return self.base <= other.base and other.end <= self.end

    # Union overlapping or adjacent ranges. / 合并重叠或相邻范围。
    def union(self, other: "AddressRange") -> "AddressRange | None":
        if self.base > other.end or other.base > self.end:
            return None
        lo, hi = min(self.base, other.base), max(self.end, other.end)
        return AddressRange(lo, hi - lo)

    # Subtract another range and return remaining fragments. / 减去范围并返回剩余片段。
    def subtract(self, other: "AddressRange") -> tuple["AddressRange", ...]:
        if other.end <= self.base or self.end <= other.base:
            return (self,)
        out: list[AddressRange] = []
        if self.base < other.base:
            out.append(AddressRange(self.base, other.base - self.base))
        if other.end < self.end:
            out.append(AddressRange(other.end, self.end - other.end))
        return tuple(out)

    # Render the rocket-chip style string. / 生成与 rocket-chip 一致的字符串。
    def __str__(self) -> str:
        return f"AddressRange(0x{self.base:x}, 0x{self.size:x})"

    # Convert a set list into sorted, unified ranges. / 将地址集合转为排序且合并的范围。
    @staticmethod
    def from_sets(sets: Iterable["AddressSet"]) -> tuple["AddressRange", ...]:
        ranges = sorted((r for s in sets for r in s.to_ranges()), key=lambda r: (r.base, -r.size))
        out: list[AddressRange] = []
        for item in ranges:
            merged = out[-1].union(item) if out else None
            if merged is not None:
                out[-1] = merged
            else:
                out.append(item)
        return tuple(out)


@dataclass(frozen=True)
class AddressSet:
    """Rocket diplomacy bit-mask address set (mask bits are don't-care)."""

    base: int
    mask: int

    # Validate alignment and non-negative base. / 校验基址对齐及非负约束。
    def __post_init__(self) -> None:
        if self.base < 0:
            raise ValueError("AddressSet base must be non-negative")
        if self.mask < -1:
            raise ValueError("AddressSet mask must be >= -1")
        if self.mask >= 0 and (self.base & self.mask):
            raise ValueError("AddressSet base must not set mask bits")

    # Test integer membership. / 测试整数地址是否属于集合。
    def contains(self, address: int) -> bool:
        return ((address ^ self.base) & ~self.mask) == 0

    # Test overlap using care bits. / 使用有效位测试集合重叠。
    def overlaps(self, other: "AddressSet") -> bool:
        return (~(self.mask | other.mask) & (self.base ^ other.base)) == 0

    # Return intersection, if any. / 返回交集（若存在）。
    def intersect(self, other: "AddressSet") -> "AddressSet | None":
        if not self.overlaps(other):
            return None
        mask = self.mask & other.mask
        base = self.base | other.base
        return AddressSet(base, mask)

    # Return alignment requirement in bytes. / 返回字节对齐要求。
    @property
    def alignment(self) -> int:
        if self.mask < 0:
            return 1
        return (self.mask + 1) & ~self.mask

    # True when represented addresses are contiguous. / 判断地址集合是否连续。
    @property
    def contiguous(self) -> bool:
        return self.mask >= 0 and self.alignment == self.mask + 1

    # True when max address is finite. / 判断最大地址是否有限。
    @property
    def finite(self) -> bool:
        return self.mask >= 0

    # Return maximum represented address. / 返回集合表示的最大地址。
    @property
    def max(self) -> int:
        if not self.finite:
            raise ValueError("infinite AddressSet has no max")
        return self.base | self.mask

    # Widen matching by ignoring additional bits. / 忽略额外位以扩大匹配范围。
    def widen(self, ignored_mask: int) -> "AddressSet":
        return AddressSet(self.base & ~ignored_mask, self.mask | ignored_mask)

    # Turn set into finite contiguous fragments. / 将集合展开为有限连续片段。
    def to_ranges(self) -> tuple[AddressRange, ...]:
        if not self.finite:
            raise ValueError("infinite AddressSet cannot be converted to ranges")
        bits = [1 << i for i in range(self.mask.bit_length()) if self.mask & (1 << i)]
        size = self.alignment
        high = self.mask & ~(size - 1)
        high_bits = [1 << i for i in range(high.bit_length()) if high & (1 << i)]
        fragments = []
        for selector in range(1 << len(high_bits)):
            offset = 0
            for index, bit in enumerate(high_bits):
                if selector & (1 << index):
                    offset |= bit
            fragments.append(AddressRange(self.base | offset, size))
        return tuple(sorted(fragments, key=lambda r: r.base))

    # Render rocket-chip style string. / 生成 rocket-chip 风格字符串。
    def __str__(self) -> str:
        return f"AddressSet(0x{self.base:x}, 0x{self.mask:x})" if self.mask >= 0 else f"AddressSet(0x{self.base:x}, ~0x{~self.mask:x})"


@dataclass(frozen=True)
class IdRange:
    """Half-open transaction ID range."""

    start: int
    end: int

    # Validate ID bounds. / 校验事务 ID 边界。
    def __post_init__(self) -> None:
        if self.start < 0 or self.end < self.start:
            raise ValueError("IdRange must satisfy 0 <= start <= end")

    # Number of IDs in range. / 返回范围中的 ID 数量。
    @property
    def size(self) -> int:
        return self.end - self.start

    # Test integer membership. / 测试整数 ID 是否属于范围。
    def contains(self, value: int | "IdRange") -> bool:
        if isinstance(value, IdRange):
            return self.start <= value.start and value.end <= self.end
        return self.start <= value < self.end

    # Test overlap. / 测试范围重叠。
    def overlaps(self, other: "IdRange") -> bool:
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True)
class TransferSizes:
    """Power-of-two transfer size interval (zero denotes none)."""

    minimum: int
    maximum: int | None = None

    # Normalize and validate transfer sizes. / 规范化并校验传输尺寸。
    def __post_init__(self) -> None:
        maximum = self.minimum if self.maximum is None else self.maximum
        object.__setattr__(self, "maximum", maximum)
        if self.minimum < 0 or maximum < 0 or self.minimum > maximum:
            raise ValueError("invalid TransferSizes interval")
        if (self.minimum and not _is_pow2(self.minimum)) or (maximum and not _is_pow2(maximum)):
            raise ValueError("TransferSizes endpoints must be powers of two")
        if maximum == 0 and self.minimum != 0:
            raise ValueError("zero maximum only allowed for (0,0)")

    # Whether no transfer is supported. / 判断是否不支持传输。
    @property
    def none(self) -> bool:
        return self.minimum == 0

    # Test a transfer size. / 测试单个传输尺寸。
    def contains(self, value: int | "TransferSizes") -> bool:
        if isinstance(value, TransferSizes):
            return value.none or (self.minimum <= value.minimum and value.maximum <= self.maximum)
        return _is_pow2(value) and self.minimum <= value <= self.maximum

    # Intersect two intervals. / 求两个传输尺寸区间交集。
    def intersect(self, other: "TransferSizes") -> "TransferSizes":
        lo, hi = max(self.minimum, other.minimum), min(self.maximum, other.maximum)
        return TransferSizes(0) if lo > hi else TransferSizes(lo, hi)

    # Compute smallest power-of-two cover interval. / 计算最小覆盖区间。
    def mincover(self, other: "TransferSizes") -> "TransferSizes":
        if self.none:
            return other
        if other.none:
            return self
        return TransferSizes(min(self.minimum, other.minimum), max(self.maximum, other.maximum))


@dataclass(frozen=True)
class ResourcePermissions:
    """DTS resource permission tuple (read/write/execute/cache/atomic)."""

    readable: bool = False
    writable: bool = False
    executable: bool = False
    cacheable: bool = False
    atomic: bool = False


@dataclass(frozen=True)
class ResourceAddress:
    """Address resource attached to a diplomacy node."""

    address: tuple[AddressSet, ...]
    permissions: ResourcePermissions = field(default_factory=ResourcePermissions)

    # Construct from one AddressSet or a sequence. / 从单个或多个 AddressSet 构造资源。
    @classmethod
    def from_value(cls, value: AddressSet | Sequence[AddressSet], permissions: ResourcePermissions | None = None) -> "ResourceAddress":
        addresses = (value,) if isinstance(value, AddressSet) else tuple(value)
        if not addresses:
            raise ValueError("resource address cannot be empty")
        return cls(addresses, permissions or ResourcePermissions())


@dataclass(frozen=True)
class ResourceBinding:
    """Deterministic resource key/value binding."""

    key: str
    value: ResourceAddress | str | int
    owner: str | None = None


# =============================================================================
# Lazy module and node graph contracts
# =============================================================================
@dataclass
class DiplomacyNode:
    """Minimal node carrying deterministic inward/outward edge metadata."""

    name: str
    role: str = "adapter"
    addresses: tuple[AddressSet, ...] = ()
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)

    # Attach one outgoing edge. / 添加一条向外连接边。
    def connect(self, target: "DiplomacyNode") -> None:
        if target.name not in self.outputs:
            self.outputs.append(target.name)
        if self.name not in target.inputs:
            target.inputs.append(self.name)


class LazyModuleGraph:
    """Deterministic graph resolver mirroring Rocket LazyModule topology."""

    # Create an empty graph. / 创建空图。
    def __init__(self) -> None:
        self.nodes: dict[str, DiplomacyNode] = {}

    # Add a node and reject duplicate names. / 添加节点并拒绝重复名称。
    def add(self, node: DiplomacyNode) -> DiplomacyNode:
        if node.name in self.nodes:
            raise ValueError(f"duplicate diplomacy node: {node.name}")
        self.nodes[node.name] = node
        return node

    # Connect existing nodes by name. / 按名称连接现有节点。
    def connect(self, source: str, target: str) -> None:
        if source not in self.nodes or target not in self.nodes:
            raise KeyError("diplomacy edge references unknown node")
        self.nodes[source].connect(self.nodes[target])

    # Return stable topological order and detect cycles. / 返回稳定拓扑序并检测环。
    def resolve(self) -> tuple[str, ...]:
        indegree = {name: len(node.inputs) for name, node in self.nodes.items()}
        ready = sorted(name for name, degree in indegree.items() if degree == 0)
        order: list[str] = []
        while ready:
            current = ready.pop(0)
            order.append(current)
            for child in sorted(self.nodes[current].outputs):
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
                    ready.sort()
        if len(order) != len(self.nodes):
            raise ValueError("diplomacy graph contains a cycle")
        return tuple(order)

    # Flatten all graph address resources. / 汇总图中所有地址资源。
    def address_map(self) -> tuple[tuple[str, AddressSet], ...]:
        return tuple((name, addr) for name in self.resolve() for addr in self.nodes[name].addresses)


# =============================================================================
# Hardware boundary
# =============================================================================
@dataclass(frozen=True)
class DiplomacyConfig:
    """Static route table used by the generated UHSC boundary."""

    address_bits: int = 48
    route_bases: tuple[int, ...] = (0x0000_0000, 0x1000_0000, 0x2000_0000, 0x3000_0000)
    route_masks: tuple[int, ...] = (0x0FFF_FFFF, 0x0FFF_FFFF, 0x0FFF_FFFF, 0x0FFF_FFFF)

    # Validate route table geometry. / 校验路由表几何参数。
    def __post_init__(self) -> None:
        if self.address_bits < 1 or len(self.route_bases) != len(self.route_masks) or not self.route_bases:
            raise ValueError("invalid diplomacy route configuration")
        if len(self.route_bases) > 16:
            raise ValueError("at most sixteen diplomacy routes are supported")
        for base, mask in zip(self.route_bases, self.route_masks):
            AddressSet(base, mask)


class DiplomacyAddressRouter(Elaboratable):
    """Ready/valid address decoder corresponding to AddressDecoder.apply."""

    # Construct router IO. / 构造路由器 IO。
    def __init__(self, configuration: DiplomacyConfig | None = None) -> None:
        self.configuration = configuration or DiplomacyConfig()
        c = self.configuration
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.input_valid = Signal(name="io_in_valid")
        self.input_ready = Signal(name="io_in_ready")
        self.input_address = Signal(c.address_bits, name="io_in_address")
        self.output_valid = Signal(name="io_out_valid")
        self.output_route = Signal(max(1, (len(c.route_bases) - 1).bit_length()), name="io_out_route")
        self.output_hit = Signal(name="io_out_hit")
        self.output_address = Signal(c.address_bits, name="io_out_address")

    # Elaborate combinational route selection with one-cycle valid pipeline. / 展开组合选路及单周期有效流水。
    def elaborate(self, platform: Any) -> Module:
        del platform
        c = self.configuration
        m = Module()
        domain = ClockDomain("diplomacy", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.diplomacy = domain
        hit_expr = 0
        route_expr = 0
        for index, (base, mask) in enumerate(zip(c.route_bases, c.route_masks)):
            care_mask = ((1 << c.address_bits) - 1) ^ mask
            hit = ((self.input_address ^ base) & care_mask) == 0
            hit_expr = hit_expr | hit
            route_expr = Mux(hit, index, route_expr)
        m.d.comb += [
            self.input_ready.eq(1),
            self.output_valid.eq(self.input_valid),
            self.output_hit.eq(hit_expr),
            self.output_route.eq(route_expr),
            self.output_address.eq(self.input_address),
        ]
        return m


# =============================================================================
# Public Adapter
# =============================================================================
# Export deterministic diplomacy Verilog. / 导出确定性的 diplomacy Verilog。
def build_verilog(configuration: DiplomacyConfig | Mapping[str, Any] | None, injected_dependencies: Mapping[str, Any]) -> str:
    """Build the UHSC diplomacy route boundary. / 构建 UHSC diplomacy 路由边界。"""
    del injected_dependencies
    if configuration is None:
        cfg, name = DiplomacyConfig(), "UHSCRocketDiplomacy"
    elif isinstance(configuration, DiplomacyConfig):
        cfg, name = configuration, "UHSCRocketDiplomacy"
    elif isinstance(configuration, Mapping):
        fields = DiplomacyConfig.__dataclass_fields__
        kwargs = {key: value for key, value in configuration.items() if key in fields}
        if "route_bases" in kwargs:
            kwargs["route_bases"] = tuple(int(x) for x in kwargs["route_bases"])
        if "route_masks" in kwargs:
            kwargs["route_masks"] = tuple(int(x) for x in kwargs["route_masks"])
        cfg, name = DiplomacyConfig(**kwargs), str(configuration.get("module", configuration.get("name", "UHSCRocketDiplomacy")))
    else:
        raise TypeError("configuration must be DiplomacyConfig, mapping, or None")
    top = DiplomacyAddressRouter(cfg)
    ports = [top.clock, top.reset, top.input_valid, top.input_ready, top.input_address,
             top.output_valid, top.output_route, top.output_hit, top.output_address]
    return verilog.convert(top, name=name, ports=ports, emit_src=False)


# Print deterministic direct export. / 打印确定性的 direct 导出。
def main() -> None:
    """Emit default diplomacy Verilog. / 输出默认 diplomacy Verilog。"""
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
