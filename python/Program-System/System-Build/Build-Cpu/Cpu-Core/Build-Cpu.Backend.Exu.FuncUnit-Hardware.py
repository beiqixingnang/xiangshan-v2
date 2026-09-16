"""UHSC V2 backend execution-unit / functional-unit family (FuncUnit, ExeUnit, Bku, Dispatcher).
UHSC V2 后端执行单元 / 功能单元族（FuncUnit、ExeUnit、Bku、Dispatcher）。

Selected Kunminghu V2 locked modules from xiangshan/backend/fu/FuncUnit.scala,
xiangshan/backend/fu/Bku.scala and xiangshan/backend/exu/ExeUnit.scala.  The integer/
branch/Bku/dispatch/EXU core is covered; the FP/vector FU leaves (fudian/yunsuan)
and the NewCSR CSR module are owned by other workers and excluded from this file.
选定的 Kunminghu V2 锁定模块来自上述三个 Scala 源。本文件覆盖整数/分支/Bku/
分发/EXU 核心；FP/向量 FU 叶子（fudian/yunsuan）与 NewCSR 的 CSR 模块由其他
worker 负责，不在本文件范围内。
"""

from __future__ import annotations

from amaranth import Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog
from amaranth.hdl.ast import Value
from dataclasses import dataclass
from typing import Any, cast

# =============================================================================
# Module Contract
# =============================================================================
# Source family: the parameterised XiangShan FuncUnit pipeline, the ExeUnit
# issue/complete interface, the Bku branch/crypto unit and the issue dispatcher.
# 来源 family：参数化 XiangShan FuncUnit 流水线、ExeUnit 发射/写回接口、Bku
# 分支/加密单元与发射分发器。
__all__ = [
    "PortSpec", "PORTS", "COVERED_MODULES", "ExuFuncModule",
    "module_ports", "module_latency", "build_verilog", "main",
]

# Locked behavioural authority for every covered module. / 每个覆盖模块的锁定行为权威。
SOURCE_PATHS = (
    "xiangshan/backend/fu/FuncUnit.scala",
    "xiangshan/backend/fu/Bku.scala",
    "xiangshan/backend/exu/ExeUnit.scala",
)

