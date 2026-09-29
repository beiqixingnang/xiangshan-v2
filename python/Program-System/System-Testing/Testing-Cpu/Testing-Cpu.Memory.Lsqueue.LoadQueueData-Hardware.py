#!/usr/bin/env python3
# Module Contract
"""Direct behavior tests for UHSC V2 load-queue data arrays."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Any
import unittest

from amaranth.sim import Settle, Simulator, Tick

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Memory.Lsqueue.LoadQueueData-Hardware.py"


# Load the exact Build. / 加载精确 Build。
# Load the exact local Build file for direct testing. / 为直接测试加载精确的本地 Build 文件。
def load_subject() -> Any:
    """Load the load-queue aggregate. / 加载加载队列聚合。"""

    spec = importlib.util.spec_from_file_location("testing_lq_data", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); return module


# Drive every public data input inactive. / 将所有公开数据输入驱动为非活动状态。
def idle_inputs(dut: Any):
    """Drive every public data input inactive. / 将所有公开数据输入置为非活动。"""

    for name, direction, _width in dut.specs:
        if direction == "input" and name not in {"clock", "reset"}:
            yield dut.ports[name].eq(0)


class LoadQueueDataTest(unittest.TestCase):
    """Check exports, banked writes, registered reads, and public CAMs. / 检查导出、分 bank 写、寄存读取和公开 CAM。"""

    # Check that each supported member exports under its public name. / 检查每个受支持成员都按公开名称导出。
    def test_all_members_export(self) -> None:
        """Every selected member exports under its exact public name. / 每个成员按精确公开名称导出。"""

        module = load_subject()
        for member in module.COVERED_MODULES:
            self.assertIn(f"module {member}", module.build_verilog({"module": member}, {}))

    # Check delayed masked writes and same-address Mux1H OR behavior. / 检查延迟掩码写及同地址 Mux1H 或行为。
    def test_delayed_mask_write_and_mux1h_same_address_or(self) -> None:
        """Delayed bank writes retain valid data and OR simultaneous Mux1H selections. / 延迟 bank 写保持有效数据并对并发 Mux1H 选择按位或。"""

        module = load_subject()
        dut = module.LoadQueueDataFamily("LqMaskModule")
        observations: list[int] = []

        def process():
            yield from idle_inputs(dut)
            yield dut.ports["io_wen_0"].eq(1)
            yield dut.ports["io_waddr_0"].eq(31)
            yield dut.ports["io_wdata_0"].eq(0x10)
            yield dut.ports["io_wen_1"].eq(1)
            yield dut.ports["io_waddr_1"].eq(31)
            yield dut.ports["io_wdata_1"].eq(0x04)
            yield Tick()
            yield dut.ports["io_wen_0"].eq(0)
            yield dut.ports["io_wen_1"].eq(0)
            yield dut.ports["io_violationMdata_0"].eq(0x10)
            yield dut.ports["io_violationMdata_1"].eq(0x04)
            yield Settle()
            observations.append(int((yield dut.ports["io_violationMmask_0_31"])))
            yield Tick()
            yield Settle()
            observations.append(int((yield dut.ports["io_violationMmask_0_31"])))
            observations.append(int((yield dut.ports["io_violationMmask_1_31"])))

        sim = Simulator(dut)
        sim.add_clock(1e-6)
        sim.add_process(process)
        sim.run()
        self.assertEqual([0, 1, 1], observations)

    # Check the physical-address line comparison boundary. / 检查物理地址行比较边界。
    def test_paddr_line_cam_uses_bits_23_through_2(self) -> None:
        """Line checks ignore only low bits [1:0], not the wider previous slice. / 行比较只忽略低位 [1:0]，不忽略更宽切片。"""

        module = load_subject()
        dut = module.LoadQueueDataFamily("LqPAddrModule_1")
        observations: list[int] = []

        def process():
            yield from idle_inputs(dut)
            yield dut.ports["io_wen_0"].eq(1)
            yield dut.ports["io_waddr_0"].eq(31)
            yield dut.ports["io_wdata_0"].eq(0xA5A5A7)
            yield Tick()
            yield dut.ports["io_wen_0"].eq(0)
            yield Tick()
            yield dut.ports["io_violationMdata_0"].eq(0xA5A5A6)
            yield dut.ports["io_violationCheckLine_0"].eq(0)
            yield Settle()
            observations.append(int((yield dut.ports["io_violationMmask_0_31"])))
            yield dut.ports["io_violationCheckLine_0"].eq(1)
            yield Settle()
            observations.append(int((yield dut.ports["io_violationMmask_0_31"])))
            yield dut.ports["io_violationMdata_0"].eq(0xA5A5A3)
            yield Settle()
            observations.append(int((yield dut.ports["io_violationMmask_0_31"])))

        sim = Simulator(dut)
        sim.add_clock(1e-6)
        sim.add_process(process)
        sim.run()
        self.assertEqual([0, 1, 0], observations)

    # Check release CAM results at the final entry. / 检查最后一个条目的 release CAM 结果。
    def test_paddr_release_cams_cover_last_bank_entry(self) -> None:
        """Release and release-violation CAMs compare every public query port. / release 与 release-violation CAM 覆盖每个公开查询端口。"""

        module = load_subject()
        dut = module.LoadQueueDataFamily("LqPAddrModule")
        observations: list[int] = []

        def process():
            yield from idle_inputs(dut)
            yield dut.ports["io_wen_0"].eq(1)
            yield dut.ports["io_waddr_0"].eq(71)
            yield dut.ports["io_wdata_0"].eq(0x55AA)
            yield Tick()
            yield dut.ports["io_wen_0"].eq(0)
            yield dut.ports["io_releaseMdata_2"].eq(0x55AA)
            yield dut.ports["io_releaseViolationMdata_0"].eq(0x55AA)
            yield dut.ports["io_releaseViolationMdata_1"].eq(0x55AB)
            yield dut.ports["io_releaseViolationMdata_2"].eq(0x55AA)
            yield Settle()
            observations.append(int((yield dut.ports["io_releaseMmask_2_71"])))
            observations.append(int((yield dut.ports["io_releaseViolationMmask_0_71"])))
            observations.append(int((yield dut.ports["io_releaseViolationMmask_1_71"])))
            observations.append(int((yield dut.ports["io_releaseViolationMmask_2_71"])))

        sim = Simulator(dut)
        sim.add_clock(1e-6)
        sim.add_process(process)
        sim.run()
        self.assertEqual([1, 1, 0, 1], observations)

    # Check enabled read capture and disabled read hold behavior. / 检查读使能捕获及禁用保持行为。
    def test_vaddr_regenable_read_holds_when_ren_is_low(self) -> None:
        """VAddr reads capture old memory at an enabled edge and retain it otherwise. / VAddr 读取在使能边沿捕获旧存储值，并在非使能时保持。"""

        module = load_subject()
        dut = module.LoadQueueDataFamily("LqVAddrModule")
        observations: list[int] = []

        def process():
            yield from idle_inputs(dut)
            yield dut.ports["io_wen_0"].eq(1)
            yield dut.ports["io_waddr_0"].eq(71)
            yield dut.ports["io_wdata_0"].eq(0x123456789ABCD)
            yield Tick()
            yield dut.ports["io_wen_0"].eq(0)
            yield dut.ports["io_ren_0"].eq(1)
            yield dut.ports["io_raddr_0"].eq(71)
            yield Tick()
            yield Settle()
            observations.append(int((yield dut.ports["io_rdata_0"])))
            yield Tick()
            yield Settle()
            observations.append(int((yield dut.ports["io_rdata_0"])))
            yield dut.ports["io_ren_0"].eq(0)
            yield dut.ports["io_raddr_0"].eq(0)
            yield Tick()
            yield Settle()
            observations.append(int((yield dut.ports["io_rdata_0"])))

        sim = Simulator(dut)
        sim.add_clock(1e-6)
        sim.add_process(process)
        sim.run()
        self.assertEqual([0, 0x123456789ABCD, 0x123456789ABCD], observations)

    # Check that invalid Vec addresses select entry zero. / 检查超出 Vec 范围的地址选择零号条目。
    def test_vaddr_out_of_range_read_uses_entry_zero(self) -> None:
        """VAddr Vec reads above entry 71 return entry zero. / VAddr Vec 读取超过 71 时返回零号条目。"""

        module = load_subject()
        dut = module.LoadQueueDataFamily("LqVAddrModule")
        observations: list[int] = []

        def process():
            yield from idle_inputs(dut)
            yield dut.ports["io_wen_0"].eq(1)
            yield dut.ports["io_waddr_0"].eq(0)
            yield dut.ports["io_wdata_0"].eq(0x23456789ABCDE)
            yield Tick()
            yield dut.ports["io_wen_0"].eq(0)
            yield Tick()
            yield dut.ports["io_ren_0"].eq(1)
            yield dut.ports["io_raddr_0"].eq(127)
            yield Tick()
            yield Settle()
            observations.append(int((yield dut.ports["io_rdata_0"])))

        sim = Simulator(dut)
        sim.add_clock(1e-6)
        sim.add_process(process)
        sim.run()
        self.assertEqual([0x23456789ABCDE], observations)


    # Check that exported read state remains as three named registers. / 检查导出读状态保留为三个具名寄存器。
    def test_vaddr_export_preserves_named_read_registers(self) -> None:
        module = load_subject()
        verilog_text = module.build_verilog({"module": "LqVAddrModule"}, {})

        for read in range(3):
            register_name = f"io_rdata_{read}_r"
            self.assertRegex(
                verilog_text,
                rf"(?m)^\s*(?:reg|wire)\s+\[49:0\]\s+{register_name}\b",
            )
            self.assertRegex(verilog_text, rf"(?m)^\s+{register_name}\s*<=")
            self.assertRegex(verilog_text, rf"(?m)^\s*assign io_rdata_{read}\s*=")
            self.assertGreaterEqual(verilog_text.count(register_name), 3)


if __name__ == "__main__":
    unittest.main()
