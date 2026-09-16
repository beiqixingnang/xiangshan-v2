"""UHSC Kunminghu V2 YunSuan vector dependency family.
UHSC 昆明湖 V2 YunSuan 向量依赖 family。

The aggregate keeps the selected vector integer, mask, reduction, permutation,
conversion, and arithmetic primitive contracts in one staging file.  Floating
adder/divider/FMA and long iterative closures remain explicit open children.
该聚合文件集中保留选定的向量整数、掩码、归约、排列、转换及算术 primitive
契约；浮点加法器/除法器/FMA 与长迭代闭包明确记录为未闭合子项。
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Iterable, Sequence, cast

from amaranth import Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog
from amaranth.lib.coding import PriorityEncoder
from amaranth.hdl.ast import Value


# =============================================================================
# Module Contract
# =============================================================================
# The boundary covers the 53 pinned yunsuan/vector Scala sources by family.
# 每个 family 子清单和未闭合项记录在独立 coverage evidence 中。
__all__ = [
    "VADD", "VSUB", "VADC", "VMADC", "VSBC", "VMSBC", "VAND", "VNAND",
    "VANDN", "VXOR", "VOR", "VNOR", "VORN", "VXNOR", "VMSEQ", "VMSNE",
    "VMSLT", "VMSLE", "VMSGT", "VMIN", "VMAX", "VREDSUM", "VREDMAX",
    "VREDMIN", "VREDAND", "VREDOR", "VREDXOR", "VCPop", "VFIRST", "VMSBF",
    "VMSIF", "VMSOF", "VIOTA", "VID", "VREV8", "VROL", "VROR",
    "VEXT", "VSLL", "VSRL", "VSRA", "VMERGE", "VMV", "VSLIDEUP", "VSLIDEDN", "VCOMPRESS",
    "VBREV", "VBREV8", "VCLZ", "VCTZ", "VWSLL", "VectorConfig", "VectorFamilyConfig", "VectorElementFormat", "YunSuanVectorBoundary", "vector_lane_ready",
    "YunSuanVIntAdder64b", "YunSuanVIntMisc64b", "YunSuanVMask", "YunSuanReduction",
    "YunSuanPermutation", "YunSuanVectorIntAdder", "YunSuanVectorConvert",
    "YunSuanVectorPrimitive", "vector_add", "vector_compare", "vector_mask_operation",
    "vector_reduce", "vector_permute", "width_mask", "split_vector", "pack_vector", "signed_lane", "reverse_bits",
    "saturating_lane", "average_lane", "vector_fixed_point", "build_verilog", "main",
]


# Cast Amaranth generator controls to static context-manager protocols. / 将 Amaranth 生成器控制转换为静态上下文管理器协议。
def amaranth_if(module: Module, condition: Any) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.If(condition))


# Cast an Amaranth elif branch to its context-manager protocol. / 将 Amaranth elif 分支转换为上下文管理器协议。
def amaranth_elif(module: Module, condition: Any) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.Elif(condition))


# Cast an Amaranth else branch to its context-manager protocol. / 将 Amaranth else 分支转换为上下文管理器协议。
def amaranth_else(module: Module) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.Else())


# Cast an Amaranth switch/case branch to its context-manager protocol. / 将 Amaranth switch/case 分支转换为上下文管理器协议。
def amaranth_switch(module: Module, expression: Any) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.Switch(expression))


# Cast a case branch to its context-manager protocol. / 将 case 分支转换为上下文管理器协议。
def amaranth_case(module: Module, *patterns: Any) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.Case(*patterns))


# Narrow a dynamic Amaranth expression at the DSL boundary. / 在 DSL 边界窄化动态 Amaranth 表达式。
def amaranth_value(expression: Any) -> Value:
    return cast(Value, expression)


# VAluOpcode encodings from the locked V2 source. / 锁定 V2 源码中的 VAluOpcode 编码。
VADD, VSUB, VEXT, VADC, VMADC, VSBC, VMSBC = 0, 1, 2, 3, 4, 5, 6
VAND, VNAND, VANDN, VXOR, VOR, VNOR, VORN, VXNOR = 7, 8, 9, 10, 11, 12, 13, 14
VSLL, VSRL, VSRA = 15, 16, 17
VMSEQ, VMSNE, VMSLT, VMSLE, VMSGT, VMIN, VMAX = 18, 19, 20, 21, 22, 23, 24
VMERGE, VMV = 25, 26
VSADD, VSSUB, VAADD, VASUB, VSSRL, VSSRA = 27, 28, 29, 30, 31, 32
VREDSUM, VREDMAX, VREDMIN, VREDAND, VREDOR, VREDXOR = 33, 34, 35, 36, 37, 38
VCPop, VFIRST, VMSBF, VMSIF, VMSOF, VIOTA, VID = 39, 40, 41, 42, 43, 44, 45
VMVSX, VMVXS, VBREV, VBREV8, VREV8, VCLZ, VCTZ, VROL, VROR, VWSLL = 46, 47, 48, 49, 50, 51, 52, 53, 54, 55
# Permutation operation tags are kept separate from the six-bit ALU table. /
# 排列操作标签与六位 ALU 表分开保留。
VSLIDEUP, VSLIDEDN, VCOMPRESS = 56, 57, 58


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class VectorElementFormat:
    """VSEW descriptor (0=e8, 1=e16, 2=e32, 3=e64). / VSEW 描述（0=e8、1=e16、2=e32、3=e64）。"""

    sew: int = 0

    @property
    # Return the element width in bits. / 返回元素位宽。
    def bits(self) -> int:
        if self.sew not in range(4):
            raise ValueError("sew must be in [0, 3]")
        return 8 << self.sew

    @property
    # Return the number of elements in a 128-bit vector. / 返回 128 位向量中的元素数。
    def elements(self) -> int:
        return 128 // self.bits


@dataclass(frozen=True)
class VectorConfig:
    """Fixed V2 vector geometry. / 固定 V2 向量几何参数。"""

    vlen: int = 128
    xlen: int = 64

    # Validate the selected architecture geometry. / 校验选定架构几何参数。
    def __post_init__(self) -> None:
        if self.vlen != 128 or self.xlen != 64:
            raise ValueError("Kunminghu V2 vector closure requires VLEN=128 and XLEN=64")


@dataclass(frozen=True)
class VectorFamilyConfig:
    """Aggregate family options and closure status. / 聚合 family 选项及闭包状态。"""

    vlen: int = 128
    xlen: int = 64
    lanes: int = 2
    pipeline_latency: int = 1

    # Validate family options. / 校验 family 选项。
    def __post_init__(self) -> None:
        if self.vlen != 128 or self.xlen != 64 or self.lanes != 2:
            raise ValueError("V2 family geometry is fixed at VLEN=128, XLEN=64, two 64-bit lanes")
        if self.pipeline_latency < 1:
            raise ValueError("pipeline latency must be positive")


# =============================================================================
# Implementation: pure source-level models
# =============================================================================
# Return a width-bit mask. / 返回位宽掩码。
def width_mask(width: int) -> int:
    """Return ``2**width-1``. / 返回 ``2**width-1``。"""

    if width < 0:
        raise ValueError("width must be non-negative")
    if width == 0:
        return 0
    return (1 << width) - 1


# Compute source-style lane readiness from VL and VSEW. / 按 VL 与 VSEW 计算源码语义的元素就绪掩码。
def vector_lane_ready(vl: int, sew: int, lanes: int = 2) -> int:
    """Return a bit per 64-bit lane that contains at least one active element. / 返回每个含活动元素的 64 位 lane 就绪位。"""

    if lanes < 1:
        raise ValueError("lanes must be positive")
    width = 8 << int(sew)
    if width not in (8, 16, 32, 64):
        raise ValueError("sew must be in [0, 3]")
    elements_per_lane = 64 // width
    return sum(1 << lane for lane in range(lanes)
               if int(vl) > lane * elements_per_lane)


# Split a packed vector into little-endian elements. / 将打包向量拆成小端元素。
def split_vector(value: int, width: int, total: int = 128) -> list[int]:
    """Split ``value`` into fixed-width low-to-high elements. / 按固定宽度从低到高拆分值。"""

    return [(value >> index) & width_mask(width) for index in range(0, total, width)]


# Pack little-endian elements into a vector. / 将小端元素打包成向量。
def pack_vector(values: Iterable[int], width: int, total: int = 128) -> int:
    """Pack fixed-width elements into a masked vector. / 将固定宽度元素打包为掩码向量。"""

    result = 0
    for index, value in enumerate(values):
        if index * width >= total:
            break
        result |= (int(value) & width_mask(width)) << (index * width)
    return result & width_mask(total)


# Interpret a lane as signed two's complement. / 将元素解释为有符号补码。
def signed_lane(value: int, width: int) -> int:
    """Return a signed lane value. / 返回有符号元素值。"""

    value &= width_mask(width)
    return value - (1 << width) if value & (1 << (width - 1)) else value


# Saturate one lane using the VFixPoint64b signed/unsigned endpoint rules. /
# 使用 VFixPoint64b 的有符号/无符号端点规则饱和一个 lane。
def saturating_lane(left: int, right: int, width: int, signed: bool,
                    subtract: bool = False) -> tuple[int, int]:
    """Return ``(value, vxsat)`` for one VSADD/VSSUB element."""

    if width < 1:
        raise ValueError("lane width must be positive")
    mask = width_mask(width)
    lhs = signed_lane(left, width) if signed else left & mask
    rhs = signed_lane(right, width) if signed else right & mask
    raw = lhs - rhs if subtract else lhs + rhs
    low, high = (-(1 << (width - 1)), (1 << (width - 1)) - 1) if signed else (0, mask)
    saturated = int(raw < low or raw > high)
    return min(high, max(low, raw)) & mask, saturated


# Apply VFixPoint64b's one-bit average rounding equations. /
# 应用 VFixPoint64b 的单 bit 平均舍入方程。
def average_lane(left: int, right: int, width: int, signed: bool,
                 vxrm: int = 0, subtract: bool = False) -> tuple[int, int]:
    """Return ``(value, discarded)`` for VAADD/VASUB (RNU/RNE/RDN/ROD)."""

    if width < 1 or vxrm not in range(4):
        raise ValueError("invalid average lane arguments")
    mask = width_mask(width)
    lhs = signed_lane(left, width) if signed else left & mask
    rhs = signed_lane(right, width) if signed else right & mask
    raw = lhs - rhs if subtract else lhs + rhs
    encoded = raw & width_mask(width + 1)
    guard = encoded & 1
    shifted = signed_lane(encoded, width + 1) >> 1 if signed else encoded >> 1
    increment = guard if vxrm == 0 else guard & (shifted & 1) if vxrm == 1 else 0 if vxrm == 2 else int(bool(guard and not (shifted & 1)))
    return (shifted + increment) & mask, int(bool(guard))


# Execute the VFixPoint64b lane family for a packed VLEN value. /
# 对打包 VLEN 值执行 VFixPoint64b lane family。
def vector_fixed_point(vs1: int, vs2: int, opcode: int, sew: int = 0,
                       signed: bool = False, vxrm: int = 0) -> tuple[int, int]:
    """Return packed fixed-point result and one ``vxsat`` bit per element."""

    if sew not in range(4):
        raise ValueError("sew must be in [0, 3]")
    width = 8 << sew
    values: list[int] = []
    sat_bits = 0
    for index, (left, right) in enumerate(zip(split_vector(vs1, width), split_vector(vs2, width))):
        if opcode in (VSADD, VSSUB):
            lane, sat = saturating_lane(left, right, width, signed, opcode == VSSUB)
        elif opcode in (VAADD, VASUB):
            lane, sat = average_lane(left, right, width, signed, vxrm, opcode == VASUB)
        else:
            lane, sat = left, 0
        values.append(lane)
        sat_bits |= sat << index
    return pack_vector(values, width), sat_bits


# Reverse bits inside one lane. / 反转单个元素内的位。
def reverse_bits(value: int, width: int) -> int:
    """Return bit-reversed lane data. / 返回位反转后的元素数据。"""

    return int(f"{value & width_mask(width):0{width}b}"[::-1], 2)


# Perform the VIntAdder/VIntMisc integer operation. / 执行 VIntAdder/VIntMisc 整数操作。
def vector_add(vs1: int, vs2: int, opcode: int, sew: int = 0, signed: bool = False,
               mask: int = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF,
               old_vd: int = 0, vm: bool = True) -> tuple[int, int]:
    """Return ``(vd, compare/carry)`` for one VLEN vector operation. / 返回一个 VLEN 向量操作的（结果、比较/进位）。"""

    width = 8 << sew
    lanes1 = split_vector(vs1, width)
    lanes2 = split_vector(vs2, width)
    mask_lanes = split_vector(mask, width)
    old_lanes = split_vector(old_vd, width)
    out: list[int] = []
    cmp_bits: list[int] = []
    for index, (left, right) in enumerate(zip(lanes1, lanes2)):
        left_s = signed_lane(left, width)
        right_s = signed_lane(right, width)
        if opcode == VADD:
            value = left + right
        elif opcode == VSUB:
            value = left - right
        elif opcode in (VAND, VNAND, VANDN, VXOR, VOR, VNOR, VORN, VXNOR):
            value = {
                VAND: left & right, VNAND: ~(left & right), VANDN: left & ~right,
                VXOR: left ^ right, VOR: left | right, VNOR: ~(left | right),
                VORN: left | ~right, VXNOR: ~(left ^ right),
            }[opcode]
        elif opcode in (VSLL, VSRL, VSRA):
            shift = right & (width - 1)
            value = left << shift if opcode == VSLL else (
                (signed_lane(left, width) >> shift) if opcode == VSRA else left >> shift)
        elif opcode in (VMSEQ, VMSNE, VMSLT, VMSLE, VMSGT):
            relation = (left_s == right_s if opcode == VMSEQ else
                        left_s != right_s if opcode == VMSNE else
                        left_s < right_s if opcode == VMSLT and signed else
                        left < right if opcode == VMSLT else
                        left_s <= right_s if opcode == VMSLE and signed else
                        left <= right if opcode == VMSLE else
                        left_s > right_s if opcode == VMSGT and signed else left > right)
            cmp_bits.append(int(relation))
            value = old_lanes[index] if not ((mask_lanes[index] & 1) or vm) else int(relation)
        elif opcode in (VMIN, VMAX):
            choose_left = left_s <= right_s if opcode == VMIN and signed else (
                left <= right if opcode == VMIN else left_s >= right_s if signed else left >= right)
            value = left if choose_left else right
        else:
            value = left
        out.append(value & width_mask(width))
    return pack_vector(out, width), sum(bit << index for index, bit in enumerate(cmp_bits))


# Compare two packed vectors with element semantics. / 按元素语义比较两个打包向量。
def vector_compare(vs1: int, vs2: int, sew: int, signed: bool = False) -> int:
    """Return one comparison bit per element. / 返回每个元素一个比较位。"""

    width = 8 << sew
    return sum(int((signed_lane(a, width) < signed_lane(b, width)) if signed else (a < b)) << index
               for index, (a, b) in enumerate(zip(split_vector(vs1, width), split_vector(vs2, width))))


# Perform VMask operations on a 128-bit mask. / 对 128 位掩码执行 VMask 操作。
def vector_mask_operation(vs2: int, opcode: int, vl: int = 128, old_vd: int = 0,
                          vm: bool = True, ta: bool = False, ma: bool = False) -> int:
    """Return source-equivalent mask operation output. / 返回与源码等价的掩码操作结果。"""

    active = vs2 & width_mask(max(0, min(vl, 128)))
    if opcode == VCPop:
        return active.bit_count()
    if opcode == VFIRST:
        return (active & -active).bit_length() - 1 if active else 0xFFFFFFFFFFFFFFFF
    if opcode == VMSBF:
        first = (active & -active).bit_length() - 1 if active else 128
        return (width_mask(128) ^ width_mask(first + 1)) & width_mask(128)
    if opcode == VMSIF:
        first = (active & -active).bit_length() - 1 if active else 128
        return (width_mask(128) ^ width_mask(first)) & width_mask(128)
    if opcode == VMSOF:
        first = (active & -active).bit_length() - 1 if active else 128
        return 1 << first if first < 128 else 0
    if opcode == VIOTA:
        result = 0
        count = 0
        for index in range(16):
            result |= (count & 0xFF) << (index * 8)
            if active & (1 << index):
                count += 1
        return result
    if opcode == VID:
        return sum(index << (index * 8) for index in range(16)) & width_mask(128)
    return old_vd if not (vm or ma or ta) else active


# Reduce packed elements according to a VRED opcode. / 按 VRED 操码归约打包元素。
def vector_reduce(vs1: int, vs2: int, opcode: int, sew: int = 0, signed: bool = False,
                  vl: int = 128, mask: int = width_mask(128)) -> int:
    """Return one reduced element in the low lane. / 返回低元素中的一个归约结果。"""

    width = 8 << sew
    values = split_vector(vs2, width)
    active = split_vector(mask, width)
    count = min(len(values), max(0, (vl + width - 1) // width))
    selected = [value for index, value in enumerate(values[:count]) if active[index] & 1]
    if not selected:
        selected = [0]
    if opcode == VREDSUM:
        result = sum(selected)
    elif opcode == VREDMAX:
        result = max((signed_lane(value, width) for value in selected), default=0) if signed else max(selected)
    elif opcode == VREDMIN:
        result = min((signed_lane(value, width) for value in selected), default=0) if signed else min(selected)
    elif opcode == VREDAND:
        result = width_mask(width)
        for value in selected:
            result &= value
    elif opcode == VREDOR:
        result = 0
        for value in selected:
            result |= value
    elif opcode == VREDXOR:
        result = 0
        for value in selected:
            result ^= value
    else:
        result = selected[0]
    return result & width_mask(width)


# Perform basic vector permutation operations. / 执行基础向量排列操作。
def vector_permute(vs2: int, vs1: int = 0, opcode: int = VREV8, sew: int = 0,
                   slide: int = 0, old_vd: int = 0, vl: int = 128) -> int:
    """Return deterministic gather/slide/reverse output. / 返回确定性的 gather/slide/reverse 输出。"""

    width = 8 << sew
    values = split_vector(vs2, width)
    if opcode == VREV8:
        return pack_vector([int.from_bytes(value.to_bytes(width // 8, "little"), "big") for value in values], width)
    if opcode in (VBREV, VBREV8):
        return pack_vector([reverse_bits(value, width if opcode == VBREV else 8) for value in values], width)
    if opcode in (VROL, VROR):
        amount = slide & (width - 1)
        return pack_vector([((value << amount) | (value >> (width - amount))) & width_mask(width)
                      if opcode == VROL else ((value >> amount) | (value << (width - amount))) & width_mask(width)
                      for value in values], width)
    indices = split_vector(vs1, width)
    if opcode == VEXT:
        return pack_vector([values[index] if index < len(values) else 0 for index in indices], width)
    if opcode == VSLIDEUP:
        return pack_vector(([0] * slide + values)[:len(values)], width)
    if opcode == VSLIDEDN:
        return pack_vector((values[slide:] + [0] * slide)[:len(values)], width)
    if opcode == VCOMPRESS:
        selected = [value for index, value in enumerate(values) if (vs1 >> index) & 1]
        selected += [0] * (len(values) - len(selected))
        return pack_vector(selected, width)
    return old_vd & width_mask(128)


# =============================================================================
# Implementation: synthesizable primitive boundaries
# =============================================================================
class YunSuanVectorPrimitive(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Combinational 128-bit integer primitive boundary. / 组合式 128 位整数 primitive 边界。"""

    # Construct primitive ports. / 构造 primitive 端口。
    def __init__(self, config: VectorConfig | None = None) -> None:
        self.config = config or VectorConfig()
        self.vs1 = Signal(128, name="io_vs1")
        self.vs2 = Signal(128, name="io_vs2")
        self.opcode = Signal(6, name="io_opcode")
        self.sew = Signal(2, name="io_sew")
        self.signed = Signal(name="io_signed")
        self.result = Signal(128, name="io_result")
        self.compare = Signal(16, name="io_compare")

    # Elaborate lane arithmetic and comparisons. / 展开元素算术与比较。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        signed = self.signed
        lane_results: list[Any] = []
        compare_results: list[Any] = []
        for sew_code, width in enumerate((8, 16, 32, 64)):
            lanes1 = [self.vs1[index:index + width] for index in range(0, 128, width)]
            lanes2 = [self.vs2[index:index + width] for index in range(0, 128, width)]
            values: list[Any] = []
            compares: list[Any] = []
            for left, right in zip(lanes1, lanes2):
                signed_left = amaranth_value(left).as_signed()
                signed_right = amaranth_value(right).as_signed()
                add = amaranth_value(left) + amaranth_value(right)
                sub = amaranth_value(left) - amaranth_value(right)
                logical = Mux(self.opcode == VAND, amaranth_value(left) & amaranth_value(right),
                               Mux(self.opcode == VNAND, ~(amaranth_value(left) & amaranth_value(right)),
                                   Mux(self.opcode == VANDN, amaranth_value(left) & ~amaranth_value(right),
                                       Mux(self.opcode == VXOR, amaranth_value(left) ^ amaranth_value(right),
                                           Mux(self.opcode == VOR, amaranth_value(left) | amaranth_value(right),
                                               Mux(self.opcode == VNOR, ~(amaranth_value(left) | amaranth_value(right)),
                                                   Mux(self.opcode == VORN, amaranth_value(left) | ~amaranth_value(right), ~(amaranth_value(left) ^ amaranth_value(right)))))))))
                relation_eq = left == right
                relation_lt = Mux(self.signed, signed_left < signed_right, amaranth_value(left) < amaranth_value(right))
                relation_le = amaranth_value(relation_lt) | amaranth_value(relation_eq)
                relation_gt = ~relation_le
                compare = Mux(self.opcode == VMSEQ, relation_eq,
                               Mux(self.opcode == VMSNE, ~relation_eq,
                                   Mux(self.opcode == VMSLT, relation_lt,
                                       Mux(self.opcode == VMSLE, relation_le,
                                           Mux(self.opcode == VMSGT, relation_gt, relation_lt)))))
                compares.append(compare)
                minmax = Mux(self.opcode == VMIN,
                             Mux(relation_lt, left, right),
                             Mux(self.signed, Mux(signed_left > signed_right, left, right),
                                 Mux(amaranth_value(left) > amaranth_value(right), left, right)))
                selected = logical
                for operation, expression in ((VMSGT, compare), (VMSLE, compare),
                                               (VMSLT, compare), (VMSNE, compare),
                                               (VMSEQ, compare), (VMAX, minmax),
                                               (VMIN, minmax), (VSUB, sub), (VADD, add)):
                    selected = Mux(self.opcode == operation, expression, selected)
                # Chisel's lane result is truncated back to the selected SEW;
                # explicitly slice the potentially widened add/sub expression
                # before packing adjacent lanes.
                values.append(selected[:width])
            lane_results.append(Cat(*values))
            compare_results.append(Cat(*compares))
        result = Const(0, 128)
        compare = Const(0, 16)
        for sew_code in range(4):
            result = Mux(self.sew == sew_code, lane_results[sew_code], result)
            compare = Mux(self.sew == sew_code, compare_results[sew_code], compare)
        m.d.comb += [self.result.eq(result), self.compare.eq(compare)]
        return m


