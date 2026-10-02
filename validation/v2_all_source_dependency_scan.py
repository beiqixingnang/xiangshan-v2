"""Build the reviewed all-source dependency plan from the locked scan seed."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "upstream"
SEED_PATH = ROOT / "validation" / "v2-all-source-scan-seed.json"
RULES_PATH = ROOT / "validation" / "v2-all-source-dependency-rules.json"
OUTPUT_PATH = ROOT / "validation" / "v2-all-source-dependency-scan.json"
SELECTED_ROOTS = {
    "yunsuan",
    "utility",
    "openLLC",
    "huancun",
    "fudian",
    "difftest",
    "coupledL2",
    "ChiselIOPMP",
    "ChiselAIA",
}
STATE_MARKERS = {"Reg", "RegInit", "RegEnable", "RegNext", "Mem", "SyncReadMem"}
FIXTURE_MARKERS = STATE_MARKERS | {"Module", "RawModule", "LazyModule"}
FALLBACK_ROUTES = {"coupled_shared", "utility_residual", "openllc_cache", "huancun_shared", "difftest_remaining", "fudian_fpu"}


def read_json(path: Path) -> dict[str, Any]:
    """Read one UTF-8 JSON evidence file."""

    return json.loads(path.read_text(encoding="utf-8"))


def hash_bytes(data: bytes) -> str:
    """Return the exact SHA-256 digest for source bytes."""

    return hashlib.sha256(data).hexdigest()


def hash_file(path: Path) -> str:
    """Return the exact SHA-256 digest for a file."""

    return hash_bytes(path.read_bytes())


def mask_source(source: str) -> str:
    """Blank Scala comments and string bodies while retaining source layout."""

    result: list[str] = []
    index = 0
    state = "code"
    block_depth = 0
    while index < len(source):
        tail = source[index:]
        char = source[index]
        consumed = 1
        if state == "code":
            if tail.startswith("//"):
                state, consumed = "line", 2
            elif tail.startswith("/*"):
                state, block_depth, consumed = "block", 1, 2
            elif tail.startswith('"""'):
                state, consumed = "triple", 3
            elif char == '"':
                state = "string"
            else:
                result.append(char)
                index += 1
                continue
        elif state == "line" and char == "\n":
            state = "code"
        elif state == "block":
            if tail.startswith("/*"):
                block_depth, consumed = block_depth + 1, 2
            elif tail.startswith("*/"):
                block_depth, consumed = block_depth - 1, 2
                if not block_depth:
                    state = "code"
        elif state == "triple" and tail.startswith('"""'):
            state, consumed = "code", 3
        elif state == "string":
            if char == "\\":
                consumed = min(2, len(tail))
            elif char == '"':
                state = "code"
        result.extend("\n" if item == "\n" else " " for item in source[index:index + consumed])
        index += consumed
    return "".join(result)


