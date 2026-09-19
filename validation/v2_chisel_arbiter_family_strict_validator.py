"""Strict complete-equivalence proof for the whole Chisel dependency catalog Build.

``Build-Cpu.Dependency.Chisel.Arbiter-Hardware.py`` is a catalog Build: its
``*_SPECS`` tables name 57 locked utility modules, each with an exact-name file
under ``validation/reference-sv``.  The Build file only counts when every one of
them closes, so this validator enumerates the tables from the Build itself and
routes each entry to the right rail: combinational leaves get an unrestricted
SAT miter, single-clock registered leaves get inductive equivalence.

Locked references are read verbatim and are never written.  Where the installed
Yosys cannot parse a locked file because Chisel emitted block-local
``automatic logic`` declarations, the section 5C synthesizable view is used:
inert non-synthesis regions are dropped and those declarations are hoisted to
module scope, with a line-conservation gate proving nothing else moved.
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
    "Build-Cpu.Dependency.Chisel.Arbiter-Hardware.py"
)
REF_DIR = ROOT / "validation/reference-sv"
EVIDENCE = ROOT / "validation/v2-chisel-arbiter-family-strict-evidence.json"
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_chisel_arbiter_family_strict"

SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
SAT_MARKER = "SAT proof finished - no model found: SUCCESS!"
EQUIV_MARKERS = ("0 are unproven.", "Equivalence successfully proven!")
ANSI_PORT = re.compile(r"^(input|output)\s+(?:\[(\d+):0\]\s*)?(.+)$")
BLOCK_LOCAL = re.compile(
    r"^([ \t]*)automatic\s+logic\s+(\[[^\]]*\])?\s*([A-Za-z_][A-Za-z0-9_]*)\s*;[ \t]*$", re.M)
INIT_DECL = re.compile(
    r"^([ \t]*)automatic\s+logic\s+(\[[^\]]*\])?\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+);\s*$", re.M)
REMOVED_REGIONS = ("`ifndef SYNTHESIS", "`ifdef ENABLE_INITIAL_REG_")
NESTED_OPEN = re.compile(r"^\s*`(ifdef|ifndef|else|elsif)\b")
NESTED_CLOSE = re.compile(r"^\s*`endif\b")
INSTANCE = re.compile(r"^\s*([A-Za-z_]\w*)\s+[A-Za-z_]\w*\s*\(", re.M)


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
    """Load the catalog Build by exact path."""

    spec = importlib.util.spec_from_file_location("strict_chisel_arbiter_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load target: {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def catalog_entries(module: Any) -> list[str]:
    """Enumerate every locked module name the catalog Build claims to cover."""

    names: list[str] = []
    for attribute in sorted(dir(module)):
        if not attribute.endswith("_SPECS"):
            continue
        table = getattr(module, attribute)
        if isinstance(table, dict):
            names.extend(str(key) for key in table)
    unique: list[str] = []
    for name in names:
        if name not in unique:
            unique.append(name)
    return sorted(unique)


def declared_scala(module: Any) -> list[str]:
    """Return every Scala source the catalog Build declares."""

    paths: list[str] = []
    for attribute in ("ARBITER_SOURCE_PATHS", "ASYNCHRONOUS_SOURCE_PATHS", "UTILITY_SOURCE_PATHS"):
        paths.extend(str(item) for item in getattr(module, attribute, ()))
    return list(dict.fromkeys(paths))


def scala_source(module: Any) -> dict[str, Any]:
    """Return the first declared Scala source this lock actually vendors."""

    for declared in declared_scala(module):
        path = ROOT / declared
        if path.is_file():
            return {"path": path.relative_to(ROOT).as_posix(), "sha256": sha256_file(path),
                    "bytes": path.stat().st_size}
    raise AssertionError("the catalog Build declares no vendored Scala source")


def scala_sources(module: Any) -> dict[str, Any]:
    """Record every declared source, including Chisel library files this lock omits."""

    record: dict[str, Any] = {}
    for declared in declared_scala(module):
        path = ROOT / declared
        record[path.relative_to(ROOT).as_posix()] = (
            {"vendored": True, "sha256": sha256_file(path)} if path.is_file()
            else {"vendored": False,
                  "note": "Chisel standard-library source, not part of this locked tree"})
    return record


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
        "output_tail": output[-2500:],
        "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
    }


def pyright_check(source: Path) -> dict[str, Any]:
    """Run Pyright on an exact visible copy of one source file."""

    temporary = Path(tempfile.mkdtemp(prefix="uhsc_arbiter_family_pyright_"))
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


def synthesizable_view(text: str, top: str, rename: bool) -> tuple[str, dict[str, Any]]:
    """Apply the section 5C view to one locked module body."""

    marker = f"module {top}("
    lines = [strip_line(line) for line in text.split("\n") if strip_line(line)]
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
    hoisted = temporaries + [(width, name) for width, name, _ in initialized]
    declarations = "".join(f"reg {width} {name};\n" if width else f"reg {name};\n"
                           for width, name in hoisted)
    rewritten = INIT_DECL.sub(lambda match: f"{match.group(3)} = {match.group(4)};", body)
    stripped = BLOCK_LOCAL.sub("", rewritten)
    normalized = ("\n".join(stripped.split("\n")) if not declarations
                  else insert_declarations(stripped, declarations, marker))
    view_lines = [line for line in normalized.split("\n") if line.strip()]
    view_set = set(view_lines)
    disappeared = [line for line in lines if line.strip() and line not in view_set]
    expected_declarations = [line.rstrip() for line in declarations.split("\n") if line.strip()]
    expected_rewrites = [f"{name} = {expression};" for _, name, expression in initialized]
    permitted = expected_declarations + expected_rewrites
    appeared = [line for line in view_lines if line not in set(lines)]
    conserved = (all(BLOCK_LOCAL.match(line) is not None or INIT_DECL.match(line) is not None
                     for line in disappeared)
                 and len(disappeared) == len(temporaries) + len(initialized)
                 and sorted(appeared) == sorted(permitted))
    registers_before = re.findall(r"^\s*[A-Za-z_]\w*\s*<=\s*.+;$", body, re.M)
    registers_after = re.findall(r"^\s*[A-Za-z_]\w*\s*<=\s*.+;$", normalized, re.M)
    audit = {
        "top": top,
        "renamed_top": bool(rename),
        "regions_removed_lines": removed,
        "block_local_temporaries_hoisted": [name for _, name in temporaries],
        "initialized_declarations_hoisted": [name for _, name, _ in initialized],
        "code_lines_locked": len([line for line in lines if line.strip()]),
        "code_lines_view": len(view_lines),
        "residual_preprocessor_directives": len(residual),
        "line_conservation_ok": conserved,
        "register_update_equations_preserved": registers_before == registers_after,
    }
    audit["view_trusted"] = bool(conserved and audit["register_update_equations_preserved"]
                                 and not residual and "automatic" not in normalized)
    if rename:
        if marker not in normalized:
            raise AssertionError(f"locked top declaration missing in {top}")
        normalized = normalized.replace(marker, f"module REF_{top}(", 1)
    return normalized + "\n", audit


def insert_declarations(stripped: str, declarations: str, marker: str) -> str:
    """Place hoisted module-scope declarations just after the module header."""

    end = stripped.index(marker) + len(marker)
    header_end = stripped.index(");", end) + 2
    return stripped[:header_end] + "\n" + declarations + stripped[header_end:]


def locked_closure(name: str, rename_top: bool) -> tuple[str, list[str], list[dict[str, Any]]]:
    """Build one locked module plus its locked children, each through the view."""

    visited: set[str] = set()
    order: list[str] = []
    audits: list[dict[str, Any]] = []

    def walk(current: str) -> None:
        if current in visited:
            return
        visited.add(current)
        path = REF_DIR / f"{current}.sv"
        if not path.is_file():
            raise AssertionError(f"locked reference missing for {current}")
        text = path.read_text(encoding="utf-8")
        children = sorted({child for child in INSTANCE.findall(text)
                           if (REF_DIR / f"{child}.sv").is_file()})
        for child in children:
            walk(child)
        view, audit = synthesizable_view(text, current,
                                         rename=(rename_top and current == name))
        audits.append(audit)
        order.append(view)

    walk(name)
    return "".join(order), sorted(visited - {name}), audits


def miter_text(name: str, inputs: dict[str, int], outputs: dict[str, int]) -> str:
    """Emit a miter whose mismatch ORs every declared output lane."""

    lines = [f"module {name}_MITER("]
    for port, width in inputs.items():
        lines.append(f"  input [{width - 1}:0] {port}," if width > 1 else f"  input {port},")
    lines.append("  output mismatch")
    lines.append(");")
    for port, width in outputs.items():
        lines.append(f"  wire [{width - 1}:0] ref_{port};")
        lines.append(f"  wire [{width - 1}:0] dut_{port};")
    for prefix, instance, top in (("ref_", "reference_i", f"REF_{name}"),
                                  ("dut_", "target_i", f"DUT_{name}")):
        connections = [f".{port}({port})" for port in inputs]
        connections += [f".{port}({prefix}{port})" for port in outputs]
        lines.append(f"  {top} {instance}(")
        lines.append("    " + ", ".join(connections))
        lines.append("  );")
    lines.append("  assign mismatch = " + " | ".join(f"(ref_{p} != dut_{p})" for p in outputs) + ";")
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def selfcheck(text: str, inputs: dict[str, int], outputs: dict[str, int]) -> bool:
    """Refuse a miter that connects nets it never declared."""

    declared = set(re.findall(r"^\s*(?:input|output|wire)\s+(?:\[\d+:0\]\s*)?([A-Za-z_]\w*)",
                              text, re.M))
    connected = {net for net in re.findall(r"\.\w+\(([^()]+)\)", text)}
    return bool(connected) and connected <= declared and bool(outputs)


def prepare(module: Any, name: str) -> dict[str, Any]:
    """Materialize one catalog entry: target, locked closure, miter, audits."""

    target_rtl = module.build_verilog(name, None)
    if f"module {name}(" not in target_rtl:
        raise AssertionError(f"{name}: Build emitted a differently named module")
    target_rtl = target_rtl.replace(f"module {name}(", f"module DUT_{name}(", 1)
    locked_text = (REF_DIR / f"{name}.sv").read_text(encoding="utf-8")
    ports = declared_ports(locked_text, name)
    closure_text, children, view_audits = locked_closure(name, True)
    inputs = {p: w for p, (d, w) in ports.items() if d == "input"}
    outputs = {p: w for p, (d, w) in ports.items() if d == "output"}
    miter = miter_text(name, inputs, outputs)
    target_path = WORK / f"DUT_{name}.sv"
    reference_path = WORK / f"REF_{name}.sv"
    miter_path = WORK / f"{name}_MITER.sv"
    target_path.write_text(target_rtl, encoding="utf-8", newline="\n")
    reference_path.write_text(closure_text, encoding="utf-8", newline="\n")
    miter_path.write_text(miter, encoding="utf-8", newline="\n")
    target_ports = declared_ports(target_rtl, f"DUT_{name}")
    sequential = any(port in ports for port in ("clock", "clk", "io_clk"))
    second = module.build_verilog(name, None).replace(f"module {name}(", f"module DUT_{name}(", 1)
    return {
        "name": name, "inputs": inputs, "outputs": outputs, "children": children,
        "sequential": sequential, "abi_exact": target_ports == ports,
        "deterministic": second == target_rtl,
        "miter_selfcheck": selfcheck(miter, inputs, outputs),
        "view_trusted": all(audit["view_trusted"] for audit in view_audits),
        "view_audits": view_audits,
        "target": target_path, "reference": reference_path, "miter": miter_path,
        "locked_sha256": sha256_file(REF_DIR / f"{name}.sv"),
    }


def prove(item: dict[str, Any]) -> dict[str, Any]:
    """Prove one catalog entry on the rail its timing requires."""

    name = item["name"]
    pair = " ".join(shlex.quote(wsl_path(path))
                    for path in (item["target"], item["reference"]))
    files = " ".join(shlex.quote(wsl_path(path))
                     for path in (item["target"], item["reference"], item["miter"]))
    lint = run_wsl(["verilator", "--lint-only", "-Wno-fatal", "--top-module",
                    f"{name}_MITER", wsl_path(item["target"]),
                    wsl_path(item["reference"]), wsl_path(item["miter"])])
    if not item["sequential"]:
        script = (f"read_verilog -sv {files}; prep -top {name}_MITER; flatten; opt; "
                  "sat -prove mismatch 0")
        proof = run_wsl(["yosys", "-Q", "-p", script])
        output = proof.get("output_tail", "")
        proof["formal_success_marker"] = SAT_MARKER in output
        proof["unconstrained"] = "Final constraint equation: { } = { }" in output
        counts = re.findall(r"Solving problem with (\d+) variables and (\d+) clauses", output)
        if counts:
            proof["sat_variables"], proof["sat_clauses"] = int(counts[-1][0]), int(counts[-1][1])
        if not proof["formal_success_marker"] or not proof["unconstrained"]:
            proof["status"] = "FAIL"
        return {"method": "sat_miter", "verilator": lint, "sat_miter": proof}

    script = (f"read_verilog -sv {pair}; proc; async2sync; memory; opt; "
              f"flatten REF_{name}; flatten DUT_{name}; "
              f"equiv_make REF_{name} DUT_{name} {name}_EQUIV; "
              f"prep -top {name}_EQUIV; equiv_induct -undef; equiv_status -assert")
    proof = run_wsl(["yosys", "-Q", "-p", script])
    output = proof.get("output_tail", "")
    markers = {marker: marker in output for marker in EQUIV_MARKERS}
    proof["markers_present"] = markers
    proof["formal_success_marker"] = all(markers.values())
    totals = re.findall(r"Found (\d+) \$equiv cells in", output)
    summary = re.findall(r"Of those cells (\d+) are proven and (\d+) are unproven", output)
    failed = re.findall(r"Found (\d+) unproven \$equiv cells in 'equiv_status -assert'", output)
    if totals:
        proof["equiv_cells"] = int(totals[-1])
    if summary:
        proof["proven_cells"], proof["unproven_cells"] = int(summary[-1][0]), int(summary[-1][1])
    if failed:
        proof["unproven_cells"] = int(failed[-1])
    if proof["returncode"] != 0 or not proof["formal_success_marker"]:
        proof["status"] = "FAIL"
    return {"method": "sequential_equivalence", "verilator": lint, "yosys_equiv": proof}


def aggregate(items: list[dict[str, Any]], subset: list[dict[str, Any]], label: str) -> dict[str, Any]:
    """Instantiate many miters once and prove the OR of their mismatches."""

    files: list[Path] = []
    lines = [f"module {label}_AGG_MITER("]
    for item in subset:
        for port, width in item["inputs"].items():
            qualified = f"{item['name']}_{port}"
            lines.append(f"  input [{width - 1}:0] {qualified}," if width > 1
                         else f"  input {qualified},")
    lines.append("  output mismatch")
    lines.append(");")
    terms: list[str] = []
    for index, item in enumerate(subset):
        term = f"m{index}"
        terms.append(term)
        lines.append(f"  wire {term};")
        connections = [f".{port}({item['name']}_{port})" for port in item["inputs"]]
        connections.append(f".mismatch({term})")
        lines.append(f"  {item['name']}_MITER mit{index}(")
        lines.append("    " + ", ".join(connections))
        lines.append("  );")
    lines.append("  assign mismatch = " + " | ".join(terms) + ";")
    lines.append("endmodule")
    glue_text = "\n".join(lines) + "\n"
    glue = WORK / f"{label}_AGG_MITER.sv"
    glue.write_text(glue_text, encoding="utf-8", newline="\n")
    declared = set(re.findall(r"^\s*(?:input|output|wire)\s+(?:\[\d+:0\]\s*)?([A-Za-z_]\w*)",
                              glue_text, re.M))
    connected = {net for net in re.findall(r"\.\w+\(([^()]+)\)", glue_text)}
    if not connected or not connected <= declared:
        raise AssertionError(f"{label}: aggregate glue drives nets it never declares")
    for item in subset:
        files.extend([item["target"], item["reference"], item["miter"]])
    quoted = " ".join(shlex.quote(wsl_path(path)) for path in files + [glue])
    script = (f"read_verilog -sv {quoted}; prep -top {label}_AGG_MITER; flatten; opt; "
              "sat -prove mismatch 0")
    proof = run_wsl(["yosys", "-Q", "-p", script])
    output = proof.get("output_tail", "")
    proof["formal_success_marker"] = SAT_MARKER in output
    proof["unconstrained"] = "Final constraint equation: { } = { }" in output
    proof["mitered_variants"] = len(subset)
    counts = re.findall(r"Solving problem with (\d+) variables and (\d+) clauses", output)
    if counts:
        proof["sat_variables"], proof["sat_clauses"] = int(counts[-1][0]), int(counts[-1][1])
    if not proof["formal_success_marker"] or not proof["unconstrained"]:
        proof["status"] = "FAIL"
    return proof


def negative_control(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Perturb one lane on each side of two representative entries."""

    verdicts: dict[str, Any] = {}
    for kind, item in (("combinational", next((entry for entry in items if not entry["sequential"]), None)),
                       ("sequential", next((entry for entry in items if entry["sequential"]), None))):
        if item is None:
            verdicts[kind] = {"status": "FAIL", "note": "no representative entry of this kind"}
            continue
        for side, path in (("target", item["target"]), ("reference", item["reference"])):
            key = f"{kind}.{side}"
            for port in sorted(item["outputs"]):
                source = path.read_text(encoding="utf-8")
                mutated, count = re.subn(rf"assign\s+{re.escape(port)}\s*=\s*[^;]+;",
                                         lambda _match: f"assign {port} = 1'b0;", source, count=1)
                if count == 0:
                    continue
                mutant = WORK / f"MUTANT_{kind}_{side}_{item['name']}.sv"
                mutant.write_text(mutated, encoding="utf-8", newline="\n")
                target_file = mutant if side == "target" else item["target"]
                reference_file = mutant if side == "reference" else item["reference"]
                if item["sequential"]:
                    script = (f"read_verilog -sv {shlex.quote(wsl_path(target_file))} "
                              f"{shlex.quote(wsl_path(reference_file))}; "
                              "proc; async2sync; memory; opt; "
                              f"equiv_make -hierarchy REF_{item['name']} DUT_{item['name']} "
                              f"{item['name']}_EQUIV; prep -top {item['name']}_EQUIV; "
                              "equiv_induct -undef; equiv_status -assert")
                else:
                    script = (f"read_verilog -sv {shlex.quote(wsl_path(target_file))} "
                              f"{shlex.quote(wsl_path(reference_file))} "
                              f"{shlex.quote(wsl_path(item['miter']))}; "
                              f"prep -top {item['name']}_MITER; flatten; opt; sat -prove mismatch 0")
                verdict = run_wsl(["yosys", "-Q", "-p", script])
                output = verdict.get("output_tail", "")
                still_proven = SAT_MARKER in output or all(
                    marker in output for marker in EQUIV_MARKERS)
                verdicts[key] = {"status": "FAIL" if still_proven else "PASS",
                                 "control_entry": item["name"], "control_port": port,
                                 "mutation_applied": True}
                break
            else:
                verdicts[key] = {"status": "FAIL", "mutation_applied": False,
                                 "note": "no declared output of this entry is driven by a single "
                                         "assign in that file, so it cannot be pinned"}
    detected = all(value["status"] == "PASS" for value in verdicts.values()) and bool(verdicts)
    return {"status": "PASS" if detected else "FAIL", "cases": verdicts,
            "note": "pinning one output lane on either side of a representative entry must break "
                    "the proof; a reference-side mutation that still proves means the reference "
                    "never reaches the comparison"}