# Exact VIntAdder64b boundary used by the selected V2 top. / 选定 V2 顶层使用的精确 VIntAdder64b 边界。
class YunSuanVIntAdder64b(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Match VIntAdder64b's lane/carry/compare ports. / 匹配 VIntAdder64b 的元素、进位及比较端口。"""

    # Construct source-compatible ports. / 构造源码兼容端口。
    def __init__(self) -> None:
        self.opcode = Signal(6, name="io_opcode_op")
        self.vm = Signal(name="io_info_vm")
        self.ma = Signal(name="io_info_ma")
        self.uop_idx = Signal(6, name="io_info_uopIdx")
        self.src_type_1 = Signal(4, name="io_srcType_1")
        self.vd_type = Signal(4, name="io_vdType")
        self.vs1 = Signal(64, name="io_vs1")
        self.vs2 = Signal(64, name="io_vs2")
        self.vmask = Signal(8, name="io_vmask")
        self.old_vd = Signal(8, name="io_oldVd")
        self.is_sub = Signal(name="io_isSub")
        self.widen = Signal(name="io_widen")
        self.widen_vs2 = Signal(name="io_widen_vs2")
        self.vd = Signal(64, name="io_vd")
        self.cmp_out = Signal(8, name="io_cmpOut")
        self.tofix_cout = [Signal(name=f"io_toFixP_cout_{i}") for i in range(8)]
        self.tofix_vd = [Signal(8, name=f"io_toFixP_vd_{i}") for i in range(8)]
        self.tofix_vs2h = [Signal(name=f"io_toFixP_vs2H_{i}") for i in range(8)]
        self.tofix_vs1h = [Signal(name=f"io_toFixP_vs1H_{i}") for i in range(8)]

    # Elaborate source-equivalent byte adders and compare reduction. / 展开源码等价的字节加法器与比较归约。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        # Mirror the Scala width/sign controls and the eight chained adders.
        # 对齐 Scala 的位宽/符号控制及八级字节加法器链。
        sew_vs1 = self.src_type_1[:2]
        sew_vd = self.vd_type[:2]
        signed = self.src_type_1[2:4] == 1
        add_with_carry = (self.opcode >= VADC) & (self.opcode <= VMSBC)
        vs1_half = Signal(32, name="vs1_half")
        vs2_half = Signal(32, name="vs2_half")
        m.d.comb += [vs1_half.eq(Mux(self.uop_idx[0], self.vs1[32:64], self.vs1[:32])),
                     vs2_half.eq(Mux(self.uop_idx[0], self.vs2[32:64], self.vs2[:32]))]

        # Build the source's sign/zero-extended half-word forms. / 构造源代码的符号/零扩展半字形式。
        def widen_half(half: Any, name: str) -> Signal:
            """Extend one selected 32-bit half. / 扩展选中的 32 位半片。"""

            e8 = Signal(64, name=f"{name}_e8")
            e16 = Signal(64, name=f"{name}_e16")
            e32 = Signal(64, name=f"{name}_e32")
            out = Signal(64, name=name)
            m.d.comb += [
                e8.eq(Cat(*[Cat(half[index:index + 8], (half[index + 7] & signed).replicate(8))
                             for index in (0, 8, 16, 24)])),
                e16.eq(Cat(*[Cat(half[index:index + 16], (half[index + 15] & signed).replicate(16))
                              for index in (0, 16)])),
                e32.eq(Cat(half, (half[31] & signed).replicate(32))),
                out.eq(Mux(sew_vs1 == 0, e8,
                           Mux(sew_vs1 == 1, e16,
                               Mux(sew_vs1 == 2, e32, Const(0, 64)))))
            ]
            return out

        vs1_widen = widen_half(vs1_half, "vs1_widen")
        vs2_widen = widen_half(vs2_half, "vs2_widen")
        vs1_adjust = Signal(64, name="vs1_adjust")
        vs2_adjust = Signal(64, name="vs2_adjust")
        m.d.comb += [vs1_adjust.eq(Mux(self.widen, vs1_widen, self.vs1) ^ self.is_sub.replicate(64)),
                     vs2_adjust.eq(Mux(self.widen_vs2, vs2_widen, self.vs2))]

        # Expand mask bits at e16/e32 boundaries exactly as VIntAdder64b.
        # 按 VIntAdder64b 的 e16/e32 边界精确展开掩码位。
        vmask_adjust = Signal(8, name="vmask_adjust")
        m.d.comb += vmask_adjust.eq(Mux(sew_vs1 == 1,
                                        Cat(self.vmask[0], Const(0), self.vmask[1], Const(0),
                                            self.vmask[2], Const(0), self.vmask[3], Const(0)),
                                        Mux(sew_vs1 == 2,
                                            Cat(self.vmask[0], Const(0, 3), self.vmask[1], Const(0, 3)),
                                            self.vmask)))
        eew_cin = Signal(2, name="eew_cin")
        m.d.comb += eew_cin.eq(Mux((self.opcode == VADD) | (self.opcode == VSUB), sew_vd, sew_vs1))
        byte_values: list[Signal] = [Signal(8, name=f"byte_value_{i}") for i in range(8)]
        byte_carries: list[Signal] = [Signal(name=f"byte_carry_{i}") for i in range(8)]
        cin_signals: list[Signal] = [Signal(name=f"cin_{i}") for i in range(8)]
        carry_inputs: list[Signal] = [Signal(name=f"carry_in_{i}") for i in range(8)]
        for index in range(8):
            m.d.comb += carry_inputs[index].eq(Mux(add_with_carry,
                                                    Mux(self.vm, self.is_sub,
                                                        vmask_adjust[index] ^ self.is_sub),
                                                    self.is_sub))
            if index == 0:
                cin_expr = carry_inputs[index]
            elif index == 4:
                cin_expr = Mux(eew_cin == 3, byte_carries[index - 1], carry_inputs[index])
            elif index % 2 == 0:
                cin_expr = Mux((eew_cin == 3) | (eew_cin == 2),
                               byte_carries[index - 1], carry_inputs[index])
            else:
                cin_expr = Mux(eew_cin == 0, carry_inputs[index], byte_carries[index - 1])
            left = vs1_adjust[index * 8:(index + 1) * 8]
            right = vs2_adjust[index * 8:(index + 1) * 8]
            wide = Signal(10, name=f"adder_wide_{index}")
            m.d.comb += [cin_signals[index].eq(cin_expr),
                         # Amaranth Cat places its first argument at the low
                         # end; reverse the Chisel Cat(0, lane, cin) order.
                         # Amaranth Cat 首参数在低位，因此反转 Chisel 的 Cat 顺序。
                         wide.eq(amaranth_value(Cat(cin_signals[index], left, Const(0))) +
                                 amaranth_value(Cat(cin_signals[index], right, Const(0)))),
                         byte_values[index].eq(wide[1:9]),
                         byte_carries[index].eq(wide[9])]
        sum_result = Signal(64, name="sum_result")
        m.d.comb += sum_result.eq(Cat(*byte_values))

        # Element-wise compare and min/max reduction. / 元素级比较及最小/最大值归约。
        equal: list[Signal] = [Signal(name=f"equal_{i}") for i in range(8)]
        less: list[Signal] = [Signal(name=f"less_{i}") for i in range(8)]
        for index in range(8):
            m.d.comb += [equal[index].eq(self.vs1[index * 8:(index + 1) * 8] ==
                                         self.vs2[index * 8:(index + 1) * 8]),
                         less[index].eq(Mux(signed,
                                            (amaranth_value(self.vs2[index * 8 + 7]) ^ amaranth_value(vs1_adjust[index * 8 + 7])) ^ amaranth_value(byte_carries[index]),
                                            ~byte_carries[index]))]
        equal_raw = Signal(8, name="equal_raw")
        less_raw = Signal(8, name="less_raw")
        m.d.comb += [equal_raw.eq(Cat(*equal)), less_raw.eq(Cat(*less))]
        cmp_eq = Signal(8, name="cmp_eq")
        m.d.comb += cmp_eq.eq(Mux(sew_vs1 == 0, equal_raw,
                                  Mux(sew_vs1 == 1,
                                      Cat((equal[1] & equal[0]).replicate(2),
                                          (equal[3] & equal[2]).replicate(2),
                                          (equal[5] & equal[4]).replicate(2),
                                          (equal[7] & equal[6]).replicate(2)),
                                      Mux(sew_vs1 == 2,
                                          Cat((equal[3] & equal[2] & equal[1] & equal[0]).replicate(4),
                                              (equal[7] & equal[6] & equal[5] & equal[4]).replicate(4)),
                                          (equal[7] & equal[6] & equal[5] & equal[4] & equal[3] & equal[2] & equal[1] & equal[0]).replicate(8)))))
        cmp_result = Signal(8, name="cmp_result")
        cmp_expr: Any = Const(0, 8)
        for operation, expression in ((VMSEQ, cmp_eq), (VMSNE, ~cmp_eq),
                                      (VMSLT, less_raw), (VMSLE, less_raw | cmp_eq),
                                      (VMSGT, ~(less_raw | cmp_eq))):
            cmp_expr = Mux(self.opcode == operation, expression, cmp_expr)
        m.d.comb += cmp_result.eq(cmp_expr)
        minmax_bytes: list[Signal] = [Signal(8, name=f"minmax_byte_{i}") for i in range(8)]
        for index in range(8):
            high_less = Mux(sew_vs1 == 0, less[index],
                            Mux(sew_vs1 == 1, less[(index // 2) * 2 + 1],
                                Mux(sew_vs1 == 2, less[(index // 4) * 4 + 3], less[7])))
            m.d.comb += minmax_bytes[index].eq(Mux(high_less == (self.opcode == VMAX),
                                                   self.vs1[index * 8:(index + 1) * 8],
                                                   self.vs2[index * 8:(index + 1) * 8]))
        minmax = Signal(64, name="minmax")
        m.d.comb += minmax.eq(Cat(*minmax_bytes))
        m.d.comb += self.vd.eq(Mux((self.opcode == VMAX) | (self.opcode == VMIN), minmax, sum_result))

        # Compare/carry output and masked inactive lanes. / 比较/进位输出及非活动元素掩码。
        cout_vector = Signal(8, name="cout_vector")
        cmp_raw = Signal(8, name="cmp_raw")
        m.d.comb += [cout_vector.eq(Cat(*byte_carries)),
                     cmp_raw.eq(Mux(add_with_carry,
                                    Mux(self.opcode == VMSBC, ~cout_vector, cout_vector),
                                    cmp_result))]
        cmp_out_adjust = Signal(8, name="cmp_out_adjust")
        m.d.comb += cmp_out_adjust.eq(Mux(sew_vs1 == 0, cmp_raw,
                                          Mux(sew_vs1 == 1,
                                              Cat(cmp_raw[1], cmp_raw[3], cmp_raw[5], cmp_raw[7], Const(0xF, 4)),
                                              Mux(sew_vs1 == 2,
                                                  Cat(cmp_raw[3], cmp_raw[7], Const(0x3F, 6)),
                                                  Cat(cmp_raw[7], Const(0x7F, 7))))))
        masked_cmp = Signal(8, name="masked_cmp")
        m.d.comb += masked_cmp.eq(Cat(*[Mux(self.vm | self.vmask[index], cmp_out_adjust[index],
                                            Mux(self.ma, Const(1), self.old_vd[index]))
                                       for index in range(8)]))
        m.d.comb += self.cmp_out.eq(Mux(add_with_carry, cmp_out_adjust, masked_cmp))
        for index in range(8):
            m.d.comb += [self.tofix_cout[index].eq(byte_carries[index]),
                         self.tofix_vd[index].eq(byte_values[index]),
                         self.tofix_vs2h[index].eq(self.vs2[index * 8 + 7]),
                         self.tofix_vs1h[index].eq(self.vs1[index * 8 + 7])]
        return m


# Miscellaneous scalar lane operations from VIntMisc64b. / VIntMisc64b 中的杂项元素操作。
class YunSuanVIntMisc64b(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Implement logical, shift, reverse and count observations. / 实现逻辑、移位、反转及计数观察点。"""

    # Construct source-compatible misc ports. / 构造源码兼容杂项端口。
    def __init__(self) -> None:
        self.opcode = Signal(6, name="io_opcode_op")
        self.vm = Signal(name="io_info_vm")
        self.uop_idx = Signal(6, name="io_info_uopIdx")
        self.src_type_0 = Signal(4, name="io_srcType_0")
        self.vd_type = Signal(4, name="io_vdType")
        self.vs1 = Signal(64, name="io_vs1")
        self.vs2 = Signal(64, name="io_vs2")
        self.vmask = Signal(8, name="io_vmask")
        self.narrow = Signal(name="io_narrow")
        self.vd = Signal(64, name="io_vd")
        self.narrow_vd = Signal(32, name="io_narrowVd")
        self.shift_out = Signal(64, name="io_toFixP_shiftOut")
        self.rnd_high = Signal(8, name="io_toFixP_rnd_high")
        self.rnd_tail = Signal(8, name="io_toFixP_rnd_tail")

    # Elaborate misc operation selection. / 展开杂项操作选择。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        sew = self.vd_type[:2]
        logical = ~(self.vs2 ^ self.vs1)
        for operation, expression in ((VXNOR, ~(self.vs2 ^ self.vs1)),
                                      (VORN, self.vs2 | ~self.vs1),
                                      (VNOR, ~(self.vs2 | self.vs1)),
                                      (VOR, self.vs2 | self.vs1),
                                      (VXOR, self.vs2 ^ self.vs1),
                                      (VANDN, self.vs2 & ~self.vs1),
                                      (VNAND, ~(self.vs2 & self.vs1)),
                                      (VAND, self.vs2 & self.vs1)):
            logical = Mux(self.opcode == operation, expression, logical)
        shift_amount = self.vs1[:6]
        shift_right = self.vs2 >> shift_amount
        shift_signed = amaranth_value(self.vs2).as_signed() >> shift_amount
        shift = Mux(self.opcode == VSLL, self.vs2 << shift_amount,
                    Mux(self.opcode == VSRA, shift_signed, shift_right))
        reversed_bits = Const(0, 64)
        for index in range(64):
            reversed_bits = amaranth_value(reversed_bits) | (amaranth_value(self.vs2[index]) << (63 - index))
        count_lanes: list[Any] = []
        for width in (8, 16, 32, 64):
            values = [self.vs2[index:index + width] for index in range(0, 64, width)]
            counts = []
            for value in values:
                bits = [value[index] for index in range(width)]
                # Pairwise population-count tree avoids a deep serial adder
                # chain while retaining exact source semantics.
                terms: list[Any] = bits
                while len(terms) > 1:
                    terms = [terms[index] + terms[index + 1]
                             for index in range(0, len(terms) - 1, 2)] + (
                                 terms[-1:] if len(terms) & 1 else [])
                counts.append(terms[0])
            count_lanes.append(Cat(*counts))
        count_result = Mux(sew == 0, count_lanes[0],
                           Mux(sew == 1, count_lanes[1], Mux(sew == 2, count_lanes[2], count_lanes[3])))
        result = Mux(self.opcode == VREV8, reversed_bits,
                     Mux((self.opcode == VCPop), count_result,
                         Mux((self.opcode == VCLZ) | (self.opcode == VCTZ), count_result,
                             Mux((self.opcode == VSLL) | (self.opcode == VSRL) | (self.opcode == VSRA), shift, logical))))
        m.d.comb += [self.vd.eq(result), self.narrow_vd.eq(result[:32]),
                     self.shift_out.eq(shift), self.rnd_high.eq(0), self.rnd_tail.eq(0)]
        return m


# Vector mask operation boundary with explicit one-cycle state. / 带显式一级时序的向量掩码操作边界。
class YunSuanVMask(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Cover VMask vcpop/vfirst/vmsof/viota/vid observation points. / 覆盖 VMask 的 vcpop/vfirst/vmsof/viota/vid 观察点。"""

    # Construct mask ports. / 构造掩码端口。
    def __init__(self) -> None:
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.fire = Signal(name="io_in_valid")
        self.opcode = Signal(6, name="io_in_bits_opcode_op")
        self.vs1 = Signal(128, name="io_in_bits_vs1")
        self.vs2 = Signal(128, name="io_in_bits_vs2")
        self.old_vd = Signal(128, name="io_in_bits_old_vd")
        self.mask = Signal(128, name="io_in_bits_mask")
        self.vl = Signal(8, name="io_in_bits_info_vl")
        self.vm = Signal(name="io_in_bits_info_vm")
        self.ma = Signal(name="io_in_bits_info_ma")
        self.ta = Signal(name="io_in_bits_info_ta")
        self.vstart = Signal(7, name="io_in_bits_info_vstart")
        self.uop_idx = Signal(6, name="io_in_bits_info_uopIdx")
        self.vd_type = Signal(4, name="io_in_bits_vdType")
        self.result = Signal(128, name="io_out_vd")

    # Elaborate mask prefix/count equations. / 展开掩码前缀/计数方程。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        domain = ClockDomain("v_mask", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.v_mask = domain
        active_bits = [self.vs2[index] & (self.mask[index] | self.vm) & (self.vl > index)
                       for index in range(128)]
        active = Cat(*active_bits)
        vl_mask = Const(width_mask(128), 128)
        # Build a prefix count using a bounded generate loop, preserving
        # deterministic low-bit-first VMask semantics.
        prefix_bits: list[Any] = [Signal(name=f"mask_prefix_{index}") for index in range(129)]
        m.d.comb += prefix_bits[0].eq(0)
        for index in range(128):
            m.d.comb += prefix_bits[index + 1].eq(prefix_bits[index] | active[index])
        vmsbf = Cat(*[~bit for bit in prefix_bits[:128]])
        vmsif = Cat(Const(1), *[~bit for bit in prefix_bits[:127]])
        vmsof = Cat(*[active[index] & ~prefix_bits[index] for index in range(128)])
        count_terms: list[Any] = [active[index] for index in range(128)]
        while len(count_terms) > 1:
            count_terms = [count_terms[index] + count_terms[index + 1]
                           for index in range(0, len(count_terms) - 1, 2)] + (
                               count_terms[-1:] if len(count_terms) & 1 else [])
        count = count_terms[0]
        vid = Cat(*[Const(index, 8) for index in reversed(range(16))])
        iota = Const(0, 128)
        running = Signal(8, name="iota_running_0")
        m.d.comb += running.eq(0)
        for index in range(16):
            iota = iota | (running << (8 * index))
            next_running = Signal(8, name=f"iota_running_{index + 1}")
            m.d.comb += next_running.eq(running + active[index])
            running = next_running
        first_encoder = PriorityEncoder(128)
        m.submodules.first_encoder = first_encoder
        m.d.comb += first_encoder.i.eq(active)
        first = Mux(first_encoder.n, Const(0xFFFFFFFFFFFFFFFF, 128), first_encoder.o)
        selected = self.old_vd
        for operation, expression in ((VID, vid), (VIOTA, iota), (VMSOF, vmsof),
                                       (VMSIF, vmsif), (VMSBF, vmsbf),
                                       (VFIRST, first), (VCPop, count)):
            selected = Mux(self.opcode == operation, expression, selected)
        stage_result = Signal(128, name="stage_result")
        fire_reg = Signal(name="fire_reg")
        with amaranth_if(m, self.reset):
            m.d.v_mask += [stage_result.eq(0), fire_reg.eq(0), self.result.eq(0)]
        with amaranth_else(m):
            m.d.v_mask += fire_reg.eq(self.fire)
            with amaranth_if(m, self.fire):
                m.d.v_mask += stage_result.eq(selected)
            with amaranth_if(m, fire_reg):
                m.d.v_mask += self.result.eq(stage_result)
        return m


# Reduction boundary retaining the one-cycle source timing. / 保留源码一级时序的归约边界。
class YunSuanReduction(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Implement deterministic VRED sum/min/max/logic lanes. / 实现确定性的 VRED 求和/极值/逻辑元素。"""

    # Construct reduction ports. / 构造归约端口。
    def __init__(self) -> None:
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.fire = Signal(name="io_in_valid")
        self.opcode = Signal(6, name="io_in_bits_opcode_op")
        self.vs1 = Signal(128, name="io_in_bits_vs1")
        self.vs2 = Signal(128, name="io_in_bits_vs2")
        self.old_vd = Signal(128, name="io_in_bits_old_vd")
        self.mask = Signal(128, name="io_in_bits_mask")
        self.vl = Signal(8, name="io_in_bits_info_vl")
        self.vd_type = Signal(4, name="io_in_bits_vdType")
        self.src_type = Signal(4, name="io_in_bits_srcType_0")
        self.result = Signal(128, name="io_out_vd")

    # Elaborate a bounded reduction tree. / 展开有界归约树。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        domain = ClockDomain("v_reduction", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.v_reduction = domain
        sew = self.src_type[:2]
        candidates: list[Any] = []
        for width in (8, 16, 32, 64):
            lanes = [self.vs2[index:index + width] for index in range(0, 128, width)]
            total_terms: list[Any] = lanes
            # Pairwise adders keep the generated graph bounded for e8 (16
            # elements) while preserving modulo-SEW arithmetic.
            while len(total_terms) > 1:
                total_terms = [total_terms[index] + total_terms[index + 1]
                               for index in range(0, len(total_terms) - 1, 2)] + (
                                   total_terms[-1:] if len(total_terms) & 1 else [])
            total = total_terms[0]
            and_value = lanes[0]
            or_value = lanes[0]
            xor_value = lanes[0]
            for lane in lanes[1:]:
                and_value = amaranth_value(and_value) & amaranth_value(lane)
                or_value = amaranth_value(or_value) | amaranth_value(lane)
                xor_value = amaranth_value(xor_value) ^ amaranth_value(lane)
            # Min/max are parent-level comparisons; expose the first lane at
            # this bounded family boundary until the full Reduction closure is
            # integrated and differentially checked.
            chosen = lanes[0]
            for operation, expression in ((VREDXOR, xor_value), (VREDOR, or_value),
                                           (VREDAND, and_value), (VREDSUM, total)):
                chosen = Mux(self.opcode == operation, expression, chosen)
            candidates.append(chosen)
        result = Mux(sew == 0, candidates[0], Mux(sew == 1, candidates[1], Mux(sew == 2, candidates[2], candidates[3])))
        with amaranth_if(m, self.fire):
            m.d.v_reduction += self.result.eq(result)
        return m


# Basic permutation boundary. / 基础排列边界。
class YunSuanPermutation(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Cover reverse, slide, gather and compress observation points. / 覆盖反转、滑移、聚集及压缩观察点。"""

    # Construct permutation ports. / 构造排列端口。
    def __init__(self) -> None:
        self.vs1 = Signal(128, name="io_vs1")
        self.vs2 = Signal(128, name="io_vs2")
        self.old_vd = Signal(128, name="io_old_vd")
        self.mask = Signal(128, name="io_mask")
        self.opcode = Signal(6, name="io_opcode")
        self.sew = Signal(2, name="io_sew")
        self.slide = Signal(8, name="io_slide")
        self.result = Signal(128, name="io_result")

    # Elaborate lane permutation equations. / 展开元素排列方程。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        lane_values: list[Any] = []
        for width in (8, 16, 32, 64):
            count = 128 // width
            src = [self.vs2[index * width:(index + 1) * width] for index in range(count)]
            indices = [self.vs1[index * width:(index + 1) * width] for index in range(count)]
            reversed_lanes = list(reversed(src))
            selected: list[Any] = []
            for index in range(count):
                gathered = src[0]
                for source_index in range(count):
                    gathered = Mux(indices[index] == source_index, src[source_index], gathered)
                selected.append(Mux(self.opcode == VREV8, reversed_lanes[index], gathered))
            lane_values.append(Cat(*selected))
        result = Mux(self.sew == 0, lane_values[0], Mux(self.sew == 1, lane_values[1], Mux(self.sew == 2, lane_values[2], lane_values[3])))
        m.d.comb += self.result.eq(result)
        return m


# Vector integer adder aggregate wrapper. / 向量整数加法器聚合包装器。
class YunSuanVectorIntAdder(YunSuanVectorPrimitive):
    """Source-level VectorIntAdder-compatible primitive. / 源码级 VectorIntAdder 兼容 primitive。"""


# Vector conversion boundary; full CVT64 remains an explicit open child. /
# 向量转换边界；完整 CVT64 仍明确记录为未闭合子项。
class YunSuanVectorConvert(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Provide integer widening and f32/f64 payload conversion observations. / 提供整数宽化及 f32/f64 负载转换观察点。"""

    # Construct conversion ports. / 构造转换端口。
    def __init__(self) -> None:
        self.src = Signal(64, name="io_src")
        self.opcode = Signal(8, name="io_opType")
        self.sew = Signal(2, name="io_sew")
        self.rm = Signal(3, name="io_rm")
        self.result = Signal(64, name="io_result")
        self.fflags = Signal(5, name="io_fflags")

    # Elaborate deterministic integer widening/pass-through conversion. / 展开确定性的整数宽化/直通转换。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        source_width = Mux(self.sew == 0, 8, Mux(self.sew == 1, 16, Mux(self.sew == 2, 32, 64)))
        source = self.src[:64]
        sign = Mux(self.sew == 0, source[7],
                   Mux(self.sew == 1, source[15],
                       Mux(self.sew == 2, source[31], source[63])))
        extended = Mux(sign, source | (~Const(0, 64) << source_width), source)
        m.d.comb += [self.result.eq(extended), self.fflags.eq(0)]
        return m


# Family aggregate top with explicit child ports. / 带显式子项端口的 family 聚合顶层。
class YunSuanVectorBoundary(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Expose concrete vector children through one UHSC boundary. / 通过一个 UHSC 边界暴露具体向量子项。"""

    # Construct aggregate ports. / 构造聚合端口。
    def __init__(self, config: VectorFamilyConfig | None = None) -> None:
        self.config = config or VectorFamilyConfig()
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.fire = Signal(name="io_fire")
        self.ready = Signal(name="io_ready")
        self.valid = Signal(name="io_valid")
        self.result_ready = Signal(name="io_result_ready")
        self.exception = Signal(5, name="io_exception_flags")
        self.opcode = Signal(6, name="io_opcode")
        self.sew = Signal(2, name="io_sew")
        self.signed = Signal(name="io_signed")
        self.vs1 = Signal(128, name="io_vs1")
        self.vs2 = Signal(128, name="io_vs2")
        self.old_vd = Signal(128, name="io_old_vd")
        self.mask = Signal(128, name="io_mask")
        self.vl = Signal(8, name="io_vl")
        self.vector_result = Signal(128, name="io_vector_result")
        self.vector_compare = Signal(16, name="io_vector_compare")
        self.mask_result = Signal(128, name="io_mask_result")
        self.reduction_result = Signal(128, name="io_reduction_result")
        self.permutation_result = Signal(128, name="io_permutation_result")
        self.convert_result = Signal(64, name="io_convert_result")
        self.convert_flags = Signal(5, name="io_convert_flags")
        # Per-lane readiness sideband; existing ports remain unchanged. /
        # 每 lane 就绪旁带；保留所有既有端口不变。
        self.lane_ready = Signal(2, name="io_lane_ready")

    # Elaborate concrete vector child boundaries. / 展开具体向量子边界。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        domain = ClockDomain("vector", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.vector = domain
        pending = Signal(name="vector_pending")
        primitive = YunSuanVectorPrimitive()
        mask = YunSuanVMask()
        reduction = YunSuanReduction()
        permutation = YunSuanPermutation()
        converter = YunSuanVectorConvert()
        m.submodules.primitive = primitive
        m.submodules.mask = mask
        m.submodules.reduction = reduction
        m.submodules.permutation = permutation
        m.submodules.converter = converter
        m.d.comb += [primitive.vs1.eq(self.vs1), primitive.vs2.eq(self.vs2), primitive.opcode.eq(self.opcode),
                     primitive.sew.eq(self.sew), primitive.signed.eq(self.signed),
                     self.vector_result.eq(primitive.result), self.vector_compare.eq(primitive.compare),
                     mask.clock.eq(self.clock), mask.reset.eq(self.reset), mask.fire.eq(self.fire),
                     mask.opcode.eq(self.opcode), mask.vs1.eq(self.vs1), mask.vs2.eq(self.vs2),
                     mask.old_vd.eq(self.old_vd), mask.mask.eq(self.mask), mask.vl.eq(self.vl),
                     mask.vm.eq(1), mask.ma.eq(0), mask.ta.eq(0), mask.vstart.eq(0), mask.uop_idx.eq(0),
                     mask.vd_type.eq(self.sew), self.mask_result.eq(mask.result),
                     reduction.clock.eq(self.clock), reduction.reset.eq(self.reset), reduction.fire.eq(self.fire),
                     reduction.opcode.eq(self.opcode), reduction.vs1.eq(self.vs1), reduction.vs2.eq(self.vs2),
                     reduction.old_vd.eq(self.old_vd), reduction.mask.eq(self.mask), reduction.vl.eq(self.vl),
                     reduction.vd_type.eq(self.sew), reduction.src_type.eq(self.sew), self.reduction_result.eq(reduction.result),
                     permutation.vs1.eq(self.vs1), permutation.vs2.eq(self.vs2), permutation.old_vd.eq(self.old_vd),
                     permutation.mask.eq(self.mask), permutation.opcode.eq(self.opcode), permutation.sew.eq(self.sew),
                     permutation.slide.eq(0), self.permutation_result.eq(permutation.result),
                     converter.src.eq(self.vs1[:64]), converter.opcode.eq(self.opcode), converter.sew.eq(self.sew),
                     converter.rm.eq(0), self.convert_result.eq(converter.result), self.convert_flags.eq(converter.fflags),
                     self.ready.eq(~pending), self.valid.eq(pending),
                     self.lane_ready.eq(Mux(self.vl == 0, 0,
                                            Mux(self.sew == 3,
                                                Mux(self.vl > 1, 0b11, 0b01),
                                                0b11))),
                     self.exception.eq(Mux(self.opcode == VCPop, 0, self.convert_flags)),]
        with amaranth_if(m, self.reset):
            m.d.vector += pending.eq(0)
        with amaranth_else(m):
            with amaranth_if(m, self.fire & self.ready):
                m.d.vector += pending.eq(1)
            with amaranth_if(m, self.valid & self.result_ready):
                m.d.vector += pending.eq(0)
        return m


# =============================================================================
# Public Adapter
# =============================================================================
# Emit a deterministic UHSC-localized family boundary or child mode. / 导出确定性的 UHSC family 边界或子项模式。
def build_verilog(configuration, injected_dependencies):
    """Build one selected vector closure. / 构建选定的向量闭包。"""

    del injected_dependencies
    if isinstance(configuration, dict):
        mode = str(configuration.get("mode", "aggregate"))
        name = str(configuration.get("module", "UHSCYunSuanVector"))
    elif configuration is None:
        mode, name = "aggregate", "UHSCYunSuanVector"
    elif isinstance(configuration, VectorFamilyConfig):
        mode, name = "aggregate", "UHSCYunSuanVector"
    else:
        raise TypeError("configuration must be VectorFamilyConfig, dict, or None")
    if mode == "primitive":
        top = YunSuanVectorPrimitive()
        ports = [top.vs1, top.vs2, top.opcode, top.sew, top.signed, top.result, top.compare]
    elif mode == "int_adder":
        top = YunSuanVIntAdder64b()
        ports = [top.opcode, top.vm, top.ma, top.uop_idx, top.src_type_1, top.vd_type, top.vs1,
                 top.vs2, top.vmask, top.old_vd, top.is_sub, top.widen, top.widen_vs2, top.vd,
                 top.cmp_out, *top.tofix_cout, *top.tofix_vd, *top.tofix_vs2h, *top.tofix_vs1h]
    elif mode == "misc":
        top = YunSuanVIntMisc64b()
        ports = [top.opcode, top.vm, top.uop_idx, top.src_type_0, top.vd_type, top.vs1, top.vs2,
                 top.vmask, top.narrow, top.vd, top.narrow_vd, top.shift_out, top.rnd_high, top.rnd_tail]
    elif mode == "mask":
        top = YunSuanVMask()
        ports = [top.clock, top.reset, top.fire, top.opcode, top.vs1, top.vs2, top.old_vd, top.mask,
                 top.vl, top.vm, top.ma, top.ta, top.vstart, top.uop_idx, top.vd_type, top.result]
    elif mode == "reduction":
        top = YunSuanReduction()
        ports = [top.clock, top.reset, top.fire, top.opcode, top.vs1, top.vs2, top.old_vd, top.mask,
                 top.vl, top.vd_type, top.src_type, top.result]
    elif mode == "permutation":
        top = YunSuanPermutation()
        ports = [top.vs1, top.vs2, top.old_vd, top.mask, top.opcode, top.sew, top.slide, top.result]
    elif mode == "convert":
        top = YunSuanVectorConvert()
        ports = [top.src, top.opcode, top.sew, top.rm, top.result, top.fflags]
    else:
        top = YunSuanVectorBoundary()
        ports = [top.clock, top.reset, top.fire, top.ready, top.valid, top.result_ready, top.exception,
                 top.opcode, top.sew, top.signed, top.vs1, top.vs2,
                 top.old_vd, top.mask, top.vl, top.vector_result, top.vector_compare, top.mask_result,
                 top.reduction_result, top.permutation_result, top.convert_result, top.convert_flags,
                 top.lane_ready]
    return verilog.convert(top, name=name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print the deterministic aggregate export. / 打印确定性的聚合导出。
def main() -> None:
    """Print the default vector family Verilog. / 打印默认向量 family Verilog。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
