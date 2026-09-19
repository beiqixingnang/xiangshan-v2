"""Reusable strict complete-equivalence rail for catalog-style Build files.

Several Build files are catalogs: they name a set of locked modules in a
``COVERED_MODULES`` tuple or one or more ``*_SPECS`` tables and export whichever
member a configuration selects.  Such a Build file only counts toward the strict
rail when *every* locked module it exposes is proven, which is exactly the shape
this module automates:

* enumerate the Build's own member tables, so no list is restated by hand;
* export each member through the Build and compare it against its exact-name
  locked file under ``validation/reference-sv``;
* route combinational members to an unrestricted SAT miter and single-clock
  registered members to inductive equivalence over the flattened pair;
* apply the section 5C synthesizable view to any locked module this Yosys cannot
  read directly, with a line-conservation gate;
* prove the combinational set again through one aggregate miter;
* and refuse to count anything unless a two-sided negative control breaks.

Callers supply three paths and a build_id; everything else is derived.
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
from collections import Counter


ROOT = Path(__file__).resolve().parents[1]
REF_DIR = ROOT / "validation/reference-sv"
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")

SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
SAT_MARKER = "SAT proof finished - no model found: SUCCESS!"
EQUIV_MARKERS = ("0 are unproven.", "Equivalence successfully proven!")
ANSI_PORT = re.compile(r"^(input|output)\s+(?:\[\s*(\d+):0\]\s*)?(.+)$")
BLOCK_LOCAL = re.compile(
    r"^([ \t]*)automatic\s+logic\s+(\[[^\]]*\])?\s*([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s*;[ \t]*$", re.M)
INIT_DECL = re.compile(
    r"^([ \t]*)automatic\s+logic\s+(\[[^\]]*\])?\s*([A-Za-z_]\w*)\s*=\s*(.+);\s*$", re.M)
# A `function automatic` header is accepted by the installed Yosys, so only a
# block-local declaration counts as surviving.
BLOCK_LOCAL_ANY = re.compile(r"\bautomatic\s+(?:logic|reg|bit)\b")
REMOVED_REGIONS = ("`ifndef SYNTHESIS", "`ifdef ENABLE_INITIAL_REG_", "`ifdef ENABLE_INITIAL_MEM_")
NESTED_OPEN = re.compile(r"^\s*`(ifdef|ifndef)\b")
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
        elif direction is not None:
            widened = re.match(r"^(?:\[\s*(\d+):0\]\s*)?(.+)$", line)
            if widened is not None and widened.group(1) is not None:
                width = int(widened.group(1)) + 1
                names = [item.strip() for item in widened.group(2).split(",") if item.strip()]
            else:
                names = [item.strip() for item in line.split(",") if item.strip()]
        else:
            continue
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


def load_module(name: str, path: Path) -> Any:
    """Load one Build module by exact path."""

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def enumerate_members(module: Any, build_path: Path) -> list[str]:
    """Collect every locked module name the Build exposes, from its own tables."""

    text = build_path.read_text(encoding="utf-8")
    runtime_names: list[str] = []
    for attribute in ("LOCKED_VARIANTS", "COVERED_MODULES"):
        value = getattr(module, attribute, None)
        if isinstance(value, (list, tuple)) and value:
            if not all(isinstance(item, str) and item for item in value):
                raise AssertionError(f"{build_path.name} has invalid {attribute} entries")
            runtime_names = list(value)
            break
    if runtime_names:
        if len(runtime_names) != len(set(runtime_names)):
            raise AssertionError(f"{build_path.name} repeats a public member entry")
        cands = set(runtime_names)
    elif (locked := re.search(
            r'\bLOCKED_VARIANTS[^=]*=\s*([\(\[])(.*?)[\)\]]', text, re.S)) is not None:
        locked_names = re.findall(r'"([^"]+)"', locked.group(2))
        if len(locked_names) != len(set(locked_names)):
            raise AssertionError(f"{build_path.name} repeats a LOCKED_VARIANTS entry")
        cands = set(locked_names)
    else:
        cands: set[str] = set()
        for table in re.finditer(
                r'\b(?:COVERED_MODULES|[A-Z_]+_MEMBERS)[^=]*=\s*([\(\[])(.*?)[\)\]]',
                text, re.S):
            cands |= set(re.findall(r'"([^"]+)"', table.group(2)))
        for name in re.findall(r'^([A-Z_]+_SPECS):', text, re.M):
            block = re.search(re.escape(name) + r':.*?\n\}', text, re.S)
            if block is not None:
                cands |= set(re.findall(r'^\s{4}"([^"]+)":', block.group(0), re.M))
        cands |= set(re.findall(
            r'(?:member|module_name|subject|module) == "([A-Za-z_]\w*)"', text))
    if not cands:
        raise AssertionError(f"{build_path.name} exposes no locked module names this rail can resolve")
    missing = sorted(c for c in cands if not (REF_DIR / f"{c}.sv").is_file())
    if missing:
        raise AssertionError(
            f"{build_path.name} exposes members without locked references: {', '.join(missing)}")
    return sorted(cands)


def wsl_path(path: Path) -> str:
    """Convert a Windows path into an absolute WSL path."""

    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                            capture_output=True, check=True)
    return result.stdout.decode("utf-8", "replace").strip()


GATE_TIMEOUT_SECONDS = 900


def run_wsl(command: list[str],
            timeout: int = GATE_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Run one WSL command and retain bounded diagnostics."""

    rendered = " ".join(shlex.quote(item) for item in command)
    try:
        result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered],
                                capture_output=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"command": command, "returncode": None, "status": "FAIL",
                "timed_out": True,
                "output_tail": f"tool call exceeded {timeout}s and was terminated"}
    except OSError as error:
        return {"command": command, "status": "FAIL", "error": repr(error)}
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    equiv_totals = re.findall(r"Found (\d+) \$equiv cells in", output)
    equiv_summary = re.findall(
        r"Of those cells (\d+) are proven and (\d+) are unproven", output)
    equiv_failed = re.findall(
        r"Found (\d+) unproven \$equiv cells in 'equiv_status -assert'", output)
    sat_counts = re.findall(
        r"Solving problem with (\d+) variables and (\d+) clauses", output)
    return {"command": command, "returncode": result.returncode,
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "sat_success_marker": SAT_MARKER in output,
            "sat_counterexample_marker": "model found: FAIL!" in output,
            "unconstrained_marker": "Final constraint equation: { } = { }" in output,
            "equiv_success_markers": {marker: marker in output for marker in EQUIV_MARKERS},
            "equiv_failure_marker": bool(
                re.search(r"ERROR:\s*Found\s+[1-9]\d*\s+unproven\s+\$equiv\s+cells", output)
                or re.search(r"Of those cells\s+\d+\s+are proven and\s+[1-9]\d*\s+are unproven", output)),
            "equiv_cells_full": int(equiv_totals[-1]) if equiv_totals else None,
            "equiv_summary_full": ([int(value) for value in equiv_summary[-1]]
                                   if equiv_summary else None),
            "equiv_failed_full": int(equiv_failed[-1]) if equiv_failed else None,
            "sat_counts_full": ([int(value) for value in sat_counts[-1]]
                                if sat_counts else None),
            "output_tail": output[-2500:],
            "output_sha256": hashlib.sha256(output.encode()).hexdigest()}


