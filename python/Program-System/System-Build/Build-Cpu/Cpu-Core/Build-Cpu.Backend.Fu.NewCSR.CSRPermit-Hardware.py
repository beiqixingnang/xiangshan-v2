"""UHSC V2 CSR permission and return-trap family.
UHSC V2 CSR 权限与返回陷阱 family。

This aggregate is a flattened Amaranth transcription of CSRPermitModule.scala
and its six permit submodules.  The port catalog is taken from the locked V2
hierarchy; all decisions remain combinational and parameter-free at the
hardware boundary, matching the Chisel implementation's CSR address tests.
此聚合将 CSRPermitModule.scala 及其六个权限子模块展平为 Amaranth 实现。端口目录
来自锁定 V2 层级；所有决策在硬件边界保持组合、无参数，匹配 Chisel 的 CSR 地址判断。
"""

from __future__ import annotations

import json
from typing import Any, cast

from amaranth import Const, Elaboratable, Module, Mux, Signal, Value
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# Every member uses the exact locked ANSI names and widths. / 每个成员使用锁定 ANSI 名称与位宽。
__all__ = ["COVERED_MODULES", "PermitModule", "build_verilog", "main"]

HIERARCHY = "validation/v2-locked-hierarchy.json"
SOURCE_PATHS = (
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/CSRPermitModule.scala",
)

