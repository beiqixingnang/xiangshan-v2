"""UHSC Kunminghu V2 Fudian arithmetic helper aggregate.
昆明湖 V2 Fudian 算术辅助聚合边界，集中保留逐位辅助器契约。

The aggregate preserves the bit-level contracts of CLZ, LZA, ShiftRightJam,
CSA and the unsigned multiplier helpers used by the Fudian floating-point
datapath.  Scala utility files are intentionally condensed into this single
Build-Cpu boundary with explicit source provenance.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Mapping, cast

from amaranth import Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog
from amaranth.hdl.ast import Value


# =============================================================================
# Module Contract
# =============================================================================
# The family covers the five pinned utility sources. / 此 family 覆盖锁定的五个工具源文件。

__all__ = [
    'ArithmeticConfig',
    'FudianArithmetic',
    'clz',
    'lza',
    'shift_right_jam',
    'csa',
    'csa5_3',
    'multiply_unsigned',
    'multiply_signed',
    'round_shift_right',
    'booth_radix4_digits',
    'build_verilog',
    'main',
]


# Cast Amaranth generator controls to the context-manager protocol. / 将 Amaranth 生成器控制转换为上下文管理器协议。
def amaranth_if(module: Module, condition: Any) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.If(condition))


# Cast an Amaranth elif branch to the context-manager protocol. / 将 Amaranth elif 分支转换为上下文管理器协议。
def amaranth_elif(module: Module, condition: Any) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.Elif(condition))


# Narrow dynamic Amaranth values at the DSL boundary. / 在 DSL 边界窄化动态 Amaranth 值。
def amaranth_value(expression: Any) -> Value:
    return cast(Value, expression)


# Count leading zeroes in a fixed-width value. / 计算定宽数值的前导零数量。
def clz(value: int, width: int) -> int:
    """Return CLZ matching Chisel PriorityEncoder semantics. / 返回与 Chisel PriorityEncoder 一致的 CLZ。"""
    if width < 1 or value < 0 or value >= (1 << width):
        raise ValueError("invalid CLZ value or width")
    if value == 0:
        return width - 1
    return width - value.bit_length()


# Compute Fudian LZA recurrence. / 计算 Fudian LZA 递推。
def lza(a: int, b: int, width: int) -> int:
    """Return bit-exact LZA.f for width-bit operands. / 返回定宽输入逐位匹配的 LZA.f。"""
    if width < 1 or min(a, b) < 0 or max(a, b) >= (1 << width):
        raise ValueError("invalid LZA operand or width")
    result = 0
    previous_k = 0
    for index in range(width):
        abit, bbit = (a >> index) & 1, (b >> index) & 1
        p = abit ^ bbit
        k = (1 - abit) & (1 - bbit)
        bit = 0 if index == 0 else p ^ (1 - previous_k)
        result |= bit << index
        previous_k = k
    return result


# Shift right while collecting discarded sticky bits. / 右移并收集被丢弃位形成 sticky。
def shift_right_jam(value: int, shift: int, width: int) -> tuple[int, int]:
    """Return ``(shifted, sticky)`` matching ShiftRightJam.scala. / 返回与源码一致的移位值及 sticky。"""
    if width < 1 or value < 0 or value >= (1 << width) or shift < 0:
        raise ValueError("invalid ShiftRightJam input")
    if shift > width:
        return 0, int(value != 0)
    return (value >> shift), int((value & ((1 << shift) - 1)) != 0)


# Round a right shift using Fudian guard/round/sticky modes. / 使用 Fudian G/R/S 模式舍入右移。
def round_shift_right(value: int, shift: int, width: int, rounding: int = 0) -> tuple[int, int]:
    """Round a right shift using the five Fudian rounding modes.

    ``RNE/RTZ/RDN/RUP/RMM`` are encoded as 0..4 in ``package.scala``.  The
    helper returns the rounded ``width``-bit value and an inexact flag; it is
    deliberately integer-only so the same guard/round/sticky equations can be
    used by software checks and by the generated datapath.
    """
    if width < 1 or value < 0 or shift < 0 or rounding not in range(5):
        raise ValueError("invalid rounded shift arguments")
    mask = (1 << width) - 1
    value &= mask
    if shift == 0:
        return value, 0
    if shift >= width:
        discarded = value
        base = 0
        guard = (value >> (shift - 1)) & 1 if shift <= value.bit_length() else 0
        sticky = int(discarded != 0)
    else:
        base = value >> shift
        discarded = value & ((1 << shift) - 1)
        guard = (discarded >> (shift - 1)) & 1
        sticky = int((discarded & ((1 << (shift - 1)) - 1)) != 0)
    inexact = int(discarded != 0)
    if rounding == 0:  # RNE, ties to even
        up = bool(guard and (sticky or (base & 1)))
    elif rounding == 1:  # RTZ
        up = False
    elif rounding == 2:  # RDN for a positive magnitude
        up = False
    elif rounding == 3:  # RUP for a positive magnitude
        up = bool(inexact)
    else:  # RMM, ties away from zero
        up = bool(guard)
    return (base + int(up)) & mask, inexact


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class ArithmeticConfig:
    """Static widths for the aggregate arithmetic helper boundary."""

    width: int = 64

    # Validate helper width. / 校验算术辅助器位宽。
    def __post_init__(self) -> None:
        if self.width < 2 or self.width > 256:
            raise ValueError("arithmetic width must be in [2, 256]")


# =============================================================================
# Hardware boundary
# =============================================================================
# The arithmetic helper boundary follows the configuration contract. /
# 算术辅助边界紧随配置契约。

# =============================================================================
# Implementation
# =============================================================================
# Compute a carry-save sum and carry vector. / 计算进位保存加法的和与进位向量。
def csa(a: int, b: int, c: int, width: int) -> tuple[int, int]:
    """Return ``(sum, carry)`` for three width-bit operands. / 返回三个定宽操作数的（和、进位）。"""
    if width < 1:
        raise ValueError("CSA width must be positive")
    mask = (1 << width) - 1
    a, b, c = a & mask, b & mask, c & mask
    return (a ^ b ^ c) & mask, ((a & b) | (a & c) | (b & c)) & mask


# Compute the bounded unsigned multiplier result. / 计算有界无符号乘法结果。
def multiply_unsigned(a: int, b: int, width: int) -> int:
    """Return a ``2*width``-bit product. / 返回 2*width 位乘积。"""
    if width < 1:
        raise ValueError("multiplier width must be positive")
    mask = (1 << width) - 1
    return ((a & mask) * (b & mask)) & ((1 << (2 * width)) - 1)


# Reduce five CSA inputs exactly as CSA5_3's two CSA3_2 layers. /
# 按 CSA5_3 的两层 CSA3_2 精确压缩五个输入。
def csa5_3(a: int, b: int, c: int, d: int, e: int, width: int) -> tuple[int, int, int]:
    """Return the three unshifted carry-save vectors emitted by ``CSA5_3``."""

    first_sum, first_carry = csa(a, b, c, width)
    second_sum, second_carry = csa(first_sum, d, e, width)
    return second_sum, first_carry, second_carry


# Interpret one finite-width operand as two's-complement. /
# 将一个定宽操作数解释为补码。
def _signed_value(value: int, width: int) -> int:
    mask = (1 << width) - 1
    value &= mask
    return value - (1 << width) if value & (1 << (width - 1)) else value


# Compute the signed product represented by Multiplier.scala's Booth tree. /
# 计算 Multiplier.scala Booth 树表示的有符号乘积。
def multiply_signed(a: int, b: int, width: int) -> int:
    """Return the width*2 two's-complement product used by Fudian helpers."""

    if width < 1:
        raise ValueError("multiplier width must be positive")
    return (_signed_value(a, width) * _signed_value(b, width)) & ((1 << (2 * width)) - 1)


