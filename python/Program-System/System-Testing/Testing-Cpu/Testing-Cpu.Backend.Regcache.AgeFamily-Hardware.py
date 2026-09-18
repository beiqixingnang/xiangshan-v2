#!/usr/bin/env python3
# Module Contract
"""Reusable direct tests for the UHSC V2 age/regcache aggregate."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest
from typing import Any

from amaranth.sim import Settle, Simulator

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Regcache.AgeFamily-Hardware.py"


# Load exact local Build. / 加载精确本地 Build。
def load_subject() -> Any:
    """Load the age family aggregate."""

    spec = importlib.util.spec_from_file_location("testing_age_family", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); return module


class AgeFamilyTest(unittest.TestCase):
    """Check all ten same-name exports and bounded issue-age behavior."""

    def test_all_members_export(self) -> None:
        module = load_subject()
        for member in module.COVERED_MODULES:
            self.assertIn(f"module {member}", module.build_verilog({"module": member}, {}))

    def test_new_age_detector_emits_can_issue_value(self) -> None:
        module = load_subject(); dut = module.AgeFamily("NewAgeDetector"); observed: list[int] = []

        def process():
            yield dut.ports["io_canIssue_0"].eq(2); yield Settle(); observed.append(int((yield dut.ports["io_out_0"])))

        sim = Simulator(dut); sim.add_process(process); sim.run(); self.assertEqual([2], observed)


if __name__ == "__main__":
    unittest.main()
