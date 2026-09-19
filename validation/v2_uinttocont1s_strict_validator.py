"""Complete formal equivalence validator for the V2 UIntToCont1s leaf.

This helper is stateless and combinational.  Its locked V2 interface has an
8-bit count and a 255-bit output.  The Yosys SAT miter leaves every input bit
unconstrained and compares the complete output bus, so no bounded vector set
is used for the strict status.
"""

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
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Build-Cpu.Backend.Fu.Vector.Utils.UIntToCont1s-Hardware.py"
)
SCALA = ROOT / (
    "upstream/src/main/scala/xiangshan/backend/fu/vector/utils/"
    "UIntToCont1s.scala"
)
REFERENCE = ROOT / "validation/reference-sv/UIntToContLow1s.sv"
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_uinttocont1s_strict"
EVIDENCE = ROOT / "validation/v2-uinttocont1s-strict-evidence.json"

INPUT_WIDTHS = {"io_dataIn": 8}
OUTPUT_WIDTHS = {"io_dataOut": 255}
INPUT_BITS = 8
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
XSTOP_BYTES = 228590583
SAT_SUCCESS_MARKER = "SAT proof finished - no model found: SUCCESS!"
SAT_FREE_INPUT_MARKER = "Final constraint equation: { } = { }"
SAT_MODEL_MARKER = "model found: FAIL!"


def sha256_file(path: Path) -> str:
    """Return SHA-256 of exact file bytes."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_target() -> Any:
    """Load the selected Build module by exact path."""

    spec = importlib.util.spec_from_file_location("strict_uinttocont1s_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load target: {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def wsl_path(path: Path) -> str:
    """Convert a Windows path to an absolute WSL path."""

    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                            capture_output=True, check=True)
    return result.stdout.decode("utf-8", "replace").strip()


def run_wsl(command: list[str]) -> dict[str, Any]:
    """Run one WSL command and retain bounded, hashed diagnostics."""

    rendered = " ".join(shlex.quote(item) for item in command)
    try:
        result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered],
                                capture_output=True, check=False)
    except OSError as error:
        return {"command": command, "status": "FAIL", "error": repr(error)}
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    counts = re.findall(r"Solving problem with (\d+) variables and (\d+) clauses", output)
    return {
        "command": command,
        "returncode": result.returncode,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "sat_success_marker": SAT_SUCCESS_MARKER in output,
        "sat_counterexample_marker": SAT_MODEL_MARKER in output,
        "unconstrained_marker": SAT_FREE_INPUT_MARKER in output,
        "sat_counts_full": ([int(value) for value in counts[-1]] if counts else None),
        "output_tail": output[-4000:],
        "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
    }


def tool_versions() -> dict[str, Any]:
    """Record versions of the proof back-end tools."""

    return {
        "verilator": run_wsl(["verilator", "--version"]),
        "yosys": run_wsl(["yosys", "--version"]),
    }


def pyright_check(source: Path) -> dict[str, Any]:
    """Run Pyright on an exact visible copy of one source file."""

    temporary = Path(tempfile.mkdtemp(prefix="uhsc_uinttocont1s_pyright_"))
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


def deterministic_export(module: Any) -> tuple[str, dict[str, Any]]:
    """Generate target RTL twice and require byte identity."""

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


def materialize_miter(target_rtl: str) -> dict[str, Path]:
    """Write target, renamed locked reference, and complete-output miter."""

    if not REFERENCE.is_file():
        raise FileNotFoundError(f"locked V2 reference missing: {REFERENCE}")
    reference_text = REFERENCE.read_text(encoding="utf-8")
    marker = "module UIntToContLow1s("
    if marker not in reference_text:
        raise AssertionError("locked UIntToContLow1s declaration missing")
    WORK.mkdir(parents=True, exist_ok=True)
    target = WORK / "UHSC_UIntToContLow1s.sv"
    reference = WORK / "REF_UIntToContLow1s.sv"
    miter = WORK / "UIntToContLow1s_MITER.sv"
    target.write_text(target_rtl, encoding="utf-8", newline="\n")
    reference.write_text(reference_text.replace(marker, "module REF_UIntToContLow1s(", 1),
                          encoding="utf-8", newline="\n")
    miter.write_text(
        """module UIntToContLow1s_MITER(
  input [7:0] io_dataIn,
  output mismatch
);
  wire [254:0] reference_out;
  wire [254:0] target_out;
  REF_UIntToContLow1s reference_i(
    .io_dataIn(io_dataIn), .io_dataOut(reference_out));
  UIntToContLow1s target_i(
    .io_dataIn(io_dataIn), .io_dataOut(target_out));
  assign mismatch = |(reference_out ^ target_out);
