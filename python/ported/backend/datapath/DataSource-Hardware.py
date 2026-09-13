"""V2 register-source selector and predicates.
V2 寄存器数据源选择器及其谓词。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amaranth import Elaboratable, Module, Signal


# =============================================================================
# Module Contract
# =============================================================================
# DataSource.scala is a four-bit Bundle.  The values are kept as source
# traceable integers here; no external XiangShan/Scala import is needed.
# DataSource.scala 是四位 Bundle；这里保留可追溯的整数编码，不导入外部 Scala。
__all__ = ["DataSourceConfig", "DataSource", "DataSourceProbe", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class DataSourceConfig:
    """Serializable selector configuration. / 可序列化的选择器配置。"""

    width: int = 4

    # Validate the fixed V2 selector width. / 校验 V2 固定选择器位宽。
    def __post_init__(self) -> None:
        if self.width != 4:
            raise ValueError("V2 DataSource.value is exactly four bits")


class DataSource:
    """Four-bit source Bundle facade. / 四位数据源 Bundle 门面。"""

    # Construct the value field, optionally reusing a hardware signal. / 构造 value 字段，可选复用外部硬件信号。
    def __init__(self, value: Signal | None = None) -> None:
        self.value = value if value is not None else Signal(4, name="value")

    # Evaluate the read-register bit predicate. / 计算读寄存器位谓词。
    def readReg(self, value: Any = None):
        return self.value[3] if value is None else ((value & 0b1000) != 0)

    # Evaluate the ordinary register source predicate. / 计算普通寄存器源谓词。
    def readRegOH(self):
        return self.value == self.reg

    # Evaluate the register-cache source predicate. / 计算寄存器缓存源谓词。
    def readRegCache(self):
        return self.value == self.regcache

    # Evaluate the vector-zero source predicate. / 计算向量零源谓词。
    def readV0(self):
        return self.value == self.v0

    # Evaluate the zero source predicate. / 计算零源谓词。
    def readZero(self):
        return self.value == self.zero

    # Evaluate the forwarding source predicate. / 计算前递源谓词。
    def readForward(self):
        return self.value == self.forward

    # Evaluate the first bypass source predicate. / 计算第一旁路源谓词。
    def readBypass(self):
        return self.value == self.bypass

    # Evaluate the second bypass source predicate. / 计算第二旁路源谓词。
    def readBypass2(self):
        return self.value == self.bypass2

    # Evaluate the immediate source predicate. / 计算立即数源谓词。
    def readImm(self):
        return self.value == self.imm

    # V2 source-selector encodings. / V2 数据源选择编码。
    reg = 0b1000
    regcache = 0b0110
    v0 = 0b0101
    zero = 0b0000
    forward = 0b0001
    bypass = 0b0010
    bypass2 = 0b0011
    imm = 0b0100

    @staticmethod
    # Test an integer against the register encoding. / 检查整数是否为寄存器编码。
    def isReg(value: int) -> bool:
        return int(value) == DataSource.reg

    @staticmethod
    # Test an integer against the cache encoding. / 检查整数是否为缓存编码。
    def isRegCache(value: int) -> bool:
        return int(value) == DataSource.regcache

    @staticmethod
    # Test an integer against the vector-zero encoding. / 检查整数是否为向量零编码。
    def isV0(value: int) -> bool:
        return int(value) == DataSource.v0

    @staticmethod
    # Test an integer against the zero encoding. / 检查整数是否为零编码。
    def isZero(value: int) -> bool:
        return int(value) == DataSource.zero

    @staticmethod
    # Test an integer against the forwarding encoding. / 检查整数是否为前递编码。
    def isForward(value: int) -> bool:
        return int(value) == DataSource.forward

    @staticmethod
    # Test an integer against the first bypass encoding. / 检查整数是否为第一旁路编码。
    def isBypass(value: int) -> bool:
        return int(value) == DataSource.bypass

    @staticmethod
    # Test an integer against the second bypass encoding. / 检查整数是否为第二旁路编码。
    def isBypass2(value: int) -> bool:
        return int(value) == DataSource.bypass2

    @staticmethod
    # Test an integer against the immediate encoding. / 检查整数是否为立即数编码。
    def isImm(value: int) -> bool:
        return int(value) == DataSource.imm


# =============================================================================
# Implementation
# =============================================================================
class DataSourceProbe(Elaboratable):
    """Expose all V2 predicates for simulation and synthesis.
    暴露全部 V2 谓词以供仿真和综合。
    """

    # Construct probe ports corresponding to the Bundle observations. / 构造对应 Bundle 观测点的探针端口。
    def __init__(self) -> None:
        self.value = Signal(4, name="io_value")
        self.read_reg = Signal(name="io_readReg")
        self.read_reg_oh = Signal(name="io_readRegOH")
        self.read_reg_cache = Signal(name="io_readRegCache")
        self.read_v0 = Signal(name="io_readV0")
        self.read_zero = Signal(name="io_readZero")
        self.read_forward = Signal(name="io_readForward")
        self.read_bypass = Signal(name="io_readBypass")
        self.read_bypass2 = Signal(name="io_readBypass2")
        self.read_imm = Signal(name="io_readImm")

    # Wire each Scala predicate to an observable output. / 将每个 Scala 谓词连接到观测输出。
    def elaborate(self, platform) -> Module:
        del platform
        module = Module()
        source = DataSource(self.value)
        module.d.comb += [
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
        return module


# =============================================================================
# Public Adapter
# =============================================================================
# Export a deterministic DataSource probe. / 导出确定性的 DataSource 探针。
def build_verilog(configuration, injected_dependencies):
    """Return Verilog for the configured selector probe. / 返回配置选择器探针的 Verilog。"""
    from amaranth.back import verilog

    del injected_dependencies
    config = configuration if isinstance(configuration, dict) else {}
    name = str(config.get("name", config.get("module", "DataSource")))
    top = DataSourceProbe()
    ports = [
        top.value,
        top.read_reg,
        top.read_reg_oh,
        top.read_reg_cache,
        top.read_v0,
        top.read_zero,
        top.read_forward,
        top.read_bypass,
        top.read_bypass2,
        top.read_imm,
    ]
    return verilog.convert(top, name=name, ports=ports)


# =============================================================================
# Direct Entry
# =============================================================================
# Print the default deterministic export. / 打印默认确定性导出结果。
def main() -> None:
    print(build_verilog(None, None))


if __name__ == "__main__":
    main()