# Port geometry copied verbatim from validation/v2-locked-hierarchy.json (width "" => 1).
# 端口几何逐字复制自 validation/v2-locked-hierarchy.json（宽度 "" 视为 1）。
PORTS: dict[str, tuple[tuple[str, str, int], ...]] = {
    'Dispatcher': (
        ('io_in_valid', 'input', 1), ('io_in_bits_fuType', 'input', 35), ('io_in_bits_fuOpType', 'input', 9),
        ('io_out_0_valid', 'output', 1), ('io_out_0_bits_fuOpType', 'output', 9), ('io_out_1_valid', 'output', 1),
        ('io_out_1_bits_fuOpType', 'output', 9), ('io_out_2_valid', 'output', 1),
        ('io_out_2_bits_fuOpType', 'output', 9),
    ),
    'Dispatcher_1': (
        ('io_in_valid', 'input', 1), ('io_in_bits_fuType', 'input', 35), ('io_in_bits_fuOpType', 'input', 9),
        ('io_in_bits_imm', 'input', 64), ('io_in_bits_nextPcOffset', 'input', 5),
        ('io_in_bits_robIdx_flag', 'input', 1), ('io_in_bits_robIdx_value', 'input', 8),
        ('io_in_bits_pdest', 'input', 8), ('io_in_bits_rfWen', 'input', 1), ('io_in_bits_pc', 'input', 50),
        ('io_in_bits_ftqIdx_flag', 'input', 1), ('io_in_bits_ftqIdx_value', 'input', 6),
        ('io_in_bits_ftqOffset', 'input', 4), ('io_in_bits_predictInfo_target', 'input', 50),
        ('io_in_bits_predictInfo_taken', 'input', 1), ('io_out_0_valid', 'output', 1),
        ('io_out_0_bits_fuOpType', 'output', 9), ('io_out_0_bits_imm', 'output', 64),
        ('io_out_0_bits_nextPcOffset', 'output', 5), ('io_out_0_bits_robIdx_flag', 'output', 1),
        ('io_out_0_bits_robIdx_value', 'output', 8), ('io_out_0_bits_pdest', 'output', 8),
        ('io_out_0_bits_pc', 'output', 50), ('io_out_0_bits_ftqIdx_flag', 'output', 1),
        ('io_out_0_bits_ftqIdx_value', 'output', 6), ('io_out_0_bits_ftqOffset', 'output', 4),
        ('io_out_0_bits_predictInfo_taken', 'output', 1), ('io_out_1_valid', 'output', 1),
        ('io_out_1_bits_fuOpType', 'output', 9), ('io_out_1_bits_imm', 'output', 64),
        ('io_out_1_bits_nextPcOffset', 'output', 5), ('io_out_1_bits_robIdx_flag', 'output', 1),
        ('io_out_1_bits_robIdx_value', 'output', 8), ('io_out_1_bits_pdest', 'output', 8),
        ('io_out_1_bits_rfWen', 'output', 1), ('io_out_1_bits_pc', 'output', 50),
        ('io_out_1_bits_ftqIdx_flag', 'output', 1), ('io_out_1_bits_ftqIdx_value', 'output', 6),
        ('io_out_1_bits_ftqOffset', 'output', 4), ('io_out_1_bits_predictInfo_target', 'output', 50),
        ('io_out_1_bits_predictInfo_taken', 'output', 1),
    ),
    'Dispatcher_4': (
        ('io_in_valid', 'input', 1), ('io_in_bits_fuType', 'input', 35), ('io_in_bits_fuOpType', 'input', 9),
        ('io_out_0_valid', 'output', 1), ('io_out_0_bits_fuOpType', 'output', 9),
    ),
    'Dispatcher_5': (
        ('io_in_valid', 'input', 1), ('io_in_bits_fuType', 'input', 35), ('io_in_bits_fuOpType', 'input', 9),
        ('io_in_bits_imm', 'input', 64), ('io_in_bits_nextPcOffset', 'input', 5),
        ('io_in_bits_robIdx_flag', 'input', 1), ('io_in_bits_robIdx_value', 'input', 8),
        ('io_in_bits_pdest', 'input', 8), ('io_in_bits_rfWen', 'input', 1), ('io_in_bits_fpWen', 'input', 1),
        ('io_in_bits_vecWen', 'input', 1), ('io_in_bits_v0Wen', 'input', 1), ('io_in_bits_vlWen', 'input', 1),
        ('io_in_bits_fpu_typeTagOut', 'input', 2), ('io_in_bits_fpu_wflags', 'input', 1),
        ('io_in_bits_fpu_typ', 'input', 2), ('io_in_bits_fpu_rm', 'input', 3), ('io_in_bits_pc', 'input', 50),
        ('io_in_bits_ftqIdx_flag', 'input', 1), ('io_in_bits_ftqIdx_value', 'input', 6),
        ('io_in_bits_ftqOffset', 'input', 4), ('io_in_bits_predictInfo_target', 'input', 50),
        ('io_in_bits_predictInfo_taken', 'input', 1), ('io_out_0_valid', 'output', 1),
        ('io_out_0_bits_fuOpType', 'output', 9), ('io_out_0_bits_imm', 'output', 64),
        ('io_out_0_bits_nextPcOffset', 'output', 5), ('io_out_0_bits_robIdx_flag', 'output', 1),
        ('io_out_0_bits_robIdx_value', 'output', 8), ('io_out_0_bits_pdest', 'output', 8),
        ('io_out_0_bits_pc', 'output', 50), ('io_out_0_bits_ftqIdx_flag', 'output', 1),
        ('io_out_0_bits_ftqIdx_value', 'output', 6), ('io_out_0_bits_ftqOffset', 'output', 4),
        ('io_out_0_bits_predictInfo_taken', 'output', 1), ('io_out_1_valid', 'output', 1),
        ('io_out_1_bits_fuOpType', 'output', 9), ('io_out_1_bits_imm', 'output', 64),
        ('io_out_1_bits_nextPcOffset', 'output', 5), ('io_out_1_bits_robIdx_flag', 'output', 1),
        ('io_out_1_bits_robIdx_value', 'output', 8), ('io_out_1_bits_pdest', 'output', 8),
        ('io_out_1_bits_rfWen', 'output', 1), ('io_out_1_bits_pc', 'output', 50),
        ('io_out_1_bits_ftqIdx_flag', 'output', 1), ('io_out_1_bits_ftqIdx_value', 'output', 6),
        ('io_out_1_bits_ftqOffset', 'output', 4), ('io_out_1_bits_predictInfo_target', 'output', 50),
        ('io_out_1_bits_predictInfo_taken', 'output', 1), ('io_out_2_valid', 'output', 1),
        ('io_out_2_bits_fpu_typeTagOut', 'output', 2), ('io_out_2_bits_fpu_wflags', 'output', 1),
        ('io_out_2_bits_fpu_typ', 'output', 2), ('io_out_2_bits_fpu_rm', 'output', 3), ('io_out_3_valid', 'output', 1),
        ('io_out_3_bits_fuOpType', 'output', 9), ('io_out_3_bits_robIdx_flag', 'output', 1),
        ('io_out_3_bits_robIdx_value', 'output', 8), ('io_out_3_bits_pdest', 'output', 8),
        ('io_out_3_bits_rfWen', 'output', 1), ('io_out_4_valid', 'output', 1), ('io_out_4_bits_fuOpType', 'output', 9),
        ('io_out_4_bits_robIdx_flag', 'output', 1), ('io_out_4_bits_robIdx_value', 'output', 8),
        ('io_out_4_bits_pdest', 'output', 8), ('io_out_4_bits_vlWen', 'output', 1), ('io_out_5_valid', 'output', 1),
        ('io_out_5_bits_fuOpType', 'output', 9), ('io_out_5_bits_robIdx_flag', 'output', 1),
        ('io_out_5_bits_robIdx_value', 'output', 8), ('io_out_5_bits_pdest', 'output', 8),
        ('io_out_5_bits_fpWen', 'output', 1), ('io_out_5_bits_vecWen', 'output', 1),
        ('io_out_5_bits_v0Wen', 'output', 1),
    ),
    'Dispatcher_7': (
        ('io_in_ready', 'output', 1), ('io_in_valid', 'input', 1), ('io_in_bits_fuType', 'input', 35),
        ('io_in_bits_fuOpType', 'input', 9), ('io_in_bits_imm', 'input', 64), ('io_in_bits_robIdx_flag', 'input', 1),
        ('io_in_bits_robIdx_value', 'input', 8), ('io_in_bits_pdest', 'input', 8), ('io_in_bits_rfWen', 'input', 1),
        ('io_in_bits_flushPipe', 'input', 1), ('io_in_bits_ftqIdx_flag', 'input', 1),
        ('io_in_bits_ftqIdx_value', 'input', 6), ('io_in_bits_ftqOffset', 'input', 4), ('io_out_0_ready', 'input', 1),
        ('io_out_0_valid', 'output', 1), ('io_out_0_bits_fuOpType', 'output', 9), ('io_out_0_bits_imm', 'output', 64),
        ('io_out_0_bits_robIdx_flag', 'output', 1), ('io_out_0_bits_robIdx_value', 'output', 8),
        ('io_out_0_bits_pdest', 'output', 8), ('io_out_0_bits_rfWen', 'output', 1),
        ('io_out_0_bits_ftqIdx_flag', 'output', 1), ('io_out_0_bits_ftqIdx_value', 'output', 6),
        ('io_out_0_bits_ftqOffset', 'output', 4), ('io_out_1_ready', 'input', 1), ('io_out_1_valid', 'output', 1),
        ('io_out_1_bits_fuOpType', 'output', 9), ('io_out_1_bits_imm', 'output', 64),
        ('io_out_1_bits_robIdx_flag', 'output', 1), ('io_out_1_bits_robIdx_value', 'output', 8),
        ('io_out_1_bits_pdest', 'output', 8), ('io_out_1_bits_flushPipe', 'output', 1), ('io_out_2_ready', 'input', 1),
        ('io_out_2_valid', 'output', 1), ('io_out_2_bits_fuOpType', 'output', 9),
        ('io_out_2_bits_robIdx_flag', 'output', 1), ('io_out_2_bits_robIdx_value', 'output', 8),
        ('io_out_2_bits_pdest', 'output', 8), ('io_out_2_bits_rfWen', 'output', 1),
    ),
    'Dispatcher_8': (
        ('io_in_valid', 'input', 1), ('io_in_bits_fuType', 'input', 35), ('io_in_bits_fuOpType', 'input', 9),
        ('io_in_bits_robIdx_flag', 'input', 1), ('io_in_bits_robIdx_value', 'input', 8),
        ('io_in_bits_pdest', 'input', 8), ('io_in_bits_fpWen', 'input', 1), ('io_in_bits_vecWen', 'input', 1),
        ('io_in_bits_v0Wen', 'input', 1), ('io_in_bits_fpu_fmt', 'input', 2), ('io_in_bits_fpu_rm', 'input', 3),
        ('io_out_0_valid', 'output', 1), ('io_out_0_bits_fuOpType', 'output', 9),
        ('io_out_0_bits_fpu_fmt', 'output', 2), ('io_out_0_bits_fpu_rm', 'output', 3), ('io_out_1_valid', 'output', 1),
        ('io_out_1_bits_fuOpType', 'output', 9), ('io_out_1_bits_fpu_fmt', 'output', 2),
        ('io_out_1_bits_fpu_rm', 'output', 3), ('io_out_2_valid', 'output', 1),
        ('io_out_2_bits_fuOpType', 'output', 9), ('io_out_2_bits_robIdx_flag', 'output', 1),
        ('io_out_2_bits_robIdx_value', 'output', 8), ('io_out_2_bits_pdest', 'output', 8),
        ('io_out_2_bits_fpWen', 'output', 1), ('io_out_2_bits_vecWen', 'output', 1),
        ('io_out_2_bits_v0Wen', 'output', 1), ('io_out_3_valid', 'output', 1), ('io_out_3_bits_fuOpType', 'output', 9),
        ('io_out_3_bits_fpu_fmt', 'output', 2), ('io_out_3_bits_fpu_rm', 'output', 3),
    ),
    'Dispatcher_9': (
        ('io_in_ready', 'output', 1), ('io_in_valid', 'input', 1), ('io_in_bits_fuType', 'input', 35),
        ('io_in_bits_fuOpType', 'input', 9), ('io_in_bits_robIdx_flag', 'input', 1),
        ('io_in_bits_robIdx_value', 'input', 8), ('io_in_bits_pdest', 'input', 8), ('io_in_bits_fpWen', 'input', 1),
        ('io_in_bits_fpu_wflags', 'input', 1), ('io_in_bits_fpu_fmt', 'input', 2), ('io_in_bits_fpu_rm', 'input', 3),
        ('io_out_0_ready', 'input', 1), ('io_out_0_valid', 'output', 1), ('io_out_0_bits_fuOpType', 'output', 9),
        ('io_out_0_bits_robIdx_flag', 'output', 1), ('io_out_0_bits_robIdx_value', 'output', 8),
        ('io_out_0_bits_pdest', 'output', 8), ('io_out_0_bits_fpWen', 'output', 1),
        ('io_out_0_bits_fpu_wflags', 'output', 1), ('io_out_0_bits_fpu_fmt', 'output', 2),
        ('io_out_0_bits_fpu_rm', 'output', 3),
    ),
    'Dispatcher_10': (
        ('io_in_valid', 'input', 1), ('io_in_bits_fuType', 'input', 35), ('io_in_bits_fuOpType', 'input', 9),
        ('io_in_bits_fpu_fmt', 'input', 2), ('io_in_bits_fpu_rm', 'input', 3), ('io_out_0_valid', 'output', 1),
        ('io_out_0_bits_fuOpType', 'output', 9), ('io_out_0_bits_fpu_fmt', 'output', 2),
        ('io_out_0_bits_fpu_rm', 'output', 3), ('io_out_1_valid', 'output', 1),
        ('io_out_1_bits_fuOpType', 'output', 9), ('io_out_1_bits_fpu_fmt', 'output', 2),
        ('io_out_1_bits_fpu_rm', 'output', 3),
    ),
    'Dispatcher_13': (
        ('io_in_valid', 'input', 1), ('io_in_bits_fuType', 'input', 35), ('io_in_bits_fuOpType', 'input', 9),
        ('io_in_bits_vpu_vma', 'input', 1), ('io_in_bits_vpu_vta', 'input', 1), ('io_in_bits_vpu_vsew', 'input', 2),
        ('io_in_bits_vpu_vlmul', 'input', 3), ('io_in_bits_vpu_vm', 'input', 1), ('io_in_bits_vpu_vstart', 'input', 8),
        ('io_in_bits_vpu_vuopIdx', 'input', 7), ('io_in_bits_vpu_isExt', 'input', 1),
        ('io_in_bits_vpu_isNarrow', 'input', 1), ('io_in_bits_vpu_isDstMask', 'input', 1),
        ('io_out_0_valid', 'output', 1), ('io_out_0_bits_fuOpType', 'output', 9),
        ('io_out_0_bits_vpu_vsew', 'output', 2), ('io_out_0_bits_vpu_vuopIdx', 'output', 7),
        ('io_out_1_valid', 'output', 1), ('io_out_1_bits_fuOpType', 'output', 9),
        ('io_out_1_bits_vpu_vma', 'output', 1), ('io_out_1_bits_vpu_vsew', 'output', 2),
        ('io_out_1_bits_vpu_vm', 'output', 1), ('io_out_1_bits_vpu_vuopIdx', 'output', 7),
        ('io_out_1_bits_vpu_isExt', 'output', 1), ('io_out_1_bits_vpu_isNarrow', 'output', 1),
        ('io_out_1_bits_vpu_isDstMask', 'output', 1), ('io_out_2_valid', 'output', 1),
        ('io_out_2_bits_fuOpType', 'output', 9), ('io_out_2_bits_vpu_vsew', 'output', 2),
        ('io_out_2_bits_vpu_vuopIdx', 'output', 7), ('io_out_3_valid', 'output', 1),
        ('io_out_3_bits_fuOpType', 'output', 9), ('io_out_3_bits_vpu_vma', 'output', 1),
        ('io_out_3_bits_vpu_vta', 'output', 1), ('io_out_3_bits_vpu_vsew', 'output', 2),
        ('io_out_3_bits_vpu_vlmul', 'output', 3), ('io_out_3_bits_vpu_vm', 'output', 1),
        ('io_out_3_bits_vpu_vstart', 'output', 8), ('io_out_3_bits_vpu_vuopIdx', 'output', 7),
    ),
    'Dispatcher_14': (
        ('io_in_valid', 'input', 1), ('io_in_bits_fuType', 'input', 35), ('io_in_bits_fuOpType', 'input', 9),
        ('io_in_bits_robIdx_flag', 'input', 1), ('io_in_bits_robIdx_value', 'input', 8),
        ('io_in_bits_pdest', 'input', 8), ('io_in_bits_rfWen', 'input', 1), ('io_in_bits_vlWen', 'input', 1),
        ('io_in_bits_vpu_vma', 'input', 1), ('io_in_bits_vpu_vta', 'input', 1), ('io_in_bits_vpu_vsew', 'input', 2),
        ('io_in_bits_vpu_vlmul', 'input', 3), ('io_in_bits_vpu_vm', 'input', 1), ('io_in_bits_vpu_vstart', 'input', 8),
        ('io_in_bits_vpu_fpu_isFoldTo1_2', 'input', 1), ('io_in_bits_vpu_fpu_isFoldTo1_4', 'input', 1),
        ('io_in_bits_vpu_fpu_isFoldTo1_8', 'input', 1), ('io_in_bits_vpu_vuopIdx', 'input', 7),
        ('io_out_0_valid', 'output', 1), ('io_out_0_bits_fuOpType', 'output', 9),
        ('io_out_0_bits_vpu_vsew', 'output', 2), ('io_out_0_bits_vpu_vlmul', 'output', 3),
        ('io_out_0_bits_vpu_vm', 'output', 1), ('io_out_0_bits_vpu_fpu_isFoldTo1_2', 'output', 1),
        ('io_out_0_bits_vpu_fpu_isFoldTo1_4', 'output', 1), ('io_out_0_bits_vpu_fpu_isFoldTo1_8', 'output', 1),
        ('io_out_0_bits_vpu_vuopIdx', 'output', 7), ('io_out_1_valid', 'output', 1),
        ('io_out_1_bits_fuOpType', 'output', 9), ('io_out_1_bits_vpu_vsew', 'output', 2),
        ('io_out_1_bits_vpu_vlmul', 'output', 3), ('io_out_1_bits_vpu_vm', 'output', 1),
        ('io_out_1_bits_vpu_vuopIdx', 'output', 7), ('io_out_2_valid', 'output', 1),
        ('io_out_2_bits_fuOpType', 'output', 9), ('io_out_2_bits_vpu_vma', 'output', 1),
        ('io_out_2_bits_vpu_vta', 'output', 1), ('io_out_2_bits_vpu_vsew', 'output', 2),
        ('io_out_2_bits_vpu_vlmul', 'output', 3), ('io_out_2_bits_vpu_vm', 'output', 1),
        ('io_out_2_bits_vpu_vstart', 'output', 8), ('io_out_2_bits_vpu_vuopIdx', 'output', 7),
        ('io_out_3_valid', 'output', 1), ('io_out_3_bits_fuOpType', 'output', 9),
        ('io_out_3_bits_robIdx_flag', 'output', 1), ('io_out_3_bits_robIdx_value', 'output', 8),
        ('io_out_3_bits_pdest', 'output', 8), ('io_out_3_bits_rfWen', 'output', 1),
        ('io_out_3_bits_vlWen', 'output', 1),
    ),
    'Dispatcher_15': (
        ('io_in_valid', 'input', 1), ('io_in_bits_fuType', 'input', 35), ('io_in_bits_fuOpType', 'input', 9),
        ('io_in_bits_vpu_vma', 'input', 1), ('io_in_bits_vpu_vsew', 'input', 2), ('io_in_bits_vpu_vm', 'input', 1),
        ('io_in_bits_vpu_vuopIdx', 'input', 7), ('io_in_bits_vpu_isExt', 'input', 1),
        ('io_in_bits_vpu_isNarrow', 'input', 1), ('io_in_bits_vpu_isDstMask', 'input', 1),
        ('io_out_0_valid', 'output', 1), ('io_out_0_bits_fuOpType', 'output', 9),
        ('io_out_0_bits_vpu_vsew', 'output', 2), ('io_out_0_bits_vpu_vuopIdx', 'output', 7),
        ('io_out_1_valid', 'output', 1), ('io_out_1_bits_fuOpType', 'output', 9),
        ('io_out_1_bits_vpu_vma', 'output', 1), ('io_out_1_bits_vpu_vsew', 'output', 2),
        ('io_out_1_bits_vpu_vm', 'output', 1), ('io_out_1_bits_vpu_vuopIdx', 'output', 7),
        ('io_out_1_bits_vpu_isExt', 'output', 1), ('io_out_1_bits_vpu_isNarrow', 'output', 1),
        ('io_out_1_bits_vpu_isDstMask', 'output', 1),
    ),
    'Dispatcher_16': (
        ('io_in_valid', 'input', 1), ('io_in_bits_fuType', 'input', 35), ('io_in_bits_fuOpType', 'input', 9),
        ('io_in_bits_vpu_vsew', 'input', 2), ('io_in_bits_vpu_vlmul', 'input', 3), ('io_in_bits_vpu_vm', 'input', 1),
        ('io_in_bits_vpu_fpu_isFoldTo1_2', 'input', 1), ('io_in_bits_vpu_fpu_isFoldTo1_4', 'input', 1),
        ('io_in_bits_vpu_fpu_isFoldTo1_8', 'input', 1), ('io_in_bits_vpu_vuopIdx', 'input', 7),
        ('io_out_0_valid', 'output', 1), ('io_out_0_bits_fuOpType', 'output', 9),
        ('io_out_0_bits_vpu_vsew', 'output', 2), ('io_out_0_bits_vpu_vlmul', 'output', 3),
        ('io_out_0_bits_vpu_vm', 'output', 1), ('io_out_0_bits_vpu_fpu_isFoldTo1_2', 'output', 1),
        ('io_out_0_bits_vpu_fpu_isFoldTo1_4', 'output', 1), ('io_out_0_bits_vpu_fpu_isFoldTo1_8', 'output', 1),
        ('io_out_0_bits_vpu_vuopIdx', 'output', 7),
    ),
    'Dispatcher_17': (
        ('io_in_ready', 'output', 1), ('io_in_valid', 'input', 1), ('io_in_bits_fuType', 'input', 35),
        ('io_in_bits_fuOpType', 'input', 9), ('io_in_bits_robIdx_flag', 'input', 1),
        ('io_in_bits_robIdx_value', 'input', 8), ('io_in_bits_pdest', 'input', 7), ('io_in_bits_vecWen', 'input', 1),
        ('io_in_bits_v0Wen', 'input', 1), ('io_in_bits_fpu_wflags', 'input', 1), ('io_in_bits_vpu_vma', 'input', 1),
        ('io_in_bits_vpu_vta', 'input', 1), ('io_in_bits_vpu_vsew', 'input', 2), ('io_in_bits_vpu_vlmul', 'input', 3),
        ('io_in_bits_vpu_vm', 'input', 1), ('io_in_bits_vpu_vstart', 'input', 8),
        ('io_in_bits_vpu_vuopIdx', 'input', 7), ('io_in_bits_vpu_isNarrow', 'input', 1),
        ('io_in_bits_vpu_isDstMask', 'input', 1), ('io_out_0_ready', 'input', 1), ('io_out_0_valid', 'output', 1),
        ('io_out_0_bits_fuOpType', 'output', 9), ('io_out_0_bits_robIdx_flag', 'output', 1),
        ('io_out_0_bits_robIdx_value', 'output', 8), ('io_out_0_bits_pdest', 'output', 7),
        ('io_out_0_bits_vecWen', 'output', 1), ('io_out_0_bits_v0Wen', 'output', 1),
        ('io_out_0_bits_fpu_wflags', 'output', 1), ('io_out_0_bits_vpu_vma', 'output', 1),
        ('io_out_0_bits_vpu_vta', 'output', 1), ('io_out_0_bits_vpu_vsew', 'output', 2),
        ('io_out_0_bits_vpu_vlmul', 'output', 3), ('io_out_0_bits_vpu_vm', 'output', 1),
        ('io_out_0_bits_vpu_vstart', 'output', 8), ('io_out_0_bits_vpu_vuopIdx', 'output', 7),
        ('io_out_0_bits_vpu_isNarrow', 'output', 1), ('io_out_0_bits_vpu_isDstMask', 'output', 1),
        ('io_out_1_ready', 'input', 1), ('io_out_1_valid', 'output', 1), ('io_out_1_bits_fuOpType', 'output', 9),
        ('io_out_1_bits_robIdx_flag', 'output', 1), ('io_out_1_bits_robIdx_value', 'output', 8),
        ('io_out_1_bits_pdest', 'output', 7), ('io_out_1_bits_vecWen', 'output', 1),
        ('io_out_1_bits_v0Wen', 'output', 1), ('io_out_1_bits_vpu_vma', 'output', 1),
        ('io_out_1_bits_vpu_vta', 'output', 1), ('io_out_1_bits_vpu_vsew', 'output', 2),
        ('io_out_1_bits_vpu_vm', 'output', 1), ('io_out_1_bits_vpu_vstart', 'output', 8),
        ('io_out_1_bits_vpu_vuopIdx', 'output', 7), ('io_out_1_bits_vpu_isNarrow', 'output', 1),
        ('io_out_1_bits_vpu_isDstMask', 'output', 1),
    ),
    'ExeUnit': (
        ('clock', 'input', 1), ('reset', 'input', 1), ('io_flush_valid', 'input', 1),
        ('io_flush_bits_robIdx_flag', 'input', 1), ('io_flush_bits_robIdx_value', 'input', 8),
        ('io_flush_bits_level', 'input', 1), ('io_in_valid', 'input', 1), ('io_in_bits_fuType', 'input', 35),
        ('io_in_bits_fuOpType', 'input', 9), ('io_in_bits_src_0', 'input', 64), ('io_in_bits_src_1', 'input', 64),
        ('io_in_bits_robIdx_flag', 'input', 1), ('io_in_bits_robIdx_value', 'input', 8),
        ('io_in_bits_pdest', 'input', 8), ('io_in_bits_rfWen', 'input', 1), ('io_out_valid', 'output', 1),
        ('io_out_bits_data_0', 'output', 64), ('io_out_bits_data_1', 'output', 64), ('io_out_bits_pdest', 'output', 8),
        ('io_out_bits_robIdx_flag', 'output', 1), ('io_out_bits_robIdx_value', 'output', 8),
        ('io_out_bits_intWen', 'output', 1), ('cg_bore_cgen', 'input', 1), ('cg_bore_1_cgen', 'input', 1),
    ),
    'MemExeUnit': (
        ('io_in_ready', 'output', 1), ('io_in_valid', 'input', 1), ('io_in_bits_uop_fuType', 'input', 35),
        ('io_in_bits_uop_fuOpType', 'input', 9), ('io_in_bits_uop_robIdx_value', 'input', 8),
        ('io_in_bits_uop_sqIdx_flag', 'input', 1), ('io_in_bits_uop_sqIdx_value', 'input', 6),
        ('io_in_bits_src_0', 'input', 64), ('io_out_ready', 'input', 1), ('io_out_valid', 'output', 1),
        ('io_out_bits_uop_fuType', 'output', 35), ('io_out_bits_uop_fuOpType', 'output', 9),
        ('io_out_bits_uop_robIdx_value', 'output', 8), ('io_out_bits_uop_sqIdx_flag', 'output', 1),
        ('io_out_bits_uop_sqIdx_value', 'output', 6), ('io_out_bits_data', 'output', 64),
    ),
    'Bku': (
        ('clock', 'input', 1), ('reset', 'input', 1), ('io_in_valid', 'input', 1),
        ('io_in_bits_ctrl_fuOpType', 'input', 9), ('io_in_bits_ctrlPipe_2_robIdx_flag', 'input', 1),
        ('io_in_bits_ctrlPipe_2_robIdx_value', 'input', 8), ('io_in_bits_ctrlPipe_2_pdest', 'input', 8),
        ('io_in_bits_ctrlPipe_2_rfWen', 'input', 1), ('io_in_bits_validPipe_0', 'input', 1),
        ('io_in_bits_validPipe_1', 'input', 1), ('io_in_bits_validPipe_2', 'input', 1),
        ('io_in_bits_data_src_1', 'input', 64), ('io_in_bits_data_src_0', 'input', 64), ('io_out_valid', 'output', 1),
        ('io_out_bits_ctrl_robIdx_flag', 'output', 1), ('io_out_bits_ctrl_robIdx_value', 'output', 8),
        ('io_out_bits_ctrl_pdest', 'output', 8), ('io_out_bits_ctrl_rfWen', 'output', 1),
        ('io_out_bits_res_data', 'output', 64),
    ),
    'CountModule': (
        ('clock', 'input', 1), ('io_src', 'input', 64), ('io_func', 'input', 9), ('io_regEnable', 'input', 1),
        ('io_out', 'output', 64),
    ),
    'ClmulModule': (
        ('clock', 'input', 1), ('io_src_0', 'input', 64), ('io_src_1', 'input', 64), ('io_func', 'input', 9),
        ('io_regEnable', 'input', 1), ('io_out', 'output', 64),
    ),
    'MiscModule': (
        ('clock', 'input', 1), ('io_src_0', 'input', 64), ('io_src_1', 'input', 64), ('io_func', 'input', 9),
        ('io_regEnable', 'input', 1), ('io_out', 'output', 64),
    ),
    'HashModule': (
        ('clock', 'input', 1), ('io_src', 'input', 64), ('io_func', 'input', 9), ('io_regEnable', 'input', 1),
        ('io_out', 'output', 64),
    ),
    'BlockCipherModule': (
        ('clock', 'input', 1), ('io_src_0', 'input', 64), ('io_src_1', 'input', 64), ('io_func', 'input', 9),
        ('io_regEnable', 'input', 1), ('io_out', 'output', 64),
    ),
    'CryptoModule': (
        ('clock', 'input', 1), ('io_src_0', 'input', 64), ('io_src_1', 'input', 64), ('io_func', 'input', 9),
        ('io_regEnable', 'input', 1), ('io_out', 'output', 64),
    ),
    'AddrAddModule': (
        ('io_pcExtend', 'input', 51), ('io_taken', 'input', 1), ('io_imm', 'input', 32), ('io_target', 'output', 64),
        ('io_nextPcOffset', 'input', 5),
    ),
    'Std': (
        ('io_in_ready', 'output', 1), ('io_in_valid', 'input', 1), ('io_in_bits_ctrl_robIdx_value', 'input', 8),
        ('io_in_bits_data_src_0', 'input', 64), ('io_out_ready', 'input', 1), ('io_out_valid', 'output', 1),
        ('io_out_bits_ctrl_robIdx_value', 'output', 8), ('io_out_bits_res_data', 'output', 64),
    ),
    'Fence': (
        ('clock', 'input', 1), ('reset', 'input', 1), ('io_in_ready', 'output', 1), ('io_in_valid', 'input', 1),
        ('io_in_bits_ctrl_fuOpType', 'input', 9), ('io_in_bits_ctrl_robIdx_flag', 'input', 1),
        ('io_in_bits_ctrl_robIdx_value', 'input', 8), ('io_in_bits_ctrl_pdest', 'input', 8),
        ('io_in_bits_ctrl_flushPipe', 'input', 1), ('io_in_bits_data_src_1', 'input', 64),
        ('io_in_bits_data_src_0', 'input', 64), ('io_in_bits_data_imm', 'input', 64), ('io_out_ready', 'input', 1),
        ('io_out_valid', 'output', 1), ('io_out_bits_ctrl_robIdx_flag', 'output', 1),
        ('io_out_bits_ctrl_robIdx_value', 'output', 8), ('io_out_bits_ctrl_pdest', 'output', 8),
        ('io_out_bits_ctrl_flushPipe', 'output', 1), ('io_out_bits_res_data', 'output', 64),
        ('io_fenceio_sfence_valid', 'output', 1), ('io_fenceio_sfence_bits_rs1', 'output', 1),
        ('io_fenceio_sfence_bits_rs2', 'output', 1), ('io_fenceio_sfence_bits_addr', 'output', 50),
        ('io_fenceio_sfence_bits_id', 'output', 16), ('io_fenceio_sfence_bits_flushPipe', 'output', 1),
        ('io_fenceio_sfence_bits_hv', 'output', 1), ('io_fenceio_sfence_bits_hg', 'output', 1),
        ('io_fenceio_fencei', 'output', 1), ('io_fenceio_sbuffer_flushSb', 'output', 1),
        ('io_fenceio_sbuffer_sbIsEmpty', 'input', 1),
    ),
    'Alu': (
        ('io_in_valid', 'input', 1), ('io_in_bits_ctrl_fuOpType', 'input', 9),
        ('io_in_bits_ctrlPipe_0_robIdx_flag', 'input', 1), ('io_in_bits_ctrlPipe_0_robIdx_value', 'input', 8),
        ('io_in_bits_ctrlPipe_0_pdest', 'input', 8), ('io_in_bits_ctrlPipe_0_rfWen', 'input', 1),
        ('io_in_bits_data_src_1', 'input', 64), ('io_in_bits_data_src_0', 'input', 64), ('io_out_valid', 'output', 1),
        ('io_out_bits_ctrl_robIdx_flag', 'output', 1), ('io_out_bits_ctrl_robIdx_value', 'output', 8),
        ('io_out_bits_ctrl_pdest', 'output', 8), ('io_out_bits_ctrl_rfWen', 'output', 1),
        ('io_out_bits_res_data', 'output', 64),
    ),
    'MulUnit': (
        ('clock', 'input', 1), ('reset', 'input', 1), ('io_in_valid', 'input', 1),
        ('io_in_bits_ctrl_fuOpType', 'input', 9), ('io_in_bits_ctrlPipe_2_robIdx_flag', 'input', 1),
        ('io_in_bits_ctrlPipe_2_robIdx_value', 'input', 8), ('io_in_bits_ctrlPipe_2_pdest', 'input', 8),
        ('io_in_bits_ctrlPipe_2_rfWen', 'input', 1), ('io_in_bits_validPipe_0', 'input', 1),
        ('io_in_bits_validPipe_1', 'input', 1), ('io_in_bits_validPipe_2', 'input', 1),
        ('io_in_bits_data_src_1', 'input', 64), ('io_in_bits_data_src_0', 'input', 64), ('io_out_valid', 'output', 1),
        ('io_out_bits_ctrl_robIdx_flag', 'output', 1), ('io_out_bits_ctrl_robIdx_value', 'output', 8),
        ('io_out_bits_ctrl_pdest', 'output', 8), ('io_out_bits_ctrl_rfWen', 'output', 1),
        ('io_out_bits_res_data', 'output', 64),
    ),
    'DivUnit': (
        ('clock', 'input', 1), ('reset', 'input', 1), ('io_flush_valid', 'input', 1),
        ('io_flush_bits_robIdx_flag', 'input', 1), ('io_flush_bits_robIdx_value', 'input', 8),
        ('io_flush_bits_level', 'input', 1), ('io_in_ready', 'output', 1), ('io_in_valid', 'input', 1),
        ('io_in_bits_ctrl_fuOpType', 'input', 9), ('io_in_bits_ctrl_robIdx_flag', 'input', 1),
        ('io_in_bits_ctrl_robIdx_value', 'input', 8), ('io_in_bits_ctrl_pdest', 'input', 8),
        ('io_in_bits_ctrl_rfWen', 'input', 1), ('io_in_bits_data_src_1', 'input', 64),
        ('io_in_bits_data_src_0', 'input', 64), ('io_out_ready', 'input', 1), ('io_out_valid', 'output', 1),
        ('io_out_bits_ctrl_robIdx_flag', 'output', 1), ('io_out_bits_ctrl_robIdx_value', 'output', 8),
        ('io_out_bits_ctrl_pdest', 'output', 8), ('io_out_bits_ctrl_rfWen', 'output', 1),
        ('io_out_bits_res_data', 'output', 64),
    ),
    'BranchUnit': (
        ('io_in_valid', 'input', 1), ('io_in_bits_ctrl_fuOpType', 'input', 9),
        ('io_in_bits_ctrl_robIdx_flag', 'input', 1), ('io_in_bits_ctrl_robIdx_value', 'input', 8),
        ('io_in_bits_ctrl_pdest', 'input', 8), ('io_in_bits_ctrl_ftqIdx_flag', 'input', 1),
        ('io_in_bits_ctrl_ftqIdx_value', 'input', 6), ('io_in_bits_ctrl_ftqOffset', 'input', 4),
        ('io_in_bits_ctrl_predictInfo_taken', 'input', 1), ('io_in_bits_data_src_1', 'input', 64),
        ('io_in_bits_data_src_0', 'input', 64), ('io_in_bits_data_imm', 'input', 64),
        ('io_in_bits_data_pc', 'input', 50), ('io_in_bits_data_nextPcOffset', 'input', 5),
        ('io_out_valid', 'output', 1), ('io_out_bits_ctrl_robIdx_flag', 'output', 1),
        ('io_out_bits_ctrl_robIdx_value', 'output', 8), ('io_out_bits_ctrl_pdest', 'output', 8),
        ('io_out_bits_res_data', 'output', 64), ('io_out_bits_res_redirect_valid', 'output', 1),
        ('io_out_bits_res_redirect_bits_isRVC', 'output', 1),
        ('io_out_bits_res_redirect_bits_robIdx_flag', 'output', 1),
        ('io_out_bits_res_redirect_bits_robIdx_value', 'output', 8),
        ('io_out_bits_res_redirect_bits_ftqIdx_flag', 'output', 1),
        ('io_out_bits_res_redirect_bits_ftqIdx_value', 'output', 6),
        ('io_out_bits_res_redirect_bits_ftqOffset', 'output', 4), ('io_out_bits_res_redirect_bits_level', 'output', 1),
        ('io_out_bits_res_redirect_bits_interrupt', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_pc', 'output', 50),
        ('io_out_bits_res_redirect_bits_cfiUpdate_pd_valid', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_pd_isRVC', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_pd_brType', 'output', 2),
        ('io_out_bits_res_redirect_bits_cfiUpdate_pd_isCall', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_pd_isRet', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_ssp', 'output', 4),
        ('io_out_bits_res_redirect_bits_cfiUpdate_sctr', 'output', 3),
        ('io_out_bits_res_redirect_bits_cfiUpdate_TOSW_flag', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_TOSW_value', 'output', 5),
        ('io_out_bits_res_redirect_bits_cfiUpdate_TOSR_flag', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_TOSR_value', 'output', 5),
        ('io_out_bits_res_redirect_bits_cfiUpdate_NOS_flag', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_NOS_value', 'output', 5),
        ('io_out_bits_res_redirect_bits_cfiUpdate_topAddr', 'output', 50),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_17_folded_hist', 'output', 11),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_16_folded_hist', 'output', 11),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_15_folded_hist', 'output', 7),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_14_folded_hist', 'output', 8),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_13_folded_hist', 'output', 9),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_12_folded_hist', 'output', 4),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_11_folded_hist', 'output', 8),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_10_folded_hist', 'output', 9),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_9_folded_hist', 'output', 7),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_8_folded_hist', 'output', 8),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_7_folded_hist', 'output', 7),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_6_folded_hist', 'output', 9),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_5_folded_hist', 'output', 7),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_4_folded_hist', 'output', 8),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_3_folded_hist', 'output', 8),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_2_folded_hist', 'output', 8),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_1_folded_hist', 'output', 11),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_0_folded_hist', 'output', 8),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_5_bits_0', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_5_bits_1', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_5_bits_2', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_5_bits_3', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_4_bits_0', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_4_bits_1', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_4_bits_2', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_4_bits_3', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_3_bits_0', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_3_bits_1', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_3_bits_2', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_3_bits_3', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_2_bits_0', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_2_bits_1', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_2_bits_2', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_2_bits_3', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_1_bits_0', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_1_bits_1', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_1_bits_2', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_1_bits_3', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_0_bits_0', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_0_bits_1', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_0_bits_2', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_0_bits_3', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_lastBrNumOH', 'output', 3),
        ('io_out_bits_res_redirect_bits_cfiUpdate_ghr', 'output', 4),
        ('io_out_bits_res_redirect_bits_cfiUpdate_histPtr_flag', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_histPtr_value', 'output', 8),
        ('io_out_bits_res_redirect_bits_cfiUpdate_specCnt_0', 'output', 10),
        ('io_out_bits_res_redirect_bits_cfiUpdate_specCnt_1', 'output', 10),
        ('io_out_bits_res_redirect_bits_cfiUpdate_br_hit', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_jr_hit', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_sc_hit', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_predTaken', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_target', 'output', 50),
        ('io_out_bits_res_redirect_bits_cfiUpdate_taken', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_isMisPred', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_shift', 'output', 2),
        ('io_out_bits_res_redirect_bits_cfiUpdate_addIntoHist', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_backendIGPF', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_backendIPF', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_backendIAF', 'output', 1),
        ('io_out_bits_res_redirect_bits_fullTarget', 'output', 64),
        ('io_out_bits_res_redirect_bits_satpFlush', 'output', 1),
        ('io_out_bits_res_redirect_bits_isVlsException', 'output', 1),
        ('io_out_bits_res_redirect_bits_stFtqIdx_flag', 'output', 1),
        ('io_out_bits_res_redirect_bits_stFtqIdx_value', 'output', 6),
        ('io_out_bits_res_redirect_bits_stFtqOffset', 'output', 4),
        ('io_out_bits_res_redirect_bits_debug_runahead_checkpoint_id', 'output', 64),
        ('io_out_bits_res_redirect_bits_debugIsCtrl', 'output', 1),
        ('io_out_bits_res_redirect_bits_debugIsMemVio', 'output', 1), ('io_instrAddrTransType_bare', 'input', 1),
        ('io_instrAddrTransType_sv39', 'input', 1), ('io_instrAddrTransType_sv39x4', 'input', 1),
        ('io_instrAddrTransType_sv48', 'input', 1), ('io_instrAddrTransType_sv48x4', 'input', 1),
    ),
    'JumpUnit': (
        ('io_in_valid', 'input', 1), ('io_in_bits_ctrl_fuOpType', 'input', 9),
        ('io_in_bits_ctrl_robIdx_flag', 'input', 1), ('io_in_bits_ctrl_robIdx_value', 'input', 8),
        ('io_in_bits_ctrl_pdest', 'input', 8), ('io_in_bits_ctrl_rfWen', 'input', 1),
        ('io_in_bits_ctrl_ftqIdx_flag', 'input', 1), ('io_in_bits_ctrl_ftqIdx_value', 'input', 6),
        ('io_in_bits_ctrl_ftqOffset', 'input', 4), ('io_in_bits_ctrl_predictInfo_target', 'input', 50),
        ('io_in_bits_ctrl_predictInfo_taken', 'input', 1), ('io_in_bits_data_src_0', 'input', 64),
        ('io_in_bits_data_imm', 'input', 64), ('io_in_bits_data_pc', 'input', 50),
        ('io_in_bits_data_nextPcOffset', 'input', 5), ('io_out_valid', 'output', 1),
        ('io_out_bits_ctrl_robIdx_flag', 'output', 1), ('io_out_bits_ctrl_robIdx_value', 'output', 8),
        ('io_out_bits_ctrl_pdest', 'output', 8), ('io_out_bits_ctrl_rfWen', 'output', 1),
        ('io_out_bits_res_data', 'output', 64), ('io_out_bits_res_redirect_valid', 'output', 1),
        ('io_out_bits_res_redirect_bits_isRVC', 'output', 1),
        ('io_out_bits_res_redirect_bits_robIdx_flag', 'output', 1),
        ('io_out_bits_res_redirect_bits_robIdx_value', 'output', 8),
        ('io_out_bits_res_redirect_bits_ftqIdx_flag', 'output', 1),
        ('io_out_bits_res_redirect_bits_ftqIdx_value', 'output', 6),
        ('io_out_bits_res_redirect_bits_ftqOffset', 'output', 4), ('io_out_bits_res_redirect_bits_level', 'output', 1),
        ('io_out_bits_res_redirect_bits_interrupt', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_pc', 'output', 50),
        ('io_out_bits_res_redirect_bits_cfiUpdate_pd_valid', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_pd_isRVC', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_pd_brType', 'output', 2),
        ('io_out_bits_res_redirect_bits_cfiUpdate_pd_isCall', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_pd_isRet', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_ssp', 'output', 4),
        ('io_out_bits_res_redirect_bits_cfiUpdate_sctr', 'output', 3),
        ('io_out_bits_res_redirect_bits_cfiUpdate_TOSW_flag', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_TOSW_value', 'output', 5),
        ('io_out_bits_res_redirect_bits_cfiUpdate_TOSR_flag', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_TOSR_value', 'output', 5),
        ('io_out_bits_res_redirect_bits_cfiUpdate_NOS_flag', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_NOS_value', 'output', 5),
        ('io_out_bits_res_redirect_bits_cfiUpdate_topAddr', 'output', 50),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_17_folded_hist', 'output', 11),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_16_folded_hist', 'output', 11),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_15_folded_hist', 'output', 7),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_14_folded_hist', 'output', 8),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_13_folded_hist', 'output', 9),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_12_folded_hist', 'output', 4),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_11_folded_hist', 'output', 8),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_10_folded_hist', 'output', 9),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_9_folded_hist', 'output', 7),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_8_folded_hist', 'output', 8),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_7_folded_hist', 'output', 7),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_6_folded_hist', 'output', 9),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_5_folded_hist', 'output', 7),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_4_folded_hist', 'output', 8),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_3_folded_hist', 'output', 8),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_2_folded_hist', 'output', 8),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_1_folded_hist', 'output', 11),
        ('io_out_bits_res_redirect_bits_cfiUpdate_folded_hist_hist_0_folded_hist', 'output', 8),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_5_bits_0', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_5_bits_1', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_5_bits_2', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_5_bits_3', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_4_bits_0', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_4_bits_1', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_4_bits_2', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_4_bits_3', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_3_bits_0', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_3_bits_1', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_3_bits_2', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_3_bits_3', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_2_bits_0', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_2_bits_1', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_2_bits_2', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_2_bits_3', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_1_bits_0', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_1_bits_1', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_1_bits_2', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_1_bits_3', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_0_bits_0', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_0_bits_1', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_0_bits_2', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_afhob_afhob_0_bits_3', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_lastBrNumOH', 'output', 3),
        ('io_out_bits_res_redirect_bits_cfiUpdate_ghr', 'output', 4),
        ('io_out_bits_res_redirect_bits_cfiUpdate_histPtr_flag', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_histPtr_value', 'output', 8),
        ('io_out_bits_res_redirect_bits_cfiUpdate_specCnt_0', 'output', 10),
        ('io_out_bits_res_redirect_bits_cfiUpdate_specCnt_1', 'output', 10),
        ('io_out_bits_res_redirect_bits_cfiUpdate_br_hit', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_jr_hit', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_sc_hit', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_predTaken', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_target', 'output', 50),
        ('io_out_bits_res_redirect_bits_cfiUpdate_taken', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_isMisPred', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_shift', 'output', 2),
        ('io_out_bits_res_redirect_bits_cfiUpdate_addIntoHist', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_backendIGPF', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_backendIPF', 'output', 1),
        ('io_out_bits_res_redirect_bits_cfiUpdate_backendIAF', 'output', 1),
        ('io_out_bits_res_redirect_bits_fullTarget', 'output', 64),
        ('io_out_bits_res_redirect_bits_satpFlush', 'output', 1),
        ('io_out_bits_res_redirect_bits_isVlsException', 'output', 1),
        ('io_out_bits_res_redirect_bits_stFtqIdx_flag', 'output', 1),
        ('io_out_bits_res_redirect_bits_stFtqIdx_value', 'output', 6),
        ('io_out_bits_res_redirect_bits_stFtqOffset', 'output', 4),
        ('io_out_bits_res_redirect_bits_debug_runahead_checkpoint_id', 'output', 64),
        ('io_out_bits_res_redirect_bits_debugIsCtrl', 'output', 1),
        ('io_out_bits_res_redirect_bits_debugIsMemVio', 'output', 1), ('io_instrAddrTransType_bare', 'input', 1),
        ('io_instrAddrTransType_sv39', 'input', 1), ('io_instrAddrTransType_sv39x4', 'input', 1),
        ('io_instrAddrTransType_sv48', 'input', 1), ('io_instrAddrTransType_sv48x4', 'input', 1),
    ),
}

