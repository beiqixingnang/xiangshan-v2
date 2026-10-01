"""Focused non-counting rail for the V2 DCache WritebackEntry leaf.

The family keeps six neighboring members at ``CONTRACT_ONLY`` while this
script runs the full static, locked-reference lint, sequential formal, and
two-sided negative-control gates for the one source-backed leaf implemented in
the current wave.  It writes a separate receipt and never edits the family or
central strict-progress evidence.
"""

from __future__ import annotations

import hashlib
import json
import py_compile
import subprocess
import sys
from pathlib import Path
from typing import Any

from v2_strict_family_rail import FamilyRail, ROOT, load_module, pyright_check


BUILD = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/"
    "Cpu-Memory-Memory.Dcache.MissQueue.Family-Hardware.py"
)
DIRECT = ROOT / (
    "python/Program-System/System-Testing/Testing-Cpu/"
    "Testing-Cpu-Memory.Dcache.MissQueue.Family-Hardware.py"
)
SCALA = ROOT / "upstream/src/main/scala/xiangshan/cache/dcache/mainpipe/WritebackQueue.scala"
LOCKED = ROOT / "validation/reference-sv/WritebackEntry.sv"
EVIDENCE = ROOT / "validation/v2-dcache-miss-writebackentry-focused-results.json"

CONTRACT_ONLY = (
    "CMOUnit",
    "MissEntry",
    "MissReadyGen",
    "ProbeEntry",
    "TreeArbiter",
    "WritebackEntry_15",
)


def source_record(path: Path) -> dict[str, Any]:
    """Return a stable identity for one input source."""

    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def run_direct() -> dict[str, Any]:
    """Run the registered family direct test as a prerequisite."""

    result = subprocess.run(
        [sys.executable, "-B", str(DIRECT.relative_to(ROOT))],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "command": [sys.executable, "-B", DIRECT.relative_to(ROOT).as_posix()],
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "returncode": result.returncode,
        "output_tail": (result.stdout + result.stderr)[-1800:],
    }


def main() -> int:
    """Run the WritebackEntry-only gates and write a non-counting receipt."""

    py_compile.compile(str(BUILD), doraise=True)
    py_compile.compile(str(DIRECT), doraise=True)
    direct = run_direct()
    module = load_module("dcache_miss_writebackentry_focused", BUILD)
    pyright = pyright_check(BUILD)
    runner = FamilyRail(
        BUILD,
        "Build-Cpu.Memory.Dcache.MissQueue.Family.WritebackEntry",
        EVIDENCE,
        scala_path=SCALA,
    )
    runner.work.mkdir(parents=True, exist_ok=True)
    item = runner.prepare(module, "WritebackEntry")
    static_failures = runner.cheap_static_failures(item)
    if pyright.get("status") != "PASS":
        static_failures.append("Pyright failed")
    lint: dict[str, Any] = {"status": "NOT_RUN"}
    locked_lint: dict[str, Any] = {"status": "NOT_RUN"}
    if not static_failures:
        lint, locked_lint = runner.lint_gate(item)
        if lint.get("status") != "PASS":
            static_failures.append("DUT miter Verilator lint failed")
        if locked_lint.get("status") != "PASS":
            static_failures.append("locked reference Verilator lint failed")
    item["static_failures"] = static_failures
    item["static_blocked"] = bool(static_failures) or direct["status"] != "PASS"
    formal: dict[str, Any] = runner.prove(item)
    negative = (
        runner.negative_control([item])
        if formal.get("yosys_equiv", {}).get("status") == "PASS"
        else {"status": "NOT_RUN", "cases": {}, "reason": "formal gate failed"}
    )
    formal_pass = runner.formal_result_pass(formal, item)
    status = "PASS_BOUNDED_PARTIAL_FORMAL"
    if formal_pass and negative.get("status") == "PASS":
        status = "COMPLETE_EQUIVALENCE_MEMBER_NONCOUNTING"
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_DCACHE_MISS_WRITEBACKENTRY_FOCUSED",
        "build_id": "Build-Cpu.Memory.Dcache.MissQueue.Family",
        "member": "WritebackEntry",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "strict_complete_build_count_delta": 0,
        "acceptance_eligible": False,
        "contract_only_members": list(CONTRACT_ONLY),
        "sources": {
            "python_build": source_record(BUILD),
            "direct_test": source_record(DIRECT),
            "locked_writeback_entry": source_record(LOCKED),
            "scala": source_record(SCALA),
            "validator": source_record(Path(__file__).resolve()),
            "strict_family_rail": source_record(ROOT / "validation/v2_strict_family_rail.py"),
        },
        "checks": {
            "py_compile": "PASS",
            "pyright": pyright,
            "direct_test": direct,
            "abi_exact": item.get("abi_exact"),
            "deterministic_export": item.get("deterministic"),
            "reference_view_trusted": item.get("view_trusted"),
            "dut_verilator": lint,
            "locked_verilator": locked_lint,
            "formal": formal,
            "formal_pass_contract": formal_pass,
            "two_sided_negative_control": negative,
        },
        "status": status,
        "unclosed": [
            "Six neighboring MissQueue members remain CONTRACT_ONLY.",
            "Family aggregate, parent DCache closure, reset-entry review, license review, and user approval remain pending.",
        ],
    }
    EVIDENCE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "status": status,
                "formal_pass": formal_pass,
                "negative_control": negative.get("status"),
                "strict_complete_build_count_delta": 0,
                "evidence": EVIDENCE.relative_to(ROOT).as_posix(),
            },
            ensure_ascii=False,
        )
    )
    return 0 if status == "COMPLETE_EQUIVALENCE_MEMBER_NONCOUNTING" else 1


if __name__ == "__main__":
    raise SystemExit(main())
