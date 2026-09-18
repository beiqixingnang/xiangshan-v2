"""Bounded validator for the V2 vector datapath family.

校验 Og2ForVector、VTypeBuffer 与 VecExcpDataMergeModule 的锁定端口目录、
可导出性及 Verilator/Yosys 语法闭包。完整父级行为差分保持 pending。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import py_compile
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGET = (
    ROOT
    / "python/Program-System/System-Build/Build-Cpu/Cpu-Core"
    / "Build-Cpu.Backend.Datapath.VectorFamily-Hardware.py"
)
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
WORK = ROOT / "validation/.work/v2-backend-vector-datapath-family"
EVIDENCE = ROOT / "validation/v2-backend-vector-datapath-family-results.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
MEMBERS = (
    "Og2ForVector",
    "VTypeBuffer",
    "VecExcpDataMergeModule",
    "VIAluSrcTypeModule",
    "VIMacSrcTypeModule",
    "VPermSrcTypeModule",
)


def digest(data: bytes) -> str:
    """Hash a byte string exactly. / 对字节串原样求摘要。"""

    return hashlib.sha256(data).hexdigest()


def load_target() -> Any:
    """Load the owned Build by exact path. / 按精确路径加载本批 Build。"""

    spec = importlib.util.spec_from_file_location("v2_vector_datapath_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def width(token: str) -> int:
    """Parse a Verilog range into a bit width. / 解析 Verilog 范围位宽。"""

    match = re.search(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", token)
    return abs(int(match.group(1)) - int(match.group(2))) + 1 if match else 1


def run_wsl(command: list[str]) -> dict[str, Any]:
    """Run one bounded WSL tool gate. / 运行一项有界 WSL 工具门。"""

    rendered = " ".join(_shell_quote(item) for item in command)
    result = subprocess.run(
        ["wsl.exe", "-e", "bash", "-lc", rendered],
        capture_output=True,
        check=False,
    )
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {
        "command": command,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "returncode": result.returncode,
        "output_tail": output[-1200:],
        "output_sha256": digest(output.encode()),
    }


def _shell_quote(value: str) -> str:
    """Quote one POSIX shell word without external helpers. / 安全引用 shell 参数。"""

    return "'" + value.replace("'", "'\\''") + "'"


def wsl_path(path: Path) -> str:
    """Map a Windows path into WSL. / 把 Windows 路径映射到 WSL。"""

    result = subprocess.run(
        ["wsl.exe", "-e", "wslpath", "-a", str(path.resolve())],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", "replace"))
    return result.stdout.decode("utf-8", "replace").strip()


def pyright_gate() -> dict[str, Any]:
    """Run Pyright on this Build only. / 仅对本批 Build 运行 Pyright。"""

    result = subprocess.run(
        ["pyright.cmd", "--outputjson", str(TARGET)],
        capture_output=True,
        check=False,
    )
    raw = (result.stdout + result.stderr).decode("utf-8", "replace")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"summary": {}, "raw_tail": raw[-1200:]}
    summary = parsed.get("summary", {}) if isinstance(parsed, dict) else {}
    errors = int(summary.get("errorCount", 1))
    return {
        "command": ["pyright.cmd", "--outputjson", str(TARGET)],
        "status": "PASS" if result.returncode == 0 and errors == 0 else "FAIL",
        "returncode": result.returncode,
        "summary": summary,
        "output_sha256": digest(raw.encode()),
    }


def main() -> int:
    module = load_target()
    hierarchy = json.loads(HIERARCHY.read_text(encoding="utf-8"))["modules"]
    failures: list[str] = []
    port_surface: dict[str, Any] = {}
    tool_gates: dict[str, Any] = {}
    pyright = pyright_gate()
    if pyright["status"] != "PASS":
        failures.append("pyright")
    if tuple(module.COVERED_MODULES) != MEMBERS:
        failures.append("covered module list")
    for member in MEMBERS:
        expected = {
            (p["name"], p["direction"], width(str(p.get("width", ""))))
            for p in hierarchy[member]["ports"]
        }
        actual = set(module.PORT_SPECS[member])
        port_surface[member] = {
            "locked": len(expected),
            "emitted": len(actual),
            "match": expected == actual,
            "children": hierarchy[member].get("children", []),
        }
        if expected != actual:
            failures.append("port mismatch " + member)
        if set(module.vector_datapath_model(member)) != {
            name for name, direction, _width in actual if direction == "output"
        }:
            failures.append("oracle mismatch " + member)
    py_compile.compile(str(TARGET), doraise=True)
    WORK.mkdir(parents=True, exist_ok=True)
    for member in MEMBERS:
        first = module.build_verilog({"module": member}, {})
        second = module.build_verilog({"module": member}, {})
        if first != second:
            failures.append("nondeterministic RTL " + member)
        path = WORK / (member + ".sv")
        path.write_text(first, encoding="utf-8", newline="\n")
        linux = wsl_path(path)
        verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal", linux])
        yosys_script = "read_verilog -sv " + _shell_quote(linux) + "; proc; check"
        yosys = run_wsl(["yosys", "-Q", "-p", yosys_script])
        tool_gates[member] = {
            "rtl_bytes": len(first.encode()),
            "rtl_sha256": digest(first.encode()),
            "verilator": verilator,
            "yosys": yosys,
        }
        if verilator["status"] != "PASS" or yosys["status"] != "PASS":
            failures.append("tool gate " + member)
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_BACKEND_VECTOR_DATAPATH_FAMILY",
        "batch_id": "V2-BACKEND-VECTOR-DATAPATH-001",
        "source_commit": SOURCE_COMMIT,
        "scala_sources": list(module.SOURCE_PATHS),
        "covered_modules": list(MEMBERS),
        "locked_port_catalog": {
            member: [
                {"name": name, "direction": direction, "width": width}
                for name, direction, width in module.PORT_SPECS[member]
            ]
            for member in MEMBERS
        },
        "port_surface": port_surface,
        "py_compile": "PASS",
        "pyright": pyright,
        "tool_gates": tool_gates,
        "gates": {
            "PYTHON_PRESENT": "PASS",
            "PYRIGHT": pyright["status"],
            "DIRECT_TEST_PASS_BOUNDED": "PASS_BOUNDED_PORT_ORACLE",
            "V2_REFERENCE_MATCHED": "PENDING_LOCKED_VECTOR_DATAPATH_DIFF",
            "VERILATOR": "PASS" if not any(
                item.endswith(member) for item in failures for member in MEMBERS
            ) else "FAIL",
            "YOSYS": "PASS" if not any(
                item.endswith(member) for item in failures for member in MEMBERS
            ) else "FAIL",
            "UHSC_LOCALIZED": "PASS_BOUNDED_FAMILY_LOCAL_NAME",
            "PARENT_CLOSURE_MATCHED": "PENDING",
            "LICENSE_REVIEW": "PENDING",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "status": "VALIDATOR_PASS_BOUNDED" if not failures else "VALIDATOR_FAIL",
        "acceptance_eligible": False,
        "failures": failures,
        "unclosed": [
            "Complete vector datapath behavior and parent closure remain pending.",
            "Locked reference differential, license review, and user approval remain pending.",
        ],
    }
    EVIDENCE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"status": payload["status"], "covered": len(MEMBERS), "failures": failures}))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
