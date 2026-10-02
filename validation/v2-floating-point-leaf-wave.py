"""Focused reproducible checks for implemented floating-point leaves."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import py_compile
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Cpu-Core-Backend.Fu.FloatingPoint.Family-Hardware.py"
TEST = ROOT / "python/Program-System/System-Testing/Testing-Cpu/Testing-Cpu-Backend.Fu.FloatingPoint.Family-Hardware.py"
DIRECT_RUNNER = ROOT / "validation/v2_direct_test_runner.py"
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
REFERENCE = ROOT / "validation/reference-sv"
WORK = ROOT / "validation/.work/v2-floating-point-leaf-wave"
EVIDENCE = ROOT / "validation/v2-floating-point-leaf-wave-results.json"
BOOTH_TB = ROOT / "validation/v2-floating-point-booth-diff-tb.sv"
ARRAY_TB = ROOT / "validation/v2-floating-point-array-diff-tb.sv"
MEMBERS = (
    "FloatAdder", "FloatAdderF32F16MixedPipeline", "FloatAdderF64Pipeline",
    "FloatDivider", "FloatDividerR64", "FloatFMA", "fpdiv_r64_block",
    "fpsqrt_r16", "BoothEncoderF64F32F16", "ArrayMulDataModule", "IntToFPDataModule",
)
IMPLEMENTED = ("BoothEncoderF64F32F16", "ArrayMulDataModule")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_build() -> Any:
    spec = importlib.util.spec_from_file_location("fp_leaf_wave_build", BUILD)
    if spec is None or spec.loader is None:
        raise RuntimeError(BUILD)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def width(value: str) -> int:
    match = re.search(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", value)
    return abs(int(match.group(1)) - int(match.group(2))) + 1 if match else 1


def command_result(command: list[str], timeout: int = 300) -> dict[str, Any]:
    try:
        result = subprocess.run(command, capture_output=True, check=False, timeout=timeout)
        output = (result.stdout + result.stderr).decode("utf-8", "replace")
        return {"status": "PASS" if result.returncode == 0 else "FAIL",
                "returncode": result.returncode, "output_tail": output[-2000:]}
    except subprocess.TimeoutExpired as error:
        return {"status": "TIMEOUT", "returncode": None,
                "output_tail": str(error)[:2000]}


def wsl_path(path: Path) -> str:
    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                            capture_output=True, check=True)
    return result.stdout.decode("utf-8", "replace").strip()


def wsl(command: list[str], timeout: int = 300) -> dict[str, Any]:
    return command_result(["wsl.exe", "-e", "bash", "-lc", shlex.join(command)], timeout)


def differential(top: str, reference_files: list[Path], dut: Path, testbench: Path,
                 work_name: str) -> dict[str, Any]:
    obj = f"/tmp/{work_name}"
    log = WORK / f"{work_name}.build.log"
    linux_inputs = [wsl_path(path) for path in reference_files + [dut, testbench]]
    linux_log = wsl_path(log)
    cmd = ["verilator", "--binary", "-Wno-fatal", "--top-module", top,
           "-Mdir", obj, *linux_inputs]
    # Keep the C++ build log out of the user-facing output while preserving it
    # as ignored diagnostic evidence for a failed run.
    shell = f"{shlex.join(cmd)} > {shlex.quote(linux_log)} 2>&1 && {shlex.quote(obj + '/V' + top)}"
    return command_result(["wsl.exe", "-e", "bash", "-lc", shell], timeout=600)


def main() -> int:
    sys.path.insert(0, str(ROOT / "validation"))
    import v2_strict_family_rail as strict_rail

    WORK.mkdir(parents=True, exist_ok=True)
    module = load_build()
    hierarchy = json.loads(HIERARCHY.read_text(encoding="utf-8"))["modules"]
    failures: list[str] = []

    py_compile.compile(str(BUILD), doraise=True)
    py_compile.compile(str(TEST), doraise=True)
    pyright = shutil.which("pyright")
    pyright_cmd = ["powershell.exe", "-NoProfile", "-Command",
                   f"pyright '{BUILD}' '{TEST}'"] if pyright else []
    pyright_result = command_result(pyright_cmd) if pyright_cmd else {
        "status": "UNAVAILABLE", "returncode": None, "output_tail": "pyright not found"}
    if pyright_result["status"] != "PASS":
        failures.append("pyright")

    direct = command_result([sys.executable, "-B", str(DIRECT_RUNNER), "--test",
                             str(TEST.relative_to(ROOT)), "--minimum-tests", "4"], timeout=180)
    test_count = 0
    match = re.search(r"Ran\s+(\d+) tests?", str(direct.get("output_tail", "")))
    if match:
        test_count = int(match.group(1))
    if direct["status"] != "PASS" or test_count < 4:
        failures.append("direct_test")

    if module.COVERED_MODULES != MEMBERS:
        failures.append("member_inventory")
    if module.IMPLEMENTED_MEMBERS != IMPLEMENTED:
        failures.append("implemented_member_inventory")

    from v2_strict_family_rail import declared_ports

    member_results: dict[str, Any] = {}
    for member in MEMBERS:
        locked_ports = {
            (port["name"], port["direction"], width(str(port.get("width", ""))))
            for port in hierarchy[member]["ports"]
        }
        declared = set(module.PORT_SPECS[member])
        first = module.build_verilog({"module": member}, {})
        second = module.build_verilog({"module": member}, {})
        rtl = first
        abi = declared == locked_ports and declared_ports(rtl, member) == {
            port: (direction, bits) for port, direction, bits in locked_ports
        }
        deterministic = first == second
        rtl_path = WORK / f"{member}.sv"
        rtl_path.write_text(rtl, encoding="utf-8", newline="\n")
        linux_rtl = wsl_path(rtl_path)
        verilator = wsl(["verilator", "--lint-only", "-Wno-fatal", linux_rtl])
        yosys = wsl(["yosys", "-Q", "-p", f"read_verilog -sv {shlex.quote(linux_rtl)}; proc; check"])
        member_results[member] = {
            "abi_exact": abi,
            "deterministic": deterministic,
            "rtl_bytes": len(rtl.encode("utf-8")),
            "rtl_sha256": hashlib.sha256(rtl.encode("utf-8")).hexdigest(),
            "verilator": verilator,
            "yosys": yosys,
        }
        if not abi:
            failures.append(f"abi:{member}")
        if not deterministic:
            failures.append(f"determinism:{member}")
        if verilator["status"] != "PASS":
            failures.append(f"verilator:{member}")
        if yosys["status"] != "PASS":
            failures.append(f"yosys:{member}")

    booth_dut = WORK / "BoothDut.sv"
    booth_dut.write_text(
        (WORK / "BoothEncoderF64F32F16.sv").read_text(encoding="utf-8").replace(
            "module BoothEncoderF64F32F16(", "module BoothDut(", 1),
        encoding="utf-8", newline="\n")
    array_dut = WORK / "ArrayMulDut.sv"
    array_dut.write_text(
        (WORK / "ArrayMulDataModule.sv").read_text(encoding="utf-8").replace(
            "module ArrayMulDataModule(", "module ArrayMulDut(", 1),
        encoding="utf-8", newline="\n")

    array_closure, array_children, array_audits = strict_rail.locked_closure("ArrayMulDataModule")
    closure_path = WORK / "ArrayMulDataModule.locked-closure.sv"
    closure_path.write_text(array_closure, encoding="utf-8", newline="\n")
    array_ref_files = [REFERENCE / "ArrayMulDataModule.sv"] + [REFERENCE / f"{name}.sv" for name in array_children]
    array_closure_trusted = bool(array_audits) and all(item["view_trusted"] for item in array_audits)
    booth_diff = differential(
        "booth_diff_tb", [REFERENCE / "BoothEncoderF64F32F16.sv"],
        booth_dut, BOOTH_TB, "v2_fp_booth_leaf_diff",
    )
    array_diff = differential(
        "array_locked_diff_tb", [closure_path], array_dut,
        ARRAY_TB, "v2_fp_array_mul_leaf_diff",
    )
    if not array_closure_trusted:
        failures.append("array_locked_closure_view")
    if booth_diff["status"] != "PASS" or "BOOTH_DIFF_PASS" not in str(booth_diff["output_tail"]):
        failures.append("booth_locked_diff")
    if array_diff["status"] != "PASS" or "ARRAY_LOCKED_DIFF_PASS" not in str(array_diff["output_tail"]):
        failures.append("array_locked_diff")

    base_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                 capture_output=True, check=False).stdout.decode().strip()
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_FLOATING_POINT_LEAF_WAVE",
        "status": "VALIDATOR_PASS_BOUNDED" if not failures else "VALIDATOR_FAIL",
        "acceptance_eligible": False,
        "formal": "NOT_RUN_COORDINATOR_SERIAL",
        "base_commit": base_commit,
        "candidate_hashes": {
            "build_sha256": sha256(BUILD),
            "direct_test_sha256": sha256(TEST),
            "direct_runner_sha256": sha256(DIRECT_RUNNER),
            "validator_sha256": sha256(Path(__file__)),
        },
        "tool_gates": {
            "PY_COMPILE": "PASS",
            "PYRIGHT": pyright_result,
            "DIRECT_TEST": {**direct, "tests_run": test_count},
        },
        "members": member_results,
        "locked_behavior": {
            "BoothEncoderF64F32F16": {
                "status": "PASS_BOUNDED" if booth_diff["status"] == "PASS" else "FAIL",
                "vectors": 256,
                "selectors": ["f16", "f32", "f64", "f64_priority_when_both_selectors_set"],
                "reference_sha256": sha256(REFERENCE / "BoothEncoderF64F32F16.sv"),
                "testbench_sha256": sha256(BOOTH_TB),
                "result": booth_diff,
            },
            "ArrayMulDataModule": {
                "status": "PASS_BOUNDED" if array_diff["status"] == "PASS" else "FAIL",
                "vectors": 69,
                "children": array_children,
                "closure_sha256": hashlib.sha256(array_closure.encode("utf-8")).hexdigest(),
                "closure_view_trusted": array_closure_trusted,
                "closure_audits": array_audits,
                "reference_file_hashes": {path.name: sha256(path) for path in array_ref_files},
                "testbench_sha256": sha256(ARRAY_TB),
                "result": array_diff,
            },
        },
        "failures": failures,
        "remaining": [
            "SAT/formal equivalence and negative controls remain for the serialized coordinator rail.",
            "Complete floating-point family still contains CONTRACT_ONLY members.",
            "Parent closure, license review, and acceptance remain pending.",
        ],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "direct_tests": test_count,
                      "members": len(member_results), "failures": failures}))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
