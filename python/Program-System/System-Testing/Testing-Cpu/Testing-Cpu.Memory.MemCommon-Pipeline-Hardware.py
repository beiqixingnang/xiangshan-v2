#!/usr/bin/env python3
# Module Contract
"""Reusable direct tests for the UHSC memory pipeline-register family.

The file mirrors its Build subject and exercises the shared Decoupled elastic
register.  It does not claim full memory-parent reference equivalence.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest
from typing import Any

from amaranth.sim import Settle, Simulator, Tick


# Fixtures And Support
ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Memory.MemCommon-Pipeline-Hardware.py"


# Load the local Build through its exact path. / 通过精确路径加载本地 Build。
def load_subject() -> Any:
    """Load the pipeline aggregate. / 加载流水寄存器聚合。"""

    spec = importlib.util.spec_from_file_location("testing_memory_pipeline", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
    return module


class MemoryPipelineTest(unittest.TestCase):
    """Check every bundle specialization and the common handshake. / 检查每个 bundle 特化与共用握手。"""

    def test_all_members_export(self) -> None:
        module = load_subject()
        for member in module.COVERED_MODULES:
            self.assertIn(f"module {member}", module.build_verilog({"module": member}, {}))

    def test_register_captures_and_releases_payload(self) -> None:
        module = load_subject(); dut = module.PipelineRegFamily("PipelineRegModule_6"); seen: list[tuple[int, int, int]] = []

        def process():
            yield dut.ports["io_out_ready"].eq(0); yield dut.ports["io_in_valid"].eq(1)
            yield dut.ports["io_in_bits_data"].eq(0x123456789ABCDEF0); yield dut.ports["io_in_bits_id"].eq(9)
            yield Tick(); yield Settle(); seen.append((int((yield dut.ports["io_out_valid"])), int((yield dut.ports["io_out_bits_data"])), int((yield dut.ports["io_out_bits_id"]))))
            yield dut.ports["io_in_valid"].eq(0); yield dut.ports["io_out_ready"].eq(1)
            yield Tick(); yield Settle(); seen.append((int((yield dut.ports["io_out_valid"])), 0, 0))

        sim = Simulator(dut); sim.add_clock(1e-6); sim.add_process(process); sim.run()
        self.assertEqual((1, 0x123456789ABCDEF0, 9), seen[0]); self.assertEqual(0, seen[1][0])


if __name__ == "__main__":
    unittest.main()
