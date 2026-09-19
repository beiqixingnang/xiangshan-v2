#!/usr/bin/env python3
# Module Contract
"""Reusable direct tests for the Kunminghu V2 CSR-permit family.

Each test drives one aggregate member through its public ANSI ports.  The
checks are deliberately bounded and independent of ``validation/``; complete
locked-reference and parent-closure evidence remains outside this test suite.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from typing import Any

from amaranth.sim import Settle, Simulator


# Fixtures And Support
ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Fu.NewCSR.CSRPermit-Hardware.py"


# Load the exact Build file without package discovery. / 按精确路径加载 Build 文件，不依赖包发现。
def load_subject() -> Any:
    """Load the CSR permit Build module. / 加载 CSR 权限 Build 模块。"""

    spec = importlib.util.spec_from_file_location("testing_v2_csrpermit_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {TARGET}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def observe(module: Any, member: str, values: dict[str, int]) -> dict[str, int]:
    """Evaluate one member with deterministic zero defaults. / 用确定性的零默认值评估一个成员。"""

    dut = module.PermitModule(member)
    outputs: dict[str, int] = {}

    def process():
        for name, signal in dut.p.items():
            if name.startswith("io_in_"):
                yield signal.eq(0)
        for name, value in values.items():
            yield dut.p[name].eq(value)
        yield Settle()
        for name, direction, _width in dut.specs:
            if direction == "output":
                outputs[name] = int((yield dut.p[name]))

    sim = Simulator(dut)
    sim.add_process(process)
    sim.run()
    return outputs


# Subject Contract
class CSRPermitContractTest(unittest.TestCase):
    """Check member coverage and deterministic same-name exports. / 检查成员覆盖与确定性同名导出。"""

    def test_all_locked_members_export(self) -> None:
        module = load_subject()
        expected = {
            "CSRPermitModule", "IndirectCSRPermitModule", "MLevelPermitModule",
            "PrivilegePermitModule", "SLevelPermitModule", "VirtualLevelPermitModule",
            "XRetPermitModule",
        }
        self.assertEqual(expected, set(module.COVERED_MODULES))
        for member in sorted(expected):
            rtl = module.build_verilog({"module": member}, {})
            self.assertIn(f"module {member}", rtl)


# Behavior Tests
class CSRPermitBehaviorTest(unittest.TestCase):
    """Exercise stable privilege, return, and state-enable equations. / 检查稳定的特权、返回与状态使能方程。"""

    def test_xret_modes_and_debug_gate(self) -> None:
        module = load_subject()
        legal_mret = observe(module, "XRetPermitModule", {
            "io_in_privState_PRVM": 3, "io_in_xRet_mret": 1,
        })
        self.assertEqual(0, legal_mret["io_out_Xret_EX_II"])
        self.assertEqual(1, legal_mret["io_out_hasLegalMret"])

        trapped_sret = observe(module, "XRetPermitModule", {
            "io_in_privState_PRVM": 1, "io_in_xRet_sret": 1,
            "io_in_status_tsr": 1,
        })
        self.assertEqual(1, trapped_sret["io_out_Xret_EX_II"])
        self.assertEqual(0, trapped_sret["io_out_hasLegalSret"])

        virtual_sret = observe(module, "XRetPermitModule", {
            "io_in_privState_PRVM": 1, "io_in_privState_V": 1,
            "io_in_xRet_sret": 1, "io_in_status_vtsr": 1,
        })
        self.assertEqual(1, virtual_sret["io_out_Xret_EX_VI"])
        self.assertEqual(0, virtual_sret["io_out_hasLegalSret"])

        debug_dret = observe(module, "XRetPermitModule", {
            "io_in_debugMode": 1, "io_in_xRet_dret": 1,
        })
        self.assertEqual(1, debug_dret["io_out_hasLegalDret"])

    def test_privilege_and_slevel_boundaries(self) -> None:
        module = load_subject()
        user_access = observe(module, "PrivilegePermitModule", {
            "io_in_privState_PRVM": 0, "io_in_csrAccess_addr": 0x000,
        })
        self.assertEqual((0, 0), (user_access["io_out_privilege_EX_II"], user_access["io_out_privilege_EX_VI"]))
        denied_supervisor = observe(module, "PrivilegePermitModule", {
            "io_in_privState_PRVM": 0, "io_in_csrAccess_addr": 0x100,
        })
        self.assertEqual((1, 0), (denied_supervisor["io_out_privilege_EX_II"], denied_supervisor["io_out_privilege_EX_VI"]))

        slevel = observe(module, "SLevelPermitModule", {
            "io_in_privState_PRVM": 0, "io_in_csrAccess_addr": 0xC00,
        })
        self.assertEqual(1, slevel["io_out_sLevelPermit_EX_II"])
        enabled = observe(module, "SLevelPermitModule", {
            "io_in_privState_PRVM": 0, "io_in_csrAccess_addr": 0xC00,
            "io_in_xcounteren_scounteren": 1,
        })
        self.assertEqual(0, enabled["io_out_sLevelPermit_EX_II"])

    def test_mlevel_read_only_and_fcsr_checks(self) -> None:
        module = load_subject()
        read_only_write = observe(module, "MLevelPermitModule", {
            "io_in_privState_PRVM": 3, "io_in_csrAccess_addr": 0xC00,
            "io_in_csrAccess_wen": 1,
        })
        self.assertEqual(1, read_only_write["io_out_mLevelPermit_EX_II"])
        fcsr_off = observe(module, "MLevelPermitModule", {
            "io_in_privState_PRVM": 1, "io_in_csrAccess_addr": 0x003,
            "io_in_csrAccess_wen": 1, "io_in_status_mstatusFSOff": 1,
        })
        self.assertEqual(1, fcsr_off["io_out_mLevelPermit_EX_II"])
        self.assertEqual(0, fcsr_off["io_out_hasLegalWriteFcsr"])

    def test_virtual_satp_and_indirect_window(self) -> None:
        module = load_subject()
        satp = observe(module, "VirtualLevelPermitModule", {
            "io_in_privState_PRVM": 1, "io_in_privState_V": 1,
            "io_in_csrAccess_addr": 0x180, "io_in_status_vtvm": 1,
        })
        self.assertEqual(1, satp["io_out_virtualLevelPermit_EX_VI"])
        indirect = observe(module, "IndirectCSRPermitModule", {
            "io_in_csrAccess_addr": 0x251,
        })
        self.assertEqual(1, indirect["io_out_indirectCSR_EX_II"])

    def test_aggregate_legal_write_and_return(self) -> None:
        module = load_subject()
        result = observe(module, "CSRPermitModule", {
            "io_in_csrAccess_wen": 1, "io_in_csrAccess_addr": 0x003,
            "io_in_privState_PRVM": 3, "io_in_xRet_mret": 1,
        })
        self.assertEqual(1, result["io_out_hasLegalWen"])
        self.assertEqual(1, result["io_out_hasLegalMret"])
        self.assertEqual(0, result["io_out_EX_II"])


if __name__ == "__main__":
    unittest.main()
