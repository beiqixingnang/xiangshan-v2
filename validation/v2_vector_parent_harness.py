"""Compose the reduced V2 VldMergeUnit parent closure.
组合 V2 精简 VldMergeUnit 父级闭包。

This validation-only hardware surface deliberately stays under ``.agents``.
It binds the existing V2 ``NewMgu`` leaf through an injected dependency and
keeps the parent register/flush contract visible at the locked XSTop boundary.
The companion collision lane is supplied by the existing ``WbArbiter`` leaf.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amaranth import Cat, ClockDomain, ClockSignal, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# V2 VldMergeUnit captures one vector writeback payload, suppresses a payload
# killed by the redirect ROB pointer, and emits it one clock later.  VldMgu
# supplies active/agnostic byte enables; the V2 VldMergeUnit wiring uses the
# captured vector as both vd and oldVd, so an agnostic byte becomes 8'hff and
# every other byte remains the captured value.  ``vlWen`` bypasses that merge.
# V2 VldMergeUnit 捕获一个向量写回载荷，按 redirect ROB 指针抑制被杀载荷，
# 并在一个时钟后输出。VldMgu 提供 active/agnostic 字节使能；V2 接线将捕获
# 向量同时作为 vd 与 oldVd，因此 agnostic 字节变为 8'hff，其余保持原值；
# ``vlWen`` 直接旁路合并结果。
__all__ = [
    "VldMergeUnitParentConfig",
    "VldMergeUnitParent",
    "vld_merge_model",
    "build_verilog",
]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class VldMergeUnitParentConfig:
    """Fixed geometry at the V2 locked parent boundary. / V2 锁定父边界的固定几何。"""

    vlen: int = 128
    rob_value_width: int = 8
    pdest_width: int = 7

    # Validate the finite V2 parent geometry. / 校验有限的 V2 父级几何。
    def __post_init__(self) -> None:
        if self.vlen != 128:
            raise ValueError("V2 VldMergeUnit uses VLEN=128")
        if self.rob_value_width != 8:
            raise ValueError("V2 VldMergeUnit ROB value width is 8")
        if self.pdest_width != 7:
            raise ValueError("V2 VldMergeUnit physical-destination width is 7")


# =============================================================================
# Implementation
# =============================================================================
# Return the V2 circular ROB ordering relation used by RobPtr.needFlush.
# 返回 RobPtr.needFlush 使用的 V2 环形 ROB 顺序关系。
def rob_is_after(value: int, flag: int, flush_value: int, flush_flag: int) -> bool:
    return bool((flag & 1) ^ (flush_flag & 1) ^ int((value & 0xFF) > (flush_value & 0xFF)))


# Return the exact redirect kill predicate from RobPtr.needFlush.
# 返回 RobPtr.needFlush 的精确 redirect kill 谓词。
def rob_need_flush(
    value: int,
    flag: int,
    flush_valid: bool,
    flush_value: int,
    flush_flag: int,
    flush_level: int,
) -> bool:
    if not flush_valid:
        return False
    same = (value & 0xFF) == (flush_value & 0xFF) and (flag & 1) == (flush_flag & 1)
    flush_itself = bool(flush_level & 1) and same
    return flush_itself or rob_is_after(value, flag, flush_value, flush_flag)


# Compute the V2 parent output for one cycle, including its registered valid.
# 计算包含寄存有效位的单周期 V2 父级输出。
def vld_merge_model(
    data: int,
    pdest: int,
    rob_flag: int,
    rob_value: int,
    vec_wen: bool,
    v0_wen: bool,
    vl_wen: bool,
    vma: bool,
    vta: bool,
    vsew: int,
    vm: bool,
    vstart: int,
    vmask: int,
    vl: int,
    veew: int,
    vd_idx: int,
    is_indexed: bool,
    is_masked: bool,
    flush_valid: bool,
    flush_flag: int,
    flush_value: int,
    flush_level: int,
    writeback_valid: bool,
) -> tuple[int, int, int, int, int, int]:
    """Model one captured V2 payload and its observable output.
    建模一个捕获的 V2 载荷及其可观察输出。

    The caller supplies the previous cycle's register state separately; this
    function models the newly captured payload and is used by the direct
    checker to build an executable transaction oracle.
    """

    killed = rob_need_flush(rob_value, rob_flag, flush_valid, flush_value, flush_flag, flush_level)
    valid = int(bool(writeback_valid) and not killed)
    merged = data & ((1 << 128) - 1)
    if not vl_wen and vstart < vl:
        real_eew = vsew if is_indexed else veew
        if real_eew in (0, 1, 2, 3):
            span = 16 >> real_eew
            selected_chunk = ((0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF if vm else vmask) >>
                              ((vd_idx & 7) * span)) & ((1 << span) - 1)
            start_bytes = ((vstart & 0xFF) << real_eew) & 0xFF
            end_bytes = ((vl & 0xFF) << real_eew) & 0xFF
            base = (vd_idx & 7) * 16
            for lane in range(16):
                position = base + lane
                body = start_bytes <= position < end_bytes
                tail = position >= end_bytes
                selected = (selected_chunk >> (lane >> real_eew)) & 1
                agnostic = (vma and body and not selected) or (vta or bool(is_masked)) and tail
                if agnostic:
                    merged = (merged & ~(0xFF << (lane * 8))) | (0xFF << (lane * 8))
    return (
        valid,
        merged,
        pdest & 0x7F,
        int(bool(vec_wen)),
        int(bool(v0_wen)),
        int(bool(vl_wen)),
    )


class VldMergeUnitParent(Elaboratable):
    """Reduced sequential V2 VldMergeUnit boundary. / 精简顺序 V2 VldMergeUnit 边界。"""

    # Declare the flattened locked-XSTop parent ports. / 声明锁定 XSTop 父级扁平端口。
    def __init__(self, configuration: VldMergeUnitParentConfig | None = None,
                 injected_dependencies: dict[str, Any] | None = None):
        self.config = configuration or VldMergeUnitParentConfig()
        dependencies = injected_dependencies or {}
        self.mask_generator = dependencies.get("mask_generator")
        if self.mask_generator is None:
            raise ValueError("mask_generator dependency must be injected from the V2 NewMgu leaf")

        self.flush_valid = Signal(name="io_flush_valid")
        self.flush_rob_flag = Signal(name="io_flush_bits_robIdx_flag")
        self.flush_rob_value = Signal(8, name="io_flush_bits_robIdx_value")
        self.flush_level = Signal(name="io_flush_bits_level")
        self.writeback_valid = Signal(name="io_writeback_valid")
        self.writeback_data = Signal(128, name="io_writeback_bits_data_0")
        self.writeback_pdest = Signal(7, name="io_writeback_bits_pdest")
        self.writeback_rob_flag = Signal(name="io_writeback_bits_robIdx_flag")
        self.writeback_rob_value = Signal(8, name="io_writeback_bits_robIdx_value")
        self.writeback_vec_wen = Signal(name="io_writeback_bits_vecWen")
        self.writeback_v0_wen = Signal(name="io_writeback_bits_v0Wen")
        self.writeback_vl_wen = Signal(name="io_writeback_bits_vlWen")
        self.writeback_vma = Signal(name="io_writeback_bits_vls_vpu_vma")
        self.writeback_vta = Signal(name="io_writeback_bits_vls_vpu_vta")
        self.writeback_vsew = Signal(2, name="io_writeback_bits_vls_vpu_vsew")
        self.writeback_vm = Signal(name="io_writeback_bits_vls_vpu_vm")
        self.writeback_vstart = Signal(8, name="io_writeback_bits_vls_vpu_vstart")
        self.writeback_vmask = Signal(128, name="io_writeback_bits_vls_vpu_vmask")
        self.writeback_vl = Signal(8, name="io_writeback_bits_vls_vpu_vl")
        self.writeback_veew = Signal(2, name="io_writeback_bits_vls_vpu_veew")
        self.writeback_vd_idx = Signal(3, name="io_writeback_bits_vls_vdIdxInField")
        self.writeback_is_indexed = Signal(name="io_writeback_bits_vls_isIndexed")
        self.writeback_is_masked = Signal(name="io_writeback_bits_vls_isMasked")
        self.out_valid = Signal(name="io_writebackAfterMerge_valid")
        self.out_data = Signal(128, name="io_writebackAfterMerge_bits_data_0")
        self.out_pdest = Signal(7, name="io_writebackAfterMerge_bits_pdest")
        self.out_vec_wen = Signal(name="io_writebackAfterMerge_bits_vecWen")
        self.out_v0_wen = Signal(name="io_writebackAfterMerge_bits_v0Wen")
        self.out_vl_wen = Signal(name="io_writebackAfterMerge_bits_vlWen")

    # Elaborate parent registers, redirect kill, and injected mask child.
    # 展开父级寄存器、redirect kill 以及注入的掩码子模块。
    def elaborate(self, platform):
        del platform
        if self.mask_generator is None:
            raise ValueError("mask_generator dependency is required")
        module = Module()
        module.domains.clock = ClockDomain("clock", reset_less=True)
        wb_valid = Signal(name="wbReg_valid")
        wb_data = Signal(128, name="wbReg_bits_data_0")
        wb_pdest = Signal(7, name="wbReg_bits_pdest")
        wb_rob_flag = Signal(name="wbReg_bits_robIdx_flag")
        wb_rob_value = Signal(8, name="wbReg_bits_robIdx_value")
        wb_vec_wen = Signal(name="wbReg_bits_vecWen")
        wb_v0_wen = Signal(name="wbReg_bits_v0Wen")
        wb_vl_wen = Signal(name="wbReg_bits_vlWen")
        wb_vma = Signal(name="wbReg_bits_vls_vpu_vma")
        wb_vta = Signal(name="wbReg_bits_vls_vpu_vta")
        wb_vsew = Signal(2, name="wbReg_bits_vls_vpu_vsew")
        wb_vm = Signal(name="wbReg_bits_vls_vpu_vm")
        wb_vstart = Signal(8, name="wbReg_bits_vls_vpu_vstart")
        wb_vmask = Signal(128, name="wbReg_bits_vls_vpu_vmask")
        wb_vl = Signal(8, name="wbReg_bits_vls_vpu_vl")
        wb_veew = Signal(2, name="wbReg_bits_vls_vpu_veew")
        wb_vd_idx = Signal(3, name="wbReg_bits_vls_vdIdxInField")
        wb_is_indexed = Signal(name="wbReg_bits_vls_isIndexed")
        wb_is_masked = Signal(name="wbReg_bits_vls_isMasked")

        same_ptr = (Cat(self.writeback_rob_flag, self.writeback_rob_value) ==
                    Cat(self.flush_rob_flag, self.flush_rob_value))
        is_after = (self.writeback_rob_flag ^ self.flush_rob_flag ^
                    (self.writeback_rob_value > self.flush_rob_value))
        need_flush = self.flush_valid & ((self.flush_level & same_ptr) | is_after)
        wb_fire = self.writeback_valid
        module.d.clock += wb_valid.eq(wb_fire & ~need_flush)
        with module.If(wb_fire):
            module.d.clock += [
                wb_data.eq(self.writeback_data), wb_pdest.eq(self.writeback_pdest),
                wb_rob_flag.eq(self.writeback_rob_flag), wb_rob_value.eq(self.writeback_rob_value),
                wb_vec_wen.eq(self.writeback_vec_wen), wb_v0_wen.eq(self.writeback_v0_wen),
                wb_vl_wen.eq(self.writeback_vl_wen), wb_vma.eq(self.writeback_vma),
                wb_vta.eq(self.writeback_vta), wb_vsew.eq(self.writeback_vsew),
                wb_vm.eq(self.writeback_vm), wb_vstart.eq(self.writeback_vstart),
                wb_vmask.eq(self.writeback_vmask), wb_vl.eq(self.writeback_vl),
                wb_veew.eq(self.writeback_veew), wb_vd_idx.eq(self.writeback_vd_idx),
                wb_is_indexed.eq(self.writeback_is_indexed), wb_is_masked.eq(self.writeback_is_masked),
            ]

        child = self.mask_generator
        module.submodules.mask_generator = child
        module.d.comb += [
            child.in_mask.eq(Mux(wb_vm, Const((1 << 128) - 1, 128), wb_vmask)),
            child.in_info_ta.eq(wb_is_masked | wb_vta),
            child.in_info_ma.eq(wb_vma),
            child.in_info_vstart.eq(wb_vstart),
            child.in_info_vl.eq(wb_vl),
            child.in_info_eew.eq(wb_veew),
            child.in_info_vsew.eq(wb_vsew),
            child.in_info_vdIdx.eq(wb_vd_idx),
            child.in_isIndexedVls.eq(wb_is_indexed),
        ]
        merged_bytes: list[Any] = []
        for lane in range(16):
            old_byte = wb_data[lane * 8:(lane + 1) * 8]
            merged_bytes.append(Mux(child.out_activeEn[lane], old_byte,
                                    Mux(child.out_agnosticEn[lane], Const(0xFF, 8), old_byte)))
        merged = Cat(*merged_bytes)
        module.d.comb += [
            self.out_valid.eq(wb_valid),
            self.out_data.eq(Mux(wb_vl_wen, wb_data, merged)),
            self.out_pdest.eq(wb_pdest),
            self.out_vec_wen.eq(wb_vec_wen),
            self.out_v0_wen.eq(wb_v0_wen),
            self.out_vl_wen.eq(wb_vl_wen),
        ]
        return module


# Emit deterministic Verilog for the injected V2 parent closure.
# 为注入的 V2 父级闭包输出确定性 Verilog。
def build_verilog(configuration, injected_dependencies):
    dependencies = injected_dependencies if isinstance(injected_dependencies, dict) else {}
    top = VldMergeUnitParent(configuration, dependencies)
    ports = [
        ClockSignal("clock"),
        top.flush_valid, top.flush_rob_flag, top.flush_rob_value, top.flush_level,
        top.writeback_valid, top.writeback_data, top.writeback_pdest,
        top.writeback_rob_flag, top.writeback_rob_value, top.writeback_vec_wen,
        top.writeback_v0_wen, top.writeback_vl_wen, top.writeback_vma,
        top.writeback_vta, top.writeback_vsew, top.writeback_vm, top.writeback_vstart,
        top.writeback_vmask, top.writeback_vl, top.writeback_veew,
        top.writeback_vd_idx, top.writeback_is_indexed, top.writeback_is_masked,
        top.out_valid, top.out_data, top.out_pdest, top.out_vec_wen,
        top.out_v0_wen, top.out_vl_wen,
    ]
    return verilog.convert(top, name="VldMergeUnitParent", ports=ports, emit_src=False)


# The parent harness is imported by the validation runner, not executed as a
# product module.  / 父级 harness 由验证运行器导入，不作为产品模块执行。
