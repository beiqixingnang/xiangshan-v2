"""V2 NewCSR parameterised CSR register family. / V2 NewCSR 参数化 CSR 寄存器族。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, cast

from amaranth import Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal, Value
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# ``CSRModule[T]`` in CSRModule.scala is one Chisel class instantiated once per
# CSR: a ``CSRBundle`` register file with a ``CSRW`` write port (``w_wen`` /
# ``w_wdata``), a masked read port (``rdata``), one unmasked observation port
# per field (``regOut_<field>``), an optional asynchronous reset carrying the
# bundle init literal, and field-level event updates appended by
# ``addOtherUpdate``.  This aggregate keeps that register network executable for
# the whole locked family while the per-module field set, write rules, internal
# temporaries and output equations are carried as a declarative manifest
# transcribed from the pinned V2 artifact ``build/rtl/XSTop.sv``.  Nothing here
# is inferred: a module is covered only when its manifest block decodes.
# CSRModule.scala 中的 ``CSRModule[T]`` 是一个 Chisel 类，每个 CSR 实例化一次：
# 带 ``w_wen``/``w_wdata`` 写口、``rdata`` 掩码读口、每字段一个 ``regOut_<field>``
# 观测口、可选异步复位（携带 bundle 初值字面量），以及由 ``addOtherUpdate``
# 追加的字段级事件更新。本聚合文件让整个锁定家族的寄存器网络可执行，各模块的字段
# 集合、写规则、内部临时信号与输出方程以声明式清单承载，清单逐条转录自锁定 V2
# 产物 ``build/rtl/XSTop.sv``。此处不做任何推测：只有清单块能解码的模块才算覆盖。
__all__ = [
    "CsrPortSpec",
    "CsrFieldSpec",
    "CsrWireSpec",
    "CsrAssignSpec",
    "CsrRuleSpec",
    "CsrModuleSpec",
    "CsrModuleFamilyConfig",
    "CSRModule",
    "csr_family_module_names",
    "csr_family_module_count",
    "csr_module_spec",
    "csr_module_port_specs",
    "csr_expression_tokens",
    "csr_expression_parse",
    "build_verilog",
    "main",
    "CSR_FAMILY_SOURCE_PATHS",
    "CSR_FAMILY_MODULE_COUNT",
]


# Frozen V2 source closure represented by this aggregate. / 本聚合表示的冻结 V2 源闭包。
CSR_FAMILY_SOURCE_PATHS: tuple[str, ...] = (
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/CSRModule.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/CSRBundle.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/CSRBundles.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/CSRFields.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/CSRDefines.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/InterruptBundle.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/ExceptionBundle.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/StateEnBundle.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/MachineLevel.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/SupervisorLevel.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/HypervisorLevel.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/VirtualSupervisorLevel.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/DebugLevel.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/Unprivileged.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/CSRPMP.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/CSRPMA.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/CSRAIA.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/CSRCustom.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/CSREvents/CSREvent.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/CSREvents/TrapEntryMEvent.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/CSREvents/TrapEntryHSEvent.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/CSREvents/TrapEntryVSEvent.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/CSREvents/TrapEntryDEvent.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/CSREvents/TrapEntryMNEvent.scala",
)


# =============================================================================
# Configuration
# =============================================================================
# The manifest is the family's declarative specification, one line per locked
# fact.  Line kinds, in the order the decoder expects them inside a block:
#   ``M <module> <a|n>``     module name and reset mode (a=async, n=none)
#   ``P <i|o> <name> <w>``   one locked port in locked order
#   ``F <name> <w> <init|->`` one sequential register, ``-`` meaning no reset
#   ``W <name> <w> = <expr>`` combinational signal with an inline definition
#   ``D <name> <w>``          combinational signal declared without a value
#   ``V <name> <w> [= <expr>]`` combinational temporary (FIRRTL ``automatic``)
#   ``S <reg> ? <guard> : <expr>`` sequential rule, highest priority first
#   ``V <tmp> ? <guard> : <expr>`` guarded combinational update of a temporary
#   ``A <target> = <expr>``   continuous assignment (``rdata``, ``regOut_*`` ...)
# Expressions use the Verilog subset that FIRRTL emitted for this family.
# 清单即本家族的声明式规格，每行一条锁定事实。行种类按块内出现顺序为：模块与复位
# 模式、锁定顺序端口、时序寄存器、带定义线网、仅声明线网、组合临时量、时序规则
# （优先级由高到低）、临时量的带条件更新、连续赋值。表达式使用 FIRRTL 在本家族中
# 生成的 Verilog 子集。
CSR_FAMILY_MANIFEST = """\
M perfEventsModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
F reg_OF 1 0
F reg_MINH 1 0
F reg_SINH 1 0
F reg_UINH 1 0
F reg_VSINH 1 0
F reg_VUINH 1 0
F reg_OPTYPE2 5 0
F reg_OPTYPE1 5 0
F reg_OPTYPE0 5 0
F reg_EVENT3 10 0
F reg_EVENT2 10 0
F reg_EVENT1 10 0
F reg_EVENT0 10 0
S reg_OF ? w_wen : w_wdata[63]
S reg_MINH ? w_wen : w_wdata[62]
S reg_SINH ? w_wen : w_wdata[61]
S reg_UINH ? w_wen : w_wdata[60]
S reg_VSINH ? w_wen : w_wdata[59]
S reg_VUINH ? w_wen : w_wdata[58]
S reg_EVENT3 ? w_wen : w_wdata[39:30]
S reg_EVENT2 ? w_wen : w_wdata[29:20]
S reg_EVENT1 ? w_wen : w_wdata[19:10]
S reg_EVENT0 ? w_wen : w_wdata[9:0]
S reg_OPTYPE2 ? w_wen & (w_wdata[54:50] == 5'h0 | w_wdata[54:50] == 5'h1 | w_wdata[54:50] == 5'h2 | w_wdata[54:50] == 5'h4) : w_wdata[54:50]
S reg_OPTYPE1 ? w_wen & (w_wdata[49:45] == 5'h0 | w_wdata[49:45] == 5'h1 | w_wdata[49:45] == 5'h2 | w_wdata[49:45] == 5'h4) : w_wdata[49:45]
S reg_OPTYPE0 ? w_wen & (w_wdata[44:40] == 5'h0 | w_wdata[44:40] == 5'h1 | w_wdata[44:40] == 5'h2 | w_wdata[44:40] == 5'h4) : w_wdata[44:40]
A rdata = {reg_OF, reg_MINH, reg_SINH, reg_UINH, reg_VSINH, reg_VUINH, 3'h0, reg_OPTYPE2, reg_OPTYPE1, reg_OPTYPE0, reg_EVENT3, reg_EVENT2, reg_EVENT1, reg_EVENT0}
M MbmcModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_BMA 58
P o regOut_KEYIDEN 1
P o regOut_BME 1
P o regOut_BCLEAR 1
P o regOut_CMODE 1
F reg_BMA 58 0
F reg_KEYIDEN 1 0
F reg_BME 1 0
F reg_BCLEAR 1 0
F reg_CMODE 1 0
S reg_BMA ? w_wen & ~reg_BME : w_wdata[63:6]
S reg_KEYIDEN ? w_wen : w_wdata[3]
S reg_CMODE ? w_wen : w_wdata[0]
S reg_BME ? w_wen & ~reg_BME : w_wdata[2]
S reg_BCLEAR ? 1'h1 : ~reg_BCLEAR & w_wen & w_wdata[1]
A rdata = {reg_BMA, 2'h0, reg_KEYIDEN, reg_BME, reg_BCLEAR, reg_CMODE}
A regOut_BMA = reg_BMA
A regOut_KEYIDEN = reg_KEYIDEN
A regOut_BME = reg_BME
A regOut_BCLEAR = reg_BCLEAR
A regOut_CMODE = reg_CMODE
M MStatusModule n
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_SIE 1
P o regOut_MIE 1
P o regOut_SPIE 1
P o regOut_MPIE 1
P o regOut_SPP 1
P o regOut_VS 2
P o regOut_MPP 2
P o regOut_FS 2
P o regOut_MPRV 1
P o regOut_SUM 1
P o regOut_MXR 1
P o regOut_TVM 1
P o regOut_TW 1
P o regOut_TSR 1
P o regOut_SDT 1
P o regOut_GVA 1
P o regOut_MPV 1
P o regOut_MDT 1
P i trapToM_mstatus_valid 1
P i trapToM_mstatus_bits_MIE 1
P i trapToM_mstatus_bits_MPIE 1
P i trapToM_mstatus_bits_MPP 2
P i trapToM_mstatus_bits_GVA 1
P i trapToM_mstatus_bits_MPV 1
P i trapToM_mstatus_bits_MDT 1
P i trapToHS_mstatus_valid 1
P i trapToHS_mstatus_bits_SIE 1
P i trapToHS_mstatus_bits_SPIE 1
P i trapToHS_mstatus_bits_SPP 1
P i trapToHS_mstatus_bits_SDT 1
P i retFromD_mstatus_valid 1
P i retFromD_mstatus_bits_MPRV 1
P i retFromD_mstatus_bits_SDT 1
P i retFromD_mstatus_bits_MDT 1
P i retFromM_mstatus_valid 1
P i retFromM_mstatus_bits_MIE 1
P i retFromM_mstatus_bits_MPIE 1
P i retFromM_mstatus_bits_MPP 2
P i retFromM_mstatus_bits_MPRV 1
P i retFromM_mstatus_bits_SDT 1
P i retFromM_mstatus_bits_MPV 1
P i retFromM_mstatus_bits_MDT 1
P i retFromMN_mstatus_valid 1
P i retFromMN_mstatus_bits_MPRV 1
P i retFromMN_mstatus_bits_SDT 1
P i retFromMN_mstatus_bits_MDT 1
P i retFromS_mstatus_valid 1
P i retFromS_mstatus_bits_SIE 1
P i retFromS_mstatus_bits_SPIE 1
P i retFromS_mstatus_bits_SPP 1
P i retFromS_mstatus_bits_MPRV 1
P i retFromS_mstatus_bits_SDT 1
P i retFromS_mstatus_bits_MDT 1
P i robCommit_fsDirty 1
P i robCommit_vsDirty 1
P i robCommit_vstart_valid 1
P i robCommit_vstart_bits 7
P i writeFCSR 1
P i writeVCSR 1
P i menvcfg_DTE 1
P o sstatus_SIE 1
P o sstatus_SPIE 1
P o sstatus_SPP 1
P o sstatus_VS 2
P o sstatus_FS 2
P o sstatus_SUM 1
P o sstatus_MXR 1
P o sstatus_SDT 1
P o sstatus_SD 1
P o sstatusRdata 64
P i wAliasSstatus_wen 1
P i wAliasSstatus_wdata 64
F reg_SIE 1 -
F reg_MIE 1 -
F reg_SPIE 1 -
F reg_MPIE 1 -
F reg_SPP 1 -
F reg_VS 2 -
F reg_MPP 2 -
F reg_FS 2 -
F reg_MPRV 1 -
F reg_SUM 1 -
F reg_MXR 1 -
F reg_TVM 1 -
F reg_TW 1 -
F reg_TSR 1 -
F reg_SDT 1 -
F reg_GVA 1 -
F reg_MPV 1 -
F reg_MDT 1 -
W _GEN 1 = robCommit_fsDirty | writeFCSR
W _GEN_0 1 = robCommit_vsDirty | writeVCSR | robCommit_vstart_valid & (|robCommit_vstart_bits)
W _mstatus_SD_T_3 1 = (&reg_FS) | (&reg_VS)
W _sstatus_SDT_WIRE 1 = reg_SDT & menvcfg_DTE
V _GEN_1 1 = trapToM_mstatus_valid | retFromM_mstatus_valid
V _GEN_2 1 = w_wen | _GEN_1
V _GEN_3 1
V _GEN_4 1 = w_wen | trapToHS_mstatus_valid | retFromS_mstatus_valid | wAliasSstatus_wen
A rdata = {_mstatus_SD_T_3, 20'h0, reg_MDT, 2'h0, reg_MPV, reg_GVA, 13'h500, reg_SDT, 1'h0, reg_TSR, reg_TW, reg_TVM, reg_MXR, reg_SUM, reg_MPRV, 2'h0, reg_FS, reg_MPP, reg_VS, reg_SPP, reg_MPIE, 1'h0, reg_SPIE, 1'h0, reg_MIE, 1'h0, reg_SIE, 1'h0}
A regOut_SIE = reg_SIE
A regOut_MIE = reg_MIE
A regOut_SPIE = reg_SPIE
A regOut_MPIE = reg_MPIE
A regOut_SPP = reg_SPP
A regOut_VS = reg_VS
A regOut_MPP = reg_MPP
A regOut_FS = reg_FS
A regOut_MPRV = reg_MPRV
A regOut_SUM = reg_SUM
A regOut_MXR = reg_MXR
A regOut_TVM = reg_TVM
A regOut_TW = reg_TW
A regOut_TSR = reg_TSR
A regOut_SDT = reg_SDT
A regOut_GVA = reg_GVA
A regOut_MPV = reg_MPV
A regOut_MDT = reg_MDT
A sstatus_SIE = reg_SIE
A sstatus_SPIE = reg_SPIE
A sstatus_SPP = reg_SPP
A sstatus_VS = reg_VS
A sstatus_FS = reg_FS
A sstatus_SUM = reg_SUM
A sstatus_MXR = reg_MXR
A sstatus_SDT = _sstatus_SDT_WIRE
A sstatus_SD = _mstatus_SD_T_3
A sstatusRdata = {_mstatus_SD_T_3, 38'h100, _sstatus_SDT_WIRE, 4'h0, reg_MXR, reg_SUM, 3'h0, reg_FS, 2'h0, reg_VS, reg_SPP, 2'h0, reg_SPIE, 3'h0, reg_SIE, 1'h0}
M MedelegModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_EX_IAM 1
P o regOut_EX_IAF 1
P o regOut_EX_II 1
P o regOut_EX_BP 1
P o regOut_EX_LAM 1
P o regOut_EX_LAF 1
P o regOut_EX_SAM 1
P o regOut_EX_SAF 1
P o regOut_EX_UCALL 1
P o regOut_EX_HSCALL 1
P o regOut_EX_VSCALL 1
P o regOut_EX_IPF 1
P o regOut_EX_LPF 1
P o regOut_EX_SPF 1
P o regOut_EX_SWC 1
P o regOut_EX_HWE 1
P o regOut_EX_IGPF 1
P o regOut_EX_LGPF 1
P o regOut_EX_VI 1
P o regOut_EX_SGPF 1
F reg_EX_IAM 1 0
F reg_EX_IAF 1 0
F reg_EX_II 1 0
F reg_EX_BP 1 0
F reg_EX_LAM 1 0
F reg_EX_LAF 1 0
F reg_EX_SAM 1 0
F reg_EX_SAF 1 0
F reg_EX_UCALL 1 0
F reg_EX_HSCALL 1 0
F reg_EX_VSCALL 1 0
F reg_EX_IPF 1 0
F reg_EX_LPF 1 0
F reg_EX_SPF 1 0
F reg_EX_SWC 1 0
F reg_EX_HWE 1 0
F reg_EX_IGPF 1 0
F reg_EX_LGPF 1 0
F reg_EX_VI 1 0
F reg_EX_SGPF 1 0
S reg_EX_IAM ? w_wen : w_wdata[0]
S reg_EX_IAF ? w_wen : w_wdata[1]
S reg_EX_II ? w_wen : w_wdata[2]
S reg_EX_BP ? w_wen : w_wdata[3]
S reg_EX_LAM ? w_wen : w_wdata[4]
S reg_EX_LAF ? w_wen : w_wdata[5]
S reg_EX_SAM ? w_wen : w_wdata[6]
S reg_EX_SAF ? w_wen : w_wdata[7]
S reg_EX_UCALL ? w_wen : w_wdata[8]
S reg_EX_HSCALL ? w_wen : w_wdata[9]
S reg_EX_VSCALL ? w_wen : w_wdata[10]
S reg_EX_IPF ? w_wen : w_wdata[12]
S reg_EX_LPF ? w_wen : w_wdata[13]
S reg_EX_SPF ? w_wen : w_wdata[15]
S reg_EX_SWC ? w_wen : w_wdata[18]
S reg_EX_HWE ? w_wen : w_wdata[19]
S reg_EX_IGPF ? w_wen : w_wdata[20]
S reg_EX_LGPF ? w_wen : w_wdata[21]
S reg_EX_VI ? w_wen : w_wdata[22]
S reg_EX_SGPF ? w_wen : w_wdata[23]
A rdata = {40'h0, reg_EX_SGPF, reg_EX_VI, reg_EX_LGPF, reg_EX_IGPF, reg_EX_HWE, reg_EX_SWC, 2'h0, reg_EX_SPF, 1'h0, reg_EX_LPF, reg_EX_IPF, 1'h0, reg_EX_VSCALL, reg_EX_HSCALL, reg_EX_UCALL, reg_EX_SAF, reg_EX_SAM, reg_EX_LAF, reg_EX_LAM, reg_EX_BP, reg_EX_II, reg_EX_IAF, reg_EX_IAM}
A regOut_EX_IAM = reg_EX_IAM
A regOut_EX_IAF = reg_EX_IAF
A regOut_EX_II = reg_EX_II
A regOut_EX_BP = reg_EX_BP
A regOut_EX_LAM = reg_EX_LAM
A regOut_EX_LAF = reg_EX_LAF
A regOut_EX_SAM = reg_EX_SAM
A regOut_EX_SAF = reg_EX_SAF
A regOut_EX_UCALL = reg_EX_UCALL
A regOut_EX_HSCALL = reg_EX_HSCALL
A regOut_EX_VSCALL = reg_EX_VSCALL
A regOut_EX_IPF = reg_EX_IPF
A regOut_EX_LPF = reg_EX_LPF
A regOut_EX_SPF = reg_EX_SPF
A regOut_EX_SWC = reg_EX_SWC
A regOut_EX_HWE = reg_EX_HWE
A regOut_EX_IGPF = reg_EX_IGPF
A regOut_EX_LGPF = reg_EX_LGPF
A regOut_EX_VI = reg_EX_VI
A regOut_EX_SGPF = reg_EX_SGPF
M MidelegModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_SSI 1
P o regOut_STI 1
P o regOut_SEI 1
P o regOut_LCOFI 1
F reg_SSI 1 0
F reg_STI 1 0
F reg_SEI 1 0
F reg_LCOFI 1 0
S reg_SSI ? w_wen : w_wdata[1]
S reg_STI ? w_wen : w_wdata[5]
S reg_SEI ? w_wen : w_wdata[9]
S reg_LCOFI ? w_wen : w_wdata[13]
A rdata = {50'h0, reg_LCOFI, 3'h5, reg_SEI, 3'h1, reg_STI, 3'h1, reg_SSI, 1'h0}
A regOut_SSI = reg_SSI
A regOut_STI = reg_STI
A regOut_SEI = reg_SEI
A regOut_LCOFI = reg_LCOFI
M MieModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_SSIE 1
P o regOut_VSSIE 1
P o regOut_MSIE 1
P o regOut_STIE 1
P o regOut_VSTIE 1
P o regOut_MTIE 1
P o regOut_SEIE 1
P o regOut_VSEIE 1
P o regOut_MEIE 1
P o regOut_SGEIE 1
P o regOut_LCOFIE 1
P i fromHie_VSSIE_valid 1
P i fromHie_VSSIE_bits 1
P i fromHie_VSTIE_valid 1
P i fromHie_VSTIE_bits 1
P i fromHie_VSEIE_valid 1
P i fromHie_VSEIE_bits 1
P i fromHie_SGEIE_valid 1
P i fromHie_SGEIE_bits 1
P i fromSie_SSIE_valid 1
P i fromSie_SSIE_bits 1
P i fromSie_STIE_valid 1
P i fromSie_STIE_bits 1
P i fromSie_SEIE_valid 1
P i fromSie_SEIE_bits 1
P i fromSie_LCOFIE_valid 1
P i fromSie_LCOFIE_bits 1
P i fromVSie_VSSIE_valid 1
P i fromVSie_VSSIE_bits 1
P i fromVSie_VSTIE_valid 1
P i fromVSie_VSTIE_bits 1
P i fromVSie_VSEIE_valid 1
P i fromVSie_VSEIE_bits 1
P i fromVSie_LCOFIE_valid 1
P i fromVSie_LCOFIE_bits 1
F reg_SSIE 1 0
F reg_VSSIE 1 0
F reg_MSIE 1 0
F reg_STIE 1 0
F reg_VSTIE 1 0
F reg_MTIE 1 0
F reg_SEIE 1 0
F reg_VSEIE 1 0
F reg_MEIE 1 0
F reg_SGEIE 1 0
F reg_LCOFIE 1 0
S reg_SSIE ? fromSie_SSIE_valid : fromSie_SSIE_bits
S reg_SSIE ? !(fromSie_SSIE_valid) & w_wen : w_wdata[1]
S reg_VSSIE ? fromHie_VSSIE_valid | fromVSie_VSSIE_valid : fromHie_VSSIE_valid & fromHie_VSSIE_bits | fromVSie_VSSIE_valid & fromVSie_VSSIE_bits
S reg_VSSIE ? !(fromHie_VSSIE_valid | fromVSie_VSSIE_valid) & w_wen : w_wdata[2]
S reg_MSIE ? w_wen : w_wdata[3]
S reg_MTIE ? w_wen : w_wdata[7]
S reg_MEIE ? w_wen : w_wdata[11]
S reg_STIE ? fromSie_STIE_valid : fromSie_STIE_bits
S reg_STIE ? !(fromSie_STIE_valid) & w_wen : w_wdata[5]
S reg_VSTIE ? fromHie_VSTIE_valid | fromVSie_VSTIE_valid : fromHie_VSTIE_valid & fromHie_VSTIE_bits | fromVSie_VSTIE_valid & fromVSie_VSTIE_bits
S reg_VSTIE ? !(fromHie_VSTIE_valid | fromVSie_VSTIE_valid) & w_wen : w_wdata[6]
S reg_SEIE ? fromSie_SEIE_valid : fromSie_SEIE_bits
S reg_SEIE ? !(fromSie_SEIE_valid) & w_wen : w_wdata[9]
S reg_VSEIE ? fromHie_VSEIE_valid | fromVSie_VSEIE_valid : fromHie_VSEIE_valid & fromHie_VSEIE_bits | fromVSie_VSEIE_valid & fromVSie_VSEIE_bits
S reg_VSEIE ? !(fromHie_VSEIE_valid | fromVSie_VSEIE_valid) & w_wen : w_wdata[10]
S reg_SGEIE ? fromHie_SGEIE_valid : fromHie_SGEIE_bits
S reg_SGEIE ? !(fromHie_SGEIE_valid) & w_wen : w_wdata[12]
S reg_LCOFIE ? fromSie_LCOFIE_valid | fromVSie_LCOFIE_valid : fromSie_LCOFIE_valid & fromSie_LCOFIE_bits | fromVSie_LCOFIE_valid & fromVSie_LCOFIE_bits
S reg_LCOFIE ? !(fromSie_LCOFIE_valid | fromVSie_LCOFIE_valid) & w_wen : w_wdata[13]
A rdata = {50'h0, reg_LCOFIE, reg_SGEIE, reg_MEIE, reg_VSEIE, reg_SEIE, 1'h0, reg_MTIE, reg_VSTIE, reg_STIE, 1'h0, reg_MSIE, reg_VSSIE, reg_SSIE, 1'h0}
A regOut_SSIE = reg_SSIE
A regOut_VSSIE = reg_VSSIE
A regOut_MSIE = reg_MSIE
A regOut_STIE = reg_STIE
A regOut_VSTIE = reg_VSTIE
A regOut_MTIE = reg_MTIE
A regOut_SEIE = reg_SEIE
A regOut_VSEIE = reg_VSEIE
A regOut_MEIE = reg_MEIE
A regOut_SGEIE = reg_SGEIE
A regOut_LCOFIE = reg_LCOFIE
M MtvecModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_mode 2
P o regOut_addr 62
F reg_mode 2 0
F reg_addr 62 0
S reg_mode ? w_wen & (w_wdata[1:0] == 2'h0 | w_wdata[1:0] == 2'h1) : w_wdata[1:0]
S reg_addr ? w_wen : w_wdata[63:2]
A rdata = {reg_addr, reg_mode}
A regOut_mode = reg_mode
A regOut_addr = reg_addr
M McounterenModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_CY 1
P o regOut_TM 1
P o regOut_IR 1
P o regOut_HPM 29
F reg_CY 1 0
F reg_TM 1 0
F reg_IR 1 0
F reg_HPM 29 0
S reg_CY ? w_wen : w_wdata[0]
S reg_TM ? w_wen : w_wdata[1]
S reg_IR ? w_wen : w_wdata[2]
S reg_HPM ? w_wen : w_wdata[31:3]
A rdata = {32'h0, reg_HPM, reg_IR, reg_TM, reg_CY}
A regOut_CY = reg_CY
A regOut_TM = reg_TM
A regOut_IR = reg_IR
A regOut_HPM = reg_HPM
M MvienModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_SSIE 1
P o regOut_SEIE 1
P o regOut_LC14IE 1
P o regOut_LC15IE 1
P o regOut_LC16IE 1
P o regOut_LC17IE 1
P o regOut_LC18IE 1
P o regOut_LC19IE 1
P o regOut_LC20IE 1
P o regOut_LC21IE 1
P o regOut_LC22IE 1
P o regOut_LC23IE 1
P o regOut_LC24IE 1
P o regOut_LC25IE 1
P o regOut_LC26IE 1
P o regOut_LC27IE 1
P o regOut_LC28IE 1
P o regOut_LC29IE 1
P o regOut_LC30IE 1
P o regOut_LC31IE 1
P o regOut_LC32IE 1
P o regOut_LC33IE 1
P o regOut_LC34IE 1
P o regOut_LPRASEIE 1
P o regOut_LC36IE 1
P o regOut_LC37IE 1
P o regOut_LC38IE 1
P o regOut_LC39IE 1
P o regOut_LC40IE 1
P o regOut_LC41IE 1
P o regOut_LC42IE 1
P o regOut_HPRASEIE 1
P o regOut_LC44IE 1
P o regOut_LC45IE 1
P o regOut_LC46IE 1
P o regOut_LC47IE 1
P o regOut_LC48IE 1
P o regOut_LC49IE 1
P o regOut_LC50IE 1
P o regOut_LC51IE 1
P o regOut_LC52IE 1
P o regOut_LC53IE 1
P o regOut_LC54IE 1
P o regOut_LC55IE 1
P o regOut_LC56IE 1
P o regOut_LC57IE 1
P o regOut_LC58IE 1
P o regOut_LC59IE 1
P o regOut_LC60IE 1
P o regOut_LC61IE 1
P o regOut_LC62IE 1
P o regOut_LC63IE 1
F reg_SSIE 1 0
F reg_SEIE 1 0
F reg_LC14IE 1 0
F reg_LC15IE 1 0
F reg_LC16IE 1 0
F reg_LC17IE 1 0
F reg_LC18IE 1 0
F reg_LC19IE 1 0
F reg_LC20IE 1 0
F reg_LC21IE 1 0
F reg_LC22IE 1 0
F reg_LC23IE 1 0
F reg_LC24IE 1 0
F reg_LC25IE 1 0
F reg_LC26IE 1 0
F reg_LC27IE 1 0
F reg_LC28IE 1 0
F reg_LC29IE 1 0
F reg_LC30IE 1 0
F reg_LC31IE 1 0
F reg_LC32IE 1 0
F reg_LC33IE 1 0
F reg_LC34IE 1 0
F reg_LPRASEIE 1 0
F reg_LC36IE 1 0
F reg_LC37IE 1 0
F reg_LC38IE 1 0
F reg_LC39IE 1 0
F reg_LC40IE 1 0
F reg_LC41IE 1 0
F reg_LC42IE 1 0
F reg_HPRASEIE 1 0
F reg_LC44IE 1 0
F reg_LC45IE 1 0
F reg_LC46IE 1 0
F reg_LC47IE 1 0
F reg_LC48IE 1 0
F reg_LC49IE 1 0
F reg_LC50IE 1 0
F reg_LC51IE 1 0
F reg_LC52IE 1 0
F reg_LC53IE 1 0
F reg_LC54IE 1 0
F reg_LC55IE 1 0
F reg_LC56IE 1 0
F reg_LC57IE 1 0
F reg_LC58IE 1 0
F reg_LC59IE 1 0
F reg_LC60IE 1 0
F reg_LC61IE 1 0
F reg_LC62IE 1 0
F reg_LC63IE 1 0
S reg_SSIE ? w_wen : w_wdata[1]
S reg_SEIE ? w_wen : w_wdata[9]
S reg_LC14IE ? w_wen : w_wdata[14]
S reg_LC15IE ? w_wen : w_wdata[15]
S reg_LC16IE ? w_wen : w_wdata[16]
S reg_LC17IE ? w_wen : w_wdata[17]
S reg_LC18IE ? w_wen : w_wdata[18]
S reg_LC19IE ? w_wen : w_wdata[19]
S reg_LC20IE ? w_wen : w_wdata[20]
S reg_LC21IE ? w_wen : w_wdata[21]
S reg_LC22IE ? w_wen : w_wdata[22]
S reg_LC23IE ? w_wen : w_wdata[23]
S reg_LC24IE ? w_wen : w_wdata[24]
S reg_LC25IE ? w_wen : w_wdata[25]
S reg_LC26IE ? w_wen : w_wdata[26]
S reg_LC27IE ? w_wen : w_wdata[27]
S reg_LC28IE ? w_wen : w_wdata[28]
S reg_LC29IE ? w_wen : w_wdata[29]
S reg_LC30IE ? w_wen : w_wdata[30]
S reg_LC31IE ? w_wen : w_wdata[31]
S reg_LC32IE ? w_wen : w_wdata[32]
S reg_LC33IE ? w_wen : w_wdata[33]
S reg_LC34IE ? w_wen : w_wdata[34]
S reg_LPRASEIE ? w_wen : w_wdata[35]
S reg_LC36IE ? w_wen : w_wdata[36]
S reg_LC37IE ? w_wen : w_wdata[37]
S reg_LC38IE ? w_wen : w_wdata[38]
S reg_LC39IE ? w_wen : w_wdata[39]
S reg_LC40IE ? w_wen : w_wdata[40]
S reg_LC41IE ? w_wen : w_wdata[41]
S reg_LC42IE ? w_wen : w_wdata[42]
S reg_HPRASEIE ? w_wen : w_wdata[43]
S reg_LC44IE ? w_wen : w_wdata[44]
S reg_LC45IE ? w_wen : w_wdata[45]
S reg_LC46IE ? w_wen : w_wdata[46]
S reg_LC47IE ? w_wen : w_wdata[47]
S reg_LC48IE ? w_wen : w_wdata[48]
S reg_LC49IE ? w_wen : w_wdata[49]
S reg_LC50IE ? w_wen : w_wdata[50]
S reg_LC51IE ? w_wen : w_wdata[51]
S reg_LC52IE ? w_wen : w_wdata[52]
S reg_LC53IE ? w_wen : w_wdata[53]
S reg_LC54IE ? w_wen : w_wdata[54]
S reg_LC55IE ? w_wen : w_wdata[55]
S reg_LC56IE ? w_wen : w_wdata[56]
S reg_LC57IE ? w_wen : w_wdata[57]
S reg_LC58IE ? w_wen : w_wdata[58]
S reg_LC59IE ? w_wen : w_wdata[59]
S reg_LC60IE ? w_wen : w_wdata[60]
S reg_LC61IE ? w_wen : w_wdata[61]
S reg_LC62IE ? w_wen : w_wdata[62]
S reg_LC63IE ? w_wen : w_wdata[63]
A rdata = {reg_LC63IE, reg_LC62IE, reg_LC61IE, reg_LC60IE, reg_LC59IE, reg_LC58IE, reg_LC57IE, reg_LC56IE, reg_LC55IE, reg_LC54IE, reg_LC53IE, reg_LC52IE, reg_LC51IE, reg_LC50IE, reg_LC49IE, reg_LC48IE, reg_LC47IE, reg_LC46IE, reg_LC45IE, reg_LC44IE, reg_HPRASEIE, reg_LC42IE, reg_LC41IE, reg_LC40IE, reg_LC39IE, reg_LC38IE, reg_LC37IE, reg_LC36IE, reg_LPRASEIE, reg_LC34IE, reg_LC33IE, reg_LC32IE, reg_LC31IE, reg_LC30IE, reg_LC29IE, reg_LC28IE, reg_LC27IE, reg_LC26IE, reg_LC25IE, reg_LC24IE, reg_LC23IE, reg_LC22IE, reg_LC21IE, reg_LC20IE, reg_LC19IE, reg_LC18IE, reg_LC17IE, reg_LC16IE, reg_LC15IE, reg_LC14IE, 4'h0, reg_SEIE, 7'h0, reg_SSIE, 1'h0}
A regOut_SSIE = reg_SSIE
A regOut_SEIE = reg_SEIE
A regOut_LC14IE = reg_LC14IE
A regOut_LC15IE = reg_LC15IE
A regOut_LC16IE = reg_LC16IE
A regOut_LC17IE = reg_LC17IE
A regOut_LC18IE = reg_LC18IE
A regOut_LC19IE = reg_LC19IE
A regOut_LC20IE = reg_LC20IE
A regOut_LC21IE = reg_LC21IE
A regOut_LC22IE = reg_LC22IE
A regOut_LC23IE = reg_LC23IE
A regOut_LC24IE = reg_LC24IE
A regOut_LC25IE = reg_LC25IE
A regOut_LC26IE = reg_LC26IE
A regOut_LC27IE = reg_LC27IE
A regOut_LC28IE = reg_LC28IE
A regOut_LC29IE = reg_LC29IE
A regOut_LC30IE = reg_LC30IE
A regOut_LC31IE = reg_LC31IE
A regOut_LC32IE = reg_LC32IE
A regOut_LC33IE = reg_LC33IE
A regOut_LC34IE = reg_LC34IE
A regOut_LPRASEIE = reg_LPRASEIE
A regOut_LC36IE = reg_LC36IE
A regOut_LC37IE = reg_LC37IE
A regOut_LC38IE = reg_LC38IE
A regOut_LC39IE = reg_LC39IE
A regOut_LC40IE = reg_LC40IE
A regOut_LC41IE = reg_LC41IE
A regOut_LC42IE = reg_LC42IE
A regOut_HPRASEIE = reg_HPRASEIE
A regOut_LC44IE = reg_LC44IE
A regOut_LC45IE = reg_LC45IE
A regOut_LC46IE = reg_LC46IE
A regOut_LC47IE = reg_LC47IE
A regOut_LC48IE = reg_LC48IE
A regOut_LC49IE = reg_LC49IE
A regOut_LC50IE = reg_LC50IE
A regOut_LC51IE = reg_LC51IE
A regOut_LC52IE = reg_LC52IE
A regOut_LC53IE = reg_LC53IE
A regOut_LC54IE = reg_LC54IE
A regOut_LC55IE = reg_LC55IE
A regOut_LC56IE = reg_LC56IE
A regOut_LC57IE = reg_LC57IE
A regOut_LC58IE = reg_LC58IE
A regOut_LC59IE = reg_LC59IE
A regOut_LC60IE = reg_LC60IE
A regOut_LC61IE = reg_LC61IE
A regOut_LC62IE = reg_LC62IE
A regOut_LC63IE = reg_LC63IE
M MvipModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_SSIP 1
P o regOut_STIP 1
P o regOut_SEIP 1
P o regOut_LCOFIP 1
P o regOut_LC14IP 1
P o regOut_LC15IP 1
P o regOut_LC16IP 1
P o regOut_LC17IP 1
P o regOut_LC18IP 1
P o regOut_LC19IP 1
P o regOut_LC20IP 1
P o regOut_LC21IP 1
P o regOut_LC22IP 1
P o regOut_LC23IP 1
P o regOut_LC24IP 1
P o regOut_LC25IP 1
P o regOut_LC26IP 1
P o regOut_LC27IP 1
P o regOut_LC28IP 1
P o regOut_LC29IP 1
P o regOut_LC30IP 1
P o regOut_LC31IP 1
P o regOut_LC32IP 1
P o regOut_LC33IP 1
P o regOut_LC34IP 1
P o regOut_LPRASEIP 1
P o regOut_LC36IP 1
P o regOut_LC37IP 1
P o regOut_LC38IP 1
P o regOut_LC39IP 1
P o regOut_LC40IP 1
P o regOut_LC41IP 1
P o regOut_LC42IP 1
P o regOut_HPRASEIP 1
P o regOut_LC44IP 1
P o regOut_LC45IP 1
P o regOut_LC46IP 1
P o regOut_LC47IP 1
P o regOut_LC48IP 1
P o regOut_LC49IP 1
P o regOut_LC50IP 1
P o regOut_LC51IP 1
P o regOut_LC52IP 1
P o regOut_LC53IP 1
P o regOut_LC54IP 1
P o regOut_LC55IP 1
P o regOut_LC56IP 1
P o regOut_LC57IP 1
P o regOut_LC58IP 1
P o regOut_LC59IP 1
P o regOut_LC60IP 1
P o regOut_LC61IP 1
P o regOut_LC62IP 1
P o regOut_LC63IP 1
P i mip_SSIP 1
P i mip_STIP 1
P i mvien_SSIE 1
P i menvcfg_STCE 1
P o toMip_SSIP_valid 1
P o toMip_SSIP_bits 1
P o toMip_STIP_valid 1
P o toMip_STIP_bits 1
P i fromMip_SEIP_valid 1
P i fromMip_SEIP_bits 1
P i fromSip_SSIP_valid 1
P i fromSip_SSIP_bits 1
P i fromSip_LCOFIP_valid 1
P i fromSip_LCOFIP_bits 1
P i fromSip_LC14IP_valid 1
P i fromSip_LC14IP_bits 1
P i fromSip_LC15IP_valid 1
P i fromSip_LC15IP_bits 1
P i fromSip_LC16IP_valid 1
P i fromSip_LC16IP_bits 1
P i fromSip_LC17IP_valid 1
P i fromSip_LC17IP_bits 1
P i fromSip_LC18IP_valid 1
P i fromSip_LC18IP_bits 1
P i fromSip_LC19IP_valid 1
P i fromSip_LC19IP_bits 1
P i fromSip_LC20IP_valid 1
P i fromSip_LC20IP_bits 1
P i fromSip_LC21IP_valid 1
P i fromSip_LC21IP_bits 1
P i fromSip_LC22IP_valid 1
P i fromSip_LC22IP_bits 1
P i fromSip_LC23IP_valid 1
P i fromSip_LC23IP_bits 1
P i fromSip_LC24IP_valid 1
P i fromSip_LC24IP_bits 1
P i fromSip_LC25IP_valid 1
P i fromSip_LC25IP_bits 1
P i fromSip_LC26IP_valid 1
P i fromSip_LC26IP_bits 1
P i fromSip_LC27IP_valid 1
P i fromSip_LC27IP_bits 1
P i fromSip_LC28IP_valid 1
P i fromSip_LC28IP_bits 1
P i fromSip_LC29IP_valid 1
P i fromSip_LC29IP_bits 1
P i fromSip_LC30IP_valid 1
P i fromSip_LC30IP_bits 1
P i fromSip_LC31IP_valid 1
P i fromSip_LC31IP_bits 1
P i fromSip_LC32IP_valid 1
P i fromSip_LC32IP_bits 1
P i fromSip_LC33IP_valid 1
P i fromSip_LC33IP_bits 1
P i fromSip_LC34IP_valid 1
P i fromSip_LC34IP_bits 1
P i fromSip_LPRASEIP_valid 1
P i fromSip_LPRASEIP_bits 1
P i fromSip_LC36IP_valid 1
P i fromSip_LC36IP_bits 1
P i fromSip_LC37IP_valid 1
P i fromSip_LC37IP_bits 1
P i fromSip_LC38IP_valid 1
P i fromSip_LC38IP_bits 1
P i fromSip_LC39IP_valid 1
P i fromSip_LC39IP_bits 1
P i fromSip_LC40IP_valid 1
P i fromSip_LC40IP_bits 1
P i fromSip_LC41IP_valid 1
P i fromSip_LC41IP_bits 1
P i fromSip_LC42IP_valid 1
P i fromSip_LC42IP_bits 1
P i fromSip_HPRASEIP_valid 1
P i fromSip_HPRASEIP_bits 1
P i fromSip_LC44IP_valid 1
P i fromSip_LC44IP_bits 1
P i fromSip_LC45IP_valid 1
P i fromSip_LC45IP_bits 1
P i fromSip_LC46IP_valid 1
P i fromSip_LC46IP_bits 1
P i fromSip_LC47IP_valid 1
P i fromSip_LC47IP_bits 1
P i fromSip_LC48IP_valid 1
P i fromSip_LC48IP_bits 1
P i fromSip_LC49IP_valid 1
P i fromSip_LC49IP_bits 1
P i fromSip_LC50IP_valid 1
P i fromSip_LC50IP_bits 1
P i fromSip_LC51IP_valid 1
P i fromSip_LC51IP_bits 1
P i fromSip_LC52IP_valid 1
P i fromSip_LC52IP_bits 1
P i fromSip_LC53IP_valid 1
P i fromSip_LC53IP_bits 1
P i fromSip_LC54IP_valid 1
P i fromSip_LC54IP_bits 1
P i fromSip_LC55IP_valid 1
P i fromSip_LC55IP_bits 1
P i fromSip_LC56IP_valid 1
P i fromSip_LC56IP_bits 1
P i fromSip_LC57IP_valid 1
P i fromSip_LC57IP_bits 1
P i fromSip_LC58IP_valid 1
P i fromSip_LC58IP_bits 1
P i fromSip_LC59IP_valid 1
P i fromSip_LC59IP_bits 1
P i fromSip_LC60IP_valid 1
P i fromSip_LC60IP_bits 1
P i fromSip_LC61IP_valid 1
P i fromSip_LC61IP_bits 1
P i fromSip_LC62IP_valid 1
P i fromSip_LC62IP_bits 1
P i fromSip_LC63IP_valid 1
P i fromSip_LC63IP_bits 1
F reg_SSIP 1 0
F reg_SEIP 1 0
F reg_LCOFIP 1 0
F reg_LC14IP 1 0
F reg_LC15IP 1 0
F reg_LC16IP 1 0
F reg_LC17IP 1 0
F reg_LC18IP 1 0
F reg_LC19IP 1 0
F reg_LC20IP 1 0
F reg_LC21IP 1 0
F reg_LC22IP 1 0
F reg_LC23IP 1 0
F reg_LC24IP 1 0
F reg_LC25IP 1 0
F reg_LC26IP 1 0
F reg_LC27IP 1 0
F reg_LC28IP 1 0
F reg_LC29IP 1 0
F reg_LC30IP 1 0
F reg_LC31IP 1 0
F reg_LC32IP 1 0
F reg_LC33IP 1 0
F reg_LC34IP 1 0
F reg_LPRASEIP 1 0
F reg_LC36IP 1 0
F reg_LC37IP 1 0
F reg_LC38IP 1 0
F reg_LC39IP 1 0
F reg_LC40IP 1 0
F reg_LC41IP 1 0
F reg_LC42IP 1 0
F reg_HPRASEIP 1 0
F reg_LC44IP 1 0
F reg_LC45IP 1 0
F reg_LC46IP 1 0
F reg_LC47IP 1 0
F reg_LC48IP 1 0
F reg_LC49IP 1 0
F reg_LC50IP 1 0
F reg_LC51IP 1 0
F reg_LC52IP 1 0
F reg_LC53IP 1 0
F reg_LC54IP 1 0
F reg_LC55IP 1 0
F reg_LC56IP 1 0
F reg_LC57IP 1 0
F reg_LC58IP 1 0
F reg_LC59IP 1 0
F reg_LC60IP 1 0
F reg_LC61IP 1 0
F reg_LC62IP 1 0
F reg_LC63IP 1 0
D _regOut_STIP_WIRE 1
D _regOut_SSIP_output 1
S reg_SSIP ? fromSip_SSIP_valid : fromSip_SSIP_bits
S reg_SSIP ? !(fromSip_SSIP_valid) & w_wen & mvien_SSIE : w_wdata[1]
S reg_SEIP ? fromMip_SEIP_valid : fromMip_SEIP_bits
S reg_SEIP ? !(fromMip_SEIP_valid) & w_wen : w_wdata[9]
S reg_LCOFIP ? fromSip_LCOFIP_valid : fromSip_LCOFIP_valid & fromSip_LCOFIP_bits
S reg_LC14IP ? fromSip_LC14IP_valid : fromSip_LC14IP_valid & fromSip_LC14IP_bits
S reg_LC14IP ? !(fromSip_LC14IP_valid) & w_wen : w_wdata[14]
S reg_LC15IP ? fromSip_LC15IP_valid : fromSip_LC15IP_valid & fromSip_LC15IP_bits
S reg_LC15IP ? !(fromSip_LC15IP_valid) & w_wen : w_wdata[15]
S reg_LC16IP ? fromSip_LC16IP_valid : fromSip_LC16IP_valid & fromSip_LC16IP_bits
S reg_LC16IP ? !(fromSip_LC16IP_valid) & w_wen : w_wdata[16]
S reg_LC17IP ? fromSip_LC17IP_valid : fromSip_LC17IP_valid & fromSip_LC17IP_bits
S reg_LC17IP ? !(fromSip_LC17IP_valid) & w_wen : w_wdata[17]
S reg_LC18IP ? fromSip_LC18IP_valid : fromSip_LC18IP_valid & fromSip_LC18IP_bits
S reg_LC18IP ? !(fromSip_LC18IP_valid) & w_wen : w_wdata[18]
S reg_LC19IP ? fromSip_LC19IP_valid : fromSip_LC19IP_valid & fromSip_LC19IP_bits
S reg_LC19IP ? !(fromSip_LC19IP_valid) & w_wen : w_wdata[19]
S reg_LC20IP ? fromSip_LC20IP_valid : fromSip_LC20IP_valid & fromSip_LC20IP_bits
S reg_LC20IP ? !(fromSip_LC20IP_valid) & w_wen : w_wdata[20]
S reg_LC21IP ? fromSip_LC21IP_valid : fromSip_LC21IP_valid & fromSip_LC21IP_bits
S reg_LC21IP ? !(fromSip_LC21IP_valid) & w_wen : w_wdata[21]
S reg_LC22IP ? fromSip_LC22IP_valid : fromSip_LC22IP_valid & fromSip_LC22IP_bits
S reg_LC22IP ? !(fromSip_LC22IP_valid) & w_wen : w_wdata[22]
S reg_LC23IP ? fromSip_LC23IP_valid : fromSip_LC23IP_valid & fromSip_LC23IP_bits
S reg_LC23IP ? !(fromSip_LC23IP_valid) & w_wen : w_wdata[23]
S reg_LC24IP ? fromSip_LC24IP_valid : fromSip_LC24IP_valid & fromSip_LC24IP_bits
S reg_LC24IP ? !(fromSip_LC24IP_valid) & w_wen : w_wdata[24]
S reg_LC25IP ? fromSip_LC25IP_valid : fromSip_LC25IP_valid & fromSip_LC25IP_bits
S reg_LC25IP ? !(fromSip_LC25IP_valid) & w_wen : w_wdata[25]
S reg_LC26IP ? fromSip_LC26IP_valid : fromSip_LC26IP_valid & fromSip_LC26IP_bits
S reg_LC26IP ? !(fromSip_LC26IP_valid) & w_wen : w_wdata[26]
S reg_LC27IP ? fromSip_LC27IP_valid : fromSip_LC27IP_valid & fromSip_LC27IP_bits
S reg_LC27IP ? !(fromSip_LC27IP_valid) & w_wen : w_wdata[27]
S reg_LC28IP ? fromSip_LC28IP_valid : fromSip_LC28IP_valid & fromSip_LC28IP_bits
S reg_LC28IP ? !(fromSip_LC28IP_valid) & w_wen : w_wdata[28]
S reg_LC29IP ? fromSip_LC29IP_valid : fromSip_LC29IP_valid & fromSip_LC29IP_bits
S reg_LC29IP ? !(fromSip_LC29IP_valid) & w_wen : w_wdata[29]
S reg_LC30IP ? fromSip_LC30IP_valid : fromSip_LC30IP_valid & fromSip_LC30IP_bits
S reg_LC30IP ? !(fromSip_LC30IP_valid) & w_wen : w_wdata[30]
S reg_LC31IP ? fromSip_LC31IP_valid : fromSip_LC31IP_valid & fromSip_LC31IP_bits
S reg_LC31IP ? !(fromSip_LC31IP_valid) & w_wen : w_wdata[31]
S reg_LC32IP ? fromSip_LC32IP_valid : fromSip_LC32IP_valid & fromSip_LC32IP_bits
S reg_LC32IP ? !(fromSip_LC32IP_valid) & w_wen : w_wdata[32]
S reg_LC33IP ? fromSip_LC33IP_valid : fromSip_LC33IP_valid & fromSip_LC33IP_bits
S reg_LC33IP ? !(fromSip_LC33IP_valid) & w_wen : w_wdata[33]
S reg_LC34IP ? fromSip_LC34IP_valid : fromSip_LC34IP_valid & fromSip_LC34IP_bits
S reg_LC34IP ? !(fromSip_LC34IP_valid) & w_wen : w_wdata[34]
S reg_LPRASEIP ? fromSip_LPRASEIP_valid : fromSip_LPRASEIP_valid & fromSip_LPRASEIP_bits
S reg_LPRASEIP ? !(fromSip_LPRASEIP_valid) & w_wen : w_wdata[35]
S reg_LC36IP ? fromSip_LC36IP_valid : fromSip_LC36IP_valid & fromSip_LC36IP_bits
S reg_LC36IP ? !(fromSip_LC36IP_valid) & w_wen : w_wdata[36]
S reg_LC37IP ? fromSip_LC37IP_valid : fromSip_LC37IP_valid & fromSip_LC37IP_bits
S reg_LC37IP ? !(fromSip_LC37IP_valid) & w_wen : w_wdata[37]
S reg_LC38IP ? fromSip_LC38IP_valid : fromSip_LC38IP_valid & fromSip_LC38IP_bits
S reg_LC38IP ? !(fromSip_LC38IP_valid) & w_wen : w_wdata[38]
S reg_LC39IP ? fromSip_LC39IP_valid : fromSip_LC39IP_valid & fromSip_LC39IP_bits
S reg_LC39IP ? !(fromSip_LC39IP_valid) & w_wen : w_wdata[39]
S reg_LC40IP ? fromSip_LC40IP_valid : fromSip_LC40IP_valid & fromSip_LC40IP_bits
S reg_LC40IP ? !(fromSip_LC40IP_valid) & w_wen : w_wdata[40]
S reg_LC41IP ? fromSip_LC41IP_valid : fromSip_LC41IP_valid & fromSip_LC41IP_bits
S reg_LC41IP ? !(fromSip_LC41IP_valid) & w_wen : w_wdata[41]
S reg_LC42IP ? fromSip_LC42IP_valid : fromSip_LC42IP_valid & fromSip_LC42IP_bits
S reg_LC42IP ? !(fromSip_LC42IP_valid) & w_wen : w_wdata[42]
S reg_HPRASEIP ? fromSip_HPRASEIP_valid : fromSip_HPRASEIP_valid & fromSip_HPRASEIP_bits
S reg_HPRASEIP ? !(fromSip_HPRASEIP_valid) & w_wen : w_wdata[43]
S reg_LC44IP ? fromSip_LC44IP_valid : fromSip_LC44IP_valid & fromSip_LC44IP_bits
S reg_LC44IP ? !(fromSip_LC44IP_valid) & w_wen : w_wdata[44]
S reg_LC45IP ? fromSip_LC45IP_valid : fromSip_LC45IP_valid & fromSip_LC45IP_bits
S reg_LC45IP ? !(fromSip_LC45IP_valid) & w_wen : w_wdata[45]
S reg_LC46IP ? fromSip_LC46IP_valid : fromSip_LC46IP_valid & fromSip_LC46IP_bits
S reg_LC46IP ? !(fromSip_LC46IP_valid) & w_wen : w_wdata[46]
S reg_LC47IP ? fromSip_LC47IP_valid : fromSip_LC47IP_valid & fromSip_LC47IP_bits
S reg_LC47IP ? !(fromSip_LC47IP_valid) & w_wen : w_wdata[47]
S reg_LC48IP ? fromSip_LC48IP_valid : fromSip_LC48IP_valid & fromSip_LC48IP_bits
S reg_LC48IP ? !(fromSip_LC48IP_valid) & w_wen : w_wdata[48]
S reg_LC49IP ? fromSip_LC49IP_valid : fromSip_LC49IP_valid & fromSip_LC49IP_bits
S reg_LC49IP ? !(fromSip_LC49IP_valid) & w_wen : w_wdata[49]
S reg_LC50IP ? fromSip_LC50IP_valid : fromSip_LC50IP_valid & fromSip_LC50IP_bits
S reg_LC50IP ? !(fromSip_LC50IP_valid) & w_wen : w_wdata[50]
S reg_LC51IP ? fromSip_LC51IP_valid : fromSip_LC51IP_valid & fromSip_LC51IP_bits
S reg_LC51IP ? !(fromSip_LC51IP_valid) & w_wen : w_wdata[51]
S reg_LC52IP ? fromSip_LC52IP_valid : fromSip_LC52IP_valid & fromSip_LC52IP_bits
S reg_LC52IP ? !(fromSip_LC52IP_valid) & w_wen : w_wdata[52]
S reg_LC53IP ? fromSip_LC53IP_valid : fromSip_LC53IP_valid & fromSip_LC53IP_bits
S reg_LC53IP ? !(fromSip_LC53IP_valid) & w_wen : w_wdata[53]
S reg_LC54IP ? fromSip_LC54IP_valid : fromSip_LC54IP_valid & fromSip_LC54IP_bits
S reg_LC54IP ? !(fromSip_LC54IP_valid) & w_wen : w_wdata[54]
S reg_LC55IP ? fromSip_LC55IP_valid : fromSip_LC55IP_valid & fromSip_LC55IP_bits
S reg_LC55IP ? !(fromSip_LC55IP_valid) & w_wen : w_wdata[55]
S reg_LC56IP ? fromSip_LC56IP_valid : fromSip_LC56IP_valid & fromSip_LC56IP_bits
S reg_LC56IP ? !(fromSip_LC56IP_valid) & w_wen : w_wdata[56]
S reg_LC57IP ? fromSip_LC57IP_valid : fromSip_LC57IP_valid & fromSip_LC57IP_bits
S reg_LC57IP ? !(fromSip_LC57IP_valid) & w_wen : w_wdata[57]
S reg_LC58IP ? fromSip_LC58IP_valid : fromSip_LC58IP_valid & fromSip_LC58IP_bits
S reg_LC58IP ? !(fromSip_LC58IP_valid) & w_wen : w_wdata[58]
S reg_LC59IP ? fromSip_LC59IP_valid : fromSip_LC59IP_valid & fromSip_LC59IP_bits
S reg_LC59IP ? !(fromSip_LC59IP_valid) & w_wen : w_wdata[59]
S reg_LC60IP ? fromSip_LC60IP_valid : fromSip_LC60IP_valid & fromSip_LC60IP_bits
S reg_LC60IP ? !(fromSip_LC60IP_valid) & w_wen : w_wdata[60]
S reg_LC61IP ? fromSip_LC61IP_valid : fromSip_LC61IP_valid & fromSip_LC61IP_bits
S reg_LC61IP ? !(fromSip_LC61IP_valid) & w_wen : w_wdata[61]
S reg_LC62IP ? fromSip_LC62IP_valid : fromSip_LC62IP_valid & fromSip_LC62IP_bits
S reg_LC62IP ? !(fromSip_LC62IP_valid) & w_wen : w_wdata[62]
S reg_LC63IP ? fromSip_LC63IP_valid : fromSip_LC63IP_valid & fromSip_LC63IP_bits
S reg_LC63IP ? !(fromSip_LC63IP_valid) & w_wen : w_wdata[63]
A _regOut_SSIP_output = mvien_SSIE ? reg_SSIP : mip_SSIP
A _regOut_STIP_WIRE = ~menvcfg_STCE & mip_STIP
A rdata = {reg_LC63IP, reg_LC62IP, reg_LC61IP, reg_LC60IP, reg_LC59IP, reg_LC58IP, reg_LC57IP, reg_LC56IP, reg_LC55IP, reg_LC54IP, reg_LC53IP, reg_LC52IP, reg_LC51IP, reg_LC50IP, reg_LC49IP, reg_LC48IP, reg_LC47IP, reg_LC46IP, reg_LC45IP, reg_LC44IP, reg_HPRASEIP, reg_LC42IP, reg_LC41IP, reg_LC40IP, reg_LC39IP, reg_LC38IP, reg_LC37IP, reg_LC36IP, reg_LPRASEIP, reg_LC34IP, reg_LC33IP, reg_LC32IP, reg_LC31IP, reg_LC30IP, reg_LC29IP, reg_LC28IP, reg_LC27IP, reg_LC26IP, reg_LC25IP, reg_LC24IP, reg_LC23IP, reg_LC22IP, reg_LC21IP, reg_LC20IP, reg_LC19IP, reg_LC18IP, reg_LC17IP, reg_LC16IP, reg_LC15IP, reg_LC14IP, reg_LCOFIP, 3'h0, reg_SEIP, 3'h0, _regOut_STIP_WIRE, 3'h0, _regOut_SSIP_output, 1'h0}
A regOut_SSIP = _regOut_SSIP_output
A regOut_STIP = _regOut_STIP_WIRE
A regOut_SEIP = reg_SEIP
A regOut_LCOFIP = reg_LCOFIP
A regOut_LC14IP = reg_LC14IP
A regOut_LC15IP = reg_LC15IP
A regOut_LC16IP = reg_LC16IP
A regOut_LC17IP = reg_LC17IP
A regOut_LC18IP = reg_LC18IP
A regOut_LC19IP = reg_LC19IP
A regOut_LC20IP = reg_LC20IP
A regOut_LC21IP = reg_LC21IP
A regOut_LC22IP = reg_LC22IP
A regOut_LC23IP = reg_LC23IP
A regOut_LC24IP = reg_LC24IP
A regOut_LC25IP = reg_LC25IP
A regOut_LC26IP = reg_LC26IP
A regOut_LC27IP = reg_LC27IP
A regOut_LC28IP = reg_LC28IP
A regOut_LC29IP = reg_LC29IP
A regOut_LC30IP = reg_LC30IP
A regOut_LC31IP = reg_LC31IP
A regOut_LC32IP = reg_LC32IP
A regOut_LC33IP = reg_LC33IP
A regOut_LC34IP = reg_LC34IP
A regOut_LPRASEIP = reg_LPRASEIP
A regOut_LC36IP = reg_LC36IP
A regOut_LC37IP = reg_LC37IP
A regOut_LC38IP = reg_LC38IP
A regOut_LC39IP = reg_LC39IP
A regOut_LC40IP = reg_LC40IP
A regOut_LC41IP = reg_LC41IP
A regOut_LC42IP = reg_LC42IP
A regOut_HPRASEIP = reg_HPRASEIP
A regOut_LC44IP = reg_LC44IP
A regOut_LC45IP = reg_LC45IP
A regOut_LC46IP = reg_LC46IP
A regOut_LC47IP = reg_LC47IP
A regOut_LC48IP = reg_LC48IP
A regOut_LC49IP = reg_LC49IP
A regOut_LC50IP = reg_LC50IP
A regOut_LC51IP = reg_LC51IP
A regOut_LC52IP = reg_LC52IP
A regOut_LC53IP = reg_LC53IP
A regOut_LC54IP = reg_LC54IP
A regOut_LC55IP = reg_LC55IP
A regOut_LC56IP = reg_LC56IP
A regOut_LC57IP = reg_LC57IP
A regOut_LC58IP = reg_LC58IP
A regOut_LC59IP = reg_LC59IP
A regOut_LC60IP = reg_LC60IP
A regOut_LC61IP = reg_LC61IP
A regOut_LC62IP = reg_LC62IP
A regOut_LC63IP = reg_LC63IP
A toMip_SSIP_valid = w_wen & ~mvien_SSIE
A toMip_SSIP_bits = w_wdata[1]
A toMip_STIP_valid = w_wen & ~menvcfg_STCE
A toMip_STIP_bits = w_wdata[5]
M MenvcfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_STCE 1
P o regOut_PBMTE 1
P o regOut_DTE 1
P o regOut_PMM 2
P o regOut_CBZE 1
P o regOut_CBCFE 1
P o regOut_CBIE 2
F reg_STCE 1 1
F reg_PBMTE 1 0
F reg_DTE 1 0
F reg_PMM 2 0
F reg_CBZE 1 1
F reg_CBCFE 1 1
F reg_CBIE 2 3
S reg_STCE ? w_wen : w_wdata[63]
S reg_PBMTE ? w_wen : w_wdata[62]
S reg_DTE ? w_wen : w_wdata[59]
S reg_CBZE ? w_wen : w_wdata[7]
S reg_CBCFE ? w_wen : w_wdata[6]
S reg_PMM ? w_wen & (w_wdata[33:32] == 2'h0 | w_wdata[33:32] == 2'h2 | (&(w_wdata[33:32]))) : w_wdata[33:32]
S reg_CBIE ? w_wen & (w_wdata[5:4] == 2'h0 | w_wdata[5:4] == 2'h1 | (&(w_wdata[5:4]))) : w_wdata[5:4]
A rdata = {reg_STCE, reg_PBMTE, 2'h0, reg_DTE, 25'h0, reg_PMM, 24'h0, reg_CBZE, reg_CBCFE, reg_CBIE, 4'h0}
A regOut_STCE = reg_STCE
A regOut_PBMTE = reg_PBMTE
A regOut_DTE = reg_DTE
A regOut_PMM = reg_PMM
A regOut_CBZE = reg_CBZE
A regOut_CBCFE = reg_CBCFE
A regOut_CBIE = reg_CBIE
M McountinhibitModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_CY 1
P o regOut_IR 1
P o regOut_HPM3 29
F reg_CY 1 0
F reg_IR 1 0
F reg_HPM3 29 0
S reg_CY ? w_wen : w_wdata[0]
S reg_IR ? w_wen : w_wdata[2]
S reg_HPM3 ? w_wen : w_wdata[31:3]
A rdata = {32'h0, reg_HPM3, reg_IR, 1'h0, reg_CY}
A regOut_CY = reg_CY
A regOut_IR = reg_IR
A regOut_HPM3 = reg_HPM3
M MhpmeventModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_OF 1
P o regOut_MINH 1
P o regOut_SINH 1
P o regOut_UINH 1
P o regOut_VSINH 1
P o regOut_VUINH 1
P o regOut_OPTYPE2 5
P o regOut_OPTYPE1 5
P o regOut_OPTYPE0 5
P o regOut_EVENT3 10
P o regOut_EVENT2 10
P o regOut_EVENT1 10
P o regOut_EVENT0 10
P i ofFromPerfCnt 1
F reg_OF 1 0
F reg_MINH 1 0
F reg_SINH 1 0
F reg_UINH 1 0
F reg_VSINH 1 0
F reg_VUINH 1 0
F reg_OPTYPE2 5 0
F reg_OPTYPE1 5 0
F reg_OPTYPE0 5 0
F reg_EVENT3 10 0
F reg_EVENT2 10 0
F reg_EVENT1 10 0
F reg_EVENT0 10 0
S reg_OF ? w_wen : w_wdata[63]
S reg_MINH ? w_wen : w_wdata[62]
S reg_SINH ? w_wen : w_wdata[61]
S reg_UINH ? w_wen : w_wdata[60]
S reg_VSINH ? w_wen : w_wdata[59]
S reg_VUINH ? w_wen : w_wdata[58]
S reg_EVENT3 ? w_wen : w_wdata[39:30]
S reg_EVENT2 ? w_wen : w_wdata[29:20]
S reg_EVENT1 ? w_wen : w_wdata[19:10]
S reg_EVENT0 ? w_wen : w_wdata[9:0]
S reg_OF ? !(w_wen) & ofFromPerfCnt : ofFromPerfCnt
S reg_OPTYPE2 ? w_wen & (w_wdata[54:50] == 5'h0 | w_wdata[54:50] == 5'h1 | w_wdata[54:50] == 5'h2 | w_wdata[54:50] == 5'h4) : w_wdata[54:50]
S reg_OPTYPE1 ? w_wen & (w_wdata[49:45] == 5'h0 | w_wdata[49:45] == 5'h1 | w_wdata[49:45] == 5'h2 | w_wdata[49:45] == 5'h4) : w_wdata[49:45]
S reg_OPTYPE0 ? w_wen & (w_wdata[44:40] == 5'h0 | w_wdata[44:40] == 5'h1 | w_wdata[44:40] == 5'h2 | w_wdata[44:40] == 5'h4) : w_wdata[44:40]
A rdata = {reg_OF, reg_MINH, reg_SINH, reg_UINH, reg_VSINH, reg_VUINH, 3'h0, reg_OPTYPE2, reg_OPTYPE1, reg_OPTYPE0, reg_EVENT3, reg_EVENT2, reg_EVENT1, reg_EVENT0}
A regOut_OF = reg_OF
A regOut_MINH = reg_MINH
A regOut_SINH = reg_SINH
A regOut_UINH = reg_UINH
A regOut_VSINH = reg_VSINH
A regOut_VUINH = reg_VUINH
A regOut_OPTYPE2 = reg_OPTYPE2
A regOut_OPTYPE1 = reg_OPTYPE1
A regOut_OPTYPE0 = reg_OPTYPE0
A regOut_EVENT3 = reg_EVENT3
A regOut_EVENT2 = reg_EVENT2
A regOut_EVENT1 = reg_EVENT1
A regOut_EVENT0 = reg_EVENT0
M MscratchModule n
P i clock 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
F reg_ALL 64 -
S reg_ALL ? w_wen : w_wdata
A rdata = reg_ALL
A regOut_ALL = reg_ALL
M MepcModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_epc 63
P i trapToM_mepc_valid 1
P i trapToM_mepc_bits_epc 63
F reg_epc 63 0
S reg_epc ? w_wen | trapToM_mepc_valid : (trapToM_mepc_valid ? trapToM_mepc_bits_epc : 63'h0) | (w_wen ? w_wdata[63:1] : 63'h0)
A rdata = {reg_epc, 1'h0}
A regOut_epc = reg_epc
M McauseModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_Interrupt 1
P o regOut_ExceptionCode 63
P i trapToM_mcause_valid 1
P i trapToM_mcause_bits_Interrupt 1
P i trapToM_mcause_bits_ExceptionCode 63
F reg_Interrupt 1 0
F reg_ExceptionCode 63 0
S reg_Interrupt ? w_wen | trapToM_mcause_valid : trapToM_mcause_valid & trapToM_mcause_bits_Interrupt | w_wen & w_wdata[63]
S reg_ExceptionCode ? w_wen | trapToM_mcause_valid : (trapToM_mcause_valid ? trapToM_mcause_bits_ExceptionCode : 63'h0) | (w_wen ? w_wdata[62:0] : 63'h0)
A rdata = {reg_Interrupt, reg_ExceptionCode}
A regOut_Interrupt = reg_Interrupt
A regOut_ExceptionCode = reg_ExceptionCode
M MtvalModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i trapToM_mtval_valid 1
P i trapToM_mtval_bits_ALL 64
F reg_ALL 64 0
S reg_ALL ? w_wen | trapToM_mtval_valid : (trapToM_mtval_valid ? trapToM_mtval_bits_ALL : 64'h0) | (w_wen ? w_wdata : 64'h0)
A rdata = reg_ALL
A regOut_ALL = reg_ALL
M MipModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_SSIP 1
P o regOut_VSSIP 1
P o regOut_MSIP 1
P o regOut_STIP 1
P o regOut_VSTIP 1
P o regOut_MTIP 1
P o regOut_SEIP 1
P o regOut_VSEIP 1
P o regOut_MEIP 1
P o regOut_SGEIP 1
P o regOut_LCOFIP 1
P o rdataFields_SSIP 1
P o rdataFields_VSSIP 1
P o rdataFields_MSIP 1
P o rdataFields_STIP 1
P o rdataFields_VSTIP 1
P o rdataFields_MTIP 1
P o rdataFields_SEIP 1
P o rdataFields_VSEIP 1
P o rdataFields_MEIP 1
P o rdataFields_SGEIP 1
P o rdataFields_LCOFIP 1
P i mvip_SEIP 1
P i mvien_SEIE 1
P i hvip_VSSIP 1
P i hvip_VSTIP 1
P i hvip_VSEIP 1
P i hgeip_ip 7
P i hgeie_ie 7
P i hstatusVGEIN 6
P i platformIRP_MEIP 1
P i platformIRP_MTIP 1
P i platformIRP_MSIP 1
P i platformIRP_SEIP 1
P i platformIRP_STIP 1
P i platformIRP_VSTIP 1
P i menvcfg_STCE 1
P i lcofiReq 1
P i aiaToCSR_meip 1
P i aiaToCSR_seip 1
P i fromMvip_SSIP_valid 1
P i fromMvip_SSIP_bits 1
P i fromMvip_STIP_valid 1
P i fromMvip_STIP_bits 1
P i fromSip_SSIP_valid 1
P i fromSip_SSIP_bits 1
P i fromSip_LCOFIP_valid 1
P i fromSip_LCOFIP_bits 1
P i fromVSip_LCOFIP_valid 1
P i fromVSip_LCOFIP_bits 1
P o toMvip_SEIP_valid 1
P o toMvip_SEIP_bits 1
P o toHvip_VSSIP_valid 1
P o toHvip_VSSIP_bits 1
F reg_SSIP 1 0
F reg_STIP 1 0
F reg_LCOFIP 1 0
F lcofiReqHold_REG 1 0
D _GEN 7
D _regOut_MEIP_WIRE 1
D _regOut_VSEIP_WIRE 1
D _rdataFields_SEIP_WIRE 1
D _regOut_VSTIP_WIRE 1
D _regOut_STIP_WIRE 1
W _regOut_SEIP_WIRE 1 = ~mvien_SEIE & mvip_SEIP
W _GEN_0 64 = {56'h0, hgeip_ip, 1'h0} >> hstatusVGEIN
V lcofiReqHold 1
V lcofiReqHold ? 1'h1 : lcofiReq | lcofiReqHold_REG
S reg_SSIP ? fromMvip_SSIP_valid | fromSip_SSIP_valid : fromMvip_SSIP_valid & fromMvip_SSIP_bits | fromSip_SSIP_valid & fromSip_SSIP_bits
S reg_SSIP ? !(fromMvip_SSIP_valid | fromSip_SSIP_valid) & w_wen : w_wdata[1]
S reg_STIP ? (w_wen | fromMvip_STIP_valid) & ~menvcfg_STCE : w_wen & w_wdata[5] | fromMvip_STIP_valid & fromMvip_STIP_bits
S reg_LCOFIP ? lcofiReqHold : lcofiReqHold
S reg_LCOFIP ? !(lcofiReqHold) & fromSip_LCOFIP_valid | fromVSip_LCOFIP_valid | w_wen : fromSip_LCOFIP_valid & fromSip_LCOFIP_bits | fromVSip_LCOFIP_valid & fromVSip_LCOFIP_bits | w_wen & w_wdata[13]
S lcofiReqHold_REG ? 1'h1 : lcofiReq
A _regOut_STIP_WIRE = menvcfg_STCE ? platformIRP_STIP : reg_STIP
A _regOut_VSTIP_WIRE = hvip_VSTIP | platformIRP_VSTIP
A _rdataFields_SEIP_WIRE = _regOut_SEIP_WIRE | platformIRP_SEIP | aiaToCSR_seip
A _regOut_VSEIP_WIRE = hvip_VSEIP | _GEN_0[0]
A _regOut_MEIP_WIRE = platformIRP_MEIP | aiaToCSR_meip
A _GEN = hgeip_ip & hgeie_ie
A rdata = {50'h0, reg_LCOFIP, |_GEN, _regOut_MEIP_WIRE, _regOut_VSEIP_WIRE, _rdataFields_SEIP_WIRE, 1'h0, platformIRP_MTIP, _regOut_VSTIP_WIRE, _regOut_STIP_WIRE, 1'h0, platformIRP_MSIP, hvip_VSSIP, reg_SSIP, 1'h0}
A regOut_SSIP = reg_SSIP
A regOut_VSSIP = hvip_VSSIP
A regOut_MSIP = platformIRP_MSIP
A regOut_STIP = _regOut_STIP_WIRE
A regOut_VSTIP = _regOut_VSTIP_WIRE
A regOut_MTIP = platformIRP_MTIP
A regOut_SEIP = _regOut_SEIP_WIRE
A regOut_VSEIP = _regOut_VSEIP_WIRE
A regOut_MEIP = _regOut_MEIP_WIRE
A regOut_SGEIP = |_GEN
A regOut_LCOFIP = reg_LCOFIP
A rdataFields_SSIP = reg_SSIP
A rdataFields_VSSIP = hvip_VSSIP
A rdataFields_MSIP = platformIRP_MSIP
A rdataFields_STIP = _regOut_STIP_WIRE
A rdataFields_VSTIP = _regOut_VSTIP_WIRE
A rdataFields_MTIP = platformIRP_MTIP
A rdataFields_SEIP = _rdataFields_SEIP_WIRE
A rdataFields_VSEIP = _regOut_VSEIP_WIRE
A rdataFields_MEIP = _regOut_MEIP_WIRE
A rdataFields_SGEIP = |_GEN
A rdataFields_LCOFIP = reg_LCOFIP
A toMvip_SEIP_valid = w_wen & ~mvien_SEIE
A toMvip_SEIP_bits = w_wdata[9]
A toHvip_VSSIP_valid = w_wen
A toHvip_VSSIP_bits = w_wdata[2]
M MtinstModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i trapToM_mtinst_valid 1
P i trapToM_mtinst_bits_ALL 64
F reg_ALL 64 0
S reg_ALL ? w_wen | trapToM_mtinst_valid : (trapToM_mtinst_valid ? trapToM_mtinst_bits_ALL : 64'h0) | (w_wen ? w_wdata : 64'h0)
A rdata = reg_ALL
A regOut_ALL = reg_ALL
M Mtval2Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i trapToM_mtval2_valid 1
P i trapToM_mtval2_bits_ALL 64
F reg_ALL 64 0
S reg_ALL ? w_wen | trapToM_mtval2_valid : (trapToM_mtval2_valid ? trapToM_mtval2_bits_ALL : 64'h0) | (w_wen ? w_wdata : 64'h0)
A rdata = reg_ALL
A regOut_ALL = reg_ALL
M MseccfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_PMM 2
F reg_PMM 2 0
S reg_PMM ? w_wen & (w_wdata[33:32] == 2'h0 | w_wdata[33:32] == 2'h2 | (&(w_wdata[33:32]))) : w_wdata[33:32]
A rdata = {30'h0, reg_PMM, 32'h0}
A regOut_PMM = reg_PMM
M McycleModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
F reg_ALL 64 0
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & !(mcountinhibit_CY) : reg_ALL + 64'h1
A rdata = reg_ALL
A regOut_ALL = reg_ALL
M MinstretModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_IR 1
P i robCommit_instNum_bits 7
F reg_ALL 64 0
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & !(mcountinhibit_IR) : reg_ALL + {57'h0, robCommit_instNum_bits}
A rdata = reg_ALL
A regOut_ALL = reg_ALL
M Mhpmcounter3Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[0] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter4Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[1] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter5Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[2] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter6Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[3] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter7Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[4] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter8Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[5] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter9Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[6] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter10Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[7] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter11Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[8] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter12Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[9] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter13Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[10] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter14Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[11] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter15Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[12] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter16Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[13] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter17Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[14] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter18Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[15] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter19Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[16] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter20Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[17] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter21Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[18] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter22Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[19] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter23Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[20] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter24Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[21] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter25Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[22] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter26Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[23] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter27Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[24] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter28Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[25] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter29Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[26] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter30Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[27] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M Mhpmcounter31Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i mcountinhibit_CY 1
P i mcountinhibit_IR 1
P i mcountinhibit_HPM3 29
P i countingEn 1
P i perf_value 6
P o toMhpmeventOF 1
F reg_ALL 64 0
W countingInhibit 1 = mcountinhibit_HPM3[28] | ~countingEn
W counterAdd 65 = {1'h0, reg_ALL} + {59'h0, perf_value}
S reg_ALL ? w_wen : w_wdata
S reg_ALL ? !(w_wen) & (|perf_value) & ~countingInhibit : counterAdd[63:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
A toMhpmeventOF = ~countingInhibit & counterAdd[64]
M MhartidModule n
P o rdata 64
P i hartid 6
A rdata = {58'h0, hartid}
M MconfigptrModule n
P o rdata 64
A rdata = 64'h0
M Mstateen0Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_SE0 1
P o regOut_ENVCFG 1
P o regOut_CSRIND 1
P o regOut_AIA 1
P o regOut_IMSIC 1
P o regOut_CONTEXT 1
P o regOut_C 1
F reg_SE0 1 0
F reg_ENVCFG 1 0
F reg_CSRIND 1 0
F reg_AIA 1 0
F reg_IMSIC 1 0
F reg_CONTEXT 1 0
F reg_C 1 0
S reg_SE0 ? w_wen : w_wdata[63]
S reg_ENVCFG ? w_wen : w_wdata[62]
S reg_CSRIND ? w_wen : w_wdata[60]
S reg_AIA ? w_wen : w_wdata[59]
S reg_IMSIC ? w_wen : w_wdata[58]
S reg_CONTEXT ? w_wen : w_wdata[57]
S reg_C ? w_wen : w_wdata[0]
A rdata = {reg_SE0, reg_ENVCFG, 1'h0, reg_CSRIND, reg_AIA, reg_IMSIC, reg_CONTEXT, 56'h0, reg_C}
A regOut_SE0 = reg_SE0
A regOut_ENVCFG = reg_ENVCFG
A regOut_CSRIND = reg_CSRIND
A regOut_AIA = reg_AIA
A regOut_IMSIC = reg_IMSIC
A regOut_CONTEXT = reg_CONTEXT
A regOut_C = reg_C
M Mstateen1Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_SE 1
F reg_SE 1 0
S reg_SE ? w_wen : w_wdata[63]
A rdata = {reg_SE, 63'h0}
A regOut_SE = reg_SE
M Mstateen2Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_SE 1
F reg_SE 1 0
S reg_SE ? w_wen : w_wdata[63]
A rdata = {reg_SE, 63'h0}
A regOut_SE = reg_SE
M Mstateen3Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_SE 1
F reg_SE 1 0
S reg_SE ? w_wen : w_wdata[63]
A rdata = {reg_SE, 63'h0}
A regOut_SE = reg_SE
M MnepcModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_epc 63
P i trapToMN_mnepc_valid 1
P i trapToMN_mnepc_bits_epc 63
F reg_epc 63 0
S reg_epc ? w_wen | trapToMN_mnepc_valid : (trapToMN_mnepc_valid ? trapToMN_mnepc_bits_epc : 63'h0) | (w_wen ? w_wdata[63:1] : 63'h0)
A rdata = {reg_epc, 1'h0}
A regOut_epc = reg_epc
M MncauseModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_Interrupt 1
P o regOut_ExceptionCode 63
P i trapToMN_mncause_valid 1
P i trapToMN_mncause_bits_Interrupt 1
P i trapToMN_mncause_bits_ExceptionCode 63
F reg_Interrupt 1 0
F reg_ExceptionCode 63 0
S reg_Interrupt ? w_wen | trapToMN_mncause_valid : trapToMN_mncause_valid & trapToMN_mncause_bits_Interrupt | w_wen & w_wdata[63]
S reg_ExceptionCode ? w_wen | trapToMN_mncause_valid : (trapToMN_mncause_valid ? trapToMN_mncause_bits_ExceptionCode : 63'h0) | (w_wen ? w_wdata[62:0] : 63'h0)
A rdata = {reg_Interrupt, reg_ExceptionCode}
A regOut_Interrupt = reg_Interrupt
A regOut_ExceptionCode = reg_ExceptionCode
M MnstatusModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_NMIE 1
P o regOut_MNPV 1
P o regOut_MNPP 2
P i trapToMN_mnstatus_valid 1
P i trapToMN_mnstatus_bits_NMIE 1
P i trapToMN_mnstatus_bits_MNPV 1
P i trapToMN_mnstatus_bits_MNPP 2
P i retFromMN_mnstatus_valid 1
P i retFromMN_mnstatus_bits_NMIE 1
F reg_NMIE 1 0
F reg_MNPV 1 0
F reg_MNPP 2 0
S reg_NMIE ? !(w_wen & ~(w_wdata[3]) | ~(w_wen | trapToMN_mnstatus_valid | retFromMN_mnstatus_valid)) : trapToMN_mnstatus_valid & trapToMN_mnstatus_bits_NMIE | retFromMN_mnstatus_valid & retFromMN_mnstatus_bits_NMIE | w_wen & w_wdata[3]
S reg_MNPV ? w_wen | trapToMN_mnstatus_valid : trapToMN_mnstatus_valid & trapToMN_mnstatus_bits_MNPV | w_wen & w_wdata[7]
S reg_MNPP ? w_wen & (w_wdata[12:11] == 2'h0 | w_wdata[12:11] == 2'h1 | (&(w_wdata[12:11]))) | trapToMN_mnstatus_valid : (trapToMN_mnstatus_valid ? trapToMN_mnstatus_bits_MNPP : 2'h0) | (w_wen ? w_wdata[12:11] : 2'h0)
A rdata = {51'h0, reg_MNPP, 3'h0, reg_MNPV, 3'h0, reg_NMIE, 3'h0}
A regOut_NMIE = reg_NMIE
A regOut_MNPV = reg_MNPV
A regOut_MNPP = reg_MNPP
M MnscratchModule n
P i clock 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
F reg_ALL 64 -
S reg_ALL ? w_wen : w_wdata
A rdata = reg_ALL
A regOut_ALL = reg_ALL
M McontextModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 14
P o regOut_HCONTEXT 14
P i fromHcontext_valid 1
P i fromHcontext_bits_HCONTEXT 14
P o toHcontext_HCONTEXT 14
F reg_HCONTEXT 14 0
S reg_HCONTEXT ? w_wen : w_wdata[13:0]
S reg_HCONTEXT ? !(w_wen) & fromHcontext_valid : fromHcontext_bits_HCONTEXT
A rdata = reg_HCONTEXT
A regOut_HCONTEXT = reg_HCONTEXT
A toHcontext_HCONTEXT = reg_HCONTEXT
M SieModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_SSIE 1
P o regOut_STIE 1
P o regOut_SEIE 1
P o regOut_LCOFIE 1
P o regOut_LC14IE 1
P o regOut_LC15IE 1
P o regOut_LC16IE 1
P o regOut_LC17IE 1
P o regOut_LC18IE 1
P o regOut_LC19IE 1
P o regOut_LC20IE 1
P o regOut_LC21IE 1
P o regOut_LC22IE 1
P o regOut_LC23IE 1
P o regOut_LC24IE 1
P o regOut_LC25IE 1
P o regOut_LC26IE 1
P o regOut_LC27IE 1
P o regOut_LC28IE 1
P o regOut_LC29IE 1
P o regOut_LC30IE 1
P o regOut_LC31IE 1
P o regOut_LC32IE 1
P o regOut_LC33IE 1
P o regOut_LC34IE 1
P o regOut_LPRASEIE 1
P o regOut_LC36IE 1
P o regOut_LC37IE 1
P o regOut_LC38IE 1
P o regOut_LC39IE 1
P o regOut_LC40IE 1
P o regOut_LC41IE 1
P o regOut_LC42IE 1
P o regOut_HPRASEIE 1
P o regOut_LC44IE 1
P o regOut_LC45IE 1
P o regOut_LC46IE 1
P o regOut_LC47IE 1
P o regOut_LC48IE 1
P o regOut_LC49IE 1
P o regOut_LC50IE 1
P o regOut_LC51IE 1
P o regOut_LC52IE 1
P o regOut_LC53IE 1
P o regOut_LC54IE 1
P o regOut_LC55IE 1
P o regOut_LC56IE 1
P o regOut_LC57IE 1
P o regOut_LC58IE 1
P o regOut_LC59IE 1
P o regOut_LC60IE 1
P o regOut_LC61IE 1
P o regOut_LC62IE 1
P o regOut_LC63IE 1
P i mideleg_SSI 1
P i mideleg_STI 1
P i mideleg_SEI 1
P i mideleg_LCOFI 1
P i mie_SSIE 1
P i mie_VSSIE 1
P i mie_MSIE 1
P i mie_STIE 1
P i mie_VSTIE 1
P i mie_MTIE 1
P i mie_SEIE 1
P i mie_VSEIE 1
P i mie_MEIE 1
P i mie_SGEIE 1
P i mie_LCOFIE 1
P i mvien_SSIE 1
P i mvien_SEIE 1
P i mvien_LC14IE 1
P i mvien_LC15IE 1
P i mvien_LC16IE 1
P i mvien_LC17IE 1
P i mvien_LC18IE 1
P i mvien_LC19IE 1
P i mvien_LC20IE 1
P i mvien_LC21IE 1
P i mvien_LC22IE 1
P i mvien_LC23IE 1
P i mvien_LC24IE 1
P i mvien_LC25IE 1
P i mvien_LC26IE 1
P i mvien_LC27IE 1
P i mvien_LC28IE 1
P i mvien_LC29IE 1
P i mvien_LC30IE 1
P i mvien_LC31IE 1
P i mvien_LC32IE 1
P i mvien_LC33IE 1
P i mvien_LC34IE 1
P i mvien_LPRASEIE 1
P i mvien_LC36IE 1
P i mvien_LC37IE 1
P i mvien_LC38IE 1
P i mvien_LC39IE 1
P i mvien_LC40IE 1
P i mvien_LC41IE 1
P i mvien_LC42IE 1
P i mvien_HPRASEIE 1
P i mvien_LC44IE 1
P i mvien_LC45IE 1
P i mvien_LC46IE 1
P i mvien_LC47IE 1
P i mvien_LC48IE 1
P i mvien_LC49IE 1
P i mvien_LC50IE 1
P i mvien_LC51IE 1
P i mvien_LC52IE 1
P i mvien_LC53IE 1
P i mvien_LC54IE 1
P i mvien_LC55IE 1
P i mvien_LC56IE 1
P i mvien_LC57IE 1
P i mvien_LC58IE 1
P i mvien_LC59IE 1
P i mvien_LC60IE 1
P i mvien_LC61IE 1
P i mvien_LC62IE 1
P i mvien_LC63IE 1
P o toMie_SSIE_valid 1
P o toMie_SSIE_bits 1
P o toMie_STIE_valid 1
P o toMie_STIE_bits 1
P o toMie_SEIE_valid 1
P o toMie_SEIE_bits 1
P o toMie_LCOFIE_valid 1
P o toMie_LCOFIE_bits 1
P i fromVSie_VSSIE_valid 1
P i fromVSie_VSSIE_bits 1
P i fromVSie_VSTIE_valid 1
P i fromVSie_VSTIE_bits 1
P i fromVSie_VSEIE_valid 1
P i fromVSie_VSEIE_bits 1
P i fromVSie_LCOFIE_valid 1
P i fromVSie_LCOFIE_bits 1
P i fromVSie_LC14IE_valid 1
P i fromVSie_LC14IE_bits 1
P i fromVSie_LC15IE_valid 1
P i fromVSie_LC15IE_bits 1
P i fromVSie_LC16IE_valid 1
P i fromVSie_LC16IE_bits 1
P i fromVSie_LC17IE_valid 1
P i fromVSie_LC17IE_bits 1
P i fromVSie_LC18IE_valid 1
P i fromVSie_LC18IE_bits 1
P i fromVSie_LC19IE_valid 1
P i fromVSie_LC19IE_bits 1
P i fromVSie_LC20IE_valid 1
P i fromVSie_LC20IE_bits 1
P i fromVSie_LC21IE_valid 1
P i fromVSie_LC21IE_bits 1
P i fromVSie_LC22IE_valid 1
P i fromVSie_LC22IE_bits 1
P i fromVSie_LC23IE_valid 1
P i fromVSie_LC23IE_bits 1
P i fromVSie_LC24IE_valid 1
P i fromVSie_LC24IE_bits 1
P i fromVSie_LC25IE_valid 1
P i fromVSie_LC25IE_bits 1
P i fromVSie_LC26IE_valid 1
P i fromVSie_LC26IE_bits 1
P i fromVSie_LC27IE_valid 1
P i fromVSie_LC27IE_bits 1
P i fromVSie_LC28IE_valid 1
P i fromVSie_LC28IE_bits 1
P i fromVSie_LC29IE_valid 1
P i fromVSie_LC29IE_bits 1
P i fromVSie_LC30IE_valid 1
P i fromVSie_LC30IE_bits 1
P i fromVSie_LC31IE_valid 1
P i fromVSie_LC31IE_bits 1
P i fromVSie_LC32IE_valid 1
P i fromVSie_LC32IE_bits 1
P i fromVSie_LC33IE_valid 1
P i fromVSie_LC33IE_bits 1
P i fromVSie_LC34IE_valid 1
P i fromVSie_LC34IE_bits 1
P i fromVSie_LPRASEIE_valid 1
P i fromVSie_LPRASEIE_bits 1
P i fromVSie_LC36IE_valid 1
P i fromVSie_LC36IE_bits 1
P i fromVSie_LC37IE_valid 1
P i fromVSie_LC37IE_bits 1
P i fromVSie_LC38IE_valid 1
P i fromVSie_LC38IE_bits 1
P i fromVSie_LC39IE_valid 1
P i fromVSie_LC39IE_bits 1
P i fromVSie_LC40IE_valid 1
P i fromVSie_LC40IE_bits 1
P i fromVSie_LC41IE_valid 1
P i fromVSie_LC41IE_bits 1
P i fromVSie_LC42IE_valid 1
P i fromVSie_LC42IE_bits 1
P i fromVSie_HPRASEIE_valid 1
P i fromVSie_HPRASEIE_bits 1
P i fromVSie_LC44IE_valid 1
P i fromVSie_LC44IE_bits 1
P i fromVSie_LC45IE_valid 1
P i fromVSie_LC45IE_bits 1
P i fromVSie_LC46IE_valid 1
P i fromVSie_LC46IE_bits 1
P i fromVSie_LC47IE_valid 1
P i fromVSie_LC47IE_bits 1
P i fromVSie_LC48IE_valid 1
P i fromVSie_LC48IE_bits 1
P i fromVSie_LC49IE_valid 1
P i fromVSie_LC49IE_bits 1
P i fromVSie_LC50IE_valid 1
P i fromVSie_LC50IE_bits 1
P i fromVSie_LC51IE_valid 1
P i fromVSie_LC51IE_bits 1
P i fromVSie_LC52IE_valid 1
P i fromVSie_LC52IE_bits 1
P i fromVSie_LC53IE_valid 1
P i fromVSie_LC53IE_bits 1
P i fromVSie_LC54IE_valid 1
P i fromVSie_LC54IE_bits 1
P i fromVSie_LC55IE_valid 1
P i fromVSie_LC55IE_bits 1
P i fromVSie_LC56IE_valid 1
P i fromVSie_LC56IE_bits 1
P i fromVSie_LC57IE_valid 1
P i fromVSie_LC57IE_bits 1
P i fromVSie_LC58IE_valid 1
P i fromVSie_LC58IE_bits 1
P i fromVSie_LC59IE_valid 1
P i fromVSie_LC59IE_bits 1
P i fromVSie_LC60IE_valid 1
P i fromVSie_LC60IE_bits 1
P i fromVSie_LC61IE_valid 1
P i fromVSie_LC61IE_bits 1
P i fromVSie_LC62IE_valid 1
P i fromVSie_LC62IE_bits 1
P i fromVSie_LC63IE_valid 1
P i fromVSie_LC63IE_bits 1
F reg_SSIE 1 0
F reg_SEIE 1 0
F reg_LC14IE 1 0
F reg_LC15IE 1 0
F reg_LC16IE 1 0
F reg_LC17IE 1 0
F reg_LC18IE 1 0
F reg_LC19IE 1 0
F reg_LC20IE 1 0
F reg_LC21IE 1 0
F reg_LC22IE 1 0
F reg_LC23IE 1 0
F reg_LC24IE 1 0
F reg_LC25IE 1 0
F reg_LC26IE 1 0
F reg_LC27IE 1 0
F reg_LC28IE 1 0
F reg_LC29IE 1 0
F reg_LC30IE 1 0
F reg_LC31IE 1 0
F reg_LC32IE 1 0
F reg_LC33IE 1 0
F reg_LC34IE 1 0
F reg_LPRASEIE 1 0
F reg_LC36IE 1 0
F reg_LC37IE 1 0
F reg_LC38IE 1 0
F reg_LC39IE 1 0
F reg_LC40IE 1 0
F reg_LC41IE 1 0
F reg_LC42IE 1 0
F reg_HPRASEIE 1 0
F reg_LC44IE 1 0
F reg_LC45IE 1 0
F reg_LC46IE 1 0
F reg_LC47IE 1 0
F reg_LC48IE 1 0
F reg_LC49IE 1 0
F reg_LC50IE 1 0
F reg_LC51IE 1 0
F reg_LC52IE 1 0
F reg_LC53IE 1 0
F reg_LC54IE 1 0
F reg_LC55IE 1 0
F reg_LC56IE 1 0
F reg_LC57IE 1 0
F reg_LC58IE 1 0
F reg_LC59IE 1 0
F reg_LC60IE 1 0
F reg_LC61IE 1 0
F reg_LC62IE 1 0
F reg_LC63IE 1 0
D _regOut_SSIE_T 1
D _regOut_STIE_T 1
D _regOut_SEIE_T 1
D _GEN 63
S reg_SSIE ? w_wen & ~mideleg_SSI & mvien_SSIE : w_wen & w_wdata[1]
S reg_SEIE ? w_wen & ~mideleg_SEI & mvien_SEIE : w_wen & w_wdata[9]
S reg_LC14IE ? w_wen & mvien_LC14IE | fromVSie_LC14IE_valid & mvien_LC14IE : w_wen & w_wdata[14] | fromVSie_LC14IE_valid & fromVSie_LC14IE_bits
S reg_LC15IE ? w_wen & mvien_LC15IE | fromVSie_LC15IE_valid & mvien_LC15IE : w_wen & w_wdata[15] | fromVSie_LC15IE_valid & fromVSie_LC15IE_bits
S reg_LC16IE ? w_wen & mvien_LC16IE | fromVSie_LC16IE_valid & mvien_LC16IE : w_wen & w_wdata[16] | fromVSie_LC16IE_valid & fromVSie_LC16IE_bits
S reg_LC17IE ? w_wen & mvien_LC17IE | fromVSie_LC17IE_valid & mvien_LC17IE : w_wen & w_wdata[17] | fromVSie_LC17IE_valid & fromVSie_LC17IE_bits
S reg_LC18IE ? w_wen & mvien_LC18IE | fromVSie_LC18IE_valid & mvien_LC18IE : w_wen & w_wdata[18] | fromVSie_LC18IE_valid & fromVSie_LC18IE_bits
S reg_LC19IE ? w_wen & mvien_LC19IE | fromVSie_LC19IE_valid & mvien_LC19IE : w_wen & w_wdata[19] | fromVSie_LC19IE_valid & fromVSie_LC19IE_bits
S reg_LC20IE ? w_wen & mvien_LC20IE | fromVSie_LC20IE_valid & mvien_LC20IE : w_wen & w_wdata[20] | fromVSie_LC20IE_valid & fromVSie_LC20IE_bits
S reg_LC21IE ? w_wen & mvien_LC21IE | fromVSie_LC21IE_valid & mvien_LC21IE : w_wen & w_wdata[21] | fromVSie_LC21IE_valid & fromVSie_LC21IE_bits
S reg_LC22IE ? w_wen & mvien_LC22IE | fromVSie_LC22IE_valid & mvien_LC22IE : w_wen & w_wdata[22] | fromVSie_LC22IE_valid & fromVSie_LC22IE_bits
S reg_LC23IE ? w_wen & mvien_LC23IE | fromVSie_LC23IE_valid & mvien_LC23IE : w_wen & w_wdata[23] | fromVSie_LC23IE_valid & fromVSie_LC23IE_bits
S reg_LC24IE ? w_wen & mvien_LC24IE | fromVSie_LC24IE_valid & mvien_LC24IE : w_wen & w_wdata[24] | fromVSie_LC24IE_valid & fromVSie_LC24IE_bits
S reg_LC25IE ? w_wen & mvien_LC25IE | fromVSie_LC25IE_valid & mvien_LC25IE : w_wen & w_wdata[25] | fromVSie_LC25IE_valid & fromVSie_LC25IE_bits
S reg_LC26IE ? w_wen & mvien_LC26IE | fromVSie_LC26IE_valid & mvien_LC26IE : w_wen & w_wdata[26] | fromVSie_LC26IE_valid & fromVSie_LC26IE_bits
S reg_LC27IE ? w_wen & mvien_LC27IE | fromVSie_LC27IE_valid & mvien_LC27IE : w_wen & w_wdata[27] | fromVSie_LC27IE_valid & fromVSie_LC27IE_bits
S reg_LC28IE ? w_wen & mvien_LC28IE | fromVSie_LC28IE_valid & mvien_LC28IE : w_wen & w_wdata[28] | fromVSie_LC28IE_valid & fromVSie_LC28IE_bits
S reg_LC29IE ? w_wen & mvien_LC29IE | fromVSie_LC29IE_valid & mvien_LC29IE : w_wen & w_wdata[29] | fromVSie_LC29IE_valid & fromVSie_LC29IE_bits
S reg_LC30IE ? w_wen & mvien_LC30IE | fromVSie_LC30IE_valid & mvien_LC30IE : w_wen & w_wdata[30] | fromVSie_LC30IE_valid & fromVSie_LC30IE_bits
S reg_LC31IE ? w_wen & mvien_LC31IE | fromVSie_LC31IE_valid & mvien_LC31IE : w_wen & w_wdata[31] | fromVSie_LC31IE_valid & fromVSie_LC31IE_bits
S reg_LC32IE ? w_wen & mvien_LC32IE | fromVSie_LC32IE_valid & mvien_LC32IE : w_wen & w_wdata[32] | fromVSie_LC32IE_valid & fromVSie_LC32IE_bits
S reg_LC33IE ? w_wen & mvien_LC33IE | fromVSie_LC33IE_valid & mvien_LC33IE : w_wen & w_wdata[33] | fromVSie_LC33IE_valid & fromVSie_LC33IE_bits
S reg_LC34IE ? w_wen & mvien_LC34IE | fromVSie_LC34IE_valid & mvien_LC34IE : w_wen & w_wdata[34] | fromVSie_LC34IE_valid & fromVSie_LC34IE_bits
S reg_LPRASEIE ? w_wen & mvien_LPRASEIE | fromVSie_LPRASEIE_valid & mvien_LPRASEIE : w_wen & w_wdata[35] | fromVSie_LPRASEIE_valid & fromVSie_LPRASEIE_bits
S reg_LC36IE ? w_wen & mvien_LC36IE | fromVSie_LC36IE_valid & mvien_LC36IE : w_wen & w_wdata[36] | fromVSie_LC36IE_valid & fromVSie_LC36IE_bits
S reg_LC37IE ? w_wen & mvien_LC37IE | fromVSie_LC37IE_valid & mvien_LC37IE : w_wen & w_wdata[37] | fromVSie_LC37IE_valid & fromVSie_LC37IE_bits
S reg_LC38IE ? w_wen & mvien_LC38IE | fromVSie_LC38IE_valid & mvien_LC38IE : w_wen & w_wdata[38] | fromVSie_LC38IE_valid & fromVSie_LC38IE_bits
S reg_LC39IE ? w_wen & mvien_LC39IE | fromVSie_LC39IE_valid & mvien_LC39IE : w_wen & w_wdata[39] | fromVSie_LC39IE_valid & fromVSie_LC39IE_bits
S reg_LC40IE ? w_wen & mvien_LC40IE | fromVSie_LC40IE_valid & mvien_LC40IE : w_wen & w_wdata[40] | fromVSie_LC40IE_valid & fromVSie_LC40IE_bits
S reg_LC41IE ? w_wen & mvien_LC41IE | fromVSie_LC41IE_valid & mvien_LC41IE : w_wen & w_wdata[41] | fromVSie_LC41IE_valid & fromVSie_LC41IE_bits
S reg_LC42IE ? w_wen & mvien_LC42IE | fromVSie_LC42IE_valid & mvien_LC42IE : w_wen & w_wdata[42] | fromVSie_LC42IE_valid & fromVSie_LC42IE_bits
S reg_HPRASEIE ? w_wen & mvien_HPRASEIE | fromVSie_HPRASEIE_valid & mvien_HPRASEIE : w_wen & w_wdata[43] | fromVSie_HPRASEIE_valid & fromVSie_HPRASEIE_bits
S reg_LC44IE ? w_wen & mvien_LC44IE | fromVSie_LC44IE_valid & mvien_LC44IE : w_wen & w_wdata[44] | fromVSie_LC44IE_valid & fromVSie_LC44IE_bits
S reg_LC45IE ? w_wen & mvien_LC45IE | fromVSie_LC45IE_valid & mvien_LC45IE : w_wen & w_wdata[45] | fromVSie_LC45IE_valid & fromVSie_LC45IE_bits
S reg_LC46IE ? w_wen & mvien_LC46IE | fromVSie_LC46IE_valid & mvien_LC46IE : w_wen & w_wdata[46] | fromVSie_LC46IE_valid & fromVSie_LC46IE_bits
S reg_LC47IE ? w_wen & mvien_LC47IE | fromVSie_LC47IE_valid & mvien_LC47IE : w_wen & w_wdata[47] | fromVSie_LC47IE_valid & fromVSie_LC47IE_bits
S reg_LC48IE ? w_wen & mvien_LC48IE | fromVSie_LC48IE_valid & mvien_LC48IE : w_wen & w_wdata[48] | fromVSie_LC48IE_valid & fromVSie_LC48IE_bits
S reg_LC49IE ? w_wen & mvien_LC49IE | fromVSie_LC49IE_valid & mvien_LC49IE : w_wen & w_wdata[49] | fromVSie_LC49IE_valid & fromVSie_LC49IE_bits
S reg_LC50IE ? w_wen & mvien_LC50IE | fromVSie_LC50IE_valid & mvien_LC50IE : w_wen & w_wdata[50] | fromVSie_LC50IE_valid & fromVSie_LC50IE_bits
S reg_LC51IE ? w_wen & mvien_LC51IE | fromVSie_LC51IE_valid & mvien_LC51IE : w_wen & w_wdata[51] | fromVSie_LC51IE_valid & fromVSie_LC51IE_bits
S reg_LC52IE ? w_wen & mvien_LC52IE | fromVSie_LC52IE_valid & mvien_LC52IE : w_wen & w_wdata[52] | fromVSie_LC52IE_valid & fromVSie_LC52IE_bits
S reg_LC53IE ? w_wen & mvien_LC53IE | fromVSie_LC53IE_valid & mvien_LC53IE : w_wen & w_wdata[53] | fromVSie_LC53IE_valid & fromVSie_LC53IE_bits
S reg_LC54IE ? w_wen & mvien_LC54IE | fromVSie_LC54IE_valid & mvien_LC54IE : w_wen & w_wdata[54] | fromVSie_LC54IE_valid & fromVSie_LC54IE_bits
S reg_LC55IE ? w_wen & mvien_LC55IE | fromVSie_LC55IE_valid & mvien_LC55IE : w_wen & w_wdata[55] | fromVSie_LC55IE_valid & fromVSie_LC55IE_bits
S reg_LC56IE ? w_wen & mvien_LC56IE | fromVSie_LC56IE_valid & mvien_LC56IE : w_wen & w_wdata[56] | fromVSie_LC56IE_valid & fromVSie_LC56IE_bits
S reg_LC57IE ? w_wen & mvien_LC57IE | fromVSie_LC57IE_valid & mvien_LC57IE : w_wen & w_wdata[57] | fromVSie_LC57IE_valid & fromVSie_LC57IE_bits
S reg_LC58IE ? w_wen & mvien_LC58IE | fromVSie_LC58IE_valid & mvien_LC58IE : w_wen & w_wdata[58] | fromVSie_LC58IE_valid & fromVSie_LC58IE_bits
S reg_LC59IE ? w_wen & mvien_LC59IE | fromVSie_LC59IE_valid & mvien_LC59IE : w_wen & w_wdata[59] | fromVSie_LC59IE_valid & fromVSie_LC59IE_bits
S reg_LC60IE ? w_wen & mvien_LC60IE | fromVSie_LC60IE_valid & mvien_LC60IE : w_wen & w_wdata[60] | fromVSie_LC60IE_valid & fromVSie_LC60IE_bits
S reg_LC61IE ? w_wen & mvien_LC61IE | fromVSie_LC61IE_valid & mvien_LC61IE : w_wen & w_wdata[61] | fromVSie_LC61IE_valid & fromVSie_LC61IE_bits
S reg_LC62IE ? w_wen & mvien_LC62IE | fromVSie_LC62IE_valid & mvien_LC62IE : w_wen & w_wdata[62] | fromVSie_LC62IE_valid & fromVSie_LC62IE_bits
S reg_LC63IE ? w_wen & mvien_LC63IE | fromVSie_LC63IE_valid & mvien_LC63IE : w_wen & w_wdata[63] | fromVSie_LC63IE_valid & fromVSie_LC63IE_bits
A _GEN = {50'h0, mideleg_LCOFI, 3'h5, mideleg_SEI, 3'h1, mideleg_STI, 3'h1, mideleg_SSI} & {50'h0, mie_LCOFIE, mie_SGEIE, mie_MEIE, mie_VSEIE, mie_SEIE, 1'h0, mie_MTIE, mie_VSTIE, mie_STIE, 1'h0, mie_MSIE, mie_VSSIE, mie_SSIE} | {50'h3FFFFFFFFFFFF, ~mideleg_LCOFI, 3'h2, ~mideleg_SEI, 3'h6, ~mideleg_STI, 3'h6, ~mideleg_SSI} & {mvien_LC63IE, mvien_LC62IE, mvien_LC61IE, mvien_LC60IE, mvien_LC59IE, mvien_LC58IE, mvien_LC57IE, mvien_LC56IE, mvien_LC55IE, mvien_LC54IE, mvien_LC53IE, mvien_LC52IE, mvien_LC51IE, mvien_LC50IE, mvien_LC49IE, mvien_LC48IE, mvien_LC47IE, mvien_LC46IE, mvien_LC45IE, mvien_LC44IE, mvien_HPRASEIE, mvien_LC42IE, mvien_LC41IE, mvien_LC40IE, mvien_LC39IE, mvien_LC38IE, mvien_LC37IE, mvien_LC36IE, mvien_LPRASEIE, mvien_LC34IE, mvien_LC33IE, mvien_LC32IE, mvien_LC31IE, mvien_LC30IE, mvien_LC29IE, mvien_LC28IE, mvien_LC27IE, mvien_LC26IE, mvien_LC25IE, mvien_LC24IE, mvien_LC23IE, mvien_LC22IE, mvien_LC21IE, mvien_LC20IE, mvien_LC19IE, mvien_LC18IE, mvien_LC17IE, mvien_LC16IE, mvien_LC15IE, mvien_LC14IE, 4'h0, mvien_SEIE, 7'h0, mvien_SSIE} & {reg_LC63IE, reg_LC62IE, reg_LC61IE, reg_LC60IE, reg_LC59IE, reg_LC58IE, reg_LC57IE, reg_LC56IE, reg_LC55IE, reg_LC54IE, reg_LC53IE, reg_LC52IE, reg_LC51IE, reg_LC50IE, reg_LC49IE, reg_LC48IE, reg_LC47IE, reg_LC46IE, reg_LC45IE, reg_LC44IE, reg_HPRASEIE, reg_LC42IE, reg_LC41IE, reg_LC40IE, reg_LC39IE, reg_LC38IE, reg_LC37IE, reg_LC36IE, reg_LPRASEIE, reg_LC34IE, reg_LC33IE, reg_LC32IE, reg_LC31IE, reg_LC30IE, reg_LC29IE, reg_LC28IE, reg_LC27IE, reg_LC26IE, reg_LC25IE, reg_LC24IE, reg_LC23IE, reg_LC22IE, reg_LC21IE, reg_LC20IE, reg_LC19IE, reg_LC18IE, reg_LC17IE, reg_LC16IE, reg_LC15IE, reg_LC14IE, 4'h0, reg_SEIE, 7'h0, reg_SSIE}
A _regOut_SEIE_T = _GEN[8]
A _regOut_STIE_T = _GEN[4]
A _regOut_SSIE_T = _GEN[0]
A rdata = {_GEN[62:12], 3'h0, _regOut_SEIE_T, 3'h0, _regOut_STIE_T, 3'h0, _regOut_SSIE_T, 1'h0}
A regOut_SSIE = _regOut_SSIE_T
A regOut_STIE = _regOut_STIE_T
A regOut_SEIE = _regOut_SEIE_T
A regOut_LCOFIE = _GEN[12]
A regOut_LC14IE = _GEN[13]
A regOut_LC15IE = _GEN[14]
A regOut_LC16IE = _GEN[15]
A regOut_LC17IE = _GEN[16]
A regOut_LC18IE = _GEN[17]
A regOut_LC19IE = _GEN[18]
A regOut_LC20IE = _GEN[19]
A regOut_LC21IE = _GEN[20]
A regOut_LC22IE = _GEN[21]
A regOut_LC23IE = _GEN[22]
A regOut_LC24IE = _GEN[23]
A regOut_LC25IE = _GEN[24]
A regOut_LC26IE = _GEN[25]
A regOut_LC27IE = _GEN[26]
A regOut_LC28IE = _GEN[27]
A regOut_LC29IE = _GEN[28]
A regOut_LC30IE = _GEN[29]
A regOut_LC31IE = _GEN[30]
A regOut_LC32IE = _GEN[31]
A regOut_LC33IE = _GEN[32]
A regOut_LC34IE = _GEN[33]
A regOut_LPRASEIE = _GEN[34]
A regOut_LC36IE = _GEN[35]
A regOut_LC37IE = _GEN[36]
A regOut_LC38IE = _GEN[37]
A regOut_LC39IE = _GEN[38]
A regOut_LC40IE = _GEN[39]
A regOut_LC41IE = _GEN[40]
A regOut_LC42IE = _GEN[41]
A regOut_HPRASEIE = _GEN[42]
A regOut_LC44IE = _GEN[43]
A regOut_LC45IE = _GEN[44]
A regOut_LC46IE = _GEN[45]
A regOut_LC47IE = _GEN[46]
A regOut_LC48IE = _GEN[47]
A regOut_LC49IE = _GEN[48]
A regOut_LC50IE = _GEN[49]
A regOut_LC51IE = _GEN[50]
A regOut_LC52IE = _GEN[51]
A regOut_LC53IE = _GEN[52]
A regOut_LC54IE = _GEN[53]
A regOut_LC55IE = _GEN[54]
A regOut_LC56IE = _GEN[55]
A regOut_LC57IE = _GEN[56]
A regOut_LC58IE = _GEN[57]
A regOut_LC59IE = _GEN[58]
A regOut_LC60IE = _GEN[59]
A regOut_LC61IE = _GEN[60]
A regOut_LC62IE = _GEN[61]
A regOut_LC63IE = _GEN[62]
A toMie_SSIE_valid = w_wen & mideleg_SSI
A toMie_SSIE_bits = w_wen & mideleg_SSI & w_wdata[1]
A toMie_STIE_valid = w_wen & mideleg_STI
A toMie_STIE_bits = w_wen & mideleg_STI & w_wdata[5]
A toMie_SEIE_valid = w_wen & mideleg_SEI
A toMie_SEIE_bits = w_wen & mideleg_SEI & w_wdata[9]
A toMie_LCOFIE_valid = w_wen & mideleg_LCOFI
A toMie_LCOFIE_bits = w_wen & mideleg_LCOFI & w_wdata[13]
M StvecModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_mode 2
P o regOut_addr 62
F reg_mode 2 0
F reg_addr 62 0
S reg_mode ? w_wen & (w_wdata[1:0] == 2'h0 | w_wdata[1:0] == 2'h1) : w_wdata[1:0]
S reg_addr ? w_wen : w_wdata[63:2]
A rdata = {reg_addr, reg_mode}
A regOut_mode = reg_mode
A regOut_addr = reg_addr
M ScounterenModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_CY 1
P o regOut_TM 1
P o regOut_IR 1
P o regOut_HPM 29
F reg_CY 1 0
F reg_TM 1 0
F reg_IR 1 0
F reg_HPM 29 0
S reg_CY ? w_wen : w_wdata[0]
S reg_TM ? w_wen : w_wdata[1]
S reg_IR ? w_wen : w_wdata[2]
S reg_HPM ? w_wen : w_wdata[31:3]
A rdata = {32'h0, reg_HPM, reg_IR, reg_TM, reg_CY}
A regOut_CY = reg_CY
A regOut_TM = reg_TM
A regOut_IR = reg_IR
A regOut_HPM = reg_HPM
M SenvcfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_PMM 2
P o regOut_CBZE 1
P o regOut_CBCFE 1
P o regOut_CBIE 2
F reg_PMM 2 0
F reg_CBZE 1 1
F reg_CBCFE 1 1
F reg_CBIE 2 3
S reg_PMM ? w_wen & (w_wdata[33:32] == 2'h0 | w_wdata[33:32] == 2'h2 | (&(w_wdata[33:32]))) : w_wdata[33:32]
S reg_CBZE ? w_wen : w_wdata[7]
S reg_CBCFE ? w_wen : w_wdata[6]
S reg_CBIE ? w_wen & (w_wdata[5:4] == 2'h0 | w_wdata[5:4] == 2'h1 | (&(w_wdata[5:4]))) : w_wdata[5:4]
A rdata = {30'h0, reg_PMM, 24'h0, reg_CBZE, reg_CBCFE, reg_CBIE, 4'h0}
A regOut_PMM = reg_PMM
A regOut_CBZE = reg_CBZE
A regOut_CBCFE = reg_CBCFE
A regOut_CBIE = reg_CBIE
M SscratchModule n
P i clock 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
F reg_ALL 64 -
S reg_ALL ? w_wen : w_wdata
A rdata = reg_ALL
A regOut_ALL = reg_ALL
M SepcModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_epc 63
P i trapToHS_sepc_valid 1
P i trapToHS_sepc_bits_epc 63
F reg_epc 63 0
S reg_epc ? w_wen | trapToHS_sepc_valid : (trapToHS_sepc_valid ? trapToHS_sepc_bits_epc : 63'h0) | (w_wen ? w_wdata[63:1] : 63'h0)
A rdata = {reg_epc, 1'h0}
A regOut_epc = reg_epc
M ScauseModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_Interrupt 1
P o regOut_ExceptionCode 63
P i trapToHS_scause_valid 1
P i trapToHS_scause_bits_Interrupt 1
P i trapToHS_scause_bits_ExceptionCode 63
F reg_Interrupt 1 0
F reg_ExceptionCode 63 0
S reg_Interrupt ? w_wen | trapToHS_scause_valid : trapToHS_scause_valid & trapToHS_scause_bits_Interrupt | w_wen & w_wdata[63]
S reg_ExceptionCode ? w_wen | trapToHS_scause_valid : (trapToHS_scause_valid ? trapToHS_scause_bits_ExceptionCode : 63'h0) | (w_wen ? w_wdata[62:0] : 63'h0)
A rdata = {reg_Interrupt, reg_ExceptionCode}
A regOut_Interrupt = reg_Interrupt
A regOut_ExceptionCode = reg_ExceptionCode
M StvalModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i trapToHS_stval_valid 1
P i trapToHS_stval_bits_ALL 64
F reg_ALL 64 0
S reg_ALL ? w_wen | trapToHS_stval_valid : (trapToHS_stval_valid ? trapToHS_stval_bits_ALL : 64'h0) | (w_wen ? w_wdata : 64'h0)
A rdata = reg_ALL
A regOut_ALL = reg_ALL
M SipModule n
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_SSIP 1
P o regOut_STIP 1
P o regOut_SEIP 1
P o regOut_LCOFIP 1
P o regOut_LC14IP 1
P o regOut_LC15IP 1
P o regOut_LC16IP 1
P o regOut_LC17IP 1
P o regOut_LC18IP 1
P o regOut_LC19IP 1
P o regOut_LC20IP 1
P o regOut_LC21IP 1
P o regOut_LC22IP 1
P o regOut_LC23IP 1
P o regOut_LC24IP 1
P o regOut_LC25IP 1
P o regOut_LC26IP 1
P o regOut_LC27IP 1
P o regOut_LC28IP 1
P o regOut_LC29IP 1
P o regOut_LC30IP 1
P o regOut_LC31IP 1
P o regOut_LC32IP 1
P o regOut_LC33IP 1
P o regOut_LC34IP 1
P o regOut_LPRASEIP 1
P o regOut_LC36IP 1
P o regOut_LC37IP 1
P o regOut_LC38IP 1
P o regOut_LC39IP 1
P o regOut_LC40IP 1
P o regOut_LC41IP 1
P o regOut_LC42IP 1
P o regOut_HPRASEIP 1
P o regOut_LC44IP 1
P o regOut_LC45IP 1
P o regOut_LC46IP 1
P o regOut_LC47IP 1
P o regOut_LC48IP 1
P o regOut_LC49IP 1
P o regOut_LC50IP 1
P o regOut_LC51IP 1
P o regOut_LC52IP 1
P o regOut_LC53IP 1
P o regOut_LC54IP 1
P o regOut_LC55IP 1
P o regOut_LC56IP 1
P o regOut_LC57IP 1
P o regOut_LC58IP 1
P o regOut_LC59IP 1
P o regOut_LC60IP 1
P o regOut_LC61IP 1
P o regOut_LC62IP 1
P o regOut_LC63IP 1
P i mideleg_SSI 1
P i mideleg_STI 1
P i mideleg_SEI 1
P i mideleg_LCOFI 1
P i mip_SSIP 1
P i mip_VSSIP 1
P i mip_MSIP 1
P i mip_STIP 1
P i mip_VSTIP 1
P i mip_MTIP 1
P i mip_SEIP 1
P i mip_VSEIP 1
P i mip_MEIP 1
P i mip_SGEIP 1
P i mip_LCOFIP 1
P i mip_LC14IP 1
P i mip_LC15IP 1
P i mip_LC16IP 1
P i mip_LC17IP 1
P i mip_LC18IP 1
P i mip_LC19IP 1
P i mip_LC20IP 1
P i mip_LC21IP 1
P i mip_LC22IP 1
P i mip_LC23IP 1
P i mip_LC24IP 1
P i mip_LC25IP 1
P i mip_LC26IP 1
P i mip_LC27IP 1
P i mip_LC28IP 1
P i mip_LC29IP 1
P i mip_LC30IP 1
P i mip_LC31IP 1
P i mip_LC32IP 1
P i mip_LC33IP 1
P i mip_LC34IP 1
P i mip_LPRASEIP 1
P i mip_LC36IP 1
P i mip_LC37IP 1
P i mip_LC38IP 1
P i mip_LC39IP 1
P i mip_LC40IP 1
P i mip_LC41IP 1
P i mip_LC42IP 1
P i mip_HPRASEIP 1
P i mip_LC44IP 1
P i mip_LC45IP 1
P i mip_LC46IP 1
P i mip_LC47IP 1
P i mip_LC48IP 1
P i mip_LC49IP 1
P i mip_LC50IP 1
P i mip_LC51IP 1
P i mip_LC52IP 1
P i mip_LC53IP 1
P i mip_LC54IP 1
P i mip_LC55IP 1
P i mip_LC56IP 1
P i mip_LC57IP 1
P i mip_LC58IP 1
P i mip_LC59IP 1
P i mip_LC60IP 1
P i mip_LC61IP 1
P i mip_LC62IP 1
P i mip_LC63IP 1
P i mvip_SSIP 1
P i mvip_STIP 1
P i mvip_SEIP 1
P i mvip_LCOFIP 1
P i mvip_LC14IP 1
P i mvip_LC15IP 1
P i mvip_LC16IP 1
P i mvip_LC17IP 1
P i mvip_LC18IP 1
P i mvip_LC19IP 1
P i mvip_LC20IP 1
P i mvip_LC21IP 1
P i mvip_LC22IP 1
P i mvip_LC23IP 1
P i mvip_LC24IP 1
P i mvip_LC25IP 1
P i mvip_LC26IP 1
P i mvip_LC27IP 1
P i mvip_LC28IP 1
P i mvip_LC29IP 1
P i mvip_LC30IP 1
P i mvip_LC31IP 1
P i mvip_LC32IP 1
P i mvip_LC33IP 1
P i mvip_LC34IP 1
P i mvip_LPRASEIP 1
P i mvip_LC36IP 1
P i mvip_LC37IP 1
P i mvip_LC38IP 1
P i mvip_LC39IP 1
P i mvip_LC40IP 1
P i mvip_LC41IP 1
P i mvip_LC42IP 1
P i mvip_HPRASEIP 1
P i mvip_LC44IP 1
P i mvip_LC45IP 1
P i mvip_LC46IP 1
P i mvip_LC47IP 1
P i mvip_LC48IP 1
P i mvip_LC49IP 1
P i mvip_LC50IP 1
P i mvip_LC51IP 1
P i mvip_LC52IP 1
P i mvip_LC53IP 1
P i mvip_LC54IP 1
P i mvip_LC55IP 1
P i mvip_LC56IP 1
P i mvip_LC57IP 1
P i mvip_LC58IP 1
P i mvip_LC59IP 1
P i mvip_LC60IP 1
P i mvip_LC61IP 1
P i mvip_LC62IP 1
P i mvip_LC63IP 1
P i mvien_SSIE 1
P i mvien_SEIE 1
P i mvien_LC14IE 1
P i mvien_LC15IE 1
P i mvien_LC16IE 1
P i mvien_LC17IE 1
P i mvien_LC18IE 1
P i mvien_LC19IE 1
P i mvien_LC20IE 1
P i mvien_LC21IE 1
P i mvien_LC22IE 1
P i mvien_LC23IE 1
P i mvien_LC24IE 1
P i mvien_LC25IE 1
P i mvien_LC26IE 1
P i mvien_LC27IE 1
P i mvien_LC28IE 1
P i mvien_LC29IE 1
P i mvien_LC30IE 1
P i mvien_LC31IE 1
P i mvien_LC32IE 1
P i mvien_LC33IE 1
P i mvien_LC34IE 1
P i mvien_LPRASEIE 1
P i mvien_LC36IE 1
P i mvien_LC37IE 1
P i mvien_LC38IE 1
P i mvien_LC39IE 1
P i mvien_LC40IE 1
P i mvien_LC41IE 1
P i mvien_LC42IE 1
P i mvien_HPRASEIE 1
P i mvien_LC44IE 1
P i mvien_LC45IE 1
P i mvien_LC46IE 1
P i mvien_LC47IE 1
P i mvien_LC48IE 1
P i mvien_LC49IE 1
P i mvien_LC50IE 1
P i mvien_LC51IE 1
P i mvien_LC52IE 1
P i mvien_LC53IE 1
P i mvien_LC54IE 1
P i mvien_LC55IE 1
P i mvien_LC56IE 1
P i mvien_LC57IE 1
P i mvien_LC58IE 1
P i mvien_LC59IE 1
P i mvien_LC60IE 1
P i mvien_LC61IE 1
P i mvien_LC62IE 1
P i mvien_LC63IE 1
P o toMip_SSIP_valid 1
P o toMip_SSIP_bits 1
P o toMip_LCOFIP_valid 1
P o toMip_LCOFIP_bits 1
P o toMvip_SSIP_valid 1
P o toMvip_SSIP_bits 1
P o toMvip_LCOFIP_valid 1
P o toMvip_LCOFIP_bits 1
P o toMvip_LC14IP_valid 1
P o toMvip_LC14IP_bits 1
P o toMvip_LC15IP_valid 1
P o toMvip_LC15IP_bits 1
P o toMvip_LC16IP_valid 1
P o toMvip_LC16IP_bits 1
P o toMvip_LC17IP_valid 1
P o toMvip_LC17IP_bits 1
P o toMvip_LC18IP_valid 1
P o toMvip_LC18IP_bits 1
P o toMvip_LC19IP_valid 1
P o toMvip_LC19IP_bits 1
P o toMvip_LC20IP_valid 1
P o toMvip_LC20IP_bits 1
P o toMvip_LC21IP_valid 1
P o toMvip_LC21IP_bits 1
P o toMvip_LC22IP_valid 1
P o toMvip_LC22IP_bits 1
P o toMvip_LC23IP_valid 1
P o toMvip_LC23IP_bits 1
P o toMvip_LC24IP_valid 1
P o toMvip_LC24IP_bits 1
P o toMvip_LC25IP_valid 1
P o toMvip_LC25IP_bits 1
P o toMvip_LC26IP_valid 1
P o toMvip_LC26IP_bits 1
P o toMvip_LC27IP_valid 1
P o toMvip_LC27IP_bits 1
P o toMvip_LC28IP_valid 1
P o toMvip_LC28IP_bits 1
P o toMvip_LC29IP_valid 1
P o toMvip_LC29IP_bits 1
P o toMvip_LC30IP_valid 1
P o toMvip_LC30IP_bits 1
P o toMvip_LC31IP_valid 1
P o toMvip_LC31IP_bits 1
P o toMvip_LC32IP_valid 1
P o toMvip_LC32IP_bits 1
P o toMvip_LC33IP_valid 1
P o toMvip_LC33IP_bits 1
P o toMvip_LC34IP_valid 1
P o toMvip_LC34IP_bits 1
P o toMvip_LPRASEIP_valid 1
P o toMvip_LPRASEIP_bits 1
P o toMvip_LC36IP_valid 1
P o toMvip_LC36IP_bits 1
P o toMvip_LC37IP_valid 1
P o toMvip_LC37IP_bits 1
P o toMvip_LC38IP_valid 1
P o toMvip_LC38IP_bits 1
P o toMvip_LC39IP_valid 1
P o toMvip_LC39IP_bits 1
P o toMvip_LC40IP_valid 1
P o toMvip_LC40IP_bits 1
P o toMvip_LC41IP_valid 1
P o toMvip_LC41IP_bits 1
P o toMvip_LC42IP_valid 1
P o toMvip_LC42IP_bits 1
P o toMvip_HPRASEIP_valid 1
P o toMvip_HPRASEIP_bits 1
P o toMvip_LC44IP_valid 1
P o toMvip_LC44IP_bits 1
P o toMvip_LC45IP_valid 1
P o toMvip_LC45IP_bits 1
P o toMvip_LC46IP_valid 1
P o toMvip_LC46IP_bits 1
P o toMvip_LC47IP_valid 1
P o toMvip_LC47IP_bits 1
P o toMvip_LC48IP_valid 1
P o toMvip_LC48IP_bits 1
P o toMvip_LC49IP_valid 1
P o toMvip_LC49IP_bits 1
P o toMvip_LC50IP_valid 1
P o toMvip_LC50IP_bits 1
P o toMvip_LC51IP_valid 1
P o toMvip_LC51IP_bits 1
P o toMvip_LC52IP_valid 1
P o toMvip_LC52IP_bits 1
P o toMvip_LC53IP_valid 1
P o toMvip_LC53IP_bits 1
P o toMvip_LC54IP_valid 1
P o toMvip_LC54IP_bits 1
P o toMvip_LC55IP_valid 1
P o toMvip_LC55IP_bits 1
P o toMvip_LC56IP_valid 1
P o toMvip_LC56IP_bits 1
P o toMvip_LC57IP_valid 1
P o toMvip_LC57IP_bits 1
P o toMvip_LC58IP_valid 1
P o toMvip_LC58IP_bits 1
P o toMvip_LC59IP_valid 1
P o toMvip_LC59IP_bits 1
P o toMvip_LC60IP_valid 1
P o toMvip_LC60IP_bits 1
P o toMvip_LC61IP_valid 1
P o toMvip_LC61IP_bits 1
P o toMvip_LC62IP_valid 1
P o toMvip_LC62IP_bits 1
P o toMvip_LC63IP_valid 1
P o toMvip_LC63IP_bits 1
D _regOut_SSIP_T 1
D _regOut_STIP_T 1
D _regOut_SEIP_T 1
D _GEN 63
W mvipIsAlias 64 = {50'h3FFFFFFFFFFFF, ~mideleg_LCOFI, 3'h2, ~mideleg_SEI, 3'h6, ~mideleg_STI, 3'h6, ~mideleg_SSI, 1'h1} & {mvien_LC63IE, mvien_LC62IE, mvien_LC61IE, mvien_LC60IE, mvien_LC59IE, mvien_LC58IE, mvien_LC57IE, mvien_LC56IE, mvien_LC55IE, mvien_LC54IE, mvien_LC53IE, mvien_LC52IE, mvien_LC51IE, mvien_LC50IE, mvien_LC49IE, mvien_LC48IE, mvien_LC47IE, mvien_LC46IE, mvien_LC45IE, mvien_LC44IE, mvien_HPRASEIE, mvien_LC42IE, mvien_LC41IE, mvien_LC40IE, mvien_LC39IE, mvien_LC38IE, mvien_LC37IE, mvien_LC36IE, mvien_LPRASEIE, mvien_LC34IE, mvien_LC33IE, mvien_LC32IE, mvien_LC31IE, mvien_LC30IE, mvien_LC29IE, mvien_LC28IE, mvien_LC27IE, mvien_LC26IE, mvien_LC25IE, mvien_LC24IE, mvien_LC23IE, mvien_LC22IE, mvien_LC21IE, mvien_LC20IE, mvien_LC19IE, mvien_LC18IE, mvien_LC17IE, mvien_LC16IE, mvien_LC15IE, mvien_LC14IE, 4'h0, mvien_SEIE, 7'h0, mvien_SSIE, 1'h0}
A _GEN = {50'h0, mideleg_LCOFI, 3'h5, mideleg_SEI, 3'h1, mideleg_STI, 3'h1, mideleg_SSI} & {mip_LC63IP, mip_LC62IP, mip_LC61IP, mip_LC60IP, mip_LC59IP, mip_LC58IP, mip_LC57IP, mip_LC56IP, mip_LC55IP, mip_LC54IP, mip_LC53IP, mip_LC52IP, mip_LC51IP, mip_LC50IP, mip_LC49IP, mip_LC48IP, mip_LC47IP, mip_LC46IP, mip_LC45IP, mip_LC44IP, mip_HPRASEIP, mip_LC42IP, mip_LC41IP, mip_LC40IP, mip_LC39IP, mip_LC38IP, mip_LC37IP, mip_LC36IP, mip_LPRASEIP, mip_LC34IP, mip_LC33IP, mip_LC32IP, mip_LC31IP, mip_LC30IP, mip_LC29IP, mip_LC28IP, mip_LC27IP, mip_LC26IP, mip_LC25IP, mip_LC24IP, mip_LC23IP, mip_LC22IP, mip_LC21IP, mip_LC20IP, mip_LC19IP, mip_LC18IP, mip_LC17IP, mip_LC16IP, mip_LC15IP, mip_LC14IP, mip_LCOFIP, mip_SGEIP, mip_MEIP, mip_VSEIP, mip_SEIP, 1'h0, mip_MTIP, mip_VSTIP, mip_STIP, 1'h0, mip_MSIP, mip_VSSIP, mip_SSIP} | mvipIsAlias[63:1] & {mvip_LC63IP, mvip_LC62IP, mvip_LC61IP, mvip_LC60IP, mvip_LC59IP, mvip_LC58IP, mvip_LC57IP, mvip_LC56IP, mvip_LC55IP, mvip_LC54IP, mvip_LC53IP, mvip_LC52IP, mvip_LC51IP, mvip_LC50IP, mvip_LC49IP, mvip_LC48IP, mvip_LC47IP, mvip_LC46IP, mvip_LC45IP, mvip_LC44IP, mvip_HPRASEIP, mvip_LC42IP, mvip_LC41IP, mvip_LC40IP, mvip_LC39IP, mvip_LC38IP, mvip_LC37IP, mvip_LC36IP, mvip_LPRASEIP, mvip_LC34IP, mvip_LC33IP, mvip_LC32IP, mvip_LC31IP, mvip_LC30IP, mvip_LC29IP, mvip_LC28IP, mvip_LC27IP, mvip_LC26IP, mvip_LC25IP, mvip_LC24IP, mvip_LC23IP, mvip_LC22IP, mvip_LC21IP, mvip_LC20IP, mvip_LC19IP, mvip_LC18IP, mvip_LC17IP, mvip_LC16IP, mvip_LC15IP, mvip_LC14IP, mvip_LCOFIP, 3'h0, mvip_SEIP, 3'h0, mvip_STIP, 3'h0, mvip_SSIP}
A _regOut_SEIP_T = _GEN[8]
A _regOut_STIP_T = _GEN[4]
A _regOut_SSIP_T = _GEN[0]
A rdata = {_GEN[62:12], 3'h0, _regOut_SEIP_T, 3'h0, _regOut_STIP_T, 3'h0, _regOut_SSIP_T, 1'h0}
A regOut_SSIP = _regOut_SSIP_T
A regOut_STIP = _regOut_STIP_T
A regOut_SEIP = _regOut_SEIP_T
A regOut_LCOFIP = _GEN[12]
A regOut_LC14IP = _GEN[13]
A regOut_LC15IP = _GEN[14]
A regOut_LC16IP = _GEN[15]
A regOut_LC17IP = _GEN[16]
A regOut_LC18IP = _GEN[17]
A regOut_LC19IP = _GEN[18]
A regOut_LC20IP = _GEN[19]
A regOut_LC21IP = _GEN[20]
A regOut_LC22IP = _GEN[21]
A regOut_LC23IP = _GEN[22]
A regOut_LC24IP = _GEN[23]
A regOut_LC25IP = _GEN[24]
A regOut_LC26IP = _GEN[25]
A regOut_LC27IP = _GEN[26]
A regOut_LC28IP = _GEN[27]
A regOut_LC29IP = _GEN[28]
A regOut_LC30IP = _GEN[29]
A regOut_LC31IP = _GEN[30]
A regOut_LC32IP = _GEN[31]
A regOut_LC33IP = _GEN[32]
A regOut_LC34IP = _GEN[33]
A regOut_LPRASEIP = _GEN[34]
A regOut_LC36IP = _GEN[35]
A regOut_LC37IP = _GEN[36]
A regOut_LC38IP = _GEN[37]
A regOut_LC39IP = _GEN[38]
A regOut_LC40IP = _GEN[39]
A regOut_LC41IP = _GEN[40]
A regOut_LC42IP = _GEN[41]
A regOut_HPRASEIP = _GEN[42]
A regOut_LC44IP = _GEN[43]
A regOut_LC45IP = _GEN[44]
A regOut_LC46IP = _GEN[45]
A regOut_LC47IP = _GEN[46]
A regOut_LC48IP = _GEN[47]
A regOut_LC49IP = _GEN[48]
A regOut_LC50IP = _GEN[49]
A regOut_LC51IP = _GEN[50]
A regOut_LC52IP = _GEN[51]
A regOut_LC53IP = _GEN[52]
A regOut_LC54IP = _GEN[53]
A regOut_LC55IP = _GEN[54]
A regOut_LC56IP = _GEN[55]
A regOut_LC57IP = _GEN[56]
A regOut_LC58IP = _GEN[57]
A regOut_LC59IP = _GEN[58]
A regOut_LC60IP = _GEN[59]
A regOut_LC61IP = _GEN[60]
A regOut_LC62IP = _GEN[61]
A regOut_LC63IP = _GEN[62]
A toMip_SSIP_valid = w_wen & mideleg_SSI
A toMip_SSIP_bits = w_wen & mideleg_SSI & w_wdata[1]
A toMip_LCOFIP_valid = w_wen & mideleg_LCOFI
A toMip_LCOFIP_bits = w_wen & mideleg_LCOFI & w_wdata[13]
A toMvip_SSIP_valid = w_wen & mvipIsAlias[1]
A toMvip_SSIP_bits = w_wen & mvipIsAlias[1] & w_wdata[1]
A toMvip_LCOFIP_valid = w_wen & mvipIsAlias[13]
A toMvip_LCOFIP_bits = w_wen & mvipIsAlias[13] & w_wdata[13]
A toMvip_LC14IP_valid = w_wen & mvipIsAlias[14]
A toMvip_LC14IP_bits = w_wen & mvipIsAlias[14] & w_wdata[14]
A toMvip_LC15IP_valid = w_wen & mvipIsAlias[15]
A toMvip_LC15IP_bits = w_wen & mvipIsAlias[15] & w_wdata[15]
A toMvip_LC16IP_valid = w_wen & mvipIsAlias[16]
A toMvip_LC16IP_bits = w_wen & mvipIsAlias[16] & w_wdata[16]
A toMvip_LC17IP_valid = w_wen & mvipIsAlias[17]
A toMvip_LC17IP_bits = w_wen & mvipIsAlias[17] & w_wdata[17]
A toMvip_LC18IP_valid = w_wen & mvipIsAlias[18]
A toMvip_LC18IP_bits = w_wen & mvipIsAlias[18] & w_wdata[18]
A toMvip_LC19IP_valid = w_wen & mvipIsAlias[19]
A toMvip_LC19IP_bits = w_wen & mvipIsAlias[19] & w_wdata[19]
A toMvip_LC20IP_valid = w_wen & mvipIsAlias[20]
A toMvip_LC20IP_bits = w_wen & mvipIsAlias[20] & w_wdata[20]
A toMvip_LC21IP_valid = w_wen & mvipIsAlias[21]
A toMvip_LC21IP_bits = w_wen & mvipIsAlias[21] & w_wdata[21]
A toMvip_LC22IP_valid = w_wen & mvipIsAlias[22]
A toMvip_LC22IP_bits = w_wen & mvipIsAlias[22] & w_wdata[22]
A toMvip_LC23IP_valid = w_wen & mvipIsAlias[23]
A toMvip_LC23IP_bits = w_wen & mvipIsAlias[23] & w_wdata[23]
A toMvip_LC24IP_valid = w_wen & mvipIsAlias[24]
A toMvip_LC24IP_bits = w_wen & mvipIsAlias[24] & w_wdata[24]
A toMvip_LC25IP_valid = w_wen & mvipIsAlias[25]
A toMvip_LC25IP_bits = w_wen & mvipIsAlias[25] & w_wdata[25]
A toMvip_LC26IP_valid = w_wen & mvipIsAlias[26]
A toMvip_LC26IP_bits = w_wen & mvipIsAlias[26] & w_wdata[26]
A toMvip_LC27IP_valid = w_wen & mvipIsAlias[27]
A toMvip_LC27IP_bits = w_wen & mvipIsAlias[27] & w_wdata[27]
A toMvip_LC28IP_valid = w_wen & mvipIsAlias[28]
A toMvip_LC28IP_bits = w_wen & mvipIsAlias[28] & w_wdata[28]
A toMvip_LC29IP_valid = w_wen & mvipIsAlias[29]
A toMvip_LC29IP_bits = w_wen & mvipIsAlias[29] & w_wdata[29]
A toMvip_LC30IP_valid = w_wen & mvipIsAlias[30]
A toMvip_LC30IP_bits = w_wen & mvipIsAlias[30] & w_wdata[30]
A toMvip_LC31IP_valid = w_wen & mvipIsAlias[31]
A toMvip_LC31IP_bits = w_wen & mvipIsAlias[31] & w_wdata[31]
A toMvip_LC32IP_valid = w_wen & mvipIsAlias[32]
A toMvip_LC32IP_bits = w_wen & mvipIsAlias[32] & w_wdata[32]
A toMvip_LC33IP_valid = w_wen & mvipIsAlias[33]
A toMvip_LC33IP_bits = w_wen & mvipIsAlias[33] & w_wdata[33]
A toMvip_LC34IP_valid = w_wen & mvipIsAlias[34]
A toMvip_LC34IP_bits = w_wen & mvipIsAlias[34] & w_wdata[34]
A toMvip_LPRASEIP_valid = w_wen & mvipIsAlias[35]
A toMvip_LPRASEIP_bits = w_wen & mvipIsAlias[35] & w_wdata[35]
A toMvip_LC36IP_valid = w_wen & mvipIsAlias[36]
A toMvip_LC36IP_bits = w_wen & mvipIsAlias[36] & w_wdata[36]
A toMvip_LC37IP_valid = w_wen & mvipIsAlias[37]
A toMvip_LC37IP_bits = w_wen & mvipIsAlias[37] & w_wdata[37]
A toMvip_LC38IP_valid = w_wen & mvipIsAlias[38]
A toMvip_LC38IP_bits = w_wen & mvipIsAlias[38] & w_wdata[38]
A toMvip_LC39IP_valid = w_wen & mvipIsAlias[39]
A toMvip_LC39IP_bits = w_wen & mvipIsAlias[39] & w_wdata[39]
A toMvip_LC40IP_valid = w_wen & mvipIsAlias[40]
A toMvip_LC40IP_bits = w_wen & mvipIsAlias[40] & w_wdata[40]
A toMvip_LC41IP_valid = w_wen & mvipIsAlias[41]
A toMvip_LC41IP_bits = w_wen & mvipIsAlias[41] & w_wdata[41]
A toMvip_LC42IP_valid = w_wen & mvipIsAlias[42]
A toMvip_LC42IP_bits = w_wen & mvipIsAlias[42] & w_wdata[42]
A toMvip_HPRASEIP_valid = w_wen & mvipIsAlias[43]
A toMvip_HPRASEIP_bits = w_wen & mvipIsAlias[43] & w_wdata[43]
A toMvip_LC44IP_valid = w_wen & mvipIsAlias[44]
A toMvip_LC44IP_bits = w_wen & mvipIsAlias[44] & w_wdata[44]
A toMvip_LC45IP_valid = w_wen & mvipIsAlias[45]
A toMvip_LC45IP_bits = w_wen & mvipIsAlias[45] & w_wdata[45]
A toMvip_LC46IP_valid = w_wen & mvipIsAlias[46]
A toMvip_LC46IP_bits = w_wen & mvipIsAlias[46] & w_wdata[46]
A toMvip_LC47IP_valid = w_wen & mvipIsAlias[47]
A toMvip_LC47IP_bits = w_wen & mvipIsAlias[47] & w_wdata[47]
A toMvip_LC48IP_valid = w_wen & mvipIsAlias[48]
A toMvip_LC48IP_bits = w_wen & mvipIsAlias[48] & w_wdata[48]
A toMvip_LC49IP_valid = w_wen & mvipIsAlias[49]
A toMvip_LC49IP_bits = w_wen & mvipIsAlias[49] & w_wdata[49]
A toMvip_LC50IP_valid = w_wen & mvipIsAlias[50]
A toMvip_LC50IP_bits = w_wen & mvipIsAlias[50] & w_wdata[50]
A toMvip_LC51IP_valid = w_wen & mvipIsAlias[51]
A toMvip_LC51IP_bits = w_wen & mvipIsAlias[51] & w_wdata[51]
A toMvip_LC52IP_valid = w_wen & mvipIsAlias[52]
A toMvip_LC52IP_bits = w_wen & mvipIsAlias[52] & w_wdata[52]
A toMvip_LC53IP_valid = w_wen & mvipIsAlias[53]
A toMvip_LC53IP_bits = w_wen & mvipIsAlias[53] & w_wdata[53]
A toMvip_LC54IP_valid = w_wen & mvipIsAlias[54]
A toMvip_LC54IP_bits = w_wen & mvipIsAlias[54] & w_wdata[54]
A toMvip_LC55IP_valid = w_wen & mvipIsAlias[55]
A toMvip_LC55IP_bits = w_wen & mvipIsAlias[55] & w_wdata[55]
A toMvip_LC56IP_valid = w_wen & mvipIsAlias[56]
A toMvip_LC56IP_bits = w_wen & mvipIsAlias[56] & w_wdata[56]
A toMvip_LC57IP_valid = w_wen & mvipIsAlias[57]
A toMvip_LC57IP_bits = w_wen & mvipIsAlias[57] & w_wdata[57]
A toMvip_LC58IP_valid = w_wen & mvipIsAlias[58]
A toMvip_LC58IP_bits = w_wen & mvipIsAlias[58] & w_wdata[58]
A toMvip_LC59IP_valid = w_wen & mvipIsAlias[59]
A toMvip_LC59IP_bits = w_wen & mvipIsAlias[59] & w_wdata[59]
A toMvip_LC60IP_valid = w_wen & mvipIsAlias[60]
A toMvip_LC60IP_bits = w_wen & mvipIsAlias[60] & w_wdata[60]
A toMvip_LC61IP_valid = w_wen & mvipIsAlias[61]
A toMvip_LC61IP_bits = w_wen & mvipIsAlias[61] & w_wdata[61]
A toMvip_LC62IP_valid = w_wen & mvipIsAlias[62]
A toMvip_LC62IP_bits = w_wen & mvipIsAlias[62] & w_wdata[62]
A toMvip_LC63IP_valid = w_wen & mvipIsAlias[63]
A toMvip_LC63IP_bits = w_wen & mvipIsAlias[63] & w_wdata[63]
M StimecmpModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_stimecmp 64
F reg_stimecmp 64 18446744073709551615
S reg_stimecmp ? w_wen : w_wdata
A rdata = reg_stimecmp
A regOut_stimecmp = reg_stimecmp
M SatpModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_MODE 4
P o regOut_ASID 16
P o regOut_PPN 44
F reg_MODE 4 0
F reg_ASID 16 0
F reg_PPN 44 0
S reg_MODE ? w_wen & (w_wdata[63:60] == 4'h0 | w_wdata[63:60] == 4'h8 | w_wdata[63:60] == 4'h9) : w_wdata[63:60]
S reg_ASID ? w_wen & (w_wdata[63:60] == 4'h0 | w_wdata[63:60] == 4'h8 | w_wdata[63:60] == 4'h9) : w_wdata[59:44]
S reg_PPN ? w_wen & (w_wdata[63:60] == 4'h0 | w_wdata[63:60] == 4'h8 | w_wdata[63:60] == 4'h9) : {8'h0, w_wdata[35:0]}
A rdata = {reg_MODE, reg_ASID, reg_PPN}
A regOut_MODE = reg_MODE
A regOut_ASID = reg_ASID
A regOut_PPN = reg_PPN
M ScountovfModule n
P o rdata 32
P i ofVec 29
P i privState_PRVM 2
P i privState_V 1
P i mcounteren_HPM 29
P i hcounteren_HPM 29
D _regOut_OFVEC_WIRE 29
W v_PrvmIsM 1 = &privState_PRVM
W isModeM 1 = v_PrvmIsM
W PrvmIsS 1 = privState_PRVM == 2'h1
W isModeHS 1 = ~privState_V & PrvmIsS
W isModeVS 1 = privState_V & PrvmIsS
A _regOut_OFVEC_WIRE = (isModeM ? ofVec : 29'h0) | (isModeHS ? mcounteren_HPM & ofVec : 29'h0) | (isModeVS ? mcounteren_HPM & hcounteren_HPM & ofVec : 29'h0)
A rdata = {_regOut_OFVEC_WIRE, 3'h0}
M Sstateen0Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 32
P o regOut_JVT 1
P o regOut_FCSR 1
P o regOut_C 1
P i fromMstateen0_SE0 1
P i fromMstateen0_ENVCFG 1
P i fromMstateen0_CSRIND 1
P i fromMstateen0_AIA 1
P i fromMstateen0_IMSIC 1
P i fromMstateen0_CONTEXT 1
P i fromMstateen0_C 1
P i fromHstateen0_JVT 1
P i fromHstateen0_FCSR 1
P i fromHstateen0_C 1
P i fromHstateen0_SE0 1
P i fromHstateen0_ENVCFG 1
P i fromHstateen0_CSRIND 1
P i fromHstateen0_AIA 1
P i fromHstateen0_IMSIC 1
P i fromHstateen0_CONTEXT 1
P i privState_V 1
F reg_C 1 0
D _GEN 3
S reg_C ? w_wen : w_wdata[0]
A _GEN = (privState_V ? {fromHstateen0_JVT, fromHstateen0_FCSR, fromHstateen0_C} : {2'h0, fromMstateen0_C}) & {2'h0, reg_C}
A rdata = {29'h0, _GEN}
A regOut_JVT = _GEN[2]
A regOut_FCSR = _GEN[1]
A regOut_C = _GEN[0]
M Sstateen1Module n
P o rdata 32
P o regOut_ALL 32
A rdata = 32'h0
A regOut_ALL = 32'h0
M Sstateen2Module n
P o rdata 32
P o regOut_ALL 32
A rdata = 32'h0
A regOut_ALL = 32'h0
M Sstateen3Module n
P o rdata 32
P o regOut_ALL 32
A rdata = 32'h0
A regOut_ALL = 32'h0
M ScontextModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 32
P o regOut_ALL 32
F reg_ALL 32 0
S reg_ALL ? w_wen : w_wdata[31:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
M HstatusModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_GVA 1
P o regOut_SPV 1
P o regOut_SPVP 1
P o regOut_HU 1
P o regOut_VGEIN 6
P o regOut_VTVM 1
P o regOut_VTW 1
P o regOut_VTSR 1
P o regOut_HUPMM 2
P i retFromS_hstatus_valid 1
P i retFromS_hstatus_bits_SPV 1
P i trapToHS_hstatus_valid 1
P i trapToHS_hstatus_bits_GVA 1
P i trapToHS_hstatus_bits_SPV 1
P i trapToHS_hstatus_bits_SPVP 1
F reg_GVA 1 0
F reg_SPV 1 0
F reg_SPVP 1 0
F reg_HU 1 0
F reg_VGEIN 6 0
F reg_VTVM 1 0
F reg_VTW 1 0
F reg_VTSR 1 0
F reg_HUPMM 2 0
S reg_GVA ? w_wen | trapToHS_hstatus_valid : trapToHS_hstatus_valid & trapToHS_hstatus_bits_GVA | w_wen & w_wdata[6]
S reg_SPVP ? w_wen | trapToHS_hstatus_valid : trapToHS_hstatus_valid & trapToHS_hstatus_bits_SPVP | w_wen & w_wdata[8]
S reg_SPV ? w_wen | retFromS_hstatus_valid | trapToHS_hstatus_valid : retFromS_hstatus_valid & retFromS_hstatus_bits_SPV | trapToHS_hstatus_valid & trapToHS_hstatus_bits_SPV | w_wen & w_wdata[7]
S reg_HU ? w_wen : w_wdata[9]
S reg_VGEIN ? w_wen : w_wdata[17:12]
S reg_VTVM ? w_wen : w_wdata[20]
S reg_VTW ? w_wen : w_wdata[21]
S reg_VTSR ? w_wen : w_wdata[22]
S reg_HUPMM ? w_wen & (w_wdata[49:48] == 2'h0 | w_wdata[49:48] == 2'h2 | (&(w_wdata[49:48]))) : w_wdata[49:48]
A rdata = {14'h0, reg_HUPMM, 25'h400, reg_VTSR, reg_VTW, reg_VTVM, 2'h0, reg_VGEIN, 2'h0, reg_HU, reg_SPVP, reg_SPV, reg_GVA, 6'h0}
A regOut_GVA = reg_GVA
A regOut_SPV = reg_SPV
A regOut_SPVP = reg_SPVP
A regOut_HU = reg_HU
A regOut_VGEIN = reg_VGEIN
A regOut_VTVM = reg_VTVM
A regOut_VTW = reg_VTW
A regOut_VTSR = reg_VTSR
A regOut_HUPMM = reg_HUPMM
M HedelegModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_EX_IAM 1
P o regOut_EX_IAF 1
P o regOut_EX_II 1
P o regOut_EX_BP 1
P o regOut_EX_LAM 1
P o regOut_EX_LAF 1
P o regOut_EX_SAM 1
P o regOut_EX_SAF 1
P o regOut_EX_UCALL 1
P o regOut_EX_IPF 1
P o regOut_EX_LPF 1
P o regOut_EX_SPF 1
P o regOut_EX_SWC 1
P o regOut_EX_HWE 1
F reg_EX_IAM 1 0
F reg_EX_IAF 1 0
F reg_EX_II 1 0
F reg_EX_BP 1 0
F reg_EX_LAM 1 0
F reg_EX_LAF 1 0
F reg_EX_SAM 1 0
F reg_EX_SAF 1 0
F reg_EX_UCALL 1 0
F reg_EX_IPF 1 0
F reg_EX_LPF 1 0
F reg_EX_SPF 1 0
F reg_EX_SWC 1 0
F reg_EX_HWE 1 0
S reg_EX_IAM ? w_wen : w_wdata[0]
S reg_EX_IAF ? w_wen : w_wdata[1]
S reg_EX_II ? w_wen : w_wdata[2]
S reg_EX_BP ? w_wen : w_wdata[3]
S reg_EX_LAM ? w_wen : w_wdata[4]
S reg_EX_LAF ? w_wen : w_wdata[5]
S reg_EX_SAM ? w_wen : w_wdata[6]
S reg_EX_SAF ? w_wen : w_wdata[7]
S reg_EX_UCALL ? w_wen : w_wdata[8]
S reg_EX_IPF ? w_wen : w_wdata[12]
S reg_EX_LPF ? w_wen : w_wdata[13]
S reg_EX_SPF ? w_wen : w_wdata[15]
S reg_EX_SWC ? w_wen : w_wdata[18]
S reg_EX_HWE ? w_wen : w_wdata[19]
A rdata = {44'h0, reg_EX_HWE, reg_EX_SWC, 2'h0, reg_EX_SPF, 1'h0, reg_EX_LPF, reg_EX_IPF, 3'h0, reg_EX_UCALL, reg_EX_SAF, reg_EX_SAM, reg_EX_LAF, reg_EX_LAM, reg_EX_BP, reg_EX_II, reg_EX_IAF, reg_EX_IAM}
A regOut_EX_IAM = reg_EX_IAM
A regOut_EX_IAF = reg_EX_IAF
A regOut_EX_II = reg_EX_II
A regOut_EX_BP = reg_EX_BP
A regOut_EX_LAM = reg_EX_LAM
A regOut_EX_LAF = reg_EX_LAF
A regOut_EX_SAM = reg_EX_SAM
A regOut_EX_SAF = reg_EX_SAF
A regOut_EX_UCALL = reg_EX_UCALL
A regOut_EX_IPF = reg_EX_IPF
A regOut_EX_LPF = reg_EX_LPF
A regOut_EX_SPF = reg_EX_SPF
A regOut_EX_SWC = reg_EX_SWC
A regOut_EX_HWE = reg_EX_HWE
M HidelegModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_SSI 1
P o regOut_VSSI 1
P o regOut_MSI 1
P o regOut_STI 1
P o regOut_VSTI 1
P o regOut_MTI 1
P o regOut_SEI 1
P o regOut_VSEI 1
P o regOut_MEI 1
P o regOut_SGEI 1
P o regOut_LCOFI 1
P i mideleg_SSI 1
P i mideleg_STI 1
P i mideleg_SEI 1
P i mideleg_LCOFI 1
F reg_VSSI 1 0
F reg_VSTI 1 0
F reg_VSEI 1 0
F reg_LCOFI 1 0
D _regOut_LCOFI_WIRE_2 1
S reg_VSSI ? w_wen : w_wdata[2]
S reg_VSTI ? w_wen : w_wdata[6]
S reg_VSEI ? w_wen : w_wdata[10]
S reg_LCOFI ? w_wen : w_wdata[13]
A _regOut_LCOFI_WIRE_2 = reg_LCOFI & mideleg_LCOFI
A rdata = {50'h0, _regOut_LCOFI_WIRE_2, 2'h0, reg_VSEI, 3'h0, reg_VSTI, 3'h0, reg_VSSI, 2'h0}
A regOut_SSI = 1'h0
A regOut_VSSI = reg_VSSI
A regOut_MSI = 1'h0
A regOut_STI = 1'h0
A regOut_VSTI = reg_VSTI
A regOut_MTI = 1'h0
A regOut_SEI = 1'h0
A regOut_VSEI = reg_VSEI
A regOut_MEI = 1'h0
A regOut_SGEI = 1'h0
A regOut_LCOFI = _regOut_LCOFI_WIRE_2
M HieModule n
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_VSSIE 1
P o regOut_VSTIE 1
P o regOut_VSEIE 1
P o regOut_SGEIE 1
P i mie_VSSIE 1
P i mie_VSTIE 1
P i mie_VSEIE 1
P i mie_SGEIE 1
P o toMie_VSSIE_valid 1
P o toMie_VSSIE_bits 1
P o toMie_VSTIE_valid 1
P o toMie_VSTIE_bits 1
P o toMie_VSEIE_valid 1
P o toMie_VSEIE_bits 1
P o toMie_SGEIE_valid 1
P o toMie_SGEIE_bits 1
A rdata = {51'h0, mie_SGEIE, 1'h0, mie_VSEIE, 3'h0, mie_VSTIE, 3'h0, mie_VSSIE, 2'h0}
A regOut_VSSIE = mie_VSSIE
A regOut_VSTIE = mie_VSTIE
A regOut_VSEIE = mie_VSEIE
A regOut_SGEIE = mie_SGEIE
A toMie_VSSIE_valid = w_wen
A toMie_VSSIE_bits = w_wen & w_wdata[2]
A toMie_VSTIE_valid = w_wen
A toMie_VSTIE_bits = w_wen & w_wdata[6]
A toMie_VSEIE_valid = w_wen
A toMie_VSEIE_bits = w_wen & w_wdata[10]
A toMie_SGEIE_valid = w_wen
A toMie_SGEIE_bits = w_wen & w_wdata[12]
M HtimedeltaModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
F reg_ALL 64 0
S reg_ALL ? w_wen : w_wdata
A rdata = reg_ALL
A regOut_ALL = reg_ALL
M HcounterenModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_CY 1
P o regOut_TM 1
P o regOut_IR 1
P o regOut_HPM 29
F reg_CY 1 0
F reg_TM 1 0
F reg_IR 1 0
F reg_HPM 29 0
S reg_CY ? w_wen : w_wdata[0]
S reg_TM ? w_wen : w_wdata[1]
S reg_IR ? w_wen : w_wdata[2]
S reg_HPM ? w_wen : w_wdata[31:3]
A rdata = {32'h0, reg_HPM, reg_IR, reg_TM, reg_CY}
A regOut_CY = reg_CY
A regOut_TM = reg_TM
A regOut_IR = reg_IR
A regOut_HPM = reg_HPM
M HgeieModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ie 7
F reg_ie 7 0
S reg_ie ? w_wen : w_wdata[7:1]
A rdata = {56'h0, reg_ie, 1'h0}
A regOut_ie = reg_ie
M HvienModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_LC14IE 1
P o regOut_LC15IE 1
P o regOut_LC16IE 1
P o regOut_LC17IE 1
P o regOut_LC18IE 1
P o regOut_LC19IE 1
P o regOut_LC20IE 1
P o regOut_LC21IE 1
P o regOut_LC22IE 1
P o regOut_LC23IE 1
P o regOut_LC24IE 1
P o regOut_LC25IE 1
P o regOut_LC26IE 1
P o regOut_LC27IE 1
P o regOut_LC28IE 1
P o regOut_LC29IE 1
P o regOut_LC30IE 1
P o regOut_LC31IE 1
P o regOut_LC32IE 1
P o regOut_LC33IE 1
P o regOut_LC34IE 1
P o regOut_LPRASEIE 1
P o regOut_LC36IE 1
P o regOut_LC37IE 1
P o regOut_LC38IE 1
P o regOut_LC39IE 1
P o regOut_LC40IE 1
P o regOut_LC41IE 1
P o regOut_LC42IE 1
P o regOut_HPRASEIE 1
P o regOut_LC44IE 1
P o regOut_LC45IE 1
P o regOut_LC46IE 1
P o regOut_LC47IE 1
P o regOut_LC48IE 1
P o regOut_LC49IE 1
P o regOut_LC50IE 1
P o regOut_LC51IE 1
P o regOut_LC52IE 1
P o regOut_LC53IE 1
P o regOut_LC54IE 1
P o regOut_LC55IE 1
P o regOut_LC56IE 1
P o regOut_LC57IE 1
P o regOut_LC58IE 1
P o regOut_LC59IE 1
P o regOut_LC60IE 1
P o regOut_LC61IE 1
P o regOut_LC62IE 1
P o regOut_LC63IE 1
F reg_LC14IE 1 0
F reg_LC15IE 1 0
F reg_LC16IE 1 0
F reg_LC17IE 1 0
F reg_LC18IE 1 0
F reg_LC19IE 1 0
F reg_LC20IE 1 0
F reg_LC21IE 1 0
F reg_LC22IE 1 0
F reg_LC23IE 1 0
F reg_LC24IE 1 0
F reg_LC25IE 1 0
F reg_LC26IE 1 0
F reg_LC27IE 1 0
F reg_LC28IE 1 0
F reg_LC29IE 1 0
F reg_LC30IE 1 0
F reg_LC31IE 1 0
F reg_LC32IE 1 0
F reg_LC33IE 1 0
F reg_LC34IE 1 0
F reg_LPRASEIE 1 0
F reg_LC36IE 1 0
F reg_LC37IE 1 0
F reg_LC38IE 1 0
F reg_LC39IE 1 0
F reg_LC40IE 1 0
F reg_LC41IE 1 0
F reg_LC42IE 1 0
F reg_HPRASEIE 1 0
F reg_LC44IE 1 0
F reg_LC45IE 1 0
F reg_LC46IE 1 0
F reg_LC47IE 1 0
F reg_LC48IE 1 0
F reg_LC49IE 1 0
F reg_LC50IE 1 0
F reg_LC51IE 1 0
F reg_LC52IE 1 0
F reg_LC53IE 1 0
F reg_LC54IE 1 0
F reg_LC55IE 1 0
F reg_LC56IE 1 0
F reg_LC57IE 1 0
F reg_LC58IE 1 0
F reg_LC59IE 1 0
F reg_LC60IE 1 0
F reg_LC61IE 1 0
F reg_LC62IE 1 0
F reg_LC63IE 1 0
S reg_LC14IE ? w_wen : w_wdata[14]
S reg_LC15IE ? w_wen : w_wdata[15]
S reg_LC16IE ? w_wen : w_wdata[16]
S reg_LC17IE ? w_wen : w_wdata[17]
S reg_LC18IE ? w_wen : w_wdata[18]
S reg_LC19IE ? w_wen : w_wdata[19]
S reg_LC20IE ? w_wen : w_wdata[20]
S reg_LC21IE ? w_wen : w_wdata[21]
S reg_LC22IE ? w_wen : w_wdata[22]
S reg_LC23IE ? w_wen : w_wdata[23]
S reg_LC24IE ? w_wen : w_wdata[24]
S reg_LC25IE ? w_wen : w_wdata[25]
S reg_LC26IE ? w_wen : w_wdata[26]
S reg_LC27IE ? w_wen : w_wdata[27]
S reg_LC28IE ? w_wen : w_wdata[28]
S reg_LC29IE ? w_wen : w_wdata[29]
S reg_LC30IE ? w_wen : w_wdata[30]
S reg_LC31IE ? w_wen : w_wdata[31]
S reg_LC32IE ? w_wen : w_wdata[32]
S reg_LC33IE ? w_wen : w_wdata[33]
S reg_LC34IE ? w_wen : w_wdata[34]
S reg_LPRASEIE ? w_wen : w_wdata[35]
S reg_LC36IE ? w_wen : w_wdata[36]
S reg_LC37IE ? w_wen : w_wdata[37]
S reg_LC38IE ? w_wen : w_wdata[38]
S reg_LC39IE ? w_wen : w_wdata[39]
S reg_LC40IE ? w_wen : w_wdata[40]
S reg_LC41IE ? w_wen : w_wdata[41]
S reg_LC42IE ? w_wen : w_wdata[42]
S reg_HPRASEIE ? w_wen : w_wdata[43]
S reg_LC44IE ? w_wen : w_wdata[44]
S reg_LC45IE ? w_wen : w_wdata[45]
S reg_LC46IE ? w_wen : w_wdata[46]
S reg_LC47IE ? w_wen : w_wdata[47]
S reg_LC48IE ? w_wen : w_wdata[48]
S reg_LC49IE ? w_wen : w_wdata[49]
S reg_LC50IE ? w_wen : w_wdata[50]
S reg_LC51IE ? w_wen : w_wdata[51]
S reg_LC52IE ? w_wen : w_wdata[52]
S reg_LC53IE ? w_wen : w_wdata[53]
S reg_LC54IE ? w_wen : w_wdata[54]
S reg_LC55IE ? w_wen : w_wdata[55]
S reg_LC56IE ? w_wen : w_wdata[56]
S reg_LC57IE ? w_wen : w_wdata[57]
S reg_LC58IE ? w_wen : w_wdata[58]
S reg_LC59IE ? w_wen : w_wdata[59]
S reg_LC60IE ? w_wen : w_wdata[60]
S reg_LC61IE ? w_wen : w_wdata[61]
S reg_LC62IE ? w_wen : w_wdata[62]
S reg_LC63IE ? w_wen : w_wdata[63]
A rdata = {reg_LC63IE, reg_LC62IE, reg_LC61IE, reg_LC60IE, reg_LC59IE, reg_LC58IE, reg_LC57IE, reg_LC56IE, reg_LC55IE, reg_LC54IE, reg_LC53IE, reg_LC52IE, reg_LC51IE, reg_LC50IE, reg_LC49IE, reg_LC48IE, reg_LC47IE, reg_LC46IE, reg_LC45IE, reg_LC44IE, reg_HPRASEIE, reg_LC42IE, reg_LC41IE, reg_LC40IE, reg_LC39IE, reg_LC38IE, reg_LC37IE, reg_LC36IE, reg_LPRASEIE, reg_LC34IE, reg_LC33IE, reg_LC32IE, reg_LC31IE, reg_LC30IE, reg_LC29IE, reg_LC28IE, reg_LC27IE, reg_LC26IE, reg_LC25IE, reg_LC24IE, reg_LC23IE, reg_LC22IE, reg_LC21IE, reg_LC20IE, reg_LC19IE, reg_LC18IE, reg_LC17IE, reg_LC16IE, reg_LC15IE, reg_LC14IE, 14'h0}
A regOut_LC14IE = reg_LC14IE
A regOut_LC15IE = reg_LC15IE
A regOut_LC16IE = reg_LC16IE
A regOut_LC17IE = reg_LC17IE
A regOut_LC18IE = reg_LC18IE
A regOut_LC19IE = reg_LC19IE
A regOut_LC20IE = reg_LC20IE
A regOut_LC21IE = reg_LC21IE
A regOut_LC22IE = reg_LC22IE
A regOut_LC23IE = reg_LC23IE
A regOut_LC24IE = reg_LC24IE
A regOut_LC25IE = reg_LC25IE
A regOut_LC26IE = reg_LC26IE
A regOut_LC27IE = reg_LC27IE
A regOut_LC28IE = reg_LC28IE
A regOut_LC29IE = reg_LC29IE
A regOut_LC30IE = reg_LC30IE
A regOut_LC31IE = reg_LC31IE
A regOut_LC32IE = reg_LC32IE
A regOut_LC33IE = reg_LC33IE
A regOut_LC34IE = reg_LC34IE
A regOut_LPRASEIE = reg_LPRASEIE
A regOut_LC36IE = reg_LC36IE
A regOut_LC37IE = reg_LC37IE
A regOut_LC38IE = reg_LC38IE
A regOut_LC39IE = reg_LC39IE
A regOut_LC40IE = reg_LC40IE
A regOut_LC41IE = reg_LC41IE
A regOut_LC42IE = reg_LC42IE
A regOut_HPRASEIE = reg_HPRASEIE
A regOut_LC44IE = reg_LC44IE
A regOut_LC45IE = reg_LC45IE
A regOut_LC46IE = reg_LC46IE
A regOut_LC47IE = reg_LC47IE
A regOut_LC48IE = reg_LC48IE
A regOut_LC49IE = reg_LC49IE
A regOut_LC50IE = reg_LC50IE
A regOut_LC51IE = reg_LC51IE
A regOut_LC52IE = reg_LC52IE
A regOut_LC53IE = reg_LC53IE
A regOut_LC54IE = reg_LC54IE
A regOut_LC55IE = reg_LC55IE
A regOut_LC56IE = reg_LC56IE
A regOut_LC57IE = reg_LC57IE
A regOut_LC58IE = reg_LC58IE
A regOut_LC59IE = reg_LC59IE
A regOut_LC60IE = reg_LC60IE
A regOut_LC61IE = reg_LC61IE
A regOut_LC62IE = reg_LC62IE
A regOut_LC63IE = reg_LC63IE
M HvictlModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_VTI 1
P o regOut_IID 12
P o regOut_DPR 1
P o regOut_IPRIOM 1
P o regOut_IPRIO 8
F reg_VTI 1 0
F reg_IID 12 0
F reg_DPR 1 0
F reg_IPRIOM 1 0
F reg_IPRIO 8 0
S reg_VTI ? w_wen : w_wdata[30]
S reg_IID ? w_wen : w_wdata[27:16]
S reg_DPR ? w_wen : w_wdata[9]
S reg_IPRIOM ? w_wen : w_wdata[8]
S reg_IPRIO ? w_wen : w_wdata[7:0]
A rdata = {33'h0, reg_VTI, 2'h0, reg_IID, 6'h0, reg_DPR, reg_IPRIOM, reg_IPRIO}
A regOut_VTI = reg_VTI
A regOut_IID = reg_IID
A regOut_DPR = reg_DPR
A regOut_IPRIOM = reg_IPRIOM
A regOut_IPRIO = reg_IPRIO
M HenvcfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_STCE 1
P o regOut_PBMTE 1
P o regOut_DTE 1
P o regOut_PMM 2
P o regOut_CBZE 1
P o regOut_CBCFE 1
P o regOut_CBIE 2
P i menvcfg_STCE 1
P i menvcfg_PBMTE 1
P i menvcfg_DTE 1
F reg_STCE 1 1
F reg_PBMTE 1 0
F reg_DTE 1 0
F reg_PMM 2 0
F reg_CBZE 1 1
F reg_CBCFE 1 1
F reg_CBIE 2 3
D _regOut_DTE_output 1
D _regOut_PBMTE_output 1
D _regOut_STCE_output 1
S reg_STCE ? w_wen : w_wdata[63]
S reg_PBMTE ? w_wen : w_wdata[62]
S reg_DTE ? w_wen : w_wdata[59]
S reg_CBZE ? w_wen : w_wdata[7]
S reg_CBCFE ? w_wen : w_wdata[6]
S reg_PMM ? w_wen & (w_wdata[33:32] == 2'h0 | w_wdata[33:32] == 2'h2 | (&(w_wdata[33:32]))) : w_wdata[33:32]
S reg_CBIE ? w_wen & (w_wdata[5:4] == 2'h0 | w_wdata[5:4] == 2'h1 | (&(w_wdata[5:4]))) : w_wdata[5:4]
A _regOut_STCE_output = menvcfg_STCE & reg_STCE
A _regOut_PBMTE_output = menvcfg_PBMTE & reg_PBMTE
A _regOut_DTE_output = menvcfg_DTE & reg_DTE
A rdata = {_regOut_STCE_output, _regOut_PBMTE_output, 2'h0, _regOut_DTE_output, 25'h0, reg_PMM, 24'h0, reg_CBZE, reg_CBCFE, reg_CBIE, 4'h0}
A regOut_STCE = _regOut_STCE_output
A regOut_PBMTE = _regOut_PBMTE_output
A regOut_DTE = _regOut_DTE_output
A regOut_PMM = reg_PMM
A regOut_CBZE = reg_CBZE
A regOut_CBCFE = reg_CBCFE
A regOut_CBIE = reg_CBIE
M HtvalModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i trapToHS_htval_valid 1
P i trapToHS_htval_bits_ALL 64
F reg_ALL 64 0
S reg_ALL ? w_wen | trapToHS_htval_valid : (trapToHS_htval_valid ? trapToHS_htval_bits_ALL : 64'h0) | (w_wen ? w_wdata : 64'h0)
A rdata = reg_ALL
A regOut_ALL = reg_ALL
M HipModule n
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_VSSIP 1
P o regOut_VSTIP 1
P o regOut_VSEIP 1
P o regOut_SGEIP 1
P i mip_VSTIP 1
P i mip_VSEIP 1
P i mip_SGEIP 1
P i hvip_VSSIP 1
P o toHvip_VSSIP_valid 1
P o toHvip_VSSIP_bits 1
A rdata = {51'h0, mip_SGEIP, 1'h0, mip_VSEIP, 3'h0, mip_VSTIP, 3'h0, hvip_VSSIP, 2'h0}
A regOut_VSSIP = hvip_VSSIP
A regOut_VSTIP = mip_VSTIP
A regOut_VSEIP = mip_VSEIP
A regOut_SGEIP = mip_SGEIP
A toHvip_VSSIP_valid = w_wen
A toHvip_VSSIP_bits = w_wdata[2]
M HvipModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_VSSIP 1
P o regOut_VSTIP 1
P o regOut_VSEIP 1
P o regOut_LCOFIP 1
P o regOut_LC14IP 1
P o regOut_LC15IP 1
P o regOut_LC16IP 1
P o regOut_LC17IP 1
P o regOut_LC18IP 1
P o regOut_LC19IP 1
P o regOut_LC20IP 1
P o regOut_LC21IP 1
P o regOut_LC22IP 1
P o regOut_LC23IP 1
P o regOut_LC24IP 1
P o regOut_LC25IP 1
P o regOut_LC26IP 1
P o regOut_LC27IP 1
P o regOut_LC28IP 1
P o regOut_LC29IP 1
P o regOut_LC30IP 1
P o regOut_LC31IP 1
P o regOut_LC32IP 1
P o regOut_LC33IP 1
P o regOut_LC34IP 1
P o regOut_LPRASEIP 1
P o regOut_LC36IP 1
P o regOut_LC37IP 1
P o regOut_LC38IP 1
P o regOut_LC39IP 1
P o regOut_LC40IP 1
P o regOut_LC41IP 1
P o regOut_LC42IP 1
P o regOut_HPRASEIP 1
P o regOut_LC44IP 1
P o regOut_LC45IP 1
P o regOut_LC46IP 1
P o regOut_LC47IP 1
P o regOut_LC48IP 1
P o regOut_LC49IP 1
P o regOut_LC50IP 1
P o regOut_LC51IP 1
P o regOut_LC52IP 1
P o regOut_LC53IP 1
P o regOut_LC54IP 1
P o regOut_LC55IP 1
P o regOut_LC56IP 1
P o regOut_LC57IP 1
P o regOut_LC58IP 1
P o regOut_LC59IP 1
P o regOut_LC60IP 1
P o regOut_LC61IP 1
P o regOut_LC62IP 1
P o regOut_LC63IP 1
P i fromMip_VSSIP_valid 1
P i fromMip_VSSIP_bits 1
P i fromHip_VSSIP_valid 1
P i fromHip_VSSIP_bits 1
P i fromVSip_VSSIP_valid 1
P i fromVSip_VSSIP_bits 1
P i fromVSip_LCOFIP_bits 1
P i fromVSip_LC14IP_valid 1
P i fromVSip_LC14IP_bits 1
P i fromVSip_LC15IP_valid 1
P i fromVSip_LC15IP_bits 1
P i fromVSip_LC16IP_valid 1
P i fromVSip_LC16IP_bits 1
P i fromVSip_LC17IP_valid 1
P i fromVSip_LC17IP_bits 1
P i fromVSip_LC18IP_valid 1
P i fromVSip_LC18IP_bits 1
P i fromVSip_LC19IP_valid 1
P i fromVSip_LC19IP_bits 1
P i fromVSip_LC20IP_valid 1
P i fromVSip_LC20IP_bits 1
P i fromVSip_LC21IP_valid 1
P i fromVSip_LC21IP_bits 1
P i fromVSip_LC22IP_valid 1
P i fromVSip_LC22IP_bits 1
P i fromVSip_LC23IP_valid 1
P i fromVSip_LC23IP_bits 1
P i fromVSip_LC24IP_valid 1
P i fromVSip_LC24IP_bits 1
P i fromVSip_LC25IP_valid 1
P i fromVSip_LC25IP_bits 1
P i fromVSip_LC26IP_valid 1
P i fromVSip_LC26IP_bits 1
P i fromVSip_LC27IP_valid 1
P i fromVSip_LC27IP_bits 1
P i fromVSip_LC28IP_valid 1
P i fromVSip_LC28IP_bits 1
P i fromVSip_LC29IP_valid 1
P i fromVSip_LC29IP_bits 1
P i fromVSip_LC30IP_valid 1
P i fromVSip_LC30IP_bits 1
P i fromVSip_LC31IP_valid 1
P i fromVSip_LC31IP_bits 1
P i fromVSip_LC32IP_valid 1
P i fromVSip_LC32IP_bits 1
P i fromVSip_LC33IP_valid 1
P i fromVSip_LC33IP_bits 1
P i fromVSip_LC34IP_valid 1
P i fromVSip_LC34IP_bits 1
P i fromVSip_LPRASEIP_valid 1
P i fromVSip_LPRASEIP_bits 1
P i fromVSip_LC36IP_valid 1
P i fromVSip_LC36IP_bits 1
P i fromVSip_LC37IP_valid 1
P i fromVSip_LC37IP_bits 1
P i fromVSip_LC38IP_valid 1
P i fromVSip_LC38IP_bits 1
P i fromVSip_LC39IP_valid 1
P i fromVSip_LC39IP_bits 1
P i fromVSip_LC40IP_valid 1
P i fromVSip_LC40IP_bits 1
P i fromVSip_LC41IP_valid 1
P i fromVSip_LC41IP_bits 1
P i fromVSip_LC42IP_valid 1
P i fromVSip_LC42IP_bits 1
P i fromVSip_HPRASEIP_valid 1
P i fromVSip_HPRASEIP_bits 1
P i fromVSip_LC44IP_valid 1
P i fromVSip_LC44IP_bits 1
P i fromVSip_LC45IP_valid 1
P i fromVSip_LC45IP_bits 1
P i fromVSip_LC46IP_valid 1
P i fromVSip_LC46IP_bits 1
P i fromVSip_LC47IP_valid 1
P i fromVSip_LC47IP_bits 1
P i fromVSip_LC48IP_valid 1
P i fromVSip_LC48IP_bits 1
P i fromVSip_LC49IP_valid 1
P i fromVSip_LC49IP_bits 1
P i fromVSip_LC50IP_valid 1
P i fromVSip_LC50IP_bits 1
P i fromVSip_LC51IP_valid 1
P i fromVSip_LC51IP_bits 1
P i fromVSip_LC52IP_valid 1
P i fromVSip_LC52IP_bits 1
P i fromVSip_LC53IP_valid 1
P i fromVSip_LC53IP_bits 1
P i fromVSip_LC54IP_valid 1
P i fromVSip_LC54IP_bits 1
P i fromVSip_LC55IP_valid 1
P i fromVSip_LC55IP_bits 1
P i fromVSip_LC56IP_valid 1
P i fromVSip_LC56IP_bits 1
P i fromVSip_LC57IP_valid 1
P i fromVSip_LC57IP_bits 1
P i fromVSip_LC58IP_valid 1
P i fromVSip_LC58IP_bits 1
P i fromVSip_LC59IP_valid 1
P i fromVSip_LC59IP_bits 1
P i fromVSip_LC60IP_valid 1
P i fromVSip_LC60IP_bits 1
P i fromVSip_LC61IP_valid 1
P i fromVSip_LC61IP_bits 1
P i fromVSip_LC62IP_valid 1
P i fromVSip_LC62IP_bits 1
P i fromVSip_LC63IP_valid 1
P i fromVSip_LC63IP_bits 1
F reg_VSSIP 1 0
F reg_VSTIP 1 0
F reg_VSEIP 1 0
F reg_LC14IP 1 0
F reg_LC15IP 1 0
F reg_LC16IP 1 0
F reg_LC17IP 1 0
F reg_LC18IP 1 0
F reg_LC19IP 1 0
F reg_LC20IP 1 0
F reg_LC21IP 1 0
F reg_LC22IP 1 0
F reg_LC23IP 1 0
F reg_LC24IP 1 0
F reg_LC25IP 1 0
F reg_LC26IP 1 0
F reg_LC27IP 1 0
F reg_LC28IP 1 0
F reg_LC29IP 1 0
F reg_LC30IP 1 0
F reg_LC31IP 1 0
F reg_LC32IP 1 0
F reg_LC33IP 1 0
F reg_LC34IP 1 0
F reg_LPRASEIP 1 0
F reg_LC36IP 1 0
F reg_LC37IP 1 0
F reg_LC38IP 1 0
F reg_LC39IP 1 0
F reg_LC40IP 1 0
F reg_LC41IP 1 0
F reg_LC42IP 1 0
F reg_HPRASEIP 1 0
F reg_LC44IP 1 0
F reg_LC45IP 1 0
F reg_LC46IP 1 0
F reg_LC47IP 1 0
F reg_LC48IP 1 0
F reg_LC49IP 1 0
F reg_LC50IP 1 0
F reg_LC51IP 1 0
F reg_LC52IP 1 0
F reg_LC53IP 1 0
F reg_LC54IP 1 0
F reg_LC55IP 1 0
F reg_LC56IP 1 0
F reg_LC57IP 1 0
F reg_LC58IP 1 0
F reg_LC59IP 1 0
F reg_LC60IP 1 0
F reg_LC61IP 1 0
F reg_LC62IP 1 0
F reg_LC63IP 1 0
S reg_VSSIP ? fromMip_VSSIP_valid | fromHip_VSSIP_valid | fromVSip_VSSIP_valid : fromMip_VSSIP_valid & fromMip_VSSIP_bits | fromHip_VSSIP_valid & fromHip_VSSIP_bits | fromVSip_VSSIP_valid & fromVSip_VSSIP_bits
S reg_VSSIP ? !(fromMip_VSSIP_valid | fromHip_VSSIP_valid | fromVSip_VSSIP_valid) & w_wen : w_wdata[2]
S reg_VSTIP ? w_wen : w_wdata[6]
S reg_VSEIP ? w_wen : w_wdata[10]
S reg_LC14IP ? fromVSip_LC14IP_valid : fromVSip_LC14IP_bits
S reg_LC14IP ? !(fromVSip_LC14IP_valid) & w_wen : w_wdata[14]
S reg_LC15IP ? fromVSip_LC15IP_valid : fromVSip_LC15IP_bits
S reg_LC15IP ? !(fromVSip_LC15IP_valid) & w_wen : w_wdata[15]
S reg_LC16IP ? fromVSip_LC16IP_valid : fromVSip_LC16IP_bits
S reg_LC16IP ? !(fromVSip_LC16IP_valid) & w_wen : w_wdata[16]
S reg_LC17IP ? fromVSip_LC17IP_valid : fromVSip_LC17IP_bits
S reg_LC17IP ? !(fromVSip_LC17IP_valid) & w_wen : w_wdata[17]
S reg_LC18IP ? fromVSip_LC18IP_valid : fromVSip_LC18IP_bits
S reg_LC18IP ? !(fromVSip_LC18IP_valid) & w_wen : w_wdata[18]
S reg_LC19IP ? fromVSip_LC19IP_valid : fromVSip_LC19IP_bits
S reg_LC19IP ? !(fromVSip_LC19IP_valid) & w_wen : w_wdata[19]
S reg_LC20IP ? fromVSip_LC20IP_valid : fromVSip_LC20IP_bits
S reg_LC20IP ? !(fromVSip_LC20IP_valid) & w_wen : w_wdata[20]
S reg_LC21IP ? fromVSip_LC21IP_valid : fromVSip_LC21IP_bits
S reg_LC21IP ? !(fromVSip_LC21IP_valid) & w_wen : w_wdata[21]
S reg_LC22IP ? fromVSip_LC22IP_valid : fromVSip_LC22IP_bits
S reg_LC22IP ? !(fromVSip_LC22IP_valid) & w_wen : w_wdata[22]
S reg_LC23IP ? fromVSip_LC23IP_valid : fromVSip_LC23IP_bits
S reg_LC23IP ? !(fromVSip_LC23IP_valid) & w_wen : w_wdata[23]
S reg_LC24IP ? fromVSip_LC24IP_valid : fromVSip_LC24IP_bits
S reg_LC24IP ? !(fromVSip_LC24IP_valid) & w_wen : w_wdata[24]
S reg_LC25IP ? fromVSip_LC25IP_valid : fromVSip_LC25IP_bits
S reg_LC25IP ? !(fromVSip_LC25IP_valid) & w_wen : w_wdata[25]
S reg_LC26IP ? fromVSip_LC26IP_valid : fromVSip_LC26IP_bits
S reg_LC26IP ? !(fromVSip_LC26IP_valid) & w_wen : w_wdata[26]
S reg_LC27IP ? fromVSip_LC27IP_valid : fromVSip_LC27IP_bits
S reg_LC27IP ? !(fromVSip_LC27IP_valid) & w_wen : w_wdata[27]
S reg_LC28IP ? fromVSip_LC28IP_valid : fromVSip_LC28IP_bits
S reg_LC28IP ? !(fromVSip_LC28IP_valid) & w_wen : w_wdata[28]
S reg_LC29IP ? fromVSip_LC29IP_valid : fromVSip_LC29IP_bits
S reg_LC29IP ? !(fromVSip_LC29IP_valid) & w_wen : w_wdata[29]
S reg_LC30IP ? fromVSip_LC30IP_valid : fromVSip_LC30IP_bits
S reg_LC30IP ? !(fromVSip_LC30IP_valid) & w_wen : w_wdata[30]
S reg_LC31IP ? fromVSip_LC31IP_valid : fromVSip_LC31IP_bits
S reg_LC31IP ? !(fromVSip_LC31IP_valid) & w_wen : w_wdata[31]
S reg_LC32IP ? fromVSip_LC32IP_valid : fromVSip_LC32IP_bits
S reg_LC32IP ? !(fromVSip_LC32IP_valid) & w_wen : w_wdata[32]
S reg_LC33IP ? fromVSip_LC33IP_valid : fromVSip_LC33IP_bits
S reg_LC33IP ? !(fromVSip_LC33IP_valid) & w_wen : w_wdata[33]
S reg_LC34IP ? fromVSip_LC34IP_valid : fromVSip_LC34IP_bits
S reg_LC34IP ? !(fromVSip_LC34IP_valid) & w_wen : w_wdata[34]
S reg_LPRASEIP ? fromVSip_LPRASEIP_valid : fromVSip_LPRASEIP_bits
S reg_LPRASEIP ? !(fromVSip_LPRASEIP_valid) & w_wen : w_wdata[35]
S reg_LC36IP ? fromVSip_LC36IP_valid : fromVSip_LC36IP_bits
S reg_LC36IP ? !(fromVSip_LC36IP_valid) & w_wen : w_wdata[36]
S reg_LC37IP ? fromVSip_LC37IP_valid : fromVSip_LC37IP_bits
S reg_LC37IP ? !(fromVSip_LC37IP_valid) & w_wen : w_wdata[37]
S reg_LC38IP ? fromVSip_LC38IP_valid : fromVSip_LC38IP_bits
S reg_LC38IP ? !(fromVSip_LC38IP_valid) & w_wen : w_wdata[38]
S reg_LC39IP ? fromVSip_LC39IP_valid : fromVSip_LC39IP_bits
S reg_LC39IP ? !(fromVSip_LC39IP_valid) & w_wen : w_wdata[39]
S reg_LC40IP ? fromVSip_LC40IP_valid : fromVSip_LC40IP_bits
S reg_LC40IP ? !(fromVSip_LC40IP_valid) & w_wen : w_wdata[40]
S reg_LC41IP ? fromVSip_LC41IP_valid : fromVSip_LC41IP_bits
S reg_LC41IP ? !(fromVSip_LC41IP_valid) & w_wen : w_wdata[41]
S reg_LC42IP ? fromVSip_LC42IP_valid : fromVSip_LC42IP_bits
S reg_LC42IP ? !(fromVSip_LC42IP_valid) & w_wen : w_wdata[42]
S reg_HPRASEIP ? fromVSip_HPRASEIP_valid : fromVSip_HPRASEIP_bits
S reg_HPRASEIP ? !(fromVSip_HPRASEIP_valid) & w_wen : w_wdata[43]
S reg_LC44IP ? fromVSip_LC44IP_valid : fromVSip_LC44IP_bits
S reg_LC44IP ? !(fromVSip_LC44IP_valid) & w_wen : w_wdata[44]
S reg_LC45IP ? fromVSip_LC45IP_valid : fromVSip_LC45IP_bits
S reg_LC45IP ? !(fromVSip_LC45IP_valid) & w_wen : w_wdata[45]
S reg_LC46IP ? fromVSip_LC46IP_valid : fromVSip_LC46IP_bits
S reg_LC46IP ? !(fromVSip_LC46IP_valid) & w_wen : w_wdata[46]
S reg_LC47IP ? fromVSip_LC47IP_valid : fromVSip_LC47IP_bits
S reg_LC47IP ? !(fromVSip_LC47IP_valid) & w_wen : w_wdata[47]
S reg_LC48IP ? fromVSip_LC48IP_valid : fromVSip_LC48IP_bits
S reg_LC48IP ? !(fromVSip_LC48IP_valid) & w_wen : w_wdata[48]
S reg_LC49IP ? fromVSip_LC49IP_valid : fromVSip_LC49IP_bits
S reg_LC49IP ? !(fromVSip_LC49IP_valid) & w_wen : w_wdata[49]
S reg_LC50IP ? fromVSip_LC50IP_valid : fromVSip_LC50IP_bits
S reg_LC50IP ? !(fromVSip_LC50IP_valid) & w_wen : w_wdata[50]
S reg_LC51IP ? fromVSip_LC51IP_valid : fromVSip_LC51IP_bits
S reg_LC51IP ? !(fromVSip_LC51IP_valid) & w_wen : w_wdata[51]
S reg_LC52IP ? fromVSip_LC52IP_valid : fromVSip_LC52IP_bits
S reg_LC52IP ? !(fromVSip_LC52IP_valid) & w_wen : w_wdata[52]
S reg_LC53IP ? fromVSip_LC53IP_valid : fromVSip_LC53IP_bits
S reg_LC53IP ? !(fromVSip_LC53IP_valid) & w_wen : w_wdata[53]
S reg_LC54IP ? fromVSip_LC54IP_valid : fromVSip_LC54IP_bits
S reg_LC54IP ? !(fromVSip_LC54IP_valid) & w_wen : w_wdata[54]
S reg_LC55IP ? fromVSip_LC55IP_valid : fromVSip_LC55IP_bits
S reg_LC55IP ? !(fromVSip_LC55IP_valid) & w_wen : w_wdata[55]
S reg_LC56IP ? fromVSip_LC56IP_valid : fromVSip_LC56IP_bits
S reg_LC56IP ? !(fromVSip_LC56IP_valid) & w_wen : w_wdata[56]
S reg_LC57IP ? fromVSip_LC57IP_valid : fromVSip_LC57IP_bits
S reg_LC57IP ? !(fromVSip_LC57IP_valid) & w_wen : w_wdata[57]
S reg_LC58IP ? fromVSip_LC58IP_valid : fromVSip_LC58IP_bits
S reg_LC58IP ? !(fromVSip_LC58IP_valid) & w_wen : w_wdata[58]
S reg_LC59IP ? fromVSip_LC59IP_valid : fromVSip_LC59IP_bits
S reg_LC59IP ? !(fromVSip_LC59IP_valid) & w_wen : w_wdata[59]
S reg_LC60IP ? fromVSip_LC60IP_valid : fromVSip_LC60IP_bits
S reg_LC60IP ? !(fromVSip_LC60IP_valid) & w_wen : w_wdata[60]
S reg_LC61IP ? fromVSip_LC61IP_valid : fromVSip_LC61IP_bits
S reg_LC61IP ? !(fromVSip_LC61IP_valid) & w_wen : w_wdata[61]
S reg_LC62IP ? fromVSip_LC62IP_valid : fromVSip_LC62IP_bits
S reg_LC62IP ? !(fromVSip_LC62IP_valid) & w_wen : w_wdata[62]
S reg_LC63IP ? fromVSip_LC63IP_valid : fromVSip_LC63IP_bits
S reg_LC63IP ? !(fromVSip_LC63IP_valid) & w_wen : w_wdata[63]
A rdata = {reg_LC63IP, reg_LC62IP, reg_LC61IP, reg_LC60IP, reg_LC59IP, reg_LC58IP, reg_LC57IP, reg_LC56IP, reg_LC55IP, reg_LC54IP, reg_LC53IP, reg_LC52IP, reg_LC51IP, reg_LC50IP, reg_LC49IP, reg_LC48IP, reg_LC47IP, reg_LC46IP, reg_LC45IP, reg_LC44IP, reg_HPRASEIP, reg_LC42IP, reg_LC41IP, reg_LC40IP, reg_LC39IP, reg_LC38IP, reg_LC37IP, reg_LC36IP, reg_LPRASEIP, reg_LC34IP, reg_LC33IP, reg_LC32IP, reg_LC31IP, reg_LC30IP, reg_LC29IP, reg_LC28IP, reg_LC27IP, reg_LC26IP, reg_LC25IP, reg_LC24IP, reg_LC23IP, reg_LC22IP, reg_LC21IP, reg_LC20IP, reg_LC19IP, reg_LC18IP, reg_LC17IP, reg_LC16IP, reg_LC15IP, reg_LC14IP, 3'h0, reg_VSEIP, 3'h0, reg_VSTIP, 3'h0, reg_VSSIP, 2'h0}
A regOut_VSSIP = reg_VSSIP
A regOut_VSTIP = reg_VSTIP
A regOut_VSEIP = reg_VSEIP
A regOut_LCOFIP = 1'h0
A regOut_LC14IP = reg_LC14IP
A regOut_LC15IP = reg_LC15IP
A regOut_LC16IP = reg_LC16IP
A regOut_LC17IP = reg_LC17IP
A regOut_LC18IP = reg_LC18IP
A regOut_LC19IP = reg_LC19IP
A regOut_LC20IP = reg_LC20IP
A regOut_LC21IP = reg_LC21IP
A regOut_LC22IP = reg_LC22IP
A regOut_LC23IP = reg_LC23IP
A regOut_LC24IP = reg_LC24IP
A regOut_LC25IP = reg_LC25IP
A regOut_LC26IP = reg_LC26IP
A regOut_LC27IP = reg_LC27IP
A regOut_LC28IP = reg_LC28IP
A regOut_LC29IP = reg_LC29IP
A regOut_LC30IP = reg_LC30IP
A regOut_LC31IP = reg_LC31IP
A regOut_LC32IP = reg_LC32IP
A regOut_LC33IP = reg_LC33IP
A regOut_LC34IP = reg_LC34IP
A regOut_LPRASEIP = reg_LPRASEIP
A regOut_LC36IP = reg_LC36IP
A regOut_LC37IP = reg_LC37IP
A regOut_LC38IP = reg_LC38IP
A regOut_LC39IP = reg_LC39IP
A regOut_LC40IP = reg_LC40IP
A regOut_LC41IP = reg_LC41IP
A regOut_LC42IP = reg_LC42IP
A regOut_HPRASEIP = reg_HPRASEIP
A regOut_LC44IP = reg_LC44IP
A regOut_LC45IP = reg_LC45IP
A regOut_LC46IP = reg_LC46IP
A regOut_LC47IP = reg_LC47IP
A regOut_LC48IP = reg_LC48IP
A regOut_LC49IP = reg_LC49IP
A regOut_LC50IP = reg_LC50IP
A regOut_LC51IP = reg_LC51IP
A regOut_LC52IP = reg_LC52IP
A regOut_LC53IP = reg_LC53IP
A regOut_LC54IP = reg_LC54IP
A regOut_LC55IP = reg_LC55IP
A regOut_LC56IP = reg_LC56IP
A regOut_LC57IP = reg_LC57IP
A regOut_LC58IP = reg_LC58IP
A regOut_LC59IP = reg_LC59IP
A regOut_LC60IP = reg_LC60IP
A regOut_LC61IP = reg_LC61IP
A regOut_LC62IP = reg_LC62IP
A regOut_LC63IP = reg_LC63IP
M Hviprio1Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_PrioSSI 8
P o regOut_PrioSTI 8
P o regOut_PrioCOI 8
P o regOut_Prio14 8
P o regOut_Prio15 8
F reg_PrioSSI 8 0
F reg_PrioSTI 8 0
F reg_PrioCOI 8 0
F reg_Prio14 8 0
F reg_Prio15 8 0
S reg_PrioSSI ? w_wen : w_wdata[15:8]
S reg_PrioSTI ? w_wen : w_wdata[31:24]
S reg_PrioCOI ? w_wen : w_wdata[47:40]
S reg_Prio14 ? w_wen : w_wdata[55:48]
S reg_Prio15 ? w_wen : w_wdata[63:56]
A rdata = {reg_Prio15, reg_Prio14, reg_PrioCOI, 8'h0, reg_PrioSTI, 8'h0, reg_PrioSSI, 8'h0}
A regOut_PrioSSI = reg_PrioSSI
A regOut_PrioSTI = reg_PrioSTI
A regOut_PrioCOI = reg_PrioCOI
A regOut_Prio14 = reg_Prio14
A regOut_Prio15 = reg_Prio15
M Hviprio2Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
F reg_ALL 64 0
S reg_ALL ? w_wen : w_wdata
A rdata = reg_ALL
A regOut_ALL = reg_ALL
M HtinstModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i trapToHS_htinst_valid 1
P i trapToHS_htinst_bits_ALL 64
F reg_ALL 64 0
S reg_ALL ? w_wen | trapToHS_htinst_valid : (trapToHS_htinst_valid ? trapToHS_htinst_bits_ALL : 64'h0) | (w_wen ? w_wdata : 64'h0)
A rdata = reg_ALL
A regOut_ALL = reg_ALL
M HgatpModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_MODE 4
P o regOut_VMID 14
P o regOut_PPN 44
F reg_MODE 4 0
F reg_VMID 14 0
F reg_PPN 44 0
S reg_MODE ? w_wen & (w_wdata[63:60] == 4'h0 | w_wdata[63:60] == 4'h8 | w_wdata[63:60] == 4'h9) : w_wdata[63:60]
S reg_VMID ? w_wen : w_wdata[57:44]
S reg_PPN ? w_wen : {8'h0, w_wdata[35:2], 2'h0}
A rdata = {reg_MODE, 2'h0, reg_VMID, reg_PPN}
A regOut_MODE = reg_MODE
A regOut_VMID = reg_VMID
A regOut_PPN = reg_PPN
M HgeipModule n
P o rdata 64
P o regOut_ip 7
P i aiaToCSR_vseip 7
A rdata = {56'h0, aiaToCSR_vseip, 1'h0}
A regOut_ip = aiaToCSR_vseip
M Hstateen0Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_JVT 1
P o regOut_FCSR 1
P o regOut_C 1
P o regOut_SE0 1
P o regOut_ENVCFG 1
P o regOut_CSRIND 1
P o regOut_AIA 1
P o regOut_IMSIC 1
P o regOut_CONTEXT 1
P i fromMstateen0_SE0 1
P i fromMstateen0_ENVCFG 1
P i fromMstateen0_CSRIND 1
P i fromMstateen0_AIA 1
P i fromMstateen0_IMSIC 1
P i fromMstateen0_CONTEXT 1
P i fromMstateen0_C 1
F reg_C 1 0
F reg_SE0 1 0
F reg_ENVCFG 1 0
F reg_CSRIND 1 0
F reg_AIA 1 0
F reg_IMSIC 1 0
F reg_CONTEXT 1 0
D _regOut_C_T 1
D _regOut_SE0_T 1
D _regOut_ENVCFG_T 1
D _regOut_CSRIND_T 1
D _regOut_AIA_T 1
D _regOut_IMSIC_T 1
D _regOut_CONTEXT_T 1
S reg_C ? w_wen : w_wdata[0]
S reg_SE0 ? w_wen : w_wdata[63]
S reg_ENVCFG ? w_wen : w_wdata[62]
S reg_CSRIND ? w_wen : w_wdata[60]
S reg_AIA ? w_wen : w_wdata[59]
S reg_IMSIC ? w_wen : w_wdata[58]
S reg_CONTEXT ? w_wen : w_wdata[57]
A _regOut_CONTEXT_T = reg_CONTEXT & fromMstateen0_CONTEXT
A _regOut_IMSIC_T = reg_IMSIC & fromMstateen0_IMSIC
A _regOut_AIA_T = reg_AIA & fromMstateen0_AIA
A _regOut_CSRIND_T = reg_CSRIND & fromMstateen0_CSRIND
A _regOut_ENVCFG_T = reg_ENVCFG & fromMstateen0_ENVCFG
A _regOut_SE0_T = reg_SE0 & fromMstateen0_SE0
A _regOut_C_T = reg_C & fromMstateen0_C
A rdata = {_regOut_SE0_T, _regOut_ENVCFG_T, 1'h0, _regOut_CSRIND_T, _regOut_AIA_T, _regOut_IMSIC_T, _regOut_CONTEXT_T, 56'h0, _regOut_C_T}
A regOut_JVT = 1'h0
A regOut_FCSR = 1'h0
A regOut_C = _regOut_C_T
A regOut_SE0 = _regOut_SE0_T
A regOut_ENVCFG = _regOut_ENVCFG_T
A regOut_CSRIND = _regOut_CSRIND_T
A regOut_AIA = _regOut_AIA_T
A regOut_IMSIC = _regOut_IMSIC_T
A regOut_CONTEXT = _regOut_CONTEXT_T
M Hstateen1Module n
P i clock 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_SE 1
P i fromMstateen1_SE 1
F reg_SE 1 -
D _regOut_SE_T 1
S reg_SE ? w_wen : w_wdata[63]
A _regOut_SE_T = reg_SE & fromMstateen1_SE
A rdata = {_regOut_SE_T, 63'h0}
A regOut_SE = _regOut_SE_T
M Hstateen2Module n
P i clock 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_SE 1
P i fromMstateen2_SE 1
F reg_SE 1 -
D _regOut_SE_T 1
S reg_SE ? w_wen : w_wdata[63]
A _regOut_SE_T = reg_SE & fromMstateen2_SE
A rdata = {_regOut_SE_T, 63'h0}
A regOut_SE = _regOut_SE_T
M Hstateen3Module n
P i clock 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_SE 1
P i fromMstateen3_SE 1
F reg_SE 1 -
D _regOut_SE_T 1
S reg_SE ? w_wen : w_wdata[63]
A _regOut_SE_T = reg_SE & fromMstateen3_SE
A rdata = {_regOut_SE_T, 63'h0}
A regOut_SE = _regOut_SE_T
M HcontextModule n
P i w_wen 1
P i w_wdata 64
P o rdata 14
P o regOut_HCONTEXT 14
P i fromMcontext_HCONTEXT 14
P o toMcontext_valid 1
P o toMcontext_bits_HCONTEXT 14
A rdata = fromMcontext_HCONTEXT
A regOut_HCONTEXT = fromMcontext_HCONTEXT
A toMcontext_valid = w_wen
A toMcontext_bits_HCONTEXT = w_wdata[13:0]
M VSstatusModule n
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_SIE 1
P o regOut_SPIE 1
P o regOut_SPP 1
P o regOut_VS 2
P o regOut_FS 2
P o regOut_SUM 1
P o regOut_MXR 1
P o regOut_SDT 1
P i retFromS_vsstatus_valid 1
P i retFromS_vsstatus_bits_SIE 1
P i retFromS_vsstatus_bits_SPIE 1
P i retFromS_vsstatus_bits_SPP 1
P i retFromSSDT_vsstatus_valid 1
P i retFromM_vsstatus_valid 1
P i retFromM_vsstatus_bits_SDT 1
P i retFromMN_vsstatus_valid 1
P i retFromMN_vsstatus_bits_SDT 1
P i retFromD_vsstatus_valid 1
P i retFromD_vsstatus_bits_SDT 1
P i trapToVS_vsstatus_valid 1
P i trapToVS_vsstatus_bits_SIE 1
P i trapToVS_vsstatus_bits_SPIE 1
P i trapToVS_vsstatus_bits_SPP 1
P i trapToVS_vsstatus_bits_SDT 1
P i robCommit_fsDirty 1
P i robCommit_vsDirty 1
P i robCommit_vstart_valid 1
P i robCommit_vstart_bits 7
P i writeFCSR 1
P i writeVCSR 1
P i isVirtMode 1
P i menvcfg_DTE 1
P i henvcfg_DTE 1
F reg_SIE 1 -
F reg_SPIE 1 -
F reg_SPP 1 -
F reg_VS 2 -
F reg_FS 2 -
F reg_SUM 1 -
F reg_MXR 1 -
F reg_SDT 1 -
D _regOut_SDT_output 1
W _GEN 1 = (robCommit_fsDirty | writeFCSR) & isVirtMode
W _GEN_0 1 = (robCommit_vsDirty | writeVCSR | robCommit_vstart_valid & (|robCommit_vstart_bits)) & isVirtMode
V _GEN_1 1 = w_wen | retFromS_vsstatus_valid | trapToVS_vsstatus_valid
A _regOut_SDT_output = menvcfg_DTE & henvcfg_DTE & reg_SDT
A rdata = {(&reg_FS) | (&reg_VS), 38'h100, _regOut_SDT_output, 4'h0, reg_MXR, reg_SUM, 3'h0, reg_FS, 2'h0, reg_VS, reg_SPP, 2'h0, reg_SPIE, 3'h0, reg_SIE, 1'h0}
A regOut_SIE = reg_SIE
A regOut_SPIE = reg_SPIE
A regOut_SPP = reg_SPP
A regOut_VS = reg_VS
A regOut_FS = reg_FS
A regOut_SUM = reg_SUM
A regOut_MXR = reg_MXR
A regOut_SDT = _regOut_SDT_output
M VSieModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_SSIE 1
P o regOut_STIE 1
P o regOut_SEIE 1
P o regOut_LCOFIE 1
P o regOut_LC14IE 1
P o regOut_LC15IE 1
P o regOut_LC16IE 1
P o regOut_LC17IE 1
P o regOut_LC18IE 1
P o regOut_LC19IE 1
P o regOut_LC20IE 1
P o regOut_LC21IE 1
P o regOut_LC22IE 1
P o regOut_LC23IE 1
P o regOut_LC24IE 1
P o regOut_LC25IE 1
P o regOut_LC26IE 1
P o regOut_LC27IE 1
P o regOut_LC28IE 1
P o regOut_LC29IE 1
P o regOut_LC30IE 1
P o regOut_LC31IE 1
P o regOut_LC32IE 1
P o regOut_LC33IE 1
P o regOut_LC34IE 1
P o regOut_LPRASEIE 1
P o regOut_LC36IE 1
P o regOut_LC37IE 1
P o regOut_LC38IE 1
P o regOut_LC39IE 1
P o regOut_LC40IE 1
P o regOut_LC41IE 1
P o regOut_LC42IE 1
P o regOut_HPRASEIE 1
P o regOut_LC44IE 1
P o regOut_LC45IE 1
P o regOut_LC46IE 1
P o regOut_LC47IE 1
P o regOut_LC48IE 1
P o regOut_LC49IE 1
P o regOut_LC50IE 1
P o regOut_LC51IE 1
P o regOut_LC52IE 1
P o regOut_LC53IE 1
P o regOut_LC54IE 1
P o regOut_LC55IE 1
P o regOut_LC56IE 1
P o regOut_LC57IE 1
P o regOut_LC58IE 1
P o regOut_LC59IE 1
P o regOut_LC60IE 1
P o regOut_LC61IE 1
P o regOut_LC62IE 1
P o regOut_LC63IE 1
P i mideleg_SSI 1
P i mideleg_STI 1
P i mideleg_SEI 1
P i mideleg_LCOFI 1
P i mie_SSIE 1
P i mie_VSSIE 1
P i mie_MSIE 1
P i mie_STIE 1
P i mie_VSTIE 1
P i mie_MTIE 1
P i mie_SEIE 1
P i mie_VSEIE 1
P i mie_MEIE 1
P i mie_SGEIE 1
P i mie_LCOFIE 1
P i mvien_SSIE 1
P i mvien_SEIE 1
P i mvien_LC14IE 1
P i mvien_LC15IE 1
P i mvien_LC16IE 1
P i mvien_LC17IE 1
P i mvien_LC18IE 1
P i mvien_LC19IE 1
P i mvien_LC20IE 1
P i mvien_LC21IE 1
P i mvien_LC22IE 1
P i mvien_LC23IE 1
P i mvien_LC24IE 1
P i mvien_LC25IE 1
P i mvien_LC26IE 1
P i mvien_LC27IE 1
P i mvien_LC28IE 1
P i mvien_LC29IE 1
P i mvien_LC30IE 1
P i mvien_LC31IE 1
P i mvien_LC32IE 1
P i mvien_LC33IE 1
P i mvien_LC34IE 1
P i mvien_LPRASEIE 1
P i mvien_LC36IE 1
P i mvien_LC37IE 1
P i mvien_LC38IE 1
P i mvien_LC39IE 1
P i mvien_LC40IE 1
P i mvien_LC41IE 1
P i mvien_LC42IE 1
P i mvien_HPRASEIE 1
P i mvien_LC44IE 1
P i mvien_LC45IE 1
P i mvien_LC46IE 1
P i mvien_LC47IE 1
P i mvien_LC48IE 1
P i mvien_LC49IE 1
P i mvien_LC50IE 1
P i mvien_LC51IE 1
P i mvien_LC52IE 1
P i mvien_LC53IE 1
P i mvien_LC54IE 1
P i mvien_LC55IE 1
P i mvien_LC56IE 1
P i mvien_LC57IE 1
P i mvien_LC58IE 1
P i mvien_LC59IE 1
P i mvien_LC60IE 1
P i mvien_LC61IE 1
P i mvien_LC62IE 1
P i mvien_LC63IE 1
P i hideleg_SSI 1
P i hideleg_VSSI 1
P i hideleg_MSI 1
P i hideleg_STI 1
P i hideleg_VSTI 1
P i hideleg_MTI 1
P i hideleg_SEI 1
P i hideleg_VSEI 1
P i hideleg_MEI 1
P i hideleg_SGEI 1
P i hideleg_LCOFI 1
P i hvien_LC14IE 1
P i hvien_LC15IE 1
P i hvien_LC16IE 1
P i hvien_LC17IE 1
P i hvien_LC18IE 1
P i hvien_LC19IE 1
P i hvien_LC20IE 1
P i hvien_LC21IE 1
P i hvien_LC22IE 1
P i hvien_LC23IE 1
P i hvien_LC24IE 1
P i hvien_LC25IE 1
P i hvien_LC26IE 1
P i hvien_LC27IE 1
P i hvien_LC28IE 1
P i hvien_LC29IE 1
P i hvien_LC30IE 1
P i hvien_LC31IE 1
P i hvien_LC32IE 1
P i hvien_LC33IE 1
P i hvien_LC34IE 1
P i hvien_LPRASEIE 1
P i hvien_LC36IE 1
P i hvien_LC37IE 1
P i hvien_LC38IE 1
P i hvien_LC39IE 1
P i hvien_LC40IE 1
P i hvien_LC41IE 1
P i hvien_LC42IE 1
P i hvien_HPRASEIE 1
P i hvien_LC44IE 1
P i hvien_LC45IE 1
P i hvien_LC46IE 1
P i hvien_LC47IE 1
P i hvien_LC48IE 1
P i hvien_LC49IE 1
P i hvien_LC50IE 1
P i hvien_LC51IE 1
P i hvien_LC52IE 1
P i hvien_LC53IE 1
P i hvien_LC54IE 1
P i hvien_LC55IE 1
P i hvien_LC56IE 1
P i hvien_LC57IE 1
P i hvien_LC58IE 1
P i hvien_LC59IE 1
P i hvien_LC60IE 1
P i hvien_LC61IE 1
P i hvien_LC62IE 1
P i hvien_LC63IE 1
P i sie_SSIE 1
P i sie_STIE 1
P i sie_SEIE 1
P i sie_LCOFIE 1
P i sie_LC14IE 1
P i sie_LC15IE 1
P i sie_LC16IE 1
P i sie_LC17IE 1
P i sie_LC18IE 1
P i sie_LC19IE 1
P i sie_LC20IE 1
P i sie_LC21IE 1
P i sie_LC22IE 1
P i sie_LC23IE 1
P i sie_LC24IE 1
P i sie_LC25IE 1
P i sie_LC26IE 1
P i sie_LC27IE 1
P i sie_LC28IE 1
P i sie_LC29IE 1
P i sie_LC30IE 1
P i sie_LC31IE 1
P i sie_LC32IE 1
P i sie_LC33IE 1
P i sie_LC34IE 1
P i sie_LPRASEIE 1
P i sie_LC36IE 1
P i sie_LC37IE 1
P i sie_LC38IE 1
P i sie_LC39IE 1
P i sie_LC40IE 1
P i sie_LC41IE 1
P i sie_LC42IE 1
P i sie_HPRASEIE 1
P i sie_LC44IE 1
P i sie_LC45IE 1
P i sie_LC46IE 1
P i sie_LC47IE 1
P i sie_LC48IE 1
P i sie_LC49IE 1
P i sie_LC50IE 1
P i sie_LC51IE 1
P i sie_LC52IE 1
P i sie_LC53IE 1
P i sie_LC54IE 1
P i sie_LC55IE 1
P i sie_LC56IE 1
P i sie_LC57IE 1
P i sie_LC58IE 1
P i sie_LC59IE 1
P i sie_LC60IE 1
P i sie_LC61IE 1
P i sie_LC62IE 1
P i sie_LC63IE 1
P o toMie_VSSIE_valid 1
P o toMie_VSSIE_bits 1
P o toMie_VSTIE_valid 1
P o toMie_VSTIE_bits 1
P o toMie_VSEIE_valid 1
P o toMie_VSEIE_bits 1
P o toMie_LCOFIE_valid 1
P o toMie_LCOFIE_bits 1
P o toSie_VSSIE_valid 1
P o toSie_VSSIE_bits 1
P o toSie_VSTIE_valid 1
P o toSie_VSTIE_bits 1
P o toSie_VSEIE_valid 1
P o toSie_VSEIE_bits 1
P o toSie_LCOFIE_valid 1
P o toSie_LCOFIE_bits 1
P o toSie_LC14IE_valid 1
P o toSie_LC14IE_bits 1
P o toSie_LC15IE_valid 1
P o toSie_LC15IE_bits 1
P o toSie_LC16IE_valid 1
P o toSie_LC16IE_bits 1
P o toSie_LC17IE_valid 1
P o toSie_LC17IE_bits 1
P o toSie_LC18IE_valid 1
P o toSie_LC18IE_bits 1
P o toSie_LC19IE_valid 1
P o toSie_LC19IE_bits 1
P o toSie_LC20IE_valid 1
P o toSie_LC20IE_bits 1
P o toSie_LC21IE_valid 1
P o toSie_LC21IE_bits 1
P o toSie_LC22IE_valid 1
P o toSie_LC22IE_bits 1
P o toSie_LC23IE_valid 1
P o toSie_LC23IE_bits 1
P o toSie_LC24IE_valid 1
P o toSie_LC24IE_bits 1
P o toSie_LC25IE_valid 1
P o toSie_LC25IE_bits 1
P o toSie_LC26IE_valid 1
P o toSie_LC26IE_bits 1
P o toSie_LC27IE_valid 1
P o toSie_LC27IE_bits 1
P o toSie_LC28IE_valid 1
P o toSie_LC28IE_bits 1
P o toSie_LC29IE_valid 1
P o toSie_LC29IE_bits 1
P o toSie_LC30IE_valid 1
P o toSie_LC30IE_bits 1
P o toSie_LC31IE_valid 1
P o toSie_LC31IE_bits 1
P o toSie_LC32IE_valid 1
P o toSie_LC32IE_bits 1
P o toSie_LC33IE_valid 1
P o toSie_LC33IE_bits 1
P o toSie_LC34IE_valid 1
P o toSie_LC34IE_bits 1
P o toSie_LPRASEIE_valid 1
P o toSie_LPRASEIE_bits 1
P o toSie_LC36IE_valid 1
P o toSie_LC36IE_bits 1
P o toSie_LC37IE_valid 1
P o toSie_LC37IE_bits 1
P o toSie_LC38IE_valid 1
P o toSie_LC38IE_bits 1
P o toSie_LC39IE_valid 1
P o toSie_LC39IE_bits 1
P o toSie_LC40IE_valid 1
P o toSie_LC40IE_bits 1
P o toSie_LC41IE_valid 1
P o toSie_LC41IE_bits 1
P o toSie_LC42IE_valid 1
P o toSie_LC42IE_bits 1
P o toSie_HPRASEIE_valid 1
P o toSie_HPRASEIE_bits 1
P o toSie_LC44IE_valid 1
P o toSie_LC44IE_bits 1
P o toSie_LC45IE_valid 1
P o toSie_LC45IE_bits 1
P o toSie_LC46IE_valid 1
P o toSie_LC46IE_bits 1
P o toSie_LC47IE_valid 1
P o toSie_LC47IE_bits 1
P o toSie_LC48IE_valid 1
P o toSie_LC48IE_bits 1
P o toSie_LC49IE_valid 1
P o toSie_LC49IE_bits 1
P o toSie_LC50IE_valid 1
P o toSie_LC50IE_bits 1
P o toSie_LC51IE_valid 1
P o toSie_LC51IE_bits 1
P o toSie_LC52IE_valid 1
P o toSie_LC52IE_bits 1
P o toSie_LC53IE_valid 1
P o toSie_LC53IE_bits 1
P o toSie_LC54IE_valid 1
P o toSie_LC54IE_bits 1
P o toSie_LC55IE_valid 1
P o toSie_LC55IE_bits 1
P o toSie_LC56IE_valid 1
P o toSie_LC56IE_bits 1
P o toSie_LC57IE_valid 1
P o toSie_LC57IE_bits 1
P o toSie_LC58IE_valid 1
P o toSie_LC58IE_bits 1
P o toSie_LC59IE_valid 1
P o toSie_LC59IE_bits 1
P o toSie_LC60IE_valid 1
P o toSie_LC60IE_bits 1
P o toSie_LC61IE_valid 1
P o toSie_LC61IE_bits 1
P o toSie_LC62IE_valid 1
P o toSie_LC62IE_bits 1
P o toSie_LC63IE_valid 1
P o toSie_LC63IE_bits 1
F reg_LC14IE 1 0
F reg_LC15IE 1 0
F reg_LC16IE 1 0
F reg_LC17IE 1 0
F reg_LC18IE 1 0
F reg_LC19IE 1 0
F reg_LC20IE 1 0
F reg_LC21IE 1 0
F reg_LC22IE 1 0
F reg_LC23IE 1 0
F reg_LC24IE 1 0
F reg_LC25IE 1 0
F reg_LC26IE 1 0
F reg_LC27IE 1 0
F reg_LC28IE 1 0
F reg_LC29IE 1 0
F reg_LC30IE 1 0
F reg_LC31IE 1 0
F reg_LC32IE 1 0
F reg_LC33IE 1 0
F reg_LC34IE 1 0
F reg_LPRASEIE 1 0
F reg_LC36IE 1 0
F reg_LC37IE 1 0
F reg_LC38IE 1 0
F reg_LC39IE 1 0
F reg_LC40IE 1 0
F reg_LC41IE 1 0
F reg_LC42IE 1 0
F reg_HPRASEIE 1 0
F reg_LC44IE 1 0
F reg_LC45IE 1 0
F reg_LC46IE 1 0
F reg_LC47IE 1 0
F reg_LC48IE 1 0
F reg_LC49IE 1 0
F reg_LC50IE 1 0
F reg_LC51IE 1 0
F reg_LC52IE 1 0
F reg_LC53IE 1 0
F reg_LC54IE 1 0
F reg_LC55IE 1 0
F reg_LC56IE 1 0
F reg_LC57IE 1 0
F reg_LC58IE 1 0
F reg_LC59IE 1 0
F reg_LC60IE 1 0
F reg_LC61IE 1 0
F reg_LC62IE 1 0
F reg_LC63IE 1 0
D _regOut_SSIE_T 1
D _regOut_STIE_T 1
D _regOut_SEIE_T 1
D _GEN 63
W _GEN_0 62 = {50'h0, hideleg_LCOFI, hideleg_SGEI, hideleg_MEI, hideleg_VSEI, hideleg_SEI, 1'h0, hideleg_MTI, hideleg_VSTI, hideleg_STI, 1'h0, hideleg_MSI, hideleg_VSSI}
W originAliasIE 62 = _GEN_0 & {50'h0, mideleg_LCOFI, 3'h5, mideleg_SEI, 3'h1, mideleg_STI, 3'h1} & {50'h0, mie_LCOFIE, mie_SGEIE, mie_MEIE, mie_VSEIE, mie_SEIE, 1'h0, mie_MTIE, mie_VSTIE, mie_STIE, 1'h0, mie_MSIE, mie_VSSIE} | _GEN_0 & {50'h3FFFFFFFFFFFF, ~mideleg_LCOFI, 3'h2, ~mideleg_SEI, 3'h6, ~mideleg_STI, 3'h6} & {mvien_LC63IE, mvien_LC62IE, mvien_LC61IE, mvien_LC60IE, mvien_LC59IE, mvien_LC58IE, mvien_LC57IE, mvien_LC56IE, mvien_LC55IE, mvien_LC54IE, mvien_LC53IE, mvien_LC52IE, mvien_LC51IE, mvien_LC50IE, mvien_LC49IE, mvien_LC48IE, mvien_LC47IE, mvien_LC46IE, mvien_LC45IE, mvien_LC44IE, mvien_HPRASEIE, mvien_LC42IE, mvien_LC41IE, mvien_LC40IE, mvien_LC39IE, mvien_LC38IE, mvien_LC37IE, mvien_LC36IE, mvien_LPRASEIE, mvien_LC34IE, mvien_LC33IE, mvien_LC32IE, mvien_LC31IE, mvien_LC30IE, mvien_LC29IE, mvien_LC28IE, mvien_LC27IE, mvien_LC26IE, mvien_LC25IE, mvien_LC24IE, mvien_LC23IE, mvien_LC22IE, mvien_LC21IE, mvien_LC20IE, mvien_LC19IE, mvien_LC18IE, mvien_LC17IE, mvien_LC16IE, mvien_LC15IE, mvien_LC14IE, 4'h0, mvien_SEIE, 7'h0} & {sie_LC63IE, sie_LC62IE, sie_LC61IE, sie_LC60IE, sie_LC59IE, sie_LC58IE, sie_LC57IE, sie_LC56IE, sie_LC55IE, sie_LC54IE, sie_LC53IE, sie_LC52IE, sie_LC51IE, sie_LC50IE, sie_LC49IE, sie_LC48IE, sie_LC47IE, sie_LC46IE, sie_LC45IE, sie_LC44IE, sie_HPRASEIE, sie_LC42IE, sie_LC41IE, sie_LC40IE, sie_LC39IE, sie_LC38IE, sie_LC37IE, sie_LC36IE, sie_LPRASEIE, sie_LC34IE, sie_LC33IE, sie_LC32IE, sie_LC31IE, sie_LC30IE, sie_LC29IE, sie_LC28IE, sie_LC27IE, sie_LC26IE, sie_LC25IE, sie_LC24IE, sie_LC23IE, sie_LC22IE, sie_LC21IE, sie_LC20IE, sie_LC19IE, sie_LC18IE, sie_LC17IE, sie_LC16IE, sie_LC15IE, sie_LC14IE, sie_LCOFIE, 3'h0, sie_SEIE, 3'h0, sie_STIE, 3'h0}
W _toMie_LCOFIE_valid_T_1 1 = hideleg_LCOFI & mideleg_LCOFI
S reg_LC14IE ? w_wen & hvien_LC14IE : w_wdata[14]
S reg_LC15IE ? w_wen & hvien_LC15IE : w_wdata[15]
S reg_LC16IE ? w_wen & hvien_LC16IE : w_wdata[16]
S reg_LC17IE ? w_wen & hvien_LC17IE : w_wdata[17]
S reg_LC18IE ? w_wen & hvien_LC18IE : w_wdata[18]
S reg_LC19IE ? w_wen & hvien_LC19IE : w_wdata[19]
S reg_LC20IE ? w_wen & hvien_LC20IE : w_wdata[20]
S reg_LC21IE ? w_wen & hvien_LC21IE : w_wdata[21]
S reg_LC22IE ? w_wen & hvien_LC22IE : w_wdata[22]
S reg_LC23IE ? w_wen & hvien_LC23IE : w_wdata[23]
S reg_LC24IE ? w_wen & hvien_LC24IE : w_wdata[24]
S reg_LC25IE ? w_wen & hvien_LC25IE : w_wdata[25]
S reg_LC26IE ? w_wen & hvien_LC26IE : w_wdata[26]
S reg_LC27IE ? w_wen & hvien_LC27IE : w_wdata[27]
S reg_LC28IE ? w_wen & hvien_LC28IE : w_wdata[28]
S reg_LC29IE ? w_wen & hvien_LC29IE : w_wdata[29]
S reg_LC30IE ? w_wen & hvien_LC30IE : w_wdata[30]
S reg_LC31IE ? w_wen & hvien_LC31IE : w_wdata[31]
S reg_LC32IE ? w_wen & hvien_LC32IE : w_wdata[32]
S reg_LC33IE ? w_wen & hvien_LC33IE : w_wdata[33]
S reg_LC34IE ? w_wen & hvien_LC34IE : w_wdata[34]
S reg_LPRASEIE ? w_wen & hvien_LPRASEIE : w_wdata[35]
S reg_LC36IE ? w_wen & hvien_LC36IE : w_wdata[36]
S reg_LC37IE ? w_wen & hvien_LC37IE : w_wdata[37]
S reg_LC38IE ? w_wen & hvien_LC38IE : w_wdata[38]
S reg_LC39IE ? w_wen & hvien_LC39IE : w_wdata[39]
S reg_LC40IE ? w_wen & hvien_LC40IE : w_wdata[40]
S reg_LC41IE ? w_wen & hvien_LC41IE : w_wdata[41]
S reg_LC42IE ? w_wen & hvien_LC42IE : w_wdata[42]
S reg_HPRASEIE ? w_wen & hvien_HPRASEIE : w_wdata[43]
S reg_LC44IE ? w_wen & hvien_LC44IE : w_wdata[44]
S reg_LC45IE ? w_wen & hvien_LC45IE : w_wdata[45]
S reg_LC46IE ? w_wen & hvien_LC46IE : w_wdata[46]
S reg_LC47IE ? w_wen & hvien_LC47IE : w_wdata[47]
S reg_LC48IE ? w_wen & hvien_LC48IE : w_wdata[48]
S reg_LC49IE ? w_wen & hvien_LC49IE : w_wdata[49]
S reg_LC50IE ? w_wen & hvien_LC50IE : w_wdata[50]
S reg_LC51IE ? w_wen & hvien_LC51IE : w_wdata[51]
S reg_LC52IE ? w_wen & hvien_LC52IE : w_wdata[52]
S reg_LC53IE ? w_wen & hvien_LC53IE : w_wdata[53]
S reg_LC54IE ? w_wen & hvien_LC54IE : w_wdata[54]
S reg_LC55IE ? w_wen & hvien_LC55IE : w_wdata[55]
S reg_LC56IE ? w_wen & hvien_LC56IE : w_wdata[56]
S reg_LC57IE ? w_wen & hvien_LC57IE : w_wdata[57]
S reg_LC58IE ? w_wen & hvien_LC58IE : w_wdata[58]
S reg_LC59IE ? w_wen & hvien_LC59IE : w_wdata[59]
S reg_LC60IE ? w_wen & hvien_LC60IE : w_wdata[60]
S reg_LC61IE ? w_wen & hvien_LC61IE : w_wdata[61]
S reg_LC62IE ? w_wen & hvien_LC62IE : w_wdata[62]
S reg_LC63IE ? w_wen & hvien_LC63IE : w_wdata[63]
A _GEN = {originAliasIE[61:11], 1'h0, originAliasIE[10:0]} | {{50'h3FFFFFFFFFFFF, ~hideleg_LCOFI} & {hvien_LC63IE, hvien_LC62IE, hvien_LC61IE, hvien_LC60IE, hvien_LC59IE, hvien_LC58IE, hvien_LC57IE, hvien_LC56IE, hvien_LC55IE, hvien_LC54IE, hvien_LC53IE, hvien_LC52IE, hvien_LC51IE, hvien_LC50IE, hvien_LC49IE, hvien_LC48IE, hvien_LC47IE, hvien_LC46IE, hvien_LC45IE, hvien_LC44IE, hvien_HPRASEIE, hvien_LC42IE, hvien_LC41IE, hvien_LC40IE, hvien_LC39IE, hvien_LC38IE, hvien_LC37IE, hvien_LC36IE, hvien_LPRASEIE, hvien_LC34IE, hvien_LC33IE, hvien_LC32IE, hvien_LC31IE, hvien_LC30IE, hvien_LC29IE, hvien_LC28IE, hvien_LC27IE, hvien_LC26IE, hvien_LC25IE, hvien_LC24IE, hvien_LC23IE, hvien_LC22IE, hvien_LC21IE, hvien_LC20IE, hvien_LC19IE, hvien_LC18IE, hvien_LC17IE, hvien_LC16IE, hvien_LC15IE, hvien_LC14IE, 1'h0}, 12'h0} & {reg_LC63IE, reg_LC62IE, reg_LC61IE, reg_LC60IE, reg_LC59IE, reg_LC58IE, reg_LC57IE, reg_LC56IE, reg_LC55IE, reg_LC54IE, reg_LC53IE, reg_LC52IE, reg_LC51IE, reg_LC50IE, reg_LC49IE, reg_LC48IE, reg_LC47IE, reg_LC46IE, reg_LC45IE, reg_LC44IE, reg_HPRASEIE, reg_LC42IE, reg_LC41IE, reg_LC40IE, reg_LC39IE, reg_LC38IE, reg_LC37IE, reg_LC36IE, reg_LPRASEIE, reg_LC34IE, reg_LC33IE, reg_LC32IE, reg_LC31IE, reg_LC30IE, reg_LC29IE, reg_LC28IE, reg_LC27IE, reg_LC26IE, reg_LC25IE, reg_LC24IE, reg_LC23IE, reg_LC22IE, reg_LC21IE, reg_LC20IE, reg_LC19IE, reg_LC18IE, reg_LC17IE, reg_LC16IE, reg_LC15IE, reg_LC14IE, 13'h0}
A _regOut_SEIE_T = _GEN[8]
A _regOut_STIE_T = _GEN[4]
A _regOut_SSIE_T = _GEN[0]
A rdata = {_GEN[62:12], 3'h0, _regOut_SEIE_T, 3'h0, _regOut_STIE_T, 3'h0, _regOut_SSIE_T, 1'h0}
A regOut_SSIE = _regOut_SSIE_T
A regOut_STIE = _regOut_STIE_T
A regOut_SEIE = _regOut_SEIE_T
A regOut_LCOFIE = _GEN[12]
A regOut_LC14IE = _GEN[13]
A regOut_LC15IE = _GEN[14]
A regOut_LC16IE = _GEN[15]
A regOut_LC17IE = _GEN[16]
A regOut_LC18IE = _GEN[17]
A regOut_LC19IE = _GEN[18]
A regOut_LC20IE = _GEN[19]
A regOut_LC21IE = _GEN[20]
A regOut_LC22IE = _GEN[21]
A regOut_LC23IE = _GEN[22]
A regOut_LC24IE = _GEN[23]
A regOut_LC25IE = _GEN[24]
A regOut_LC26IE = _GEN[25]
A regOut_LC27IE = _GEN[26]
A regOut_LC28IE = _GEN[27]
A regOut_LC29IE = _GEN[28]
A regOut_LC30IE = _GEN[29]
A regOut_LC31IE = _GEN[30]
A regOut_LC32IE = _GEN[31]
A regOut_LC33IE = _GEN[32]
A regOut_LC34IE = _GEN[33]
A regOut_LPRASEIE = _GEN[34]
A regOut_LC36IE = _GEN[35]
A regOut_LC37IE = _GEN[36]
A regOut_LC38IE = _GEN[37]
A regOut_LC39IE = _GEN[38]
A regOut_LC40IE = _GEN[39]
A regOut_LC41IE = _GEN[40]
A regOut_LC42IE = _GEN[41]
A regOut_HPRASEIE = _GEN[42]
A regOut_LC44IE = _GEN[43]
A regOut_LC45IE = _GEN[44]
A regOut_LC46IE = _GEN[45]
A regOut_LC47IE = _GEN[46]
A regOut_LC48IE = _GEN[47]
A regOut_LC49IE = _GEN[48]
A regOut_LC50IE = _GEN[49]
A regOut_LC51IE = _GEN[50]
A regOut_LC52IE = _GEN[51]
A regOut_LC53IE = _GEN[52]
A regOut_LC54IE = _GEN[53]
A regOut_LC55IE = _GEN[54]
A regOut_LC56IE = _GEN[55]
A regOut_LC57IE = _GEN[56]
A regOut_LC58IE = _GEN[57]
A regOut_LC59IE = _GEN[58]
A regOut_LC60IE = _GEN[59]
A regOut_LC61IE = _GEN[60]
A regOut_LC62IE = _GEN[61]
A regOut_LC63IE = _GEN[62]
A toMie_VSSIE_valid = hideleg_VSSI & w_wen
A toMie_VSSIE_bits = hideleg_VSSI & w_wen & w_wdata[1]
A toMie_VSTIE_valid = hideleg_VSTI & w_wen
A toMie_VSTIE_bits = hideleg_VSTI & w_wen & w_wdata[5]
A toMie_VSEIE_valid = hideleg_VSEI & w_wen
A toMie_VSEIE_bits = hideleg_VSEI & w_wen & w_wdata[9]
A toMie_LCOFIE_valid = _toMie_LCOFIE_valid_T_1 & w_wen
A toMie_LCOFIE_bits = _toMie_LCOFIE_valid_T_1 & w_wen & w_wdata[13]
A toSie_VSSIE_valid = 1'h0
A toSie_VSSIE_bits = 1'h0
A toSie_VSTIE_valid = 1'h0
A toSie_VSTIE_bits = 1'h0
A toSie_VSEIE_valid = 1'h0
A toSie_VSEIE_bits = 1'h0
A toSie_LCOFIE_valid = 1'h0
A toSie_LCOFIE_bits = 1'h0
A toSie_LC14IE_valid = 1'h0
A toSie_LC14IE_bits = 1'h0
A toSie_LC15IE_valid = 1'h0
A toSie_LC15IE_bits = 1'h0
A toSie_LC16IE_valid = 1'h0
A toSie_LC16IE_bits = 1'h0
A toSie_LC17IE_valid = 1'h0
A toSie_LC17IE_bits = 1'h0
A toSie_LC18IE_valid = 1'h0
A toSie_LC18IE_bits = 1'h0
A toSie_LC19IE_valid = 1'h0
A toSie_LC19IE_bits = 1'h0
A toSie_LC20IE_valid = 1'h0
A toSie_LC20IE_bits = 1'h0
A toSie_LC21IE_valid = 1'h0
A toSie_LC21IE_bits = 1'h0
A toSie_LC22IE_valid = 1'h0
A toSie_LC22IE_bits = 1'h0
A toSie_LC23IE_valid = 1'h0
A toSie_LC23IE_bits = 1'h0
A toSie_LC24IE_valid = 1'h0
A toSie_LC24IE_bits = 1'h0
A toSie_LC25IE_valid = 1'h0
A toSie_LC25IE_bits = 1'h0
A toSie_LC26IE_valid = 1'h0
A toSie_LC26IE_bits = 1'h0
A toSie_LC27IE_valid = 1'h0
A toSie_LC27IE_bits = 1'h0
A toSie_LC28IE_valid = 1'h0
A toSie_LC28IE_bits = 1'h0
A toSie_LC29IE_valid = 1'h0
A toSie_LC29IE_bits = 1'h0
A toSie_LC30IE_valid = 1'h0
A toSie_LC30IE_bits = 1'h0
A toSie_LC31IE_valid = 1'h0
A toSie_LC31IE_bits = 1'h0
A toSie_LC32IE_valid = 1'h0
A toSie_LC32IE_bits = 1'h0
A toSie_LC33IE_valid = 1'h0
A toSie_LC33IE_bits = 1'h0
A toSie_LC34IE_valid = 1'h0
A toSie_LC34IE_bits = 1'h0
A toSie_LPRASEIE_valid = 1'h0
A toSie_LPRASEIE_bits = 1'h0
A toSie_LC36IE_valid = 1'h0
A toSie_LC36IE_bits = 1'h0
A toSie_LC37IE_valid = 1'h0
A toSie_LC37IE_bits = 1'h0
A toSie_LC38IE_valid = 1'h0
A toSie_LC38IE_bits = 1'h0
A toSie_LC39IE_valid = 1'h0
A toSie_LC39IE_bits = 1'h0
A toSie_LC40IE_valid = 1'h0
A toSie_LC40IE_bits = 1'h0
A toSie_LC41IE_valid = 1'h0
A toSie_LC41IE_bits = 1'h0
A toSie_LC42IE_valid = 1'h0
A toSie_LC42IE_bits = 1'h0
A toSie_HPRASEIE_valid = 1'h0
A toSie_HPRASEIE_bits = 1'h0
A toSie_LC44IE_valid = 1'h0
A toSie_LC44IE_bits = 1'h0
A toSie_LC45IE_valid = 1'h0
A toSie_LC45IE_bits = 1'h0
A toSie_LC46IE_valid = 1'h0
A toSie_LC46IE_bits = 1'h0
A toSie_LC47IE_valid = 1'h0
A toSie_LC47IE_bits = 1'h0
A toSie_LC48IE_valid = 1'h0
A toSie_LC48IE_bits = 1'h0
A toSie_LC49IE_valid = 1'h0
A toSie_LC49IE_bits = 1'h0
A toSie_LC50IE_valid = 1'h0
A toSie_LC50IE_bits = 1'h0
A toSie_LC51IE_valid = 1'h0
A toSie_LC51IE_bits = 1'h0
A toSie_LC52IE_valid = 1'h0
A toSie_LC52IE_bits = 1'h0
A toSie_LC53IE_valid = 1'h0
A toSie_LC53IE_bits = 1'h0
A toSie_LC54IE_valid = 1'h0
A toSie_LC54IE_bits = 1'h0
A toSie_LC55IE_valid = 1'h0
A toSie_LC55IE_bits = 1'h0
A toSie_LC56IE_valid = 1'h0
A toSie_LC56IE_bits = 1'h0
A toSie_LC57IE_valid = 1'h0
A toSie_LC57IE_bits = 1'h0
A toSie_LC58IE_valid = 1'h0
A toSie_LC58IE_bits = 1'h0
A toSie_LC59IE_valid = 1'h0
A toSie_LC59IE_bits = 1'h0
A toSie_LC60IE_valid = 1'h0
A toSie_LC60IE_bits = 1'h0
A toSie_LC61IE_valid = 1'h0
A toSie_LC61IE_bits = 1'h0
A toSie_LC62IE_valid = 1'h0
A toSie_LC62IE_bits = 1'h0
A toSie_LC63IE_valid = 1'h0
A toSie_LC63IE_bits = 1'h0
M VStvecModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_mode 2
P o regOut_addr 62
F reg_mode 2 0
F reg_addr 62 0
S reg_mode ? w_wen & (w_wdata[1:0] == 2'h0 | w_wdata[1:0] == 2'h1) : w_wdata[1:0]
S reg_addr ? w_wen : w_wdata[63:2]
A rdata = {reg_addr, reg_mode}
A regOut_mode = reg_mode
A regOut_addr = reg_addr
M VSscratchModule n
P i clock 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
F reg_ALL 64 -
S reg_ALL ? w_wen : w_wdata
A rdata = reg_ALL
A regOut_ALL = reg_ALL
M VSepcModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_epc 63
P i trapToVS_vsepc_valid 1
P i trapToVS_vsepc_bits_epc 63
F reg_epc 63 0
S reg_epc ? w_wen | trapToVS_vsepc_valid : (trapToVS_vsepc_valid ? trapToVS_vsepc_bits_epc : 63'h0) | (w_wen ? w_wdata[63:1] : 63'h0)
A rdata = {reg_epc, 1'h0}
A regOut_epc = reg_epc
M VScauseModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_Interrupt 1
P o regOut_ExceptionCode 63
P i trapToVS_vscause_valid 1
P i trapToVS_vscause_bits_Interrupt 1
P i trapToVS_vscause_bits_ExceptionCode 63
F reg_Interrupt 1 0
F reg_ExceptionCode 63 0
S reg_Interrupt ? w_wen | trapToVS_vscause_valid : trapToVS_vscause_valid & trapToVS_vscause_bits_Interrupt | w_wen & w_wdata[63]
S reg_ExceptionCode ? w_wen | trapToVS_vscause_valid : (trapToVS_vscause_valid ? trapToVS_vscause_bits_ExceptionCode : 63'h0) | (w_wen ? w_wdata[62:0] : 63'h0)
A rdata = {reg_Interrupt, reg_ExceptionCode}
A regOut_Interrupt = reg_Interrupt
A regOut_ExceptionCode = reg_ExceptionCode
M VStvalModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
P i trapToVS_vstval_valid 1
P i trapToVS_vstval_bits_ALL 64
F reg_ALL 64 0
S reg_ALL ? w_wen | trapToVS_vstval_valid : (trapToVS_vstval_valid ? trapToVS_vstval_bits_ALL : 64'h0) | (w_wen ? w_wdata : 64'h0)
A rdata = reg_ALL
A regOut_ALL = reg_ALL
M VSipModule n
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_SSIP 1
P o regOut_STIP 1
P o regOut_SEIP 1
P o regOut_LCOFIP 1
P o regOut_LC14IP 1
P o regOut_LC15IP 1
P o regOut_LC16IP 1
P o regOut_LC17IP 1
P o regOut_LC18IP 1
P o regOut_LC19IP 1
P o regOut_LC20IP 1
P o regOut_LC21IP 1
P o regOut_LC22IP 1
P o regOut_LC23IP 1
P o regOut_LC24IP 1
P o regOut_LC25IP 1
P o regOut_LC26IP 1
P o regOut_LC27IP 1
P o regOut_LC28IP 1
P o regOut_LC29IP 1
P o regOut_LC30IP 1
P o regOut_LC31IP 1
P o regOut_LC32IP 1
P o regOut_LC33IP 1
P o regOut_LC34IP 1
P o regOut_LPRASEIP 1
P o regOut_LC36IP 1
P o regOut_LC37IP 1
P o regOut_LC38IP 1
P o regOut_LC39IP 1
P o regOut_LC40IP 1
P o regOut_LC41IP 1
P o regOut_LC42IP 1
P o regOut_HPRASEIP 1
P o regOut_LC44IP 1
P o regOut_LC45IP 1
P o regOut_LC46IP 1
P o regOut_LC47IP 1
P o regOut_LC48IP 1
P o regOut_LC49IP 1
P o regOut_LC50IP 1
P o regOut_LC51IP 1
P o regOut_LC52IP 1
P o regOut_LC53IP 1
P o regOut_LC54IP 1
P o regOut_LC55IP 1
P o regOut_LC56IP 1
P o regOut_LC57IP 1
P o regOut_LC58IP 1
P o regOut_LC59IP 1
P o regOut_LC60IP 1
P o regOut_LC61IP 1
P o regOut_LC62IP 1
P o regOut_LC63IP 1
P i mideleg_SSI 1
P i mideleg_STI 1
P i mideleg_SEI 1
P i mideleg_LCOFI 1
P i mip_SSIP 1
P i mip_VSSIP 1
P i mip_MSIP 1
P i mip_STIP 1
P i mip_VSTIP 1
P i mip_MTIP 1
P i mip_SEIP 1
P i mip_VSEIP 1
P i mip_MEIP 1
P i mip_SGEIP 1
P i mip_LCOFIP 1
P i mip_LC14IP 1
P i mip_LC15IP 1
P i mip_LC16IP 1
P i mip_LC17IP 1
P i mip_LC18IP 1
P i mip_LC19IP 1
P i mip_LC20IP 1
P i mip_LC21IP 1
P i mip_LC22IP 1
P i mip_LC23IP 1
P i mip_LC24IP 1
P i mip_LC25IP 1
P i mip_LC26IP 1
P i mip_LC27IP 1
P i mip_LC28IP 1
P i mip_LC29IP 1
P i mip_LC30IP 1
P i mip_LC31IP 1
P i mip_LC32IP 1
P i mip_LC33IP 1
P i mip_LC34IP 1
P i mip_LPRASEIP 1
P i mip_LC36IP 1
P i mip_LC37IP 1
P i mip_LC38IP 1
P i mip_LC39IP 1
P i mip_LC40IP 1
P i mip_LC41IP 1
P i mip_LC42IP 1
P i mip_HPRASEIP 1
P i mip_LC44IP 1
P i mip_LC45IP 1
P i mip_LC46IP 1
P i mip_LC47IP 1
P i mip_LC48IP 1
P i mip_LC49IP 1
P i mip_LC50IP 1
P i mip_LC51IP 1
P i mip_LC52IP 1
P i mip_LC53IP 1
P i mip_LC54IP 1
P i mip_LC55IP 1
P i mip_LC56IP 1
P i mip_LC57IP 1
P i mip_LC58IP 1
P i mip_LC59IP 1
P i mip_LC60IP 1
P i mip_LC61IP 1
P i mip_LC62IP 1
P i mip_LC63IP 1
P i mvip_SSIP 1
P i mvip_STIP 1
P i mvip_SEIP 1
P i mvip_LCOFIP 1
P i mvip_LC14IP 1
P i mvip_LC15IP 1
P i mvip_LC16IP 1
P i mvip_LC17IP 1
P i mvip_LC18IP 1
P i mvip_LC19IP 1
P i mvip_LC20IP 1
P i mvip_LC21IP 1
P i mvip_LC22IP 1
P i mvip_LC23IP 1
P i mvip_LC24IP 1
P i mvip_LC25IP 1
P i mvip_LC26IP 1
P i mvip_LC27IP 1
P i mvip_LC28IP 1
P i mvip_LC29IP 1
P i mvip_LC30IP 1
P i mvip_LC31IP 1
P i mvip_LC32IP 1
P i mvip_LC33IP 1
P i mvip_LC34IP 1
P i mvip_LPRASEIP 1
P i mvip_LC36IP 1
P i mvip_LC37IP 1
P i mvip_LC38IP 1
P i mvip_LC39IP 1
P i mvip_LC40IP 1
P i mvip_LC41IP 1
P i mvip_LC42IP 1
P i mvip_HPRASEIP 1
P i mvip_LC44IP 1
P i mvip_LC45IP 1
P i mvip_LC46IP 1
P i mvip_LC47IP 1
P i mvip_LC48IP 1
P i mvip_LC49IP 1
P i mvip_LC50IP 1
P i mvip_LC51IP 1
P i mvip_LC52IP 1
P i mvip_LC53IP 1
P i mvip_LC54IP 1
P i mvip_LC55IP 1
P i mvip_LC56IP 1
P i mvip_LC57IP 1
P i mvip_LC58IP 1
P i mvip_LC59IP 1
P i mvip_LC60IP 1
P i mvip_LC61IP 1
P i mvip_LC62IP 1
P i mvip_LC63IP 1
P i mvien_SSIE 1
P i mvien_SEIE 1
P i mvien_LC14IE 1
P i mvien_LC15IE 1
P i mvien_LC16IE 1
P i mvien_LC17IE 1
P i mvien_LC18IE 1
P i mvien_LC19IE 1
P i mvien_LC20IE 1
P i mvien_LC21IE 1
P i mvien_LC22IE 1
P i mvien_LC23IE 1
P i mvien_LC24IE 1
P i mvien_LC25IE 1
P i mvien_LC26IE 1
P i mvien_LC27IE 1
P i mvien_LC28IE 1
P i mvien_LC29IE 1
P i mvien_LC30IE 1
P i mvien_LC31IE 1
P i mvien_LC32IE 1
P i mvien_LC33IE 1
P i mvien_LC34IE 1
P i mvien_LPRASEIE 1
P i mvien_LC36IE 1
P i mvien_LC37IE 1
P i mvien_LC38IE 1
P i mvien_LC39IE 1
P i mvien_LC40IE 1
P i mvien_LC41IE 1
P i mvien_LC42IE 1
P i mvien_HPRASEIE 1
P i mvien_LC44IE 1
P i mvien_LC45IE 1
P i mvien_LC46IE 1
P i mvien_LC47IE 1
P i mvien_LC48IE 1
P i mvien_LC49IE 1
P i mvien_LC50IE 1
P i mvien_LC51IE 1
P i mvien_LC52IE 1
P i mvien_LC53IE 1
P i mvien_LC54IE 1
P i mvien_LC55IE 1
P i mvien_LC56IE 1
P i mvien_LC57IE 1
P i mvien_LC58IE 1
P i mvien_LC59IE 1
P i mvien_LC60IE 1
P i mvien_LC61IE 1
P i mvien_LC62IE 1
P i mvien_LC63IE 1
P i hideleg_SSI 1
P i hideleg_VSSI 1
P i hideleg_MSI 1
P i hideleg_STI 1
P i hideleg_VSTI 1
P i hideleg_MTI 1
P i hideleg_SEI 1
P i hideleg_VSEI 1
P i hideleg_MEI 1
P i hideleg_SGEI 1
P i hideleg_LCOFI 1
P i hvien_LC14IE 1
P i hvien_LC15IE 1
P i hvien_LC16IE 1
P i hvien_LC17IE 1
P i hvien_LC18IE 1
P i hvien_LC19IE 1
P i hvien_LC20IE 1
P i hvien_LC21IE 1
P i hvien_LC22IE 1
P i hvien_LC23IE 1
P i hvien_LC24IE 1
P i hvien_LC25IE 1
P i hvien_LC26IE 1
P i hvien_LC27IE 1
P i hvien_LC28IE 1
P i hvien_LC29IE 1
P i hvien_LC30IE 1
P i hvien_LC31IE 1
P i hvien_LC32IE 1
P i hvien_LC33IE 1
P i hvien_LC34IE 1
P i hvien_LPRASEIE 1
P i hvien_LC36IE 1
P i hvien_LC37IE 1
P i hvien_LC38IE 1
P i hvien_LC39IE 1
P i hvien_LC40IE 1
P i hvien_LC41IE 1
P i hvien_LC42IE 1
P i hvien_HPRASEIE 1
P i hvien_LC44IE 1
P i hvien_LC45IE 1
P i hvien_LC46IE 1
P i hvien_LC47IE 1
P i hvien_LC48IE 1
P i hvien_LC49IE 1
P i hvien_LC50IE 1
P i hvien_LC51IE 1
P i hvien_LC52IE 1
P i hvien_LC53IE 1
P i hvien_LC54IE 1
P i hvien_LC55IE 1
P i hvien_LC56IE 1
P i hvien_LC57IE 1
P i hvien_LC58IE 1
P i hvien_LC59IE 1
P i hvien_LC60IE 1
P i hvien_LC61IE 1
P i hvien_LC62IE 1
P i hvien_LC63IE 1
P i hvip_VSSIP 1
P i hvip_VSTIP 1
P i hvip_VSEIP 1
P i hvip_LCOFIP 1
P i hvip_LC14IP 1
P i hvip_LC15IP 1
P i hvip_LC16IP 1
P i hvip_LC17IP 1
P i hvip_LC18IP 1
P i hvip_LC19IP 1
P i hvip_LC20IP 1
P i hvip_LC21IP 1
P i hvip_LC22IP 1
P i hvip_LC23IP 1
P i hvip_LC24IP 1
P i hvip_LC25IP 1
P i hvip_LC26IP 1
P i hvip_LC27IP 1
P i hvip_LC28IP 1
P i hvip_LC29IP 1
P i hvip_LC30IP 1
P i hvip_LC31IP 1
P i hvip_LC32IP 1
P i hvip_LC33IP 1
P i hvip_LC34IP 1
P i hvip_LPRASEIP 1
P i hvip_LC36IP 1
P i hvip_LC37IP 1
P i hvip_LC38IP 1
P i hvip_LC39IP 1
P i hvip_LC40IP 1
P i hvip_LC41IP 1
P i hvip_LC42IP 1
P i hvip_HPRASEIP 1
P i hvip_LC44IP 1
P i hvip_LC45IP 1
P i hvip_LC46IP 1
P i hvip_LC47IP 1
P i hvip_LC48IP 1
P i hvip_LC49IP 1
P i hvip_LC50IP 1
P i hvip_LC51IP 1
P i hvip_LC52IP 1
P i hvip_LC53IP 1
P i hvip_LC54IP 1
P i hvip_LC55IP 1
P i hvip_LC56IP 1
P i hvip_LC57IP 1
P i hvip_LC58IP 1
P i hvip_LC59IP 1
P i hvip_LC60IP 1
P i hvip_LC61IP 1
P i hvip_LC62IP 1
P i hvip_LC63IP 1
P o toMip_LCOFIP_valid 1
P o toMip_LCOFIP_bits 1
P o toHvip_VSSIP_valid 1
P o toHvip_VSSIP_bits 1
P o toHvip_LCOFIP_bits 1
P o toHvip_LC14IP_valid 1
P o toHvip_LC14IP_bits 1
P o toHvip_LC15IP_valid 1
P o toHvip_LC15IP_bits 1
P o toHvip_LC16IP_valid 1
P o toHvip_LC16IP_bits 1
P o toHvip_LC17IP_valid 1
P o toHvip_LC17IP_bits 1
P o toHvip_LC18IP_valid 1
P o toHvip_LC18IP_bits 1
P o toHvip_LC19IP_valid 1
P o toHvip_LC19IP_bits 1
P o toHvip_LC20IP_valid 1
P o toHvip_LC20IP_bits 1
P o toHvip_LC21IP_valid 1
P o toHvip_LC21IP_bits 1
P o toHvip_LC22IP_valid 1
P o toHvip_LC22IP_bits 1
P o toHvip_LC23IP_valid 1
P o toHvip_LC23IP_bits 1
P o toHvip_LC24IP_valid 1
P o toHvip_LC24IP_bits 1
P o toHvip_LC25IP_valid 1
P o toHvip_LC25IP_bits 1
P o toHvip_LC26IP_valid 1
P o toHvip_LC26IP_bits 1
P o toHvip_LC27IP_valid 1
P o toHvip_LC27IP_bits 1
P o toHvip_LC28IP_valid 1
P o toHvip_LC28IP_bits 1
P o toHvip_LC29IP_valid 1
P o toHvip_LC29IP_bits 1
P o toHvip_LC30IP_valid 1
P o toHvip_LC30IP_bits 1
P o toHvip_LC31IP_valid 1
P o toHvip_LC31IP_bits 1
P o toHvip_LC32IP_valid 1
P o toHvip_LC32IP_bits 1
P o toHvip_LC33IP_valid 1
P o toHvip_LC33IP_bits 1
P o toHvip_LC34IP_valid 1
P o toHvip_LC34IP_bits 1
P o toHvip_LPRASEIP_valid 1
P o toHvip_LPRASEIP_bits 1
P o toHvip_LC36IP_valid 1
P o toHvip_LC36IP_bits 1
P o toHvip_LC37IP_valid 1
P o toHvip_LC37IP_bits 1
P o toHvip_LC38IP_valid 1
P o toHvip_LC38IP_bits 1
P o toHvip_LC39IP_valid 1
P o toHvip_LC39IP_bits 1
P o toHvip_LC40IP_valid 1
P o toHvip_LC40IP_bits 1
P o toHvip_LC41IP_valid 1
P o toHvip_LC41IP_bits 1
P o toHvip_LC42IP_valid 1
P o toHvip_LC42IP_bits 1
P o toHvip_HPRASEIP_valid 1
P o toHvip_HPRASEIP_bits 1
P o toHvip_LC44IP_valid 1
P o toHvip_LC44IP_bits 1
P o toHvip_LC45IP_valid 1
P o toHvip_LC45IP_bits 1
P o toHvip_LC46IP_valid 1
P o toHvip_LC46IP_bits 1
P o toHvip_LC47IP_valid 1
P o toHvip_LC47IP_bits 1
P o toHvip_LC48IP_valid 1
P o toHvip_LC48IP_bits 1
P o toHvip_LC49IP_valid 1
P o toHvip_LC49IP_bits 1
P o toHvip_LC50IP_valid 1
P o toHvip_LC50IP_bits 1
P o toHvip_LC51IP_valid 1
P o toHvip_LC51IP_bits 1
P o toHvip_LC52IP_valid 1
P o toHvip_LC52IP_bits 1
P o toHvip_LC53IP_valid 1
P o toHvip_LC53IP_bits 1
P o toHvip_LC54IP_valid 1
P o toHvip_LC54IP_bits 1
P o toHvip_LC55IP_valid 1
P o toHvip_LC55IP_bits 1
P o toHvip_LC56IP_valid 1
P o toHvip_LC56IP_bits 1
P o toHvip_LC57IP_valid 1
P o toHvip_LC57IP_bits 1
P o toHvip_LC58IP_valid 1
P o toHvip_LC58IP_bits 1
P o toHvip_LC59IP_valid 1
P o toHvip_LC59IP_bits 1
P o toHvip_LC60IP_valid 1
P o toHvip_LC60IP_bits 1
P o toHvip_LC61IP_valid 1
P o toHvip_LC61IP_bits 1
P o toHvip_LC62IP_valid 1
P o toHvip_LC62IP_bits 1
P o toHvip_LC63IP_valid 1
P o toHvip_LC63IP_bits 1
D _regOut_SSIP_T 1
D _regOut_STIP_T 1
D _regOut_SEIP_T 1
D originIP 62
W _GEN 62 = {50'h0, hideleg_LCOFI, hideleg_SGEI, hideleg_MEI, hideleg_VSEI, hideleg_SEI, 1'h0, hideleg_MTI, hideleg_VSTI, hideleg_STI, 1'h0, hideleg_MSI, hideleg_VSSI}
A originIP = {50'h0, mideleg_LCOFI, 3'h5, mideleg_SEI, 3'h1, mideleg_STI, 3'h1} & _GEN & {mip_LC63IP, mip_LC62IP, mip_LC61IP, mip_LC60IP, mip_LC59IP, mip_LC58IP, mip_LC57IP, mip_LC56IP, mip_LC55IP, mip_LC54IP, mip_LC53IP, mip_LC52IP, mip_LC51IP, mip_LC50IP, mip_LC49IP, mip_LC48IP, mip_LC47IP, mip_LC46IP, mip_LC45IP, mip_LC44IP, mip_HPRASEIP, mip_LC42IP, mip_LC41IP, mip_LC40IP, mip_LC39IP, mip_LC38IP, mip_LC37IP, mip_LC36IP, mip_LPRASEIP, mip_LC34IP, mip_LC33IP, mip_LC32IP, mip_LC31IP, mip_LC30IP, mip_LC29IP, mip_LC28IP, mip_LC27IP, mip_LC26IP, mip_LC25IP, mip_LC24IP, mip_LC23IP, mip_LC22IP, mip_LC21IP, mip_LC20IP, mip_LC19IP, mip_LC18IP, mip_LC17IP, mip_LC16IP, mip_LC15IP, mip_LC14IP, mip_LCOFIP, mip_SGEIP, mip_MEIP, mip_VSEIP, mip_SEIP, 1'h0, mip_MTIP, mip_VSTIP, mip_STIP, 1'h0, mip_MSIP, mip_VSSIP} | {50'h3FFFFFFFFFFFF, ~mideleg_LCOFI, 3'h2, ~mideleg_SEI, 3'h6, ~mideleg_STI, 3'h6} & _GEN & {mvien_LC63IE, mvien_LC62IE, mvien_LC61IE, mvien_LC60IE, mvien_LC59IE, mvien_LC58IE, mvien_LC57IE, mvien_LC56IE, mvien_LC55IE, mvien_LC54IE, mvien_LC53IE, mvien_LC52IE, mvien_LC51IE, mvien_LC50IE, mvien_LC49IE, mvien_LC48IE, mvien_LC47IE, mvien_LC46IE, mvien_LC45IE, mvien_LC44IE, mvien_HPRASEIE, mvien_LC42IE, mvien_LC41IE, mvien_LC40IE, mvien_LC39IE, mvien_LC38IE, mvien_LC37IE, mvien_LC36IE, mvien_LPRASEIE, mvien_LC34IE, mvien_LC33IE, mvien_LC32IE, mvien_LC31IE, mvien_LC30IE, mvien_LC29IE, mvien_LC28IE, mvien_LC27IE, mvien_LC26IE, mvien_LC25IE, mvien_LC24IE, mvien_LC23IE, mvien_LC22IE, mvien_LC21IE, mvien_LC20IE, mvien_LC19IE, mvien_LC18IE, mvien_LC17IE, mvien_LC16IE, mvien_LC15IE, mvien_LC14IE, 4'h0, mvien_SEIE, 7'h0} & {mvip_LC63IP, mvip_LC62IP, mvip_LC61IP, mvip_LC60IP, mvip_LC59IP, mvip_LC58IP, mvip_LC57IP, mvip_LC56IP, mvip_LC55IP, mvip_LC54IP, mvip_LC53IP, mvip_LC52IP, mvip_LC51IP, mvip_LC50IP, mvip_LC49IP, mvip_LC48IP, mvip_LC47IP, mvip_LC46IP, mvip_LC45IP, mvip_LC44IP, mvip_HPRASEIP, mvip_LC42IP, mvip_LC41IP, mvip_LC40IP, mvip_LC39IP, mvip_LC38IP, mvip_LC37IP, mvip_LC36IP, mvip_LPRASEIP, mvip_LC34IP, mvip_LC33IP, mvip_LC32IP, mvip_LC31IP, mvip_LC30IP, mvip_LC29IP, mvip_LC28IP, mvip_LC27IP, mvip_LC26IP, mvip_LC25IP, mvip_LC24IP, mvip_LC23IP, mvip_LC22IP, mvip_LC21IP, mvip_LC20IP, mvip_LC19IP, mvip_LC18IP, mvip_LC17IP, mvip_LC16IP, mvip_LC15IP, mvip_LC14IP, mvip_LCOFIP, 3'h0, mvip_SEIP, 3'h0, mvip_STIP, 3'h0} | {50'h3FFFFFFFFFFFF, ~hideleg_LCOFI, ~hideleg_SGEI, ~hideleg_MEI, ~hideleg_VSEI, ~hideleg_SEI, 1'h1, ~hideleg_MTI, ~hideleg_VSTI, ~hideleg_STI, 1'h1, ~hideleg_MSI, ~hideleg_VSSI} & {hvien_LC63IE, hvien_LC62IE, hvien_LC61IE, hvien_LC60IE, hvien_LC59IE, hvien_LC58IE, hvien_LC57IE, hvien_LC56IE, hvien_LC55IE, hvien_LC54IE, hvien_LC53IE, hvien_LC52IE, hvien_LC51IE, hvien_LC50IE, hvien_LC49IE, hvien_LC48IE, hvien_LC47IE, hvien_LC46IE, hvien_LC45IE, hvien_LC44IE, hvien_HPRASEIE, hvien_LC42IE, hvien_LC41IE, hvien_LC40IE, hvien_LC39IE, hvien_LC38IE, hvien_LC37IE, hvien_LC36IE, hvien_LPRASEIE, hvien_LC34IE, hvien_LC33IE, hvien_LC32IE, hvien_LC31IE, hvien_LC30IE, hvien_LC29IE, hvien_LC28IE, hvien_LC27IE, hvien_LC26IE, hvien_LC25IE, hvien_LC24IE, hvien_LC23IE, hvien_LC22IE, hvien_LC21IE, hvien_LC20IE, hvien_LC19IE, hvien_LC18IE, hvien_LC17IE, hvien_LC16IE, hvien_LC15IE, hvien_LC14IE, 12'h0} & {hvip_LC63IP, hvip_LC62IP, hvip_LC61IP, hvip_LC60IP, hvip_LC59IP, hvip_LC58IP, hvip_LC57IP, hvip_LC56IP, hvip_LC55IP, hvip_LC54IP, hvip_LC53IP, hvip_LC52IP, hvip_LC51IP, hvip_LC50IP, hvip_LC49IP, hvip_LC48IP, hvip_LC47IP, hvip_LC46IP, hvip_LC45IP, hvip_LC44IP, hvip_HPRASEIP, hvip_LC42IP, hvip_LC41IP, hvip_LC40IP, hvip_LC39IP, hvip_LC38IP, hvip_LC37IP, hvip_LC36IP, hvip_LPRASEIP, hvip_LC34IP, hvip_LC33IP, hvip_LC32IP, hvip_LC31IP, hvip_LC30IP, hvip_LC29IP, hvip_LC28IP, hvip_LC27IP, hvip_LC26IP, hvip_LC25IP, hvip_LC24IP, hvip_LC23IP, hvip_LC22IP, hvip_LC21IP, hvip_LC20IP, hvip_LC19IP, hvip_LC18IP, hvip_LC17IP, hvip_LC16IP, hvip_LC15IP, hvip_LC14IP, hvip_LCOFIP, 2'h0, hvip_VSEIP, 3'h0, hvip_VSTIP, 3'h0, hvip_VSSIP}
A _regOut_SEIP_T = originIP[8]
A _regOut_STIP_T = originIP[4]
A _regOut_SSIP_T = originIP[0]
A rdata = {originIP[61:11], 3'h0, _regOut_SEIP_T, 3'h0, _regOut_STIP_T, 3'h0, _regOut_SSIP_T, 1'h0}
A regOut_SSIP = _regOut_SSIP_T
A regOut_STIP = _regOut_STIP_T
A regOut_SEIP = _regOut_SEIP_T
A regOut_LCOFIP = originIP[11]
A regOut_LC14IP = originIP[12]
A regOut_LC15IP = originIP[13]
A regOut_LC16IP = originIP[14]
A regOut_LC17IP = originIP[15]
A regOut_LC18IP = originIP[16]
A regOut_LC19IP = originIP[17]
A regOut_LC20IP = originIP[18]
A regOut_LC21IP = originIP[19]
A regOut_LC22IP = originIP[20]
A regOut_LC23IP = originIP[21]
A regOut_LC24IP = originIP[22]
A regOut_LC25IP = originIP[23]
A regOut_LC26IP = originIP[24]
A regOut_LC27IP = originIP[25]
A regOut_LC28IP = originIP[26]
A regOut_LC29IP = originIP[27]
A regOut_LC30IP = originIP[28]
A regOut_LC31IP = originIP[29]
A regOut_LC32IP = originIP[30]
A regOut_LC33IP = originIP[31]
A regOut_LC34IP = originIP[32]
A regOut_LPRASEIP = originIP[33]
A regOut_LC36IP = originIP[34]
A regOut_LC37IP = originIP[35]
A regOut_LC38IP = originIP[36]
A regOut_LC39IP = originIP[37]
A regOut_LC40IP = originIP[38]
A regOut_LC41IP = originIP[39]
A regOut_LC42IP = originIP[40]
A regOut_HPRASEIP = originIP[41]
A regOut_LC44IP = originIP[42]
A regOut_LC45IP = originIP[43]
A regOut_LC46IP = originIP[44]
A regOut_LC47IP = originIP[45]
A regOut_LC48IP = originIP[46]
A regOut_LC49IP = originIP[47]
A regOut_LC50IP = originIP[48]
A regOut_LC51IP = originIP[49]
A regOut_LC52IP = originIP[50]
A regOut_LC53IP = originIP[51]
A regOut_LC54IP = originIP[52]
A regOut_LC55IP = originIP[53]
A regOut_LC56IP = originIP[54]
A regOut_LC57IP = originIP[55]
A regOut_LC58IP = originIP[56]
A regOut_LC59IP = originIP[57]
A regOut_LC60IP = originIP[58]
A regOut_LC61IP = originIP[59]
A regOut_LC62IP = originIP[60]
A regOut_LC63IP = originIP[61]
A toMip_LCOFIP_valid = w_wen & hideleg_LCOFI & mideleg_LCOFI
A toMip_LCOFIP_bits = w_wdata[13]
A toHvip_VSSIP_valid = w_wen & hideleg_VSSI
A toHvip_VSSIP_bits = w_wdata[1]
A toHvip_LCOFIP_bits = w_wdata[13]
A toHvip_LC14IP_valid = w_wen & hvien_LC14IE
A toHvip_LC14IP_bits = w_wdata[14]
A toHvip_LC15IP_valid = w_wen & hvien_LC15IE
A toHvip_LC15IP_bits = w_wdata[15]
A toHvip_LC16IP_valid = w_wen & hvien_LC16IE
A toHvip_LC16IP_bits = w_wdata[16]
A toHvip_LC17IP_valid = w_wen & hvien_LC17IE
A toHvip_LC17IP_bits = w_wdata[17]
A toHvip_LC18IP_valid = w_wen & hvien_LC18IE
A toHvip_LC18IP_bits = w_wdata[18]
A toHvip_LC19IP_valid = w_wen & hvien_LC19IE
A toHvip_LC19IP_bits = w_wdata[19]
A toHvip_LC20IP_valid = w_wen & hvien_LC20IE
A toHvip_LC20IP_bits = w_wdata[20]
A toHvip_LC21IP_valid = w_wen & hvien_LC21IE
A toHvip_LC21IP_bits = w_wdata[21]
A toHvip_LC22IP_valid = w_wen & hvien_LC22IE
A toHvip_LC22IP_bits = w_wdata[22]
A toHvip_LC23IP_valid = w_wen & hvien_LC23IE
A toHvip_LC23IP_bits = w_wdata[23]
A toHvip_LC24IP_valid = w_wen & hvien_LC24IE
A toHvip_LC24IP_bits = w_wdata[24]
A toHvip_LC25IP_valid = w_wen & hvien_LC25IE
A toHvip_LC25IP_bits = w_wdata[25]
A toHvip_LC26IP_valid = w_wen & hvien_LC26IE
A toHvip_LC26IP_bits = w_wdata[26]
A toHvip_LC27IP_valid = w_wen & hvien_LC27IE
A toHvip_LC27IP_bits = w_wdata[27]
A toHvip_LC28IP_valid = w_wen & hvien_LC28IE
A toHvip_LC28IP_bits = w_wdata[28]
A toHvip_LC29IP_valid = w_wen & hvien_LC29IE
A toHvip_LC29IP_bits = w_wdata[29]
A toHvip_LC30IP_valid = w_wen & hvien_LC30IE
A toHvip_LC30IP_bits = w_wdata[30]
A toHvip_LC31IP_valid = w_wen & hvien_LC31IE
A toHvip_LC31IP_bits = w_wdata[31]
A toHvip_LC32IP_valid = w_wen & hvien_LC32IE
A toHvip_LC32IP_bits = w_wdata[32]
A toHvip_LC33IP_valid = w_wen & hvien_LC33IE
A toHvip_LC33IP_bits = w_wdata[33]
A toHvip_LC34IP_valid = w_wen & hvien_LC34IE
A toHvip_LC34IP_bits = w_wdata[34]
A toHvip_LPRASEIP_valid = w_wen & hvien_LPRASEIE
A toHvip_LPRASEIP_bits = w_wdata[35]
A toHvip_LC36IP_valid = w_wen & hvien_LC36IE
A toHvip_LC36IP_bits = w_wdata[36]
A toHvip_LC37IP_valid = w_wen & hvien_LC37IE
A toHvip_LC37IP_bits = w_wdata[37]
A toHvip_LC38IP_valid = w_wen & hvien_LC38IE
A toHvip_LC38IP_bits = w_wdata[38]
A toHvip_LC39IP_valid = w_wen & hvien_LC39IE
A toHvip_LC39IP_bits = w_wdata[39]
A toHvip_LC40IP_valid = w_wen & hvien_LC40IE
A toHvip_LC40IP_bits = w_wdata[40]
A toHvip_LC41IP_valid = w_wen & hvien_LC41IE
A toHvip_LC41IP_bits = w_wdata[41]
A toHvip_LC42IP_valid = w_wen & hvien_LC42IE
A toHvip_LC42IP_bits = w_wdata[42]
A toHvip_HPRASEIP_valid = w_wen & hvien_HPRASEIE
A toHvip_HPRASEIP_bits = w_wdata[43]
A toHvip_LC44IP_valid = w_wen & hvien_LC44IE
A toHvip_LC44IP_bits = w_wdata[44]
A toHvip_LC45IP_valid = w_wen & hvien_LC45IE
A toHvip_LC45IP_bits = w_wdata[45]
A toHvip_LC46IP_valid = w_wen & hvien_LC46IE
A toHvip_LC46IP_bits = w_wdata[46]
A toHvip_LC47IP_valid = w_wen & hvien_LC47IE
A toHvip_LC47IP_bits = w_wdata[47]
A toHvip_LC48IP_valid = w_wen & hvien_LC48IE
A toHvip_LC48IP_bits = w_wdata[48]
A toHvip_LC49IP_valid = w_wen & hvien_LC49IE
A toHvip_LC49IP_bits = w_wdata[49]
A toHvip_LC50IP_valid = w_wen & hvien_LC50IE
A toHvip_LC50IP_bits = w_wdata[50]
A toHvip_LC51IP_valid = w_wen & hvien_LC51IE
A toHvip_LC51IP_bits = w_wdata[51]
A toHvip_LC52IP_valid = w_wen & hvien_LC52IE
A toHvip_LC52IP_bits = w_wdata[52]
A toHvip_LC53IP_valid = w_wen & hvien_LC53IE
A toHvip_LC53IP_bits = w_wdata[53]
A toHvip_LC54IP_valid = w_wen & hvien_LC54IE
A toHvip_LC54IP_bits = w_wdata[54]
A toHvip_LC55IP_valid = w_wen & hvien_LC55IE
A toHvip_LC55IP_bits = w_wdata[55]
A toHvip_LC56IP_valid = w_wen & hvien_LC56IE
A toHvip_LC56IP_bits = w_wdata[56]
A toHvip_LC57IP_valid = w_wen & hvien_LC57IE
A toHvip_LC57IP_bits = w_wdata[57]
A toHvip_LC58IP_valid = w_wen & hvien_LC58IE
A toHvip_LC58IP_bits = w_wdata[58]
A toHvip_LC59IP_valid = w_wen & hvien_LC59IE
A toHvip_LC59IP_bits = w_wdata[59]
A toHvip_LC60IP_valid = w_wen & hvien_LC60IE
A toHvip_LC60IP_bits = w_wdata[60]
A toHvip_LC61IP_valid = w_wen & hvien_LC61IE
A toHvip_LC61IP_bits = w_wdata[61]
A toHvip_LC62IP_valid = w_wen & hvien_LC62IE
A toHvip_LC62IP_bits = w_wdata[62]
A toHvip_LC63IP_valid = w_wen & hvien_LC63IE
A toHvip_LC63IP_bits = w_wdata[63]
M VStimecmpModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_vstimecmp 64
F reg_vstimecmp 64 18446744073709551615
S reg_vstimecmp ? w_wen : w_wdata
A rdata = reg_vstimecmp
A regOut_vstimecmp = reg_vstimecmp
M VSatpModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_MODE 4
P o regOut_ASID 16
P o regOut_PPN 44
P i v 1
P i hgatp_MODE 4
F reg_MODE 4 0
F reg_ASID 16 0
F reg_PPN 44 0
V _GEN 1 = w_wdata[63:60] == 4'h0 | w_wdata[63:60] == 4'h8 | w_wdata[63:60] == 4'h9
V _GEN_0 1 = w_wen & _GEN
V _GEN_1 1 = w_wen & ~v & ~_GEN
S reg_MODE ? _GEN_0 | _GEN_1 & _GEN_0 : w_wdata[63:60]
S reg_ASID ? _GEN_0 | _GEN_1 : w_wdata[59:44]
S reg_PPN ? _GEN_0 | _GEN_1 : w_wdata[43:0] & ((hgatp_MODE == 4'h0 ? 44'hFFFFFFFFF : 44'h0) | (hgatp_MODE == 4'h8 ? 44'h1FFFFFFF : 44'h0) | (hgatp_MODE == 4'h9 ? 44'h3FFFFFFFFF : 44'h0))
A rdata = {reg_MODE, reg_ASID, reg_PPN}
A regOut_MODE = reg_MODE
A regOut_ASID = reg_ASID
A regOut_PPN = reg_PPN
M FcsrModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P i robCommit_fflags_valid 1
P i robCommit_fflags_bits 5
P i wAliasFflags_wen 1
P i wAliasFflags_wdata 64
P i wAliasFfm_wen 1
P i wAliasFfm_wdata 64
P o fflags 5
P o frm 3
P o fflagsRdata 5
P o frmRdata 3
F reg_NX 1 0
F reg_UF 1 0
F reg_OF 1 0
F reg_DZ 1 0
F reg_NV 1 0
F reg_FRM 3 0
W _fflags_output 5 = {reg_NV, reg_DZ, reg_OF, reg_UF, reg_NX}
S reg_NX ? robCommit_fflags_valid : robCommit_fflags_bits[0] | reg_NX
S reg_UF ? robCommit_fflags_valid : robCommit_fflags_bits[1] | reg_UF
S reg_OF ? robCommit_fflags_valid : robCommit_fflags_bits[2] | reg_OF
S reg_DZ ? robCommit_fflags_valid : robCommit_fflags_bits[3] | reg_DZ
S reg_NV ? robCommit_fflags_valid : robCommit_fflags_bits[4] | reg_NV
S reg_NX ? !(robCommit_fflags_valid) & w_wen | wAliasFflags_wen : wAliasFflags_wen & wAliasFflags_wdata[0] | w_wen & w_wdata[0]
S reg_UF ? !(robCommit_fflags_valid) & w_wen | wAliasFflags_wen : wAliasFflags_wen & wAliasFflags_wdata[1] | w_wen & w_wdata[1]
S reg_OF ? !(robCommit_fflags_valid) & w_wen | wAliasFflags_wen : wAliasFflags_wen & wAliasFflags_wdata[2] | w_wen & w_wdata[2]
S reg_DZ ? !(robCommit_fflags_valid) & w_wen | wAliasFflags_wen : wAliasFflags_wen & wAliasFflags_wdata[3] | w_wen & w_wdata[3]
S reg_NV ? !(robCommit_fflags_valid) & w_wen | wAliasFflags_wen : wAliasFflags_wen & wAliasFflags_wdata[4] | w_wen & w_wdata[4]
S reg_FRM ? w_wen | wAliasFfm_wen : (wAliasFfm_wen ? wAliasFfm_wdata[2:0] : 3'h0) | (w_wen ? w_wdata[7:5] : 3'h0)
A rdata = {56'h0, reg_FRM, reg_NV, reg_DZ, reg_OF, reg_UF, reg_NX}
A fflags = _fflags_output
A frm = reg_FRM
A fflagsRdata = _fflags_output
A frmRdata = reg_FRM
M VstartModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_vstart 7
P i robCommit_vsDirty 1
P i robCommit_vstart_valid 1
P i robCommit_vstart_bits 7
F reg_vstart 7 0
S reg_vstart ? w_wen : w_wdata[6:0]
S reg_vstart ? !(w_wen) & robCommit_vsDirty & ~robCommit_vstart_valid : 7'h0
S reg_vstart ? !(w_wen) & !(robCommit_vsDirty & ~robCommit_vstart_valid) & robCommit_vstart_valid : robCommit_vstart_bits
A rdata = {57'h0, reg_vstart}
A regOut_vstart = reg_vstart
M VcsrModule n
P i clock 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P i robCommit_vxsat_valid 1
P i robCommit_vxsat_bits 1
P i wAliasVxsat_wen 1
P i wAliasVxsat_wdata 64
P i wAliasVxrm_wen 1
P i wAliasVxrm_wdata 64
P o vxsat 1
P o vxrm 2
F reg_VXSAT 1 -
F reg_VXRM 2 -
S reg_VXSAT ? robCommit_vxsat_valid : reg_VXSAT | robCommit_vxsat_bits
S reg_VXSAT ? !(robCommit_vxsat_valid) & w_wen | wAliasVxsat_wen : wAliasVxsat_wen & wAliasVxsat_wdata[0] | w_wen & w_wdata[0]
S reg_VXRM ? w_wen | wAliasVxrm_wen : (wAliasVxrm_wen ? wAliasVxrm_wdata[1:0] : 2'h0) | (w_wen ? w_wdata[2:1] : 2'h0)
A rdata = {61'h0, reg_VXRM, reg_VXSAT}
A vxsat = reg_VXSAT
A vxrm = reg_VXRM
M VtypeModule a
P i clock 1
P i reset 1
P o rdata 64
P i robCommit_vtype_valid 1
P i robCommit_vtype_bits_VILL 1
P i robCommit_vtype_bits_VMA 1
P i robCommit_vtype_bits_VTA 1
P i robCommit_vtype_bits_VSEW 3
P i robCommit_vtype_bits_VLMUL 3
F reg_VILL 1 1
F reg_VMA 1 0
F reg_VTA 1 0
F reg_VSEW 3 0
F reg_VLMUL 3 0
S reg_VILL ? robCommit_vtype_valid : robCommit_vtype_bits_VILL
S reg_VMA ? robCommit_vtype_valid : robCommit_vtype_bits_VMA
S reg_VTA ? robCommit_vtype_valid : robCommit_vtype_bits_VTA
S reg_VSEW ? robCommit_vtype_valid : robCommit_vtype_bits_VSEW
S reg_VLMUL ? robCommit_vtype_valid : robCommit_vtype_bits_VLMUL
A rdata = {reg_VILL, 55'h0, reg_VMA, reg_VTA, reg_VSEW, reg_VLMUL}
M cycleModule n
P i clock 1
P o rdata 64
P i mHPM_cycle 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_cycle 64 -
S reg_cycle ? unprivCountUpdate : mHPM_cycle
A rdata = debugModeStopCount ? reg_cycle : mHPM_cycle
M timeModule n
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_time_valid 1
P i mHPM_time_bits 64
P i v 1
P i nextV 1
P i htimedelta 64
P i debugModeStopTime 1
P o updated 1
P o stime 64
P o vstime 64
F reg_time 64 -
F virtModeChanged 1 -
F updated_last_REG 1 -
W _vstimeTmp_T 64 = mHPM_time_bits + htimedelta
S reg_time ? mHPM_time_valid & ~debugModeStopTime | virtModeChanged : v ? _vstimeTmp_T : mHPM_time_bits
A rdata = reg_time
A updated = updated_last_REG
A stime = mHPM_time_bits
A vstime = _vstimeTmp_T
M instretModule n
P i clock 1
P o rdata 64
P i mHPM_instret 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_instret 64 -
S reg_instret ? unprivCountUpdate : mHPM_instret
A rdata = debugModeStopCount ? reg_instret : mHPM_instret
M Hpmcounter3Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_0 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_0
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_0
M Hpmcounter4Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_1 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_1
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_1
M Hpmcounter5Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_2 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_2
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_2
M Hpmcounter6Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_3 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_3
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_3
M Hpmcounter7Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_4 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_4
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_4
M Hpmcounter8Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_5 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_5
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_5
M Hpmcounter9Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_6 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_6
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_6
M Hpmcounter10Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_7 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_7
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_7
M Hpmcounter11Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_8 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_8
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_8
M Hpmcounter12Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_9 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_9
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_9
M Hpmcounter13Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_10 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_10
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_10
M Hpmcounter14Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_11 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_11
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_11
M Hpmcounter15Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_12 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_12
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_12
M Hpmcounter16Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_13 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_13
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_13
M Hpmcounter17Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_14 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_14
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_14
M Hpmcounter18Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_15 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_15
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_15
M Hpmcounter19Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_16 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_16
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_16
M Hpmcounter20Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_17 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_17
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_17
M Hpmcounter21Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_18 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_18
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_18
M Hpmcounter22Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_19 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_19
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_19
M Hpmcounter23Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_20 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_20
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_20
M Hpmcounter24Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_21 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_21
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_21
M Hpmcounter25Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_22 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_22
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_22
M Hpmcounter26Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_23 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_23
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_23
M Hpmcounter27Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_24 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_24
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_24
M Hpmcounter28Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_25 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_25
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_25
M Hpmcounter29Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_26 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_26
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_26
M Hpmcounter30Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_27 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_27
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_27
M Hpmcounter31Module a
P i clock 1
P i reset 1
P o rdata 64
P i mHPM_hpmcounters_28 64
P i debugModeStopCount 1
P i unprivCountUpdate 1
F reg_hpmcounter 64 0
S reg_hpmcounter ? unprivCountUpdate : mHPM_hpmcounters_28
A rdata = debugModeStopCount ? reg_hpmcounter : mHPM_hpmcounters_28
M MiselectModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 9
P o inIMSICRange 1
F value 9 0
S value ? w_wen & ~(w_wdata[8]) : w_wdata[8:0]
A rdata = {55'h0, value}
A regOut_ALL = value
A inIMSICRange = value > 9'h6F & ~(value[8])
M MiregModule n
P o rdata 64
P o regOut_ALL 64
P i iregRead_mireg 64
A rdata = iregRead_mireg
A regOut_ALL = iregRead_mireg
M MtopeiModule n
P o rdata 64
P o regOut_IID 11
P o regOut_IPRIO 11
P i aiaToCSR_mtopei_IID 11
P i aiaToCSR_mtopei_IPRIO 11
A rdata = {37'h0, aiaToCSR_mtopei_IID, 5'h0, aiaToCSR_mtopei_IPRIO}
A regOut_IID = aiaToCSR_mtopei_IID
A regOut_IPRIO = aiaToCSR_mtopei_IPRIO
M MtopiModule n
P o rdata 64
P o regOut_IID 12
P i topIR_mtopi_IID 12
P i topIR_mtopi_IPRIO 8
A rdata = {36'h0, topIR_mtopi_IID, 8'h0, topIR_mtopi_IPRIO}
A regOut_IID = topIR_mtopi_IID
M SiselectModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 13
P o inIMSICRange 1
F value 13 0
S value ? w_wen & ~(w_wdata[12]) : w_wdata[12:0]
A rdata = {51'h0, value}
A regOut_ALL = value
A inIMSICRange = value > 13'h6F & value < 13'h100
M SiregModule n
P o rdata 64
P o regOut_ALL 64
P i iregRead_sireg 64
A rdata = iregRead_sireg
A regOut_ALL = iregRead_sireg
M StopeiModule n
P o rdata 64
P o regOut_IID 11
P o regOut_IPRIO 11
P i aiaToCSR_stopei_IID 11
P i aiaToCSR_stopei_IPRIO 11
A rdata = {37'h0, aiaToCSR_stopei_IID, 5'h0, aiaToCSR_stopei_IPRIO}
A regOut_IID = aiaToCSR_stopei_IID
A regOut_IPRIO = aiaToCSR_stopei_IPRIO
M StopiModule n
P o rdata 64
P o regOut_IID 12
P i topIR_stopi_IID 12
P i topIR_stopi_IPRIO 8
A rdata = {36'h0, topIR_stopi_IID, 8'h0, topIR_stopi_IPRIO}
A regOut_IID = topIR_stopi_IID
M VSiselectModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 13
P o inIMSICRange 1
F value 13 0
S value ? w_wen & ~(w_wdata[12]) : w_wdata[12:0]
A rdata = {51'h0, value}
A regOut_ALL = value
A inIMSICRange = value > 13'h6F & value < 13'h100
M VSiregModule n
P o rdata 64
P o regOut_ALL 64
P i iregRead_sireg 64
A rdata = iregRead_sireg
A regOut_ALL = iregRead_sireg
M VStopeiModule n
P o rdata 64
P o regOut_IID 11
P o regOut_IPRIO 11
P i aiaToCSR_vstopei_IID 11
P i aiaToCSR_vstopei_IPRIO 11
A rdata = {37'h0, aiaToCSR_vstopei_IID, 5'h0, aiaToCSR_vstopei_IPRIO}
A regOut_IID = aiaToCSR_vstopei_IID
A regOut_IPRIO = aiaToCSR_vstopei_IPRIO
M VStopiModule n
P o rdata 64
P o regOut_IID 12
P i topIR_vstopi_IID 12
P i topIR_vstopi_IPRIO 8
A rdata = {36'h0, topIR_vstopi_IID, 8'h0, topIR_vstopi_IPRIO}
A regOut_IID = topIR_vstopi_IID
M Iprio0Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
F reg_PrioSSI 8 0
F reg_PrioVSSI 8 0
F reg_PrioMSI 8 0
F reg_PrioSTI 8 0
F reg_PrioVSTI 8 0
F reg_PrioMTI 8 0
S reg_PrioSSI ? w_wen : w_wdata[15:8]
S reg_PrioVSSI ? w_wen : w_wdata[23:16]
S reg_PrioMSI ? w_wen : w_wdata[31:24]
S reg_PrioSTI ? w_wen : w_wdata[47:40]
S reg_PrioVSTI ? w_wen : w_wdata[55:48]
S reg_PrioMTI ? w_wen : w_wdata[63:56]
A rdata = {reg_PrioMTI, reg_PrioVSTI, reg_PrioSTI, 8'h0, reg_PrioMSI, reg_PrioVSSI, reg_PrioSSI, 8'h0}
M Iprio2Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
F reg_PrioSEI 8 0
F reg_PrioVSEI 8 0
F reg_PrioSGEI 8 0
F reg_PrioLCOFI 8 0
F reg_Prio14 8 0
F reg_Prio15 8 0
S reg_PrioSEI ? w_wen : w_wdata[15:8]
S reg_PrioVSEI ? w_wen : w_wdata[23:16]
S reg_PrioSGEI ? w_wen : w_wdata[39:32]
S reg_PrioLCOFI ? w_wen : w_wdata[47:40]
S reg_Prio14 ? w_wen : w_wdata[55:48]
S reg_Prio15 ? w_wen : w_wdata[63:56]
A rdata = {16'h0, reg_PrioLCOFI, reg_PrioSGEI, 8'h0, reg_PrioVSEI, reg_PrioSEI, 8'h0}
M Iprio0Module_1 a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P i mideleg_SSI 1
P i mideleg_STI 1
P i mideleg_SEI 1
P i mideleg_LCOFI 1
P i mvien_SSIE 1
P i mvien_SEIE 1
P i mvien_LC14IE 1
P i mvien_LC15IE 1
P i mvien_LC16IE 1
P i mvien_LC17IE 1
P i mvien_LC18IE 1
P i mvien_LC19IE 1
P i mvien_LC20IE 1
P i mvien_LC21IE 1
P i mvien_LC22IE 1
P i mvien_LC23IE 1
P i mvien_LC24IE 1
P i mvien_LC25IE 1
P i mvien_LC26IE 1
P i mvien_LC27IE 1
P i mvien_LC28IE 1
P i mvien_LC29IE 1
P i mvien_LC30IE 1
P i mvien_LC31IE 1
P i mvien_LC32IE 1
P i mvien_LC33IE 1
P i mvien_LC34IE 1
P i mvien_LPRASEIE 1
P i mvien_LC36IE 1
P i mvien_LC37IE 1
P i mvien_LC38IE 1
P i mvien_LC39IE 1
P i mvien_LC40IE 1
P i mvien_LC41IE 1
P i mvien_LC42IE 1
P i mvien_HPRASEIE 1
P i mvien_LC44IE 1
P i mvien_LC45IE 1
P i mvien_LC46IE 1
P i mvien_LC47IE 1
P i mvien_LC48IE 1
P i mvien_LC49IE 1
P i mvien_LC50IE 1
P i mvien_LC51IE 1
P i mvien_LC52IE 1
P i mvien_LC53IE 1
P i mvien_LC54IE 1
P i mvien_LC55IE 1
P i mvien_LC56IE 1
P i mvien_LC57IE 1
P i mvien_LC58IE 1
P i mvien_LC59IE 1
P i mvien_LC60IE 1
P i mvien_LC61IE 1
P i mvien_LC62IE 1
P i mvien_LC63IE 1
F reg_PrioSSI 8 0
F reg_PrioVSSI 8 0
F reg_PrioMSI 8 0
F reg_PrioSTI 8 0
F reg_PrioVSTI 8 0
F reg_PrioMTI 8 0
D _regOut_PrioSSI_T 8
D _regOut_PrioSTI_T 8
S reg_PrioSSI ? w_wen : w_wdata[15:8]
S reg_PrioVSSI ? w_wen : w_wdata[23:16]
S reg_PrioMSI ? w_wen : w_wdata[31:24]
S reg_PrioSTI ? w_wen : w_wdata[47:40]
S reg_PrioVSTI ? w_wen : w_wdata[55:48]
S reg_PrioMTI ? w_wen : w_wdata[63:56]
A _regOut_PrioSTI_T = reg_PrioSTI & {8{mideleg_STI}}
A _regOut_PrioSSI_T = reg_PrioSSI & {8{mideleg_SSI | ~mideleg_SSI & mvien_SSIE}}
A rdata = {8'h0, reg_PrioVSTI, _regOut_PrioSTI_T, 16'h0, reg_PrioVSSI, _regOut_PrioSSI_T, 8'h0}
M Iprio2Module_1 a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P i mideleg_SSI 1
P i mideleg_STI 1
P i mideleg_SEI 1
P i mideleg_LCOFI 1
P i mvien_SSIE 1
P i mvien_SEIE 1
P i mvien_LC14IE 1
P i mvien_LC15IE 1
P i mvien_LC16IE 1
P i mvien_LC17IE 1
P i mvien_LC18IE 1
P i mvien_LC19IE 1
P i mvien_LC20IE 1
P i mvien_LC21IE 1
P i mvien_LC22IE 1
P i mvien_LC23IE 1
P i mvien_LC24IE 1
P i mvien_LC25IE 1
P i mvien_LC26IE 1
P i mvien_LC27IE 1
P i mvien_LC28IE 1
P i mvien_LC29IE 1
P i mvien_LC30IE 1
P i mvien_LC31IE 1
P i mvien_LC32IE 1
P i mvien_LC33IE 1
P i mvien_LC34IE 1
P i mvien_LPRASEIE 1
P i mvien_LC36IE 1
P i mvien_LC37IE 1
P i mvien_LC38IE 1
P i mvien_LC39IE 1
P i mvien_LC40IE 1
P i mvien_LC41IE 1
P i mvien_LC42IE 1
P i mvien_HPRASEIE 1
P i mvien_LC44IE 1
P i mvien_LC45IE 1
P i mvien_LC46IE 1
P i mvien_LC47IE 1
P i mvien_LC48IE 1
P i mvien_LC49IE 1
P i mvien_LC50IE 1
P i mvien_LC51IE 1
P i mvien_LC52IE 1
P i mvien_LC53IE 1
P i mvien_LC54IE 1
P i mvien_LC55IE 1
P i mvien_LC56IE 1
P i mvien_LC57IE 1
P i mvien_LC58IE 1
P i mvien_LC59IE 1
P i mvien_LC60IE 1
P i mvien_LC61IE 1
P i mvien_LC62IE 1
P i mvien_LC63IE 1
F reg_PrioVSEI 8 0
F reg_PrioMEI 8 0
F reg_PrioSGEI 8 0
F reg_PrioLCOFI 8 0
F reg_Prio14 8 0
F reg_Prio15 8 0
D _regOut_PrioLCOFI_T 8
D _regOut_Prio14_T 8
D _regOut_Prio15_T 8
S reg_PrioVSEI ? w_wen : w_wdata[23:16]
S reg_PrioMEI ? w_wen : w_wdata[31:24]
S reg_PrioSGEI ? w_wen : w_wdata[39:32]
S reg_PrioLCOFI ? w_wen : w_wdata[47:40]
S reg_Prio14 ? w_wen : w_wdata[55:48]
S reg_Prio15 ? w_wen : w_wdata[63:56]
A _regOut_Prio15_T = reg_Prio15 & {8{mvien_LC15IE}}
A _regOut_Prio14_T = reg_Prio14 & {8{mvien_LC14IE}}
A _regOut_PrioLCOFI_T = reg_PrioLCOFI & {8{mideleg_LCOFI}}
A rdata = {_regOut_Prio15_T, _regOut_Prio14_T, _regOut_PrioLCOFI_T, reg_PrioSGEI, 8'h0, reg_PrioVSEI, 16'h0}
M Iprio4Module_1 a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P i mideleg_SSI 1
P i mideleg_STI 1
P i mideleg_SEI 1
P i mideleg_LCOFI 1
P i mvien_SSIE 1
P i mvien_SEIE 1
P i mvien_LC14IE 1
P i mvien_LC15IE 1
P i mvien_LC16IE 1
P i mvien_LC17IE 1
P i mvien_LC18IE 1
P i mvien_LC19IE 1
P i mvien_LC20IE 1
P i mvien_LC21IE 1
P i mvien_LC22IE 1
P i mvien_LC23IE 1
P i mvien_LC24IE 1
P i mvien_LC25IE 1
P i mvien_LC26IE 1
P i mvien_LC27IE 1
P i mvien_LC28IE 1
P i mvien_LC29IE 1
P i mvien_LC30IE 1
P i mvien_LC31IE 1
P i mvien_LC32IE 1
P i mvien_LC33IE 1
P i mvien_LC34IE 1
P i mvien_LPRASEIE 1
P i mvien_LC36IE 1
P i mvien_LC37IE 1
P i mvien_LC38IE 1
P i mvien_LC39IE 1
P i mvien_LC40IE 1
P i mvien_LC41IE 1
P i mvien_LC42IE 1
P i mvien_HPRASEIE 1
P i mvien_LC44IE 1
P i mvien_LC45IE 1
P i mvien_LC46IE 1
P i mvien_LC47IE 1
P i mvien_LC48IE 1
P i mvien_LC49IE 1
P i mvien_LC50IE 1
P i mvien_LC51IE 1
P i mvien_LC52IE 1
P i mvien_LC53IE 1
P i mvien_LC54IE 1
P i mvien_LC55IE 1
P i mvien_LC56IE 1
P i mvien_LC57IE 1
P i mvien_LC58IE 1
P i mvien_LC59IE 1
P i mvien_LC60IE 1
P i mvien_LC61IE 1
P i mvien_LC62IE 1
P i mvien_LC63IE 1
F reg_ALL 64 0
S reg_ALL ? w_wen : w_wdata
A rdata = reg_ALL & {{8{mvien_LC23IE}}, {8{mvien_LC22IE}}, {8{mvien_LC21IE}}, {8{mvien_LC20IE}}, {8{mvien_LC19IE}}, {8{mvien_LC18IE}}, {8{mvien_LC17IE}}, {8{mvien_LC16IE}}}
M Iprio6Module_1 a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P i mideleg_SSI 1
P i mideleg_STI 1
P i mideleg_SEI 1
P i mideleg_LCOFI 1
P i mvien_SSIE 1
P i mvien_SEIE 1
P i mvien_LC14IE 1
P i mvien_LC15IE 1
P i mvien_LC16IE 1
P i mvien_LC17IE 1
P i mvien_LC18IE 1
P i mvien_LC19IE 1
P i mvien_LC20IE 1
P i mvien_LC21IE 1
P i mvien_LC22IE 1
P i mvien_LC23IE 1
P i mvien_LC24IE 1
P i mvien_LC25IE 1
P i mvien_LC26IE 1
P i mvien_LC27IE 1
P i mvien_LC28IE 1
P i mvien_LC29IE 1
P i mvien_LC30IE 1
P i mvien_LC31IE 1
P i mvien_LC32IE 1
P i mvien_LC33IE 1
P i mvien_LC34IE 1
P i mvien_LPRASEIE 1
P i mvien_LC36IE 1
P i mvien_LC37IE 1
P i mvien_LC38IE 1
P i mvien_LC39IE 1
P i mvien_LC40IE 1
P i mvien_LC41IE 1
P i mvien_LC42IE 1
P i mvien_HPRASEIE 1
P i mvien_LC44IE 1
P i mvien_LC45IE 1
P i mvien_LC46IE 1
P i mvien_LC47IE 1
P i mvien_LC48IE 1
P i mvien_LC49IE 1
P i mvien_LC50IE 1
P i mvien_LC51IE 1
P i mvien_LC52IE 1
P i mvien_LC53IE 1
P i mvien_LC54IE 1
P i mvien_LC55IE 1
P i mvien_LC56IE 1
P i mvien_LC57IE 1
P i mvien_LC58IE 1
P i mvien_LC59IE 1
P i mvien_LC60IE 1
P i mvien_LC61IE 1
P i mvien_LC62IE 1
P i mvien_LC63IE 1
F reg_ALL 64 0
S reg_ALL ? w_wen : w_wdata
A rdata = reg_ALL & {{8{mvien_LC31IE}}, {8{mvien_LC30IE}}, {8{mvien_LC29IE}}, {8{mvien_LC28IE}}, {8{mvien_LC27IE}}, {8{mvien_LC26IE}}, {8{mvien_LC25IE}}, {8{mvien_LC24IE}}}
M Iprio8Module_1 a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P i mideleg_SSI 1
P i mideleg_STI 1
P i mideleg_SEI 1
P i mideleg_LCOFI 1
P i mvien_SSIE 1
P i mvien_SEIE 1
P i mvien_LC14IE 1
P i mvien_LC15IE 1
P i mvien_LC16IE 1
P i mvien_LC17IE 1
P i mvien_LC18IE 1
P i mvien_LC19IE 1
P i mvien_LC20IE 1
P i mvien_LC21IE 1
P i mvien_LC22IE 1
P i mvien_LC23IE 1
P i mvien_LC24IE 1
P i mvien_LC25IE 1
P i mvien_LC26IE 1
P i mvien_LC27IE 1
P i mvien_LC28IE 1
P i mvien_LC29IE 1
P i mvien_LC30IE 1
P i mvien_LC31IE 1
P i mvien_LC32IE 1
P i mvien_LC33IE 1
P i mvien_LC34IE 1
P i mvien_LPRASEIE 1
P i mvien_LC36IE 1
P i mvien_LC37IE 1
P i mvien_LC38IE 1
P i mvien_LC39IE 1
P i mvien_LC40IE 1
P i mvien_LC41IE 1
P i mvien_LC42IE 1
P i mvien_HPRASEIE 1
P i mvien_LC44IE 1
P i mvien_LC45IE 1
P i mvien_LC46IE 1
P i mvien_LC47IE 1
P i mvien_LC48IE 1
P i mvien_LC49IE 1
P i mvien_LC50IE 1
P i mvien_LC51IE 1
P i mvien_LC52IE 1
P i mvien_LC53IE 1
P i mvien_LC54IE 1
P i mvien_LC55IE 1
P i mvien_LC56IE 1
P i mvien_LC57IE 1
P i mvien_LC58IE 1
P i mvien_LC59IE 1
P i mvien_LC60IE 1
P i mvien_LC61IE 1
P i mvien_LC62IE 1
P i mvien_LC63IE 1
F reg_ALL 64 0
S reg_ALL ? w_wen : w_wdata
A rdata = reg_ALL & {{8{mvien_LC39IE}}, {8{mvien_LC38IE}}, {8{mvien_LC37IE}}, {8{mvien_LC36IE}}, {8{mvien_LPRASEIE}}, {8{mvien_LC34IE}}, {8{mvien_LC33IE}}, {8{mvien_LC32IE}}}
M Iprio10Module_1 a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P i mideleg_SSI 1
P i mideleg_STI 1
P i mideleg_SEI 1
P i mideleg_LCOFI 1
P i mvien_SSIE 1
P i mvien_SEIE 1
P i mvien_LC14IE 1
P i mvien_LC15IE 1
P i mvien_LC16IE 1
P i mvien_LC17IE 1
P i mvien_LC18IE 1
P i mvien_LC19IE 1
P i mvien_LC20IE 1
P i mvien_LC21IE 1
P i mvien_LC22IE 1
P i mvien_LC23IE 1
P i mvien_LC24IE 1
P i mvien_LC25IE 1
P i mvien_LC26IE 1
P i mvien_LC27IE 1
P i mvien_LC28IE 1
P i mvien_LC29IE 1
P i mvien_LC30IE 1
P i mvien_LC31IE 1
P i mvien_LC32IE 1
P i mvien_LC33IE 1
P i mvien_LC34IE 1
P i mvien_LPRASEIE 1
P i mvien_LC36IE 1
P i mvien_LC37IE 1
P i mvien_LC38IE 1
P i mvien_LC39IE 1
P i mvien_LC40IE 1
P i mvien_LC41IE 1
P i mvien_LC42IE 1
P i mvien_HPRASEIE 1
P i mvien_LC44IE 1
P i mvien_LC45IE 1
P i mvien_LC46IE 1
P i mvien_LC47IE 1
P i mvien_LC48IE 1
P i mvien_LC49IE 1
P i mvien_LC50IE 1
P i mvien_LC51IE 1
P i mvien_LC52IE 1
P i mvien_LC53IE 1
P i mvien_LC54IE 1
P i mvien_LC55IE 1
P i mvien_LC56IE 1
P i mvien_LC57IE 1
P i mvien_LC58IE 1
P i mvien_LC59IE 1
P i mvien_LC60IE 1
P i mvien_LC61IE 1
P i mvien_LC62IE 1
P i mvien_LC63IE 1
F reg_ALL 64 0
S reg_ALL ? w_wen : w_wdata
A rdata = reg_ALL & {{8{mvien_LC47IE}}, {8{mvien_LC46IE}}, {8{mvien_LC45IE}}, {8{mvien_LC44IE}}, {8{mvien_HPRASEIE}}, {8{mvien_LC42IE}}, {8{mvien_LC41IE}}, {8{mvien_LC40IE}}}
M Iprio12Module_1 a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P i mideleg_SSI 1
P i mideleg_STI 1
P i mideleg_SEI 1
P i mideleg_LCOFI 1
P i mvien_SSIE 1
P i mvien_SEIE 1
P i mvien_LC14IE 1
P i mvien_LC15IE 1
P i mvien_LC16IE 1
P i mvien_LC17IE 1
P i mvien_LC18IE 1
P i mvien_LC19IE 1
P i mvien_LC20IE 1
P i mvien_LC21IE 1
P i mvien_LC22IE 1
P i mvien_LC23IE 1
P i mvien_LC24IE 1
P i mvien_LC25IE 1
P i mvien_LC26IE 1
P i mvien_LC27IE 1
P i mvien_LC28IE 1
P i mvien_LC29IE 1
P i mvien_LC30IE 1
P i mvien_LC31IE 1
P i mvien_LC32IE 1
P i mvien_LC33IE 1
P i mvien_LC34IE 1
P i mvien_LPRASEIE 1
P i mvien_LC36IE 1
P i mvien_LC37IE 1
P i mvien_LC38IE 1
P i mvien_LC39IE 1
P i mvien_LC40IE 1
P i mvien_LC41IE 1
P i mvien_LC42IE 1
P i mvien_HPRASEIE 1
P i mvien_LC44IE 1
P i mvien_LC45IE 1
P i mvien_LC46IE 1
P i mvien_LC47IE 1
P i mvien_LC48IE 1
P i mvien_LC49IE 1
P i mvien_LC50IE 1
P i mvien_LC51IE 1
P i mvien_LC52IE 1
P i mvien_LC53IE 1
P i mvien_LC54IE 1
P i mvien_LC55IE 1
P i mvien_LC56IE 1
P i mvien_LC57IE 1
P i mvien_LC58IE 1
P i mvien_LC59IE 1
P i mvien_LC60IE 1
P i mvien_LC61IE 1
P i mvien_LC62IE 1
P i mvien_LC63IE 1
F reg_ALL 64 0
S reg_ALL ? w_wen : w_wdata
A rdata = reg_ALL & {{8{mvien_LC55IE}}, {8{mvien_LC54IE}}, {8{mvien_LC53IE}}, {8{mvien_LC52IE}}, {8{mvien_LC51IE}}, {8{mvien_LC50IE}}, {8{mvien_LC49IE}}, {8{mvien_LC48IE}}}
M Iprio14Module_1 a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P i mideleg_SSI 1
P i mideleg_STI 1
P i mideleg_SEI 1
P i mideleg_LCOFI 1
P i mvien_SSIE 1
P i mvien_SEIE 1
P i mvien_LC14IE 1
P i mvien_LC15IE 1
P i mvien_LC16IE 1
P i mvien_LC17IE 1
P i mvien_LC18IE 1
P i mvien_LC19IE 1
P i mvien_LC20IE 1
P i mvien_LC21IE 1
P i mvien_LC22IE 1
P i mvien_LC23IE 1
P i mvien_LC24IE 1
P i mvien_LC25IE 1
P i mvien_LC26IE 1
P i mvien_LC27IE 1
P i mvien_LC28IE 1
P i mvien_LC29IE 1
P i mvien_LC30IE 1
P i mvien_LC31IE 1
P i mvien_LC32IE 1
P i mvien_LC33IE 1
P i mvien_LC34IE 1
P i mvien_LPRASEIE 1
P i mvien_LC36IE 1
P i mvien_LC37IE 1
P i mvien_LC38IE 1
P i mvien_LC39IE 1
P i mvien_LC40IE 1
P i mvien_LC41IE 1
P i mvien_LC42IE 1
P i mvien_HPRASEIE 1
P i mvien_LC44IE 1
P i mvien_LC45IE 1
P i mvien_LC46IE 1
P i mvien_LC47IE 1
P i mvien_LC48IE 1
P i mvien_LC49IE 1
P i mvien_LC50IE 1
P i mvien_LC51IE 1
P i mvien_LC52IE 1
P i mvien_LC53IE 1
P i mvien_LC54IE 1
P i mvien_LC55IE 1
P i mvien_LC56IE 1
P i mvien_LC57IE 1
P i mvien_LC58IE 1
P i mvien_LC59IE 1
P i mvien_LC60IE 1
P i mvien_LC61IE 1
P i mvien_LC62IE 1
P i mvien_LC63IE 1
F reg_ALL 64 0
S reg_ALL ? w_wen : w_wdata
A rdata = reg_ALL & {{8{mvien_LC63IE}}, {8{mvien_LC62IE}}, {8{mvien_LC61IE}}, {8{mvien_LC60IE}}, {8{mvien_LC59IE}}, {8{mvien_LC58IE}}, {8{mvien_LC57IE}}, {8{mvien_LC56IE}}}
M TrapEntryDEventModule n
P i valid 1
P i in_trapPc 50
P i in_fetchMalTval 64
P i in_isFetchMalAddr 1
P i in_satpFlushFirstFetchFault 1
P i in_iMode_PRVM 2
P i in_iMode_V 1
P i in_privState_PRVM 2
P i in_privState_V 1
P i in_hgatp_MODE 4
P i in_oldSatp_MODE 4
P i in_oldVsatp_MODE 4
P i in_hasTrap 1
P i in_debugMode 1
P i in_hasDebugIntr 1
P i in_triggerEnterDebugMode 1
P i in_hasDebugEbreakException 1
P i in_hasSingleStep 1
P i in_breakPoint 1
P i in_criticalErrorStateEnterDebug 1
P i in_holdDpc 1
P o out_privState_valid 1
P o out_privState_bits_PRVM 2
P o out_privState_bits_V 1
P o out_dcsr_valid 1
P o out_dcsr_bits_DEBUGVER 4
P o out_dcsr_bits_EXTCAUSE 3
P o out_dcsr_bits_CETRIG 1
P o out_dcsr_bits_EBREAKVS 1
P o out_dcsr_bits_EBREAKVU 1
P o out_dcsr_bits_EBREAKM 1
P o out_dcsr_bits_EBREAKS 1
P o out_dcsr_bits_EBREAKU 1
P o out_dcsr_bits_STEPIE 1
P o out_dcsr_bits_STOPCOUNT 1
P o out_dcsr_bits_STOPTIME 1
P o out_dcsr_bits_CAUSE 3
P o out_dcsr_bits_V 1
P o out_dcsr_bits_MPRVEN 1
P o out_dcsr_bits_NMIP 1
P o out_dcsr_bits_STEP 1
P o out_dcsr_bits_PRV 2
P o out_dpc_valid 1
P o out_dpc_bits_epc 63
P o out_targetPc_valid 1
P o out_targetPc_bits_pc 64
P o out_targetPc_bits_raiseIPF 1
P o out_targetPc_bits_raiseIAF 1
P o out_targetPc_bits_raiseIGPF 1
P o out_debugMode_valid 1
P o out_debugMode_bits 1
P o out_debugIntrEnable_valid 1
P o out_debugIntrEnable_bits 1
W hasExceptionInDmode 1 = in_debugMode & in_hasTrap
W trapPC_isBare_v_PrvmIsM 1 = &in_iMode_PRVM
W trapPC_isBare_isModeM 1 = trapPC_isBare_v_PrvmIsM
W trapPC_isBare_PrvmIsU 1 = in_iMode_PRVM == 2'h0
W trapPC_isBare_PrvmIsS 1 = in_iMode_PRVM == 2'h1
W _trapPC_isSv48_T 1 = trapPC_isBare_PrvmIsU | trapPC_isBare_PrvmIsS
W _trapPC_isSv48x4_T_2 1 = in_oldVsatp_MODE == 4'h0
A out_privState_valid = valid
A out_privState_bits_PRVM = 2'h3
A out_privState_bits_V = 1'h0
A out_dcsr_valid = valid
A out_dcsr_bits_DEBUGVER = 4'h0
A out_dcsr_bits_EXTCAUSE = 3'h0
A out_dcsr_bits_CETRIG = 1'h0
A out_dcsr_bits_EBREAKVS = 1'h0
A out_dcsr_bits_EBREAKVU = 1'h0
A out_dcsr_bits_EBREAKM = 1'h0
A out_dcsr_bits_EBREAKS = 1'h0
A out_dcsr_bits_EBREAKU = 1'h0
A out_dcsr_bits_STEPIE = 1'h0
A out_dcsr_bits_STOPCOUNT = 1'h0
A out_dcsr_bits_STOPTIME = 1'h0
A out_dcsr_bits_CAUSE = in_criticalErrorStateEnterDebug ? 3'h7 : in_hasDebugIntr ? 3'h3 : in_triggerEnterDebugMode ? 3'h2 : in_hasDebugEbreakException ? 3'h1 : {in_hasSingleStep, 2'h0}
A out_dcsr_bits_V = in_privState_V
A out_dcsr_bits_MPRVEN = 1'h0
A out_dcsr_bits_NMIP = 1'h0
A out_dcsr_bits_STEP = 1'h0
A out_dcsr_bits_PRV = in_privState_PRVM
A out_dpc_valid = valid & ~in_holdDpc
A out_dpc_bits_epc = in_satpFlushFirstFetchFault | ~in_isFetchMalAddr ? (trapPC_isBare_isModeM | _trapPC_isSv48_T & ~in_iMode_V & in_oldSatp_MODE == 4'h0 | in_iMode_V & _trapPC_isSv48x4_T_2 & in_hgatp_MODE == 4'h0 ? {16'h0, in_trapPc[47:1]} : 63'h0) | (_trapPC_isSv48_T & ~in_iMode_V & in_oldSatp_MODE == 4'h8 | in_iMode_V & in_oldVsatp_MODE == 4'h8 ? {{25{in_trapPc[38]}}, in_trapPc[38:1]} : 63'h0) | (in_iMode_V & _trapPC_isSv48x4_T_2 & in_hgatp_MODE == 4'h8 ? {23'h0, in_trapPc[40:1]} : 63'h0) | (_trapPC_isSv48_T & ~in_iMode_V & in_oldSatp_MODE == 4'h9 | in_iMode_V & in_oldVsatp_MODE == 4'h9 ? {{16{in_trapPc[47]}}, in_trapPc[47:1]} : 63'h0) | (in_iMode_V & _trapPC_isSv48x4_T_2 & in_hgatp_MODE == 4'h9 ? {14'h0, in_trapPc[49:1]} : 63'h0) : in_fetchMalTval[63:1]
A out_targetPc_valid = valid | hasExceptionInDmode
A out_targetPc_bits_pc = {60'h3802080, hasExceptionInDmode & ~in_breakPoint, 3'h0}
A out_targetPc_bits_raiseIPF = 1'h0
A out_targetPc_bits_raiseIAF = 1'h0
A out_targetPc_bits_raiseIGPF = 1'h0
A out_debugMode_valid = valid
A out_debugMode_bits = 1'h1
A out_debugIntrEnable_valid = valid
A out_debugIntrEnable_bits = 1'h0
M TrapEntryMEventModule n
P i valid 1
P i in_causeNO_Interrupt 1
P i in_causeNO_ExceptionCode 63
P i in_trapPc 50
P i in_trapPcGPA 56
P i in_trapInst_valid 1
P i in_trapInst_bits 32
P i in_fetchMalTval 64
P i in_isCrossPageIPF 1
P i in_isHls 1
P i in_isFetchMalAddr 1
P i in_satpFlushFirstFetchFault 1
P i in_isFetchBkpt 1
P i in_trapIsForVSnonLeafPTE 1
P i in_hasDTExcp 1
P i in_iMode_PRVM 2
P i in_iMode_V 1
P i in_dMode_V 1
P i in_privState_PRVM 2
P i in_privState_V 1
P i in_mstatus_MIE 1
P i in_pcFromXtvec 64
P i in_hgatp_MODE 4
P i in_oldSatp_MODE 4
P i in_oldVsatp_MODE 4
P i in_memExceptionVAddr 64
P i in_memExceptionGPAddr 64
P i in_memExceptionIsForVSnonLeafPTE 1
P o out_privState_valid 1
P o out_privState_bits_PRVM 2
P o out_privState_bits_V 1
P o out_mstatus_valid 1
P o out_mstatus_bits_SIE 1
P o out_mstatus_bits_MIE 1
P o out_mstatus_bits_SPIE 1
P o out_mstatus_bits_UBE 1
P o out_mstatus_bits_MPIE 1
P o out_mstatus_bits_SPP 1
P o out_mstatus_bits_VS 2
P o out_mstatus_bits_MPP 2
P o out_mstatus_bits_FS 2
P o out_mstatus_bits_XS 2
P o out_mstatus_bits_MPRV 1
P o out_mstatus_bits_SUM 1
P o out_mstatus_bits_MXR 1
P o out_mstatus_bits_TVM 1
P o out_mstatus_bits_TW 1
P o out_mstatus_bits_TSR 1
P o out_mstatus_bits_SDT 1
P o out_mstatus_bits_UXL 2
P o out_mstatus_bits_SXL 2
P o out_mstatus_bits_SBE 1
P o out_mstatus_bits_MBE 1
P o out_mstatus_bits_GVA 1
P o out_mstatus_bits_MPV 1
P o out_mstatus_bits_MDT 1
P o out_mstatus_bits_SD 1
P o out_mepc_valid 1
P o out_mepc_bits_epc 63
P o out_mcause_valid 1
P o out_mcause_bits_Interrupt 1
P o out_mcause_bits_ExceptionCode 63
P o out_mtval_valid 1
P o out_mtval_bits_ALL 64
P o out_mtval2_valid 1
P o out_mtval2_bits_ALL 64
P o out_mtinst_valid 1
P o out_mtinst_bits_ALL 64
P o out_targetPc_valid 1
P o out_targetPc_bits_pc 64
P o out_targetPc_bits_raiseIPF 1
P o out_targetPc_bits_raiseIAF 1
P o out_targetPc_bits_raiseIGPF 1
W trapPC_isBare_v_PrvmIsM 1 = &in_iMode_PRVM
W trapPC_isBare_isModeM 1 = trapPC_isBare_v_PrvmIsM
W trapPC_isBare_PrvmIsU 1 = in_iMode_PRVM == 2'h0
W trapPC_isBare_PrvmIsS 1 = in_iMode_PRVM == 2'h1
W _trapPCGPAFromSatpFlush_isSv48_T 1 = trapPC_isBare_PrvmIsU | trapPC_isBare_PrvmIsS
W _trapPCGPAFromSatpFlush_isBare_T_5 1 = in_oldSatp_MODE == 4'h0
W _trapPCGPAFromSatpFlush_isSv48x4_T_2 1 = in_oldVsatp_MODE == 4'h0
W _trapPCGPAFromSatpFlush_isBare_T_12 1 = in_hgatp_MODE == 4'h0
W _trapPCGPAFromSatpFlush_isSv39_T_5 1 = in_oldSatp_MODE == 4'h8
W _trapPCGPAFromSatpFlush_isSv39_T_9 1 = in_oldVsatp_MODE == 4'h8
W _trapPCGPAFromSatpFlush_isSv48_T_5 1 = in_oldSatp_MODE == 4'h9
W _trapPCGPAFromSatpFlush_isSv48_T_9 1 = in_oldVsatp_MODE == 4'h9
W _trapPCGPAFromSatpFlush_isSv39x4_T_4 1 = in_hgatp_MODE == 4'h8
W _trapPCGPAFromSatpFlush_isSv48x4_T_4 1 = in_hgatp_MODE == 4'h9
W trapPC 64 = (trapPC_isBare_isModeM | _trapPCGPAFromSatpFlush_isSv48_T & ~in_iMode_V & _trapPCGPAFromSatpFlush_isBare_T_5 | in_iMode_V & _trapPCGPAFromSatpFlush_isSv48x4_T_2 & _trapPCGPAFromSatpFlush_isBare_T_12 ? {16'h0, in_trapPc[47:0]} : 64'h0) | (_trapPCGPAFromSatpFlush_isSv48_T & ~in_iMode_V & _trapPCGPAFromSatpFlush_isSv39_T_5 | in_iMode_V & _trapPCGPAFromSatpFlush_isSv39_T_9 ? {{25{in_trapPc[38]}}, in_trapPc[38:0]} : 64'h0) | (in_iMode_V & _trapPCGPAFromSatpFlush_isSv48x4_T_2 & _trapPCGPAFromSatpFlush_isSv39x4_T_4 ? {23'h0, in_trapPc[40:0]} : 64'h0) | (_trapPCGPAFromSatpFlush_isSv48_T & ~in_iMode_V & _trapPCGPAFromSatpFlush_isSv48_T_5 | in_iMode_V & _trapPCGPAFromSatpFlush_isSv48_T_9 ? {{16{in_trapPc[47]}}, in_trapPc[47:0]} : 64'h0) | (in_iMode_V & _trapPCGPAFromSatpFlush_isSv48x4_T_2 & _trapPCGPAFromSatpFlush_isSv48x4_T_4 ? {14'h0, in_trapPc} : 64'h0)
W trapPCGPAFromSatpFlush 64 = (trapPC_isBare_isModeM | _trapPCGPAFromSatpFlush_isSv48_T & ~in_iMode_V & _trapPCGPAFromSatpFlush_isBare_T_5 | in_iMode_V & _trapPCGPAFromSatpFlush_isSv48x4_T_2 & _trapPCGPAFromSatpFlush_isBare_T_12 ? {16'h0, in_trapPcGPA[47:0]} : 64'h0) | (_trapPCGPAFromSatpFlush_isSv48_T & ~in_iMode_V & _trapPCGPAFromSatpFlush_isSv39_T_5 | in_iMode_V & _trapPCGPAFromSatpFlush_isSv39_T_9 ? {{25{in_trapPcGPA[38]}}, in_trapPcGPA[38:0]} : 64'h0) | (in_iMode_V & _trapPCGPAFromSatpFlush_isSv48x4_T_2 & _trapPCGPAFromSatpFlush_isSv39x4_T_4 ? {23'h0, in_trapPcGPA[40:0]} : 64'h0) | (_trapPCGPAFromSatpFlush_isSv48_T & ~in_iMode_V & _trapPCGPAFromSatpFlush_isSv48_T_5 | in_iMode_V & _trapPCGPAFromSatpFlush_isSv48_T_9 ? {{16{in_trapPcGPA[47]}}, in_trapPcGPA[47:0]} : 64'h0) | (in_iMode_V & _trapPCGPAFromSatpFlush_isSv48x4_T_2 & _trapPCGPAFromSatpFlush_isSv48x4_T_4 ? {14'h0, in_trapPcGPA[49:0]} : 64'h0)
W isFetchExcp 1 = ~in_causeNO_Interrupt & (in_causeNO_ExceptionCode == 63'h0 | in_causeNO_ExceptionCode == 63'h1 | in_causeNO_ExceptionCode == 63'hC)
W isBpExcp 1 = ~in_causeNO_Interrupt & in_causeNO_ExceptionCode == 63'h3
W isFetchBkpt 1 = isBpExcp & in_isFetchBkpt
W isLSGuestExcp 1 = ~in_causeNO_Interrupt & (in_causeNO_ExceptionCode == 63'h15 | in_causeNO_ExceptionCode == 63'h17)
W isFetchGuestExcp 1 = ~in_causeNO_Interrupt & in_causeNO_ExceptionCode == 63'h14
W _tvalFillPcPlus2_T 1 = isFetchExcp | isFetchGuestExcp
W tvalFillMemVaddr 1 = ~in_causeNO_Interrupt & (in_causeNO_ExceptionCode == 63'h4 | in_causeNO_ExceptionCode == 63'h5 | in_causeNO_ExceptionCode == 63'hD | in_causeNO_ExceptionCode == 63'h13 | in_causeNO_ExceptionCode == 63'h6 | in_causeNO_ExceptionCode == 63'h7 | in_causeNO_ExceptionCode == 63'hF) | isBpExcp & ~in_isFetchBkpt
W tvalFillGVA 1 = isLSGuestExcp | isFetchGuestExcp | (isFetchExcp | isFetchBkpt) & in_iMode_V | tvalFillMemVaddr & (in_dMode_V | ~in_causeNO_Interrupt & in_isHls)
W _tval_T_8 64 = (_tvalFillPcPlus2_T & ~in_isCrossPageIPF | isFetchBkpt ? trapPC : 64'h0) | (_tvalFillPcPlus2_T & in_isCrossPageIPF ? trapPC + 64'h2 : 64'h0) | (tvalFillMemVaddr | isLSGuestExcp ? in_memExceptionVAddr : 64'h0)
W _tval2FromSatpFlush_T 1 = isFetchGuestExcp & in_isFetchMalAddr
W _tval2_T_8 56 = in_trapPcGPA + 56'h2
W _tval2_T_10 62 = _tval2FromSatpFlush_T ? in_fetchMalTval[63:2] : 62'h0
W _tval2FromSatpFlush_T_13 62 = isLSGuestExcp ? in_memExceptionGPAddr[63:2] : 62'h0
W _tval2FromSatpFlush_T_8 64 = trapPCGPAFromSatpFlush + 64'h2
A out_privState_valid = valid
A out_privState_bits_PRVM = 2'h3
A out_privState_bits_V = 1'h0
A out_mstatus_valid = valid
A out_mstatus_bits_SIE = 1'h0
A out_mstatus_bits_MIE = 1'h0
A out_mstatus_bits_SPIE = 1'h0
A out_mstatus_bits_UBE = 1'h0
A out_mstatus_bits_MPIE = in_mstatus_MIE
A out_mstatus_bits_SPP = 1'h0
A out_mstatus_bits_VS = 2'h0
A out_mstatus_bits_MPP = in_privState_PRVM
A out_mstatus_bits_FS = 2'h0
A out_mstatus_bits_XS = 2'h0
A out_mstatus_bits_MPRV = 1'h0
A out_mstatus_bits_SUM = 1'h0
A out_mstatus_bits_MXR = 1'h0
A out_mstatus_bits_TVM = 1'h0
A out_mstatus_bits_TW = 1'h0
A out_mstatus_bits_TSR = 1'h0
A out_mstatus_bits_SDT = 1'h0
A out_mstatus_bits_UXL = 2'h0
A out_mstatus_bits_SXL = 2'h0
A out_mstatus_bits_SBE = 1'h0
A out_mstatus_bits_MBE = 1'h0
A out_mstatus_bits_GVA = tvalFillGVA
A out_mstatus_bits_MPV = in_privState_V
A out_mstatus_bits_MDT = 1'h1
A out_mstatus_bits_SD = 1'h0
A out_mepc_valid = valid
A out_mepc_bits_epc = in_satpFlushFirstFetchFault | ~in_isFetchMalAddr ? trapPC[63:1] : in_fetchMalTval[63:1]
A out_mcause_valid = valid
A out_mcause_bits_Interrupt = in_causeNO_Interrupt & ~in_hasDTExcp
A out_mcause_bits_ExceptionCode = in_hasDTExcp ? 63'h10 : in_causeNO_ExceptionCode
A out_mtval_valid = valid
A out_mtval_bits_ALL = in_satpFlushFirstFetchFault | ~(~in_causeNO_Interrupt & in_isFetchMalAddr) ? {_tval_T_8[63:32], _tval_T_8[31:0] | (~in_causeNO_Interrupt & (in_causeNO_ExceptionCode == 63'h2 | in_causeNO_ExceptionCode == 63'h16) & in_trapInst_valid ? in_trapInst_bits : 32'h0)} : in_fetchMalTval
A out_mtval2_valid = valid
A out_mtval2_bits_ALL = in_hasDTExcp ? {in_causeNO_Interrupt, in_causeNO_ExceptionCode} : {2'h0, in_satpFlushFirstFetchFault ? (_tval2FromSatpFlush_T ? in_fetchMalTval[63:2] : 62'h0) | (isFetchGuestExcp & ~in_isFetchMalAddr & ~in_isCrossPageIPF ? trapPCGPAFromSatpFlush[63:2] : 62'h0) | (isFetchGuestExcp & ~in_isFetchMalAddr & in_isCrossPageIPF ? _tval2FromSatpFlush_T_8[63:2] : 62'h0) | _tval2FromSatpFlush_T_13 : {_tval2_T_10[61:54], _tval2_T_10[53:0] | (isFetchGuestExcp & ~in_isFetchMalAddr & ~in_isCrossPageIPF ? in_trapPcGPA[55:2] : 54'h0) | (isFetchGuestExcp & ~in_isFetchMalAddr & in_isCrossPageIPF ? _tval2_T_8[55:2] : 54'h0)} | _tval2FromSatpFlush_T_13}
A out_mtinst_valid = valid
A out_mtinst_bits_ALL = {50'h0, isFetchGuestExcp & in_trapIsForVSnonLeafPTE | isLSGuestExcp & in_memExceptionIsForVSnonLeafPTE ? 14'h3000 : 14'h0}
A out_targetPc_valid = valid
A out_targetPc_bits_pc = in_pcFromXtvec
A out_targetPc_bits_raiseIPF = 1'h0
A out_targetPc_bits_raiseIAF = |(in_pcFromXtvec[63:48])
A out_targetPc_bits_raiseIGPF = 1'h0
M TrapEntryMNEventModule n
P i valid 1
P i in_causeNO_Interrupt 1
P i in_causeNO_ExceptionCode 63
P i in_trapPc 50
P i in_fetchMalTval 64
P i in_isFetchMalAddr 1
P i in_satpFlushFirstFetchFault 1
P i in_iMode_PRVM 2
P i in_iMode_V 1
P i in_privState_PRVM 2
P i in_privState_V 1
P i in_pcFromXtvec 64
P i in_hgatp_MODE 4
P i in_oldSatp_MODE 4
P i in_oldVsatp_MODE 4
P o out_privState_valid 1
P o out_privState_bits_PRVM 2
P o out_privState_bits_V 1
P o out_mnstatus_valid 1
P o out_mnstatus_bits_NMIE 1
P o out_mnstatus_bits_MNPV 1
P o out_mnstatus_bits_MNPELP 1
P o out_mnstatus_bits_MNPP 2
P o out_mnepc_valid 1
P o out_mnepc_bits_epc 63
P o out_mncause_valid 1
P o out_mncause_bits_Interrupt 1
P o out_mncause_bits_ExceptionCode 63
P o out_targetPc_valid 1
P o out_targetPc_bits_pc 64
P o out_targetPc_bits_raiseIPF 1
P o out_targetPc_bits_raiseIAF 1
P o out_targetPc_bits_raiseIGPF 1
W trapPC_isBare_v_PrvmIsM 1 = &in_iMode_PRVM
W trapPC_isBare_isModeM 1 = trapPC_isBare_v_PrvmIsM
W trapPC_isBare_PrvmIsU 1 = in_iMode_PRVM == 2'h0
W trapPC_isBare_PrvmIsS 1 = in_iMode_PRVM == 2'h1
W _trapPC_isSv48_T 1 = trapPC_isBare_PrvmIsU | trapPC_isBare_PrvmIsS
W _trapPC_isSv48x4_T_2 1 = in_oldVsatp_MODE == 4'h0
A out_privState_valid = valid
A out_privState_bits_PRVM = 2'h3
A out_privState_bits_V = 1'h0
A out_mnstatus_valid = valid
A out_mnstatus_bits_NMIE = 1'h0
A out_mnstatus_bits_MNPV = in_privState_V
A out_mnstatus_bits_MNPELP = 1'h0
A out_mnstatus_bits_MNPP = in_privState_PRVM
A out_mnepc_valid = valid
A out_mnepc_bits_epc = in_satpFlushFirstFetchFault | ~in_isFetchMalAddr ? (trapPC_isBare_isModeM | _trapPC_isSv48_T & ~in_iMode_V & in_oldSatp_MODE == 4'h0 | in_iMode_V & _trapPC_isSv48x4_T_2 & in_hgatp_MODE == 4'h0 ? {16'h0, in_trapPc[47:1]} : 63'h0) | (_trapPC_isSv48_T & ~in_iMode_V & in_oldSatp_MODE == 4'h8 | in_iMode_V & in_oldVsatp_MODE == 4'h8 ? {{25{in_trapPc[38]}}, in_trapPc[38:1]} : 63'h0) | (in_iMode_V & _trapPC_isSv48x4_T_2 & in_hgatp_MODE == 4'h8 ? {23'h0, in_trapPc[40:1]} : 63'h0) | (_trapPC_isSv48_T & ~in_iMode_V & in_oldSatp_MODE == 4'h9 | in_iMode_V & in_oldVsatp_MODE == 4'h9 ? {{16{in_trapPc[47]}}, in_trapPc[47:1]} : 63'h0) | (in_iMode_V & _trapPC_isSv48x4_T_2 & in_hgatp_MODE == 4'h9 ? {14'h0, in_trapPc[49:1]} : 63'h0) : in_fetchMalTval[63:1]
A out_mncause_valid = valid
A out_mncause_bits_Interrupt = in_causeNO_Interrupt
A out_mncause_bits_ExceptionCode = in_causeNO_ExceptionCode
A out_targetPc_valid = valid
A out_targetPc_bits_pc = in_pcFromXtvec
A out_targetPc_bits_raiseIPF = 1'h0
A out_targetPc_bits_raiseIAF = |(in_pcFromXtvec[63:48])
A out_targetPc_bits_raiseIGPF = 1'h0
M TrapEntryHSEventModule n
P i valid 1
P i in_causeNO_Interrupt 1
P i in_causeNO_ExceptionCode 63
P i in_trapPc 50
P i in_trapPcGPA 56
P i in_trapInst_valid 1
P i in_trapInst_bits 32
P i in_fetchMalTval 64
P i in_isCrossPageIPF 1
P i in_isHls 1
P i in_isFetchMalAddr 1
P i in_satpFlushFirstFetchFault 1
P i in_isFetchBkpt 1
P i in_trapIsForVSnonLeafPTE 1
P i in_iMode_PRVM 2
P i in_iMode_V 1
P i in_dMode_V 1
P i in_privState_PRVM 2
P i in_privState_V 1
P i in_hstatus_SPVP 1
P i in_sstatus_SIE 1
P i in_menvcfg_DTE 1
P i in_pcFromXtvec 64
P i in_satp_MODE 4
P i in_hgatp_MODE 4
P i in_oldSatp_MODE 4
P i in_oldVsatp_MODE 4
P i in_memExceptionVAddr 64
P i in_memExceptionGPAddr 64
P i in_memExceptionIsForVSnonLeafPTE 1
P o out_privState_valid 1
P o out_privState_bits_PRVM 2
P o out_privState_bits_V 1
P o out_mstatus_valid 1
P o out_mstatus_bits_SIE 1
P o out_mstatus_bits_MIE 1
P o out_mstatus_bits_SPIE 1
P o out_mstatus_bits_UBE 1
P o out_mstatus_bits_MPIE 1
P o out_mstatus_bits_SPP 1
P o out_mstatus_bits_VS 2
P o out_mstatus_bits_MPP 2
P o out_mstatus_bits_FS 2
P o out_mstatus_bits_XS 2
P o out_mstatus_bits_MPRV 1
P o out_mstatus_bits_SUM 1
P o out_mstatus_bits_MXR 1
P o out_mstatus_bits_TVM 1
P o out_mstatus_bits_TW 1
P o out_mstatus_bits_TSR 1
P o out_mstatus_bits_SDT 1
P o out_mstatus_bits_UXL 2
P o out_mstatus_bits_SXL 2
P o out_mstatus_bits_SBE 1
P o out_mstatus_bits_MBE 1
P o out_mstatus_bits_GVA 1
P o out_mstatus_bits_MPV 1
P o out_mstatus_bits_MDT 1
P o out_mstatus_bits_SD 1
P o out_hstatus_valid 1
P o out_hstatus_bits_VSBE 1
P o out_hstatus_bits_GVA 1
P o out_hstatus_bits_SPV 1
P o out_hstatus_bits_SPVP 1
P o out_hstatus_bits_HU 1
P o out_hstatus_bits_VGEIN 6
P o out_hstatus_bits_VTVM 1
P o out_hstatus_bits_VTW 1
P o out_hstatus_bits_VTSR 1
P o out_hstatus_bits_VSXL 2
P o out_hstatus_bits_HUPMM 2
P o out_sepc_valid 1
P o out_sepc_bits_epc 63
P o out_scause_valid 1
P o out_scause_bits_Interrupt 1
P o out_scause_bits_ExceptionCode 63
P o out_stval_valid 1
P o out_stval_bits_ALL 64
P o out_htval_valid 1
P o out_htval_bits_ALL 64
P o out_htinst_valid 1
P o out_htinst_bits_ALL 64
P o out_targetPc_valid 1
P o out_targetPc_bits_pc 64
P o out_targetPc_bits_raiseIPF 1
P o out_targetPc_bits_raiseIAF 1
P o out_targetPc_bits_raiseIGPF 1
W trapPC_isBare_v_PrvmIsM 1 = &in_iMode_PRVM
W trapPC_isBare_isModeM 1 = trapPC_isBare_v_PrvmIsM
W trapPC_isBare_PrvmIsU 1 = in_iMode_PRVM == 2'h0
W trapPC_isBare_PrvmIsS 1 = in_iMode_PRVM == 2'h1
W _trapPCGPAFromSatpFlush_isSv48_T 1 = trapPC_isBare_PrvmIsU | trapPC_isBare_PrvmIsS
W _trapPCGPAFromSatpFlush_isBare_T_5 1 = in_oldSatp_MODE == 4'h0
W _trapPCGPAFromSatpFlush_isSv48x4_T_2 1 = in_oldVsatp_MODE == 4'h0
W _trapPCGPAFromSatpFlush_isBare_T_12 1 = in_hgatp_MODE == 4'h0
W _trapPCGPAFromSatpFlush_isSv39_T_5 1 = in_oldSatp_MODE == 4'h8
W _trapPCGPAFromSatpFlush_isSv39_T_9 1 = in_oldVsatp_MODE == 4'h8
W _trapPCGPAFromSatpFlush_isSv48_T_5 1 = in_oldSatp_MODE == 4'h9
W _trapPCGPAFromSatpFlush_isSv48_T_9 1 = in_oldVsatp_MODE == 4'h9
W _trapPCGPAFromSatpFlush_isSv39x4_T_4 1 = in_hgatp_MODE == 4'h8
W _trapPCGPAFromSatpFlush_isSv48x4_T_4 1 = in_hgatp_MODE == 4'h9
W trapPC 64 = (trapPC_isBare_isModeM | _trapPCGPAFromSatpFlush_isSv48_T & ~in_iMode_V & _trapPCGPAFromSatpFlush_isBare_T_5 | in_iMode_V & _trapPCGPAFromSatpFlush_isSv48x4_T_2 & _trapPCGPAFromSatpFlush_isBare_T_12 ? {16'h0, in_trapPc[47:0]} : 64'h0) | (_trapPCGPAFromSatpFlush_isSv48_T & ~in_iMode_V & _trapPCGPAFromSatpFlush_isSv39_T_5 | in_iMode_V & _trapPCGPAFromSatpFlush_isSv39_T_9 ? {{25{in_trapPc[38]}}, in_trapPc[38:0]} : 64'h0) | (in_iMode_V & _trapPCGPAFromSatpFlush_isSv48x4_T_2 & _trapPCGPAFromSatpFlush_isSv39x4_T_4 ? {23'h0, in_trapPc[40:0]} : 64'h0) | (_trapPCGPAFromSatpFlush_isSv48_T & ~in_iMode_V & _trapPCGPAFromSatpFlush_isSv48_T_5 | in_iMode_V & _trapPCGPAFromSatpFlush_isSv48_T_9 ? {{16{in_trapPc[47]}}, in_trapPc[47:0]} : 64'h0) | (in_iMode_V & _trapPCGPAFromSatpFlush_isSv48x4_T_2 & _trapPCGPAFromSatpFlush_isSv48x4_T_4 ? {14'h0, in_trapPc} : 64'h0)
W trapPCGPAFromSatpFlush 64 = (trapPC_isBare_isModeM | _trapPCGPAFromSatpFlush_isSv48_T & ~in_iMode_V & _trapPCGPAFromSatpFlush_isBare_T_5 | in_iMode_V & _trapPCGPAFromSatpFlush_isSv48x4_T_2 & _trapPCGPAFromSatpFlush_isBare_T_12 ? {16'h0, in_trapPcGPA[47:0]} : 64'h0) | (_trapPCGPAFromSatpFlush_isSv48_T & ~in_iMode_V & _trapPCGPAFromSatpFlush_isSv39_T_5 | in_iMode_V & _trapPCGPAFromSatpFlush_isSv39_T_9 ? {{25{in_trapPcGPA[38]}}, in_trapPcGPA[38:0]} : 64'h0) | (in_iMode_V & _trapPCGPAFromSatpFlush_isSv48x4_T_2 & _trapPCGPAFromSatpFlush_isSv39x4_T_4 ? {23'h0, in_trapPcGPA[40:0]} : 64'h0) | (_trapPCGPAFromSatpFlush_isSv48_T & ~in_iMode_V & _trapPCGPAFromSatpFlush_isSv48_T_5 | in_iMode_V & _trapPCGPAFromSatpFlush_isSv48_T_9 ? {{16{in_trapPcGPA[47]}}, in_trapPcGPA[47:0]} : 64'h0) | (in_iMode_V & _trapPCGPAFromSatpFlush_isSv48x4_T_2 & _trapPCGPAFromSatpFlush_isSv48x4_T_4 ? {14'h0, in_trapPcGPA[49:0]} : 64'h0)
W isFetchExcp 1 = ~in_causeNO_Interrupt & (in_causeNO_ExceptionCode == 63'h0 | in_causeNO_ExceptionCode == 63'h1 | in_causeNO_ExceptionCode == 63'hC)
W isBpExcp 1 = ~in_causeNO_Interrupt & in_causeNO_ExceptionCode == 63'h3
W isFetchBkpt 1 = isBpExcp & in_isFetchBkpt
W isLSGuestExcp 1 = ~in_causeNO_Interrupt & (in_causeNO_ExceptionCode == 63'h15 | in_causeNO_ExceptionCode == 63'h17)
W isFetchGuestExcp 1 = ~in_causeNO_Interrupt & in_causeNO_ExceptionCode == 63'h14
W _tvalFillPcPlus2_T 1 = isFetchExcp | isFetchGuestExcp
W tvalFillMemVaddr 1 = ~in_causeNO_Interrupt & (in_causeNO_ExceptionCode == 63'h4 | in_causeNO_ExceptionCode == 63'h5 | in_causeNO_ExceptionCode == 63'hD | in_causeNO_ExceptionCode == 63'h13 | in_causeNO_ExceptionCode == 63'h6 | in_causeNO_ExceptionCode == 63'h7 | in_causeNO_ExceptionCode == 63'hF) | isBpExcp & ~in_isFetchBkpt
W tvalFillGVA 1 = isLSGuestExcp | isFetchGuestExcp | (isFetchExcp | isFetchBkpt) & in_iMode_V | tvalFillMemVaddr & (in_dMode_V | ~in_causeNO_Interrupt & in_isHls)
W _tval_T_8 64 = (_tvalFillPcPlus2_T & ~in_isCrossPageIPF | isFetchBkpt ? trapPC : 64'h0) | (_tvalFillPcPlus2_T & in_isCrossPageIPF ? trapPC + 64'h2 : 64'h0) | (tvalFillMemVaddr | isLSGuestExcp ? in_memExceptionVAddr : 64'h0)
W _tval2FromSatpFlush_T 1 = isFetchGuestExcp & in_isFetchMalAddr
W _tval2_T_8 56 = in_trapPcGPA + 56'h2
W _tval2_T_10 62 = _tval2FromSatpFlush_T ? in_fetchMalTval[63:2] : 62'h0
W _tval2FromSatpFlush_T_13 62 = isLSGuestExcp ? in_memExceptionGPAddr[63:2] : 62'h0
W _tval2FromSatpFlush_T_8 64 = trapPCGPAFromSatpFlush + 64'h2
A out_privState_valid = valid
A out_privState_bits_PRVM = 2'h1
A out_privState_bits_V = 1'h0
A out_mstatus_valid = valid
A out_mstatus_bits_SIE = 1'h0
A out_mstatus_bits_MIE = 1'h0
A out_mstatus_bits_SPIE = in_sstatus_SIE
A out_mstatus_bits_UBE = 1'h0
A out_mstatus_bits_MPIE = 1'h0
A out_mstatus_bits_SPP = in_privState_PRVM[0]
A out_mstatus_bits_VS = 2'h0
A out_mstatus_bits_MPP = 2'h0
A out_mstatus_bits_FS = 2'h0
A out_mstatus_bits_XS = 2'h0
A out_mstatus_bits_MPRV = 1'h0
A out_mstatus_bits_SUM = 1'h0
A out_mstatus_bits_MXR = 1'h0
A out_mstatus_bits_TVM = 1'h0
A out_mstatus_bits_TW = 1'h0
A out_mstatus_bits_TSR = 1'h0
A out_mstatus_bits_SDT = in_menvcfg_DTE
A out_mstatus_bits_UXL = 2'h0
A out_mstatus_bits_SXL = 2'h0
A out_mstatus_bits_SBE = 1'h0
A out_mstatus_bits_MBE = 1'h0
A out_mstatus_bits_GVA = 1'h0
A out_mstatus_bits_MPV = 1'h0
A out_mstatus_bits_MDT = 1'h0
A out_mstatus_bits_SD = 1'h0
A out_hstatus_valid = valid
A out_hstatus_bits_VSBE = 1'h0
A out_hstatus_bits_GVA = tvalFillGVA
A out_hstatus_bits_SPV = in_privState_V
A out_hstatus_bits_SPVP = in_privState_V ? in_privState_PRVM[0] : in_hstatus_SPVP
A out_hstatus_bits_HU = 1'h0
A out_hstatus_bits_VGEIN = 6'h0
A out_hstatus_bits_VTVM = 1'h0
A out_hstatus_bits_VTW = 1'h0
A out_hstatus_bits_VTSR = 1'h0
A out_hstatus_bits_VSXL = 2'h0
A out_hstatus_bits_HUPMM = 2'h0
A out_sepc_valid = valid
A out_sepc_bits_epc = in_satpFlushFirstFetchFault | ~in_isFetchMalAddr ? trapPC[63:1] : in_fetchMalTval[63:1]
A out_scause_valid = valid
A out_scause_bits_Interrupt = in_causeNO_Interrupt
A out_scause_bits_ExceptionCode = in_causeNO_ExceptionCode
A out_stval_valid = valid
A out_stval_bits_ALL = in_satpFlushFirstFetchFault | ~(~in_causeNO_Interrupt & in_isFetchMalAddr) ? {_tval_T_8[63:32], _tval_T_8[31:0] | (~in_causeNO_Interrupt & (in_causeNO_ExceptionCode == 63'h2 | in_causeNO_ExceptionCode == 63'h16) & in_trapInst_valid ? in_trapInst_bits : 32'h0)} : in_fetchMalTval
A out_htval_valid = valid
A out_htval_bits_ALL = {2'h0, in_satpFlushFirstFetchFault ? (_tval2FromSatpFlush_T ? in_fetchMalTval[63:2] : 62'h0) | (isFetchGuestExcp & ~in_isFetchMalAddr & ~in_isCrossPageIPF ? trapPCGPAFromSatpFlush[63:2] : 62'h0) | (isFetchGuestExcp & ~in_isFetchMalAddr & in_isCrossPageIPF ? _tval2FromSatpFlush_T_8[63:2] : 62'h0) | _tval2FromSatpFlush_T_13 : {_tval2_T_10[61:54], _tval2_T_10[53:0] | (isFetchGuestExcp & ~in_isFetchMalAddr & ~in_isCrossPageIPF ? in_trapPcGPA[55:2] : 54'h0) | (isFetchGuestExcp & ~in_isFetchMalAddr & in_isCrossPageIPF ? _tval2_T_8[55:2] : 54'h0)} | _tval2FromSatpFlush_T_13}
A out_htinst_valid = valid
A out_htinst_bits_ALL = {50'h0, isFetchGuestExcp & in_trapIsForVSnonLeafPTE | isLSGuestExcp & in_memExceptionIsForVSnonLeafPTE ? 14'h3000 : 14'h0}
A out_targetPc_valid = valid
A out_targetPc_bits_pc = in_pcFromXtvec
A out_targetPc_bits_raiseIPF = in_satp_MODE == 4'h8 & in_pcFromXtvec[63:39] != {25{in_pcFromXtvec[38]}} | in_satp_MODE == 4'h9 & in_pcFromXtvec[63:48] != {16{in_pcFromXtvec[47]}}
A out_targetPc_bits_raiseIAF = in_satp_MODE == 4'h0 & (|(in_pcFromXtvec[63:48]))
A out_targetPc_bits_raiseIGPF = 1'h0
M TrapEntryVSEventModule n
P i clock 1
P i reset 1
P i valid 1
P i in_causeNO_Interrupt 1
P i in_causeNO_ExceptionCode 63
P i in_trapPc 50
P i in_trapInst_valid 1
P i in_trapInst_bits 32
P i in_fetchMalTval 64
P i in_isCrossPageIPF 1
P i in_isFetchMalAddr 1
P i in_satpFlushFirstFetchFault 1
P i in_isFetchBkpt 1
P i in_iMode_PRVM 2
P i in_iMode_V 1
P i in_dMode_V 1
P i in_privState_PRVM 2
P i in_privState_V 1
P i in_vsstatus_SIE 1
P i in_henvcfg_DTE 1
P i in_pcFromXtvec 64
P i in_vsatp_MODE 4
P i in_hgatp_MODE 4
P i in_oldSatp_MODE 4
P i in_oldVsatp_MODE 4
P i in_memExceptionVAddr 64
P i in_virtualInterruptIsHvictlInject 1
P i in_hvictlIID 12
P o out_privState_valid 1
P o out_privState_bits_PRVM 2
P o out_privState_bits_V 1
P o out_vsstatus_valid 1
P o out_vsstatus_bits_SIE 1
P o out_vsstatus_bits_SPIE 1
P o out_vsstatus_bits_UBE 1
P o out_vsstatus_bits_SPP 1
P o out_vsstatus_bits_VS 2
P o out_vsstatus_bits_FS 2
P o out_vsstatus_bits_XS 2
P o out_vsstatus_bits_SUM 1
P o out_vsstatus_bits_MXR 1
P o out_vsstatus_bits_SDT 1
P o out_vsstatus_bits_UXL 2
P o out_vsstatus_bits_SD 1
P o out_vsepc_valid 1
P o out_vsepc_bits_epc 63
P o out_vscause_valid 1
P o out_vscause_bits_Interrupt 1
P o out_vscause_bits_ExceptionCode 63
P o out_vstval_valid 1
P o out_vstval_bits_ALL 64
P o out_targetPc_valid 1
P o out_targetPc_bits_pc 64
P o out_targetPc_bits_raiseIPF 1
P o out_targetPc_bits_raiseIAF 1
P o out_targetPc_bits_raiseIGPF 1
W highPrioTrapNO 63 = (in_causeNO_ExceptionCode == 63'h2 | in_causeNO_ExceptionCode == 63'h6 | in_causeNO_ExceptionCode == 63'hA) & in_causeNO_Interrupt ? in_causeNO_ExceptionCode - 63'h1 : in_causeNO_ExceptionCode
W trapPC_isBare_v_PrvmIsM 1 = &in_iMode_PRVM
W trapPC_isBare_isModeM 1 = trapPC_isBare_v_PrvmIsM
W trapPC_isBare_PrvmIsU 1 = in_iMode_PRVM == 2'h0
W trapPC_isBare_PrvmIsS 1 = in_iMode_PRVM == 2'h1
W _trapPC_isSv48_T 1 = trapPC_isBare_PrvmIsU | trapPC_isBare_PrvmIsS
W _trapPC_isSv48x4_T_2 1 = in_oldVsatp_MODE == 4'h0
W _instrAddrTransType_x1_T_1 1 = in_hgatp_MODE == 4'h0
W _instrAddrTransType_x4_T_1 1 = in_hgatp_MODE == 4'h8
W _instrAddrTransType_x5_T_1 1 = in_hgatp_MODE == 4'h9
W trapPC 64 = (trapPC_isBare_isModeM | _trapPC_isSv48_T & ~in_iMode_V & in_oldSatp_MODE == 4'h0 | in_iMode_V & _trapPC_isSv48x4_T_2 & _instrAddrTransType_x1_T_1 ? {16'h0, in_trapPc[47:0]} : 64'h0) | (_trapPC_isSv48_T & ~in_iMode_V & in_oldSatp_MODE == 4'h8 | in_iMode_V & in_oldVsatp_MODE == 4'h8 ? {{25{in_trapPc[38]}}, in_trapPc[38:0]} : 64'h0) | (in_iMode_V & _trapPC_isSv48x4_T_2 & _instrAddrTransType_x4_T_1 ? {23'h0, in_trapPc[40:0]} : 64'h0) | (_trapPC_isSv48_T & ~in_iMode_V & in_oldSatp_MODE == 4'h9 | in_iMode_V & in_oldVsatp_MODE == 4'h9 ? {{16{in_trapPc[47]}}, in_trapPc[47:0]} : 64'h0) | (in_iMode_V & _trapPC_isSv48x4_T_2 & _instrAddrTransType_x5_T_1 ? {14'h0, in_trapPc} : 64'h0)
W isFetchExcp 1 = ~in_causeNO_Interrupt & (highPrioTrapNO == 63'h1 | highPrioTrapNO == 63'hC)
W isBpExcp 1 = ~in_causeNO_Interrupt & highPrioTrapNO == 63'h3
W isFetchBkpt 1 = isBpExcp & in_isFetchBkpt
W tvalFillMemVaddr 1 = ~in_causeNO_Interrupt & (highPrioTrapNO == 63'h4 | highPrioTrapNO == 63'h5 | highPrioTrapNO == 63'h6 | highPrioTrapNO == 63'h7 | highPrioTrapNO == 63'hD | highPrioTrapNO == 63'hF) | isBpExcp & ~in_isFetchBkpt
W tvalFillGVA 1 = (isFetchExcp | isFetchBkpt) & in_iMode_V | tvalFillMemVaddr & in_dMode_V
W _tval_T_7 64 = (isFetchExcp & ~in_isCrossPageIPF | isFetchBkpt ? trapPC : 64'h0) | (isFetchExcp & in_isCrossPageIPF ? trapPC + 64'h2 : 64'h0) | (tvalFillMemVaddr ? in_memExceptionVAddr : 64'h0)
W _instrAddrTransType_x5_T 1 = in_vsatp_MODE == 4'h0
A out_privState_valid = valid
A out_privState_bits_PRVM = 2'h1
A out_privState_bits_V = 1'h1
A out_vsstatus_valid = valid
A out_vsstatus_bits_SIE = 1'h0
A out_vsstatus_bits_SPIE = in_vsstatus_SIE
A out_vsstatus_bits_UBE = 1'h0
A out_vsstatus_bits_SPP = in_privState_PRVM[0]
A out_vsstatus_bits_VS = 2'h0
A out_vsstatus_bits_FS = 2'h0
A out_vsstatus_bits_XS = 2'h0
A out_vsstatus_bits_SUM = 1'h0
A out_vsstatus_bits_MXR = 1'h0
A out_vsstatus_bits_SDT = in_henvcfg_DTE
A out_vsstatus_bits_UXL = 2'h0
A out_vsstatus_bits_SD = 1'h0
A out_vsepc_valid = valid
A out_vsepc_bits_epc = in_satpFlushFirstFetchFault | ~in_isFetchMalAddr ? trapPC[63:1] : in_fetchMalTval[63:1]
A out_vscause_valid = valid
A out_vscause_bits_Interrupt = in_causeNO_Interrupt
A out_vscause_bits_ExceptionCode = in_virtualInterruptIsHvictlInject & in_causeNO_Interrupt ? {51'h0, in_hvictlIID} : highPrioTrapNO
A out_vstval_valid = valid
A out_vstval_bits_ALL = in_satpFlushFirstFetchFault | ~(~in_causeNO_Interrupt & in_isFetchMalAddr) ? {_tval_T_7[63:32], _tval_T_7[31:0] | (~in_causeNO_Interrupt & (highPrioTrapNO == 63'h2 | highPrioTrapNO == 63'h16) & in_trapInst_valid ? in_trapInst_bits : 32'h0)} : in_fetchMalTval
A out_targetPc_valid = valid
A out_targetPc_bits_pc = in_pcFromXtvec
A out_targetPc_bits_raiseIPF = in_vsatp_MODE == 4'h8 & in_pcFromXtvec[63:39] != {25{in_pcFromXtvec[38]}} | in_vsatp_MODE == 4'h9 & in_pcFromXtvec[63:48] != {16{in_pcFromXtvec[47]}}
A out_targetPc_bits_raiseIAF = _instrAddrTransType_x5_T & _instrAddrTransType_x1_T_1 & (|(in_pcFromXtvec[63:48]))
A out_targetPc_bits_raiseIGPF = _instrAddrTransType_x5_T & _instrAddrTransType_x4_T_1 & (|(in_pcFromXtvec[63:41])) | _instrAddrTransType_x5_T & _instrAddrTransType_x5_T_1 & (|(in_pcFromXtvec[63:50]))
M MretEventModule n
P i valid 1
P i in_mstatus_MPIE 1
P i in_mstatus_MPP 2
P i in_mstatus_MPRV 1
P i in_mstatus_SDT 1
P i in_mstatus_MPV 1
P i in_vsstatus_SDT 1
P i in_mepc_epc 63
P i in_satp_MODE 4
P i in_vsatp_MODE 4
P i in_hgatp_MODE 4
P o out_privState_valid 1
P o out_privState_bits_PRVM 2
P o out_privState_bits_V 1
P o out_mstatus_valid 1
P o out_mstatus_bits_SIE 1
P o out_mstatus_bits_MIE 1
P o out_mstatus_bits_SPIE 1
P o out_mstatus_bits_UBE 1
P o out_mstatus_bits_MPIE 1
P o out_mstatus_bits_SPP 1
P o out_mstatus_bits_VS 2
P o out_mstatus_bits_MPP 2
P o out_mstatus_bits_FS 2
P o out_mstatus_bits_XS 2
P o out_mstatus_bits_MPRV 1
P o out_mstatus_bits_SUM 1
P o out_mstatus_bits_MXR 1
P o out_mstatus_bits_TVM 1
P o out_mstatus_bits_TW 1
P o out_mstatus_bits_TSR 1
P o out_mstatus_bits_SDT 1
P o out_mstatus_bits_UXL 2
P o out_mstatus_bits_SXL 2
P o out_mstatus_bits_SBE 1
P o out_mstatus_bits_MBE 1
P o out_mstatus_bits_GVA 1
P o out_mstatus_bits_MPV 1
P o out_mstatus_bits_MDT 1
P o out_mstatus_bits_SD 1
P o out_vsstatus_valid 1
P o out_vsstatus_bits_SIE 1
P o out_vsstatus_bits_SPIE 1
P o out_vsstatus_bits_UBE 1
P o out_vsstatus_bits_SPP 1
P o out_vsstatus_bits_VS 2
P o out_vsstatus_bits_FS 2
P o out_vsstatus_bits_XS 2
P o out_vsstatus_bits_SUM 1
P o out_vsstatus_bits_MXR 1
P o out_vsstatus_bits_SDT 1
P o out_vsstatus_bits_UXL 2
P o out_vsstatus_bits_SD 1
P o out_targetPc_valid 1
P o out_targetPc_bits_pc 64
P o out_targetPc_bits_raiseIPF 1
P o out_targetPc_bits_raiseIAF 1
P o out_targetPc_bits_raiseIGPF 1
W _out_privState_bits_PRVM_output 2 = in_mstatus_MPP
W instrAddrTransType_x1_v_PrvmIsM 1 = &_out_privState_bits_PRVM_output
W instrAddrTransType_x1_isModeM 1 = instrAddrTransType_x1_v_PrvmIsM
D _out_privState_bits_V_output 1
W _instrAddrTransType_x5_T_2 1 = in_vsatp_MODE == 4'h0
W mretToM_v_PrvmIsM 1 = &in_mstatus_MPP
W isModeM 1 = mretToM_v_PrvmIsM
W PrvmIsS 1 = in_mstatus_MPP == 2'h1
W isModeHS 1 = ~_out_privState_bits_V_output & PrvmIsS
W PrvmIsU 1 = in_mstatus_MPP == 2'h0
W isModeVU 1 = _out_privState_bits_V_output & PrvmIsU
A _out_privState_bits_V_output = ~(&in_mstatus_MPP) & in_mstatus_MPV
A out_privState_valid = valid
A out_privState_bits_PRVM = _out_privState_bits_PRVM_output
A out_privState_bits_V = _out_privState_bits_V_output
A out_mstatus_valid = valid
A out_mstatus_bits_SIE = 1'h0
A out_mstatus_bits_MIE = in_mstatus_MPIE
A out_mstatus_bits_SPIE = 1'h0
A out_mstatus_bits_UBE = 1'h0
A out_mstatus_bits_MPIE = 1'h1
A out_mstatus_bits_SPP = 1'h0
A out_mstatus_bits_VS = 2'h0
A out_mstatus_bits_MPP = 2'h0
A out_mstatus_bits_FS = 2'h0
A out_mstatus_bits_XS = 2'h0
A out_mstatus_bits_MPRV = (&in_mstatus_MPP) & in_mstatus_MPRV
A out_mstatus_bits_SUM = 1'h0
A out_mstatus_bits_MXR = 1'h0
A out_mstatus_bits_TVM = 1'h0
A out_mstatus_bits_TW = 1'h0
A out_mstatus_bits_TSR = 1'h0
A out_mstatus_bits_SDT = (isModeM | isModeHS) & in_mstatus_SDT
A out_mstatus_bits_UXL = 2'h0
A out_mstatus_bits_SXL = 2'h0
A out_mstatus_bits_SBE = 1'h0
A out_mstatus_bits_MBE = 1'h0
A out_mstatus_bits_GVA = 1'h0
A out_mstatus_bits_MPV = 1'h0
A out_mstatus_bits_MDT = 1'h0
A out_mstatus_bits_SD = 1'h0
A out_vsstatus_valid = valid
A out_vsstatus_bits_SIE = 1'h0
A out_vsstatus_bits_SPIE = 1'h0
A out_vsstatus_bits_UBE = 1'h0
A out_vsstatus_bits_SPP = 1'h0
A out_vsstatus_bits_VS = 2'h0
A out_vsstatus_bits_FS = 2'h0
A out_vsstatus_bits_XS = 2'h0
A out_vsstatus_bits_SUM = 1'h0
A out_vsstatus_bits_MXR = 1'h0
A out_vsstatus_bits_SDT = ~isModeVU & in_vsstatus_SDT
A out_vsstatus_bits_UXL = 2'h0
A out_vsstatus_bits_SD = 1'h0
A out_targetPc_valid = valid
A out_targetPc_bits_pc = {in_mepc_epc, 1'h0}
A out_targetPc_bits_raiseIPF = (~instrAddrTransType_x1_isModeM & ~_out_privState_bits_V_output & in_satp_MODE == 4'h8 | _out_privState_bits_V_output & in_vsatp_MODE == 4'h8) & in_mepc_epc[62:38] != {25{in_mepc_epc[37]}} | (~instrAddrTransType_x1_isModeM & ~_out_privState_bits_V_output & in_satp_MODE == 4'h9 | _out_privState_bits_V_output & in_vsatp_MODE == 4'h9) & in_mepc_epc[62:47] != {16{in_mepc_epc[46]}}
A out_targetPc_bits_raiseIAF = (instrAddrTransType_x1_isModeM | ~_out_privState_bits_V_output & in_satp_MODE == 4'h0 | _out_privState_bits_V_output & _instrAddrTransType_x5_T_2 & in_hgatp_MODE == 4'h0) & (|(in_mepc_epc[62:47]))
A out_targetPc_bits_raiseIGPF = _out_privState_bits_V_output & _instrAddrTransType_x5_T_2 & in_hgatp_MODE == 4'h8 & (|(in_mepc_epc[62:40])) | _out_privState_bits_V_output & _instrAddrTransType_x5_T_2 & in_hgatp_MODE == 4'h9 & (|(in_mepc_epc[62:49]))
M MNretEventModule n
P i valid 1
P i in_mnstatus_MNPV 1
P i in_mnstatus_MNPP 2
P i in_mstatus_MPRV 1
P i in_mstatus_SDT 1
P i in_mstatus_MDT 1
P i in_mnepc_epc 63
P i in_satp_MODE 4
P i in_vsatp_MODE 4
P i in_hgatp_MODE 4
P i in_vsstatus_SDT 1
P o out_privState_valid 1
P o out_privState_bits_PRVM 2
P o out_privState_bits_V 1
P o out_mnstatus_valid 1
P o out_mnstatus_bits_NMIE 1
P o out_mnstatus_bits_MNPV 1
P o out_mnstatus_bits_MNPELP 1
P o out_mnstatus_bits_MNPP 2
P o out_mstatus_valid 1
P o out_mstatus_bits_SIE 1
P o out_mstatus_bits_MIE 1
P o out_mstatus_bits_SPIE 1
P o out_mstatus_bits_UBE 1
P o out_mstatus_bits_MPIE 1
P o out_mstatus_bits_SPP 1
P o out_mstatus_bits_VS 2
P o out_mstatus_bits_MPP 2
P o out_mstatus_bits_FS 2
P o out_mstatus_bits_XS 2
P o out_mstatus_bits_MPRV 1
P o out_mstatus_bits_SUM 1
P o out_mstatus_bits_MXR 1
P o out_mstatus_bits_TVM 1
P o out_mstatus_bits_TW 1
P o out_mstatus_bits_TSR 1
P o out_mstatus_bits_SDT 1
P o out_mstatus_bits_UXL 2
P o out_mstatus_bits_SXL 2
P o out_mstatus_bits_SBE 1
P o out_mstatus_bits_MBE 1
P o out_mstatus_bits_GVA 1
P o out_mstatus_bits_MPV 1
P o out_mstatus_bits_MDT 1
P o out_mstatus_bits_SD 1
P o out_vsstatus_valid 1
P o out_vsstatus_bits_SIE 1
P o out_vsstatus_bits_SPIE 1
P o out_vsstatus_bits_UBE 1
P o out_vsstatus_bits_SPP 1
P o out_vsstatus_bits_VS 2
P o out_vsstatus_bits_FS 2
P o out_vsstatus_bits_XS 2
P o out_vsstatus_bits_SUM 1
P o out_vsstatus_bits_MXR 1
P o out_vsstatus_bits_SDT 1
P o out_vsstatus_bits_UXL 2
P o out_vsstatus_bits_SD 1
P o out_targetPc_valid 1
P o out_targetPc_bits_pc 64
P o out_targetPc_bits_raiseIPF 1
P o out_targetPc_bits_raiseIAF 1
P o out_targetPc_bits_raiseIGPF 1
W _out_privState_bits_PRVM_output 2 = in_mnstatus_MNPP
W instrAddrTransType_x1_v_PrvmIsM 1 = &_out_privState_bits_PRVM_output
W instrAddrTransType_x1_isModeM 1 = instrAddrTransType_x1_v_PrvmIsM
D _out_privState_bits_V_output 1
W _instrAddrTransType_x5_T_2 1 = in_vsatp_MODE == 4'h0
W mnretToM_v_PrvmIsM 1 = &in_mnstatus_MNPP
W isModeM 1 = mnretToM_v_PrvmIsM
W PrvmIsS 1 = in_mnstatus_MNPP == 2'h1
W isModeHS 1 = ~_out_privState_bits_V_output & PrvmIsS
W PrvmIsU 1 = in_mnstatus_MNPP == 2'h0
W isModeVU 1 = _out_privState_bits_V_output & PrvmIsU
A _out_privState_bits_V_output = ~(&in_mnstatus_MNPP) & in_mnstatus_MNPV
A out_privState_valid = valid
A out_privState_bits_PRVM = _out_privState_bits_PRVM_output
A out_privState_bits_V = _out_privState_bits_V_output
A out_mnstatus_valid = valid
A out_mnstatus_bits_NMIE = 1'h1
A out_mnstatus_bits_MNPV = 1'h0
A out_mnstatus_bits_MNPELP = 1'h0
A out_mnstatus_bits_MNPP = 2'h0
A out_mstatus_valid = valid
A out_mstatus_bits_SIE = 1'h0
A out_mstatus_bits_MIE = 1'h0
A out_mstatus_bits_SPIE = 1'h0
A out_mstatus_bits_UBE = 1'h0
A out_mstatus_bits_MPIE = 1'h0
A out_mstatus_bits_SPP = 1'h0
A out_mstatus_bits_VS = 2'h0
A out_mstatus_bits_MPP = 2'h0
A out_mstatus_bits_FS = 2'h0
A out_mstatus_bits_XS = 2'h0
A out_mstatus_bits_MPRV = (&in_mnstatus_MNPP) & in_mstatus_MPRV
A out_mstatus_bits_SUM = 1'h0
A out_mstatus_bits_MXR = 1'h0
A out_mstatus_bits_TVM = 1'h0
A out_mstatus_bits_TW = 1'h0
A out_mstatus_bits_TSR = 1'h0
A out_mstatus_bits_SDT = (isModeM | isModeHS) & in_mstatus_SDT
A out_mstatus_bits_UXL = 2'h0
A out_mstatus_bits_SXL = 2'h0
A out_mstatus_bits_SBE = 1'h0
A out_mstatus_bits_MBE = 1'h0
A out_mstatus_bits_GVA = 1'h0
A out_mstatus_bits_MPV = 1'h0
A out_mstatus_bits_MDT = isModeM & in_mstatus_MDT
A out_mstatus_bits_SD = 1'h0
A out_vsstatus_valid = valid
A out_vsstatus_bits_SIE = 1'h0
A out_vsstatus_bits_SPIE = 1'h0
A out_vsstatus_bits_UBE = 1'h0
A out_vsstatus_bits_SPP = 1'h0
A out_vsstatus_bits_VS = 2'h0
A out_vsstatus_bits_FS = 2'h0
A out_vsstatus_bits_XS = 2'h0
A out_vsstatus_bits_SUM = 1'h0
A out_vsstatus_bits_MXR = 1'h0
A out_vsstatus_bits_SDT = ~isModeVU & in_vsstatus_SDT
A out_vsstatus_bits_UXL = 2'h0
A out_vsstatus_bits_SD = 1'h0
A out_targetPc_valid = valid
A out_targetPc_bits_pc = {in_mnepc_epc, 1'h0}
A out_targetPc_bits_raiseIPF = (~instrAddrTransType_x1_isModeM & ~_out_privState_bits_V_output & in_satp_MODE == 4'h8 | _out_privState_bits_V_output & in_vsatp_MODE == 4'h8) & in_mnepc_epc[62:38] != {25{in_mnepc_epc[37]}} | (~instrAddrTransType_x1_isModeM & ~_out_privState_bits_V_output & in_satp_MODE == 4'h9 | _out_privState_bits_V_output & in_vsatp_MODE == 4'h9) & in_mnepc_epc[62:47] != {16{in_mnepc_epc[46]}}
A out_targetPc_bits_raiseIAF = (instrAddrTransType_x1_isModeM | ~_out_privState_bits_V_output & in_satp_MODE == 4'h0 | _out_privState_bits_V_output & _instrAddrTransType_x5_T_2 & in_hgatp_MODE == 4'h0) & (|(in_mnepc_epc[62:47]))
A out_targetPc_bits_raiseIGPF = _out_privState_bits_V_output & _instrAddrTransType_x5_T_2 & in_hgatp_MODE == 4'h8 & (|(in_mnepc_epc[62:40])) | _out_privState_bits_V_output & _instrAddrTransType_x5_T_2 & in_hgatp_MODE == 4'h9 & (|(in_mnepc_epc[62:49]))
M SretEventModule n
P i valid 1
P i in_privState_PRVM 2
P i in_privState_V 1
P i in_mstatus_SPIE 1
P i in_mstatus_SPP 1
P i in_mstatus_SDT 1
P i in_mstatus_MDT 1
P i in_hstatus_SPV 1
P i in_vsstatus_SPIE 1
P i in_vsstatus_SPP 1
P i in_sepc_epc 63
P i in_vsepc_epc 63
P i in_satp_MODE 4
P i in_vsatp_MODE 4
P i in_hgatp_MODE 4
P o out_privState_valid 1
P o out_privState_bits_PRVM 2
P o out_privState_bits_V 1
P o out_mstatus_valid 1
P o out_mstatus_bits_SIE 1
P o out_mstatus_bits_MIE 1
P o out_mstatus_bits_SPIE 1
P o out_mstatus_bits_UBE 1
P o out_mstatus_bits_MPIE 1
P o out_mstatus_bits_SPP 1
P o out_mstatus_bits_VS 2
P o out_mstatus_bits_MPP 2
P o out_mstatus_bits_FS 2
P o out_mstatus_bits_XS 2
P o out_mstatus_bits_MPRV 1
P o out_mstatus_bits_SUM 1
P o out_mstatus_bits_MXR 1
P o out_mstatus_bits_TVM 1
P o out_mstatus_bits_TW 1
P o out_mstatus_bits_TSR 1
P o out_mstatus_bits_SDT 1
P o out_mstatus_bits_UXL 2
P o out_mstatus_bits_SXL 2
P o out_mstatus_bits_SBE 1
P o out_mstatus_bits_MBE 1
P o out_mstatus_bits_GVA 1
P o out_mstatus_bits_MPV 1
P o out_mstatus_bits_MDT 1
P o out_mstatus_bits_SD 1
P o out_hstatus_valid 1
P o out_hstatus_bits_VSBE 1
P o out_hstatus_bits_GVA 1
P o out_hstatus_bits_SPV 1
P o out_hstatus_bits_SPVP 1
P o out_hstatus_bits_HU 1
P o out_hstatus_bits_VGEIN 6
P o out_hstatus_bits_VTVM 1
P o out_hstatus_bits_VTW 1
P o out_hstatus_bits_VTSR 1
P o out_hstatus_bits_VSXL 2
P o out_hstatus_bits_HUPMM 2
P o out_vsstatus_valid 1
P o out_vsstatus_bits_SIE 1
P o out_vsstatus_bits_SPIE 1
P o out_vsstatus_bits_UBE 1
P o out_vsstatus_bits_SPP 1
P o out_vsstatus_bits_VS 2
P o out_vsstatus_bits_FS 2
P o out_vsstatus_bits_XS 2
P o out_vsstatus_bits_SUM 1
P o out_vsstatus_bits_MXR 1
P o out_vsstatus_bits_SDT 1
P o out_vsstatus_bits_UXL 2
P o out_vsstatus_bits_SD 1
P o out_targetPc_valid 1
P o out_targetPc_bits_pc 64
P o out_targetPc_bits_raiseIPF 1
P o out_targetPc_bits_raiseIAF 1
P o out_targetPc_bits_raiseIGPF 1
P o outSDT_vsstatus_valid 1
D _out_privState_bits_V_output 1
W _instrAddrTransType_x5_T_2 1 = in_vsatp_MODE == 4'h0
W sretInM_v_PrvmIsM 1 = &in_privState_PRVM
W isModeM 1 = sretInM_v_PrvmIsM
W PrvmIsS 1 = in_privState_PRVM == 2'h1
W isModeHS 1 = ~in_privState_V & PrvmIsS
W sretInHSorM 1 = isModeM | isModeHS
W isModeVS 1 = in_privState_V & PrvmIsS
W _xepc_ret_epc_T_4 63 = (sretInHSorM ? in_sepc_epc : 63'h0) | (isModeVS ? in_vsepc_epc : 63'h0)
W PrvmIsS_1 1 = sretInHSorM & in_mstatus_SPP | isModeVS & in_vsstatus_SPP
W PrvmIsU 1 = ~PrvmIsS_1
W isModeVU 1 = _out_privState_bits_V_output & PrvmIsU
W isModeVS_1 1 = _out_privState_bits_V_output & PrvmIsS_1
W isModeHU 1 = ~_out_privState_bits_V_output & PrvmIsU
W _out_mstatus_valid_T 1 = valid & sretInHSorM
A _out_privState_bits_V_output = sretInHSorM & in_hstatus_SPV | isModeVS & in_privState_V
A out_privState_valid = valid
A out_privState_bits_PRVM = {1'h0, PrvmIsS_1}
A out_privState_bits_V = _out_privState_bits_V_output
A out_mstatus_valid = _out_mstatus_valid_T
A out_mstatus_bits_SIE = in_mstatus_SPIE
A out_mstatus_bits_MIE = 1'h0
A out_mstatus_bits_SPIE = 1'h1
A out_mstatus_bits_UBE = 1'h0
A out_mstatus_bits_MPIE = 1'h0
A out_mstatus_bits_SPP = 1'h0
A out_mstatus_bits_VS = 2'h0
A out_mstatus_bits_MPP = 2'h0
A out_mstatus_bits_FS = 2'h0
A out_mstatus_bits_XS = 2'h0
A out_mstatus_bits_MPRV = 1'h0
A out_mstatus_bits_SUM = 1'h0
A out_mstatus_bits_MXR = 1'h0
A out_mstatus_bits_TVM = 1'h0
A out_mstatus_bits_TW = 1'h0
A out_mstatus_bits_TSR = 1'h0
A out_mstatus_bits_SDT = ~(isModeHS | isModeM & (isModeHU | isModeVS_1 | isModeVU)) & in_mstatus_SDT
A out_mstatus_bits_UXL = 2'h0
A out_mstatus_bits_SXL = 2'h0
A out_mstatus_bits_SBE = 1'h0
A out_mstatus_bits_MBE = 1'h0
A out_mstatus_bits_GVA = 1'h0
A out_mstatus_bits_MPV = 1'h0
A out_mstatus_bits_MDT = ~isModeM & in_mstatus_MDT
A out_mstatus_bits_SD = 1'h0
A out_hstatus_valid = _out_mstatus_valid_T
A out_hstatus_bits_VSBE = 1'h0
A out_hstatus_bits_GVA = 1'h0
A out_hstatus_bits_SPV = 1'h0
A out_hstatus_bits_SPVP = 1'h0
A out_hstatus_bits_HU = 1'h0
A out_hstatus_bits_VGEIN = 6'h0
A out_hstatus_bits_VTVM = 1'h0
A out_hstatus_bits_VTW = 1'h0
A out_hstatus_bits_VTSR = 1'h0
A out_hstatus_bits_VSXL = 2'h0
A out_hstatus_bits_HUPMM = 2'h0
A out_vsstatus_valid = valid & isModeVS
A out_vsstatus_bits_SIE = in_vsstatus_SPIE
A out_vsstatus_bits_SPIE = 1'h1
A out_vsstatus_bits_UBE = 1'h0
A out_vsstatus_bits_SPP = 1'h0
A out_vsstatus_bits_VS = 2'h0
A out_vsstatus_bits_FS = 2'h0
A out_vsstatus_bits_XS = 2'h0
A out_vsstatus_bits_SUM = 1'h0
A out_vsstatus_bits_MXR = 1'h0
A out_vsstatus_bits_SDT = 1'h0
A out_vsstatus_bits_UXL = 2'h0
A out_vsstatus_bits_SD = 1'h0
A out_targetPc_valid = valid
A out_targetPc_bits_pc = {_xepc_ret_epc_T_4, 1'h0}
A out_targetPc_bits_raiseIPF = (~_out_privState_bits_V_output & in_satp_MODE == 4'h8 | _out_privState_bits_V_output & in_vsatp_MODE == 4'h8) & _xepc_ret_epc_T_4[62:38] != {25{_xepc_ret_epc_T_4[37]}} | (~_out_privState_bits_V_output & in_satp_MODE == 4'h9 | _out_privState_bits_V_output & in_vsatp_MODE == 4'h9) & _xepc_ret_epc_T_4[62:47] != {16{_xepc_ret_epc_T_4[46]}}
A out_targetPc_bits_raiseIAF = (~_out_privState_bits_V_output & in_satp_MODE == 4'h0 | _out_privState_bits_V_output & _instrAddrTransType_x5_T_2 & in_hgatp_MODE == 4'h0) & (|(_xepc_ret_epc_T_4[62:47]))
A out_targetPc_bits_raiseIGPF = _out_privState_bits_V_output & _instrAddrTransType_x5_T_2 & in_hgatp_MODE == 4'h8 & (|(_xepc_ret_epc_T_4[62:40])) | _out_privState_bits_V_output & _instrAddrTransType_x5_T_2 & in_hgatp_MODE == 4'h9 & (|(_xepc_ret_epc_T_4[62:49]))
A outSDT_vsstatus_valid = valid & (isModeVU | isModeVS)
M DretEventModule n
P i valid 1
P i in_dcsr_V 1
P i in_dcsr_PRV 2
P i in_dpc_epc 63
P i in_mstatus_MPRV 1
P i in_mstatus_SDT 1
P i in_mstatus_MDT 1
P i in_vsstatus_SDT 1
P i in_satp_MODE 4
P i in_vsatp_MODE 4
P i in_hgatp_MODE 4
P o out_privState_valid 1
P o out_privState_bits_PRVM 2
P o out_privState_bits_V 1
P o out_dcsr_valid 1
P o out_dcsr_bits_DEBUGVER 4
P o out_dcsr_bits_EXTCAUSE 3
P o out_dcsr_bits_CETRIG 1
P o out_dcsr_bits_EBREAKVS 1
P o out_dcsr_bits_EBREAKVU 1
P o out_dcsr_bits_EBREAKM 1
P o out_dcsr_bits_EBREAKS 1
P o out_dcsr_bits_EBREAKU 1
P o out_dcsr_bits_STEPIE 1
P o out_dcsr_bits_STOPCOUNT 1
P o out_dcsr_bits_STOPTIME 1
P o out_dcsr_bits_CAUSE 3
P o out_dcsr_bits_V 1
P o out_dcsr_bits_MPRVEN 1
P o out_dcsr_bits_NMIP 1
P o out_dcsr_bits_STEP 1
P o out_dcsr_bits_PRV 2
P o out_mstatus_valid 1
P o out_mstatus_bits_SIE 1
P o out_mstatus_bits_MIE 1
P o out_mstatus_bits_SPIE 1
P o out_mstatus_bits_UBE 1
P o out_mstatus_bits_MPIE 1
P o out_mstatus_bits_SPP 1
P o out_mstatus_bits_VS 2
P o out_mstatus_bits_MPP 2
P o out_mstatus_bits_FS 2
P o out_mstatus_bits_XS 2
P o out_mstatus_bits_MPRV 1
P o out_mstatus_bits_SUM 1
P o out_mstatus_bits_MXR 1
P o out_mstatus_bits_TVM 1
P o out_mstatus_bits_TW 1
P o out_mstatus_bits_TSR 1
P o out_mstatus_bits_SDT 1
P o out_mstatus_bits_UXL 2
P o out_mstatus_bits_SXL 2
P o out_mstatus_bits_SBE 1
P o out_mstatus_bits_MBE 1
P o out_mstatus_bits_GVA 1
P o out_mstatus_bits_MPV 1
P o out_mstatus_bits_MDT 1
P o out_mstatus_bits_SD 1
P o out_vsstatus_valid 1
P o out_vsstatus_bits_SIE 1
P o out_vsstatus_bits_SPIE 1
P o out_vsstatus_bits_UBE 1
P o out_vsstatus_bits_SPP 1
P o out_vsstatus_bits_VS 2
P o out_vsstatus_bits_FS 2
P o out_vsstatus_bits_XS 2
P o out_vsstatus_bits_SUM 1
P o out_vsstatus_bits_MXR 1
P o out_vsstatus_bits_SDT 1
P o out_vsstatus_bits_UXL 2
P o out_vsstatus_bits_SD 1
P o out_debugMode_valid 1
P o out_debugMode_bits 1
P o out_debugIntrEnable_valid 1
P o out_debugIntrEnable_bits 1
P o out_targetPc_valid 1
P o out_targetPc_bits_pc 64
P o out_targetPc_bits_raiseIPF 1
P o out_targetPc_bits_raiseIAF 1
P o out_targetPc_bits_raiseIGPF 1
W _out_privState_bits_PRVM_output 2 = in_dcsr_PRV
W instrAddrTransType_x1_v_PrvmIsM 1 = &_out_privState_bits_PRVM_output
W instrAddrTransType_x1_isModeM 1 = instrAddrTransType_x1_v_PrvmIsM
D _out_privState_bits_V_output 1
W _instrAddrTransType_x5_T_2 1 = in_vsatp_MODE == 4'h0
W PrvmIsU 1 = _out_privState_bits_PRVM_output == 2'h0
W isModeHU 1 = ~_out_privState_bits_V_output & PrvmIsU
W isModeVU 1 = _out_privState_bits_V_output & PrvmIsU
A _out_privState_bits_V_output = in_dcsr_PRV != 2'h3 & in_dcsr_V
A out_privState_valid = valid
A out_privState_bits_PRVM = _out_privState_bits_PRVM_output
A out_privState_bits_V = _out_privState_bits_V_output
A out_dcsr_valid = valid
A out_dcsr_bits_DEBUGVER = 4'h0
A out_dcsr_bits_EXTCAUSE = 3'h0
A out_dcsr_bits_CETRIG = 1'h0
A out_dcsr_bits_EBREAKVS = 1'h0
A out_dcsr_bits_EBREAKVU = 1'h0
A out_dcsr_bits_EBREAKM = 1'h0
A out_dcsr_bits_EBREAKS = 1'h0
A out_dcsr_bits_EBREAKU = 1'h0
A out_dcsr_bits_STEPIE = 1'h0
A out_dcsr_bits_STOPCOUNT = 1'h0
A out_dcsr_bits_STOPTIME = 1'h0
A out_dcsr_bits_CAUSE = 3'h0
A out_dcsr_bits_V = 1'h0
A out_dcsr_bits_MPRVEN = 1'h0
A out_dcsr_bits_NMIP = 1'h0
A out_dcsr_bits_STEP = 1'h0
A out_dcsr_bits_PRV = 2'h0
A out_mstatus_valid = valid
A out_mstatus_bits_SIE = 1'h0
A out_mstatus_bits_MIE = 1'h0
A out_mstatus_bits_SPIE = 1'h0
A out_mstatus_bits_UBE = 1'h0
A out_mstatus_bits_MPIE = 1'h0
A out_mstatus_bits_SPP = 1'h0
A out_mstatus_bits_VS = 2'h0
A out_mstatus_bits_MPP = 2'h0
A out_mstatus_bits_FS = 2'h0
A out_mstatus_bits_XS = 2'h0
A out_mstatus_bits_MPRV = instrAddrTransType_x1_isModeM & in_mstatus_MPRV
A out_mstatus_bits_SUM = 1'h0
A out_mstatus_bits_MXR = 1'h0
A out_mstatus_bits_TVM = 1'h0
A out_mstatus_bits_TW = 1'h0
A out_mstatus_bits_TSR = 1'h0
A out_mstatus_bits_SDT = ~(_out_privState_bits_V_output | isModeHU) & in_mstatus_SDT
A out_mstatus_bits_UXL = 2'h0
A out_mstatus_bits_SXL = 2'h0
A out_mstatus_bits_SBE = 1'h0
A out_mstatus_bits_MBE = 1'h0
A out_mstatus_bits_GVA = 1'h0
A out_mstatus_bits_MPV = 1'h0
A out_mstatus_bits_MDT = instrAddrTransType_x1_isModeM & in_mstatus_MDT
A out_mstatus_bits_SD = 1'h0
A out_vsstatus_valid = valid
A out_vsstatus_bits_SIE = 1'h0
A out_vsstatus_bits_SPIE = 1'h0
A out_vsstatus_bits_UBE = 1'h0
A out_vsstatus_bits_SPP = 1'h0
A out_vsstatus_bits_VS = 2'h0
A out_vsstatus_bits_FS = 2'h0
A out_vsstatus_bits_XS = 2'h0
A out_vsstatus_bits_SUM = 1'h0
A out_vsstatus_bits_MXR = 1'h0
A out_vsstatus_bits_SDT = ~isModeVU & in_vsstatus_SDT
A out_vsstatus_bits_UXL = 2'h0
A out_vsstatus_bits_SD = 1'h0
A out_debugMode_valid = valid
A out_debugMode_bits = 1'h0
A out_debugIntrEnable_valid = valid
A out_debugIntrEnable_bits = 1'h1
A out_targetPc_valid = valid
A out_targetPc_bits_pc = {in_dpc_epc, 1'h0}
A out_targetPc_bits_raiseIPF = (~instrAddrTransType_x1_isModeM & ~_out_privState_bits_V_output & in_satp_MODE == 4'h8 | _out_privState_bits_V_output & in_vsatp_MODE == 4'h8) & in_dpc_epc[62:38] != {25{in_dpc_epc[37]}} | (~instrAddrTransType_x1_isModeM & ~_out_privState_bits_V_output & in_satp_MODE == 4'h9 | _out_privState_bits_V_output & in_vsatp_MODE == 4'h9) & in_dpc_epc[62:47] != {16{in_dpc_epc[46]}}
A out_targetPc_bits_raiseIAF = (instrAddrTransType_x1_isModeM | ~_out_privState_bits_V_output & in_satp_MODE == 4'h0 | _out_privState_bits_V_output & _instrAddrTransType_x5_T_2 & in_hgatp_MODE == 4'h0) & (|(in_dpc_epc[62:47]))
A out_targetPc_bits_raiseIGPF = _out_privState_bits_V_output & _instrAddrTransType_x5_T_2 & in_hgatp_MODE == 4'h8 & (|(in_dpc_epc[62:40])) | _out_privState_bits_V_output & _instrAddrTransType_x5_T_2 & in_hgatp_MODE == 4'h9 & (|(in_dpc_epc[62:49]))
M TselectModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 2
P o regOut_ALL 2
F reg_ALL 2 0
S reg_ALL ? w_wen & w_wdata < 64'h4 : w_wdata[1:0]
A rdata = reg_ALL
A regOut_ALL = reg_ALL
M Tdata1Module n
P o rdata 64
P o regOut_TYPE 4
P o regOut_DMODE 1
P o regOut_DATA 59
P i tdataRead_tdata1 64
A rdata = tdataRead_tdata1
A regOut_TYPE = tdataRead_tdata1[63:60]
A regOut_DMODE = tdataRead_tdata1[59]
A regOut_DATA = tdataRead_tdata1[58:0]
M Tdata2Module n
P o rdata 64
P o regOut_ALL 64
P i tdataRead_tdata2 64
A rdata = tdataRead_tdata2
A regOut_ALL = tdataRead_tdata2
M Trigger0_Tdata1Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P i canWriteDmode 1
P i chainable 1
P i dmodeNextTrigger 1
F reg_TYPE 4 15
F reg_DMODE 1 0
F reg_DATA 59 0
V _GEN 1
V dmode 1 = w_wdata[59] & canWriteDmode
V _GEN ? 1'h1 : w_wdata[63:60] == 4'h6
S reg_TYPE ? w_wen : _GEN ? w_wdata[63:60] : 4'hF
S reg_DMODE ? w_wen : dmode
S reg_DATA ? w_wen : _GEN ? {34'h0, w_wdata[24:23], 7'h0, w_wdata[15:12] == 4'h0 | w_wdata[15:12] == 4'h1 & dmode ? w_wdata[15:12] : 4'h0, w_wdata[11] & chainable & ~(~dmode & dmodeNextTrigger), w_wdata[10:7] == 4'h0 | w_wdata[10:7] == 4'h2 | w_wdata[10:7] == 4'h3 ? w_wdata[10:7] : 4'h0, w_wdata[6], 1'h0, w_wdata[4:0]} : 59'h0
S reg_TYPE ? !(w_wen) & w_wen & _GEN : w_wdata[63:60]
A rdata = {reg_TYPE, reg_DMODE, reg_DATA}
M Trigger1_Tdata1Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P i canWriteDmode 1
P i chainable 1
P i dmodeNextTrigger 1
F reg_TYPE 4 15
F reg_DMODE 1 0
F reg_DATA 59 0
V _GEN 1
V dmode 1 = w_wdata[59] & canWriteDmode
V _GEN ? 1'h1 : w_wdata[63:60] == 4'h6
S reg_TYPE ? w_wen : _GEN ? w_wdata[63:60] : 4'hF
S reg_DMODE ? w_wen : dmode
S reg_DATA ? w_wen : _GEN ? {34'h0, w_wdata[24:23], 7'h0, w_wdata[15:12] == 4'h0 | w_wdata[15:12] == 4'h1 & dmode ? w_wdata[15:12] : 4'h0, w_wdata[11] & chainable & ~(~dmode & dmodeNextTrigger), w_wdata[10:7] == 4'h0 | w_wdata[10:7] == 4'h2 | w_wdata[10:7] == 4'h3 ? w_wdata[10:7] : 4'h0, w_wdata[6], 1'h0, w_wdata[4:0]} : 59'h0
S reg_TYPE ? !(w_wen) & w_wen & _GEN : w_wdata[63:60]
A rdata = {reg_TYPE, reg_DMODE, reg_DATA}
M Trigger2_Tdata1Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P i canWriteDmode 1
P i chainable 1
P i dmodeNextTrigger 1
F reg_TYPE 4 15
F reg_DMODE 1 0
F reg_DATA 59 0
V _GEN 1
V dmode 1 = w_wdata[59] & canWriteDmode
V _GEN ? 1'h1 : w_wdata[63:60] == 4'h6
S reg_TYPE ? w_wen : _GEN ? w_wdata[63:60] : 4'hF
S reg_DMODE ? w_wen : dmode
S reg_DATA ? w_wen : _GEN ? {34'h0, w_wdata[24:23], 7'h0, w_wdata[15:12] == 4'h0 | w_wdata[15:12] == 4'h1 & dmode ? w_wdata[15:12] : 4'h0, w_wdata[11] & chainable & ~(~dmode & dmodeNextTrigger), w_wdata[10:7] == 4'h0 | w_wdata[10:7] == 4'h2 | w_wdata[10:7] == 4'h3 ? w_wdata[10:7] : 4'h0, w_wdata[6], 1'h0, w_wdata[4:0]} : 59'h0
S reg_TYPE ? !(w_wen) & w_wen & _GEN : w_wdata[63:60]
A rdata = {reg_TYPE, reg_DMODE, reg_DATA}
M Trigger3_Tdata1Module a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P i canWriteDmode 1
P i chainable 1
F reg_TYPE 4 15
F reg_DMODE 1 0
F reg_DATA 59 0
V _GEN 1
V dmode 1 = w_wdata[59] & canWriteDmode
V _GEN ? 1'h1 : w_wdata[63:60] == 4'h6
S reg_TYPE ? w_wen : _GEN ? w_wdata[63:60] : 4'hF
S reg_DMODE ? w_wen : dmode
S reg_DATA ? w_wen : _GEN ? {34'h0, w_wdata[24:23], 7'h0, w_wdata[15:12] == 4'h0 | w_wdata[15:12] == 4'h1 & dmode ? w_wdata[15:12] : 4'h0, w_wdata[11] & chainable, w_wdata[10:7] == 4'h0 | w_wdata[10:7] == 4'h2 | w_wdata[10:7] == 4'h3 ? w_wdata[10:7] : 4'h0, w_wdata[6], 1'h0, w_wdata[4:0]} : 59'h0
S reg_TYPE ? !(w_wen) & w_wen & _GEN : w_wdata[63:60]
A rdata = {reg_TYPE, reg_DMODE, reg_DATA}
M Trigger0_Tdata2Module n
P i clock 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
F reg_ALL 64 -
S reg_ALL ? w_wen : w_wdata
A rdata = reg_ALL
M Trigger1_Tdata2Module n
P i clock 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
F reg_ALL 64 -
S reg_ALL ? w_wen : w_wdata
A rdata = reg_ALL
M Trigger2_Tdata2Module n
P i clock 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
F reg_ALL 64 -
S reg_ALL ? w_wen : w_wdata
A rdata = reg_ALL
M Trigger3_Tdata2Module n
P i clock 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
F reg_ALL 64 -
S reg_ALL ? w_wen : w_wdata
A rdata = reg_ALL
M DcsrModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 32
P o regOut_CETRIG 1
P o regOut_EBREAKVS 1
P o regOut_EBREAKVU 1
P o regOut_EBREAKM 1
P o regOut_EBREAKS 1
P o regOut_EBREAKU 1
P o regOut_STEPIE 1
P o regOut_STOPCOUNT 1
P o regOut_STOPTIME 1
P o regOut_CAUSE 3
P o regOut_V 1
P o regOut_MPRVEN 1
P o regOut_NMIP 1
P o regOut_STEP 1
P o regOut_PRV 2
P i trapToD_dcsr_valid 1
P i trapToD_dcsr_bits_CAUSE 3
P i trapToD_dcsr_bits_V 1
P i trapToD_dcsr_bits_PRV 2
P i retFromD_dcsr_valid 1
P i retFromD_dcsr_bits_V 1
P i retFromD_dcsr_bits_PRV 2
P i nmip 1
F reg_CETRIG 1 0
F reg_EBREAKVS 1 0
F reg_EBREAKVU 1 0
F reg_EBREAKM 1 0
F reg_EBREAKS 1 0
F reg_EBREAKU 1 0
F reg_STEPIE 1 0
F reg_STOPCOUNT 1 0
F reg_STOPTIME 1 0
F reg_CAUSE 3 0
F reg_V 1 0
F reg_MPRVEN 1 0
F reg_STEP 1 0
F reg_PRV 2 3
V _GEN 1 = trapToD_dcsr_valid | retFromD_dcsr_valid
S reg_CETRIG ? w_wen : w_wdata[19]
S reg_EBREAKVS ? w_wen : w_wdata[17]
S reg_EBREAKVU ? w_wen : w_wdata[16]
S reg_EBREAKM ? w_wen : w_wdata[15]
S reg_EBREAKS ? w_wen : w_wdata[13]
S reg_EBREAKU ? w_wen : w_wdata[12]
S reg_STEPIE ? w_wen : w_wdata[11]
S reg_STOPCOUNT ? w_wen : w_wdata[10]
S reg_STOPTIME ? w_wen : w_wdata[9]
S reg_MPRVEN ? w_wen : w_wdata[4]
S reg_STEP ? w_wen : w_wdata[2]
S reg_CAUSE ? trapToD_dcsr_valid : (trapToD_dcsr_valid ? trapToD_dcsr_bits_CAUSE : 3'h0) | (w_wen ? w_wdata[8:6] : 3'h0)
S reg_V ? w_wen | _GEN : trapToD_dcsr_valid & trapToD_dcsr_bits_V | retFromD_dcsr_valid & retFromD_dcsr_bits_V | w_wen & w_wdata[5]
S reg_PRV ? w_wen & (w_wdata[1:0] == 2'h0 | w_wdata[1:0] == 2'h1 | (&(w_wdata[1:0]))) | _GEN : (trapToD_dcsr_valid ? trapToD_dcsr_bits_PRV : 2'h0) | (retFromD_dcsr_valid ? retFromD_dcsr_bits_PRV : 2'h0) | (w_wen ? w_wdata[1:0] : 2'h0)
A rdata = {12'h400, reg_CETRIG, 1'h0, reg_EBREAKVS, reg_EBREAKVU, reg_EBREAKM, 1'h0, reg_EBREAKS, reg_EBREAKU, reg_STEPIE, reg_STOPCOUNT, reg_STOPTIME, reg_CAUSE, reg_V, reg_MPRVEN, nmip, reg_STEP, reg_PRV}
A regOut_CETRIG = reg_CETRIG
A regOut_EBREAKVS = reg_EBREAKVS
A regOut_EBREAKVU = reg_EBREAKVU
A regOut_EBREAKM = reg_EBREAKM
A regOut_EBREAKS = reg_EBREAKS
A regOut_EBREAKU = reg_EBREAKU
A regOut_STEPIE = reg_STEPIE
A regOut_STOPCOUNT = reg_STOPCOUNT
A regOut_STOPTIME = reg_STOPTIME
A regOut_CAUSE = reg_CAUSE
A regOut_V = reg_V
A regOut_MPRVEN = reg_MPRVEN
A regOut_NMIP = nmip
A regOut_STEP = reg_STEP
A regOut_PRV = reg_PRV
M DpcModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_epc 63
P i trapToD_dpc_valid 1
P i trapToD_dpc_bits_epc 63
F reg_epc 63 0
S reg_epc ? w_wen | trapToD_dpc_valid : (trapToD_dpc_valid ? trapToD_dpc_bits_epc : 63'h0) | (w_wen ? w_wdata[63:1] : 63'h0)
A rdata = {reg_epc, 1'h0}
A regOut_epc = reg_epc
M Dscratch0Module n
P i clock 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
F reg_ALL 64 -
S reg_ALL ? w_wen : w_wdata
A rdata = reg_ALL
A regOut_ALL = reg_ALL
M Dscratch1Module n
P i clock 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_ALL 64
F reg_ALL 64 -
S reg_ALL ? w_wen : w_wdata
A rdata = reg_ALL
A regOut_ALL = reg_ALL
M SbpctlModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_LOOP_ENABLE 1
P o regOut_RAS_ENABLE 1
P o regOut_SC_ENABLE 1
P o regOut_TAGE_ENABLE 1
P o regOut_BIM_ENABLE 1
P o regOut_BTB_ENABLE 1
P o regOut_UBTB_ENABLE 1
F reg_LOOP_ENABLE 1 1
F reg_RAS_ENABLE 1 1
F reg_SC_ENABLE 1 1
F reg_TAGE_ENABLE 1 1
F reg_BIM_ENABLE 1 1
F reg_BTB_ENABLE 1 1
F reg_UBTB_ENABLE 1 1
S reg_LOOP_ENABLE ? w_wen : w_wdata[6]
S reg_RAS_ENABLE ? w_wen : w_wdata[5]
S reg_SC_ENABLE ? w_wen : w_wdata[4]
S reg_TAGE_ENABLE ? w_wen : w_wdata[3]
S reg_BIM_ENABLE ? w_wen : w_wdata[2]
S reg_BTB_ENABLE ? w_wen : w_wdata[1]
S reg_UBTB_ENABLE ? w_wen : w_wdata[0]
A rdata = {57'h0, reg_LOOP_ENABLE, reg_RAS_ENABLE, reg_SC_ENABLE, reg_TAGE_ENABLE, reg_BIM_ENABLE, reg_BTB_ENABLE, reg_UBTB_ENABLE}
A regOut_LOOP_ENABLE = reg_LOOP_ENABLE
A regOut_RAS_ENABLE = reg_RAS_ENABLE
A regOut_SC_ENABLE = reg_SC_ENABLE
A regOut_TAGE_ENABLE = reg_TAGE_ENABLE
A regOut_BIM_ENABLE = reg_BIM_ENABLE
A regOut_BTB_ENABLE = reg_BTB_ENABLE
A regOut_UBTB_ENABLE = reg_UBTB_ENABLE
M SpfctlModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_L2_PF_DELAY_LATENCY 10
P o regOut_L2_PF_TP_ENABLE 1
P o regOut_L2_PF_VBOP_ENABLE 1
P o regOut_L2_PF_PBOP_ENABLE 1
P o regOut_L2_PF_RECV_ENABLE 1
P o regOut_L2_PF_STORE_ONLY 1
P o regOut_L1D_PF_ENABLE_STRIDE 1
P o regOut_L1D_PF_ACTIVE_STRIDE 6
P o regOut_L1D_PF_ACTIVE_THRESHOLD 4
P o regOut_L1D_PF_ENABLE_PHT 1
P o regOut_L1D_PF_ENABLE_AGT 1
P o regOut_L1D_PF_TRAIN_ON_HIT 1
P o regOut_L1D_PF_ENABLE 1
P o regOut_L2_PF_ENABLE 1
P o regOut_L1I_PF_ENABLE 1
F reg_L2_PF_DELAY_LATENCY 10 0
F reg_L2_PF_TP_ENABLE 1 1
F reg_L2_PF_VBOP_ENABLE 1 1
F reg_L2_PF_PBOP_ENABLE 1 1
F reg_L2_PF_RECV_ENABLE 1 1
F reg_L2_PF_STORE_ONLY 1 0
F reg_L1D_PF_ENABLE_STRIDE 1 1
F reg_L1D_PF_ACTIVE_STRIDE 6 30
F reg_L1D_PF_ACTIVE_THRESHOLD 4 12
F reg_L1D_PF_ENABLE_PHT 1 1
F reg_L1D_PF_ENABLE_AGT 1 1
F reg_L1D_PF_TRAIN_ON_HIT 1 0
F reg_L1D_PF_ENABLE 1 1
F reg_L2_PF_ENABLE 1 1
F reg_L1I_PF_ENABLE 1 1
S reg_L2_PF_DELAY_LATENCY ? w_wen : w_wdata[31:22]
S reg_L2_PF_TP_ENABLE ? w_wen : w_wdata[21]
S reg_L2_PF_VBOP_ENABLE ? w_wen : w_wdata[20]
S reg_L2_PF_PBOP_ENABLE ? w_wen : w_wdata[19]
S reg_L2_PF_RECV_ENABLE ? w_wen : w_wdata[18]
S reg_L2_PF_STORE_ONLY ? w_wen : w_wdata[17]
S reg_L1D_PF_ENABLE_STRIDE ? w_wen : w_wdata[16]
S reg_L1D_PF_ACTIVE_STRIDE ? w_wen : w_wdata[15:10]
S reg_L1D_PF_ACTIVE_THRESHOLD ? w_wen : w_wdata[9:6]
S reg_L1D_PF_ENABLE_PHT ? w_wen : w_wdata[5]
S reg_L1D_PF_ENABLE_AGT ? w_wen : w_wdata[4]
S reg_L1D_PF_TRAIN_ON_HIT ? w_wen : w_wdata[3]
S reg_L1D_PF_ENABLE ? w_wen : w_wdata[2]
S reg_L2_PF_ENABLE ? w_wen : w_wdata[1]
S reg_L1I_PF_ENABLE ? w_wen : w_wdata[0]
A rdata = {32'h0, reg_L2_PF_DELAY_LATENCY, reg_L2_PF_TP_ENABLE, reg_L2_PF_VBOP_ENABLE, reg_L2_PF_PBOP_ENABLE, reg_L2_PF_RECV_ENABLE, reg_L2_PF_STORE_ONLY, reg_L1D_PF_ENABLE_STRIDE, reg_L1D_PF_ACTIVE_STRIDE, reg_L1D_PF_ACTIVE_THRESHOLD, reg_L1D_PF_ENABLE_PHT, reg_L1D_PF_ENABLE_AGT, reg_L1D_PF_TRAIN_ON_HIT, reg_L1D_PF_ENABLE, reg_L2_PF_ENABLE, reg_L1I_PF_ENABLE}
A regOut_L2_PF_DELAY_LATENCY = reg_L2_PF_DELAY_LATENCY
A regOut_L2_PF_TP_ENABLE = reg_L2_PF_TP_ENABLE
A regOut_L2_PF_VBOP_ENABLE = reg_L2_PF_VBOP_ENABLE
A regOut_L2_PF_PBOP_ENABLE = reg_L2_PF_PBOP_ENABLE
A regOut_L2_PF_RECV_ENABLE = reg_L2_PF_RECV_ENABLE
A regOut_L2_PF_STORE_ONLY = reg_L2_PF_STORE_ONLY
A regOut_L1D_PF_ENABLE_STRIDE = reg_L1D_PF_ENABLE_STRIDE
A regOut_L1D_PF_ACTIVE_STRIDE = reg_L1D_PF_ACTIVE_STRIDE
A regOut_L1D_PF_ACTIVE_THRESHOLD = reg_L1D_PF_ACTIVE_THRESHOLD
A regOut_L1D_PF_ENABLE_PHT = reg_L1D_PF_ENABLE_PHT
A regOut_L1D_PF_ENABLE_AGT = reg_L1D_PF_ENABLE_AGT
A regOut_L1D_PF_TRAIN_ON_HIT = reg_L1D_PF_TRAIN_ON_HIT
A regOut_L1D_PF_ENABLE = reg_L1D_PF_ENABLE
A regOut_L2_PF_ENABLE = reg_L2_PF_ENABLE
A regOut_L1I_PF_ENABLE = reg_L1I_PF_ENABLE
M SlvpredctlModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_LVPRED_TIMEOUT 5
P o regOut_STORESET_NO_FAST_WAKEUP 1
P o regOut_STORESET_WAIT_STORE 1
P o regOut_NO_SPEC_LOAD 1
P o regOut_LVPRED_DISABLE 1
F reg_LVPRED_TIMEOUT 5 3
F reg_STORESET_NO_FAST_WAKEUP 1 0
F reg_STORESET_WAIT_STORE 1 0
F reg_NO_SPEC_LOAD 1 0
F reg_LVPRED_DISABLE 1 0
S reg_LVPRED_TIMEOUT ? w_wen : w_wdata[8:4]
S reg_STORESET_NO_FAST_WAKEUP ? w_wen : w_wdata[3]
S reg_STORESET_WAIT_STORE ? w_wen : w_wdata[2]
S reg_NO_SPEC_LOAD ? w_wen : w_wdata[1]
S reg_LVPRED_DISABLE ? w_wen : w_wdata[0]
A rdata = {55'h0, reg_LVPRED_TIMEOUT, reg_STORESET_NO_FAST_WAKEUP, reg_STORESET_WAIT_STORE, reg_NO_SPEC_LOAD, reg_LVPRED_DISABLE}
A regOut_LVPRED_TIMEOUT = reg_LVPRED_TIMEOUT
A regOut_STORESET_NO_FAST_WAKEUP = reg_STORESET_NO_FAST_WAKEUP
A regOut_STORESET_WAIT_STORE = reg_STORESET_WAIT_STORE
A regOut_NO_SPEC_LOAD = reg_NO_SPEC_LOAD
A regOut_LVPRED_DISABLE = reg_LVPRED_DISABLE
M SmblockctlModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_SBUFFER_TIMEOUT 22
P o regOut_HD_MISALIGN_LD_ENABLE 1
P o regOut_HD_MISALIGN_ST_ENABLE 1
P o regOut_UNCACHE_WRITE_OUTSTANDING_ENABLE 1
P o regOut_CACHE_ERROR_ENABLE 1
P o regOut_SOFT_PREFETCH_ENABLE 1
P o regOut_LDLD_VIO_CHECK_ENABLE 1
P o regOut_SBUFFER_THRESHOLD 4
F reg_SBUFFER_TIMEOUT 22 1048576
F reg_HD_MISALIGN_LD_ENABLE 1 1
F reg_HD_MISALIGN_ST_ENABLE 1 1
F reg_UNCACHE_WRITE_OUTSTANDING_ENABLE 1 0
F reg_CACHE_ERROR_ENABLE 1 1
F reg_SOFT_PREFETCH_ENABLE 1 1
F reg_LDLD_VIO_CHECK_ENABLE 1 1
F reg_SBUFFER_THRESHOLD 4 7
S reg_SBUFFER_TIMEOUT ? w_wen : w_wdata[31:10]
S reg_HD_MISALIGN_LD_ENABLE ? w_wen : w_wdata[9]
S reg_HD_MISALIGN_ST_ENABLE ? w_wen : w_wdata[8]
S reg_UNCACHE_WRITE_OUTSTANDING_ENABLE ? w_wen : w_wdata[7]
S reg_CACHE_ERROR_ENABLE ? w_wen : w_wdata[6]
S reg_SOFT_PREFETCH_ENABLE ? w_wen : w_wdata[5]
S reg_LDLD_VIO_CHECK_ENABLE ? w_wen : w_wdata[4]
S reg_SBUFFER_THRESHOLD ? w_wen : w_wdata[3:0]
A rdata = {32'h0, reg_SBUFFER_TIMEOUT, reg_HD_MISALIGN_LD_ENABLE, reg_HD_MISALIGN_ST_ENABLE, reg_UNCACHE_WRITE_OUTSTANDING_ENABLE, reg_CACHE_ERROR_ENABLE, reg_SOFT_PREFETCH_ENABLE, reg_LDLD_VIO_CHECK_ENABLE, reg_SBUFFER_THRESHOLD}
A regOut_SBUFFER_TIMEOUT = reg_SBUFFER_TIMEOUT
A regOut_HD_MISALIGN_LD_ENABLE = reg_HD_MISALIGN_LD_ENABLE
A regOut_HD_MISALIGN_ST_ENABLE = reg_HD_MISALIGN_ST_ENABLE
A regOut_UNCACHE_WRITE_OUTSTANDING_ENABLE = reg_UNCACHE_WRITE_OUTSTANDING_ENABLE
A regOut_CACHE_ERROR_ENABLE = reg_CACHE_ERROR_ENABLE
A regOut_SOFT_PREFETCH_ENABLE = reg_SOFT_PREFETCH_ENABLE
A regOut_LDLD_VIO_CHECK_ENABLE = reg_LDLD_VIO_CHECK_ENABLE
A regOut_SBUFFER_THRESHOLD = reg_SBUFFER_THRESHOLD
M SrnctlModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_WFI_ENABLE 1
P o regOut_FUSION_ENABLE 1
F reg_WFI_ENABLE 1 1
F reg_FUSION_ENABLE 1 1
S reg_WFI_ENABLE ? w_wen : w_wdata[2]
S reg_FUSION_ENABLE ? w_wen : w_wdata[0]
A rdata = {61'h0, reg_WFI_ENABLE, 1'h0, reg_FUSION_ENABLE}
A regOut_WFI_ENABLE = reg_WFI_ENABLE
A regOut_FUSION_ENABLE = reg_FUSION_ENABLE
M McorepwrModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_COMMIT_STUCK_CHECK_ENABLE 1
P o regOut_POWER_DOWN_ENABLE 1
F reg_COMMIT_STUCK_CHECK_ENABLE 1 0
F reg_POWER_DOWN_ENABLE 1 0
S reg_COMMIT_STUCK_CHECK_ENABLE ? w_wen : w_wdata[1]
S reg_POWER_DOWN_ENABLE ? w_wen : w_wdata[0]
A rdata = {62'h0, reg_COMMIT_STUCK_CHECK_ENABLE, reg_POWER_DOWN_ENABLE}
A regOut_COMMIT_STUCK_CHECK_ENABLE = reg_COMMIT_STUCK_CHECK_ENABLE
A regOut_POWER_DOWN_ENABLE = reg_POWER_DOWN_ENABLE
M MflushpwrModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 64
P o regOut_FLUSH_L2_ENABLE 1
P o regOut_L2_FLUSH_DONE 1
P i l2FlushDone 1
F reg_FLUSH_L2_ENABLE 1 0
S reg_FLUSH_L2_ENABLE ? w_wen : w_wdata[0]
A rdata = {62'h0, l2FlushDone, reg_FLUSH_L2_ENABLE}
A regOut_FLUSH_L2_ENABLE = reg_FLUSH_L2_ENABLE
A regOut_L2_FLUSH_DONE = l2FlushDone
M Pmpcfg0Module n
P o rdata 64
P o regOut_ALL 64
P i cfgRData 64
A rdata = cfgRData
A regOut_ALL = cfgRData
M Pmpcfg2Module n
P o rdata 64
P o regOut_ALL 64
P i cfgRData 64
A rdata = cfgRData
A regOut_ALL = cfgRData
M Pmpcfg4Module n
P o rdata 64
P o regOut_ALL 64
P i cfgRData 64
A rdata = cfgRData
A regOut_ALL = cfgRData
M Pmpcfg6Module n
P o rdata 64
P o regOut_ALL 64
P i cfgRData 64
A rdata = cfgRData
A regOut_ALL = cfgRData
M Pmpcfg8Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpcfg10Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpcfg12Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpcfg14Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmp0cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp1cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp2cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp3cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp4cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp5cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp6cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp7cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp8cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp9cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp10cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp11cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp12cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp13cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp14cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp15cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp16cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp17cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp18cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp19cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp20cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp21cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp22cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp23cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp24cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp25cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp26cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp27cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp28cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp29cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp30cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmp31cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_X ? w_wen : w_wdata[2]
S reg_A ? w_wen : w_wdata[4:3] == 2'h2 ? 2'h3 : w_wdata[4:3]
S reg_L ? w_wen : w_wdata[7]
S reg_W ? w_wen & ~(~(w_wdata[0]) & w_wdata[1]) : w_wdata[1]
A rdata = {reg_L, 2'h0, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_L = reg_L
M Pmpaddr0Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_0 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_0[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr1Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_1 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_1[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr2Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_2 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_2[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr3Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_3 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_3[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr4Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_4 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_4[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr5Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_5 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_5[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr6Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_6 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_6[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr7Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_7 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_7[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr8Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_8 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_8[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr9Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_9 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_9[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr10Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_10 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_10[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr11Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_11 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_11[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr12Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_12 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_12[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr13Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_13 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_13[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr14Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_14 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_14[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr15Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_15 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_15[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr16Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_16 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_16[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr17Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_17 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_17[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr18Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_18 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_18[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr19Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_19 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_19[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr20Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_20 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_20[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr21Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_21 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_21[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr22Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_22 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_22[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr23Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_23 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_23[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr24Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_24 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_24[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr25Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_25 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_25[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr26Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_26 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_26[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr27Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_27 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_27[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr28Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_28 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_28[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr29Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_29 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_29[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr30Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_30 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_30[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr31Module n
P o rdata 64
P o regOut_ADDRESS 46
P i addrRData_31 64
D _regOut_ADDRESS_T 46
A _regOut_ADDRESS_T = addrRData_31[45:0]
A rdata = {18'h0, _regOut_ADDRESS_T}
A regOut_ADDRESS = _regOut_ADDRESS_T
M Pmpaddr32Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr33Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr34Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr35Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr36Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr37Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr38Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr39Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr40Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr41Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr42Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr43Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr44Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr45Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr46Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr47Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr48Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr49Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr50Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr51Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr52Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr53Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr54Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr55Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr56Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr57Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr58Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr59Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr60Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr61Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr62Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmpaddr63Module n
P o rdata 64
P o regOut_ALL 64
A rdata = 64'h0
A regOut_ALL = 64'h0
M Pmacfg0Module n
P o rdata 64
P o regOut_ALL 64
P i cfgRData 64
A rdata = cfgRData
A regOut_ALL = cfgRData
M Pmacfg2Module n
P o rdata 64
P o regOut_ALL 64
P i cfgRData 64
A rdata = cfgRData
A regOut_ALL = cfgRData
M Pmacfg4Module n
P o rdata 64
P o regOut_ALL 64
P i cfgRData 64
A rdata = cfgRData
A regOut_ALL = cfgRData
M Pmacfg6Module n
P o rdata 64
P o regOut_ALL 64
P i cfgRData 64
A rdata = cfgRData
A regOut_ALL = cfgRData
M Pma0cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma1cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma2cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma3cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma4cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma5cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma6cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma7cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma8cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma9cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma10cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma11cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma12cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma13cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma14cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma15cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma16cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma17cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma18cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 0
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma19cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 1
F reg_W 1 1
F reg_X 1 0
F reg_A 2 1
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma20cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 1
F reg_W 1 1
F reg_X 1 1
F reg_A 2 1
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma21cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 1
F reg_W 1 1
F reg_X 1 0
F reg_A 2 1
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma22cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 1
F reg_W 1 1
F reg_X 1 0
F reg_A 2 1
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma23cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 1
F reg_W 1 1
F reg_X 1 0
F reg_A 2 1
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma24cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 1
F reg_W 1 1
F reg_X 1 1
F reg_A 2 1
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma25cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 1
F reg_W 1 1
F reg_X 1 0
F reg_A 2 1
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma26cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 1
F reg_W 1 1
F reg_X 1 0
F reg_A 2 1
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma27cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 1
F reg_W 1 1
F reg_X 1 0
F reg_A 2 1
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma28cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 1
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma29cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 1
F reg_W 1 1
F reg_X 1 0
F reg_A 2 1
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma30cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 1
F reg_W 1 1
F reg_X 1 1
F reg_A 2 1
F reg_ATOMIC 1 1
F reg_C 1 1
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pma31cfgModule a
P i clock 1
P i reset 1
P i w_wen 1
P i w_wdata 64
P o rdata 8
P o regOut_R 1
P o regOut_W 1
P o regOut_X 1
P o regOut_A 2
P o regOut_ATOMIC 1
P o regOut_C 1
P o regOut_L 1
F reg_R 1 0
F reg_W 1 0
F reg_X 1 0
F reg_A 2 3
F reg_ATOMIC 1 0
F reg_C 1 0
F reg_L 1 0
S reg_R ? w_wen : w_wdata[0]
S reg_W ? w_wen : w_wdata[1]
S reg_X ? w_wen : w_wdata[2]
S reg_ATOMIC ? w_wen : w_wdata[5]
S reg_C ? w_wen : w_wdata[6]
S reg_L ? w_wen : w_wdata[7]
S reg_A ? w_wen & (w_wdata[4:3] == 2'h0 | w_wdata[4:3] == 2'h1 | w_wdata[4:3] == 2'h2 | (&(w_wdata[4:3]))) : w_wdata[4:3]
A rdata = {reg_L, reg_C, reg_ATOMIC, reg_A, reg_X, reg_W, reg_R}
A regOut_R = reg_R
A regOut_W = reg_W
A regOut_X = reg_X
A regOut_A = reg_A
A regOut_ATOMIC = reg_ATOMIC
A regOut_C = reg_C
A regOut_L = reg_L
M Pmaaddr0Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_0 64
A rdata = addrRData_0
A regOut_ALL = addrRData_0
M Pmaaddr1Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_1 64
A rdata = addrRData_1
A regOut_ALL = addrRData_1
M Pmaaddr2Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_2 64
A rdata = addrRData_2
A regOut_ALL = addrRData_2
M Pmaaddr3Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_3 64
A rdata = addrRData_3
A regOut_ALL = addrRData_3
M Pmaaddr4Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_4 64
A rdata = addrRData_4
A regOut_ALL = addrRData_4
M Pmaaddr5Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_5 64
A rdata = addrRData_5
A regOut_ALL = addrRData_5
M Pmaaddr6Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_6 64
A rdata = addrRData_6
A regOut_ALL = addrRData_6
M Pmaaddr7Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_7 64
A rdata = addrRData_7
A regOut_ALL = addrRData_7
M Pmaaddr8Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_8 64
A rdata = addrRData_8
A regOut_ALL = addrRData_8
M Pmaaddr9Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_9 64
A rdata = addrRData_9
A regOut_ALL = addrRData_9
M Pmaaddr10Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_10 64
A rdata = addrRData_10
A regOut_ALL = addrRData_10
M Pmaaddr11Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_11 64
A rdata = addrRData_11
A regOut_ALL = addrRData_11
M Pmaaddr12Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_12 64
A rdata = addrRData_12
A regOut_ALL = addrRData_12
M Pmaaddr13Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_13 64
A rdata = addrRData_13
A regOut_ALL = addrRData_13
M Pmaaddr14Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_14 64
A rdata = addrRData_14
A regOut_ALL = addrRData_14
M Pmaaddr15Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_15 64
A rdata = addrRData_15
A regOut_ALL = addrRData_15
M Pmaaddr16Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_16 64
A rdata = addrRData_16
A regOut_ALL = addrRData_16
M Pmaaddr17Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_17 64
A rdata = addrRData_17
A regOut_ALL = addrRData_17
M Pmaaddr18Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_18 64
A rdata = addrRData_18
A regOut_ALL = addrRData_18
M Pmaaddr19Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_19 64
A rdata = addrRData_19
A regOut_ALL = addrRData_19
M Pmaaddr20Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_20 64
A rdata = addrRData_20
A regOut_ALL = addrRData_20
M Pmaaddr21Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_21 64
A rdata = addrRData_21
A regOut_ALL = addrRData_21
M Pmaaddr22Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_22 64
A rdata = addrRData_22
A regOut_ALL = addrRData_22
M Pmaaddr23Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_23 64
A rdata = addrRData_23
A regOut_ALL = addrRData_23
M Pmaaddr24Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_24 64
A rdata = addrRData_24
A regOut_ALL = addrRData_24
M Pmaaddr25Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_25 64
A rdata = addrRData_25
A regOut_ALL = addrRData_25
M Pmaaddr26Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_26 64
A rdata = addrRData_26
A regOut_ALL = addrRData_26
M Pmaaddr27Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_27 64
A rdata = addrRData_27
A regOut_ALL = addrRData_27
M Pmaaddr28Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_28 64
A rdata = addrRData_28
A regOut_ALL = addrRData_28
M Pmaaddr29Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_29 64
A rdata = addrRData_29
A regOut_ALL = addrRData_29
M Pmaaddr30Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_30 64
A rdata = addrRData_30
A regOut_ALL = addrRData_30
M Pmaaddr31Module n
P o rdata 64
P o regOut_ALL 64
P i addrRData_31 64
A rdata = addrRData_31
A regOut_ALL = addrRData_31"""


# One parsed expression: nested tuples whose head names the operator. / 一个解析后的表达式：以运算符名为首的嵌套元组。
CsrExpression = tuple[Any, ...]

# Literal and identifier token shapes used by the manifest. / 清单使用的字面量与标识符记号形状。
CSR_LITERAL_PATTERN = re.compile(r"(\d+)'([hbod])([0-9a-fA-F]+)")
CSR_NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")

# Verilog-subset tokenizer for manifest expressions. / 清单表达式的 Verilog 子集词法器。
CSR_TOKEN_PATTERN = re.compile(
    r"\d+'[hbod][0-9a-fA-F]+"
    r"|\d+"
    r"|[A-Za-z_][A-Za-z_0-9]*"
    r"|==|!=|<<|>>|<=|>=|\|\||&&"
    r"|[&|~!+\-*/%?:{}(),\[\]<>]"
)

# Numeric base for each Verilog literal radix. / 每种 Verilog 字面量进制的数值基数。
CSR_LITERAL_RADIX = {"h": 16, "b": 2, "o": 8, "d": 10}

# Binary precedence, loosest level first. / 二元优先级，最松的层级在前。
CSR_BINARY_LEVELS: tuple[tuple[str, ...], ...] = (
    ("|",),
    ("&",),
    ("==", "!=", "<", ">", "<=", ">="),
    ("+", "-"),
    ("<<", ">>"),
)

# Operator tag stored in the expression tree for each surface token. / 每个表层记号在表达式树中的运算符标签。
CSR_BINARY_TAGS = {
    "|": "or", "&": "and", "^": "xor",
    "==": "eq", "!=": "ne", "<": "lt", ">": "gt", "<=": "le", ">=": "ge",
    "+": "add", "-": "sub", "<<": "shl", ">>": "shr",
    "&&": "logic_and", "||": "logic_or",
}

# Reduction operator tag for each prefix token. / 每个前缀记号的归约运算符标签。
CSR_REDUCE_TAGS = {"&": "reduce_and", "|": "reduce_or", "^": "reduce_xor"}

# Manifest reset-mode letters mapped onto domain descriptions. / 清单复位模式字母到时钟域描述的映射。
CSR_RESET_KINDS = {"a": "async", "n": "none"}


# Split manifest text into expression tokens. / 将清单文本切分为表达式记号。
def csr_expression_tokens(text: str) -> list[str]:
    """Tokenize one manifest expression. / 对一个清单表达式做词法分析。"""

    return CSR_TOKEN_PATTERN.findall(text)


class CsrExpressionParser:
    """Recursive-descent parser for the manifest expression subset. / 清单表达式子集的递归下降解析器。"""

    # Bind the token sequence and the read cursor. / 绑定记号序列与读取游标。
    def __init__(self, tokens: list[str]) -> None:
        """Store tokens for one expression. / 保存单个表达式的记号。"""

        self.tokens = tokens
        self.cursor = 0

    # Return the current token without consuming it. / 返回当前记号但不消费。
    def peek(self) -> str | None:
        """Inspect the next token. / 查看下一个记号。"""

        return self.tokens[self.cursor] if self.cursor < len(self.tokens) else None

    # Consume and return the current token. / 消费并返回当前记号。
    def take(self) -> str:
        """Consume the next token. / 消费下一个记号。"""

        token = self.tokens[self.cursor]
        self.cursor += 1
        return token

    # Parse one expression and require every token to be consumed. / 解析一个表达式并要求所有记号被消费。
    def parse(self) -> CsrExpression:
        """Return the expression tree. / 返回表达式树。"""

        node = self.parse_ternary()
        if self.cursor != len(self.tokens):
            raise ValueError("unparsed manifest tokens: " + " ".join(self.tokens[self.cursor:]))
        return node

    # Parse the right-associative conditional operator. / 解析右结合三目运算符。
    def parse_ternary(self) -> CsrExpression:
        """Return a conditional or the next lower precedence node. / 返回条件表达式或更低优先级节点。"""

        node = self.parse_binary(0)
        if self.peek() == "?":
            self.take()
            when_true = self.parse_ternary()
            if self.take() != ":":
                raise ValueError("manifest conditional without ':'")
            return ("ite", node, when_true, self.parse_ternary())
        return node

    # Parse one binary precedence level, recursing to the tighter level. / 解析一个二元优先级层，递归到更紧的层。
    def parse_binary(self, level: int) -> CsrExpression:
        """Return one binary expression at ``level``. / 返回 ``level`` 层的一个二元表达式。"""

        if level == len(CSR_BINARY_LEVELS):
            return self.parse_unary()
        node = self.parse_binary(level + 1)
        while self.peek() in CSR_BINARY_LEVELS[level]:
            operator = self.take()
            node = (CSR_BINARY_TAGS[operator], node, self.parse_binary(level + 1))
        return node

    # Parse a prefix negation, reduction or arithmetic negation. / 解析前缀取反、归约或算术取负。
    def parse_unary(self) -> CsrExpression:
        """Return a prefix operator application or a primary. / 返回前缀运算符应用或基本表达式。"""

        token = self.peek()
        if token in ("~", "!"):
            self.take()
            return ("bitnot" if token == "~" else "logic_not", self.parse_unary())
        if token in CSR_REDUCE_TAGS:
            self.take()
            return (CSR_REDUCE_TAGS[token], self.parse_unary())
        if token == "-":
            self.take()
            return ("neg", self.parse_unary())
        return self.parse_primary()

    # Parse a literal, signal, slice, concatenation or parenthesised term. / 解析字面量、信号、切片、拼接或括号项。
    def parse_primary(self) -> CsrExpression:
        """Return one primary expression node. / 返回一个基本表达式节点。"""

        token = self.peek()
        if token is None:
            raise ValueError("manifest expression ended early")
        self.take()
        if token == "(":
            node = self.parse_ternary()
            if self.take() != ")":
                raise ValueError("unbalanced manifest parentheses")
            return node
        if token == "{":
            # Verilog replication ``{n{expr}}`` shares the concatenation
            # opener, so it is discriminated by a leading decimal count.
            # Verilog 复制 ``{n{expr}}`` 与拼接共用左花括号，用前导十进制计数区分。
            following = self.peek()
            if following is not None and following.isdigit() and self.tokens[self.cursor + 1:self.cursor + 2] == ["{"]:
                count = int(self.take())
                self.take()
                part = self.parse_ternary()
                if self.take() != "}" or self.take() != "}":
                    raise ValueError("unbalanced manifest replication")
                return ("repeat", count, part)
            parts = [self.parse_ternary()]
            while self.peek() == ",":
                self.take()
                parts.append(self.parse_ternary())
            if self.take() != "}":
                raise ValueError("unbalanced manifest concatenation")
            return ("concat", tuple(parts))
        literal = CSR_LITERAL_PATTERN.fullmatch(token)
        if literal:
            return ("literal", int(literal.group(1)), int(literal.group(3), CSR_LITERAL_RADIX[literal.group(2)]))
        if token.isdigit():
            return ("literal", 32, int(token))
        if CSR_NAME_PATTERN.fullmatch(token):
            if self.peek() != "[":
                return ("signal", token)
            self.take()
            msb = int(self.take())
            lsb = msb
            if self.peek() == ":":
                self.take()
                lsb = int(self.take())
            if self.take() != "]":
                raise ValueError("unbalanced manifest slice")
            return ("slice", token, msb, lsb)
        raise ValueError("unexpected manifest token: " + token)


# Parse one manifest expression into its tree form. / 将一个清单表达式解析为树形式。
def csr_expression_parse(text: str) -> CsrExpression:
    """Parse a manifest expression. / 解析一个清单表达式。"""

    return CsrExpressionParser(csr_expression_tokens(text)).parse()


# Translate one parsed expression into an Amaranth value. / 将一个解析后的表达式转换为 Amaranth 值。
def csr_expression_value(node: CsrExpression, signals: dict[str, Value]) -> Value:
    """Evaluate a manifest expression over the elaborated signals. / 在已展开信号上求值清单表达式。"""

    tag = node[0]
    if tag == "literal":
        return Const(node[2], node[1])
    if tag == "signal":
        return signals[node[1]]
    if tag == "slice":
        signal = signals[node[1]]
        msb, lsb = int(node[2]), int(node[3])
        # Amaranth returns the narrower ``Slice`` type for the dynamic slice
        # operators; widening to ``Value`` is the documented dynamic boundary.
        # Amaranth 的动态切片运算符返回更窄的 ``Slice`` 类型；扩宽为 ``Value``
        # 是文档允许的动态边界。
        return cast(Value, signal[lsb] if msb == lsb else signal[lsb:msb + 1])
    if tag == "concat":
        return cast(Value, Cat(*[csr_expression_value(part, signals) for part in reversed(node[1])]))
    if tag == "repeat":
        return cast(Value, csr_expression_value(node[2], signals).replicate(int(node[1])))
    if tag == "ite":
        return Mux(csr_expression_value(node[1], signals),
                   csr_expression_value(node[2], signals),
                   csr_expression_value(node[3], signals))
    if tag == "neg":
        return -csr_expression_value(node[1], signals)
    if tag in ("bitnot", "logic_not", "reduce_and", "reduce_or", "reduce_xor"):
        operand = csr_expression_value(node[1], signals)
        if tag == "bitnot":
            return ~operand
        if tag == "logic_not":
            return operand == 0
        if tag == "reduce_and":
            return operand.all()
        if tag == "reduce_or":
            return operand.any()
        return operand.xor()
    left = csr_expression_value(node[1], signals)
    right = csr_expression_value(node[2], signals)
    if tag == "or":
        return left | right
    if tag == "and":
        return left & right
    if tag == "xor":
        return left ^ right
    if tag == "logic_or":
        return (left != 0) | (right != 0)
    if tag == "logic_and":
        return (left != 0) & (right != 0)
    if tag == "eq":
        return left == right
    if tag == "ne":
        return left != right
    if tag == "lt":
        return left < right
    if tag == "gt":
        return left > right
    if tag == "le":
        return left <= right
    if tag == "ge":
        return left >= right
    if tag == "add":
        return left + right
    if tag == "sub":
        return left - right
    if tag == "shl":
        return left << right
    if tag == "shr":
        return left >> right
    raise ValueError("unsupported manifest operator: " + str(tag))


# One locked module port in locked order. / 按锁定顺序排列的一个锁定模块端口。
@dataclass(frozen=True)
class CsrPortSpec:
    """Describe one locked CSRModule port. / 描述一个锁定 CSRModule 端口。"""

    name: str
    direction: str
    width: int


# One sequential register of a CSRModule instance. / 一个 CSRModule 实例的一个时序寄存器。
@dataclass(frozen=True)
class CsrFieldSpec:
    """Describe one register and its reset value. / 描述一个寄存器及其复位值。"""

    name: str
    width: int
    init: int | None


# One combinational signal introduced by the manifest. / 清单引入的一个组合信号。
@dataclass(frozen=True)
class CsrWireSpec:
    """Describe a declared combinational signal. / 描述一个已声明的组合信号。"""

    name: str
    width: int
    value: CsrExpression | None
    text: str


# One continuous assignment of the locked module. / 锁定模块的一条连续赋值。
@dataclass(frozen=True)
class CsrAssignSpec:
    """Describe a continuous assignment. / 描述一条连续赋值。"""

    target: str
    value: CsrExpression
    text: str


# One guarded update of a register or a temporary. / 寄存器或临时量的一条带条件更新。
@dataclass(frozen=True)
class CsrRuleSpec:
    """Describe one guarded update and its kind. / 描述一条带条件更新及其类别。"""

    target: str
    guard: CsrExpression
    value: CsrExpression
    combinational: bool
    guard_text: str
    value_text: str


# The complete locked behaviour of one CSRModule instance. / 一个 CSRModule 实例的完整锁定行为。
@dataclass(frozen=True)
class CsrModuleSpec:
    """Describe one covered locked CSRModule. / 描述一个已覆盖的锁定 CSRModule。"""

    name: str
    reset_kind: str
    ports: tuple[CsrPortSpec, ...]
    fields: tuple[CsrFieldSpec, ...]
    wires: tuple[CsrWireSpec, ...]
    assigns: tuple[CsrAssignSpec, ...]
    rules: tuple[CsrRuleSpec, ...]

    # Report the locked port order and geometry. / 报告锁定端口顺序与几何。
    def port_specs(self) -> tuple[tuple[str, str, int], ...]:
        """Return (name, direction, width) per locked port. / 返回每个锁定端口的名称、方向与位宽。"""

        return tuple((port.name, port.direction, port.width) for port in self.ports)

    # Report the sequential register names. / 报告时序寄存器名称。
    def register_names(self) -> tuple[str, ...]:
        """Return the register names in manifest order. / 按清单顺序返回寄存器名称。"""

        return tuple(field.name for field in self.fields)

    # Report whether the locked module carries an asynchronous reset pin. / 报告锁定模块是否带异步复位引脚。
    def has_reset(self) -> bool:
        """Return True when the module exposes ``reset``. / 当模块暴露 ``reset`` 时返回 True。"""

        return any(port.name == "reset" for port in self.ports)


# Split one manifest block line into its leading kind and payload. / 将一行清单块拆分为行种类与载荷。
def csr_manifest_line(line: str) -> tuple[str, str]:
    """Return the line kind and the remaining payload. / 返回行种类与其余载荷。"""

    kind = line[:1]
    return kind, line[2:] if len(line) > 2 else ""


# Decode the manifest text into one specification per covered module. / 将清单文本解码为每个已覆盖模块的规格。
def csr_manifest_decode(text: str) -> dict[str, CsrModuleSpec]:
    """Decode the family manifest. / 解码家族清单。"""

    decoded: dict[str, CsrModuleSpec] = {}
    order: list[str] = []
    name = ""
    reset_kind = ""
    ports: list[CsrPortSpec] = []
    fields: list[CsrFieldSpec] = []
    wires: list[CsrWireSpec] = []
    assigns: list[CsrAssignSpec] = []
    rules: list[CsrRuleSpec] = []

    # Flush the block currently being accumulated. / 提交当前累积的清单块。
    def flush() -> None:
        if not name:
            return
        decoded[name] = CsrModuleSpec(name, reset_kind, tuple(ports), tuple(fields),
                                      tuple(wires), tuple(assigns), tuple(rules))

    for raw in text.splitlines():
        if not raw:
            continue
        kind, payload = csr_manifest_line(raw)
        if kind == "M":
            flush()
            module_name, mode = payload.split()
            if mode not in CSR_RESET_KINDS:
                raise ValueError("unknown manifest reset mode: " + mode)
            name, reset_kind = module_name, CSR_RESET_KINDS[mode]
            order.append(name)
            ports, fields, wires, assigns, rules = [], [], [], [], []
        elif kind == "P":
            direction, port_name, width = payload.split()
            ports.append(CsrPortSpec(port_name, "input" if direction == "i" else "output", int(width)))
        elif kind == "F":
            field_name, width, init = payload.split()
            fields.append(CsrFieldSpec(field_name, int(width), None if init == "-" else int(init)))
        elif kind == "W":
            head, expression = payload.split(" = ", 1)
            wire_name, width = head.split()
            wires.append(CsrWireSpec(wire_name, int(width), csr_expression_parse(expression),
                                     expression))
        elif kind == "D":
            wire_name, width = payload.split()
            wires.append(CsrWireSpec(wire_name, int(width), None, ""))
        elif kind == "V":
            if " ? " in payload:
                target, rest = payload.split(" ? ", 1)
                guard, value = rest.split(" : ", 1)
                rules.append(CsrRuleSpec(target, csr_expression_parse(guard),
                                         csr_expression_parse(value), True, guard, value))
            elif " = " in payload:
                head, expression = payload.split(" = ", 1)
                wire_name, width = head.split()
                wires.append(CsrWireSpec(wire_name, int(width), csr_expression_parse(expression),
                                         expression))
            else:
                wire_name, width = payload.split()
                wires.append(CsrWireSpec(wire_name, int(width), None, ""))
        elif kind == "S":
            target, rest = payload.split(" ? ", 1)
            guard, value = rest.split(" : ", 1)
            rules.append(CsrRuleSpec(target, csr_expression_parse(guard),
                                     csr_expression_parse(value), False, guard, value))
        elif kind == "A":
            target, value = payload.split(" = ", 1)
            assigns.append(CsrAssignSpec(target, csr_expression_parse(value), value))
        else:
            raise ValueError("unknown manifest line kind: " + kind)
    flush()
    return {module: decoded[module] for module in order}


# Decoded registry of every module covered by this aggregate. / 本聚合覆盖的全部模块的解码注册表。
CSR_FAMILY_MODULES: dict[str, CsrModuleSpec] = csr_manifest_decode(CSR_FAMILY_MANIFEST)

# Number of locked modules covered by this aggregate. / 本聚合覆盖的锁定模块数量。
CSR_FAMILY_MODULE_COUNT: int = len(CSR_FAMILY_MODULES)


# Return every covered module name in manifest order. / 按清单顺序返回全部已覆盖模块名。
def csr_family_module_names() -> tuple[str, ...]:
    """Return the covered locked module names. / 返回已覆盖的锁定模块名。"""

    return tuple(CSR_FAMILY_MODULES)


# Return the number of covered locked modules. / 返回已覆盖的锁定模块数量。
def csr_family_module_count() -> int:
    """Return the covered module count. / 返回已覆盖模块数量。"""

    return CSR_FAMILY_MODULE_COUNT


# Return the decoded specification of one covered module. / 返回一个已覆盖模块的解码规格。
def csr_module_spec(name: str) -> CsrModuleSpec:
    """Look up one covered module. / 查找一个已覆盖模块。"""

    if name not in CSR_FAMILY_MODULES:
        raise KeyError("module is not covered by this family file: " + name)
    return CSR_FAMILY_MODULES[name]


# Return the locked port order of one covered module. / 返回一个已覆盖模块的锁定端口顺序。
def csr_module_port_specs(name: str) -> tuple[tuple[str, str, int], ...]:
    """Return (name, direction, width) per locked port. / 返回每个锁定端口的名称、方向与位宽。"""

    return csr_module_spec(name).port_specs()


# =============================================================================
# Implementation
# =============================================================================
class CSRModule(Elaboratable):
    """Parameterised register file of one locked CSRModule instance. / 一个锁定 CSRModule 实例的参数化寄存器组。"""

    # Create every locked port, register and combinational signal. / 创建全部锁定端口、寄存器与组合信号。
    def __init__(self, spec: CsrModuleSpec) -> None:
        """Bind one decoded specification. / 绑定一个解码规格。"""

        self.spec = spec
        self.ports: dict[str, Signal] = {}
        for port in spec.ports:
            self.ports[port.name] = Signal(port.width, name=port.name)
        self.registers: dict[str, Signal] = {}
        for field in spec.fields:
            if field.init is None:
                # Chisel ``Reg`` without an init has no reset branch at all.
                # Chisel 的无初值 ``Reg`` 完全没有复位分支。
                self.registers[field.name] = Signal(field.width, name=field.name, reset_less=True)
            else:
                # Chisel ``RegInit(bundle, bundle.init)`` resets every field,
                # using zero for the fields whose init literal is null.
                # Chisel 的 ``RegInit`` 复位全部字段，初值字面量为空的字段复位为 0。
                self.registers[field.name] = Signal(field.width, name=field.name, reset=field.init)
        self.signals: dict[str, Value] = dict(self.ports)
        self.signals.update(self.registers)
        for wire in spec.wires:
            if wire.name not in self.signals:
                self.signals[wire.name] = Signal(wire.width, name=wire.name)
        # Read-only CSRs such as MhartidModule are combinational and carry no
        # clock pin at all; they are covered by the same manifest without a
        # clock domain and must not contain sequential rules.
        # 例如 MhartidModule 之类的只读 CSR 是纯组合逻辑，完全没有时钟引脚；它们
        # 由同一清单覆盖但不含时钟域，且不得包含时序规则。
        self.clock: Signal | None = self.ports.get("clock")
        self.has_clock = self.clock is not None
        self.sequential_rules = tuple(rule for rule in spec.rules if not rule.combinational)
        if self.sequential_rules and not self.has_clock:
            raise ValueError("sequential rules without a clock pin: " + spec.name)
        self.reset_tied = self.has_clock and not spec.has_reset()
        if not self.has_clock:
            self.reset = Signal(name="csr_reset_unused", reset_less=True)
        elif self.reset_tied:
            self.reset = Signal(name="csr_reset_tie", reset_less=True)
        else:
            self.reset = self.ports["reset"]

    # Elaborate the locked register, wire and assignment network. / 展开锁定的寄存器、线网与赋值网络。
    def elaborate(self, platform: Any) -> Module:
        """Build the Amaranth module for one CSRModule. / 为一个 CSRModule 构建 Amaranth 模块。"""

        del platform
        module = Module()
        spec = self.spec
        if self.has_clock:
            # Chisel drives this family from one domain; the locked SV uses an
            # asynchronous, active-high reset exactly when the bundle needs
            # reset, and a tied-off reset when the bundle does not.
            # Chisel 让本家族处于单一时钟域；当 bundle 需要复位时，锁定 SV 使用
            # 异步、高有效复位；不需要复位时复位被恒定拉低。
            domain = ClockDomain("sync", async_reset=spec.reset_kind == "async")
            domain.clk = cast(Signal, self.clock)
            domain.rst = self.reset
            module.domains += domain
            if self.reset_tied:
                module.d.comb += self.reset.eq(0)
        for wire in spec.wires:
            if wire.value is not None:
                module.d.comb += self.signals[wire.name].eq(csr_expression_value(wire.value, self.signals))
        # Lowest-priority rule first so that the last Amaranth assignment wins
        # for the highest-priority Chisel ``when`` branch.
        # 先展开最低优先级规则，使 Amaranth 的“后写者胜”对应 Chisel 最高优先级分支。
        for rule in reversed(spec.rules):
            guard = csr_expression_value(rule.guard, self.signals)
            value = csr_expression_value(rule.value, self.signals)
            target = self.signals[rule.target]
            with cast(Any, module.If(guard)):
                if rule.combinational:
                    module.d.comb += target.eq(value)
                else:
                    module.d.sync += target.eq(value)
        for assign in spec.assigns:
            module.d.comb += self.signals[assign.target].eq(csr_expression_value(assign.value, self.signals))
        return module


# =============================================================================
# Public Adapter
# =============================================================================
@dataclass(frozen=True)
class CsrModuleFamilyConfig:
    """Select which covered modules the adapter exports. / 选择适配器导出哪些已覆盖模块。"""

    modules: tuple[str, ...] = ()

    # Reject names outside the covered family early and explicitly. / 尽早显式拒绝家族之外的名称。
    def __post_init__(self) -> None:
        unknown = [name for name in self.modules if name not in CSR_FAMILY_MODULES]
        if unknown:
            raise ValueError("modules outside the covered family: " + ", ".join(unknown))


# Re-order the emitted module header into the locked V2 port order. / 将输出的模块头部重排为锁定 V2 端口顺序。
def csr_module_port_order(text: str, name: str, locked: tuple[str, ...]) -> str:
    """Permute the emitted header port list into locked order. / 将输出头部的端口列表重排为锁定顺序。"""

    # Amaranth reaches Verilog through Yosys, which regroups the header by
    # direction (clock last) and therefore loses the locked positional order
    # that Verilog instantiation depends on.  Only the header name list is
    # permuted here; every declaration, width and direction inside the body is
    # left exactly as the backend emitted it, so the module is unchanged.
    # Amaranth 经 Yosys 生成 Verilog，Yosys 会按方向重排头部（时钟置后），
    # 因而丢失 Verilog 实例化所依赖的锁定位置顺序。此处只重排头部的名称列表，
    # 模块体内部的声明、位宽与方向完全保持后端输出不变，模块语义不变。
    pattern = re.compile(r"(^module\s+" + re.escape(name) + r"\s*\()([^)]*)(\);)", re.M)
    match = pattern.search(text)
    if match is None:
        raise ValueError("generated module header not found for " + name)
    emitted = [item.strip() for item in match.group(2).split(",") if item.strip()]
    if sorted(emitted) != sorted(locked):
        raise ValueError("generated port set differs from the locked port set for " + name)
    return text[:match.start(2)] + ", ".join(locked) + text[match.end(2):]


# Elaborate one covered module and return its Verilog definition. / 展开一个已覆盖模块并返回其 Verilog 定义。
def csr_module_verilog(name: str) -> str:
    """Emit deterministic Verilog for one covered module. / 为一个已覆盖模块输出确定性 Verilog。"""

    spec = csr_module_spec(name)
    top = CSRModule(spec)
    ports = [top.ports[port.name] for port in spec.ports]
    emitted = verilog.convert(top, name=name, ports=ports, emit_src=False)
    return csr_module_port_order(emitted, name, tuple(port.name for port in spec.ports))


# Emit the requested module selection in manifest order. / 按清单顺序输出所请求的模块选择。
def csr_family_verilog(names: tuple[str, ...]) -> str:
    """Concatenate the requested module definitions. / 拼接所请求的模块定义。"""

    banner = ("// CSR_MODULE_FAMILY covered={} requested={} source=XSTop.sv\n"
              .format(CSR_FAMILY_MODULE_COUNT, len(names)))
    return banner + "\n".join(csr_module_verilog(name) for name in names)


# Resolve the adapter configuration into a covered-module selection. / 将适配器配置解析为已覆盖模块选择。
def csr_family_selection(configuration: Any, injected_dependencies: Any) -> tuple[str, ...]:
    """Return the module names to emit. / 返回需要输出的模块名。"""

    del injected_dependencies
    if configuration is None:
        return csr_family_module_names()
    if isinstance(configuration, CsrModuleFamilyConfig):
        return configuration.modules or csr_family_module_names()
    if isinstance(configuration, str):
        return (configuration,)
    if isinstance(configuration, dict):
        selected = configuration.get("module", configuration.get("name"))
        if selected is not None:
            return (str(selected),)
        listed = configuration.get("modules")
        if listed is not None:
            return tuple(str(item) for item in listed)
        return csr_family_module_names()
    return csr_family_module_names()


# Emit the family export selected by ``configuration``. / 输出由 ``configuration`` 选择的家族导出。
def build_verilog(configuration, injected_dependencies):
    """Return Verilog for the requested covered CSRModule set. / 返回所请求已覆盖 CSRModule 集合的 Verilog。"""

    return csr_family_verilog(csr_family_selection(configuration, injected_dependencies))


# =============================================================================
# Direct Entry
# =============================================================================
# Print the default family export for a direct smoke invocation. / 直接 smoke 调用时打印默认家族导出。
def main() -> None:
    """Print generated Verilog. / 打印生成的 Verilog。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()

