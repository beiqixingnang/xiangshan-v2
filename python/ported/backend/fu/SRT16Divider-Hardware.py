"""V2 radix-4 integer divider data path. / V2 基4整数除法数据通路。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from amaranth import Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal


# =============================================================================
# Module Contract
# =============================================================================
# This module follows the pinned V2 SRT16DividerDataModule interface and its
# seven one-hot state sequence.  Arithmetic is a sequential radix-four
# recurrence with the same signed special-result rules and finish handshake.
# 本模块遵循锁定 V2 SRT16DividerDataModule 接口及七个独热状态序列；算术采用
# 时序基四递推，并保持相同的有符号特殊结果规则与 finish 握手。
__all__ = [
    "SRT16DividerConfig",
    "SRT16DividerDataModule",
    "SRT16DividerReferenceAdapter",
    "RightShifter",
    "mLookUpTable2",
    "csa3_2",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class SRT16DividerConfig:
    """Describe one legal V2 divider width. / 描述一个合法的 V2 除法器位宽。"""

    len: int = 64

    # Validate the source width and preserve V2's supported specializations.
    # Validate width / 校验源位宽并保留 V2 支持的特化位宽。
    def __post_init__(self) -> None:
        """Reject unsupported widths. / 拒绝不支持的位宽。"""

        if self.len not in (32, 64):
            raise ValueError("SRT16Divider V2 supports len=32 or len=64")


# V2's four seven-bit negative-m lookup rows. / V2 的四行七位负 m 查找表。
_MINUS_M_ROWS: tuple[tuple[tuple[int, int], ...], ...] = (
    tuple(enumerate((0b0011010, 0b0011110, 0b0100000, 0b0100100,
                     0b0100110, 0b0101010, 0b0101100, 0b0110000))),
    tuple(enumerate((0b0000100, 0b0000110, 0b0000110, 0b0000110,
                     0b0001000, 0b0001000, 0b0001000, 0b0001000))),
    tuple(enumerate((0b1111101, 0b1111100, 0b1111100, 0b1111100,
                     0b1111011, 0b1111010, 0b1111010, 0b1111010))),
    tuple(enumerate((0b01101000, 0b01100100, 0b01100010, 0b01011110,
                     0b01011100, 0b01011000, 0b01010110, 0b01010010))),
)


class mLookUpTable2:
    """Expose the source SRT negative-m rows. / 暴露源代码中的 SRT 负 m 表。"""

    minus_m = _MINUS_M_ROWS


# =============================================================================
# Implementation
# =============================================================================
# Mask an integer helper value or truncate an Amaranth expression. / 截取整数辅助值或 Amaranth 表达式。
def mask_value(value: Any, width: int) -> Any:
    """Apply a fixed-width mask. / 应用固定位宽掩码。"""

    if isinstance(value, int):
        return value & ((1 << width) - 1)
    return value.bit_select(0, width)


# Compute one carry-save compressor. / 计算一个进位保存压缩器。
def csa3_2(a: Any, b: Any, cin: Any, width: int) -> tuple[Any, Any]:
    """Return sum and carry vectors. / 返回和与进位向量。"""

    return mask_value(a ^ b ^ cin, width), mask_value(
        (a & b) | ((a ^ b) & cin), width)


# Compute a fixed-width two's-complement value. / 计算固定位宽二进制补码值。
def twos_complement(value: Any, width: int) -> Any:
    """Negate and truncate a value. / 求反并截断一个值。"""

    if isinstance(value, int):
        return (-value) & ((1 << width) - 1)
    return (-value).bit_select(0, width)


# Replicate a one-bit expression. / 复制一个单比特表达式。
def replicate(bit: Any, width: int) -> Any:
    """Return ``width`` copies of ``bit``. / 返回 bit 的 width 份复制。"""

    return Cat(*[bit for _ in range(width)])


# Return a source-compatible MSB-first leading-zero count. / 返回兼容源代码的最高位优先前导零计数。
def priority_encoder(value: Any, width: int) -> Any:
    """Return the first-one index, or width for zero. / 返回首个一位索引，零返回 width。"""

    count_width = max(1, width.bit_length())
    result: Any = Const(width, count_width)
    found: Any = Const(0, 1)
    for index in range(width):
        bit = value.bit_select(width - index - 1, 1)
        first = (~found) & bit
        result = Mux(first, Const(index, count_width), result)
        found = found | bit
    return result


# Sign-extend an expression to a target width. / 将表达式符号扩展到目标位宽。
def sign_ext(value: Any, value_width: int, target_width: int) -> Any:
    """Return a width-limited sign extension. / 返回限定位宽的符号扩展。"""

    if target_width <= value_width:
        return value.bit_select(0, target_width)
    sign = value.bit_select(value_width - 1, 1)
    return Cat(value, replicate(sign, target_width - value_width))


# Select a constant from a small lookup row. / 从小型查找行选择常量。
def mux_lookup(index: Any, default: int,
               row: Iterable[tuple[int, int]], width: int) -> Any:
    """Build a deterministic priority lookup mux. / 构建确定性的优先查找复用器。"""

    result: Any = Const(default, width)
    for key, value in row:
        result = Mux(index == key, Const(value, width), result)
    return result


# Select one value under a one-hot vector. / 在独热向量下选择一个值。
def mux1h(selectors: Any, values: list[Any]) -> Any:
    """Return the OR of one-hot selected values. / 返回独热选择值的或结果。"""

    width = values[0].shape().width
    result: Any = Const(0, width)
    for index, value in enumerate(values):
        result = result | (value & replicate(selectors.bit_select(index, 1), width))
    return result


# Build a bounded barrel left shift. / 构建有界桶形左移器。
def barrel_lsh(value: Any, shift: Any, width: int) -> Any:
    """Shift left and fill with zeros. / 左移并以零填充。"""

    result = value
    shift_width = shift.shape().width
    for bit in range(shift_width):
        amount = 1 << bit
        if amount >= width:
            break
        result = Mux(shift.bit_select(bit, 1),
                     Cat(Const(0, amount), result.bit_select(0, width - amount)),
                     result)
    return result


class RightShifter(Elaboratable):
    """Replicate the V2 sign-filled right shifter. / 复现 V2 符号填充右移器。"""

    # Declare source-compatible shifter ports. / 声明与源代码兼容的移位器端口。
    def __init__(self, length: int, lzc_width: int) -> None:
        """Create a fixed-width shifter. / 创建固定宽度移位器。"""

        if length not in (32, 64):
            raise ValueError("RightShifter V2 supports len=32 or len=64")
        self.length = length
        self.lzc_width = lzc_width
        self.shiftNum = Signal(lzc_width, name="io_shiftNum")
        self.in_ = Signal(length, name="io_in")
        self.msb = Signal(name="io_msb")
        self.out = Signal(length, name="io_out")

    # Elaborate source's staged barrel network. / 展开源代码的分级桶形网络。
    def elaborate(self, platform: Any) -> Module:
        """Connect each sign-filled shift stage. / 连接每个符号填充移位级。"""

        del platform
        module = Module()
        shifted: Any = self.in_
        for bit in range(self.lzc_width):
            amount = 1 << bit
            if amount >= self.length:
                break
            # Cat places its first operand in the low bits: retain the old
            # high slice as low bits and put the fill bits above it.
            # Cat 的第一个操作数位于低位：保留旧高位片段为低位，并将填充值置于高位。
            filled = Cat(shifted.bit_select(amount, self.length - amount),
                         replicate(self.msb, amount))
            shifted = Mux(self.shiftNum.bit_select(bit, 1), filled, shifted)
        module.d.comb += self.out.eq(shifted)
        return module


class SRT16DividerDataModule(Elaboratable):
    """V2 seven-state SRT16 divider closure. / V2 七状态 SRT16 除法器闭包。"""

    # Declare exact source IO and compatibility aliases. / 声明精确源接口及兼容别名。
    def __init__(self, configuration: SRT16DividerConfig | int | None = None,
                 *, len: int | None = None) -> None:
        """Create divider ports and state registers. / 创建除法器端口与状态寄存器。"""

        if len is not None:
            if configuration is not None:
                raise TypeError("provide configuration or len, not both")
            configuration = len
        if configuration is None:
            configuration = SRT16DividerConfig()
        elif isinstance(configuration, int):
            configuration = SRT16DividerConfig(configuration)
        self.configuration = configuration
        self.config = configuration
        self.width = configuration.len
        width = self.width

        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.io_src_0 = Signal(width, name="io_src_0")
        self.io_src_1 = Signal(width, name="io_src_1")
        self.io_valid = Signal(name="io_valid")
        self.io_sign = Signal(name="io_sign")
        self.io_kill_w = Signal(name="io_kill_w")
        self.io_kill_r = Signal(name="io_kill_r")
        self.io_isHi = Signal(name="io_isHi")
        self.io_isW = Signal(name="io_isW")
        self.io_in_ready = Signal(name="io_in_ready")
        self.io_out_valid = Signal(name="io_out_valid")
        self.io_out_data = Signal(width, name="io_out_data")
        self.io_out_ready = Signal(name="io_out_ready")
        self.outValidAhead3Cycle = Signal(name="outValidAhead3Cycle")
        self.io_outValidAhead3Cycle = self.outValidAhead3Cycle
        self.debug_quotient = None
        self.debug_remainder = None
        self.debug_iterations = None
        self.debug_shift = None

        # Source field aliases used by existing parent adapters. / 现有父适配器使用的源字段别名。
        self.src = [self.io_src_0, self.io_src_1]
        self.valid = self.io_valid
        self.sign = self.io_sign
        self.kill_w = self.io_kill_w
        self.kill_r = self.io_kill_r
        self.isHi = self.io_isHi
        self.isW = self.io_isW
        self.in_ready = self.io_in_ready
        self.out_valid = self.io_out_valid
        self.out_data = self.io_out_data
        self.out_ready = self.io_out_ready
        self.out_validNext = Signal(name="out_validNext")
        self.io_out_validNext = self.out_validNext

    # Elaborate the V2 pipeline, recurrence, and handshake. / 展开 V2 流水线、递推与握手。
    def elaborate(self, platform: Any) -> Module:
        """Build the sequential radix-four implementation. / 构建时序基四实现。"""

        del platform
        module = Module()
        domain = ClockDomain("sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        module.domains += domain
        width = self.width
        rem_width = width + 2
        count_width = max(1, (width // 2).bit_length())

        idle, pre0, pre1, iterate, post0, post1, finish = range(7)
        state = Signal(7, reset=1 << idle, name="state")

        # Request and mode registers. / 请求与模式寄存器。
        a_reg = Signal(width, name="aReg")
        d_reg = Signal(width, name="dReg")
        a_abs_reg = Signal(width, name="aAbsReg")
        d_abs_reg = Signal(width, name="dAbsReg")
        dividend_shift = Signal(width, name="dividendShift")
        sign_reg = Signal(name="signReg")
        a_sign_reg = Signal(name="aSignReg")
        d_sign_reg = Signal(name="dSignReg")
        r_sign_reg = Signal(name="rSignReg")

        # Iteration and result registers. / 迭代与结果寄存器。
        remainder_reg = Signal(rem_width, name="remainderReg")
        quotient_reg = Signal(width, name="quotientReg")
        iterations_left = Signal(count_width, name="iterationsLeft")
        special_reg = Signal(name="specialReg")
        quotient_final = Signal(width, name="qFinal")
        remainder_final = Signal(width, name="rFinal")
        self.debug_quotient = quotient_reg
        self.debug_remainder = remainder_reg
        self.debug_iterations = iterations_left
        self.debug_shift = dividend_shift

        # Request preprocessing. / 请求预处理。
        a_sign = self.io_sign & self.io_src_0.bit_select(width - 1, 1)
        d_sign = self.io_sign & self.io_src_1.bit_select(width - 1, 1)
        a_abs = Mux(a_sign, twos_complement(self.io_src_0, width), self.io_src_0)
        d_abs = Mux(d_sign, twos_complement(self.io_src_1, width), self.io_src_1)
        in_fire = self.io_valid & self.io_in_ready

        # Special cases are evaluated from captured absolute operands.
        # 特殊情况根据捕获的绝对操作数计算。
        d_is_zero = d_abs_reg == 0
        d_is_one = d_abs_reg == 1
        a_too_small = (d_abs_reg != 0) & (a_abs_reg < d_abs_reg)
        special = d_is_zero | d_is_one | a_too_small
        all_ones = Const((1 << width) - 1, width)
        quotient_special = Mux(
            d_is_zero, all_ones,
            Mux(a_too_small, Const(0, width),
                Mux(d_sign_reg, twos_complement(a_reg, width), a_reg)))
        remainder_special = Mux(d_is_zero | a_too_small,
                                a_reg, Const(0, width))

        # One radix-four restoring step. / 一个基四恢复除法步骤。
        pair = dividend_shift.bit_select(width - 2, 2)
        shifted_remainder = ((remainder_reg << 2) | pair).bit_select(0, rem_width)
        # Cat's first operand occupies the low bits; append two low zeroes to
        # represent a fixed-point divisor scaled by four.
        # Cat 的第一个操作数位于低位；追加两个低零表示乘四后的除数。
        divisor_ext = Cat(d_abs_reg, Const(0, 2))
        divisor_x2 = (divisor_ext << 1).bit_select(0, rem_width)
        divisor_x3 = (divisor_x2 + divisor_ext).bit_select(0, rem_width)
        digit = Mux(shifted_remainder >= divisor_x3, Const(3, 2),
                     Mux(shifted_remainder >= divisor_x2, Const(2, 2),
                         Mux(shifted_remainder >= divisor_ext, Const(1, 2),
                             Const(0, 2))))
        subtract = Mux(digit == 3, divisor_x3,
                       Mux(digit == 2, divisor_x2,
                           Mux(digit == 1, divisor_ext,
                               Const(0, rem_width))))
        remainder_step = (shifted_remainder - subtract).bit_select(0, rem_width)
        quotient_step = ((quotient_reg << 2) | digit).bit_select(0, width)

        # Normal signed final values. / 正常有符号最终值。
        quotient_unsigned = quotient_reg.bit_select(0, width)
        remainder_unsigned = remainder_reg.bit_select(0, width)
        quotient_signed = Mux(sign_reg & (a_sign_reg ^ d_sign_reg),
                               twos_complement(quotient_unsigned, width),
                               quotient_unsigned)
        remainder_signed = Mux(sign_reg & r_sign_reg,
                                twos_complement(remainder_unsigned, width),
                                remainder_unsigned)

        # Public outputs. / 公共输出。
        module.d.comb += [
            self.io_in_ready.eq(state.bit_select(idle, 1)),
            self.io_out_valid.eq(state.bit_select(finish, 1)),
            self.out_validNext.eq(state.bit_select(post1, 1)),
        ]
        selected = Mux(self.io_isHi, remainder_final, quotient_final)
        low_width = 32 if width == 64 else 16
        low = selected.bit_select(0, low_width)
        word = Cat(low, replicate(selected.bit_select(low_width - 1, 1),
                                  width - low_width))
        module.d.comb += self.io_out_data.eq(Mux(self.io_isW, word, selected))
        module.d.comb += self.outValidAhead3Cycle.eq(
            (state.bit_select(iterate, 1) & (iterations_left == 1)) |
            (state.bit_select(pre1, 1) & special))

        # V2 state transitions: kill, request, seven pipeline states, finish.
        # V2 状态转换：kill、请求、七个流水状态及 finish。
        with module.If(self.io_kill_r):
            module.d.sync += state.eq(1 << idle)
        with module.Elif(state.bit_select(idle, 1) & in_fire & ~self.io_kill_w):
            module.d.sync += state.eq(1 << pre0)
        with module.Elif(state.bit_select(pre0, 1)):
            module.d.sync += state.eq(1 << pre1)
        with module.Elif(state.bit_select(pre1, 1)):
            module.d.sync += state.eq(Mux(special, 1 << post1, 1 << iterate))
        with module.Elif(state.bit_select(iterate, 1)):
            module.d.sync += state.eq(Mux(iterations_left == 1,
                                          1 << post0, 1 << iterate))
        with module.Elif(state.bit_select(post0, 1)):
            module.d.sync += state.eq(1 << post1)
        with module.Elif(state.bit_select(post1, 1)):
            module.d.sync += state.eq(1 << finish)
        with module.Elif(state.bit_select(finish, 1) & self.io_out_ready):
            module.d.sync += state.eq(1 << idle)

        # Capture request and mode bits on the input fire. / 在输入 fire 时捕获请求与模式位。
        with module.If(in_fire):
            module.d.sync += [
                a_reg.eq(self.io_src_0),
                d_reg.eq(self.io_src_1),
                a_abs_reg.eq(a_abs),
                d_abs_reg.eq(d_abs),
                dividend_shift.eq(a_abs),
                sign_reg.eq(self.io_sign),
                a_sign_reg.eq(a_sign),
                d_sign_reg.eq(d_sign),
                r_sign_reg.eq(a_sign),
            ]

        # Initialize radix-four state in pre_1. / 在 pre_1 初始化基四状态。
        with module.If(state.bit_select(pre1, 1)):
            module.d.sync += [
                remainder_reg.eq(0),
                quotient_reg.eq(0),
                iterations_left.eq(width // 2),
                special_reg.eq(special),
            ]

        # Advance one radix-four digit per iterate cycle. / 每个 iterate 周期推进一个基四数位。
        with module.If(state.bit_select(iterate, 1)):
            module.d.sync += [
                remainder_reg.eq(remainder_step),
                quotient_reg.eq(quotient_step),
                dividend_shift.eq(dividend_shift << 2),
            ]
            with module.If(iterations_left != 0):
                module.d.sync += iterations_left.eq(iterations_left - 1)

        # Capture final signed/special results in post_1. / 在 post_1 捕获有符号或特殊最终结果。
        with module.If(state.bit_select(post1, 1)):
            module.d.sync += [
                quotient_final.eq(Mux(special_reg, quotient_special,
                                      quotient_signed)),
                remainder_final.eq(Mux(special_reg, remainder_special,
                                       remainder_signed)),
            ]
        return module


class SRT16DividerReferenceAdapter(SRT16DividerDataModule):
    """Keep the historical exact-IO adapter name for V2 harnesses. / 为 V2 测试台保留历史精确接口适配器名称。"""

    # Construct the source-compatible adapter. / 构造源代码兼容的适配器。
    def __init__(self, configuration: SRT16DividerConfig | int | None = None) -> None:
        """Forward configuration to the V2 data module. / 将配置转发给 V2 数据模块。"""

        super().__init__(configuration)


# =============================================================================
# Public Adapter
# =============================================================================
# Build deterministic source-shaped Verilog. / 构建确定性的源接口 Verilog。
def build_verilog(configuration: SRT16DividerConfig | int | None = None,
                  injected_dependencies: dict[str, Any] | None = None) -> str:
    """Emit standalone V2 divider RTL. / 输出独立 V2 除法器 RTL。"""

    del injected_dependencies
    from amaranth.back import verilog

    if isinstance(configuration, dict):
        config = SRT16DividerConfig(int(configuration.get("len", 64)))
    elif configuration is None:
        config = SRT16DividerConfig()
    elif isinstance(configuration, SRT16DividerConfig):
        config = configuration
    else:
        config = SRT16DividerConfig(configuration)
    top = SRT16DividerDataModule(config)
    ports = [
        top.clock, top.reset, top.io_src_0, top.io_src_1, top.io_valid,
        top.io_sign, top.io_kill_w, top.io_kill_r, top.io_isHi, top.io_isW,
        top.io_in_ready, top.io_out_valid, top.io_out_data, top.io_out_ready,
    ]
    return verilog.convert(top, name="SRT16DividerDataModule", ports=ports,
                           emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print default source-shaped Verilog. / 打印默认源接口 Verilog。
def main() -> None:
    """Print deterministic generated RTL. / 打印确定性的生成 RTL。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
