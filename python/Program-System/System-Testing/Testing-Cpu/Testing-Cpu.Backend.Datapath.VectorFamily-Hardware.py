"""Bounded direct tests for the UHSC V2 vector datapath family.

本测试只验证锁定端口目录、输出 oracle 与三种同名 Verilog 导出；
完整 V2 行为差分由父级闭包另行承担。
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
TARGET = (
    ROOT
    / "python/Program-System/System-Build/Build-Cpu/Cpu-Core"
    / "Build-Cpu.Backend.Datapath.VectorFamily-Hardware.py"
)
MEMBERS = (
    "Og2ForVector",
    "VTypeBuffer",
    "VecExcpDataMergeModule",
    "VIAluSrcTypeModule",
    "VIMacSrcTypeModule",
    "VPermSrcTypeModule",
)


def load_subject() -> Any:
    """Load the exact owned Build. / 加载本批精确 Build。"""

    spec = importlib.util.spec_from_file_location("testing_vector_datapath_family", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class VectorDatapathFamilyTest(unittest.TestCase):
    """Port and deterministic-export tests. / 端口与确定性导出测试。"""

    def test_members_and_output_oracles(self) -> None:
        module = load_subject()
        self.assertEqual(tuple(module.COVERED_MODULES), MEMBERS)
        for member in MEMBERS:
            outputs = module.vector_datapath_model(member)
            expected = {
                name
                for name, direction, _width in module.PORT_SPECS[member]
                if direction == "output"
            }
            self.assertEqual(set(outputs), expected)
            self.assertTrue(all(value == 0 for value in outputs.values()))

    def test_same_name_exports(self) -> None:
        module = load_subject()
        for member in MEMBERS:
            rtl = module.build_verilog({"module": member}, {})
            self.assertIn(f"module {member}", rtl)
            self.assertEqual(rtl, module.build_verilog({"module": member}, {}))


if __name__ == "__main__":
    unittest.main()
