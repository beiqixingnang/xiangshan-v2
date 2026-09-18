"""Generate the explicit bounded aggregate for all currently missing V2 leaves."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Residual.LeafFamily-Hardware.py"
HIER = ROOT / "validation/v2-locked-hierarchy.json"
COVERAGE = ROOT / "validation/v2-hierarchy-coverage.json"


def width(token: str) -> int:
    match = re.search(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", token)
    return abs(int(match.group(1)) - int(match.group(2))) + 1 if match else 1


def main() -> None:
    hierarchy = json.loads(HIER.read_text(encoding="utf-8"))["modules"]
    coverage = json.loads(COVERAGE.read_text(encoding="utf-8"))
    members = tuple(row["module"] for row in coverage["rows"] if row["status"] == "MISSING")
    catalog = ["LOCKED_PORT_SPECS: dict[str, tuple[tuple[str, str, int], ...]] = {"]
    for member in members:
        catalog.append(f'    "{member}": (')
        for port in hierarchy[member]["ports"]:
            catalog.append(f'        ("{port["name"]}", "{port["direction"]}", {width(str(port.get("width", "")))}),')
        catalog.append("    ),")
    catalog.append("}")
    text = '''"""UHSC V2 residual locked-leaf structural aggregate.

This aggregate closes only the exact port/export/tool surface for the
remaining locked modules.  It is deliberately STRUCTURE_VERIFIED_BOUNDED;
source-backed behavioral families, parent closure, and top differential remain
mandatory and this file is never acceptance evidence by itself.
"""
from __future__ import annotations
from typing import Any
from amaranth import ClockDomain, Elaboratable, Module, Signal
from amaranth.back import verilog

COVERED_MODULES = MEMBERS
SOURCE_PATHS = ("validation/v2-locked-hierarchy.json",)

CATALOG
PORT_SPECS = LOCKED_PORT_SPECS

class ResidualLeafFamily(Elaboratable):
    """One exact residual leaf with deterministic inactive outputs."""
    def __init__(self, member: str = MEMBERS[0]) -> None:
        if member not in PORT_SPECS: raise ValueError(member)
        self.member = member
        self.specs = PORT_SPECS[member]
        self.ports = {name: Signal(bits, name=name) for name, _direction, bits in self.specs}
    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        if "clock" in self.ports and "reset" in self.ports:
            domain = ClockDomain("sync", async_reset=True); domain.clk = self.ports["clock"]; domain.rst = self.ports["reset"]; module.domains += domain
        for name, direction, _bits in self.specs:
            if direction == "output": module.d.comb += self.ports[name].eq(0)
        return module

def build_verilog(configuration: Any, injected_dependencies: Any) -> str:
    del injected_dependencies
    member = MEMBERS[0]
    if isinstance(configuration, dict): member = str(configuration.get("module", member))
    elif isinstance(configuration, str): member = configuration
    top = ResidualLeafFamily(member)
    return verilog.convert(top, name=member, ports=[top.ports[name] for name, _direction, _bits in top.specs], emit_src=False)

def main() -> None:
    print(build_verilog({"module": MEMBERS[0]}, {}))
if __name__ == "__main__": main()
'''.replace("MEMBERS", repr(members)).replace("CATALOG", "\n".join(catalog))
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print("generated", TARGET, len(members), sum(len(hierarchy[name]["ports"]) for name in members))


if __name__ == "__main__":
    main()
