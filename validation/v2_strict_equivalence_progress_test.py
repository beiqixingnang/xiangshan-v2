"""Regression tests for the strict-equivalence progress audit."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v2_strict_equivalence_progress as progress


class BuildCatalogEnumerationTests(unittest.TestCase):
    """Keep dynamic Build catalogs from being reduced to regex fragments."""

    def test_regfile_runtime_catalog_has_every_locked_member(self) -> None:
        # This catalog is computed from embedded JSON and cannot be resolved by AST literals alone.
        build = Path(
            "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
            "Build-Cpu.Backend.Regfile.Regfile-Hardware.py"
        )
        failures: list[str] = []

        members = progress.build_declared_members(build, failures)

        self.assertEqual([], failures)
        self.assertEqual(97, len(members))
        self.assertIn("BusyTable", members)
        self.assertIn("RenameTable", members)
        self.assertIn("WbFuBusyTable", members)


if __name__ == "__main__":
    unittest.main()
