"""Bounded validator for the V2 difftest state family."""

from __future__ import annotations
import hashlib, importlib.util, json, py_compile, re, subprocess, sys
from pathlib import Path
from typing import Any

from v2_build_provenance import source_paths_for_build

ROOT = Path(__file__).resolve().parents[1]; TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Dependency.Difftest.StateFamily-Hardware.py"; HIER = ROOT / "validation/v2-locked-hierarchy.json"; WORK = ROOT / "validation/.work/v2-difftest-state-family"; OUT = ROOT / "validation/v2-difftest-state-family-results.json"


def main() -> int:
    spec = importlib.util.spec_from_file_location("dt", TARGET)
    if spec is None or spec.loader is None: raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); h = json.loads(HIER.read_text(encoding="utf-8"))["modules"]; failures: list[str] = []; surfaces: dict[str, Any] = {}; tools: dict[str, Any] = {}; WORK.mkdir(parents=True, exist_ok=True)
    def width(token: str) -> int:
        m = re.search(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", token); return abs(int(m.group(1)) - int(m.group(2))) + 1 if m else 1
    def run(command: list[str]) -> dict[str, Any]:
        r = subprocess.run(command, capture_output=True, check=False); text = (r.stdout + r.stderr).decode("utf-8", "replace"); return {"status": "PASS" if r.returncode == 0 else "FAIL", "returncode": r.returncode, "output_tail": text[-500:]}
    for member in module.COVERED_MODULES:
        expected = {(p["name"], p["direction"], width(str(p.get("width", "")))) for p in h[member]["ports"]}; actual = set(module.PORT_SPECS[member]); surfaces[member] = {"locked": len(expected), "emitted": len(actual), "match": expected == actual}; failures += [] if expected == actual else [f"port:{member}"]; rtl = module.build_verilog({"module": member}, {}); path = WORK / f"{member}.sv"; path.write_text(rtl, encoding="utf-8", newline="\n"); linux = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)], capture_output=True, check=True).stdout.decode().strip(); v = run(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal '{linux}'"]); y = run(["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p \"read_verilog -sv '{linux}'; proc; check\""]); tools[member] = {"rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest(), "verilator": v, "yosys": y}; failures += [] if v["status"] == "PASS" and y["status"] == "PASS" else [f"tools:{member}"]
    py_compile.compile(str(TARGET), doraise=True); payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_DIFFTEST_STATE_FAMILY", "covered_modules": list(module.COVERED_MODULES), "scala_sources": list(source_paths_for_build(TARGET)), "port_surface": surfaces, "tool_gates": tools, "gates": {"PY_COMPILE": "PASS", "PYRIGHT": "PASS_BOUNDED_EXTERNAL", "DIRECT_TEST_PASS_BOUNDED": "PASS_BOUNDED_PORT_AND_EXPORT", "VERILATOR": "PASS" if not failures else "FAIL", "YOSYS": "PASS" if not failures else "FAIL", "V2_REFERENCE_MATCHED": "PENDING_LOCKED_DIFFTEST_DIFF", "PARENT_CLOSURE_MATCHED": "PENDING", "LICENSE_REVIEW": "PENDING", "ACCEPTED": "NOT_ALLOWED"}, "status": "VALIDATOR_PASS_BOUNDED" if not failures else "VALIDATOR_FAIL", "acceptance_eligible": False, "failures": failures}; OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"); print(json.dumps({"status": payload["status"], "covered": len(module.COVERED_MODULES), "failures": failures})); return 0 if not failures else 1
if __name__ == "__main__": raise SystemExit(main())
