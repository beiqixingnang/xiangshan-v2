"""Executable ICache and prefetch family for the V2 front end.

The seven modules share one exact, self-contained ANSI surface and remain
selectable through ``build_verilog``.

WayLookup implements a 32-entry dual-lane queue, refill updates and a guest-page
fault record. L2TlbPrefetch implements
next-line generation and four recent request records; L2TlbMissQueue implements
a depth-40 packed FIFO. InstrMMIOEntry implements its four-state handshake and
PrefetcherMonitor implements quality windows and timed recovery. IPrefetchPipe
implements translation/meta retries and two-lane miss arbitration. ICacheMainPipe
implements banked fetch data, refill waiting and ECC reporting. Full parent
closure and remaining acceptance gates are explicit follow-up obligations.
"""

from __future__ import annotations

from typing import Any, cast

from amaranth import Array, Cat, ClockDomain, Const, Elaboratable, Memory, Module, Mux, Signal, Value
from amaranth.back import verilog

# Module Contract / 模块契约
__all__ = [
    'COVERED_MODULES',
    'PORT_SPECS',
    'IcachePrefetchFamily',
    'build_verilog',
    'main',
]

# Configuration / 配置
COVERED_MODULES: tuple[str, ...] = (
    "ICacheMainPipe",
    "IPrefetchPipe",
    "WayLookup",
    "InstrMMIOEntry",
    "L2TlbPrefetch",
    "L2TlbMissQueue",
    "PrefetcherMonitor",
)


PortSpec = tuple[str, str, int]

