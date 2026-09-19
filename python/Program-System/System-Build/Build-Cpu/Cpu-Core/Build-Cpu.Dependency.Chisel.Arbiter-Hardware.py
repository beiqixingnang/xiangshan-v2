"""UHSC Kunminghu V2 Chisel arbitration and clock-domain-crossing boundary.
昆明湖 V2 Chisel 仲裁与跨时钟域边界。

The frozen V2 top instantiates the Chisel standard-library static-priority
``Arbiter`` (34 instances across the core, the L1/L2 and the MMU closures), the
Rocket-Chip asynchronous queue family (``AsyncQueueSource``, ``AsyncQueueSink``,
``AsyncValidSync``, ``AsyncResetSynchronizerShiftReg``, ``ClockCrossingReg``) and
a small set of ready/valid utility leaves (``Repeater``, ``ValidIOBroadcast``,
``IDPool``, the depth-one ``Queue`` BundleMap specialisations).  This aggregate
reproduces those primitives with one parameterised implementation per family plus
an explicit per-instance interface table read from the locked hierarchy, instead
of one shallow stub per generated module.

Two facts about the locked artifact drive the design.  First, every covered
``Arbiter`` instance is the *static-priority* Chisel arbiter: the generated
modules contain no register and drive ``io_in_{i}_ready`` from the
``ArbiterCtrl`` prefix mask, so the family keeps a rotation parameter but does
not claim a rotation policy that the artifact never exercises.  Second, the
generated modules were produced by firtool with dead-port removal and
cross-module constant folding, so some payload fields and some handshake inputs
exist only as folded constants in the locked netlist; those constants were read
back from the locked artifact and are recorded per instance in the interface
table instead of being guessed.

该聚合体按 family 提供一份参数化实现，并用显式实例表记录锁定层级中的每个实例，
而不是为每个生成模块写一个浅层桩；表中同时保存了锁定网表里被折叠掉的字段常量。
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, cast

from amaranth import Assert, Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# The boundary covers the Chisel arbiter family, the Rocket-Chip asynchronous
# queue and reset synchroniser chain, and the ready/valid utility leaves named in
# the coverage manifest. / 该边界覆盖 Chisel 仲裁器 family、Rocket-Chip 异步队列与
# 复位同步链，以及覆盖清单中列出的 ready/valid 工具叶模块。
__all__ = [
    "PayloadLayout", "PackingSegment", "ArbiterSpec", "AsyncQueueSourceSpec",
    "AsyncQueueSinkSpec", "ShiftRegSpec", "AsyncValidSyncSpec", "ClockCrossingSpec",
    "RepeaterSpec", "BroadcastSpec", "IdPoolSpec", "BundleQueueSpec", "FamilySubject",
    "ARBITER_SPECS", "ASYNC_QUEUE_SOURCE_SPECS", "ASYNC_QUEUE_SINK_SPECS",
    "SHIFT_REG_SPECS", "ASYNC_VALID_SYNC_SPECS", "CLOCK_CROSSING_SPECS",
    "REPEATER_SPECS", "BROADCAST_SPECS", "ID_POOL_SPECS", "BUNDLE_QUEUE_SPECS",
    "DEFAULT_SUBJECT_MODULE", "ARBITER_SOURCE_PATHS", "ASYNCHRONOUS_SOURCE_PATHS",
    "UTILITY_SOURCE_PATHS", "StaticArbiter", "AsyncResetSynchronizerShiftReg",
    "AsyncValidSync", "ClockCrossingReg", "AsyncQueueSource", "AsyncQueueSink",
    "Repeater", "ValidIOBroadcast", "IdPool", "BundleMapQueue", "covered_modules",
    "subject_for", "build_verilog", "main",
]


# The Chisel standard-library arbiter is compiled into the V2 top from the
# chisel3 tree; the vendored snapshot keeps it outside `upstream/`. / Chisel 标准
# 库仲裁器由 chisel3 树编译进 V2 顶层；vendored 快照不含该目录。
ARBITER_SOURCE_PATHS: tuple[str, ...] = (
    "src/main/scala/chisel3/util/Arbiter.scala",
)


# The asynchronous queue family spans Rocket-Chip's queue, synchroniser and
# shift-register sources. / 异步队列 family 覆盖 Rocket-Chip 的队列、同步器与移位
# 寄存器源文件。
ASYNCHRONOUS_SOURCE_PATHS: tuple[str, ...] = (
    "upstream/rocket-chip/src/main/scala/util/AsyncQueue.scala",
    "upstream/rocket-chip/src/main/scala/util/SynchronizerReg.scala",
    "upstream/rocket-chip/src/main/scala/util/ShiftReg.scala",
)


# The utility leaves come from Rocket-Chip and the XiangShan utility package. /
# 工具叶模块来自 Rocket-Chip 与 XiangShan utility 包。
UTILITY_SOURCE_PATHS: tuple[str, ...] = (
    "upstream/rocket-chip/src/main/scala/util/Repeater.scala",
    "upstream/rocket-chip/src/main/scala/util/IDPool.scala",
    "upstream/utility/src/main/scala/utility/DiplomacyWidget.scala",
    "src/main/scala/chisel3/util/Decoupled.scala",
)


# =============================================================================
# Configuration
# =============================================================================
# A payload layout is an ordered tuple of (field name, bit width) pairs. / 载荷布局是有序的 (字段名, 位宽) 对元组。
PayloadLayout = tuple[tuple[str, int], ...]


# Describe one locked Chisel static-priority ``Arbiter`` instance. / 描述一个锁定 Chisel 静态优先级 ``Arbiter`` 实例。
@dataclass(frozen=True)
class ArbiterSpec:
    """Locked ``Arbiter`` instance: one payload layout plus per-input presence. / 锁定 ``Arbiter`` 实例：单一载荷布局加逐输入存在性。"""

    name: str
    output_layout: PayloadLayout
    input_fields: tuple[tuple[str, ...], ...]
    tie_offs: tuple[tuple[tuple[str, int], ...], ...]
    chosen_width: int = 0
    omitted_ports: tuple[str, ...] = ()
    out_ready_constant: int | None = None
    priority_order: tuple[int, ...] | None = None

    # Validate the instance geometry against the locked interface. / 校验实例几何与锁定接口一致。
    def __post_init__(self) -> None:
        if not self.input_fields:
            raise ValueError(f"{self.name}: an arbiter needs at least one input")
        if len(self.tie_offs) != len(self.input_fields):
            raise ValueError(f"{self.name}: tie_offs needs one table per input")
        order = self.order()
        if sorted(order) != list(range(len(self.input_fields))):
            raise ValueError(f"{self.name}: priority_order must permute the input indices")
        # The locked hierarchy orders every input's payload fields exactly as the
        # output orders them, with the folded fields omitted, so each input's
        # field list must be a subsequence of the output layout. / 锁定层级中每个输入
        # 的载荷字段顺序与输出完全一致、只是缺少被折叠的字段，因此每个输入的字段
        # 列表必须是输出布局的子序列。
        declared = [field for field, _ in self.output_layout]
        for index, fields in enumerate(self.input_fields):
            if len(set(fields)) != len(fields):
                raise ValueError(f"{self.name}: input {index} repeats a payload field")
            remaining = iter(declared)
            if not all(field in remaining for field in fields):
                raise ValueError(f"{self.name}: input {index} is not in output order")
        for index, table in enumerate(self.tie_offs):
            for field, value in table:
                if value < 0:
                    raise ValueError(f"{self.name}: tie-off {field} must not be negative")
                if field in self.input_fields[index]:
                    raise ValueError(f"{self.name}: input {index} both carries and ties off {field}")
                if field not in declared:
                    raise ValueError(f"{self.name}: tie-off {field} is not a payload field")
        for index in range(len(self.input_fields)):
            covered = set(self.input_fields[index]) | {field for field, _ in self.tie_offs[index]}
            if covered != set(declared):
                raise ValueError(f"{self.name}: input {index} covers {sorted(covered)}, not the layout")

    # Return the arbitration priority order, defaulting to the locked static order.
    # 返回仲裁优先级顺序，默认使用锁定静态顺序。
    def order(self) -> tuple[int, ...]:
        return self.priority_order or tuple(range(len(self.input_fields)))

    # Report whether one input carries a payload field. / 报告某输入是否携带某载荷字段。
    def carries(self, index: int, field: str) -> bool:
        return field in self.input_fields[index]

    # Return the bit width of one payload field. / 返回某载荷字段的位宽。
    def width_of(self, field: str) -> int:
        for name, width in self.output_layout:
            if name == field:
                return width
        raise KeyError(f"{self.name}: unknown payload field {field}")

    # Return the folded constant used when one input lacks a payload field. / 返回某输入缺少某载荷字段时使用的折叠常量。
    def tie_off(self, index: int, field: str) -> int:
        for name, value in self.tie_offs[index]:
            if name == field:
                return value
        return 0


# Describe one locked Rocket-Chip ``AsyncQueueSource`` instance. / 描述一个锁定 Rocket-Chip ``AsyncQueueSource`` 实例。
@dataclass(frozen=True)
class AsyncQueueSourceSpec:
    """Locked asynchronous queue source: depth, sync depth, safety and payload. / 锁定异步队列源：深度、同步级数、安全模式与载荷。"""

    name: str
    depth: int
    sync: int
    safe: bool
    narrow: bool
    layout: PayloadLayout
    omitted_ports: tuple[str, ...] = ()

    # Validate the queue geometry against the V2 parameters. / 校验队列几何参数与 V2 参数一致。
    def __post_init__(self) -> None:
        if self.depth < 1 or self.depth & (self.depth - 1):
            raise ValueError(f"{self.name}: depth must be a positive power of two")
        if self.sync < 2:
            raise ValueError(f"{self.name}: sync must be at least two")
        if self.narrow and self.depth == 1:
            # ``AsyncQueueParams.singleton`` pins ``narrow`` to false for a one
            # entry queue because the read mux has nothing to select, so a narrow
            # single-entry queue has no index to route (AsyncQueue.scala:20-22). /
            # ``AsyncQueueParams.singleton`` 对单条目队列把 ``narrow`` 固定为假，
            # 因为读多路没有可选对象，窄单条目队列没有可用的 index
            # （AsyncQueue.scala:20-22）。
            raise ValueError(f"{self.name}: a single-entry queue has no narrow form")

    # Return the index width of the Gray counter. / 返回格雷计数器的索引位宽。
    def index_width(self) -> int:
        return (self.depth - 1).bit_length()

    # Return the number of crossed payload entries. / 返回跨时钟域载荷条目数。
    def wire_count(self) -> int:
        return 1 if self.narrow else self.depth


# One segment of the packed clock-crossing word: a payload field or a constant. /
# 打包跨时钟字的一个片段：载荷字段或常量。
@dataclass(frozen=True)
class PackingSegment:
    """Packed-word segment; ``field=None`` marks a folded constant. / 打包片段；``field=None`` 表示折叠常量。"""

    field: str | None
    width: int
    value: int = 0


# Describe one locked Rocket-Chip ``AsyncQueueSink`` instance. / 描述一个锁定 Rocket-Chip ``AsyncQueueSink`` 实例。
@dataclass(frozen=True)
class AsyncQueueSinkSpec:
    """Locked asynchronous queue sink: payload, packing and register slices. / 锁定异步队列汇：载荷、打包与寄存器切片。"""

    name: str
    depth: int
    sync: int
    safe: bool
    narrow: bool
    layout: PayloadLayout
    pack: tuple[PackingSegment, ...]
    deq_slices: tuple[tuple[str, int, int], ...]
    deq_ready_constant: int | None = None
    omitted_ports: tuple[str, ...] = ()

    # Validate the sink geometry and packed-word width. / 校验汇几何与打包字宽。
    def __post_init__(self) -> None:
        if self.depth < 1 or self.depth & (self.depth - 1):
            raise ValueError(f"{self.name}: depth must be a positive power of two")
        if self.sync < 2:
            raise ValueError(f"{self.name}: sync must be at least two")
        if self.narrow and self.depth == 1:
            # See ``AsyncQueueSourceSpec``: a one entry queue is never narrow
            # (AsyncQueue.scala:20-22). / 见 ``AsyncQueueSourceSpec``：单条目队列
            # 永远不是窄形式（AsyncQueue.scala:20-22）。
            raise ValueError(f"{self.name}: a single-entry queue has no narrow form")
        for field, msb, lsb in self.deq_slices:
            if msb < lsb or msb >= self.pack_width():
                raise ValueError(f"{self.name}: slice {field} is outside the packed word")

    # Return the index width of the Gray counter. / 返回格雷计数器的索引位宽。
    def index_width(self) -> int:
        return (self.depth - 1).bit_length()

    # Return the number of crossed payload entries. / 返回跨时钟域载荷条目数。
    def wire_count(self) -> int:
        return 1 if self.narrow else self.depth

    # Return the total packed-word width. / 返回打包字总位宽。
    def pack_width(self) -> int:
        return sum(segment.width for segment in self.pack)


# Describe one locked reset-synchroniser shift register. / 描述一个锁定复位同步移位寄存器。
@dataclass(frozen=True)
class ShiftRegSpec:
    """Locked async-reset synchroniser shift register. / 锁定异步复位同步移位寄存器。"""

    name: str
    width: int
    sync: int
    init: int
    primitive: bool

    # Validate the shift-register geometry. / 校验移位寄存器几何参数。
    def __post_init__(self) -> None:
        if self.width < 1:
            raise ValueError(f"{self.name}: width must be positive")
        if self.sync < 2:
            raise ValueError(f"{self.name}: sync must be at least two")
        if self.primitive and self.width != 1:
            raise ValueError(f"{self.name}: the primitive chain is one bit wide")


# Describe one locked ``AsyncValidSync`` handshake synchroniser. / 描述一个锁定 ``AsyncValidSync`` 握手同步器。
@dataclass(frozen=True)
class AsyncValidSyncSpec:
    """Locked handshake synchroniser wrapping one one-bit async-reset chain. / 锁定握手同步器，内部为一条一位异步复位链。"""

    name: str
    sync: int = 3

    # Validate the synchroniser depth against the V2 parameters. / 校验同步级数与 V2 参数一致。
    def __post_init__(self) -> None:
        if self.sync < 2:
            raise ValueError(f"{self.name}: sync must be at least two")


# Describe one locked ``ClockCrossingReg``. / 描述一个锁定 ``ClockCrossingReg``。
@dataclass(frozen=True)
class ClockCrossingSpec:
    """Locked single-depth clock-crossing register. / 锁定单级跨时钟寄存器。"""

    name: str
    width: int
    do_init: bool = False

    # Validate the crossing register width and reset mode. / 校验跨时钟寄存器位宽与复位模式。
    def __post_init__(self) -> None:
        if self.width < 1:
            raise ValueError(f"{self.name}: width must be positive")
        if self.do_init:
            # ``ClockCrossingReg(w, doInit = true)`` would build
            # ``RegEnable(io.d, 0.U, io.en)``, whose reset class depends on
            # chisel3 reset inference.  The locked hierarchy contains no such
            # instance, so the reset type cannot be established from the
            # artifact and the path stays unimplemented rather than guessed.
            # ``ClockCrossingReg(w, doInit = true)`` 会构造带初值的
            # ``RegEnable``，其复位类型取决于 chisel3 复位推断；锁定层级没有该
            # 实例，无法从制品确认复位类型，因此不实现该路径而非猜测。
            raise ValueError(f"{self.name}: do_init=true has no locked evidence")


# Describe one locked ``Repeater``. / 描述一个锁定 ``Repeater``。
@dataclass(frozen=True)
class RepeaterSpec:
    """Locked repeating ready/valid leaf. / 锁定重复发送 ready/valid 叶模块。"""

    name: str
    layout: PayloadLayout
    full_port: bool = True


# Describe one locked ``ValidIOBroadcast``. / 描述一个锁定 ``ValidIOBroadcast``。
@dataclass(frozen=True)
class BroadcastSpec:
    """Locked diplomacy broadcast of one valid/payload bundle. / 锁定 diplomacy 单 bundle 广播。"""

    name: str
    layout: PayloadLayout
    outputs: int = 1


# Describe one locked ``IDPool``. / 描述一个锁定 ``IDPool``。
@dataclass(frozen=True)
class IdPoolSpec:
    """Locked identifier pool with irrevocable select. / 锁定标识池，select 不可撤销。"""

    name: str
    num_ids: int
    late_valid: bool = False
    revocable_select: bool = False

    # Validate the identifier pool width. / 校验标识池位宽。
    def __post_init__(self) -> None:
        if self.num_ids < 1 or self.num_ids & (self.num_ids - 1):
            raise ValueError(f"{self.name}: num_ids must be a positive power of two")

    # Return the identifier width. / 返回标识位宽。
    def id_width(self) -> int:
        return (self.num_ids - 1).bit_length()


# Describe one locked depth-one ``Queue`` bundle specialisation. / 描述一个锁定单深度 ``Queue`` bundle 特化。
@dataclass(frozen=True)
class BundleQueueSpec:
    """Locked single-entry queue with an explicit field serialisation order. / 锁定单条目队列，字段序列化顺序显式给出。"""

    name: str
    layout: PayloadLayout
    packing: tuple[str, ...]

    # Validate that the serialisation order covers the payload exactly. / 校验序列化顺序恰好覆盖载荷。
    def __post_init__(self) -> None:
        declared = {name for name, _ in self.layout}
        if sorted(self.packing) != sorted(declared):
            raise ValueError(f"{self.name}: packing must permute the payload fields")

    # Return the payload width of one field. / 返回某字段的载荷位宽。
    def width_of(self, field: str) -> int:
        for name, width in self.layout:
            if name == field:
                return width
        raise KeyError(f"{self.name}: unknown field {field}")

    # Return the packed bit range of one field as (msb, lsb). / 返回某字段的打包位区间 (msb, lsb)。
    def slice_of(self, field: str) -> tuple[int, int]:
        low = 0
        for name in reversed(self.packing):
            width = self.width_of(name)
            if name == field:
                return low + width - 1, low
            low += width
        raise KeyError(f"{self.name}: unknown field {field}")


# One entry per locked Arbiter instance, in locked port order. / 每个锁定 Arbiter 实例一项，按锁定端口顺序。
ARBITER_SPECS: dict[str, ArbiterSpec] = {
    "Arbiter16_MainPipeReq": ArbiterSpec(
        name="Arbiter16_MainPipeReq",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(
            ("miss_id", 4),
            ("occupy_way", 4),
            ("miss_fail_cause_evict_btot", 1),
            ("source", 4),
            ("cmd", 5),
            ("vaddr", 50),
            ("addr", 48),
            ("word_idx", 3),
            ("amo_data", 128),
            ("amo_mask", 16),
            ("amo_cmp", 128),
            ("pf_source", 3),
            ("access", 1),
            ("id", 6),
        ),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            (
                "miss_id",
                "occupy_way",
                "miss_fail_cause_evict_btot",
                "source",
                "cmd",
                "vaddr",
                "addr",
                "word_idx",
                "amo_data",
                "amo_mask",
                "amo_cmp",
                "pf_source",
                "access",
                "id",
            ),
            # io_in_1 / io_in_1
            (
                "miss_id",
                "occupy_way",
                "miss_fail_cause_evict_btot",
                "source",
                "cmd",
                "vaddr",
                "addr",
                "word_idx",
                "amo_data",
                "amo_mask",
                "amo_cmp",
                "pf_source",
                "access",
                "id",
            ),
            # io_in_2 / io_in_2
            (
                "miss_id",
                "occupy_way",
                "miss_fail_cause_evict_btot",
                "source",
                "cmd",
                "vaddr",
                "addr",
                "word_idx",
                "amo_data",
                "amo_mask",
                "amo_cmp",
                "pf_source",
                "access",
                "id",
            ),
            # io_in_3 / io_in_3
            (
                "miss_id",
                "occupy_way",
                "miss_fail_cause_evict_btot",
                "source",
                "cmd",
                "vaddr",
                "addr",
                "word_idx",
                "amo_data",
                "amo_mask",
                "amo_cmp",
                "pf_source",
                "access",
                "id",
            ),
            # io_in_4 / io_in_4
            (
                "miss_id",
                "occupy_way",
                "miss_fail_cause_evict_btot",
                "source",
                "cmd",
                "vaddr",
                "addr",
                "word_idx",
                "amo_data",
                "amo_mask",
                "amo_cmp",
                "pf_source",
                "access",
                "id",
            ),
            # io_in_5 / io_in_5
            (
                "miss_id",
                "occupy_way",
                "miss_fail_cause_evict_btot",
                "source",
                "cmd",
                "vaddr",
                "addr",
                "word_idx",
                "amo_data",
                "amo_mask",
                "amo_cmp",
                "pf_source",
                "access",
                "id",
            ),
            # io_in_6 / io_in_6
            (
                "miss_id",
                "occupy_way",
                "miss_fail_cause_evict_btot",
                "source",
                "cmd",
                "vaddr",
                "addr",
                "word_idx",
                "amo_data",
                "amo_mask",
                "amo_cmp",
                "pf_source",
                "access",
                "id",
            ),
            # io_in_7 / io_in_7
            (
                "miss_id",
                "occupy_way",
                "miss_fail_cause_evict_btot",
                "source",
                "cmd",
                "vaddr",
                "addr",
                "word_idx",
                "amo_data",
                "amo_mask",
                "amo_cmp",
                "pf_source",
                "access",
                "id",
            ),
            # io_in_8 / io_in_8
            (
                "miss_id",
                "occupy_way",
                "miss_fail_cause_evict_btot",
                "source",
                "cmd",
                "vaddr",
                "addr",
                "word_idx",
                "amo_data",
                "amo_mask",
                "amo_cmp",
                "pf_source",
                "access",
                "id",
            ),
            # io_in_9 / io_in_9
            (
                "miss_id",
                "occupy_way",
                "miss_fail_cause_evict_btot",
                "source",
                "cmd",
                "vaddr",
                "addr",
                "word_idx",
                "amo_data",
                "amo_mask",
                "amo_cmp",
                "pf_source",
                "access",
                "id",
            ),
            # io_in_10 / io_in_10
            (
                "miss_id",
                "occupy_way",
                "miss_fail_cause_evict_btot",
                "source",
                "cmd",
                "vaddr",
                "addr",
                "word_idx",
                "amo_data",
                "amo_mask",
                "amo_cmp",
                "pf_source",
                "access",
                "id",
            ),
            # io_in_11 / io_in_11
            (
                "miss_id",
                "occupy_way",
                "miss_fail_cause_evict_btot",
                "source",
                "cmd",
                "vaddr",
                "addr",
                "word_idx",
                "amo_data",
                "amo_mask",
                "amo_cmp",
                "pf_source",
                "access",
                "id",
            ),
            # io_in_12 / io_in_12
            (
                "miss_id",
                "occupy_way",
                "miss_fail_cause_evict_btot",
                "source",
                "cmd",
                "vaddr",
                "addr",
                "word_idx",
                "amo_data",
                "amo_mask",
                "amo_cmp",
                "pf_source",
                "access",
                "id",
            ),
            # io_in_13 / io_in_13
            (
                "miss_id",
                "occupy_way",
                "miss_fail_cause_evict_btot",
                "source",
                "cmd",
                "vaddr",
                "addr",
                "word_idx",
                "amo_data",
                "amo_mask",
                "amo_cmp",
                "pf_source",
                "access",
                "id",
            ),
            # io_in_14 / io_in_14
            (
                "miss_id",
                "occupy_way",
                "miss_fail_cause_evict_btot",
                "source",
                "cmd",
                "vaddr",
                "addr",
                "word_idx",
                "amo_data",
                "amo_mask",
                "amo_cmp",
                "pf_source",
                "access",
                "id",
            ),
            # io_in_15 / io_in_15
            (
                "miss_id",
                "occupy_way",
                "miss_fail_cause_evict_btot",
                "source",
                "cmd",
                "vaddr",
                "addr",
                "word_idx",
                "amo_data",
                "amo_mask",
                "amo_cmp",
                "pf_source",
                "access",
                "id",
            ),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
        ),
    ),
    "Arbiter1_InsUncacheResp": ArbiterSpec(
        name="Arbiter1_InsUncacheResp",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(("data", 32), ("corrupt", 1),),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            ("data", "corrupt",),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (),
        ),
        omitted_ports=("io_out_ready", "io_in_0_ready",),
    ),
    "Arbiter1_L1BankedDataWriteReq": ArbiterSpec(
        name="Arbiter1_L1BankedDataWriteReq",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(
            ("wmask", 8),
            ("data_0", 64),
            ("data_1", 64),
            ("data_2", 64),
            ("data_3", 64),
            ("data_4", 64),
            ("data_5", 64),
            ("data_6", 64),
            ("data_7", 64),
        ),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            (
                "wmask",
                "data_0",
                "data_1",
                "data_2",
                "data_3",
                "data_4",
                "data_5",
                "data_6",
                "data_7",
            ),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (),
        ),
        omitted_ports=("io_out_ready", "io_in_0_ready",),
    ),
    "Arbiter1_L1BankedDataWriteReqCtrl": ArbiterSpec(
        name="Arbiter1_L1BankedDataWriteReqCtrl",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(("way_en", 4), ("addr", 48),),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            ("way_en", "addr",),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (),
        ),
        omitted_ports=("io_out_ready", "io_in_0_ready",),
    ),
    "Arbiter1_L2TLBImp_Anon": ArbiterSpec(
        name="Arbiter1_L2TLBImp_Anon",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(
            ("s2xlate", 2),
            ("s1_entry_tag", 35),
            ("s1_entry_asid", 16),
            ("s1_entry_vmid", 14),
            ("s1_entry_n", 1),
            ("s1_entry_pbmt", 2),
            ("s1_entry_perm_d", 1),
            ("s1_entry_perm_a", 1),
            ("s1_entry_perm_g", 1),
            ("s1_entry_perm_u", 1),
            ("s1_entry_perm_x", 1),
            ("s1_entry_perm_w", 1),
            ("s1_entry_perm_r", 1),
            ("s1_entry_level", 2),
            ("s1_entry_v", 1),
            ("s1_entry_ppn", 41),
            ("s1_addr_low", 3),
            ("s1_ppn_low_0", 3),
            ("s1_ppn_low_1", 3),
            ("s1_ppn_low_2", 3),
            ("s1_ppn_low_3", 3),
            ("s1_ppn_low_4", 3),
            ("s1_ppn_low_5", 3),
            ("s1_ppn_low_6", 3),
            ("s1_ppn_low_7", 3),
            ("s1_valididx_0", 1),
            ("s1_valididx_1", 1),
            ("s1_valididx_2", 1),
            ("s1_valididx_3", 1),
            ("s1_valididx_4", 1),
            ("s1_valididx_5", 1),
            ("s1_valididx_6", 1),
            ("s1_valididx_7", 1),
            ("s1_pteidx_0", 1),
            ("s1_pteidx_1", 1),
            ("s1_pteidx_2", 1),
            ("s1_pteidx_3", 1),
            ("s1_pteidx_4", 1),
            ("s1_pteidx_5", 1),
            ("s1_pteidx_6", 1),
            ("s1_pteidx_7", 1),
            ("s1_pf", 1),
            ("s1_af", 1),
            ("s2_entry_tag", 38),
            ("s2_entry_vmid", 14),
            ("s2_entry_n", 1),
            ("s2_entry_pbmt", 2),
            ("s2_entry_ppn", 38),
            ("s2_entry_perm_d", 1),
            ("s2_entry_perm_a", 1),
            ("s2_entry_perm_g", 1),
            ("s2_entry_perm_u", 1),
            ("s2_entry_perm_x", 1),
            ("s2_entry_perm_w", 1),
            ("s2_entry_perm_r", 1),
            ("s2_entry_level", 2),
            ("s2_gpf", 1),
            ("s2_gaf", 1),
        ),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            (
                "s2xlate",
                "s1_entry_tag",
                "s1_entry_asid",
                "s1_entry_vmid",
                "s1_entry_n",
                "s1_entry_pbmt",
                "s1_entry_perm_d",
                "s1_entry_perm_a",
                "s1_entry_perm_g",
                "s1_entry_perm_u",
                "s1_entry_perm_x",
                "s1_entry_perm_w",
                "s1_entry_perm_r",
                "s1_entry_level",
                "s1_entry_v",
                "s1_entry_ppn",
                "s1_addr_low",
                "s1_ppn_low_0",
                "s1_ppn_low_1",
                "s1_ppn_low_2",
                "s1_ppn_low_3",
                "s1_ppn_low_4",
                "s1_ppn_low_5",
                "s1_ppn_low_6",
                "s1_ppn_low_7",
                "s1_valididx_0",
                "s1_valididx_1",
                "s1_valididx_2",
                "s1_valididx_3",
                "s1_valididx_4",
                "s1_valididx_5",
                "s1_valididx_6",
                "s1_valididx_7",
                "s1_pteidx_0",
                "s1_pteidx_1",
                "s1_pteidx_2",
                "s1_pteidx_3",
                "s1_pteidx_4",
                "s1_pteidx_5",
                "s1_pteidx_6",
                "s1_pteidx_7",
                "s1_pf",
                "s1_af",
                "s2_entry_tag",
                "s2_entry_vmid",
                "s2_entry_n",
                "s2_entry_pbmt",
                "s2_entry_ppn",
                "s2_entry_perm_d",
                "s2_entry_perm_a",
                "s2_entry_perm_g",
                "s2_entry_perm_u",
                "s2_entry_perm_x",
                "s2_entry_perm_w",
                "s2_entry_perm_r",
                "s2_entry_level",
                "s2_gpf",
                "s2_gaf",
            ),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (),
        ),
    ),
    "Arbiter1_TagWriteReq": ArbiterSpec(
        name="Arbiter1_TagWriteReq",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(("idx", 8), ("way_en", 4), ("tag", 36),),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            ("idx", "way_en", "tag",),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (),
        ),
        omitted_ports=("io_out_ready", "io_in_0_ready",),
    ),
    "Arbiter2_ClientDirWrite": ArbiterSpec(
        name="Arbiter2_ClientDirWrite",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(("set", 10), ("way", 4), ("data_0_state", 2),),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            ("set", "way", "data_0_state",),
            # io_in_1 / io_in_1
            ("set", "way", "data_0_state",),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (),
            (),
        ),
    ),
    "Arbiter2_ClientTagWrite": ArbiterSpec(
        name="Arbiter2_ClientTagWrite",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(("set", 10), ("way", 4), ("tag", 30),),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            ("set", "way", "tag",),
            # io_in_1 / io_in_1
            ("set", "way", "tag",),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (),
            (),
        ),
    ),
    "Arbiter2_DSAddress": ArbiterSpec(
        name="Arbiter2_DSAddress",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(("way", 4), ("set", 12), ("beat", 1), ("noop", 1),),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            ("way", "set", "beat",),
            # io_in_1 / io_in_1
            ("way", "set", "beat", "noop",),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (("noop", 0),),
            (),
        ),
    ),
    "Arbiter2_DirRead": ArbiterSpec(
        name="Arbiter2_DirRead",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(
            ("idOH", 16),
            ("tag", 28),
            ("set", 12),
            ("replacerInfo_channel", 3),
            ("replacerInfo_opcode", 3),
            ("source", 11),
        ),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            ("idOH", "tag", "set",),
            # io_in_1 / io_in_1
            ("idOH", "tag", "set", "replacerInfo_channel", "replacerInfo_opcode", "source",),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (
                ("replacerInfo_channel", 0),
                ("replacerInfo_opcode", 0),
                ("source", 0),
            ),
            (),
        ),
        omitted_ports=("io_in_0_ready",),
    ),
    "Arbiter2_ICacheMissReq": ArbiterSpec(
        name="Arbiter2_ICacheMissReq",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(("blkPaddr", 42), ("vSetIdx", 8),),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            ("blkPaddr", "vSetIdx",),
            # io_in_1 / io_in_1
            ("blkPaddr", "vSetIdx",),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (),
            (),
        ),
    ),
    "Arbiter2_L2TLBImp_Anon": ArbiterSpec(
        name="Arbiter2_L2TLBImp_Anon",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(("id", 3), ("source", 2), ("gvpn", 38),),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            ("source", "gvpn",),
            # io_in_1 / io_in_1
            ("id", "source", "gvpn",),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (("id", 6),),
            (),
        ),
    ),
    "Arbiter2_L2TLBImp_Anon_1": ArbiterSpec(
        name="Arbiter2_L2TLBImp_Anon_1",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(
            ("resp_entry_tag", 38),
            ("resp_entry_vmid", 14),
            ("resp_entry_n", 1),
            ("resp_entry_pbmt", 2),
            ("resp_entry_ppn", 38),
            ("resp_entry_perm_d", 1),
            ("resp_entry_perm_a", 1),
            ("resp_entry_perm_g", 1),
            ("resp_entry_perm_u", 1),
            ("resp_entry_perm_x", 1),
            ("resp_entry_perm_w", 1),
            ("resp_entry_perm_r", 1),
            ("resp_entry_level", 2),
            ("resp_gpf", 1),
            ("resp_gaf", 1),
            ("id", 3),
        ),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            (
                "resp_entry_tag",
                "resp_entry_vmid",
                "resp_entry_n",
                "resp_entry_pbmt",
                "resp_entry_ppn",
                "resp_entry_perm_d",
                "resp_entry_perm_a",
                "resp_entry_perm_g",
                "resp_entry_perm_u",
                "resp_entry_perm_x",
                "resp_entry_perm_w",
                "resp_entry_perm_r",
                "resp_entry_level",
                "resp_gpf",
                "id",
            ),
            # io_in_1 / io_in_1
            (
                "resp_entry_tag",
                "resp_entry_vmid",
                "resp_entry_n",
                "resp_entry_pbmt",
                "resp_entry_ppn",
                "resp_entry_perm_d",
                "resp_entry_perm_a",
                "resp_entry_perm_g",
                "resp_entry_perm_u",
                "resp_entry_perm_x",
                "resp_entry_perm_w",
                "resp_entry_perm_r",
                "resp_entry_level",
                "resp_gpf",
                "resp_gaf",
                "id",
            ),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (("resp_gaf", 0),),
            (),
        ),
        omitted_ports=("io_out_ready", "io_in_0_ready",),
        out_ready_constant=1,
    ),
    "Arbiter2_L2TlbWithHptwIdBundle": ArbiterSpec(
        name="Arbiter2_L2TlbWithHptwIdBundle",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(("req_info_vpn", 38), ("req_info_s2xlate", 2), ("req_info_source", 2), ("isLLptw", 1),),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            ("req_info_vpn", "req_info_s2xlate", "req_info_source", "isLLptw",),
            # io_in_1 / io_in_1
            ("req_info_vpn", "req_info_s2xlate", "req_info_source",),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (),
            (("isLLptw", 0),),
        ),
    ),
    "Arbiter2_LLPTW_Anon": ArbiterSpec(
        name="Arbiter2_LLPTW_Anon",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(("source", 2), ("id", 3), ("ppn", 44),),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            ("source", "id", "ppn",),
            # io_in_1 / io_in_1
            ("source", "id", "ppn",),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (),
            (),
        ),
    ),
    "Arbiter2_MSHRRequest": ArbiterSpec(
        name="Arbiter2_MSHRRequest",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(
            ("channel", 3),
            ("opcode", 3),
            ("param", 3),
            ("size", 3),
            ("source", 11),
            ("set", 12),
            ("tag", 28),
            ("off", 6),
            ("mask", 32),
            ("bufIdx", 4),
            ("needHint", 1),
            ("isPrefetch", 1),
            ("isBop", 1),
            ("preferCache", 1),
            ("dirty", 1),
            ("isHit", 1),
            ("fromProbeHelper", 1),
            ("fromCmoHelper", 1),
            ("needProbeAckData", 1),
            ("reqSource", 5),
        ),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            (
                "channel",
                "opcode",
                "param",
                "size",
                "source",
                "set",
                "tag",
                "off",
                "mask",
                "bufIdx",
                "needHint",
                "isPrefetch",
                "isBop",
                "preferCache",
                "dirty",
                "isHit",
                "fromProbeHelper",
                "fromCmoHelper",
                "needProbeAckData",
                "reqSource",
            ),
            # io_in_1 / io_in_1
            (
                "channel",
                "opcode",
                "param",
                "size",
                "source",
                "set",
                "tag",
                "off",
                "mask",
                "isPrefetch",
                "isBop",
                "needProbeAckData",
                "reqSource",
            ),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (),
            (
                ("bufIdx", 0),
                ("needHint", 0),
                ("preferCache", 1),
                ("dirty", 0),
                ("isHit", 1),
                ("fromProbeHelper", 0),
                ("fromCmoHelper", 0),
            ),
        ),
    ),
    "Arbiter2_PtwReq": ArbiterSpec(
        name="Arbiter2_PtwReq",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(("vpn", 38), ("s2xlate", 2),),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            ("vpn", "s2xlate",),
            # io_in_1 / io_in_1
            ("vpn", "s2xlate",),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (),
            (),
        ),
        chosen_width=1,
    ),
    "Arbiter2_SelfDirWrite": ArbiterSpec(
        name="Arbiter2_SelfDirWrite",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(
            ("set", 12),
            ("way", 4),
            ("data_dirty", 1),
            ("data_state", 2),
            ("data_clientStates_0", 2),
            ("data_prefetch", 1),
        ),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            ("set", "way", "data_dirty", "data_state", "data_clientStates_0", "data_prefetch",),
            # io_in_1 / io_in_1
            ("set", "way", "data_dirty", "data_state", "data_clientStates_0", "data_prefetch",),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (),
            (),
        ),
    ),
    "Arbiter2_SelfTagWrite": ArbiterSpec(
        name="Arbiter2_SelfTagWrite",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(("set", 12), ("way", 4), ("tag", 28),),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            ("set", "way", "tag",),
            # io_in_1 / io_in_1
            ("set", "way", "tag",),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (),
            (),
        ),
    ),
    "Arbiter3_1_Anon": ArbiterSpec(
        name="Arbiter3_1_Anon",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(
            ("task_channel", 3),
            ("task_txChannel", 3),
            ("task_set", 9),
            ("task_tag", 31),
            ("task_off", 6),
            ("task_alias", 2),
            ("task_vaddr", 44),
            ("task_isKeyword", 1),
            ("task_opcode", 4),
            ("task_param", 3),
            ("task_size", 3),
            ("task_sourceId", 7),
            ("task_bufIdx", 2),
            ("task_needProbeAckData", 1),
            ("task_denied", 1),
            ("task_corrupt", 1),
            ("task_mshrTask", 1),
            ("task_mshrId", 8),
            ("task_aliasTask", 1),
            ("task_useProbeData", 1),
            ("task_mshrRetry", 1),
            ("task_readProbeDataDown", 1),
            ("task_fromL2pft", 1),
            ("task_needHint", 1),
            ("task_dirty", 1),
            ("task_way", 3),
            ("task_meta_dirty", 1),
            ("task_meta_state", 2),
            ("task_meta_clients", 1),
            ("task_meta_alias", 2),
            ("task_meta_prefetch", 1),
            ("task_meta_prefetchSrc", 3),
            ("task_meta_accessed", 1),
            ("task_meta_tagErr", 1),
            ("task_meta_dataErr", 1),
            ("task_metaWen", 1),
            ("task_tagWen", 1),
            ("task_dsWen", 1),
            ("task_wayMask", 8),
            ("task_replTask", 1),
            ("task_cmoTask", 1),
            ("task_cmoAll", 1),
            ("task_reqSource", 5),
            ("task_mergeA", 1),
            ("task_aMergeTask_off", 6),
            ("task_aMergeTask_alias", 2),
            ("task_aMergeTask_vaddr", 44),
            ("task_aMergeTask_isKeyword", 1),
            ("task_aMergeTask_opcode", 3),
            ("task_aMergeTask_param", 3),
            ("task_aMergeTask_sourceId", 7),
            ("task_aMergeTask_meta_dirty", 1),
            ("task_aMergeTask_meta_state", 2),
            ("task_aMergeTask_meta_clients", 1),
            ("task_aMergeTask_meta_alias", 2),
            ("task_aMergeTask_meta_prefetch", 1),
            ("task_aMergeTask_meta_prefetchSrc", 3),
            ("task_aMergeTask_meta_accessed", 1),
            ("task_aMergeTask_meta_tagErr", 1),
            ("task_aMergeTask_meta_dataErr", 1),
            ("task_snpHitRelease", 1),
            ("task_snpHitReleaseToInval", 1),
            ("task_snpHitReleaseToClean", 1),
            ("task_snpHitReleaseWithData", 1),
            ("task_snpHitReleaseIdx", 8),
            ("task_snpHitReleaseMeta_dirty", 1),
            ("task_snpHitReleaseMeta_state", 2),
            ("task_snpHitReleaseMeta_clients", 1),
            ("task_snpHitReleaseMeta_alias", 2),
            ("task_snpHitReleaseMeta_prefetch", 1),
            ("task_snpHitReleaseMeta_prefetchSrc", 3),
            ("task_snpHitReleaseMeta_accessed", 1),
            ("task_snpHitReleaseMeta_tagErr", 1),
            ("task_snpHitReleaseMeta_dataErr", 1),
            ("data_data", 512),
        ),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            (
                "task_channel",
                "task_txChannel",
                "task_set",
                "task_tag",
                "task_off",
                "task_alias",
                "task_vaddr",
                "task_isKeyword",
                "task_opcode",
                "task_param",
                "task_size",
                "task_sourceId",
                "task_bufIdx",
                "task_needProbeAckData",
                "task_denied",
                "task_corrupt",
                "task_mshrTask",
                "task_mshrId",
                "task_aliasTask",
                "task_useProbeData",
                "task_mshrRetry",
                "task_readProbeDataDown",
                "task_fromL2pft",
                "task_needHint",
                "task_dirty",
                "task_way",
                "task_meta_dirty",
                "task_meta_state",
                "task_meta_clients",
                "task_meta_alias",
                "task_meta_prefetch",
                "task_meta_prefetchSrc",
                "task_meta_accessed",
                "task_meta_tagErr",
                "task_meta_dataErr",
                "task_metaWen",
                "task_tagWen",
                "task_dsWen",
                "task_wayMask",
                "task_replTask",
                "task_cmoTask",
                "task_cmoAll",
                "task_reqSource",
                "task_mergeA",
                "task_aMergeTask_off",
                "task_aMergeTask_alias",
                "task_aMergeTask_vaddr",
                "task_aMergeTask_isKeyword",
                "task_aMergeTask_opcode",
                "task_aMergeTask_param",
                "task_aMergeTask_sourceId",
                "task_aMergeTask_meta_dirty",
                "task_aMergeTask_meta_state",
                "task_aMergeTask_meta_clients",
                "task_aMergeTask_meta_alias",
                "task_aMergeTask_meta_prefetch",
                "task_aMergeTask_meta_prefetchSrc",
                "task_aMergeTask_meta_accessed",
                "task_aMergeTask_meta_tagErr",
                "task_aMergeTask_meta_dataErr",
                "task_snpHitRelease",
                "task_snpHitReleaseToInval",
                "task_snpHitReleaseToClean",
                "task_snpHitReleaseWithData",
                "task_snpHitReleaseIdx",
                "task_snpHitReleaseMeta_dirty",
                "task_snpHitReleaseMeta_state",
                "task_snpHitReleaseMeta_clients",
                "task_snpHitReleaseMeta_alias",
                "task_snpHitReleaseMeta_prefetch",
                "task_snpHitReleaseMeta_prefetchSrc",
                "task_snpHitReleaseMeta_accessed",
                "task_snpHitReleaseMeta_tagErr",
                "task_snpHitReleaseMeta_dataErr",
                "data_data",
            ),
            # io_in_1 / io_in_1
            (
                "task_channel",
                "task_txChannel",
                "task_set",
                "task_tag",
                "task_off",
                "task_alias",
                "task_vaddr",
                "task_isKeyword",
                "task_opcode",
                "task_param",
                "task_size",
                "task_sourceId",
                "task_bufIdx",
                "task_needProbeAckData",
                "task_denied",
                "task_corrupt",
                "task_mshrTask",
                "task_mshrId",
                "task_aliasTask",
                "task_useProbeData",
                "task_mshrRetry",
                "task_readProbeDataDown",
                "task_fromL2pft",
                "task_needHint",
                "task_dirty",
                "task_way",
                "task_meta_dirty",
                "task_meta_state",
                "task_meta_clients",
                "task_meta_alias",
                "task_meta_prefetch",
                "task_meta_prefetchSrc",
                "task_meta_accessed",
                "task_meta_tagErr",
                "task_meta_dataErr",
                "task_metaWen",
                "task_tagWen",
                "task_dsWen",
                "task_wayMask",
                "task_replTask",
                "task_cmoTask",
                "task_cmoAll",
                "task_reqSource",
                "task_mergeA",
                "task_aMergeTask_off",
                "task_aMergeTask_alias",
                "task_aMergeTask_vaddr",
                "task_aMergeTask_isKeyword",
                "task_aMergeTask_opcode",
                "task_aMergeTask_param",
                "task_aMergeTask_sourceId",
                "task_aMergeTask_meta_dirty",
                "task_aMergeTask_meta_state",
                "task_aMergeTask_meta_clients",
                "task_aMergeTask_meta_alias",
                "task_aMergeTask_meta_prefetch",
                "task_aMergeTask_meta_prefetchSrc",
                "task_aMergeTask_meta_accessed",
                "task_aMergeTask_meta_tagErr",
                "task_aMergeTask_meta_dataErr",
                "task_snpHitRelease",
                "task_snpHitReleaseToInval",
                "task_snpHitReleaseToClean",
                "task_snpHitReleaseWithData",
                "task_snpHitReleaseIdx",
                "task_snpHitReleaseMeta_dirty",
                "task_snpHitReleaseMeta_state",
                "task_snpHitReleaseMeta_clients",
                "task_snpHitReleaseMeta_alias",
                "task_snpHitReleaseMeta_prefetch",
                "task_snpHitReleaseMeta_prefetchSrc",
                "task_snpHitReleaseMeta_accessed",
                "task_snpHitReleaseMeta_tagErr",
                "task_snpHitReleaseMeta_dataErr",
                "data_data",
            ),
            # io_in_2 / io_in_2
            (
                "task_channel",
                "task_txChannel",
                "task_set",
                "task_tag",
                "task_off",
                "task_alias",
                "task_vaddr",
                "task_isKeyword",
                "task_opcode",
                "task_param",
                "task_size",
                "task_sourceId",
                "task_bufIdx",
                "task_needProbeAckData",
                "task_denied",
                "task_corrupt",
                "task_mshrTask",
                "task_mshrId",
                "task_aliasTask",
                "task_useProbeData",
                "task_mshrRetry",
                "task_readProbeDataDown",
                "task_fromL2pft",
                "task_needHint",
                "task_dirty",
                "task_way",
                "task_meta_dirty",
                "task_meta_state",
                "task_meta_clients",
                "task_meta_alias",
                "task_meta_prefetch",
                "task_meta_prefetchSrc",
                "task_meta_accessed",
                "task_meta_tagErr",
                "task_meta_dataErr",
                "task_metaWen",
                "task_tagWen",
                "task_dsWen",
                "task_wayMask",
                "task_replTask",
                "task_cmoTask",
                "task_cmoAll",
                "task_reqSource",
                "task_mergeA",
                "task_aMergeTask_off",
                "task_aMergeTask_alias",
                "task_aMergeTask_vaddr",
                "task_aMergeTask_isKeyword",
                "task_aMergeTask_opcode",
                "task_aMergeTask_param",
                "task_aMergeTask_sourceId",
                "task_aMergeTask_meta_dirty",
                "task_aMergeTask_meta_state",
                "task_aMergeTask_meta_clients",
                "task_aMergeTask_meta_alias",
                "task_aMergeTask_meta_prefetch",
                "task_aMergeTask_meta_prefetchSrc",
                "task_aMergeTask_meta_accessed",
                "task_aMergeTask_meta_tagErr",
                "task_aMergeTask_meta_dataErr",
                "task_snpHitRelease",
                "task_snpHitReleaseToInval",
                "task_snpHitReleaseToClean",
                "task_snpHitReleaseWithData",
                "task_snpHitReleaseIdx",
                "task_snpHitReleaseMeta_dirty",
                "task_snpHitReleaseMeta_state",
                "task_snpHitReleaseMeta_clients",
                "task_snpHitReleaseMeta_alias",
                "task_snpHitReleaseMeta_prefetch",
                "task_snpHitReleaseMeta_prefetchSrc",
                "task_snpHitReleaseMeta_accessed",
                "task_snpHitReleaseMeta_tagErr",
                "task_snpHitReleaseMeta_dataErr",
                "data_data",
            ),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (),
            (),
            (),
        ),
        omitted_ports=("io_in_0_ready",),
    ),
    "Arbiter3_L2TLBImp_Anon": ArbiterSpec(
        name="Arbiter3_L2TLBImp_Anon",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(
            ("s2xlate", 2),
            ("s1_entry_0_tag", 35),
            ("s1_entry_0_asid", 16),
            ("s1_entry_0_vmid", 14),
            ("s1_entry_0_n", 1),
            ("s1_entry_0_pbmt", 2),
            ("s1_entry_0_perm_d", 1),
            ("s1_entry_0_perm_a", 1),
            ("s1_entry_0_perm_g", 1),
            ("s1_entry_0_perm_u", 1),
            ("s1_entry_0_perm_x", 1),
            ("s1_entry_0_perm_w", 1),
            ("s1_entry_0_perm_r", 1),
            ("s1_entry_0_level", 2),
            ("s1_entry_0_v", 1),
            ("s1_entry_0_ppn", 41),
            ("s1_entry_0_ppn_low", 3),
            ("s1_entry_0_af", 1),
            ("s1_entry_0_pf", 1),
            ("s1_entry_0_cf", 1),
            ("s1_entry_1_tag", 35),
            ("s1_entry_1_asid", 16),
            ("s1_entry_1_vmid", 14),
            ("s1_entry_1_n", 1),
            ("s1_entry_1_pbmt", 2),
            ("s1_entry_1_perm_d", 1),
            ("s1_entry_1_perm_a", 1),
            ("s1_entry_1_perm_g", 1),
            ("s1_entry_1_perm_u", 1),
            ("s1_entry_1_perm_x", 1),
            ("s1_entry_1_perm_w", 1),
            ("s1_entry_1_perm_r", 1),
            ("s1_entry_1_level", 2),
            ("s1_entry_1_v", 1),
            ("s1_entry_1_ppn", 41),
            ("s1_entry_1_ppn_low", 3),
            ("s1_entry_1_af", 1),
            ("s1_entry_1_pf", 1),
            ("s1_entry_1_cf", 1),
            ("s1_entry_2_tag", 35),
            ("s1_entry_2_asid", 16),
            ("s1_entry_2_vmid", 14),
            ("s1_entry_2_n", 1),
            ("s1_entry_2_pbmt", 2),
            ("s1_entry_2_perm_d", 1),
            ("s1_entry_2_perm_a", 1),
            ("s1_entry_2_perm_g", 1),
            ("s1_entry_2_perm_u", 1),
            ("s1_entry_2_perm_x", 1),
            ("s1_entry_2_perm_w", 1),
            ("s1_entry_2_perm_r", 1),
            ("s1_entry_2_level", 2),
            ("s1_entry_2_v", 1),
            ("s1_entry_2_ppn", 41),
            ("s1_entry_2_ppn_low", 3),
            ("s1_entry_2_af", 1),
            ("s1_entry_2_pf", 1),
            ("s1_entry_2_cf", 1),
            ("s1_entry_3_tag", 35),
            ("s1_entry_3_asid", 16),
            ("s1_entry_3_vmid", 14),
            ("s1_entry_3_n", 1),
            ("s1_entry_3_pbmt", 2),
            ("s1_entry_3_perm_d", 1),
            ("s1_entry_3_perm_a", 1),
            ("s1_entry_3_perm_g", 1),
            ("s1_entry_3_perm_u", 1),
            ("s1_entry_3_perm_x", 1),
            ("s1_entry_3_perm_w", 1),
            ("s1_entry_3_perm_r", 1),
            ("s1_entry_3_level", 2),
            ("s1_entry_3_v", 1),
            ("s1_entry_3_ppn", 41),
            ("s1_entry_3_ppn_low", 3),
            ("s1_entry_3_af", 1),
            ("s1_entry_3_pf", 1),
            ("s1_entry_3_cf", 1),
            ("s1_entry_4_tag", 35),
            ("s1_entry_4_asid", 16),
            ("s1_entry_4_vmid", 14),
            ("s1_entry_4_n", 1),
            ("s1_entry_4_pbmt", 2),
            ("s1_entry_4_perm_d", 1),
            ("s1_entry_4_perm_a", 1),
            ("s1_entry_4_perm_g", 1),
            ("s1_entry_4_perm_u", 1),
            ("s1_entry_4_perm_x", 1),
            ("s1_entry_4_perm_w", 1),
            ("s1_entry_4_perm_r", 1),
            ("s1_entry_4_level", 2),
            ("s1_entry_4_v", 1),
            ("s1_entry_4_ppn", 41),
            ("s1_entry_4_ppn_low", 3),
            ("s1_entry_4_af", 1),
            ("s1_entry_4_pf", 1),
            ("s1_entry_4_cf", 1),
            ("s1_entry_5_tag", 35),
            ("s1_entry_5_asid", 16),
            ("s1_entry_5_vmid", 14),
            ("s1_entry_5_n", 1),
            ("s1_entry_5_pbmt", 2),
            ("s1_entry_5_perm_d", 1),
            ("s1_entry_5_perm_a", 1),
            ("s1_entry_5_perm_g", 1),
            ("s1_entry_5_perm_u", 1),
            ("s1_entry_5_perm_x", 1),
            ("s1_entry_5_perm_w", 1),
            ("s1_entry_5_perm_r", 1),
            ("s1_entry_5_level", 2),
            ("s1_entry_5_v", 1),
            ("s1_entry_5_ppn", 41),
            ("s1_entry_5_ppn_low", 3),
            ("s1_entry_5_af", 1),
            ("s1_entry_5_pf", 1),
            ("s1_entry_5_cf", 1),
            ("s1_entry_6_tag", 35),
            ("s1_entry_6_asid", 16),
            ("s1_entry_6_vmid", 14),
            ("s1_entry_6_n", 1),
            ("s1_entry_6_pbmt", 2),
            ("s1_entry_6_perm_d", 1),
            ("s1_entry_6_perm_a", 1),
            ("s1_entry_6_perm_g", 1),
            ("s1_entry_6_perm_u", 1),
            ("s1_entry_6_perm_x", 1),
            ("s1_entry_6_perm_w", 1),
            ("s1_entry_6_perm_r", 1),
            ("s1_entry_6_level", 2),
            ("s1_entry_6_v", 1),
            ("s1_entry_6_ppn", 41),
            ("s1_entry_6_ppn_low", 3),
            ("s1_entry_6_af", 1),
            ("s1_entry_6_pf", 1),
            ("s1_entry_6_cf", 1),
            ("s1_entry_7_tag", 35),
            ("s1_entry_7_asid", 16),
            ("s1_entry_7_vmid", 14),
            ("s1_entry_7_n", 1),
            ("s1_entry_7_pbmt", 2),
            ("s1_entry_7_perm_d", 1),
            ("s1_entry_7_perm_a", 1),
            ("s1_entry_7_perm_g", 1),
            ("s1_entry_7_perm_u", 1),
            ("s1_entry_7_perm_x", 1),
            ("s1_entry_7_perm_w", 1),
            ("s1_entry_7_perm_r", 1),
            ("s1_entry_7_level", 2),
            ("s1_entry_7_v", 1),
            ("s1_entry_7_ppn", 41),
            ("s1_entry_7_ppn_low", 3),
            ("s1_entry_7_af", 1),
            ("s1_entry_7_pf", 1),
            ("s1_entry_7_cf", 1),
            ("s1_pteidx_0", 1),
            ("s1_pteidx_1", 1),
            ("s1_pteidx_2", 1),
            ("s1_pteidx_3", 1),
            ("s1_pteidx_4", 1),
            ("s1_pteidx_5", 1),
            ("s1_pteidx_6", 1),
            ("s1_pteidx_7", 1),
            ("s1_not_super", 1),
            ("s1_not_merge", 1),
            ("s2_entry_tag", 38),
            ("s2_entry_vmid", 14),
            ("s2_entry_n", 1),
            ("s2_entry_pbmt", 2),
            ("s2_entry_ppn", 38),
            ("s2_entry_perm_d", 1),
            ("s2_entry_perm_a", 1),
            ("s2_entry_perm_g", 1),
            ("s2_entry_perm_u", 1),
            ("s2_entry_perm_x", 1),
            ("s2_entry_perm_w", 1),
            ("s2_entry_perm_r", 1),
            ("s2_entry_level", 2),
            ("s2_gpf", 1),
            ("s2_gaf", 1),
        ),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            (
                "s2xlate",
                "s1_entry_0_tag",
                "s1_entry_0_asid",
                "s1_entry_0_vmid",
                "s1_entry_0_n",
                "s1_entry_0_pbmt",
                "s1_entry_0_perm_d",
                "s1_entry_0_perm_a",
                "s1_entry_0_perm_g",
                "s1_entry_0_perm_u",
                "s1_entry_0_perm_x",
                "s1_entry_0_perm_w",
                "s1_entry_0_perm_r",
                "s1_entry_0_level",
                "s1_entry_0_v",
                "s1_entry_0_ppn",
                "s1_entry_0_ppn_low",
                "s1_entry_0_pf",
                "s1_entry_0_cf",
                "s1_entry_1_tag",
                "s1_entry_1_asid",
                "s1_entry_1_vmid",
                "s1_entry_1_n",
                "s1_entry_1_pbmt",
                "s1_entry_1_perm_d",
                "s1_entry_1_perm_a",
                "s1_entry_1_perm_g",
                "s1_entry_1_perm_u",
                "s1_entry_1_perm_x",
                "s1_entry_1_perm_w",
                "s1_entry_1_perm_r",
                "s1_entry_1_level",
                "s1_entry_1_v",
                "s1_entry_1_ppn",
                "s1_entry_1_ppn_low",
                "s1_entry_1_pf",
                "s1_entry_1_cf",
                "s1_entry_2_tag",
                "s1_entry_2_asid",
                "s1_entry_2_vmid",
                "s1_entry_2_n",
                "s1_entry_2_pbmt",
                "s1_entry_2_perm_d",
                "s1_entry_2_perm_a",
                "s1_entry_2_perm_g",
                "s1_entry_2_perm_u",
                "s1_entry_2_perm_x",
                "s1_entry_2_perm_w",
                "s1_entry_2_perm_r",
                "s1_entry_2_level",
                "s1_entry_2_v",
                "s1_entry_2_ppn",
                "s1_entry_2_ppn_low",
                "s1_entry_2_pf",
                "s1_entry_2_cf",
                "s1_entry_3_tag",
                "s1_entry_3_asid",
                "s1_entry_3_vmid",
                "s1_entry_3_n",
                "s1_entry_3_pbmt",
                "s1_entry_3_perm_d",
                "s1_entry_3_perm_a",
                "s1_entry_3_perm_g",
                "s1_entry_3_perm_u",
                "s1_entry_3_perm_x",
                "s1_entry_3_perm_w",
                "s1_entry_3_perm_r",
                "s1_entry_3_level",
                "s1_entry_3_v",
                "s1_entry_3_ppn",
                "s1_entry_3_ppn_low",
                "s1_entry_3_pf",
                "s1_entry_3_cf",
                "s1_entry_4_tag",
                "s1_entry_4_asid",
                "s1_entry_4_vmid",
                "s1_entry_4_n",
                "s1_entry_4_pbmt",
                "s1_entry_4_perm_d",
                "s1_entry_4_perm_a",
                "s1_entry_4_perm_g",
                "s1_entry_4_perm_u",
                "s1_entry_4_perm_x",
                "s1_entry_4_perm_w",
                "s1_entry_4_perm_r",
                "s1_entry_4_level",
                "s1_entry_4_v",
                "s1_entry_4_ppn",
                "s1_entry_4_ppn_low",
                "s1_entry_4_pf",
                "s1_entry_4_cf",
                "s1_entry_5_tag",
                "s1_entry_5_asid",
                "s1_entry_5_vmid",
                "s1_entry_5_n",
                "s1_entry_5_pbmt",
                "s1_entry_5_perm_d",
                "s1_entry_5_perm_a",
                "s1_entry_5_perm_g",
                "s1_entry_5_perm_u",
                "s1_entry_5_perm_x",
                "s1_entry_5_perm_w",
                "s1_entry_5_perm_r",
                "s1_entry_5_level",
                "s1_entry_5_v",
                "s1_entry_5_ppn",
                "s1_entry_5_ppn_low",
                "s1_entry_5_pf",
                "s1_entry_5_cf",
                "s1_entry_6_tag",
                "s1_entry_6_asid",
                "s1_entry_6_vmid",
                "s1_entry_6_n",
                "s1_entry_6_pbmt",
                "s1_entry_6_perm_d",
                "s1_entry_6_perm_a",
                "s1_entry_6_perm_g",
                "s1_entry_6_perm_u",
                "s1_entry_6_perm_x",
                "s1_entry_6_perm_w",
                "s1_entry_6_perm_r",
                "s1_entry_6_level",
                "s1_entry_6_v",
                "s1_entry_6_ppn",
                "s1_entry_6_ppn_low",
                "s1_entry_6_pf",
                "s1_entry_6_cf",
                "s1_entry_7_tag",
                "s1_entry_7_asid",
                "s1_entry_7_vmid",
                "s1_entry_7_n",
                "s1_entry_7_pbmt",
                "s1_entry_7_perm_d",
                "s1_entry_7_perm_a",
                "s1_entry_7_perm_g",
                "s1_entry_7_perm_u",
                "s1_entry_7_perm_x",
                "s1_entry_7_perm_w",
                "s1_entry_7_perm_r",
                "s1_entry_7_level",
                "s1_entry_7_v",
                "s1_entry_7_ppn",
                "s1_entry_7_ppn_low",
                "s1_entry_7_pf",
                "s1_entry_7_cf",
                "s1_pteidx_0",
                "s1_pteidx_1",
                "s1_pteidx_2",
                "s1_pteidx_3",
                "s1_pteidx_4",
                "s1_pteidx_5",
                "s1_pteidx_6",
                "s1_pteidx_7",
                "s1_not_super",
                "s2_entry_tag",
                "s2_entry_vmid",
                "s2_entry_n",
                "s2_entry_pbmt",
                "s2_entry_ppn",
                "s2_entry_perm_d",
                "s2_entry_perm_a",
                "s2_entry_perm_g",
                "s2_entry_perm_u",
                "s2_entry_perm_x",
                "s2_entry_perm_w",
                "s2_entry_perm_r",
                "s2_entry_level",
                "s2_gpf",
            ),
            # io_in_1 / io_in_1
            (
                "s2xlate",
                "s1_entry_0_tag",
                "s1_entry_0_asid",
                "s1_entry_0_vmid",
                "s1_entry_0_n",
                "s1_entry_0_pbmt",
                "s1_entry_0_perm_d",
                "s1_entry_0_perm_a",
                "s1_entry_0_perm_g",
                "s1_entry_0_perm_u",
                "s1_entry_0_perm_x",
                "s1_entry_0_perm_w",
                "s1_entry_0_perm_r",
                "s1_entry_0_level",
                "s1_entry_0_v",
                "s1_entry_0_ppn",
                "s1_entry_0_ppn_low",
                "s1_entry_0_af",
                "s1_entry_0_pf",
                "s1_entry_0_cf",
                "s1_entry_1_tag",
                "s1_entry_1_asid",
                "s1_entry_1_vmid",
                "s1_entry_1_n",
                "s1_entry_1_pbmt",
                "s1_entry_1_perm_d",
                "s1_entry_1_perm_a",
                "s1_entry_1_perm_g",
                "s1_entry_1_perm_u",
                "s1_entry_1_perm_x",
                "s1_entry_1_perm_w",
                "s1_entry_1_perm_r",
                "s1_entry_1_level",
                "s1_entry_1_v",
                "s1_entry_1_ppn",
                "s1_entry_1_ppn_low",
                "s1_entry_1_af",
                "s1_entry_1_pf",
                "s1_entry_1_cf",
                "s1_entry_2_tag",
                "s1_entry_2_asid",
                "s1_entry_2_vmid",
                "s1_entry_2_n",
                "s1_entry_2_pbmt",
                "s1_entry_2_perm_d",
                "s1_entry_2_perm_a",
                "s1_entry_2_perm_g",
                "s1_entry_2_perm_u",
                "s1_entry_2_perm_x",
                "s1_entry_2_perm_w",
                "s1_entry_2_perm_r",
                "s1_entry_2_level",
                "s1_entry_2_v",
                "s1_entry_2_ppn",
                "s1_entry_2_ppn_low",
                "s1_entry_2_af",
                "s1_entry_2_pf",
                "s1_entry_2_cf",
                "s1_entry_3_tag",
                "s1_entry_3_asid",
                "s1_entry_3_vmid",
                "s1_entry_3_n",
                "s1_entry_3_pbmt",
                "s1_entry_3_perm_d",
                "s1_entry_3_perm_a",
                "s1_entry_3_perm_g",
                "s1_entry_3_perm_u",
                "s1_entry_3_perm_x",
                "s1_entry_3_perm_w",
                "s1_entry_3_perm_r",
                "s1_entry_3_level",
                "s1_entry_3_v",
                "s1_entry_3_ppn",
                "s1_entry_3_ppn_low",
                "s1_entry_3_af",
                "s1_entry_3_pf",
                "s1_entry_3_cf",
                "s1_entry_4_tag",
                "s1_entry_4_asid",
                "s1_entry_4_vmid",
                "s1_entry_4_n",
                "s1_entry_4_pbmt",
                "s1_entry_4_perm_d",
                "s1_entry_4_perm_a",
                "s1_entry_4_perm_g",
                "s1_entry_4_perm_u",
                "s1_entry_4_perm_x",
                "s1_entry_4_perm_w",
                "s1_entry_4_perm_r",
                "s1_entry_4_level",
                "s1_entry_4_v",
                "s1_entry_4_ppn",
                "s1_entry_4_ppn_low",
                "s1_entry_4_af",
                "s1_entry_4_pf",
                "s1_entry_4_cf",
                "s1_entry_5_tag",
                "s1_entry_5_asid",
                "s1_entry_5_vmid",
                "s1_entry_5_n",
                "s1_entry_5_pbmt",
                "s1_entry_5_perm_d",
                "s1_entry_5_perm_a",
                "s1_entry_5_perm_g",
                "s1_entry_5_perm_u",
                "s1_entry_5_perm_x",
                "s1_entry_5_perm_w",
                "s1_entry_5_perm_r",
                "s1_entry_5_level",
                "s1_entry_5_v",
                "s1_entry_5_ppn",
                "s1_entry_5_ppn_low",
                "s1_entry_5_af",
                "s1_entry_5_pf",
                "s1_entry_5_cf",
                "s1_entry_6_tag",
                "s1_entry_6_asid",
                "s1_entry_6_vmid",
                "s1_entry_6_n",
                "s1_entry_6_pbmt",
                "s1_entry_6_perm_d",
                "s1_entry_6_perm_a",
                "s1_entry_6_perm_g",
                "s1_entry_6_perm_u",
                "s1_entry_6_perm_x",
                "s1_entry_6_perm_w",
                "s1_entry_6_perm_r",
                "s1_entry_6_level",
                "s1_entry_6_v",
                "s1_entry_6_ppn",
                "s1_entry_6_ppn_low",
                "s1_entry_6_af",
                "s1_entry_6_pf",
                "s1_entry_6_cf",
                "s1_entry_7_tag",
                "s1_entry_7_asid",
                "s1_entry_7_vmid",
                "s1_entry_7_n",
                "s1_entry_7_pbmt",
                "s1_entry_7_perm_d",
                "s1_entry_7_perm_a",
                "s1_entry_7_perm_g",
                "s1_entry_7_perm_u",
                "s1_entry_7_perm_x",
                "s1_entry_7_perm_w",
                "s1_entry_7_perm_r",
                "s1_entry_7_level",
                "s1_entry_7_v",
                "s1_entry_7_ppn",
                "s1_entry_7_ppn_low",
                "s1_entry_7_af",
                "s1_entry_7_pf",
                "s1_entry_7_cf",
                "s1_pteidx_0",
                "s1_pteidx_1",
                "s1_pteidx_2",
                "s1_pteidx_3",
                "s1_pteidx_4",
                "s1_pteidx_5",
                "s1_pteidx_6",
                "s1_pteidx_7",
                "s1_not_super",
                "s2_entry_tag",
                "s2_entry_vmid",
                "s2_entry_n",
                "s2_entry_pbmt",
                "s2_entry_ppn",
                "s2_entry_perm_d",
                "s2_entry_perm_a",
                "s2_entry_perm_g",
                "s2_entry_perm_u",
                "s2_entry_perm_x",
                "s2_entry_perm_w",
                "s2_entry_perm_r",
                "s2_entry_level",
                "s2_gpf",
                "s2_gaf",
            ),
            # io_in_2 / io_in_2
            (
                "s2xlate",
                "s1_entry_0_tag",
                "s1_entry_0_asid",
                "s1_entry_0_vmid",
                "s1_entry_0_n",
                "s1_entry_0_pbmt",
                "s1_entry_0_perm_d",
                "s1_entry_0_perm_a",
                "s1_entry_0_perm_g",
                "s1_entry_0_perm_u",
                "s1_entry_0_perm_x",
                "s1_entry_0_perm_w",
                "s1_entry_0_perm_r",
                "s1_entry_0_level",
                "s1_entry_0_v",
                "s1_entry_0_ppn",
                "s1_entry_0_ppn_low",
                "s1_entry_0_af",
                "s1_entry_0_pf",
                "s1_entry_0_cf",
                "s1_entry_1_tag",
                "s1_entry_1_asid",
                "s1_entry_1_vmid",
                "s1_entry_1_n",
                "s1_entry_1_pbmt",
                "s1_entry_1_perm_d",
                "s1_entry_1_perm_a",
                "s1_entry_1_perm_g",
                "s1_entry_1_perm_u",
                "s1_entry_1_perm_x",
                "s1_entry_1_perm_w",
                "s1_entry_1_perm_r",
                "s1_entry_1_level",
                "s1_entry_1_v",
                "s1_entry_1_ppn",
                "s1_entry_1_ppn_low",
                "s1_entry_1_af",
                "s1_entry_1_pf",
                "s1_entry_1_cf",
                "s1_entry_2_tag",
                "s1_entry_2_asid",
                "s1_entry_2_vmid",
                "s1_entry_2_n",
                "s1_entry_2_pbmt",
                "s1_entry_2_perm_d",
                "s1_entry_2_perm_a",
                "s1_entry_2_perm_g",
                "s1_entry_2_perm_u",
                "s1_entry_2_perm_x",
                "s1_entry_2_perm_w",
                "s1_entry_2_perm_r",
                "s1_entry_2_level",
                "s1_entry_2_v",
                "s1_entry_2_ppn",
                "s1_entry_2_ppn_low",
                "s1_entry_2_af",
                "s1_entry_2_pf",
                "s1_entry_2_cf",
                "s1_entry_3_tag",
                "s1_entry_3_asid",
                "s1_entry_3_vmid",
                "s1_entry_3_n",
                "s1_entry_3_pbmt",
                "s1_entry_3_perm_d",
                "s1_entry_3_perm_a",
                "s1_entry_3_perm_g",
                "s1_entry_3_perm_u",
                "s1_entry_3_perm_x",
                "s1_entry_3_perm_w",
                "s1_entry_3_perm_r",
                "s1_entry_3_level",
                "s1_entry_3_v",
                "s1_entry_3_ppn",
                "s1_entry_3_ppn_low",
                "s1_entry_3_af",
                "s1_entry_3_pf",
                "s1_entry_3_cf",
                "s1_entry_4_tag",
                "s1_entry_4_asid",
                "s1_entry_4_vmid",
                "s1_entry_4_n",
                "s1_entry_4_pbmt",
                "s1_entry_4_perm_d",
                "s1_entry_4_perm_a",
                "s1_entry_4_perm_g",
                "s1_entry_4_perm_u",
                "s1_entry_4_perm_x",
                "s1_entry_4_perm_w",
                "s1_entry_4_perm_r",
                "s1_entry_4_level",
                "s1_entry_4_v",
                "s1_entry_4_ppn",
                "s1_entry_4_ppn_low",
                "s1_entry_4_af",
                "s1_entry_4_pf",
                "s1_entry_4_cf",
                "s1_entry_5_tag",
                "s1_entry_5_asid",
                "s1_entry_5_vmid",
                "s1_entry_5_n",
                "s1_entry_5_pbmt",
                "s1_entry_5_perm_d",
                "s1_entry_5_perm_a",
                "s1_entry_5_perm_g",
                "s1_entry_5_perm_u",
                "s1_entry_5_perm_x",
                "s1_entry_5_perm_w",
                "s1_entry_5_perm_r",
                "s1_entry_5_level",
                "s1_entry_5_v",
                "s1_entry_5_ppn",
                "s1_entry_5_ppn_low",
                "s1_entry_5_af",
                "s1_entry_5_pf",
                "s1_entry_5_cf",
                "s1_entry_6_tag",
                "s1_entry_6_asid",
                "s1_entry_6_vmid",
                "s1_entry_6_n",
                "s1_entry_6_pbmt",
                "s1_entry_6_perm_d",
                "s1_entry_6_perm_a",
                "s1_entry_6_perm_g",
                "s1_entry_6_perm_u",
                "s1_entry_6_perm_x",
                "s1_entry_6_perm_w",
                "s1_entry_6_perm_r",
                "s1_entry_6_level",
                "s1_entry_6_v",
                "s1_entry_6_ppn",
                "s1_entry_6_ppn_low",
                "s1_entry_6_af",
                "s1_entry_6_pf",
                "s1_entry_6_cf",
                "s1_entry_7_tag",
                "s1_entry_7_asid",
                "s1_entry_7_vmid",
                "s1_entry_7_n",
                "s1_entry_7_pbmt",
                "s1_entry_7_perm_d",
                "s1_entry_7_perm_a",
                "s1_entry_7_perm_g",
                "s1_entry_7_perm_u",
                "s1_entry_7_perm_x",
                "s1_entry_7_perm_w",
                "s1_entry_7_perm_r",
                "s1_entry_7_level",
                "s1_entry_7_v",
                "s1_entry_7_ppn",
                "s1_entry_7_ppn_low",
                "s1_entry_7_af",
                "s1_entry_7_pf",
                "s1_entry_7_cf",
                "s1_pteidx_0",
                "s1_pteidx_1",
                "s1_pteidx_2",
                "s1_pteidx_3",
                "s1_pteidx_4",
                "s1_pteidx_5",
                "s1_pteidx_6",
                "s1_pteidx_7",
                "s1_not_super",
                "s1_not_merge",
                "s2_entry_tag",
                "s2_entry_vmid",
                "s2_entry_n",
                "s2_entry_pbmt",
                "s2_entry_ppn",
                "s2_entry_perm_d",
                "s2_entry_perm_a",
                "s2_entry_perm_g",
                "s2_entry_perm_u",
                "s2_entry_perm_x",
                "s2_entry_perm_w",
                "s2_entry_perm_r",
                "s2_entry_level",
                "s2_gpf",
                "s2_gaf",
            ),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (
                ("s1_entry_0_af", 0),
                ("s1_entry_1_af", 0),
                ("s1_entry_2_af", 0),
                ("s1_entry_3_af", 0),
                ("s1_entry_4_af", 0),
                ("s1_entry_5_af", 0),
                ("s1_entry_6_af", 0),
                ("s1_entry_7_af", 0),
                ("s1_not_merge", 0),
                ("s2_gaf", 0),
            ),
            (("s1_not_merge", 0),),
            (),
        ),
    ),
    "Arbiter3_PfGenReq": ArbiterSpec(
        name="Arbiter3_PfGenReq",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(
            ("region_tag", 11),
            ("region_addr", 40),
            ("region_bits", 16),
            ("paddr_valid", 1),
            ("decr_mode", 1),
        ),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            ("region_tag", "region_addr", "region_bits",),
            # io_in_1 / io_in_1
            ("region_tag", "region_addr", "region_bits", "paddr_valid",),
            # io_in_2 / io_in_2
            ("region_tag", "region_addr", "region_bits", "paddr_valid",),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (
                ("paddr_valid", 1),
                ("decr_mode", 0),
            ),
            (("decr_mode", 0),),
            (("decr_mode", 1),),
        ),
        omitted_ports=("io_out_ready", "io_in_0_ready",),
        out_ready_constant=1,
    ),
    "Arbiter3_bitmapReqBundle": ArbiterSpec(
        name="Arbiter3_bitmapReqBundle",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(
            ("bmppn", 36),
            ("id", 3),
            ("vpn", 38),
            ("level", 2),
            ("way_info", 4),
            ("hptw_bypassed", 1),
            ("s2xlate", 2),
            ("n", 1),
        ),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            ("bmppn", "vpn", "level", "s2xlate", "n",),
            # io_in_1 / io_in_1
            ("bmppn", "id", "vpn", "way_info", "s2xlate", "n",),
            # io_in_2 / io_in_2
            ("bmppn", "vpn", "level", "way_info", "hptw_bypassed", "n",),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (
                ("id", 6),
                ("way_info", 0),
                ("hptw_bypassed", 0),
            ),
            (
                ("level", 0),
                ("hptw_bypassed", 0),
            ),
            (
                ("id", 7),
                ("s2xlate", 2),
            ),
        ),
    ),
    "Arbiter4_CtrlResp": ArbiterSpec(
        name="Arbiter4_CtrlResp",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(
            ("cmd", 8),
            ("data_0", 64),
            ("data_1", 64),
            ("data_2", 64),
            ("data_3", 64),
            ("data_4", 64),
            ("data_5", 64),
            ("data_6", 64),
            ("data_7", 64),
        ),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            (
                "cmd",
                "data_0",
                "data_1",
                "data_2",
                "data_3",
                "data_4",
                "data_5",
                "data_6",
                "data_7",
            ),
            # io_in_1 / io_in_1
            (
                "cmd",
                "data_0",
                "data_1",
                "data_2",
                "data_3",
                "data_4",
                "data_5",
                "data_6",
                "data_7",
            ),
            # io_in_2 / io_in_2
            (
                "cmd",
                "data_0",
                "data_1",
                "data_2",
                "data_3",
                "data_4",
                "data_5",
                "data_6",
                "data_7",
            ),
            # io_in_3 / io_in_3
            (
                "cmd",
                "data_0",
                "data_1",
                "data_2",
                "data_3",
                "data_4",
                "data_5",
                "data_6",
                "data_7",
            ),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (),
            (),
            (),
            (),
        ),
    ),
    "Arbiter4_EccInfo": ArbiterSpec(
        name="Arbiter4_EccInfo",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(("errCode", 8), ("addr", 64),),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            ("errCode", "addr",),
            # io_in_1 / io_in_1
            ("errCode", "addr",),
            # io_in_2 / io_in_2
            ("errCode", "addr",),
            # io_in_3 / io_in_3
            ("errCode", "addr",),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (),
            (),
            (),
            (),
        ),
        chosen_width=2,
    ),
    "Arbiter4_L2CacheErrorInfo": ArbiterSpec(
        name="Arbiter4_L2CacheErrorInfo",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(("valid", 1), ("address", 46),),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            ("valid", "address",),
            # io_in_1 / io_in_1
            ("valid", "address",),
            # io_in_2 / io_in_2
            ("valid", "address",),
            # io_in_3 / io_in_3
            ("valid", "address",),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (),
            (),
            (),
            (),
        ),
        omitted_ports=("io_out_ready", "io_in_0_ready", "io_in_1_ready", "io_in_2_ready", "io_in_3_ready",),
    ),
    "Arbiter4_L2TlbMemReqBundle": ArbiterSpec(
        name="Arbiter4_L2TlbMemReqBundle",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(("addr", 48), ("id", 4), ("hptw_bypassed", 1),),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            ("addr",),
            # io_in_1 / io_in_1
            ("addr", "id",),
            # io_in_2 / io_in_2
            ("addr", "hptw_bypassed",),
            # io_in_3 / io_in_3
            ("addr", "id",),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (
                ("id", 6),
                ("hptw_bypassed", 0),
            ),
            (("hptw_bypassed", 0),),
            (("id", 7),),
            (("hptw_bypassed", 0),),
        ),
    ),
    "Arbiter4_L2ToL1Hint": ArbiterSpec(
        name="Arbiter4_L2ToL1Hint",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(("sourceId", 32), ("isKeyword", 1),),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            ("sourceId", "isKeyword",),
            # io_in_1 / io_in_1
            ("sourceId", "isKeyword",),
            # io_in_2 / io_in_2
            ("sourceId", "isKeyword",),
            # io_in_3 / io_in_3
            ("sourceId", "isKeyword",),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (),
            (),
            (),
            (),
        ),
        chosen_width=2,
    ),
    "Arbiter4_MainPipeReq": ArbiterSpec(
        name="Arbiter4_MainPipeReq",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(
            ("miss", 1),
            ("miss_id", 4),
            ("occupy_way", 4),
            ("miss_fail_cause_evict_btot", 1),
            ("probe", 1),
            ("probe_param", 2),
            ("probe_need_data", 1),
            ("source", 4),
            ("cmd", 5),
            ("vaddr", 50),
            ("addr", 48),
            ("store_data", 512),
            ("store_mask", 64),
            ("word_idx", 3),
            ("amo_data", 128),
            ("amo_mask", 16),
            ("amo_cmp", 128),
            ("pf_source", 3),
            ("access", 1),
            ("id", 6),
        ),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            ("probe_param", "probe_need_data", "vaddr", "addr", "id",),
            # io_in_1 / io_in_1
            (
                "miss_id",
                "occupy_way",
                "miss_fail_cause_evict_btot",
                "source",
                "cmd",
                "vaddr",
                "addr",
                "word_idx",
                "amo_data",
                "amo_mask",
                "amo_cmp",
                "pf_source",
                "access",
                "id",
            ),
            # io_in_2 / io_in_2
            ("vaddr", "addr", "store_data", "store_mask", "id",),
            # io_in_3 / io_in_3
            ("cmd", "vaddr", "addr", "word_idx", "amo_data", "amo_mask", "amo_cmp",),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (
                ("miss", 0),
                ("miss_id", 0),
                ("occupy_way", 0),
                ("miss_fail_cause_evict_btot", 0),
                ("probe", 1),
                ("source", 0),
                ("cmd", 0),
                ("store_data", 0),
                ("store_mask", 0),
                ("word_idx", 0),
                ("amo_data", 0),
                ("amo_mask", 0),
                ("amo_cmp", 0),
                ("pf_source", 0),
                ("access", 0),
            ),
            (
                ("miss", 1),
                ("probe", 0),
                ("probe_param", 0),
                ("probe_need_data", 0),
                ("store_data", 0),
                ("store_mask", 0),
            ),
            (
                ("miss", 0),
                ("miss_id", 0),
                ("occupy_way", 0),
                ("miss_fail_cause_evict_btot", 0),
                ("probe", 0),
                ("probe_param", 0),
                ("probe_need_data", 0),
                ("source", 1),
                ("cmd", 1),
                ("word_idx", 0),
                ("amo_data", 0),
                ("amo_mask", 0),
                ("amo_cmp", 0),
                ("pf_source", 0),
                ("access", 0),
            ),
            (
                ("miss", 0),
                ("miss_id", 0),
                ("occupy_way", 0),
                ("miss_fail_cause_evict_btot", 0),
                ("probe", 0),
                ("probe_param", 0),
                ("probe_need_data", 0),
                ("source", 2),
                ("store_data", 0),
                ("store_mask", 0),
                ("pf_source", 0),
                ("access", 0),
                ("id", 0),
            ),
        ),
        omitted_ports=("io_in_2_ready",),
    ),
    "Arbiter4_PrefetchReq": ArbiterSpec(
        name="Arbiter4_PrefetchReq",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(("tag", 33), ("set", 9), ("vaddr", 44), ("needT", 1), ("source", 7), ("pfSource", 5),),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            ("tag", "set", "pfSource",),
            # io_in_1 / io_in_1
            ("tag", "set", "vaddr", "needT", "source",),
            # io_in_2 / io_in_2
            ("tag", "set", "vaddr", "needT", "source",),
            # io_in_3 / io_in_3
            ("tag", "set",),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (
                ("vaddr", 0),
                ("needT", 0),
                ("source", 0),
            ),
            (("pfSource", 8),),
            (("pfSource", 9),),
            (
                ("vaddr", 0),
                ("needT", 1),
                ("source", 0),
                ("pfSource", 13),
            ),
        ),
        omitted_ports=("io_out_ready", "io_in_0_ready", "io_in_1_ready", "io_in_2_ready", "io_in_3_ready",),
    ),
    "Arbiter5_L2TlbWithHptwIdBundle": ArbiterSpec(
        name="Arbiter5_L2TlbWithHptwIdBundle",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(
            ("req_info_vpn", 38),
            ("req_info_s2xlate", 2),
            ("req_info_source", 2),
            ("isHptwReq", 1),
            ("hptwId", 3),
        ),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            ("req_info_vpn", "req_info_source", "hptwId",),
            # io_in_1 / io_in_1
            ("req_info_vpn", "req_info_s2xlate", "req_info_source",),
            # io_in_2 / io_in_2
            ("req_info_vpn", "req_info_s2xlate", "req_info_source", "isHptwReq", "hptwId",),
            # io_in_3 / io_in_3
            ("req_info_vpn", "req_info_s2xlate", "req_info_source",),
            # io_in_4 / io_in_4
            ("req_info_vpn", "req_info_s2xlate",),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (
                ("req_info_s2xlate", 2),
                ("isHptwReq", 1),
            ),
            (
                ("isHptwReq", 0),
                ("hptwId", 0),
            ),
            (),
            (
                ("isHptwReq", 0),
                ("hptwId", 0),
            ),
            (
                ("req_info_source", 2),
                ("isHptwReq", 0),
                ("hptwId", 0),
            ),
        ),
        chosen_width=3,
    ),
    "Arbiter5_MSHRAcquire": ArbiterSpec(
        name="Arbiter5_MSHRAcquire",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(("acquire_source", 4), ("acquire_address", 48), ("vSetIdx", 8),),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            ("acquire_address", "vSetIdx",),
            # io_in_1 / io_in_1
            ("acquire_address", "vSetIdx",),
            # io_in_2 / io_in_2
            ("acquire_address", "vSetIdx",),
            # io_in_3 / io_in_3
            ("acquire_address", "vSetIdx",),
            # io_in_4 / io_in_4
            ("acquire_source", "acquire_address", "vSetIdx",),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (("acquire_source", 0),),
            (("acquire_source", 1),),
            (("acquire_source", 2),),
            (("acquire_source", 3),),
            (),
        ),
    ),
    "Arbiter8_MainPipeReq": ArbiterSpec(
        name="Arbiter8_MainPipeReq",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(("probe_param", 2), ("probe_need_data", 1), ("vaddr", 50), ("addr", 48), ("id", 6),),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            ("probe_param", "probe_need_data", "vaddr", "addr", "id",),
            # io_in_1 / io_in_1
            ("probe_param", "probe_need_data", "vaddr", "addr", "id",),
            # io_in_2 / io_in_2
            ("probe_param", "probe_need_data", "vaddr", "addr", "id",),
            # io_in_3 / io_in_3
            ("probe_param", "probe_need_data", "vaddr", "addr", "id",),
            # io_in_4 / io_in_4
            ("probe_param", "probe_need_data", "vaddr", "addr", "id",),
            # io_in_5 / io_in_5
            ("probe_param", "probe_need_data", "vaddr", "addr", "id",),
            # io_in_6 / io_in_6
            ("probe_param", "probe_need_data", "vaddr", "addr", "id",),
            # io_in_7 / io_in_7
            ("probe_param", "probe_need_data", "vaddr", "addr", "id",),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
        ),
    ),
    "Arbiter8_bitmapCacheReqBundle": ArbiterSpec(
        name="Arbiter8_bitmapCacheReqBundle",
        # Payload layout in io_out_bits_* order. / 载荷布局，按 io_out_bits_* 顺序。
        output_layout=(("order", 8), ("tag", 36),),
        # Fields each input actually carries; the rest are folded. / 各输入实际携带的字段，其余被折叠。
        input_fields=(
            # io_in_0 / io_in_0
            ("tag",),
            # io_in_1 / io_in_1
            ("tag",),
            # io_in_2 / io_in_2
            ("tag",),
            # io_in_3 / io_in_3
            ("tag",),
            # io_in_4 / io_in_4
            ("tag",),
            # io_in_5 / io_in_5
            ("tag",),
            # io_in_6 / io_in_6
            ("tag",),
            # io_in_7 / io_in_7
            ("tag",),
        ),
        # Folded constants read back from the locked netlist. / 从锁定网表读回的折叠常量。
        tie_offs=(
            (("order", 0),),
            (("order", 1),),
            (("order", 2),),
            (("order", 3),),
            (("order", 4),),
            (("order", 5),),
            (("order", 6),),
            (("order", 7),),
        ),
        chosen_width=3,
        omitted_ports=("io_out_ready", "io_in_0_ready", "io_in_1_ready", "io_in_2_ready", "io_in_3_ready", "io_in_4_ready", "io_in_5_ready", "io_in_6_ready", "io_in_7_ready",),
    ),
}

# One entry per locked AsyncQueueSource instance. / 每个锁定 AsyncQueueSource 实例一项。
ASYNC_QUEUE_SOURCE_SPECS: dict[str, AsyncQueueSourceSpec] = {
    "AsyncQueueSource": AsyncQueueSourceSpec(
        name="AsyncQueueSource",
        depth=1, sync=3, safe=False, narrow=False,
        # Payload layout in io_enq_bits_* order. / 载荷布局，按 io_enq_bits_* 顺序。
        layout=(("opcode", 4), ("address", 9), ("data", 32),),
    ),
    "AsyncQueueSource_1": AsyncQueueSourceSpec(
        name="AsyncQueueSource_1",
        depth=1, sync=3, safe=False, narrow=False,
        # Payload layout in io_enq_bits_* order. / 载荷布局，按 io_enq_bits_* 顺序。
        layout=(("resumereq", 1), ("hartsel", 10), ("ackhavereset", 1), ("hrmask_0", 1),),
    ),
    "AsyncQueueSource_2": AsyncQueueSourceSpec(
        name="AsyncQueueSource_2",
        depth=1, sync=3, safe=False, narrow=False,
        # Payload layout in io_enq_bits_* order. / 载荷布局，按 io_enq_bits_* 顺序。
        layout=(("opcode", 4), ("size", 2), ("source", 1), ("data", 32),),
    ),
    "AsyncQueueSource_3": AsyncQueueSourceSpec(
        name="AsyncQueueSource_3",
        depth=8, sync=3, safe=True, narrow=False,
        # Payload layout in io_enq_bits_* order. / 载荷布局，按 io_enq_bits_* 顺序。
        layout=(("", 64),),
        omitted_ports=("io_enq_ready",),
    ),
}

# One entry per locked AsyncQueueSink instance. / 每个锁定 AsyncQueueSink 实例一项。
ASYNC_QUEUE_SINK_SPECS: dict[str, AsyncQueueSinkSpec] = {
    "AsyncQueueSink": AsyncQueueSinkSpec(
        name="AsyncQueueSink",
        depth=1, sync=3, safe=False, narrow=False,
        # Payload layout in io_async_mem_0_* order. / 载荷布局，按 io_async_mem_0_* 顺序。
        layout=(("opcode", 4), ("size", 2), ("source", 1), ("data", 32),),
        # Crossing word, most significant segment first. / 跨时钟字，最高位片段在前。
        pack=(
            PackingSegment(field="opcode", width=4),
            PackingSegment(field=None, width=2, value=0),
            PackingSegment(field="size", width=2),
            PackingSegment(field="source", width=1),
            PackingSegment(field=None, width=2, value=0),
            PackingSegment(field="data", width=32),
            PackingSegment(field=None, width=1, value=0),
        ),
        # io_deq_bits_* slices of the crossing word. / 跨时钟字的 io_deq_bits_* 切片。
        deq_slices=(("opcode", 43, 40), ("denied", 33, 33), ("data", 32, 1), ("corrupt", 0, 0),),
    ),
    "AsyncQueueSink_1": AsyncQueueSinkSpec(
        name="AsyncQueueSink_1",
        depth=1, sync=3, safe=False, narrow=False,
        # Payload layout in io_async_mem_0_* order. / 载荷布局，按 io_async_mem_0_* 顺序。
        layout=(("opcode", 4), ("address", 9), ("data", 32),),
        # Crossing word, most significant segment first. / 跨时钟字，最高位片段在前。
        pack=(
            PackingSegment(field="opcode", width=4),
            PackingSegment(field=None, width=6, value=4),
            PackingSegment(field="address", width=9),
            PackingSegment(field=None, width=4, value=15),
            PackingSegment(field="data", width=32),
            PackingSegment(field=None, width=1, value=0),
        ),
        # io_deq_bits_* slices of the crossing word. / 跨时钟字的 io_deq_bits_* 切片。
        deq_slices=(("opcode", 55, 52), ("size", 48, 47), ("source", 46, 46), ("address", 45, 37), ("mask", 36, 33), ("data", 32, 1),),
    ),
    "AsyncQueueSink_2": AsyncQueueSinkSpec(
        name="AsyncQueueSink_2",
        depth=1, sync=3, safe=False, narrow=False,
        # Payload layout in io_async_mem_0_* order. / 载荷布局，按 io_async_mem_0_* 顺序。
        layout=(("resumereq", 1), ("hartsel", 10), ("ackhavereset", 1), ("hrmask_0", 1),),
        # Crossing word, most significant segment first. / 跨时钟字，最高位片段在前。
        pack=(
            PackingSegment(field="resumereq", width=1),
            PackingSegment(field="hartsel", width=10),
            PackingSegment(field="ackhavereset", width=1),
            PackingSegment(field=None, width=2, value=0),
            PackingSegment(field="hrmask_0", width=1),
        ),
        # io_deq_bits_* slices of the crossing word. / 跨时钟字的 io_deq_bits_* 切片。
        deq_slices=(
            ("resumereq", 14, 14),
            ("hartsel", 13, 4),
            ("ackhavereset", 3, 3),
            ("hrmask_0", 0, 0),
        ),
        omitted_ports=("io_deq_ready",),
        deq_ready_constant=1,
    ),
    "AsyncQueueSink_3": AsyncQueueSinkSpec(
        name="AsyncQueueSink_3",
        depth=8, sync=3, safe=True, narrow=False,
        # Payload layout in io_async_mem_0_* order. / 载荷布局，按 io_async_mem_0_* 顺序。
        layout=(("", 64),),
        # Crossing word, most significant segment first. / 跨时钟字，最高位片段在前。
        pack=(
            PackingSegment(field="", width=64),
        ),
        # io_deq_bits_* slices of the crossing word. / 跨时钟字的 io_deq_bits_* 切片。
        deq_slices=(("", 63, 0),),
        omitted_ports=("io_deq_ready",),
        deq_ready_constant=1,
    ),
}

# One entry per locked reset-synchroniser chain. / 每条锁定复位同步链一项。
SHIFT_REG_SPECS: dict[str, ShiftRegSpec] = {
    "AsyncResetSynchronizerPrimitiveShiftReg_d3_i0": ShiftRegSpec(name="AsyncResetSynchronizerPrimitiveShiftReg_d3_i0", width=1, sync=3, init=0, primitive=True),
    "AsyncResetSynchronizerShiftReg_w1_d3_i0": ShiftRegSpec(name="AsyncResetSynchronizerShiftReg_w1_d3_i0", width=1, sync=3, init=0, primitive=False),
    "AsyncResetSynchronizerShiftReg_w4_d3_i0": ShiftRegSpec(name="AsyncResetSynchronizerShiftReg_w4_d3_i0", width=4, sync=3, init=0, primitive=False),
}

# One entry per locked handshake synchroniser. / 每个锁定握手同步器一项。
ASYNC_VALID_SYNC_SPECS: dict[str, AsyncValidSyncSpec] = {
    "AsyncValidSync": AsyncValidSyncSpec(name="AsyncValidSync", sync=3),
}

# One entry per locked clock-crossing register. / 每个锁定跨时钟寄存器一项。
CLOCK_CROSSING_SPECS: dict[str, ClockCrossingSpec] = {
    "ClockCrossingReg_w15": ClockCrossingSpec(name="ClockCrossingReg_w15", width=15),
    "ClockCrossingReg_w44": ClockCrossingSpec(name="ClockCrossingReg_w44", width=44),
    "ClockCrossingReg_w56": ClockCrossingSpec(name="ClockCrossingReg_w56", width=56),
    "ClockCrossingReg_w64": ClockCrossingSpec(name="ClockCrossingReg_w64", width=64),
}

# One entry per locked ``Repeater``. / 每个锁定 ``Repeater`` 一项。
REPEATER_SPECS: dict[str, RepeaterSpec] = {
    "Repeater_1": RepeaterSpec(
        name="Repeater_1",
        layout=(("opcode", 4), ("size", 2), ("source", 5), ("address", 30), ("mask", 4),),
    ),
    "Repeater_2": RepeaterSpec(
        name="Repeater_2",
        layout=(("opcode", 4), ("size", 2), ("source", 5), ("address", 30), ("mask", 8), ("data", 64),),
        full_port=False,
    ),
}

# One entry per locked ``ValidIOBroadcast``. / 每个锁定 ``ValidIOBroadcast`` 一项。
BROADCAST_SPECS: dict[str, BroadcastSpec] = {
    "ValidIOBroadcast": BroadcastSpec(
        name="ValidIOBroadcast",
        layout=(
            ("hartid", 6),
            ("rawData_0", 42),
            ("rawData_1", 42),
            ("rawData_2", 42),
            ("rawData_3", 42),
            ("rawData_4", 42),
            ("rawData_5", 42),
            ("rawData_6", 42),
            ("rawData_7", 42),
            ("rawData_8", 42),
            ("rawData_9", 42),
            ("rawData_10", 42),
            ("rawData_11", 42),
        ),
    ),
}

# One entry per locked ``IDPool``. / 每个锁定 ``IDPool`` 一项。
ID_POOL_SPECS: dict[str, IdPoolSpec] = {
    "IDPool": IdPoolSpec(name="IDPool", num_ids=8),
}

# One entry per locked depth-one bundle queue. / 每个锁定单深度 bundle 队列一项。
BUNDLE_QUEUE_SPECS: dict[str, BundleQueueSpec] = {
    "Queue1_BundleMap": BundleQueueSpec(
        name="Queue1_BundleMap",
        layout=(("tl_state_size", 4), ("tl_state_source", 6),),
        # Serialisation order, most significant field first. / 序列化顺序，最高位字段在前。
        packing=("tl_state_source", "tl_state_size",),
    ),
    "Queue1_BundleMap_128": BundleQueueSpec(
        name="Queue1_BundleMap_128",
        layout=(("tl_state_size", 4), ("tl_state_source", 5),),
        # Serialisation order, most significant field first. / 序列化顺序，最高位字段在前。
        packing=("tl_state_source", "tl_state_size",),
    ),
    "Queue1_BundleMap_162": BundleQueueSpec(
        name="Queue1_BundleMap_162",
        layout=(("extra_id", 13), ("real_last", 1),),
        # Serialisation order, most significant field first. / 序列化顺序，最高位字段在前。
        packing=("real_last", "extra_id",),
    ),
}


# The default Build subject is the representative arbiter named in the wave
# assignment. / 默认 Build 主体为 wave 任务中指定的代表仲裁器。
DEFAULT_SUBJECT_MODULE = "Arbiter2_MSHRRequest"


# =============================================================================
# Implementation
# =============================================================================
# Create one named port signal and register it for the Build adapter. / 创建一个具名端口信号并登记，供 Build 适配器使用。
def declare_port(ports: dict[str, Signal], name: str, width: int) -> Signal:
    signal = Signal(width, name=name)
    ports[name] = signal
    return signal


# Cast Amaranth generator controls to the context-manager protocol. / 将 Amaranth 生成器控制转换为上下文管理器协议。
def amaranth_if(module: Module, condition: Any) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.If(condition))


# Cast an Amaranth elif branch to the context-manager protocol. / 将 Amaranth elif 分支转换为上下文管理器协议。
def amaranth_elif(module: Module, condition: Any) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.Elif(condition))


# Cast an Amaranth else branch to the context-manager protocol. / 将 Amaranth else 分支转换为上下文管理器协议。
def amaranth_else(module: Module) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.Else())


# Decode a dynamic index into a one-hot pattern, replacing ``UIntToOH``. / 将动态索引解码为独热模式，替代 ``UIntToOH``。
def one_hot_decode(index: Any, width: int) -> Any:
    pattern: Any = Const(0, width)
    for position in range(width):
        pattern = Mux(index == position, Const(1 << position, width), pattern)
    return pattern


# Encode a request bitmap into the lowest set bit index, replacing ``PriorityEncoder``. / 将请求位图编码为最低置位索引，替代 ``PriorityEncoder``。
def priority_encode(bitmap: Any, width: int) -> Any:
    if len(bitmap) > 1 << width:
        raise ValueError("the encoded index width cannot address every bitmap bit")
    encoded: Any = Const((1 << width) - 1, width)
    for position in reversed(range(len(bitmap))):
        encoded = Mux(bitmap[position], Const(position, width), encoded)
    return encoded


# Render the port-name infix of one payload field; the locked netlist drops the
# underscore when firtool named the payload itself instead of a bundle field. /
# 渲染一个载荷字段的端口名中缀；当 firtool 直接命名载荷而非 bundle 字段时，锁定
# 网表会省略下划线。
def field_infix(field: str) -> str:
    return f"_{field}" if field else ""


# Count the set bits of a request bitmap, replacing ``PopCount``. / 统计请求位图的置位数，替代 ``PopCount``。
def pop_count(bitmap: Any) -> Any:
    total: Any = Const(0, 1)
    for position in range(len(bitmap)):
        total = total + bitmap[position]
    return total


# Select one crossed payload field of the asynchronous queue memory. / 选择异步队列存储体的一个跨时钟载荷字段。
def select_mem_field(entries: list[Signal], index: Signal | None) -> Any:
    value: Any = entries[-1]
    for position in reversed(range(len(entries) - 1)):
        value = Mux(index == position, entries[position], value)
    return value


# Fold one Gray-coded queue pointer into the physical entry it addresses,
# replacing ``p(bits-1, 0) ^ (p(bits) << (bits-1))``
# (AsyncQueue.scala:85 for the source, :152 for the sink). / 将格雷编码的队列指针
# 折叠为其寻址的物理条目，替代 ``p(bits-1, 0) ^ (p(bits) << (bits-1))``
# （源见 AsyncQueue.scala:85，汇见 :152）。
def gray_entry_index(pointer: Signal, bits: int) -> Any:
    return pointer[0:bits] ^ Mux(pointer[bits], Const(1 << (bits - 1), bits), Const(0, bits))


class StaticArbiter(Elaboratable):
    """Static-priority Chisel ``Arbiter`` with the ``ArbiterCtrl`` ready mask. / 静态优先级 Chisel ``Arbiter`` 与 ``ArbiterCtrl`` ready 掩码。"""

    # Create the exact locked port set of one arbiter instance. / 创建一个仲裁器实例的精确锁定端口集合。
    def __init__(self, spec: ArbiterSpec) -> None:
        self.spec = spec
        self.ports: dict[str, Signal] = {}
        count = len(spec.input_fields)
        # firtool lists each ``Decoupled`` input as ready, valid, then payload and
        # the output the same way, so the declaration order repeats that layout. /
        # firtool 将每个 ``Decoupled`` 输入按 ready、valid、载荷的顺序列出，输出
        # 相同，因此声明顺序重复该布局。
        for index, fields in enumerate(spec.input_fields):
            if f"io_in_{index}_ready" not in spec.omitted_ports:
                declare_port(self.ports, f"io_in_{index}_ready", 1)
            declare_port(self.ports, f"io_in_{index}_valid", 1)
            for field in fields:
                declare_port(self.ports, f"io_in_{index}_bits_{field}", spec.width_of(field))
        if "io_out_ready" not in spec.omitted_ports:
            declare_port(self.ports, "io_out_ready", 1)
        elif spec.out_ready_constant is None and any(
                f"io_in_{index}_ready" not in spec.omitted_ports for index in range(count)):
            raise ValueError(f"{spec.name}: a surviving ready output needs the folded io_out_ready constant")
        declare_port(self.ports, "io_out_valid", 1)
        for field, width in spec.output_layout:
            declare_port(self.ports, f"io_out_bits_{field}", width)
        if spec.chosen_width:
            declare_port(self.ports, "io_chosen", spec.chosen_width)

    # Elaborate the priority mux tree and the ArbiterCtrl prefix mask. / 展开优先多路树与 ArbiterCtrl 前缀掩码。
    def elaborate(self, platform: Any) -> Module:
        del platform
        spec = self.spec
        m = Module()
        count = len(spec.input_fields)
        valid = [self.ports[f"io_in_{index}_valid"] for index in range(count)]
        if "io_out_ready" in self.ports:
            out_ready: Any = self.ports["io_out_ready"]
        else:
            out_ready = Const(spec.out_ready_constant or 0, 1)
        prefix: Any = None
        for index in range(count):
            ready = self.ports.get(f"io_in_{index}_ready")
            if ready is not None:
                # ``ArbiterCtrl`` grants input 0 ``true.B`` and every later input
                # the negated prefix-or of its predecessors (Arbiter.scala:45), so
                # each ready copies the sink's ready unchanged on the winner. /
                # ``ArbiterCtrl`` 对输入 0 授予 ``true.B``，后续输入取前驱前缀或的
                # 非（Arbiter.scala:45），因此胜出者的 ready 直接复用 sink 的 ready。
                m.d.comb += ready.eq(out_ready if prefix is None else (~prefix & out_ready))
            prefix = valid[index] if prefix is None else (prefix | valid[index])
        # ``io.out.valid := !grant.last || io.in.last.valid`` (Arbiter.scala:154)
        # is the plain or-reduction of the request vector. /
        # ``io.out.valid := !grant.last || io.in.last.valid``（Arbiter.scala:154）
        # 即请求向量的或归约。
        m.d.comb += self.ports["io_out_valid"].eq(prefix)
        for field, width in spec.output_layout:
            value: Any = None
            for index in reversed(spec.order()):
                if spec.carries(index, field):
                    source: Any = self.ports[f"io_in_{index}_bits_{field}"]
                else:
                    # firtool folded the parent's constant drive of a payload
                    # field that the locked port list no longer carries. / firtool
                    # 折叠了锁定端口列表不再携带的载荷字段的父级常量驱动。
                    source = Const(spec.tie_off(index, field), width)
                value = source if value is None else Mux(valid[index], source, value)
            m.d.comb += self.ports[f"io_out_bits_{field}"].eq(value)
        if spec.chosen_width:
            order = spec.order()
            # ``io.chosen := (n-1)`` overridden from the highest priority input
            # downwards (Arbiter.scala:142-147). / ``io.chosen := (n-1)``，再按
            # 优先级从高到低覆盖（Arbiter.scala:142-147）。
            chosen: Any = Const(order[-1], spec.chosen_width)
            for index in reversed(order[:-1]):
                chosen = Mux(valid[index], Const(index, spec.chosen_width), chosen)
            m.d.comb += self.ports["io_chosen"].eq(chosen)
        return m


class AsyncResetSynchronizerShiftReg(Elaboratable):
    """Async-reset synchroniser chain of ``sync`` flip-flops per payload bit. / 每载荷位 ``sync`` 级触发器的异步复位同步链。"""

    # Create the ports of one primitive chain or one composed width slice. / 创建一个原始链或一个组合位宽切片的端口。
    def __init__(self, spec: ShiftRegSpec) -> None:
        self.spec = spec
        self.ports: dict[str, Signal] = {}
        self.clock = declare_port(self.ports, "clock", 1)
        self.reset = declare_port(self.ports, "reset", 1)
        self.io_d = declare_port(self.ports, "io_d", spec.width)
        self.io_q = declare_port(self.ports, "io_q", spec.width)
        self.children: list[AsyncResetSynchronizerShiftReg] = []

    # Elaborate the per-bit chains or the primitive instantiations. / 展开逐位链或原始实例。
    def elaborate(self, platform: Any) -> Module:
        del platform
        spec = self.spec
        m = Module()
        if spec.primitive:
            # Only the primitive chain holds registers, so only it declares the
            # asynchronously reset domain; the composed wrapper stays domain
            # free and inherits the chains' domains. / 只有原始链持有寄存器，因此
            # 只有它声明异步复位域；组合包装本身不声明域，只继承各链的域。
            domain = ClockDomain("async_reset_sync", async_reset=True)
            domain.clk = self.clock
            domain.rst = self.reset
            m.domains.async_reset_sync = domain
            # ``chain.last := io.d``, then ``chain(i) := chain(i+1)`` and finally
            # ``io.q := chain.head`` (SynchronizerReg.scala:50-59). /
            # 先 ``chain.last := io.d``，再 ``chain(i) := chain(i+1)``，最后
            # ``io.q := chain.head``（SynchronizerReg.scala:50-59）。
            init_bit = spec.init & 1
            chain = [Signal(1, name=f"sync_{position}", reset=init_bit) for position in range(spec.sync)]
            m.d.async_reset_sync += chain[-1].eq(self.io_d[0])
            for sink, source in zip(chain, chain[1:]):
                m.d.async_reset_sync += sink.eq(source)
            m.d.comb += self.io_q.eq(chain[0])
        else:
            # ``AsyncResetSynchronizerShiftReg`` is W one-bit primitives whose
            # outputs concatenate most significant bit first
            # (SynchronizerReg.scala:84-90). / ``AsyncResetSynchronizerShiftReg``
            # 由 W 个一位原始链组成，输出按高位在前拼接
            # （SynchronizerReg.scala:84-90）。
            outputs: list[Signal] = []
            for position in range(spec.width):
                bit = (spec.init >> position) & 1
                child = AsyncResetSynchronizerShiftReg(ShiftRegSpec(
                    name=f"{spec.name}_chain_{position}", width=1, sync=spec.sync,
                    init=bit, primitive=True))
                # firtool names the first chain ``output_chain`` and the rest
                # ``output_chain_N`` (SynchronizerReg.scala:84-90). / firtool 将首条
                # 链命名为 ``output_chain``，其余为 ``output_chain_N``
                # （SynchronizerReg.scala:84-90）。
                label = "output_chain" if position == 0 else f"output_chain_{position}"
                setattr(m.submodules, label, child)
                m.d.comb += [child.clock.eq(self.clock), child.reset.eq(self.reset),
                             child.io_d.eq(self.io_d[position])]
                outputs.append(child.io_q)
                self.children.append(child)
            m.d.comb += self.io_q.eq(Cat(*outputs))
        return m


class AsyncValidSync(Elaboratable):
    """Handshake synchroniser wrapping one single-bit async-reset shift register. / 握手同步器，内部为一条单位异步复位移位链。"""

    # Create the handshake ports of one synchroniser. / 创建一个同步器的握手端口。
    def __init__(self, spec: AsyncValidSyncSpec) -> None:
        self.spec = spec
        self.ports: dict[str, Signal] = {}
        self.io_in = declare_port(self.ports, "io_in", 1)
        self.io_out = declare_port(self.ports, "io_out", 1)
        self.clock = declare_port(self.ports, "clock", 1)
        self.reset = declare_port(self.ports, "reset", 1)

    # Elaborate the underlying async-reset shift register chain. / 展开底层异步复位移位寄存器链。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        # ``AsyncValidSync`` is a thin wrapper whose only child is the one-bit
        # ``AsyncResetSynchronizerShiftReg`` named after ``io.out``
        # (AsyncQueue.scala:59-66). / ``AsyncValidSync`` 是薄包装，唯一子实例是
        # 以 ``io.out`` 命名的一位 ``AsyncResetSynchronizerShiftReg``
        # （AsyncQueue.scala:59-66）。
        child = AsyncResetSynchronizerShiftReg(ShiftRegSpec(
            name=f"AsyncResetSynchronizerShiftReg_w1_d{self.spec.sync}_i0", width=1,
            sync=self.spec.sync, init=0, primitive=False))
        m.submodules.io_out_source_valid_0 = child
        m.d.comb += [child.clock.eq(self.clock), child.reset.eq(self.reset),
                     child.io_d.eq(self.io_in), self.io_out.eq(child.io_q)]
        return m


class ClockCrossingReg(Elaboratable):
    """Single-depth enable-gated clock-crossing register without reset. / 无复位、带使能的单级跨时钟寄存器。"""

    # Create the ports of one crossing register. / 创建一个跨时钟寄存器的端口。
    def __init__(self, spec: ClockCrossingSpec) -> None:
        self.spec = spec
        self.ports: dict[str, Signal] = {}
        self.clock = declare_port(self.ports, "clock", 1)
        self.io_d = declare_port(self.ports, "io_d", spec.width)
        self.io_q = declare_port(self.ports, "io_q", spec.width)
        self.io_en = declare_port(self.ports, "io_en", 1)

    # Elaborate ``RegEnable(io.d, io.en)`` with no reset. / 展开无复位的 ``RegEnable(io.d, io.en)``。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        domain = ClockDomain("clock_crossing")
        domain.clk = self.clock
        domain.rst = None
        m.domains.clock_crossing = domain
        # ``ClockCrossingReg(w, doInit = false)`` is ``RegEnable(io.d, io.en)``
        # whose contents are explicitly never reset (SynchronizerReg.scala:201). /
        # ``ClockCrossingReg(w, doInit = false)`` 即 ``RegEnable(io.d, io.en)``，
        # 其内容明确不复位（SynchronizerReg.scala:201）。
        register = Signal(self.spec.width, reset_less=True)
        with amaranth_if(m, self.io_en):
            m.d.clock_crossing += register.eq(self.io_d)
        m.d.comb += self.io_q.eq(register)
        return m


class AsyncQueueSource(Elaboratable):
    """Rocket-Chip asynchronous queue source with Gray-coded pointers. / Rocket-Chip 异步队列源，格雷码指针。"""

    # Create the exact locked port set of one queue source instance. / 创建一个队列源实例的精确锁定端口集合。
    def __init__(self, spec: AsyncQueueSourceSpec) -> None:
        self.spec = spec
        self.ports: dict[str, Signal] = {}
        counter_width = spec.index_width() + 1
        self.clock = declare_port(self.ports, "clock", 1)
        self.reset = declare_port(self.ports, "reset", 1)
        if "io_enq_ready" not in spec.omitted_ports:
            declare_port(self.ports, "io_enq_ready", 1)
        declare_port(self.ports, "io_enq_valid", 1)
        for field, width in spec.layout:
            declare_port(self.ports, f"io_enq_bits{field_infix(field)}", width)
        for wire in range(spec.wire_count()):
            for field, width in spec.layout:
                declare_port(self.ports, f"io_async_mem_{wire}{field_infix(field)}", width)
        declare_port(self.ports, "io_async_ridx", counter_width)
        declare_port(self.ports, "io_async_widx", counter_width)
        if spec.narrow:
            declare_port(self.ports, "io_async_index", spec.index_width())
        if spec.safe:
            declare_port(self.ports, "io_async_safe_ridx_valid", 1)
            declare_port(self.ports, "io_async_safe_widx_valid", 1)
            declare_port(self.ports, "io_async_safe_source_reset_n", 1)
            declare_port(self.ports, "io_async_safe_sink_reset_n", 1)

    # Elaborate the memory, the Gray counters and the safe handshake chain. / 展开存储体、格雷计数器与安全握手链。
    def elaborate(self, platform: Any) -> Module:
        del platform
        spec = self.spec
        m = Module()
        domain = ClockDomain("async_queue_source", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.async_queue_source = domain
        bits = spec.index_width()
        counter_width = bits + 1
        index: Signal | None = Signal(bits) if bits else None
        sink_ready: Any
        if spec.safe:
            # ``AsyncQueueSource`` protects both sides with four
            # ``AsyncValidSync`` stages and extends the reset of three of them
            # across the crossing (AsyncQueue.scala:99-131). / ``AsyncQueueSource``
            # 用四级 ``AsyncValidSync`` 保护两侧，并把其中三级的复位跨到对侧
            # （AsyncQueue.scala:99-131）。
            source_valid_0 = AsyncValidSync(AsyncValidSyncSpec(name="source_valid_0", sync=spec.sync))
            source_valid_1 = AsyncValidSync(AsyncValidSyncSpec(name="source_valid_1", sync=spec.sync))
            sink_extend = AsyncValidSync(AsyncValidSyncSpec(name="sink_extend", sync=spec.sync))
            sink_valid = AsyncValidSync(AsyncValidSyncSpec(name="sink_valid", sync=spec.sync))
            reset_extended = Signal()
            m.d.comb += [reset_extended.eq(self.reset | ~self.ports["io_async_safe_sink_reset_n"]),
                         source_valid_0.io_in.eq(1),
                         source_valid_1.io_in.eq(source_valid_0.io_out),
                         sink_valid.io_in.eq(sink_extend.io_out),
                         sink_extend.io_in.eq(self.ports["io_async_safe_ridx_valid"]),
                         self.ports["io_async_safe_widx_valid"].eq(source_valid_1.io_out),
                         self.ports["io_async_safe_source_reset_n"].eq(~self.reset),
                         sink_valid.reset.eq(self.reset)]
            for name, child in (("source_valid_0", source_valid_0), ("source_valid_1", source_valid_1),
                                ("sink_extend", sink_extend), ("sink_valid", sink_valid)):
                setattr(m.submodules, name, child)
                m.d.comb += child.clock.eq(self.clock)
            for child in (source_valid_0, source_valid_1, sink_extend):
                m.d.comb += child.reset.eq(reset_extended)
            sink_ready = sink_valid.io_out
        else:
            sink_ready = Const(1, 1)
        ridx_sync = AsyncResetSynchronizerShiftReg(ShiftRegSpec(
            name=f"AsyncResetSynchronizerShiftReg_w{counter_width}_d{spec.sync}_i0",
            width=counter_width, sync=spec.sync, init=0, primitive=False))
        m.submodules.ridx_ridx_gray = ridx_sync
        m.d.comb += [ridx_sync.clock.eq(self.clock), ridx_sync.reset.eq(self.reset),
                     ridx_sync.io_d.eq(self.ports["io_async_ridx"])]
        memory = {(wire, field): Signal(width, reset_less=True)
                  for wire in range(spec.depth) for field, width in spec.layout}
        # Names follow the locked netlist so equivalence cells pair the same state:
        # widx_widx_bin is the binary write pointer and widx_gray the registered
        # Gray output. The combinational Gray value keeps a distinct name because
        # the locked reference has no such net, and matching it to the register of
        # the same role would compare a combinational signal against a clocked one.
        # 命名对齐锁定网表：组合格雷码另起名，避免与同名寄存器错配。
        widx_bin = Signal(counter_width, reset=0, name="widx_widx_bin")
        widx_incremented = Signal(counter_width, name="widx_incremented")
        widx_gray = Signal(counter_width, name="widx_gray_comb")
        ready_reg = Signal(reset=0, name="ready_reg")
        wide_widx_reg = Signal(counter_width, reset=0, name="widx_gray")
        enq_ready = Signal()
        enq_fire = Signal()
        m.d.comb += [enq_ready.eq(ready_reg & sink_ready),
                     enq_fire.eq(enq_ready & self.ports["io_enq_valid"])]
        # ``GrayCounter(bits + 1, io.enq.fire, !sink_ready)`` clears the binary
        # index while the sink side is not ready (AsyncQueue.scala:49-56, :81). /
        # ``GrayCounter(bits + 1, io.enq.fire, !sink_ready)`` 在 sink 侧未就绪时清零
        # 二进制索引（AsyncQueue.scala:49-56, :81）。
        m.d.comb += widx_incremented.eq(Mux(~sink_ready, 0, widx_bin + enq_fire))
        m.d.comb += widx_gray.eq(widx_incremented ^ (widx_incremented >> 1))
        mask = spec.depth | (spec.depth >> 1)
        ready_comb = Signal()
        m.d.comb += ready_comb.eq(sink_ready & (widx_gray != (ridx_sync.io_q ^ Const(mask, counter_width))))
        m.d.async_queue_source += [widx_bin.eq(widx_incremented), wide_widx_reg.eq(widx_gray),
                                   ready_reg.eq(ready_comb)]
        if index is not None:
            # ``mem(index)`` uses the *registered* Gray write pointer
            # (AsyncQueue.scala:85), so the write lands one cycle after the
            # pointer update. / ``mem(index)`` 使用*已寄存*的格雷写指针
            # （AsyncQueue.scala:85），因此写入发生在指针更新后的下一个周期。
            m.d.comb += index.eq(gray_entry_index(wide_widx_reg, bits))
        for wire in range(spec.depth):
            condition: Any = enq_fire if index is None else (enq_fire & (index == wire))
            with amaranth_if(m, condition):
                m.d.async_queue_source += [
                    memory[(wire, field)].eq(self.ports[f"io_enq_bits{field_infix(field)}"])
                    for field, _ in spec.layout]
        if spec.narrow:
            # The narrow source moves the read mux across the crossing: the sink
            # drives ``io.async.index`` and only the selected entry is exported
            # (AsyncQueue.scala:24, :75, :89-92). / 窄源把读多路搬到跨时钟另一侧：
            # 汇驱动 ``io.async.index``，只导出被选中的条目
            # （AsyncQueue.scala:24, :75, :89-92）。
            selector = self.ports["io_async_index"]
            for field, _ in spec.layout:
                m.d.comb += self.ports[f"io_async_mem_0{field_infix(field)}"].eq(
                    select_mem_field([memory[(wire, field)] for wire in range(spec.depth)], selector))
        else:
            for wire in range(spec.depth):
                for field, _ in spec.layout:
                    m.d.comb += self.ports[f"io_async_mem_{wire}{field_infix(field)}"].eq(memory[(wire, field)])
        if "io_enq_ready" in self.ports:
            m.d.comb += self.ports["io_enq_ready"].eq(enq_ready)
        m.d.comb += self.ports["io_async_widx"].eq(wide_widx_reg)
        return m


class AsyncQueueSink(Elaboratable):
    """Rocket-Chip asynchronous queue sink with a packed crossing register. / Rocket-Chip 异步队列汇，含打包跨时钟寄存器。"""

    # Create the exact locked port set of one queue sink instance. / 创建一个队列汇实例的精确锁定端口集合。
    def __init__(self, spec: AsyncQueueSinkSpec) -> None:
        self.spec = spec
        self.ports: dict[str, Signal] = {}
        counter_width = spec.index_width() + 1
        self.clock = declare_port(self.ports, "clock", 1)
        self.reset = declare_port(self.ports, "reset", 1)
        if "io_deq_ready" not in spec.omitted_ports:
            declare_port(self.ports, "io_deq_ready", 1)
        declare_port(self.ports, "io_deq_valid", 1)
        for field, msb, lsb in spec.deq_slices:
            declare_port(self.ports, f"io_deq_bits{field_infix(field)}", msb - lsb + 1)
        for wire in range(spec.wire_count()):
            for field, width in spec.layout:
                declare_port(self.ports, f"io_async_mem_{wire}{field_infix(field)}", width)
        declare_port(self.ports, "io_async_ridx", counter_width)
        declare_port(self.ports, "io_async_widx", counter_width)
        if spec.narrow:
            declare_port(self.ports, "io_async_index", spec.index_width())
        if spec.safe:
            declare_port(self.ports, "io_async_safe_ridx_valid", 1)
            declare_port(self.ports, "io_async_safe_widx_valid", 1)
            declare_port(self.ports, "io_async_safe_source_reset_n", 1)
            declare_port(self.ports, "io_async_safe_sink_reset_n", 1)

    # Elaborate the read pointer, the payload mux and the safe handshake chain. / 展开读指针、载荷多路与安全握手链。
    def elaborate(self, platform: Any) -> Module:
        del platform
        spec = self.spec
        m = Module()
        domain = ClockDomain("async_queue_sink", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.async_queue_sink = domain
        bits = spec.index_width()
        counter_width = bits + 1
        index: Signal | None = Signal(bits) if bits else None
        source_ready: Any
        if spec.safe:
            # Mirrored protection of the sink side (AsyncQueue.scala:167-199). /
            # sink 侧对称的保护逻辑（AsyncQueue.scala:167-199）。
            sink_valid_0 = AsyncValidSync(AsyncValidSyncSpec(name="sink_valid_0", sync=spec.sync))
            sink_valid_1 = AsyncValidSync(AsyncValidSyncSpec(name="sink_valid_1", sync=spec.sync))
            source_extend = AsyncValidSync(AsyncValidSyncSpec(name="source_extend", sync=spec.sync))
            source_valid = AsyncValidSync(AsyncValidSyncSpec(name="source_valid", sync=spec.sync))
            reset_extended = Signal()
            m.d.comb += [reset_extended.eq(self.reset | ~self.ports["io_async_safe_source_reset_n"]),
                         sink_valid_0.io_in.eq(1),
                         sink_valid_1.io_in.eq(sink_valid_0.io_out),
                         source_valid.io_in.eq(source_extend.io_out),
                         source_extend.io_in.eq(self.ports["io_async_safe_widx_valid"]),
                         self.ports["io_async_safe_ridx_valid"].eq(sink_valid_1.io_out),
                         self.ports["io_async_safe_sink_reset_n"].eq(~self.reset),
                         source_valid.reset.eq(self.reset)]
            for name, child in (("sink_valid_0", sink_valid_0), ("sink_valid_1", sink_valid_1),
                                ("source_extend", source_extend), ("source_valid", source_valid)):
                setattr(m.submodules, name, child)
                m.d.comb += child.clock.eq(self.clock)
            for child in (sink_valid_0, sink_valid_1, source_extend):
                m.d.comb += child.reset.eq(reset_extended)
            source_ready = source_valid.io_out
        else:
            source_ready = Const(1, 1)
        widx_sync = AsyncResetSynchronizerShiftReg(ShiftRegSpec(
            name=f"AsyncResetSynchronizerShiftReg_w{counter_width}_d{spec.sync}_i0",
            width=counter_width, sync=spec.sync, init=0, primitive=False))
        m.submodules.widx_widx_gray = widx_sync
        m.d.comb += [widx_sync.clock.eq(self.clock), widx_sync.reset.eq(self.reset),
                     widx_sync.io_d.eq(self.ports["io_async_widx"])]
        # Internal names mirror the locked netlist so name-matched equivalence cells
        # correspond: ridx_ridx_bin is the binary read pointer, ridx the combinational
        # Gray code of the incremented pointer, and ridx_gray the registered Gray
        # output that drives io_async_ridx.
        # 内部命名对齐锁定网表，按名配对的等价单元才有意义。
        ridx_bin = Signal(counter_width, reset=0, name="ridx_ridx_bin")
        ridx_incremented = Signal(counter_width, name="ridx_incremented")
        ridx_gray = Signal(counter_width, name="ridx")
        valid_reg = Signal(reset=0, name="valid_reg")
        ridx_reg = Signal(counter_width, reset=0, name="ridx_gray")
        valid = Signal()
        deq_ready: Any = (self.ports["io_deq_ready"] if "io_deq_ready" in self.ports
                          else Const(spec.deq_ready_constant or 0, 1))
        deq_fire = Signal()
        m.d.comb += [deq_fire.eq(deq_ready & valid_reg & source_ready),
                     ridx_incremented.eq(Mux(~source_ready, 0, ridx_bin + deq_fire)),
                     ridx_gray.eq(ridx_incremented ^ (ridx_incremented >> 1)),
                     valid.eq(source_ready & (ridx_gray != widx_sync.io_q))]
        m.d.async_queue_sink += [ridx_bin.eq(ridx_incremented), valid_reg.eq(valid),
                                 ridx_reg.eq(ridx_gray)]
        if index is not None:
            # ``index`` uses the combinational Gray counter output here, because
            # the sink reads the entry it is about to release the writer
            # (AsyncQueue.scala:152). / 此处 ``index`` 使用组合的格雷计数器输出，
            # 因为汇读取的是即将向写侧释放的条目（AsyncQueue.scala:152）。
            m.d.comb += index.eq(gray_entry_index(ridx_gray, bits))
        if spec.narrow:
            m.d.comb += self.ports["io_async_index"].eq(index)
        packed: list[Any] = []
        for segment in reversed(spec.pack):
            if segment.field is None:
                # Fields that the locked netlist exposes only as tie-offs inside
                # the crossing word. / 锁定网表仅以跨时钟字内补位形式暴露的字段。
                packed.append(Const(segment.value, segment.width))
                continue
            entries = [self.ports[f"io_async_mem_{wire}{field_infix(segment.field)}"]
                       for wire in range(spec.wire_count())]
            packed.append(entries[0] if spec.narrow or spec.depth == 1
                          else select_mem_field(entries, index))
        crossing = ClockCrossingReg(ClockCrossingSpec(name=f"ClockCrossingReg_w{spec.pack_width()}",
                                                      width=spec.pack_width()))
        m.submodules.io_deq_bits_deq_bits_reg = crossing
        m.d.comb += [crossing.clock.eq(self.clock), crossing.io_d.eq(Cat(*packed)),
                     crossing.io_en.eq(valid)]
        for field, msb, lsb in spec.deq_slices:
            m.d.comb += self.ports[f"io_deq_bits{field_infix(field)}"].eq(crossing.io_q[lsb:msb + 1])
        m.d.comb += [self.ports["io_deq_valid"].eq(valid_reg & source_ready),
                     self.ports["io_async_ridx"].eq(ridx_reg)]
        return m


class Repeater(Elaboratable):
    """Rocket-Chip repeater: pass-through unless ``repeat`` latches a copy. / Rocket-Chip 重复器：``repeat`` 置位时锁存副本重复发送。"""

    # Create the ports of one repeater instance. / 创建一个重复器实例的端口。
    def __init__(self, spec: RepeaterSpec) -> None:
        self.spec = spec
        self.ports: dict[str, Signal] = {}
        self.clock = declare_port(self.ports, "clock", 1)
        self.reset = declare_port(self.ports, "reset", 1)
        declare_port(self.ports, "io_repeat", 1)
        if spec.full_port:
            declare_port(self.ports, "io_full", 1)
        declare_port(self.ports, "io_enq_ready", 1)
        declare_port(self.ports, "io_enq_valid", 1)
        for field, width in spec.layout:
            declare_port(self.ports, f"io_enq_bits{field_infix(field)}", width)
        declare_port(self.ports, "io_deq_ready", 1)
        declare_port(self.ports, "io_deq_valid", 1)
        for field, width in spec.layout:
            declare_port(self.ports, f"io_deq_bits{field_infix(field)}", width)

    # Elaborate the held payload register and the pass-through mux. / 展开保持载荷寄存器与直通多路。
    def elaborate(self, platform: Any) -> Module:
        del platform
        spec = self.spec
        m = Module()
        domain = ClockDomain("repeater", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.repeater = domain
        full = Signal(reset=0)
        saved = {field: Signal(width, reset_less=True) for field, width in spec.layout}
        enq_fire = Signal()
        deq_valid = Signal()
        deq_fire = Signal()
        # ``io.deq.valid := io.enq.valid || full`` and
        # ``io.enq.ready := io.deq.ready && !full`` (Repeater.scala:23-24). /
        # ``io.deq.valid := io.enq.valid || full``，
        # ``io.enq.ready := io.deq.ready && !full``（Repeater.scala:23-24）。
        m.d.comb += [deq_valid.eq(self.ports["io_enq_valid"] | full),
                     self.ports["io_deq_valid"].eq(deq_valid),
                     self.ports["io_enq_ready"].eq(self.ports["io_deq_ready"] & ~full),
                     deq_fire.eq(self.ports["io_deq_ready"] & deq_valid),
                     enq_fire.eq(self.ports["io_enq_ready"] & self.ports["io_enq_valid"])]
        # Chisel last-connect: the unlock statement wins over the lock statement
        # (Repeater.scala:28-29). / Chisel 后写优先：解锁语句覆盖加锁语句
        # （Repeater.scala:28-29）。
        with amaranth_if(m, enq_fire & self.ports["io_repeat"]):
            m.d.repeater += [full.eq(1)] + [saved[field].eq(self.ports[f"io_enq_bits{field_infix(field)}"])
                                            for field, _ in spec.layout]
        with amaranth_if(m, deq_fire & ~self.ports["io_repeat"]):
            m.d.repeater += full.eq(0)
        for field, _ in spec.layout:
            m.d.comb += self.ports[f"io_deq_bits{field_infix(field)}"].eq(
                Mux(full, saved[field], self.ports[f"io_enq_bits{field_infix(field)}"]))
        if spec.full_port:
            m.d.comb += self.ports["io_full"].eq(full)
        return m


class ValidIOBroadcast(Elaboratable):
    """Diplomacy broadcast of one valid/payload bundle to every output. / 将单个 valid/载荷 bundle 广播到全部输出。"""

    # Create the diplomacy-named input and output ports. / 创建 diplomacy 命名的输入与输出端口。
    def __init__(self, spec: BroadcastSpec) -> None:
        self.spec = spec
        self.ports: dict[str, Signal] = {}
        declare_port(self.ports, "auto_in_valid", 1)
        for field, width in spec.layout:
            declare_port(self.ports, f"auto_in_bits_{field}", width)
        for output in range(spec.outputs):
            suffix = "" if spec.outputs == 1 else f"_{output}"
            declare_port(self.ports, f"auto_out{suffix}_valid", 1)
            for field, width in spec.layout:
                declare_port(self.ports, f"auto_out{suffix}_bits_{field}", width)

    # Elaborate the flat valid/payload fan-out. / 展开扁平 valid/载荷扇出。
    def elaborate(self, platform: Any) -> Module:
        del platform
        spec = self.spec
        m = Module()
        # ``o.valid := input.valid`` and ``o.bits := input.bits`` for every
        # downstream bundle (DiplomacyWidget.scala:25-28). / 对每个下游 bundle 执行
        # ``o.valid := input.valid`` 与 ``o.bits := input.bits``
        # （DiplomacyWidget.scala:25-28）。
        for output in range(spec.outputs):
            suffix = "" if spec.outputs == 1 else f"_{output}"
            m.d.comb += self.ports[f"auto_out{suffix}_valid"].eq(self.ports["auto_in_valid"])
            for field, _ in spec.layout:
                m.d.comb += self.ports[f"auto_out{suffix}_bits_{field}"].eq(
                    self.ports[f"auto_in_bits_{field}"])
        return m


class IdPool(Elaboratable):
    """Rocket-Chip identifier pool with an irrevocable select register. / Rocket-Chip 标识池，select 寄存器不可撤销。"""

    # Create the ports of one identifier pool instance. / 创建一个标识池实例的端口。
    def __init__(self, spec: IdPoolSpec) -> None:
        self.spec = spec
        self.ports: dict[str, Signal] = {}
        width = spec.id_width()
        self.clock = declare_port(self.ports, "clock", 1)
        self.reset = declare_port(self.ports, "reset", 1)
        declare_port(self.ports, "io_free_valid", 1)
        declare_port(self.ports, "io_free_bits", width)
        declare_port(self.ports, "io_alloc_ready", 1)
        declare_port(self.ports, "io_alloc_valid", 1)
        declare_port(self.ports, "io_alloc_bits", width)

    # Elaborate the availability bitmap, the select register and the legality asserts. / 展开可用位图、select 寄存器与合法性断言。
    def elaborate(self, platform: Any) -> Module:
        del platform
        spec = self.spec
        m = Module()
        domain = ClockDomain("id_pool", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.id_pool = domain
        width = spec.id_width()
        free_valid = self.ports["io_free_valid"]
        free_bits = self.ports["io_free_bits"]
        alloc_ready = self.ports["io_alloc_ready"]
        bitmap = Signal(spec.num_ids, reset=(1 << spec.num_ids) - 1)
        select = Signal(width, reset=0)
        valid = Signal(reset=1)
        # ``taken``, ``allocated``, ``bitmap1`` and the select/valid update follow
        # IDPool.scala:25-41.  ``alloc.bits`` is the registered ``select`` because
        # ``revocableSelect`` is false, and ``alloc.valid`` is the registered
        # ``valid`` because ``lateValid`` is false. / ``taken``、``allocated``、
        # ``bitmap1`` 与 select/valid 更新遵循 IDPool.scala:25-41；因
        # ``revocableSelect`` 为假，``alloc.bits`` 取寄存的 ``select``；因
        # ``lateValid`` 为假，``alloc.valid`` 取寄存的 ``valid``。
        select_update = Signal()
        taken = Signal(spec.num_ids)
        allocated = Signal(spec.num_ids)
        bitmap1 = Signal(spec.num_ids)
        select1 = Signal(width)
        valid1 = Signal()
        alloc_valid = Signal()
        alloc_bits = Signal(width)
        m.d.comb += [select_update.eq(alloc_ready | (~alloc_valid & free_valid)),
                     alloc_valid.eq(bitmap.any() if spec.late_valid else valid),
                     alloc_bits.eq(select1 if spec.revocable_select else select),
                     taken.eq(Mux(alloc_ready, one_hot_decode(alloc_bits, spec.num_ids), 0)),
                     allocated.eq(Mux(free_valid, one_hot_decode(free_bits, spec.num_ids), 0)),
                     bitmap1.eq((bitmap & ~taken) | allocated),
                     select1.eq(priority_encode(bitmap1, width))]
        m.d.comb += valid1.eq((bitmap.any() & ~((pop_count(bitmap) == 1) & alloc_ready))
                              | free_valid)
        with amaranth_if(m, alloc_ready | free_valid):
            m.d.id_pool += [bitmap.eq(bitmap1), valid.eq(valid1)]
        with amaranth_if(m, select_update):
            m.d.id_pool += select.eq(select1)
        # The three locked assertions are kept: a violated ``$fatal`` is
        # observable in simulation even though it drives no port.
        # IDPool.scala:44 rejects double freeing, :48 ties the registered valid to
        # the bitmap or-reduction, and :52 pins the irrevocable select to the
        # bitmap priority encoder one cycle after a select update. / 三条锁定断言
        # 被保留：被违反的 ``$fatal`` 在仿真中可观测，尽管它不驱动任何端口。
        # IDPool.scala:44 拒绝重复释放，:48 将寄存 valid 绑定到位图或归约，:52 在
        # select 更新后一拍校验不可撤销 select 与位图优先编码器一致。
        select_pipe = Signal(reset_less=True)
        m.d.id_pool += select_pipe.eq(select_update)
        taken_free: Any = (bitmap & ~taken).bit_select(free_bits, 1)
        m.d.comb += [Assert(~free_valid | ~taken_free),
                     Assert(self.reset | (valid == bitmap.any())),
                     Assert(self.reset | ~(valid & select_pipe &
                                           (select != priority_encode(bitmap, width))))]
        m.d.comb += [self.ports["io_alloc_valid"].eq(alloc_valid),
                     self.ports["io_alloc_bits"].eq(alloc_bits)]
        return m


class BundleMapQueue(Elaboratable):
    """Chisel depth-one ``Queue`` over a bundle with an explicit packing order. / 显式打包顺序的单深度 Chisel ``Queue``。"""

    # Create the ports of one depth-one queue specialisation. / 创建一个单深度队列特化的端口。
    def __init__(self, spec: BundleQueueSpec) -> None:
        self.spec = spec
        self.ports: dict[str, Signal] = {}
        self.clock = declare_port(self.ports, "clock", 1)
        self.reset = declare_port(self.ports, "reset", 1)
        declare_port(self.ports, "io_enq_ready", 1)
        declare_port(self.ports, "io_enq_valid", 1)
        for field, width in spec.layout:
            declare_port(self.ports, f"io_enq_bits{field_infix(field)}", width)
        declare_port(self.ports, "io_deq_ready", 1)
        declare_port(self.ports, "io_deq_valid", 1)
        for field, width in spec.layout:
            declare_port(self.ports, f"io_deq_bits{field_infix(field)}", width)

    # Elaborate the single-entry RAM, the full flag and the field slices. / 展开单条目 RAM、full 标志与字段切片。
    def elaborate(self, platform: Any) -> Module:
        del platform
        spec = self.spec
        m = Module()
        domain = ClockDomain("bundle_map_queue", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.bundle_map_queue = domain
        width = sum(field_width for _, field_width in spec.layout)
        # ``Queue(gen, 1)`` keeps the payload in an uninitialised RAM word and
        # tracks occupancy in ``full`` (Decoupled.scala:243-286). /
        # ``Queue(gen, 1)`` 将载荷保存在未初始化 RAM 字中，用 ``full`` 记录占用
        # （Decoupled.scala:243-286）。
        ram = Signal(width, reset_less=True)
        full = Signal(reset=0)
        packed = Cat(*[self.ports[f"io_enq_bits{field_infix(field)}"] for field in reversed(spec.packing)])
        do_enq = Signal()
        m.d.comb += [do_enq.eq(~full & self.ports["io_enq_valid"]),
                     self.ports["io_enq_ready"].eq(~full),
                     self.ports["io_deq_valid"].eq(full)]
        with amaranth_if(m, do_enq):
            m.d.bundle_map_queue += ram.eq(packed)
        with amaranth_if(m, do_enq != (self.ports["io_deq_ready"] & full)):
            m.d.bundle_map_queue += full.eq(do_enq)
        for field, _ in spec.layout:
            msb, lsb = spec.slice_of(field)
            m.d.comb += self.ports[f"io_deq_bits{field_infix(field)}"].eq(ram[lsb:msb + 1])
        return m


# =============================================================================
# Public Adapter
# =============================================================================
# One locked module name paired with its instantiable boundary and port list. / 一个锁定模块名及其可实例化边界与端口列表。
@dataclass(frozen=True)
class FamilySubject:
    """Resolved Build subject: locked name, instance and ordered ports. / 解析后的 Build 主体：锁定名、实例与有序端口。"""

    module: str
    instance: Elaboratable
    ports: tuple[Signal, ...]


# Report every locked module name this Build file covers. / 报告本 Build 文件覆盖的全部锁定模块名。
def covered_modules() -> tuple[str, ...]:
    return tuple(sorted((*ARBITER_SPECS, *ASYNC_QUEUE_SOURCE_SPECS, *ASYNC_QUEUE_SINK_SPECS,
                         *SHIFT_REG_SPECS, *ASYNC_VALID_SYNC_SPECS, *CLOCK_CROSSING_SPECS,
                         *REPEATER_SPECS, *BROADCAST_SPECS, *ID_POOL_SPECS,
                         *BUNDLE_QUEUE_SPECS)))


# Resolve one locked module name into its elaboratable and port list. / 将一个锁定模块名解析为可展开对象与端口列表。
def subject_for(module: str) -> FamilySubject:
    if module in ARBITER_SPECS:
        instance: Elaboratable = StaticArbiter(ARBITER_SPECS[module])
    elif module in ASYNC_QUEUE_SOURCE_SPECS:
        instance = AsyncQueueSource(ASYNC_QUEUE_SOURCE_SPECS[module])
    elif module in ASYNC_QUEUE_SINK_SPECS:
        instance = AsyncQueueSink(ASYNC_QUEUE_SINK_SPECS[module])
    elif module in SHIFT_REG_SPECS:
        instance = AsyncResetSynchronizerShiftReg(SHIFT_REG_SPECS[module])
    elif module in ASYNC_VALID_SYNC_SPECS:
        instance = AsyncValidSync(ASYNC_VALID_SYNC_SPECS[module])
    elif module in CLOCK_CROSSING_SPECS:
        instance = ClockCrossingReg(CLOCK_CROSSING_SPECS[module])
    elif module in REPEATER_SPECS:
        instance = Repeater(REPEATER_SPECS[module])
    elif module in BROADCAST_SPECS:
        instance = ValidIOBroadcast(BROADCAST_SPECS[module])
    elif module in ID_POOL_SPECS:
        instance = IdPool(ID_POOL_SPECS[module])
    elif module in BUNDLE_QUEUE_SPECS:
        instance = BundleMapQueue(BUNDLE_QUEUE_SPECS[module])
    else:
        raise KeyError(f"{module} is outside the arbitration/CDC family boundary")
    ports = getattr(instance, "ports")
    return FamilySubject(module=module, instance=instance, ports=tuple(ports.values()))


# Resolve the adapter configuration argument into one locked module name. / 将适配器配置参数解析为一个锁定模块名。
def resolve_module(configuration: Any) -> str:
    if configuration is None:
        return DEFAULT_SUBJECT_MODULE
    if isinstance(configuration, str):
        return configuration
    if isinstance(configuration, dict):
        for key in ("module", "name", "subject"):
            if key in configuration:
                return str(configuration[key])
        raise KeyError("configuration mapping needs a 'module' entry")
    raise TypeError("configuration must be a locked module name, a mapping, or None")


# Export deterministic Verilog for one covered family instance. / 为一个被覆盖 family 实例导出确定性 Verilog。
def build_verilog(configuration, injected_dependencies):
    """Return the Verilog text of one covered locked module. / 返回一个被覆盖锁定模块的 Verilog 文本。"""

    # This family needs no cross-family dependency: every primitive it uses is
    # defined here, so the injected dependency bag stays unused. / 本 family 无跨
    # family 依赖：所需原语均在本文件内定义，因此注入依赖包不被使用。
    del injected_dependencies
    subject = subject_for(resolve_module(configuration))
    return verilog.convert(subject.instance, name=subject.module,
                           ports=list(subject.ports), emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print the deterministic default export. / 打印确定性的默认导出。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
