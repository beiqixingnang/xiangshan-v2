"""Strict inductive-equivalence proof for the locked V2 InstrMMIOEntry.

The reference is a four-state, single-clock engine with no child instances, so
asynchronous reset semantics are normalized with async2sync and the whole
transition relation is discharged by equiv_induct rather than by a bounded
vector set.  The compared port surface is parsed from the locked reference and
the run carries a built-in negative control, because an equivalence harness
that cannot fail cannot prove anything.
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
    "Build-Cpu.Frontend.Icache.InstrMMIOEntry-Hardware.py"
)
SCALA = ROOT / "upstream/src/main/scala/xiangshan/frontend/icache/InstrUncache.scala"
REFERENCE = ROOT / "validation/reference-sv/InstrMMIOEntry.sv"
EVIDENCE = ROOT / "validation/v2-instrmmioentry-strict-evidence.json"
MODULE_NAME = "InstrMMIOEntry"
CONTROL_PORT = "io_resp_valid"
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_instrmmioentry_strict"

SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
EQUIV_MARKERS = ("0 are unproven.", "Equivalence successfully proven!")
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
    """Read a Chisel ANSI declaration, letting grouped names inherit width."""

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
    """Read an Amaranth header-plus-body declaration."""

    header = re.search(r"module\s+" + re.escape(module) + r"\s*\(([^)]*)\)\s*;", rtl, re.S)
    if header is None:
        return {}
    wanted = [item for item in
              (name.strip() for name in
               strip_comments(header.group(1)).replace("\n", " ").split(",")) if item]
    ports: dict[str, tuple[str, int]] = {}
    for raw in rtl[header.end():].splitlines():
        declared = ANSI_PORT.match(strip_comments(raw).rstrip(";").strip())
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

    spec = importlib.util.spec_from_file_location("strict_instrmmioentry_target", TARGET)
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
        return {"command": command, "status": "FAIL", "error": repr(error)}
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {
        "command": command,
        "returncode": result.returncode,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "output_tail": output[-5000:],
        "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
    }


def pyright_check(source: Path) -> dict[str, Any]:
    """Run Pyright on an exact visible copy of one source file."""

    temporary = Path(tempfile.mkdtemp(prefix="uhsc_instrmmioentry_pyright_"))
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


REMOVED_REGIONS = ("`ifndef SYNTHESIS", "`ifdef ENABLE_INITIAL_REG_")
BLOCK_LOCAL = re.compile(
    r"^([ \t]*)automatic\s+logic\s+(\[[^\]]*\])?\s*([A-Za-z_][A-Za-z0-9_]*)\s*;[ \t]*$", re.M)
NESTED_OPEN = re.compile(r"^\s*`(ifdef|ifndef|else|elsif)\b")
NESTED_CLOSE = re.compile(r"^\s*`endif\b")


def directive_block_end(lines: list[str], start: int) -> int:
    """Return the index just past the `endif closing the directive at start."""

    depth = 0
    for index in range(start, len(lines)):
        if NESTED_OPEN.match(lines[index]):
            depth += 1
        elif NESTED_CLOSE.match(lines[index]):
            depth -= 1
            if depth == 0:
                return index + 1
    raise AssertionError("unterminated preprocessor region")


def strip_directives(text: str) -> tuple[str, dict[str, int]]:
    """Drop the non-synthesis conditional regions from comment-stripped text."""

    lines = text.split("\n")
    removed: dict[str, int] = {}
    for opening in REMOVED_REGIONS:
        start = next((i for i, line in enumerate(lines) if opening in line), None)
        if start is None:
            continue
        end = directive_block_end(lines, start)
        removed[opening] = end - start
        lines = lines[:start] + lines[end:]
    return "\n".join(lines), removed


def reference_synthesizable_view(locked_text: str) -> tuple[str, dict[str, Any]]:
    """Build the Yosys-readable view of the locked reference, per rules 5C.

    Only inert region removal and block-local declaration hoisting are allowed,
    and the returned audit fails if any other code line moved.
    """

    marker = f"module {MODULE_NAME}("
    if not locked_text.startswith(marker):
        raise AssertionError("locked reference declaration marker missing")
    body = "\n".join(strip_comments(line) for line in locked_text.split("\n"))
    body, removed = strip_directives(body)
    residual = [line for line in body.split("\n") if "`" in line]
    if residual:
        raise AssertionError(f"preprocessor directive survived region removal: {residual[0][:60]}")

    temporaries = [(match.group(2), match.group(3)) for match in BLOCK_LOCAL.finditer(body)]
    if not temporaries:
        raise AssertionError("no block-local temporaries found; view assumption stale")
    declarations = "".join(f"  reg {width} {name};\n" if width else f"  reg {name};\n"
                           for width, name in temporaries)
    stripped = BLOCK_LOCAL.sub("", body)
    header_end = stripped.index(");") + 2
    normalized = stripped[:header_end] + "\n" + declarations + stripped[header_end:]
    if "automatic" in normalized:
        raise AssertionError("automatic declaration survived hoisting")
    renamed = normalized.replace(marker, f"module {MODULE_NAME}_ref(", 1)

    body_lines = [line for line in body.split("\n") if line.strip()]
    view_lines = [line for line in normalized.split("\n") if line.strip()]
    body_set, view_set = set(body_lines), set(view_lines)
    disappeared = [line for line in body_lines if line not in view_set]
    appeared = [line for line in view_lines if line not in body_set]
    expected = [f"  reg {width} {name};" if width else f"  reg {name};"
                for width, name in temporaries]
    conserved = (all(BLOCK_LOCAL.match(line) is not None for line in disappeared)
                 and len(disappeared) == len(temporaries)
                 and sorted(appeared) == sorted(expected))
    locked_registers = re.findall(r"^\s*([A-Za-z_]\w*)\s*<=\s*(.+);$", body, re.M)
    view_registers = re.findall(r"^\s*([A-Za-z_]\w*)\s*<=\s*(.+);$", normalized, re.M)
    audit = {
        "policy": "the locked reference under validation/reference-sv is opened read-only and "
                  "never written; the synthesizable view exists only in a temporary work directory",
        "regions_removed_lines": removed,
        "block_local_temporaries_hoisted": [name for _, name in temporaries],
        "code_lines_locked": len(body_lines),
        "code_lines_view": len(view_lines),
        "residual_preprocessor_directives": len(residual),
        "line_conservation_ok": conserved,
        "register_update_equations_locked": len(locked_registers),
        "register_update_equations_preserved": locked_registers == view_registers,
    }
    audit["view_trusted"] = bool(conserved and audit["register_update_equations_preserved"]
                                 and not residual and locked_registers)
    return renamed, audit