PORT_SPECS: dict[str, tuple[PortSpec, ...]] = {
    'ICacheMainPipe': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_dataArray_toIData_0_valid', 'output', 1),
        ('io_dataArray_toIData_0_bits_vSetIdx_0', 'output', 8),
        ('io_dataArray_toIData_0_bits_vSetIdx_1', 'output', 8),
        ('io_dataArray_toIData_0_bits_waymask_0_0', 'output', 1),
        ('io_dataArray_toIData_0_bits_waymask_0_1', 'output', 1),
        ('io_dataArray_toIData_0_bits_waymask_0_2', 'output', 1),
        ('io_dataArray_toIData_0_bits_waymask_0_3', 'output', 1),
        ('io_dataArray_toIData_0_bits_waymask_1_0', 'output', 1),
        ('io_dataArray_toIData_0_bits_waymask_1_1', 'output', 1),
        ('io_dataArray_toIData_0_bits_waymask_1_2', 'output', 1),
        ('io_dataArray_toIData_0_bits_waymask_1_3', 'output', 1),
        ('io_dataArray_toIData_0_bits_blkOffset', 'output', 6),
        ('io_dataArray_toIData_1_valid', 'output', 1),
        ('io_dataArray_toIData_1_bits_vSetIdx_0', 'output', 8),
        ('io_dataArray_toIData_1_bits_vSetIdx_1', 'output', 8),
        ('io_dataArray_toIData_2_valid', 'output', 1),
        ('io_dataArray_toIData_2_bits_vSetIdx_0', 'output', 8),
        ('io_dataArray_toIData_2_bits_vSetIdx_1', 'output', 8),
        ('io_dataArray_toIData_3_ready', 'input', 1),
        ('io_dataArray_toIData_3_valid', 'output', 1),
        ('io_dataArray_toIData_3_bits_vSetIdx_0', 'output', 8),
        ('io_dataArray_toIData_3_bits_vSetIdx_1', 'output', 8),
        ('io_dataArray_fromIData_datas_0', 'input', 64),
        ('io_dataArray_fromIData_datas_1', 'input', 64),
        ('io_dataArray_fromIData_datas_2', 'input', 64),
        ('io_dataArray_fromIData_datas_3', 'input', 64),
        ('io_dataArray_fromIData_datas_4', 'input', 64),
        ('io_dataArray_fromIData_datas_5', 'input', 64),
        ('io_dataArray_fromIData_datas_6', 'input', 64),
        ('io_dataArray_fromIData_datas_7', 'input', 64),
        ('io_dataArray_fromIData_codes_0', 'input', 1),
        ('io_dataArray_fromIData_codes_1', 'input', 1),
        ('io_dataArray_fromIData_codes_2', 'input', 1),
        ('io_dataArray_fromIData_codes_3', 'input', 1),
        ('io_dataArray_fromIData_codes_4', 'input', 1),
        ('io_dataArray_fromIData_codes_5', 'input', 1),
        ('io_dataArray_fromIData_codes_6', 'input', 1),
        ('io_dataArray_fromIData_codes_7', 'input', 1),
        ('io_metaArrayFlush_0_valid', 'output', 1),
        ('io_metaArrayFlush_0_bits_virIdx', 'output', 8),
        ('io_metaArrayFlush_0_bits_waymask', 'output', 4),
        ('io_metaArrayFlush_1_valid', 'output', 1),
        ('io_metaArrayFlush_1_bits_virIdx', 'output', 8),
        ('io_metaArrayFlush_1_bits_waymask', 'output', 4),
        ('io_touch_0_valid', 'output', 1),
        ('io_touch_0_bits_vSetIdx', 'output', 8),
        ('io_touch_0_bits_way', 'output', 2),
        ('io_touch_1_valid', 'output', 1),
        ('io_touch_1_bits_vSetIdx', 'output', 8),
        ('io_touch_1_bits_way', 'output', 2),
        ('io_wayLookupRead_ready', 'output', 1),
        ('io_wayLookupRead_valid', 'input', 1),
        ('io_wayLookupRead_bits_entry_vSetIdx_0', 'input', 8),
        ('io_wayLookupRead_bits_entry_vSetIdx_1', 'input', 8),
        ('io_wayLookupRead_bits_entry_waymask_0', 'input', 4),
        ('io_wayLookupRead_bits_entry_waymask_1', 'input', 4),
        ('io_wayLookupRead_bits_entry_ptag_0', 'input', 36),
        ('io_wayLookupRead_bits_entry_ptag_1', 'input', 36),
        ('io_wayLookupRead_bits_entry_itlb_exception_0', 'input', 2),
        ('io_wayLookupRead_bits_entry_itlb_exception_1', 'input', 2),
        ('io_wayLookupRead_bits_entry_itlb_pbmt_0', 'input', 2),
        ('io_wayLookupRead_bits_entry_itlb_pbmt_1', 'input', 2),
        ('io_wayLookupRead_bits_entry_meta_codes_0', 'input', 1),
        ('io_wayLookupRead_bits_entry_meta_codes_1', 'input', 1),
        ('io_wayLookupRead_bits_gpf_gpaddr', 'input', 56),
        ('io_wayLookupRead_bits_gpf_isForVSnonLeafPTE', 'input', 1),
        ('io_mshr_req_ready', 'input', 1),
        ('io_mshr_req_valid', 'output', 1),
        ('io_mshr_req_bits_blkPaddr', 'output', 42),
        ('io_mshr_req_bits_vSetIdx', 'output', 8),
        ('io_mshr_resp_valid', 'input', 1),
        ('io_mshr_resp_bits_blkPaddr', 'input', 42),
        ('io_mshr_resp_bits_vSetIdx', 'input', 8),
        ('io_mshr_resp_bits_data', 'input', 512),
        ('io_mshr_resp_bits_corrupt', 'input', 1),
        ('io_ecc_enable', 'input', 1),
        ('io_fetch_req_ready', 'output', 1),
        ('io_fetch_req_valid', 'input', 1),
        ('io_fetch_req_bits_pcMemRead_0_startAddr', 'input', 50),
        ('io_fetch_req_bits_pcMemRead_0_nextlineStart', 'input', 50),
        ('io_fetch_req_bits_pcMemRead_1_startAddr', 'input', 50),
        ('io_fetch_req_bits_pcMemRead_1_nextlineStart', 'input', 50),
        ('io_fetch_req_bits_pcMemRead_2_startAddr', 'input', 50),
        ('io_fetch_req_bits_pcMemRead_2_nextlineStart', 'input', 50),
        ('io_fetch_req_bits_pcMemRead_3_startAddr', 'input', 50),
        ('io_fetch_req_bits_pcMemRead_3_nextlineStart', 'input', 50),
        ('io_fetch_req_bits_pcMemRead_4_startAddr', 'input', 50),
        ('io_fetch_req_bits_pcMemRead_4_nextlineStart', 'input', 50),
        ('io_fetch_req_bits_readValid_0', 'input', 1),
        ('io_fetch_req_bits_readValid_1', 'input', 1),
        ('io_fetch_req_bits_readValid_2', 'input', 1),
        ('io_fetch_req_bits_readValid_3', 'input', 1),
        ('io_fetch_req_bits_readValid_4', 'input', 1),
        ('io_fetch_req_bits_backendException', 'input', 1),
        ('io_fetch_req_bits_hasSatpFlush', 'input', 1),
        ('io_fetch_resp_valid', 'output', 1),
        ('io_fetch_resp_bits_doubleline', 'output', 1),
        ('io_fetch_resp_bits_vaddr_0', 'output', 50),
        ('io_fetch_resp_bits_vaddr_1', 'output', 50),
        ('io_fetch_resp_bits_data', 'output', 512),
        ('io_fetch_resp_bits_paddr_0', 'output', 48),
        ('io_fetch_resp_bits_exception_0', 'output', 2),
        ('io_fetch_resp_bits_exception_1', 'output', 2),
        ('io_fetch_resp_bits_pmp_mmio_0', 'output', 1),
        ('io_fetch_resp_bits_pmp_mmio_1', 'output', 1),
        ('io_fetch_resp_bits_itlb_pbmt_0', 'output', 2),
        ('io_fetch_resp_bits_itlb_pbmt_1', 'output', 2),
        ('io_fetch_resp_bits_backendException', 'output', 1),
        ('io_fetch_resp_bits_hasSatpFlush', 'output', 1),
        ('io_fetch_resp_bits_gpaddr', 'output', 56),
        ('io_fetch_resp_bits_isForVSnonLeafPTE', 'output', 1),
        ('io_fetch_topdownIcacheMiss', 'output', 1),
        ('io_flush', 'input', 1),
        ('io_pmp_0_req_valid', 'output', 1),
        ('io_pmp_0_req_bits_addr', 'output', 48),
        ('io_pmp_0_resp_instr', 'input', 1),
        ('io_pmp_0_resp_mmio', 'input', 1),
        ('io_pmp_1_req_valid', 'output', 1),
        ('io_pmp_1_req_bits_addr', 'output', 48),
        ('io_pmp_1_resp_instr', 'input', 1),
        ('io_pmp_1_resp_mmio', 'input', 1),
        ('io_respStall', 'input', 1),
        ('io_errors_0_valid', 'output', 1),
        ('io_errors_0_bits_paddr', 'output', 48),
        ('io_errors_0_bits_report_to_beu', 'output', 1),
        ('io_errors_1_valid', 'output', 1),
        ('io_errors_1_bits_paddr', 'output', 48),
        ('io_errors_1_bits_report_to_beu', 'output', 1),
        ('io_perfInfo_only_0_hit', 'output', 1),
        ('io_perfInfo_only_0_miss', 'output', 1),
        ('io_perfInfo_hit_0_hit_1', 'output', 1),
        ('io_perfInfo_hit_0_miss_1', 'output', 1),
        ('io_perfInfo_miss_0_hit_1', 'output', 1),
        ('io_perfInfo_miss_0_miss_1', 'output', 1),
        ('io_perfInfo_bank_hit_1', 'output', 1),
        ('io_perfInfo_hit', 'output', 1),
    ),
    'IPrefetchPipe': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_csr_pf_enable', 'input', 1),
        ('io_flush', 'input', 1),
        ('io_req_ready', 'output', 1),
        ('io_req_valid', 'input', 1),
        ('io_req_bits_startAddr', 'input', 50),
        ('io_req_bits_nextlineStart', 'input', 50),
        ('io_req_bits_ftqIdx_flag', 'input', 1),
        ('io_req_bits_ftqIdx_value', 'input', 6),
        ('io_req_bits_isSoftPrefetch', 'input', 1),
        ('io_req_bits_backendException', 'input', 2),
        ('io_flushFromBpu_s2_valid', 'input', 1),
        ('io_flushFromBpu_s2_bits_flag', 'input', 1),
        ('io_flushFromBpu_s2_bits_value', 'input', 6),
        ('io_flushFromBpu_s3_valid', 'input', 1),
        ('io_flushFromBpu_s3_bits_flag', 'input', 1),
        ('io_flushFromBpu_s3_bits_value', 'input', 6),
        ('io_itlb_0_req_valid', 'output', 1),
        ('io_itlb_0_req_bits_vaddr', 'output', 50),
        ('io_itlb_0_resp_bits_paddr_0', 'input', 48),
        ('io_itlb_0_resp_bits_gpaddr_0', 'input', 64),
        ('io_itlb_0_resp_bits_pbmt_0', 'input', 2),
        ('io_itlb_0_resp_bits_miss', 'input', 1),
        ('io_itlb_0_resp_bits_isForVSnonLeafPTE', 'input', 1),
        ('io_itlb_0_resp_bits_excp_0_gpf_instr', 'input', 1),
        ('io_itlb_0_resp_bits_excp_0_pf_instr', 'input', 1),
        ('io_itlb_0_resp_bits_excp_0_af_instr', 'input', 1),
        ('io_itlb_1_req_valid', 'output', 1),
        ('io_itlb_1_req_bits_vaddr', 'output', 50),
        ('io_itlb_1_resp_bits_paddr_0', 'input', 48),
        ('io_itlb_1_resp_bits_gpaddr_0', 'input', 64),
        ('io_itlb_1_resp_bits_pbmt_0', 'input', 2),
        ('io_itlb_1_resp_bits_miss', 'input', 1),
        ('io_itlb_1_resp_bits_isForVSnonLeafPTE', 'input', 1),
        ('io_itlb_1_resp_bits_excp_0_gpf_instr', 'input', 1),
        ('io_itlb_1_resp_bits_excp_0_pf_instr', 'input', 1),
        ('io_itlb_1_resp_bits_excp_0_af_instr', 'input', 1),
        ('io_itlbFlushPipe', 'output', 1),
        ('io_pmp_0_req_valid', 'output', 1),
        ('io_pmp_0_req_bits_addr', 'output', 48),
        ('io_pmp_0_resp_instr', 'input', 1),
        ('io_pmp_0_resp_mmio', 'input', 1),
        ('io_pmp_1_req_valid', 'output', 1),
        ('io_pmp_1_req_bits_addr', 'output', 48),
        ('io_pmp_1_resp_instr', 'input', 1),
        ('io_pmp_1_resp_mmio', 'input', 1),
        ('io_metaRead_toIMeta_ready', 'input', 1),
        ('io_metaRead_toIMeta_valid', 'output', 1),
        ('io_metaRead_toIMeta_bits_vSetIdx_0', 'output', 8),
        ('io_metaRead_toIMeta_bits_vSetIdx_1', 'output', 8),
        ('io_metaRead_toIMeta_bits_isDoubleLine', 'output', 1),
        ('io_metaRead_fromIMeta_metas_0_0_tag', 'input', 36),
        ('io_metaRead_fromIMeta_metas_0_1_tag', 'input', 36),
        ('io_metaRead_fromIMeta_metas_0_2_tag', 'input', 36),
        ('io_metaRead_fromIMeta_metas_0_3_tag', 'input', 36),
        ('io_metaRead_fromIMeta_metas_1_0_tag', 'input', 36),
        ('io_metaRead_fromIMeta_metas_1_1_tag', 'input', 36),
        ('io_metaRead_fromIMeta_metas_1_2_tag', 'input', 36),
        ('io_metaRead_fromIMeta_metas_1_3_tag', 'input', 36),
        ('io_metaRead_fromIMeta_codes_0_0', 'input', 1),
        ('io_metaRead_fromIMeta_codes_0_1', 'input', 1),
        ('io_metaRead_fromIMeta_codes_0_2', 'input', 1),
        ('io_metaRead_fromIMeta_codes_0_3', 'input', 1),
        ('io_metaRead_fromIMeta_codes_1_0', 'input', 1),
        ('io_metaRead_fromIMeta_codes_1_1', 'input', 1),
        ('io_metaRead_fromIMeta_codes_1_2', 'input', 1),
        ('io_metaRead_fromIMeta_codes_1_3', 'input', 1),
        ('io_metaRead_fromIMeta_entryValid_0_0', 'input', 1),
        ('io_metaRead_fromIMeta_entryValid_0_1', 'input', 1),
        ('io_metaRead_fromIMeta_entryValid_0_2', 'input', 1),
        ('io_metaRead_fromIMeta_entryValid_0_3', 'input', 1),
        ('io_metaRead_fromIMeta_entryValid_1_0', 'input', 1),
        ('io_metaRead_fromIMeta_entryValid_1_1', 'input', 1),
        ('io_metaRead_fromIMeta_entryValid_1_2', 'input', 1),
        ('io_metaRead_fromIMeta_entryValid_1_3', 'input', 1),
        ('io_MSHRReq_ready', 'input', 1),
        ('io_MSHRReq_valid', 'output', 1),
        ('io_MSHRReq_bits_blkPaddr', 'output', 42),
        ('io_MSHRReq_bits_vSetIdx', 'output', 8),
        ('io_MSHRResp_valid', 'input', 1),
        ('io_MSHRResp_bits_blkPaddr', 'input', 42),
        ('io_MSHRResp_bits_vSetIdx', 'input', 8),
        ('io_MSHRResp_bits_waymask', 'input', 4),
        ('io_MSHRResp_bits_corrupt', 'input', 1),
        ('io_wayLookupWrite_ready', 'input', 1),
        ('io_wayLookupWrite_valid', 'output', 1),
        ('io_wayLookupWrite_bits_entry_vSetIdx_0', 'output', 8),
        ('io_wayLookupWrite_bits_entry_vSetIdx_1', 'output', 8),
        ('io_wayLookupWrite_bits_entry_waymask_0', 'output', 4),
        ('io_wayLookupWrite_bits_entry_waymask_1', 'output', 4),
        ('io_wayLookupWrite_bits_entry_ptag_0', 'output', 36),
        ('io_wayLookupWrite_bits_entry_ptag_1', 'output', 36),
        ('io_wayLookupWrite_bits_entry_itlb_exception_0', 'output', 2),
        ('io_wayLookupWrite_bits_entry_itlb_exception_1', 'output', 2),
        ('io_wayLookupWrite_bits_entry_itlb_pbmt_0', 'output', 2),
        ('io_wayLookupWrite_bits_entry_itlb_pbmt_1', 'output', 2),
        ('io_wayLookupWrite_bits_entry_meta_codes_0', 'output', 1),
        ('io_wayLookupWrite_bits_entry_meta_codes_1', 'output', 1),
        ('io_wayLookupWrite_bits_gpf_gpaddr', 'output', 56),
        ('io_wayLookupWrite_bits_gpf_isForVSnonLeafPTE', 'output', 1),
    ),
    'WayLookup': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_flush', 'input', 1),
        ('io_read_ready', 'input', 1),
        ('io_read_valid', 'output', 1),
        ('io_read_bits_entry_vSetIdx_0', 'output', 8),
        ('io_read_bits_entry_vSetIdx_1', 'output', 8),
        ('io_read_bits_entry_waymask_0', 'output', 4),
        ('io_read_bits_entry_waymask_1', 'output', 4),
        ('io_read_bits_entry_ptag_0', 'output', 36),
        ('io_read_bits_entry_ptag_1', 'output', 36),
        ('io_read_bits_entry_itlb_exception_0', 'output', 2),
        ('io_read_bits_entry_itlb_exception_1', 'output', 2),
        ('io_read_bits_entry_itlb_pbmt_0', 'output', 2),
        ('io_read_bits_entry_itlb_pbmt_1', 'output', 2),
        ('io_read_bits_entry_meta_codes_0', 'output', 1),
        ('io_read_bits_entry_meta_codes_1', 'output', 1),
        ('io_read_bits_gpf_gpaddr', 'output', 56),
        ('io_read_bits_gpf_isForVSnonLeafPTE', 'output', 1),
        ('io_write_ready', 'output', 1),
        ('io_write_valid', 'input', 1),
        ('io_write_bits_entry_vSetIdx_0', 'input', 8),
        ('io_write_bits_entry_vSetIdx_1', 'input', 8),
        ('io_write_bits_entry_waymask_0', 'input', 4),
        ('io_write_bits_entry_waymask_1', 'input', 4),
        ('io_write_bits_entry_ptag_0', 'input', 36),
        ('io_write_bits_entry_ptag_1', 'input', 36),
        ('io_write_bits_entry_itlb_exception_0', 'input', 2),
        ('io_write_bits_entry_itlb_exception_1', 'input', 2),
        ('io_write_bits_entry_itlb_pbmt_0', 'input', 2),
        ('io_write_bits_entry_itlb_pbmt_1', 'input', 2),
        ('io_write_bits_entry_meta_codes_0', 'input', 1),
        ('io_write_bits_entry_meta_codes_1', 'input', 1),
        ('io_write_bits_gpf_gpaddr', 'input', 56),
        ('io_write_bits_gpf_isForVSnonLeafPTE', 'input', 1),
        ('io_update_valid', 'input', 1),
        ('io_update_bits_blkPaddr', 'input', 42),
        ('io_update_bits_vSetIdx', 'input', 8),
        ('io_update_bits_waymask', 'input', 4),
        ('io_update_bits_corrupt', 'input', 1),
    ),
    'InstrMMIOEntry': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_req_ready', 'output', 1),
        ('io_req_valid', 'input', 1),
        ('io_req_bits_addr', 'input', 48),
        ('io_req_bits_flush', 'input', 1),
        ('io_resp_valid', 'output', 1),
        ('io_resp_bits_data', 'output', 32),
        ('io_resp_bits_corrupt', 'output', 1),
        ('io_mmio_acquire_ready', 'input', 1),
        ('io_mmio_acquire_valid', 'output', 1),
        ('io_mmio_acquire_bits_address', 'output', 48),
        ('io_mmio_grant_valid', 'input', 1),
        ('io_mmio_grant_bits_data', 'input', 64),
        ('io_mmio_grant_bits_corrupt', 'input', 1),
        ('io_wfi_wfiReq', 'input', 1),
        ('io_wfi_wfiSafe', 'output', 1),
    ),
    'L2TlbPrefetch': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_sfence_valid', 'input', 1),
        ('io_csr_satp_changed', 'input', 1),
        ('io_csr_vsatp_mode', 'input', 4),
        ('io_csr_vsatp_changed', 'input', 1),
        ('io_csr_hgatp_mode', 'input', 4),
        ('io_csr_hgatp_changed', 'input', 1),
        ('io_csr_priv_virt', 'input', 1),
        ('io_csr_priv_virt_changed', 'input', 1),
        ('io_in_valid', 'input', 1),
        ('io_in_bits_vpn', 'input', 38),
        ('io_out_ready', 'input', 1),
        ('io_out_valid', 'output', 1),
        ('io_out_bits_req_info_vpn', 'output', 38),
        ('io_out_bits_req_info_s2xlate', 'output', 2),
    ),
    'L2TlbMissQueue': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_sfence_valid', 'input', 1),
        ('io_csr_satp_changed', 'input', 1),
        ('io_csr_vsatp_changed', 'input', 1),
        ('io_csr_hgatp_changed', 'input', 1),
        ('io_csr_priv_virt_changed', 'input', 1),
        ('io_in_ready', 'output', 1),
        ('io_in_valid', 'input', 1),
        ('io_in_bits_req_info_vpn', 'input', 38),
        ('io_in_bits_req_info_s2xlate', 'input', 2),
        ('io_in_bits_req_info_source', 'input', 2),
        ('io_in_bits_isLLptw', 'input', 1),
        ('io_out_ready', 'input', 1),
        ('io_out_valid', 'output', 1),
        ('io_out_bits_req_info_vpn', 'output', 38),
        ('io_out_bits_req_info_s2xlate', 'output', 2),
        ('io_out_bits_req_info_source', 'output', 2),
        ('io_out_bits_isHptwReq', 'output', 1),
        ('io_out_bits_isLLptw', 'output', 1),
        ('io_out_bits_hptwId', 'output', 3),
    ),
    'PrefetcherMonitor': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_timely_total_prefetch', 'input', 1),
        ('io_timely_late_hit_prefetch', 'input', 1),
        ('io_timely_late_miss_prefetch', 'input', 1),
        ('io_validity_good_prefetch', 'input', 1),
        ('io_validity_bad_prefetch', 'input', 1),
        ('io_pf_ctrl_enable', 'output', 1),
        ('io_pf_ctrl_confidence', 'output', 1),
    ),
}








