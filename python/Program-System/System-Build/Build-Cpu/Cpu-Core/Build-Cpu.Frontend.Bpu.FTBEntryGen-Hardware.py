"""V2 FTB entry update combinational closure.
昆明湖 V2 FTB 条目更新组合闭包。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, cast

from amaranth import Cat, Const, Elaboratable, Module, Mux, Signal


# Module Contract
# ---------------------------------------------------------------------------
# FTBEntryGen creates or updates one V2 FTB entry from predecode and redirect
# observations; all fields are combinational and preserve the locked equations.
# FTBEntryGen 根据预译码与重定向观测创建或更新一个 V2 FTB 条目；全部字段为组合逻辑，
# 保留锁定参考中的方程。
__all__ = ["FTBEntryGenConfig", "FTBEntryGen", "build_verilog", "main"]


# Configuration
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FTBEntryGenConfig:
    """Locked Kunminghu V2 FTB geometry. / 锁定昆明湖 V2 FTB 几何参数。"""

    vaddr_bits: int = 50
    predict_width: int = 16
    branch_offset_bits: int = 4
    branch_lower_bits: int = 12
    tail_lower_bits: int = 20
    target_status_bits: int = 2

    # Validate the fixed V2 specialization used by XSTop. / 校验 XSTop 使用的固定 V2 特化参数。
    def __post_init__(self) -> None:
        if self.vaddr_bits != 50:
            raise ValueError("Kunminghu V2 FTB uses 50-bit virtual addresses")
        if self.predict_width != 16:
            raise ValueError("Kunminghu V2 prediction width is 16")
        if self.branch_offset_bits != 4 or self.branch_lower_bits != 12:
            raise ValueError("unexpected V2 branch slot geometry")
        if self.tail_lower_bits != 20 or self.target_status_bits != 2:
            raise ValueError("unexpected V2 tail slot geometry")


# Implementation
# ---------------------------------------------------------------------------
class FTBEntryGen(Elaboratable):
    """Generate one FTB entry with V2 NewFtq semantics. / 按 V2 NewFtq 语义生成一个 FTB 条目。"""

    # Construct the exact extracted-reference port surface.
    # Construct the exact extracted-reference port surface. / 构造与提取参考完全一致的端口表面。
    def __init__(self, configuration: FTBEntryGenConfig | None = None) -> None:
        self.configuration = configuration or FTBEntryGenConfig()
        cfg = self.configuration

        self.start_addr = Signal(cfg.vaddr_bits, name="io_start_addr")
        self.old_is_call = Signal(name="io_old_entry_isCall")
        self.old_is_ret = Signal(name="io_old_entry_isRet")
        self.old_is_jalr = Signal(name="io_old_entry_isJalr")
        self.old_valid = Signal(name="io_old_entry_valid")
        self.old_br_offset = Signal(cfg.branch_offset_bits, name="io_old_entry_brSlots_0_offset")
        self.old_br_sharing = Signal(name="io_old_entry_brSlots_0_sharing")
        self.old_br_valid = Signal(name="io_old_entry_brSlots_0_valid")
        self.old_br_lower = Signal(cfg.branch_lower_bits, name="io_old_entry_brSlots_0_lower")
        self.old_br_tar_stat = Signal(cfg.target_status_bits, name="io_old_entry_brSlots_0_tarStat")
        self.old_tail_offset = Signal(cfg.branch_offset_bits, name="io_old_entry_tailSlot_offset")
        self.old_tail_sharing = Signal(name="io_old_entry_tailSlot_sharing")
        self.old_tail_valid = Signal(name="io_old_entry_tailSlot_valid")
        self.old_tail_lower = Signal(cfg.tail_lower_bits, name="io_old_entry_tailSlot_lower")
        self.old_tail_tar_stat = Signal(cfg.target_status_bits, name="io_old_entry_tailSlot_tarStat")
        self.old_pft_addr = Signal(cfg.branch_offset_bits, name="io_old_entry_pftAddr")
        self.old_carry = Signal(name="io_old_entry_carry")
        self.old_last_rvi_call = Signal(name="io_old_entry_last_may_be_rvi_call")
        self.old_strong_bias_0 = Signal(name="io_old_entry_strong_bias_0")
        self.old_strong_bias_1 = Signal(name="io_old_entry_strong_bias_1")

        self.pd_br_mask = [Signal(name=f"io_pd_brMask_{index}") for index in range(cfg.predict_width)]
        self.pd_jmp_info_valid = Signal(name="io_pd_jmpInfo_valid")
        self.pd_jmp_info_0 = Signal(name="io_pd_jmpInfo_bits_0")
        self.pd_jmp_info_1 = Signal(name="io_pd_jmpInfo_bits_1")
        self.pd_jmp_info_2 = Signal(name="io_pd_jmpInfo_bits_2")
        self.pd_jmp_offset = Signal(cfg.branch_offset_bits, name="io_pd_jmpOffset")
        self.pd_jal_target = Signal(cfg.vaddr_bits, name="io_pd_jalTarget")
        self.pd_rvc_mask = [Signal(name=f"io_pd_rvcMask_{index}") for index in range(cfg.predict_width)]

        self.cfi_index_valid = Signal(name="io_cfiIndex_valid")
        self.cfi_index_bits = Signal(cfg.branch_offset_bits, name="io_cfiIndex_bits")
        self.target = Signal(cfg.vaddr_bits, name="io_target")
        self.hit = Signal(name="io_hit")
        self.mispredict_vec = [Signal(name=f"io_mispredict_vec_{index}") for index in range(cfg.predict_width)]

        self.new_is_call = Signal(name="io_new_entry_isCall")
        self.new_is_ret = Signal(name="io_new_entry_isRet")
        self.new_is_jalr = Signal(name="io_new_entry_isJalr")
        self.new_valid = Signal(name="io_new_entry_valid")
        self.new_br_offset = Signal(cfg.branch_offset_bits, name="io_new_entry_brSlots_0_offset")
        self.new_br_sharing = Signal(name="io_new_entry_brSlots_0_sharing")
        self.new_br_valid = Signal(name="io_new_entry_brSlots_0_valid")
        self.new_br_lower = Signal(cfg.branch_lower_bits, name="io_new_entry_brSlots_0_lower")
        self.new_br_tar_stat = Signal(cfg.target_status_bits, name="io_new_entry_brSlots_0_tarStat")
        self.new_tail_offset = Signal(cfg.branch_offset_bits, name="io_new_entry_tailSlot_offset")
        self.new_tail_sharing = Signal(name="io_new_entry_tailSlot_sharing")
        self.new_tail_valid = Signal(name="io_new_entry_tailSlot_valid")
        self.new_tail_lower = Signal(cfg.tail_lower_bits, name="io_new_entry_tailSlot_lower")
        self.new_tail_tar_stat = Signal(cfg.target_status_bits, name="io_new_entry_tailSlot_tarStat")
        self.new_pft_addr = Signal(cfg.branch_offset_bits, name="io_new_entry_pftAddr")
        self.new_carry = Signal(name="io_new_entry_carry")
        self.new_last_rvi_call = Signal(name="io_new_entry_last_may_be_rvi_call")
        self.new_strong_bias_0 = Signal(name="io_new_entry_strong_bias_0")
        self.new_strong_bias_1 = Signal(name="io_new_entry_strong_bias_1")
        self.taken_mask_0 = Signal(name="io_taken_mask_0")
        self.taken_mask_1 = Signal(name="io_taken_mask_1")
        self.jmp_taken = Signal(name="io_jmp_taken")
        self.mispred_mask_0 = Signal(name="io_mispred_mask_0")
        self.mispred_mask_1 = Signal(name="io_mispred_mask_1")
        self.mispred_mask_2 = Signal(name="io_mispred_mask_2")
        self.is_old_entry = Signal(name="io_is_old_entry")
        # Internal-only mirror of the parent update gate: the locked XSTop extraction prunes
        # io_update_valid because NewFtq.scala gates it with io.toBpu.update.valid, so this net
        # stays off the exported boundary.
        # 仅内部镜像父级更新门控：锁定 XSTop 抽取剪除了 io_update_valid，因为 NewFtq.scala 用
        # io.toBpu.update.valid 门控它，故该网络不导出到公共边界。
        self.update_valid = Signal(name="io_update_valid")

    # Elaborate the V2 NewFtq FTB-entry equations as one combinational module.
    # Elaborate the V2 NewFtq FTB-entry equations as one combinational module. / 将 V2 NewFtq FTB 条目方程展开为一个组合逻辑模块。
    def elaborate(self, platform: Any) -> Module:
        del platform
        cfg = self.configuration
        # Amaranth's ``If``/``Elif`` context managers are generated at runtime;
        # this local annotation preserves their DSL use without suppression.
        module: Any = Module()

        br_mask = Cat(*self.pd_br_mask)
        rvc_mask = Cat(*self.pd_rvc_mask)
        mispredict = Cat(*self.mispredict_vec)
        cfi_is_br = cast(Any, br_mask).bit_select(self.cfi_index_bits, 1) & self.cfi_index_valid
        entry_has_jmp = self.pd_jmp_info_valid
        init_entry_is_jalr = entry_has_jmp & self.pd_jmp_info_0 & self.cfi_index_valid
        last_jmp_rvi = entry_has_jmp & (self.pd_jmp_offset == Const(15, cfg.branch_offset_bits)) & ~cast(Any, rvc_mask[15])
        cfi_is_jal = (self.cfi_index_bits == self.pd_jmp_offset) & entry_has_jmp & ~self.pd_jmp_info_0 & self.cfi_index_valid
        cfi_is_jalr = (self.cfi_index_bits == self.pd_jmp_offset) & init_entry_is_jalr
        del cfi_is_jal

        gen0 = Mux(cfi_is_jalr, self.target[1:cfg.vaddr_bits], self.pd_jal_target[1:cfg.vaddr_bits])
        start_low = self.start_addr[1:5]
        start_low_wide = Cat(start_low, Const(0, 1))
        jmp_step = Mux(cast(Any, rvc_mask).bit_select(self.pd_jmp_offset, 1), Const(1, 3), Const(2, 3))
        jmp_pft_wide = cast(Any, Cat(start_low, Const(0, 1))) + cast(Any, Cat(self.pd_jmp_offset, Const(0, 1))) + jmp_step
        jmp_pft = jmp_pft_wide[:5]

        br_recorded_0 = self.old_br_valid & (self.old_br_offset == self.cfi_index_bits)
        br_recorded_1 = self.old_tail_valid & (self.old_tail_offset == self.cfi_index_bits) & self.old_tail_sharing
        is_new_br = cfi_is_br & ~(br_recorded_0 | br_recorded_1)
        insert_0 = ~self.old_br_valid | (self.cfi_index_bits < self.old_br_offset)
        insert_1 = self.old_br_valid & (self.cfi_index_bits > self.old_br_offset) & (~self.old_tail_valid | (self.cfi_index_bits < self.old_tail_offset))
        insert_br_after = self.cfi_index_bits > self.old_br_offset
        gen3 = self.cfi_index_bits > self.old_tail_offset
        gen4 = gen3 | ~self.old_br_valid
        pft_need_change = is_new_br & self.old_br_valid & self.old_tail_valid
        new_pft_offset = Mux(insert_0 | insert_1, self.old_tail_offset, self.cfi_index_bits)
        old_entry_modified_carry = (cast(Any, Cat(start_low, Const(0, 1))) + cast(Any, Cat(new_pft_offset, Const(0, 1))))[:5]

        old_tail_hi_br = self.start_addr[13:50]
        old_tail_hi_jmp = self.start_addr[21:50]
        old_tail_hi_br_plus = (old_tail_hi_br + Const(1, 37))[:37]
        old_tail_hi_br_minus = (old_tail_hi_br - Const(1, 37))[:37]
        old_tail_hi_jmp_plus = (old_tail_hi_jmp + Const(1, 29))[:29]
        old_tail_hi_jmp_minus = (old_tail_hi_jmp - Const(1, 29))[:29]
        stat_is_ovf = self.old_tail_tar_stat == Const(1, cfg.target_status_bits)
        stat_is_udf = self.old_tail_tar_stat == Const(2, cfg.target_status_bits)
        stat_is_fit = self.old_tail_tar_stat == Const(0, cfg.target_status_bits)
        old_hi_br = Mux(stat_is_ovf, old_tail_hi_br_plus, Mux(stat_is_udf, old_tail_hi_br_minus, Mux(stat_is_fit, old_tail_hi_br, Const(0, 37))))
        old_hi_jmp = Mux(stat_is_ovf, old_tail_hi_jmp_plus, Mux(stat_is_udf, old_tail_hi_jmp_minus, Mux(stat_is_fit, old_tail_hi_jmp, Const(0, 29))))
        old_target_shared = Cat(Const(0, 1), self.old_tail_lower[:12], old_hi_br)
        old_target_jmp = Cat(Const(0, 1), self.old_tail_lower, old_hi_jmp)
        old_target = Mux(self.old_tail_sharing, old_target_shared, old_target_jmp)
        jalr_target_modified = cfi_is_jalr & (old_target != self.target) & ~self.old_tail_sharing

        strong_bias_modified_tail = self.old_tail_valid & self.old_tail_sharing
        old_strong_0 = Mux(
            br_recorded_0,
            self.old_strong_bias_0 & self.cfi_index_valid & self.old_br_valid & (self.cfi_index_bits == self.old_br_offset),
            ~br_recorded_1 & self.old_strong_bias_0,
        )
        old_strong_1 = (
            br_recorded_0
            | ~br_recorded_1
            | (self.cfi_index_valid & strong_bias_modified_tail & (self.cfi_index_bits == self.old_tail_offset))
        ) & self.old_strong_bias_1
        gen5 = ~is_new_br | ~pft_need_change
        gen6 = is_new_br & insert_0
        gen7 = is_new_br & pft_need_change

        br_target_hi = self.target[13:50]
        start_target_hi = self.start_addr[13:50]
        br_target_stat = Mux(cast(Any, br_target_hi) > cast(Any, start_target_hi), Const(1, 2), Mux(cast(Any, br_target_hi) < cast(Any, start_target_hi), Const(2, 2), Const(0, 2)))
        jmp_target_hi = self.target[21:50]
        start_jmp_hi = self.start_addr[21:50]
        jmp_target_stat = Mux(cast(Any, jmp_target_hi) > cast(Any, start_jmp_hi), Const(1, 2), Mux(cast(Any, jmp_target_hi) < cast(Any, start_jmp_hi), Const(2, 2), Const(0, 2)))
        init_target_hi = gen0[20:49]
        init_target_stat = Mux(cast(Any, init_target_hi) > cast(Any, start_jmp_hi), Const(1, 2), Mux(cast(Any, init_target_hi) < cast(Any, start_jmp_hi), Const(2, 2), Const(0, 2)))
        target_br_lower_wide = Cat(self.target[1:13], Const(0, 8))
        old_br_lower_wide = Cat(self.old_br_lower, Const(0, 8))

        new_br_offset = Mux(self.hit, Mux(gen6, self.cfi_index_bits, self.old_br_offset), Mux(cfi_is_br, self.cfi_index_bits, Const(0, 4)))
        new_br_valid = Mux(self.hit, gen6 | self.old_br_valid, cfi_is_br)
        new_br_sharing = self.hit & (~is_new_br | ~insert_0) & self.old_br_sharing
        new_br_lower = Mux(self.hit, Mux(gen6, self.target[1:13], self.old_br_lower), Mux(cfi_is_br, self.target[1:13], Const(0, 12)))
        new_br_tar_stat = Mux(self.hit, Mux(gen6, br_target_stat, self.old_br_tar_stat), Mux(cfi_is_br, br_target_stat, Const(0, 2)))

        new_tail_offset = Mux(
            self.hit,
            Mux(
                is_new_br,
                Mux(insert_1, self.cfi_index_bits, Mux(gen4, self.old_tail_offset, self.old_br_offset)),
                self.old_tail_offset,
            ),
            Mux(entry_has_jmp, self.pd_jmp_offset, Const(0, 4)),
        )
        new_tail_sharing = self.hit & Mux(
            is_new_br,
            insert_1 | (~gen3 & self.old_br_valid) | self.old_tail_sharing,
            ~jalr_target_modified & self.old_tail_sharing,
        )
        new_tail_valid = Mux(
            self.hit,
            Mux(is_new_br, insert_1 | Mux(gen4, self.old_tail_valid, self.old_br_valid), self.old_tail_valid),
            entry_has_jmp & ((entry_has_jmp & ~self.pd_jmp_info_0 & self.cfi_index_valid) | init_entry_is_jalr),
        )
        new_tail_lower = Mux(
            self.hit,
            Mux(
                is_new_br,
                Mux(insert_1, target_br_lower_wide, Mux(gen4, self.old_tail_lower, old_br_lower_wide)),
                Mux(jalr_target_modified, self.target[1:21], self.old_tail_lower),
            ),
            Mux(entry_has_jmp, gen0[:20], Const(0, 20)),
        )
        new_tail_tar_stat = Mux(
            self.hit,
            Mux(
                is_new_br,
                Mux(insert_1, br_target_stat, Mux(gen4, self.old_tail_tar_stat, self.old_br_tar_stat)),
                Mux(jalr_target_modified, jmp_target_stat, self.old_tail_tar_stat),
            ),
            Mux(entry_has_jmp, init_target_stat, Const(0, 2)),
        )
        new_pft_addr = Mux(
            self.hit,
            Mux(gen7, (start_low + new_pft_offset)[:4], self.old_pft_addr),
            Mux(entry_has_jmp & ~last_jmp_rvi, jmp_pft[:4], start_low),
        )
        new_carry = Mux(
            self.hit,
            Mux(gen7, old_entry_modified_carry[4], self.old_carry),
            ~(entry_has_jmp & ~last_jmp_rvi) | jmp_pft[4],
        )
        new_last_rvi_call = Mux(self.hit, gen5 & self.old_last_rvi_call, (self.pd_jmp_offset == Const(15, 4)) & ~cast(Any, rvc_mask[15]))
        new_strong_bias_0 = Mux(
            self.hit,
            Mux(is_new_br, insert_0 | (~insert_br_after & self.old_strong_bias_0), Mux(jalr_target_modified, ~jalr_target_modified & self.old_strong_bias_0, old_strong_0)),
            cfi_is_br,
        )
        new_strong_bias_1 = Mux(
            self.hit,
            Mux(is_new_br, insert_1 | (~gen3 & self.old_strong_bias_1), Mux(jalr_target_modified, ~jalr_target_modified & self.old_strong_bias_1, old_strong_1)),
            entry_has_jmp & init_entry_is_jalr,
        )

        tail_share_marker = new_tail_valid & new_tail_sharing
        module.d.comb += [
            self.update_valid.eq(self.new_valid),
            self.new_is_call.eq(Mux(self.hit, gen5 & self.old_is_call, entry_has_jmp & self.pd_jmp_info_1 & self.cfi_index_valid)),
            self.new_is_ret.eq(Mux(self.hit, gen5 & self.old_is_ret, entry_has_jmp & self.pd_jmp_info_2 & self.cfi_index_valid)),
            self.new_is_jalr.eq(Mux(self.hit, gen5 & self.old_is_jalr, init_entry_is_jalr)),
            self.new_valid.eq(Mux(~self.hit, Const(1, 1), self.old_valid)),
            self.new_br_offset.eq(new_br_offset),
            self.new_br_sharing.eq(new_br_sharing),
            self.new_br_valid.eq(new_br_valid),
            self.new_br_lower.eq(new_br_lower),
            self.new_br_tar_stat.eq(new_br_tar_stat),
            self.new_tail_offset.eq(new_tail_offset),
            self.new_tail_sharing.eq(new_tail_sharing),
            self.new_tail_valid.eq(new_tail_valid),
            self.new_tail_lower.eq(new_tail_lower),
            self.new_tail_tar_stat.eq(new_tail_tar_stat),
            self.new_pft_addr.eq(new_pft_addr),
            self.new_carry.eq(new_carry),
            self.new_last_rvi_call.eq(new_last_rvi_call),
            self.new_strong_bias_0.eq(new_strong_bias_0),
            self.new_strong_bias_1.eq(new_strong_bias_1),
            self.taken_mask_0.eq((self.cfi_index_bits == new_br_offset) & self.cfi_index_valid & new_br_valid),
            self.taken_mask_1.eq((self.cfi_index_bits == new_tail_offset) & self.cfi_index_valid & tail_share_marker),
            self.jmp_taken.eq(new_tail_valid & ~new_tail_sharing & (new_tail_offset == self.cfi_index_bits)),
            self.mispred_mask_0.eq(new_br_valid & cast(Any, mispredict).bit_select(new_br_offset, 1)),
            self.mispred_mask_1.eq(tail_share_marker & cast(Any, mispredict).bit_select(new_tail_offset, 1)),
            self.mispred_mask_2.eq(new_tail_valid & ~new_tail_sharing & cast(Any, mispredict).bit_select(self.pd_jmp_offset, 1)),
            self.is_old_entry.eq(
                self.hit
                & ~is_new_br
                & ~jalr_target_modified
                & ~(self.old_strong_bias_0 & self.old_br_valid & ~old_strong_0 | self.old_strong_bias_1 & strong_bias_modified_tail & ~old_strong_1)
            ),
        ]
        return module


# Public Adapter
# ---------------------------------------------------------------------------
# Emit deterministic RTL with the locked FTBEntryGen port names.
# 使用锁定 FTBEntryGen 端口名导出确定性 RTL。


# Build standalone SystemVerilog for the selected V2 specialization. / 为选定 V2 特化构建独立 SystemVerilog。
def build_verilog(configuration, injected_dependencies):
    """Return FTBEntryGen SystemVerilog. / 返回 FTBEntryGen SystemVerilog。"""

    del injected_dependencies
    from amaranth.back import verilog

    if isinstance(configuration, FTBEntryGenConfig):
        cfg = configuration
    elif isinstance(configuration, Mapping):
        cfg = FTBEntryGenConfig(**{key: value for key, value in configuration.items()
                                   if key in FTBEntryGenConfig.__dataclass_fields__})
    else:
        cfg = FTBEntryGenConfig()
    top = FTBEntryGen(cfg)
    inputs = [
        top.start_addr, top.old_is_call, top.old_is_ret, top.old_is_jalr, top.old_valid,
        top.old_br_offset, top.old_br_sharing, top.old_br_valid, top.old_br_lower, top.old_br_tar_stat,
        top.old_tail_offset, top.old_tail_sharing, top.old_tail_valid, top.old_tail_lower, top.old_tail_tar_stat,
        top.old_pft_addr, top.old_carry, top.old_last_rvi_call, top.old_strong_bias_0, top.old_strong_bias_1,
        *top.pd_br_mask, top.pd_jmp_info_valid, top.pd_jmp_info_0, top.pd_jmp_info_1, top.pd_jmp_info_2,
        top.pd_jmp_offset, top.pd_jal_target, *top.pd_rvc_mask,
        top.cfi_index_valid, top.cfi_index_bits, top.target, top.hit, *top.mispredict_vec,
    ]
    outputs = [
        top.new_is_call, top.new_is_ret, top.new_is_jalr, top.new_valid,
        top.new_br_offset, top.new_br_sharing, top.new_br_valid, top.new_br_lower, top.new_br_tar_stat,
        top.new_tail_offset, top.new_tail_sharing, top.new_tail_valid, top.new_tail_lower, top.new_tail_tar_stat,
        top.new_pft_addr, top.new_carry, top.new_last_rvi_call, top.new_strong_bias_0, top.new_strong_bias_1,
        top.taken_mask_0, top.taken_mask_1, top.jmp_taken,
        top.mispred_mask_0, top.mispred_mask_1, top.mispred_mask_2, top.is_old_entry,
    ]
    # ``top.update_valid`` stays an internal net: the locked reference declares no such port
    # because its parent gates the update with io.toBpu.update.valid.
    # ``top.update_valid`` 保持为内部网络：锁定参考未声明该端口，其父级用 io.toBpu.update.valid 门控更新。
    return verilog.convert(top, ports=inputs + outputs, name="FTBEntryGen")


# Direct Entry
# ---------------------------------------------------------------------------
# Direct command-line entry for deterministic RTL emission. / 用于确定性 RTL 导出的命令行入口。
def main() -> None:
    """Print FTBEntryGen RTL. / 打印 FTBEntryGen RTL。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
