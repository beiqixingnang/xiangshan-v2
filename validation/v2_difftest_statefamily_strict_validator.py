"""Strict complete-equivalence proof for the Difftest state family Build.

The Build lists 21 locked difftest state views in its own tables and exports
whichever one a configuration names, so only proving all 21 completes the Build
file.  Every gate lives in the shared family rail; this module supplies the
targets and prints the verdict.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from v2_strict_family_rail import ROOT, FamilyRail, REF_DIR  # noqa: E402


BUILD = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Build-Cpu.Dependency.Difftest.StateFamily-Hardware.py"
)
EVIDENCE = ROOT / "validation/v2-difftest-statefamily-strict-evidence.json"
SCALA_CANDIDATES = tuple(
    ROOT / f"upstream/difftest/src/main/scala/difftest/{name}.scala"
    for name in ("ArchEvent", "CSRState", "InstrCommit", "TrapEvent")
)


def scala_source() -> Path | None:
    """Return the first declared Difftest Scala source this lock vendors."""

    for path in SCALA_CANDIDATES:
        if path.is_file():
            return path
    return None


def main() -> int:
    """Prove all 21 Difftest state views and report the verdict."""

    locked = sorted(p.stem for p in REF_DIR.glob("DiffExt*.sv"))
    print(json.dumps({"locked_diffext_views": len(locked)}, ensure_ascii=False))
    payload = FamilyRail(BUILD, "Build-Cpu.Dependency.Difftest.StateFamily",
                         EVIDENCE, scala_source()).run()
    scope = payload["scope"]
    print(json.dumps({
        "status": payload["status"],
        "strict_complete_eligible": payload["strict_complete_eligible"],
        "strict_complete_count_delta": payload["strict_complete_count_delta"],
        "entries": scope["variant_count"],
        "combinational": scope["combinational_variants"],
        "sequential": scope["sequential_variants"],
        "aggregate_input_bits": scope["aggregate_input_bits"],
        "proven": payload["checks"]["catalog_coverage"]["proven"],
        "negative_control": payload["checks"]["negative_control"]["status"],
        "failures": payload["failures"][:10],
    }, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