def port_surface() -> tuple[dict[str, int], dict[str, int]]:
    """Derive the compared input and output widths from the locked reference."""

    ports = declared_ports(REFERENCE.read_text(encoding="utf-8"), MODULE_NAME)
    inputs = {name: width for name, (direction, width) in ports.items() if direction == "input"}
    outputs = {name: width for name, (direction, width) in ports.items() if direction == "output"}
    return inputs, outputs


def abi_audit(target_rtl: str, inputs: dict[str, int], outputs: dict[str, int]) -> dict[str, Any]:
    """Require the target to declare exactly the locked port surface."""

    reference_rtl = REFERENCE.read_text(encoding="utf-8")
    reference_ports = declared_ports(reference_rtl, MODULE_NAME)
    target_ports = declared_ports(target_rtl, MODULE_NAME)
    checks: dict[str, bool] = {
        "target_module": f"module {MODULE_NAME}(" in target_rtl,
        "reference_module": f"module {MODULE_NAME}(" in reference_rtl and bool(reference_ports),
        "target_surface_equals_reference": target_ports == reference_ports,
        "no_extra_target_ports": set(target_ports) == set(reference_ports),
        "every_output_compared": set(outputs)
                                 == {name for name, (d, _) in reference_ports.items() if d == "output"},
        "surface_is_not_empty": bool(inputs) and bool(outputs),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "target_declared_ports": {k: list(v) for k, v in sorted(target_ports.items())},
        "reference_declared_ports": {k: list(v) for k, v in sorted(reference_ports.items())},
        "inputs": inputs,
        "outputs_compared": outputs,
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


def materialize(target_rtl: str) -> tuple[dict[str, Path], dict[str, Any]]:
    """Write target plus the renamed 5C view of the locked reference."""

    locked_text = REFERENCE.read_text(encoding="utf-8")
    if re.search(r"^\s*[A-Z]\w*\s+\S+\s*\(", locked_text, re.M):
        raise AssertionError("unexpected child instance in locked reference; closure assembly required")
    view, audit = reference_synthesizable_view(locked_text)
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)
    target = WORK / f"{MODULE_NAME}-target.sv"
    reference = WORK / f"{MODULE_NAME}-reference.sv"
    target.write_text(target_rtl, encoding="utf-8", newline="\n")
    reference.write_text(view, encoding="utf-8", newline="\n")
    return {"target": target, "reference": reference}, audit


