"""Implement the V2 destination-mask merge folded into Mgu.scala.
实现折叠在 Mgu.scala 中的 V2 目的掩码合并逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from amaranth import Cat, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# V2 has no standalone DstMgu.scala: Mgu.scala computes maskOldVdBits and
# maskBits with splitVdMask, builds maskVd from the low mask element bits, then
# splices those bits into oldVd for dstMask operations.  This boundary exposes
# exactly that combinational closure; the V3 valid/S1 register interface is not
# carried forward. V2 没有独立 DstMgu.scala：Mgu.scala 用 splitVdMask 计算掩码，
# 从 maskVd 取低元素位并写回 oldVd。此边界只暴露该组合闭包，不保留 V3 的寄存器接口。
__all__ = ["DstMguConfig", "VSew", "DstMgu", "dst_mgu_model", "dst_mgu_observation", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class DstMguConfig:
    """Geometry of the folded V2 destination path. / 折叠 V2 目的通路几何。"""

    vlen: int = 128

    # Validate the V2 vector geometry. / 校验 V2 向量几何。
    def __post_init__(self) -> None:
        if self.vlen != 128:
            raise ValueError("V2 DstMgu closure requires vlen=128")


class VSew:
    """Canonical two-bit V2 element-width encodings. / V2 两位元素宽度编码。"""

    e8 = 0
    e16 = 1
    e32 = 2
    e64 = 3


# Return one V2 splitVdMask 16-bit chunk. / 返回 V2 splitVdMask 的一个 16 位块。
def split_mask_chunk(value: int, eew: int, vd_idx: int) -> int:
    if eew not in (0, 1, 2, 3):
        return 0
    span = 16 >> eew
    return (value >> ((vd_idx & 7) * span)) & ((1 << span) - 1)


# Compute the folded V2 destination-mask result in integer form. / 以整数形式计算折叠的 V2 目的掩码结果。
def dst_mgu_model(vd: int, old_vd: int, mask: int, ma: bool, eew: int, vd_idx: int) -> int:
    if eew not in (0, 1, 2, 3):
        return old_vd & ((1 << 128) - 1)
    old_mask = split_mask_chunk(old_vd, eew, vd_idx)
    mask_bits = split_mask_chunk(mask, eew, vd_idx)
    mask_vd = 0
    for lane in range(16):
        bit = ((vd >> lane) & 1) if ((mask_bits >> lane) & 1) else (1 if ma else ((old_mask >> lane) & 1))
        mask_vd |= bit << lane
    width = (16, 8, 4, 2)[eew]
    shift = width * (vd_idx & 7)
    field_mask = ((1 << width) - 1) << shift
    return ((old_vd & ((1 << 128) - 1)) & ~field_mask) | ((mask_vd & ((1 << width) - 1)) << shift)


def dst_mgu_observation(vd: int, old_vd: int, mask: int, ma: bool,
                        eew: int, vd_idx: int) -> dict[str, int]:
    """Return the merged destination and selected mask chunk. / 返回合并结果与掩码块。"""

    return {"result": dst_mgu_model(vd, old_vd, mask, ma, eew, vd_idx),
            "mask_chunk": split_mask_chunk(mask, eew, vd_idx)}


# =============================================================================
# Implementation
# =============================================================================
class DstMgu(Elaboratable):
    """Combinational folded destination-mask merge. / 折叠的组合式目的掩码合并。"""

    # Declare the source-level V2 Mgu destination inputs. / 声明 V2 Mgu 目的输入。
    def __init__(self, configuration: DstMguConfig | None = None):
        config = configuration or DstMguConfig()
        self.config = config
        self.in_vd = Signal(128, name="io_in_vd")
        self.in_oldVd = Signal(128, name="io_in_oldVd")
        self.in_mask = Signal(128, name="io_in_mask")
        self.in_info_ma = Signal(name="io_in_info_ma")
        self.in_info_eew = Signal(2, name="io_in_info_eew")
        self.in_info_vdIdx = Signal(3, name="io_in_info_vdIdx")
        self.out_vd = Signal(128, name="io_out_vd")

    # Elaborate splitVdMask, maskVd, and allPossibleResBit selection. / 展开 splitVdMask、maskVd 与结果选择。
    def elaborate(self, platform):
        del platform
        module = Module()
        old_chunks: list[object] = []
        mask_chunks: list[object] = []
        for eew in range(4):
            span = 16 >> eew
            old_values: list[object] = []
            mask_values: list[object] = []
            for vd_idx in range(8):
                base = vd_idx * span
                old_values.append(self.in_oldVd[base:base + span] if span == 16 else
                                  Cat(self.in_oldVd[base:base + span], Const(0, 16 - span)))
                mask_values.append(self.in_mask[base:base + span] if span == 16 else
                                   Cat(self.in_mask[base:base + span], Const(0, 16 - span)))
            old_selected: object = old_values[0]
            mask_selected: object = mask_values[0]
            for vd_idx in range(1, 8):
                old_selected = Mux(self.in_info_vdIdx == vd_idx, old_values[vd_idx], old_selected)
                mask_selected = Mux(self.in_info_vdIdx == vd_idx, mask_values[vd_idx], mask_selected)
            old_chunks.append(old_selected)
            mask_chunks.append(mask_selected)

        old_mask = Signal(16, name="maskOldVdBits")
        mask_bits = Signal(16, name="maskBits")
        old_expr = old_chunks[3]
        mask_expr = mask_chunks[3]
        for eew in range(2, -1, -1):
            old_expr = Mux(self.in_info_eew == eew, old_chunks[eew], old_expr)
            mask_expr = Mux(self.in_info_eew == eew, mask_chunks[eew], mask_expr)
        module.d.comb += [old_mask.eq(old_expr), mask_bits.eq(mask_expr)]

        mask_vd = Signal(16, name="maskVd")
        for lane in range(16):
            module.d.comb += cast(Any, mask_vd[lane]).eq(
                Mux(mask_bits[lane], self.in_vd[lane], Mux(self.in_info_ma, 1, old_mask[lane]))
            )

        candidates: list[list[object]] = []
        widths = (16, 8, 4, 2)
        for width in widths:
            row: list[object] = []
            for vd_idx in range(8):
                shift = width * vd_idx
                parts = []
                if shift:
                    parts.append(self.in_oldVd[:shift])
                parts.append(mask_vd[:width])
                if shift + width < 128:
                    parts.append(self.in_oldVd[shift + width:128])
                row.append(Cat(*parts))
            candidates.append(row)
        selected_row: object = candidates[3][0]
        for vd_idx in range(1, 8):
            selected_row = Mux(self.in_info_vdIdx == vd_idx, candidates[3][vd_idx], selected_row)
        for eew in range(2, -1, -1):
            row_expr: object = candidates[eew][0]
            for vd_idx in range(1, 8):
                row_expr = Mux(self.in_info_vdIdx == vd_idx, candidates[eew][vd_idx], row_expr)
            selected_row = Mux(self.in_info_eew == eew, row_expr, selected_row)
        module.d.comb += self.out_vd.eq(selected_row)
        return module


# =============================================================================
# Public Adapter
# =============================================================================
# Emit deterministic V2 closure Verilog. / 输出确定性的 V2 闭包 Verilog。
def build_verilog(configuration, injected_dependencies) -> str:
    del injected_dependencies
    top = DstMgu(configuration)
    return verilog.convert(
        top, name="DstMgu", ports=[top.in_vd, top.in_oldVd, top.in_mask,
        top.in_info_ma, top.in_info_eew, top.in_info_vdIdx, top.out_vd], emit_src=False,
    )


# =============================================================================
# Direct Entry
# =============================================================================
# Print the default folded closure helper. / 直接打印默认折叠闭包辅助器。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
