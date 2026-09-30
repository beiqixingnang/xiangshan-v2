"""UHSC Kunminghu V2 YunSuan scalar arithmetic family.
UHSC 昆明湖 V2 YunSuan 标量算术 family。

The five pinned scalar sources are kept behind one explicit family boundary.
该文件将锁定的五个标量源文件置于一个明确的 family 边界之后。
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Mapping, cast

from amaranth import Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog
from amaranth.lib.coding import PriorityEncoder
from amaranth.hdl.ast import Value


# =============================================================================
# Module Contract
# =============================================================================
# The five scalar sources are intentionally exposed as one family boundary. /
# 五个标量源文件有意通过一个 family 边界聚合暴露。

# Source closure: Convert.scala, FPU.scala, IntToFP.scala, RoundingUnit.scala,
# and utils.scala.  The aggregate exposes the source-level primitive contracts,
# integer-to-float pipeline, and an explicit FP conversion boundary.
# 来源闭包：Convert.scala、FPU.scala、IntToFP.scala、RoundingUnit.scala 与
# utils.scala；聚合边界暴露源级 primitive、整数转浮点流水线及显式浮点转换边界。
__all__ = [
    'RNE',
    'RTZ',
    'RDN',
    'RUP',
    'RMM',
    'FType',
    'FloatPoint',
    'FPUConfig',
    'YunSuanScalarConfig',
    'YunSuanFPU',
    'YunSuanRoundingUnit',
    'YunSuanLZA',
    'YunSuanCLZ',
    'YunSuanIntToFPPreNorm',
    'YunSuanIntToFPPostNorm',
    'YunSuanIntToFP',
    'YunSuanINT2FP',
    'YunSuanFPCVT',
    'YunSuanScalarArithmeticPipeline',
    'YunSuanScalarPipe',
    'YunSuanScalarBoundary',
    'FPU',
    'RoundingUnit',
    'LZA',
    'CLZ',
    'IntToFP',
    'INT2FP',
    'FPCVT',
    'rounding_decision',
    'float_classify',
    'fp_exception_flags',
    'leading_zero_count',
    'lza_value',
    'sign_extend',
    'zero_extend',
    'SignExt',
    'ZeroExt',
    'float_box',
    'int_to_float_bits',
    'fp_convert_bits',
    'build_verilog',
    'main',
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


# RISC-V rounding mode encodings used by the pinned scalar source. /
# 锁定标量源码使用的 RISC-V 舍入模式编码。
RNE = 0
RTZ = 1
RDN = 2
RUP = 3
RMM = 4


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class FType:
    """One IEEE-like floating format descriptor. / 一个类 IEEE 浮点格式描述。"""

    exp_width: int
    precision: int

    # Return the stored fraction width. / 返回存储的尾数宽度。
    @property
    # Return the stored fraction width. / 返回存储的尾数宽度。
    def frac_width(self) -> int:
        return self.precision - 1

    # Return the total encoded width. / 返回编码总宽度。
    @property
    # Return the total encoded width. / 返回编码总宽度。
    def width(self) -> int:
        return self.exp_width + self.precision

    # Return the exponent bias. / 返回指数偏置。
    @property
    # Return the exponent bias. / 返回指数偏置。
    def bias(self) -> int:
        return (1 << (self.exp_width - 1)) - 1

    # Return the largest finite biased exponent. / 返回最大有限偏置指数。
    @property
    # Return the largest finite biased exponent. / 返回最大有限偏置指数。
    def max_norm_exp(self) -> int:
        return (1 << self.exp_width) - 2

    @property
    # Expose the source camel-case exponent name for adapters. / 为适配器暴露源码驼峰式指数名称。
    def expWidth(self) -> int:
        return self.exp_width

    @property
    # Expose the source significant-width name for adapters. / 为适配器暴露源码有效位宽名称。
    def sigWidth(self) -> int:
        return self.frac_width

    @property
    # Expose the source total-length name for adapters. / 为适配器暴露源码总长度名称。
    def len(self) -> int:
        return self.width


@dataclass(frozen=True)
class FPUConfig:
    """Configuration for the FPU metadata boundary. / FPU 元数据边界配置。"""

    xlen: int = 64

    # Validate FPU width. / 校验 FPU 位宽。
    def __post_init__(self) -> None:
        if self.xlen != 64:
            raise ValueError("Kunminghu V2 scalar FPU requires XLEN=64")


class FloatPoint:
    """Source-compatible floating exponent helpers. / 源码兼容的浮点指数辅助器。"""

    @staticmethod
    # Return the exponent bias for a format width. / 返回格式位宽对应的指数偏置。
    def expBias(exp_width: int) -> int:
        if exp_width < 2:
            raise ValueError("exponent width must be at least two")
        return (1 << (exp_width - 1)) - 1

    @staticmethod
    # Return the largest finite biased exponent. / 返回最大有限偏置指数。
    def maxNormExp(exp_width: int) -> int:
        if exp_width < 2:
            raise ValueError("exponent width must be at least two")
        return (1 << exp_width) - 2


@dataclass(frozen=True)
class YunSuanScalarConfig:
    """Aggregate geometry for the selected V2 scalar closure. / 选定 V2 标量闭包的聚合几何参数。"""

    xlen: int = 64
    int2fp_latency: int = 2
    rounding_width: int = 52
    default_exp_width: int = 11
    default_precision: int = 53
    arithmetic_latency: int = 3

    # Validate finite source-compatible geometry. / 校验有限且兼容源码的几何参数。
    def __post_init__(self) -> None:
        if self.xlen != 64:
            raise ValueError("scalar closure requires xlen=64")
        if self.int2fp_latency < 2:
            raise ValueError("int2fp latency must be at least two stages")
        if self.rounding_width < 1:
            raise ValueError("rounding width must be positive")
        if self.default_exp_width < 2 or self.default_precision < 2:
            raise ValueError("floating format widths must be positive")
        if self.arithmetic_latency < 1:
            raise ValueError("arithmetic latency must be positive")


# =============================================================================
# Implementation
# =============================================================================
@dataclass(frozen=True)
class YunSuanFPU:
    """Scalar FPU format constants matching FPU.scala. / 匹配 FPU.scala 的标量 FPU 格式常量。"""

    config: FPUConfig = FPUConfig()
    f16: FType = FType(5, 11)
    f32: FType = FType(8, 24)
    f64: FType = FType(11, 53)
    ftypes: tuple[FType, FType, FType] = (FType(5, 11), FType(8, 24), FType(11, 53))
    H: int = 0
    S: int = 1
    D: int = 2

    # Return the half-precision descriptor. / 返回半精度描述。
    @staticmethod
    # Return the half-precision descriptor. / 返回半精度描述。
    def half() -> FType:
        return FType(5, 11)

    # Return the single-precision descriptor. / 返回单精度描述。
    @staticmethod
    # Return the single-precision descriptor. / 返回单精度描述。
    def single() -> FType:
        return FType(8, 24)

    # Return the double-precision descriptor. / 返回双精度描述。
    @staticmethod
    # Return the double-precision descriptor. / 返回双精度描述。
    def double() -> FType:
        return FType(11, 53)

    # Box a narrow float into a 64-bit RISC-V register. / 将窄浮点装箱到 64 位 RISC-V 寄存器。
    @staticmethod
    # Box a narrow float into a 64-bit RISC-V register. / 将窄浮点装箱到 64 位 RISC-V 寄存器。
    def box(value: int, type_tag: int) -> int:
        return float_box(value, type_tag)


# Return a fixed-width sign extension. / 返回固定宽度符号扩展。
def sign_extend(value: int, source_width: int, target_width: int) -> int:
    """Extend a two's-complement value to ``target_width`` bits. / 将补码值扩展到目标位宽。"""

    if source_width < 1 or target_width < 1:
        raise ValueError("widths must be positive")
    source_mask = (1 << source_width) - 1
    value &= source_mask
    if target_width <= source_width:
        return value & ((1 << target_width) - 1)
    if value & (1 << (source_width - 1)):
        value |= ((1 << (target_width - source_width)) - 1) << source_width
    return value & ((1 << target_width) - 1)


# Return a fixed-width zero extension. / 返回固定宽度零扩展。
def zero_extend(value: int, source_width: int, target_width: int) -> int:
    """Extend a value with zeros to ``target_width`` bits. / 使用零将值扩展到目标位宽。"""

    if source_width < 1 or target_width < 1:
        raise ValueError("widths must be positive")
    return value & ((1 << min(source_width, target_width)) - 1)