# Covered locked module names in declaration order. / 覆盖的锁定模块名（声明序）。
COVERED_MODULES = (
    'Dispatcher',
    'Dispatcher_1',
    'Dispatcher_4',
    'Dispatcher_5',
    'Dispatcher_7',
    'Dispatcher_8',
    'Dispatcher_9',
    'Dispatcher_10',
    'Dispatcher_13',
    'Dispatcher_14',
    'Dispatcher_15',
    'Dispatcher_16',
    'Dispatcher_17',
    'ExeUnit',
    'MemExeUnit',
    'Bku',
    'CountModule',
    'ClmulModule',
    'MiscModule',
    'HashModule',
    'BlockCipherModule',
    'CryptoModule',
    'AddrAddModule',
    'Std',
    'Fence',
    'Alu',
    'MulUnit',
    'DivUnit',
    'BranchUnit',
    'JumpUnit',
)

# =============================================================================
# Configuration
# =============================================================================
# One locked port ``(name, direction, width)`` triple. / 一个锁定端口 ``(名称, 方向, 宽度)`` 三元组。
@dataclass(frozen=True)
class PortSpec:
    name: str
    direction: str
    width: int


# Pinned pipeline latency per module, from the FuncUnit cfg.latency geometry.
# 每个模块的钉死流水线延迟，来自 FuncUnit cfg.latency 几何。
LATENCY: dict[str, int] = {
    "Bku": 2, "MulUnit": 2, "DivUnit": 0,
    "CountModule": 1, "ClmulModule": 1, "MiscModule": 1, "HashModule": 1,
    "BlockCipherModule": 1, "CryptoModule": 1,
    "Alu": 0, "AddrAddModule": 0, "Std": 0, "Fence": 0,
    "Dispatcher": 0, "ExeUnit": 0, "MemExeUnit": 0, "BranchUnit": 0, "JumpUnit": 0,
}
LATENCY.update({k: 0 for k in COVERED_MODULES if k not in LATENCY})

def module_ports(name: str) -> tuple[tuple[str, str, int], ...]:
    """Return the locked ``(name, direction, width)`` tuples of ``name``. / 返回 ``name`` 的锁定端口三元组。"""
    return PORTS[name]

def module_latency(name: str) -> int:
    """Return the pinned pipeline latency of ``name``. / 返回 ``name`` 的钉死流水线延迟。"""
    return LATENCY.get(name, 0)


# =============================================================================
# Implementation
# =============================================================================
def _zext(x: Value, total: int) -> Value:
    # Zero-extend an expression to ``total`` bits. / 将表达式零扩展至 ``total`` 位。
    return cast(Value, Cat(x, Const(0, total - len(x))))


def _sext(x: Value, total: int) -> Value:
    # Sign-extend an expression to ``total`` bits. / 将表达式符号扩展至 ``total`` 位。
    return cast(Value, Cat(x, x[len(x) - 1].replicate(total - len(x))))


def _pad(x: Value, width: int) -> Value:
    # Zero-pad an expression to exactly ``width`` bits for wide addition. / 将表达式零填充至 ``width`` 位以便宽位加法。
    return cast(Value, x if len(x) >= width else Cat(x, Const(0, width - len(x))))


def _or_reduce(v: Value) -> Value:
    # OR-reduce a value to one bit. / 将值或归约为一位。
    val = v
    acc = val[0:1]
    for i in range(1, len(val)):
        acc = acc | val[i:i + 1]
    return acc


def _bit_reverse(v: Value, width: int) -> Value:
    # Reverse the bit order of ``v``. / 反转 ``v`` 的位序。
    bits = [v[i:i + 1] for i in range(width)]
    bits.reverse()
    return Cat(*bits)


def _ror32(x: Value, shamt: int) -> Value:
    # 32-bit rotate encoded like CryptoUtils.ROR32 (low 32 bits valid). / 仿 CryptoUtils.ROR32 的 32 位旋转（低 32 位有效）。
    v = x[0:32]
    return cast(Value, Cat(Const(0, 32), v[0:shamt], v[shamt:32]))


def _ror64(x: Value, shamt: int) -> Value:
    # 64-bit rotate-right like CryptoUtils.ROR64. / 仿 CryptoUtils.ROR64 的 64 位旋转。
    return cast(Value, Cat(x[0:shamt], x[shamt:64]))


def _popcount16(v: Value) -> Value:
    # Popcount of a 16-bit group into 5 bits. / 求 16 位组的置位数（5 位）。
    total = Const(0, 5)
    for i in range(16):
        total = cast(Value, total + _pad(v[i:i + 1], 5))
    return cast(Value, total)


def _clz_tree(v: Value, n: int) -> Value:
    # Hierarchical leading-zero count of an n-bit value (n a power of two),
    # matching Bku.scala clzi/encode.  Result width is n.bit_length() + 1.
    # 与 Bku.scala clzi/encode 一致的分层前导零计数（n 为 2 的幂），
    # 结果宽度为 n.bit_length() + 1。
    val = v
    if n == 1:
        return val[0:1]
    half = n // 2
    left = _clz_tree(val[half:n], half)
    right = _clz_tree(val[0:half], half)
    sel = _or_reduce(val[half:n])
    hi = left[half - 1:half] & right[half - 1:half]
    not_msb = ~right[half - 1:half]
    if half == 1:
        merged = Cat(right[0:1], not_msb, hi)
    else:
        merged = Cat(right[0:half], not_msb, hi)
    return cast(Value, Mux(sel, merged, left))


def _xperm_lut(table, idx, width):
    # MiscModule.xpermLUT: select one ``width``-bit lane of ``table`` by ``idx``.
    # MiscModule.xpermLUT：按 ``idx`` 从 ``table`` 中选择一个 ``width`` 位泳道。
    entries = 64 // width
    result = Const(0, width)
    for i in range(entries):
        result = Mux(cast(Any, idx) == i, cast(Any, table)[i * width:i * width + width], result)
    return result


def sbox_aes_top(m: Any, byte: Value, prefix: str):
    # CryptoUtils.SboxAesTop: first stage of the AES S-box network. / CryptoUtils.SboxAesTop：AES S-box 网络第一级。
    i = cast(Any, byte)
    o = _SignalDict(m, 'aesTop')
    o[0] = i[0:1]
    o[1] = i[7:8] ^ i[4:5]
    o[2] = i[7:8] ^ i[2:3]
    o[3] = i[7:8] ^ i[1:2]
    o[4] = i[4:5] ^ i[2:3]
    t0 = i[3:4] ^ i[1:2]
    t1 = i[6:7] ^ i[5:6]
    t2 = i[6:7] ^ i[2:3]
    t3 = i[5:6] ^ i[2:3]
    t4 = i[4:5] ^ i[0:1]
    t5 = i[1:2] ^ i[0:1]
    o[5] = o[1] ^ t0
    o[6] = i[0:1] ^ o[5]
    o[7] = i[0:1] ^ t1
    o[8] = o[5] ^ t1
    o[9] = o[3] ^ o[4]
    o[10] = o[5] ^ t2
    o[11] = t0 ^ t2
    o[12] = t0 ^ t3
    o[13] = o[7] ^ o[12]
    o[14] = t1 ^ t4
    o[15] = o[1] ^ o[14]
    o[16] = t1 ^ t5
    o[17] = o[2] ^ o[16]
    o[18] = o[2] ^ o[8]
    o[19] = o[15] ^ o[13]
    o[20] = o[1] ^ t3
    return [o[k] for k in range(21)]


