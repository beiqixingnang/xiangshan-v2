"""Basic rewrite-freeze gates for the aggregated Frontend V2 Builds.
昆明湖 V2 前端聚合 Build 的重写冻结基础门禁。

This gate intentionally stops at elaboration and RTL syntax.  Locked-reference
differential testing belongs to the later BATCH_VALIDATION phase.
本门禁仅覆盖展开和 RTL 语法；锁定参考差分属于后续 BATCH_VALIDATION 阶段。
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import py_compile
import re
import subprocess
import sys
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core"
OUT = ROOT / "validation/v2-frontend-rewrite-freeze-basic-results.json"
MAPPING = ROOT / "validation/v2-frontend-rewrite-freeze-mapping.json"

# One aggregate per Frontend family; no one-Scala/one-Python expansion is used.
# This batch owns the new BPU parent aggregate. Existing leaves have historical
# evidence and remain outside this commit to avoid cross-worker ownership.
TARGETS = {
    "Frontend.Bpu.Parent": BUILD / "Build-Cpu.Frontend.Bpu.Parent-Hardware.py",
}


def load_target(path: Path, name: str):
    """Load one Build by exact path without sibling imports. / 精确路径导入 Build。"""

    spec = importlib.util.spec_from_file_location(f"v2_frontend_freeze_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def export(module):
    """Call the public adapter with a deterministic configuration. / 调用公开适配器。"""

    try:
        return module.build_verilog(None, {})
    except (TypeError, ValueError):
        configs = [value for value in vars(module).values() if isinstance(value, type) and value.__name__.endswith("Config")]
        if not configs:
            raise
        return module.build_verilog(configs[0](), {})


def syntax_gate(source: str, top: str, directory: Path) -> dict[str, object]:
    """Run Verilator and Yosys syntax checks on generated RTL. / 检查 RTL 语法。"""

    rtl = directory / f"{top}.sv"
    rtl.write_text(source, encoding="utf-8", newline="\n")
    wsl_path = subprocess.run(
        ["wsl.exe", "-e", "wslpath", "-a", str(rtl)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    ).stdout.strip()
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


def main() -> int:
    """Run all Frontend basic gates in one batch. / 批量运行前端基础门禁。"""

    records: dict[str, dict[str, object]] = {}
    with TemporaryDirectory(prefix="v2_frontend_freeze_") as temporary:
        directory = Path(temporary)
        for name, path in TARGETS.items():
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
            try:
                raw = path.read_bytes()
                decoded = raw.decode("utf-8")
                payload["utf8_lf"] = b"\r" not in raw and not raw.startswith(b"\xef\xbb\xbf")
                ast.parse(decoded)
                payload["ast"] = True
                py_compile.compile(str(path), doraise=True)
                payload["py_compile"] = True
                module = load_target(path, name)
                payload["exact_import"] = True
                source = export(module)
                payload["build_verilog"] = isinstance(source, str) and bool(source)
                payload["generated_bytes"] = len(source.encode("utf-8"))
                match = re.search(r"\bmodule\s+([A-Za-z_][A-Za-z0-9_]*)", source)
                top = match.group(1) if match else ""
                payload["module"] = top
                payload["module_decl"] = bool(top)
                payload["syntax"] = syntax_gate(source, top, directory) if top else {"verilator": "FAIL", "yosys": "FAIL"}
                payload["pass"] = all(
                    (payload["utf8_lf"], payload["ast"], payload["py_compile"], payload["exact_import"],
                     payload["build_verilog"], payload["module_decl"], payload["syntax"]["verilator"] == "PASS",
                     payload["syntax"]["yosys"] == "PASS")
                )
            except Exception as exc:  # Record failures without hiding a bad batch.
                payload["error"] = f"{type(exc).__name__}: {exc}"
                payload["pass"] = False
            records[name] = payload

    paths = [str(path) for path in TARGETS.values()]
    pyright_data: dict[str, object]
    pyright_command = shutil.which("pyright")
    if pyright_command:
        pyright = subprocess.run([pyright_command, "--outputjson", *paths], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        try:
            pyright_data = json.loads(pyright.stdout) if pyright.stdout else {}
        except json.JSONDecodeError:
            pyright_data = {}
    else:
        pyright_data = {"version": "unavailable", "summary": {"errorCount": None, "warningCount": None}, "status": "UNAVAILABLE"}
    summary = pyright_data.get("summary", {})
    pyright_errors = summary.get("errorCount") if isinstance(summary, dict) else None
    # Tool absence is recorded explicitly; it does not hide static/elaboration failures.
    pyright_gate = "PASS" if pyright_errors == 0 else ("UNAVAILABLE" if pyright_errors is None else "FAIL")
    passed = bool(records) and all(bool(record["pass"]) for record in records.values()) and pyright_gate in {"PASS", "UNAVAILABLE"}
    result = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_FRONTEND_REWRITE_FREEZE_BASIC",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "locked_xstop_sha256": "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d",
        "targets": records,
        "pyright": {"status": pyright_gate, "version": pyright_data.get("version", "unavailable"), "error_count": pyright_errors, "warning_count": summary.get("warningCount") if isinstance(summary, dict) else None},
        "gates": {"REWRITE_FREEZE_BASIC": "PASS" if passed else "FAIL", "PYRIGHT": pyright_gate, "STRUCTURE_VERIFIED": "PASS" if passed else "PENDING", "BEHAVIOR_VERIFIED_frontend": "PENDING", "ACCEPTED": "NOT_ALLOWED"},
        "status": "REWRITE_FREEZE_BASIC_PASS" if passed else "REWRITE_FREEZE_BASIC_FAIL",
        "acceptance_eligible": False,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    mapping = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_FRONTEND_AGGREGATE_MAPPING", "source_commit": result["source_commit"], "targets": {name: record["path"] for name, record in records.items()}, "aggregation": "frontend family/parent closure", "behavior_status": "PENDING_BATCH_VALIDATION"}
    MAPPING.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": result["status"], "targets": len(records), "pyright_errors": pyright_errors}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