# Implementation / 实现
class Queue40_L2TlbMQBundle(Elaboratable):
    """Packed depth-40 queue matching the locked Queue40_L2TlbMQBundle.

    The Queue stores one 47-bit record.  The three high bits are the
    surrounding L2 TLB's HPTW fields and are zero for this input path; keeping
    them in the packed record preserves the locked RAM width and bit slices.
    """

    def __init__(self) -> None:
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.io_enq_ready = Signal(name="io_enq_ready")
        self.io_enq_valid = Signal(name="io_enq_valid")
        self.io_enq_bits_req_info_vpn = Signal(38, name="io_enq_bits_req_info_vpn")
        self.io_enq_bits_req_info_s2xlate = Signal(2, name="io_enq_bits_req_info_s2xlate")
        self.io_enq_bits_req_info_source = Signal(2, name="io_enq_bits_req_info_source")
        self.io_enq_bits_isLLptw = Signal(name="io_enq_bits_isLLptw")
        self.io_deq_ready = Signal(name="io_deq_ready")
        self.io_deq_valid = Signal(name="io_deq_valid")
        self.io_deq_bits_req_info_vpn = Signal(38, name="io_deq_bits_req_info_vpn")
        self.io_deq_bits_req_info_s2xlate = Signal(2, name="io_deq_bits_req_info_s2xlate")
        self.io_deq_bits_req_info_source = Signal(2, name="io_deq_bits_req_info_source")
        self.io_deq_bits_isHptwReq = Signal(name="io_deq_bits_isHptwReq")
        self.io_deq_bits_isLLptw = Signal(name="io_deq_bits_isLLptw")
        self.io_deq_bits_hptwId = Signal(3, name="io_deq_bits_hptwId")
        self.io_flush = Signal(name="io_flush")

    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        depth = 40
        ptr_width = 6
        enq_ptr_value = Signal(ptr_width, reset=0, name="enq_ptr_value")
        deq_ptr_value = Signal(ptr_width, reset=0, name="deq_ptr_value")
        maybe_full = Signal(reset=0, name="maybe_full")
        packed_in = Cat(
            self.io_enq_bits_req_info_vpn,
            self.io_enq_bits_req_info_s2xlate,
            self.io_enq_bits_req_info_source,
            Const(0, 1), self.io_enq_bits_isLLptw, Const(0, 3),
        )
        ram_ext = Memory(width=47, depth=depth, name="ram_ext")
        read_port = ram_ext.read_port(domain="comb")
        write_port = ram_ext.write_port(domain="sync")
        # Match the locked RAM word identity when Yosys maps the memory.
        module.submodules["ram_ext.Memory"] = ram_ext
        ram_read_data = Signal(47, name="_ram_ext_R0_data")

        ptr_match = enq_ptr_value == deq_ptr_value
        empty = ptr_match & ~maybe_full
        full = ptr_match & maybe_full
        do_enq = ~full & self.io_enq_valid
        do_deq = self.io_deq_ready & ~empty
        next_enq = Mux(enq_ptr_value == depth - 1, 0, enq_ptr_value + 1)
        next_deq = Mux(deq_ptr_value == depth - 1, 0, deq_ptr_value + 1)
        module.d.comb += [
            self.io_enq_ready.eq(~full),
            self.io_deq_valid.eq(~empty),
            read_port.addr.eq(deq_ptr_value),
            write_port.addr.eq(enq_ptr_value),
            write_port.en.eq(do_enq),
            write_port.data.eq(packed_in),
            ram_read_data.eq(read_port.data),
            self.io_deq_bits_req_info_vpn.eq(ram_read_data[0:38]),
            self.io_deq_bits_req_info_s2xlate.eq(ram_read_data[38:40]),
            self.io_deq_bits_req_info_source.eq(ram_read_data[40:42]),
            self.io_deq_bits_isHptwReq.eq(ram_read_data[42]),
            self.io_deq_bits_isLLptw.eq(ram_read_data[43]),
            self.io_deq_bits_hptwId.eq(ram_read_data[44:47]),
        ]
        with cast(Any, module).If(self.io_flush):
            module.d.sync += [enq_ptr_value.eq(0), deq_ptr_value.eq(0), maybe_full.eq(0)]
        with cast(Any, module).Else():
            with cast(Any, module).If(do_enq):
                module.d.sync += enq_ptr_value.eq(next_enq)
            with cast(Any, module).If(do_deq):
                module.d.sync += deq_ptr_value.eq(next_deq)
            with cast(Any, module).If(do_enq != do_deq):
                module.d.sync += maybe_full.eq(do_enq)
        return module


class PrefetchMissArbiter(Elaboratable):
    """Select lane zero before lane one, preserving idle payload visibility."""

    def __init__(self) -> None:
        self.valid = [Signal(name=f"io_in_{lane}_valid") for lane in range(2)]
        self.ready = [Signal(name=f"io_in_{lane}_ready") for lane in range(2)]
        self.block = [Signal(42, name=f"io_in_{lane}_bits_blkPaddr") for lane in range(2)]
        self.vset = [Signal(8, name=f"io_in_{lane}_bits_vSetIdx") for lane in range(2)]
        self.out_valid = Signal(name="io_out_valid")
        self.out_ready = Signal(name="io_out_ready")
        self.out_block = Signal(42, name="io_out_bits_blkPaddr")
        self.out_vset = Signal(8, name="io_out_bits_vSetIdx")

    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        module.d.comb += [self.ready[0].eq(self.out_ready),
                          self.ready[1].eq(~self.valid[0] & self.out_ready),
                          self.out_valid.eq(self.valid[0] | self.valid[1]),
                          self.out_block.eq(Mux(self.valid[0], self.block[0], self.block[1])),
                          self.out_vset.eq(Mux(self.valid[0], self.vset[0], self.vset[1]))]
        return module


