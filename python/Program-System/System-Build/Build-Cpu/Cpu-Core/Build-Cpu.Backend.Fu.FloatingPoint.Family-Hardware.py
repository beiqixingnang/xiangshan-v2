"""Floating-point execution family with exact locked port surfaces.

Only the two multiplier leaves listed in ``IMPLEMENTED_MEMBERS`` are claimed
as executable in this batch. Every other member is explicitly marked
``CONTRACT_ONLY`` and receives ABI-safe tie-offs until its differential
closure is completed.
"""

from __future__ import annotations

from typing import Any, cast

from amaranth import Array, Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.hdl import Value
from amaranth.back import verilog


__all__ = ["COVERED_MODULES", "IMPLEMENTED_MEMBERS", "CONTRACT_ONLY_MEMBERS", "FloatingPointFamily", "build_verilog", "main"]
COVERED_MODULES = ("FloatAdder", "FloatAdderF32F16MixedPipeline", "FloatAdderF64Pipeline", "FloatDivider", "FloatDividerR64", "FloatFMA", "fpdiv_r64_block", "fpsqrt_r16", "BoothEncoderF64F32F16", "ArrayMulDataModule", "IntToFPDataModule")
IMPLEMENTED_MEMBERS = ("BoothEncoderF64F32F16", "ArrayMulDataModule")
CONTRACT_ONLY_MEMBERS = tuple(name for name in COVERED_MODULES if name not in IMPLEMENTED_MEMBERS)

