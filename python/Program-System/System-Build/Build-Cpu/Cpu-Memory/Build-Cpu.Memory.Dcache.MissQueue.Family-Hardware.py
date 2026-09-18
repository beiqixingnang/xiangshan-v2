# pyright: reportGeneralTypeIssues=false

"""UHSC V2 DCache miss, probe, and writeback queue family.

This aggregate owns the exact locked ANSI surfaces for the DCache miss-queue
and adjacent queue leaves.  The catalog is mechanically frozen from
``validation/v2-locked-hierarchy.json`` by
``scripts/generate_dcache_miss_family_port_catalog.py``.  The implementation
keeps bounded, reset-safe request, response, and arbitration behavior useful
to direct tests; full TileLink/coherence and parent DCache closure remain
explicitly outside this leaf-family claim.
"""

from __future__ import annotations

from typing import Any

from amaranth import ClockDomain, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
__all__ = [
    "COVERED_MODULES",
    "SOURCE_PATHS",
    "LOCKED_PORT_SPECS",
    "PORT_SPECS",
    "DcacheMissQueueFamily",
    "build_verilog",
    "main",
]

COVERED_MODULES = (
    "CMOUnit",
    "MissEntry",
    "MissReadyGen",
    "ProbeEntry",
    "TreeArbiter",
    "WritebackEntry",
    "WritebackEntry_15",
)

SOURCE_PATHS = (
    "upstream/src/main/scala/xiangshan/cache/dcache/mainpipe/MissQueue.scala",
    "upstream/src/main/scala/xiangshan/cache/dcache/mainpipe/Probe.scala",
    "upstream/src/main/scala/xiangshan/cache/dcache/mainpipe/WritebackQueue.scala",
    "upstream/src/main/scala/xiangshan/cache/dcache/DCacheWrapper.scala",
)


