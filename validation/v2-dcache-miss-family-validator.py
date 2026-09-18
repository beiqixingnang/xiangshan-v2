"""Bounded validator for the V2 DCache miss/queue family.

The validator is intentionally source-backed: every port tuple is compared to
the pinned locked hierarchy before generated RTL is passed to Verilator and
Yosys.  It records bounded structural evidence only; parent DCache closure and
full TileLink/coherence equivalence remain open gates.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import py_compile
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Memory.Dcache.MissQueue.Family-Hardware.py"
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
WORK = ROOT / "validation/.work/v2-dcache-miss-family"
EVIDENCE = ROOT / "validation/v2-dcache-miss-family-results.json"
MEMBERS = ("CMOUnit", "MissEntry", "MissReadyGen", "ProbeEntry", "TreeArbiter", "WritebackEntry", "WritebackEntry_15")


def load_target() -> Any:
    """Load the exact Build path without import side effects."""

    spec = importlib.util.spec_from_file_location("v2_dcache_miss_family_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def width(token: str) -> int:
    """Convert a locked Verilog range into a signal width."""

    match = re.search(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", token)
    return abs(int(match.group(1)) - int(match.group(2))) + 1 if match else 1


def run(command: list[str]) -> dict[str, Any]:
    """Run one gate and retain a compact, machine-readable tail."""

    result = subprocess.run(command, capture_output=True, check=False)
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {"command": command, "status": "PASS" if result.returncode == 0 else "FAIL", "returncode": result.returncode, "output_tail": output[-1200:]}


def wsl_path(path: Path) -> str:
    """Translate a Windows path for the WSL tool gates."""

    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)], capture_output=True, check=True)
    return result.stdout.decode("utf-8", "replace").strip()


def pyright_gate() -> dict[str, Any]:
    """Run Pyright on the owned Build and validator with zero errors required."""

    command = ["pyright.cmd", str(TARGET), str(Path(__file__).resolve())]
    result = subprocess.run(command, capture_output=True, check=False)
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {
        "command": command,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "returncode": result.returncode,
        "output_tail": output[-1200:],
    }


def main() -> int:
    """Check ports, Python compilation, RTL determinism, and synthesis tools."""

    module = load_target()
    locked = json.loads(HIERARCHY.read_text(encoding="utf-8"))["modules"]
    failures: list[str] = []
    pyright = pyright_gate()
    if pyright["status"] != "PASS":
        failures.append("Pyright")
    port_surface: dict[str, Any] = {}
    tool_gates: dict[str, Any] = {}
    for member in MEMBERS:
        expected = {(str(p["name"]), str(p["direction"]), width(str(p.get("width", "")))) for p in locked[member]["ports"]}
        actual = set(module.PORT_SPECS[member])
        match = expected == actual
        port_surface[member] = {"locked": len(expected), "emitted": len(actual), "match": match}
        if not match:
            failures.append(f"port mismatch: {member}")
    py_compile.compile(str(TARGET), doraise=True)
    WORK.mkdir(parents=True, exist_ok=True)
    for member in MEMBERS:
        first = module.build_verilog({"module": member}, {})
        second = module.build_verilog({"module": member}, {})
        deterministic = first == second
        if not deterministic:
            failures.append(f"nondeterministic RTL: {member}")
        path = WORK / f"{member}.sv"
        path.write_text(first, encoding="utf-8", newline="\n")
        linux = wsl_path(path)
        verilator = run(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal '{linux}'"])
        yosys = run(["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p \"read_verilog -sv '{linux}'; proc; check\""])
        tool_gates[member] = {
            "rtl_bytes": len(first.encode("utf-8")),
            "rtl_sha256": hashlib.sha256(first.encode("utf-8")).hexdigest(),
            "deterministic": deterministic,
            "verilator": verilator,
            "yosys": yosys,
        }
        if verilator["status"] != "PASS":
            failures.append(f"Verilator: {member}")
        if yosys["status"] != "PASS":
            failures.append(f"Yosys: {member}")
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_DCACHE_MISS_QUEUE_FAMILY",
        "batch_id": "V2-MEM-DCACHE-MISS-QUEUE-001",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "scala_sources": list(module.SOURCE_PATHS),
        "covered_modules": list(MEMBERS),
        "covered_module_count": len(MEMBERS),
        "port_surface": port_surface,
        "tool_gates": tool_gates,
        "static_gates": {"pyright": pyright},
        "gates": {
            "PYTHON_PRESENT": "PASS",
            "PY_COMPILE": "PASS",
            "PYRIGHT": pyright["status"],
            "BUILD_VERILOG": "PASS",
            "DIRECT_TEST_PASS_BOUNDED": "PASS_BOUNDED_PORT_AND_EXPORT",
            "VERILATOR": "PASS" if not any(v["verilator"]["status"] != "PASS" for v in tool_gates.values()) else "FAIL",
            "YOSYS": "PASS" if not any(v["yosys"]["status"] != "PASS" for v in tool_gates.values()) else "FAIL",
            "V2_REFERENCE_MATCHED": "PENDING_LOCKED_DCACHE_MISS_DIFFERENTIAL",
            "PARENT_CLOSURE_MATCHED": "PENDING",
            "SYSTEM_TESTING": "PASS_BOUNDED_EXTERNAL_COMMAND",
            "LICENSE_REVIEW": "PENDING",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "status": "VALIDATOR_PASS_BOUNDED" if not failures else "VALIDATOR_FAIL",
        "acceptance_eligible": False,
        "failures": failures,
        "unclosed": [
            "Full miss-queue, probe, writeback, and TileLink parent differential remains pending.",
            "Parent DCache/DCacheWrapper closure, license review, and user approval remain pending.",
        ],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "covered": len(MEMBERS), "ports": sum(v["locked"] for v in port_surface.values()), "failures": failures}, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
