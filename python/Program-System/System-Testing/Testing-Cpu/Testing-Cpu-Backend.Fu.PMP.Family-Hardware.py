"""Reusable bounded tests for the UHSC V2 PMP family."""

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

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Cpu-Core-Backend.Fu.PMP.Family-Hardware.py"


def load_subject() -> Any:
    spec = importlib.util.spec_from_file_location("testing_pmp_family", TARGET)
    if spec is None or spec.loader is None: raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); return module


class PMPFamilyTest(unittest.TestCase):
    def test_checker12_command_capture_and_invalid_hold(self) -> None:
        module = load_subject()
        dut = module.PMPFamily("PMPChecker_12")
        p = dut.ports

        async def bench(ctx):
            for name, direction, _width in dut.specs:
                if direction == "input" and name != "clock":
                    ctx.set(p[name], 0)
            ctx.set(p["reset"], 1)
            await ctx.tick()
            ctx.set(p["reset"], 0)
            ctx.set(p["io_req_bits_addr"], 0xABC01230)
            for prefix in ("pmp", "pma"):
                ctx.set(p[f"io_check_env_{prefix}_0_cfg_a"], 3)
                ctx.set(p[f"io_check_env_{prefix}_0_addr"], 0xABC00000 >> 2)
                ctx.set(p[f"io_check_env_{prefix}_0_mask"], (1 << 48) - 1)
                ctx.set(p[f"io_check_env_{prefix}_1_cfg_a"], 3)
                ctx.set(p[f"io_check_env_{prefix}_1_addr"], 0xABC00000 >> 2)
                ctx.set(p[f"io_check_env_{prefix}_1_mask"], (1 << 48) - 1)
                for field in ("r", "w", "x"):
                    ctx.set(p[f"io_check_env_{prefix}_1_cfg_{field}"], 1)
            ctx.set(p["io_check_env_pmp_0_cfg_l"], 1)
            for flags in range(32):
                r, w, x, atomic, cache = [(flags >> bit) & 1 for bit in range(5)]
                for cmd in range(8):
                    ctx.set(p["io_req_valid"], 1)
                    ctx.set(p["io_req_bits_cmd"], cmd)
                    for prefix in ("pmp", "pma"):
                        for field, value in (("r", r), ("w", w), ("x", x)):
                            ctx.set(p[f"io_check_env_{prefix}_0_cfg_{field}"], value)
                    ctx.set(p["io_check_env_pma_0_cfg_atomic"], atomic)
                    ctx.set(p["io_check_env_pma_0_cfg_c"], cache)
                    await ctx.tick()
                    load = int(((cmd % 4 == 0 or cmd == 7) and not r) or (cmd == 4 and not atomic))
                    store = int((cmd % 4 == 1 and not w) or (cmd == 5 and not atomic))
                    execute = int((cmd % 4 == 2 or cmd == 7) and not x)
                    expected = (load, store, execute, 1 - cache, atomic)
                    names = ("io_resp_ld", "io_resp_st", "io_resp_instr", "io_resp_mmio", "io_resp_atomic")
                    self.assertEqual(expected, tuple(ctx.get(p[name]) for name in names), (flags, cmd))
                    # Current input changes do not alter a captured response.
                    ctx.set(p["io_req_valid"], 0)
                    ctx.set(p["io_req_bits_addr"], 0)
                    ctx.set(p["io_req_bits_cmd"], 7 - cmd)
                    await ctx.tick()
                    self.assertEqual(expected, tuple(ctx.get(p[name]) for name in names))
                    ctx.set(p["io_req_bits_addr"], 0xABC01230)
            # Reset clears the match vector while reset-less permissions hold.
            ctx.set(p["reset"], 1)
            await ctx.delay(1e-9)
            self.assertEqual(1, ctx.get(p["io_resp_mmio"]))
            self.assertEqual(0, ctx.get(p["io_resp_atomic"]))

        sim = Simulator(dut)
        sim.add_clock(1e-6)
        sim.add_testbench(bench)
        sim.run()

    def test_read_checker_ordered_permissions_and_address_boundaries(self) -> None:
        module = load_subject()
        dut = module.PMPFamily("PMPChecker")
        p = dut.ports
        rng = random.Random(0x3A01)

        async def bench(ctx):
            for cycle in range(260):
                mode, debug = cycle % 4, (cycle // 4) % 2
                request = rng.choice([0, 0xFFF, 0x1000, 0x1FFF, 0x2000,
                                      0x3801FFFF, 0x38020000, 0x38020FFF, 0x38021000,
                                      (1 << 47) | 0x1020])
                groups = {}
                for kind in ("pmp", "pma"):
                    entries = []
                    for index in range(32):
                        cfg_a = rng.randrange(4)
                        address = rng.choice([0, 0x400, 0x800, request >> 2, rng.getrandbits(46)])
                        mask = rng.choice([0, 0xFFF, (1 << 48) - 1])
                        read, cache, atomic, lock = [rng.randrange(2) for _ in range(4)]
                        if index in (0, 1) and cycle % 7 == 0:
                            cfg_a, mask = 3, (1 << 48) - 1
                            read = index  # The first matching deny beats the next allow.
                        ctx.set(p[f"io_check_env_{kind}_{index}_cfg_a"], cfg_a)
                        ctx.set(p[f"io_check_env_{kind}_{index}_addr"], address)
                        ctx.set(p[f"io_check_env_{kind}_{index}_mask"], mask)
                        ctx.set(p[f"io_check_env_{kind}_{index}_cfg_r"], read)
                        if kind == "pmp":
                            ctx.set(p[f"io_check_env_pmp_{index}_cfg_l"], lock)
                        else:
                            ctx.set(p[f"io_check_env_pma_{index}_cfg_c"], cache)
                            ctx.set(p[f"io_check_env_pma_{index}_cfg_atomic"], atomic)
                        entries.append((cfg_a, address, mask, read, cache, atomic, lock))
                    groups[kind] = entries
                ctx.set(p["io_req_bits_addr"], request)
                ctx.set(p["io_check_env_mode"], mode)
                ctx.set(p["io_check_env_debug"], debug)
                blocked_debug = 0x38020000 <= request < 0x38021000 and not debug
                found = {}
                for kind, entries in groups.items():
                    lower = 0
                    selected = None
                    for cfg_a, address, mask, read, cache, atomic, lock in entries:
                        upper = (address & 0x3FFFFFFFFC00) * 4
                        match = (((request ^ upper) & (~mask & ((1 << 48) - 1))) == 0
                                 if cfg_a & 2 else cfg_a == 1 and lower <= request < upper)
                        if selected is None and match and not blocked_debug:
                            selected = (read, cache, atomic, lock)
                        lower = upper
                    found[kind] = selected
                pmp = found["pmp"]
                pma = found["pma"] or (0, 0, 0, 0)
                pmp_read = bool(mode & 2) if pmp is None else bool(pmp[0] or (mode & 2 and not pmp[3]))
                self.assertEqual(int(not (pmp_read and pma[0])), ctx.get(p["io_resp_ld"]), cycle)
                self.assertEqual(int(not pma[1]), ctx.get(p["io_resp_mmio"]), cycle)
                self.assertEqual(pma[2], ctx.get(p["io_resp_atomic"]), cycle)

        sim = Simulator(dut)
        sim.add_testbench(bench)
        sim.run()

    def test_pmp_pma_delayed_csr_state_and_reset_table(self) -> None:
        module = load_subject()
        dut = module.PMPFamily("PMP")
        p = dut.ports
        text = (ROOT / "validation/reference-sv/PMP.sv").read_text(encoding="utf-8")
        reset_block = text[text.index("if (reset)"):text.index("else begin", text.index("if (reset)"))]
        initial = {name: int(value, 16) for name, value in re.findall(
            r"(p(?:mp|ma)Mapping_\w+)\s*<=\s*\d+'h([0-9A-Fa-f]+);", reset_block)}
        rng = random.Random(0xC5A0)

        def reset_state():
            return {kind: {
                "cfg": [(initial[f"{kind}Mapping_cfgMerged_{index // 8}"] >> (8 * (index % 8))) & 255
                        for index in range(32)],
                "addr": [initial[f"{kind}Mapping_addr_{index}"] for index in range(32)],
                "mask": [initial[f"{kind}Mapping_mask_{index}"] for index in range(32)],
            } for kind in ("pmp", "pma")}

        def mask_for(address, mode_low):
            joined = (((address & ((1 << 45) - 1)) << 1) | mode_low) | 0x3FF
            return (((joined & ~(joined + 1)) << 2) | 3) & ((1 << 48) - 1)

        async def bench(ctx):
            ctx.set(p["clock"], 0)
            model = reset_state()
            pending: tuple[int, int] | None = None

            async def step(command=None, reset=False):
                nonlocal model, pending
                ctx.set(p["reset"], int(reset))
                ctx.set(p["io_distribute_csr_w_valid"], int(command is not None))
                ctx.set(p["io_distribute_csr_w_bits_addr"], command[0] if command else 0)
                ctx.set(p["io_distribute_csr_w_bits_data"], command[1] if command else rng.getrandbits(64))
                if reset:
                    model, pending = reset_state(), None
                await ctx.delay(1e-9)
                for kind, values in model.items():
                    for index in range(32):
                        byte = values["cfg"][index]
                        expected = {"cfg_a": (byte >> 3) & 3, "cfg_x": (byte >> 2) & 1,
                                    "cfg_w": (byte >> 1) & 1, "cfg_r": byte & 1,
                                    "addr": values["addr"][index], "mask": values["mask"][index]}
                        if kind == "pmp":
                            expected["cfg_l"] = (byte >> 7) & 1
                        else:
                            expected.update(cfg_c=(byte >> 6) & 1, cfg_atomic=(byte >> 5) & 1)
                        for field, value in expected.items():
                            self.assertEqual(value, ctx.get(p[f"io_{kind}_{index}_{field}"]), (kind, index, field))
                if not reset and pending is not None:
                    csr, data = pending
                    for kind, cfg_base, addr_base in (("pmp", 0x3A0, 0x3B0), ("pma", 0x7C0, 0x7C8)):
                        values = model[kind]
                        for group in range(4):
                            if csr == cfg_base + 2 * group:
                                for lane in range(8):
                                    index = group * 8 + lane
                                    old, incoming = values["cfg"][index], (data >> (lane * 8)) & 255
                                    if old & 128:
                                        continue
                                    canonical = incoming
                                    if not incoming & 1:
                                        canonical &= ~2
                                    if incoming & 16:
                                        canonical |= 8
                                    values["cfg"][index] = canonical
                                    if canonical & 16:
                                        values["mask"][index] = mask_for(values["addr"][index], (canonical >> 3) & 1)
                        if addr_base <= csr < addr_base + 32:
                            index = csr - addr_base
                            old = values["cfg"][index]
                            following = values["cfg"][index + 1] if index < 31 else 0
                            locked = bool(old & 128 or (following & 128 and ((following >> 3) & 3) == 1))
                            if not locked:
                                values["addr"][index] = data & ((1 << 46) - 1)
                                values["mask"][index] = mask_for(data, (old >> 3) & 1)
                pending = None if reset else command
                ctx.set(p["clock"], 1)
                await ctx.delay(1e-9)
                ctx.set(p["clock"], 0)
                await ctx.delay(1e-9)

            await step(reset=True)
            for base in (0x3B0, 0x7C8):
                for index in range(32):
                    await step((base + index, (1 << 45) | 0x40000 | index * 0x123))
            await step()
            for base in (0x3A0, 0x7C0):
                for group in range(4):
                    await step((base + 2 * group, 0x18231E02230A8F89))
            await step()
            # Locked bytes and next-entry TOR locks reject subsequent writes.
            for base in (0x3B0, 0x7C8):
                for index in (0, 1, 6, 7, 31):
                    await step((base + index, rng.getrandbits(64)))
            await step()
            legal = [0x3A0 + 2 * i for i in range(4)] + [0x7C0 + 2 * i for i in range(4)]
            legal += list(range(0x3B0, 0x3D0)) + list(range(0x7C8, 0x7E8)) + [0x3A1, 0x7C1, 0x123]
            for cycle in range(350):
                command = (rng.choice(legal), rng.getrandbits(64)) if cycle % 5 else None
                await step(command, reset=cycle in (101, 277))
            await step()

        sim = Simulator(dut)
        sim.add_testbench(bench)
        sim.run()

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
