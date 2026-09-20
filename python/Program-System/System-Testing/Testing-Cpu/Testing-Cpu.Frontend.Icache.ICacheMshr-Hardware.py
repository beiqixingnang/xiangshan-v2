"""Direct tests for the locked V2 ICache MSHR specializations."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Frontend.Icache.ICacheMshr-Hardware.py"


def load_subject() -> Any:
    """Load the exact matching Build path. / 加载精确匹配的 Build 路径。"""

    spec = importlib.util.spec_from_file_location("testing_icache_mshr", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ICacheMshrTest(unittest.TestCase):
    """Check the two exact locked exports and fire oracle. / 检查两个精确锁定导出与 fire oracle。"""

    def test_locked_variants_export_deterministically(self) -> None:
        """Require exact names and specialization-only flush. / 要求精确名称及特化 flush 端口。"""

        module = load_subject()
        fetch = module.build_verilog({"module": "ICacheMSHR"}, {})
        prefetch = module.build_verilog({"module": "ICacheMSHR_4"}, {})
        self.assertEqual(fetch, module.build_verilog({"module": "ICacheMSHR"}, {}))
        self.assertEqual(prefetch, module.build_verilog({"module": "ICacheMSHR_4"}, {}))
        self.assertIn("module ICacheMSHR(", fetch)
        self.assertIn("module ICacheMSHR_4(", prefetch)
        self.assertNotIn("io_flush", fetch.split(");", 1)[0])
        self.assertIn("io_flush", prefetch.split(");", 1)[0])
        fetch_header = fetch.split(");", 1)[0]
        self.assertNotIn("io_acquire_fire", fetch_header)

    def test_fire_observation(self) -> None:
        """Exercise request, acquire, response, and flush cases. / 覆盖请求、发出、响应与 flush 情况。"""

        module = load_subject()
        self.assertEqual(
            {"req_fire": 1, "acquire_fire": 1, "response_fire": 1, "blocked": 0},
            module.mshr_observation(True, True, True, True, True, True),
        )
        self.assertEqual(
            {"req_fire": 0, "acquire_fire": 0, "response_fire": 0, "blocked": 1},
            module.mshr_observation(True, True, True, True, True, True, flush=True),
        )


if __name__ == "__main__":
    unittest.main()
