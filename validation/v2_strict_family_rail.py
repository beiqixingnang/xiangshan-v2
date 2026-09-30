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
import inspect
import importlib.util
import importlib.metadata as importlib_metadata
import json
import py_compile
import platform
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

# Formal proofs are expensive and the previous rail discarded all progress at
# the start of every run.  Keep a small content addressed checkpoint beside
# the generated pair files so a retry resumes at the first incomplete stage.
CACHE_SCHEMA = 4
WSL_PATH_CACHE: dict[str, str] = {}
TOOL_VERSION_CACHE: dict[str, str] | None = None


def path_cache_key(path: Path) -> str:
    """Return one stable key for a path conversion cache entry."""

    return str(path.resolve())

SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
SAT_MARKER = "SAT proof finished - no model found: SUCCESS!"
EQUIV_MARKERS = ("0 are unproven.", "Equivalence successfully proven!")
ANSI_PORT = re.compile(r"^(input|output)\s+(?:\[\s*(\d+):0\]\s*)?(.+)$")
BLOCK_LOCAL = re.compile(
    r"^([ \t]*)automatic\s+logic\s+((?:\[[^\]]*\][ \t]*)+)?"
    r"([A-Za-z_]\w*(?:\[[^\]]*\])?(?:\s*,\s*[A-Za-z_]\w*(?:\[[^\]]*\])?)*)"
    r"[ \t]*;[ \t]*$", re.M)
# Generated references commonly wrap an initialized automatic declaration over
# several lines.  Keep the expression as one syntactic statement while
# allowing embedded newlines; the terminating semicolon is the only delimiter
# because comments have already been stripped by ``synthesizable_view``.
INIT_DECL = re.compile(
    r"^([ \t]*)automatic[ \t]+logic[ \t]+((?:\[[^\]]*\][ \t]*)+)?([A-Za-z_]\w*)[ \t]*=[ \t]*(.*?);[ \t]*$",
    re.M | re.S)
INIT_DECL_START = re.compile(
    r"^[ \t]*automatic[ \t]+logic[ \t]+(?:\[[^\]]*\][ \t]*)*[A-Za-z_]\w*[ \t]*=")
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

    key = path_cache_key(path)
    cached = WSL_PATH_CACHE.get(key)
    if cached is not None:
        return cached
    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", key],
                            capture_output=True, check=True)
    converted = result.stdout.decode("utf-8", "replace").strip()
    WSL_PATH_CACHE[key] = converted
    return converted


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


def validation_tool_versions() -> dict[str, str]:
    """Return tool versions that affect deterministic export and formal results."""

    global TOOL_VERSION_CACHE
    if TOOL_VERSION_CACHE is not None:
        return dict(TOOL_VERSION_CACHE)
    try:
        amaranth_version = importlib_metadata.version("amaranth")
    except importlib_metadata.PackageNotFoundError:
        amaranth_version = "unavailable"
    try:
        result = subprocess.run(
            ["wsl.exe", "-e", "bash", "-lc", "yosys -V; verilator --version"],
            capture_output=True, check=False, timeout=30,
        )
        tool_text = (result.stdout + result.stderr).decode("utf-8", "replace")
        yosys_match = re.search(r"Yosys\s+[^\r\n]+", tool_text)
        verilator_match = re.search(r"Verilator\s+[^\r\n]+", tool_text)
        yosys_version = yosys_match.group(0).strip() if yosys_match else "unavailable"
        verilator_version = verilator_match.group(0).strip() if verilator_match else "unavailable"
    except (OSError, subprocess.TimeoutExpired):
        yosys_version = "unavailable"
        verilator_version = "unavailable"
    TOOL_VERSION_CACHE = {
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "host": platform.platform(),
        "amaranth": amaranth_version,
        "yosys": yosys_version,
        "verilator": verilator_version,
    }
    return dict(TOOL_VERSION_CACHE)


