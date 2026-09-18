"""Bounded validator for the utility/protocol residual family."""
from __future__ import annotations
import importlib.util, json, py_compile, subprocess, sys
from pathlib import Path
from typing import Any
ROOT = Path(__file__).resolve().parents[1]; TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Dependency.Utility.ResidualFamily-Hardware.py"; OUT = ROOT / "validation/v2-utility-residual-family-results.json"; WORK = ROOT / "validation/.work/v2-utility-residual-family"
def main() -> int:
    spec = importlib.util.spec_from_file_location("util_res", TARGET)
    if spec is None or spec.loader is None: raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); WORK.mkdir(parents=True, exist_ok=True); failures: list[str] = []; tools: dict[str, Any] = {}
    for member in module.COVERED_MODULES:
        rtl = module.build_verilog({"module": member}, {}); path = WORK / f"{member}.sv"; path.write_text(rtl, encoding="utf-8", newline="\n"); linux = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)], capture_output=True, check=True).stdout.decode().strip();
        def run(command: list[str]) -> dict[str, Any]:
            r = subprocess.run(command, capture_output=True, check=False); return {"status": "PASS" if r.returncode == 0 else "FAIL", "returncode": r.returncode, "output_tail": (r.stdout + r.stderr).decode("utf-8", "replace")[-300:]}
        v = run(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal '{linux}'"]); y = run(["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p \"read_verilog -sv '{linux}'; proc; check\""]); tools[member] = {"verilator": v, "yosys": y}; failures += [] if v["status"] == "PASS" and y["status"] == "PASS" else [member]
    py_compile.compile(str(TARGET), doraise=True); payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_UTILITY_RESIDUAL_FAMILY", "covered_modules": list(module.COVERED_MODULES), "tool_gates": tools, "gates": {"PY_COMPILE": "PASS", "PYRIGHT": "PASS_BOUNDED_EXTERNAL", "VERILATOR": "PASS" if not failures else "FAIL", "YOSYS": "PASS" if not failures else "FAIL", "V2_REFERENCE_MATCHED": "PENDING_SOURCE_FAMILY_DIFF", "ACCEPTED": "NOT_ALLOWED"}, "status": "VALIDATOR_PASS_BOUNDED" if not failures else "VALIDATOR_FAIL", "acceptance_eligible": False, "failures": failures, "unclosed": ["Source-specific behavior and parent closure remain pending."]}; OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"); print(json.dumps({"status": payload["status"], "covered": len(module.COVERED_MODULES), "failures": failures})); return 0 if not failures else 1
if __name__ == "__main__": raise SystemExit(main())
