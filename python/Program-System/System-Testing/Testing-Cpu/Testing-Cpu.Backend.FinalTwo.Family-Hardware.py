"""Direct tests for the V2 final-two behavior family."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.FinalTwo.Family-Hardware.py"


def load_subject() -> Any:
    """Load the exact matching Build file. / 加载精确匹配的 Build 文件。"""

    spec = importlib.util.spec_from_file_location("testing_final_two", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FinalTwoFamilyTest(unittest.TestCase):
    """Check deterministic exports and the PLRU oracle. / 检查确定性导出及 PLRU oracle。"""

    def test_all_members_export_deterministically(self) -> None:
        """Require exact module names and stable output. / 要求精确模块名和稳定输出。"""

        module = load_subject()
        for name in module.COVERED_MODULES:
            first = module.build_verilog({"module": name}, {})
            self.assertEqual(first, module.build_verilog({"module": name}, {}))
            self.assertIn(f"module {name}", first)

    def test_plru_touch_moves_replacement(self) -> None:
        """Exercise all 16 touches through the pure model. / 通过纯模型覆盖全部 16 路访问。"""

        module = load_subject()
        state = 0
        observed = []
        for way in range(16):
            observed.append(module.plru_replace_int(state))
            state = module.plru_next_int(state, way)
        self.assertTrue(all(0 <= way < 16 for way in observed))
        self.assertGreater(len(set(observed)), 1)


if __name__ == "__main__":
    unittest.main()