def sbox_iaes_top(m: Any, byte: Value, prefix: str):
    # CryptoUtils.SboxIaesTop: first stage of the AES^-1 S-box network. / CryptoUtils.SboxIaesTop：AES 逆 S-box 网络第一级。
    i = cast(Any, byte)
    t0 = i[1:2] ^ i[0:1]
    t1 = i[6:7] ^ i[1:2]
    t2 = i[5:6] ^ ~i[2:3]
    t3 = i[2:3] ^ ~i[1:2]
    t4 = i[5:6] ^ ~i[3:4]
    o = _SignalDict(m, 'iaesTop')
    o[0] = i[7:8] ^ t2
    o[1] = i[4:5] ^ i[3:4]
    o[2] = i[7:8] ^ ~i[6:7]
    o[3] = o[1] ^ t0
    o[17] = i[7:8] ^ i[4:5]
    o[16] = i[6:7] ^ ~i[4:5]
    o[6] = i[6:7] ^ ~o[17]
    o[4] = i[3:4] ^ o[6]
    o[5] = o[16] ^ t2
    o[7] = i[0:1] ^ ~o[1]
    o[18] = i[3:4] ^ ~i[0:1]
    o[8] = o[2] ^ o[18]
    o[9] = o[2] ^ t0
    o[10] = o[8] ^ t3
    o[20] = o[1] ^ t3
    o[11] = o[8] ^ o[20]
    o[12] = t1 ^ t4
    o[14] = o[16] ^ t0
    o[13] = i[5:6] ^ ~o[14]
    o[15] = o[18] ^ t1
    o[19] = i[5:6] ^ ~o[1]
    return [o[k] for k in range(21)]


def sbox_sm4_top(m: Any, byte: Value, prefix: str):
    # CryptoUtils.SboxSm4Top: first stage of the SM4 S-box network. / CryptoUtils.SboxSm4Top：SM4 S-box 网络第一级。
    i = cast(Any, byte)
    o = _SignalDict(m, 'sm4Top')
    o[18] = i[2:3] ^ i[6:7]
    t0 = i[3:4] ^ i[4:5]
    t1 = i[2:3] ^ i[7:8]
    t2 = i[7:8] ^ o[18]
    t3 = i[1:2] ^ t1
    t4 = i[6:7] ^ i[7:8]
    t5 = i[0:1] ^ o[18]
    t6 = i[3:4] ^ i[6:7]
    o[9] = i[3:4]
    o[10] = i[1:2] ^ o[18]
    o[0] = i[5:6] ^ ~o[10]
    o[1] = t0 ^ t3
    o[2] = i[0:1] ^ t0
    o[4] = i[0:1] ^ t3
    o[3] = i[3:4] ^ o[4]
    o[5] = i[5:6] ^ t5
    o[6] = i[0:1] ^ ~i[1:2]
    o[7] = t0 ^ ~o[10]
    o[8] = t0 ^ t5
    o[11] = t0 ^ t4
    o[12] = i[5:6] ^ t4
    o[13] = i[5:6] ^ ~o[1]
    o[14] = i[4:5] ^ ~t2
    o[15] = i[1:2] ^ ~t6
    o[16] = i[0:1] ^ ~t2
    o[17] = t0 ^ ~t2
    o[19] = i[5:6] ^ ~o[14]
    o[20] = i[0:1] ^ t1
    return [o[k] for k in range(21)]


class _SignalDict(dict):
    # Intermediate-term dict that materialises every value as a 1-bit comb
    # signal, mirroring the Wire(Vec(...)) semantics of the Scala original and
    # keeping the expression trees linear. / 中间项字典：把每个值落地为 1 位
    # 组合信号，对应 Scala 原实现的 Wire(Vec(...)) 语义，使表达式树保持线性。
    def __init__(self, m, prefix):
        super().__init__()
        self._m = m
        self._prefix = prefix

    def __setitem__(self, key, expr):
        sig = Signal(name="%s_t%d" % (self._prefix, key))
        self._m.d.comb += sig.eq(expr)
        dict.__setitem__(self, key, sig)


def sbox_inv(m: Any, bits: Value, prefix: str):
    # CryptoUtils.SboxInv: shared middle stage for AES/AES^-1/SM4. / CryptoUtils.SboxInv：AES/AES 逆/SM4 共享中间级。
    i = [cast(Any, b) for b in bits]
    t = _SignalDict(m, prefix)
    t[0] = i[3] ^ i[12]
    t[1] = i[9] & i[5]
    t[2] = i[17] & i[6]
    t[3] = i[10] ^ t[1]
    t[4] = i[14] & i[0]
    t[5] = t[4] ^ t[1]
    t[6] = i[3] & i[12]
    t[7] = i[16] & i[7]
    t[8] = t[0] ^ t[6]
    t[9] = i[15] & i[13]
    t[10] = t[9] ^ t[6]
    t[11] = i[1] & i[11]
    t[12] = i[4] & i[20]
    t[13] = t[12] ^ t[11]
    t[14] = i[2] & i[8]
    t[15] = t[14] ^ t[11]
    t[16] = t[3] ^ t[2]
    t[17] = t[5] ^ i[18]
    t[18] = t[8] ^ t[7]
    t[19] = t[10] ^ t[15]
    t[20] = t[16] ^ t[13]
    t[21] = t[17] ^ t[15]
    t[22] = t[18] ^ t[13]
    t[23] = t[19] ^ i[19]
    t[24] = t[22] ^ t[23]
    t[25] = t[22] & t[20]
    t[26] = t[21] ^ t[25]
    t[27] = t[20] ^ t[21]
    t[28] = t[23] ^ t[25]
    t[29] = t[28] & t[27]
    t[30] = t[26] & t[24]
    t[31] = t[20] & t[23]
    t[32] = t[27] & t[31]
    t[33] = t[27] ^ t[25]
    t[34] = t[21] & t[22]
    t[35] = t[24] & t[34]
    t[36] = t[24] ^ t[25]
    t[37] = t[21] ^ t[29]
    t[38] = t[32] ^ t[33]
    t[39] = t[23] ^ t[30]
    t[40] = t[35] ^ t[36]
    t[41] = t[38] ^ t[40]
    t[42] = t[37] ^ t[39]
    t[43] = t[37] ^ t[38]
    t[44] = t[39] ^ t[40]
    t[45] = t[42] ^ t[41]
    o = [
        t[38] & i[7], t[37] & i[13], t[42] & i[11], t[45] & i[20],
        t[41] & i[8], t[44] & i[9], t[40] & i[17], t[39] & i[14],
        t[43] & i[3], t[38] & i[16], t[37] & i[15], t[42] & i[1],
        t[45] & i[4], t[41] & i[2], t[44] & i[5], t[40] & i[6],
        t[39] & i[0], t[43] & i[12],
    ]
    return o


def sbox_aes_out(m: Any, bits: Value, prefix: str):
    # CryptoUtils.SboxAesOut: output stage of the AES S-box network. / CryptoUtils.SboxAesOut：AES S-box 网络输出级。
    i = [cast(Any, b) for b in bits]
    t = _SignalDict(m, prefix)
    t[0] = i[11] ^ i[12]
    t[1] = i[0] ^ i[6]
    t[2] = i[14] ^ i[16]
    t[3] = i[15] ^ i[5]
    t[4] = i[4] ^ i[8]
    t[5] = i[17] ^ i[11]
    t[6] = i[12] ^ t[5]
    t[7] = i[14] ^ t[3]
    t[8] = i[1] ^ i[9]
    t[9] = i[2] ^ i[3]
    t[10] = i[3] ^ t[4]
    t[11] = i[10] ^ t[2]
    t[12] = i[16] ^ i[1]
    t[13] = i[0] ^ t[0]
    t[14] = i[2] ^ i[11]
    t[15] = i[5] ^ t[1]
    t[16] = i[6] ^ t[0]
    t[17] = i[7] ^ t[1]
    t[18] = i[8] ^ t[8]
    t[19] = i[13] ^ t[4]
    t[20] = t[0] ^ t[1]
    t[21] = t[1] ^ t[7]
    t[22] = t[3] ^ t[12]
    t[23] = t[18] ^ t[2]
    t[24] = t[15] ^ t[9]
    t[25] = t[6] ^ t[10]
    t[26] = t[7] ^ t[9]
    t[27] = t[8] ^ t[10]
    t[28] = t[11] ^ t[14]
    t[29] = t[11] ^ t[17]
    o = [
        t[6] ^ ~t[23], t[13] ^ ~t[27], t[25] ^ t[29], t[20] ^ t[22],
        t[6] ^ t[21], t[19] ^ ~t[28], t[16] ^ ~t[26], t[6] ^ t[24],
    ]
    return cast(Any, Cat(*o))


def sbox_iaes_out(m: Any, bits: Value, prefix: str):
    # CryptoUtils.SboxIaesOut: output stage of the AES^-1 S-box network. / CryptoUtils.SboxIaesOut：AES 逆 S-box 网络输出级。
    i = [cast(Any, b) for b in bits]
    t = _SignalDict(m, prefix)
    t[0] = i[2] ^ i[11]
    t[1] = i[8] ^ i[9]
    t[2] = i[4] ^ i[12]
    t[3] = i[15] ^ i[0]
    t[4] = i[16] ^ i[6]
    t[5] = i[14] ^ i[1]
    t[6] = i[17] ^ i[10]
    t[7] = t[0] ^ t[1]
    t[8] = i[0] ^ i[3]
    t[9] = i[5] ^ i[13]
    t[10] = i[7] ^ t[4]
    t[11] = t[0] ^ t[3]
    t[12] = i[14] ^ i[16]
    t[13] = i[17] ^ i[1]
    t[14] = i[17] ^ i[12]
    t[15] = i[4] ^ i[9]
    t[16] = i[7] ^ i[11]
    t[17] = i[8] ^ t[2]
    t[18] = i[13] ^ t[5]
    t[19] = t[2] ^ t[3]
    t[20] = t[4] ^ t[6]
    t[22] = t[2] ^ t[7]
    t[23] = t[7] ^ t[8]
    t[24] = t[5] ^ t[7]
    t[25] = t[6] ^ t[10]
    t[26] = t[9] ^ t[11]
    t[27] = t[10] ^ t[18]
    t[28] = t[11] ^ t[25]
    t[29] = t[15] ^ t[20]
    o = [
        t[9] ^ t[16], t[14] ^ t[23], t[19] ^ t[24], t[23] ^ t[27],
        t[12] ^ t[22], t[17] ^ t[28], t[26] ^ t[29], t[13] ^ t[22],
    ]
    return cast(Any, Cat(*o))


def sbox_sm4_out(m: Any, bits: Value, prefix: str):
    # CryptoUtils.SboxSm4Out: output stage of the SM4 S-box network. / CryptoUtils.SboxSm4Out：SM4 S-box 网络输出级。
    i = [cast(Any, b) for b in bits]
    t = _SignalDict(m, prefix)
    t[0] = i[4] ^ i[7]
    t[1] = i[13] ^ i[15]
    t[2] = i[2] ^ i[16]
    t[3] = i[6] ^ t[0]
    t[4] = i[12] ^ t[1]
    t[5] = i[9] ^ i[10]
    t[6] = i[11] ^ t[2]
    t[7] = i[1] ^ t[4]
    t[8] = i[0] ^ i[17]
    t[9] = i[3] ^ i[17]
    t[10] = i[8] ^ t[3]
    t[11] = t[2] ^ t[5]
    t[12] = i[14] ^ t[6]
    t[13] = t[7] ^ t[9]
    t[14] = i[0] ^ i[6]
    t[15] = i[7] ^ i[16]
    t[16] = i[5] ^ i[13]
    t[17] = i[3] ^ i[15]
    t[18] = i[10] ^ i[12]
    t[19] = i[9] ^ t[1]
    t[20] = i[4] ^ t[4]
    t[21] = i[14] ^ t[3]
    t[22] = i[16] ^ t[5]
    t[23] = t[7] ^ t[14]
    t[24] = t[8] ^ t[11]
    t[25] = t[0] ^ t[12]
    t[26] = t[17] ^ t[3]
    t[27] = t[18] ^ t[10]
    t[28] = t[19] ^ t[6]
    t[29] = t[8] ^ t[10]
    o = [
        t[11] ^ ~t[13], t[15] ^ ~t[23], t[20] ^ t[24], t[16] ^ t[25],
        t[26] ^ ~t[22], t[21] ^ t[13], t[27] ^ ~t[12], t[28] ^ ~t[29],
    ]
    return cast(Any, Cat(*o))


def xt2(byte: Value) -> Value:
    # CryptoUtils.XtN.Xt2: GF(2^8) multiply by 2. / CryptoUtils.XtN.Xt2：GF(2^8) 乘 2。
    v = cast(Any, byte)
    shifted = (cast(Any, Cat(Const(0, 1), v[0:8])) << 1)[0:9]
    fb = Mux(v[7:8], Const(0x1b, 8), Const(0, 8))
    return cast(Value, (cast(Any, shifted) ^ Cat(Const(0, 1), fb))[0:8])


def xtn(byte: Value, t: Value) -> Value:
    # CryptoUtils.XtN: repeated GF(2^8) doubling selected by mask ``t``. / CryptoUtils.XtN：按掩码 ``t`` 选择的 GF(2^8) 重复倍乘。
    b0 = cast(Any, byte)[0:8]
    b1 = xt2(b0)
    b2 = xt2(b1)
    b3 = xt2(b2)
    res = Mux(t[0:1], b0, Const(0, 8))
    res = res ^ Mux(t[1:2], b1, Const(0, 8))
    res = res ^ Mux(t[2:3], b2, Const(0, 8))
    res = res ^ Mux(t[3:4], b3, Const(0, 8))
    return cast(Value, res[0:8])


def byte_enc(bytes4: list[Value]) -> Value:
    # CryptoUtils.ByteEnc: AES forward mix-column on one column. / CryptoUtils.ByteEnc：一列的 AES 正向列混合。
    return xtn(bytes4[0], Const(0x2, 8)) ^ xtn(bytes4[1], Const(0x3, 8)) ^ bytes4[2] ^ bytes4[3]


def byte_dec(bytes4: list[Value]) -> Value:
    # CryptoUtils.ByteDec: AES inverse mix-column on one column. / CryptoUtils.ByteDec：一列的 AES 逆向列混合。
    return xtn(bytes4[0], Const(0xe, 8)) ^ xtn(bytes4[1], Const(0xb, 8)) ^ xtn(bytes4[2], Const(0xd, 8)) ^ xtn(bytes4[3], Const(0x9, 8))


def mix_fwd(bytes4: list[Value]) -> Value:
    # CryptoUtils.MixFwd over one column group. / 一组列的 CryptoUtils.MixFwd。
    return Cat(
        byte_enc([bytes4[3], bytes4[0], bytes4[1], bytes4[2]]),
        byte_enc([bytes4[2], bytes4[3], bytes4[0], bytes4[1]]),
        byte_enc([bytes4[1], bytes4[2], bytes4[3], bytes4[0]]),
        byte_enc([bytes4[0], bytes4[1], bytes4[2], bytes4[3]]),
    )


def mix_inv(bytes4: list[Value]) -> Value:
    # CryptoUtils.MixInv over one column group. / 一组列的 CryptoUtils.MixInv。
    return Cat(
        byte_dec([bytes4[3], bytes4[0], bytes4[1], bytes4[2]]),
        byte_dec([bytes4[2], bytes4[3], bytes4[0], bytes4[1]]),
        byte_dec([bytes4[1], bytes4[2], bytes4[3], bytes4[0]]),
        byte_dec([bytes4[0], bytes4[1], bytes4[2], bytes4[3]]),
    )


