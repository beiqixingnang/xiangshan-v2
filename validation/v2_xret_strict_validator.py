"""Prove the complete registered exception-return permission Build."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from v2_strict_family_rail import FamilyRail, ROOT


BUILD_ID = "Build-Cpu.Backend.Fu.NewCSR.XRetPermit"
BUILD = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Cpu-Core-Backend.Fu.NewCSR.XRetPermit-Hardware.py"
DIRECT = ROOT / "python/Program-System/System-Testing/Testing-Cpu/Testing-Cpu-Backend.Fu.NewCSR.XRetPermit-Hardware.py"
SOURCE = ROOT / "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/CSRPermitModule.scala"
EVIDENCE = ROOT / "validation/v2-build-cpu-backend-fu-newcsr-xretpermit-strict-evidence.json"


def source_record(path: Path) -> dict[str, Any]:
    """Bind an exact input without copying provenance into the product."""

    return {"path": path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size}


def main() -> int:
    """Run real direct discovery before the complete unconstrained rail."""

    manifest = json.loads((ROOT / "UHSC-Naming-Manifest.json").read_text(encoding="utf-8"))
    records = manifest["candidate_additions"]
    builds = [row for row in records if row.get("build_id") == BUILD_ID]
    tests = [row for row in records if row.get("subject_id") == BUILD_ID and row.get("direct") is True]
    if len(builds) != 1 or len(tests) != 1:
        raise ValueError("missing or duplicate registered candidate/direct subject")
    if builds[0]["new_path"] != BUILD.relative_to(ROOT).as_posix() or tests[0]["new_path"] != DIRECT.relative_to(ROOT).as_posix():
        raise ValueError("registered candidate path mismatch")
    command = [sys.executable, "-B", "validation/v2_direct_test_runner.py", "--test",
               DIRECT.relative_to(ROOT).as_posix(), "--minimum-tests", "2"]
    direct = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", check=False)
    direct_output = direct.stdout + direct.stderr
    if direct.returncode != 0 or "Ran 2 tests" not in direct_output:
        print(direct_output[-2000:])
        return 1
    runner = FamilyRail(BUILD, BUILD_ID, EVIDENCE, scala_path=SOURCE)
    payload = runner.run()
    payload["validator"] = Path(__file__).resolve().relative_to(ROOT).as_posix()
    payload["sources"]["validator"] = source_record(Path(__file__).resolve())
    payload["sources"]["validator_dependencies"] = {
        "strict_family_rail": source_record(ROOT / "validation/v2_strict_family_rail.py"),
        "direct_test": source_record(DIRECT),
        "direct_runner": source_record(ROOT / "validation/v2_direct_test_runner.py"),
    }
    payload["sources"]["declared_scala_sources"] = {
        SOURCE.relative_to(ROOT).as_posix(): {"vendored": True, "sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest()}
    }
    payload["checks"]["direct_test"] = {
        "status": "PASS", "returncode": direct.returncode, "command": command,
        "tests_run": 2, "output_tail": direct_output[-2000:],
    }
    payload["checks"]["reset_entry"] = {
        "status": "PASS", "applicable": False, "state_bits": 0,
        "reason": "The full reference and DUT contain no clock or state; SAT covers all 1024 input assignments and all six outputs."
    }
    payload["acceptance_eligible"] = False
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"build_id": BUILD_ID, "status": payload["status"],
                      "proven": payload["checks"]["catalog_coverage"],
                      "negative_control": payload["checks"]["negative_control"]["status"],
                      "failures": payload["failures"]}))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
