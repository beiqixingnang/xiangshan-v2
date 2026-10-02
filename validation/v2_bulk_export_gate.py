"""Cheap source-first rewrite gate; never runs behavioral or formal validation."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "validation/v2-all-source-rewrite-plan.json"
BUILD_ROOT = ROOT / "python/Program-System/System-Build/Build-Cpu"
ZONES = ("Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry")
FORBIDDEN = re.compile(r"\bscala\b|\bXiangShan\b|\bXSTop\b|SOURCE_PATHS|reference-sv|BEGIN LOCKED PORT CATALOG", re.I)


def read_source(path: Path) -> tuple[str, ast.Module, list[str]]:
    raw = path.read_bytes()
    source = raw.decode("utf-8")
    findings = []
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw or "\t" in source:
        findings.append("UTF8_LF_FOUR_SPACE_BASELINE")
    tree = ast.parse(source, filename=str(path))
    positions = [source.find("# " + zone) for zone in ZONES]
    if min(positions) < 0 or positions != sorted(positions):
        findings.append("FIXED_FIVE_ZONE_ORDER")
    if FORBIDDEN.search(source):
        findings.append("PRODUCT_PROVENANCE_LEAK")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_") and not (node.name.startswith("__") and node.name.endswith("__")):
                findings.append("NON_PROTOCOL_FUNCTION_PREFIX:" + node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for imported in modules:
                root = imported.split(".")[0]
                if root != "amaranth" and root not in sys.stdlib_module_names:
                    findings.append("UNCONTROLLED_IMPORT:" + imported)
                if root in {"importlib", "runpy", "subprocess", "socket", "urllib", "http"}:
                    findings.append("BUILD_LOADER_OR_PROCESS_IMPORT:" + imported)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if re.search(r"\bmodule\s+[A-Za-z_]\w*\s*\(|\balways\s*@|\bassign\s+\w+\s*=", node.value):
                findings.append("EMBEDDED_HDL_IMPLEMENTATION")
    return source, tree, sorted(set(findings))


def load_build(path: Path) -> Any:
    name = "v2_export_gate_" + hashlib.sha256(path.as_posix().encode()).hexdigest()[:16]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def export_one(relative: str, work: Path, export_all: bool) -> dict[str, Any]:
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(BUILD_ROOT.resolve()) or not path.is_file():
        raise ValueError("unknown or out-of-scope candidate Build path")
    source, _tree, findings = read_source(path)
    row: dict[str, Any] = {"path": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                           "static_findings": findings, "exports": [], "behavior_validation": "NOT_RUN_PHASE_DEFERRED",
                           "strict_count_delta": 0, "acceptance_eligible": False}
    if findings:
        row["status"] = "BASIC_GATE_FAILED"
        return row
    module = load_build(path)
    public = getattr(module, "__all__", ())
    if not isinstance(public, (tuple, list)) or len(public) != len(set(public)) or not all(hasattr(module, name) for name in public):
        raise ValueError("invalid public API contract")
    covered = getattr(module, "COVERED_MODULES", getattr(module, "LOCKED_VARIANTS", ()))
    configuration = [{"module": name} for name in covered] if export_all and covered else [None]
    row["contract_only_members"] = list(getattr(module, "CONTRACT_ONLY_MEMBERS", ()))
    for index, selected in enumerate(configuration):
        rtl = module.build_verilog(selected, {})
        match = re.search(r"\bmodule\s+([A-Za-z_]\w*)", rtl) if isinstance(rtl, str) else None
        if not isinstance(rtl, str) or match is None:
            raise ValueError("native export returned no Verilog module")
        name = selected["module"] if selected else match[1]
        if not re.search(r"\bmodule\s+" + re.escape(name) + r"\s*\(", rtl):
            raise ValueError("export module name differs from selected public member")
        target = work / (path.stem + f"-{index}.sv")
        target.write_text(rtl, encoding="utf-8", newline="\n")
        row["exports"].append({"member": name, "rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest(),
                               "rtl_bytes": len(rtl.encode()), "status": "NATIVE_EXPORT_PASS_BEHAVIOR_UNVERIFIED"})
    row["status"] = "EXPORT_PASS_CONTRACT_MEMBERS_PENDING" if row["contract_only_members"] else "EXPORT_PASS_BEHAVIOR_UNVERIFIED"
    row["rewrite_coverage_confirmed"] = False
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="append", required=True)
    parser.add_argument("--export-all-public-members", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    planned = {row["path"] for row in plan["python_files"]}
    if not set(args.build).issubset(planned):
        raise ValueError("bulk rewrite exports must resolve through the frozen source plan")
    work = ROOT / "validation/.work/bulk-source-exports"
    work.mkdir(parents=True, exist_ok=True)
    results = []
    for relative in args.build:
        try:
            result = export_one(relative, work, args.export_all_public_members)
        except Exception as error:
            result = {"path": relative, "status": "BASIC_GATE_FAILED", "error": f"{type(error).__name__}: {error}",
                      "acceptance_eligible": False}
        results.append(result)
        print(json.dumps({"path": relative, "status": result["status"], "exports": len(result.get("exports", []))}), flush=True)
    payload = {"kind": "V2_SOURCE_FIRST_BULK_NATIVE_EXPORT_RECEIPT",
               "source_plan_sha256": hashlib.sha256(PLAN.read_bytes()).hexdigest(),
               "producer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "results": results, "formal": "NOT_RUN_PHASE_DEFERRED", "differential": "NOT_RUN_PHASE_DEFERRED",
               "strict_complete_count_delta": 0, "acceptance_eligible": False,
               "policy": "Export success is usable syntax/elaboration only; source-feature coverage and behavior acceptance remain separate gates."}
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 1 if any(row["status"] == "BASIC_GATE_FAILED" for row in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
