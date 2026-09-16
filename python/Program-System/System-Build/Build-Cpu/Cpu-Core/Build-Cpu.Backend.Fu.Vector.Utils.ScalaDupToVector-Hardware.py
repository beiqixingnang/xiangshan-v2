"""Duplicate a scalar value across vector elements selected by VSew.
按 VSew 选定元素宽度将标量值复制到向量各元素。
"""

from __future__ import annotations

from dataclasses import dataclass

from amaranth import Cat, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# ScalaDupToVector.scala constructs four VecInit values from the low 8/16/32/
# 64 bits of scalaData and selects one with Mux1H.  VSew is two bits in V2;
# therefore every code is defined and no default arm is needed.  The packed
# Vec.asUInt ordering places element zero in the least-significant slice.
# ScalaDupToVector.scala 用 scalaData 低 8/16/32/64 位构造四个 VecInit，再以
# Mux1H 选择；V2 的 VSew 为两位，因此四个编码均有定义。Vec.asUInt 的元素零在低位。
__all__ = ["ScalaDupToVectorConfig", "VSew", "ScalaDupToVector", "duplicate_scalar_integer", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class ScalaDupToVectorConfig:
    """Vector geometry for the V2 helper. / V2 辅助器的向量几何配置。"""

    vlen: int = 128

    # Validate that all four element views are integral. / 校验四种元素视图均为整数。
    def __post_init__(self) -> None:
        if self.vlen < 64 or self.vlen % 64:
            raise ValueError("vlen must be a positive multiple of 64")


class VSew:
    """Canonical V2 element-width encodings. / V2 标准元素宽度编码。"""

    e8 = 0
    e16 = 1
    e32 = 2
    e64 = 3


# =============================================================================
# Implementation
# =============================================================================
# Build repeated low bits in the packed Vec.asUInt ordering. / 按打包 Vec.asUInt 顺序构造重复的低位数据。
def repeated_slice(scalar: Signal, element_width: int, vlen: int) -> object:
    return Cat(*[scalar[:element_width] for _ in range(vlen // element_width)])


def duplicate_scalar_integer(scalar: int, vsew: int, vlen: int = 128) -> int:
    """Duplicate scalar low bits across VLEN elements as ScalaDupToVector. / 按元素宽复制标量低位。"""

    element_width = 8 << int(vsew)
    if element_width not in (8, 16, 32, 64) or vlen < element_width or vlen % element_width:
        raise ValueError("invalid VSew or VLEN")
    element = int(scalar) & ((1 << element_width) - 1)
    return sum(element << (index * element_width) for index in range(vlen // element_width))


class ScalaDupToVector(Elaboratable):
    """Replicate scalar low bits over a VLEN vector. / 在 VLEN 向量上复制标量低位。"""

    # Declare the flattened source-compatible V2 ports. / 声明扁平化的 V2 兼容端口。
    def __init__(self, configuration: ScalaDupToVectorConfig | None = None):
        config = configuration or ScalaDupToVectorConfig()
        self.config = config
        self.in_scalaData = Signal(64, name="io_in_scalaData")
        self.in_vsew = Signal(2, name="io_in_vsew")
        self.out_vecData = Signal(config.vlen, name="io_out_vecData")

    # Elaborate the four Mux1H arms from the canonical Scala. / 展开 Scala 的四个 Mux1H 分支。
    def elaborate(self, platform):
        del platform
        module = Module()
        width = self.config.vlen
        e8 = repeated_slice(self.in_scalaData, 8, width)
        e16 = repeated_slice(self.in_scalaData, 16, width)
        e32 = repeated_slice(self.in_scalaData, 32, width)
        e64 = repeated_slice(self.in_scalaData, 64, width)
        selected = Mux(
            self.in_vsew == VSew.e8,
            e8,
            Mux(
                self.in_vsew == VSew.e16,
                e16,
                Mux(self.in_vsew == VSew.e32, e32, e64),
            ),
        )
        module.d.comb += self.out_vecData.eq(selected)
        return module


# =============================================================================
# Public Adapter
# =============================================================================
# Emit deterministic V2-compatible Verilog. / 输出确定性的 V2 兼容 Verilog。
def build_verilog(configuration, injected_dependencies) -> str:
    del injected_dependencies
    top = ScalaDupToVector(configuration)
    return verilog.convert(
        top, name="ScalaDupToVector",
        ports=[top.in_scalaData, top.in_vsew, top.out_vecData], emit_src=False,
    )


# =============================================================================
# Direct Entry
# =============================================================================
# Print the default standalone helper. / 直接打印默认独立辅助器。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
