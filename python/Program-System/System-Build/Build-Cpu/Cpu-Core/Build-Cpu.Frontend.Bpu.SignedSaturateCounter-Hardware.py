"""V2 signed saturating counter closure. / V2 有符号饱和计数器闭包。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amaranth import Const, Elaboratable, Module, Mux, Signal, signed
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# V2's signedSatUpdate is a BPUUtils helper consumed by SC.scala; there is no
# standalone source class. The recurrence below preserves signed endpoints and
# is exposed through a registered harness for closure testing.
# V2 的 signedSatUpdate 是 BPUUtils 辅助逻辑，由 SC.scala 消费，并非独立类。
__all__ = [
    "SignedSaturateCounterConfig",
    "SignedSaturateCounterValue",
    "SignedSaturateCounter",
    "SignedSaturateCounterReg",
    "signed_sat_update",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class SignedSaturateCounterConfig:
    """Set signed width and reset value. / 设置有符号宽度与复位值。"""

    width: int = 6
    reset_value: int = 0

    # Validate signed-counter parameters. / 校验有符号计数器参数。
    def __post_init__(self) -> None:
        if self.width < 2:
            raise ValueError("signed counter width must be at least two")
        lower = -(1 << (self.width - 1))
        upper = (1 << (self.width - 1)) - 1
        if self.reset_value < lower or self.reset_value > upper:
            raise ValueError("reset value is outside the signed domain")


class SignedSaturateCounterValue:
    """Named signed counter boundary constants. / 有符号计数器边界常量。"""

    # Return the positive saturation value. / 返回正饱和值。
    @staticmethod
    # saturate_positive responsibility. / saturate_positive 函数职责。
    def saturate_positive(width: int) -> int:
        return (1 << (width - 1)) - 1

    # Return the negative saturation value. / 返回负饱和值。
    @staticmethod
    # saturate_negative responsibility. / saturate_negative 函数职责。
    def saturate_negative(width: int) -> int:
        return -(1 << (width - 1))

    # Return the weak-positive state. / 返回弱正状态。
    @staticmethod
    # weak_positive responsibility. / weak_positive 函数职责。
    def weak_positive(width: int) -> int:
        if width < 2:
            raise ValueError("weak states require at least two bits")
        return 1

    # Return the weak-negative state. / 返回弱负状态。
    @staticmethod
    # weak_negative responsibility. / weak_negative 函数职责。
    def weak_negative(width: int) -> int:
        if width < 2:
            raise ValueError("weak states require at least two bits")
        return -1


# =============================================================================
# Implementation
# =============================================================================
# Evaluate BPUUtils.signedSatUpdate in the integer reference domain. / 整数域计算有符号更新。
def signed_sat_update(old: int, width: int, taken: bool) -> int:
    """Apply V2's one-step signed saturating update. / 执行 V2 有符号单步饱和更新。"""

    if width < 2:
        raise ValueError("signed counter width must be at least two")
    lower = -(1 << (width - 1))
    upper = (1 << (width - 1)) - 1
    modulus = 1 << width
    raw = old & (modulus - 1)
    value = raw - modulus if raw & (1 << (width - 1)) else raw
    if taken:
        return min(value + 1, upper)
    return max(value - 1, lower)


