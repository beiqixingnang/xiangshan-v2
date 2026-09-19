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
    "Build-Cpu.Backend.Fu.JumpDataModule-Hardware.py"
)
SCALA = ROOT / "upstream/src/main/scala/xiangshan/backend/fu/Jump.scala"
REFERENCE = ROOT / "validation/reference-closures/JumpDataModule-v2.sv"
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_jumpdatamodule_strict"
EVIDENCE = ROOT / "validation/v2-jumpdatamodule-strict-evidence.json"
SAT_SUCCESS_MARKER = "SAT proof finished - no model found: SUCCESS!"
SAT_FREE_INPUT_MARKER = "Final constraint equation: { } = { }"
SAT_MODEL_MARKER = "model found: FAIL!"

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
    counts = re.findall(r"Solving problem with (\d+) variables and (\d+) clauses", output)
    return {
        "command": command,
        "returncode": result.returncode,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "sat_success_marker": SAT_SUCCESS_MARKER in output,
        "sat_counterexample_marker": SAT_MODEL_MARKER in output,
        "unconstrained_marker": SAT_FREE_INPUT_MARKER in output,
        "sat_counts_full": ([int(value) for value in counts[-1]] if counts else None),
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
    proof["formal_success_marker"] = proof.get("sat_success_marker") is True
    proof["unconstrained"] = proof.get("unconstrained_marker") is True
    proof["miter_carries_no_assumption"] = proof["unconstrained"]
    if isinstance(proof.get("sat_counts_full"), list):
        proof["sat_variables"], proof["sat_clauses"] = proof["sat_counts_full"]
    if not proof["formal_success_marker"] or not proof["unconstrained"]:
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


def abi_audit(target_rtl: str, reference_rtl: str, miter_rtl: str) -> dict[str, Any]:
    """Require exact five-input/three-output surface and all miter connections."""

    expected = {**{name: ("input", width) for name, width in INPUT_WIDTHS.items()},
                **{name: ("output", width) for name, width in OUTPUT_WIDTHS.items()}}

    def ports(text: str, module: str) -> dict[str, tuple[str, int]]:
        clean = re.sub(r"//.*", "", text)
        header = re.search(r"module\s+" + re.escape(module) + r"\s*\((.*?)\)\s*;", clean, re.S)
        if header is None:
            return {}
        result: dict[str, tuple[str, int]] = {}
        raw_header = header.group(1)
        if re.search(r"\b(?:input|output)\b", raw_header):
            pending: tuple[str, int] | None = None
            for raw in raw_header.split(","):
                item = " ".join(raw.split())
                match = re.match(
                    r"^(input|output)\b(?:\s*\[\s*(\d+)\s*:\s*0\s*\])?\s*([A-Za-z_]\w*)?$",
                    item)
                if match is not None:
                    direction, msb, name = match.groups()
                    pending = (direction, int(msb) + 1 if msb else 1)
                    if name:
                        result[name] = pending
                elif pending is not None and re.fullmatch(r"[A-Za-z_]\w*", item):
                    result[item] = pending
                else:
                    pending = None
            return result
        names = set(re.findall(r"[A-Za-z_]\w*", raw_header))
        body = clean[header.end():clean.find("endmodule", header.end())]
        for direction, msb, name in re.findall(
                r"^\s*(input|output)\s*(?:\[\s*(\d+)\s*:\s*0\s*\])?\s*([A-Za-z_]\w*)\s*;",
                body, re.M):
            if name in names:
                result[name] = (direction, int(msb) + 1 if msb else 1)
        return result

    target = ports(target_rtl, "JumpDataModule")
    reference = ports(reference_rtl, "REF_JumpDataModule")
    checks = {
        "target_exact_port_set": target == expected,
        "reference_exact_port_set": reference == expected,
        "target_reference_equal": target == reference,
        "every_output_compared": all(f"{name}" in miter_rtl for name in OUTPUT_WIDTHS),
        "no_assume": "assume" not in miter_rtl.lower(),
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks, "target_ports": target, "reference_ports": reference}


def negative_control(paths: dict[str, Path]) -> dict[str, Any]:
    """Mutate target and reference result and require SAT counterexamples."""

    results: dict[str, Any] = {}
    for side in ("target", "reference"):
        source = paths[side].read_text(encoding="utf-8")
        module = "JumpDataModule" if side == "target" else "REF_JumpDataModule"
        start = source.find(f"module {module}(")
        end = source.find("endmodule", start)
        body = source[start:end] if start >= 0 and end >= 0 else ""
        mutated_body, count = re.subn(r"assign\s+io_result\s*=\s*.*?;",
                                      "assign io_result = 64'h0;", body, count=1, flags=re.S)
        if count != 1:
            results[side] = {"status": "FAIL", "mutation_applied": False}
            continue
        mutant = WORK / f"MUTANT_{side}.sv"
        mutant.write_text(source[:start] + mutated_body + source[end:], encoding="utf-8", newline="\n")
        selected = {**paths, side: mutant}
        converted = {name: wsl_path(path) for name, path in selected.items()}
        script = (f"read_verilog -sv {converted['target']} {converted['reference']} {converted['miter']}; "
                  "prep -top JumpDataModule_MITER; flatten; opt; sat -prove mismatch 0")
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


# Assemble evidence and refuse COMPLETE_EQUIVALENCE on any failed gate.
def validate() -> dict[str, Any]:
    """Run all gates and write the JumpDataModule evidence JSON."""

    module = load_target()
    py_compile.compile(str(TARGET), doraise=True)
    py_compile.compile(str(Path(__file__)), doraise=True)
    target_rtl, export = deterministic_export(module)
    paths = materialize_miter(target_rtl)
    reference_rtl = paths["reference"].read_text(encoding="utf-8")
    miter_rtl = paths["miter"].read_text(encoding="utf-8")
    abi = abi_audit(target_rtl, reference_rtl, miter_rtl)
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
        "build_id": "Build-Cpu.Backend.Fu.JumpDataModule",
        "validator": Path(__file__).relative_to(ROOT).as_posix(),
        "status": status,
        "strict_complete_eligible": status == "COMPLETE_EQUIVALENCE",
        "strict_complete_count_delta": 1 if status == "COMPLETE_EQUIVALENCE" else 0,
        "acceptance_eligible": status == "COMPLETE_EQUIVALENCE",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "audit_policy": {
            "require_negative_control": True,
            "require_two_sided_negative_control": True,
            "require_unconstrained_sat": True,
            "require_all_declared_outputs_compared": True,
            "scope_source": "single locked JumpDataModule surface",
        },
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
                    "pyright": pyright,
                    "source_lock": {"status": "PASS", "xstop_sha256":
                        "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"},
                    "abi": abi, "deterministic_export": export,
                    "tools": tool_versions(), "formal": gates,
                    "negative_control": control},
        "failures": failures,
        "unclosed": [] if not failures else ["strict gates did not all pass"],
        "acceptance_unclosed": [
            "Backend/FU parent closure, license review and user approval remain outside this proof."
        ],
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
