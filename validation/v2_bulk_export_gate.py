"""Cheap source-first rewrite gate; never runs behavioral or formal validation."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "validation/v2-all-source-rewrite-plan.json"
BUILD_ROOT = ROOT / "python/Program-System/System-Build/Build-Cpu"
ZONES = ("Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry")
FORBIDDEN = re.compile(r"\bscala\b|\bXiangShan\b|\bXSTop\b|SOURCE_PATHS|reference-sv|BEGIN LOCKED PORT CATALOG", re.I)
TEST_ZONES = ("Module Contract", "Fixtures And Support", "Subject Contract", "Behavior Tests")


def inspect_direct_test(relative: str) -> dict[str, Any]:
    path = (ROOT / relative).resolve()
    if not path.is_relative_to((ROOT / "python/Program-System/System-Testing").resolve()) or not path.is_file():
        return {"path": relative, "status": "STATIC_TEST_FAILED", "findings": ["DIRECT_TEST_MISSING"]}
    raw = path.read_bytes()
    source = raw.decode("utf-8")
    tree = ast.parse(source, filename=str(path))
    compile(tree, str(path), "exec")
    findings: list[str] = []
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw or "\t" in source:
        findings.append("UTF8_LF_FOUR_SPACE_BASELINE")
    lines = source.splitlines()
    positions = [next((index + 1 for index, line in enumerate(lines) if line == "# " + zone), -1) for zone in TEST_ZONES]
    if min(positions) < 0 or positions != sorted(positions):
        findings.append("FIXED_FOUR_ZONE_ORDER")
    metadata: dict[str, Any] = {}
    metadata_nodes: list[tuple[str, int]] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            key = node.targets[0].id
            if key in ("TEST_ID", "SUBJECT_TYPE", "SUBJECT_ID", "DIRECT"):
                metadata_nodes.append((key, node.lineno))
                metadata[key] = ast.literal_eval(node.value)
    if [key for key, _line in metadata_nodes] != ["TEST_ID", "SUBJECT_TYPE", "SUBJECT_ID", "DIRECT"]:
        findings.append("FIXED_TEST_METADATA_ORDER")
    if any(not positions[1] < line < positions[2] for _key, line in metadata_nodes):
        findings.append("TEST_METADATA_OUTSIDE_FIXTURES")
    kind = metadata.get("SUBJECT_TYPE")
    if kind not in ("build", "runtime") or metadata.get("DIRECT") is not True or not metadata.get("TEST_ID") or not metadata.get("SUBJECT_ID"):
        findings.append("DIRECT_SUBJECT_METADATA")
    contract_name = "RuntimeSubjectContractTest" if kind == "runtime" else "BuildSubjectContractTest"
    contracts = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == contract_name]
    if len(contracts) != 1 or not any(isinstance(node, ast.FunctionDef) and node.name == "test_subject_contract" for node in contracts[0].body):
        findings.append("DIRECT_SUBJECT_CONTRACT_CLASS")
    elif not positions[2] < contracts[0].lineno < positions[3]:
        findings.append("CONTRACT_CLASS_OUTSIDE_SUBJECT_ZONE")
    if not tree.body or not isinstance(tree.body[-1], ast.ClassDef) or not any(
        isinstance(node, ast.FunctionDef) and node.name.startswith("test_") for node in tree.body[-1].body
    ):
        findings.append("FINAL_NODE_NOT_DISCOVERABLE_TEST_CLASS")
    if not path.name.startswith(path.parent.name + "-"):
        findings.append("DIRECT_PARENT_FILENAME_PREFIX")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "unittest" and node.func.attr == "main":
            findings.append("TEST_LOCAL_EXECUTION_ENTRY")
    return {"path": relative, "sha256": hashlib.sha256(raw).hexdigest(),
            "status": "STATIC_TEST_FAILED" if findings else "STATIC_TEST_PASS_BEHAVIOR_NOT_RUN",
            "metadata": metadata, "findings": findings}


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


def export_one(relative: str, work: Path, export_all: bool,
               extra_configurations: list[dict[str, Any]] | None = None) -> dict[str, Any]:
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
    configuration: list[dict[str, Any] | None] = [{"module": name} for name in covered] if export_all and covered else [None]
    configuration.extend(extra_configurations or [])
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
                               "configuration": selected, "rtl_bytes": len(rtl.encode()),
                               "status": "NATIVE_EXPORT_PASS_BEHAVIOR_UNVERIFIED"})
    if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
        raise ValueError("Build changed while the native export gate was running")
    row["status"] = "EXPORT_PASS_CONTRACT_MEMBERS_PENDING" if row["contract_only_members"] else "EXPORT_PASS_BEHAVIOR_UNVERIFIED"
    row["rewrite_coverage_confirmed"] = False
    return row


def main() -> int:
    producer_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="append", required=True)
    parser.add_argument("--export-all-public-members", action="store_true")
    parser.add_argument("--configurations", type=Path,
                        help="Auxiliary JSON mapping Build paths to additional legal configuration dictionaries")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    planned_rows = {row["path"]: row for row in plan["python_files"]}
    planned = set(planned_rows)
    if not set(args.build).issubset(planned):
        raise ValueError("bulk rewrite exports must resolve through the frozen source plan")
    configurations = json.loads(args.configurations.read_text(encoding="utf-8")) if args.configurations else {}
    if not isinstance(configurations, dict) or not set(configurations).issubset(set(args.build)):
        raise ValueError("extra export configurations must reference this explicit Build batch")
    for cases in configurations.values():
        if not isinstance(cases, list) or not all(isinstance(case, dict) and isinstance(case.get("module"), str) for case in cases):
            raise ValueError("every extra native export must select a named public module")
    work = ROOT / "validation/.work/bulk-source-exports"
    work.mkdir(parents=True, exist_ok=True)
    results = []
    for relative in args.build:
        try:
            result = export_one(relative, work, args.export_all_public_members, configurations.get(relative))
            test_path = planned_rows[relative].get("test_path")
            result["direct_test_structure"] = inspect_direct_test(test_path) if test_path else {
                "status": "STATIC_TEST_FAILED", "findings": ["PLAN_DIRECT_TEST_PATH_MISSING"]}
            if result["direct_test_structure"]["status"] == "STATIC_TEST_FAILED":
                result["status"] = "BASIC_GATE_FAILED"
        except Exception as error:
            result = {"path": relative, "status": "BASIC_GATE_FAILED", "error": f"{type(error).__name__}: {error}",
                      "acceptance_eligible": False}
        results.append(result)
        print(json.dumps({"path": relative, "status": result["status"], "exports": len(result.get("exports", []))}), flush=True)
    payload = {"kind": "V2_SOURCE_FIRST_BULK_NATIVE_EXPORT_RECEIPT",
               "source_plan_sha256": hashlib.sha256(PLAN.read_bytes()).hexdigest(),
               "producer_sha256": producer_sha256,
               "results": results, "formal": "NOT_RUN_PHASE_DEFERRED", "differential": "NOT_RUN_PHASE_DEFERRED",
               "strict_complete_count_delta": 0, "acceptance_eligible": False,
               "policy": "Export success is usable syntax/elaboration only; source-feature coverage and behavior acceptance remain separate gates."}
    if producer_sha256 != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError("native export gate changed while running; receipt is not reusable")
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 1 if any(row["status"] == "BASIC_GATE_FAILED" for row in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