class SignedSaturateCounter:
    """Expression wrapper for signedSatUpdate. / signedSatUpdate 表达式包装器。"""

    # Construct a signed counter expression wrapper. / 创建有符号计数器表达式包装器。
    def __init__(self, width: int, value: Any | None = None,
                 name: str = "cnt") -> None:
        if width < 2:
            raise ValueError("signed counter width must be at least two")
        self.width = width
        self.value = value if value is not None else Signal(signed(width), name=name)

    # Report a non-negative value. / 报告非负值。
    def is_positive(self) -> Any:
        return self.value >= Const(0, signed(self.width))

    # Report a negative value. / 报告负值。
    def is_negative(self) -> Any:
        return self.value < Const(0, signed(self.width))

    # Report positive saturation. / 报告正饱和。
    def is_saturate_positive(self) -> Any:
        return self.value == Const((1 << (self.width - 1)) - 1, signed(self.width))

    # Report negative saturation. / 报告负饱和。
    def is_saturate_negative(self) -> Any:
        return self.value == Const(-(1 << (self.width - 1)), signed(self.width))

    # Report either saturation boundary. / 报告任一饱和边界。
    def is_saturate(self) -> Any:
        return self.is_saturate_positive() | self.is_saturate_negative()

    # Report whether an update must hold at a boundary. / 报告边界是否保持。
    def should_hold(self, taken: Any) -> Any:
        return (self.is_saturate_positive() & taken) | (self.is_saturate_negative() & ~taken)

    # Report the weak-positive state. / 报告弱正状态。
    def is_weak_positive(self) -> Any:
        return self.value == Const(1, signed(self.width))

    # Report the weak-negative state. / 报告弱负状态。
    def is_weak_negative(self) -> Any:
        return self.value == Const(-1, signed(self.width))

    # Report either weak state. / 报告任一弱状态。
    def is_weak(self) -> Any:
        return self.is_weak_positive() | self.is_weak_negative()

    # Report a non-boundary, non-weak state. / 报告中间状态。
    def is_mid(self) -> Any:
        if self.width < 3:
            raise ValueError("mid state requires at least three bits")
        return ~self.is_saturate() & ~self.is_weak()

    # Build the exact one-step signed update expression. / 构建有符号单步更新表达式。
    def get_updated_value(self, taken: Any, en: Any | None = None) -> Any:
        enable = Const(1) if en is None else en
        lower = Const(-(1 << (self.width - 1)), signed(self.width))
        upper = Const((1 << (self.width - 1)) - 1, signed(self.width))
        incremented = (self.value + Const(1, signed(self.width)))[: self.width]
        decremented = (self.value - Const(1, signed(self.width)))[: self.width]
        next_value = Mux(taken, incremented, decremented)
        return Mux(~enable | self.should_hold(taken), self.value, next_value)

    # Build a multi-step positive saturated update. / 构建多步正向饱和更新。
    def get_increased_value(self, step: Any, en: Any | None = None) -> Any:
        enable = Const(1) if en is None else en
        upper = Const((1 << (self.width - 1)) - 1, signed(self.width))
        candidate = self.value + step
        return Mux(~enable, self.value, Mux(candidate >= upper, upper, candidate[: self.width]))

    # Build a multi-step negative saturated update. / 构建多步负向饱和更新。
    def get_decreased_value(self, step: Any, en: Any | None = None) -> Any:
        enable = Const(1) if en is None else en
        lower = Const(-(1 << (self.width - 1)), signed(self.width))
        candidate = self.value - step
        return Mux(~enable, self.value, Mux(candidate <= lower, lower, candidate[: self.width]))


class SignedSaturateCounterReg(Elaboratable):
    """Registered harness for signedSatUpdate. / signedSatUpdate 的寄存器外壳。"""

    # Declare the signed registered counter ports. / 声明有符号寄存器端口。
    def __init__(self, configuration: SignedSaturateCounterConfig | None = None) -> None:
        self.configuration = configuration or SignedSaturateCounterConfig()
        cfg = self.configuration
        self.en = Signal(name="en")
        self.positive = Signal(name="taken")
        self.value = Signal(signed(cfg.width), reset=cfg.reset_value, name="value")
        self.next_value = Signal(signed(cfg.width), name="next_value")
        self.is_positive = Signal(name="is_positive")
        self.is_saturate = Signal(name="is_saturate")

    # Elaborate one synchronous signed recurrence. / 展开一个同步有符号递推。
    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        counter = SignedSaturateCounter(self.configuration.width, self.value)
        module.d.comb += [
            self.next_value.eq(counter.get_updated_value(self.positive, self.en)),
            self.is_positive.eq(counter.is_positive()),
            self.is_saturate.eq(counter.is_saturate()),
        ]
        module.d.sync += self.value.eq(self.next_value)
        return module


# =============================================================================
# Public Adapter
# =============================================================================
# Emit deterministic RTL for the signed registered counter. / 输出有符号计数器 RTL。
def build_verilog(configuration: SignedSaturateCounterConfig | None = None,
                  injected_dependencies: dict[str, Any] | None = None) -> str:
    del injected_dependencies
    top = SignedSaturateCounterReg(configuration)
    return verilog.convert(
        top,
        name="SignedSaturateCounter",
        ports=[top.en, top.positive, top.value, top.next_value,
               top.is_positive, top.is_saturate],
        emit_src=False,
    )


# =============================================================================
# Direct Entry
# =============================================================================
# Print generated RTL for a default signed counter. / 打印默认有符号计数器 RTL。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
