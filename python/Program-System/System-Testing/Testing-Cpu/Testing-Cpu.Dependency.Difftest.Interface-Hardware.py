#!/usr/bin/env python3
# Module Contract
"""Reusable direct tests for the Kunminghu V2 Difftest interface.

The tests exercise the independent trace-queue and AXI-Lite reference models
exposed by the Build.  They are intentionally bounded and are not a substitute
for the locked XSTop differential closure kept in ``validation/``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest
from typing import Any


# Fixtures And Support
ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Dependency.Difftest.Interface-Hardware.py"


# Load the exact Build file without package installation. / 按精确路径加载 Build 文件，不依赖包安装。
def load_subject() -> Any:
    """Load the Difftest Build module. / 加载 Difftest Build 模块。"""

    spec = importlib.util.spec_from_file_location("testing_v2_difftest_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Subject Contract
class DifftestInterfaceContractTest(unittest.TestCase):
    """Check the bounded public reference contracts. / 检查有界公共参考契约。"""

    def test_trace_queue_reference_handles_push_pop_and_overflow(self) -> None:
        module = load_subject()
        first = {"pc": 0x1000, "inst": 0x13}
        second = {"pc": 0x1004, "inst": 0x93}
        queue, head, ready, overflow = module.difftest_trace_step([], first, False, 2)
        self.assertEqual((queue, head, ready, overflow), ([first], first, True, False))
        queue, head, ready, overflow = module.difftest_trace_step(queue, second, False, 1)
        self.assertEqual(([first], first, False, True), (queue, head, ready, overflow))
        queue, head, ready, overflow = module.difftest_trace_step(queue, second, True, 1)
        self.assertEqual(([second], second, True, False), (queue, head, ready, overflow))

    def test_axi_lite_reference_accepts_channels_in_either_order(self) -> None:
        module = load_subject()
        state: dict[str, int] = {}
        state = module.axi_lite_reference_step(state, False, 0, True, 1, False, False, 0, False, 0)
        self.assertEqual(1, state["w_hold"])
        state = module.axi_lite_reference_step(state, True, 4, False, 0, False, False, 0, False, 0)
        self.assertEqual(1, state["b_valid"])
        self.assertEqual(1, state["halted"])
        state = module.axi_lite_reference_step(state, False, 0, False, 0, True, True, 4, False, 0)
        self.assertEqual(0, state["b_valid"])
        self.assertEqual(1, state["r_valid"])
        self.assertEqual(1, state["r_data"])

    def test_export_has_stable_module_name(self) -> None:
        module = load_subject()
        rtl = module.build_verilog({"module": "UHSCDifftestInterface", "trace_depth": 2}, {})
        self.assertIn("module UHSCDifftestInterface", rtl)
        self.assertIn("io_trace_valid", rtl)


if __name__ == "__main__":
    unittest.main()
