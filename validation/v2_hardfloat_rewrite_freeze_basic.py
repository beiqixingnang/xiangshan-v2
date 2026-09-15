"""Rewrite-freeze basic gates for the V2 Rocket HardFloat aggregate.
昆明湖 V2 Rocket HardFloat 聚合的重写冻结基础门禁。

The gate proves that the final aggregate path is importable, type-checks, and
deterministically emits parseable Verilog.  It does not claim complete
HardFloat arithmetic or Rocket FPU parent equivalence; those remain later
batch-validation closures.
本门禁证明最终聚合路径可导入、可类型检查并确定性导出可解析 Verilog，
不宣称完整 HardFloat 算术或 Rocket FPU 父级等价；这些属于后续批量闭包。
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import io
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from typing import Any, Mapping

# Import Amaranth before the target so its support modules are not mistaken for
# import-time side effects. / 预先导入 Amaranth，避免把支持模块误报为副作用。
from amaranth.back import verilog as _amaranth_verilog


# =============================================================================
# Module Contract
# =============================================================================
ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python" / "Program-System" / "System-Build" / "Build-Cpu" / "Cpu-Core" / "Build-Cpu.Dependency.Rocket.Hardfloat-Hardware.py"
OUT = ROOT / "validation" / "v2-hardfloat-rewrite-freeze-basic-results.json"
MAPPING = ROOT / "validation" / "v2-hardfloat-rewrite-freeze-mapping.json"
CACHE_ROOT = ROOT / "validation" / ".cache"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
BATCH_ID = "V2-DEPENDENCY-HARDFLOAT-001"
FAMILY_ID = "dependency.hardfloat"
TOP_MODULE = "UHSCHardFloatPrimitive"
EXPORT_CONFIGURATION: dict[str, Any] = {
    "module": TOP_MODULE,
    "exp_width": 8,
    "sig_width": 24,
}
SOURCE_PATHS = (
    "rocket-chip/hardfloat/hardfloat/src/main/scala/AddRecFN.scala",
    "rocket-chip/hardfloat/hardfloat/src/main/scala/classifyRecFN.scala",
    "rocket-chip/hardfloat/hardfloat/src/main/scala/common.scala",
    "rocket-chip/hardfloat/hardfloat/src/main/scala/CompareRecFN.scala",
    "rocket-chip/hardfloat/hardfloat/src/main/scala/DivSqrtRecF64.scala",
    "rocket-chip/hardfloat/hardfloat/src/main/scala/DivSqrtRecF64_mulAddZ31.scala",
    "rocket-chip/hardfloat/hardfloat/src/main/scala/DivSqrtRecFN_small.scala",
    "rocket-chip/hardfloat/hardfloat/src/main/scala/fNFromRecFN.scala",
    "rocket-chip/hardfloat/hardfloat/src/main/scala/INToRecFN.scala",
    "rocket-chip/hardfloat/hardfloat/src/main/scala/MulAddRecFN.scala",
    "rocket-chip/hardfloat/hardfloat/src/main/scala/MulRecFN.scala",
    "rocket-chip/hardfloat/hardfloat/src/main/scala/primitives.scala",
    "rocket-chip/hardfloat/hardfloat/src/main/scala/rawFloatFromFN.scala",
    "rocket-chip/hardfloat/hardfloat/src/main/scala/rawFloatFromIN.scala",
    "rocket-chip/hardfloat/hardfloat/src/main/scala/rawFloatFromRecFN.scala",
    "rocket-chip/hardfloat/hardfloat/src/main/scala/recFNFromFN.scala",
    "rocket-chip/hardfloat/hardfloat/src/main/scala/RecFNToIN.scala",
    "rocket-chip/hardfloat/hardfloat/src/main/scala/RecFNToRecFN.scala",
    "rocket-chip/hardfloat/hardfloat/src/main/scala/resizeRawFloat.scala",
    "rocket-chip/hardfloat/hardfloat/src/main/scala/RoundAnyRawFNToRecFN.scala",
)


# =============================================================================
# Configuration
# =============================================================================
# Hash bytes for content-addressed evidence. / 为内容寻址证据计算字节哈希。
def sha256_bytes(data: bytes) -> str:
    """Return a SHA-256 digest for evidence bytes. / 返回证据字节的 SHA-256 摘要。"""

    return hashlib.sha256(data).hexdigest()


# Write normalized UTF-8/LF JSON. / 写入规范化 UTF-8/LF JSON。
def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Persist one evidence object. / 持久化一个证据对象。"""

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


