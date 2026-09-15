"""UHSC Kunminghu V2 Rocket diplomacy aggregate.
昆明湖 V2 Rocket diplomacy 聚合边界。

This file condenses the reachable diplomacy support classes from rocket-chip
into one deterministic Python/Amaranth boundary.  It intentionally models the
pure contracts used by the V2 top (address sets/ranges, transfer and ID ranges,
resource bindings, lazy node graph resolution and address decoding) while
keeping Chisel elaboration and test-only helpers outside the hardware boundary.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import total_ordering
from typing import Any, ClassVar, Iterable, Mapping, Sequence

from amaranth import ClockDomain, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
__all__ = [
    "AddressSet", "AddressRange", "AddressMapEntry", "IdRange", "TransferSizes",
    "ResourcePermissions", "ResourceAddress", "ResourceMapping", "ResourceString",
    "ResourceInt", "ResourceReference", "ResourceAlias", "ResourceMap", "ResourceBinding",
    "ResourceBindings", "BufferParams", "CreditedDelay", "AsyncQueueParams",
    "DiplomacyNode", "LazyModuleGraph", "ClockCrossingType", "NoCrossing",
    "SynchronousCrossing", "RationalCrossing", "AsynchronousCrossing", "CreditedCrossing",
    "DiplomacyConfig", "DiplomacyAddressRouter", "DiplomacyRouter", "UHSCRocketDiplomacy",
    "address_decoder", "AddressDecoder", "build_verilog", "main",
]


# =============================================================================
# Configuration
# =============================================================================
# The aggregate keeps immutable metadata contracts separate from generated RTL.
# 聚合边界将不可变元数据契约与生成 RTL 分离。


# Return true for powers of two used by TransferSizes. / 判断是否为传输尺寸要求的二次幂。
def _is_pow2(value: int) -> bool:
    return value > 0 and (value & (value - 1)) == 0


# Enumerate set bits from least significant to most significant. / 从最低有效位
# 到最高有效位枚举置位比特。 /
def _enumerate_bits(mask: int) -> tuple[int, ...]:
    if mask < 0:
        raise ValueError("bit enumeration requires a non-negative mask")
    bits: list[int] = []
    remaining = mask
    while remaining:
        bit = remaining & -remaining
        bits.append(bit)
        remaining &= ~bit
    return tuple(bits)


# Address and protocol value contracts are the immutable metadata layer used
# by the selected Rocket diplomacy boundary. / 地址和协议值契约构成选定 Rocket
# diplomacy 边界使用的不可变元数据层。


@total_ordering
@dataclass(frozen=True, order=False)
class AddressRange:
    """Finite half-open address range ``[base, base + size)``."""

    base: int
    size: int

    # Validate range geometry. / 校验范围几何参数。
    def __post_init__(self) -> None:
        if not isinstance(self.base, int) or not isinstance(self.size, int):
            raise TypeError("AddressRange base and size must be integers")
        if self.base < 0 or self.size <= 0:
            raise ValueError("AddressRange requires base >= 0 and size > 0")

    # Return one-past-the-end address. / 返回范围的尾后地址。
    @property
    def end(self) -> int:
        return self.base + self.size

    # Match Rocket's base-then-largest-size ordering. / 匹配 Rocket 的基址优先、
    # 同基址时大范围优先排序。 /
    def __lt__(self, other: object) -> bool:
        if not isinstance(other, AddressRange):
            return NotImplemented
        return (self.base, -self.size) < (other.base, -other.size)

    # Return Rocket's three-way comparison result. / 返回 Rocket 风格三向比较结果。
    def compare(self, other: "AddressRange") -> int:
        return (self > other) - (self < other)

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

    # Render the UVM range form used by Rocket tooling. / 生成 Rocket 工具使用的
    # UVM 范围格式。 /
    def to_uvm(self) -> str:
        return f"    set_addr_range(1, 32'h{self.base:08x}, 32'h{self.end:08x});"

    # Render a compact JSON-compatible mapping. / 生成紧凑的 JSON 兼容映射。
    def to_json(self) -> dict[str, int]:
        return {"base": self.base, "max": self.end}

    # Render the original Scala JSON string form. / 生成原始 Scala JSON 字符串格式。
    def toJSON(self) -> str:
        return json.dumps(self.to_json(), ensure_ascii=False, separators=(",", ":"))

    # Preserve the camel-case UVM helper exposed by Scala tooling. / 保留 Scala 工具暴露的
    # 驼峰命名 UVM 辅助方法。
    toUVM = to_uvm

    # Convert a set list into sorted, unified ranges. / 将地址集合转为排序且合并的范围。
    @staticmethod
    def from_sets(sets: Iterable["AddressSet"]) -> tuple["AddressRange", ...]:
        ranges = sorted((r for s in sets for r in s.to_ranges()))
        out: list[AddressRange] = []
        for item in ranges:
            merged = out[-1].union(item) if out else None
            if merged is not None:
                out[-1] = merged
            else:
                out.append(item)
        return tuple(out)

    # Unify an existing range sequence. / 合并已有范围序列。
    @staticmethod
    def unify(ranges: Iterable["AddressRange"]) -> tuple["AddressRange", ...]:
        out: list[AddressRange] = []
        for item in sorted(ranges):
            merged = out[-1].union(item) if out else None
            if merged is not None:
                out[-1] = merged
            else:
                out.append(item)
        return tuple(out)

    # Subtract each range in ``take`` from ``from_ranges``. / 从范围集合中依次减去
    # take 集合中的每个范围。 /
    @staticmethod
    def subtract_all(
        from_ranges: Iterable["AddressRange"],
        take: Iterable["AddressRange"],
    ) -> tuple["AddressRange", ...]:
        remaining = tuple(from_ranges)
        for item in take:
            remaining = tuple(fragment for current in remaining for fragment in current.subtract(item))
        return remaining

    # Preserve the Scala-style constructor alias. / 保留 Scala 风格的构造别名。
    fromSets = from_sets


@total_ordering
@dataclass(frozen=True)
class AddressSet:
    """Rocket diplomacy bit-mask address set (mask bits are don't-care)."""

    base: int
    mask: int
    everything: ClassVar["AddressSet"]

    # Validate alignment and non-negative base. / 校验基址对齐及非负约束。
    def __post_init__(self) -> None:
        if not isinstance(self.base, int) or not isinstance(self.mask, int):
            raise TypeError("AddressSet base and mask must be integers")
        if self.base < 0:
            raise ValueError("AddressSet base must be non-negative")
        # Rocket permits any negative mask to represent an unbounded set.
        # Rocket 允许任意负掩码表示无界地址集合。
        if (self.base & self.mask) != 0:
            raise ValueError("AddressSet base must not set mask bits")

    # Test an integer or nested AddressSet for membership. / 测试整数或嵌套
    # AddressSet 是否属于当前集合。 /
    def contains(self, address: int | AddressSet) -> bool:
        if isinstance(address, AddressSet):
            return ((address.mask | (self.base ^ address.base)) & ~self.mask) == 0
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
        return (self.mask + 1) & ~self.mask

    # True when represented addresses are contiguous. / 判断地址集合是否连续。
    @property
    def contiguous(self) -> bool:
        return self.alignment == self.mask + 1

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
        if not isinstance(ignored_mask, int):
            raise TypeError("ignored_mask must be an integer")
        return AddressSet(self.base & ~ignored_mask, self.mask | ignored_mask)

    # Legalize an address by retaining only don't-care bits. / 通过保留可忽略位
    # 将地址规范化到集合中。 /
    def legalize(self, address: int) -> int:
        return self.base | (self.mask & address)

    # Subtract another set using Rocket's bit-enumeration construction. / 使用
    # Rocket 位枚举构造从当前集合减去另一个集合。 /
    def subtract(self, other: "AddressSet") -> tuple["AddressSet", ...]:
        remove = self.intersect(other)
        if remove is None:
            return (self,)
        if not self.finite:
            raise ValueError("cannot subtract from an infinite AddressSet")
        varying = self.mask & ~remove.mask
        return tuple(
            AddressSet(
                (remove.base ^ bit) & ~new_mask,
                new_mask,
            )
            for bit in _enumerate_bits(varying)
            for new_mask in ((self.mask & (bit - 1)) | remove.mask,)
        )

    # Turn set into finite contiguous fragments. / 将集合展开为有限连续片段。
    def to_ranges(self) -> tuple[AddressRange, ...]:
        if not self.finite:
            raise ValueError("infinite AddressSet cannot be converted to ranges")
        size = self.alignment
        high = self.mask & ~(size - 1)
        high_bits = _enumerate_bits(high)
        fragments = [
            AddressRange(self.base | sum(bit for index, bit in enumerate(high_bits) if selector & (1 << index)), size)
            for selector in range(1 << len(high_bits))
        ]
        return tuple(sorted(fragments))

    # Render rocket-chip style string. / 生成 rocket-chip 风格字符串。
    def __str__(self) -> str:
        return f"AddressSet(0x{self.base:x}, 0x{self.mask:x})" if self.mask >= 0 else f"AddressSet(0x{self.base:x}, ~0x{~self.mask:x})"

    # Compare by base and then by descending mask width, matching Rocket. /
    # 先按基址、再按掩码宽度降序比较，与 Rocket 一致。 /
    def __lt__(self, other: object) -> bool:
        if not isinstance(other, AddressSet):
            return NotImplemented
        return (self.base, -self.mask) < (other.base, -other.mask)

    # Return Rocket's three-way comparison result. / 返回 Rocket 风格三向比较结果。
    def compare(self, other: "AddressSet") -> int:
        return (self > other) - (self < other)

    # Enumerate low-order set bits for deterministic helper algorithms. / 枚举低位
    # 置位以支持确定性辅助算法。 /
    @staticmethod
    def enumerate_bits(mask: int) -> tuple[int, ...]:
        return _enumerate_bits(mask)

    # Enumerate all selectors represented by a mask. / 枚举掩码表示的全部选择器。
    @staticmethod
    def enumerate_mask(mask: int) -> tuple[int, ...]:
        if mask < 0:
            raise ValueError("mask enumeration requires a non-negative mask")
        bits = _enumerate_bits(mask)
        return tuple(sum(bit for index, bit in enumerate(bits) if selector & (1 << index))
                     for selector in range(1 << len(bits)))

    # Return a minimal aligned decomposition of an arbitrary interval. / 返回任意
    # 区间的最小对齐分解。 /
    @staticmethod
    def misaligned(base: int, size: int, tail: Sequence["AddressSet"] = ()) -> tuple["AddressSet", ...]:
        if base < 0 or size < 0:
            raise ValueError("misaligned range requires base >= 0 and size >= 0")
        result = list(tail)
        current = base
        remaining = size
        while remaining:
            base_alignment = current & -current
            size_alignment = 1 << (remaining.bit_length() - 1)
            step = size_alignment if base_alignment == 0 or base_alignment > size_alignment else base_alignment
            result.append(AddressSet(current, step - 1))
            current += step
            remaining -= step
        return tuple(result)

    # Unify pairs that differ only in one don't-care bit. / 合并仅在一个可忽略位
    # 上不同的地址集合。 /
    @staticmethod
    def unify(sets: Iterable["AddressSet"], bit: int | None = None) -> tuple["AddressSet", ...]:
        unique = tuple(dict.fromkeys(sets))
        if bit is not None:
            grouped: dict[tuple[int, int], list[AddressSet]] = {}
            for item in unique:
                grouped.setdefault((item.base & ~bit, item.mask), []).append(item)
            return tuple(
                values[0] if len(values) == 1 else AddressSet(key[0], key[1] | bit)
                for key, values in sorted(grouped.items())
            )
        bits = 0
        for item in unique:
            bits |= item.base
        result = unique
        for candidate in _enumerate_bits(bits):
            result = AddressSet.unify(result, candidate)
        return tuple(sorted(result))

    # Scala-compatible aliases for callers using the original API. / 为使用原始
    # API 的调用方提供 Scala 兼容别名。
    toRanges = to_ranges
    enumerateBits = enumerate_bits
    enumerateMask = enumerate_mask


# Match Rocket's unbounded address-set singleton. / 匹配 Rocket 的无界地址集合单例。
AddressSet.everything = AddressSet(0, -1)


@total_ordering
@dataclass(frozen=True, order=False)
class IdRange:
    """Half-open transaction ID range."""

    start: int
    end: int

    # Validate ID bounds. / 校验事务 ID 边界。
    def __post_init__(self) -> None:
        if not isinstance(self.start, int) or not isinstance(self.end, int):
            raise TypeError("IdRange bounds must be integers")
        if self.start < 0 or self.end < self.start:
            raise ValueError("IdRange must satisfy 0 <= start <= end")

    # Match Rocket's start-then-largest-range ordering. / 匹配 Rocket 的起点优先、
    # 同起点时大范围优先排序。 /
    def __lt__(self, other: object) -> bool:
        if not isinstance(other, IdRange):
            return NotImplemented
        return (self.start, -self.end) < (other.start, -other.end)

    # Return Rocket's three-way comparison result. / 返回 Rocket 风格三向比较结果。
    def compare(self, other: "IdRange") -> int:
        return (self > other) - (self < other)

    # Number of IDs in range. / 返回范围中的 ID 数量。
    @property
    def size(self) -> int:
        return self.end - self.start

    # Test integer membership. / 测试整数 ID 是否属于范围。
    def contains(self, value: int | IdRange) -> bool:
        if isinstance(value, IdRange):
            return self.start <= value.start and value.end <= self.end
        return self.start <= value < self.end

    # Test overlap. / 测试范围重叠。
    def overlaps(self, other: "IdRange") -> bool:
        return self.start < other.end and other.start < self.end

    # Shift both bounds by a signed offset. / 将两个边界按有符号偏移移动。
    def shift(self, offset: int) -> "IdRange":
        return IdRange(self.start + offset, self.end + offset)

    # Return whether this half-open range is empty. / 判断半开区间是否为空。
    @property
    def is_empty(self) -> bool:
        return self.end == self.start

    # Enumerate the represented integer IDs. / 枚举范围表示的整数 ID。
    @property
    def range(self) -> range:
        return range(self.start, self.end)

    # Find the first overlapping pair in a sequence. / 查找序列中的首个重叠范围对。
    @staticmethod
    def find_overlap(ranges: Iterable["IdRange"]) -> tuple["IdRange", "IdRange"] | None:
        ordered = sorted(ranges)
        for left, right in zip(ordered, ordered[1:]):
            if left.overlaps(right):
                return left, right
        return None

    # Scala-compatible aliases. / Scala 兼容别名。
    isEmpty = is_empty
    findOverlap = find_overlap


@dataclass(frozen=True)
class TransferSizes:
    """Power-of-two transfer size interval (zero denotes none)."""

    minimum: int
    maximum: int | None = None

    # Normalize and validate transfer sizes. / 规范化并校验传输尺寸。
    def __post_init__(self) -> None:
        maximum = self.minimum if self.maximum is None else self.maximum
        object.__setattr__(self, "maximum", maximum)
        if not isinstance(self.minimum, int) or not isinstance(maximum, int):
            raise TypeError("TransferSizes endpoints must be integers")
        if self.minimum < 0 or maximum < 0 or self.minimum > maximum:
            raise ValueError("invalid TransferSizes interval")
        if (self.minimum and not _is_pow2(self.minimum)) or (maximum and not _is_pow2(maximum)):
            raise ValueError("TransferSizes endpoints must be powers of two")
        if (maximum == 0) != (self.minimum == 0):
            raise ValueError("zero is only valid for the (0,0) interval")

    # Whether no transfer is supported. / 判断是否不支持传输。
    @property
    def none(self) -> bool:
        return self.minimum == 0

    # Expose Rocket's min/max field names alongside explicit Python names. /
    # 除显式 Python 名称外，同时暴露 Rocket 的 min/max 字段名。
    @property
    def min(self) -> int:
        return self.minimum

    # Return the largest supported transfer size. / 返回支持的最大传输尺寸。
    @property
    def max(self) -> int:
        maximum = self.maximum
        assert maximum is not None
        return maximum

    # Test a transfer size. / 测试单个传输尺寸。
    def contains(self, value: int | TransferSizes) -> bool:
        if isinstance(value, TransferSizes):
            maximum = self.maximum
            value_maximum = value.maximum
            assert maximum is not None and value_maximum is not None
            return value.none or (self.minimum <= value.minimum and value_maximum <= maximum)
        maximum = self.maximum
        assert maximum is not None
        return _is_pow2(value) and self.minimum <= value <= maximum

    # Test a logarithmic transfer-size encoding. / 测试以对数表示的传输尺寸。
    def contains_lg(self, exponent: int) -> bool:
        return exponent >= 0 and self.contains(1 << exponent)

    # Intersect two intervals. / 求两个传输尺寸区间交集。
    def intersect(self, other: "TransferSizes") -> "TransferSizes":
        maximum = self.maximum
        other_maximum = other.maximum
        assert maximum is not None and other_maximum is not None
        lo, hi = max(self.minimum, other.minimum), min(maximum, other_maximum)
        return TransferSizes(0) if lo > hi else TransferSizes(lo, hi)

    # Compute smallest power-of-two cover interval. / 计算最小覆盖区间。
    def mincover(self, other: "TransferSizes") -> "TransferSizes":
        if self.none:
            return other
        if other.none:
            return self
        maximum = self.maximum
        other_maximum = other.maximum
        assert maximum is not None and other_maximum is not None
        return TransferSizes(min(self.minimum, other.minimum), max(maximum, other_maximum))

    # Render the original Rocket notation. / 生成原始 Rocket 表示法。
    def __str__(self) -> str:
        return f"TransferSizes[{self.minimum}, {self.max}]"

    # Scala-compatible logarithmic helper alias. / Scala 兼容的对数辅助别名。
    containsLg = contains_lg


@dataclass(frozen=True)
class ResourcePermissions:
    """DTS resource permission tuple (read/write/execute/cache/atomic)."""

    readable: bool = False
    writable: bool = False
    executable: bool = False
    cacheable: bool = False
    atomic: bool = False


@dataclass(frozen=True)
class AddressMapEntry:
    """Address-map row carrying permissions and symbolic names. / 携带权限及符号名称的地址映射行。"""

    range: AddressRange
    permissions: ResourcePermissions = field(default_factory=ResourcePermissions)
    names: tuple[str, ...] = ()

    # Render a human-readable address-map row. / 生成可读的地址映射行。
    def to_string(self, address_width: int = 8) -> str:
        permissions = self.permissions
        flags = "".join((
            "A" if permissions.atomic else " ",
            "R" if permissions.readable else " ",
            "W" if permissions.writable else " ",
            "X" if permissions.executable else " ",
            "C" if permissions.cacheable else " ",
        ))
        return f"\t{self.range.base:0{address_width}x} - {self.range.end:0{address_width}x} {flags} {', '.join(self.names)}"

    # Render a JSON-compatible address-map row. / 生成 JSON 兼容的地址映射行。
    def to_json(self) -> dict[str, Any]:
        permissions = self.permissions
        return {
            "base": [self.range.base],
            "size": [self.range.size],
            "r": [permissions.readable],
            "w": [permissions.writable],
            "x": [permissions.executable],
            "c": [permissions.cacheable],
            "a": [permissions.atomic],
            "names": list(self.names),
        }

    # Render the original Scala JSON string form. / 生成原始 Scala JSON 字符串格式。
    def toJSON(self) -> str:
        return json.dumps(self.to_json(), ensure_ascii=False, separators=(",", ":"))

    # Preserve the Scala-style text helper alias. / 保留 Scala 风格的文本辅助别名。
    toString = to_string


@dataclass(frozen=True)
class ResourceAddress:
    """Address resource attached to a diplomacy node."""

    address: tuple[AddressSet, ...]
    permissions: ResourcePermissions = field(default_factory=ResourcePermissions)

    # Normalize and validate address resources. / 规范化并校验地址资源。
    def __post_init__(self) -> None:
        addresses = tuple(self.address)
        if not addresses or not all(isinstance(item, AddressSet) for item in addresses):
            raise ValueError("resource address must contain at least one AddressSet")
        object.__setattr__(self, "address", addresses)

    # Construct from one AddressSet or a sequence. / 从单个或多个 AddressSet 构造资源。
    @classmethod
    def from_value(
        cls,
        value: AddressSet | Sequence[AddressSet] | int,
        permissions: ResourcePermissions | None = None,
    ) -> "ResourceAddress":
        if isinstance(value, int):
            addresses = (AddressSet(value, 0),)
        elif isinstance(value, AddressSet):
            addresses = (value,)
        else:
            addresses = tuple(value)
        if not addresses:
            raise ValueError("resource address cannot be empty")
        return cls(addresses, permissions or ResourcePermissions())

    # Return a globally shifted resource without mutating this value. / 返回全局偏移
    # 后的资源，同时保持当前值不可变。 /
    def shifted(self, offset: int) -> "ResourceAddress":
        return ResourceAddress(
            tuple(AddressSet(item.base + offset, item.mask) for item in self.address),
            self.permissions,
        )


# Lightweight resource value records preserve the serializable Rocket shape.
# 轻量资源值记录保留可序列化的 Rocket 结构。
@dataclass(frozen=True)
class ResourceMapping:
    """Mapped address resource with an explicit offset. / 带显式偏移的映射地址资源。"""

    address: tuple[AddressSet, ...]
    offset: int = 0
    permissions: ResourcePermissions = field(default_factory=ResourcePermissions)

    # Normalize mapped address sets. / 规范化映射地址集合。
    def __post_init__(self) -> None:
        addresses = tuple(self.address)
        if not addresses or not all(isinstance(item, AddressSet) for item in addresses):
            raise ValueError("resource mapping must contain at least one AddressSet")
        object.__setattr__(self, "address", addresses)


@dataclass(frozen=True)
class ResourceString:
    """String-valued device-tree resource. / 字符串设备树资源。"""

    value: str


@dataclass(frozen=True)
class ResourceInt:
    """Integer-valued device-tree resource. / 整数设备树资源。"""

    value: int


@dataclass(frozen=True)
class ResourceReference:
    """Reference-valued device-tree resource. / 引用型设备树资源。"""

    value: str


@dataclass(frozen=True)
class ResourceAlias:
    """Alias-valued device-tree resource. / 别名型设备树资源。"""

    value: str


@dataclass(frozen=True)
class ResourceMap:
    """Nested deterministic device-tree resource map. / 嵌套确定性设备树资源映射。"""

    value: Mapping[str, Sequence[Any]]
    labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResourceBindings:
    """Keyed collection of resource bindings. / 按键组织的资源绑定集合。"""

    map: Mapping[str, tuple["ResourceBinding", ...]] = field(default_factory=dict)

    # Return bindings for a key, defaulting to an empty tuple. / 返回指定键绑定，缺失
    # 时返回空元组。 /
    def get(self, key: str) -> tuple["ResourceBinding", ...]:
        values = self.map.get(key, ())
        return tuple(values)

    # Keep Scala's callable binding lookup shape. / 保留 Scala 可调用绑定查询形式。
    def __call__(self, key: str) -> tuple["ResourceBinding", ...]:
        return self.get(key)


@dataclass(frozen=True)
class ResourceBinding:
    """Deterministic resource key/value binding."""

    key: str
    value: ResourceAddress | ResourceMapping | ResourceString | ResourceInt | ResourceReference | ResourceAlias | ResourceMap | str | int
    owner: str | None = None


@dataclass(frozen=True)
class BufferParams:
    """Clock-crossing buffer geometry. / 时钟跨越缓冲区几何参数。"""

    depth: int = 2
    flow: bool = False
    pipe: bool = False

    # Validate buffer depth. / 校验缓冲区深度。
    def __post_init__(self) -> None:
        if self.depth < 0:
            raise ValueError("buffer depth must be non-negative")

    # Report whether a queue is materialized. / 报告是否实例化队列。
    @property
    def is_defined(self) -> bool:
        return self.depth > 0

    # Report crossing latency in cycles. / 报告跨越延迟周期数。
    @property
    def latency(self) -> int:
        return int(self.is_defined and not self.flow)

    # Keep Rocket's field-style aliases. / 保留 Rocket 字段风格别名。
    isDefined = is_defined


@dataclass(frozen=True)
class CreditedDelay:
    """Credit crossing delay tuple. / Credit 跨越延迟元组。"""

    debit: int = 1
    credit: int = 1

    # Validate delay values. / 校验延迟取值。
    def __post_init__(self) -> None:
        if self.debit < 0 or self.credit < 0:
            raise ValueError("credited delay values must be non-negative")

    # Return the reverse-direction delay. / 返回反向通道延迟。
    @property
    def flip(self) -> "CreditedDelay":
        return CreditedDelay(self.credit, self.debit)

    # Return round-trip delay. / 返回往返总延迟。
    @property
    def total(self) -> int:
        return self.debit + self.credit

    # Keep descriptive aliases used by this aggregate. / 保留本聚合使用的描述性别名。
    @property
    def cycles(self) -> int:
        return self.debit

    # Return the credit-side delay alias. / 返回 credit 侧延迟别名。
    @property
    def credits(self) -> int:
        return self.credit

    # Render Rocket's compact delay notation. / 生成 Rocket 紧凑延迟表示法。
    def __str__(self) -> str:
        return f"{self.debit}:{self.credit}"


@dataclass(frozen=True)
class AsyncQueueParams:
    """Asynchronous queue synchronizer parameters. / 异步队列同步器参数。"""

    depth: int
    sync: int
    safe: bool = True
    narrow: bool = False

    # Validate asynchronous queue parameters. / 校验异步队列参数。
    def __post_init__(self) -> None:
        if self.depth < 1 or self.sync < 1:
            raise ValueError("async queue depth and synchronizer count must be positive")


class ClockCrossingType:
    """Base metadata type for diplomacy clock crossings. / diplomacy 时钟跨越元数据基类。"""

    # Report whether the crossing is synchronous. / 报告跨越是否同步。
    @property
    def same_clock(self) -> bool:
        return False

    # Scala-compatible camel-case property. / Scala 兼容的驼峰属性。
    @property
    def sameClock(self) -> bool:
        return self.same_clock


class _NoCrossing(ClockCrossingType):
    """Singleton marker for an unbuffered crossing. / 无缓冲跨越单例标记。"""

    # NoCrossing is normalized to an empty synchronous crossing. / NoCrossing 归一化
    # 为无缓冲同步跨越。 /
    @property
    def same_clock(self) -> bool:
        return True

    # Render a stable diagnostic name. / 生成稳定诊断名称。
    def __repr__(self) -> str:
        return "NoCrossing"


NoCrossing = _NoCrossing()


@dataclass(frozen=True)
class SynchronousCrossing(ClockCrossingType):
    """Synchronous crossing with optional buffering. / 带可选缓冲的同步跨越。"""

    params: BufferParams = field(default_factory=lambda: BufferParams())

    # Synchronous crossings stay in the same clock. / 同步跨越保持同一时钟。
    @property
    def same_clock(self) -> bool:
        return True


@dataclass(frozen=True)
class RationalCrossing(ClockCrossingType):
    """Rational clock crossing marker. / Rational 时钟跨越标记。"""

    direction: str = "fast_to_slow"


@dataclass(frozen=True)
class AsynchronousCrossing(ClockCrossingType):
    """Asynchronous crossing synchronizer geometry. / 异步跨越同步器几何参数。"""

    depth: int = 8
    source_sync: int = 3
    sink_sync: int = 3
    safe: bool = True
    narrow: bool = False

    # Validate synchronizer geometry. / 校验同步器几何参数。
    def __post_init__(self) -> None:
        if self.depth < 1 or self.source_sync < 1 or self.sink_sync < 1:
            raise ValueError("asynchronous crossing dimensions must be positive")

    # Return sink-side queue parameters. / 返回接收端异步队列参数。
    @property
    def as_sink_params(self) -> AsyncQueueParams:
        return AsyncQueueParams(self.depth, self.sink_sync, self.safe, self.narrow)

    # Preserve Rocket's camel-case helper. / 保留 Rocket 驼峰命名辅助方法。
    asSinkParams = as_sink_params


@dataclass(frozen=True)
class CreditedCrossing(ClockCrossingType):
    """Credit-based crossing delay metadata. / Credit 型跨越延迟元数据。"""

    source_delay: CreditedDelay = field(default_factory=CreditedDelay)
    sink_delay: CreditedDelay = field(default_factory=CreditedDelay)


# =============================================================================
# Implementation
# =============================================================================
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

    # Normalize mutable edge lists at construction time. / 在构造时规范化可变边列表。
    def __post_init__(self) -> None:
        self.inputs = list(dict.fromkeys(self.inputs))
        self.outputs = list(dict.fromkeys(self.outputs))
        self.addresses = tuple(self.addresses)
        if not self.name:
            raise ValueError("diplomacy node name cannot be empty")

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

    # Return all nodes in stable insertion-independent order. / 按稳定且与插入顺序
    # 无关的方式返回全部节点。 /
    @property
    def node_names(self) -> tuple[str, ...]:
        return tuple(sorted(self.nodes))


# Find a deterministic bit mask that separates non-overlapping ports. /
# 为不重叠端口查找确定性地址区分位掩码。 /
def address_decoder(
    ports: Sequence[Sequence[AddressSet]] | Sequence[int],
    given_bits: int = 0,
) -> int:
    """Return a conservative AddressDecoder-compatible distinguishing mask. /
    返回兼容 AddressDecoder 的保守区分掩码。

    The source implementation uses a greedy partition heuristic.  The V2
    aggregate computes the same observable contract without retaining mutable
    partition state: every pair of ports contributes one care bit, and the
    result is widened only when those bits remain disjoint.
    """
    if given_bits < 0:
        raise ValueError("given_bits must be non-negative")
    normalized: list[tuple[AddressSet, ...]]
    values = tuple(ports)
    if values and isinstance(values[0], int):
        normalized = [(AddressSet(int(value), 0),) for value in values]  # type: ignore[arg-type]
    elif values and isinstance(values[0], AddressSet):
        normalized = [(value,) for value in values]  # type: ignore[misc]
    else:
        normalized = [tuple(port) for port in values]  # type: ignore[arg-type]
    non_empty = [port for port in normalized if port]
    if len(non_empty) <= 1:
        return given_bits
    for index, left_port in enumerate(non_empty):
        for right_port in non_empty[index + 1:]:
            for left in left_port:
                for right in right_port:
                    if left.overlaps(right):
                        raise ValueError(f"ports cannot overlap: {left} {right}")
    selected = given_bits
    for index, left_port in enumerate(non_empty):
        for right_port in non_empty[index + 1:]:
            candidates = [
                (~(left.mask | right.mask) & (left.base ^ right.base))
                for left in left_port for right in right_port
            ]
            distinguishing = 0
            for candidate in candidates:
                distinguishing |= candidate
            selected |= distinguishing
    return selected


# Keep the source object's callable name as a compatibility alias. / 保留源对象的
# 可调用名称作为兼容别名。
AddressDecoder = address_decoder


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
        if not isinstance(self.address_bits, int) or self.address_bits < 1 or self.address_bits > 1024:
            raise ValueError("invalid diplomacy route configuration")
        bases = tuple(int(base) for base in self.route_bases)
        masks = tuple(int(mask) for mask in self.route_masks)
        object.__setattr__(self, "route_bases", bases)
        object.__setattr__(self, "route_masks", masks)
        if len(bases) != len(masks) or not bases:
            raise ValueError("invalid diplomacy route configuration")
        if len(self.route_bases) > 16:
            raise ValueError("at most sixteen diplomacy routes are supported")
        width_mask = (1 << self.address_bits) - 1
        routes: list[AddressSet] = []
        for base, mask in zip(bases, masks):
            if base < 0 or base & ~width_mask:
                raise ValueError("diplomacy route base exceeds address width")
            if mask >= 0 and mask & ~width_mask:
                raise ValueError("diplomacy route mask exceeds address width")
            AddressSet(base, mask)
            routes.append(AddressSet(base, mask))
        for index, route in enumerate(routes):
            if any(route.overlaps(other) for other in routes[index + 1:]):
                raise ValueError("diplomacy routes must not overlap")

    # Return immutable route records for software decoders. / 返回供软件解码器使用的
    # 不可变路由记录。 /
    @property
    def routes(self) -> tuple[AddressSet, ...]:
        return tuple(AddressSet(base, mask) for base, mask in zip(self.route_bases, self.route_masks))

    # Decode one address into hit and route index. / 将地址解码为命中标志和路由索引。
    def decode(self, address: int) -> tuple[bool, int]:
        if not isinstance(address, int) or address < 0 or address >= (1 << self.address_bits):
            return False, 0
        for index, route in enumerate(self.routes):
            if route.contains(address):
                return True, index
        return False, 0


class DiplomacyAddressRouter(Elaboratable):
    """Combinational ready/valid address decoder. / 组合式 ready/valid 地址解码器。"""

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

    # Elaborate combinational ready/valid route selection. / 展开组合 ready/valid 路由选择。
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
        width_mask = (1 << c.address_bits) - 1
        for index, (base, mask) in enumerate(zip(c.route_bases, c.route_masks)):
            care_mask = width_mask ^ (mask & width_mask)
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


# Stable source-oriented aliases used by family consumers. / 为 family 消费者保留稳定
# 的源代码导向别名。
DiplomacyRouter = DiplomacyAddressRouter
UHSCRocketDiplomacy = DiplomacyAddressRouter


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


# =============================================================================
# Direct Entry
# =============================================================================
# Print deterministic direct export. / 打印确定性的 direct 导出。
def main() -> None:
    """Emit default diplomacy Verilog. / 输出默认 diplomacy Verilog。"""
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
