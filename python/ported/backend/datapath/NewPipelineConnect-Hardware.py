"""NewPipelineConnect (decoupled pipeline register with flush/older override). / 流水线寄存器（带冲刷与更老覆盖）。"""

from __future__ import annotations

from amaranth import Cat, Const, Elaboratable, Module, Mux, Signal
from amaranth.lib import data


# =============================================================================
# Module Contract
# =============================================================================
# Public symbols / 公开符号:
#   - NewPipelineConnectPipe : one-stage pipeline register module
#   - NewPipelineConnect.connect : inline connect helper (builds the regs)
# Ports / 端口:
#   in_{valid,ready,bits} (Decoupled); out_{valid,ready,bits} (Decoupled);
#   rightOutFire, isFlush, isOlder (in).
# Real logic: a valid register plus a RegEnable data register; left.ready is
# right.ready || !valid || isOlder; valid cleared on rightOutFire/isFlush and
# set on left.fire. / 真实逻辑：有效寄存器加 RegEnable 数据寄存器；左就绪
# 为 右就绪或无效或更老；有效在右出火/冲刷时清、左出火时置。
# Status / 状态: PYTHON_PRESENT_UNVERIFIED (phase-1 bulk port / 阶段一批量重写)
__all__ = ["NewPipelineConnectPipe", "NewPipelineConnect", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
# (no parameters; data width passed at construction) / 无参数，数据宽度构造时给定


# =============================================================================
# Implementation
# =============================================================================
# connect responsibility. / connect 函数职责。
def connect(m, leftValid, leftReady, leftBits, rightValid, rightReady,
            rightBits, rightOutFire, isFlush, isOlder):
    # inline pipeline-connect (mirrors Scala NewPipelineConnect.connect) /
    # 内联流水线连接（镜像 Scala connect）
    valid = Signal(name="npc_valid", reset=0)
    dataReg = Signal.like(leftBits, name="npc_data")
    m.d.comb += leftReady.eq(rightReady | ~valid | isOlder)
    with m.If(leftValid & leftReady):
        m.d.sync += dataReg.eq(leftBits)
    with m.If(rightOutFire):
        m.d.sync += valid.eq(0)
    with m.If(leftValid & leftReady):
        m.d.sync += valid.eq(1)
    with m.If(isFlush):
        m.d.sync += valid.eq(0)
    m.d.comb += rightBits.eq(dataReg)
    m.d.comb += rightValid.eq(valid)
    return dataReg


class NewPipelineConnectPipe(Elaboratable):
    # one-stage decoupled pipeline register / 单级 Decoupled 流水线寄存器
    def __init__(self, dataWidth=64):
        self.dataWidth = dataWidth
        self.in_valid = Signal(name="in_valid")
        self.in_ready = Signal(name="in_ready")
        self.in_bits = Signal(dataWidth, name="in_bits")
        self.out_valid = Signal(name="out_valid")
        self.out_ready = Signal(name="out_ready")
        self.out_bits = Signal(dataWidth, name="out_bits")
        self.rightOutFire = Signal(name="rightOutFire")
        self.isFlush = Signal(name="isFlush")
        self.isOlder = Signal(name="isOlder")

    # elaborate responsibility. / elaborate 函数职责。
    def elaborate(self, platform):
        # build the pipeline register / 构建流水线寄存器
        m = Module()
        connect(m, self.in_valid, self.in_ready, self.in_bits,
                self.out_valid, self.out_ready, self.out_bits,
                self.rightOutFire, self.isFlush, self.isOlder)
        return m


class NewPipelineConnect:
    # static facade mirroring the Scala object / 静态门面（镜像 Scala object）
    @staticmethod
    # connect responsibility. / connect 函数职责。
    def connect(m, leftValid, leftReady, leftBits, rightValid, rightReady,
                rightBits, rightOutFire, isFlush, isOlder):
        # inline connect (no submodule) / 内联连接（无子模块）
        return connect(m, leftValid, leftReady, leftBits, rightValid, rightReady,
                       rightBits, rightOutFire, isFlush, isOlder)


# =============================================================================
# Public Adapter
# =============================================================================
# build_verilog responsibility. / build_verilog 函数职责。
def build_verilog(dataWidth: int = 64, name: str = "NewPipelineConnectPipe") -> str:
    # Convert pipeline to verilog / 转换流水线为 Verilog
    from amaranth.back import verilog

    top = NewPipelineConnectPipe(dataWidth)
    ports = [top.in_valid, top.in_ready, top.in_bits, top.out_valid,
             top.out_ready, top.out_bits, top.rightOutFire, top.isFlush,
             top.isOlder]
    return verilog.convert(top, name=name, ports=ports)


# =============================================================================
# Direct Entry
# =============================================================================
# main responsibility. / main 函数职责。
def main() -> None:
    # Entry point / 入口
    print(build_verilog())


if __name__ == "__main__":
    main()
