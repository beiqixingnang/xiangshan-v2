"""Prove the complete Rocket TL child catalog with full-cone state partitions.

This is a complete Build producer. The focused diagnostic remains non-counting;
both use the same partition policy and all the shared strict-family gates.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import v2_strict_family_rail as rail
from v2_catalog_family_strict_validator import (
    build_id_for, direct_path_for, resolve_build, source_record,
)
from v2_queue_state_correspondence_validator import QueueStateRail


def main() -> int:
    build = resolve_build("Rocket.TLChildren.Family")
    direct_path = direct_path_for(build)
    evidence = rail.ROOT / "validation/v2-build-cpu-dependency-rocket-tlchildren-family-strict-evidence.json"
    provenance = json.loads((rail.ROOT / "validation/v2-build-provenance-map.json").read_text(encoding="utf-8"))
    declared = provenance["entries"][build.relative_to(rail.ROOT).as_posix()]["SOURCE_SCALA_PATHS"]
    scala_paths = [rail.ROOT / relative for relative in declared]
    if not scala_paths or any(not path.is_file() for path in scala_paths):
        raise ValueError("the complete Rocket source provenance must be present")
    command = [sys.executable, "-B", "validation/v2_direct_test_runner.py", "--test",
               direct_path.relative_to(rail.ROOT).as_posix()]
    direct = subprocess.run(command, cwd=rail.ROOT, capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    if direct.returncode != 0:
        print((direct.stdout + direct.stderr)[-2400:])
        return 1
    runner = QueueStateRail(build, build_id_for(build), evidence, scala_path=scala_paths[0])
    payload = runner.run()
    payload["validator"] = Path(__file__).resolve().relative_to(rail.ROOT).as_posix()
    payload["sources"]["validator"] = source_record(Path(__file__).resolve())
    payload["sources"]["validator_dependencies"] = {
        "strict_family_rail": source_record(rail.ROOT / "validation/v2_strict_family_rail.py"),
        "state_partition_rail": source_record(rail.ROOT / "validation/v2_queue_state_correspondence_validator.py"),
        "catalog_resolver": source_record(rail.ROOT / "validation/v2_catalog_family_strict_validator.py"),
        "direct_test": source_record(direct_path),
        "direct_runner": source_record(rail.ROOT / "validation/v2_direct_test_runner.py"),
    }
    payload["sources"]["declared_scala_sources"] = {
        path.relative_to(rail.ROOT).as_posix(): {
            "vendored": True, "sha256": rail.sha256_file(path)} for path in scala_paths
    }
    payload["checks"]["direct_test"] = {
        "status": "PASS", "returncode": direct.returncode, "command": command,
        "output_tail": (direct.stdout + direct.stderr)[-2400:],
    }
    payload["acceptance_eligible"] = False
    evidence.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "build_id": runner.build_id,
                      "proven": payload["checks"]["catalog_coverage"]["proven"],
                      "members": payload["scope"]["variant_count"],
                      "strict_complete_count_delta": payload["strict_complete_count_delta"],
                      "negative_control": payload["checks"]["negative_control"]["status"],
                      "failures": payload["failures"]}), flush=True)
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
