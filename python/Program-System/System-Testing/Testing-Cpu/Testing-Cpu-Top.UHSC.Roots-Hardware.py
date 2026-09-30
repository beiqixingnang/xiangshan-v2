"""Direct tests for the bounded UHSTile parent.
有界 UHSTile 父级的直接测试。
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Cpu-Core-Top.UHSC.Roots-Hardware.py"
INVENTORY = ROOT / "validation/v2-root-port-inventories.json"


def load_subject() -> Any:
    """Load the exact root Build. / 加载精确根 Build。"""
    spec = importlib.util.spec_from_file_location("testing_uhstile_parent_subject", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class UHSTileParentContractTest(unittest.TestCase):
    """Check 153 ports and honest missing-child state. / 检查 153 端口及诚实缺子级状态。"""

    def test_surface_and_pending(self) -> None:
        """Require deterministic exact export while children remain pending. / 要求确定性导出且子级保持 pending。"""
        module = load_subject()
        source_root = "XSTile"
        product_root = {"XSCore": "UHSCore", "XSTile": "UHSTile", "XSTop": "UHSCTop"}[source_root]
        inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))["modules"][source_root]["ports"]
        configuration = {"root": product_root, "module": product_root}
        first = module.build_verilog(configuration, {"full_port_specs": inventory})
        self.assertEqual(first, module.build_verilog(configuration, {"full_port_specs": inventory}))
        self.assertIn("module UHSTile", first)
        tile = module.UHSTile(injected_dependencies={"full_port_specs": inventory})
        self.assertEqual(len(tile.uhstile_children), 6)
        self.assertIsNone(tile.uhstile_children["uhs_core"])


if __name__ == "__main__":
    unittest.main()
