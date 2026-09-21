"""Reusable bounded tests for the utility/protocol residual family."""
from __future__ import annotations
import importlib.util
import random
import sys
import unittest
from pathlib import Path
from typing import Any
from amaranth.sim import Delay, Simulator
ROOT = Path(__file__).resolve().parents[4]; TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Dependency.Utility.ResidualFamily-Hardware.py"
def load_subject() -> Any:
    spec = importlib.util.spec_from_file_location("testing_util_res", TARGET)
    if spec is None or spec.loader is None: raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); return module
class UtilityResidualFamilyTest(unittest.TestCase):
    def test_all_members_export(self) -> None:
        module = load_subject()
        for member in module.COVERED_MODULES: self.assertIn(f"module {member}", module.build_verilog({"module": member}, {}))

    def test_csa_pipeline_vectors(self) -> None:
        module = load_subject()
        subject = module.UtilityResidualFamily("CSA_Nto2With3to2MainPipeline")
        rng = random.Random(0xC5A27)
        mask = (1 << 107) - 1
        vectors = [[rng.getrandbits(107) for _ in range(27)] for _ in range(24)]

        def csa3(a: int, b: int, c: int) -> tuple[int, int]:
            return (a ^ b ^ c) & mask, (((a & b) | (a & c) | (b & c)) << 1) & mask

        def csa4(a: int, b: int, c: int, d: int) -> tuple[int, int]:
            cout = [((c >> index) & 1) if ((a ^ b) >> index) & 1 else ((a >> index) & 1) for index in range(107)]
            raw_sum: list[int] = []
            raw_carry: list[int] = []
            for index in range(107):
                prior = 0 if index == 0 else cout[index - 1]
                parity = ((a ^ b ^ c ^ d) >> index) & 1
                raw_sum.append(parity ^ prior)
                raw_carry.append(prior if parity else ((d >> index) & 1))
            sums = [raw_sum[0]] + [raw_carry[index - 1] if index % 2 else raw_sum[index] for index in range(1, 107)]
            carries = [0] + [raw_sum[index] if index % 2 else raw_carry[index - 1] for index in range(1, 107)]
            return sum(bit << index for index, bit in enumerate(sums)), sum(bit << index for index, bit in enumerate(carries))

        def reduce_values(values: list[int]) -> tuple[int, int]:
            while len(values) > 2:
                reduced: list[int] = []
                if len(values) in (4, 8):
                    for base in range(0, len(values), 4): reduced.extend(csa4(*values[base:base + 4]))
                else:
                    complete = len(values) // 3
                    for group in range(complete): reduced.extend(csa3(*values[group * 3:group * 3 + 3]))
                    reduced.extend(values[complete * 3:])
                values = reduced
            return values[0], values[1]

        async def bench(context: Any) -> None:
            context.set(subject.ports["io_fire"], 1)
            for values in vectors:
                for index, value in enumerate(values): context.set(subject.ports[f"io_in_{index}"], value)
                await context.tick("sync")
                expected_sum, expected_carry = reduce_values(values)
                self.assertEqual(context.get(subject.ports["io_out_sum"]), expected_sum)
                self.assertEqual(context.get(subject.ports["io_out_car"]), expected_carry)

        simulator = Simulator(subject)
        simulator.add_clock(1e-6)
        simulator.add_testbench(bench)
        simulator.run()

    def test_skid_buffer_hold_and_flush(self) -> None:
        module = load_subject()
        subject = module.UtilityResidualFamily("skidBufferConnect")
        checked = ("flowMask", "data", "baseAddr", "uopAddr", "stride", "flowNum")
        values = {field: (index + 1) * 0x12345 for index, field in enumerate(checked)}

        async def bench(context: Any) -> None:
            context.set(subject.ports["reset"], 1)
            await context.tick()
            context.set(subject.ports["reset"], 0)
            context.set(subject.ports["io_in_valid"], 1)
            context.set(subject.ports["io_out_ready"], 0)
            for field, value in values.items(): context.set(subject.ports[f"io_in_bits_{field}"], value)
            await context.tick()
            self.assertEqual(context.get(subject.ports["io_in_ready"]), 0)
            self.assertEqual(context.get(subject.ports["io_out_valid"]), 1)
            context.set(subject.ports["io_in_valid"], 0)
            for field in checked: self.assertEqual(context.get(subject.ports[f"io_out_bits_{field}"]), values[field] & ((1 << len(subject.ports[f"io_out_bits_{field}"])) - 1))
            context.set(subject.ports["io_flush"], 1)
            await context.tick()
            self.assertEqual(context.get(subject.ports["io_in_ready"]), 1)
            self.assertEqual(context.get(subject.ports["io_out_valid"]), 0)

        simulator = Simulator(subject)
        simulator.add_clock(1e-6)
        simulator.add_testbench(bench)
        simulator.run()

    def test_jtag_tap_reset_and_instruction_capture(self) -> None:
        module = load_subject()
        subject = module.UtilityResidualFamily("JtagTapController")

        async def bench(context: Any) -> None:
            context.set(subject.ports["io_control_jtag_reset"], 1)
            await context.tick("tap")
            self.assertEqual(context.get(subject.ports["io_output_instruction"]), 1)
            self.assertEqual(context.get(subject.ports["io_output_tapIsInTestLogicReset"]), 1)
            context.set(subject.ports["io_control_jtag_reset"], 0)
            for tms in (0, 1, 1, 0, 0):
                context.set(subject.ports["io_jtag_TMS"], tms)
                await context.tick("tap")
            self.assertEqual(context.get(subject.ports["io_dataChainOut_shift"]), 0)
            await context.tick("tap_fall")
            self.assertEqual(context.get(subject.ports["io_jtag_TDO_driven"]), 1)

        simulator = Simulator(subject)
        simulator.add_clock(1e-6, domain="tap")
        simulator.add_clock(1e-6, domain="shift")
        simulator.add_clock(1e-6, domain="tap_fall", phase=0.5e-6)
        simulator.add_testbench(bench)
        simulator.run()

    def test_clock_gate_latch_equation(self) -> None:
        module = load_subject()
        rtl = module.build_verilog({"module": "ClockGate"}, {})
        self.assertIn("$dlatch", rtl)
        self.assertIn("assign Q = CK & enable_latch", rtl)
        enable = 0
        sequence = ((0, 1, 0), (1, 1, 0), (0, 0, 0), (1, 0, 0))
        expected_q = []
        for ck, te, e in sequence:
            if not ck:
                enable = te | e
            expected_q.append(ck & enable)
        self.assertEqual(expected_q, [0, 1, 0, 0])
if __name__ == "__main__": unittest.main()
