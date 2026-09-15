"""Basic rewrite-freeze gate for the remaining V2 core leaves.
昆明湖 V2 其余核心叶子的重写冻结基础门禁。

The gate is deliberately structural: it proves that the final Build paths can
be parsed, imported, elaborated, and checked by the RTL tools.  Locked-reference
and parent-closure behavior remains a later batch-validation obligation.
本门禁有意保持结构性：证明最终 Build 路径可解析、导入、展开并通过 RTL 工具。
锁定参考差分和父级闭包行为仍属于后续批量验证义务。
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import importlib.util
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


# =============================================================================
# Module Contract
# =============================================================================
ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core"
OUT = ROOT / "validation/v2-core-leaf-rewrite-freeze-basic-results.json"
MAPPING = ROOT / "validation/v2-core-leaf-rewrite-freeze-mapping.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
LOCKED_XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"

# Backend leaf and frontend replacement/IFU paths are owned by this batch.
# Backend parents, BPU/ICache parents, dependencies, and memory aggregates are
# intentionally listed in their own freeze batches.
# 本批次负责 Backend 叶子及前端替换/IFU 路径；Backend 父级、BPU/ICache 父级、
# 依赖和内存聚合由各自冻结批次负责。
TARGET_NAMES = (
    "Build-Cpu.Backend.Datapath.DataSource-Hardware.py",
    "Build-Cpu.Backend.Datapath.NewPipelineConnect-Hardware.py",
    "Build-Cpu.Backend.Datapath.WbArbiter-Hardware.py",
    "Build-Cpu.Backend.Decode.Instructions-Hardware.py",
    "Build-Cpu.Backend.Decode.Isa.Bitfield.RiscvInst-Hardware.py",
    "Build-Cpu.Backend.Decode.Isa.CSRs-Hardware.py",
    "Build-Cpu.Backend.Decode.Isa.Predecode.PreDecodeInst-Hardware.py",
    "Build-Cpu.Backend.Fu.AluDataModule-Hardware.py",
    "Build-Cpu.Backend.Fu.BranchModule-Hardware.py",
    "Build-Cpu.Backend.Fu.Fpu.FliTable-Hardware.py",
    "Build-Cpu.Backend.Fu.JumpDataModule-Hardware.py",
    "Build-Cpu.Backend.Fu.NewCSR.SstcInterruptGen-Hardware.py",
    "Build-Cpu.Backend.Fu.SRT16Divider-Hardware.py",
    "Build-Cpu.Backend.Fu.Util.CryptoUtils-Hardware.py",
    "Build-Cpu.Backend.Fu.Util.CSA-Hardware.py",
    "Build-Cpu.Backend.Fu.Util.DebugCSR-Hardware.py",
    "Build-Cpu.Backend.Fu.Vector.ByteMaskTailGen-Hardware.py",
    "Build-Cpu.Backend.Fu.Vector.DstMgu-Hardware.py",
    "Build-Cpu.Backend.Fu.Vector.Mgtu-Hardware.py",
    "Build-Cpu.Backend.Fu.Vector.NewMgu-Hardware.py",
    "Build-Cpu.Backend.Fu.Vector.Utils.MaskExtrator-Hardware.py",
    "Build-Cpu.Backend.Fu.Vector.Utils.ScalaDupToVector-Hardware.py",
    "Build-Cpu.Backend.Fu.Vector.Utils.UIntToCont0s-Hardware.py",
    "Build-Cpu.Backend.Fu.Vector.Utils.UIntToCont1s-Hardware.py",
    "Build-Cpu.Backend.Fu.Vector.Utils.VecDataSplitModule-Hardware.py",
    "Build-Cpu.Backend.Issue.AgeDetector-Hardware.py",
    "Build-Cpu.Backend.Issue.DataArray-Hardware.py",
    "Build-Cpu.Backend.Issue.DeqPolicy-Hardware.py",
    "Build-Cpu.Backend.Issue.EnqPolicy-Hardware.py",
    "Build-Cpu.Backend.Issue.FuBusyTableRead-Hardware.py",
    "Build-Cpu.Backend.Issue.ImmExtractor-Hardware.py",
    "Build-Cpu.Backend.Rob.CommitStuckCounter-Hardware.py",
    "Build-Cpu.Backend.Rob.PtrWrappers-Hardware.py",
    "Build-Cpu.Frontend.Bpu.Replacer.LruStateGen-Hardware.py",
    "Build-Cpu.Frontend.Bpu.Replacer.PlruStateGen-Hardware.py",
    "Build-Cpu.Frontend.Bpu.Replacer.ReplacerState-Hardware.py",
    "Build-Cpu.Frontend.Ifu.RvcExpander-Hardware.py",
)
TARGETS = {path.removesuffix("-Hardware.py"): BUILD / path for path in TARGET_NAMES}


# Load one Build by exact path without importing sibling Build files.
# 按精确路径加载一个 Build，且不导入兄弟 Build 文件。
def load_target(path: Path, stem: str) -> Any:
    """Load a target module from its final path. / 从最终路径加载目标模块。"""

    spec = importlib.util.spec_from_file_location(f"v2_core_leaf_freeze_{stem}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot create import specification for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Audit the five ordered source zones and bilingual callable documentation.
# 审计五个有序源码分区及双语可调用对象说明。
def style_gate(source: str) -> dict[str, bool]:
    """Check the repository's source-format contract. / 检查仓库源码格式契约。"""

    tree = ast.parse(source)
    zone_names = ("Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry")
    positions = [source.find(f"# {name}") for name in zone_names]
    zone_ok = all(position >= 0 for position in positions) and positions == sorted(positions)
    lines = source.splitlines()
    callables = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    missing: list[str] = []
    for node in callables:
        if ast.get_docstring(node):
            continue
        preceding = "\n".join(lines[max(0, node.lineno - 8): node.lineno - 1])
        if not ("/" in preceding or any("\u4e00" <= char <= "\u9fff" for char in preceding)):
            missing.append(node.name)
    return {"five_zone_order": zone_ok, "function_responsibility_comments": not missing, "missing_callables": missing}


