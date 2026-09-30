"""Complete strict rail and source audit for the two prefetch metadata members."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from v2_strict_family_rail import FamilyRail, ROOT


BUILD_ID = "Build-Cpu.Memory.Prefetch.Metadata.Family"
BUILD = (ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory"
         / "Cpu-Memory-Memory.Prefetch.Metadata.Family-Hardware.py")
DIRECT = (ROOT / "python/Program-System/System-Testing/Testing-Cpu"
          / "Testing-Cpu-Memory.Prefetch.Metadata.Family-Hardware.py")
EVIDENCE = ROOT / "validation/v2-build-cpu-memory-prefetch-metadata-family-strict-evidence.json"
SCALA_SOURCES = (
    ROOT / "upstream/src/main/scala/xiangshan/mem/prefetch/L1StreamPrefetcher.scala",
    ROOT / "upstream/src/main/scala/xiangshan/mem/prefetch/L1StridePrefetcher.scala",
)
RAIL = ROOT / "validation/v2_strict_family_rail.py"


def source_record(path: Path) -> dict[str, Any]:
    """Record an exact vendored source without modifying it."""

    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def run_direct() -> dict[str, Any]:
    """Reject direct-test failures before starting formal."""

    direct = subprocess.run(
        [sys.executable, "-B", str(DIRECT)], cwd=ROOT, capture_output=True,
        text=True, encoding="utf-8", errors="replace", check=False,
    )
    direct_pass = direct.returncode == 0 and "Ran 4 tests" in direct.stderr
    return {
        "status": "PASS" if direct_pass else "FAIL",
        "returncode": direct.returncode,
        "command": [sys.executable, "-B", DIRECT.relative_to(ROOT).as_posix()],
        "output_tail": (direct.stdout + direct.stderr)[-1500:],
    }


def main() -> int:
    """Run both complete member proofs and independently audit their sources."""

    for path in (BUILD, DIRECT, *SCALA_SOURCES, RAIL):
        if not path.is_file():
            raise FileNotFoundError(path)
    direct = run_direct()
    if direct["status"] != "PASS":
        raise RuntimeError("direct test failed; strict formal was not started")
    payload = FamilyRail(BUILD, BUILD_ID, EVIDENCE, SCALA_SOURCES[0]).run()
    if payload["scope"]["public_variants"] != ["StreamBitVectorArray", "StrideMetaArray"]:
        raise AssertionError("prefetch metadata member catalog changed")
    payload["checks"]["direct_test"] = direct

    payload["validator"] = Path(__file__).resolve().relative_to(ROOT).as_posix()
    payload["sources"]["validator"] = source_record(Path(__file__).resolve())
    payload["sources"]["validator_dependencies"] = {
        "strict_family_rail": source_record(RAIL),
        "direct_test": source_record(DIRECT),
    }
    payload["sources"]["declared_scala_sources"] = {
        path.relative_to(ROOT).as_posix(): {
            "vendored": True,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in SCALA_SOURCES
    }
    payload["acceptance_eligible"] = False
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    print(json.dumps({
        "build_id": BUILD_ID,
        "status": payload["status"],
        "strict_complete_count_delta": payload["strict_complete_count_delta"],
        "proven_members": payload["checks"]["catalog_coverage"]["proven"],
        "direct": payload["checks"]["direct_test"]["status"],
        "failures": payload["failures"],
    }, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