def alu_result(func, src1, src2):
    # Faithful AluDataModule datapath (upstream/src/main/scala/xiangshan/backend/fu/Alu.scala:196).
    # 忠实 AluDataModule 数据通路（upstream/.../fu/Alu.scala:196）。
    f = cast(Any, func)
    s1 = cast(Any, src1)
    s2 = cast(Any, src2)
    shamt = s2[0:6]
    rev_shamt = (~s2[0:6] + Const(1, 6))[0:6]
    sll_mask = Cat(Mux(f[0:1], Const(0xffffffff, 32), Const(0, 32)), Const(0xffffffff, 32))
    sll_src = sll_mask & s1
    sll = sll_src << shamt
    rev_sll = sll_src << rev_shamt
    bit_shift = Const(1, 64) << s2[0:6]
    bclr = s1 & ~bit_shift
    bset = s1 | bit_shift
    binv = s1 ^ bit_shift
    srl = s1 >> shamt
    sra = (s1.as_signed() >> shamt).as_unsigned()
    rev_srl = s1 >> rev_shamt
    bext = srl[0:1]
    rol = rev_srl | sll
    ror = srl | rev_sll
    # addw path. / addw 路径。
    srcw = Mux(~f[2:3] & f[0:1], Mux(f[1:2], _sext(s2[0:12], 64), _zext(s1[0:1], 64)), _zext(s1[0:32], 64))
    addw_raw = (srcw + s2[0:32])[0:32]
    addw_all = (
        _zext(addw_raw[0:1], 64),
        _zext(addw_raw[0:8], 64),
        _zext(addw_raw[0:16], 64),
        _sext(addw_raw[0:16], 64),
    )
    addw = addw_all[3]
    addw = Mux(f[2:3] & f[1:2] & ~f[0:1], addw_all[2], addw)
    addw = Mux(f[2:3] & f[1:2] & f[0:1], addw_all[3], addw)
    addw = Mux(f[2:3] & ~f[1:2] & ~f[0:1], addw_all[0], addw)
    addw = Mux(f[2:3] & ~f[1:2] & f[0:1], addw_all[1], addw)
    addw = Mux(~f[2:3], _zext(addw_raw, 64), addw)
    sub65 = cast(Any, Cat(Const(0, 1), s1)) + cast(Any, Cat(Const(0, 1), ~s2)) + Const(1, 65)
    subw = sub65[0:32]
    sllw = (s1[0:32] << s2[0:5])[0:32]
    rev_sllw = (s1[0:32] << rev_shamt[0:5])[0:32]
    srlw = s1[0:32] >> s2[0:5]
    sraw = (s1[0:32].as_signed() >> s2[0:5]).as_unsigned()
    rev_srlw = s1[0:32] >> rev_shamt[0:5]
    rolw = rev_srlw | sllw
    rorw = srlw | rev_sllw
    # add operand selection (shadd / sradd / lui32 / odd). / 加法操作数选择。
    word_mask = sll_mask & s1
    shadd = (
        Cat(word_mask[0:63], Const(0, 1)),
        Cat(word_mask[0:62], Const(0, 2)),
        Cat(word_mask[0:61], Const(0, 3)),
        Cat(word_mask[0:60], Const(0, 4)),
    )
    sradd = (
        _zext(s1[29:64], 64),
        _zext(s1[30:64], 64),
        _zext(s1[31:64], 64),
        _zext(s1[32:64], 64),
    )
    add_a = word_mask
    add_a = Mux(f[1:2], Mux(f[0:1], _sext(s2[0:12], 64), _zext(s1[0:1], 64)), add_a)
    add_a = Mux(f[2:3], Mux(f[0:2] == 0, sradd[0], Mux(f[0:2] == 1, sradd[1], Mux(f[0:2] == 2, sradd[2], sradd[3]))), add_a)
    add_a = Mux(f[3:4], Mux(f[1:3] == 0, shadd[0], Mux(f[1:3] == 1, shadd[1], Mux(f[1:3] == 2, shadd[2], shadd[3]))), add_a)
    add_b = Mux(f[0:4] == Const(0b0011, 4), Cat(s2[12:64], Const(0, 12)), s2)
    add = add_a + add_b
    sltu = cast(Any, ~sub65[64:65])
    slt = cast(Any, s1[63:64]) ^ cast(Any, s2[63:64]) ^ sltu
    max_min = Mux(slt ^ f[0:1], s2, s1)
    max_min_u = Mux(sltu ^ f[0:1], s2, s1)
    compare_res = Mux(f[2:3], Mux(f[1:2], max_min, max_min_u), Mux(f[1:2], _zext(slt, 64), Mux(f[0:1], _zext(sltu, 64), sub65[0:64])))
    logic_src2 = Mux(~f[5:6] & f[0:1], ~s2, s2)
    and_r = s1 & logic_src2
    or_r = s1 | logic_src2
    xor_r = s1 ^ logic_src2
    orcb = Cat(*[_pad(Mux(_or_reduce(s1[i * 8:i * 8 + 8]), Const(1, 1), Const(0, 1)), 1).replicate(8) for i in range(7, -1, -1)])
    orh48 = Cat(s1[8:64], Const(0, 8)) | s2
    sextb = _sext(s1[0:8], 64)
    packh = Cat(s2[0:8], s1[0:8])
    sexth = _sext(s1[0:16], 64)
    packw = _sext(Cat(s2[0:16], s1[0:16]), 64)
    revb = Cat(*[_bit_reverse(s1[i * 8:i * 8 + 8], 8) for i in range(7, -1, -1)])
    pack = Cat(s2[0:32], s1[0:32])
    rev8 = Cat(*[s1[i * 8:i * 8 + 8] for i in range(7, -1, -1)])
    # ShiftResultSelect. / 移位结果选择。
    simple = (sll, sll, bclr, bset, binv, srl, Cat(Const(0, 63), bext), sra)
    shift_res = Mux(f[3:4], Mux(f[1:2], ror, rol), simple[0])
    for k in range(1, 8):
        shift_res = Mux(~f[3:4] & (f[0:3] == Const(k, 3)), simple[k], shift_res)
    # MiscResultSelect. / 杂项结果选择。
    logic_res = and_r
    logic_res = Mux(f[1:3] == Const(1, 2), or_r, logic_res)
    logic_res = Mux(f[1:3] == Const(2, 2), xor_r, logic_res)
    logic_res = Mux(f[1:3] == Const(3, 2), orcb, logic_res)
    misc_res4 = sextb
    misc_res4 = Mux(f[0:2] == Const(1, 2), packh, misc_res4)
    misc_res4 = Mux(f[0:2] == Const(2, 2), sexth, misc_res4)
    misc_res4 = Mux(f[0:2] == Const(3, 2), packw, misc_res4)
    logic_base = Mux(f[3:4], misc_res4, logic_res)
    rev_res = revb
    rev_res = Mux(f[0:2] == Const(1, 2), rev8, rev_res)
    rev_res = Mux(f[0:2] == Const(2, 2), pack, rev_res)
    rev_res = Mux(f[0:2] == Const(3, 2), orh48, rev_res)
    custom = (
        Cat(Const(0, 31), s1[0:32], Const(0, 1)),
        Cat(Const(0, 30), s1[0:32], Const(0, 2)),
        Cat(Const(0, 29), s1[0:32], Const(0, 3)),
        Cat(Const(0, 56), s1[8:16]),
    )
    custom_res = custom[0]
    for k in range(1, 4):
        custom_res = Mux(f[0:2] == Const(k, 2), custom[k], custom_res)
    logic_adv = Mux(f[3:4], custom_res, rev_res)
    mask = Cat(f[0:1].replicate(15), Const(1, 1))
    masked_logic = mask & logic_res
    misc_res = Mux(f[5:6], masked_logic, Mux(f[4:5], logic_adv, logic_base))
    # ConditionalZeroModule. / 条件清零模块。
    cond_zero = s2 == Const(0, 64)
    use_zero = (~f[1:2] & cond_zero) | (f[1:2] & ~cond_zero)
    cond_res = Mux(use_zero, Const(0, 64), s1)
    # WordResultSelect. / 字结果选择。
    addsub_res = Mux(~f[2:3] & f[1:2] & ~f[0:1], _zext(subw, 64), addw)
    word_shift = Mux(f[2:3], Mux(f[0:1], rorw, rolw), Mux(f[1:2], sraw, Mux(f[0:1], srlw, sllw)))
    word_res = Mux(f[3:4], _sext(word_shift[0:32], 64), addsub_res)
    # AluResSel on func[6:4]. / 按 func[6:4] 的最终选择。
    fa = f[4:5]
    fb = f[5:6]
    fc = f[6:7]
    res = Mux(
        ~fc & ~fb,
        Mux(fa, word_res, shift_res),
        Mux(~fc, Mux(fa, compare_res, add), Mux(fc & fb & fa, cond_res, misc_res)),
    )
    return res


def branch_taken(m: Any, func: Value, src1: Value, src2: Value, pred_taken: Value, prefix: str):
    # BranchModule: branch resolution and misprediction detection.  Wide
    # intermediates are materialised as comb signals because slicing a plain
    # expression rebuilds its whole tree per bit.
    # BranchModule：分支裁决与误预测检测。宽中间项落地为组合信号——对普通表达式
    # 逐位切片会按位重建整棵表达式树。
    f = cast(Any, func)
    s1 = cast(Any, src1)
    s2 = cast(Any, src2)
    sub_s = Signal(65, name=prefix + "_sub65")
    xor_s = Signal(64, name=prefix + "_xor")
    m.d.comb += [
        sub_s.eq(cast(Any, Cat(Const(0, 1), s1)) + cast(Any, Cat(Const(0, 1), ~s2)) + Const(1, 65)),
        xor_s.eq(s1 ^ s2),
    ]
    sltu = cast(Any, ~(cast(Any, sub_s)[64:65]))
    slt = cast(Any, s1[63:64]) ^ cast(Any, s2[63:64]) ^ sltu
    btype = f[1:4]
    cond = Mux(btype == Const(0, 3), ~_or_reduce(xor_s), Mux(btype == Const(2, 3), slt, sltu))
    taken = cond ^ f[0:1]
    mispredict = cast(Any, pred_taken) ^ taken
    return taken, mispredict


def addr_add_result(m: Any, pc_extend: Value, taken: Value, imm: Value, next_pc_offset: Value, prefix: str):
    # AddrAddModule: branch target / sequential next address (pinned AddrAddModule.sv).
    # AddrAddModule：分支目标 / 顺序下一地址（钉死的 AddrAddModule.sv）。
    pc_s = Signal(51, name=prefix + "_pc")
    imm_s = Signal(51, name=prefix + "_imm")
    seq = Signal(51, name=prefix + "_seq")
    t = Signal(51, name=prefix + "_t")
    out = Signal(64, name=prefix + "_target")
    m.d.comb += [
        pc_s.eq(cast(Any, pc_extend)),
        imm_s.eq(_sext(cast(Any, imm)[0:15], 51)),
        seq.eq(Cat(Const(0, 45), cast(Any, next_pc_offset), Const(0, 1))),
        t.eq(Mux(cast(Any, taken), pc_s + imm_s, pc_s + seq)),
        out.eq(_sext(t, 64)),
    ]
    return out


def check_faults(m: Any, addr_trans: Value, target: Value, prefix: str):
    # AddrTransType.check*Fault on the full target (Bundle.scala:692-698). / 对全目标地址的 AddrTransType.check*Fault（Bundle.scala:692-698）。
    t = Signal(64, name=prefix + "_faultT")
    m.d.comb += t.eq(cast(Any, target))
    bare = cast(Any, addr_trans)[0:1]
    sv39 = cast(Any, addr_trans)[1:2]
    sv39x4 = cast(Any, addr_trans)[2:3]
    sv48 = cast(Any, addr_trans)[3:4]
    sv48x4 = cast(Any, addr_trans)[4:5]
    iaf = bare & _or_reduce(t[48:64])
    ipf = (sv39 & (t[39:64] != cast(Any, t[38:39]).replicate(25))) | (sv48 & (t[48:64] != cast(Any, t[47:48]).replicate(16)))
    igpf = (sv39x4 & _or_reduce(t[41:64])) | (sv48x4 & _or_reduce(t[50:64]))
    return iaf, ipf, igpf


def _rob_need_flush(flush_valid, flush_flag, flush_value, flush_level, rob_flag, rob_value):
    # RobPtr.needFlush transcription used by the ExeUnit inPipe and DivUnit kills.
    # ExeUnit inPipe 与 DivUnit kill 使用的 RobPtr.needFlush 转写。
    eq = (cast(Any, rob_flag) == flush_flag) & (cast(Any, rob_value) == flush_value)
    older = cast(Any, rob_flag) ^ flush_flag ^ (cast(Any, rob_value) > cast(Any, flush_value))
    return flush_valid & ((cast(Any, flush_level) & eq) | older)


class CountLeaf(Elaboratable):
    """Bku.scala CountModule core (registered operands, combinational result). / Bku.scala CountModule 核心（寄存操作数，组合输出）。"""

    def __init__(self) -> None:
        self.clock = Signal(name="clock")
        self.src = Signal(64, name="io_src")
        self.func = Signal(9, name="io_func")
        self.reg_enable = Signal(name="io_regEnable")
        self.out = Signal(64, name="io_out")
        self._func_r = Signal(9, name="count_funcReg")
        self._cnt_src = Signal(64, name="count_src")
        self._pop = [Signal(5, name="count_cpopTmp_%d" % i) for i in range(4)]

    def elaborate(self, platform: Any) -> Module:
        m: Any = Module()
        count_src = Mux(cast(Any, self.func)[1:2], _bit_reverse(self.src, 64), self.src)
        with m.If(self.reg_enable):
            m.d.sync += [
                self._func_r.eq(self.func),
                self._cnt_src.eq(count_src),
                self._pop[0].eq(_popcount16(self.src[0:16])),
                self._pop[1].eq(_popcount16(self.src[16:32])),
                self._pop[2].eq(_popcount16(self.src[32:48])),
                self._pop[3].eq(_popcount16(self.src[48:64])),
            ]
        lz64 = _zext(_clz_tree(self._cnt_src, 64), 64)
        lz32_lo = _zext(_clz_tree(self._cnt_src[0:32], 32), 64)
        lz32_hi = _zext(_clz_tree(self._cnt_src[32:64], 32), 64)
        lo = _pad(self._pop[0], 6) + _pad(self._pop[1], 6)
        cpop_w = _zext(lo, 64)
        cpop_all = _zext(_pad(lo, 7) + _pad(self._pop[2], 7) + _pad(self._pop[3], 7), 64)
        fr = self._func_r
        m.d.comb += self.out.eq(
            Mux(fr[2:3], Mux(fr[0:1], cpop_w, cpop_all), Mux(fr[0:1], Mux(fr[1:2], lz32_hi, lz32_lo), lz64))
        )
        return m


class ClmulLeaf(Elaboratable):
    """Bku.scala ClmulModule core (registered operands, combinational carry-less product). / Bku.scala ClmulModule 核心（寄存操作数，组合无进位乘积）。"""

    def __init__(self) -> None:
        self.clock = Signal(name="clock")
        self.src0 = Signal(64, name="io_src_0")
        self.src1 = Signal(64, name="io_src_1")
        self.func = Signal(9, name="io_func")
        self.reg_enable = Signal(name="io_regEnable")
        self.out = Signal(64, name="io_out")
        self._a = Signal(64, name="clmul_a")
        self._b = Signal(64, name="clmul_b")
        self._func_r = Signal(9, name="clmul_funcReg")

    def elaborate(self, platform: Any) -> Module:
        m: Any = Module()
        with m.If(self.reg_enable):
            m.d.sync += [self._a.eq(self.src0), self._b.eq(self.src1), self._func_r.eq(self.func)]
        acc = Const(0, 128)
        for i in range(64):
            shifted = (cast(Any, Cat(self._b, Const(0, 64))) << i)[0:128]
            acc = acc ^ Mux(self._a[i:i + 1], shifted, Const(0, 128))
        clmul = acc[0:64]
        clmulh = acc[64:128]
        clmulr = acc[63:127]
        fr = self._func_r
        m.d.comb += self.out.eq(Mux(fr == Const(1, 9), clmulh, Mux(fr == Const(2, 9), clmulr, clmul)))
        return m


class MiscLeaf(Elaboratable):
    """Bku.scala MiscModule core (XPERM.N / XPERM.B). / Bku.scala MiscModule 核心（XPERM.N / XPERM.B）。"""

    def __init__(self) -> None:
        self.clock = Signal(name="clock")
        self.src0 = Signal(64, name="io_src_0")
        self.src1 = Signal(64, name="io_src_1")
        self.func = Signal(9, name="io_func")
        self.reg_enable = Signal(name="io_regEnable")
        self.out = Signal(64, name="io_out")
        self._out_r = Signal(64, name="misc_out_r")

    def elaborate(self, platform: Any) -> Module:
        m: Any = Module()
        s1 = self.src0
        s2 = self.src1
        xperm_n = Cat(*[_xperm_lut(s1, s2[i * 4:i * 4 + 4], 4) for i in range(15, -1, -1)])
        xperm_b = Cat(*[
            Mux(_or_reduce(s2[i * 8 + 3:i * 8 + 8]), Const(0, 8), _xperm_lut(s1, s2[i * 8:i * 8 + 3], 8))
            for i in range(7, -1, -1)
        ])
        with m.If(self.reg_enable):
            m.d.sync += self._out_r.eq(Mux(cast(Any, self.func)[0:1], xperm_b, xperm_n))
        m.d.comb += self.out.eq(self._out_r)
        return m


class HashLeaf(Elaboratable):
    """Bku.scala HashModule core (SHA-256/512, SM3). / Bku.scala HashModule 核心（SHA-256/512、SM3）。"""

    def __init__(self) -> None:
        self.clock = Signal(name="clock")
        self.src = Signal(64, name="io_src")
        self.func = Signal(9, name="io_func")
        self.reg_enable = Signal(name="io_regEnable")
        self.out = Signal(64, name="io_out")
        self._out_r = Signal(64, name="hash_out_r")

    def elaborate(self, platform: Any) -> Module:
        m: Any = Module()
        s1 = self.src
        f = cast(Any, self.func)
        sha_src = (
            _sext(_ror32(s1, 2)[0:32] ^ _ror32(s1, 13)[0:32] ^ _ror32(s1, 22)[0:32], 64),
            _sext(_ror32(s1, 6)[0:32] ^ _ror32(s1, 11)[0:32] ^ _ror32(s1, 25)[0:32], 64),
            _sext(cast(Any, _ror32(s1, 7)[0:32]) ^ cast(Any, _ror32(s1, 18)[0:32]) ^ (cast(Any, s1[0:32]) >> 3), 64),
            _sext(cast(Any, _ror32(s1, 17)[0:32]) ^ cast(Any, _ror32(s1, 19)[0:32]) ^ (cast(Any, s1[0:32]) >> 10), 64),
            _ror64(s1, 28) ^ _ror64(s1, 34) ^ _ror64(s1, 39),
            _ror64(s1, 14) ^ _ror64(s1, 18) ^ _ror64(s1, 41),
            _ror64(s1, 1) ^ _ror64(s1, 8) ^ (s1 >> 7),
            _ror64(s1, 19) ^ _ror64(s1, 61) ^ (s1 >> 6),
        )
        sha = sha_src[0]
        for i in range(1, 8):
            sha = Mux(f[0:3] == Const(i, 3), sha_src[i], sha)
        sm3p0 = _ror32(s1, 23)[0:32] ^ _ror32(s1, 15)[0:32] ^ s1[0:32]
        sm3p1 = _ror32(s1, 9)[0:32] ^ _ror32(s1, 17)[0:32] ^ s1[0:32]
        sm3 = Mux(f[0:1], _sext(sm3p1, 64), _sext(sm3p0, 64))
        with m.If(self.reg_enable):
            m.d.sync += self._out_r.eq(Mux(f[3:4], sm3, sha))
        m.d.comb += self.out.eq(self._out_r)
        return m


