"""V2 commit-stuck watchdog counter.
V2 提交卡死监视计数器。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from amaranth import ClockDomain, Elaboratable, Module, Signal


# =============================================================================
# Module Contract
# =============================================================================
# The V2 counter clears when disabled/not stuck and reports an all-ones
# overflow after the configured number of consecutive stuck cycles.
# V2 计数器在禁用或未卡死时清零，并在连续卡死达到阈值时报告溢出。
__all__ = ["CommitStuckCounterConfig", "CommitStuckCounter", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class CommitStuckCounterConfig:
    """Counter width and force-enable policy. / 计数器位宽与强制使能策略。"""

    width: int = 21
    force_enable: bool = False

    # Validate the V2 counter geometry. / 校验 V2 计数器几何约束。
    def __post_init__(self) -> None:
        if self.width < 1:
            raise ValueError("width must be positive")


# =============================================================================
# Implementation
# =============================================================================
class CommitStuckCounter(Elaboratable):
    """Registered watchdog with explicit V2 ports. / 带显式 V2 端口的寄存式监视器。"""

    # Construct watchdog ports. / 构造监视器端口。
    def __init__(self, configuration: CommitStuckCounterConfig = CommitStuckCounterConfig()) -> None:
        self.configuration = configuration
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.clock_domain = ClockDomain("sync", async_reset=True)
        self.clock_domain.clk = self.clock
        self.clock_domain.rst = self.reset
        self.stuck = Signal(name="io_stuck")
        self.runtime_enable = Signal(name="io_runtimeEnable")
        self.overflow_enabled = Signal(name="io_overflowEnabled")
        self.count = Signal(configuration.width, name="io_count")
        self.overflow = Signal(name="io_overflow")

    # Elaborate reset, clear, increment, and overflow equations. / 展开复位、清零、递增与溢出方程。
    def elaborate(self, platform) -> Module:
        del platform
        m = Module()
        m.domains += self.clock_domain
        m.d.comb += self.overflow.eq(self.count.all() & self.overflow_enabled)
        effective_enable = self.runtime_enable | self.configuration.force_enable
        with cast(Any, m.If(effective_enable & self.stuck)):
            m.d.sync += self.count.eq(self.count + 1)
        with cast(Any, m.Else()):
            m.d.sync += self.count.eq(0)
        return m


# =============================================================================
# Public Adapter
# =============================================================================
# Emit a deterministic standalone watchdog module. / 输出确定性的独立监视器模块。
def build_verilog(configuration=None, injected_dependencies=None) -> str:
    """Build Verilog for the configured counter. / 为配置计数器生成 Verilog。"""

    del injected_dependencies
    from amaranth.back import verilog

    config = configuration or CommitStuckCounterConfig()
    top = CommitStuckCounter(config)
    return verilog.convert(
        top,
        name="CommitStuckCounter",
        ports=[top.clock, top.reset, top.stuck, top.runtime_enable,
               top.overflow_enabled, top.count, top.overflow],
    )


# =============================================================================
# Direct Entry
# =============================================================================
# Print the standalone watchdog RTL. / 打印独立监视器 RTL。
def main() -> None:
    """Print generated Verilog. / 打印生成的 Verilog。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