class IcachePrefetchFamily(Elaboratable):
    """One exact locked member selected by name."""

    def __init__(self, member: str = "ICacheMainPipe") -> None:
        if member not in PORT_SPECS:
            raise ValueError(f"unknown member: {member}")
        self.member = member
        self.specs = PORT_SPECS[member]
        self.ports: dict[str, Signal] = {
            name: Signal(width, name=name) for name, _direction, width in self.specs
        }

    def _domain(self, module: Module) -> None:
        if "clock" in self.ports and "reset" in self.ports:
            domain = ClockDomain("sync", async_reset=True)
            domain.clk = self.ports["clock"]
            domain.rst = self.ports["reset"]
            module.domains.sync = domain

    def _defaults(self, expressions: dict[str, Any]) -> None:
        """Populate a single expression for every output port."""

        for name, direction, _width_value in self.specs:
            if direction == "output" and name not in expressions:
                expressions[name] = Const(0, len(self.ports[name]))

    def _instr_mmio(self, module: Module, expressions: dict[str, Any]) -> None:
        """Four-state MMIO request/grant/response with latched flush."""

        p = self.ports
        state = Signal(2, init=0, name="state")
        addr = Signal(48, reset_less=True, name="req_addr")
        data = Signal(64, init=0, name="respDataReg")
        corrupt = Signal(init=0, name="respCorruptReg")
        flush_pending = Signal(init=0, name="needFlush")
        idle, acquire, grant, response = (0, 1, 2, 3)
        req_fire = p["io_req_valid"] & (state == idle)
        acquire_valid = (state == acquire) & ~p["io_wfi_wfiReq"]
        grant_fire = (state == grant) & p["io_mmio_grant_valid"]
        module.d.comb += [
            p["io_req_ready"].eq(state == idle),
            p["io_mmio_acquire_valid"].eq(acquire_valid),
            p["io_mmio_acquire_bits_address"].eq(Cat(Const(0, 3), addr[3:])),
            p["io_resp_valid"].eq((state == response) & ~flush_pending),
            p["io_resp_bits_corrupt"].eq(corrupt),
            p["io_resp_bits_data"].eq(
                Mux(addr[1:3] == 0, data[:32],
                    Mux(addr[1:3] == 1, data[16:48],
                        Mux(addr[1:3] == 2, data[32:64], Cat(data[48:64], Const(0, 16)))))
            ),
            p["io_wfi_wfiSafe"].eq(state != grant),
        ]
        module.d.sync += flush_pending.eq(
            (p["io_req_bits_flush"] & (state != idle) & (state != response))
            | (flush_pending & (state != response)))
        with cast(Any, module).If(state == response):
            module.d.sync += state.eq(idle)
        with cast(Any, module).Elif(grant_fire):
            module.d.sync += state.eq(response)
        with cast(Any, module).Elif(acquire_valid & p["io_mmio_acquire_ready"]):
            module.d.sync += state.eq(grant)
        with cast(Any, module).Elif(req_fire):
            module.d.sync += [state.eq(acquire), addr.eq(p["io_req_bits_addr"])]
        with cast(Any, module).If(grant_fire):
            module.d.sync += [data.eq(p["io_mmio_grant_bits_data"]), corrupt.eq(p["io_mmio_grant_bits_corrupt"])]
        for name in ("io_req_ready", "io_mmio_acquire_valid", "io_mmio_acquire_bits_address",
                     "io_resp_valid", "io_resp_bits_corrupt", "io_resp_bits_data", "io_wfi_wfiSafe"):
            expressions[name] = p[name]

    def _way_lookup(self, module: Module, expressions: dict[str, Any]) -> None:
        """Store 32 dual-lane lookup entries and one pending guest-page fault."""

        p = self.ports
        fields = ("vSetIdx", "waymask", "ptag", "itlb_exception", "itlb_pbmt", "meta_codes")
        entries = [{f"{field}_{lane}": Signal(
            len(p[f"io_write_bits_entry_{field}_{lane}"]), name=f"entries_{slot}_{field}_{lane}")
            for field in fields for lane in range(2)} for slot in range(32)]
        read_value = Signal(5, name="readPtr_value")
        read_flag = Signal(name="readPtr_flag")
        write_value = Signal(5, name="writePtr_value")
        write_flag = Signal(name="writePtr_flag")
        gpf_value = Signal(5, name="gpfPtr_value")
        gpf_flag = Signal(name="gpfPtr_flag")
        gpf_valid = Signal(name="gpf_entry_valid")
        gpf_addr = Signal(56, name="gpf_entry_bits_gpaddr")
        gpf_nonleaf = Signal(name="gpf_entry_bits_isForVSnonLeafPTE")
        read_ptr = cast(Value, Cat(read_value, read_flag))
        write_ptr = cast(Value, Cat(write_value, write_flag))
        empty = Signal(name="empty")
        bypass = Signal(name="can_bypass")
        gpf_hit = Signal(name="gpf_hit")
        module.d.comb += [empty.eq(read_ptr == write_ptr),
                          bypass.eq(empty & p["io_write_valid"]),
                          gpf_hit.eq(gpf_valid & (Cat(gpf_value, gpf_flag) == read_ptr)),
                          p["io_read_valid"].eq(~empty | p["io_write_valid"])]
        read_fire = p["io_read_ready"] & p["io_read_valid"]
        full = (read_value == write_value) & (read_flag != write_flag)
        module.d.comb += p["io_write_ready"].eq(~full & ~(gpf_valid & ~(read_fire & gpf_hit)))
        write_fire = p["io_write_valid"] & p["io_write_ready"]
        for field in fields:
            for lane in range(2):
                key = f"{field}_{lane}"
                output = f"io_read_bits_entry_{key}"
                module.d.comb += p[output].eq(Mux(bypass, p[f"io_write_bits_entry_{key}"],
                                                Array(entry[key] for entry in entries)[read_value]))
                expressions[output] = p[output]
        module.d.comb += [
            p["io_read_bits_gpf_gpaddr"].eq(Mux(bypass, p["io_write_bits_gpf_gpaddr"],
                                                Mux(gpf_hit, gpf_addr, 0))),
            p["io_read_bits_gpf_isForVSnonLeafPTE"].eq(Mux(
                bypass, p["io_write_bits_gpf_isForVSnonLeafPTE"], gpf_hit & gpf_nonleaf)),
        ]
        for slot, entry in enumerate(entries):
            with cast(Any, module.If(write_fire & (write_value == slot))):
                module.d.sync += [reg.eq(p[f"io_write_bits_entry_{key}"]) for key, reg in entry.items()]
            with cast(Any, module.Else()):
                for lane in range(2):
                    tag = entry[f"ptag_{lane}"]
                    waymask = entry[f"waymask_{lane}"]
                    update = (p["io_update_valid"] & ~p["io_update_bits_corrupt"]
                              & (p["io_update_bits_vSetIdx"] == entry[f"vSetIdx_{lane}"]))
                    with cast(Any, module.If(update)):
                        with cast(Any, module.If(p["io_update_bits_blkPaddr"][6:42] == tag)):
                            module.d.sync += [waymask.eq(p["io_update_bits_waymask"]),
                                              entry[f"meta_codes_{lane}"].eq(tag.xor())]
                        with cast(Any, module.Elif(p["io_update_bits_waymask"] == waymask)):
                            module.d.sync += waymask.eq(0)
        with cast(Any, module).If(p["io_flush"]):
            module.d.sync += [read_ptr.eq(0), write_ptr.eq(0)]
        with cast(Any, module.Else()):
            with cast(Any, module.If(read_fire)):
                module.d.sync += read_ptr.eq(read_ptr + 1)
            with cast(Any, module.If(write_fire)):
                module.d.sync += write_ptr.eq(write_ptr + 1)
        guest_fault = ((p["io_write_bits_entry_itlb_exception_0"] == 2)
                       | (p["io_write_bits_entry_itlb_exception_1"] == 2))
        with cast(Any, module.If(write_fire & guest_fault)):
            module.d.sync += [
                gpf_valid.eq(~(bypass & read_fire)),
                gpf_addr.eq(p["io_write_bits_gpf_gpaddr"]),
                gpf_nonleaf.eq(p["io_write_bits_gpf_isForVSnonLeafPTE"]),
                cast(Value, Cat(gpf_value, gpf_flag)).eq(write_ptr),
            ]
        with cast(Any, module.Else()):
            module.d.sync += gpf_valid.eq(~p["io_flush"] & gpf_valid & ~(read_fire & gpf_hit & ~bypass))
            with cast(Any, module.If(p["io_flush"])):
                module.d.sync += [gpf_addr.eq(0), gpf_nonleaf.eq(0)]
        for output in ("io_write_ready", "io_read_valid", "io_read_bits_gpf_gpaddr",
                       "io_read_bits_gpf_isForVSnonLeafPTE"):
            expressions[output] = p[output]

    def _tlb_prefetch(self, module: Module, expressions: dict[str, Any]) -> None:
        """Prefetch the next VPN line and suppress four recent sent requests."""

        p = self.ports
        valid = Signal(name="v")
        next_req = Signal(38, reset_less=True, name="next_req")
        old_index = Signal(2, name="old_index")
        old_reqs = [Signal(38, reset_less=True, name=f"old_reqs_{i}") for i in range(4)]
        old_valid = [Signal(name=f"old_v_{i}") for i in range(4)]
        next_line = (cast(Any, p["io_in_bits_vpn"][3:38]) + 1)[:35]
        flush = (p["io_sfence_valid"] | p["io_csr_satp_changed"]
                 | p["io_csr_vsatp_changed"] | p["io_csr_hgatp_changed"]
                 | p["io_csr_priv_virt_changed"])
        duplicate: Any = Const(0)
        for record, record_valid in zip(old_reqs, old_valid):
            duplicate = duplicate | ((record[3:38] == next_line) & record_valid)
        fire = p["io_out_ready"] & valid
        module.d.comb += [
            p["io_out_valid"].eq(valid),
            p["io_out_bits_req_info_vpn"].eq(next_req),
            p["io_out_bits_req_info_s2xlate"].eq(Cat(
                p["io_csr_priv_virt"] & (p["io_csr_vsatp_mode"] != 0),
                p["io_csr_priv_virt"] & (p["io_csr_hgatp_mode"] != 0))),
        ]
        module.d.sync += valid.eq(~flush & (
            (p["io_in_valid"] & ~duplicate) | (~fire & valid)))
        with cast(Any, module.If(p["io_in_valid"])):
            module.d.sync += next_req.eq(Cat(Const(0, 3), next_line))
        for i, (record, record_valid) in enumerate(zip(old_reqs, old_valid)):
            selected = fire & (old_index == i)
            with cast(Any, module.If(selected)):
                module.d.sync += record.eq(next_req)
            module.d.sync += record_valid.eq(~flush & (selected | record_valid))
        with cast(Any, module.If(fire)):
            module.d.sync += old_index.eq(old_index + 1)
        for output in ("io_out_valid", "io_out_bits_req_info_vpn", "io_out_bits_req_info_s2xlate"):
            expressions[output] = p[output]

    def _miss_queue(self, module: Module, expressions: dict[str, Any]) -> None:
        """Model the locked ``Queue(io.in, MissQueueSize)`` implementation.

        ``MissQueueSize`` is the sum of the instruction and data filter sizes
        (8 + 32) in the pinned V2 configuration.  The top level only exposes
        the request fields that are consumed by the queue; ``isHptwReq`` and
        ``hptwId`` are supplied by the surrounding L2 TLB arbiter and are
        constant false/zero for this miss queue input path.
        """

        p = self.ports
        flush = (
            p["io_sfence_valid"]
            | p["io_csr_satp_changed"]
            | p["io_csr_vsatp_changed"]
            | p["io_csr_hgatp_changed"]
            | p["io_csr_priv_virt_changed"]
        )

        queue = Queue40_L2TlbMQBundle()
        module.submodules.io_out_q = queue
        module.d.comb += [
            queue.clock.eq(p["clock"]), queue.reset.eq(p["reset"]),
            queue.io_flush.eq(flush), queue.io_enq_valid.eq(p["io_in_valid"]),
            queue.io_enq_bits_req_info_vpn.eq(p["io_in_bits_req_info_vpn"]),
            queue.io_enq_bits_req_info_s2xlate.eq(p["io_in_bits_req_info_s2xlate"]),
            queue.io_enq_bits_req_info_source.eq(p["io_in_bits_req_info_source"]),
            queue.io_enq_bits_isLLptw.eq(p["io_in_bits_isLLptw"]),
            queue.io_deq_ready.eq(p["io_out_ready"]),
            p["io_in_ready"].eq(queue.io_enq_ready),
            p["io_out_valid"].eq(queue.io_deq_valid),
            p["io_out_bits_req_info_vpn"].eq(queue.io_deq_bits_req_info_vpn),
            p["io_out_bits_req_info_s2xlate"].eq(queue.io_deq_bits_req_info_s2xlate),
            p["io_out_bits_req_info_source"].eq(queue.io_deq_bits_req_info_source),
            p["io_out_bits_isHptwReq"].eq(queue.io_deq_bits_isHptwReq),
            p["io_out_bits_isLLptw"].eq(queue.io_deq_bits_isLLptw),
            p["io_out_bits_hptwId"].eq(queue.io_deq_bits_hptwId),
        ]
        expressions.update({
            "io_in_ready": p["io_in_ready"],
            "io_out_valid": p["io_out_valid"],
            "io_out_bits_req_info_vpn": p["io_out_bits_req_info_vpn"],
            "io_out_bits_req_info_s2xlate": p["io_out_bits_req_info_s2xlate"],
            "io_out_bits_req_info_source": p["io_out_bits_req_info_source"],
            "io_out_bits_isHptwReq": p["io_out_bits_isHptwReq"],
            "io_out_bits_isLLptw": p["io_out_bits_isLLptw"],
            "io_out_bits_hptwId": p["io_out_bits_hptwId"],
        })

    def _monitor(self, module: Module, expressions: dict[str, Any]) -> None:
        """Track prefetch quality windows and independently timed recovery."""

        p = self.ports
        enable = Signal(init=1, name="enable")
        confidence = Signal(init=1, name="confidence")
        total = Signal(11, name="total_prefetch_cnt")
        late_hit = Signal(11, name="late_hit_prefetch_cnt")
        late_miss = Signal(11, name="late_miss_prefetch_cnt")
        good = Signal(11, name="good_prefetch_cnt")
        bad = Signal(11, name="bad_prefetch_cnt")
        back_off = Signal(18, name="back_off_cnt")
        low_conf = Signal(19, name="low_conf_cnt")
        timely_reset = (total == 1000) | (late_hit >= 1000)
        validity_reset = (good + bad)[:11] == 1000
        back_off_reset = back_off == 100000
        conf_reset = low_conf == 200000
        trigger_disable = validity_reset & (bad >= 900)
        trigger_late_miss = timely_reset & (late_miss >= 200)
        trigger_late_hit = timely_reset & (late_hit >= 900)
        disable = trigger_disable | (~trigger_late_miss & trigger_late_hit)
        module.d.comb += [p["io_pf_ctrl_enable"].eq(enable),
                          p["io_pf_ctrl_confidence"].eq(confidence)]
        module.d.sync += [
            enable.eq((back_off_reset | enable) & ~disable),
            confidence.eq((conf_reset | confidence) & ~disable),
            total.eq(Mux(timely_reset, 0, total + p["io_timely_total_prefetch"])),
            late_hit.eq(Mux(timely_reset, 0, late_hit + p["io_timely_late_hit_prefetch"])),
            late_miss.eq(Mux(timely_reset, 0, late_miss + p["io_timely_late_miss_prefetch"])),
            good.eq(Mux(validity_reset, 0, good + p["io_validity_good_prefetch"])),
            bad.eq(Mux(validity_reset, 0, bad + p["io_validity_bad_prefetch"])),
            back_off.eq(Mux(back_off_reset, 0, back_off + ~enable)),
            low_conf.eq(Mux(conf_reset, 0, low_conf + ~confidence)),
        ]
        expressions.update({"io_pf_ctrl_enable": p["io_pf_ctrl_enable"], "io_pf_ctrl_confidence": p["io_pf_ctrl_confidence"]})

    def _prefetch_pipe(self, module: Module, expressions: dict[str, Any]) -> None:
        """Translate and look up two instruction lines before issuing misses."""

        p = self.ports

        def reg(name: str, width: int = 1, resetless: bool = False) -> Signal:
            return Signal(width, name=name, reset_less=resetless)

        def wire(name: str, width: int, expression: Any) -> Signal:
            signal = Signal(width, name=name)
            module.d.comb += signal.eq(expression)
            return signal

        s1_valid = reg("s1_valid")
        s1_vaddr = [reg(f"s1_req_vaddr_{lane}", 50) for lane in range(2)]
        soft = reg("s1_isSoftPrefetch")
        double = reg("s1_doubleline")
        ftq_flag = reg("s1_req_ftqIdx_flag")
        ftq_value = reg("s1_req_ftqIdx_value", 6)
        backend = [reg(f"s1_backendException_{lane}", 2) for lane in range(2)]
        state = reg("state", 3)
        s1_ready, s1_fire, real_fire = reg("s1_ready"), reg("s1_fire"), reg("s1_real_fire")
        s2_ready, s2_fire = reg("s2_ready"), reg("s2_fire")
        flush_match = (p["io_flushFromBpu_s3_bits_flag"] ^ ftq_flag
                       ^ (p["io_flushFromBpu_s3_bits_value"] <= ftq_value))
        s1_flush = wire("s1_flush", 1, p["io_flush"] | (s1_valid & ~soft
                        & p["io_flushFromBpu_s3_valid"] & flush_match))
        s0_flush: Any = p["io_flush"] | s1_flush
        for stage in (2, 3):
            stem = f"io_flushFromBpu_s{stage}"
            match = (p[stem + "_bits_flag"] ^ p["io_req_bits_ftqIdx_flag"]
                     ^ (p[stem + "_bits_value"] <= p["io_req_bits_ftqIdx_value"]))
            s0_flush = s0_flush | (~p["io_req_bits_isSoftPrefetch"] & p[stem + "_valid"] & match)
        s0_can = wire("s0_can_go", 1, s1_ready & p["io_metaRead_toIMeta_ready"])
        s0_fire = wire("s0_fire", 1, p["io_req_valid"] & s0_can & ~s0_flush)
        delays = {name: reg(name, resetless=True) for name in (
            "s0_fire_r", "REG", "REG_1", "s1_need_itlb_REG", "s1_need_itlb_REG_1",
            "tlb_valid_pulse_REG", "tlb_valid_pulse_REG_1")}
        module.d.sync += [signal.eq(s0_fire) for signal in delays.values()]
        waits = [reg(f"s1_wait_itlb_{lane}") for lane in range(2)]
        latched = [reg("tlb_valid_latch_valid" + ("_1" if lane else "")) for lane in range(2)]
        pulses, needs = [], []
        paddrs, gpaddrs, nonleafs, exceptions, pbmts = [], [], [], [], []
        for lane in range(2):
            suffix = "_1" if lane else ""
            miss = p[f"io_itlb_{lane}_resp_bits_miss"]
            active = double if lane else Const(1, 1)
            pulse = wire(f"tlb_valid_pulse_{lane}", 1,
                         (delays["tlb_valid_pulse_REG" + suffix] | waits[lane]) & ~miss & active)
            need = wire(f"s1_need_itlb_{lane}", 1,
                        (delays["s1_need_itlb_REG" + suffix] | waits[lane]) & miss & active)
            pulses.append(pulse)
            needs.append(need)
            module.d.sync += [waits[lane].eq(~s1_flush & (
                delays["REG" + suffix] & miss | ~(waits[lane] & ~miss) & waits[lane])),
                latched[lane].eq(~(s1_flush | s1_fire) & (pulse | latched[lane]))]
            response = f"io_itlb_{lane}_resp_bits_"
            exception_now = wire(f"s1_itlb_exception_tmp_x9{suffix}", 2, Mux(
                p[response + "excp_0_pf_instr"], 1,
                Mux(p[response + "excp_0_gpf_instr"], 2,
                    Mux(p[response + "excp_0_af_instr"], 3, 0))))
            held_values = []
            for name, width, current in (
                ("s1_req_paddr_reg_r", 48, p[response + "paddr_0"]),
                ("s1_req_gpaddr_tmp_r", 56, p[response + "gpaddr_0"][:56]),
                ("s1_req_isForVSnonLeafPTE_tmp_r", 1, p[response + "isForVSnonLeafPTE"]),
                ("s1_itlb_exception_tmp_r", 2, exception_now),
                ("s1_itlb_pbmt_r", 2, p[response + "pbmt_0"]),
            ):
                held = reg(name + suffix, width)
                with cast(Any, module.If(pulse)):
                    module.d.sync += held.eq(current)
                held_values.append(wire(f"{name}_bypass_{lane}", width, Mux(pulse, current, held)))
            paddrs.append(held_values[0])
            gpaddrs.append(held_values[1])
            nonleafs.append(held_values[2])
            exceptions.append(wire(f"s1_itlb_exception_{lane}", 2,
                                   Mux(backend[lane].any(), backend[lane], held_values[3])))
            pbmts.append(held_values[4])
        itlb_finish = wire("itlb_finish", 1, (latched[0] | pulses[0])
                           & (~double | latched[1] | pulses[1]))
        need_meta = wire("s1_need_meta", 1, ((state == 1) & itlb_finish) | (state == 2))
        meta_delay = reg("s1_SRAM_valid_REG", resetless=True)
        module.d.sync += meta_delay.eq(need_meta & p["io_metaRead_toIMeta_ready"])
        sram_valid = wire("s1_SRAM_valid", 1, delays["s0_fire_r"] | meta_delay)
        new_masks, new_codes = [], []
        refill_valid = p["io_MSHRResp_valid"] & ~p["io_MSHRResp_bits_corrupt"]
        for lane in range(2):
            tag = paddrs[lane][12:48]
            hit_bits = [wire(f"sram_hit_{lane}_{way}", 1,
                        p[f"io_metaRead_fromIMeta_entryValid_{lane}_{way}"]
                        & (p[f"io_metaRead_fromIMeta_metas_{lane}_{way}_tag"] == tag))
                        for way in range(4)]
            sram_mask = wire(f"s1_SRAM_waymasks_{lane}", 4, Cat(*hit_bits))
            code_expr: Any = Const(0, 1)
            for way in range(4):
                code_expr = code_expr | (hit_bits[way] & p[f"io_metaRead_fromIMeta_codes_{lane}_{way}"])
            sram_code = wire(f"s1_SRAM_meta_codes_{lane}", 1, code_expr)
            held_mask = reg(f"s1_waymasks_r_{lane}", 4)
            held_code = reg(f"s1_meta_codes_r_{lane}")
            old_mask = wire(f"old_waymask_{lane}", 4, Mux(sram_valid, sram_mask, held_mask))
            match_set = wire(f"refill_set_{lane}", 1,
                             refill_valid & (p["io_MSHRResp_bits_vSetIdx"] == s1_vaddr[lane][6:14]))
            match_tag = wire(f"refill_tag_{lane}", 1, p["io_MSHRResp_bits_blkPaddr"][6:42] == tag)
            mask = wire(f"new_mask_{lane}", 4, Mux(match_set,
                        Mux(match_tag, p["io_MSHRResp_bits_waymask"],
                            Mux(p["io_MSHRResp_bits_waymask"] == old_mask, 0, old_mask)), old_mask))
            code = wire(f"new_code_{lane}", 1, Mux(match_set & match_tag, tag.xor(),
                                                   Mux(sram_valid, sram_code, held_code)))
            with cast(Any, module.If(sram_valid | refill_valid)):
                module.d.sync += [held_mask.eq(mask), held_code.eq(code)]
            new_masks.append(mask)
            new_codes.append(code)
        way_valid = wire("io_wayLookupWrite_valid_0", 1, ((state == 3) | ((state == 0) & itlb_finish))
                         & ~s1_flush & ~p["io_MSHRResp_valid"] & ~soft)
        way_fire = p["io_wayLookupWrite_ready"] & way_valid
        next_state = reg("next_state", 3)
        module.d.comb += next_state.eq(state)
        with cast(Any, module.If(s1_flush)):
            module.d.comb += next_state.eq(0)
        with cast(Any, module.Elif(state == 0)):
            with cast(Any, module.If(s1_valid)):
                module.d.comb += next_state.eq(Mux(~itlb_finish, 1,
                    Mux(~way_fire, 3, Mux(s2_ready, state, 4))))
        with cast(Any, module.Elif(state == 1)):
            with cast(Any, module.If(itlb_finish)):
                module.d.comb += next_state.eq(Mux(p["io_metaRead_toIMeta_ready"], 3, 2))
        with cast(Any, module.Elif(state == 2)):
            with cast(Any, module.If(p["io_metaRead_toIMeta_ready"])):
                module.d.comb += next_state.eq(3)
        with cast(Any, module.Elif(state == 3)):
            with cast(Any, module.If(way_fire | soft)):
                module.d.comb += next_state.eq(Mux(s2_ready, 0, 4))
        with cast(Any, module.Elif((state == 4) & s2_ready)):
            module.d.comb += next_state.eq(0)
        module.d.comb += [s1_ready.eq(next_state == 0), s1_fire.eq(s1_ready & s1_valid & ~s1_flush),
                          real_fire.eq(s1_fire & p["io_csr_pf_enable"])]
        module.d.sync += [state.eq(next_state), s1_valid.eq(~s1_flush & (s0_fire | ~s1_fire & s1_valid))]
        with cast(Any, module.If(s0_fire)):
            module.d.sync += [s1_vaddr[0].eq(p["io_req_bits_startAddr"]),
                              s1_vaddr[1].eq(p["io_req_bits_nextlineStart"]),
                              soft.eq(p["io_req_bits_isSoftPrefetch"]),
                              double.eq(p["io_req_bits_startAddr"][5]),
                              ftq_flag.eq(p["io_req_bits_ftqIdx_flag"]),
                              ftq_value.eq(p["io_req_bits_ftqIdx_value"]),
                              *(value.eq(p["io_req_bits_backendException"]) for value in backend)]
        s2_valid = reg("s2_valid")
        s2_vaddr = [reg(f"s2_req_vaddr_{lane}", 50) for lane in range(2)]
        s2_paddr = [reg(f"s2_req_paddr_{lane}", 48) for lane in range(2)]
        s2_exc = [reg(f"s2_itlb_exception_{lane}", 2) for lane in range(2)]
        s2_pbmt = [reg(f"s2_itlb_pbmt_{lane}", 2) for lane in range(2)]
        s2_masks = [reg(f"s2_waymasks_{lane}", 4) for lane in range(2)]
        s2_double = reg("s2_doubleline")
        pmp_delay = reg("s2_pmp_exception_REG", resetless=True)
        mmio_delay = reg("s2_pmp_mmio_REG", resetless=True)
        module.d.sync += [pmp_delay.eq(real_fire), mmio_delay.eq(real_fire),
                          s2_valid.eq(~p["io_flush"] & (real_fire | ~s2_fire & s2_valid))]
        with cast(Any, module.If(real_fire)):
            module.d.sync += [s2_double.eq(double)]
            for lane in range(2):
                module.d.sync += [s2_vaddr[lane].eq(s1_vaddr[lane]), s2_paddr[lane].eq(paddrs[lane]),
                                  s2_exc[lane].eq(exceptions[lane]), s2_pbmt[lane].eq(pbmts[lane]),
                                  s2_masks[lane].eq(new_masks[lane])]
        s2_exceptions, s2_mmios, s2_hits, sends = [], [], [], []
        for lane in range(2):
            pmp_hold = reg(f"s2_pmp_exception_r_{lane}", 2, resetless=True)
            mmio_hold = reg(f"s2_pmp_mmio_r_{lane}", resetless=True)
            pmp_now = Mux(p[f"io_pmp_{lane}_resp_instr"], 3, 0)
            with cast(Any, module.If(pmp_delay)):
                module.d.sync += pmp_hold.eq(pmp_now)
            with cast(Any, module.If(mmio_delay)):
                module.d.sync += mmio_hold.eq(p[f"io_pmp_{lane}_resp_mmio"])
            s2_exceptions.append(wire(f"s2_exception_{lane}", 2,
                Mux(s2_exc[lane].any(), s2_exc[lane], Mux(pmp_delay, pmp_now, pmp_hold))))
            s2_mmios.append(wire(f"s2_mmio_{lane}", 1,
                Mux(mmio_delay, p[f"io_pmp_{lane}_resp_mmio"], mmio_hold)
                | (s2_pbmt[lane] == 1) | (s2_pbmt[lane] == 2)))
            match = wire(f"s2_MSHR_match_{lane}", 1, refill_valid & s2_valid
                         & (s2_vaddr[lane][6:14] == p["io_MSHRResp_bits_vSetIdx"])
                         & (s2_paddr[lane][12:48] == p["io_MSHRResp_bits_blkPaddr"][6:42]))
            held_hit = reg("s2_MSHR_hits_valid" + ("_1" if lane else ""))
            module.d.sync += held_hit.eq(~(s2_fire | p["io_flush"]) & (match | held_hit))
            s2_hits.append(held_hit | match | s2_masks[lane].any())
            sends.append(reg(f"has_send_{lane}"))
        misses = [wire("s2_miss_0", 1, ~s2_hits[0] & (s2_exceptions[0] == 0) & ~s2_mmios[0]),
                  wire("s2_miss_1", 1, ~s2_hits[1] & s2_double & (s2_exceptions[0] == 0)
                       & (s2_exceptions[1] == 0) & ~s2_mmios[0] & ~s2_mmios[1])]
        finish = wire("s2_finish", 1, (sends[0] | ~misses[0]) & (sends[1] | ~misses[1]))
        module.d.comb += [s2_ready.eq(finish | ~s2_valid), s2_fire.eq(s2_valid & finish & ~p["io_flush"])]
        arbiter = PrefetchMissArbiter()
        module.submodules.toMSHRArbiter = arbiter
        module.d.comb += [arbiter.out_ready.eq(p["io_MSHRReq_ready"]),
                          p["io_MSHRReq_valid"].eq(arbiter.out_valid),
                          p["io_MSHRReq_bits_blkPaddr"].eq(arbiter.out_block),
                          p["io_MSHRReq_bits_vSetIdx"].eq(arbiter.out_vset)]
        for lane in range(2):
            module.d.comb += [arbiter.valid[lane].eq(s2_valid & misses[lane] & ~sends[lane]),
                              arbiter.block[lane].eq(s2_paddr[lane][6:48]),
                              arbiter.vset[lane].eq(s2_vaddr[lane][6:14])]
            module.d.sync += sends[lane].eq(~real_fire & (
                arbiter.ready[lane] & arbiter.valid[lane] | sends[lane]))
        module.d.comb += [p["io_req_ready"].eq(s0_can), p["io_itlbFlushPipe"].eq(s1_flush),
                          p["io_metaRead_toIMeta_valid"].eq(need_meta | p["io_req_valid"]),
                          p["io_metaRead_toIMeta_bits_isDoubleLine"].eq(
                              Mux(need_meta, double, p["io_req_bits_startAddr"][5])),
                          p["io_wayLookupWrite_valid"].eq(way_valid)]
        for lane in range(2):
            incoming_addr = p["io_req_bits_nextlineStart" if lane else "io_req_bits_startAddr"]
            module.d.comb += [p[f"io_itlb_{lane}_req_valid"].eq(needs[lane]
                                  | (p["io_req_valid"] & (p["io_req_bits_startAddr"][5] if lane else Const(1)))),
                              p[f"io_itlb_{lane}_req_bits_vaddr"].eq(Mux(needs[lane], s1_vaddr[lane], incoming_addr)),
                              p[f"io_pmp_{lane}_req_valid"].eq(s1_valid),
                              p[f"io_pmp_{lane}_req_bits_addr"].eq(paddrs[lane]),
                              p[f"io_metaRead_toIMeta_bits_vSetIdx_{lane}"].eq(
                                  Mux(need_meta, s1_vaddr[lane][6:14], incoming_addr[6:14]))]
            stem = "io_wayLookupWrite_bits_entry_"
            module.d.comb += [p[f"{stem}vSetIdx_{lane}"].eq(s1_vaddr[lane][6:14]),
                              p[f"{stem}waymask_{lane}"].eq(new_masks[lane]),
                              p[f"{stem}ptag_{lane}"].eq(paddrs[lane][12:48]),
                              p[f"{stem}itlb_exception_{lane}"].eq(
                                  Mux(double, exceptions[lane], 0) if lane else exceptions[lane]),
                              p[f"{stem}itlb_pbmt_{lane}"].eq(Mux(double, pbmts[lane], 0) if lane else pbmts[lane]),
                              p[f"{stem}meta_codes_{lane}"].eq(new_codes[lane])]
        fault_0, fault_1 = exceptions[0] == 2, exceptions[1] == 2
        module.d.comb += [p["io_wayLookupWrite_bits_gpf_gpaddr"].eq(
            Mux(fault_0, gpaddrs[0], Mux(fault_1, gpaddrs[1] - 64, 0))),
            p["io_wayLookupWrite_bits_gpf_isForVSnonLeafPTE"].eq(
                Mux(fault_0, nonleafs[0], fault_1 & nonleafs[1]))]
        for name, direction, _width in self.specs:
            if direction == "output":
                expressions[name] = p[name]

    def _main_pipe(self, module: Module, expressions: dict[str, Any]) -> None:
        """Fetch banked instruction data and wait for missing-line refills."""

        p = self.ports

        def reg(name: str, width: int = 1, resetless: bool = False) -> Signal:
            return Signal(width, name=name, reset_less=resetless)

        def wire(name: str, width: int, expression: Any) -> Signal:
            signal = Signal(width, name=name)
            module.d.comb += signal.eq(expression)
            return signal

        s1_valid, s2_valid = reg("s1_valid"), reg("s2_valid")
        s1_ready, s1_fire = reg("s1_ready"), reg("s1_fire")
        s2_ready, s2_fire = reg("s2_ready"), reg("s2_fire")
        s0_can = wire("s0_can_go", 1, p["io_dataArray_toIData_3_ready"] & p["io_wayLookupRead_valid"] & s1_ready)
        s0_fire = wire("s0_fire", 1, p["io_fetch_req_valid"] & s0_can & ~p["io_flush"])
        stages = []
        masks = []
        for stage in (1, 2):
            values = {field: reg(f"s{stage}_{field}", width) for field, width in (
                ("req_gpaddr", 56), ("req_isForVSnonLeafPTE", 1), ("doubleline", 1),
                ("backendException", 1), ("hasSatpFlush", 1))}
            for lane in range(2):
                for field, width in (("req_vaddr", 50), ("req_ptags", 36),
                                      ("itlb_exception", 2), ("itlb_pbmt", 2), ("SRAMhits", 1)):
                    values[f"{field}_{lane}"] = reg(f"s{stage}_{field}_{lane}", width)
            bits = [[reg(f"s{stage}_waymasks_{lane}_{way}") for way in range(4)] for lane in range(2)]
            masks.append(bits)
            stages.append(values)
        s1, s2 = stages
        s1_paddr = [wire(f"s1_req_paddr_{lane}", 48, Cat(s1[f"req_vaddr_{lane}"][:12], s1[f"req_ptags_{lane}"]))
                    for lane in range(2)]
        s2_paddr = [wire(f"s2_req_paddr_{lane}", 48, Cat(s2[f"req_vaddr_{lane}"][:12], s2[f"req_ptags_{lane}"]))
                    for lane in range(2)]
        meta_codes = [reg(f"s1_meta_codes_{lane}") for lane in range(2)]
        with cast(Any, module.If(s0_fire)):
            module.d.sync += [s1["req_gpaddr"].eq(p["io_wayLookupRead_bits_gpf_gpaddr"]),
                              s1["req_isForVSnonLeafPTE"].eq(p["io_wayLookupRead_bits_gpf_isForVSnonLeafPTE"]),
                              s1["doubleline"].eq(p["io_fetch_req_bits_readValid_4"] & p["io_fetch_req_bits_pcMemRead_4_startAddr"][5]),
                              s1["backendException"].eq(p["io_fetch_req_bits_backendException"]),
                              s1["hasSatpFlush"].eq(p["io_fetch_req_bits_hasSatpFlush"])]
            for lane in range(2):
                module.d.sync += [s1[f"req_vaddr_{lane}"].eq(p["io_fetch_req_bits_pcMemRead_4_nextlineStart" if lane else "io_fetch_req_bits_pcMemRead_4_startAddr"]),
                                  s1[f"req_ptags_{lane}"].eq(p[f"io_wayLookupRead_bits_entry_ptag_{lane}"]),
                                  s1[f"SRAMhits_{lane}"].eq(p[f"io_wayLookupRead_bits_entry_waymask_{lane}"].any()),
                                  s1[f"itlb_exception_{lane}"].eq(p[f"io_wayLookupRead_bits_entry_itlb_exception_{lane}"]),
                                  s1[f"itlb_pbmt_{lane}"].eq(p[f"io_wayLookupRead_bits_entry_itlb_pbmt_{lane}"]),
                                  meta_codes[lane].eq(p[f"io_wayLookupRead_bits_entry_meta_codes_{lane}"]),
                                  *(bit.eq(p[f"io_wayLookupRead_bits_entry_waymask_{lane}"][way])
                                    for way, bit in enumerate(masks[0][lane]))]
        s1_matches, s2_matches = [], []
        for lane in range(2):
            for values, valid, stage, collection in ((s1, s1_valid, 1, s1_matches), (s2, s2_valid, 2, s2_matches)):
                match = (valid & p["io_mshr_resp_valid"]
                         & (values[f"req_vaddr_{lane}"][6:14] == p["io_mshr_resp_bits_vSetIdx"])
                         & (values[f"req_ptags_{lane}"] == p["io_mshr_resp_bits_blkPaddr"][6:42]))
                if stage == 1:
                    match = match & ~p["io_mshr_resp_bits_corrupt"]
                if lane:
                    match = match & values["doubleline"]
                collection.append(wire(f"s{stage}_MSHR_match_{lane}", 1, match))
        s1_hits, s2_hits = [], []
        for lane in range(2):
            suffix = "_1" if lane else ""
            delayed = reg("s1_hits_REG" + suffix, resetless=True)
            held = reg("s1_hits_valid" + suffix)
            module.d.sync += [delayed.eq(s0_fire), held.eq(~(s1_fire | p["io_flush"]) & (
                s1_matches[lane] | delayed & s1[f"SRAMhits_{lane}"] | held))]
            s1_hits.append(wire(f"s1_hits_{lane}", 1,
                               held | s1_matches[lane] | delayed & s1[f"SRAMhits_{lane}"]))
            hit = reg(f"s2_hits_{lane}")
            with cast(Any, module.If(s1_fire)):
                module.d.sync += hit.eq(s1_hits[lane])
            with cast(Any, module.Else()):
                module.d.sync += hit.eq(s2_matches[lane] | hit)
            s2_hits.append(hit)
        s2_data, s2_from_mshr, s2_codes = [], [], []
        code_delay = reg("s1_codes_REG", resetless=True)
        module.d.sync += code_delay.eq(s0_fire)
        for bank in range(8):
            suffix = f"_{bank}" if bank else ""
            bank_hit_1 = wire(f"s1_bankMSHRHit_{bank}", 1,
                Mux(s1["req_vaddr_0"][3:6] <= bank, s1_matches[0], s1_matches[1]))
            bank_hit_2 = wire(f"s2_bankMSHRHit_{bank}", 1,
                Mux(s2["req_vaddr_0"][3:6] <= bank, s2_matches[0], s2_matches[1]))
            data_delay = reg("s1_datas_REG" + suffix, resetless=True)
            data_hold = reg("s1_datas_r" + suffix, 64, resetless=True)
            data_now = wire(f"s1_bank_data_{bank}", 64, Mux(bank_hit_1,
                            p["io_mshr_resp_bits_data"][64 * bank:64 * (bank + 1)], p[f"io_dataArray_fromIData_datas_{bank}"]))
            data_valid = bank_hit_1 | data_delay
            module.d.sync += data_delay.eq(s0_fire)
            with cast(Any, module.If(data_valid)):
                module.d.sync += data_hold.eq(data_now)
            from_delay = reg("s1_data_is_from_MSHR_REG" + suffix, resetless=True)
            from_hold = reg("s1_data_is_from_MSHR_r" + suffix, resetless=True)
            module.d.sync += from_delay.eq(s0_fire)
            with cast(Any, module.If(bank_hit_1 | from_delay)):
                module.d.sync += from_hold.eq(bank_hit_1)
            code_hold = reg(f"s1_codes_r_{bank}", resetless=True)
            with cast(Any, module.If(code_delay)):
                module.d.sync += code_hold.eq(p[f"io_dataArray_fromIData_codes_{bank}"])
            data = reg(f"s2_datas_{bank}", 64)
            origin = reg(f"s2_data_is_from_MSHR_{bank}")
            code = reg(f"s2_codes_{bank}")
            with cast(Any, module.If(s1_fire)):
                module.d.sync += [data.eq(Mux(data_valid, data_now, data_hold)),
                                  origin.eq(Mux(bank_hit_1 | from_delay, bank_hit_1, from_hold)),
                                  code.eq(Mux(code_delay, p[f"io_dataArray_fromIData_codes_{bank}"], code_hold))]
            with cast(Any, module.Else()):
                module.d.sync += origin.eq(bank_hit_2 | origin)
                with cast(Any, module.If(bank_hit_2)):
                    module.d.sync += data.eq(p["io_mshr_resp_bits_data"][64 * bank:64 * (bank + 1)])
            s2_data.append(data)
            s2_from_mshr.append(origin)
            s2_codes.append(code)
        with cast(Any, module.If(s1_fire)):
            module.d.sync += [value.eq(s1[key]) for key, value in s2.items()]
            for lane in range(2):
                module.d.sync += [bit.eq(previous) for bit, previous in zip(masks[1][lane], masks[0][lane])]
        pmp_delay = reg("s2_pmp_exception_REG", resetless=True)
        mmio_delay = reg("s2_pmp_mmio_REG", resetless=True)
        module.d.sync += [pmp_delay.eq(s1_fire), mmio_delay.eq(s1_fire)]
        exceptions, pmp_mmio, mmio, meta_bad, corrupt, l2_bad, sent = [], [], [], [], [], [], []
        for lane in range(2):
            pmp_hold = reg(f"s2_pmp_exception_r_{lane}", 2, resetless=True)
            mmio_hold = reg(f"s2_pmp_mmio_r_{lane}", resetless=True)
            pmp_now = Mux(p[f"io_pmp_{lane}_resp_instr"], 3, 0)
            with cast(Any, module.If(pmp_delay)):
                module.d.sync += pmp_hold.eq(pmp_now)
            with cast(Any, module.If(mmio_delay)):
                module.d.sync += mmio_hold.eq(p[f"io_pmp_{lane}_resp_mmio"])
            exceptions.append(wire(f"s2_exception_{lane}", 2, Mux(s2[f"itlb_exception_{lane}"].any(),
                s2[f"itlb_exception_{lane}"], Mux(pmp_delay, pmp_now, pmp_hold))))
            pmp_mmio.append(wire(f"s2_pmp_mmio_{lane}", 1, Mux(mmio_delay, p[f"io_pmp_{lane}_resp_mmio"], mmio_hold)))
            mmio.append(wire(f"s2_mmio_{lane}", 1, pmp_mmio[lane] | (s2[f"itlb_pbmt_{lane}"] == 1) | (s2[f"itlb_pbmt_{lane}"] == 2)))
            meta = reg(f"s2_meta_corrupt_{lane}")
            hit_count: Any = sum(masks[0][lane], Const(0, 3))
            meta_now = p["io_ecc_enable"] & (
                ((s1[f"req_ptags_{lane}"].xor() != meta_codes[lane]) & (hit_count == 1)) | (hit_count >= 2))
            if lane:
                meta_now = meta_now & s1["doubleline"]
            with cast(Any, module.If(s1_fire)):
                module.d.sync += meta.eq(meta_now)
            with cast(Any, module.Else()):
                module.d.sync += meta.eq(~s2_matches[lane] & meta)
            meta_bad.append(meta)
            low = s2["req_vaddr_0"][3:6]
            high = wire(f"bank_high_{lane}", 4,
                        (cast(Value, Cat(s2["req_vaddr_0"][:6], Const(0, 1))) + 32)[3:7])
            bad_data: Any = Const(0, 1)
            for bank in range(8):
                number = 8 * lane + bank
                selected = (low <= number) & (high >= number)
                bad_data = bad_data | ((s2_data[bank].xor() != s2_codes[bank]) & selected & ~s2_from_mshr[bank])
            corrupt.append(wire(f"s2_corrupt_refetch_{lane}", 1,
                meta | (p["io_ecc_enable"] & bad_data & s2[f"SRAMhits_{lane}"])))
            l2 = reg(f"s2_l2_corrupt_{lane}")
            module.d.sync += l2.eq(~s1_fire & Mux(s2_matches[lane], p["io_mshr_resp_bits_corrupt"], l2))
            l2_bad.append(l2)
            sent.append(reg(f"s2_has_send_{lane}"))
        should = [wire("s2_should_fetch_0", 1, (~s2_hits[0] | corrupt[0]) & (exceptions[0] == 0) & ~mmio[0]),
                  wire("s2_should_fetch_1", 1, (~s2_hits[1] | corrupt[1]) & s2["doubleline"]
                       & (exceptions[0] == 0) & (exceptions[1] == 0) & ~mmio[0] & ~mmio[1])]
        pending = wire("pending_misses", 1, should[0] | should[1])
        module.d.comb += [s2_ready.eq((~pending & ~p["io_respStall"]) | ~s2_valid),
                          s2_fire.eq(s2_valid & ~pending & ~p["io_respStall"] & ~p["io_flush"]),
                          s1_ready.eq(s2_ready | ~s1_valid), s1_fire.eq(s1_valid & s2_ready & ~p["io_flush"])]
        module.d.sync += [s1_valid.eq(~p["io_flush"] & (s0_fire | ~s1_fire & s1_valid)),
                          s2_valid.eq(~p["io_flush"] & (s1_fire | ~s2_fire & s2_valid))]
        arbiter = PrefetchMissArbiter()
        module.submodules.toMSHRArbiter = arbiter
        module.d.comb += [arbiter.out_ready.eq(p["io_mshr_req_ready"]), p["io_mshr_req_valid"].eq(arbiter.out_valid),
                          p["io_mshr_req_bits_blkPaddr"].eq(arbiter.out_block), p["io_mshr_req_bits_vSetIdx"].eq(arbiter.out_vset)]
        for lane in range(2):
            module.d.comb += [arbiter.valid[lane].eq(s2_valid & should[lane] & ~sent[lane] & ~p["io_flush"]),
                              arbiter.block[lane].eq(Cat(s2[f"req_vaddr_{lane}"][6:12], s2[f"req_ptags_{lane}"])),
                              arbiter.vset[lane].eq(s2[f"req_vaddr_{lane}"][6:14])]
            module.d.sync += sent[lane].eq(~s1_fire & (arbiter.ready[lane] & arbiter.valid[lane] | sent[lane]))
            touch = reg(f"io_touch_{lane}_valid_REG", resetless=True)
            module.d.sync += touch.eq(s0_fire)
            module.d.comb += [p[f"io_touch_{lane}_valid"].eq(touch & s1[f"SRAMhits_{lane}"] & (s1["doubleline"] if lane else Const(1))),
                              p[f"io_touch_{lane}_bits_vSetIdx"].eq(s1[f"req_vaddr_{lane}"][6:14]),
                              p[f"io_touch_{lane}_bits_way"].eq(Cat(masks[0][lane][3] | masks[0][lane][1],
                                                                                    masks[0][lane][3] | masks[0][lane][2])),
                              p[f"io_pmp_{lane}_req_valid"].eq(s1_valid), p[f"io_pmp_{lane}_req_bits_addr"].eq(s1_paddr[lane])]
            error_delay = reg(f"io_errors_{lane}_valid_REG", resetless=True)
            report_delay = reg(f"io_errors_{lane}_bits_report_to_beu_REG", resetless=True)
            flush_delay = reg(f"io_metaArrayFlush_{lane}_valid_REG", resetless=True)
            l2_delay = reg(f"REG_{4 + lane}", resetless=True)
            error_addr = reg(f"io_errors_{lane}_bits_paddr_REG", 48, resetless=True)
            module.d.sync += [error_delay.eq(s1_fire), report_delay.eq(s1_fire), flush_delay.eq(s1_fire),
                              l2_delay.eq(s2_fire & l2_bad[lane]), error_addr.eq(s2_paddr[lane])]
            module.d.comb += [p[f"io_errors_{lane}_valid"].eq(l2_delay | corrupt[lane] & error_delay),
                              p[f"io_errors_{lane}_bits_paddr"].eq(Mux(l2_delay, error_addr, s2_paddr[lane])),
                              p[f"io_errors_{lane}_bits_report_to_beu"].eq(~l2_delay & corrupt[lane] & report_delay),
                              p[f"io_metaArrayFlush_{lane}_valid"].eq(corrupt[lane] & flush_delay),
                              p[f"io_metaArrayFlush_{lane}_bits_virIdx"].eq(s2[f"req_vaddr_{lane}"][6:14]),
                              p[f"io_metaArrayFlush_{lane}_bits_waymask"].eq(Mux(meta_bad[lane], 15, Cat(*masks[1][lane])))]
        for index in range(4):
            module.d.comb += [p[f"io_dataArray_toIData_{index}_valid"].eq(p[f"io_fetch_req_bits_readValid_{index}"]),
                              p[f"io_dataArray_toIData_{index}_bits_vSetIdx_0"].eq(p[f"io_fetch_req_bits_pcMemRead_{index}_startAddr"][6:14]),
                              p[f"io_dataArray_toIData_{index}_bits_vSetIdx_1"].eq(p[f"io_fetch_req_bits_pcMemRead_{index}_nextlineStart"][6:14])]
        for lane in range(2):
            for way in range(4):
                module.d.comb += p[f"io_dataArray_toIData_0_bits_waymask_{lane}_{way}"].eq(p[f"io_wayLookupRead_bits_entry_waymask_{lane}"][way])
            visible = s2["doubleline"] if lane else Const(1)
            module.d.comb += [p[f"io_fetch_resp_bits_vaddr_{lane}"].eq(s2[f"req_vaddr_{lane}"]),
                              p[f"io_fetch_resp_bits_exception_{lane}"].eq(Mux(visible,
                                  Mux(exceptions[lane].any(), exceptions[lane], Mux(l2_bad[lane], 3, 0)), 0)),
                              p[f"io_fetch_resp_bits_pmp_mmio_{lane}"].eq(visible & pmp_mmio[lane]),
                              p[f"io_fetch_resp_bits_itlb_pbmt_{lane}"].eq(Mux(visible, s2[f"itlb_pbmt_{lane}"], 0))]
        module.d.comb += [p["io_dataArray_toIData_0_bits_blkOffset"].eq(p["io_fetch_req_bits_pcMemRead_0_startAddr"][:6]),
                          p["io_wayLookupRead_ready"].eq(s0_fire), p["io_fetch_req_ready"].eq(s0_can),
                          p["io_fetch_resp_valid"].eq(s2_fire), p["io_fetch_resp_bits_data"].eq(Cat(*s2_data)),
                          p["io_fetch_resp_bits_paddr_0"].eq(s2_paddr[0]),
                          p["io_fetch_resp_bits_gpaddr"].eq(s2["req_gpaddr"]),
                          p["io_fetch_resp_bits_isForVSnonLeafPTE"].eq(s2["req_isForVSnonLeafPTE"]),
                          p["io_fetch_resp_bits_backendException"].eq(s2["backendException"]),
                          p["io_fetch_resp_bits_hasSatpFlush"].eq(s2["hasSatpFlush"]),
                          p["io_fetch_resp_bits_doubleline"].eq(s2["doubleline"]),
                          p["io_fetch_topdownIcacheMiss"].eq(s2_valid & pending)]
        perf = {"only_0_hit": s2_hits[0] & ~s2["doubleline"], "only_0_miss": ~s2_hits[0] & ~s2["doubleline"],
                "hit_0_hit_1": s2_hits[0] & s2_hits[1] & s2["doubleline"],
                "hit_0_miss_1": s2_hits[0] & ~s2_hits[1] & s2["doubleline"],
                "miss_0_hit_1": ~s2_hits[0] & s2_hits[1] & s2["doubleline"],
                "miss_0_miss_1": ~s2_hits[0] & ~s2_hits[1] & s2["doubleline"],
                "bank_hit_1": s2_hits[1] & s2["doubleline"],
                "hit": s2_hits[0] & (~s2["doubleline"] | s2_hits[1])}
        module.d.comb += [p[f"io_perfInfo_{name}"].eq(value) for name, value in perf.items()]
        for name, direction, _width in self.specs:
            if direction == "output":
                expressions[name] = p[name]

    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        self._domain(module)
        expressions: dict[str, Any] = {}
        if self.member == "InstrMMIOEntry":
            self._instr_mmio(module, expressions)
        elif self.member == "WayLookup":
            self._way_lookup(module, expressions)
        elif self.member == "L2TlbPrefetch":
            self._tlb_prefetch(module, expressions)
        elif self.member == "L2TlbMissQueue":
            self._miss_queue(module, expressions)
        elif self.member == "PrefetcherMonitor":
            self._monitor(module, expressions)
        elif self.member == "IPrefetchPipe":
            self._prefetch_pipe(module, expressions)
        elif self.member == "ICacheMainPipe":
            self._main_pipe(module, expressions)
        self._defaults(expressions)
        # Helpers above install direct assignments for stateful/compound
        # outputs and retain the corresponding signal in ``expressions`` for
        # bookkeeping.  Do not emit ``signal.eq(signal)`` here: Amaranth
        # correctly diagnoses that as a combinational cycle.
        module.d.comb += [
            self.ports[name].eq(value)
            for name, value in expressions.items()
            if value is not self.ports[name]
        ]
        return module


# Public Adapter / 公开适配器
def build_verilog(configuration: Any, injected_dependencies: Any) -> str:
    """Emit deterministic Verilog for one exact locked member."""

    del injected_dependencies
    member = "ICacheMainPipe"
    if isinstance(configuration, dict):
        member = str(configuration.get("module", member))
    elif isinstance(configuration, str):
        member = configuration
    top = IcachePrefetchFamily(member)
    return verilog.convert(top, name=member, ports=[top.ports[name] for name, _direction, _width_value in top.specs], emit_src=False)


# Direct Entry / 直接入口
def main() -> None:
    print(build_verilog({"module": COVERED_MODULES[0]}, {}))


if __name__ == "__main__":
    main()
