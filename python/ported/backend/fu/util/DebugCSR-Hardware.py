"""DebugCSR (DcsrStruct debug CSR bundle). / 调试 CSR（DcsrStruct 调试寄存器束）。"""

from __future__ import annotations

from amaranth import Cat, Const, Elaboratable, Module, Signal

# =============================================================================
# Module Contract
# =============================================================================
# =============================================================================
# Configuration
# =============================================================================
# =============================================================================
# Implementation
# =============================================================================
# =============================================================================
# Public Adapter
# =============================================================================
# =============================================================================
# Direct Entry
# =============================================================================



# =============================================================================
# =============================================================================
# Public symbols / 公开符号:
#   - DcsrStruct : 32-bit debug CSR field layout + init constant
#   - DEBUGVER_*, CAUSE_* : debug constants
#   - build_verilog, main
# Real logic: 32-bit dcsr field decomposition (debugver[31:28], ebreakm[15],
# ebreaks[13], ebreaku[12], cause[8:6], prv[1:0] etc.); init = DEBUGVER_SPEC
# at offset 28 | ModeM at offset 0. Field accessors as pure helpers.
# / 真实逻辑：32 位 dcsr 字段分解（debugver[31:28]、ebreakm[15]、ebreaks[13]、
# ebreaku[12]、cause[8:6]、prv[1:0] 等）；init = DEBUGVER_SPEC 在 28 偏移 |
# ModeM 在 0 偏移。字段访问器为纯助手。
# Status / 状态: PYTHON_PRESENT_UNVERIFIED (phase-1 bulk port / 阶段一批量重写)
__all__ = ["DcsrStruct", "build_verilog", "main"]


# =============================================================================
# =============================================================================
class DcsrStruct(Elaboratable):
    # 32-bit dcsr surface / 32 位 dcsr 表面
    DEBUGVER_NONE = 0
    DEBUGVER_SPEC = 4
    DEBUGVER_CUSTOM = 15
    CAUSE_EBREAK = 1
    CAUSE_TRIGGER = 2
    CAUSE_HALTREQ = 3
    CAUSE_STEP = 4
    CAUSE_RESETHALTREQ = 5
    ModeM = 0x3

    # __init__ implementation / __init__ 实现。
    def __init__(self):
        self.value = Signal(32, name="dcsr")
        self.debugver = Signal(4, name="dcsr_debugver")
        self.ebreakm = Signal(name="dcsr_ebreakm")
        self.ebreaks = Signal(name="dcsr_ebreaks")
        self.ebreaku = Signal(name="dcsr_ebreaku")
        self.cause = Signal(3, name="dcsr_cause")
        self.prv = Signal(2, name="dcsr_prv")

    @staticmethod
    # init implementation / init 实现。
    def init():
        # DEBUGVER_SPEC<<28 | ModeM<<0 / 初始化值
        return (DcsrStruct.DEBUGVER_SPEC << 28) | (DcsrStruct.ModeM << 0)

    # elaborate implementation / elaborate 实现。
    def elaborate(self, platform):
        m = Module()
        v = self.value
        m.d.comb += self.debugver.eq(v.bit_select(28, 4))
        m.d.comb += self.ebreakm.eq(v.bit_select(15, 1))
        m.d.comb += self.ebreaks.eq(v.bit_select(13, 1))
        m.d.comb += self.ebreaku.eq(v.bit_select(12, 1))
        m.d.comb += self.cause.eq(v.bit_select(6, 3))
        m.d.comb += self.prv.eq(v.bit_select(0, 2))
        return m


# =============================================================================
# =============================================================================
# (layout/constants only at phase-1 granularity; see Module Contract)
# / 阶段一粒度下仅布局与常量；见模块契约。

# =============================================================================
# =============================================================================
# build_verilog implementation / build_verilog 实现。
def build_verilog(config=None, name: str = "DcsrStruct") -> str:
    from amaranth.back import verilog
    top = DcsrStruct()
    ports = [top.value, top.debugver, top.ebreakm, top.ebreaks,
             top.ebreaku, top.cause, top.prv]
    return verilog.convert(top, name=name, ports=ports)


# main implementation / main 实现。
def main() -> None:
    print(build_verilog())


if __name__ == "__main__":
    main()

# =============================================================================
# =============================================================================
# main implementation / main 实现。
def main() -> None:
    # direct elaboration entry / 直接入口
    print(build_verilog())

if __name__ == "__main__":
    main()
