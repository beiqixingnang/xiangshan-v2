#!/usr/bin/env python3
"""Bounded System-Testing contract for TOP-XSTILE-INTBUFFER-004.
TOP-XSTILE-INTBUFFER-004 的有界系统测试契约。
"""
from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
import unittest
from pathlib import Path
from typing import Any, Final

from amaranth.sim import Settle, Simulator, Tick

# Module Contract / 模块契约
TEST_ID: Final = "Cpu.Top.XSTile.IntBuffer.Family"
SUBJECT_TYPE: Final = "build"
SUBJECT_ID: Final = "Cpu.Top.XSTile.IntBuffer.Family"
DIRECT: Final = True
MEMBERS: Final = ("IntBuffer", "IntBuffer_1", "IntBuffer_2")
PORT_COUNTS: Final = (4, 6, 6)
PARENT_CLOSURE: Final = "PENDING"

# Fixtures And Support / 测试夹具与辅助
TARGET: Final = Path(__file__).resolve().parents[3] / "Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Top.XSTile.IntBuffer.Family-Hardware.py"

# Load the exact Build subject / 装载精确 Build 主体
def load_subject() -> Any:
    spec = importlib.util.spec_from_file_location("testing_top_xstile_intbuffer_subject", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Subject Contract / 主体契约
class BuildSubjectContractTest(unittest.TestCase):
    # Verify the exact subject identity / 验证精确主体身份
    def test_subject_contract(self) -> None:
        self.assertEqual(SUBJECT_ID, TEST_ID)


# Behavior Tests / 行为测试
class IntBufferFamilyContractTest(unittest.TestCase):
    # Load the exact local Build subject / 装载精确的本地 Build 主体
    def setUp(self) -> None:
        self.module = load_subject()

    # Verify the locked catalog and reordered lane order / 验证锁定目录及重排通道顺序
    def test_catalog_is_locked_and_reordered_variant_preserved(self) -> None:
        self.assertEqual(MEMBERS, tuple(self.module.COVERED_MODULES))
        self.assertEqual(PORT_COUNTS, tuple(len(self.module.PORT_SPECS[name]) for name in MEMBERS))
        self.assertEqual(
            ("auto_in_1_0", "auto_in_0_0", "auto_out_1_0", "auto_out_0_0"),
            tuple(port.name for port in self.module.PORT_SPECS["IntBuffer_2"][2:]),
        )
        for name in MEMBERS:
            for port in self.module.PORT_SPECS[name]:
                self.assertIn(port.direction, ("input", "output"))
                self.assertEqual(port.width, 1)

    # Verify deterministic Verilog exports / 验证确定性的 Verilog 导出
    def test_each_member_exports_non_empty_deterministic_verilog(self) -> None:
        for name in MEMBERS:
            with self.subTest(member=name):
                first = self.module.build_verilog({"module": name}, {})
                second = self.module.build_verilog({"module": name}, {})
                self.assertEqual(first, second)
                self.assertGreater(len(first), 100)
                self.assertRegex(first, rf"\bmodule\s+{re.escape(name)}\b")
                self.assertNotEqual(hashlib.sha256(first.encode()).hexdigest(), "0" * 64)

    # Verify reset and one-cycle lane transfer / 验证复位及单周期通道传输
    def test_direct_one_stage_async_reset_for_all_members(self) -> None:
        for member in MEMBERS:
            with self.subTest(member=member):
                dut = self.module.IntBufferFamily(member)
                inputs = list(dut.input_names)
                outputs = list(dut.output_names)

                # Drive reset, then one vector and inspect outputs / 驱动复位及一个向量并检查输出
                def process():
                    yield dut.ports["reset"].eq(1)
                    yield Settle()
                    for output in outputs:
                        self.assertEqual((yield dut.ports[output]), 0)
                    yield dut.ports["reset"].eq(0)
                    vector = [index & 1 for index in range(len(inputs))]
                    for name, value in zip(inputs, vector):
                        yield dut.ports[name].eq(value)
                    yield Tick()
                    yield Settle()
                    for name, value in zip(outputs, vector):
                        self.assertEqual((yield dut.ports[name]), value)

                simulator = Simulator(dut)
                simulator.add_clock(1e-6)
                simulator.add_process(process)
                simulator.run()

    # Verify unknown members are rejected / 验证未知成员被拒绝
    def test_public_adapter_rejects_unknown_member(self) -> None:
        with self.assertRaises(ValueError):
            self.module.build_verilog({"module": "NotAnIntBuffer"}, {})


if __name__ == "__main__":
    unittest.main()
