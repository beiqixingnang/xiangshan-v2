"""Bounded MMU/LSQ family aggregate with an exact frozen port ABI.
具有精确冻结端口 ABI 的有界 MMU/LSQ family 聚合。
"""
from __future__ import annotations
from typing import Any, cast
from amaranth import Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal, Value
from amaranth.back import verilog

# Module Contract
__all__ = ["COVERED_MODULES", "IMPLEMENTED_MEMBERS", "CONTRACT_ONLY_MEMBERS", "PORT_SPECS", "FamilySpec", "family_spec", "MemoryFamily", "build_verilog", "main"]
COVERED_MODULES = ('AtomicsUnit', 'Bitmap', 'HPTW', 'TLBNonBlock_2', 'LoadMisalignBuffer', 'LqExceptionBuffer', 'LsqEnqCtrl', 'AgeDetector_38')
# AgeDetector_38 is the first behaviorally closed LSQ leaf in this aggregate.
# The remaining large MMU/LSQ blocks retain an explicit contract-only status
# until their complete locked-parent differential proofs are available.
IMPLEMENTED_MEMBERS: tuple[str, ...] = ('AgeDetector_38', 'Bitmap')
CONTRACT_ONLY_MEMBERS = tuple(member for member in COVERED_MODULES if member not in IMPLEMENTED_MEMBERS)
# The Build carries only executable behavior and its public port contract.
PortSpec = tuple[str, str, int]

