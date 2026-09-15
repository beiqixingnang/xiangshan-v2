"""Basic rewrite-freeze gates for the six Backend aggregate builds.
六个 Backend 聚合 Build 的重写冻结基础门禁。
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import py_compile
import subprocess
import sys
import os
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core"
OUT = ROOT / "validation/v2-backend-rewrite-freeze-basic-results.json"
TARGETS = {
    "BackendTop": (BUILD / "Build-Cpu.Backend.Top-Hardware.py", "UHSCBackendTop"),
    "Instructions": (BUILD / "Build-Cpu.Backend.Decode.Instructions-Hardware.py", "Instructions"),
    "DeqPolicy": (BUILD / "Build-Cpu.Backend.Issue.DeqPolicy-Hardware.py", "DeqPolicy"),
    "DataArray": (BUILD / "Build-Cpu.Backend.Issue.DataArray-Hardware.py", "DataArray"),
    "FuBusyTableRead": (BUILD / "Build-Cpu.Backend.Issue.FuBusyTableRead-Hardware.py", "FuBusyTableRead"),
    "RobPtrWrappers": (BUILD / "Build-Cpu.Backend.Rob.PtrWrappers-Hardware.py", "RobPtrWrappers"),
}


# Load one target by exact path without sibling imports. / 按精确路径加载目标且不导入兄弟模块。
def load_target(path: Path, name: str):
    """Load a Build module for the smoke gate. / 为冒烟门禁加载 Build 模块。"""

    spec = importlib.util.spec_from_file_location(f"v2_freeze_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Run Verilator and Yosys syntax checks on generated RTL. / 对生成 RTL 运行 Verilator 与 Yosys 语法检查。
def syntax_gate(source: str, top: str, directory: Path) -> dict[str, object]:
    """Check generated Verilog with available WSL tools. / 使用可用 WSL 工具检查生成 Verilog。"""

    rtl = directory / f"{top}.sv"
    rtl.write_text(source, encoding="utf-8", newline="\n")
    path_result = subprocess.run(
        ["wsl.exe", "-e", "wslpath", "-a", str(rtl)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    )
    wsl_path = path_result.stdout.strip()
    verilator = subprocess.run(
        ["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal '{wsl_path}'"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    yosys = subprocess.run(
        ["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p 'read_verilog -sv {wsl_path}; hierarchy -top {top}; proc; check'"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    return {
        "verilator": "PASS" if verilator.returncode == 0 else "FAIL",
        "yosys": "PASS" if yosys.returncode == 0 else "FAIL",
        "verilator_returncode": verilator.returncode,
        "yosys_returncode": yosys.returncode,
        "stderr_tail": (verilator.stderr + yosys.stderr)[-800:],
    }


# Execute all cheap gates in one coherent batch. / 在一个连贯批次中执行全部轻量门禁。
def main() -> int:
    """Run static, import, export, and syntax gates. / 运行静态、导入、导出和语法门禁。"""

    records: dict[str, dict[str, object]] = {}
    with TemporaryDirectory(prefix="v2_backend_freeze_") as temporary:
        directory = Path(temporary)
        for name, (path, top) in TARGETS.items():
            payload: dict[str, object] = {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "utf8_lf": False,
                "ast": False,
                "py_compile": False,
                "exact_import": False,
                "build_verilog": False,
                "module_decl": False,
            }
            raw = path.read_bytes()
            payload["utf8_lf"] = raw.decode("utf-8") and b"\r" not in raw and not raw.startswith(b"\xef\xbb\xbf")
            ast.parse(raw.decode("utf-8"))
            payload["ast"] = True
            py_compile.compile(str(path), doraise=True)
            payload["py_compile"] = True
            module = load_target(path, name)
            payload["exact_import"] = True
            source = module.build_verilog(None, {})
            payload["build_verilog"] = isinstance(source, str) and bool(source)
            payload["generated_bytes"] = len(source.encode("utf-8"))
            payload["module_decl"] = f"module {top}" in source
            payload["syntax"] = syntax_gate(source, top, directory)
            payload["pass"] = all((payload["utf8_lf"], payload["ast"], payload["py_compile"], payload["exact_import"], payload["build_verilog"], payload["module_decl"], payload["syntax"]["verilator"] == "PASS", payload["syntax"]["yosys"] == "PASS"))
            records[name] = payload
    pyright_executable = "pyright.cmd" if os.name == "nt" else "pyright"
    pyright = subprocess.run([pyright_executable, "--outputjson", *[str(path) for path, _ in TARGETS.values()]], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    pyright_data = json.loads(pyright.stdout) if pyright.stdout else {"version": "unavailable", "summary": {"errorCount": -1}}
    passed = all(bool(record["pass"]) for record in records.values()) and int(pyright_data.get("summary", {}).get("errorCount", 1)) == 0
    result = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_BACKEND_REWRITE_FREEZE_BASIC",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "targets": records,
        "pyright": {"version": pyright_data.get("version"), "error_count": pyright_data.get("summary", {}).get("errorCount"), "warning_count": pyright_data.get("summary", {}).get("warningCount")},
        "gates": {"REWRITE_FREEZE_BASIC": "PASS" if passed else "FAIL", "STRUCTURE_VERIFIED": "PASS" if passed else "PENDING", "BEHAVIOR_VERIFIED_backend": "PENDING", "ACCEPTED": "NOT_ALLOWED"},
        "status": "REWRITE_FREEZE_BASIC_PASS" if passed else "REWRITE_FREEZE_BASIC_FAIL",
        "acceptance_eligible": False,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": result["status"], "targets": len(records), "pyright_errors": result["pyright"]["error_count"]}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
