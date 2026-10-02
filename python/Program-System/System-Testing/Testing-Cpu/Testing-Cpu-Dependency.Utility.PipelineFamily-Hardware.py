"""Direct behavior and ABI checks for elastic and credit pipelines."""

from __future__ import annotations

import importlib.util
import json
import random
import re
import sys
import unittest
from pathlib import Path
from typing import Any

from amaranth.sim import Simulator


# =============================================================================
# Module Contract
# =============================================================================
"""The direct tests cover all owned queue, wrapper, and connect members."""


# =============================================================================
# Fixtures And Support
# =============================================================================
TEST_ID = "Build-Cpu.Dependency.Utility.PipelineFamily"
SUBJECT_TYPE = "build"
SUBJECT_ID = "Build-Cpu.Dependency.Utility.PipelineFamily"
DIRECT = True

AUX_ROOT = Path(__file__).resolve().parents[4]
BUILD_PATH = AUX_ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Cpu-Core-Dependency.Utility.PipelineFamily-Hardware.py"
)
LOCKED_HIERARCHY = AUX_ROOT / "validation/v2-locked-hierarchy.json"

PIPELINE_OUTPUT_CONSTANTS: dict[str, dict[str, int]] = {
    "Pipeline_12": {"needT": 0, "source": 0},
    "Pipeline_14": {
        "channel": 4, "opcode": 0, "size": 6, "source": 0, "off": 0,
        "mask": 0, "bufIdx": 0, "needHint": 0, "isPrefetch": 0,
        "isBop": 0, "preferCache": 0, "dirty": 0, "fromProbeHelper": 0,
        "fromCmoHelper": 1, "needProbeAckData": 0, "reqSource": 0,
    },
}
QUEUE_OUTPUT_CONSTANTS: dict[str, dict[str, int]] = {
    "Queue1_PrefetchReq_1": {"needT": 0, "source": 0},
}


def load_subject() -> Any:
    spec = importlib.util.spec_from_file_location(
        "testing_pipeline_family_build", BUILD_PATH
    )
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


def numeric_suffix(name: str, prefix: str) -> bool:
    return name.startswith(prefix) and name[len(prefix):].isdecimal()


def expected_members(hierarchy: dict[str, Any]) -> set[str]:
    pipeline_roots = {
        name for name in hierarchy
        if name == "Pipeline" or numeric_suffix(name, "Pipeline_")
    }
    connect_roots = {
        name for name in hierarchy
        if numeric_suffix(name, "NewPipelineConnectPipe_")
    }
    queue_children = {
        child["module"]
        for name in pipeline_roots
        for child in hierarchy[name]["children"]
    }
    return pipeline_roots | connect_roots | queue_children


def payload_fields(
    ports: list[dict[str, Any]], direction: str, prefix: str
) -> dict[str, int]:
    return {
        port["name"][len(prefix):]: locked_width(port)
        for port in ports
        if port["direction"] == direction and port["name"].startswith(prefix)
    }


def exported_port_map(verilog_text: str) -> dict[str, tuple[str, int]]:
    declaration = re.compile(
        r"^\s*(input|output)\s+(?:\[(\d+):(\d+)\]\s+)?"
        r"([A-Za-z_$][A-Za-z0-9_$]*)\s*;"
    )
    ports: dict[str, tuple[str, int]] = {}
    for line in verilog_text.splitlines():
        match = declaration.match(line)
        if match is None:
            continue
        direction, left, right, name = match.groups()
        width = abs(int(left) - int(right)) + 1 if left and right else 1
        ports[name] = (direction, width)
    return ports


def drive_zero_inputs(context: Any, subject: Any) -> None:
    for signal in subject.inputs.values():
        context.set(signal, 0)


def reset_design(context: Any, subject: Any) -> None:
    context.set(subject.inputs["clock"], 0)
    context.set(subject.inputs["reset"], 1)


