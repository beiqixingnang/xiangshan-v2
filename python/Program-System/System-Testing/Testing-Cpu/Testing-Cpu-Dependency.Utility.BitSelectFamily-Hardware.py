"""Direct behavioral checks for the combinational bit-select utility family."""

from __future__ import annotations

import importlib.util
import json
import random
import sys
import unittest
from pathlib import Path
from typing import Any

from amaranth.sim import Simulator


# =============================================================================
# Module Contract
# =============================================================================
"""The four direct tests cover the locked mux and bit-selection behaviors."""

# =============================================================================
# Fixtures And Support
# =============================================================================
TEST_ID = "Build-Cpu.Dependency.Utility.BitSelectFamily"
SUBJECT_TYPE = "build"
SUBJECT_ID = "Build-Cpu.Dependency.Utility.BitSelectFamily"
DIRECT = True

ROOT = Path(__file__).resolve().parents[4]
BUILD_PATH = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Cpu-Core-Dependency.Utility.BitSelectFamily-Hardware.py"
)
LOCKED_HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
MEMBER_NAMES = (
    "PriorityMuxModule",
    "PriorityMuxModule_4",
    "PriorityMuxModule_8",
    "PriorityMuxModule_12",
    "PriorityMuxModule_16",
    "PriorityMuxModule_20",
    "UIntCompressor_27_000011100000000000001010101",
    "UIntCompressor_27_000000000000001010100000000",
    "UIntExtractor_27_000011100000000000001010101",
    "UIntExtractor_27_000000000000001010100000000",
)

PRIORITY_SOURCE_LAYOUT: dict[str, tuple[tuple[str | None, str], ...]] = {
    "PriorityMuxModule": (
        ("s2_target_sel", "s2_target_src"),
        ("s1_target_sel", "s1_target_src"),
        ("s3_target_sel", "s3_target_src"),
        ("redirect_target_sel", "redirect_target_src"),
        (None, "stallPC_src"),
    ),
    "PriorityMuxModule_4": (
        ("s2_FGH_sel", "s2_FGH_src_"),
        ("s1_FGH_sel", "s1_FGH_src_"),
        ("s3_FGH_sel", "s3_FGH_src_"),
        ("redirect_FGHT_sel", "redirect_FGHT_src_"),
        (None, "stallFGH_src_"),
    ),
    "PriorityMuxModule_8": (
        ("s2_GHPtr_sel", "s2_GHPtr_src_"),
        ("s1_GHPtr_sel", "s1_GHPtr_src_"),
        ("s3_GHPtr_sel", "s3_GHPtr_src_"),
        ("redirect_GHPtr_sel", "redirect_GHPtr_src_"),
        (None, "stallGHPtr_src_"),
    ),
    "PriorityMuxModule_12": (
        ("s2_AFHOB_sel", "s2_AFHOB_src_"),
        ("s1_AFHOB_sel", "s1_AFHOB_src_"),
        ("s3_AFHOB_sel", "s3_AFHOB_src_"),
        ("redirect_AFHOB_sel", "redirect_AFHOB_src_"),
        (None, "stallAFHOB_src_"),
    ),
    "PriorityMuxModule_16": (
        ("s2_BrNumOH_sel", "s2_BrNumOH_src"),
        ("s1_BrNumOH_sel", "s1_BrNumOH_src"),
        ("s3_BrNumOH_sel", "s3_BrNumOH_src"),
        ("redirect_BrNumOH_sel", "redirect_BrNumOH_src"),
        (None, "stallBrNumOH_src"),
    ),
    "PriorityMuxModule_20": (
        ("s2_new_bit_0_sel", "s2_new_bit_0_src"),
        ("s1_new_bit_0_sel", "s1_new_bit_0_src"),
        ("s3_new_bit_0_sel", "s3_new_bit_0_src"),
        (None, "redirect_new_bit_0_src"),
    ),
}