def collect_source_details(source: str, seed_row: dict[str, Any], route: dict[str, Any], classification: str) -> list[str]:
    """Add source-specific operation, state, child and guard observations."""

    masked = mask_source(source)
    obligations: list[str] = []
    markers = set(seed_row.get("hardware_markers", []))
    names = [item["name"] for item in seed_row.get("declarations", [])]
    methods = sorted(set(re.findall(
        r"(?m)^\s*(?:(?:private|protected|override|final|lazy|implicit|abstract|sealed|inline)\s+)*def\s+([A-Za-z][A-Za-z0-9_]*)",
        masked,
    )))
    states = sorted(set(re.findall(
        r"\b(?:val|var)\s+([A-Za-z][A-Za-z0-9_]*)\s*=\s*(?:RegInit|RegEnable|RegNext|Reg|SyncReadMem|Mem)\b",
        masked,
    )))
    children = sorted(set(re.findall(
        r"\b(?:Module|LazyModule)\s*\(\s*new\s+([A-Za-z][A-Za-z0-9_]*)",
        masked,
    )))
    branches = sorted(set(re.findall(
        r"\bif\s*\(\s*([^()\n]{1,84})\s*\)",
        masked,
    )))
    if names:
        obligations.append("Declarations owned by this source: " + ", ".join(names) + ". Implement or classify every owner listed below individually.")
    if methods:
        shown = methods[:28]
        suffix = "" if len(methods) <= len(shown) else f"; plus {len(methods) - len(shown)} additional source methods"
        obligations.append("Source-defined operations: " + ", ".join(shown) + suffix + ". Preserve each observable operation's actual equations and control paths.")
    if states:
        shown_states = states[:32]
        suffix = "" if len(states) <= len(shown_states) else f"; plus {len(states) - len(shown_states)} additional state/memory names"
        obligations.append("Source-defined registered state or memory names: " + ", ".join(shown_states) + suffix + ". Preserve reset/init value, write enable, read/write timing and hold behavior from the source.")
    elif markers & STATE_MARKERS:
        obligations.append("This source uses register or memory primitives; identify each state element and preserve its reset, enable, latency and access semantics.")
    if children:
        shown_children = children[:24]
        suffix = "" if len(children) <= len(shown_children) else f"; plus {len(children) - len(shown_children)} additional children"
        obligations.append("Source-instantiated child modules: " + ", ".join(shown_children) + suffix + ". Keep family dependencies explicit and inject their public APIs through the controller.")
    if branches:
        shown_branches = branches[:12]
        suffix = "" if len(branches) <= len(shown_branches) else f"; plus {len(branches) - len(shown_branches)} additional source branches"
        obligations.append("Source configuration/control branches: " + "; ".join(shown_branches) + suffix + ". Retain all listed legal branches even when they are not selected by DefaultConfig.")
    if markers & {"Module", "RawModule", "LazyModule", "IO", "Bundle"}:
        obligations.append("Source declares hardware/module/IO/bundle constructs; preserve each public field's direction, width, signedness and decoupled handshake.")
    if markers & {"Mem", "SyncReadMem"}:
        obligations.append("Source declares memory primitives; preserve depth, port count, masked writes, collision policy and synchronous/asynchronous read latency.")
    guards: list[str] = []
    if re.search(r"\bassert\s*\(", masked):
        guards.append("assert")
    if re.search(r"\brequire\s*\(", masked):
        guards.append("require")
    if guards:
        obligations.append("Source guard constructs: " + ", ".join(guards) + "; preserve the guarded error/illegal-configuration conditions.")
    if route.get("classification") == "AUTO_TEST" and classification == "MIXED_HARDWARE_SUPPORT":
        obligations.append("This test source also declares Chisel hardware helpers; keep them as explicit direct-test fixtures and do not count the Scala test top as a product Build.")
    if route.get("classification") == "AUTO_TEST" and classification == "TEST_ONLY":
        obligations.append("Test-only declarations remain case/vector/configuration obligations for the linked Python direct test; they are not Build implementation symbols.")
    if not obligations:
        obligations.append("No class/object/trait declaration or hardware primitive was detected; preserve the source's explicit host/build contract in the disposition.")
    return obligations


def source_route(path: str, route_specs: list[dict[str, Any]]) -> dict[str, Any]:
    """Find the first reviewed route, allowing only known broad family fallbacks."""

    matches = [item for item in route_specs if re.search(item["pattern"], path)]
    if not matches:
        raise ValueError(f"source has no reviewed route: {path}")
    if len(matches) > 1 and any(item["id"] not in FALLBACK_ROUTES for item in matches[1:]):
        route_names = [item["id"] for item in matches]
        raise ValueError(f"source has overlapping specific routes: {path}: {route_names}")
    return matches[0]


def effective_classification(route: dict[str, Any], seed_row: dict[str, Any]) -> str:
    """Resolve the explicit test-fixture split using scanned Chisel markers."""

    value = route["classification"]
    if value != "AUTO_TEST":
        return value
    markers = set(seed_row.get("hardware_markers", []))
    return "MIXED_HARDWARE_SUPPORT" if markers & FIXTURE_MARKERS else "TEST_ONLY"


def python_path(target_id: str, targets: dict[str, dict[str, Any]]) -> str:
    """Resolve one rule target ID to its complete Build path."""

    if target_id not in targets:
        raise ValueError(f"unknown Build target ID: {target_id}")
    return str(targets[target_id]["path"])


def validate_build_dependency_graph(rules: dict[str, Any]) -> None:
    """Reject unknown companion IDs and Build dependency cycles."""

    specs = {item["id"]: item for item in rules["targets"]}
    runtime_ids = {item["id"] for item in rules.get("runtime_targets", [])}
    graph: dict[str, list[str]] = {}
    for target_id, spec in specs.items():
        graph[target_id] = []
        for companion in spec.get("companions", []):
            if companion in specs:
                graph[target_id].append(companion)
            elif companion not in runtime_ids:
                raise ValueError(f"unknown companion {companion} on {target_id}")
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(target_id: str) -> None:
        status = state.get(target_id, 0)
        if status == 2:
            return
        if status == 1:
            start = stack.index(target_id)
            raise ValueError("Build companion cycle: " + " -> ".join(stack[start:] + [target_id]))
        state[target_id] = 1
        stack.append(target_id)
        for companion in graph[target_id]:
            visit(companion)
        stack.pop()
        state[target_id] = 2

    for target_id in graph:
        visit(target_id)


