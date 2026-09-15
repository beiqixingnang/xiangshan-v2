"""Represent the V2 Mgu mask-generation sub-closure under its legacy name.
以旧名称表示 V2 Mgu 的掩码生成子闭包。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from amaranth import Cat, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# V2 removed NewMgu.scala and folds this behavior into Mgu.scala.  This local
# surface therefore exposes only the integrated mask-generation inputs: realEw
# is info.vsew when isIndexedVls is set, otherwise info.eew; VecDataToMaskDataVec
# selects one mask chunk by vdIdx; ByteMaskTailGen then applies vstart/vl/vma/vta.
# V2 已删除 NewMgu.scala，并将行为折叠进 Mgu.scala。本地表面仅暴露集成掩码生成
# 输入：isIndexedVls 时 realEw=info.vsew，否则为 info.eew；按 vdIdx 选择掩码块，
# 再由 ByteMaskTailGen 应用 vstart/vl/vma/vta。Reference mode is source/parent
# closure because XSTop contains Mgu but no standalone NewMgu module.
__all__ = ["NewMguConfig", "VSew", "NewMgu", "new_mgu_model", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class NewMguConfig:
    """Geometry of the V2 Mgu mask sub-closure. / V2 Mgu 掩码子闭包几何。"""

    vlen: int = 128
    index_width: int = 8

    # Validate the fixed V2 vector geometry. / 校验固定 V2 向量几何。
    def __post_init__(self) -> None:
        if self.vlen != 128 or self.index_width != 8:
            raise ValueError("V2 NewMgu closure requires vlen=128 and index_width=8")


class VSew:
    """Canonical two-bit V2 element-width encodings. / V2 两位元素宽度编码。"""

    e8 = 0
    e16 = 1
    e32 = 2
    e64 = 3


# Compute the integrated V2 mask-generation result in integer form. / 以整数形式计算集成 V2 掩码生成结果。
def new_mgu_model(
    mask: int,
    ta: bool,
    ma: bool,
    vstart: int,
    vl: int,
    eew: int,
    vsew: int,
    vd_idx: int,
    is_indexed_vls: bool,
) -> tuple[int, int]:
    real_eew = vsew if is_indexed_vls else eew
    if real_eew not in (0, 1, 2, 3):
        return (0, 0)
    span = 16 >> real_eew
    chunk = (mask >> ((vd_idx & 7) * span)) & ((1 << span) - 1)
    start_bytes = ((vstart & 0xFF) << real_eew) & 0xFF
    end_bytes = ((vl & 0xFF) << real_eew) & 0xFF
    active = 0
    agnostic = 0
    base = (vd_idx & 7) * 16
    for lane in range(16):
        position = base + lane
        body = start_bytes <= position < end_bytes
        tail = position >= end_bytes
        selected = (chunk >> (lane >> real_eew)) & 1
        if vstart < vl and body and selected:
            active |= 1 << lane
        if vstart < vl and ((ma and body and not selected) or (ta and tail)):
            agnostic |= 1 << lane
    return active, agnostic


# =============================================================================
# Implementation
# =============================================================================
class NewMgu(Elaboratable):
    """Generate active/agnostic enables for the V2 Mgu closure. / 生成 V2 Mgu 使能。"""

    # Declare the flattened subset of V2 MguIO. / 声明 V2 MguIO 的扁平子集。
    def __init__(self, configuration: NewMguConfig | None = None):
        config = configuration or NewMguConfig()
        self.config = config
        self.in_mask = Signal(128, name="io_in_mask")
        self.in_info_ta = Signal(name="io_in_info_ta")
        self.in_info_ma = Signal(name="io_in_info_ma")
        self.in_info_vstart = Signal(8, name="io_in_info_vstart")
        self.in_info_vl = Signal(8, name="io_in_info_vl")
        self.in_info_eew = Signal(2, name="io_in_info_eew")
        self.in_info_vsew = Signal(2, name="io_in_info_vsew")
        self.in_info_vdIdx = Signal(3, name="io_in_info_vdIdx")
        self.in_isIndexedVls = Signal(name="io_in_isIndexedVls")
        self.out_activeEn = Signal(16, name="io_out_activeEn")
        self.out_agnosticEn = Signal(16, name="io_out_agnosticEn")

    # Elaborate realEw, mask chunking, and byte-range policy. / 展开 realEw、掩码分块与字节范围策略。
    def elaborate(self, platform):
        del platform
        module = Module()
        real_eew = Signal(2, name="realEw")
        module.d.comb += real_eew.eq(Mux(self.in_isIndexedVls, self.in_info_vsew, self.in_info_eew))

        chunks: list[object] = []
        for eew in range(4):
            span = 16 >> eew
            values: list[object] = []
            for vd_idx in range(8):
                base = vd_idx * span
                values.append(self.in_mask[base:base + span] if span == 16 else
                              Cat(self.in_mask[base:base + span], Const(0, 16 - span)))
            selected: object = values[0]
            for vd_idx in range(1, 8):
                selected = Mux(self.in_info_vdIdx == vd_idx, values[vd_idx], selected)
            chunks.append(selected)
        mask_used = Signal(16, name="maskUsed")
        mask_expr = chunks[3]
        for eew in range(2, -1, -1):
            mask_expr = Mux(real_eew == eew, chunks[eew], mask_expr)
        module.d.comb += mask_used.eq(mask_expr)

        start_bytes = Signal(8, name="startBytes")
        end_bytes = Signal(8, name="vlBytes")
        module.d.comb += [
            start_bytes.eq(self.in_info_vstart << real_eew),
            end_bytes.eq(self.in_info_vl << real_eew),
        ]
        body = Signal(128, name="bodyEn")
        tail = Signal(128, name="tailEn")
        for index in range(128):
            module.d.comb += [
                cast(Any, body[index]).eq((start_bytes <= index) & (index < end_bytes)),
                cast(Any, tail[index]).eq(end_bytes <= index),
            ]
        body_selected = body[:16]
        tail_selected = tail[:16]
        for vd_idx in range(1, 8):
            body_selected = Mux(self.in_info_vdIdx == vd_idx, body[vd_idx * 16:(vd_idx + 1) * 16], body_selected)
            tail_selected = Mux(self.in_info_vdIdx == vd_idx, tail[vd_idx * 16:(vd_idx + 1) * 16], tail_selected)

        expanded_arms = [
            mask_used,
            Cat(*[mask_used[index] for index in range(8) for _ in range(2)]),
            Cat(*[mask_used[index] for index in range(4) for _ in range(4)]),
            Cat(*[mask_used[index] for index in range(2) for _ in range(8)]),
        ]
        expanded = Signal(16, name="maskEn")
        expanded_expr = expanded_arms[3]
        for eew in range(2, -1, -1):
            expanded_expr = Mux(real_eew == eew, expanded_arms[eew], expanded_expr)
        module.d.comb += expanded.eq(expanded_expr)
        valid_range = self.in_info_vstart < self.in_info_vl
        active = Mux(valid_range, body_selected & expanded, Const(0, 16))
        agnostic = Mux(
            valid_range,
            ((~expanded) & body_selected & Mux(self.in_info_ma, Const(0xFFFF, 16), Const(0, 16)))
            | (tail_selected & Mux(self.in_info_ta, Const(0xFFFF, 16), Const(0, 16))),
            Const(0, 16),
        )
        module.d.comb += [self.out_activeEn.eq(active), self.out_agnosticEn.eq(agnostic)]
        return module


# =============================================================================
# Public Adapter
# =============================================================================
# Emit deterministic V2 closure Verilog. / 输出确定性的 V2 闭包 Verilog。
def build_verilog(configuration, injected_dependencies) -> str:
    del injected_dependencies
    top = NewMgu(configuration)
    return verilog.convert(
        top, name="NewMgu", ports=[top.in_mask, top.in_info_ta, top.in_info_ma,
        top.in_info_vstart, top.in_info_vl, top.in_info_eew, top.in_info_vsew,
        top.in_info_vdIdx, top.in_isIndexedVls, top.out_activeEn,
        top.out_agnosticEn], emit_src=False,
    )


# =============================================================================
# Direct Entry
# =============================================================================
# Print the default closure helper. / 直接打印默认闭包辅助器。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
