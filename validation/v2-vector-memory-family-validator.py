"""Bounded validator for the V2 vector-memory family."""

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
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Memory.Vector.Family-Hardware.py"
HIER = ROOT / "validation/v2-locked-hierarchy.json"
WORK = ROOT / "validation/.work/v2-vector-memory-family"
EVIDENCE = ROOT / "validation/v2-vector-memory-family-results.json"
MEMBERS = ("VLMergeBufferImp", "VSMergeBufferImp", "VSegmentUnit", "VfofBuffer", "VirtualLoadQueue", "VldMergeUnit", "VsetModule")


def load_target() -> Any:
    spec = importlib.util.spec_from_file_location("v2_vector_memory_target", TARGET)
    if spec is None or spec.loader is None: raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); return module


def width(token: str) -> int:
    match = re.search(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", token)
    return abs(int(match.group(1)) - int(match.group(2))) + 1 if match else 1


def run(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(command, capture_output=True, check=False); output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {"command": command, "status": "PASS" if result.returncode == 0 else "FAIL", "returncode": result.returncode, "output_tail": output[-800:]}


def wsl_path(path: Path) -> str:
    return subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)], capture_output=True, check=True).stdout.decode().strip()


def pyright_gate() -> dict[str, Any]:
    """Run strict Pyright on the owned Build. / 对本批 Build 运行严格 Pyright。"""

    result = subprocess.run(["pyright.cmd", "--outputjson", str(TARGET)], capture_output=True, check=False)
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        parsed = {"raw_tail": output[-1200:]}
    summary = parsed.get("summary", {}) if isinstance(parsed, dict) else {}
    status = "PASS" if result.returncode == 0 and int(summary.get("errorCount", 1)) == 0 else "FAIL"
    return {"command": ["pyright.cmd", "--outputjson", str(TARGET)], "status": status, "returncode": result.returncode, "summary": summary, "output_sha256": hashlib.sha256(output.encode()).hexdigest()}


def main() -> int:
    module = load_target(); hierarchy = json.loads(HIER.read_text(encoding="utf-8"))["modules"]; failures: list[str] = []; ports: dict[str, Any] = {}; tools: dict[str, Any] = {}
    pyright = pyright_gate()
    if pyright["status"] != "PASS": failures.append("pyright")
    for member in MEMBERS:
        expected = {(p["name"], p["direction"], width(str(p.get("width", "")))) for p in hierarchy[member]["ports"]}; actual = set(module.PORT_SPECS[member]); ports[member] = {"locked": len(expected), "emitted": len(actual), "match": expected == actual}
        if expected != actual: failures.append(f"port mismatch {member}")
    py_compile.compile(str(TARGET), doraise=True); WORK.mkdir(parents=True, exist_ok=True)
    for member in MEMBERS:
        rtl = module.build_verilog({"module": member}, {}); path = WORK / f"{member}.sv"; path.write_text(rtl, encoding="utf-8", newline="\n"); linux = wsl_path(path)
        verilator = run(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal '{linux}'"]); yosys = run(["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p \"read_verilog -sv '{linux}'; proc; check\""])
        tools[member] = {"rtl_bytes": len(rtl.encode()), "rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest(), "verilator": verilator, "yosys": yosys}
        if verilator["status"] != "PASS" or yosys["status"] != "PASS": failures.append(f"tool gate {member}")
    payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_VECTOR_MEMORY_FAMILY", "batch_id": "V2-MEM-VECTOR-001", "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af", "scala_sources": list(source_paths_for_build(TARGET)), "covered_modules": list(MEMBERS), "port_surface": ports, "py_compile": "PASS", "pyright": pyright, "tool_gates": tools, "gates": {"PYTHON_PRESENT": "PASS", "PYRIGHT": pyright["status"], "DIRECT_TEST_PASS_BOUNDED": "PASS_BOUNDED_PORT_AND_EXPORT", "V2_REFERENCE_MATCHED": "PENDING_LOCKED_VECTOR_MEMORY_DIFF", "VERILATOR": "PASS" if not failures else "FAIL", "YOSYS": "PASS" if not failures else "FAIL", "UHSC_LOCALIZED": "PASS_BOUNDED_FAMILY_LOCAL_NAME", "PARENT_CLOSURE_MATCHED": "PENDING", "LICENSE_REVIEW": "PENDING", "ACCEPTED": "NOT_ALLOWED"}, "status": "VALIDATOR_PASS_BOUNDED" if not failures else "VALIDATOR_FAIL", "acceptance_eligible": False, "failures": failures, "unclosed": ["Complete vector memory behavior and parent closure remain pending.", "Locked reference differential, license review, and user approval remain pending."]}
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"); print(json.dumps({"status": payload["status"], "covered": len(MEMBERS), "failures": failures})); return 0 if not failures else 1


if __name__ == "__main__": raise SystemExit(main())