def equiv_run(target: str, reference: str) -> dict[str, Any]:
    """Discharge the full transition relation by induction."""

    script = (f"read_verilog -sv {shlex.quote(target)} {shlex.quote(reference)}; "
              "proc; async2sync; memory; opt; "
              f"equiv_make {MODULE_NAME} {MODULE_NAME}_ref {MODULE_NAME}_equiv; "
              f"prep -top {MODULE_NAME}_equiv; equiv_induct -undef; equiv_status -assert")
    result = run_wsl(["yosys", "-Q", "-p", script])
    output = result.get("output_tail", "")
    result["markers_present"] = {marker: marker in output for marker in EQUIV_MARKERS}
    result["formal_success_marker"] = all(result["markers_present"].values())
    final = re.findall(r"Of those cells (\d+) are proven and (\d+) are unproven", output)
    totals = re.findall(r"Found (\d+) \$equiv cells in", output)
    assert_failure = re.findall(r"Found (\d+) unproven \$equiv cells in 'equiv_status -assert'", output)
    if final:
        result["proven_cells"] = int(final[-1][0])
        result["unproven_cells"] = int(final[-1][1])
    if totals:
        result["equiv_cells"] = int(totals[-1])
    if assert_failure:
        result["unproven_cells"] = int(assert_failure[-1])
    if result["returncode"] != 0 or not result["formal_success_marker"]:
        result["status"] = "FAIL"
    return result


def negative_control(paths: dict[str, Path]) -> dict[str, Any]:
    """Tie one observable output low and require the harness to report it."""

    target_rtl = paths["target"].read_text(encoding="utf-8")
    pattern = rf"assign\s+{CONTROL_PORT}\s*=\s*[^;]+;"
    mutated, count = re.subn(pattern, lambda _match: f"assign {CONTROL_PORT} = 1'b0;",
                             target_rtl, count=1)
    control_path = WORK / f"{MODULE_NAME}-mutant.sv"
    control_path.write_text(mutated, encoding="utf-8", newline="\n")
    if count != 1:
        return {
            "control_port": CONTROL_PORT,
            "mutation_applied": False,
            "status": "FAIL",
            "note": "the control driver was not found, so the harness was never challenged",
        }
    verdict = equiv_run(wsl_path(control_path), wsl_path(paths["reference"]))
    detected = not verdict["formal_success_marker"]
    return {
        "control_port": CONTROL_PORT,
        "mutation_applied": True,
        "unproven_cells": verdict.get("unproven_cells"),
        "markers_present": verdict.get("markers_present"),
        "status": "PASS" if detected else "FAIL",
        "note": "a mutated target must be reported as not equivalent, otherwise the "
                "harness is vacuous and a clean success would mean nothing",
        "output_tail": verdict.get("output_tail", "")[-1500:],
    }


def lint_and_check(paths: dict[str, Path]) -> dict[str, Any]:
    """Lint and structurally check both sides before the equivalence run."""

    target = wsl_path(paths["target"])
    reference = wsl_path(paths["reference"])
    return {
        "target_verilator": run_wsl(["verilator", "--lint-only", "-Wno-fatal", target]),
        "reference_verilator": run_wsl(["verilator", "--lint-only", "-Wno-fatal", reference]),
        "locked_reference_verilator": run_wsl([
            "verilator", "--lint-only", "-Wno-fatal", "--top-module", MODULE_NAME,
            wsl_path(REFERENCE)]),
        "target_yosys": run_wsl(["yosys", "-Q", "-p",
                                 f"read_verilog -sv {shlex.quote(target)}; proc; async2sync; opt; "
                                 f"hierarchy -top {MODULE_NAME}; check"]),
        "reference_yosys": run_wsl(["yosys", "-Q", "-p",
                                    f"read_verilog -sv {shlex.quote(reference)}; proc; async2sync; opt; "
                                    f"hierarchy -top {MODULE_NAME}_ref; check"]),
    }


def measured_state_bits() -> tuple[int, dict[str, int]]:
    """Sum the widths of the locked reference register declarations."""

    text = REFERENCE.read_text(encoding="utf-8")
    registers: dict[str, int] = {}
    for declared in re.finditer(r"^\s*reg\s+(?:\[(\d+):0\]\s*)?([^;]+);", text, re.M):
        width = int(declared.group(1)) + 1 if declared.group(1) else 1
        for name in [item.strip() for item in declared.group(2).split(",") if item.strip()]:
            registers[name] = width
    return sum(registers.values()), registers


