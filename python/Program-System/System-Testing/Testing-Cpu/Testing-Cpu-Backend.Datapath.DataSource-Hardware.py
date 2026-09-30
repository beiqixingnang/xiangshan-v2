"""Direct bounded test for the UHSC V2 DataSource selector.

This test covers every four-bit selector value and checks the public
predicates against the locked DataSource.scala equations.  It records no
strict-equivalence claim: the V2 reference catalog has only a source-level
parent surface and no standalone locked DataSource module.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any

from amaranth.sim import Settle, Simulator


ROOT = Path(__file__).resolve().parents[4]
TARGET = (
    ROOT
    / "python/Program-System/System-Build/Build-Cpu/Cpu-Core"
    / "Cpu-Core-Backend.Datapath.DataSource-Hardware.py"
)


def load_subject() -> Any:
    """Load the exact DataSource Build under test. / 加载精确 DataSource Build。"""

    spec = importlib.util.spec_from_file_location("testing_datasource", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def expected(value: int) -> tuple[int, ...]:
    """Evaluate the locked DataSource.scala selector equations."""

    return (
        (value >> 3) & 1,
        int(value == 0b1000),
        int(value == 0b0110),
        int(value == 0b0101),
        int(value == 0b0000),
        int(value == 0b0001),
        int(value == 0b0010),
        int(value == 0b0011),
        int(value == 0b0100),
    )


def observe(module: Any) -> list[tuple[int, ...]]:
    """Simulate all sixteen selector values through the public probe."""

    dut = module.DataSourceProbe()
    outputs = (
        dut.read_reg,
        dut.read_reg_oh,
        dut.read_reg_cache,
        dut.read_v0,
        dut.read_zero,
        dut.read_forward,
        dut.read_bypass,
        dut.read_bypass2,
        dut.read_imm,
    )
    rows: list[tuple[int, ...]] = []

    def process():
        for value in range(16):
            yield dut.value.eq(value)
            yield Settle()
            row: list[int] = []
            for signal in outputs:
                row.append(int((yield signal)))
            rows.append(tuple(row))

    simulator = Simulator(dut)
    simulator.add_process(process)
    simulator.run()
    return rows


class DataSourceDirectTest(unittest.TestCase):
    """Bounded direct tests for all selector encodings."""

    direct = True

    def test_all_selector_values(self) -> None:
        module = load_subject()
        self.assertEqual(observe(module), [expected(value) for value in range(16)])

    def test_same_name_deterministic_export(self) -> None:
        module = load_subject()
        first = module.build_verilog({"name": "DataSource"}, {})
        second = module.build_verilog({"name": "DataSource"}, {})
        self.assertEqual(first, second)
        self.assertIn("module DataSource", first)


if __name__ == "__main__":
    unittest.main()
