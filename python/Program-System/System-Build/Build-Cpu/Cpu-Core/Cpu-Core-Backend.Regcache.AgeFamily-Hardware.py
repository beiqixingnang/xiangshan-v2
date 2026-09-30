"""UHSC V2 age and register-cache family aggregate.
昆明湖 V2 年龄与寄存器缓存 family 聚合。

The locked V2 hierarchy emits several specializations from NewAgeDetector,
RegCacheAgeDetector, RegCacheAgeTimer, RegCacheDataModule, and
RegCacheTagModule.  This Build keeps every exact ANSI surface in an explicit
catalog while sharing source-backed bounded age, valid, data, and tag logic.
"""

from __future__ import annotations

from typing import Any, cast

from amaranth import Array, Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
__all__ = ["COVERED_MODULES", "AgeFamily", "build_verilog", "main"]

COVERED_MODULES: tuple[str, ...] = (
    "NewAgeDetector", "NewAgeDetector_6", "RegCacheAgeDetector", "RegCacheAgeDetector_1",
    "RegCacheAgeTimer", "RegCacheAgeTimer_1", "RegCacheDataModule", "RegCacheDataModule_1",
    "RegCacheTagModule", "RegCacheTagModule_1",
)


PortSpec = tuple[str, str, int]

PORT_SPECS: dict[str, tuple[PortSpec, ...]] = {
    'NewAgeDetector': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_enq_0', 'input', 1),
        ('io_enq_1', 'input', 1),
        ('io_canIssue_0', 'input', 2),
        ('io_canIssue_1', 'input', 2),
        ('io_out_0', 'output', 2),
        ('io_out_1', 'output', 2),
    ),
    'NewAgeDetector_6': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_enq_0', 'input', 1),
        ('io_enq_1', 'input', 1),
        ('io_canIssue_0', 'input', 2),
        ('io_out_0', 'output', 2),
    ),
    'RegCacheAgeDetector': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_ageInfo_0_1', 'input', 1),
        ('io_ageInfo_0_2', 'input', 1),
        ('io_ageInfo_0_3', 'input', 1),
        ('io_ageInfo_0_4', 'input', 1),
        ('io_ageInfo_0_5', 'input', 1),
        ('io_ageInfo_0_6', 'input', 1),
        ('io_ageInfo_0_7', 'input', 1),
        ('io_ageInfo_0_8', 'input', 1),
        ('io_ageInfo_0_9', 'input', 1),
        ('io_ageInfo_0_10', 'input', 1),
        ('io_ageInfo_0_11', 'input', 1),
        ('io_ageInfo_0_12', 'input', 1),
        ('io_ageInfo_0_13', 'input', 1),
        ('io_ageInfo_0_14', 'input', 1),
        ('io_ageInfo_0_15', 'input', 1),
        ('io_ageInfo_1_2', 'input', 1),
        ('io_ageInfo_1_3', 'input', 1),
        ('io_ageInfo_1_4', 'input', 1),
        ('io_ageInfo_1_5', 'input', 1),
        ('io_ageInfo_1_6', 'input', 1),
        ('io_ageInfo_1_7', 'input', 1),
        ('io_ageInfo_1_8', 'input', 1),
        ('io_ageInfo_1_9', 'input', 1),
        ('io_ageInfo_1_10', 'input', 1),
        ('io_ageInfo_1_11', 'input', 1),
        ('io_ageInfo_1_12', 'input', 1),
        ('io_ageInfo_1_13', 'input', 1),
        ('io_ageInfo_1_14', 'input', 1),
        ('io_ageInfo_1_15', 'input', 1),
        ('io_ageInfo_2_3', 'input', 1),
        ('io_ageInfo_2_4', 'input', 1),
        ('io_ageInfo_2_5', 'input', 1),
        ('io_ageInfo_2_6', 'input', 1),
        ('io_ageInfo_2_7', 'input', 1),
        ('io_ageInfo_2_8', 'input', 1),
        ('io_ageInfo_2_9', 'input', 1),
        ('io_ageInfo_2_10', 'input', 1),
        ('io_ageInfo_2_11', 'input', 1),
        ('io_ageInfo_2_12', 'input', 1),
        ('io_ageInfo_2_13', 'input', 1),
        ('io_ageInfo_2_14', 'input', 1),
        ('io_ageInfo_2_15', 'input', 1),
        ('io_ageInfo_3_4', 'input', 1),
        ('io_ageInfo_3_5', 'input', 1),
        ('io_ageInfo_3_6', 'input', 1),
        ('io_ageInfo_3_7', 'input', 1),
        ('io_ageInfo_3_8', 'input', 1),
        ('io_ageInfo_3_9', 'input', 1),
        ('io_ageInfo_3_10', 'input', 1),
        ('io_ageInfo_3_11', 'input', 1),
        ('io_ageInfo_3_12', 'input', 1),
        ('io_ageInfo_3_13', 'input', 1),
        ('io_ageInfo_3_14', 'input', 1),
        ('io_ageInfo_3_15', 'input', 1),
        ('io_ageInfo_4_5', 'input', 1),
        ('io_ageInfo_4_6', 'input', 1),
        ('io_ageInfo_4_7', 'input', 1),
        ('io_ageInfo_4_8', 'input', 1),
        ('io_ageInfo_4_9', 'input', 1),
        ('io_ageInfo_4_10', 'input', 1),
        ('io_ageInfo_4_11', 'input', 1),
        ('io_ageInfo_4_12', 'input', 1),
        ('io_ageInfo_4_13', 'input', 1),
        ('io_ageInfo_4_14', 'input', 1),
        ('io_ageInfo_4_15', 'input', 1),
        ('io_ageInfo_5_6', 'input', 1),
        ('io_ageInfo_5_7', 'input', 1),
        ('io_ageInfo_5_8', 'input', 1),
        ('io_ageInfo_5_9', 'input', 1),
        ('io_ageInfo_5_10', 'input', 1),
        ('io_ageInfo_5_11', 'input', 1),
        ('io_ageInfo_5_12', 'input', 1),
        ('io_ageInfo_5_13', 'input', 1),
        ('io_ageInfo_5_14', 'input', 1),
        ('io_ageInfo_5_15', 'input', 1),
        ('io_ageInfo_6_7', 'input', 1),
        ('io_ageInfo_6_8', 'input', 1),
        ('io_ageInfo_6_9', 'input', 1),
        ('io_ageInfo_6_10', 'input', 1),
        ('io_ageInfo_6_11', 'input', 1),
        ('io_ageInfo_6_12', 'input', 1),
        ('io_ageInfo_6_13', 'input', 1),
        ('io_ageInfo_6_14', 'input', 1),
        ('io_ageInfo_6_15', 'input', 1),
        ('io_ageInfo_7_8', 'input', 1),
        ('io_ageInfo_7_9', 'input', 1),
        ('io_ageInfo_7_10', 'input', 1),
        ('io_ageInfo_7_11', 'input', 1),
        ('io_ageInfo_7_12', 'input', 1),
        ('io_ageInfo_7_13', 'input', 1),
        ('io_ageInfo_7_14', 'input', 1),
        ('io_ageInfo_7_15', 'input', 1),
        ('io_ageInfo_8_9', 'input', 1),
        ('io_ageInfo_8_10', 'input', 1),
        ('io_ageInfo_8_11', 'input', 1),
        ('io_ageInfo_8_12', 'input', 1),
        ('io_ageInfo_8_13', 'input', 1),
        ('io_ageInfo_8_14', 'input', 1),
        ('io_ageInfo_8_15', 'input', 1),
        ('io_ageInfo_9_10', 'input', 1),
        ('io_ageInfo_9_11', 'input', 1),
        ('io_ageInfo_9_12', 'input', 1),
        ('io_ageInfo_9_13', 'input', 1),
        ('io_ageInfo_9_14', 'input', 1),
        ('io_ageInfo_9_15', 'input', 1),
        ('io_ageInfo_10_11', 'input', 1),
        ('io_ageInfo_10_12', 'input', 1),
        ('io_ageInfo_10_13', 'input', 1),
        ('io_ageInfo_10_14', 'input', 1),
        ('io_ageInfo_10_15', 'input', 1),
        ('io_ageInfo_11_12', 'input', 1),
        ('io_ageInfo_11_13', 'input', 1),
        ('io_ageInfo_11_14', 'input', 1),
        ('io_ageInfo_11_15', 'input', 1),
        ('io_ageInfo_12_13', 'input', 1),
        ('io_ageInfo_12_14', 'input', 1),
        ('io_ageInfo_12_15', 'input', 1),
        ('io_ageInfo_13_14', 'input', 1),
        ('io_ageInfo_13_15', 'input', 1),
        ('io_ageInfo_14_15', 'input', 1),
        ('io_out_0', 'output', 4),
        ('io_out_1', 'output', 4),
        ('io_out_2', 'output', 4),
        ('io_out_3', 'output', 4),
    ),
    'RegCacheAgeDetector_1': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_ageInfo_0_1', 'input', 1),
        ('io_ageInfo_0_2', 'input', 1),
        ('io_ageInfo_0_3', 'input', 1),
        ('io_ageInfo_0_4', 'input', 1),
        ('io_ageInfo_0_5', 'input', 1),
        ('io_ageInfo_0_6', 'input', 1),
        ('io_ageInfo_0_7', 'input', 1),
        ('io_ageInfo_0_8', 'input', 1),
        ('io_ageInfo_0_9', 'input', 1),
        ('io_ageInfo_0_10', 'input', 1),
        ('io_ageInfo_0_11', 'input', 1),
        ('io_ageInfo_1_2', 'input', 1),
        ('io_ageInfo_1_3', 'input', 1),
        ('io_ageInfo_1_4', 'input', 1),
        ('io_ageInfo_1_5', 'input', 1),
        ('io_ageInfo_1_6', 'input', 1),
        ('io_ageInfo_1_7', 'input', 1),
        ('io_ageInfo_1_8', 'input', 1),
        ('io_ageInfo_1_9', 'input', 1),
        ('io_ageInfo_1_10', 'input', 1),
        ('io_ageInfo_1_11', 'input', 1),
        ('io_ageInfo_2_3', 'input', 1),
        ('io_ageInfo_2_4', 'input', 1),
        ('io_ageInfo_2_5', 'input', 1),
        ('io_ageInfo_2_6', 'input', 1),
        ('io_ageInfo_2_7', 'input', 1),
        ('io_ageInfo_2_8', 'input', 1),
        ('io_ageInfo_2_9', 'input', 1),
        ('io_ageInfo_2_10', 'input', 1),
        ('io_ageInfo_2_11', 'input', 1),
        ('io_ageInfo_3_4', 'input', 1),
        ('io_ageInfo_3_5', 'input', 1),
        ('io_ageInfo_3_6', 'input', 1),
        ('io_ageInfo_3_7', 'input', 1),
        ('io_ageInfo_3_8', 'input', 1),
        ('io_ageInfo_3_9', 'input', 1),
        ('io_ageInfo_3_10', 'input', 1),
        ('io_ageInfo_3_11', 'input', 1),
        ('io_ageInfo_4_5', 'input', 1),
        ('io_ageInfo_4_6', 'input', 1),
        ('io_ageInfo_4_7', 'input', 1),
        ('io_ageInfo_4_8', 'input', 1),
        ('io_ageInfo_4_9', 'input', 1),
        ('io_ageInfo_4_10', 'input', 1),
        ('io_ageInfo_4_11', 'input', 1),
        ('io_ageInfo_5_6', 'input', 1),
        ('io_ageInfo_5_7', 'input', 1),
        ('io_ageInfo_5_8', 'input', 1),
        ('io_ageInfo_5_9', 'input', 1),
        ('io_ageInfo_5_10', 'input', 1),
        ('io_ageInfo_5_11', 'input', 1),
        ('io_ageInfo_6_7', 'input', 1),
        ('io_ageInfo_6_8', 'input', 1),
        ('io_ageInfo_6_9', 'input', 1),
        ('io_ageInfo_6_10', 'input', 1),
        ('io_ageInfo_6_11', 'input', 1),
        ('io_ageInfo_7_8', 'input', 1),
        ('io_ageInfo_7_9', 'input', 1),
        ('io_ageInfo_7_10', 'input', 1),
        ('io_ageInfo_7_11', 'input', 1),
        ('io_ageInfo_8_9', 'input', 1),
        ('io_ageInfo_8_10', 'input', 1),
        ('io_ageInfo_8_11', 'input', 1),
        ('io_ageInfo_9_10', 'input', 1),
        ('io_ageInfo_9_11', 'input', 1),
        ('io_ageInfo_10_11', 'input', 1),
        ('io_out_0', 'output', 4),
        ('io_out_1', 'output', 4),
        ('io_out_2', 'output', 4),
    ),
    'RegCacheAgeTimer': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_readPorts_0_ren', 'input', 1),
        ('io_readPorts_0_addr', 'input', 4),
        ('io_readPorts_1_ren', 'input', 1),
        ('io_readPorts_1_addr', 'input', 4),
        ('io_readPorts_2_ren', 'input', 1),
        ('io_readPorts_2_addr', 'input', 4),
        ('io_readPorts_3_ren', 'input', 1),
        ('io_readPorts_3_addr', 'input', 4),
        ('io_readPorts_4_ren', 'input', 1),
        ('io_readPorts_4_addr', 'input', 4),
        ('io_readPorts_5_ren', 'input', 1),
        ('io_readPorts_5_addr', 'input', 4),
        ('io_readPorts_6_ren', 'input', 1),
        ('io_readPorts_6_addr', 'input', 4),
        ('io_readPorts_7_ren', 'input', 1),
        ('io_readPorts_7_addr', 'input', 4),
        ('io_readPorts_8_ren', 'input', 1),
        ('io_readPorts_8_addr', 'input', 4),
        ('io_readPorts_9_ren', 'input', 1),
        ('io_readPorts_9_addr', 'input', 4),
        ('io_readPorts_10_ren', 'input', 1),
        ('io_readPorts_10_addr', 'input', 4),
        ('io_readPorts_11_ren', 'input', 1),
        ('io_readPorts_11_addr', 'input', 4),
        ('io_readPorts_12_ren', 'input', 1),
        ('io_readPorts_12_addr', 'input', 4),
        ('io_readPorts_13_ren', 'input', 1),
        ('io_readPorts_13_addr', 'input', 4),
        ('io_readPorts_14_ren', 'input', 1),
        ('io_readPorts_14_addr', 'input', 4),
        ('io_readPorts_15_ren', 'input', 1),
        ('io_readPorts_15_addr', 'input', 4),
        ('io_readPorts_16_ren', 'input', 1),
        ('io_readPorts_16_addr', 'input', 4),
        ('io_readPorts_17_ren', 'input', 1),
        ('io_readPorts_17_addr', 'input', 4),
        ('io_readPorts_18_ren', 'input', 1),
        ('io_readPorts_18_addr', 'input', 4),
        ('io_readPorts_19_ren', 'input', 1),
        ('io_readPorts_19_addr', 'input', 4),
        ('io_readPorts_20_ren', 'input', 1),
        ('io_readPorts_20_addr', 'input', 4),
        ('io_readPorts_21_ren', 'input', 1),
        ('io_readPorts_21_addr', 'input', 4),
        ('io_readPorts_22_ren', 'input', 1),
        ('io_readPorts_22_addr', 'input', 4),
        ('io_writePorts_0_wen', 'input', 1),
        ('io_writePorts_0_addr', 'input', 4),
        ('io_writePorts_1_wen', 'input', 1),
        ('io_writePorts_1_addr', 'input', 4),
        ('io_writePorts_2_wen', 'input', 1),
        ('io_writePorts_2_addr', 'input', 4),
        ('io_writePorts_3_wen', 'input', 1),
        ('io_writePorts_3_addr', 'input', 4),
        ('io_validInfo_0', 'input', 1),
        ('io_validInfo_1', 'input', 1),
        ('io_validInfo_2', 'input', 1),
        ('io_validInfo_3', 'input', 1),
        ('io_validInfo_4', 'input', 1),
        ('io_validInfo_5', 'input', 1),
        ('io_validInfo_6', 'input', 1),
        ('io_validInfo_7', 'input', 1),
        ('io_validInfo_8', 'input', 1),
        ('io_validInfo_9', 'input', 1),
        ('io_validInfo_10', 'input', 1),
        ('io_validInfo_11', 'input', 1),
        ('io_validInfo_12', 'input', 1),
        ('io_validInfo_13', 'input', 1),
        ('io_validInfo_14', 'input', 1),
        ('io_validInfo_15', 'input', 1),
        ('io_ageInfo_0_1', 'output', 1),
        ('io_ageInfo_0_2', 'output', 1),
        ('io_ageInfo_0_3', 'output', 1),
        ('io_ageInfo_0_4', 'output', 1),
        ('io_ageInfo_0_5', 'output', 1),
        ('io_ageInfo_0_6', 'output', 1),
        ('io_ageInfo_0_7', 'output', 1),
        ('io_ageInfo_0_8', 'output', 1),
        ('io_ageInfo_0_9', 'output', 1),
        ('io_ageInfo_0_10', 'output', 1),
        ('io_ageInfo_0_11', 'output', 1),
        ('io_ageInfo_0_12', 'output', 1),
        ('io_ageInfo_0_13', 'output', 1),
        ('io_ageInfo_0_14', 'output', 1),
        ('io_ageInfo_0_15', 'output', 1),
        ('io_ageInfo_1_2', 'output', 1),
        ('io_ageInfo_1_3', 'output', 1),
        ('io_ageInfo_1_4', 'output', 1),
        ('io_ageInfo_1_5', 'output', 1),
        ('io_ageInfo_1_6', 'output', 1),
        ('io_ageInfo_1_7', 'output', 1),
        ('io_ageInfo_1_8', 'output', 1),
        ('io_ageInfo_1_9', 'output', 1),
        ('io_ageInfo_1_10', 'output', 1),
        ('io_ageInfo_1_11', 'output', 1),
        ('io_ageInfo_1_12', 'output', 1),
        ('io_ageInfo_1_13', 'output', 1),
        ('io_ageInfo_1_14', 'output', 1),
        ('io_ageInfo_1_15', 'output', 1),
        ('io_ageInfo_2_3', 'output', 1),
        ('io_ageInfo_2_4', 'output', 1),
        ('io_ageInfo_2_5', 'output', 1),
        ('io_ageInfo_2_6', 'output', 1),
        ('io_ageInfo_2_7', 'output', 1),
        ('io_ageInfo_2_8', 'output', 1),
        ('io_ageInfo_2_9', 'output', 1),
        ('io_ageInfo_2_10', 'output', 1),
        ('io_ageInfo_2_11', 'output', 1),
        ('io_ageInfo_2_12', 'output', 1),
        ('io_ageInfo_2_13', 'output', 1),
        ('io_ageInfo_2_14', 'output', 1),
        ('io_ageInfo_2_15', 'output', 1),
        ('io_ageInfo_3_4', 'output', 1),
        ('io_ageInfo_3_5', 'output', 1),
        ('io_ageInfo_3_6', 'output', 1),
        ('io_ageInfo_3_7', 'output', 1),
        ('io_ageInfo_3_8', 'output', 1),
        ('io_ageInfo_3_9', 'output', 1),
        ('io_ageInfo_3_10', 'output', 1),
        ('io_ageInfo_3_11', 'output', 1),
        ('io_ageInfo_3_12', 'output', 1),
        ('io_ageInfo_3_13', 'output', 1),
        ('io_ageInfo_3_14', 'output', 1),
        ('io_ageInfo_3_15', 'output', 1),
        ('io_ageInfo_4_5', 'output', 1),
        ('io_ageInfo_4_6', 'output', 1),
        ('io_ageInfo_4_7', 'output', 1),
        ('io_ageInfo_4_8', 'output', 1),
        ('io_ageInfo_4_9', 'output', 1),
        ('io_ageInfo_4_10', 'output', 1),
        ('io_ageInfo_4_11', 'output', 1),
        ('io_ageInfo_4_12', 'output', 1),
        ('io_ageInfo_4_13', 'output', 1),
        ('io_ageInfo_4_14', 'output', 1),
        ('io_ageInfo_4_15', 'output', 1),
        ('io_ageInfo_5_6', 'output', 1),
        ('io_ageInfo_5_7', 'output', 1),
        ('io_ageInfo_5_8', 'output', 1),
        ('io_ageInfo_5_9', 'output', 1),
        ('io_ageInfo_5_10', 'output', 1),
        ('io_ageInfo_5_11', 'output', 1),
        ('io_ageInfo_5_12', 'output', 1),
        ('io_ageInfo_5_13', 'output', 1),
        ('io_ageInfo_5_14', 'output', 1),
        ('io_ageInfo_5_15', 'output', 1),
        ('io_ageInfo_6_7', 'output', 1),
        ('io_ageInfo_6_8', 'output', 1),
        ('io_ageInfo_6_9', 'output', 1),
        ('io_ageInfo_6_10', 'output', 1),
        ('io_ageInfo_6_11', 'output', 1),
        ('io_ageInfo_6_12', 'output', 1),
        ('io_ageInfo_6_13', 'output', 1),
        ('io_ageInfo_6_14', 'output', 1),
        ('io_ageInfo_6_15', 'output', 1),
        ('io_ageInfo_7_8', 'output', 1),
        ('io_ageInfo_7_9', 'output', 1),
        ('io_ageInfo_7_10', 'output', 1),
        ('io_ageInfo_7_11', 'output', 1),
        ('io_ageInfo_7_12', 'output', 1),
        ('io_ageInfo_7_13', 'output', 1),
        ('io_ageInfo_7_14', 'output', 1),
        ('io_ageInfo_7_15', 'output', 1),
        ('io_ageInfo_8_9', 'output', 1),
        ('io_ageInfo_8_10', 'output', 1),
        ('io_ageInfo_8_11', 'output', 1),
        ('io_ageInfo_8_12', 'output', 1),
        ('io_ageInfo_8_13', 'output', 1),
        ('io_ageInfo_8_14', 'output', 1),
        ('io_ageInfo_8_15', 'output', 1),
        ('io_ageInfo_9_10', 'output', 1),
        ('io_ageInfo_9_11', 'output', 1),
        ('io_ageInfo_9_12', 'output', 1),
        ('io_ageInfo_9_13', 'output', 1),
        ('io_ageInfo_9_14', 'output', 1),
        ('io_ageInfo_9_15', 'output', 1),
        ('io_ageInfo_10_11', 'output', 1),
        ('io_ageInfo_10_12', 'output', 1),
        ('io_ageInfo_10_13', 'output', 1),
        ('io_ageInfo_10_14', 'output', 1),
        ('io_ageInfo_10_15', 'output', 1),
        ('io_ageInfo_11_12', 'output', 1),
        ('io_ageInfo_11_13', 'output', 1),
        ('io_ageInfo_11_14', 'output', 1),
        ('io_ageInfo_11_15', 'output', 1),
        ('io_ageInfo_12_13', 'output', 1),
        ('io_ageInfo_12_14', 'output', 1),
        ('io_ageInfo_12_15', 'output', 1),
        ('io_ageInfo_13_14', 'output', 1),
        ('io_ageInfo_13_15', 'output', 1),
        ('io_ageInfo_14_15', 'output', 1),
    ),
    'RegCacheAgeTimer_1': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_readPorts_0_ren', 'input', 1),
        ('io_readPorts_0_addr', 'input', 4),
        ('io_readPorts_1_ren', 'input', 1),
        ('io_readPorts_1_addr', 'input', 4),
        ('io_readPorts_2_ren', 'input', 1),
        ('io_readPorts_2_addr', 'input', 4),
        ('io_readPorts_3_ren', 'input', 1),
        ('io_readPorts_3_addr', 'input', 4),
        ('io_readPorts_4_ren', 'input', 1),
        ('io_readPorts_4_addr', 'input', 4),
        ('io_readPorts_5_ren', 'input', 1),
        ('io_readPorts_5_addr', 'input', 4),
        ('io_readPorts_6_ren', 'input', 1),
        ('io_readPorts_6_addr', 'input', 4),
        ('io_readPorts_7_ren', 'input', 1),
        ('io_readPorts_7_addr', 'input', 4),
        ('io_readPorts_8_ren', 'input', 1),
        ('io_readPorts_8_addr', 'input', 4),
        ('io_readPorts_9_ren', 'input', 1),
        ('io_readPorts_9_addr', 'input', 4),
        ('io_readPorts_10_ren', 'input', 1),
        ('io_readPorts_10_addr', 'input', 4),
        ('io_readPorts_11_ren', 'input', 1),
        ('io_readPorts_11_addr', 'input', 4),
        ('io_readPorts_12_ren', 'input', 1),
        ('io_readPorts_12_addr', 'input', 4),
        ('io_readPorts_13_ren', 'input', 1),
        ('io_readPorts_13_addr', 'input', 4),
        ('io_readPorts_14_ren', 'input', 1),
        ('io_readPorts_14_addr', 'input', 4),
        ('io_readPorts_15_ren', 'input', 1),
        ('io_readPorts_15_addr', 'input', 4),
        ('io_readPorts_16_ren', 'input', 1),
        ('io_readPorts_16_addr', 'input', 4),
        ('io_readPorts_17_ren', 'input', 1),
        ('io_readPorts_17_addr', 'input', 4),
        ('io_readPorts_18_ren', 'input', 1),
        ('io_readPorts_18_addr', 'input', 4),
        ('io_readPorts_19_ren', 'input', 1),
        ('io_readPorts_19_addr', 'input', 4),
        ('io_readPorts_20_ren', 'input', 1),
        ('io_readPorts_20_addr', 'input', 4),
        ('io_readPorts_21_ren', 'input', 1),
        ('io_readPorts_21_addr', 'input', 4),
        ('io_readPorts_22_ren', 'input', 1),
        ('io_readPorts_22_addr', 'input', 4),
        ('io_writePorts_0_wen', 'input', 1),
        ('io_writePorts_0_addr', 'input', 4),
        ('io_writePorts_1_wen', 'input', 1),
        ('io_writePorts_1_addr', 'input', 4),
        ('io_writePorts_2_wen', 'input', 1),
        ('io_writePorts_2_addr', 'input', 4),
        ('io_validInfo_0', 'input', 1),
        ('io_validInfo_1', 'input', 1),
        ('io_validInfo_2', 'input', 1),
        ('io_validInfo_3', 'input', 1),
        ('io_validInfo_4', 'input', 1),
        ('io_validInfo_5', 'input', 1),
        ('io_validInfo_6', 'input', 1),
        ('io_validInfo_7', 'input', 1),
        ('io_validInfo_8', 'input', 1),
        ('io_validInfo_9', 'input', 1),
        ('io_validInfo_10', 'input', 1),
        ('io_validInfo_11', 'input', 1),
        ('io_ageInfo_0_1', 'output', 1),
        ('io_ageInfo_0_2', 'output', 1),
        ('io_ageInfo_0_3', 'output', 1),
        ('io_ageInfo_0_4', 'output', 1),
        ('io_ageInfo_0_5', 'output', 1),
        ('io_ageInfo_0_6', 'output', 1),
        ('io_ageInfo_0_7', 'output', 1),
        ('io_ageInfo_0_8', 'output', 1),
        ('io_ageInfo_0_9', 'output', 1),
        ('io_ageInfo_0_10', 'output', 1),
        ('io_ageInfo_0_11', 'output', 1),
        ('io_ageInfo_1_2', 'output', 1),
        ('io_ageInfo_1_3', 'output', 1),
        ('io_ageInfo_1_4', 'output', 1),
        ('io_ageInfo_1_5', 'output', 1),
        ('io_ageInfo_1_6', 'output', 1),
        ('io_ageInfo_1_7', 'output', 1),
        ('io_ageInfo_1_8', 'output', 1),
        ('io_ageInfo_1_9', 'output', 1),
        ('io_ageInfo_1_10', 'output', 1),
        ('io_ageInfo_1_11', 'output', 1),
        ('io_ageInfo_2_3', 'output', 1),
        ('io_ageInfo_2_4', 'output', 1),
        ('io_ageInfo_2_5', 'output', 1),
        ('io_ageInfo_2_6', 'output', 1),
        ('io_ageInfo_2_7', 'output', 1),
        ('io_ageInfo_2_8', 'output', 1),
        ('io_ageInfo_2_9', 'output', 1),
        ('io_ageInfo_2_10', 'output', 1),
        ('io_ageInfo_2_11', 'output', 1),
        ('io_ageInfo_3_4', 'output', 1),
        ('io_ageInfo_3_5', 'output', 1),
        ('io_ageInfo_3_6', 'output', 1),
        ('io_ageInfo_3_7', 'output', 1),
        ('io_ageInfo_3_8', 'output', 1),
        ('io_ageInfo_3_9', 'output', 1),
        ('io_ageInfo_3_10', 'output', 1),
        ('io_ageInfo_3_11', 'output', 1),
        ('io_ageInfo_4_5', 'output', 1),
        ('io_ageInfo_4_6', 'output', 1),
        ('io_ageInfo_4_7', 'output', 1),
        ('io_ageInfo_4_8', 'output', 1),
        ('io_ageInfo_4_9', 'output', 1),
        ('io_ageInfo_4_10', 'output', 1),
        ('io_ageInfo_4_11', 'output', 1),
        ('io_ageInfo_5_6', 'output', 1),
        ('io_ageInfo_5_7', 'output', 1),
        ('io_ageInfo_5_8', 'output', 1),
        ('io_ageInfo_5_9', 'output', 1),
        ('io_ageInfo_5_10', 'output', 1),
        ('io_ageInfo_5_11', 'output', 1),
        ('io_ageInfo_6_7', 'output', 1),
        ('io_ageInfo_6_8', 'output', 1),
        ('io_ageInfo_6_9', 'output', 1),
        ('io_ageInfo_6_10', 'output', 1),
        ('io_ageInfo_6_11', 'output', 1),
        ('io_ageInfo_7_8', 'output', 1),
        ('io_ageInfo_7_9', 'output', 1),
        ('io_ageInfo_7_10', 'output', 1),
        ('io_ageInfo_7_11', 'output', 1),
        ('io_ageInfo_8_9', 'output', 1),
        ('io_ageInfo_8_10', 'output', 1),
        ('io_ageInfo_8_11', 'output', 1),
        ('io_ageInfo_9_10', 'output', 1),
        ('io_ageInfo_9_11', 'output', 1),
        ('io_ageInfo_10_11', 'output', 1),
    ),
    'RegCacheDataModule': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_readPorts_0_ren', 'input', 1),
        ('io_readPorts_0_addr', 'input', 4),
        ('io_readPorts_0_data', 'output', 64),
        ('io_readPorts_1_ren', 'input', 1),
        ('io_readPorts_1_addr', 'input', 4),
        ('io_readPorts_1_data', 'output', 64),
        ('io_readPorts_2_ren', 'input', 1),
        ('io_readPorts_2_addr', 'input', 4),
        ('io_readPorts_2_data', 'output', 64),
        ('io_readPorts_3_ren', 'input', 1),
        ('io_readPorts_3_addr', 'input', 4),
        ('io_readPorts_3_data', 'output', 64),
        ('io_readPorts_4_ren', 'input', 1),
        ('io_readPorts_4_addr', 'input', 4),
        ('io_readPorts_4_data', 'output', 64),
        ('io_readPorts_5_ren', 'input', 1),
        ('io_readPorts_5_addr', 'input', 4),
        ('io_readPorts_5_data', 'output', 64),
        ('io_readPorts_6_ren', 'input', 1),
        ('io_readPorts_6_addr', 'input', 4),
        ('io_readPorts_6_data', 'output', 64),
        ('io_readPorts_7_ren', 'input', 1),
        ('io_readPorts_7_addr', 'input', 4),
        ('io_readPorts_7_data', 'output', 64),
        ('io_readPorts_8_ren', 'input', 1),
        ('io_readPorts_8_addr', 'input', 4),
        ('io_readPorts_8_data', 'output', 64),
        ('io_readPorts_9_ren', 'input', 1),
        ('io_readPorts_9_addr', 'input', 4),
        ('io_readPorts_9_data', 'output', 64),
        ('io_readPorts_10_ren', 'input', 1),
        ('io_readPorts_10_addr', 'input', 4),
        ('io_readPorts_10_data', 'output', 64),
        ('io_readPorts_11_ren', 'input', 1),
        ('io_readPorts_11_addr', 'input', 4),
        ('io_readPorts_11_data', 'output', 64),
        ('io_readPorts_12_ren', 'input', 1),
        ('io_readPorts_12_addr', 'input', 4),
        ('io_readPorts_12_data', 'output', 64),
        ('io_readPorts_13_ren', 'input', 1),
        ('io_readPorts_13_addr', 'input', 4),
        ('io_readPorts_13_data', 'output', 64),
        ('io_readPorts_14_ren', 'input', 1),
        ('io_readPorts_14_addr', 'input', 4),
        ('io_readPorts_14_data', 'output', 64),
        ('io_readPorts_15_ren', 'input', 1),
        ('io_readPorts_15_addr', 'input', 4),
        ('io_readPorts_15_data', 'output', 64),
        ('io_readPorts_16_ren', 'input', 1),
        ('io_readPorts_16_addr', 'input', 4),
        ('io_readPorts_16_data', 'output', 64),
        ('io_readPorts_17_ren', 'input', 1),
        ('io_readPorts_17_addr', 'input', 4),
        ('io_readPorts_17_data', 'output', 64),
        ('io_readPorts_18_ren', 'input', 1),
        ('io_readPorts_18_addr', 'input', 4),
        ('io_readPorts_18_data', 'output', 64),
        ('io_readPorts_19_ren', 'input', 1),
        ('io_readPorts_19_addr', 'input', 4),
        ('io_readPorts_19_data', 'output', 64),
        ('io_readPorts_20_ren', 'input', 1),
        ('io_readPorts_20_addr', 'input', 4),
        ('io_readPorts_20_data', 'output', 64),
        ('io_readPorts_21_ren', 'input', 1),
        ('io_readPorts_21_addr', 'input', 4),
        ('io_readPorts_21_data', 'output', 64),
        ('io_readPorts_22_ren', 'input', 1),
        ('io_readPorts_22_addr', 'input', 4),
        ('io_readPorts_22_data', 'output', 64),
        ('io_writePorts_0_wen', 'input', 1),
        ('io_writePorts_0_addr', 'input', 4),
        ('io_writePorts_0_data', 'input', 64),
        ('io_writePorts_1_wen', 'input', 1),
        ('io_writePorts_1_addr', 'input', 4),
        ('io_writePorts_1_data', 'input', 64),
        ('io_writePorts_2_wen', 'input', 1),
        ('io_writePorts_2_addr', 'input', 4),
        ('io_writePorts_2_data', 'input', 64),
        ('io_writePorts_3_wen', 'input', 1),
        ('io_writePorts_3_addr', 'input', 4),
        ('io_writePorts_3_data', 'input', 64),
        ('io_validInfo_0', 'output', 1),
        ('io_validInfo_1', 'output', 1),
        ('io_validInfo_2', 'output', 1),
        ('io_validInfo_3', 'output', 1),
        ('io_validInfo_4', 'output', 1),
        ('io_validInfo_5', 'output', 1),
        ('io_validInfo_6', 'output', 1),
        ('io_validInfo_7', 'output', 1),
        ('io_validInfo_8', 'output', 1),
        ('io_validInfo_9', 'output', 1),
        ('io_validInfo_10', 'output', 1),
        ('io_validInfo_11', 'output', 1),
        ('io_validInfo_12', 'output', 1),
        ('io_validInfo_13', 'output', 1),
        ('io_validInfo_14', 'output', 1),
        ('io_validInfo_15', 'output', 1),
    ),
    'RegCacheDataModule_1': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_readPorts_0_ren', 'input', 1),
        ('io_readPorts_0_addr', 'input', 4),
        ('io_readPorts_0_data', 'output', 64),
        ('io_readPorts_1_ren', 'input', 1),
        ('io_readPorts_1_addr', 'input', 4),
        ('io_readPorts_1_data', 'output', 64),
        ('io_readPorts_2_ren', 'input', 1),
        ('io_readPorts_2_addr', 'input', 4),
        ('io_readPorts_2_data', 'output', 64),
        ('io_readPorts_3_ren', 'input', 1),
        ('io_readPorts_3_addr', 'input', 4),
        ('io_readPorts_3_data', 'output', 64),
        ('io_readPorts_4_ren', 'input', 1),
        ('io_readPorts_4_addr', 'input', 4),
        ('io_readPorts_4_data', 'output', 64),
        ('io_readPorts_5_ren', 'input', 1),
        ('io_readPorts_5_addr', 'input', 4),
        ('io_readPorts_5_data', 'output', 64),
        ('io_readPorts_6_ren', 'input', 1),
        ('io_readPorts_6_addr', 'input', 4),
        ('io_readPorts_6_data', 'output', 64),
        ('io_readPorts_7_ren', 'input', 1),
        ('io_readPorts_7_addr', 'input', 4),
        ('io_readPorts_7_data', 'output', 64),
        ('io_readPorts_8_ren', 'input', 1),
        ('io_readPorts_8_addr', 'input', 4),
        ('io_readPorts_8_data', 'output', 64),
        ('io_readPorts_9_ren', 'input', 1),
        ('io_readPorts_9_addr', 'input', 4),
        ('io_readPorts_9_data', 'output', 64),
        ('io_readPorts_10_ren', 'input', 1),
        ('io_readPorts_10_addr', 'input', 4),
        ('io_readPorts_10_data', 'output', 64),
        ('io_readPorts_11_ren', 'input', 1),
        ('io_readPorts_11_addr', 'input', 4),
        ('io_readPorts_11_data', 'output', 64),
        ('io_readPorts_12_ren', 'input', 1),
        ('io_readPorts_12_addr', 'input', 4),
        ('io_readPorts_12_data', 'output', 64),
        ('io_readPorts_13_ren', 'input', 1),
        ('io_readPorts_13_addr', 'input', 4),
        ('io_readPorts_13_data', 'output', 64),
        ('io_readPorts_14_ren', 'input', 1),
        ('io_readPorts_14_addr', 'input', 4),
        ('io_readPorts_14_data', 'output', 64),
        ('io_readPorts_15_ren', 'input', 1),
        ('io_readPorts_15_addr', 'input', 4),
        ('io_readPorts_15_data', 'output', 64),
        ('io_readPorts_16_ren', 'input', 1),
        ('io_readPorts_16_addr', 'input', 4),
        ('io_readPorts_16_data', 'output', 64),
        ('io_readPorts_17_ren', 'input', 1),
        ('io_readPorts_17_addr', 'input', 4),
        ('io_readPorts_17_data', 'output', 64),
        ('io_readPorts_18_ren', 'input', 1),
        ('io_readPorts_18_addr', 'input', 4),
        ('io_readPorts_18_data', 'output', 64),
        ('io_readPorts_19_ren', 'input', 1),
        ('io_readPorts_19_addr', 'input', 4),
        ('io_readPorts_19_data', 'output', 64),
        ('io_readPorts_20_ren', 'input', 1),
        ('io_readPorts_20_addr', 'input', 4),
        ('io_readPorts_20_data', 'output', 64),
        ('io_readPorts_21_ren', 'input', 1),
        ('io_readPorts_21_addr', 'input', 4),
        ('io_readPorts_21_data', 'output', 64),
        ('io_readPorts_22_ren', 'input', 1),
        ('io_readPorts_22_addr', 'input', 4),
        ('io_readPorts_22_data', 'output', 64),
        ('io_writePorts_0_wen', 'input', 1),
        ('io_writePorts_0_addr', 'input', 4),
        ('io_writePorts_0_data', 'input', 64),
        ('io_writePorts_1_wen', 'input', 1),
        ('io_writePorts_1_addr', 'input', 4),
        ('io_writePorts_1_data', 'input', 64),
        ('io_writePorts_2_wen', 'input', 1),
        ('io_writePorts_2_addr', 'input', 4),
        ('io_writePorts_2_data', 'input', 64),
        ('io_validInfo_0', 'output', 1),
        ('io_validInfo_1', 'output', 1),
        ('io_validInfo_2', 'output', 1),
        ('io_validInfo_3', 'output', 1),
        ('io_validInfo_4', 'output', 1),
        ('io_validInfo_5', 'output', 1),
        ('io_validInfo_6', 'output', 1),
        ('io_validInfo_7', 'output', 1),
        ('io_validInfo_8', 'output', 1),
        ('io_validInfo_9', 'output', 1),
        ('io_validInfo_10', 'output', 1),
        ('io_validInfo_11', 'output', 1),
    ),
    'RegCacheTagModule': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_readPorts_0_ren', 'input', 1),
        ('io_readPorts_0_tag', 'input', 8),
        ('io_readPorts_0_valid', 'output', 1),
        ('io_readPorts_0_addr', 'output', 4),
        ('io_readPorts_1_ren', 'input', 1),
        ('io_readPorts_1_tag', 'input', 8),
        ('io_readPorts_1_valid', 'output', 1),
        ('io_readPorts_1_addr', 'output', 4),
        ('io_readPorts_2_ren', 'input', 1),
        ('io_readPorts_2_tag', 'input', 8),
        ('io_readPorts_2_valid', 'output', 1),
        ('io_readPorts_2_addr', 'output', 4),
        ('io_readPorts_3_ren', 'input', 1),
        ('io_readPorts_3_tag', 'input', 8),
        ('io_readPorts_3_valid', 'output', 1),
        ('io_readPorts_3_addr', 'output', 4),
        ('io_readPorts_4_ren', 'input', 1),
        ('io_readPorts_4_tag', 'input', 8),
        ('io_readPorts_4_valid', 'output', 1),
        ('io_readPorts_4_addr', 'output', 4),
        ('io_readPorts_5_ren', 'input', 1),
        ('io_readPorts_5_tag', 'input', 8),
        ('io_readPorts_5_valid', 'output', 1),
        ('io_readPorts_5_addr', 'output', 4),
        ('io_readPorts_6_ren', 'input', 1),
        ('io_readPorts_6_tag', 'input', 8),
        ('io_readPorts_6_valid', 'output', 1),
        ('io_readPorts_6_addr', 'output', 4),
        ('io_readPorts_7_ren', 'input', 1),
        ('io_readPorts_7_tag', 'input', 8),
        ('io_readPorts_7_valid', 'output', 1),
        ('io_readPorts_7_addr', 'output', 4),
        ('io_readPorts_8_ren', 'input', 1),
        ('io_readPorts_8_tag', 'input', 8),
        ('io_readPorts_8_valid', 'output', 1),
        ('io_readPorts_8_addr', 'output', 4),
        ('io_readPorts_9_ren', 'input', 1),
        ('io_readPorts_9_tag', 'input', 8),
        ('io_readPorts_9_valid', 'output', 1),
        ('io_readPorts_9_addr', 'output', 4),
        ('io_readPorts_10_ren', 'input', 1),
        ('io_readPorts_10_tag', 'input', 8),
        ('io_readPorts_10_valid', 'output', 1),
        ('io_readPorts_10_addr', 'output', 4),
        ('io_readPorts_11_ren', 'input', 1),
        ('io_readPorts_11_tag', 'input', 8),
        ('io_readPorts_11_valid', 'output', 1),
        ('io_readPorts_11_addr', 'output', 4),
        ('io_writePorts_0_wen', 'input', 1),
        ('io_writePorts_0_addr', 'input', 4),
        ('io_writePorts_0_tag', 'input', 8),
        ('io_writePorts_0_loadDependency_0', 'input', 2),
        ('io_writePorts_0_loadDependency_1', 'input', 2),
        ('io_writePorts_0_loadDependency_2', 'input', 2),
        ('io_writePorts_1_wen', 'input', 1),
        ('io_writePorts_1_addr', 'input', 4),
        ('io_writePorts_1_tag', 'input', 8),
        ('io_writePorts_1_loadDependency_0', 'input', 2),
        ('io_writePorts_1_loadDependency_1', 'input', 2),
        ('io_writePorts_1_loadDependency_2', 'input', 2),
        ('io_writePorts_2_wen', 'input', 1),
        ('io_writePorts_2_addr', 'input', 4),
        ('io_writePorts_2_tag', 'input', 8),
        ('io_writePorts_2_loadDependency_0', 'input', 2),
        ('io_writePorts_2_loadDependency_1', 'input', 2),
        ('io_writePorts_2_loadDependency_2', 'input', 2),
        ('io_writePorts_3_wen', 'input', 1),
        ('io_writePorts_3_addr', 'input', 4),
        ('io_writePorts_3_tag', 'input', 8),
        ('io_writePorts_3_loadDependency_0', 'input', 2),
        ('io_writePorts_3_loadDependency_1', 'input', 2),
        ('io_writePorts_3_loadDependency_2', 'input', 2),
        ('io_cancelVec_0', 'input', 1),
        ('io_cancelVec_1', 'input', 1),
        ('io_cancelVec_2', 'input', 1),
        ('io_cancelVec_3', 'input', 1),
        ('io_cancelVec_4', 'input', 1),
        ('io_cancelVec_5', 'input', 1),
        ('io_cancelVec_6', 'input', 1),
        ('io_cancelVec_7', 'input', 1),
        ('io_cancelVec_8', 'input', 1),
        ('io_cancelVec_9', 'input', 1),
        ('io_cancelVec_10', 'input', 1),
        ('io_cancelVec_11', 'input', 1),
        ('io_cancelVec_12', 'input', 1),
        ('io_cancelVec_13', 'input', 1),
        ('io_cancelVec_14', 'input', 1),
        ('io_cancelVec_15', 'input', 1),
        ('io_validVec_0', 'output', 1),
        ('io_validVec_1', 'output', 1),
        ('io_validVec_2', 'output', 1),
        ('io_validVec_3', 'output', 1),
        ('io_validVec_4', 'output', 1),
        ('io_validVec_5', 'output', 1),
        ('io_validVec_6', 'output', 1),
        ('io_validVec_7', 'output', 1),
        ('io_validVec_8', 'output', 1),
        ('io_validVec_9', 'output', 1),
        ('io_validVec_10', 'output', 1),
        ('io_validVec_11', 'output', 1),
        ('io_validVec_12', 'output', 1),
        ('io_validVec_13', 'output', 1),
        ('io_validVec_14', 'output', 1),
        ('io_validVec_15', 'output', 1),
        ('io_tagVec_0', 'output', 8),
        ('io_tagVec_1', 'output', 8),
        ('io_tagVec_2', 'output', 8),
        ('io_tagVec_3', 'output', 8),
        ('io_tagVec_4', 'output', 8),
        ('io_tagVec_5', 'output', 8),
        ('io_tagVec_6', 'output', 8),
        ('io_tagVec_7', 'output', 8),
        ('io_tagVec_8', 'output', 8),
        ('io_tagVec_9', 'output', 8),
        ('io_tagVec_10', 'output', 8),
        ('io_tagVec_11', 'output', 8),
        ('io_tagVec_12', 'output', 8),
        ('io_tagVec_13', 'output', 8),
        ('io_tagVec_14', 'output', 8),
        ('io_tagVec_15', 'output', 8),
        ('io_loadDependencyVec_0_0', 'output', 2),
        ('io_loadDependencyVec_0_1', 'output', 2),
        ('io_loadDependencyVec_0_2', 'output', 2),
        ('io_loadDependencyVec_1_0', 'output', 2),
        ('io_loadDependencyVec_1_1', 'output', 2),
        ('io_loadDependencyVec_1_2', 'output', 2),
        ('io_loadDependencyVec_2_0', 'output', 2),
        ('io_loadDependencyVec_2_1', 'output', 2),
        ('io_loadDependencyVec_2_2', 'output', 2),
        ('io_loadDependencyVec_3_0', 'output', 2),
        ('io_loadDependencyVec_3_1', 'output', 2),
        ('io_loadDependencyVec_3_2', 'output', 2),
        ('io_loadDependencyVec_4_0', 'output', 2),
        ('io_loadDependencyVec_4_1', 'output', 2),
        ('io_loadDependencyVec_4_2', 'output', 2),
        ('io_loadDependencyVec_5_0', 'output', 2),
        ('io_loadDependencyVec_5_1', 'output', 2),
        ('io_loadDependencyVec_5_2', 'output', 2),
        ('io_loadDependencyVec_6_0', 'output', 2),
        ('io_loadDependencyVec_6_1', 'output', 2),
        ('io_loadDependencyVec_6_2', 'output', 2),
        ('io_loadDependencyVec_7_0', 'output', 2),
        ('io_loadDependencyVec_7_1', 'output', 2),
        ('io_loadDependencyVec_7_2', 'output', 2),
        ('io_loadDependencyVec_8_0', 'output', 2),
        ('io_loadDependencyVec_8_1', 'output', 2),
        ('io_loadDependencyVec_8_2', 'output', 2),
        ('io_loadDependencyVec_9_0', 'output', 2),
        ('io_loadDependencyVec_9_1', 'output', 2),
        ('io_loadDependencyVec_9_2', 'output', 2),
        ('io_loadDependencyVec_10_0', 'output', 2),
        ('io_loadDependencyVec_10_1', 'output', 2),
        ('io_loadDependencyVec_10_2', 'output', 2),
        ('io_loadDependencyVec_11_0', 'output', 2),
        ('io_loadDependencyVec_11_1', 'output', 2),
        ('io_loadDependencyVec_11_2', 'output', 2),
        ('io_loadDependencyVec_12_0', 'output', 2),
        ('io_loadDependencyVec_12_1', 'output', 2),
        ('io_loadDependencyVec_12_2', 'output', 2),
        ('io_loadDependencyVec_13_0', 'output', 2),
        ('io_loadDependencyVec_13_1', 'output', 2),
        ('io_loadDependencyVec_13_2', 'output', 2),
        ('io_loadDependencyVec_14_0', 'output', 2),
        ('io_loadDependencyVec_14_1', 'output', 2),
        ('io_loadDependencyVec_14_2', 'output', 2),
        ('io_loadDependencyVec_15_0', 'output', 2),
        ('io_loadDependencyVec_15_1', 'output', 2),
        ('io_loadDependencyVec_15_2', 'output', 2),
    ),
    'RegCacheTagModule_1': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_readPorts_0_ren', 'input', 1),
        ('io_readPorts_0_tag', 'input', 8),
        ('io_readPorts_0_valid', 'output', 1),
        ('io_readPorts_0_addr', 'output', 4),
        ('io_readPorts_1_ren', 'input', 1),
        ('io_readPorts_1_tag', 'input', 8),
        ('io_readPorts_1_valid', 'output', 1),
        ('io_readPorts_1_addr', 'output', 4),
        ('io_readPorts_2_ren', 'input', 1),
        ('io_readPorts_2_tag', 'input', 8),
        ('io_readPorts_2_valid', 'output', 1),
        ('io_readPorts_2_addr', 'output', 4),
        ('io_readPorts_3_ren', 'input', 1),
        ('io_readPorts_3_tag', 'input', 8),
        ('io_readPorts_3_valid', 'output', 1),
        ('io_readPorts_3_addr', 'output', 4),
        ('io_readPorts_4_ren', 'input', 1),
        ('io_readPorts_4_tag', 'input', 8),
        ('io_readPorts_4_valid', 'output', 1),
        ('io_readPorts_4_addr', 'output', 4),
        ('io_readPorts_5_ren', 'input', 1),
        ('io_readPorts_5_tag', 'input', 8),
        ('io_readPorts_5_valid', 'output', 1),
        ('io_readPorts_5_addr', 'output', 4),
        ('io_readPorts_6_ren', 'input', 1),
        ('io_readPorts_6_tag', 'input', 8),
        ('io_readPorts_6_valid', 'output', 1),
        ('io_readPorts_6_addr', 'output', 4),
        ('io_readPorts_7_ren', 'input', 1),
        ('io_readPorts_7_tag', 'input', 8),
        ('io_readPorts_7_valid', 'output', 1),
        ('io_readPorts_7_addr', 'output', 4),
        ('io_readPorts_8_ren', 'input', 1),
        ('io_readPorts_8_tag', 'input', 8),
        ('io_readPorts_8_valid', 'output', 1),
        ('io_readPorts_8_addr', 'output', 4),
        ('io_readPorts_9_ren', 'input', 1),
        ('io_readPorts_9_tag', 'input', 8),
        ('io_readPorts_9_valid', 'output', 1),
        ('io_readPorts_9_addr', 'output', 4),
        ('io_readPorts_10_ren', 'input', 1),
        ('io_readPorts_10_tag', 'input', 8),
        ('io_readPorts_10_valid', 'output', 1),
        ('io_readPorts_10_addr', 'output', 4),
        ('io_readPorts_11_ren', 'input', 1),
        ('io_readPorts_11_tag', 'input', 8),
        ('io_readPorts_11_valid', 'output', 1),
        ('io_readPorts_11_addr', 'output', 4),
        ('io_writePorts_0_wen', 'input', 1),
        ('io_writePorts_0_addr', 'input', 4),
        ('io_writePorts_0_tag', 'input', 8),
        ('io_writePorts_1_wen', 'input', 1),
        ('io_writePorts_1_addr', 'input', 4),
        ('io_writePorts_1_tag', 'input', 8),
        ('io_writePorts_2_wen', 'input', 1),
        ('io_writePorts_2_addr', 'input', 4),
        ('io_writePorts_2_tag', 'input', 8),
        ('io_cancelVec_0', 'input', 1),
        ('io_cancelVec_1', 'input', 1),
        ('io_cancelVec_2', 'input', 1),
        ('io_cancelVec_3', 'input', 1),
        ('io_cancelVec_4', 'input', 1),
        ('io_cancelVec_5', 'input', 1),
        ('io_cancelVec_6', 'input', 1),
        ('io_cancelVec_7', 'input', 1),
        ('io_cancelVec_8', 'input', 1),
        ('io_cancelVec_9', 'input', 1),
        ('io_cancelVec_10', 'input', 1),
        ('io_cancelVec_11', 'input', 1),
        ('io_validVec_0', 'output', 1),
        ('io_validVec_1', 'output', 1),
        ('io_validVec_2', 'output', 1),
        ('io_validVec_3', 'output', 1),
        ('io_validVec_4', 'output', 1),
        ('io_validVec_5', 'output', 1),
        ('io_validVec_6', 'output', 1),
        ('io_validVec_7', 'output', 1),
        ('io_validVec_8', 'output', 1),
        ('io_validVec_9', 'output', 1),
        ('io_validVec_10', 'output', 1),
        ('io_validVec_11', 'output', 1),
        ('io_tagVec_0', 'output', 8),
        ('io_tagVec_1', 'output', 8),
        ('io_tagVec_2', 'output', 8),
        ('io_tagVec_3', 'output', 8),
        ('io_tagVec_4', 'output', 8),
        ('io_tagVec_5', 'output', 8),
        ('io_tagVec_6', 'output', 8),
        ('io_tagVec_7', 'output', 8),
        ('io_tagVec_8', 'output', 8),
        ('io_tagVec_9', 'output', 8),
        ('io_tagVec_10', 'output', 8),
        ('io_tagVec_11', 'output', 8),
        ('io_loadDependencyVec_0_0', 'output', 2),
        ('io_loadDependencyVec_0_1', 'output', 2),
        ('io_loadDependencyVec_0_2', 'output', 2),
        ('io_loadDependencyVec_1_0', 'output', 2),
        ('io_loadDependencyVec_1_1', 'output', 2),
        ('io_loadDependencyVec_1_2', 'output', 2),
        ('io_loadDependencyVec_2_0', 'output', 2),
        ('io_loadDependencyVec_2_1', 'output', 2),
        ('io_loadDependencyVec_2_2', 'output', 2),
        ('io_loadDependencyVec_3_0', 'output', 2),
        ('io_loadDependencyVec_3_1', 'output', 2),
        ('io_loadDependencyVec_3_2', 'output', 2),
        ('io_loadDependencyVec_4_0', 'output', 2),
        ('io_loadDependencyVec_4_1', 'output', 2),
        ('io_loadDependencyVec_4_2', 'output', 2),
        ('io_loadDependencyVec_5_0', 'output', 2),
        ('io_loadDependencyVec_5_1', 'output', 2),
        ('io_loadDependencyVec_5_2', 'output', 2),
        ('io_loadDependencyVec_6_0', 'output', 2),
        ('io_loadDependencyVec_6_1', 'output', 2),
        ('io_loadDependencyVec_6_2', 'output', 2),
        ('io_loadDependencyVec_7_0', 'output', 2),
        ('io_loadDependencyVec_7_1', 'output', 2),
        ('io_loadDependencyVec_7_2', 'output', 2),
        ('io_loadDependencyVec_8_0', 'output', 2),
        ('io_loadDependencyVec_8_1', 'output', 2),
        ('io_loadDependencyVec_8_2', 'output', 2),
        ('io_loadDependencyVec_9_0', 'output', 2),
        ('io_loadDependencyVec_9_1', 'output', 2),
        ('io_loadDependencyVec_9_2', 'output', 2),
        ('io_loadDependencyVec_10_0', 'output', 2),
        ('io_loadDependencyVec_10_1', 'output', 2),
        ('io_loadDependencyVec_10_2', 'output', 2),
        ('io_loadDependencyVec_11_0', 'output', 2),
        ('io_loadDependencyVec_11_1', 'output', 2),
        ('io_loadDependencyVec_11_2', 'output', 2),
    ),
}

