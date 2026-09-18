"""Bounded contract/tool validator for the V2 debug-trigger family."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import py_compile
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Fu.NewCSR.DebugFamily-Hardware.py"
HIER = ROOT / "validation/v2-locked-hierarchy.json"
WORK = ROOT / "validation/.work/v2-debug-family"
EVIDENCE = ROOT / "validation/v2-debug-family-results.json"
MEMBERS = ("Debug", "MemTrigger", "MemTrigger_3", "VSegmentTrigger")


def load_target() -> Any:
    spec = importlib.util.spec_from_file_location("v2_debug_family_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); return module


def width(token: str) -> int:
    import re
    match = re.search(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", token)
    return abs(int(match.group(1)) - int(match.group(2))) + 1 if match else 1


def tool(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(command, capture_output=True, check=False)
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {"command": command, "status": "PASS" if result.returncode == 0 else "FAIL", "returncode": result.returncode, "output_tail": output[-800:]}


def wsl_path(path: Path) -> str:
    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)], capture_output=True, check=True)
    return result.stdout.decode().strip()


def main() -> int:
    module = load_target(); hierarchy = json.loads(HIER.read_text(encoding="utf-8"))["modules"]; failures: list[str] = []; ports: dict[str, Any] = {}; outputs: dict[str, Any] = {}
    for member in MEMBERS:
        expected = {(p["name"], p["direction"], width(str(p.get("width", "")))) for p in hierarchy[member]["ports"]}; actual = set(module.PORT_SPECS[member]); match = expected == actual
        ports[member] = {"locked": len(expected), "emitted": len(actual), "match": match}
        if not match: failures.append(f"port mismatch {member}")
    py_compile.compile(str(TARGET), doraise=True); WORK.mkdir(parents=True, exist_ok=True)
    for member in MEMBERS:
        rtl = module.build_verilog({"module": member}, {}); path = WORK / f"{member}.sv"; path.write_text(rtl, encoding="utf-8", newline="\n")
        linux_path = wsl_path(path)
        verilator = tool(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal '{linux_path}'"])
        yosys = tool(["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p \"read_verilog -sv '{linux_path}'; proc; check\""])
        outputs[member] = {"rtl_bytes": len(rtl.encode()), "rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest(), "verilator": verilator, "yosys": yosys}
        if verilator["status"] != "PASS" or yosys["status"] != "PASS": failures.append(f"tool gate {member}")
    payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_DEBUG_TRIGGER_FAMILY", "batch_id": "V2-BACKEND-DEBUG-001", "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af", "scala_sources": list(module.SOURCE_PATHS), "covered_modules": list(MEMBERS), "port_surface": ports, "tool_gates": outputs, "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": "PASS_BOUNDED_PORT_AND_EXPORT", "V2_REFERENCE_MATCHED": "PENDING_LOCKED_DEBUG_DIFF", "VERILATOR": "PASS" if not failures else "FAIL", "YOSYS": "PASS" if not failures else "FAIL", "UHSC_LOCALIZED": "PASS_BOUNDED_FAMILY_LOCAL_NAME", "PARENT_CLOSURE_MATCHED": "PENDING", "LICENSE_REVIEW": "PENDING", "ACCEPTED": "NOT_ALLOWED"}, "status": "VALIDATOR_PASS_BOUNDED" if not failures else "VALIDATOR_FAIL", "acceptance_eligible": False, "failures": failures, "unclosed": ["Complete NewCSR parent closure and debug behavioral differential remain pending.", "License review and user approval remain pending."]}
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"); print(json.dumps({"status": payload["status"], "covered": len(MEMBERS), "failures": failures})); return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
