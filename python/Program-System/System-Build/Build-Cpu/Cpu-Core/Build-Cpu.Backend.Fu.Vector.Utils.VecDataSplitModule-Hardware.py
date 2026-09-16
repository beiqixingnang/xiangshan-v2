"""Expose packed vector data at 8-, 16-, 32-, and 64-bit granularity.
以 8、16、32 和 64 位粒度导出打包向量数据。
"""

from __future__ import annotations

from dataclasses import dataclass

from amaranth import Elaboratable, Module, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# VecDataSplitModule.scala uses UInt.asTypeOf(Vec(...)) four times.  This is a
# pure bit reinterpretation: output element i is input bits [i*w+w-1:i*w],
# with no byte swapping or register state.  The Scala outDataWidth argument is
# retained in configuration because it is part of the constructor, although it
# does not affect the IO shape.  VecDataSplitModule.scala 四次使用 asTypeOf；
# 这是纯位重解释，元素 i 为输入 [i*w+w-1:i*w]，无换字节或寄存器状态。Scala
# 的 outDataWidth 构造参数保留在配置中，但不改变 IO 形状。
__all__ = ["VecDataSplitConfig", "VecDataSplitModule", "split_integer", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class VecDataSplitConfig:
    """Widths of the V2 splitter constructor. / V2 分割器构造参数宽度。"""

    inDataWidth: int = 128
    outDataWidth: int = 128

    # Validate the source geometry and retained constructor width. / 校验源几何与保留的构造宽度。
    def __post_init__(self) -> None:
        if self.inDataWidth < 64 or self.inDataWidth % 64:
            raise ValueError("inDataWidth must be a positive multiple of 64")
        if self.outDataWidth < 1:
            raise ValueError("outDataWidth must be positive")


# =============================================================================
# Implementation
# =============================================================================
# Connect every output slice to its corresponding packed input range. / 将每个输出切片连接到对应的打包输入范围。
def connect_slices(module: Module, source: Signal, outputs: list[Signal], width: int) -> None:
    for index, output in enumerate(outputs):
        module.d.comb += output.eq(source.bit_select(index * width, width))


def split_integer(value: int, in_width: int = 128) -> dict[str, list[int]]:
    """Return all four packed views used by VecDataSplitModule. / 返回四种打包视图。"""

    masked = int(value) & ((1 << in_width) - 1)
    return {f"bits{width}": [(masked >> offset) & ((1 << width) - 1)
                             for offset in range(0, in_width, width)]
            for width in (8, 16, 32, 64)}


class VecDataSplitModule(Elaboratable):
    """Split one packed vector into fixed-width views. / 将打包向量拆为固定宽度视图。"""

    # Declare the flattened source-compatible V2 ports. / 声明扁平化的 V2 兼容端口。
    def __init__(self, configuration: VecDataSplitConfig | None = None):
        config = configuration or VecDataSplitConfig()
        self.config = config
        width = config.inDataWidth
        self.inVecData = Signal(width, name="io_inVecData")
        self.outVec8b = [Signal(8, name=f"io_outVec8b_{i}") for i in range(width // 8)]
        self.outVec16b = [Signal(16, name=f"io_outVec16b_{i}") for i in range(width // 16)]
        self.outVec32b = [Signal(32, name=f"io_outVec32b_{i}") for i in range(width // 32)]
        self.outVec64b = [Signal(64, name=f"io_outVec64b_{i}") for i in range(width // 64)]

    # Elaborate all four combinational reinterpretations. / 展开四种组合位重解释。
    def elaborate(self, platform):
        del platform
        module = Module()
        connect_slices(module, self.inVecData, self.outVec8b, 8)
        connect_slices(module, self.inVecData, self.outVec16b, 16)
        connect_slices(module, self.inVecData, self.outVec32b, 32)
        connect_slices(module, self.inVecData, self.outVec64b, 64)
        return module


# =============================================================================
# Public Adapter
# =============================================================================
# Emit deterministic V2-compatible Verilog. / 输出确定性的 V2 兼容 Verilog。
def build_verilog(configuration, injected_dependencies) -> str:
    del injected_dependencies
    top = VecDataSplitModule(configuration)
    ports = [top.inVecData, *top.outVec8b, *top.outVec16b,
             *top.outVec32b, *top.outVec64b]
    return verilog.convert(top, name="VecDataSplitModule", ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print the default standalone helper. / 直接打印默认独立辅助器。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
