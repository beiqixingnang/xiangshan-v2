"""Floating-point execution family with exact locked port surfaces.

Only members listed in ``IMPLEMENTED_MEMBERS`` claim executable behavior.
Every other member is explicitly marked ``CONTRACT_ONLY`` and retains its
ABI-safe tie-offs until its behavior is closed.
"""

# Module Contract
from __future__ import annotations

from typing import Any, cast

from amaranth import Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.hdl import Value
from amaranth.back import verilog


__all__ = ["COVERED_MODULES", "IMPLEMENTED_MEMBERS", "CONTRACT_ONLY_MEMBERS", "FloatingPointFamily", "build_verilog", "main"]
# Configuration
COVERED_MODULES = ("FloatAdder", "FloatAdderF32F16MixedPipeline", "FloatAdderF64Pipeline", "FloatDivider", "FloatDividerR64", "FloatFMA", "fpdiv_r64_block", "fpsqrt_r16", "BoothEncoderF64F32F16", "ArrayMulDataModule", "IntToFPDataModule")
IMPLEMENTED_MEMBERS: tuple[str, ...] = ("BoothEncoderF64F32F16", "ArrayMulDataModule")
CONTRACT_ONLY_MEMBERS = tuple(member for member in COVERED_MODULES if member not in IMPLEMENTED_MEMBERS)

PortSpec = tuple[str, str, int]

