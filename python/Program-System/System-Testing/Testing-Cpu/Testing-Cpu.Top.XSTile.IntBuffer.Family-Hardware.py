"""Bounded tests for the XSTile IntBuffer family."""
from __future__ import annotations
import importlib.util, sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Top.XSTile.IntBuffer.Family-Hardware.py"
def load_subject():
    spec = importlib.util.spec_from_file_location("intbuffer_subject", TARGET); module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); return module
class IntBufferFamilyTest(unittest.TestCase):
    def test_exports(self):
        module = load_subject()
        for member in module.COVERED_MODULES: self.assertIn("module " + member, module.build_verilog({"module": member}, {}))
if __name__ == "__main__": unittest.main()
