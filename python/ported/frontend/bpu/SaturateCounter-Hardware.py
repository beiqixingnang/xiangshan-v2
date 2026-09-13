"""V2 unsigned saturating counter closure. / V2 无符号饱和计数器闭包。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amaranth import Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# V2 has no standalone SaturateCounter class. BPUUtils.satUpdate is inlined
# in BPU, Tage, Bim, FauFTB, and SC. This leaf exposes that exact recurrence,
# plus a small registered harness used by direct and parent-closure tests.
# V2 没有独立 SaturateCounter 类；BPUUtils.satUpdate 内联于多个消费者。
__all__ = [
    "SaturateCounterConfig",
    "SaturateCounterValue",
    "SaturateCounter",
    "SaturateCounterReg",
    "sat_update",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class SaturateCounterConfig:
    """Set counter width and reset state. / 设置计数器宽度与复位状态。"""

    width: int = 2
    reset_value: int = 0

    # Validate unsigned-counter parameters. / 校验无符号计数器参数。
    def __post_init__(self) -> None:
        if self.width < 1:
            raise ValueError("counter width must be positive")
        limit = 1 << self.width
        if self.reset_value < 0 or self.reset_value >= limit:
            raise ValueError("reset value is outside the counter domain")


class SaturateCounterValue:
    """Named V2 counter boundary constants. / V2 计数器边界常量。"""

    # Return the positive saturation value. / 返回正饱和值。
    @staticmethod
    # saturate_positive responsibility. / saturate_positive 函数职责。
    def saturate_positive(width: int) -> int:
        return (1 << width) - 1

    # Return the negative saturation value. / 返回负饱和值。
    @staticmethod
    # saturate_negative responsibility. / saturate_negative 函数职责。
    def saturate_negative(width: int) -> int:
        return 0

    # Return the weak-positive state used by legacy two-bit users. / 返回弱正状态。
    @staticmethod
    # weak_positive responsibility. / weak_positive 函数职责。
    def weak_positive(width: int) -> int:
        if width < 2:
            raise ValueError("weak states require at least two bits")
        return 1 << (width - 1)

    # Return the weak-negative state used by legacy two-bit users. / 返回弱负状态。
    @staticmethod
    # weak_negative responsibility. / weak_negative 函数职责。
    def weak_negative(width: int) -> int:
        if width < 2:
            raise ValueError("weak states require at least two bits")
        return (1 << (width - 1)) - 1


# =============================================================================
# Implementation
# =============================================================================
# Evaluate BPUUtils.satUpdate in the integer reference domain. / 整数域计算 V2 更新。
def sat_update(old: int, width: int, taken: bool) -> int:
    """Apply V2's one-step unsigned saturating update. / 执行 V2 无符号单步饱和更新。"""

    if width < 1:
        raise ValueError("counter width must be positive")
    limit = 1 << width
    old &= limit - 1
    if taken:
        return min(old + 1, limit - 1)
    return max(old - 1, 0)