PORT_SPECS: dict[str, tuple[PortSpec, ...]] = {
    'AtomicsUnit': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_hartId', 'input', 6),
        ('io_in_ready', 'output', 1),
        ('io_in_valid', 'input', 1),
        ('io_in_bits_uop_fuOpType', 'input', 9),
        ('io_in_bits_uop_rfWen', 'input', 1),
        ('io_in_bits_uop_pdest', 'input', 8),
        ('io_in_bits_uop_robIdx_flag', 'input', 1),
        ('io_in_bits_uop_robIdx_value', 'input', 8),
        ('io_in_bits_uop_sqIdx_flag', 'input', 1),
        ('io_in_bits_uop_sqIdx_value', 'input', 6),
        ('io_in_bits_src_0', 'input', 64),
        ('io_storeDataIn_0_valid', 'input', 1),
        ('io_storeDataIn_0_bits_uop_fuOpType', 'input', 9),
        ('io_storeDataIn_0_bits_data', 'input', 64),
        ('io_storeDataIn_1_valid', 'input', 1),
        ('io_storeDataIn_1_bits_uop_fuOpType', 'input', 9),
        ('io_storeDataIn_1_bits_data', 'input', 64),
        ('io_out_valid', 'output', 1),
        ('io_out_bits_uop_exceptionVec_3', 'output', 1),
        ('io_out_bits_uop_exceptionVec_4', 'output', 1),
        ('io_out_bits_uop_exceptionVec_5', 'output', 1),
        ('io_out_bits_uop_exceptionVec_6', 'output', 1),
        ('io_out_bits_uop_exceptionVec_7', 'output', 1),
        ('io_out_bits_uop_exceptionVec_13', 'output', 1),
        ('io_out_bits_uop_exceptionVec_15', 'output', 1),
        ('io_out_bits_uop_exceptionVec_19', 'output', 1),
        ('io_out_bits_uop_exceptionVec_21', 'output', 1),
        ('io_out_bits_uop_exceptionVec_23', 'output', 1),
        ('io_out_bits_uop_trigger', 'output', 4),
        ('io_out_bits_uop_rfWen', 'output', 1),
        ('io_out_bits_uop_pdest', 'output', 8),
        ('io_out_bits_uop_robIdx_flag', 'output', 1),
        ('io_out_bits_uop_robIdx_value', 'output', 8),
        ('io_out_bits_data', 'output', 64),
        ('io_out_bits_debug_isMMIO', 'output', 1),
        ('io_dcache_req_ready', 'input', 1),
        ('io_dcache_req_valid', 'output', 1),
        ('io_dcache_req_bits_cmd', 'output', 5),
        ('io_dcache_req_bits_vaddr', 'output', 50),
        ('io_dcache_req_bits_addr', 'output', 48),
        ('io_dcache_req_bits_word_idx', 'output', 3),
        ('io_dcache_req_bits_amo_data', 'output', 128),
        ('io_dcache_req_bits_amo_mask', 'output', 16),
        ('io_dcache_req_bits_amo_cmp', 'output', 128),
        ('io_dcache_resp_valid', 'input', 1),
        ('io_dcache_resp_bits_data', 'input', 128),
        ('io_dcache_resp_bits_miss', 'input', 1),
        ('io_dcache_resp_bits_replay', 'input', 1),
        ('io_dcache_resp_bits_tl_error_tl_denied', 'input', 1),
        ('io_dcache_resp_bits_tl_error_tl_corrupt', 'input', 1),
        ('io_dcache_resp_bits_id', 'input', 6),
        ('io_dcache_block_lr', 'input', 1),
        ('io_dtlb_req_valid', 'output', 1),
        ('io_dtlb_req_bits_vaddr', 'output', 50),
        ('io_dtlb_req_bits_fullva', 'output', 64),
        ('io_dtlb_req_bits_cmd', 'output', 3),
        ('io_dtlb_req_bits_debug_robIdx_flag', 'output', 1),
        ('io_dtlb_req_bits_debug_robIdx_value', 'output', 8),
        ('io_dtlb_resp_valid', 'input', 1),
        ('io_dtlb_resp_bits_paddr_0', 'input', 48),
        ('io_dtlb_resp_bits_gpaddr_0', 'input', 64),
        ('io_dtlb_resp_bits_fullva', 'input', 64),
        ('io_dtlb_resp_bits_pbmt_0', 'input', 2),
        ('io_dtlb_resp_bits_miss', 'input', 1),
        ('io_dtlb_resp_bits_isForVSnonLeafPTE', 'input', 1),
        ('io_dtlb_resp_bits_excp_0_gpf_ld', 'input', 1),
        ('io_dtlb_resp_bits_excp_0_gpf_st', 'input', 1),
        ('io_dtlb_resp_bits_excp_0_pf_ld', 'input', 1),
        ('io_dtlb_resp_bits_excp_0_pf_st', 'input', 1),
        ('io_dtlb_resp_bits_excp_0_af_ld', 'input', 1),
        ('io_dtlb_resp_bits_excp_0_af_st', 'input', 1),
        ('io_pmpResp_ld', 'input', 1),
        ('io_pmpResp_st', 'input', 1),
        ('io_pmpResp_mmio', 'input', 1),
        ('io_flush_sbuffer_valid', 'output', 1),
        ('io_flush_sbuffer_empty', 'input', 1),
        ('io_feedbackSlow_valid', 'output', 1),
        ('io_feedbackSlow_bits_sqIdx_flag', 'output', 1),
        ('io_feedbackSlow_bits_sqIdx_value', 'output', 6),
        ('io_redirect_valid', 'input', 1),
        ('io_exceptionInfo_valid', 'output', 1),
        ('io_exceptionInfo_bits_vaddr', 'output', 64),
        ('io_exceptionInfo_bits_gpaddr', 'output', 64),
        ('io_exceptionInfo_bits_isForVSnonLeafPTE', 'output', 1),
        ('io_csrCtrl_cache_error_enable', 'input', 1),
        ('io_csrCtrl_mem_trigger_tUpdate_valid', 'input', 1),
        ('io_csrCtrl_mem_trigger_tUpdate_bits_addr', 'input', 2),
        ('io_csrCtrl_mem_trigger_tUpdate_bits_tdata_matchType', 'input', 2),
        ('io_csrCtrl_mem_trigger_tUpdate_bits_tdata_select', 'input', 1),
        ('io_csrCtrl_mem_trigger_tUpdate_bits_tdata_action', 'input', 4),
        ('io_csrCtrl_mem_trigger_tUpdate_bits_tdata_chain', 'input', 1),
        ('io_csrCtrl_mem_trigger_tUpdate_bits_tdata_store', 'input', 1),
        ('io_csrCtrl_mem_trigger_tUpdate_bits_tdata_load', 'input', 1),
        ('io_csrCtrl_mem_trigger_tUpdate_bits_tdata_tdata2', 'input', 64),
        ('io_csrCtrl_mem_trigger_tEnableVec_0', 'input', 1),
        ('io_csrCtrl_mem_trigger_tEnableVec_1', 'input', 1),
        ('io_csrCtrl_mem_trigger_tEnableVec_2', 'input', 1),
        ('io_csrCtrl_mem_trigger_tEnableVec_3', 'input', 1),
        ('io_csrCtrl_mem_trigger_debugMode', 'input', 1),
        ('io_csrCtrl_mem_trigger_triggerCanRaiseBpExp', 'input', 1),
    ),
    'Bitmap': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_sfence_valid', 'input', 1),
        ('io_csr_satp_changed', 'input', 1),
        ('io_csr_vsatp_changed', 'input', 1),
        ('io_csr_hgatp_changed', 'input', 1),
        ('io_csr_mbmc_BMA', 'input', 58),
        ('io_csr_priv_virt_changed', 'input', 1),
        ('io_mem_req_ready', 'input', 1),
        ('io_mem_req_valid', 'output', 1),
        ('io_mem_req_bits_addr', 'output', 48),
        ('io_mem_req_bits_id', 'output', 4),
        ('io_mem_resp_valid', 'input', 1),
        ('io_mem_resp_bits_id', 'input', 4),
        ('io_mem_resp_bits_value', 'input', 512),
        ('io_mem_req_mask_0', 'input', 1),
        ('io_mem_req_mask_1', 'input', 1),
        ('io_mem_req_mask_2', 'input', 1),
        ('io_mem_req_mask_3', 'input', 1),
        ('io_mem_req_mask_4', 'input', 1),
        ('io_mem_req_mask_5', 'input', 1),
        ('io_mem_req_mask_6', 'input', 1),
        ('io_mem_req_mask_7', 'input', 1),
        ('io_req_ready', 'output', 1),
        ('io_req_valid', 'input', 1),
        ('io_req_bits_bmppn', 'input', 36),
        ('io_req_bits_id', 'input', 3),
        ('io_req_bits_vpn', 'input', 38),
        ('io_req_bits_level', 'input', 2),
        ('io_req_bits_way_info', 'input', 4),
        ('io_req_bits_hptw_bypassed', 'input', 1),
        ('io_req_bits_s2xlate', 'input', 2),
        ('io_req_bits_n', 'input', 1),
        ('io_resp_ready', 'input', 1),
        ('io_resp_valid', 'output', 1),
        ('io_resp_bits_cf', 'output', 1),
        ('io_resp_bits_cfs_0', 'output', 1),
        ('io_resp_bits_cfs_1', 'output', 1),
        ('io_resp_bits_cfs_2', 'output', 1),
        ('io_resp_bits_cfs_3', 'output', 1),
        ('io_resp_bits_cfs_4', 'output', 1),
        ('io_resp_bits_cfs_5', 'output', 1),
        ('io_resp_bits_cfs_6', 'output', 1),
        ('io_resp_bits_cfs_7', 'output', 1),
        ('io_resp_bits_id', 'output', 3),
        ('io_pmp_req_bits_addr', 'output', 48),
        ('io_pmp_resp_ld', 'input', 1),
        ('io_pmp_resp_mmio', 'input', 1),
        ('io_wakeup_ready', 'input', 1),
        ('io_wakeup_valid', 'output', 1),
        ('io_wakeup_bits_setIndex', 'output', 6),
        ('io_wakeup_bits_tag', 'output', 38),
        ('io_wakeup_bits_way_info', 'output', 4),
        ('io_wakeup_bits_pte_index', 'output', 3),
        ('io_wakeup_bits_check_success', 'output', 1),
        ('io_wakeup_bits_s2xlate', 'output', 2),
        ('io_cache_req_ready', 'input', 1),
        ('io_cache_req_valid', 'output', 1),
        ('io_cache_req_bits_order', 'output', 8),
        ('io_cache_req_bits_tag', 'output', 36),
        ('io_cache_resp_ready', 'output', 1),
        ('io_cache_resp_valid', 'input', 1),
        ('io_cache_resp_bits_hit', 'input', 1),
        ('io_cache_resp_bits_cfs_0', 'input', 1),
        ('io_cache_resp_bits_cfs_1', 'input', 1),
        ('io_cache_resp_bits_cfs_2', 'input', 1),
        ('io_cache_resp_bits_cfs_3', 'input', 1),
        ('io_cache_resp_bits_cfs_4', 'input', 1),
        ('io_cache_resp_bits_cfs_5', 'input', 1),
        ('io_cache_resp_bits_cfs_6', 'input', 1),
        ('io_cache_resp_bits_cfs_7', 'input', 1),
        ('io_cache_resp_bits_order', 'input', 8),
        ('io_refill_valid', 'output', 1),
        ('io_refill_bits_tag', 'output', 36),
        ('io_refill_bits_data', 'output', 64),
    ),
    'HPTW': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_sfence_valid', 'input', 1),
        ('io_csr_satp_changed', 'input', 1),
        ('io_csr_vsatp_changed', 'input', 1),
        ('io_csr_hgatp_mode', 'input', 4),
        ('io_csr_hgatp_vmid', 'input', 16),
        ('io_csr_hgatp_ppn', 'input', 44),
        ('io_csr_hgatp_changed', 'input', 1),
        ('io_csr_mbmc_BME', 'input', 1),
        ('io_csr_mbmc_CMODE', 'input', 1),
        ('io_csr_priv_virt_changed', 'input', 1),
        ('io_csr_mPBMTE', 'input', 1),
        ('io_req_ready', 'output', 1),
        ('io_req_valid', 'input', 1),
        ('io_req_bits_source', 'input', 2),
        ('io_req_bits_id', 'input', 3),
        ('io_req_bits_gvpn', 'input', 38),
        ('io_req_bits_ppn', 'input', 36),
        ('io_req_bits_l3Hit', 'input', 1),
        ('io_req_bits_l2Hit', 'input', 1),
        ('io_req_bits_l1Hit', 'input', 1),
        ('io_req_bits_bypassed', 'input', 1),
        ('io_req_bits_bitmapCheck_jmp_bitmap_check', 'input', 1),
        ('io_req_bits_bitmapCheck_pte', 'input', 64),
        ('io_req_bits_bitmapCheck_ptes_0', 'input', 64),
        ('io_req_bits_bitmapCheck_ptes_1', 'input', 64),
        ('io_req_bits_bitmapCheck_ptes_2', 'input', 64),
        ('io_req_bits_bitmapCheck_ptes_3', 'input', 64),
        ('io_req_bits_bitmapCheck_ptes_4', 'input', 64),
        ('io_req_bits_bitmapCheck_ptes_5', 'input', 64),
        ('io_req_bits_bitmapCheck_ptes_6', 'input', 64),
        ('io_req_bits_bitmapCheck_ptes_7', 'input', 64),
        ('io_req_bits_bitmapCheck_hitway', 'input', 4),
        ('io_req_bits_bitmapCheck_fromSP', 'input', 1),
        ('io_req_bits_bitmapCheck_SPlevel', 'input', 2),
        ('io_resp_ready', 'input', 1),
        ('io_resp_valid', 'output', 1),
        ('io_resp_bits_resp_entry_tag', 'output', 38),
        ('io_resp_bits_resp_entry_vmid', 'output', 14),
        ('io_resp_bits_resp_entry_n', 'output', 1),
        ('io_resp_bits_resp_entry_pbmt', 'output', 2),
        ('io_resp_bits_resp_entry_ppn', 'output', 38),
        ('io_resp_bits_resp_entry_perm_d', 'output', 1),
        ('io_resp_bits_resp_entry_perm_a', 'output', 1),
        ('io_resp_bits_resp_entry_perm_g', 'output', 1),
        ('io_resp_bits_resp_entry_perm_u', 'output', 1),
        ('io_resp_bits_resp_entry_perm_x', 'output', 1),
        ('io_resp_bits_resp_entry_perm_w', 'output', 1),
        ('io_resp_bits_resp_entry_perm_r', 'output', 1),
        ('io_resp_bits_resp_entry_level', 'output', 2),
        ('io_resp_bits_resp_gpf', 'output', 1),
        ('io_resp_bits_resp_gaf', 'output', 1),
        ('io_resp_bits_id', 'output', 4),
        ('io_mem_req_ready', 'input', 1),
        ('io_mem_req_valid', 'output', 1),
        ('io_mem_req_bits_addr', 'output', 48),
        ('io_mem_req_bits_hptw_bypassed', 'output', 1),
        ('io_mem_resp_valid', 'input', 1),
        ('io_mem_resp_bits', 'input', 64),
        ('io_mem_mask', 'input', 1),
        ('io_refill_req_info_vpn', 'output', 38),
        ('io_refill_req_info_source', 'output', 2),
        ('io_refill_level', 'output', 2),
        ('io_pmp_req_bits_addr', 'output', 48),
        ('io_pmp_resp_ld', 'input', 1),
        ('io_pmp_resp_mmio', 'input', 1),
        ('io_bitmap_req_ready', 'input', 1),
        ('io_bitmap_req_valid', 'output', 1),
        ('io_bitmap_req_bits_bmppn', 'output', 36),
        ('io_bitmap_req_bits_vpn', 'output', 38),
        ('io_bitmap_req_bits_level', 'output', 2),
        ('io_bitmap_req_bits_way_info', 'output', 4),
        ('io_bitmap_req_bits_hptw_bypassed', 'output', 1),
        ('io_bitmap_req_bits_n', 'output', 1),
        ('io_bitmap_resp_ready', 'output', 1),
        ('io_bitmap_resp_valid', 'input', 1),
        ('io_bitmap_resp_bits_cf', 'input', 1),
        ('io_l0_way_info', 'input', 4),
    ),
    'TLBNonBlock_2': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_sfence_valid', 'input', 1),
        ('io_sfence_bits_rs1', 'input', 1),
        ('io_sfence_bits_rs2', 'input', 1),
        ('io_sfence_bits_addr', 'input', 50),
        ('io_sfence_bits_id', 'input', 16),
        ('io_sfence_bits_flushPipe', 'input', 1),
        ('io_sfence_bits_hv', 'input', 1),
        ('io_sfence_bits_hg', 'input', 1),
        ('io_csr_satp_mode', 'input', 4),
        ('io_csr_satp_asid', 'input', 16),
        ('io_csr_satp_changed', 'input', 1),
        ('io_csr_vsatp_mode', 'input', 4),
        ('io_csr_vsatp_asid', 'input', 16),
        ('io_csr_vsatp_changed', 'input', 1),
        ('io_csr_hgatp_mode', 'input', 4),
        ('io_csr_hgatp_vmid', 'input', 16),
        ('io_csr_hgatp_changed', 'input', 1),
        ('io_csr_mbmc_BME', 'input', 1),
        ('io_csr_mbmc_CMODE', 'input', 1),
        ('io_csr_priv_mxr', 'input', 1),
        ('io_csr_priv_sum', 'input', 1),
        ('io_csr_priv_vmxr', 'input', 1),
        ('io_csr_priv_vsum', 'input', 1),
        ('io_csr_priv_virt', 'input', 1),
        ('io_csr_priv_virt_changed', 'input', 1),
        ('io_csr_priv_spvp', 'input', 1),
        ('io_csr_priv_imode', 'input', 2),
        ('io_csr_priv_dmode', 'input', 2),
        ('io_csr_priv_debug', 'input', 1),
        ('io_csr_pmm_mseccfg', 'input', 2),
        ('io_csr_pmm_menvcfg', 'input', 2),
        ('io_csr_pmm_henvcfg', 'input', 2),
        ('io_csr_pmm_hstatus', 'input', 2),
        ('io_csr_pmm_senvcfg', 'input', 2),
        ('io_requestor_0_req_valid', 'input', 1),
        ('io_requestor_0_req_bits_vaddr', 'input', 50),
        ('io_requestor_0_req_bits_fullva', 'input', 64),
        ('io_requestor_0_req_bits_checkfullva', 'input', 1),
        ('io_requestor_0_req_bits_cmd', 'input', 3),
        ('io_requestor_0_req_bits_hyperinst', 'input', 1),
        ('io_requestor_0_req_bits_hlvx', 'input', 1),
        ('io_requestor_0_req_bits_kill', 'input', 1),
        ('io_requestor_0_req_bits_isPrefetch', 'input', 1),
        ('io_requestor_0_req_bits_no_translate', 'input', 1),
        ('io_requestor_0_req_bits_pmp_addr', 'input', 48),
        ('io_requestor_0_req_bits_frm_mabuf', 'input', 1),
        ('io_requestor_0_req_bits_debug_robIdx_flag', 'input', 1),
        ('io_requestor_0_req_bits_debug_robIdx_value', 'input', 8),
        ('io_requestor_0_resp_valid', 'output', 1),
        ('io_requestor_0_resp_bits_paddr_0', 'output', 48),
        ('io_requestor_0_resp_bits_pbmt_0', 'output', 2),
        ('io_requestor_0_resp_bits_miss', 'output', 1),
        ('io_requestor_0_resp_bits_excp_0_gpf_ld', 'output', 1),
        ('io_requestor_0_resp_bits_excp_0_pf_ld', 'output', 1),
        ('io_requestor_0_resp_bits_excp_0_af_ld', 'output', 1),
        ('io_requestor_1_req_valid', 'input', 1),
        ('io_requestor_1_req_bits_vaddr', 'input', 50),
        ('io_requestor_1_req_bits_cmd', 'input', 3),
        ('io_requestor_1_req_bits_kill', 'input', 1),
        ('io_requestor_1_req_bits_isPrefetch', 'input', 1),
        ('io_requestor_1_req_bits_no_translate', 'input', 1),
        ('io_requestor_1_resp_valid', 'output', 1),
        ('io_requestor_1_resp_bits_paddr_0', 'output', 48),
        ('io_requestor_1_resp_bits_pbmt_0', 'output', 2),
        ('io_requestor_1_resp_bits_miss', 'output', 1),
        ('io_requestor_1_resp_bits_excp_0_gpf_ld', 'output', 1),
        ('io_requestor_1_resp_bits_excp_0_pf_ld', 'output', 1),
        ('io_requestor_1_resp_bits_excp_0_af_ld', 'output', 1),
        ('io_redirect_valid', 'input', 1),
        ('io_redirect_bits_robIdx_flag', 'input', 1),
        ('io_redirect_bits_robIdx_value', 'input', 8),
        ('io_redirect_bits_level', 'input', 1),
        ('io_ptw_req_0_valid', 'output', 1),
        ('io_ptw_req_0_bits_vpn', 'output', 38),
        ('io_ptw_req_0_bits_s2xlate', 'output', 2),
        ('io_ptw_req_0_bits_getGpa', 'output', 1),
        ('io_ptw_req_1_valid', 'output', 1),
        ('io_ptw_req_1_bits_vpn', 'output', 38),
        ('io_ptw_req_1_bits_s2xlate', 'output', 2),
        ('io_ptw_req_1_bits_getGpa', 'output', 1),
        ('io_ptw_resp_valid', 'input', 1),
        ('io_ptw_resp_bits_s2xlate', 'input', 2),
        ('io_ptw_resp_bits_s1_entry_tag', 'input', 35),
        ('io_ptw_resp_bits_s1_entry_asid', 'input', 16),
        ('io_ptw_resp_bits_s1_entry_vmid', 'input', 14),
        ('io_ptw_resp_bits_s1_entry_n', 'input', 1),
        ('io_ptw_resp_bits_s1_entry_pbmt', 'input', 2),
        ('io_ptw_resp_bits_s1_entry_perm_d', 'input', 1),
        ('io_ptw_resp_bits_s1_entry_perm_a', 'input', 1),
        ('io_ptw_resp_bits_s1_entry_perm_g', 'input', 1),
        ('io_ptw_resp_bits_s1_entry_perm_u', 'input', 1),
        ('io_ptw_resp_bits_s1_entry_perm_x', 'input', 1),
        ('io_ptw_resp_bits_s1_entry_perm_w', 'input', 1),
        ('io_ptw_resp_bits_s1_entry_perm_r', 'input', 1),
        ('io_ptw_resp_bits_s1_entry_level', 'input', 2),
        ('io_ptw_resp_bits_s1_entry_v', 'input', 1),
        ('io_ptw_resp_bits_s1_entry_ppn', 'input', 41),
        ('io_ptw_resp_bits_s1_addr_low', 'input', 3),
        ('io_ptw_resp_bits_s1_ppn_low_0', 'input', 3),
        ('io_ptw_resp_bits_s1_ppn_low_1', 'input', 3),
        ('io_ptw_resp_bits_s1_ppn_low_2', 'input', 3),
        ('io_ptw_resp_bits_s1_ppn_low_3', 'input', 3),
        ('io_ptw_resp_bits_s1_ppn_low_4', 'input', 3),
        ('io_ptw_resp_bits_s1_ppn_low_5', 'input', 3),
        ('io_ptw_resp_bits_s1_ppn_low_6', 'input', 3),
        ('io_ptw_resp_bits_s1_ppn_low_7', 'input', 3),
        ('io_ptw_resp_bits_s1_valididx_0', 'input', 1),
        ('io_ptw_resp_bits_s1_valididx_1', 'input', 1),
        ('io_ptw_resp_bits_s1_valididx_2', 'input', 1),
        ('io_ptw_resp_bits_s1_valididx_3', 'input', 1),
        ('io_ptw_resp_bits_s1_valididx_4', 'input', 1),
        ('io_ptw_resp_bits_s1_valididx_5', 'input', 1),
        ('io_ptw_resp_bits_s1_valididx_6', 'input', 1),
        ('io_ptw_resp_bits_s1_valididx_7', 'input', 1),
        ('io_ptw_resp_bits_s1_pteidx_0', 'input', 1),
        ('io_ptw_resp_bits_s1_pteidx_1', 'input', 1),
        ('io_ptw_resp_bits_s1_pteidx_2', 'input', 1),
        ('io_ptw_resp_bits_s1_pteidx_3', 'input', 1),
        ('io_ptw_resp_bits_s1_pteidx_4', 'input', 1),
        ('io_ptw_resp_bits_s1_pteidx_5', 'input', 1),
        ('io_ptw_resp_bits_s1_pteidx_6', 'input', 1),
        ('io_ptw_resp_bits_s1_pteidx_7', 'input', 1),
        ('io_ptw_resp_bits_s1_pf', 'input', 1),
        ('io_ptw_resp_bits_s1_af', 'input', 1),
        ('io_ptw_resp_bits_s2_entry_tag', 'input', 38),
        ('io_ptw_resp_bits_s2_entry_vmid', 'input', 14),
        ('io_ptw_resp_bits_s2_entry_n', 'input', 1),
        ('io_ptw_resp_bits_s2_entry_pbmt', 'input', 2),
        ('io_ptw_resp_bits_s2_entry_ppn', 'input', 38),
        ('io_ptw_resp_bits_s2_entry_perm_d', 'input', 1),
        ('io_ptw_resp_bits_s2_entry_perm_a', 'input', 1),
        ('io_ptw_resp_bits_s2_entry_perm_g', 'input', 1),
        ('io_ptw_resp_bits_s2_entry_perm_u', 'input', 1),
        ('io_ptw_resp_bits_s2_entry_perm_x', 'input', 1),
        ('io_ptw_resp_bits_s2_entry_perm_w', 'input', 1),
        ('io_ptw_resp_bits_s2_entry_perm_r', 'input', 1),
        ('io_ptw_resp_bits_s2_entry_level', 'input', 2),
        ('io_ptw_resp_bits_s2_gpf', 'input', 1),
        ('io_ptw_resp_bits_s2_gaf', 'input', 1),
        ('io_ptw_resp_bits_getGpa', 'input', 1),
        ('io_pmp_0_valid', 'output', 1),
        ('io_pmp_0_bits_addr', 'output', 48),
        ('io_pmp_0_bits_cmd', 'output', 3),
        ('io_pmp_1_valid', 'output', 1),
        ('io_pmp_1_bits_addr', 'output', 48),
        ('io_pmp_1_bits_cmd', 'output', 3),
        ('io_pmpMode_0', 'output', 2),
        ('io_pmpMode_1', 'output', 2),
        ('io_robPendingPtr_flag', 'input', 1),
        ('io_robPendingPtr_value', 'input', 8),
    ),
    'LoadMisalignBuffer': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_redirect_valid', 'input', 1),
        ('io_redirect_bits_robIdx_flag', 'input', 1),
        ('io_redirect_bits_robIdx_value', 'input', 8),
        ('io_redirect_bits_level', 'input', 1),
        ('io_enq_0_req_ready', 'output', 1),
        ('io_enq_0_req_valid', 'input', 1),
        ('io_enq_0_req_bits_uop_exceptionVec_3', 'input', 1),
        ('io_enq_0_req_bits_uop_exceptionVec_5', 'input', 1),
        ('io_enq_0_req_bits_uop_exceptionVec_13', 'input', 1),
        ('io_enq_0_req_bits_uop_exceptionVec_19', 'input', 1),
        ('io_enq_0_req_bits_uop_exceptionVec_21', 'input', 1),
        ('io_enq_0_req_bits_uop_trigger', 'input', 4),
        ('io_enq_0_req_bits_uop_preDecodeInfo_isRVC', 'input', 1),
        ('io_enq_0_req_bits_uop_ftqPtr_flag', 'input', 1),
        ('io_enq_0_req_bits_uop_ftqPtr_value', 'input', 6),
        ('io_enq_0_req_bits_uop_ftqOffset', 'input', 4),
        ('io_enq_0_req_bits_uop_fuOpType', 'input', 9),
        ('io_enq_0_req_bits_uop_rfWen', 'input', 1),
        ('io_enq_0_req_bits_uop_fpWen', 'input', 1),
        ('io_enq_0_req_bits_uop_vpu_vstart', 'input', 8),
        ('io_enq_0_req_bits_uop_vpu_veew', 'input', 2),
        ('io_enq_0_req_bits_uop_uopIdx', 'input', 7),
        ('io_enq_0_req_bits_uop_pdest', 'input', 8),
        ('io_enq_0_req_bits_uop_robIdx_flag', 'input', 1),
        ('io_enq_0_req_bits_uop_robIdx_value', 'input', 8),
        ('io_enq_0_req_bits_uop_storeSetHit', 'input', 1),
        ('io_enq_0_req_bits_uop_waitForRobIdx_flag', 'input', 1),
        ('io_enq_0_req_bits_uop_waitForRobIdx_value', 'input', 8),
        ('io_enq_0_req_bits_uop_loadWaitBit', 'input', 1),
        ('io_enq_0_req_bits_uop_loadWaitStrict', 'input', 1),
        ('io_enq_0_req_bits_uop_lqIdx_flag', 'input', 1),
        ('io_enq_0_req_bits_uop_lqIdx_value', 'input', 7),
        ('io_enq_0_req_bits_uop_sqIdx_flag', 'input', 1),
        ('io_enq_0_req_bits_uop_sqIdx_value', 'input', 6),
        ('io_enq_0_req_bits_vaddr', 'input', 50),
        ('io_enq_0_req_bits_fullva', 'input', 64),
        ('io_enq_0_req_bits_vaNeedExt', 'input', 1),
        ('io_enq_0_req_bits_gpaddr', 'input', 64),
        ('io_enq_0_req_bits_mask', 'input', 16),
        ('io_enq_0_req_bits_isForVSnonLeafPTE', 'input', 1),
        ('io_enq_0_req_bits_isvec', 'input', 1),
        ('io_enq_0_req_bits_elemIdx', 'input', 8),
        ('io_enq_0_req_bits_alignedType', 'input', 3),
        ('io_enq_0_req_bits_mbIndex', 'input', 4),
        ('io_enq_0_req_bits_elemIdxInsideVd', 'input', 8),
        ('io_enq_0_req_bits_vecTriggerMask', 'input', 16),
        ('io_enq_1_req_ready', 'output', 1),
        ('io_enq_1_req_valid', 'input', 1),
        ('io_enq_1_req_bits_uop_exceptionVec_3', 'input', 1),
        ('io_enq_1_req_bits_uop_exceptionVec_5', 'input', 1),
        ('io_enq_1_req_bits_uop_exceptionVec_13', 'input', 1),
        ('io_enq_1_req_bits_uop_exceptionVec_19', 'input', 1),
        ('io_enq_1_req_bits_uop_exceptionVec_21', 'input', 1),
        ('io_enq_1_req_bits_uop_trigger', 'input', 4),
        ('io_enq_1_req_bits_uop_preDecodeInfo_isRVC', 'input', 1),
        ('io_enq_1_req_bits_uop_ftqPtr_flag', 'input', 1),
        ('io_enq_1_req_bits_uop_ftqPtr_value', 'input', 6),
        ('io_enq_1_req_bits_uop_ftqOffset', 'input', 4),
        ('io_enq_1_req_bits_uop_fuOpType', 'input', 9),
        ('io_enq_1_req_bits_uop_rfWen', 'input', 1),
        ('io_enq_1_req_bits_uop_fpWen', 'input', 1),
        ('io_enq_1_req_bits_uop_vpu_vstart', 'input', 8),
        ('io_enq_1_req_bits_uop_vpu_veew', 'input', 2),
        ('io_enq_1_req_bits_uop_uopIdx', 'input', 7),
        ('io_enq_1_req_bits_uop_pdest', 'input', 8),
        ('io_enq_1_req_bits_uop_robIdx_flag', 'input', 1),
        ('io_enq_1_req_bits_uop_robIdx_value', 'input', 8),
        ('io_enq_1_req_bits_uop_storeSetHit', 'input', 1),
        ('io_enq_1_req_bits_uop_waitForRobIdx_flag', 'input', 1),
        ('io_enq_1_req_bits_uop_waitForRobIdx_value', 'input', 8),
        ('io_enq_1_req_bits_uop_loadWaitBit', 'input', 1),
        ('io_enq_1_req_bits_uop_loadWaitStrict', 'input', 1),
        ('io_enq_1_req_bits_uop_lqIdx_flag', 'input', 1),
        ('io_enq_1_req_bits_uop_lqIdx_value', 'input', 7),
        ('io_enq_1_req_bits_uop_sqIdx_flag', 'input', 1),
        ('io_enq_1_req_bits_uop_sqIdx_value', 'input', 6),
        ('io_enq_1_req_bits_vaddr', 'input', 50),
        ('io_enq_1_req_bits_fullva', 'input', 64),
        ('io_enq_1_req_bits_vaNeedExt', 'input', 1),
        ('io_enq_1_req_bits_gpaddr', 'input', 64),
        ('io_enq_1_req_bits_mask', 'input', 16),
        ('io_enq_1_req_bits_isForVSnonLeafPTE', 'input', 1),
        ('io_enq_1_req_bits_isvec', 'input', 1),
        ('io_enq_1_req_bits_elemIdx', 'input', 8),
        ('io_enq_1_req_bits_alignedType', 'input', 3),
        ('io_enq_1_req_bits_mbIndex', 'input', 4),
        ('io_enq_1_req_bits_elemIdxInsideVd', 'input', 8),
        ('io_enq_1_req_bits_vecTriggerMask', 'input', 16),
        ('io_enq_2_req_ready', 'output', 1),
        ('io_enq_2_req_valid', 'input', 1),
        ('io_enq_2_req_bits_uop_exceptionVec_3', 'input', 1),
        ('io_enq_2_req_bits_uop_exceptionVec_5', 'input', 1),
        ('io_enq_2_req_bits_uop_exceptionVec_13', 'input', 1),
        ('io_enq_2_req_bits_uop_exceptionVec_19', 'input', 1),
        ('io_enq_2_req_bits_uop_exceptionVec_21', 'input', 1),
        ('io_enq_2_req_bits_uop_trigger', 'input', 4),
        ('io_enq_2_req_bits_uop_preDecodeInfo_isRVC', 'input', 1),
        ('io_enq_2_req_bits_uop_ftqPtr_flag', 'input', 1),
        ('io_enq_2_req_bits_uop_ftqPtr_value', 'input', 6),
        ('io_enq_2_req_bits_uop_ftqOffset', 'input', 4),
        ('io_enq_2_req_bits_uop_fuOpType', 'input', 9),
        ('io_enq_2_req_bits_uop_rfWen', 'input', 1),
        ('io_enq_2_req_bits_uop_fpWen', 'input', 1),
        ('io_enq_2_req_bits_uop_vpu_vstart', 'input', 8),
        ('io_enq_2_req_bits_uop_vpu_veew', 'input', 2),
        ('io_enq_2_req_bits_uop_uopIdx', 'input', 7),
        ('io_enq_2_req_bits_uop_pdest', 'input', 8),
        ('io_enq_2_req_bits_uop_robIdx_flag', 'input', 1),
        ('io_enq_2_req_bits_uop_robIdx_value', 'input', 8),
        ('io_enq_2_req_bits_uop_storeSetHit', 'input', 1),
        ('io_enq_2_req_bits_uop_waitForRobIdx_flag', 'input', 1),
        ('io_enq_2_req_bits_uop_waitForRobIdx_value', 'input', 8),
        ('io_enq_2_req_bits_uop_loadWaitBit', 'input', 1),
        ('io_enq_2_req_bits_uop_loadWaitStrict', 'input', 1),
        ('io_enq_2_req_bits_uop_lqIdx_flag', 'input', 1),
        ('io_enq_2_req_bits_uop_lqIdx_value', 'input', 7),
        ('io_enq_2_req_bits_uop_sqIdx_flag', 'input', 1),
        ('io_enq_2_req_bits_uop_sqIdx_value', 'input', 6),
        ('io_enq_2_req_bits_vaddr', 'input', 50),
        ('io_enq_2_req_bits_fullva', 'input', 64),
        ('io_enq_2_req_bits_vaNeedExt', 'input', 1),
        ('io_enq_2_req_bits_gpaddr', 'input', 64),
        ('io_enq_2_req_bits_mask', 'input', 16),
        ('io_enq_2_req_bits_isForVSnonLeafPTE', 'input', 1),
        ('io_enq_2_req_bits_isvec', 'input', 1),
        ('io_enq_2_req_bits_elemIdx', 'input', 8),
        ('io_enq_2_req_bits_alignedType', 'input', 3),
        ('io_enq_2_req_bits_mbIndex', 'input', 4),
        ('io_enq_2_req_bits_elemIdxInsideVd', 'input', 8),
        ('io_enq_2_req_bits_vecTriggerMask', 'input', 16),
        ('io_splitLoadReq_ready', 'input', 1),
        ('io_splitLoadReq_valid', 'output', 1),
        ('io_splitLoadReq_bits_uop_exceptionVec_3', 'output', 1),
        ('io_splitLoadReq_bits_uop_exceptionVec_4', 'output', 1),
        ('io_splitLoadReq_bits_uop_exceptionVec_5', 'output', 1),
        ('io_splitLoadReq_bits_uop_exceptionVec_13', 'output', 1),
        ('io_splitLoadReq_bits_uop_exceptionVec_19', 'output', 1),
        ('io_splitLoadReq_bits_uop_exceptionVec_21', 'output', 1),
        ('io_splitLoadReq_bits_uop_trigger', 'output', 4),
        ('io_splitLoadReq_bits_uop_preDecodeInfo_isRVC', 'output', 1),
        ('io_splitLoadReq_bits_uop_ftqPtr_flag', 'output', 1),
        ('io_splitLoadReq_bits_uop_ftqPtr_value', 'output', 6),
        ('io_splitLoadReq_bits_uop_ftqOffset', 'output', 4),
        ('io_splitLoadReq_bits_uop_fuOpType', 'output', 9),
        ('io_splitLoadReq_bits_uop_rfWen', 'output', 1),
        ('io_splitLoadReq_bits_uop_fpWen', 'output', 1),
        ('io_splitLoadReq_bits_uop_vpu_vstart', 'output', 8),
        ('io_splitLoadReq_bits_uop_vpu_veew', 'output', 2),
        ('io_splitLoadReq_bits_uop_uopIdx', 'output', 7),
        ('io_splitLoadReq_bits_uop_pdest', 'output', 8),
        ('io_splitLoadReq_bits_uop_robIdx_flag', 'output', 1),
        ('io_splitLoadReq_bits_uop_robIdx_value', 'output', 8),
        ('io_splitLoadReq_bits_uop_storeSetHit', 'output', 1),
        ('io_splitLoadReq_bits_uop_waitForRobIdx_flag', 'output', 1),
        ('io_splitLoadReq_bits_uop_waitForRobIdx_value', 'output', 8),
        ('io_splitLoadReq_bits_uop_loadWaitBit', 'output', 1),
        ('io_splitLoadReq_bits_uop_loadWaitStrict', 'output', 1),
        ('io_splitLoadReq_bits_uop_lqIdx_flag', 'output', 1),
        ('io_splitLoadReq_bits_uop_lqIdx_value', 'output', 7),
        ('io_splitLoadReq_bits_uop_sqIdx_flag', 'output', 1),
        ('io_splitLoadReq_bits_uop_sqIdx_value', 'output', 6),
        ('io_splitLoadReq_bits_vaddr', 'output', 50),
        ('io_splitLoadReq_bits_fullva', 'output', 64),
        ('io_splitLoadReq_bits_vaNeedExt', 'output', 1),
        ('io_splitLoadReq_bits_gpaddr', 'output', 64),
        ('io_splitLoadReq_bits_mask', 'output', 16),
        ('io_splitLoadReq_bits_nc', 'output', 1),
        ('io_splitLoadReq_bits_mmio', 'output', 1),
        ('io_splitLoadReq_bits_memBackTypeMM', 'output', 1),
        ('io_splitLoadReq_bits_isForVSnonLeafPTE', 'output', 1),
        ('io_splitLoadReq_bits_isvec', 'output', 1),
        ('io_splitLoadReq_bits_is128bit', 'output', 1),
        ('io_splitLoadReq_bits_vecActive', 'output', 1),
        ('io_splitLoadReq_bits_mshrid', 'output', 4),
        ('io_splitLoadReq_bits_schedIndex', 'output', 7),
        ('io_splitLoadReq_bits_isFinalSplit', 'output', 1),
        ('io_splitLoadReq_bits_misalignNeedWakeUp', 'output', 1),
        ('io_splitLoadResp_valid', 'input', 1),
        ('io_splitLoadResp_bits_uop_exceptionVec_3', 'input', 1),
        ('io_splitLoadResp_bits_uop_exceptionVec_4', 'input', 1),
        ('io_splitLoadResp_bits_uop_exceptionVec_5', 'input', 1),
        ('io_splitLoadResp_bits_uop_exceptionVec_13', 'input', 1),
        ('io_splitLoadResp_bits_uop_exceptionVec_19', 'input', 1),
        ('io_splitLoadResp_bits_uop_exceptionVec_21', 'input', 1),
        ('io_splitLoadResp_bits_uop_trigger', 'input', 4),
        ('io_splitLoadResp_bits_uop_robIdx_flag', 'input', 1),
        ('io_splitLoadResp_bits_uop_robIdx_value', 'input', 8),
        ('io_splitLoadResp_bits_vaddr', 'input', 50),
        ('io_splitLoadResp_bits_fullva', 'input', 64),
        ('io_splitLoadResp_bits_vaNeedExt', 'input', 1),
        ('io_splitLoadResp_bits_gpaddr', 'input', 64),
        ('io_splitLoadResp_bits_data', 'input', 129),
        ('io_splitLoadResp_bits_nc', 'input', 1),
        ('io_splitLoadResp_bits_mmio', 'input', 1),
        ('io_splitLoadResp_bits_memBackTypeMM', 'input', 1),
        ('io_splitLoadResp_bits_isForVSnonLeafPTE', 'input', 1),
        ('io_splitLoadResp_bits_vecActive', 'input', 1),
        ('io_splitLoadResp_bits_misalignNeedWakeUp', 'input', 1),
        ('io_splitLoadResp_bits_rep_info_cause_0', 'input', 1),
        ('io_splitLoadResp_bits_rep_info_cause_1', 'input', 1),
        ('io_splitLoadResp_bits_rep_info_cause_2', 'input', 1),
        ('io_splitLoadResp_bits_rep_info_cause_3', 'input', 1),
        ('io_splitLoadResp_bits_rep_info_cause_4', 'input', 1),
        ('io_splitLoadResp_bits_rep_info_cause_5', 'input', 1),
        ('io_splitLoadResp_bits_rep_info_cause_6', 'input', 1),
        ('io_splitLoadResp_bits_rep_info_cause_7', 'input', 1),
        ('io_splitLoadResp_bits_rep_info_cause_8', 'input', 1),
        ('io_splitLoadResp_bits_rep_info_cause_9', 'input', 1),
        ('io_splitLoadResp_bits_rep_info_cause_10', 'input', 1),
        ('io_writeBack_ready', 'input', 1),
        ('io_writeBack_valid', 'output', 1),
        ('io_writeBack_bits_uop_exceptionVec_3', 'output', 1),
        ('io_writeBack_bits_uop_exceptionVec_4', 'output', 1),
        ('io_writeBack_bits_uop_exceptionVec_5', 'output', 1),
        ('io_writeBack_bits_uop_exceptionVec_13', 'output', 1),
        ('io_writeBack_bits_uop_exceptionVec_19', 'output', 1),
        ('io_writeBack_bits_uop_exceptionVec_21', 'output', 1),
        ('io_writeBack_bits_uop_trigger', 'output', 4),
        ('io_writeBack_bits_uop_rfWen', 'output', 1),
        ('io_writeBack_bits_uop_fpWen', 'output', 1),
        ('io_writeBack_bits_uop_pdest', 'output', 8),
        ('io_writeBack_bits_uop_robIdx_flag', 'output', 1),
        ('io_writeBack_bits_uop_robIdx_value', 'output', 8),
        ('io_writeBack_bits_data', 'output', 64),
        ('io_writeBack_bits_debug_isMMIO', 'output', 1),
        ('io_writeBack_bits_debug_isNCIO', 'output', 1),
        ('io_vecWriteBack_valid', 'output', 1),
        ('io_vecWriteBack_bits_mBIndex', 'output', 4),
        ('io_vecWriteBack_bits_exceptionVec_3', 'output', 1),
        ('io_vecWriteBack_bits_exceptionVec_4', 'output', 1),
        ('io_vecWriteBack_bits_exceptionVec_5', 'output', 1),
        ('io_vecWriteBack_bits_exceptionVec_13', 'output', 1),
        ('io_vecWriteBack_bits_exceptionVec_19', 'output', 1),
        ('io_vecWriteBack_bits_exceptionVec_21', 'output', 1),
        ('io_vecWriteBack_bits_hasException', 'output', 1),
        ('io_vecWriteBack_bits_vaddr', 'output', 64),
        ('io_vecWriteBack_bits_vaNeedExt', 'output', 1),
        ('io_vecWriteBack_bits_gpaddr', 'output', 64),
        ('io_vecWriteBack_bits_isForVSnonLeafPTE', 'output', 1),
        ('io_vecWriteBack_bits_vstart', 'output', 8),
        ('io_vecWriteBack_bits_vecTriggerMask', 'output', 16),
        ('io_vecWriteBack_bits_elemIdx', 'output', 8),
        ('io_vecWriteBack_bits_mask', 'output', 16),
        ('io_vecWriteBack_bits_alignedType', 'output', 3),
        ('io_vecWriteBack_bits_elemIdxInsideVd', 'output', 8),
        ('io_vecWriteBack_bits_vecdata', 'output', 128),
        ('io_loadOutValid', 'input', 1),
        ('io_loadVecOutValid', 'input', 1),
    ),
    'LqExceptionBuffer': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_redirect_valid', 'input', 1),
        ('io_redirect_bits_robIdx_flag', 'input', 1),
        ('io_redirect_bits_robIdx_value', 'input', 8),
        ('io_redirect_bits_level', 'input', 1),
        ('io_req_0_valid', 'input', 1),
        ('io_req_0_bits_uop_exceptionVec_3', 'input', 1),
        ('io_req_0_bits_uop_exceptionVec_4', 'input', 1),
        ('io_req_0_bits_uop_exceptionVec_5', 'input', 1),
        ('io_req_0_bits_uop_exceptionVec_13', 'input', 1),
        ('io_req_0_bits_uop_exceptionVec_19', 'input', 1),
        ('io_req_0_bits_uop_exceptionVec_21', 'input', 1),
        ('io_req_0_bits_uop_uopIdx', 'input', 7),
        ('io_req_0_bits_uop_robIdx_flag', 'input', 1),
        ('io_req_0_bits_uop_robIdx_value', 'input', 8),
        ('io_req_0_bits_fullva', 'input', 64),
        ('io_req_0_bits_vaNeedExt', 'input', 1),
        ('io_req_0_bits_gpaddr', 'input', 64),
        ('io_req_0_bits_isHyper', 'input', 1),
        ('io_req_0_bits_isForVSnonLeafPTE', 'input', 1),
        ('io_req_1_valid', 'input', 1),
        ('io_req_1_bits_uop_exceptionVec_3', 'input', 1),
        ('io_req_1_bits_uop_exceptionVec_4', 'input', 1),
        ('io_req_1_bits_uop_exceptionVec_5', 'input', 1),
        ('io_req_1_bits_uop_exceptionVec_13', 'input', 1),
        ('io_req_1_bits_uop_exceptionVec_19', 'input', 1),
        ('io_req_1_bits_uop_exceptionVec_21', 'input', 1),
        ('io_req_1_bits_uop_uopIdx', 'input', 7),
        ('io_req_1_bits_uop_robIdx_flag', 'input', 1),
        ('io_req_1_bits_uop_robIdx_value', 'input', 8),
        ('io_req_1_bits_fullva', 'input', 64),
        ('io_req_1_bits_vaNeedExt', 'input', 1),
        ('io_req_1_bits_gpaddr', 'input', 64),
        ('io_req_1_bits_isHyper', 'input', 1),
        ('io_req_1_bits_isForVSnonLeafPTE', 'input', 1),
        ('io_req_2_valid', 'input', 1),
        ('io_req_2_bits_uop_exceptionVec_3', 'input', 1),
        ('io_req_2_bits_uop_exceptionVec_4', 'input', 1),
        ('io_req_2_bits_uop_exceptionVec_5', 'input', 1),
        ('io_req_2_bits_uop_exceptionVec_13', 'input', 1),
        ('io_req_2_bits_uop_exceptionVec_19', 'input', 1),
        ('io_req_2_bits_uop_exceptionVec_21', 'input', 1),
        ('io_req_2_bits_uop_uopIdx', 'input', 7),
        ('io_req_2_bits_uop_robIdx_flag', 'input', 1),
        ('io_req_2_bits_uop_robIdx_value', 'input', 8),
        ('io_req_2_bits_fullva', 'input', 64),
        ('io_req_2_bits_vaNeedExt', 'input', 1),
        ('io_req_2_bits_gpaddr', 'input', 64),
        ('io_req_2_bits_isHyper', 'input', 1),
        ('io_req_2_bits_isForVSnonLeafPTE', 'input', 1),
        ('io_req_3_valid', 'input', 1),
        ('io_req_3_bits_uop_exceptionVec_3', 'input', 1),
        ('io_req_3_bits_uop_exceptionVec_4', 'input', 1),
        ('io_req_3_bits_uop_exceptionVec_5', 'input', 1),
        ('io_req_3_bits_uop_exceptionVec_13', 'input', 1),
        ('io_req_3_bits_uop_exceptionVec_19', 'input', 1),
        ('io_req_3_bits_uop_exceptionVec_21', 'input', 1),
        ('io_req_3_bits_uop_uopIdx', 'input', 7),
        ('io_req_3_bits_uop_robIdx_flag', 'input', 1),
        ('io_req_3_bits_uop_robIdx_value', 'input', 8),
        ('io_req_3_bits_fullva', 'input', 64),
        ('io_req_3_bits_vaNeedExt', 'input', 1),
        ('io_req_3_bits_gpaddr', 'input', 64),
        ('io_req_3_bits_isForVSnonLeafPTE', 'input', 1),
        ('io_req_4_valid', 'input', 1),
        ('io_req_4_bits_uop_exceptionVec_3', 'input', 1),
        ('io_req_4_bits_uop_exceptionVec_4', 'input', 1),
        ('io_req_4_bits_uop_exceptionVec_5', 'input', 1),
        ('io_req_4_bits_uop_exceptionVec_13', 'input', 1),
        ('io_req_4_bits_uop_exceptionVec_19', 'input', 1),
        ('io_req_4_bits_uop_exceptionVec_21', 'input', 1),
        ('io_req_4_bits_uop_uopIdx', 'input', 7),
        ('io_req_4_bits_uop_robIdx_flag', 'input', 1),
        ('io_req_4_bits_uop_robIdx_value', 'input', 8),
        ('io_req_4_bits_fullva', 'input', 64),
        ('io_req_4_bits_vaNeedExt', 'input', 1),
        ('io_req_4_bits_gpaddr', 'input', 64),
        ('io_req_4_bits_isForVSnonLeafPTE', 'input', 1),
        ('io_req_5_valid', 'input', 1),
        ('io_req_5_bits_uop_exceptionVec_3', 'input', 1),
        ('io_req_5_bits_uop_exceptionVec_4', 'input', 1),
        ('io_req_5_bits_uop_exceptionVec_5', 'input', 1),
        ('io_req_5_bits_uop_exceptionVec_13', 'input', 1),
        ('io_req_5_bits_uop_exceptionVec_19', 'input', 1),
        ('io_req_5_bits_uop_exceptionVec_21', 'input', 1),
        ('io_req_5_bits_uop_uopIdx', 'input', 7),
        ('io_req_5_bits_uop_robIdx_flag', 'input', 1),
        ('io_req_5_bits_uop_robIdx_value', 'input', 8),
        ('io_req_5_bits_fullva', 'input', 64),
        ('io_req_5_bits_gpaddr', 'input', 64),
        ('io_req_5_bits_isHyper', 'input', 1),
        ('io_req_5_bits_isForVSnonLeafPTE', 'input', 1),
        ('io_exceptionAddr_vaddr', 'output', 64),
        ('io_exceptionAddr_vaNeedExt', 'output', 1),
        ('io_exceptionAddr_isHyper', 'output', 1),
        ('io_exceptionAddr_gpaddr', 'output', 64),
        ('io_exceptionAddr_isForVSnonLeafPTE', 'output', 1),
    ),
    'LsqEnqCtrl': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_redirect_valid', 'input', 1),
        ('io_enq_canAccept', 'output', 1),
        ('io_enq_needAlloc_0', 'input', 2),
        ('io_enq_needAlloc_1', 'input', 2),
        ('io_enq_needAlloc_2', 'input', 2),
        ('io_enq_needAlloc_3', 'input', 2),
        ('io_enq_needAlloc_4', 'input', 2),
        ('io_enq_needAlloc_5', 'input', 2),
        ('io_enq_req_0_valid', 'input', 1),
        ('io_enq_req_0_bits_exceptionVec_0', 'input', 1),
        ('io_enq_req_0_bits_exceptionVec_1', 'input', 1),
        ('io_enq_req_0_bits_exceptionVec_2', 'input', 1),
        ('io_enq_req_0_bits_exceptionVec_3', 'input', 1),
        ('io_enq_req_0_bits_exceptionVec_4', 'input', 1),
        ('io_enq_req_0_bits_exceptionVec_5', 'input', 1),
        ('io_enq_req_0_bits_exceptionVec_6', 'input', 1),
        ('io_enq_req_0_bits_exceptionVec_7', 'input', 1),
        ('io_enq_req_0_bits_exceptionVec_8', 'input', 1),
        ('io_enq_req_0_bits_exceptionVec_9', 'input', 1),
        ('io_enq_req_0_bits_exceptionVec_10', 'input', 1),
        ('io_enq_req_0_bits_exceptionVec_11', 'input', 1),
        ('io_enq_req_0_bits_exceptionVec_12', 'input', 1),
        ('io_enq_req_0_bits_exceptionVec_13', 'input', 1),
        ('io_enq_req_0_bits_exceptionVec_14', 'input', 1),
        ('io_enq_req_0_bits_exceptionVec_15', 'input', 1),
        ('io_enq_req_0_bits_exceptionVec_16', 'input', 1),
        ('io_enq_req_0_bits_exceptionVec_17', 'input', 1),
        ('io_enq_req_0_bits_exceptionVec_18', 'input', 1),
        ('io_enq_req_0_bits_exceptionVec_19', 'input', 1),
        ('io_enq_req_0_bits_exceptionVec_20', 'input', 1),
        ('io_enq_req_0_bits_exceptionVec_21', 'input', 1),
        ('io_enq_req_0_bits_exceptionVec_22', 'input', 1),
        ('io_enq_req_0_bits_exceptionVec_23', 'input', 1),
        ('io_enq_req_0_bits_trigger', 'input', 4),
        ('io_enq_req_0_bits_fuType', 'input', 35),
        ('io_enq_req_0_bits_fuOpType', 'input', 9),
        ('io_enq_req_0_bits_flushPipe', 'input', 1),
        ('io_enq_req_0_bits_uopIdx', 'input', 7),
        ('io_enq_req_0_bits_lastUop', 'input', 1),
        ('io_enq_req_0_bits_robIdx_flag', 'input', 1),
        ('io_enq_req_0_bits_robIdx_value', 'input', 8),
        ('io_enq_req_0_bits_numLsElem', 'input', 5),
        ('io_enq_req_1_valid', 'input', 1),
        ('io_enq_req_1_bits_exceptionVec_0', 'input', 1),
        ('io_enq_req_1_bits_exceptionVec_1', 'input', 1),
        ('io_enq_req_1_bits_exceptionVec_2', 'input', 1),
        ('io_enq_req_1_bits_exceptionVec_3', 'input', 1),
        ('io_enq_req_1_bits_exceptionVec_4', 'input', 1),
        ('io_enq_req_1_bits_exceptionVec_5', 'input', 1),
        ('io_enq_req_1_bits_exceptionVec_6', 'input', 1),
        ('io_enq_req_1_bits_exceptionVec_7', 'input', 1),
        ('io_enq_req_1_bits_exceptionVec_8', 'input', 1),
        ('io_enq_req_1_bits_exceptionVec_9', 'input', 1),
        ('io_enq_req_1_bits_exceptionVec_10', 'input', 1),
        ('io_enq_req_1_bits_exceptionVec_11', 'input', 1),
        ('io_enq_req_1_bits_exceptionVec_12', 'input', 1),
        ('io_enq_req_1_bits_exceptionVec_13', 'input', 1),
        ('io_enq_req_1_bits_exceptionVec_14', 'input', 1),
        ('io_enq_req_1_bits_exceptionVec_15', 'input', 1),
        ('io_enq_req_1_bits_exceptionVec_16', 'input', 1),
        ('io_enq_req_1_bits_exceptionVec_17', 'input', 1),
        ('io_enq_req_1_bits_exceptionVec_18', 'input', 1),
        ('io_enq_req_1_bits_exceptionVec_19', 'input', 1),
        ('io_enq_req_1_bits_exceptionVec_20', 'input', 1),
        ('io_enq_req_1_bits_exceptionVec_21', 'input', 1),
        ('io_enq_req_1_bits_exceptionVec_22', 'input', 1),
        ('io_enq_req_1_bits_exceptionVec_23', 'input', 1),
        ('io_enq_req_1_bits_trigger', 'input', 4),
        ('io_enq_req_1_bits_fuType', 'input', 35),
        ('io_enq_req_1_bits_fuOpType', 'input', 9),
        ('io_enq_req_1_bits_flushPipe', 'input', 1),
        ('io_enq_req_1_bits_uopIdx', 'input', 7),
        ('io_enq_req_1_bits_lastUop', 'input', 1),
        ('io_enq_req_1_bits_robIdx_flag', 'input', 1),
        ('io_enq_req_1_bits_robIdx_value', 'input', 8),
        ('io_enq_req_1_bits_numLsElem', 'input', 5),
        ('io_enq_req_2_valid', 'input', 1),
        ('io_enq_req_2_bits_exceptionVec_0', 'input', 1),
        ('io_enq_req_2_bits_exceptionVec_1', 'input', 1),
        ('io_enq_req_2_bits_exceptionVec_2', 'input', 1),
        ('io_enq_req_2_bits_exceptionVec_3', 'input', 1),
        ('io_enq_req_2_bits_exceptionVec_4', 'input', 1),
        ('io_enq_req_2_bits_exceptionVec_5', 'input', 1),
        ('io_enq_req_2_bits_exceptionVec_6', 'input', 1),
        ('io_enq_req_2_bits_exceptionVec_7', 'input', 1),
        ('io_enq_req_2_bits_exceptionVec_8', 'input', 1),
        ('io_enq_req_2_bits_exceptionVec_9', 'input', 1),
        ('io_enq_req_2_bits_exceptionVec_10', 'input', 1),
        ('io_enq_req_2_bits_exceptionVec_11', 'input', 1),
        ('io_enq_req_2_bits_exceptionVec_12', 'input', 1),
        ('io_enq_req_2_bits_exceptionVec_13', 'input', 1),
        ('io_enq_req_2_bits_exceptionVec_14', 'input', 1),
        ('io_enq_req_2_bits_exceptionVec_15', 'input', 1),
        ('io_enq_req_2_bits_exceptionVec_16', 'input', 1),
        ('io_enq_req_2_bits_exceptionVec_17', 'input', 1),
        ('io_enq_req_2_bits_exceptionVec_18', 'input', 1),
        ('io_enq_req_2_bits_exceptionVec_19', 'input', 1),
        ('io_enq_req_2_bits_exceptionVec_20', 'input', 1),
        ('io_enq_req_2_bits_exceptionVec_21', 'input', 1),
        ('io_enq_req_2_bits_exceptionVec_22', 'input', 1),
        ('io_enq_req_2_bits_exceptionVec_23', 'input', 1),
        ('io_enq_req_2_bits_trigger', 'input', 4),
        ('io_enq_req_2_bits_fuType', 'input', 35),
        ('io_enq_req_2_bits_fuOpType', 'input', 9),
        ('io_enq_req_2_bits_flushPipe', 'input', 1),
        ('io_enq_req_2_bits_uopIdx', 'input', 7),
        ('io_enq_req_2_bits_lastUop', 'input', 1),
        ('io_enq_req_2_bits_robIdx_flag', 'input', 1),
        ('io_enq_req_2_bits_robIdx_value', 'input', 8),
        ('io_enq_req_2_bits_numLsElem', 'input', 5),
        ('io_enq_req_3_valid', 'input', 1),
        ('io_enq_req_3_bits_exceptionVec_0', 'input', 1),
        ('io_enq_req_3_bits_exceptionVec_1', 'input', 1),
        ('io_enq_req_3_bits_exceptionVec_2', 'input', 1),
        ('io_enq_req_3_bits_exceptionVec_3', 'input', 1),
        ('io_enq_req_3_bits_exceptionVec_4', 'input', 1),
        ('io_enq_req_3_bits_exceptionVec_5', 'input', 1),
        ('io_enq_req_3_bits_exceptionVec_6', 'input', 1),
        ('io_enq_req_3_bits_exceptionVec_7', 'input', 1),
        ('io_enq_req_3_bits_exceptionVec_8', 'input', 1),
        ('io_enq_req_3_bits_exceptionVec_9', 'input', 1),
        ('io_enq_req_3_bits_exceptionVec_10', 'input', 1),
        ('io_enq_req_3_bits_exceptionVec_11', 'input', 1),
        ('io_enq_req_3_bits_exceptionVec_12', 'input', 1),
        ('io_enq_req_3_bits_exceptionVec_13', 'input', 1),
        ('io_enq_req_3_bits_exceptionVec_14', 'input', 1),
        ('io_enq_req_3_bits_exceptionVec_15', 'input', 1),
        ('io_enq_req_3_bits_exceptionVec_16', 'input', 1),
        ('io_enq_req_3_bits_exceptionVec_17', 'input', 1),
        ('io_enq_req_3_bits_exceptionVec_18', 'input', 1),
        ('io_enq_req_3_bits_exceptionVec_19', 'input', 1),
        ('io_enq_req_3_bits_exceptionVec_20', 'input', 1),
        ('io_enq_req_3_bits_exceptionVec_21', 'input', 1),
        ('io_enq_req_3_bits_exceptionVec_22', 'input', 1),
        ('io_enq_req_3_bits_exceptionVec_23', 'input', 1),
        ('io_enq_req_3_bits_trigger', 'input', 4),
        ('io_enq_req_3_bits_fuType', 'input', 35),
        ('io_enq_req_3_bits_fuOpType', 'input', 9),
        ('io_enq_req_3_bits_flushPipe', 'input', 1),
        ('io_enq_req_3_bits_uopIdx', 'input', 7),
        ('io_enq_req_3_bits_lastUop', 'input', 1),
        ('io_enq_req_3_bits_robIdx_flag', 'input', 1),
        ('io_enq_req_3_bits_robIdx_value', 'input', 8),
        ('io_enq_req_3_bits_numLsElem', 'input', 5),
        ('io_enq_req_4_valid', 'input', 1),
        ('io_enq_req_4_bits_exceptionVec_0', 'input', 1),
        ('io_enq_req_4_bits_exceptionVec_1', 'input', 1),
        ('io_enq_req_4_bits_exceptionVec_2', 'input', 1),
        ('io_enq_req_4_bits_exceptionVec_3', 'input', 1),
        ('io_enq_req_4_bits_exceptionVec_4', 'input', 1),
        ('io_enq_req_4_bits_exceptionVec_5', 'input', 1),
        ('io_enq_req_4_bits_exceptionVec_6', 'input', 1),
        ('io_enq_req_4_bits_exceptionVec_7', 'input', 1),
        ('io_enq_req_4_bits_exceptionVec_8', 'input', 1),
        ('io_enq_req_4_bits_exceptionVec_9', 'input', 1),
        ('io_enq_req_4_bits_exceptionVec_10', 'input', 1),
        ('io_enq_req_4_bits_exceptionVec_11', 'input', 1),
        ('io_enq_req_4_bits_exceptionVec_12', 'input', 1),
        ('io_enq_req_4_bits_exceptionVec_13', 'input', 1),
        ('io_enq_req_4_bits_exceptionVec_14', 'input', 1),
        ('io_enq_req_4_bits_exceptionVec_15', 'input', 1),
        ('io_enq_req_4_bits_exceptionVec_16', 'input', 1),
        ('io_enq_req_4_bits_exceptionVec_17', 'input', 1),
        ('io_enq_req_4_bits_exceptionVec_18', 'input', 1),
        ('io_enq_req_4_bits_exceptionVec_19', 'input', 1),
        ('io_enq_req_4_bits_exceptionVec_20', 'input', 1),
        ('io_enq_req_4_bits_exceptionVec_21', 'input', 1),
        ('io_enq_req_4_bits_exceptionVec_22', 'input', 1),
        ('io_enq_req_4_bits_exceptionVec_23', 'input', 1),
        ('io_enq_req_4_bits_trigger', 'input', 4),
        ('io_enq_req_4_bits_fuType', 'input', 35),
        ('io_enq_req_4_bits_fuOpType', 'input', 9),
        ('io_enq_req_4_bits_flushPipe', 'input', 1),
        ('io_enq_req_4_bits_uopIdx', 'input', 7),
        ('io_enq_req_4_bits_lastUop', 'input', 1),
        ('io_enq_req_4_bits_robIdx_flag', 'input', 1),
        ('io_enq_req_4_bits_robIdx_value', 'input', 8),
        ('io_enq_req_4_bits_numLsElem', 'input', 5),
        ('io_enq_req_5_valid', 'input', 1),
        ('io_enq_req_5_bits_exceptionVec_0', 'input', 1),
        ('io_enq_req_5_bits_exceptionVec_1', 'input', 1),
        ('io_enq_req_5_bits_exceptionVec_2', 'input', 1),
        ('io_enq_req_5_bits_exceptionVec_3', 'input', 1),
        ('io_enq_req_5_bits_exceptionVec_4', 'input', 1),
        ('io_enq_req_5_bits_exceptionVec_5', 'input', 1),
        ('io_enq_req_5_bits_exceptionVec_6', 'input', 1),
        ('io_enq_req_5_bits_exceptionVec_7', 'input', 1),
        ('io_enq_req_5_bits_exceptionVec_8', 'input', 1),
        ('io_enq_req_5_bits_exceptionVec_9', 'input', 1),
        ('io_enq_req_5_bits_exceptionVec_10', 'input', 1),
        ('io_enq_req_5_bits_exceptionVec_11', 'input', 1),
        ('io_enq_req_5_bits_exceptionVec_12', 'input', 1),
        ('io_enq_req_5_bits_exceptionVec_13', 'input', 1),
        ('io_enq_req_5_bits_exceptionVec_14', 'input', 1),
        ('io_enq_req_5_bits_exceptionVec_15', 'input', 1),
        ('io_enq_req_5_bits_exceptionVec_16', 'input', 1),
        ('io_enq_req_5_bits_exceptionVec_17', 'input', 1),
        ('io_enq_req_5_bits_exceptionVec_18', 'input', 1),
        ('io_enq_req_5_bits_exceptionVec_19', 'input', 1),
        ('io_enq_req_5_bits_exceptionVec_20', 'input', 1),
        ('io_enq_req_5_bits_exceptionVec_21', 'input', 1),
        ('io_enq_req_5_bits_exceptionVec_22', 'input', 1),
        ('io_enq_req_5_bits_exceptionVec_23', 'input', 1),
        ('io_enq_req_5_bits_trigger', 'input', 4),
        ('io_enq_req_5_bits_fuType', 'input', 35),
        ('io_enq_req_5_bits_fuOpType', 'input', 9),
        ('io_enq_req_5_bits_flushPipe', 'input', 1),
        ('io_enq_req_5_bits_uopIdx', 'input', 7),
        ('io_enq_req_5_bits_lastUop', 'input', 1),
        ('io_enq_req_5_bits_robIdx_flag', 'input', 1),
        ('io_enq_req_5_bits_robIdx_value', 'input', 8),
        ('io_enq_req_5_bits_numLsElem', 'input', 5),
        ('io_enq_iqAccept_0', 'input', 1),
        ('io_enq_iqAccept_1', 'input', 1),
        ('io_enq_iqAccept_2', 'input', 1),
        ('io_enq_iqAccept_3', 'input', 1),
        ('io_enq_iqAccept_4', 'input', 1),
        ('io_enq_iqAccept_5', 'input', 1),
        ('io_enq_resp_0_lqIdx_flag', 'output', 1),
        ('io_enq_resp_0_lqIdx_value', 'output', 7),
        ('io_enq_resp_0_sqIdx_flag', 'output', 1),
        ('io_enq_resp_0_sqIdx_value', 'output', 6),
        ('io_enq_resp_1_lqIdx_flag', 'output', 1),
        ('io_enq_resp_1_lqIdx_value', 'output', 7),
        ('io_enq_resp_1_sqIdx_flag', 'output', 1),
        ('io_enq_resp_1_sqIdx_value', 'output', 6),
        ('io_enq_resp_2_lqIdx_flag', 'output', 1),
        ('io_enq_resp_2_lqIdx_value', 'output', 7),
        ('io_enq_resp_2_sqIdx_flag', 'output', 1),
        ('io_enq_resp_2_sqIdx_value', 'output', 6),
        ('io_enq_resp_3_lqIdx_flag', 'output', 1),
        ('io_enq_resp_3_lqIdx_value', 'output', 7),
        ('io_enq_resp_3_sqIdx_flag', 'output', 1),
        ('io_enq_resp_3_sqIdx_value', 'output', 6),
        ('io_enq_resp_4_lqIdx_flag', 'output', 1),
        ('io_enq_resp_4_lqIdx_value', 'output', 7),
        ('io_enq_resp_4_sqIdx_flag', 'output', 1),
        ('io_enq_resp_4_sqIdx_value', 'output', 6),
        ('io_enq_resp_5_lqIdx_flag', 'output', 1),
        ('io_enq_resp_5_lqIdx_value', 'output', 7),
        ('io_enq_resp_5_sqIdx_flag', 'output', 1),
        ('io_enq_resp_5_sqIdx_value', 'output', 6),
        ('io_lcommit', 'input', 4),
        ('io_scommit', 'input', 2),
        ('io_lqCancelCnt', 'input', 7),
        ('io_sqCancelCnt', 'input', 6),
        ('io_lqFreeCount', 'output', 7),
        ('io_sqFreeCount', 'output', 6),
        ('io_enqLsq_needAlloc_0', 'output', 2),
        ('io_enqLsq_needAlloc_1', 'output', 2),
        ('io_enqLsq_needAlloc_2', 'output', 2),
        ('io_enqLsq_needAlloc_3', 'output', 2),
        ('io_enqLsq_needAlloc_4', 'output', 2),
        ('io_enqLsq_needAlloc_5', 'output', 2),
        ('io_enqLsq_req_0_valid', 'output', 1),
        ('io_enqLsq_req_0_bits_exceptionVec_0', 'output', 1),
        ('io_enqLsq_req_0_bits_exceptionVec_1', 'output', 1),
        ('io_enqLsq_req_0_bits_exceptionVec_2', 'output', 1),
        ('io_enqLsq_req_0_bits_exceptionVec_3', 'output', 1),
        ('io_enqLsq_req_0_bits_exceptionVec_4', 'output', 1),
        ('io_enqLsq_req_0_bits_exceptionVec_5', 'output', 1),
        ('io_enqLsq_req_0_bits_exceptionVec_6', 'output', 1),
        ('io_enqLsq_req_0_bits_exceptionVec_7', 'output', 1),
        ('io_enqLsq_req_0_bits_exceptionVec_8', 'output', 1),
        ('io_enqLsq_req_0_bits_exceptionVec_9', 'output', 1),
        ('io_enqLsq_req_0_bits_exceptionVec_10', 'output', 1),
        ('io_enqLsq_req_0_bits_exceptionVec_11', 'output', 1),
        ('io_enqLsq_req_0_bits_exceptionVec_12', 'output', 1),
        ('io_enqLsq_req_0_bits_exceptionVec_13', 'output', 1),
        ('io_enqLsq_req_0_bits_exceptionVec_14', 'output', 1),
        ('io_enqLsq_req_0_bits_exceptionVec_15', 'output', 1),
        ('io_enqLsq_req_0_bits_exceptionVec_16', 'output', 1),
        ('io_enqLsq_req_0_bits_exceptionVec_17', 'output', 1),
        ('io_enqLsq_req_0_bits_exceptionVec_18', 'output', 1),
        ('io_enqLsq_req_0_bits_exceptionVec_19', 'output', 1),
        ('io_enqLsq_req_0_bits_exceptionVec_20', 'output', 1),
        ('io_enqLsq_req_0_bits_exceptionVec_21', 'output', 1),
        ('io_enqLsq_req_0_bits_exceptionVec_22', 'output', 1),
        ('io_enqLsq_req_0_bits_exceptionVec_23', 'output', 1),
        ('io_enqLsq_req_0_bits_trigger', 'output', 4),
        ('io_enqLsq_req_0_bits_fuType', 'output', 35),
        ('io_enqLsq_req_0_bits_fuOpType', 'output', 9),
        ('io_enqLsq_req_0_bits_flushPipe', 'output', 1),
        ('io_enqLsq_req_0_bits_uopIdx', 'output', 7),
        ('io_enqLsq_req_0_bits_lastUop', 'output', 1),
        ('io_enqLsq_req_0_bits_robIdx_flag', 'output', 1),
        ('io_enqLsq_req_0_bits_robIdx_value', 'output', 8),
        ('io_enqLsq_req_0_bits_lqIdx_flag', 'output', 1),
        ('io_enqLsq_req_0_bits_lqIdx_value', 'output', 7),
        ('io_enqLsq_req_0_bits_sqIdx_flag', 'output', 1),
        ('io_enqLsq_req_0_bits_sqIdx_value', 'output', 6),
        ('io_enqLsq_req_0_bits_numLsElem', 'output', 5),
        ('io_enqLsq_req_1_valid', 'output', 1),
        ('io_enqLsq_req_1_bits_exceptionVec_0', 'output', 1),
        ('io_enqLsq_req_1_bits_exceptionVec_1', 'output', 1),
        ('io_enqLsq_req_1_bits_exceptionVec_2', 'output', 1),
        ('io_enqLsq_req_1_bits_exceptionVec_3', 'output', 1),
        ('io_enqLsq_req_1_bits_exceptionVec_4', 'output', 1),
        ('io_enqLsq_req_1_bits_exceptionVec_5', 'output', 1),
        ('io_enqLsq_req_1_bits_exceptionVec_6', 'output', 1),
        ('io_enqLsq_req_1_bits_exceptionVec_7', 'output', 1),
        ('io_enqLsq_req_1_bits_exceptionVec_8', 'output', 1),
        ('io_enqLsq_req_1_bits_exceptionVec_9', 'output', 1),
        ('io_enqLsq_req_1_bits_exceptionVec_10', 'output', 1),
        ('io_enqLsq_req_1_bits_exceptionVec_11', 'output', 1),
        ('io_enqLsq_req_1_bits_exceptionVec_12', 'output', 1),
        ('io_enqLsq_req_1_bits_exceptionVec_13', 'output', 1),
        ('io_enqLsq_req_1_bits_exceptionVec_14', 'output', 1),
        ('io_enqLsq_req_1_bits_exceptionVec_15', 'output', 1),
        ('io_enqLsq_req_1_bits_exceptionVec_16', 'output', 1),
        ('io_enqLsq_req_1_bits_exceptionVec_17', 'output', 1),
        ('io_enqLsq_req_1_bits_exceptionVec_18', 'output', 1),
        ('io_enqLsq_req_1_bits_exceptionVec_19', 'output', 1),
        ('io_enqLsq_req_1_bits_exceptionVec_20', 'output', 1),
        ('io_enqLsq_req_1_bits_exceptionVec_21', 'output', 1),
        ('io_enqLsq_req_1_bits_exceptionVec_22', 'output', 1),
        ('io_enqLsq_req_1_bits_exceptionVec_23', 'output', 1),
        ('io_enqLsq_req_1_bits_trigger', 'output', 4),
        ('io_enqLsq_req_1_bits_fuType', 'output', 35),
        ('io_enqLsq_req_1_bits_fuOpType', 'output', 9),
        ('io_enqLsq_req_1_bits_flushPipe', 'output', 1),
        ('io_enqLsq_req_1_bits_uopIdx', 'output', 7),
        ('io_enqLsq_req_1_bits_lastUop', 'output', 1),
        ('io_enqLsq_req_1_bits_robIdx_flag', 'output', 1),
        ('io_enqLsq_req_1_bits_robIdx_value', 'output', 8),
        ('io_enqLsq_req_1_bits_lqIdx_flag', 'output', 1),
        ('io_enqLsq_req_1_bits_lqIdx_value', 'output', 7),
        ('io_enqLsq_req_1_bits_sqIdx_flag', 'output', 1),
        ('io_enqLsq_req_1_bits_sqIdx_value', 'output', 6),
        ('io_enqLsq_req_1_bits_numLsElem', 'output', 5),
        ('io_enqLsq_req_2_valid', 'output', 1),
        ('io_enqLsq_req_2_bits_exceptionVec_0', 'output', 1),
        ('io_enqLsq_req_2_bits_exceptionVec_1', 'output', 1),
        ('io_enqLsq_req_2_bits_exceptionVec_2', 'output', 1),
        ('io_enqLsq_req_2_bits_exceptionVec_3', 'output', 1),
        ('io_enqLsq_req_2_bits_exceptionVec_4', 'output', 1),
        ('io_enqLsq_req_2_bits_exceptionVec_5', 'output', 1),
        ('io_enqLsq_req_2_bits_exceptionVec_6', 'output', 1),
        ('io_enqLsq_req_2_bits_exceptionVec_7', 'output', 1),
        ('io_enqLsq_req_2_bits_exceptionVec_8', 'output', 1),
        ('io_enqLsq_req_2_bits_exceptionVec_9', 'output', 1),
        ('io_enqLsq_req_2_bits_exceptionVec_10', 'output', 1),
        ('io_enqLsq_req_2_bits_exceptionVec_11', 'output', 1),
        ('io_enqLsq_req_2_bits_exceptionVec_12', 'output', 1),
        ('io_enqLsq_req_2_bits_exceptionVec_13', 'output', 1),
        ('io_enqLsq_req_2_bits_exceptionVec_14', 'output', 1),
        ('io_enqLsq_req_2_bits_exceptionVec_15', 'output', 1),
        ('io_enqLsq_req_2_bits_exceptionVec_16', 'output', 1),
        ('io_enqLsq_req_2_bits_exceptionVec_17', 'output', 1),
        ('io_enqLsq_req_2_bits_exceptionVec_18', 'output', 1),
        ('io_enqLsq_req_2_bits_exceptionVec_19', 'output', 1),
        ('io_enqLsq_req_2_bits_exceptionVec_20', 'output', 1),
        ('io_enqLsq_req_2_bits_exceptionVec_21', 'output', 1),
        ('io_enqLsq_req_2_bits_exceptionVec_22', 'output', 1),
        ('io_enqLsq_req_2_bits_exceptionVec_23', 'output', 1),
        ('io_enqLsq_req_2_bits_trigger', 'output', 4),
        ('io_enqLsq_req_2_bits_fuType', 'output', 35),
        ('io_enqLsq_req_2_bits_fuOpType', 'output', 9),
        ('io_enqLsq_req_2_bits_flushPipe', 'output', 1),
        ('io_enqLsq_req_2_bits_uopIdx', 'output', 7),
        ('io_enqLsq_req_2_bits_lastUop', 'output', 1),
        ('io_enqLsq_req_2_bits_robIdx_flag', 'output', 1),
        ('io_enqLsq_req_2_bits_robIdx_value', 'output', 8),
        ('io_enqLsq_req_2_bits_lqIdx_flag', 'output', 1),
        ('io_enqLsq_req_2_bits_lqIdx_value', 'output', 7),
        ('io_enqLsq_req_2_bits_sqIdx_flag', 'output', 1),
        ('io_enqLsq_req_2_bits_sqIdx_value', 'output', 6),
        ('io_enqLsq_req_2_bits_numLsElem', 'output', 5),
        ('io_enqLsq_req_3_valid', 'output', 1),
        ('io_enqLsq_req_3_bits_exceptionVec_0', 'output', 1),
        ('io_enqLsq_req_3_bits_exceptionVec_1', 'output', 1),
        ('io_enqLsq_req_3_bits_exceptionVec_2', 'output', 1),
        ('io_enqLsq_req_3_bits_exceptionVec_3', 'output', 1),
        ('io_enqLsq_req_3_bits_exceptionVec_4', 'output', 1),
        ('io_enqLsq_req_3_bits_exceptionVec_5', 'output', 1),
        ('io_enqLsq_req_3_bits_exceptionVec_6', 'output', 1),
        ('io_enqLsq_req_3_bits_exceptionVec_7', 'output', 1),
        ('io_enqLsq_req_3_bits_exceptionVec_8', 'output', 1),
        ('io_enqLsq_req_3_bits_exceptionVec_9', 'output', 1),
        ('io_enqLsq_req_3_bits_exceptionVec_10', 'output', 1),
        ('io_enqLsq_req_3_bits_exceptionVec_11', 'output', 1),
        ('io_enqLsq_req_3_bits_exceptionVec_12', 'output', 1),
        ('io_enqLsq_req_3_bits_exceptionVec_13', 'output', 1),
        ('io_enqLsq_req_3_bits_exceptionVec_14', 'output', 1),
        ('io_enqLsq_req_3_bits_exceptionVec_15', 'output', 1),
        ('io_enqLsq_req_3_bits_exceptionVec_16', 'output', 1),
        ('io_enqLsq_req_3_bits_exceptionVec_17', 'output', 1),
        ('io_enqLsq_req_3_bits_exceptionVec_18', 'output', 1),
        ('io_enqLsq_req_3_bits_exceptionVec_19', 'output', 1),
        ('io_enqLsq_req_3_bits_exceptionVec_20', 'output', 1),
        ('io_enqLsq_req_3_bits_exceptionVec_21', 'output', 1),
        ('io_enqLsq_req_3_bits_exceptionVec_22', 'output', 1),
        ('io_enqLsq_req_3_bits_exceptionVec_23', 'output', 1),
        ('io_enqLsq_req_3_bits_trigger', 'output', 4),
        ('io_enqLsq_req_3_bits_fuType', 'output', 35),
        ('io_enqLsq_req_3_bits_fuOpType', 'output', 9),
        ('io_enqLsq_req_3_bits_flushPipe', 'output', 1),
        ('io_enqLsq_req_3_bits_uopIdx', 'output', 7),
        ('io_enqLsq_req_3_bits_lastUop', 'output', 1),
        ('io_enqLsq_req_3_bits_robIdx_flag', 'output', 1),
        ('io_enqLsq_req_3_bits_robIdx_value', 'output', 8),
        ('io_enqLsq_req_3_bits_lqIdx_flag', 'output', 1),
        ('io_enqLsq_req_3_bits_lqIdx_value', 'output', 7),
        ('io_enqLsq_req_3_bits_sqIdx_flag', 'output', 1),
        ('io_enqLsq_req_3_bits_sqIdx_value', 'output', 6),
        ('io_enqLsq_req_3_bits_numLsElem', 'output', 5),
        ('io_enqLsq_req_4_valid', 'output', 1),
        ('io_enqLsq_req_4_bits_exceptionVec_0', 'output', 1),
        ('io_enqLsq_req_4_bits_exceptionVec_1', 'output', 1),
        ('io_enqLsq_req_4_bits_exceptionVec_2', 'output', 1),
        ('io_enqLsq_req_4_bits_exceptionVec_3', 'output', 1),
        ('io_enqLsq_req_4_bits_exceptionVec_4', 'output', 1),
        ('io_enqLsq_req_4_bits_exceptionVec_5', 'output', 1),
        ('io_enqLsq_req_4_bits_exceptionVec_6', 'output', 1),
        ('io_enqLsq_req_4_bits_exceptionVec_7', 'output', 1),
        ('io_enqLsq_req_4_bits_exceptionVec_8', 'output', 1),
        ('io_enqLsq_req_4_bits_exceptionVec_9', 'output', 1),
        ('io_enqLsq_req_4_bits_exceptionVec_10', 'output', 1),
        ('io_enqLsq_req_4_bits_exceptionVec_11', 'output', 1),
        ('io_enqLsq_req_4_bits_exceptionVec_12', 'output', 1),
        ('io_enqLsq_req_4_bits_exceptionVec_13', 'output', 1),
        ('io_enqLsq_req_4_bits_exceptionVec_14', 'output', 1),
        ('io_enqLsq_req_4_bits_exceptionVec_15', 'output', 1),
        ('io_enqLsq_req_4_bits_exceptionVec_16', 'output', 1),
        ('io_enqLsq_req_4_bits_exceptionVec_17', 'output', 1),
        ('io_enqLsq_req_4_bits_exceptionVec_18', 'output', 1),
        ('io_enqLsq_req_4_bits_exceptionVec_19', 'output', 1),
        ('io_enqLsq_req_4_bits_exceptionVec_20', 'output', 1),
        ('io_enqLsq_req_4_bits_exceptionVec_21', 'output', 1),
        ('io_enqLsq_req_4_bits_exceptionVec_22', 'output', 1),
        ('io_enqLsq_req_4_bits_exceptionVec_23', 'output', 1),
        ('io_enqLsq_req_4_bits_trigger', 'output', 4),
        ('io_enqLsq_req_4_bits_fuType', 'output', 35),
        ('io_enqLsq_req_4_bits_fuOpType', 'output', 9),
        ('io_enqLsq_req_4_bits_flushPipe', 'output', 1),
        ('io_enqLsq_req_4_bits_uopIdx', 'output', 7),
        ('io_enqLsq_req_4_bits_lastUop', 'output', 1),
        ('io_enqLsq_req_4_bits_robIdx_flag', 'output', 1),
        ('io_enqLsq_req_4_bits_robIdx_value', 'output', 8),
        ('io_enqLsq_req_4_bits_lqIdx_flag', 'output', 1),
        ('io_enqLsq_req_4_bits_lqIdx_value', 'output', 7),
        ('io_enqLsq_req_4_bits_sqIdx_flag', 'output', 1),
        ('io_enqLsq_req_4_bits_sqIdx_value', 'output', 6),
        ('io_enqLsq_req_4_bits_numLsElem', 'output', 5),
        ('io_enqLsq_req_5_valid', 'output', 1),
        ('io_enqLsq_req_5_bits_exceptionVec_0', 'output', 1),
        ('io_enqLsq_req_5_bits_exceptionVec_1', 'output', 1),
        ('io_enqLsq_req_5_bits_exceptionVec_2', 'output', 1),
        ('io_enqLsq_req_5_bits_exceptionVec_3', 'output', 1),
        ('io_enqLsq_req_5_bits_exceptionVec_4', 'output', 1),
        ('io_enqLsq_req_5_bits_exceptionVec_5', 'output', 1),
        ('io_enqLsq_req_5_bits_exceptionVec_6', 'output', 1),
        ('io_enqLsq_req_5_bits_exceptionVec_7', 'output', 1),
        ('io_enqLsq_req_5_bits_exceptionVec_8', 'output', 1),
        ('io_enqLsq_req_5_bits_exceptionVec_9', 'output', 1),
        ('io_enqLsq_req_5_bits_exceptionVec_10', 'output', 1),
        ('io_enqLsq_req_5_bits_exceptionVec_11', 'output', 1),
        ('io_enqLsq_req_5_bits_exceptionVec_12', 'output', 1),
        ('io_enqLsq_req_5_bits_exceptionVec_13', 'output', 1),
        ('io_enqLsq_req_5_bits_exceptionVec_14', 'output', 1),
        ('io_enqLsq_req_5_bits_exceptionVec_15', 'output', 1),
        ('io_enqLsq_req_5_bits_exceptionVec_16', 'output', 1),
        ('io_enqLsq_req_5_bits_exceptionVec_17', 'output', 1),
        ('io_enqLsq_req_5_bits_exceptionVec_18', 'output', 1),
        ('io_enqLsq_req_5_bits_exceptionVec_19', 'output', 1),
        ('io_enqLsq_req_5_bits_exceptionVec_20', 'output', 1),
        ('io_enqLsq_req_5_bits_exceptionVec_21', 'output', 1),
        ('io_enqLsq_req_5_bits_exceptionVec_22', 'output', 1),
        ('io_enqLsq_req_5_bits_exceptionVec_23', 'output', 1),
        ('io_enqLsq_req_5_bits_trigger', 'output', 4),
        ('io_enqLsq_req_5_bits_fuType', 'output', 35),
        ('io_enqLsq_req_5_bits_fuOpType', 'output', 9),
        ('io_enqLsq_req_5_bits_flushPipe', 'output', 1),
        ('io_enqLsq_req_5_bits_uopIdx', 'output', 7),
        ('io_enqLsq_req_5_bits_lastUop', 'output', 1),
        ('io_enqLsq_req_5_bits_robIdx_flag', 'output', 1),
        ('io_enqLsq_req_5_bits_robIdx_value', 'output', 8),
        ('io_enqLsq_req_5_bits_lqIdx_flag', 'output', 1),
        ('io_enqLsq_req_5_bits_lqIdx_value', 'output', 7),
        ('io_enqLsq_req_5_bits_sqIdx_flag', 'output', 1),
        ('io_enqLsq_req_5_bits_sqIdx_value', 'output', 6),
        ('io_enqLsq_req_5_bits_numLsElem', 'output', 5),
    ),
    'AgeDetector_38': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_enq_0', 'input', 24),
        ('io_enq_1', 'input', 24),
        ('io_enq_2', 'input', 24),
        ('io_deq', 'input', 24),
        ('io_ready', 'input', 24),
        ('io_out', 'output', 24),
    ),
}



