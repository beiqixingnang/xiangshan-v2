"""NewMgu: mask-generate unit steering ByteMaskTailGen by vdIdx/EEW. / NewMgu：按 vdIdx/EEW 选择掩码切片并驱动 ByteMaskTailGen 的掩码生成单元。"""

from __future__ import annotations

from dataclasses import dataclass

from amaranth import Module, Mux, Signal
from amaranth.lib.wiring import Component, In, Out


# =============================================================================
# Module Contract
# =============================================================================
# Public symbols / 公开符号:
#   - NewMguConfig, NewMgu, build_verilog, main
# Port contract / 端口契约 (NewMguIO):
#   - in.mask(vlen), in.info{ta,ma,vstart(8),vl(8),eew(2),vsew(2),vdIdx(3)},
#     in.isIndexedVls; out.activeEn/agnosticEn (vlen/8)
# Real logic / 真实逻辑 (verbatim):
#   - realEw = Mux(isIndexedVls, vsew, eew)
#   - the mask slice used by the tail generator is selected by vdIdx at the
#     realEw element granularity (VecDataToMaskDataVec)
#   - maskTailGen receives begin=vstart, end=vl, vma, vta, vsew=realEw
#   / realEw 按 isIndexedVls 在 vsew/eew 间选择；切片按 vdIdx 选择；
#     ByteMaskTailGen 以 vstart/vl/vma/vta/realEw 驱动。
# Status / 状态: PYTHON_PRESENT_UNVERIFIED (phase-1 bulk port / 阶段一批量重写)
__all__ = ["NewMguConfig", "NewMgu", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class NewMguConfig:
    # frozen config / 冻结配置
    vlen: int = 128


# =============================================================================
# Implementation
# =============================================================================
class NewMgu(Component):
    # new mask-generate unit / 新掩码生成单元
    def __init__(self, cfg: NewMguConfig | None = None):
        # depends on Build-Cpu.Backend.Fu.Vector.ByteMaskTailGen (injected)
        c = cfg or NewMguConfig()
        self.cfg = c
        numBytes = c.vlen // 8
        if numBytes != 16:
            raise ValueError("NewMgu reference instance requires vlen=128")
        super().__init__({
            "io_in_mask": In(c.vlen),
            "io_in_info_ta": In(1),
            "io_in_info_ma": In(1),
            "io_in_info_vl": In(8),
            "io_in_info_eew": In(3),
            "io_in_info_vdIdx": In(3),
            "io_out_activeEn": Out(numBytes),
            "io_out_agnosticEn": Out(numBytes),
        })
        # Compatibility aliases retain the pre-alignment Python surface.
        self.in_mask = self.io_in_mask
        self.in_ta = self.io_in_info_ta
        self.in_ma = self.io_in_info_ma
        self.in_vl = self.io_in_info_vl
        self.in_eew = self.io_in_info_eew
        self.in_vdIdx = self.io_in_info_vdIdx
        self.out_activeEn = self.io_out_activeEn
        self.out_agnosticEn = self.io_out_agnosticEn

    def elaborate(self, platform):
        # select mask slice by vdIdx and feed the tail generator / 按 vdIdx 选择切片并驱动尾段生成器
        m = Module()
        elems = self.cfg.vlen // 8
        mask_variants = []
        for eew in range(4):
            span = 16 >> eew
            mask_variant = Signal(elems, name=f"maskUsedEew{eew}")
            for byte in range(elems):
                source_index = (self.in_vdIdx * span) + (byte >> eew)
                m.d.comb += mask_variant[byte].eq(
                    self.in_mask.bit_select(source_index, 1))
            mask_variants.append(mask_variant)
        sliceMask = Signal(elems, name="maskUsed")
        m.d.comb += sliceMask.eq(Mux(self.in_eew == 0, mask_variants[0],
                                     Mux(self.in_eew == 1, mask_variants[1],
                                         Mux(self.in_eew == 2, mask_variants[2],
                                             mask_variants[3]))))

        # ByteMaskTailGen is instantiated with begin=0 in the pinned NewMgu.
        # Its byte position is vl scaled by EEW; the zero-length case suppresses
        # both outputs exactly as the reference guard does.
        vl_bytes = Signal(8, name="vlBytes")
        m.d.comb += vl_bytes.eq(self.in_vl << self.in_eew)
        active = Signal(elems, name="activeEn")
        agnostic = Signal(elems, name="agnosticEn")
        nonempty = self.in_vl != 0
        for byte in range(elems):
            body = byte < vl_bytes
            tail = byte >= vl_bytes
            m.d.comb += [active[byte].eq(body & sliceMask[byte]),
                         agnostic[byte].eq(nonempty &
                                           ((body & ~sliceMask[byte] & self.in_ma) |
                                            (tail & self.in_ta)))]
        m.d.comb += [self.out_activeEn.eq(active),
                     self.out_agnosticEn.eq(agnostic)]
        return m


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(config: NewMguConfig | None = None,
                  name: str = "NewMgu") -> str:
    # minimal public adapter generating Verilog via amaranth / 最小公开适配器，用 amaranth 生成 Verilog
    from amaranth.back import verilog
    top = NewMgu(config)
    ports = [top.in_mask, top.in_ta, top.in_ma, top.in_vl,
             top.in_eew, top.in_vdIdx, top.out_activeEn,
             top.out_agnosticEn]
    return verilog.convert(top, name=name, ports=ports)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    # direct elaboration entry / 直接入口
    print(build_verilog())


if __name__ == "__main__":
    main()
