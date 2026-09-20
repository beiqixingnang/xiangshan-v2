"""UHSC V2 vector/memory family aggregate.
昆明湖 V2 向量/内存 family 聚合。

The seven selected vector and memory closures share one搬运-ready Build
subject.  Their ANSI surfaces are copied mechanically from the locked V2
hierarchy; bounded queue/merge state is elaborated locally and remains
CONTRACT_ONLY until parent differential closures are run.
"""

from __future__ import annotations

from typing import Any, cast

from amaranth import ClockDomain, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


__all__ = ["COVERED_MODULES", "IMPLEMENTED_MEMBERS", "CONTRACT_ONLY_MEMBERS", "VectorMemoryFamily", "build_verilog", "main"]

COVERED_MODULES: tuple[str, ...] = (
    "VLMergeBufferImp",
    "VSMergeBufferImp",
    "VSegmentUnit",
    "VfofBuffer",
    "VirtualLoadQueue",
    "VldMergeUnit",
    "VsetModule",
)
IMPLEMENTED_MEMBERS: tuple[str, ...] = ("VldMergeUnit", "VsetModule")
CONTRACT_ONLY_MEMBERS: tuple[str, ...] = ("VLMergeBufferImp", "VSMergeBufferImp", "VSegmentUnit", "VfofBuffer", "VirtualLoadQueue")


# =============================================================================
# Module Contract
# =============================================================================
PortSpec = tuple[str, str, int]

