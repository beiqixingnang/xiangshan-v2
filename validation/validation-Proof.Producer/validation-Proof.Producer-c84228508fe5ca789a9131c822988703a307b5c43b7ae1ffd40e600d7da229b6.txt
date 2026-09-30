"""Prove the locked V2 TagArray closure with the multiline section 5C view."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parent))
import v2_funcunit_strict_validator as multiline  # noqa: E402
import v2_strict_family_rail as rail  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/"
    "Build-Cpu.Cache.Dcache.Meta.TagArray-Hardware.py"
)
BUILD_ID = "Build-Cpu.Cache.Dcache.Meta.TagArray"
EVIDENCE = ROOT / "validation/v2-build-cpu-cache-dcache-meta-tagarray-strict-evidence.json"


def source_record(path: Path) -> dict[str, Any]:
    """Lock one repository-contained proof input. / 锁定仓库内的一项证明输入。"""

    return {"path": path.relative_to(ROOT).as_posix(),
            "sha256": rail.sha256_file(path), "bytes": path.stat().st_size}


def pyright_check(path: Path) -> dict[str, Any]:
    """Run Pyright on this validator. / 对本验证器运行 Pyright。"""

    command = ["cmd.exe", "/d", "/c", "pyright", "--outputjson",
               str(path).replace("\\", "/")]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", check=False, timeout=60)
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        parsed = {}
    summary = parsed.get("summary", {}) if isinstance(parsed, dict) else {}
    return {"command": command, "returncode": result.returncode,
            "status": "PASS" if result.returncode == 0 and summary.get("errorCount") == 0 else "FAIL",
            "version": parsed.get("version") if isinstance(parsed, dict) else None,
            "error_count": summary.get("errorCount"),
            "files_analyzed": summary.get("filesAnalyzed"),
            "diagnostics": parsed.get("generalDiagnostics", []) if isinstance(parsed, dict) else [],
            "stderr_tail": result.stderr[-600:]}


def quick_two_sided_control(self: rail.FamilyRail,
                            items: list[dict[str, Any]]) -> dict[str, Any]:
    """Reject a public ready-path mutation without re-proving every SRAM bit."""

    if len(items) != 1:
        return {"status": "FAIL", "cases": {}, "note": "unexpected member count"}
    item = items[0]
    verdicts: dict[str, Any] = {}
    for side in ("target", "reference"):
        path = item[side]
        source = path.read_text(encoding="utf-8")
        mutated, count = re.subn(
            r"assign\s+io_read_ready\s*=\s*(?P<rhs>[^;]+);",
            lambda match: f"assign io_read_ready = ~({match.group('rhs')});",
            source,
            count=1,
        )
        if count != 1:
            verdicts[f"sequential.{side}"] = {
                "status": "FAIL", "mutation_applied": False,
                "reason": "io_read_ready assignment not found exactly once",
            }
            continue
        mutant = self.work / f"MUTANT_quick_{side}.sv"
        mutant.write_text(mutated, encoding="utf-8", newline="\n")
        files = ([mutant, item["reference"]] if side == "target"
                 else [item["target"], mutant])
        pair = " ".join(shlex.quote(rail.wsl_path(entry)) for entry in files)
        script = (
            f"read_verilog -sv {pair}; proc; async2sync; memory; opt; "
            "flatten REF_TagArray; flatten DUT_TagArray; "
            "equiv_make REF_TagArray DUT_TagArray TagArray_EQUIV; "
            "prep -top TagArray_EQUIV; equiv_simple -undef -seq 1; "
            "equiv_status -assert"
        )
        verdict = rail.run_wsl(["yosys", "-Q", "-p", script])
        still_proves = all(verdict.get("equiv_success_markers", {}).values())
        explicit_failure = verdict.get("equiv_failure_marker") is True
        detected = (
            isinstance(verdict.get("returncode"), int)
            and verdict.get("timed_out") is not True
            and explicit_failure
            and not still_proves
        )
        verdicts[f"sequential.{side}"] = {
            "status": "PASS" if detected else "FAIL",
            "control_entry": "TagArray",
            "control_port": "io_read_ready",
            "mutation_applied": True,
            "explicit_failure_marker": explicit_failure,
            "success_marker_still_present": still_proves,
            "returncode": verdict.get("returncode"),
        }
    passed = bool(verdicts) and all(case["status"] == "PASS"
                                    for case in verdicts.values())
    return {
        "status": "PASS" if passed else "FAIL",
        "cases": verdicts,
        "method": "equiv_simple -undef -seq 1 on the flattened full pair",
        "note": "The baseline uses full equiv_induct; this control only establishes that "
                "the same pair rejects a mutation on each side.",
    }


def main() -> int:
    """Run the complete two-bank storage proof and persist locked evidence."""

    rail.synthesizable_view = multiline.synthesizable_view
    runner = rail.FamilyRail(BUILD, BUILD_ID, EVIDENCE)
    original_control = rail.FamilyRail.negative_control
    rail.FamilyRail.negative_control = quick_two_sided_control
    try:
        payload = runner.run()
    finally:
        rail.FamilyRail.negative_control = original_control
    validator = Path(__file__).resolve()
    shared_rail = Path(rail.__file__).resolve()
    multiline_view = Path(multiline.__file__).resolve()
    validator_pyright = pyright_check(validator)
    payload["validator"] = validator.relative_to(ROOT).as_posix()
    payload["sources"]["validator"] = source_record(validator)
    payload["sources"]["validator_dependencies"] = {
        "strict_family_rail": source_record(shared_rail),
        "multiline_reference_view": source_record(multiline_view),
    }
    payload["checks"]["pyright"]["validator"] = validator_pyright
    variant_detail = payload["checks"]["variants"][0].get("yosys_equiv", {})
    if variant_detail.get("timed_out") is True:
        variant_detail["formal_success_marker"] = False
        payload["scope"]["variants"]["TagArray"]["success_marker"] = False
    payload["view_policy"] = {
        "status": "PASS",
        "kind": "SECTION_5C_MULTILINE_AUTOMATIC_AND_SRAM_VIEW",
        "locked_sources_written": False,
        "line_conservation_required": True,
        "register_update_equations_required": True,
    }
    if validator_pyright.get("status") != "PASS":
        payload["failures"].append("TagArray validator pyright")
        payload["unclosed"] = ["strict gates did not all pass"]
        payload["status"] = "STRICT_PENDING"
        payload["strict_complete_eligible"] = False
        payload["strict_complete_count_delta"] = 0
        payload["acceptance_eligible"] = False
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"],
                      "strict_complete_count_delta": payload["strict_complete_count_delta"],
                      "proven": payload["checks"]["catalog_coverage"]["proven"],
                      "negative_control": payload["checks"]["negative_control"]["status"],
                      "failure_count": len(payload["failures"]),
                      "first_failures": payload["failures"][:8]}, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
