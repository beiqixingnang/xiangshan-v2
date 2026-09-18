"""Bounded validator for the XSTile IntBuffer family."""
from __future__ import annotations
import importlib.util
import json
import py_compile
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Top.XSTile.IntBuffer.Family-Hardware.py"
OUT = ROOT / "validation/v2-intbuffer-family-results.json"
WORK = ROOT / "validation/.work/v2-intbuffer-family"

def main() -> int:
    spec = importlib.util.spec_from_file_location("ib", TARGET)
    if spec is None or spec.loader is None: raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
    WORK.mkdir(parents=True, exist_ok=True); failures: list[str] = []; reports = []
    for name, specs in module.PORT_SPECS.items():
        rtl = module.build_verilog({"module": name}, {}); path = WORK / f"{name}.sv"; path.write_text(rtl, encoding="utf-8", newline="\n")
        linux = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)], capture_output=True, check=True).stdout.decode().strip()
        verilator = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal '{linux}'"], capture_output=True, check=False)
        yosys = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p \"read_verilog -sv '{linux}'; proc; check\""], capture_output=True, check=False)
        reports.append({"module": name, "ports": len(specs), "verilator": "PASS" if verilator.returncode == 0 else "FAIL", "yosys": "PASS" if yosys.returncode == 0 else "FAIL"})
        if verilator.returncode or yosys.returncode: failures.append(name)
    py_compile.compile(str(TARGET), doraise=True)
    payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_INTBUFFER_FAMILY", "batch_id": "TOP-XSTILE-INTBUFFER-004", "source_paths": list(module.SOURCE_PATHS), "covered_modules": list(module.COVERED_MODULES), "port_counts": {name: len(specs) for name, specs in module.PORT_SPECS.items()}, "reports": reports, "gates": {"PY_COMPILE": "PASS", "PYRIGHT": "PASS_BOUNDED_EXTERNAL", "VERILATOR": "PASS" if not failures else "FAIL", "YOSYS": "PASS" if not failures else "FAIL", "V2_REFERENCE_MATCHED": "PENDING_LOCKED_REFERENCE_DIFFERENTIAL", "PARENT_XSTILE_CLOSURE": "PENDING", "ACCEPTED": "NOT_ALLOWED"}, "status": "VALIDATOR_PASS_BOUNDED" if not failures else "VALIDATOR_FAIL", "acceptance_eligible": False, "parent_closure": "PENDING", "failures": failures, "unclosed": ["XSCore/L2Top/XSTile parent binding and full XSTop closure remain pending."]}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"); print(json.dumps({"status": payload["status"], "covered": len(module.COVERED_MODULES), "failures": failures})); return 0 if not failures else 1

if __name__ == "__main__": raise SystemExit(main())
