"""Complete combinational equivalence validator for the V2 JumpDataModule leaf.

The miter leaves every input bit unconstrained and proves all three outputs,
so this is a complete input-space proof for the locked RV64 configuration,
not a bounded vector checkpoint.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import platform
import py_compile
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Build-Cpu.Backend.Fu.JumpDataModule-Hardware.py"
)
SCALA = ROOT / "upstream/src/main/scala/xiangshan/backend/fu/Jump.scala"
REFERENCE = ROOT / "validation/reference-closures/JumpDataModule-v2.sv"
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_jumpdatamodule_strict"
EVIDENCE = ROOT / "validation/v2-jumpdatamodule-strict-evidence.json"

INPUT_WIDTHS = {
    "io_src": 64,
    "io_pc": 64,
    "io_imm": 33,
    "io_nextPcOffset": 5,
    "io_func": 9,
}
OUTPUT_WIDTHS = {"io_result": 64, "io_target": 64, "io_isAuipc": 1}
INPUT_BITS = sum(INPUT_WIDTHS.values())


# Hash exact source/artifact bytes for reproducible evidence.
def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# Load only the selected Build module by exact path.
def load_target() -> Any:
    """Load the JumpDataModule Build."""

    spec = importlib.util.spec_from_file_location("strict_jump_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load target: {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Convert a Windows path to a WSL path using the platform bridge.
def wsl_path(path: Path) -> str:
    """Return the absolute WSL spelling of a Windows path."""

    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                            capture_output=True, check=True)
    return result.stdout.decode("utf-8", "replace").strip()


# Run one WSL tool command with exact shell quoting and bounded diagnostics.
def run_wsl(command: list[str]) -> dict[str, Any]:
    """Run a WSL command and return a stable machine-readable record."""

    rendered = " ".join(shlex.quote(item) for item in command)
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered],
                            capture_output=True, check=False)
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {
        "command": command,
        "returncode": result.returncode,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "output_tail": output[-3000:],
        "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
    }


# Record the exact backend tool versions used by the strict run.
def tool_versions() -> dict[str, Any]:
    """Collect Verilator and Yosys version records."""

    return {"verilator": run_wsl(["verilator", "--version"]),
            "yosys": run_wsl(["yosys", "--version"])}


# Run Pyright on a visible exact source copy (Pyright auto-excludes dot paths).
def pyright_check(source: Path) -> dict[str, Any]:
    """Run Pyright and retain the diagnostic summary."""

    temporary = Path(tempfile.mkdtemp(prefix="uhsc_jump_pyright_"))
    try:
        copied = temporary / source.name
        shutil.copyfile(source, copied)
        command = ["cmd.exe", "/d", "/c", "pyright", "--outputjson", str(copied)]
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", check=False)
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError:
            parsed = {}
        summary = parsed.get("summary", {}) if isinstance(parsed, dict) else {}
        passed = result.returncode == 0 and summary.get("errorCount") == 0
        return {
            "command": command,
            "returncode": result.returncode,
            "status": "PASS" if passed else "FAIL",
            "version": parsed.get("version") if isinstance(parsed, dict) else None,
            "files_analyzed": summary.get("filesAnalyzed"),
            "error_count": summary.get("errorCount"),
            "warning_count": summary.get("warningCount"),
            "output_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
            "stderr_tail": result.stderr[-1000:],
        }
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


# Generate the target twice and require exact byte identity.
def deterministic_export(module: Any) -> tuple[str, dict[str, Any]]:
    """Return one export and deterministic-export evidence."""

    first = module.build_verilog(None, {})
    second = module.build_verilog(None, {})
    first_bytes = first.encode("utf-8")
    second_bytes = second.encode("utf-8")
    return first, {
        "status": "PASS" if first_bytes == second_bytes else "FAIL",
        "bytes": len(first_bytes),
        "sha256": hashlib.sha256(first_bytes).hexdigest(),
        "repeat_sha256": hashlib.sha256(second_bytes).hexdigest(),
        "byte_equal": first_bytes == second_bytes,
    }


# Materialize renamed reference and a miter comparing every declared output.
def materialize_miter(target_rtl: str) -> dict[str, Path]:
    """Write target/reference/miter sources in an ASCII tool directory."""

    WORK.mkdir(parents=True, exist_ok=True)
    target = WORK / "UHSC_JumpDataModule.sv"
    reference = WORK / "REF_JumpDataModule.sv"
    miter = WORK / "JumpDataModule_MITER.sv"
    target.write_text(target_rtl, encoding="utf-8", newline="\n")
    source = REFERENCE.read_text(encoding="utf-8")
    source = source.replace("module JumpDataModule(",
                            "module REF_JumpDataModule(", 1)
    reference.write_text(source, encoding="utf-8", newline="\n")
    miter.write_text(
        """module JumpDataModule_MITER(
  input [63:0] io_src,
  input [63:0] io_pc,
  input [32:0] io_imm,
  input [4:0] io_nextPcOffset,
  input [8:0] io_func,
  output mismatch
);
  wire [63:0] ref_result, ref_target, dut_result, dut_target;
  wire ref_auipc, dut_auipc;
  REF_JumpDataModule ref_i(
    .io_src(io_src), .io_pc(io_pc), .io_imm(io_imm),
    .io_nextPcOffset(io_nextPcOffset), .io_func(io_func),
    .io_result(ref_result), .io_target(ref_target), .io_isAuipc(ref_auipc));
  JumpDataModule dut_i(
    .io_src(io_src), .io_pc(io_pc), .io_imm(io_imm),
    .io_nextPcOffset(io_nextPcOffset), .io_func(io_func),
    .io_result(dut_result), .io_target(dut_target), .io_isAuipc(dut_auipc));
  assign mismatch = |(ref_result ^ dut_result)
                  | |(ref_target ^ dut_target)
                  | (ref_auipc ^ dut_auipc);