def direct_test_path(build_path: str) -> str:
    """Derive the direct Testing script path from the formal Build basename."""

    build_name = Path(build_path).name
    if build_name.startswith("Cpu-Core-"):
        test_name = "Testing-Cpu-" + build_name[len("Cpu-Core-"):]
    elif build_name.startswith("Cpu-Memory-"):
        test_name = "Testing-Cpu-Memory-" + build_name[len("Cpu-Memory-"):]
    else:
        raise ValueError(f"unrecognized CPU Build basename: {build_name}")
    return "python/Program-System/System-Testing/Testing-Cpu/" + test_name


def route_declarations(
    seed_row: dict[str, Any],
    route: dict[str, Any],
    classification: str,
    build_paths: list[str],
) -> list[dict[str, str]]:
    """Assign every scanned Scala declaration to its Build, runtime or test role."""

    owners: list[dict[str, str]] = []
    is_test_route = route.get("classification") == "AUTO_TEST"
    for declaration in seed_row.get("declarations", []):
        target = build_paths[0] if build_paths and (classification != "TEST_ONLY" or is_test_route and classification == "MIXED_HARDWARE_SUPPORT") else ""
        disposition = route["disposition"]
        if is_test_route and classification == "MIXED_HARDWARE_SUPPORT":
            disposition = "TEST_FIXTURE_ONLY_DO_NOT_COUNT_AS_PRODUCT_BUILD"
        elif classification == "TEST_ONLY":
            target = ""
            disposition = "TEST_ONLY_CASES_TO_DIRECT_PYTHON_TEST"
        elif classification == "HOST_TOOL":
            target = ""
            disposition = route["disposition"]
        owners.append({
            "name": str(declaration["name"]),
            "kind": str(declaration["kind"]),
            "python_target": target,
            "disposition": disposition,
        })
    return owners


