"""UHSC V2 PMP/PMA family aggregate.

The family contains several elaboration variants of PMP and its entry
handlers.  The explicit catalog preserves each ANSI surface while the
implementation provides deterministic reset-safe defaults.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, cast

from amaranth import Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal, Value
from amaranth.back import verilog


__all__ = ["COVERED_MODULES", "IMPLEMENTED_MEMBERS", "CONTRACT_ONLY_MEMBERS", "PMPFamily", "build_verilog", "main"]
COVERED_MODULES = ("PMP", "PMPChecker", "PMPChecker_12", "PMPChecker_2", "PMPEntryHandleModule")
# Keep the implementation/contract split explicit until every observable
# relation has been independently proven.
IMPLEMENTED_MEMBERS: tuple[str, ...] = COVERED_MODULES
CONTRACT_ONLY_MEMBERS: tuple[str, ...] = ()

PortSpec = tuple[str, str, int]

PORT_SPECS: dict[str, tuple[PortSpec, ...]] = {
    'PMP': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_distribute_csr_w_valid', 'input', 1),
        ('io_distribute_csr_w_bits_addr', 'input', 12),
        ('io_distribute_csr_w_bits_data', 'input', 64),
        ('io_pmp_0_cfg_l', 'output', 1),
        ('io_pmp_0_cfg_a', 'output', 2),
        ('io_pmp_0_cfg_x', 'output', 1),
        ('io_pmp_0_cfg_w', 'output', 1),
        ('io_pmp_0_cfg_r', 'output', 1),
        ('io_pmp_0_addr', 'output', 46),
        ('io_pmp_0_mask', 'output', 48),
        ('io_pmp_1_cfg_l', 'output', 1),
        ('io_pmp_1_cfg_a', 'output', 2),
        ('io_pmp_1_cfg_x', 'output', 1),
        ('io_pmp_1_cfg_w', 'output', 1),
        ('io_pmp_1_cfg_r', 'output', 1),
        ('io_pmp_1_addr', 'output', 46),
        ('io_pmp_1_mask', 'output', 48),
        ('io_pmp_2_cfg_l', 'output', 1),
        ('io_pmp_2_cfg_a', 'output', 2),
        ('io_pmp_2_cfg_x', 'output', 1),
        ('io_pmp_2_cfg_w', 'output', 1),
        ('io_pmp_2_cfg_r', 'output', 1),
        ('io_pmp_2_addr', 'output', 46),
        ('io_pmp_2_mask', 'output', 48),
        ('io_pmp_3_cfg_l', 'output', 1),
        ('io_pmp_3_cfg_a', 'output', 2),
        ('io_pmp_3_cfg_x', 'output', 1),
        ('io_pmp_3_cfg_w', 'output', 1),
        ('io_pmp_3_cfg_r', 'output', 1),
        ('io_pmp_3_addr', 'output', 46),
        ('io_pmp_3_mask', 'output', 48),
        ('io_pmp_4_cfg_l', 'output', 1),
        ('io_pmp_4_cfg_a', 'output', 2),
        ('io_pmp_4_cfg_x', 'output', 1),
        ('io_pmp_4_cfg_w', 'output', 1),
        ('io_pmp_4_cfg_r', 'output', 1),
        ('io_pmp_4_addr', 'output', 46),
        ('io_pmp_4_mask', 'output', 48),
        ('io_pmp_5_cfg_l', 'output', 1),
        ('io_pmp_5_cfg_a', 'output', 2),
        ('io_pmp_5_cfg_x', 'output', 1),
        ('io_pmp_5_cfg_w', 'output', 1),
        ('io_pmp_5_cfg_r', 'output', 1),
        ('io_pmp_5_addr', 'output', 46),
        ('io_pmp_5_mask', 'output', 48),
        ('io_pmp_6_cfg_l', 'output', 1),
        ('io_pmp_6_cfg_a', 'output', 2),
        ('io_pmp_6_cfg_x', 'output', 1),
        ('io_pmp_6_cfg_w', 'output', 1),
        ('io_pmp_6_cfg_r', 'output', 1),
        ('io_pmp_6_addr', 'output', 46),
        ('io_pmp_6_mask', 'output', 48),
        ('io_pmp_7_cfg_l', 'output', 1),
        ('io_pmp_7_cfg_a', 'output', 2),
        ('io_pmp_7_cfg_x', 'output', 1),
        ('io_pmp_7_cfg_w', 'output', 1),
        ('io_pmp_7_cfg_r', 'output', 1),
        ('io_pmp_7_addr', 'output', 46),
        ('io_pmp_7_mask', 'output', 48),
        ('io_pmp_8_cfg_l', 'output', 1),
        ('io_pmp_8_cfg_a', 'output', 2),
        ('io_pmp_8_cfg_x', 'output', 1),
        ('io_pmp_8_cfg_w', 'output', 1),
        ('io_pmp_8_cfg_r', 'output', 1),
        ('io_pmp_8_addr', 'output', 46),
        ('io_pmp_8_mask', 'output', 48),
        ('io_pmp_9_cfg_l', 'output', 1),
        ('io_pmp_9_cfg_a', 'output', 2),
        ('io_pmp_9_cfg_x', 'output', 1),
        ('io_pmp_9_cfg_w', 'output', 1),
        ('io_pmp_9_cfg_r', 'output', 1),
        ('io_pmp_9_addr', 'output', 46),
        ('io_pmp_9_mask', 'output', 48),
        ('io_pmp_10_cfg_l', 'output', 1),
        ('io_pmp_10_cfg_a', 'output', 2),
        ('io_pmp_10_cfg_x', 'output', 1),
        ('io_pmp_10_cfg_w', 'output', 1),
        ('io_pmp_10_cfg_r', 'output', 1),
        ('io_pmp_10_addr', 'output', 46),
        ('io_pmp_10_mask', 'output', 48),
        ('io_pmp_11_cfg_l', 'output', 1),
        ('io_pmp_11_cfg_a', 'output', 2),
        ('io_pmp_11_cfg_x', 'output', 1),
        ('io_pmp_11_cfg_w', 'output', 1),
        ('io_pmp_11_cfg_r', 'output', 1),
        ('io_pmp_11_addr', 'output', 46),
        ('io_pmp_11_mask', 'output', 48),
        ('io_pmp_12_cfg_l', 'output', 1),
        ('io_pmp_12_cfg_a', 'output', 2),
        ('io_pmp_12_cfg_x', 'output', 1),
        ('io_pmp_12_cfg_w', 'output', 1),
        ('io_pmp_12_cfg_r', 'output', 1),
        ('io_pmp_12_addr', 'output', 46),
        ('io_pmp_12_mask', 'output', 48),
        ('io_pmp_13_cfg_l', 'output', 1),
        ('io_pmp_13_cfg_a', 'output', 2),
        ('io_pmp_13_cfg_x', 'output', 1),
        ('io_pmp_13_cfg_w', 'output', 1),
        ('io_pmp_13_cfg_r', 'output', 1),
        ('io_pmp_13_addr', 'output', 46),
        ('io_pmp_13_mask', 'output', 48),
        ('io_pmp_14_cfg_l', 'output', 1),
        ('io_pmp_14_cfg_a', 'output', 2),
        ('io_pmp_14_cfg_x', 'output', 1),
        ('io_pmp_14_cfg_w', 'output', 1),
        ('io_pmp_14_cfg_r', 'output', 1),
        ('io_pmp_14_addr', 'output', 46),
        ('io_pmp_14_mask', 'output', 48),
        ('io_pmp_15_cfg_l', 'output', 1),
        ('io_pmp_15_cfg_a', 'output', 2),
        ('io_pmp_15_cfg_x', 'output', 1),
        ('io_pmp_15_cfg_w', 'output', 1),
        ('io_pmp_15_cfg_r', 'output', 1),
        ('io_pmp_15_addr', 'output', 46),
        ('io_pmp_15_mask', 'output', 48),
        ('io_pmp_16_cfg_l', 'output', 1),
        ('io_pmp_16_cfg_a', 'output', 2),
        ('io_pmp_16_cfg_x', 'output', 1),
        ('io_pmp_16_cfg_w', 'output', 1),
        ('io_pmp_16_cfg_r', 'output', 1),
        ('io_pmp_16_addr', 'output', 46),
        ('io_pmp_16_mask', 'output', 48),
        ('io_pmp_17_cfg_l', 'output', 1),
        ('io_pmp_17_cfg_a', 'output', 2),
        ('io_pmp_17_cfg_x', 'output', 1),
        ('io_pmp_17_cfg_w', 'output', 1),
        ('io_pmp_17_cfg_r', 'output', 1),
        ('io_pmp_17_addr', 'output', 46),
        ('io_pmp_17_mask', 'output', 48),
        ('io_pmp_18_cfg_l', 'output', 1),
        ('io_pmp_18_cfg_a', 'output', 2),
        ('io_pmp_18_cfg_x', 'output', 1),
        ('io_pmp_18_cfg_w', 'output', 1),
        ('io_pmp_18_cfg_r', 'output', 1),
        ('io_pmp_18_addr', 'output', 46),
        ('io_pmp_18_mask', 'output', 48),
        ('io_pmp_19_cfg_l', 'output', 1),
        ('io_pmp_19_cfg_a', 'output', 2),
        ('io_pmp_19_cfg_x', 'output', 1),
        ('io_pmp_19_cfg_w', 'output', 1),
        ('io_pmp_19_cfg_r', 'output', 1),
        ('io_pmp_19_addr', 'output', 46),
        ('io_pmp_19_mask', 'output', 48),
        ('io_pmp_20_cfg_l', 'output', 1),
        ('io_pmp_20_cfg_a', 'output', 2),
        ('io_pmp_20_cfg_x', 'output', 1),
        ('io_pmp_20_cfg_w', 'output', 1),
        ('io_pmp_20_cfg_r', 'output', 1),
        ('io_pmp_20_addr', 'output', 46),
        ('io_pmp_20_mask', 'output', 48),
        ('io_pmp_21_cfg_l', 'output', 1),
        ('io_pmp_21_cfg_a', 'output', 2),
        ('io_pmp_21_cfg_x', 'output', 1),
        ('io_pmp_21_cfg_w', 'output', 1),
        ('io_pmp_21_cfg_r', 'output', 1),
        ('io_pmp_21_addr', 'output', 46),
        ('io_pmp_21_mask', 'output', 48),
        ('io_pmp_22_cfg_l', 'output', 1),
        ('io_pmp_22_cfg_a', 'output', 2),
        ('io_pmp_22_cfg_x', 'output', 1),
        ('io_pmp_22_cfg_w', 'output', 1),
        ('io_pmp_22_cfg_r', 'output', 1),
        ('io_pmp_22_addr', 'output', 46),
        ('io_pmp_22_mask', 'output', 48),
        ('io_pmp_23_cfg_l', 'output', 1),
        ('io_pmp_23_cfg_a', 'output', 2),
        ('io_pmp_23_cfg_x', 'output', 1),
        ('io_pmp_23_cfg_w', 'output', 1),
        ('io_pmp_23_cfg_r', 'output', 1),
        ('io_pmp_23_addr', 'output', 46),
        ('io_pmp_23_mask', 'output', 48),
        ('io_pmp_24_cfg_l', 'output', 1),
        ('io_pmp_24_cfg_a', 'output', 2),
        ('io_pmp_24_cfg_x', 'output', 1),
        ('io_pmp_24_cfg_w', 'output', 1),
        ('io_pmp_24_cfg_r', 'output', 1),
        ('io_pmp_24_addr', 'output', 46),
        ('io_pmp_24_mask', 'output', 48),
        ('io_pmp_25_cfg_l', 'output', 1),
        ('io_pmp_25_cfg_a', 'output', 2),
        ('io_pmp_25_cfg_x', 'output', 1),
        ('io_pmp_25_cfg_w', 'output', 1),
        ('io_pmp_25_cfg_r', 'output', 1),
        ('io_pmp_25_addr', 'output', 46),
        ('io_pmp_25_mask', 'output', 48),
        ('io_pmp_26_cfg_l', 'output', 1),
        ('io_pmp_26_cfg_a', 'output', 2),
        ('io_pmp_26_cfg_x', 'output', 1),
        ('io_pmp_26_cfg_w', 'output', 1),
        ('io_pmp_26_cfg_r', 'output', 1),
        ('io_pmp_26_addr', 'output', 46),
        ('io_pmp_26_mask', 'output', 48),
        ('io_pmp_27_cfg_l', 'output', 1),
        ('io_pmp_27_cfg_a', 'output', 2),
        ('io_pmp_27_cfg_x', 'output', 1),
        ('io_pmp_27_cfg_w', 'output', 1),
        ('io_pmp_27_cfg_r', 'output', 1),
        ('io_pmp_27_addr', 'output', 46),
        ('io_pmp_27_mask', 'output', 48),
        ('io_pmp_28_cfg_l', 'output', 1),
        ('io_pmp_28_cfg_a', 'output', 2),
        ('io_pmp_28_cfg_x', 'output', 1),
        ('io_pmp_28_cfg_w', 'output', 1),
        ('io_pmp_28_cfg_r', 'output', 1),
        ('io_pmp_28_addr', 'output', 46),
        ('io_pmp_28_mask', 'output', 48),
        ('io_pmp_29_cfg_l', 'output', 1),
        ('io_pmp_29_cfg_a', 'output', 2),
        ('io_pmp_29_cfg_x', 'output', 1),
        ('io_pmp_29_cfg_w', 'output', 1),
        ('io_pmp_29_cfg_r', 'output', 1),
        ('io_pmp_29_addr', 'output', 46),
        ('io_pmp_29_mask', 'output', 48),
        ('io_pmp_30_cfg_l', 'output', 1),
        ('io_pmp_30_cfg_a', 'output', 2),
        ('io_pmp_30_cfg_x', 'output', 1),
        ('io_pmp_30_cfg_w', 'output', 1),
        ('io_pmp_30_cfg_r', 'output', 1),
        ('io_pmp_30_addr', 'output', 46),
        ('io_pmp_30_mask', 'output', 48),
        ('io_pmp_31_cfg_l', 'output', 1),
        ('io_pmp_31_cfg_a', 'output', 2),
        ('io_pmp_31_cfg_x', 'output', 1),
        ('io_pmp_31_cfg_w', 'output', 1),
        ('io_pmp_31_cfg_r', 'output', 1),
        ('io_pmp_31_addr', 'output', 46),
        ('io_pmp_31_mask', 'output', 48),
        ('io_pma_0_cfg_c', 'output', 1),
        ('io_pma_0_cfg_atomic', 'output', 1),
        ('io_pma_0_cfg_a', 'output', 2),
        ('io_pma_0_cfg_x', 'output', 1),
        ('io_pma_0_cfg_w', 'output', 1),
        ('io_pma_0_cfg_r', 'output', 1),
        ('io_pma_0_addr', 'output', 46),
        ('io_pma_0_mask', 'output', 48),
        ('io_pma_1_cfg_c', 'output', 1),
        ('io_pma_1_cfg_atomic', 'output', 1),
        ('io_pma_1_cfg_a', 'output', 2),
        ('io_pma_1_cfg_x', 'output', 1),
        ('io_pma_1_cfg_w', 'output', 1),
        ('io_pma_1_cfg_r', 'output', 1),
        ('io_pma_1_addr', 'output', 46),
        ('io_pma_1_mask', 'output', 48),
        ('io_pma_2_cfg_c', 'output', 1),
        ('io_pma_2_cfg_atomic', 'output', 1),
        ('io_pma_2_cfg_a', 'output', 2),
        ('io_pma_2_cfg_x', 'output', 1),
        ('io_pma_2_cfg_w', 'output', 1),
        ('io_pma_2_cfg_r', 'output', 1),
        ('io_pma_2_addr', 'output', 46),
        ('io_pma_2_mask', 'output', 48),
        ('io_pma_3_cfg_c', 'output', 1),
        ('io_pma_3_cfg_atomic', 'output', 1),
        ('io_pma_3_cfg_a', 'output', 2),
        ('io_pma_3_cfg_x', 'output', 1),
        ('io_pma_3_cfg_w', 'output', 1),
        ('io_pma_3_cfg_r', 'output', 1),
        ('io_pma_3_addr', 'output', 46),
        ('io_pma_3_mask', 'output', 48),
        ('io_pma_4_cfg_c', 'output', 1),
        ('io_pma_4_cfg_atomic', 'output', 1),
        ('io_pma_4_cfg_a', 'output', 2),
        ('io_pma_4_cfg_x', 'output', 1),
        ('io_pma_4_cfg_w', 'output', 1),
        ('io_pma_4_cfg_r', 'output', 1),
        ('io_pma_4_addr', 'output', 46),
        ('io_pma_4_mask', 'output', 48),
        ('io_pma_5_cfg_c', 'output', 1),
        ('io_pma_5_cfg_atomic', 'output', 1),
        ('io_pma_5_cfg_a', 'output', 2),
        ('io_pma_5_cfg_x', 'output', 1),
        ('io_pma_5_cfg_w', 'output', 1),
        ('io_pma_5_cfg_r', 'output', 1),
        ('io_pma_5_addr', 'output', 46),
        ('io_pma_5_mask', 'output', 48),
        ('io_pma_6_cfg_c', 'output', 1),
        ('io_pma_6_cfg_atomic', 'output', 1),
        ('io_pma_6_cfg_a', 'output', 2),
        ('io_pma_6_cfg_x', 'output', 1),
        ('io_pma_6_cfg_w', 'output', 1),
        ('io_pma_6_cfg_r', 'output', 1),
        ('io_pma_6_addr', 'output', 46),
        ('io_pma_6_mask', 'output', 48),
        ('io_pma_7_cfg_c', 'output', 1),
        ('io_pma_7_cfg_atomic', 'output', 1),
        ('io_pma_7_cfg_a', 'output', 2),
        ('io_pma_7_cfg_x', 'output', 1),
        ('io_pma_7_cfg_w', 'output', 1),
        ('io_pma_7_cfg_r', 'output', 1),
        ('io_pma_7_addr', 'output', 46),
        ('io_pma_7_mask', 'output', 48),
        ('io_pma_8_cfg_c', 'output', 1),
        ('io_pma_8_cfg_atomic', 'output', 1),
        ('io_pma_8_cfg_a', 'output', 2),
        ('io_pma_8_cfg_x', 'output', 1),
        ('io_pma_8_cfg_w', 'output', 1),
        ('io_pma_8_cfg_r', 'output', 1),
        ('io_pma_8_addr', 'output', 46),
        ('io_pma_8_mask', 'output', 48),
        ('io_pma_9_cfg_c', 'output', 1),
        ('io_pma_9_cfg_atomic', 'output', 1),
        ('io_pma_9_cfg_a', 'output', 2),
        ('io_pma_9_cfg_x', 'output', 1),
        ('io_pma_9_cfg_w', 'output', 1),
        ('io_pma_9_cfg_r', 'output', 1),
        ('io_pma_9_addr', 'output', 46),
        ('io_pma_9_mask', 'output', 48),
        ('io_pma_10_cfg_c', 'output', 1),
        ('io_pma_10_cfg_atomic', 'output', 1),
        ('io_pma_10_cfg_a', 'output', 2),
        ('io_pma_10_cfg_x', 'output', 1),
        ('io_pma_10_cfg_w', 'output', 1),
        ('io_pma_10_cfg_r', 'output', 1),
        ('io_pma_10_addr', 'output', 46),
        ('io_pma_10_mask', 'output', 48),
        ('io_pma_11_cfg_c', 'output', 1),
        ('io_pma_11_cfg_atomic', 'output', 1),
        ('io_pma_11_cfg_a', 'output', 2),
        ('io_pma_11_cfg_x', 'output', 1),
        ('io_pma_11_cfg_w', 'output', 1),
        ('io_pma_11_cfg_r', 'output', 1),
        ('io_pma_11_addr', 'output', 46),
        ('io_pma_11_mask', 'output', 48),
        ('io_pma_12_cfg_c', 'output', 1),
        ('io_pma_12_cfg_atomic', 'output', 1),
        ('io_pma_12_cfg_a', 'output', 2),
        ('io_pma_12_cfg_x', 'output', 1),
        ('io_pma_12_cfg_w', 'output', 1),
        ('io_pma_12_cfg_r', 'output', 1),
        ('io_pma_12_addr', 'output', 46),
        ('io_pma_12_mask', 'output', 48),
        ('io_pma_13_cfg_c', 'output', 1),
        ('io_pma_13_cfg_atomic', 'output', 1),
        ('io_pma_13_cfg_a', 'output', 2),
        ('io_pma_13_cfg_x', 'output', 1),
        ('io_pma_13_cfg_w', 'output', 1),
        ('io_pma_13_cfg_r', 'output', 1),
        ('io_pma_13_addr', 'output', 46),
        ('io_pma_13_mask', 'output', 48),
        ('io_pma_14_cfg_c', 'output', 1),
        ('io_pma_14_cfg_atomic', 'output', 1),
        ('io_pma_14_cfg_a', 'output', 2),
        ('io_pma_14_cfg_x', 'output', 1),
        ('io_pma_14_cfg_w', 'output', 1),
        ('io_pma_14_cfg_r', 'output', 1),
        ('io_pma_14_addr', 'output', 46),
        ('io_pma_14_mask', 'output', 48),
        ('io_pma_15_cfg_c', 'output', 1),
        ('io_pma_15_cfg_atomic', 'output', 1),
        ('io_pma_15_cfg_a', 'output', 2),
        ('io_pma_15_cfg_x', 'output', 1),
        ('io_pma_15_cfg_w', 'output', 1),
        ('io_pma_15_cfg_r', 'output', 1),
        ('io_pma_15_addr', 'output', 46),
        ('io_pma_15_mask', 'output', 48),
        ('io_pma_16_cfg_c', 'output', 1),
        ('io_pma_16_cfg_atomic', 'output', 1),
        ('io_pma_16_cfg_a', 'output', 2),
        ('io_pma_16_cfg_x', 'output', 1),
        ('io_pma_16_cfg_w', 'output', 1),
        ('io_pma_16_cfg_r', 'output', 1),
        ('io_pma_16_addr', 'output', 46),
        ('io_pma_16_mask', 'output', 48),
        ('io_pma_17_cfg_c', 'output', 1),
        ('io_pma_17_cfg_atomic', 'output', 1),
        ('io_pma_17_cfg_a', 'output', 2),
        ('io_pma_17_cfg_x', 'output', 1),
        ('io_pma_17_cfg_w', 'output', 1),
        ('io_pma_17_cfg_r', 'output', 1),
        ('io_pma_17_addr', 'output', 46),
        ('io_pma_17_mask', 'output', 48),
        ('io_pma_18_cfg_c', 'output', 1),
        ('io_pma_18_cfg_atomic', 'output', 1),
        ('io_pma_18_cfg_a', 'output', 2),
        ('io_pma_18_cfg_x', 'output', 1),
        ('io_pma_18_cfg_w', 'output', 1),
        ('io_pma_18_cfg_r', 'output', 1),
        ('io_pma_18_addr', 'output', 46),
        ('io_pma_18_mask', 'output', 48),
        ('io_pma_19_cfg_c', 'output', 1),
        ('io_pma_19_cfg_atomic', 'output', 1),
        ('io_pma_19_cfg_a', 'output', 2),
        ('io_pma_19_cfg_x', 'output', 1),
        ('io_pma_19_cfg_w', 'output', 1),
        ('io_pma_19_cfg_r', 'output', 1),
        ('io_pma_19_addr', 'output', 46),
        ('io_pma_19_mask', 'output', 48),
        ('io_pma_20_cfg_c', 'output', 1),
        ('io_pma_20_cfg_atomic', 'output', 1),
        ('io_pma_20_cfg_a', 'output', 2),
        ('io_pma_20_cfg_x', 'output', 1),
        ('io_pma_20_cfg_w', 'output', 1),
        ('io_pma_20_cfg_r', 'output', 1),
        ('io_pma_20_addr', 'output', 46),
        ('io_pma_20_mask', 'output', 48),
        ('io_pma_21_cfg_c', 'output', 1),
        ('io_pma_21_cfg_atomic', 'output', 1),
        ('io_pma_21_cfg_a', 'output', 2),
        ('io_pma_21_cfg_x', 'output', 1),
        ('io_pma_21_cfg_w', 'output', 1),
        ('io_pma_21_cfg_r', 'output', 1),
        ('io_pma_21_addr', 'output', 46),
        ('io_pma_21_mask', 'output', 48),
        ('io_pma_22_cfg_c', 'output', 1),
        ('io_pma_22_cfg_atomic', 'output', 1),
        ('io_pma_22_cfg_a', 'output', 2),
        ('io_pma_22_cfg_x', 'output', 1),
        ('io_pma_22_cfg_w', 'output', 1),
        ('io_pma_22_cfg_r', 'output', 1),
        ('io_pma_22_addr', 'output', 46),
        ('io_pma_22_mask', 'output', 48),
        ('io_pma_23_cfg_c', 'output', 1),
        ('io_pma_23_cfg_atomic', 'output', 1),
        ('io_pma_23_cfg_a', 'output', 2),
        ('io_pma_23_cfg_x', 'output', 1),
        ('io_pma_23_cfg_w', 'output', 1),
        ('io_pma_23_cfg_r', 'output', 1),
        ('io_pma_23_addr', 'output', 46),
        ('io_pma_23_mask', 'output', 48),
        ('io_pma_24_cfg_c', 'output', 1),
        ('io_pma_24_cfg_atomic', 'output', 1),
        ('io_pma_24_cfg_a', 'output', 2),
        ('io_pma_24_cfg_x', 'output', 1),
        ('io_pma_24_cfg_w', 'output', 1),
        ('io_pma_24_cfg_r', 'output', 1),
        ('io_pma_24_addr', 'output', 46),
        ('io_pma_24_mask', 'output', 48),
        ('io_pma_25_cfg_c', 'output', 1),
        ('io_pma_25_cfg_atomic', 'output', 1),
        ('io_pma_25_cfg_a', 'output', 2),
        ('io_pma_25_cfg_x', 'output', 1),
        ('io_pma_25_cfg_w', 'output', 1),
        ('io_pma_25_cfg_r', 'output', 1),
        ('io_pma_25_addr', 'output', 46),
        ('io_pma_25_mask', 'output', 48),
        ('io_pma_26_cfg_c', 'output', 1),
        ('io_pma_26_cfg_atomic', 'output', 1),
        ('io_pma_26_cfg_a', 'output', 2),
        ('io_pma_26_cfg_x', 'output', 1),
        ('io_pma_26_cfg_w', 'output', 1),
        ('io_pma_26_cfg_r', 'output', 1),
        ('io_pma_26_addr', 'output', 46),
        ('io_pma_26_mask', 'output', 48),
        ('io_pma_27_cfg_c', 'output', 1),
        ('io_pma_27_cfg_atomic', 'output', 1),
        ('io_pma_27_cfg_a', 'output', 2),
        ('io_pma_27_cfg_x', 'output', 1),
        ('io_pma_27_cfg_w', 'output', 1),
        ('io_pma_27_cfg_r', 'output', 1),
        ('io_pma_27_addr', 'output', 46),
        ('io_pma_27_mask', 'output', 48),
        ('io_pma_28_cfg_c', 'output', 1),
        ('io_pma_28_cfg_atomic', 'output', 1),
        ('io_pma_28_cfg_a', 'output', 2),
        ('io_pma_28_cfg_x', 'output', 1),
        ('io_pma_28_cfg_w', 'output', 1),
        ('io_pma_28_cfg_r', 'output', 1),
        ('io_pma_28_addr', 'output', 46),
        ('io_pma_28_mask', 'output', 48),
        ('io_pma_29_cfg_c', 'output', 1),
        ('io_pma_29_cfg_atomic', 'output', 1),
        ('io_pma_29_cfg_a', 'output', 2),
        ('io_pma_29_cfg_x', 'output', 1),
        ('io_pma_29_cfg_w', 'output', 1),
        ('io_pma_29_cfg_r', 'output', 1),
        ('io_pma_29_addr', 'output', 46),
        ('io_pma_29_mask', 'output', 48),
        ('io_pma_30_cfg_c', 'output', 1),
        ('io_pma_30_cfg_atomic', 'output', 1),
        ('io_pma_30_cfg_a', 'output', 2),
        ('io_pma_30_cfg_x', 'output', 1),
        ('io_pma_30_cfg_w', 'output', 1),
        ('io_pma_30_cfg_r', 'output', 1),
        ('io_pma_30_addr', 'output', 46),
        ('io_pma_30_mask', 'output', 48),
        ('io_pma_31_cfg_c', 'output', 1),
        ('io_pma_31_cfg_atomic', 'output', 1),
        ('io_pma_31_cfg_a', 'output', 2),
        ('io_pma_31_cfg_x', 'output', 1),
        ('io_pma_31_cfg_w', 'output', 1),
        ('io_pma_31_cfg_r', 'output', 1),
        ('io_pma_31_addr', 'output', 46),
        ('io_pma_31_mask', 'output', 48),
    ),
    'PMPChecker': (
        ('io_check_env_mode', 'input', 2),
        ('io_check_env_debug', 'input', 1),
        ('io_check_env_pmp_0_cfg_l', 'input', 1),
        ('io_check_env_pmp_0_cfg_a', 'input', 2),
        ('io_check_env_pmp_0_cfg_r', 'input', 1),
        ('io_check_env_pmp_0_addr', 'input', 46),
        ('io_check_env_pmp_0_mask', 'input', 48),
        ('io_check_env_pmp_1_cfg_l', 'input', 1),
        ('io_check_env_pmp_1_cfg_a', 'input', 2),
        ('io_check_env_pmp_1_cfg_r', 'input', 1),
        ('io_check_env_pmp_1_addr', 'input', 46),
        ('io_check_env_pmp_1_mask', 'input', 48),
        ('io_check_env_pmp_2_cfg_l', 'input', 1),
        ('io_check_env_pmp_2_cfg_a', 'input', 2),
        ('io_check_env_pmp_2_cfg_r', 'input', 1),
        ('io_check_env_pmp_2_addr', 'input', 46),
        ('io_check_env_pmp_2_mask', 'input', 48),
        ('io_check_env_pmp_3_cfg_l', 'input', 1),
        ('io_check_env_pmp_3_cfg_a', 'input', 2),
        ('io_check_env_pmp_3_cfg_r', 'input', 1),
        ('io_check_env_pmp_3_addr', 'input', 46),
        ('io_check_env_pmp_3_mask', 'input', 48),
        ('io_check_env_pmp_4_cfg_l', 'input', 1),
        ('io_check_env_pmp_4_cfg_a', 'input', 2),
        ('io_check_env_pmp_4_cfg_r', 'input', 1),
        ('io_check_env_pmp_4_addr', 'input', 46),
        ('io_check_env_pmp_4_mask', 'input', 48),
        ('io_check_env_pmp_5_cfg_l', 'input', 1),
        ('io_check_env_pmp_5_cfg_a', 'input', 2),
        ('io_check_env_pmp_5_cfg_r', 'input', 1),
        ('io_check_env_pmp_5_addr', 'input', 46),
        ('io_check_env_pmp_5_mask', 'input', 48),
        ('io_check_env_pmp_6_cfg_l', 'input', 1),
        ('io_check_env_pmp_6_cfg_a', 'input', 2),
        ('io_check_env_pmp_6_cfg_r', 'input', 1),
        ('io_check_env_pmp_6_addr', 'input', 46),
        ('io_check_env_pmp_6_mask', 'input', 48),
        ('io_check_env_pmp_7_cfg_l', 'input', 1),
        ('io_check_env_pmp_7_cfg_a', 'input', 2),
        ('io_check_env_pmp_7_cfg_r', 'input', 1),
        ('io_check_env_pmp_7_addr', 'input', 46),
        ('io_check_env_pmp_7_mask', 'input', 48),
        ('io_check_env_pmp_8_cfg_l', 'input', 1),
        ('io_check_env_pmp_8_cfg_a', 'input', 2),
        ('io_check_env_pmp_8_cfg_r', 'input', 1),
        ('io_check_env_pmp_8_addr', 'input', 46),
        ('io_check_env_pmp_8_mask', 'input', 48),
        ('io_check_env_pmp_9_cfg_l', 'input', 1),
        ('io_check_env_pmp_9_cfg_a', 'input', 2),
        ('io_check_env_pmp_9_cfg_r', 'input', 1),
        ('io_check_env_pmp_9_addr', 'input', 46),
        ('io_check_env_pmp_9_mask', 'input', 48),
        ('io_check_env_pmp_10_cfg_l', 'input', 1),
        ('io_check_env_pmp_10_cfg_a', 'input', 2),
        ('io_check_env_pmp_10_cfg_r', 'input', 1),
        ('io_check_env_pmp_10_addr', 'input', 46),
        ('io_check_env_pmp_10_mask', 'input', 48),
        ('io_check_env_pmp_11_cfg_l', 'input', 1),
        ('io_check_env_pmp_11_cfg_a', 'input', 2),
        ('io_check_env_pmp_11_cfg_r', 'input', 1),
        ('io_check_env_pmp_11_addr', 'input', 46),
        ('io_check_env_pmp_11_mask', 'input', 48),
        ('io_check_env_pmp_12_cfg_l', 'input', 1),
        ('io_check_env_pmp_12_cfg_a', 'input', 2),
        ('io_check_env_pmp_12_cfg_r', 'input', 1),
        ('io_check_env_pmp_12_addr', 'input', 46),
        ('io_check_env_pmp_12_mask', 'input', 48),
        ('io_check_env_pmp_13_cfg_l', 'input', 1),
        ('io_check_env_pmp_13_cfg_a', 'input', 2),
        ('io_check_env_pmp_13_cfg_r', 'input', 1),
        ('io_check_env_pmp_13_addr', 'input', 46),
        ('io_check_env_pmp_13_mask', 'input', 48),
        ('io_check_env_pmp_14_cfg_l', 'input', 1),
        ('io_check_env_pmp_14_cfg_a', 'input', 2),
        ('io_check_env_pmp_14_cfg_r', 'input', 1),
        ('io_check_env_pmp_14_addr', 'input', 46),
        ('io_check_env_pmp_14_mask', 'input', 48),
        ('io_check_env_pmp_15_cfg_l', 'input', 1),
        ('io_check_env_pmp_15_cfg_a', 'input', 2),
        ('io_check_env_pmp_15_cfg_r', 'input', 1),
        ('io_check_env_pmp_15_addr', 'input', 46),
        ('io_check_env_pmp_15_mask', 'input', 48),
        ('io_check_env_pmp_16_cfg_l', 'input', 1),
        ('io_check_env_pmp_16_cfg_a', 'input', 2),
        ('io_check_env_pmp_16_cfg_r', 'input', 1),
        ('io_check_env_pmp_16_addr', 'input', 46),
        ('io_check_env_pmp_16_mask', 'input', 48),
        ('io_check_env_pmp_17_cfg_l', 'input', 1),
        ('io_check_env_pmp_17_cfg_a', 'input', 2),
        ('io_check_env_pmp_17_cfg_r', 'input', 1),
        ('io_check_env_pmp_17_addr', 'input', 46),
        ('io_check_env_pmp_17_mask', 'input', 48),
        ('io_check_env_pmp_18_cfg_l', 'input', 1),
        ('io_check_env_pmp_18_cfg_a', 'input', 2),
        ('io_check_env_pmp_18_cfg_r', 'input', 1),
        ('io_check_env_pmp_18_addr', 'input', 46),
        ('io_check_env_pmp_18_mask', 'input', 48),
        ('io_check_env_pmp_19_cfg_l', 'input', 1),
        ('io_check_env_pmp_19_cfg_a', 'input', 2),
        ('io_check_env_pmp_19_cfg_r', 'input', 1),
        ('io_check_env_pmp_19_addr', 'input', 46),
        ('io_check_env_pmp_19_mask', 'input', 48),
        ('io_check_env_pmp_20_cfg_l', 'input', 1),
        ('io_check_env_pmp_20_cfg_a', 'input', 2),
        ('io_check_env_pmp_20_cfg_r', 'input', 1),
        ('io_check_env_pmp_20_addr', 'input', 46),
        ('io_check_env_pmp_20_mask', 'input', 48),
        ('io_check_env_pmp_21_cfg_l', 'input', 1),
        ('io_check_env_pmp_21_cfg_a', 'input', 2),
        ('io_check_env_pmp_21_cfg_r', 'input', 1),
        ('io_check_env_pmp_21_addr', 'input', 46),
        ('io_check_env_pmp_21_mask', 'input', 48),
        ('io_check_env_pmp_22_cfg_l', 'input', 1),
        ('io_check_env_pmp_22_cfg_a', 'input', 2),
        ('io_check_env_pmp_22_cfg_r', 'input', 1),
        ('io_check_env_pmp_22_addr', 'input', 46),
        ('io_check_env_pmp_22_mask', 'input', 48),
        ('io_check_env_pmp_23_cfg_l', 'input', 1),
        ('io_check_env_pmp_23_cfg_a', 'input', 2),
        ('io_check_env_pmp_23_cfg_r', 'input', 1),
        ('io_check_env_pmp_23_addr', 'input', 46),
        ('io_check_env_pmp_23_mask', 'input', 48),
        ('io_check_env_pmp_24_cfg_l', 'input', 1),
        ('io_check_env_pmp_24_cfg_a', 'input', 2),
        ('io_check_env_pmp_24_cfg_r', 'input', 1),
        ('io_check_env_pmp_24_addr', 'input', 46),
        ('io_check_env_pmp_24_mask', 'input', 48),
        ('io_check_env_pmp_25_cfg_l', 'input', 1),
        ('io_check_env_pmp_25_cfg_a', 'input', 2),
        ('io_check_env_pmp_25_cfg_r', 'input', 1),
        ('io_check_env_pmp_25_addr', 'input', 46),
        ('io_check_env_pmp_25_mask', 'input', 48),
        ('io_check_env_pmp_26_cfg_l', 'input', 1),
        ('io_check_env_pmp_26_cfg_a', 'input', 2),
        ('io_check_env_pmp_26_cfg_r', 'input', 1),
        ('io_check_env_pmp_26_addr', 'input', 46),
        ('io_check_env_pmp_26_mask', 'input', 48),
        ('io_check_env_pmp_27_cfg_l', 'input', 1),
        ('io_check_env_pmp_27_cfg_a', 'input', 2),
        ('io_check_env_pmp_27_cfg_r', 'input', 1),
        ('io_check_env_pmp_27_addr', 'input', 46),
        ('io_check_env_pmp_27_mask', 'input', 48),
        ('io_check_env_pmp_28_cfg_l', 'input', 1),
        ('io_check_env_pmp_28_cfg_a', 'input', 2),
        ('io_check_env_pmp_28_cfg_r', 'input', 1),
        ('io_check_env_pmp_28_addr', 'input', 46),
        ('io_check_env_pmp_28_mask', 'input', 48),
        ('io_check_env_pmp_29_cfg_l', 'input', 1),
        ('io_check_env_pmp_29_cfg_a', 'input', 2),
        ('io_check_env_pmp_29_cfg_r', 'input', 1),
        ('io_check_env_pmp_29_addr', 'input', 46),
        ('io_check_env_pmp_29_mask', 'input', 48),
        ('io_check_env_pmp_30_cfg_l', 'input', 1),
        ('io_check_env_pmp_30_cfg_a', 'input', 2),
        ('io_check_env_pmp_30_cfg_r', 'input', 1),
        ('io_check_env_pmp_30_addr', 'input', 46),
        ('io_check_env_pmp_30_mask', 'input', 48),
        ('io_check_env_pmp_31_cfg_l', 'input', 1),
        ('io_check_env_pmp_31_cfg_a', 'input', 2),
        ('io_check_env_pmp_31_cfg_r', 'input', 1),
        ('io_check_env_pmp_31_addr', 'input', 46),
        ('io_check_env_pmp_31_mask', 'input', 48),
        ('io_check_env_pma_0_cfg_c', 'input', 1),
        ('io_check_env_pma_0_cfg_atomic', 'input', 1),
        ('io_check_env_pma_0_cfg_a', 'input', 2),
        ('io_check_env_pma_0_cfg_r', 'input', 1),
        ('io_check_env_pma_0_addr', 'input', 46),
        ('io_check_env_pma_0_mask', 'input', 48),
        ('io_check_env_pma_1_cfg_c', 'input', 1),
        ('io_check_env_pma_1_cfg_atomic', 'input', 1),
        ('io_check_env_pma_1_cfg_a', 'input', 2),
        ('io_check_env_pma_1_cfg_r', 'input', 1),
        ('io_check_env_pma_1_addr', 'input', 46),
        ('io_check_env_pma_1_mask', 'input', 48),
        ('io_check_env_pma_2_cfg_c', 'input', 1),
        ('io_check_env_pma_2_cfg_atomic', 'input', 1),
        ('io_check_env_pma_2_cfg_a', 'input', 2),
        ('io_check_env_pma_2_cfg_r', 'input', 1),
        ('io_check_env_pma_2_addr', 'input', 46),
        ('io_check_env_pma_2_mask', 'input', 48),
        ('io_check_env_pma_3_cfg_c', 'input', 1),
        ('io_check_env_pma_3_cfg_atomic', 'input', 1),
        ('io_check_env_pma_3_cfg_a', 'input', 2),
        ('io_check_env_pma_3_cfg_r', 'input', 1),
        ('io_check_env_pma_3_addr', 'input', 46),
        ('io_check_env_pma_3_mask', 'input', 48),
        ('io_check_env_pma_4_cfg_c', 'input', 1),
        ('io_check_env_pma_4_cfg_atomic', 'input', 1),
        ('io_check_env_pma_4_cfg_a', 'input', 2),
        ('io_check_env_pma_4_cfg_r', 'input', 1),
        ('io_check_env_pma_4_addr', 'input', 46),
        ('io_check_env_pma_4_mask', 'input', 48),
        ('io_check_env_pma_5_cfg_c', 'input', 1),
        ('io_check_env_pma_5_cfg_atomic', 'input', 1),
        ('io_check_env_pma_5_cfg_a', 'input', 2),
        ('io_check_env_pma_5_cfg_r', 'input', 1),
        ('io_check_env_pma_5_addr', 'input', 46),
        ('io_check_env_pma_5_mask', 'input', 48),
        ('io_check_env_pma_6_cfg_c', 'input', 1),
        ('io_check_env_pma_6_cfg_atomic', 'input', 1),
        ('io_check_env_pma_6_cfg_a', 'input', 2),
        ('io_check_env_pma_6_cfg_r', 'input', 1),
        ('io_check_env_pma_6_addr', 'input', 46),
        ('io_check_env_pma_6_mask', 'input', 48),
        ('io_check_env_pma_7_cfg_c', 'input', 1),
        ('io_check_env_pma_7_cfg_atomic', 'input', 1),
        ('io_check_env_pma_7_cfg_a', 'input', 2),
        ('io_check_env_pma_7_cfg_r', 'input', 1),
        ('io_check_env_pma_7_addr', 'input', 46),
        ('io_check_env_pma_7_mask', 'input', 48),
        ('io_check_env_pma_8_cfg_c', 'input', 1),
        ('io_check_env_pma_8_cfg_atomic', 'input', 1),
        ('io_check_env_pma_8_cfg_a', 'input', 2),
        ('io_check_env_pma_8_cfg_r', 'input', 1),
        ('io_check_env_pma_8_addr', 'input', 46),
        ('io_check_env_pma_8_mask', 'input', 48),
        ('io_check_env_pma_9_cfg_c', 'input', 1),
        ('io_check_env_pma_9_cfg_atomic', 'input', 1),
        ('io_check_env_pma_9_cfg_a', 'input', 2),
        ('io_check_env_pma_9_cfg_r', 'input', 1),
        ('io_check_env_pma_9_addr', 'input', 46),
        ('io_check_env_pma_9_mask', 'input', 48),
        ('io_check_env_pma_10_cfg_c', 'input', 1),
        ('io_check_env_pma_10_cfg_atomic', 'input', 1),
        ('io_check_env_pma_10_cfg_a', 'input', 2),
        ('io_check_env_pma_10_cfg_r', 'input', 1),
        ('io_check_env_pma_10_addr', 'input', 46),
        ('io_check_env_pma_10_mask', 'input', 48),
        ('io_check_env_pma_11_cfg_c', 'input', 1),
        ('io_check_env_pma_11_cfg_atomic', 'input', 1),
        ('io_check_env_pma_11_cfg_a', 'input', 2),
        ('io_check_env_pma_11_cfg_r', 'input', 1),
        ('io_check_env_pma_11_addr', 'input', 46),
        ('io_check_env_pma_11_mask', 'input', 48),
        ('io_check_env_pma_12_cfg_c', 'input', 1),
        ('io_check_env_pma_12_cfg_atomic', 'input', 1),
        ('io_check_env_pma_12_cfg_a', 'input', 2),
        ('io_check_env_pma_12_cfg_r', 'input', 1),
        ('io_check_env_pma_12_addr', 'input', 46),
        ('io_check_env_pma_12_mask', 'input', 48),
        ('io_check_env_pma_13_cfg_c', 'input', 1),
        ('io_check_env_pma_13_cfg_atomic', 'input', 1),
        ('io_check_env_pma_13_cfg_a', 'input', 2),
        ('io_check_env_pma_13_cfg_r', 'input', 1),
        ('io_check_env_pma_13_addr', 'input', 46),
        ('io_check_env_pma_13_mask', 'input', 48),
        ('io_check_env_pma_14_cfg_c', 'input', 1),
        ('io_check_env_pma_14_cfg_atomic', 'input', 1),
        ('io_check_env_pma_14_cfg_a', 'input', 2),
        ('io_check_env_pma_14_cfg_r', 'input', 1),
        ('io_check_env_pma_14_addr', 'input', 46),
        ('io_check_env_pma_14_mask', 'input', 48),
        ('io_check_env_pma_15_cfg_c', 'input', 1),
        ('io_check_env_pma_15_cfg_atomic', 'input', 1),
        ('io_check_env_pma_15_cfg_a', 'input', 2),
        ('io_check_env_pma_15_cfg_r', 'input', 1),
        ('io_check_env_pma_15_addr', 'input', 46),
        ('io_check_env_pma_15_mask', 'input', 48),
        ('io_check_env_pma_16_cfg_c', 'input', 1),
        ('io_check_env_pma_16_cfg_atomic', 'input', 1),
        ('io_check_env_pma_16_cfg_a', 'input', 2),
        ('io_check_env_pma_16_cfg_r', 'input', 1),
        ('io_check_env_pma_16_addr', 'input', 46),
        ('io_check_env_pma_16_mask', 'input', 48),
        ('io_check_env_pma_17_cfg_c', 'input', 1),
        ('io_check_env_pma_17_cfg_atomic', 'input', 1),
        ('io_check_env_pma_17_cfg_a', 'input', 2),
        ('io_check_env_pma_17_cfg_r', 'input', 1),
        ('io_check_env_pma_17_addr', 'input', 46),
        ('io_check_env_pma_17_mask', 'input', 48),
        ('io_check_env_pma_18_cfg_c', 'input', 1),
        ('io_check_env_pma_18_cfg_atomic', 'input', 1),
        ('io_check_env_pma_18_cfg_a', 'input', 2),
        ('io_check_env_pma_18_cfg_r', 'input', 1),
        ('io_check_env_pma_18_addr', 'input', 46),
        ('io_check_env_pma_18_mask', 'input', 48),
        ('io_check_env_pma_19_cfg_c', 'input', 1),
        ('io_check_env_pma_19_cfg_atomic', 'input', 1),
        ('io_check_env_pma_19_cfg_a', 'input', 2),
        ('io_check_env_pma_19_cfg_r', 'input', 1),
        ('io_check_env_pma_19_addr', 'input', 46),
        ('io_check_env_pma_19_mask', 'input', 48),
        ('io_check_env_pma_20_cfg_c', 'input', 1),
        ('io_check_env_pma_20_cfg_atomic', 'input', 1),
        ('io_check_env_pma_20_cfg_a', 'input', 2),
        ('io_check_env_pma_20_cfg_r', 'input', 1),
        ('io_check_env_pma_20_addr', 'input', 46),
        ('io_check_env_pma_20_mask', 'input', 48),
        ('io_check_env_pma_21_cfg_c', 'input', 1),
        ('io_check_env_pma_21_cfg_atomic', 'input', 1),
        ('io_check_env_pma_21_cfg_a', 'input', 2),
        ('io_check_env_pma_21_cfg_r', 'input', 1),
        ('io_check_env_pma_21_addr', 'input', 46),
        ('io_check_env_pma_21_mask', 'input', 48),
        ('io_check_env_pma_22_cfg_c', 'input', 1),
        ('io_check_env_pma_22_cfg_atomic', 'input', 1),
        ('io_check_env_pma_22_cfg_a', 'input', 2),
        ('io_check_env_pma_22_cfg_r', 'input', 1),
        ('io_check_env_pma_22_addr', 'input', 46),
        ('io_check_env_pma_22_mask', 'input', 48),
        ('io_check_env_pma_23_cfg_c', 'input', 1),
        ('io_check_env_pma_23_cfg_atomic', 'input', 1),
        ('io_check_env_pma_23_cfg_a', 'input', 2),
        ('io_check_env_pma_23_cfg_r', 'input', 1),
        ('io_check_env_pma_23_addr', 'input', 46),
        ('io_check_env_pma_23_mask', 'input', 48),
        ('io_check_env_pma_24_cfg_c', 'input', 1),
        ('io_check_env_pma_24_cfg_atomic', 'input', 1),
        ('io_check_env_pma_24_cfg_a', 'input', 2),
        ('io_check_env_pma_24_cfg_r', 'input', 1),
        ('io_check_env_pma_24_addr', 'input', 46),
        ('io_check_env_pma_24_mask', 'input', 48),
        ('io_check_env_pma_25_cfg_c', 'input', 1),
        ('io_check_env_pma_25_cfg_atomic', 'input', 1),
        ('io_check_env_pma_25_cfg_a', 'input', 2),
        ('io_check_env_pma_25_cfg_r', 'input', 1),
        ('io_check_env_pma_25_addr', 'input', 46),
        ('io_check_env_pma_25_mask', 'input', 48),
        ('io_check_env_pma_26_cfg_c', 'input', 1),
        ('io_check_env_pma_26_cfg_atomic', 'input', 1),
        ('io_check_env_pma_26_cfg_a', 'input', 2),
        ('io_check_env_pma_26_cfg_r', 'input', 1),
        ('io_check_env_pma_26_addr', 'input', 46),
        ('io_check_env_pma_26_mask', 'input', 48),
        ('io_check_env_pma_27_cfg_c', 'input', 1),
        ('io_check_env_pma_27_cfg_atomic', 'input', 1),
        ('io_check_env_pma_27_cfg_a', 'input', 2),
        ('io_check_env_pma_27_cfg_r', 'input', 1),
        ('io_check_env_pma_27_addr', 'input', 46),
        ('io_check_env_pma_27_mask', 'input', 48),
        ('io_check_env_pma_28_cfg_c', 'input', 1),
        ('io_check_env_pma_28_cfg_atomic', 'input', 1),
        ('io_check_env_pma_28_cfg_a', 'input', 2),
        ('io_check_env_pma_28_cfg_r', 'input', 1),
        ('io_check_env_pma_28_addr', 'input', 46),
        ('io_check_env_pma_28_mask', 'input', 48),
        ('io_check_env_pma_29_cfg_c', 'input', 1),
        ('io_check_env_pma_29_cfg_atomic', 'input', 1),
        ('io_check_env_pma_29_cfg_a', 'input', 2),
        ('io_check_env_pma_29_cfg_r', 'input', 1),
        ('io_check_env_pma_29_addr', 'input', 46),
        ('io_check_env_pma_29_mask', 'input', 48),
        ('io_check_env_pma_30_cfg_c', 'input', 1),
        ('io_check_env_pma_30_cfg_atomic', 'input', 1),
        ('io_check_env_pma_30_cfg_a', 'input', 2),
        ('io_check_env_pma_30_cfg_r', 'input', 1),
        ('io_check_env_pma_30_addr', 'input', 46),
        ('io_check_env_pma_30_mask', 'input', 48),
        ('io_check_env_pma_31_cfg_c', 'input', 1),
        ('io_check_env_pma_31_cfg_atomic', 'input', 1),
        ('io_check_env_pma_31_cfg_a', 'input', 2),
        ('io_check_env_pma_31_cfg_r', 'input', 1),
        ('io_check_env_pma_31_addr', 'input', 46),
        ('io_check_env_pma_31_mask', 'input', 48),
        ('io_req_bits_addr', 'input', 48),
        ('io_resp_ld', 'output', 1),
        ('io_resp_mmio', 'output', 1),
        ('io_resp_atomic', 'output', 1),
    ),
    'PMPChecker_12': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_check_env_mode', 'input', 2),
        ('io_check_env_debug', 'input', 1),
        ('io_check_env_pmp_0_cfg_l', 'input', 1),
        ('io_check_env_pmp_0_cfg_a', 'input', 2),
        ('io_check_env_pmp_0_cfg_x', 'input', 1),
        ('io_check_env_pmp_0_cfg_w', 'input', 1),
        ('io_check_env_pmp_0_cfg_r', 'input', 1),
        ('io_check_env_pmp_0_addr', 'input', 46),
        ('io_check_env_pmp_0_mask', 'input', 48),
        ('io_check_env_pmp_1_cfg_l', 'input', 1),
        ('io_check_env_pmp_1_cfg_a', 'input', 2),
        ('io_check_env_pmp_1_cfg_x', 'input', 1),
        ('io_check_env_pmp_1_cfg_w', 'input', 1),
        ('io_check_env_pmp_1_cfg_r', 'input', 1),
        ('io_check_env_pmp_1_addr', 'input', 46),
        ('io_check_env_pmp_1_mask', 'input', 48),
        ('io_check_env_pmp_2_cfg_l', 'input', 1),
        ('io_check_env_pmp_2_cfg_a', 'input', 2),
        ('io_check_env_pmp_2_cfg_x', 'input', 1),
        ('io_check_env_pmp_2_cfg_w', 'input', 1),
        ('io_check_env_pmp_2_cfg_r', 'input', 1),
        ('io_check_env_pmp_2_addr', 'input', 46),
        ('io_check_env_pmp_2_mask', 'input', 48),
        ('io_check_env_pmp_3_cfg_l', 'input', 1),
        ('io_check_env_pmp_3_cfg_a', 'input', 2),
        ('io_check_env_pmp_3_cfg_x', 'input', 1),
        ('io_check_env_pmp_3_cfg_w', 'input', 1),
        ('io_check_env_pmp_3_cfg_r', 'input', 1),
        ('io_check_env_pmp_3_addr', 'input', 46),
        ('io_check_env_pmp_3_mask', 'input', 48),
        ('io_check_env_pmp_4_cfg_l', 'input', 1),
        ('io_check_env_pmp_4_cfg_a', 'input', 2),
        ('io_check_env_pmp_4_cfg_x', 'input', 1),
        ('io_check_env_pmp_4_cfg_w', 'input', 1),
        ('io_check_env_pmp_4_cfg_r', 'input', 1),
        ('io_check_env_pmp_4_addr', 'input', 46),
        ('io_check_env_pmp_4_mask', 'input', 48),
        ('io_check_env_pmp_5_cfg_l', 'input', 1),
        ('io_check_env_pmp_5_cfg_a', 'input', 2),
        ('io_check_env_pmp_5_cfg_x', 'input', 1),
        ('io_check_env_pmp_5_cfg_w', 'input', 1),
        ('io_check_env_pmp_5_cfg_r', 'input', 1),
        ('io_check_env_pmp_5_addr', 'input', 46),
        ('io_check_env_pmp_5_mask', 'input', 48),
        ('io_check_env_pmp_6_cfg_l', 'input', 1),
        ('io_check_env_pmp_6_cfg_a', 'input', 2),
        ('io_check_env_pmp_6_cfg_x', 'input', 1),
        ('io_check_env_pmp_6_cfg_w', 'input', 1),
        ('io_check_env_pmp_6_cfg_r', 'input', 1),
        ('io_check_env_pmp_6_addr', 'input', 46),
        ('io_check_env_pmp_6_mask', 'input', 48),
        ('io_check_env_pmp_7_cfg_l', 'input', 1),
        ('io_check_env_pmp_7_cfg_a', 'input', 2),
        ('io_check_env_pmp_7_cfg_x', 'input', 1),
        ('io_check_env_pmp_7_cfg_w', 'input', 1),
        ('io_check_env_pmp_7_cfg_r', 'input', 1),
        ('io_check_env_pmp_7_addr', 'input', 46),
        ('io_check_env_pmp_7_mask', 'input', 48),
        ('io_check_env_pmp_8_cfg_l', 'input', 1),
        ('io_check_env_pmp_8_cfg_a', 'input', 2),
        ('io_check_env_pmp_8_cfg_x', 'input', 1),
        ('io_check_env_pmp_8_cfg_w', 'input', 1),
        ('io_check_env_pmp_8_cfg_r', 'input', 1),
        ('io_check_env_pmp_8_addr', 'input', 46),
        ('io_check_env_pmp_8_mask', 'input', 48),
        ('io_check_env_pmp_9_cfg_l', 'input', 1),
        ('io_check_env_pmp_9_cfg_a', 'input', 2),
        ('io_check_env_pmp_9_cfg_x', 'input', 1),
        ('io_check_env_pmp_9_cfg_w', 'input', 1),
        ('io_check_env_pmp_9_cfg_r', 'input', 1),
        ('io_check_env_pmp_9_addr', 'input', 46),
        ('io_check_env_pmp_9_mask', 'input', 48),
        ('io_check_env_pmp_10_cfg_l', 'input', 1),
        ('io_check_env_pmp_10_cfg_a', 'input', 2),
        ('io_check_env_pmp_10_cfg_x', 'input', 1),
        ('io_check_env_pmp_10_cfg_w', 'input', 1),
        ('io_check_env_pmp_10_cfg_r', 'input', 1),
        ('io_check_env_pmp_10_addr', 'input', 46),
        ('io_check_env_pmp_10_mask', 'input', 48),
        ('io_check_env_pmp_11_cfg_l', 'input', 1),
        ('io_check_env_pmp_11_cfg_a', 'input', 2),
        ('io_check_env_pmp_11_cfg_x', 'input', 1),
        ('io_check_env_pmp_11_cfg_w', 'input', 1),
        ('io_check_env_pmp_11_cfg_r', 'input', 1),
        ('io_check_env_pmp_11_addr', 'input', 46),
        ('io_check_env_pmp_11_mask', 'input', 48),
        ('io_check_env_pmp_12_cfg_l', 'input', 1),
        ('io_check_env_pmp_12_cfg_a', 'input', 2),
        ('io_check_env_pmp_12_cfg_x', 'input', 1),
        ('io_check_env_pmp_12_cfg_w', 'input', 1),
        ('io_check_env_pmp_12_cfg_r', 'input', 1),
        ('io_check_env_pmp_12_addr', 'input', 46),
        ('io_check_env_pmp_12_mask', 'input', 48),
        ('io_check_env_pmp_13_cfg_l', 'input', 1),
        ('io_check_env_pmp_13_cfg_a', 'input', 2),
        ('io_check_env_pmp_13_cfg_x', 'input', 1),
        ('io_check_env_pmp_13_cfg_w', 'input', 1),
        ('io_check_env_pmp_13_cfg_r', 'input', 1),
        ('io_check_env_pmp_13_addr', 'input', 46),
        ('io_check_env_pmp_13_mask', 'input', 48),
        ('io_check_env_pmp_14_cfg_l', 'input', 1),
        ('io_check_env_pmp_14_cfg_a', 'input', 2),
        ('io_check_env_pmp_14_cfg_x', 'input', 1),
        ('io_check_env_pmp_14_cfg_w', 'input', 1),
        ('io_check_env_pmp_14_cfg_r', 'input', 1),
        ('io_check_env_pmp_14_addr', 'input', 46),
        ('io_check_env_pmp_14_mask', 'input', 48),
        ('io_check_env_pmp_15_cfg_l', 'input', 1),
        ('io_check_env_pmp_15_cfg_a', 'input', 2),
        ('io_check_env_pmp_15_cfg_x', 'input', 1),
        ('io_check_env_pmp_15_cfg_w', 'input', 1),
        ('io_check_env_pmp_15_cfg_r', 'input', 1),
        ('io_check_env_pmp_15_addr', 'input', 46),
        ('io_check_env_pmp_15_mask', 'input', 48),
        ('io_check_env_pmp_16_cfg_l', 'input', 1),
        ('io_check_env_pmp_16_cfg_a', 'input', 2),
        ('io_check_env_pmp_16_cfg_x', 'input', 1),
        ('io_check_env_pmp_16_cfg_w', 'input', 1),
        ('io_check_env_pmp_16_cfg_r', 'input', 1),
        ('io_check_env_pmp_16_addr', 'input', 46),
        ('io_check_env_pmp_16_mask', 'input', 48),
        ('io_check_env_pmp_17_cfg_l', 'input', 1),
        ('io_check_env_pmp_17_cfg_a', 'input', 2),
        ('io_check_env_pmp_17_cfg_x', 'input', 1),
        ('io_check_env_pmp_17_cfg_w', 'input', 1),
        ('io_check_env_pmp_17_cfg_r', 'input', 1),
        ('io_check_env_pmp_17_addr', 'input', 46),
        ('io_check_env_pmp_17_mask', 'input', 48),
        ('io_check_env_pmp_18_cfg_l', 'input', 1),
        ('io_check_env_pmp_18_cfg_a', 'input', 2),
        ('io_check_env_pmp_18_cfg_x', 'input', 1),
        ('io_check_env_pmp_18_cfg_w', 'input', 1),
        ('io_check_env_pmp_18_cfg_r', 'input', 1),
        ('io_check_env_pmp_18_addr', 'input', 46),
        ('io_check_env_pmp_18_mask', 'input', 48),
        ('io_check_env_pmp_19_cfg_l', 'input', 1),
        ('io_check_env_pmp_19_cfg_a', 'input', 2),
        ('io_check_env_pmp_19_cfg_x', 'input', 1),
        ('io_check_env_pmp_19_cfg_w', 'input', 1),
        ('io_check_env_pmp_19_cfg_r', 'input', 1),
        ('io_check_env_pmp_19_addr', 'input', 46),
        ('io_check_env_pmp_19_mask', 'input', 48),
        ('io_check_env_pmp_20_cfg_l', 'input', 1),
        ('io_check_env_pmp_20_cfg_a', 'input', 2),
        ('io_check_env_pmp_20_cfg_x', 'input', 1),
        ('io_check_env_pmp_20_cfg_w', 'input', 1),
        ('io_check_env_pmp_20_cfg_r', 'input', 1),
        ('io_check_env_pmp_20_addr', 'input', 46),
        ('io_check_env_pmp_20_mask', 'input', 48),
        ('io_check_env_pmp_21_cfg_l', 'input', 1),
        ('io_check_env_pmp_21_cfg_a', 'input', 2),
        ('io_check_env_pmp_21_cfg_x', 'input', 1),
        ('io_check_env_pmp_21_cfg_w', 'input', 1),
        ('io_check_env_pmp_21_cfg_r', 'input', 1),
        ('io_check_env_pmp_21_addr', 'input', 46),
        ('io_check_env_pmp_21_mask', 'input', 48),
        ('io_check_env_pmp_22_cfg_l', 'input', 1),
        ('io_check_env_pmp_22_cfg_a', 'input', 2),
        ('io_check_env_pmp_22_cfg_x', 'input', 1),
        ('io_check_env_pmp_22_cfg_w', 'input', 1),
        ('io_check_env_pmp_22_cfg_r', 'input', 1),
        ('io_check_env_pmp_22_addr', 'input', 46),
        ('io_check_env_pmp_22_mask', 'input', 48),
        ('io_check_env_pmp_23_cfg_l', 'input', 1),
        ('io_check_env_pmp_23_cfg_a', 'input', 2),
        ('io_check_env_pmp_23_cfg_x', 'input', 1),
        ('io_check_env_pmp_23_cfg_w', 'input', 1),
        ('io_check_env_pmp_23_cfg_r', 'input', 1),
        ('io_check_env_pmp_23_addr', 'input', 46),
        ('io_check_env_pmp_23_mask', 'input', 48),
        ('io_check_env_pmp_24_cfg_l', 'input', 1),
        ('io_check_env_pmp_24_cfg_a', 'input', 2),
        ('io_check_env_pmp_24_cfg_x', 'input', 1),
        ('io_check_env_pmp_24_cfg_w', 'input', 1),
        ('io_check_env_pmp_24_cfg_r', 'input', 1),
        ('io_check_env_pmp_24_addr', 'input', 46),
        ('io_check_env_pmp_24_mask', 'input', 48),
        ('io_check_env_pmp_25_cfg_l', 'input', 1),
        ('io_check_env_pmp_25_cfg_a', 'input', 2),
        ('io_check_env_pmp_25_cfg_x', 'input', 1),
        ('io_check_env_pmp_25_cfg_w', 'input', 1),
        ('io_check_env_pmp_25_cfg_r', 'input', 1),
        ('io_check_env_pmp_25_addr', 'input', 46),
        ('io_check_env_pmp_25_mask', 'input', 48),
        ('io_check_env_pmp_26_cfg_l', 'input', 1),
        ('io_check_env_pmp_26_cfg_a', 'input', 2),
        ('io_check_env_pmp_26_cfg_x', 'input', 1),
        ('io_check_env_pmp_26_cfg_w', 'input', 1),
        ('io_check_env_pmp_26_cfg_r', 'input', 1),
        ('io_check_env_pmp_26_addr', 'input', 46),
        ('io_check_env_pmp_26_mask', 'input', 48),
        ('io_check_env_pmp_27_cfg_l', 'input', 1),
        ('io_check_env_pmp_27_cfg_a', 'input', 2),
        ('io_check_env_pmp_27_cfg_x', 'input', 1),
        ('io_check_env_pmp_27_cfg_w', 'input', 1),
        ('io_check_env_pmp_27_cfg_r', 'input', 1),
        ('io_check_env_pmp_27_addr', 'input', 46),
        ('io_check_env_pmp_27_mask', 'input', 48),
        ('io_check_env_pmp_28_cfg_l', 'input', 1),
        ('io_check_env_pmp_28_cfg_a', 'input', 2),
        ('io_check_env_pmp_28_cfg_x', 'input', 1),
        ('io_check_env_pmp_28_cfg_w', 'input', 1),
        ('io_check_env_pmp_28_cfg_r', 'input', 1),
        ('io_check_env_pmp_28_addr', 'input', 46),
        ('io_check_env_pmp_28_mask', 'input', 48),
        ('io_check_env_pmp_29_cfg_l', 'input', 1),
        ('io_check_env_pmp_29_cfg_a', 'input', 2),
        ('io_check_env_pmp_29_cfg_x', 'input', 1),
        ('io_check_env_pmp_29_cfg_w', 'input', 1),
        ('io_check_env_pmp_29_cfg_r', 'input', 1),
        ('io_check_env_pmp_29_addr', 'input', 46),
        ('io_check_env_pmp_29_mask', 'input', 48),
        ('io_check_env_pmp_30_cfg_l', 'input', 1),
        ('io_check_env_pmp_30_cfg_a', 'input', 2),
        ('io_check_env_pmp_30_cfg_x', 'input', 1),
        ('io_check_env_pmp_30_cfg_w', 'input', 1),
        ('io_check_env_pmp_30_cfg_r', 'input', 1),
        ('io_check_env_pmp_30_addr', 'input', 46),
        ('io_check_env_pmp_30_mask', 'input', 48),
        ('io_check_env_pmp_31_cfg_l', 'input', 1),
        ('io_check_env_pmp_31_cfg_a', 'input', 2),
        ('io_check_env_pmp_31_cfg_x', 'input', 1),
        ('io_check_env_pmp_31_cfg_w', 'input', 1),
        ('io_check_env_pmp_31_cfg_r', 'input', 1),
        ('io_check_env_pmp_31_addr', 'input', 46),
        ('io_check_env_pmp_31_mask', 'input', 48),
        ('io_check_env_pma_0_cfg_c', 'input', 1),
        ('io_check_env_pma_0_cfg_atomic', 'input', 1),
        ('io_check_env_pma_0_cfg_a', 'input', 2),
        ('io_check_env_pma_0_cfg_x', 'input', 1),
        ('io_check_env_pma_0_cfg_w', 'input', 1),
        ('io_check_env_pma_0_cfg_r', 'input', 1),
        ('io_check_env_pma_0_addr', 'input', 46),
        ('io_check_env_pma_0_mask', 'input', 48),
        ('io_check_env_pma_1_cfg_c', 'input', 1),
        ('io_check_env_pma_1_cfg_atomic', 'input', 1),
        ('io_check_env_pma_1_cfg_a', 'input', 2),
        ('io_check_env_pma_1_cfg_x', 'input', 1),
        ('io_check_env_pma_1_cfg_w', 'input', 1),
        ('io_check_env_pma_1_cfg_r', 'input', 1),
        ('io_check_env_pma_1_addr', 'input', 46),
        ('io_check_env_pma_1_mask', 'input', 48),
        ('io_check_env_pma_2_cfg_c', 'input', 1),
        ('io_check_env_pma_2_cfg_atomic', 'input', 1),
        ('io_check_env_pma_2_cfg_a', 'input', 2),
        ('io_check_env_pma_2_cfg_x', 'input', 1),
        ('io_check_env_pma_2_cfg_w', 'input', 1),
        ('io_check_env_pma_2_cfg_r', 'input', 1),
        ('io_check_env_pma_2_addr', 'input', 46),
        ('io_check_env_pma_2_mask', 'input', 48),
        ('io_check_env_pma_3_cfg_c', 'input', 1),
        ('io_check_env_pma_3_cfg_atomic', 'input', 1),
        ('io_check_env_pma_3_cfg_a', 'input', 2),
        ('io_check_env_pma_3_cfg_x', 'input', 1),
        ('io_check_env_pma_3_cfg_w', 'input', 1),
        ('io_check_env_pma_3_cfg_r', 'input', 1),
        ('io_check_env_pma_3_addr', 'input', 46),
        ('io_check_env_pma_3_mask', 'input', 48),
        ('io_check_env_pma_4_cfg_c', 'input', 1),
        ('io_check_env_pma_4_cfg_atomic', 'input', 1),
        ('io_check_env_pma_4_cfg_a', 'input', 2),
        ('io_check_env_pma_4_cfg_x', 'input', 1),
        ('io_check_env_pma_4_cfg_w', 'input', 1),
        ('io_check_env_pma_4_cfg_r', 'input', 1),
        ('io_check_env_pma_4_addr', 'input', 46),
        ('io_check_env_pma_4_mask', 'input', 48),
        ('io_check_env_pma_5_cfg_c', 'input', 1),
        ('io_check_env_pma_5_cfg_atomic', 'input', 1),
        ('io_check_env_pma_5_cfg_a', 'input', 2),
        ('io_check_env_pma_5_cfg_x', 'input', 1),
        ('io_check_env_pma_5_cfg_w', 'input', 1),
        ('io_check_env_pma_5_cfg_r', 'input', 1),
        ('io_check_env_pma_5_addr', 'input', 46),
        ('io_check_env_pma_5_mask', 'input', 48),
        ('io_check_env_pma_6_cfg_c', 'input', 1),
        ('io_check_env_pma_6_cfg_atomic', 'input', 1),
        ('io_check_env_pma_6_cfg_a', 'input', 2),
        ('io_check_env_pma_6_cfg_x', 'input', 1),
        ('io_check_env_pma_6_cfg_w', 'input', 1),
        ('io_check_env_pma_6_cfg_r', 'input', 1),
        ('io_check_env_pma_6_addr', 'input', 46),
        ('io_check_env_pma_6_mask', 'input', 48),
        ('io_check_env_pma_7_cfg_c', 'input', 1),
        ('io_check_env_pma_7_cfg_atomic', 'input', 1),
        ('io_check_env_pma_7_cfg_a', 'input', 2),
        ('io_check_env_pma_7_cfg_x', 'input', 1),
        ('io_check_env_pma_7_cfg_w', 'input', 1),
        ('io_check_env_pma_7_cfg_r', 'input', 1),
        ('io_check_env_pma_7_addr', 'input', 46),
        ('io_check_env_pma_7_mask', 'input', 48),
        ('io_check_env_pma_8_cfg_c', 'input', 1),
        ('io_check_env_pma_8_cfg_atomic', 'input', 1),
        ('io_check_env_pma_8_cfg_a', 'input', 2),
        ('io_check_env_pma_8_cfg_x', 'input', 1),
        ('io_check_env_pma_8_cfg_w', 'input', 1),
        ('io_check_env_pma_8_cfg_r', 'input', 1),
        ('io_check_env_pma_8_addr', 'input', 46),
        ('io_check_env_pma_8_mask', 'input', 48),
        ('io_check_env_pma_9_cfg_c', 'input', 1),
        ('io_check_env_pma_9_cfg_atomic', 'input', 1),
        ('io_check_env_pma_9_cfg_a', 'input', 2),
        ('io_check_env_pma_9_cfg_x', 'input', 1),
        ('io_check_env_pma_9_cfg_w', 'input', 1),
        ('io_check_env_pma_9_cfg_r', 'input', 1),
        ('io_check_env_pma_9_addr', 'input', 46),
        ('io_check_env_pma_9_mask', 'input', 48),
        ('io_check_env_pma_10_cfg_c', 'input', 1),
        ('io_check_env_pma_10_cfg_atomic', 'input', 1),
        ('io_check_env_pma_10_cfg_a', 'input', 2),
        ('io_check_env_pma_10_cfg_x', 'input', 1),
        ('io_check_env_pma_10_cfg_w', 'input', 1),
        ('io_check_env_pma_10_cfg_r', 'input', 1),
        ('io_check_env_pma_10_addr', 'input', 46),
        ('io_check_env_pma_10_mask', 'input', 48),
        ('io_check_env_pma_11_cfg_c', 'input', 1),
        ('io_check_env_pma_11_cfg_atomic', 'input', 1),
        ('io_check_env_pma_11_cfg_a', 'input', 2),
        ('io_check_env_pma_11_cfg_x', 'input', 1),
        ('io_check_env_pma_11_cfg_w', 'input', 1),
        ('io_check_env_pma_11_cfg_r', 'input', 1),
        ('io_check_env_pma_11_addr', 'input', 46),
        ('io_check_env_pma_11_mask', 'input', 48),
        ('io_check_env_pma_12_cfg_c', 'input', 1),
        ('io_check_env_pma_12_cfg_atomic', 'input', 1),
        ('io_check_env_pma_12_cfg_a', 'input', 2),
        ('io_check_env_pma_12_cfg_x', 'input', 1),
        ('io_check_env_pma_12_cfg_w', 'input', 1),
        ('io_check_env_pma_12_cfg_r', 'input', 1),
        ('io_check_env_pma_12_addr', 'input', 46),
        ('io_check_env_pma_12_mask', 'input', 48),
        ('io_check_env_pma_13_cfg_c', 'input', 1),
        ('io_check_env_pma_13_cfg_atomic', 'input', 1),
        ('io_check_env_pma_13_cfg_a', 'input', 2),
        ('io_check_env_pma_13_cfg_x', 'input', 1),
        ('io_check_env_pma_13_cfg_w', 'input', 1),
        ('io_check_env_pma_13_cfg_r', 'input', 1),
        ('io_check_env_pma_13_addr', 'input', 46),
        ('io_check_env_pma_13_mask', 'input', 48),
        ('io_check_env_pma_14_cfg_c', 'input', 1),
        ('io_check_env_pma_14_cfg_atomic', 'input', 1),
        ('io_check_env_pma_14_cfg_a', 'input', 2),
        ('io_check_env_pma_14_cfg_x', 'input', 1),
        ('io_check_env_pma_14_cfg_w', 'input', 1),
        ('io_check_env_pma_14_cfg_r', 'input', 1),
        ('io_check_env_pma_14_addr', 'input', 46),
        ('io_check_env_pma_14_mask', 'input', 48),
        ('io_check_env_pma_15_cfg_c', 'input', 1),
        ('io_check_env_pma_15_cfg_atomic', 'input', 1),
        ('io_check_env_pma_15_cfg_a', 'input', 2),
        ('io_check_env_pma_15_cfg_x', 'input', 1),
        ('io_check_env_pma_15_cfg_w', 'input', 1),
        ('io_check_env_pma_15_cfg_r', 'input', 1),
        ('io_check_env_pma_15_addr', 'input', 46),
        ('io_check_env_pma_15_mask', 'input', 48),
        ('io_check_env_pma_16_cfg_c', 'input', 1),
        ('io_check_env_pma_16_cfg_atomic', 'input', 1),
        ('io_check_env_pma_16_cfg_a', 'input', 2),
        ('io_check_env_pma_16_cfg_x', 'input', 1),
        ('io_check_env_pma_16_cfg_w', 'input', 1),
        ('io_check_env_pma_16_cfg_r', 'input', 1),
        ('io_check_env_pma_16_addr', 'input', 46),
        ('io_check_env_pma_16_mask', 'input', 48),
        ('io_check_env_pma_17_cfg_c', 'input', 1),
        ('io_check_env_pma_17_cfg_atomic', 'input', 1),
        ('io_check_env_pma_17_cfg_a', 'input', 2),
        ('io_check_env_pma_17_cfg_x', 'input', 1),
        ('io_check_env_pma_17_cfg_w', 'input', 1),
        ('io_check_env_pma_17_cfg_r', 'input', 1),
        ('io_check_env_pma_17_addr', 'input', 46),
        ('io_check_env_pma_17_mask', 'input', 48),
        ('io_check_env_pma_18_cfg_c', 'input', 1),
        ('io_check_env_pma_18_cfg_atomic', 'input', 1),
        ('io_check_env_pma_18_cfg_a', 'input', 2),
        ('io_check_env_pma_18_cfg_x', 'input', 1),
        ('io_check_env_pma_18_cfg_w', 'input', 1),
        ('io_check_env_pma_18_cfg_r', 'input', 1),
        ('io_check_env_pma_18_addr', 'input', 46),
        ('io_check_env_pma_18_mask', 'input', 48),
        ('io_check_env_pma_19_cfg_c', 'input', 1),
        ('io_check_env_pma_19_cfg_atomic', 'input', 1),
        ('io_check_env_pma_19_cfg_a', 'input', 2),
        ('io_check_env_pma_19_cfg_x', 'input', 1),
        ('io_check_env_pma_19_cfg_w', 'input', 1),
        ('io_check_env_pma_19_cfg_r', 'input', 1),
        ('io_check_env_pma_19_addr', 'input', 46),
        ('io_check_env_pma_19_mask', 'input', 48),
        ('io_check_env_pma_20_cfg_c', 'input', 1),
        ('io_check_env_pma_20_cfg_atomic', 'input', 1),
        ('io_check_env_pma_20_cfg_a', 'input', 2),
        ('io_check_env_pma_20_cfg_x', 'input', 1),
        ('io_check_env_pma_20_cfg_w', 'input', 1),
        ('io_check_env_pma_20_cfg_r', 'input', 1),
        ('io_check_env_pma_20_addr', 'input', 46),
        ('io_check_env_pma_20_mask', 'input', 48),
        ('io_check_env_pma_21_cfg_c', 'input', 1),
        ('io_check_env_pma_21_cfg_atomic', 'input', 1),
        ('io_check_env_pma_21_cfg_a', 'input', 2),
        ('io_check_env_pma_21_cfg_x', 'input', 1),
        ('io_check_env_pma_21_cfg_w', 'input', 1),
        ('io_check_env_pma_21_cfg_r', 'input', 1),
        ('io_check_env_pma_21_addr', 'input', 46),
        ('io_check_env_pma_21_mask', 'input', 48),
        ('io_check_env_pma_22_cfg_c', 'input', 1),
        ('io_check_env_pma_22_cfg_atomic', 'input', 1),
        ('io_check_env_pma_22_cfg_a', 'input', 2),
        ('io_check_env_pma_22_cfg_x', 'input', 1),
        ('io_check_env_pma_22_cfg_w', 'input', 1),
        ('io_check_env_pma_22_cfg_r', 'input', 1),
        ('io_check_env_pma_22_addr', 'input', 46),
        ('io_check_env_pma_22_mask', 'input', 48),
        ('io_check_env_pma_23_cfg_c', 'input', 1),
        ('io_check_env_pma_23_cfg_atomic', 'input', 1),
        ('io_check_env_pma_23_cfg_a', 'input', 2),
        ('io_check_env_pma_23_cfg_x', 'input', 1),
        ('io_check_env_pma_23_cfg_w', 'input', 1),
        ('io_check_env_pma_23_cfg_r', 'input', 1),
        ('io_check_env_pma_23_addr', 'input', 46),
        ('io_check_env_pma_23_mask', 'input', 48),
        ('io_check_env_pma_24_cfg_c', 'input', 1),
        ('io_check_env_pma_24_cfg_atomic', 'input', 1),
        ('io_check_env_pma_24_cfg_a', 'input', 2),
        ('io_check_env_pma_24_cfg_x', 'input', 1),
        ('io_check_env_pma_24_cfg_w', 'input', 1),
        ('io_check_env_pma_24_cfg_r', 'input', 1),
        ('io_check_env_pma_24_addr', 'input', 46),
        ('io_check_env_pma_24_mask', 'input', 48),
        ('io_check_env_pma_25_cfg_c', 'input', 1),
        ('io_check_env_pma_25_cfg_atomic', 'input', 1),
        ('io_check_env_pma_25_cfg_a', 'input', 2),
        ('io_check_env_pma_25_cfg_x', 'input', 1),
        ('io_check_env_pma_25_cfg_w', 'input', 1),
        ('io_check_env_pma_25_cfg_r', 'input', 1),
        ('io_check_env_pma_25_addr', 'input', 46),
        ('io_check_env_pma_25_mask', 'input', 48),
        ('io_check_env_pma_26_cfg_c', 'input', 1),
        ('io_check_env_pma_26_cfg_atomic', 'input', 1),
        ('io_check_env_pma_26_cfg_a', 'input', 2),
        ('io_check_env_pma_26_cfg_x', 'input', 1),
        ('io_check_env_pma_26_cfg_w', 'input', 1),
        ('io_check_env_pma_26_cfg_r', 'input', 1),
        ('io_check_env_pma_26_addr', 'input', 46),
        ('io_check_env_pma_26_mask', 'input', 48),
        ('io_check_env_pma_27_cfg_c', 'input', 1),
        ('io_check_env_pma_27_cfg_atomic', 'input', 1),
        ('io_check_env_pma_27_cfg_a', 'input', 2),
        ('io_check_env_pma_27_cfg_x', 'input', 1),
        ('io_check_env_pma_27_cfg_w', 'input', 1),
        ('io_check_env_pma_27_cfg_r', 'input', 1),
        ('io_check_env_pma_27_addr', 'input', 46),
        ('io_check_env_pma_27_mask', 'input', 48),
        ('io_check_env_pma_28_cfg_c', 'input', 1),
        ('io_check_env_pma_28_cfg_atomic', 'input', 1),
        ('io_check_env_pma_28_cfg_a', 'input', 2),
        ('io_check_env_pma_28_cfg_x', 'input', 1),
        ('io_check_env_pma_28_cfg_w', 'input', 1),
        ('io_check_env_pma_28_cfg_r', 'input', 1),
        ('io_check_env_pma_28_addr', 'input', 46),
        ('io_check_env_pma_28_mask', 'input', 48),
        ('io_check_env_pma_29_cfg_c', 'input', 1),
        ('io_check_env_pma_29_cfg_atomic', 'input', 1),
        ('io_check_env_pma_29_cfg_a', 'input', 2),
        ('io_check_env_pma_29_cfg_x', 'input', 1),
        ('io_check_env_pma_29_cfg_w', 'input', 1),
        ('io_check_env_pma_29_cfg_r', 'input', 1),
        ('io_check_env_pma_29_addr', 'input', 46),
        ('io_check_env_pma_29_mask', 'input', 48),
        ('io_check_env_pma_30_cfg_c', 'input', 1),
        ('io_check_env_pma_30_cfg_atomic', 'input', 1),
        ('io_check_env_pma_30_cfg_a', 'input', 2),
        ('io_check_env_pma_30_cfg_x', 'input', 1),
        ('io_check_env_pma_30_cfg_w', 'input', 1),
        ('io_check_env_pma_30_cfg_r', 'input', 1),
        ('io_check_env_pma_30_addr', 'input', 46),
        ('io_check_env_pma_30_mask', 'input', 48),
        ('io_check_env_pma_31_cfg_c', 'input', 1),
        ('io_check_env_pma_31_cfg_atomic', 'input', 1),
        ('io_check_env_pma_31_cfg_a', 'input', 2),
        ('io_check_env_pma_31_cfg_x', 'input', 1),
        ('io_check_env_pma_31_cfg_w', 'input', 1),
        ('io_check_env_pma_31_cfg_r', 'input', 1),
        ('io_check_env_pma_31_addr', 'input', 46),
        ('io_check_env_pma_31_mask', 'input', 48),
        ('io_req_valid', 'input', 1),
        ('io_req_bits_addr', 'input', 48),
        ('io_req_bits_cmd', 'input', 3),
        ('io_resp_ld', 'output', 1),
        ('io_resp_st', 'output', 1),
        ('io_resp_instr', 'output', 1),
        ('io_resp_mmio', 'output', 1),
        ('io_resp_atomic', 'output', 1),
    ),
    'PMPChecker_2': (
        ('clock', 'input', 1),
        ('io_check_env_mode', 'input', 2),
        ('io_check_env_debug', 'input', 1),
        ('io_check_env_pmp_0_cfg_l', 'input', 1),
        ('io_check_env_pmp_0_cfg_a', 'input', 2),
        ('io_check_env_pmp_0_cfg_x', 'input', 1),
        ('io_check_env_pmp_0_addr', 'input', 46),
        ('io_check_env_pmp_0_mask', 'input', 48),
        ('io_check_env_pmp_1_cfg_l', 'input', 1),
        ('io_check_env_pmp_1_cfg_a', 'input', 2),
        ('io_check_env_pmp_1_cfg_x', 'input', 1),
        ('io_check_env_pmp_1_addr', 'input', 46),
        ('io_check_env_pmp_1_mask', 'input', 48),
        ('io_check_env_pmp_2_cfg_l', 'input', 1),
        ('io_check_env_pmp_2_cfg_a', 'input', 2),
        ('io_check_env_pmp_2_cfg_x', 'input', 1),
        ('io_check_env_pmp_2_addr', 'input', 46),
        ('io_check_env_pmp_2_mask', 'input', 48),
        ('io_check_env_pmp_3_cfg_l', 'input', 1),
        ('io_check_env_pmp_3_cfg_a', 'input', 2),
        ('io_check_env_pmp_3_cfg_x', 'input', 1),
        ('io_check_env_pmp_3_addr', 'input', 46),
        ('io_check_env_pmp_3_mask', 'input', 48),
        ('io_check_env_pmp_4_cfg_l', 'input', 1),
        ('io_check_env_pmp_4_cfg_a', 'input', 2),
        ('io_check_env_pmp_4_cfg_x', 'input', 1),
        ('io_check_env_pmp_4_addr', 'input', 46),
        ('io_check_env_pmp_4_mask', 'input', 48),
        ('io_check_env_pmp_5_cfg_l', 'input', 1),
        ('io_check_env_pmp_5_cfg_a', 'input', 2),
        ('io_check_env_pmp_5_cfg_x', 'input', 1),
        ('io_check_env_pmp_5_addr', 'input', 46),
        ('io_check_env_pmp_5_mask', 'input', 48),
        ('io_check_env_pmp_6_cfg_l', 'input', 1),
        ('io_check_env_pmp_6_cfg_a', 'input', 2),
        ('io_check_env_pmp_6_cfg_x', 'input', 1),
        ('io_check_env_pmp_6_addr', 'input', 46),
        ('io_check_env_pmp_6_mask', 'input', 48),
        ('io_check_env_pmp_7_cfg_l', 'input', 1),
        ('io_check_env_pmp_7_cfg_a', 'input', 2),
        ('io_check_env_pmp_7_cfg_x', 'input', 1),
        ('io_check_env_pmp_7_addr', 'input', 46),
        ('io_check_env_pmp_7_mask', 'input', 48),
        ('io_check_env_pmp_8_cfg_l', 'input', 1),
        ('io_check_env_pmp_8_cfg_a', 'input', 2),
        ('io_check_env_pmp_8_cfg_x', 'input', 1),
        ('io_check_env_pmp_8_addr', 'input', 46),
        ('io_check_env_pmp_8_mask', 'input', 48),
        ('io_check_env_pmp_9_cfg_l', 'input', 1),
        ('io_check_env_pmp_9_cfg_a', 'input', 2),
        ('io_check_env_pmp_9_cfg_x', 'input', 1),
        ('io_check_env_pmp_9_addr', 'input', 46),
        ('io_check_env_pmp_9_mask', 'input', 48),
        ('io_check_env_pmp_10_cfg_l', 'input', 1),
        ('io_check_env_pmp_10_cfg_a', 'input', 2),
        ('io_check_env_pmp_10_cfg_x', 'input', 1),
        ('io_check_env_pmp_10_addr', 'input', 46),
        ('io_check_env_pmp_10_mask', 'input', 48),
        ('io_check_env_pmp_11_cfg_l', 'input', 1),
        ('io_check_env_pmp_11_cfg_a', 'input', 2),
        ('io_check_env_pmp_11_cfg_x', 'input', 1),
        ('io_check_env_pmp_11_addr', 'input', 46),
        ('io_check_env_pmp_11_mask', 'input', 48),
        ('io_check_env_pmp_12_cfg_l', 'input', 1),
        ('io_check_env_pmp_12_cfg_a', 'input', 2),
        ('io_check_env_pmp_12_cfg_x', 'input', 1),
        ('io_check_env_pmp_12_addr', 'input', 46),
        ('io_check_env_pmp_12_mask', 'input', 48),
        ('io_check_env_pmp_13_cfg_l', 'input', 1),
        ('io_check_env_pmp_13_cfg_a', 'input', 2),
        ('io_check_env_pmp_13_cfg_x', 'input', 1),
        ('io_check_env_pmp_13_addr', 'input', 46),
        ('io_check_env_pmp_13_mask', 'input', 48),
        ('io_check_env_pmp_14_cfg_l', 'input', 1),
        ('io_check_env_pmp_14_cfg_a', 'input', 2),
        ('io_check_env_pmp_14_cfg_x', 'input', 1),
        ('io_check_env_pmp_14_addr', 'input', 46),
        ('io_check_env_pmp_14_mask', 'input', 48),
        ('io_check_env_pmp_15_cfg_l', 'input', 1),
        ('io_check_env_pmp_15_cfg_a', 'input', 2),
        ('io_check_env_pmp_15_cfg_x', 'input', 1),
        ('io_check_env_pmp_15_addr', 'input', 46),
        ('io_check_env_pmp_15_mask', 'input', 48),
        ('io_check_env_pmp_16_cfg_l', 'input', 1),
        ('io_check_env_pmp_16_cfg_a', 'input', 2),
        ('io_check_env_pmp_16_cfg_x', 'input', 1),
        ('io_check_env_pmp_16_addr', 'input', 46),
        ('io_check_env_pmp_16_mask', 'input', 48),
        ('io_check_env_pmp_17_cfg_l', 'input', 1),
        ('io_check_env_pmp_17_cfg_a', 'input', 2),
        ('io_check_env_pmp_17_cfg_x', 'input', 1),
        ('io_check_env_pmp_17_addr', 'input', 46),
        ('io_check_env_pmp_17_mask', 'input', 48),
        ('io_check_env_pmp_18_cfg_l', 'input', 1),
        ('io_check_env_pmp_18_cfg_a', 'input', 2),
        ('io_check_env_pmp_18_cfg_x', 'input', 1),
        ('io_check_env_pmp_18_addr', 'input', 46),
        ('io_check_env_pmp_18_mask', 'input', 48),
        ('io_check_env_pmp_19_cfg_l', 'input', 1),
        ('io_check_env_pmp_19_cfg_a', 'input', 2),
        ('io_check_env_pmp_19_cfg_x', 'input', 1),
        ('io_check_env_pmp_19_addr', 'input', 46),
        ('io_check_env_pmp_19_mask', 'input', 48),
        ('io_check_env_pmp_20_cfg_l', 'input', 1),
        ('io_check_env_pmp_20_cfg_a', 'input', 2),
        ('io_check_env_pmp_20_cfg_x', 'input', 1),
        ('io_check_env_pmp_20_addr', 'input', 46),
        ('io_check_env_pmp_20_mask', 'input', 48),
        ('io_check_env_pmp_21_cfg_l', 'input', 1),
        ('io_check_env_pmp_21_cfg_a', 'input', 2),
        ('io_check_env_pmp_21_cfg_x', 'input', 1),
        ('io_check_env_pmp_21_addr', 'input', 46),
        ('io_check_env_pmp_21_mask', 'input', 48),
        ('io_check_env_pmp_22_cfg_l', 'input', 1),
        ('io_check_env_pmp_22_cfg_a', 'input', 2),
        ('io_check_env_pmp_22_cfg_x', 'input', 1),
        ('io_check_env_pmp_22_addr', 'input', 46),
        ('io_check_env_pmp_22_mask', 'input', 48),
        ('io_check_env_pmp_23_cfg_l', 'input', 1),
        ('io_check_env_pmp_23_cfg_a', 'input', 2),
        ('io_check_env_pmp_23_cfg_x', 'input', 1),
        ('io_check_env_pmp_23_addr', 'input', 46),
        ('io_check_env_pmp_23_mask', 'input', 48),
        ('io_check_env_pmp_24_cfg_l', 'input', 1),
        ('io_check_env_pmp_24_cfg_a', 'input', 2),
        ('io_check_env_pmp_24_cfg_x', 'input', 1),
        ('io_check_env_pmp_24_addr', 'input', 46),
        ('io_check_env_pmp_24_mask', 'input', 48),
        ('io_check_env_pmp_25_cfg_l', 'input', 1),
        ('io_check_env_pmp_25_cfg_a', 'input', 2),
        ('io_check_env_pmp_25_cfg_x', 'input', 1),
        ('io_check_env_pmp_25_addr', 'input', 46),
        ('io_check_env_pmp_25_mask', 'input', 48),
        ('io_check_env_pmp_26_cfg_l', 'input', 1),
        ('io_check_env_pmp_26_cfg_a', 'input', 2),
        ('io_check_env_pmp_26_cfg_x', 'input', 1),
        ('io_check_env_pmp_26_addr', 'input', 46),
        ('io_check_env_pmp_26_mask', 'input', 48),
        ('io_check_env_pmp_27_cfg_l', 'input', 1),
        ('io_check_env_pmp_27_cfg_a', 'input', 2),
        ('io_check_env_pmp_27_cfg_x', 'input', 1),
        ('io_check_env_pmp_27_addr', 'input', 46),
        ('io_check_env_pmp_27_mask', 'input', 48),
        ('io_check_env_pmp_28_cfg_l', 'input', 1),
        ('io_check_env_pmp_28_cfg_a', 'input', 2),
        ('io_check_env_pmp_28_cfg_x', 'input', 1),
        ('io_check_env_pmp_28_addr', 'input', 46),
        ('io_check_env_pmp_28_mask', 'input', 48),
        ('io_check_env_pmp_29_cfg_l', 'input', 1),
        ('io_check_env_pmp_29_cfg_a', 'input', 2),
        ('io_check_env_pmp_29_cfg_x', 'input', 1),
        ('io_check_env_pmp_29_addr', 'input', 46),
        ('io_check_env_pmp_29_mask', 'input', 48),
        ('io_check_env_pmp_30_cfg_l', 'input', 1),
        ('io_check_env_pmp_30_cfg_a', 'input', 2),
        ('io_check_env_pmp_30_cfg_x', 'input', 1),
        ('io_check_env_pmp_30_addr', 'input', 46),
        ('io_check_env_pmp_30_mask', 'input', 48),
        ('io_check_env_pmp_31_cfg_l', 'input', 1),
        ('io_check_env_pmp_31_cfg_a', 'input', 2),
        ('io_check_env_pmp_31_cfg_x', 'input', 1),
        ('io_check_env_pmp_31_addr', 'input', 46),
        ('io_check_env_pmp_31_mask', 'input', 48),
        ('io_check_env_pma_0_cfg_c', 'input', 1),
        ('io_check_env_pma_0_cfg_a', 'input', 2),
        ('io_check_env_pma_0_cfg_x', 'input', 1),
        ('io_check_env_pma_0_addr', 'input', 46),
        ('io_check_env_pma_0_mask', 'input', 48),
        ('io_check_env_pma_1_cfg_c', 'input', 1),
        ('io_check_env_pma_1_cfg_a', 'input', 2),
        ('io_check_env_pma_1_cfg_x', 'input', 1),
        ('io_check_env_pma_1_addr', 'input', 46),
        ('io_check_env_pma_1_mask', 'input', 48),
        ('io_check_env_pma_2_cfg_c', 'input', 1),
        ('io_check_env_pma_2_cfg_a', 'input', 2),
        ('io_check_env_pma_2_cfg_x', 'input', 1),
        ('io_check_env_pma_2_addr', 'input', 46),
        ('io_check_env_pma_2_mask', 'input', 48),
        ('io_check_env_pma_3_cfg_c', 'input', 1),
        ('io_check_env_pma_3_cfg_a', 'input', 2),
        ('io_check_env_pma_3_cfg_x', 'input', 1),
        ('io_check_env_pma_3_addr', 'input', 46),
        ('io_check_env_pma_3_mask', 'input', 48),
        ('io_check_env_pma_4_cfg_c', 'input', 1),
        ('io_check_env_pma_4_cfg_a', 'input', 2),
        ('io_check_env_pma_4_cfg_x', 'input', 1),
        ('io_check_env_pma_4_addr', 'input', 46),
        ('io_check_env_pma_4_mask', 'input', 48),
        ('io_check_env_pma_5_cfg_c', 'input', 1),
        ('io_check_env_pma_5_cfg_a', 'input', 2),
        ('io_check_env_pma_5_cfg_x', 'input', 1),
        ('io_check_env_pma_5_addr', 'input', 46),
        ('io_check_env_pma_5_mask', 'input', 48),
        ('io_check_env_pma_6_cfg_c', 'input', 1),
        ('io_check_env_pma_6_cfg_a', 'input', 2),
        ('io_check_env_pma_6_cfg_x', 'input', 1),
        ('io_check_env_pma_6_addr', 'input', 46),
        ('io_check_env_pma_6_mask', 'input', 48),
        ('io_check_env_pma_7_cfg_c', 'input', 1),
        ('io_check_env_pma_7_cfg_a', 'input', 2),
        ('io_check_env_pma_7_cfg_x', 'input', 1),
        ('io_check_env_pma_7_addr', 'input', 46),
        ('io_check_env_pma_7_mask', 'input', 48),
        ('io_check_env_pma_8_cfg_c', 'input', 1),
        ('io_check_env_pma_8_cfg_a', 'input', 2),
        ('io_check_env_pma_8_cfg_x', 'input', 1),
        ('io_check_env_pma_8_addr', 'input', 46),
        ('io_check_env_pma_8_mask', 'input', 48),
        ('io_check_env_pma_9_cfg_c', 'input', 1),
        ('io_check_env_pma_9_cfg_a', 'input', 2),
        ('io_check_env_pma_9_cfg_x', 'input', 1),
        ('io_check_env_pma_9_addr', 'input', 46),
        ('io_check_env_pma_9_mask', 'input', 48),
        ('io_check_env_pma_10_cfg_c', 'input', 1),
        ('io_check_env_pma_10_cfg_a', 'input', 2),
        ('io_check_env_pma_10_cfg_x', 'input', 1),
        ('io_check_env_pma_10_addr', 'input', 46),
        ('io_check_env_pma_10_mask', 'input', 48),
        ('io_check_env_pma_11_cfg_c', 'input', 1),
        ('io_check_env_pma_11_cfg_a', 'input', 2),
        ('io_check_env_pma_11_cfg_x', 'input', 1),
        ('io_check_env_pma_11_addr', 'input', 46),
        ('io_check_env_pma_11_mask', 'input', 48),
        ('io_check_env_pma_12_cfg_c', 'input', 1),
        ('io_check_env_pma_12_cfg_a', 'input', 2),
        ('io_check_env_pma_12_cfg_x', 'input', 1),
        ('io_check_env_pma_12_addr', 'input', 46),
        ('io_check_env_pma_12_mask', 'input', 48),
        ('io_check_env_pma_13_cfg_c', 'input', 1),
        ('io_check_env_pma_13_cfg_a', 'input', 2),
        ('io_check_env_pma_13_cfg_x', 'input', 1),
        ('io_check_env_pma_13_addr', 'input', 46),
        ('io_check_env_pma_13_mask', 'input', 48),
        ('io_check_env_pma_14_cfg_c', 'input', 1),
        ('io_check_env_pma_14_cfg_a', 'input', 2),
        ('io_check_env_pma_14_cfg_x', 'input', 1),
        ('io_check_env_pma_14_addr', 'input', 46),
        ('io_check_env_pma_14_mask', 'input', 48),
        ('io_check_env_pma_15_cfg_c', 'input', 1),
        ('io_check_env_pma_15_cfg_a', 'input', 2),
        ('io_check_env_pma_15_cfg_x', 'input', 1),
        ('io_check_env_pma_15_addr', 'input', 46),
        ('io_check_env_pma_15_mask', 'input', 48),
        ('io_check_env_pma_16_cfg_c', 'input', 1),
        ('io_check_env_pma_16_cfg_a', 'input', 2),
        ('io_check_env_pma_16_cfg_x', 'input', 1),
        ('io_check_env_pma_16_addr', 'input', 46),
        ('io_check_env_pma_16_mask', 'input', 48),
        ('io_check_env_pma_17_cfg_c', 'input', 1),
        ('io_check_env_pma_17_cfg_a', 'input', 2),
        ('io_check_env_pma_17_cfg_x', 'input', 1),
        ('io_check_env_pma_17_addr', 'input', 46),
        ('io_check_env_pma_17_mask', 'input', 48),
        ('io_check_env_pma_18_cfg_c', 'input', 1),
        ('io_check_env_pma_18_cfg_a', 'input', 2),
        ('io_check_env_pma_18_cfg_x', 'input', 1),
        ('io_check_env_pma_18_addr', 'input', 46),
        ('io_check_env_pma_18_mask', 'input', 48),
        ('io_check_env_pma_19_cfg_c', 'input', 1),
        ('io_check_env_pma_19_cfg_a', 'input', 2),
        ('io_check_env_pma_19_cfg_x', 'input', 1),
        ('io_check_env_pma_19_addr', 'input', 46),
        ('io_check_env_pma_19_mask', 'input', 48),
        ('io_check_env_pma_20_cfg_c', 'input', 1),
        ('io_check_env_pma_20_cfg_a', 'input', 2),
        ('io_check_env_pma_20_cfg_x', 'input', 1),
        ('io_check_env_pma_20_addr', 'input', 46),
        ('io_check_env_pma_20_mask', 'input', 48),
        ('io_check_env_pma_21_cfg_c', 'input', 1),
        ('io_check_env_pma_21_cfg_a', 'input', 2),
        ('io_check_env_pma_21_cfg_x', 'input', 1),
        ('io_check_env_pma_21_addr', 'input', 46),
        ('io_check_env_pma_21_mask', 'input', 48),
        ('io_check_env_pma_22_cfg_c', 'input', 1),
        ('io_check_env_pma_22_cfg_a', 'input', 2),
        ('io_check_env_pma_22_cfg_x', 'input', 1),
        ('io_check_env_pma_22_addr', 'input', 46),
        ('io_check_env_pma_22_mask', 'input', 48),
        ('io_check_env_pma_23_cfg_c', 'input', 1),
        ('io_check_env_pma_23_cfg_a', 'input', 2),
        ('io_check_env_pma_23_cfg_x', 'input', 1),
        ('io_check_env_pma_23_addr', 'input', 46),
        ('io_check_env_pma_23_mask', 'input', 48),
        ('io_check_env_pma_24_cfg_c', 'input', 1),
        ('io_check_env_pma_24_cfg_a', 'input', 2),
        ('io_check_env_pma_24_cfg_x', 'input', 1),
        ('io_check_env_pma_24_addr', 'input', 46),
        ('io_check_env_pma_24_mask', 'input', 48),
        ('io_check_env_pma_25_cfg_c', 'input', 1),
        ('io_check_env_pma_25_cfg_a', 'input', 2),
        ('io_check_env_pma_25_cfg_x', 'input', 1),
        ('io_check_env_pma_25_addr', 'input', 46),
        ('io_check_env_pma_25_mask', 'input', 48),
        ('io_check_env_pma_26_cfg_c', 'input', 1),
        ('io_check_env_pma_26_cfg_a', 'input', 2),
        ('io_check_env_pma_26_cfg_x', 'input', 1),
        ('io_check_env_pma_26_addr', 'input', 46),
        ('io_check_env_pma_26_mask', 'input', 48),
        ('io_check_env_pma_27_cfg_c', 'input', 1),
        ('io_check_env_pma_27_cfg_a', 'input', 2),
        ('io_check_env_pma_27_cfg_x', 'input', 1),
        ('io_check_env_pma_27_addr', 'input', 46),
        ('io_check_env_pma_27_mask', 'input', 48),
        ('io_check_env_pma_28_cfg_c', 'input', 1),
        ('io_check_env_pma_28_cfg_a', 'input', 2),
        ('io_check_env_pma_28_cfg_x', 'input', 1),
        ('io_check_env_pma_28_addr', 'input', 46),
        ('io_check_env_pma_28_mask', 'input', 48),
        ('io_check_env_pma_29_cfg_c', 'input', 1),
        ('io_check_env_pma_29_cfg_a', 'input', 2),
        ('io_check_env_pma_29_cfg_x', 'input', 1),
        ('io_check_env_pma_29_addr', 'input', 46),
        ('io_check_env_pma_29_mask', 'input', 48),
        ('io_check_env_pma_30_cfg_c', 'input', 1),
        ('io_check_env_pma_30_cfg_a', 'input', 2),
        ('io_check_env_pma_30_cfg_x', 'input', 1),
        ('io_check_env_pma_30_addr', 'input', 46),
        ('io_check_env_pma_30_mask', 'input', 48),
        ('io_check_env_pma_31_cfg_c', 'input', 1),
        ('io_check_env_pma_31_cfg_a', 'input', 2),
        ('io_check_env_pma_31_cfg_x', 'input', 1),
        ('io_check_env_pma_31_addr', 'input', 46),
        ('io_check_env_pma_31_mask', 'input', 48),
        ('io_req_valid', 'input', 1),
        ('io_req_bits_addr', 'input', 48),
        ('io_resp_instr', 'output', 1),
        ('io_resp_mmio', 'output', 1),
    ),
    'PMPEntryHandleModule': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_in_wen', 'input', 1),
        ('io_in_ren', 'input', 1),
        ('io_in_addr', 'input', 12),
        ('io_in_wdata', 'input', 64),
        ('io_in_pmpCfg_0_R', 'input', 1),
        ('io_in_pmpCfg_0_W', 'input', 1),
        ('io_in_pmpCfg_0_X', 'input', 1),
        ('io_in_pmpCfg_0_A', 'input', 2),
        ('io_in_pmpCfg_0_L', 'input', 1),
        ('io_in_pmpCfg_1_R', 'input', 1),
        ('io_in_pmpCfg_1_W', 'input', 1),
        ('io_in_pmpCfg_1_X', 'input', 1),
        ('io_in_pmpCfg_1_A', 'input', 2),
        ('io_in_pmpCfg_1_L', 'input', 1),
        ('io_in_pmpCfg_2_R', 'input', 1),
        ('io_in_pmpCfg_2_W', 'input', 1),
        ('io_in_pmpCfg_2_X', 'input', 1),
        ('io_in_pmpCfg_2_A', 'input', 2),
        ('io_in_pmpCfg_2_L', 'input', 1),
        ('io_in_pmpCfg_3_R', 'input', 1),
        ('io_in_pmpCfg_3_W', 'input', 1),
        ('io_in_pmpCfg_3_X', 'input', 1),
        ('io_in_pmpCfg_3_A', 'input', 2),
        ('io_in_pmpCfg_3_L', 'input', 1),
        ('io_in_pmpCfg_4_R', 'input', 1),
        ('io_in_pmpCfg_4_W', 'input', 1),
        ('io_in_pmpCfg_4_X', 'input', 1),
        ('io_in_pmpCfg_4_A', 'input', 2),
        ('io_in_pmpCfg_4_L', 'input', 1),
        ('io_in_pmpCfg_5_R', 'input', 1),
        ('io_in_pmpCfg_5_W', 'input', 1),
        ('io_in_pmpCfg_5_X', 'input', 1),
        ('io_in_pmpCfg_5_A', 'input', 2),
        ('io_in_pmpCfg_5_L', 'input', 1),
        ('io_in_pmpCfg_6_R', 'input', 1),
        ('io_in_pmpCfg_6_W', 'input', 1),
        ('io_in_pmpCfg_6_X', 'input', 1),
        ('io_in_pmpCfg_6_A', 'input', 2),
        ('io_in_pmpCfg_6_L', 'input', 1),
        ('io_in_pmpCfg_7_R', 'input', 1),
        ('io_in_pmpCfg_7_W', 'input', 1),
        ('io_in_pmpCfg_7_X', 'input', 1),
        ('io_in_pmpCfg_7_A', 'input', 2),
        ('io_in_pmpCfg_7_L', 'input', 1),
        ('io_in_pmpCfg_8_R', 'input', 1),
        ('io_in_pmpCfg_8_W', 'input', 1),
        ('io_in_pmpCfg_8_X', 'input', 1),
        ('io_in_pmpCfg_8_A', 'input', 2),
        ('io_in_pmpCfg_8_L', 'input', 1),
        ('io_in_pmpCfg_9_R', 'input', 1),
        ('io_in_pmpCfg_9_W', 'input', 1),
        ('io_in_pmpCfg_9_X', 'input', 1),
        ('io_in_pmpCfg_9_A', 'input', 2),
        ('io_in_pmpCfg_9_L', 'input', 1),
        ('io_in_pmpCfg_10_R', 'input', 1),
        ('io_in_pmpCfg_10_W', 'input', 1),
        ('io_in_pmpCfg_10_X', 'input', 1),
        ('io_in_pmpCfg_10_A', 'input', 2),
        ('io_in_pmpCfg_10_L', 'input', 1),
        ('io_in_pmpCfg_11_R', 'input', 1),
        ('io_in_pmpCfg_11_W', 'input', 1),
        ('io_in_pmpCfg_11_X', 'input', 1),
        ('io_in_pmpCfg_11_A', 'input', 2),
        ('io_in_pmpCfg_11_L', 'input', 1),
        ('io_in_pmpCfg_12_R', 'input', 1),
        ('io_in_pmpCfg_12_W', 'input', 1),
        ('io_in_pmpCfg_12_X', 'input', 1),
        ('io_in_pmpCfg_12_A', 'input', 2),
        ('io_in_pmpCfg_12_L', 'input', 1),
        ('io_in_pmpCfg_13_R', 'input', 1),
        ('io_in_pmpCfg_13_W', 'input', 1),
        ('io_in_pmpCfg_13_X', 'input', 1),
        ('io_in_pmpCfg_13_A', 'input', 2),
        ('io_in_pmpCfg_13_L', 'input', 1),
        ('io_in_pmpCfg_14_R', 'input', 1),
        ('io_in_pmpCfg_14_W', 'input', 1),
        ('io_in_pmpCfg_14_X', 'input', 1),
        ('io_in_pmpCfg_14_A', 'input', 2),
        ('io_in_pmpCfg_14_L', 'input', 1),
        ('io_in_pmpCfg_15_R', 'input', 1),
        ('io_in_pmpCfg_15_W', 'input', 1),
        ('io_in_pmpCfg_15_X', 'input', 1),
        ('io_in_pmpCfg_15_A', 'input', 2),
        ('io_in_pmpCfg_15_L', 'input', 1),
        ('io_in_pmpCfg_16_R', 'input', 1),
        ('io_in_pmpCfg_16_W', 'input', 1),
        ('io_in_pmpCfg_16_X', 'input', 1),
        ('io_in_pmpCfg_16_A', 'input', 2),
        ('io_in_pmpCfg_16_L', 'input', 1),
        ('io_in_pmpCfg_17_R', 'input', 1),
        ('io_in_pmpCfg_17_W', 'input', 1),
        ('io_in_pmpCfg_17_X', 'input', 1),
        ('io_in_pmpCfg_17_A', 'input', 2),
        ('io_in_pmpCfg_17_L', 'input', 1),
        ('io_in_pmpCfg_18_R', 'input', 1),
        ('io_in_pmpCfg_18_W', 'input', 1),
        ('io_in_pmpCfg_18_X', 'input', 1),
        ('io_in_pmpCfg_18_A', 'input', 2),
        ('io_in_pmpCfg_18_L', 'input', 1),
        ('io_in_pmpCfg_19_R', 'input', 1),
        ('io_in_pmpCfg_19_W', 'input', 1),
        ('io_in_pmpCfg_19_X', 'input', 1),
        ('io_in_pmpCfg_19_A', 'input', 2),
        ('io_in_pmpCfg_19_L', 'input', 1),
        ('io_in_pmpCfg_20_R', 'input', 1),
        ('io_in_pmpCfg_20_W', 'input', 1),
        ('io_in_pmpCfg_20_X', 'input', 1),
        ('io_in_pmpCfg_20_A', 'input', 2),
        ('io_in_pmpCfg_20_L', 'input', 1),
        ('io_in_pmpCfg_21_R', 'input', 1),
        ('io_in_pmpCfg_21_W', 'input', 1),
        ('io_in_pmpCfg_21_X', 'input', 1),
        ('io_in_pmpCfg_21_A', 'input', 2),
        ('io_in_pmpCfg_21_L', 'input', 1),
        ('io_in_pmpCfg_22_R', 'input', 1),
        ('io_in_pmpCfg_22_W', 'input', 1),
        ('io_in_pmpCfg_22_X', 'input', 1),
        ('io_in_pmpCfg_22_A', 'input', 2),
        ('io_in_pmpCfg_22_L', 'input', 1),
        ('io_in_pmpCfg_23_R', 'input', 1),
        ('io_in_pmpCfg_23_W', 'input', 1),
        ('io_in_pmpCfg_23_X', 'input', 1),
        ('io_in_pmpCfg_23_A', 'input', 2),
        ('io_in_pmpCfg_23_L', 'input', 1),
        ('io_in_pmpCfg_24_R', 'input', 1),
        ('io_in_pmpCfg_24_W', 'input', 1),
        ('io_in_pmpCfg_24_X', 'input', 1),
        ('io_in_pmpCfg_24_A', 'input', 2),
        ('io_in_pmpCfg_24_L', 'input', 1),
        ('io_in_pmpCfg_25_R', 'input', 1),
        ('io_in_pmpCfg_25_W', 'input', 1),
        ('io_in_pmpCfg_25_X', 'input', 1),
        ('io_in_pmpCfg_25_A', 'input', 2),
        ('io_in_pmpCfg_25_L', 'input', 1),
        ('io_in_pmpCfg_26_R', 'input', 1),
        ('io_in_pmpCfg_26_W', 'input', 1),
        ('io_in_pmpCfg_26_X', 'input', 1),
        ('io_in_pmpCfg_26_A', 'input', 2),
        ('io_in_pmpCfg_26_L', 'input', 1),
        ('io_in_pmpCfg_27_R', 'input', 1),
        ('io_in_pmpCfg_27_W', 'input', 1),
        ('io_in_pmpCfg_27_X', 'input', 1),
        ('io_in_pmpCfg_27_A', 'input', 2),
        ('io_in_pmpCfg_27_L', 'input', 1),
        ('io_in_pmpCfg_28_R', 'input', 1),
        ('io_in_pmpCfg_28_W', 'input', 1),
        ('io_in_pmpCfg_28_X', 'input', 1),
        ('io_in_pmpCfg_28_A', 'input', 2),
        ('io_in_pmpCfg_28_L', 'input', 1),
        ('io_in_pmpCfg_29_R', 'input', 1),
        ('io_in_pmpCfg_29_W', 'input', 1),
        ('io_in_pmpCfg_29_X', 'input', 1),
        ('io_in_pmpCfg_29_A', 'input', 2),
        ('io_in_pmpCfg_29_L', 'input', 1),
        ('io_in_pmpCfg_30_R', 'input', 1),
        ('io_in_pmpCfg_30_W', 'input', 1),
        ('io_in_pmpCfg_30_X', 'input', 1),
        ('io_in_pmpCfg_30_A', 'input', 2),
        ('io_in_pmpCfg_30_L', 'input', 1),
        ('io_in_pmpCfg_31_R', 'input', 1),
        ('io_in_pmpCfg_31_W', 'input', 1),
        ('io_in_pmpCfg_31_X', 'input', 1),
        ('io_in_pmpCfg_31_A', 'input', 2),
        ('io_in_pmpCfg_31_L', 'input', 1),
        ('io_out_pmpCfgWData', 'output', 64),
        ('io_out_pmpAddrRData_0', 'output', 64),
        ('io_out_pmpAddrRData_1', 'output', 64),
        ('io_out_pmpAddrRData_2', 'output', 64),
        ('io_out_pmpAddrRData_3', 'output', 64),
        ('io_out_pmpAddrRData_4', 'output', 64),
        ('io_out_pmpAddrRData_5', 'output', 64),
        ('io_out_pmpAddrRData_6', 'output', 64),
        ('io_out_pmpAddrRData_7', 'output', 64),
        ('io_out_pmpAddrRData_8', 'output', 64),
        ('io_out_pmpAddrRData_9', 'output', 64),
        ('io_out_pmpAddrRData_10', 'output', 64),
        ('io_out_pmpAddrRData_11', 'output', 64),
        ('io_out_pmpAddrRData_12', 'output', 64),
        ('io_out_pmpAddrRData_13', 'output', 64),
        ('io_out_pmpAddrRData_14', 'output', 64),
        ('io_out_pmpAddrRData_15', 'output', 64),
        ('io_out_pmpAddrRData_16', 'output', 64),
        ('io_out_pmpAddrRData_17', 'output', 64),
        ('io_out_pmpAddrRData_18', 'output', 64),
        ('io_out_pmpAddrRData_19', 'output', 64),
        ('io_out_pmpAddrRData_20', 'output', 64),
        ('io_out_pmpAddrRData_21', 'output', 64),
        ('io_out_pmpAddrRData_22', 'output', 64),
        ('io_out_pmpAddrRData_23', 'output', 64),
        ('io_out_pmpAddrRData_24', 'output', 64),
        ('io_out_pmpAddrRData_25', 'output', 64),
        ('io_out_pmpAddrRData_26', 'output', 64),
        ('io_out_pmpAddrRData_27', 'output', 64),
        ('io_out_pmpAddrRData_28', 'output', 64),
        ('io_out_pmpAddrRData_29', 'output', 64),
        ('io_out_pmpAddrRData_30', 'output', 64),
        ('io_out_pmpAddrRData_31', 'output', 64),
    ),
}

def _pmp_napot_mask(address: Any) -> Any:
    """Return the locked V2 NAPOT mask from a 46-bit pmpaddr value."""
    # pmpaddr stores address bits [55:2]; the low contiguous ones encode size.
    # The expression is deliberately width-preserving and synthesizable.
    return (~(address ^ (address + 1)))[:46]


def _connect_defaults(module: Module, ports: dict[str, Signal], specs: tuple[tuple[str, str, int], ...]) -> None:
    """Drive every unsupported output explicitly; no implicit X values."""
    for name, direction, _width in specs:
        if direction == "output":
            module.d.comb += ports[name].eq(0)


class PMPFamily(Elaboratable):
    """PMP/PMA family with real CSR state and ordered permission matching.

    PMP, PMPChecker, PMPChecker_12, PMPChecker_2 and PMPEntryHandleModule are
    implemented from the locked V2 equations.  No other member is silently
    represented by an all-zero shell: unsupported fields remain explicit
    contract-only tie-offs at the ABI boundary.
    """

    def __init__(self, member: str = "PMP") -> None:
        if member not in PORT_SPECS:
            raise ValueError(member)
        self.member = member
        self.specs = PORT_SPECS[member]
        self.ports = {name: Signal(width, name=name) for name, _direction, width in self.specs}

    def _clock_domain(self, module: Module) -> None:
        if "clock" in self.ports:
            domain = (ClockDomain("sync", async_reset=True) if "reset" in self.ports
                      else ClockDomain("sync", reset_less=True))
            domain.clk = self.ports["clock"]
            if "reset" in self.ports:
                domain.rst = self.ports["reset"]
            module.domains += domain

    def _pmp(self, module: Module) -> None:
        """Hold PMP/PMA CSR state and apply distributed writes one cycle later."""

        p = self.ports
        write_addresses = (
            0x7DE, 0x3C9, 0x3CE, 0x3B4, 0x3B7, 0x7CB, 0x3C2, 0x7CF,
            0x7C4, 0x3B1, 0x3A2, 0x7E4, 0x3CD, 0x7DA, 0x3A6, 0x7C8,
            0x3B5, 0x7D7, 0x3C6, 0x7E1, 0x3BC, 0x7D2, 0x7DB, 0x7D0,
            0x3BD, 0x3B8, 0x7DF, 0x7E7, 0x3CA, 0x7D6, 0x7C0, 0x3B9,
            0x7CC, 0x7D1, 0x3C5, 0x3CF, 0x7E0, 0x3BE, 0x7CD, 0x3B3,
            0x7C9, 0x3C4, 0x3A4, 0x3BF, 0x7E6, 0x7D5, 0x3B0, 0x7C6,
            0x3C8, 0x3CB, 0x7DC, 0x3BA, 0x7DD, 0x7CE, 0x3C1, 0x3C3,
            0x3B2, 0x7D4, 0x7D9, 0x7CA, 0x7E3, 0x7D3, 0x3C7, 0x3B6,
            0x7D8, 0x7C2, 0x3C0, 0x3BB, 0x7E5, 0x3A0, 0x7E2, 0x3CC,
        )
        delayed = {address: Signal(name="wen_reg_last_REG" + (f"_{index}" if index else ""))
                   for index, address in enumerate(write_addresses)}
        wdata = Signal(64, name="wdata_reg", reset_less=True)
        module.d.sync += [signal.eq(p["io_distribute_csr_w_valid"]
                                   & (p["io_distribute_csr_w_bits_addr"] == address))
                          for address, signal in delayed.items()]
        with cast(AbstractContextManager[None], module.If(p["io_distribute_csr_w_valid"])):
            module.d.sync += wdata.eq(p["io_distribute_csr_w_bits_data"])
        pma_cfg = (0, 0, 0x0B0B0B0F0B000000, 0x186F0B080B0B0B0F)
        pma_addr = (0,) * 19 + (0x4000000, 0x8000000, 0xC004000, 0xC014000,
                    0xE008000, 0xE008400, 0xE008800, 0xE400000, 0xE400800,
                    0xE800000, 0x20000000, 0x20000000000, 0x1FFFFFFFFFFF)
        config_first = {
            "pmp": (True,) * 8 + (False,) * 10 + (True, False, True, True, True,
                    False, False, True, False, False, False, True, True, False),
            "pma": (True, False, False, True, False, False, False, True, True, True,
                    True, True, True, True, True, True, False, False, False, False,
                    False, False, True, False, True, True, False, False, True, False, True, True),
        }

        def matching_mask(name: str, address: Any, mode_low: Any) -> Any:
            packed = Signal(46, name=name + "_packed")
            mask = Signal(48, name=name)
            module.d.comb += [packed.eq(cast(Any, Cat(mode_low, address[:45])) | Const(0x3FF, 46)),
                              mask.eq(Cat(Const(3, 2), (packed & ~(packed + 1))[:46]))]
            return mask

        def bit(value: Value, index: int) -> Value:
            return cast(Value, value[index])

        for kind, cfg_base, addr_base in (("pmp", 0x3A0, 0x3B0), ("pma", 0x7C0, 0x7C8)):
            cfg = [Signal(64, name=f"{kind}Mapping_cfgMerged_{group}",
                          init=pma_cfg[group] if kind == "pma" else 0) for group in range(4)]
            addresses = [Signal(46, name=f"{kind}Mapping_addr_{index}",
                                init=pma_addr[index] if kind == "pma" else 0) for index in range(32)]
            masks = [Signal(48, name=f"{kind}Mapping_mask_{index}",
                            init=((1 << 48) - 1 if index == 31 else 0xFFF) if kind == "pma" else 0)
                     for index in range(32)]
            bytes_old = [cast(Value, cfg[index // 8][8 * (index % 8):8 * (index % 8) + 8]) for index in range(32)]
            for group in range(4):
                new_bytes = []
                for lane in range(8):
                    old = bytes_old[group * 8 + lane]
                    incoming = cast(Value, wdata[8 * lane:8 * lane + 8])
                    canonical = Cat(bit(incoming, 0), bit(incoming, 1) & bit(incoming, 0), bit(incoming, 2),
                                    bit(incoming, 3) | bit(incoming, 4), bit(incoming, 4),
                                    bit(incoming, 5), bit(incoming, 6), bit(incoming, 7))
                    new_bytes.append(Mux(old[7], old, canonical))
                with cast(AbstractContextManager[None], module.If(delayed[cfg_base + group * 2])):
                    module.d.sync += cfg[group].eq(Cat(*new_bytes))
            for index, old in enumerate(bytes_old):
                incoming = cast(Value, wdata[8 * (index % 8):8 * (index % 8) + 8])
                cfg_flag = delayed[cfg_base + (index // 8) * 2]
                addr_flag = delayed[addr_base + index]
                locked = bit(old, 7)
                if index < 31:
                    following = bytes_old[index + 1]
                    locked = locked | (bit(following, 7) & (cast(Value, following[3:5]) == 1))
                address_write = addr_flag & ~locked
                with cast(AbstractContextManager[None], module.If(address_write)):
                    module.d.sync += addresses[index].eq(wdata[:46])
                new_mode = Signal(2, name=f"{kind}_new_mode_{index}")
                module.d.comb += new_mode.eq(Mux(bit(old, 7), old[3:5],
                                               Cat(bit(incoming, 3) | bit(incoming, 4), bit(incoming, 4))))
                cfg_mask_write = cfg_flag & ~bit(old, 7) & new_mode[1]
                cfg_mask = matching_mask(f"{kind}_cfg_mask_{index}", addresses[index], new_mode[0])
                addr_mask = matching_mask(f"{kind}_addr_mask_{index}", wdata[:46], old[3])
                if config_first[kind][index]:
                    with cast(AbstractContextManager[None], module.If(cfg_mask_write)):
                        module.d.sync += masks[index].eq(cfg_mask)
                    with cast(AbstractContextManager[None], module.Elif(address_write)):
                        module.d.sync += masks[index].eq(addr_mask)
                else:
                    with cast(AbstractContextManager[None], module.If(addr_flag)):
                        with cast(AbstractContextManager[None], module.If(~locked)):
                            module.d.sync += masks[index].eq(addr_mask)
                    with cast(AbstractContextManager[None], module.Elif(cfg_mask_write)):
                        module.d.sync += masks[index].eq(cfg_mask)
                fields = {"cfg_a": old[3:5], "cfg_x": old[2], "cfg_w": old[1], "cfg_r": old[0],
                          "addr": addresses[index], "mask": masks[index]}
                if kind == "pmp":
                    fields["cfg_l"] = old[7]
                else:
                    fields.update(cfg_c=old[6], cfg_atomic=old[5])
                module.d.comb += [p[f"io_{kind}_{index}_{field}"].eq(value) for field, value in fields.items()]

    def _checker12(self, module: Module) -> None:
        """Implement locked PMPChecker_12 capture, matching and response equations."""
        request_valid = self.ports["io_req_valid"]
        request_address = self.ports["io_req_bits_addr"]
        request_command = self.ports["io_req_bits_cmd"]
        mode = self.ports["io_check_env_mode"]
        debug = self.ports["io_check_env_debug"]
        grain_mask = Const(0x3FFFFFFFFC00, 46)
        debug_window = ((request_address > Const(0x3801FFFF, 48)) &
                        (request_address < Const(0x38021000, 48)))
        match_enable = ~debug_window | debug

        def state_name(base: str, index: int) -> str:
            return base if index == 0 else f"{base}_{index}"

        # These exact names correspond to the locked match registers. They are
        # asynchronously cleared and only capture a new comparison on valid.
        pmp_match = [
            Signal(name=state_name("res_pmp_r", index)) for index in range(32)
        ]
        pma_match = [
            Signal(name=state_name("res_pma_r", index)) for index in range(32)
        ]

        def match_equations(prefix: str) -> list[Any]:
            matches: list[Any] = []
            previous_base: Any = Const(0, 48)
            for index in range(32):
                address = self.ports[f"io_check_env_{prefix}_{index}_addr"]
                mask = self.ports[f"io_check_env_{prefix}_{index}_mask"]
                mode_a = self.ports[f"io_check_env_{prefix}_{index}_cfg_a"]
                entry_base = Cat(Const(0, 2), address & grain_mask)
                napot_match = mode_a[1] & (
                    (request_address & ~mask) == (entry_base & ~mask)
                )
                tor_match = mode_a == 1
                if index == 0:
                    tor_match = tor_match & (request_address < entry_base)
                else:
                    tor_match = (tor_match & (request_address >= previous_base) &
                                 (request_address < entry_base))
                matches.append((napot_match | tor_match) & match_enable)
                previous_base = entry_base
            return matches

        pmp_hit_next = match_equations("pmp")
        pma_hit_next = match_equations("pma")

        # Captured cfg/command registers have no reset in the reference clock
        # block. Keep them reset-less and uninitialized until the first valid.
        pmp_cfg = {
            field: [
                Signal(name=f"res_pmp_r_33_{index}_cfg_{field}",
                       reset_less=True, init=None)
                for index in range(33)
            ]
            for field in ("x", "w", "r")
        }
        pma_cfg = {
            field: [
                Signal(name=f"res_pma_r_33_{index}_cfg_{field}",
                       reset_less=True, init=None)
                for index in range(32)
            ]
            for field in ("c", "atomic", "x", "w", "r")
        }
        command = Signal(3, name="cmd", reset_less=True, init=None)

        with cast(AbstractContextManager[None], module.If(request_valid)):
            module.d.sync += [
                *(pmp_match[index].eq(pmp_hit_next[index]) for index in range(32)),
                *(pma_match[index].eq(pma_hit_next[index]) for index in range(32)),
            ]
            for index in range(32):
                ignore_pmp = mode[1] & ~self.ports[f"io_check_env_pmp_{index}_cfg_l"]
                for field in ("x", "w", "r"):
                    source = self.ports[f"io_check_env_pmp_{index}_cfg_{field}"]
                    module.d.sync += pmp_cfg[field][index].eq(source | ignore_pmp)
                    pma_source = self.ports[f"io_check_env_pma_{index}_cfg_{field}"]
                    module.d.sync += pma_cfg[field][index].eq(pma_source)
                for field in ("c", "atomic"):
                    module.d.sync += pma_cfg[field][index].eq(
                        self.ports[f"io_check_env_pma_{index}_cfg_{field}"]
                    )
            # PMP's slot 32 is the no-match default; PMA has a zero default.
            for field in ("x", "w", "r"):
                module.d.sync += pmp_cfg[field][32].eq(mode[1])
            module.d.sync += command.eq(request_command)

        def first_match(hits: list[Any], values: list[Any], default: Any) -> Any:
            selected = default
            # Build from high to low so slot 0 has highest priority.
            for index in range(len(hits) - 1, -1, -1):
                selected = Mux(hits[index], values[index], selected)
            return selected

        selected_pmp = {
            field: Signal(name=f"selected_pmp_{field}") for field in ("x", "w", "r")
        }
        selected_pma = {
            field: Signal(name=("res_pma_cfg_w" if field == "w" else
                               "resp_atomic" if field == "atomic" else
                               f"selected_pma_{field}"))
            for field in ("c", "atomic", "x", "w", "r")
        }
        for field in ("x", "w", "r"):
            module.d.comb += selected_pmp[field].eq(
                first_match(pmp_match, pmp_cfg[field][:32], pmp_cfg[field][32])
            )
        for field in ("c", "atomic", "x", "w", "r"):
            module.d.comb += selected_pma[field].eq(
                first_match(pma_match, pma_cfg[field], Const(0, 1))
            )
        load_or_misc = (command[:2] == 0) | (command == 7)
        load_error = (
            (load_or_misc & (command != 5) & ~selected_pmp["r"])
            | (load_or_misc & ~selected_pma["r"])
            | ((command == 4) & ~selected_pma["atomic"])
        )
        store_error = (
            (((command[:2] == 1) | (command == 5)) & ~selected_pmp["w"])
            | (((command == 5) & (~selected_pma["atomic"] | ~selected_pma["w"]))
               | ((command != 5) & (command[:2] == 1) & ~selected_pma["w"]))
        )
        instruction_error = (
            ((command[:2] == 2) | (command == 7))
            & (~selected_pmp["x"] | ~selected_pma["x"])
        )
        module.d.comb += [
            self.ports["io_resp_ld"].eq(load_error),
            self.ports["io_resp_st"].eq(store_error),
            self.ports["io_resp_instr"].eq(instruction_error),
            self.ports["io_resp_mmio"].eq(~selected_pma["c"]),
            self.ports["io_resp_atomic"].eq(selected_pma["atomic"]),
        ]


    def _checker(self, module: Module, variant: str) -> None:
        """Implement the first-match PMP/PMA checker variants."""
        mode = self.ports["io_check_env_mode"]
        debug = self.ports["io_check_env_debug"]
        req = self.ports.get("io_req_bits_addr")
        cmd = self.ports.get("io_req_bits_cmd")
        if req is None:
            req = Const(0, 48)

        # The read-only checker variant is a specialized V2 read path.  Its
        # reference does not expose a command or write/execute permissions:
        # it returns exception bits (not allow bits), and PMA is mandatory.
        # Keep the first-match equations explicit so every PMA input affects
        # the generated RTL rather than collapsing to a fixed MMIO window.
        if variant == "PMPChecker":
            grain_mask = Const(0x3FFFFFFFFC00, 46)
            debug_window = (req > Const(0x3801FFFF, 48)) & (req < Const(0x38021000, 48))

            def match_entries(prefix: str) -> list[Any]:
                matches: list[Any] = []
                previous_base: Any = Const(0, 48)
                for index in range(32):
                    address = self.ports[f"io_check_env_{prefix}_{index}_addr"]
                    mode_a = self.ports[f"io_check_env_{prefix}_{index}_cfg_a"]
                    # Concatenation keeps the architectural 48-bit address
                    # width exact; an arithmetic shift otherwise widens the
                    # intermediate expression in generated RTL.
                    entry_base = Signal(48, name=f"read_{prefix}_base_{index}")
                    module.d.comb += entry_base.eq(Cat(Const(0, 2), address & grain_mask))
                    napot = (mode_a[1] &
                             (((req & ~self.ports[f"io_check_env_{prefix}_{index}_mask"]) ==
                               (entry_base & ~self.ports[f"io_check_env_{prefix}_{index}_mask"]))))
                    tor = ((mode_a == 1) & (req >= previous_base) & (req < entry_base))
                    matched = Signal(name=f"read_{prefix}_match_{index}")
                    module.d.comb += matched.eq(Mux(mode_a[1], napot, tor) & (~debug_window | debug))
                    matches.append(matched)
                    previous_base = entry_base
                return matches

            pmp_matches = match_entries("pmp")
            pma_matches = match_entries("pma")

            pmp_r: Any = mode[1]
            pma_r: Any = Const(0)
            pma_c: Any = Const(0)
            pma_atomic: Any = Const(0)
            for index in range(31, -1, -1):
                pmp_r_value = self.ports[f"io_check_env_pmp_{index}_cfg_r"]
                pmp_r_value = pmp_r_value | (mode[1] & ~self.ports[f"io_check_env_pmp_{index}_cfg_l"])
                pmp_r = Mux(pmp_matches[index], pmp_r_value, pmp_r)
                pma_r = Mux(pma_matches[index], self.ports[f"io_check_env_pma_{index}_cfg_r"], pma_r)
                pma_c = Mux(pma_matches[index], self.ports[f"io_check_env_pma_{index}_cfg_c"], pma_c)
                pma_atomic = Mux(pma_matches[index], self.ports[f"io_check_env_pma_{index}_cfg_atomic"], pma_atomic)

            module.d.comb += [
                self.ports["io_resp_ld"].eq(~(pmp_r & pma_r)),
                self.ports["io_resp_mmio"].eq(~pma_c),
                self.ports["io_resp_atomic"].eq(pma_atomic),
            ]
            return

        # This reduced checker instance exposes only execute-denial and PMA
        # cacheability.  Its response is captured on a valid request, while
        # both PMP and PMA use the same ordered address-match structure.
        if variant == "PMPChecker_2":
            grain_mask = Const(0x3FFFFFFFFC00, 46)
            debug_window = (req > Const(0x3801FFFF, 48)) & (req < Const(0x38021000, 48))
            debug_allowed = ~debug_window | debug

            def match_entries(prefix: str) -> list[Any]:
                matches: list[Any] = []
                for index in range(32):
                    address = self.ports[f"io_check_env_{prefix}_{index}_addr"]
                    mode_a = self.ports[f"io_check_env_{prefix}_{index}_cfg_a"]
                    entry_base = Cat(Const(0, 2), address & grain_mask)
                    if index == 0:
                        previous_base: Any = Const(0, 48)
                    else:
                        previous_address = self.ports[f"io_check_env_{prefix}_{index - 1}_addr"]
                        previous_base = Cat(Const(0, 2), previous_address & grain_mask)
                    napot = mode_a[1] & (
                        (req & ~self.ports[f"io_check_env_{prefix}_{index}_mask"])
                        == (entry_base & ~self.ports[f"io_check_env_{prefix}_{index}_mask"])
                    )
                    tor = (mode_a == 1) & (req >= previous_base) & (req < entry_base)
                    matches.append((napot | tor) & debug_allowed)
                return matches

            pmp_matches = match_entries("pmp")
            pma_matches = match_entries("pma")
            pmp_x: Any = self.ports["io_check_env_mode"][1]
            pma_x: Any = Const(0)
            pma_c: Any = Const(0)
            for index in range(31, -1, -1):
                pmp_l = self.ports[f"io_check_env_pmp_{index}_cfg_l"]
                pmp_x_value = self.ports[f"io_check_env_pmp_{index}_cfg_x"]
                pmp_x_value = pmp_x_value | (self.ports["io_check_env_mode"][1] & ~pmp_l)
                pmp_x = Mux(pmp_matches[index], pmp_x_value, pmp_x)
                pma_x = Mux(
                    pma_matches[index],
                    self.ports[f"io_check_env_pma_{index}_cfg_x"],
                    pma_x,
                )
                pma_c = Mux(
                    pma_matches[index],
                    self.ports[f"io_check_env_pma_{index}_cfg_c"],
                    pma_c,
                )

            with cast(AbstractContextManager[None], module.If(self.ports["io_req_valid"])):
                module.d.sync += [
                    self.ports["io_resp_instr"].eq(~(pmp_x & pma_x)),
                    self.ports["io_resp_mmio"].eq(~pma_c),
                ]
            return

        raise ValueError("unsupported checker variant")

    def _entry(self, module: Module) -> None:
        """Model the NewCSR PMP entry handler, including its WARL rules.

        Configuration bits are supplied by the individual CSR fields.  This
        block owns the address registers and emits a write-back value for a
        selected configuration CSR. Readback presents the WARL grain bits
        only when the corresponding address CSR is read.
        """
        wen = self.ports["io_in_wen"]
        ren = self.ports["io_in_ren"]
        csr = self.ports["io_in_addr"]
        data = self.ports["io_in_wdata"]

        # The configured platform grain is 4 KiB, hence
        # G = PlatformGrain - PMPOffBits = 10.  The state registers
        # store pmpaddr[45:0] under the reference's address-state identities.
        addr = [Signal(46, name=f"pmpAddr_{i}_ADDRESS") for i in range(32)]

        def cfg_byte(index: int) -> Any:
            """Return one externally supplied PMPCfg byte as a UInt."""

            # PMPCfg uses R/W/X/A in bits 0..4, read-only ATOMIC/C in bits
            # 5..6, and L in bit 7.  The read-only fields are constant zero
            # on this interface, so preserve the architectural byte layout.
            return Cat(
                self.ports[f"io_in_pmpCfg_{index}_R"],
                self.ports[f"io_in_pmpCfg_{index}_W"],
                self.ports[f"io_in_pmpCfg_{index}_X"],
                self.ports[f"io_in_pmpCfg_{index}_A"][0],
                self.ports[f"io_in_pmpCfg_{index}_A"][1],
                Const(0, 2),
                self.ports[f"io_in_pmpCfg_{index}_L"],
            )

        # Configuration CSR write-back is zero when no CSR is selected.
        cfg_write = Const(0, 64)
        for group in range(4):
            selected = wen & (csr == (0x3A0 + group * 2))
            lane_values: list[Any] = []
            for lane in range(8):
                index = group * 8 + lane
                old = cfg_byte(index)
                incoming = data[lane * 8:(lane + 1) * 8]
                # Coarser grain canonicalizes A[0] to A[1] | A[0].
                canonical = Cat(
                    incoming[0],
                    cast(Any, incoming[1]) & cast(Any, incoming[0]),
                    incoming[2],
                    cast(Any, incoming[3]) | cast(Any, incoming[4]),
                    incoming[4],
                    incoming[5],
                    incoming[6],
                    incoming[7],
                )
                lane_value = Mux(~old[7], canonical, old)
                lane_values.append(lane_value)
            cfg_write = Mux(selected, Cat(*lane_values), cfg_write)
        module.d.comb += self.ports["io_out_pmpCfgWData"].eq(cfg_write)

        # Address state and masked readback.  A locked entry, or an entry
        # immediately preceding a locked TOR entry, cannot be rewritten.
        for i in range(32):
            current_cfg = cfg_byte(i)
            if i < 31:
                next_cfg = cfg_byte(i + 1)
                locked = current_cfg[7] | (next_cfg[7] & (next_cfg[3:5] == 1))
            else:
                locked = current_cfg[7]
            write_hit = wen & (csr == (0x3B0 + i))
            module.d.sync += addr[i].eq(Mux(write_hit & ~locked, data[:46], addr[i]))

            # Address reads always return the current register, with WARL
            # low-bit presentation only for the selected pmpaddr CSR.
            aligned = Mux(
                current_cfg[4],
                Cat(Const(0x1FF, 9), addr[i][9:46]),
                Cat(Const(0, 10), addr[i][10:46]),
            )
            read_value = Mux(ren & (csr == (0x3B0 + i)), aligned, addr[i])
            module.d.comb += self.ports[f"io_out_pmpAddrRData_{i}"].eq(Cat(read_value, Const(0, 18)))

    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        self._clock_domain(module)
        if self.member == "PMP":
            self._pmp(module)
        elif self.member == "PMPChecker_12":
            self._checker12(module)
        elif self.member in ("PMPChecker", "PMPChecker_2"):
            self._checker(module, self.member)
        elif self.member == "PMPEntryHandleModule":
            self._entry(module)
        return module


def build_verilog(configuration: Any, injected_dependencies: Any) -> str:
    """Export deterministic Verilog for one same-name PMP member."""

    del injected_dependencies
    member = "PMP"
    if isinstance(configuration, dict):
        member = str(configuration.get("module", member))
    elif isinstance(configuration, str):
        member = configuration
    top = PMPFamily(member)
    return verilog.convert(top, name=member, ports=[top.ports[name] for name, _direction, _width in top.specs], emit_src=False)


def main() -> None:
    """Print the default PMP RTL."""

    print(build_verilog({"module": "PMP"}, {}))


if __name__ == "__main__":
    main()
