"""Complete input-space equivalence validator for the V2 BranchModule leaf.

BranchModule is a stateless combinational Build.  The Yosys miter below leaves
all 138 input bits unconstrained and compares both observable outputs, making
the result a complete equivalence proof rather than a bounded vector test.
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
    "Build-Cpu.Backend.Fu.BranchModule-Hardware.py"
)
SCALA = ROOT / "upstream/src/main/scala/xiangshan/backend/fu/Branch.scala"
SCALA_SUB = ROOT / "upstream/src/main/scala/xiangshan/backend/fu/Alu.scala"
REFERENCE = ROOT / "validation/reference-closures/BranchModule-v2.sv"
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_branchmodule_strict"
EVIDENCE = ROOT / "validation/v2-branchmodule-strict-evidence.json"

INPUT_WIDTHS = {"io_src_0": 64, "io_src_1": 64, "io_func": 9,
                "io_pred_taken": 1}
OUTPUT_WIDTHS = {"io_taken": 1, "io_mispredict": 1}
INPUT_BITS = sum(INPUT_WIDTHS.values())


# Hash exact source and closure bytes for reproducibility.
def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one exact file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# Load only the selected Build by exact path.
def load_target() -> Any:
    """Load the BranchModule Build module."""

    spec = importlib.util.spec_from_file_location("strict_branch_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load target: {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Convert a Windows path to WSL's absolute spelling.
def wsl_path(path: Path) -> str:
    """Return an absolute WSL path."""

    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                            capture_output=True, check=True)
    return result.stdout.decode("utf-8", "replace").strip()


# Run one WSL command with stable diagnostics.
def run_wsl(command: list[str]) -> dict[str, Any]:
    """Run a WSL command and retain bounded output."""

    rendered = " ".join(shlex.quote(item) for item in command)
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered],
                            capture_output=True, check=False)
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {"command": command, "returncode": result.returncode,
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "output_tail": output[-3000:],
            "output_sha256": hashlib.sha256(output.encode()).hexdigest()}


# Record backend tool versions used by this proof.
def tool_versions() -> dict[str, Any]:
    """Return Verilator and Yosys version records."""

    return {"verilator": run_wsl(["verilator", "--version"]),
            "yosys": run_wsl(["yosys", "--version"])}


# Run Pyright on a visible exact source copy.
def pyright_check(source: Path) -> dict[str, Any]:
    """Run Pyright and return its machine-readable summary."""

    temporary = Path(tempfile.mkdtemp(prefix="uhsc_branch_pyright_"))
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
        return {"command": command, "returncode": result.returncode,
                "status": "PASS" if passed else "FAIL",
                "version": parsed.get("version") if isinstance(parsed, dict) else None,
                "files_analyzed": summary.get("filesAnalyzed"),
                "error_count": summary.get("errorCount"),
                "warning_count": summary.get("warningCount"),
                "output_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
                "stderr_tail": result.stderr[-1000:]}
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


# Generate deterministic target Verilog twice.
def deterministic_export(module: Any) -> tuple[str, dict[str, Any]]:
    """Return one export and its repeatability evidence."""

    first = module.build_verilog(None, {})
    second = module.build_verilog(None, {})
    first_bytes = first.encode("utf-8")
    second_bytes = second.encode("utf-8")
    return first, {"status": "PASS" if first_bytes == second_bytes else "FAIL",
                   "bytes": len(first_bytes),
                   "sha256": hashlib.sha256(first_bytes).hexdigest(),
                   "repeat_sha256": hashlib.sha256(second_bytes).hexdigest(),
                   "byte_equal": first_bytes == second_bytes}


# Materialize target, renamed locked closure, and an all-output miter.
def materialize_miter(target_rtl: str) -> dict[str, Path]:
    """Write the formal input files under an ASCII temporary path."""

    WORK.mkdir(parents=True, exist_ok=True)
    target = WORK / "UHSC_BranchModule.sv"
    reference = WORK / "REF_BranchModule.sv"
    miter = WORK / "BranchModule_MITER.sv"
    target.write_text(target_rtl, encoding="utf-8", newline="\n")
    source = REFERENCE.read_text(encoding="utf-8")
    source = source.replace("module BranchModule(",
                            "module REF_BranchModule(", 1)
    reference.write_text(source, encoding="utf-8", newline="\n")
    miter.write_text(
        """module BranchModule_MITER(
  input [63:0] io_src_0,
  input [63:0] io_src_1,
  input [8:0] io_func,
  input io_pred_taken,
  output mismatch
);
  wire ref_taken, ref_mispredict, dut_taken, dut_mispredict;
  REF_BranchModule ref_i(
    .io_src_0(io_src_0), .io_src_1(io_src_1), .io_func(io_func),
    .io_pred_taken(io_pred_taken), .io_taken(ref_taken),
    .io_mispredict(ref_mispredict));
  BranchModule dut_i(
    .io_src_0(io_src_0), .io_src_1(io_src_1), .io_func(io_func),
    .io_pred_taken(io_pred_taken), .io_taken(dut_taken),
    .io_mispredict(dut_mispredict));
  assign mismatch = (ref_taken ^ dut_taken)
                  | (ref_mispredict ^ dut_mispredict);
