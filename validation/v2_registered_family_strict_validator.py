"""Prove all members of an explicitly registered auxiliary candidate family."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from v2_strict_family_rail import FamilyRail, ROOT, enumerate_members, load_module


def source_record(path: Path) -> dict[str, Any]:
    return {"path": path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, help="Exact registered Build ID")
    parser.add_argument("--scala", type=Path, action="append", required=True)
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args()
    if Path(args.evidence).name != args.evidence or not args.evidence.endswith("-strict-evidence.json"):
        raise ValueError("a complete Build receipt needs its own strict evidence filename")
    manifest = json.loads((ROOT / "UHSC-Naming-Manifest.json").read_text(encoding="utf-8"))
    records = manifest["path_rename_transaction"]["renames"] + manifest.get("candidate_additions", [])
    builds = [row for row in records if row["kind"] == "build-script" and row["build_id"] == args.build]
    name = "Testing-Cpu-" + args.build.removeprefix("Build-Cpu.") + "-Hardware.py"
    tests = [row for row in records if row["kind"] == "testing-script" and Path(row["new_path"]).name == name]
    if len(builds) != 1 or len(tests) != 1:
        raise ValueError("missing or duplicate exact Build/direct registration")
    build = ROOT / builds[0]["new_path"]
    direct_path = ROOT / tests[0]["new_path"]
    source_paths = [(ROOT / path).resolve() for path in args.scala]
    if any(not path.is_relative_to(ROOT) or not path.is_file() for path in source_paths):
        raise ValueError("all source bindings must be vendored existing files")
    module = load_module("v2_registered_family", build)
    members = enumerate_members(module, build)
    if getattr(module, "CONTRACT_ONLY_MEMBERS", ()):
        raise ValueError("contract-only members block full family proof")
    initial = {"build": source_record(build), "test": source_record(direct_path)}
    command = [sys.executable, "-B", "validation/v2_direct_test_runner.py", "--test", tests[0]["new_path"]]
    direct = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", check=False)
    if direct.returncode:
        print((direct.stdout + direct.stderr)[-2400:])
        return 1
    evidence = ROOT / "validation" / args.evidence
    runner = FamilyRail(build, args.build, evidence, scala_path=source_paths[0])
    payload = runner.run()
    payload["validator"] = Path(__file__).resolve().relative_to(ROOT).as_posix()
    payload["sources"]["validator"] = source_record(Path(__file__).resolve())
    payload["sources"]["validator_dependencies"] = {
        "strict_family_rail": source_record(ROOT / "validation/v2_strict_family_rail.py"),
        "direct_test": source_record(direct_path),
        "direct_runner": source_record(ROOT / "validation/v2_direct_test_runner.py"),
    }
    payload["sources"]["declared_scala_sources"] = {
        path.relative_to(ROOT).as_posix(): {"vendored": True, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in source_paths
    }
    payload["checks"]["direct_test"] = {
        "status": "PASS", "returncode": direct.returncode, "command": command,
        "output_tail": (direct.stdout + direct.stderr)[-2400:],
    }
    if payload["scope"]["sequential_variants"] == 0:
        payload["checks"]["reset_entry"] = {"status": "PASS", "applicable": False,
                                            "state_bits": 0, "reason": "All public members are combinational."}
    stable = initial == {"build": source_record(build), "test": source_record(direct_path)}
    payload["checks"]["sources_stable_during_run"] = {"status": "PASS" if stable else "FAIL"}
    if not stable:
        payload["status"] = "STRICT_PENDING"
        payload["failures"].append("Build or direct test changed during the proof")
        payload["unclosed"].append("Re-export and re-audit stable sources")
        payload["strict_complete_eligible"] = False
        payload["strict_complete_count_delta"] = 0
    payload["acceptance_eligible"] = False
    evidence.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"build_id": args.build, "status": payload["status"], "members": len(members),
                      "proven": payload["checks"]["catalog_coverage"]["proven"],
                      "negative_control": payload["checks"]["negative_control"]["status"],
                      "failures": payload["failures"]}), flush=True)
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
