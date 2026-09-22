#!/usr/bin/env python3
"""Direct tests for the UHSC V2 instruction-cache utility family.

The subject aggregates the four locked utility boundaries emitted by the V2
snapshot: two demultiplexer widths, the ten-way acquire mux, and the
stateful FIFO.  These tests are intentionally local to the Build contract:
they verify exact-path loading, deterministic same-name exports, and a small
set of observable handshake/state transitions.  Locked-reference equivalence
remains owned by the validation rail and is not claimed by this direct test.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest
from typing import Any

from amaranth.sim import Settle, Simulator, Tick


# Fixtures And Support
ROOT = Path(__file__).resolve().parents[4]
TARGET = (
    ROOT
    / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Build-Cpu.Frontend.Icache.Utils-Hardware.py"
)


def load_subject() -> Any:
    """Load the exact Build file without package discovery. / 按精确路径加载 Build。"""

    spec = importlib.util.spec_from_file_location("testing_icache_utils", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Subject Contract
class ICacheUtilsContractTest(unittest.TestCase):
    """Check all four exact members and deterministic same-name exports. / 检查四个成员。"""

    def test_catalog_is_exact(self) -> None:
        module = load_subject()
        self.assertEqual(
            ("DeMultiplexer", "DeMultiplexer_1", "MuxBundle", "FIFOReg"),
            module.COVERED_MODULES,
        )

    def test_each_member_exports_deterministically(self) -> None:
        module = load_subject()
        for member in module.COVERED_MODULES:
            first = module.build_verilog({"module": member}, {})
            second = module.build_verilog({"module": member}, {})
            self.assertEqual(first, second, member)
            self.assertIn(f"module {member}", first, member)


# Behavior Tests
class ICacheUtilsBehaviorTest(unittest.TestCase):
    """Exercise demux, mux, FIFO observation, and one state transition. / 检查基本行为。"""

    def test_demultiplexer_variants_route_payload_and_choose_ready(self) -> None:
        module = load_subject()
        for n, expose_chosen in ((4, False), (10, True)):
            dut = module._LockedDeMultiplexer(n, expose_chosen)
            observed: dict[str, int] = {}

            def process():
                yield dut.in_valid.eq(1)
                yield dut.in_blk_paddr.eq(0x12345)
                yield dut.in_vset_idx.eq(0x5A)
                for index, signal in enumerate(dut.out_ready):
                    yield signal.eq(int(index == 2))
                yield Settle()
                observed["ready"] = int((yield dut.in_ready))
                observed["valid0"] = int((yield dut.out_valid[0]))
                observed["valid1"] = int((yield dut.out_valid[1]))
                observed["valid2"] = int((yield dut.out_valid[2]))
                observed["paddr2"] = int((yield dut.out_blk_paddr[2]))
                observed["vset2"] = int((yield dut.out_vset_idx[2]))
                if dut.chosen is not None:
                    observed["chosen"] = int((yield dut.chosen))

            sim = Simulator(dut)
            sim.add_process(process)
            sim.run()
            self.assertEqual(1, observed["ready"])
            self.assertEqual(1, observed["valid0"])
            self.assertEqual(1, observed["valid1"])
            self.assertEqual(1, observed["valid2"])
            self.assertEqual(0x12345, observed["paddr2"])
            self.assertEqual(0x5A, observed["vset2"])
            if expose_chosen:
                self.assertEqual(2, observed["chosen"])

    def test_mux_bundle_selects_input_and_gates_ready(self) -> None:
        module = load_subject()
        dut = module._LockedMuxBundle()
        observed: dict[str, int] = {}

        def process():
            yield dut.sel.eq(3)
            yield dut.out_ready.eq(1)
            for index in range(10):
                yield dut.in_valid[index].eq(int(index == 3))
                yield dut.in_address[index].eq(0x1000 + index)
                yield dut.in_vset_idx[index].eq(index + 1)
            yield Settle()
            observed["valid"] = int((yield dut.out_valid))
            observed["source"] = int((yield dut.out_source))
            observed["address"] = int((yield dut.out_address))
            observed["vset"] = int((yield dut.out_vset_idx))
            observed["ready3"] = int((yield dut.in_ready[3]))
            observed["ready2"] = int((yield dut.in_ready[2]))

        sim = Simulator(dut)
        sim.add_process(process)
        sim.run()
        self.assertEqual(1, observed["valid"])
        self.assertEqual(7, observed["source"])
        self.assertEqual(0x1003, observed["address"])
        self.assertEqual(4, observed["vset"])
        self.assertEqual(1, observed["ready3"])
        self.assertEqual(0, observed["ready2"])

    def test_fifo_observation_and_registered_payload(self) -> None:
        module = load_subject()
        self.assertEqual(
            {
                "enq_ready": 1,
                "deq_valid": 0,
                "enq_fire": 1,
                "deq_fire": 0,
                "next_occupancy": 1,
            },
            module.fifo_observation(0, 2, True, False),
        )
        self.assertEqual(
            {
                "enq_ready": 1,
                "deq_valid": 1,
                "enq_fire": 1,
                "deq_fire": 1,
                "next_occupancy": 1,
            },
            module.fifo_observation(1, 2, True, True, pipe=True),
        )

        dut = module.FIFOReg(bits_width=4, entries=2, has_flush=True)
        observed: list[tuple[int, int, int]] = []

        def process():
            yield dut.reset.eq(1)
            yield Tick()
            yield dut.reset.eq(0)
            yield dut.enq_bits.eq(0xA)
            yield dut.enq_valid.eq(1)
            yield Settle()
            observed.append((int((yield dut.enq_ready)), int((yield dut.deq_valid)), int((yield dut.deq_bits))))
            yield Tick()
            yield dut.enq_valid.eq(0)
            yield Settle()
            observed.append((int((yield dut.enq_ready)), int((yield dut.deq_valid)), int((yield dut.deq_bits))))
            yield dut.deq_ready.eq(1)
            yield Tick()
            yield Settle()
            observed.append((int((yield dut.enq_ready)), int((yield dut.deq_valid)), int((yield dut.deq_bits))))

        sim = Simulator(dut)
        sim.add_clock(1e-6)
        sim.add_process(process)
        sim.run()
        self.assertEqual((1, 0, 0), observed[0])
        self.assertEqual((1, 1, 0xA), observed[1])
        self.assertEqual((1, 0, 0), observed[2])


if __name__ == "__main__":
    unittest.main()
