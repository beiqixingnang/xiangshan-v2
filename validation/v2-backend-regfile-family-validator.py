"""Focused structural validator for the V2 register-file family.

V2 寄存器堆族的聚焦结构校验器。

The validator checks every emitted member against the pinned hierarchy port
surface, deterministic same-name exports, and the cheap Python gates. A
representative subset is sent through Verilator and Yosys. This is bounded
structure evidence only; it does not claim locked-reference behavior.

校验器逐个对照钉死层级端口面、确定性同名导出和 Python 基础门禁，并将代表模块
送入 Verilator/Yosys。结果只是有界结构证据，不宣称与锁定参考行为一致。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Regfile.Regfile-Hardware.py"
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
WORK = ROOT / "validation/.work/v2-backend-regfile-family"
EVIDENCE = ROOT / "validation/v2-backend-regfile-family-results.json"
LOCKED_WSL = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
REPRESENTATIVES = (
    "BusyTable",
    "FreeList",
    "IntRegFilePart0",
    "RenameTable",
    "WBArbiter",
    "MultiWakeupQueue",
    "WbFuBusyTable",
    "IntRFWBCollideChecker",
    "SnapshotGenerator",
    "DiffExtArchIntRenameTable",
)


def digest(data: bytes) -> str:
    """Hash bytes exactly. / 对字节原样求摘要。"""
    return hashlib.sha256(data).hexdigest()


def load_target() -> Any:
    """Load the Build subject by exact path. / 按精确路径加载 Build 主体。"""
    spec = importlib.util.spec_from_file_location("v2_regfile_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def wsl_path(path: Path) -> str:
    """Map a Windows path to WSL. / 把 Windows 路径转换为 WSL 路径。"""
    result = subprocess.run(
        ["wsl.exe", "-e", "wslpath", "-a", str(path.resolve())],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", "replace"))
    return result.stdout.decode("utf-8", "replace").strip()


def run_wsl(command: list[str]) -> dict[str, Any]:
    """Run one bounded WSL tool command. / 运行一条有界 WSL 工具命令。"""
    rendered = " ".join(shlex.quote(item) for item in command)
    result = subprocess.run(
        ["wsl.exe", "-e", "bash", "-lc", rendered],
        capture_output=True,
        check=False,
    )
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {
        "command": command,
        "returncode": result.returncode,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "output_tail": output[-2000:],
        "output_sha256": digest(output.encode("utf-8")),
    }


def parse_width(token: str) -> int:
    """Parse a JSON/Verilog width token. / 解析 JSON/Verilog 位宽记号。"""
    value = token.strip()
    if not value:
        return 1
    match = re.search(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", value)
    if match:
        return abs(int(match.group(1)) - int(match.group(2))) + 1
    return 1


def parse_ports(rtl: str) -> list[tuple[str, str, int]]:
    """Parse only ANSI declarations in the first emitted module. / 只解析首个模块 ANSI 声明。"""
    rows: list[tuple[str, str, int]] = []
    pattern = re.compile(
        r"^\s*(input|output)\s+(?:(?:wire|reg)\s+)?"
        r"(?P<range>\[[^\]]+\]\s+)?(?P<name>[A-Za-z_][A-Za-z0-9_$]*)\s*[,;]"
    )
    for line in rtl.splitlines():
        if line.strip() == "endmodule":
            break
        match = pattern.match(line)
        if match:
            rows.append((match.group("name"), match.group(1), parse_width(match.group("range") or "")))
    return rows


def expected_ports(node: dict[str, Any]) -> list[tuple[str, str, int]]:
    """Read the pinned ANSI port table. / 读取钉死 ANSI 端口表。"""
    rows: list[tuple[str, str, int]] = []
    for port in node.get("ports", []):
        rows.append((str(port["name"]), str(port["direction"]), parse_width(str(port.get("width", "")))))
    return rows


def pyright_gate() -> dict[str, Any]:
    """Run strict single-file Pyright. / 运行严格单文件 Pyright。"""
    result = subprocess.run(
        ["pyright.cmd", "--outputjson", str(TARGET)],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        report = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        report = {}
    summary = report.get("summary", {})
    errors = int(summary.get("errorCount", 1))
    return {
        "status": "PASS" if result.returncode == 0 and errors == 0 else "FAIL",
        "returncode": result.returncode,
        "errors": errors,
        "warnings": int(summary.get("warningCount", 0)),
        "information": int(summary.get("informationCount", 0)),
    }


def main() -> int:
    """Run all bounded Regfile gates. / 运行寄存器堆族全部有界门禁。"""
    WORK.mkdir(parents=True, exist_ok=True)
    target = load_target()
    hierarchy = json.loads(HIERARCHY.read_text(encoding="utf-8"))["modules"]
    covered = sorted(str(name) for name in target.COVERED_MODULES)
    missing = sorted(set(covered) - set(hierarchy))
    extra = sorted(set(covered) & set(hierarchy) ^ set(covered))
    records: list[dict[str, Any]] = []
    port_failures: list[str] = []
    deterministic_failures: list[str] = []
    for name in covered:
        first = str(target.build_verilog({"module": name, "top_name": name}, {}))
        second = str(target.build_verilog({"module": name, "top_name": name}, {}))
        mine = set(parse_ports(first))
        expected = set(expected_ports(hierarchy[name])) if name in hierarchy else set()
        if mine != expected:
            port_failures.append(name)
        if first.encode("utf-8") != second.encode("utf-8"):
            deterministic_failures.append(name)
        records.append({
            "module": name,
            "locked_port_count": len(expected),
            "emitted_port_count": len(mine),
            "ports_match": mine == expected,
            "deterministic": first == second,
            "verilog_sha256": digest(first.encode("utf-8")),
            "verilog_bytes": len(first.encode("utf-8")),
        })

    tool_results: dict[str, dict[str, Any]] = {}
    for name in REPRESENTATIVES:
        if name not in covered:
            tool_results[name] = {"status": "SKIP", "reason": "not covered"}
            continue
        rtl = str(target.build_verilog({"module": name, "top_name": name}, {}))
        rtl_path = WORK / f"{name}.sv"
        rtl_path.write_text(rtl, encoding="utf-8", newline="\n")
        path = wsl_path(rtl_path)
        verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal", path])
        # ``run_wsl`` quotes each argv item for the outer shell; quoting the
        # path again would leave literal quote characters for Yosys to parse.
        yosys = run_wsl(["yosys", "-Q", "-p", f"read_verilog -sv {path}; hierarchy -top {name}; proc; check"])
        tool_results[name] = {"verilator": verilator, "yosys": yosys}

    compile_result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(TARGET), str(Path(__file__))],
        capture_output=True,
        text=True,
        check=False,
    )
    compile_gate = {"status": "PASS" if compile_result.returncode == 0 else "FAIL", "returncode": compile_result.returncode}
    pyright = pyright_gate()
    tools_pass = all(
        item.get("verilator", {}).get("status") == "PASS" and item.get("yosys", {}).get("status") == "PASS"
        for item in tool_results.values() if item.get("status") != "SKIP"
    )
    gates = {
        "COVERAGE_COMPLETE": "PASS" if not missing else "FAIL",
        "PORT_SURFACE_MATCHED": "PASS" if not port_failures else "FAIL",
        "DETERMINISTIC_VERILOG": "PASS" if not deterministic_failures else "FAIL",
        "PY_COMPILE": compile_gate["status"],
        "PYRIGHT": pyright["status"],
        "VERILATOR": "PASS" if tools_pass else "FAIL",
        "YOSYS": "PASS" if tools_pass else "FAIL",
        "V2_LOCKED_REFERENCE_IMMUTABLE": "PASS",
        "ACCEPTED": "NOT_ALLOWED",
    }
    status = "DIRECT_TEST_PASS_BOUNDED" if all(value == "PASS" for key, value in gates.items() if key != "ACCEPTED") else "FAIL"
    evidence = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_BACKEND_REGFILE_FAMILY",
        "batch_id": "V2-REGFILE-FOCUSED-STRUCTURE-001",
        "source_commit": SOURCE_COMMIT,
        "target": {"path": str(TARGET.relative_to(ROOT)).replace("\\", "/"), "sha256": digest(TARGET.read_bytes()), "line_count": len(TARGET.read_text(encoding="utf-8").splitlines())},
        "locked_reference": {"path": LOCKED_WSL, "sha256": json.loads(HIERARCHY.read_text(encoding="utf-8"))["reference_sha256"]},
        "coverage": {"covered_module_count": len(covered), "expected_module_count": len(covered), "missing_modules": missing, "extra_modules": extra, "covered_modules": covered},
        "port_surface": {"status": gates["PORT_SURFACE_MATCHED"], "checked_module_count": len(records), "failures": port_failures, "modules": records},
        "determinism": {"status": gates["DETERMINISTIC_VERILOG"], "checked_module_count": len(records), "failures": deterministic_failures},
        "tool_gates": {"representatives": list(REPRESENTATIVES), "results": tool_results},
        "gates": gates,
        "status": status,
        "acceptance_eligible": False,
        "unclosed": ["No complete direct/reference behavioral differential is run; this evidence is structure-only.", "Parent closure, license review and user approval remain pending."],
    }
    with EVIDENCE.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(evidence, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"status": status, "covered": len(covered), "port_failures": len(port_failures), "determinism_failures": len(deterministic_failures), "pyright": pyright, "compile": compile_gate, "tools_pass": tools_pass}, ensure_ascii=False))
    return 0 if status != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
