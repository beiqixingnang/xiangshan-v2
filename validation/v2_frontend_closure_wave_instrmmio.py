"""Focused V2 instruction-MMIO closure wave validator. / V2 指令 MMIO 闭包波验证器。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import py_compile
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Cpu-Core-Frontend.Icache.InstrMMIOEntry-Hardware.py"
)
DIRECT_TEST = ROOT / "validation/v2_frontend_instr_mmio_entry_child_differential.py"
SCALA = ROOT / "upstream/src/main/scala/xiangshan/frontend/icache/InstrUncache.scala"
REFERENCE = ROOT / "validation/reference-sv/InstrMMIOEntry.sv"
EVIDENCE = ROOT / "validation/v2-frontend-closure-wave-instrmmio.json"
LOCKED_CANONICAL = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
LOCKED_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
LOCKED_BYTES = 228590583
WORK = ROOT / "validation/.work/v2-frontend-closure-wave-instrmmio"


def sha256_bytes(payload: bytes) -> str:
    """Return one deterministic SHA-256 digest. / 返回确定性的 SHA-256 摘要。"""
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash a repository file without changing it. / 只读计算仓库文件摘要。"""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_target() -> Any:
    """Load the exact Build path under test. / 加载精确 Build 测试路径。"""
    spec = importlib.util.spec_from_file_location("v2_closure_instrmmio_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load target: {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def wsl_path(path: Path) -> str:
    """Convert a Windows path for the WSL tool boundary. / 转换 WSL 工具边界路径。"""
    result = subprocess.run(
        ["wsl.exe", "-e", "wslpath", "-a", str(path.resolve())],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", "replace"))
    return result.stdout.decode("utf-8", "replace").strip()


def run_wsl(command: list[str]) -> dict[str, Any]:
    """Run one bounded WSL tool command and preserve its digest. / 运行 WSL 工具并保存摘要。"""
    result = subprocess.run(
        ["wsl.exe", "-e", "bash", "-lc", " ".join(shlex.quote(item) for item in command)],
        capture_output=True,
        check=False,
    )
    output = result.stdout + result.stderr
    return {
        "command": command,
        "returncode": result.returncode,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "output_sha256": sha256_bytes(output),
        "output_tail": output.decode("utf-8", "replace")[-2000:],
    }


def locked_xstop_check() -> dict[str, Any]:
    """Verify the immutable WSL XSTop artifact identity. / 核验不可变 WSL XSTop 身份。"""
    result = run_wsl(["sha256sum", LOCKED_CANONICAL])
    stat = run_wsl(["stat", "-c%s", LOCKED_CANONICAL])
    observed_hash = str(result["output_tail"]).split()[0] if result["returncode"] == 0 else ""
    observed_size_text = str(stat["output_tail"]).strip().splitlines()[0] if stat["returncode"] == 0 else ""
    try:
        observed_size = int(observed_size_text)
    except ValueError:
        observed_size = -1
    passed = (
        result["returncode"] == 0
        and stat["returncode"] == 0
        and observed_hash == LOCKED_SHA256
        and observed_size == LOCKED_BYTES
    )
    return {
        "canonical_path": LOCKED_CANONICAL,
        "expected_sha256": LOCKED_SHA256,
        "observed_sha256": observed_hash,
        "expected_bytes": LOCKED_BYTES,
        "observed_bytes": observed_size,
        "sha256_command": result,
        "size_command": stat,
        "status": "PASS" if passed else "FAIL",
    }


def run_direct_test() -> dict[str, Any]:
    """Run the real direct test and consume its machine result. / 运行真实 direct 测试并读取结果。"""
    result = subprocess.run(
        [sys.executable, "-B", str(DIRECT_TEST.relative_to(ROOT))],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    payload: dict[str, Any] = {}
    result_file = ROOT / "validation/v2-frontend-instr-mmio-entry-child-differential-results.json"
    if result_file.is_file():
        try:
            parsed = json.loads(result_file.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            payload = {}
    return {
        "command": [sys.executable, "-B", str(DIRECT_TEST.relative_to(ROOT))],
        "returncode": result.returncode,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "stdout_tail": result.stdout.decode("utf-8", "replace")[-2000:],
        "stderr_tail": result.stderr.decode("utf-8", "replace")[-2000:],
        "result_status": payload.get("status"),
        "direct": payload.get("direct"),
        "differential": payload.get("differential"),
        "tool_gates": payload.get("tool_gates"),
    }


def direct_export_and_abi(module: Any) -> tuple[str, dict[str, Any]]:
    """Check same-name deterministic export and exact reference ABI. / 核验同名确定性导出与精确 ABI。"""
    first = module.build_verilog(None, {})
    second = module.build_verilog(None, {})
    first_bytes = first.encode("utf-8")
    second_bytes = second.encode("utf-8")
    strict_validator = ROOT / "validation/v2_instrmmioentry_strict_validator.py"
    spec = importlib.util.spec_from_file_location("v2_existing_instrmmio_strict", strict_validator)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load ABI parser")
    parser_module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = parser_module
    spec.loader.exec_module(parser_module)
    reference_ports = parser_module.declared_ports(REFERENCE.read_text(encoding="utf-8"), "InstrMMIOEntry")
    target_ports = parser_module.declared_ports(first, "InstrMMIOEntry")
    abi_ok = target_ports == reference_ports and "module InstrMMIOEntry(" in first
    return first, {
        "status": "PASS" if first_bytes == second_bytes and abi_ok else "FAIL",
        "bytes": len(first_bytes),
        "sha256": sha256_bytes(first_bytes),
        "repeat_sha256": sha256_bytes(second_bytes),
        "byte_equal": first_bytes == second_bytes,
        "abi": {
            "status": "PASS" if abi_ok else "FAIL",
            "target_ports": {key: list(value) for key, value in sorted(target_ports.items())},
            "reference_ports": {key: list(value) for key, value in sorted(reference_ports.items())},
            "exact_surface": abi_ok,
        },
    }


def main() -> int:
    """Run the closure wave and write explicit implementation status. / 运行闭包波并写出明确实现状态。"""
    WORK.mkdir(parents=True, exist_ok=True)
    module = load_target()
    py_compile.compile(str(TARGET), doraise=True)
    py_compile.compile(str(DIRECT_TEST), doraise=True)
    target_rtl, export = direct_export_and_abi(module)
    target_path = WORK / "InstrMMIOEntry-target.sv"
    target_path.write_text(target_rtl, encoding="utf-8", newline="\n")
    target_wsl = wsl_path(target_path)
    verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal", target_wsl])
    yosys = run_wsl([
        "yosys", "-Q", "-p",
        f"read_verilog -sv {target_wsl}; hierarchy -top InstrMMIOEntry; proc; check; stat",
    ])
    direct = run_direct_test()
    xstop = locked_xstop_check()
    source_status = {
        "scala_path": str(SCALA.relative_to(ROOT)).replace("\\", "/"),
        "scala_sha256": sha256_file(SCALA),
        "reference_path": str(REFERENCE.relative_to(ROOT)).replace("\\", "/"),
        "reference_sha256": sha256_file(REFERENCE),
        "status": "PASS" if SCALA.is_file() and REFERENCE.is_file() else "FAIL",
    }
    gate_pass = all([
        export["status"] == "PASS",
        direct["returncode"] == 0,
        direct.get("result_status") == "PASS_BOUNDED_INSTR_MMIO_ENTRY_CHILD",
        verilator["status"] == "PASS",
        yosys["status"] == "PASS",
        xstop["status"] == "PASS",
        source_status["status"] == "PASS",
    ])
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_FRONTEND_CLOSURE_WAVE_INSTR_MMIO",
        "batch_id": "V2-FRONTEND-CLOSURE-WAVE-INSTR-MMIO-001",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "validator": {
            "path": str(Path(__file__).relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256_file(Path(__file__)),
            "bytes": Path(__file__).stat().st_size,
        },
        "target": {
            "path": str(TARGET.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256_file(TARGET),
            "bytes": TARGET.stat().st_size,
        },
        "implementation_status": "IMPLEMENTED" if gate_pass else "CONTRACT_ONLY",
        "strict_status": "STRICT_PENDING",
        "acceptance_eligible": False,
        "locked_xstop": xstop,
        "sources": source_status,
        "gates": {
            "PY_COMPILE": "PASS",
            "DETERMINISTIC_SAME_NAME_EXPORT": export,
            "ABI": export["abi"],
            "DIRECT": direct,
            "VERILATOR": verilator,
            "YOSYS": yosys,
            "STRICT_FORMAL": "STRICT_PENDING_COORDINATOR_RAIL",
            "PARENT_CLOSURE": "STRICT_PENDING",
            "LICENSE_REVIEW": "PENDING",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "behavior_scope": {
            "states": {"INVALID": 0, "REFILL_REQ": 1, "REFILL_RESP": 2, "SEND_RESP": 3},
            "transactions": [
                "request accepted only in INVALID",
                "A-channel valid waits for WFI and ready",
                "D-channel grant captures data/corrupt",
                "response lane selected by req_addr[2:1]",
                "flush suppresses response and clears on send state",
            ],
            "direct_vectors": direct.get("direct", {}).get("cycles"),
            "direct_checks": direct.get("direct", {}).get("checks"),
        },
        "unclosed": [
            "Coordinator strict formal rail was not rerun in this focused wave.",
            "InstrUncache/Frontend parent closure, license review, and user approval remain pending.",
        ],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({
        "implementation_status": payload["implementation_status"],
        "strict_status": payload["strict_status"],
        "direct": direct.get("returncode"),
        "verilator": verilator["returncode"],
        "yosys": yosys["returncode"],
        "xstop": xstop["status"],
    }, ensure_ascii=False, sort_keys=True))
    return 0 if gate_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