# =============================================================================
# Configuration and exact source-backed implementation
# =============================================================================
def scalar_inputs(member: str) -> tuple[str, ...]:
    """Return all input names for a member. / 返回成员全部输入名称。"""

    return tuple(name for name, direction, _width in PORT_SPECS[member] if direction == "input")


def scalar_outputs(member: str) -> tuple[str, ...]:
    """Return all output names for a member. / 返回成员全部输出名称。"""

    return tuple(name for name, direction, _width in PORT_SPECS[member] if direction == "output")


def _or_all(values: list[Any], width: int = 1) -> Any:
    """Bitwise OR reduction with an explicit zero-width-safe seed."""

    result: Any = Const(0, width)
    for value in values:
        result = result | value
    return result


def _indexed(values: list[Any], index: Any, default: Any) -> Any:
    """Combinational Vec lookup, including Chisel's power-of-two default.

    FIRRTL pads a dynamic lookup of a non-power-of-two Vec with element zero.
    The 12-entry data/tag instances therefore return entry zero for addresses
    12--15; spelling the mux out keeps that behavior explicit.
    """

    result: Any = default
    for number in reversed(range(len(values))):
        result = Mux(index == number, values[number], result)
    return result


def _port(self: "AgeFamily", name: str) -> Signal:
    return self.ports[name]


