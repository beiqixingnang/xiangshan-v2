#!/usr/bin/env python3
# Module Contract
"""Reusable direct tests for the Kunminghu V2 ICache replacer.

The suite covers the two-bank index mapping and the delayed victim response
contract.  It deliberately does not import ``validation/`` or claim a full
ICache parent differential result.
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
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Frontend.Icache.ICacheReplacer-Hardware.py"


# Load the exact Build file without package discovery. / 按精确路径加载 Build 文件，不依赖包发现。
def load_subject() -> Any:
    """Load the ICacheReplacer Build module. / 加载 ICacheReplacer Build 模块。"""

    spec = importlib.util.spec_from_file_location("testing_v2_icache_replacer_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Subject Contract
class ICacheReplacerContractTest(unittest.TestCase):
    """Check the V2 geometry and interleaving oracle. / 检查 V2 几何配置与交错映射模型。"""

    def test_two_bank_index_mapping(self) -> None:
        module = load_subject()
        self.assertEqual({"bank": 0, "bank_set": 0, "request_valid": 1},
                         module.replacer_request_observation(0, True))
        self.assertEqual({"bank": 1, "bank_set": 0, "request_valid": 1},
                         module.replacer_request_observation(1, True))
        self.assertEqual({"bank": 0, "bank_set": 127, "request_valid": 0},
                         module.replacer_request_observation(254, False))
        self.assertEqual({"bank": 1, "bank_set": 127, "request_valid": 0},
                         module.replacer_request_observation(255, False))

    def test_invalid_geometry_is_rejected(self) -> None:
        module = load_subject()
        with self.assertRaises(ValueError):
            module.ReplacerConfig(n_sets=3)
        with self.assertRaises(ValueError):
            module.ReplacerConfig(port_number=1)

    def test_export_has_stable_module_name(self) -> None:
        module = load_subject()
        rtl = module.build_verilog(None, {})
        self.assertIn("module ICacheReplacer", rtl)
        self.assertIn("io_victim_way", rtl)


# Behavior Tests
class ICacheReplacerBehaviorTest(unittest.TestCase):
    """Check delayed victim touch and deterministic PLRU state. / 检查延迟受害路触碰与确定性 PLRU 状态。"""

    def test_victim_touch_is_registered_for_one_cycle(self) -> None:
        module = load_subject()
        dut = module.ICacheReplacer()
        observed: list[int] = []

        # The Build uses the implicit ``sync`` domain; add_clock drives it.
        sim = Simulator(dut)
        sim.add_clock(1e-6)

        def sync_process():
            yield dut.victim_req_v_set_idx.eq(0)
            yield dut.victim_req_valid.eq(1)
            yield Settle()
            observed.append(int((yield dut.victim_resp_way)))
            yield Tick()
            yield Settle()
            observed.append(int((yield dut.victim_resp_way)))
            yield dut.victim_req_valid.eq(0)
            yield Tick()
            yield Settle()
            observed.append(int((yield dut.victim_resp_way)))
            yield Tick()
            yield Settle()
            observed.append(int((yield dut.victim_resp_way)))

        sim.add_process(sync_process)
        sim.run()
        self.assertEqual([0, 0, 2, 2], observed)


if __name__ == "__main__":
    unittest.main()
