"""Fill mask-destination tail bits according to the active vector length.
依据活动向量长度填充掩码目的尾部位。
"""

from __future__ import annotations

from dataclasses import dataclass

from amaranth import Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# Mgtu.scala treats every bit index below vl as data and every bit at or above
# vl as one.  The operation is combinational and deliberately independent of
# vta. Mgtu.scala 将 vl 以下的位保留为数据，将 vl 及以上的位设为一；该操作为
# 组合逻辑且有意与 vta 无关。 The flattened names below match Chisel output.
__all__ = ["MgtuConfig", "Mgtu", "mgtu_value", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class MgtuConfig:
    """Vector and VL field widths. / 向量与 VL 字段宽度。"""

    vlen: int = 128
    vl_width: int = 8

    # Validate widths accepted by the V2 module. / 校验 V2 模块接受的位宽。
    def __post_init__(self) -> None:
        if self.vlen < 1 or self.vlen % 8:
            raise ValueError("vlen must be a positive multiple of 8")
        if self.vl_width < 1:
            raise ValueError("vl_width must be positive")


# =============================================================================
# Implementation
# =============================================================================
# Compute the integer-level Mgtu contract for direct reference tests. / 计算整数级 Mgtu 合同以供直接参考测试。
def mgtu_value(vd: int, vl: int, config: MgtuConfig | None = None) -> int:
    c = config or MgtuConfig()
    mask = (1 << c.vlen) - 1
    if vl < 0:
        raise ValueError("vl must be non-negative")
    return ((vd & mask) & ((1 << min(vl, c.vlen)) - 1)) | (
        mask & ~((1 << min(vl, c.vlen)) - 1)
    )


class Mgtu(Elaboratable):
    """Combinational mask-tail fill unit. / 组合式掩码尾部填充单元。"""

    # Declare the flattened V2 MgtuIO ports. / 声明扁平化的 V2 MgtuIO 端口。
    def __init__(self, configuration: MgtuConfig | None = None):
        config = configuration or MgtuConfig()
        self.config = config
        self.in_vd = Signal(config.vlen, name="io_in_vd")
        self.in_vl = Signal(config.vl_width, name="io_in_vl")
        self.out_vd = Signal(config.vlen, name="io_out_vd")

    # Elaborate one conditional assignment per destination bit. / 为每个目的位展开条件赋值。
    def elaborate(self, platform):
        del platform
        module = Module()
        for index in range(self.config.vlen):
            module.d.comb += self.out_vd[index].eq(
                Mux(index < self.in_vl, self.in_vd[index], Const(1, 1))
            )
        return module


# =============================================================================
# Public Adapter
# =============================================================================
# Emit deterministic V2-compatible Verilog. / 输出确定性的 V2 兼容 Verilog。
def build_verilog(configuration, injected_dependencies) -> str:
    del injected_dependencies
    top = Mgtu(configuration)
    return verilog.convert(top, name="Mgtu", ports=[top.in_vd, top.in_vl, top.out_vd], emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print the default standalone helper. / 直接打印默认独立辅助器。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