def validate() -> dict[str, Any]:
    """Prove the whole catalog and persist machine-readable evidence."""

    failures: list[str] = []
    module = load_target()
    names = catalog_entries(module)
    py_compile.compile(str(TARGET), doraise=True)
    py_compile.compile(str(Path(__file__)), doraise=True)
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)
    items = [prepare(module, name) for name in names]
    results = [prove(item) for item in items]
    comb = [item for item in items if not item["sequential"]]
    seq = [item for item in items if item["sequential"]]
    comb_aggregate = aggregate(items, comb, "ARB_COMB") if comb else {"status": "NOT_RUN"}
    control = negative_control(items)
    pyright = {"target": pyright_check(TARGET), "validator": pyright_check(Path(__file__))}
    for item, result in zip(items, results):
        name = item["name"]
        if not item["abi_exact"]:
            failures.append(f"ABI mismatch: {name}")
        if not item["deterministic"]:
            failures.append(f"non-deterministic export: {name}")
        if not item["miter_selfcheck"]:
            failures.append(f"miter drives implicit nets: {name}")
        if not item["view_trusted"]:
            failures.append(f"synthesizable view failed conservation: {name}")
        for gate_name, gate in result.items():
            if isinstance(gate, dict) and gate.get("status") not in (None, "PASS"):
                failures.append(f"{name}:{gate_name}")
    if comb_aggregate.get("status") != "PASS":
        failures.append("aggregate combinational SAT miter")
    if control["status"] != "PASS":
        failures.append("negative control did not detect a mutated design")
    for gate_name, gate in pyright.items():
        if gate["status"] != "PASS":
            failures.append(f"pyright {gate_name}")
    status = "COMPLETE_EQUIVALENCE" if not failures else "STRICT_PENDING"
    variants: dict[str, Any] = {}
    for index, item in enumerate(items):
        proof: dict[str, Any] = (results[index].get("sat_miter")
                                 or results[index].get("yosys_equiv") or {})
        variants[item["name"]] = {
            "method": results[index]["method"],
            "sequential": item["sequential"],
            "locked_reference": f"validation/reference-sv/{item['name']}.sv",
            "locked_sha256": item["locked_sha256"],
            "children": item["children"],
            "inputs": item["inputs"],
            "outputs_compared": item["outputs"],
            "input_bits": sum(item["inputs"].values()),
            "output_bits": sum(item["outputs"].values()),
            "abi_exact": item["abi_exact"],
            "deterministic": item["deterministic"],
            "miter_selfcheck": item["miter_selfcheck"],
            "view_trusted": item["view_trusted"],
            "verdict": proof.get("status"),
            "success_marker": proof.get("formal_success_marker"),
            "unconstrained_or_cells": (proof.get("unconstrained") if not item["sequential"]
                                        else proof.get("equiv_cells")),
            "sat_variables": proof.get("sat_variables"),
            "sat_clauses": proof.get("sat_clauses"),
            "proven_cells": proof.get("proven_cells"),
            "unproven_cells": proof.get("unproven_cells"),
        }
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_STRICT_COMPLETE_EQUIVALENCE",
        "build_id": "Build-Cpu.Dependency.Chisel.Arbiter",
        "validator": Path(__file__).relative_to(ROOT).as_posix(),
        "status": status,
        "strict_complete_eligible": status == "COMPLETE_EQUIVALENCE",
        "strict_complete_count_delta": 1 if status == "COMPLETE_EQUIVALENCE" else 0,
        "acceptance_eligible": status == "COMPLETE_EQUIVALENCE",
        "source_commit": SOURCE_COMMIT,
        "scope": {
            "kind": "mixed_catalog_build",
            "public_variants": [item["name"] for item in items],
            "variant_count": len(items),
            "combinational_variants": len(comb),
            "sequential_variants": len(seq),
            "inputs": {f"{item['name']}_{port}": width
                       for item in items for port, width in item["inputs"].items()},
            "outputs_compared": {f"{item['name']}_{port}": width
                                 for item in items for port, width in item["outputs"].items()},
            "aggregate_input_bits": sum(sum(item["inputs"].values()) for item in items),
            "aggregate_compared_output_bits": sum(sum(item["outputs"].values()) for item in items),
            "variants": variants,
            "why_complete": "Every module named by the Build's spec tables is proven against its "
                            "exact-name locked reference on the rail its timing requires, the "
                            "combinational set is additionally proven through one aggregate miter, "
                            "and a two-sided negative control shows the harness detects differences.",
            "bounded_tests_counted": False,
        },
        "reference_lock": {
            "directory": "validation/reference-sv",
            "xstop_sha256": XSTOP_SHA256,
            "locked_references_written": False,
            "sha256_by_module": {item["name"]: item["locked_sha256"] for item in items},
        },
        "sources": {
            "python_build": {"path": TARGET.relative_to(ROOT).as_posix(),
                             "sha256": sha256_file(TARGET), "bytes": TARGET.stat().st_size},
            "reference_sv": {"path": f"validation/reference-sv/{names[0]}.sv",
                             "sha256": sha256_file(REF_DIR / f"{names[0]}.sv"),
                             "bytes": (REF_DIR / f"{names[0]}.sv").stat().st_size},
            "scala": scala_source(module),
            "declared_scala_sources": scala_sources(module),
        },
        "checks": {
            "py_compile": {"status": "PASS"},
            "pyright": pyright,
            "catalog_coverage": {
                "spec_tables_enumerated": True,
                "entries": len(items),
                "proven": sum(1 for item in variants.values() if item["verdict"] == "PASS"),
            },
            "formal": ({"yosys_formal_miter": comb_aggregate} if comb else
                       {"yosys_equiv": next((result["yosys_equiv"] for result in results
                                            if result["method"] == "sequential_equivalence"), {})}),
            "aggregate_comb_sat_miter": comb_aggregate,
            "negative_control": control,
            "variants": results,
        },
        "failures": failures,
        "unclosed": [] if not failures else ["strict gates did not all pass"],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    return payload


def main() -> int:
    """Print strict status and return nonzero until every entry closes."""

    payload = validate()
    scope = payload["scope"]
    print(json.dumps({
        "status": payload["status"],
        "strict_complete_eligible": payload["strict_complete_eligible"],
        "strict_complete_count_delta": payload["strict_complete_count_delta"],
        "entries": scope["variant_count"],
        "combinational": scope["combinational_variants"],
        "sequential": scope["sequential_variants"],
        "aggregate_input_bits": scope["aggregate_input_bits"],
        "proven": payload["checks"]["catalog_coverage"]["proven"],
        "negative_control": payload["checks"]["negative_control"]["status"],
        "failures": payload["failures"][:8],
    }, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