# Provide the source helper spelling for standalone integer adapters. / 为独立整数适配器提供源码辅助器拼写。
def SignExt(value: int, target_width: int, source_width: int | None = None) -> int:
    """Source-compatible sign extension with optional source width. / 带可选源位宽的源码兼容符号扩展。"""

    width = source_width if source_width is not None else max(1, int(value).bit_length())
    return sign_extend(value, width, target_width)


# Provide the source helper spelling for standalone zero-extension adapters. / 为独立零扩展适配器提供源码辅助器拼写。
def ZeroExt(value: int, target_width: int, source_width: int | None = None) -> int:
    """Source-compatible zero extension with optional source width. / 带可选源位宽的源码兼容零扩展。"""

    width = source_width if source_width is not None else max(1, int(value).bit_length())
    return zero_extend(value, width, target_width)


# Compute the scalar CLZ convention used by Chisel PriorityEncoder. / 计算 Chisel PriorityEncoder 使用的标量 CLZ 约定。
def leading_zero_count(value: int, width: int = 64) -> int:
    """Return a width-minus-one saturated leading-zero count. / 返回饱和到位宽减一的前导零计数。"""

    if width < 1:
        raise ValueError("width must be positive")
    value &= (1 << width) - 1
    for index in range(width - 1, -1, -1):
        if value & (1 << index):
            return width - 1 - index
    return width - 1


# Compute the source LZA recurrence. / 计算源码 LZA 递推。
def lza_value(a: int, b: int, width: int = 64) -> int:
    """Return the bit-exact ``LZA.f`` recurrence. / 返回逐位匹配 ``LZA.f`` 的递推结果。"""

    if width < 1:
        raise ValueError("width must be positive")
    mask = (1 << width) - 1
    a &= mask
    b &= mask
    result = 0
    for index in range(width):
        if index == 0:
            bit = 0
        else:
            p = ((a >> index) ^ (b >> index)) & 1
            k_previous = ((~(a >> (index - 1))) & (~(b >> (index - 1)))) & 1
            bit = p ^ (1 ^ k_previous)
        result |= (bit & 1) << index
    return result & mask


# Evaluate the source rounding decision. / 计算源码舍入决策。
def rounding_decision(value: int, round_in: int, sticky_in: int, sign_in: int,
                      rm: int, width: int) -> tuple[int, int, int, int]:
    """Return ``(rounded, inexact, carry, round_up)``. / 返回（舍入值、不精确、进位、向上舍入）。"""

    if width < 1:
        raise ValueError("rounding width must be positive")
    mask = (1 << width) - 1
    value &= mask
    round_bit = int(bool(round_in))
    sticky_bit = int(bool(sticky_in))
    sign_bit = int(bool(sign_in))
    inexact = round_bit | sticky_bit
    if rm == RNE:
        round_up = round_bit & (sticky_bit | (value & 1))
    elif rm == RTZ:
        round_up = 0
    elif rm == RUP:
        round_up = inexact & (1 - sign_bit)
    elif rm == RDN:
        round_up = inexact & sign_bit
    elif rm == RMM:
        round_up = round_bit
    else:
        round_up = 0
    rounded = (value + round_up) & mask
    carry = int(bool(round_up and value == mask))
    return rounded, inexact, carry, round_up


# Classify an IEEE-like payload using the source FPU exception categories. /
# 按源码 FPU 异常类别对类 IEEE 负载进行分类。
def float_classify(value: int, floating: FType) -> str:
    """Return ``zero``, ``subnormal``, ``normal``, ``inf`` or ``nan``. / 返回 zero、subnormal、normal、inf 或 nan。"""

    payload = int(value) & ((1 << floating.width) - 1)
    exponent = (payload >> floating.frac_width) & ((1 << floating.exp_width) - 1)
    fraction = payload & ((1 << floating.frac_width) - 1)
    if exponent == 0:
        return "zero" if fraction == 0 else "subnormal"
    if exponent == (1 << floating.exp_width) - 1:
        return "inf" if fraction == 0 else "nan"
    return "normal"


# Assemble RISC-V NV/DZ/OF/UF/NX flags from the Convert.scala conditions. /
# 按 Convert.scala 条件组合 RISC-V NV/DZ/OF/UF/NX 标志。
def fp_exception_flags(value: int, floating: FType, *, divide_by_zero: bool = False,
                       overflow: bool = False, underflow: bool = False,
                       inexact: bool = False) -> int:
    """Return FPCVT-style exception bits with signaling-NaN detection.

    Convert.scala propagates invalid for a NaN whose quiet payload bit is zero;
    the remaining inputs model the directly generated DZ/OF/UF/NX equations.
    """

    payload = int(value) & ((1 << floating.width) - 1)
    fraction = payload & ((1 << floating.frac_width) - 1)
    classification = float_classify(payload, floating)
    quiet_bit = (fraction >> max(0, floating.frac_width - 1)) & 1
    invalid = int(classification == "nan" and not quiet_bit)
    return ((invalid << 4) | (int(bool(divide_by_zero)) << 3) |
            (int(bool(overflow)) << 2) | (int(bool(underflow)) << 1) |
            int(bool(inexact)))


# Box f16/f32/f64 payloads as FPU.scala. / 按 FPU.scala 装箱 f16/f32/f64 负载。
def float_box(value: int, type_tag: int) -> int:
    """Return a 64-bit NaN-boxed value. / 返回 64 位 NaN 装箱值。"""

    value &= (1 << 64) - 1
    if type_tag == 2:
        return value
    if type_tag == 1:
        return ((1 << 32) - 1) << 32 | (value & ((1 << 32) - 1))
    if type_tag == 0:
        return ((1 << 48) - 1) << 16 | (value & ((1 << 16) - 1))
    raise ValueError("type_tag must be 0 (f16), 1 (f32), or 2 (f64)")


# Round an integer into one floating format. / 将整数舍入到指定浮点格式。
def int_to_float_bits(value: int, signed: bool, source_width: int,
                      target: FType, rm: int) -> tuple[int, int]:
    """Return encoded bits and RISC-V flags for integer conversion. / 返回整数转换编码及 RISC-V 标志。"""

    if source_width < 1:
        raise ValueError("source width must be positive")
    source_mask = (1 << source_width) - 1
    raw = value & source_mask
    sign = int(bool(signed and (raw & (1 << (source_width - 1)))))
    if sign:
        magnitude = ((~raw) + 1) & source_mask
    else:
        magnitude = raw
    if magnitude == 0:
        return sign << (target.width - 1), 0
    exponent = magnitude.bit_length() - 1
    frac_width = target.frac_width
    if exponent <= frac_width:
        significand = magnitude << (frac_width - exponent)
        inexact = 0
        carry = 0
    else:
        shift = exponent - frac_width
        significand = magnitude >> shift
        remainder = magnitude & ((1 << shift) - 1)
        round_bit = (remainder >> (shift - 1)) & 1
        sticky_bit = int(bool(remainder & ((1 << (shift - 1)) - 1))) if shift > 1 else 0
        significand, inexact, carry, _ = rounding_decision(
            significand, round_bit, sticky_bit, sign, rm, frac_width + 1)
    if carry:
        significand >>= 1
        exponent += 1
    biased = exponent + target.bias
    max_field = (1 << target.exp_width) - 1
    overflow = int(biased >= max_field)
    if overflow:
        rmin = int(rm == RTZ or (sign and rm == RUP) or ((not sign) and rm == RDN))
        if rmin:
            exponent_field = max_field - 1
            fraction = (1 << frac_width) - 1
        else:
            exponent_field = max_field
            fraction = 0
        flags = (overflow << 2) | int(bool(overflow or inexact))
        return (sign << (target.width - 1)) | (exponent_field << frac_width) | fraction, flags
    exponent_field = biased & max_field
    fraction = significand & ((1 << frac_width) - 1)
    flags = int(bool(inexact))
    return (sign << (target.width - 1)) | (exponent_field << frac_width) | fraction, flags