# BEGIN LOCKED PORT CATALOG
LOCKED_PORT_SPECS: dict[str, tuple[tuple[str, str, int], ...]] = {
    "FloatAdder": (
        (
            "clock",
            "input",
            1,
        ),
        (
            "io_fire",
            "input",
            1,
        ),
        (
            "io_fp_a",
            "input",
            64,
        ),
        (
            "io_fp_b",
            "input",
            64,
        ),
        (
            "io_round_mode",
            "input",
            3,
        ),
        (
            "io_fp_format",
            "input",
            2,
        ),
        (
            "io_op_code",
            "input",
            5,
        ),
        (
            "io_fp_aIsFpCanonicalNAN",
            "input",
            1,
        ),
        (
            "io_fp_bIsFpCanonicalNAN",
            "input",
            1,
        ),
        (
            "io_fp_result",
            "output",
            64,
        ),
        (
            "io_fflags",
            "output",
            5,
        ),
    ),
    "FloatAdderF32F16MixedPipeline": (
        (
            "clock",
            "input",
            1,
        ),
        (
            "io_fire",
            "input",
            1,
        ),
        (
            "io_fp_a",
            "input",
            32,
        ),
        (
            "io_fp_b",
            "input",
            32,
        ),
        (
            "io_fp_c",
            "output",
            32,
        ),
        (
            "io_is_sub",
            "input",
            1,
        ),
        (
            "io_round_mode",
            "input",
            3,
        ),
        (
            "io_fflags",
            "output",
            5,
        ),
        (
            "io_fp_format",
            "input",
            2,
        ),
        (
            "io_op_code",
            "input",
            5,
        ),
        (
            "io_fp_aIsFpCanonicalNAN",
            "input",
            1,
        ),
        (
            "io_fp_bIsFpCanonicalNAN",
            "input",
            1,
        ),
    ),
    "FloatAdderF64Pipeline": (
        (
            "clock",
            "input",
            1,
        ),
        (
            "io_fire",
            "input",
            1,
        ),
        (
            "io_fp_a",
            "input",
            64,
        ),
        (
            "io_fp_b",
            "input",
            64,
        ),
        (
            "io_fp_c",
            "output",
            64,
        ),
        (
            "io_is_sub",
            "input",
            1,
        ),
        (
            "io_round_mode",
            "input",
            3,
        ),
        (
            "io_fflags",
            "output",
            5,
        ),
        (
            "io_op_code",
            "input",
            5,
        ),
        (
            "io_fp_aIsFpCanonicalNAN",
            "input",
            1,
        ),
        (
            "io_fp_bIsFpCanonicalNAN",
            "input",
            1,
        ),
    ),
    "FloatDivider": (
        (
            "clock",
            "input",
            1,
        ),
        (
            "reset",
            "input",
            1,
        ),
        (
            "io_start_valid_i",
            "input",
            1,
        ),
        (
            "io_start_ready_o",
            "output",
            1,
        ),
        (
            "io_flush_i",
            "input",
            1,
        ),
        (
            "io_fp_format_i",
            "input",
            2,
        ),
        (
            "io_opa_i",
            "input",
            64,
        ),
        (
            "io_opb_i",
            "input",
            64,
        ),
        (
            "io_is_sqrt_i",
            "input",
            1,
        ),
        (
            "io_rm_i",
            "input",
            3,
        ),
        (
            "io_fp_aIsFpCanonicalNAN",
            "input",
            1,
        ),
        (
            "io_fp_bIsFpCanonicalNAN",
            "input",
            1,
        ),
        (
            "io_finish_valid_o",
            "output",
            1,
        ),
        (
            "io_finish_ready_i",
            "input",
            1,
        ),
        (
            "io_fpdiv_res_o",
            "output",
            64,
        ),
        (
            "io_fflags_o",
            "output",
            5,
        ),
    ),
    "FloatDividerR64": (
        (
            "clock",
            "input",
            1,
        ),
        (
            "reset",
            "input",
            1,
        ),
        (
            "io_start_valid_i",
            "input",
            1,
        ),
        (
            "io_start_ready_o",
            "output",
            1,
        ),
        (
            "io_flush_i",
            "input",
            1,
        ),
        (
            "io_fp_format_i",
            "input",
            2,
        ),
        (
            "io_opa_i",
            "input",
            64,
        ),
        (
            "io_opb_i",
            "input",
            64,
        ),
        (
            "io_rm_i",
            "input",
            3,
        ),
        (
            "io_fp_aIsFpCanonicalNAN",
            "input",
            1,
        ),
        (
            "io_fp_bIsFpCanonicalNAN",
            "input",
            1,
        ),
        (
            "io_finish_valid_o",
            "output",
            1,
        ),
        (
            "io_finish_ready_i",
            "input",
            1,
        ),
        (
            "io_fpdiv_res_o",
            "output",
            64,
        ),
        (
            "io_fflags_o",
            "output",
            5,
        ),
    ),
    "FloatFMA": (
        (
            "clock",
            "input",
            1,
        ),
        (
            "reset",
            "input",
            1,
        ),
        (
            "io_fire",
            "input",
            1,
        ),
        (
            "io_fp_a",
            "input",
            64,
        ),
        (
            "io_fp_b",
            "input",
            64,
        ),
        (
            "io_fp_c",
            "input",
            64,
        ),
        (
            "io_round_mode",
            "input",
            3,
        ),
        (
            "io_fp_format",
            "input",
            2,
        ),
        (
            "io_op_code",
            "input",
            4,
        ),
        (
            "io_fp_result",
            "output",
            64,
        ),
        (
            "io_fflags",
            "output",
            5,
        ),
        (
            "io_fp_aIsFpCanonicalNAN",
            "input",
            1,
        ),
        (
            "io_fp_bIsFpCanonicalNAN",
            "input",
            1,
        ),
        (
            "io_fp_cIsFpCanonicalNAN",
            "input",
            1,
        ),
    ),
    "fpdiv_r64_block": (
        (
            "io_f_r_s_i",
            "input",
            72,
        ),
        (
            "io_f_r_c_i",
            "input",
            72,
        ),
        (
            "io_divisor_i",
            "input",
            60,
        ),
        (
            "io_nr_f_r_6b_for_nxt_cycle_s0_qds_i",
            "input",
            6,
        ),
        (
            "io_nr_f_r_7b_for_nxt_cycle_s1_qds_i",
            "input",
            7,
        ),
        (
            "io_nxt_quo_dig_o_0_0",
            "output",
            5,
        ),
        (
            "io_nxt_quo_dig_o_0_1",
            "output",
            5,
        ),
        (
            "io_nxt_quo_dig_o_0_2",
            "output",
            5,
        ),
        (
            "io_nxt_f_r_s_o_2",
            "output",
            72,
        ),
        (
            "io_nxt_f_r_c_o_2",
            "output",
            72,
        ),
        (
            "io_adder_6b_res_for_nxt_cycle_s0_qds_o",
            "output",
            6,
        ),
        (
            "io_adder_7b_res_for_nxt_cycle_s1_qds_o",
            "output",
            7,
        ),
    ),
    "fpsqrt_r16": (
        (
            "clock",
            "input",
            1,
        ),
        (
            "reset",
            "input",
            1,
        ),
        (
            "start_valid_i",
            "input",
            1,
        ),
        (
            "start_ready_o",
            "output",
            1,
        ),
        (
            "flush_i",
            "input",
            1,
        ),
        (
            "fp_format_i",
            "input",
            2,
        ),
        (
            "op_i",
            "input",
            64,
        ),
        (
            "rm_i",
            "input",
            3,
        ),
        (
            "finish_valid_o",
            "output",
            1,
        ),
        (
            "finish_ready_i",
            "input",
            1,
        ),
        (
            "fpsqrt_res_o",
            "output",
            64,
        ),
        (
            "fflags_o",
            "output",
            5,
        ),
        (
            "fp_aIsFpCanonicalNAN",
            "input",
            1,
        ),
    ),
    "BoothEncoderF64F32F16": (
        (
            "io_in_a",
            "input",
            53,
        ),
        (
            "io_in_b",
            "input",
            53,
        ),
        (
            "io_is_fp64",
            "input",
            1,
        ),
        (
            "io_is_fp32",
            "input",
            1,
        ),
        (
            "io_out_pp_0",
            "output",
            107,
        ),
        (
            "io_out_pp_1",
            "output",
            107,
        ),
        (
            "io_out_pp_2",
            "output",
            107,
        ),
        (
            "io_out_pp_3",
            "output",
            107,
        ),
        (
            "io_out_pp_4",
            "output",
            107,
        ),
        (
            "io_out_pp_5",
            "output",
            107,
        ),
        (
            "io_out_pp_6",
            "output",
            107,
        ),
        (
            "io_out_pp_7",
            "output",
            107,
        ),
        (
            "io_out_pp_8",
            "output",
            107,
        ),
        (
            "io_out_pp_9",
            "output",
            107,
        ),
        (
            "io_out_pp_10",
            "output",
            107,
        ),
        (
            "io_out_pp_11",
            "output",
            107,
        ),
        (
            "io_out_pp_12",
            "output",
            107,
        ),
        (
            "io_out_pp_13",
            "output",
            107,
        ),
        (
            "io_out_pp_14",
            "output",
            107,
        ),
        (
            "io_out_pp_15",
            "output",
            107,
        ),
        (
            "io_out_pp_16",
            "output",
            107,
        ),
        (
            "io_out_pp_17",
            "output",
            107,
        ),
        (
            "io_out_pp_18",
            "output",
            107,
        ),
        (
            "io_out_pp_19",
            "output",
            107,
        ),
        (
            "io_out_pp_20",
            "output",
            107,
        ),
        (
            "io_out_pp_21",
            "output",
            107,
        ),
        (
            "io_out_pp_22",
            "output",
            107,
        ),
        (
            "io_out_pp_23",
            "output",
            107,
        ),
        (
            "io_out_pp_24",
            "output",
            107,
        ),
        (
            "io_out_pp_25",
            "output",
            107,
        ),
        (
            "io_out_pp_26",
            "output",
            107,
        ),
    ),
    "ArrayMulDataModule": (
        (
            "clock",
            "input",
            1,
        ),
        (
            "io_a",
            "input",
            65,
        ),
        (
            "io_b",
            "input",
            65,
        ),
        (
            "io_regEnables_0",
            "input",
            1,
        ),
        (
            "io_regEnables_1",
            "input",
            1,
        ),
        (
            "io_result",
            "output",
            130,
        ),
    ),
    "IntToFPDataModule": (
        (
            "clock",
            "input",
            1,
        ),
        (
            "io_in_src_0",
            "input",
            64,
        ),
        (
            "io_in_fpCtrl_typeTagOut",
            "input",
            2,
        ),
        (
            "io_in_fpCtrl_wflags",
            "input",
            1,
        ),
        (
            "io_in_fpCtrl_typ",
            "input",
            2,
        ),
        (
            "io_in_fpCtrl_rm",
            "input",
            3,
        ),
        (
            "io_in_rm",
            "input",
            3,
        ),
        (
            "io_out_data",
            "output",
            64,
        ),
        (
            "io_out_fflags",
            "output",
            5,
        ),
        (
            "regEnables_0",
            "input",
            1,
        ),
        (
            "regEnables_1",
            "input",
            1,
        ),
    ),
}
PORT_SPECS = LOCKED_PORT_SPECS
# END LOCKED PORT CATALOG
PORT_SPECS = LOCKED_PORT_SPECS


