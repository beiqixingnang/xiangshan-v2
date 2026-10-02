"""Track reviewed source obligations separately from mapping and Verilog export."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "validation/v2-all-source-rewrite-plan.json"
OUTPUT = ROOT / "validation/v2-all-source-implementation-progress.json"


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    receipts = []
    for path in sorted((ROOT / "validation").glob("v2-all-source-*-implementation-receipt.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        receipts.append((path, payload))
    file_rows = []
    target_kinds = {row["path"]: row.get("kind", "build") for row in plan["python_files"]}
    for row in plan["files"]:
        required = bool(row["python_targets"]) and row["classification"] != "TEST_ONLY"
        result = {"path": row["path"], "classification": row["classification"], "python_targets": row["python_targets"],
                  "implementation_required": required,
                  "status": "IMPLEMENTATION_REVIEW_PENDING" if required else "REVIEWED_NON_RTL_DISPOSITION",
                  "receipt": None, "remaining_feature_obligations": row.get("feature_obligations", [])}
        matches = [(path, payload, entry) for path, payload in receipts for entry in payload.get("sources", [])
                   if entry.get("path") == row["path"] and entry.get("complete_feature_review") is True]
        if len(matches) > 1:
            result["status"] = "DUPLICATE_IMPLEMENTATION_CLAIM"
        elif matches:
            receipt_path, payload, entry = matches[0]
            source_ok = entry.get("sha256") == row["sha256"] == checksum(ROOT / row["path"])
            bound_builds = payload.get("builds", [])
            bindings = {item["path"]: item for item in bound_builds}
            build_ok = bool(row["python_targets"]) and all(
                target in bindings and (ROOT / target).is_file()
                and bindings[target].get("sha256") == checksum(ROOT / target)
                and bindings[target].get("native_export_pass" if target_kinds[target] == "build" else "runtime_import_pass") is True
                for target in row["python_targets"])
            obligations = entry.get("feature_implementations", [])
            planned_obligations = row.get("feature_obligations", [])
            reviewed = {item.get("obligation") for item in obligations if item.get("python_symbol") and item.get("review_status") == "IMPLEMENTED_REVIEWED"}
            full_review = set(planned_obligations).issubset(reviewed) and not entry.get("unimplemented_features")
            if required and source_ok and build_ok and full_review:
                result["status"] = "IMPLEMENTED_EXPORT_PASS_BEHAVIOR_UNVERIFIED"
                result["remaining_feature_obligations"] = []
                result["receipt"] = {"path": receipt_path.relative_to(ROOT).as_posix(), "sha256": checksum(receipt_path)}
            else:
                result["status"] = "STALE_OR_INCOMPLETE_IMPLEMENTATION_REVIEW"
        file_rows.append(result)
    counts = Counter(row["status"] for row in file_rows)
    required_count = sum(row["implementation_required"] for row in file_rows)
    implemented = counts["IMPLEMENTED_EXPORT_PASS_BEHAVIOR_UNVERIFIED"]
    payload = {"kind": "V2_ALL_SOURCE_REWRITE_COVERAGE_PROGRESS", "source_plan_sha256": checksum(PLAN),
               "all_scala_files": len(file_rows), "hardware_and_configuration_sources_required": required_count,
               "implemented_export_pass_sources": implemented,
               "status_counts": dict(counts), "files": file_rows,
               "mapping_complete": plan["mapping_partition_complete"],
               "source_rewrite_coverage_complete": implemented == required_count and not counts["DUPLICATE_IMPLEMENTATION_CLAIM"],
               "behavior_validation_ready": implemented == required_count and not counts["DUPLICATE_IMPLEMENTATION_CLAIM"],
               "behavior_validation": "NOT_RUN_PHASE_DEFERRED", "acceptance_eligible": False,
               "policy": "A source is covered only when all recorded feature obligations have reviewed Python symbols and current native export receipts; mappings or port catalogs are never sufficient."}
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: payload[key] for key in (
        "all_scala_files", "hardware_and_configuration_sources_required", "implemented_export_pass_sources",
        "status_counts", "source_rewrite_coverage_complete")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
