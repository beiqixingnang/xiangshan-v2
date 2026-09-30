"""Prove the locked V2 ICacheReplacer with the multiline-safe section 5C view."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parent))
import v2_funcunit_strict_validator as multiline  # noqa: E402
import v2_strict_family_rail as rail  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Build-Cpu.Frontend.Icache.ICacheReplacer-Hardware.py"
)
BUILD_ID = "Build-Cpu.Frontend.Icache.ICacheReplacer"
EVIDENCE = ROOT / "validation/v2-build-cpu-frontend-icache-icachereplacer-strict-evidence.json"
SCALA_SOURCE = ROOT / "upstream/src/main/scala/xiangshan/frontend/icache/ICache.scala"


def source_record(path: Path) -> dict[str, Any]:
    """Lock one repository-contained validator source. / 锁定仓库内验证器源码。"""

    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": rail.sha256_file(path),
        "bytes": path.stat().st_size,
    }


def pyright_check(path: Path) -> dict[str, Any]:
    """Run the pinned static analyzer on this validator. / 对本验证器运行固定静态分析。"""

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
    """Run the exact-member proof and persist independently hashed evidence."""

    rail.synthesizable_view = multiline.synthesizable_view
    payload = rail.FamilyRail(BUILD, BUILD_ID, EVIDENCE).run()
    validator = Path(__file__).resolve()
    shared_rail = Path(rail.__file__).resolve()
    multiline_view = Path(multiline.__file__).resolve()
    validator_pyright = pyright_check(validator)
    payload["validator"] = validator.relative_to(ROOT).as_posix()
    payload["sources"]["validator"] = source_record(validator)
    if SCALA_SOURCE.is_file():
        payload["sources"]["scala"] = source_record(SCALA_SOURCE)
        payload["sources"]["declared_scala_sources"] = {
            SCALA_SOURCE.relative_to(ROOT).as_posix(): {
                "vendored": True,
                "sha256": rail.sha256_file(SCALA_SOURCE),
            }
        }
    payload["sources"]["validator_dependencies"] = {
        "strict_family_rail": source_record(shared_rail),
        "multiline_reference_view": source_record(multiline_view),
    }
    payload["checks"]["pyright"]["validator"] = validator_pyright
    payload["view_policy"] = {
        "status": "PASS",
        "kind": "SECTION_5C_MULTILINE_AUTOMATIC_AND_POSITIONAL_PACKED_VIEW",
        "locked_sources_written": False,
        "line_conservation_required": True,
        "register_update_equations_required": True,
    }
    if validator_pyright.get("status") != "PASS":
        payload["failures"].append("ICacheReplacer validator pyright")
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
        "proven": payload["checks"]["catalog_coverage"]["proven"],
        "negative_control": payload["checks"]["negative_control"]["status"],
        "failure_count": len(payload["failures"]),
        "first_failures": payload["failures"][:8],
    }, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
