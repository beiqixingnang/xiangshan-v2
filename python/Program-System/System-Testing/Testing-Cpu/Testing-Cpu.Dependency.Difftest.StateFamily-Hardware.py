"""Reusable bounded tests for the UHSC V2 difftest state family."""
from __future__ import annotations
import importlib.util, sys, unittest
from pathlib import Path
from typing import Any
ROOT = Path(__file__).resolve().parents[4]; TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Dependency.Difftest.StateFamily-Hardware.py"
def load_subject() -> Any:
    spec = importlib.util.spec_from_file_location("testing_dt", TARGET)
    if spec is None or spec.loader is None: raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); return module
class DifftestStateFamilyTest(unittest.TestCase):
    def test_all_members_export(self) -> None:
        module = load_subject()
        for member in module.COVERED_MODULES: self.assertIn(f"module {member}", module.build_verilog({"module": member}, {}))
if __name__ == "__main__": unittest.main()
