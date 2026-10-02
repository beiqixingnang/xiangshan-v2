#!/usr/bin/env python3
# Module Contract
"""Direct behavior tests for the DCache miss, probe, arbiter, and writeback family."""

from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
import unittest
from pathlib import Path
from typing import Any, Final

from amaranth.sim import Settle, Simulator, Tick


# Fixtures And Support
TEST_ID: Final = "Build-Cpu.Memory.Dcache.MissQueue.Family"
SUBJECT_TYPE: Final = "build"
SUBJECT_ID: Final = "Build-Cpu.Memory.Dcache.MissQueue.Family"
DIRECT: Final = True
MEMBERS: Final = (
    "CMOUnit",
    "MissEntry",
    "MissReadyGen",
    "ProbeEntry",
    "TreeArbiter",
    "WritebackEntry",
    "WritebackEntry_15",
)
IMPLEMENTED_MEMBERS: Final = (
    "MissReadyGen",
    "TreeArbiter",
    "WritebackEntry",
    "WritebackEntry_15",
)
CONTRACT_ONLY_MEMBERS: Final = ("CMOUnit", "MissEntry", "ProbeEntry")
TARGET: Final = (
    Path(__file__).resolve().parents[4]
    / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/"
    "Cpu-Memory-Memory.Dcache.MissQueue.Family-Hardware.py"
)


