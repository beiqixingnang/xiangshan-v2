"""Direct checks for all locked CLZ and rounding primitive variants."""

# Module Contract
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any

from amaranth.sim import Simulator

# Fixtures And Support
TEST_ID = "Build-Cpu.Dependency.Fpu.NormalizeRoundFamily"
SUBJECT_TYPE = "build"
SUBJECT_ID = "Build-Cpu.Dependency.Fpu.NormalizeRoundFamily"
DIRECT = True

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Cpu-Core-Dependency.Fpu.NormalizeRoundFamily-Hardware.py"


def load_subject() -> Any:
    spec = importlib.util.spec_from_file_location("testing_normalize_round_subject", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def clz_expected(value: int, width: int, zero_sentinel: bool) -> int:
    if value == 0:
        return width if zero_sentinel else width - 1
    return width - value.bit_length()


def round_increment(value: int, round_in: int, sticky_in: int, sign_in: int,
                    mode: int, vector_surface: bool) -> int:
    inexact = bool(round_in or sticky_in)
    if mode == 0:
        return int(bool(round_in and (sticky_in or (value & 1))))
    if mode == 1:
        return 0
    if mode == 2:
        return int(bool(inexact and sign_in))
    if mode == 3:
        return int(bool(inexact and not sign_in))
    if mode == 4:
        return round_in
    if vector_surface and mode == 6:
        return int(bool(inexact and not (value & 1)))
    return 0


# Subject Contract
class BuildSubjectContractTest(unittest.TestCase):
    def test_subject_contract(self) -> None:
        module = load_subject()
        expected = (
            "CLZ", "CLZ_6", "CLZ_7", "CLZ_9", "CLZ_11", "CLZ_28", "CLZ_29", "CLZ_30", "CLZ_31",
            "RoundingUnit", "RoundingUnit_1", "RoundingUnit_2", "RoundingUnit_3", "RoundingUnit_4",
            "RoundingUnit_8", "RoundingUnit_9", "RoundingUnit_11",
        )
        self.assertEqual(module.COVERED_MODULES, expected)
        self.assertEqual(module.IMPLEMENTED_MEMBERS, expected)
        self.assertEqual(module.CONTRACT_ONLY_MEMBERS, ())
        for member in expected:
            with self.subTest(member=member):
                self.assertNotIn("clock", {name.lower() for name, _direction, _width in module.PORT_SPECS[member]})
                self.assertNotIn("reset", {name.lower() for name, _direction, _width in module.PORT_SPECS[member]})


# Behavior Tests
class NormalizeRoundBehaviorTest(unittest.TestCase):
    def test_every_clz_variant_matches_priority_and_zero_boundaries(self) -> None:
        module = load_subject()
        for member in module.CLZ_MEMBERS:
            input_width, output_width, zero_sentinel = module.CLZ_CONFIG[member]
            dut = module.NormalizeRoundFamily(member)
            sim = Simulator(dut)
            observed: list[tuple[int, int]] = []
            mask = (1 << input_width) - 1
            values = [0, mask]
            values.extend(1 << index for index in range(input_width))
            values.extend((mask ^ (1 << index)) for index in range(input_width))

            async def bench(ctx: Any) -> None:
                for value in values:
                    ctx.set(dut.ports["io_in"], value)
                    await ctx.delay(1e-9)
                    observed.append((value, ctx.get(dut.ports["io_out"])))

            sim.add_testbench(bench)
            sim.run()
            self.assertEqual(len(observed), len(values))
            for value, result in observed:
                with self.subTest(member=member, value=value):
                    self.assertLess(result, 1 << output_width)
                    self.assertEqual(result, clz_expected(value, input_width, zero_sentinel))

    def test_every_rounding_variant_matches_all_modes_and_carry(self) -> None:
        module = load_subject()
        for member in module.ROUNDING_MEMBERS:
            input_width, vector_surface = module.ROUNDING_CONFIG[member]
            dut = module.NormalizeRoundFamily(member)
            sim = Simulator(dut)
            observed: list[tuple[int, int, int, int, int, tuple[int, ...]]] = []
            mask = (1 << input_width) - 1
            values = (0, 1, 2, mask ^ 1, mask, 1 << (input_width - 1))

            async def bench(ctx: Any) -> None:
                for value in values:
                    for mode in range(8):
                        for round_in in range(2):
                            for sticky_in in range(2):
                                for sign_in in range(2):
                                    ctx.set(dut.ports["io_in"], value)
                                    ctx.set(dut.ports["io_rm"], mode)
                                    ctx.set(dut.ports["io_roundIn"], round_in)
                                    ctx.set(dut.ports["io_stickyIn"], sticky_in)
                                    ctx.set(dut.ports["io_signIn"], sign_in)
                                    await ctx.delay(1e-9)
                                    if vector_surface:
                                        actual = (
                                            ctx.get(dut.ports["io_inexact"]),
                                            ctx.get(dut.ports["io_r_up"]),
                                        )
                                    else:
                                        actual = (
                                            ctx.get(dut.ports["io_out"]),
                                            ctx.get(dut.ports["io_inexact"]),
                                            ctx.get(dut.ports["io_cout"]),
                                        )
                                    observed.append((value, mode, round_in, sticky_in, sign_in, actual))

            sim.add_testbench(bench)
            sim.run()
            self.assertEqual(len(observed), len(values) * 8 * 2 * 2 * 2)
            for value, mode, round_in, sticky_in, sign_in, actual in observed:
                increment = round_increment(value, round_in, sticky_in, sign_in, mode, vector_surface)
                inexact = int(bool(round_in or sticky_in))
                if vector_surface:
                    expected = (inexact, increment)
                else:
                    expected = ((value + increment) & mask, inexact, int(bool(increment and value == mask)))
                with self.subTest(member=member, value=value, mode=mode,
                                  round_in=round_in, sticky_in=sticky_in, sign_in=sign_in):
                    self.assertEqual(actual, expected)