def load_subject() -> Any:
    spec = importlib.util.spec_from_file_location("testing_bitselect_family_build", BUILD_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(BUILD_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_locked_hierarchy() -> dict[str, Any]:
    payload = json.loads(LOCKED_HIERARCHY.read_text(encoding="utf-8"))
    return payload["modules"]


def locked_width(port: dict[str, Any]) -> int:
    width = str(port.get("width", ""))
    if not width:
        return 1
    left, right = (int(value) for value in width[1:-1].split(":"))
    return abs(left - right) + 1


def bit_mask(width: int) -> int:
    return (1 << width) - 1


# =============================================================================
# Subject Contract
# =============================================================================
class BitSelectFamilySubjectContract:
    """Load the finite Build API and its exact locked interface authority."""

    def __init__(self) -> None:
        self.module = load_subject()
        self.locked_modules = load_locked_hierarchy()

    def subject(self, member_name: str) -> Any:
        return self.module.BitSelectFamily(member_name)

    def expected_port_map(self, member_name: str) -> dict[str, tuple[str, int]]:
        return {
            port["name"]: (port["direction"], locked_width(port))
            for port in self.locked_modules[member_name]["ports"]
        }

    def output_suffix(self, output_name: str) -> str:
        if output_name == "out_res":
            return ""
        return output_name.removeprefix("out_res_")


# =============================================================================
# Behavior Tests
# =============================================================================
class BitSelectFamilyBehavior:
    """Independent finite input patterns and bit mapping expectations."""

    def __init__(self, test_case: unittest.TestCase,
                 contract: BitSelectFamilySubjectContract) -> None:
        self.test_case = test_case
        self.contract = contract

    def check_priority_member(self, member_name: str) -> None:
        subject = self.contract.subject(member_name)
        sources = PRIORITY_SOURCE_LAYOUT[member_name]
        locked_ports = self.contract.locked_modules[member_name]["ports"]
        output_ports = [port for port in locked_ports if port["direction"] == "output"]
        selectable_sources = [(selector, prefix) for selector, prefix in sources
                              if selector is not None]
        pattern_count = 1 << len(selectable_sources)

        async def bench(context: Any) -> None:
            for pattern in range(pattern_count):
                assigned: dict[str, int] = {}
                for selector_index, (selector, _prefix) in enumerate(selectable_sources):
                    value = (pattern >> selector_index) & 1
                    context.set(subject.inputs[selector], value)
                    assigned[selector] = value
                for source_index, (_selector, prefix) in enumerate(sources):
                    for output_index, port in enumerate(output_ports):
                        suffix = self.contract.output_suffix(port["name"])
                        input_name = prefix + suffix
                        width = locked_width(port)
                        rng = random.Random(
                            0xB175E1EC + pattern * 0x9E3779B1
                            + source_index * 0x85EBCA77 + output_index * 0xC2B2AE3D
                        )
                        value = rng.getrandbits(width)
                        context.set(subject.inputs[input_name], value)
                        assigned[input_name] = value
                await context.delay(1e-8)
                winner = next(
                    (index for index, (selector, _prefix) in enumerate(sources[:-1])
                     if assigned[selector]),
                    len(sources) - 1,
                )
                for port in output_ports:
                    suffix = self.contract.output_suffix(port["name"])
                    expected = assigned[sources[winner][1] + suffix]
                    self.test_case.assertEqual(
                        context.get(subject.outputs[port["name"]]), expected,
                        f"{member_name}.{port['name']} at select pattern {pattern}",
                    )

        simulator = Simulator(subject)
        simulator.add_testbench(bench)
        simulator.run()

    def check_compressor(self, member_name: str) -> None:
        subject = self.contract.subject(member_name)
        locked_ports = self.contract.locked_modules[member_name]["ports"]
        input_width = next(locked_width(port) for port in locked_ports
                           if port["direction"] == "input")
        output_width = next(locked_width(port) for port in locked_ports
                            if port["direction"] == "output")
        mask = member_name.rsplit("_", 1)[1]
        selected_bits = tuple(index for index, selected in enumerate(reversed(mask))
                              if selected == "1")
        expected_positions = {source: output for output, source in enumerate(selected_bits)}

        async def bench(context: Any) -> None:
            vectors = [1 << bit for bit in range(input_width)]
            vectors.extend((0, bit_mask(input_width), 0x0524912D & bit_mask(input_width)))
            for value in vectors:
                context.set(subject.inputs["io_in"], value)
                await context.delay(1e-8)
                expected = 0
                for source_bit, output_bit in expected_positions.items():
                    expected |= ((value >> source_bit) & 1) << output_bit
                self.test_case.assertEqual(
                    context.get(subject.outputs["io_out"]) & bit_mask(output_width),
                    expected,
                    f"{member_name} input {value:#x}",
                )

        simulator = Simulator(subject)
        simulator.add_testbench(bench)
        simulator.run()

    def check_extractor(self, member_name: str) -> None:
        subject = self.contract.subject(member_name)
        locked_ports = self.contract.locked_modules[member_name]["ports"]
        input_width = next(locked_width(port) for port in locked_ports
                           if port["direction"] == "input")
        output_width = next(locked_width(port) for port in locked_ports
                            if port["direction"] == "output")
        mask = member_name.rsplit("_", 1)[1]
        selected_bits = tuple(index for index, selected in enumerate(reversed(mask))
                              if selected == "1")

        async def bench(context: Any) -> None:
            for value in range(1 << input_width):
                context.set(subject.inputs["io_in"], value)
                await context.delay(1e-8)
                expected = sum(
                    ((value >> input_bit) & 1) << destination_bit
                    for input_bit, destination_bit in enumerate(selected_bits)
                )
                self.test_case.assertEqual(
                    context.get(subject.outputs["io_out"]) & bit_mask(output_width),
                    expected,
                    f"{member_name} input {value:#x}",
                )

        simulator = Simulator(subject)
        simulator.add_testbench(bench)
        simulator.run()


class TestBitSelectFamily(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = BitSelectFamilySubjectContract()
        self.behavior = BitSelectFamilyBehavior(self, self.contract)

    def test_exact_member_catalog_and_locked_abi(self) -> None:
        self.assertEqual(self.contract.module.COVERED_MODULES, MEMBER_NAMES)
        self.assertEqual(self.contract.module.IMPLEMENTED_MEMBERS, MEMBER_NAMES)
        self.assertEqual(self.contract.module.CONTRACT_ONLY_MEMBERS, ())
        self.assertEqual(set(self.contract.module.COVERED_MODULES),
                         set(self.contract.module.IMPLEMENTED_MEMBERS))
        for member_name in MEMBER_NAMES:
            subject = self.contract.subject(member_name)
            Simulator(subject)
            actual = {
                **{name: ("input", len(signal)) for name, signal in subject.inputs.items()},
                **{name: ("output", len(signal)) for name, signal in subject.outputs.items()},
            }
            self.assertEqual(actual, self.contract.expected_port_map(member_name), member_name)

    def test_priority_muxes_cover_every_selector_pattern(self) -> None:
        for member_name in PRIORITY_SOURCE_LAYOUT:
            with self.subTest(member=member_name):
                self.behavior.check_priority_member(member_name)

    def test_compressors_select_the_locked_source_bits(self) -> None:
        for member_name in MEMBER_NAMES:
            if member_name.startswith("UIntCompressor_"):
                with self.subTest(member=member_name):
                    self.behavior.check_compressor(member_name)

    def test_extractors_place_selected_bits_and_zero_fill(self) -> None:
        for member_name in MEMBER_NAMES:
            if member_name.startswith("UIntExtractor_"):
                with self.subTest(member=member_name):
                    self.behavior.check_extractor(member_name)