class SaturateCounter:
    """Expression wrapper matching BPUUtils.satUpdate. / 匹配 BPUUtils 的表达式包装器。"""

    # Construct a counter expression wrapper. / 创建计数器表达式包装器。
    def __init__(self, width: int, value: Any | None = None,
                 name: str = "cnt") -> None:
        if width < 1:
            raise ValueError("counter width must be positive")
        self.width = width
        self.value = value if value is not None else Signal(width, name=name)

    # Report whether the counter predicts taken. / 报告计数器是否预测 taken。
    def is_positive(self) -> Any:
        return self.value[-1]

    # Report whether the counter predicts not-taken. / 报告计数器是否预测 not-taken。
    def is_negative(self) -> Any:
        return ~self.value[-1]

    # Report positive saturation. / 报告正饱和。
    def is_saturate_positive(self) -> Any:
        return self.value == Const((1 << self.width) - 1, self.width)

    # Report negative saturation. / 报告负饱和。
    def is_saturate_negative(self) -> Any:
        return self.value == Const(0, self.width)

    # Report either saturation boundary. / 报告任一饱和边界。
    def is_saturate(self) -> Any:
        return self.is_saturate_positive() | self.is_saturate_negative()

    # Report whether an update must hold at a boundary. / 报告边界是否保持。
    def should_hold(self, taken: Any) -> Any:
        return (self.is_saturate_positive() & taken) | (self.is_saturate_negative() & ~taken)

    # Report the weak-positive state. / 报告弱正状态。
    def is_weak_positive(self) -> Any:
        return self.value == Const(1 << (self.width - 1), self.width)

    # Report the weak-negative state. / 报告弱负状态。
    def is_weak_negative(self) -> Any:
        if self.width < 2:
            return Const(0)
        return self.value == Const((1 << (self.width - 1)) - 1, self.width)

    # Report either weak state. / 报告任一弱状态。
    def is_weak(self) -> Any:
        return self.is_weak_positive() | self.is_weak_negative()

    # Report a non-boundary, non-weak state. / 报告中间状态。
    def is_mid(self) -> Any:
        if self.width < 3:
            raise ValueError("mid state requires at least three bits")
        return ~self.is_saturate() & ~self.is_weak()

    # Build the exact one-step V2 update expression. / 构建 V2 单步更新表达式。
    def get_updated_value(self, taken: Any, en: Any | None = None) -> Any:
        enable = Const(1) if en is None else en
        maximum = Const((1 << self.width) - 1, self.width)
        incremented = (self.value + Const(1, self.width))[: self.width]
        decremented = (self.value - Const(1, self.width))[: self.width]
        next_value = Mux(taken, incremented, decremented)
        return Mux(~enable | self.should_hold(taken), self.value, next_value)

    # Build a multi-step positive saturated update for compatibility. / 构建多步正向饱和更新。
    def get_increased_value(self, step: Any, en: Any | None = None) -> Any:
        enable = Const(1) if en is None else en
        maximum = Const((1 << self.width) - 1, self.width)
        candidate = self.value + step
        return Mux(~enable, self.value, Mux(candidate >= maximum, maximum, candidate[: self.width]))

    # Build a multi-step negative saturated update for compatibility. / 构建多步负向饱和更新。
    def get_decreased_value(self, step: Any, en: Any | None = None) -> Any:
        enable = Const(1) if en is None else en
        candidate = self.value - step
        return Mux(~enable, self.value, Mux(self.value <= step, Const(0, self.width), candidate[: self.width]))


class SaturateCounterReg(Elaboratable):
    """Registered harness for the distributed V2 recurrence. / 分布式 V2 更新的寄存器外壳。"""

    # Declare the registered counter ports. / 声明寄存器计数器端口。
    def __init__(self, configuration: SaturateCounterConfig | None = None) -> None:
        self.configuration = configuration or SaturateCounterConfig()
        cfg = self.configuration
        self.en = Signal(name="en")
        self.increase = Signal(name="taken")
        self.value = Signal(cfg.width, reset=cfg.reset_value, name="value")
        self.next_value = Signal(cfg.width, name="next_value")
        self.is_positive = Signal(name="is_positive")
        self.is_saturate = Signal(name="is_saturate")

    # Elaborate one synchronous satUpdate recurrence. / 展开一个同步 satUpdate 递推。
    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        counter = SaturateCounter(self.configuration.width, self.value)
        module.d.comb += [
            self.next_value.eq(counter.get_updated_value(self.increase, self.en)),
            self.is_positive.eq(counter.is_positive()),
            self.is_saturate.eq(counter.is_saturate()),
        ]
        module.d.sync += self.value.eq(self.next_value)
        return module


# =============================================================================
# Public Adapter
# =============================================================================
# Emit deterministic RTL for the registered counter. / 输出确定性的寄存器计数器 RTL。
def build_verilog(configuration: SaturateCounterConfig | None = None,
                  injected_dependencies: dict[str, Any] | None = None) -> str:
    del injected_dependencies
    top = SaturateCounterReg(configuration)
    return verilog.convert(
        top,
        name="SaturateCounter",
        ports=[top.en, top.increase, top.value, top.next_value,
               top.is_positive, top.is_saturate],
        emit_src=False,
    )


# =============================================================================
# Direct Entry
# =============================================================================
# Print generated RTL for a default counter. / 打印默认计数器 RTL。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
