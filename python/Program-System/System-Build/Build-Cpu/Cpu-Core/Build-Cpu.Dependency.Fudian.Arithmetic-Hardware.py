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

from amaranth import ClockDomain, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog
from amaranth.hdl.ast import Value


# =============================================================================
# Module Contract
# =============================================================================
# The family covers the five pinned utility sources. / 此 family 覆盖锁定的五个工具源文件。
SOURCE_SCALA_ROOT = "fudian/src/main/scala/fudian/utils"
SOURCE_SCALA_PATHS = (
    "fudian/src/main/scala/fudian/utils/CLZ.scala",
    "fudian/src/main/scala/fudian/utils/CSA.scala",
    "fudian/src/main/scala/fudian/utils/LZA.scala",
    "fudian/src/main/scala/fudian/utils/Multiplier.scala",
    "fudian/src/main/scala/fudian/utils/ShiftRightJam.scala",
)
SOURCE_SCALA_FILE_COUNT = len(SOURCE_SCALA_PATHS)

__all__ = [
    "SOURCE_SCALA_ROOT", "SOURCE_SCALA_PATHS", "SOURCE_SCALA_FILE_COUNT",
    "ArithmeticConfig", "FudianArithmetic", "clz", "lza", "shift_right_jam",
    "csa", "multiply_unsigned", "build_verilog", "main",
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
        # op=0 CLZ, op=1 LZA, op=2 shift-jam, op=3 multiply. / 操作码定义。
        with amaranth_if(m, self.operation == 0):
            # PriorityEncoder(reverse) gives width-1 for zero. / 反向优先编码器对零返回 width-1。
            expr = width - 1
            for index in range(width):
                expr = Mux(self.a[index], width - 1 - index, expr)
            m.d.comb += self.auxiliary.eq(expr)
        with amaranth_elif(m, self.operation == 1):
            lza_expr = 0
            previous_k = 0
            for index in range(width):
                p = amaranth_value(self.a[index]) ^ amaranth_value(self.b[index])
                k = (~amaranth_value(self.a[index])) & (~amaranth_value(self.b[index]))
                bit = 0 if index == 0 else p ^ (~previous_k)
                lza_expr = lza_expr | (bit << index)
                previous_k = k
            m.d.comb += self.auxiliary.eq(lza_expr)
        with amaranth_elif(m, self.operation == 2):
            exceed = self.shift > width
            discarded = self.a & ((1 << width) - 1)
            m.d.comb += [self.result.eq(Mux(exceed, 0, self.a >> self.shift)), self.sticky.eq(Mux(exceed, self.a != 0, (discarded & ((1 << width) - 1)) != 0))]
        with amaranth_elif(m, self.operation == 3):
            m.d.comb += self.result.eq(self.a * self.b)
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