_PORTS: dict[str, tuple[tuple[str, str, int], ...]] = {
    "CSRPermitModule": (
        ("io_in_csrAccess_ren", "input", 1), ("io_in_csrAccess_wen", "input", 1), ("io_in_csrAccess_addr", "input", 12),
        ("io_in_privState_PRVM", "input", 2), ("io_in_privState_V", "input", 1), ("io_in_debugMode", "input", 1),
        ("io_in_xRet_mnret", "input", 1), ("io_in_xRet_mret", "input", 1), ("io_in_xRet_sret", "input", 1), ("io_in_xRet_dret", "input", 1),
        ("io_in_status_tsr", "input", 1), ("io_in_status_vtsr", "input", 1), ("io_in_status_tvm", "input", 1), ("io_in_status_vtvm", "input", 1), ("io_in_status_vgein", "input", 6),
        ("io_in_status_mstatusFSOff", "input", 1), ("io_in_status_vsstatusFSOff", "input", 1), ("io_in_status_mstatusVSOff", "input", 1), ("io_in_status_vsstatusVSOff", "input", 1),
        ("io_in_xcounteren_mcounteren", "input", 32), ("io_in_xcounteren_hcounteren", "input", 32), ("io_in_xcounteren_scounteren", "input", 32),
        ("io_in_xenvcfg_menvcfg", "input", 64), ("io_in_xenvcfg_henvcfg", "input", 64),
        ("io_in_xstateen_mstateen0_SE0", "input", 1), ("io_in_xstateen_mstateen0_ENVCFG", "input", 1), ("io_in_xstateen_mstateen0_CSRIND", "input", 1), ("io_in_xstateen_mstateen0_AIA", "input", 1), ("io_in_xstateen_mstateen0_IMSIC", "input", 1), ("io_in_xstateen_mstateen0_CONTEXT", "input", 1), ("io_in_xstateen_mstateen0_C", "input", 1),
        ("io_in_xstateen_mstateen1_SE", "input", 1), ("io_in_xstateen_mstateen2_SE", "input", 1), ("io_in_xstateen_mstateen3_SE", "input", 1),
        ("io_in_xstateen_hstateen0_C", "input", 1), ("io_in_xstateen_hstateen0_SE0", "input", 1), ("io_in_xstateen_hstateen0_ENVCFG", "input", 1), ("io_in_xstateen_hstateen0_CSRIND", "input", 1), ("io_in_xstateen_hstateen0_AIA", "input", 1), ("io_in_xstateen_hstateen0_IMSIC", "input", 1), ("io_in_xstateen_hstateen0_CONTEXT", "input", 1),
        ("io_in_xstateen_hstateen1_SE", "input", 1), ("io_in_xstateen_hstateen2_SE", "input", 1), ("io_in_xstateen_hstateen3_SE", "input", 1),
        ("io_in_xstateen_sstateen0_C", "input", 1),
        ("io_in_aia_miselect", "input", 64), ("io_in_aia_siselect", "input", 64), ("io_in_aia_vsiselect", "input", 64), ("io_in_aia_mvienSEIE", "input", 1), ("io_in_aia_hvictlVTI", "input", 1),
        ("io_out_hasLegalWen", "output", 1), ("io_out_hasLegalMNret", "output", 1), ("io_out_hasLegalMret", "output", 1), ("io_out_hasLegalSret", "output", 1), ("io_out_hasLegalDret", "output", 1), ("io_out_hasLegalWriteFcsr", "output", 1), ("io_out_hasLegalWriteVcsr", "output", 1), ("io_out_EX_II", "output", 1), ("io_out_EX_VI", "output", 1),
    ),
    "IndirectCSRPermitModule": (
        ("io_in_csrAccess_addr", "input", 12), ("io_in_privState_PRVM", "input", 2), ("io_in_privState_V", "input", 1), ("io_in_aia_miselect", "input", 64), ("io_in_aia_siselect", "input", 64), ("io_in_aia_vsiselect", "input", 64), ("io_in_aia_mvienSEIE", "input", 1), ("io_in_xstateen_mstateen0_AIA", "input", 1), ("io_in_xstateen_mstateen0_IMSIC", "input", 1), ("io_in_xstateen_hstateen0_IMSIC", "input", 1), ("io_out_indirectCSR_EX_II", "output", 1), ("io_out_indirectCSR_EX_VI", "output", 1),
    ),
    "MLevelPermitModule": (
        ("io_in_csrAccess_wen", "input", 1), ("io_in_csrAccess_addr", "input", 12), ("io_in_privState_PRVM", "input", 2), ("io_in_privState_V", "input", 1), ("io_in_status_tvm", "input", 1), ("io_in_status_mstatusFSOff", "input", 1), ("io_in_status_vsstatusFSOff", "input", 1), ("io_in_status_mstatusVSOff", "input", 1), ("io_in_status_vsstatusVSOff", "input", 1), ("io_in_xcounteren_mcounteren", "input", 32), ("io_in_xenvcfg_menvcfg", "input", 64), ("io_in_xstateen_mstateen0_SE0", "input", 1), ("io_in_xstateen_mstateen0_ENVCFG", "input", 1), ("io_in_xstateen_mstateen0_CSRIND", "input", 1), ("io_in_xstateen_mstateen0_AIA", "input", 1), ("io_in_xstateen_mstateen0_IMSIC", "input", 1), ("io_in_xstateen_mstateen0_CONTEXT", "input", 1), ("io_in_xstateen_mstateen0_C", "input", 1), ("io_in_xstateen_mstateen1_SE", "input", 1), ("io_in_xstateen_mstateen2_SE", "input", 1), ("io_in_xstateen_mstateen3_SE", "input", 1), ("io_in_aia_mvienSEIE", "input", 1), ("io_out_mLevelPermit_EX_II", "output", 1), ("io_out_hasLegalWriteFcsr", "output", 1), ("io_out_hasLegalWriteVcsr", "output", 1),
    ),
    "PrivilegePermitModule": (
        ("io_in_csrAccess_addr", "input", 12), ("io_in_privState_PRVM", "input", 2), ("io_in_privState_V", "input", 1), ("io_in_debugMode", "input", 1), ("io_out_privilege_EX_II", "output", 1), ("io_out_privilege_EX_VI", "output", 1),
    ),
    "SLevelPermitModule": (
        ("io_in_csrAccess_addr", "input", 12), ("io_in_privState_PRVM", "input", 2), ("io_in_privState_V", "input", 1), ("io_in_xcounteren_scounteren", "input", 32), ("io_in_xstateen_sstateen0_C", "input", 1), ("io_out_sLevelPermit_EX_II", "output", 1),
    ),
    "VirtualLevelPermitModule": (
        ("io_in_csrAccess_wen", "input", 1), ("io_in_csrAccess_addr", "input", 12), ("io_in_privState_PRVM", "input", 2), ("io_in_privState_V", "input", 1), ("io_in_status_vtvm", "input", 1), ("io_in_status_vgein", "input", 6), ("io_in_xcounteren_hcounteren", "input", 32), ("io_in_xcounteren_scounteren", "input", 32), ("io_in_xenvcfg_henvcfg", "input", 64), ("io_in_xstateen_hstateen0_C", "input", 1), ("io_in_xstateen_hstateen0_SE0", "input", 1), ("io_in_xstateen_hstateen0_ENVCFG", "input", 1), ("io_in_xstateen_hstateen0_CSRIND", "input", 1), ("io_in_xstateen_hstateen0_AIA", "input", 1), ("io_in_xstateen_hstateen0_IMSIC", "input", 1), ("io_in_xstateen_hstateen0_CONTEXT", "input", 1), ("io_in_xstateen_hstateen1_SE", "input", 1), ("io_in_xstateen_hstateen2_SE", "input", 1), ("io_in_xstateen_hstateen3_SE", "input", 1), ("io_in_xstateen_sstateen0_C", "input", 1), ("io_in_aia_hvictlVTI", "input", 1), ("io_out_virtualLevelPermit_EX_II", "output", 1), ("io_out_virtualLevelPermit_EX_VI", "output", 1),
    ),
    "XRetPermitModule": (
        ("io_in_privState_PRVM", "input", 2), ("io_in_privState_V", "input", 1), ("io_in_debugMode", "input", 1), ("io_in_xRet_mnret", "input", 1), ("io_in_xRet_mret", "input", 1), ("io_in_xRet_sret", "input", 1), ("io_in_xRet_dret", "input", 1), ("io_in_status_tsr", "input", 1), ("io_in_status_vtsr", "input", 1), ("io_out_Xret_EX_II", "output", 1), ("io_out_Xret_EX_VI", "output", 1), ("io_out_hasLegalMNret", "output", 1), ("io_out_hasLegalMret", "output", 1), ("io_out_hasLegalSret", "output", 1), ("io_out_hasLegalDret", "output", 1),
    ),
}