# BEGIN LOCKED PORT CATALOG
# Generated from validation/v2-locked-hierarchy.json; do not hand-edit.
LOCKED_PORT_SPECS: dict[str, tuple[tuple[str, str, int], ...]] = {
    "CMOUnit": (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_req_ready', 'output', 1),
        ('io_req_valid', 'input', 1),
        ('io_req_bits_opcode', 'input', 3),
        ('io_req_bits_address', 'input', 64),
        ('io_req_chanA_ready', 'input', 1),
        ('io_req_chanA_valid', 'output', 1),
        ('io_req_chanA_bits_opcode', 'output', 4),
        ('io_req_chanA_bits_address', 'output', 48),
        ('io_resp_chanD_ready', 'output', 1),
        ('io_resp_chanD_valid', 'input', 1),
        ('io_resp_chanD_bits_denied', 'input', 1),
        ('io_resp_chanD_bits_corrupt', 'input', 1),
        ('io_resp_to_lsq_ready', 'input', 1),
        ('io_resp_to_lsq_valid', 'output', 1),
        ('io_resp_to_lsq_bits_denied', 'output', 1),
        ('io_resp_to_lsq_bits_corrupt', 'output', 1),
        ('io_wfi_wfiReq', 'input', 1),
        ('io_wfi_wfiSafe', 'output', 1),
    ),
    "MissEntry": (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_id', 'input', 4),
        ('io_req_valid', 'input', 1),
        ('io_req_bits_source', 'input', 4),
        ('io_req_bits_addr', 'input', 48),
        ('io_req_bits_vaddr', 'input', 50),
        ('io_req_bits_cancel', 'input', 1),
        ('io_wbq_block_miss_req', 'input', 1),
        ('io_miss_req_pipe_reg_req_source', 'input', 4),
        ('io_miss_req_pipe_reg_req_pf_source', 'input', 3),
        ('io_miss_req_pipe_reg_req_cmd', 'input', 5),
        ('io_miss_req_pipe_reg_req_addr', 'input', 48),
        ('io_miss_req_pipe_reg_req_vaddr', 'input', 50),
        ('io_miss_req_pipe_reg_req_full_overwrite', 'input', 1),
        ('io_miss_req_pipe_reg_req_word_idx', 'input', 3),
        ('io_miss_req_pipe_reg_req_amo_data', 'input', 128),
        ('io_miss_req_pipe_reg_req_amo_mask', 'input', 16),
        ('io_miss_req_pipe_reg_req_amo_cmp', 'input', 128),
        ('io_miss_req_pipe_reg_req_req_coh_state', 'input', 2),
        ('io_miss_req_pipe_reg_req_id', 'input', 6),
        ('io_miss_req_pipe_reg_req_isBtoT', 'input', 1),
        ('io_miss_req_pipe_reg_req_occupy_way', 'input', 4),
        ('io_miss_req_pipe_reg_req_store_data', 'input', 512),
        ('io_miss_req_pipe_reg_req_store_mask', 'input', 64),
        ('io_miss_req_pipe_reg_merge', 'input', 1),
        ('io_miss_req_pipe_reg_alloc', 'input', 1),
        ('io_miss_req_pipe_reg_cancel', 'input', 1),
        ('io_primary_valid', 'input', 1),
        ('io_primary_ready', 'output', 1),
        ('io_secondary_ready', 'output', 1),
        ('io_secondary_reject', 'output', 1),
        ('io_mem_acquire_ready', 'input', 1),
        ('io_mem_acquire_valid', 'output', 1),
        ('io_mem_acquire_bits_opcode', 'output', 4),
        ('io_mem_acquire_bits_param', 'output', 3),
        ('io_mem_acquire_bits_source', 'output', 6),
        ('io_mem_acquire_bits_address', 'output', 48),
        ('io_mem_acquire_bits_user_alias', 'output', 2),
        ('io_mem_acquire_bits_user_vaddr', 'output', 44),
        ('io_mem_acquire_bits_user_reqSource', 'output', 5),
        ('io_mem_acquire_bits_user_needHint', 'output', 1),
        ('io_mem_acquire_bits_echo_isKeyword', 'output', 1),
        ('io_mem_grant_valid', 'input', 1),
        ('io_mem_grant_bits_opcode', 'input', 4),
        ('io_mem_grant_bits_param', 'input', 2),
        ('io_mem_grant_bits_size', 'input', 3),
        ('io_mem_grant_bits_sink', 'input', 10),
        ('io_mem_grant_bits_denied', 'input', 1),
        ('io_mem_grant_bits_data', 'input', 256),
        ('io_mem_grant_bits_corrupt', 'input', 1),
        ('io_mem_finish_ready', 'input', 1),
        ('io_mem_finish_valid', 'output', 1),
        ('io_mem_finish_bits_sink', 'output', 10),
        ('io_queryME_0_req_bits_source', 'input', 4),
        ('io_queryME_0_req_bits_addr', 'input', 48),
        ('io_queryME_0_req_bits_vaddr', 'input', 50),
        ('io_queryME_0_primary_ready', 'output', 1),
        ('io_queryME_0_secondary_ready', 'output', 1),
        ('io_queryME_0_secondary_reject', 'output', 1),
        ('io_queryME_1_req_bits_source', 'input', 4),
        ('io_queryME_1_req_bits_addr', 'input', 48),
        ('io_queryME_1_req_bits_vaddr', 'input', 50),
        ('io_queryME_1_primary_ready', 'output', 1),
        ('io_queryME_1_secondary_ready', 'output', 1),
        ('io_queryME_1_secondary_reject', 'output', 1),
        ('io_queryME_2_req_bits_source', 'input', 4),
        ('io_queryME_2_req_bits_addr', 'input', 48),
        ('io_queryME_2_req_bits_vaddr', 'input', 50),
        ('io_queryME_2_primary_ready', 'output', 1),
        ('io_queryME_2_secondary_ready', 'output', 1),
        ('io_queryME_2_secondary_reject', 'output', 1),
        ('io_queryME_3_req_bits_source', 'input', 4),
        ('io_queryME_3_req_bits_addr', 'input', 48),
        ('io_queryME_3_req_bits_vaddr', 'input', 50),
        ('io_queryME_3_primary_ready', 'output', 1),
        ('io_queryME_3_secondary_ready', 'output', 1),
        ('io_queryME_3_secondary_reject', 'output', 1),
        ('io_l2_hint_valid', 'input', 1),
        ('io_main_pipe_req_ready', 'input', 1),
        ('io_main_pipe_req_valid', 'output', 1),
        ('io_main_pipe_req_bits_miss_id', 'output', 4),
        ('io_main_pipe_req_bits_occupy_way', 'output', 4),
        ('io_main_pipe_req_bits_miss_fail_cause_evict_btot', 'output', 1),
        ('io_main_pipe_req_bits_source', 'output', 4),
        ('io_main_pipe_req_bits_cmd', 'output', 5),
        ('io_main_pipe_req_bits_vaddr', 'output', 50),
        ('io_main_pipe_req_bits_addr', 'output', 48),
        ('io_main_pipe_req_bits_word_idx', 'output', 3),
        ('io_main_pipe_req_bits_amo_data', 'output', 128),
        ('io_main_pipe_req_bits_amo_mask', 'output', 16),
        ('io_main_pipe_req_bits_amo_cmp', 'output', 128),
        ('io_main_pipe_req_bits_pf_source', 'output', 3),
        ('io_main_pipe_req_bits_access', 'output', 1),
        ('io_main_pipe_req_bits_id', 'output', 6),
        ('io_main_pipe_resp', 'input', 1),
        ('io_main_pipe_refill_resp', 'input', 1),
        ('io_main_pipe_replay', 'input', 1),
        ('io_main_pipe_evict_BtoT_way', 'input', 1),
        ('io_main_pipe_next_evict_way', 'input', 4),
        ('io_refill_info_valid', 'output', 1),
        ('io_refill_info_bits_store_data', 'output', 512),
        ('io_refill_info_bits_miss_param', 'output', 2),
        ('io_refill_info_bits_error_tl_denied', 'output', 1),
        ('io_refill_info_bits_error_tl_corrupt', 'output', 1),
        ('io_occupy_way', 'output', 4),
        ('io_probe_req_bits_addr', 'input', 48),
        ('io_probe_req_bits_vaddr', 'input', 50),
        ('io_probe_block', 'output', 1),
        ('io_replace_req_bits_addr', 'input', 48),
        ('io_replace_req_bits_vaddr', 'input', 50),
        ('io_replace_block', 'output', 1),
        ('io_req_vaddr_valid', 'output', 1),
        ('io_req_vaddr_bits', 'output', 50),
        ('io_req_isBtoT', 'output', 1),
        ('io_req_handled_by_this_entry', 'output', 1),
        ('io_forwardInfo_inflight', 'output', 1),
        ('io_forwardInfo_paddr', 'output', 48),
        ('io_forwardInfo_raw_data_0', 'output', 64),
        ('io_forwardInfo_raw_data_1', 'output', 64),
        ('io_forwardInfo_raw_data_2', 'output', 64),
        ('io_forwardInfo_raw_data_3', 'output', 64),
        ('io_forwardInfo_raw_data_4', 'output', 64),
        ('io_forwardInfo_raw_data_5', 'output', 64),
        ('io_forwardInfo_raw_data_6', 'output', 64),
        ('io_forwardInfo_raw_data_7', 'output', 64),
        ('io_forwardInfo_firstbeat_valid', 'output', 1),
        ('io_forwardInfo_lastbeat_valid', 'output', 1),
        ('io_forwardInfo_denied', 'output', 1),
        ('io_forwardInfo_corrupt', 'output', 1),
        ('io_l2_pf_store_only', 'input', 1),
        ('io_acquire_fired_by_pipe_reg', 'input', 1),
        ('io_memSetPattenDetected', 'input', 1),
        ('io_matched', 'output', 1),
        ('io_l1Miss', 'output', 1),
        ('io_wfi_wfiReq', 'input', 1),
        ('io_wfi_wfiSafe', 'output', 1),
    ),
    "MissReadyGen": (
        ('io_in_0_ready', 'output', 1),
        ('io_in_0_valid', 'input', 1),
        ('io_in_0_bits_source', 'input', 4),
        ('io_in_0_bits_addr', 'input', 48),
        ('io_in_0_bits_vaddr', 'input', 50),
        ('io_in_1_ready', 'output', 1),
        ('io_in_1_valid', 'input', 1),
        ('io_in_1_bits_source', 'input', 4),
        ('io_in_1_bits_addr', 'input', 48),
        ('io_in_1_bits_vaddr', 'input', 50),
        ('io_in_2_ready', 'output', 1),
        ('io_in_2_valid', 'input', 1),
        ('io_in_2_bits_source', 'input', 4),
        ('io_in_2_bits_addr', 'input', 48),
        ('io_in_2_bits_vaddr', 'input', 50),
        ('io_in_3_ready', 'output', 1),
        ('io_in_3_bits_source', 'input', 4),
        ('io_in_3_bits_addr', 'input', 48),
        ('io_in_3_bits_vaddr', 'input', 50),
        ('io_queryMQ_0_req_bits_source', 'output', 4),
        ('io_queryMQ_0_req_bits_addr', 'output', 48),
        ('io_queryMQ_0_req_bits_vaddr', 'output', 50),
        ('io_queryMQ_0_ready', 'input', 1),
        ('io_queryMQ_1_req_bits_source', 'output', 4),
        ('io_queryMQ_1_req_bits_addr', 'output', 48),
        ('io_queryMQ_1_req_bits_vaddr', 'output', 50),
        ('io_queryMQ_1_ready', 'input', 1),
        ('io_queryMQ_2_req_bits_source', 'output', 4),
        ('io_queryMQ_2_req_bits_addr', 'output', 48),
        ('io_queryMQ_2_req_bits_vaddr', 'output', 50),
        ('io_queryMQ_2_ready', 'input', 1),
        ('io_queryMQ_3_req_bits_source', 'output', 4),
        ('io_queryMQ_3_req_bits_addr', 'output', 48),
        ('io_queryMQ_3_req_bits_vaddr', 'output', 50),
        ('io_queryMQ_3_ready', 'input', 1),
    ),
    "ProbeEntry": (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_req_ready', 'output', 1),
        ('io_req_valid', 'input', 1),
        ('io_req_bits_addr', 'input', 48),
        ('io_req_bits_vaddr', 'input', 50),
        ('io_req_bits_param', 'input', 2),
        ('io_req_bits_needData', 'input', 1),
        ('io_pipe_req_ready', 'input', 1),
        ('io_pipe_req_valid', 'output', 1),
        ('io_pipe_req_bits_probe_param', 'output', 2),
        ('io_pipe_req_bits_probe_need_data', 'output', 1),
        ('io_pipe_req_bits_vaddr', 'output', 50),
        ('io_pipe_req_bits_addr', 'output', 48),
        ('io_pipe_req_bits_id', 'output', 6),
        ('io_pipe_resp_valid', 'input', 1),
        ('io_pipe_resp_bits_id', 'input', 3),
        ('io_lrsc_locked_block_valid', 'input', 1),
        ('io_lrsc_locked_block_bits', 'input', 48),
        ('io_id', 'input', 3),
        ('io_block_addr_valid', 'output', 1),
        ('io_block_addr_bits', 'output', 48),
    ),
    "TreeArbiter": (
        ('io_in_0_valid', 'input', 1),
        ('io_in_0_bits_source', 'input', 4),
        ('io_in_0_bits_cmd', 'input', 5),
        ('io_in_0_bits_addr', 'input', 48),
        ('io_in_0_bits_vaddr', 'input', 50),
        ('io_in_0_bits_full_overwrite', 'input', 1),
        ('io_in_0_bits_word_idx', 'input', 3),
        ('io_in_0_bits_amo_data', 'input', 128),
        ('io_in_0_bits_amo_mask', 'input', 16),
        ('io_in_0_bits_amo_cmp', 'input', 128),
        ('io_in_0_bits_req_coh_state', 'input', 2),
        ('io_in_0_bits_id', 'input', 6),
        ('io_in_0_bits_isBtoT', 'input', 1),
        ('io_in_0_bits_occupy_way', 'input', 4),
        ('io_in_0_bits_cancel', 'input', 1),
        ('io_in_0_bits_store_data', 'input', 512),
        ('io_in_0_bits_store_mask', 'input', 64),
        ('io_in_1_valid', 'input', 1),
        ('io_in_1_bits_source', 'input', 4),
        ('io_in_1_bits_pf_source', 'input', 3),
        ('io_in_1_bits_cmd', 'input', 5),
        ('io_in_1_bits_addr', 'input', 48),
        ('io_in_1_bits_vaddr', 'input', 50),
        ('io_in_1_bits_req_coh_state', 'input', 2),
        ('io_in_1_bits_isBtoT', 'input', 1),
        ('io_in_1_bits_occupy_way', 'input', 4),
        ('io_in_1_bits_cancel', 'input', 1),
        ('io_in_2_valid', 'input', 1),
        ('io_in_2_bits_source', 'input', 4),
        ('io_in_2_bits_pf_source', 'input', 3),
        ('io_in_2_bits_cmd', 'input', 5),
        ('io_in_2_bits_addr', 'input', 48),
        ('io_in_2_bits_vaddr', 'input', 50),
        ('io_in_2_bits_req_coh_state', 'input', 2),
        ('io_in_2_bits_isBtoT', 'input', 1),
        ('io_in_2_bits_occupy_way', 'input', 4),
        ('io_in_2_bits_cancel', 'input', 1),
        ('io_in_3_valid', 'input', 1),
        ('io_in_3_bits_source', 'input', 4),
        ('io_in_3_bits_pf_source', 'input', 3),
        ('io_in_3_bits_cmd', 'input', 5),
        ('io_in_3_bits_addr', 'input', 48),
        ('io_in_3_bits_vaddr', 'input', 50),
        ('io_in_3_bits_req_coh_state', 'input', 2),
        ('io_in_3_bits_isBtoT', 'input', 1),
        ('io_in_3_bits_occupy_way', 'input', 4),
        ('io_in_3_bits_cancel', 'input', 1),
        ('io_out_valid', 'output', 1),
        ('io_out_bits_source', 'output', 4),
        ('io_out_bits_pf_source', 'output', 3),
        ('io_out_bits_cmd', 'output', 5),
        ('io_out_bits_addr', 'output', 48),
        ('io_out_bits_vaddr', 'output', 50),
        ('io_out_bits_full_overwrite', 'output', 1),
        ('io_out_bits_word_idx', 'output', 3),
        ('io_out_bits_amo_data', 'output', 128),
        ('io_out_bits_amo_mask', 'output', 16),
        ('io_out_bits_amo_cmp', 'output', 128),
        ('io_out_bits_req_coh_state', 'output', 2),
        ('io_out_bits_id', 'output', 6),
        ('io_out_bits_isBtoT', 'output', 1),
        ('io_out_bits_occupy_way', 'output', 4),
        ('io_out_bits_cancel', 'output', 1),
        ('io_out_bits_store_data', 'output', 512),
        ('io_out_bits_store_mask', 'output', 64),
    ),
    "WritebackEntry": (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_id', 'input', 5),
        ('io_req_valid', 'input', 1),
        ('io_req_bits_param', 'input', 3),
        ('io_req_bits_voluntary', 'input', 1),
        ('io_req_bits_hasData', 'input', 1),
        ('io_req_bits_corrupt', 'input', 1),
        ('io_req_bits_dirty', 'input', 1),
        ('io_req_bits_addr', 'input', 48),
        ('io_req_data_data', 'input', 512),
        ('io_mem_release_ready', 'input', 1),
        ('io_mem_release_valid', 'output', 1),
        ('io_mem_release_bits_opcode', 'output', 3),
        ('io_mem_release_bits_param', 'output', 3),
        ('io_mem_release_bits_source', 'output', 6),
        ('io_mem_release_bits_address', 'output', 48),
        ('io_mem_release_bits_data', 'output', 256),
        ('io_mem_release_bits_corrupt', 'output', 1),
        ('io_mem_grant_valid', 'input', 1),
        ('io_primary_valid', 'input', 1),
        ('io_primary_ready', 'output', 1),
        ('io_block_addr_valid', 'output', 1),
        ('io_block_addr_bits', 'output', 48),
    ),
    "WritebackEntry_15": (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_id', 'input', 6),
        ('io_req_valid', 'input', 1),
        ('io_req_bits_param', 'input', 3),
        ('io_req_bits_voluntary', 'input', 1),
        ('io_req_bits_hasData', 'input', 1),
        ('io_req_bits_corrupt', 'input', 1),
        ('io_req_bits_dirty', 'input', 1),
        ('io_req_bits_addr', 'input', 48),
        ('io_req_data_data', 'input', 512),
        ('io_mem_release_ready', 'input', 1),
        ('io_mem_release_valid', 'output', 1),
        ('io_mem_release_bits_opcode', 'output', 3),
        ('io_mem_release_bits_param', 'output', 3),
        ('io_mem_release_bits_source', 'output', 6),
        ('io_mem_release_bits_address', 'output', 48),
        ('io_mem_release_bits_data', 'output', 256),
        ('io_mem_release_bits_corrupt', 'output', 1),
        ('io_mem_grant_valid', 'input', 1),
        ('io_primary_valid', 'input', 1),
        ('io_primary_ready', 'output', 1),
        ('io_block_addr_valid', 'output', 1),
        ('io_block_addr_bits', 'output', 48),
    ),
}
PORT_SPECS = LOCKED_PORT_SPECS
# END LOCKED PORT CATALOG


