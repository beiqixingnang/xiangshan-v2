"""Strict complete-equivalence proof for the locked V2 vector data splitter.

The locked reference exposes one 128-bit input and 30 packed output lanes.  The
surface compared here is derived from the locked SystemVerilog itself instead of
being restated by hand, so every declared output lane participates in the
reduction-OR mismatch and no input bit is constrained.
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
    "Build-Cpu.Backend.Fu.Vector.Utils.VecDataSplitModule-Hardware.py"
)
SCALA = ROOT / "upstream/src/main/scala/xiangshan/backend/fu/vector/utils/VecDataSplitModule.scala"
REFERENCE = ROOT / "validation/reference-sv/VecDataSplitModule.sv"
EVIDENCE = ROOT / "validation/v2-vecdatasplitmodule-strict-evidence.json"
MODULE_NAME = "VecDataSplitModule"
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_vecdatasplitmodule_strict"

SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
SAT_SUCCESS_MARKER = "SAT proof finished - no model found: SUCCESS!"
MODEL_FOUND_MARKER = "SAT proof finished - model found: FAIL!"
FREE_INPUT_MARKER = "Final constraint equation: { } = { }"
ANSI_PORT = re.compile(r"^(input|output)\s+(?:\[(\d+):0\]\s*)?(.+)$")


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one exact file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def strip_comments(line: str) -> str:
    """Drop a SystemVerilog line comment."""

    return re.sub(r"//.*", "", line).strip()


def ansi_ports(rtl: str, module: str) -> dict[str, tuple[str, int]]:
    """Read an ANSI-style locked port declaration into name - (direction, width)."""

    header = re.search(r"module\s+" + re.escape(module) + r"\s*\((.*?)\)\s*[;:]", rtl, re.S)
    if header is None:
        return {}
    ports: dict[str, tuple[str, int]] = {}
    direction: str | None = None
    width = 1
    for raw in header.group(1).splitlines():
        line = strip_comments(raw).rstrip(",").strip()
        if not line:
            continue
        declared = ANSI_PORT.match(line)
        if declared is not None:
            direction = str(declared.group(1))
            width = int(declared.group(2)) + 1 if declared.group(2) else 1
            names: list[str] = [item.strip() for item in declared.group(3).split(",") if item.strip()]
        else:
            if direction is None:
                continue
            names = [item.strip() for item in line.split(",") if item.strip()]
        for name in names:
            ports[name] = (direction, width)
    return ports


def nonansi_ports(rtl: str, module: str) -> dict[str, tuple[str, int]]:
    """Read an Amaranth-style header-plus-body declaration."""

    header = re.search(r"module\s+" + re.escape(module) + r"\s*\(([^)]*)\)\s*;", rtl, re.S)
    if header is None:
        return {}
    names = [item.strip() for item in strip_comments(header.group(1)).replace("\n", " ").split(",")]
    wanted = [item for item in names if item]
    ports: dict[str, tuple[str, int]] = {}
    for raw in rtl[header.end():].splitlines():
        line = strip_comments(raw)
        declared = ANSI_PORT.match(line.rstrip(";").strip())
        if declared is None:
            continue
        width = int(declared.group(2)) + 1 if declared.group(2) else 1
        for name in [item.strip() for item in declared.group(3).split(",") if item.strip()]:
            if name in wanted and name not in ports:
                ports[name] = (str(declared.group(1)), width)
    return ports


def declared_ports(rtl: str, module: str) -> dict[str, tuple[str, int]]:
    """Return whichever declaration style one module actually uses."""

    return ansi_ports(rtl, module) or nonansi_ports(rtl, module)


def load_target() -> Any:
    """Load only the selected Build module by exact path."""

    spec = importlib.util.spec_from_file_location("strict_vecdatasplitmodule_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load target: {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def wsl_path(path: Path) -> str:
    """Convert a Windows path into an absolute WSL path."""

    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                            capture_output=True, check=True)
    return result.stdout.decode("utf-8", "replace").strip()


def run_wsl(command: list[str]) -> dict[str, Any]:
    """Run one WSL command and retain bounded diagnostics."""

    rendered = " ".join(shlex.quote(item) for item in command)
    try:
        result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered],
                                capture_output=True, check=False)
    except OSError as error:
        return {"command": command, "returncode": None, "status": "FAIL",
                "error": repr(error), "output_tail": repr(error),
                "sat_success_marker": False, "sat_counterexample_marker": False,
                "unconstrained_marker": False, "sat_variables": None,
                "sat_clauses": None}
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    counts = re.findall(r"Solving problem with (\d+) variables and (\d+) clauses", output)
    variables = clauses = None
    if counts:
        variables, clauses = map(int, counts[-1])
    return {
        "command": command,
        "returncode": result.returncode,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "sat_success_marker": SAT_SUCCESS_MARKER in output,
        "sat_counterexample_marker": MODEL_FOUND_MARKER in output,
        "unconstrained_marker": FREE_INPUT_MARKER in output,
        "sat_variables": variables,
        "sat_clauses": clauses,
        "output_tail": output[-4000:],
        "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
    }


def pyright_check(source: Path) -> dict[str, Any]:
    """Run Pyright on an exact visible copy of one source file."""

    temporary = Path(tempfile.mkdtemp(prefix="uhsc_vecdatasplit_pyright_"))
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


def source_lock() -> tuple[dict[str, Any], dict[str, Any]]:
    """Record the exact locked inputs this proof depends on."""

    records = {
        "scala": SCALA,
        "reference_sv": REFERENCE,
        "python_build": TARGET,
    }
    sources = {name: {"path": path.relative_to(ROOT).as_posix(),
                      "sha256": sha256_file(path),
                      "bytes": path.stat().st_size} for name, path in records.items()}
    return sources, {"status": "PASS" if all(path.is_file() for path in records.values()) else "FAIL",
                     "source_commit": SOURCE_COMMIT,
                     "locked_reference_directory": "validation/reference-sv"}


def surface() -> tuple[dict[str, int], dict[str, int]]:
    """Derive the compared input and output widths from the locked reference."""

    ports = declared_ports(REFERENCE.read_text(encoding="utf-8"), MODULE_NAME)
    inputs = {name: width for name, (direction, width) in ports.items() if direction == "input"}
    outputs = {name: width for name, (direction, width) in ports.items() if direction == "output"}
    return inputs, outputs


def abi_audit(target_rtl: str, inputs: dict[str, int], outputs: dict[str, int]) -> dict[str, Any]:
    """Require the target to declare exactly the locked port surface."""

    reference_ports = declared_ports(REFERENCE.read_text(encoding="utf-8"), MODULE_NAME)
    target_ports = declared_ports(target_rtl, MODULE_NAME)
    expected = {**{name: ("input", width) for name, width in inputs.items()},
                **{name: ("output", width) for name, width in outputs.items()}}
    checks = {
        "target_module": f"module {MODULE_NAME}(" in target_rtl,
        "reference_module": f"module {MODULE_NAME}(" in REFERENCE.read_text(encoding="utf-8")
                            and bool(reference_ports),
        "target_declares_every_port": all(name in target_ports for name in expected),
        "surface_equals_locked_surface": target_ports == reference_ports,
        "no_extra_target_ports": set(target_ports) == set(expected),
        "every_output_compared": set(outputs) == {name for name, (d, _) in reference_ports.items() if d == "output"},
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "target_declared_ports": {k: list(v) for k, v in sorted(target_ports.items())},
        "reference_declared_ports": {k: list(v) for k, v in sorted(reference_ports.items())},
        "input_count": len(inputs),
        "output_count": len(outputs),
    }


def deterministic_export(module: Any) -> tuple[str, dict[str, Any]]:
    """Generate the target RTL twice and require exact byte identity."""

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


def miter_text(inputs: dict[str, int], outputs: dict[str, int]) -> str:
    """Emit a miter whose mismatch ORs every declared output lane."""

    lines = [f"module {MODULE_NAME}_MITER("]
    body: list[str] = []
    for name, width in inputs.items():
        lines.append(f"  input [{width - 1}:0] {name}," if width > 1 else f"  input {name},")
    lines.append("  output mismatch")
    lines.append(");")
    for name, width in outputs.items():
        lines.append(f"  wire [{width - 1}:0] ref_{name};")
        lines.append(f"  wire [{width - 1}:0] dut_{name};")
    for prefix, instance in (("ref_", "reference_i"), ("dut_", "target_i")):
        connections = [f".{name}({name})" for name in inputs]
        for name in outputs:
            connections.append(f".{name}({prefix}{name})")
        top = f"REF_{MODULE_NAME}" if prefix == "ref_" else MODULE_NAME
        lines.append(f"  {top} {instance}(")
        lines.append("    " + ", ".join(connections))
        lines.append("  );")
    terms = [f"(ref_{name} != dut_{name})" for name in outputs]
    body.append("  assign mismatch = " + " | ".join(terms) + ";")
    lines.extend(body)
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def materialize(target_rtl: str, inputs: dict[str, int], outputs: dict[str, int]) -> dict[str, Path]:
    """Write target, renamed locked reference, and the derived miter."""

    reference_text = REFERENCE.read_text(encoding="utf-8")
    marker = f"module {MODULE_NAME}("
    if marker not in reference_text:
        raise AssertionError("locked reference declaration missing")
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)
    target = WORK / f"UHSC_{MODULE_NAME}.sv"
    reference = WORK / f"REF_{MODULE_NAME}.sv"
    miter = WORK / f"{MODULE_NAME}_MITER.sv"
    target.write_text(target_rtl, encoding="utf-8", newline="\n")
    reference.write_text(reference_text.replace(marker, f"module REF_{MODULE_NAME}(", 1),
                         encoding="utf-8", newline="\n")
    miter.write_text(miter_text(inputs, outputs), encoding="utf-8", newline="\n")
    return {"target": target, "reference": reference, "miter": miter}


def formal_gates(paths: dict[str, Path], inputs: dict[str, int],
                 outputs: dict[str, int]) -> dict[str, Any]:
    """Run lint, structural checks, and the unrestricted SAT equivalence."""

    converted = {name: wsl_path(path) for name, path in paths.items()}
    target, reference, miter = converted["target"], converted["reference"], converted["miter"]
    verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal", "--top-module",
                         f"{MODULE_NAME}_MITER", target, reference, miter])
    target_yosys = run_wsl(["yosys", "-Q", "-p",
                            f"read_verilog -sv {shlex.quote(target)}; hierarchy -top {MODULE_NAME}; proc; opt; check"])
    reference_yosys = run_wsl(["yosys", "-Q", "-p",
                               f"read_verilog -sv {shlex.quote(reference)}; "
                               f"hierarchy -top REF_{MODULE_NAME}; proc; opt; check"])
    proof_script = (f"read_verilog -sv {shlex.quote(target)} {shlex.quote(reference)} "
                    f"{shlex.quote(miter)}; prep -top {MODULE_NAME}_MITER; flatten; opt; "
                    "sat -prove mismatch 0")
    proof = run_wsl(["yosys", "-Q", "-p", proof_script])
    proof["formal_success_marker"] = proof.get("sat_success_marker") is True
    proof["unconstrained"] = proof.get("unconstrained_marker") is True
    if not proof["formal_success_marker"] or not proof["unconstrained"]:
        proof["status"] = "FAIL"
    proof["formal_scope"] = {
        "input_bits": sum(inputs.values()),
        "input_space": f"2**{sum(inputs.values())}",
        "state_bits": 0,
        "state_space": "singleton (stateless combinational module)",
        "property": "mismatch == 0 for every 2-state input valuation",
        "outputs_compared": outputs,
    }
    return {"verilator": verilator, "yosys_target": target_yosys,
            "yosys_reference": reference_yosys, "yosys_formal_miter": proof}


def negative_control(paths: dict[str, Path], output_name: str) -> dict[str, Any]:
    """Mutate one compared lane on both sides and require SAT counterexamples."""

    results: dict[str, Any] = {}
    for side in ("target", "reference"):
        source = paths[side].read_text(encoding="utf-8")
        mutated, count = re.subn(
            rf"assign\s+{re.escape(output_name)}\s*=.*?;",
            f"assign {output_name} = '0;", source, count=1, flags=re.S)
        if count != 1:
            results[side] = {"status": "FAIL", "mutation_applied": False}
            continue
        mutant = WORK / f"MUTANT_{side}.sv"
        mutant.write_text(mutated, encoding="utf-8", newline="\n")
        selected = {**paths, side: mutant}
        converted = {name: wsl_path(path) for name, path in selected.items()}
        script = (f"read_verilog -sv {shlex.quote(converted['target'])} "
                  f"{shlex.quote(converted['reference'])} {shlex.quote(converted['miter'])}; "
                  f"prep -top {MODULE_NAME}_MITER; flatten; opt; sat -prove mismatch 0")
        verdict = run_wsl(["yosys", "-Q", "-p", script])
        output = verdict.get("output_tail", "")
        counterexample = verdict.get("sat_counterexample_marker") is True
        success = verdict.get("sat_success_marker") is True
        detected = verdict.get("returncode") == 0 and counterexample and not success
        results[side] = {"status": "PASS" if detected else "FAIL",
                         "mutation_applied": True,
                         "counterexample_marker": counterexample,
                         "success_marker_still_present": success,
                         "returncode": verdict.get("returncode"),
                         "output_tail": output[-900:]}
    return {"status": "PASS" if all(item["status"] == "PASS"
                                      for item in results.values()) else "FAIL",
            "control_output": output_name, "sides": results}


def validate() -> dict[str, Any]:
    """Run every strict gate and persist machine-readable evidence."""

    failures: list[str] = []
    sources, locks = source_lock()
    module = load_target()
    py_compile.compile(str(TARGET), doraise=True)
    py_compile.compile(str(Path(__file__)), doraise=True)
    inputs, outputs = surface()
    target_rtl, export = deterministic_export(module)
    abi = abi_audit(target_rtl, inputs, outputs)
    paths = materialize(target_rtl, inputs, outputs)
    gates = formal_gates(paths, inputs, outputs)
    control = negative_control(paths, sorted(outputs)[0])
    pyright = {"target": pyright_check(TARGET), "validator": pyright_check(Path(__file__))}
    if locks["status"] != "PASS":
        failures.append("source lock audit")
    if abi["status"] != "PASS":
        failures.append("ABI audit")
    if export["status"] != "PASS":
        failures.append("deterministic export mismatch")
    if not inputs or not outputs:
        failures.append("derived port surface is empty")
    if control["status"] != "PASS":
        failures.append("negative control")
    for name, result in pyright.items():
        if result["status"] != "PASS":
            failures.append(f"pyright {name}")
    for name, result in gates.items():
        if result["status"] != "PASS":
            failures.append(name)
    status = "COMPLETE_EQUIVALENCE" if not failures else "STRICT_PENDING"
    input_bits = sum(inputs.values())
    output_bits = sum(outputs.values())
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_STRICT_COMPLETE_EQUIVALENCE",
        "build_id": "Build-Cpu.Backend.Fu.Vector.Utils.VecDataSplitModule",
        "validator": Path(__file__).relative_to(ROOT).as_posix(),
        "status": status,
        "strict_complete_eligible": status == "COMPLETE_EQUIVALENCE",
        "strict_complete_count_delta": 1 if status == "COMPLETE_EQUIVALENCE" else 0,
        "acceptance_eligible": status == "COMPLETE_EQUIVALENCE",
        "source_commit": SOURCE_COMMIT,
        "audit_policy": {"require_negative_control": True,
                         "two_sided_negative_control": True,
                         "full_output_markers": True,
                         "scope_source": "locked XSTop specialization"},
        "scope": {
            "kind": "stateless_combinational_leaf",
            "configuration": "locked V2 vlen=128 splitter, inDataWidth=128, outDataWidth=128",
            "state_bits": 0,
            "state_boundary": "no clock/reset/register/memory; one combinational evaluation",
            "inputs": inputs,
            "outputs_compared": outputs,
            "input_bits": input_bits,
            "output_bits": output_bits,
            "input_space": f"2**{input_bits}",
            "input_space_cardinality": str(1 << input_bits),
            "surface_derivation": "input and output lanes are parsed from the locked "
                                  "VecDataSplitModule.sv declaration rather than restated by hand",
            "why_complete": "Yosys SAT proves the reduction-OR over all "
                            f"{len(outputs)} declared output lanes ({output_bits} bits) equals zero "
                            f"with all {input_bits} input bits unconstrained; the module holds no state.",
            "bounded_tests_counted": False,
        },
        "sources": sources,
        "checks": {
            "py_compile": {"status": "PASS"},
            "pyright": pyright,
            "source_lock": locks,
            "abi": abi,
            "deterministic_export": export,
            "negative_control": control,
            "formal": gates,
        },
        "failures": failures,
        "unclosed": [] if not failures else ["strict gates did not all pass"],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    return payload


def main() -> int:
    """Print strict status and return nonzero until every gate passes."""

    payload = validate()
    scope = payload["scope"]
    print(json.dumps({"status": payload["status"],
                      "strict_complete_eligible": payload["strict_complete_eligible"],
                      "input_bits": scope["input_bits"],
                      "output_lanes": len(scope["outputs_compared"]),
                      "failures": payload["failures"]}, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
