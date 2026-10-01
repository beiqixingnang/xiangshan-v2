"""Reusable bounded tests for the UHSC V2 prefetch family."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any

from amaranth.sim import Settle, Simulator, Tick

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Cpu-Memory-Memory.Prefetch.Family-Hardware.py"


def load_subject() -> Any:
    spec = importlib.util.spec_from_file_location("testing_prefetch_family", TARGET)
    if spec is None or spec.loader is None: raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); return module


class PrefetchFamilyTest(unittest.TestCase):
    def test_all_members_export(self) -> None:
        module = load_subject()
        for member in module.COVERED_MODULES: self.assertIn(f"module {member}", module.build_verilog({"module": member}, {}))

    def test_active_generation_table_allocates_updates_and_falls_back_to_pht(self) -> None:
        subject = load_subject()
        dut = subject.PrefetchFamily("ActiveGenerationTable")
        ports = dut.ports
        observed: list[int] = []

        def process():
            for name, direction, _width in subject.PORT_SPECS["ActiveGenerationTable"]:
                if direction == "input" and name not in ("clock", "reset"):
                    yield ports[name].eq(0)
            yield ports["reset"].eq(1)
            yield Tick("prefetch")
            yield ports["reset"].eq(0)
            yield ports["io_s0_lookup_bits_region_tag"].eq(0x315)
            yield ports["io_s0_lookup_bits_region_p1_tag"].eq(0x314)
            yield ports["io_s0_lookup_bits_region_m1_tag"].eq(0x316)
            yield ports["io_s0_lookup_bits_region_offset"].eq(4)
            yield ports["io_s0_lookup_bits_pht_index"].eq(0x13)
            yield ports["io_s0_lookup_bits_pht_tag"].eq(0x1456)
            yield ports["io_s0_lookup_bits_region_paddr"].eq(0x123456789A)
            yield ports["io_s0_lookup_bits_region_vaddr"].eq(0x23456789AB)
            yield ports["io_s0_lookup_valid"].eq(1)
            yield Tick("prefetch")
            yield ports["io_s0_lookup_valid"].eq(0)
            yield Tick("prefetch")
            yield Settle()
            observed.append((yield ports["io_s2_pht_lookup_valid"]))
            observed.append((yield ports["io_s2_pht_lookup_bits_pht_index"]))
            observed.append((yield ports["io_s2_pht_lookup_bits_pht_tag"]))
            observed.append((yield ports["io_s2_pht_lookup_bits_region_paddr"]))
            observed.append((yield ports["io_s2_pht_lookup_bits_region_vaddr"]))
            observed.append((yield ports["io_s2_pht_lookup_bits_region_offset"]))

            # A repeat access updates the resident region entry instead of reallocating it.
            yield ports["io_s0_lookup_bits_region_offset"].eq(5)
            yield ports["io_s0_lookup_valid"].eq(1)
            yield Tick("prefetch")
            yield ports["io_s0_lookup_valid"].eq(0)
            yield Settle()
            observed.append((yield ports["io_s1_sel_stride"]))
            yield Tick("prefetch")

        simulator = Simulator(dut)
        simulator.add_clock(1e-6, domain="prefetch")
        simulator.add_process(process)
        simulator.run()
        self.assertEqual(observed, [1, 0x13, 0x1456, 0x123456789A, 0x23456789AB, 4, 0])

    def test_bloom_filter_set_and_clear(self) -> None:
        subject = load_subject()
        dut = subject.PrefetchFamily("BloomFilter")
        ports = dut.ports
        bits = dut._private_state["bloom_bits"]
        observed: list[int] = []

        def process():
            for name, direction, _width in subject.PORT_SPECS["BloomFilter"]:
                if direction == "input" and name not in ("clock", "reset"):
                    yield ports[name].eq(0)
            yield ports["reset"].eq(1)
            yield Tick("prefetch")
            yield ports["reset"].eq(0)
            yield ports["io_set_valid"].eq(1)
            yield ports["io_set_bits_addr"].eq(0x321)
            yield Tick("prefetch")
            yield ports["io_set_valid"].eq(0)
            yield Settle()
            observed.append((yield bits[0x321]))

            yield ports["io_set_valid"].eq(1)
            yield ports["io_set_bits_addr"].eq(0x777)
            yield ports["io_clr_valid"].eq(1)
            yield ports["io_clr_bits_addr"].eq(0x321)
            yield Tick("prefetch")
            yield ports["io_set_valid"].eq(0)
            yield ports["io_clr_valid"].eq(0)
            yield Settle()
            observed.extend(((yield bits[0x321]), (yield bits[0x777])))

        simulator = Simulator(dut)
        simulator.add_clock(1e-6, domain="prefetch")
        simulator.add_process(process)
        simulator.run()
        self.assertEqual(observed, [1, 0, 1])

    def test_counter_filter_tracks_set_way_and_delayed_free(self) -> None:
        subject = load_subject()
        dut = subject.PrefetchFamily("CounterFilter")
        ports = dut.ports
        observed: list[int] = []

        def process():
            for name, direction, _width in subject.PORT_SPECS["CounterFilter"]:
                if direction == "input" and name not in ("clock", "reset"):
                    yield ports[name].eq(0)
            yield ports["reset"].eq(1)
            yield Tick("prefetch")
            yield ports["reset"].eq(0)
            yield ports["io_ld_in_0_valid"].eq(1)
            yield ports["io_ld_in_0_bits_idx"].eq(0x4A)
            yield ports["io_ld_in_0_bits_way"].eq(2)
            yield ports["io_ld_in_1_valid"].eq(1)
            yield ports["io_ld_in_1_bits_idx"].eq(0xC3)
            yield ports["io_ld_in_1_bits_way"].eq(1)
            yield ports["io_query_0_req_valid"].eq(1)
            yield ports["io_query_0_req_bits_idx"].eq(0x4A)
            yield ports["io_query_0_req_bits_way"].eq(2)
            yield ports["io_query_1_req_valid"].eq(1)
            yield ports["io_query_1_req_bits_idx"].eq(0xC3)
            yield ports["io_query_1_req_bits_way"].eq(1)
            yield ports["io_query_2_req_valid"].eq(1)
            yield ports["io_query_2_req_bits_idx"].eq(0x4A)
            yield ports["io_query_2_req_bits_way"].eq(1)
            yield Tick("prefetch")
            yield Settle()
            observed.extend(
                (
                    (yield ports["io_query_0_resp"]),
                    (yield ports["io_query_1_resp"]),
                    (yield ports["io_query_2_resp"]),
                )
            )
            yield ports["io_ld_in_0_valid"].eq(0)
            yield ports["io_ld_in_1_valid"].eq(0)
            for _ in range(4):
                yield Tick("prefetch")
            yield Settle()
            observed.append((yield ports["io_query_0_resp"]))

        simulator = Simulator(dut)
        simulator.add_clock(1e-6, domain="prefetch")
        simulator.add_process(process)
        simulator.run()
        self.assertEqual(observed, [1, 1, 0, 0])

    def test_train_filter_queues_and_deduplicates(self) -> None:
        subject = load_subject()
        results: dict[str, list[int]] = {}

        for member in ("TrainFilter", "TrainFilter_1"):
            dut = subject.PrefetchFamily(member)
            ports = dut.ports
            observed: list[int] = []

            def process():
                for name, direction, _width in subject.PORT_SPECS[member]:
                    if direction == "input" and name not in ("clock", "reset"):
                        yield ports[name].eq(0)
                yield ports["reset"].eq(1)
                yield Tick("prefetch")
                yield ports["reset"].eq(0)
                yield ports["io_enable"].eq(1)
                yield ports["io_train_req_ready"].eq(0)
                yield ports["io_ld_in_0_valid"].eq(1)
                yield ports["io_ld_in_0_bits_vaddr"].eq(0x123456)
                if member == "TrainFilter":
                    yield ports["io_ld_in_0_bits_uop_pc"].eq(0x34567)
                else:
                    yield ports["io_ld_in_0_bits_miss"].eq(1)
                    yield ports["io_ld_in_0_bits_meta_prefetch"].eq(3)
                for _ in range(4):
                    yield Tick("prefetch")
                yield ports["io_ld_in_0_valid"].eq(0)
                yield Settle()
                observed.append((yield ports["io_train_req_valid"]))
                observed.append((yield ports["io_train_req_bits_vaddr"]))
                if member == "TrainFilter":
                    observed.append((yield ports["io_train_req_bits_pc"]))
                else:
                    observed.append((yield ports["io_train_req_bits_miss"]))
                    observed.append((yield ports["io_train_req_bits_pfHitStream"]))

                # Same cache block is suppressed while the first item remains queued.
                yield ports["io_ld_in_1_valid"].eq(1)
                yield ports["io_ld_in_1_bits_vaddr"].eq(0x12347F)
                if member == "TrainFilter":
                    yield ports["io_ld_in_1_bits_uop_pc"].eq(0x45678)
                else:
                    yield ports["io_ld_in_1_bits_miss"].eq(0)
                    yield ports["io_ld_in_1_bits_meta_prefetch"].eq(0)
                for _ in range(4):
                    yield Tick("prefetch")
                yield ports["io_ld_in_1_valid"].eq(0)
                yield Settle()
                observed.append((yield ports["io_train_req_valid"]))
                observed.append((yield ports["io_train_req_bits_vaddr"]))

            simulator = Simulator(dut)
            simulator.add_clock(1e-6, domain="prefetch")
            simulator.add_process(process)
            simulator.run()
            results[member] = observed

        self.assertEqual(results["TrainFilter"], [1, 0x123456, 0x34567, 1, 0x123456])
        self.assertEqual(results["TrainFilter_1"], [1, 0x123456, 1, 1, 1, 0x123456])

    def test_sms_train_filter_reorders_and_emits_one_request_per_cycle(self) -> None:
        subject = load_subject()
        dut = subject.PrefetchFamily("SMSTrainFilter")
        ports = dut.ports
        observed: list[tuple[int, int, int, int]] = []

        def process():
            for name, direction, _width in subject.PORT_SPECS["SMSTrainFilter"]:
                if direction == "input" and name not in ("clock", "reset"):
                    yield ports[name].eq(0)
            yield ports["reset"].eq(1)
            yield Tick("prefetch")
            yield ports["reset"].eq(0)
            # Lane 1 is older, so the ROB ordering network places it first.
            yield ports["io_ld_in_0_valid"].eq(1)
            yield ports["io_ld_in_0_bits_uop_robIdx_value"].eq(20)
            yield ports["io_ld_in_0_bits_uop_pc"].eq(0x11111)
            yield ports["io_ld_in_0_bits_vaddr"].eq(0x900000)
            yield ports["io_ld_in_0_bits_paddr"].eq(0xA00000)
            yield ports["io_ld_in_1_valid"].eq(1)
            yield ports["io_ld_in_1_bits_uop_robIdx_value"].eq(5)
            yield ports["io_ld_in_1_bits_uop_pc"].eq(0x22222)
            yield ports["io_ld_in_1_bits_vaddr"].eq(0xA00000)
            yield ports["io_ld_in_1_bits_paddr"].eq(0xB00000)
            for _ in range(4):
                yield Tick("prefetch")
            yield Settle()
            observed.append(
                (
                    (yield ports["io_train_req_valid"]),
                    (yield ports["io_train_req_bits_vaddr"]),
                    (yield ports["io_train_req_bits_paddr"]),
                    (yield ports["io_train_req_bits_pc"]),
                )
            )
            yield Tick("prefetch")
            yield Settle()
            observed.append(
                (
                    (yield ports["io_train_req_valid"]),
                    (yield ports["io_train_req_bits_vaddr"]),
                    (yield ports["io_train_req_bits_paddr"]),
                    (yield ports["io_train_req_bits_pc"]),
                )
            )

        simulator = Simulator(dut)
        simulator.add_clock(1e-6, domain="prefetch")
        simulator.add_process(process)
        simulator.run()
        self.assertEqual(observed, [(1, 0xA00000, 0xB00000, 0x22222), (1, 0x900000, 0xA00000, 0x11111)])


if __name__ == "__main__": unittest.main()
