"""Elastic pipelines, queue adapters, and registered connect stages."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Callable, Literal, Mapping, TypeAlias, cast

from amaranth import Array, Assert, Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal, Value
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
__all__ = [
    "PortSpec",
    "ElasticMemberConfiguration",
    "ConnectMemberConfiguration",
    "SourcePipelineConfiguration",
    "ValidInterface",
    "CreditedDelay",
    "SourcePipeline",
    "PipelineFamily",
    "SOURCE_PIPELINE_MEMBERS",
    "COVERED_MODULES",
    "IMPLEMENTED_MEMBERS",
    "CONTRACT_ONLY_MEMBERS",
    "family_configuration",
    "build_verilog",
    "main",
]
COVERED_MODULES: tuple[str, ...] = (
    "Pipeline", "Pipeline_1", "Pipeline_2", "Pipeline_3",
    "Pipeline_12", "Pipeline_13", "Pipeline_14", "Pipeline_15",
    "Pipeline_16", "Pipeline_17", "Pipeline_18", "Pipeline_19",
    "Pipeline_20", "Pipeline_45", "Pipeline_49", "Pipeline_53",
    "NewPipelineConnectPipe_1", "NewPipelineConnectPipe_5",
    "NewPipelineConnectPipe_7", "NewPipelineConnectPipe_8",
    "NewPipelineConnectPipe_9", "NewPipelineConnectPipe_10",
    "NewPipelineConnectPipe_13", "NewPipelineConnectPipe_14",
    "NewPipelineConnectPipe_16", "NewPipelineConnectPipe_18",
    "NewPipelineConnectPipe_20", "NewPipelineConnectPipe_23",
    "NewPipelineConnectPipe_25", "NewPipelineConnectPipe_27",
    "NewPipelineConnectPipe_29", "NewPipelineConnectPipe_33",
    "NewPipelineConnectPipe_34", "NewPipelineConnectPipe_35",
    "Queue1_ClientDirWrite", "Queue1_ClientTagWrite", "Queue1_CtrlReq",
    "Queue1_CtrlResp", "Queue1_EccInfo", "Queue1_L1PrefetchReq",
    "Queue1_MSHRRequest", "Queue1_PipeInfo", "Queue1_PrefetchReq",
    "Queue1_PrefetchReq_1", "Queue1_PrefetchResp",
    "Queue1_PrefetchResp_4", "Queue1_PrefetchTrain",
    "Queue1_PrefetchTrain_4", "Queue1_SelfDirWrite",
    "Queue1_SelfTagWrite",
)
SOURCE_PIPELINE_MEMBERS: tuple[str, ...] = (
    "Pipe", "LatencyPipe", "Broadcaster", "Repeater", "ShiftQueue",
    "ReorderQueue", "MultiWidthFifo", "CreditedIOCounter",
    "CreditedIOPipeline", "CreditedIOSender", "CreditedIOReceiver",
)
COVERED_MODULES += SOURCE_PIPELINE_MEMBERS
IMPLEMENTED_MEMBERS: tuple[str, ...] = COVERED_MODULES
CONTRACT_ONLY_MEMBERS: tuple[str, ...] = ()


# =============================================================================
# Configuration
# =============================================================================
PortDirection: TypeAlias = Literal["input", "output"]
FieldProfile: TypeAlias = tuple[tuple[str, int], ...]
ConstantProfile: TypeAlias = tuple[tuple[str, int], ...]
ElasticProfileRow: TypeAlias = tuple[
    str, int, bool, FieldProfile, FieldProfile, ConstantProfile
]
ConnectProfileRow: TypeAlias = tuple[
    str, bool, bool, bool, bool, FieldProfile
]


@dataclass(frozen=True)
class PortSpec:
    """One exact flattened input or output port. / 一个精确展开的输入或输出端口。"""

    name: str
    direction: PortDirection
    width: int


@dataclass(frozen=True)
class ElasticMemberConfiguration:
    """A finite one-entry queue chain with exact payload and public port shape."""

    member_name: str
    stage_count: int
    input_ready_name: str | None
    input_fields: FieldProfile
    output_fields: FieldProfile
    output_constants: ConstantProfile
    input_valid_name: str
    output_valid_name: str
    output_ready_name: str
    input_prefix: str
    output_prefix: str


@dataclass(frozen=True)
class ConnectMemberConfiguration:
    """One registered connect stage with its exact retained control ports."""

    member_name: str
    payload_fields: FieldProfile
    exposes_input_ready: bool
    exposes_output_ready: bool
    exposes_flush: bool
    exposes_older: bool


@dataclass(frozen=True)
class SourcePipelineConfiguration:
    """Geometry and compile-time flow choices for reusable queue adapters."""

    member_name: str = "Pipe"
    width: int = 32
    latency: int = 1
    entries: int = 4
    targets: int = 3
    tag_width: int = 3
    reorder_size: int | None = None
    input_width: int = 16
    output_width: int = 8
    pipe: bool | None = None
    flow: bool | None = None
    debit_delay: int = 1
    credit_delay: int = 1
    initial_credits: int | None = None
    async_reset: bool = False

    def __post_init__(self) -> None:
        if self.member_name not in SOURCE_PIPELINE_MEMBERS:
            raise ValueError("unsupported pipeline adapter")
        if self.pipe is None:
            object.__setattr__(self, "pipe", self.member_name == "CreditedIOSender")
        if self.flow is None:
            object.__setattr__(self, "flow", self.member_name == "CreditedIOReceiver")
        minimum_entries = 0 if self.member_name == "CreditedIOCounter" else 1
        if self.width < 0 or self.entries < minimum_entries or self.targets < 1:
            raise ValueError("invalid payload width, queue depth, or fanout")
        if self.member_name == "Pipe" and self.latency < 0:
            raise ValueError("a valid pipeline requires nonnegative latency")
        if self.tag_width < 0 or (self.reorder_size is not None and self.reorder_size < 1):
            raise ValueError("invalid reorder geometry")
        if min(self.input_width, self.output_width) < 0 or (
            self.input_width != self.output_width and min(self.input_width, self.output_width) == 0
        ):
            raise ValueError("invalid FIFO width ratio")
        if self.member_name == "MultiWidthFifo":
            larger, smaller = max(self.input_width, self.output_width), min(self.input_width, self.output_width)
            if larger != smaller and larger % smaller:
                raise ValueError("FIFO widths must have an integral ratio")
            if self.input_width > self.output_width and self.entries % (larger // smaller):
                raise ValueError("output capacity must be divisible by the split beat count")
        if self.debit_delay < 0 or self.credit_delay < 0:
            raise ValueError("credit link delays must be nonnegative")
        if self.initial_credits is not None and not 0 <= self.initial_credits <= self.entries:
            raise ValueError("initial credit count must fit the link capacity")


@dataclass(frozen=True)
class CreditedDelay:
    debit: int
    credit: int

    def __post_init__(self) -> None:
        if self.debit < 0 or self.credit < 0:
            raise ValueError("credit link delays must be nonnegative")

    @property
    def total(self) -> int:
        return self.debit + self.credit

    def flip(self) -> CreditedDelay:
        return CreditedDelay(self.credit, self.debit)

    def __add__(self, other: CreditedDelay) -> CreditedDelay:
        return CreditedDelay(self.debit + other.debit, self.credit + other.credit)

    def __str__(self) -> str:
        return f"{self.debit}:{self.credit}"


# The compact field/width profiles are used by the equations below. They hold
# only executable interface geometry and constants; no source or HDL is loaded.
PIPELINE_PROFILE_ROWS: tuple[tuple[str, int, bool, tuple[tuple[str, int], ...], tuple[tuple[str, int], ...], tuple[tuple[str, int], ...]], ...] = (
    ('Pipeline', 1, True,
     (('paddr', 48), ('alias', 2), ('confidence', 1), ('is_store', 1), ('pf_source_value', 3)),
     (('paddr', 48), ('alias', 2), ('confidence', 1), ('is_store', 1), ('pf_source_value', 3)), ()),
    ('Pipeline_1', 1, True,
     (('tag', 33), ('set', 9), ('vaddr', 44), ('needT', 1), ('source', 7), ('pfSource', 5)),
     (('tag', 33), ('set', 9), ('vaddr', 44), ('needT', 1), ('source', 7), ('pfSource', 5)), ()),
    ('Pipeline_2', 1, False,
     (('tag', 33), ('set', 9), ('needT', 1), ('source', 7), ('vaddr', 44), ('hit', 1),
      ('prefetched', 1), ('pfsource', 3), ('reqsource', 5)),
     (('tag', 33), ('set', 9), ('needT', 1), ('source', 7), ('vaddr', 44), ('reqsource', 5)), ()),
    ('Pipeline_3', 1, True, (), (), ()),
    ('Pipeline_12', 1, True, (('tag', 30), ('set', 12), ('pfSource', 5)),
     (('tag', 30), ('set', 12), ('needT', 1), ('source', 11), ('pfSource', 5)),
     (('needT', 0), ('source', 0))),
    ('Pipeline_13', 4, True,
     (('counter', 1), ('beat', 1), ('last', 1), ('needPb', 1), ('need_d', 1), ('isReleaseAck', 1),
      ('req_sourceId', 11), ('req_set', 12), ('req_tag', 28), ('req_channel', 3), ('req_opcode', 3),
      ('req_param', 3), ('req_size', 3), ('req_way', 4), ('req_off', 6), ('req_useBypass', 1),
      ('req_bufIdx', 4), ('req_denied', 1), ('req_sinkId', 4), ('req_bypassPut', 1),
      ('req_dirty', 1), ('req_isHit', 1)),
     (('counter', 1), ('beat', 1), ('last', 1), ('needPb', 1), ('isReleaseAck', 1),
      ('req_sourceId', 11), ('req_set', 12), ('req_channel', 3), ('req_opcode', 3),
      ('req_param', 3), ('req_size', 3), ('req_way', 4), ('req_denied', 1), ('req_sinkId', 4),
      ('req_bypassPut', 1), ('req_dirty', 1)),
     ()),
    ('Pipeline_14', 1, True, (('param', 3), ('set', 12), ('tag', 28)),
     (('channel', 3), ('opcode', 3), ('param', 3), ('size', 3), ('source', 11), ('set', 12),
      ('tag', 28), ('off', 6), ('mask', 32), ('bufIdx', 4), ('needHint', 1), ('isPrefetch', 1),
      ('isBop', 1), ('preferCache', 1), ('dirty', 1), ('fromProbeHelper', 1), ('fromCmoHelper', 1),
      ('needProbeAckData', 1), ('reqSource', 5)),
     (('channel', 4), ('opcode', 0), ('size', 6), ('source', 0), ('off', 0), ('mask', 0),
      ('bufIdx', 0), ('needHint', 0), ('isPrefetch', 0), ('isBop', 0), ('preferCache', 0),
      ('dirty', 0), ('fromProbeHelper', 0), ('fromCmoHelper', 1), ('needProbeAckData', 0),
      ('reqSource', 0))),
    ('Pipeline_15', 1, True,
     (('set', 12), ('way', 4), ('data_dirty', 1), ('data_state', 2), ('data_clientStates_0', 2),
      ('data_prefetch', 1)),
     (('set', 12), ('way', 4), ('data_dirty', 1), ('data_state', 2), ('data_clientStates_0', 2),
      ('data_prefetch', 1)),
     ()),
    ('Pipeline_16', 1, True, (('set', 12), ('way', 4), ('tag', 28)),
     (('set', 12), ('way', 4), ('tag', 28)), ()),
    ('Pipeline_17', 1, True, (('set', 10), ('way', 4), ('data_0_state', 2)),
     (('set', 10), ('way', 4), ('data_0_state', 2)), ()),
    ('Pipeline_18', 1, True, (('set', 10), ('way', 4), ('tag', 30)),
     (('set', 10), ('way', 4), ('tag', 30)), ()),
    ('Pipeline_19', 1, True, (), (), ()),
    ('Pipeline_20', 1, True, (), (), ()),
    ('Pipeline_45', 2, False, (('errCode', 8), ('addr', 64)), (('errCode', 8), ('addr', 64)), ()),
    ('Pipeline_49', 2, True,
     (('cmd', 8), ('data_0', 64), ('data_1', 64), ('data_2', 64), ('data_3', 64), ('data_4', 64),
      ('data_5', 64), ('data_6', 64), ('data_7', 64), ('set', 64), ('tag', 64), ('way', 64),
      ('dir', 64)),
     (('cmd', 8), ('data_0', 64), ('data_1', 64), ('data_2', 64), ('data_3', 64), ('data_4', 64),
      ('data_5', 64), ('data_6', 64), ('data_7', 64), ('set', 64), ('tag', 64), ('way', 64),
      ('dir', 64)),
     ()),
    ('Pipeline_53', 2, True,
     (('cmd', 8), ('data_0', 64), ('data_1', 64), ('data_2', 64), ('data_3', 64), ('data_4', 64),
      ('data_5', 64), ('data_6', 64), ('data_7', 64)),
     (('cmd', 8), ('data_0', 64), ('data_1', 64), ('data_2', 64), ('data_3', 64), ('data_4', 64),
      ('data_5', 64), ('data_6', 64), ('data_7', 64)),
     ()),
)
CONNECT_PROFILE_ROWS: tuple[tuple[str, bool, bool, bool, bool, tuple[tuple[str, int], ...]], ...] = (
    ('NewPipelineConnectPipe_1', False, False, True, False,
     (('fuType', 35), ('fuOpType', 9), ('src_0', 64), ('src_1', 64), ('imm', 64),
      ('nextPcOffset', 5), ('robIdx_flag', 1), ('robIdx_value', 8), ('pdest', 8), ('rfWen', 1),
      ('pc', 50), ('ftqIdx_flag', 1), ('ftqIdx_value', 6), ('ftqOffset', 4),
      ('predictInfo_target', 50), ('predictInfo_taken', 1))),
    ('NewPipelineConnectPipe_5', False, False, True, False,
     (('fuType', 35), ('fuOpType', 9), ('src_0', 64), ('src_1', 64), ('imm', 64),
      ('nextPcOffset', 5), ('robIdx_flag', 1), ('robIdx_value', 8), ('pdest', 8), ('rfWen', 1),
      ('fpWen', 1), ('vecWen', 1), ('v0Wen', 1), ('vlWen', 1), ('fpu_typeTagOut', 2),
      ('fpu_wflags', 1), ('fpu_typ', 2), ('fpu_rm', 3), ('pc', 50), ('ftqIdx_flag', 1),
      ('ftqIdx_value', 6), ('ftqOffset', 4), ('predictInfo_target', 50), ('predictInfo_taken', 1))),
    ('NewPipelineConnectPipe_7', True, True, True, False,
     (('fuType', 35), ('fuOpType', 9), ('src_0', 64), ('src_1', 64), ('imm', 64),
      ('robIdx_flag', 1), ('robIdx_value', 8), ('pdest', 8), ('rfWen', 1), ('flushPipe', 1),
      ('ftqIdx_flag', 1), ('ftqIdx_value', 6), ('ftqOffset', 4))),
    ('NewPipelineConnectPipe_8', False, False, True, False,
     (('fuType', 35), ('fuOpType', 9), ('src_0', 64), ('src_1', 64), ('src_2', 64),
      ('robIdx_flag', 1), ('robIdx_value', 8), ('pdest', 8), ('rfWen', 1), ('fpWen', 1),
      ('vecWen', 1), ('v0Wen', 1), ('fpu_wflags', 1), ('fpu_fmt', 2), ('fpu_rm', 3))),
    ('NewPipelineConnectPipe_9', True, True, True, False,
     (('fuType', 35), ('fuOpType', 9), ('src_0', 64), ('src_1', 64), ('robIdx_flag', 1),
      ('robIdx_value', 8), ('pdest', 8), ('fpWen', 1), ('fpu_wflags', 1), ('fpu_fmt', 2),
      ('fpu_rm', 3))),
    ('NewPipelineConnectPipe_10', False, False, True, False,
     (('fuType', 35), ('fuOpType', 9), ('src_0', 64), ('src_1', 64), ('src_2', 64),
      ('robIdx_flag', 1), ('robIdx_value', 8), ('pdest', 8), ('rfWen', 1), ('fpWen', 1),
      ('fpu_wflags', 1), ('fpu_fmt', 2), ('fpu_rm', 3))),
    ('NewPipelineConnectPipe_13', True, True, True, False,
     (('fuType', 35), ('fuOpType', 9), ('src_0', 128), ('src_1', 128), ('src_2', 128),
      ('src_3', 128), ('src_4', 128), ('robIdx_flag', 1), ('robIdx_value', 8), ('pdest', 7),
      ('vecWen', 1), ('v0Wen', 1), ('fpu_wflags', 1), ('vpu_vma', 1), ('vpu_vta', 1),
      ('vpu_vsew', 2), ('vpu_vlmul', 3), ('vpu_vm', 1), ('vpu_vstart', 8), ('vpu_vuopIdx', 7),
      ('vpu_isExt', 1), ('vpu_isNarrow', 1), ('vpu_isDstMask', 1), ('vpu_isOpMask', 1))),
    ('NewPipelineConnectPipe_14', False, False, True, False,
     (('fuType', 35), ('fuOpType', 9), ('src_0', 128), ('src_1', 128), ('src_2', 128),
      ('src_3', 128), ('src_4', 128), ('robIdx_flag', 1), ('robIdx_value', 8), ('pdest', 8),
      ('rfWen', 1), ('fpWen', 1), ('vecWen', 1), ('v0Wen', 1), ('vlWen', 1), ('fpu_wflags', 1),
      ('vpu_vma', 1), ('vpu_vta', 1), ('vpu_vsew', 2), ('vpu_vlmul', 3), ('vpu_vm', 1),
      ('vpu_vstart', 8), ('vpu_fpu_isFoldTo1_2', 1), ('vpu_fpu_isFoldTo1_4', 1),
      ('vpu_fpu_isFoldTo1_8', 1), ('vpu_vuopIdx', 7), ('vpu_lastUop', 1), ('vpu_isNarrow', 1),
      ('vpu_isDstMask', 1))),
    ('NewPipelineConnectPipe_16', False, False, True, False,
     (('fuType', 35), ('fuOpType', 9), ('src_0', 128), ('src_1', 128), ('src_2', 128),
      ('src_3', 128), ('src_4', 128), ('robIdx_flag', 1), ('robIdx_value', 8), ('pdest', 8),
      ('fpWen', 1), ('vecWen', 1), ('v0Wen', 1), ('fpu_wflags', 1), ('vpu_vma', 1), ('vpu_vta', 1),
      ('vpu_vsew', 2), ('vpu_vlmul', 3), ('vpu_vm', 1), ('vpu_vstart', 8),
      ('vpu_fpu_isFoldTo1_2', 1), ('vpu_fpu_isFoldTo1_4', 1), ('vpu_fpu_isFoldTo1_8', 1),
      ('vpu_vuopIdx', 7), ('vpu_lastUop', 1), ('vpu_isNarrow', 1), ('vpu_isDstMask', 1))),
    ('NewPipelineConnectPipe_18', True, True, True, False,
     (('fuType', 35), ('fuOpType', 9), ('src_0', 64), ('imm', 64), ('robIdx_flag', 1),
      ('robIdx_value', 8), ('pdest', 8), ('rfWen', 1), ('sqIdx_flag', 1), ('sqIdx_value', 6))),
    ('NewPipelineConnectPipe_20', True, True, True, False,
     (('fuOpType', 9), ('src_0', 64), ('imm', 64), ('robIdx_flag', 1), ('robIdx_value', 8),
      ('pdest', 8), ('rfWen', 1), ('fpWen', 1), ('pc', 50), ('preDecode_isRVC', 1),
      ('ftqIdx_flag', 1), ('ftqIdx_value', 6), ('ftqOffset', 4), ('loadWaitBit', 1),
      ('waitForRobIdx_flag', 1), ('waitForRobIdx_value', 8), ('storeSetHit', 1),
      ('loadWaitStrict', 1), ('sqIdx_flag', 1), ('sqIdx_value', 6), ('lqIdx_flag', 1),
      ('lqIdx_value', 7))),
    ('NewPipelineConnectPipe_23', True, True, True, True,
     (('fuType', 35), ('fuOpType', 9), ('src_0', 128), ('src_1', 128), ('src_2', 128),
      ('src_3', 128), ('src_4', 128), ('robIdx_flag', 1), ('robIdx_value', 8), ('pdest', 7),
      ('vecWen', 1), ('v0Wen', 1), ('vlWen', 1), ('vpu_vma', 1), ('vpu_vta', 1), ('vpu_vsew', 2),
      ('vpu_vlmul', 3), ('vpu_vm', 1), ('vpu_vstart', 8), ('vpu_vuopIdx', 7), ('vpu_lastUop', 1),
      ('vpu_vmask', 128), ('vpu_nf', 3), ('vpu_veew', 2), ('vpu_isVleff', 1), ('ftqIdx_flag', 1),
      ('ftqIdx_value', 6), ('ftqOffset', 4), ('numLsElem', 5), ('sqIdx_flag', 1),
      ('sqIdx_value', 6), ('lqIdx_flag', 1), ('lqIdx_value', 7), ('isVecPartReplay', 1),
      ('vecReplayMask', 16), ('vecReplayMbIdx', 4))),
    ('NewPipelineConnectPipe_25', True, True, True, False,
     (('fuType', 35), ('fuOpType', 9), ('src_0', 64), ('robIdx_flag', 1), ('robIdx_value', 8),
      ('sqIdx_flag', 1), ('sqIdx_value', 6))),
    ('NewPipelineConnectPipe_27', True, True, False, False,
     (('0_valid', 1), ('0_mask', 64), ('1_valid', 1), ('1_mask', 64), ('2_valid', 1),
      ('2_mask', 64), ('3_valid', 1), ('3_mask', 64), ('4_valid', 1), ('4_mask', 64),
      ('5_valid', 1), ('5_mask', 64), ('6_valid', 1), ('6_mask', 64), ('7_valid', 1),
      ('7_mask', 64))),
    ('NewPipelineConnectPipe_29', True, True, True, False,
     (('uop_exceptionVec_3', 1), ('uop_exceptionVec_4', 1), ('uop_exceptionVec_5', 1),
      ('uop_exceptionVec_6', 1), ('uop_exceptionVec_7', 1), ('uop_exceptionVec_13', 1),
      ('uop_exceptionVec_15', 1), ('uop_exceptionVec_19', 1), ('uop_exceptionVec_21', 1),
      ('uop_exceptionVec_23', 1), ('uop_trigger', 4), ('uop_fuOpType', 9), ('uop_vecWen', 1),
      ('uop_v0Wen', 1), ('uop_vlWen', 1), ('uop_flushPipe', 1), ('uop_vpu_vma', 1),
      ('uop_vpu_vta', 1), ('uop_vpu_vsew', 2), ('uop_vpu_vlmul', 3), ('uop_vpu_vm', 1),
      ('uop_vpu_vstart', 8), ('uop_vpu_vuopIdx', 7), ('uop_vpu_vmask', 128), ('uop_vpu_vl', 8),
      ('uop_vpu_nf', 3), ('uop_vpu_veew', 2), ('uop_pdest', 8), ('uop_robIdx_flag', 1),
      ('uop_robIdx_value', 8), ('uop_replayInst', 1), ('data', 128), ('vdIdxInField', 3))),
    ('NewPipelineConnectPipe_33', True, True, False, False,
     (('vaddr', 50), ('data', 128), ('mask', 16), ('addr', 48), ('vecValid', 1))),
    ('NewPipelineConnectPipe_34', True, True, False, False,
     (('uop_exceptionVec_0', 1), ('uop_exceptionVec_1', 1), ('uop_exceptionVec_2', 1),
      ('uop_exceptionVec_3', 1), ('uop_exceptionVec_4', 1), ('uop_exceptionVec_5', 1),
      ('uop_exceptionVec_6', 1), ('uop_exceptionVec_7', 1), ('uop_exceptionVec_8', 1),
      ('uop_exceptionVec_9', 1), ('uop_exceptionVec_10', 1), ('uop_exceptionVec_11', 1),
      ('uop_exceptionVec_12', 1), ('uop_exceptionVec_13', 1), ('uop_exceptionVec_14', 1),
      ('uop_exceptionVec_15', 1), ('uop_exceptionVec_16', 1), ('uop_exceptionVec_17', 1),
      ('uop_exceptionVec_18', 1), ('uop_exceptionVec_19', 1), ('uop_exceptionVec_20', 1),
      ('uop_exceptionVec_21', 1), ('uop_exceptionVec_22', 1), ('uop_exceptionVec_23', 1),
      ('uop_trigger', 4), ('uop_flushPipe', 1), ('uop_robIdx_flag', 1), ('uop_robIdx_value', 8),
      ('debug_isMMIO', 1))),
    ('NewPipelineConnectPipe_35', True, True, True, False,
     (('vaddr', 64), ('basevaddr', 50), ('mask', 16), ('reg_offset', 4), ('alignedType', 3),
      ('vecActive', 1), ('vecIsFirstActiveElement', 1), ('uop_exceptionVec_4', 1),
      ('uop_exceptionVec_5', 1), ('uop_exceptionVec_6', 1), ('uop_exceptionVec_13', 1),
      ('uop_exceptionVec_19', 1), ('uop_exceptionVec_21', 1), ('uop_trigger', 4),
      ('uop_preDecodeInfo_isRVC', 1), ('uop_ftqPtr_flag', 1), ('uop_ftqPtr_value', 6),
      ('uop_ftqOffset', 4), ('uop_fuOpType', 9), ('uop_rfWen', 1), ('uop_fpWen', 1),
      ('uop_vpu_vstart', 8), ('uop_vpu_veew', 2), ('uop_uopIdx', 7), ('uop_pdest', 8),
      ('uop_robIdx_flag', 1), ('uop_robIdx_value', 8), ('uop_storeSetHit', 1),
      ('uop_waitForRobIdx_flag', 1), ('uop_waitForRobIdx_value', 8), ('uop_loadWaitBit', 1),
      ('uop_loadWaitStrict', 1), ('uop_lqIdx_flag', 1), ('uop_lqIdx_value', 7),
      ('uop_sqIdx_flag', 1), ('uop_sqIdx_value', 6), ('mBIndex', 4), ('elemIdx', 8),
      ('elemIdxInsideVd', 8), ('splitIndex', 5))),
)
QUEUE_PROFILE_ROWS: tuple[tuple[str, bool, tuple[tuple[str, int], ...], tuple[tuple[str, int], ...], tuple[tuple[str, int], ...]], ...] = (
    ('Queue1_ClientDirWrite', True, (('set', 10), ('way', 4), ('data_0_state', 2)),
     (('set', 10), ('way', 4), ('data_0_state', 2)), ()),
    ('Queue1_ClientTagWrite', True, (('set', 10), ('way', 4), ('tag', 30)),
     (('set', 10), ('way', 4), ('tag', 30)), ()),
    ('Queue1_CtrlReq', True,
     (('cmd', 8), ('data_0', 64), ('data_1', 64), ('data_2', 64), ('data_3', 64), ('data_4', 64),
      ('data_5', 64), ('data_6', 64), ('data_7', 64), ('set', 64), ('tag', 64), ('way', 64),
      ('dir', 64)),
     (('cmd', 8), ('data_0', 64), ('data_1', 64), ('data_2', 64), ('data_3', 64), ('data_4', 64),
      ('data_5', 64), ('data_6', 64), ('data_7', 64), ('set', 64), ('tag', 64), ('way', 64),
      ('dir', 64)),
     ()),
    ('Queue1_CtrlResp', True,
     (('cmd', 8), ('data_0', 64), ('data_1', 64), ('data_2', 64), ('data_3', 64), ('data_4', 64),
      ('data_5', 64), ('data_6', 64), ('data_7', 64)),
     (('cmd', 8), ('data_0', 64), ('data_1', 64), ('data_2', 64), ('data_3', 64), ('data_4', 64),
      ('data_5', 64), ('data_6', 64), ('data_7', 64)),
     ()),
    ('Queue1_EccInfo', True, (('errCode', 8), ('addr', 64)), (('errCode', 8), ('addr', 64)), ()),
    ('Queue1_L1PrefetchReq', True,
     (('paddr', 48), ('alias', 2), ('confidence', 1), ('is_store', 1), ('pf_source_value', 3)),
     (('paddr', 48), ('alias', 2), ('confidence', 1), ('is_store', 1), ('pf_source_value', 3)), ()),
    ('Queue1_MSHRRequest', True,
     (('channel', 3), ('opcode', 3), ('param', 3), ('size', 3), ('source', 11), ('set', 12),
      ('tag', 28), ('off', 6), ('mask', 32), ('bufIdx', 4), ('needHint', 1), ('isPrefetch', 1),
      ('isBop', 1), ('preferCache', 1), ('dirty', 1), ('isHit', 1), ('fromProbeHelper', 1),
      ('fromCmoHelper', 1), ('needProbeAckData', 1), ('reqSource', 5)),
     (('channel', 3), ('opcode', 3), ('param', 3), ('size', 3), ('source', 11), ('set', 12),
      ('tag', 28), ('off', 6), ('mask', 32), ('bufIdx', 4), ('needHint', 1), ('isPrefetch', 1),
      ('isBop', 1), ('preferCache', 1), ('dirty', 1), ('fromProbeHelper', 1), ('fromCmoHelper', 1),
      ('needProbeAckData', 1), ('reqSource', 5)),
     ()),
    ('Queue1_PipeInfo', True,
     (('counter', 1), ('beat', 1), ('last', 1), ('needPb', 1), ('need_d', 1), ('isReleaseAck', 1),
      ('req_sourceId', 11), ('req_set', 12), ('req_tag', 28), ('req_channel', 3), ('req_opcode', 3),
      ('req_param', 3), ('req_size', 3), ('req_way', 4), ('req_off', 6), ('req_useBypass', 1),
      ('req_bufIdx', 4), ('req_denied', 1), ('req_sinkId', 4), ('req_bypassPut', 1),
      ('req_dirty', 1), ('req_isHit', 1)),
     (('counter', 1), ('beat', 1), ('last', 1), ('needPb', 1), ('need_d', 1), ('isReleaseAck', 1),
      ('req_sourceId', 11), ('req_set', 12), ('req_tag', 28), ('req_channel', 3), ('req_opcode', 3),
      ('req_param', 3), ('req_size', 3), ('req_way', 4), ('req_off', 6), ('req_useBypass', 1),
      ('req_bufIdx', 4), ('req_denied', 1), ('req_sinkId', 4), ('req_bypassPut', 1),
      ('req_dirty', 1), ('req_isHit', 1)),
     ()),
    ('Queue1_PrefetchReq', True,
     (('tag', 33), ('set', 9), ('vaddr', 44), ('needT', 1), ('source', 7), ('pfSource', 5)),
     (('tag', 33), ('set', 9), ('vaddr', 44), ('needT', 1), ('source', 7), ('pfSource', 5)), ()),
    ('Queue1_PrefetchReq_1', True, (('tag', 30), ('set', 12), ('pfSource', 5)),
     (('tag', 30), ('set', 12), ('needT', 1), ('source', 11), ('pfSource', 5)),
     (('needT', 0), ('source', 0))),
    ('Queue1_PrefetchResp', True, (), (), ()),
    ('Queue1_PrefetchResp_4', True, (), (), ()),
    ('Queue1_PrefetchTrain', False,
     (('tag', 33), ('set', 9), ('needT', 1), ('source', 7), ('vaddr', 44), ('hit', 1),
      ('prefetched', 1), ('pfsource', 3), ('reqsource', 5)),
     (('tag', 33), ('set', 9), ('needT', 1), ('source', 7), ('vaddr', 44), ('reqsource', 5)), ()),
    ('Queue1_PrefetchTrain_4', True, (), (), ()),
    ('Queue1_SelfDirWrite', True,
     (('set', 12), ('way', 4), ('data_dirty', 1), ('data_state', 2), ('data_clientStates_0', 2),
      ('data_prefetch', 1)),
     (('set', 12), ('way', 4), ('data_dirty', 1), ('data_state', 2), ('data_clientStates_0', 2),
      ('data_prefetch', 1)),
     ()),
    ('Queue1_SelfTagWrite', True, (('set', 12), ('way', 4), ('tag', 28)),
     (('set', 12), ('way', 4), ('tag', 28)), ()),
)

PIPELINE_INPUT_PREFIX = "io_in_bits_"
PIPELINE_OUTPUT_PREFIX = "io_out_bits_"
QUEUE_INPUT_PREFIX = "io_enq_bits_"
QUEUE_OUTPUT_PREFIX = "io_deq_bits_"
CONNECT_INPUT_PREFIX = "io_in_bits_"
CONNECT_OUTPUT_PREFIX = "io_out_bits_"

PIPELINE_NAMES: tuple[str, ...] = tuple(row[0] for row in PIPELINE_PROFILE_ROWS)
CONNECT_NAMES: tuple[str, ...] = tuple(row[0] for row in CONNECT_PROFILE_ROWS)
QUEUE_NAMES: tuple[str, ...] = tuple(row[0] for row in QUEUE_PROFILE_ROWS)

_PIPELINE_CONFIGURATIONS: dict[str, ElasticMemberConfiguration] = {
    name: ElasticMemberConfiguration(
        member_name=name,
        stage_count=stage_count,
        input_ready_name="io_in_ready" if exposes_input_ready else None,
        input_fields=input_fields,
        output_fields=output_fields,
        output_constants=constants,
        input_valid_name="io_in_valid",
        output_valid_name="io_out_valid",
        output_ready_name="io_out_ready",
        input_prefix=PIPELINE_INPUT_PREFIX,
        output_prefix=PIPELINE_OUTPUT_PREFIX,
    )
    for name, stage_count, exposes_input_ready, input_fields, output_fields, constants
    in PIPELINE_PROFILE_ROWS
}
_QUEUE_CONFIGURATIONS: dict[str, ElasticMemberConfiguration] = {
    name: ElasticMemberConfiguration(
        member_name=name,
        stage_count=1,
        input_ready_name="io_enq_ready" if exposes_input_ready else None,
        input_fields=input_fields,
        output_fields=output_fields,
        output_constants=constants,
        input_valid_name="io_enq_valid",
        output_valid_name="io_deq_valid",
        output_ready_name="io_deq_ready",
        input_prefix=QUEUE_INPUT_PREFIX,
        output_prefix=QUEUE_OUTPUT_PREFIX,
    )
    for name, exposes_input_ready, input_fields, output_fields, constants
    in QUEUE_PROFILE_ROWS
}
_CONNECT_CONFIGURATIONS: dict[str, ConnectMemberConfiguration] = {
    name: ConnectMemberConfiguration(
        member_name=name,
        payload_fields=payload_fields,
        exposes_input_ready=exposes_input_ready,
        exposes_output_ready=exposes_output_ready,
        exposes_flush=exposes_flush,
        exposes_older=exposes_older,
    )
    for name, exposes_input_ready, exposes_output_ready, exposes_flush, exposes_older,
    payload_fields in CONNECT_PROFILE_ROWS
}
_CONFIGURED_MEMBER_NAMES = (
    set(_PIPELINE_CONFIGURATIONS)
    | set(_CONNECT_CONFIGURATIONS)
    | set(_QUEUE_CONFIGURATIONS)
)
if len(COVERED_MODULES) != len(set(COVERED_MODULES)):
    raise ValueError("PipelineFamily requires unique public members")
if set(COVERED_MODULES) != _CONFIGURED_MEMBER_NAMES | set(SOURCE_PIPELINE_MEMBERS):
    raise ValueError("PipelineFamily coverage and hardware configurations differ")
MemberConfiguration: TypeAlias = (
    ElasticMemberConfiguration | ConnectMemberConfiguration | SourcePipelineConfiguration
)


# =============================================================================
# Implementation
# =============================================================================
class ValidInterface:
    """Packed valid/payload bundle with elaboration-time mapping support."""

    def __init__(self, width: int, name: str = "valid") -> None:
        if width < 0:
            raise ValueError("valid payload width must be nonnegative")
        self.width = width
        self.valid = Signal(name=f"{name}_valid")
        self.bits = Signal(width, name=f"{name}_bits")

    @property
    def fire(self) -> Signal:
        return self.valid

    @property
    def type_name(self) -> str:
        return f"Valid_UInt{self.width}"

    def map(self, module: Module, transform: Callable[[Value], Value], width: int) -> ValidInterface:
        mapped = ValidInterface(width, "mapped")
        module.d.comb += [mapped.valid.eq(self.valid), mapped.bits.eq(transform(self.bits))]
        return mapped


class SourcePipeline(Elaboratable):
    """Parameterized valid, ready/valid, credit, and tag-addressed storage."""

    def __init__(self, configuration: SourcePipelineConfiguration) -> None:
        self.configuration = configuration
        self.inputs: dict[str, Signal] = {}
        self.outputs: dict[str, Signal] = {}
        self.port_specs: list[PortSpec] = []
        self.add_port("clock", "input", 1)
        self.add_port("reset", "input", 1)
        member = configuration.member_name
        width = configuration.width
        if member == "CreditedIOCounter":
            self.add_port("io_credit", "input", 1)
            self.add_port("io_debit", "input", 1)
            self.add_port("io_value", "output", configuration.entries.bit_length())
            self.add_port("io_nextValue", "output", configuration.entries.bit_length())
            self.add_port("io_full", "output", 1)
            self.add_port("io_empty", "output", 1)
        elif member == "CreditedIOPipeline":
            for name, direction, size in (
                ("io_in_credit", "output", 1), ("io_in_debit", "input", 1),
                ("io_in_bits", "input", width), ("io_out_credit", "input", 1),
                ("io_out_debit", "output", 1), ("io_out_bits", "output", width),
            ):
                self.add_port(name, cast(PortDirection, direction), size)
        elif member == "CreditedIOSender":
            self.add_ready_valid("io_in", "input", width)
            self.add_port("io_credit", "input", 1)
            self.add_port("io_debit", "output", 1)
            self.add_port("io_bits", "output", width)
        elif member == "CreditedIOReceiver":
            self.add_port("io_credit", "output", 1)
            self.add_port("io_debit", "input", 1)
            self.add_port("io_bits", "input", width)
            self.add_ready_valid("io_out", "output", width)
        elif member == "ReorderQueue":
            self.add_port("io_enq_ready", "output", 1)
            self.add_port("io_enq_valid", "input", 1)
            self.add_port("io_enq_bits_data", "input", width)
            self.add_port("io_enq_bits_tag", "input", configuration.tag_width)
            self.add_port("io_deq_valid", "input", 1)
            self.add_port("io_deq_tag", "input", configuration.tag_width)
            self.add_port("io_deq_data", "output", width)
            self.add_port("io_deq_matches", "output", 1)
        elif member == "Pipe":
            self.add_port("io_enq_valid", "input", 1)
            self.add_port("io_enq_bits", "input", width)
            self.add_port("io_deq_valid", "output", 1)
            self.add_port("io_deq_bits", "output", width)
        else:
            enq_prefix = "io_enq" if member in ("ShiftQueue", "Repeater") else "io_in"
            deq_prefix = "io_deq" if member in ("ShiftQueue", "Repeater") else "io_out"
            input_width = configuration.input_width if member == "MultiWidthFifo" else width
            output_width = configuration.output_width if member == "MultiWidthFifo" else width
            self.add_ready_valid(enq_prefix, "input", input_width)
            if member == "Broadcaster":
                for index in range(configuration.targets):
                    self.add_ready_valid(f"io_out_{index}", "output", width)
            else:
                self.add_ready_valid(deq_prefix, "output", output_width)
            if member == "Repeater":
                self.add_port("io_repeat", "input", 1)
                self.add_port("io_full", "output", 1)
            elif member == "ShiftQueue":
                self.add_port("io_mask", "output", configuration.entries)
                self.add_port("io_count", "output", configuration.entries.bit_length())
            elif member == "MultiWidthFifo":
                self.add_port("io_count", "output", configuration.entries.bit_length())

    def add_port(self, name: str, direction: PortDirection, width: int) -> Signal:
        signal = Signal(width, name=name)
        self.port_specs.append(PortSpec(name, direction, width))
        (self.inputs if direction == "input" else self.outputs)[name] = signal
        return signal

    def add_ready_valid(self, prefix: str, direction: PortDirection, width: int) -> None:
        reverse: PortDirection = "output" if direction == "input" else "input"
        self.add_port(prefix + "_valid", direction, 1)
        self.add_port(prefix + "_bits", direction, width)
        self.add_port(prefix + "_ready", reverse, 1)

    def ports(self) -> list[Signal]:
        return [
            (self.inputs if spec.direction == "input" else self.outputs)[spec.name]
            for spec in self.port_specs if spec.width > 0
        ]

    def elaborate(self, platform: object) -> Module:
        del platform
        module = Module()
        domain = ClockDomain("sync", async_reset=self.configuration.async_reset)
        domain.clk, domain.rst = self.inputs["clock"], self.inputs["reset"]
        module.domains += domain
        member = self.configuration.member_name
        if member == "Pipe":
            self.elaborate_valid_pipe(module)
        elif member == "LatencyPipe":
            self.elaborate_latency_pipe(module)
        elif member == "Broadcaster":
            self.elaborate_broadcaster(module)
        elif member == "Repeater":
            self.elaborate_repeater(module)
        elif member == "ShiftQueue":
            self.elaborate_shift_queue(module)
        elif member == "ReorderQueue":
            self.elaborate_reorder_queue(module)
        elif member == "MultiWidthFifo":
            self.elaborate_width_fifo(module)
        elif member == "CreditedIOCounter":
            value, following = self.credit_counter(module, self.inputs["io_credit"], self.inputs["io_debit"])
            module.d.comb += [
                self.outputs["io_value"].eq(value), self.outputs["io_nextValue"].eq(following),
                self.outputs["io_empty"].eq(value == 0),
                self.outputs["io_full"].eq(value == self.configuration.entries),
            ]
        elif member == "CreditedIOPipeline":
            self.elaborate_credit_pipeline(module)
        elif member == "CreditedIOSender":
            debit = self.outputs["io_debit"]
            value, _following = self.credit_counter(module, self.inputs["io_credit"], debit, self.configuration.entries)
            ready = (value != 0) | (Const(self.configuration.pipe) & self.inputs["io_credit"])
            module.d.comb += [
                self.outputs["io_in_ready"].eq(ready),
                debit.eq(self.inputs["io_in_valid"] & ready),
                self.outputs["io_bits"].eq(self.inputs["io_in_bits"]),
            ]
        elif member == "CreditedIOReceiver":
            self.elaborate_credit_receiver(module)
        return module

    def elaborate_valid_pipe(self, module: Module) -> None:
        valid: Value = self.inputs["io_enq_valid"]
        payload: Value = self.inputs["io_enq_bits"]
        for index in range(self.configuration.latency):
            next_valid = Signal(name=f"pipe_{index}_valid")
            next_payload = Signal(self.configuration.width, name=f"pipe_{index}_bits", reset_less=True)
            module.d.sync += next_valid.eq(valid)
            with cast(AbstractContextManager[None], module.If(valid)):
                module.d.sync += next_payload.eq(payload)
            valid, payload = next_valid, next_payload
        module.d.comb += [self.outputs["io_deq_valid"].eq(valid), self.outputs["io_deq_bits"].eq(payload)]

    def elaborate_latency_pipe(self, module: Module) -> None:
        count = max(0, self.configuration.latency)
        if count == 0:
            module.d.comb += [
                self.outputs["io_out_valid"].eq(self.inputs["io_in_valid"]),
                self.outputs["io_out_bits"].eq(self.inputs["io_in_bits"]),
                self.outputs["io_in_ready"].eq(self.inputs["io_out_ready"]),
            ]
            return
        valid = [Signal(name=f"stage_{index}_valid") for index in range(count)]
        data = [Signal(self.configuration.width, name=f"stage_{index}_bits", reset_less=True) for index in range(count)]
        ready = [Signal(name=f"stage_{index}_ready") for index in range(count)]
        for index in range(count - 1, -1, -1):
            downstream = self.inputs["io_out_ready"] if index == count - 1 else ready[index + 1]
            module.d.comb += ready[index].eq(~valid[index] | downstream)
            upstream_valid = self.inputs["io_in_valid"] if index == 0 else valid[index - 1]
            upstream_data = self.inputs["io_in_bits"] if index == 0 else data[index - 1]
            fire = upstream_valid & ready[index]
            with cast(AbstractContextManager[None], module.If(fire != (valid[index] & downstream))):
                module.d.sync += valid[index].eq(fire)
            with cast(AbstractContextManager[None], module.If(fire)):
                module.d.sync += data[index].eq(upstream_data)
        module.d.comb += [
            self.outputs["io_in_ready"].eq(ready[0]), self.outputs["io_out_valid"].eq(valid[-1]),
            self.outputs["io_out_bits"].eq(data[-1]),
        ]

    def elaborate_broadcaster(self, module: Module) -> None:
        count = self.configuration.targets
        if count == 1:
            module.d.comb += [
                self.outputs["io_out_0_valid"].eq(self.inputs["io_in_valid"]),
                self.outputs["io_out_0_bits"].eq(self.inputs["io_in_bits"]),
                self.outputs["io_in_ready"].eq(self.inputs["io_out_0_ready"]),
            ]
            return
        selected = Signal(range(count), name="selected")
        saved = Signal(self.configuration.width, name="saved", reset_less=True)
        module.d.comb += self.outputs["io_in_ready"].eq(self.inputs["io_out_0_ready"] & (selected == 0))
        for index in range(count):
            valid = (selected == index) & self.inputs["io_in_valid"] if index == 0 else selected == index
            module.d.comb += [
                self.outputs[f"io_out_{index}_valid"].eq(valid),
                self.outputs[f"io_out_{index}_bits"].eq(self.inputs["io_in_bits"] if index == 0 else saved),
            ]
        with cast(AbstractContextManager[None], module.If(self.inputs["io_in_valid"] & self.outputs["io_in_ready"])):
            module.d.sync += saved.eq(self.inputs["io_in_bits"])
        ready = Array(self.inputs[f"io_out_{index}_ready"] for index in range(count))
        valid = Array(self.outputs[f"io_out_{index}_valid"] for index in range(count))
        with cast(AbstractContextManager[None], module.If(ready[selected] & valid[selected])):
            module.d.sync += selected.eq(Mux(selected == count - 1, 0, selected + 1))

    def elaborate_repeater(self, module: Module) -> None:
        full = Signal(name="full")
        saved = Signal(self.configuration.width, name="saved", reset_less=True)
        valid = self.inputs["io_enq_valid"] | full
        ready = self.inputs["io_deq_ready"] & ~full
        module.d.comb += [
            self.outputs["io_full"].eq(full), self.outputs["io_enq_ready"].eq(ready),
            self.outputs["io_deq_valid"].eq(valid),
            self.outputs["io_deq_bits"].eq(Mux(full, saved, self.inputs["io_enq_bits"])),
        ]
        with cast(AbstractContextManager[None], module.If(self.inputs["io_enq_valid"] & ready & self.inputs["io_repeat"])):
            module.d.sync += [full.eq(1), saved.eq(self.inputs["io_enq_bits"])]
        with cast(AbstractContextManager[None], module.If(valid & self.inputs["io_deq_ready"] & ~self.inputs["io_repeat"])):
            module.d.sync += full.eq(0)

    def elaborate_shift_queue(self, module: Module) -> None:
        count = self.configuration.entries
        valid = [Signal(name=f"valid_{index}") for index in range(count)]
        data = [Signal(self.configuration.width, name=f"elts_{index}", reset_less=True) for index in range(count)]
        ready = ~valid[-1] | (Const(self.configuration.pipe) & self.inputs["io_deq_ready"])
        fire = self.inputs["io_enq_valid"] & ready
        module.d.comb += [
            self.outputs["io_enq_ready"].eq(ready),
            self.outputs["io_deq_valid"].eq(valid[0] | (Const(self.configuration.flow) & self.inputs["io_enq_valid"])),
            self.outputs["io_deq_bits"].eq(Mux(Const(self.configuration.flow) & ~valid[0], self.inputs["io_enq_bits"], data[0])),
            self.outputs["io_mask"].eq(Cat(*valid)), self.outputs["io_count"].eq(sum(valid)),
        ]
        for index in range(count):
            above: Value = valid[index + 1] if index + 1 < count else Const(0)
            below: Value = valid[index - 1] if index > 0 else Const(1)
            incoming = self.inputs["io_enq_bits"] if index + 1 == count else Mux(above, data[index + 1], self.inputs["io_enq_bits"])
            shift_valid = above | (fire & (Const(index == 0 and not self.configuration.flow) | valid[index]))
            append_valid = (fire & below) | valid[index]
            write = Mux(self.inputs["io_deq_ready"], shift_valid, fire & below & ~valid[index])
            module.d.sync += valid[index].eq(Mux(self.inputs["io_deq_ready"], shift_valid, append_valid))
            with cast(AbstractContextManager[None], module.If(write)):
                module.d.sync += data[index].eq(incoming)

    def elaborate_reorder_queue(self, module: Module) -> None:
        tag_space = 1 << self.configuration.tag_width
        count = self.configuration.reorder_size or tag_space
        associative = count < tag_space
        if not associative:
            count = tag_space
        free = [Signal(init=1, name=f"free_{index}") for index in range(count)]
        data = [Signal(self.configuration.width, name=f"data_{index}", reset_less=True) for index in range(count)]
        incoming_tag = self.inputs["io_enq_bits_tag"]
        requested_tag = self.inputs["io_deq_tag"]
        write_index = Signal(range(max(2, count)), name="write_index")
        read_index = Signal(range(max(2, count)), name="read_index")
        if associative:
            tags = [Signal(self.configuration.tag_width, name=f"tag_{index}", reset_less=True) for index in range(count)]
            matched = [(tags[index] == requested_tag) & ~free[index] for index in range(count)]
            any_match: Value = Const(0)
            selected_data: Value = Const(0, self.configuration.width)
            for index in range(count - 1, -1, -1):
                with cast(AbstractContextManager[None], module.If(free[index])):
                    module.d.comb += write_index.eq(index)
                with cast(AbstractContextManager[None], module.If(matched[index])):
                    module.d.comb += read_index.eq(index)
                selected_data = Mux(matched[index], data[index], selected_data)
                any_match = any_match | matched[index]
            module.d.comb += [
                self.outputs["io_enq_ready"].eq(cast(Value, Cat(*free)).any()),
                self.outputs["io_deq_matches"].eq(any_match),
                self.outputs["io_deq_data"].eq(selected_data),
            ]
            with cast(AbstractContextManager[None], module.If(self.inputs["io_enq_valid"] & self.outputs["io_enq_ready"])):
                module.d.sync += Array(tags)[write_index].eq(incoming_tag)
        else:
            module.d.comb += [
                write_index.eq(incoming_tag), read_index.eq(requested_tag),
                self.outputs["io_enq_ready"].eq(Array(free)[incoming_tag]),
                self.outputs["io_deq_matches"].eq(~cast(Value, Array(free)[requested_tag])),
                self.outputs["io_deq_data"].eq(Array(data)[requested_tag]),
            ]
        with cast(AbstractContextManager[None], module.If(self.inputs["io_enq_valid"] & self.outputs["io_enq_ready"])):
            module.d.sync += [Array(data)[write_index].eq(self.inputs["io_enq_bits_data"]), Array(free)[write_index].eq(0)]
        with cast(AbstractContextManager[None], module.If(self.inputs["io_deq_valid"])):
            module.d.sync += Array(free)[read_index].eq(1)

    def elaborate_width_fifo(self, module: Module) -> None:
        incoming, outgoing, capacity = self.configuration.input_width, self.configuration.output_width, self.configuration.entries
        if incoming == outgoing:
            ratio, words, head_words, tail_words = 1, capacity, capacity, capacity
        elif incoming > outgoing:
            ratio = incoming // outgoing
            words, head_words, tail_words = capacity // ratio, capacity // ratio, capacity
        else:
            ratio = outgoing // incoming
            words, head_words, tail_words = capacity * ratio, capacity * ratio, capacity
        data = [Signal(incoming, name=f"wdata_{index}", reset_less=True) for index in range(words)]
        head = Signal(max(1, (head_words - 1).bit_length()), name="head")
        tail = Signal(max(1, (tail_words - 1).bit_length()), name="tail")
        unit_capacity = capacity if incoming >= outgoing else capacity * ratio
        size = Signal(unit_capacity.bit_length(), name="size")
        if incoming == outgoing:
            read_data = Array(data)[tail]
        elif incoming > outgoing:
            read_data = Array(word[beat * outgoing:(beat + 1) * outgoing] for word in data for beat in range(ratio))[tail]
        else:
            read_data = Array(Cat(*data[index * ratio:(index + 1) * ratio]) for index in range(capacity))[tail]
        count_value = size if incoming >= outgoing else size >> (ratio - 1).bit_length()
        module.d.comb += [
            self.outputs["io_count"].eq(count_value), self.outputs["io_in_ready"].eq(size < unit_capacity),
            self.outputs["io_out_valid"].eq(count_value > 0), self.outputs["io_out_bits"].eq(read_data),
        ]
        enq = self.inputs["io_in_valid"] & self.outputs["io_in_ready"]
        deq = self.outputs["io_out_valid"] & self.inputs["io_out_ready"]
        with cast(AbstractContextManager[None], module.If(enq)):
            module.d.sync += Array(data)[head].eq(self.inputs["io_in_bits"])
            if incoming == outgoing:
                module.d.sync += head.eq(Mux(head == head_words - 1, 0, head + 1))
            else:
                module.d.sync += head.eq(head + 1)
        with cast(AbstractContextManager[None], module.If(deq)):
            if incoming == outgoing:
                module.d.sync += tail.eq(Mux(tail == tail_words - 1, 0, tail + 1))
            else:
                module.d.sync += tail.eq(tail + 1)
        increment = ratio if incoming > outgoing else 1
        decrement = ratio if outgoing > incoming else 1
        module.d.sync += size.eq(size + Mux(enq, increment, 0) - Mux(deq, decrement, 0))

    def credit_counter(self, module: Module, credit: Value, debit: Value, initial: int | None = None) -> tuple[Signal, Signal]:
        depth = self.configuration.entries
        start = self.configuration.initial_credits
        if start is None:
            start = depth if initial is None else initial
        value = Signal(depth.bit_length(), init=start, name="credits")
        following = Signal.like(value, name="next_credits")
        module.d.comb += following.eq(Mux(credit != debit, Mux(credit, value + 1, value - 1), value))
        with cast(AbstractContextManager[None], module.If(credit != debit)):
            module.d.sync += value.eq(following)
        module.d.sync += Assert((~(credit & (value == depth)) | debit) & (~(debit & (value == 0)) | credit))
        return value, following

    def elaborate_credit_pipeline(self, module: Module) -> None:
        debit: Value = self.inputs["io_in_debit"]
        bits: Value = self.inputs["io_in_bits"]
        credit: Value = self.inputs["io_out_credit"]
        for index in range(self.configuration.debit_delay):
            registered_debit = Signal(name=f"debit_{index}")
            registered_bits = Signal(self.configuration.width, name=f"bits_{index}", reset_less=True)
            module.d.sync += registered_debit.eq(debit)
            with cast(AbstractContextManager[None], module.If(debit)):
                module.d.sync += registered_bits.eq(bits)
            debit, bits = registered_debit, registered_bits
        for index in range(self.configuration.credit_delay):
            registered_credit = Signal(name=f"credit_{index}")
            module.d.sync += registered_credit.eq(credit)
            credit = registered_credit
        module.d.comb += [
            self.outputs["io_in_credit"].eq(credit), self.outputs["io_out_debit"].eq(debit),
            self.outputs["io_out_bits"].eq(bits),
        ]

    def elaborate_credit_receiver(self, module: Module) -> None:
        count = self.configuration.entries
        data = [Signal(self.configuration.width, name=f"ram_{index}", reset_less=True) for index in range(count)]
        head = Signal(range(max(2, count)), name="enq_ptr")
        tail = Signal(range(max(2, count)), name="deq_ptr")
        used = Signal(range(count + 1), name="occupancy")
        empty, full = used == 0, used == count
        debit = self.inputs["io_debit"]
        ready = ~full | self.inputs["io_out_ready"]
        valid = ~empty | (Const(self.configuration.flow) & debit)
        bypass = Const(self.configuration.flow) & empty
        dequeue = valid & self.inputs["io_out_ready"]
        enq_store = debit & ready & ~(bypass & self.inputs["io_out_ready"])
        deq_store = dequeue & ~bypass
        module.d.comb += [
            self.outputs["io_out_valid"].eq(valid), self.outputs["io_credit"].eq(dequeue),
            self.outputs["io_out_bits"].eq(Mux(bypass, self.inputs["io_bits"], Array(data)[tail])),
        ]
        module.d.sync += Assert(~debit | ready)
        with cast(AbstractContextManager[None], module.If(enq_store)):
            module.d.sync += [Array(data)[head].eq(self.inputs["io_bits"]), head.eq(Mux(head == count - 1, 0, head + 1))]
        with cast(AbstractContextManager[None], module.If(deq_store)):
            module.d.sync += tail.eq(Mux(tail == count - 1, 0, tail + 1))
        module.d.sync += used.eq(used + enq_store - deq_store)


def elastic_port_specs(
    configuration: ElasticMemberConfiguration,
) -> tuple[PortSpec, ...]:
    specs = [PortSpec("clock", "input", 1), PortSpec("reset", "input", 1)]
    if configuration.input_ready_name is not None:
        specs.append(PortSpec(configuration.input_ready_name, "output", 1))
    specs.append(PortSpec(configuration.input_valid_name, "input", 1))
    specs.extend(
        PortSpec(configuration.input_prefix + suffix, "input", width)
        for suffix, width in configuration.input_fields
    )
    specs.append(PortSpec(configuration.output_ready_name, "input", 1))
    specs.append(PortSpec(configuration.output_valid_name, "output", 1))
    specs.extend(
        PortSpec(configuration.output_prefix + suffix, "output", width)
        for suffix, width in configuration.output_fields
    )
    return tuple(specs)


def connect_port_specs(
    configuration: ConnectMemberConfiguration,
) -> tuple[PortSpec, ...]:
    specs = [PortSpec("clock", "input", 1), PortSpec("reset", "input", 1)]
    if configuration.exposes_input_ready:
        specs.append(PortSpec("io_in_ready", "output", 1))
    specs.append(PortSpec("io_in_valid", "input", 1))
    specs.extend(
        PortSpec(CONNECT_INPUT_PREFIX + suffix, "input", width)
        for suffix, width in configuration.payload_fields
    )
    if configuration.exposes_output_ready:
        specs.append(PortSpec("io_out_ready", "input", 1))
    specs.append(PortSpec("io_out_valid", "output", 1))
    specs.extend(
        PortSpec(CONNECT_OUTPUT_PREFIX + suffix, "output", width)
        for suffix, width in configuration.payload_fields
    )
    specs.append(PortSpec("io_rightOutFire", "input", 1))
    if configuration.exposes_flush:
        specs.append(PortSpec("io_isFlush", "input", 1))
    if configuration.exposes_older:
        specs.append(PortSpec("io_isOlder", "input", 1))
    return tuple(specs)


class PipelineFamily(Elaboratable):
    """Export one exact queue, pipeline wrapper, or registered connect member."""

    def __init__(self, member: str | MemberConfiguration) -> None:
        if isinstance(member, SourcePipelineConfiguration):
            raise ValueError("use SourcePipeline for a parameterized adapter")
        selected = (
            member if isinstance(member, (ElasticMemberConfiguration, ConnectMemberConfiguration))
            else family_configuration(member)
        )
        if isinstance(selected, SourcePipelineConfiguration):
            raise ValueError("use SourcePipeline for a parameterized adapter")
        self.configuration: ElasticMemberConfiguration | ConnectMemberConfiguration = selected
        specs = (
            elastic_port_specs(self.configuration)
            if isinstance(self.configuration, ElasticMemberConfiguration)
            else connect_port_specs(self.configuration)
        )
        self._port_specs = specs
        self.inputs: dict[str, Signal] = {}
        self.outputs: dict[str, Signal] = {}
        for spec in specs:
            signal = Signal(spec.width, name=spec.name)
            if spec.direction == "input":
                self.inputs[spec.name] = signal
            else:
                self.outputs[spec.name] = signal

    def ports(self) -> list[Signal]:
        """Return the exact ordered public ABI. / 返回精确且有序的公开ABI。"""

        return [
            self.inputs[spec.name] if spec.direction == "input"
            else self.outputs[spec.name]
            for spec in self._port_specs
        ]

    def elaborate(self, platform: object) -> Module:
        del platform
        module = Module()
        domain = ClockDomain("sync", async_reset=True)
        domain.clk = self.inputs["clock"]
        domain.rst = self.inputs["reset"]
        module.domains += domain
        if isinstance(self.configuration, ElasticMemberConfiguration):
            self.elaborate_elastic(module, self.configuration)
        else:
            self.elaborate_connect(module, self.configuration)
        return module

    def elastic_sources(
        self,
        configuration: ElasticMemberConfiguration,
    ) -> dict[str, Value]:
        input_fields = dict(configuration.input_fields)
        constants = dict(configuration.output_constants)
        sources: dict[str, Value] = {}
        for suffix, output_width in configuration.output_fields:
            if suffix in input_fields:
                input_width = input_fields[suffix]
                if input_width != output_width:
                    raise ValueError(
                        f"{configuration.member_name}.{suffix}: "
                        f"input width {input_width} differs from output width {output_width}"
                    )
                sources[suffix] = self.inputs[configuration.input_prefix + suffix]
            elif suffix in constants:
                value = constants[suffix]
                if value < 0 or value >= 1 << output_width:
                    raise ValueError(
                        f"{configuration.member_name}.{suffix}: constant does not fit its output"
                    )
                sources[suffix] = Const(value, output_width)
            else:
                raise ValueError(
                    f"{configuration.member_name}.{suffix}: output has no payload source"
                )
        return sources

    def elaborate_elastic(
        self,
        module: Module,
        configuration: ElasticMemberConfiguration,
    ) -> None:
        sources = self.elastic_sources(configuration)
        stage_valid = [
            Signal(name=f"stage_{index}_valid")
            for index in range(configuration.stage_count)
        ]
        stage_data = [
            {
                suffix: Signal(width, name=f"stage_{index}_{suffix}", reset_less=True)
                for suffix, width in configuration.output_fields
            }
            for index in range(configuration.stage_count)
        ]
        stage_ready = [
            Signal(name=f"stage_{index}_ready")
            for index in range(configuration.stage_count)
        ]
        downstream_ready: list[Value] = [
            Const(0, 1) for _ in range(configuration.stage_count)
        ]
        for index in range(configuration.stage_count - 1, -1, -1):
            ready = (
                self.inputs[configuration.output_ready_name]
                if index == configuration.stage_count - 1
                else stage_ready[index + 1]
            )
            downstream_ready[index] = ready
            module.d.comb += stage_ready[index].eq(ready | ~stage_valid[index])

        if configuration.input_ready_name is not None:
            module.d.comb += self.outputs[configuration.input_ready_name].eq(
                stage_ready[0]
            )
        module.d.comb += self.outputs[configuration.output_valid_name].eq(
            stage_valid[-1]
        )
        for suffix, _width in configuration.output_fields:
            module.d.comb += self.outputs[
                configuration.output_prefix + suffix
            ].eq(stage_data[-1][suffix])

        input_valid = self.inputs[configuration.input_valid_name]
        for index in range(configuration.stage_count):
            enqueue_valid = input_valid if index == 0 else stage_valid[index - 1]
            enqueue_fire = enqueue_valid & stage_ready[index]
            dequeue_fire = stage_valid[index] & downstream_ready[index]
            module.d.sync += stage_valid[index].eq(
                enqueue_fire | (stage_valid[index] & ~dequeue_fire)
            )
            with cast(AbstractContextManager[None], module.If(enqueue_fire)):
                for suffix, _width in configuration.output_fields:
                    source = (
                        sources[suffix]
                        if index == 0
                        else stage_data[index - 1][suffix]
                    )
                    module.d.sync += stage_data[index][suffix].eq(source)

    def elaborate_connect(
        self,
        module: Module,
        configuration: ConnectMemberConfiguration,
    ) -> None:
        valid = Signal(name="valid")
        can_accept: Value = Const(1, 1)
        if configuration.exposes_output_ready:
            can_accept = self.inputs["io_out_ready"] | ~valid
            if configuration.exposes_older:
                can_accept = can_accept | self.inputs["io_isOlder"]
        if configuration.exposes_input_ready:
            module.d.comb += self.outputs["io_in_ready"].eq(can_accept)
        module.d.comb += self.outputs["io_out_valid"].eq(valid)

        data = {
            suffix: Signal(width, name=f"data_{suffix}", reset_less=True)
            for suffix, width in configuration.payload_fields
        }
        for suffix, _width in configuration.payload_fields:
            module.d.comb += self.outputs[
                CONNECT_OUTPUT_PREFIX + suffix
            ].eq(data[suffix])

        input_fire = self.inputs["io_in_valid"] & can_accept
        with cast(AbstractContextManager[None], module.If(input_fire)):
            for suffix, _width in configuration.payload_fields:
                module.d.sync += data[suffix].eq(
                    self.inputs[CONNECT_INPUT_PREFIX + suffix]
                )

        next_valid = input_fire | (
            ~self.inputs["io_rightOutFire"] & valid
        )
        if configuration.exposes_flush:
            next_valid = ~self.inputs["io_isFlush"] & next_valid
        module.d.sync += valid.eq(next_valid)


# =============================================================================
# Public Adapter
# =============================================================================
def family_configuration(member_name: str) -> MemberConfiguration:
    """Return one finite, exact member configuration. / 返回一个有限且精确的成员配置。"""

    if member_name in _PIPELINE_CONFIGURATIONS:
        return _PIPELINE_CONFIGURATIONS[member_name]
    if member_name in _CONNECT_CONFIGURATIONS:
        return _CONNECT_CONFIGURATIONS[member_name]
    if member_name in _QUEUE_CONFIGURATIONS:
        return _QUEUE_CONFIGURATIONS[member_name]
    if member_name in SOURCE_PIPELINE_MEMBERS:
        return SourcePipelineConfiguration(member_name=member_name)
    raise ValueError(f"unknown pipeline family member: {member_name}")


def configured_member(configuration: object) -> MemberConfiguration:
    if isinstance(
        configuration, (ElasticMemberConfiguration, ConnectMemberConfiguration, SourcePipelineConfiguration)
    ):
        return configuration
    if isinstance(configuration, str):
        return family_configuration(configuration)
    if isinstance(configuration, Mapping):
        member_name = configuration.get("module", configuration.get("member"))
        if isinstance(member_name, str):
            if member_name in SOURCE_PIPELINE_MEMBERS:
                values = {key: value for key, value in configuration.items() if key not in ("module", "member")}
                return SourcePipelineConfiguration(member_name=member_name, **values)
            return family_configuration(member_name)
    if configuration is None:
        return family_configuration(COVERED_MODULES[0])
    raise TypeError("configuration must select a covered module by its exact name")


def build_verilog(
    configuration: object,
    injected_dependencies: Mapping[str, object] | None,
) -> str:
    """Export one deterministic, same-named native Amaranth module."""

    del injected_dependencies
    selected = configured_member(configuration)
    design = SourcePipeline(selected) if isinstance(selected, SourcePipelineConfiguration) else PipelineFamily(selected)
    return verilog.convert(
        design,
        name=selected.member_name,
        ports=design.ports(),
        emit_src=False,
    )


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    print(build_verilog(COVERED_MODULES[0], {}))


if __name__ == "__main__":
    main()