PORT_SPECS: dict[str, tuple[PortSpec, ...]] = {
    'FloatAdder': (
        ('clock', 'input', 1),
        ('io_fire', 'input', 1),
        ('io_fp_a', 'input', 64),
        ('io_fp_b', 'input', 64),
        ('io_round_mode', 'input', 3),
        ('io_fp_format', 'input', 2),
        ('io_op_code', 'input', 5),
        ('io_fp_aIsFpCanonicalNAN', 'input', 1),
        ('io_fp_bIsFpCanonicalNAN', 'input', 1),
        ('io_fp_result', 'output', 64),
        ('io_fflags', 'output', 5),
    ),
    'FloatAdderF32F16MixedPipeline': (
        ('clock', 'input', 1),
        ('io_fire', 'input', 1),
        ('io_fp_a', 'input', 32),
        ('io_fp_b', 'input', 32),
        ('io_fp_c', 'output', 32),
        ('io_is_sub', 'input', 1),
        ('io_round_mode', 'input', 3),
        ('io_fflags', 'output', 5),
        ('io_fp_format', 'input', 2),
        ('io_op_code', 'input', 5),
        ('io_fp_aIsFpCanonicalNAN', 'input', 1),
        ('io_fp_bIsFpCanonicalNAN', 'input', 1),
    ),
    'FloatAdderF64Pipeline': (
        ('clock', 'input', 1),
        ('io_fire', 'input', 1),
        ('io_fp_a', 'input', 64),
        ('io_fp_b', 'input', 64),
        ('io_fp_c', 'output', 64),
        ('io_is_sub', 'input', 1),
        ('io_round_mode', 'input', 3),
        ('io_fflags', 'output', 5),
        ('io_op_code', 'input', 5),
        ('io_fp_aIsFpCanonicalNAN', 'input', 1),
        ('io_fp_bIsFpCanonicalNAN', 'input', 1),
    ),
    'FloatDivider': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_start_valid_i', 'input', 1),
        ('io_start_ready_o', 'output', 1),
        ('io_flush_i', 'input', 1),
        ('io_fp_format_i', 'input', 2),
        ('io_opa_i', 'input', 64),
        ('io_opb_i', 'input', 64),
        ('io_is_sqrt_i', 'input', 1),
        ('io_rm_i', 'input', 3),
        ('io_fp_aIsFpCanonicalNAN', 'input', 1),
        ('io_fp_bIsFpCanonicalNAN', 'input', 1),
        ('io_finish_valid_o', 'output', 1),
        ('io_finish_ready_i', 'input', 1),
        ('io_fpdiv_res_o', 'output', 64),
        ('io_fflags_o', 'output', 5),
    ),
    'FloatDividerR64': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_start_valid_i', 'input', 1),
        ('io_start_ready_o', 'output', 1),
        ('io_flush_i', 'input', 1),
        ('io_fp_format_i', 'input', 2),
        ('io_opa_i', 'input', 64),
        ('io_opb_i', 'input', 64),
        ('io_rm_i', 'input', 3),
        ('io_fp_aIsFpCanonicalNAN', 'input', 1),
        ('io_fp_bIsFpCanonicalNAN', 'input', 1),
        ('io_finish_valid_o', 'output', 1),
        ('io_finish_ready_i', 'input', 1),
        ('io_fpdiv_res_o', 'output', 64),
        ('io_fflags_o', 'output', 5),
    ),
    'FloatFMA': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_fire', 'input', 1),
        ('io_fp_a', 'input', 64),
        ('io_fp_b', 'input', 64),
        ('io_fp_c', 'input', 64),
        ('io_round_mode', 'input', 3),
        ('io_fp_format', 'input', 2),
        ('io_op_code', 'input', 4),
        ('io_fp_result', 'output', 64),
        ('io_fflags', 'output', 5),
        ('io_fp_aIsFpCanonicalNAN', 'input', 1),
        ('io_fp_bIsFpCanonicalNAN', 'input', 1),
        ('io_fp_cIsFpCanonicalNAN', 'input', 1),
    ),
    'fpdiv_r64_block': (
        ('io_f_r_s_i', 'input', 72),
        ('io_f_r_c_i', 'input', 72),
        ('io_divisor_i', 'input', 60),
        ('io_nr_f_r_6b_for_nxt_cycle_s0_qds_i', 'input', 6),
        ('io_nr_f_r_7b_for_nxt_cycle_s1_qds_i', 'input', 7),
        ('io_nxt_quo_dig_o_0_0', 'output', 5),
        ('io_nxt_quo_dig_o_0_1', 'output', 5),
        ('io_nxt_quo_dig_o_0_2', 'output', 5),
        ('io_nxt_f_r_s_o_2', 'output', 72),
        ('io_nxt_f_r_c_o_2', 'output', 72),
        ('io_adder_6b_res_for_nxt_cycle_s0_qds_o', 'output', 6),
        ('io_adder_7b_res_for_nxt_cycle_s1_qds_o', 'output', 7),
    ),
    'fpsqrt_r16': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('start_valid_i', 'input', 1),
        ('start_ready_o', 'output', 1),
        ('flush_i', 'input', 1),
        ('fp_format_i', 'input', 2),
        ('op_i', 'input', 64),
        ('rm_i', 'input', 3),
        ('finish_valid_o', 'output', 1),
        ('finish_ready_i', 'input', 1),
        ('fpsqrt_res_o', 'output', 64),
        ('fflags_o', 'output', 5),
        ('fp_aIsFpCanonicalNAN', 'input', 1),
    ),
    'BoothEncoderF64F32F16': (
        ('io_in_a', 'input', 53),
        ('io_in_b', 'input', 53),
        ('io_is_fp64', 'input', 1),
        ('io_is_fp32', 'input', 1),
        ('io_out_pp_0', 'output', 107),
        ('io_out_pp_1', 'output', 107),
        ('io_out_pp_2', 'output', 107),
        ('io_out_pp_3', 'output', 107),
        ('io_out_pp_4', 'output', 107),
        ('io_out_pp_5', 'output', 107),
        ('io_out_pp_6', 'output', 107),
        ('io_out_pp_7', 'output', 107),
        ('io_out_pp_8', 'output', 107),
        ('io_out_pp_9', 'output', 107),
        ('io_out_pp_10', 'output', 107),
        ('io_out_pp_11', 'output', 107),
        ('io_out_pp_12', 'output', 107),
        ('io_out_pp_13', 'output', 107),
        ('io_out_pp_14', 'output', 107),
        ('io_out_pp_15', 'output', 107),
        ('io_out_pp_16', 'output', 107),
        ('io_out_pp_17', 'output', 107),
        ('io_out_pp_18', 'output', 107),
        ('io_out_pp_19', 'output', 107),
        ('io_out_pp_20', 'output', 107),
        ('io_out_pp_21', 'output', 107),
        ('io_out_pp_22', 'output', 107),
        ('io_out_pp_23', 'output', 107),
        ('io_out_pp_24', 'output', 107),
        ('io_out_pp_25', 'output', 107),
        ('io_out_pp_26', 'output', 107),
    ),
    'ArrayMulDataModule': (
        ('clock', 'input', 1),
        ('io_a', 'input', 65),
        ('io_b', 'input', 65),
        ('io_regEnables_0', 'input', 1),
        ('io_regEnables_1', 'input', 1),
        ('io_result', 'output', 130),
    ),
    'IntToFPDataModule': (
        ('clock', 'input', 1),
        ('io_in_src_0', 'input', 64),
        ('io_in_fpCtrl_typeTagOut', 'input', 2),
        ('io_in_fpCtrl_wflags', 'input', 1),
        ('io_in_fpCtrl_typ', 'input', 2),
        ('io_in_fpCtrl_rm', 'input', 3),
        ('io_in_rm', 'input', 3),
        ('io_out_data', 'output', 64),
        ('io_out_fflags', 'output', 5),
        ('regEnables_0', 'input', 1),
        ('regEnables_1', 'input', 1),
    ),
}

