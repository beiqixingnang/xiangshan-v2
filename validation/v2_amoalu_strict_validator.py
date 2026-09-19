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
OUTPUT_BITS = sum(OUTPUT_WIDTHS.values())
PORT_SURFACE = {
    "io_mask": ("input", 8),
    "io_cmd": ("input", 5),
    "io_lhs": ("input", 64),
    "io_rhs": ("input", 64),
    "io_out": ("output", 64),
}
BUILD_ID = "Build-Cpu.Cache.Dcache.Mainpipe.AMOALU"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
LOCKED_XSTOP = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
XSTOP_BYTES = 228590583
EXPECTED_SCALA_SHA256 = "4d67206b88f9b3baf88d816cb90c2c4bdd70ff04509b9a60a9b4aab98a9f45fd"
EXPECTED_REFERENCE_SHA256 = "f7bb49ef88b9ab6ecec70f4fa9f1a92de32640a4b13f923813d42a6e80d171ba"
EXPECTED_TARGET_SHA256 = "cdb47ac9790136562d40e7778af9a8be54ad2016787afc7d6740e196a7d3a7d5"
SUCCESS_MARKER = "SAT proof finished - no model found: SUCCESS!"
FREE_INPUT_MARKER = "Final constraint equation: { } = { }"
TARGET_RELATIVE = TARGET.relative_to(ROOT).as_posix()
REFERENCE_RELATIVE = REFERENCE.relative_to(ROOT).as_posix()
SCALA_RELATIVE = SCALA.relative_to(ROOT).as_posix()
VALIDATOR_RELATIVE = Path(__file__).relative_to(ROOT).as_posix()


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
            # Verdict markers are computed from the complete output before the
            # bounded tail is retained.  A SAT counterexample is printed after
            # the verdict, so ``model found: FAIL!`` may fall outside the tail.
            "success_marker": SUCCESS_MARKER in output,
            "counterexample_marker": "model found: FAIL!" in output,
            "unconstrained_marker": FREE_INPUT_MARKER in output,
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


def _module_region(rtl: str, module_name: str) -> tuple[str, str]:
    """Return one module's header and body without crossing its endmodule."""

    start = rtl.find(f"module {module_name}(")
    if start < 0:
        return "", ""
    open_index = rtl.find("(", start)
    depth = 0
    close_index = -1
    for index in range(open_index, len(rtl)):
        if rtl[index] == "(":
            depth += 1
        elif rtl[index] == ")":
            depth -= 1
            if depth == 0:
                close_index = index
                break
    if close_index < 0:
        return "", ""
    end_index = rtl.find("endmodule", close_index)
    return (rtl[open_index + 1:close_index],
            rtl[close_index + 1:end_index if end_index >= 0 else len(rtl)])


def _split_items(text: str) -> list[str]:
    """Split a declaration list on commas outside packed/concatenated ranges."""

    items: list[str] = []
    current: list[str] = []
    depth = 0
    for char in text:
        if char in "[{(":
            depth += 1
        elif char in "]})":
            depth -= 1
        if char == "," and depth == 0:
            items.append("".join(current))
            current = []
        else:
            current.append(char)
    items.append("".join(current))
    return items


def _header_names(header: str) -> set[str]:
    """Extract names from a bare Amaranth module header."""

    stripped = re.sub(r"//[^\n]*", "", header)
    if re.search(r"\b(?:input|output)\b", stripped):
        return set()
    return set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", stripped))


def _classify_declarations(items: list[str]) -> dict[str, tuple[str, int]]:
    """Classify ANSI declarations, including Chisel continuation names."""

    result: dict[str, tuple[str, int]] = {}
    pending: tuple[str, int] | None = None
    for item in items:
        entry = " ".join(re.sub(r"//[^\n]*", "", item).split())
        if not entry:
            continue
        entry = entry.rstrip(";")
        match = re.match(
            r"^(input|output)\b(?:\s*\[(\d+):0\])?\s*"
            r"([A-Za-z_][A-Za-z0-9_]*)?$", entry)
        if match is not None:
            direction, msb, name = match.groups()
            pending = (direction, int(msb) + 1 if msb is not None else 1)
            if name is not None:
                result[name] = pending
            continue
        if pending is not None and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", entry):
            result[entry] = pending
            continue
        pending = None
    return result


