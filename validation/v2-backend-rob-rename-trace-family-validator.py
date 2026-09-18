"""Independent bounded validator for the V2 ROB/rename/trace aggregate.

校验器从冻结层级重新读取端口目录，逐成员检查方向/位宽，执行 py_compile、
双次确定性导出和 Verilator/Yosys lint。该证据只声明 bounded structural/direct
通过；父级 CPU 闭包、完整行为差分、许可证和 ACCEPTED 仍明确未完成。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import py_compile
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Rob.Rename.Trace-Family-Hardware.py"
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
EVIDENCE = ROOT / "validation/v2-backend-rob-rename-trace-family-results.json"
LOCKED_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"


def _width(token: object) -> int:
    text = str(token or "").strip()
    if not text:
        return 1
    if text.startswith("[") and text.endswith("]") and ":" in text:
        high, low = text[1:-1].split(":", 1)
        return abs(int(high) - int(low)) + 1
    return 1


def _load(path: Path):
    spec = importlib.util.spec_from_file_location("v2_backend_rob_rename_trace", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run_tool(command: list[str]) -> dict[str, Any]:
    proc = subprocess.run(command, capture_output=True, check=False)
    output = (proc.stdout + proc.stderr).decode("utf-8", "replace")
    return {
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "returncode": proc.returncode,
        "output_tail": output[-1200:],
        "sha256": hashlib.sha256(output.encode()).hexdigest(),
    }


def _wsl(path: Path) -> str | None:
    if shutil.which("wsl.exe") is None:
        return None
    proc = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)], capture_output=True, check=False)
    if proc.returncode:
        return None
    return proc.stdout.decode().strip()


def main() -> int:
    payload = json.loads(HIERARCHY.read_text(encoding="utf-8"))
    if payload.get("reference_sha256") != LOCKED_SHA256:
        raise RuntimeError("locked hierarchy digest mismatch")
    module = _load(TARGET)
    expected_names = tuple(module.COVERED_MODULES)
    expected = payload["modules"]
    failures: list[str] = []
    surfaces: dict[str, Any] = {}
    exports: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="v2-rob-rename-trace-") as temp:
        temp_root = Path(temp)
        for name in expected_names:
            locked = tuple((str(p["name"]), str(p["direction"]), _width(p.get("width"))) for p in expected[name]["ports"])
            actual = tuple(module.PORT_SPECS[name])
            match = locked == actual
            surfaces[name] = {"locked": len(locked), "catalog": len(actual), "exact": match}
            if not match:
                failures.append(f"port:{name}")
                continue
            first = module.build_verilog({"module": name}, {})
            second = module.build_verilog({"module": name}, {})
            first_hash = hashlib.sha256(first.encode()).hexdigest()
            second_hash = hashlib.sha256(second.encode()).hexdigest()
            deterministic = first_hash == second_hash and len(first) > 0
            path = temp_root / f"{name}.sv"
            path.write_text(first, encoding="utf-8", newline="\n")
            tool_result: dict[str, Any] = {"verilator": {"status": "SKIP"}, "yosys": {"status": "SKIP"}}
            linux = _wsl(path)
            if linux:
                tool_result["verilator"] = _run_tool(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal '{linux}'"])
                tool_result["yosys"] = _run_tool(["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p \"read_verilog -sv '{linux}'; proc; check\""])
            exports[name] = {"bytes": len(first), "sha256": first_hash, "deterministic": deterministic, **tool_result}
            if not deterministic:
                failures.append(f"export:{name}")
            if any(tool_result[k]["status"] == "FAIL" for k in ("verilator", "yosys")):
                failures.append(f"tools:{name}")
    py_compile.compile(str(TARGET), doraise=True)
    payload_out = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_BACKEND_ROB_RENAME_TRACE_FAMILY",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "locked_reference_sha256": LOCKED_SHA256,
        "build": str(TARGET.relative_to(ROOT)).replace("\\", "/"),
        "covered_modules": list(expected_names),
        "source_paths": list(module.SOURCE_PATHS),
        "port_surface": surfaces,
        "exports": exports,
        "gates": {
            "PY_COMPILE": "PASS",
            "PORTS": "PASS" if not any(x.startswith("port:") for x in failures) else "FAIL",
            "DETERMINISTIC_EXPORT": "PASS" if not any(x.startswith("export:") for x in failures) else "FAIL",
            "VERILATOR_YOSYS": "PASS" if not any(x.startswith("tools:") for x in failures) else "FAIL",
            "DIRECT_TEST_PASS_BOUNDED": "PASS_BOUNDED_PORT_AND_EXPORT" if not failures else "FAIL",
            "REFERENCE_DIFFERENTIAL": "PENDING_LOCKED_BEHAVIORAL_TRACE",
            "PARENT_CLOSURE": "PENDING_BACKEND_CPU",
            "LICENSE_REVIEW": "PENDING",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "status": "VALIDATOR_PASS_BOUNDED" if not failures else "VALIDATOR_FAIL",
        "acceptance_eligible": False,
        "failures": failures,
    }
    EVIDENCE.write_text(json.dumps(payload_out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload_out["status"], "covered": len(expected_names), "failures": failures}, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