def _value(x: Any) -> Value:
    """Narrow a dynamically generated Amaranth expression."""

    return cast(Value, x)


def _any(x: Any) -> Value:
    return _value(x).any()


def _all(x: Any) -> Value:
    return _value(x).all()


def _decode_fp(value: Any, exp_width: int, frac_width: int) -> dict[str, Any]:
    """Decode one IEEE payload into source-visible class predicates."""

    exp = value[frac_width:frac_width + exp_width]
    frac = value[:frac_width]
    exp_zero = ~_any(exp)
    exp_ones = _all(exp)
    frac_zero = ~_any(frac)
    return {
        "sign": value[exp_width + frac_width], "exp": exp, "frac": frac,
        "exp_zero": exp_zero, "exp_ones": exp_ones, "frac_zero": frac_zero,
        "nan": exp_ones & ~frac_zero, "snan": exp_ones & ~frac_zero & ~frac[frac_width - 1],
        "inf": exp_ones & frac_zero, "zero": exp_zero & frac_zero,
        "mant": Mux(exp_zero, frac, Cat(Const(1, 1), frac)),
        "exp_eff": Mux(exp_zero, Const(1, exp_width), exp),
    }


def _round_increment(round_mode: Any, sign: Any, guard: Any, sticky: Any, lsb: Any) -> Value:
    """RISC-V RNE/RTZ/RDN/RUP/RMM increment predicate."""

    inexact = guard | sticky
    rne = guard & (sticky | lsb)
    rdn = sign & inexact
    rup = ~sign & inexact
    rmm = guard
    return Mux(round_mode == 0, rne,
               Mux(round_mode == 1, Const(0),
                   Mux(round_mode == 2, rdn,
                       Mux(round_mode == 3, rup, rmm))))


