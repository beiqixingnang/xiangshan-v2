"""Direct bounded tests for the NewCSR control/trap family.

直接有界测试 NewCSR 控制/陷阱 family 的同名导出与端口覆盖。
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Fu.NewCSR.ControlFamily-Hardware.py"


def load_subject() -> Any:
    """Load the exact Build path. / 加载精确 Build 路径。"""

    spec = importlib.util.spec_from_file_location("testing_newcsr_control_family", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class NewCSRControlFamilyTest(unittest.TestCase):
    """Check all nine locked family members export by their own name."""

    def test_all_members_export(self) -> None:
        module = load_subject()
        for member in module.COVERED_MODULES:
            rtl = module.build_verilog({"module": member}, {})
            self.assertIn(f"module {member}", rtl)

    def test_deterministic_exports(self) -> None:
        module = load_subject()
        for member in module.COVERED_MODULES:
            self.assertEqual(module.build_verilog({"module": member}, {}),
                             module.build_verilog({"module": member}, {}))


if __name__ == "__main__":
    unittest.main()
