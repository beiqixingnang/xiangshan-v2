"""ScalaDupToVector hardware mirror. / ScalaDupToVector 硬件镜像。"""

from __future__ import annotations

from dataclasses import dataclass

from amaranth import Cat, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# The pinned XiangShan source (0ff31c2d) takes one 64-bit scalar and duplicates
# its low SEW bits into every element of a VLEN-wide vector. VSew encodings are
# e8=0, e16=1, e32=2 and e64=3; Mux1H has no selected arm for other encodings,
# therefore unsupported values produce zero. Vec.asUInt preserves element
# zero in the least-significant slice, which is the ordering used by Cat below.
# 固定 XiangShan 源码（0ff31c2d）将 64 位标量的低 SEW 位复制到 VLEN 向量的
# 每个元素。VSew 编码为 e8=0、e16=1、e32=2、e64=3；其他编码没有 Mux1H
# 分支，因此输出为零。Vec.asUInt 使元素 0 位于最低切片，下面 Cat 保持该顺序。
__all__ = ["ScalaDupToVectorConfig", "VSew", "ScalaDupToVector",
           "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class ScalaDupToVectorConfig:
    """Vector geometry for one ScalaDupToVector instance. / 向量几何配置。"""

    vlen: int = 128

    # Validate configuration geometry / 校验配置几何约束
    def __post_init__(self) -> None:
        if self.vlen < 64 or self.vlen % 64:
            raise ValueError("vlen must be a positive multiple of 64")


class VSew:
    """XiangShan vector element-width encodings. / 香山向量元素宽度编码。"""

    e8 = 0b000
    e16 = 0b001
    e32 = 0b010
    e64 = 0b011


# =============================================================================
# Implementation
# =============================================================================
class ScalaDupToVector(Elaboratable):
    """Duplicate scalar low-SEW bits over a VLEN-wide vector. / 复制标量。"""

    # Create the scalar, SEW and vector ports / 创建标量、SEW 与向量端口
    def __init__(self, configuration: ScalaDupToVectorConfig | None = None):
        config = configuration or ScalaDupToVectorConfig()
        self.config = config
        self.in_scalaData = Signal(64, name="sdv_scala")
        self.in_vsew = Signal(3, name="sdv_vsew")
        self.out_vecData = Signal(config.vlen, name="sdv_out")

    # Elaborate the four Chisel VecInit/asUInt branches / 展开四个 Chisel 分支
    def elaborate(self, platform):
        del platform
        module = Module()
        scalar = self.in_scalaData
        width = self.config.vlen
        e8 = Cat(*[scalar[:8] for _ in range(width // 8)])
        e16 = Cat(*[scalar[:16] for _ in range(width // 16)])
        e32 = Cat(*[scalar[:32] for _ in range(width // 32)])
        e64 = Cat(*[scalar[:64] for _ in range(width // 64)])
        selected = Mux(
            self.in_vsew == VSew.e8,
            e8,
            Mux(
                self.in_vsew == VSew.e16,
                e16,
                Mux(self.in_vsew == VSew.e32, e32,
                    Mux(self.in_vsew == VSew.e64, e64, Const(0, width))),
            ),
        )
        module.d.comb += self.out_vecData.eq(selected)
        return module


# =============================================================================
# Public Adapter
# =============================================================================
# Generate deterministic RTL for the requested geometry / 生成确定性 RTL
def build_verilog(configuration: ScalaDupToVectorConfig | None = None,
                  injected_dependencies: dict | None = None,
                  name: str = "ScalaDupToVector") -> str:
    """Emit the Amaranth representation with no implicit dependencies. / 输出。"""

    del injected_dependencies
    top = ScalaDupToVector(configuration)
    ports = [top.in_scalaData, top.in_vsew, top.out_vecData]
    return verilog.convert(top, name=name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print a default 128-bit instance for command-line checks / 打印默认实例
def main() -> None:
    print(build_verilog())


if __name__ == "__main__":
    main()
