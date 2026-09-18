"""Reusable bounded tests for the final two family."""
from __future__ import annotations
import importlib.util,sys,unittest
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parents[4]; TARGET=ROOT/'python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.FinalTwo.Family-Hardware.py'
def load_subject()->Any:
 spec=importlib.util.spec_from_file_location('testing_final_two',TARGET)
 if spec is None or spec.loader is None: raise RuntimeError(TARGET)
 m=importlib.util.module_from_spec(spec); sys.modules[spec.name]=m; spec.loader.exec_module(m); return m
class FinalTwoFamilyTest(unittest.TestCase):
 def test_all_members_export(self)->None:
  m=load_subject()
  for n in m.COVERED_MODULES: self.assertIn(f'module {n}',m.build_verilog({'module':n},{}))
if __name__=='__main__': unittest.main()