# Build a deterministic configuration from the first dataclass when a target
# does not accept ``None``.  Defaults remain authoritative; only dimensions
# are bounded to keep the freeze smoke resource-bounded.
# 当目标不接受 ``None`` 时从首个 dataclass 构造确定性配置；默认值仍是权威，
# 仅对几何尺寸做有界处理以控制冻结冒烟资源。
def default_configuration(module: Any) -> Any:
    """Return a target's default configuration or ``None``. / 返回目标默认配置。"""

    candidates = [value for value in vars(module).values() if isinstance(value, type) and dataclasses.is_dataclass(value)]
    if not candidates:
        return None
    config_type = candidates[0]
    values: dict[str, Any] = {}
    for field in dataclasses.fields(config_type):
        if field.default is dataclasses.MISSING:
            continue
        value = field.default
        if isinstance(value, int) and not isinstance(value, bool):
            name = field.name.lower()
            if any(token in name for token in ("entry", "way", "set", "queue", "bank", "port", "client")):
                value = max(1, min(value, 2))
        values[field.name] = value
    try:
        return config_type(**values)
    except (TypeError, ValueError):
        return config_type()


# Export and syntax-check one target in a shared temporary directory.
# 在共享临时目录中导出并检查一个目标。
def export_gate(module: Any, stem: str, work: Path) -> dict[str, Any]:
    """Run deterministic export plus Verilator/Yosys checks. / 运行确定性导出及工具检查。"""

    configuration = None
    try:
        first = module.build_verilog(None, {})
        second = module.build_verilog(None, {})
    except (TypeError, ValueError):
        configuration = default_configuration(module)
        first = module.build_verilog(configuration, {})
        second = module.build_verilog(configuration, {})
    if not isinstance(first, str) or not first:
        raise TypeError("build_verilog must return a non-empty string")
    if first != second:
        raise ValueError("build_verilog output is not deterministic")
    match = re.search(r"(?m)^module\s+([A-Za-z_][A-Za-z0-9_$]*)\b", first)
    if match is None:
        raise ValueError("generated Verilog has no module declaration")
    top = match.group(1)
    rtl = work / f"{stem}.sv"
    rtl.write_text(first, encoding="utf-8", newline="\n")
    wslpath = subprocess.run(
        ["wsl.exe", "-e", "wslpath", "-a", str(rtl)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    if wslpath.returncode != 0:
        raise RuntimeError(f"wslpath failed: {wslpath.stderr[-300:]}")
    linux_path = wslpath.stdout.strip().replace("'", "'\\''")
    verilator = subprocess.run(
        ["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal '{linux_path}'"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    yosys = subprocess.run(
        ["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p 'read_verilog -sv {linux_path}; hierarchy -top {top}; proc; check'"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    return {
        "configuration": repr(configuration),
        "module": top,
        "generated_bytes": len(first.encode("utf-8")),
        "generated_sha256": hashlib.sha256(first.encode("utf-8")).hexdigest(),
        "deterministic_export": True,
        "module_decl": True,
        "verilator": "PASS" if verilator.returncode == 0 else "FAIL",
        "yosys": "PASS" if yosys.returncode == 0 else "FAIL",
        "verilator_returncode": verilator.returncode,
        "yosys_returncode": yosys.returncode,
        "tool_output_tail": (verilator.stderr + verilator.stdout + yosys.stderr + yosys.stdout)[-1200:],
    }


# Run every static and elaboration gate and write machine-readable evidence.
# 运行全部静态与展开门禁并写入机器可读证据。
def main() -> int:
    """Validate this core-leaf batch. / 验证本核心叶子批次。"""

    records: dict[str, dict[str, Any]] = {}
    with TemporaryDirectory(prefix="v2_core_leaf_freeze_") as temporary:
        work = Path(temporary)
        for stem, path in TARGETS.items():
            record: dict[str, Any] = {
                "path": path.relative_to(ROOT).as_posix(),
                "exists": path.is_file(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
                "utf8_lf": False,
                "ast": False,
                "py_compile": False,
                "format": {},
                "exact_import": False,
                "build_verilog": False,
                "pass": False,
            }
            try:
                raw = path.read_bytes()
                text = raw.decode("utf-8")
                record["utf8_lf"] = not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw
                ast.parse(text)
                record["ast"] = True
                py_compile.compile(str(path), doraise=True)
                record["py_compile"] = True
                record["format"] = style_gate(text)
                module = load_target(path, stem)
                record["exact_import"] = True
                exported = export_gate(module, stem, work)
                record.update(exported)
                record["build_verilog"] = True
                record["pass"] = all((
                    record["utf8_lf"], record["ast"], record["py_compile"],
                    record["format"].get("five_zone_order", False),
                    record["format"].get("function_responsibility_comments", False),
                    record["exact_import"], record["build_verilog"],
                    record.get("deterministic_export", False), record.get("module_decl", False),
                    record.get("verilator") == "PASS", record.get("yosys") == "PASS",
                ))
            except Exception as exc:  # Record each failure without hiding the batch result.
                record["error"] = f"{type(exc).__name__}: {exc}"
            records[stem] = record

    pyright_executable = shutil.which("pyright.cmd") or shutil.which("pyright")
    relative_paths = [str(path.relative_to(ROOT)).replace("\\", "/") for path in TARGETS.values()]
    if pyright_executable:
        pyright = subprocess.run(
            [pyright_executable, "--outputjson", *relative_paths],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )
        try:
            pyright_data: dict[str, Any] = json.loads(pyright.stdout)
        except json.JSONDecodeError:
            pyright_data = {"version": "unparseable", "summary": {"errorCount": None, "warningCount": None}, "raw_tail": pyright.stdout[-1000:]}
    else:
        pyright_data = {"version": "unavailable", "summary": {"errorCount": None, "warningCount": None}}
    summary = pyright_data.get("summary", {})
    pyright_errors = summary.get("errorCount") if isinstance(summary, dict) else None
    structural_pass = bool(records) and all(bool(record["pass"]) for record in records.values())
    passed = structural_pass and pyright_errors == 0
    result: dict[str, Any] = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_CORE_LEAF_REWRITE_FREEZE_BASIC",
        "batch_id": "V2-SCAN-A-CORE-LEAVES-REMAINING",
        "source_commit": SOURCE_COMMIT,
        "locked_xstop_sha256": LOCKED_XSTOP_SHA256,
        "scope": {"backend_leaf_and_frontend_replacement": True, "excluded_parent_vld_merge_unit": True, "excluded_memory_dcache": True},
        "targets": records,
        "pyright": {"version": pyright_data.get("version"), "error_count": pyright_errors, "warning_count": summary.get("warningCount") if isinstance(summary, dict) else None},
        "gates": {
            "REWRITE_FREEZE_BASIC": "PASS" if passed else "FAIL",
            "PYRIGHT": "PASS" if pyright_errors == 0 else "FAIL",
            "STRUCTURE_VERIFIED": "PASS" if passed else "PENDING",
            "BEHAVIOR_VERIFIED_core_leaf": "PENDING_BATCH_VALIDATION",
            "PARENT_CLOSURE_MATCHED": "PENDING",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "status": "REWRITE_FREEZE_BASIC_PASS" if passed else "REWRITE_FREEZE_BASIC_FAIL",
        "acceptance_eligible": False,
        "notes": [
            "VldMergeUnit is a previously validated parent closure and remains excluded from this leaf batch.",
            "A clean basic gate does not establish locked-reference behavioral equivalence or full parent closure.",
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    mapping = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_CORE_LEAF_REWRITE_FREEZE_MAPPING",
        "source_commit": SOURCE_COMMIT,
        "targets": {stem: record["path"] for stem, record in records.items()},
        "excluded": {"VldMergeUnit": "parent closure owned by parent-validation batch", "Dcache": "memory freeze batch"},
        "behavior_status": "PENDING_BATCH_VALIDATION",
    }
    MAPPING.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": result["status"], "targets": len(records), "passed": sum(bool(record["pass"]) for record in records.values()), "pyright_errors": pyright_errors}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
