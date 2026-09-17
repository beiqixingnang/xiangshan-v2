#!/usr/bin/env python3
# Module Contract
"""Reusable direct tests for the UHSC JTAG shifter family.

The file name mirrors ``Build-Cpu.Dependency.Rocket.Jtag-Hardware.py`` so it
can be moved into the main System-Testing tree without a naming translation.
These bounded tests are not locked-reference acceptance evidence.
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
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Dependency.Rocket.Jtag-Hardware.py"


# Load the exact local Build. / 加载本地精确 Build。
def load_subject() -> Any:
    """Load the JTAG aggregate without package imports. / 不依赖包导入加载 JTAG 聚合。"""

    spec = importlib.util.spec_from_file_location("testing_jtag_subject", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_vector(module: Any, member: str, values: dict[str, int]) -> dict[str, int]:
    """Drive one capture/shift vector and return exposed outputs. / 驱动捕获/移位向量并返回公开输出。"""

    dut = module.JtagShifterFamily(member)
    result: dict[str, int] = {}

    def process():
        for name, signal in dut.ports.items():
            if name not in {"clock", "reset"} and name.startswith("io_chainIn_"):
                yield signal.eq(0)
        for name, value in values.items():
            yield dut.ports[name].eq(value)
        yield dut.ports["io_chainIn_capture"].eq(1)
        yield Tick()
        yield Settle()
        result["chain"] = int((yield dut.ports["io_chainOut_data"]))
        yield dut.ports["io_chainIn_capture"].eq(0)
        if "io_chainIn_update" in dut.ports:
            yield dut.ports["io_chainIn_update"].eq(1)
            yield Settle()
        for name in dut.ports:
            if name.startswith("io_update_") or name == "io_capture_capture":
                result[name] = int((yield dut.ports[name]))

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_process(process)
    sim.run()
    return result


# Subject Contract
class JtagShifterContractTest(unittest.TestCase):
    """Check all five locked members and same-name exports. / 检查全部五个锁定成员及同名导出。"""

    def test_all_members_export(self) -> None:
        module = load_subject()
        self.assertEqual(set(module.COVERED_MODULES), set(module.PORT_SPECS))
        for member in module.COVERED_MODULES:
            self.assertIn(f"module {member}", module.build_verilog({"module": member}, {}))


# Behavior Tests
class JtagShifterBehaviorTest(unittest.TestCase):
    """Check capture, update, and bypass boundary behavior. / 检查捕获、更新与旁路边界行为。"""

    def test_bypass_capture_clears_then_shift_loads_tdi(self) -> None:
        module = load_subject()
        dut = module.JtagShifterFamily("JtagBypassChain")
        observed: list[int] = []

        def process():
            yield dut.ports["io_chainIn_capture"].eq(1)
            yield Tick()
            yield Settle()
            observed.append(int((yield dut.ports["io_chainOut_data"])))
            yield dut.ports["io_chainIn_capture"].eq(0)
            yield dut.ports["io_chainIn_shift"].eq(1)
            yield dut.ports["io_chainIn_data"].eq(1)
            yield Tick()
            yield Settle()
            observed.append(int((yield dut.ports["io_chainOut_data"])))

        sim = Simulator(dut)
        sim.add_clock(1e-6)
        sim.add_process(process)
        sim.run()
        self.assertEqual([0, 1], observed)

    def test_capture_chain_places_mfrid_at_chain_lsb(self) -> None:
        module = load_subject()
        result = run_vector(module, "CaptureChain", {
            "io_capture_bits_version": 0xA,
            "io_capture_bits_partNumber": 0x1234,
            "io_capture_bits_mfrId": 0x345,
        })
        self.assertEqual(1, result["chain"])

    def test_dmi_capture_update_preserves_fields(self) -> None:
        module = load_subject()
        result = run_vector(module, "CaptureUpdateChain_1", {
            "io_capture_bits_addr": 0x45,
            "io_capture_bits_data": 0x89ABCDEF,
            "io_capture_bits_resp": 2,
        })
        self.assertEqual(1, result["io_update_valid"])
        self.assertEqual(0x45, result["io_update_bits_addr"])
        self.assertEqual(0x89ABCDEF, result["io_update_bits_data"])
        self.assertEqual(2, result["io_update_bits_op"])


if __name__ == "__main__":
    unittest.main()