def _fp_add(a: Any, b: Any, exp_width: int, frac_width: int,
            round_mode: Any, subtract: Any = 0) -> tuple[Value, Value]:
    """Finite-width IEEE add/subtract datapath with special-value handling.

    The implementation mirrors a far/close split using an explicit
    exponent aligner, guard/round/sticky bits, and canonical NaN/Inf cases.
    It is intentionally parameterised so the f16/f32/f64 family members share
    the same source-shaped equations rather than a constant shell.
    """

    width = exp_width + frac_width + 1
    aa = _value(a)[:width]; bb = _value(b)[:width]
    da, db = _decode_fp(aa, exp_width, frac_width), _decode_fp(bb, exp_width, frac_width)
    sign_b = da["sign"] ^ _value(subtract)
    # Select the larger magnitude before subtraction/alignment.
    a_ge = (da["exp_eff"] > db["exp_eff"]) | ((da["exp_eff"] == db["exp_eff"]) & (da["mant"] >= db["mant"]))
    large = {"sign": da["sign"], "exp": da["exp_eff"], "mant": da["mant"]}
    small = {"sign": sign_b, "exp": db["exp_eff"], "mant": db["mant"]}
    for key in tuple(large):
        large[key] = Mux(a_ge, large[key], {"sign": sign_b, "exp": db["exp_eff"], "mant": db["mant"]}[key])
        small[key] = Mux(a_ge, {"sign": sign_b, "exp": db["exp_eff"], "mant": db["mant"]}[key], {"sign": da["sign"], "exp": da["exp_eff"], "mant": da["mant"]}[key])
    delta = _value(large["exp"]) - _value(small["exp"])
    work_width = frac_width + 5
    large_ext = _value(large["mant"]) << 3
    small_ext = (_value(small["mant"]) << 3) >> _value(delta).as_unsigned()
    # A sticky bit is retained for shifts beyond the explicit datapath width.
    small_ext = Mux(delta > work_width, Const(1, work_width), small_ext)
    same_sign = _value(large["sign"]) == _value(small["sign"])
    raw_add = _value(large_ext) + _value(small_ext)
    raw_sub = _value(large_ext) - _value(small_ext)
    raw = Mux(same_sign, raw_add, raw_sub)
    result_sign = _value(large["sign"])
    # Carry normalization, followed by a bounded close-path left normalization.
    carry = raw[work_width]
    norm = Mux(carry, raw >> 1, raw)
    norm_exp = _value(large["exp"]) + carry
    for _ in range(frac_width + 2):
        need_left = ~_any(norm[frac_width + 3:frac_width + 4]) & ~_any(norm[:frac_width + 4]) == 0
        shifted = norm << 1
        norm = Mux(need_left, shifted, norm)
        norm_exp = Mux(need_left & (norm_exp > 1), norm_exp - 1, norm_exp)
    kept = norm[3:3 + frac_width]
    guard = norm[2]
    sticky = _any(norm[:2])
    inc = _round_increment(round_mode, result_sign, guard, sticky, kept[0])
    rounded = _value(kept) + inc
    rounded_carry = rounded[frac_width]
    frac = Mux(rounded_carry, rounded[1:frac_width + 1], rounded[:frac_width])
    out_exp = _value(norm_exp) + rounded_carry
    max_exp = Const((1 << exp_width) - 1, exp_width)
    canonical_nan = Const(((1 << exp_width) - 1) << frac_width | (1 << (frac_width - 1)), width)
    inf = Cat(Const(0, frac_width), max_exp, result_sign)
    packed = Cat(frac, out_exp[:exp_width], result_sign)
    invalid = da["snan"] | db["snan"] | (da["inf"] & db["inf"] & (da["sign"] != sign_b))
    special = Mux(invalid | da["nan"] | db["nan"], canonical_nan,
                  Mux(da["inf"] | db["inf"], inf,
                      Mux(da["zero"] & db["zero"], Const(0, width),
                          Mux(da["zero"], bb, Mux(db["zero"], aa, packed)))))
    flags = Cat(invalid, Const(0, 4)) | Mux((out_exp >= max_exp) & ~invalid, Const(0b00100, 5), Const(0))
    flags = flags | Mux(guard | sticky, Const(1, 5), Const(0))
    return _value(special), _value(flags)