# Convert a floating payload between IEEE-like formats. / 在类 IEEE 格式之间转换浮点负载。
def fp_convert_bits(value: int, source: FType, target: FType, rm: int) -> tuple[int, int]:
    """Return converted payload and flags for finite/exceptional values. / 返回有限值及异常值的转换负载和标志。"""

    source_mask = (1 << source.width) - 1
    value &= source_mask
    sign = (value >> (source.width - 1)) & 1
    source_exp_mask = (1 << source.exp_width) - 1
    source_exp = (value >> source.frac_width) & source_exp_mask
    source_frac = value & ((1 << source.frac_width) - 1)
    target_exp_mask = (1 << target.exp_width) - 1
    target_frac_mask = (1 << target.frac_width) - 1
    if source_exp == source_exp_mask:
        if source_frac:
            payload = source_frac << max(0, target.frac_width - source.frac_width)
            payload |= 1 << max(0, target.frac_width - 1)
            return ((sign << (target.width - 1)) | (target_exp_mask << target.frac_width) |
                    (payload & target_frac_mask)), 1
        return (sign << (target.width - 1)) | (target_exp_mask << target.frac_width), 0
    if source_exp == 0 and source_frac == 0:
        return sign << (target.width - 1), 0
    if source_exp == 0:
        significand = source_frac
        unbiased = 1 - source.bias - source.frac_width
    else:
        significand = (1 << source.frac_width) | source_frac
        unbiased = source_exp - source.bias - source.frac_width
    highest = significand.bit_length() - 1
    value_exponent = highest + unbiased
    if value_exponent > ((1 << target.exp_width) - 2) - target.bias:
        rmin = int(rm == RTZ or (sign and rm == RUP) or ((not sign) and rm == RDN))
        if rmin:
            return ((sign << (target.width - 1)) |
                    ((target_exp_mask - 1) << target.frac_width) | target_frac_mask), 5
        return (sign << (target.width - 1)) | (target_exp_mask << target.frac_width), 5
    # Normal destination path; retain guard/sticky bits while changing precision.
    shift = highest - target.frac_width
    if shift > 0:
        significand_out = significand >> shift
        remainder = significand & ((1 << shift) - 1)
        round_bit = (remainder >> (shift - 1)) & 1
        sticky_bit = int(bool(remainder & ((1 << (shift - 1)) - 1))) if shift > 1 else 0
        significand_out, inexact, carry, _ = rounding_decision(
            significand_out, round_bit, sticky_bit, sign, rm, target.frac_width + 1)
    else:
        significand_out = significand << (-shift)
        inexact = 0
        carry = 0
    if carry:
        significand_out >>= 1
        value_exponent += 1
    biased = value_exponent + target.bias
    if biased >= target_exp_mask:
        rmin = int(rm == RTZ or (sign and rm == RUP) or ((not sign) and rm == RDN))
        if rmin:
            return ((sign << (target.width - 1)) |
                    ((target_exp_mask - 1) << target.frac_width) | target_frac_mask), 5
        return (sign << (target.width - 1)) | (target_exp_mask << target.frac_width), 5
    if biased <= 0:
        # Subnormal conversion is rounded in units of the destination LSB. /
        # 非规格化转换按目标最低有效位单位舍入。
        sub_shift = unbiased - (1 - target.bias - target.frac_width)
        if sub_shift >= 0:
            sub_value = significand << sub_shift
            sub_inexact = 0
        else:
            amount = -sub_shift
            sub_value = significand >> amount
            remainder = significand & ((1 << amount) - 1)
            round_bit = (remainder >> (amount - 1)) & 1
            sticky_bit = int(bool(remainder & ((1 << (amount - 1)) - 1))) if amount > 1 else 0
            sub_value, sub_inexact, _, _ = rounding_decision(
                sub_value, round_bit, sticky_bit, sign, rm, target.frac_width + 1)
        if sub_value >= (1 << target.frac_width):
            return (sign << (target.width - 1)) | (1 << target.frac_width), int(bool(sub_inexact))
        return (sign << (target.width - 1)) | (sub_value & target_frac_mask), int(bool(sub_inexact))
    return ((sign << (target.width - 1)) | ((biased & target_exp_mask) << target.frac_width) |
            (significand_out & target_frac_mask)), int(bool(inexact))


