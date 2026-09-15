"""Rewrite-freeze basic gates for the V2 Rocket diplomacy aggregate.
昆明湖 V2 Rocket diplomacy 聚合 Build 的重写冻结基础门禁。

This script validates the final Build-Cpu path as a deterministic structural
subject.  It does not claim full Rocket Diplomacy or XSTop behavioural closure;
those remain Batch Validation and parent-closure work.
本脚本验证最终 Build-Cpu 路径的确定性结构可用性，不宣称完整 Rocket
Diplomacy 或 XSTop 行为闭包；后者仍属于批量验证和父级闭包工作。
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

from amaranth.back import verilog as _amaranth_verilog


# =============================================================================
# Module Contract
# =============================================================================
ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python" / "Program-System" / "System-Build" / "Build-Cpu" / "Cpu-Core" / "Build-Cpu.Dependency.Rocket.Diplomacy-Hardware.py"
OUT = ROOT / "validation" / "v2-rocket-diplomacy-rewrite-freeze-basic-results.json"
MAPPING = ROOT / "validation" / "v2-rocket-diplomacy-rewrite-freeze-mapping.json"
CACHE_ROOT = ROOT / "validation" / ".cache"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
LOCKED_XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
BATCH_ID = "V2-DEPENDENCY-ROCKET-DIPLOMACY-001"
FAMILY_ID = "dependency.rocket.diplomacy"
TOP_MODULE = "UHSCRocketDiplomacy"
EXPORT_CONFIGURATION: dict[str, Any] = {
    "module": TOP_MODULE,
    "address_bits": 16,
    "route_bases": [0x0000, 0x4000, 0x8000, 0xC000],
    "route_masks": [0x3FFF, 0x3FFF, 0x3FFF, 0x3FFF],
}
SOURCE_PATHS = (
    "rocket-chip/src/main/scala/diplomacy/AddressDecoder.scala",
    "rocket-chip/src/main/scala/diplomacy/AddressRange.scala",
    "rocket-chip/src/main/scala/diplomacy/BundleBridge.scala",
    "rocket-chip/src/main/scala/diplomacy/ClockDomain.scala",
    "rocket-chip/src/main/scala/diplomacy/Clone.scala",
    "rocket-chip/src/main/scala/diplomacy/CloneModule.scala",
    "rocket-chip/src/main/scala/diplomacy/DeviceTree.scala",
    "rocket-chip/src/main/scala/diplomacy/FixedClockResource.scala",
    "rocket-chip/src/main/scala/diplomacy/JSON.scala",
    "rocket-chip/src/main/scala/diplomacy/LazyModule.scala",
    "rocket-chip/src/main/scala/diplomacy/Main.scala",
    "rocket-chip/src/main/scala/diplomacy/Nodes.scala",
    "rocket-chip/src/main/scala/diplomacy/package.scala",
    "rocket-chip/src/main/scala/diplomacy/Parameters.scala",
    "rocket-chip/src/main/scala/diplomacy/Resources.scala",
    "rocket-chip/src/main/scala/diplomacy/SRAM.scala",
    "rocket-chip/src/main/scala/diplomacy/Unreachable.scala",
    "rocket-chip/src/main/scala/diplomacy/ValName.scala",
)


# =============================================================================
# Configuration
# =============================================================================
# Hash bytes exactly for content-addressed evidence. / 为内容寻址证据精确计算字节哈希。
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# Write normalized UTF-8/LF JSON evidence. / 写入规范化 UTF-8/LF JSON 证据。
def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


# Snapshot immediate target-directory metadata without following child trees. /
# 快照目标目录的直接元数据，不递归遍历子树。
def directory_signature(directory: Path) -> tuple[tuple[str, int, int], ...]:
    return tuple(sorted(
        (item.name, item.stat().st_size, item.stat().st_mtime_ns)
        for item in directory.iterdir()
    ))


# Locate the bilingual responsibility comment attached to a callable. /
# 定位附着在可调用对象上的双语职责注释。
def callable_comment_errors(source: str, tree: ast.AST) -> list[str]:
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


# Audit encoding, five ordered zones, AST, and forbidden target coupling. /
# 审计编码、五个有序分区、AST 以及禁止的目标耦合。
def static_audit() -> dict[str, Any]:
    raw = TARGET.read_bytes()
    payload: dict[str, Any] = {
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
    except UnicodeDecodeError as error:
        payload["decode_error"] = f"{type(error).__name__}: {error}"
        return payload
    payload["utf8_lf"] = not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw
    try:
        tree = ast.parse(source, filename=str(TARGET))
    except SyntaxError as error:
        payload["ast_error"] = f"{type(error).__name__}: {error}"
        return payload
    payload["ast"] = True
    zones = ("Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry")
    positions = [source.find(f"# {zone}") for zone in zones]
    payload["zones"] = dict(zip(zones, positions, strict=True))
    payload["five_zone_order"] = all(position >= 0 for position in positions) and positions == sorted(positions)
    comment_errors = callable_comment_errors(source, tree)
    payload["function_comment_errors"] = comment_errors
    payload["bilingual_function_comments"] = not comment_errors
    forbidden_roots = {"importlib", "runpy", "subprocess", "socket", "urllib", "pathlib"}
    forbidden: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            forbidden.extend(alias.name for alias in node.names if alias.name.split(".")[0] in forbidden_roots)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level or module.split(".")[0] in forbidden_roots:
                forbidden.append(module or "relative-import")
    payload["forbidden_imports"] = sorted(forbidden)
    payload["pass"] = all((
        payload["utf8_lf"], payload["ast"], payload["five_zone_order"],
        payload["bilingual_function_comments"], not forbidden,
    ))
    return payload


# Compile the target to an isolated temporary bytecode location. / 将目标编译到隔离的
# 临时字节码位置。
def py_compile_gate() -> dict[str, Any]:
    try:
        with TemporaryDirectory(prefix="v2_rocket_diplomacy_compile_") as temporary:
            cfile = Path(temporary) / "Build-Cpu.Dependency.Rocket.Diplomacy-Hardware.pyc"
            py_compile.compile(str(TARGET), cfile=str(cfile), doraise=True)
            return {"status": "PASS", "bytecode_bytes": cfile.stat().st_size}
    except Exception as error:
        return {"status": "FAIL", "error": f"{type(error).__name__}: {error}"}


# Import the exact final path while detecting observable import-time mutation. /
# 导入最终精确路径，同时检测可观察到的导入期变更。
def exact_path_import() -> tuple[ModuleType | None, dict[str, Any]]:
    module_name = "v2_rocket_diplomacy_rewrite_freeze_target"
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
            raise RuntimeError(f"cannot create exact-path import specification for {TARGET}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        sys.dont_write_bytecode = True
        with redirect_stdout(stdout), redirect_stderr(stderr):
            spec.loader.exec_module(module)
    except Exception as error:
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
    record: dict[str, Any] = {
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
        record["error"] = error_text
        return None, record
    record["status"] = "PASS" if all((
        record["stdout_bytes"] == 0,
        record["stderr_bytes"] == 0,
        record["cwd_unchanged"],
        record["environment_unchanged"],
        record["sys_path_unchanged"],
        record["target_directory_unchanged"],
        not foreign_modules,
    )) else "FAIL"
    return module, record


# Export twice under one explicit UHSC module name. / 使用一个显式 UHSC 模块名导出两次。
def export_gate(module: ModuleType) -> tuple[str | None, dict[str, Any]]:
    try:
        first = module.build_verilog(dict(EXPORT_CONFIGURATION), {})
        second = module.build_verilog(dict(EXPORT_CONFIGURATION), {})
    except Exception as error:
        return None, {"status": "FAIL", "error": f"{type(error).__name__}: {error}"}
    match = re.search(r"(?m)^module\s+([A-Za-z_][A-Za-z0-9_$]*)\b", first)
    module_name = match.group(1) if match is not None else None
    record: dict[str, Any] = {
        "status": "PASS" if isinstance(first, str) and bool(first) and first == second and module_name == TOP_MODULE else "FAIL",
        "configuration": EXPORT_CONFIGURATION,
        "same_name": TOP_MODULE,
        "module_name": module_name,
        "deterministic_export": first == second,
        "rtl_bytes": len(first.encode("utf-8")),
        "rtl_sha256": sha256_bytes(first.encode("utf-8")),
    }
    return first, record


# Run one bounded WSL command and retain stable diagnostic evidence. /
# 运行一条有界 WSL 命令并保留稳定诊断证据。
def run_wsl(arguments: list[str], timeout: int = 120) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["wsl.exe", "-e", *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"status": "UNAVAILABLE", "error": f"{type(error).__name__}: {error}"}
    output = (completed.stdout + completed.stderr).replace("\r\n", "\n")
    return {
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "returncode": completed.returncode,
        "output": output,
    }


# Normalize tool output before it is persisted or hashed. / 在持久化或哈希前规范化工具输出。
def normalized_tool_output(output: str, rtl_path: str) -> str:
    normalized = output.replace("\r\n", "\n")
    if not rtl_path:
        return normalized
    return normalized.replace(rtl_path, "<RTL>").replace(rtl_path.replace("/", "\\"), "<RTL>")


# Run or reuse content-addressed Verilator/Yosys syntax checks. / 运行或复用内容寻址的
# Verilator/Yosys 语法检查。
def syntax_gate(rtl: str, export: Mapping[str, Any], target_hash: str) -> dict[str, Any]:
    version_verilator = run_wsl(["verilator", "--version"])
    version_yosys = run_wsl(["yosys", "-V"])
    versions = {
        "verilator": normalized_tool_output(str(version_verilator.get("output", "")), "").strip(),
        "yosys": normalized_tool_output(str(version_yosys.get("output", "")), "").strip(),
    }
    fingerprint = {
        "target_sha256": target_hash,
        "rtl_sha256": export["rtl_sha256"],
        "locked_xstop_sha256": LOCKED_XSTOP_SHA256,
        "module_name": TOP_MODULE,
        "configuration": EXPORT_CONFIGURATION,
        "tool_versions": versions,
        "verilator_command": ["verilator", "--lint-only", "-Wno-fatal", "--top-module", TOP_MODULE],
        "yosys_command": "read_verilog -sv <RTL>; hierarchy -top UHSCRocketDiplomacy; proc; check",
    }
    cache_key = sha256_bytes(json.dumps(fingerprint, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    cache_dir = CACHE_ROOT / cache_key
    record_path = cache_dir / "syntax-results.json"
    if record_path.is_file():
        try:
            cached = json.loads(record_path.read_text(encoding="utf-8"))
            if (
                cached.get("fingerprint") == fingerprint
                and isinstance(cached.get("result"), dict)
                and cached["result"].get("status") == "PASS"
            ):
                result = dict(cached["result"])
                result["cache"] = "HIT_REUSED"
                result["cache_key"] = cache_key
                return result
        except (OSError, ValueError, TypeError):
            pass
    cache_dir.mkdir(parents=True, exist_ok=True)
    rtl_path = cache_dir / f"{TOP_MODULE}.sv"
    rtl_path.write_text(rtl, encoding="utf-8", newline="\n")
    translated = run_wsl(["wslpath", "-a", str(rtl_path)])
    if translated["status"] != "PASS":
        result = {
            "status": "FAIL",
            "cache": "MISS_TOOL_PATH_FAILURE",
            "cache_key": cache_key,
            "verilator": {"status": "NOT_RUN"},
            "yosys": {"status": "NOT_RUN"},
            "wslpath": {key: value for key, value in translated.items() if key != "output"},
        }
        write_json(record_path, {"fingerprint": fingerprint, "result": result})
        return result
    wsl_rtl = str(translated["output"]).strip()
    verilator = run_wsl([
        "verilator", "--lint-only", "-Wno-fatal", "--top-module", TOP_MODULE, wsl_rtl,
    ])
    yosys_script = f"read_verilog -sv {wsl_rtl}; hierarchy -top {TOP_MODULE}; proc; check"
    yosys = run_wsl(["yosys", "-Q", "-p", yosys_script])
    # Normalize one backend result record. / 规范化单个后端结果记录。
    def tool_record(raw: Mapping[str, Any]) -> dict[str, Any]:
        output = normalized_tool_output(str(raw.get("output", "")), wsl_rtl)
        return {
            "status": raw.get("status", "FAIL"),
            "returncode": raw.get("returncode"),
            "output_sha256": sha256_bytes(output.encode("utf-8")),
            "output_tail": output[-800:],
        }
    result = {
        "status": "PASS" if verilator["status"] == yosys["status"] == "PASS" else "FAIL",
        "cache": "MISS_EXECUTED",
        "cache_key": cache_key,
        "verilator": tool_record(verilator),
        "yosys": tool_record(yosys),
    }
    write_json(record_path, {"fingerprint": fingerprint, "result": result})
    return result


# Run Pyright over the target and its dedicated gate runner. / 对目标和其专用门禁
# 运行 Pyright。
def pyright_gate() -> dict[str, Any]:
    executable = shutil.which("pyright") or shutil.which("pyright.cmd")
    if executable is None:
        return {"status": "UNAVAILABLE", "version": "unavailable", "error_count": None, "warning_count": None}
    completed = subprocess.run(
        [executable, "--outputjson", str(TARGET), str(Path(__file__).resolve())],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"status": "FAIL", "version": "unavailable", "error_count": None, "warning_count": None, "output_tail": completed.stdout[-800:]}
    summary = payload.get("summary", {})
    errors = summary.get("errorCount") if isinstance(summary, dict) else None
    warnings = summary.get("warningCount") if isinstance(summary, dict) else None
    return {
        "status": "PASS" if completed.returncode == 0 and errors == 0 else "FAIL",
        "version": payload.get("version", "unavailable"),
        "error_count": errors,
        "warning_count": warnings,
    }


# =============================================================================
# Implementation
# Assemble the immutable mapping record for this aggregate boundary. /
# 组装该聚合边界的不可变映射记录。
def mapping_record(result: Mapping[str, Any]) -> dict[str, Any]:
    gates = result["gates"]
    return {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_ROCKET_DIPLOMACY_REWRITE_FREEZE_MAPPING",
        "phase": "REWRITE_FREEZE",
        "batch_id": BATCH_ID,
        "family_id": FAMILY_ID,
        "source_commit": SOURCE_COMMIT,
        "locked_xstop_sha256": LOCKED_XSTOP_SHA256,
        "source_root": "upstream/rocket-chip/src/main/scala/diplomacy",
        "source_scala_file_count": len(SOURCE_PATHS),
        "source_paths": list(SOURCE_PATHS),
        "target": result["target"],
        "disposition": "AGGREGATED_FAMILY_BOUNDARY",
        "boundary": {
            "implemented_contracts": [
                "AddressRange/AddressSet arithmetic and AddressDecoder-compatible route selection",
                "IdRange, TransferSizes, resource bindings, and clock-crossing metadata",
                "deterministic LazyModule-style graph topology resolution",
                "UHSC-localized combinational address-route RTL boundary",
            ],
            "source_backed_metadata": [
                "AddressDecoder.scala", "AddressRange.scala", "ClockDomain.scala",
                "LazyModule.scala", "Nodes.scala", "package.scala", "Parameters.scala", "Resources.scala",
            ],
            "explicitly_deferred_chisel_elaboration": [
                "BundleBridge.scala", "Clone.scala", "CloneModule.scala", "DeviceTree.scala", "JSON.scala",
                "FixedClockResource.scala", "Main.scala", "SRAM.scala", "Unreachable.scala", "ValName.scala",
            ],
            "deferred_reason": "These files require Chisel elaboration, generated device-tree emission, or selected-parent wiring; they are not silently substituted by the Build boundary.",
        },
        "localization": [
            {
                "source_name": "AddressDecoder.apply",
                "local_name": "UHSCRocketDiplomacy",
                "visibility": "generated HDL top",
                "reason": "UHSC project-facing deterministic route-boundary export",
            },
        ],
        "evidence": {
            "rewrite_freeze_basic": OUT.relative_to(ROOT).as_posix(),
            "bounded_family_validation": "validation/v2-rocket-diplomacy-family-results.json",
        },
        "gates": gates,
        "structure_status": "PASS" if gates["REWRITE_FREEZE_BASIC"] == "PASS" else "PENDING",
        "behavior_status": "PENDING_BATCH_VALIDATION",
        "unclosed": [
            "Complete Rocket Diplomacy Chisel/LazyModule elaboration remains outside this aggregate boundary.",
            "Locked XSTop parent-level diplomacy differential remains pending.",
            "License review, complete parent closure, UHSC integration, and user approval remain pending.",
        ],
        "accepted": False,
        "acceptance_eligible": False,
    }


# =============================================================================
# Public Adapter
# Execute every rewrite-freeze basic gate and persist machine-readable evidence. /
# 执行每个重写冻结基础门禁并持久化机器可读证据。
def main() -> int:
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
        "kind": "XIANGSHAN_KUNMINGHU_V2_ROCKET_DIPLOMACY_REWRITE_FREEZE_BASIC",
        "phase": "REWRITE_FREEZE",
        "batch_id": BATCH_ID,
        "family_id": FAMILY_ID,
        "source_commit": SOURCE_COMMIT,
        "locked_xstop_sha256": LOCKED_XSTOP_SHA256,
        "target": {
            "path": TARGET.relative_to(ROOT).as_posix(),
            "sha256": static["sha256"],
        },
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
            "VERILATOR": syntax["verilator"]["status"],
            "YOSYS": syntax["yosys"]["status"],
            "REWRITE_FREEZE_BASIC": "PASS" if passed else "FAIL",
            "STRUCTURE_VERIFIED": "PASS" if passed else "PENDING",
            "BEHAVIOR_VERIFIED_dependency.rocket.diplomacy": "PENDING_BATCH_VALIDATION",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "status": "REWRITE_FREEZE_BASIC_PASS" if passed else "REWRITE_FREEZE_BASIC_FAIL",
        "unclosed": [
            "Full Rocket Diplomacy behavioral closure is not established by this structural freeze gate.",
            "Locked XSTop differential and parent integration remain pending.",
            "License review and user approval remain pending.",
        ],
        "acceptance_eligible": False,
    }
    write_json(OUT, result)
    write_json(MAPPING, mapping_record(result))
    print(json.dumps({
        "status": result["status"],
        "pyright": pyright["status"],
        "verilator": syntax["verilator"]["status"],
        "yosys": syntax["yosys"]["status"],
    }, sort_keys=True))
    return 0 if passed else 1


# =============================================================================
# Direct Entry
# Run the focused gate only when invoked as a validation command. /
# 仅在作为验证命令调用时运行聚焦门禁。
if __name__ == "__main__":
    raise SystemExit(main())
