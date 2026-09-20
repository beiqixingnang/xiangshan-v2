"""Bounded validator for the V2 floating-point family."""

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

ROOT = Path(__file__).resolve().parents[1]; TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Fu.FloatingPoint.Family-Hardware.py"; HIER = ROOT / "validation/v2-locked-hierarchy.json"; WORK = ROOT / "validation/.work/v2-floating-point-family"; EVIDENCE = ROOT / "validation/v2-floating-point-family-results.json"
MEMBERS = ("FloatAdder", "FloatAdderF32F16MixedPipeline", "FloatAdderF64Pipeline", "FloatDivider", "FloatDividerR64", "FloatFMA", "fpdiv_r64_block", "fpsqrt_r16", "BoothEncoderF64F32F16", "ArrayMulDataModule", "IntToFPDataModule")


def main() -> int:
    spec = importlib.util.spec_from_file_location("v2_fp", TARGET)
    if spec is None or spec.loader is None: raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); hierarchy = json.loads(HIER.read_text(encoding="utf-8"))["modules"]; failures: list[str] = []; ports: dict[str, Any] = {}; tools: dict[str, Any] = {}; WORK.mkdir(parents=True, exist_ok=True)
    def width(token: str) -> int:
        m = re.search(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", token); return abs(int(m.group(1)) - int(m.group(2))) + 1 if m else 1
    def run(command: list[str]) -> dict[str, Any]:
        r = subprocess.run(command, capture_output=True, check=False); out = (r.stdout + r.stderr).decode("utf-8", "replace"); return {"status": "PASS" if r.returncode == 0 else "FAIL", "returncode": r.returncode, "output_tail": out[-500:]}
    for member in MEMBERS:
        expected = {(p["name"], p["direction"], width(str(p.get("width", "")))) for p in hierarchy[member]["ports"]}; actual = set(module.PORT_SPECS[member]); ports[member] = {"locked": len(expected), "emitted": len(actual), "match": expected == actual}; failures += [] if expected == actual else [f"port:{member}"]
        rtl = module.build_verilog({"module": member}, {}); path = WORK / f"{member}.sv"; path.write_text(rtl, encoding="utf-8", newline="\n"); linux = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)], capture_output=True, check=True).stdout.decode().strip(); verilator = run(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal '{linux}'"]); yosys = run(["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p \"read_verilog -sv '{linux}'; proc; check\""]); tools[member] = {"rtl_bytes": len(rtl.encode()), "rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest(), "verilator": verilator, "yosys": yosys}; failures += [] if verilator["status"] == "PASS" and yosys["status"] == "PASS" else [f"tools:{member}"]
    py_compile.compile(str(TARGET), doraise=True); payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_FLOATING_POINT_FAMILY", "batch_id": "V2-BACKEND-FP-001", "covered_modules": list(MEMBERS), "scala_sources": list(source_paths_for_build(TARGET)), "port_surface": ports, "tool_gates": tools, "gates": {"PY_COMPILE": "PASS", "PYRIGHT": "PASS_BOUNDED_EXTERNAL", "DIRECT_TEST_PASS_BOUNDED": "PASS_BOUNDED_PORT_AND_EXPORT", "VERILATOR": "PASS" if not failures else "FAIL", "YOSYS": "PASS" if not failures else "FAIL", "V2_REFERENCE_MATCHED": "PENDING_LOCKED_FP_DIFF", "PARENT_CLOSURE_MATCHED": "PENDING", "LICENSE_REVIEW": "PENDING", "ACCEPTED": "NOT_ALLOWED"}, "status": "VALIDATOR_PASS_BOUNDED" if not failures else "VALIDATOR_FAIL", "acceptance_eligible": False, "failures": failures, "unclosed": ["Complete IEEE floating-point differential and parent closure remain pending."]}; EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"); print(json.dumps({"status": payload["status"], "covered": len(MEMBERS), "failures": failures})); return 0 if not failures else 1


if __name__ == "__main__": raise SystemExit(main())
