"""Audit selected implemented members without granting complete Build credit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import unittest
from typing import Any

from v2_strict_family_rail import (
    FamilyRail, ROOT, SOURCE_COMMIT, enumerate_members, load_module, miter_text, run_wsl, wsl_path,
    tool_versions_complete,
)


def source_record(path: Path) -> dict[str, Any]:
    return {"path": path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size}


class OutputConeRail(FamilyRail):
    """Prove every complete output cone with all inputs unconstrained."""

    @staticmethod
    def formal_result_pass(result: dict[str, Any], item: dict[str, Any]) -> bool:
        proof = result.get("sat_miter") or {}
        if proof.get("proof_decomposition") != "all_public_output_cones_no_input_assumptions":
            return FamilyRail.formal_result_pass(result, item)
        rows = proof.get("partitions", [])
        if (item.get("sequential") or item.get("abi_exact") is not True
                or item.get("deterministic") is not True or item.get("view_trusted") is not True
                or not tool_versions_complete(item.get("tool_versions", {}))
                or result.get("verilator", {}).get("status") != "PASS"
                or result.get("locked_verilator", {}).get("status") != "PASS"
                or proof.get("status") != "PASS" or proof.get("returncode") != 0
                or proof.get("formal_success_marker") is not True or proof.get("unconstrained") is not True
                or len(rows) != len(item["outputs"])
                or {row["output"]: row["width"] for row in rows} != item["outputs"]):
            return False
        for row in rows:
            raw = row.get("proof", {})
            command = " ".join(str(value) for value in raw.get("command", []))
            if (row.get("status") != "PASS" or type(raw.get("returncode")) is not int
                    or raw.get("returncode") != 0 or raw.get("status") != "PASS"
                    or raw.get("timed_out") is True or raw.get("sat_success_marker") is not True
                    or raw.get("unconstrained_marker") is not True or "sat -prove mismatch 0" not in command):
                return False
        return True

    def prove(self, item: dict[str, Any]) -> dict[str, Any]:
        if item.get("sequential") or item.get("static_blocked"):
            return super().prove(item)
        lint, locked_lint = self.lint_gate(item)
        if lint.get("status") != "PASS" or locked_lint.get("status") != "PASS":
            item["static_blocked"] = True
            item["verilator"], item["locked_verilator"] = lint, locked_lint
            return super().prove(item)
        partitions = []
        for output, width in item["outputs"].items():
            path = self.work / f"{item['name']}_CONE_{output}.sv"
            path.write_text(miter_text(item["name"], item["inputs"], {output: width}),
                            encoding="utf-8", newline="\n")
            files = " ".join(shlex.quote(value) for value in (
                item["wsl"]["target"], item["wsl"]["reference"], wsl_path(path)))
            script = (f"read_verilog -sv {files}; prep -top {item['name']}_MITER; "
                      "flatten; opt; sat -prove mismatch 0")
            proof = run_wsl(["yosys", "-Q", "-p", script], timeout=60)
            passed = (proof.get("returncode") == 0 and proof.get("status") == "PASS"
                      and proof.get("sat_success_marker") is True and proof.get("unconstrained_marker") is True)
            partitions.append({"output": output, "width": width, "status": "PASS" if passed else "PENDING",
                               "miter": source_record(path) if path.is_relative_to(ROOT) else {
                                   "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}, "proof": proof})
            print(json.dumps({"member": item["name"], "output": output, "status": partitions[-1]["status"]}), flush=True)
            if not passed:
                break
        complete = ({row["output"] for row in partitions} == set(item["outputs"])
                    and all(row["status"] == "PASS" for row in partitions))
        counts = [row["proof"].get("sat_counts_full") or [0, 0] for row in partitions]
        sat = {"status": "PASS" if complete else "PENDING", "returncode": 0 if complete else None,
               "formal_success_marker": complete, "unconstrained": complete,
               "sat_variables": sum(count[0] for count in counts),
               "sat_clauses": sum(count[1] for count in counts),
               "proof_decomposition": "all_public_output_cones_no_input_assumptions",
               "outputs_expected": item["outputs"], "partitions": partitions,
               "output_sha256": hashlib.sha256(json.dumps(partitions, sort_keys=True).encode()).hexdigest()}
        return {"method": "sat_miter", "verilator": lint, "locked_verilator": locked_lint, "sat_miter": sat}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, help="Explicit auxiliary Build ID")
    parser.add_argument("--member", action="append", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--scala", type=Path, action="append", default=[])
    parser.add_argument("--test-case", action="append", default=[],
                        help="Explicit direct unittest case for a partial member diagnostic")
    parser.add_argument("--partition-outputs", action="store_true")
    args = parser.parse_args()
    if Path(args.evidence).name != args.evidence or "strict-evidence" in args.evidence:
        raise ValueError("member diagnostics require a distinct non-counting evidence filename")
    naming = json.loads((ROOT / "UHSC-Naming-Manifest.json").read_text(encoding="utf-8"))
    records = naming["path_rename_transaction"]["renames"] + naming.get("candidate_additions", [])
    builds = [row for row in records if row["kind"] == "build-script" and row["build_id"] == args.build]
    if len(builds) != 1:
        raise ValueError("missing or duplicate explicit Build identity")
    build = ROOT / builds[0]["new_path"]
    test_name = "Testing-Cpu-" + args.build.removeprefix("Build-Cpu.") + "-Hardware.py"
    tests = [row for row in records if row["kind"] == "testing-script" and Path(row["new_path"]).name == test_name]
    if len(tests) != 1:
        raise ValueError("missing or duplicate exact direct test")
    direct_path = ROOT / tests[0]["new_path"]
    build_before = source_record(build)
    direct_before = source_record(direct_path)
    if args.test_case:
        direct_module = load_module("v2_member_direct_subset", direct_path)
        suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(case, direct_module)
                                   for case in args.test_case)
        if suite.countTestCases() != len(args.test_case):
            raise ValueError("selected direct cases are absent or ambiguous")
        result = unittest.TextTestRunner(verbosity=1).run(suite)
        direct_record = {"status": "PASS" if result.wasSuccessful() and not result.skipped else "FAIL",
                         "full_subject_suite": False, "selected_cases": args.test_case,
                         "tests_run": result.testsRun}
    else:
        command = [sys.executable, "-B", "validation/v2_direct_test_runner.py", "--test", tests[0]["new_path"]]
        direct = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", check=False)
        direct_record = {"command": command, "returncode": direct.returncode,
                         "status": "PASS" if direct.returncode == 0 else "FAIL", "full_subject_suite": True,
                         "output_tail": (direct.stdout + direct.stderr)[-2400:]}
    if direct_record["status"] != "PASS":
        print(json.dumps(direct_record))
        return 1
    module = load_module("v2_member_audit", build)
    catalog = enumerate_members(module, build)
    members = list(dict.fromkeys(args.member))
    if not set(members).issubset(catalog) or set(members) & set(getattr(module, "CONTRACT_ONLY_MEMBERS", ())):
        raise ValueError("select only implemented members of the declared catalog")
    sources = [(ROOT / path).resolve() for path in args.scala]
    if any(not path.is_relative_to(ROOT) or not path.is_file() for path in sources):
        raise ValueError("source bindings must be vendored existing files")
    evidence = ROOT / "validation" / args.evidence
    rail_type = OutputConeRail if args.partition_outputs else FamilyRail
    runner = rail_type(build, args.build + ".MemberDiagnostic", evidence,
                       scala_path=sources[0] if sources else None)
    runner.work.mkdir(parents=True, exist_ok=True)
    results = []
    items = []
    for name in members:
        item = runner.prepare(module, name)
        failures = runner.cheap_static_failures(item)
        item["static_blocked"] = bool(failures)
        formal = runner.cached_formal(item["cache_key"], item) if not failures else None
        if formal is None:
            formal = runner.prove(item)
        proof = formal.get("yosys_equiv") or formal.get("sat_miter") or {}
        passed = not failures and runner.formal_result_pass(formal, item)
        if passed:
            runner.remember_formal(item["cache_key"], formal, proof, item)
            items.append(item)
        results.append({"member": name, "status": "PASS" if passed else "PENDING",
                        "prepared": runner.path_value(item), "static_failures": failures, "formal": formal})
        print(json.dumps({"member": name, "status": results[-1]["status"],
                          "cells": proof.get("equiv_cells"), "unproven": proof.get("unproven_cells")}), flush=True)
    controls = runner.negative_control(items) if len(items) == len(members) else {
        "status": "NOT_RUN", "reason": "member proof failed"}
    stable_sources = build_before == source_record(build) and direct_before == source_record(direct_path)
    passed = len(items) == len(members) and runner.controls_result_pass(controls, items) and stable_sources
    payload = {
        "kind": "V2_IMPLEMENTED_MEMBER_FORMAL_DIAGNOSTIC", "source_commit": SOURCE_COMMIT,
        "build_id": args.build, "members": members, "family_members": catalog,
        "status": "PASS_MEMBER_PROOFS_NON_COUNTING" if passed else "STRICT_PENDING",
        "strict_complete_build_count_delta": 0, "acceptance_eligible": False,
        "sources": {"python_build": source_record(build), "direct_test": source_record(direct_path),
                    "direct_runner": source_record(ROOT / "validation/v2_direct_test_runner.py"),
                    "validator": source_record(Path(__file__).resolve()),
                    "rail": source_record(ROOT / "validation/v2_strict_family_rail.py"),
                    "scala": [source_record(path) for path in sources]},
        "direct": direct_record, "sources_stable_during_run": stable_sources,
        "results": results, "negative_control": controls,
        "unclosed": ["Complete family, reset/startup correspondence, parent/top closure and acceptance remain separate gates."],
    }
    evidence.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "passed": len(items), "total": len(members),
                      "negative_control": controls["status"]}), flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