# Implementation
def _value(x: Any) -> Value:
    """Narrow a dynamically generated Amaranth expression."""

    return cast(Value, x)


def _all(x: Any) -> Value:
    return _value(x).all()




class FloatingPointFamily(Elaboratable):
    """Source-shaped floating-point family with explicit implemented members.

    The implemented leaves contain data-dependent combinational or sequential
    equations. Other members retain contract-only behavior.
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


    def _booth(self, module: Module) -> None:
        p = self.ports; out_num = 27
        a, b = p["io_in_a"], p["io_in_b"]
        is64, is32 = p["io_is_fp64"], p["io_is_fp32"]

        # The first Booth window is two bits; later windows overlap by one bit.
        # Keep the observable code-3 selector used by this datapath.
        b_cat = Mux(is64, Cat(b, Const(0, 1)),
                    Mux(is32, Cat(b[:24], Const(0, 30)), Cat(b[:11], Const(0, 43))))

        def onehot(code: Value, first: bool = False) -> Value:
            if first:
                # This two-bit window maps code 3 to the correction selector.
                return Mux(code == 1, Const(0b1000, 4),
                           Mux(code == 2, Const(0b0001, 4),
                               Mux(_all(code), Const(0b0010, 4), Const(0, 4))))
            return Mux((code == 1) | (code == 2), Const(0b1000, 4),
                       Mux(code == 3, Const(0b0100, 4),
                           Mux(code == 4, Const(0b0001, 4),
                               Mux((code == 5) | (code == 6), Const(0b0010, 4), Const(0, 4)))))

        def pp(operand: Value, selector: Value, operand_width: int) -> Value:
            op = _value(operand[:operand_width])
            pos_one = Cat(op, Const(0, 1))
            pos_two = Cat(Const(0, 1), op)
            neg_one = Cat(~op, Const(1, 1))
            neg_two = Cat(Const(1, 1), ~op)
            return _value(Mux(selector[3], pos_one,
                              Mux(selector[2], pos_two,
                                  Mux(selector[1], neg_one,
                                      Mux(selector[0], neg_two, Const(0, operand_width + 1))))))

        selectors: list[Value] = []
        for i in range(out_num):
            code = b_cat[:2] if i == 0 else b_cat[2 * i - 1:2 * i + 2]
            selectors.append(onehot(_value(code), first=i == 0))

        signs = [_value(selector[1]) | _value(selector[0]) for selector in selectors]
        pp64 = [pp(a, selector, 53) for selector in selectors]
        pp32 = [pp(_value(a[:24]), selector, 24) if i <= 13 else Const(0, 25) for i, selector in enumerate(selectors)]
        pp16 = [pp(_value(a[:11]), selector, 11) if i <= 5 else Const(0, 12) for i, selector in enumerate(selectors)]

        def one(width: int) -> Value:
            # Width-padded numeric one used in the partial-product prefixes.
            return Const(1, width)

        f64: list[Value] = []
        f32: list[Value] = []
        f16: list[Value] = []
        for i in range(out_num):
            if i == 0:
                f64.append(_value(Cat(pp64[i], signs[i], signs[i], ~signs[i], Const(0, 50))))
                f32.append(_value(Cat(pp32[i], signs[i], signs[i], ~signs[i], Const(0, 79))))
                f16.append(_value(Cat(pp16[i], signs[i], signs[i], ~signs[i], Const(0, 92))))
            elif i == 1:
                f64.append(_value(Cat(signs[0], Const(0, 1), pp64[i], ~signs[i], one(49), Const(0, 1))))
                f32.append(_value(Cat(signs[0], Const(0, 1), pp32[i], ~signs[i], one(20), Const(0, 59))))
                f16.append(_value(Cat(signs[0], Const(0, 1), pp16[i], ~signs[i], one(7), Const(0, 85))))
            elif i == 26:
                f64.append(_value(Cat(Const(0, 50), signs[25], Const(0, 1), pp64[i], one(1))))
                f32.append(Const(0, 107))
                f16.append(Const(0, 107))
            elif 2 <= i <= 25:
                tail = 2 * (i - 1)
                f64.append(_value(Cat(Const(0, tail), signs[i - 1], Const(0, 1), pp64[i], ~signs[i], one(51 - 2 * i), Const(0, 1))))
                if 2 <= i <= 10:
                    f32.append(_value(Cat(Const(0, tail), signs[i - 1], Const(0, 1), pp32[i], ~signs[i], one(22 - 2 * i), Const(0, 59))))
                elif i == 11:
                    f32.append(_value(Cat(Const(0, 20), signs[10], Const(0, 1), pp32[i], ~signs[i], one(1), Const(0, 59))))
                elif i == 12:
                    f32.append(_value(Cat(Const(0, 22), signs[11], Const(0, 1), pp32[i][:24], Const(0, 59))))
                else:
                    f32.append(Const(0, 107))
                if 2 <= i <= 3:
                    f16.append(_value(Cat(Const(0, tail), signs[i - 1], Const(0, 1), pp16[i], ~signs[i], one(9 - 2 * i), Const(0, 85))))
                elif i == 4:
                    f16.append(_value(Cat(Const(0, 6), signs[3], Const(0, 1), pp16[i], ~signs[i], one(1), Const(0, 85))))
                elif i == 5:
                    f16.append(_value(Cat(Const(0, 8), signs[4], Const(0, 1), pp16[i], one(1), Const(0, 84))))
                else:
                    f16.append(Const(0, 107))
            else:
                f64.append(Const(0, 107)); f32.append(Const(0, 107)); f16.append(Const(0, 107))
        for i in range(out_num):
            module.d.comb += p[f"io_out_pp_{i}"].eq(Mux(is64, f64[i], Mux(is32, f32[i], f16[i])))

    def _array_mul(self, module: Module) -> None:
        p = self.ports
        length = 65
        columns: list[list[Value]] = [[] for _ in range(2 * length)]

        signal_index = 0

        def comb_signal(value: Any, prefix: str) -> Value:
            nonlocal signal_index
            result = Signal(len(value), name=f"mul_{prefix}_{signal_index}")
            signal_index += 1
            module.d.comb += result.eq(value)
            return _value(result)

        b_sext = _value(Cat(p["io_b"], p["io_b"][length - 1]))
        bx2 = (b_sext << 1)[:length + 1]
        neg_b = ~_value(b_sext)
        neg_bx2 = (neg_b << 1)[:length + 1]

        last_x: Value = Const(0, 3)
        for index in range(0, length, 2):
            if index == 0:
                x = Cat(Const(0, 1), p["io_a"][:2])
            elif index + 1 == length:
                x = Cat(p["io_a"][index - 1], p["io_a"][index], p["io_a"][index])
            else:
                x = p["io_a"][index - 1:index + 2]
            x = comb_signal(x, "booth_code")
            pp_temp = comb_signal(
                Mux((x == 1) | (x == 2), b_sext,
                    Mux(x == 3, bx2,
                        Mux(x == 4, neg_bx2,
                            Mux((x == 5) | (x == 6), neg_b, Const(0, length + 1))))),
                "partial_value")
            sign = _value(pp_temp[length])
            correction = comb_signal(
                Mux(last_x == 4, Const(2, 2),
                    Mux((last_x == 5) | (last_x == 6), Const(1, 2), Const(0, 2))),
                "correction")
            last_x = _value(x)
            if index == 0:
                partial = comb_signal(Cat(pp_temp, sign, sign, ~sign), "partial_product")
                weight = 0
            elif index == length - 1 or index == length - 2:
                partial = comb_signal(Cat(correction, pp_temp, ~sign), "partial_product")
                weight = index - 2
            else:
                partial = comb_signal(Cat(correction, pp_temp, ~sign, Const(1, 1)), "partial_product")
                weight = index - 2
            for column_index in range(weight, min(2 * length, weight + len(partial))):
                columns[column_index].append(_value(partial[column_index - weight]))

        def register_enable(value: Value, enable: Value, name: str) -> Value:
            register = Signal(name=name)
            module.d.sync += register.eq(Mux(enable, value, register))
            return register

        columns = [
            [register_enable(bit, p["io_regEnables_0"], f"mul_pp_{column_index}_{bit_index}")
             for bit_index, bit in enumerate(column)]
            for column_index, column in enumerate(columns)
        ]

        def add_one_column(column: list[Value], carry_in: list[Value]) -> tuple[list[Value], list[Value], list[Value]]:
            count = len(column)
            if count == 0:
                return list(carry_in), [], []
            if count == 1:
                return list(column) + list(carry_in), [], []
            if count == 2:
                first_xor = comb_signal(column[0] ^ column[1], "c22_sum")
                carry = comb_signal(column[0] & column[1], "c22_carry")
                return [first_xor] + list(carry_in), [], [carry]
            if count == 3:
                first_xor = comb_signal(column[0] ^ column[1], "c32_xor")
                total = comb_signal(first_xor ^ column[2], "c32_sum")
                carry = comb_signal((column[0] & column[1]) | (first_xor & column[2]), "c32_carry")
                return [total] + list(carry_in), [], [carry]
            if count == 4:
                fifth = carry_in[0] if carry_in else Const(0, 1)
                first_xor = comb_signal(column[0] ^ column[1], "c53_xor_a")
                first_sum = comb_signal(first_xor ^ column[2], "c53_sum_a")
                first_carry = comb_signal((column[0] & column[1]) | (first_xor & column[2]), "c53_carry_a")
                second_xor = comb_signal(first_sum ^ column[3], "c53_xor_b")
                second_sum = comb_signal(second_xor ^ fifth, "c53_sum_b")
                second_carry = comb_signal((first_sum & column[3]) | (second_xor & fifth), "c53_carry_b")
                return [second_sum] + (list(carry_in[1:]) if carry_in else []), [first_carry], [second_carry]
            sum_a, carry1_a, carry2_a = add_one_column(column[:4], carry_in[:1])
            sum_b, carry1_b, carry2_b = add_one_column(column[4:], carry_in[1:])
            return sum_a + sum_b, carry1_a + carry1_b, carry2_a + carry2_b

        def add_all(current: list[list[Value]], depth: int) -> tuple[Value, Value]:
            if max(len(column) for column in current) <= 2:
                summed = Cat(*[column[0] for column in current])
                first_multi = 0
                while len(current[first_multi]) == 1:
                    first_multi += 1
                carry_bits = [column[1] for column in current[first_multi:]]
                carried = Cat(Const(0, first_multi), *carry_bits)
                return _value(summed), _value(carried)

            next_columns: list[list[Value]] = [[] for _ in range(2 * length)]
            carry1: list[Value] = []
            carry2: list[Value] = []
            for column_index, column in enumerate(current):
                summed, next_carry1, next_carry2 = add_one_column(column, carry1)
                next_columns[column_index] = summed + carry2
                carry1, carry2 = next_carry1, next_carry2
            if depth == 4:
                next_columns = [
                    [register_enable(bit, p["io_regEnables_1"], f"mul_reduce_{column_index}_{bit_index}")
                     for bit_index, bit in enumerate(column)]
                    for column_index, column in enumerate(next_columns)
                ]
            return add_all(next_columns, depth + 1)

        product_sum, product_carry = add_all(columns, 0)
        result = comb_signal(product_sum + product_carry, "product")
        module.d.comb += p["io_result"].eq(result)


    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module(); self._domain(module); self._defaults(module)
        if self.member == "BoothEncoderF64F32F16":
            self._booth(module)
        elif self.member == "ArrayMulDataModule":
            self._array_mul(module)
        return module


# Public Adapter
def build_verilog(configuration: Any, injected_dependencies: Any) -> str:
    """Export deterministic Verilog for one same-name floating-point member."""

    del injected_dependencies; member = "FloatAdder"
    if isinstance(configuration, dict): member = str(configuration.get("module", member))
    elif isinstance(configuration, str): member = configuration
    top = FloatingPointFamily(member); return verilog.convert(top, name=member, ports=[top.ports[name] for name, _direction, _width in top.specs], emit_src=False)


# Direct Entry
def main() -> None:
    """Print the default floating-point RTL."""

    print(build_verilog({"module": "FloatAdder"}, {}))


if __name__ == "__main__": main()