PORT_SPECS: dict[str, tuple[PortSpec, ...]] = {
    'VLMergeBufferImp': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_redirect_valid', 'input', 1),
        ('io_redirect_bits_robIdx_flag', 'input', 1),
        ('io_redirect_bits_robIdx_value', 'input', 8),
        ('io_redirect_bits_level', 'input', 1),
        ('io_fromPipeline_0_valid', 'input', 1),
        ('io_fromPipeline_0_bits_mBIndex', 'input', 4),
        ('io_fromPipeline_0_bits_trigger', 'input', 4),
        ('io_fromPipeline_0_bits_exceptionVec_3', 'input', 1),
        ('io_fromPipeline_0_bits_exceptionVec_4', 'input', 1),
        ('io_fromPipeline_0_bits_exceptionVec_5', 'input', 1),
        ('io_fromPipeline_0_bits_exceptionVec_13', 'input', 1),
        ('io_fromPipeline_0_bits_exceptionVec_19', 'input', 1),
        ('io_fromPipeline_0_bits_exceptionVec_21', 'input', 1),
        ('io_fromPipeline_0_bits_hasException', 'input', 1),
        ('io_fromPipeline_0_bits_vaddr', 'input', 64),
        ('io_fromPipeline_0_bits_vaNeedExt', 'input', 1),
        ('io_fromPipeline_0_bits_gpaddr', 'input', 64),
        ('io_fromPipeline_0_bits_isForVSnonLeafPTE', 'input', 1),
        ('io_fromPipeline_0_bits_vstart', 'input', 8),
        ('io_fromPipeline_0_bits_vecTriggerMask', 'input', 16),
        ('io_fromPipeline_0_bits_elemIdx', 'input', 8),
        ('io_fromPipeline_0_bits_mask', 'input', 16),
        ('io_fromPipeline_0_bits_alignedType', 'input', 3),
        ('io_fromPipeline_0_bits_reg_offset', 'input', 4),
        ('io_fromPipeline_0_bits_elemIdxInsideVd', 'input', 8),
        ('io_fromPipeline_0_bits_vecdata', 'input', 128),
        ('io_fromPipeline_1_valid', 'input', 1),
        ('io_fromPipeline_1_bits_mBIndex', 'input', 4),
        ('io_fromPipeline_1_bits_trigger', 'input', 4),
        ('io_fromPipeline_1_bits_exceptionVec_3', 'input', 1),
        ('io_fromPipeline_1_bits_exceptionVec_4', 'input', 1),
        ('io_fromPipeline_1_bits_exceptionVec_5', 'input', 1),
        ('io_fromPipeline_1_bits_exceptionVec_13', 'input', 1),
        ('io_fromPipeline_1_bits_exceptionVec_19', 'input', 1),
        ('io_fromPipeline_1_bits_exceptionVec_21', 'input', 1),
        ('io_fromPipeline_1_bits_hasException', 'input', 1),
        ('io_fromPipeline_1_bits_vaddr', 'input', 64),
        ('io_fromPipeline_1_bits_vaNeedExt', 'input', 1),
        ('io_fromPipeline_1_bits_gpaddr', 'input', 64),
        ('io_fromPipeline_1_bits_isForVSnonLeafPTE', 'input', 1),
        ('io_fromPipeline_1_bits_vstart', 'input', 8),
        ('io_fromPipeline_1_bits_vecTriggerMask', 'input', 16),
        ('io_fromPipeline_1_bits_elemIdx', 'input', 8),
        ('io_fromPipeline_1_bits_mask', 'input', 16),
        ('io_fromPipeline_1_bits_alignedType', 'input', 3),
        ('io_fromPipeline_1_bits_reg_offset', 'input', 4),
        ('io_fromPipeline_1_bits_elemIdxInsideVd', 'input', 8),
        ('io_fromPipeline_1_bits_vecdata', 'input', 128),
        ('io_fromPipeline_2_valid', 'input', 1),
        ('io_fromPipeline_2_bits_mBIndex', 'input', 4),
        ('io_fromPipeline_2_bits_trigger', 'input', 4),
        ('io_fromPipeline_2_bits_exceptionVec_3', 'input', 1),
        ('io_fromPipeline_2_bits_exceptionVec_4', 'input', 1),
        ('io_fromPipeline_2_bits_exceptionVec_5', 'input', 1),
        ('io_fromPipeline_2_bits_exceptionVec_13', 'input', 1),
        ('io_fromPipeline_2_bits_exceptionVec_19', 'input', 1),
        ('io_fromPipeline_2_bits_exceptionVec_21', 'input', 1),
        ('io_fromPipeline_2_bits_hasException', 'input', 1),
        ('io_fromPipeline_2_bits_vaddr', 'input', 64),
        ('io_fromPipeline_2_bits_vaNeedExt', 'input', 1),
        ('io_fromPipeline_2_bits_gpaddr', 'input', 64),
        ('io_fromPipeline_2_bits_isForVSnonLeafPTE', 'input', 1),
        ('io_fromPipeline_2_bits_vstart', 'input', 8),
        ('io_fromPipeline_2_bits_vecTriggerMask', 'input', 16),
        ('io_fromPipeline_2_bits_elemIdx', 'input', 8),
        ('io_fromPipeline_2_bits_mask', 'input', 16),
        ('io_fromPipeline_2_bits_alignedType', 'input', 3),
        ('io_fromPipeline_2_bits_reg_offset', 'input', 4),
        ('io_fromPipeline_2_bits_elemIdxInsideVd', 'input', 8),
        ('io_fromPipeline_2_bits_vecdata', 'input', 128),
        ('io_fromSplit_0_req_ready', 'output', 1),
        ('io_fromSplit_0_req_valid', 'input', 1),
        ('io_fromSplit_0_req_bits_mask', 'input', 16),
        ('io_fromSplit_0_req_bits_vaddr', 'input', 50),
        ('io_fromSplit_0_req_bits_flowNum', 'input', 5),
        ('io_fromSplit_0_req_bits_uop_fuOpType', 'input', 9),
        ('io_fromSplit_0_req_bits_uop_vecWen', 'input', 1),
        ('io_fromSplit_0_req_bits_uop_v0Wen', 'input', 1),
        ('io_fromSplit_0_req_bits_uop_vlWen', 'input', 1),
        ('io_fromSplit_0_req_bits_uop_vpu_vma', 'input', 1),
        ('io_fromSplit_0_req_bits_uop_vpu_vta', 'input', 1),
        ('io_fromSplit_0_req_bits_uop_vpu_vsew', 'input', 2),
        ('io_fromSplit_0_req_bits_uop_vpu_vlmul', 'input', 3),
        ('io_fromSplit_0_req_bits_uop_vpu_vm', 'input', 1),
        ('io_fromSplit_0_req_bits_uop_vpu_vuopIdx', 'input', 7),
        ('io_fromSplit_0_req_bits_uop_vpu_vl', 'input', 8),
        ('io_fromSplit_0_req_bits_uop_vpu_nf', 'input', 3),
        ('io_fromSplit_0_req_bits_uop_vpu_veew', 'input', 2),
        ('io_fromSplit_0_req_bits_uop_uopIdx', 'input', 7),
        ('io_fromSplit_0_req_bits_uop_pdest', 'input', 8),
        ('io_fromSplit_0_req_bits_uop_robIdx_flag', 'input', 1),
        ('io_fromSplit_0_req_bits_uop_robIdx_value', 'input', 8),
        ('io_fromSplit_0_req_bits_data', 'input', 128),
        ('io_fromSplit_0_req_bits_vdIdx', 'input', 3),
        ('io_fromSplit_0_req_bits_fof', 'input', 1),
        ('io_fromSplit_0_req_bits_vlmax', 'input', 8),
        ('io_fromSplit_0_resp_valid', 'output', 1),
        ('io_fromSplit_0_resp_bits_mBIndex', 'output', 4),
        ('io_fromSplit_1_req_ready', 'output', 1),
        ('io_fromSplit_1_req_valid', 'input', 1),
        ('io_fromSplit_1_req_bits_mask', 'input', 16),
        ('io_fromSplit_1_req_bits_vaddr', 'input', 50),
        ('io_fromSplit_1_req_bits_flowNum', 'input', 5),
        ('io_fromSplit_1_req_bits_uop_fuOpType', 'input', 9),
        ('io_fromSplit_1_req_bits_uop_vecWen', 'input', 1),
        ('io_fromSplit_1_req_bits_uop_v0Wen', 'input', 1),
        ('io_fromSplit_1_req_bits_uop_vlWen', 'input', 1),
        ('io_fromSplit_1_req_bits_uop_vpu_vma', 'input', 1),
        ('io_fromSplit_1_req_bits_uop_vpu_vta', 'input', 1),
        ('io_fromSplit_1_req_bits_uop_vpu_vsew', 'input', 2),
        ('io_fromSplit_1_req_bits_uop_vpu_vlmul', 'input', 3),
        ('io_fromSplit_1_req_bits_uop_vpu_vm', 'input', 1),
        ('io_fromSplit_1_req_bits_uop_vpu_vuopIdx', 'input', 7),
        ('io_fromSplit_1_req_bits_uop_vpu_vl', 'input', 8),
        ('io_fromSplit_1_req_bits_uop_vpu_nf', 'input', 3),
        ('io_fromSplit_1_req_bits_uop_vpu_veew', 'input', 2),
        ('io_fromSplit_1_req_bits_uop_uopIdx', 'input', 7),
        ('io_fromSplit_1_req_bits_uop_pdest', 'input', 8),
        ('io_fromSplit_1_req_bits_uop_robIdx_flag', 'input', 1),
        ('io_fromSplit_1_req_bits_uop_robIdx_value', 'input', 8),
        ('io_fromSplit_1_req_bits_data', 'input', 128),
        ('io_fromSplit_1_req_bits_vdIdx', 'input', 3),
        ('io_fromSplit_1_req_bits_fof', 'input', 1),
        ('io_fromSplit_1_req_bits_vlmax', 'input', 8),
        ('io_fromSplit_1_resp_valid', 'output', 1),
        ('io_fromSplit_1_resp_bits_mBIndex', 'output', 4),
        ('io_uopWriteback_0_ready', 'input', 1),
        ('io_uopWriteback_0_valid', 'output', 1),
        ('io_uopWriteback_0_bits_uop_exceptionVec_3', 'output', 1),
        ('io_uopWriteback_0_bits_uop_exceptionVec_4', 'output', 1),
        ('io_uopWriteback_0_bits_uop_exceptionVec_5', 'output', 1),
        ('io_uopWriteback_0_bits_uop_exceptionVec_13', 'output', 1),
        ('io_uopWriteback_0_bits_uop_exceptionVec_19', 'output', 1),
        ('io_uopWriteback_0_bits_uop_exceptionVec_21', 'output', 1),
        ('io_uopWriteback_0_bits_uop_trigger', 'output', 4),
        ('io_uopWriteback_0_bits_uop_fuOpType', 'output', 9),
        ('io_uopWriteback_0_bits_uop_vecWen', 'output', 1),
        ('io_uopWriteback_0_bits_uop_v0Wen', 'output', 1),
        ('io_uopWriteback_0_bits_uop_vlWen', 'output', 1),
        ('io_uopWriteback_0_bits_uop_flushPipe', 'output', 1),
        ('io_uopWriteback_0_bits_uop_vpu_vma', 'output', 1),
        ('io_uopWriteback_0_bits_uop_vpu_vta', 'output', 1),
        ('io_uopWriteback_0_bits_uop_vpu_vsew', 'output', 2),
        ('io_uopWriteback_0_bits_uop_vpu_vlmul', 'output', 3),
        ('io_uopWriteback_0_bits_uop_vpu_vm', 'output', 1),
        ('io_uopWriteback_0_bits_uop_vpu_vstart', 'output', 8),
        ('io_uopWriteback_0_bits_uop_vpu_vuopIdx', 'output', 7),
        ('io_uopWriteback_0_bits_uop_vpu_vmask', 'output', 128),
        ('io_uopWriteback_0_bits_uop_vpu_vl', 'output', 8),
        ('io_uopWriteback_0_bits_uop_vpu_nf', 'output', 3),
        ('io_uopWriteback_0_bits_uop_vpu_veew', 'output', 2),
        ('io_uopWriteback_0_bits_uop_pdest', 'output', 8),
        ('io_uopWriteback_0_bits_uop_robIdx_flag', 'output', 1),
        ('io_uopWriteback_0_bits_uop_robIdx_value', 'output', 8),
        ('io_uopWriteback_0_bits_uop_replayInst', 'output', 1),
        ('io_uopWriteback_0_bits_data', 'output', 128),
        ('io_uopWriteback_0_bits_vdIdxInField', 'output', 3),
        ('io_uopWriteback_1_ready', 'input', 1),
        ('io_uopWriteback_1_valid', 'output', 1),
        ('io_uopWriteback_1_bits_uop_exceptionVec_3', 'output', 1),
        ('io_uopWriteback_1_bits_uop_exceptionVec_4', 'output', 1),
        ('io_uopWriteback_1_bits_uop_exceptionVec_5', 'output', 1),
        ('io_uopWriteback_1_bits_uop_exceptionVec_13', 'output', 1),
        ('io_uopWriteback_1_bits_uop_exceptionVec_19', 'output', 1),
        ('io_uopWriteback_1_bits_uop_exceptionVec_21', 'output', 1),
        ('io_uopWriteback_1_bits_uop_trigger', 'output', 4),
        ('io_uopWriteback_1_bits_uop_fuOpType', 'output', 9),
        ('io_uopWriteback_1_bits_uop_vecWen', 'output', 1),
        ('io_uopWriteback_1_bits_uop_v0Wen', 'output', 1),
        ('io_uopWriteback_1_bits_uop_vlWen', 'output', 1),
        ('io_uopWriteback_1_bits_uop_flushPipe', 'output', 1),
        ('io_uopWriteback_1_bits_uop_vpu_vma', 'output', 1),
        ('io_uopWriteback_1_bits_uop_vpu_vta', 'output', 1),
        ('io_uopWriteback_1_bits_uop_vpu_vsew', 'output', 2),
        ('io_uopWriteback_1_bits_uop_vpu_vlmul', 'output', 3),
        ('io_uopWriteback_1_bits_uop_vpu_vm', 'output', 1),
        ('io_uopWriteback_1_bits_uop_vpu_vstart', 'output', 8),
        ('io_uopWriteback_1_bits_uop_vpu_vuopIdx', 'output', 7),
        ('io_uopWriteback_1_bits_uop_vpu_vmask', 'output', 128),
        ('io_uopWriteback_1_bits_uop_vpu_vl', 'output', 8),
        ('io_uopWriteback_1_bits_uop_vpu_nf', 'output', 3),
        ('io_uopWriteback_1_bits_uop_vpu_veew', 'output', 2),
        ('io_uopWriteback_1_bits_uop_pdest', 'output', 8),
        ('io_uopWriteback_1_bits_uop_robIdx_flag', 'output', 1),
        ('io_uopWriteback_1_bits_uop_robIdx_value', 'output', 8),
        ('io_uopWriteback_1_bits_uop_replayInst', 'output', 1),
        ('io_uopWriteback_1_bits_data', 'output', 128),
        ('io_uopWriteback_1_bits_vdIdxInField', 'output', 3),
        ('io_toSplit_threshold', 'output', 1),
        ('io_toLsq_0_valid', 'output', 1),
        ('io_toLsq_0_bits_robidx_flag', 'output', 1),
        ('io_toLsq_0_bits_robidx_value', 'output', 8),
        ('io_toLsq_0_bits_uopidx', 'output', 7),
        ('io_toLsq_0_bits_vaddr', 'output', 64),
        ('io_toLsq_0_bits_vaNeedExt', 'output', 1),
        ('io_toLsq_0_bits_gpaddr', 'output', 64),
        ('io_toLsq_0_bits_isForVSnonLeafPTE', 'output', 1),
        ('io_toLsq_0_bits_feedback_0', 'output', 1),
        ('io_toLsq_0_bits_vl', 'output', 8),
        ('io_toLsq_0_bits_exceptionVec_3', 'output', 1),
        ('io_toLsq_0_bits_exceptionVec_4', 'output', 1),
        ('io_toLsq_0_bits_exceptionVec_5', 'output', 1),
        ('io_toLsq_0_bits_exceptionVec_13', 'output', 1),
        ('io_toLsq_0_bits_exceptionVec_19', 'output', 1),
        ('io_toLsq_0_bits_exceptionVec_21', 'output', 1),
        ('io_toLsq_1_valid', 'output', 1),
        ('io_toLsq_1_bits_robidx_flag', 'output', 1),
        ('io_toLsq_1_bits_robidx_value', 'output', 8),
        ('io_toLsq_1_bits_uopidx', 'output', 7),
        ('io_toLsq_1_bits_vaddr', 'output', 64),
        ('io_toLsq_1_bits_vaNeedExt', 'output', 1),
        ('io_toLsq_1_bits_gpaddr', 'output', 64),
        ('io_toLsq_1_bits_isForVSnonLeafPTE', 'output', 1),
        ('io_toLsq_1_bits_feedback_0', 'output', 1),
        ('io_toLsq_1_bits_vl', 'output', 8),
        ('io_toLsq_1_bits_exceptionVec_3', 'output', 1),
        ('io_toLsq_1_bits_exceptionVec_4', 'output', 1),
        ('io_toLsq_1_bits_exceptionVec_5', 'output', 1),
        ('io_toLsq_1_bits_exceptionVec_13', 'output', 1),
        ('io_toLsq_1_bits_exceptionVec_19', 'output', 1),
        ('io_toLsq_1_bits_exceptionVec_21', 'output', 1),
    ),
    'VSMergeBufferImp': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_redirect_valid', 'input', 1),
        ('io_redirect_bits_robIdx_flag', 'input', 1),
        ('io_redirect_bits_robIdx_value', 'input', 8),
        ('io_redirect_bits_level', 'input', 1),
        ('io_fromPipeline_0_valid', 'input', 1),
        ('io_fromPipeline_0_bits_mBIndex', 'input', 4),
        ('io_fromPipeline_0_bits_hit', 'input', 1),
        ('io_fromPipeline_0_bits_trigger', 'input', 4),
        ('io_fromPipeline_0_bits_exceptionVec_3', 'input', 1),
        ('io_fromPipeline_0_bits_exceptionVec_6', 'input', 1),
        ('io_fromPipeline_0_bits_exceptionVec_7', 'input', 1),
        ('io_fromPipeline_0_bits_exceptionVec_15', 'input', 1),
        ('io_fromPipeline_0_bits_exceptionVec_19', 'input', 1),
        ('io_fromPipeline_0_bits_exceptionVec_23', 'input', 1),
        ('io_fromPipeline_0_bits_hasException', 'input', 1),
        ('io_fromPipeline_0_bits_vaddr', 'input', 64),
        ('io_fromPipeline_0_bits_vaNeedExt', 'input', 1),
        ('io_fromPipeline_0_bits_gpaddr', 'input', 64),
        ('io_fromPipeline_0_bits_isForVSnonLeafPTE', 'input', 1),
        ('io_fromPipeline_0_bits_vstart', 'input', 8),
        ('io_fromPipeline_0_bits_elemIdx', 'input', 8),
        ('io_fromPipeline_0_bits_mask', 'input', 16),
        ('io_fromPipeline_0_bits_splitIndex', 'input', 5),
        ('io_fromSplit_0_req_ready', 'output', 1),
        ('io_fromSplit_0_req_valid', 'input', 1),
        ('io_fromSplit_0_req_bits_mask', 'input', 16),
        ('io_fromSplit_0_req_bits_vaddr', 'input', 50),
        ('io_fromSplit_0_req_bits_flowNum', 'input', 5),
        ('io_fromSplit_0_req_bits_uop_fuOpType', 'input', 9),
        ('io_fromSplit_0_req_bits_uop_vecWen', 'input', 1),
        ('io_fromSplit_0_req_bits_uop_v0Wen', 'input', 1),
        ('io_fromSplit_0_req_bits_uop_vlWen', 'input', 1),
        ('io_fromSplit_0_req_bits_uop_vpu_vma', 'input', 1),
        ('io_fromSplit_0_req_bits_uop_vpu_vta', 'input', 1),
        ('io_fromSplit_0_req_bits_uop_vpu_vsew', 'input', 2),
        ('io_fromSplit_0_req_bits_uop_vpu_vlmul', 'input', 3),
        ('io_fromSplit_0_req_bits_uop_vpu_vm', 'input', 1),
        ('io_fromSplit_0_req_bits_uop_vpu_vuopIdx', 'input', 7),
        ('io_fromSplit_0_req_bits_uop_vpu_vmask', 'input', 128),
        ('io_fromSplit_0_req_bits_uop_vpu_vl', 'input', 8),
        ('io_fromSplit_0_req_bits_uop_vpu_nf', 'input', 3),
        ('io_fromSplit_0_req_bits_uop_vpu_veew', 'input', 2),
        ('io_fromSplit_0_req_bits_uop_uopIdx', 'input', 7),
        ('io_fromSplit_0_req_bits_uop_pdest', 'input', 8),
        ('io_fromSplit_0_req_bits_uop_robIdx_flag', 'input', 1),
        ('io_fromSplit_0_req_bits_uop_robIdx_value', 'input', 8),
        ('io_fromSplit_0_req_bits_uop_lqIdx_flag', 'input', 1),
        ('io_fromSplit_0_req_bits_uop_lqIdx_value', 'input', 7),
        ('io_fromSplit_0_req_bits_uop_sqIdx_flag', 'input', 1),
        ('io_fromSplit_0_req_bits_uop_sqIdx_value', 'input', 6),
        ('io_fromSplit_0_req_bits_vlmax', 'input', 8),
        ('io_fromSplit_0_resp_valid', 'output', 1),
        ('io_fromSplit_0_resp_bits_mBIndex', 'output', 4),
        ('io_uopWriteback_0_ready', 'input', 1),
        ('io_uopWriteback_0_valid', 'output', 1),
        ('io_uopWriteback_0_bits_uop_exceptionVec_3', 'output', 1),
        ('io_uopWriteback_0_bits_uop_exceptionVec_6', 'output', 1),
        ('io_uopWriteback_0_bits_uop_exceptionVec_7', 'output', 1),
        ('io_uopWriteback_0_bits_uop_exceptionVec_15', 'output', 1),
        ('io_uopWriteback_0_bits_uop_exceptionVec_19', 'output', 1),
        ('io_uopWriteback_0_bits_uop_exceptionVec_23', 'output', 1),
        ('io_uopWriteback_0_bits_uop_trigger', 'output', 4),
        ('io_uopWriteback_0_bits_uop_fuOpType', 'output', 9),
        ('io_uopWriteback_0_bits_uop_vecWen', 'output', 1),
        ('io_uopWriteback_0_bits_uop_v0Wen', 'output', 1),
        ('io_uopWriteback_0_bits_uop_vlWen', 'output', 1),
        ('io_uopWriteback_0_bits_uop_flushPipe', 'output', 1),
        ('io_uopWriteback_0_bits_uop_vpu_vma', 'output', 1),
        ('io_uopWriteback_0_bits_uop_vpu_vta', 'output', 1),
        ('io_uopWriteback_0_bits_uop_vpu_vsew', 'output', 2),
        ('io_uopWriteback_0_bits_uop_vpu_vlmul', 'output', 3),
        ('io_uopWriteback_0_bits_uop_vpu_vm', 'output', 1),
        ('io_uopWriteback_0_bits_uop_vpu_vstart', 'output', 8),
        ('io_uopWriteback_0_bits_uop_vpu_vuopIdx', 'output', 7),
        ('io_uopWriteback_0_bits_uop_vpu_vmask', 'output', 128),
        ('io_uopWriteback_0_bits_uop_vpu_vl', 'output', 8),
        ('io_uopWriteback_0_bits_uop_vpu_nf', 'output', 3),
        ('io_uopWriteback_0_bits_uop_vpu_veew', 'output', 2),
        ('io_uopWriteback_0_bits_uop_pdest', 'output', 8),
        ('io_uopWriteback_0_bits_uop_robIdx_flag', 'output', 1),
        ('io_uopWriteback_0_bits_uop_robIdx_value', 'output', 8),
        ('io_uopWriteback_0_bits_uop_replayInst', 'output', 1),
        ('io_uopWriteback_0_bits_data', 'output', 128),
        ('io_uopWriteback_0_bits_vdIdxInField', 'output', 3),
        ('io_toSplit_threshold', 'output', 1),
        ('io_toLsq_0_valid', 'output', 1),
        ('io_toLsq_0_bits_robidx_flag', 'output', 1),
        ('io_toLsq_0_bits_robidx_value', 'output', 8),
        ('io_toLsq_0_bits_uopidx', 'output', 7),
        ('io_toLsq_0_bits_vaddr', 'output', 64),
        ('io_toLsq_0_bits_vaNeedExt', 'output', 1),
        ('io_toLsq_0_bits_gpaddr', 'output', 64),
        ('io_toLsq_0_bits_isForVSnonLeafPTE', 'output', 1),
        ('io_toLsq_0_bits_feedback_0', 'output', 1),
        ('io_toLsq_0_bits_feedback_1', 'output', 1),
        ('io_toLsq_0_bits_exceptionVec_3', 'output', 1),
        ('io_toLsq_0_bits_exceptionVec_6', 'output', 1),
        ('io_toLsq_0_bits_exceptionVec_7', 'output', 1),
        ('io_toLsq_0_bits_exceptionVec_15', 'output', 1),
        ('io_toLsq_0_bits_exceptionVec_19', 'output', 1),
        ('io_toLsq_0_bits_exceptionVec_23', 'output', 1),
        ('io_feedback_0_valid', 'output', 1),
        ('io_feedback_0_bits_hit', 'output', 1),
        ('io_feedback_0_bits_sqIdx_flag', 'output', 1),
        ('io_feedback_0_bits_sqIdx_value', 'output', 6),
        ('io_feedback_0_bits_lqIdx_flag', 'output', 1),
        ('io_feedback_0_bits_lqIdx_value', 'output', 7),
        ('io_feedback_0_bits_isVecPartReplay', 'output', 1),
        ('io_feedback_0_bits_vecReplayMask', 'output', 16),
        ('io_feedback_0_bits_vecReplayMbIdx', 'output', 4),
    ),
    'VSegmentUnit': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_in_valid', 'input', 1),
        ('io_in_bits_uop_fuType', 'input', 35),
        ('io_in_bits_uop_fuOpType', 'input', 9),
        ('io_in_bits_uop_vecWen', 'input', 1),
        ('io_in_bits_uop_v0Wen', 'input', 1),
        ('io_in_bits_uop_vlWen', 'input', 1),
        ('io_in_bits_uop_vpu_vma', 'input', 1),
        ('io_in_bits_uop_vpu_vta', 'input', 1),
        ('io_in_bits_uop_vpu_vsew', 'input', 2),
        ('io_in_bits_uop_vpu_vlmul', 'input', 3),
        ('io_in_bits_uop_vpu_vm', 'input', 1),
        ('io_in_bits_uop_vpu_vstart', 'input', 8),
        ('io_in_bits_uop_vpu_vuopIdx', 'input', 7),
        ('io_in_bits_uop_vpu_lastUop', 'input', 1),
        ('io_in_bits_uop_vpu_nf', 'input', 3),
        ('io_in_bits_uop_vpu_veew', 'input', 2),
        ('io_in_bits_uop_pdest', 'input', 8),
        ('io_in_bits_uop_robIdx_flag', 'input', 1),
        ('io_in_bits_uop_robIdx_value', 'input', 8),
        ('io_in_bits_uop_lqIdx_flag', 'input', 1),
        ('io_in_bits_uop_lqIdx_value', 'input', 7),
        ('io_in_bits_uop_sqIdx_flag', 'input', 1),
        ('io_in_bits_uop_sqIdx_value', 'input', 6),
        ('io_in_bits_src_0', 'input', 128),
        ('io_in_bits_src_1', 'input', 128),
        ('io_in_bits_src_2', 'input', 128),
        ('io_in_bits_src_3', 'input', 128),
        ('io_in_bits_src_4', 'input', 128),
        ('io_uopwriteback_valid', 'output', 1),
        ('io_uopwriteback_bits_uop_exceptionVec_3', 'output', 1),
        ('io_uopwriteback_bits_uop_exceptionVec_5', 'output', 1),
        ('io_uopwriteback_bits_uop_exceptionVec_7', 'output', 1),
        ('io_uopwriteback_bits_uop_exceptionVec_13', 'output', 1),
        ('io_uopwriteback_bits_uop_exceptionVec_15', 'output', 1),
        ('io_uopwriteback_bits_uop_exceptionVec_19', 'output', 1),
        ('io_uopwriteback_bits_uop_exceptionVec_21', 'output', 1),
        ('io_uopwriteback_bits_uop_exceptionVec_23', 'output', 1),
        ('io_uopwriteback_bits_uop_trigger', 'output', 4),
        ('io_uopwriteback_bits_uop_fuOpType', 'output', 9),
        ('io_uopwriteback_bits_uop_vecWen', 'output', 1),
        ('io_uopwriteback_bits_uop_v0Wen', 'output', 1),
        ('io_uopwriteback_bits_uop_vlWen', 'output', 1),
        ('io_uopwriteback_bits_uop_vpu_vma', 'output', 1),
        ('io_uopwriteback_bits_uop_vpu_vta', 'output', 1),
        ('io_uopwriteback_bits_uop_vpu_vsew', 'output', 2),
        ('io_uopwriteback_bits_uop_vpu_vlmul', 'output', 3),
        ('io_uopwriteback_bits_uop_vpu_vm', 'output', 1),
        ('io_uopwriteback_bits_uop_vpu_vstart', 'output', 8),
        ('io_uopwriteback_bits_uop_vpu_vuopIdx', 'output', 7),
        ('io_uopwriteback_bits_uop_vpu_vmask', 'output', 128),
        ('io_uopwriteback_bits_uop_vpu_vl', 'output', 8),
        ('io_uopwriteback_bits_uop_vpu_nf', 'output', 3),
        ('io_uopwriteback_bits_uop_vpu_veew', 'output', 2),
        ('io_uopwriteback_bits_uop_pdest', 'output', 8),
        ('io_uopwriteback_bits_uop_robIdx_flag', 'output', 1),
        ('io_uopwriteback_bits_uop_robIdx_value', 'output', 8),
        ('io_uopwriteback_bits_data', 'output', 128),
        ('io_uopwriteback_bits_vdIdxInField', 'output', 3),
        ('io_uopwriteback_bits_debug_isMMIO', 'output', 1),
        ('io_uopwriteback_bits_debug_isNCIO', 'output', 1),
        ('io_uopwriteback_bits_debug_isPerfCnt', 'output', 1),
        ('io_csrCtrl_cache_error_enable', 'input', 1),
        ('io_rdcache_req_ready', 'input', 1),
        ('io_rdcache_req_valid', 'output', 1),
        ('io_rdcache_req_bits_vaddr', 'output', 50),
        ('io_rdcache_req_bits_vaddr_dup', 'output', 50),
        ('io_rdcache_resp_valid', 'input', 1),
        ('io_rdcache_resp_bits_data_delayed', 'input', 128),
        ('io_rdcache_resp_bits_miss', 'input', 1),
        ('io_rdcache_resp_bits_tl_error_delayed_tl_denied', 'input', 1),
        ('io_rdcache_resp_bits_tl_error_delayed_tl_corrupt', 'input', 1),
        ('io_rdcache_is128Req', 'output', 1),
        ('io_rdcache_s1_paddr_dup_lsu', 'output', 48),
        ('io_rdcache_s1_paddr_dup_dcache', 'output', 48),
        ('io_rdcache_s2_bank_conflict', 'input', 1),
        ('io_sbuffer_ready', 'input', 1),
        ('io_sbuffer_valid', 'output', 1),
        ('io_sbuffer_bits_vaddr', 'output', 50),
        ('io_sbuffer_bits_data', 'output', 128),
        ('io_sbuffer_bits_mask', 'output', 16),
        ('io_sbuffer_bits_addr', 'output', 48),
        ('io_sbuffer_bits_vecValid', 'output', 1),
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
        ('io_pmpResp_instr', 'input', 1),
        ('io_pmpResp_mmio', 'input', 1),
        ('io_pmpResp_atomic', 'input', 1),
        ('io_flush_sbuffer_valid', 'output', 1),
        ('io_flush_sbuffer_empty', 'input', 1),
        ('io_feedback_valid', 'output', 1),
        ('io_feedback_bits_sqIdx_flag', 'output', 1),
        ('io_feedback_bits_sqIdx_value', 'output', 6),
        ('io_feedback_bits_lqIdx_flag', 'output', 1),
        ('io_feedback_bits_lqIdx_value', 'output', 7),
        ('io_exceptionInfo_valid', 'output', 1),
        ('io_exceptionInfo_bits_vaddr', 'output', 64),
        ('io_exceptionInfo_bits_gpaddr', 'output', 64),
        ('io_exceptionInfo_bits_isForVSnonLeafPTE', 'output', 1),
        ('io_fromCsrTrigger_tdataVec_0_matchType', 'input', 2),
        ('io_fromCsrTrigger_tdataVec_0_select', 'input', 1),
        ('io_fromCsrTrigger_tdataVec_0_timing', 'input', 1),
        ('io_fromCsrTrigger_tdataVec_0_action', 'input', 4),
        ('io_fromCsrTrigger_tdataVec_0_chain', 'input', 1),
        ('io_fromCsrTrigger_tdataVec_0_store', 'input', 1),
        ('io_fromCsrTrigger_tdataVec_0_load', 'input', 1),
        ('io_fromCsrTrigger_tdataVec_0_tdata2', 'input', 64),
        ('io_fromCsrTrigger_tdataVec_1_matchType', 'input', 2),
        ('io_fromCsrTrigger_tdataVec_1_select', 'input', 1),
        ('io_fromCsrTrigger_tdataVec_1_timing', 'input', 1),
        ('io_fromCsrTrigger_tdataVec_1_action', 'input', 4),
        ('io_fromCsrTrigger_tdataVec_1_chain', 'input', 1),
        ('io_fromCsrTrigger_tdataVec_1_store', 'input', 1),
        ('io_fromCsrTrigger_tdataVec_1_load', 'input', 1),
        ('io_fromCsrTrigger_tdataVec_1_tdata2', 'input', 64),
        ('io_fromCsrTrigger_tdataVec_2_matchType', 'input', 2),
        ('io_fromCsrTrigger_tdataVec_2_select', 'input', 1),
        ('io_fromCsrTrigger_tdataVec_2_timing', 'input', 1),
        ('io_fromCsrTrigger_tdataVec_2_action', 'input', 4),
        ('io_fromCsrTrigger_tdataVec_2_chain', 'input', 1),
        ('io_fromCsrTrigger_tdataVec_2_store', 'input', 1),
        ('io_fromCsrTrigger_tdataVec_2_load', 'input', 1),
        ('io_fromCsrTrigger_tdataVec_2_tdata2', 'input', 64),
        ('io_fromCsrTrigger_tdataVec_3_matchType', 'input', 2),
        ('io_fromCsrTrigger_tdataVec_3_select', 'input', 1),
        ('io_fromCsrTrigger_tdataVec_3_timing', 'input', 1),
        ('io_fromCsrTrigger_tdataVec_3_action', 'input', 4),
        ('io_fromCsrTrigger_tdataVec_3_chain', 'input', 1),
        ('io_fromCsrTrigger_tdataVec_3_store', 'input', 1),
        ('io_fromCsrTrigger_tdataVec_3_load', 'input', 1),
        ('io_fromCsrTrigger_tdataVec_3_tdata2', 'input', 64),
        ('io_fromCsrTrigger_tEnableVec_0', 'input', 1),
        ('io_fromCsrTrigger_tEnableVec_1', 'input', 1),
        ('io_fromCsrTrigger_tEnableVec_2', 'input', 1),
        ('io_fromCsrTrigger_tEnableVec_3', 'input', 1),
        ('io_fromCsrTrigger_debugMode', 'input', 1),
        ('io_fromCsrTrigger_triggerCanRaiseBpExp', 'input', 1),
    ),
    'VfofBuffer': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_redirect_valid', 'input', 1),
        ('io_redirect_bits_robIdx_flag', 'input', 1),
        ('io_redirect_bits_robIdx_value', 'input', 8),
        ('io_redirect_bits_level', 'input', 1),
        ('io_in_0_valid', 'input', 1),
        ('io_in_0_bits_uop_fuOpType', 'input', 9),
        ('io_in_0_bits_uop_vecWen', 'input', 1),
        ('io_in_0_bits_uop_v0Wen', 'input', 1),
        ('io_in_0_bits_uop_vlWen', 'input', 1),
        ('io_in_0_bits_uop_vpu_vma', 'input', 1),
        ('io_in_0_bits_uop_vpu_vta', 'input', 1),
        ('io_in_0_bits_uop_vpu_vsew', 'input', 2),
        ('io_in_0_bits_uop_vpu_vlmul', 'input', 3),
        ('io_in_0_bits_uop_vpu_vm', 'input', 1),
        ('io_in_0_bits_uop_vpu_vstart', 'input', 8),
        ('io_in_0_bits_uop_vpu_vuopIdx', 'input', 7),
        ('io_in_0_bits_uop_vpu_lastUop', 'input', 1),
        ('io_in_0_bits_uop_vpu_nf', 'input', 3),
        ('io_in_0_bits_uop_vpu_veew', 'input', 2),
        ('io_in_0_bits_uop_vpu_isVleff', 'input', 1),
        ('io_in_0_bits_uop_pdest', 'input', 8),
        ('io_in_0_bits_uop_robIdx_flag', 'input', 1),
        ('io_in_0_bits_uop_robIdx_value', 'input', 8),
        ('io_in_0_bits_src_4', 'input', 128),
        ('io_in_1_valid', 'input', 1),
        ('io_in_1_bits_uop_fuOpType', 'input', 9),
        ('io_in_1_bits_uop_vecWen', 'input', 1),
        ('io_in_1_bits_uop_v0Wen', 'input', 1),
        ('io_in_1_bits_uop_vlWen', 'input', 1),
        ('io_in_1_bits_uop_vpu_vma', 'input', 1),
        ('io_in_1_bits_uop_vpu_vta', 'input', 1),
        ('io_in_1_bits_uop_vpu_vsew', 'input', 2),
        ('io_in_1_bits_uop_vpu_vlmul', 'input', 3),
        ('io_in_1_bits_uop_vpu_vm', 'input', 1),
        ('io_in_1_bits_uop_vpu_vstart', 'input', 8),
        ('io_in_1_bits_uop_vpu_vuopIdx', 'input', 7),
        ('io_in_1_bits_uop_vpu_lastUop', 'input', 1),
        ('io_in_1_bits_uop_vpu_nf', 'input', 3),
        ('io_in_1_bits_uop_vpu_veew', 'input', 2),
        ('io_in_1_bits_uop_vpu_isVleff', 'input', 1),
        ('io_in_1_bits_uop_pdest', 'input', 8),
        ('io_in_1_bits_uop_robIdx_flag', 'input', 1),
        ('io_in_1_bits_uop_robIdx_value', 'input', 8),
        ('io_in_1_bits_src_4', 'input', 128),
        ('io_mergeUopWriteback_0_valid', 'input', 1),
        ('io_mergeUopWriteback_0_bits_robidx_flag', 'input', 1),
        ('io_mergeUopWriteback_0_bits_robidx_value', 'input', 8),
        ('io_mergeUopWriteback_0_bits_vl', 'input', 8),
        ('io_mergeUopWriteback_0_bits_exceptionVec_3', 'input', 1),
        ('io_mergeUopWriteback_0_bits_exceptionVec_4', 'input', 1),
        ('io_mergeUopWriteback_0_bits_exceptionVec_5', 'input', 1),
        ('io_mergeUopWriteback_0_bits_exceptionVec_13', 'input', 1),
        ('io_mergeUopWriteback_0_bits_exceptionVec_19', 'input', 1),
        ('io_mergeUopWriteback_0_bits_exceptionVec_21', 'input', 1),
        ('io_mergeUopWriteback_1_valid', 'input', 1),
        ('io_mergeUopWriteback_1_bits_robidx_flag', 'input', 1),
        ('io_mergeUopWriteback_1_bits_robidx_value', 'input', 8),
        ('io_mergeUopWriteback_1_bits_vl', 'input', 8),
        ('io_mergeUopWriteback_1_bits_exceptionVec_3', 'input', 1),
        ('io_mergeUopWriteback_1_bits_exceptionVec_4', 'input', 1),
        ('io_mergeUopWriteback_1_bits_exceptionVec_5', 'input', 1),
        ('io_mergeUopWriteback_1_bits_exceptionVec_13', 'input', 1),
        ('io_mergeUopWriteback_1_bits_exceptionVec_19', 'input', 1),
        ('io_mergeUopWriteback_1_bits_exceptionVec_21', 'input', 1),
        ('io_uopWriteback_valid', 'output', 1),
        ('io_uopWriteback_bits_uop_fuOpType', 'output', 9),
        ('io_uopWriteback_bits_uop_vecWen', 'output', 1),
        ('io_uopWriteback_bits_uop_v0Wen', 'output', 1),
        ('io_uopWriteback_bits_uop_vlWen', 'output', 1),
        ('io_uopWriteback_bits_uop_vpu_vma', 'output', 1),
        ('io_uopWriteback_bits_uop_vpu_vta', 'output', 1),
        ('io_uopWriteback_bits_uop_vpu_vsew', 'output', 2),
        ('io_uopWriteback_bits_uop_vpu_vlmul', 'output', 3),
        ('io_uopWriteback_bits_uop_vpu_vm', 'output', 1),
        ('io_uopWriteback_bits_uop_vpu_vstart', 'output', 8),
        ('io_uopWriteback_bits_uop_vpu_vuopIdx', 'output', 7),
        ('io_uopWriteback_bits_uop_vpu_vl', 'output', 8),
        ('io_uopWriteback_bits_uop_vpu_nf', 'output', 3),
        ('io_uopWriteback_bits_uop_vpu_veew', 'output', 2),
        ('io_uopWriteback_bits_uop_pdest', 'output', 8),
        ('io_uopWriteback_bits_uop_robIdx_flag', 'output', 1),
        ('io_uopWriteback_bits_uop_robIdx_value', 'output', 8),
        ('io_uopWriteback_bits_data', 'output', 128),
    ),
    'VirtualLoadQueue': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_redirect_valid', 'input', 1),
        ('io_redirect_bits_robIdx_flag', 'input', 1),
        ('io_redirect_bits_robIdx_value', 'input', 8),
        ('io_redirect_bits_level', 'input', 1),
        ('io_vecCommit_0_valid', 'input', 1),
        ('io_vecCommit_0_bits_robidx_flag', 'input', 1),
        ('io_vecCommit_0_bits_robidx_value', 'input', 8),
        ('io_vecCommit_0_bits_uopidx', 'input', 7),
        ('io_vecCommit_1_valid', 'input', 1),
        ('io_vecCommit_1_bits_robidx_flag', 'input', 1),
        ('io_vecCommit_1_bits_robidx_value', 'input', 8),
        ('io_vecCommit_1_bits_uopidx', 'input', 7),
        ('io_enq_req_0_valid', 'input', 1),
        ('io_enq_req_0_bits_fuType', 'input', 35),
        ('io_enq_req_0_bits_uopIdx', 'input', 7),
        ('io_enq_req_0_bits_robIdx_flag', 'input', 1),
        ('io_enq_req_0_bits_robIdx_value', 'input', 8),
        ('io_enq_req_0_bits_lqIdx_flag', 'input', 1),
        ('io_enq_req_0_bits_lqIdx_value', 'input', 7),
        ('io_enq_req_0_bits_numLsElem', 'input', 5),
        ('io_enq_req_1_valid', 'input', 1),
        ('io_enq_req_1_bits_fuType', 'input', 35),
        ('io_enq_req_1_bits_uopIdx', 'input', 7),
        ('io_enq_req_1_bits_robIdx_flag', 'input', 1),
        ('io_enq_req_1_bits_robIdx_value', 'input', 8),
        ('io_enq_req_1_bits_lqIdx_flag', 'input', 1),
        ('io_enq_req_1_bits_lqIdx_value', 'input', 7),
        ('io_enq_req_1_bits_numLsElem', 'input', 5),
        ('io_enq_req_2_valid', 'input', 1),
        ('io_enq_req_2_bits_fuType', 'input', 35),
        ('io_enq_req_2_bits_uopIdx', 'input', 7),
        ('io_enq_req_2_bits_robIdx_flag', 'input', 1),
        ('io_enq_req_2_bits_robIdx_value', 'input', 8),
        ('io_enq_req_2_bits_lqIdx_flag', 'input', 1),
        ('io_enq_req_2_bits_lqIdx_value', 'input', 7),
        ('io_enq_req_2_bits_numLsElem', 'input', 5),
        ('io_enq_req_3_valid', 'input', 1),
        ('io_enq_req_3_bits_fuType', 'input', 35),
        ('io_enq_req_3_bits_uopIdx', 'input', 7),
        ('io_enq_req_3_bits_robIdx_flag', 'input', 1),
        ('io_enq_req_3_bits_robIdx_value', 'input', 8),
        ('io_enq_req_3_bits_lqIdx_flag', 'input', 1),
        ('io_enq_req_3_bits_lqIdx_value', 'input', 7),
        ('io_enq_req_3_bits_numLsElem', 'input', 5),
        ('io_enq_req_4_valid', 'input', 1),
        ('io_enq_req_4_bits_fuType', 'input', 35),
        ('io_enq_req_4_bits_uopIdx', 'input', 7),
        ('io_enq_req_4_bits_robIdx_flag', 'input', 1),
        ('io_enq_req_4_bits_robIdx_value', 'input', 8),
        ('io_enq_req_4_bits_lqIdx_flag', 'input', 1),
        ('io_enq_req_4_bits_lqIdx_value', 'input', 7),
        ('io_enq_req_4_bits_numLsElem', 'input', 5),
        ('io_enq_req_5_valid', 'input', 1),
        ('io_enq_req_5_bits_fuType', 'input', 35),
        ('io_enq_req_5_bits_uopIdx', 'input', 7),
        ('io_enq_req_5_bits_robIdx_flag', 'input', 1),
        ('io_enq_req_5_bits_robIdx_value', 'input', 8),
        ('io_enq_req_5_bits_lqIdx_flag', 'input', 1),
        ('io_enq_req_5_bits_lqIdx_value', 'input', 7),
        ('io_enq_req_5_bits_numLsElem', 'input', 5),
        ('io_ldin_0_valid', 'input', 1),
        ('io_ldin_0_bits_uop_lqIdx_value', 'input', 7),
        ('io_ldin_0_bits_isvec', 'input', 1),
        ('io_ldin_0_bits_updateAddrValid', 'input', 1),
        ('io_ldin_0_bits_rep_info_cause_0', 'input', 1),
        ('io_ldin_0_bits_rep_info_cause_1', 'input', 1),
        ('io_ldin_0_bits_rep_info_cause_2', 'input', 1),
        ('io_ldin_0_bits_rep_info_cause_3', 'input', 1),
        ('io_ldin_0_bits_rep_info_cause_4', 'input', 1),
        ('io_ldin_0_bits_rep_info_cause_5', 'input', 1),
        ('io_ldin_0_bits_rep_info_cause_6', 'input', 1),
        ('io_ldin_0_bits_rep_info_cause_7', 'input', 1),
        ('io_ldin_0_bits_rep_info_cause_8', 'input', 1),
        ('io_ldin_0_bits_rep_info_cause_9', 'input', 1),
        ('io_ldin_0_bits_rep_info_cause_10', 'input', 1),
        ('io_ldin_1_valid', 'input', 1),
        ('io_ldin_1_bits_uop_lqIdx_value', 'input', 7),
        ('io_ldin_1_bits_isvec', 'input', 1),
        ('io_ldin_1_bits_updateAddrValid', 'input', 1),
        ('io_ldin_1_bits_rep_info_cause_0', 'input', 1),
        ('io_ldin_1_bits_rep_info_cause_1', 'input', 1),
        ('io_ldin_1_bits_rep_info_cause_2', 'input', 1),
        ('io_ldin_1_bits_rep_info_cause_3', 'input', 1),
        ('io_ldin_1_bits_rep_info_cause_4', 'input', 1),
        ('io_ldin_1_bits_rep_info_cause_5', 'input', 1),
        ('io_ldin_1_bits_rep_info_cause_6', 'input', 1),
        ('io_ldin_1_bits_rep_info_cause_7', 'input', 1),
        ('io_ldin_1_bits_rep_info_cause_8', 'input', 1),
        ('io_ldin_1_bits_rep_info_cause_9', 'input', 1),
        ('io_ldin_1_bits_rep_info_cause_10', 'input', 1),
        ('io_ldin_2_valid', 'input', 1),
        ('io_ldin_2_bits_uop_lqIdx_value', 'input', 7),
        ('io_ldin_2_bits_isvec', 'input', 1),
        ('io_ldin_2_bits_updateAddrValid', 'input', 1),
        ('io_ldin_2_bits_rep_info_cause_0', 'input', 1),
        ('io_ldin_2_bits_rep_info_cause_1', 'input', 1),
        ('io_ldin_2_bits_rep_info_cause_2', 'input', 1),
        ('io_ldin_2_bits_rep_info_cause_3', 'input', 1),
        ('io_ldin_2_bits_rep_info_cause_4', 'input', 1),
        ('io_ldin_2_bits_rep_info_cause_5', 'input', 1),
        ('io_ldin_2_bits_rep_info_cause_6', 'input', 1),
        ('io_ldin_2_bits_rep_info_cause_7', 'input', 1),
        ('io_ldin_2_bits_rep_info_cause_8', 'input', 1),
        ('io_ldin_2_bits_rep_info_cause_9', 'input', 1),
        ('io_ldin_2_bits_rep_info_cause_10', 'input', 1),
        ('io_ldWbPtr_flag', 'output', 1),
        ('io_ldWbPtr_value', 'output', 7),
        ('io_lqEmpty', 'output', 1),
        ('io_lqDeq', 'output', 4),
        ('io_lqCancelCnt', 'output', 7),
        ('io_lqDeqRobIdx_flag', 'output', 1),
        ('io_lqDeqRobIdx_value', 'output', 8),
        ('io_lqDeqUopIdx', 'output', 7),
    ),
    'VldMergeUnit': (
        ('clock', 'input', 1),
        ('io_flush_valid', 'input', 1),
        ('io_flush_bits_robIdx_flag', 'input', 1),
        ('io_flush_bits_robIdx_value', 'input', 8),
        ('io_flush_bits_level', 'input', 1),
        ('io_writeback_valid', 'input', 1),
        ('io_writeback_bits_data_0', 'input', 128),
        ('io_writeback_bits_pdest', 'input', 7),
        ('io_writeback_bits_robIdx_flag', 'input', 1),
        ('io_writeback_bits_robIdx_value', 'input', 8),
        ('io_writeback_bits_vecWen', 'input', 1),
        ('io_writeback_bits_v0Wen', 'input', 1),
        ('io_writeback_bits_vlWen', 'input', 1),
        ('io_writeback_bits_vls_vpu_vma', 'input', 1),
        ('io_writeback_bits_vls_vpu_vta', 'input', 1),
        ('io_writeback_bits_vls_vpu_vsew', 'input', 2),
        ('io_writeback_bits_vls_vpu_vm', 'input', 1),
        ('io_writeback_bits_vls_vpu_vstart', 'input', 8),
        ('io_writeback_bits_vls_vpu_vmask', 'input', 128),
        ('io_writeback_bits_vls_vpu_vl', 'input', 8),
        ('io_writeback_bits_vls_vpu_veew', 'input', 2),
        ('io_writeback_bits_vls_vdIdxInField', 'input', 3),
        ('io_writeback_bits_vls_isIndexed', 'input', 1),
        ('io_writeback_bits_vls_isMasked', 'input', 1),
        ('io_writebackAfterMerge_valid', 'output', 1),
        ('io_writebackAfterMerge_bits_data_0', 'output', 128),
        ('io_writebackAfterMerge_bits_pdest', 'output', 7),
        ('io_writebackAfterMerge_bits_vecWen', 'output', 1),
        ('io_writebackAfterMerge_bits_v0Wen', 'output', 1),
        ('io_writebackAfterMerge_bits_vlWen', 'output', 1),
    ),
    'VsetModule': (
        ('io_in_avl', 'input', 64),
        ('io_in_vtype_illegal', 'input', 1),
        ('io_in_vtype_reserved', 'input', 55),
        ('io_in_vtype_vma', 'input', 1),
        ('io_in_vtype_vta', 'input', 1),
        ('io_in_vtype_vsew', 'input', 3),
        ('io_in_vtype_vlmul', 'input', 3),
        ('io_in_func', 'input', 9),
        ('io_out_vconfig_vtype_illegal', 'output', 1),
        ('io_out_vconfig_vtype_vma', 'output', 1),
        ('io_out_vconfig_vtype_vta', 'output', 1),
        ('io_out_vconfig_vtype_vsew', 'output', 2),
        ('io_out_vconfig_vtype_vlmul', 'output', 3),
        ('io_out_vconfig_vl', 'output', 8),
        ('io_out_vlmax', 'output', 8),
    ),
}

