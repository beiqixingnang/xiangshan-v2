"""Sstc timer-comparison interrupt generator. / Sstc 时间比较中断生成器。"""

from __future__ import annotations

from typing import Any, cast

from amaranth import ClockDomain, ClockSignal, Elaboratable, Module, ResetSignal, Signal


# Module Contract
# =============================================================================
# STIP/VSTIP are registered comparisons. Each register updates only when its
# Scala ``RegEnable`` condition is true and resets asynchronously high.
__all__ = ["SstcInterruptGen", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
# The pinned Scala module has no tunable parameters; all comparison inputs are
# explicit ports. / 锁定 Scala 模块没有可调参数，所有比较输入均为显式端口。

# =============================================================================
# Implementation
# =============================================================================


class SstcInterruptGen(Elaboratable):
    """Generate supervisor and virtual-supervisor timer interrupts.

    生成 supervisor 与 virtual-supervisor 定时器中断。
    """

    # Declare timer comparison ports and state / 声明定时器比较端口与状态。
    def __init__(self):
        # Explicit declarations keep the public hardware contract visible to
        # static analyzers and to the validation adapter.
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.i_stime_valid = Signal(name="i_stime_valid")
        self.i_stime_bits = Signal(64, name="i_stime_bits")
        self.i_vstime_valid = Signal(name="i_vstime_valid")
        self.i_vstime_bits = Signal(64, name="i_vstime_bits")
        self.i_stimecmp_wen = Signal(name="i_stimecmp_wen")
        self.i_stimecmp_rdata = Signal(64, name="i_stimecmp_rdata")
        self.i_vstimecmp_wen = Signal(name="i_vstimecmp_wen")
        self.i_vstimecmp_rdata = Signal(64, name="i_vstimecmp_rdata")
        self.i_htimedeltaWen = Signal(name="i_htimedeltaWen")
        self.i_menvcfg_wen = Signal(name="i_menvcfg_wen")
        self.i_menvcfg_STCE = Signal(name="i_menvcfg_STCE")
        self.i_henvcfg_wen = Signal(name="i_henvcfg_wen")
        self.i_henvcfg_STCE = Signal(name="i_henvcfg_STCE")
        self.o_STIP = Signal(name="o_STIP")
        self.o_VSTIP = Signal(name="o_VSTIP")
        self.stipReg = Signal(name="o_STIP_r", reset=0)
        self.vstipReg = Signal(name="o_VSTIP_r", reset=0)

    # Elaborate registered comparisons in an async-reset domain / 在异步复位域构造寄存器比较逻辑。
    def elaborate(self, platform):
        module = Module()
        module.domains += ClockDomain("sstc", async_reset=True, local=True)
        module.d.comb += [
            ClockSignal("sstc").eq(self.clock),
            ResetSignal("sstc").eq(self.reset),
            self.o_STIP.eq(self.stipReg),
            self.o_VSTIP.eq(self.vstipReg),
        ]
        with cast(Any, module.If(self.i_stime_valid | self.i_stimecmp_wen |
                                 self.i_menvcfg_wen)):
            module.d.sstc += self.stipReg.eq(
                (self.i_stime_bits >= self.i_stimecmp_rdata) & self.i_menvcfg_STCE)
        with cast(Any, module.If(self.i_vstime_valid | self.i_vstimecmp_wen |
                                 self.i_htimedeltaWen | self.i_menvcfg_wen |
                                 self.i_henvcfg_wen)):
            module.d.sstc += self.vstipReg.eq(
                (self.i_vstime_bits >= self.i_vstimecmp_rdata) & self.i_henvcfg_STCE)
        return module


# =============================================================================
# Public Adapter
# =============================================================================
# Export a standalone Verilog view / 导出独立 Verilog 视图。
def build_verilog(configuration: Any = None, injected_dependencies: dict | None = None,
                  name: str = "SstcInterruptGen") -> str:
    """Export standalone Verilog for the validation adapter / 导出验证适配器所需 Verilog。"""
    del configuration, injected_dependencies
    from amaranth.back import verilog
    top = SstcInterruptGen()
    ports = [getattr(top, name) for name in (
        "clock", "reset", "i_stime_valid", "i_stime_bits", "i_vstime_valid",
        "i_vstime_bits", "i_stimecmp_wen", "i_stimecmp_rdata", "i_vstimecmp_wen",
        "i_vstimecmp_rdata", "i_htimedeltaWen", "i_menvcfg_wen", "i_menvcfg_STCE",
        "i_henvcfg_wen", "i_henvcfg_STCE", "o_STIP", "o_VSTIP")]
    return verilog.convert(top, name=name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print the generated Verilog / 打印生成的 Verilog。
def main() -> None:
    """Print the generated Verilog / 打印生成的 Verilog。"""
    print(build_verilog())


if __name__ == "__main__":
    main()