def load_subject() -> Any:
    """Load the exact family Build path without loading sibling Builds."""

    spec = importlib.util.spec_from_file_location(
        "testing_dcache_miss_family_subject", TARGET
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Subject Contract
class BuildSubjectContractTest(unittest.TestCase):
    """Keep this direct test bound to its exact Manifest subject."""

    def test_subject_contract(self) -> None:
        subject = load_subject()
        self.assertTrue(DIRECT)
        self.assertEqual(SUBJECT_ID, TEST_ID)
        self.assertEqual("build", SUBJECT_TYPE)
        self.assertEqual(
            (
                "COVERED_MODULES",
                "CONTRACT_ONLY_MEMBERS",
                "IMPLEMENTED_MEMBERS",
                "PORT_SPECS",
                "DcacheMissQueueFamily",
                "build_verilog",
                "main",
            ),
            tuple(subject.__all__),
        )
        self.assertTrue(all(hasattr(subject, name) for name in subject.__all__))
        self.assertEqual(MEMBERS, tuple(subject.COVERED_MODULES))
        self.assertEqual(IMPLEMENTED_MEMBERS, tuple(subject.IMPLEMENTED_MEMBERS))
        self.assertEqual(CONTRACT_ONLY_MEMBERS, tuple(subject.CONTRACT_ONLY_MEMBERS))
        source = TARGET.read_text(encoding="utf-8")
        sections = (
            "# Module Contract",
            "# Configuration",
            "# Implementation",
            "# Public Adapter",
            "# Direct Entry",
        )
        positions = tuple(source.index(section) for section in sections)
        self.assertEqual(tuple(sorted(positions)), positions)
        self.assertIn("module MissReadyGen", subject.build_verilog({"module": "MissReadyGen"}, {}))


# Behavior Tests
class DcacheMissQueueFamilyBehaviorTest(unittest.TestCase):
    """Exercise implemented leaves through their real Amaranth equations."""

    def setUp(self) -> None:
        self.module = load_subject()

    def test_catalog_contract_exports_and_classification(self) -> None:
        self.assertEqual(MEMBERS, tuple(self.module.COVERED_MODULES))
        self.assertEqual(IMPLEMENTED_MEMBERS, tuple(self.module.IMPLEMENTED_MEMBERS))
        self.assertEqual(CONTRACT_ONLY_MEMBERS, tuple(self.module.CONTRACT_ONLY_MEMBERS))
        self.assertEqual(set(MEMBERS), set(self.module.PORT_SPECS))
        self.assertEqual(5, next(
            width for name, _direction, width
            in self.module.PORT_SPECS["WritebackEntry"] if name == "io_id"
        ))
        self.assertEqual(6, next(
            width for name, _direction, width
            in self.module.PORT_SPECS["WritebackEntry_15"] if name == "io_id"
        ))
        for member in MEMBERS:
            for _name, direction, width in self.module.PORT_SPECS[member]:
                self.assertIn(direction, ("input", "output"))
                self.assertGreaterEqual(width, 1)

    def test_each_member_exports_deterministic_same_name_verilog(self) -> None:
        for member in MEMBERS:
            with self.subTest(member=member):
                first = self.module.build_verilog({"module": member}, {})
                second = self.module.build_verilog({"module": member}, {})
                self.assertEqual(first, second)
                self.assertGreater(len(first), 100)
                self.assertRegex(first, rf"\bmodule\s+{re.escape(member)}\b")
                self.assertNotEqual(
                    hashlib.sha256(first.encode()).hexdigest(), "0" * 64
                )

    def test_public_adapter_rejects_unknown_member(self) -> None:
        with self.assertRaises(ValueError):
            self.module.build_verilog({"module": "NotAMissQueueMember"}, {})

    def test_miss_ready_queries_and_priority_ready_for_all_valid_masks(self) -> None:
        dut = self.module.DcacheMissQueueFamily("MissReadyGen")

        def process():
            for valid_mask in range(8):
                for ready_mask in range(16):
                    for index in range(3):
                        yield dut.ports[f"io_in_{index}_valid"].eq(
                            (valid_mask >> index) & 1
                        )
                    for index in range(4):
                        yield dut.ports[f"io_queryMQ_{index}_ready"].eq(
                            (ready_mask >> index) & 1
                        )
                        payloads = {
                            "source": (valid_mask + 3 * index) & 0xF,
                            "addr": (0x1200 + 0x101 * index + valid_mask) & ((1 << 48) - 1),
                            "vaddr": (0x5000 + 0x203 * index + valid_mask) & ((1 << 50) - 1),
                        }
                        for field, value in payloads.items():
                            yield dut.ports[f"io_in_{index}_bits_{field}"].eq(value)
                    yield Settle()
                    for index in range(4):
                        blocked = any((valid_mask >> earlier) & 1 for earlier in range(index))
                        self.assertEqual(
                            ((ready_mask >> index) & 1) & int(not blocked),
                            (yield dut.ports[f"io_in_{index}_ready"]),
                        )
                        for field in ("source", "addr", "vaddr"):
                            self.assertEqual(
                                (yield dut.ports[f"io_in_{index}_bits_{field}"]),
                                (yield dut.ports[f"io_queryMQ_{index}_req_bits_{field}"]),
                            )

        simulator = Simulator(dut)
        simulator.add_process(process)
        simulator.run()

    def test_tree_arbiter_priority_and_unmasked_invalid_payloads(self) -> None:
        dut = self.module.DcacheMissQueueFamily("TreeArbiter")
        specifications = self.module.PORT_SPECS["TreeArbiter"]
        input_widths = {
            name: width
            for name, direction, width in specifications
            if direction == "input"
        }
        output_names = tuple(
            name for name, direction, _width in specifications
            if direction == "output"
        )

        def process():
            for valid_mask in range(16):
                for index in range(4):
                    yield dut.ports[f"io_in_{index}_valid"].eq(
                        (valid_mask >> index) & 1
                    )
                    prefix = f"io_in_{index}_bits_"
                    for name, width in input_widths.items():
                        if name.startswith(prefix):
                            field = name[len(prefix):]
                            value = (
                                (valid_mask + 1) * 0x13579BDF
                                ^ (index + 5) * 0x2468ACE1
                                ^ sum(field.encode("ascii"))
                            ) & ((1 << width) - 1)
                            yield dut.ports[name].eq(value)
                yield Settle()
                selected = next(
                    (index for index in range(4) if (valid_mask >> index) & 1),
                    3,
                )
                self.assertEqual(
                    int(valid_mask != 0), (yield dut.ports["io_out_valid"])
                )
                for output in output_names:
                    if output == "io_out_valid":
                        continue
                    field = output.removeprefix("io_out_bits_")
                    source = f"io_in_{selected}_bits_{field}"
                    if field in {
                        "full_overwrite", "word_idx", "amo_data", "amo_mask",
                        "amo_cmp", "id", "store_data", "store_mask",
                    }:
                        expected = (
                            (yield dut.ports[source]) if valid_mask & 1 else 0
                        )
                    elif field == "pf_source" and selected == 0:
                        expected = 0
                    else:
                        expected = (yield dut.ports[source])
                    self.assertEqual(expected, (yield dut.ports[output]), output)

        simulator = Simulator(dut)
        simulator.add_process(process)
        simulator.run()

    def test_probe_lrsc_delay_backpressure_response_match_and_saved_request(self) -> None:
        dut = self.module.DcacheMissQueueFamily("ProbeEntry")
        observations: list[tuple[int, int, int, int, int, int]] = []

        def process():
            yield dut.ports["reset"].eq(1)
            yield Tick()
            yield dut.ports["reset"].eq(0)
            yield dut.ports["io_id"].eq(5)
            yield dut.ports["io_req_valid"].eq(1)
            yield dut.ports["io_req_bits_addr"].eq(0x1234)
            yield dut.ports["io_req_bits_vaddr"].eq(0x2A1234)
            yield dut.ports["io_req_bits_param"].eq(2)
            yield dut.ports["io_req_bits_needData"].eq(1)
            yield dut.ports["io_lrsc_locked_block_valid"].eq(1)
            yield dut.ports["io_lrsc_locked_block_bits"].eq(0x1237)
            yield dut.ports["io_pipe_req_ready"].eq(1)
            yield Tick()
            yield dut.ports["io_req_valid"].eq(0)
            yield Settle()
            self.assertEqual(1, (yield dut.ports["io_block_addr_valid"]))
            self.assertEqual(0x1234, (yield dut.ports["io_block_addr_bits"]))
            self.assertEqual(0, (yield dut.ports["io_pipe_req_valid"]))
            for name, expected in (
                ("io_pipe_req_bits_probe_param", 2),
                ("io_pipe_req_bits_probe_need_data", 1),
                ("io_pipe_req_bits_addr", 0x1234),
                ("io_pipe_req_bits_vaddr", 0x2A1234),
                ("io_pipe_req_bits_id", 5),
            ):
                self.assertEqual(expected, (yield dut.ports[name]))

            # Releasing the reservation is observed through the registered
            # LR/SC block signal, so the request stays blocked until one edge.
            yield dut.ports["io_lrsc_locked_block_valid"].eq(0)
            yield Settle()
            self.assertEqual(0, (yield dut.ports["io_pipe_req_valid"]))
            yield Tick()
            yield Settle()
            self.assertEqual(1, (yield dut.ports["io_pipe_req_valid"]))

            # Backpressure holds the saved request in the pipe-request state.
            yield dut.ports["io_pipe_req_ready"].eq(0)
            yield Tick()
            yield Settle()
            self.assertEqual(1, (yield dut.ports["io_pipe_req_valid"]))
            yield dut.ports["io_pipe_req_ready"].eq(1)
            yield Tick()
            yield Settle()
            self.assertEqual(0, (yield dut.ports["io_pipe_req_valid"]))
            self.assertEqual(1, (yield dut.ports["io_block_addr_valid"]))

            # A response with the wrong ID cannot free the entry.
            yield dut.ports["io_pipe_resp_valid"].eq(1)
            yield dut.ports["io_pipe_resp_bits_id"].eq(4)
            yield Tick()
            yield Settle()
            self.assertEqual(1, (yield dut.ports["io_block_addr_valid"]))
            yield dut.ports["io_pipe_resp_bits_id"].eq(5)
            yield Tick()
            yield Settle()
            observations.append((
                int((yield dut.ports["io_req_ready"])),
                int((yield dut.ports["io_pipe_req_valid"])),
                int((yield dut.ports["io_block_addr_valid"])),
                int((yield dut.ports["io_pipe_req_bits_addr"])),
                int((yield dut.ports["io_pipe_req_bits_vaddr"])),
                int((yield dut.ports["io_pipe_req_bits_id"])),
            ))

        simulator = Simulator(dut)
        simulator.add_clock(1e-6)
        simulator.add_process(process)
        simulator.run()
        self.assertEqual([(1, 0, 0, 0x1234, 0x2A1234, 5)], observations)

    def test_writeback_variants_stream_data_and_preserve_id_width(self) -> None:
        payload = int("0123456789abcdef" * 4, 16) | (
            int("fedcba9876543210" * 4, 16) << 256
        )
        expected_beats = (payload & ((1 << 256) - 1), payload >> 256)
        for member, source_id in (("WritebackEntry", 17), ("WritebackEntry_15", 43)):
            with self.subTest(member=member):
                dut = self.module.DcacheMissQueueFamily(member)
                observed: list[tuple[int, int, int, int, int, int, int]] = []

                def process():
                    yield dut.ports["reset"].eq(1)
                    yield Tick()
                    yield dut.ports["reset"].eq(0)
                    yield dut.ports["io_id"].eq(source_id)
                    yield dut.ports["io_req_valid"].eq(1)
                    yield dut.ports["io_primary_valid"].eq(1)
                    yield dut.ports["io_req_bits_param"].eq(5)
                    yield dut.ports["io_req_bits_voluntary"].eq(0)
                    yield dut.ports["io_req_bits_hasData"].eq(1)
                    yield dut.ports["io_req_bits_corrupt"].eq(1)
                    yield dut.ports["io_req_bits_dirty"].eq(1)
                    yield dut.ports["io_req_bits_addr"].eq(0x123456789ABC)
                    yield dut.ports["io_req_data_data"].eq(payload)
                    yield dut.ports["io_mem_release_ready"].eq(0)
                    yield Tick()
                    yield dut.ports["io_req_valid"].eq(0)
                    yield dut.ports["io_primary_valid"].eq(0)
                    # The payload register captures req_data on the next edge.
                    yield Tick()
                    yield Settle()
                    self.assertEqual(1, (yield dut.ports["io_mem_release_valid"]))
                    yield dut.ports["io_mem_release_ready"].eq(1)
                    yield Settle()
                    for expected_data in expected_beats:
                        observed.append((
                            int((yield dut.ports["io_mem_release_valid"])),
                            int((yield dut.ports["io_mem_release_bits_opcode"])),
                            int((yield dut.ports["io_mem_release_bits_param"])),
                            int((yield dut.ports["io_mem_release_bits_source"])),
                            int((yield dut.ports["io_mem_release_bits_address"])),
                            int((yield dut.ports["io_mem_release_bits_data"])),
                            int((yield dut.ports["io_mem_release_bits_corrupt"])),
                        ))
                        self.assertEqual(expected_data, observed[-1][5])
                        yield Tick()
                        yield Settle()
                    self.assertEqual(0, (yield dut.ports["io_mem_release_valid"]))
                    self.assertEqual(1, (yield dut.ports["io_primary_ready"]))
                    self.assertEqual(0, (yield dut.ports["io_block_addr_valid"]))

                simulator = Simulator(dut)
                simulator.add_clock(1e-6)
                simulator.add_process(process)
                simulator.run()
                self.assertEqual(
                    [
                        (1, 5, 5, source_id, 0x123456789ABC, expected_beats[0], 1),
                        (1, 5, 5, source_id, 0x123456789ABC, expected_beats[1], 1),
                    ],
                    observed,
                )

    def test_writeback_no_data_voluntary_release_waits_for_grant(self) -> None:
        for member, source_id in (("WritebackEntry", 17), ("WritebackEntry_15", 43)):
            with self.subTest(member=member):
                dut = self.module.DcacheMissQueueFamily(member)
                observed: list[tuple[int, int, int, int, int]] = []

                def process():
                    yield dut.ports["reset"].eq(1)
                    yield Tick()
                    yield dut.ports["reset"].eq(0)
                    yield dut.ports["io_id"].eq(source_id)
                    yield dut.ports["io_req_valid"].eq(1)
                    yield dut.ports["io_primary_valid"].eq(1)
                    yield dut.ports["io_req_bits_param"].eq(2)
                    yield dut.ports["io_req_bits_voluntary"].eq(1)
                    yield dut.ports["io_req_bits_hasData"].eq(0)
                    yield dut.ports["io_req_bits_corrupt"].eq(0)
                    yield dut.ports["io_req_bits_dirty"].eq(0)
                    yield dut.ports["io_req_bits_addr"].eq(0x4000)
                    yield Tick()
                    yield dut.ports["io_req_valid"].eq(0)
                    yield dut.ports["io_primary_valid"].eq(0)
                    yield dut.ports["io_mem_release_ready"].eq(1)
                    yield Tick()
                    yield Settle()
                    observed.append((
                        int((yield dut.ports["io_mem_release_valid"])),
                        int((yield dut.ports["io_mem_release_bits_opcode"])),
                        int((yield dut.ports["io_mem_release_bits_source"])),
                        int((yield dut.ports["io_mem_release_bits_data"])),
                        int((yield dut.ports["io_block_addr_valid"])),
                    ))
                    yield Tick()
                    yield Settle()
                    self.assertEqual(0, (yield dut.ports["io_mem_release_valid"]))
                    self.assertEqual(0, (yield dut.ports["io_primary_ready"]))
                    self.assertEqual(1, (yield dut.ports["io_block_addr_valid"]))
                    yield dut.ports["io_mem_grant_valid"].eq(0)
                    yield Tick()
                    self.assertEqual(1, (yield dut.ports["io_block_addr_valid"]))
                    yield dut.ports["io_mem_grant_valid"].eq(1)
                    yield Tick()
                    yield Settle()
                    self.assertEqual(1, (yield dut.ports["io_primary_ready"]))
                    self.assertEqual(0, (yield dut.ports["io_block_addr_valid"]))

                simulator = Simulator(dut)
                simulator.add_clock(1e-6)
                simulator.add_process(process)
                simulator.run()
                self.assertEqual([(1, 6, source_id, 0, 1)], observed)
