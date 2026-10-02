#!/usr/bin/env python3
# Module Contract
"""Direct tests for the Kunminghu V2 store-buffer family."""

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
TEST_ID: Final = "Build-Cpu.Memory.Store.Family"
SUBJECT_TYPE: Final = "build"
SUBJECT_ID: Final = "Build-Cpu.Memory.Store.Family"
DIRECT: Final = True
MEMBERS: Final = (
    "SbufferData",
    "StoreExceptionBuffer",
    "StoreMisalignBuffer",
    "StoreUnit",
)
IMPLEMENTED_MEMBERS: Final = ("SbufferData", "StoreExceptionBuffer")
CONTRACT_ONLY_MEMBERS: Final = ("StoreMisalignBuffer", "StoreUnit")
TARGET: Final = (
    Path(__file__).resolve().parents[4]
    / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/"
    "Cpu-Memory-Memory.Store.Family-Hardware.py"
)


def load_subject() -> Any:
    """Load only this exact Build path."""

    spec = importlib.util.spec_from_file_location("testing_store_family_subject", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def store_exception_values(
    member: Any,
    index: int,
    *,
    rob_index: int,
    uop_index: int,
    vaddr: int,
    gpaddr: int,
    exception_bit: int = 7,
    va_need_ext: int = 0,
    is_hyper: int = 0,
    is_for_vs_nonleaf: int = 0,
) -> dict[str, int]:
    """Build one sparse locked input bundle for the exception buffer."""

    prefix = f"io_storeAddrIn_{index}_bits_"
    values = {
        f"io_storeAddrIn_{index}_valid": 1,
        f"{prefix}uop_uopIdx": uop_index,
        f"{prefix}uop_robIdx_flag": 0,
        f"{prefix}uop_robIdx_value": rob_index,
        f"{prefix}fullva": vaddr,
    }
    port_names = {name for name, _direction, _width in member.PORT_SPECS["StoreExceptionBuffer"]}
    for bit in (3, 6, 7, 15, 19, 23):
        signal = f"{prefix}uop_exceptionVec_{bit}"
        if signal in port_names:
            values[signal] = int(bit == exception_bit)
    for suffix, value in (
        ("vaNeedExt", va_need_ext),
        ("gpaddr", gpaddr),
        ("isHyper", is_hyper),
        ("isForVSnonLeafPTE", is_for_vs_nonleaf),
    ):
        signal = f"{prefix}{suffix}"
        if signal in port_names:
            values[signal] = value
    return values


# Subject Contract
class BuildSubjectContractTest(unittest.TestCase):
    """Bind this direct suite to the registered Build and its five zones."""

    def test_subject_contract(self) -> None:
        subject = load_subject()
        self.assertTrue(DIRECT)
        self.assertEqual(SUBJECT_ID, TEST_ID)
        self.assertEqual("build", SUBJECT_TYPE)
        self.assertEqual(
            (
                "COVERED_MODULES",
                "IMPLEMENTED_MEMBERS",
                "CONTRACT_ONLY_MEMBERS",
                "PORT_SPECS",
                "StoreFamily",
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
        self.assertIn("module SbufferData", subject.build_verilog({"module": "SbufferData"}, {}))


# Behavior Tests
class StoreFamilyBehaviorTest(unittest.TestCase):
    """Exercise the stateful leaves through their real Amaranth descriptions."""

    def setUp(self) -> None:
        self.module = load_subject()

    def test_catalog_exact_widths_and_member_declarations(self) -> None:
        self.assertEqual(MEMBERS, tuple(self.module.COVERED_MODULES))
        self.assertEqual(IMPLEMENTED_MEMBERS, tuple(self.module.IMPLEMENTED_MEMBERS))
        self.assertEqual(CONTRACT_ONLY_MEMBERS, tuple(self.module.CONTRACT_ONLY_MEMBERS))
        self.assertEqual(set(MEMBERS), set(self.module.PORT_SPECS))
        for member in MEMBERS:
            for _name, direction, width in self.module.PORT_SPECS[member]:
                self.assertIn(direction, ("input", "output"))
                self.assertGreaterEqual(width, 1)
        self.assertEqual(2064, len(self.module.PORT_SPECS["SbufferData"]))
        self.assertEqual(106, len(self.module.PORT_SPECS["StoreExceptionBuffer"]))
        self.assertEqual(200, len(self.module.PORT_SPECS["StoreMisalignBuffer"]))
        self.assertEqual(312, len(self.module.PORT_SPECS["StoreUnit"]))

    def test_exports_are_deterministic_and_keep_locked_top_names(self) -> None:
        for member in MEMBERS:
            with self.subTest(member=member):
                first = self.module.build_verilog({"module": member}, {})
                second = self.module.build_verilog({"module": member}, {})
                self.assertEqual(first, second)
                self.assertRegex(first, rf"\bmodule\s+{re.escape(member)}\b")
                self.assertGreater(len(first), 100)
                self.assertNotEqual(hashlib.sha256(first.encode()).hexdigest(), "0" * 64)
        with self.assertRaises(ValueError):
            self.module.build_verilog({"module": "NoSuchStoreMember"}, {})

    def test_sbuffer_two_cycle_sparse_and_full_line_writes(self) -> None:
        dut = self.module.StoreFamily("SbufferData")
        expected_sparse = 0x0123456789ABCDEF
        full_line_data = int("0123456789abcdef" * 2, 16)

        def process():
            yield dut.ports["reset"].eq(1)
            yield Tick()
            yield dut.ports["reset"].eq(0)
            yield dut.ports["io_writeReq_0_valid"].eq(1)
            yield dut.ports["io_writeReq_0_bits_wvec"].eq(1 << 3)
            yield dut.ports["io_writeReq_0_bits_mask"].eq(1 << 1)
            yield dut.ports["io_writeReq_0_bits_data"].eq(expected_sparse)
            yield dut.ports["io_writeReq_0_bits_vwordOffset"].eq(2)
            yield dut.ports["io_writeReq_0_bits_wline"].eq(0)
            yield Tick()
            yield Settle()
            self.assertEqual(0, (yield dut.ports["io_maskOut_3_2_1"]))
            yield dut.ports["io_writeReq_0_valid"].eq(0)
            yield Tick()
            yield Settle()
            self.assertEqual((expected_sparse >> 8) & 0xFF, (yield dut.ports["io_dataOut_3_2_1"]))
            self.assertEqual(1, (yield dut.ports["io_maskOut_3_2_1"]))
            self.assertEqual(0, (yield dut.ports["io_maskOut_3_2_0"]))
            self.assertEqual(0, (yield dut.ports["io_maskOut_3_1_1"]))

            yield dut.ports["io_writeReq_0_valid"].eq(1)
            yield dut.ports["io_writeReq_0_bits_wvec"].eq(1 << 7)
            yield dut.ports["io_writeReq_0_bits_mask"].eq(0)
            yield dut.ports["io_writeReq_0_bits_data"].eq(full_line_data)
            yield dut.ports["io_writeReq_0_bits_vwordOffset"].eq(1)
            yield dut.ports["io_writeReq_0_bits_wline"].eq(1)
            yield Tick()
            yield dut.ports["io_writeReq_0_valid"].eq(0)
            yield Tick()
            yield Settle()
            for word in range(4):
                for byte in range(16):
                    self.assertEqual(
                        (full_line_data >> (byte * 8)) & 0xFF,
                        (yield dut.ports[f"io_dataOut_7_{word}_{byte}"]),
                    )
                    self.assertEqual(1, (yield dut.ports[f"io_maskOut_7_{word}_{byte}"]))

        simulator = Simulator(dut)
        simulator.add_clock(1e-6)
        simulator.add_process(process)
        simulator.run()

    def test_sbuffer_port_one_priority_flush_delay_and_resetless_data(self) -> None:
        dut = self.module.StoreFamily("SbufferData")
        observed: list[tuple[int, int]] = []

        def process():
            yield dut.ports["reset"].eq(1)
            yield Tick()
            yield dut.ports["reset"].eq(0)
            for port, value in ((0, 0x11), (1, 0xAA)):
                yield dut.ports[f"io_writeReq_{port}_valid"].eq(1)
                yield dut.ports[f"io_writeReq_{port}_bits_wvec"].eq(1 << 5)
                yield dut.ports[f"io_writeReq_{port}_bits_mask"].eq(1)
                yield dut.ports[f"io_writeReq_{port}_bits_data"].eq(value)
                yield dut.ports[f"io_writeReq_{port}_bits_vwordOffset"].eq(0)
                yield dut.ports[f"io_writeReq_{port}_bits_wline"].eq(0)
            yield Tick()
            yield dut.ports["io_writeReq_0_valid"].eq(0)
            yield dut.ports["io_writeReq_1_valid"].eq(0)
            yield Tick()
            yield Settle()
            self.assertEqual(0xAA, (yield dut.ports["io_dataOut_5_0_0"]))
            self.assertEqual(1, (yield dut.ports["io_maskOut_5_0_0"]))

            yield dut.ports["io_maskFlushReq_0_valid"].eq(1)
            yield dut.ports["io_maskFlushReq_0_bits_wvec"].eq(1 << 5)
            yield Tick()
            yield Settle()
            self.assertEqual(1, (yield dut.ports["io_maskOut_5_0_0"]))
            yield dut.ports["io_maskFlushReq_0_valid"].eq(0)
            yield Tick()
            yield Settle()
            observed.append((
                int((yield dut.ports["io_maskOut_5_0_0"])),
                int((yield dut.ports["io_dataOut_5_0_0"])),
            ))
            yield dut.ports["reset"].eq(1)
            yield Settle()
            observed.append((
                int((yield dut.ports["io_maskOut_5_0_0"])),
                int((yield dut.ports["io_dataOut_5_0_0"])),
            ))

        simulator = Simulator(dut)
        simulator.add_clock(1e-6)
        simulator.add_process(process)
        simulator.run()
        self.assertEqual([(0, 0xAA), (0, 0xAA)], observed)

    def test_exception_buffer_pipeline_oldest_hold_and_redirect(self) -> None:
        dut = self.module.StoreFamily("StoreExceptionBuffer")
        observed: list[tuple[int, int, int, int, int]] = []

        def assign(values: dict[str, int]):
            for name, value in values.items():
                yield dut.ports[name].eq(value)

        def process():
            for name, direction, _width in self.module.PORT_SPECS["StoreExceptionBuffer"]:
                if direction == "input" and name not in ("clock", "reset"):
                    yield dut.ports[name].eq(0)
            yield dut.ports["reset"].eq(1)
            yield Tick()
            yield dut.ports["reset"].eq(0)

            # Inputs arrive on the first stage; output updates after the
            # second registered exception-selection stage.
            yield from assign(store_exception_values(
                self.module, 0, rob_index=7, uop_index=6, vaddr=0x7000,
                gpaddr=0x17000, exception_bit=15,
            ))
            yield from assign(store_exception_values(
                self.module, 1, rob_index=3, uop_index=1, vaddr=0x3000,
                gpaddr=0x13000, exception_bit=7, va_need_ext=1, is_hyper=1,
            ))
            yield Tick()
            yield dut.ports["io_storeAddrIn_0_valid"].eq(0)
            yield dut.ports["io_storeAddrIn_1_valid"].eq(0)
            yield Tick()
            yield Settle()
            observed.append((
                int((yield dut.ports["io_exceptionAddr_vaddr"])),
                int((yield dut.ports["io_exceptionAddr_gpaddr"])),
                int((yield dut.ports["io_exceptionAddr_vaNeedExt"])),
                int((yield dut.ports["io_exceptionAddr_isHyper"])),
                int((yield dut.ports["io_exceptionAddr_isForVSnonLeafPTE"])),
            ))

            # A younger later request cannot displace the stored older one.
            yield from assign(store_exception_values(
                self.module, 2, rob_index=4, uop_index=0, vaddr=0x4000,
                gpaddr=0x14000, exception_bit=23,
            ))
            yield Tick()
            yield dut.ports["io_storeAddrIn_2_valid"].eq(0)
            yield Tick()
            yield Settle()
            observed.append((
                int((yield dut.ports["io_exceptionAddr_vaddr"])),
                int((yield dut.ports["io_exceptionAddr_gpaddr"])),
                int((yield dut.ports["io_exceptionAddr_vaNeedExt"])),
                int((yield dut.ports["io_exceptionAddr_isHyper"])),
                int((yield dut.ports["io_exceptionAddr_isForVSnonLeafPTE"])),
            ))

            # Redirecting the held exception flushes the stored request.
            yield dut.ports["io_redirect_valid"].eq(1)
            yield dut.ports["io_redirect_bits_level"].eq(1)
            yield dut.ports["io_redirect_bits_robIdx_flag"].eq(0)
            yield dut.ports["io_redirect_bits_robIdx_value"].eq(3)
            yield Tick()
            yield dut.ports["io_redirect_valid"].eq(0)
            yield from assign(store_exception_values(
                self.module, 3, rob_index=5, uop_index=0, vaddr=0x5000,
                gpaddr=0x15000, exception_bit=19,
            ))
            yield Tick()
            yield dut.ports["io_storeAddrIn_3_valid"].eq(0)
            yield Tick()
            yield Settle()
            observed.append((
                int((yield dut.ports["io_exceptionAddr_vaddr"])),
                int((yield dut.ports["io_exceptionAddr_gpaddr"])),
                int((yield dut.ports["io_exceptionAddr_vaNeedExt"])),
                int((yield dut.ports["io_exceptionAddr_isHyper"])),
                int((yield dut.ports["io_exceptionAddr_isForVSnonLeafPTE"])),
            ))

        simulator = Simulator(dut)
        simulator.add_clock(1e-6)
        simulator.add_process(process)
        simulator.run()
        self.assertEqual(
            [
                (0x3000, 0x13000, 1, 1, 0),
                (0x3000, 0x13000, 1, 1, 0),
                (0x5000, 0x15000, 0, 0, 0),
            ],
            observed,
        )

    def test_contract_members_elaborate_and_reset_outputs(self) -> None:
        for member in CONTRACT_ONLY_MEMBERS:
            with self.subTest(member=member):
                dut = self.module.StoreFamily(member)
                outputs = [
                    name for name, direction, _width in self.module.PORT_SPECS[member]
                    if direction == "output"
                ]

                def process():
                    yield dut.ports["reset"].eq(1)
                    yield Tick()
                    yield Settle()
                    self.assertTrue(outputs)
                    for name in outputs:
                        self.assertIsNotNone((yield dut.ports[name]))

                simulator = Simulator(dut)
                simulator.add_clock(1e-6)
                simulator.add_process(process)
                simulator.run()