def declared_ports(rtl: str, module_name: str) -> dict[str, tuple[str, int]]:
    """Parse the exact external input/output surface of one module."""

    header, body = _module_region(rtl, module_name)
    clean_header = re.sub(r"//[^\n]*", "", header)
    if re.search(r"\b(?:input|output)\b", clean_header):
        return _classify_declarations(_split_items(clean_header))
    names = _header_names(clean_header)
    declarations: list[str] = []
    for line in body.splitlines():
        code = re.sub(r"//[^\n]*", "", line).strip()
        match = re.match(
            r"^(input|output)\b(?:\s*\[(\d+):0\])?\s*"
            r"([A-Za-z_][A-Za-z0-9_]*)?;?$", code)
        if match is None:
            continue
        direction, msb, name = match.groups()
        if name is not None and name in names:
            declarations.append(
                f"{direction} [{int(msb)}:0] {name}" if msb is not None
                else f"{direction} {name}")
    return _classify_declarations(declarations)


def source_lock_audit() -> dict[str, Any]:
    """Hash and provenance-check every locked input before elaboration."""

    paths = {"scala": SCALA, "reference_sv": REFERENCE, "python_build": TARGET}
    missing = [name for name, path in paths.items() if not path.is_file()]
    actual = {name: sha256_file(path) for name, path in paths.items() if path.is_file()}
    checks = {
        "all_sources_present": not missing,
        "scala_hash_locked": actual.get("scala") == EXPECTED_SCALA_SHA256,
        "reference_hash_locked": actual.get("reference_sv") == EXPECTED_REFERENCE_SHA256,
        "python_build_hash_recorded": actual.get("python_build") == EXPECTED_TARGET_SHA256,
        "source_commit_recorded": bool(SOURCE_COMMIT),
        "xstop_lock_recorded": len(XSTOP_SHA256) == 64 and XSTOP_BYTES > 0,
        "reference_module_marker": bool(
            REFERENCE.is_file() and "module AMOALU(" in REFERENCE.read_text(encoding="utf-8")),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "missing": missing,
        "actual": actual,
        "expected": {"scala": EXPECTED_SCALA_SHA256,
                      "reference_sv": EXPECTED_REFERENCE_SHA256,
                      "python_build": EXPECTED_TARGET_SHA256},
        "source_commit": SOURCE_COMMIT,
        "xstop": {"path": LOCKED_XSTOP, "sha256": XSTOP_SHA256,
                  "bytes": XSTOP_BYTES},
    }


def identity_audit() -> dict[str, Any]:
    """Ensure evidence identity, Build ID, and source paths cannot drift."""

    checks = {
        "build_id_exact": BUILD_ID == "Build-Cpu.Cache.Dcache.Mainpipe.AMOALU",
        "validator_path_exact": VALIDATOR_RELATIVE == "validation/v2_amoalu_strict_validator.py",
        "target_path_exact": TARGET_RELATIVE == (
            "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/"
            "Build-Cpu.Cache.Dcache.Mainpipe.AMOALU-Hardware.py"),
        "reference_path_exact": REFERENCE_RELATIVE == "validation/reference-closures/AMOALU-dcache-v2.sv",
        "scala_path_exact": SCALA_RELATIVE == "upstream/src/main/scala/xiangshan/cache/dcache/mainpipe/AMOALU.scala",
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks,
            "build_id": BUILD_ID, "validator": VALIDATOR_RELATIVE,
            "target": TARGET_RELATIVE, "reference": REFERENCE_RELATIVE,
            "scala": SCALA_RELATIVE}


