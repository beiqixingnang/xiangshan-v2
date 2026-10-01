"""Reusable bounded tests for the UHSC V2 PMP family."""

from __future__ import annotations

import importlib.util
import json
import re
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
    def test_locked_member_catalog_and_abi(self) -> None:
        module = load_subject()
        hierarchy = json.loads((ROOT / "validation/v2-locked-hierarchy.json").read_text(encoding="utf-8"))["modules"]
        for member in module.COVERED_MODULES:
            expected = []
            for port in hierarchy[member]["ports"]:
                limits = re.fullmatch(r"\[(\d+):(\d+)\]", str(port.get("width", "")))
                width = abs(int(limits[1]) - int(limits[2])) + 1 if limits else 1
                expected.append((port["name"], port["direction"], width))
            self.assertEqual(tuple(expected), module.PORT_SPECS[member], member)

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

    def test_entry_handle_csr_write_lock_and_readback(self) -> None:
        module = load_subject()
        subject = module.PMPFamily("PMPEntryHandleModule")
        ports = subject.ports
        address_mask = (1 << 46) - 1
        written_addresses = [
            (0x123456789ABC + index * 0x12345) & address_mask
            for index in range(32)
        ]

        async def bench(context: Any) -> None:
            for name, direction, _width in subject.specs:
                if direction == "input" and name != "clock":
                    context.set(ports[name], 0)

            context.set(ports["reset"], 1)
            await context.delay(1e-9)
            for index in range(32):
                self.assertEqual(context.get(ports[f"io_out_pmpAddrRData_{index}"]), 0)
            context.set(ports["reset"], 0)
            await context.delay(1e-9)

            # Every CSR address writes its own state, and the unselected read
            # outputs expose all 32 full address values.
            context.set(ports["io_in_wen"], 1)
            for index, value in enumerate(written_addresses):
                context.set(ports["io_in_addr"], 0x3B0 + index)
                context.set(ports["io_in_wdata"], value)
                await context.tick()
            context.set(ports["io_in_wen"], 0)
            context.set(ports["io_in_ren"], 0)
            await context.delay(1e-9)
            for index, value in enumerate(written_addresses):
                self.assertEqual(context.get(ports[f"io_out_pmpAddrRData_{index}"]), value)

            # Only the selected read is WARL-aligned: TOR/off clears ten
            # low bits at 4 KiB grain; A[1] sets the low nine bits.
            context.set(ports["io_in_ren"], 1)
            context.set(ports["io_in_addr"], 0x3B0)
            context.set(ports["io_in_pmpCfg_0_A"], 0)
            await context.delay(1e-9)
            self.assertEqual(
                context.get(ports["io_out_pmpAddrRData_0"]),
                written_addresses[0] & ~0x3FF,
            )
            self.assertEqual(
                context.get(ports["io_out_pmpAddrRData_1"]), written_addresses[1]
            )
            context.set(ports["io_in_pmpCfg_0_A"], 2)
            await context.delay(1e-9)
            self.assertEqual(
                context.get(ports["io_out_pmpAddrRData_0"]),
                (written_addresses[0] & ~0x1FF) | 0x1FF,
            )
            context.set(ports["io_in_ren"], 0)
            await context.delay(1e-9)
            self.assertEqual(
                context.get(ports["io_out_pmpAddrRData_0"]), written_addresses[0]
            )

            # Writes require wen, the entry's own L bit to be clear, and no
            # following locked TOR entry.
            context.set(ports["io_in_wen"], 0)
            context.set(ports["io_in_addr"], 0x3B2)
            context.set(ports["io_in_wdata"], 0x23456789ABCD)
            await context.tick()
            context.set(ports["io_in_wen"], 0)
            await context.delay(1e-9)
            self.assertEqual(
                context.get(ports["io_out_pmpAddrRData_2"]), written_addresses[2]
            )

            context.set(ports["io_in_pmpCfg_0_L"], 1)
            context.set(ports["io_in_addr"], 0x3B0)
            context.set(ports["io_in_wdata"], 0x3456789ABCDE)
            context.set(ports["io_in_wen"], 1)
            await context.tick()
            context.set(ports["io_in_wen"], 0)
            await context.delay(1e-9)
            self.assertEqual(
                context.get(ports["io_out_pmpAddrRData_0"]), written_addresses[0]
            )

            context.set(ports["io_in_pmpCfg_0_L"], 0)
            context.set(ports["io_in_pmpCfg_1_L"], 1)
            context.set(ports["io_in_pmpCfg_1_A"], 1)
            context.set(ports["io_in_wdata"], 0x456789ABCDEF)
            context.set(ports["io_in_wen"], 1)
            await context.tick()
            context.set(ports["io_in_wen"], 0)
            await context.delay(1e-9)
            self.assertEqual(
                context.get(ports["io_out_pmpAddrRData_0"]), written_addresses[0]
            )

            # A locked next entry only blocks its predecessor in TOR mode.
            context.set(ports["io_in_pmpCfg_1_A"], 2)
            context.set(ports["io_in_wdata"], 0x56789ABCDEF0)
            context.set(ports["io_in_wen"], 1)
            await context.tick()
            context.set(ports["io_in_wen"], 0)
            await context.delay(1e-9)
            written_addresses[0] = 0x56789ABCDEF0 & address_mask
            self.assertEqual(
                context.get(ports["io_out_pmpAddrRData_0"]), written_addresses[0]
            )

            context.set(ports["io_in_pmpCfg_31_L"], 1)
            context.set(ports["io_in_addr"], 0x3CF)
            context.set(ports["io_in_wdata"], 0x2789ABCDEF01)
            context.set(ports["io_in_wen"], 1)
            await context.tick()
            context.set(ports["io_in_wen"], 0)
            await context.delay(1e-9)
            self.assertEqual(
                context.get(ports["io_out_pmpAddrRData_31"]), written_addresses[31]
            )

            # The configuration writeback selects the four implemented CSR
            # addresses, canonicalizes W and A, and preserves locked bytes.
            for index in range(32):
                for field in ("R", "W", "X", "A", "L"):
                    context.set(ports[f"io_in_pmpCfg_{index}_{field}"], 0)
            context.set(ports["io_in_pmpCfg_1_R"], 1)
            context.set(ports["io_in_pmpCfg_1_X"], 1)
            context.set(ports["io_in_pmpCfg_1_A"], 2)
            context.set(ports["io_in_pmpCfg_1_L"], 1)
            context.set(ports["io_in_addr"], 0x3A0)
            context.set(ports["io_in_wdata"], (0x62 << 16) | (0xC3 << 8) | 0x10)
            context.set(ports["io_in_wen"], 1)
            await context.delay(1e-9)
            self.assertEqual(context.get(ports["io_out_pmpCfgWData"]), 0x00609518)

            context.set(ports["io_in_wen"], 0)
            await context.delay(1e-9)
            self.assertEqual(context.get(ports["io_out_pmpCfgWData"]), 0)
            context.set(ports["io_in_wen"], 1)
            context.set(ports["io_in_addr"], 0x3A6)
            context.set(ports["io_in_wdata"], 0xC3 << 56)
            await context.delay(1e-9)
            self.assertEqual(
                context.get(ports["io_out_pmpCfgWData"]), 0xC3 << 56
            )
            context.set(ports["io_in_addr"], 0x3A1)
            await context.delay(1e-9)
            self.assertEqual(context.get(ports["io_out_pmpCfgWData"]), 0)

            # Asynchronous reset clears the public address state.
            context.set(ports["io_in_wen"], 0)
            context.set(ports["reset"], 1)
            await context.delay(1e-9)
            for index in range(32):
                self.assertEqual(context.get(ports[f"io_out_pmpAddrRData_{index}"]), 0)

        simulator = Simulator(subject)
        simulator.add_clock(1e-6)
        simulator.add_testbench(bench)
        simulator.run()


if __name__ == "__main__": unittest.main()