def tool_versions_complete(versions: dict[str, str]) -> bool:
    """Return whether the fingerprint identified every proof-critical runtime."""

    return all(versions.get(name) not in (None, "", "unavailable")
               for name in ("python", "amaranth", "yosys", "verilator"))


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


def canonicalize_plain_declarations(lines: list[str], top: str) -> list[str]:
    """Join only known multiline plain declarations into statement records.

    CtrlBlock and LoadQueueRAW contain generated declarations whose packed
    width/name are split across physical lines.  Their behavior is unchanged;
    joining the declaration span lets the conservation audit operate on
    declarations rather than accidentally treating a continuation as logic.
    All other references retain the original physical-line path.
    """

    if top not in {"CtrlBlock", "LoadQueueRAW"}:
        return lines
    result: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("automatic logic") and "=" not in line:
            end = index
            while end < len(lines) and ";" not in lines[end]:
                end += 1
            if end < len(lines) and end > index:
                result.append(" ".join(lines[index:end + 1]))
                index = end + 1
                continue
        result.append(line)
        index += 1
    return result


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
    lines = canonicalize_plain_declarations(lines, top)
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
    # A wrapped declaration contributes only its first rewritten line to the
    # multiset delta: continuation lines are already present verbatim in the
    # locked body and therefore are not "appeared" lines.  This keeps the
    # conservation check one-for-one while still retaining the full expression
    # in ``normalized``.
    expected_rewrites = [f"{n} = {e};".splitlines()[0] for _, n, e in initialized]
    permitted = expected_declarations + expected_rewrites
    appeared = list((view_counts - locked_counts).elements())
    conserved = (all(BLOCK_LOCAL.match(line) is not None or INIT_DECL_START.match(line) is not None
                     for line in disappeared)
                 and len(disappeared) == len(plain_lines) + len(initialized)
                 and Counter(appeared) == Counter(permitted)
                 and len(view_lines) == len(lines) + len(initialized))
    # Keep indentation matching on the current physical line.  ``\s`` also
    # consumes newlines, which made equivalent equations appear different
    # after declarations were hoisted and produced false untrusted results.
    registers_before = re.findall(r"^[ \t]*[A-Za-z_]\w*[ \t]*<=[ \t]*.+;$", body, re.M)
    registers_after = re.findall(r"^[ \t]*[A-Za-z_]\w*[ \t]*<=[ \t]*.+;$", normalized, re.M)
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
        self.cache_path = (ROOT / "validation/.cache/strict-family"
                           / re.sub(r"\W+", "_", build_id).strip("_").lower()
                           / "rail-checkpoint.json")
        self._cache: dict[str, Any] = {}
        self._cache_loaded = False

    def load_cache(self) -> None:
        """Load a checkpoint if it has the current schema and source identity."""

        if self._cache_loaded:
            return
        self._cache_loaded = True
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        if isinstance(payload, dict) and payload.get("schema_version") == CACHE_SCHEMA:
            self._cache = payload
        else:
            self._cache = {"schema_version": CACHE_SCHEMA, "members": {}, "stages": {}}

    def save_cache(self) -> None:
        """Atomically persist the checkpoint without touching locked inputs."""

        self.work.mkdir(parents=True, exist_ok=True)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cache_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._cache, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8", newline="\n")
        temporary.replace(self.cache_path)

    def member_cache_key(self, name: str, children: list[str], target_rtl: str,
                         reference_view: str, miter: str) -> str:
        """Build a content key that invalidates on any relevant source change."""

        records: list[tuple[str, str]] = [
            ("rail", sha256_file(Path(__file__))),
            ("target_rtl", hashlib.sha256(target_rtl.encode()).hexdigest()),
            ("reference_view", hashlib.sha256(reference_view.encode()).hexdigest()),
            ("miter", hashlib.sha256(miter.encode()).hexdigest()),
        ]
        producer_paths: set[Path] = set()
        for producer_type in type(self).__mro__:
            producer_module = sys.modules.get(producer_type.__module__)
            producer_path = Path(str(getattr(producer_module, "__file__", "")))
            if producer_path.is_file():
                producer_paths.add(producer_path.resolve())
        for producer_path in sorted(producer_paths):
            records.append(("producer_mro:" + producer_path.as_posix(), sha256_file(producer_path)))
        caller_path: Path | None = None
        for frame in inspect.stack()[1:]:
            frame_path = Path(frame.filename).resolve()
            if frame_path != Path(__file__).resolve() and frame_path.is_file():
                caller_path = frame_path
                break
        if caller_path is not None:
            records.append(("caller_validator", sha256_file(caller_path)))
        for child in sorted(set(children) | {name}):
            path = REF_DIR / f"{child}.sv"
            records.append((child, sha256_file(path)))
        if self.scala_path is not None and self.scala_path.is_file():
            records.append(("scala", sha256_file(self.scala_path)))
        versions = validation_tool_versions()
        records.append(("tool_versions", hashlib.sha256(
            json.dumps(versions, sort_keys=True).encode()).hexdigest()))
        records.append(("build_id", self.build_id))
        return hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()

    @staticmethod
    def path_value(value: Any) -> Any:
        """Convert Paths to JSON-safe strings recursively."""

        if isinstance(value, Path):
            return {"__path__": str(value)}
        if isinstance(value, dict):
            return {str(k): FamilyRail.path_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [FamilyRail.path_value(v) for v in value]
        return value

    @staticmethod
    def restore_paths(value: Any) -> Any:
        """Restore Paths from a checkpoint value."""

        if isinstance(value, dict):
            if set(value) == {"__path__"}:
                return Path(str(value["__path__"]))
            return {k: FamilyRail.restore_paths(v) for k, v in value.items()}
        if isinstance(value, list):
            return [FamilyRail.restore_paths(v) for v in value]
        return value

    def cached_item(self, key: str) -> dict[str, Any] | None:
        self.load_cache()
        raw = self._cache.get("members", {}).get(key)
        if not isinstance(raw, dict):
            return None
        item = self.restore_paths(raw.get("item"))
        if not isinstance(item, dict):
            return None
        paths = [item.get(name) for name in ("target", "reference", "miter")]
        if any(not isinstance(path, Path) or not path.is_file() for path in paths):
            return None
        expected = item.get("prepared_hashes")
        if not isinstance(expected, dict):
            return None
        for label, path in zip(("target", "reference", "miter"), paths):
            if not isinstance(path, Path) or expected.get(label) != sha256_file(path):
                return None
        return item

    def prepare(self, module: Any, name: str) -> dict[str, Any]:
        locked_text = (REF_DIR / f"{name}.sv").read_text(encoding="utf-8")
        ports = declared_ports(locked_text, name)
        closure, children, audits = locked_closure(name)
        target_rtl = export_member(module, name)
        deterministic_rtl = export_member(module, name)
        inputs = {p: w for p, (d, w) in ports.items() if d == "input"}
        outputs = {p: w for p, (d, w) in ports.items() if d == "output"}
        miter = miter_text(name, inputs, outputs)
        cache_key = self.member_cache_key(name, children, target_rtl, closure, miter)
        cached = self.cached_item(cache_key)
        if cached is not None:
            cached["cache_key"] = cache_key
            cached["cache_hit"] = True
            cached["deterministic"] = deterministic_rtl == target_rtl
            cached["abi_exact"] = declared_ports(target_rtl, f"DUT_{name}") == ports
            return cached

        target_path = self.work / f"DUT_{name}.sv"
        reference_path = self.work / f"REF_{name}.sv"
        miter_path = self.work / f"{name}_MITER.sv"
        target_path.write_text(target_rtl, encoding="utf-8", newline="\n")
        reference_path.write_text(closure, encoding="utf-8", newline="\n")
        miter_path.write_text(miter, encoding="utf-8", newline="\n")
        item = {
            "name": name, "inputs": inputs, "outputs": outputs, "children": children,
            "sequential": any(
                direction == "input"
                and (port in ("clock", "clk", "io_clock", "io_clk")
                     or port.endswith("_clock") or port.endswith("_clk"))
                for port, (direction, _width) in ports.items()),
            "abi_exact": declared_ports(target_rtl, f"DUT_{name}") == ports,
            "deterministic": deterministic_rtl == target_rtl,
            "output_less": not outputs,
            "miter_selfcheck": bool(outputs) and nets_declared(miter),
            "view_trusted": all(audit["view_trusted"] for audit in audits),
            "view_audits": audits,
            "locked_sha256": sha256_file(REF_DIR / f"{name}.sv"),
            "locked_sources": [REF_DIR / f"{child}.sv" for child in children]
                              + [REF_DIR / f"{name}.sv"],
            "target": target_path, "reference": reference_path, "miter": miter_path,
            "wsl": {
                "target": wsl_path(target_path),
                "reference": wsl_path(reference_path),
                "miter": wsl_path(miter_path),
                "locked_sources": [wsl_path(path) for path in
                                    ([REF_DIR / f"{child}.sv" for child in children]
                                     + [REF_DIR / f"{name}.sv"])],
            },
            "cache_key": cache_key,
            "cache_hit": False,
            "tool_versions": validation_tool_versions(),
            "prepared_hashes": {
                "target": sha256_file(target_path),
                "reference": sha256_file(reference_path),
                "miter": sha256_file(miter_path),
            },
        }
        self.load_cache()
        self._cache.setdefault("members", {})[cache_key] = {
            "name": name,
            "item": self.path_value(item),
        }
        self.save_cache()
        return item

    def prove(self, item: dict[str, Any]) -> dict[str, Any]:
        name = item["name"]
        if item.get("static_blocked"):
            return {"method": "sequential_equivalence" if item["sequential"] else "sat_miter",
                    "status": "NOT_RUN", "reason": "static gate failed",
                    "verilator": item.get("verilator", {"status": "NOT_RUN"}),
                    "locked_verilator": item.get("locked_verilator", {"status": "NOT_RUN"}),
                    "sat_miter": {"status": "NOT_RUN"} if not item["sequential"] else None,
                    "yosys_equiv": {"status": "NOT_RUN"} if item["sequential"] else None}
        wsl = item.get("wsl", {})
        target_wsl = str(wsl["target"]) if "target" in wsl else wsl_path(item["target"])
        reference_wsl = str(wsl["reference"]) if "reference" in wsl else wsl_path(item["reference"])
        miter_wsl = str(wsl["miter"]) if "miter" in wsl else wsl_path(item["miter"])
        locked_wsl = [str(value) for value in wsl.get("locked_sources", [])]
        pair = " ".join(shlex.quote(value) for value in (target_wsl, reference_wsl))
        files = pair + " " + shlex.quote(miter_wsl)
        lint = item.get("verilator")
        locked_lint = item.get("locked_verilator")
        if not isinstance(lint, dict) or not isinstance(locked_lint, dict):
            lint, locked_lint = self.lint_gate(item)
        item["verilator"] = lint
        item["locked_verilator"] = locked_lint
        if lint.get("status") != "PASS" or locked_lint.get("status") != "PASS":
            result = {"method": "sequential_equivalence" if item["sequential"] else "sat_miter",
                      "verilator": lint, "locked_verilator": locked_lint,
                      "sat_miter": {"status": "NOT_RUN", "reason": "lint gate failed"}
                      if not item["sequential"] else None,
                      "yosys_equiv": {"status": "NOT_RUN", "reason": "lint gate failed"}
                      if item["sequential"] else None}
            return result
        if not item["sequential"]:
            script = (f"read_verilog -sv {files}; prep -top {name}_MITER; flatten; opt; "
                      "sat -prove mismatch 0")
            proof = run_wsl(["yosys", "-Q", "-p", script])
            proof["formal_success_marker"] = (
                isinstance(proof.get("returncode"), int)
                and not isinstance(proof.get("returncode"), bool)
                and proof.get("returncode") == 0
                and proof.get("status") == "PASS"
                and proof.get("sat_success_marker") is True
            )
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
        proof["formal_success_marker"] = (
            isinstance(proof.get("returncode"), int)
            and not isinstance(proof.get("returncode"), bool)
            and proof.get("returncode") == 0
            and proof.get("status") == "PASS"
            and isinstance(markers, dict)
            and all(markers.get(marker) is True for marker in EQUIV_MARKERS)
        )
        if isinstance(proof.get("equiv_cells_full"), int):
            proof["equiv_cells"] = proof["equiv_cells_full"]
        summary = proof.get("equiv_summary_full")
        if isinstance(summary, list) and len(summary) == 2:
            proof["proven_cells"], proof["unproven_cells"] = summary
        if isinstance(proof.get("equiv_failed_full"), int):
            proof["unproven_cells"] = proof["equiv_failed_full"]
        if proof.get("returncode") != 0 or not proof["formal_success_marker"]:
            proof["status"] = "FAIL"
        return {"method": "sequential_equivalence", "verilator": lint,
                "locked_verilator": locked_lint, "yosys_equiv": proof}

    @staticmethod
    def formal_result_pass(result: dict[str, Any], item: dict[str, Any]) -> bool:
        """Recheck the full formal success contract before accepting a cache hit."""

        if (item.get("abi_exact") is not True
                or item.get("deterministic") is not True
                or item.get("view_trusted") is not True
                or not tool_versions_complete(item.get("tool_versions", {}))
                or result.get("verilator", {}).get("status") != "PASS"
                or result.get("locked_verilator", {}).get("status") != "PASS"):
            return False
        proof = result.get("sat_miter") or result.get("yosys_equiv")
        if not isinstance(proof, dict) or proof.get("status") != "PASS" \
                or not isinstance(proof.get("returncode"), int) \
                or isinstance(proof.get("returncode"), bool) \
                or proof.get("returncode") != 0 or proof.get("timed_out") is True \
                or proof.get("formal_success_marker") is not True:
            return False
        command = proof.get("command", [])
        command_text = " ".join(str(value) for value in command) \
            if isinstance(command, list) else str(command)
        if not item.get("sequential"):
            return (proof.get("sat_success_marker") is True
                    and proof.get("unconstrained") is True
                    and "sat -prove mismatch 0" in command_text)
        markers = proof.get("markers_present", {})
        return (
            isinstance(markers, dict)
            and all(markers.get(marker) is True for marker in EQUIV_MARKERS)
            and isinstance(proof.get("equiv_cells"), int)
            and not isinstance(proof.get("equiv_cells"), bool)
            and proof.get("equiv_cells", 0) > 0
            and isinstance(proof.get("proven_cells"), int)
            and not isinstance(proof.get("proven_cells"), bool)
            and proof.get("proven_cells") == proof.get("equiv_cells")
            and isinstance(proof.get("unproven_cells"), int)
            and not isinstance(proof.get("unproven_cells"), bool)
            and proof.get("unproven_cells") == 0
            and "equiv_induct -undef" in command_text
            and "equiv_status -assert" in command_text
        )

    def remember_formal(self, cache_key: str, result: dict[str, Any],
                         proof: dict[str, Any], item: dict[str, Any]) -> None:
        """Record a completed formal attempt for resumable member execution."""

        if not cache_key:
            return
        self.load_cache()
        reusable = self.formal_result_pass(result, item)
        self._cache.setdefault("formal", {})[cache_key] = {
            "reusable": reusable,
            "result": self.path_value(result),
        }
        self.save_cache()

    def cached_formal(self, cache_key: str, item: dict[str, Any]) -> dict[str, Any] | None:
        """Return the original full-PASS receipt only when its proof still matches."""

        self.load_cache()
        formal = self._cache.get("formal", {})
        cached = formal.get(cache_key) if isinstance(formal, dict) else None
        if not isinstance(cached, dict) or cached.get("reusable") is not True:
            return None
        result = self.restore_paths(cached.get("result"))
        if not isinstance(result, dict) or not self.formal_result_pass(result, item):
            return None
        return result

    @staticmethod
    def aggregate_result_pass(result: dict[str, Any], items: list[dict[str, Any]]) -> bool:
        """Require a complete aggregate SAT receipt, including output coverage."""

        combinational = sum(not item["sequential"] for item in items)
        if not combinational:
            return result.get("status") == "NOT_APPLICABLE" \
                and result.get("mitered_variants") == 0
        command = result.get("command", [])
        command_text = " ".join(str(value) for value in command) \
            if isinstance(command, list) else str(command)
        return (result.get("status") == "PASS"
                and type(result.get("returncode")) is int
                and result["returncode"] == 0
                and result.get("timed_out") is not True
                and result.get("formal_success_marker") is True
                and result.get("sat_success_marker") is True
                and result.get("unconstrained") is True
                and result.get("mitered_variants") == combinational
                and "sat -prove mismatch 0" in command_text)

    @staticmethod
    def controls_result_pass(result: dict[str, Any], items: list[dict[str, Any]]) -> bool:
        """Require applied, decisive mutations on both sides of each used rail."""

        cases = result.get("cases")
        if result.get("status") != "PASS" or not isinstance(cases, dict):
            return False
        kinds = {"sequential" if item["sequential"] else "sat" for item in items}
        for kind in kinds:
            for side in ("target", "reference"):
                case = cases.get(f"{kind}.{side}")
                if (not isinstance(case, dict) or case.get("status") != "PASS"
                        or case.get("mutation_applied") is not True
                        or case.get("explicit_failure_marker") is not True
                        or case.get("success_marker_still_present") is not False
                        or type(case.get("returncode")) is not int):
                    return False
        return True

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
        proof["formal_success_marker"] = (
            isinstance(proof.get("returncode"), int)
            and not isinstance(proof.get("returncode"), bool)
            and proof.get("returncode") == 0
            and proof.get("status") == "PASS"
            and proof.get("sat_success_marker") is True
        )
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
                        rf"assign\s+{re.escape(candidate)}\s*=\s*(?P<rhs>[^;]+);",
                        lambda match: f"assign {candidate} = ~({match.group('rhs')});",
                        body, count=1)
                    if count != 1:
                        mutated_body, count = re.subn(
                            rf"\b{re.escape(candidate)}\s*<=\s*(?P<rhs>[^;]+);",
                            lambda match: f"{candidate} <= ~({match.group('rhs')});",
                            body, count=1)
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

    @staticmethod
    def cheap_static_failures(item: dict[str, Any]) -> list[str]:
        """Return failures that are known without invoking Verilator/Yosys."""

        name = str(item["name"])
        failures: list[str] = []
        if not item.get("abi_exact"):
            failures.append(f"ABI mismatch: {name}")
        if not item.get("deterministic"):
            failures.append(f"non-deterministic export: {name}")
        if item.get("output_less"):
            failures.append(f"output-less member, nothing observable to compare: {name}")
        if not item.get("miter_selfcheck"):
            failures.append(f"miter drives implicit nets: {name}")
        if not item.get("view_trusted"):
            failures.append(f"synthesizable view failed conservation: {name}")
        return failures

    def lint_gate(self, item: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Run or restore both Verilator lint gates before any formal command."""

        self.load_cache()
        cache_key = str(item.get("cache_key", ""))
        static = self._cache.setdefault("static", {})
        cached = static.get(cache_key) if isinstance(static, dict) else None
        if isinstance(cached, dict) and isinstance(cached.get("verilator"), dict):
            lint = self.restore_paths(cached["verilator"])
            locked = self.restore_paths(cached.get("locked_verilator", {"status": "NOT_RUN"}))
            if (tool_versions_complete(validation_tool_versions())
                    and lint.get("status") == "PASS" and locked.get("status") == "PASS"):
                item["verilator"], item["locked_verilator"] = lint, locked
                return lint, locked
        wsl = item.get("wsl", {})
        target_wsl = str(wsl["target"]) if "target" in wsl else wsl_path(item["target"])
        reference_wsl = str(wsl["reference"]) if "reference" in wsl else wsl_path(item["reference"])
        miter_wsl = str(wsl["miter"]) if "miter" in wsl else wsl_path(item["miter"])
        locked_wsl = [str(value) for value in wsl.get("locked_sources", [])]
        lint = run_wsl(["verilator", "--lint-only", "-Wno-fatal", "--top-module",
                        f"{item['name']}_MITER", target_wsl, reference_wsl, miter_wsl])
        locked = run_wsl(
            ["verilator", "--lint-only", "-Wno-fatal", "-DSYNTHESIS", "--top-module",
             item["name"]] + (locked_wsl or [wsl_path(path) for path in item["locked_sources"]]))
        item["verilator"], item["locked_verilator"] = lint, locked
        if cache_key:
            static[cache_key] = {"verilator": self.path_value(lint),
                                 "locked_verilator": self.path_value(locked)}
            self.save_cache()
        return lint, locked

    def run(self) -> dict[str, Any]:
        """Prove every member and persist the evidence."""

        module = load_module("rail_" + re.sub(r"\W+", "_", self.build_id), self.build_path)
        members = enumerate_members(module, self.build_path)
        py_compile.compile(str(self.build_path), doraise=True)
        py_compile.compile(str(Path(__file__)), doraise=True)
        self.work.mkdir(parents=True, exist_ok=True)
        self.load_cache()
        items = [self.prepare(module, name) for name in members]
        pyright = {"build": pyright_check(self.build_path), "rail": pyright_check(Path(__file__))}
        failures: list[str] = []
        for item in items:
            item_failures = self.cheap_static_failures(item)
            if not item_failures and all(check.get("status") == "PASS" for check in pyright.values()):
                lint, locked_lint = self.lint_gate(item)
                if lint.get("status") != "PASS":
                    item_failures.append(f"{item['name']}:verilator")
                if locked_lint.get("status") != "PASS":
                    item_failures.append(f"{item['name']}:locked reference verilator")
            item["static_failures"] = item_failures
            item["static_blocked"] = bool(item_failures) or any(
                check.get("status") != "PASS" for check in pyright.values())
            failures.extend(item_failures)
        for gate, check in pyright.items():
            if check["status"] != "PASS":
                failures.append(f"pyright {gate}")

        # Formal is strictly downstream of the cheap gates.  A failed static
        # member is emitted as NOT_RUN and does not consume a 900 second gate.
        results: list[dict[str, Any]] = []
        for item in items:
            cache_key = str(item.get("cache_key", ""))
            cached_formal = None if item.get("static_blocked") else self.cached_formal(cache_key, item)
            item["formal_cache_hit"] = cached_formal is not None
            candidate: Any = (cached_formal if cached_formal is not None else
                              FamilyRail.prove(self, item) if item.get("static_blocked")
                              else self.prove(item))
            if not isinstance(candidate, dict):
                candidate = {
                    "method": "sequential_equivalence" if item["sequential"] else "sat_miter",
                    "status": "FAIL", "reason": "validator returned a non-object result",
                }
            proof_result: Any = candidate
            proof = proof_result.get("sat_miter") or proof_result.get("yosys_equiv")
            if isinstance(proof, dict) and proof.get("status") not in (None, "NOT_RUN"):
                self.remember_formal(cache_key, proof_result, proof, item)
            results.append(proof_result)
        member_formal_pass = all(
            not item.get("static_blocked")
            and (proof_result.get("sat_miter") or proof_result.get("yosys_equiv") or {}).get("status") == "PASS"
            and proof_result.get("verilator", {}).get("status") == "PASS"
            and proof_result.get("locked_verilator", {}).get("status") == "PASS"
            and self.formal_result_pass(proof_result, item)
            for item, proof_result in zip(items, results)
        )
        stage_key = hashlib.sha256(json.dumps([
            item.get("cache_key") for item in items
        ] + [
            (result.get("sat_miter") or result.get("yosys_equiv") or {}).get("output_sha256")
            for result in results
        ], sort_keys=True).encode()).hexdigest()
        stages = self._cache.setdefault("stages", {})
        cached_aggregate = stages.get("aggregate") if isinstance(stages, dict) else None
        if member_formal_pass and isinstance(cached_aggregate, dict) \
                and cached_aggregate.get("key") == stage_key \
                and isinstance(cached_aggregate.get("result"), dict) \
                and self.aggregate_result_pass(cached_aggregate["result"], items):
            aggregate = self.restore_paths(cached_aggregate["result"])
        elif member_formal_pass:
            aggregate = self.aggregate(items)
            if not self.aggregate_result_pass(aggregate, items):
                aggregate["status"] = "FAIL"
            if isinstance(stages, dict):
                stages["aggregate"] = {"key": stage_key, "result": self.path_value(aggregate)}
                self.save_cache()
        else:
            aggregate = {"status": "NOT_RUN", "mitered_variants": 0,
                         "reason": "member static/formal gate failed"}
        cached_control = stages.get("negative_control") if isinstance(stages, dict) else None
        if self.aggregate_result_pass(aggregate, items) and isinstance(cached_control, dict) \
                and cached_control.get("key") == stage_key \
                and isinstance(cached_control.get("result"), dict) \
                and self.controls_result_pass(cached_control["result"], items):
            control = self.restore_paths(cached_control["result"])
        elif self.aggregate_result_pass(aggregate, items):
            control = self.negative_control(items)
            if not self.controls_result_pass(control, items):
                control["status"] = "FAIL"
            if isinstance(stages, dict):
                stages["negative_control"] = {"key": stage_key, "result": self.path_value(control)}
                self.save_cache()
        else:
            control = {"status": "NOT_RUN", "cases": {},
                       "reason": "aggregate gate failed"}
        for item, proof_result in zip(items, results):
            name = item["name"]
            proof = proof_result.get("sat_miter") or proof_result.get("yosys_equiv") or {}
            if item.get("static_blocked"):
                continue
            if proof_result.get("verilator", {}).get("status") != "PASS":
                failures.append(f"{name}:verilator")
            if proof_result.get("locked_verilator", {}).get("status") != "PASS":
                failures.append(f"{name}:locked reference verilator")
            if proof.get("status") != "PASS":
                failures.append(f"{name}:{'sat_miter' if 'sat_miter' in proof_result and proof_result['method'] == 'sat_miter' else 'yosys_equiv'}")
            elif not self.formal_result_pass(proof_result, item):
                failures.append(f"{name}:strict formal contract")
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
            "proof_execution_profile": "RECOVERABLE_STRICT_FAMILY_V2",
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
                "stages": {
                    "static_preflight": "PASS" if not any(item.get("static_blocked") for item in items) else "FAIL",
                    "formal_members": "PASS" if member_formal_pass else "NOT_RUN_OR_FAIL",
                    "aggregate": aggregate.get("status"),
                    "negative_control": control.get("status"),
                    "resume": {
                        "checkpoint": str(self.cache_path),
                        "prepared_cache_hits": sum(bool(item.get("cache_hit")) for item in items),
                        "formal_cache_hits": sum(bool(item.get("formal_cache_hit")) for item in items),
                        "member_count": len(items),
                    },
                    "tool_versions": validation_tool_versions(),
                },
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
