"""Reusable bounded tests for the UHSC V2 PMP family."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any

from amaranth.sim import Simulator

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Cpu-Core-Backend.Fu.PMP.Family-Hardware.py"


def load_subject() -> Any:
    spec = importlib.util.spec_from_file_location("testing_pmp_family", TARGET)
    if spec is None or spec.loader is None: raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); return module


class PMPFamilyTest(unittest.TestCase):
    def test_all_members_export(self) -> None:
        module = load_subject()
        for member in module.COVERED_MODULES: self.assertIn(f"module {member}", module.build_verilog({"module": member}, {}))

    def test_checker_2_permissions_priority_and_valid_hold(self) -> None:
        module = load_subject()
        subject = module.PMPFamily("PMPChecker_2")
        napot_mask = 0

        async def bench(context: Any) -> None:
            for name, direction, _width in subject.specs:
                if direction == "input" and name != "clock":
                    context.set(subject.ports[name], 0)
            for prefix in ("pmp", "pma"):
                context.set(subject.ports[f"io_check_env_{prefix}_0_cfg_a"], 3)
                context.set(subject.ports[f"io_check_env_{prefix}_0_addr"], 0x40000)
                context.set(subject.ports[f"io_check_env_{prefix}_0_mask"], napot_mask)
            context.set(subject.ports["io_req_bits_addr"], 0x40000)
            context.set(subject.ports["io_check_env_pmp_0_cfg_l"], 1)
            context.set(subject.ports["io_check_env_pmp_0_cfg_x"], 0)
            context.set(subject.ports["io_check_env_pma_0_cfg_x"], 1)
            context.set(subject.ports["io_check_env_pma_0_cfg_c"], 1)
            context.set(subject.ports["io_req_valid"], 1)
            await context.tick()
            await context.delay(1e-9)
            self.assertEqual(context.get(subject.ports["io_resp_instr"]), 1)
            self.assertEqual(context.get(subject.ports["io_resp_mmio"]), 1)

            context.set(subject.ports["io_req_bits_addr"], 0x100000)
            await context.tick()
            await context.delay(1e-9)
            self.assertEqual(context.get(subject.ports["io_resp_instr"]), 1)
            self.assertEqual(context.get(subject.ports["io_resp_mmio"]), 0)

            context.set(subject.ports["io_check_env_pmp_0_cfg_x"], 1)
            await context.tick()
            await context.delay(1e-9)
            self.assertEqual(context.get(subject.ports["io_resp_instr"]), 0)
            self.assertEqual(context.get(subject.ports["io_resp_mmio"]), 0)

            context.set(subject.ports["io_req_valid"], 0)
            context.set(subject.ports["io_check_env_pmp_0_cfg_x"], 0)
            context.set(subject.ports["io_check_env_pma_0_cfg_c"], 0)
            await context.tick()
            await context.delay(1e-9)
            self.assertEqual(context.get(subject.ports["io_resp_instr"]), 0)
            self.assertEqual(context.get(subject.ports["io_resp_mmio"]), 0)

            context.set(subject.ports["io_req_valid"], 1)
            await context.tick()
            await context.delay(1e-9)
            self.assertEqual(context.get(subject.ports["io_resp_instr"]), 1)
            self.assertEqual(context.get(subject.ports["io_resp_mmio"]), 1)

            context.set(subject.ports["io_check_env_mode"], 3)
            context.set(subject.ports["io_check_env_pmp_0_cfg_l"], 0)
            context.set(subject.ports["io_check_env_pma_0_cfg_x"], 1)
            context.set(subject.ports["io_check_env_pma_0_cfg_c"], 1)
            await context.tick()
            await context.delay(1e-9)
            self.assertEqual(context.get(subject.ports["io_resp_instr"]), 0)
            self.assertEqual(context.get(subject.ports["io_resp_mmio"]), 0)

            context.set(subject.ports["io_check_env_mode"], 0)
            context.set(subject.ports["io_check_env_pmp_0_cfg_l"], 1)
            context.set(subject.ports["io_check_env_pmp_0_cfg_x"], 0)
            context.set(subject.ports["io_check_env_pmp_1_cfg_a"], 3)
            context.set(subject.ports["io_check_env_pmp_1_addr"], 0x40000)
            context.set(subject.ports["io_check_env_pmp_1_mask"], napot_mask)
            context.set(subject.ports["io_check_env_pmp_1_cfg_l"], 1)
            context.set(subject.ports["io_check_env_pmp_1_cfg_x"], 1)
            await context.tick()
            await context.delay(1e-9)
            self.assertEqual(context.get(subject.ports["io_resp_instr"]), 1)

            context.set(subject.ports["io_check_env_pmp_0_cfg_a"], 0)
            await context.tick()
            await context.delay(1e-9)
            self.assertEqual(context.get(subject.ports["io_resp_instr"]), 0)

            context.set(subject.ports["io_check_env_pma_0_cfg_x"], 0)
            await context.tick()
            await context.delay(1e-9)
            self.assertEqual(context.get(subject.ports["io_resp_instr"]), 1)

        simulator = Simulator(subject)
        simulator.add_clock(1e-6)
        simulator.add_testbench(bench)
        simulator.run()


if __name__ == "__main__": unittest.main()
