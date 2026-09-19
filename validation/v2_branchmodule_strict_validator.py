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
OUTPUT_BITS = sum(OUTPUT_WIDTHS.values())
PORT_SURFACE = {
    "io_src_0": ("input", 64),
    "io_src_1": ("input", 64),
    "io_func": ("input", 9),
    "io_pred_taken": ("input", 1),
    "io_taken": ("output", 1),
    "io_mispredict": ("output", 1),
}
BUILD_ID = "Build-Cpu.Backend.Fu.BranchModule"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
LOCKED_XSTOP = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
XSTOP_BYTES = 228590583
EXPECTED_SCALA_SHA256 = "2553218c21dc4eb5368ae122c47a42b8d3873e326c5f381119a3651998508953"
EXPECTED_SCALA_SUB_SHA256 = "7f4e7f5f2f463216330efa02c5b8a0d42e02a2345e339bca4d2a633e374ee287"
EXPECTED_REFERENCE_SHA256 = "2f62a3e9fd5bbe51af539adc594d15f0ca2c75059cfde022b8051addb61dbd5a"
EXPECTED_TARGET_SHA256 = "d95127c09e3f1f319ecc8660afc875f6e5f521a07485153c06fa8fa52e3fbef3"
SUCCESS_MARKER = "SAT proof finished - no model found: SUCCESS!"
FREE_INPUT_MARKER = "Final constraint equation: { } = { }"
TARGET_RELATIVE = TARGET.relative_to(ROOT).as_posix()
REFERENCE_RELATIVE = REFERENCE.relative_to(ROOT).as_posix()
SCALA_RELATIVE = SCALA.relative_to(ROOT).as_posix()
SCALA_SUB_RELATIVE = SCALA_SUB.relative_to(ROOT).as_posix()
VALIDATOR_RELATIVE = Path(__file__).relative_to(ROOT).as_posix()


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
            # Capture markers from complete output before retaining a bounded
            # tail; SAT models are printed after the verdict line.
            "success_marker": SUCCESS_MARKER in output,
            "counterexample_marker": "model found: FAIL!" in output,
            "unconstrained_marker": FREE_INPUT_MARKER in output,
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


def _module_region(rtl: str, module_name: str) -> tuple[str, str]:
    """Return one module's header/body without crossing its endmodule."""

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
    """Split a declaration list on commas outside packed ranges."""

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
    """Classify ANSI declarations, including continuation names."""

    result: dict[str, tuple[str, int]] = {}
    pending: tuple[str, int] | None = None
    for item in items:
        entry = " ".join(re.sub(r"//[^\n]*", "", item).split()).rstrip(";")
        if not entry:
            continue
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
    """Parse the exact external port direction/width map of one module."""

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

    paths = {"scala": SCALA, "scala_dependency": SCALA_SUB,
             "reference_sv": REFERENCE, "python_build": TARGET}
    missing = [name for name, path in paths.items() if not path.is_file()]
    actual = {name: sha256_file(path) for name, path in paths.items() if path.is_file()}
    checks = {
        "all_sources_present": not missing,
        "scala_hash_locked": actual.get("scala") == EXPECTED_SCALA_SHA256,
        "scala_dependency_hash_locked": actual.get("scala_dependency") == EXPECTED_SCALA_SUB_SHA256,
        "reference_hash_locked": actual.get("reference_sv") == EXPECTED_REFERENCE_SHA256,
        "python_build_hash_recorded": actual.get("python_build") == EXPECTED_TARGET_SHA256,
        "source_commit_recorded": bool(SOURCE_COMMIT),
        "xstop_lock_recorded": len(XSTOP_SHA256) == 64 and XSTOP_BYTES > 0,
        "reference_modules_present": bool(
            REFERENCE.is_file()
            and "module SubModule(" in REFERENCE.read_text(encoding="utf-8")
            and "module BranchModule(" in REFERENCE.read_text(encoding="utf-8")),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks, "missing": missing, "actual": actual,
        "expected": {"scala": EXPECTED_SCALA_SHA256,
                      "scala_dependency": EXPECTED_SCALA_SUB_SHA256,
                      "reference_sv": EXPECTED_REFERENCE_SHA256,
                      "python_build": EXPECTED_TARGET_SHA256},
        "source_commit": SOURCE_COMMIT,
        "xstop": {"path": LOCKED_XSTOP, "sha256": XSTOP_SHA256,
                  "bytes": XSTOP_BYTES},
    }


def identity_audit() -> dict[str, Any]:
    """Ensure Build ID and every evidence source path are bound exactly."""

    checks = {
        "build_id_exact": BUILD_ID == "Build-Cpu.Backend.Fu.BranchModule",
        "validator_path_exact": VALIDATOR_RELATIVE == "validation/v2_branchmodule_strict_validator.py",
        "target_path_exact": TARGET_RELATIVE == (
            "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
            "Build-Cpu.Backend.Fu.BranchModule-Hardware.py"),
        "reference_path_exact": REFERENCE_RELATIVE == "validation/reference-closures/BranchModule-v2.sv",
        "scala_path_exact": SCALA_RELATIVE == "upstream/src/main/scala/xiangshan/backend/fu/Branch.scala",
        "scala_dependency_path_exact": SCALA_SUB_RELATIVE == "upstream/src/main/scala/xiangshan/backend/fu/Alu.scala",
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks,
            "build_id": BUILD_ID, "validator": VALIDATOR_RELATIVE,
            "target": TARGET_RELATIVE, "reference": REFERENCE_RELATIVE,
            "scala": SCALA_RELATIVE, "scala_dependency": SCALA_SUB_RELATIVE}