def compare_output_payload(
    test_case: unittest.TestCase,
    context: Any,
    subject: Any,
    outputs: dict[str, int],
    prefix: str,
    expected: dict[str, int],
    member_name: str,
    cycle: int,
) -> None:
    constants = (
        PIPELINE_OUTPUT_CONSTANTS.get(member_name)
        or QUEUE_OUTPUT_CONSTANTS.get(member_name)
        or {}
    )
    for suffix, width in outputs.items():
        observed = context.get(subject.outputs[prefix + suffix])
        if suffix in expected:
            value = expected[suffix]
        else:
            test_case.assertIn(
                suffix, constants,
                f"{member_name}.{suffix} lacks an independent expected source",
            )
            value = constants[suffix]
        test_case.assertEqual(
            observed, value & ((1 << width) - 1),
            f"{member_name}.{prefix + suffix} cycle={cycle}",
        )


def simulate_elastic_member(
    test_case: unittest.TestCase,
    subject: Any,
    hierarchy: dict[str, Any],
    member_name: str,
    *,
    stage_count: int,
    input_valid_name: str,
    input_ready_name: str,
    output_valid_name: str,
    output_ready_name: str,
    input_prefix: str,
    output_prefix: str,
) -> None:
    ports = hierarchy[member_name]["ports"]
    input_payload = payload_fields(ports, "input", input_prefix)
    output_fields = payload_fields(ports, "output", output_prefix)
    data_state: list[dict[str, int]] = [{} for _ in range(stage_count)]
    valid_state = [False] * stage_count
    rng = random.Random(0x510E0000 + sum(map(ord, member_name)))
    schedule = [
        (1, 0), (1, 0), (1, 1), (1, 0), (0, 0), (1, 1),
        (1, 1), (0, 0), (1, 0), (0, 1), (1, 1), (0, 0),
    ]

    async def bench(context: Any) -> None:
        nonlocal valid_state, data_state
        drive_zero_inputs(context, subject)
        reset_design(context, subject)
        await context.delay(1e-9)
        context.set(subject.inputs["clock"], 1)
        await context.delay(1e-9)
        context.set(subject.inputs["clock"], 0)
        context.set(subject.inputs["reset"], 0)
        await context.delay(1e-9)

        for cycle, (input_valid, output_ready) in enumerate(schedule):
            context.set(subject.inputs["clock"], 0)
            context.set(subject.inputs[input_valid_name], input_valid)
            context.set(subject.inputs[output_ready_name], output_ready)
            input_values: dict[str, int] = {}
            for suffix, width in input_payload.items():
                value = rng.getrandbits(width)
                input_values[suffix] = value
                context.set(subject.inputs[input_prefix + suffix], value)
            await context.delay(1e-9)

            downstream_ready = [False] * stage_count
            stage_ready = [False] * stage_count
            next_ready = bool(output_ready)
            for index in range(stage_count - 1, -1, -1):
                downstream_ready[index] = next_ready
                stage_ready[index] = not valid_state[index] or next_ready
                next_ready = stage_ready[index]

            test_case.assertEqual(
                context.get(subject.outputs[output_valid_name]),
                int(valid_state[-1]),
                f"{member_name}.{output_valid_name} cycle={cycle}",
            )
            if input_ready_name in subject.outputs:
                test_case.assertEqual(
                    context.get(subject.outputs[input_ready_name]),
                    int(stage_ready[0]),
                    f"{member_name}.{input_ready_name} cycle={cycle}",
                )
            if valid_state[-1]:
                compare_output_payload(
                    test_case, context, subject, output_fields, output_prefix,
                    data_state[-1], member_name, cycle,
                )

            old_valid = list(valid_state)
            old_data = [dict(row) for row in data_state]
            next_valid = list(old_valid)
            next_data = [dict(row) for row in old_data]
            for index in range(stage_count):
                enqueue_valid = bool(input_valid) if index == 0 else old_valid[index - 1]
                enqueue_fire = enqueue_valid and stage_ready[index]
                dequeue_fire = old_valid[index] and downstream_ready[index]
                next_valid[index] = enqueue_fire or (
                    old_valid[index] and not dequeue_fire
                )
                if enqueue_fire:
                    for suffix, width in output_fields.items():
                        if index == 0:
                            if suffix in input_values:
                                value = input_values[suffix]
                            else:
                                constants = (
                                    PIPELINE_OUTPUT_CONSTANTS.get(member_name)
                                    or QUEUE_OUTPUT_CONSTANTS.get(member_name)
                                    or {}
                                )
                                test_case.assertIn(suffix, constants)
                                value = constants[suffix]
                        else:
                            value = old_data[index - 1][suffix]
                        next_data[index][suffix] = value & ((1 << width) - 1)

            context.set(subject.inputs["clock"], 1)
            await context.delay(1e-9)
            valid_state, data_state = next_valid, next_data
            context.set(subject.inputs["clock"], 0)
            await context.delay(1e-9)

    simulator = Simulator(subject)
    simulator.add_testbench(bench)
    simulator.run()