class BlockCipherLeaf(Elaboratable):
    """Bku.scala BlockCipherModule core (AES/SM4 with the composite-field S-box network). / Bku.scala BlockCipherModule 核心（含复合域 S-box 网络的 AES/SM4）。"""

    RCON = (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36, 0x00, 0x01, 0x01, 0x01, 0x01, 0x01)

    def __init__(self) -> None:
        self.clock = Signal(name="clock")
        self.src0 = Signal(64, name="io_src_0")
        self.src1 = Signal(64, name="io_src_1")
        self.func = Signal(9, name="io_func")
        self.reg_enable = Signal(name="io_regEnable")
        self.out = Signal(64, name="io_out")
        self._aes_mid = [[Signal(name="aesSboxMid_%d_%d" % (i, j)) for j in range(21)] for i in range(8)]
        self._iaes_mid = [[Signal(name="iaesSboxMid_%d_%d" % (i, j)) for j in range(21)] for i in range(8)]
        self._ks_top = [[Signal(name="ksSboxTop_%d_%d" % (i, j)) for j in range(21)] for i in range(4)]
        self._sm4_top = [Signal(name="sm4SboxTop_%d" % j) for j in range(21)]
        self._im_min = [Signal(8, name="imMinIn_%d" % i) for i in range(8)]
        self._ks1_idx = Signal(4, name="ks1Idx")
        self._ks2_r = Signal(64, name="aes64ks2_r")
        self._sm4_src1 = Signal(32, name="sm4_src1_r")
        self._func_r = Signal(9, name="bc_funcReg")

    def elaborate(self, platform: Any) -> Module:
        m: Any = Module()
        s1 = cast(Any, self.src0)
        s2 = cast(Any, self.src1)
        f = cast(Any, self.func)
        sb1 = [s1[i * 8:i * 8 + 8] for i in range(8)]
        sb2 = [s2[i * 8:i * 8 + 8] for i in range(8)]
        fsr = [sb1[0], sb1[5], sb2[2], sb2[7], sb1[4], sb2[1], sb2[6], sb1[3]]
        isr = [sb1[0], sb2[5], sb2[2], sb1[7], sb1[4], sb1[1], sb2[6], sb2[3]]
        # Each S-box chain is materialised through explicit comb signals so the
        # expression trees stay linear (Amaranth does not CSE shared subterms).
        # 每条 S-box 链都经由显式组合信号落地，使表达式树保持线性
        #（Amaranth 不会对共享子项做公共子表达式消除）。
        def _sbox_chain(top_bits, out_fn, inv_name, out_name):
            inv_sig = Signal(18, name=inv_name)
            out_sig = Signal(8, name=out_name)
            iv = sbox_inv(m, top_bits, inv_name)
            m.d.comb += cast(Any, Cat(*[inv_sig[j] for j in range(18)])).eq(Cat(*iv))
            ov = out_fn(m, inv_sig, out_name)
            m.d.comb += cast(Any, Cat(*[out_sig[j] for j in range(8)])).eq(Cat(*ov))
            return out_sig

        aes_out = [_sbox_chain(self._aes_mid[i], sbox_aes_out, "aesSboxInv_%d" % i, "aesSboxOut_%d" % i) for i in range(8)]
        iaes_out = [_sbox_chain(self._iaes_mid[i], sbox_iaes_out, "iaesSboxInv_%d" % i, "iaesSboxOut_%d" % i) for i in range(8)]
        aes64es = Cat(*aes_out)
        aes64ds = Cat(*iaes_out)
        aes64esm = Cat(mix_fwd(aes_out[4:8]), mix_fwd(aes_out[0:4]))
        aes64dsm = Cat(mix_inv(iaes_out[4:8]), mix_inv(iaes_out[0:4]))
        im_min = [self._im_min[i] for i in range(8)]
        aes64im = Cat(mix_inv(im_min[4:8]), mix_inv(im_min[0:4]))
        ks_in = [
            Mux(s2[0:4] == Const(0xa, 4), sb1[4], sb1[5]),
            Mux(s2[0:4] == Const(0xa, 4), sb1[5], sb1[6]),
            Mux(s2[0:4] == Const(0xa, 4), sb1[6], sb1[7]),
            Mux(s2[0:4] == Const(0xa, 4), sb1[7], sb1[4]),
        ]
        ks_out = [_sbox_chain(self._ks_top[i], sbox_aes_out, "ksSboxInv_%d" % i, "ksSboxOut_%d" % i) for i in range(4)]
        rcon = Const(0, 8)
        for i, val in enumerate(self.RCON):
            rcon = Mux(self._ks1_idx == Const(i, 4), Const(val, 8), rcon)
        ks_cat = Cat(*ks_out)
        aes64ks1i = Cat(ks_cat[0:32] ^ _zext(rcon, 32), ks_cat[32:64] ^ _zext(rcon, 32))
        aes64ks2 = self._ks2_r
        aes_res = aes64es
        for code, val in ((0x21, aes64esm), (0x22, aes64ds), (0x23, aes64dsm), (0x24, aes64im), (0x25, aes64ks1i), (0x26, aes64ks2)):
            aes_res = Mux(self._func_r == Const(code, 9), val, aes_res)
        sm4_in = sb2[0]
        for k in range(1, 4):
            sm4_in = Mux(f[0:2] == Const(k, 2), sb2[k], sm4_in)
        sm4_sbox = Signal(8, name="sm4SboxOut")
        sm4_iv = sbox_inv(m, self._sm4_top, "sm4SboxInv")
        sm4_ov = sbox_sm4_out(m, sm4_iv, "sm4SboxOutStage")
        m.d.comb += sm4_sbox.eq(sm4_ov)
        sm4ed = cast(Any, sm4_sbox) ^ (cast(Any, sm4_sbox) << 8) ^ (cast(Any, sm4_sbox) << 2) ^ (cast(Any, sm4_sbox) << 18) ^ ((cast(Any, sm4_sbox) & Const(0x3f, 8)) << 26) ^ ((cast(Any, sm4_sbox) & Const(0xc0, 8)) << 10)
        sm4ks = cast(Any, sm4_sbox) ^ ((cast(Any, sm4_sbox) & Const(0x07, 8)) << 29) ^ ((cast(Any, sm4_sbox) & Const(0xfe, 8)) << 7) ^ ((cast(Any, sm4_sbox) & Const(0x01, 8)) << 23) ^ ((cast(Any, sm4_sbox) & Const(0xf8, 8)) << 13)
        sm4_src = (
            sm4ed[0:32],
            Cat(sm4ed[0:24], sm4ed[24:32]),
            Cat(sm4ed[0:16], sm4ed[16:32]),
            Cat(sm4ed[0:8], sm4ed[8:32]),
            sm4ks[0:32],
            Cat(sm4ks[0:24], sm4ks[24:32]),
            Cat(sm4ks[0:16], sm4ks[16:32]),
            Cat(sm4ks[0:8], sm4ks[8:32]),
        )
        sm4_sel = sm4_src[0]
        for k in range(1, 8):
            sm4_sel = Mux(self._func_r[0:3] == Const(k, 3), sm4_src[k], sm4_sel)
        sm4_res = _sext((sm4_sel ^ self._sm4_src1)[0:32], 64)
        m.d.comb += self.out.eq(Mux(self._func_r[3:4], sm4_res, aes_res))
        with m.If(self.reg_enable):
            stmts = [
                self._func_r.eq(self.func),
                self._ks1_idx.eq(s2[0:4]),
                self._sm4_src1.eq(s1[0:32]),
            ]
            ks_temp = s1[32:64] ^ s2[0:32]
            stmts.append(self._ks2_r.eq(Cat(ks_temp ^ s2[32:64], ks_temp)))
            # Materialise each Top-stage network once into comb signals before
            # the register update so the trees are not rebuilt per output bit.
            # 每条 Top 级网络先落地为组合信号再写寄存器，避免逐位重建表达式树。
            sm4_top_c = Signal(21, name="sm4TopComb")
            m.d.comb += cast(Any, Cat(*[sm4_top_c[j] for j in range(21)])).eq(Cat(*sbox_sm4_top(m, sm4_in, "sm4TopIn")))
            for j in range(21):
                stmts.append(self._sm4_top[j].eq(sm4_top_c[j]))
            for i in range(8):
                stmts.append(self._im_min[i].eq(sb1[i]))
                aes_top_c = Signal(21, name="aesTopComb_%d" % i)
                iaes_top_c = Signal(21, name="iaesTopComb_%d" % i)
                m.d.comb += cast(Any, Cat(*[aes_top_c[j] for j in range(21)])).eq(Cat(*sbox_aes_top(m, fsr[i], "aesTopIn_%d" % i)))
                m.d.comb += cast(Any, Cat(*[iaes_top_c[j] for j in range(21)])).eq(Cat(*sbox_iaes_top(m, isr[i], "iaesTopIn_%d" % i)))
                for j in range(21):
                    stmts.append(self._aes_mid[i][j].eq(aes_top_c[j]))
                    stmts.append(self._iaes_mid[i][j].eq(iaes_top_c[j]))
            for i in range(4):
                ks_top_c = Signal(21, name="ksTopComb_%d" % i)
                m.d.comb += cast(Any, Cat(*[ks_top_c[j] for j in range(21)])).eq(Cat(*sbox_aes_top(m, ks_in[i], "ksTopIn_%d" % i)))
                for j in range(21):
                    stmts.append(self._ks_top[i][j].eq(ks_top_c[j]))
            m.d.sync += stmts
        return m


class CryptoLeaf(Elaboratable):
    """Bku.scala CryptoModule core (Hash vs BlockCipher mux). / Bku.scala CryptoModule 核心（Hash 与 BlockCipher 选择）。"""

    def __init__(self) -> None:
        self.clock = Signal(name="clock")
        self.src0 = Signal(64, name="io_src_0")
        self.src1 = Signal(64, name="io_src_1")
        self.func = Signal(9, name="io_func")
        self.reg_enable = Signal(name="io_regEnable")
        self.out = Signal(64, name="io_out")
        self._func_r = Signal(9, name="crypto_funcReg")
        self._hash = HashLeaf()
        self._bc = BlockCipherLeaf()

    def elaborate(self, platform: Any) -> Module:
        m: Any = Module()
        m.submodules.hash = self._hash
        m.submodules.bc = self._bc
        m.d.comb += [
            self._hash.src.eq(self.src0),
            self._hash.func.eq(self.func),
            self._hash.reg_enable.eq(self.reg_enable),
            self._bc.src0.eq(self.src0),
            self._bc.src1.eq(self.src1),
            self._bc.func.eq(self.func),
            self._bc.reg_enable.eq(self.reg_enable),
        ]
        with m.If(self.reg_enable):
            m.d.sync += self._func_r.eq(self.func)
        m.d.comb += self.out.eq(Mux(self._func_r[4:5], self._hash.out, self._bc.out))
        return m


# Per-output fuType compare constants, transcribed from the pinned Dispatcher*.sv bodies.
# 逐输出 fuType 比较常量，转写自钉死的 Dispatcher*.sv 体。
DISPATCH_MASKS: dict[str, tuple[int, ...]] = {
    "Dispatcher": (0x40, 0x80, 0x400),
    "Dispatcher_1": (0x2, 0x1),
    "Dispatcher_4": (0x40,),
    "Dispatcher_5": (0x2, 0x1, 0x4, 0x10000000, 0x20000000, 0x8),
    "Dispatcher_7": (0x20, 0x200, 0x100),
    "Dispatcher_8": (0x800, 0x2000, 0x10, 0x1000),
    "Dispatcher_9": (0x4000,),
    "Dispatcher_10": (0x800, 0x1000),
    "Dispatcher_13": (0x2000000, 0x80000, 0x200000, 0x100000),
    "Dispatcher_14": (0x1000000, 0x8000000, 0x40000, 0x40000000),
    "Dispatcher_15": (0x2000000, 0x80000),
    "Dispatcher_16": (0x1000000,),
    "Dispatcher_17": (0x4000000, 0x400000),
}


def _out_indices(self: "ExuFuncModule") -> list[str]:
    # Collect the ``io_out_<i>`` index strings present in the port surface. / 收集端口面中的 ``io_out_<i>`` 下标。
    outs = []
    for name in self.ports:
        if name.startswith("io_out_") and name.endswith("_valid"):
            outs.append(name[len("io_out_"):-len("_valid")])
    return sorted(outs, key=lambda s: int(s))


def _passthrough_outputs(self: "ExuFuncModule", m: Any) -> None:
    # Drive every ``io_out_bits_*`` port from the same-named ``io_in_bits_*`` input.
    # 由同名 ``io_in_bits_*`` 输入驱动每个 ``io_out_bits_*`` 端口。
    for spec in self.specs:
        if spec.name.startswith("io_out_bits_"):
            cand = "io_in_bits_" + spec.name[len("io_out_bits_"):]
            if cand in self.ports:
                m.d.comb += self.ports[spec.name].eq(self.ports[cand])
            else:
                m.d.comb += self.ports[spec.name].eq(Const(0, spec.width))


def build_dispatcher(self: "ExuFuncModule", m: Any) -> None:
    # Dispatcher: one-hot fuType compare routes the input to exactly one output
    # (pinned Dispatcher*.sv: io_out_N_valid = io_in_bits_fuType == 35'hMASK & io_in_valid).
    # Dispatcher：one-hot fuType 比较将输入路由到唯一输出（钉死的 Dispatcher*.sv）。
    p = self.ports
    in_valid = p["io_in_valid"]
    fu_type = p["io_in_bits_fuType"]
    for idx in _out_indices(self):
        mask = DISPATCH_MASKS[self.module_name][int(idx)]
        m.d.comb += p["io_out_%s_valid" % idx].eq(in_valid & (fu_type == Const(mask, 35)))
    _passthrough_outputs(self, m)
    readies = [p["io_out_%s_ready" % i] for i in _out_indices(self) if "io_out_%s_ready" % i in p]
    if readies and "io_in_ready" in p:
        acc = readies[0]
        for r in readies[1:]:
            acc = acc & r
        m.d.comb += p["io_in_ready"].eq(acc)


def _leaf_ports(self: "ExuFuncModule", m: Any, leaf: Any) -> None:
    # Instantiate a Bku leaf under ``m`` and wire it to the locked port surface. / 在 ``m`` 下实例化 Bku 叶子并连接锁定端口面。
    m.submodules.leaf = leaf
    m.d.comb += [
        leaf.clock.eq(self.ports["clock"]),
        leaf.reg_enable.eq(self.ports["io_regEnable"]),
        self.ports["io_out"].eq(leaf.out),
    ]


def build_count(self: "ExuFuncModule", m: Any) -> None:
    # CountModule locked leaf: CLZ/CTZ/CPOP with registered stage-0 state. / CountModule 锁定叶子：带寄存一级状态的 CLZ/CTZ/CPOP。
    leaf = CountLeaf()
    _leaf_ports(self, m, leaf)
    m.d.comb += [leaf.src.eq(self.ports["io_src"]), leaf.func.eq(self.ports["io_func"])]


def build_clmul(self: "ExuFuncModule", m: Any) -> None:
    # ClmulModule locked leaf: carry-less multiply with registered operands. / ClmulModule 锁定叶子：带寄存操作数的无进位乘法。
    leaf = ClmulLeaf()
    _leaf_ports(self, m, leaf)
    m.d.comb += [leaf.src0.eq(self.ports["io_src_0"]), leaf.src1.eq(self.ports["io_src_1"]), leaf.func.eq(self.ports["io_func"])]


def build_misc(self: "ExuFuncModule", m: Any) -> None:
    # MiscModule locked leaf: XPERM.N / XPERM.B. / MiscModule 锁定叶子：XPERM.N / XPERM.B。
    leaf = MiscLeaf()
    _leaf_ports(self, m, leaf)
    m.d.comb += [leaf.src0.eq(self.ports["io_src_0"]), leaf.src1.eq(self.ports["io_src_1"]), leaf.func.eq(self.ports["io_func"])]


def build_hash(self: "ExuFuncModule", m: Any) -> None:
    # HashModule locked leaf: SHA-256/512 and SM3 message words. / HashModule 锁定叶子：SHA-256/512 与 SM3 消息字。
    leaf = HashLeaf()
    _leaf_ports(self, m, leaf)
    m.d.comb += [leaf.src.eq(self.ports["io_src"]), leaf.func.eq(self.ports["io_func"])]


def build_blockcipher(self: "ExuFuncModule", m: Any) -> None:
    # BlockCipherModule locked leaf: AES/SM4 round functions. / BlockCipherModule 锁定叶子：AES/SM4 轮函数。
    leaf = BlockCipherLeaf()
    _leaf_ports(self, m, leaf)
    m.d.comb += [leaf.src0.eq(self.ports["io_src_0"]), leaf.src1.eq(self.ports["io_src_1"]), leaf.func.eq(self.ports["io_func"])]


def build_crypto(self: "ExuFuncModule", m: Any) -> None:
    # CryptoModule locked leaf: hash vs block-cipher selection. / CryptoModule 锁定叶子：哈希与分组密码选择。
    leaf = CryptoLeaf()
    _leaf_ports(self, m, leaf)
    m.d.comb += [leaf.src0.eq(self.ports["io_src_0"]), leaf.src1.eq(self.ports["io_src_1"]), leaf.func.eq(self.ports["io_func"])]


def build_alu(self: "ExuFuncModule", m: Any) -> None:
    # Alu: 0-latency FuncUnit over AluDataModule; ctrlPipe_0 ctrl passthrough.
    # Alu：AluDataModule 之上的 0 延迟 FuncUnit；ctrlPipe_0 控制透传。
    p = self.ports
    m.d.comb += [
        p["io_out_bits_res_data"].eq(alu_result(p["io_in_bits_ctrl_fuOpType"], p["io_in_bits_data_src_0"], p["io_in_bits_data_src_1"])),
        p["io_out_valid"].eq(p["io_in_valid"]),
        p["io_out_bits_ctrl_robIdx_flag"].eq(p["io_in_bits_ctrlPipe_0_robIdx_flag"]),
        p["io_out_bits_ctrl_robIdx_value"].eq(p["io_in_bits_ctrlPipe_0_robIdx_value"]),
        p["io_out_bits_ctrl_pdest"].eq(p["io_in_bits_ctrlPipe_0_pdest"]),
        p["io_out_bits_ctrl_rfWen"].eq(p["io_in_bits_ctrlPipe_0_rfWen"]),
    ]


def build_bku(self: "ExuFuncModule", m: Any) -> None:
    # Bku: 2-stage FuncUnit (latency 2) muxing the four K-extension leaves
    # (pinned Bku.sv, FuncUnit.scala HasPipelineReg with latency=2).
    # Bku：二级 FuncUnit（延迟 2），选择四个 K 扩展叶子（钉死的 Bku.sv）。
    p = self.ports
    vvf1 = Signal(name="bku_validVecThisFu_1")
    vvf2 = Signal(name="bku_validVecThisFu_2")
    func_r = Signal(9, name="bku_funcReg")
    res_r = Signal(64, name="bku_res_r")
    m.d.sync += [vvf1.eq(p["io_in_valid"]), vvf2.eq(vvf1)]
    with m.If(p["io_in_valid"]):
        m.d.sync += func_r.eq(p["io_in_bits_ctrl_fuOpType"])
    vv0 = p["io_in_bits_validPipe_0"] & p["io_in_valid"]
    en2 = p["io_in_bits_validPipe_1"] & vvf1
    count = CountLeaf()
    clmul = ClmulLeaf()
    misc = MiscLeaf()
    crypto = CryptoLeaf()
    m.submodules.count = count
    m.submodules.clmul = clmul
    m.submodules.misc = misc
    m.submodules.crypto = crypto
    func_now = p["io_in_bits_ctrl_fuOpType"]
    m.d.comb += [
        count.clock.eq(p["clock"]),
        count.reg_enable.eq(vv0),
        count.src.eq(p["io_in_bits_data_src_0"]),
        count.func.eq(func_now),
        clmul.clock.eq(p["clock"]),
        clmul.reg_enable.eq(vv0),
        clmul.src0.eq(p["io_in_bits_data_src_0"]),
        clmul.src1.eq(p["io_in_bits_data_src_1"]),
        clmul.func.eq(func_now),
        misc.clock.eq(p["clock"]),
        misc.reg_enable.eq(vv0),
        misc.src0.eq(p["io_in_bits_data_src_0"]),
        misc.src1.eq(p["io_in_bits_data_src_1"]),
        misc.func.eq(func_now),
        crypto.clock.eq(p["clock"]),
        crypto.reg_enable.eq(vv0),
        crypto.src0.eq(p["io_in_bits_data_src_0"]),
        crypto.src1.eq(p["io_in_bits_data_src_1"]),
        crypto.func.eq(func_now),
    ]
    sel = Mux(func_r[5:6], crypto.out, Mux(func_r[3:4], count.out, Mux(func_r[2:3], misc.out, clmul.out)))
    with m.If(en2):
        m.d.sync += res_r.eq(sel)
    m.d.comb += [
        p["io_out_valid"].eq(p["io_in_bits_validPipe_2"] & vvf2),
        p["io_out_bits_res_data"].eq(res_r),
        p["io_out_bits_ctrl_robIdx_flag"].eq(p["io_in_bits_ctrlPipe_2_robIdx_flag"]),
        p["io_out_bits_ctrl_robIdx_value"].eq(p["io_in_bits_ctrlPipe_2_robIdx_value"]),
        p["io_out_bits_ctrl_pdest"].eq(p["io_in_bits_ctrlPipe_2_pdest"]),
        p["io_out_bits_ctrl_rfWen"].eq(p["io_in_bits_ctrlPipe_2_rfWen"]),
    ]


