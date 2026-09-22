"""Prove the locked V2 ICache utility family with explicit provenance."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parent))
import v2_strict_family_rail as rail  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Build-Cpu.Frontend.Icache.Utils-Hardware.py"
)
BUILD_ID = "Build-Cpu.Frontend.Icache.Utils"
EVIDENCE = ROOT / "validation/v2-build-cpu-frontend-icache-utils-strict-evidence.json"
SCALA_SOURCES = (
    ROOT / "upstream/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala",
    ROOT / "upstream/src/main/scala/xiangshan/frontend/icache/FIFO.scala",
)


def source_record(path: Path) -> dict[str, Any]:
    """Lock one repository-contained source by path, digest, and size."""

    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": rail.sha256_file(path),
        "bytes": path.stat().st_size,
    }


def pyright_check(path: Path) -> dict[str, Any]:
    """Run pinned Pyright on this validator and retain machine-readable output."""

    command = [
        "cmd.exe", "/d", "/c", "pyright", "--outputjson",
        str(path).replace("\\", "/"),
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=60,
    )
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        parsed = {}
    summary = parsed.get("summary", {}) if isinstance(parsed, dict) else {}
    return {
        "command": command,
        "returncode": result.returncode,
        "status": (
            "PASS"
            if result.returncode == 0 and summary.get("errorCount") == 0
            else "FAIL"
        ),
        "version": parsed.get("version") if isinstance(parsed, dict) else None,
        "error_count": summary.get("errorCount"),
        "files_analyzed": summary.get("filesAnalyzed"),
        "diagnostics": parsed.get("generalDiagnostics", []) if isinstance(parsed, dict) else [],
        "stderr_tail": result.stderr[-600:],
    }


def main() -> int:
    """Run all utility members and persist strict, provenance-complete evidence."""

    payload = rail.FamilyRail(BUILD, BUILD_ID, EVIDENCE).run()
    validator = Path(__file__).resolve()
    payload["validator"] = validator.relative_to(ROOT).as_posix()
    payload["sources"]["validator"] = source_record(validator)
    present = [path for path in SCALA_SOURCES if path.is_file()]
    if present:
        payload["sources"]["scala"] = source_record(present[0])
    payload["sources"]["declared_scala_sources"] = {
        path.relative_to(ROOT).as_posix(): (
            {"vendored": True, "sha256": rail.sha256_file(path)}
            if path.is_file()
            else {"vendored": False, "note": "declared Scala source is missing"}
        )
        for path in SCALA_SOURCES
    }
    payload["sources"]["validator_dependencies"] = {
        "strict_family_rail": source_record(Path(rail.__file__).resolve()),
    }
    validator_pyright = pyright_check(validator)
    payload["checks"]["pyright"]["validator"] = validator_pyright
    if validator_pyright.get("status") != "PASS":
        payload["failures"].append("ICache utility validator pyright")
        payload["unclosed"] = ["strict gates did not all pass"]
        payload["status"] = "STRICT_PENDING"
        payload["strict_complete_eligible"] = False
        payload["strict_complete_count_delta"] = 0
        payload["acceptance_eligible"] = False
    EVIDENCE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({
        "status": payload["status"],
        "strict_complete_count_delta": payload["strict_complete_count_delta"],
        "entries": payload["scope"]["variant_count"],
        "proven": payload["checks"]["catalog_coverage"]["proven"],
        "negative_control": payload["checks"]["negative_control"]["status"],
        "failure_count": len(payload["failures"]),
        "first_failures": payload["failures"][:8],
    }, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