# Decode radix-4 Booth recoding windows used by Multiplier.scala. /
# 解码 Multiplier.scala 使用的 radix-4 Booth 重编码窗口。
def booth_radix4_digits(value: int, width: int) -> list[int]:
    """Return low-to-high Booth coefficients in ``{-2,-1,0,1,2}``."""

    if width < 2:
        raise ValueError("Booth recoding requires width >= 2")
    signed = _signed_value(value, width)
    # Append the implicit low zero and sign-extend both high bits, matching
    # ``Cat(a(1,0), 0.U)`` / ``SignExt(a(i,i-1), 3)`` in the source.
    encoded = (signed << 1) & ((1 << (width + 3)) - 1)
    if signed < 0:
        encoded |= ((1 << 3) - 1) << (width + 1)
    table = {0b000: 0, 0b111: 0, 0b001: 1, 0b010: 1,
             0b011: 2, 0b100: -2, 0b101: -1, 0b110: -1}
    return [table[(encoded >> (2 * index)) & 0b111]
            for index in range((width + 1) // 2)]


class FudianArithmetic(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Combinational CLZ/LZA/shift-jam/multiply helper boundary."""

    # Construct helper ports. / 构造辅助器端口。
    def __init__(self, configuration: ArithmeticConfig | None = None) -> None:
        self.configuration = configuration or ArithmeticConfig()
        width = self.configuration.width
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.a = Signal(width, name="io_a")
        self.b = Signal(width, name="io_b")
        self.shift = Signal(max(1, (width + 1).bit_length()), name="io_shift")
        self.operation = Signal(3, name="io_operation")
        self.result = Signal(width * 2, name="io_result")
        self.auxiliary = Signal(width, name="io_auxiliary")
        self.sticky = Signal(name="io_sticky")

    # Elaborate arithmetic operations. / 展开算术操作。
    def elaborate(self, platform: Any) -> Module:
        del platform
        width = self.configuration.width
        m = Module()
        domain = ClockDomain("fudian_arithmetic", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.fudian_arithmetic = domain
        m.d.comb += [self.result.eq(0), self.auxiliary.eq(0), self.sticky.eq(0)]
        # op=0 CLZ, op=1 LZA, op=2 shift-jam, op=3 multiply, op=4 CSA,
        # op=5 rounded shift-right (``b[2:0]`` selects RNE/RTZ/RDN/RUP/RMM).
        # The extra operation reuses the existing ports so legacy callers keep
        # the same interface while Fudian's RoundingUnit gets a concrete
        # bit-level helper at this aggregate boundary.
        with amaranth_if(m, self.operation == 0):
            # PriorityEncoder(reverse) gives width-1 for zero. / 反向优先编码器对零返回 width-1。
            expr = width - 1
            for index in range(width):
                expr = Mux(self.a[index], width - 1 - index, expr)
            m.d.comb += [self.auxiliary.eq(expr), self.result.eq(expr)]
        with amaranth_elif(m, self.operation == 1):
            # Keep the recurrence in one-bit Values.  Using Python ``~`` on
            # the previous integer (the old implementation) created a
            # negative constant and produced width-dependent RTL.
            lza_expr = 0
            previous_k: Any = Const(0, 1)
            for index in range(width):
                p = amaranth_value(self.a[index]) ^ amaranth_value(self.b[index])
                k = (~amaranth_value(self.a[index])) & (~amaranth_value(self.b[index]))
                bit = Const(0, 1) if index == 0 else p ^ (~previous_k)
                lza_expr = lza_expr | (bit << index)
                previous_k = k
            m.d.comb += [self.auxiliary.eq(lza_expr), self.result.eq(lza_expr)]
        with amaranth_elif(m, self.operation == 2):
            exceed = self.shift > width
            # ``(1 << shamt)-1`` is formed at width+1 so a shift equal to the
            # operand width still retains all discarded bits after slicing.
            shift_mask = ((Const(1, width + 1) << self.shift) - 1)[:width]
            sticky_expr = (self.a & shift_mask).any() | exceed & (self.a != 0)
            m.d.comb += [self.result.eq(Mux(exceed, 0, self.a >> self.shift)), self.sticky.eq(sticky_expr)]
        with amaranth_elif(m, self.operation == 3):
            m.d.comb += self.result.eq(self.a * self.b)
        with amaranth_elif(m, self.operation == 4):
            # CSA3_2 is the common Fudian carry-save primitive.  Carry bits
            # are intentionally not shifted, matching CSA.scala's Vec output.
            sum_bits = self.a ^ self.b ^ self.shift[:width]
            carry_bits = (self.a & self.b) | (self.a & self.shift[:width]) | (self.b & self.shift[:width])
            m.d.comb += [self.result.eq(sum_bits), self.auxiliary.eq(carry_bits)]
        with amaranth_elif(m, self.operation == 5):
            shift_mask = ((Const(1, width + 1) << self.shift) - 1)[:width]
            discarded = amaranth_value(self.a & shift_mask)
            base = amaranth_value(self.a >> self.shift)
            shift_minus_one = amaranth_value((self.shift - Const(1, len(self.shift))).as_unsigned())
            guard = amaranth_value(Mux(self.shift == 0, 0,
                                       (self.a >> shift_minus_one)[:1]))
            lower_mask = amaranth_value(amaranth_value(shift_mask) >> Const(1, 1))
            lower_discarded = amaranth_value(discarded & lower_mask)
            sticky_round = lower_discarded.any()
            inexact_round = discarded.any() | ((self.shift > width) & (self.a != 0))
            round_up = Mux(self.b[:3] == 0, guard & (sticky_round | base[0]),
                           Mux(self.b[:3] == 3, inexact_round,
                               Mux(self.b[:3] == 4, guard, Const(0, 1))))
            rounded = amaranth_value(base + round_up)
            m.d.comb += [self.result.eq(rounded), self.auxiliary.eq(rounded[:width]),
                         self.sticky.eq(inexact_round)]
        return m


# =============================================================================
# Public Adapter
# =============================================================================
# Export deterministic arithmetic helper Verilog. / 导出确定性的算术辅助器 Verilog。
def build_verilog(configuration: ArithmeticConfig | Mapping[str, Any] | None, injected_dependencies: Mapping[str, Any]) -> str:
    """Build arithmetic aggregate RTL. / 构建算术聚合 RTL。"""
    del injected_dependencies
    if configuration is None:
        cfg, name = ArithmeticConfig(), "UHSCFudianArithmetic"
    elif isinstance(configuration, ArithmeticConfig):
        cfg, name = configuration, "UHSCFudianArithmetic"
    elif isinstance(configuration, Mapping):
        cfg = ArithmeticConfig(width=int(configuration.get("width", 64)))
        name = str(configuration.get("module", configuration.get("name", "UHSCFudianArithmetic")))
    else:
        raise TypeError("configuration must be ArithmeticConfig, mapping, or None")
    top = FudianArithmetic(cfg)
    ports = [top.clock, top.reset, top.a, top.b, top.shift, top.operation, top.result, top.auxiliary, top.sticky]
    return verilog.convert(top, name=name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print deterministic direct export. / 打印确定性的 direct 导出。
def main() -> None:
    """Emit default arithmetic Verilog. / 输出默认算术 Verilog。"""
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
