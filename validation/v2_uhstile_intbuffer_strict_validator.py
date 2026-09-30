"""Run strict equivalence for the localized UHSTile IntBuffer Build."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from v2_strict_family_rail import FamilyRail, ROOT


BUILD_ID = "Build-Cpu.Top.UHSTile.IntBuffer.Family"
BUILD = (ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core"
         / "Cpu-Core-Top.UHSTile.IntBuffer.Family-Hardware.py")
DIRECT = (ROOT / "python/Program-System/System-Testing/Testing-Cpu"
          / "Testing-Cpu-Top.UHSTile.IntBuffer.Family-Hardware.py")
EVIDENCE = ROOT / "validation/v2-build-cpu-top-uhstile-intbuffer-family-strict-evidence.json"
SCALA = ROOT / "upstream/utility/src/main/scala/utility/IntBuffer.scala"
RAIL = ROOT / "validation/v2_strict_family_rail.py"


def source_record(path: Path) -> dict[str, Any]:
    """Record an exact source path, digest, and byte count."""

    raw = path.read_bytes()
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def run_direct() -> dict[str, Any]:
    """Run the direct test before spending time on formal proofs."""

    result = subprocess.run(
        [sys.executable, "-B", str(DIRECT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = result.stdout + result.stderr
    passed = result.returncode == 0 and "Ran 5 tests" in output
    return {
        "status": "PASS" if passed else "FAIL",
        "returncode": result.returncode,
        "command": [sys.executable, "-B", DIRECT.relative_to(ROOT).as_posix()],
        "output_tail": output[-1800:],
    }


def main() -> int:
    """Prove all three locked members serially and bind this validator hash."""

    for path in (BUILD, DIRECT, SCALA, RAIL):
        if not path.is_file():
            raise FileNotFoundError(path)

    direct = run_direct()
    if direct["status"] != "PASS":
        raise RuntimeError("direct test failed; strict formal was not started")

    payload = FamilyRail(BUILD, BUILD_ID, EVIDENCE, SCALA).run()
    expected_members = ["IntBuffer", "IntBuffer_1", "IntBuffer_2"]
    if payload.get("scope", {}).get("public_variants") != expected_members:
        raise AssertionError("strict rail did not prove all three IntBuffer variants")

    payload["validator"] = Path(__file__).resolve().relative_to(ROOT).as_posix()
    payload.setdefault("sources", {})["validator"] = source_record(Path(__file__).resolve())
    payload["sources"]["validator_dependencies"] = {
        "strict_family_rail": source_record(RAIL),
        "direct_test": source_record(DIRECT),
    }
    payload["sources"]["scala"] = source_record(SCALA)
    payload["checks"]["direct_test"] = direct
    payload["acceptance_eligible"] = False
    payload.pop("proof_origin", None)
    payload.pop("origin_sha256", None)
    EVIDENCE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    summary = {
        "build_id": BUILD_ID,
        "status": payload["status"],
        "strict_complete_count_delta": payload["strict_complete_count_delta"],
        "proven_members": payload["checks"]["catalog_coverage"]["proven"],
        "direct": direct["status"],
        "validator_sha256": payload["sources"]["validator"]["sha256"],
        "failures": payload["failures"],
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
