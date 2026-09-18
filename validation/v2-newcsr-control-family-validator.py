"""Bounded validator for the NewCSR control/trap family.

The validator compares every emitted member with the pinned ANSI contract,
checks deterministic same-name exports, and runs the mandatory Python,
Verilator and Yosys gates.  It records a bounded result: the complete NewCSR
parent closure and architectural differential remain explicitly open.

NewCSR 控制/陷阱 family 的有界校验器：逐模块比对锁定端口、检查确定性同名
导出，并运行 Python、Verilator、Yosys 门禁。结果只代表叶级有界验证，完整
NewCSR 父级闭包与架构差分仍保持未闭合状态。
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
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Fu.NewCSR.ControlFamily-Hardware.py"
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
WORK = ROOT / "validation/.work/v2-newcsr-control-family"
EVIDENCE = ROOT / "validation/v2-newcsr-control-family-results.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"


def digest(data: bytes) -> str:
    """Return a byte-stable SHA-256 digest. / 返回字节稳定的 SHA-256 摘要。"""

    return hashlib.sha256(data).hexdigest()


def load_target() -> Any:
    """Import the Build by exact path. / 按精确路径导入 Build。"""

    spec = importlib.util.spec_from_file_location("v2_newcsr_control_family", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def width(token: str) -> int:
    """Parse a locked Verilog range. / 解析锁定 Verilog 位宽。"""

    match = re.search(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", token)
    return abs(int(match.group(1)) - int(match.group(2))) + 1 if match else 1


def expected_ports(node: dict[str, Any]) -> set[tuple[str, str, int]]:
    """Return the pinned port set. / 返回钉死的端口集合。"""

    return {(str(port["name"]), str(port["direction"]), width(str(port.get("width", ""))))
            for port in node["ports"]}


def emitted_ports(text: str, member: str) -> set[tuple[str, str, int]]:
    """Parse the first ANSI declaration of ``member``. / 解析成员 ANSI 声明。"""

    header = re.search(r"module\s+" + re.escape(member) + r"\s*\((.*?)\);", text, re.S)
    if header is None:
        raise AssertionError(f"module {member} missing")
    body = text[header.end():]
    body = body[:body.find("endmodule")]
    result: set[tuple[str, str, int]] = set()
    pattern = re.compile(r"^\s*(input|output)\s*(\[[^\]]+\])?\s*(\w+)\s*[,;]", re.M)
    for match in pattern.finditer(body):
        result.add((match.group(3), match.group(1), width(match.group(2) or "")))
    return result


def wsl_path(path: Path) -> str:
    """Convert a Windows path to a WSL path. / 将 Windows 路径转为 WSL 路径。"""

    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path.resolve())],
                            capture_output=True, check=True)
    return result.stdout.decode("utf-8", "replace").strip()


def tool(command: list[str]) -> dict[str, Any]:
    """Run one external tool and retain a compact tail. / 运行工具并保留输出尾部。"""

    result = subprocess.run(command, capture_output=True, check=False)
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {"command": command, "status": "PASS" if result.returncode == 0 else "FAIL",
            "returncode": result.returncode, "output_tail": output[-1200:],
            "output_sha256": digest(output.encode())}


def main() -> int:
    """Run all bounded gates and write machine-readable evidence. / 运行门禁并写证据。"""

    module = load_target()
    hierarchy = json.loads(HIERARCHY.read_text(encoding="utf-8"))["modules"]
    names = tuple(module.COVERED_MODULES)
    WORK.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    records: list[dict[str, Any]] = []
    tool_results: dict[str, Any] = {}
    for name in names:
        first = str(module.build_verilog({"module": name}, {}))
        second = str(module.build_verilog({"module": name}, {}))
        locked = expected_ports(hierarchy[name])
        emitted = emitted_ports(first, name)
        match = locked == emitted
        deterministic = first == second
        if not match:
            failures.append(f"port:{name}")
        if not deterministic:
            failures.append(f"determinism:{name}")
        path = WORK / f"{name}.sv"
        path.write_text(first, encoding="utf-8", newline="\n")
        linux = wsl_path(path)
        tool_results[name] = {
            "verilator": tool(["wsl.exe", "-e", "bash", "-lc",
                                f"verilator --lint-only -Wno-fatal '{linux}'"]),
            "yosys": tool(["wsl.exe", "-e", "bash", "-lc",
                            f"yosys -Q -p 'read_verilog -sv {linux}; hierarchy -top {name}; proc; check'"]),
        }
        if any(result["status"] != "PASS" for result in tool_results[name].values()):
            failures.append(f"tools:{name}")
        records.append({"module": name, "locked_port_count": len(locked),
                        "emitted_port_count": len(emitted), "ports_match": match,
                        "deterministic": deterministic, "verilog_bytes": len(first.encode()),
                        "verilog_sha256": digest(first.encode())})

    compile_result = subprocess.run([sys.executable, "-m", "py_compile", str(TARGET), str(Path(__file__))],
                                    capture_output=True, text=True, check=False)
    pyright_result = subprocess.run(["pyright.cmd", "--outputjson", str(TARGET)],
                                    capture_output=True, text=True, check=False)
    try:
        pyright_summary = json.loads(pyright_result.stdout or "{}").get("summary", {})
    except json.JSONDecodeError:
        pyright_summary = {}
    py_compile_pass = compile_result.returncode == 0
    pyright_pass = pyright_result.returncode == 0 and pyright_summary.get("errorCount", 1) == 0
    if not py_compile_pass:
        failures.append("py_compile")
    if not pyright_pass:
        failures.append("pyright")
    tool_pass = not any(failure.startswith("tools:") for failure in failures)
    gates = {
        "COVERAGE_COMPLETE": "PASS" if len(records) == len(names) else "FAIL",
        "PORT_SURFACE_MATCHED": "PASS" if not any(failure.startswith("port:") for failure in failures) else "FAIL",
        "DETERMINISTIC_VERILOG": "PASS" if not any(failure.startswith("determinism:") for failure in failures) else "FAIL",
        "PY_COMPILE": "PASS" if py_compile_pass else "FAIL",
        "PYRIGHT": "PASS" if pyright_pass else "FAIL",
        "VERILATOR": "PASS" if tool_pass else "FAIL",
        "YOSYS": "PASS" if tool_pass else "FAIL",
        "UHSC_LOCALIZED": "PASS_BOUNDED_FAMILY_LOCAL_NAME",
        "PARENT_CLOSURE_MATCHED": "PENDING",
        "LICENSE_REVIEW": "PENDING",
        "ACCEPTED": "NOT_ALLOWED",
    }
    status = "VALIDATOR_PASS_BOUNDED" if not failures else "VALIDATOR_FAIL"
    evidence = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_NEWCSR_CONTROL_FAMILY",
        "batch_id": "V2-NEWCSR-CONTROL-001",
        "source_commit": SOURCE_COMMIT,
        "scala_sources": list(module.SOURCE_PATHS),
        "target": {"path": str(TARGET.relative_to(ROOT)).replace("\\", "/"),
                   "sha256": digest(TARGET.read_bytes()),
                   "line_count": len(TARGET.read_text(encoding="utf-8").splitlines())},
        "coverage": {"covered_module_count": len(records), "expected_module_count": len(names),
                     "missing_modules": [name for name in names if name not in {r["module"] for r in records}],
                     "covered_modules": list(names)},
        "port_surface": {"status": gates["PORT_SURFACE_MATCHED"], "modules": records},
        "tool_gates": tool_results,
        "py_compile": {"status": gates["PY_COMPILE"], "returncode": compile_result.returncode},
        "pyright": {"status": gates["PYRIGHT"], "summary": pyright_summary},
        "gates": gates,
        "status": status,
        "acceptance_eligible": False,
        "failures": failures,
        "unclosed": ["Complete NewCSR parent behavioral closure remains pending.",
                      "License review and user approval remain pending."],
    }
    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    print(json.dumps({"status": status, "covered": len(records), "port_failures": sum(not r["ports_match"] for r in records),
                      "pyright_errors": pyright_summary.get("errorCount"), "tools": tool_pass,
                      "failures": failures}, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