endmodule
""",
        encoding="utf-8", newline="\n")
    return {"target": target, "reference": reference, "miter": miter}


# Run lint, Yosys checks, and unrestricted SAT proof.
def formal_gates(paths: dict[str, Path]) -> dict[str, Any]:
    """Run Verilator/Yosys and prove mismatch is impossible."""

    converted = {name: wsl_path(path) for name, path in paths.items()}
    target, reference, miter = (converted["target"], converted["reference"],
                                converted["miter"])
    verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal",
                         target, reference, miter])
    target_yosys = run_wsl(["yosys", "-Q", "-p",
                            f"read_verilog -sv {shlex.quote(target)}; "
                            "hierarchy -top BranchModule; proc; opt; check"])
    reference_yosys = run_wsl(["yosys", "-Q", "-p",
                               f"read_verilog -sv {shlex.quote(reference)}; "
                               "hierarchy -top REF_BranchModule; proc; opt; check"])
    proof_script = (
        f"read_verilog -sv {shlex.quote(target)} {shlex.quote(reference)} "
        f"{shlex.quote(miter)}; prep -top BranchModule_MITER; flatten; opt; "
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
    return {"verilator": verilator, "yosys_target": target_yosys,
            "yosys_reference": reference_yosys, "yosys_formal_miter": proof}


# Assemble evidence; never claim COMPLETE_EQUIVALENCE after a failed gate.
def validate() -> dict[str, Any]:
    """Run all strict gates and write machine-readable evidence."""

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
        "build_id": "Build-Cpu.Backend.Fu.BranchModule",
        "validator": Path(__file__).relative_to(ROOT).as_posix(),
        "status": status,
        "strict_complete_eligible": status == "COMPLETE_EQUIVALENCE",
        "strict_complete_count_delta": 1 if status == "COMPLETE_EQUIVALENCE" else 0,
        "acceptance_eligible": status == "COMPLETE_EQUIVALENCE",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "scope": {
            "kind": "stateless_combinational_leaf",
            "configuration": "locked RV64, FuOpType func=9 bits",
            "state_bits": 0,
            "state_boundary": "no clock/reset/register/memory; one combinational evaluation",
            "inputs": INPUT_WIDTHS,
            "outputs_compared": OUTPUT_WIDTHS,
            "input_bits": INPUT_BITS,
            "input_space": f"2**{INPUT_BITS}",
            "input_space_cardinality": str(1 << INPUT_BITS),
            "why_complete": (
                "Yosys SAT proves the two-output miter mismatch is zero with all "
                "138 input bits unconstrained; no temporal state exists."
            ),
        },
        "sources": {
            "scala": {"path": SCALA.relative_to(ROOT).as_posix(),
                      "sha256": sha256_file(SCALA), "bytes": SCALA.stat().st_size},
            "scala_dependency": {"path": SCALA_SUB.relative_to(ROOT).as_posix(),
                                  "sha256": sha256_file(SCALA_SUB), "bytes": SCALA_SUB.stat().st_size,
                                  "used_for": "SubModule subtractor in locked closure"},
            "reference_sv": {"path": REFERENCE.relative_to(ROOT).as_posix(),
                             "sha256": sha256_file(REFERENCE), "bytes": REFERENCE.stat().st_size,
                             "locked_modules": ["SubModule", "BranchModule"],
                             "locked_xstop_sha256": "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d",
                             "locked_xstop_module_lines": [1198215, 1198236]},
            "python_build": {"path": TARGET.relative_to(ROOT).as_posix(),
                             "sha256": sha256_file(TARGET), "bytes": TARGET.stat().st_size},
        },
        "checks": {"python_version": platform.python_version(),
                    "py_compile": {"status": "PASS"}, "pyright": pyright,
                    "deterministic_export": export, "tools": tool_versions(),
                    "formal": gates},
        "failures": failures,
        "unclosed": [] if not failures else ["strict gates did not all pass"],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    return payload


# Print compact status and return nonzero while proof is pending.
def main() -> int:
    """Run the strict validator."""

    payload = validate()
    print(json.dumps({"status": payload["status"],
                      "strict_complete_eligible": payload["strict_complete_eligible"],
                      "failures": payload["failures"]}, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
