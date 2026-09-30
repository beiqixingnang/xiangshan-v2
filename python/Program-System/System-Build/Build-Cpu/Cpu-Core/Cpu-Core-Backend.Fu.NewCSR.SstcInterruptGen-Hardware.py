"""V2 Sstc timer interrupt generator. / V2 Sstc 定时器中断生成器。"""

from __future__ import annotations

from typing import Any, cast

from amaranth import ClockDomain, Elaboratable, Module, Signal


# =============================================================================
# Module Contract
# =============================================================================
# ``STIP`` and ``VSTIP`` are independently enabled, asynchronously reset,
# registered unsigned comparisons, exactly as in SstcInterruptGen.scala.
# STIP/VSTIP 是独立使能、异步复位的无符号比较寄存器，与 Scala 一致。
__all__ = ["SstcInterruptGen", "sstc_observation", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
# The V2 module has no tunable parameters; all widths and enables are fixed by
# the source IO bundle. / V2 模块没有可调参数，宽度与使能均由源 IO 固定。


def sstc_observation(stime: int, stimecmp: int, vstime: int, vstimecmp: int,
                     stce: bool, vstce: bool) -> dict[str, int]:
    """Return unsigned STIP/VSTIP comparison outputs. / 返回无符号定时器比较结果。"""

    mask = (1 << 64) - 1
    return {"STIP": int(stce and ((int(stime) & mask) >= (int(stimecmp) & mask))),
            "VSTIP": int(vstce and ((int(vstime) & mask) >= (int(vstimecmp) & mask)))}


# =============================================================================
# Implementation
# =============================================================================
class SstcInterruptGen(Elaboratable):
    """Register supervisor timer comparison results. / 寄存定时器比较结果。"""

    # Declare the source IO fields and registered outputs / 声明源端口与寄存输出。
    def __init__(self) -> None:
        """Create all V2-compatible ports. / 创建全部 V2 兼容端口。"""

        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.clock_domain = ClockDomain("sync", async_reset=True)
        # Reuse the explicitly named source ports as the domain pins so both
        # simulation and emitted RTL expose ``clock``/``reset`` directly.
        self.clock_domain.clk = self.clock
        self.clock_domain.rst = self.reset
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
        self.stip_register = Signal(name="o_STIP_r", reset=0)
        self.vstip_register = Signal(name="o_VSTIP_r", reset=0)

    # Elaborate the asynchronous-reset register equations / 展开异步复位寄存方程。
    def elaborate(self, platform: Any) -> Module:
        """Build the two independently enabled registers. / 构建两个独立寄存器。"""

        del platform
        module = Module()
        module.domains += self.clock_domain
        module.d.comb += [
            self.o_STIP.eq(self.stip_register),
            self.o_VSTIP.eq(self.vstip_register),
        ]
        stip_enable = (self.i_stime_valid | self.i_stimecmp_wen |
                       self.i_menvcfg_wen)
        vstip_enable = (self.i_vstime_valid | self.i_vstimecmp_wen |
                        self.i_htimedeltaWen | self.i_menvcfg_wen |
                        self.i_henvcfg_wen)
        with cast(Any, module.If(stip_enable)):
            # RegEnable data expression: comparison is unsigned in Amaranth.
            module.d.sync += self.stip_register.eq(
                (self.i_stime_bits >= self.i_stimecmp_rdata) &
                self.i_menvcfg_STCE
            )
        with cast(Any, module.If(vstip_enable)):
            module.d.sync += self.vstip_register.eq(
                (self.i_vstime_bits >= self.i_vstimecmp_rdata) &
                self.i_henvcfg_STCE
            )
        return module


# =============================================================================
# Public Adapter
# =============================================================================
# Emit deterministic standalone Verilog / 输出确定性的独立 Verilog。
def build_verilog(configuration: Any = None,
                  injected_dependencies: dict[str, Any] | None = None) -> str:
    """Build the Sstc adapter. / 构建 Sstc 适配器。"""

    del configuration, injected_dependencies
    from amaranth.back import verilog

    top = SstcInterruptGen()
    ports = [
        top.clock, top.reset, top.i_stime_valid, top.i_stime_bits,
        top.i_vstime_valid, top.i_vstime_bits, top.i_stimecmp_wen,
        top.i_stimecmp_rdata, top.i_vstimecmp_wen, top.i_vstimecmp_rdata,
        top.i_htimedeltaWen, top.i_menvcfg_wen, top.i_menvcfg_STCE,
        top.i_henvcfg_wen, top.i_henvcfg_STCE, top.o_STIP, top.o_VSTIP,
    ]
    return verilog.convert(top, name="SstcInterruptGen", ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print the direct-entry adapter / 打印直接入口适配器。
def main() -> None:
    """Print generated Verilog. / 打印生成的 Verilog。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
