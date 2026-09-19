"""Formal complete-equivalence validator for the standalone V2 AMOALU leaf.

This validator deliberately targets one stateless, combinational Build.  The
Yosys miter quantifies every input bit, so the result is not a sampled or
``PASS_BOUNDED`` check: it covers the complete 2**141 input space of the
64-bit AMOALU interface.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
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
    "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/"
    "Build-Cpu.Cache.Dcache.Mainpipe.AMOALU-Hardware.py"
)
SCALA = ROOT / "upstream/src/main/scala/xiangshan/cache/dcache/mainpipe/AMOALU.scala"
REFERENCE = ROOT / "validation/reference-closures/AMOALU-dcache-v2.sv"
# WSL cannot reliably decode the non-ASCII repository path on every Windows
# transport.  Keep tool inputs in a fixed ASCII temporary directory instead.
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_amoalu_strict"
EVIDENCE = ROOT / "validation/v2-amoalu-strict-evidence.json"

INPUT_WIDTHS = {"io_mask": 8, "io_cmd": 5, "io_lhs": 64, "io_rhs": 64}
OUTPUT_WIDTHS = {"io_out": 64}
INPUT_BITS = sum(INPUT_WIDTHS.values())


# Hash exact bytes so the proof is tied to the reviewed sources and artifact.
def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one exact file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# Load the target by exact path without importing any sibling Build modules.
def load_target() -> Any:
    """Load the AMOALU Build module."""

    spec = importlib.util.spec_from_file_location("strict_amoalu_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load target: {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Run a native Windows command and retain machine-readable bounded diagnostics.
def run_windows(command: list[str]) -> dict[str, Any]:
    """Run one Windows command, returning status and output digest."""

    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", check=False)
        output = (result.stdout or "") + (result.stderr or "")
        return {
            "command": command,
            "returncode": result.returncode,
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "output_tail": output[-2000:],
            "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
        }
    except OSError as error:
        return {"command": command, "status": "FAIL", "error": repr(error)}


# Convert a Windows path to a WSL path without invoking a shell on Windows.
def wsl_path(path: Path) -> str:
    """Return an absolute WSL path for a Windows path."""

    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                            capture_output=True, check=True)
    return result.stdout.decode("utf-8", "replace").strip()


# Run a WSL command with exact argument quoting and bounded output.
def run_wsl(command: list[str]) -> dict[str, Any]:
    """Run a command in WSL and retain its exact command/result."""

    rendered = " ".join(shlex.quote(item) for item in command)
    try:
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
    except OSError as error:
        return {"command": command, "status": "FAIL", "error": repr(error)}


# Query tool versions in the same WSL environment used by the proof.
def tool_versions() -> dict[str, Any]:
    """Collect Verilator and Yosys versions."""

    return {
        "verilator": run_wsl(["verilator", "--version"]),
        "yosys": run_wsl(["yosys", "--version"]),
    }


# Copy a source into a visible temporary directory for a real Pyright analysis.
def pyright_check(source: Path) -> dict[str, Any]:
    """Run Pyright on an exact source copy (dot directories are auto-excluded)."""

    temporary = Path(tempfile.mkdtemp(prefix="uhsc_amoalu_pyright_"))
    try:
        copied = temporary / source.name
        shutil.copyfile(source, copied)
        command = ["cmd.exe", "/d", "/c", "pyright", "--outputjson", str(copied)]
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", check=False)
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            payload = {"parse_error": True, "stdout": result.stdout[-2000:]}
        summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
        passed = result.returncode == 0 and summary.get("errorCount") == 0
        return {
            "command": command,
            "returncode": result.returncode,
            "status": "PASS" if passed else "FAIL",
            "version": payload.get("version") if isinstance(payload, dict) else None,
            "files_analyzed": summary.get("filesAnalyzed"),
            "error_count": summary.get("errorCount"),
            "warning_count": summary.get("warningCount"),
            "output_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
            "stderr_tail": result.stderr[-1000:],
        }
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


# Export the exact target twice and prove byte-for-byte deterministic output.
def deterministic_export(module: Any) -> tuple[str, dict[str, Any]]:
    """Generate AMOALU Verilog twice and compare exact bytes."""

    first = module.build_verilog({"name": "UHSC_AMOALU"}, {})
    second = module.build_verilog({"name": "UHSC_AMOALU"}, {})
    first_bytes = first.encode("utf-8")
    second_bytes = second.encode("utf-8")
    return first, {
        "status": "PASS" if first_bytes == second_bytes else "FAIL",
        "bytes": len(first_bytes),
        "sha256": hashlib.sha256(first_bytes).hexdigest(),
        "repeat_sha256": hashlib.sha256(second_bytes).hexdigest(),
        "byte_equal": first_bytes == second_bytes,
    }


# Build a two-instance combinational miter against the locked Chisel SV.
def materialize_miter(target_rtl: str) -> dict[str, Path]:
    """Write target, renamed reference, and miter sources to the work tree."""

    WORK.mkdir(parents=True, exist_ok=True)
    target_path = WORK / "UHSC_AMOALU.sv"
    reference_path = WORK / "REF_AMOALU.sv"
    miter_path = WORK / "AMOALU_MITER.sv"
    target_path.write_text(target_rtl, encoding="utf-8", newline="\n")
    reference_text = REFERENCE.read_text(encoding="utf-8")
    marker = "module AMOALU("
    if marker not in reference_text:
        raise AssertionError("locked reference AMOALU module marker missing")
    reference_path.write_text(reference_text.replace(marker, "module REF_AMOALU(", 1),
                               encoding="utf-8", newline="\n")
    miter_path.write_text(
        """module AMOALU_MITER(
  input [7:0] io_mask,
  input [4:0] io_cmd,
  input [63:0] io_lhs,
  input [63:0] io_rhs,
  output mismatch
);
  wire [63:0] reference_out;
  wire [63:0] target_out;
  REF_AMOALU reference_i(
    .io_mask(io_mask), .io_cmd(io_cmd), .io_lhs(io_lhs), .io_rhs(io_rhs),
    .io_out(reference_out));
  UHSC_AMOALU target_i(
    .io_mask(io_mask), .io_cmd(io_cmd), .io_lhs(io_lhs), .io_rhs(io_rhs),
    .io_out(target_out));
  assign mismatch = |(reference_out ^ target_out);
