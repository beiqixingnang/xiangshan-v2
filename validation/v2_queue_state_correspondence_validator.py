"""Focused Queue state proofs using the unchanged strict-family gates.

This diagnostic deliberately cannot promote a partial family or increment the
Build numerator. Successful member receipts share the full family's checkpoint.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import v2_strict_family_rail as rail
from v2_catalog_family_strict_validator import (
    build_id_for, direct_path_for, resolve_build, source_record,
)


class QueueStateRail(rail.FamilyRail):
    """Prove independent Queue2 islands without constructing one huge SAT set."""

    def inductive_steps(self, name: str) -> str:
        if name == "TLXbar_8":
            commands: list[str] = []
            groups = [
                ["beatsLeft", "readys_mask", "state_0", "state_1"],
                ["beatsLeft_1", "readys_mask_1", "state_1_0", "state_1_1"],
                ["beatsLeft_2", "readys_mask_2", "state_2_0", "state_2_1"],
                ["beatsLeft_3", "readys_mask_3", "state_3_0", "state_3_1", "state_3_2"],
                ["beatsLeft_4", "readys_mask_4", "state_4_0", "state_4_1", "state_4_2"],
            ]
            for index, wires in enumerate(groups):
                selector = " ".join(f"w:{wire}" for wire in wires)
                commands += [f"select -set xbar{index} {selector} %x t:$equiv %i %ci*",
                             f"select -assert-any @xbar{index}",
                             f"equiv_induct -undef @xbar{index}"]
            commands += ["select -clear", "equiv_induct -undef"]
            return "; ".join(commands)
        if name != "TLBuffer_27":
            return super().inductive_steps(name)
        commands: list[str] = []
        for bank in range(4):
            for channel in "abcde":
                direction = "In" if channel in "bd" else "Out"
                island = f"node{direction}_{channel}_q" + (f"_{bank}" if bank else "")
                group = f"queue{bank}{channel}"
                # Expand the full driver cone, including sequential logic.
                # Selecting just the equiv cells would discard their drivers.
                commands += [f"select -set {group} w:{island}.* %x t:$equiv %i %ci*",
                             f"select -assert-any @{group}",
                             f"equiv_induct -undef @{group}"]
        # Any cell not reached by the partition selectors must still prove.
        # The caller always finishes with equiv_status -assert for the whole
        # design; no cutpoint is assumed, removed, or omitted from coverage.
        commands += ["select -clear", "equiv_induct -undef"]
        return "; ".join(commands)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True)
    parser.add_argument("--member", action="append", required=True)
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args()
    if Path(args.evidence).name != args.evidence or "strict-evidence" in args.evidence:
        raise ValueError("focused diagnostics need a distinct evidence filename")
    build = resolve_build(args.build)
    evidence = rail.ROOT / "validation" / args.evidence
    direct_path = direct_path_for(build)
    module = rail.load_module("queue_state_diagnostic", build)
    catalog = rail.enumerate_members(module, build)
    members = list(dict.fromkeys(args.member))
    if set(members) - set(catalog):
        raise ValueError("selected members must belong to the Build catalog")
    runner = QueueStateRail(build, build_id_for(build), evidence)
    runner.work.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    direct_command = [sys.executable, "-B", str(direct_path)]
    direct = subprocess.run(direct_command, cwd=rail.ROOT, capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    checks: dict[str, Any] = {
        "direct": {"command": direct_command, "returncode": direct.returncode,
                   "status": "PASS" if direct.returncode == 0 else "FAIL",
                   "output_tail": (direct.stdout + direct.stderr)[-2400:]},
        "pyright": rail.pyright_check(build),
    }
    rows: list[dict[str, Any]] = []
    passing_items: list[dict[str, Any]] = []
    if direct.returncode == 0 and checks["pyright"].get("status") == "PASS":
        for name in members:
            item = runner.prepare(module, name)
            failures = runner.cheap_static_failures(item)
            if not failures:
                lint, locked = runner.lint_gate(item)
                if lint.get("status") != "PASS" or locked.get("status") != "PASS":
                    failures.append("lint")
            item["static_blocked"] = bool(failures)
            result = (runner.cached_formal(item["cache_key"], item)
                      if not failures else None)
            cache_hit = result is not None
            if result is None:
                result = runner.prove(item)
            proof = result.get("yosys_equiv") or result.get("sat_miter") or {}
            passed = not failures and runner.formal_result_pass(result, item)
            runner.remember_formal(item["cache_key"], result, proof, item)
            row = {"member": name, "status": "PASS" if passed else "STRICT_PENDING",
                   "formal_cache_hit": cache_hit, "static_failures": failures,
                   "prepared": runner.path_value(item), "formal": result}
            rows.append(row)
            if passed:
                passing_items.append(item)
            print(json.dumps({"member": name, "status": row["status"],
                              "cells": proof.get("equiv_cells"),
                              "unproven": proof.get("unproven_cells"),
                              "cache_hit": cache_hit}), flush=True)
    controls = (runner.negative_control(passing_items)
                if len(passing_items) == len(members) else
                {"status": "NOT_RUN", "reason": "member gate failed"})
    passed = len(passing_items) == len(members) and runner.controls_result_pass(
        controls, passing_items)
    payload = {
        "schema_version": 1, "kind": "V2_QUEUE_STATE_FOCUSED_DIAGNOSTIC",
        "build_id": runner.build_id,
        "status": "PASS_MEMBER_PROOFS_NON_COUNTING" if passed else "STRICT_PENDING",
        "strict_complete_eligible": False, "strict_complete_count_delta": 0,
        "acceptance_eligible": False, "members": members, "family_members": catalog,
        "full_family_covered": set(members) == set(catalog),
        "sources": {"python_build": source_record(build),
                    "validator": source_record(Path(__file__).resolve()),
                    "rail": source_record(Path(rail.__file__).resolve()),
                    "direct_test": source_record(direct_path)},
        "checks": checks, "results": rows, "negative_control": controls,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "unclosed": ["Full Build catalog, parent closure, license and acceptance remain pending."],
    }
    evidence.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "passed": len(passing_items),
                      "total": len(members), "negative_control": controls["status"],
                      "elapsed_seconds": payload["elapsed_seconds"]}), flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