# Build the scalar rounding unit. / 构造标量舍入单元。
class YunSuanRoundingUnit(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Combinational guard/round/sticky unit from RoundingUnit.scala. / 来自 RoundingUnit.scala 的组合 GRS 舍入单元。"""

    # Construct rounding ports. / 构造舍入端口。
    def __init__(self, width: int = 52) -> None:
        if width < 1:
            raise ValueError("rounding width must be positive")
        self.width = width
        self.input = Signal(width, name="io_round_in")
        self.round_in = Signal(name="io_roundIn")
        self.sticky_in = Signal(name="io_stickyIn")
        self.sign_in = Signal(name="io_signIn")
        self.rm = Signal(3, name="io_rm")
        self.output = Signal(width, name="io_round_out")
        self.inexact = Signal(name="io_inexact")
        self.carry_out = Signal(name="io_cout")
        self.round_up = Signal(name="io_r_up")

    # Elaborate the exact RoundingUnit equations. / 展开精确的 RoundingUnit 方程。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        inexact = self.round_in | self.sticky_in
        rne = self.round_in & (self.sticky_in | self.input[0])
        rtz = Const(0)
        rdn = inexact & self.sign_in
        rup = inexact & ~self.sign_in
        rmm = self.round_in
        selected = Mux(self.rm == RNE, rne,
                       Mux(self.rm == RTZ, rtz,
                           Mux(self.rm == RDN, rdn,
                               Mux(self.rm == RUP, rup,
                                   Mux(self.rm == RMM, rmm, Const(0))))))
        m.d.comb += [self.inexact.eq(inexact), self.round_up.eq(selected),
                     self.output.eq(Mux(selected, self.input + 1, self.input)),
                     self.carry_out.eq(selected & self.input.all())]
        return m


# Build the source LZA recurrence. / 构造源码 LZA 递推。
class YunSuanLZA(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Leading-zero anticipator matching scalar utils.scala. / 匹配 scalar utils.scala 的前导零预测器。"""

    # Construct LZA ports. / 构造 LZA 端口。
    def __init__(self, width: int = 64) -> None:
        if width < 1:
            raise ValueError("LZA width must be positive")
        self.width = width
        self.a = Signal(width, name="io_a")
        self.b = Signal(width, name="io_b")
        self.output = Signal(width, name="io_f")

    # Elaborate bitwise p/k/f equations. / 展开逐位 p/k/f 方程。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        bits = []
        for index in range(self.width):
            if index == 0:
                bits.append(Const(0))
            else:
                p = amaranth_value(self.a[index]) ^ amaranth_value(self.b[index])
                k_previous = (~amaranth_value(self.a[index - 1])) & (~amaranth_value(self.b[index - 1]))
                bits.append(p ^ ~k_previous)
        output = Const(0, self.width)
        for index, bit in enumerate(bits):
            output = output | (bit << index)
        m.d.comb += self.output.eq(output)
        return m


# Build the source CLZ convention. / 构造源码 CLZ 约定。
class YunSuanCLZ(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """PriorityEncoder-based leading-zero count. / 基于 PriorityEncoder 的前导零计数器。"""

    # Construct CLZ ports. / 构造 CLZ 端口。
    def __init__(self, width: int = 64, zero: bool = True) -> None:
        if width < 1:
            raise ValueError("CLZ width must be positive")
        del zero
        self.width = width
        self.input = Signal(width, name="io_in")
        self.output = Signal(max(1, (width - 1).bit_length()), name="io_out")

    # Elaborate the high-bit priority encoder. / 展开高位优先编码器。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        out_width = len(self.output)
        encoder = PriorityEncoder(self.width)
        m.submodules.encoder = encoder
        # PriorityEncoder selects the least-significant asserted bit; reversing
        # the input sequence makes that bit the highest asserted source bit,
        # exactly matching ``PriorityEncoder(in.asBools.reverse)`` in Chisel.
        # PriorityEncoder 选择最低位请求；反转输入后即得到 Chisel
        # ``PriorityEncoder(in.asBools.reverse)`` 的最高位优先语义。
        m.d.comb += encoder.i.eq(Cat(*[self.input[self.width - 1 - index]
                                       for index in range(self.width)]))
        m.d.comb += self.output.eq(Mux(encoder.n, Const(self.width - 1, out_width), encoder.o))
        return m


# Build the scalar integer pre-normalizer. / 构造标量整数预规格化单元。
class YunSuanIntToFPPreNorm(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Pre-normalization stage from IntToFP.scala. / 来自 IntToFP.scala 的预规格化阶段。"""

    # Construct pre-normalization ports. / 构造预规格化端口。
    def __init__(self) -> None:
        self.input = Signal(64, name="io_in_int")
        self.signed = Signal(name="io_in_sign")
        self.long = Signal(name="io_in_long")
        self.norm_int = Signal(63, name="io_out_norm_int")
        self.lzc = Signal(6, name="io_out_lzc")
        self.is_zero = Signal(name="io_out_is_zero")
        self.output_sign = Signal(name="io_out_sign")

    # Elaborate source-equivalent sign, LZA and normalization equations. / 展开与源码等价的符号、LZA 及规格化方程。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        in_sign = self.signed & Mux(self.long, self.input[63], self.input[31])
        in_sext = (amaranth_value(self.input[31]).replicate(32) << 32) | amaranth_value(self.input[:32])
        in_raw = Mux(self.signed & ~self.long, in_sext, self.input)
        in_abs = Mux(in_sign, (~in_raw) + 1, in_raw)
        lza = YunSuanLZA(64)
        clz_pos = YunSuanCLZ(64)
        clz_neg = YunSuanCLZ(64)
        m.submodules.lza = lza
        m.submodules.clz_pos = clz_pos
        m.submodules.clz_neg = clz_neg
        m.d.comb += [lza.a.eq(0), lza.b.eq(~in_raw),
                     clz_pos.input.eq(self.input), clz_neg.input.eq(lza.output)]
        lzc = Mux(in_sign, clz_neg.output, clz_pos.output)
        mask_bits = []
        for index in range(64):
            if index == 63:
                mask_bits.append(lza.output[63])
            elif index == 0:
                mask_bits.append(~amaranth_value(lza.output[1:64]).any())
            else:
                mask_bits.append(lza.output[index] & ~amaranth_value(lza.output[index + 1:64]).any())
        one_mask = Const(0, 64)
        for index, bit in enumerate(mask_bits):
            one_mask = one_mask | (bit << index)
        lzc_error = in_sign & ~amaranth_value((in_abs & one_mask)).any()
        shifted = (in_abs << lzc)
        norm = Mux(lzc_error, Cat(Const(0), shifted[:62]), shifted[:63])
        m.d.comb += [self.norm_int.eq(norm), self.lzc.eq(lzc + lzc_error),
                     self.is_zero.eq(~amaranth_value(self.input).any()), self.output_sign.eq(in_sign)]
        return m


# Build the scalar integer post-normalizer. / 构造标量整数后规格化单元。
class YunSuanIntToFPPostNorm(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Post-normalization stage parameterized by destination format. / 按目标格式参数化的后规格化阶段。"""

    # Construct post-normalization ports. / 构造后规格化端口。
    def __init__(self, exp_width: int = 11, precision: int = 53) -> None:
        if exp_width < 2 or precision < 2:
            raise ValueError("invalid floating format")
        self.exp_width = exp_width
        self.precision = precision
        self.norm_int = Signal(63, name="io_in_norm_int")
        self.lzc = Signal(6, name="io_in_lzc")
        self.is_zero = Signal(name="io_in_is_zero")
        self.sign = Signal(name="io_in_sign")
        self.rm = Signal(3, name="io_rm")
        self.result = Signal(exp_width + precision, name="io_result")
        self.fflags = Signal(5, name="io_fflags")

    # Elaborate exponent, GRS and overflow equations. / 展开指数、GRS 与溢出方程。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        frac_width = self.precision - 1
        raw_sig = self.norm_int[63 - frac_width:63]
        round_bit = self.norm_int[63 - frac_width - 1]
        sticky = amaranth_value(self.norm_int[:63 - frac_width - 1]).any()
        rounder = YunSuanRoundingUnit(frac_width)
        m.submodules.rounder = rounder
        m.d.comb += [rounder.input.eq(raw_sig), rounder.round_in.eq(round_bit),
                     rounder.sticky_in.eq(sticky), rounder.sign_in.eq(self.sign),
                     rounder.rm.eq(self.rm)]
        bias = (1 << (self.exp_width - 1)) - 1
        exp_raw = Const(63 + bias, 11) - self.lzc
        fp_exp = Mux(self.is_zero, Const(0, 11), exp_raw + rounder.carry_out)
        max_norm = (1 << self.exp_width) - 2
        flow = fp_exp > Const(max_norm, 11)
        rmin = (self.rm == RTZ) | ((self.sign) & (self.rm == RUP)) | ((~self.sign) & (self.rm == RDN))
        max_finite = (1 << (self.exp_width + self.precision - 1)) - (1 << 0)
        inf_payload = (1 << self.exp_width) - 1
        finite_payload = (max_norm << frac_width) | ((1 << frac_width) - 1)
        normal_payload = (amaranth_value(fp_exp[:self.exp_width]) << frac_width) | amaranth_value(rounder.output)
        payload = Mux(flow, Mux(rmin, Const(finite_payload, self.exp_width + frac_width),
                                Const(inf_payload << frac_width, self.exp_width + frac_width)),
                      normal_payload)
        m.d.comb += [self.result.eq((amaranth_value(self.sign) << (self.exp_width + frac_width)) | amaranth_value(payload)),
                     self.fflags.eq((amaranth_value(flow) << 2) | (amaranth_value(flow) | amaranth_value(rounder.inexact)))]
        del max_finite
        return m


# Build a complete scalar IntToFP converter. / 构造完整标量 IntToFP 转换器。
class YunSuanIntToFP(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Two-stage integer-to-float converter matching scalar IntToFP.scala. / 匹配 scalar IntToFP.scala 的两级整数转浮点转换器。"""

    # Construct converter ports. / 构造转换器端口。
    def __init__(self, exp_width: int = 11, precision: int = 53) -> None:
        self.exp_width = exp_width
        self.precision = precision
        self.input = Signal(64, name="io_int")
        self.signed = Signal(name="io_sign")
        self.long = Signal(name="io_long")
        self.rm = Signal(3, name="io_rm")
        self.result = Signal(exp_width + precision, name="io_result")
        self.fflags = Signal(5, name="io_fflags")

    # Elaborate pre/post normalization stages. / 展开预/后规格化阶段。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        pre = YunSuanIntToFPPreNorm()
        post = YunSuanIntToFPPostNorm(self.exp_width, self.precision)
        m.submodules.pre = pre
        m.submodules.post = post
        m.d.comb += [pre.input.eq(self.input), pre.signed.eq(self.signed), pre.long.eq(self.long),
                     post.norm_int.eq(pre.norm_int), post.lzc.eq(pre.lzc),
                     post.is_zero.eq(pre.is_zero), post.sign.eq(pre.output_sign), post.rm.eq(self.rm),
                     self.result.eq(post.result), self.fflags.eq(post.fflags)]
        return m


# Build the scalar Convert.scala INT2FP pipeline. / 构造 Convert.scala 标量 INT2FP 流水线。
class YunSuanINT2FP(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Latency-parametric integer-to-float pipeline from Convert.scala. / 来自 Convert.scala 的参数化延迟整数转浮点流水线。"""

    # Construct pipeline ports. / 构造流水线端口。
    def __init__(self, latency: int = 2, xlen: int = 64) -> None:
        if latency < 2 or xlen != 64:
            raise ValueError("scalar INT2FP requires latency>=2 and XLEN=64")
        self.latency = latency
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.src = Signal(64, name="io_src")
        self.op_type = Signal(5, name="io_opType")
        self.rm = Signal(3, name="io_rm")
        self.wflags = Signal(name="io_wflags")
        self.rm_inst = Signal(3, name="io_rmInst")
        self.reg_enables = [Signal(name=f"io_regEnables_{index}") for index in range(latency)]
        self.result = Signal(64, name="io_result")
        self.fflags = Signal(5, name="io_fflags")

    # Elaborate stage registers and three destination formats. / 展开阶段寄存器与三种目标格式。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        domain = ClockDomain("scalar_int2fp", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.scalar_int2fp = domain
        selected_rm = Mux(self.rm_inst == 7, self.rm, self.rm_inst)
        in_long = self.op_type[3]
        in_sign = self.op_type[0]
        short_value = (amaranth_value(self.src[31]).replicate(32) << 32) | amaranth_value(self.src[:32])
        int_value_next = Mux(self.wflags, Mux(in_long, self.src, Mux(in_sign, short_value, self.src[:32])), self.src)
        int_value = Signal(64, name="int_value")
        type_in = Signal(name="type_in")
        type_out = Signal(2, name="type_out")
        sign_in = Signal(name="sign_in")
        wflags_reg = Signal(name="wflags_reg")
        rm_reg = Signal(3, name="rm_reg")
        with amaranth_if(m, self.reset):
            m.d.scalar_int2fp += [int_value.eq(0), type_in.eq(0), type_out.eq(0),
                                  sign_in.eq(0), wflags_reg.eq(0), rm_reg.eq(0)]
        with amaranth_elif(m, self.reg_enables[0]):
            m.d.scalar_int2fp += [int_value.eq(int_value_next), type_in.eq(in_long),
                                  type_out.eq(self.op_type[1:3]), sign_in.eq(in_sign),
                                  wflags_reg.eq(self.wflags), rm_reg.eq(selected_rm)]
        converters = []
        for index, (exp_width, precision) in enumerate(((5, 11), (8, 24), (11, 53))):
            converter = YunSuanIntToFP(exp_width, precision)
            m.submodules[f"converter_{index}"] = converter
            m.d.comb += [converter.input.eq(int_value), converter.signed.eq(sign_in),
                         converter.long.eq(type_in), converter.rm.eq(rm_reg)]
            converters.append(converter)
        chosen_data = Mux(type_out == 0, converters[0].result,
                          Mux(type_out == 1, converters[1].result, converters[2].result))
        chosen_flags = Mux(type_out == 0, converters[0].fflags,
                           Mux(type_out == 1, converters[1].fflags, converters[2].fflags))
        data_reg = Signal(64, name="data_reg")
        flags_reg = Signal(5, name="flags_reg")
        tag_reg = Signal(2, name="tag_reg")
        with amaranth_if(m, self.reset):
            m.d.scalar_int2fp += [data_reg.eq(0), flags_reg.eq(0), tag_reg.eq(0)]
        with amaranth_elif(m, self.reg_enables[1]):
            m.d.scalar_int2fp += [data_reg.eq(chosen_data), flags_reg.eq(chosen_flags), tag_reg.eq(type_out)]
        boxed = Mux(tag_reg == 0, (Const((1 << 48) - 1, 64) << 16) | data_reg[:16],
                    Mux(tag_reg == 1, (Const((1 << 32) - 1, 64) << 32) | data_reg[:32], data_reg))
        m.d.comb += [self.result.eq(boxed), self.fflags.eq(flags_reg)]
        return m


# Build an explicit scalar FPCVT boundary. / 构造显式标量 FPCVT 边界。
class YunSuanFPCVT(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """FP conversion boundary with source-compatible two-cycle timing. / 具有源码兼容两周期时序的浮点转换边界。"""

    # Construct FPCVT ports. / 构造 FPCVT 端口。
    def __init__(self, xlen: int = 64) -> None:
        if xlen != 64:
            raise ValueError("FPCVT requires XLEN=64")
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.fire = Signal(name="io_fire")
        self.src = Signal(64, name="io_src")
        self.op_type = Signal(8, name="io_opType")
        self.sew = Signal(2, name="io_sew")
        self.rm = Signal(3, name="io_rm")
        self.is_fround = Signal(2, name="io_isFround")
        self.is_fcvtmod = Signal(name="io_isFcvtmod")
        self.result = Signal(64, name="io_result")
        self.fflags = Signal(5, name="io_fflags")

    # Elaborate format decoding and a deterministic FP conversion datapath. / 展开格式译码及确定性的浮点转换数据通路。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        domain = ClockDomain("scalar_fpcvt", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.scalar_fpcvt = domain
        # Decode source/destination widths exactly as Convert.scala's one-hot PLA. /
        # 精确按 Convert.scala 的 one-hot PLA 译码源/目标宽度。
        widen = amaranth_value(self.op_type[3]) & ~amaranth_value(self.op_type[4])
        narrow = amaranth_value(self.op_type[4]) & ~amaranth_value(self.op_type[3])
        input_width = Signal(7, name="input_width")
        output_width = Signal(7, name="output_width")
        relation_sew = (amaranth_value(self.op_type[4]) << 3) | (amaranth_value(self.op_type[3]) << 2) | amaranth_value(self.sew)
        m.d.comb += [input_width.eq(0), output_width.eq(0)]
        # Input one-hot decoder table copied from Convert.scala. /
        # 复制自 Convert.scala 的输入宽度译码表。
        with amaranth_switch(m, relation_sew):
            with amaranth_case(m, 0b0001):
                m.d.comb += input_width.eq(16)
            with amaranth_case(m, 0b0010):
                m.d.comb += input_width.eq(32)
            with amaranth_case(m, 0b0011):
                m.d.comb += input_width.eq(64)
            with amaranth_case(m, 0b0100):
                m.d.comb += input_width.eq(8)
            with amaranth_case(m, 0b0101):
                m.d.comb += input_width.eq(16)
            with amaranth_case(m, 0b0110):
                m.d.comb += input_width.eq(32)
            with amaranth_case(m, 0b1000):
                m.d.comb += input_width.eq(16)
            with amaranth_case(m, 0b1001):
                m.d.comb += input_width.eq(32)
            with amaranth_case(m, 0b1010):
                m.d.comb += input_width.eq(64)
            with amaranth_case(m, 0b1101):
                m.d.comb += input_width.eq(16)
            with amaranth_case(m, 0b1111):
                m.d.comb += input_width.eq(64)
        # Output one-hot decoder table copied from Convert.scala. /
        # 复制自 Convert.scala 的输出宽度译码表。
        with amaranth_switch(m, relation_sew):
            with amaranth_case(m, 0b0001):
                m.d.comb += output_width.eq(16)
            with amaranth_case(m, 0b0010):
                m.d.comb += output_width.eq(32)
            with amaranth_case(m, 0b0011):
                m.d.comb += output_width.eq(64)
            with amaranth_case(m, 0b0100):
                m.d.comb += output_width.eq(16)
            with amaranth_case(m, 0b0101):
                m.d.comb += output_width.eq(32)
            with amaranth_case(m, 0b0110):
                m.d.comb += output_width.eq(64)
            with amaranth_case(m, 0b1000):
                m.d.comb += output_width.eq(8)
            with amaranth_case(m, 0b1001):
                m.d.comb += output_width.eq(16)
            with amaranth_case(m, 0b1010):
                m.d.comb += output_width.eq(32)
            with amaranth_case(m, 0b1101):
                m.d.comb += output_width.eq(64)
            with amaranth_case(m, 0b1111):
                m.d.comb += output_width.eq(16)
        in_is_fp = self.op_type[7]
        out_is_fp = self.op_type[6]
        # Common finite conversion paths use the f32/f64 payloads.  Unsupported
        # vector-only CVT64 extensions remain visible through ``closure_open`` in
        # the evidence rather than being silently replaced by a constant.
        src_f32 = self.src[:32]
        src_f64 = self.src
        f32_to_f64 = YunSuanFPConvert(8, 24, 11, 53)
        f64_to_f32 = YunSuanFPConvert(11, 53, 8, 24)
        m.submodules.f32_to_f64 = f32_to_f64
        m.submodules.f64_to_f32 = f64_to_f32
        m.d.comb += [f32_to_f64.input.eq(src_f32), f32_to_f64.rm.eq(self.rm),
                     f64_to_f32.input.eq(src_f64), f64_to_f32.rm.eq(self.rm)]
        converted = Mux((amaranth_value(in_is_fp) & amaranth_value(out_is_fp) & (amaranth_value(input_width) == 32) & (amaranth_value(output_width) == 64)), f32_to_f64.output,
                        Mux((amaranth_value(in_is_fp) & amaranth_value(out_is_fp) & (amaranth_value(input_width) == 64) & (amaranth_value(output_width) == 32)),
                            f64_to_f32.output, self.src))
        converted_flags = Mux((amaranth_value(in_is_fp) & amaranth_value(out_is_fp) & (amaranth_value(input_width) == 32) & (amaranth_value(output_width) == 64)), f32_to_f64.flags,
                              Mux((amaranth_value(in_is_fp) & amaranth_value(out_is_fp) & (amaranth_value(input_width) == 64) & (amaranth_value(output_width) == 32)),
                                  f64_to_f32.flags, Const(0, 5)))
        stage_result = Signal(64, name="stage_result")
        stage_flags = Signal(5, name="stage_flags")
        result_reg = Signal(64, name="result_reg")
        flags_reg = Signal(5, name="flags_reg")
        fire_reg = Signal(name="fire_reg")
        with amaranth_if(m, self.reset):
            m.d.scalar_fpcvt += [fire_reg.eq(0), stage_result.eq(0), stage_flags.eq(0),
                                 result_reg.eq(0), flags_reg.eq(0)]
        with amaranth_else(m):
            m.d.scalar_fpcvt += fire_reg.eq(self.fire)
            with amaranth_if(m, self.fire):
                m.d.scalar_fpcvt += [stage_result.eq(converted), stage_flags.eq(converted_flags)]
            with amaranth_if(m, fire_reg):
                m.d.scalar_fpcvt += [result_reg.eq(stage_result), flags_reg.eq(stage_flags)]
        m.d.comb += [self.result.eq(result_reg), self.fflags.eq(flags_reg)]
        del input_width, output_width, out_is_fp
        return m


# Build a small IEEE widening/narrowing helper used by FPCVT. / 构造 FPCVT 使用的小型 IEEE 宽化/窄化辅助单元。
class YunSuanFPConvert(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Combinational f32/f64 payload converter. / 组合式 f32/f64 负载转换器。"""

    # Construct converter ports. / 构造转换器端口。
    def __init__(self, source_exp: int, source_precision: int,
                 target_exp: int, target_precision: int) -> None:
        self.source_width = source_exp + source_precision
        self.target_width = target_exp + target_precision
        self.source_exp = source_exp
        self.source_precision = source_precision
        self.target_exp = target_exp
        self.target_precision = target_precision
        self.input = Signal(self.source_width, name="io_fp_input")
        self.rm = Signal(3, name="io_fp_rm")
        self.output = Signal(self.target_width, name="io_fp_output")
        self.flags = Signal(5, name="io_fp_flags")

    # Elaborate common normal/zero/inf/NaN conversion equations. / 展开常见规格化、零、无穷与 NaN 转换方程。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        src_frac_width = self.source_precision - 1
        dst_frac_width = self.target_precision - 1
        sign = self.input[self.source_width - 1]
        exp = self.input[src_frac_width:self.source_width - 1]
        frac = self.input[:src_frac_width]
        src_exp_max = (1 << self.source_exp) - 1
        is_nan = (exp == src_exp_max) & amaranth_value(frac).any()
        is_inf = (exp == src_exp_max) & ~amaranth_value(frac).any()
        is_zero = (exp == 0) & ~amaranth_value(frac).any()
        # Widening preserves payload bits and shifts the exponent bias. /
        # 宽化保留负载位并调整指数偏置。
        if self.target_width >= self.source_width:
            bias_delta = ((1 << (self.target_exp - 1)) - 1) - ((1 << (self.source_exp - 1)) - 1)
            normal_exp = amaranth_value(exp) + bias_delta
            normal_frac = amaranth_value(frac) << (dst_frac_width - src_frac_width)
            normal = (amaranth_value(sign) << (self.target_width - 1)) | (amaranth_value(normal_exp) << dst_frac_width) | amaranth_value(normal_frac)
            inf = (amaranth_value(sign) << (self.target_width - 1)) | (((1 << self.target_exp) - 1) << dst_frac_width)
            nan_payload = (amaranth_value(frac) << (dst_frac_width - src_frac_width)) | (Const(1, self.target_width) << (dst_frac_width - 1))
            nan = (amaranth_value(sign) << (self.target_width - 1)) | (((1 << self.target_exp) - 1) << dst_frac_width) | amaranth_value(nan_payload)
            zero = Const(0, self.target_width)
            output = Mux(is_nan, nan, Mux(is_inf, inf, Mux(is_zero, amaranth_value(sign) << (self.target_width - 1), normal)))
            m.d.comb += [self.output.eq(output),
                         self.flags.eq(Mux(amaranth_value(is_nan) & ~amaranth_value(frac[src_frac_width - 1]), 16, 0))]
        else:
            # Narrowing uses truncation with a sticky guard and preserves the
            # directed overflow choice.  / 窄化使用带粘滞位的截断并保留定向溢出选择。
            bias_delta = ((1 << (self.source_exp - 1)) - 1) - ((1 << (self.target_exp - 1)) - 1)
            narrow_rounder = YunSuanRoundingUnit(dst_frac_width)
            m.submodules.narrow_rounder = narrow_rounder
            narrow_input = frac[src_frac_width - dst_frac_width:src_frac_width]
            narrow_guard = frac[src_frac_width - dst_frac_width - 1]
            narrow_sticky = amaranth_value(frac[:src_frac_width - dst_frac_width - 1]).any()
            m.d.comb += [narrow_rounder.input.eq(narrow_input),
                         narrow_rounder.round_in.eq(narrow_guard),
                         narrow_rounder.sticky_in.eq(narrow_sticky),
                         narrow_rounder.sign_in.eq(sign), narrow_rounder.rm.eq(self.rm)]
            narrowed_exp = Mux(amaranth_value(exp) > bias_delta, amaranth_value(exp) - bias_delta + amaranth_value(narrow_rounder.carry_out), 0)
            narrowed_frac = narrow_rounder.output
            normal = (amaranth_value(sign) << (self.target_width - 1)) | (amaranth_value(narrowed_exp) << dst_frac_width) | amaranth_value(narrowed_frac)
            inf = (amaranth_value(sign) << (self.target_width - 1)) | (((1 << self.target_exp) - 1) << dst_frac_width)
            nan_payload = (amaranth_value(frac) >> (src_frac_width - dst_frac_width)) | (Const(1, self.target_width) << (dst_frac_width - 1))
            nan = (amaranth_value(sign) << (self.target_width - 1)) | (((1 << self.target_exp) - 1) << dst_frac_width) | amaranth_value(nan_payload)
            zero = amaranth_value(sign) << (self.target_width - 1)
            output = Mux(is_nan, nan, Mux(is_inf, inf, Mux(is_zero, zero, normal)))
            overflow = (~amaranth_value(is_nan)) & (~amaranth_value(is_inf)) & (amaranth_value(narrowed_exp) >= (1 << self.target_exp) - 1)
            narrow_flags = Mux(is_nan, Mux(~amaranth_value(frac[src_frac_width - 1]), 16, 0),
                               Mux(is_inf, 0, (overflow << 2) | (overflow | narrow_rounder.inexact)))
            m.d.comb += [self.output.eq(Mux(overflow, inf, output)), self.flags.eq(narrow_flags)]
        return m


# Build a fixed-latency decoupled scalar arithmetic pipeline. / 构造固定延迟解耦标量算术流水线。
class YunSuanScalarArithmeticPipeline(Elaboratable):
    """Execute scalar integer arithmetic with an elastic valid/ready shell.

    The datapath is deliberately integer-width and deterministic; floating-point
    conversion remains provided by :class:`YunSuanFPCVT`.  Every accepted input
    advances through exactly ``latency`` registers when the sink is ready.  A
    small occupancy scoreboard prevents accepting work after the pipeline is
    full and records protocol underflow/overflow as ``scoreboard_error``.
    """

    # Construct decoupled arithmetic ports and scoreboard state. / 构造解耦算术端口与记分板状态。
    def __init__(self, latency: int = 3, xlen: int = 64) -> None:
        if latency < 1 or xlen != 64:
            raise ValueError("scalar arithmetic requires latency>=1 and XLEN=64")
        self.latency = latency
        self.xlen = xlen
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.in_valid = Signal(name="io_arith_in_valid")
        self.in_ready = Signal(name="io_arith_in_ready")
        self.in_opcode = Signal(4, name="io_arith_in_opcode")
        self.in_signed = Signal(name="io_arith_in_signed")
        self.in_a = Signal(xlen, name="io_arith_in_a")
        self.in_b = Signal(xlen, name="io_arith_in_b")
        self.in_rm = Signal(3, name="io_arith_in_rm")
        self.out_valid = Signal(name="io_arith_out_valid")
        self.out_ready = Signal(name="io_arith_out_ready")
        self.out_result = Signal(xlen, name="io_arith_out_result")
        self.out_fflags = Signal(5, name="io_arith_out_fflags")
        self.out_exception = Signal(name="io_arith_out_exception")
        self.in_fire = Signal(name="io_arith_in_fire")
        self.out_fire = Signal(name="io_arith_out_fire")
        count_width = max(1, (latency + 1).bit_length())
        self.scoreboard_count = Signal(count_width, name="io_arith_scoreboard_count")
        self.scoreboard_error = Signal(name="io_arith_scoreboard_error")

    # Elaborate arithmetic equations, elastic stages and fixed-latency scoreboard. / 展开算术方程、弹性级及固定延迟记分板。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        domain = ClockDomain("scalar_arith", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.scalar_arith = domain

        # Opcode contract: 0 add, 1 sub, 2 mul, 3 div, 4 rem, 5 min, 6 max.
        a = self.in_a
        b = self.in_b
        add_u = a + b
        sub_u = a - b
        add_ext = amaranth_value(Cat(Const(0), a)) + amaranth_value(Cat(Const(0), b))
        mul_unsigned = a * b
        a_signed = a.as_signed()
        b_signed = b.as_signed()
        mul_signed = a_signed * b_signed
        div_signed = a_signed // b_signed
        rem_signed = a_signed % b_signed
        div_unsigned = a // b
        rem_unsigned = a % b
        # Divide-by-zero is defined by the RISC-V integer result convention.
        div_zero = b == 0
        signed_div_overflow = (self.in_signed & (a == Const(1 << (self.xlen - 1), self.xlen))
                               & (b == Const((1 << self.xlen) - 1, self.xlen)))
        div_result = Mux(div_zero, Const((1 << self.xlen) - 1, self.xlen),
                         Mux(self.in_signed, div_signed, div_unsigned))
        rem_result = Mux(div_zero, a, Mux(self.in_signed, rem_signed, rem_unsigned))
        min_result = Mux(self.in_signed, Mux(a_signed < b_signed, a, b), Mux(a < b, a, b))
        max_result = Mux(self.in_signed, Mux(a_signed > b_signed, a, b), Mux(a > b, a, b))
        mul_result = Mux(self.in_signed, mul_signed, mul_unsigned)
        arithmetic_result = Mux(self.in_opcode == 0, add_u,
                            Mux(self.in_opcode == 1, sub_u,
                            Mux(self.in_opcode == 2, mul_result,
                            Mux(self.in_opcode == 3, div_result,
                            Mux(self.in_opcode == 4, rem_result,
                            Mux(self.in_opcode == 5, min_result,
                            Mux(self.in_opcode == 6, max_result, a)))))))
        add_overflow = Mux(self.in_signed,
                           (a[63] == b[63]) & (arithmetic_result[63] != a[63]),
                           add_ext[64])
        sub_overflow = self.in_signed & ((a[63] != b[63]) & (arithmetic_result[63] != a[63]))
        mul_high_unsigned = mul_unsigned[64:128]
        mul_high_signed = mul_signed[64:128]
        mul_overflow = Mux(self.in_signed,
                           ~((mul_high_signed == 0) | (mul_high_signed == ((1 << 64) - 1))),
                           mul_high_unsigned != 0)
        overflow = ((self.in_opcode == 0) & add_overflow) | ((self.in_opcode == 1) & sub_overflow) | ((self.in_opcode == 2) & mul_overflow)
        # fflags uses NV/DZ/OF/UF/NX in bits [4:0], matching RISC-V.
        flags = (Const(0, 5) | (div_zero << 3) | (overflow << 2) | signed_div_overflow)
        result_next = Signal(self.xlen, name="arith_result_next")
        flags_next = Signal(5, name="arith_flags_next")
        m.d.comb += [result_next.eq(arithmetic_result), flags_next.eq(flags)]

        valid_regs = [Signal(name=f"arith_valid_{index}") for index in range(self.latency)]
        result_regs = [Signal(self.xlen, name=f"arith_result_{index}") for index in range(self.latency)]
        flags_regs = [Signal(5, name=f"arith_flags_{index}") for index in range(self.latency)]
        ready_chain: list[Any] = [Const(0)] * self.latency
        ready_chain[-1] = ~valid_regs[-1] | self.out_ready
        for index in range(self.latency - 2, -1, -1):
            ready_chain[index] = ~valid_regs[index] | ready_chain[index + 1]
        in_fire = self.in_valid & ready_chain[0]
        out_fire = valid_regs[-1] & self.out_ready
        m.d.comb += [self.in_ready.eq(ready_chain[0]), self.in_fire.eq(in_fire),
                     self.out_valid.eq(valid_regs[-1]), self.out_fire.eq(out_fire),
                     self.out_result.eq(result_regs[-1]), self.out_fflags.eq(flags_regs[-1]),
                     self.out_exception.eq(flags_regs[-1].any())]

        with amaranth_if(m, self.reset):
            m.d.scalar_arith += [self.scoreboard_count.eq(0), self.scoreboard_error.eq(0)]
            for valid in valid_regs:
                m.d.scalar_arith += valid.eq(0)
            for result in result_regs:
                m.d.scalar_arith += result.eq(0)
            for flag in flags_regs:
                m.d.scalar_arith += flag.eq(0)
        with amaranth_else(m):
            # Elastic movement: each stage loads its predecessor only when ready.
            for index in range(self.latency - 1, -1, -1):
                source_valid = in_fire if index == 0 else valid_regs[index - 1]
                source_result = result_next if index == 0 else result_regs[index - 1]
                source_flags = flags_next if index == 0 else flags_regs[index - 1]
                with amaranth_if(m, ready_chain[index]):
                    m.d.scalar_arith += [valid_regs[index].eq(source_valid),
                                         result_regs[index].eq(source_result),
                                         flags_regs[index].eq(source_flags)]
            count_next = self.scoreboard_count + in_fire - out_fire
            m.d.scalar_arith += self.scoreboard_count.eq(count_next)
            with amaranth_if(m, out_fire & (self.scoreboard_count == 0)):
                m.d.scalar_arith += self.scoreboard_error.eq(1)
            with amaranth_if(m, in_fire & ~out_fire & (self.scoreboard_count == self.latency)):
                m.d.scalar_arith += self.scoreboard_error.eq(1)
        return m


# Short source-compatible alias for scalar pipeline users. / 为标量流水线用户保留简短源码兼容别名。
YunSuanScalarPipe = YunSuanScalarArithmeticPipeline


# Build the aggregate family boundary. / 构造聚合 family 边界。
class YunSuanScalarBoundary(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Expose all five scalar source contracts through one UHSC boundary. / 通过一个 UHSC 边界暴露五个标量源契约。"""

    # Construct aggregate ports. / 构造聚合端口。
    def __init__(self, configuration: YunSuanScalarConfig | None = None) -> None:
        self.configuration = configuration or YunSuanScalarConfig()
        c = self.configuration
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.fire = Signal(name="io_fire")
        self.round_input = Signal(c.rounding_width, name="io_round_input")
        self.round_in = Signal(name="io_roundIn")
        self.sticky_in = Signal(name="io_stickyIn")
        self.sign_in = Signal(name="io_signIn")
        self.rm = Signal(3, name="io_rm")
        self.round_output = Signal(c.rounding_width, name="io_round_output")
        self.round_inexact = Signal(name="io_round_inexact")
        self.round_carry = Signal(name="io_round_carry")
        self.lza_a = Signal(64, name="io_lza_a")
        self.lza_b = Signal(64, name="io_lza_b")
        self.lza_output = Signal(64, name="io_lza_output")
        self.clz_input = Signal(64, name="io_clz_input")
        self.clz_output = Signal(6, name="io_clz_output")
        self.int_input = Signal(64, name="io_int")
        self.int_signed = Signal(name="io_sign")
        self.int_long = Signal(name="io_long")
        self.int_result = Signal(64, name="io_int_result")
        self.int_flags = Signal(5, name="io_int_fflags")
        self.int2fp_src = Signal(64, name="io_int2fp_src")
        self.int2fp_op_type = Signal(5, name="io_int2fp_opType")
        self.int2fp_rm = Signal(3, name="io_int2fp_rm")
        self.int2fp_wflags = Signal(name="io_int2fp_wflags")
        self.int2fp_rm_inst = Signal(3, name="io_int2fp_rmInst")
        self.int2fp_reg_enables = [Signal(name=f"io_int2fp_regEnables_{index}")
                                   for index in range(c.int2fp_latency)]
        self.int2fp_result = Signal(64, name="io_int2fp_result")
        self.int2fp_flags = Signal(5, name="io_int2fp_fflags")
        self.fcvt_src = Signal(64, name="io_fcvt_src")
        self.fcvt_op_type = Signal(8, name="io_fcvt_opType")
        self.fcvt_sew = Signal(2, name="io_fcvt_sew")
        self.fcvt_result = Signal(64, name="io_fcvt_result")
        self.fcvt_flags = Signal(5, name="io_fcvt_fflags")
        # Decoupled arithmetic sideband; existing conversion ports stay unchanged.
        self.arith_in_valid = Signal(name="io_arith_in_valid")
        self.arith_in_ready = Signal(name="io_arith_in_ready")
        self.arith_in_opcode = Signal(4, name="io_arith_in_opcode")
        self.arith_in_signed = Signal(name="io_arith_in_signed")
        self.arith_in_a = Signal(64, name="io_arith_in_a")
        self.arith_in_b = Signal(64, name="io_arith_in_b")
        self.arith_in_rm = Signal(3, name="io_arith_in_rm")
        self.arith_out_valid = Signal(name="io_arith_out_valid")
        self.arith_out_ready = Signal(name="io_arith_out_ready")
        self.arith_out_result = Signal(64, name="io_arith_out_result")
        self.arith_out_fflags = Signal(5, name="io_arith_out_fflags")
        self.arith_out_exception = Signal(name="io_arith_out_exception")
        self.arith_scoreboard_count = Signal(max(1, (self.configuration.arithmetic_latency + 1).bit_length()),
                                              name="io_arith_scoreboard_count")
        self.arith_scoreboard_error = Signal(name="io_arith_scoreboard_error")

    # Elaborate all independent family closures. / 展开所有相互独立的 family 闭包。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        c = self.configuration
        rounding = YunSuanRoundingUnit(c.rounding_width)
        lza = YunSuanLZA(64)
        clz = YunSuanCLZ(64)
        integer = YunSuanIntToFP(c.default_exp_width, c.default_precision)
        int2fp = YunSuanINT2FP(c.int2fp_latency, c.xlen)
        fpcvt = YunSuanFPCVT(c.xlen)
        arithmetic = YunSuanScalarArithmeticPipeline(c.arithmetic_latency, c.xlen)
        m.submodules.rounding = rounding
        m.submodules.lza = lza
        m.submodules.clz = clz
        m.submodules.integer = integer
        m.submodules.int2fp = int2fp
        m.submodules.fpcvt = fpcvt
        m.submodules.arithmetic = arithmetic
        boxed_integer = integer.result
        # The aggregate integer port is a 64-bit staging payload; boxing is
        # selected by the caller's explicit type in the dedicated converter.
        # 聚合整数端口是 64 位暂存负载；专用转换器由调用者显式选择装箱类型。
        m.d.comb += [rounding.input.eq(self.round_input), rounding.round_in.eq(self.round_in),
                     rounding.sticky_in.eq(self.sticky_in), rounding.sign_in.eq(self.sign_in),
                     rounding.rm.eq(self.rm), self.round_output.eq(rounding.output),
                     self.round_inexact.eq(rounding.inexact), self.round_carry.eq(rounding.carry_out),
                     lza.a.eq(self.lza_a), lza.b.eq(self.lza_b), self.lza_output.eq(lza.output),
                     clz.input.eq(self.clz_input), self.clz_output.eq(clz.output),
                     integer.input.eq(self.int_input), integer.signed.eq(self.int_signed),
                     integer.long.eq(self.int_long), integer.rm.eq(self.rm),
                     self.int_result.eq(boxed_integer), self.int_flags.eq(integer.fflags),
                     int2fp.clock.eq(self.clock), int2fp.reset.eq(self.reset),
                     int2fp.src.eq(self.int2fp_src), int2fp.op_type.eq(self.int2fp_op_type),
                     int2fp.rm.eq(self.int2fp_rm), int2fp.wflags.eq(self.int2fp_wflags),
                     int2fp.rm_inst.eq(self.int2fp_rm_inst),
                     self.int2fp_result.eq(int2fp.result), self.int2fp_flags.eq(int2fp.fflags),
                     fpcvt.clock.eq(self.clock), fpcvt.reset.eq(self.reset), fpcvt.fire.eq(self.fire),
                     fpcvt.src.eq(self.fcvt_src), fpcvt.op_type.eq(self.fcvt_op_type),
                     fpcvt.sew.eq(self.fcvt_sew), fpcvt.rm.eq(self.rm),
                     self.fcvt_result.eq(fpcvt.result), self.fcvt_flags.eq(fpcvt.fflags),
                     arithmetic.clock.eq(self.clock), arithmetic.reset.eq(self.reset),
                     arithmetic.in_valid.eq(self.arith_in_valid), arithmetic.in_opcode.eq(self.arith_in_opcode),
                     arithmetic.in_signed.eq(self.arith_in_signed), arithmetic.in_a.eq(self.arith_in_a),
                     arithmetic.in_b.eq(self.arith_in_b), arithmetic.in_rm.eq(self.arith_in_rm),
                     arithmetic.out_ready.eq(self.arith_out_ready),
                     self.arith_in_ready.eq(arithmetic.in_ready), self.arith_out_valid.eq(arithmetic.out_valid),
                     self.arith_out_result.eq(arithmetic.out_result), self.arith_out_fflags.eq(arithmetic.out_fflags),
                     self.arith_out_exception.eq(arithmetic.out_exception),
                     self.arith_scoreboard_count.eq(arithmetic.scoreboard_count),
                     self.arith_scoreboard_error.eq(arithmetic.scoreboard_error)]
        return m


# Source-compatible aliases retained for family consumers. / 为 family 消费者保留源码兼容别名。
FPU = YunSuanFPU
RoundingUnit = YunSuanRoundingUnit
LZA = YunSuanLZA
CLZ = YunSuanCLZ
IntToFP = YunSuanIntToFP
INT2FP = YunSuanINT2FP
FPCVT = YunSuanFPCVT


# =============================================================================
# Public Adapter
# =============================================================================
# Emit a deterministic UHSC-localized family Verilog boundary. / 导出确定性的 UHSC family Verilog 边界。
def build_verilog(configuration: YunSuanScalarConfig | Mapping[str, Any] | None,
                 injected_dependencies: Mapping[str, Any]) -> str:
    """Build the aggregate family or a selected primitive mode. / 构建聚合 family 或选定的 primitive 模式。"""

    del injected_dependencies
    if isinstance(configuration, YunSuanScalarConfig):
        cfg = configuration
        mode = "aggregate"
        name = "UHSCYunSuanScalar"
    elif isinstance(configuration, Mapping):
        fields = YunSuanScalarConfig.__dataclass_fields__
        values = {key: int(value) for key, value in configuration.items() if key in fields}
        cfg = YunSuanScalarConfig(**values)
        mode = str(configuration.get("mode", "aggregate"))
        name = str(configuration.get("module", configuration.get("name", "UHSCYunSuanScalar")))
    elif configuration is None:
        cfg = YunSuanScalarConfig()
        mode = "aggregate"
        name = "UHSCYunSuanScalar"
    else:
        raise TypeError("configuration must be YunSuanScalarConfig, dict, or None")
    if mode == "rounding":
        top = YunSuanRoundingUnit(cfg.rounding_width)
        ports = [top.input, top.round_in, top.sticky_in, top.sign_in, top.rm,
                 top.output, top.inexact, top.carry_out, top.round_up]
    elif mode == "lza":
        top = YunSuanLZA(64)
        ports = [top.a, top.b, top.output]
    elif mode == "clz":
        top = YunSuanCLZ(64)
        ports = [top.input, top.output]
    elif mode == "int_to_fp":
        top = YunSuanIntToFP(cfg.default_exp_width, cfg.default_precision)
        ports = [top.input, top.signed, top.long, top.rm, top.result, top.fflags]
    elif mode == "int2fp":
        top = YunSuanINT2FP(cfg.int2fp_latency, cfg.xlen)
        ports = [top.clock, top.reset, top.src, top.op_type, top.rm, top.wflags,
                 top.rm_inst, *top.reg_enables, top.result, top.fflags]
    elif mode == "fpcvt":
        top = YunSuanFPCVT(cfg.xlen)
        ports = [top.clock, top.reset, top.fire, top.src, top.op_type, top.sew,
                 top.rm, top.is_fround, top.is_fcvtmod, top.result, top.fflags]
    elif mode in ("arithmetic", "scalar_arithmetic", "scalar_pipe"):
        top = YunSuanScalarArithmeticPipeline(cfg.arithmetic_latency, cfg.xlen)
        ports = [top.clock, top.reset, top.in_valid, top.in_ready, top.in_opcode,
                 top.in_signed, top.in_a, top.in_b, top.in_rm, top.out_valid,
                 top.out_ready, top.out_result, top.out_fflags, top.out_exception,
                 top.in_fire, top.out_fire, top.scoreboard_count, top.scoreboard_error]
    else:
        top = YunSuanScalarBoundary(cfg)
        ports = [top.clock, top.reset, top.fire, top.round_input, top.round_in,
                 top.sticky_in, top.sign_in, top.rm, top.round_output, top.round_inexact,
                 top.round_carry, top.lza_a, top.lza_b, top.lza_output, top.clz_input,
                 top.clz_output, top.int_input, top.int_signed, top.int_long, top.int_result,
                 top.int_flags, top.int2fp_src, top.int2fp_op_type, top.int2fp_rm,
                 top.int2fp_wflags, top.int2fp_rm_inst, *top.int2fp_reg_enables,
                 top.int2fp_result, top.int2fp_flags, top.fcvt_src, top.fcvt_op_type, top.fcvt_sew,
                 top.fcvt_result, top.fcvt_flags, top.arith_in_valid, top.arith_in_ready,
                 top.arith_in_opcode, top.arith_in_signed, top.arith_in_a, top.arith_in_b,
                 top.arith_in_rm, top.arith_out_valid, top.arith_out_ready, top.arith_out_result,
                 top.arith_out_fflags, top.arith_out_exception, top.arith_scoreboard_count,
                 top.arith_scoreboard_error]
    return verilog.convert(top, name=name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print deterministic default family Verilog for direct smoke tests. / 为 direct smoke 测试打印默认 family Verilog。
def main() -> None:
    """Print the default UHSC family export. / 打印默认 UHSC family 导出。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
