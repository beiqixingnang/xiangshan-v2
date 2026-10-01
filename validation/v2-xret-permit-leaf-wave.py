"""Focused bounded gate for the local XRetPermitModule leaf."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import py_compile
import subprocess
import sys
import shlex

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Cpu-Core-Backend.Fu.NewCSR.XRetPermit-Hardware.py"
DIRECT = ROOT / "python/Program-System/System-Testing/Testing-Cpu/Testing-Cpu-Backend.Fu.NewCSR.XRetPermit-Hardware.py"
REFERENCE = ROOT / "validation/reference-sv/XRetPermitModule.sv"
EVIDENCE = ROOT / "validation/v2-xret-permit-leaf-wave.json"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(path: Path):
    spec = importlib.util.spec_from_file_location("xret_wave", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_wsl(command: list[str]) -> dict[str, object]:
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", " ".join(shlex.quote(item) for item in command)],
                            capture_output=True, check=False)
    output = result.stdout + result.stderr
    return {"status": "PASS" if result.returncode == 0 else "FAIL",
            "returncode": result.returncode, "output_tail": output.decode("utf-8", "replace")[-1500:]}


def main() -> int:
    module = load(BUILD)
    py_compile.compile(str(BUILD), doraise=True)
    py_compile.compile(str(DIRECT), doraise=True)
    rtl = module.build_verilog({"module": "XRetPermitModule"}, {})
    rtl2 = module.build_verilog({"module": "XRetPermitModule"}, {})
    direct = subprocess.run([sys.executable, "-B", str(DIRECT.relative_to(ROOT))], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    work = ROOT / "validation/.work/xret-permit-leaf-wave"
    work.mkdir(parents=True, exist_ok=True)
    target = work / "XRetPermitModule.sv"
    target.write_text(rtl, encoding="utf-8", newline="\n")
    target_wsl = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(target)], capture_output=True, check=True).stdout.decode().strip()
    verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal", target_wsl])
    yosys = run_wsl(["yosys", "-Q", "-p", f"read_verilog -sv {target_wsl}; hierarchy -check -top XRetPermitModule; proc; stat; check"])
    expected = module.PORT_SPECS
    payload = {"schema_version": 1, "kind": "V2_XRET_PERMIT_LEAF_WAVE", "member": "XRetPermitModule",
               "build": {"path": BUILD.relative_to(ROOT).as_posix(), "sha256": digest(BUILD.read_bytes()),
                         "rtl_sha256": digest(rtl.encode()), "rtl_bytes": len(rtl.encode())},
               "reference": {"path": REFERENCE.relative_to(ROOT).as_posix(),
                             "sha256": digest(REFERENCE.read_bytes()) if REFERENCE.is_file() else None},
               "abi_port_count": len(expected), "deterministic": rtl == rtl2,
               "direct": {"status": "PASS" if direct.returncode == 0 else "FAIL", "returncode": direct.returncode,
                          "output_tail": (direct.stdout + direct.stderr)[-1200:]},
               "verilator": verilator, "yosys": yosys,
               "status": "IMPLEMENTED_UNVERIFIED_STRICT_PENDING" if direct.returncode == 0 and rtl == rtl2 and verilator["status"] == yosys["status"] == "PASS" else "FAIL",
               "strict_delta": 0, "acceptance_eligible": False,
               "unclosed": ["Locked reference differential/formal, parent closure, license and acceptance remain pending."]}
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "direct": payload["direct"]["status"], "verilator": verilator["status"], "yosys": yosys["status"]}))
    return 0 if payload["status"].startswith("IMPLEMENTED_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
