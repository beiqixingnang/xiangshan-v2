#!/usr/bin/env python3
"""Bounded System-Testing contract for TOP-XSCORE-CHILD-002.

The test locks the 308-port XSCore parent surface and verifies that the
Frontend/Backend/MemBlock bridge reports missing child closures honestly.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
import unittest
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, Final

from amaranth import Elaboratable, Module
from amaranth.sim import Settle, Simulator

ROOT: Final = Path(__file__).resolve().parents[4]
TARGET: Final = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Cpu-Core-Top.UHSCore.Parent-Hardware.py"


if TYPE_CHECKING:
    def test_load_subject_module(subject_type: str, subject_id: str) -> ModuleType: ...


def load_standalone_subject() -> ModuleType:
    """Load the exact Build path for standalone direct invocation. / 独立调用时按精确路径加载 Build。"""

    spec = importlib.util.spec_from_file_location("testing_uhscore_parent_subject", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# =============================================================================
# Module Contract
# =============================================================================
TEST_ID: Final = "Cpu.Top.UHSCore.Parent"
SUBJECT_TYPE: Final = "build"
SUBJECT_ID: Final = "Cpu.Top.UHSCore.Parent"
PORT_COUNT: Final = 308
PARENT_CLOSURE: Final = "PENDING_CHILD_MISSING"


# =============================================================================
# Behavior Tests
# =============================================================================
class UHSCoreSubjectContractTest(unittest.TestCase):
    """Check the subject identity. / 检查测试主题身份。"""

    def test_subject_contract(self) -> None:
        """Keep the test subject stable. / 保持测试主题稳定。"""

        self.assertEqual(TEST_ID, SUBJECT_ID)


class UHSCoreParentContractTest(unittest.TestCase):
    """Exercise the bounded parent contract. / 测试有界父级契约。"""

    def setUp(self) -> None:
        """Load the exact Build target. / 加载精确 Build 目标。"""

        self.module = test_load_subject_module(SUBJECT_TYPE, SUBJECT_ID)

    def test_locked_port_inventory(self) -> None:
        """Require 308 unique source names and directions. / 要求 308 个唯一源端口名及方向。"""

        specs = tuple(self.module.uhs_core_port_specs())
        self.assertEqual(PORT_COUNT, len(specs))
        self.assertEqual(PORT_COUNT, len({row[0] for row in specs}))
        self.assertEqual({"input", "output"}, {row[1] for row in specs})
        self.assertTrue(all(int(row[2]) >= 1 for row in specs))

    def test_deterministic_exact_export(self) -> None:
        """Export the exact envelope twice. / 两次导出精确包络并比较确定性。"""

        first = self.module.build_verilog({"module": "UHSCoreParent"}, {})
        second = self.module.build_verilog({"module": "UHSCoreParent"}, {})
        self.assertEqual(first, second)
        self.assertRegex(first, r"module UHSCoreParent")
        self.assertEqual(len(re.findall(r"^\s*(?:input|output|inout)", first, re.MULTILINE)), PORT_COUNT)
        self.assertNotEqual(hashlib.sha256(first.encode()).hexdigest(), "0" * 64)

    def test_missing_children_are_not_promoted(self) -> None:
        """Require the real bounded child-missing mask. / 要求真实有界缺子级掩码。"""

        dut = self.module.UHSCoreParent()
        observed: dict[str, int] = {}

        def process():
            yield dut.reset.eq(1)
            yield Settle()
            observed.update({
                "mask": (yield dut.child_missing),
                "count": (yield dut.child_missing_count),
                "missing": (yield dut.closure_missing),
                "complete": (yield dut.closure_complete),
            })

        simulator = Simulator(dut)
        simulator.add_process(process)
        simulator.run()
        self.assertEqual({"mask": 7, "count": 3, "missing": 1, "complete": 0}, observed)
        self.assertEqual(PARENT_CLOSURE, "PENDING_CHILD_MISSING")

    def test_source_equation_observation(self) -> None:
        """Check Frontend/Backend and MemBlock fire equations. / 检查三父级握手方程。"""

        result = self.module.uhs_core_parent_observation(
            frontend_valid=True, backend_can_accept=True,
            mem_a_valid=True, mem_a_ready=True,
            mem_d_valid=True, mem_d_ready=True,
            child_missing=3,
        )
        self.assertEqual(1, result["frontend_backend_fire"])
        self.assertEqual(1, result["mem_a_fire"])
        self.assertEqual(1, result["mem_d_fire"])
        self.assertEqual(0, result["closure_complete"])

    def test_complete_children_do_not_hide_rejected_pin_edges(self) -> None:
        """A missing exact endpoint keeps closure pending after child status passes. / 子级状态通过仍不能掩盖缺失 pin。"""

        class EmptyChild(Elaboratable):
            def elaborate(self, platform):
                del platform
                return Module()

        dut = self.module.UHSCoreParent(injected_dependencies={
            "frontend": EmptyChild(), "backend": EmptyChild(), "mem_block": EmptyChild(),
            "child_status": {"frontend": "PASS_COMPLETE", "backend": "PASS_COMPLETE",
                             "mem_block": "PASS_COMPLETE"},
            "verified_pin_audit": {"pin_table_complete": True, "unsupported_pin_count": 0},
            "verified_pin_edges": [{
                "source": {"kind": "child", "child": "frontend", "port": "missing_pin"},
                "destinations": [{"kind": "parent", "port": "io_msiAck"}],
                "width": 1,
            }],
        })
        observed: dict[str, int] = {}

        def process():
            yield Settle()
            observed.update({
                "child_missing_count": (yield dut.child_missing_count),
                "edge_missing_count": (yield dut.verified_edge_missing_count),
                "closure_missing": (yield dut.closure_missing),
                "closure_complete": (yield dut.closure_complete),
            })

        simulator = Simulator(dut)
        simulator.add_process(process)
        simulator.run()
        self.assertEqual({"child_missing_count": 0, "edge_missing_count": 1,
                          "closure_missing": 1, "closure_complete": 0}, observed)


if __name__ == "__main__":
    def test_load_subject_module(subject_type: str, subject_id: str) -> ModuleType:
        if subject_type != SUBJECT_TYPE or subject_id != SUBJECT_ID:
            raise ValueError(f"unexpected subject request: {subject_type} {subject_id}")
        return load_standalone_subject()

    unittest.main()