def simulate_connect_member(
    test_case: unittest.TestCase,
    subject: Any,
    hierarchy: dict[str, Any],
    member_name: str,
) -> None:
    ports = hierarchy[member_name]["ports"]
    input_payload = payload_fields(ports, "input", "io_in_bits_")
    output_fields = payload_fields(ports, "output", "io_out_bits_")
    test_case.assertEqual(input_payload, output_fields, member_name)
    valid_state = False
    data_state: dict[str, int] = {}
    rng = random.Random(0xC011EC7 + sum(map(ord, member_name)))
    schedule = [
        (1, 0, 0, 0, 0), (1, 0, 0, 0, 0), (1, 1, 1, 0, 0),
        (0, 0, 1, 0, 0), (1, 0, 0, 1, 0), (1, 0, 0, 0, 1),
        (0, 1, 0, 0, 0), (1, 1, 0, 0, 0), (0, 0, 0, 0, 0),
        (1, 0, 1, 0, 0), (0, 0, 0, 1, 0), (1, 1, 0, 0, 0),
    ]

    async def bench(context: Any) -> None:
        nonlocal valid_state, data_state
        drive_zero_inputs(context, subject)
        reset_design(context, subject)
        await context.delay(1e-9)
        context.set(subject.inputs["clock"], 1)
        await context.delay(1e-9)
        context.set(subject.inputs["clock"], 0)
        context.set(subject.inputs["reset"], 0)
        await context.delay(1e-9)

        for cycle, (input_valid, output_ready, right_fire, flush, older) in enumerate(schedule):
            context.set(subject.inputs["clock"], 0)
            context.set(subject.inputs["io_in_valid"], input_valid)
            context.set(subject.inputs["io_rightOutFire"], right_fire)
            if "io_out_ready" in subject.inputs:
                context.set(subject.inputs["io_out_ready"], output_ready)
            if "io_isFlush" in subject.inputs:
                context.set(subject.inputs["io_isFlush"], flush)
            if "io_isOlder" in subject.inputs:
                context.set(subject.inputs["io_isOlder"], older)
            input_values: dict[str, int] = {}
            for suffix, width in input_payload.items():
                value = rng.getrandbits(width)
                input_values[suffix] = value
                context.set(subject.inputs["io_in_bits_" + suffix], value)
            await context.delay(1e-9)

            can_accept = (
                bool(output_ready) or not valid_state
                or (bool(older) if "io_isOlder" in subject.inputs else False)
                if "io_out_ready" in subject.inputs
                else True
            )
            input_fire = bool(input_valid) and can_accept
            test_case.assertEqual(
                context.get(subject.outputs["io_out_valid"]),
                int(valid_state),
                f"{member_name}.io_out_valid cycle={cycle}",
            )
            if valid_state:
                compare_output_payload(
                    test_case, context, subject, output_fields,
                    "io_out_bits_", data_state, member_name, cycle,
                )
            if "io_in_ready" in subject.outputs:
                test_case.assertEqual(
                    context.get(subject.outputs["io_in_ready"]),
                    int(can_accept),
                    f"{member_name}.io_in_ready cycle={cycle}",
                )

            next_data = dict(data_state)
            if input_fire:
                next_data = dict(input_values)
            next_valid = input_fire or (valid_state and not bool(right_fire))
            if "io_isFlush" in subject.inputs and flush:
                next_valid = False

            context.set(subject.inputs["clock"], 1)
            await context.delay(1e-9)
            valid_state, data_state = next_valid, next_data
            context.set(subject.inputs["clock"], 0)
            await context.delay(1e-9)

    simulator = Simulator(subject)
    simulator.add_testbench(bench)
    simulator.run()


