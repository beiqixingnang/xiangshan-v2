"""Static ABI checks for the Utility ResidualFamily ClockGate reference."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from v2_utility_residual_clockgate_abi import (
    CLOCKGATE_PORTS,
    parse_module_ports,
    parse_reference,
)


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "validation/reference-sv/ClockGate.sv"
BUILD = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Build-Cpu.Dependency.Utility.ResidualFamily-Hardware.py"
)


class UtilityResidualClockGateAbiTest(unittest.TestCase):
    """Keep typed-net parsing and the Build ABI aligned without formal runs."""

    def test_locked_typed_nonansi_reference(self) -> None:
        self.assertEqual(parse_reference(REFERENCE), CLOCKGATE_PORTS)

    def test_generated_ansi_and_typed_widths(self) -> None:
        ansi = """module Demo(\n  input [3:0] data,\n  output ready\n);\nendmodule\n"""
        typed = """module Demo(data, ready);\n  input wire [3:0] data;\n  output logic ready;\nendmodule\n"""
        expected = {"data": ("input", 4), "ready": ("output", 1)}
        self.assertEqual(parse_module_ports(ansi, "Demo"), expected)
        self.assertEqual(parse_module_ports(typed, "Demo"), expected)

    def test_current_build_clockgate_export_matches_reference(self) -> None:
        spec = importlib.util.spec_from_file_location("utility_residual_build", BUILD)
        if spec is None or spec.loader is None:
            self.fail(f"cannot load Build module from {BUILD}")
        loader = spec.loader
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        rtl = module.build_verilog({"module": "ClockGate"}, {})
        self.assertEqual(parse_module_ports(rtl, "ClockGate"), CLOCKGATE_PORTS)


if __name__ == "__main__":
    unittest.main()
