"""Prove the locked V2 VldMergeUnit with its injected Mgu behavior.

The Build deliberately receives its vector mask generator through dependency
injection.  This validator supplies the repository-contained NewMgu closure,
then lets the shared strict family rail flatten and compare the complete parent
against VldMergeUnit plus every locked reference child.
"""

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
    "Build-Cpu.Backend.Datapath.VldMergeUnit-Hardware.py"
)
NEW_MGU = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Build-Cpu.Backend.Fu.Vector.NewMgu-Hardware.py"
)
BUILD_ID = "Build-Cpu.Backend.Datapath.VldMergeUnit"
EVIDENCE = ROOT / "validation/v2-build-cpu-backend-datapath-vldmergeunit-strict-evidence.json"


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


def main() -> int:
    """Run the complete flattened parent proof and persist locked evidence."""

    injected = rail.load_module("v2_vldmergeunit_newmgu", NEW_MGU)

    def export_with_injected_mgu(module: Any, name: str) -> str:
        """Export the parent with a fresh exact dependency. / 注入精确依赖并导出父模块。"""

        if name != "VldMergeUnit":
            raise AssertionError(f"unexpected VldMergeUnit member: {name}")
        rtl = module.build_verilog(
            {"module": name},
            {"mask_generator": injected.NewMgu()},
        )
        header = f"module {name}("
        if header not in rtl:
            raise AssertionError("VldMergeUnit export did not preserve the locked top name")
        return rtl.replace(header, f"module DUT_{name}(", 1)

    rail.export_member = export_with_injected_mgu
    payload = rail.FamilyRail(BUILD, BUILD_ID, EVIDENCE).run()
    validator = Path(__file__).resolve()
    shared_rail = Path(rail.__file__).resolve()
    validator_pyright = pyright_check(validator)
    payload["validator"] = validator.relative_to(ROOT).as_posix()
    payload["sources"]["validator"] = source_record(validator)
    payload["sources"]["validator_dependencies"] = {
        "strict_family_rail": source_record(shared_rail),
        "injected_new_mgu_build": source_record(NEW_MGU),
    }
    payload["checks"]["pyright"]["validator"] = validator_pyright
    payload["audit_policy"]["injected_dependency_hash_locked"] = True
    payload["scope"]["injected_dependency"] = {
        "target": "NewMgu",
        "reference_child": "VldMgu",
        "comparison_boundary": "flattened inside VldMergeUnit",
    }
    if validator_pyright.get("status") != "PASS":
        payload["failures"].append("VldMergeUnit validator pyright")
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
