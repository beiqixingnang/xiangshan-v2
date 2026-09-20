"""UHSC V2 debug-trigger family aggregate.
昆明湖 V2 调试触发器 family 聚合。

The locked V2 hierarchy emits Debug, MemTrigger, MemTrigger_3, and
VSegmentTrigger from the NewCSR debug source.  Exact ANSI ports are frozen in
an explicit catalog; bounded trigger predicates are implemented without
claiming the complete NewCSR parent closure.
"""

from __future__ import annotations

from typing import Any, cast

from amaranth import ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
__all__ = ["COVERED_MODULES", "DebugFamily", "build_verilog", "main"]
COVERED_MODULES = ("Debug", "MemTrigger", "MemTrigger_3", "VSegmentTrigger")
SOURCE_PATHS = ("upstream/src/main/scala/xiangshan/backend/fu/NewCSR/Debug.scala",)

# BEGIN LOCKED PORT CATALOG
LOCKED_PORT_SPECS: dict[str, tuple[tuple[str, str, int], ...]] = {
    "Debug": (
        (
            "clock",
            "input",
            1,
        ),
        (
            "io_in_trapInfo_valid",
            "input",
            1,
        ),
        (
            "io_in_trapInfo_bits_trapVec",
            "input",
            64,
        ),
        (
            "io_in_trapInfo_bits_isDebugIntr",
            "input",
            1,
        ),
        (
            "io_in_trapInfo_bits_isInterrupt",
            "input",
            1,
        ),
        (
            "io_in_trapInfo_bits_singleStep",
            "input",
            1,
        ),
        (
            "io_in_trapInfo_bits_trigger",
            "input",
            4,
        ),
        (
            "io_in_trapInfo_bits_criticalErrorState",
            "input",
            1,
        ),
        (
            "io_in_privState_PRVM",
            "input",
            2,
        ),
        (
            "io_in_privState_V",
            "input",
            1,
        ),
        (
            "io_in_debugMode",
            "input",
            1,
        ),
        (
            "io_in_dcsr_CETRIG",
            "input",
            1,
        ),
        (
            "io_in_dcsr_EBREAKVS",
            "input",
            1,
        ),
        (
            "io_in_dcsr_EBREAKVU",
            "input",
            1,
        ),
        (
            "io_in_dcsr_EBREAKM",
            "input",
            1,
        ),
        (
            "io_in_dcsr_EBREAKS",
            "input",
            1,
        ),
        (
            "io_in_dcsr_EBREAKU",
            "input",
            1,
        ),
        (
            "io_in_tselect_ALL",
            "input",
            2,
        ),
        (
            "io_in_tdata1Selected_DATA",
            "input",
            59,
        ),
        (
            "io_in_tdata2Selected_ALL",
            "input",
            64,
        ),
        (
            "io_in_tdata1Vec_0_TYPE",
            "input",
            4,
        ),
        (
            "io_in_tdata1Vec_0_DATA",
            "input",
            59,
        ),
        (
            "io_in_tdata1Vec_1_TYPE",
            "input",
            4,
        ),
        (
            "io_in_tdata1Vec_1_DATA",
            "input",
            59,
        ),
        (
            "io_in_tdata1Vec_2_TYPE",
            "input",
            4,
        ),
        (
            "io_in_tdata1Vec_2_DATA",
            "input",
            59,
        ),
        (
            "io_in_tdata1Vec_3_TYPE",
            "input",
            4,
        ),
        (
            "io_in_tdata1Vec_3_DATA",
            "input",
            59,
        ),
        (
            "io_in_triggerCanRaiseBpExp",
            "input",
            1,
        ),
        (
            "io_in_tdata1Update",
            "input",
            1,
        ),
        (
            "io_in_tdata2Update",
            "input",
            1,
        ),
        (
            "io_in_tdata1Wdata_TYPE",
            "input",
            4,
        ),
        (
            "io_in_tdata1Wdata_DATA",
            "input",
            59,
        ),
        (
            "io_out_triggerFrontendChange",
            "output",
            1,
        ),
        (
            "io_out_newTriggerChainIsLegal",
            "output",
            1,
        ),
        (
            "io_out_memTrigger_tUpdate_valid",
            "output",
            1,
        ),
        (
            "io_out_memTrigger_tUpdate_bits_addr",
            "output",
            2,
        ),
        (
            "io_out_memTrigger_tUpdate_bits_tdata_matchType",
            "output",
            2,
        ),
        (
            "io_out_memTrigger_tUpdate_bits_tdata_select",
            "output",
            1,
        ),
        (
            "io_out_memTrigger_tUpdate_bits_tdata_action",
            "output",
            4,
        ),
        (
            "io_out_memTrigger_tUpdate_bits_tdata_chain",
            "output",
            1,
        ),
        (
            "io_out_memTrigger_tUpdate_bits_tdata_store",
            "output",
            1,
        ),
        (
            "io_out_memTrigger_tUpdate_bits_tdata_load",
            "output",
            1,
        ),
        (
            "io_out_memTrigger_tUpdate_bits_tdata_tdata2",
            "output",
            64,
        ),
        (
            "io_out_memTrigger_tEnableVec_0",
            "output",
            1,
        ),
        (
            "io_out_memTrigger_tEnableVec_1",
            "output",
            1,
        ),
        (
            "io_out_memTrigger_tEnableVec_2",
            "output",
            1,
        ),
        (
            "io_out_memTrigger_tEnableVec_3",
            "output",
            1,
        ),
        (
            "io_out_memTrigger_debugMode",
            "output",
            1,
        ),
        (
            "io_out_memTrigger_triggerCanRaiseBpExp",
            "output",
            1,
        ),
        (
            "io_out_frontendTrigger_tUpdate_valid",
            "output",
            1,
        ),
        (
            "io_out_frontendTrigger_tUpdate_bits_addr",
            "output",
            2,
        ),
        (
            "io_out_frontendTrigger_tUpdate_bits_tdata_matchType",
            "output",
            2,
        ),
        (
            "io_out_frontendTrigger_tUpdate_bits_tdata_select",
            "output",
            1,
        ),
        (
            "io_out_frontendTrigger_tUpdate_bits_tdata_action",
            "output",
            4,
        ),
        (
            "io_out_frontendTrigger_tUpdate_bits_tdata_chain",
            "output",
            1,
        ),
        (
            "io_out_frontendTrigger_tUpdate_bits_tdata_tdata2",
            "output",
            64,
        ),
        (
            "io_out_frontendTrigger_tEnableVec_0",
            "output",
            1,
        ),
        (
            "io_out_frontendTrigger_tEnableVec_1",
            "output",
            1,
        ),
        (
            "io_out_frontendTrigger_tEnableVec_2",
            "output",
            1,
        ),
        (
            "io_out_frontendTrigger_tEnableVec_3",
            "output",
            1,
        ),
        (
            "io_out_frontendTrigger_debugMode",
            "output",
            1,
        ),
        (
            "io_out_frontendTrigger_triggerCanRaiseBpExp",
            "output",
            1,
        ),
        (
            "io_out_hasDebugTrap",
            "output",
            1,
        ),
        (
            "io_out_hasDebugIntr",
            "output",
            1,
        ),
        (
            "io_out_hasSingleStep",
            "output",
            1,
        ),
        (
            "io_out_triggerEnterDebugMode",
            "output",
            1,
        ),
        (
            "io_out_hasDebugEbreakException",
            "output",
            1,
        ),
        (
            "io_out_breakPoint",
            "output",
            1,
        ),
        (
            "io_out_criticalErrorStateEnterDebug",
            "output",
            1,
        ),
    ),
    "MemTrigger": (
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_0_matchType",
            "input",
            2,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_0_select",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_0_timing",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_0_action",
            "input",
            4,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_0_chain",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_0_load",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_0_tdata2",
            "input",
            64,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_1_matchType",
            "input",
            2,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_1_select",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_1_timing",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_1_action",
            "input",
            4,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_1_chain",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_1_load",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_1_tdata2",
            "input",
            64,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_2_matchType",
            "input",
            2,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_2_select",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_2_timing",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_2_action",
            "input",
            4,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_2_chain",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_2_load",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_2_tdata2",
            "input",
            64,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_3_matchType",
            "input",
            2,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_3_select",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_3_timing",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_3_action",
            "input",
            4,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_3_chain",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_3_load",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_3_tdata2",
            "input",
            64,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tEnableVec_0",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tEnableVec_1",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tEnableVec_2",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tEnableVec_3",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_debugMode",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_triggerCanRaiseBpExp",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromLoadStore_vaddr",
            "input",
            50,
        ),
        (
            "tdataVec_io_fromLoadStore_isVectorUnitStride",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromLoadStore_mask",
            "input",
            16,
        ),
        (
            "tdataVec_io_toLoadStore_triggerAction",
            "output",
            4,
        ),
        (
            "tdataVec_io_toLoadStore_triggerVaddr",
            "output",
            50,
        ),
        (
            "tdataVec_io_toLoadStore_triggerMask",
            "output",
            16,
        ),
        (
            "tdataVec_io_isPrf",
            "input",
            1,
        ),
    ),
    "MemTrigger_3": (
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_0_matchType",
            "input",
            2,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_0_select",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_0_timing",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_0_action",
            "input",
            4,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_0_chain",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_0_store",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_0_tdata2",
            "input",
            64,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_1_matchType",
            "input",
            2,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_1_select",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_1_timing",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_1_action",
            "input",
            4,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_1_chain",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_1_store",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_1_tdata2",
            "input",
            64,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_2_matchType",
            "input",
            2,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_2_select",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_2_timing",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_2_action",
            "input",
            4,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_2_chain",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_2_store",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_2_tdata2",
            "input",
            64,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_3_matchType",
            "input",
            2,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_3_select",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_3_timing",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_3_action",
            "input",
            4,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_3_chain",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_3_store",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_3_tdata2",
            "input",
            64,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tEnableVec_0",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tEnableVec_1",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tEnableVec_2",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tEnableVec_3",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_debugMode",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_triggerCanRaiseBpExp",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromLoadStore_vaddr",
            "input",
            50,
        ),
        (
            "tdataVec_io_fromLoadStore_isVectorUnitStride",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromLoadStore_mask",
            "input",
            16,
        ),
        (
            "tdataVec_io_toLoadStore_triggerAction",
            "output",
            4,
        ),
        (
            "tdataVec_io_toLoadStore_triggerVaddr",
            "output",
            50,
        ),
        (
            "tdataVec_io_isCbo",
            "input",
            1,
        ),
    ),
    "VSegmentTrigger": (
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_0_matchType",
            "input",
            2,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_0_select",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_0_timing",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_0_action",
            "input",
            4,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_0_chain",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_0_store",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_0_load",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_0_tdata2",
            "input",
            64,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_1_matchType",
            "input",
            2,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_1_select",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_1_timing",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_1_action",
            "input",
            4,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_1_chain",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_1_store",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_1_load",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_1_tdata2",
            "input",
            64,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_2_matchType",
            "input",
            2,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_2_select",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_2_timing",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_2_action",
            "input",
            4,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_2_chain",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_2_store",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_2_load",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_2_tdata2",
            "input",
            64,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_3_matchType",
            "input",
            2,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_3_select",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_3_timing",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_3_action",
            "input",
            4,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_3_chain",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_3_store",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_3_load",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tdataVec_3_tdata2",
            "input",
            64,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tEnableVec_0",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tEnableVec_1",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tEnableVec_2",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_tEnableVec_3",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_debugMode",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromCsrTrigger_triggerCanRaiseBpExp",
            "input",
            1,
        ),
        (
            "tdataVec_io_fromLoadStore_vaddr",
            "input",
            50,
        ),
        (
            "tdataVec_io_toLoadStore_triggerAction",
            "output",
            4,
        ),
        (
            "tdataVec_io_memType",
            "input",
            1,
        ),
    ),
}
PORT_SPECS = LOCKED_PORT_SPECS
# END LOCKED PORT CATALOG
PORT_SPECS = LOCKED_PORT_SPECS