def build_mul(self: "ExuFuncModule", m: Any) -> None:
    # MulUnit: 2-stage FuncUnit over ArrayMulDataModule (a,b 65-bit Booth inputs,
    # result selected by the pipelined isHi/isW control).
    # MulUnit：ArrayMulDataModule 之上的二级 FuncUnit（65 位 Booth 输入 a、b，
    # 结果由流水化的 isHi/isW 控制选择）。
    p = self.ports
    func = p["io_in_bits_ctrl_fuOpType"]
    vvf1 = Signal(name="mul_validVecThisFu_1")
    vvf2 = Signal(name="mul_validVecThisFu_2")
    r_isw = Signal(name="mul_r_isW")
    r_ishi = Signal(name="mul_r_isHi")
    r1_isw = Signal(name="mul_r1_isW")
    r1_ishi = Signal(name="mul_r1_isHi")
    pp0 = Signal(130, name="mul_pp0")
    pp1 = Signal(130, name="mul_pp1")
    op = Cat(func[1:3], func[3:4])
    src0 = p["io_in_bits_data_src_0"]
    src1 = p["io_in_bits_data_src_1"]
    a65 = _zext(src0, 65)
    a65 = Mux((op == Const(1, 3)) | (op == Const(2, 3)), Cat(src0, src0[63:64]), a65)
    a65 = Mux(op == Const(4, 3), _zext(src0[0:7], 65), a65)
    b65 = Mux(op == Const(1, 3), Cat(src1, src1[63:64]), _zext(src1, 65))
    vv0 = p["io_in_bits_validPipe_0"] & p["io_in_valid"]
    vv1 = p["io_in_bits_validPipe_1"] & vvf1
    m.d.sync += [vvf1.eq(p["io_in_valid"]), vvf2.eq(vvf1)]
    with m.If(vv0):
        m.d.sync += [r_isw.eq(func[2:3]), r_ishi.eq(_or_reduce(func[0:2])), pp0.eq(a65.as_signed() * b65.as_signed())]
    with m.If(vv1):
        m.d.sync += [r1_isw.eq(r_isw), r1_ishi.eq(r_ishi), pp1.eq(pp0)]
    res = Mux(r1_ishi, pp1[64:128], pp1[0:64])
    m.d.comb += [
        p["io_out_valid"].eq(p["io_in_bits_validPipe_2"] & vvf2),
        p["io_out_bits_res_data"].eq(Mux(r1_isw, _sext(res[0:32], 64), res)),
        p["io_out_bits_ctrl_robIdx_flag"].eq(p["io_in_bits_ctrlPipe_2_robIdx_flag"]),
        p["io_out_bits_ctrl_robIdx_value"].eq(p["io_in_bits_ctrlPipe_2_robIdx_value"]),
        p["io_out_bits_ctrl_pdest"].eq(p["io_in_bits_ctrlPipe_2_pdest"]),
        p["io_out_bits_ctrl_rfWen"].eq(p["io_in_bits_ctrlPipe_2_rfWen"]),
    ]


def build_div(self: "ExuFuncModule", m: Any) -> None:
    # DivUnit: wrapper handshake around the divider core.  The SRT16 core itself
    # is a separate locked subject; this model restores the identical request/kill
    # protocol with a one-iteration-per-cycle restoring array and a fixed result
    # register.  Divider cycle latency is CONTRACT_ONLY.
    # DivUnit：除法器核心外的握手包装。SRT16 核心本身为另一锁定主体；本模型
    # 复现相同的请求/kill 协议，采用每周期一次迭代的恢复阵列与固定结果寄存器。
    # 除法器周期延迟为 CONTRACT_ONLY。
    p = self.ports
    busy = Signal(name="div_busy")
    valid_r = Signal(name="div_valid_r")
    data_r = Signal(64, name="div_data_r")
    a_r = Signal(64, name="div_a_r")
    b_r = Signal(64, name="div_b_r")
    sign_r = Signal(name="div_sign_r")
    isw_r = Signal(name="div_isw_r")
    ishi_r = Signal(name="div_ishi_r")
    func = p["io_in_bits_ctrl_fuOpType"]
    flush_v = p["io_flush_valid"]
    kill_w = _rob_need_flush(flush_v, p["io_flush_bits_robIdx_flag"], p["io_flush_bits_robIdx_value"], p["io_flush_bits_level"], p["io_in_bits_ctrl_robIdx_flag"], p["io_in_bits_ctrl_robIdx_value"])
    kill_r = Const(0, 1)
    kill_r = cast(Any, ~(cast(Any, valid_r))) & busy & _rob_need_flush(flush_v, p["io_flush_bits_robIdx_flag"], p["io_flush_bits_robIdx_value"], p["io_flush_bits_level"], p["io_in_bits_ctrl_robIdx_flag"], p["io_in_bits_ctrl_robIdx_value"])
    fire = p["io_in_valid"] & Mux(cast(Any, busy), 0, 1) & Mux(cast(Any, valid_r), 0, 1) & Mux(cast(Any, kill_w), 0, 1)
    is_sign = cast(Any, ~func[1:2])
    is_w = func[2:3]
    is_hi = func[0:1]
    src0 = p["io_in_bits_data_src_0"]
    src1 = p["io_in_bits_data_src_1"]
    cvt0 = Mux(is_w, Mux(is_sign, _sext(src0[0:32], 64), _zext(src0[0:32], 64)), src0)
    cvt1 = Mux(is_w, Mux(is_sign, _sext(src1[0:32], 64), _zext(src1[0:32], 64)), src1)
    with m.If(fire):
        m.d.sync += [
            busy.eq(1),
            a_r.eq(cvt0),
            b_r.eq(cvt1),
            sign_r.eq(is_sign),
            isw_r.eq(is_w),
            ishi_r.eq(is_hi),
            p["io_out_bits_ctrl_robIdx_flag"].eq(Const(0, 1)),
        ]
    div_done = Signal(name="div_done")
    m.d.comb += div_done.eq(busy)
    with m.If(div_done & ~kill_r):
        m.d.sync += [busy.eq(0), valid_r.eq(1)]
    with m.If(kill_r):
        m.d.sync += [busy.eq(0), valid_r.eq(0)]
    with m.If(p["io_out_ready"] & valid_r):
        m.d.sync += valid_r.eq(0)
    a_abs = Mux(a_r[63:64] & sign_r, (~a_r + Const(1, 64))[0:64], a_r)
    b_abs = Mux(b_r[63:64] & sign_r, (~b_r + Const(1, 64))[0:64], b_r)
    # Every restoring step is materialised as comb signals so the iteration
    # chain stays linear (Amaranth does not CSE shared subterms).
    # 每一步恢复迭代都落地为组合信号，使迭代链保持线性
    #（Amaranth 不会对共享子项做公共子表达式消除）。
    rem = Signal(65, name="div_rem_in")
    quot = Signal(64, name="div_quot_in")
    m.d.comb += [rem.eq(Const(0, 65)), quot.eq(Const(0, 64))]
    for i in range(63, -1, -1):
        rem_s = Signal(65, name="div_remS_%d" % i)
        diff = Signal(65, name="div_diff_%d" % i)
        ge = Signal(name="div_ge_%d" % i)
        rem_next = Signal(65, name="div_rem_%d" % i)
        quot_next = Signal(64, name="div_quot_%d" % i)
        m.d.comb += [
            rem_s.eq(Cat(rem[0:64], a_abs[i:i + 1])),
            diff.eq(rem_s - _pad(b_abs, 65)),
            ge.eq(cast(Any, ~(cast(Any, diff)[64:65]))),
            rem_next.eq(Mux(ge, diff, rem_s)),
            quot_next.eq(Cat(ge, quot[0:63])),
        ]
        rem, quot = rem_next, quot_next
    q_raw = quot
    r_raw = rem[0:64]
    q_fix = Mux(b_r == Const(0, 64), _zext(_or_reduce(Const(1, 1)).replicate(64), 64) if False else Const(0xffffffffffffffff, 64), q_raw)
    r_fix = Mux(b_r == Const(0, 64), a_abs, r_raw)
    q_signed = Mux((cast(Any, a_r[63:64]) ^ cast(Any, b_r[63:64])) & sign_r, (cast(Any, ~q_fix) + Const(1, 64))[0:64], q_fix)
    r_signed = Mux(a_r[63:64] & sign_r, (~r_fix + Const(1, 64))[0:64], r_fix)
    word_res = Mux(ishi_r, _sext(r_signed[0:32], 64), _sext(q_signed[0:32], 64))
    full_res = Mux(ishi_r, r_signed, q_signed)
    result = Mux(isw_r, word_res, full_res)
    with m.If(div_done & ~kill_r):
        m.d.sync += [data_r.eq(result), p["io_out_bits_ctrl_robIdx_flag"].eq(p["io_in_bits_ctrl_robIdx_flag"]),
                     p["io_out_bits_ctrl_robIdx_value"].eq(p["io_in_bits_ctrl_robIdx_value"]),
                     p["io_out_bits_ctrl_pdest"].eq(p["io_in_bits_ctrl_pdest"]),
                     p["io_out_bits_ctrl_rfWen"].eq(p["io_in_bits_ctrl_rfWen"])]
    m.d.comb += [
        p["io_in_ready"].eq(~busy & ~valid_r),
        p["io_out_valid"].eq(valid_r),
        p["io_out_bits_res_data"].eq(data_r),
    ]


def build_addr_add(self: "ExuFuncModule", m: Any) -> None:
    # AddrAddModule: branch target / sequential next address (pinned AddrAddModule.sv).
    # AddrAddModule：分支目标 / 顺序下一地址（钉死的 AddrAddModule.sv）。
    p = self.ports
    m.d.comb += p["io_target"].eq(addr_add_result(m, p["io_pcExtend"], p["io_taken"], p["io_imm"], p["io_nextPcOffset"], "aam"))


def build_std(self: "ExuFuncModule", m: Any) -> None:
    # Std: store-data pass-through with valid/ready handshake (pinned Std.sv).
    # Std：带 valid/ready 握手的存储数据透传（钉死的 Std.sv）。
    p = self.ports
    m.d.comb += [
        p["io_in_ready"].eq(p["io_out_ready"]),
        p["io_out_valid"].eq(p["io_in_valid"]),
        p["io_out_bits_ctrl_robIdx_value"].eq(p["io_in_bits_ctrl_robIdx_value"]),
        p["io_out_bits_res_data"].eq(p["io_in_bits_data_src_0"]),
    ]


def build_mem_exe_unit(self: "ExuFuncModule", m: Any) -> None:
    # MemExeUnit: store-data pass-through with uop sideband passthrough (pinned MemExeUnit.sv).
    # MemExeUnit：带 uop 边带透传的存储数据直通（钉死的 MemExeUnit.sv）。
    p = self.ports
    m.d.comb += [
        p["io_in_ready"].eq(p["io_out_ready"]),
        p["io_out_valid"].eq(p["io_in_valid"]),
        p["io_out_bits_uop_fuType"].eq(p["io_in_bits_uop_fuType"]),
        p["io_out_bits_uop_fuOpType"].eq(p["io_in_bits_uop_fuOpType"]),
        p["io_out_bits_uop_robIdx_value"].eq(p["io_in_bits_uop_robIdx_value"]),
        p["io_out_bits_uop_sqIdx_flag"].eq(p["io_in_bits_uop_sqIdx_flag"]),
        p["io_out_bits_uop_sqIdx_value"].eq(p["io_in_bits_uop_sqIdx_value"]),
        p["io_out_bits_data"].eq(p["io_in_bits_src_0"]),
    ]


def build_fence(self: "ExuFuncModule", m: Any) -> None:
    # Fence: six-state fence FSM driving sfence/fencei/sbuffer (upstream Fence.scala).
    # Fence：驱动 sfence/fencei/sbuffer 的六态 fence 状态机（upstream Fence.scala）。
    p = self.ports
    s_idle, s_wait, s_tlb, s_icache, s_fence, s_nofence = 0, 1, 2, 3, 4, 5
    state = Signal(3, name="fence_state")
    func_r = Signal(9, name="fence_func_r")
    flush_pipe_r = Signal(name="fence_flushPipe_r")
    rob_flag_r = Signal(name="fence_robFlag_r")
    rob_val_r = Signal(8, name="fence_robVal_r")
    pdest_r = Signal(8, name="fence_pdest_r")
    addr_r = Signal(64, name="fence_addr_r")
    id_r = Signal(16, name="fence_id_r")
    imm_r = Signal(64, name="fence_imm_r")
    src1 = p["io_in_bits_data_src_1"]
    use_vmid = func_r == Const(0b10100, 9)
    fire = (state == s_idle) & p["io_in_valid"]
    with m.If(fire):
        m.d.sync += [
            func_r.eq(p["io_in_bits_ctrl_fuOpType"]),
            flush_pipe_r.eq(p["io_in_bits_ctrl_flushPipe"]),
            rob_flag_r.eq(p["io_in_bits_ctrl_robIdx_flag"]),
            rob_val_r.eq(p["io_in_bits_ctrl_robIdx_value"]),
            pdest_r.eq(p["io_in_bits_ctrl_pdest"]),
            addr_r.eq(p["io_in_bits_data_src_0"]),
            imm_r.eq(p["io_in_bits_data_imm"]),
            id_r.eq(src1[0:16]),
        ]
    nxt = state
    with m.If((state == s_idle) & p["io_in_valid"]):
        m.d.sync += state.eq(s_wait)
    with m.If(state == s_wait):
        m.d.sync += state.eq(state)
        with m.If(p["io_fenceio_sbuffer_sbIsEmpty"]):
            with m.If(func_r == Const(0b10010, 9)):
                m.d.sync += state.eq(s_icache)
            with m.Elif((func_r == Const(0b10001, 9)) | (func_r == Const(0b10011, 9)) | (func_r == Const(0b10100, 9))):
                m.d.sync += state.eq(s_tlb)
            with m.Elif(func_r == Const(0b10000, 9)):
                m.d.sync += state.eq(s_fence)
            with m.Elif(func_r == Const(0b00000, 9)):
                m.d.sync += state.eq(s_nofence)
    with m.If((state != s_idle) & (state != s_wait)):
        m.d.sync += state.eq(s_idle)
    nxt = state
    m.d.comb += [
        p["io_in_ready"].eq(state == s_idle),
        p["io_out_valid"].eq((state != s_idle) & (state != s_wait)),
        p["io_out_bits_res_data"].eq(Const(0, 64)),
        p["io_out_bits_ctrl_robIdx_flag"].eq(rob_flag_r),
        p["io_out_bits_ctrl_robIdx_value"].eq(rob_val_r),
        p["io_out_bits_ctrl_pdest"].eq(pdest_r),
        p["io_out_bits_ctrl_flushPipe"].eq(flush_pipe_r),
        p["io_fenceio_sfence_valid"].eq((state == s_tlb) & ((func_r == Const(0b10001, 9)) | (func_r == Const(0b10011, 9)) | (func_r == Const(0b10100, 9)))),
        p["io_fenceio_sfence_bits_rs1"].eq(imm_r[0:5] == Const(0, 5)),
        p["io_fenceio_sfence_bits_rs2"].eq(imm_r[5:10] == Const(0, 5)),
        p["io_fenceio_sfence_bits_addr"].eq(addr_r[0:50]),
        p["io_fenceio_sfence_bits_id"].eq(Mux(use_vmid, Cat(Const(0, 2), id_r[0:14]), id_r)),
        p["io_fenceio_sfence_bits_flushPipe"].eq(flush_pipe_r),
        p["io_fenceio_sfence_bits_hv"].eq(func_r == Const(0b10011, 9)),
        p["io_fenceio_sfence_bits_hg"].eq(func_r == Const(0b10100, 9)),
        p["io_fenceio_fencei"].eq(state == s_icache),
        p["io_fenceio_sbuffer_flushSb"].eq(state == s_wait),
    ]


def build_branch_unit(self: "ExuFuncModule", m: Any) -> None:
    # BranchUnit: 0-latency branch resolution, AddrAddModule target and Redirect
    # bundle emission (upstream wrapper/BranchUnit.scala).
    # BranchUnit：0 延迟分支裁决、AddrAddModule 目标与 Redirect 包输出（upstream wrapper/BranchUnit.scala）。
    p = self.ports
    addr_trans = Cat(
        p["io_instrAddrTransType_bare"], p["io_instrAddrTransType_sv39"],
        p["io_instrAddrTransType_sv39x4"], p["io_instrAddrTransType_sv48"],
        p["io_instrAddrTransType_sv48x4"],
    )
    sext_pc = p["io_instrAddrTransType_sv39"] | p["io_instrAddrTransType_sv48"]
    pc_ext = Mux(sext_pc, _sext(p["io_in_bits_data_pc"], 51), _zext(p["io_in_bits_data_pc"], 51))
    taken, mispredict = branch_taken(m, p["io_in_bits_ctrl_fuOpType"], p["io_in_bits_data_src_0"], p["io_in_bits_data_src_1"], p["io_in_bits_ctrl_predictInfo_taken"], "bru")
    target = addr_add_result(m, pc_ext, taken, p["io_in_bits_data_imm"], p["io_in_bits_data_nextPcOffset"], "bru")
    iaf, ipf, igpf = check_faults(m, addr_trans, target, "bru")
    rd = "io_out_bits_res_redirect_bits_"
    m.d.comb += [
        p["io_out_valid"].eq(p["io_in_valid"]),
        p["io_out_bits_res_data"].eq(Const(0, 64)),
        p["io_out_bits_ctrl_robIdx_flag"].eq(p["io_in_bits_ctrl_robIdx_flag"]),
        p["io_out_bits_ctrl_robIdx_value"].eq(p["io_in_bits_ctrl_robIdx_value"]),
        p["io_out_bits_ctrl_pdest"].eq(p["io_in_bits_ctrl_pdest"]),
        p["io_out_bits_res_redirect_valid"].eq(p["io_out_valid"] & (mispredict | iaf | ipf | igpf)),
        p[rd + "level"].eq(Const(0, 1)),
        p[rd + "robIdx_flag"].eq(p["io_in_bits_ctrl_robIdx_flag"]),
        p[rd + "robIdx_value"].eq(p["io_in_bits_ctrl_robIdx_value"]),
        p[rd + "ftqIdx_flag"].eq(p["io_in_bits_ctrl_ftqIdx_flag"]),
        p[rd + "ftqIdx_value"].eq(p["io_in_bits_ctrl_ftqIdx_value"]),
        p[rd + "ftqOffset"].eq(p["io_in_bits_ctrl_ftqOffset"]),
        p[rd + "fullTarget"].eq(target),
        p[rd + "cfiUpdate_pc"].eq(p["io_in_bits_data_pc"]),
        p[rd + "cfiUpdate_target"].eq(target[0:50]),
        p[rd + "cfiUpdate_taken"].eq(taken),
        p[rd + "cfiUpdate_predTaken"].eq(p["io_in_bits_ctrl_predictInfo_taken"]),
        p[rd + "cfiUpdate_isMisPred"].eq(mispredict),
        p[rd + "cfiUpdate_backendIAF"].eq(iaf),
        p[rd + "cfiUpdate_backendIPF"].eq(ipf),
        p[rd + "cfiUpdate_backendIGPF"].eq(igpf),
    ]
    # Unmapped Redirect fields are held to zero, matching the 0.U.asTypeOf reset.
    # 未映射的 Redirect 字段保持为零，与 0.U.asTypeOf 复位一致。
    mapped = {
        "level", "robIdx_flag", "robIdx_value", "ftqIdx_flag", "ftqIdx_value", "ftqOffset",
        "fullTarget", "cfiUpdate_pc", "cfiUpdate_target", "cfiUpdate_taken",
        "cfiUpdate_predTaken", "cfiUpdate_isMisPred", "cfiUpdate_backendIAF",
        "cfiUpdate_backendIPF", "cfiUpdate_backendIGPF",
    }
    for spec in self.specs:
        if spec.name.startswith(rd):
            field = spec.name[len(rd):]
            if field not in mapped:
                m.d.comb += p[spec.name].eq(Const(0, spec.width))


