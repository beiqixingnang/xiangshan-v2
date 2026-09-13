"""Unsigned saturate counter bundle of XiangShan BPU (state query + update + reset methods).
香山 BPU 无符号饱和计数器（状态查询、更新与复位方法）的 amaranth 重写。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amaranth import Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# ============================================================================
# Module Contract
# ============================================================================
# Public symbols / 公开符号:
#   SaturateCounterValue - constant states (Saturate/Weak Positive/Negative) / 常量状态
#   SaturateCounter      - counter value wrapper with state/update methods / 计数器包装器
#   SaturateCounterReg   - registered counter module (self-update on taken) / 寄存器计数器
#   build_verilog / main
# Contract: methods return amaranth expressions; reg module updates on m.d.sync.
__all__ = [
    "SaturateCounterValue",
    "SaturateCounterConfig",
    "SaturateCounter",
    "SaturateCounterReg",
    "build_verilog",
    "main",
]


# ============================================================================
# Configuration
# ============================================================================
@dataclass(frozen=True)
class SaturateCounterConfig:
    # Counter width config / 计数器宽度配置
    width: int = 2


class SaturateCounterValue:
    # Constant states for a given width / 给定宽度的常量状态
    @staticmethod
    def saturate_positive(width: int) -> int:
        # All-ones / 全一
        return (1 << width) - 1

    # Saturate negative constant / 负饱和常量
    @staticmethod
    def saturate_negative(width: int) -> int:
        return 0

    # Weak positive constant / 弱正常量
    @staticmethod
    def weak_positive(width: int) -> int:
        assert width >= 2
        return 1 << (width - 1)

    # Weak negative constant / 弱负常量
    @staticmethod
    def weak_negative(width: int) -> int:
        assert width >= 2
        return (1 << (width - 1)) - 1


# ============================================================================
# Implementation
# ============================================================================
class SaturateCounter:
    # Counter value wrapper / 计数器值包装器
    def __init__(self, width: int, value=None, name: str = "cnt") -> None:
        assert width >= 2
        self.width = width
        self.value: Any = value if value is not None else Signal(width, name=name)

    # Direction queries / 方向查询
    def is_positive(self):
        return self.value[self.width - 1]

    # Negative query / 负向查询
    def is_negative(self):
        return ~self.value[self.width - 1]

    # Saturated positive (all ones) / 正饱和（全一）
    def is_saturate_positive(self):
        return self.value.all()

    # Saturated negative (zero) / 负饱和（全零）
    def is_saturate_negative(self):
        return ~self.value.any()

    # Saturated on either side / 任意侧饱和
    def is_saturate(self):
        return self.is_saturate_positive() | self.is_saturate_negative()

    # Should hold on update in given direction / 给定方向更新时是否保持
    def should_hold(self, increase):
        return (self.is_saturate_positive() & increase) | (self.is_saturate_negative() & ~increase)

    # Weak positive (exactly 1<<(w-1)) / 弱正（恰为 1<<(w-1)）
    def is_weak_positive(self):
        return self.is_positive() & ~self.value[: self.width - 1].any()

    # Weak negative (exactly (1<<(w-1))-1) / 弱负
    def is_weak_negative(self):
        return self.is_negative() & self.value[: self.width - 1].all()

    # Weak on either side / 任意侧弱态
    def is_weak(self):
        return self.is_weak_positive() | self.is_weak_negative()

    # Mid state / 中间态
    def is_mid(self):
        assert self.width >= 3
        return ~self.is_saturate() & ~self.is_weak()

    # Next value on +/-1 update / 加减一更新的下一值
    def get_updated_value(self, increase, en=None):
        enable = en if en is not None else Const(1)
        return Mux(~enable | self.should_hold(increase), self.value,
                   Mux(increase, self.value + 1, self.value - 1))

    # Next value on +step update with saturation / 加步长并饱和的下一值
    def get_increased_value(self, step, en=None):
        enable = en if en is not None else Const(1)
        sat = SaturateCounterValue.saturate_positive(self.width)
        return Mux(~enable, self.value,
                   Mux(self.value + step >= sat, sat, self.value + step))

    # Next value on -step update with saturation / 减步长并饱和的下一值
    def get_decreased_value(self, step, en=None):
        enable = en if en is not None else Const(1)
        return Mux(~enable, self.value,
                   Mux(self.value <= step, 0, self.value - step))


class SaturateCounterReg(Elaboratable):
    # Registered counter with self-update / 带自更新的寄存器计数器
    def __init__(self, config: SaturateCounterConfig = SaturateCounterConfig()) -> None:
        super().__init__()
        w = config.width
        self.en = Signal()
        self.increase = Signal()
        self.value = Signal(w, reset=SaturateCounterValue.weak_positive(w))
        self.is_positive = Signal()
        self.is_saturate = Signal()

    # Elaborate the self-update logic / 展开自更新逻辑
    def elaborate(self, platform) -> Module:
        m = Module()
        cnt = SaturateCounter(len(self.value), self.value)
        m.d.sync += self.value.eq(cnt.get_updated_value(self.increase, self.en))
        m.d.comb += [
            self.is_positive.eq(cnt.is_positive()),
            self.is_saturate.eq(cnt.is_saturate()),
        ]
        return m


# ============================================================================
# Public Adapter
# ============================================================================
# Build Verilog for the registered counter / 为寄存器计数器生成 Verilog
def build_verilog(config: SaturateCounterConfig = SaturateCounterConfig()) -> str:
    top = SaturateCounterReg(config)
    ports = [top.en, top.increase, top.value, top.is_positive, top.is_saturate]
    return verilog.convert(top, ports=ports)


# ============================================================================
# Direct Entry
# ============================================================================
# Direct entry: print generated Verilog / 直接入口：打印生成的 Verilog
def main() -> None:
    print(build_verilog())


if __name__ == "__main__":
    main()