def pyright_check(source: Path) -> dict[str, Any]:
    """Run Pyright on an exact visible copy of one source file."""

    temporary = Path(tempfile.mkdtemp(prefix="uhsc_family_rail_pyright_"))
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
        return {"command": command, "returncode": result.returncode,
                "status": "PASS" if result.returncode == 0 and summary.get("errorCount") == 0 else "FAIL",
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


def insert_declarations(stripped: str, declarations: str, top: str) -> str:
    """Place hoisted module-scope declarations just after the module header."""

    header = re.search(r"\bmodule\s+" + re.escape(top) + r"\s*\(", stripped)
    if header is None:
        raise AssertionError(f"module header vanished while hoisting declarations for {top}")
    header_end = stripped.index(");", header.end()) + 2
    return stripped[:header_end] + "\n" + declarations + stripped[header_end:]


def module_declaration(text: str, top: str) -> re.Match[str] | None:
    """Locate a module declaration, tolerating whitespace before its port list."""

    return re.search(r"\bmodule\s+" + re.escape(top) + r"\s*\(", text)


def synthesizable_view(text: str, top: str, rename: bool) -> tuple[str, dict[str, Any]]:
    """Apply the section 5C view to one locked module body."""

    if module_declaration(text, top) is None:
        raise AssertionError(f"locked top declaration missing for {top}")
    lines = [line for line in (strip_line(raw) for raw in text.split("\n")) if line]
    removed: dict[str, int] = {}
    for opening in REMOVED_REGIONS:
        while True:
            start = next((i for i, line in enumerate(lines) if opening in line), None)
            if start is None:
                break
            end = directive_block_end(lines, start)
            removed[opening] = removed.get(opening, 0) + end - start
            lines = lines[:start] + lines[end:]
    residual = [line for line in lines if "`" in line]
    body = "\n".join(lines)
    plain_lines = [m.group(2) for m in BLOCK_LOCAL.finditer(body)]
    temporaries = [(width, name.strip())
                   for m in BLOCK_LOCAL.finditer(body)
                   for width, name in [(m.group(2), item) for item in m.group(3).split(",")]]
    initialized = [(m.group(2), m.group(3), m.group(4)) for m in INIT_DECL.finditer(body)]
    hoisted = temporaries + [(w, n) for w, n, _ in initialized]
    declarations = "".join(f"reg {w} {n};\n" if w else f"reg {n};\n" for w, n in hoisted)
    rewritten = INIT_DECL.sub(lambda m: f"{m.group(3)} = {m.group(4)};", body)
    stripped = BLOCK_LOCAL.sub("", rewritten)
    normalized = stripped if not declarations else insert_declarations(stripped, declarations, top)
    view_lines = [line for line in normalized.split("\n") if line.strip()]
    locked_counts = Counter(line for line in lines if line)
    view_counts = Counter(view_lines)
    disappeared = list((locked_counts - view_counts).elements())
    expected_declarations = [line.rstrip() for line in declarations.split("\n") if line.strip()]
    expected_rewrites = [f"{n} = {e};" for _, n, e in initialized]
    permitted = expected_declarations + expected_rewrites
    appeared = list((view_counts - locked_counts).elements())
    conserved = (all(BLOCK_LOCAL.match(line) is not None or INIT_DECL.match(line) is not None
                     for line in disappeared)
                 and len(disappeared) == len(plain_lines) + len(initialized)
                 and Counter(appeared) == Counter(permitted)
                 and len(view_lines) == len(lines) + len(initialized))
    registers_before = re.findall(r"^\s*[A-Za-z_]\w*\s*<=\s*.+;$", body, re.M)
    registers_after = re.findall(r"^\s*[A-Za-z_]\w*\s*<=\s*.+;$", normalized, re.M)
    audit = {
        "top": top,
        "renamed_top": rename,
        "regions_removed_lines": removed,
        "block_local_temporaries_hoisted": [n for _, n in temporaries],
        "initialized_declarations_hoisted": [n for _, n, _ in initialized],
        "code_lines_locked": len(lines),
        "code_lines_view": len(view_lines),
        "residual_preprocessor_directives": len(residual),
        "line_conservation_ok": conserved,
        "register_update_equations_locked": len(registers_before),
        "register_update_equations_preserved": registers_before == registers_after,
    }
    audit["view_trusted"] = bool(
        conserved and audit["register_update_equations_preserved"]
        and not BLOCK_LOCAL_ANY.search(normalized)
        and not residual)
    if rename:
        renamed, count = re.subn(r"\bmodule\s+" + re.escape(top) + r"\s*\(",
                                 f"module REF_{top}(", normalized, count=1)
        if count != 1:
            raise AssertionError(f"locked top declaration missing for {top}")
        normalized = renamed
    return normalized + "\n", audit


def locked_closure(name: str) -> tuple[str, list[str], list[dict[str, Any]]]:
    """Assemble one locked module plus its locked children through the view."""

    visited: set[str] = set()
    parts: list[str] = []
    audits: list[dict[str, Any]] = []

    def walk(current: str) -> None:
        if current in visited:
            return
        visited.add(current)
        path = REF_DIR / f"{current}.sv"
        text = path.read_text(encoding="utf-8")
        code = "\n".join(strip_line(raw) for raw in text.split("\n"))
        for child in sorted({item for item in INSTANCE.findall(code)
                             if item != current and (REF_DIR / f"{item}.sv").is_file()}):
            walk(child)
        view, audit = synthesizable_view(text, current, rename=(current == name))
        audits.append(audit)
        parts.append(view)

    walk(name)
    return "".join(parts), sorted(visited - {name}), audits


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


def nets_declared(text: str) -> bool:
    """Refuse any miter that connects nets it never declares."""

    declared = set(re.findall(r"^\s*(?:input|output|wire)\s+(?:\[\s*\d+:0\]\s*)?([A-Za-z_]\w*)", text, re.M))
    connected = {net for net in re.findall(r"\.\w+\(([^()]+)\)", text)}
    return bool(connected) and connected <= declared


def declared_scala(build_path: Path) -> Path | None:
    """Return the first Scala source the Build declares that this lock vendors."""

    text = build_path.read_text(encoding="utf-8")
    for declared in re.findall(r'"(upstream/[^"]+\.scala)"', text):
        path = ROOT / declared
        if path.is_file():
            return path
    return None


def declared_scala_sources(build_path: Path) -> dict[str, Any]:
    """Record every Scala path declared by a catalog Build."""

    text = build_path.read_text(encoding="utf-8")
    records: dict[str, Any] = {}
    for declared in dict.fromkeys(re.findall(r'"(upstream/[^"]+\.scala)"', text)):
        path = ROOT / declared
        records[declared] = (
            {"vendored": True, "sha256": sha256_file(path)} if path.is_file()
            else {"vendored": False, "note": "declared Scala source is missing"})
    return records


def export_member(module: Any, name: str) -> str:
    """Emit one member through the Build and rename its top for pairing."""

    for configuration in ({'module': name}, name, {'member': name}):
        try:
            rtl = module.build_verilog(configuration, {})
        except Exception:
            try:
                rtl = module.build_verilog(configuration, None)
            except Exception:
                continue
        if f"module {name}(" in rtl:
            return rtl.replace(f"module {name}(", f"module DUT_{name}(", 1)
    raise AssertionError(f"{name}: the Build never emitted a module under that name")


class FamilyRail:
    """Prove every locked member a catalog Build exposes."""

    def __init__(self, build_path: Path, build_id: str, evidence_path: Path,
                 scala_path: Path | None = None) -> None:
        self.build_path = build_path
        self.build_id = build_id
        self.evidence_path = evidence_path
        self.scala_path = scala_path if scala_path is not None else declared_scala(build_path)
        self.work = TEMP_ROOT / ("uhsc_" + re.sub(r"\W+", "_", build_id).strip("_").lower() + "_family")

    def prepare(self, module: Any, name: str) -> dict[str, Any]:
        target_rtl = export_member(module, name)
        locked_text = (REF_DIR / f"{name}.sv").read_text(encoding="utf-8")
        ports = declared_ports(locked_text, name)
        closure, children, audits = locked_closure(name)
        inputs = {p: w for p, (d, w) in ports.items() if d == "input"}
        outputs = {p: w for p, (d, w) in ports.items() if d == "output"}
        miter = miter_text(name, inputs, outputs)
        target_path = self.work / f"DUT_{name}.sv"
        reference_path = self.work / f"REF_{name}.sv"
        miter_path = self.work / f"{name}_MITER.sv"
        target_path.write_text(target_rtl, encoding="utf-8", newline="\n")
        reference_path.write_text(closure, encoding="utf-8", newline="\n")
        miter_path.write_text(miter, encoding="utf-8", newline="\n")
        return {
            "name": name, "inputs": inputs, "outputs": outputs, "children": children,
            "sequential": any(
                direction == "input"
                and (port in ("clock", "clk", "io_clock", "io_clk")
                     or port.endswith("_clock") or port.endswith("_clk"))
                for port, (direction, _width) in ports.items()),
            "abi_exact": declared_ports(target_rtl, f"DUT_{name}") == ports,
            "deterministic": export_member(module, name) == target_rtl,
            "output_less": not outputs,
            "miter_selfcheck": bool(outputs) and nets_declared(miter),
            "view_trusted": all(audit["view_trusted"] for audit in audits),
            "view_audits": audits,
            "locked_sha256": sha256_file(REF_DIR / f"{name}.sv"),
            "locked_sources": [REF_DIR / f"{child}.sv" for child in children]
                              + [REF_DIR / f"{name}.sv"],
            "target": target_path, "reference": reference_path, "miter": miter_path,
        }

    def prove(self, item: dict[str, Any]) -> dict[str, Any]:
        name = item["name"]
        pair = " ".join(shlex.quote(wsl_path(path))
                        for path in (item["target"], item["reference"]))
        files = pair + " " + shlex.quote(wsl_path(item["miter"]))
        lint = run_wsl(["verilator", "--lint-only", "-Wno-fatal", "--top-module",
                        f"{name}_MITER", wsl_path(item["target"]), wsl_path(item["reference"]),
                        wsl_path(item["miter"])])
        locked_lint = run_wsl(
            ["verilator", "--lint-only", "-Wno-fatal", "-DSYNTHESIS", "--top-module", name]
            + [wsl_path(path) for path in item["locked_sources"]])
        if not item["sequential"]:
            script = (f"read_verilog -sv {files}; prep -top {name}_MITER; flatten; opt; "
                      "sat -prove mismatch 0")
            proof = run_wsl(["yosys", "-Q", "-p", script])
            proof["formal_success_marker"] = proof.get("sat_success_marker") is True
            proof["unconstrained"] = proof.get("unconstrained_marker") is True
            counts = proof.get("sat_counts_full")
            if isinstance(counts, list) and len(counts) == 2:
                proof["sat_variables"], proof["sat_clauses"] = counts
            if not proof["formal_success_marker"] or not proof["unconstrained"]:
                proof["status"] = "FAIL"
            return {"method": "sat_miter", "verilator": lint,
                    "locked_verilator": locked_lint, "sat_miter": proof}
        script = (f"read_verilog -sv {pair}; proc; async2sync; memory; opt; "
                  f"flatten REF_{name}; flatten DUT_{name}; "
                  f"equiv_make REF_{name} DUT_{name} {name}_EQUIV; "
                  f"prep -top {name}_EQUIV; equiv_induct -undef; equiv_status -assert")
        proof = run_wsl(["yosys", "-Q", "-p", script])
        markers = proof.get("equiv_success_markers", {})
        proof["markers_present"] = markers
        proof["formal_success_marker"] = all(markers.values())
        if isinstance(proof.get("equiv_cells_full"), int):
            proof["equiv_cells"] = proof["equiv_cells_full"]
        summary = proof.get("equiv_summary_full")
        if isinstance(summary, list) and len(summary) == 2:
            proof["proven_cells"], proof["unproven_cells"] = summary
        if isinstance(proof.get("equiv_failed_full"), int):
            proof["unproven_cells"] = proof["equiv_failed_full"]
        if proof["returncode"] != 0 or not proof["formal_success_marker"]:
            proof["status"] = "FAIL"
        return {"method": "sequential_equivalence", "verilator": lint,
                "locked_verilator": locked_lint, "yosys_equiv": proof}

    def aggregate(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        subset = [item for item in items if not item["sequential"]]
        if not subset:
            return {"status": "NOT_APPLICABLE", "mitered_variants": 0}
        lines = [f"module {self.build_id.split('.')[-1]}_AGG("]
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
        glue = self.work / f"{self.build_id.split('.')[-1]}_AGG.sv"
        glue.write_text(glue_text, encoding="utf-8", newline="\n")
        if not nets_declared(glue_text):
            raise AssertionError("aggregate glue drives nets it never declares")
        sources = " ".join(shlex.quote(wsl_path(path))
                           for item in subset
                           for path in (item["target"], item["reference"], item["miter"]))
        script = (f"read_verilog -sv {sources} {shlex.quote(wsl_path(glue))}; "
                  f"prep -top {glue.stem}; flatten; opt; sat -prove mismatch 0")
        proof = run_wsl(["yosys", "-Q", "-p", script])
        proof["formal_success_marker"] = proof.get("sat_success_marker") is True
        proof["unconstrained"] = proof.get("unconstrained_marker") is True
        proof["mitered_variants"] = len(subset)
        counts = proof.get("sat_counts_full")
        if isinstance(counts, list) and len(counts) == 2:
            proof["sat_variables"], proof["sat_clauses"] = counts
        if not proof["formal_success_marker"] or not proof["unconstrained"]:
            proof["status"] = "FAIL"
        return proof

    def negative_control(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        """Pin one lane on each side of a representative entry of each rail."""

        verdicts: dict[str, Any] = {}
        for kind in ("sat", "sequential"):
            wanted = kind == "sequential"
            sample = next((item for item in items
                           if item["sequential"] == wanted and item["outputs"]), None)
            if sample is None:
                verdicts[kind] = {"status": "PASS", "note": "no representative with outputs"}
                continue
            for side in ("target", "reference"):
                path = sample["target"] if side == "target" else sample["reference"]
                source = path.read_text(encoding="utf-8")
                top = f"DUT_{sample['name']}" if side == "target" else f"REF_{sample['name']}"
                module_start = re.search(r"\bmodule\s+" + re.escape(top) + r"\s*\(", source)
                if module_start is None:
                    verdicts[f"{kind}.{side}"] = {
                        "status": "FAIL", "mutation_applied": False,
                        "reason": "top module not found"}
                    continue
                module_end = source.find("endmodule", module_start.end())
                if module_end < 0:
                    verdicts[f"{kind}.{side}"] = {
                        "status": "FAIL", "mutation_applied": False,
                        "reason": "top module is unterminated"}
                    continue
                body = source[module_start.start():module_end]
                attempted = False
                for candidate in sorted(sample["outputs"]):
                    mutated_body, count = re.subn(
                        rf"assign\s+{re.escape(candidate)}\s*=\s*[^;]+;",
                        lambda _m: f"assign {candidate} = 1'b0;", body, count=1)
                    if count != 1:
                        mutated_body, count = re.subn(
                            rf"\b{re.escape(candidate)}\s*<=\s*[^;]+;",
                            lambda _m: f"{candidate} <= 1'b0;", body, count=1)
                    if count != 1:
                        continue
                    attempted = True
                    mutated = (source[:module_start.start()] + mutated_body
                               + source[module_end:])
                    mutant = self.work / f"MUTANT_{kind}_{side}.sv"
                    mutant.write_text(mutated, encoding="utf-8", newline="\n")
                    name = sample["name"]
                    if sample["sequential"]:
                        files = ([mutant, sample["reference"]] if side == "target"
                                 else [sample["target"], mutant])
                        script = ("read_verilog -sv "
                                  + " ".join(shlex.quote(wsl_path(entry)) for entry in files)
                                  + f"; proc; async2sync; memory; opt; flatten REF_{name}; flatten DUT_{name}; "
                                    f"equiv_make REF_{name} DUT_{name} {name}_EQUIV; prep -top {name}_EQUIV; "
                                    "equiv_induct -undef; equiv_status -assert")
                    else:
                        files = ([mutant, sample["reference"], sample["miter"]] if side == "target"
                                 else [sample["target"], mutant, sample["miter"]])
                        script = ("read_verilog -sv "
                                  + " ".join(shlex.quote(wsl_path(entry)) for entry in files)
                                  + f"; prep -top {name}_MITER; flatten; opt; sat -prove mismatch 0")
                    verdict = run_wsl(["yosys", "-Q", "-p", script])
                    if sample["sequential"]:
                        explicit_failure = verdict.get("equiv_failure_marker") is True
                        still = all(verdict.get("equiv_success_markers", {}).values())
                    else:
                        explicit_failure = verdict.get("sat_counterexample_marker") is True
                        still = verdict.get("sat_success_marker") is True
                    process_ran = isinstance(verdict.get("returncode"), int) \
                        and verdict.get("timed_out") is not True
                    detected = process_ran and explicit_failure and not still
                    verdicts[f"{kind}.{side}"] = {
                        "status": "PASS" if detected else "FAIL",
                        "control_entry": name, "control_port": candidate,
                        "mutation_applied": True,
                        "explicit_failure_marker": explicit_failure,
                        "success_marker_still_present": still,
                        "returncode": verdict.get("returncode"),
                    }
                    if detected:
                        break
                if not attempted:
                    verdicts[f"{kind}.{side}"] = {"status": "FAIL", "mutation_applied": False}
        detected = bool(verdicts) and all(case["status"] == "PASS" for case in verdicts.values())
        return {"status": "PASS" if detected else "FAIL", "cases": verdicts,
                "note": "a reference-side mutation that still proves means the reference never "
                        "reaches the comparison"}

    def run(self) -> dict[str, Any]:
        """Prove every member and persist the evidence."""

        failures: list[str] = []
        module = load_module("rail_" + re.sub(r"\W+", "_", self.build_id), self.build_path)
        members = enumerate_members(module, self.build_path)
        py_compile.compile(str(self.build_path), doraise=True)
        py_compile.compile(str(Path(__file__)), doraise=True)
        shutil.rmtree(self.work, ignore_errors=True)
        self.work.mkdir(parents=True, exist_ok=True)
        items = [self.prepare(module, name) for name in members]
        results = [self.prove(item) for item in items]
        aggregate = self.aggregate(items)
        control = self.negative_control(items)
        pyright = {"build": pyright_check(self.build_path), "rail": pyright_check(Path(__file__))}
        for item, result in zip(items, results):
            name = item["name"]
            if not item["abi_exact"]:
                failures.append(f"ABI mismatch: {name}")
            if not item["deterministic"]:
                failures.append(f"non-deterministic export: {name}")
            if item["output_less"]:
                failures.append(f"output-less member, nothing observable to compare: {name}")
                continue
            if not item["miter_selfcheck"]:
                failures.append(f"miter drives implicit nets: {name}")
            if not item["view_trusted"]:
                failures.append(f"synthesizable view failed conservation: {name}")
            proof = result.get("sat_miter") or result.get("yosys_equiv") or {}
            if result.get("verilator", {}).get("status") != "PASS":
                failures.append(f"{name}:verilator")
            if result.get("locked_verilator", {}).get("status") != "PASS":
                failures.append(f"{name}:locked reference verilator")
            if proof.get("status") != "PASS":
                failures.append(f"{name}:{'sat_miter' if 'sat_miter' in result and result['method'] == 'sat_miter' else 'yosys_equiv'}")
            if "unproven_cells" in proof and proof.get("unproven_cells"):
                failures.append(f"{name}: {proof['unproven_cells']} $equiv cells unproven")
            if item["sequential"] and (
                    not isinstance(proof.get("equiv_cells"), int)
                    or proof.get("equiv_cells", 0) <= 0):
                failures.append(f"{name}: zero or missing $equiv cells")
            if "unconstrained" in proof and not proof["unconstrained"]:
                failures.append(f"{name}: SAT ran under assumptions")
        if aggregate.get("status") not in ("PASS", "NOT_APPLICABLE"):
            failures.append("aggregate SAT miter")
        if control["status"] != "PASS":
            failures.append("negative control did not detect a mutated design")
        for gate, result in pyright.items():
            if result["status"] != "PASS":
                failures.append(f"pyright {gate}")
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
                "locked_reference_lint": results[index].get("locked_verilator", {}).get("status"),
                "verdict": proof.get("status"),
                "success_marker": proof.get("formal_success_marker"),
                "markers_present": proof.get("markers_present"),
                "unconstrained_or_equiv_cells": (proof.get("unconstrained")
                                                 if not item["sequential"] else proof.get("equiv_cells")),
                "proven_cells": proof.get("proven_cells"),
                "unproven_cells": proof.get("unproven_cells"),
                "sat_variables": proof.get("sat_variables"),
                "sat_clauses": proof.get("sat_clauses"),
            }
        sources: dict[str, Any] = {
            "validator": {"path": Path(__file__).relative_to(ROOT).as_posix(),
                          "sha256": sha256_file(Path(__file__)),
                          "bytes": Path(__file__).stat().st_size},
            "python_build": {"path": self.build_path.relative_to(ROOT).as_posix(),
                             "sha256": sha256_file(self.build_path),
                             "bytes": self.build_path.stat().st_size},
            "reference_sv": {"path": f"validation/reference-sv/{members[0]}.sv",
                             "sha256": sha256_file(REF_DIR / f"{members[0]}.sv"),
                             "bytes": (REF_DIR / f"{members[0]}.sv").stat().st_size},
        }
        if self.scala_path is not None and self.scala_path.is_file():
            sources["scala"] = {"path": self.scala_path.relative_to(ROOT).as_posix(),
                                "sha256": sha256_file(self.scala_path),
                                "bytes": self.scala_path.stat().st_size}
        sources["declared_scala_sources"] = declared_scala_sources(self.build_path)
        child_paths = sorted({path for item in items
                              for path in item["locked_sources"][:-1]})
        sources["reference_children"] = {
            path.stem: {"path": path.relative_to(ROOT).as_posix(),
                        "sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in child_paths
        }
        payload: dict[str, Any] = {
            "schema_version": 1,
            "kind": "XIANGSHAN_KUNMINGHU_V2_STRICT_COMPLETE_EQUIVALENCE",
            "build_id": self.build_id,
            "validator": Path(__file__).relative_to(ROOT).as_posix(),
            "status": status,
            "strict_complete_eligible": status == "COMPLETE_EQUIVALENCE",
            "strict_complete_count_delta": 1 if status == "COMPLETE_EQUIVALENCE" else 0,
            "acceptance_eligible": status == "COMPLETE_EQUIVALENCE",
            "source_commit": SOURCE_COMMIT,
            "audit_policy": {"require_negative_control": True,
                             "require_two_sided_negative_control": True,
                             "require_locked_reference_lint": True,
                             "require_validator_hash": True,
                             "scope_source": "Build catalog tables"},
            "scope": {
                "kind": "catalog_build_multi_variant",
                "public_variants": members,
                "variant_count": len(members),
                "combinational_variants": sum(1 for item in items if not item["sequential"]),
                "sequential_variants": sum(1 for item in items if item["sequential"]),
                "inputs": {f"{item['name']}_{p}": w for item in items
                           for p, w in item["inputs"].items()},
                "outputs_compared": {f"{item['name']}_{p}": w for item in items
                                     for p, w in item["outputs"].items()},
                "aggregate_input_bits": sum(sum(item["inputs"].values()) for item in items),
                "aggregate_compared_output_bits": sum(sum(item["outputs"].values()) for item in items),
                "variants": variants,
                "why_complete": "Every locked module named by this Build's own tables is proven "
                                "against its exact-name locked reference on the rail its timing "
                                "requires, with a conservation-audited 5C view where the installed "
                                "Yosys cannot read the original.",
                "bounded_tests_counted": False,
            },
            "reference_lock": {
                "directory": "validation/reference-sv",
                "xstop_sha256": XSTOP_SHA256,
                "locked_references_written": False,
                "sha256_by_module": {item["name"]: item["locked_sha256"] for item in items},
            },
            "sources": sources,
            "checks": {
                "py_compile": {"status": "PASS"},
                "pyright": pyright,
                "catalog_coverage": {"entries": len(members),
                                     "proven": sum(1 for v in variants.values() if v["verdict"] == "PASS")},
                "formal": {"yosys_formal_miter": aggregate},
                "aggregate_sat_miter": aggregate,
                "negative_control": control,
                "variants": results,
            },
            "failures": failures,
            "unclosed": [] if not failures else ["strict gates did not all pass"],
            "acceptance_unclosed": [
                "Parent closure, full-top differential, final license review, and user approval "
                "remain outside this Build proof."
            ],
        }
        self.evidence_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8", newline="\n")
        return payload