endmodule
""",
        encoding="utf-8", newline="\n")
    return {"target": target, "reference": reference, "miter": miter}


# Run lint, synthesis, and the unrestricted SAT miter proof.
def formal_gates(paths: dict[str, Path]) -> dict[str, Any]:
    """Run Verilator/Yosys gates and prove mismatch is impossible."""

    converted = {name: wsl_path(path) for name, path in paths.items()}
    target, reference, miter = (converted["target"], converted["reference"],
                                converted["miter"])
    verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal",
                         target, reference, miter])
    target_yosys = run_wsl(["yosys", "-Q", "-p",
                            f"read_verilog -sv {shlex.quote(target)}; "
                            "hierarchy -top JumpDataModule; proc; opt; check"])
    reference_yosys = run_wsl(["yosys", "-Q", "-p",
                               f"read_verilog -sv {shlex.quote(reference)}; "
                               "hierarchy -top REF_JumpDataModule; proc; opt; check"])
    proof_script = (
        f"read_verilog -sv {shlex.quote(target)} {shlex.quote(reference)} "
        f"{shlex.quote(miter)}; prep -top JumpDataModule_MITER; flatten; opt; "
        "sat -prove mismatch 0"
    )
    proof = run_wsl(["yosys", "-Q", "-p", proof_script])
    marker = "SAT proof finished - no model found: SUCCESS!"
    proof["formal_success_marker"] = marker in proof.get("output_tail", "")
    if not proof["formal_success_marker"]:
        proof["status"] = "FAIL"
    proof["formal_scope"] = {
        "input_bits": INPUT_BITS,
        "input_space": f"2**{INPUT_BITS}",
        "input_space_cardinality": str(1 << INPUT_BITS),
        "state_bits": 0,
        "state_space": "singleton (stateless combinational module)",
        "property": "mismatch == 0 for every 2-state input valuation",
    }
    return {
        "verilator": verilator,
        "yosys_target": target_yosys,
        "yosys_reference": reference_yosys,
        "yosys_formal_miter": proof,
    }


# Assemble evidence and refuse COMPLETE_EQUIVALENCE on any failed gate.
def validate() -> dict[str, Any]:
    """Run all gates and write the JumpDataModule evidence JSON."""

    module = load_target()
    py_compile.compile(str(TARGET), doraise=True)
    py_compile.compile(str(Path(__file__)), doraise=True)
    target_rtl, export = deterministic_export(module)
    gates = formal_gates(materialize_miter(target_rtl))
    pyright = {"target": pyright_check(TARGET),
               "validator": pyright_check(Path(__file__))}
    failures: list[str] = []
    if export["status"] != "PASS":
        failures.append("deterministic export mismatch")
    for name, result in pyright.items():
        if result["status"] != "PASS":
            failures.append(f"pyright {name}")
    for name, result in gates.items():
        if result["status"] != "PASS":
            failures.append(name)
    status = "COMPLETE_EQUIVALENCE" if not failures else "STRICT_PENDING"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_STRICT_COMPLETE_EQUIVALENCE",
        "build_id": "Build-Cpu.Backend.Fu.JumpDataModule",
        "validator": Path(__file__).relative_to(ROOT).as_posix(),
        "status": status,
        "strict_complete_eligible": status == "COMPLETE_EQUIVALENCE",
        "strict_complete_count_delta": 1 if status == "COMPLETE_EQUIVALENCE" else 0,
        "acceptance_eligible": status == "COMPLETE_EQUIVALENCE",
        "source_commit": "5fe0e8f3f77aa1cdb8523312cb222405bb6be8e5",
        "scope": {
            "kind": "stateless_combinational_leaf",
            "configuration": "locked RV64, imm=33 bits, nextPcOffset=5 bits, func=9 bits",
            "state_bits": 0,
            "state_boundary": "no clock/reset/register/memory; one combinational evaluation",
            "inputs": INPUT_WIDTHS,
            "outputs_compared": OUTPUT_WIDTHS,
            "input_bits": INPUT_BITS,
            "input_space": f"2**{INPUT_BITS}",
            "input_space_cardinality": str(1 << INPUT_BITS),
            "why_complete": (
                "Yosys SAT proves the three-output miter mismatch is zero with "
                "all 175 input bits unconstrained; no temporal state exists."
            ),
        },
        "sources": {
            "scala": {"path": SCALA.relative_to(ROOT).as_posix(),
                      "sha256": sha256_file(SCALA), "bytes": SCALA.stat().st_size},
            "reference_sv": {"path": REFERENCE.relative_to(ROOT).as_posix(),
                             "sha256": sha256_file(REFERENCE), "bytes": REFERENCE.stat().st_size,
                             "locked_module": "JumpDataModule",
                             "locked_xstop_sha256": "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d",
                             "locked_xstop_module_lines": [1198515, 1198531]},
            "python_build": {"path": TARGET.relative_to(ROOT).as_posix(),
                             "sha256": sha256_file(TARGET), "bytes": TARGET.stat().st_size},
        },
        "checks": {"python_version": platform.python_version(),
                    "py_compile": {"status": "PASS"},
                    "pyright": pyright, "deterministic_export": export,
                    "tools": tool_versions(), "formal": gates},
        "failures": failures,
        "unclosed": [] if not failures else ["strict gates did not all pass"],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    return payload


# Print a compact result and return nonzero while strict proof is pending.
def main() -> int:
    """Run validation and return its strict status."""

    payload = validate()
    print(json.dumps({"status": payload["status"],
                      "strict_complete_eligible": payload["strict_complete_eligible"],
                      "failures": payload["failures"]}, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
