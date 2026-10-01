"""Direct bounded test for Cpu-Memory-Memory.Mmu.Lsq.Family-Hardware.py."""
from __future__ import annotations
import importlib.util
import unittest
from pathlib import Path
from amaranth.sim import Settle, Simulator, Tick
ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Cpu-Memory-Memory.Mmu.Lsq.Family-Hardware.py"
# Load the exact Build subject. / 装载精确 Build 主体。
def load_subject():
    # Avoid any sibling build import. / 避免任何兄弟 Build 导入。
    spec = importlib.util.spec_from_file_location("memory_family_subject", TARGET)
    if spec is None or spec.loader is None: raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
class MemoryFamilyTest(unittest.TestCase):
    # Verify every frozen member exports. / 验证每个冻结成员可导出。
    def test_exact_members_export(self):
        # Iterate the declared family catalog. / 遍历声明的 family catalog。
        module = load_subject()
        for member in module.COVERED_MODULES:
            self.assertIn("module " + member, module.build_verilog({"module": member}, {}))

    def test_age_detector_38_tracks_enqueue_order_and_dequeue(self):
        """Exercise the locked 24-entry LSQ age relation over real clock edges."""

        subject = load_subject()
        self.assertEqual(("AgeDetector_38",), subject.IMPLEMENTED_MEMBERS)
        dut = subject.MemoryFamily("AgeDetector_38")
        reset = dut.ports["reset"]
        enq0 = dut.ports["io_enq_0"]
        enq1 = dut.ports["io_enq_1"]
        enq2 = dut.ports["io_enq_2"]
        deq = dut.ports["io_deq"]
        ready = dut.ports["io_ready"]
        out = dut.ports["io_out"]
        observed: list[int] = []

        def process():
            yield reset.eq(1)
            yield Tick("age")
            yield reset.eq(0)
            yield enq0.eq(0)
            yield enq1.eq(0)
            yield enq2.eq(0)
            yield deq.eq(0)
            yield ready.eq(0)
            yield Settle()
            observed.append((yield out))

            yield enq0.eq(1 << 5)
            yield ready.eq(1 << 5)
            yield Tick("age")
            yield enq0.eq(0)
            yield Settle()
            observed.append((yield out))

            yield enq1.eq(1 << 2)
            yield ready.eq((1 << 2) | (1 << 5))
            yield Tick("age")
            yield enq1.eq(0)
            yield Settle()
            observed.append((yield out))

            yield deq.eq(1 << 5)
            yield Tick("age")
            yield deq.eq(0)
            yield Settle()
            observed.append((yield out))

        simulator = Simulator(dut)
        simulator.add_clock(1e-6, domain="age")
        simulator.add_process(process)
        simulator.run()
        self.assertEqual([0, 1 << 5, 1 << 5, 1 << 2], observed)

    def test_age_detector_38_honors_enqueue_port_priority(self):
        """A same-cycle port-zero enqueue is older than port-one."""

        subject = load_subject()
        dut = subject.MemoryFamily("AgeDetector_38")
        reset = dut.ports["reset"]
        enq0 = dut.ports["io_enq_0"]
        enq1 = dut.ports["io_enq_1"]
        ready = dut.ports["io_ready"]
        out = dut.ports["io_out"]
        observed: list[int] = []

        def process():
            yield reset.eq(1)
            yield Tick("age")
            yield reset.eq(0)
            yield enq0.eq(1 << 1)
            yield enq1.eq(1 << 3)
            yield ready.eq((1 << 1) | (1 << 3))
            yield Tick("age")
            yield enq0.eq(0)
            yield enq1.eq(0)
            yield Settle()
            observed.append((yield out))

        simulator = Simulator(dut)
        simulator.add_clock(1e-6, domain="age")
        simulator.add_process(process)
        simulator.run()
        self.assertEqual([1 << 1], observed)
if __name__ == "__main__": unittest.main()
