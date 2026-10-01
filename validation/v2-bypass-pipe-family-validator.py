"""Bounded contract/tool validator for the V2 bypass/pipe family."""

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

from v2_build_provenance import source_paths_for_build

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Cpu-Core-Backend.Datapath.BypassPipeFamily-Hardware.py"
DIRECT_TEST = ROOT / "python/Program-System/System-Testing/Testing-Cpu/Testing-Cpu-Backend.Datapath.BypassPipeFamily-Hardware.py"
HIER = ROOT / "validation/v2-locked-hierarchy.json"
WORK = ROOT / "validation/.work/v2-bypass-pipe-family"
EVIDENCE = ROOT / "validation/v2-bypass-pipe-family-results.json"
MEMBERS = ("BypassNetwork", "PipeGroupConnect")


def load_target() -> Any:
    spec = importlib.util.spec_from_file_location("v2_bypass_pipe_target", TARGET)
    if spec is None or spec.loader is None: raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); return module


def width(token: str) -> int:
    match = re.search(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", token)
    return abs(int(match.group(1)) - int(match.group(2))) + 1 if match else 1


def run(command: list[str], *, cwd: Path | None = None) -> dict[str, Any]:
    result = subprocess.run(command, capture_output=True, check=False, cwd=str(cwd) if cwd else None)
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {"command": command, "status": "PASS" if result.returncode == 0 else "FAIL", "returncode": result.returncode, "output_tail": output[-800:]}


def wsl_path(path: Path) -> str:
    return subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)], capture_output=True, check=True).stdout.decode().strip()


def main() -> int:
    module = load_target(); hierarchy = json.loads(HIER.read_text(encoding="utf-8"))["modules"]; failures: list[str] = []; ports: dict[str, Any] = {}; tools: dict[str, Any] = {}
    for member in MEMBERS:
        expected = {(p["name"], p["direction"], width(str(p.get("width", "")))) for p in hierarchy[member]["ports"]}; actual = set(module.PORT_SPECS[member]); ports[member] = {"locked": len(expected), "emitted": len(actual), "match": expected == actual}
        if expected != actual: failures.append(f"port mismatch {member}")
    py_compile.compile(str(TARGET), doraise=True); py_compile.compile(str(DIRECT_TEST), doraise=True)
    direct = run([sys.executable, "-B", str(DIRECT_TEST)], cwd=ROOT)
    if direct["status"] != "PASS": failures.append("behavioral direct test")
    WORK.mkdir(parents=True, exist_ok=True)
    for member in MEMBERS:
        rtl = module.build_verilog({"module": member}, {}); path = WORK / f"{member}.sv"; path.write_text(rtl, encoding="utf-8", newline="\n"); linux = wsl_path(path)
        verilator = run(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal '{linux}'"]); yosys = run(["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p \"read_verilog -sv '{linux}'; proc; check\""])
        tools[member] = {"rtl_bytes": len(rtl.encode()), "rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest(), "verilator": verilator, "yosys": yosys}
        if verilator["status"] != "PASS" or yosys["status"] != "PASS": failures.append(f"tool gate {member}")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True, check=False).stdout.decode().strip()
    payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_BYPASS_PIPE_FAMILY", "batch_id": "V2-BACKEND-DATAPATH-BYPASS-001", "source_commit": commit, "scala_sources": list(source_paths_for_build(TARGET)), "covered_modules": list(MEMBERS), "port_surface": ports, "behavioral_direct_test": direct, "tool_gates": tools, "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": "PASS_BOUNDED_BEHAVIOR" if direct["status"] == "PASS" else "FAIL", "V2_REFERENCE_MATCHED": "PENDING_LOCKED_BYPASS_DIFF", "VERILATOR": "PASS" if not failures else "FAIL", "YOSYS": "PASS" if not failures else "FAIL", "UHSC_LOCALIZED": "PASS_BOUNDED_FAMILY_LOCAL_NAME", "PARENT_CLOSURE_MATCHED": "PENDING", "LICENSE_REVIEW": "PENDING", "ACCEPTED": "NOT_ALLOWED"}, "status": "VALIDATOR_PASS_BOUNDED" if not failures else "VALIDATOR_FAIL", "acceptance_eligible": False, "failures": failures, "unclosed": ["BypassNetwork remains contract-only; complete family behavior and locked-reference differential remain pending.", "Parent closure, license review, and user approval remain pending."]}
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"); print(json.dumps({"status": payload["status"], "covered": len(MEMBERS), "failures": failures})); return 0 if not failures else 1


if __name__ == "__main__": raise SystemExit(main())
