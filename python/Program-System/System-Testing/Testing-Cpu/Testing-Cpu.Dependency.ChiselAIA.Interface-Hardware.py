#!/usr/bin/env python3
"""Bounded System-Testing for TOP-XSTOP-UHSC-IO-005 AIA/IMSIC AXI4.

The test locks the external XSTop port directions and exercises the aggregate
single-beat register boundary.  Full AXI ordering, multi-hart routing, and the
parent XSTop differential remain intentionally pending.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path
from typing import Any, Final

from amaranth.sim import Settle, Simulator, Tick


TEST_ID: Final = "Cpu.Dependency.ChiselAIA.Interface"
SUBJECT_ID: Final = "Cpu.Dependency.ChiselAIA.Interface"
PARENT_CLOSURE: Final = "PENDING_XSTOP_AIA_PARENT"
ROOT: Final = Path(__file__).resolve().parents[4]
TARGET: Final = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Dependency.ChiselAIA.Interface-Hardware.py"

LOCKED_PORTS: Final = (
    ("io_clock", "input", 1), ("io_reset", "input", 1), ("io_extIntrs", "input", 64),
    ("imsic_axi4_awready", "output", 1), ("imsic_axi4_awvalid", "input", 1),
    ("imsic_axi4_awid", "input", 16), ("imsic_axi4_awaddr", "input", 32),
    ("imsic_axi4_awlen", "input", 8), ("imsic_axi4_awsize", "input", 3),
    ("imsic_axi4_awburst", "input", 2), ("imsic_axi4_awlock", "input", 1),
    ("imsic_axi4_awcache", "input", 4), ("imsic_axi4_awprot", "input", 3),
    ("imsic_axi4_awqos", "input", 4), ("imsic_axi4_wready", "output", 1),
    ("imsic_axi4_wvalid", "input", 1), ("imsic_axi4_wdata", "input", 32),
    ("imsic_axi4_wstrb", "input", 4), ("imsic_axi4_wlast", "input", 1),
    ("imsic_axi4_bready", "input", 1), ("imsic_axi4_bvalid", "output", 1),
    ("imsic_axi4_bid", "output", 16), ("imsic_axi4_bresp", "output", 2),
    ("imsic_axi4_arready", "output", 1), ("imsic_axi4_arvalid", "input", 1),
    ("imsic_axi4_arid", "input", 16), ("imsic_axi4_araddr", "input", 32),
    ("imsic_axi4_arlen", "input", 8), ("imsic_axi4_arsize", "input", 3),
    ("imsic_axi4_arburst", "input", 2), ("imsic_axi4_arlock", "input", 1),
    ("imsic_axi4_arcache", "input", 4), ("imsic_axi4_arprot", "input", 3),
    ("imsic_axi4_arqos", "input", 4), ("imsic_axi4_rready", "input", 1),
    ("imsic_axi4_rvalid", "output", 1), ("imsic_axi4_rid", "output", 16),
    ("imsic_axi4_rdata", "output", 32), ("imsic_axi4_rresp", "output", 2),
    ("imsic_axi4_rlast", "output", 1),
)


def load_subject() -> Any:
    spec = importlib.util.spec_from_file_location("testing_chisel_aia_subject", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class AIAInterfaceContractTest(unittest.TestCase):
    def test_identity_and_locked_port_surface(self) -> None:
        self.assertEqual(TEST_ID, SUBJECT_ID)
        module = load_subject()
        dut = module.UHSCAIAImsicAXI4(module.AIAConfig())
        self.assertEqual(tuple(name for name, _, _ in LOCKED_PORTS), tuple(s.name for s in dut.export_ports()))
        dut.elaborate(None)
        rtl = module.build_verilog({"module": "UHSCAIAImsicAXI4"}, {})
        self.assertRegex(rtl, r"\bmodule\s+UHSCAIAImsicAXI4\b")
        for name, direction, width in LOCKED_PORTS:
            self.assertIn(name, rtl)
            expected = "input" if direction == "input" else "output"
            self.assertRegex(rtl, rf"\b{expected}\b[^;]*\b{name}\b")
            if width > 1:
                self.assertIn(f"[{width - 1}:0]", rtl)

    def test_reference_axi_register_vectors(self) -> None:
        module = load_subject()
        idle = module.imsic_axi4_reference_step(0, 0, 2, irq_sources=8)
        self.assertEqual({"pending": 2, "enable": 0, "interrupt": 0},
                         {k: idle[k] for k in ("pending", "enable", "interrupt")})
        enabled = module.imsic_axi4_reference_step(2, 0, 0, write_word=0, write_data=2, irq_sources=8)
        self.assertEqual(1, enabled["interrupt"])
        claimed = module.imsic_axi4_reference_step(2, 2, 0, write_word=4, write_data=2, irq_sources=8)
        self.assertEqual(0, claimed["pending"])
        completed = module.imsic_axi4_reference_step(0, 2, 0, write_word=5, write_data=2, irq_sources=8)
        self.assertEqual(2, completed["pending"])

    def test_single_beat_axi_write_and_external_source(self) -> None:
        module = load_subject()
        dut = module.UHSCAIAImsicAXI4(module.AIAConfig(irq_sources=8))
        observed: list[tuple[int, int, int]] = []

        def process():
            yield dut.io_reset.eq(1)
            yield Tick("aia_axi")
            yield dut.io_reset.eq(0)
            yield dut.io_extIntrs.eq(2)
            yield Tick("aia_axi")
            yield Settle()
            observed.append((int((yield dut.imsic_pending)), int((yield dut.imsic_axi4_awready)), int((yield dut.imsic_axi4_wready))))
            yield dut.io_extIntrs.eq(0)
            yield dut.imsic_axi4_awaddr.eq(0)
            yield dut.imsic_axi4_awid.eq(7)
            yield dut.imsic_axi4_awvalid.eq(1)
            yield dut.imsic_axi4_wdata.eq(2)
            yield dut.imsic_axi4_wvalid.eq(1)
            yield Tick("aia_axi")
            yield Settle()
            yield dut.imsic_axi4_awvalid.eq(0)
            yield dut.imsic_axi4_wvalid.eq(0)
            yield dut.imsic_axi4_bready.eq(1)
            yield Tick("aia_axi")
            yield Settle()
            observed.append((int((yield dut.imsic_enable)), int((yield dut.imsic_axi4_bid)), int((yield dut.imsic_axi4_bresp))))

        sim = Simulator(dut)
        sim.add_clock(1e-6, domain="aia_axi")
        sim.add_process(process)
        sim.run()
        self.assertEqual((2, 1, 1), observed[0])
        self.assertEqual((2, 7, 0), observed[1])


if __name__ == "__main__":
    unittest.main()
