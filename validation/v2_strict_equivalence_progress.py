"""Rebuild the authoritative strict-equivalence progress rail.

重建严格行为等价验证的权威进度清单。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = ROOT / "python/Program-System/System-Build/Build-Cpu"
PLAN = ROOT / "V2-Rewrite-Batch-Plan.json"
OUTPUT = ROOT / "validation/v2-strict-equivalence-progress.json"
EXPECTED_KIND = "XIANGSHAN_KUNMINGHU_V2_STRICT_COMPLETE_EQUIVALENCE"
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


def verify_evidence(path: Path, expected_source_commit: str) -> dict[str, Any]:
    """Verify one strict proof without trusting its status string alone. / 不仅依赖状态字符串，验证一份严格证明。"""

    payload = json.loads(path.read_text(encoding="utf-8"))
    failures: list[str] = []
    build_id = str(payload.get("build_id", ""))
    if payload.get("kind") != EXPECTED_KIND:
        failures.append("kind")
    if payload.get("status") != "COMPLETE_EQUIVALENCE":
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
    for required in ("python_build", "scala", "reference_sv"):
        if required not in verified_sources:
            failures.append(f"required source: {required}")

    proof_method = "sat_miter"
    formal = nested(payload, "checks", "formal", "yosys_formal_miter")
    if not isinstance(formal, dict):
        proof_method = "sequential_equivalence"
        formal = nested(payload, "checks", "formal", "yosys_equiv")
    if not isinstance(formal, dict):
        failures.append("formal result")
        formal = {}
    if formal.get("returncode") != 0 or formal.get("status") != "PASS":
        failures.append("formal status")
    if formal.get("formal_success_marker") is not True:
        failures.append("formal_success_marker")
    formal_output = str(formal.get("output_tail", ""))
    formal_command = formal.get("command", [])
    command_text = " ".join(str(item) for item in formal_command) if isinstance(formal_command, list) else str(formal_command)
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
        failures.append("formal scope")
    return {
        "evidence": str(path.relative_to(ROOT)).replace("\\", "/"),
        "build_id": build_id,
        "source_commit": {
            "expected": expected_source_commit,
            "observed": source_commit,
            "status": "PASS" if source_commit == expected_source_commit else "FAIL",
        },
        "status": "PASS" if not failures else "FAIL",
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
    strict_count = sum(row["status"] == "PASS" for row in rows)
    denominator = len(builds)
    execution = plan.get("execution_state", {})
    plan_count = execution.get("strict_complete_equivalence_build_count")
    plan_denominator = execution.get("strict_complete_equivalence_build_denominator")
    reconciliation = (
        "PASS" if plan_count == strict_count and plan_denominator == denominator else "FAIL"
    )
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_STRICT_EQUIVALENCE_PROGRESS",
        "build_denominator": denominator,
        "strict_complete_build_count": strict_count,
        "fraction": f"{strict_count}/{denominator}",
        "percentage": round(100.0 * strict_count / denominator, 6) if denominator else 0.0,
        "policy": "Only independently reverified COMPLETE_EQUIVALENCE evidence with the locked source commit, matching source hashes, and either a Yosys SAT no-model miter or fully proven Yosys inductive-equivalence status is counted.",
        "plan_reconciliation": {
            "plan_count": plan_count,
            "plan_denominator": plan_denominator,
            "status": reconciliation,
        },
        "duplicate_build_ids": duplicates,
        "proofs": rows,
        "status": "PASS" if all(row["status"] == "PASS" for row in rows) and reconciliation == "PASS" else "FAIL",
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "fraction": payload["fraction"], "proofs": len(rows), "duplicates": duplicates}))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
