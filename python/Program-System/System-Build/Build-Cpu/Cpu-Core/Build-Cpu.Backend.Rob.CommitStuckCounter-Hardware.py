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
# The locked V2 ABI has clock/reset, stuck/runtimeEnable inputs and one
# overflow output.  The count is private state and overflow is the reduction
# AND of that state (there is no external overflow-enable gate).
# 锁定 V2 ABI 只有时钟/复位、卡死/运行使能输入和溢出输出；计数为私有状态，
# 溢出是计数的归约与（不存在外部 overflow-enable 门控）。
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
        # Keep count internal: the locked generated module does not expose it.
        # 保持 count 为内部状态：锁定生成模块不导出该端口。
        self.count = Signal(configuration.width, name="count")
        self.overflow = Signal(name="io_overflow")

    # Elaborate reset, clear, increment, and overflow equations. / 展开复位、清零、递增与溢出方程。
    def elaborate(self, platform) -> Module:
        del platform
        m = Module()
        m.domains += self.clock_domain
        m.d.comb += self.overflow.eq(self.count.all())
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
        ports=[top.clock, top.reset, top.stuck, top.runtime_enable, top.overflow],
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
