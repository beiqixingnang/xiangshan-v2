"""ByteMaskTailGen computes active and agnostic vector byte masks.

按 vstart/vl/vma/vta 和 vsew 生成逐字节 active/agnostic 掩码。
"""

from __future__ import annotations

from dataclasses import dataclass

from amaranth import Cat, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# Public symbols / 公开符号:
#   - ByteMaskTailGenConfig, ByteMaskTailGen, build_verilog, main
# Real logic / 真实逻辑:
#   - Convert element indices to byte indices using vsew, construct body/tail
#     masks, select one 16-byte destination by vdIdx, and expand maskUsed by
#     element width. This mirrors ByteMaskTailGen.scala and MaskExtractor.scala.
#   / 将元素索引按 vsew 转为字节索引，生成 body/tail 掩码，按 vdIdx 选取
#     16 字节目标，并按元素宽度扩展 maskUsed，与 Scala 源一致。
# Status / 状态: PYTHON_PRESENT_UNVERIFIED (targeted phase-2 repair)
__all__ = ["ByteMaskTailGenConfig", "ByteMaskTailGen", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class ByteMaskTailGenConfig:
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
class ByteMaskTailGen(Elaboratable):
    """Generate the 128-bit destination masks / 生成 128 位目标掩码。"""

    # Create the explicit component ports / 创建显式组件端口
    def __init__(self, cfg: ByteMaskTailGenConfig | None = None):
        config = cfg or ByteMaskTailGenConfig()
        if config.vlen != 128:
            raise ValueError("ByteMaskTailGen currently requires vlen=128")
        self.cfg = config
        num_bytes = config.vlen // 8
        self.io_in_begin = Signal(8, name="io_in_begin")
        self.io_in_end = Signal(8, name="io_in_end")
        self.io_in_vma = Signal(name="io_in_vma")
        self.io_in_vta = Signal(name="io_in_vta")
        self.io_in_vsew = Signal(3, name="io_in_vsew")
        self.io_in_maskUsed = Signal(num_bytes, name="io_in_maskUsed")
        self.io_in_vdIdx = Signal(3, name="io_in_vdIdx")
        self.io_out_activeEn = Signal(num_bytes, name="io_out_activeEn")
        self.io_out_agnosticEn = Signal(num_bytes, name="io_out_agnosticEn")
        self.in_begin = self.io_in_begin
        self.in_end = self.io_in_end
        self.in_vma = self.io_in_vma
        self.in_vta = self.io_in_vta
        self.in_vsew = self.io_in_vsew
        self.in_maskUsed = self.io_in_maskUsed
        self.in_vdIdx = self.io_in_vdIdx
        self.out_activeEn = self.io_out_activeEn
        self.out_agnosticEn = self.io_out_agnosticEn

    # Elaborate byte mask and agnostic semantics / 展开字节掩码与不可知语义
    def elaborate(self, platform):
        m = Module()
        num_bytes = self.cfg.vlen // 8
        width = num_bytes * 8

        # Mux1H in the reference yields zero for unsupported vsew values;
        # shifts remain eight-bit values, so overflow is naturally truncated.
        start_bytes = Signal(8, name="startBytes")
        vl_bytes = Signal(8, name="vlBytes")
        m.d.comb += [
            start_bytes.eq(Mux(self.in_vsew == VSew.e8, self.in_begin,
                               Mux(self.in_vsew == VSew.e16, self.in_begin << 1,
                                   Mux(self.in_vsew == VSew.e32, self.in_begin << 2,
                                       Mux(self.in_vsew == VSew.e64, self.in_begin << 3, 0))))),
            vl_bytes.eq(Mux(self.in_vsew == VSew.e8, self.in_end,
                            Mux(self.in_vsew == VSew.e16, self.in_end << 1,
                                Mux(self.in_vsew == VSew.e32, self.in_end << 2,
                                    Mux(self.in_vsew == VSew.e64, self.in_end << 3, 0))))),
        ]

        body_mask = Signal(width, name="bodyMask")
        tail_mask = Signal(width, name="tailMask")
        # UIntToContLow0s(start) & UIntToContLow1s(vl): [start, vl).
        m.d.comb += body_mask.eq(Cat(*[
            (start_bytes <= byte_index) & (byte_index < vl_bytes)
            for byte_index in range(width)
        ]))
        m.d.comb += tail_mask.eq(Cat(*[
            vl_bytes <= byte_index for byte_index in range(width)
        ]))

        # Inline the MaskExtractor contract to keep this Build self-contained.
        mask_en = Signal(num_bytes, name="maskEn")
        e16 = Cat(*[self.in_maskUsed[index] for index in range(8)
                    for _ in range(2)])
        e32 = Cat(*[self.in_maskUsed[index] for index in range(4)
                    for _ in range(4)])
        e64 = Cat(*[self.in_maskUsed[index] for index in range(2)
                    for _ in range(8)])
        m.d.comb += mask_en.eq(Mux(self.in_vsew == VSew.e8, self.in_maskUsed,
                                   Mux(self.in_vsew == VSew.e16, e16,
                                       Mux(self.in_vsew == VSew.e32, e32,
                                           Mux(self.in_vsew == VSew.e64, e64, 0)))))

        selected_body = Signal(num_bytes, name="bodyEnInVd")
        selected_tail = Signal(num_bytes, name="tailEnInVd")
        selected_body_expr = body_mask[112:128]
        selected_tail_expr = tail_mask[112:128]
        for index in range(6, -1, -1):
            selected_body_expr = Mux(
                self.in_vdIdx == index,
                body_mask[index * num_bytes:(index + 1) * num_bytes],
                selected_body_expr,
            )
            selected_tail_expr = Mux(
                self.in_vdIdx == index,
                tail_mask[index * num_bytes:(index + 1) * num_bytes],
                selected_tail_expr,
            )
        m.d.comb += [selected_body.eq(selected_body_expr),
                     selected_tail.eq(selected_tail_expr)]

        valid_range = self.in_begin < self.in_end
        active = Mux(valid_range, selected_body & mask_en, 0)
        mask_agnostic = Mux(self.in_vma, (~mask_en) & selected_body, 0)
        tail_agnostic = Mux(self.in_vta, selected_tail, 0)
        m.d.comb += [
            self.out_activeEn.eq(active),
            self.out_agnosticEn.eq(Mux(valid_range,
                                       mask_agnostic | tail_agnostic, 0)),
        ]
        return m


# =============================================================================
# Public Adapter
# =============================================================================
# Generate deterministic Verilog / 生成确定性 Verilog
def build_verilog(configuration: ByteMaskTailGenConfig | None = None,
                  injected_dependencies: dict | None = None,
                  name: str = "ByteMaskTailGen") -> str:
    top = ByteMaskTailGen(configuration)
    ports = [top.io_in_begin, top.io_in_end, top.io_in_vma, top.io_in_vta,
             top.io_in_vsew, top.io_in_maskUsed, top.io_in_vdIdx,
             top.io_out_activeEn, top.io_out_agnosticEn]
    return verilog.convert(top, name=name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Emit the direct-entry Verilog / 输出直接入口 Verilog
def main() -> None:
    print(build_verilog())


if __name__ == "__main__":
    main()
