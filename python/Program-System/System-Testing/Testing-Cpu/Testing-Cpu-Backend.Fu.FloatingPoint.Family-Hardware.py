"""Direct contract and behavior checks for the floating-point family Build."""

# Module Contract
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any

from amaranth.sim import Simulator

# Fixtures And Support
TEST_ID = "Build-Cpu.Backend.Fu.FloatingPoint.Family"
SUBJECT_TYPE = "build"
SUBJECT_ID = "Build-Cpu.Backend.Fu.FloatingPoint.Family"
DIRECT = True

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Cpu-Core-Backend.Fu.FloatingPoint.Family-Hardware.py"


def load_subject() -> Any:
    spec = importlib.util.spec_from_file_location("testing_fp_subject", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Subject Contract
class BuildSubjectContractTest(unittest.TestCase):
    def test_subject_contract(self) -> None:
        module = load_subject()
        self.assertEqual(module.COVERED_MODULES, (
            "FloatAdder", "FloatAdderF32F16MixedPipeline", "FloatAdderF64Pipeline",
            "FloatDivider", "FloatDividerR64", "FloatFMA", "fpdiv_r64_block",
            "fpsqrt_r16", "BoothEncoderF64F32F16", "ArrayMulDataModule", "IntToFPDataModule",
        ))
        self.assertEqual(module.IMPLEMENTED_MEMBERS, ("BoothEncoderF64F32F16", "ArrayMulDataModule"))
        self.assertEqual(set(module.IMPLEMENTED_MEMBERS) | set(module.CONTRACT_ONLY_MEMBERS), set(module.COVERED_MODULES))
        self.assertFalse(set(module.IMPLEMENTED_MEMBERS) & set(module.CONTRACT_ONLY_MEMBERS))


# Behavior Tests
class FloatingPointBehaviorTest(unittest.TestCase):
    def test_booth_member_has_input_dependent_partial_products(self) -> None:
        module = load_subject()
        dut = module.FloatingPointFamily("BoothEncoderF64F32F16")
        sim = Simulator(dut)
        ports = dut.ports
        out_names = [f"io_out_pp_{i}" for i in range(27)]
        observed: list[list[int]] = []

        async def bench(ctx: Any) -> None:
            for mode64, mode32, a_value, b_value in (
                (0, 0, 0x7FF, 0x7FF),
                (0, 1, 0xA5C321, 0xFEDCBA),
                (1, 0, 0x13579BDF2468A, 0x1ABCDEFFEDCBA),
                (1, 1, 0x1ABCDEFFEDCBA, 0x123456789ABCD),
            ):
                ctx.set(ports["io_in_a"], a_value)
                ctx.set(ports["io_in_b"], b_value)
                ctx.set(ports["io_is_fp64"], mode64)
                ctx.set(ports["io_is_fp32"], mode32)
                await ctx.delay(1e-9)
                observed.append([ctx.get(ports[name]) for name in out_names])

        sim.add_testbench(bench)
        sim.run()
        self.assertEqual(len(observed), 4)
        self.assertTrue(all(any(result) for result in observed))
        self.assertTrue(any(observed[0][i] != observed[2][i] for i in range(27)))
        self.assertEqual(observed[0][6:], [0] * 21)
        self.assertEqual(observed[1][13:], [0] * 14)

    def test_array_multiplier_locked_vectors(self) -> None:
        module = load_subject()
        dut = module.FloatingPointFamily("ArrayMulDataModule")
        sim = Simulator(dut)
        sim.add_clock(1e-6)
        ports = dut.ports
        mask_a = (1 << 65) - 1
        vectors = (
            (1, 1, 0x1),
            (3, 5, 0xF),
            ((1 << 65) - 1, 1, 0x3FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF),
            (1 << 64, 2, 0x3FFFFFFFFFFFFFFFD0000000000000000),
            ((1 << 65) - 1, (1 << 65) - 1, 0x1),
        )

        async def bench(ctx: Any) -> None:
            for a_value, b_value, expected in vectors:
                ctx.set(ports["io_a"], a_value & mask_a)
                ctx.set(ports["io_b"], b_value & mask_a)
                ctx.set(ports["io_regEnables_0"], 1)
                ctx.set(ports["io_regEnables_1"], 0)
                await ctx.tick()
                ctx.set(ports["io_regEnables_0"], 0)
                ctx.set(ports["io_regEnables_1"], 1)
                await ctx.tick()
                self.assertEqual(ctx.get(ports["io_result"]), expected)
                ctx.set(ports["io_regEnables_1"], 0)
                await ctx.tick()
                self.assertEqual(ctx.get(ports["io_result"]), expected)

        sim.add_testbench(bench)
        sim.run()

    def test_array_multiplier_enable_stages_hold_state(self) -> None:
        module = load_subject()
        dut = module.FloatingPointFamily("ArrayMulDataModule")
        sim = Simulator(dut)
        sim.add_clock(1e-6)
        ports = dut.ports

        async def bench(ctx: Any) -> None:
            ctx.set(ports["io_a"], 3)
            ctx.set(ports["io_b"], 5)
            ctx.set(ports["io_regEnables_0"], 1)
            ctx.set(ports["io_regEnables_1"], 0)
            await ctx.tick()
            ctx.set(ports["io_a"], 100)
            ctx.set(ports["io_b"], 200)
            ctx.set(ports["io_regEnables_0"], 0)
            await ctx.tick()
            ctx.set(ports["io_regEnables_1"], 1)
            await ctx.tick()
            self.assertEqual(ctx.get(ports["io_result"]), 0xF)
            ctx.set(ports["io_regEnables_1"], 0)
            await ctx.tick()
            self.assertEqual(ctx.get(ports["io_result"]), 0xF)

        sim.add_testbench(bench)
        sim.run()
