"""Reusable bounded tests for the UHSC V2 decode/control family."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Cpu-Core-Backend.Decode.ControlFamily-Hardware.py"


def load_subject() -> Any:
    spec = importlib.util.spec_from_file_location("testing_decode_control_family", TARGET)
    if spec is None or spec.loader is None: raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); return module


class DecodeControlFamilyTest(unittest.TestCase):
    def test_all_members_export(self) -> None:
        module = load_subject()
        for member in module.COVERED_MODULES: self.assertIn(f"module {member}", module.build_verilog({"module": member}, {}))

    def test_uop_info_real_equations(self) -> None:
        module = load_subject()
        self.assertEqual(("UopInfoGen",), tuple(module.IMPLEMENTED_MEMBERS))
        vectors = (
            ("VEC_VVV", 1, 0, 0, 0, 0, False, False, (2, 2, 2)),
            ("VEC_RGATHER", 3, 0, 0, 0, 0, False, False, (64, 64, 8)),
            ("VEC_I_LDST", 1, 0, 0, 1, 0, False, False, (5, 5, 2)),
            ("AMO_CAS_Q", 0, 0, 0, 0, 0, False, False, (4, 2, 1)),
            ("VEC_US_LDST", 1, 0, 0, 0, 0, True, False, (2, 2, 2)),
        )
        for name, vlmul, vsew, vwidth, nf, vmvn, is_vlsr, is_vlsm, expected in vectors:
            with self.subTest(name=name):
                actual = module.uop_info_reference(
                    module.UOP_SPLIT_CODES[name], vsew, vlmul, vwidth,
                    nf, vmvn, is_vlsr, is_vlsm,
                )
                self.assertEqual(expected, actual)


if __name__ == "__main__": unittest.main()