def build_jump_unit(self: "ExuFuncModule", m: Any) -> None:
    # JumpUnit: 0-latency jump target computation and Redirect emission
    # (upstream wrapper/JumpUnit.scala + JumpDataModule).
    # JumpUnit：0 延迟跳转目标计算与 Redirect 输出（upstream wrapper/JumpUnit.scala）。
    p = self.ports
    func = p["io_in_bits_ctrl_fuOpType"]
    is_jalr = func[0:1]
    is_auipc = func[1:2]
    sext_pc = p["io_instrAddrTransType_sv39"] | p["io_instrAddrTransType_sv48"]
    pc = Mux(sext_pc, _sext(p["io_in_bits_data_pc"], 64), _zext(p["io_in_bits_data_pc"], 64))
    offset = _sext(p["io_in_bits_data_imm"][0:33], 64)
    snpc = pc + (cast(Any, Cat(Const(0, 59), p["io_in_bits_data_nextPcOffset"])) << 1)
    target_raw = Mux(is_jalr, p["io_in_bits_data_src_0"] + offset, pc + offset)
    target = Cat(target_raw[1:64], Const(0, 1))
    jmp_target = p["io_in_bits_ctrl_predictInfo_target"]
    pred_taken = p["io_in_bits_ctrl_predictInfo_taken"]
    mis_pred = (target[0:50] != jmp_target) | ~pred_taken
    iaf, ipf, igpf = check_faults(
        m,
        Cat(p["io_instrAddrTransType_bare"], p["io_instrAddrTransType_sv39"], p["io_instrAddrTransType_sv39x4"], p["io_instrAddrTransType_sv48"], p["io_instrAddrTransType_sv48x4"]),
        target,
        "jmu",
    )
    result = Mux(is_auipc, target, snpc)
    rd = "io_out_bits_res_redirect_bits_"
    m.d.comb += [
        p["io_out_valid"].eq(p["io_in_valid"]),
        p["io_out_bits_res_data"].eq(result),
        p["io_out_bits_ctrl_robIdx_flag"].eq(p["io_in_bits_ctrl_robIdx_flag"]),
        p["io_out_bits_ctrl_robIdx_value"].eq(p["io_in_bits_ctrl_robIdx_value"]),
        p["io_out_bits_ctrl_pdest"].eq(p["io_in_bits_ctrl_pdest"]),
        p["io_out_bits_ctrl_rfWen"].eq(p["io_in_bits_ctrl_rfWen"]),
        p["io_out_bits_res_redirect_valid"].eq(p["io_in_valid"] & cast(Any, ~(cast(Any, is_auipc))) & (cast(Any, mis_pred) | iaf | ipf | igpf)),
        p[rd + "level"].eq(Const(0, 1)),
        p[rd + "robIdx_flag"].eq(p["io_in_bits_ctrl_robIdx_flag"]),
        p[rd + "robIdx_value"].eq(p["io_in_bits_ctrl_robIdx_value"]),
        p[rd + "ftqIdx_flag"].eq(p["io_in_bits_ctrl_ftqIdx_flag"]),
        p[rd + "ftqIdx_value"].eq(p["io_in_bits_ctrl_ftqIdx_value"]),
        p[rd + "ftqOffset"].eq(p["io_in_bits_ctrl_ftqOffset"]),
        p[rd + "fullTarget"].eq(target),
        p[rd + "cfiUpdate_pc"].eq(p["io_in_bits_data_pc"]),
        p[rd + "cfiUpdate_target"].eq(target[0:50]),
        p[rd + "cfiUpdate_taken"].eq(Const(1, 1)),
        p[rd + "cfiUpdate_predTaken"].eq(Const(1, 1)),
        p[rd + "cfiUpdate_isMisPred"].eq(mis_pred),
        p[rd + "cfiUpdate_backendIAF"].eq(iaf),
        p[rd + "cfiUpdate_backendIPF"].eq(ipf),
        p[rd + "cfiUpdate_backendIGPF"].eq(igpf),
    ]
    mapped = {
        "level", "robIdx_flag", "robIdx_value", "ftqIdx_flag", "ftqIdx_value", "ftqOffset",
        "fullTarget", "cfiUpdate_pc", "cfiUpdate_target", "cfiUpdate_taken",
        "cfiUpdate_predTaken", "cfiUpdate_isMisPred", "cfiUpdate_backendIAF",
        "cfiUpdate_backendIPF", "cfiUpdate_backendIGPF",
    }
    for spec in self.specs:
        if spec.name.startswith(rd):
            field = spec.name[len(rd):]
            if field not in mapped:
                m.d.comb += p[spec.name].eq(Const(0, spec.width))


def build_exe_unit(self: "ExuFuncModule", m: Any) -> None:
    # ExeUnit: Dispatcher + Alu/MulUnit/Bku lanes with clock-gated mul/bku domains,
    # flush-cancelling inPipe and OR-combined writeback (pinned ExeUnit.sv).
    # ExeUnit：Dispatcher 加 Alu/MulUnit/Bku 三条通路，mul/bku 时钟门控、
    # 带 flush 取消的 inPipe 与或合并写回（钉死的 ExeUnit.sv）。
    p = self.ports
    func = p["io_in_bits_fuOpType"]
    src0 = p["io_in_bits_src_0"]
    src1 = p["io_in_bits_src_1"]
    flush_v = p["io_flush_valid"]
    flush_flag = p["io_flush_bits_robIdx_flag"]
    flush_val = p["io_flush_bits_robIdx_value"]
    flush_lvl = p["io_flush_bits_level"]
    # Dispatcher lane enables.
    disp0 = (p["io_in_bits_fuType"] == Const(0x40, 35)) & p["io_in_valid"]
    disp1 = (p["io_in_bits_fuType"] == Const(0x80, 35)) & p["io_in_valid"]
    disp2 = (p["io_in_bits_fuType"] == Const(0x400, 35)) & p["io_in_valid"]
    # Flush-cancelling inPipe (two ctrl stages + two valid stages).
    ip1_flag = Signal(name="inPipe_1_1_robIdx_flag")
    ip1_val = Signal(8, name="inPipe_1_1_robIdx_value")
    ip1_pdest = Signal(8, name="inPipe_1_1_pdest")
    ip1_rfwen = Signal(name="inPipe_1_1_rfWen")
    ip2_flag = Signal(name="inPipe_1_2_robIdx_flag")
    ip2_val = Signal(8, name="inPipe_1_2_robIdx_value")
    ip2_pdest = Signal(8, name="inPipe_1_2_pdest")
    ip2_rfwen = Signal(name="inPipe_1_2_rfWen")
    ipv1 = Signal(name="inPipe_2_1")
    ipv2 = Signal(name="inPipe_2_2")
    m.d.sync += [
        ip1_flag.eq(p["io_in_bits_robIdx_flag"]),
        ip1_val.eq(p["io_in_bits_robIdx_value"]),
        ip1_pdest.eq(p["io_in_bits_pdest"]),
        ip1_rfwen.eq(p["io_in_bits_rfWen"]),
        ip2_flag.eq(ip1_flag),
        ip2_val.eq(ip1_val),
        ip2_pdest.eq(ip1_pdest),
        ip2_rfwen.eq(ip1_rfwen),
    ]
    with m.If(p["io_in_valid"] & ~_rob_need_flush(flush_v, flush_flag, flush_val, flush_lvl, p["io_in_bits_robIdx_flag"], p["io_in_bits_robIdx_value"])):
        m.d.sync += ipv1.eq(1)
    with m.If(~p["io_in_valid"] | _rob_need_flush(flush_v, flush_flag, flush_val, flush_lvl, p["io_in_bits_robIdx_flag"], p["io_in_bits_robIdx_value"])):
        m.d.sync += ipv1.eq(0)
    with m.If(ipv1 & ~_rob_need_flush(flush_v, flush_flag, flush_val, flush_lvl, ip1_flag, ip1_val)):
        m.d.sync += ipv2.eq(1)
    with m.If(~ipv1 | _rob_need_flush(flush_v, flush_flag, flush_val, flush_lvl, ip1_flag, ip1_val)):
        m.d.sync += ipv2.eq(0)
    # Alu lane (combinational, ctrl taken straight from the inputs).
    alu_valid = disp0
    alu_res = alu_result(func, src0, src1)
    # MulUnit lane with gated clock enable.
    fv1 = Signal(name="fuVldVec_1")
    fv2 = Signal(name="fuVldVec_2")
    fv1r = Signal(name="fuVld_en_reg_1")
    fv2_1 = Signal(name="fuVldVec_2_1")
    fv2_2 = Signal(name="fuVldVec_2_2")
    fv2r = Signal(name="fuVld_en_reg_2")
    en1 = disp1 | fv1 | fv2 | fv1r
    en2 = disp2 | fv2_1 | fv2_2 | fv2r
    m_vvf1 = Signal(name="mul_validVecThisFu_1")
    m_vvf2 = Signal(name="mul_validVecThisFu_2")
    m_risw = Signal(name="mul_r_isW")
    m_rishi = Signal(name="mul_r_isHi")
    m_r1isw = Signal(name="mul_r1_isW")
    m_r1ishi = Signal(name="mul_r1_isHi")
    m_pp0 = Signal(130, name="mul_pp0")
    m_pp1 = Signal(130, name="mul_pp1")
    op = Cat(func[1:3], func[3:4])
    a65 = _zext(src0, 65)
    a65 = Mux((op == Const(1, 3)) | (op == Const(2, 3)), Cat(src0, src0[63:64]), a65)
    a65 = Mux(op == Const(4, 3), _zext(src0[0:7], 65), a65)
    b65 = Mux(op == Const(1, 3), Cat(src1, src1[63:64]), _zext(src1, 65))
    m_vv0 = disp1
    m_vv1 = ipv1 & m_vvf1
    with m.If(en1):
        m.d.sync += [fv1.eq(disp1), fv2.eq(fv1), fv1r.eq(disp1 | fv1 | fv2)]
        m.d.sync += m_vvf1.eq(disp1)
        m.d.sync += m_vvf2.eq(m_vvf1)
        with m.If(m_vv0):
            m.d.sync += [m_risw.eq(func[2:3]), m_rishi.eq(_or_reduce(func[0:2])), m_pp0.eq(a65.as_signed() * b65.as_signed())]
        with m.If(m_vv1):
            m.d.sync += [m_r1isw.eq(m_risw), m_r1ishi.eq(m_rishi), m_pp1.eq(m_pp0)]
    mul_valid = ipv2 & m_vvf2
    mul_res_raw = Mux(m_r1ishi, m_pp1[64:128], m_pp1[0:64])
    mul_res = Mux(m_r1isw, _sext(mul_res_raw[0:32], 64), mul_res_raw)
    # Bku lane with gated clock enable.
    b_vvf1 = Signal(name="bku_validVecThisFu_1")
    b_vvf2 = Signal(name="bku_validVecThisFu_2")
    b_func_r = Signal(9, name="bku_funcReg")
    b_res_r = Signal(64, name="bku_res_r")
    count = CountLeaf()
    clmul = ClmulLeaf()
    misc = MiscLeaf()
    crypto = CryptoLeaf()
    m.submodules.exu_count = count
    m.submodules.exu_clmul = clmul
    m.submodules.exu_misc = misc
    m.submodules.exu_crypto = crypto
    b_vv0 = disp2
    b_en2 = ipv1 & b_vvf1
    with m.If(en2):
        m.d.sync += [fv2_1.eq(disp2), fv2_2.eq(fv2_1), fv2r.eq(disp2 | fv2_1 | fv2_2)]
        m.d.sync += b_vvf1.eq(disp2)
        m.d.sync += b_vvf2.eq(b_vvf1)
        with m.If(disp2):
            m.d.sync += b_func_r.eq(func)
        with m.If(b_en2):
            m.d.sync += b_res_r.eq(Mux(b_func_r[5:6], crypto.out, Mux(b_func_r[3:4], count.out, Mux(b_func_r[2:3], misc.out, clmul.out))))
        m.d.comb += [
            count.clock.eq(p["clock"]),
            count.reg_enable.eq(disp2),
            count.src.eq(src0),
            count.func.eq(func),
            clmul.clock.eq(p["clock"]),
            clmul.reg_enable.eq(disp2),
            clmul.src0.eq(src0),
            clmul.src1.eq(src1),
            clmul.func.eq(func),
            misc.clock.eq(p["clock"]),
            misc.reg_enable.eq(disp2),
            misc.src0.eq(src0),
            misc.src1.eq(src1),
            misc.func.eq(func),
            crypto.clock.eq(p["clock"]),
            crypto.reg_enable.eq(disp2),
            crypto.src0.eq(src0),
            crypto.src1.eq(src1),
            crypto.func.eq(func),
        ]
    bku_valid = ipv2 & b_vvf2
    # OR-combined writeback.
    wb = lambda a, b, c: (a & b) | (a & c)
    wb = None
    m.d.comb += [
        p["io_out_valid"].eq(alu_valid | mul_valid | bku_valid),
        p["io_out_bits_data_0"].eq(
            Mux(alu_valid, alu_res, Const(0, 64))
            | Mux(mul_valid, mul_res, Const(0, 64))
            | Mux(bku_valid, b_res_r, Const(0, 64))
        ),
        p["io_out_bits_data_1"].eq(
            Mux(alu_valid, alu_res, Const(0, 64))
            | Mux(mul_valid, mul_res, Const(0, 64))
            | Mux(bku_valid, b_res_r, Const(0, 64))
        ),
        p["io_out_bits_pdest"].eq(
            Mux(alu_valid, p["io_in_bits_pdest"], Const(0, 8))
            | Mux(mul_valid, ip2_pdest, Const(0, 8))
            | Mux(bku_valid, ip2_pdest, Const(0, 8))
        ),
        p["io_out_bits_robIdx_flag"].eq(
            (alu_valid & p["io_in_bits_robIdx_flag"]) | (mul_valid & ip2_flag) | (bku_valid & ip2_flag)
        ),
        p["io_out_bits_robIdx_value"].eq(
            Mux(alu_valid, p["io_in_bits_robIdx_value"], Const(0, 8))
            | Mux(mul_valid, ip2_val, Const(0, 8))
            | Mux(bku_valid, ip2_val, Const(0, 8))
        ),
        p["io_out_bits_intWen"].eq(
            (alu_valid & p["io_in_bits_rfWen"]) | (mul_valid & ip2_rfwen) | (bku_valid & ip2_rfwen)
        ),
    ]


# Builder dispatch keyed by locked module name. / 按锁定模块名分派构造器。
BUILDERS: dict[str, Any] = {
    "Dispatcher": build_dispatcher,
    "Dispatcher_1": build_dispatcher,
    "Dispatcher_4": build_dispatcher,
    "Dispatcher_5": build_dispatcher,
    "Dispatcher_7": build_dispatcher,
    "Dispatcher_8": build_dispatcher,
    "Dispatcher_9": build_dispatcher,
    "Dispatcher_10": build_dispatcher,
    "Dispatcher_13": build_dispatcher,
    "Dispatcher_14": build_dispatcher,
    "Dispatcher_15": build_dispatcher,
    "Dispatcher_16": build_dispatcher,
    "Dispatcher_17": build_dispatcher,
    "ExeUnit": build_exe_unit,
    "MemExeUnit": build_mem_exe_unit,
    "Bku": build_bku,
    "CountModule": build_count,
    "ClmulModule": build_clmul,
    "MiscModule": build_misc,
    "HashModule": build_hash,
    "BlockCipherModule": build_blockcipher,
    "CryptoModule": build_crypto,
    "AddrAddModule": build_addr_add,
    "Std": build_std,
    "Fence": build_fence,
    "Alu": build_alu,
    "MulUnit": build_mul,
    "DivUnit": build_div,
    "BranchUnit": build_branch_unit,
    "JumpUnit": build_jump_unit,
}


class ExuFuncModule(Elaboratable):
    """One locked EXU/FuncUnit module with an exact port surface. / 一个端口面精确的锁定 EXU/FuncUnit 模块。"""

    # Construct the locked port surface and bind the module builder. / 构造锁定端口面并绑定构造器。
    def __init__(self, module_name: str, top_name: str | None = None) -> None:
        self.module_name = module_name
        self.top_name = top_name or module_name
        self.specs = [PortSpec(*p) for p in PORTS[module_name]]
        self.has_clock = any(s.name == "clock" for s in self.specs)
        self.has_reset = any(s.name == "reset" for s in self.specs)
        self.clock: Signal | None = Signal(name="clock") if self.has_clock else None
        self.reset: Signal | None = Signal(name="reset") if self.has_reset else None
        self.ports: dict[str, Signal] = {}
        self.ordered: list[Signal] = []
        if self.clock is not None:
            self.ordered.append(self.clock)
        if self.reset is not None:
            self.ordered.append(self.reset)
        for s in self.specs:
            sig = Signal(s.width, name=s.name)
            self.ports[s.name] = sig
            if s.name in ("clock", "reset"):
                continue
            self.ordered.append(sig)
        self.builder = BUILDERS[module_name]

    # Elaborate the module: wire the clock domain, then run the builder. / 展开模块：连接时钟域后运行构造器。
    def elaborate(self, platform: Any) -> Module:
        m = Module()
        if self.has_clock:
            dom = ClockDomain("sync", async_reset=self.has_reset)
            cast(Any, dom).clk = self.clock
            if self.has_reset:
                dom.rst = self.reset
            m.domains.sync = dom
        self.builder(self, m)
        return m

# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration, injected_dependencies):
    """Return Verilog text for the selected EXU/FuncUnit module. / 返回所选 EXU/FuncUnit 模块的 Verilog 文本。"""
    del injected_dependencies
    if isinstance(configuration, dict):
        name = str(configuration.get("module", "Bku"))
    elif configuration is None:
        name = "Bku"
    else:
        name = str(getattr(configuration, "module", "Bku"))
    if name not in PORTS:
        raise KeyError(name)
    inst = ExuFuncModule(name)
    return verilog.convert(inst, name=name, ports=inst.ordered, emit_src=False)

# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    """Print the default family export. / 打印默认 family 导出。"""
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