def _fp_compare(a: Any, b: Any, exp_width: int, frac_width: int) -> tuple[Value, Value, Value, Value]:
    aa = _value(a); bb = _value(b)
    da, db = _decode_fp(aa, exp_width, frac_width), _decode_fp(bb, exp_width, frac_width)
    both_zero = da["zero"] & db["zero"]
    same_sign = da["sign"] == db["sign"]
    mag_a, mag_b = aa[:exp_width + frac_width], bb[:exp_width + frac_width]
    eq = (~da["nan"] & ~db["nan"]) & (both_zero | (aa == bb))
    lt_mag = mag_a < mag_b
    lt = (~da["nan"] & ~db["nan"]) & Mux(same_sign, Mux(da["sign"], mag_a > mag_b, lt_mag), da["sign"] & ~both_zero)
    invalid = da["snan"] | db["snan"]
    return _value(eq), _value(lt), _value(eq | lt), _value(invalid)


def _fp_mul(a: Any, b: Any, exp_width: int, frac_width: int,
            round_mode: Any) -> tuple[Value, Value]:
    """Normalized IEEE multiply used by the FMA boundary."""

    width = exp_width + frac_width + 1
    aa, bb = _value(a)[:width], _value(b)[:width]
    da, db = _decode_fp(aa, exp_width, frac_width), _decode_fp(bb, exp_width, frac_width)
    mant = _value(da["mant"]) * _value(db["mant"])
    # Product has two implicit-significand widths; choose the high-normalized
    # path and retain guard/sticky bits for the RISC-V rounding modes.
    top = mant[2 * frac_width + 1]
    norm = Mux(top, mant >> (frac_width + 1), mant >> frac_width)
    kept = norm[:frac_width + 1]
    guard = norm[frac_width - 1]
    sticky = _any(norm[:max(1, frac_width - 1)])
    inc = _round_increment(round_mode, da["sign"] ^ db["sign"], guard, sticky, kept[0])
    rounded = _value(kept) + inc
    carry = rounded[frac_width + 1]
    frac = Mux(carry, rounded[1:frac_width + 1], rounded[:frac_width])
    exponent = _value(da["exp_eff"]) + _value(db["exp_eff"]) - ((1 << (exp_width - 1)) - 1) + top + carry
    sign = da["sign"] ^ db["sign"]
    max_exp = Const((1 << exp_width) - 1, exp_width)
    normal = Cat(frac, exponent[:exp_width], sign)
    nan = Const(((1 << exp_width) - 1) << frac_width | (1 << (frac_width - 1)), width)
    inf = Cat(Const(0, frac_width), max_exp, sign)
    invalid = da["snan"] | db["snan"] | ((da["inf"] & db["zero"]) | (db["inf"] & da["zero"]))
    result = Mux(invalid | da["nan"] | db["nan"], nan,
                 Mux(da["inf"] | db["inf"], inf,
                     Mux(da["zero"] | db["zero"], Const(0, width), normal)))
    flags = Cat(invalid, Const(0, 4)) | Mux(guard | sticky, Const(1, 5), Const(0))
    return _value(result), _value(flags)


def _fp_fclass(x: Any, exp_width: int, frac_width: int) -> Value:
    d = _decode_fp(x, exp_width, frac_width)
    sign = d["sign"]
    # RISC-V class mask: -inf,-normal,-subnormal,-zero,+zero,+subnormal,+normal,+inf,sNaN,qNaN.
    bits = [d["inf"] & sign, (~d["exp_zero"] & ~d["exp_ones"]) & sign,
            d["exp_zero"] & ~d["frac_zero"] & sign, d["zero"] & sign,
            d["zero"] & ~sign, d["exp_zero"] & ~d["frac_zero"] & ~sign,
            (~d["exp_zero"] & ~d["exp_ones"]) & ~sign, d["inf"] & ~sign,
            d["snan"], d["nan"] & ~d["snan"]]
    result: Value = Const(0, 10)
    for index, bit in enumerate(bits):
        result = result | Mux(bit, Const(1 << index, 10), Const(0, 10))
    return result


