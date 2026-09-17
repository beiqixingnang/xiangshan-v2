"""Bounded validator for the UHSC JTAG shifter family.
UHSC JTAG 移位链 family 的有界校验器。

The validator checks the five locked JtagShifter subjects as one aggregate,
then runs small independent capture/shift/update transactions.  It does not
claim equivalence of the complete Rocket-Chip JTAG parent.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import py_compile
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from amaranth.sim import Settle, Simulator, Tick


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Dependency.Rocket.Jtag-Hardware.py"
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
WORK = ROOT / "validation/.work/v2-jtag-family"
EVIDENCE = ROOT / "validation/v2-jtag-family-results.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
MEMBERS = ("CaptureChain", "CaptureUpdateChain", "CaptureUpdateChain_1", "CaptureUpdateChain_2", "JtagBypassChain")


# Hash exact bytes for reproducible evidence. / 对原始字节计算可复现摘要。
def digest(data: bytes) -> str:
    """Return a SHA-256 digest. / 返回 SHA-256 摘要。"""

    return hashlib.sha256(data).hexdigest()


# Load the Build through an exact path. / 通过精确路径加载 Build。
def load_target() -> Any:
    """Load the local JTAG aggregate. / 加载本地 JTAG 聚合模块。"""

    spec = importlib.util.spec_from_file_location("v2_jtag_family_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Parse a locked width token. / 解析锁定端口位宽记号。
def width(token: str) -> int:
    """Convert ``[high:low]`` to a bit count. / 将 ``[high:low]`` 转换为位数。"""

    match = re.search(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", token)
    return abs(int(match.group(1)) - int(match.group(2))) + 1 if match else 1


# Run one command in WSL and retain a bounded log tail. / 在 WSL 中运行命令并保留有限日志尾部。
def run_wsl(command: list[str]) -> dict[str, Any]:
    """Run a deterministic WSL tool command. / 执行确定性的 WSL 工具命令。"""

    rendered = " ".join(shlex.quote(item) for item in command)
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered], capture_output=True, check=False)
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {"command": command, "returncode": result.returncode,
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "output_tail": output[-1200:], "output_sha256": digest(output.encode())}


# Convert a Windows path to a WSL path. / 将 Windows 路径转换为 WSL 路径。
def wsl_path(path: Path) -> str:
    """Return the absolute WSL path for ``path``. / 返回路径的绝对 WSL 表示。"""

    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)], capture_output=True, check=True)
    return result.stdout.decode("utf-8", "replace").strip()


# Exercise one member's registered state machine. / 检查一个成员的寄存移位行为。
def direct_member(module: Any, member: str) -> dict[str, Any]:
    """Run representative capture/shift/update vectors. / 运行代表性捕获、移位与更新向量。"""

    dut = module.JtagShifterFamily(member)
    observed: list[dict[str, int]] = []

    def process():
        p = dut.ports
        yield p["io_chainIn_shift"].eq(0)
        yield p["io_chainIn_data"].eq(0)
        yield p["io_chainIn_update"].eq(0)
        yield p["io_chainIn_capture"].eq(0)
        if member == "CaptureChain":
            yield p["io_capture_bits_version"].eq(0xA)
            yield p["io_capture_bits_partNumber"].eq(0x1234)
            yield p["io_capture_bits_mfrId"].eq(0x345)
        elif member == "CaptureUpdateChain":
            yield p["io_capture_bits_dmiStatus"].eq(2)
        elif member == "CaptureUpdateChain_1":
            yield p["io_capture_bits_addr"].eq(0x45)
            yield p["io_capture_bits_data"].eq(0x89ABCDEF)
            yield p["io_capture_bits_resp"].eq(2)
        yield p["io_chainIn_capture"].eq(1)
        yield Tick()
        yield Settle()
        observed.append({"capture_data": int((yield p["io_chainOut_data"]))})
        yield p["io_chainIn_capture"].eq(0)
        yield p["io_chainIn_update"].eq(1)
        yield Settle()
        row = {"update_valid": int((yield p.get("io_update_valid", p["io_chainOut_data"]))) }
        if "io_update_bits_dmireset" in p:
            row["update_bits"] = int((yield p["io_update_bits_dmireset"]))
        if "io_update_bits" in p:
            row["update_bits"] = int((yield p["io_update_bits"]))
        if "io_update_bits_addr" in p:
            row["update_addr"] = int((yield p["io_update_bits_addr"]))
            row["update_data"] = int((yield p["io_update_bits_data"]))
            row["update_op"] = int((yield p["io_update_bits_op"]))
        if "io_capture_capture" in p:
            row["capture_pulse"] = int((yield p["io_capture_capture"]))
        observed.append(row)
        yield p["io_chainIn_update"].eq(0)
        yield p["io_chainIn_shift"].eq(1)
        yield p["io_chainIn_data"].eq(1)
        yield Tick()
        yield Settle()
        observed.append({"shifted_data": int((yield p["io_chainOut_data"]))})

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_process(process)
    sim.run()
    if len(observed) != 3:
        raise AssertionError((member, observed))
    if member == "CaptureChain" and observed[0]["capture_data"] != 1:
        raise AssertionError((member, observed))
    if member == "CaptureUpdateChain" and observed[1].get("update_bits") != 0:
        raise AssertionError((member, observed))
    if member == "CaptureUpdateChain_1" and observed[1].get("update_addr") != 0x45:
        raise AssertionError((member, observed))
    if member == "CaptureUpdateChain_2" and observed[1].get("update_bits") != 0:
        raise AssertionError((member, observed))
    if member == "JtagBypassChain" and observed[2]["shifted_data"] != 1:
        raise AssertionError((member, observed))
    return {"member": member, "vectors": 3, "observations": observed}


def main() -> int:
    """Run contract, direct, and tool gates. / 运行契约、直接行为与工具门禁。"""

    module = load_target()
    hierarchy = json.loads(HIERARCHY.read_text(encoding="utf-8"))["modules"]
    ports: dict[str, Any] = {}
    failures: list[str] = []
    for member in MEMBERS:
        node = hierarchy.get(member)
        if node is None:
            failures.append(f"missing hierarchy member {member}")
            continue
        expected = {(p["name"], p["direction"], width(str(p.get("width", "")))) for p in node["ports"]}
        actual = set(module.PORT_SPECS[member])
        if expected != actual:
            failures.append(f"port mismatch {member}")
        ports[member] = {"locked": len(expected), "emitted": len(actual), "match": expected == actual}
    py_compile.compile(str(TARGET), doraise=True)
    direct = [direct_member(module, member) for member in MEMBERS]

    WORK.mkdir(parents=True, exist_ok=True)
    tools: dict[str, Any] = {}
    for member in MEMBERS:
        rtl = module.build_verilog({"module": member}, {})
        path = WORK / f"{member}.sv"
        path.write_text(rtl, encoding="utf-8", newline="\n")
        wsl = wsl_path(path)
        tools[member] = {
            "verilator": run_wsl(["verilator", "--lint-only", "-Wno-fatal", wsl]),
            "yosys": run_wsl(["yosys", "-Q", "-p", f"read_verilog -sv {wsl}; hierarchy -top {member}; proc; check"]),
            "rtl_bytes": len(rtl.encode()), "rtl_sha256": digest(rtl.encode()),
        }
        if tools[member]["verilator"]["status"] != "PASS" or tools[member]["yosys"]["status"] != "PASS":
            failures.append(f"tool gate {member}")
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_JTAG_SHIFTER_FAMILY",
        "batch_id": "V2-DEPENDENCY-JTAG-001",
        "source_commit": SOURCE_COMMIT,
        "scala_sources": ["upstream/rocket-chip/src/main/scala/jtag/JtagShifter.scala"],
        "covered_modules": list(MEMBERS), "port_surface": ports,
        "direct": {"status": "PASS" if not failures else "FAIL", "members": direct},
        "tool_gates": tools,
        "gates": {
            "PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": "PASS" if not failures else "FAIL",
            "V2_REFERENCE_MATCHED": "PENDING_LOCKED_JTAG_PARENT_DIFF",
            "VERILATOR": "PASS" if not failures else "FAIL",
            "YOSYS": "PASS" if not failures else "FAIL",
            "UHSC_LOCALIZED": "PASS_BOUNDED_FAMILY_LOCAL_NAME",
            "PARENT_CLOSURE_MATCHED": "PENDING", "LICENSE_REVIEW": "PENDING", "ACCEPTED": "NOT_ALLOWED",
        },
        "status": "VALIDATOR_PASS_BOUNDED" if not failures else "VALIDATOR_FAIL",
        "acceptance_eligible": False,
        "failures": failures,
        "unclosed": ["Complete JTAG parent and locked XSTop differential remain pending.", "License review and user approval remain pending."],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "covered": len(MEMBERS), "failures": failures}))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