class PipelineFamilyFixtures:
    """Bind finite builds to the complete locked module and child set."""

    def __init__(self) -> None:
        self.module = load_subject()
        self.hierarchy = load_locked_hierarchy()

    def expected_ports(self, member_name: str) -> dict[str, tuple[str, int]]:
        return {
            port["name"]: (port["direction"], locked_width(port))
            for port in self.hierarchy[member_name]["ports"]
        }


# =============================================================================
# Subject Contract
# =============================================================================
class BuildSubjectContractTest(unittest.TestCase):
    """Check the registered direct subject and all public member contracts."""

    def setUp(self) -> None:
        self.contract = PipelineFamilyFixtures()

    def test_subject_contract(self) -> None:
        module = self.contract.module
        hierarchy = self.contract.hierarchy
        members = tuple(module.COVERED_MODULES)
        self.assertEqual(TEST_ID, SUBJECT_ID)
        self.assertEqual(SUBJECT_TYPE, "build")
        self.assertIs(DIRECT, True)
        self.assertEqual(len(members), 50 + len(module.SOURCE_PIPELINE_MEMBERS))
        self.assertEqual(len(set(members)), len(members))
        self.assertEqual(set(members), expected_members(hierarchy) | set(module.SOURCE_PIPELINE_MEMBERS))
        self.assertEqual(sum(
            name == "Pipeline" or numeric_suffix(name, "Pipeline_")
            for name in members
        ), 16)
        self.assertEqual(sum(
            numeric_suffix(name, "NewPipelineConnectPipe_")
            for name in members
        ), 18)
        self.assertEqual(sum(name.startswith("Queue1_") for name in members), 16)
        self.assertNotIn("NewPipelineConnectPipe", members)
        self.assertEqual(module.IMPLEMENTED_MEMBERS, module.COVERED_MODULES)
        self.assertEqual(module.CONTRACT_ONLY_MEMBERS, ())
        self.assertEqual(module.__all__, [
            "PortSpec", "ElasticMemberConfiguration", "ConnectMemberConfiguration",
            "SourcePipelineConfiguration", "ValidInterface", "CreditedDelay", "SourcePipeline",
            "PipelineFamily", "SOURCE_PIPELINE_MEMBERS", "COVERED_MODULES", "IMPLEMENTED_MEMBERS",
            "CONTRACT_ONLY_MEMBERS", "family_configuration", "build_verilog", "main",
        ])

    def test_all_locked_abis_and_same_name_exports(self) -> None:
        module = self.contract.module
        for member_name in module.COVERED_MODULES:
            if member_name in module.SOURCE_PIPELINE_MEMBERS:
                continue
            with self.subTest(member=member_name):
                first = module.build_verilog({"module": member_name}, {})
                second = module.build_verilog({"module": member_name}, {})
                self.assertEqual(first, second, member_name)
                self.assertIn(f"module {member_name}", first)
                self.assertEqual(
                    exported_port_map(first),
                    self.contract.expected_ports(member_name),
                    member_name,
                )


