"""Record the reviewed implementation wave without hiding acceptance gaps."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = ROOT / "python/Program-System/System-Build/Build-Cpu"
BASELINE = "04205060c9c67df2d83e1d1ad2e8708847a615f9"
OUTPUT = ROOT / "validation/v2-complete-implementation-wave-01.json"
SUBJECTS = (
    "Cpu-Core-Backend.Fu.FloatingPoint.Family-Hardware.py",
    "Cpu-Core-Backend.Fu.NewCSR.XRetPermit-Hardware.py",
    "Cpu-Core-Dependency.Fpu.NormalizeRoundFamily-Hardware.py",
    "Cpu-Core-Dependency.Utility.DelayFamily-Hardware.py",
    "Cpu-Core-Dependency.Utility.BitSelectFamily-Hardware.py",
    "Cpu-Memory-Memory.Dcache.MissQueue.Family-Hardware.py",
    "Cpu-Memory-Memory.Store.Family-Hardware.py",
)
RECEIPTS = (
    "v2-build-cpu-backend-fu-newcsr-xretpermit-strict-evidence.json",
    "v2-build-cpu-dependency-rocket-tlchildren-family-strict-evidence.json",
    "v2-build-cpu-dependency-fpu-normalizeroundfamily-strict-evidence.json",
    "v2-build-cpu-dependency-utility-delayfamily-strict-evidence.json",
    "v2-build-cpu-dependency-utility-bitselectfamily-strict-evidence.json",
    "v2-floating-point-leaf-wave-results.json",
    "v2-floating-booth-cone-focused-results.json",
    "v2-normalize-round-family-wave-results.json",
    "v2-utility-delay-wave-results.json",
    "v2-bitselect-family-wave-results.json",
    "v2-dcache-completion-wave-results.json",
    "v2-dcache-completion-focused-formal-results.json",
    "v2-store-two-member-focused-results.json",
)


def record(path: Path) -> dict[str, object]:
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main() -> int:
    progress = json.loads((ROOT / "validation/v2-strict-equivalence-progress.json").read_text(encoding="utf-8"))
    closure = json.loads((ROOT / "validation/v2-complete-closure-inventory.json").read_text(encoding="utf-8"))
    command = [sys.executable, "-B", "validation/v2_python_size_audit.py", "--baseline", BASELINE]
    size_run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True)
    size = json.loads(size_run.stdout)
    static = []
    for name in SUBJECTS:
        paths = list(BUILD_ROOT.rglob(name))
        if len(paths) != 1:
            raise ValueError("missing or duplicate reviewed Build: " + name)
        path = paths[0]
        source = path.read_text(encoding="utf-8")
        compile(source, str(path), "exec")
        positions = [source.find("# " + zone) for zone in (
            "Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry")]
        valid = (min(positions) >= 0 and positions == sorted(positions)
                 and not re.search(r"\bscala\b|\bXiangShan\b|\bXSTop\b|SOURCE_PATHS|reference-sv|BEGIN LOCKED PORT", source, re.I))
        if not valid:
            raise ValueError("product structure/provenance audit failed: " + name)
        static.append({**record(path), "syntax": "PASS", "five_zone_order": "PASS", "provenance_separation": "PASS"})
    audited_new = []
    for name in RECEIPTS[:5]:
        path = "validation/" + name
        matches = [row for row in progress["proofs"] if row["evidence"] == path]
        if len(matches) != 1 or matches[0]["status"] != "PASS":
            raise ValueError("complete wave proof is not independently audited: " + name)
        audited_new.append(matches[0]["build_id"])
    payload = {
        "kind": "V2_REVIEWED_COMPLETE_IMPLEMENTATION_WAVE", "baseline": BASELINE,
        "status": "REAL_IMPLEMENTATION_PROGRESS_ACCEPTANCE_PENDING",
        "strict_formal_builds": progress["fraction"], "strict_formal_delta": 5,
        "full_build_acceptance": f"0/{progress['build_denominator']}", "accepted": 0,
        "central_audit_status": progress["status"],
        "historical_failed_receipts": [row["build_id"] for row in progress["proofs"] if row["status"] == "FAIL"],
        "new_or_revalidated_complete_builds": audited_new,
        "new_aggregate_builds": {"NormalizeRoundFamily": 17, "DelayFamily": 48, "BitSelectFamily": 10},
        "new_exact_member_ownership": 75,
        "locked_module_definitions": closure["summary"]["locked_modules"],
        "formal_build_scope_modules": closure["summary"]["module_status_counts"]["AUDITED_FORMAL_BUILD_SCOPE"],
        "unknown_exact_owner": closure["summary"]["module_status_counts"]["NO_EXACT_EXECUTABLE_OWNER_CONFIRMED"],
        "contract_only_modules": closure["summary"]["module_status_counts"]["EXPLICIT_CONTRACT_ONLY"],
        "catalog_pending_modules": closure["summary"]["module_status_counts"]["EXPLICIT_CATALOG_BEHAVIOR_PENDING"],
        "coverage_policy": "1976 elaborated module definitions, not Scala file or instance counts; catalog ownership is not behavior acceptance.",
        "python_size": size, "static_review": static,
        "receipt_sources": [record(ROOT / "validation" / name) for name in RECEIPTS],
        "partial_family_proofs": {"DcacheMissQueueFamily": "4/7 focused formal and two-sided controls; not a complete Build",
                                  "FloatingPointFamily": "Booth 27/27 unconstrained output cones; ArrayMul 69-vector locked-closure differential only",
                                  "StoreFamily": "2/4 implementation and locked-output differential; formal and remaining members pending"},
        "resource_policy": "WSL formal serialized; complete-output cone proofs replace oversized worksets without input assumptions",
        "unrun_or_unclosed": ["global Pyright milestone", "historical receipt repairs", "reset/startup acceptance beyond recorded proof relations",
                              "remaining exact implementations and direct tests", "all parent/top closures", "full CPU transactions",
                              "license acceptance", "user approval and preview integration"],
        "main_product_changes": False, "locked_reference_changes": False, "acceptance_eligible": False,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"strict": payload["strict_formal_builds"], "module_scope": payload["formal_build_scope_modules"],
                      "unknown_owner": payload["unknown_exact_owner"], "python": size["current"], "delta": size["delta"],
                      "accepted": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
