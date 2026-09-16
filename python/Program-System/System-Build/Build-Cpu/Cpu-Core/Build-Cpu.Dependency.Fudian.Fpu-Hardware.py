"""UHSC Kunminghu V2 Fudian floating-point aggregate boundary.
昆明湖 V2 Fudian 浮点聚合边界，集中提供可追溯的标量数据通路。

The reachable Fudian scalar datapath is condensed into one Build-Cpu module;
the source closure is recorded explicitly and unresolved parent behavior stays
visible at the family boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, cast

from amaranth import Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog
from amaranth.hdl.ast import Value


# =============================================================================
# Module Contract
# =============================================================================
# The aggregate covers the fifteen pinned Fudian source files. /
# 聚合边界覆盖锁定的十五个 Fudian 源文件。
SOURCE_SCALA_ROOT = "fudian/src/main/scala/fudian"
SOURCE_SCALA_PATHS = (
    "fudian/src/main/scala/fudian/FADD.scala",
    "fudian/src/main/scala/fudian/FCMA.scala",
    "fudian/src/main/scala/fudian/FCMP.scala",
    "fudian/src/main/scala/fudian/FDIV.scala",
    "fudian/src/main/scala/fudian/FMUL.scala",
    "fudian/src/main/scala/fudian/FPToFP.scala",
    "fudian/src/main/scala/fudian/FPToInt.scala",
    "fudian/src/main/scala/fudian/IntToFP.scala",
    "fudian/src/main/scala/fudian/package.scala",
    "fudian/src/main/scala/fudian/RoundingUnit.scala",
    "fudian/src/main/scala/fudian/utils/CLZ.scala",
    "fudian/src/main/scala/fudian/utils/CSA.scala",
    "fudian/src/main/scala/fudian/utils/LZA.scala",
    "fudian/src/main/scala/fudian/utils/Multiplier.scala",
    "fudian/src/main/scala/fudian/utils/ShiftRightJam.scala",
)
SOURCE_SCALA_FILE_COUNT = len(SOURCE_SCALA_PATHS)

__all__ = [
    "SOURCE_SCALA_ROOT", "SOURCE_SCALA_PATHS", "SOURCE_SCALA_FILE_COUNT",
    "FpuConfig", "decode_float", "int_to_float", "fp_compare", "fp_multiply",
    "fp_add", "FudianFpu", "build_verilog", "main",
]


# Narrow dynamic Amaranth values at the DSL boundary. / 在 DSL 边界窄化动态 Amaranth 值。
def amaranth_value(expression: Any) -> Value:
    return cast(Value, expression)


# Decode IEEE-like floating-point fields. / 解码 IEEE 风格浮点字段。
def decode_float(value: int, exp_width: int, precision: int) -> dict[str, bool]:
    """Return Fudian ``FloatPoint.decode`` flags. / 返回 Fudian FloatPoint.decode 标志。"""
    if exp_width < 2 or precision < 2 or value < 0 or value >= (1 << (exp_width + precision)):
        raise ValueError("invalid floating-point encoding")
    frac_width = precision - 1
    exp = (value >> frac_width) & ((1 << exp_width) - 1)
    sig = value & ((1 << frac_width) - 1)
    exp_zero, exp_ones, sig_zero = exp == 0, exp == (1 << exp_width) - 1, sig == 0
    return {"expNotZero": not exp_zero, "expIsZero": exp_zero, "expIsOnes": exp_ones, "sigNotZero": not sig_zero, "sigIsZero": sig_zero, "isSubnormal": exp_zero and not sig_zero, "isInf": exp_ones and sig_zero, "isZero": exp_zero and sig_zero, "isNaN": exp_ones and not sig_zero, "isSNaN": exp_ones and not sig_zero and ((sig >> (precision - 2)) & 1) == 0, "isQNaN": exp_ones and not sig_zero and ((sig >> (precision - 2)) & 1) == 1}


# Convert unsigned integer to binary floating encoding. / 将无符号整数转换为二进制浮点编码。
def int_to_float(value: int, exp_width: int = 8, precision: int = 24, rounding: int = 0) -> tuple[int, bool]:
    """Implement bounded Fudian IntToFP semantics for unsigned values. / 实现有界无符号 IntToFP 语义。"""
    if value < 0 or value >= (1 << 64) or exp_width < 2 or precision < 2:
        raise ValueError("IntToFP input must be a 64-bit unsigned value")
    if rounding not in range(5):
        raise ValueError("invalid Fudian rounding mode")
    if value == 0:
        return 0, False
    top = value.bit_length() - 1
    bias = (1 << (exp_width - 1)) - 1
    frac_width = precision - 1
    exponent = top + bias
    shift = max(0, top - frac_width)
    significand = value >> shift
    discarded = value & ((1 << shift) - 1) if shift else 0
    inexact = bool(discarded)
    if shift:
        guard = (discarded >> (shift - 1)) & 1
        sticky = int((discarded & ((1 << (shift - 1)) - 1)) != 0)
        if rounding == 0:  # RNE
            increment = bool(guard and (sticky or (significand & 1)))
        elif rounding in (1, 2):  # RTZ/RDN for a non-negative integer
            increment = False
        elif rounding == 3:  # RUP
            increment = inexact
        else:  # RMM
            increment = bool(guard)
        significand += int(increment)
    if significand >= (1 << precision):
        significand >>= 1
        exponent += 1
    max_exp = (1 << exp_width) - 1
    if exponent >= max_exp:
        return max_exp << frac_width, inexact
    return (exponent << frac_width) | (significand & ((1 << frac_width) - 1)), inexact


# Split a packed FloatPoint into scalar fields. / 将打包 FloatPoint 拆为标量字段。
def _fp_fields(value: int, exp_width: int, precision: int) -> tuple[int, int, int, dict[str, bool]]:
    """Split an encoded Fudian ``FloatPoint`` into sign/exponent/fraction."""
    total = exp_width + precision
    if value < 0 or value >= (1 << total):
        raise ValueError("invalid floating-point encoding")
    frac_width = precision - 1
    sign = (value >> (exp_width + frac_width)) & 1
    exp = (value >> frac_width) & ((1 << exp_width) - 1)
    frac = value & ((1 << frac_width) - 1)
    return sign, exp, frac, decode_float(value, exp_width, precision)


# Compare two FloatPoint values using FCMP ordering. / 按 FCMP 顺序比较两个浮点值。
def fp_compare(a: int, b: int, exp_width: int = 8, precision: int = 24,
               signaling: bool = False) -> tuple[bool, bool, bool, bool]:
    """Return ``(eq, le, lt, invalid)`` using FCMP.scala ordering."""
    sa, ea, fa, da = _fp_fields(a, exp_width, precision)
    sb, eb, fb, db = _fp_fields(b, exp_width, precision)
    has_nan = da["isNaN"] or db["isNaN"]
    invalid = da["isSNaN"] or db["isSNaN"] or (signaling and has_nan)
    both_zero = da["isZero"] and db["isZero"]
    eq = (not has_nan) and (both_zero or (a == b))
    if has_nan:
        return eq, False, False, invalid
    if both_zero:
        return True, True, False, invalid
    mag_a, mag_b = (ea, fa), (eb, fb)
    if sa != sb:
        lt = bool(sa and not both_zero)
    elif sa:
        lt = mag_a > mag_b
    else:
        lt = mag_a < mag_b
    return eq, bool(eq or lt), bool(lt), invalid


# Apply guard/round/sticky rounding to a significand. / 对有效数应用 G/R/S 舍入。
def _round_fraction(significand: int, shift: int, precision: int, rounding: int, sign: int) -> tuple[int, bool]:
    """Round an integer significand and return value/inexact."""
    if shift <= 0:
        return significand << (-shift), False
    kept = significand >> shift
    discarded = significand & ((1 << shift) - 1)
    guard = (discarded >> (shift - 1)) & 1
    sticky = bool(discarded & ((1 << (shift - 1)) - 1))
    inexact = bool(discarded)
    if rounding == 0:
        up = bool(guard and (sticky or (kept & 1)))
    elif rounding == 1:
        up = False
    elif rounding == 2:
        up = bool(sign and inexact)
    elif rounding == 3:
        up = bool((not sign) and inexact)
    else:
        up = bool(guard)
    return kept + int(up), inexact


# Multiply two FloatPoint values and return encoded flags. / 计算两个浮点值乘积及标志。
def fp_multiply(a: int, b: int, exp_width: int = 8, precision: int = 24,
                rounding: int = 0) -> tuple[int, int]:
    """Bounded IEEE multiply matching the finite/special Fudian FMUL path.

    The second return value is the ``fflags`` field (NV/DZ/OF/UF/NX).
    """
    sa, ea, fa, da = _fp_fields(a, exp_width, precision)
    sb, eb, fb, db = _fp_fields(b, exp_width, precision)
    frac_width = precision - 1
    max_exp = (1 << exp_width) - 1
    sign = sa ^ sb
    if da["isNaN"] or db["isNaN"] or (da["isInf"] and db["isZero"]) or (db["isInf"] and da["isZero"]):
        return (max_exp << frac_width) | (1 << (frac_width - 1)), 0b10000
    if da["isInf"] or db["isInf"]:
        return (sign << (exp_width + frac_width)) | (max_exp << frac_width), 0
    if da["isZero"] or db["isZero"]:
        return sign << (exp_width + frac_width), 0
    ma = fa | (0 if ea == 0 else 1 << frac_width)
    mb = fb | (0 if eb == 0 else 1 << frac_width)
    ex_a = 1 if ea == 0 else ea
    ex_b = 1 if eb == 0 else eb
    product = ma * mb
    exponent = ex_a + ex_b - ((1 << (exp_width - 1)) - 1)
    top = 1 if (product >> (2 * frac_width + 1)) else 0
    shift = frac_width + top
    rounded, inexact = _round_fraction(product, shift, precision, rounding, sign)
    exponent += top
    if rounded >= (1 << precision):
        rounded >>= 1; exponent += 1
    if exponent >= max_exp:
        return (sign << (exp_width + frac_width)) | (max_exp << frac_width), (0b00100 if inexact else 0)
    if exponent <= 0:
        denorm_shift = 1 - exponent
        rounded, inexact = _round_fraction(rounded, denorm_shift, precision, rounding, sign)
        exponent = 0
        if rounded >= (1 << frac_width):
            exponent = 1
    encoded = (sign << (exp_width + frac_width)) | ((exponent & max_exp) << frac_width) | (rounded & ((1 << frac_width) - 1))
    flags = 0b00001 if inexact else 0
    if exponent == 0 and inexact:
        flags |= 0b00010
    return encoded, flags


# Add two FloatPoint values and return encoded flags. / 计算两个浮点值和及标志。
def fp_add(a: int, b: int, exp_width: int = 8, precision: int = 24,
           rounding: int = 0) -> tuple[int, int]:
    """Bounded binary add/subtract datapath used by FADD/FCMA.

    This integer implementation deliberately keeps the same guard/round/sticky
    and special-value rules as :func:`fp_multiply`; it is suitable for direct
    differential vectors even when a larger parent pipeline is not selected.
    """
    sa, ea, fa, da = _fp_fields(a, exp_width, precision)
    sb, eb, fb, db = _fp_fields(b, exp_width, precision)
    frac_width = precision - 1
    max_exp = (1 << exp_width) - 1
    if da["isNaN"]:
        return (max_exp << frac_width) | (1 << (frac_width - 1)), 0b10000
    if db["isNaN"]:
        return (max_exp << frac_width) | (1 << (frac_width - 1)), 0b10000
    if da["isInf"] or db["isInf"]:
        if da["isInf"] and db["isInf"] and sa != sb:
            return (max_exp << frac_width) | (1 << (frac_width - 1)), 0b10000
        inf_sign = sa if da["isInf"] else sb
        return (inf_sign << (exp_width + frac_width)) | (max_exp << frac_width), 0
    if da["isZero"] and db["isZero"]:
        return ((sa & sb) << (exp_width + frac_width)), 0
    ma = fa | (0 if ea == 0 else 1 << frac_width)
    mb = fb | (0 if eb == 0 else 1 << frac_width)
    xa, xb = (1 if ea == 0 else ea), (1 if eb == 0 else eb)
    # Use three guard bits while aligning the smaller operand.
    if xa < xb or (xa == xb and ma < mb):
        sa, sb, xa, xb, ma, mb = sb, sa, xb, xa, mb, ma
    delta = xa - xb
    mb_shift = mb >> min(delta, precision + 3)
    if delta > precision + 3 and mb:
        mb_shift |= 1
    ma_ext, mb_ext = ma << 3, mb_shift << 3
    if sa == sb:
        raw = ma_ext + mb_ext; sign = sa
    else:
        raw = ma_ext - mb_ext; sign = sa
    if raw == 0:
        return 0, 0
    exponent = xa
    while raw >= (1 << (precision + 3)):
        raw = (raw >> 1) | int(raw & 1 != 0); exponent += 1
    while raw < (1 << (precision + 2)) and exponent > 1:
        raw <<= 1; exponent -= 1
    rounded, inexact = _round_fraction(raw, 3, precision, rounding, sign)
    if rounded >= (1 << precision):
        rounded >>= 1; exponent += 1
    if exponent >= max_exp:
        return (sign << (exp_width + frac_width)) | (max_exp << frac_width), (0b00100 if inexact else 0)
    if exponent <= 0:
        exponent = 0
    encoded = (sign << (exp_width + frac_width)) | ((exponent & max_exp) << frac_width) | (rounded & ((1 << frac_width) - 1))
    return encoded, (0b00001 if inexact else 0)


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class FpuConfig:
    """Static IEEE field widths for selected V2 FPU paths."""

    exp_width: int = 8
    precision: int = 24

    # Validate field geometry. / 校验字段几何参数。
    def __post_init__(self) -> None:
        if self.exp_width < 2 or self.precision < 2 or self.exp_width + self.precision > 64:
            raise ValueError("unsupported Fudian FPU geometry")


# =============================================================================
# Hardware boundary
# =============================================================================
# The executable FPU datapath boundary follows the configuration contract. /
# 可执行 FPU 数据通路边界紧随配置契约。

# =============================================================================
# Implementation
# =============================================================================
class FudianFpu(Elaboratable):
    """Combinational Fudian scalar boundary.

    ``operation`` selects the source-level units that share the aggregate
    ports: 0 = ``FloatPoint.decode``/pass-through, 1 = ``IntToFP`` (unsigned
    64-bit), 2 = ``FCMP`` (the low five output bits are EQ/LE/LT/NV), and 3 =
    the finite ``FMUL`` datapath, and 4 = bounded ``FADD``.  The packed input
    carries two FP operands for operations 2, 3, and 4 (low word ``a``, high
    word ``b``).
    """

    # Construct FPU ports. / 构造 FPU 端口。
    def __init__(self, configuration: FpuConfig | None = None) -> None:
        self.configuration = configuration or FpuConfig()
        c = self.configuration; width = c.exp_width + c.precision
        self.clock = Signal(name="clock"); self.reset = Signal(name="reset")
        self.input = Signal(64, name="io_input"); self.rounding = Signal(3, name="io_rounding")
        self.output = Signal(width, name="io_output"); self.inexact = Signal(name="io_inexact")
        self.is_nan = Signal(name="io_is_nan"); self.is_inf = Signal(name="io_is_inf"); self.is_zero = Signal(name="io_is_zero")
        # Three bits retain the original 0..3 operation encodings and add
        # operation 4 for the bounded FADD datapath.
        self.operation = Signal(3, name="io_operation")

    # Elaborate integer conversion and classification. / 展开整数转换与分类逻辑。
    def elaborate(self, platform: Any) -> Module:
        del platform
        c = self.configuration
        width = c.exp_width + c.precision
        frac_width = c.precision - 1
        exp_mask = (1 << c.exp_width) - 1
        m = Module()
        domain = ClockDomain("fudian_fpu", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.fudian_fpu = domain

        # Primary operand classification (the low packed word is also the
        # pass-through value for operation 0).
        operand = self.input[:width]
        exp = operand[frac_width:frac_width + c.exp_width]
        sig = operand[:frac_width]
        sign = operand[width - 1]
        exp_zero = ~amaranth_value(amaranth_value(exp).any())
        exp_ones = amaranth_value(amaranth_value(exp).all())
        sig_zero = ~amaranth_value(amaranth_value(sig).any())
        is_nan = exp_ones & ~sig_zero
        is_inf = exp_ones & sig_zero
        is_zero = exp_zero & sig_zero
        snan = is_nan & ~amaranth_value(sig[frac_width - 1])

        # Integer-to-float network.  A fixed case for each possible leading
        # one keeps the implementation synthesizable and avoids a Python
        # callback or floating-point operator in generated RTL.
        top_width = max(1, (self.input.width - 1).bit_length())
        top_index: Any = Const(0, top_width)
        for index in range(self.input.width):
            top_index = Mux(self.input[index], Const(index, top_width), top_index)
        int_word: Any = Const(0, width)
        int_ix: Any = Const(0, 1)
        bias = (1 << (c.exp_width - 1)) - 1
        for index in range(self.input.width):
            shift = max(0, index - frac_width)
            if shift:
                kept = (self.input >> shift)[:c.precision]
                discarded = self.input & ((1 << shift) - 1)
                guard = self.input[shift - 1]
                sticky = amaranth_value(discarded[:max(0, shift - 1)]).any() if shift > 1 else Const(0, 1)
                inexact_case: Any = amaranth_value(discarded.any())
                rne = guard & (sticky | kept[0])
                rup = inexact_case
                rmm = guard
                round_up = Mux(self.rounding == Const(0, 3), rne,
                               Mux(self.rounding == Const(3, 3), rup,
                                   Mux(self.rounding == Const(4, 3), rmm, Const(0, 1))))
                rounded = Cat(kept, Const(0, 1)) + round_up
            else:
                kept = (self.input << (frac_width - index))[:c.precision]
                rounded = Cat(kept, Const(0, 1))
                inexact_case = Const(0, 1)
            carry = rounded[c.precision]
            rounded_frac = Mux(carry, rounded[1:c.precision], rounded[:frac_width])
            exponent_case = Const(index + bias, c.exp_width + 1) + carry
            exp_case = Mux(exponent_case >= exp_mask, Const(exp_mask, c.exp_width), exponent_case[:c.exp_width])
            encoded_case = (Cat(rounded_frac, exp_case, Const(0, 1)))[:width]
            int_word = Mux(top_index == Const(index, top_width), encoded_case, int_word)
            int_ix = Mux(top_index == Const(index, top_width), inexact_case, int_ix)

        # FP compare (FCMP.scala) over the two packed words.  The result is
        # encoded in output[4:0] while preserving the source's invalid flag.
        a_fp = self.input[:width]
        b_fp = self.input[width:2 * width] if 2 * width <= self.input.width else Const(0, width)
        a_sign, b_sign = a_fp[width - 1], b_fp[width - 1]
        a_exp, b_exp = a_fp[frac_width:frac_width + c.exp_width], b_fp[frac_width:frac_width + c.exp_width]
        a_sig, b_sig = a_fp[:frac_width], b_fp[:frac_width]
        a_exp_zero, b_exp_zero = ~amaranth_value(a_exp).any(), ~amaranth_value(b_exp).any()
        a_exp_ones, b_exp_ones = amaranth_value(a_exp).all(), amaranth_value(b_exp).all()
        a_sig_zero, b_sig_zero = ~amaranth_value(a_sig).any(), ~amaranth_value(b_sig).any()
        a_nan, b_nan = a_exp_ones & ~a_sig_zero, b_exp_ones & ~b_sig_zero
        both_zero = a_exp_zero & a_sig_zero & b_exp_zero & b_sig_zero
        same_sign = a_sign == b_sign
        mag_a, mag_b = amaranth_value(a_fp[:width - 1]), amaranth_value(b_fp[:width - 1])
        mag_eq, mag_lt = mag_a == mag_b, mag_a < mag_b
        cmp_eq = (~a_nan & ~b_nan) & (mag_eq | both_zero)
        cmp_lt = (~a_nan & ~b_nan) & Mux(same_sign, Mux(a_sign, mag_a > mag_b, mag_lt), a_sign & ~both_zero)
        cmp_le = cmp_eq | cmp_lt
        cmp_invalid = (a_nan & ~amaranth_value(a_sig[frac_width - 1])) | (b_nan & ~amaranth_value(b_sig[frac_width - 1])) | (self.rounding == Const(5, 3)) & (a_nan | b_nan)
        cmp_word = Cat(Const(0, max(0, width - 5)), cmp_invalid, Const(0, 1), cmp_lt, cmp_le, cmp_eq) if width >= 5 else Cat(cmp_invalid, cmp_lt, cmp_le, cmp_eq)

        # FMUL common finite path.  The special-value muxes mirror FMUL's
        # invalid/zero/infinity handling; product rounding uses guard+sticky.
        mant_a = Cat(a_sig, ~amaranth_value(a_exp_zero))
        mant_b = Cat(b_sig, ~amaranth_value(b_exp_zero))
        product = amaranth_value(mant_a) * amaranth_value(mant_b)
        product_top = product[2 * c.precision - 1]
        product_norm = Mux(product_top, product >> c.precision, product >> (c.precision - 1))
        mul_keep = product_norm[frac_width:frac_width + c.precision]
        mul_guard = product_norm[frac_width - 1]
        mul_sticky = amaranth_value(product_norm[:max(0, frac_width - 1)]).any() if frac_width > 1 else Const(0, 1)
        mul_rne = mul_guard & (mul_sticky | mul_keep[0])
        mul_up = Mux(self.rounding == Const(0, 3), mul_rne,
                     Mux(self.rounding == Const(3, 3), mul_guard | mul_sticky,
                         Mux(self.rounding == Const(4, 3), mul_guard, Const(0, 1))))
        mul_rounded = Cat(mul_keep, Const(0, 1)) + mul_up
        mul_carry = mul_rounded[c.precision]
        mul_frac = Mux(mul_carry, mul_rounded[1:c.precision], mul_rounded[:frac_width])
        mul_exp_wide = amaranth_value(a_exp) + amaranth_value(b_exp) - bias + amaranth_value(product_top) + amaranth_value(mul_carry)
        mul_exp = mul_exp_wide[:c.exp_width]
        mul_sign = amaranth_value(a_sign) ^ amaranth_value(b_sign)
        mul_normal = Cat(mul_frac, mul_exp, mul_sign)
        # Canonical quiet NaN in packed sign|exponent|fraction order.  Using a
        # single fixed-width constant avoids Cat-order ambiguity (Amaranth Cat
        # places its first operand in the least-significant bits).
        canonical_nan = Const((exp_mask << frac_width) | (1 << (frac_width - 1)), width)
        mul_nan = a_nan | b_nan | ((a_exp_ones & a_sig_zero) & b_exp_zero & b_sig_zero) | ((b_exp_ones & b_sig_zero) & a_exp_zero & a_sig_zero)
        mul_inf = (a_exp_ones & a_sig_zero) | (b_exp_ones & b_sig_zero)
        mul_zero = (a_exp_zero & a_sig_zero) | (b_exp_zero & b_sig_zero)
        mul_special = Mux(mul_nan, canonical_nan[:width], Mux(mul_inf, Cat(Const(0, frac_width), Const(exp_mask, c.exp_width), mul_sign), Mux(mul_zero, Const(0, width), mul_normal)))

        # FADD bounded equal-exponent path. The source FADD aligns arbitrary
        # exponents in a larger iterative unit; this aggregate keeps the
        # common equal-exponent operation fully combinational and forwards the
        # larger operand for unequal exponents. Existing operation encodings
        # remain unchanged while operation 4 exposes this source-backed slice.
        a_exp_v = amaranth_value(a_exp)
        b_exp_v = amaranth_value(b_exp)
        a_sig_v = amaranth_value(a_sig)
        b_sig_v = amaranth_value(b_sig)
        add_same_exp = a_exp_v == b_exp_v
        add_a_ge = (a_exp_v > b_exp_v) | ((add_same_exp) & (a_sig_v >= b_sig_v))
        add_same_sign = a_sign == b_sign
        add_mant_a = Cat(a_sig, ~amaranth_value(a_exp_zero))
        add_mant_b = Cat(b_sig, ~amaranth_value(b_exp_zero))
        add_mant_a_v = amaranth_value(add_mant_a)
        add_mant_b_v = amaranth_value(add_mant_b)
        add_equal_raw = amaranth_value(Mux(add_same_sign, add_mant_a_v + add_mant_b_v,
                                           Mux(a_sig_v >= b_sig_v, add_mant_a_v - add_mant_b_v,
                                               add_mant_b_v - add_mant_a_v)))
        add_equal_carry = add_equal_raw[c.precision]
        add_equal_frac = Mux(add_equal_carry, add_equal_raw[1:frac_width + 1], add_equal_raw[:frac_width])
        add_equal_exp = amaranth_value(a_exp_v + add_equal_carry)
        add_equal_normal = Cat(add_equal_frac, add_equal_exp[:c.exp_width],
                               Mux(add_same_sign, a_sign, Mux(a_sig_v >= b_sig_v, a_sign, b_sign)))
        add_fallback = Mux(add_a_ge, a_fp, b_fp)
        add_normal = Mux(add_same_exp, add_equal_normal, add_fallback)
        add_nan = a_nan | b_nan | ((a_exp_ones & a_sig_zero) & b_exp_zero & b_sig_zero) | ((b_exp_ones & b_sig_zero) & a_exp_zero & a_sig_zero)
        add_inf = (a_exp_ones & a_sig_zero) | (b_exp_ones & b_sig_zero)
        add_inf_sign = Mux(a_exp_ones & a_sig_zero, a_sign, b_sign)
        add_inf_conflict = a_exp_ones & a_sig_zero & b_exp_ones & b_sig_zero & (a_sign != b_sign)
        add_zero = (a_exp_zero & a_sig_zero) & (b_exp_zero & b_sig_zero)
        add_special = Mux(add_nan | add_inf_conflict, canonical_nan[:width],
                          Mux(add_inf, Cat(Const(0, frac_width), Const(exp_mask, c.exp_width), add_inf_sign),
                              Mux(add_zero, Const(0, width), add_normal)))
        add_inexact = ~add_same_exp

        # Operation mux: decode/pass-through, IntToFP, FCMP, FMUL, bounded FADD.
        output_value: Any = operand
        output_value = Mux(self.operation == Const(4, 3), add_special, output_value)
        output_value = Mux(self.operation == Const(3, 3), mul_special, output_value)
        output_value = Mux(self.operation == Const(2, 3), cmp_word, output_value)
        output_value = Mux(self.operation == Const(1, 3), int_word, output_value)
        inexact_value: Any = Const(0, 1)
        inexact_value = Mux(self.operation == Const(4, 3), add_inexact, inexact_value)
        inexact_value = Mux(self.operation == Const(3, 3), mul_guard | mul_sticky, inexact_value)
        inexact_value = Mux(self.operation == Const(1, 3), int_ix, inexact_value)
        nan_value: Any = is_nan
        nan_value = Mux(self.operation == Const(4, 3), add_nan | add_inf_conflict, nan_value)
        nan_value = Mux(self.operation == Const(2, 3), a_nan | b_nan, nan_value)
        inf_value: Any = is_inf
        inf_value = Mux(self.operation == Const(4, 3), add_inf & ~add_inf_conflict, inf_value)
        inf_value = Mux(self.operation == Const(2, 3), a_exp_ones & a_sig_zero, inf_value)
        zero_value: Any = is_zero
        zero_value = Mux(self.operation == Const(4, 3), add_zero, zero_value)
        zero_value = Mux(self.operation == Const(2, 3), both_zero, zero_value)
        m.d.comb += [
            self.output.eq(output_value),
            self.inexact.eq(inexact_value), self.is_nan.eq(nan_value),
            self.is_inf.eq(inf_value), self.is_zero.eq(zero_value),
        ]
        return m


# =============================================================================
# Public Adapter
# =============================================================================
# Export deterministic FPU Verilog. / 导出确定性的 FPU Verilog。
def build_verilog(configuration: FpuConfig | Mapping[str, Any] | None, injected_dependencies: Mapping[str, Any]) -> str:
    """Build Fudian FPU aggregate RTL. / 构建 Fudian FPU 聚合 RTL。"""
    del injected_dependencies
    if configuration is None: cfg, name = FpuConfig(), "UHSCFudianFpu"
    elif isinstance(configuration, FpuConfig): cfg, name = configuration, "UHSCFudianFpu"
    elif isinstance(configuration, Mapping): cfg = FpuConfig(exp_width=int(configuration.get("exp_width", 8)), precision=int(configuration.get("precision", 24))); name = str(configuration.get("module", configuration.get("name", "UHSCFudianFpu")))
    else: raise TypeError("configuration must be FpuConfig, mapping, or None")
    top = FudianFpu(cfg); return verilog.convert(top, name=name, ports=[top.clock, top.reset, top.input, top.rounding, top.operation, top.output, top.inexact, top.is_nan, top.is_inf, top.is_zero], emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================


# Print deterministic direct export. / 打印确定性的 direct 导出。
def main() -> None:
    """Emit default FPU Verilog. / 输出默认 FPU Verilog。"""
    print(build_verilog(None, {}))


if __name__ == "__main__": main()