# =============================================================================
# Behavior Tests
# =============================================================================
class PipelineFamilyBehaviorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = PipelineFamilyFixtures()

    def test_all_standalone_queue_child_behaviors(self) -> None:
        for member_name in sorted(
            name for name in self.contract.module.COVERED_MODULES
            if name.startswith("Queue1_")
        ):
            with self.subTest(member=member_name):
                subject = self.contract.module.PipelineFamily(member_name)
                simulate_elastic_member(
                    self, subject, self.contract.hierarchy, member_name,
                    stage_count=1,
                    input_valid_name="io_enq_valid",
                    input_ready_name="io_enq_ready",
                    output_valid_name="io_deq_valid",
                    output_ready_name="io_deq_ready",
                    input_prefix="io_enq_bits_",
                    output_prefix="io_deq_bits_",
                )

    def test_all_pipeline_wrapper_behaviors(self) -> None:
        for member_name in sorted(
            name for name in self.contract.module.COVERED_MODULES
            if name == "Pipeline" or numeric_suffix(name, "Pipeline_")
        ):
            with self.subTest(member=member_name):
                subject = self.contract.module.PipelineFamily(member_name)
                simulate_elastic_member(
                    self, subject, self.contract.hierarchy, member_name,
                    stage_count=self.contract.hierarchy[member_name]["child_count"],
                    input_valid_name="io_in_valid",
                    input_ready_name="io_in_ready",
                    output_valid_name="io_out_valid",
                    output_ready_name="io_out_ready",
                    input_prefix="io_in_bits_",
                    output_prefix="io_out_bits_",
                )

    def test_all_numbered_connect_stage_behaviors(self) -> None:
        for member_name in sorted(
            name for name in self.contract.module.COVERED_MODULES
            if numeric_suffix(name, "NewPipelineConnectPipe_")
        ):
            with self.subTest(member=member_name):
                subject = self.contract.module.PipelineFamily(member_name)
                simulate_connect_member(
                    self, subject, self.contract.hierarchy, member_name
                )

    def test_multi_width_fifo_split_join_and_equal_width(self) -> None:
        module = self.contract.module
        cases = (
            (16, 8, 8, [0x0100, 0x0302, 0x0504, 0x0706], list(range(8))),
            (8, 16, 4, list(range(8)), [0x0100, 0x0302, 0x0504, 0x0706]),
            (13, 13, 3, [0x11, 0x1337, 0x1001], [0x11, 0x1337, 0x1001]),
        )
        for input_width, output_width, capacity, incoming, expected in cases:
            with self.subTest(input_width=input_width, output_width=output_width):
                configuration = module.SourcePipelineConfiguration(
                    member_name="MultiWidthFifo", input_width=input_width,
                    output_width=output_width, entries=capacity,
                )
                subject = module.SourcePipeline(configuration)

                async def bench(context: Any) -> None:
                    drive_zero_inputs(context, subject)
                    context.set(subject.inputs["reset"], 1)
                    await context.delay(1e-9)
                    context.set(subject.inputs["clock"], 1)
                    await context.delay(1e-9)
                    context.set(subject.inputs["clock"], 0)
                    context.set(subject.inputs["reset"], 0)
                    for value in incoming:
                        context.set(subject.inputs["io_in_valid"], 1)
                        context.set(subject.inputs["io_in_bits"], value)
                        await context.delay(1e-9)
                        self.assertEqual(context.get(subject.outputs["io_in_ready"]), 1)
                        context.set(subject.inputs["clock"], 1)
                        await context.delay(1e-9)
                        context.set(subject.inputs["clock"], 0)
                    context.set(subject.inputs["io_in_valid"], 0)
                    await context.delay(1e-9)
                    self.assertEqual(context.get(subject.outputs["io_count"]), len(expected))
                    for index, value in enumerate(expected):
                        context.set(subject.inputs["io_out_ready"], index % 2)
                        await context.delay(1e-9)
                        self.assertEqual(context.get(subject.outputs["io_out_valid"]), 1)
                        self.assertEqual(context.get(subject.outputs["io_out_bits"]), value)
                        if index % 2 == 0:
                            context.set(subject.inputs["clock"], 1)
                            await context.delay(1e-9)
                            context.set(subject.inputs["clock"], 0)
                            await context.delay(1e-9)
                            self.assertEqual(context.get(subject.outputs["io_out_bits"]), value)
                        context.set(subject.inputs["io_out_ready"], 1)
                        await context.delay(1e-9)
                        context.set(subject.inputs["clock"], 1)
                        await context.delay(1e-9)
                        context.set(subject.inputs["clock"], 0)
                    await context.delay(1e-9)
                    self.assertEqual(context.get(subject.outputs["io_out_valid"]), 0)
                    self.assertEqual(context.get(subject.outputs["io_count"]), 0)

                simulator = Simulator(subject)
                simulator.add_testbench(bench)
                simulator.run()