# =============================================================================
# Implementation
# =============================================================================
class DcacheMissQueueFamily(Elaboratable):
    """One exact DCache miss/queue leaf with bounded transaction semantics."""

    def __init__(self, member: str = "MissEntry") -> None:
        """Declare the frozen ANSI port surface for one locked member."""

        if member not in PORT_SPECS:
            raise ValueError(member)
        self.member = member
        self.specs = PORT_SPECS[member]
        self.ports = {
            name: Signal(width, name=name)
            for name, _direction, width in self.specs
        }
        self.directions = {
            name: direction for name, direction, _width in self.specs
        }

    def _defaults(self, module: Module) -> None:
        """Drive every output deterministically before member-specific routing."""

        for name, direction, _width in self.specs:
            if direction == "output":
                module.d.comb += self.ports[name].eq(0)

    def _clock_domain(self, module: Module) -> None:
        """Attach the locked clock/reset pair when the member has one."""

        if "clock" in self.ports and "reset" in self.ports:
            domain = ClockDomain("sync", async_reset=True)
            domain.clk = self.ports["clock"]
            domain.rst = self.ports["reset"]
            module.domains += domain

    def _elaborate_cmo(self, module: Module) -> None:
        """Model the bounded CMO request/A-channel/D-channel response sequence."""

        state = Signal(2, reset=0)
        saved_opcode = Signal(3)
        saved_address = Signal(64)
        denied = Signal()
        corrupt = Signal()
        module.d.comb += [
            self.ports["io_req_ready"].eq(state == 0),
            self.ports["io_req_chanA_valid"].eq((state == 1) & ~self.ports["io_wfi_wfiReq"]),
            self.ports["io_req_chanA_bits_opcode"].eq(Mux(state == 0, self.ports["io_req_bits_opcode"], saved_opcode)),
            self.ports["io_req_chanA_bits_address"].eq(saved_address[:48]),
            self.ports["io_resp_chanD_ready"].eq(state == 2),
            self.ports["io_resp_to_lsq_valid"].eq(state == 3),
            self.ports["io_resp_to_lsq_bits_denied"].eq(denied),
            self.ports["io_resp_to_lsq_bits_corrupt"].eq(corrupt),
            self.ports["io_wfi_wfiSafe"].eq((state == 0) & self.ports["io_wfi_wfiReq"]),
        ]
        with module.If((state == 0) & self.ports["io_req_valid"]):
            module.d.sync += [
                state.eq(1),
                saved_opcode.eq(self.ports["io_req_bits_opcode"]),
                saved_address.eq(self.ports["io_req_bits_address"]),
                denied.eq(0),
                corrupt.eq(0),
            ]
        with module.Elif((state == 1) & self.ports["io_req_chanA_ready"] & ~self.ports["io_wfi_wfiReq"]):
            module.d.sync += state.eq(2)
        with module.Elif((state == 2) & self.ports["io_resp_chanD_valid"]):
            module.d.sync += [
                state.eq(3),
                denied.eq(self.ports["io_resp_chanD_bits_denied"]),
                corrupt.eq(self.ports["io_resp_chanD_bits_corrupt"]),
            ]
        with module.Elif((state == 3) & self.ports["io_resp_to_lsq_ready"]):
            module.d.sync += state.eq(0)

    def _elaborate_miss_entry(self, module: Module) -> None:
        """Model allocation, acquire issue, grant acknowledgement, and release."""

        active = Signal(reset=0)
        acquire_sent = Signal(reset=0)
        grant_seen = Signal(reset=0)
        saved_source = Signal(4)
        saved_addr = Signal(48)
        saved_vaddr = Signal(50)
        saved_cmd = Signal(5)
        saved_id = Signal(6)
        saved_way = Signal(4)
        saved_data = Signal(512)
        saved_mask = Signal(64)
        alloc = (
            self.ports["io_primary_valid"]
            & self.ports["io_req_valid"]
            & ~self.ports["io_req_bits_cancel"]
            & ~self.ports["io_wbq_block_miss_req"]
            & ~active
        )
        module.d.comb += [
            self.ports["io_primary_ready"].eq(~active),
            self.ports["io_secondary_ready"].eq(active & (self.ports["io_req_bits_addr"] == saved_addr)),
            self.ports["io_secondary_reject"].eq(active & (self.ports["io_req_bits_addr"] != saved_addr)),
            self.ports["io_mem_acquire_valid"].eq(active & ~acquire_sent),
            self.ports["io_mem_acquire_bits_opcode"].eq(0),
            self.ports["io_mem_acquire_bits_param"].eq(0),
            self.ports["io_mem_acquire_bits_source"].eq(self.ports["io_id"]),
            self.ports["io_mem_acquire_bits_address"].eq(saved_addr),
            self.ports["io_mem_acquire_bits_user_alias"].eq(0),
            self.ports["io_mem_acquire_bits_user_vaddr"].eq(saved_vaddr[:44]),
            self.ports["io_mem_acquire_bits_user_reqSource"].eq(saved_source),
            self.ports["io_mem_acquire_bits_user_needHint"].eq(0),
            self.ports["io_mem_acquire_bits_echo_isKeyword"].eq(0),
            self.ports["io_mem_finish_valid"].eq(grant_seen),
            self.ports["io_mem_finish_bits_sink"].eq(self.ports["io_mem_grant_bits_sink"]),
            self.ports["io_main_pipe_req_valid"].eq(active & grant_seen),
            self.ports["io_main_pipe_req_bits_miss_id"].eq(self.ports["io_id"]),
            self.ports["io_main_pipe_req_bits_occupy_way"].eq(saved_way),
            self.ports["io_main_pipe_req_bits_source"].eq(saved_source),
            self.ports["io_main_pipe_req_bits_cmd"].eq(saved_cmd),
            self.ports["io_main_pipe_req_bits_vaddr"].eq(saved_vaddr),
            self.ports["io_main_pipe_req_bits_addr"].eq(saved_addr),
            self.ports["io_main_pipe_req_bits_word_idx"].eq(0),
            self.ports["io_main_pipe_req_bits_amo_data"].eq(0),
            self.ports["io_main_pipe_req_bits_amo_mask"].eq(0),
            self.ports["io_main_pipe_req_bits_amo_cmp"].eq(0),
            self.ports["io_main_pipe_req_bits_pf_source"].eq(0),
            self.ports["io_main_pipe_req_bits_access"].eq(0),
            self.ports["io_main_pipe_req_bits_id"].eq(saved_id),
            self.ports["io_refill_info_valid"].eq(active & grant_seen),
            self.ports["io_refill_info_bits_store_data"].eq(saved_data),
            self.ports["io_refill_info_bits_miss_param"].eq(self.ports["io_mem_grant_bits_param"]),
            self.ports["io_refill_info_bits_error_tl_denied"].eq(self.ports["io_mem_grant_bits_denied"]),
            self.ports["io_refill_info_bits_error_tl_corrupt"].eq(self.ports["io_mem_grant_bits_corrupt"]),
            self.ports["io_occupy_way"].eq(saved_way),
            self.ports["io_probe_block"].eq(active & (self.ports["io_probe_req_bits_addr"] == saved_addr)),
            self.ports["io_replace_block"].eq(active & (self.ports["io_replace_req_bits_addr"] == saved_addr)),
            self.ports["io_req_vaddr_valid"].eq(active),
            self.ports["io_req_vaddr_bits"].eq(saved_vaddr),
            self.ports["io_req_isBtoT"].eq(0),
            self.ports["io_req_handled_by_this_entry"].eq(alloc | self.ports["io_secondary_ready"]),
            self.ports["io_forwardInfo_inflight"].eq(active),
            self.ports["io_forwardInfo_paddr"].eq(saved_addr),
            self.ports["io_forwardInfo_raw_data_0"].eq(saved_data[:64]),
            self.ports["io_forwardInfo_raw_data_1"].eq(saved_data[64:128]),
            self.ports["io_forwardInfo_raw_data_2"].eq(saved_data[128:192]),
            self.ports["io_forwardInfo_raw_data_3"].eq(saved_data[192:256]),
            self.ports["io_forwardInfo_raw_data_4"].eq(saved_data[256:320]),
            self.ports["io_forwardInfo_raw_data_5"].eq(saved_data[320:384]),
            self.ports["io_forwardInfo_raw_data_6"].eq(saved_data[384:448]),
            self.ports["io_forwardInfo_raw_data_7"].eq(saved_data[448:512]),
            self.ports["io_forwardInfo_firstbeat_valid"].eq(grant_seen),
            self.ports["io_forwardInfo_lastbeat_valid"].eq(grant_seen),
            self.ports["io_forwardInfo_denied"].eq(self.ports["io_mem_grant_bits_denied"]),
            self.ports["io_forwardInfo_corrupt"].eq(self.ports["io_mem_grant_bits_corrupt"]),
            self.ports["io_matched"].eq(active),
            self.ports["io_l1Miss"].eq(active),
            self.ports["io_wfi_wfiSafe"].eq(~active & self.ports["io_wfi_wfiReq"]),
        ]
        with module.If(alloc):
            module.d.sync += [
                active.eq(1),
                acquire_sent.eq(0),
                grant_seen.eq(0),
                saved_source.eq(self.ports["io_req_bits_source"]),
                saved_addr.eq(self.ports["io_req_bits_addr"]),
                saved_vaddr.eq(self.ports["io_req_bits_vaddr"]),
                saved_cmd.eq(self.ports["io_miss_req_pipe_reg_req_cmd"]),
                saved_id.eq(self.ports["io_miss_req_pipe_reg_req_id"]),
                saved_way.eq(self.ports["io_miss_req_pipe_reg_req_occupy_way"]),
                saved_data.eq(self.ports["io_miss_req_pipe_reg_req_store_data"]),
                saved_mask.eq(self.ports["io_miss_req_pipe_reg_req_store_mask"]),
            ]
        with module.If(active & ~acquire_sent & self.ports["io_mem_acquire_ready"]):
            module.d.sync += acquire_sent.eq(1)
        with module.If(active & self.ports["io_mem_grant_valid"]):
            module.d.sync += grant_seen.eq(1)
        with module.If(active & grant_seen & self.ports["io_mem_finish_ready"]):
            module.d.sync += grant_seen.eq(0)
        with module.If(active & grant_seen & self.ports["io_main_pipe_req_ready"] & self.ports["io_main_pipe_resp"]):
            module.d.sync += active.eq(0)

    def _elaborate_ready_gen(self, module: Module) -> None:
        """Implement fixed-priority miss-ready generation and query forwarding."""

        earlier = Signal(reset=0)
        del earlier
        for index in range(4):
            prefix = f"io_in_{index}"
            query = f"io_queryMQ_{index}"
            if f"{prefix}_ready" in self.ports:
                prior_valids = [
                    self.ports[f"io_in_{previous}_valid"]
                    for previous in range(index)
                    if f"io_in_{previous}_valid" in self.ports
                ]
                blocked = prior_valids[0] if prior_valids else 0
                for value in prior_valids[1:]:
                    blocked = blocked | value
                module.d.comb += self.ports[f"{prefix}_ready"].eq(
                    self.ports[f"{query}_ready"] & ~blocked
                )
            for field in ("source", "addr", "vaddr"):
                source = f"{prefix}_bits_{field}"
                target = f"{query}_req_bits_{field}"
                if source in self.ports and target in self.ports:
                    module.d.comb += self.ports[target].eq(self.ports[source])

    def _elaborate_probe(self, module: Module) -> None:
        """Model one probe entry from enqueue through pipe response."""

        state = Signal(2, reset=0)
        saved_addr = Signal(48)
        saved_vaddr = Signal(50)
        saved_param = Signal(2)
        saved_need_data = Signal()
        module.d.comb += [
            self.ports["io_req_ready"].eq(state == 0),
            self.ports["io_pipe_req_valid"].eq(state == 1),
            self.ports["io_pipe_req_bits_probe_param"].eq(saved_param),
            self.ports["io_pipe_req_bits_probe_need_data"].eq(saved_need_data),
            self.ports["io_pipe_req_bits_vaddr"].eq(saved_vaddr),
            self.ports["io_pipe_req_bits_addr"].eq(saved_addr),
            self.ports["io_pipe_req_bits_id"].eq(self.ports["io_id"]),
            self.ports["io_block_addr_valid"].eq(state != 0),
            self.ports["io_block_addr_bits"].eq(saved_addr),
        ]
        with module.If((state == 0) & self.ports["io_req_valid"]):
            module.d.sync += [
                state.eq(1),
                saved_addr.eq(self.ports["io_req_bits_addr"]),
                saved_vaddr.eq(self.ports["io_req_bits_vaddr"]),
                saved_param.eq(self.ports["io_req_bits_param"]),
                saved_need_data.eq(self.ports["io_req_bits_needData"]),
            ]
        with module.Elif((state == 1) & self.ports["io_pipe_req_ready"]):
            module.d.sync += state.eq(2)
        with module.Elif((state == 2) & self.ports["io_pipe_resp_valid"] & (self.ports["io_pipe_resp_bits_id"] == self.ports["io_id"])):
            module.d.sync += state.eq(0)

    def _elaborate_tree_arbiter(self, module: Module) -> None:
        """Route the first valid request through the locked arbiter surface."""

        valid0 = self.ports["io_in_0_valid"]
        valid1 = self.ports["io_in_1_valid"]
        valid2 = self.ports["io_in_2_valid"]
        valid3 = self.ports["io_in_3_valid"]
        selected = Signal(2)
        module.d.comb += [
            selected.eq(Mux(valid0, 0, Mux(valid1, 1, Mux(valid2, 2, 3)))),
            self.ports["io_out_valid"].eq(valid0 | valid1 | valid2 | valid3),
        ]
        fields = (
            "source", "pf_source", "cmd", "addr", "vaddr", "full_overwrite",
            "word_idx", "amo_data", "amo_mask", "amo_cmp", "req_coh_state",
            "id", "isBtoT", "occupy_way", "cancel", "store_data", "store_mask",
        )
        for field in fields:
            output = f"io_out_bits_{field}"
            if output not in self.ports:
                continue
            result = 0
            for index in range(3, -1, -1):
                source = f"io_in_{index}_bits_{field}"
                if source in self.ports:
                    result = Mux(selected == index, self.ports[source], result)
            module.d.comb += self.ports[output].eq(result)

    def _elaborate_writeback(self, module: Module) -> None:
        """Model bounded writeback allocation, release beats, and completion."""

        active = Signal(reset=0)
        saved_addr = Signal(48)
        saved_param = Signal(3)
        saved_corrupt = Signal()
        saved_data = Signal(512)
        sent = Signal(reset=0)
        alloc = self.ports["io_primary_valid"] & self.ports["io_req_valid"] & ~active
        module.d.comb += [
            self.ports["io_primary_ready"].eq(~active),
            self.ports["io_mem_release_valid"].eq(active & ~sent),
            self.ports["io_mem_release_bits_opcode"].eq(0),
            self.ports["io_mem_release_bits_param"].eq(saved_param),
            self.ports["io_mem_release_bits_source"].eq(self.ports["io_id"]),
            self.ports["io_mem_release_bits_address"].eq(saved_addr),
            self.ports["io_mem_release_bits_data"].eq(saved_data[:256]),
            self.ports["io_mem_release_bits_corrupt"].eq(saved_corrupt),
            self.ports["io_block_addr_valid"].eq(active),
            self.ports["io_block_addr_bits"].eq(saved_addr),
        ]
        with module.If(alloc):
            module.d.sync += [
                active.eq(1),
                sent.eq(0),
                saved_addr.eq(self.ports["io_req_bits_addr"]),
                saved_param.eq(self.ports["io_req_bits_param"]),
                saved_corrupt.eq(self.ports["io_req_bits_corrupt"]),
                saved_data.eq(self.ports["io_req_data_data"]),
            ]
        with module.If(active & ~sent & self.ports["io_mem_release_ready"]):
            module.d.sync += sent.eq(1)
        with module.If(active & sent & self.ports["io_mem_grant_valid"]):
            module.d.sync += [active.eq(0), sent.eq(0)]

    def elaborate(self, platform: Any) -> Module:
        """Elaborate the requested member's bounded behavior and exact ports."""

        del platform
        module = Module()
        self._clock_domain(module)
        self._defaults(module)
        if self.member == "CMOUnit":
            self._elaborate_cmo(module)
        elif self.member == "MissEntry":
            self._elaborate_miss_entry(module)
        elif self.member == "MissReadyGen":
            self._elaborate_ready_gen(module)
        elif self.member == "ProbeEntry":
            self._elaborate_probe(module)
        elif self.member == "TreeArbiter":
            self._elaborate_tree_arbiter(module)
        elif self.member in ("WritebackEntry", "WritebackEntry_15"):
            self._elaborate_writeback(module)
        return module


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration: Any, injected_dependencies: Any) -> str:
    """Export deterministic same-name Verilog for one locked family member."""

    del injected_dependencies
    member = "MissEntry"
    if isinstance(configuration, dict):
        member = str(configuration.get("module", member))
    elif isinstance(configuration, str):
        member = configuration
    top = DcacheMissQueueFamily(member)
    ports = [top.ports[name] for name, _direction, _width in top.specs]
    return verilog.convert(top, name=member, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    """Print the default MissEntry RTL for a direct Build invocation."""

    print(build_verilog({"module": "MissEntry"}, {}))


if __name__ == "__main__":
    main()
