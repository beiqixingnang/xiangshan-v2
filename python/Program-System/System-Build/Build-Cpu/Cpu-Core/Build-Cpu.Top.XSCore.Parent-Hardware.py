"""Source-backed XSCore parent/bridge boundary for Kunminghu V2.

This aggregate implements the parent-visible wiring documented by
XSCore.scala. Frontend, Backend, and MemBlock remain explicit injected
children; absent or bounded children are reported through child_missing and
never promoted to a complete closure. The 308-port contract is copied from
the locked XSCore inventory and is materialized without reading the reference
artifact at build time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from amaranth import Cat, ClockDomain, Const, Elaboratable, Module, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
__all__ = [
    'XSCoreParentConfig',
    'XSCoreParent',
    'UHSCXSCoreParent',
    'XSCoreBridge',
    'XSCore',
    'xs_core_port_specs',
    'xs_core_parent_observation',
    'build_verilog',
    'main',
    'XSCORE_REFERENCE_PORT_COUNT',
]

XSCORE_REFERENCE_PORT_COUNT = 308

# Locked XSCore ANSI names/directions/widths from v2-root-port-inventories.json.
_XSCORE_PORT_SPECS: tuple[tuple[str, str, int], ...] = (
    ("clock", "input", 1),
    ("reset", "input", 1),
    ("auto_memBlock_inner_buffers_out_a_ready", "input", 1),
    ("auto_memBlock_inner_buffers_out_a_valid", "output", 1),
    ("auto_memBlock_inner_buffers_out_a_bits_opcode", "output", 4),
    ("auto_memBlock_inner_buffers_out_a_bits_param", "output", 3),
    ("auto_memBlock_inner_buffers_out_a_bits_size", "output", 3),
    ("auto_memBlock_inner_buffers_out_a_bits_source", "output", 4),
    ("auto_memBlock_inner_buffers_out_a_bits_address", "output", 48),
    ("auto_memBlock_inner_buffers_out_a_bits_mask", "output", 8),
    ("auto_memBlock_inner_buffers_out_a_bits_data", "output", 64),
    ("auto_memBlock_inner_buffers_out_a_bits_corrupt", "output", 1),
    ("auto_memBlock_inner_buffers_out_d_ready", "output", 1),
    ("auto_memBlock_inner_buffers_out_d_valid", "input", 1),
    ("auto_memBlock_inner_buffers_out_d_bits_opcode", "input", 4),
    ("auto_memBlock_inner_buffers_out_d_bits_param", "input", 2),
    ("auto_memBlock_inner_buffers_out_d_bits_size", "input", 3),
    ("auto_memBlock_inner_buffers_out_d_bits_source", "input", 4),
    ("auto_memBlock_inner_buffers_out_d_bits_sink", "input", 1),
    ("auto_memBlock_inner_buffers_out_d_bits_denied", "input", 1),
    ("auto_memBlock_inner_buffers_out_d_bits_data", "input", 64),
    ("auto_memBlock_inner_buffers_out_d_bits_corrupt", "input", 1),
    ("auto_memBlock_inner_frontendBridge_instr_uncache_out_a_ready", "input", 1),
    ("auto_memBlock_inner_frontendBridge_instr_uncache_out_a_valid", "output", 1),
    ("auto_memBlock_inner_frontendBridge_instr_uncache_out_a_bits_param", "output", 3),
    ("auto_memBlock_inner_frontendBridge_instr_uncache_out_a_bits_address", "output", 48),
    ("auto_memBlock_inner_frontendBridge_instr_uncache_out_a_bits_corrupt", "output", 1),
    ("auto_memBlock_inner_frontendBridge_instr_uncache_out_d_ready", "output", 1),
    ("auto_memBlock_inner_frontendBridge_instr_uncache_out_d_valid", "input", 1),
    ("auto_memBlock_inner_frontendBridge_instr_uncache_out_d_bits_opcode", "input", 4),
    ("auto_memBlock_inner_frontendBridge_instr_uncache_out_d_bits_param", "input", 2),
    ("auto_memBlock_inner_frontendBridge_instr_uncache_out_d_bits_size", "input", 3),
    ("auto_memBlock_inner_frontendBridge_instr_uncache_out_d_bits_source", "input", 1),
    ("auto_memBlock_inner_frontendBridge_instr_uncache_out_d_bits_sink", "input", 1),
    ("auto_memBlock_inner_frontendBridge_instr_uncache_out_d_bits_denied", "input", 1),
    ("auto_memBlock_inner_frontendBridge_instr_uncache_out_d_bits_data", "input", 64),
    ("auto_memBlock_inner_frontendBridge_instr_uncache_out_d_bits_corrupt", "input", 1),
    ("auto_memBlock_inner_frontendBridge_icachectrl_in_a_ready", "output", 1),
    ("auto_memBlock_inner_frontendBridge_icachectrl_in_a_valid", "input", 1),
    ("auto_memBlock_inner_frontendBridge_icachectrl_in_a_bits_opcode", "input", 4),
    ("auto_memBlock_inner_frontendBridge_icachectrl_in_a_bits_param", "input", 3),
    ("auto_memBlock_inner_frontendBridge_icachectrl_in_a_bits_size", "input", 2),
    ("auto_memBlock_inner_frontendBridge_icachectrl_in_a_bits_source", "input", 5),
    ("auto_memBlock_inner_frontendBridge_icachectrl_in_a_bits_address", "input", 30),
    ("auto_memBlock_inner_frontendBridge_icachectrl_in_a_bits_mask", "input", 8),
    ("auto_memBlock_inner_frontendBridge_icachectrl_in_a_bits_data", "input", 64),
    ("auto_memBlock_inner_frontendBridge_icachectrl_in_a_bits_corrupt", "input", 1),
    ("auto_memBlock_inner_frontendBridge_icachectrl_in_d_ready", "input", 1),
    ("auto_memBlock_inner_frontendBridge_icachectrl_in_d_valid", "output", 1),
    ("auto_memBlock_inner_frontendBridge_icachectrl_in_d_bits_opcode", "output", 4),
    ("auto_memBlock_inner_frontendBridge_icachectrl_in_d_bits_param", "output", 2),
    ("auto_memBlock_inner_frontendBridge_icachectrl_in_d_bits_size", "output", 2),
    ("auto_memBlock_inner_frontendBridge_icachectrl_in_d_bits_source", "output", 5),
    ("auto_memBlock_inner_frontendBridge_icachectrl_in_d_bits_sink", "output", 1),
    ("auto_memBlock_inner_frontendBridge_icachectrl_in_d_bits_denied", "output", 1),
    ("auto_memBlock_inner_frontendBridge_icachectrl_in_d_bits_data", "output", 64),
    ("auto_memBlock_inner_frontendBridge_icachectrl_in_d_bits_corrupt", "output", 1),
    ("auto_memBlock_inner_frontendBridge_icache_out_a_ready", "input", 1),
    ("auto_memBlock_inner_frontendBridge_icache_out_a_valid", "output", 1),
    ("auto_memBlock_inner_frontendBridge_icache_out_a_bits_opcode", "output", 4),
    ("auto_memBlock_inner_frontendBridge_icache_out_a_bits_param", "output", 3),
    ("auto_memBlock_inner_frontendBridge_icache_out_a_bits_size", "output", 3),
    ("auto_memBlock_inner_frontendBridge_icache_out_a_bits_source", "output", 4),
    ("auto_memBlock_inner_frontendBridge_icache_out_a_bits_address", "output", 48),
    ("auto_memBlock_inner_frontendBridge_icache_out_a_bits_user_alias", "output", 2),
    ("auto_memBlock_inner_frontendBridge_icache_out_a_bits_user_reqSource", "output", 5),
    ("auto_memBlock_inner_frontendBridge_icache_out_a_bits_user_needHint", "output", 1),
    ("auto_memBlock_inner_frontendBridge_icache_out_a_bits_mask", "output", 32),
    ("auto_memBlock_inner_frontendBridge_icache_out_a_bits_data", "output", 256),
    ("auto_memBlock_inner_frontendBridge_icache_out_a_bits_corrupt", "output", 1),
    ("auto_memBlock_inner_frontendBridge_icache_out_d_ready", "output", 1),
    ("auto_memBlock_inner_frontendBridge_icache_out_d_valid", "input", 1),
    ("auto_memBlock_inner_frontendBridge_icache_out_d_bits_opcode", "input", 4),
    ("auto_memBlock_inner_frontendBridge_icache_out_d_bits_param", "input", 2),
    ("auto_memBlock_inner_frontendBridge_icache_out_d_bits_size", "input", 3),
    ("auto_memBlock_inner_frontendBridge_icache_out_d_bits_source", "input", 4),
    ("auto_memBlock_inner_frontendBridge_icache_out_d_bits_sink", "input", 10),
    ("auto_memBlock_inner_frontendBridge_icache_out_d_bits_denied", "input", 1),
    ("auto_memBlock_inner_frontendBridge_icache_out_d_bits_data", "input", 256),
    ("auto_memBlock_inner_frontendBridge_icache_out_d_bits_corrupt", "input", 1),
    ("auto_memBlock_inner_ptw_to_l2_buffer_out_a_ready", "input", 1),
    ("auto_memBlock_inner_ptw_to_l2_buffer_out_a_valid", "output", 1),
    ("auto_memBlock_inner_ptw_to_l2_buffer_out_a_bits_opcode", "output", 4),
    ("auto_memBlock_inner_ptw_to_l2_buffer_out_a_bits_param", "output", 3),
    ("auto_memBlock_inner_ptw_to_l2_buffer_out_a_bits_size", "output", 3),
    ("auto_memBlock_inner_ptw_to_l2_buffer_out_a_bits_source", "output", 4),
    ("auto_memBlock_inner_ptw_to_l2_buffer_out_a_bits_address", "output", 48),
    ("auto_memBlock_inner_ptw_to_l2_buffer_out_a_bits_user_reqSource", "output", 5),
    ("auto_memBlock_inner_ptw_to_l2_buffer_out_a_bits_mask", "output", 32),
    ("auto_memBlock_inner_ptw_to_l2_buffer_out_a_bits_data", "output", 256),
    ("auto_memBlock_inner_ptw_to_l2_buffer_out_a_bits_corrupt", "output", 1),
    ("auto_memBlock_inner_ptw_to_l2_buffer_out_d_ready", "output", 1),
    ("auto_memBlock_inner_ptw_to_l2_buffer_out_d_valid", "input", 1),
    ("auto_memBlock_inner_ptw_to_l2_buffer_out_d_bits_opcode", "input", 4),
    ("auto_memBlock_inner_ptw_to_l2_buffer_out_d_bits_param", "input", 2),
    ("auto_memBlock_inner_ptw_to_l2_buffer_out_d_bits_size", "input", 3),
    ("auto_memBlock_inner_ptw_to_l2_buffer_out_d_bits_source", "input", 4),
    ("auto_memBlock_inner_ptw_to_l2_buffer_out_d_bits_sink", "input", 10),
    ("auto_memBlock_inner_ptw_to_l2_buffer_out_d_bits_denied", "input", 1),
    ("auto_memBlock_inner_ptw_to_l2_buffer_out_d_bits_data", "input", 256),
    ("auto_memBlock_inner_ptw_to_l2_buffer_out_d_bits_corrupt", "input", 1),
    ("auto_memBlock_inner_beu_local_int_sink_in_0", "input", 1),
    ("auto_memBlock_inner_nmi_int_sink_in_0", "input", 1),
    ("auto_memBlock_inner_nmi_int_sink_in_1", "input", 1),
    ("auto_memBlock_inner_plic_int_sink_in_1_0", "input", 1),
    ("auto_memBlock_inner_plic_int_sink_in_0_0", "input", 1),
    ("auto_memBlock_inner_debug_int_sink_in_0", "input", 1),
    ("auto_memBlock_inner_clint_int_sink_in_0", "input", 1),
    ("auto_memBlock_inner_clint_int_sink_in_1", "input", 1),
    ("auto_memBlock_inner_l3_pf_sender_out_addr", "output", 64),
    ("auto_memBlock_inner_l3_pf_sender_out_addr_valid", "output", 1),
    ("auto_memBlock_inner_l2_pf_sender_out_addr", "output", 64),
    ("auto_memBlock_inner_l2_pf_sender_out_pf_source", "output", 5),
    ("auto_memBlock_inner_l2_pf_sender_out_addr_valid", "output", 1),
    ("auto_memBlock_inner_dcache_client_out_a_ready", "input", 1),
    ("auto_memBlock_inner_dcache_client_out_a_valid", "output", 1),
    ("auto_memBlock_inner_dcache_client_out_a_bits_opcode", "output", 4),
    ("auto_memBlock_inner_dcache_client_out_a_bits_param", "output", 3),
    ("auto_memBlock_inner_dcache_client_out_a_bits_size", "output", 3),
    ("auto_memBlock_inner_dcache_client_out_a_bits_source", "output", 6),
    ("auto_memBlock_inner_dcache_client_out_a_bits_address", "output", 48),
    ("auto_memBlock_inner_dcache_client_out_a_bits_user_alias", "output", 2),
    ("auto_memBlock_inner_dcache_client_out_a_bits_user_vaddr", "output", 44),
    ("auto_memBlock_inner_dcache_client_out_a_bits_user_reqSource", "output", 5),
    ("auto_memBlock_inner_dcache_client_out_a_bits_user_needHint", "output", 1),
    ("auto_memBlock_inner_dcache_client_out_a_bits_echo_isKeyword", "output", 1),
    ("auto_memBlock_inner_dcache_client_out_a_bits_mask", "output", 32),
    ("auto_memBlock_inner_dcache_client_out_a_bits_data", "output", 256),
    ("auto_memBlock_inner_dcache_client_out_a_bits_corrupt", "output", 1),
    ("auto_memBlock_inner_dcache_client_out_b_ready", "output", 1),
    ("auto_memBlock_inner_dcache_client_out_b_valid", "input", 1),
    ("auto_memBlock_inner_dcache_client_out_b_bits_opcode", "input", 3),
    ("auto_memBlock_inner_dcache_client_out_b_bits_param", "input", 2),
    ("auto_memBlock_inner_dcache_client_out_b_bits_size", "input", 3),
    ("auto_memBlock_inner_dcache_client_out_b_bits_source", "input", 6),
    ("auto_memBlock_inner_dcache_client_out_b_bits_address", "input", 48),
    ("auto_memBlock_inner_dcache_client_out_b_bits_mask", "input", 32),
    ("auto_memBlock_inner_dcache_client_out_b_bits_data", "input", 256),
    ("auto_memBlock_inner_dcache_client_out_b_bits_corrupt", "input", 1),
    ("auto_memBlock_inner_dcache_client_out_c_ready", "input", 1),
    ("auto_memBlock_inner_dcache_client_out_c_valid", "output", 1),
    ("auto_memBlock_inner_dcache_client_out_c_bits_opcode", "output", 3),
    ("auto_memBlock_inner_dcache_client_out_c_bits_param", "output", 3),
    ("auto_memBlock_inner_dcache_client_out_c_bits_size", "output", 3),
    ("auto_memBlock_inner_dcache_client_out_c_bits_source", "output", 6),
    ("auto_memBlock_inner_dcache_client_out_c_bits_address", "output", 48),
    ("auto_memBlock_inner_dcache_client_out_c_bits_user_alias", "output", 2),
    ("auto_memBlock_inner_dcache_client_out_c_bits_user_vaddr", "output", 44),
    ("auto_memBlock_inner_dcache_client_out_c_bits_user_reqSource", "output", 5),
    ("auto_memBlock_inner_dcache_client_out_c_bits_user_needHint", "output", 1),
    ("auto_memBlock_inner_dcache_client_out_c_bits_echo_isKeyword", "output", 1),
    ("auto_memBlock_inner_dcache_client_out_c_bits_data", "output", 256),
    ("auto_memBlock_inner_dcache_client_out_c_bits_corrupt", "output", 1),
    ("auto_memBlock_inner_dcache_client_out_d_ready", "output", 1),
    ("auto_memBlock_inner_dcache_client_out_d_valid", "input", 1),
    ("auto_memBlock_inner_dcache_client_out_d_bits_opcode", "input", 4),
    ("auto_memBlock_inner_dcache_client_out_d_bits_param", "input", 2),
    ("auto_memBlock_inner_dcache_client_out_d_bits_size", "input", 3),
    ("auto_memBlock_inner_dcache_client_out_d_bits_source", "input", 6),
    ("auto_memBlock_inner_dcache_client_out_d_bits_sink", "input", 10),
    ("auto_memBlock_inner_dcache_client_out_d_bits_denied", "input", 1),
    ("auto_memBlock_inner_dcache_client_out_d_bits_echo_isKeyword", "input", 1),
    ("auto_memBlock_inner_dcache_client_out_d_bits_data", "input", 256),
    ("auto_memBlock_inner_dcache_client_out_d_bits_corrupt", "input", 1),
    ("auto_memBlock_inner_dcache_client_out_e_ready", "input", 1),
    ("auto_memBlock_inner_dcache_client_out_e_valid", "output", 1),
    ("auto_memBlock_inner_dcache_client_out_e_bits_sink", "output", 10),
    ("io_hartId", "input", 6),
    ("io_msiInfo_valid", "input", 1),
    ("io_msiInfo_bits", "input", 12),
    ("io_msiAck", "output", 1),
    ("io_clintTime_valid", "input", 1),
    ("io_clintTime_bits", "input", 64),
    ("io_reset_vector", "input", 48),
    ("io_cpu_halt", "output", 1),
    ("io_l2_flush_done", "input", 1),
    ("io_l2_flush_en", "output", 1),
    ("io_power_down_en", "output", 1),
    ("io_cpu_critical_error", "output", 1),
    ("io_resetInFrontend", "output", 1),
    ("io_traceCoreInterface_fromEncoder_enable", "input", 1),
    ("io_traceCoreInterface_fromEncoder_stall", "input", 1),
    ("io_traceCoreInterface_toEncoder_priv", "output", 3),
    ("io_traceCoreInterface_toEncoder_mstatus", "output", 64),
    ("io_traceCoreInterface_toEncoder_trap_cause", "output", 64),
    ("io_traceCoreInterface_toEncoder_trap_tval", "output", 50),
    ("io_traceCoreInterface_toEncoder_groups_0_valid", "output", 1),
    ("io_traceCoreInterface_toEncoder_groups_0_bits_iaddr", "output", 50),
    ("io_traceCoreInterface_toEncoder_groups_0_bits_itype", "output", 4),
    ("io_traceCoreInterface_toEncoder_groups_0_bits_iretire", "output", 7),
    ("io_traceCoreInterface_toEncoder_groups_0_bits_ilastsize", "output", 1),
    ("io_traceCoreInterface_toEncoder_groups_1_valid", "output", 1),
    ("io_traceCoreInterface_toEncoder_groups_1_bits_iaddr", "output", 50),
    ("io_traceCoreInterface_toEncoder_groups_1_bits_itype", "output", 4),
    ("io_traceCoreInterface_toEncoder_groups_1_bits_iretire", "output", 7),
    ("io_traceCoreInterface_toEncoder_groups_1_bits_ilastsize", "output", 1),
    ("io_traceCoreInterface_toEncoder_groups_2_valid", "output", 1),
    ("io_traceCoreInterface_toEncoder_groups_2_bits_iaddr", "output", 50),
    ("io_traceCoreInterface_toEncoder_groups_2_bits_itype", "output", 4),
    ("io_traceCoreInterface_toEncoder_groups_2_bits_iretire", "output", 7),
    ("io_traceCoreInterface_toEncoder_groups_2_bits_ilastsize", "output", 1),
    ("io_l2PfCtrl_l2_pf_master_en", "output", 1),
    ("io_l2PfCtrl_l2_pf_recv_en", "output", 1),
    ("io_l2PfCtrl_l2_pbop_en", "output", 1),
    ("io_l2PfCtrl_l2_vbop_en", "output", 1),
    ("io_l2PfCtrl_l2_tp_en", "output", 1),
    ("io_l2PfCtrl_l2_pf_delay_latency", "output", 10),
    ("io_perfEvents_1_value", "input", 6),
    ("io_perfEvents_2_value", "input", 6),
    ("io_perfEvents_3_value", "input", 6),
    ("io_perfEvents_4_value", "input", 6),
    ("io_perfEvents_5_value", "input", 6),
    ("io_perfEvents_6_value", "input", 6),
    ("io_perfEvents_7_value", "input", 6),
    ("io_perfEvents_8_value", "input", 6),
    ("io_perfEvents_9_value", "input", 6),
    ("io_perfEvents_10_value", "input", 6),
    ("io_perfEvents_11_value", "input", 6),
    ("io_perfEvents_12_value", "input", 6),
    ("io_perfEvents_13_value", "input", 6),
    ("io_perfEvents_14_value", "input", 6),
    ("io_perfEvents_15_value", "input", 6),
    ("io_perfEvents_16_value", "input", 6),
    ("io_perfEvents_17_value", "input", 6),
    ("io_perfEvents_18_value", "input", 6),
    ("io_perfEvents_19_value", "input", 6),
    ("io_perfEvents_20_value", "input", 6),
    ("io_perfEvents_21_value", "input", 6),
    ("io_perfEvents_22_value", "input", 6),
    ("io_perfEvents_23_value", "input", 6),
    ("io_perfEvents_24_value", "input", 6),
    ("io_perfEvents_25_value", "input", 6),
    ("io_perfEvents_26_value", "input", 6),
    ("io_perfEvents_27_value", "input", 6),
    ("io_perfEvents_28_value", "input", 6),
    ("io_perfEvents_29_value", "input", 6),
    ("io_perfEvents_30_value", "input", 6),
    ("io_perfEvents_31_value", "input", 6),
    ("io_perfEvents_32_value", "input", 6),
    ("io_perfEvents_33_value", "input", 6),
    ("io_perfEvents_34_value", "input", 6),
    ("io_perfEvents_35_value", "input", 6),
    ("io_perfEvents_36_value", "input", 6),
    ("io_perfEvents_37_value", "input", 6),
    ("io_perfEvents_38_value", "input", 6),
    ("io_perfEvents_39_value", "input", 6),
    ("io_perfEvents_40_value", "input", 6),
    ("io_perfEvents_41_value", "input", 6),
    ("io_perfEvents_42_value", "input", 6),
    ("io_perfEvents_43_value", "input", 6),
    ("io_perfEvents_44_value", "input", 6),
    ("io_perfEvents_45_value", "input", 6),
    ("io_perfEvents_46_value", "input", 6),
    ("io_perfEvents_47_value", "input", 6),
    ("io_perfEvents_48_value", "input", 6),
    ("io_perfEvents_49_value", "input", 6),
    ("io_perfEvents_50_value", "input", 6),
    ("io_perfEvents_51_value", "input", 6),
    ("io_perfEvents_52_value", "input", 6),
    ("io_perfEvents_53_value", "input", 6),
    ("io_perfEvents_54_value", "input", 6),
    ("io_perfEvents_55_value", "input", 6),
    ("io_perfEvents_56_value", "input", 6),
    ("io_perfEvents_57_value", "input", 6),
    ("io_perfEvents_58_value", "input", 6),
    ("io_perfEvents_59_value", "input", 6),
    ("io_perfEvents_60_value", "input", 6),
    ("io_perfEvents_61_value", "input", 6),
    ("io_perfEvents_62_value", "input", 6),
    ("io_perfEvents_63_value", "input", 6),
    ("io_perfEvents_64_value", "input", 6),
    ("io_perfEvents_65_value", "input", 6),
    ("io_perfEvents_66_value", "input", 6),
    ("io_perfEvents_67_value", "input", 6),
    ("io_perfEvents_68_value", "input", 6),
    ("io_beu_errors_icache_ecc_error_valid", "output", 1),
    ("io_beu_errors_icache_ecc_error_bits", "output", 48),
    ("io_beu_errors_dcache_ecc_error_valid", "output", 1),
    ("io_beu_errors_dcache_ecc_error_bits", "output", 48),
    ("io_beu_errors_uncache_ecc_error_valid", "output", 1),
    ("io_beu_errors_uncache_ecc_error_bits", "output", 48),
    ("io_l2_hint_valid", "input", 1),
    ("io_l2_hint_bits_sourceId", "input", 4),
    ("io_l2_hint_bits_isKeyword", "input", 1),
    ("io_l2_tlb_req_req_valid", "input", 1),
    ("io_l2_tlb_req_req_bits_vaddr", "input", 50),
    ("io_l2_tlb_req_req_bits_cmd", "input", 3),
    ("io_l2_tlb_req_req_bits_kill", "input", 1),
    ("io_l2_tlb_req_req_bits_isPrefetch", "input", 1),
    ("io_l2_tlb_req_req_bits_no_translate", "input", 1),
    ("io_l2_tlb_req_resp_valid", "output", 1),
    ("io_l2_tlb_req_resp_bits_paddr_0", "output", 48),
    ("io_l2_tlb_req_resp_bits_pbmt_0", "output", 2),
    ("io_l2_tlb_req_resp_bits_miss", "output", 1),
    ("io_l2_tlb_req_resp_bits_excp_0_gpf_ld", "output", 1),
    ("io_l2_tlb_req_resp_bits_excp_0_pf_ld", "output", 1),
    ("io_l2_tlb_req_resp_bits_excp_0_af_ld", "output", 1),
    ("io_l2_pmp_resp_ld", "output", 1),
    ("io_l2_pmp_resp_mmio", "output", 1),
    ("io_topDownInfo_l2Miss", "input", 1),
    ("io_topDownInfo_l3Miss", "input", 1),
    ("io_dft_ram_hold", "input", 1),
    ("io_dft_ram_bypass", "input", 1),
    ("io_dft_ram_bp_clken", "input", 1),
    ("io_dft_ram_aux_clk", "input", 1),
    ("io_dft_ram_aux_ckbp", "input", 1),
    ("io_dft_ram_mcp_hold", "input", 1),
    ("io_dft_cgen", "input", 1),
)


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class XSCoreParentConfig:
    """Kunminghu V2 parent geometry. / 昆明湖 V2 父级几何配置。"""

    xlen: int = 64
    vaddr_bits: int = 50
    paddr_bits: int = 48
    fetch_width: int = 6
    strict_inventory: bool = True

    # Reject geometry that diverges from the locked DefaultConfig. / 拒绝偏离锁定 DefaultConfig 的几何配置。
    def __post_init__(self) -> None:
        if self.xlen != 64:
            raise ValueError("Kunminghu V2 XSCore requires XLEN=64")
        if self.vaddr_bits < self.paddr_bits or self.paddr_bits < 8:
            raise ValueError("address widths are inconsistent")
        if self.fetch_width != 6:
            raise ValueError("Kunminghu V2 XSCore fetch width is six")


def xs_core_port_specs() -> tuple[tuple[str, str, int], ...]:
    """Return the frozen 308-port XSCore contract. / 返回冻结的 308 端口 XSCore 契约。"""

    return _XSCORE_PORT_SPECS


def _spec_width(value: Any) -> int:
    """Normalize an injected inventory width. / 规范化注入清单位宽。"""

    if isinstance(value, str):
        text = value.strip()
        if text.startswith("[") and text.endswith("]") and ":" in text:
            high, low = text[1:-1].split(":", 1)
            try:
                return max(1, abs(int(high) - int(low)) + 1)
            except ValueError:
                return 1
    try:
        return max(1, int(value or 1))
    except (TypeError, ValueError):
        return 1


def xs_core_parent_observation(
    *,
    frontend_valid: bool,
    backend_can_accept: bool,
    mem_a_valid: bool,
    mem_a_ready: bool,
    mem_d_valid: bool,
    mem_d_ready: bool,
    reset: bool = False,
    child_missing: int = 3,
) -> dict[str, int]:
    """Evaluate XSCore.scala parent handshakes for one cycle.

    The equations correspond to the Frontend/Backend admission and MemBlock
    TileLink A/D edges in XSCoreImp. They are deliberately bounded to
    parent-owned observations and do not imply complete child behavior.
    """

    blocked = bool(reset)
    missing = max(0, int(child_missing))
    return {
        "frontend_backend_fire": int(bool(frontend_valid) and bool(backend_can_accept) and not blocked),
        "mem_a_fire": int(bool(mem_a_valid) and bool(mem_a_ready) and not blocked),
        "mem_d_fire": int(bool(mem_d_valid) and bool(mem_d_ready) and not blocked),
        "child_missing": missing,
        "closure_complete": int(missing == 0 and not blocked),
    }


# =============================================================================
# Implementation
# =============================================================================
class XSCoreParent(Elaboratable):
    """Source-backed Frontend/Backend/MemBlock parent bridge. / 源码支撑的三子级父桥。"""

    # Construct explicit child injection points and the frozen port envelope. / 构造显式子级注入点及冻结端口包络。
    def __init__(
        self,
        configuration: XSCoreParentConfig | dict[str, Any] | None = None,
        injected_dependencies: dict[str, Any] | None = None,
    ) -> None:
        if configuration is None:
            self.configuration = XSCoreParentConfig()
        elif isinstance(configuration, XSCoreParentConfig):
            self.configuration = configuration
        else:
            fields = XSCoreParentConfig.__dataclass_fields__
            self.configuration = XSCoreParentConfig(
                **{key: value for key, value in dict(configuration).items() if key in fields}
            )
        deps = injected_dependencies if isinstance(injected_dependencies, dict) else {}
        self.injected_dependencies = deps
        self.frontend = deps.get("frontend") or deps.get("Frontend")
        self.backend = deps.get("backend") or deps.get("Backend")
        self.mem_block = deps.get("mem_block") or deps.get("memblock") or deps.get("MemBlock")
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.child_missing = Signal(3, name="xs_core_child_missing")
        self.child_missing_count = Signal(3, name="xs_core_child_missing_count")
        self.closure_missing = Signal(name="xs_core_closure_missing")
        self.closure_complete = Signal(name="xs_core_closure_complete")
        self.inventory: dict[str, Signal] = {}
        self.inventory_inputs: list[Signal] = []
        self.inventory_outputs: list[Signal] = []
        self._bound_outputs: set[str] = set()
        specs = tuple(
            item for item in deps.get("full_port_specs", ())
            if isinstance(item, Mapping) and item.get("name")
        )
        if not specs:
            specs = tuple({"name": name, "direction": direction, "width": width}
                          for name, direction, width in xs_core_port_specs())
        if self.configuration.strict_inventory and len(specs) != XSCORE_REFERENCE_PORT_COUNT:
            raise ValueError("XSCore inventory must contain exactly 308 ports")
        self.full_port_specs = specs
        self._install_inventory(specs)

    def _install_inventory(self, specs: Iterable[Mapping[str, Any]]) -> None:
        """Materialize exact source ports. / 实例化精确源端口。"""

        existing = {str(value.name): value for value in self.__dict__.values()
                    if isinstance(value, Signal) and value.name}
        for spec in specs:
            name = str(spec.get("name", ""))
            if not name or name in self.inventory:
                continue
            width = _spec_width(spec.get("width", 1))
            signal = existing.get(name)
            if signal is None:
                signal = Signal(width, name=name)
                setattr(self, f"_inventory_{len(self.inventory):03d}", signal)
            elif len(signal) != width:
                raise ValueError(f"XSCore inventory width mismatch for {name}")
            self.inventory[name] = signal
            setattr(self, name, signal)
            if str(spec.get("direction", "input")).lower() == "output":
                self.inventory_outputs.append(signal)
            else:
                self.inventory_inputs.append(signal)

    @staticmethod
    def _signal(obj: Any, name: str) -> Any:
        """Look up a child signal without assuming a concrete child class. / 按属性查找子级信号。"""

        value = getattr(obj, name, None) if obj is not None else None
        return value if isinstance(value, Signal) else None

    def _wire(self, module: Module, destination: Any, source: Any) -> bool:
        """Connect compatible Amaranth values and report whether bound. / 连接兼容值并返回是否成功。"""

        if not isinstance(destination, Signal) or not isinstance(source, Signal):
            return False
        if len(destination) == len(source):
            value: Any = source
        elif len(destination) < len(source):
            value = source[:len(destination)]
        else:
            value = Cat(source, Const(0, len(destination) - len(source)))
        module.d.comb += destination.eq(value)
        return True

    def _wire_output(self, module: Module, port_name: str, child: Any, child_name: str) -> None:
        """Drive one XSCore output from a child alias. / 用子级别名驱动一个 XSCore 输出。"""

        port = self.inventory.get(port_name)
        child_signal = self._signal(child, child_name)
        if port is not None and self._wire(module, port, child_signal):
            self._bound_outputs.add(port_name)

    def _wire_input(self, module: Module, port_name: str, child: Any, child_name: str) -> None:
        """Forward one XSCore input into a child alias. / 将 XSCore 输入转发到子级别名。"""

        self._wire(module, self._signal(child, child_name), self.inventory.get(port_name))

    def elaborate(self, platform: Any) -> Module:
        """Elaborate parent wiring and explicit missing-child diagnostics. / 展开父级接线及显式缺子级诊断。"""

        del platform
        module = Module()
        domain = ClockDomain("xs_core_sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        module.domains.xs_core_sync = domain

        children = (("frontend", self.frontend), ("backend", self.backend), ("mem_block", self.mem_block))
        for name, child in children:
            if child is not None:
                setattr(module.submodules, name, child)
                self._wire(module, self._signal(child, "clock"), self.clock)
                self._wire(module, self._signal(child, "reset"), self.reset)

        f, b, mem = self.frontend, self.backend, self.mem_block

        # XSCore.scala top-level fanout and Frontend/Backend handshake.
        for child in (f, b, mem):
            self._wire(module, self._signal(child, "reset_vector"), self.inventory.get("io_reset_vector"))
            self._wire(module, self._signal(child, "hart_id"), self.inventory.get("io_hartId"))
        for child_name, port_name in (
            ("msi_valid", "io_msiInfo_valid"), ("msi_bits", "io_msiInfo_bits"),
            ("clint_time_valid", "io_clintTime_valid"), ("clint_time", "io_clintTime_bits"),
            ("l2_flush_done", "io_l2_flush_done"),
        ):
            self._wire(module, self._signal(mem, child_name), self.inventory.get(port_name))
        self._wire(module, self._signal(b, "frontend_valid"), self._signal(f, "cf_valid"))
        self._wire(module, self._signal(b, "frontend_instr"), self._signal(f, "cf_instr"))
        self._wire(module, self._signal(b, "frontend_pc"), self._signal(f, "cf_pc"))
        self._wire(module, self._signal(b, "frontend_exception"), self._signal(f, "cf_exception"))
        self._wire(module, self._signal(f, "backend_can_accept"), self._signal(b, "frontend_can_accept"))
        self._wire(module, self._signal(f, "redirect_valid"), self._signal(b, "redirect_valid"))
        self._wire(module, self._signal(f, "redirect_pc"), self._signal(b, "redirect_pc"))

        # Parent-facing observable outputs from Backend/MemBlock.
        for port_name, child_name, child in (
            ("io_msiAck", "msi_ack", b), ("io_cpu_halt", "cpu_halted", b),
            ("io_cpu_critical_error", "cpu_critical_error", b),
            ("io_resetInFrontend", "reset_in_frontend", mem),
            ("io_power_down_en", "power_down_en", mem),
            ("io_l2_flush_en", "l2_flush_en", mem),
            ("io_l2_pmp_resp_ld", "l2_pmp_resp_ld", mem),
            ("io_l2_pmp_resp_mmio", "l2_pmp_resp_mmio", mem),
        ):
            self._wire_output(module, port_name, child, child_name)

        # MemBlock TileLink A/D edge from XSCore.scala.
        for port_name, child_name in (
            ("auto_memBlock_inner_buffers_out_a_valid", "tl_a_valid"),
            ("auto_memBlock_inner_buffers_out_a_bits_opcode", "tl_a_opcode"),
            ("auto_memBlock_inner_buffers_out_a_bits_source", "tl_a_source"),
            ("auto_memBlock_inner_buffers_out_a_bits_address", "tl_a_address"),
            ("auto_memBlock_inner_buffers_out_a_bits_data", "tl_a_data"),
            ("auto_memBlock_inner_buffers_out_a_bits_mask", "tl_a_mask"),
        ):
            self._wire_output(module, port_name, mem, child_name)
        for port_name, child_name in (
            ("auto_memBlock_inner_buffers_out_a_ready", "tl_a_ready"),
            ("auto_memBlock_inner_buffers_out_d_valid", "tl_d_valid"),
            ("auto_memBlock_inner_buffers_out_d_bits_source", "tl_d_source"),
            ("auto_memBlock_inner_buffers_out_d_bits_data", "tl_d_data"),
        ):
            self._wire_input(module, port_name, mem, child_name)
        self._wire_output(module, "auto_memBlock_inner_buffers_out_d_ready", mem, "refill_ready")

        # Unimplemented source edges are deterministic tie-offs; inputs are
        # consumed by private sinks so direction remains visible in RTL.
        direction_by_name = {str(item.get("name")): str(item.get("direction", "input")).lower()
                             for item in self.full_port_specs}
        for name, signal in self.inventory.items():
            if name not in self._bound_outputs and direction_by_name.get(name) == "output":
                module.d.comb += signal.eq(0)
        for index, signal in enumerate(self.inventory_inputs):
            sink = Signal(len(signal), name=f"xs_core_input_sink_{index:03d}")
            module.d.comb += sink.eq(signal)

        # Presence is not completion: only explicit PASS_COMPLETE child status
        # can clear a missing bit. This keeps the closure gate pending.
        status = self.injected_dependencies.get("child_status", {})
        missing_bits = []
        for index, name in enumerate(("frontend", "backend", "mem_block")):
            value = status.get(name) if isinstance(status, Mapping) else None
            child = (f, b, mem)[index]
            missing_bits.append(0 if child is not None and value in {"PASS_COMPLETE", "COMPLETE"} else 1)
        module.d.comb += [
            self.child_missing.eq(sum(bit << index for index, bit in enumerate(missing_bits))),
            self.child_missing_count.eq(sum(missing_bits)),
            self.closure_missing.eq(self.child_missing_count != 0),
            self.closure_complete.eq(self.child_missing_count == 0),
        ]
        return module


# Localized aliases retain source identity in provenance. / UHSC 别名保留源根身份。
UHSCXSCoreParent = XSCoreParent
XSCoreBridge = XSCoreParent
XSCore = XSCoreParent


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration: XSCoreParentConfig | dict[str, Any] | None = None,
                  injected_dependencies: dict[str, Any] | None = None) -> str:
    """Emit deterministic exact-port XSCore SystemVerilog. / 输出确定性精确端口 XSCore SystemVerilog。"""

    options = configuration if isinstance(configuration, dict) else {}
    if isinstance(configuration, XSCoreParentConfig):
        cfg = configuration
    else:
        fields = XSCoreParentConfig.__dataclass_fields__
        cfg = XSCoreParentConfig(**{key: value for key, value in options.items() if key in fields})
    deps = injected_dependencies if isinstance(injected_dependencies, dict) else {}
    top = XSCoreParent(cfg, deps)
    module_name = str(options.get("module", options.get("name", "UHSCXSCoreParent")))
    return verilog.convert(top, name=module_name, ports=list(top.inventory.values()), emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    """Print the default exact XSCore envelope. / 打印默认精确 XSCore 包络。"""

    print(build_verilog())


if __name__ == "__main__":
    main()
