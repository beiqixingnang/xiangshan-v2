"""Validate newly implemented utility residual members without widening claims."""

from __future__ import annotations

import json
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from v2_strict_family_rail import FamilyRail, load_module


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Build-Cpu.Dependency.Utility.ResidualFamily-Hardware.py"
)
DIRECT_TEST = ROOT / (
    "python/Program-System/System-Testing/Testing-Cpu/"
    "Testing-Cpu.Dependency.Utility.ResidualFamily-Hardware.py"
)
EVIDENCE = ROOT / "validation/v2-utility-residual-rewrite-wave-results.json"
MEMBERS = (
    "CSA_Nto2With3to2MainPipeline",
    "ClockGate",
    "JtagTapController",
    "skidBufferConnect",
)


def proof_summary(item: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Return the strict gates relevant to one focused member."""

    proof = result.get("yosys_equiv") or result.get("sat_miter") or {}
    formal_pass = bool(
        item["abi_exact"]
        and item["deterministic"]
        and item["view_trusted"]
        and result["verilator"]["status"] == "PASS"
        and result["locked_verilator"]["status"] == "PASS"
        and proof.get("status") == "PASS"
        and proof.get("formal_success_marker") is True
        and proof.get("unproven_cells", 0) == 0
    )
    return {
        "member": item["name"],
        "abi_exact": item["abi_exact"],
        "deterministic_export": item["deterministic"],
        "reference_view_trusted": item["view_trusted"],
        "target_verilator": result["verilator"]["status"],
        "reference_verilator": result["locked_verilator"]["status"],
        "formal_method": result["method"],
        "formal_status": "PASS" if formal_pass else "PENDING",
        "formal_tool_status": proof.get("status"),
        "formal_success_marker": proof.get("formal_success_marker"),
        "equiv_cells": proof.get("equiv_cells"),
        "unproven_cells": proof.get("unproven_cells"),
        "diagnostic_tail": proof.get("output_tail", "")[-1200:],
    }


def main() -> int:
    """Run direct tests and serial locked-reference checks for this wave."""

    py_compile.compile(str(BUILD), doraise=True)
    py_compile.compile(str(DIRECT_TEST), doraise=True)
    direct = subprocess.run(
        [sys.executable, str(DIRECT_TEST), "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    rail = FamilyRail(BUILD, "UtilityResidualRewriteWave", EVIDENCE)
    shutil.rmtree(rail.work, ignore_errors=True)
    rail.work.mkdir(parents=True)
    module = load_module("v2_utility_residual_rewrite_wave", BUILD)
    records = []
    for member in MEMBERS:
        item = rail.prepare(module, member)
        records.append(proof_summary(item, rail.prove(item)))

    formal_passes = [record["member"] for record in records if record["formal_status"] == "PASS"]
    formal_pending = [record["member"] for record in records if record["formal_status"] != "PASS"]
    direct_pass = direct.returncode == 0
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_UTILITY_RESIDUAL_REWRITE_WAVE",
        "build": BUILD.relative_to(ROOT).as_posix(),
        "direct_test": DIRECT_TEST.relative_to(ROOT).as_posix(),
        "implemented_members": list(MEMBERS),
        "direct_test_status": "PASS" if direct_pass else "FAIL",
        "direct_test_output": (direct.stdout + direct.stderr)[-1600:],
        "formal_equivalent_members": formal_passes,
        "formal_pending_members": formal_pending,
        "records": records,
        "strict_equivalence_count_delta": 0,
        "strict_equivalence_fraction": "39/118",
        "status": (
            "PASS_BOUNDED_PARTIAL_FORMAL"
            if direct_pass and formal_passes == ["CSA_Nto2With3to2MainPipeline", "skidBufferConnect"]
            and formal_pending == ["ClockGate", "JtagTapController"]
            else "FAIL"
        ),
        "unclosed": [
            "JtagTapController remains outside strict completion until its parent-state relation is proven.",
            "ClockGate, DebugTransportModuleJTAG, and PrintCommitIDModule remain CONTRACT_ONLY.",
            "The aggregate Build cannot increment the strict rail until every observable member closes.",
        ],
        "acceptance_eligible": False,
    }
    EVIDENCE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({
        "status": payload["status"],
        "direct": payload["direct_test_status"],
        "formal_pass": formal_passes,
        "formal_pending": formal_pending,
    }, ensure_ascii=False))
    return 0 if payload["status"] == "PASS_BOUNDED_PARTIAL_FORMAL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