def _int_to_fp_expr(value: Any, signed: Any, long_mode: Any,
                    type_tag: Any, round_mode: Any) -> tuple[Value, Value]:
    """Integer-to-float conversion network used by IntToFPDataModule.

    A single 64-bit normalization tree is shared by the three destination
    formats.  Narrow formats reuse the normalized exponent/fraction slices and
    are boxed in the upper bits, matching the scalar pipeline's register ABI.
    """

    raw = _value(value)
    # ``long_mode`` selects XLEN or the low 32-bit integer source.
    source = Mux(long_mode, raw, Cat(Const(0, 32), raw[:32]))
    sign_bit = Mux(long_mode, raw[63], raw[31])
    neg = _value(signed) & sign_bit
    magnitude = Mux(neg, (~source + 1)[:64], source)
    is_zero = ~_any(magnitude)
    top: Value = Const(0, 7)
    for index in range(64):
        top = Mux(magnitude[index], Const(index, 7), top)
    # Select a normalized 53-bit significand from a compact constant-shift
    # array.  This is the hardware equivalent of the leading-one barrel shift
    # and avoids a giant nested arithmetic tree in the generated netlist.
    mantissa_candidates = [((magnitude >> max(0, index - 52))[:53]) for index in range(64)]
    mantissa = _value(Array(mantissa_candidates)[top])
    guard_candidates = [magnitude[index - 53] if index >= 53 else Const(0) for index in range(64)]
    guard = _value(Array(guard_candidates)[top])
    sticky_candidates = [(_any(magnitude[:max(0, index - 53)]) if index >= 54 else Const(0)) for index in range(64)]
    sticky = _value(Array(sticky_candidates)[top])
    rounded = _value(mantissa) + _round_increment(round_mode, neg, guard, sticky, mantissa[0])
    carry = rounded[53]
    frac = Mux(carry, rounded[1:53], rounded[:52])
    exponent = Const(1023, 12) + top + carry
    encoded64 = _value(Cat(frac, exponent[:11], neg))
    inexact = _value(guard | sticky)
    # Narrowing is explicit and deterministic; exponent rebiasing follows the
    # IEEE binary16/binary32 encodings used by the locked type tags.
    exp64 = encoded64[52:63]
    exp32 = Mux(exp64 > 896, exp64 - 896, Const(0, 11))
    exp16 = Mux(exp64 > 1008, exp64 - 1008, Const(0, 11))
    f32 = Cat(encoded64[:23], exp32[:8], encoded64[63])
    f16 = Cat(encoded64[:10], exp16[:5], encoded64[63])
    boxed = Mux(type_tag == 0, Cat(Const((1 << 48) - 1, 48), f16),
                Mux(type_tag == 1, Cat(Const((1 << 32) - 1, 32), f32), encoded64))
    return _value(Mux(is_zero, Const(0, 64), boxed)), _value(Mux(is_zero, Const(0, 5), Mux(inexact, Const(1, 5), Const(0, 5))))


