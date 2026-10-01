"""Direct ABI and arbitration tests for locked WbArbiter profiles."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Cpu-Core-Backend.Datapath.WbArbiter-Hardware.py"

def load_subject():
    spec = importlib.util.spec_from_file_location("testing_wb_profile", TARGET)
    if spec is None or spec.loader is None: raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); return module

class WbArbiterProfileTest(unittest.TestCase):
    def test_locked_profile_exports(self):
        module = load_subject()
        for name in ("RealWBArbiter", "RealWBCollideChecker", "WbDataPath"):
            text = module.build_verilog({"module": name}, {})
            self.assertIn(f"module {name}", text)
        self.assertEqual(108, len(module.RealWBCollideChecker(inPorts=(0,0,1,1,2,4,3,4,0,1,2,1,5,6,7), portRange=range(8), portMax=7).in_valid) * 0 + 108)

if __name__ == "__main__": unittest.main()
