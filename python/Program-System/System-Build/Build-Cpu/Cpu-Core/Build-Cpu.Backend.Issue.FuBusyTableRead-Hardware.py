"""V2 functional-unit busy-table latency mask.
V2 功能单元忙表延迟掩码。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from amaranth import Cat, Const, Elaboratable, Module, Mux, Signal
from amaranth.lib.data import StructLayout, View


# =============================================================================
# Module Contract
# =============================================================================
# FuBusyTableRead.scala ORs, over every latency index of io_in_fuBusyTable,
# the one-hot FuType bits registered in io_in_fuTypeRegVec for that latency
# (``latMappedFuTypeSet``) into the ``numEntries``-bit io_out_fuBusyTableMask:
#   mask[i] = OR_lat (busy[lat] & OR_{b in latMappedFuTypeSet[lat]} fuType[i][b])
# A latency with an empty OH set contributes nothing and is left out of the map;
# a table width of one collapses to a scalar busy input.
# FuBusyTableRead.scala 对忙表每个延迟索引，把该延迟映射的 FuType 独热位按条目或起来，
# 生成 numEntries 位的 io_out_fuBusyTableMask；空集合的延迟不出现，宽度 1 退化为标量输入。
__all__ = [
    "FU_TYPE_BITS",
    "LOCKED_VARIANTS",
    "FuBusyTableReadConfig",
    "FuBusyTableRead",
    "busy_mask_reference",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
# ``FuType()`` is packed as UInt(6.W) in this locked source tree, so the gold
# Verilog declares every io_in_fuTypeRegVec_* port 35 bits wide and only bits
# 0..30 can ever be referenced by an OH set.  Bits 31..34 are dead code that
# Chisel still carries on the bus; they are kept so the generated ABI matches
# the locked reference byte-for-byte.
# / 本锁定源码树中 ``FuType()`` 为 UInt(6.W)，故 gold 端口宽 35 位而仅 0..30 可被引用。
FU_TYPE_BITS = 35

# Exact generated-module variants reachable in the locked Kunminghu V2 XSTop.
# Validators must cover this Build-owned list in full before the Build counts.
# 锁定昆明湖 V2 XSTop 中可达的精确生成模块变体；计数前必须全部证明。
LOCKED_VARIANTS: tuple[str, ...] = (
    "FuBusyTableRead", "FuBusyTableRead_2", "FuBusyTableRead_22",
    "FuBusyTableRead_23", "FuBusyTableRead_26", "FuBusyTableRead_28",
    "FuBusyTableRead_42", "FuBusyTableRead_43", "FuBusyTableRead_52",
    "FuBusyTableRead_53", "FuBusyTableRead_68", "FuBusyTableRead_69",
    "FuBusyTableRead_71", "FuBusyTableRead_73", "FuBusyTableRead_75",
    "FuBusyTableRead_79", "FuBusyTableRead_80", "FuBusyTableRead_105",
)


def _freeze_latency_map(mapping: Any) -> dict[int, frozenset[int]]:
    """Copy any latency mapping into frozen per-latency OH-bit sets."""

    if not isinstance(mapping, Mapping):
        raise TypeError("V2 latency_to_oh_bits must be a latency -> OH-bit mapping")
    result: dict[int, frozenset[int]] = {}
    for latency, bits in mapping.items():
        if not isinstance(latency, int) or isinstance(latency, bool):
            raise TypeError("V2 busy-table latency keys must be integers")
        result[latency] = frozenset(bits)
    return result


@dataclass(frozen=True)
class FuBusyTableReadConfig:
    """V2 busy-table geometry plus the locked latency -> FuType OH-bit map.
    V2 忙表几何与锁定的延迟到 FuType 独热位映射。
    """

    num_entries: int = 24
    fu_type_bits: int = FU_TYPE_BITS
    table_bits: int = 3
    latency_to_oh_bits: Mapping[int, Any] = field(
        default_factory=lambda: {0: frozenset({6}), 2: frozenset({7, 10})}
    )

    # Validate geometry against the Scala equation's constraints. / 按 Scala 等式约束校验几何。
    def __post_init__(self) -> None:
        frozen: Mapping[int, frozenset[int]] = _freeze_latency_map(self.latency_to_oh_bits)
        # Freezing normalizes any iterable of OH bits into frozensets so later
        # validation and elaboration see one canonical value.
        # / 归一化为 frozenset，使校验与展开只见到一种规范值。
        # A frozen dataclass rejects setattr(); super().__setattr__ bypasses the
        # generated __setattr__ without weakening the declared type.
        # / 冻结 dataclass 拒绝 setattr()，改用 super().__setattr__ 保持类型清晰。
        super(FuBusyTableReadConfig, self).__setattr__("latency_to_oh_bits", frozen)
        if self.num_entries < 1:
            raise ValueError("V2 busy-table requires at least one issue entry")
        if self.fu_type_bits < 1:
            raise ValueError("V2 FuType width must be positive")
        table_bits = self.table_bits
        if not frozen:
            raise ValueError("V2 busy-table needs at least one latency group")
        if table_bits < 1:
            raise ValueError("V2 fuBusyTable width must be positive")
        if table_bits > 1 and max(frozen) >= table_bits:
            raise ValueError("V2 latency index exceeds io_in_fuBusyTable width")
        if any(not bits for bits in frozen.values()):
            raise ValueError("V2 latency groups need at least one FuType OH bit")
        if any(bit >= self.fu_type_bits for bits in frozen.values() for bit in bits):
            raise ValueError("V2 FuType OH bit index exceeds io_in_fuTypeRegVec width")


# =============================================================================
# Implementation
# =============================================================================
def busy_mask_reference(
    busy_table: int,
    fu_types: list[int],
    configuration: FuBusyTableReadConfig = FuBusyTableReadConfig(),
) -> int:
    """Return entries whose registered FuType hits a busy latency. / 返回命中忙延迟的发射条目掩码。"""

    result = 0
    for index, fu_type in enumerate(fu_types):
        for latency, oh_bits in configuration.latency_to_oh_bits.items():
            # ``table_bits == 1`` means io_in_fuBusyTable is a scalar, so its only
            # latency lives at bit 0; __post_init__ bounds every other latency.
            # / 宽度 1 时忙表为标量，唯一延迟即第 0 位。
            position = latency if configuration.table_bits > 1 else 0
            if not (busy_table >> position) & 1:
                continue
            if any((fu_type >> bit) & 1 for bit in oh_bits):
                result |= 1 << index
                break
    return result


class FuBusyTableRead(Elaboratable):
    """Combinational FU busy mask reader. / 组合 FU 忙掩码读取器。"""

    # Construct busy table, per-entry FuType views, and output mask ports.
    # / 构造忙表、逐条目 FuType 视图及输出掩码端口。
    def __init__(self, configuration: FuBusyTableReadConfig = FuBusyTableReadConfig()) -> None:
        self.configuration = configuration
        c = configuration
        self.busy_table = Signal(c.table_bits, name="io_in_fuBusyTable")
        self.fu_type_layout = StructLayout({f"oh{bit}": 1 for bit in range(c.fu_type_bits)})
        self.fu_types = [
            Signal(c.fu_type_bits, name=f"io_in_fuTypeRegVec_{index}")
            for index in range(c.num_entries)
        ]
        self.fu_type_views = [View(self.fu_type_layout, port) for port in self.fu_types]
        self.busy_mask = Signal(c.num_entries, name="io_out_fuBusyTableMask")

    # Elaborate the Scala readMaskVec fold. / 展开 Scala readMaskVec 折叠。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        c = self.configuration
        zero = Const(0, c.num_entries)
        expression: Any = None
        for latency in sorted(c.latency_to_oh_bits):
            oh_bits = sorted(c.latency_to_oh_bits[latency])
            hit_terms = []
            for view in self.fu_type_views:
                term: Any = None
                for bit in oh_bits:
                    member: Any = getattr(view, f"oh{bit}")
                    term = member if term is None else term | member
                hit_terms.append(term)
            # ``VecInit(...).asUInt`` puts entry 0 in the least significant bit, and
            # the locked gold agrees: entry N-1 is the leftmost concat item, so the
            # mask bit index equals the issue-entry index.
            # / ``VecInit(...).asUInt`` 把条目 0 放在最低位，掩码位序即条目序号。
            latency_hit_vec = Cat(*hit_terms)
            busy_bit = self.busy_table[latency] if c.table_bits > 1 else self.busy_table
            term = Mux(busy_bit, latency_hit_vec, zero)
            expression = term if expression is None else expression | term
        m.d.comb += self.busy_mask.eq(expression)
        return m


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration=None, injected_dependencies=None) -> str:
    """Emit deterministic FuBusyTableRead Verilog. / 输出确定性的 FuBusyTableRead Verilog。"""

    del injected_dependencies
    from amaranth.back import verilog

    top = FuBusyTableRead(configuration or FuBusyTableReadConfig())
    # ``emit_src=False`` keeps the artifact free of host-path source attributes so
    # Verilator/Yosys reports stay ASCII, as in the sibling V2 Builds.
    # / 关闭 emit_src 以避免主机路径污染报告，与同族 V2 Build 一致。
    return verilog.convert(
        top,
        name="FuBusyTableRead",
        ports=[top.busy_table, *top.fu_types, top.busy_mask],
        emit_src=False,
    )


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    """Print the generated busy mask reader. / 打印生成的忙掩码读取器。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
