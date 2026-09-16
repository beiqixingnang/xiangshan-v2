"""Register the hierarchy-completion wave Build subjects in the plan manifests.

把层级补全波次新增的 Build 主题登记进计划台账。

Coordinator tooling.  It appends the new subjects to `V2-Core-Rewrite-Inventory.json`
and `V2-Dependency-Family-Inventory.json`, refreshes the derived counts in
`V2-Rewrite-Batch-Plan.json` and `V2-Rewrite-Freeze-Manifest.json`, and is
idempotent: an existing subject id is updated in place, never duplicated.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "V2-Core-Rewrite-Inventory.json"
FAMILY = ROOT / "V2-Dependency-Family-Inventory.json"
PLAN = ROOT / "V2-Rewrite-Batch-Plan.json"
FREEZE = ROOT / "V2-Rewrite-Freeze-Manifest.json"

CORE_ADDITIONS = [
    {
        "id": "CSRModule",
        "source_scala": "scala/src/main/scala/xiangshan/backend/fu/NewCSR/CSRModule.scala",
        "build_path": "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Fu.NewCSR.CSRModule-Hardware.py",
        "family_id": "core.backend.newcsr",
        "closure_root": "core.backend.newcsr",
        "classification": "REWRITTEN",
        "disposition": "DIRECT_TEST_PASS_BOUNDED",
        "v2_status": "VALIDATOR_PASS_BOUNDED",
        "reference_surface": [
            "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/CSRModule.scala",
            "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/CSRBundles.scala",
            "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/CSRFields.scala",
            "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/CSRDefines.scala",
        ],
    },
    {
        "id": "CSRLite",
        "source_scala": "scala/src/main/scala/xiangshan/backend/fu/NewCSR/CSRPMP.scala",
        "build_path": "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Fu.NewCSR.CSRLite-Hardware.py",
        "family_id": "core.backend.newcsr",
        "closure_root": "core.backend.newcsr",
        "classification": "REWRITTEN",
        "disposition": "DIRECT_TEST_PASS_BOUNDED",
        "v2_status": "VALIDATOR_PASS_BOUNDED",
        "reference_surface": [
            "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/CSRPMP.scala",
            "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/CSRPMA.scala",
        ],
    },
]

FAMILY_ADDITIONS = [
    {
        "family_id": "dependency.chisel.decoupled",
        "kind": "dependency",
        "plan_build_file": "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Dependency.Chisel.Decoupled-Hardware.py",
        "source_roots": ["chisel3"],
        "scala_source_count": 2,
        "source_paths": [
            "chisel3/src/main/scala/chisel3/util/Decoupled.scala",
            "chisel3/src/main/scala/chisel3/util/PipeWithFlush.scala",
        ],
        "covered_locked_modules": 216,
        "boundary": "Chisel Queue/BundleMap/PipeWithFlush ready-valid boundary; pinned artifact is the authority because chisel3 is not vendored",
        "status": "DIRECT_TEST_PASS_BOUNDED",
        "exclusion_rationale": "chisel3 library sources are not vendored; the pinned V2 artifact carries per-line provenance for every derived module",
    },
    {
        "family_id": "dependency.chisel.arbiter",
        "kind": "dependency",
        "plan_build_file": "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Dependency.Chisel.Arbiter-Hardware.py",
        "source_roots": ["chisel3", "rocket-chip"],
        "scala_source_count": 3,
        "source_paths": [
            "chisel3/src/main/scala/chisel3/util/Arbiter.scala",
            "rocket-chip/src/main/scala/util/AsyncQueue.scala",
            "rocket-chip/src/main/scala/util/Arbiters.scala",
        ],
        "covered_locked_modules": 57,
        "boundary": "arbitration priority and four-phase asynchronous queue handshake boundary",
        "status": "DIRECT_TEST_PASS_BOUNDED",
        "exclusion_rationale": "chisel3 Arbiter sources are not vendored; AsyncQueue is transcribed from the vendored rocket-chip source plus the pinned artifact",
    },
]


def upsert(entries: list, addition: dict, key: str) -> str:
    for index, entry in enumerate(entries):
        if entry.get(key) == addition[key]:
            entries[index] = addition
            return "updated"
    entries.append(addition)
    return "added"


def main() -> int:
    core = json.loads(CORE.read_text(encoding="utf-8"))
    for addition in CORE_ADDITIONS:
        outcome = upsert(core["entries"], addition, "id")
        print(f"core {addition['id']}: {outcome}")
    statuses: dict[str, int] = {}
    for entry in core["entries"]:
        statuses[entry["v2_status"]] = statuses.get(entry["v2_status"], 0) + 1
    core["status"] = "IMPLEMENTATION_WAVES_VALIDATED_BOUNDED_HIERARCHY_WAVE1"
    core["entries_status_counts"] = statuses
    CORE.write_text(json.dumps(core, ensure_ascii=False, indent=1), encoding="utf-8")

    family = json.loads(FAMILY.read_text(encoding="utf-8"))
    for addition in FAMILY_ADDITIONS:
        outcome = upsert(family["families"], addition, "family_id")
        print(f"family {addition['family_id']}: {outcome}")
    FAMILY.write_text(json.dumps(family, ensure_ascii=False, indent=1), encoding="utf-8")

    build_root = ROOT / "python/Program-System/System-Build/Build-Cpu"
    build_files = sorted(build_root.rglob("Build-*-Hardware.py"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    plan["execution_state"]["current_build_file_count"] = len(build_files)
    plan["execution_state"]["hierarchy_wave1_build_files"] = [
        str(path.relative_to(ROOT)).replace("\\", "/") for path in build_files
    ][-4:]
    plan["execution_state"]["hierarchy_wave1_note"] = (
        "Four new aggregate Build subjects were added under the 2026-09-16 "
        "hierarchy-completion amendment; the 78 closure-subject bound is unchanged "
        "and the new subjects are counted separately."
    )
    PLAN.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")

    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    freeze["file_count_semantics"]["current_distinct_build_paths"] = len(build_files)
    freeze["file_count_semantics"]["hierarchy_wave1_added_subjects"] = 4
    freeze["file_count_semantics"]["note"] = (
        "78 remains the frozen closure-subject upper bound.  The 2026-09-16 "
        "hierarchy-completion amendment adds four further aggregate subjects whose "
        "covered modules are counted in validation/v2-hierarchy-coverage.json, not "
        "in the 78."
    )
    FREEZE.write_text(json.dumps(freeze, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"build_files": len(build_files), "core_status_counts": statuses}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
