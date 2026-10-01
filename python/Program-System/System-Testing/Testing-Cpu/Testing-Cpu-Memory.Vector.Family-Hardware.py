"""Reusable bounded tests for the UHSC V2 vector-memory family."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any

from amaranth.sim import Simulator

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Cpu-Memory-Memory.Vector.Family-Hardware.py"


def load_subject() -> Any:
    spec = importlib.util.spec_from_file_location("testing_vector_memory_family", TARGET)
    if spec is None or spec.loader is None: raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); return module


class VectorMemoryFamilyTest(unittest.TestCase):
    def test_all_members_export(self) -> None:
        module = load_subject()
        for member in module.COVERED_MODULES: self.assertIn(f"module {member}", module.build_verilog({"module": member}, {}))

    def test_vfof_buffer_accumulates_vl_and_emits_final_uop(self) -> None:
        subject = load_subject()
        dut = subject.VectorMemoryFamily("VfofBuffer")
        simulator = Simulator(dut)
        simulator.add_clock(1e-6)

        async def bench(ctx: Any) -> None:
            for name, direction, _width in dut.specs:
                if direction == "input":
                    ctx.set(dut.ports[name], 0)

            # Establish the asynchronous reset state.
            ctx.set(dut.ports["reset"], 1)
            await ctx.tick()
            ctx.set(dut.ports["reset"], 0)
            await ctx.tick()

            # First VLEFF segment captures the uop and initial VL, but does
            # not emit until the final segment is observed.
            ctx.set(dut.ports["io_in_0_valid"], 1)
            ctx.set(dut.ports["io_in_0_bits_uop_vpu_isVleff"], 1)
            ctx.set(dut.ports["io_in_0_bits_uop_vpu_lastUop"], 0)
            ctx.set(dut.ports["io_in_0_bits_uop_fuOpType"], 0x12)
            ctx.set(dut.ports["io_in_0_bits_uop_pdest"], 0x55)
            ctx.set(dut.ports["io_in_0_bits_uop_robIdx_value"], 7)
            ctx.set(dut.ports["io_in_0_bits_src_4"], 37)
            await ctx.tick()
            self.assertEqual(ctx.get(dut.ports["io_uopWriteback_valid"]), 0)
            self.assertEqual(ctx.get(dut.ports["io_uopWriteback_bits_uop_vpu_vl"]), 37)

            # A matching merge writeback lowers VL while the entry is waiting
            # for its final segment.
            ctx.set(dut.ports["io_in_0_valid"], 0)
            ctx.set(dut.ports["io_mergeUopWriteback_0_valid"], 1)
            ctx.set(dut.ports["io_mergeUopWriteback_0_bits_robidx_value"], 7)
            ctx.set(dut.ports["io_mergeUopWriteback_0_bits_vl"], 12)
            await ctx.tick()
            self.assertEqual(ctx.get(dut.ports["io_uopWriteback_valid"]), 0)
            self.assertEqual(ctx.get(dut.ports["io_uopWriteback_bits_uop_vpu_vl"]), 12)

            # The final segment replaces the stored uop while preserving the
            # accumulated VL, producing one writeback pulse.
            ctx.set(dut.ports["io_mergeUopWriteback_0_valid"], 0)
            ctx.set(dut.ports["io_in_0_valid"], 1)
            ctx.set(dut.ports["io_in_0_bits_uop_vpu_lastUop"], 1)
            ctx.set(dut.ports["io_in_0_bits_uop_pdest"], 0x66)
            await ctx.tick()
            self.assertEqual(ctx.get(dut.ports["io_uopWriteback_valid"]), 1)
            self.assertEqual(ctx.get(dut.ports["io_uopWriteback_bits_uop_pdest"]), 0x66)
            self.assertEqual(ctx.get(dut.ports["io_uopWriteback_bits_uop_vpu_vl"]), 12)
            self.assertEqual(ctx.get(dut.ports["io_uopWriteback_bits_data"]), 12)

            # There is no ready port on this ABI; the valid pulse consumes the
            # entry at the following edge.
            ctx.set(dut.ports["io_in_0_valid"], 0)
            await ctx.tick()
            self.assertEqual(ctx.get(dut.ports["io_uopWriteback_valid"]), 0)

        simulator.add_testbench(bench)
        simulator.run()


if __name__ == "__main__": unittest.main()