# Configuration
class FamilySpec:
    """Exact locked member. / 精确锁定成员。"""
    # Initialize one exact family member. / 初始化一个精确 family 成员。
    def __init__(self, module: str) -> None:
        # Validate selected member. / 校验选定成员。
        if module not in PORT_SPECS:
            raise ValueError(module)
        self.module = module
        self.ports: tuple[PortSpec, ...] = PORT_SPECS[module]
    # Return width. / 返回位宽。
    def width(self, name: str) -> int:
        # Find catalog row. / 查找 catalog 行。
        for port, _direction, width in self.ports:
            if port == name:
                return width
        raise KeyError(name)
    # Test presence. / 判断存在。
    def has(self, name: str) -> bool:
        # Check membership. / 检查成员。
        return any(port == name for port, _direction, _width in self.ports)

# Implementation
# Return one exact member specification. / 返回一个精确成员规格。
def family_spec(module: str) -> FamilySpec:
    # Construct exact spec. / 构造精确规格。
    return FamilySpec(module)


def _age_detector_38(module: Module, ports: dict[str, Signal]) -> None:
    """Elaborate the locked 24-entry LSQ age detector.

    The implementation stores the upper triangular pairwise age matrix
    (including the diagonal validity bits).  A dequeue clears an entry, a
    dequeue of the other endpoint revalidates the column from the current
    entry state, and an enqueue inserts the entry after all entries enqueued
    by an earlier enqueue port.  The other family members continue to use the
    contract adapter below until their behavior is closed.
    """

    entries = 24
    enq = [ports[f"io_enq_{port}"] for port in range(3)]
    deq = ports["io_deq"]
    ready = ports["io_ready"]
    out = ports["io_out"]

    # The locked module uses an active-high asynchronous reset and a dedicated
    # clock.  Keep the domain explicit so the generated RTL has the same
    # reset edge semantics as the frozen Chisel output.
    clock_domain = ClockDomain("age", async_reset=True)
    clock_domain.clk = ports["clock"]
    clock_domain.rst = ports["reset"]
    module.domains += clock_domain

    diagonal = [Signal(reset=0, name=f"age_{index}_{index}") for index in range(entries)]
    upper = {
        (row, col): Signal(reset=0, name=f"age_{row}_{col}")
        for row in range(entries)
        for col in range(row + 1, entries)
    }

    def age_value(row: int, col: int) -> Any:
        if row == col:
            return diagonal[row]
        if row < col:
            return upper[(row, col)]
        # Lower-triangular queries read the transposed upper bit and invert it.
        return ~upper[(col, row)]

    def enqueued(index: int) -> Any:
        return (cast(Any, enq[0][index]) | enq[1][index] | enq[2][index]) & ~cast(Any, deq[index])

    def previous_port_enqueued(index: int, port_count: int) -> Any:
        # ``isEnqueued(index, 0)`` is false; port k sees only ports before k.
        if port_count == 0:
            return Const(0, 1)
        value: Any = Const(0, 1)
        for port in range(port_count):
            value = value | enq[port][index]
        return value & ~cast(Any, deq[index])

    def parallel_mux(row: int, col: int) -> Any:
        # The selector result[k] is the prefix enqueue state of the other
        # endpoint.  The first port has an empty prefix.
        value: Any = Const(0, 1)
        for port in range(3):
            value = value | (enq[port][row] & previous_port_enqueued(col, port))
        return value

    for row in range(entries):
        row_valid = enqueued(row)
        for col in range(row, entries):
            current = diagonal[row] if row == col else upper[(row, col)]
            if row == col:
                # The diagonal is the validity bit.  Dequeue wins over a
                # same-cycle enqueue, exactly as in the locked ternary chain.
                next_value = Mux(
                    deq[row],
                    Const(0, 1),
                    Mux(row_valid, ~diagonal[row] & ~parallel_mux(row, col), diagonal[row]),
                )
            else:
                this_valid = age_value(row, row) | row_valid
                next_value = Mux(
                    deq[row],
                    Const(0, 1),
                    Mux(
                        deq[col],
                        this_valid,
                        Mux(row_valid, ~age_value(col, col) & ~parallel_mux(row, col), current),
                    ),
                )
            module.d.age += current.eq(next_value)

    # The output is a combinational oldest-ready one-hot mask evaluated against
    # the registered age matrix, so enqueues become visible after their clock
    # edge.
    result: Any = Const(0, entries)
    for row in range(entries):
        older_than_ready: Any = Const(1, 1)
        for col in range(entries):
            if row == col:
                relation: Any = Const(1, 1)
            else:
                relation = age_value(row, col)
            older_than_ready = older_than_ready & (~cast(Any, ready[col]) | relation)
        selected = ready[row] & older_than_ready
        result = Mux(selected, Const(1 << row, entries), result)
    module.d.comb += out.eq(result)