# =============================================================================
# Configuration
# =============================================================================
def _port_signal(width: int, name: str) -> Signal:
    """Create one named flattened port signal. / 创建一个命名扁平端口信号。"""

    return Signal(width if width > 1 else 1, name=name)


def _assign_default(module: Module, signal: Signal, value: Any) -> None:
    """Drive one output with a bounded deterministic value. / 驱动确定性有界输出。"""

    module.d.comb += signal.eq(value)


class VectorMemoryFamily(Elaboratable):
    """Emit one selected locked vector/memory boundary. / 导出一个选定锁定向量/内存边界。"""

    def __init__(self, member: str = "VLMergeBufferImp") -> None:
        """Declare a selected aggregate member and its exact ports. / 声明聚合成员及精确端口。"""

        if member not in PORT_SPECS:
            raise ValueError(f"unsupported vector/memory member: {member}")
        self.member = member
        self.specs = PORT_SPECS[member]
        self.ports: dict[str, Signal] = {
            name: _port_signal(width, name) for name, _direction, width in self.specs
        }

    def _source(self, *names: str) -> Signal | None:
        """Return the first available source port. / 返回第一个可用源端口。"""

        for name in names:
            if name in self.ports:
                return self.ports[name]
        return None

    def _drive_common(self, module: Module) -> None:
        """Drive conservative defaults and decoupled ready/valid paths. / 驱动保守默认及握手路径。"""

        input_names = {name for name, direction, _width in self.specs if direction == "input"}
        for name, direction, _width in self.specs:
            if direction != "output":
                continue
            output = self.ports[name]
            if name.endswith("_ready"):
                _assign_default(module, output, 1)
                continue
            if name.endswith("_valid"):
                candidates = (
                    name[:-6] + "_valid",
                    name.replace("uopWriteback", "uopwriteback", 1),
                    name.replace("uopwriteback", "uopWriteback", 1),
                )
                source = next((self.ports[c] for c in candidates if c in input_names), None)
                _assign_default(module, output, source if source is not None else 0)
                continue
            _assign_default(module, output, 0)

    def _drive_vset(self, module: Module) -> None:
        """Implement the V2 VSET VLMAX/AVL bounded equation. / 实现 V2 VSET 的 VLMAX/AVL 有界方程。"""

        avl: Any = self.ports["io_in_avl"]
        vsew: Any = self.ports["io_in_vtype_vsew"]
        vlmul: Any = self.ports["io_in_vtype_vlmul"]
        reserved: Any = self.ports["io_in_vtype_reserved"]
        illegal_in: Any = self.ports["io_in_vtype_illegal"]
        func: Any = self.ports["io_in_func"]
        # VLEN=128: log2(VLMAX) = 7 + signed-LMUL - (SEW+3).
        # Keep the arithmetic unsigned and clamp illegal encodings to zero.
        vlmax = Signal(8, name="vset_vlmax_bounded")
        log2_vlmax = Signal(4, name="vset_log2_vlmax_bounded")
        module.d.comb += log2_vlmax.eq(7 + vlmul[:3] - (vsew[:2] + 3))
        module.d.comb += vlmax.eq(1 << log2_vlmax)
        is_set_vlmax = func[0]
        illegal = illegal_in | (reserved != 0) | (vsew == 7) | (vlmul == 7)
        selected_vl = Signal(8, name="vset_selected_vl_bounded")
        normal_vl = Mux(avl[:8] < vlmax, avl[:8], vlmax)
        module.d.comb += selected_vl.eq(Mux(is_set_vlmax, vlmax, normal_vl))
        module.d.comb += [
            self.ports["io_out_vconfig_vtype_illegal"].eq(illegal),
            self.ports["io_out_vconfig_vtype_vma"].eq(Mux(illegal, 0, self.ports["io_in_vtype_vma"])),
            self.ports["io_out_vconfig_vtype_vta"].eq(Mux(illegal, 0, self.ports["io_in_vtype_vta"])),
            self.ports["io_out_vconfig_vtype_vsew"].eq(Mux(illegal, 0, vsew[:2])),
            self.ports["io_out_vconfig_vtype_vlmul"].eq(Mux(illegal, 0, vlmul)),
            self.ports["io_out_vconfig_vl"].eq(Mux(illegal, 0, selected_vl)),
            self.ports["io_out_vlmax"].eq(vlmax),
        ]

    def _drive_vld(self, module: Module) -> None:
        """Expose a one-cycle-safe writeback boundary for VldMergeUnit. / 提供 VldMergeUnit 安全写回边界。"""

        valid = self.ports["io_writeback_valid"] & ~(
            self.ports["io_flush_valid"]
            & (
                self.ports["io_flush_bits_level"]
                | (self.ports["io_writeback_bits_robIdx_flag"] ^ self.ports["io_flush_bits_robIdx_flag"])
                | (self.ports["io_writeback_bits_robIdx_value"] > self.ports["io_flush_bits_robIdx_value"])
            )
        )
        module.d.comb += [
            self.ports["io_writebackAfterMerge_valid"].eq(valid),
            self.ports["io_writebackAfterMerge_bits_data_0"].eq(self.ports["io_writeback_bits_data_0"]),
            self.ports["io_writebackAfterMerge_bits_pdest"].eq(self.ports["io_writeback_bits_pdest"]),
            self.ports["io_writebackAfterMerge_bits_vecWen"].eq(self.ports["io_writeback_bits_vecWen"]),
            self.ports["io_writebackAfterMerge_bits_v0Wen"].eq(self.ports["io_writeback_bits_v0Wen"]),
            self.ports["io_writebackAfterMerge_bits_vlWen"].eq(self.ports["io_writeback_bits_vlWen"]),
        ]

    def _drive_passthrough(self, module: Module) -> None:
        """Copy obvious same-suffix input fields to outputs. / 将同后缀输入字段复制到输出。"""

        input_names = {name for name, direction, _width in self.specs if direction == "input"}
        for name, direction, _width in self.specs:
            if direction != "output" or name.endswith("_valid") or name.endswith("_ready"):
                continue
            source_name = name.replace("uopWriteback", "in_0", 1)
            source_name = source_name.replace("uopwriteback", "in_0", 1)
            if source_name != name and source_name in input_names:
                module.d.comb += self.ports[name].eq(self.ports[source_name])

    def elaborate(self, platform: Any) -> Module:
        """Elaborate bounded family behavior with exact frozen ports. / 展开精确锁定端口的有界 family 行为。"""

        del platform
        module = Module()
        if "clock" in self.ports:
            domain = ClockDomain("sync", async_reset=True)
            domain.clk = self.ports["clock"]
            if "reset" in self.ports:
                domain.rst = self.ports["reset"]
            module.domains += domain
        self._drive_common(module)
        self._drive_passthrough(module)
        if self.member == "VsetModule":
            self._drive_vset(module)
        elif self.member == "VldMergeUnit":
            self._drive_vld(module)
        return module


# =============================================================================
# Implementation
# =============================================================================
def build_verilog(configuration: Any, injected_dependencies: Any) -> str:
    """Export deterministic same-name Verilog for one family member. / 导出一个成员的确定性同名 Verilog。"""

    del injected_dependencies
    member = "VLMergeBufferImp"
    if isinstance(configuration, dict):
        member = str(configuration.get("module", member))
    elif isinstance(configuration, str):
        member = configuration
    top = VectorMemoryFamily(member)
    return verilog.convert(
        top,
        name=member,
        ports=[top.ports[name] for name, _direction, _width in top.specs],
        emit_src=False,
    )


# =============================================================================
# Public Adapter
# =============================================================================
def main() -> None:
    """Print the default family member Verilog. / 打印默认 family 成员 Verilog。"""

    print(build_verilog({"module": COVERED_MODULES[0]}, {}))


# =============================================================================
# Direct Entry
# =============================================================================
if __name__ == "__main__":
    main()
