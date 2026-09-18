"""Smoke tests for the bounded ROB/rename/trace family evidence."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Rob.Rename.Trace-Family-Hardware.py"
MANIFEST = ROOT / "validation/v2-backend-rob-rename-trace-family-manifest.json"
EVIDENCE = ROOT / "validation/v2-backend-rob-rename-trace-family-results.json"


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    spec = importlib.util.spec_from_file_location("rob_rename_trace_test_build", BUILD)
    if spec is None or spec.loader is None:
        raise RuntimeError(BUILD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    names = tuple(item["module"] for item in manifest["modules"])
    assert names == tuple(module.COVERED_MODULES)
    assert evidence["status"] == "VALIDATOR_PASS_BOUNDED"
    assert evidence["gates"]["ACCEPTED"] == "NOT_ALLOWED"
    assert evidence["gates"]["REFERENCE_DIFFERENTIAL"] == "PENDING_LOCKED_BEHAVIORAL_TRACE"
    for name in names:
        assert evidence["port_surface"][name]["exact"] is True
        assert evidence["exports"][name]["deterministic"] is True
    print(f"PASS bounded ROB/rename/trace smoke ({len(names)} modules)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