# Snapshot direct directory metadata. / 快照目录直接元数据。
def directory_signature(directory: Path) -> tuple[tuple[str, int, int], ...]:
    """Return a stable immediate-directory signature. / 返回稳定的直接目录签名。"""

    return tuple(sorted((item.name, item.stat().st_size, item.stat().st_mtime_ns) for item in directory.iterdir()))


# Find bilingual responsibility comments on every callable. / 检查每个可调用对象的双语职责注释。
def callable_comment_errors(source: str, tree: ast.AST) -> list[str]:
    """List callables lacking a preceding bilingual comment. / 列出缺少前置双语注释的可调用对象。"""

    lines = source.splitlines()
    errors: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decorated_line = min((decorator.lineno for decorator in node.decorator_list), default=node.lineno)
        index = decorated_line - 2
        comments: list[str] = []
        while index >= 0 and lines[index].lstrip().startswith("#"):
            comments.append(lines[index].strip())
            index -= 1
        if not comments or not any("/" in comment for comment in comments):
            errors.append(f"{node.name}:{node.lineno}")
    return sorted(errors)


# Audit source contract and forbidden target imports. / 审计源码契约和禁止的目标导入。
def static_audit() -> dict[str, Any]:
    """Run encoding, zone, AST, comment, and import checks. / 执行编码、分区、AST、注释和导入检查。"""

    raw = TARGET.read_bytes()
    result: dict[str, Any] = {
        "path": TARGET.relative_to(ROOT).as_posix(),
        "sha256": sha256_bytes(raw),
        "bytes": len(raw),
        "utf8_lf": False,
        "ast": False,
        "five_zone_order": False,
        "bilingual_function_comments": False,
        "function_comment_errors": [],
        "forbidden_imports": [],
    }
    try:
        source = raw.decode("utf-8")
        tree = ast.parse(source, filename=str(TARGET))
    except (UnicodeDecodeError, SyntaxError) as error:
        result["error"] = f"{type(error).__name__}: {error}"
        return result
    result["utf8_lf"] = not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw
    result["ast"] = True
    zones = ("Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry")
    positions = [source.find(f"# {zone}") for zone in zones]
    result["zones"] = dict(zip(zones, positions, strict=True))
    result["five_zone_order"] = all(position >= 0 for position in positions) and positions == sorted(positions)
    result["function_comment_errors"] = callable_comment_errors(source, tree)
    result["bilingual_function_comments"] = not result["function_comment_errors"]
    forbidden_roots = {"importlib", "runpy", "subprocess", "socket", "urllib", "pathlib"}
    forbidden: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            forbidden.extend(alias.name for alias in node.names if alias.name.split(".")[0] in forbidden_roots)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level or module.split(".")[0] in forbidden_roots:
                forbidden.append(module or "relative-import")
    result["forbidden_imports"] = sorted(forbidden)
    result["pass"] = all((
        result["utf8_lf"], result["ast"], result["five_zone_order"],
        result["bilingual_function_comments"], not forbidden,
    ))
    return result


# Compile to an isolated bytecode location. / 编译到隔离字节码目录。
def py_compile_gate() -> dict[str, Any]:
    """Compile the target without creating repository bytecode. / 编译目标且不在仓库生成字节码。"""

    try:
        with TemporaryDirectory(prefix="v2_hardfloat_compile_") as temporary:
            output = Path(temporary) / "target.pyc"
            py_compile.compile(str(TARGET), cfile=str(output), doraise=True)
            return {"status": "PASS", "bytecode_bytes": output.stat().st_size}
    except Exception as error:  # pragma: no cover - diagnostic path
        return {"status": "FAIL", "error": f"{type(error).__name__}: {error}"}


