"""Direct bounded tests for the NewCSR control/trap family.

直接有界测试 NewCSR 控制/陷阱 family 的同名导出与端口覆盖。
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any

from amaranth.sim import Simulator

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Cpu-Core-Backend.Fu.NewCSR.ControlFamily-Hardware.py"


def load_subject() -> Any:
    """Load the exact Build path. / 加载精确 Build 路径。"""

    spec = importlib.util.spec_from_file_location("testing_newcsr_control_family", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class NewCSRControlFamilyTest(unittest.TestCase):
    """Check all nine locked family members export by their own name."""

    def test_all_members_export(self) -> None:
        module = load_subject()
        for member in module.COVERED_MODULES:
            rtl = module.build_verilog({"module": member}, {})
            self.assertIn(f"module {member}", rtl)

    def test_deterministic_exports(self) -> None:
        module = load_subject()
        for member in module.COVERED_MODULES:
            self.assertEqual(module.build_verilog({"module": member}, {}),
                             module.build_verilog({"module": member}, {}))

    def test_trap_inst_csr_encoding(self) -> None:
        module = load_subject()
        subject = module.ControlFamily("TrapInstMod")
        csr_addr, rs1, rd, funct3 = 0xC00, 3, 5, 2
        csr_uop_imm = csr_addr | (rs1 << 12) | (rd << 17)
        expected = (csr_addr << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | 0x73

        async def bench(context: Any) -> None:
            for name, direction, _width in subject.specs:
                if direction == "input" and name != "clock":
                    context.set(subject.ports[name], 0)
            context.set(subject.ports["reset"], 1)
            await context.tick()
            context.set(subject.ports["reset"], 0)
            context.set(subject.ports["io_faultCsrUop_valid"], 1)
            context.set(subject.ports["io_faultCsrUop_bits_imm"], csr_uop_imm)
            context.set(subject.ports["io_faultCsrUop_bits_fuOpType"], funct3)
            await context.tick()
            await context.delay(1e-9)
            self.assertEqual(context.get(subject.ports["io_currentTrapInst_valid"]), 1)
            self.assertEqual(context.get(subject.ports["io_currentTrapInst_bits"]), expected)

        simulator = Simulator(subject)
        simulator.add_clock(1e-6)
        simulator.add_testbench(bench)
        simulator.run()


if __name__ == "__main__":
    unittest.main()
