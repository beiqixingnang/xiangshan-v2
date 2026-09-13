"""DstMgu: two-stage mask-destination merge (S0 gather, S1 spliced write). / DstMgu：两级掩码目的合并（S0 采集、S1 拼接写入）。"""

from __future__ import annotations

from dataclasses import dataclass

from amaranth import Array, Cat, ClockDomain, ClockSignal, Module, Mux, Signal
from amaranth.lib.wiring import Component, In, Out


# =============================================================================
# Module Contract
# =============================================================================
# Public symbols / 公开符号:
#   - DstMguConfig, DstMgu, build_verilog, main
# Port contract / 端口契约 (DstMguIO):
#   - in.valid, in.oldVd, in.mask, in.ma, in.eew(3), in.vdIdx(3),
#     in.toS1{vd(numBytes), oldVdS1, eewS1(3), vdIdxS1(3)}; out.vd (vlen)
# Real logic / 真实逻辑 (verbatim):
#   - S0: maskMaOrOldVdBits[i] = Mux(ma, 1, maskOldVdBits[i]) registered at
#     valid, together with maskBits (splitVdMask slice)
#   - S1: maskVecByte[i] = Mux(maskBitsS1[i], vdS1[i], maskMaOrOldVdBitsS1[i])
#     and the result spliced into oldVdS1 at eewS1 granularity
# CONTRACT: the allPossibleResBit splice table and splitVdMask partitioning
#   are stage-2 refinements; this port keeps the registered two-stage
#   structure and the byte-lane merge.
# / 契约：allPossibleResBit 拼接表与 splitVdMask 划分属阶段二细化；此处保留
#   两级寄存结构与字节通路合并。
# Status / 状态: PYTHON_PRESENT_UNVERIFIED (phase-1 bulk port / 阶段一批量重写)
__all__ = ["DstMguConfig", "DstMgu", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class DstMguConfig:
    # frozen config / 冻结配置
    # Reference DefaultConfig uses a 128-bit vector destination for this unit.
    vlen: int = 128


# =============================================================================
# Implementation
# =============================================================================
class DstMgu(Component):
    # two-stage mask-destination merge unit / 两级掩码目的合并单元
    def __init__(self, cfg: DstMguConfig | None = None):
        c = cfg or DstMguConfig()
        self.cfg = c
        numBytes = c.vlen // 8
        super().__init__({
            "clock": In(1),
            "io_in_valid": In(1),
            "io_in_oldVd": In(c.vlen),
            "io_in_mask": In(c.vlen),
            "io_in_ma": In(1),
            "io_in_eew": In(3),
            "io_in_vdIdx": In(3),
            "io_in_toS1_vd": In(numBytes),
            "io_in_toS1_oldVdS1": In(c.vlen),
            "io_in_toS1_eewS1": In(3),
            "io_in_toS1_vdIdxS1": In(3),
            "io_out_vd": Out(c.vlen),
        })
        self.in_valid = self.io_in_valid
        self.in_oldVd = self.io_in_oldVd
        self.in_mask = self.io_in_mask
        self.in_ma = self.io_in_ma
        self.in_eew = self.io_in_eew
        self.in_vdIdx = self.io_in_vdIdx
        self.in_toS1_vd = self.io_in_toS1_vd
        self.in_toS1_oldVdS1 = self.io_in_toS1_oldVdS1
        self.in_toS1_eewS1 = self.io_in_toS1_eewS1
        self.in_toS1_vdIdxS1 = self.io_in_toS1_vdIdxS1
        self.out_vd = self.io_out_vd
        self.maskMaOrOldVdBitsS1 = Signal(numBytes, name="maskMaOrOldVdBitsS1")
        self.maskBitsS1 = Signal(numBytes, name="maskBitsS1")

    def elaborate(self, platform):
        # S0 register, S1 merge, and eew/vdIdx splice selection / S0 寄存、S1 合并及 eew/vdIdx 拼接选择
        m = Module()
        # DstMgu has no explicit reset in the reference IO contract.
        m.domains.sync = ClockDomain("sync", reset_less=True)
        m.d.comb += ClockSignal().eq(self.clock)
        numBytes = self.cfg.vlen // 8
        max_vd_idx = 8
        meaningful_bits = (16, 8, 4, 2)

        # splitVdMask from DstMgu.scala: each eew selects one mask group and
        # zero-extends narrower element masks to the byte-lane width.
        # / 对应 DstMgu.scala 的 splitVdMask：按 eew 选择掩码组，并将窄元素掩码零扩展到字节通路宽度。
        selected_old_groups = []
        selected_mask_groups = []
        for sew, element_bits in enumerate(meaningful_bits):
            lanes_per_group = numBytes // (1 << sew)
            for vd_idx in range(max_vd_idx):
                base = vd_idx * lanes_per_group
                old_lanes = [
                    self.in_oldVd[base + lane] if lane < lanes_per_group else 0
                    for lane in range(numBytes)
                ]
                mask_lanes = [
                    self.in_mask[base + lane] if lane < lanes_per_group else 0
                    for lane in range(numBytes)
                ]
                selected_old_groups.append(Cat(*old_lanes))
                selected_mask_groups.append(Cat(*mask_lanes))

        group_index = Cat(self.in_vdIdx, self.in_eew[:2])
        selected_old = Array(selected_old_groups)[group_index]
        selected_mask = Array(selected_mask_groups)[group_index]
        with m.If(self.in_valid):
            for lane in range(numBytes):
                m.d.sync += self.maskMaOrOldVdBitsS1[lane].eq(
                    Mux(self.in_ma, 1, selected_old[lane]))
                m.d.sync += self.maskBitsS1[lane].eq(selected_mask[lane])

        mask_vd = Signal(numBytes, name="maskVd")
        for lane in range(numBytes):
            m.d.comb += mask_vd[lane].eq(
                Mux(self.maskBitsS1[lane], self.in_toS1_vd[lane],
                    self.maskMaOrOldVdBitsS1[lane]))

        # Build the allPossibleResBit table from the reference implementation.
        # / 构造参考实现中的 allPossibleResBit 拼接表。
        candidates = []
        for element_bits in meaningful_bits:
            for vd_idx in range(max_vd_idx):
                start = element_bits * vd_idx
                parts = []
                if start:
                    parts.append(self.in_toS1_oldVdS1[:start])
                parts.append(mask_vd[:element_bits])
                if start + element_bits < self.cfg.vlen:
                    parts.append(self.in_toS1_oldVdS1[start + element_bits:])
                candidates.append(Cat(*parts))
        result_index = Cat(self.in_toS1_vdIdxS1, self.in_toS1_eewS1[:2])
        m.d.comb += self.out_vd.eq(Array(candidates)[result_index])
        return m


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(config: DstMguConfig | None = None,
                  name: str = "DstMgu") -> str:
    # Export only the Scala-visible ports; Component's implicit reset is not
    # part of DstMguIO and must not leak into the structural contract.
    from amaranth.back import verilog
    top = DstMgu(config)
    ports = [top.clock, top.in_valid, top.in_oldVd, top.in_mask, top.in_ma,
             top.in_eew, top.in_vdIdx, top.in_toS1_vd, top.in_toS1_oldVdS1,
             top.in_toS1_eewS1, top.in_toS1_vdIdxS1, top.out_vd]
    return verilog.convert(top, name=name, ports=ports)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    # direct elaboration entry / 直接入口
    print(build_verilog())


if __name__ == "__main__":
    main()