# Import the exact final path while checking side effects. / 导入最终路径并检查副作用。
def exact_path_import() -> tuple[ModuleType | None, dict[str, Any]]:
    """Load the target and verify process state remains unchanged. / 加载目标并验证进程状态不变。"""

    module_name = "v2_hardfloat_rewrite_freeze_target"
    stdout = io.StringIO()
    stderr = io.StringIO()
    before_modules = set(sys.modules)
    before_environment = dict(os.environ)
    before_cwd = Path.cwd()
    before_sys_path = tuple(sys.path)
    before_directory = directory_signature(TARGET.parent)
    previous_module = sys.modules.get(module_name)
    previous_bytecode = sys.dont_write_bytecode
    module: ModuleType | None = None
    error_text: str | None = None
    try:
        spec = importlib.util.spec_from_file_location(module_name, TARGET)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot create import specification for {TARGET}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        sys.dont_write_bytecode = True
        with redirect_stdout(stdout), redirect_stderr(stderr):
            spec.loader.exec_module(module)
    except Exception as error:  # pragma: no cover - diagnostic path
        error_text = f"{type(error).__name__}: {error}"
        module = None
    finally:
        sys.dont_write_bytecode = previous_bytecode
        if previous_module is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous_module
    after_directory = directory_signature(TARGET.parent)
    foreign_modules = sorted(set(sys.modules) - before_modules)
    result: dict[str, Any] = {
        "status": "FAIL",
        "stdout_bytes": len(stdout.getvalue().encode("utf-8")),
        "stderr_bytes": len(stderr.getvalue().encode("utf-8")),
        "cwd_unchanged": Path.cwd() == before_cwd,
        "environment_unchanged": dict(os.environ) == before_environment,
        "sys_path_unchanged": tuple(sys.path) == before_sys_path,
        "target_directory_unchanged": after_directory == before_directory,
        "foreign_modules": foreign_modules,
    }
    if error_text is not None:
        result["error"] = error_text
        return None, result
    result["status"] = "PASS" if all((
        result["stdout_bytes"] == 0, result["stderr_bytes"] == 0,
        result["cwd_unchanged"], result["environment_unchanged"],
        result["sys_path_unchanged"], result["target_directory_unchanged"],
        not foreign_modules,
    )) else "FAIL"
    return module, result


# Export twice under one explicit UHSC module name. / 使用同一 UHSC 模块名导出两次。
def export_gate(module: ModuleType) -> tuple[str | None, dict[str, Any]]:
    """Run deterministic adapter exports and inspect the module name. / 执行确定性适配器导出并检查模块名。"""

    try:
        first = module.build_verilog(dict(EXPORT_CONFIGURATION), {})
        second = module.build_verilog(dict(EXPORT_CONFIGURATION), {})
    except Exception as error:  # pragma: no cover - diagnostic path
        return None, {"status": "FAIL", "error": f"{type(error).__name__}: {error}"}
    match = re.search(r"(?m)^module\s+([A-Za-z_][A-Za-z0-9_$]*)\b", first)
    module_name = match.group(1) if match is not None else None
    result: dict[str, Any] = {
        "status": "PASS" if isinstance(first, str) and bool(first) and first == second and module_name == TOP_MODULE else "FAIL",
        "configuration": EXPORT_CONFIGURATION,
        "same_name": TOP_MODULE,
        "module_name": module_name,
        "deterministic_export": first == second,
        "rtl_bytes": len(first.encode("utf-8")),
        "rtl_sha256": sha256_bytes(first.encode("utf-8")),
    }
    return first, result


