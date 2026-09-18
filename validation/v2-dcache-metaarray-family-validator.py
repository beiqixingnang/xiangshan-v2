"""Bounded validator for the V2 asynchronous DCache metadata arrays.
V2 异步 DCache 元数据阵列的有界校验器。

The four locked members are checked as one family.  Port surfaces are derived
from the pinned hierarchy, while direct vectors cover write-enable selection
and registered read timing.  This is not a full DCache parent differential.
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
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Memory.Dcache.MetaArray-Hardware.py"
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
WORK = ROOT / "validation/.work/v2-dcache-metaarray"
EVIDENCE = ROOT / "validation/v2-dcache-metaarray-family-results.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
MEMBERS = ("L1CohMetaArray", "L1ErrorMetaArray", "L1FlagMetaArray", "L1PrefetchSourceArray")


# Hash bytes exactly. / 对字节原样计算摘要。
def digest(data: bytes) -> str:
    """Return SHA-256. / 返回 SHA-256。"""

    return hashlib.sha256(data).hexdigest()


# Load the exact Build module. / 加载精确 Build 模块。
def load_target() -> Any:
    """Load the local metadata-array aggregate. / 加载本地元数据阵列聚合。"""

    spec = importlib.util.spec_from_file_location("v2_dcache_metaarray_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Parse locked widths. / 解析锁定位宽。
def width(token: str) -> int:
    """Return the width of an ANSI range. / 返回 ANSI 范围位宽。"""

    match = re.search(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", token)
    return abs(int(match.group(1)) - int(match.group(2))) + 1 if match else 1


# Run one WSL command with bounded output. / 运行一条 WSL 命令并限制输出。
def run_wsl(command: list[str]) -> dict[str, Any]:
    """Run a tool command in WSL. / 在 WSL 中运行工具命令。"""

    rendered = " ".join(shlex.quote(item) for item in command)
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered], capture_output=True, check=False)
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {"command": command, "returncode": result.returncode,
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "output_tail": output[-1200:], "output_sha256": digest(output.encode())}


# Convert a Windows path to WSL without locale decoding. / 将 Windows 路径转换为 WSL，避免本地编码解码。
def wsl_path(path: Path) -> str:
    """Return an absolute WSL path. / 返回绝对 WSL 路径。"""

    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)], capture_output=True, check=True)
    return result.stdout.decode("utf-8", "replace").strip()


# Exercise one member with deterministic write/read vectors. / 用确定性写读向量检查一个成员。
def direct_member(module: Any, member: str) -> dict[str, Any]:
    """Run a bounded direct transaction. / 运行有界直接事务。"""

    dut = module.DcacheMetaArrayFamily(member)
    p = dut.ports
    observed: list[dict[str, int]] = []
    inputs = {name for name, direction, _width in dut.specs if direction == "input"}

    def process():
        for name, signal in p.items():
            if name in inputs and name not in {"clock", "reset"}:
                yield signal.eq(0)
        # First write one way, then issue a read for the same set. /
        # 先写入一路，再读取同一集合。
        yield p["io_write_0_valid"].eq(1)
        yield p["io_write_0_bits_idx"].eq(3)
        yield p["io_write_0_bits_way_en"].eq(1)
        if member == "L1CohMetaArray":
            yield p["io_write_0_bits_meta_coh_state"].eq(2)
        elif member == "L1ErrorMetaArray":
            yield p["io_write_0_bits_error_tl_denied"].eq(1)
            yield p["io_write_0_bits_error_tl_corrupt"].eq(1)
        elif member == "L1FlagMetaArray":
            yield p["io_write_3_valid"].eq(1)
            yield p["io_write_3_bits_idx"].eq(3)
            yield p["io_write_3_bits_way_en"].eq(1)
            yield p["io_write_3_bits_flag"].eq(1)
        else:
            yield p["io_write_3_bits_source"].eq(5)
        yield Tick()
        yield p["io_write_0_valid"].eq(0)
        if member == "L1PrefetchSourceArray":
            yield p["io_write_3_valid"].eq(1)
            yield p["io_write_3_bits_idx"].eq(3)
            yield p["io_write_3_bits_way_en"].eq(1)
            yield p["io_write_3_bits_source"].eq(5)
            yield Tick()
            yield p["io_write_3_valid"].eq(0)
        read = 0 if member != "L1FlagMetaArray" else 3
        yield p[f"io_read_{read}_valid"].eq(1)
        yield p[f"io_read_{read}_bits_idx"].eq(3)
        yield Tick()
        yield Settle()
        row: dict[str, int] = {}
        if member == "L1CohMetaArray":
            row["way0"] = int((yield p["io_resp_0_0_coh_state"]))
        elif member == "L1ErrorMetaArray":
            row["denied"] = int((yield p["io_resp_0_0_tl_denied"]))
            row["corrupt"] = int((yield p["io_resp_0_0_tl_corrupt"]))
        elif member == "L1FlagMetaArray":
            row["way0"] = int((yield p["io_resp_3_0"]))
        else:
            row["way0"] = int((yield p["io_resp_0_0"]))
        observed.append(row)

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_process(process)
    sim.run()
    if member == "L1CohMetaArray" and observed[0]["way0"] != 2:
        raise AssertionError((member, observed))
    if member == "L1ErrorMetaArray" and observed[0] != {"denied": 1, "corrupt": 1}:
        raise AssertionError((member, observed))
    if member == "L1FlagMetaArray" and observed[0]["way0"] != 1:
        raise AssertionError((member, observed))
    if member == "L1PrefetchSourceArray" and observed[0]["way0"] != 5:
        raise AssertionError((member, observed))
    return {"member": member, "vectors": 2, "observations": observed}


def main() -> int:
    """Run the family gates. / 运行 family 门禁。"""

    module = load_target()
    hierarchy = json.loads(HIERARCHY.read_text(encoding="utf-8"))["modules"]
    failures: list[str] = []
    surface: dict[str, Any] = {}
    for member in MEMBERS:
        expected = {(p["name"], p["direction"], width(str(p.get("width", "")))) for p in hierarchy[member]["ports"]}
        actual = set(module.PORT_SPECS[member])
        surface[member] = {"locked": len(expected), "emitted": len(actual), "match": expected == actual}
        if expected != actual:
            failures.append(f"port mismatch {member}")
    py_compile.compile(str(TARGET), doraise=True)
    direct = [direct_member(module, member) for member in MEMBERS]
    WORK.mkdir(parents=True, exist_ok=True)
    tools: dict[str, Any] = {}
    for member in MEMBERS:
        rtl = module.build_verilog({"module": member}, {})
        path = WORK / f"{member}.sv"
        path.write_text(rtl, encoding="utf-8", newline="\n")
        wsl = wsl_path(path)
        tools[member] = {"verilator": run_wsl(["verilator", "--lint-only", "-Wno-fatal", wsl]),
                         "yosys": run_wsl(["yosys", "-Q", "-p", f"read_verilog -sv {wsl}; hierarchy -top {member}; proc; check"]),
                         "rtl_bytes": len(rtl.encode()), "rtl_sha256": digest(rtl.encode())}
        if tools[member]["verilator"]["status"] != "PASS" or tools[member]["yosys"]["status"] != "PASS":
            failures.append(f"tool gate {member}")
    payload = {
        "schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_DCACHE_METAARRAY_FAMILY",
        "batch_id": "V2-MEMORY-DCACHE-METAARRAY-001", "source_commit": SOURCE_COMMIT,
        "scala_sources": ["upstream/src/main/scala/xiangshan/cache/dcache/meta/AsynchronousMetaArray.scala"],
        "covered_modules": list(MEMBERS), "port_surface": surface,
        "direct": {"status": "PASS" if not failures else "FAIL", "members": direct},
        "tool_gates": tools,
        "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": "PASS" if not failures else "FAIL",
                  "V2_REFERENCE_MATCHED": "PENDING_LOCKED_DCACHE_PARENT_DIFF", "VERILATOR": "PASS" if not failures else "FAIL",
                  "YOSYS": "PASS" if not failures else "FAIL", "UHSC_LOCALIZED": "PASS_BOUNDED_FAMILY_LOCAL_NAME",
                  "PARENT_CLOSURE_MATCHED": "PENDING", "LICENSE_REVIEW": "PENDING", "ACCEPTED": "NOT_ALLOWED"},
        "status": "VALIDATOR_PASS_BOUNDED" if not failures else "VALIDATOR_FAIL", "acceptance_eligible": False,
        "failures": failures,
        "unclosed": ["Complete DCache parent and locked XSTop differential remain pending.", "License review and user approval remain pending."],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "covered": len(MEMBERS), "failures": failures}))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
