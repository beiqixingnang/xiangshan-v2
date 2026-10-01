"""Bounded direct tests for the DCache miss/queue family."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
import sys

from amaranth.sim import Settle, Simulator, Tick

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Cpu-Memory-Memory.Dcache.MissQueue.Family-Hardware.py"


def load_subject():
    """Load the exact family Build path."""

    spec = importlib.util.spec_from_file_location("testing_dcache_miss_family", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class DcacheMissQueueFamilyTest(unittest.TestCase):
    """Check all exports and bounded ready/valid transaction behavior."""

    def test_all_members_export(self) -> None:
        module = load_subject()
        self.assertEqual(7, len(module.COVERED_MODULES))
        for member in module.COVERED_MODULES:
            self.assertIn(f"module {member}", module.build_verilog({"module": member}, {}))
        self.assertEqual(
            {
                "CMOUnit",
                "MissEntry",
                "MissReadyGen",
                "ProbeEntry",
                "TreeArbiter",
                "WritebackEntry_15",
            },
            set(module.CONTRACT_ONLY_MEMBERS),
        )

    def test_probe_entry_round_trip(self) -> None:
        module = load_subject()
        dut = module.DcacheMissQueueFamily("ProbeEntry")
        observed: list[tuple[int, int]] = []

        def process():
            yield dut.ports["io_req_valid"].eq(1)
            yield dut.ports["io_req_bits_addr"].eq(0x1234)
            yield dut.ports["io_req_bits_vaddr"].eq(0x2234)
            yield dut.ports["io_req_bits_param"].eq(1)
            yield dut.ports["io_req_bits_needData"].eq(1)
            yield Tick()
            yield dut.ports["io_req_valid"].eq(0)
            yield dut.ports["io_pipe_req_ready"].eq(1)
            yield Tick()
            yield dut.ports["io_pipe_req_ready"].eq(0)
            yield dut.ports["io_pipe_resp_valid"].eq(1)
            yield dut.ports["io_pipe_resp_bits_id"].eq(0)
            yield Settle()
            observed.append((int((yield dut.ports["io_block_addr_valid"])), int((yield dut.ports["io_block_addr_bits"]))))

        sim = Simulator(dut)
        sim.add_clock(1e-6)
        sim.add_process(process)
        sim.run()
        self.assertEqual([(1, 0x1234)], observed)

    def test_probe_entry_lrsc_blocking_is_delayed_and_block_granular(self) -> None:
        module = load_subject()
        req_addr = 0x1234

        cases = (
            ("no reservation", 0, 0x1237, (1,)),
            ("same 64-byte block", 1, 0x1237, (0, 0, 1)),
            ("different 64-byte block", 1, 0x1274, (1,)),
        )
        for label, locked_valid, locked_addr, expected in cases:
            with self.subTest(case=label):
                dut = module.DcacheMissQueueFamily("ProbeEntry")
                observed: list[int] = []

                def process():
                    yield dut.ports["io_req_valid"].eq(1)
                    yield dut.ports["io_req_bits_addr"].eq(req_addr)
                    yield dut.ports["io_lrsc_locked_block_valid"].eq(locked_valid)
                    yield dut.ports["io_lrsc_locked_block_bits"].eq(locked_addr)
                    yield dut.ports["io_pipe_req_ready"].eq(0)
                    yield Tick()
                    yield dut.ports["io_req_valid"].eq(0)
                    yield Settle()
                    observed.append(int((yield dut.ports["io_pipe_req_valid"])))
                    if locked_valid and (locked_addr >> 6) == (req_addr >> 6):
                        yield dut.ports["io_lrsc_locked_block_valid"].eq(0)
                        yield Settle()
                        observed.append(int((yield dut.ports["io_pipe_req_valid"])))
                        yield Tick()
                        yield Settle()
                        observed.append(int((yield dut.ports["io_pipe_req_valid"])))

                sim = Simulator(dut)
                sim.add_clock(1e-6)
                sim.add_process(process)
                sim.run()
                self.assertEqual(expected, tuple(observed))

    def test_writeback_entry_probe_ack_streams_two_beats(self) -> None:
        """A dirty ProbeAck emits low then high 256-bit beats and frees."""

        module = load_subject()
        dut = module.DcacheMissQueueFamily("WritebackEntry")
        low = int("0123456789abcdef" * 4, 16)
        high = int("fedcba9876543210" * 4, 16)
        payload = low | (high << 256)
        observed: list[tuple[int, int, int, int, int, int]] = []

        def process():
            yield dut.ports["reset"].eq(1)
            yield Tick()
            yield dut.ports["reset"].eq(0)
            yield dut.ports["io_id"].eq(3)
            yield dut.ports["io_req_valid"].eq(1)
            yield dut.ports["io_primary_valid"].eq(1)
            yield dut.ports["io_req_bits_param"].eq(5)
            yield dut.ports["io_req_bits_voluntary"].eq(0)
            yield dut.ports["io_req_bits_hasData"].eq(1)
            yield dut.ports["io_req_bits_corrupt"].eq(1)
            yield dut.ports["io_req_bits_dirty"].eq(1)
            yield dut.ports["io_req_bits_addr"].eq(0x123456789ABC)
            yield dut.ports["io_req_data_data"].eq(payload)
            yield dut.ports["io_mem_release_ready"].eq(0)
            yield Tick()
            yield dut.ports["io_req_valid"].eq(0)
            yield dut.ports["io_primary_valid"].eq(0)
            yield dut.ports["io_mem_release_ready"].eq(1)
            # The locked data path intentionally inserts one cycle before the
            # first release beat is visible.
            yield Settle()
            self.assertEqual(0, (yield dut.ports["io_mem_release_valid"]))
            yield Tick()
            yield Settle()
            observed.append(
                (
                    int((yield dut.ports["io_mem_release_valid"])),
                    int((yield dut.ports["io_mem_release_bits_opcode"])),
                    int((yield dut.ports["io_mem_release_bits_param"])),
                    int((yield dut.ports["io_mem_release_bits_source"])),
                    int((yield dut.ports["io_mem_release_bits_address"])),
                    int((yield dut.ports["io_mem_release_bits_data"])),
                )
            )
            yield Tick()
            yield Settle()
            observed.append(
                (
                    int((yield dut.ports["io_mem_release_valid"])),
                    int((yield dut.ports["io_mem_release_bits_opcode"])),
                    int((yield dut.ports["io_mem_release_bits_param"])),
                    int((yield dut.ports["io_mem_release_bits_source"])),
                    int((yield dut.ports["io_mem_release_bits_address"])),
                    int((yield dut.ports["io_mem_release_bits_data"])),
                )
            )
            yield Tick()
            yield Settle()
            self.assertEqual(0, (yield dut.ports["io_mem_release_valid"]))
            self.assertEqual(1, (yield dut.ports["io_primary_ready"]))
            self.assertEqual(0, (yield dut.ports["io_block_addr_valid"]))

        sim = Simulator(dut)
        sim.add_clock(1e-6)
        sim.add_process(process)
        sim.run()
        self.assertEqual(
            [
                (1, 5, 5, 3, 0x123456789ABC, low),
                (1, 5, 5, 3, 0x123456789ABC, high),
            ],
            observed,
        )

    def test_writeback_entry_voluntary_release_waits_for_grant(self) -> None:
        """A no-data voluntary release waits in response state for grant."""

        module = load_subject()
        dut = module.DcacheMissQueueFamily("WritebackEntry")
        observed: list[tuple[int, int, int, int]] = []

        def process():
            yield dut.ports["reset"].eq(1)
            yield Tick()
            yield dut.ports["reset"].eq(0)
            yield dut.ports["io_id"].eq(17)
            yield dut.ports["io_req_valid"].eq(1)
            yield dut.ports["io_primary_valid"].eq(1)
            yield dut.ports["io_req_bits_param"].eq(2)
            yield dut.ports["io_req_bits_voluntary"].eq(1)
            yield dut.ports["io_req_bits_hasData"].eq(0)
            yield dut.ports["io_req_bits_addr"].eq(0x4000)
            yield Tick()
            yield dut.ports["io_req_valid"].eq(0)
            yield dut.ports["io_primary_valid"].eq(0)
            yield dut.ports["io_mem_release_ready"].eq(1)
            yield Tick()
            yield Settle()
            observed.append(
                (
                    int((yield dut.ports["io_mem_release_valid"])),
                    int((yield dut.ports["io_mem_release_bits_opcode"])),
                    int((yield dut.ports["io_mem_release_bits_data"])),
                    int((yield dut.ports["io_block_addr_valid"])),
                )
            )
            yield Tick()
            yield Settle()
            self.assertEqual(0, (yield dut.ports["io_mem_release_valid"]))
            self.assertEqual(0, (yield dut.ports["io_primary_ready"]))
            self.assertEqual(1, (yield dut.ports["io_block_addr_valid"]))
            yield dut.ports["io_mem_grant_valid"].eq(1)
            yield Tick()
            yield Settle()
            self.assertEqual(1, (yield dut.ports["io_primary_ready"]))
            self.assertEqual(0, (yield dut.ports["io_block_addr_valid"]))

        sim = Simulator(dut)
        sim.add_clock(1e-6)
        sim.add_process(process)
        sim.run()
        self.assertEqual([(1, 6, 0, 1)], observed)


if __name__ == "__main__":
    unittest.main()
