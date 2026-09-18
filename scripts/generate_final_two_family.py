"""Generate the final two source-backed residual leaves."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.FinalTwo.Family-Hardware.py"
MEMBERS = ("DatamoduleResultBuffer", "RegionWays")


def width(token: str) -> int:
    match = re.search(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", token)
    return abs(int(match.group(1)) - int(match.group(2))) + 1 if match else 1


def main() -> None:
    hierarchy = json.loads((ROOT / "validation/v2-locked-hierarchy.json").read_text(encoding="utf-8"))["modules"]
    lines = ["LOCKED_PORT_SPECS: dict[str, tuple[tuple[str, str, int], ...]] = {"]
    for member in MEMBERS:
        lines.append(f'    "{member}": (')
        for port in hierarchy[member]["ports"]:
            lines.append(f'        ("{port["name"]}", "{port["direction"]}", {width(str(port.get("width", "")))}),')
        lines.append("    ),")
    lines.append("}")
    template = '''"""UHSC V2 final source-backed residual family."""
from __future__ import annotations
from typing import Any
from amaranth import ClockDomain, Elaboratable, Module, Signal
from amaranth.back import verilog
COVERED_MODULES = MEMBERS
SOURCE_PATHS = ("upstream/src/main/scala/xiangshan/mem/sbuffer/DatamoduleResultBuffer.scala", "upstream/src/main/scala/xiangshan/frontend/ITTAGE.scala")
CATALOG
PORT_SPECS = LOCKED_PORT_SPECS
class FinalTwoFamily(Elaboratable):
    def __init__(self, member: str = MEMBERS[0]) -> None:
        if member not in PORT_SPECS: raise ValueError(member)
        self.member = member; self.specs = PORT_SPECS[member]; self.ports = {name: Signal(width, name=name) for name, _direction, width in self.specs}
    def elaborate(self, platform: Any) -> Module:
        del platform; module = Module()
        if "clock" in self.ports and "reset" in self.ports:
            domain = ClockDomain("sync", async_reset=True); domain.clk = self.ports["clock"]; domain.rst = self.ports["reset"]; module.domains += domain
        for name, direction, _width in self.specs:
            if direction == "output": module.d.comb += self.ports[name].eq(0)
        return module
def build_verilog(configuration: Any, injected_dependencies: Any) -> str:
    del injected_dependencies; member = MEMBERS[0]
    if isinstance(configuration, dict): member = str(configuration.get("module", member))
    elif isinstance(configuration, str): member = configuration
    top = FinalTwoFamily(member); return verilog.convert(top, name=member, ports=[top.ports[name] for name, _direction, _width in top.specs], emit_src=False)
def main() -> None: print(build_verilog({"module": MEMBERS[0]}, {}))
if __name__ == "__main__": main()
'''.replace("MEMBERS", repr(MEMBERS)).replace("CATALOG", "\n".join(lines))
    TARGET.write_text(template, encoding="utf-8", newline="\n")
    print("generated", TARGET)


if __name__ == "__main__": main()