def abi_audit(target_rtl: str, reference_rtl: str, miter_rtl: str) -> dict[str, Any]:
    """Require all six locked ports and both output bits in the miter."""

    target_ports = declared_ports(target_rtl, "BranchModule")
    reference_ports = declared_ports(reference_rtl, "REF_BranchModule")
    expected = dict(PORT_SURFACE)
    checks: dict[str, bool] = {
        "target_module": "module BranchModule(" in target_rtl,
        "reference_module": "module REF_BranchModule(" in reference_rtl,
        "reference_child_submodule": "module SubModule(" in reference_rtl,
        "target_exact_port_set": target_ports == expected,
        "reference_exact_port_set": reference_ports == expected,
        "target_reference_port_sets_equal": target_ports == reference_ports,
        "every_output_compared": set(OUTPUT_WIDTHS) == {
            name for name, (direction, _) in reference_ports.items()
            if direction == "output"},
        "miter_has_mismatch": "assign mismatch" in miter_rtl,
        "miter_compares_taken": "ref_taken ^ dut_taken" in miter_rtl,
        "miter_compares_mispredict": "ref_mispredict ^ dut_mispredict" in miter_rtl,
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
        "property": "mismatch == 0 for every 2-state input valuation",
        "outputs_compared": OUTPUT_WIDTHS,
        "no_assumptions": True,
    }
    return {"verilator": verilator, "yosys_target": target_yosys,
            "yosys_reference": reference_yosys, "yosys_formal_miter": proof}


def _mutate_output(text: str, module: str, output_name: str) -> tuple[str, bool, str]:
    """Replace exactly one scalar output driver with a constant zero."""

    start = text.find(f"module {module}(")
    if start < 0:
        return text, False, "module-not-found"
    end = text.find("endmodule", start)
    if end < 0:
        return text, False, "endmodule-not-found"
    body = text[start:end]
    pattern = rf"assign\s+{re.escape(output_name)}\s*=\s*.*?;"
    mutated, count = re.subn(
        pattern, f"assign {output_name} = 1'b0;", body,
        count=1, flags=re.S)
    if count == 1:
        return text[:start] + mutated + text[end:], True, "scalar_assignment"
    return text, False, "output-driver-not-found"


def negative_control(paths: dict[str, Path]) -> dict[str, Any]:
    """Mutate one output on each side and require SAT counterexamples."""

    output_name = "io_taken"
    results: dict[str, Any] = {}
    for side in ("target", "reference"):
        source = paths[side]
        module = "BranchModule" if side == "target" else "REF_BranchModule"
        mutated, applied, mutation_kind = _mutate_output(
            source.read_text(encoding="utf-8"), module, output_name)
        if not applied:
            results[side] = {"status": "FAIL", "mutation_applied": False,
                             "mutation_kind": mutation_kind}
            continue
        mutant = WORK / f"MUTANT_{side}_BranchModule.sv"
        mutant.write_text(mutated, encoding="utf-8", newline="\n")
        selected = {**paths, side: mutant}
        converted = {name: wsl_path(path) for name, path in selected.items()}
        script = (f"read_verilog -sv {shlex.quote(converted['target'])} "
                  f"{shlex.quote(converted['reference'])} "
                  f"{shlex.quote(converted['miter'])}; "
                  "prep -top BranchModule_MITER; flatten; opt; sat -prove mismatch 0")
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
            "mutated_output": output_name,
            "counterexample_marker": counterexample_marker,
            "success_marker_still_present": success_marker,
            "output_tail": tail[-1200:],
        }
    return {"status": "PASS" if all(item["status"] == "PASS"
                                     for item in results.values()) else "FAIL",
            "control_output": output_name, "sides": results}


# Assemble evidence; never claim COMPLETE_EQUIVALENCE after a failed gate.
def validate() -> dict[str, Any]:
    """Run all strict gates and write machine-readable evidence."""

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
    pyright = {"target": pyright_check(TARGET),
               "validator": pyright_check(Path(__file__))}
    failures: list[str] = []
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
        "source_commit": SOURCE_COMMIT,
        "audit_policy": {
            "require_negative_control": True,
            "scope_source": "locked BranchModule reference closure",
            "require_unconstrained_sat": True,
            "require_all_declared_outputs_compared": True,
        },
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
            "output_bits_compared": OUTPUT_BITS,
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
                             "locked_xstop_sha256": XSTOP_SHA256,
                             "locked_xstop_module_lines": [1198215, 1198236]},
            "python_build": {"path": TARGET.relative_to(ROOT).as_posix(),
                             "sha256": sha256_file(TARGET), "bytes": TARGET.stat().st_size},
        },
        "reference_lock": {
            "path": REFERENCE_RELATIVE,
            "upstream_source_commit": SOURCE_COMMIT,
            "xstop_sha256": XSTOP_SHA256,
            "xstop_bytes": XSTOP_BYTES,
            "scala_path": SCALA_RELATIVE,
            "scala_dependency_path": SCALA_SUB_RELATIVE,
            "scala_sha256": locks["actual"].get("scala"),
            "scala_dependency_sha256": locks["actual"].get("scala_dependency"),
            "reference_sha256": locks["actual"].get("reference_sv"),
            "child_modules": ["SubModule", "BranchModule"],
            "closure_policy": "reference bytes are copied verbatim and only BranchModule is renamed to REF_BranchModule in the temporary work directory",
        },
        "checks": {"python_version": platform.python_version(),
                    "py_compile": {"status": "PASS", "files": [
                        TARGET.relative_to(ROOT).as_posix(),
                        Path(__file__).relative_to(ROOT).as_posix()]},
                    "pyright": pyright, "source_lock": locks,
                    "identity": identity, "abi": abi,
                    "deterministic_export": export, "tools": tool_versions(),
                    "formal": gates, "negative_control": control},
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
