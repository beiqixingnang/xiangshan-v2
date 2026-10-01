"""Reusable bounded tests for the UHSC V2 decode/control family."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any

from amaranth.sim import Simulator

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Cpu-Core-Backend.Decode.ControlFamily-Hardware.py"


def load_subject() -> Any:
    spec = importlib.util.spec_from_file_location("testing_decode_control_family", TARGET)
    if spec is None or spec.loader is None: raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); return module


class DecodeControlFamilyTest(unittest.TestCase):
    def test_all_members_export(self) -> None:
        module = load_subject()
        for member in module.COVERED_MODULES: self.assertIn(f"module {member}", module.build_verilog({"module": member}, {}))

    def test_uop_info_amaranth_outputs(self) -> None:
        module = load_subject()
        self.assertEqual(("UopInfoGen",), tuple(module.IMPLEMENTED_MEMBERS))
        self.assertFalse(hasattr(module, "uop_info_reference"))
        dut = module.DecodeControlFamily("UopInfoGen")
        vectors = (
            (0b010010, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, (2, 2, 2, 0)),
            (0b101111, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, (8, 8, 2, 0)),
            (0b110011, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, (3, 3, 2, 0)),
            (0b110111, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, (4, 2, 1, 0)),
            (0b000100, 0, 0, 0, 0, 7, 0, 0, 0, 0, 0, (8, 8, 1, 0)),
            (0b000000, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, (1, 1, 1, 1)),
        )

        async def bench(ctx: Any) -> None:
            input_fields = (
                "io_in_preInfo_typeOfSplit", "io_in_preInfo_vlmul",
                "io_in_preInfo_vsew", "io_in_preInfo_vwidth",
                "io_in_preInfo_nf", "io_in_preInfo_vmvn",
                "io_in_preInfo_isVecArith", "io_in_preInfo_isVecMem",
                "io_in_preInfo_isAmoCAS", "io_in_preInfo_isVlsr",
                "io_in_preInfo_isVlsm",
            )
            for split, vlmul, vsew, vwidth, nf, vmvn, vec_arith, vec_mem, amo_cas, is_vlsr, is_vlsm, expected in vectors:
                values = (split, vlmul, vsew, vwidth, nf, vmvn, vec_arith, vec_mem, amo_cas, is_vlsr, is_vlsm)
                for name, value in zip(input_fields, values):
                    ctx.set(dut.ports[name], value)
                await ctx.delay(1e-9)
                actual = (
                    ctx.get(dut.ports["io_out_uopInfo_numOfUop"]),
                    ctx.get(dut.ports["io_out_uopInfo_numOfWB"]),
                    ctx.get(dut.ports["io_out_uopInfo_lmul"]),
                    ctx.get(dut.ports["io_out_isComplex"]),
                )
                self.assertEqual(expected, actual, split)

        simulator = Simulator(dut)
        simulator.add_testbench(bench)
        simulator.run()


if __name__ == "__main__": unittest.main()