def scan_sources(seed: dict[str, Any], rules: dict[str, Any], source_commit: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Create exact source rows and verify scope, route and lock-seed hashes."""

    routes = rules["routes"]
    target_specs = {item["id"]: item for item in rules["targets"]}
    runtime_specs = rules.get("runtime_targets", [])
    seed_rows = {
        row["path"]: row
        for row in seed["files"]
        if row.get("root") in SELECTED_ROOTS
    }
    actual_paths = sorted(
        path.relative_to(ROOT).as_posix()
        for root_name in SELECTED_ROOTS
        for path in (UPSTREAM / root_name).rglob("*.scala")
    )
    if set(actual_paths) != set(seed_rows):
        missing_seed = sorted(set(actual_paths) - set(seed_rows))
        missing_disk = sorted(set(seed_rows) - set(actual_paths))
        raise ValueError(f"seed/source partition mismatch; absent seed={missing_seed}; absent source={missing_disk}")
    root_counts = Counter(seed_rows[path]["root"] for path in actual_paths)
    expected_root_counts = {item["name"]: item["file_count"] for item in rules["selected_roots"]}
    if dict(sorted(root_counts.items())) != dict(sorted(expected_root_counts.items())):
        raise ValueError(f"selected root counts differ from reviewed rules: {dict(root_counts)} != {expected_root_counts}")

    rows: list[dict[str, Any]] = []
    routed: dict[str, dict[str, Any]] = {}
    route_counts: Counter[str] = Counter()
    for relative in actual_paths:
        seed_row = seed_rows[relative]
        source_path = ROOT / relative
        source_bytes = source_path.read_bytes()
        source_hash = hash_bytes(source_bytes)
        if source_hash != seed_row.get("sha256"):
            raise ValueError(f"source hash differs from seed: {relative}: {source_hash} != {seed_row.get('sha256')}")
        source = source_bytes.decode("utf-8-sig")
        route = source_route(relative, routes)
        classification = effective_classification(route, seed_row)
        route_counts[route["id"]] += 1
        build_paths = [python_path(target_id, target_specs) for target_id in route.get("targets", [])]
        runtime_specs_for_source = [
            item for item in runtime_specs
            if any(re.search(pattern, relative) for pattern in item.get("source_patterns", []))
        ]
        runtime_paths = [str(item["path"]) for item in runtime_specs_for_source]
        declaration_owners = route_declarations(seed_row, route, classification, build_paths)
        obligations = list(route.get("features", []))
        obligations.extend(collect_source_details(source, seed_row, route, classification))
        for runtime_spec in runtime_specs_for_source:
            modes = "; ".join(runtime_spec.get("required_configuration_modes", []))
            obligations.append(
                "Secondary runtime contract " + str(runtime_spec["path"]) + ": "
                + str(runtime_spec["responsibility"]) + " Modes: " + modes + "."
            )
        if not obligations:
            raise ValueError(f"source has no feature obligations: {relative}")
        if len(declaration_owners) != len(seed_row.get("declarations", [])):
            raise ValueError(f"declaration owners do not cover seed declarations: {relative}")
        row = {
            "path": relative,
            "source_sha256": source_hash,
            "classification": classification,
            "reason": str(route["reason"]),
            "python_targets": build_paths + runtime_paths,
            "python_build_targets": build_paths,
            "python_runtime_targets": runtime_paths,
            "runtime_contract_owners": [
                {"python_target": str(item["path"]), "disposition": "SECONDARY_RUNTIME_CONTRACT_SOURCE"}
                for item in runtime_specs_for_source
            ],
            "declaration_owners": declaration_owners,
            "feature_obligations": obligations,
            "scope_claim": "ALL_SOURCE_PLANNED_NOT_IMPLEMENTED",
        }
        rows.append(row)
        routed[relative] = {
            "route": route,
            "classification": classification,
            "seed": seed_row,
            "row": row,
        }
    if sum(route_counts.values()) != len(actual_paths):
        raise ValueError("route count does not match the exact selected source count")
    return rows, routed, [dict(id=key, file_count=value) for key, value in sorted(route_counts.items())]


def build_python_file_index(rules: dict[str, Any], routed: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Produce a source-derived index for every existing or newly planned Build."""

    index: list[dict[str, Any]] = []
    target_specs = {item["id"]: item for item in rules["targets"]}
    target_paths = {key: value["path"] for key, value in target_specs.items()}
    runtime_specs = {item["id"]: item for item in rules.get("runtime_targets", [])}
    for target_id, spec in target_specs.items():
        target_path = str(spec["path"])
        source_rows: list[str] = []
        hardware_symbols: list[dict[str, str]] = []
        for source_path, detail in routed.items():
            route = detail["route"]
            if route.get("classification") == "AUTO_TEST" or detail["classification"] == "HOST_TOOL":
                continue
            if target_path not in detail["row"]["python_build_targets"]:
                continue
            source_rows.append(source_path)
            for owner in detail["row"]["declaration_owners"]:
                if owner["python_target"] == target_path:
                    hardware_symbols.append({"source": source_path, "kind": owner["kind"], "name": owner["name"]})
        dependencies: list[str] = []
        for companion in spec.get("companions", []):
            if companion in target_paths:
                dependencies.append(target_paths[companion])
            elif companion in runtime_specs:
                dependencies.append(str(runtime_specs[companion]["path"]))
            else:
                raise ValueError(f"unknown companion {companion} on {target_id}")
        test_path = direct_test_path(target_path)
        test_disk_path = ROOT / test_path
        build_disk_path = ROOT / target_path
        expected_parent = Path(target_path).parent.name
        if not Path(target_path).name.startswith(expected_parent + "-"):
            raise ValueError(f"Build basename violates parent prefix: {target_path}")
        if not source_rows:
            raise ValueError(f"Build target has no source mapping in selected scope: {target_path}")
        index.append({
            "path": target_path,
            "existing": build_disk_path.is_file(),
            "responsibility": spec["responsibility"],
            "sources": sorted(source_rows),
            "hardware_symbols": sorted(hardware_symbols, key=lambda item: (item["source"], item["kind"], item["name"])),
            "required_configuration_modes": list(spec["required_configuration_modes"]),
            "needed_companion_dependencies": sorted(set(dependencies)),
            "direct_test": {"path": test_path, "existing": test_disk_path.is_file(), "direct_required": True},
        })
    return sorted(index, key=lambda item: item["path"])


def runtime_file_index(rules: dict[str, Any], source_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Produce the separately counted runtime contract index."""

    source_paths = {item["path"] for item in source_rows}
    result: list[dict[str, Any]] = []
    for spec in rules.get("runtime_targets", []):
        matched: set[str] = set()
        for pattern in spec.get("source_patterns", []):
            matched.update(path for path in source_paths if re.search(pattern, path))
        if not matched:
            raise ValueError(f"runtime target has no selected source obligations: {spec['id']}")
        runtime_path = str(spec["path"])
        expected_parent = Path(runtime_path).parent.name
        if not Path(runtime_path).name.startswith(expected_parent + "-"):
            raise ValueError(f"Runtime basename violates parent prefix: {runtime_path}")
        target_disk_path = ROOT / runtime_path
        test_path = str(spec["direct_test"])
        result.append({
            "path": runtime_path,
            "kind": str(spec["kind"]),
            "existing": target_disk_path.is_file(),
            "responsibility": spec["responsibility"],
            "sources": sorted(matched),
            "required_configuration_modes": list(spec["required_configuration_modes"]),
            "needed_companion_dependencies": [],
            "direct_test": {"path": test_path, "existing": (ROOT / test_path).is_file(), "direct_required": True},
        })
    return sorted(result, key=lambda item: item["path"])


def summarize_rows(seed: dict[str, Any], rows: list[dict[str, Any]], python_files: list[dict[str, Any]], runtime_files: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize exact planned coverage without claiming implementation."""

    by_root = Counter(Path(item["path"]).parts[1] for item in rows)
    by_class = Counter(item["classification"] for item in rows)
    owner_count = sum(len(item["declaration_owners"]) for item in rows)
    seed_owner_count = sum(len(seed_row.get("declarations", [])) for seed_row in seed["files"] if seed_row.get("root") in SELECTED_ROOTS)
    if owner_count != seed_owner_count:
        raise ValueError(f"declaration partition mismatch: {owner_count} != {seed_owner_count}")
    existing_builds = sum(bool(item["existing"]) for item in python_files)
    existing_test_paths = sum(bool(item["direct_test"]["existing"]) for item in python_files)
    return {
        "source_file_count": len(rows),
        "source_hash_verified_count": len(rows),
        "source_hashes_match_seed": True,
        "exact_partition_matches_seed_and_disk": True,
        "declaration_owner_count": owner_count,
        "declaration_count_in_seed": sum(len(seed_row.get("declarations", [])) for seed_row in seed["files"] if seed_row.get("root") in SELECTED_ROOTS),
        "locked_source_file_count": sum(1 for seed_row in seed["files"] if seed_row.get("root") in SELECTED_ROOTS and seed_row.get("locked_modules")),
        "by_root": dict(sorted(by_root.items())),
        "by_classification": dict(sorted(by_class.items())),
        "python_build_file_count": len(python_files),
        "existing_python_build_count": existing_builds,
        "new_python_build_count": len(python_files) - existing_builds,
        "existing_direct_test_path_count": existing_test_paths,
        "new_direct_test_path_count": len(python_files) - existing_test_paths,
        "direct_test_registration_status": "NOT_AUDITED",
        "python_runtime_file_count": len(runtime_files),
        "existing_python_runtime_count": sum(bool(item["existing"]) for item in runtime_files),
        "new_python_runtime_count": sum(not bool(item["existing"]) for item in runtime_files),
        "all_sources_planned": True,
        "all_sources_implemented": False,
        "behavior_verified_build_count": 0,
        "acceptance_eligible": False,
    }


def main() -> int:
    """Generate the planning map after verifying every selected source hash."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    seed = read_json(SEED_PATH)
    rules = read_json(RULES_PATH)
    try:
        validate_build_dependency_graph(rules)
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
        source_rows, routed, route_counts = scan_sources(seed, rules, str(seed.get("source_commit", "")))
        python_files = build_python_file_index(rules, routed)
        runtime_files = runtime_file_index(rules, source_rows)
    except (OSError, ValueError, KeyError, re.error) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 1

    summary = summarize_rows(seed, source_rows, python_files, runtime_files)
    payload = {
        "schema_version": 1,
        "kind": "V2_ALL_SOURCE_DEPENDENCY_SCAN",
        "status": "ALL_SOURCE_PLANNED_NOT_IMPLEMENTED",
        "source_commit": seed.get("source_commit", ""),
        "auxiliary_commit_at_scan": head,
        "seed_auxiliary_commit": seed.get("auxiliary_commit", ""),
        "seed_sha256": hash_file(SEED_PATH),
        "rules_sha256": hash_file(RULES_PATH),
        "scope": "The nine explicitly selected upstream roots only; exact source partition verified against disk and the complete all-source scan seed.",
        "selected_roots": [item["name"] for item in rules["selected_roots"]],
        "seed_global_inventory": {
            "source_file_count": seed.get("source_file_count", 0),
            "declared_symbol_count": seed.get("declared_symbol_count", 0),
            "locked_source_file_count": seed.get("locked_source_file_count", 0),
        },
        "mapping_policy": "Historical mapping candidates and existing Build presence are not implementation credit. Every row is a source-derived plan; reused targets still need complete basic export and behavior verification for each listed obligation.",
        "summary": summary,
        "route_counts": route_counts,
        "python_files": python_files,
        "python_runtime_files": runtime_files,
        "files": source_rows,
        "coverage_complete": True,
        "implementation_complete": False,
        "acceptance_eligible": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"summary": summary, "route_counts": route_counts}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
