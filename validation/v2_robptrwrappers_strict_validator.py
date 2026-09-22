"""Strict V2 ROB pointer-wrapper family proof.

The locked wrapper RTL uses Chisel's multiline block-local ``automatic logic``
declarations.  The frozen family rail intentionally handles only its original
one-line subset, so this dedicated entry point reuses the already audited
multiline view and delegates every ABI, formal, negative-control, and evidence
gate to the frozen rail.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import py_compile
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import v2_strict_family_rail as rail  # noqa: E402
from v2_build_provenance import source_paths_for_build  # noqa: E402
from v2_smallcontrol_strict_validator import _view  # noqa: E402


ROOT = rail.ROOT
BUILD = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Build-Cpu.Backend.Rob.PtrWrappers-Hardware.py"
)
EVIDENCE = ROOT / (
    "validation/v2-build-cpu-backend-rob-ptrwrappers-strict-evidence.json"
)
FROZEN_RAIL = ROOT / "validation/v2_strict_family_rail.py"
VIEW_PROVIDER = ROOT / "validation/v2_smallcontrol_strict_validator.py"


def sha256(path: Path) -> str:
    """Hash one repository file exactly."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_record(path: Path) -> dict[str, Any]:
    """Return a repository-relative, digest-bound source record."""

    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
    }


def pyright_check(path: Path) -> dict[str, Any]:
    """Type-check this dedicated entry point at its real path."""

    command = ["cmd.exe", "/d", "/c", "pyright", "--outputjson", str(path)]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {}
    summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
    passed = result.returncode == 0 and summary.get("errorCount") == 0
    return {
        "command": command,
        "returncode": result.returncode,
        "status": "PASS" if passed else "FAIL",
        "version": payload.get("version") if isinstance(payload, dict) else None,
        "files_analyzed": summary.get("filesAnalyzed"),
        "error_count": summary.get("errorCount"),
        "warning_count": summary.get("warningCount"),
        "stdout_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
        "stderr_tail": result.stderr[-1000:],
    }


def main() -> int:
    """Run the two-member strict family proof and persist its evidence."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=900,
        help="per-tool timeout for the serial WSL formal gates",
    )
    arguments = parser.parse_args()
    if arguments.timeout_seconds <= 0:
        raise SystemExit("--timeout-seconds must be positive")

    original_view = rail.synthesizable_view
    original_defaults = rail.run_wsl.__defaults__
    rail.synthesizable_view = _view
    rail.run_wsl.__defaults__ = (arguments.timeout_seconds,)
    try:
        payload = rail.FamilyRail(
            BUILD,
            "Build-Cpu.Backend.Rob.PtrWrappers",
            EVIDENCE,
        ).run()
    finally:
        rail.synthesizable_view = original_view
        rail.run_wsl.__defaults__ = original_defaults

    # Build files intentionally contain no upstream identity strings.  Bind
    # the frozen Scala provenance into evidence from the repository inventory.
    provenance = {}
    for source in source_paths_for_build(BUILD):
        source_path = ROOT / source
        provenance[source] = {
            "vendored": source_path.is_file(),
            "sha256": sha256(source_path) if source_path.is_file() else None,
        }
    payload["sources"]["declared_scala_sources"] = provenance
    if provenance:
        first = next(iter(provenance))
        first_path = ROOT / first
        payload["sources"]["scala"] = {
            "path": first,
            "sha256": sha256(first_path) if first_path.is_file() else None,
            "bytes": first_path.stat().st_size if first_path.is_file() else 0,
        }

    own_path = Path(__file__)
    py_compile.compile(str(own_path), doraise=True)
    wrapper_pyright = pyright_check(own_path)
    payload["validator"] = own_path.relative_to(ROOT).as_posix()
    payload["sources"]["validator"] = source_record(own_path)
    payload["sources"]["validator_dependencies"] = {
        "frozen_family_rail": source_record(FROZEN_RAIL),
        "multiline_view_provider": source_record(VIEW_PROVIDER),
    }
    payload["audit_policy"]["validator_dependency_hashes"] = True
    payload["audit_policy"]["per_tool_timeout_seconds"] = arguments.timeout_seconds
    payload["checks"]["validator_wrapper"] = {
        "status": wrapper_pyright["status"],
        "path": own_path.relative_to(ROOT).as_posix(),
        "sha256": sha256(own_path),
        "py_compile": "PASS",
        "pyright": wrapper_pyright,
    }
    if wrapper_pyright["status"] != "PASS":
        payload["status"] = "STRICT_PENDING"
        payload["strict_complete_eligible"] = False
        payload["strict_complete_count_delta"] = 0
        payload["acceptance_eligible"] = False
        payload["failures"].append("pyright validator wrapper")
        payload["unclosed"] = ["strict gates did not all pass"]
    EVIDENCE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({
        "build": BUILD.relative_to(ROOT).as_posix(),
        "status": payload["status"],
        "strict_complete_count_delta": payload["strict_complete_count_delta"],
        "proven": payload["checks"]["catalog_coverage"]["proven"],
        "entries": payload["scope"]["variant_count"],
        "failures": payload["failures"][:8],
    }, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
