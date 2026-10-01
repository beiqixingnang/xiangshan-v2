"""Inventory every locked V2 module without promoting source mappings to behavior."""

from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
NAMING = ROOT / "UHSC-Naming-Manifest.json"
PROGRESS = ROOT / "validation/v2-strict-equivalence-progress.json"
EXPECTED_HASH = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
ZONES = ("Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> tuple[dict[str, Any], str]:
    data = path.read_bytes()
    return json.loads(data), digest(data)


def strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [item for item in value if isinstance(item, str)]
    return []


def source_key(value: str) -> str:
    value = value.replace("\\", "/").split(":", 1)[0]
    return value.split("src/main/scala/", 1)[-1]


def constant(node: ast.AST, values: dict[str, Any]) -> Any:
    """Resolve literal declarations and aliases without importing a Build."""
    if isinstance(node, ast.Name):
        return values[node.id]
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return [constant(item, values) for item in node.elts]
    if isinstance(node, ast.Dict):
        return {constant(k, values): constant(v, values)
                for k, v in zip(node.keys, node.values) if k is not None}
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return constant(node.left, values) + constant(node.right, values)
    return ast.literal_eval(node)


def module_declarations(tree: ast.Module, locked: set[str]) -> dict[str, list[str]]:
    values: dict[str, Any] = {}
    for statement in tree.body:
        if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
            continue
        names = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
        for name in names:
            if not isinstance(name, ast.Name) or statement.value is None:
                continue
            try:
                values[name.id] = constant(statement.value, values)
            except (ValueError, TypeError, KeyError):
                pass
    catalog: set[str] = set()
    for name, value in values.items():
        if name in ("COVERED_MODULES", "LOCKED_VARIANTS", "CSR_FAMILY_MODULES",
                    "HANDLER_MODULE_NAMES") or name.endswith("_MEMBERS"):
            catalog.update(strings(value))
        if name.endswith("_SPECS") and isinstance(value, dict):
            catalog.update(key for key in value if isinstance(key, str))
    implemented = set(strings(values.get("IMPLEMENTED_MEMBERS", [])))
    contracts = set(strings(values.get("CONTRACT_ONLY_MEMBERS", [])))
    # Common tuple comprehension: all covered members except the explicit
    # implemented set.  It is evaluated structurally, never through eval().
    if "CONTRACT_ONLY_MEMBERS" not in values:
        for statement in tree.body:
            names = (statement.targets if isinstance(statement, ast.Assign)
                     else [statement.target] if isinstance(statement, ast.AnnAssign) else [])
            if any(isinstance(name, ast.Name) and name.id == "CONTRACT_ONLY_MEMBERS"
                   for name in names):
                if isinstance(statement.value, ast.Call) and isinstance(statement.value.func, ast.Name) \
                        and statement.value.func.id == "tuple" and statement.value.args \
                        and isinstance(statement.value.args[0], ast.GeneratorExp):
                    expression = statement.value.args[0]
                    if len(expression.generators) == 1 and expression.generators[0].ifs:
                        condition = expression.generators[0].ifs[0]
                        if isinstance(condition, ast.Compare) and len(condition.ops) == 1 \
                                and isinstance(condition.ops[0], ast.NotIn) \
                                and isinstance(condition.comparators[0], ast.Name) \
                                and condition.comparators[0].id == "IMPLEMENTED_MEMBERS":
                            contracts = catalog - implemented
    return {"catalog": sorted(catalog & locked),
            "declared_implemented": sorted(implemented & locked),
            "contract_only": sorted(contracts & locked)}


def proof_modules(row: dict[str, Any], locked: set[str]) -> set[str]:
    scope = row.get("scope", {})
    names = set(strings(scope.get("public_variants", [])))
    names.update(scope.get("variants", {}))
    for item in row.get("sources", {}).values():
        if isinstance(item, dict) and str(item.get("path", "")).startswith("validation/reference-sv/"):
            names.add(Path(item["path"]).stem)
    return names & locked


def current_sources(row: dict[str, Any], hashes: dict[str, str]) -> bool:
    """A saved PASS is stale when a current Build/source digest has changed."""
    records: list[dict[str, Any]] = []
    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if "path" in value and "expected_sha256" in value:
                records.append(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    for label in ("sources", "source_children", "validator_dependencies"):
        visit(row.get(label, {}))
    if not records:
        return False
    for record in records:
        relative = record["path"]
        # Historical producer snapshots have separate origin audits; retain
        # their recorded receipt identity instead of demanding the current
        # producer be byte-identical to its historical version.
        if record.get("producer_snapshot"):
            continue
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
            return False
        observed = hashes.setdefault(relative, digest(path.read_bytes()))
        if observed != record["expected_sha256"]:
            return False
    return True


def inventory() -> dict[str, Any]:
    hierarchy, hierarchy_hash = read_json(HIERARCHY)
    naming, naming_hash = read_json(NAMING)
    progress, progress_hash = read_json(PROGRESS)
    modules = hierarchy["modules"]
    if len(modules) != 1976 or hierarchy["reference_sha256"] != EXPECTED_HASH:
        raise ValueError("locked hierarchy changed")
    locked = set(modules)
    missing_edges = [(name, child["module"]) for name, module in modules.items()
                     for child in module["children"] if child["module"] not in modules]
    if missing_edges:
        raise ValueError("unresolved reference child modules: " + repr(missing_edges))
    reachable: set[str] = set()
    def walk(name: str) -> None:
        if name in reachable:
            return
        reachable.add(name)
        for child in modules[name]["children"]:
            walk(child["module"])
    walk("XSTop")
    transaction = naming["path_rename_transaction"]["renames"]
    tests = {row["new_path"] for row in transaction if row["kind"] == "testing-script"}
    builds = [row for row in transaction if row["kind"] == "build-script"]
    declared: dict[str, list[dict[str, str]]] = defaultdict(list)
    source_candidates: dict[str, set[str]] = defaultdict(set)
    input_hashes = {HIERARCHY.relative_to(ROOT).as_posix(): hierarchy_hash,
                    NAMING.relative_to(ROOT).as_posix(): naming_hash,
                    PROGRESS.relative_to(ROOT).as_posix(): progress_hash}
    retired_paths: set[str] = set()
    for filename, list_key, path_key, sources_key in (
        ("V2-Core-Rewrite-Inventory.json", "entries", "build_path", "source_scala"),
        ("V2-Dependency-Family-Inventory.json", "families", "plan_build_file", "source_paths"),
    ):
        mapping, checksum = read_json(ROOT / filename)
        input_hashes[filename] = checksum
        for row in mapping[list_key]:
            build_path = row.get(path_key)
            if not build_path:
                continue
            if row.get("v2_status") == "RETIRED" or str(row.get("disposition", "")).startswith("RETIRED"):
                retired_paths.add(build_path)
                continue
            for source in strings(row.get(sources_key)):
                source_candidates[source_key(source)].add(build_path)
    proofs = {row["build_id"]: row for row in progress["proofs"]}
    hashes: dict[str, str] = {}
    proven_modules: dict[str, set[str]] = defaultdict(set)
    build_rows: list[dict[str, Any]] = []
    for record in builds:
        path = ROOT / record["new_path"]
        data = path.read_bytes()
        text = data.decode("utf-8")
        tree = ast.parse(text, filename=record["new_path"])
        declarations = module_declarations(tree, locked)
        checksum = digest(data)
        hashes[record["new_path"]] = checksum
        for name in declarations["catalog"] if record["new_path"] not in retired_paths else []:
            state = ("CONTRACT_ONLY" if name in declarations["contract_only"] else
                     "DECLARED_IMPLEMENTED_UNVERIFIED" if name in declarations["declared_implemented"] else
                     "CATALOG_ONLY_NEEDS_BEHAVIOR_AUDIT")
            declared[name].append({"build": record["new_path"], "state": state})
        proof = proofs.get(record["build_id"], {})
        fresh_pass = proof.get("status") == "PASS" and current_sources(proof, hashes)
        if fresh_pass:
            for name in proof_modules(proof, locked):
                proven_modules[name].add(record["new_path"])
        identity = record["build_id"].removeprefix("Build-Cpu.")
        expected_test = "python/Program-System/System-Testing/Testing-Cpu/Testing-Cpu-" + identity + "-Hardware.py"
        positions = [text.find(zone) for zone in ZONES]
        findings = []
        if any(pos < 0 for pos in positions) or positions != sorted(positions):
            findings.append("fixed five-zone order missing")
        if re.search(r"\bscala\b|\bXiangShan\b|\bXSTop\b|reference-sv/|SOURCE_PATHS", text, re.I):
            findings.append("product/provenance separation requires review")
        doc_lines: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                    and isinstance(node.value.value, str):
                doc_lines.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
        lines = text.splitlines()
        code_lines = sum(bool(line.strip()) and not line.lstrip().startswith("#")
                         and index not in doc_lines for index, line in enumerate(lines, 1))
        build_rows.append({**record, "sha256": checksum, **declarations,
                           "lines_total": len(lines), "lines_nonempty": sum(bool(line.strip()) for line in lines),
                           "lines_excluding_comments_docstrings": code_lines,
                           "direct_test_expected": expected_test,
                           "direct_test_registered": expected_test in tests,
                           "direct_test_exists": (ROOT / expected_test).is_file(),
                           "retired_inventory_subject": record["new_path"] in retired_paths,
                           "saved_strict_status": proof.get("status", "NO_STRICT_RECEIPT"),
                           "saved_pass_sources_still_match": fresh_pass,
                           "static_findings": findings})
    rows = []
    for name, module in sorted(modules.items()):
        mapped = sorted({path for source in module["scala_sources"]
                         for path in source_candidates[source_key(source)]})
        candidates = declared[name]
        status = ("AUDITED_FORMAL_BUILD_SCOPE" if proven_modules[name] else
                  "EXPLICIT_CONTRACT_ONLY" if candidates and all(item["state"] == "CONTRACT_ONLY" for item in candidates) else
                  "EXPLICIT_CATALOG_BEHAVIOR_PENDING" if candidates else "NO_EXACT_EXECUTABLE_OWNER_CONFIRMED")
        rows.append({"module": name, "reachable_from_XSTop": name in reachable,
                     "status": status, "ports": module["port_count"], "children": module["children"],
                     "scala_sources": module["scala_sources"], "exact_catalog_candidates": candidates,
                     "source_mapping_candidates_not_implementation": mapped,
                     "fresh_audited_build_scopes": sorted(proven_modules[name]),
                     "requires_parent_and_reset_acceptance": True})
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.strip()
    working = subprocess.run(["git", "status", "--short"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.splitlines()
    return {"schema_version": 1, "kind": "V2_COMPLETE_CLOSURE_IMPLEMENTATION_INVENTORY",
            "git_commit": git, "worktree_status_at_snapshot": working,
            "inputs_sha256": input_hashes, "locked_xstop_sha256": EXPECTED_HASH,
            "policy": "Static exact catalogs and broad source mappings do not establish behavior; saved audited proofs with changed sources are excluded; reset/parent/top acceptance is separate.",
            "summary": {"locked_modules": len(rows), "reachable_modules": len(reachable),
                        "module_status_counts": dict(Counter(row["status"] for row in rows)),
                        "build_files": len(build_rows),
                        "historical_ledger_fraction": progress["fraction"],
                        "saved_pass_builds_current_sources": sum(row["saved_pass_sources_still_match"] for row in build_rows),
                        "build_raw_lines": sum(row["lines_total"] for row in build_rows),
                        "build_nonempty_lines": sum(row["lines_nonempty"] for row in build_rows),
                        "build_code_lines": sum(row["lines_excluding_comments_docstrings"] for row in build_rows),
                        "builds_without_registered_direct": sum(not row["direct_test_registered"] for row in build_rows)},
            "builds": build_rows, "modules": rows, "acceptance_eligible": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "validation/v2-complete-closure-inventory.json")
    args = parser.parse_args()
    payload = inventory()
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(payload["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