def abi_audit(target_rtl: str, reference_rtl: str, miter_rtl: str) -> dict[str, Any]:
    """Require the exact five-port ABI and compare every locked output lane."""

    target_ports = declared_ports(target_rtl, "UHSC_AMOALU")
    reference_ports = declared_ports(reference_rtl, "REF_AMOALU")
    expected = dict(PORT_SURFACE)
    checks: dict[str, bool] = {
        "target_module": "module UHSC_AMOALU(" in target_rtl,
        "reference_module": "module REF_AMOALU(" in reference_rtl,
        "target_exact_port_set": target_ports == expected,
        "reference_exact_port_set": reference_ports == expected,
        "target_reference_port_sets_equal": target_ports == reference_ports,
        "every_output_compared": set(OUTPUT_WIDTHS) == {
            name for name, (direction, _) in reference_ports.items()
            if direction == "output"},
        "miter_has_mismatch": "assign mismatch" in miter_rtl,
        "miter_reduction_compares_io_out": (
            "reference_out ^ target_out" in miter_rtl),
    }
    for name in expected:
        checks[f"miter_connects_{name}_twice"] = miter_rtl.count(f".{name}(") == 2
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "target_declared_ports": {k: list(v) for k, v in sorted(target_ports.items())},
        "reference_declared_ports": {k: list(v) for k, v in sorted(reference_ports.items())},
        "expected_declared_ports": {k: list(v) for k, v in sorted(expected.items())},
        "inputs": INPUT_WIDTHS, "outputs_compared": OUTPUT_WIDTHS,
        "port_count": len(expected), "output_bits_compared": OUTPUT_BITS,
    }


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
    proof["formal_success_marker"] = bool(proof.get(
        "success_marker", SUCCESS_MARKER in proof.get("output_tail", "")))
    if not proof["formal_success_marker"]:
        proof["status"] = "FAIL"
    proof["unconstrained"] = bool(proof.get(
        "unconstrained_marker", FREE_INPUT_MARKER in proof.get("output_tail", "")))
    proof["miter_carries_no_assumption"] = proof["unconstrained"]
    if not proof["unconstrained"]:
        proof["status"] = "FAIL"
    miter_source = paths["miter"].read_text(encoding="utf-8")
    proof["miter_has_assume"] = bool(re.search(r"\b(?:assume|restrict|assert)\b",
                                                miter_source, flags=re.I))
    if proof["miter_has_assume"]:
        proof["status"] = "FAIL"
    proof["miter_output_bits"] = OUTPUT_BITS
    proof["formal_scope"] = {
        "input_bits": INPUT_BITS,
        "input_space": f"2**{INPUT_BITS}",
        "input_space_cardinality": str(1 << INPUT_BITS),
        "state_bits": 0,
        "state_space": "singleton (stateless combinational module)",
        "property": "mismatch == 0 for every 2-state valuation of io_mask/io_cmd/io_lhs/io_rhs",
        "outputs_compared": OUTPUT_WIDTHS,
        "no_assumptions": True,
    }
    return {
        "verilator": verilator,
        "yosys_target": target_yosys,
        "yosys_reference": reference_yosys,
        "yosys_formal_miter": proof,
    }


def _mutate_output(text: str, module: str, output_name: str,
                   width: int) -> tuple[str, bool, str]:
    """Replace exactly one parent output driver with a constant zero."""

    start = text.find(f"module {module}(")
    if start < 0:
        return text, False, "module-not-found"
    end = text.find("endmodule", start)
    if end < 0:
        return text, False, "endmodule-not-found"
    body = text[start:end]
    pattern = rf"assign\s+{re.escape(output_name)}\s*=\s*.*?;"
    mutated, count = re.subn(
        pattern, f"assign {output_name} = {width}'h0;", body,
        count=1, flags=re.S)
    if count == 1:
        return text[:start] + mutated + text[end:], True, "vector_assignment"
    return text, False, "output-driver-not-found"


