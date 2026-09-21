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

    def test_id_pool_priority_and_release(self) -> None:
        """Exercise every allocation and the locked empty-pool encoder value."""
        module = load_subject()
        subject = module.UtilityResidualFamily("IDPool")

        async def bench(context: Any) -> None:
            context.set(subject.ports["reset"], 1)
            context.set(subject.ports["io_alloc_ready"], 0)
            context.set(subject.ports["io_free_valid"], 0)
            await context.tick("sync")
            context.set(subject.ports["reset"], 0)
            for expected_id in range(8):
                self.assertEqual(context.get(subject.ports["io_alloc_valid"]), 1)
                self.assertEqual(context.get(subject.ports["io_alloc_bits"]), expected_id)
                context.set(subject.ports["io_alloc_ready"], 1)
                await context.tick("sync")
            # The locked priority encoder returns 7 for an empty eight-lane
            # pool, even while alloc.valid is low; this lane is observable.
            self.assertEqual(context.get(subject.ports["io_alloc_valid"]), 0)
            self.assertEqual(context.get(subject.ports["io_alloc_bits"]), 7)
            context.set(subject.ports["io_alloc_ready"], 0)
            context.set(subject.ports["io_free_valid"], 1)
            context.set(subject.ports["io_free_bits"], 3)
            await context.tick("sync")
            self.assertEqual(context.get(subject.ports["io_alloc_valid"]), 1)
            self.assertEqual(context.get(subject.ports["io_alloc_bits"]), 3)

        simulator = Simulator(subject)
        simulator.add_clock(1e-6)
        simulator.add_testbench(bench)
        simulator.run()

    def test_overrideable_queue_variants(self) -> None:
        """Check all payload fields, wraparound, and simultaneous replace/dequeue."""
        module = load_subject()
        for member in ("OverrideableQueue", "OverrideableQueue_1"):
            subject = module.UtilityResidualFamily(member)
            input_fields = tuple(
                name.removeprefix("io_in_bits_")
                for name in subject.ports
                if name.startswith("io_in_bits_")
            )

            async def bench(context: Any, *, fields: tuple[str, ...] = input_fields) -> None:
                context.set(subject.ports["reset"], 1)
                context.set(subject.ports["io_in_valid"], 0)
                context.set(subject.ports["io_out_ready"], 0)
                await context.tick("sync")
                context.set(subject.ports["reset"], 0)
                payloads = [
                    {field: (entry + 1) * (index + 3) for index, field in enumerate(fields)}
                    for entry in range(4)
                ]
                for payload in payloads:
                    context.set(subject.ports["io_in_valid"], 1)
                    for field, value in payload.items():
                        context.set(subject.ports[f"io_in_bits_{field}"], value)
                    await context.tick("sync")
                context.set(subject.ports["io_in_valid"], 0)
                context.set(subject.ports["io_out_ready"], 1)
                for payload in payloads:
                    self.assertEqual(context.get(subject.ports["io_out_valid"]), 1)
                    for field, value in payload.items():
                        output = subject.ports[f"io_out_bits_{field}"]
                        self.assertEqual(context.get(output), value & ((1 << len(output)) - 1))
                    await context.tick("sync")
                self.assertEqual(context.get(subject.ports["io_out_valid"]), 0)
                # A dequeue and enqueue to the same slot in one cycle must
                # retain the new entry (the Chisel write wins over the clear).
                first = {field: 0x51 + index for index, field in enumerate(fields)}
                second = {field: 0xA1 + index for index, field in enumerate(fields)}
                context.set(subject.ports["io_in_valid"], 1)
                context.set(subject.ports["io_out_ready"], 0)
                for field, value in first.items():
                    context.set(subject.ports[f"io_in_bits_{field}"], value)
                await context.tick("sync")
                context.set(subject.ports["io_out_ready"], 1)
                for field, value in second.items():
                    context.set(subject.ports[f"io_in_bits_{field}"], value)
                await context.tick("sync")
                self.assertEqual(context.get(subject.ports["io_out_valid"]), 1)
                for field, value in second.items():
                    output = subject.ports[f"io_out_bits_{field}"]
                    self.assertEqual(context.get(output), value & ((1 << len(output)) - 1))

            simulator = Simulator(subject)
            simulator.add_clock(1e-6)
            simulator.add_testbench(bench)
            simulator.run()

    def test_time_async_capture_edges(self) -> None:
        """Model the three-stage valid synchronizer and edge-triggered capture."""
        module = load_subject()
        subject = module.UtilityResidualFamily("TimeAsync")
        vectors = (
            (0, 0x11), (1, 0x1234), (1, 0x2345), (0, 0x3456),
            (0, 0x4567), (1, 0x5678), (0, 0x6789), (0, 0x789A),
            (1, 0x89AB), (1, 0x9ABC), (0, 0xABCD),
        )

        async def bench(context: Any) -> None:
            context.set(subject.ports["reset"], 1)
            context.set(subject.ports["io_i_time_valid"], 0)
            context.set(subject.ports["io_i_time_bits"], 0)
            await context.tick("sync")
            context.set(subject.ports["reset"], 0)
            stage_0 = stage_1 = stage_2 = delayed = captured = 0
            for valid, value in vectors:
                context.set(subject.ports["io_i_time_valid"], valid)
                context.set(subject.ports["io_i_time_bits"], value)
                if stage_0 ^ delayed:
                    captured = value
                stage_0, stage_1, stage_2, delayed = stage_1, stage_2, valid, stage_0
                await context.tick("sync")
                self.assertEqual(context.get(subject.ports["io_o_time_bits"]), captured)

        simulator = Simulator(subject)
        simulator.add_clock(1e-6)
        simulator.add_testbench(bench)
        simulator.run()

if __name__ == "__main__": unittest.main()
