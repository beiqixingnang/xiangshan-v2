"""Direct simulation tests for the V2 utility delay family.
V2 实用延迟族的直接仿真测试。
"""

from __future__ import annotations

from collections.abc import Mapping
import importlib.util
import json
import random
import sys
import unittest
from pathlib import Path
from typing import Any

from amaranth.sim import Delay, Simulator


# =============================================================================
# Module Contract
# =============================================================================
MEMBER_PROFILES: dict[str, tuple[str, int]] = {
    "DelayN": ("plain", 1), "DelayN_1": ("plain", 2),
    "DelayN_13": ("plain", 1), "DelayN_15": ("plain", 4),
    "DelayN_17": ("plain", 5), "DelayN_208": ("plain", 5),
    "DelayN_214": ("plain", 2), "DelayN_215": ("plain", 2),
    "DelayN_220": ("plain", 1), "DelayN_221": ("plain", 1),
    "DelayN_225": ("plain", 0), "DelayN_297": ("plain", 3),
    "DelayN_331": ("plain", 10), "DelayN_333": ("plain", 2),
    "DelayN_334": ("plain", 5), "DelayN_7": ("plain", 2),
    "DelayN_8": ("plain", 2), "DelayN_9": ("plain", 2),
    "DelayNWithValid": ("valid", 2), "DelayNWithValid_1": ("valid", 2),
    "DelayNWithValid_103": ("valid", 1), "DelayNWithValid_152": ("valid", 1),
    "DelayNWithValid_155": ("valid", 1), "DelayNWithValid_2": ("valid", 2),
    "DelayNWithValid_200": ("valid", 2), "DelayNWithValid_202": ("valid", 1),
    "DelayNWithValid_203": ("valid", 1), "DelayNWithValid_3": ("valid", 2),
    "DelayNWithValid_4": ("valid", 0), "DelayNWithValid_52": ("valid", 1),
    "DelayNWithValid_55": ("valid", 1), "DelayNWithValid_7": ("valid", 0),
    "DelayReg": ("enabled", 3), "DelayReg_8": ("enabled", 2),
    "DelayReg_10": ("enabled", 2), "DelayReg_11": ("enabled", 2),
    "DelayReg_12": ("enabled", 2), "DelayReg_13": ("enabled", 2),
    "DelayReg_14": ("enabled", 3), "DelayReg_15": ("enabled", 4),
    "PipeWithFlush": ("pipe", 0), "PipeWithFlush_1": ("pipe", 2),
    "PipeWithFlush_6": ("pipe", 1), "PipeWithFlush_7": ("pipe", 2),
    "PipeWithFlush_8": ("pipe", 0), "PipeWithFlush_9": ("pipe", 3),
    "PipeWithFlush_10": ("pipe", 1), "PipeWithFlush_11": ("pipe", 3),
}


# =============================================================================
# Fixtures And Support
# =============================================================================
TEST_ID = "Build-Cpu.Dependency.Utility.DelayFamily"
SUBJECT_TYPE = "build"
SUBJECT_ID = "Build-Cpu.Dependency.Utility.DelayFamily"
DIRECT = True

ROOT = Path(__file__).resolve().parents[4]
BUILD_PATH = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Cpu-Core-Dependency.Utility.DelayFamily-Hardware.py"
)
LOCKED_HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"


