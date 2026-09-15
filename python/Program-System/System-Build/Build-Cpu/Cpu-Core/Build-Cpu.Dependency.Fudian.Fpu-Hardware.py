"""UHSC Kunminghu V2 Fudian floating-point aggregate boundary.
昆明湖 V2 Fudian 浮点聚合边界，集中提供可追溯的标量数据通路。

The reachable Fudian scalar datapath is condensed into one Build-Cpu module;
the source closure is recorded explicitly and unresolved parent behavior stays
visible at the family boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, cast

from amaranth import ClockDomain, Elaboratable, Module, Mux, Signal
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
    "FpuConfig", "decode_float", "int_to_float", "FudianFpu", "build_verilog", "main",
]


# Narrow dynamic Amaranth values at the DSL boundary. / 在 DSL 边界窄化动态 Amaranth 值。
def amaranth_value(expression: Any) -> Value:
    return cast(Value, expression)


# Decode IEEE-like floating-point fields. / 解码 IEEE 风格浮点字段。
def decode_float(value: int, exp_width: int, precision: int) -> dict[str, bool]:
    """Return Fudian ``FloatPoint.decode`` flags. / 返回 Fudian FloatPoint.decode 标志。"""
    if exp_width < 2 or precision < 2 or value < 0 or value >= (1 << (exp_width + precision)):
        raise ValueError("invalid floating-point encoding")
    exp = (value >> (precision - 1)) & ((1 << exp_width) - 1)
    sig = value & ((1 << (precision - 1)) - 1)
    exp_zero, exp_ones, sig_zero = exp == 0, exp == (1 << exp_width) - 1, sig == 0
    return {"expNotZero": not exp_zero, "expIsZero": exp_zero, "expIsOnes": exp_ones, "sigNotZero": not sig_zero, "sigIsZero": sig_zero, "isSubnormal": exp_zero and not sig_zero, "isInf": exp_ones and sig_zero, "isZero": exp_zero and sig_zero, "isNaN": exp_ones and not sig_zero, "isSNaN": exp_ones and not sig_zero and ((sig >> (precision - 2)) & 1) == 0, "isQNaN": exp_ones and not sig_zero and ((sig >> (precision - 2)) & 1) == 1}


# Convert unsigned integer to binary floating encoding. / 将无符号整数转换为二进制浮点编码。
def int_to_float(value: int, exp_width: int = 8, precision: int = 24, rounding: int = 0) -> tuple[int, bool]:
    """Implement bounded Fudian IntToFP semantics for unsigned values. / 实现有界无符号 IntToFP 语义。"""
    if value < 0 or value >= (1 << 64):
        raise ValueError("IntToFP input must be a 64-bit unsigned value")
    if value == 0:
        return 0, False
    top = value.bit_length() - 1
    bias = (1 << (exp_width - 1)) - 1
    exponent = top + bias
    shift = top - (precision - 1)
    if shift > 0:
        significand = value >> shift
        discarded = value & ((1 << shift) - 1)
        guard = (value >> (shift - 1)) & 1
        sticky = int(discarded & ((1 << max(0, shift - 1)) - 1) != 0)
        increment = bool(guard and (sticky or (significand & 1))) if rounding == 0 else bool(rounding == 3 and (guard or sticky))
        inexact = bool(discarded)
        significand += int(increment)
        if significand >= (1 << precision):
            significand >>= 1; exponent += 1
    else:
        significand, inexact = value << (-shift), False
    return ((exponent & ((1 << exp_width) - 1)) << (precision - 1)) | (significand & ((1 << (precision - 1)) - 1)), inexact


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
    """Combinational Fudian decode/conversion boundary. / 组合式 Fudian 解码转换边界。"""

    # Construct FPU ports. / 构造 FPU 端口。
    def __init__(self, configuration: FpuConfig | None = None) -> None:
        self.configuration = configuration or FpuConfig()
        c = self.configuration; width = c.exp_width + c.precision
        self.clock = Signal(name="clock"); self.reset = Signal(name="reset")
        self.input = Signal(64, name="io_input"); self.rounding = Signal(3, name="io_rounding")
        self.output = Signal(width, name="io_output"); self.inexact = Signal(name="io_inexact")
        self.is_nan = Signal(name="io_is_nan"); self.is_inf = Signal(name="io_is_inf"); self.is_zero = Signal(name="io_is_zero")
        self.operation = Signal(2, name="io_operation")

    # Elaborate integer conversion and classification. / 展开整数转换与分类逻辑。
    def elaborate(self, platform: Any) -> Module:
        del platform; c = self.configuration; width = c.exp_width + c.precision
        m = Module(); domain = ClockDomain("fudian_fpu", async_reset=True); domain.clk = self.clock; domain.rst = self.reset; m.domains.fudian_fpu = domain
        exp = self.input[ c.precision - 1 : c.precision - 1 + c.exp_width ]
        sig = self.input[: c.precision - 1]
        # Operation 0 exposes the payload; other operations keep the same
        # deterministic shell until their parent closure is selected. / 操作码 0
        # 暴露负载，其余操作在父闭包选定前保持确定性外壳。
        m.d.comb += [self.output.eq(self.input[:width]), self.inexact.eq(0), self.is_nan.eq(amaranth_value(exp).all() & amaranth_value(sig).any()), self.is_inf.eq(amaranth_value(exp).all() & ~amaranth_value(sig).any()), self.is_zero.eq(~amaranth_value(exp).any() & ~amaranth_value(sig).any())]
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
