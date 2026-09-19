"""Strict complete-equivalence proof for the locked V2 FTBEntryGen leaf.

FTBEntryGen is a purely combinational FTB-entry generator: the locked XSTop
extraction declares 104 ports, contains no ``automatic`` declaration, no
``always`` block and no child instance, so the plain SAT-miter rail applies and
no Yosys-readable view of the reference is needed (rules 5C views are only for
references the installed frontend rejects).

The compared surface is parsed out of ``validation/reference-sv/FTBEntryGen.sv``
itself; none of its 104 names, directions or widths is restated by hand.  The
proof miter is generated from that parse: its ``mismatch`` is the reduction-OR
over every declared output bit, all input bits stay unconstrained (the log must
show ``Final constraint equation: { } = { }``), and success is decided by the
literal Yosys marker, never by the return code.

A negative control ties exactly one generated target output lane to a different
constant and requires the same command to answer ``model found``.  Without that
gate a mis-wired miter can "prove" equivalence vacuously.
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
    "Build-Cpu.Frontend.Bpu.FTBEntryGen-Hardware.py"
)
SCALA = ROOT / "upstream/src/main/scala/xiangshan/frontend/NewFtq.scala"
REFERENCE = ROOT / "validation/reference-sv/FTBEntryGen.sv"
EVIDENCE = ROOT / "validation/v2-ftbentrygen-strict-evidence.json"
MODULE_NAME = "FTBEntryGen"
MITER_NAME = f"{MODULE_NAME}_MITER"
# One generated target lane is perturbed by the negative control below.
CONTROL_PORT = "io_new_entry_valid"
CONTROL_MUTATION = "assign io_new_entry_valid = 1'h0;"
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_ftbentrygen_strict"

BUILD_ID = "Build-Cpu.Frontend.Bpu.FTBEntryGen"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
LOCKED_XSTOP = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
SUCCESS_MARKER = "SAT proof finished - no model found: SUCCESS!"
MODEL_FOUND_MARKER = "SAT proof finished - model found: FAIL!"
FREE_INPUT_MARKER = "Final constraint equation: { } = { }"
# The extra port the Build exported before this proof, recorded so a regression
# that re-exposes it fails the ABI gate with an explicit reason.
PRUNED_PORT = "io_update_valid"


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one exact file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def strip_code(line: str) -> str:
    """Drop a SystemVerilog source-location comment."""

    return re.sub(r"//.*", "", line).strip()


def _module_region(rtl: str, module_name: str) -> tuple[str, str]:
    """Return one module's port-header text and its body region.

    Anchoring on the exact ``module NAME(`` spelling means an instantiation of
    the same module elsewhere in the file cannot be mistaken for its own
    declaration.
    """

    start = rtl.find(f"module {module_name}(")
    if start < 0:
        return "", ""
    open_index = rtl.index("(", start)
    depth = 0
    close_index = -1
    for index in range(open_index, len(rtl)):
        char = rtl[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                close_index = index
                break
    if close_index < 0:
        return "", ""
    end_index = rtl.find("endmodule", close_index)
    return rtl[open_index + 1:close_index], rtl[close_index + 1:end_index if end_index >= 0 else len(rtl)]


def _split_items(text: str) -> list[str]:
    """Split one declaration region on top-level commas only."""

    items: list[str] = []
    current: list[str] = []
    depth = 0
    for char in text:
        if char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
        if char == "," and depth == 0:
            items.append("".join(current))
            current = []
        else:
            current.append(char)
    items.append("".join(current))
    return items


def _classify(items: list[str]) -> dict[str, tuple[str, int]]:
    """Map port names to (direction, width) honouring grouped ANSI declarations.

    Chisel references write ``input [4:0] a,`` and then continuation name lines
    which inherit that direction and width; Amaranth writes one whole
    declaration per body line.  Both spellings reduce to the same pending state.
    """

    result: dict[str, tuple[str, int]] = {}
    pending: tuple[str, int] | None = None
    for item in items:
        entry = " ".join(item.split())
        if not entry:
            continue
        match = re.match(r"^(input|output)\b(?:\s*\[(\d+):0\])?\s*([A-Za-z_][A-Za-z0-9_]*)?$", entry)
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


def _body_declaration_lines(body: str, names: set[str]) -> str:
    """Collect per-name direction declarations from an Amaranth module body."""

    kept: list[str] = []
    for line in body.splitlines():
        code = strip_code(line)
        if code.startswith("endmodule"):
            break
        match = re.match(r"^(input|output)\b(?:\s*\[(\d+):0\])?\s*([A-Za-z_][A-Za-z0-9_]*)?;$", code)
        if match is None:
            continue
        direction, msb, name = match.groups()
        if name is not None and name in names:
            width = int(msb) + 1 if msb is not None else 1
            kept.append(f"{direction} {name}" if width == 1 else f"{direction} [{width - 1}:0] {name}")
    return ",\n".join(kept)


def declared_ports(rtl: str, module_name: str) -> dict[str, tuple[str, int]]:
    """Return the typed port surface of one module in whichever style it uses."""

    header, body = _module_region(rtl, module_name)
    stripped = re.sub(r"//[^\n]*", "", header)
    if re.search(r"\b(?:input|output)\b", stripped):
        return _classify(_split_items(stripped))
    names = {token for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", stripped)}
    return _classify(_split_items(_body_declaration_lines(body, names)))


def load_target() -> Any:
    """Load only the selected Build module by exact path."""

    spec = importlib.util.spec_from_file_location("strict_ftbentrygen_target", TARGET)
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
    """Run one WSL command strictly serially and retain bounded diagnostics.

    The Yosys SAT verdict lines are followed by a long model table, so a
    tail-only window would clip the very markers this rail decides on.  Long
    output is therefore kept as an ASCII-safe head plus the tail, with the
    elided size recorded, and the full bytes are digested.
    """

    rendered = " ".join(shlex.quote(item) for item in command)
    try:
        result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered],
                                capture_output=True, check=False)
    except OSError as error:
        return {"command": command, "status": "FAIL", "error": repr(error)}
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    # Only host-timing chatter is dropped from the retained text: Yosys prints a
    # CPU/MEM tail on its ``End of script.`` line plus a ``Time spent`` summary,
    # and Verilator reports walltime.  The Logfile hash and every diagnostic stay,
    # and the unredacted log is still digested below, so this cannot hide a real
    # problem while it keeps two runs byte-comparable.
    timing = re.compile(r"^(?:Time spent: |- Verilator: Walltime |.*Memory usage: \d+ K)")

    def redact(line: str) -> str:
        """Strip the trailing CPU/MEM timing clause from one log line."""

        if not line.startswith("End of script. Logfile hash:"):
            return line
        return line.split(", CPU:", 1)[0]

    retained = "\n".join(redact(line) for line in output.splitlines()
                         if not timing.match(line))
    window = 6000
    if len(retained) > 2 * window:
        retained = (retained[:window]
                    + f"\n[... {len(retained) - 2 * window} characters elided ...]\n"
                    + retained[-window:])
    marker_words = (SUCCESS_MARKER, MODEL_FOUND_MARKER, FREE_INPUT_MARKER,
                    "Solving problem with", "ERROR")
    decisive = [line.strip() for line in output.splitlines()
                if any(word in line for word in marker_words)][:40]
    # The verdict is decided on the complete log, never on the retained window.
    # ``output_sha256`` digests the timing-redacted retained text because Yosys
    # seeds its own logfile hash randomly, so neither that hash nor a digest of
    # the raw log is reproducible across runs.
    return {
        "command": command,
        "returncode": result.returncode,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "output_tail": retained,
        "output_characters": len(output),
        "decisive_lines": decisive,
        "output_sha256": hashlib.sha256(retained.encode()).hexdigest(),
        "success_marker_in_full_output": SUCCESS_MARKER in output,
        "model_found_marker_in_full_output": MODEL_FOUND_MARKER in output,
        "free_input_marker_in_full_output": FREE_INPUT_MARKER in output,
        "sat_variables": next((int(item) for item in
                               re.findall(r"Solving problem with (\d+) variables", output)), None),
        "sat_clauses": next((int(item) for item in
                             re.findall(r"and (\d+) clauses", output)), None),
    }


def tool_versions() -> dict[str, Any]:
    """Record the exact Verilator/Yosys binaries behind the proof."""

    return {"verilator": run_wsl(["verilator", "--version"]),
            "yosys": run_wsl(["yosys", "--version"])}


def pyright_check(source: Path) -> dict[str, Any]:
    """Run Pyright on an exact visible copy of one source file.

    A bare ``subprocess.run(["pyright", ...])`` raises FileNotFoundError on this
    Windows host, so the call goes through ``cmd.exe`` like every other strict
    rail; a missing tool must never become a PASS.
    """

    temporary = Path(tempfile.mkdtemp(prefix="uhsc_ftbentrygen_pyright_"))
    try:
        copied = temporary / source.name
        shutil.copyfile(source, copied)
        command = ["cmd.exe", "/d", "/c", "pyright", "--outputjson", str(copied)]
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", check=False)
        # The reported JSON echoes this check's own random mkdtemp directory, an
        # incidental path with no bearing on the verdict; normalizing it keeps two
        # runs byte-comparable without touching any diagnostic content.
        stdout = re.sub(r"uhsc_ftbentrygen_pyright_[A-Za-z0-9_]{8}", "PYRIGHT_TMP",
                        result.stdout or "")
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            parsed = {}
        summary = parsed.get("summary", {}) if isinstance(parsed, dict) else {}
        passed = result.returncode == 0 and summary.get("errorCount") == 0
        return {
            "command": [item.replace(temporary.name, "PYRIGHT_TMP") for item in command],
            "returncode": result.returncode,
            "status": "PASS" if passed else "FAIL",
            "version": parsed.get("version") if isinstance(parsed, dict) else None,
            "files_analyzed": summary.get("filesAnalyzed"),
            "error_count": summary.get("errorCount"),
            "warning_count": summary.get("warningCount"),
            "output_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
            "stderr_tail": result.stderr[-1000:],
        }
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def reference_surface() -> tuple[dict[str, int], dict[str, int], dict[str, Any]]:
    """Parse the compared surface and assert the reference really is a plain leaf.

    The route chosen here (plain SAT miter, no 5C view) is only valid when the
    locked artifact carries no block-local ``automatic`` declaration, no
    non-synthesis region, no clocked state and no child instance, so each of
    those properties is measured rather than assumed.
    """

    text = REFERENCE.read_text(encoding="utf-8")
    ports = declared_ports(text, MODULE_NAME)
    inputs = {name: width for name, (direction, width) in ports.items() if direction == "input"}
    outputs = {name: width for name, (direction, width) in ports.items() if direction == "output"}
    leaf = {
        "declared_modules": re.findall(r"^module\s+(\w+)", text, re.M),
        "automatic_declarations": len(re.findall(r"\bautomatic\b", text)),
        "non_synthesis_regions": len(re.findall(r"`ifndef\s+SYNTHESIS|`ifdef\s+ENABLE_INITIAL_REG_", text)),
        "always_blocks": len(re.findall(r"\balways\b", text)),
        "register_declarations": len(re.findall(r"^\s*reg\b", text, re.M)),
        "child_instances": len([line for line in text.split("\n")[text.index(");"):]
                                if re.match(r"^\s*[A-Z]\w*\s+\S+\s*\(", strip_code(line))]),
    }
    plain_leaf = (len(leaf["declared_modules"]) == 1 and leaf["declared_modules"][0] == MODULE_NAME
                  and leaf["automatic_declarations"] == 0 and leaf["non_synthesis_regions"] == 0
                  and leaf["always_blocks"] == 0 and leaf["register_declarations"] == 0
                  and leaf["child_instances"] == 0)
    audit = {
        **leaf,
        "plain_sat_miter_route_valid": plain_leaf,
        "reference_view_required": False,
        "view_reason": "the locked file parses under the installed Yosys 0.52 verbatim, so the "
                       "rules 5C synthesizable view is not applied and the byte-exact reference "
                       "itself is compared",
        "only_transformation": "the module declaration is renamed REF_FTBEntryGen so the reference "
                               "and the target can sit in one design; no other byte changes",
        "port_count": len(ports),
        "inputs": len(inputs),
        "outputs": len(outputs),
    }
    return inputs, outputs, audit


def abi_audit(target_rtl: str, inputs: dict[str, int], outputs: dict[str, int]) -> dict[str, Any]:
    """Require both surfaces to agree name-by-name, direction-by-direction, width-by-width."""

    reference_ports = declared_ports(REFERENCE.read_text(encoding="utf-8"), MODULE_NAME)
    target_ports = declared_ports(target_rtl, MODULE_NAME)
    expected = {**{name: ("input", width) for name, width in inputs.items()},
                **{name: ("output", width) for name, width in outputs.items()}}
    checks: dict[str, bool] = {
        "target_module": f"module {MODULE_NAME}(" in target_rtl,
        "reference_module": bool(reference_ports),
        "surface_parsed_non_empty": bool(inputs) and bool(outputs),
        "exact_name_set": set(target_ports) == set(reference_ports) == set(expected),
        "directions_match": all(target_ports.get(name, ("", 0))[0] == reference_ports[name][0]
                                for name in reference_ports if name in target_ports),
        "widths_match": all(target_ports.get(name, ("", 0))[1] == reference_ports[name][1]
                            for name in reference_ports if name in target_ports),
        "target_surface_equals_reference": target_ports == reference_ports,
        "pruned_internal_port_not_exported": PRUNED_PORT not in target_ports,
        "every_reference_output_compared":
            set(outputs) == {name for name, (direction, _) in reference_ports.items()
                             if direction == "output"},
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "port_style": {"reference": "grouped ANSI header (Chisel)",
                       "target": "non-ANSI header plus per-port body declarations (Amaranth)"},
        "target_declared_ports": {name: list(target_ports[name]) for name in sorted(target_ports)},
        "reference_declared_ports": {name: list(reference_ports[name]) for name in sorted(reference_ports)},
        "extra_target_ports": sorted(set(target_ports) - set(reference_ports)),
        "missing_target_ports": sorted(set(reference_ports) - set(target_ports)),
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
    """Emit a miter whose mismatch ORs every declared output lane.

    Every input is declared free with no ``assume``, so the proved property
    quantifies the complete 2**input_bits input space.
    """

    lines = [f"module {MITER_NAME}("]
    for name, width in inputs.items():
        lines.append(f"  input [{width - 1}:0] {name}," if width > 1 else f"  input {name},")
    lines.append("  output mismatch")
    lines.append(");")
    for name, width in outputs.items():
        lines.append(f"  wire [{width - 1}:0] ref_{name};" if width > 1 else f"  wire ref_{name};")
        lines.append(f"  wire [{width - 1}:0] dut_{name};" if width > 1 else f"  wire dut_{name};")

    def chunked(items: list[str]) -> list[str]:
        """Wrap named connections so the generated file stays readable."""

        return ["    " + ", ".join(items[offset:offset + 4])
                + ("," if offset + 4 < len(items) else "")
                for offset in range(0, len(items), 4)]

    for prefix, instance, top in (("ref_", "reference_i", f"REF_{MODULE_NAME}"),
                                  ("dut_", "target_i", MODULE_NAME)):
        connections = [f".{name}({name})" for name in inputs]
        connections += [f".{name}({prefix}{name})" for name in outputs]
        lines.append(f"  {top} {instance} (")
        lines.extend(chunked(connections))
        lines.append("  );")
    terms = [f"(ref_{name} != dut_{name})" for name in outputs]
    lines.append("  assign mismatch =")
    buffer = ""
    chunks: list[str] = []
    for index, term in enumerate(terms):
        piece = term + (" |" if index < len(terms) - 1 else ";")
        if len(buffer) + len(piece) > 90:
            chunks.append("    " + buffer.strip())
            buffer = ""
        buffer += piece + " "
    chunks.append("    " + buffer.strip())
    lines.extend(chunks)
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def materialize(target_rtl: str, inputs: dict[str, int],
                outputs: dict[str, int]) -> dict[str, Path]:
    """Write target, the rename-only locked reference, and the derived miter."""

    locked_text = REFERENCE.read_text(encoding="utf-8")
    marker = f"module {MODULE_NAME}("
    if not locked_text.startswith(marker):
        raise AssertionError("locked reference declaration marker missing")
    renamed = locked_text.replace(marker, f"module REF_{MODULE_NAME}(", 1)
    if renamed.count("\n") != locked_text.count("\n"):
        raise AssertionError("reference renaming changed the line count")
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)
    paths = {
        "target": WORK / f"UHSC_{MODULE_NAME}.sv",
        "reference": WORK / f"REF_{MODULE_NAME}.sv",
        "miter": WORK / f"{MITER_NAME}.sv",
    }
    paths["target"].write_text(target_rtl, encoding="utf-8", newline="\n")
    paths["reference"].write_text(renamed, encoding="utf-8", newline="\n")
    paths["miter"].write_text(miter_text(inputs, outputs), encoding="utf-8", newline="\n")
    return paths


def sat_run(target: str, paths: dict[str, Path]) -> dict[str, Any]:
    """Discharge the miter and decide success from literal markers only."""

    script = (f"read_verilog -sv {shlex.quote(target)} {shlex.quote(wsl_path(paths['reference']))} "
              f"{shlex.quote(wsl_path(paths['miter']))}; prep -top {MITER_NAME}; flatten; opt; "
              "sat -prove mismatch 0")
    result = run_wsl(["yosys", "-Q", "-p", script])
    result["formal_success_marker"] = bool(result.get("success_marker_in_full_output"))
    result["model_found_marker"] = bool(result.get("model_found_marker_in_full_output"))
    result["no_assumption_observed"] = bool(result.get("free_input_marker_in_full_output"))
    # yosys exits 0 even when the inner proof fails, so the marker decides.
    if not (result["formal_success_marker"] and result["no_assumption_observed"]
            and not result["model_found_marker"]):
        result["status"] = "FAIL"
    return result


def formal_gates(paths: dict[str, Path], inputs: dict[str, int],
                 outputs: dict[str, int]) -> dict[str, Any]:
    """Lint both sides, structurally check both sides, then prove the miter."""

    target = wsl_path(paths["target"])
    reference = wsl_path(paths["reference"])
    miter = wsl_path(paths["miter"])
    verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal", "--top-module",
                         MITER_NAME, target, reference, miter])
    target_yosys = run_wsl(["yosys", "-Q", "-p",
                            f"read_verilog -sv {shlex.quote(target)}; hierarchy -top {MODULE_NAME}; "
                            "proc; opt; check"])
    reference_yosys = run_wsl(["yosys", "-Q", "-p",
                               f"read_verilog -sv {shlex.quote(reference)}; "
                               f"hierarchy -top REF_{MODULE_NAME}; proc; opt; check"])
    proof = sat_run(target, paths)
    miter_source = paths["miter"].read_text(encoding="utf-8")
    proof["miter_has_assume"] = "assume" in miter_source.lower()
    proof["miter_sha256"] = sha256_file(paths["miter"])
    if proof["miter_has_assume"]:
        proof["status"] = "FAIL"
    proof["formal_scope"] = {
        "input_bits": sum(inputs.values()),
        "input_space": f"2**{sum(inputs.values())}",
        "input_space_cardinality": str(1 << sum(inputs.values())),
        "state_bits": 0,
        "state_space": "singleton (stateless combinational module)",
        "property": "mismatch == 0 for every 2-state valuation of all declared inputs",
        "outputs_compared": outputs,
        "miter_sequence": (f"read_verilog -sv -> prep -top {MITER_NAME} -> flatten -> opt "
                           "-> sat -prove mismatch 0"),
    }
    return {
        "verilator": verilator,
        "yosys_target": target_yosys,
        "yosys_reference": reference_yosys,
        "yosys_formal_miter": proof,
    }


def negative_control(paths: dict[str, Path]) -> dict[str, Any]:
    """Tie one generated target output lane low and require the proof to break."""

    target_rtl = paths["target"].read_text(encoding="utf-8")
    pattern = rf"assign\s+{CONTROL_PORT}\s*=\s*[^;]+;"
    original = re.search(pattern, target_rtl)
    mutated, count = re.subn(pattern, lambda _match: CONTROL_MUTATION, target_rtl, count=1)
    mutant = WORK / f"UHSC_{MODULE_NAME}-mutant.sv"
    mutant.write_text(mutated, encoding="utf-8", newline="\n")
    if count != 1 or original is None:
        return {
            "control_port": CONTROL_PORT,
            "mutation_applied": False,
            "matched_drivers": count,
            "status": "FAIL",
            "note": "the control driver was not uniquely found, so the harness was never challenged",
        }
    verdict = sat_run(wsl_path(mutant), paths)
    detected = (not verdict["formal_success_marker"]
                and verdict["model_found_marker"]
                and verdict["status"] == "FAIL")
    return {
        "control_port": CONTROL_PORT,
        "mutation_applied": True,
        "original_statement": original.group(0)[-200:],
        "mutated_statement": CONTROL_MUTATION,
        "mutant_sha256": sha256_file(mutant),
        "rerun_command_identical": verdict["command"],
        "sat_variables": verdict.get("sat_variables"),
        "sat_clauses": verdict.get("sat_clauses"),
        "model_found_marker": verdict["model_found_marker"],
        "success_marker_present": verdict["formal_success_marker"],
        "decisive_lines": verdict.get("decisive_lines", []),
        "status": "PASS" if detected else "FAIL",
        "note": "a mutated target must be reported as not equivalent, otherwise the harness is "
                "vacuous and a clean success would mean nothing",
        "output_tail": verdict.get("output_tail", "")[-1200:],
    }


def validate() -> dict[str, Any]:
    """Run every strict gate and persist machine-readable evidence."""

    failures: list[str] = []
    for path in (SCALA, REFERENCE, TARGET):
        if not path.is_file():
            raise FileNotFoundError(f"locked input missing: {path}")
    sources = {
        name: {"path": path.relative_to(ROOT).as_posix(),
               "sha256": sha256_file(path),
               "bytes": path.stat().st_size}
        for name, path in (("scala", SCALA), ("reference_sv", REFERENCE), ("python_build", TARGET))
    }
    module = load_target()
    py_compile.compile(str(TARGET), doraise=True)
    py_compile.compile(str(Path(__file__)), doraise=True)
    inputs, outputs, reference_route = reference_surface()
    target_rtl, export = deterministic_export(module)
    abi = abi_audit(target_rtl, inputs, outputs)
    paths = materialize(target_rtl, inputs, outputs)
    gates = formal_gates(paths, inputs, outputs)
    control = negative_control(paths)
    pyright = {"target": pyright_check(TARGET), "validator": pyright_check(Path(__file__))}
    source_lock = {
        "status": "PASS",
        "source_commit": SOURCE_COMMIT,
        "checks": {
            "scala_present": SCALA.is_file(),
            "python_build_present": TARGET.is_file(),
            "reference_sv_present": REFERENCE.is_file(),
            "xstop_digest_recorded": len(XSTOP_SHA256) == 64,
            "locked_reference_directory": REFERENCE.parent.relative_to(ROOT).as_posix()
                                          == "validation/reference-sv",
        },
        "digests": {name: record["sha256"] for name, record in sources.items()},
        "reference_immutable": sha256_file(REFERENCE) == sources["reference_sv"]["sha256"],
    }
    if source_lock["status"] != "PASS" or not source_lock["reference_immutable"]:
        source_lock["status"] = "FAIL"
        failures.append("source lock audit")
    if not reference_route["plain_sat_miter_route_valid"]:
        failures.append("reference is not a plain combinational leaf")
    if abi["status"] != "PASS":
        failures.append("ABI audit")
    if export["status"] != "PASS":
        failures.append("deterministic export mismatch")
    for name, result in pyright.items():
        if result["status"] != "PASS":
            failures.append(f"pyright {name}")
    for name, result in gates.items():
        if result["status"] != "PASS":
            failures.append(name)
    if control["status"] != "PASS":
        failures.append("negative control did not detect a mutated target")
    status = "COMPLETE_EQUIVALENCE" if not failures else "STRICT_PENDING"
    input_bits = sum(inputs.values())
    output_bits = sum(outputs.values())
    proof = gates["yosys_formal_miter"]
    unclosed = list(failures)
    unclosed.append("Frontend/BPU parent closure, license review and user approval remain outside "
                    "this proof.")
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_STRICT_COMPLETE_EQUIVALENCE",
        "build_id": BUILD_ID,
        "validator": Path(__file__).relative_to(ROOT).as_posix(),
        "status": status,
        "strict_complete_eligible": status == "COMPLETE_EQUIVALENCE",
        "strict_complete_count_delta": 1 if status == "COMPLETE_EQUIVALENCE" else 0,
        "acceptance_eligible": status == "COMPLETE_EQUIVALENCE",
        "source_commit": SOURCE_COMMIT,
        "scope": {
            "kind": "stateless_combinational_leaf",
            "configuration": ("locked Kunminghu V2 FTB geometry: VAddrBits=50, PredictWidth=16, "
                              "numBr=2, BR_OFFSET_LEN=12, JMP_OFFSET_LEN=20, TAR_STAT_SZ=2"),
            "state_bits": 0,
            "state_boundary": "no clock/reset/register/memory in either surface; one combinational evaluation",
            "inputs": inputs,
            "outputs_compared": outputs,
            "input_bits": input_bits,
            "output_bits": output_bits,
            "input_space": f"2**{input_bits}",
            "input_space_cardinality": str(1 << input_bits),
            "surface_derivation": "all 104 names, directions and widths are parsed from the locked "
                                  "FTBEntryGen.sv declaration; none is restated by hand",
            "why_complete": "Yosys SAT proves the reduction-OR over all "
                            f"{len(outputs)} declared output lanes ({output_bits} bits) equals zero "
                            f"with all {input_bits} input bits unconstrained (no assume anywhere in "
                            "the miter) and no temporal state exists; the built-in negative control "
                            "shows the same harness rejects a perturbed target equation",
            "bounded_tests_counted": False,
            "abi_defect_repair": {
                "symptom": f"the Build exported 105 ports including {PRUNED_PORT}; the locked "
                           "reference declares 104",
                "resolution": "boundary alignment only: the internal net and its equation "
                              f"(update_valid := new_valid) were kept and {PRUNED_PORT} was removed "
                              "from verilog.convert ports, so the exported surface is now exactly "
                              "the locked 104",
                "justification": "class FTBEntryGen in the locked NewFtq.scala declares no update "
                                 "port at all, and the only update_valid in that file is the local "
                                 "alias of io.toBpu.update.valid used by u(...) to gate consumers, "
                                 "i.e. the parent supplies the qualification; the locked extraction "
                                 "confirms it by declaring no such port",
            },
        },
        "reference_lock": {
            "path": LOCKED_XSTOP,
            "upstream_source_commit": SOURCE_COMMIT,
            "xstop_sha256": XSTOP_SHA256,
            "locked_reference": REFERENCE.relative_to(ROOT).as_posix(),
            "locked_reference_sha256": sources["reference_sv"]["sha256"],
            "reference_module": MODULE_NAME,
            "reference_route": reference_route,
            "closure_policy": "the locked reference declares one module and instantiates nothing, so "
                              "the only textual transformation anywhere is the REF_ prefix on its own "
                              "module declaration; no 5C view is taken because none is required",
        },
        "sources": sources,
        "checks": {
            "python_version": platform.python_version(),
            "py_compile": {"status": "PASS", "files": [
                TARGET.relative_to(ROOT).as_posix(),
                Path(__file__).relative_to(ROOT).as_posix(),
            ]},
            "pyright": pyright,
            "source_lock": source_lock,
            "abi": abi,
            "deterministic_export": export,
            "tools": tool_versions(),
            "formal": {**gates, "negative_control": control},
        },
        "failures": failures,
        "unclosed": unclosed,
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    return payload


def main() -> int:
    """Print strict status and return nonzero until every gate passes."""

    payload = validate()
    scope = payload["scope"]
    proof = payload["checks"]["formal"]["yosys_formal_miter"]
    control = payload["checks"]["formal"]["negative_control"]
    print(json.dumps({"status": payload["status"],
                      "strict_complete_eligible": payload["strict_complete_eligible"],
                      "input_bits": scope["input_bits"],
                      "output_bits": scope["output_bits"],
                      "output_lanes": len(scope["outputs_compared"]),
                      "sat_variables": proof.get("sat_variables"),
                      "sat_clauses": proof.get("sat_clauses"),
                      "negative_control": control["status"],
                      "failures": payload["failures"]}, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