# Run a bounded WSL command. / 运行有界 WSL 命令。
def run_wsl(arguments: list[str], timeout: int = 120) -> dict[str, Any]:
    """Execute one tool command and capture normalized output. / 执行工具命令并捕获规范化输出。"""

    try:
        completed = subprocess.run(
            ["wsl.exe", "-e", *arguments], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:  # pragma: no cover - diagnostic path
        return {"status": "UNAVAILABLE", "error": f"{type(error).__name__}: {error}"}
    output = (completed.stdout + completed.stderr).replace("\r\n", "\n")
    return {"status": "PASS" if completed.returncode == 0 else "FAIL", "returncode": completed.returncode, "output": output}


# Normalize tool output for stable hashes. / 规范化工具输出以获得稳定哈希。
def normalized_output(output: str, path: str) -> str:
    """Remove temporary path variability from tool output. / 消除工具输出中的临时路径差异。"""

    normalized = output.replace("\r\n", "\n")
    return normalized.replace(path, "<RTL>").replace(path.replace("/", "\\"), "<RTL>") if path else normalized


# Run cached Verilator and Yosys syntax gates. / 运行缓存的 Verilator 和 Yosys 语法门禁。
def syntax_gate(rtl: str, export: Mapping[str, Any], target_hash: str) -> dict[str, Any]:
    """Check generated Verilog with both synthesis front ends. / 用两个综合前端检查生成 Verilog。"""

    verilator_version = run_wsl(["verilator", "--version"])
    yosys_version = run_wsl(["yosys", "-V"])
    versions = {
        "verilator": str(verilator_version.get("output", "")).strip(),
        "yosys": str(yosys_version.get("output", "")).strip(),
    }
    fingerprint: dict[str, Any] = {
        "target_sha256": target_hash,
        "rtl_sha256": export["rtl_sha256"],
        "module_name": TOP_MODULE,
        "configuration": EXPORT_CONFIGURATION,
        "tool_versions": versions,
        "verilator_command": ["verilator", "--lint-only", "-Wno-fatal", "--top-module", TOP_MODULE],
        "yosys_command": f"read_verilog -sv <RTL>; hierarchy -top {TOP_MODULE}; proc; check",
    }
    cache_key = sha256_bytes(json.dumps(fingerprint, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    cache_dir = CACHE_ROOT / cache_key
    cached_path = cache_dir / "syntax-results.json"
    if cached_path.is_file():
        try:
            cached = json.loads(cached_path.read_text(encoding="utf-8"))
            if cached.get("fingerprint") == fingerprint and cached.get("result", {}).get("status") == "PASS":
                result = dict(cached["result"])
                result.update({"cache": "HIT_REUSED", "cache_key": cache_key})
                return result
        except (OSError, ValueError, TypeError):
            pass
    cache_dir.mkdir(parents=True, exist_ok=True)
    rtl_path = cache_dir / f"{TOP_MODULE}.sv"
    rtl_path.write_text(rtl, encoding="utf-8", newline="\n")
    translated = run_wsl(["wslpath", "-a", str(rtl_path)])
    if translated["status"] != "PASS":
        result = {"status": "FAIL", "cache": "MISS_TOOL_PATH_FAILURE", "cache_key": cache_key, "verilator": {"status": "NOT_RUN"}, "yosys": {"status": "NOT_RUN"}}
        write_json(cached_path, {"fingerprint": fingerprint, "result": result})
        return result
    wsl_rtl = str(translated["output"]).strip()
    verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal", "--top-module", TOP_MODULE, wsl_rtl])
    yosys = run_wsl(["yosys", "-Q", "-p", f"read_verilog -sv {wsl_rtl}; hierarchy -top {TOP_MODULE}; proc; check"])

    # Normalize each tool record before persisting it. / 持久化前规范化每个工具记录。
    def tool_record(raw: Mapping[str, Any]) -> dict[str, Any]:
        output = normalized_output(str(raw.get("output", "")), wsl_rtl)
        return {"status": raw.get("status", "FAIL"), "returncode": raw.get("returncode"), "output_sha256": sha256_bytes(output.encode("utf-8")), "output_tail": output[-800:]}

    result = {
        "status": "PASS" if verilator["status"] == yosys["status"] == "PASS" else "FAIL",
        "cache": "MISS_EXECUTED",
        "cache_key": cache_key,
        "verilator": tool_record(verilator),
        "yosys": tool_record(yosys),
    }
    write_json(cached_path, {"fingerprint": fingerprint, "result": result})
    return result


# Run Pyright over the owned Build target. / 对本批次所属 Build 目标运行 Pyright。
def pyright_gate() -> dict[str, Any]:
    """Require zero Pyright errors and warnings. / 要求 Pyright 错误和警告均为零。"""

    executable = shutil.which("pyright") or shutil.which("pyright.cmd")
    if executable is None:
        return {"status": "UNAVAILABLE", "version": "unavailable", "error_count": None, "warning_count": None}
    completed = subprocess.run([executable, "--outputjson", str(TARGET)], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"status": "FAIL", "version": "unavailable", "error_count": None, "warning_count": None, "output_tail": completed.stdout[-800:]}
    summary = payload.get("summary", {})
    errors = summary.get("errorCount") if isinstance(summary, dict) else None
    warnings = summary.get("warningCount") if isinstance(summary, dict) else None
    return {"status": "PASS" if completed.returncode == 0 and errors == 0 and warnings == 0 else "FAIL", "version": payload.get("version", "unavailable"), "error_count": errors, "warning_count": warnings}


# =============================================================================
# Implementation
# =============================================================================
# Build the family mapping record. / 构建依赖族映射记录。
def mapping_record(result: Mapping[str, Any]) -> dict[str, Any]:
    """Describe covered Scala paths and deferred closure. / 描述覆盖的 Scala 路径和延后闭包。"""

    gates = result["gates"]
    return {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_HARDFLOAT_REWRITE_FREEZE_MAPPING",
        "phase": "REWRITE_FREEZE",
        "batch_id": BATCH_ID,
        "family_id": FAMILY_ID,
        "source_commit": SOURCE_COMMIT,
        "source_root": "upstream/rocket-chip/hardfloat/hardfloat/src/main/scala",
        "source_scala_file_count": len(SOURCE_PATHS),
        "source_paths": list(SOURCE_PATHS),
        "target": result["target"],
        "disposition": "AGGREGATED_FAMILY_BOUNDARY",
        "boundary": {
            "implemented_contracts": [
                "IEEE sign/exponent/fraction packing and zero/subnormal/Inf/NaN classification",
                "combinational equality and sign-aware magnitude comparison observations",
                "bounded primitive operation result mux used by Rocket/Fudian adapters",
            ],
            "source_backed_metadata": [
                "classifyRecFN.scala", "CompareRecFN.scala", "rawFloatFromFN.scala",
                "rawFloatFromRecFN.scala", "recFNFromFN.scala", "RecFNToIN.scala",
            ],
            "explicitly_deferred_closure": [
                "AddRecFN.scala", "DivSqrtRecF64.scala", "DivSqrtRecF64_mulAddZ31.scala",
                "DivSqrtRecFN_small.scala", "MulAddRecFN.scala", "MulRecFN.scala",
                "RoundAnyRawFNToRecFN.scala", "resizeRawFloat.scala", "RecFNToRecFN.scala",
                "INToRecFN.scala", "rawFloatFromIN.scala", "primitives.scala", "common.scala",
            ],
            "deferred_reason": "Iterative div/sqrt, FMA, recFN recoding, rounding, and selected Rocket FPU parent wiring require parent-level reference closure; they are not silently represented by this bounded boundary.",
        },
        "localization": [
            {
                "source_name": "HardFloat aggregate boundary",
                "local_name": TOP_MODULE,
                "visibility": "generated HDL top",
                "reason": "UHSC project-facing family Build export while retaining source names in provenance",
            },
        ],
        "evidence": {
            "rewrite_freeze_basic": OUT.relative_to(ROOT).as_posix(),
            "bounded_family_validation": "validation/v2-hardfloat-family-results.json",
        },
        "gates": gates,
        "structure_status": "PASS" if gates["REWRITE_FREEZE_BASIC"] == "PASS" else "PENDING",
        "behavior_status": "PENDING_BATCH_VALIDATION",
        "unclosed": [
            "Full HardFloat div/sqrt/FMA and recFN-rounding closure remains pending.",
            "Rocket FPU parent and locked XSTop differential remain pending.",
            "BSD attribution/license review and user approval remain pending.",
        ],
        "accepted": False,
        "acceptance_eligible": False,
    }


# =============================================================================
# Public Adapter
# =============================================================================
# Execute all rewrite-freeze gates and persist evidence. / 执行全部重写冻结门禁并保存证据。
def main() -> int:
    """Run the focused HardFloat freeze gate. / 运行聚焦的 HardFloat 冻结门禁。"""

    static = static_audit()
    compile_result = py_compile_gate()
    module, imported = exact_path_import()
    exported: dict[str, Any] = {"status": "NOT_RUN"}
    syntax: dict[str, Any] = {"status": "NOT_RUN", "verilator": {"status": "NOT_RUN"}, "yosys": {"status": "NOT_RUN"}}
    if module is not None and imported["status"] == "PASS":
        rtl, exported = export_gate(module)
        if rtl is not None and exported["status"] == "PASS":
            syntax = syntax_gate(rtl, exported, str(static["sha256"]))
    pyright = pyright_gate()
    passed = all((
        static.get("pass") is True,
        compile_result["status"] == "PASS",
        imported["status"] == "PASS",
        exported["status"] == "PASS",
        pyright["status"] == "PASS",
        syntax["status"] == "PASS",
    ))
    result: dict[str, Any] = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_HARDFLOAT_REWRITE_FREEZE_BASIC",
        "phase": "REWRITE_FREEZE",
        "batch_id": BATCH_ID,
        "family_id": FAMILY_ID,
        "source_commit": SOURCE_COMMIT,
        "target": {"path": TARGET.relative_to(ROOT).as_posix(), "sha256": static["sha256"]},
        "static": static,
        "py_compile": compile_result,
        "exact_path_import": imported,
        "pyright": pyright,
        "build_verilog": exported,
        "verilog_syntax": syntax,
        "gates": {
            "UTF8_LF": "PASS" if static.get("utf8_lf") else "FAIL",
            "FIVE_ZONE_BILINGUAL_AUDIT": "PASS" if static.get("five_zone_order") and static.get("bilingual_function_comments") else "FAIL",
            "AST": "PASS" if static.get("ast") else "FAIL",
            "PY_COMPILE": compile_result["status"],
            "EXACT_PATH_IMPORT_NO_SIDE_EFFECTS": imported["status"],
            "PYRIGHT": pyright["status"],
            "DETERMINISTIC_SAME_NAME_BUILD_VERILOG": exported["status"],
            "VERILATOR": syntax.get("verilator", {}).get("status", "FAIL"),
            "YOSYS": syntax.get("yosys", {}).get("status", "FAIL"),
            "REWRITE_FREEZE_BASIC": "PASS" if passed else "FAIL",
            "STRUCTURE_VERIFIED": "PASS" if passed else "PENDING",
            # The structural gate must not promote the separate behavior rail.
            # / 结构门禁不得推进独立的行为验证轨道。
            "BEHAVIOR_VERIFIED_dependency.hardfloat": "PENDING_BATCH_VALIDATION",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "status": "REWRITE_FREEZE_BASIC_PASS" if passed else "REWRITE_FREEZE_BASIC_FAIL",
        "unclosed": [
            "Full HardFloat div/sqrt/FMA and recFN-rounding closure remains pending.",
            "Rocket FPU parent and locked XSTop differential remain pending.",
            "BSD attribution/license review and user approval remain pending.",
        ],
        "acceptance_eligible": False,
    }
    write_json(OUT, result)
    write_json(MAPPING, mapping_record(result))
    print(json.dumps({"status": result["status"], "pyright": pyright["status"], "verilator": syntax.get("verilator", {}).get("status"), "yosys": syntax.get("yosys", {}).get("status")}, sort_keys=True))
    return 0 if passed else 1


# =============================================================================
# Direct Entry
# Run only when explicitly invoked as a validator. / 仅在显式调用验证器时运行。
if __name__ == "__main__":
    raise SystemExit(main())
