"""Basic rewrite-freeze gates for the four OpenLLC aggregate Build files.
四个 OpenLLC 聚合 Build 文件的重写冻结基础门禁。

The runner is intentionally structural.  It checks exact-path loading,
deterministic same-name Verilog export and backend syntax; family behaviour
and locked-XSTop closure remain a separate batch-validation milestone.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import py_compile
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast


# =============================================================================
# Module Contract
# =============================================================================
ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory"
OUT = ROOT / "validation/v2-openllc-rewrite-freeze-basic-results.json"
TARGETS = tuple(BUILD / name for name in (
    "Build-Cpu.Dependency.OpenLLC.Cache-Hardware.py",
    "Build-Cpu.Dependency.OpenLLC.Sram-Hardware.py",
    "Build-Cpu.Dependency.OpenLLC.Bridge-Hardware.py",
    "Build-Cpu.Dependency.OpenLLC.OpenNCB-Hardware.py",
))


# =============================================================================
# Configuration
# =============================================================================
def load_exact(path: Path) -> Any:
    """Load a Build file by exact path without changing process search paths. / 按精确路径加载 Build 文件且不修改进程搜索路径。"""

    name = "v2_openllc_" + hashlib.sha256(str(path).encode()).hexdigest()[:16]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Audit zones and bilingual callable documentation. / 审计分区及双语可调用对象文档。
def style_gate(source: str) -> dict[str, object]:
    """Return the five-zone and function-comment results. / 返回五区和函数注释结果。"""

    tree = ast.parse(source)
    zone_names = ("Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry")
    positions = [source.find(f"# {name}") for name in zone_names]
    lines = source.splitlines()
    functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    missing: list[str] = []
    for node in functions:
        if ast.get_docstring(node):
            continue
        prior = lines[max(0, node.lineno - 4):node.lineno - 1]
        if not any("/" in line or "中文" in line for line in prior):
            missing.append(node.name)
    return {
        "five_zone_order": all(value >= 0 for value in positions) and positions == sorted(positions),
        "bilingual_function_comments": not missing,
        "function_comment_errors": missing,
    }


# Run Verilator and Yosys against one generated artifact. / 对生成产物运行 Verilator 与 Yosys。
def backend_gate(rtl: str, module_name: str, directory: Path) -> dict[str, object]:
    """Return backend syntax results. / 返回后端语法检查结果。"""

    target = directory / f"{module_name}.sv"
    target.write_text(rtl, encoding="utf-8", newline="\n")
    translated = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(target)],
                                capture_output=True, text=True, check=True).stdout.strip()
    verilator = subprocess.run(["wsl.exe", "-e", "bash", "-lc",
                                f"verilator --lint-only -Wno-fatal '{translated}'"],
                               capture_output=True, text=True, check=False)
    yosys = subprocess.run(["wsl.exe", "-e", "bash", "-lc",
                            f"yosys -Q -p 'read_verilog -sv {translated}; hierarchy -top {module_name}; proc; check'"],
                           capture_output=True, text=True, check=False)
    return {
        "verilator": {"status": "PASS" if verilator.returncode == 0 else "FAIL", "returncode": verilator.returncode},
        "yosys": {"status": "PASS" if yosys.returncode == 0 else "FAIL", "returncode": yosys.returncode},
        "output_tail": (verilator.stdout + verilator.stderr + yosys.stdout + yosys.stderr)[-1200:],
    }


# =============================================================================
# Implementation
# =============================================================================
def check_target(path: Path, work: Path) -> dict[str, Any]:
    """Run all structural gates for one OpenLLC aggregate. / 对一个 OpenLLC 聚合运行全部结构门禁。"""

    raw = path.read_bytes()
    source = raw.decode("utf-8")
    style = style_gate(source)
    record: dict[str, Any] = {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "utf8_lf": not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw,
        "ast": False,
        "py_compile": False,
        "exact_path_import": False,
        "format": style,
    }
    ast.parse(source)
    record["ast"] = True
    py_compile.compile(str(path), doraise=True)
    record["py_compile"] = True
    module = load_exact(path)
    record["exact_path_import"] = True
    configs: dict[str, Any] = {"sets": 2, "ways": 2, "banks": 2, "client_sets": 2,
                               "client_ways": 2, "depth": 4, "address_bits": 16,
                               "node_id_bits": 4, "txn_id_bits": 4, "data_bits": 64,
                               "outstanding_depth": 2}
    first = module.build_verilog(configs, {})
    second = module.build_verilog(configs, {})
    match = re.search(r"(?m)^module\s+([A-Za-z_][A-Za-z0-9_$]*)\b", first)
    record["build_verilog"] = {"status": "PASS" if match else "FAIL",
                                "deterministic_export": first == second,
                                "module_name": match.group(1) if match else None,
                                "rtl_bytes": len(first.encode("utf-8"))}
    record["verilog_syntax"] = backend_gate(first, match.group(1), work) if match else {
        "verilator": {"status": "FAIL"}, "yosys": {"status": "FAIL"}}
    syntax = cast(dict[str, Any], record["verilog_syntax"])
    build = cast(dict[str, Any], record["build_verilog"])
    record["pass"] = bool(record["utf8_lf"] and record["ast"] and record["py_compile"]
                           and record["exact_path_import"] and style["five_zone_order"]
                           and style["bilingual_function_comments"] and build["status"] == "PASS"
                           and build["deterministic_export"] and syntax["verilator"]["status"] == "PASS"
                           and syntax["yosys"]["status"] == "PASS")
    return record


# =============================================================================
# Public Adapter
# =============================================================================
def main() -> int:
    """Run the batch and write machine-readable evidence. / 运行批次并写入机器可读证据。"""

    with TemporaryDirectory(prefix="v2_openllc_freeze_") as temporary:
        records = {path.stem: check_target(path, Path(temporary)) for path in TARGETS}
    executable = "pyright.cmd" if os.name == "nt" else "pyright"
    pyright = subprocess.run([executable, "--outputjson", *map(str, TARGETS)],
                             capture_output=True, text=True, check=False)
    diagnostics = json.loads(pyright.stdout) if pyright.stdout else {"summary": {"errorCount": -1, "warningCount": -1}}
    errors = int(diagnostics.get("summary", {}).get("errorCount", -1))
    passed = all(bool(value["pass"]) for value in records.values()) and errors == 0
    result = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_OPENLLC_REWRITE_FREEZE_BASIC",
        "phase": "REWRITE_FREEZE",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "targets": records,
        "pyright": {"version": diagnostics.get("version"), "error_count": errors,
                    "warning_count": diagnostics.get("summary", {}).get("warningCount", -1)},
        "gates": {"REWRITE_FREEZE_BASIC": "PASS" if passed else "FAIL",
                  "STRUCTURE_VERIFIED": "PASS" if passed else "PENDING",
                  "BEHAVIOR_VERIFIED_openLLC": "PENDING_BATCH_VALIDATION",
                  "PYRIGHT": "PASS" if errors == 0 else "FAIL", "ACCEPTED": "NOT_ALLOWED"},
        "status": "REWRITE_FREEZE_BASIC_PASS" if passed else "REWRITE_FREEZE_BASIC_FAIL",
        "unclosed": ["Family direct/reference and locked-XSTop differential remain pending.",
                     "Selected-top parent closure, license audit, and user approval remain pending."],
        "acceptance_eligible": False,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": result["status"], "targets": len(records), "pyright_errors": errors}))
    return 0 if passed else 1


# =============================================================================
# Direct Entry
# =============================================================================
if __name__ == "__main__":
    raise SystemExit(main())
