"""Prove one PMP checker specialization without claiming its parent family.

The full PMP family contains other unfinished members.  This validator uses
the existing locked-reference rail for the exact PMPChecker_2 ABI, the same
Verilator/Yosys proof, and mutations on both comparison sides.  It writes
only a variant-level, non-counting diagnostic record.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import py_compile
import subprocess
import sys
from typing import Any

import v2_strict_family_rail as rail


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Cpu-Core-Backend.Fu.PMP.Family-Hardware.py"
)
DIRECT_TEST = ROOT / (
    "python/Program-System/System-Testing/Testing-Cpu/"
    "Testing-Cpu-Backend.Fu.PMP.Family-Hardware.py"
)
EVIDENCE = ROOT / "validation/v2-pmpchecker2-focused-strict-diagnostic.json"
MEMBER = "PMPChecker_2"


def source_record(path: Path) -> dict[str, Any]:
    """Record the exact path, size, and digest of one proof input."""

    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def direct_test() -> dict[str, Any]:
    """Run the family direct test without affecting the formal rail."""

    result = subprocess.run(
        [sys.executable, "-B", str(DIRECT_TEST), "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=180,
    )
    output = result.stdout + result.stderr
    return {
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "returncode": result.returncode,
        "output_tail": output[-1000:],
        "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
    }


def main() -> int:
    """Run exact variant proof and retain its non-counting evidence."""

    for path in (BUILD, DIRECT_TEST, Path(__file__).resolve()):
        py_compile.compile(str(path), doraise=True)
    module = rail.load_module("pmpchecker2_focused", BUILD)
    runner = rail.FamilyRail(
        BUILD,
        "Build-Cpu.Backend.Fu.PMP.Family.Checker2Diagnostic",
        EVIDENCE,
    )
    runner.work.mkdir(parents=True, exist_ok=True)
    item = runner.prepare(module, MEMBER)
    result = runner.prove(item)
    proof = result.get("yosys_equiv", {})
    negative = runner.negative_control([item])
    direct = direct_test()
    exact_ports = len(item["inputs"]) + len(item["outputs"])
    formal_pass = (
        item["abi_exact"] is True
        and item["deterministic"] is True
        and item["view_trusted"] is True
        and exact_ports == 327
        and sum(item["outputs"].values()) == 2
        and result["verilator"]["status"] == "PASS"
        and result["locked_verilator"]["status"] == "PASS"
        and proof.get("returncode") == 0
        and proof.get("status") == "PASS"
        and proof.get("formal_success_marker") is True
        and proof.get("equiv_cells") == 2
        and proof.get("proven_cells") == 2
        and proof.get("unproven_cells") == 0
    )
    control_cases = negative.get("cases", {})
    two_sided_control = (
        negative.get("status") == "PASS"
        and all(
            control_cases.get("sequential." + side, {}).get("status") == "PASS"
            and control_cases["sequential." + side].get("mutation_applied") is True
            and control_cases["sequential." + side].get("explicit_failure_marker") is True
            and control_cases["sequential." + side].get("success_marker_still_present") is False
            for side in ("target", "reference")
        )
    )
    variant_pass = formal_pass and two_sided_control and direct["status"] == "PASS"
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_PMP_CHECKER2_VARIANT_STRICT_DIAGNOSTIC",
        "build_id": "Build-Cpu.Backend.Fu.PMP.Family",
        "member": MEMBER,
        "status": "COMPLETE_EQUIVALENCE_VARIANT_ONLY" if variant_pass else "STRICT_PENDING",
        "variant_strict_proven": variant_pass,
        "strict_complete_build_count_delta": 0,
        "acceptance_eligible": False,
        "scope": {
            "build_catalog_members": list(rail.enumerate_members(module, BUILD)),
            "only_member_proven_in_this_record": MEMBER,
            "abi_ports": exact_ports,
            "input_bits": sum(item["inputs"].values()),
            "output_bits": sum(item["outputs"].values()),
            "outputs_compared": item["outputs"],
            "locked_children": item["children"],
        },
        "sources": {
            "python_build": source_record(BUILD),
            "direct_test": source_record(DIRECT_TEST),
            "validator": source_record(Path(__file__).resolve()),
            "strict_family_rail": source_record(Path(rail.__file__).resolve()),
            "locked_reference": source_record(rail.REF_DIR / f"{MEMBER}.sv"),
        },
        "checks": {
            "py_compile": "PASS",
            "abi_exact": item["abi_exact"],
            "deterministic_export": item["deterministic"],
            "locked_reference_view_trusted": item["view_trusted"],
            "reference_view_audits": item["view_audits"],
            "target_verilator": result["verilator"],
            "locked_verilator": result["locked_verilator"],
            "yosys_equiv": proof,
            "two_sided_negative_control": negative,
            "direct_test": direct,
        },
        "unclosed": [
            "PMP, PMPChecker, PMPChecker_12, and PMPEntryHandleModule are not proven by this record.",
            "The full PMP family, parent closure, product identity review, license review, and user approval remain pending.",
        ],
    }
    EVIDENCE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({
        "status": payload["status"],
        "formal": f"{proof.get('proven_cells')}/{proof.get('equiv_cells')}",
        "negative_control": negative.get("status"),
        "direct_test": direct["status"],
        "strict_complete_build_count_delta": 0,
    }, ensure_ascii=False))
    return 0 if variant_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