COVERED_MODULES: tuple[str, ...] = tuple(_PORTS)


# =============================================================================
# Configuration
# =============================================================================
# CSR addresses used by the V2 permission equations. / V2 权限方程使用的 CSR 地址。
CSR_CYCLE = 0xC00
CSR_HPMCOUNTER31 = 0xC1F
CSR_FFLAGS, CSR_FRM, CSR_FCSR = 0x001, 0x002, 0x003
CSR_VSTART, CSR_VXSAT, CSR_VXRM, CSR_VCSR, CSR_VTYPE = 0x008, 0x009, 0x00A, 0x00F, 0xC21
CSR_SATP, CSR_HGATP = 0x180, 0x680
CSR_STIMECMP, CSR_VSTIMECMP = 0x14D, 0x24D
CSR_SIE, CSR_SIP = 0x104, 0x144
CSR_SENVCFG, CSR_HENVCFG = 0x10A, 0x60A
CSR_SSTATEEN0, CSR_HSTATEEN0 = 0x10C, 0x60C
CSR_SISELECT, CSR_SIREG, CSR_SIREG6, CSR_SIPH = 0x150, 0x151, 0x157, 0x154
CSR_VSISELECT, CSR_VSIREG, CSR_VSIREG6, CSR_VSIPH = 0x250, 0x251, 0x257, 0x254
CSR_MIREG, CSR_MIREG6, CSR_MIPH = 0x351, 0x357, 0x354
CSR_STOPEI, CSR_VSTOPEI = 0x15C, 0x25C
CSR_HVIEN, CSR_HVICTL, CSR_HVIPRIO1, CSR_HVIPRIO2 = 0x608, 0x609, 0x646, 0x647
CSR_SCONTEXT, CSR_HCONTEXT = 0x5A8, 0x6A8
CSR_STOPI, CSR_VSTOPI = 0xDB0, 0xEB0
IMSIC_GEILEN = 7


def _eq(value: Value, constant: int, width: int = 12) -> Value:
    # Compare a signal with a fixed CSR literal. / 将信号与固定 CSR 字面量比较。
    return value == Const(constant, width)


def _part(value: Value, start: int, stop: int) -> Value:
    # Keep Amaranth slice unions behind the typed hardware boundary. / 将 Amaranth 切片联合类型收敛到硬件边界。
    return cast(Value, value[start:stop])


def _bit_select(value: Value, index: Value) -> Value:
    # Select a runtime bit with an explicit Value result. / 用显式 Value 结果选择运行期位。
    return cast(Value, value.bit_select(index, 1))


