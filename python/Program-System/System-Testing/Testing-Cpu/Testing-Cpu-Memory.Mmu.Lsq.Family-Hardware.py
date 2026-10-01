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
        self.assertIn("AgeDetector_38", subject.IMPLEMENTED_MEMBERS)
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

    def test_bitmap_pmp_fault_completes_entry(self):
        """A PMP fault bypasses cache/memory and reports all fault bits."""

        subject = load_subject()
        dut = subject.MemoryFamily("Bitmap")
        p = dut.ports

        def process():
            for name, direction, _width in subject.PORT_SPECS["Bitmap"]:
                if direction == "input" and name not in ("clock", "reset"):
                    yield p[name].eq(0)
            yield p["reset"].eq(1)
            yield Tick("bitmap")
            yield p["reset"].eq(0)
            yield p["io_resp_ready"].eq(1)
            yield p["io_req_bits_id"].eq(5)
            yield p["io_req_bits_bmppn"].eq(0x123)
            yield p["io_req_bits_vpn"].eq(0x23456)
            yield p["io_req_bits_level"].eq(0)
            yield p["io_req_bits_hptw_bypassed"].eq(1)
            yield p["io_req_valid"].eq(1)
            yield Tick("bitmap")
            yield p["io_req_valid"].eq(0)
            yield p["io_pmp_resp_ld"].eq(1)
            yield Tick("bitmap")
            yield p["io_pmp_resp_ld"].eq(0)
            yield Settle()
            self.assertEqual((yield p["io_resp_valid"]), 1)
            self.assertEqual((yield p["io_resp_bits_id"]), 5)
            self.assertEqual((yield p["io_resp_bits_cf"]), 1)
            observed_cfs = []
            for bit in range(8):
                observed_cfs.append((yield p[f"io_resp_bits_cfs_{bit}"]))
            self.assertEqual(observed_cfs, [1] * 8)
            self.assertEqual((yield p["io_mem_req_valid"]), 0)
            yield Tick("bitmap")

        simulator = Simulator(dut)
        simulator.add_clock(1e-6, domain="bitmap")
        simulator.add_process(process)
        simulator.run()

    def test_bitmap_cache_miss_memory_response(self):
        """A cache miss issues one bitmap memory read and decodes its word."""

        subject = load_subject()
        dut = subject.MemoryFamily("Bitmap")
        p = dut.ports
        bmppn = 0x123
        bma = 0x100
        value = (1 << 512) - 1
        expected_addr = ((bma & ((1 << 42) - 1)) << 6) + ((bmppn >> 6) << 3)

        def process():
            for name, direction, _width in subject.PORT_SPECS["Bitmap"]:
                if direction == "input" and name not in ("clock", "reset"):
                    yield p[name].eq(0)
            yield p["reset"].eq(1)
            yield Tick("bitmap")
            yield p["reset"].eq(0)
            yield p["io_csr_mbmc_BMA"].eq(bma)
            yield p["io_resp_ready"].eq(1)
            yield p["io_req_bits_id"].eq(3)
            yield p["io_req_bits_bmppn"].eq(bmppn)
            yield p["io_req_bits_vpn"].eq(0x34567)
            yield p["io_req_bits_level"].eq(0)
            yield p["io_req_bits_hptw_bypassed"].eq(1)
            yield p["io_cache_req_ready"].eq(1)
            yield p["io_req_valid"].eq(1)
            yield Tick("bitmap")
            yield p["io_req_valid"].eq(0)
            yield Tick("bitmap")
            yield Settle()
            self.assertEqual((yield p["io_cache_req_valid"]), 1)
            self.assertEqual((yield p["io_cache_req_bits_order"]), 0)
            self.assertEqual((yield p["io_cache_req_bits_tag"]), bmppn)
            yield Tick("bitmap")
            yield p["io_cache_resp_valid"].eq(1)
            yield p["io_cache_resp_bits_order"].eq(0)
            yield p["io_cache_resp_bits_hit"].eq(0)
            yield Tick("bitmap")
            yield p["io_cache_resp_valid"].eq(0)
            yield Settle()
            self.assertEqual((yield p["io_mem_req_valid"]), 1)
            self.assertEqual((yield p["io_mem_req_bits_addr"]), expected_addr)
            self.assertEqual((yield p["io_mem_req_bits_id"]), 8)
            yield p["io_mem_req_ready"].eq(1)
            yield Tick("bitmap")
            yield p["io_mem_req_ready"].eq(0)
            yield p["io_mem_resp_valid"].eq(1)
            yield p["io_mem_resp_bits_id"].eq(8)
            yield p["io_mem_resp_bits_value"].eq(value)
            yield Tick("bitmap")
            yield p["io_mem_resp_valid"].eq(0)
            yield Settle()
            self.assertEqual((yield p["io_resp_valid"]), 1)
            self.assertEqual((yield p["io_resp_bits_id"]), 3)
            self.assertEqual((yield p["io_resp_bits_cf"]), 1)
            self.assertEqual((yield p["io_refill_valid"]), 1)
            self.assertEqual((yield p["io_refill_bits_tag"]), bmppn)
            self.assertEqual((yield p["io_refill_bits_data"]), (1 << 64) - 1)
            yield Tick("bitmap")

        simulator = Simulator(dut)
        simulator.add_clock(1e-6, domain="bitmap")
        simulator.add_process(process)
        simulator.run()

    def test_bitmap_memory_arbiter_preserves_slot_id(self):
        """A masked slot must not rewrite the selected slot's response ID."""

        subject = load_subject()
        dut = subject.MemoryFamily("Bitmap")
        p = dut.ports

        def process():
            for name, direction, _width in subject.PORT_SPECS["Bitmap"]:
                if direction == "input" and name not in ("clock", "reset"):
                    yield p[name].eq(0)
            yield p["reset"].eq(1)
            yield Tick("bitmap")
            yield p["reset"].eq(0)
            yield p["io_resp_ready"].eq(0)
            yield p["io_cache_req_ready"].eq(1)
            yield p["io_mem_req_mask_0"].eq(1)

            # Fill slot zero through a cache miss and leave its memory request
            # pending.  The masked slot must be skipped by the RR arbiter.
            yield p["io_req_bits_bmppn"].eq(0x100)
            yield p["io_req_bits_vpn"].eq(0x1000)
            yield p["io_req_bits_hptw_bypassed"].eq(1)
            yield p["io_req_valid"].eq(1)
            yield Tick("bitmap")
            yield p["io_req_valid"].eq(0)
            yield Tick("bitmap")
            yield Tick("bitmap")
            yield p["io_cache_resp_valid"].eq(1)
            yield p["io_cache_resp_bits_order"].eq(0)
            yield p["io_cache_resp_bits_hit"].eq(0)
            yield Tick("bitmap")
            yield p["io_cache_resp_valid"].eq(0)
            yield Settle()
            self.assertEqual((yield p["io_mem_req_valid"]), 0)

            # The second miss occupies slot one.  With slot zero masked, its
            # memory request must carry the zero-extended slot-one ID (9).
            yield p["io_req_bits_bmppn"].eq(0x200)
            yield p["io_req_bits_vpn"].eq(0x2000)
            yield p["io_req_valid"].eq(1)
            yield Tick("bitmap")
            yield p["io_req_valid"].eq(0)
            yield Tick("bitmap")
            yield Tick("bitmap")
            yield p["io_cache_resp_valid"].eq(1)
            yield p["io_cache_resp_bits_order"].eq(1)
            yield p["io_cache_resp_bits_hit"].eq(0)
            yield Tick("bitmap")
            yield p["io_cache_resp_valid"].eq(0)
            yield p["io_mem_req_ready"].eq(1)
            yield Settle()
            self.assertEqual((yield p["io_mem_req_valid"]), 1)
            self.assertEqual((yield p["io_mem_req_bits_id"]), 9)
            yield Tick("bitmap")

        simulator = Simulator(dut)
        simulator.add_clock(1e-6, domain="bitmap")
        simulator.add_process(process)
        simulator.run()
if __name__ == "__main__": unittest.main()
