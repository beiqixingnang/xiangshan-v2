#!/usr/bin/env python3
# Module Contract
"""Reusable direct tests for the Kunminghu V2 Sstc interrupt generator.

These tests intentionally stay independent of the migration-only validators:
they load the local Build path, exercise the public equations, and check the
registered update boundary.  They are reusable test subjects, not acceptance
evidence for the complete NewCSR parent.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from typing import Any

from amaranth.sim import Delay, Simulator


# Fixtures And Support
ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Fu.NewCSR.SstcInterruptGen-Hardware.py"


# Load the exact Build file without relying on package installation. / 按精确路径加载 Build 文件。
def load_subject() -> Any:
    """Load the Sstc Build module from this checkout. / 从当前检出加载 Sstc Build 模块。"""

    spec = importlib.util.spec_from_file_location("testing_v2_sstc_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {TARGET}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tick(signal: Any):
    """Generate one deterministic rising-edge cycle. / 生成一个确定性的上升沿周期。"""

    yield signal.eq(0)
    yield Delay(1e-9)
    yield signal.eq(1)
    yield Delay(1e-9)


# Subject Contract
class SstcInterruptGenContractTest(unittest.TestCase):
    """Check the stable public contract and pure comparison oracle. / 检查稳定公共契约与纯比较模型。"""

    def test_unsigned_observation_masks_to_xlen(self) -> None:
        module = load_subject()
        self.assertEqual({"STIP": 1, "VSTIP": 0}, module.sstc_observation(
            -1, 0, 0, 1, True, True))
        self.assertEqual({"STIP": 0, "VSTIP": 1}, module.sstc_observation(
            0, 1, -1, 0, True, True))
        self.assertEqual({"STIP": 0, "VSTIP": 0}, module.sstc_observation(
            9, 0, 9, 0, False, False))

    def test_export_has_stable_module_name(self) -> None:
        module = load_subject()
        rtl = module.build_verilog(None, {})
        self.assertIn("module SstcInterruptGen", rtl)
        self.assertIn("o_STIP", rtl)
        self.assertIn("o_VSTIP", rtl)


# Behavior Tests
class SstcInterruptGenBehaviorTest(unittest.TestCase):
    """Exercise the two independent RegEnable-style update paths. / 检查两条独立的 RegEnable 更新路径。"""

    def test_stip_and_vstip_update_only_when_their_enable_is_asserted(self) -> None:
        module = load_subject()
        dut = module.SstcInterruptGen()
        observed: list[tuple[int, int]] = []

        def process():
            yield dut.reset.eq(1)
            yield Delay(1e-9)
            yield dut.reset.eq(0)
            yield dut.i_stime_bits.eq(10)
            yield dut.i_stimecmp_rdata.eq(10)
            yield dut.i_menvcfg_STCE.eq(1)
            yield dut.i_stime_valid.eq(1)
            yield from tick(dut.clock)
            observed.append((int((yield dut.o_STIP)), int((yield dut.o_VSTIP))))

            # Changing the comparison without an enable must retain STIP. /
            # 未使能时改变比较输入，STIP 应保持寄存值。
            yield dut.i_stime_valid.eq(0)
            yield dut.i_stime_bits.eq(0)
            yield from tick(dut.clock)
            observed.append((int((yield dut.o_STIP)), int((yield dut.o_VSTIP))))

            yield dut.i_vstime_bits.eq(7)
            yield dut.i_vstimecmp_rdata.eq(3)
            yield dut.i_henvcfg_STCE.eq(1)
            yield dut.i_vstime_valid.eq(1)
            yield from tick(dut.clock)
            observed.append((int((yield dut.o_STIP)), int((yield dut.o_VSTIP))))

        sim = Simulator(dut)
        sim.add_process(process)
        sim.run()
        self.assertEqual([(1, 0), (1, 0), (1, 1)], observed)


if __name__ == "__main__":
    unittest.main()
