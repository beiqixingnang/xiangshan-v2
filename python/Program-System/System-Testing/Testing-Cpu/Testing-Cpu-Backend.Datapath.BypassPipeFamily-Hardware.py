"""Reusable bounded tests for the UHSC V2 bypass/pipe family."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any

from amaranth.sim import Simulator

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Cpu-Core-Backend.Datapath.BypassPipeFamily-Hardware.py"


def load_subject() -> Any:
    spec = importlib.util.spec_from_file_location("testing_bypass_pipe_family", TARGET)
    if spec is None or spec.loader is None: raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); return module


class BypassPipeFamilyTest(unittest.TestCase):
    def test_all_members_export(self) -> None:
        module = load_subject()
        for member in module.COVERED_MODULES: self.assertIn(f"module {member}", module.build_verilog({"module": member}, {}))

    def test_pipe_group_connect_capture_hold_flush_and_replace(self) -> None:
        module = load_subject()
        subject = module.BypassPipeFamily("PipeGroupConnect")
        ports = subject.ports

        def set_all_inputs(context: Any, value: int = 0) -> None:
            for name, direction, _width in subject.specs:
                if direction == "input" and name != "clock":
                    context.set(ports[name], value)

        def set_lane(context: Any, lane: int, token: int, valid: int = 1) -> None:
            context.set(ports[f"io_in_{lane}_valid"], valid)
            context.set(ports[f"io_in_{lane}_bits_instr"], token)
            context.set(ports[f"io_in_{lane}_bits_pdest"], token + 0x40)
            context.set(ports[f"io_in_{lane}_bits_imm"], (token << 4) | lane)

        def assert_outputs(context: Any, tokens: list[int], valid: int) -> None:
            for lane, token in enumerate(tokens):
                self.assertEqual(context.get(ports[f"io_out_{lane}_valid"]), valid)
                if valid:
                    self.assertEqual(context.get(ports[f"io_out_{lane}_bits_instr"]), token)
                    # pdest is an 8-bit field in the locked ABI.
                    self.assertEqual(context.get(ports[f"io_out_{lane}_bits_pdest"]), (token + 0x40) & 0xFF)
                    self.assertEqual(context.get(ports[f"io_out_{lane}_bits_imm"]), (token << 4) | lane)

        async def bench(context: Any) -> None:
            set_all_inputs(context)
            context.set(ports["reset"], 1)
            await context.delay(1e-9)
            await context.tick()
            assert_outputs(context, [0] * 6, 0)
            for lane in range(6):
                self.assertEqual(context.get(ports[f"io_in_{lane}_ready"]), 1)

            # Capture six lanes in one cycle and verify payload preservation.
            context.set(ports["reset"], 0)
            for lane in range(6):
                set_lane(context, lane, 0x100 + lane)
            await context.tick()
            for lane in range(6):
                context.set(ports[f"io_in_{lane}_valid"], 0)
                context.set(ports[f"io_out_{lane}_ready"], 0)
            await context.tick()
            assert_outputs(context, [0x100 + lane for lane in range(6)], 1)

            # Backpressure holds every lane; one ready output clears only itself.
            context.set(ports["io_out_2_ready"], 1)
            await context.tick()
            self.assertEqual(context.get(ports["io_out_2_valid"]), 0)
            for lane in (0, 1, 3, 4, 5):
                self.assertEqual(context.get(ports[f"io_out_{lane}_valid"]), 1)
            self.assertEqual(context.get(ports["io_out_1_bits_instr"]), 0x101)

            # Flush wins over a simultaneous fresh input, even when outAllFire
            # would otherwise permit replacing occupied lanes.
            context.set(ports["io_flush"], 1)
            context.set(ports["io_outAllFire"], 1)
            for lane in range(6):
                set_lane(context, lane, 0x200 + lane)
            await context.tick()
            for lane in range(6):
                context.set(ports[f"io_in_{lane}_valid"], 0)
                context.set(ports[f"io_out_{lane}_ready"], 0)
            context.set(ports["io_flush"], 0)
            context.set(ports["io_outAllFire"], 0)
            await context.tick()
            assert_outputs(context, [0] * 6, 0)

            # With all lanes occupied, outAllFire allows a same-cycle payload
            # replacement; the new bits must be captured on every lane.
            for lane in range(6):
                set_lane(context, lane, 0x300 + lane)
            await context.tick()
            for lane in range(6):
                context.set(ports[f"io_in_{lane}_valid"], 0)
                context.set(ports[f"io_out_{lane}_ready"], 0)
            await context.tick()
            assert_outputs(context, [0x300 + lane for lane in range(6)], 1)

            context.set(ports["io_outAllFire"], 1)
            for lane in range(6):
                set_lane(context, lane, 0x400 + lane)
            await context.tick()
            for lane in range(6):
                context.set(ports[f"io_in_{lane}_valid"], 0)
            context.set(ports["io_outAllFire"], 0)
            await context.tick()
            assert_outputs(context, [0x400 + lane for lane in range(6)], 1)

            # A final ready pulse drains all six held entries independently.
            for lane in range(6):
                context.set(ports[f"io_out_{lane}_ready"], 1)
            await context.tick()
            assert_outputs(context, [0] * 6, 0)

        simulator = Simulator(subject)
        simulator.add_clock(1e-6)
        simulator.add_testbench(bench)
        simulator.run()


if __name__ == "__main__": unittest.main()
