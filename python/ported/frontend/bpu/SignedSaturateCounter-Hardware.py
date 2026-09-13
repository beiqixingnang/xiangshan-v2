"""Signed saturate counter bundle of XiangShan BPU (state query + update + reset methods).
香山 BPU 有符号饱和计数器（状态查询、更新与复位方法）的 amaranth 重写。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amaranth import Const, Elaboratable, Module, Mux, Signal, signed
from amaranth.back import verilog


# ============================================================================
# Module Contract
# ============================================================================
# Public symbols / 公开符号:
#   SignedSaturateCounterValue - constant states / 常量状态
#   SignedSaturateCounter      - signed counter value wrapper / 有符号计数器包装器
#   SignedSaturateCounterReg   - registered counter module / 寄存器计数器模块
#   build_verilog / main
# Contract: value is an amaranth signed Signal; updates saturate at both ends.
__all__ = [
    "SignedSaturateCounterValue",
    "SignedSaturateCounterConfig",
    "SignedSaturateCounter",
    "SignedSaturateCounterReg",
    "build_verilog",
    "main",
]


# ============================================================================
# Configuration
# ============================================================================
@dataclass(frozen=True)
class SignedSaturateCounterConfig:
    # Counter width config / 计数器宽度配置
    width: int = 6


class SignedSaturateCounterValue:
    # Constant states for a given width / 给定宽度的常量状态
    @staticmethod
    def saturate_positive(width: int) -> int:
        return (1 << (width - 1)) - 1

    # Saturate negative constant / 负饱和常量
    @staticmethod
    def saturate_negative(width: int) -> int:
        return -(1 << (width - 1))

    # Weak positive constant / 弱正常量
    @staticmethod
    def weak_positive(width: int) -> int:
        assert width >= 2
        return 1

    # Weak negative constant / 弱负常量
    @staticmethod
    def weak_negative(width: int) -> int:
        assert width >= 2
        return -1


# ============================================================================
# Implementation
# ============================================================================
class SignedSaturateCounter:
    # Signed counter value wrapper / 有符号计数器值包装器
    def __init__(self, width: int, value=None, name: str = "cnt") -> None:
        assert width >= 2
        self.width = width
        self.value: Any = value if value is not None else Signal(signed(width), name=name)

    # Direction queries / 方向查询
    def is_positive(self):
        return self.value >= 0

    # Negative query / 负向查询
    def is_negative(self):
        return self.value < 0

    # Saturated positive / 正饱和
    def is_saturate_positive(self):
        return self.value == SignedSaturateCounterValue.saturate_positive(self.width)

    # Saturated negative / 负饱和
    def is_saturate_negative(self):
        return self.value == SignedSaturateCounterValue.saturate_negative(self.width)

    # Saturated on either side / 任意侧饱和
    def is_saturate(self):
        return self.is_saturate_positive() | self.is_saturate_negative()

    # Should hold on update in given direction / 给定方向更新时是否保持
    def should_hold(self, positive):
        return (self.is_saturate_positive() & positive) | (self.is_saturate_negative() & ~positive)

    # Weak positive (== 0) / 弱正（等于 0）
    def is_weak_positive(self):
        return self.value == 0

    # Weak negative (== -1) / 弱负（等于 -1）
    def is_weak_negative(self):
        return self.value == -1

    # Weak on either side / 任意侧弱态
    def is_weak(self):
        return self.is_weak_positive() | self.is_weak_negative()

    # Mid state / 中间态
    def is_mid(self):
        assert self.width >= 3
        return ~self.is_saturate() & ~self.is_weak()

    # Next value on +/-1 update / 加减一更新的下一值
    def get_updated_value(self, positive, en=None):
        enable = en if en is not None else Const(1)
        return Mux(~enable | self.should_hold(positive), self.value,
                   Mux(positive, self.value + 1, self.value - 1))

    # Next value on +step update with saturation / 加步长并饱和的下一值
    def get_increased_value(self, step, en=None):
        enable = en if en is not None else Const(1)
        sat = SignedSaturateCounterValue.saturate_positive(self.width)
        return Mux(~enable, self.value,
                   Mux(self.value + step >= sat, sat, self.value + step))

    # Next value on -step update with saturation / 减步长并饱和的下一值
    def get_decreased_value(self, step, en=None):
        enable = en if en is not None else Const(1)
        sat = SignedSaturateCounterValue.saturate_negative(self.width)
        return Mux(~enable, self.value,
                   Mux(self.value - step <= sat, sat, self.value - step))


class SignedSaturateCounterReg(Elaboratable):
    # Registered signed counter with self-update / 带自更新的寄存器有符号计数器
    def __init__(self, config: SignedSaturateCounterConfig = SignedSaturateCounterConfig()) -> None:
        super().__init__()
        w = config.width
        self.en = Signal()
        self.positive = Signal()
        self.value = Signal(signed(w), reset=0)
        self.is_positive = Signal()
        self.is_saturate = Signal()

    # Elaborate the self-update logic / 展开自更新逻辑
    def elaborate(self, platform) -> Module:
        m = Module()
        cnt = SignedSaturateCounter(len(self.value), self.value)
        m.d.sync += self.value.eq(cnt.get_updated_value(self.positive, self.en))
        m.d.comb += [
            self.is_positive.eq(cnt.is_positive()),
            self.is_saturate.eq(cnt.is_saturate()),
        ]
        return m


# ============================================================================
# Public Adapter
# ============================================================================
# Build Verilog for the registered counter / 为寄存器计数器生成 Verilog
def build_verilog(config: SignedSaturateCounterConfig = SignedSaturateCounterConfig()) -> str:
    top = SignedSaturateCounterReg(config)
    ports = [top.en, top.positive, top.value, top.is_positive, top.is_saturate]
    return verilog.convert(top, ports=ports)


# ============================================================================
# Direct Entry
# ============================================================================
# Direct entry: print generated Verilog / 直接入口：打印生成的 Verilog
def main() -> None:
    print(build_verilog())


if __name__ == "__main__":
    main()
