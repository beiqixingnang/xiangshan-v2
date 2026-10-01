"""System-Testing contract for the bounded Rocket TL child family.

This test locks the eleven selected L2Top child inventories and verifies that
relay, merger and BusErrorUnit equations remain deterministic. It does not
close the L2Top parent or any XSTile/XSCore family.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import random
import sys
import unittest
from collections import deque
from pathlib import Path

from amaranth.sim import Simulator


ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Cpu-Core-Dependency.Rocket.TLChildren.Family-Hardware.py"
)
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
MEMBERS = (
    "TLXbar_7", "TLXbar_8", "TLXbar_9", "TLBuffer_27", "TLBuffer_20",
    "TLBuffer_29", "TLBuffer_22", "TLBuffer_16", "TLBuffer_2",
    "TLClientsMerger_1", "BusErrorUnit",
)


def load_subject():
    spec = importlib.util.spec_from_file_location("tl_children_subject", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TLChildrenFamilyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_subject()

    def test_locked_members_and_ports(self) -> None:
        hierarchy = json.loads(HIERARCHY.read_text(encoding="utf-8"))
        self.assertEqual(MEMBERS, tuple(self.module.COVERED_MODULES))
        for member in MEMBERS:
            with self.subTest(member=member):
                expected = hierarchy["modules"][member]["ports"]
                actual = self.module.PORT_SPECS[member]
                self.assertEqual(len(expected), len(actual))
                self.assertEqual(
                    [(row["name"], row["direction"],
                      int(row["width"][1:row["width"].find(":")])
                      - int(row["width"][row["width"].find(":") + 1:-1]) + 1
                      if str(row["width"]).startswith("[") else 1)
                     for row in expected],
                    list(actual),
                )

    def test_deterministic_exact_exports(self) -> None:
        for member in MEMBERS:
            with self.subTest(member=member):
                first = self.module.build_verilog({"module": member}, {})
                second = self.module.build_verilog({"module": member}, {})
                self.assertEqual(first, second)
                self.assertRegex(first, rf"\bmodule\s+{re.escape(member)}\b")
                self.assertGreater(len(first), 100)
                self.assertNotEqual(hashlib.sha256(first.encode()).hexdigest(), "0" * 64)

    def test_source_equations(self) -> None:
        self.assertEqual(
            {"ready": 1, "valid": 1, "fire": 1, "reset": 0},
            self.module.relay_observation(valid=True, ready=True),
        )
        self.assertEqual(
            {"min_id": 0, "max_id": 16, "source_id_width": 16, "client_count": 2},
            self.module.merge_source_ids([4, 8], starts=[0, 8]),
        )
        self.assertEqual(
            {"cause_valid": 1, "cause": 1, "global_interrupt": 0, "local_interrupt": 1},
            self.module.bus_error_observation([False, True], [True, True],
                                              [True, False], [False, True]),
        )

    def test_tlclients_merger_source_id_remap(self) -> None:
        """Preserve the locked four-way address-to-source mapping."""

        rtl = self.module.build_verilog({"module": "TLClientsMerger_1"}, {})
        self.assertIn("auto_in_b_bits_source", rtl)
        for constant in ("10'h100", "10'h200", "10'h300"):
            self.assertIn(constant, rtl)

    def test_tlbuffer_queue_backpressure_and_reset_model(self) -> None:
        # A depth-two Queue accepts two requests, holds the head under
        # backpressure, blocks the third request while full, and resumes in
        # FIFO order.  The reset event clears both entries immediately.
        events = [
            {"valid": True, "ready": False, "payload": "a"},
            {"valid": True, "ready": False, "payload": "b"},
            {"valid": True, "ready": False, "payload": "c"},
            {"valid": False, "ready": True},
            {"valid": False, "ready": True},
            {"reset": True, "valid": False, "ready": False},
            {"valid": True, "ready": True, "payload": "d"},
            {"valid": False, "ready": True},
        ]
        observations = self.module.tlbuffer_model(events)
        self.assertEqual([1, 1, 0, 0, 1, 1, 1, 1],
                         [row["ready"] for row in observations])
        self.assertEqual([None, "a", "a", "a", "b", None, None, "d"],
                         [row["payload"] for row in observations])
        self.assertEqual([0, 0, 0, 1, 1, 0, 0, 1],
                         [row["fire_out"] for row in observations])
        self.assertEqual(1, observations[5]["reset"])

    def test_unknown_member_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.module.build_verilog({"module": "NotATLChild"}, {})

    def test_tlbuffer_all_channels_against_fifo_scoreboards(self) -> None:
        """Exercise actual DUT queues through fill, drain, reset and wrap."""

        for member in (name for name in MEMBERS if name.startswith("TLBuffer_")):
            dut = self.module.TLChildFamily(member)
            lanes = []
            for port in dut.spec.ports:
                if port.direction != "input" or not port.name.endswith("_valid"):
                    continue
                enqueue = port.name.removesuffix("_valid")
                dequeue = enqueue.replace("auto_in", "auto_out") if enqueue.startswith(
                    "auto_in") else enqueue.replace("auto_out", "auto_in")
                fields = [(p.name.removeprefix(enqueue + "_bits_"), p.width)
                          for p in dut.spec.ports
                          if p.direction == "input" and p.name.startswith(enqueue + "_bits_")]
                lanes.append((enqueue, dequeue, fields))

            async def bench(ctx, dut=dut, lanes=lanes, member=member):
                rng = random.Random(0x2751)
                queues = {enqueue: deque() for enqueue, _dequeue, _fields in lanes}
                ctx.set(dut.ports["clock"], 0)
                for cycle in range(100):
                    reset = cycle in (0, 36, 71)
                    ctx.set(dut.ports["reset"], int(reset))
                    pending = []
                    for index, (enqueue, dequeue, fields) in enumerate(lanes):
                        q = queues[enqueue]
                        if reset:
                            q.clear()
                        # Fill fully before draining; subsequent independent
                        # traffic forces both pointers to wrap repeatedly.
                        valid = cycle < 5 or (rng.randrange(4) != 0)
                        ready = cycle >= 5 and (rng.randrange(4) != 0)
                        payload = tuple(rng.getrandbits(width) for _field, width in fields)
                        ctx.set(dut.ports[f"{enqueue}_valid"], int(valid))
                        ctx.set(dut.ports[f"{dequeue}_ready"], int(ready))
                        for (field, _width), value in zip(fields, payload):
                            ctx.set(dut.ports[f"{enqueue}_bits_{field}"], value)
                        pending.append((enqueue, dequeue, fields, payload, valid, ready))
                    await ctx.delay(1e-9)
                    for enqueue, dequeue, fields, payload, valid, ready in pending:
                        q = queues[enqueue]
                        enq_ready = len(q) < 2
                        deq_valid = bool(q)
                        self.assertEqual(int(enq_ready), ctx.get(dut.ports[f"{enqueue}_ready"]),
                                         (member, enqueue, cycle))
                        self.assertEqual(int(deq_valid), ctx.get(dut.ports[f"{dequeue}_valid"]),
                                         (member, dequeue, cycle))
                        if deq_valid:
                            actual = tuple(ctx.get(dut.ports[f"{dequeue}_bits_{field}"])
                                           for field, _width in fields)
                            self.assertEqual(q[0], actual, (member, dequeue, cycle))
                        if not reset:
                            if deq_valid and ready:
                                q.popleft()
                            if enq_ready and valid:
                                q.append(payload)
                    ctx.set(dut.ports["clock"], 1)
                    await ctx.delay(1e-9)
                    ctx.set(dut.ports["clock"], 0)
                    await ctx.delay(1e-9)

            with self.subTest(member=member):
                sim = Simulator(dut)
                sim.add_testbench(bench)
                sim.run()

    def test_bus_error_registers_and_interrupt_scoreboard(self) -> None:
        """Compare MMIO and four error sources against an independent model."""

        dut = self.module.TLChildFamily("BusErrorUnit")
        p = dut.ports

        async def bench(ctx):
            rng = random.Random(0xBEE)
            state = {"cause": 0, "value": 0, "enable": 15,
                     "global": 0, "accrued": 0, "local": 0}
            ctx.set(p["clock"], 0)
            for cycle in range(600):
                reset = cycle in (0, 200, 400)
                if reset:
                    state.update(cause=0, enable=15)
                    state["global"] = state["accrued"] = state["local"] = 0
                ctx.set(p["reset"], int(reset))
                # Cycle zero seeds the resetless value register through a
                # real masked write while the other registers remain reset.
                address = 8 if cycle == 0 else rng.choice(
                    [0, 8, 16, 24, 32, 40, 48, 56, 64, 0x1008, 0x100010])
                mask = 63 if cycle == 0 else rng.randrange(256)
                data = rng.getrandbits(64)
                opcode = 0 if cycle == 0 else rng.choice([0, 1, 4, 7])
                valid = 1 if cycle == 0 else rng.randrange(2)
                ready = 1 if cycle == 0 else rng.randrange(2)
                size, source = rng.randrange(4), rng.randrange(32)
                ctx.set(p["auto_in_a_valid"], valid)
                ctx.set(p["auto_in_d_ready"], ready)
                for suffix, value in (("address", address), ("mask", mask), ("data", data),
                                      ("opcode", opcode), ("size", size), ("source", source)):
                    ctx.set(p[f"auto_in_a_bits_{suffix}"], value)
                error_valid = rng.randrange(16) if cycle else 0
                error_values = [rng.getrandbits(48) for _ in range(4)]
                for i, name in enumerate(("icache", "dcache", "uncache", "l2")):
                    ctx.set(p[f"io_errors_{name}_ecc_error_valid"], (error_valid >> i) & 1)
                    ctx.set(p[f"io_errors_{name}_ecc_error_bits"], error_values[i])
                await ctx.delay(1e-9)
                index = (address >> 3) & 7
                decoded = ((address >> 6) & 63) == 0
                values = [state[key] for key in ("cause", "value", "enable", "global",
                                                 "accrued", "local")] + [0, 0]
                self.assertEqual(ready, ctx.get(p["auto_in_a_ready"]))
                self.assertEqual(valid, ctx.get(p["auto_in_d_valid"]))
                self.assertEqual(int(opcode == 4), ctx.get(p["auto_in_d_bits_opcode"]))
                self.assertEqual(size, ctx.get(p["auto_in_d_bits_size"]))
                self.assertEqual(source, ctx.get(p["auto_in_d_bits_source"]))
                self.assertEqual(values[index] if decoded else 0,
                                 ctx.get(p["auto_in_d_bits_data"]), (cycle, address))
                self.assertEqual(int(bool(state["accrued"] & state["global"])),
                                 ctx.get(p["auto_int_out_0"]))
                self.assertEqual(int(bool(state["accrued"] & state["local"])),
                                 ctx.get(p["io_interrupt"]))
                eligible = error_valid & state["enable"]
                capture = state["cause"] == 0 and bool(eligible)
                winner = eligible.bit_length() - 1 if eligible else 0
                write = valid and ready and opcode != 4 and decoded
                if write and index == 1 and (mask & 63):
                    for lane in range(6):
                        if (mask >> lane) & 1:
                            lane_mask = 255 << (lane * 8)
                            state["value"] = (state["value"] & ~lane_mask) | (data & lane_mask)
                elif capture:
                    state["value"] = error_values[winner]
                if not reset:
                    if write and index == 0 and mask & 1:
                        state["cause"] = data & 3
                    elif capture:
                        state["cause"] = winner
                    for key, offset in (("enable", 2), ("global", 3), ("local", 5)):
                        if write and index == offset and mask & 1:
                            state[key] = data & 15
                    state["accrued"] = data & 15 if write and index == 4 and mask & 1 else (
                        state["accrued"] | error_valid)
                ctx.set(p["clock"], 1)
                await ctx.delay(1e-9)
                ctx.set(p["clock"], 0)
                await ctx.delay(1e-9)

        sim = Simulator(dut)
        sim.add_testbench(bench)
        sim.run()

    def test_tlxbar8_address_source_and_round_robin_routes(self) -> None:
        """Check locked address sets, source expansion and D demux."""

        dut = self.module.TLChildFamily("TLXbar_8")
        p = dut.ports

        async def bench(ctx):
            ctx.set(p["clock"], 0)
            ctx.set(p["reset"], 1)
            await ctx.tick()
            ctx.set(p["reset"], 0)
            for manager, ready in enumerate((1, 1, 1)):
                ctx.set(p[f"auto_out_{manager}_a_ready"], ready)
            # Client 0 -> manager 0, then source must carry 0x10 prefix.
            for name, value in (("auto_in_0_a_valid", 1),
                                ("auto_in_0_a_bits_address", 0x38010000),
                                ("auto_in_0_a_bits_source", 1),
                                ("auto_in_0_a_bits_opcode", 0)):
                ctx.set(p[name], value)
            await ctx.delay(1e-9)
            self.assertEqual(1, ctx.get(p["auto_out_0_a_valid"]))
            self.assertEqual(0x11, ctx.get(p["auto_out_0_a_bits_source"]))
            self.assertEqual(1, ctx.get(p["auto_in_0_a_ready"]))
            # Adjacent boundary moves to manager 2, while manager 0 is idle.
            ctx.set(p["auto_in_0_a_bits_address"], 0x38011000)
            await ctx.delay(1e-9)
            self.assertEqual(0, ctx.get(p["auto_out_0_a_valid"]))
            self.assertEqual(1, ctx.get(p["auto_out_2_a_valid"]))
            # D source 0x10 returns to client 0 and trims to one local bit.
            ctx.set(p["auto_in_0_a_valid"], 0)
            ctx.set(p["auto_out_2_d_valid"], 1)
            ctx.set(p["auto_out_2_d_bits_source"], 0x10)
            ctx.set(p["auto_in_0_d_ready"], 1)
            ctx.set(p["auto_in_1_d_ready"], 0)
            await ctx.delay(1e-9)
            self.assertEqual(1, ctx.get(p["auto_in_0_d_valid"]))
            self.assertEqual(1, ctx.get(p["auto_out_2_d_ready"]))

            ctx.set(p["auto_out_2_d_valid"], 0)
            for address, manager in ((0x38010FFF, 0), (0x38022000, 1),
                                     (0x380220FF, 1), (0x38022100, 2),
                                     (0x31110000, None), (1 << 47, 2)):
                ctx.set(p["auto_in_0_a_valid"], 1)
                ctx.set(p["auto_in_0_a_bits_address"], address)
                await ctx.delay(1e-9)
                for lane in range(3):
                    self.assertEqual(int(manager == lane),
                                     ctx.get(p[f"auto_out_{lane}_a_valid"]), hex(address))
            ctx.set(p["auto_in_0_a_valid"], 0)
            ctx.set(p["auto_in_0_a_bits_address"], 0)
            # Idle ready is independent of A.valid.
            await ctx.delay(1e-9)
            self.assertEqual(1, ctx.get(p["auto_in_0_a_ready"]))

            # The first RR winner is client 1. It owns all four beats of a
            # 32-byte Put, including stalled cycles, before client 0 wins.
            ctx.set(p["reset"], 1)
            await ctx.tick()
            ctx.set(p["reset"], 0)
            for client in range(2):
                ctx.set(p[f"auto_in_{client}_a_valid"], 1)
                ctx.set(p[f"auto_in_{client}_a_bits_address"], 0)
                ctx.set(p[f"auto_in_{client}_a_bits_opcode"], 0)
                ctx.set(p[f"auto_in_{client}_a_bits_size"], 5 if client else 0)
                ctx.set(p[f"auto_in_{client}_a_bits_source"], 3 if client else 0)
            ctx.set(p["auto_out_2_a_ready"], 1)
            for _ in range(4):
                self.assertEqual(3, ctx.get(p["auto_out_2_a_bits_source"]))
                self.assertEqual(0, ctx.get(p["auto_in_0_a_ready"]))
                await ctx.tick()
                ctx.set(p["auto_out_2_a_ready"], 0)
                self.assertEqual(0, ctx.get(p["auto_in_1_a_ready"]))
                ctx.set(p["auto_out_2_a_ready"], 1)
            self.assertEqual(0x10, ctx.get(p["auto_out_2_a_bits_source"]))

            # Three D responders round-robin toward client 1; invalid global
            # source values must never make either client's response valid.
            ctx.set(p["reset"], 1)
            await ctx.tick()
            ctx.set(p["reset"], 0)
            for client in range(2):
                ctx.set(p[f"auto_in_{client}_a_valid"], 0)
                ctx.set(p[f"auto_in_{client}_d_ready"], 1)
            for manager in range(3):
                ctx.set(p[f"auto_out_{manager}_d_valid"], 1)
                ctx.set(p[f"auto_out_{manager}_d_bits_source"], manager + 1)
                ctx.set(p[f"auto_out_{manager}_d_bits_opcode"], 0)
                ctx.set(p[f"auto_out_{manager}_d_bits_data"], 0xA0 + manager)
            for winner in (2, 1, 0, 2):
                self.assertEqual(0xA0 + winner, ctx.get(p["auto_in_1_d_bits_data"]))
                self.assertEqual(winner + 1, ctx.get(p["auto_in_1_d_bits_source"]))
                await ctx.tick()
            for manager in range(3):
                ctx.set(p[f"auto_out_{manager}_d_bits_source"], 31)
            self.assertEqual(0, ctx.get(p["auto_in_0_d_valid"]))
            self.assertEqual(0, ctx.get(p["auto_in_1_d_valid"]))

        sim = Simulator(dut)
        sim.add_clock(1e-6)
        sim.add_testbench(bench)
        sim.run()


if __name__ == "__main__":
    unittest.main()
