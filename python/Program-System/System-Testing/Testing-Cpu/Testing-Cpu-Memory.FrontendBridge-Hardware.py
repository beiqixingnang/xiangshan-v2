"""Direct tests for the V2 FrontendBridge Build.

The test deliberately stays at the public Build boundary.  It checks the
locked module ABI, deterministic export, and the externally visible
ready/valid behavior of the two serial two-entry queues used by the I-cache A
edge; it does not import a sibling Build or regenerate the locked reference.
"""

from __future__ import annotations

import importlib.util
import random
import re
import sys
import unittest
from collections import deque
from pathlib import Path
from typing import Any

from amaranth import ClockDomain, Elaboratable, Module, Signal
from amaranth.sim import Simulator


ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/"
    "Cpu-Memory-Memory.FrontendBridge-Hardware.py"
)
LOCKED = ROOT / "validation/reference-sv/FrontendBridge.sv"


def load_subject() -> Any:
    """Load the exact FrontendBridge Build path. / 加载精确 FrontendBridge Build 路径。"""

    spec = importlib.util.spec_from_file_location("testing_frontend_bridge", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _width(high: str | None, low: str | None) -> int:
    return abs(int(high) - int(low)) + 1 if high is not None and low is not None else 1


def _locked_ports(text: str) -> dict[str, tuple[str, int]]:
    """Parse grouped ANSI declarations from the locked FrontendBridge header."""

    match = re.search(r"^module\s+FrontendBridge\s*\((.*?)\);", text, re.MULTILINE | re.DOTALL)
    if match is None:
        raise AssertionError("locked FrontendBridge header is missing")
    ports: dict[str, tuple[str, int]] = {}
    direction: str | None = None
    declared_width = 1
    for raw in match.group(1).split(","):
        token = re.sub(r"//[^\n]*", "", raw).strip()
        if not token:
            continue
        declaration = re.match(
            r"^(input|output|inout)\s*(?:\[(\d+):(\d+)\])?\s*(.*)$",
            token,
            re.DOTALL,
        )
        if declaration is not None:
            direction = declaration.group(1)
            declared_width = _width(declaration.group(2), declaration.group(3))
            token = declaration.group(4).strip()
        if direction is None or not re.fullmatch(r"[A-Za-z_]\w*", token):
            raise AssertionError(f"invalid locked port declaration: {raw!r}")
        ports[token] = (direction, declared_width)
    return ports


def _exported_ports(text: str, module_name: str) -> dict[str, tuple[str, int]]:
    """Parse Amaranth's non-ANSI body declarations for one exported module."""

    header = re.search(
        rf"^module\s+{re.escape(module_name)}\s*\((.*?)\);",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if header is None:
        raise AssertionError(f"exported {module_name} header is missing")
    wanted = {
        item.strip()
        for item in re.sub(r"//[^\n]*", "", header.group(1)).replace("\n", " ").split(",")
        if item.strip()
    }
    ports: dict[str, tuple[str, int]] = {}
    module_end = text.find("endmodule", header.end())
    body = text[header.end() : module_end if module_end >= 0 else len(text)]
    for raw in body.splitlines():
        line = re.sub(r"//[^\n]*", "", raw).strip().rstrip(";").strip()
        declaration = re.match(
            r"^(input|output|inout)\s*(?:\[(\d+):(\d+)\])?\s*(.+)$", line
        )
        if declaration is None:
            continue
        direction = declaration.group(1)
        declared_width = _width(declaration.group(2), declaration.group(3))
        for name in declaration.group(4).split(","):
            name = name.strip()
            if name in wanted:
                ports[name] = (direction, declared_width)
    return ports


class FrontendBridgeTest(unittest.TestCase):
    """Check the public ABI and bounded queue behavior. / 检查公开 ABI 与有限队列行为。"""

    def test_locked_abi_and_deterministic_export(self) -> None:
        """The generated top must match the locked names/directions/widths exactly."""

        module = load_subject()
        first = module.build_verilog({"module": "FrontendBridge"}, {})
        second = module.build_verilog({"module": "FrontendBridge"}, {})
        self.assertEqual(first, second)
        self.assertEqual(
            _exported_ports(first, "FrontendBridge"),
            _locked_ports(LOCKED.read_text(encoding="utf-8")),
        )

    def test_icache_a_queue_ready_valid_order(self) -> None:
        """Two serial depth-two queues accept four items, then drain in order."""

        module = load_subject()
        bridge = module.FrontendBridge()
        accepted: list[int] = []
        observed: list[int] = []

        async def bench(ctx: Any) -> None:
            ctx.set(bridge.reset, 1)
            await ctx.tick("sync")
            ctx.set(bridge.reset, 0)
            ctx.set(bridge.auto_icache_out_a_ready, 0)
            for value in range(5):
                ctx.set(bridge.auto_icache_in_a_valid, 1)
                ctx.set(bridge.auto_icache_in_a_bits_source, value)
                ctx.set(bridge.auto_icache_in_a_bits_address, 0x1000 + value * 64)
                ready = int(ctx.get(bridge.auto_icache_in_a_ready))
                await ctx.tick("sync")
                if ready:
                    accepted.append(value)
            self.assertEqual(accepted, [0, 1, 2, 3])

            ctx.set(bridge.auto_icache_in_a_valid, 0)
            ctx.set(bridge.auto_icache_out_a_ready, 1)
            for _ in range(10):
                if int(ctx.get(bridge.auto_icache_out_a_valid)):
                    observed.append(int(ctx.get(bridge.auto_icache_out_a_bits_source)))
                await ctx.tick("sync")
            self.assertEqual(observed, accepted)

        simulator = Simulator(bridge)
        simulator.add_clock(1e-6, domain="sync")
        simulator.add_testbench(bench)
        simulator.run()

    def test_all_six_channels_against_independent_fifo_scoreboards(self) -> None:
        module = load_subject()
        bridge = module.FrontendBridge()
        widths = dict(module.port_schema())
        rng = random.Random(0xB12D)
        channels = []
        for edge in ("icache", "icachectrl", "instr_uncache"):
            for channel in ("a", "d"):
                source_side, sink_side = ("in", "out") if channel == "a" else ("out", "in")
                source = f"auto_{edge}_{source_side}_{channel}"
                sink = f"auto_{edge}_{sink_side}_{channel}"
                fields = {name.removeprefix(source + "_bits_"): width for name, width in widths.items()
                          if name.startswith(source + "_bits_")}
                channels.append((edge, channel, source, sink, fields, deque(), deque()))

        async def bench(ctx):
            for cycle in range(450):
                reset = cycle in (0, 211)
                ctx.set(bridge.reset, int(reset))
                if reset:
                    for _edge, _channel, _source, _sink, _fields, q0, q1 in channels:
                        q0.clear()
                        q1.clear()
                transfers = []
                for edge, channel, source, sink, fields, q0, q1 in channels:
                    valid = rng.randrange(4) != 0
                    consumer_ready = rng.randrange(3) != 0 if sink + "_ready" in widths else True
                    incoming = {field: rng.getrandbits(width) for field, width in fields.items()}
                    ctx.set(getattr(bridge, source + "_valid"), int(valid))
                    if sink + "_ready" in widths:
                        ctx.set(getattr(bridge, sink + "_ready"), int(consumer_ready))
                    for field, value in incoming.items():
                        ctx.set(getattr(bridge, source + "_bits_" + field), value)
                    if channel == "a" and edge == "icache":
                        incoming.update(opcode=4, param=0, size=6, user_alias=0, user_reqSource=1,
                                        user_needHint=0, mask=(1 << 32) - 1, data=0, corrupt=0)
                    elif channel == "a" and edge == "instr_uncache":
                        incoming.update(param=0, corrupt=0)
                    elif channel == "d" and edge == "icachectrl":
                        incoming.update(param=0, sink=0, denied=0, corrupt=0)
                    self.assertEqual(int(len(q0) < 2), ctx.get(getattr(bridge, source + "_ready")), (edge, channel, cycle))
                    self.assertEqual(int(bool(q1)), ctx.get(getattr(bridge, sink + "_valid")), (edge, channel, cycle))
                    if q1:
                        for name in widths:
                            if name.startswith(sink + "_bits_"):
                                field = name.removeprefix(sink + "_bits_")
                                self.assertEqual(q1[0][field], ctx.get(getattr(bridge, name)), (name, cycle))
                    transfers.append((incoming if valid and len(q0) < 2 else None,
                                      bool(q1) and consumer_ready, bool(q0) and len(q1) < 2))
                await ctx.tick("sync")
                if not reset:
                    for row, (incoming, pop, move) in zip(channels, transfers):
                        q0, q1 = row[-2:]
                        if pop:
                            q1.popleft()
                        if move:
                            q1.append(q0.popleft())
                        if incoming is not None:
                            q0.append(incoming)

        simulator = Simulator(bridge)
        simulator.add_clock(1e-6, domain="sync")
        simulator.add_testbench(bench)
        simulator.run()

    def test_two_entry_queue_temporal_contract(self) -> None:
        """Exercise Queue(2) empty/full, pointer wrap, and invalid payload rules."""

        module = load_subject()

        class QueueHarness(Elaboratable):
            def __init__(self) -> None:
                self.reset = Signal()
                self.queue = module.TwoEntryQueue((8,), "direct_queue")

            def elaborate(self, platform: Any) -> Module:
                del platform
                harness = Module()
                domain = ClockDomain("sync", async_reset=True)
                domain.rst = self.reset
                harness.domains.sync = domain
                harness.submodules.queue = self.queue
                return harness

        harness = QueueHarness()

        async def bench(ctx: Any) -> None:
            ctx.set(harness.reset, 1)
            await ctx.tick("sync")
            ctx.set(harness.reset, 0)
            ctx.set(harness.queue.enq_valid, 0)
            ctx.set(harness.queue.deq_ready, 0)

            # Empty: ready is asserted, valid is deasserted.  The payload is
            # intentionally not inspected while valid is low.
            self.assertEqual(int(ctx.get(harness.queue.enq_ready)), 1)
            self.assertEqual(int(ctx.get(harness.queue.deq_valid)), 0)

            # Fill both entries and observe the full handshake.
            for value in (0x11, 0x22):
                ctx.set(harness.queue.enq_bits[0], value)
                ctx.set(harness.queue.enq_valid, 1)
                self.assertEqual(int(ctx.get(harness.queue.enq_ready)), 1)
                await ctx.tick("sync")
            self.assertEqual(int(ctx.get(harness.queue.enq_ready)), 0)
            self.assertEqual(int(ctx.get(harness.queue.deq_valid)), 1)
            self.assertEqual(int(ctx.get(harness.queue.deq_bits[0])), 0x11)

            # pipe=false means a full queue does not accept a replacement
            # during a dequeue; the next item remains 0x22.
            ctx.set(harness.queue.enq_bits[0], 0x33)
            ctx.set(harness.queue.enq_valid, 1)
            ctx.set(harness.queue.deq_ready, 1)
            self.assertEqual(int(ctx.get(harness.queue.enq_ready)), 0)
            await ctx.tick("sync")
            self.assertEqual(int(ctx.get(harness.queue.enq_ready)), 1)
            self.assertEqual(int(ctx.get(harness.queue.deq_valid)), 1)
            self.assertEqual(int(ctx.get(harness.queue.deq_bits[0])), 0x22)

            # Now there is space, so enqueue/dequeue happen together and the
            # newly accepted item becomes the sole queued value.
            self.assertEqual(int(ctx.get(harness.queue.enq_ready)), 1)
            await ctx.tick("sync")
            self.assertEqual(int(ctx.get(harness.queue.deq_valid)), 1)
            self.assertEqual(int(ctx.get(harness.queue.deq_bits[0])), 0x33)

            # Drain 0x33, then use the wrapped slots (1 then 0) for 0x44/55.
            ctx.set(harness.queue.enq_valid, 0)
            await ctx.tick("sync")
            self.assertEqual(int(ctx.get(harness.queue.deq_valid)), 0)
            ctx.set(harness.queue.deq_ready, 0)
            for value in (0x44, 0x55):
                ctx.set(harness.queue.enq_bits[0], value)
                ctx.set(harness.queue.enq_valid, 1)
                await ctx.tick("sync")
            self.assertEqual(int(ctx.get(harness.queue.enq_ready)), 0)
            self.assertEqual(int(ctx.get(harness.queue.deq_bits[0])), 0x44)
            ctx.set(harness.queue.deq_ready, 1)
            await ctx.tick("sync")
            self.assertEqual(int(ctx.get(harness.queue.deq_valid)), 1)
            self.assertEqual(int(ctx.get(harness.queue.deq_bits[0])), 0x55)
            ctx.set(harness.queue.enq_valid, 0)
            await ctx.tick("sync")
            self.assertEqual(int(ctx.get(harness.queue.deq_valid)), 0)

        simulator = Simulator(harness)
        simulator.add_clock(1e-6, domain="sync")
        simulator.add_testbench(bench)
        simulator.run()


if __name__ == "__main__":
    unittest.main()
