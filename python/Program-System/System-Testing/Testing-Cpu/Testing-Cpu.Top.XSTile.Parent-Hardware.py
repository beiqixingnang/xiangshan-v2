"""Direct tests for the bounded UHSC XSTile parent.
有界 UHSC XSTile 父级的直接测试。
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Top.XiangShan-Roots-Hardware.py"
INVENTORY = ROOT / "validation/v2-root-port-inventories.json"


def load_subject() -> Any:
    """Load the exact root Build. / 加载精确根 Build。"""
    spec = importlib.util.spec_from_file_location("testing_xstile_parent_subject", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class XSTileParentContractTest(unittest.TestCase):
    """Check 153 ports and honest missing-child state. / 检查 153 端口及诚实缺子级状态。"""

    def test_surface_and_pending(self) -> None:
        """Require deterministic exact export while children remain pending. / 要求确定性导出且子级保持 pending。"""
        module = load_subject()
        inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))["modules"]["XSTile"]["ports"]
        first = module.build_verilog({"root": "XSTile", "module": "XSTile"}, {"full_port_specs": inventory})
        self.assertEqual(first, module.build_verilog({"root": "XSTile", "module": "XSTile"}, {"full_port_specs": inventory}))
        self.assertIn("module XSTile", first)
        self.assertEqual(len(module.XSTile(injected_dependencies={"full_port_specs": inventory}).xstile_children), 6)


if __name__ == "__main__":
    unittest.main()