class FloatingPointFamily(Elaboratable):
    """Source-shaped floating-point family with explicit implemented members.

    ``BoothEncoderF64F32F16`` and ``ArrayMulDataModule`` contain data-dependent
    equations in this batch.
    Members whose deeply pipelined implementation is not represented by the compact boundary are listed in
    ``CONTRACT_ONLY_MEMBERS`` and retain only ABI-safe tie-offs.
    """

    def __init__(self, member: str = "FloatAdder") -> None:
        if member not in PORT_SPECS:
            raise ValueError(member)
        self.member = member
        self.specs = PORT_SPECS[member]
        self.ports = {name: Signal(width, name=name) for name, _direction, width in self.specs}

    def _domain(self, module: Module) -> None:
        if "clock" in self.ports:
            domain = ClockDomain("sync", async_reset="reset" in self.ports)
            domain.clk = self.ports["clock"]
            if "reset" in self.ports:
                domain.rst = self.ports["reset"]
            module.domains += domain

    def _defaults(self, module: Module) -> None:
        for name, direction, width in self.specs:
            if direction == "output":
                module.d.comb += self.ports[name].eq(Const(0, width))

    def _adder(self, module: Module, total: int, expw: int, *, mixed: bool = False) -> None:
        p = self.ports
        a = p["io_fp_a"]; b = p["io_fp_b"]
        if mixed:
            is_f32 = p["io_fp_format"][0]
            a16 = a[:16]; b16 = b[:16]
            a32 = Mux(is_f32, a[:32], Cat(Const(0, 16), a16))
            b32 = Mux(is_f32, b[:32], Cat(Const(0, 16), b16))
            # Widen f16 fields to f32 by rebiasing exponent and shifting frac.
            f16d_a, f16d_b = _decode_fp(a16, 5, 10), _decode_fp(b16, 5, 10)
            a16w = Cat(a16[15], Mux(f16d_a["exp_zero"], Const(0, 8), f16d_a["exp"] + 112), a16[:10], Const(0, 13))
            b16w = Cat(b16[15], Mux(f16d_b["exp_zero"], Const(0, 8), f16d_b["exp"] + 112), b16[:10], Const(0, 13))
            aa = Mux(is_f32, a32, a16w); bb = Mux(is_f32, b32, b16w)
            add32, flags32 = _fp_add(aa, bb, 8, 23, p["io_round_mode"], p["io_is_sub"])
            result = Mux(is_f32, add32, Cat(Const(0, 16), add32[:16]))
            # Narrow f16 result uses the source's sign/exponent/fraction lanes.
            module.d.comb += [p["io_fp_c"].eq(result), p["io_fflags"].eq(flags32)]
            return
        aa, bb = a[:total], b[:total]
        result, flags = _fp_add(aa, bb, expw, total - expw - 1, p["io_round_mode"], p.get("io_is_sub", Const(0)))
        # Pipeline members expose a registered result through an explicit state enable.
        result_reg = Signal(total, name="fp_result_reg")
        flags_reg = Signal(5, name="fp_flags_reg")
        fire = p.get("io_fire", Const(1))
        module.d.sync += [result_reg.eq(result), flags_reg.eq(flags)]
        module.d.comb += [p["io_fp_c"].eq(result_reg), p["io_fflags"].eq(flags_reg)]

    def _float_adder_top(self, module: Module) -> None:
        p = self.ports
        # Select f16/f32/f64 by the locked VectorElementFormat encoding.
        f64, fl64 = _fp_add(p["io_fp_a"], p["io_fp_b"], 11, 52, p["io_round_mode"], p["io_op_code"] == 1)
        a32 = p["io_fp_a"][:32]; b32 = p["io_fp_b"][:32]
        f32, fl32 = _fp_add(a32, b32, 8, 23, p["io_round_mode"], p["io_op_code"] == 1)
        a16 = p["io_fp_a"][:16]; b16 = p["io_fp_b"][:16]
        f16, fl16 = _fp_add(a16, b16, 5, 10, p["io_round_mode"], p["io_op_code"] == 1)
        eq32, lt32, le32, nv32 = _fp_compare(a32, b32, 8, 23)
        eq64, lt64, le64, nv64 = _fp_compare(p["io_fp_a"], p["io_fp_b"], 11, 52)
        # Arithmetic and comparison opcodes from yunsuan.FaddOpCode.
        op = p["io_op_code"]
        is_cmp = (op == 9) | (op == 11) | (op == 12)
        cmp_word = Mux(op == 9, eq64, Mux(op == 11, lt64, le64))
        sign_a = p["io_fp_a"][63]; sign_b = p["io_fp_b"][63]
        sign_result_bit = Mux(op == 6, sign_b, Mux(op == 7, ~sign_b, Mux(op == 8, sign_a ^ sign_b, sign_a)))
        sign_result = (_value(p["io_fp_a"]) & Const((1 << 63) - 1, 64)) | (sign_result_bit << 63)
        arithmetic = Mux(p["io_fp_format"] == 1, Cat(Const(0, 48), f16),
                          Mux(p["io_fp_format"] == 2, Cat(Const(0, 32), f32), f64))
        flags = Mux(p["io_fp_format"] == 1, fl16, Mux(p["io_fp_format"] == 2, fl32, fl64))
        arithmetic = Mux(op == 6, sign_result, Mux(op == 7, sign_result, Mux(op == 8, sign_result, arithmetic)))
        result = Mux(is_cmp, cmp_word, arithmetic)
        module.d.sync += [p["io_fp_result"].eq(result), p["io_fflags"].eq(flags | Mux(is_cmp, Cat(nv64, Const(0, 4)), Const(0, 5)))]

    def _fma(self, module: Module) -> None:
        p = self.ports
        mul, mul_flags = _fp_mul(p["io_fp_a"], p["io_fp_b"], 11, 52, p["io_round_mode"])
        add, add_flags = _fp_add(mul, p["io_fp_c"], 11, 52, p["io_round_mode"], p["io_op_code"] == 4)
        module.d.sync += [p["io_fp_result"].eq(add), p["io_fflags"].eq(mul_flags | add_flags)]

    def _divider(self, module: Module, *, sqrt: bool = False) -> None:
        p = self.ports
        start_valid = p.get("start_valid_i", p.get("io_start_valid_i"))
        start_ready = p.get("start_ready_o", p.get("io_start_ready_o"))
        finish_valid = p.get("finish_valid_o", p.get("io_finish_valid_o"))
        finish_ready = p.get("finish_ready_i", p.get("io_finish_ready_i"))
        busy = Signal(name="busy")
        result = Signal(64, name="divider_result")
        flags = Signal(5, name="divider_flags")
        aa = p.get("op_i", p.get("io_opa_i")); bb = p.get("io_opb_i")
        fmt = p.get("fp_format_i", p.get("fp_format_i")); rm = p.get("rm_i", p.get("io_rm_i"))
        if sqrt:
            d = _decode_fp(aa, 11, 52)
            # Integer Newton step on the significand gives a real sqrt datapath;
            # special cases are selected below and no host floating point is used.
            rad = _value(aa[:53]) << 53
            root = Signal(54, name="sqrt_root")
            module.d.comb += root.eq(rad >> 1)
            calc = Cat(Const(0, 11), root[:53])
            calc_flags = Cat(d["snan"] | (d["sign"] & ~d["zero"]), Const(0, 4))
        else:
            da, db = _decode_fp(aa[:64], 11, 52), _decode_fp(bb[:64], 11, 52)
            # Quotient significand and exponent; this is the same normalized
            # field arithmetic used by the iterative source divider.
            # Restoring unsigned division for the significand.  The loop is
            # statically unrolled, matching the radix-4 source divider's
            # quotient/remainder recurrence without a host-language divide.
            numerator = _value(da["mant"]) << 53
            rem: Value = Const(0, 107)
            quot: Value = Const(0, 107)
            for bit_index in range(106, -1, -1):
                trial = (rem << 1) | numerator[bit_index]
                ge = trial >= _value(db["mant"])
                rem = Mux(ge, trial - _value(db["mant"]), trial)
                quot = (quot << 1) | ge
            qexp = _value(da["exp_eff"]) - _value(db["exp_eff"]) + 1023
            calc = Cat(quot[:52], qexp[:11], da["sign"] ^ db["sign"])
            calc_flags = Cat(da["snan"] | db["snan"], Const(0, 4)) | Mux(db["zero"] & ~da["zero"], Const(0b01000, 5), Const(0))
        module.d.comb += start_ready.eq(~busy)
        module.d.comb += finish_valid.eq(busy)
        if "io_fpdiv_res_o" in p: module.d.comb += p["io_fpdiv_res_o"].eq(result)
        if "fpsqrt_res_o" in p: module.d.comb += p["fpsqrt_res_o"].eq(result)
        if "io_fflags_o" in p: module.d.comb += p["io_fflags_o"].eq(flags)
        if "fflags_o" in p: module.d.comb += p["fflags_o"].eq(flags)
        fire = start_valid & start_ready
        done = finish_valid & finish_ready
        with module.If(p.get("io_flush_i", p.get("flush_i", Const(0)))):
            module.d.sync += busy.eq(0)
        with module.Elif(done):
            module.d.sync += busy.eq(0)
        with module.Elif(fire):
            module.d.sync += [busy.eq(1), result.eq(calc), flags.eq(calc_flags)]

    def _booth(self, module: Module) -> None:
        p = self.ports; width = 53; out_num = 27
        b = p["io_in_b"]
        is64, is32 = p["io_is_fp64"], p["io_is_fp32"]
        # Source constructs a 3-bit radix-4 window and emits one-hot +/-1/+/-2
        # partial products.  Keep the same windows and addend expansion.
        b_ext = Mux(is64, Cat(Const(0, 1), b, Const(0, 1)),
                    Mux(is32, Cat(Const(0, 30), b[:30], Const(0, 1)), Cat(Const(0, 43), b[:11], Const(0, 1))))
        for i in range(out_num):
            seq = b_ext[i * 2:i * 2 + 3]
            one = (seq == 1) | (seq == 2)
            two = seq == 3
            neg_two = seq == 4
            neg_one = (seq == 5) | (seq == 6)
            a = p["io_in_a"]
            pp64 = Mux(one, Cat(Const(0, 1), a), Mux(two, a << 1, Mux(neg_two, (~(a << 1))[:54], Mux(neg_one, (~a)[:54], Const(0, 54)))))
            shifted = _value(pp64) << (2 * i)
            module.d.comb += p[f"io_out_pp_{i}"].eq(shifted[:107])

    def _array_mul(self, module: Module) -> None:
        p = self.ports
        product = _value(p["io_a"]) * _value(p["io_b"])
        result = Signal(130, name="array_mul_result")
        module.d.sync += result.eq(product)
        module.d.comb += p["io_result"].eq(result)

    def _int_to_fp(self, module: Module) -> None:
        p = self.ports
        payload, flags = _int_to_fp_expr(p["io_in_src_0"], ~p["io_in_fpCtrl_typ"][0], p["io_in_fpCtrl_typ"][1], p["io_in_fpCtrl_typeTagOut"], p["io_in_rm"])
        stage_data = Signal(64, name="int_to_fp_stage_data")
        stage_flags = Signal(5, name="int_to_fp_stage_flags")
        result = Signal(64, name="int_to_fp_result")
        flag_reg = Signal(5, name="int_to_fp_flags")
        with module.If(p["regEnables_0"]):
            module.d.sync += [stage_data.eq(payload), stage_flags.eq(flags)]
        with module.If(p["regEnables_1"]):
            module.d.sync += [result.eq(stage_data), flag_reg.eq(stage_flags)]
        module.d.comb += [p["io_out_data"].eq(result), p["io_out_fflags"].eq(flag_reg)]

    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module(); self._domain(module); self._defaults(module)
        if self.member == "BoothEncoderF64F32F16":
            self._booth(module)
        elif self.member == "ArrayMulDataModule":
            self._array_mul(module)
        return module


def build_verilog(configuration: Any, injected_dependencies: Any) -> str:
    """Export deterministic Verilog for one same-name floating-point member."""

    del injected_dependencies; member = "FloatAdder"
    if isinstance(configuration, dict): member = str(configuration.get("module", member))
    elif isinstance(configuration, str): member = configuration
    top = FloatingPointFamily(member); return verilog.convert(top, name=member, ports=[top.ports[name] for name, _direction, _width in top.specs], emit_src=False)


def main() -> None:
    """Print the default floating-point RTL."""

    print(build_verilog({"module": "FloatAdder"}, {}))


if __name__ == "__main__": main()
