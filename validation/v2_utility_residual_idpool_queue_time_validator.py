"""Strict focused rail for the repaired IDPool/queue/TimeAsync members."""

from __future__ import annotations

import hashlib
import json
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from v2_strict_family_rail import FamilyRail, load_module, run_wsl, wsl_path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Build-Cpu.Dependency.Utility.ResidualFamily-Hardware.py"
)
DIRECT_TEST = ROOT / (
    "python/Program-System/System-Testing/Testing-Cpu/"
    "Testing-Cpu.Dependency.Utility.ResidualFamily-Hardware.py"
)
EVIDENCE = ROOT / "validation/v2-utility-residual-idpool-queue-time-results.json"
MEMBERS = ("IDPool", "OverrideableQueue", "OverrideableQueue_1", "TimeAsync")


def sha256(path: Path) -> str:
    """Hash one exact evidence input."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_direct() -> dict[str, Any]:
    """Run the focused direct test without hiding its exit status."""

    result = subprocess.run(
        [sys.executable, str(DIRECT_TEST), "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = result.stdout + result.stderr
    return {
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "returncode": result.returncode,
        "output_tail": output[-2000:],
        "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
    }


def standalone_backend(module: Any, member: str, work: Path) -> dict[str, Any]:
    """Export one exact-name module and run standalone Verilator/Yosys gates."""

    rtl = module.build_verilog({"module": member}, {})
    if f"module {member}(" not in rtl:
        raise AssertionError(f"{member}: build_verilog did not preserve its top name")
    target = work / f"same-name-{member}.sv"
    target.write_text(rtl, encoding="utf-8", newline="\n")
    linux = wsl_path(target)
    verilator = run_wsl([
        "verilator", "--lint-only", "-Wno-fatal", "--top-module", member, linux,
    ])
    yosys = run_wsl([
        "yosys", "-Q", "-p",
        f"read_verilog -sv {linux}; hierarchy -top {member}; proc; check",
    ])
    return {
        "rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest(),
        "rtl_bytes": len(rtl.encode()),
        "verilator": verilator,
        "yosys": yosys,
    }


def formal_summary(item: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Reduce FamilyRail output to explicit strict-gate facts."""

    proof = result.get("yosys_equiv") or {}
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
        "method": result["method"],
        "abi_exact": item["abi_exact"],
        "deterministic_export": item["deterministic"],
        "reference_view_trusted": item["view_trusted"],
        "target_verilator": result["verilator"]["status"],
        "locked_reference_verilator": result["locked_verilator"]["status"],
        "formal_status": "PASS" if formal_pass else "PENDING",
        "formal_tool_status": proof.get("status"),
        "formal_success_marker": proof.get("formal_success_marker"),
        "equiv_cells": proof.get("equiv_cells"),
        "proven_cells": proof.get("proven_cells"),
        "unproven_cells": proof.get("unproven_cells"),
        "locked_reference": f"validation/reference-sv/{item['name']}.sv",
        "locked_reference_sha256": item["locked_sha256"],
    }


def main() -> int:
    """Run direct, export, backend, and complete strict formal gates."""

    py_compile.compile(str(BUILD), doraise=True)
    py_compile.compile(str(DIRECT_TEST), doraise=True)
    py_compile.compile(str(Path(__file__)), doraise=True)
    direct = run_direct()

    rail = FamilyRail(BUILD, "UtilityResidualIdPoolQueueTime", EVIDENCE)
    shutil.rmtree(rail.work, ignore_errors=True)
    rail.work.mkdir(parents=True)
    module = load_module("v2_utility_residual_idpool_queue_time", BUILD)
    backend = {member: standalone_backend(module, member, rail.work) for member in MEMBERS}
    items = [rail.prepare(module, member) for member in MEMBERS]
    results = [rail.prove(item) for item in items]
    formal = {
        item["name"]: formal_summary(item, result)
        for item, result in zip(items, results)
    }
    for member in MEMBERS:
        formal[member]["same_name_verilog"] = backend[member]
    controls = rail.negative_control(items)
    strict_members = [
        member for member in MEMBERS if formal[member]["formal_status"] == "PASS"
    ]
    pending_members = [member for member in MEMBERS if member not in strict_members]
    failures = [
        f"{member}:strict_formal"
        for member in MEMBERS
        if formal[member]["formal_status"] != "PASS"
    ]
    failures += [
        f"{member}:standalone_backend"
        for member in MEMBERS
        if backend[member]["verilator"]["status"] != "PASS"
        or backend[member]["yosys"]["status"] != "PASS"
    ]
    if direct["status"] != "PASS":
        failures.append("direct_test")
    if controls["status"] != "PASS":
        failures.append("negative_control")
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_UTILITY_RESIDUAL_IDPOOL_QUEUE_TIME",
        "build": BUILD.relative_to(ROOT).as_posix(),
        "direct_test_path": DIRECT_TEST.relative_to(ROOT).as_posix(),
        "members": list(MEMBERS),
        "py_compile": "PASS",
        "direct_test": direct,
        "variants": formal,
        "negative_control": controls,
        "strict_formal_members": strict_members,
        "strict_pending_members": pending_members,
        # The aggregate catalog still contains other pending members; this
        # focused proof therefore does not increment the global 39/118 rail.
        "strict_equivalence_count_delta": 0,
        "aggregate_status": "FOCUSED_STRICT_MEMBERS_PASS" if not failures else "STRICT_PENDING",
        "acceptance_eligible": False,
        "failures": failures,
        "unclosed": [
            "ResidualFamily members outside this focused set remain pending;",
            "parent closure, license review, UHSC review, and user approval remain open.",
        ],
        "sources": {
            "build_sha256": sha256(BUILD),
            "direct_test_sha256": sha256(DIRECT_TEST),
            "validator_sha256": sha256(Path(__file__)),
        },
    }
    EVIDENCE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({
        "status": payload["aggregate_status"],
        "direct": direct["status"],
        "strict_formal_members": strict_members,
        "pending": pending_members,
        "failures": failures,
    }, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
