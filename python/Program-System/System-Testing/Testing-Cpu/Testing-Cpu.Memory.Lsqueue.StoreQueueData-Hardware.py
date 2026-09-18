#!/usr/bin/env python3
# Module Contract
"""Reusable direct tests for UHSC V2 store-queue data arrays."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest
from typing import Any

from amaranth.sim import Settle, Simulator, Tick

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Memory.Lsqueue.StoreQueueData-Hardware.py"


# Load the exact Build. / 加载精确 Build。
def load_subject() -> Any:
    """Load the store-queue aggregate. / 加载存储队列聚合。"""

    spec = importlib.util.spec_from_file_location("testing_sq_data", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); return module


class StoreQueueDataTest(unittest.TestCase):
    """Check exports and representative address forwarding. / 检查导出及代表性地址转发。"""

    def test_all_members_export(self) -> None:
        module = load_subject()
        for member in module.COVERED_MODULES:
            self.assertIn(f"module {member}", module.build_verilog({"module": member}, {}))

    def test_address_cam_detects_matching_entry(self) -> None:
        module = load_subject(); dut = module.StoreQueueDataFamily("SQAddrModule"); result: list[int] = []

        def process():
            yield dut.ports["io_wen_0"].eq(1); yield dut.ports["io_waddr_0"].eq(5); yield dut.ports["io_wdata_0"].eq(0x1000)
            yield dut.ports["io_wmask_0"].eq(0xFFFF); yield dut.ports["io_wlineflag_0"].eq(1)
            yield Tick(); yield dut.ports["io_wen_0"].eq(0); yield dut.ports["io_forwardMdata_0"].eq(0x1000); yield Settle()
            result.append(int((yield dut.ports["io_forwardMmask_0_5"])))

        sim = Simulator(dut); sim.add_clock(1e-6); sim.add_process(process); sim.run(); self.assertEqual([1], result)


if __name__ == "__main__":
    unittest.main()