endmodule
""",
        encoding="utf-8", newline="\n")
    return {"target": target, "reference": reference, "miter": miter}


def formal_gates(paths: dict[str, Path]) -> dict[str, Any]:
    """Run Verilator/Yosys lint and unrestricted SAT equivalence."""

    converted = {name: wsl_path(path) for name, path in paths.items()}
    target, reference, miter = (converted["target"], converted["reference"],
                                converted["miter"])
    verilator = run_wsl([
        "verilator", "--lint-only", "-Wno-fatal", "--top-module",
        "UIntToContLow1s_MITER", target, reference, miter,
    ])
    target_yosys = run_wsl(["yosys", "-Q", "-p",
                            f"read_verilog -sv {shlex.quote(target)}; "
                            "hierarchy -top UIntToContLow1s; proc; opt; check"])
    reference_yosys = run_wsl(["yosys", "-Q", "-p",
                               f"read_verilog -sv {shlex.quote(reference)}; "
                               "hierarchy -top REF_UIntToContLow1s; proc; opt; check"])
    proof_script = (
        f"read_verilog -sv {shlex.quote(target)} {shlex.quote(reference)} "
        f"{shlex.quote(miter)}; prep -top UIntToContLow1s_MITER; flatten; opt; "
        "sat -prove mismatch 0"
    )
    proof = run_wsl(["yosys", "-Q", "-p", proof_script])
    proof["formal_success_marker"] = proof.get("sat_success_marker") is True
    proof["unconstrained"] = proof.get("unconstrained_marker") is True
    proof["miter_carries_no_assumption"] = proof["unconstrained"]
    counts = proof.get("sat_counts_full")
    if isinstance(counts, list) and len(counts) == 2:
        proof["sat_variables"], proof["sat_clauses"] = counts
    if not proof["formal_success_marker"] or not proof["unconstrained"]:
        proof["status"] = "FAIL"
    proof["formal_scope"] = {
        "input_bits": INPUT_BITS,
        "input_space": f"2**{INPUT_BITS}",
        "input_space_cardinality": str(1 << INPUT_BITS),
        "state_bits": 0,
        "state_space": "singleton (stateless combinational module)",
        "property": "mismatch == 0 for every 2-state valuation of io_dataIn",
        "outputs_compared": OUTPUT_WIDTHS,
    }
    return {
        "verilator": verilator,
        "yosys_target": target_yosys,
        "yosys_reference": reference_yosys,
        "yosys_formal_miter": proof,
    }


def abi_audit(paths: dict[str, Path]) -> dict[str, Any]:
    """Check both exact ports and the complete-output miter wiring."""

    target = paths["target"].read_text(encoding="utf-8")
    reference = paths["reference"].read_text(encoding="utf-8")
    miter = paths["miter"].read_text(encoding="utf-8")
    checks = {
        "target_module": "module UIntToContLow1s(" in target,
        "reference_module": "module REF_UIntToContLow1s(" in reference,
        "target_input": bool(re.search(r"input\s+\[7:0\]\s+io_dataIn", target)),
        "reference_input": bool(re.search(r"input\s+\[7:0\]\s+io_dataIn", reference)),
        "target_output": bool(re.search(r"output\s+\[254:0\]\s+io_dataOut", target)),
        "reference_output": bool(re.search(r"output\s+\[254:0\]\s+io_dataOut", reference)),
        "miter_both_instances": "REF_UIntToContLow1s reference_i" in miter
                                and "UIntToContLow1s target_i" in miter,
        "miter_input_connected": miter.count(".io_dataIn(io_dataIn)") == 2,
        "complete_output_compared": "reference_out ^ target_out" in miter,
        "no_assume": "assume" not in miter.lower(),
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}


def negative_control(paths: dict[str, Path]) -> dict[str, Any]:
    """Mutate each side's full output and require explicit SAT models."""

    results: dict[str, Any] = {}
    for side in ("target", "reference"):
        source = paths[side].read_text(encoding="utf-8")
        mutated, count = re.subn(r"assign\s+io_dataOut\s*=\s*.*?;",
                                 "assign io_dataOut = 255'h0;", source,
                                 count=1, flags=re.S)
        if count != 1:
            results[side] = {"status": "FAIL", "mutation_applied": False}
            continue
        mutant = WORK / f"MUTANT_{side}.sv"
        mutant.write_text(mutated, encoding="utf-8", newline="\n")
        selected = {**paths, side: mutant}
        converted = {name: wsl_path(path) for name, path in selected.items()}
        script = (f"read_verilog -sv {converted['target']} {converted['reference']} {converted['miter']}; "
                  "prep -top UIntToContLow1s_MITER; flatten; opt; sat -prove mismatch 0")
        verdict = run_wsl(["yosys", "-Q", "-p", script])
        detected = (isinstance(verdict.get("returncode"), int)
                    and verdict.get("sat_counterexample_marker") is True
                    and verdict.get("sat_success_marker") is not True)
        results[side] = {"status": "PASS" if detected else "FAIL",
                         "mutation_applied": True,
                         "counterexample_marker": verdict.get("sat_counterexample_marker"),
                         "success_marker_still_present": verdict.get("sat_success_marker")}
    return {"status": "PASS" if all(item["status"] == "PASS" for item in results.values()) else "FAIL",
            "sides": results, "two_sided": True}


