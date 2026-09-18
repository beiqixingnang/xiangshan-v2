#!/usr/bin/env python3
# Module Contract
"""Reusable direct tests for UHSC V2 DCache metadata arrays."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest
from typing import Any

from amaranth.sim import Settle, Simulator, Tick

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Memory.Dcache.MetaArray-Hardware.py"


# Load the exact Build. / 加载精确 Build。
def load_subject() -> Any:
    """Load the metadata aggregate. / 加载元数据聚合。"""

    spec = importlib.util.spec_from_file_location("testing_dcache_meta", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); return module


class DcacheMetaArrayTest(unittest.TestCase):
    """Check same-name exports and coherent-state storage. / 检查同名导出及一致性状态存储。"""

    def test_all_members_export(self) -> None:
        module = load_subject()
        for member in module.COVERED_MODULES:
            self.assertIn(f"module {member}", module.build_verilog({"module": member}, {}))

    def test_coherent_metadata_write_read(self) -> None:
        module = load_subject(); dut = module.DcacheMetaArrayFamily("L1CohMetaArray"); result: list[int] = []

        def process():
            yield dut.ports["io_write_0_valid"].eq(1); yield dut.ports["io_write_0_bits_idx"].eq(7)
            yield dut.ports["io_write_0_bits_way_en"].eq(1); yield dut.ports["io_write_0_bits_meta_coh_state"].eq(2)
            yield Tick(); yield dut.ports["io_write_0_valid"].eq(0); yield dut.ports["io_read_0_valid"].eq(1)
            yield dut.ports["io_read_0_bits_idx"].eq(7); yield Tick(); yield Settle()
            result.append(int((yield dut.ports["io_resp_0_0_coh_state"])))

        sim = Simulator(dut); sim.add_clock(1e-6); sim.add_process(process); sim.run(); self.assertEqual([2], result)


if __name__ == "__main__":
    unittest.main()
