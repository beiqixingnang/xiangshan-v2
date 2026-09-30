"""Reusable bounded tests for the UHSC V2 ICache/prefetch family."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any

from amaranth.sim import Settle, Simulator, Tick

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Cpu-Core-Frontend.Icache.Prefetch.Family-Hardware.py"


def load_subject() -> Any:
    spec = importlib.util.spec_from_file_location("testing_icache_prefetch", TARGET)
    if spec is None or spec.loader is None: raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); return module


class IcachePrefetchFamilyTest(unittest.TestCase):
    def test_all_members_export(self) -> None:
        module = load_subject()
        for member in module.COVERED_MODULES: self.assertIn(f"module {member}", module.build_verilog({"module": member}, {}))

    def test_l2tlb_miss_queue_fifo_and_flush(self) -> None:
        module = load_subject()
        dut = module.IcachePrefetchFamily("L2TlbMissQueue")
        observed: list[tuple[int, int, int, int]] = []

        def process():
            yield dut.ports["reset"].eq(1)
            yield Tick()
            yield dut.ports["reset"].eq(0)
            yield dut.ports["io_out_ready"].eq(0)
            for vpn, s2xlate, source, is_llptw in ((11, 1, 2, 0), (22, 2, 1, 1), (33, 3, 0, 0)):
                yield dut.ports["io_in_valid"].eq(1)
                yield dut.ports["io_in_bits_req_info_vpn"].eq(vpn)
                yield dut.ports["io_in_bits_req_info_s2xlate"].eq(s2xlate)
                yield dut.ports["io_in_bits_req_info_source"].eq(source)
                yield dut.ports["io_in_bits_isLLptw"].eq(is_llptw)
                yield Tick()
            yield dut.ports["io_in_valid"].eq(0)
            yield Settle()
            for expected in ((11, 1, 2, 0), (22, 2, 1, 1), (33, 3, 0, 0)):
                observed.append((
                    int((yield dut.ports["io_out_bits_req_info_vpn"])),
                    int((yield dut.ports["io_out_bits_req_info_s2xlate"])),
                    int((yield dut.ports["io_out_bits_req_info_source"])),
                    int((yield dut.ports["io_out_bits_isLLptw"])),
                ))
                self.assertEqual(expected, observed[-1])
                yield dut.ports["io_out_ready"].eq(1)
                yield Tick()
                yield dut.ports["io_out_ready"].eq(0)
                yield Settle()
            self.assertEqual(0, int((yield dut.ports["io_out_valid"])))

            yield dut.ports["io_in_valid"].eq(1)
            yield dut.ports["io_in_bits_req_info_vpn"].eq(99)
            yield Tick()
            yield dut.ports["io_in_valid"].eq(0)
            yield dut.ports["io_sfence_valid"].eq(1)
            yield Tick()
            yield dut.ports["io_sfence_valid"].eq(0)
            yield Settle()
            self.assertEqual(0, int((yield dut.ports["io_out_valid"])))

        sim = Simulator(dut)
        sim.add_clock(1e-6)
        sim.add_process(process)
        sim.run()


if __name__ == "__main__": unittest.main()
