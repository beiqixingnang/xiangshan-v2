"""Complete formal equivalence validator for the locked V2 RVCExpander leaf.

The immutable XSTop module exposes a 32-bit instruction input, fsIsOff, a
32-bit expanded instruction, and an illegal flag.  The Build previously kept
register metadata as internal taps but accidentally exported those taps; its
adapter is normalized here to the exact four-port locked ABI.  The SAT miter
then quantifies all 33 input bits and compares every locked output bit.
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
    "Build-Cpu.Frontend.Ifu.RvcExpander-Hardware.py"
)
SCALA = ROOT / "upstream/src/main/scala/xiangshan/frontend/PreDecode.scala"
REFERENCE = ROOT / "validation/reference-closures/RVCExpander-v2.sv"
MANIFEST = ROOT / "validation/reference-closures/RVCExpander-v2.json"
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_rvcexpander_strict"
EVIDENCE = ROOT / "validation/v2-rvcexpander-strict-evidence.json"

SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
LOCKED_XSTOP = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
XSTOP_BYTES = 228590583
CONFIGURATION = {
    "XLEN": 64,
    "fLen": 64,
    "useAddiForMv": True,
    "HasCExtension": True,
}
INPUT_WIDTHS = {"io_in": 32, "io_fsIsOff": 1}
OUTPUT_WIDTHS = {"io_out_bits": 32, "io_ill": 1}
INPUT_BITS = sum(INPUT_WIDTHS.values())
OUTPUT_BITS = sum(OUTPUT_WIDTHS.values())
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

    spec = importlib.util.spec_from_file_location("strict_rvcexpander_target", TARGET)
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
        "output_tail": output[-5000:],
        "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
    }


def tool_versions() -> dict[str, Any]:
    """Record versions of formal back-end tools."""

    return {
        "verilator": run_wsl(["verilator", "--version"]),
        "yosys": run_wsl(["yosys", "--version"]),
    }


def pyright_check(source: Path) -> dict[str, Any]:
    """Run Pyright on an exact visible copy of one source file."""

    temporary = Path(tempfile.mkdtemp(prefix="uhsc_rvcexpander_pyright_"))
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
    """Generate the fixed V2 configuration RTL twice and compare bytes."""

    config = module.RvcExpanderConfig(**CONFIGURATION)
    first = module.build_verilog(config, {})
    second = module.build_verilog(config, {})
    first_bytes = first.encode("utf-8")
    second_bytes = second.encode("utf-8")
    return first, {
        "status": "PASS" if first_bytes == second_bytes else "FAIL",
        "bytes": len(first_bytes),
        "sha256": hashlib.sha256(first_bytes).hexdigest(),
        "repeat_sha256": hashlib.sha256(second_bytes).hexdigest(),
        "byte_equal": first_bytes == second_bytes,
        "configuration": CONFIGURATION,
    }


def closure_audit() -> dict[str, Any]:
    """Audit exact single-module extraction and locked four-port ABI."""

    if not REFERENCE.is_file() or not MANIFEST.is_file():
        return {"status": "FAIL", "reason": "closure or manifest missing"}
    try:
        text = REFERENCE.read_text(encoding="utf-8")
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {"status": "FAIL", "reason": repr(error)}
    declaration = text.split("\n\n", 1)[0].lstrip()
    expected_ports = ["io_in", "io_fsIsOff", "io_out_bits", "io_ill"]
    checks = {
        "target": manifest.get("target") == "RVCExpander",
        "source_sha256": manifest.get("source_sha256") == XSTOP_SHA256,
        "closure_complete": manifest.get("closure_complete") is True,
        "module_count": manifest.get("module_count") == 1,
        "extracted_hash": manifest.get("extracted_sha256") == sha256_file(REFERENCE),
        "module_declaration": declaration.startswith("module RVCExpander("),
        "locked_input": "input  [31:0] io_in" in declaration and "input         io_fsIsOff" in declaration,
        "locked_outputs": "output [31:0] io_out_bits" in declaration and "output        io_ill" in declaration,
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "ports": expected_ports,
        "closure_path": REFERENCE.relative_to(ROOT).as_posix(),
        "closure_sha256": sha256_file(REFERENCE),
        "closure_bytes": REFERENCE.stat().st_size,
        "manifest_path": MANIFEST.relative_to(ROOT).as_posix(),
        "manifest_sha256": sha256_file(MANIFEST),
        "source": manifest.get("source"),
        "source_sha256": manifest.get("source_sha256"),
    }


def materialize_miter(target_rtl: str) -> dict[str, Path]:
    """Write target, renamed reference, and all-output miter."""

    reference_text = REFERENCE.read_text(encoding="utf-8")
    marker = "module RVCExpander("
    if marker not in reference_text:
        raise AssertionError("locked RVCExpander declaration missing")
    WORK.mkdir(parents=True, exist_ok=True)
    target = WORK / "UHSC_RVCExpander.sv"
    reference = WORK / "REF_RVCExpander.sv"
    miter = WORK / "RVCExpander_MITER.sv"
    target.write_text(target_rtl, encoding="utf-8", newline="\n")
    reference.write_text(reference_text.replace(marker, "module REF_RVCExpander(", 1),
                          encoding="utf-8", newline="\n")
    miter.write_text(
        """module RVCExpander_MITER(
  input [31:0] io_in,
  input io_fsIsOff,
  output mismatch
);
  wire [31:0] ref_bits;
  wire ref_ill;
  wire [31:0] dut_bits;
  wire dut_ill;
  REF_RVCExpander reference_i(
    .io_in(io_in), .io_fsIsOff(io_fsIsOff),
    .io_out_bits(ref_bits), .io_ill(ref_ill));
  RVCExpander target_i(
    .io_in(io_in), .io_fsIsOff(io_fsIsOff),
    .io_out_bits(dut_bits), .io_ill(dut_ill));
  assign mismatch = |(ref_bits ^ dut_bits) | (ref_ill ^ dut_ill);
