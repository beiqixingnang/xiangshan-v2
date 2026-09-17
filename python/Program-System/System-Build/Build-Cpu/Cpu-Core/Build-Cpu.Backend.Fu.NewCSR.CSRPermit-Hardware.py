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
CSR_VSTART, CSR_VXSAT, CSR_VXRM, CSR_VCSR, CSR_VTYPE = 0x008, 0x009, 0x00A, 0x00F, 0x00B
CSR_SATP, CSR_HGATP = 0x180, 0x680
CSR_STIMECMP, CSR_VSTIMECMP = 0x14D, 0x24D
CSR_STOPI, CSR_VSTOPI = 0xDB0, 0x2DB0
CSR_MIREG, CSR_MIREG2, CSR_SIREG, CSR_SIREG2, CSR_VSIREG, CSR_VSIREG2 = 0x350, 0x351, 0x150, 0x151, 0x250, 0x251


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
        mode_m, mode_hu, mode_hs, mode_vu, mode_vs = (_mode(prvm, virt, c, v) for c, v in ((3, False), (0, False), (1, False), (0, True), (1, True)))
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
            _mode(prvm, virt, 1, True) & (level == Const(0, 2)),
            _mode(prvm, virt, 3, False),
        ])
        legal = regular | debug
        csr_m = level == Const(3, 2)
        return {"privilege_EX_II": ~legal & (~virt | csr_m), "privilege_EX_VI": ~legal & virt & ~csr_m}

    # Machine-level state and read-only checks. / Machine 级状态与只读检查。
    def _mlevel(self) -> dict[str, Value]:
        p = self.p
        addr, wen, prvm, virt = p["io_in_csrAccess_addr"], p["io_in_csrAccess_wen"], p["io_in_privState_PRVM"], p["io_in_privState_V"]
        non_m = ~_mode(prvm, virt, 3, False)
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
        satp_illegal = _mode(prvm, virt, 1, False) & p["io_in_status_tvm"] & (_eq(addr, CSR_SATP) | _eq(addr, CSR_HGATP))
        stateen = _any([_eq(addr, 0x120 + i) | _eq(addr, 0x100 + i) for i in range(4)]) & ~p["io_in_xstateen_mstateen0_SE0"] & non_m
        envcfg = (_eq(addr, 0x10A) | _eq(addr, 0x1A0)) & non_m & ~p["io_in_xstateen_mstateen0_ENVCFG"]
        custom = ((_part(addr, 8, 11) != Const(0, 3)) & (_part(addr, 6, 8) == Const(3, 2))) | (_part(addr, 8, 12) == Const(8, 4)) | (_part(addr, 6, 12) == Const(0x33, 6))
        custom_illegal = custom & non_m & ~p["io_in_xstateen_mstateen0_C"]
        illegal = (csr_ro & wen) | (fp & fs_off) | (vec & vs_off) | stime_illegal | access_hpm | satp_illegal | stateen | envcfg | custom_illegal
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
        satp_vi = mode_vs & p["io_in_status_vtvm"] & _eq(addr, CSR_SATP)
        stopei = (_eq(addr, CSR_STOPI) | _eq(addr, CSR_VSTOPI)) & (p["io_in_status_vgein"] == Const(0, 6))
        custom = ((_part(addr, 8, 11) != Const(0, 3)) & (_part(addr, 6, 8) == Const(3, 2))) | (_part(addr, 8, 12) == Const(8, 4)) | (_part(addr, 6, 12) == Const(0x33, 6))
        stateen = _any([_eq(addr, 0x100 + i) for i in range(4)]) & ~p["io_in_xstateen_hstateen0_SE0"]
        custom_vi = custom & (~p["io_in_xstateen_hstateen0_C"] | (mode_vu & p["io_in_xstateen_hstateen0_C"] & ~p["io_in_xstateen_sstateen0_C"]))
        ex_ii = ((_eq(addr, CSR_VSTOPI) & ~stopei) & (~mode_vs | ~virt))
        ex_vi = satp_vi | stopei | hpm_vi | stateen | custom_vi
        return {"virtualLevelPermit_EX_II": ex_ii, "virtualLevelPermit_EX_VI": ex_vi}

    # Indirect AIA register window checks. / 间接 AIA 寄存器窗口检查。
    def _indirect(self) -> dict[str, Value]:
        p = self.p
        addr, virt = p["io_in_csrAccess_addr"], p["io_in_privState_V"]
        msel, ssel, vssel = p["io_in_aia_miselect"], p["io_in_aia_siselect"], p["io_in_aia_vsiselect"]
        mireg = _eq(addr, CSR_MIREG) | ((addr >= Const(0x351, 12)) & (addr <= Const(0x356, 12)))
        sireg = _eq(addr, CSR_SIREG) | ((addr >= Const(0x151, 12)) & (addr <= Const(0x156, 12)))
        vsireg = _eq(addr, CSR_VSIREG) | ((addr >= Const(0x251, 12)) & (addr <= Const(0x256, 12)))
        m_aia = _any([_part(msel, 0, 1), _part(msel, 1, 2), _part(msel, 2, 3)]) & ~p["io_in_xstateen_mstateen0_AIA"]
        s_aia = _any([_part(ssel, 0, 1), _part(ssel, 1, 2), _part(ssel, 2, 3)]) & ~p["io_in_xstateen_mstateen0_AIA"]
        v_aia = _any([_part(vssel, 0, 1), _part(vssel, 1, 2), _part(vssel, 2, 3)]) & ~p["io_in_xstateen_hstateen0_IMSIC"]
        return {"indirectCSR_EX_II": mireg & m_aia | sireg & (~virt | s_aia) | vsireg & (~virt | ~p["io_in_xstateen_mstateen0_AIA"]), "indirectCSR_EX_VI": virt & (sireg | vsireg) & v_aia}

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
            equations = {"hasLegalWen": self._v("io_in_csrAccess_wen") & ~ex_ii & ~ex_vi, "hasLegalMNret": xret["hasLegalMNret"], "hasLegalMret": xret["hasLegalMret"], "hasLegalSret": xret["hasLegalSret"], "hasLegalDret": xret["hasLegalDret"], "hasLegalWriteFcsr": mlevel["hasLegalWriteFcsr"], "hasLegalWriteVcsr": mlevel["hasLegalWriteVcsr"], "EX_II": ex_ii | xret["Xret_EX_II"], "EX_VI": ~ (ex_ii | xret["Xret_EX_II"]) & (ex_vi | xret["Xret_EX_VI"])}
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
