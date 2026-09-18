#!/usr/bin/env python3
# Module Contract
"""Test the locked-port backend small-control aggregate."""

from __future__ import annotations

import hashlib
import re
import unittest
from types import ModuleType
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    def test_hardware_package(package_id: str) -> dict[str, str]: ...
    def test_load_subject_module(subject_type: str, subject_id: str) -> ModuleType: ...


# Fixtures And Support
TEST_ID: Final = "Cpu.Backend.SmallControl.Family"
SUBJECT_TYPE: Final = "build"
SUBJECT_ID: Final = "Cpu.Backend.SmallControl.Family"
DIRECT: Final = True

MEMBERS: Final = (
    "AddrAddModule",
    "GPAMem",
    "RedirectGenerator",
    "RegCache",
    "RegCacheTagTable",
    "RASStack",
    "FauFTBWay",
    "VectorCvtTop",
)


# Subject Contract
class BuildSubjectContractTest(unittest.TestCase):
    def test_subject_contract(self) -> None:
        result = test_hardware_package(SUBJECT_ID)
        self.assertEqual(SUBJECT_ID, result["id"])


# Behavior Tests
class SmallControlFamilyContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = test_load_subject_module(SUBJECT_TYPE, SUBJECT_ID)

    def test_catalog_is_locked_and_complete(self) -> None:
        self.assertEqual(MEMBERS, tuple(self.module.COVERED_MODULES))
        self.assertEqual(set(MEMBERS), set(self.module.PORT_SPECS))
        self.assertEqual(
            (5, 11, 56, 92, 111, 47, 46, 14),
            tuple(len(self.module.PORT_SPECS[name]) for name in MEMBERS),
        )
        for name in MEMBERS:
            for port in self.module.PORT_SPECS[name]:
                self.assertIn(port.direction, ("input", "output"))
                self.assertGreaterEqual(port.width, 1)

    def test_each_member_exports_non_empty_deterministic_verilog(self) -> None:
        for name in MEMBERS:
            with self.subTest(member=name):
                first = self.module.build_verilog({"module": name}, {})
                second = self.module.build_verilog({"module": name}, {})
                self.assertEqual(first, second)
                self.assertGreater(len(first), 100)
                self.assertRegex(first, rf"\bmodule\s+{re.escape(name)}\b")
                self.assertNotEqual(hashlib.sha256(first.encode()).hexdigest(), "0" * 64)

    def test_public_adapter_rejects_unknown_member(self) -> None:
        with self.assertRaises(ValueError):
            self.module.build_verilog({"module": "NotARealSmallControlLeaf"}, {})
