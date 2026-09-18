"""System-Testing contract for the bounded Rocket TL child family.

This test locks the eleven selected L2Top child inventories and verifies that
relay, merger and BusErrorUnit equations remain deterministic. It does not
close the L2Top parent or any XSTile/XSCore family.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Build-Cpu.Dependency.Rocket.TLChildren.Family-Hardware.py"
)
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
MEMBERS = (
    "TLXbar_7", "TLXbar_8", "TLXbar_9", "TLBuffer_27", "TLBuffer_20",
    "TLBuffer_29", "TLBuffer_22", "TLBuffer_16", "TLBuffer_2",
    "TLClientsMerger_1", "BusErrorUnit",
)


def load_subject():
    spec = importlib.util.spec_from_file_location("tl_children_subject", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TLChildrenFamilyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_subject()

    def test_locked_members_and_ports(self) -> None:
        hierarchy = json.loads(HIERARCHY.read_text(encoding="utf-8"))
        self.assertEqual(MEMBERS, tuple(self.module.COVERED_MODULES))
        for member in MEMBERS:
            with self.subTest(member=member):
                expected = hierarchy["modules"][member]["ports"]
                actual = self.module.PORT_SPECS[member]
                self.assertEqual(len(expected), len(actual))
                self.assertEqual(
                    [(row["name"], row["direction"],
                      int(row["width"][1:row["width"].find(":")])
                      - int(row["width"][row["width"].find(":") + 1:-1]) + 1
                      if str(row["width"]).startswith("[") else 1)
                     for row in expected],
                    list(actual),
                )

    def test_deterministic_exact_exports(self) -> None:
        for member in MEMBERS:
            with self.subTest(member=member):
                first = self.module.build_verilog({"module": member}, {})
                second = self.module.build_verilog({"module": member}, {})
                self.assertEqual(first, second)
                self.assertRegex(first, rf"\bmodule\s+{re.escape(member)}\b")
                self.assertGreater(len(first), 100)
                self.assertNotEqual(hashlib.sha256(first.encode()).hexdigest(), "0" * 64)

    def test_source_equations(self) -> None:
        self.assertEqual(
            {"ready": 1, "valid": 1, "fire": 1, "reset": 0},
            self.module.relay_observation(valid=True, ready=True),
        )
        self.assertEqual(
            {"min_id": 0, "max_id": 16, "source_id_width": 16, "client_count": 2},
            self.module.merge_source_ids([4, 8], starts=[0, 8]),
        )
        self.assertEqual(
            {"cause_valid": 1, "cause": 1, "global_interrupt": 0, "local_interrupt": 1},
            self.module.bus_error_observation([False, True], [True, True],
                                              [True, False], [False, True]),
        )

    def test_unknown_member_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.module.build_verilog({"module": "NotATLChild"}, {})


if __name__ == "__main__":
    unittest.main()
