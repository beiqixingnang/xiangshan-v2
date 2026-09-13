"""MaskExtractor expands vector mask bits according to element width.

按元素宽度复制向量掩码位，与锁定的 XiangShan MaskExtrator.scala 对齐。
"""

from __future__ import annotations

from dataclasses import dataclass

from amaranth import Cat, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# Public symbols / 公开符号:
#   - MaskExtractorConfig, MaskExtractor, build_verilog, main
# Real logic: e8 passes the byte mask through; e16/e32/e64 replicate each
# source bit by 2/4/8 positions. Unsupported vsew values produce zero, matching
# the Chisel Mux1H contract. The output width is vlen / 8 (numBytes), not vlen.
# / 真实逻辑：e8 直通字节掩码；e16/e32/e64 分别复制 2/4/8 位；不支持的
# vsew 输出零，与 Chisel Mux1H 合同一致。输出宽度为 vlen / 8（numBytes）。
# Status / 状态: PYTHON_PRESENT_UNVERIFIED (targeted phase-2 repair)
__all__ = ["MaskExtractorConfig", "MaskExtractor", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class MaskExtractorConfig:
    """Vector length configuration / 向量长度配置。"""

    vlen: int = 128


class VSew:
    """Closed element-width encodings / 封闭元素宽度编码。"""

    e8 = 0b000
    e16 = 0b001
    e32 = 0b010
    e64 = 0b011


# =============================================================================
# Implementation
# =============================================================================
class MaskExtractor(Elaboratable):
    """Replicate mask bits for the selected element width / 按元素宽度复制掩码。"""

    # Create the fixed mask ports / 创建固定掩码端口
    def __init__(self, cfg: MaskExtractorConfig | None = None):
        config = cfg or MaskExtractorConfig()
        if config.vlen <= 0 or config.vlen % 8:
            raise ValueError("vlen must be a positive multiple of 8")
        self.config = config
        self.num_bytes = config.vlen // 8
        self.in_mask = Signal(self.num_bytes, name="me_mask")
        self.in_vsew = Signal(3, name="me_vsew")
        self.out_mask = Signal(self.num_bytes, name="me_out")

    # Elaborate mask replication logic / 展开掩码复制逻辑
    def elaborate(self, platform):
        m = Module()
        mask = self.in_mask
        width = self.num_bytes
        # Chisel's VecInit(mask.asBools.flatMap(...)).asUInt is LSB-first in
        # the generated RTL. Replication is truncated to the fixed output.
        e8 = mask
        e16 = Cat(*[mask.bit_select(index, 1)
                    for index in range(width // 2) for _ in range(2)])
        e32 = Cat(*[mask.bit_select(index, 1)
                    for index in range(width // 4) for _ in range(4)])
        e64 = Cat(*[mask.bit_select(index, 1)
                    for index in range(width // 8) for _ in range(8)])
        zero = Const(0, width)
        selected = Mux(
            self.in_vsew == VSew.e8,
            e8,
            Mux(
                self.in_vsew == VSew.e16,
                e16,
                Mux(self.in_vsew == VSew.e32, e32,
                    Mux(self.in_vsew == VSew.e64, e64, zero)),
            ),
        )
        m.d.comb += self.out_mask.eq(selected)
        return m


# =============================================================================
# Public Adapter
# =============================================================================
# Generate deterministic Verilog / 生成确定性 Verilog
def build_verilog(configuration: MaskExtractorConfig | None = None,
                  injected_dependencies: dict | None = None,
                  name: str = "MaskExtractor") -> str:
    config = configuration or MaskExtractorConfig()
    top = MaskExtractor(config)
    return verilog.convert(top, name=name, ports=[top.in_mask, top.in_vsew,
                                                   top.out_mask], emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Emit direct-entry Verilog / 输出直接入口 Verilog
def main() -> None:
    print(build_verilog())


if __name__ == "__main__":
    main()
