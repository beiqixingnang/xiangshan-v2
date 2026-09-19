"""Strict inductive-equivalence proof for the locked V2 WRBypass leaf.

WrBypass is a registered content-addressed bypass check: it instantiates a
locked IndexableCAMTemplate child, it holds many one-bit valid registers, and its
locked reference carries both block-local ``automatic logic`` declarations and
non-synthesis conditional regions.  Everything about that reference is therefore
read through the section 5C synthesizable view, applied recursively to locked
children, and a line-conservation gate has to agree that nothing but inert region
removal and declaration hoisting happened.

The proof itself is ``equiv_induct`` over the flattened pair, so the whole
transition relation is discharged rather than sampled, and a two-sided negative
control shows the harness detects a perturbation on either side.
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
    "Build-Cpu.Frontend.Bpu.WrBypass-Hardware.py"
)
SCALA = ROOT / "upstream/src/main/scala/xiangshan/frontend/WrBypass.scala"
REF_DIR = ROOT / "validation/reference-sv"
EVIDENCE = ROOT / "validation/v2-wrbypass-strict-evidence.json"
MODULE_NAME = "WrBypass"
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_wrbypass_strict"

SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
EQUIV_MARKERS = ("0 are unproven.", "Equivalence successfully proven!")
ANSI_PORT = re.compile(r"^(input|output)\s+(?:\[(\d+):0\]\s*)?(.+)$")
BLOCK_LOCAL = re.compile(
    r"^([ \t]*)automatic\s+logic\s+(\[[^\]]*\])?\s*([A-Za-z_][A-Za-z0-9_]*)\s*;[ \t]*$", re.M)
INIT_DECL = re.compile(
    r"^([ \t]*)automatic\s+logic\s+(\[[^\]]*\])?\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+);\s*$", re.M)
REMOVED_REGIONS = ("`ifndef SYNTHESIS", "`ifdef ENABLE_INITIAL_REG_",
                   "`ifdef ENABLE_INITIAL_MEM_")
NESTED_OPEN = re.compile(r"^\s*`(ifdef|ifndef|else|elsif)\b")
NESTED_CLOSE = re.compile(r"^\s*`endif\b")
INSTANCE = re.compile(r"^\s*([A-Za-z_]\w*)\s+[A-Za-z_]\w*\s*\(", re.M)
REGISTER_UPDATE = re.compile(r"^\s*[A-Za-z_$][\w$]*\s*<=\s*.+;$", re.M)


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one exact file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def strip_line(line: str) -> str:
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
        line = strip_line(raw).rstrip(",").strip()
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
    wanted = [item for item in (name.strip() for name in
                                strip_line(header.group(1)).replace("\n", " ").split(",")) if item]
    ports: dict[str, tuple[str, int]] = {}
    for raw in rtl[header.end():].splitlines():
        declared = ANSI_PORT.match(strip_line(raw).rstrip(";").strip())
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
    """Load the WrBypass Build by exact path."""

    spec = importlib.util.spec_from_file_location("strict_wrbypass_target", TARGET)
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
    return {"command": command, "returncode": result.returncode,
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "output_tail": output[-4000:],
            "output_sha256": hashlib.sha256(output.encode()).hexdigest()}


def pyright_check(source: Path) -> dict[str, Any]:
    """Run Pyright on an exact visible copy of one source file."""

    temporary = Path(tempfile.mkdtemp(prefix="uhsc_wrbypass_pyright_"))
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
                "error_count": summary.get("errorCount"),
                "files_analyzed": summary.get("filesAnalyzed"),
                "stderr_tail": result.stderr[-600:]}
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def directive_block_end(lines: list[str], start: int) -> int:
    """Return the index just past the endif closing the directive at start."""

    depth = 0
    for index in range(start, len(lines)):
        if NESTED_OPEN.match(lines[index]):
            depth += 1
        elif NESTED_CLOSE.match(lines[index]):
            depth -= 1
            if depth == 0:
                return index + 1
    raise AssertionError("unterminated preprocessor region")


def insert_declarations(stripped: str, declarations: str, marker: str) -> str:
    """Place hoisted module-scope declarations just after the module header."""

    start = stripped.index(marker) + len(marker)
    header_end = stripped.index(");", start) + 2
    return stripped[:header_end] + "\n" + declarations + stripped[header_end:]


def synthesizable_view(text: str, top: str, rename: bool) -> tuple[str, dict[str, Any]]:
    """Apply the section 5C view to one locked module body."""

    marker = f"module {top}("
    lines = [line for line in (strip_line(raw) for raw in text.split("\n")) if line]
    removed: dict[str, int] = {}
    for opening in REMOVED_REGIONS:
        start = next((i for i, line in enumerate(lines) if opening in line), None)
        if start is None:
            continue
        end = directive_block_end(lines, start)
        removed[opening] = end - start
        lines = lines[:start] + lines[end:]
    residual = [line for line in lines if "`" in line]
    body = "\n".join(lines)
    temporaries = [(match.group(2), match.group(3)) for match in BLOCK_LOCAL.finditer(body)]
    initialized = [(match.group(2), match.group(3), match.group(4))
                   for match in INIT_DECL.finditer(body)]
    declarations = "".join(f"reg {width} {name};\n" if width else f"reg {name};\n"
                           for width, name in temporaries + [(width, name)
                                                             for width, name, _ in initialized])
    stripped = INIT_DECL.sub(lambda match: f"{match.group(3)} = {match.group(4)};", body)
    stripped = BLOCK_LOCAL.sub("", stripped)
    normalized = stripped if not declarations else insert_declarations(stripped, declarations, marker)
    view_lines = [line for line in normalized.split("\n") if line.strip()]
    view_set = set(view_lines)
    disappeared = [line for line in lines if line and line not in view_set]
    appeared = [line for line in view_lines if line not in set(lines)]
    expected_declarations = [line.rstrip() for line in declarations.split("\n") if line.strip()]
    expected_rewrites = [f"{name} = {expression};" for _, name, expression in initialized]
    permitted_removals = ([line for line in disappeared if BLOCK_LOCAL.match(line)]
                          + [line for line in disappeared if INIT_DECL.match(line)])
    conserved = (len(permitted_removals) == len(disappeared)
                 and len(disappeared) == len(temporaries) + len(initialized)
                 and all(line in expected_declarations + expected_rewrites for line in appeared)
                 and sorted(appeared) == sorted(expected_declarations + expected_rewrites))
    audit = {
        "top": top,
        "renamed_top": rename,
        "regions_removed_lines": removed,
        "block_local_temporaries_hoisted": [name for _, name in temporaries],
        "initialized_declarations_hoisted": [name for _, name, _ in initialized],
        "code_lines_locked": len([line for line in lines if line]),
        "code_lines_view": len(view_lines),
        "residual_preprocessor_directives": len(residual),
        "line_conservation_ok": conserved,
        "register_update_equations_locked": len(REGISTER_UPDATE.findall(body)),
        "register_update_equations_preserved": (REGISTER_UPDATE.findall(body)
                                                == REGISTER_UPDATE.findall(normalized)),
    }
    audit["view_trusted"] = bool(
        conserved and audit["register_update_equations_preserved"]
        and "automatic" not in normalized
        and all(line.lstrip().startswith("`") for line in residual))
    if rename:
        if marker not in normalized:
            raise AssertionError(f"locked top declaration missing for {top}")
        normalized = normalized.replace(marker, f"module REF_{top}(", 1)
    return normalized + "\n", audit


def locked_closure() -> tuple[str, list[str], list[dict[str, Any]]]:
    """Assemble WrBypass plus its locked children, each through the view."""

    visited: set[str] = set()
    parts: list[str] = []
    audits: list[dict[str, Any]] = []

    def walk(current: str) -> None:
        if current in visited:
            return
        visited.add(current)
        path = REF_DIR / f"{current}.sv"
        if not path.is_file():
            raise AssertionError(f"locked reference missing for {current}")
        text = path.read_text(encoding="utf-8")
        code = "\n".join(strip_line(raw) for raw in text.split("\n"))
        for child in sorted({item for item in INSTANCE.findall(code)
                             if item != current and (REF_DIR / f"{item}.sv").is_file()}):
            walk(child)
        view, audit = synthesizable_view(text, current, rename=(current == MODULE_NAME))
        audits.append(audit)
        parts.append(view)

    walk(MODULE_NAME)
    return "".join(parts), sorted(visited - {MODULE_NAME}), audits


def abi_audit(target_rtl: str, ports: dict[str, tuple[str, int]]) -> dict[str, Any]:
    """Require the target to declare exactly the locked port surface."""

    target_ports = declared_ports(target_rtl, f"DUT_{MODULE_NAME}")
    checks = {
        "target_module": f"module DUT_{MODULE_NAME}(" in target_rtl,
        "surfaces_identical": target_ports == ports,
        "no_extra_target_ports": set(target_ports) == set(ports),
        "outputs_present": any(direction == "output" for direction, _ in ports.values()),
        "clock_and_reset_present": {"clock", "reset"} <= set(ports),
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks,
            "target_declared_ports": {k: list(v) for k, v in sorted(target_ports.items())},
            "reference_declared_ports": {k: list(v) for k, v in sorted(ports.items())}}


def deterministic_export(module: Any) -> tuple[str, dict[str, Any]]:
    """Generate the target RTL twice and require exact byte identity."""

    first = module.build_verilog(None, {})
    second = module.build_verilog(None, {})
    renamed = first.replace(f"module {MODULE_NAME}(", f"module DUT_{MODULE_NAME}(", 1)
    repeat = second.replace(f"module {MODULE_NAME}(", f"module DUT_{MODULE_NAME}(", 1)
    equal = renamed == repeat
    return renamed, {"status": "PASS" if equal else "FAIL", "bytes": len(renamed.encode("utf-8")),
                     "sha256": hashlib.sha256(renamed.encode("utf-8")).hexdigest(),
                     "repeat_sha256": hashlib.sha256(repeat.encode("utf-8")).hexdigest(),
                     "byte_equal": equal}


def measured_state(locked_text: str) -> tuple[int, dict[str, int]]:
    """Sum the locked register declarations as the state boundary."""

    registers: dict[str, int] = {}
    for declared in re.finditer(r"^\s*reg\s+(?:\[(\d+):0\]\s*)?([^;]+);", locked_text, re.M):
        width = int(declared.group(1)) + 1 if declared.group(1) else 1
        for name in [item.strip().split()[0] for item in declared.group(2).split(",") if item.strip()]:
            registers[name] = width
    return sum(registers.values()), registers


def equiv_run(target: Path, reference: Path) -> dict[str, Any]:
    """Discharge the flattened pair by induction."""

    script = (f"read_verilog -sv {shlex.quote(wsl_path(target))} "
              f"{shlex.quote(wsl_path(reference))}; "
              "proc; async2sync; memory; opt; "
              f"flatten REF_{MODULE_NAME}; flatten DUT_{MODULE_NAME}; "
              f"equiv_make REF_{MODULE_NAME} DUT_{MODULE_NAME} WrBypass_EQUIV; "
              "prep -top WrBypass_EQUIV; equiv_induct -undef; equiv_status -assert")
    result = run_wsl(["yosys", "-Q", "-p", script])
    output = result.get("output_tail", "")
    markers = {marker: marker in output for marker in EQUIV_MARKERS}
    result["markers_present"] = markers
    result["formal_success_marker"] = all(markers.values())
    totals = re.findall(r"Found (\d+) \$equiv cells in", output)
    summary = re.findall(r"Of those cells (\d+) are proven and (\d+) are unproven", output)
    failed = re.findall(r"Found (\d+) unproven \$equiv cells in 'equiv_status -assert'", output)
    if totals:
        result["equiv_cells"] = int(totals[-1])
    if summary:
        result["proven_cells"], result["unproven_cells"] = int(summary[-1][0]), int(summary[-1][1])
    if failed:
        result["unproven_cells"] = int(failed[-1])
    if result["returncode"] != 0 or not result["formal_success_marker"]:
        result["status"] = "FAIL"
    return result


def negative_control(paths: dict[str, Path], outputs: dict[str, int]) -> dict[str, Any]:
    """Pin one output lane low on each side and require both to break."""

    port = sorted(outputs)[-1]
    verdicts: dict[str, Any] = {}
    for side in ("target", "reference"):
        source = paths[side].read_text(encoding="utf-8")
        mutated, count = re.subn(rf"assign\s+{re.escape(port)}\s*=\s*[^;]+;",
                                 lambda _match: f"assign {port} = 1'b0;", source, count=1)
        if count == 0:
            verdicts[side] = {"status": "FAIL", "mutation_applied": False,
                              "note": "the control driver was not found"}
            continue
        mutant = WORK / f"MUTANT_{side}.sv"
        mutant.write_text(mutated, encoding="utf-8", newline="\n")
        verdict = equiv_run(mutant if side == "target" else paths["target"],
                            mutant if side == "reference" else paths["reference"])
        verdicts[side] = {"status": "PASS" if not verdict["formal_success_marker"] else "FAIL",
                          "mutation_applied": True, "control_port": port,
                          "unproven_cells": verdict.get("unproven_cells"),
                          "markers_present": verdict.get("markers_present")}
    detected = bool(verdicts) and all(item["status"] == "PASS" for item in verdicts.values())
    return {"status": "PASS" if detected else "FAIL", "sides": verdicts,
            "note": "a reference-side mutation that still proves means the reference never "
                    "reaches the comparison, which is the degenerate-miter failure mode"}


def validate() -> dict[str, Any]:
    """Run every strict gate and persist machine-readable evidence."""

    failures: list[str] = []
    locked_text = (REF_DIR / f"{MODULE_NAME}.sv").read_text(encoding="utf-8")
    ports = declared_ports(locked_text, MODULE_NAME)
    inputs = {name: width for name, (direction, width) in ports.items() if direction == "input"}
    outputs = {name: width for name, (direction, width) in ports.items() if direction == "output"}
    state_bits, state_registers = measured_state(locked_text)
    sources = {
        name: {"path": (SCALA if name == "scala" else
                        (TARGET if name == "python_build" else REF_DIR / f"{MODULE_NAME}.sv")
                        ).relative_to(ROOT).as_posix(),
               "sha256": sha256_file(SCALA if name == "scala" else
                                     (TARGET if name == "python_build"
                                      else REF_DIR / f"{MODULE_NAME}.sv"))}
        for name in ("scala", "reference_sv", "python_build")
    }
    module = load_target()
    py_compile.compile(str(TARGET), doraise=True)
    py_compile.compile(str(Path(__file__)), doraise=True)
    target_rtl, export = deterministic_export(module)
    abi = abi_audit(target_rtl, ports)
    closure, children, view_audits = locked_closure()
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)
    target_path = WORK / f"{MODULE_NAME}-target.sv"
    reference_path = WORK / f"{MODULE_NAME}-reference.sv"
    target_path.write_text(target_rtl, encoding="utf-8", newline="\n")
    reference_path.write_text(closure, encoding="utf-8", newline="\n")
    paths = {"target": target_path, "reference": reference_path}
    lints = {
        "target_verilator": run_wsl(["verilator", "--lint-only", "-Wno-fatal",
                                     "--top-module", f"DUT_{MODULE_NAME}", wsl_path(target_path)]),
        "reference_verilator": run_wsl(["verilator", "--lint-only", "-Wno-fatal",
                                        "--top-module", f"REF_{MODULE_NAME}", wsl_path(reference_path)]),
        "locked_reference_verilator": run_wsl([
            "verilator", "--lint-only", "-Wno-fatal", "--top-module", MODULE_NAME,
            wsl_path(REF_DIR / f"{MODULE_NAME}.sv"),
            *(wsl_path(REF_DIR / f"{child}.sv") for child in children)]),
        "target_yosys": run_wsl(["yosys", "-Q", "-p",
                                 f"read_verilog -sv {shlex.quote(wsl_path(target_path))}; "
                                 f"proc; async2sync; opt; hierarchy -top DUT_{MODULE_NAME}; check"]),
        "reference_yosys": run_wsl(["yosys", "-Q", "-p",
                                    f"read_verilog -sv {shlex.quote(wsl_path(reference_path))}; "
                                    f"proc; async2sync; opt; hierarchy -top REF_{MODULE_NAME}; check"]),
    }
    control = negative_control(paths, outputs)
    proof = equiv_run(target_path, reference_path)
    pyright = {"target": pyright_check(TARGET), "validator": pyright_check(Path(__file__))}
    if not inputs or not outputs:
        failures.append("derived port surface is empty")
    if not abi["status"] == "PASS":
        failures.append("ABI audit")
    if export["status"] != "PASS":
        failures.append("deterministic export mismatch")
    if not all(audit["view_trusted"] for audit in view_audits):
        failures.append("synthesizable view failed conservation for a locked module")
    for name, result in pyright.items():
        if result["status"] != "PASS":
            failures.append(f"pyright {name}")
    for name, result in lints.items():
        if result["status"] != "PASS":
            failures.append(name)
    if control["status"] != "PASS":
        failures.append("negative control did not detect a mutated design")
    if proof["status"] != "PASS":
        failures.append("yosys_equiv")
    if not any((proof.get("equiv_cells"), proof.get("proven_cells"), proof.get("unproven_cells"))):
        failures.append("no $equiv cells were matched, so the run is vacuous")
    elif proof.get("unproven_cells"):
        failures.append(f"{proof['unproven_cells']} $equiv cells remain unproven")
    status = "COMPLETE_EQUIVALENCE" if not failures else "STRICT_PENDING"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_STRICT_COMPLETE_EQUIVALENCE",
        "build_id": "Build-Cpu.Frontend.Bpu.WrBypass",
        "validator": Path(__file__).relative_to(ROOT).as_posix(),
        "status": status,
        "strict_complete_eligible": status == "COMPLETE_EQUIVALENCE",
        "strict_complete_count_delta": 1 if status == "COMPLETE_EQUIVALENCE" else 0,
        "acceptance_eligible": status == "COMPLETE_EQUIVALENCE",
        "source_commit": SOURCE_COMMIT,
        "scope": {
            "kind": "sequential_registered_leaf",
            "configuration": "locked V2 write bypass CAM check over a locked IndexableCAMTemplate",
            "state_bits": state_bits,
            "state_registers": state_registers,
            "state_boundary": "valid and data registers across two posedge blocks, async reset "
                              "normalized by async2sync, locked CAM child included flattened",
            "inputs": inputs,
            "outputs_compared": outputs,
            "input_bits": sum(inputs.values()),
            "output_bits": sum(outputs.values()),
            "transition_relation": "all input sequences, posedge clock, async reset normalized by async2sync",
            "proof_cell_coverage": "equiv_status -assert requires every matched state and output cell",
            "why_complete": "Yosys equiv_induct -undef discharges the flattened transition relation; "
                            "a two-sided negative control shows the harness detects differences",
            "bounded_tests_counted": False,
        },
        "reference_lock": {
            "path": f"validation/reference-sv/{MODULE_NAME}.sv",
            "sha256": sha256_file(REF_DIR / f"{MODULE_NAME}.sv"),
            "xstop_sha256": XSTOP_SHA256,
            "reference_module": MODULE_NAME,
            "child_instances": children,
            "child_sha256": {child: sha256_file(REF_DIR / f"{child}.sv") for child in children},
            "locked_references_written": False,
        },
        "sources": sources,
        "checks": {
            "py_compile": {"status": "PASS"},
            "pyright": pyright,
            "abi": abi,
            "deterministic_export": export,
            "reference_normalization": view_audits,
            "formal": {**lints, "negative_control": control, "yosys_equiv": proof},
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
    proof = payload["checks"]["formal"]["yosys_equiv"]
    print(json.dumps({
        "status": payload["status"],
        "strict_complete_eligible": payload["strict_complete_eligible"],
        "input_bits": payload["scope"]["input_bits"],
        "output_bits": payload["scope"]["output_bits"],
        "state_bits": payload["scope"]["state_bits"],
        "children": payload["reference_lock"]["child_instances"],
        "equiv_cells": proof.get("equiv_cells"),
        "proven_cells": proof.get("proven_cells"),
        "unproven_cells": proof.get("unproven_cells"),
        "negative_control": payload["checks"]["formal"]["negative_control"]["status"],
        "pyright_error_counts": {k: v["error_count"] for k, v in payload["checks"]["pyright"].items()},
        "failures": payload["failures"],
    }, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
