"""Direct tests for the V2 FrontendBridge Build.

The test deliberately stays at the public Build boundary.  It checks the
locked module ABI, deterministic export, and the externally visible
ready/valid behavior of the two serial two-entry queues used by the I-cache A
edge; it does not import a sibling Build or regenerate the locked reference.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path
from typing import Any

from amaranth.sim import Simulator


ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/"
    "Build-Cpu.Memory.FrontendBridge-Hardware.py"
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


if __name__ == "__main__":
    unittest.main()