def _mode(prvm: Value, virtual: Value, code: int, want_virtual: bool = False) -> Value:
    # Decode PRVM/V exactly as PrivState's mode helpers. / 按 PrivState 模式助手解码 PRVM/V。
    return (prvm == Const(code, 2)) & (virtual if want_virtual else ~virtual)


def _any(values: list[Value]) -> Value:
    # OR-reduce a nonempty list of predicates. / 对非空谓词列表执行或归约。
    result = Const(0, 1)
    for value in values:
        result = result | value
    return result


# =============================================================================
# Implementation
# =============================================================================
class PermitModule(Elaboratable):
    """Flattened CSR permit family member. / 展平 CSR 权限 family 成员。"""

    # Build exact ports and retain the selected member name. / 构造精确端口并保留成员名。
    def __init__(self, name: str) -> None:
        if name not in _PORTS:
            raise KeyError(name)
        self.name = name
        self.specs = _PORTS[name]
        self.p: dict[str, Signal] = {port: Signal(width, name=port) for port, _direction, width in self.specs}

    # Return a port signal by locked name. / 按锁定名称返回端口信号。
    def _v(self, name: str) -> Signal:
        return self.p[name]

    # Common XRet equations from CSRPermitModule.scala. / CSRPermitModule.scala 的 XRet 方程。
    def _xret(self) -> dict[str, Value]:
        prvm, virt, debug = self._v("io_in_privState_PRVM"), self._v("io_in_privState_V"), self._v("io_in_debugMode")
        mnret, mret, sret, dret = (self._v(f"io_in_xRet_{x}") for x in ("mnret", "mret", "sret", "dret"))
        tsr, vtsr = self._v("io_in_status_tsr"), self._v("io_in_status_vtsr")
        mode_m = prvm == Const(3, 2)
        mode_hu, mode_hs, mode_vu, mode_vs = (
            _mode(prvm, virt, c, v)
            for c, v in ((0, False), (1, False), (0, True), (1, True))
        )
        mnret_illegal, mret_illegal = mnret & ~mode_m, mret & ~mode_m
        sret_ii, sret_vi = sret & (mode_hu | (mode_hs & tsr)), sret & (mode_vu | (mode_vs & vtsr))
        dret_illegal = dret & ~debug
        return {
            "Xret_EX_II": _any([mnret_illegal, mret_illegal, sret_ii, dret_illegal]),
            "Xret_EX_VI": sret_vi,
            "hasLegalMNret": mnret & ~mnret_illegal,
            "hasLegalMret": mret & ~mret_illegal,
            "hasLegalSret": sret & ~(sret_ii | sret_vi),
            "hasLegalDret": dret & ~dret_illegal,
        }

    # Privilege encoding and debug override. / 特权编码与 debug 覆盖。
    def _privilege(self) -> dict[str, Value]:
        addr, prvm, virt, debug = (self._v(x) for x in ("io_in_csrAccess_addr", "io_in_privState_PRVM", "io_in_privState_V", "io_in_debugMode"))
        level = _part(addr, 8, 10)
        regular = _any([
            _mode(prvm, virt, 0, False) & (level == Const(0, 2)),
            _mode(prvm, virt, 1, False) & (level != Const(3, 2)),
            _mode(prvm, virt, 0, True) & (level == Const(0, 2)),
            _mode(prvm, virt, 1, True) & (level < Const(2, 2)),
            _mode(prvm, virt, 3, False),
        ])
        debug_register = _part(addr, 4, 12) == Const(0x7B, 8)
        legal = Mux(debug_register, debug, regular | debug)
        csr_m = level == Const(3, 2)
        return {"privilege_EX_II": ~legal & (~virt | csr_m), "privilege_EX_VI": ~legal & virt & ~csr_m}

    # Machine-level state and read-only checks. / Machine 级状态与只读检查。
    def _mlevel(self) -> dict[str, Value]:
        p = self.p
        addr, wen, prvm, virt = p["io_in_csrAccess_addr"], p["io_in_csrAccess_wen"], p["io_in_privState_PRVM"], p["io_in_privState_V"]
        mode_m = prvm == Const(3, 2)
        mode_hs = _mode(prvm, virt, 1, False)
        non_m = ~mode_m
        csr_ro = _part(addr, 10, 12) == Const(3, 2)
        hpm = (addr >= Const(CSR_CYCLE, 12)) & (addr <= Const(CSR_HPMCOUNTER31, 12))
        fp = _any([_eq(addr, x) for x in (CSR_FFLAGS, CSR_FRM, CSR_FCSR)])
        vec = _any([_eq(addr, x) for x in (CSR_VSTART, CSR_VXSAT, CSR_VXRM, CSR_VCSR, CSR_VTYPE)])
        vec_w = _any([_eq(addr, x) for x in (CSR_VSTART, CSR_VXSAT, CSR_VXRM, CSR_VCSR)])
        fs_off = Mux(virt, p["io_in_status_mstatusFSOff"] | p["io_in_status_vsstatusFSOff"], p["io_in_status_mstatusFSOff"])
        vs_off = Mux(virt, p["io_in_status_mstatusVSOff"] | p["io_in_status_vsstatusVSOff"], p["io_in_status_mstatusVSOff"])
        mcounter_tm = _part(p["io_in_xcounteren_mcounteren"], 1, 2)
        counter_index = _part(addr, 0, 5)
        access_hpm = hpm & non_m & ~_bit_select(p["io_in_xcounteren_mcounteren"], counter_index)
        stime = _eq(addr, CSR_STIMECMP) | _eq(addr, CSR_VSTIMECMP)
        stime_illegal = non_m & stime & (~mcounter_tm | (~_part(p["io_in_xenvcfg_menvcfg"], 63, 64) & _eq(addr, CSR_STIMECMP)))
        satp_illegal = mode_hs & p["io_in_status_tvm"] & (_eq(addr, CSR_SATP) | _eq(addr, CSR_HGATP))
        stopei_illegal = mode_hs & p["io_in_aia_mvienSEIE"] & _eq(addr, CSR_STOPEI)
        stateen_bits = [
            p["io_in_xstateen_mstateen0_SE0"],
            p["io_in_xstateen_mstateen1_SE"],
            p["io_in_xstateen_mstateen2_SE"],
            p["io_in_xstateen_mstateen3_SE"],
        ]
        stateen = _any([
            (_eq(addr, CSR_HSTATEEN0 + index) | _eq(addr, CSR_SSTATEEN0 + index))
            & non_m & ~enabled
            for index, enabled in enumerate(stateen_bits)
        ])
        envcfg = (_eq(addr, CSR_HENVCFG) | _eq(addr, CSR_SENVCFG)) & non_m & ~p["io_in_xstateen_mstateen0_ENVCFG"]
        csr_indirect = (
            ((addr >= Const(CSR_SISELECT, 12)) & (addr <= Const(CSR_SIREG6, 12)) & ~_eq(addr, CSR_SIPH))
            | ((addr >= Const(CSR_VSISELECT, 12)) & (addr <= Const(CSR_VSIREG6, 12)) & ~_eq(addr, CSR_VSIPH))
        )
        indirect_illegal = csr_indirect & non_m & ~p["io_in_xstateen_mstateen0_CSRIND"]
        aia_address = _any([
            _eq(addr, value)
            for value in (CSR_HVIEN, CSR_HVICTL, CSR_HVIPRIO1, CSR_HVIPRIO2, CSR_VSTOPI, CSR_STOPI)
        ])
        aia_illegal = aia_address & non_m & ~p["io_in_xstateen_mstateen0_AIA"]
        topie_address = _eq(addr, CSR_STOPEI) | _eq(addr, CSR_VSTOPEI)
        topie_illegal = topie_address & non_m & ~p["io_in_xstateen_mstateen0_IMSIC"]
        context_address = _eq(addr, CSR_HCONTEXT) | _eq(addr, CSR_SCONTEXT)
        context_illegal = context_address & non_m & ~p["io_in_xstateen_mstateen0_CONTEXT"]
        hvs_custom = (_part(addr, 10, 12) != Const(0, 2)) & (_part(addr, 8, 10) == Const(2, 2)) & (_part(addr, 6, 8) == Const(3, 2))
        s_custom = (_part(addr, 10, 12) != Const(0, 2)) & (_part(addr, 8, 10) == Const(1, 2)) & (_part(addr, 6, 8) == Const(3, 2))
        u_custom = (_part(addr, 8, 12) == Const(8, 4)) | (_part(addr, 6, 12) == Const(0x33, 6))
        custom = hvs_custom | s_custom | u_custom
        custom_illegal = custom & non_m & ~p["io_in_xstateen_mstateen0_C"]
        illegal = _any([
            csr_ro & wen,
            fp & fs_off,
            vec & vs_off,
            stime_illegal,
            access_hpm,
            satp_illegal,
            stopei_illegal,
            stateen,
            envcfg,
            indirect_illegal,
            aia_illegal,
            topie_illegal,
            context_illegal,
            custom_illegal,
        ])
        return {"mLevelPermit_EX_II": illegal, "hasLegalWriteFcsr": wen & fp & ~fs_off, "hasLegalWriteVcsr": wen & vec_w & ~vs_off}

    # Supervisor-level counter and custom checks. / Supervisor 级计数器与 custom 检查。
    def _slevel(self) -> Value:
        p = self.p
        addr, prvm, virt = p["io_in_csrAccess_addr"], p["io_in_privState_PRVM"], p["io_in_privState_V"]
        hpm = (addr >= Const(CSR_CYCLE, 12)) & (addr <= Const(CSR_HPMCOUNTER31, 12))
        custom = (_part(addr, 8, 12) == Const(8, 4)) | (_part(addr, 6, 12) == Const(0x33, 6))
        return (hpm & _mode(prvm, virt, 0, False) & ~_bit_select(p["io_in_xcounteren_scounteren"], _part(addr, 0, 5))) | (custom & _mode(prvm, virt, 0, False) & ~p["io_in_xstateen_sstateen0_C"])

    # Virtual-level checks, including H stateen and IMSIC gates. / Virtual 级检查（含 H stateen 与 IMSIC）。
    def _vlevel(self) -> dict[str, Value]:
        p = self.p
        addr, wen, prvm, virt = p["io_in_csrAccess_addr"], p["io_in_csrAccess_wen"], p["io_in_privState_PRVM"], p["io_in_privState_V"]
        mode_vs, mode_vu = _mode(prvm, virt, 1, True), _mode(prvm, virt, 0, True)
        hpm = (addr >= Const(CSR_CYCLE, 12)) & (addr <= Const(CSR_HPMCOUNTER31, 12))
        idx = _part(addr, 0, 5)
        hpm_vi = hpm & (mode_vs & ~_bit_select(p["io_in_xcounteren_hcounteren"], idx) | mode_vu & (~_bit_select(p["io_in_xcounteren_hcounteren"], idx) | ~_bit_select(p["io_in_xcounteren_scounteren"], idx)))
        mode_m = prvm == Const(3, 2)
        mode_hs = _mode(prvm, virt, 1, False)
        satp_vi = mode_vs & p["io_in_status_vtvm"] & _eq(addr, CSR_SATP)
        invalid_vgein = (p["io_in_status_vgein"] == Const(0, 6)) | (p["io_in_status_vgein"] > Const(IMSIC_GEILEN, 6))
        vstopei_ii = (mode_m | mode_hs) & _eq(addr, CSR_VSTOPEI) & invalid_vgein
        stopei_vi = mode_vs & _eq(addr, CSR_STOPEI) & invalid_vgein
        sip_sie_vi = mode_vs & p["io_in_aia_hvictlVTI"] & (_eq(addr, CSR_SIP) | _eq(addr, CSR_SIE))
        stimecmp_vi = mode_vs & _eq(addr, CSR_STIMECMP) & (
            ~_part(p["io_in_xcounteren_hcounteren"], 1, 2)
            | ~_part(p["io_in_xenvcfg_henvcfg"], 63, 64)
            | (wen & p["io_in_aia_hvictlVTI"])
        )
        stateen_bits = [
            p["io_in_xstateen_hstateen0_SE0"],
            p["io_in_xstateen_hstateen1_SE"],
            p["io_in_xstateen_hstateen2_SE"],
            p["io_in_xstateen_hstateen3_SE"],
        ]
        stateen_vi = _any([
            _eq(addr, CSR_SSTATEEN0 + index) & virt & ~enabled
            for index, enabled in enumerate(stateen_bits)
        ])
        envcfg_vi = _eq(addr, CSR_SENVCFG) & virt & ~p["io_in_xstateen_hstateen0_ENVCFG"]
        csr_si = (addr >= Const(CSR_SISELECT, 12)) & (addr <= Const(CSR_SIREG6, 12)) & ~_eq(addr, CSR_SIPH)
        indirect_vi = csr_si & virt & ~p["io_in_xstateen_hstateen0_CSRIND"]
        aia_vi = _eq(addr, CSR_STOPI) & virt & ~p["io_in_xstateen_hstateen0_AIA"]
        topie_vi = _eq(addr, CSR_STOPEI) & virt & ~p["io_in_xstateen_hstateen0_IMSIC"]
        context_vi = _eq(addr, CSR_SCONTEXT) & virt & ~p["io_in_xstateen_hstateen0_CONTEXT"]
        s_custom = (_part(addr, 10, 12) != Const(0, 2)) & (_part(addr, 8, 10) == Const(1, 2)) & (_part(addr, 6, 8) == Const(3, 2))
        u_custom = (_part(addr, 8, 12) == Const(8, 4)) | (_part(addr, 6, 12) == Const(0x33, 6))
        custom_vi = ((s_custom | u_custom) & virt & ~p["io_in_xstateen_hstateen0_C"]) | (
            u_custom & mode_vu & p["io_in_xstateen_hstateen0_C"] & ~p["io_in_xstateen_sstateen0_C"]
        )
        ex_ii = vstopei_ii
        ex_vi = _any([
            satp_vi,
            stopei_vi,
            sip_sie_vi,
            stimecmp_vi,
            hpm_vi,
            stateen_vi,
            envcfg_vi,
            indirect_vi,
            aia_vi,
            topie_vi,
            context_vi,
            custom_vi,
        ])
        return {"virtualLevelPermit_EX_II": ex_ii, "virtualLevelPermit_EX_VI": ex_vi}

    # Indirect AIA register window checks. / 间接 AIA 寄存器窗口检查。
    def _indirect(self) -> dict[str, Value]:
        p = self.p
        addr, prvm, virt = p["io_in_csrAccess_addr"], p["io_in_privState_PRVM"], p["io_in_privState_V"]
        msel, ssel, vssel = p["io_in_aia_miselect"], p["io_in_aia_siselect"], p["io_in_aia_vsiselect"]
        mode_m = prvm == Const(3, 2)
        mode_hs = _mode(prvm, virt, 1, False)

        def in_aia(value: Value) -> Value:
            return (value >= Const(0x30, 64)) & (value <= Const(0x3F, 64))

        def in_imsic(value: Value) -> Value:
            return (value >= Const(0x70, 64)) & (value <= Const(0xFF, 64))

        def in_others(value: Value) -> Value:
            return ~(in_aia(value) | in_imsic(value))

        mireg2_6 = (addr >= Const(CSR_MIREG + 1, 12)) & (addr <= Const(CSR_MIREG6, 12)) & ~_eq(addr, CSR_MIPH)
        sireg2_6 = (addr >= Const(CSR_SIREG + 1, 12)) & (addr <= Const(CSR_SIREG6, 12)) & ~_eq(addr, CSR_SIPH)
        vsireg2_6 = (addr >= Const(CSR_VSIREG + 1, 12)) & (addr <= Const(CSR_VSIREG6, 12)) & ~_eq(addr, CSR_VSIPH)
        rw_mireg_ii = ((in_aia(msel) & _part(msel, 0, 1)) | in_others(msel)) & _eq(addr, CSR_MIREG)
        rw_sireg_ii = (
            (~virt & ((in_aia(ssel) & _part(ssel, 0, 1)) | in_others(ssel)))
            | (mode_hs & (
                (p["io_in_aia_mvienSEIE"] & in_imsic(ssel))
                | (~p["io_in_xstateen_mstateen0_AIA"] & in_aia(ssel))
                | (~p["io_in_xstateen_mstateen0_IMSIC"] & in_imsic(ssel))
            ))
            | (virt & (
                in_others(vssel)
                | (~p["io_in_xstateen_mstateen0_IMSIC"] & in_imsic(vssel))
            ))
        ) & _eq(addr, CSR_SIREG)
        rw_sireg_vi = virt & (
            in_aia(vssel)
            | (in_imsic(vssel) & ~p["io_in_xstateen_hstateen0_IMSIC"])
        ) & _eq(addr, CSR_SIREG)
        rw_sireg2_6_vi = virt & (in_aia(vssel) | in_imsic(vssel)) & sireg2_6
        rw_sireg2_6_ii = sireg2_6 & ~rw_sireg2_6_vi
        rw_vsireg_ii = (
            ~in_imsic(vssel)
            | (~mode_m & ~p["io_in_xstateen_mstateen0_IMSIC"])
        ) & _eq(addr, CSR_VSIREG)
        illegal = _any([
            rw_mireg_ii,
            mireg2_6,
            rw_sireg_ii,
            rw_sireg2_6_ii,
            rw_vsireg_ii,
            vsireg2_6,
        ])
        virtual_illegal = rw_sireg_vi | rw_sireg2_6_vi
        return {"indirectCSR_EX_II": illegal, "indirectCSR_EX_VI": virtual_illegal}

    # Elaborate one selected member with exact output equations. / 使用精确输出方程展开选定成员。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        outputs = {name for name, direction, _width in self.specs if direction == "output"}
        for name in outputs:
            m.d.comb += self.p[name].eq(Const(0, len(self.p[name])))
        if self.name == "XRetPermitModule":
            for suffix, value in self._xret().items():
                m.d.comb += self._v(f"io_out_{suffix}").eq(value)
        elif self.name == "PrivilegePermitModule":
            for suffix, value in self._privilege().items():
                m.d.comb += self._v(f"io_out_{suffix}").eq(value)
        elif self.name == "MLevelPermitModule":
            for suffix, value in self._mlevel().items():
                m.d.comb += self._v(f"io_out_{suffix}").eq(value)
        elif self.name == "SLevelPermitModule":
            m.d.comb += self._v("io_out_sLevelPermit_EX_II").eq(self._slevel())
        elif self.name == "VirtualLevelPermitModule":
            for suffix, value in self._vlevel().items():
                m.d.comb += self._v(f"io_out_{suffix}").eq(value)
        elif self.name == "IndirectCSRPermitModule":
            for suffix, value in self._indirect().items():
                m.d.comb += self._v(f"io_out_{suffix}").eq(value)
        else:
            xret, mlevel, slevel, privilege, virtual, indirect = self._xret(), self._mlevel(), self._slevel(), self._privilege(), self._vlevel(), self._indirect()
            direct_ii = mlevel["mLevelPermit_EX_II"] | slevel | privilege["privilege_EX_II"] | privilege["privilege_EX_VI"] | virtual["virtualLevelPermit_EX_II"] | virtual["virtualLevelPermit_EX_VI"]
            access = self._v("io_in_csrAccess_ren") | self._v("io_in_csrAccess_wen")
            ex_ii = access & ((mlevel["mLevelPermit_EX_II"] | slevel | privilege["privilege_EX_II"] | virtual["virtualLevelPermit_EX_II"]) | (~direct_ii & indirect["indirectCSR_EX_II"]))
            ex_vi = ~ex_ii & access & (privilege["privilege_EX_VI"] | virtual["virtualLevelPermit_EX_VI"] | (~direct_ii & indirect["indirectCSR_EX_VI"]))
            final_ii = ex_ii | xret["Xret_EX_II"]
            final_vi = ~final_ii & (ex_vi | xret["Xret_EX_VI"])
            equations = {"hasLegalWen": self._v("io_in_csrAccess_wen") & ~final_ii & ~final_vi, "hasLegalMNret": xret["hasLegalMNret"], "hasLegalMret": xret["hasLegalMret"], "hasLegalSret": xret["hasLegalSret"], "hasLegalDret": xret["hasLegalDret"], "hasLegalWriteFcsr": mlevel["hasLegalWriteFcsr"], "hasLegalWriteVcsr": mlevel["hasLegalWriteVcsr"], "EX_II": final_ii, "EX_VI": final_vi}
            for suffix, value in equations.items():
                m.d.comb += self._v(f"io_out_{suffix}").eq(value)
        return m


# =============================================================================
# Public Adapter
# =============================================================================
# Deterministic same-name Verilog export. / 确定性的同名 Verilog 导出。
def build_verilog(configuration, injected_dependencies):
    del injected_dependencies
    config: dict[str, Any] = configuration if isinstance(configuration, dict) else {}
    name = str(config.get("module") or "CSRPermitModule")
    top = PermitModule(name)
    return verilog.convert(top, name=name, ports=[top.p[n] for n, _d, _w in _PORTS[name]])


# =============================================================================
# Direct Entry
# =============================================================================
# Print the default top member. / 打印默认顶层成员。
def main() -> None:
    print(build_verilog(None, None))


if __name__ == "__main__":
    main()