endmodule
""",
        encoding="utf-8", newline="\n")
    return {"target": target, "reference": reference, "miter": miter}


def formal_gates(paths: dict[str, Path]) -> dict[str, Any]:
    """Run Verilator/Yosys lint and unrestricted 33-input SAT proof."""

    target = wsl_path(paths["target"])
    reference = wsl_path(paths["reference"])
    miter = wsl_path(paths["miter"])
    verilator = run_wsl([
        "verilator", "--lint-only", "-Wno-fatal", "--top-module",
        "RVCExpander_MITER", target, reference, miter,
    ])
    yosys_target = run_wsl(["yosys", "-Q", "-p",
                            f"read_verilog -sv {shlex.quote(target)}; "
                            "hierarchy -top RVCExpander; proc; opt; check"])
    yosys_reference = run_wsl(["yosys", "-Q", "-p",
                               f"read_verilog -sv {shlex.quote(reference)}; "
                               "hierarchy -top REF_RVCExpander; proc; opt; check"])
    proof = run_wsl(["yosys", "-Q", "-p",
                     f"read_verilog -sv {shlex.quote(target)} {shlex.quote(reference)} "
                     f"{shlex.quote(miter)}; prep -top RVCExpander_MITER; flatten; opt; "
                     "sat -prove mismatch 0"])
    proof["formal_success_marker"] = proof.get("sat_success_marker") is True
    proof["unconstrained"] = proof.get("unconstrained_marker") is True
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
        "state_space": "singleton (stateless combinational decoder)",
        "outputs_compared": OUTPUT_WIDTHS,
        "output_bits": OUTPUT_BITS,
        "property": "mismatch == 0 for every 2-state valuation of io_in/io_fsIsOff",
    }
    return {
        "verilator": verilator,
        "yosys_target": yosys_target,
        "yosys_reference": yosys_reference,
        "yosys_formal_miter": proof,
    }


def abi_audit(paths: dict[str, Path]) -> dict[str, Any]:
    """Check the locked four-port ABI and both output comparisons."""

    target = paths["target"].read_text(encoding="utf-8")
    reference = paths["reference"].read_text(encoding="utf-8")
    miter = paths["miter"].read_text(encoding="utf-8")
    checks = {
        "target_module": "module RVCExpander(" in target,
        "reference_module": "module REF_RVCExpander(" in reference,
        "target_input": bool(re.search(r"input\s+\[31:0\]\s+io_in", target)),
        "reference_input": bool(re.search(r"input\s+\[31:0\]\s+io_in", reference)),
        "target_fs": bool(re.search(r"input\s+io_fsIsOff", target)),
        "reference_fs": bool(re.search(r"input\s+io_fsIsOff", reference)),
        "target_bits": bool(re.search(r"output\s+\[31:0\]\s+io_out_bits", target)),
        "reference_bits": bool(re.search(r"output\s+\[31:0\]\s+io_out_bits", reference)),
        "target_ill": bool(re.search(r"output\s+io_ill", target)),
        "reference_ill": bool(re.search(r"output\s+io_ill", reference)),
        "inputs_connected_twice": miter.count(".io_in(io_in)") == 2
                                  and miter.count(".io_fsIsOff(io_fsIsOff)") == 2,
        "both_outputs_compared": "ref_bits ^ dut_bits" in miter
                                 and "ref_ill ^ dut_ill" in miter,
        "no_assume": "assume" not in miter.lower(),
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}


def negative_control(paths: dict[str, Path]) -> dict[str, Any]:
    """Mutate each side's expanded instruction and require SAT models."""

    results: dict[str, Any] = {}
    for side in ("target", "reference"):
        source = paths[side].read_text(encoding="utf-8")
        mutated, count = re.subn(r"assign\s+io_out_bits\s*=\s*.*?;",
                                 "assign io_out_bits = 32'h0;", source,
                                 count=1, flags=re.S)
        if count != 1:
            results[side] = {"status": "FAIL", "mutation_applied": False}
            continue
        mutant = WORK / f"MUTANT_{side}.sv"
        mutant.write_text(mutated, encoding="utf-8", newline="\n")
        selected = {**paths, side: mutant}
        converted = {name: wsl_path(path) for name, path in selected.items()}
        script = (f"read_verilog -sv {converted['target']} {converted['reference']} {converted['miter']}; "
                  "prep -top RVCExpander_MITER; flatten; opt; sat -prove mismatch 0")
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
    """Run every strict gate and persist evidence."""

    closure = closure_audit()
    failures: list[str] = []
    if closure["status"] != "PASS":
        failures.append("closure/ABI audit")
    module = load_target()
    py_compile.compile(str(TARGET), doraise=True)
    py_compile.compile(str(Path(__file__)), doraise=True)
    target_rtl, export = deterministic_export(module)
    paths = materialize_miter(target_rtl)
    abi = abi_audit(paths)
    formal = formal_gates(paths)
    control = negative_control(paths)
    pyright = {"target": pyright_check(TARGET),
               "validator": pyright_check(Path(__file__))}
    if export["status"] != "PASS":
        failures.append("deterministic export")
    if abi["status"] != "PASS":
        failures.append("exact ABI/miter audit")
    if control["status"] != "PASS":
        failures.append("two-sided negative control")
    for name, result in pyright.items():
        if result["status"] != "PASS":
            failures.append(f"pyright {name}")
    for name, result in formal.items():
        if result["status"] != "PASS":
            failures.append(f"formal {name}")
    status = "COMPLETE_EQUIVALENCE" if not failures else "STRICT_PENDING"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_STRICT_COMPLETE_EQUIVALENCE",
        "build_id": "Build-Cpu.Frontend.Ifu.RvcExpander",
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
                         "scope_source": "single locked RVCExpander surface"},
        "scope": {
            "kind": "stateless_combinational_leaf",
            "configuration": CONFIGURATION,
            "inputs": INPUT_WIDTHS,
            "input_bits": INPUT_BITS,
            "input_space": f"2**{INPUT_BITS}",
            "input_space_cardinality": str(1 << INPUT_BITS),
            "state_bits": 0,
            "state_boundary": "no clock/reset/register/memory; one combinational evaluation",
            "outputs_compared": OUTPUT_WIDTHS,
            "output_bits": OUTPUT_BITS,
            "why_complete": (
                "Yosys SAT proves both locked output ports equal for every valuation "
                "of all 33 input bits; metadata taps are internal and not part of the locked ABI."
            ),
            "bounded_tests_counted": False,
        },
        "reference_lock": {
            "path": LOCKED_XSTOP,
            "upstream_source_commit": SOURCE_COMMIT,
            "xstop_sha256": XSTOP_SHA256,
            "xstop_bytes": XSTOP_BYTES,
            "closure_audit": closure,
            "extraction_rule": "exact RVCExpander module copied from immutable XSTop.sv",
        },
        "sources": {
            "scala": {"path": SCALA.relative_to(ROOT).as_posix(),
                      "sha256": sha256_file(SCALA), "bytes": SCALA.stat().st_size},
            "python_build": {"path": TARGET.relative_to(ROOT).as_posix(),
                             "sha256": sha256_file(TARGET), "bytes": TARGET.stat().st_size},
            "reference_sv": {"path": REFERENCE.relative_to(ROOT).as_posix(),
                             "sha256": sha256_file(REFERENCE), "bytes": REFERENCE.stat().st_size,
                             "module": "RVCExpander"},
            "reference_manifest": {"path": MANIFEST.relative_to(ROOT).as_posix(),
                                   "sha256": sha256_file(MANIFEST), "bytes": MANIFEST.stat().st_size},
        },
        "checks": {
            "py_compile": {"status": "PASS", "files": [
                TARGET.relative_to(ROOT).as_posix(),
                Path(__file__).relative_to(ROOT).as_posix(),
            ]},
            "pyright": pyright,
            "deterministic_export": export,
            "abi": abi,
            "closure_audit": closure,
            "tools": tool_versions(),
            "formal": formal,
            "negative_control": control,
        },
        "failures": failures,
        "unclosed": [] if not failures else ["strict gates did not all pass"],
        "acceptance_unclosed": [
            "Frontend parent closure, license review and user approval remain outside this proof."
        ],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    return payload


def main() -> int:
    """Print strict status and return nonzero until all gates pass."""

    payload = validate()
    print(json.dumps({"status": payload["status"],
                      "strict_complete_eligible": payload["strict_complete_eligible"],
                      "failures": payload["failures"]}, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
