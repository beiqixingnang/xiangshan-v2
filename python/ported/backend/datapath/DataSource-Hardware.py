"""DataSource (source-selector codes for register reads). / 数据源选择码（寄存器读）。."""

from __future__ import annotations

from dataclasses import dataclass

from amaranth import Elaboratable, Module, Signal


# =============================================================================
# Module Contract
# =============================================================================
# Public symbols / 公开符号:
#   - DataSource : 4-bit source-selector bundle and source constants
# The Scala source is a Bundle carrying a 4-bit value and predicate methods.
# Status / 状态: PYTHON_PRESENT_UNVERIFIED (phase-1 bulk port / 阶段一批量重写)
__all__ = ["DataSource", "DataSourceProbe", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
class DataSource:
    # 4-bit source selector bundle / 4 位数据源 Bundle
    def __init__(self, value: Signal | None = None):
        # Create the hardware value field / 创建硬件 value 字段
        self.value = value if value is not None else Signal(4, name="value")

    # Read-register predicate / 读取寄存器谓词
    def readReg(self, value=None):
        if value is None:
            return self.value[3]
        return (value & 0b1000) != 0

    # Register source predicate / 普通寄存器源谓词
    def readRegOH(self):
        return self.value == self.reg

    # Register-cache source predicate / 寄存器缓存源谓词
    def readRegCache(self):
        return self.value == self.regcache

    # Vector-zero source predicate / 向量零源谓词
    def readV0(self):
        return self.value == self.v0

    # Zero source predicate / 零源谓词
    def readZero(self):
        return self.value == self.zero

    # Forward source predicate / 前递源谓词
    def readForward(self):
        return self.value == self.forward

    # Bypass source predicate / 旁路源谓词
    def readBypass(self):
        return self.value == self.bypass

    # Secondary bypass source predicate / 第二旁路源谓词
    def readBypass2(self):
        return self.value == self.bypass2

    # Immediate source predicate / 立即数源谓词
    def readImm(self):
        return self.value == self.imm

    # Integer constant for a source code / 源编码整数常量
    reg = 0b1000
    regcache = 0b0110
    v0 = 0b0101
    zero = 0b0000
    forward = 0b0001
    bypass = 0b0010
    bypass2 = 0b0011
    imm = 0b0100

    @staticmethod
    # Integer predicate helper / 整数谓词辅助函数
    def isReg(value):
        # value === reg / 等于 reg
        return value == DataSource.reg

    @staticmethod
    # Integer predicate helper / 整数谓词辅助函数
    def isRegCache(value):
        # value === regcache / 等于 regcache
        return value == DataSource.regcache

    @staticmethod
    # Integer predicate helper / 整数谓词辅助函数
    def isV0(value):
        # value === v0 / 等于 v0
        return value == DataSource.v0

    @staticmethod
    # Integer predicate helper / 整数谓词辅助函数
    def isZero(value):
        # value === zero / 等于 zero
        return value == DataSource.zero

    @staticmethod
    # Integer predicate helper / 整数谓词辅助函数
    def isForward(value):
        # value === forward / 等于 forward
        return value == DataSource.forward

    @staticmethod
    # Integer predicate helper / 整数谓词辅助函数
    def isBypass(value):
        # value === bypass / 等于 bypass
        return value == DataSource.bypass

    @staticmethod
    # Integer predicate helper / 整数谓词辅助函数
    def isBypass2(value):
        # value === bypass2 / 等于 bypass2
        return value == DataSource.bypass2

    @staticmethod
    # Integer predicate helper / 整数谓词辅助函数
    def isImm(value):
        # value === imm / 等于 imm
        return value == DataSource.imm


# =============================================================================
# Implementation
# =============================================================================
class DataSourceProbe(Elaboratable):
    """Expose DataSource predicates for synthesis and direct checks. / 暴露谓词供综合和直接检查。"""

    # Initialize probe ports / 初始化探针端口
    def __init__(self):
        # Probe input and predicate outputs / 探针输入与谓词输出
        self.value = Signal(4)
        self.read_reg = Signal()
        self.read_reg_oh = Signal()
        self.read_reg_cache = Signal()
        self.read_v0 = Signal()
        self.read_zero = Signal()
        self.read_forward = Signal()
        self.read_bypass = Signal()
        self.read_bypass2 = Signal()
        self.read_imm = Signal()

    # Elaborate combinational predicate wiring / 展开组合谓词连线
    def elaborate(self, platform):
        # Combinationally expose all Scala predicates / 组合暴露 Scala 全部谓词
        m = Module()
        source = DataSource(self.value)
        m.d.comb += [
            self.read_reg.eq(source.readReg()),
            self.read_reg_oh.eq(source.readRegOH()),
            self.read_reg_cache.eq(source.readRegCache()),
            self.read_v0.eq(source.readV0()),
            self.read_zero.eq(source.readZero()),
            self.read_forward.eq(source.readForward()),
            self.read_bypass.eq(source.readBypass()),
            self.read_bypass2.eq(source.readBypass2()),
            self.read_imm.eq(source.readImm()),
        ]
        return m


# =============================================================================
# Public Adapter
# =============================================================================
# Convert the probe to deterministic Verilog / 将探针转换为确定性 Verilog
def build_verilog(name: str = "DataSource") -> str:
    # Convert probe to verilog / 转换探针为 Verilog
    from amaranth.back import verilog

    probe = DataSourceProbe()
    return verilog.convert(probe, name=name,
                           ports=[probe.value, probe.read_reg,
                                  probe.read_reg_oh, probe.read_reg_cache,
                                  probe.read_v0, probe.read_zero,
                                  probe.read_forward, probe.read_bypass,
                                  probe.read_bypass2, probe.read_imm])


# =============================================================================
# Direct Entry
# =============================================================================
# Run the direct export entry point / 运行直接导出入口
def main() -> None:
    # Entry point / 入口
    print(build_verilog())


if __name__ == "__main__":
    main()
