"""Rebuild the authoritative strict-equivalence progress rail.

重建严格行为等价验证的权威进度清单。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = ROOT / "python/Program-System/System-Build/Build-Cpu"
PLAN = ROOT / "V2-Rewrite-Batch-Plan.json"
OUTPUT = ROOT / "validation/v2-strict-equivalence-progress.json"
EXPECTED_KIND = "XIANGSHAN_KUNMINGHU_V2_STRICT_COMPLETE_EQUIVALENCE"
NON_COUNTING_STATUSES = ("STRICT_PENDING", "COMPLETE_EQUIVALENCE_VARIANT_ONLY")
LOCKED_REFERENCE_NAMES = {path.stem for path in (ROOT / "validation/reference-sv").glob("*.sv")}
SUCCESS_MARKER = "SAT proof finished - no model found: SUCCESS!"
EQUIV_SUCCESS_MARKERS = (
    "0 are unproven.",
    "Equivalence successfully proven!",
)


def sha256(path: Path) -> str:
    """Return the exact SHA-256 digest. / 返回精确 SHA-256 摘要。"""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def nested(payload: dict[str, Any], *keys: str) -> Any:
    """Read a nested evidence value. / 读取嵌套证据值。"""

    value: Any = payload
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def verify_source(record: Any, label: str, failures: list[str]) -> dict[str, Any]:
    """Verify one source path and digest. / 验证一个来源路径及摘要。"""

    if not isinstance(record, dict):
        failures.append(f"missing source record: {label}")
        return {"status": "FAIL"}
    relative = str(record.get("path", ""))
    path = ROOT / relative
    expected = str(record.get("sha256", ""))
    present = path.is_file()
    observed = sha256(path) if present else None
    matched = present and bool(expected) and observed == expected
    if not matched:
        failures.append(f"source digest: {label}")
    return {
        "path": relative,
        "present": present,
        "expected_sha256": expected,
        "observed_sha256": observed,
        "status": "PASS" if matched else "FAIL",
    }


def locked_reference_names() -> set[str]:
    """Return every module name that has an exact locked reference file."""

    return {path.stem for path in (ROOT / "validation/reference-sv").glob("*.sv")}


def build_locked_members(build_path: Path, locked_names: set[str]) -> set[str]:
    """Enumerate the locked modules a catalog Build exposes.

    Covers ``COVERED_MODULES`` and ``*_MEMBERS`` tuples plus ``*_SPECS`` mapping
    keys and string-compared member selectors, keeping only names that have an
    exact locked reference file.
    """

    if not build_path.is_file():
        return set()
    text = build_path.read_text(encoding="utf-8")
    candidates: set[str] = set()
    for table in re.finditer(r'\b(?:COVERED_MODULES|[A-Z_]+_MEMBERS)[^=]*=\s*([\(\[])(.*?)[\)\]]',
                             text, re.S):
        candidates |= set(re.findall(r'"([^"]+)"', table.group(2)))
    for name in re.findall(r'^([A-Z_]+_SPECS):', text, re.M):
        block = re.search(re.escape(name) + r':.*?\n\}', text, re.S)
        if block is not None:
            candidates |= set(re.findall(r'^\s{4}"([^"]+)":', block.group(0), re.M))
    candidates |= set(re.findall(
        r'(?:member|module_name|subject|module)\s*==\s*"([A-Za-z_]\w*)"', text))
    return {item for item in candidates if item in locked_names}


def verify_evidence(path: Path, expected_source_commit: str) -> dict[str, Any]:
    """Verify one strict proof without trusting its status string alone. / 不仅依赖状态字符串，验证一份严格证明。"""

    payload = json.loads(path.read_text(encoding="utf-8"))
    failures: list[str] = []
    build_id = str(payload.get("build_id", ""))
    if payload.get("kind") != EXPECTED_KIND:
        failures.append("kind")
    declared_status = str(payload.get("status", ""))
    non_counting = declared_status in NON_COUNTING_STATUSES
    if non_counting:
        if payload.get("strict_complete_eligible") is not False:
            failures.append("non-counting record must not claim strict_complete_eligible")
        if payload.get("strict_complete_count_delta") != 0:
            failures.append("non-counting record must claim strict_complete_count_delta 0")
    else:
        if declared_status != "COMPLETE_EQUIVALENCE":
            failures.append("status")
        if payload.get("strict_complete_eligible") is not True:
            failures.append("strict_complete_eligible")
        if payload.get("strict_complete_count_delta") != 1:
            failures.append("strict_complete_count_delta")
    if not build_id:
        failures.append("build_id")
    source_commit = str(payload.get("source_commit", ""))
    if source_commit != expected_source_commit:
        failures.append("source_commit")

    sources = payload.get("sources", {})
    verified_sources = {
        name: verify_source(record, name, failures)
        for name, record in sources.items()
        if name in {"python_build", "scala", "reference_sv"}
    } if isinstance(sources, dict) else {}
    for required in ("python_build", "reference_sv"):
        if required not in verified_sources:
            failures.append(f"required source: {required}")
    if non_counting:
        if "scala" not in verified_sources:
            row_note = "scala provenance not vendored for this attempt record"
        else:
            row_note = None
    elif "scala" not in verified_sources:
        failures.append("required source: scala")
        row_note = None
    else:
        row_note = None

    claimed_variants: set[str] = set()
    if isinstance(scope_claim := payload.get("scope"), dict):
        if isinstance(public_variants := scope_claim.get("public_variants"), list):
            claimed_variants |= {str(item) for item in public_variants}
        if isinstance(variant_map := scope_claim.get("variants"), dict):
            claimed_variants |= {str(item) for item in variant_map}
    claimed_build = str(verified_sources.get("python_build", {}).get("path", ""))
    if not non_counting and claimed_build:
        members = build_locked_members(ROOT / claimed_build, LOCKED_REFERENCE_NAMES)
        if len(members) > 1 and not members <= claimed_variants:
            failures.append(
                f"aggregate Build exposes {len(members)} locked members but only "
                f"{len(members & claimed_variants)} are proven here")

    proof_method = "sat_miter"
    formal = nested(payload, "checks", "formal", "yosys_formal_miter")
    if not isinstance(formal, dict):
        proof_method = "sequential_equivalence"
        formal = nested(payload, "checks", "formal", "yosys_equiv")
    if not isinstance(formal, dict):
        formal = {}
        if not non_counting:
            failures.append("formal result")
    formal_output = str(formal.get("output_tail", ""))
    formal_command = formal.get("command", [])
    command_text = " ".join(str(item) for item in formal_command) if isinstance(formal_command, list) else str(formal_command)
    if not non_counting:
        if formal.get("returncode") != 0 or formal.get("status") != "PASS":
            failures.append("formal status")
        if formal.get("formal_success_marker") is not True:
            failures.append("formal_success_marker")
        if proof_method == "sat_miter":
            if SUCCESS_MARKER not in formal_output:
                failures.append("SAT success output")
        else:
            if "equiv_induct" not in command_text or "equiv_status -assert" not in command_text:
                failures.append("sequential equivalence command")
            for marker in EQUIV_SUCCESS_MARKERS:
                if marker not in formal_output:
                    failures.append(f"sequential equivalence marker: {marker}")

    scope = payload.get("scope", {})
    if not isinstance(scope, dict) or not scope.get("inputs") or not scope.get("outputs_compared"):
        if not non_counting:
            failures.append("formal scope")
    return {
        "evidence": str(path.relative_to(ROOT)).replace("\\", "/"),
        "build_id": build_id,
        "declared_status": declared_status,
        "source_commit": {
            "expected": expected_source_commit,
            "observed": source_commit,
            "status": "PASS" if source_commit == expected_source_commit else "FAIL",
        },
        "status": ("NON_COUNTING" if non_counting and not failures
                   else "PASS" if not failures else "FAIL"),
        "note": row_note,
        "scope": scope,
        "sources": verified_sources,
        "formal": {
            "proof_method": proof_method,
            "command": formal.get("command"),
            "returncode": formal.get("returncode"),
            "status": formal.get("status"),
            "formal_success_marker": formal.get("formal_success_marker"),
        },
        "failures": failures,
    }


def main() -> int:
    """Reconcile strict proofs against the dynamic Build denominator. / 根据动态 Build 分母核对严格证明。"""

    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    scan_freeze = plan.get("scan_freeze", {})
    expected_source_commit = str(scan_freeze.get("source_commit", ""))
    evidence_paths = sorted((ROOT / "validation").glob("v2-*-strict-evidence.json"))
    rows = [verify_evidence(path, expected_source_commit) for path in evidence_paths]
    seen: set[str] = set()
    duplicates: list[str] = []
    for row in rows:
        build_id = str(row["build_id"])
        if build_id in seen:
            duplicates.append(build_id)
            row["status"] = "FAIL"
            row["failures"].append("duplicate build_id")
        seen.add(build_id)
    builds = sorted(BUILD_ROOT.rglob("*.py"))
    build_claims: dict[str, list[str]] = {}
    for row in rows:
        if row["status"] != "PASS":
            continue
        claimed_path = str(row["sources"].get("python_build", {}).get("path", ""))
        if claimed_path:
            build_claims.setdefault(claimed_path, []).append(str(row["build_id"]))
    aggregate_claims = {path: ids for path, ids in build_claims.items() if len(ids) > 1}
    for row in rows:
        row_path = str(row["sources"].get("python_build", {}).get("path", ""))
        if row["status"] == "PASS" and row_path in aggregate_claims:
            row["status"] = "FAIL"
            row["failures"].append(
                "aggregate Build claimed by "
                f"{len(aggregate_claims[row_path])} strict proofs: {row_path}"
            )
    strict_count = sum(row["status"] == "PASS" for row in rows)
    denominator = len(builds)
    execution = plan.get("execution_state", {})
    plan_count = execution.get("strict_complete_equivalence_build_count")
    plan_denominator = execution.get("strict_complete_equivalence_build_denominator")
    reconciliation = (
        "PASS" if plan_count == strict_count and plan_denominator == denominator else "FAIL"
    )
    accepted_rows = [row for row in rows if row["status"] in ("PASS", "NON_COUNTING")]
    non_counting = [{"evidence": row["evidence"], "build_id": row["build_id"],
                     "declared_status": row["declared_status"], "failures": row["failures"]}
                    for row in rows if row["status"] == "NON_COUNTING"]
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_STRICT_EQUIVALENCE_PROGRESS",
        "build_denominator": denominator,
        "strict_complete_build_count": strict_count,
        "fraction": f"{strict_count}/{denominator}",
        "percentage": round(100.0 * strict_count / denominator, 6) if denominator else 0.0,
        "policy": "Only independently reverified COMPLETE_EQUIVALENCE evidence with the locked source commit, matching source hashes, and either a Yosys SAT no-model miter or fully proven Yosys inductive-equivalence status is counted. STRICT_PENDING and COMPLETE_EQUIVALENCE_VARIANT_ONLY records are inventoried as attempted-but-not-counted instead of failing the rail, and one Build file may not be claimed by several counting proofs.",
        "non_counting_attempt_count": len(non_counting),
        "non_counting_attempts": non_counting,
        "plan_reconciliation": {
            "plan_count": plan_count,
            "plan_denominator": plan_denominator,
            "status": reconciliation,
        },
        "duplicate_build_ids": duplicates,
        "aggregate_build_claim_conflicts": {
            path: ids for path, ids in sorted(aggregate_claims.items())
        },
        "proofs": rows,
        "status": "PASS" if len(accepted_rows) == len(rows) and reconciliation == "PASS" else "FAIL",
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "fraction": payload["fraction"],
                      "proofs": strict_count, "non_counting": len(non_counting),
                      "duplicates": duplicates}, ensure_ascii=False))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
