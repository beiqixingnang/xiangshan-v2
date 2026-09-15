"""UHSC Kunminghu V2 Frontend parent closure.
昆明湖 V2 前端父级闭包的 UHSC Amaranth 实现。

The locked V2 ``Frontend`` is a 371-port integration boundary.  This file
keeps the parent-visible control and transaction equations executable while
leaving large child families (ICache, InstrUncache, IFU, BPU, FTQ, IBuffer,
and ITLB) behind explicit constructor injection points.  The reduced surface
is intentional: it is a bounded parent closure, not a claim that every
Diplomacy/SRAM port has already been rewritten.
"""

from __future__ import annotations
# pyright: reportAttributeAccessIssue=false, reportGeneralTypeIssues=false, reportOperatorIssue=false

from dataclasses import dataclass
from typing import Any

from amaranth import Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# Frontend.scala delays redirect/fence/WFI controls, joins ICache and
# InstrUncache safety, pipelines ICache errors, and exposes the backend CF
# vector plus frontend information.  The parent below preserves those
# equations and names every unfinished child as an injected dependency.
# Frontend.scala 延迟 redirect/fence/WFI 控制，合并 ICache 与 InstrUncache
# 安全状态，流水化 ICache 错误，并输出后端 CF 向量及前端信息；本父级保留这些
# 方程，并将未完成子级全部声明为显式注入依赖。
__all__ = [
    "FrontendTopConfig",
    "FrontendChildBoundary",
    "FrontendRvcBoundary",
    "FrontendBpuBoundary",
    "FrontendParent",
    "UHSCTop",
    "Frontend",
    "frontend_port_specs",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class FrontendTopConfig:
    """Finite V2 geometry for the parent-visible Frontend boundary. / V2 前端父边界的有限几何。"""

    vaddr_bits: int = 50
    paddr_bits: int = 48
    ftq_idx_bits: int = 6
    ftq_offset_bits: int = 4
    fetch_width: int = 6
    instr_bits: int = 32
    error_bits: int = 48
    perf_bits: int = 6
    perf_count: int = 8
    soft_prefetch_count: int = 3

    # Validate the widths used by the locked Kunminghu V2 Frontend. / 校验锁定昆明湖 V2 前端使用的位宽。
    def __post_init__(self) -> None:
        if self.vaddr_bits < self.paddr_bits or self.paddr_bits < 8:
            raise ValueError("V2 virtual/physical address widths are inconsistent")
        if self.ftq_idx_bits < 1 or self.ftq_offset_bits < 1:
            raise ValueError("FTQ widths must be positive")
        if self.fetch_width != 6:
            raise ValueError("Kunminghu V2 Frontend backend width is six")
        if self.instr_bits != 32:
            raise ValueError("the V2 instruction width is 32")
        if self.error_bits < 1 or self.perf_bits < 1 or self.perf_count < 1:
            raise ValueError("error/performance widths must be positive")
        if self.soft_prefetch_count != 3:
            raise ValueError("V2 Frontend exposes three soft-prefetch lanes")


# Return the exact locked V2 Frontend port order. / 返回锁定 V2 Frontend 的精确端口顺序。
def frontend_port_specs() -> tuple[tuple[str, str, int], ...]:
    """Describe all 371 generated Frontend ports. / 描述生成的全部 371 个 Frontend 端口。"""

    specs: list[tuple[str, str, int]] = [
        ("clock", "input", 1), ("reset", "input", 1),
        ("auto_inner_icache_ctrlUnitOpt_in_a_ready", "output", 1),
        ("auto_inner_icache_ctrlUnitOpt_in_a_valid", "input", 1),
        ("auto_inner_icache_ctrlUnitOpt_in_a_bits_opcode", "input", 4),
        ("auto_inner_icache_ctrlUnitOpt_in_a_bits_size", "input", 2),
        ("auto_inner_icache_ctrlUnitOpt_in_a_bits_source", "input", 5),
        ("auto_inner_icache_ctrlUnitOpt_in_a_bits_address", "input", 30),
        ("auto_inner_icache_ctrlUnitOpt_in_a_bits_mask", "input", 8),
        ("auto_inner_icache_ctrlUnitOpt_in_a_bits_data", "input", 64),
        ("auto_inner_icache_ctrlUnitOpt_in_d_ready", "input", 1),
        ("auto_inner_icache_ctrlUnitOpt_in_d_valid", "output", 1),
        ("auto_inner_icache_ctrlUnitOpt_in_d_bits_opcode", "output", 4),
        ("auto_inner_icache_ctrlUnitOpt_in_d_bits_size", "output", 2),
        ("auto_inner_icache_ctrlUnitOpt_in_d_bits_source", "output", 5),
        ("auto_inner_icache_ctrlUnitOpt_in_d_bits_data", "output", 64),
        ("auto_inner_icache_client_out_a_ready", "input", 1),
        ("auto_inner_icache_client_out_a_valid", "output", 1),
        ("auto_inner_icache_client_out_a_bits_source", "output", 4),
        ("auto_inner_icache_client_out_a_bits_address", "output", 48),
        ("auto_inner_icache_client_out_d_valid", "input", 1),
        ("auto_inner_icache_client_out_d_bits_opcode", "input", 4),
        ("auto_inner_icache_client_out_d_bits_size", "input", 3),
        ("auto_inner_icache_client_out_d_bits_source", "input", 4),
        ("auto_inner_icache_client_out_d_bits_data", "input", 256),
        ("auto_inner_icache_client_out_d_bits_corrupt", "input", 1),
        ("auto_inner_instrUncache_client_out_a_ready", "input", 1),
        ("auto_inner_instrUncache_client_out_a_valid", "output", 1),
        ("auto_inner_instrUncache_client_out_a_bits_address", "output", 48),
        ("auto_inner_instrUncache_client_out_d_valid", "input", 1),
        ("auto_inner_instrUncache_client_out_d_bits_source", "input", 1),
        ("auto_inner_instrUncache_client_out_d_bits_data", "input", 64),
        ("auto_inner_instrUncache_client_out_d_bits_corrupt", "input", 1),
        ("io_reset_vector", "input", 48), ("io_fencei", "input", 1),
        ("io_ptw_req_0_ready", "input", 1), ("io_ptw_req_0_valid", "output", 1),
        ("io_ptw_req_0_bits_vpn", "output", 38), ("io_ptw_req_0_bits_s2xlate", "output", 2),
        ("io_ptw_resp_ready", "output", 1), ("io_ptw_resp_valid", "input", 1),
        ("io_ptw_resp_bits_s2xlate", "input", 2), ("io_ptw_resp_bits_s1_entry_tag", "input", 35),
        ("io_ptw_resp_bits_s1_entry_asid", "input", 16), ("io_ptw_resp_bits_s1_entry_vmid", "input", 14),
        ("io_ptw_resp_bits_s1_entry_n", "input", 1), ("io_ptw_resp_bits_s1_entry_pbmt", "input", 2),
        ("io_ptw_resp_bits_s1_entry_perm_d", "input", 1), ("io_ptw_resp_bits_s1_entry_perm_a", "input", 1),
        ("io_ptw_resp_bits_s1_entry_perm_g", "input", 1), ("io_ptw_resp_bits_s1_entry_perm_u", "input", 1),
        ("io_ptw_resp_bits_s1_entry_perm_x", "input", 1), ("io_ptw_resp_bits_s1_entry_perm_w", "input", 1),
        ("io_ptw_resp_bits_s1_entry_perm_r", "input", 1), ("io_ptw_resp_bits_s1_entry_level", "input", 2),
        ("io_ptw_resp_bits_s1_entry_v", "input", 1), ("io_ptw_resp_bits_s1_entry_ppn", "input", 41),
        ("io_ptw_resp_bits_s1_addr_low", "input", 3),
    ]
    specs.extend((f"io_ptw_resp_bits_s1_ppn_low_{index}", "input", 3) for index in range(8))
    specs.extend((f"io_ptw_resp_bits_s1_valididx_{index}", "input", 1) for index in range(8))
    specs.extend((f"io_ptw_resp_bits_s1_pteidx_{index}", "input", 1) for index in range(8))
    specs.extend([
        ("io_ptw_resp_bits_s1_pf", "input", 1), ("io_ptw_resp_bits_s1_af", "input", 1),
        ("io_ptw_resp_bits_s2_entry_tag", "input", 38), ("io_ptw_resp_bits_s2_entry_vmid", "input", 14),
        ("io_ptw_resp_bits_s2_entry_n", "input", 1), ("io_ptw_resp_bits_s2_entry_pbmt", "input", 2),
        ("io_ptw_resp_bits_s2_entry_ppn", "input", 38), ("io_ptw_resp_bits_s2_entry_perm_d", "input", 1),
        ("io_ptw_resp_bits_s2_entry_perm_a", "input", 1), ("io_ptw_resp_bits_s2_entry_perm_g", "input", 1),
        ("io_ptw_resp_bits_s2_entry_perm_u", "input", 1), ("io_ptw_resp_bits_s2_entry_perm_x", "input", 1),
        ("io_ptw_resp_bits_s2_entry_perm_w", "input", 1), ("io_ptw_resp_bits_s2_entry_perm_r", "input", 1),
        ("io_ptw_resp_bits_s2_entry_level", "input", 2), ("io_ptw_resp_bits_s2_gpf", "input", 1),
        ("io_ptw_resp_bits_s2_gaf", "input", 1),
    ])
    cf_fields = (
        ("valid", 1), ("bits_instr", 32), ("bits_exceptionVec_1", 1),
        ("bits_exceptionVec_2", 1), ("bits_exceptionVec_12", 1), ("bits_exceptionVec_20", 1),
        ("bits_backendException", 1), ("bits_satpFlushFirstFetchFault", 1),
        ("bits_trigger", 4), ("bits_pd_isRVC", 1), ("bits_pd_brType", 2),
        ("bits_pred_taken", 1), ("bits_crossPageIPFFix", 1), ("bits_ftqPtr_flag", 1),
        ("bits_ftqPtr_value", 6), ("bits_ftqOffset", 4), ("bits_isLastInFtqEntry", 1),
    )
    for lane in range(6):
        specs.extend((f"io_backend_cfVec_{lane}_{suffix}", "output", width) for suffix, width in cf_fields)
    specs.extend([
        ("io_backend_fromFtq_pc_mem_wen", "output", 1), ("io_backend_fromFtq_pc_mem_waddr", "output", 6),
        ("io_backend_fromFtq_pc_mem_wdata_startAddr", "output", 50),
        ("io_backend_fromFtq_newest_entry_en", "output", 1), ("io_backend_fromFtq_newest_entry_target", "output", 50),
        ("io_backend_fromFtq_newest_entry_ptr_value", "output", 6),
        ("io_backend_fromIfu_gpaddrMem_wen", "output", 1), ("io_backend_fromIfu_gpaddrMem_waddr", "output", 6),
        ("io_backend_fromIfu_gpaddrMem_wdata_gpaddr", "output", 56),
        ("io_backend_fromIfu_gpaddrMem_wdata_isForVSnonLeafPTE", "output", 1),
    ])
    rob_fields = (("valid", 1), ("bits_commitType", 3), ("bits_ftqIdx_flag", 1),
                  ("bits_ftqIdx_value", 6), ("bits_ftqOffset", 4))
    for lane in range(8):
        specs.extend((f"io_backend_toFtq_rob_commits_{lane}_{suffix}", "input", width)
                      for suffix, width in rob_fields)
    specs.extend([
        ("io_backend_toFtq_redirect_valid", "input", 1),
        ("io_backend_toFtq_redirect_bits_ftqIdx_flag", "input", 1),
        ("io_backend_toFtq_redirect_bits_ftqIdx_value", "input", 6),
        ("io_backend_toFtq_redirect_bits_ftqOffset", "input", 4),
        ("io_backend_toFtq_redirect_bits_level", "input", 1),
        ("io_backend_toFtq_redirect_bits_cfiUpdate_pc", "input", 50),
        ("io_backend_toFtq_redirect_bits_cfiUpdate_target", "input", 50),
        ("io_backend_toFtq_redirect_bits_cfiUpdate_taken", "input", 1),
        ("io_backend_toFtq_redirect_bits_cfiUpdate_isMisPred", "input", 1),
        ("io_backend_toFtq_redirect_bits_cfiUpdate_backendIGPF", "input", 1),
        ("io_backend_toFtq_redirect_bits_cfiUpdate_backendIPF", "input", 1),
        ("io_backend_toFtq_redirect_bits_cfiUpdate_backendIAF", "input", 1),
        ("io_backend_toFtq_redirect_bits_satpFlush", "input", 1),
        ("io_backend_toFtq_ftqIdxAhead_0_valid", "input", 1),
        ("io_backend_toFtq_ftqIdxAhead_0_bits_value", "input", 6),
        ("io_backend_toFtq_ftqIdxSelOH_bits", "input", 3),
        ("io_backend_canAccept", "input", 1), ("io_backend_wfi_wfiReq", "input", 1),
        ("io_backend_wfi_wfiSafe", "output", 1),
    ])
    for lane in range(3):
        specs.extend([(f"io_softPrefetch_{lane}_valid", "input", 1),
                       (f"io_softPrefetch_{lane}_bits_vaddr", "input", 50)])
    specs.extend([
        ("io_sfence_valid", "input", 1), ("io_sfence_bits_rs1", "input", 1),
        ("io_sfence_bits_rs2", "input", 1), ("io_sfence_bits_addr", "input", 50),
        ("io_sfence_bits_id", "input", 16), ("io_sfence_bits_flushPipe", "input", 1),
        ("io_sfence_bits_hv", "input", 1), ("io_sfence_bits_hg", "input", 1),
        ("io_tlbCsr_satp_mode", "input", 4), ("io_tlbCsr_satp_asid", "input", 16),
        ("io_tlbCsr_satp_changed", "input", 1), ("io_tlbCsr_vsatp_mode", "input", 4),
        ("io_tlbCsr_vsatp_asid", "input", 16), ("io_tlbCsr_vsatp_changed", "input", 1),
        ("io_tlbCsr_hgatp_mode", "input", 4), ("io_tlbCsr_hgatp_vmid", "input", 16),
        ("io_tlbCsr_hgatp_changed", "input", 1), ("io_tlbCsr_mbmc_BME", "input", 1),
        ("io_tlbCsr_mbmc_CMODE", "input", 1), ("io_tlbCsr_priv_mxr", "input", 1),
        ("io_tlbCsr_priv_sum", "input", 1), ("io_tlbCsr_priv_vmxr", "input", 1),
        ("io_tlbCsr_priv_vsum", "input", 1), ("io_tlbCsr_priv_virt", "input", 1),
        ("io_tlbCsr_priv_virt_changed", "input", 1), ("io_tlbCsr_priv_spvp", "input", 1),
        ("io_tlbCsr_priv_imode", "input", 2), ("io_tlbCsr_priv_dmode", "input", 2),
        ("io_tlbCsr_priv_debug", "input", 1), ("io_tlbCsr_pmm_mseccfg", "input", 2),
        ("io_tlbCsr_pmm_menvcfg", "input", 2), ("io_tlbCsr_pmm_henvcfg", "input", 2),
        ("io_tlbCsr_pmm_hstatus", "input", 2), ("io_tlbCsr_pmm_senvcfg", "input", 2),
        ("io_csrCtrl_pf_ctrl_l1I_pf_enable", "input", 1), ("io_csrCtrl_bp_ctrl_ubtb_enable", "input", 1),
        ("io_csrCtrl_bp_ctrl_btb_enable", "input", 1), ("io_csrCtrl_bp_ctrl_tage_enable", "input", 1),
        ("io_csrCtrl_bp_ctrl_sc_enable", "input", 1), ("io_csrCtrl_bp_ctrl_ras_enable", "input", 1),
        ("io_csrCtrl_sbuffer_timeout", "input", 22), ("io_csrCtrl_ldld_vio_check_enable", "input", 1),
        ("io_csrCtrl_cache_error_enable", "input", 1), ("io_csrCtrl_hd_misalign_st_enable", "input", 1),
        ("io_csrCtrl_hd_misalign_ld_enable", "input", 1), ("io_csrCtrl_distribute_csr_w_valid", "input", 1),
        ("io_csrCtrl_distribute_csr_w_bits_addr", "input", 12), ("io_csrCtrl_distribute_csr_w_bits_data", "input", 64),
        ("io_csrCtrl_frontend_trigger_tUpdate_valid", "input", 1), ("io_csrCtrl_frontend_trigger_tUpdate_bits_addr", "input", 2),
        ("io_csrCtrl_frontend_trigger_tUpdate_bits_tdata_matchType", "input", 2),
        ("io_csrCtrl_frontend_trigger_tUpdate_bits_tdata_select", "input", 1),
        ("io_csrCtrl_frontend_trigger_tUpdate_bits_tdata_action", "input", 4),
        ("io_csrCtrl_frontend_trigger_tUpdate_bits_tdata_chain", "input", 1),
        ("io_csrCtrl_frontend_trigger_tUpdate_bits_tdata_tdata2", "input", 64),
    ])
    specs.extend((f"io_csrCtrl_frontend_trigger_tEnableVec_{index}", "input", 1) for index in range(4))
    specs.extend([
        ("io_csrCtrl_frontend_trigger_debugMode", "input", 1),
        ("io_csrCtrl_frontend_trigger_triggerCanRaiseBpExp", "input", 1),
        ("io_csrCtrl_mem_trigger_tUpdate_valid", "input", 1), ("io_csrCtrl_mem_trigger_tUpdate_bits_addr", "input", 2),
        ("io_csrCtrl_mem_trigger_tUpdate_bits_tdata_matchType", "input", 2),
        ("io_csrCtrl_mem_trigger_tUpdate_bits_tdata_select", "input", 1),
        ("io_csrCtrl_mem_trigger_tUpdate_bits_tdata_action", "input", 4),
        ("io_csrCtrl_mem_trigger_tUpdate_bits_tdata_chain", "input", 1),
        ("io_csrCtrl_mem_trigger_tUpdate_bits_tdata_store", "input", 1),
        ("io_csrCtrl_mem_trigger_tUpdate_bits_tdata_load", "input", 1),
        ("io_csrCtrl_mem_trigger_tUpdate_bits_tdata_tdata2", "input", 64),
    ])
    specs.extend((f"io_csrCtrl_mem_trigger_tEnableVec_{index}", "input", 1) for index in range(4))
    specs.extend([
        ("io_csrCtrl_mem_trigger_debugMode", "input", 1),
        ("io_csrCtrl_mem_trigger_triggerCanRaiseBpExp", "input", 1),
        ("io_csrCtrl_fsIsOff", "input", 1), ("io_error_ecc_error_valid", "output", 1),
        ("io_error_ecc_error_bits", "output", 48), ("io_resetInFrontend", "output", 1),
        ("io_dft_ram_hold", "input", 1), ("io_dft_ram_bypass", "input", 1),
        ("io_dft_ram_bp_clken", "input", 1), ("io_dft_ram_aux_clk", "input", 1),
        ("io_dft_ram_aux_ckbp", "input", 1), ("io_dft_ram_mcp_hold", "input", 1),
        ("io_dft_cgen", "input", 1),
    ])
    specs.extend((f"io_perf_{index}_value", "output", 6) for index in range(8))
    if len(specs) != 371:
        raise AssertionError(f"locked Frontend port inventory has {len(specs)} entries")
    return tuple(specs)


# =============================================================================
# Implementation
# =============================================================================
class FrontendChildBoundary(Elaboratable):
    """Small injectable child contract for ICache-like frontend units. / 可注入 ICache 类前端子级合同。"""

    # Construct a named child request/status surface. / 构造带名称的子级请求与状态表面。
    def __init__(self, configuration: FrontendTopConfig | None = None,
                 child_name: str = "child") -> None:
        self.configuration = configuration or FrontendTopConfig()
        cfg = self.configuration
        self.child_name = child_name
        self.clock = Signal(name=f"{child_name}_clock")
        self.reset = Signal(name=f"{child_name}_reset")
        self.flush = Signal(name=f"{child_name}_flush")
        self.fencei = Signal(name=f"{child_name}_fencei")
        self.wfi_req = Signal(name=f"{child_name}_wfiReq")
        self.req_valid = Signal(name=f"{child_name}_req_valid")
        self.req_ready = Signal(name=f"{child_name}_req_ready")
        self.req_addr = Signal(cfg.vaddr_bits, name=f"{child_name}_req_addr")
        self.req_nextline = Signal(cfg.vaddr_bits, name=f"{child_name}_req_nextline")
        self.resp_valid = Signal(name=f"{child_name}_resp_valid")
        self.resp_data = Signal(cfg.instr_bits * 16, name=f"{child_name}_resp_data")
        self.resp_error = Signal(name=f"{child_name}_resp_error")
        self.wfi_safe = Signal(name=f"{child_name}_wfiSafe")
        self.error_valid = Signal(name=f"{child_name}_error_valid")
        self.error_bits = Signal(cfg.error_bits, name=f"{child_name}_error_bits")
        self.ibuffer_full = Signal(name=f"{child_name}_ibufferFull")
        self.bp_right = Signal(cfg.instr_bits, name=f"{child_name}_bpRight")
        self.bp_wrong = Signal(cfg.instr_bits, name=f"{child_name}_bpWrong")
        self.cf_valid = Signal(cfg.fetch_width, name=f"{child_name}_cf_valid")
        self.cf_instr = Signal(cfg.fetch_width * cfg.instr_bits, name=f"{child_name}_cf_instr")
        self.cf_pc = Signal(cfg.fetch_width * cfg.vaddr_bits, name=f"{child_name}_cf_pc")
        self.cf_is_rvc = Signal(cfg.fetch_width, name=f"{child_name}_cf_isRVC")
        self.cf_pred_taken = Signal(cfg.fetch_width, name=f"{child_name}_cf_predTaken")
        self.cf_exception = Signal(cfg.fetch_width, name=f"{child_name}_cf_exception")

    # Elaborate a deterministic one-entry child fallback for standalone use. / 为独立使用展开确定性单项子级回退。
    def elaborate(self, platform: Any) -> Module:
        del platform
        cfg = self.configuration
        module = Module()
        domain = ClockDomain(f"{self.child_name}_sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        setattr(module.domains, f"{self.child_name}_sync", domain)
        busy = Signal(name=f"{self.child_name}_busy")
        saved_addr = Signal(cfg.vaddr_bits, name=f"{self.child_name}_saved_addr")
        request_fire = self.req_valid & self.req_ready
        module.d.comb += [
            self.req_ready.eq(~busy & ~self.flush & ~self.fencei),
            self.resp_valid.eq(busy & ~self.flush),
            self.resp_data.eq(0),
            self.resp_error.eq(0),
            self.wfi_safe.eq(~busy),
            self.error_valid.eq(0),
            self.error_bits.eq(0),
            self.ibuffer_full.eq(0),
            self.bp_right.eq(0),
            self.bp_wrong.eq(0),
            self.cf_valid.eq(0),
            self.cf_instr.eq(0),
            self.cf_pc.eq(0),
            self.cf_is_rvc.eq(0),
            self.cf_pred_taken.eq(0),
            self.cf_exception.eq(0),
        ]
        with module.If(self.reset | self.flush | self.fencei):
            module.d[f"{self.child_name}_sync"] += busy.eq(0)
        with module.Elif(request_fire):
            module.d[f"{self.child_name}_sync"] += [busy.eq(1), saved_addr.eq(self.req_addr)]
        with module.Elif(busy):
            module.d[f"{self.child_name}_sync"] += busy.eq(0)
        return module


class FrontendRvcBoundary(Elaboratable):
    """Fallback RVC child matching the validated decoder surface. / 与已验证解码器表面匹配的 RVC 回退子级。"""

    # Construct a compact decoder contract that accepts an injected full RVC
    # implementation without a sibling import. / 构造可替换完整 RVC 实现的紧凑解码器合同。
    def __init__(self, configuration: FrontendTopConfig | None = None) -> None:
        del configuration
        self.clock = Signal(name="rvc_clock")
        self.reset = Signal(name="rvc_reset")
        self.in_ = Signal(32, name="io_in")
        self.fsIsOff = Signal(name="io_fsIsOff")
        self.out_bits = Signal(32, name="io_out_bits")
        self.out_rd = Signal(5, name="io_out_rd")
        self.out_rs1 = Signal(5, name="io_out_rs1")
        self.out_rs2 = Signal(5, name="io_out_rs2")
        self.out_rs3 = Signal(5, name="io_out_rs3")
        self.ill = Signal(name="io_ill")

    # Keep a deterministic legal pass-through for standalone parent use. / 独立父级使用时保持确定性合法直通。
    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        module.d.comb += [self.out_bits.eq(self.in_), self.out_rd.eq(self.in_[7:12]),
                          self.out_rs1.eq(self.in_[15:20]), self.out_rs2.eq(self.in_[20:25]),
                          self.out_rs3.eq(self.in_[27:32]), self.ill.eq(0)]
        return module


class FrontendBpuBoundary(Elaboratable):
    """Fallback BPU child with a sequential-PC prediction. / 提供顺序 PC 预测的 BPU 回退子级。"""

    # Construct the parent-visible BPU control and prediction ports. / 构造父级可见的 BPU 控制与预测端口。
    def __init__(self, configuration: FrontendTopConfig | None = None) -> None:
        cfg = configuration or FrontendTopConfig()
        self.clock = Signal(name="bpu_clock")
        self.reset = Signal(name="bpu_reset")
        self.enable = Signal(5, name="io_enable")
        self.reset_vector = Signal(cfg.paddr_bits, name="io_reset_vector")
        self.pc = Signal(cfg.vaddr_bits, name="io_pc")
        self.pred_taken = Signal(name="io_pred_taken")
        self.pred_target = Signal(cfg.vaddr_bits, name="io_pred_target")
        self.pred_cfi_position = Signal(4, name="io_pred_cfi_position")
        self.bp_right = Signal(32, name="io_bpRight")
        self.bp_wrong = Signal(32, name="io_bpWrong")

    # Emit a no-taken sequential prediction until a full BPU is injected. / 在注入完整 BPU 前输出不跳转顺序预测。
    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        module.d.comb += [self.pred_taken.eq(0), self.pred_target.eq(self.pc + 4),
                          self.pred_cfi_position.eq(0), self.bp_right.eq(0), self.bp_wrong.eq(0)]
        return module


class FrontendParent(Elaboratable):
    """Reduced executable V2 Frontend parent closure. / 可执行的精简 V2 前端父级闭包。"""

    # Construct parent controls, child boundaries, and observable frontend lanes. / 构造父级控制、子级边界及可观察前端通道。
    def __init__(self, configuration: FrontendTopConfig | dict[str, Any] | None = None,
                 injected_dependencies: dict[str, Any] | None = None,
                 locked_io: bool = False) -> None:
        if configuration is None:
            self.configuration = FrontendTopConfig()
        elif isinstance(configuration, FrontendTopConfig):
            self.configuration = configuration
        else:
            fields = FrontendTopConfig.__dataclass_fields__
            self.configuration = FrontendTopConfig(**{key: value for key, value in dict(configuration).items()
                                                       if key in fields})
        cfg = self.configuration
        dependencies = injected_dependencies if isinstance(injected_dependencies, dict) else {}
        self.injected_dependencies = dependencies
        self.locked_io = bool(locked_io)
        self.icache = dependencies.get("icache") or dependencies.get("ICache") or FrontendChildBoundary(cfg, "icache")
        self.instr_uncache = (dependencies.get("instr_uncache") or dependencies.get("InstrUncache")
                              or FrontendChildBoundary(cfg, "instr_uncache"))
        self.pipeline = dependencies.get("pipeline") or dependencies.get("FrontendPipeline")
        # Optional leaf children are injected by the family-level validator or
        # by a later full integration.  They are never imported dynamically,
        # preserving the single-file Build contract.  可选叶子子级由 family
        # 验证器或后续完整集成注入；不进行动态导入，保持单文件 Build 契约。
        self.rvc = dependencies.get("rvc") or dependencies.get("RVCExpander") or FrontendRvcBoundary(cfg)
        self.bpu = dependencies.get("bpu") or dependencies.get("BPU") or FrontendBpuBoundary(cfg)
        self.icache_replacer = dependencies.get("icache_replacer") or dependencies.get("ICacheReplacer")
        self.icache_mshr = dependencies.get("icache_mshr") or dependencies.get("ICacheMSHR")
        self.wr_bypass = dependencies.get("wr_bypass") or dependencies.get("WrBypass")

        # Clock/reset and source-level Frontend.scala controls. / 时钟、复位及 Frontend.scala 源级控制。
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.reset_vector = Signal(cfg.paddr_bits, name="io_reset_vector")
        self.fencei = Signal(name="io_fencei")
        self.redirect_valid = Signal(name="io_backend_toFtq_redirect_valid")
        self.redirect_ftq_idx = Signal(cfg.ftq_idx_bits, name="io_backend_toFtq_redirect_ftqIdx")
        self.redirect_ftq_offset = Signal(cfg.ftq_offset_bits, name="io_backend_toFtq_redirect_ftqOffset")
        self.redirect_level = Signal(name="io_backend_toFtq_redirect_level")
        self.redirect_pc = Signal(cfg.vaddr_bits, name="io_backend_toFtq_redirect_pc")
        self.redirect_cfi_taken = Signal(name="io_backend_toFtq_redirect_cfiTaken")
        self.redirect_debug_ctrl = Signal(name="io_backend_toFtq_redirect_debugIsCtrl")
        self.redirect_debug_memvio = Signal(name="io_backend_toFtq_redirect_debugIsMemVio")
        self.backend_can_accept = Signal(name="io_backend_canAccept")
        self.wfi_req = Signal(name="io_backend_wfi_wfiReq")

        # Delayed CSR/SFENCE controls used by ICache/ITLB. / 提供给 ICache/ITLB 的延迟 CSR/SFENCE 控制。
        self.csr_pf_enable = Signal(name="io_csrCtrl_pf_enable")
        self.csr_fs_off = Signal(name="io_csrCtrl_fsIsOff")
        self.csr_bp_enable = Signal(5, name="io_csrCtrl_bp_enable")
        self.sfence_valid = Signal(name="io_sfence_valid")

        # Reduced fetch and uncache transactions. / 精简取指与非缓存事务。
        self.fetch_req_valid = Signal(name="io_fetch_req_valid")
        self.fetch_req_addr = Signal(cfg.vaddr_bits, name="io_fetch_req_addr")
        self.fetch_req_nextline = Signal(cfg.vaddr_bits, name="io_fetch_req_nextline")
        self.fetch_req_ready = Signal(name="io_fetch_req_ready")
        self.fetch_resp_valid = Signal(name="io_fetch_resp_valid")
        self.fetch_resp_data = Signal(cfg.instr_bits * 16, name="io_fetch_resp_data")
        self.fetch_resp_error = Signal(name="io_fetch_resp_error")
        self.uncache_req_valid = Signal(name="io_uncache_req_valid")
        self.uncache_req_addr = Signal(cfg.vaddr_bits, name="io_uncache_req_addr")
        self.uncache_req_ready = Signal(name="io_uncache_req_ready")
        self.uncache_resp_valid = Signal(name="io_uncache_resp_valid")
        self.uncache_resp_data = Signal(cfg.instr_bits * 2, name="io_uncache_resp_data")
        self.uncache_resp_error = Signal(name="io_uncache_resp_error")

        # Explicit parent-visible child status overrides. / 显式父级可见子级状态覆盖。
        self.icache_wfi_safe = Signal(name="io_icache_wfiSafe")
        self.instr_uncache_wfi_safe = Signal(name="io_instrUncache_wfiSafe")
        self.icache_error_valid = Signal(name="io_icache_error_valid")
        self.icache_error_bits = Signal(cfg.error_bits, name="io_icache_error_bits")
        self.ibuffer_full_in = Signal(name="io_ibuffer_full")
        self.bp_right_in = Signal(cfg.instr_bits, name="io_bp_right")
        self.bp_wrong_in = Signal(cfg.instr_bits, name="io_bp_wrong")

        # Parent outputs and observation points. / 父级输出及观测点。
        self.need_flush = Signal(name="io_needFlush")
        self.flush_control_redirect = Signal(name="io_flushControlRedirect")
        self.flush_mem_vio_redirect = Signal(name="io_flushMemVioRedirect")
        self.icache_fencei = Signal(name="io_icache_fencei")
        self.icache_pf_enable = Signal(name="io_icache_pf_enable")
        self.ifu_fs_off = Signal(name="io_ifu_fsIsOff")
        self.bpu_enable = Signal(5, name="io_bpu_enable")
        self.itlb_sfence = Signal(name="io_itlb_sfence")
        self.icache_flush = Signal(name="io_icache_flush")
        self.icache_wfi_req = Signal(name="io_icache_wfiReq")
        self.instr_uncache_wfi_req = Signal(name="io_instrUncache_wfiReq")
        self.wfi_safe = Signal(name="io_backend_wfi_wfiSafe")
        self.error_valid = Signal(name="io_error_ecc_error_valid")
        self.error_bits = Signal(cfg.error_bits, name="io_error_ecc_error_bits")
        self.reset_in_frontend = Signal(name="io_resetInFrontend")
        self.frontend_info_ibuf_full = Signal(name="io_frontendInfo_ibufFull")
        self.frontend_info_bp_right = Signal(cfg.instr_bits, name="io_frontendInfo_bpRight")
        self.frontend_info_bp_wrong = Signal(cfg.instr_bits, name="io_frontendInfo_bpWrong")
        self.cf_valid = Signal(cfg.fetch_width, name="io_backend_cfVec_valid")
        self.cf_instr = Signal(cfg.fetch_width * cfg.instr_bits, name="io_backend_cfVec_instr")
        self.cf_pc = Signal(cfg.fetch_width * cfg.vaddr_bits, name="io_backend_cfVec_pc")
        self.cf_is_rvc = Signal(cfg.fetch_width, name="io_backend_cfVec_isRVC")
        self.cf_pred_taken = Signal(cfg.fetch_width, name="io_backend_cfVec_predTaken")
        self.cf_exception = Signal(cfg.fetch_width, name="io_backend_cfVec_exception")
        self.ptw_req_valid = Signal(name="io_ptw_req_valid")
        self.ptw_req_vpn = Signal(max(1, cfg.vaddr_bits - 12), name="io_ptw_req_vpn")
        self.ptw_resp_ready = Signal(name="io_ptw_resp_ready")
        self.perf = [Signal(cfg.perf_bits, name=f"io_perf_{index}_value") for index in range(cfg.perf_count)]

        # Materialize the exact 371-port XSTop inventory. / 实例化与 XSTop 完全一致的 371 个端口清单。
        self.frontend_port_specs = frontend_port_specs()
        self.frontend_ports: dict[str, Signal] = {}
        self.inventory_inputs: list[Signal] = []
        self.inventory_outputs: list[Signal] = []
        for port_name, direction, port_width in self.frontend_port_specs:
            existing = getattr(self, port_name, None)
            signal = existing if existing is not None and len(existing) == port_width else Signal(port_width, name=port_name)
            setattr(self, port_name, signal)
            self.frontend_ports[port_name] = signal
            (self.inventory_inputs if direction == "input" else self.inventory_outputs).append(signal)

    # Connect a child signal when the injected object implements the named contract. / 当注入对象实现命名合同时连接子级信号。
    def connect_child_signal(self, module: Module, child: Any, child_name: str,
                             attribute: str, value: Any) -> None:
        signal = getattr(child, attribute, None)
        # Only drive assignable child ports.  Some compatibility aliases are
        # expressions (e.g. a source-gated grant-valid), not writable Signals.
        if isinstance(signal, Signal):
            module.d.comb += signal.eq(value)
        del child_name

    # Elaborate delayed controls, child handshakes, error pipeline, and CF observations. / 展开延迟控制、子级握手、错误流水和 CF 观测。
    def elaborate(self, platform: Any) -> Module:
        del platform
        cfg = self.configuration
        module = Module()
        domain = ClockDomain("frontend_sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        module.domains.frontend_sync = domain
        module.submodules.icache = self.icache
        module.submodules.instr_uncache = self.instr_uncache
        if self.pipeline is not None:
            module.submodules.pipeline = self.pipeline
        if self.wr_bypass is not None:
            module.submodules.wr_bypass = self.wr_bypass
        if self.rvc is not None:
            module.submodules.rvc = self.rvc
        if self.bpu is not None:
            module.submodules.bpu = self.bpu
        if self.icache_replacer is not None:
            module.submodules.icache_replacer = self.icache_replacer
        if self.icache_mshr is not None:
            module.submodules.icache_mshr = self.icache_mshr

        # In full locked-I/O mode, bridge the exact generated Frontend names
        # into the compact internal equations below.  The reduced validator
        # keeps driving the compact signals directly, so these assignments are
        # deliberately conditional.  在完整锁定 I/O 模式下，将精确生成端口
        # 接入下方紧凑方程；精简验证器直接驱动紧凑信号，因此条件化连接。
        if self.locked_io:
            module.d.comb += [
                self.reset_vector.eq(self.io_reset_vector),
                self.fencei.eq(self.io_fencei),
                self.redirect_valid.eq(self.io_backend_toFtq_redirect_valid),
                self.redirect_debug_ctrl.eq(self.io_backend_toFtq_redirect_bits_cfiUpdate_isMisPred),
                self.redirect_debug_memvio.eq(self.io_backend_toFtq_redirect_bits_cfiUpdate_backendIPF),
                self.backend_can_accept.eq(self.io_backend_canAccept),
                self.wfi_req.eq(self.io_backend_wfi_wfiReq),
                self.csr_pf_enable.eq(self.io_csrCtrl_pf_ctrl_l1I_pf_enable),
                self.csr_fs_off.eq(self.io_csrCtrl_fsIsOff),
                self.csr_bp_enable.eq(Cat(self.io_csrCtrl_bp_ctrl_ubtb_enable,
                                          self.io_csrCtrl_bp_ctrl_btb_enable,
                                          self.io_csrCtrl_bp_ctrl_tage_enable,
                                          self.io_csrCtrl_bp_ctrl_sc_enable,
                                          self.io_csrCtrl_bp_ctrl_ras_enable)),
                self.sfence_valid.eq(self.io_sfence_valid),
                # The first soft-prefetch lane is the compact parent request
                # source in the full envelope.  完整包络中用首个 soft-prefetch
                # 通道作为紧凑取指请求源。
                self.fetch_req_valid.eq(self.io_softPrefetch_0_valid),
                self.fetch_req_addr.eq(self.io_softPrefetch_0_bits_vaddr),
                self.fetch_req_nextline.eq(self.io_softPrefetch_0_bits_vaddr + 64),
                self.uncache_req_valid.eq(0),
                self.uncache_req_addr.eq(0),
            ]

        # Child request/status wiring is intentionally attribute-based so a
        # future full child can be injected without importing a sibling Build.
        # 子级请求/状态连接仅按属性进行，以便未来完整子级注入且无需跨 Build 导入。
        for child, name, valid, addr, nextline in (
            (self.icache, "icache", self.fetch_req_valid, self.fetch_req_addr, self.fetch_req_nextline),
            (self.instr_uncache, "instr_uncache", self.uncache_req_valid, self.uncache_req_addr, self.uncache_req_addr),
        ):
            self.connect_child_signal(module, child, name, "clock", self.clock)
            self.connect_child_signal(module, child, name, "reset", self.reset)
            self.connect_child_signal(module, child, name, "flush", self.need_flush)
            self.connect_child_signal(module, child, name, "fencei", self.icache_fencei)
            self.connect_child_signal(module, child, name, "pf_enable", self.icache_pf_enable)
            self.connect_child_signal(module, child, name, "fs_is_off", self.ifu_fs_off)
            self.connect_child_signal(module, child, name, "bp_enable", self.bpu_enable)
            self.connect_child_signal(module, child, name, "sfence", self.itlb_sfence)
            self.connect_child_signal(module, child, name, "wfi_req",
                                      self.icache_wfi_req if name == "icache" else self.instr_uncache_wfi_req)
            self.connect_child_signal(module, child, name, "req_valid", valid)
            self.connect_child_signal(module, child, name, "req_addr", addr)
            self.connect_child_signal(module, child, name, "req_nextline", nextline)

        # Bind optional RVC/BPU/ICache leaf contracts when their canonical
        # signals are present.  This keeps the parent usable with the already
        # rewritten children without a sibling import.  若注入子级提供标准
        # 信号，则在父级直接绑定 RVC/BPU/ICache 叶子合同。
        if self.rvc is not None:
            self.connect_child_signal(module, self.rvc, "rvc", "in_", self.fetch_resp_data[:32])
            self.connect_child_signal(module, self.rvc, "rvc", "fsIsOff", self.ifu_fs_off)
            rvc_out = getattr(self.rvc, "out_bits", None)
            rvc_ill = getattr(self.rvc, "ill", None)
            if rvc_out is not None:
                module.d.comb += self.cf_instr[:cfg.instr_bits].eq(rvc_out)
            if rvc_ill is not None:
                module.d.comb += self.cf_exception[0].eq(rvc_ill)
        if self.bpu is not None:
            self.connect_child_signal(module, self.bpu, "bpu", "enable", self.bpu_enable)
            self.connect_child_signal(module, self.bpu, "bpu", "reset_vector", self.reset_vector)
            bpu_taken = getattr(self.bpu, "pred_taken", None)
            if bpu_taken is not None:
                module.d.comb += self.cf_pred_taken[0].eq(bpu_taken)
        for child, name in ((self.icache_replacer, "icache_replacer"), (self.icache_mshr, "icache_mshr")):
            if child is None:
                continue
            self.connect_child_signal(module, child, name, "flush", self.need_flush)
            self.connect_child_signal(module, child, name, "fencei", self.icache_fencei)
            self.connect_child_signal(module, child, name, "wfi_req", self.icache_wfi_req)

        child_icache_ready = getattr(self.icache, "req_ready", self.fetch_req_ready)
        child_uncache_ready = getattr(self.instr_uncache, "req_ready", self.uncache_req_ready)
        child_fetch_resp_valid = getattr(self.icache, "resp_valid", self.fetch_resp_valid)
        child_fetch_resp_data = getattr(self.icache, "resp_data", self.fetch_resp_data)
        child_fetch_resp_error = getattr(self.icache, "resp_error", self.fetch_resp_error)
        child_uncache_resp_valid = getattr(self.instr_uncache, "resp_valid", self.uncache_resp_valid)
        child_uncache_resp_data = getattr(self.instr_uncache, "resp_data", self.uncache_resp_data)
        child_uncache_resp_error = getattr(self.instr_uncache, "resp_error", self.uncache_resp_error)
        if self.locked_io:
            # In the exact envelope, the InstrUncache child owns the complete
            # request/grant transaction.  External TileLink A/D pins are
            # connected to the injected child, matching the locked
            # InstrUncache module instead of bypassing its state machine.
            # 精确包络中 InstrUncache 子级负责完整请求/grant 事务；外部
            # TileLink A/D 引脚连接到注入子级，保持与锁定模块一致。
            module.d.comb += [
                self.fetch_req_ready.eq(child_icache_ready),
                self.fetch_resp_valid.eq(self.auto_inner_icache_client_out_d_valid),
                self.fetch_resp_data.eq(Cat(self.auto_inner_icache_client_out_d_bits_data, Const(0, 256))),
                self.fetch_resp_error.eq(self.auto_inner_icache_client_out_d_bits_corrupt),
                self.uncache_req_ready.eq(child_uncache_ready),
                self.uncache_resp_valid.eq(child_uncache_resp_valid),
                self.uncache_resp_data.eq(child_uncache_resp_data[:len(self.uncache_resp_data)]),
                self.uncache_resp_error.eq(child_uncache_resp_error),
            ]
            # InstrUncache's generated client has no D-ready port and accepts
            # every grant beat (the locked one-entry arbiter ties ready high).
            self.connect_child_signal(module, self.instr_uncache, "instr_uncache",
                                      "mmio_acquire_ready", self.auto_inner_instrUncache_client_out_a_ready)
            self.connect_child_signal(module, self.instr_uncache, "instr_uncache",
                                      "mmio_grant_valid", self.auto_inner_instrUncache_client_out_d_valid)
            self.connect_child_signal(module, self.instr_uncache, "instr_uncache",
                                      "mmio_grant_source", self.auto_inner_instrUncache_client_out_d_bits_source)
            self.connect_child_signal(module, self.instr_uncache, "instr_uncache",
                                      "mmio_grant_data", self.auto_inner_instrUncache_client_out_d_bits_data)
            self.connect_child_signal(module, self.instr_uncache, "instr_uncache",
                                      "mmio_grant_corrupt", self.auto_inner_instrUncache_client_out_d_bits_corrupt)
            # Canonical InstrUncache child names (used by the standalone
            # aggregate) are wired as well; aliases above support legacy
            # InstrMMIOEntry injections.
            self.connect_child_signal(module, self.instr_uncache, "instr_uncache",
                                      "client_out_a_ready", self.auto_inner_instrUncache_client_out_a_ready)
            self.connect_child_signal(module, self.instr_uncache, "instr_uncache",
                                      "client_out_d_valid", self.auto_inner_instrUncache_client_out_d_valid)
            self.connect_child_signal(module, self.instr_uncache, "instr_uncache",
                                      "client_out_d_bits_source", self.auto_inner_instrUncache_client_out_d_bits_source)
            self.connect_child_signal(module, self.instr_uncache, "instr_uncache",
                                      "client_out_d_bits_data", self.auto_inner_instrUncache_client_out_d_bits_data)
            self.connect_child_signal(module, self.instr_uncache, "instr_uncache",
                                      "client_out_d_bits_corrupt", self.auto_inner_instrUncache_client_out_d_bits_corrupt)
        else:
            module.d.comb += [
                self.fetch_req_ready.eq(child_icache_ready),
                self.fetch_resp_valid.eq(child_fetch_resp_valid),
                self.fetch_resp_data.eq(child_fetch_resp_data[:len(self.fetch_resp_data)]),
                self.fetch_resp_error.eq(child_fetch_resp_error),
                self.uncache_req_ready.eq(child_uncache_ready),
                self.uncache_resp_valid.eq(child_uncache_resp_valid),
                self.uncache_resp_data.eq(child_uncache_resp_data[:len(self.uncache_resp_data)]),
                self.uncache_resp_error.eq(child_uncache_resp_error),
            ]
        if self.locked_io:
            # Child status is authoritative when the injected child exposes
            # it; fallback boundaries remain safe while idle.  若注入子级
            # 暴露状态，则以其为准；回退边界空闲时保持安全。
            child_wfi_safe = getattr(self.icache, "wfi_safe", None)
            child_uncache_safe = getattr(self.instr_uncache, "wfi_safe", None)
            child_error_valid = getattr(self.icache, "error_valid", None)
            child_error_bits = getattr(self.icache, "error_bits", None)
            child_ibuf_full = getattr(self.icache, "ibuffer_full", None)
            child_bp_right = getattr(self.icache, "bp_right", None)
            child_bp_wrong = getattr(self.icache, "bp_wrong", None)
            if child_wfi_safe is not None:
                module.d.comb += self.icache_wfi_safe.eq(child_wfi_safe)
            if child_uncache_safe is not None:
                module.d.comb += self.instr_uncache_wfi_safe.eq(child_uncache_safe)
            if child_error_valid is not None:
                module.d.comb += self.icache_error_valid.eq(child_error_valid)
            if child_error_bits is not None:
                module.d.comb += self.icache_error_bits.eq(child_error_bits)
            if child_ibuf_full is not None:
                module.d.comb += self.ibuffer_full_in.eq(child_ibuf_full)
            if child_bp_right is not None:
                module.d.comb += self.bp_right_in.eq(child_bp_right)
            if child_bp_wrong is not None:
                module.d.comb += self.bp_wrong_in.eq(child_bp_wrong)
        # Deterministic tie-offs for unbound full-inventory outputs. / 对尚未绑定的完整清单输出确定性置零。
        if self.locked_io:
            mapped_outputs = {
                "auto_inner_icache_client_out_a_valid", "auto_inner_icache_client_out_a_bits_source",
                "auto_inner_icache_client_out_a_bits_address", "auto_inner_instrUncache_client_out_a_valid",
                "auto_inner_instrUncache_client_out_a_bits_address", "io_ptw_req_0_valid",
                "io_ptw_req_0_bits_vpn", "io_ptw_req_0_bits_s2xlate", "io_ptw_resp_ready",
                "io_backend_wfi_wfiSafe", "io_error_ecc_error_valid", "io_error_ecc_error_bits",
                "io_resetInFrontend", *[f"io_perf_{index}_value" for index in range(cfg.perf_count)],
                *[f"io_backend_cfVec_{lane}_{suffix}" for lane in range(cfg.fetch_width)
                  for suffix in ("valid", "bits_instr", "bits_exceptionVec_1", "bits_pd_isRVC", "bits_pred_taken")],
            }
            for port_name, _direction, _width in self.frontend_port_specs:
                if _direction == "output" and port_name not in mapped_outputs:
                    module.d.comb += self.frontend_ports[port_name].eq(0)
            module.d.comb += [
                self.auto_inner_icache_client_out_a_valid.eq(self.fetch_req_valid & self.fetch_req_ready),
                self.auto_inner_icache_client_out_a_bits_source.eq(0),
                self.auto_inner_icache_client_out_a_bits_address.eq(self.fetch_req_addr[:48]),
                self.auto_inner_instrUncache_client_out_a_valid.eq(
                    getattr(self.instr_uncache, "mmio_acquire_valid", self.uncache_req_valid & self.uncache_req_ready)),
                self.auto_inner_instrUncache_client_out_a_bits_address.eq(
                    getattr(self.instr_uncache, "mmio_acquire_address", self.uncache_req_addr[:48])),
                self.io_ptw_req_0_valid.eq(self.ptw_req_valid),
                self.io_ptw_req_0_bits_vpn.eq(self.ptw_req_vpn),
                self.io_ptw_req_0_bits_s2xlate.eq(0),
                self.io_ptw_resp_ready.eq(self.ptw_resp_ready),
                self.io_backend_wfi_wfiSafe.eq(self.wfi_safe),
                self.io_error_ecc_error_valid.eq(self.error_valid),
                self.io_error_ecc_error_bits.eq(self.error_bits),
                self.io_resetInFrontend.eq(self.reset_in_frontend),
            ]
            for index in range(cfg.perf_count):
                module.d.comb += self.frontend_ports[f"io_perf_{index}_value"].eq(self.perf[index])
            # Expand the compact CF vectors into the six generated bundle lanes.
            for lane in range(cfg.fetch_width):
                prefix = f"io_backend_cfVec_{lane}_"
                module.d.comb += [
                    self.frontend_ports[prefix + "valid"].eq(self.cf_valid[lane]),
                    self.frontend_ports[prefix + "bits_instr"].eq(self.cf_instr[lane * cfg.instr_bits:(lane + 1) * cfg.instr_bits]),
                    self.frontend_ports[prefix + "bits_pd_isRVC"].eq(self.cf_is_rvc[lane]),
                    self.frontend_ports[prefix + "bits_pred_taken"].eq(self.cf_pred_taken[lane]),
                    self.frontend_ports[prefix + "bits_exceptionVec_1"].eq(self.cf_exception[lane]),
                ]

        # Source Frontend.scala uses RegNext for redirect/fence and DelayN(1)
        # for WFI, then a second DelayN(1) for the returned safe indication.
        # Frontend.scala 对 redirect/fence 使用 RegNext，对 WFI 使用 DelayN(1)，
        # safe 返回再经过一个 DelayN(1)。
        need_flush_reg = Signal(name="needFlush_reg")
        control_redirect_reg = Signal(name="flushControlRedirect_reg")
        mem_vio_redirect_reg = Signal(name="flushMemVioRedirect_reg")
        fencei_reg = Signal(name="fencei_reg")
        wfi_req_reg = Signal(name="wfiReq_reg")
        csr_pf_reg_1 = Signal(name="csr_pf_reg_1")
        csr_pf_reg_2 = Signal(name="csr_pf_reg_2")
        csr_fs_reg_1 = Signal(name="csr_fs_reg_1")
        csr_fs_reg_2 = Signal(name="csr_fs_reg_2")
        csr_bp_reg_1 = Signal(5, name="csr_bp_reg_1")
        csr_bp_reg_2 = Signal(5, name="csr_bp_reg_2")
        sfence_reg_1 = Signal(name="sfence_reg_1")
        sfence_reg_2 = Signal(name="sfence_reg_2")
        error_valid_reg_1 = Signal(name="error_valid_reg_1")
        error_valid_reg_2 = Signal(name="error_valid_reg_2")
        error_bits_reg_1 = Signal(cfg.error_bits, name="error_bits_reg_1")
        error_bits_reg_2 = Signal(cfg.error_bits, name="error_bits_reg_2")
        wfi_safe_reg_1 = Signal(name="wfi_safe_reg_1")
        wfi_safe_reg_2 = Signal(name="wfi_safe_reg_2")
        ibuffer_full_reg = Signal(name="ibuffer_full_reg")
        module.d.frontend_sync += [
            need_flush_reg.eq(self.redirect_valid),
            control_redirect_reg.eq(self.redirect_debug_ctrl),
            mem_vio_redirect_reg.eq(self.redirect_debug_memvio),
            fencei_reg.eq(self.fencei),
            wfi_req_reg.eq(self.wfi_req),
            csr_pf_reg_1.eq(self.csr_pf_enable),
            csr_pf_reg_2.eq(csr_pf_reg_1),
            csr_fs_reg_1.eq(self.csr_fs_off),
            csr_fs_reg_2.eq(csr_fs_reg_1),
            csr_bp_reg_1.eq(self.csr_bp_enable),
            csr_bp_reg_2.eq(csr_bp_reg_1),
            sfence_reg_1.eq(self.sfence_valid),
            sfence_reg_2.eq(sfence_reg_1),
            error_valid_reg_1.eq(self.icache_error_valid),
            error_valid_reg_2.eq(error_valid_reg_1),
            error_bits_reg_1.eq(self.icache_error_bits),
            error_bits_reg_2.eq(error_bits_reg_1),
            wfi_safe_reg_1.eq(wfi_req_reg & self.icache_wfi_safe & self.instr_uncache_wfi_safe),
            wfi_safe_reg_2.eq(wfi_safe_reg_1),
            ibuffer_full_reg.eq(self.ibuffer_full_in),
        ]

        module.d.comb += [
            self.need_flush.eq(need_flush_reg),
            self.flush_control_redirect.eq(control_redirect_reg),
            self.flush_mem_vio_redirect.eq(mem_vio_redirect_reg),
            self.icache_fencei.eq(fencei_reg),
            self.icache_pf_enable.eq(csr_pf_reg_2),
            self.ifu_fs_off.eq(csr_fs_reg_2),
            self.bpu_enable.eq(csr_bp_reg_2),
            self.itlb_sfence.eq(sfence_reg_2),
            self.icache_flush.eq(need_flush_reg),
            self.icache_wfi_req.eq(wfi_req_reg),
            self.instr_uncache_wfi_req.eq(wfi_req_reg),
            self.wfi_safe.eq(wfi_safe_reg_2),
            self.error_valid.eq(error_valid_reg_2),
            self.error_bits.eq(error_bits_reg_2),
            self.reset_in_frontend.eq(self.reset),
            self.frontend_info_ibuf_full.eq(ibuffer_full_reg),
            self.frontend_info_bp_right.eq(self.bp_right_in),
            self.frontend_info_bp_wrong.eq(self.bp_wrong_in),
            self.ptw_req_valid.eq(0),
            self.ptw_req_vpn.eq(self.fetch_req_addr[12:]),
            self.ptw_resp_ready.eq(~self.reset & ~need_flush_reg),
        ]

        # Forward a pipeline child when supplied; otherwise expose the ICache
        # child as the bounded CF-vector source and keep all metadata explicit.
        # 若提供 pipeline 子级则转发其 CF 向量，否则以 ICache 子级作为精简来源。
        source = self.pipeline if self.pipeline is not None else self.icache
        module.d.comb += [
            self.cf_valid.eq(getattr(source, "cf_valid", 0)),
            self.cf_instr.eq(getattr(source, "cf_instr", 0)),
            self.cf_pc.eq(getattr(source, "cf_pc", 0)),
            self.cf_is_rvc.eq(getattr(source, "cf_is_rvc", 0)),
            self.cf_pred_taken.eq(getattr(source, "cf_pred_taken", 0)),
            self.cf_exception.eq(getattr(source, "cf_exception", 0)),
        ]
        for index, perf_signal in enumerate(self.perf):
            # The reduced parent reports deterministic event lanes; injected
            # pipelines may override them through an optional ``perf`` array.
            # 精简父级报告确定性事件通道；注入 pipeline 可通过可选 perf 数组覆盖。
            external_perf = getattr(source, "perf", None)
            if isinstance(external_perf, (list, tuple)) and index < len(external_perf):
                module.d.comb += perf_signal.eq(external_perf[index])
            else:
                module.d.comb += perf_signal.eq(0)
        return module


# Preserve source-oriented aliases while exposing the project-facing UHSCTop. / 保留源导向别名并暴露项目侧 UHSCTop。
UHSCTop = FrontendParent
Frontend = FrontendParent


# =============================================================================
# Public Adapter
# =============================================================================
# Emit deterministic RTL using the final project-facing external name. / 使用最终项目侧外部名称输出确定性 RTL。
def build_verilog(configuration, injected_dependencies):
    """Return Verilog for the configured bounded Frontend parent. / 返回配置后的精简前端父级 Verilog。"""
    dependencies = injected_dependencies if isinstance(injected_dependencies, dict) else {}
    if isinstance(configuration, FrontendTopConfig):
        cfg = configuration
        options: dict[str, Any] = {}
    elif isinstance(configuration, dict):
        options = dict(configuration)
        fields = FrontendTopConfig.__dataclass_fields__
        cfg = FrontendTopConfig(**{key: value for key, value in options.items() if key in fields})
    else:
        options = {}
        cfg = FrontendTopConfig()
    top = UHSCTop(cfg, dependencies,
                  locked_io=bool(options.get("locked_io", options.get("full", True))))
    if top.locked_io:
        # Export the exact locked Frontend port order; compact auxiliary
        # signals remain internal implementation observables. / 输出锁定
        # Frontend 精确端口顺序；紧凑辅助信号保留为内部观测点。
        ports: list[Any] = [top.frontend_ports[name] for name, _direction, _width in top.frontend_port_specs]
    else:
        # Preserve the compact parent adapter used by earlier leaf validators.
        # 保留早期叶子验证器使用的紧凑父级适配器。
        ports = [
            top.clock, top.reset, top.reset_vector, top.fencei, top.redirect_valid,
            top.redirect_ftq_idx, top.redirect_ftq_offset, top.redirect_level,
            top.redirect_pc, top.redirect_cfi_taken, top.redirect_debug_ctrl,
            top.redirect_debug_memvio, top.backend_can_accept, top.wfi_req,
            top.csr_pf_enable, top.csr_fs_off, top.csr_bp_enable, top.sfence_valid,
            top.fetch_req_valid, top.fetch_req_addr, top.fetch_req_nextline,
            top.fetch_req_ready, top.fetch_resp_valid, top.fetch_resp_data,
            top.fetch_resp_error, top.uncache_req_valid, top.uncache_req_addr,
            top.uncache_req_ready, top.uncache_resp_valid, top.uncache_resp_data,
            top.uncache_resp_error, top.icache_wfi_safe, top.instr_uncache_wfi_safe,
            top.icache_error_valid, top.icache_error_bits, top.ibuffer_full_in,
            top.bp_right_in, top.bp_wrong_in, top.need_flush,
            top.flush_control_redirect, top.flush_mem_vio_redirect, top.icache_fencei,
            top.icache_pf_enable, top.ifu_fs_off, top.bpu_enable, top.itlb_sfence,
            top.icache_flush, top.icache_wfi_req, top.instr_uncache_wfi_req,
            top.wfi_safe, top.error_valid, top.error_bits, top.reset_in_frontend,
            top.frontend_info_ibuf_full, top.frontend_info_bp_right,
            top.frontend_info_bp_wrong, top.cf_valid, top.cf_instr, top.cf_pc,
            top.cf_is_rvc, top.cf_pred_taken, top.cf_exception, top.ptw_req_valid,
            top.ptw_req_vpn, top.ptw_resp_ready,
        ] + top.perf
    name = str(options.get("module", options.get("name", "UHSCTop")))
    return verilog.convert(top, name=name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print the default parent export for a direct smoke invocation. / 直接 smoke 调用时打印默认父级导出。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