def negative_control(paths: dict[str, Path]) -> dict[str, Any]:
    """Mutate target and reference output drivers and require SAT models."""

    results: dict[str, Any] = {}
    for side in ("target", "reference"):
        source = paths[side]
        module = "UHSC_AMOALU" if side == "target" else "REF_AMOALU"
        mutated, applied, mutation_kind = _mutate_output(
            source.read_text(encoding="utf-8"), module, "io_out", OUTPUT_BITS)
        if not applied:
            results[side] = {"status": "FAIL", "mutation_applied": False,
                             "mutation_kind": mutation_kind}
            continue
        mutant = WORK / f"MUTANT_{side}_AMOALU.sv"
        mutant.write_text(mutated, encoding="utf-8", newline="\n")
        selected = {**paths, side: mutant}
        converted = {name: wsl_path(path) for name, path in selected.items()}
        script = (f"read_verilog -sv {shlex.quote(converted['target'])} "
                  f"{shlex.quote(converted['reference'])} "
                  f"{shlex.quote(converted['miter'])}; "
                  "prep -top AMOALU_MITER; flatten; opt; sat -prove mismatch 0")
        verdict = run_wsl(["yosys", "-Q", "-p", script])
        tail = verdict.get("output_tail", "")
        success_marker = bool(verdict.get(
            "success_marker", SUCCESS_MARKER in tail))
        counterexample_marker = bool(verdict.get(
            "counterexample_marker", "model found: FAIL!" in tail))
        detected = verdict.get("returncode") == 0 and not success_marker \
            and counterexample_marker
        results[side] = {
            "status": "PASS" if detected else "FAIL",
            "mutation_applied": True,
            "mutation_kind": mutation_kind,
            "counterexample_marker": counterexample_marker,
            "success_marker_still_present": success_marker,
            "output_tail": tail[-1200:],
        }
    return {"status": "PASS" if all(item["status"] == "PASS"
                                     for item in results.values()) else "FAIL",
            "control_output": "io_out", "sides": results}


# Assemble and persist the evidence record; never claim complete equivalence on
# a failed gate.  The caller can use ``strict_complete_eligible`` as the count
# input without changing any top-level manifest or root metric.
def validate() -> dict[str, Any]:
    """Run all strict gates and write the machine-readable evidence record."""

    failures: list[str] = []
    locks = source_lock_audit()
    identity = identity_audit()
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
    pyright = {
        "target": pyright_check(TARGET),
        "validator": pyright_check(Path(__file__)),
    }
    if export["status"] != "PASS":
        failures.append("deterministic export mismatch")
    if locks["status"] != "PASS":
        failures.append("source lock audit")
    if identity["status"] != "PASS":
        failures.append("Build ID/path identity audit")
    if abi["status"] != "PASS":
        failures.append("ABI/miter audit")
    if control["status"] != "PASS":
        failures.append("negative control")
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
        "source_commit": SOURCE_COMMIT,
        "audit_policy": {
            "require_negative_control": True,
            "scope_source": "locked AMOALU reference closure",
            "require_unconstrained_sat": True,
            "require_all_declared_outputs_compared": True,
        },
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
            "output_bits_compared": OUTPUT_BITS,
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
        "reference_lock": {
            "path": REFERENCE_RELATIVE,
            "upstream_source_commit": SOURCE_COMMIT,
            "xstop_sha256": XSTOP_SHA256,
            "xstop_bytes": XSTOP_BYTES,
            "scala_path": SCALA_RELATIVE,
            "scala_sha256": locks["actual"].get("scala"),
            "reference_sha256": locks["actual"].get("reference_sv"),
            "closure_policy": "reference bytes are copied verbatim and only the top module is renamed to REF_AMOALU in the temporary work directory",
        },
        "checks": {
            "py_compile": {"status": "PASS"},
            "pyright": pyright,
            "source_lock": locks,
            "identity": identity,
            "abi": abi,
            "deterministic_export": export,
            "tools": tool_versions(),
            "formal": gates,
            "negative_control": control,
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
