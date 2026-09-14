"""Independent probe for the Kunminghu V2 full-generation gate.
昆明湖 V2 完整生成门禁的独立探针。

The probe converts the explicit UHSCTop boundary, inventories the 57 existing
Build-Cpu files, and records which top closures are still absent.  It is
deliberately independent from implementation workers and never promotes a
bounded/reduced result to ``ACCEPTED``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = ROOT / "python/Program-System/System-Build/Build-Cpu"
TOP_FILE = BUILD_ROOT / "Cpu-Core/Build-Cpu.Top.UHSCTop-GenerationProbe-Hardware.py"
WORK_DIR = ROOT / "validation/.work"
RTL_FILE = WORK_DIR / "uhsc-top-probe.sv"
EVIDENCE = ROOT / "validation/v2-top-generation-probe-results.json"
EXPECTED_REFERENCE = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
EXPECTED_SOURCE = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"


def load_top_module():
    """Load the hyphenated Build file without changing its source imports.
    以不修改源文件导入的方式加载带连字符的 Build 文件。
    """

    spec = importlib.util.spec_from_file_location("uhsc_top_probe", TOP_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {TOP_FILE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def module_names(text: str) -> list[str]:
    """Return deterministic Verilog module names from generated text.
    从生成文本中提取确定性的 Verilog 模块名。
    """

    return sorted(set(re.findall(r"^module\s+([A-Za-z_][A-Za-z0-9_$]*)\s*\(", text, re.MULTILINE)))


def main() -> int:
    builds = sorted(BUILD_ROOT.rglob("Build-*.py"))
    top = load_top_module()
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    rtl = top.build_verilog()
    RTL_FILE.write_text(rtl, encoding="utf-8", newline="\n")
    modules = module_names(rtl)

    # These are the mandatory V2 hierarchy roots identified from Top.scala.
    required_roots = ["XSCore", "L2Top", "XSTile", "XSTop"]
    present_build_text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in builds)
    defined_classes = set(re.findall(r"^class\s+([A-Za-z_][A-Za-z0-9_]*)\b", present_build_text, re.MULTILINE))
    # Match actual class definitions, not prose/docstrings that mention the
    # names of still-unimplemented Scala roots.
    missing_build_roots = [root for root in required_roots if root not in defined_classes]
    generated_top = "UHSCTop" in modules

    verilator_path = shutil.which("verilator")
    if verilator_path is None:
        verilator_status = "UNAVAILABLE"
        verilator_returncode = None
    else:
        verilator = subprocess.run(
            [verilator_path, "--lint-only", "-Wall", str(RTL_FILE)],
            capture_output=True,
            text=True,
            check=False,
        )
        verilator_returncode = verilator.returncode
        verilator_status = "PASS" if verilator.returncode == 0 else "FAIL"

    report = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_TOP_GENERATION_PROBE",
        "status": "GENERATION_PROBE_PASS_REDUCED" if generated_top else "GENERATION_PROBE_FAIL",
        "complete_gate": "BLOCKED_MISSING_CLOSURES",
        "accepted": "NOT_ALLOWED",
        "build_file_count": len(builds),
        "build_files": [str(path.relative_to(ROOT)).replace("\\", "/") for path in builds],
        "generated_artifact": {
            "path": str(RTL_FILE.relative_to(ROOT)).replace("\\", "/"),
            "sha256": hashlib.sha256(rtl.encode("utf-8")).hexdigest(),
            "bytes": len(rtl.encode("utf-8")),
            "modules": modules,
            "top_module": "UHSCTop" if generated_top else None,
        },
        "required_hierarchy_roots": required_roots,
        "defined_build_classes": sorted(name for name in defined_classes if name in required_roots),
        "missing_build_roots": missing_build_roots,
        "locked_baseline": {
            "source_commit": EXPECTED_SOURCE,
            "reference_xstop_sha256": EXPECTED_REFERENCE,
            "reference_immutable": True,
        },
        "tool_gates": {"verilator_lint": verilator_status},
        "blocking_reasons": [
            "XSCore, L2Top, XSTile and source-named XSTop Build closures are not present",
            "probe drives quiescent outputs and asserts io_closure_missing",
            "complete XSTop module/port inventory differential has not run",
        ],
    }
    EVIDENCE.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    # A generated probe is useful evidence even when an optional host linter is
    # unavailable; the complete gate remains blocked by the missing closures.
    return 0 if generated_top and verilator_status in {"PASS", "UNAVAILABLE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