endmodule
""",
        encoding="utf-8", newline="\n")
    return {"target": target_path, "reference": reference_path, "miter": miter_path}


# Run lint/synthesis gates and a full symbolic miter proof.
def formal_gates(paths: dict[str, Path]) -> dict[str, Any]:
    """Run Verilator, Yosys lint, and Yosys SAT over all 2**141 inputs."""

    converted = {name: wsl_path(path) for name, path in paths.items()}
    target = converted["target"]
    reference = converted["reference"]
    miter = converted["miter"]
    verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal",
                         target, reference, miter])
    target_yosys = run_wsl(["yosys", "-Q", "-p",
                            f"read_verilog -sv {shlex.quote(target)}; "
                            "hierarchy -top UHSC_AMOALU; proc; opt; check"])
    reference_yosys = run_wsl(["yosys", "-Q", "-p",
                               f"read_verilog -sv {shlex.quote(reference)}; "
                               "hierarchy -top REF_AMOALU; proc; opt; check"])
    proof_script = (
        f"read_verilog -sv {shlex.quote(target)} {shlex.quote(reference)} "
        f"{shlex.quote(miter)}; prep -top AMOALU_MITER; flatten; opt; "
        "sat -prove mismatch 0"
    )
    proof = run_wsl(["yosys", "-Q", "-p", proof_script])
    proof_marker = "SAT proof finished - no model found: SUCCESS!"
    proof["formal_success_marker"] = proof_marker in proof.get("output_tail", "")
    if not proof["formal_success_marker"]:
        proof["status"] = "FAIL"
    proof["formal_scope"] = {
        "input_bits": INPUT_BITS,
        "input_space": f"2**{INPUT_BITS}",
        "input_space_cardinality": str(1 << INPUT_BITS),
        "state_bits": 0,
        "state_space": "singleton (stateless combinational module)",
        "property": "mismatch == 0 for every 2-state valuation of io_mask/io_cmd/io_lhs/io_rhs",
    }
    return {
        "verilator": verilator,
        "yosys_target": target_yosys,
        "yosys_reference": reference_yosys,
        "yosys_formal_miter": proof,
    }


# Assemble and persist the evidence record; never claim complete equivalence on
# a failed gate.  The caller can use ``strict_complete_eligible`` as the count
# input without changing any top-level manifest or root metric.
def validate() -> dict[str, Any]:
    """Run all strict gates and write the machine-readable evidence record."""

    failures: list[str] = []
    module = load_target()
    py_compile.compile(str(TARGET), doraise=True)
    py_compile.compile(str(Path(__file__)), doraise=True)
    target_rtl, export = deterministic_export(module)
    paths = materialize_miter(target_rtl)
    gates = formal_gates(paths)
    pyright = {
        "target": pyright_check(TARGET),
        "validator": pyright_check(Path(__file__)),
    }
    if export["status"] != "PASS":
        failures.append("deterministic export mismatch")
    for name, result in pyright.items():
        if result["status"] != "PASS":
            failures.append(f"pyright {name}")
    for name, result in gates.items():
        if result["status"] != "PASS":
            failures.append(name)

    scala_hash = sha256_file(SCALA)
    reference_hash = sha256_file(REFERENCE)
    target_hash = sha256_file(TARGET)
    status = "COMPLETE_EQUIVALENCE" if not failures else "STRICT_PENDING"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_STRICT_COMPLETE_EQUIVALENCE",
        "build_id": "Build-Cpu.Cache.Dcache.Mainpipe.AMOALU",
        "validator": Path(__file__).relative_to(ROOT).as_posix(),
        "status": status,
        "strict_complete_eligible": status == "COMPLETE_EQUIVALENCE",
        "strict_complete_count_delta": 1 if status == "COMPLETE_EQUIVALENCE" else 0,
        "acceptance_eligible": status == "COMPLETE_EQUIVALENCE",
        "source_commit": "5fe0e8f3f77aa1cdb8523312cb222405bb6be8e5",
        "scope": {
            "kind": "stateless_combinational_leaf",
            "state_bits": 0,
            "state_boundary": "no clock/reset/register/memory; one combinational evaluation",
            "inputs": INPUT_WIDTHS,
            "outputs_compared": OUTPUT_WIDTHS,
            "uncompared_outputs": {
                "io_out_unmasked": (
                    "not exported by the locked reference SV or the Build adapter; "
                    "the strict claim is for the declared io_out interface"
                )
            },
            "input_bits": INPUT_BITS,
            "input_space": f"2**{INPUT_BITS}",
            "input_space_cardinality": str(1 << INPUT_BITS),
            "why_complete": (
                "Yosys SAT proves the miter mismatch output is zero with all "
                "141 input bits unconstrained; no temporal state exists."
            ),
        },
        "sources": {
            "scala": {"path": SCALA.relative_to(ROOT).as_posix(),
                      "sha256": scala_hash, "bytes": SCALA.stat().st_size},
            "reference_sv": {"path": REFERENCE.relative_to(ROOT).as_posix(),
                             "sha256": reference_hash, "bytes": REFERENCE.stat().st_size},
            "python_build": {"path": TARGET.relative_to(ROOT).as_posix(),
                             "sha256": target_hash, "bytes": TARGET.stat().st_size},
        },
        "checks": {
            "py_compile": {"status": "PASS"},
            "pyright": pyright,
            "deterministic_export": export,
            "tools": tool_versions(),
            "formal": gates,
        },
        "failures": failures,
        "unclosed": [] if not failures else ["strict gates did not all pass"],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    return payload


# Print a compact result for CI and preserve non-zero exit on pending proof.
def main() -> int:
    """Run validation and return a strict acceptance exit code."""

    payload = validate()
    print(json.dumps({"status": payload["status"],
                      "strict_complete_eligible": payload["strict_complete_eligible"],
                      "failures": payload["failures"]}, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