def load_subject() -> Any:
    spec = importlib.util.spec_from_file_location("testing_utility_delay_family", BUILD_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(BUILD_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_locked_hierarchy() -> dict[str, Any]:
    payload = json.loads(LOCKED_HIERARCHY.read_text(encoding="utf-8"))
    return payload["modules"]


def port_width(port: dict[str, Any]) -> int:
    width = str(port.get("width", ""))
    if not width:
        return 1
    left, right = (int(value) for value in width[1:-1].split(":"))
    return abs(left - right) + 1


def width_mask(width: int) -> int:
    return (1 << width) - 1


def value_for(seed: int, cycle: int, port_index: int, width: int) -> int:
    rng = random.Random(seed + cycle * 0x9E3779B1 + port_index * 0x85EBCA77)
    return rng.getrandbits(width)


def initialized_value(value: int | None) -> int:
    if value is None:
        raise AssertionError("a valid pipeline stage must have initialized payload")
    return value


def pipe_flush_model(configuration: Any, stage: int,
                     previous: Mapping[str, int | None], controls: dict[str, int]) -> bool:
    role = configuration.pipe_flush
    if role is None:
        return False
    redirect_flush = False
    if (all((role.enq_rob_flag, role.enq_rob_value, role.redirect_valid,
             role.redirect_rob_flag, role.redirect_rob_value, role.redirect_level))
            and controls[role.redirect_valid]):
        pointer_flag = initialized_value(previous[role.enq_rob_flag])
        pointer_value = initialized_value(previous[role.enq_rob_value])
        redirect_flag = controls[role.redirect_rob_flag]
        redirect_value = controls[role.redirect_rob_value]
        same = pointer_flag == redirect_flag and pointer_value == redirect_value
        after = (pointer_flag ^ redirect_flag) ^ int(pointer_value > redirect_value)
        redirect_flush = bool(controls[role.redirect_valid]) and (
            (bool(controls[role.redirect_level]) and same) or bool(after)
        )
    load_cancel = False
    for dependency_name, pair in zip(role.load_dependencies,
                                      role.load_cancel_pairs, strict=False):
        ld1_name, ld2_name = pair
        if ld1_name is not None and controls[ld1_name]:
            dependency = initialized_value(previous[dependency_name])
            load_cancel |= bool(dependency & 1)
        if ld2_name is not None and controls[ld2_name]:
            dependency = initialized_value(previous[dependency_name])
            load_cancel |= bool((dependency >> 1) & 1)
    og_fail = bool(controls[role.og0_fail]) if stage == 1 and role.og0_fail else False
    og_fail |= bool(controls[role.og1_fail]) if stage == 2 and role.og1_fail else False
    return redirect_flush or load_cancel or og_fail


def simulate_member(test_case: unittest.TestCase, module: Any,
                    member_name: str, configuration: Any, member_index: int) -> None:
    dut = module.DelayFamily(configuration)
    rng_seed = 0xD31A0000 + member_index
    field_names = [field.input_name for field in configuration.data_fields]
    stages = configuration.stages
    cycle_count = max(6, stages + 5)
    data_state: list[dict[str, int | None]] = [
        {name: (0 if configuration.mode == "enabled" else None) for name in field_names}
        for _ in range(stages)
    ]
    valid_state: list[int | None] = [
        (0 if configuration.reset_name is not None or configuration.mode == "pipe" else None)
        for _ in range(stages)
    ]

    async def bench(context: Any) -> None:
        clock_name = configuration.clock_name
        reset_name = configuration.reset_name
        if clock_name:
            context.set(dut.inputs[clock_name], 0)
        if reset_name:
            context.set(dut.inputs[reset_name], 1)
            await context.delay(1e-9)
            context.set(dut.inputs[reset_name], 0)
            await context.delay(1e-9)

        for cycle in range(cycle_count):
            data_values = {
                field.input_name: value_for(rng_seed, cycle, index, field.width)
                for index, field in enumerate(configuration.data_fields)
            }
            controls: dict[str, int] = {}
            for index, port in enumerate(configuration.control_inputs):
                name = port.name
                if name in (clock_name, reset_name):
                    value = 0
                elif name == configuration.valid_input_name:
                    value = int(cycle <= stages + 1 or (cycle + member_index) % 5 != 0)
                elif name == configuration.enable_name:
                    value = int(cycle <= stages + 1 or (cycle + member_index) % 4 != 2)
                elif configuration.mode == "pipe" and cycle <= stages + 1 and name.startswith("io_flush_"):
                    value = 0
                else:
                    value = value_for(rng_seed ^ 0xA5A5, cycle, index, port.width)
                controls[name] = value
                context.set(dut.inputs[name], value)
            for field in configuration.data_fields:
                context.set(dut.inputs[field.input_name], data_values[field.input_name])
            await context.delay(1e-9)

            old_data = [dict(row) for row in data_state]
            old_valid = list(valid_state)
            if configuration.mode == "plain":
                for stage in range(stages):
                    for field in configuration.data_fields:
                        data_state[stage][field.input_name] = (
                            data_values[field.input_name] if stage == 0
                            else old_data[stage - 1][field.input_name]
                        )
            elif configuration.mode == "valid":
                previous_valid = controls.get(configuration.valid_input_name, 0)
                for stage in range(stages):
                    if previous_valid:
                        for field in configuration.data_fields:
                            data_state[stage][field.input_name] = (
                                data_values[field.input_name] if stage == 0
                                else old_data[stage - 1][field.input_name]
                            )
                    valid_state[stage] = previous_valid
                    if stage + 1 < stages:
                        previous_valid = old_valid[stage] or 0
            elif configuration.mode == "enabled":
                if controls.get(configuration.enable_name, 1):
                    for stage in range(stages):
                        for field in configuration.data_fields:
                            data_state[stage][field.input_name] = (
                                data_values[field.input_name] if stage == 0
                                else old_data[stage - 1][field.input_name]
                            )
            else:
                input_valid = controls.get(configuration.valid_input_name, 0)
                for stage in range(stages):
                    previous_valid = input_valid if stage == 0 else (old_valid[stage - 1] or 0)
                    previous_data = data_values if stage == 0 else old_data[stage - 1]
                    kill = stage > 0 and bool(previous_valid) and pipe_flush_model(
                        configuration, stage, previous_data, controls
                    )
                    valid_state[stage] = int(bool(previous_valid) and not kill)
                    if previous_valid:
                        for field in configuration.data_fields:
                            value = initialized_value(previous_data[field.input_name])
                            if stage > 0 and field.input_name in configuration.pipe_modify_fields:
                                value = (value << 1) & width_mask(field.width)
                            data_state[stage][field.input_name] = value

            if clock_name:
                context.set(dut.inputs[clock_name], 1)
                await context.delay(1e-9)

            expected_data = (dict(data_values) if stages == 0 else data_state[-1])
            expected_valid = (
                controls.get(configuration.valid_input_name, 0)
                if stages == 0 else valid_state[-1]
            )
            for field in configuration.data_fields:
                expected = expected_data[field.input_name]
                if expected is not None:
                    observed = context.get(dut.outputs[field.output_name])
                    test_case.assertEqual(
                        observed, expected,
                        f"{member_name} cycle={cycle} output={field.output_name}",
                    )
            if configuration.valid_output_name is not None and expected_valid is not None:
                observed_valid = context.get(dut.outputs[configuration.valid_output_name])
                test_case.assertEqual(
                    observed_valid, expected_valid,
                    f"{member_name} cycle={cycle} output={configuration.valid_output_name}",
                )
            if clock_name:
                context.set(dut.inputs[clock_name], 0)
                await context.delay(1e-9)

    simulator = Simulator(dut)
    simulator.add_testbench(bench)
    simulator.run()


# =============================================================================
# Subject Contract
# =============================================================================
class BuildSubjectContractTest(unittest.TestCase):
    def test_subject_contract(self) -> None:
        self.assertEqual(TEST_ID, SUBJECT_ID)
        self.assertEqual(SUBJECT_TYPE, "build")
        self.assertIs(DIRECT, True)
        module = load_subject()
        self.assertEqual(set(module.MEMBER_NAMES), set(MEMBER_PROFILES))
        self.assertEqual(module.COVERED_MODULES, module.MEMBER_NAMES)
        self.assertEqual(module.IMPLEMENTED_MEMBERS, module.COVERED_MODULES)
        self.assertEqual(module.CONTRACT_ONLY_MEMBERS, ())
        self.assertEqual(module.__all__, [
            "DelayPort", "DelayField", "PipeFlushConfig", "DelayFamilyConfig",
            "DelayFamily", "MEMBER_NAMES", "COVERED_MODULES",
            "IMPLEMENTED_MEMBERS", "CONTRACT_ONLY_MEMBERS",
            "family_configuration", "build_verilog", "main",
        ])
        rtl = module.build_verilog({"module": "DelayN_13"}, {})
        self.assertIn("module DelayN_13", rtl)
        self.assertEqual(rtl, module.build_verilog({"module": "DelayN_13"}, {}))


# =============================================================================
# Behavior Tests
# =============================================================================
class DelayFamilyBehaviorTests(unittest.TestCase):
    def test_all_locked_member_interfaces(self) -> None:
        module = load_subject()
        hierarchy = load_locked_hierarchy()
        self.assertEqual(len(MEMBER_PROFILES), 48)
        self.assertEqual(set(MEMBER_PROFILES), set(module.MEMBER_NAMES))
        for member_name, (mode, stages) in MEMBER_PROFILES.items():
            configuration = module.family_configuration(member_name)
            self.assertEqual((configuration.mode, configuration.stages), (mode, stages))
            actual = {
                (port.name, "input", port.width)
                for port in configuration.control_inputs
            } | {
                (field.input_name, "input", field.width)
                for field in configuration.data_fields
            } | {
                (port.name, "output", port.width)
                for port in configuration.control_outputs
            } | {
                (field.output_name, "output", field.width)
                for field in configuration.data_fields
            }
            expected = {
                (port["name"], port["direction"], port_width(port))
                for port in hierarchy[member_name]["ports"]
            }
            self.assertEqual(actual, expected, member_name)

    def test_all_locked_member_behaviors(self) -> None:
        module = load_subject()
        for member_index, (member_name, (mode, stages)) in enumerate(MEMBER_PROFILES.items()):
            with self.subTest(member=member_name, mode=mode, stages=stages):
                configuration = module.family_configuration(member_name)
                simulate_member(self, module, member_name, configuration, member_index)