def validate() -> dict[str, Any]:
    """Run every strict gate and persist machine-readable evidence."""

    failures: list[str] = []
    inputs, outputs = port_surface()
    sources = {
        name: {"path": path.relative_to(ROOT).as_posix(),
               "sha256": sha256_file(path),
               "bytes": path.stat().st_size}
        for name, path in (("scala", SCALA), ("reference_sv", REFERENCE), ("python_build", TARGET))
    }
    module = load_target()
    py_compile.compile(str(TARGET), doraise=True)
    py_compile.compile(str(Path(__file__)), doraise=True)
    target_rtl, export = deterministic_export(module)
    abi = abi_audit(target_rtl, inputs, outputs)
    paths, normalization = materialize(target_rtl)
    lints = lint_and_check(paths)
    control = negative_control(paths)
    proof = equiv_run(wsl_path(paths["target"]), wsl_path(paths["reference"]))
    pyright = {"target": pyright_check(TARGET), "validator": pyright_check(Path(__file__))}
    if not inputs or not outputs:
        failures.append("derived port surface is empty")
    if not normalization["view_trusted"]:
        failures.append("synthesizable view failed its conservation or equation-preservation audit")
    if abi["status"] != "PASS":
        failures.append("ABI audit")
    if export["status"] != "PASS":
        failures.append("deterministic export mismatch")
    for name, result in pyright.items():
        if result["status"] != "PASS":
            failures.append(f"pyright {name}")
    for name, result in lints.items():
        if result["status"] != "PASS":
            failures.append(name)
    if control["status"] != "PASS":
        failures.append("negative control did not detect a mutated target")
    if proof["status"] != "PASS":
        failures.append("yosys_equiv")
    if not proof.get("equiv_cells"):
        failures.append("no $equiv cells were matched, so the equivalence run is vacuous")
    elif proof.get("unproven_cells"):
        failures.append(f"{proof['unproven_cells']} $equiv cells remain unproven")
    status = "COMPLETE_EQUIVALENCE" if not failures else "STRICT_PENDING"
    state_bits, state_registers = measured_state_bits()
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_STRICT_COMPLETE_EQUIVALENCE",
        "build_id": "Build-Cpu.Frontend.Icache.InstrMMIOEntry",
        "validator": Path(__file__).relative_to(ROOT).as_posix(),
        "status": status,
        "strict_complete_eligible": status == "COMPLETE_EQUIVALENCE",
        "strict_complete_count_delta": 1 if status == "COMPLETE_EQUIVALENCE" else 0,
        "acceptance_eligible": status == "COMPLETE_EQUIVALENCE",
        "source_commit": SOURCE_COMMIT,
        "scope": {
            "kind": "sequential_registered_leaf",
            "configuration": "locked V2 single-entry uncached instruction transaction engine",
            "state_bits": state_bits,
            "state_registers": state_registers,
            "state_boundary": "four-state register, request address, response data/corrupt and "
                              "needFlush registers, all in one posedge clocked block",
            "inputs": inputs,
            "outputs_compared": outputs,
            "input_bits": sum(inputs.values()),
            "output_bits": sum(outputs.values()),
            "transition_relation": "all input sequences, posedge clock, async reset normalized by async2sync",
            "proof_cell_coverage": "equiv_status -assert requires every matched state and output cell",
            "why_complete": "Yosys equiv_induct -undef discharges the full transition relation; "
                            "a built-in negative control proves the harness reports a mutated target",
            "bounded_tests_counted": False,
        },
        "reference_lock": {
            "path": REFERENCE.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(REFERENCE),
            "xstop_sha256": "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d",
            "reference_module": MODULE_NAME,
            "child_instances": 0,
        },
        "sources": sources,
        "checks": {
            "py_compile": {"status": "PASS"},
            "reference_normalization": normalization,
            "pyright": pyright,
            "abi": abi,
            "deterministic_export": export,
            "formal": {
                "negative_control": control,
                **lints,
                "yosys_equiv": proof,
            },
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
    formal = payload["checks"]["formal"]
    print(json.dumps({
        "status": payload["status"],
        "strict_complete_eligible": payload["strict_complete_eligible"],
        "input_bits": payload["scope"]["input_bits"],
        "output_bits": payload["scope"]["output_bits"],
        "unproven_cells": formal["yosys_equiv"].get("unproven_cells"),
        "negative_control": formal["negative_control"]["status"],
        "pyright_error_counts": {k: v["error_count"] for k, v in payload["checks"]["pyright"].items()},
        "failures": payload["failures"],
    }, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
