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
        self.assertEqual(("UopInfoGen", "VTypeGen", "FPDecoder", "VIAluDecoder"), tuple(module.IMPLEMENTED_MEMBERS))
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

    def test_vtypegen_amaranth_state_priority(self) -> None:
        module = load_subject()
        self.assertIn("VTypeGen", module.IMPLEMENTED_MEMBERS)
        dut = module.DecodeControlFamily("VTypeGen")
        simulator = Simulator(dut)
        simulator.add_clock(1e-6)

        def vset(vlmul: int, vsew: int, vta: int = 0, vma: int = 0, ivli: bool = False, reserved: int = 0) -> int:
            immediate = vlmul | (vsew << 3) | (vta << 6) | (vma << 7)
            return (0xC0000000 if ivli else 0) | (reserved << 28) | (immediate << 20) | 0x7057

        async def bench(ctx: Any) -> None:
            p = dut.ports
            ctx.set(p["reset"], 1)
            await ctx.delay(1e-8)
            self.assertEqual(1, ctx.get(p["io_vtype_illegal"]))
            ctx.set(p["reset"], 0)
            await ctx.delay(1e-8)

            ctx.set(p["io_insts_0_valid"], 1)
            ctx.set(p["io_insts_0_bits"], vset(1, 1, vta=1, vma=1))
            ctx.set(p["io_canUpdateVType"], 1)
            await ctx.tick()
            self.assertEqual(
                (0, 1, 1, 1, 1),
                tuple(ctx.get(p[name]) for name in (
                    "io_vtype_illegal", "io_vtype_vma", "io_vtype_vta",
                    "io_vtype_vsew", "io_vtype_vlmul",
                )),
            )

            ctx.set(p["io_insts_0_valid"], 0)
            ctx.set(p["io_canUpdateVType"], 0)
            ctx.set(p["io_commitVType_vtype_valid"], 1)
            ctx.set(p["io_commitVType_vtype_bits_illegal"], 0)
            ctx.set(p["io_commitVType_vtype_bits_vma"], 0)
            ctx.set(p["io_commitVType_vtype_bits_vta"], 1)
            ctx.set(p["io_commitVType_vtype_bits_vsew"], 3)
            ctx.set(p["io_commitVType_vtype_bits_vlmul"], 2)
            await ctx.tick()
            # Commit updates architectural state; speculative output changes on walk-to-arch.
            self.assertEqual(1, ctx.get(p["io_vtype_vma"]))
            ctx.set(p["io_commitVType_vtype_valid"], 0)
            ctx.set(p["io_walkToArchVType"], 1)
            await ctx.tick()
            self.assertEqual(
                (0, 0, 1, 3, 2),
                tuple(ctx.get(p[name]) for name in (
                    "io_vtype_illegal", "io_vtype_vma", "io_vtype_vta",
                    "io_vtype_vsew", "io_vtype_vlmul",
                )),
            )

            ctx.set(p["io_walkToArchVType"], 0)
            ctx.set(p["io_walkVType_valid"], 1)
            ctx.set(p["io_walkVType_bits_illegal"], 0)
            ctx.set(p["io_walkVType_bits_vma"], 0)
            ctx.set(p["io_walkVType_bits_vta"], 0)
            ctx.set(p["io_walkVType_bits_vsew"], 0)
            ctx.set(p["io_walkVType_bits_vlmul"], 1)
            ctx.set(p["io_commitVType_hasVsetvl"], 1)
            ctx.set(p["io_vsetvlVType_illegal"], 1)
            ctx.set(p["io_vsetvlVType_vma"], 1)
            ctx.set(p["io_vsetvlVType_vta"], 0)
            ctx.set(p["io_vsetvlVType_vsew"], 0)
            ctx.set(p["io_vsetvlVType_vlmul"], 0)
            await ctx.tick()
            self.assertEqual(
                (1, 1, 0, 0, 0),
                tuple(ctx.get(p[name]) for name in (
                    "io_vtype_illegal", "io_vtype_vma", "io_vtype_vta",
                    "io_vtype_vsew", "io_vtype_vlmul",
                )),
            )

            ctx.set(p["io_commitVType_hasVsetvl"], 0)
            ctx.set(p["io_walkVType_valid"], 0)
            ctx.set(p["io_insts_0_valid"], 1)
            ctx.set(p["io_insts_0_bits"], vset(4, 1, vta=1, vma=1, ivli=True, reserved=1))
            ctx.set(p["io_canUpdateVType"], 1)
            await ctx.tick()
            self.assertEqual(
                (1, 0, 0, 0, 0),
                tuple(ctx.get(p[name]) for name in (
                    "io_vtype_illegal", "io_vtype_vma", "io_vtype_vta",
                    "io_vtype_vsew", "io_vtype_vlmul",
                )),
            )

        simulator.add_testbench(bench)
        simulator.run()

    def test_fpdecoder_amaranth_controls(self) -> None:
        module = load_subject()
        self.assertIn("FPDecoder", module.IMPLEMENTED_MEMBERS)
        first = module.build_verilog({"module": "FPDecoder"}, {})
        second = module.build_verilog({"module": "FPDecoder"}, {})
        self.assertEqual(first, second)
        self.assertIn("module FPDecoder", first)

    def test_vialu_decoder_all_opcode_values(self) -> None:
        module = load_subject()
        self.assertIn("VIAluDecoder", module.IMPLEMENTED_MEMBERS)
        dut = module.DecodeControlFamily("VIAluDecoder")
        expected = {opcode: (opcode_value, src_type2, vd_type)
                    for opcode, opcode_value, src_type2, vd_type in module._VI_ALU_SPECS}

        async def bench(ctx: Any) -> None:
            for opcode in range(256):
                ctx.set(dut.ports["io_in_fuOpType"], opcode)
                await ctx.delay(1e-9)
                actual = (
                    ctx.get(dut.ports["io_out_opcode"]),
                    ctx.get(dut.ports["io_out_srcType2"]),
                    ctx.get(dut.ports["io_out_vdType"]),
                )
                self.assertEqual(expected.get(opcode, (0, 0, 0)), actual, opcode)

        simulator = Simulator(dut)
        simulator.add_testbench(bench)
        simulator.run()


if __name__ == "__main__": unittest.main()