# =============================================================================
# Implementation
# =============================================================================
class AgeFamily(Elaboratable):
    """Exact source-backed implementation of all ten locked family members."""

    def __init__(self, member: str = "NewAgeDetector") -> None:
        if member not in PORT_SPECS:
            raise ValueError(f"unsupported age family member: {member}")
        self.member = member
        self.specs = PORT_SPECS[member]
        self.ports: dict[str, Signal] = {
            name: Signal(width, name=name) for name, _direction, width in self.specs
        }

    def _new_age(self, m: Module) -> None:
        """NewAgeDetector.scala: two-entry upper age matrix and selectors."""

        age = Signal(reset=0, name="age_0_1")
        enq0, enq1 = _port(self, "io_enq_0"), _port(self, "io_enq_1")
        update = enq1 | (~enq0 & age)
        m.d.sync += age.eq(Mux(enq0 | enq1, update, age))
        for deq in range(2):
            out_name = f"io_out_{deq}"
            if out_name not in self.ports:
                continue
            can = _port(self, f"io_canIssue_{deq}")
            row0 = cast(Any, can[0]) & (age | ~cast(Any, can[1]))
            row1 = cast(Any, can[1]) & (~age | ~cast(Any, can[0]))
            # Cat's first argument is the least-significant bit, matching the
            # generated Chisel concatenation {row1,row0}.
            m.d.comb += _port(self, out_name).eq(Cat(row0, row1))

    def _regcache_age(self, m: Module) -> None:
        """RegCache AgeDetector.scala, for the 16/4 and 12/3 instances."""

        n = 16 if self.member == "RegCacheAgeDetector" else 12
        replaces = 4 if n == 16 else 3
        age: list[list[Any | None]] = [
            [Signal(reset=1, name=f"age_{row}_{col}") if row < col else None
             for col in range(n)] for row in range(n)
        ]
        for row in range(n):
            for col in range(row + 1, n):
                m.d.sync += cast(Any, age[row][col]).eq(
                    _port(self, f"io_ageInfo_{row}_{col}")
                )

        def relation(row: int, col: int) -> Any:
            if row == col:
                return Const(1)
            if row < col:
                return cast(Any, age[row][col])
            return ~cast(Any, age[col][row])

        row_sums: list[Any] = []
        sum_width = (n + 1).bit_length()
        for row in range(n):
            total: Any = Const(0, sum_width)
            for col in range(n):
                total = total + relation(row, col)
            row_sums.append(total)
        out_width = 4
        for idx in range(replaces):
            target = n - idx
            # Chisel PriorityMux uses the final value as its fallback and tests
            # conditions 0..n-2 in order. This distinction is observable for
            # malformed free states even though the source assertion rejects
            # them, so the formal transition relation must preserve it.
            result: Any = Const(n - 1, out_width)
            for row in reversed(range(n - 1)):
                result = Mux(row_sums[row] == target, Const(row, out_width), result)
            m.d.comb += _port(self, f"io_out_{idx}").eq(result)

    def _age_timer(self, m: Module) -> None:
        """RegCacheAgeTimer.scala with the fixed generated geometries."""

        n = 16 if self.member == "RegCacheAgeTimer" else 12
        reads, writes = 23, (4 if n == 16 else 3)
        group = n // 4
        timers = [Signal(2, reset=i // group, name=f"ageTimer_{i}") for i in range(n)]
        extras = [Signal(2, reset=i, name=f"ageTimerExtra_{i}") for i in range(4)]
        read_req: list[Any] = []
        write_req: list[Any] = []
        for entry in range(n):
            read_req.append(_or_all([
                _port(self, f"io_readPorts_{p}_ren")
                & (_port(self, f"io_readPorts_{p}_addr") == entry)
                for p in range(reads)
            ]))
            write_req.append(_or_all([
                _port(self, f"io_writePorts_{p}_wen")
                & (_port(self, f"io_writePorts_{p}_addr") == entry)
                for p in range(writes)
            ]))
        next_timer: list[Any] = []
        for entry in range(n):
            incremented = timers[entry] + Const(1, 2)
            value_wide = Mux(
                write_req[entry], Const(0, 2),
                Mux(read_req[entry], timers[entry],
                    Mux((timers[entry] == 3) & _port(self, f"io_validInfo_{entry}"),
                        Const(3, 2), incremented)))
            # ageTimerNext is an explicitly two-bit Wire in Scala. Amaranth
            # widens addition, so truncate before both comparison and update.
            value = value_wide[:2]
            next_timer.append(value)
            m.d.sync += timers[entry].eq(value)
        for extra in extras:
            m.d.sync += extra.eq(extra + Const(1, 2))

        for row in range(n):
            for col in range(row + 1, n):
                valid_row = _port(self, f"io_validInfo_{row}")
                valid_col = _port(self, f"io_validInfo_{col}")
                if row // group == col // group:
                    left, right = next_timer[row], next_timer[col]
                else:
                    left = Cat(extras[row // group], next_timer[row])
                    right = Cat(extras[col // group], next_timer[col])
                cmp = cast(Any, left) >= cast(Any, right)
                value = Mux(valid_row & ~valid_col, 0,
                            Mux(~valid_row & valid_col, 1, cmp))
                m.d.comb += _port(self, f"io_ageInfo_{row}_{col}").eq(value)

    def _data_module(self, m: Module) -> None:
        """RegCacheDataModule.scala, including Chisel Vec padding semantics."""

        n = 16 if self.member == "RegCacheDataModule" else 12
        writes, reads = (4 if n == 16 else 3), 23
        valid = [Signal(reset=0, name=f"v_{i}") for i in range(n)]
        mem = [Signal(64, name=f"mem_{i}", reset_less=True) for i in range(n)]
        hits: list[list[Any]] = []
        for entry in range(n):
            row = [
                _port(self, f"io_writePorts_{p}_wen")
                & (_port(self, f"io_writePorts_{p}_addr") == entry)
                for p in range(writes)
            ]
            hits.append(row)
            any_hit = _or_all(row)
            data = _or_all([
                Mux(row[p], _port(self, f"io_writePorts_{p}_data"), Const(0, 64))
                for p in range(writes)
            ], 64)
            m.d.sync += valid[entry].eq(Mux(any_hit, 1, valid[entry]))
            m.d.sync += mem[entry].eq(Mux(any_hit, data, mem[entry]))
        for entry in range(n):
            m.d.comb += _port(self, f"io_validInfo_{entry}").eq(valid[entry])
        for p in range(reads):
            value = _indexed(mem, _port(self, f"io_readPorts_{p}_addr"), mem[0])
            m.d.comb += _port(self, f"io_readPorts_{p}_data").eq(value)

    def _tag_module(self, m: Module) -> None:
        """RegCacheTagModule.scala, including the optimized 12-entry variant."""

        n = 16 if self.member == "RegCacheTagModule" else 12
        writes, reads = (4 if n == 16 else 3), 12
        valid = [Signal(reset=0, name=f"v_{i}") for i in range(n)]
        tags = [Signal(8, name=f"tag_{i}", reset_less=True) for i in range(n)]
        deps = [[Signal(2, name=f"loadDependency_{i}_{d}", reset_less=True) for d in range(3)]
                for i in range(n)]
        write_hits: list[list[Any]] = []
        for entry in range(n):
            row = [
                _port(self, f"io_writePorts_{p}_wen")
                & (_port(self, f"io_writePorts_{p}_addr") == entry)
                for p in range(writes)
            ]
            write_hits.append(row)
            any_hit = _or_all(row)
            cancel = _port(self, f"io_cancelVec_{entry}")
            m.d.sync += valid[entry].eq(any_hit | (~cancel & valid[entry]))
            new_tag = _or_all([
                Mux(row[p], _port(self, f"io_writePorts_{p}_tag"), Const(0, 8))
                for p in range(writes)
            ], 8)
            m.d.sync += tags[entry].eq(Mux(any_hit, new_tag, tags[entry]))
            for dep_index in range(3):
                if f"io_writePorts_0_loadDependency_{dep_index}" in self.ports:
                    new_dep = _or_all([
                        Mux(row[p], _port(self, f"io_writePorts_{p}_loadDependency_{dep_index}"), Const(0, 2))
                        for p in range(writes)
                    ], 2)
                else:
                    # In the optimized 12-entry XSTop instance the parent ties
                    # this input bundle to constants; FIRRTL removes the ports
                    # and leaves {1'b0, wenOH_d} in dependency lane d.  Each
                    # lane therefore tracks only its matching write port; an
                    # any-write reduction here would incorrectly duplicate a
                    # hit into all three dependency lanes.
                    new_dep = Mux(row[dep_index], Const(1, 2), Const(0, 2))
                any_dep = _or_all([deps[entry][d].any() for d in range(3)])
                shifted = Cat(Const(0), deps[entry][dep_index][0])
                next_dep = Mux(_or_all(row), new_dep,
                               Mux(cancel | ~any_dep, deps[entry][dep_index], shifted))
                m.d.sync += deps[entry][dep_index].eq(next_dep)

        # Read match/one-hot address is purely combinational. OHToUInt in the
        # locked Chisel emits an OR-of-index-bits encoder (not a priority mux).
        for read in range(reads):
            query = _port(self, f"io_readPorts_{read}_tag")
            matches = [valid[i] & (tags[i] == query) for i in range(n)]
            m.d.comb += _port(self, f"io_readPorts_{read}_valid").eq(
                _port(self, f"io_readPorts_{read}_ren") & _or_all(matches))
            encoded: Any = Const(0, 4)
            for entry in range(n):
                encoded = encoded | Mux(matches[entry], Const(entry, 4), Const(0, 4))
            m.d.comb += _port(self, f"io_readPorts_{read}_addr").eq(encoded)
        for entry in range(n):
            m.d.comb += _port(self, f"io_validVec_{entry}").eq(valid[entry])
            m.d.comb += _port(self, f"io_tagVec_{entry}").eq(tags[entry])
            for dep_index in range(3):
                m.d.comb += _port(self, f"io_loadDependencyVec_{entry}_{dep_index}").eq(
                    deps[entry][dep_index])

    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        domain = ClockDomain("sync", async_reset=True)
        domain.clk = _port(self, "clock")
        domain.rst = _port(self, "reset")
        m.domains += domain
        if self.member.startswith("NewAgeDetector"):
            self._new_age(m)
        elif self.member.startswith("RegCacheAgeDetector"):
            self._regcache_age(m)
        elif self.member.startswith("RegCacheAgeTimer"):
            self._age_timer(m)
        elif self.member.startswith("RegCacheDataModule"):
            self._data_module(m)
        elif self.member.startswith("RegCacheTagModule"):
            self._tag_module(m)
        else:
            raise AssertionError(self.member)
        return m


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration: Any, injected_dependencies: Any) -> str:
    """Export one deterministic same-name age family member. / 导出确定性的同名年龄 family 成员。"""

    del injected_dependencies
    member = "NewAgeDetector"
    if isinstance(configuration, dict):
        member = str(configuration.get("module", member))
    elif isinstance(configuration, str):
        member = configuration
    top = AgeFamily(member)
    return verilog.convert(top, name=member, ports=[top.ports[n] for n, _d, _w in top.specs], emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    """Print the default age detector Verilog. / 打印默认年龄检测器 Verilog。"""

    print(build_verilog({"module": "NewAgeDetector"}, {}))


if __name__ == "__main__":
    main()