def _bitmap(module: Module, ports: dict[str, Signal]) -> None:
    """Elaborate the eight-entry bitmap translation checker.

    The checker accepts translated PPN requests, performs the PMP stage, then
    arbitrates a small bitmap cache and the backing memory.  Entries sharing a
    PPN block coalesce behind one memory response; each completed entry carries
    the selected fault bit and the eight contiguous fault bits to the caller.
    """

    entries = 8
    state_idle = 0
    state_addr_check = 1
    state_cache_req = 2
    state_cache_resp = 3
    state_mem_req = 4
    state_mem_waiting = 5
    state_mem_out = 6

    # The generated Chisel block has an active-high asynchronous reset on its
    # entry/state registers.  Keep an independent domain so the public clock
    # remains an ordinary ABI port.
    clock_domain = ClockDomain("bitmap", async_reset=True)
    clock_domain.clk = ports["clock"]
    clock_domain.rst = ports["reset"]
    module.domains += clock_domain

    state = [Signal(3, reset=0, name=f"bitmap_state_{index}") for index in range(entries)]
    ppn = [Signal(36, reset=0, name=f"bitmap_ppn_{index}") for index in range(entries)]
    vpn = [Signal(38, reset=0, name=f"bitmap_vpn_{index}") for index in range(entries)]
    s2xlate = [Signal(2, reset=0, name=f"bitmap_s2xlate_{index}") for index in range(entries)]
    request_id = [Signal(3, reset=0, name=f"bitmap_id_{index}") for index in range(entries)]
    wait_id = [Signal(3, reset=0, name=f"bitmap_wait_id_{index}") for index in range(entries)]
    fault = [Signal(reset=0, name=f"bitmap_cf_{index}") for index in range(entries)]
    hit = [Signal(reset=0, name=f"bitmap_hit_{index}") for index in range(entries)]
    contiguous = [
        [Signal(reset=0, name=f"bitmap_cfs_{index}_{bit}") for bit in range(8)]
        for index in range(entries)
    ]
    level = [Signal(2, reset=0, name=f"bitmap_level_{index}") for index in range(entries)]
    way_info = [Signal(4, reset=0, name=f"bitmap_way_{index}") for index in range(entries)]
    hptw_bypassed = [Signal(reset=0, name=f"bitmap_bypassed_{index}") for index in range(entries)]
    napot = [Signal(reset=0, name=f"bitmap_napot_{index}") for index in range(entries)]
    data = [Signal(64, reset=0, name=f"bitmap_data_{index}") for index in range(entries)]

    enq_ptr_reg = Signal(3, name="bitmap_enq_ptr_reg")
    need_addr_check = Signal(name="bitmap_need_addr_check")
    pmp_addr_reg = Signal(64, name="bitmap_pmp_addr_reg")
    wakeup_stall = Signal(reset=0, name="bitmap_wakeup_stall")
    wakeup_set_index_reg = Signal(6, reset=0, name="bitmap_wakeup_set_index")
    wakeup_tag_reg = Signal(38, reset=0, name="bitmap_wakeup_tag")
    wakeup_way_reg = Signal(4, reset=0, name="bitmap_wakeup_way")
    wakeup_pte_index_reg = Signal(3, reset=0, name="bitmap_wakeup_pte_index")
    wakeup_success_reg = Signal(reset=0, name="bitmap_wakeup_success")
    wakeup_s2xlate_reg = Signal(2, reset=0, name="bitmap_wakeup_s2xlate")
    memory_last_grant = Signal(3, reset=0, name="bitmap_memory_last_grant")

    def select_expr(values: list[Any], selector: Any, width: int) -> Any:
        """Priority mux indexed by a three-bit slot selector."""

        result: Any = Const(0, width)
        for index in reversed(range(len(values))):
            result = Mux(selector == Const(index, len(selector)), values[index], result)
        return result

    def _or_reduce(values: list[Any]) -> Any:
        result: Any = Const(0, 1)
        for value in values:
            result = result | value
        return result

    flush = (
        ports["io_sfence_valid"]
        | ports["io_csr_satp_changed"]
        | ports["io_csr_vsatp_changed"]
        | ports["io_csr_hgatp_changed"]
        | ports["io_csr_priv_virt_changed"]
    )
    idle = [state[index] == Const(state_idle, 3) for index in range(entries)]
    cache_request = [state[index] == Const(state_cache_req, 3) for index in range(entries)]
    cache_response = [state[index] == Const(state_cache_resp, 3) for index in range(entries)]
    memory_request = [state[index] == Const(state_mem_req, 3) for index in range(entries)]
    waiting = [state[index] == Const(state_mem_waiting, 3) for index in range(entries)]
    having = [state[index] == Const(state_mem_out, 3) for index in range(entries)]

    idle_any: Any = Const(0, 1)
    enq_ptr: Any = Const(entries - 1, 3)
    for index in range(entries):
        idle_any = idle_any | idle[index]
    for index in reversed(range(entries)):
        enq_ptr = Mux(idle[index], Const(index, 3), enq_ptr)

    cache_any: Any = Const(0, 1)
    cache_ptr: Any = Const(entries - 1, 3)
    for index in range(entries):
        cache_any = cache_any | cache_request[index]
    for index in reversed(range(entries)):
        cache_ptr = Mux(cache_request[index], Const(index, 3), cache_ptr)

    mask_inputs = [ports[f"io_mem_req_mask_{index}"] for index in range(entries)]
    memory_valid: list[Any] = [memory_request[index] & ~mask_inputs[index] for index in range(entries)]
    memory_any: Any = Const(0, 1)
    memory_ptr: Any = Const(entries - 1, 3)
    memory_after_valid = [
        memory_valid[index] & (Const(index, 3) > memory_last_grant)
        for index in range(entries)
    ]
    memory_after_any: Any = Const(0, 1)
    memory_after_ptr: Any = Const(entries - 1, 3)
    for index in range(entries):
        memory_any = memory_any | memory_valid[index]
        memory_after_any = memory_after_any | memory_after_valid[index]
    for index in reversed(range(entries)):
        memory_ptr = Mux(memory_valid[index], Const(index, 3), memory_ptr)
        memory_after_ptr = Mux(memory_after_valid[index], Const(index, 3), memory_after_ptr)
    memory_ptr = Mux(memory_after_any, memory_after_ptr, memory_ptr)

    having_any: Any = Const(0, 1)
    response_ptr: Any = Const(entries - 1, 3)
    for index in range(entries):
        having_any = having_any | having[index]
    for index in reversed(range(entries)):
        response_ptr = Mux(having[index], Const(index, 3), response_ptr)

    # Effective PPN is the level-specific superpage reconstruction used by
    # bitmap addressing.  The locked configuration has no key-ID enable port,
    # so the incoming PPN is used directly.
    request_level = ports["io_req_bits_level"]
    request_bmppn = ports["io_req_bits_bmppn"]
    request_vpn = ports["io_req_bits_vpn"]
    request_n = ports["io_req_bits_n"]
    effective_ppn: Any = Mux(
        request_level == Const(3, 2),
        Cat(request_vpn[0:27], request_bmppn[27:36]),
        Mux(
            request_level == Const(2, 2),
            Cat(request_vpn[0:18], request_bmppn[18:36]),
            Mux(
                request_level == Const(1, 2),
                Cat(request_vpn[0:9], request_bmppn[9:36]),
                Mux(request_n, Cat(request_vpn[0:4], request_bmppn[4:36]), request_bmppn),
            ),
        ),
    )

    def bitmap_address(ppn_value: Any) -> Any:
        # BMA is a 58-bit page base; the public address is the low 48 bits.
        base = Cat(Const(0, 6), ports["io_csr_mbmc_BMA"][0:42])
        offset = Cat(Const(0, 3), ppn_value[6:36], Const(0, 15))
        return cast(Any, base) + offset

    request_address = bitmap_address(effective_ppn)
    request_fire = ports["io_req_valid"] & idle_any

    # Memory and waiting duplicate detection use the 32-bit bitmap block tag.
    request_block = effective_ppn[5:36]
    memory_selected_ppn = select_expr(ppn, memory_ptr, 36)
    memory_fire = memory_any & ports["io_mem_req_ready"]
    duplicate_wait = [waiting[index] & (request_block == ppn[index][5:36]) for index in range(entries)]
    duplicate_wait_any: Any = Const(0, 1)
    for value in duplicate_wait:
        duplicate_wait_any = duplicate_wait_any | value
    duplicate_request = memory_fire & (request_block == memory_selected_ppn[5:36])

    memory_resp_waiting = [
        waiting[index]
        & (ports["io_mem_resp_bits_id"] == (Cat(wait_id[index], Const(0, 1)) + Const(8, 4)))
        for index in range(entries)
    ]
    memory_resp_fire = ports["io_mem_resp_valid"] & _or_reduce(waiting)
    duplicate_response: Any = Const(0, 1)
    for index in range(entries):
        duplicate_response = duplicate_response | (
            duplicate_wait[index]
            & ports["io_mem_resp_valid"]
            & (ports["io_mem_resp_bits_id"][0:3] == Const(index, 3))
        )
    request_wait_id: Any = select_expr(wait_id, Const(0, 3), 3)
    for index in reversed(range(entries)):
        request_wait_id = Mux(duplicate_wait[index], wait_id[index], request_wait_id)
    request_wait_id = Mux(duplicate_request, memory_ptr, request_wait_id)
    request_to_wait = duplicate_wait_any | duplicate_request
    request_state: Any = Mux(duplicate_response, Const(state_mem_out, 3), Mux(request_to_wait, Const(state_mem_waiting, 3), Const(state_addr_check, 3)))

    # Memory response payload is eight little-endian 64-bit words.  Each word
    # supplies one selected fault bit and eight contiguous byte fault bits.
    response_words = [ports["io_mem_resp_bits_value"][index * 64:(index + 1) * 64] for index in range(8)]

    def decode_faults(ppn_value: Any, source_value: Any) -> tuple[Any, list[Any], Any]:
        word = select_expr(response_words, ppn_value[6:9], 64)
        byte_shift = Cat(Const(0, 3), ppn_value[3:6])
        byte_window = word >> byte_shift
        cfs = [byte_window[index * 8] for index in range(8)]
        cf_value = (word >> ppn_value[0:6])[0]
        return cf_value, cfs, word

    request_cf, request_cfs, request_word = decode_faults(effective_ppn, ports["io_mem_resp_bits_value"])
    del request_word

    # Public output arbitration and handshake surfaces.
    module.d.comb += ports["io_req_ready"].eq(idle_any)
    module.d.comb += ports["io_mem_req_valid"].eq(memory_any & ~flush)
    module.d.comb += ports["io_mem_req_bits_addr"].eq(bitmap_address(memory_selected_ppn))
    module.d.comb += ports["io_mem_req_bits_id"].eq(Cat(memory_ptr, Const(0, 1)) + Const(8, 4))
    module.d.comb += ports["io_cache_req_valid"].eq(cache_any & ~flush)
    module.d.comb += ports["io_cache_req_bits_order"].eq(cache_ptr)
    module.d.comb += ports["io_cache_req_bits_tag"].eq(select_expr(ppn, cache_ptr, 36))
    module.d.comb += ports["io_cache_resp_ready"].eq((Const(0, 1) | _or_reduce(cache_response)) & ~flush)
    module.d.comb += ports["io_pmp_req_bits_addr"].eq(pmp_addr_reg[0:48])

    cache_response_fire = (Const(0, 1) | _or_reduce(cache_response)) & ports["io_cache_resp_valid"] & ~flush
    cache_matches = [cache_response_fire & cache_response[index] & (ports["io_cache_resp_bits_order"] == Const(index, 8)) for index in range(entries)]
    cache_hit = cache_response_fire & ports["io_cache_resp_bits_hit"]

    # Completion output, wakeup hold, and refill payload.
    response_valid = having_any & ~wakeup_stall
    response_fire = response_valid & ports["io_resp_ready"]
    selected_fault = select_expr(fault, response_ptr, 1)
    selected_hit = select_expr(hit, response_ptr, 1)
    selected_ppn = select_expr(ppn, response_ptr, 36)
    selected_vpn = select_expr(vpn, response_ptr, 38)
    selected_level = select_expr(level, response_ptr, 2)
    selected_napot = select_expr(napot, response_ptr, 1)
    selected_bypassed = select_expr(hptw_bypassed, response_ptr, 1)
    selected_s2xlate = select_expr(s2xlate, response_ptr, 2)
    selected_way = select_expr(way_info, response_ptr, 4)
    selected_request_id = select_expr(request_id, response_ptr, 3)
    selected_data = select_expr(data, response_ptr, 64)
    selected_cfs = [select_expr([contiguous[index][bit] for index in range(entries)], response_ptr, 1) for bit in range(8)]
    wakeup_one = response_valid & ~selected_bypassed & (selected_level == Const(0, 2)) & ~selected_napot
    wakeup_fire = (wakeup_stall | wakeup_one) & ports["io_wakeup_ready"]
    module.d.comb += ports["io_resp_valid"].eq(response_valid)
    module.d.comb += ports["io_resp_bits_cf"].eq(selected_fault)
    module.d.comb += ports["io_resp_bits_id"].eq(selected_request_id)
    for bit in range(8):
        module.d.comb += ports[f"io_resp_bits_cfs_{bit}"].eq(selected_cfs[bit])
    module.d.comb += ports["io_wakeup_valid"].eq(wakeup_stall | wakeup_one)
    module.d.comb += ports["io_wakeup_bits_setIndex"].eq(Mux(wakeup_one, selected_vpn[3:9], wakeup_set_index_reg))
    module.d.comb += ports["io_wakeup_bits_tag"].eq(Mux(wakeup_one, selected_vpn, wakeup_tag_reg))
    module.d.comb += ports["io_wakeup_bits_way_info"].eq(Mux(wakeup_one, selected_way, wakeup_way_reg))
    module.d.comb += ports["io_wakeup_bits_pte_index"].eq(Mux(wakeup_one, selected_vpn[0:3], wakeup_pte_index_reg))
    module.d.comb += ports["io_wakeup_bits_check_success"].eq(Mux(wakeup_one, ~selected_fault, wakeup_success_reg))
    module.d.comb += ports["io_wakeup_bits_s2xlate"].eq(Mux(wakeup_one, selected_s2xlate, wakeup_s2xlate_reg))
    module.d.comb += ports["io_refill_valid"].eq(response_valid & ~selected_hit)
    module.d.comb += ports["io_refill_bits_tag"].eq(selected_ppn)
    module.d.comb += ports["io_refill_bits_data"].eq(selected_data)

    # The PMP request is a one-cycle delayed side effect of an accepted entry.
    pmp_fire = need_addr_check
    access_fault = ports["io_pmp_resp_ld"] | ports["io_pmp_resp_mmio"]
    pmp_matches = [pmp_fire & (enq_ptr_reg == Const(index, 3)) for index in range(entries)]

    # Register updates.  The order mirrors the source state machine: enqueue,
    # PMP response, cache handshake, cache response, memory request/response,
    # output dequeue, and finally flush.
    for index in range(entries):
        next_state: Any = state[index]
        next_state = Mux(request_fire & (enq_ptr == Const(index, 3)), request_state, next_state)
        next_state = Mux(pmp_matches[index], Mux(access_fault, Const(state_mem_out, 3), Const(state_cache_req, 3)), next_state)
        next_state = Mux(cache_request_fire := (cache_any & ports["io_cache_req_ready"] & ~flush) & (cache_ptr == Const(index, 3)), Const(state_cache_resp, 3), next_state)

        # A cache miss either joins an existing memory request, joins a newly
        # issued one, or starts a fresh request of its own.
        cache_duplicate_wait = [
            waiting[other] & (ppn[index][5:36] == ppn[other][5:36])
            for other in range(entries)
        ]
        cache_duplicate_any: Any = Const(0, 1)
        for value in cache_duplicate_wait:
            cache_duplicate_any = cache_duplicate_any | value
        cache_duplicate_response: Any = Const(0, 1)
        for other in range(entries):
            cache_duplicate_response = cache_duplicate_response | (
                cache_duplicate_wait[other]
                & (ports["io_mem_resp_bits_id"][0:3] == Const(other, 3))
                & ports["io_mem_resp_valid"]
            )
        cache_duplicate_request = memory_fire & (ppn[index][5:36] == memory_selected_ppn[5:36])
        cache_wait_id: Any = Const(0, 3)
        for other in reversed(range(entries)):
            cache_wait_id = Mux(cache_duplicate_wait[other], wait_id[other], cache_wait_id)
        cache_wait_id = Mux(cache_duplicate_request, memory_ptr, cache_wait_id)
        cache_to_wait = cache_duplicate_any | cache_duplicate_request
        cache_next_state = Mux(cache_duplicate_response, Const(state_mem_out, 3), Mux(cache_to_wait, Const(state_mem_waiting, 3), Const(state_mem_req, 3)))
        next_state = Mux(cache_matches[index] & ~cache_hit, cache_next_state, next_state)
        next_state = Mux(cache_matches[index] & cache_hit, Const(state_mem_out, 3), next_state)
        next_state = Mux(memory_fire & memory_request[index] & (ppn[index][5:36] == memory_selected_ppn[5:36]), Const(state_mem_waiting, 3), next_state)
        next_state = Mux(memory_resp_waiting[index], Const(state_mem_out, 3), next_state)
        next_state = Mux(response_fire & (response_ptr == Const(index, 3)), Const(state_idle, 3), next_state)
        next_state = Mux(flush, Const(state_idle, 3), next_state)
        module.d.bitmap += state[index].eq(next_state)

        # Entry field updates follow the same event priority.
        field_ppn: Any = ppn[index]
        field_vpn: Any = vpn[index]
        field_s2: Any = s2xlate[index]
        field_id: Any = request_id[index]
        field_wait: Any = wait_id[index]
        field_fault: Any = fault[index]
        field_hit: Any = hit[index]
        field_level: Any = level[index]
        field_way: Any = way_info[index]
        field_bypassed: Any = hptw_bypassed[index]
        field_napot: Any = napot[index]
        field_data: Any = data[index]
        cfs_next: list[Value] = list(contiguous[index])
        enq_here = request_fire & (enq_ptr == Const(index, 3))
        field_ppn = Mux(enq_here, effective_ppn, field_ppn)
        field_vpn = Mux(enq_here, request_vpn, field_vpn)
        field_s2 = Mux(enq_here, ports["io_req_bits_s2xlate"], field_s2)
        field_id = Mux(enq_here, ports["io_req_bits_id"], field_id)
        field_wait = Mux(enq_here, request_wait_id, field_wait)
        field_fault = Mux(enq_here, Mux(duplicate_response, request_cf, Const(0, 1)), field_fault)
        field_hit = Mux(enq_here, request_to_wait | duplicate_response, field_hit)
        field_level = Mux(enq_here, request_level, field_level)
        field_way = Mux(enq_here, ports["io_req_bits_way_info"], field_way)
        field_bypassed = Mux(enq_here, ports["io_req_bits_hptw_bypassed"], field_bypassed)
        field_napot = Mux(enq_here, request_n, field_napot)
        for bit in range(8):
            cfs_next[bit] = Mux(enq_here, Mux(duplicate_response, request_cfs[bit], Const(0, 1)), cfs_next[bit])
        field_fault = Mux(pmp_matches[index], access_fault, field_fault)
        for bit in range(8):
            cfs_next[bit] = Mux(pmp_matches[index], access_fault, cfs_next[bit])
        cache_cfs = [ports[f"io_cache_resp_bits_cfs_{bit}"] for bit in range(8)]
        cache_fault = select_expr(cache_cfs, ppn[index][0:3], 1)
        field_fault = Mux(cache_matches[index] & cache_hit, cache_fault, field_fault)
        for bit in range(8):
            cfs_next[bit] = Mux(cache_matches[index] & cache_hit, cache_cfs[bit], cfs_next[bit])
        field_hit = Mux(cache_matches[index] & cache_hit, Const(1, 1), field_hit)
        memory_fault, memory_cfs, memory_word = decode_faults(ppn[index], ports["io_mem_resp_bits_value"])
        field_fault = Mux(memory_resp_waiting[index], memory_fault, field_fault)
        field_data = Mux(memory_resp_waiting[index], memory_word, field_data)
        for bit in range(8):
            cfs_next[bit] = Mux(memory_resp_waiting[index], memory_cfs[bit], cfs_next[bit])
        module.d.bitmap += ppn[index].eq(field_ppn)
        module.d.bitmap += vpn[index].eq(field_vpn)
        module.d.bitmap += s2xlate[index].eq(field_s2)
        module.d.bitmap += request_id[index].eq(field_id)
        module.d.bitmap += wait_id[index].eq(field_wait)
        module.d.bitmap += fault[index].eq(field_fault)
        module.d.bitmap += hit[index].eq(field_hit)
        module.d.bitmap += level[index].eq(field_level)
        module.d.bitmap += way_info[index].eq(field_way)
        module.d.bitmap += hptw_bypassed[index].eq(field_bypassed)
        module.d.bitmap += napot[index].eq(field_napot)
        module.d.bitmap += data[index].eq(field_data)
        for bit in range(8):
            module.d.bitmap += contiguous[index][bit].eq(cfs_next[bit])

    module.d.bitmap += enq_ptr_reg.eq(enq_ptr)
    module.d.bitmap += need_addr_check.eq(request_fire & (request_state == Const(state_addr_check, 3)) & ~flush)
    module.d.bitmap += pmp_addr_reg.eq(Mux(request_fire, request_address, pmp_addr_reg))
    module.d.bitmap += memory_last_grant.eq(Mux(memory_fire, memory_ptr, memory_last_grant))
    module.d.bitmap += wakeup_stall.eq(Mux(wakeup_fire, Const(0, 1), Mux(wakeup_one, Const(1, 1), wakeup_stall)))
    module.d.bitmap += wakeup_set_index_reg.eq(Mux(wakeup_one, selected_vpn[3:9], wakeup_set_index_reg))
    module.d.bitmap += wakeup_tag_reg.eq(Mux(wakeup_one, selected_vpn, wakeup_tag_reg))
    module.d.bitmap += wakeup_way_reg.eq(Mux(wakeup_one, selected_way, wakeup_way_reg))
    module.d.bitmap += wakeup_pte_index_reg.eq(Mux(wakeup_one, selected_vpn[0:3], wakeup_pte_index_reg))
    module.d.bitmap += wakeup_success_reg.eq(Mux(wakeup_one, ~selected_fault, wakeup_success_reg))
    module.d.bitmap += wakeup_s2xlate_reg.eq(Mux(wakeup_one, selected_s2xlate, wakeup_s2xlate_reg))

