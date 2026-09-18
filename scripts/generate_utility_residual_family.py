"""Generate a source-grouped utility/protocol family from locked V2 leaves."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Dependency.Utility.ResidualFamily-Hardware.py"
MEMBERS = ("CSA3to2", "CSA3to2_20", "CSA3to2_24", "CSA4to2", "CSA_Nto2With3to2MainPipeline", "ClockGate", "DebugTransportModuleJTAG", "IDPool", "JtagStateMachine", "JtagTapController", "MaxPeriodFibonacciLFSR", "MaxPeriodFibonacciLFSR_3", "OverrideableQueue", "OverrideableQueue_1", "TimeAsync", "r4_qds_v2", "r4_qds_v2_spec", "skidBufferConnect", "PrintCommitIDModule")


def width(token: str) -> int:
    match = re.search(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", token); return abs(int(match.group(1)) - int(match.group(2))) + 1 if match else 1


def main() -> None:
    h = json.loads((ROOT / "validation/v2-locked-hierarchy.json").read_text(encoding="utf-8"))["modules"]
    lines = ["LOCKED_PORT_SPECS: dict[str, tuple[tuple[str, str, int], ...]] = {"]
    for member in MEMBERS:
        lines.append(f'    "{member}": (')
        for port in h[member]["ports"]: lines.append(f'        ("{port["name"]}", "{port["direction"]}", {width(str(port.get("width", "")))}),')
        lines.append("    ),")
    lines.append("}")
    source = '''"""UHSC V2 utility/protocol residual leaf family.

This source-grouped family replaces the broad residual compatibility subject
for arithmetic helpers, debug/JTAG, queues, clocks, LFSRs and vector plumbing.
Behavior beyond deterministic inactive defaults remains explicitly pending.
"""
from __future__ import annotations
from typing import Any
from amaranth import ClockDomain, Elaboratable, Module, Signal
from amaranth.back import verilog
COVERED_MODULES = MEMBERS
SOURCE_PATHS = ("upstream/rocket-chip/src/main/scala/util", "upstream/rocket-chip/src/main/scala/jtag", "upstream/src/main/scala/utils", "upstream/yunsuan/src/main/scala")
CATALOG
PORT_SPECS = LOCKED_PORT_SPECS
class UtilityResidualFamily(Elaboratable):
    def __init__(self, member: str = MEMBERS[0]) -> None:
        if member not in PORT_SPECS: raise ValueError(member)
        self.member = member; self.specs = PORT_SPECS[member]; self.ports = {n: Signal(w, name=n) for n, _d, w in self.specs}
    def elaborate(self, platform: Any) -> Module:
        del platform; module = Module()
        if "clock" in self.ports and "reset" in self.ports:
            domain = ClockDomain("sync", async_reset=True); domain.clk = self.ports["clock"]; domain.rst = self.ports["reset"]; module.domains += domain
        for n, d, _w in self.specs:
            if d == "output": module.d.comb += self.ports[n].eq(0)
        return module
def build_verilog(configuration: Any, injected_dependencies: Any) -> str:
    del injected_dependencies; member = MEMBERS[0]
    if isinstance(configuration, dict): member = str(configuration.get("module", member))
    elif isinstance(configuration, str): member = configuration
    top = UtilityResidualFamily(member); return verilog.convert(top, name=member, ports=[top.ports[n] for n, _d, _w in top.specs], emit_src=False)
def main() -> None: print(build_verilog({"module": MEMBERS[0]}, {}))
if __name__ == "__main__": main()
'''.replace("MEMBERS", repr(MEMBERS)).replace("CATALOG", "\n".join(lines))
    TARGET.write_text(source, encoding="utf-8", newline="\n"); print("generated", TARGET, len(MEMBERS))
if __name__ == "__main__": main()
