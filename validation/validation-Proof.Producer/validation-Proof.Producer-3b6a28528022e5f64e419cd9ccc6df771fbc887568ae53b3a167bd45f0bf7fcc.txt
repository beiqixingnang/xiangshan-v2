"""Prove InstrUncache and mutate its reference child for the negative control."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parent))
import v2_strict_family_rail as rail  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Build-Cpu.Frontend.Icache.InstrUncache-Hardware.py"
)
BUILD_ID = "Build-Cpu.Frontend.Icache.InstrUncache"
EVIDENCE = ROOT / "validation/v2-build-cpu-frontend-icache-instruncache-strict-evidence.json"
SCALA = ROOT / "upstream/src/main/scala/xiangshan/frontend/icache/InstrUncache.scala"


def source_record(path: Path) -> dict[str, Any]:
    """Lock one repository-contained proof input. / 锁定仓库内的一项证明输入。"""

    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": rail.sha256_file(path),
        "bytes": path.stat().st_size,
    }


def pyright_check(path: Path) -> dict[str, Any]:
    """Run Pyright on this validator. / 对本验证器运行 Pyright。"""

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
        "diagnostics": (
            parsed.get("generalDiagnostics", []) if isinstance(parsed, dict) else []
        ),
        "stderr_tail": result.stderr[-600:],
    }


def reference_child_negative_control(work: Path) -> dict[str, Any]:
    """Invert the locked arbiter data path and require equivalence to fail."""

    target = work / "DUT_InstrUncache.sv"
    reference = work / "REF_InstrUncache.sv"
    source = reference.read_text(encoding="utf-8")
    mutated, count = re.subn(
        r"assign\s+io_out_bits_data\s*=\s*io_in_0_bits_data\s*;",
        "assign io_out_bits_data = ~io_in_0_bits_data;",
        source,
        count=1,
    )
    if count != 1:
        return {
            "status": "FAIL",
            "mutation_applied": False,
            "reason": "locked arbiter data assignment was not found exactly once",
        }
    mutant = work / "MUTANT_sequential_reference_child.sv"
    mutant.write_text(mutated, encoding="utf-8", newline="\n")
    files = " ".join(
        shlex.quote(rail.wsl_path(path)) for path in (target, mutant)
    )
    script = (
        f"read_verilog -sv {files}; proc; async2sync; memory; opt; "
        "flatten REF_InstrUncache; flatten DUT_InstrUncache; "
        "equiv_make REF_InstrUncache DUT_InstrUncache InstrUncache_EQUIV; "
        "prep -top InstrUncache_EQUIV; equiv_induct -undef; equiv_status -assert"
    )
    verdict = rail.run_wsl(["yosys", "-Q", "-p", script])
    still_proves = all(verdict.get("equiv_success_markers", {}).values())
    explicit_failure = verdict.get("equiv_failure_marker") is True
    process_ran = (
        isinstance(verdict.get("returncode"), int)
        and verdict.get("timed_out") is not True
    )
    detected = process_ran and explicit_failure and not still_proves
    return {
        "status": "PASS" if detected else "FAIL",
        "control_entry": "InstrUncache/Arbiter1_InsUncacheResp",
        "control_port": "io_out_bits_data",
        "mutation_applied": True,
        "explicit_failure_marker": explicit_failure,
        "success_marker_still_present": still_proves,
        "returncode": verdict.get("returncode"),
    }


def main() -> int:
    """Run the parent proof and replace only its unsupported child-side control."""

    runner = rail.FamilyRail(BUILD, BUILD_ID, EVIDENCE, scala_path=SCALA)
    payload = runner.run()
    custom_reference = reference_child_negative_control(runner.work)
    control = payload["checks"]["negative_control"]
    control["cases"]["sequential.reference"] = custom_reference
    control["status"] = (
        "PASS"
        if all(case.get("status") == "PASS" for case in control["cases"].values())
        else "FAIL"
    )
    failure = "negative control did not detect a mutated design"
    if custom_reference["status"] == "PASS" and failure in payload["failures"]:
        payload["failures"].remove(failure)

    validator = Path(__file__).resolve()
    shared_rail = Path(rail.__file__).resolve()
    validator_pyright = pyright_check(validator)
    payload["validator"] = validator.relative_to(ROOT).as_posix()
    payload["sources"]["validator"] = source_record(validator)
    payload["sources"]["validator_dependencies"] = {
        "strict_family_rail": source_record(shared_rail),
    }
    payload["checks"]["pyright"]["validator"] = validator_pyright
    payload["audit_policy"]["reference_child_negative_control"] = True
    if validator_pyright.get("status") != "PASS":
        payload["failures"].append("InstrUncache validator pyright")

    status = "COMPLETE_EQUIVALENCE" if not payload["failures"] else "STRICT_PENDING"
    payload["status"] = status
    payload["strict_complete_eligible"] = status == "COMPLETE_EQUIVALENCE"
    payload["strict_complete_count_delta"] = 1 if status == "COMPLETE_EQUIVALENCE" else 0
    payload["acceptance_eligible"] = status == "COMPLETE_EQUIVALENCE"
    payload["unclosed"] = [] if not payload["failures"] else [
        "strict gates did not all pass"
    ]
    EVIDENCE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({
        "status": status,
        "strict_complete_count_delta": payload["strict_complete_count_delta"],
        "proven": payload["checks"]["catalog_coverage"]["proven"],
        "negative_control": control["status"],
        "failure_count": len(payload["failures"]),
        "first_failures": payload["failures"][:8],
    }, ensure_ascii=False))
    return 0 if status == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