class MemoryFamily(Elaboratable):
    """Bounded exact-port member. / 有界精确端口成员。"""
    # Initialize all locked ports. / 初始化全部锁定端口。
    def __init__(self, module: str = COVERED_MODULES[0]) -> None:
        # Allocate locked signals. / 分配锁定信号。
        self.member = module
        self.spec = family_spec(module)
        self.ports = {name: Signal(width, name=name) for name, _direction, width in self.spec.ports}
    # Elaborate. / 展开。
    def elaborate(self, platform: Any) -> Module:
        # Elaborate the one closed LSQ leaf; keep the other surfaces explicit
        # until their locked behavioral proofs are complete.
        del platform
        module = Module()
        if self.member == "AgeDetector_38":
            _age_detector_38(module, self.ports)
        elif self.member == "Bitmap":
            _bitmap(module, self.ports)
        else:
            for name, direction, width in self.spec.ports:
                if direction == "output":
                    module.d.comb += self.ports[name].eq(Const(0, width))
        return module

# Public Adapter
# Export selected member. / 导出选定成员。
def build_verilog(configuration: Any = None, injected_dependencies: Any = None, name: str | None = None) -> str:
    # Resolve selected member. / 解析选定成员。
    del injected_dependencies
    member = COVERED_MODULES[0]
    if isinstance(configuration, dict): member = str(configuration.get("module", member))
    elif isinstance(configuration, str): member = configuration
    elif name is not None: member = name
    top = MemoryFamily(member)
    return verilog.convert(top, name=member, ports=[top.ports[p] for p, _d, _w in top.spec.ports], emit_src=False)

# Direct Entry
# Print default member. / 打印默认成员。
def main() -> None:
    # Run public adapter. / 运行公开适配器。
    print(build_verilog({"module": COVERED_MODULES[0]}, {}))

if __name__ == "__main__": main()