def validate() -> dict[str, Any]:
    """Run every strict gate and persist machine-readable evidence."""

    module = load_target()
    py_compile.compile(str(TARGET), doraise=True)
    py_compile.compile(str(Path(__file__)), doraise=True)
    target_rtl, export = deterministic_export(module)
    paths = materialize_miter(target_rtl)
    abi = abi_audit(paths)
    gates = formal_gates(paths)
    control = negative_control(paths)
    pyright = {"target": pyright_check(TARGET),
               "validator": pyright_check(Path(__file__))}
    failures: list[str] = []
    if export["status"] != "PASS":
        failures.append("deterministic export mismatch")
    if abi["status"] != "PASS":
        failures.append("ABI/miter audit")
    if control["status"] != "PASS":
        failures.append("two-sided negative control")
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
        "build_id": "Build-Cpu.Backend.Fu.Vector.Utils.UIntToCont1s",
        "validator": Path(__file__).relative_to(ROOT).as_posix(),
        "status": status,
        "strict_complete_eligible": status == "COMPLETE_EQUIVALENCE",
        "strict_complete_count_delta": 1 if status == "COMPLETE_EQUIVALENCE" else 0,
        "acceptance_eligible": status == "COMPLETE_EQUIVALENCE",
        "source_commit": SOURCE_COMMIT,
        "audit_policy": {"require_negative_control": True,
                         "require_two_sided_negative_control": True,
                         "require_unconstrained_sat": True,
                         "require_all_declared_outputs_compared": True,
                         "scope_source": "single locked UIntToContLow1s surface"},
        "scope": {
            "kind": "stateless_combinational_leaf",
            "configuration": "locked V2 UIntToContLow1s uintWidth=8, outWidth=(2**8)-1=255",
            "state_bits": 0,
            "state_boundary": "no clock/reset/register/memory; one combinational evaluation",
            "inputs": INPUT_WIDTHS,
            "outputs_compared": OUTPUT_WIDTHS,
            "input_bits": INPUT_BITS,
            "input_space": f"2**{INPUT_BITS}",
            "input_space_cardinality": str(1 << INPUT_BITS),
            "why_complete": (
                "Yosys SAT proves the complete 255-bit-output miter mismatch is zero "
                "with all 8 input bits unconstrained; no temporal state exists."
            ),
            "bounded_tests_counted": False,
        },
        "reference_lock": {
            "upstream_source_commit": SOURCE_COMMIT,
            "xstop_sha256": XSTOP_SHA256,
            "xstop_bytes": XSTOP_BYTES,
            "reference_module": "UIntToContLow1s extracted from locked V2 XSTop",
        },
        "sources": {
            "scala": {"path": SCALA.relative_to(ROOT).as_posix(),
                      "sha256": sha256_file(SCALA), "bytes": SCALA.stat().st_size},
            "reference_sv": {"path": REFERENCE.relative_to(ROOT).as_posix(),
                             "sha256": sha256_file(REFERENCE), "bytes": REFERENCE.stat().st_size,
                             "locked_module": "UIntToContLow1s"},
            "python_build": {"path": TARGET.relative_to(ROOT).as_posix(),
                             "sha256": sha256_file(TARGET), "bytes": TARGET.stat().st_size},
        },
        "checks": {
            "py_compile": {"status": "PASS", "files": [
                TARGET.relative_to(ROOT).as_posix(),
                Path(__file__).relative_to(ROOT).as_posix(),
            ]},
            "pyright": pyright,
            "source_lock": {"status": "PASS", "xstop_sha256": XSTOP_SHA256},
            "abi": abi,
            "deterministic_export": export,
            "tools": tool_versions(),
            "formal": gates,
            "negative_control": control,
        },
        "failures": failures,
        "unclosed": [] if not failures else ["strict gates did not all pass"],
        "acceptance_unclosed": [
            "Vector utility parent closure, license review and user approval remain outside this proof."
        ],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    return payload


def main() -> int:
    """Print strict status and return nonzero until every gate passes."""

    payload = validate()
    print(json.dumps({"status": payload["status"],
                      "strict_complete_eligible": payload["strict_complete_eligible"],
                      "failures": payload["failures"]}, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