# =============================================================================
# Implementation
# =============================================================================
class DebugFamily(Elaboratable):
    """One locked debug family member. / 一个锁定调试 family 成员。"""

    def __init__(self, member: str = "Debug") -> None:
        """Declare exact flattened ports. / 声明精确扁平端口。"""

        if member not in PORT_SPECS:
            raise ValueError(member)
        self.member = member
        self.specs = PORT_SPECS[member]
        self.ports = {name: Signal(width, name=name) for name, _direction, width in self.specs}

    def _debug(self, module: Module) -> None:
        """Implement the locked Debug control and two-cycle update pulses."""

        p = self.ports
        priv = p["io_in_privState_PRVM"]
        virtual = p["io_in_privState_V"]
        mode_m = priv.all()
        mode_s = priv == 1
        mode_u = priv == 0
        mode_hs = ~virtual & mode_s
        mode_hu = ~virtual & mode_u
        mode_vs = virtual & mode_s
        mode_vu = virtual & mode_u
        valid = p["io_in_trapInfo_valid"]
        interrupt = p["io_in_trapInfo_bits_isInterrupt"]
        has_debug_intr = valid & interrupt & p["io_in_trapInfo_bits_isDebugIntr"]
        has_exp = valid & ~interrupt
        trigger = p["io_in_trapInfo_bits_trigger"]
        trap_vec = p["io_in_trapInfo_bits_trapVec"]
        ebreak_mode = (
            (mode_m & p["io_in_dcsr_EBREAKM"])
            | (mode_hs & p["io_in_dcsr_EBREAKS"])
            | (mode_hu & p["io_in_dcsr_EBREAKU"])
            | (mode_vs & p["io_in_dcsr_EBREAKVS"])
            | (mode_vu & p["io_in_dcsr_EBREAKVU"])
        )
        debug_ebreak = has_exp & trap_vec[3] & trigger.any() & ebreak_mode
        trigger_debug = has_exp & (trigger == 1)
        single_step = has_exp & p["io_in_trapInfo_bits_singleStep"]
        critical_debug = (
            p["io_in_trapInfo_bits_criticalErrorState"]
            & p["io_in_dcsr_CETRIG"]
        )

        selected = p["io_in_tdata1Selected_DATA"]
        write_data = p["io_in_tdata1Wdata_DATA"]
        selected_type = p["io_in_tdata1Wdata_TYPE"] == 6
        trigger_update = p["io_in_tdata1Update"] | p["io_in_tdata2Update"]
        frontend_update = (
            p["io_in_tdata1Update"] & selected_type & write_data[2]
            | selected[2] & trigger_update
        )
        mem_update = (
            p["io_in_tdata1Update"] & selected_type
            & (cast(Any, write_data[1]) | write_data[0])
            | (cast(Any, selected[1]) | selected[0]) & trigger_update
        )
        frontend_pipe = Signal(name="io_out_frontendTrigger_tUpdate_valid_REG",
                               reset_less=True)
        frontend_pipe_1 = Signal(name="io_out_frontendTrigger_tUpdate_valid_REG_1",
                                 reset_less=True)
        mem_pipe = Signal(name="io_out_memTrigger_tUpdate_valid_REG",
                          reset_less=True)
        mem_pipe_1 = Signal(name="io_out_memTrigger_tUpdate_valid_REG_1",
                            reset_less=True)
        module.d.sync += [
            frontend_pipe.eq(frontend_update),
            frontend_pipe_1.eq(frontend_pipe),
            mem_pipe.eq(mem_update),
            mem_pipe_1.eq(mem_pipe),
        ]

        chain_0 = (p["io_in_tselect_ALL"] == 0) | p["io_in_tdata1Vec_0_DATA"][11]
        chain_1 = (p["io_in_tselect_ALL"] == 1) | p["io_in_tdata1Vec_1_DATA"][11]
        chain_2 = (p["io_in_tselect_ALL"] == 2) | p["io_in_tdata1Vec_2_DATA"][11]
        chain_3 = p["io_in_tselect_ALL"].all() | p["io_in_tdata1Vec_3_DATA"][11]
        module.d.comb += [
            p["io_out_triggerFrontendChange"].eq(frontend_update),
            p["io_out_newTriggerChainIsLegal"].eq(
                ~((chain_0 & chain_1) | (chain_1 & chain_2) | (chain_2 & chain_3))
            ),
            p["io_out_memTrigger_tUpdate_valid"].eq(mem_pipe_1),
            p["io_out_frontendTrigger_tUpdate_valid"].eq(frontend_pipe_1),
        ]

        for prefix in ("io_out_memTrigger", "io_out_frontendTrigger"):
            module.d.comb += [
                p[f"{prefix}_tUpdate_bits_addr"].eq(p["io_in_tselect_ALL"]),
                p[f"{prefix}_tUpdate_bits_tdata_matchType"].eq(selected[7:9]),
                p[f"{prefix}_tUpdate_bits_tdata_select"].eq(selected[21]),
                p[f"{prefix}_tUpdate_bits_tdata_action"].eq(selected[12:16]),
                p[f"{prefix}_tUpdate_bits_tdata_chain"].eq(selected[11]),
                p[f"{prefix}_tUpdate_bits_tdata_tdata2"].eq(
                    p["io_in_tdata2Selected_ALL"]),
                p[f"{prefix}_debugMode"].eq(p["io_in_debugMode"]),
                p[f"{prefix}_triggerCanRaiseBpExp"].eq(
                    p["io_in_triggerCanRaiseBpExp"]),
            ]
        module.d.comb += [
            p["io_out_memTrigger_tUpdate_bits_tdata_store"].eq(selected[1]),
            p["io_out_memTrigger_tUpdate_bits_tdata_load"].eq(selected[0]),
        ]

        for index in range(4):
            data = p[f"io_in_tdata1Vec_{index}_DATA"]
            enabled = (
                (p[f"io_in_tdata1Vec_{index}_TYPE"] == 6)
                & ((data[6] & mode_m) | (data[4] & mode_hs)
                   | (data[3] & mode_hu) | (data[24] & mode_vs)
                   | (data[23] & mode_vu))
            )
            module.d.comb += [
                p[f"io_out_memTrigger_tEnableVec_{index}"].eq(
                    enabled & (cast(Any, data[1]) | data[0])),
                p[f"io_out_frontendTrigger_tEnableVec_{index}"].eq(
                    enabled & data[2]),
            ]

        module.d.comb += [
            p["io_out_hasDebugTrap"].eq(
                debug_ebreak | trigger_debug | single_step
                | critical_debug | has_debug_intr),
            p["io_out_hasDebugIntr"].eq(has_debug_intr),
            p["io_out_hasSingleStep"].eq(single_step),
            p["io_out_triggerEnterDebugMode"].eq(trigger_debug),
            p["io_out_hasDebugEbreakException"].eq(debug_ebreak),
            p["io_out_breakPoint"].eq(trap_vec[3]),
            p["io_out_criticalErrorStateEnterDebug"].eq(critical_debug),
        ]

    @staticmethod
    def _address_match(address: Any, tdata: Any, match_type: Any) -> Any:
        """Implement the locked EQ/GE/LT trigger comparison."""

        operand = tdata[:50]
        return Mux(match_type == 3, address < operand,
                   Mux(match_type == 2, address >= operand,
                       (match_type == 0) & (address == operand)))

    def _trigger(self, module: Module) -> None:
        """Implement MemTrigger, MemTrigger_3, and VSegmentTrigger exactly."""

        p = self.ports
        address = p["tdataVec_io_fromLoadStore_vaddr"]
        debug_mode = p["tdataVec_io_fromCsrTrigger_debugMode"]
        hits: list[Any] = []
        chains: list[Any] = []
        timings: list[Any] = []
        actions: list[Any] = []
        tdata_values: list[Any] = []
        for index in range(4):
            prefix = f"tdataVec_io_fromCsrTrigger_tdataVec_{index}"
            match_type = p[f"{prefix}_matchType"]
            select = p[f"{prefix}_select"]
            timing = p[f"{prefix}_timing"]
            action = p[f"{prefix}_action"]
            chain = p[f"{prefix}_chain"]
            tdata = p[f"{prefix}_tdata2"]
            enabled = p[f"tdataVec_io_fromCsrTrigger_tEnableVec_{index}"]
            if self.member == "VSegmentTrigger":
                access = Mux(p["tdataVec_io_memType"],
                             p[f"{prefix}_load"], p[f"{prefix}_store"])
                hit = (~select & ~debug_mode & enabled & access
                       & self._address_match(address, tdata, match_type))
            elif self.member == "MemTrigger":
                load = p[f"{prefix}_load"]
                scalar = (~select & ~debug_mode & ~p["tdataVec_io_isPrf"]
                          & enabled & load
                          & self._address_match(address, tdata, match_type))
                lane = (Const(1, 16) << tdata[:4])[:16]
                vector = (~select & ~debug_mode & enabled & load
                          & (address[4:50] == tdata[4:64])
                          & (lane & p["tdataVec_io_fromLoadStore_mask"]).any())
                hit = Mux(p["tdataVec_io_fromLoadStore_isVectorUnitStride"],
                          vector, scalar)
            else:
                store = p[f"{prefix}_store"]
                scalar = (~select & ~debug_mode & enabled & store
                          & self._address_match(address, tdata, match_type))
                lane = (Const(1, 16) << tdata[:4])[:16]
                vector = (~select & ~debug_mode & enabled & store
                          & (address[4:50] == tdata[4:64])
                          & (lane & p["tdataVec_io_fromLoadStore_mask"]).any())
                line_base = cast(Any, address[6:50]) << 6
                line_last = line_base | Const(0x3F, 50)
                line_match = Mux(
                    match_type == 3, line_base < tdata[:50],
                    Mux(match_type == 2, line_last >= tdata[:50],
                        (match_type == 0) & (address[6:50] == tdata[6:50])),
                )
                cbo = (~select & ~debug_mode & enabled & store
                       & p["tdataVec_io_isCbo"] & line_match)
                hit = Mux(p["tdataVec_io_isCbo"], cbo,
                          Mux(p["tdataVec_io_fromLoadStore_isVectorUnitStride"],
                              vector, scalar))
            hits.append(hit)
            chains.append(chain)
            timings.append(timing)
            actions.append(action)
            tdata_values.append(tdata)

        can_fire: list[Any] = [hits[0] & ~chains[0]]
        for index in range(1, 4):
            previous = index - 1
            chain_ok = (chains[previous] & hits[previous]) | ~chains[previous]
            timing_ok = (
                chains[previous] & ~chains[index]
                & (timings[previous] == timings[index])
            ) | ~chains[previous]
            can_fire.append(chain_ok & timing_ok & hits[index] & ~chains[index])

        debug_hits = [can_fire[index] & (actions[index] == 1) for index in range(4)]
        bp_hits = [can_fire[index] & (actions[index] == 0) for index in range(4)]
        debug_fire: Any = Const(0)
        bp_candidate: Any = Const(0)
        for value in debug_hits:
            debug_fire = debug_fire | value
        for value in bp_hits:
            bp_candidate = bp_candidate | value
        bp_fire = bp_candidate & p["tdataVec_io_fromCsrTrigger_triggerCanRaiseBpExp"]
        trigger_fire = [Mux(debug_fire, debug_hits[index], bp_fire & bp_hits[index])
                        for index in range(4)]
        trigger_any: Any = Const(0)
        for value in trigger_fire:
            trigger_any = trigger_any | value
        selected_tdata = Mux(
            trigger_fire[0], tdata_values[0],
            Mux(trigger_fire[1], tdata_values[1],
                Mux(trigger_fire[2], tdata_values[2], tdata_values[3])),
        )
        module.d.comb += p["tdataVec_io_toLoadStore_triggerAction"].eq(
            Mux(debug_fire, 1, Mux(bp_fire, 0, 15)))
        if "tdataVec_io_toLoadStore_triggerVaddr" in p:
            module.d.comb += p["tdataVec_io_toLoadStore_triggerVaddr"].eq(
                Mux(trigger_any, selected_tdata[:50], 0))
        if "tdataVec_io_toLoadStore_triggerMask" in p:
            module.d.comb += p["tdataVec_io_toLoadStore_triggerMask"].eq(
                Mux(trigger_any, (Const(1, 16) << selected_tdata[:4])[:16], 0))

    def elaborate(self, platform: Any) -> Module:
        """Implement bounded debug entry and trigger defaults. / 实现有界调试进入和触发默认行为。"""

        del platform
        module = Module()
        if self.member == "Debug":
            domain = ClockDomain("sync", reset_less=True)
            domain.clk = self.ports["clock"]
            module.domains += domain
            self._debug(module)
        else:
            self._trigger(module)
        return module


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration: Any, injected_dependencies: Any) -> str:
    """Export one deterministic same-name debug member. / 导出确定性的同名调试成员。"""

    del injected_dependencies
    member = "Debug"
    if isinstance(configuration, dict): member = str(configuration.get("module", member))
    elif isinstance(configuration, str): member = configuration
    top = DebugFamily(member)
    return verilog.convert(top, name=member, ports=[top.ports[n] for n, _d, _w in top.specs], emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    """Print default Debug RTL. / 打印默认 Debug RTL。"""

    print(build_verilog({"module": "Debug"}, {}))


if __name__ == "__main__":
    main()
