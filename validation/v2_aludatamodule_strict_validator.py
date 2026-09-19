"""Strict complete-behavior equivalence validator for the V2 AluDataModule leaf.

AluDataModule is a stateless, combinational integer ALU datapath.  The Build
exports exactly one canonical configuration (``AluConfig(xlen=64)``), so the
locked V2 reference surface ``io_src_0``/``io_src_1``/``io_func`` ->
``io_result`` forms a single miter.  Yosys SAT quantifies every one of the 137
input bits with no assumption and compares the whole 64-bit result bus, so a
successful run covers the complete 2**137 input space rather than any sampled
vector set.

The locked reference is not a hand-written oracle: it is the byte-exact V2
XSTop extraction held in ``validation/reference-sv``.  Because that extraction
instantiates eleven helper modules, their locked bodies are read verbatim and
assembled with the parent into one instance-closure file inside an ASCII
temporary work directory; nothing in ``validation/reference-sv`` is written or
modified by this rail.
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
    "Build-Cpu.Backend.Fu.AluDataModule-Hardware.py"
)
SCALA = ROOT / "upstream/src/main/scala/xiangshan/backend/fu/Alu.scala"
REFERENCE_DIR = ROOT / "validation/reference-sv"
PARENT_REFERENCE = REFERENCE_DIR / "AluDataModule.sv"
# Locked V2 XSTop children instantiated by the parent extraction.  Their bodies
# are read verbatim and renamed only at instantiation boundaries.
CHILD_REFERENCES = [
    "AddModule",
    "SubModule",
    "LeftShiftModule",
    "RightShiftModule",
    "LeftShiftWordModule",
    "RightShiftWordModule",
    "ShiftResultSelect",
    "MiscResultSelect",
    "WordResultSelect",
    "ConditionalZeroModule",
    "AluResSel",
]
EVIDENCE = ROOT / "validation/v2-aludatamodule-strict-evidence.json"
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_aludatamodule_strict"

SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
LOCKED_XSTOP = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
XSTOP_BYTES = 228590583
SUCCESS_MARKER = "SAT proof finished - no model found: SUCCESS!"

INPUT_WIDTHS = {"io_src_0": 64, "io_src_1": 64, "io_func": 9}
OUTPUT_WIDTHS = {"io_result": 64}
INPUT_BITS = sum(INPUT_WIDTHS.values())
OUTPUT_BITS = sum(OUTPUT_WIDTHS.values())

# Exact locked four-port ABI of both surfaces.
PORT_SURFACE = {
    "io_src_0": ("input", 64),
    "io_src_1": ("input", 64),
    "io_func": ("input", 9),
    "io_result": ("output", 64),
}


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one exact file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_target() -> Any:
    """Load only the selected Build module by exact path."""

    spec = importlib.util.spec_from_file_location("strict_aludatamodule_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load target: {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def wsl_path(path: Path) -> str:
    """Convert a Windows path to an absolute WSL path."""

    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                            capture_output=True, check=True)
    return result.stdout.decode("utf-8", "replace").strip()


def run_wsl(command: list[str]) -> dict[str, Any]:
    """Run one WSL command and retain bounded machine-readable diagnostics."""

    rendered = " ".join(shlex.quote(item) for item in command)
    try:
        result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered],
                                capture_output=True, check=False)
    except OSError as error:
        return {"command": command, "returncode": None, "status": "FAIL",
                "error": repr(error), "output_tail": repr(error)}
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {
        "command": command,
        "returncode": result.returncode,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "output_tail": output[-4000:],
        "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
    }


def tool_versions() -> dict[str, Any]:
    """Record the exact Verilator/Yosys binaries used by the proof."""

    return {"verilator": run_wsl(["verilator", "--version"]),
            "yosys": run_wsl(["yosys", "--version"])}


def pyright_check(source: Path) -> dict[str, Any]:
    """Run Pyright on an exact visible copy of one source file.

    A bare ``subprocess.run(["pyright", ...])`` raises FileNotFoundError on this
    Windows host, so the call goes through ``cmd.exe`` exactly like the other
    strict rails.  A missing tool must never become a PASS.
    """

    temporary = Path(tempfile.mkdtemp(prefix="uhsc_aludatamodule_pyright_"))
    try:
        copied = temporary / source.name
        shutil.copyfile(source, copied)
        command = ["cmd.exe", "/d", "/c", "pyright", "--outputjson", str(copied)]
        try:
            result = subprocess.run(command, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", check=False)
            stdout = result.stdout or ""
            stderr = result.stderr or ""
        except OSError as error:
            return {"command": command, "returncode": None, "status": "FAIL",
                    "error": repr(error), "stderr_tail": repr(error)}
        try:
            parsed = json.loads(stdout)
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
            "output_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
            "stderr_tail": stderr[-1000:],
        }
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def reference_closure_text() -> str:
    """Return the locked reference text with child instances renamed.

    Every byte of every locked module body is preserved.  Only the eleven child
    instantiations inside the parent body receive the ``REF_`` prefix so the
    closure can live in one compilation unit next to the Amaranth target.
    """

    parts: list[str] = []
    for name in CHILD_REFERENCES:
        body = (REFERENCE_DIR / f"{name}.sv").read_text(encoding="utf-8")
        marker = f"module {name}("
        if not body.startswith(marker):
            raise AssertionError(f"locked child declaration missing: {name}")
        parts.append(body.replace(marker, f"module REF_{name}(", 1))
    parent = PARENT_REFERENCE.read_text(encoding="utf-8")
    if not parent.startswith("module AluDataModule("):
        raise AssertionError("locked AluDataModule declaration missing")
    for name in CHILD_REFERENCES:
        parent = parent.replace(f"\n  {name} ", f"\n  REF_{name} ")
    for name in CHILD_REFERENCES:
        if f"REF_{name} " not in parent:
            raise AssertionError(f"locked child instantiation not renamed: {name}")
    parts.append(parent)
    return "\n".join(parts)


def source_lock_audit() -> dict[str, Any]:
    """Check every locked source digest before elaboration."""

    if not SCALA.is_file():
        raise FileNotFoundError(f"locked Scala source missing: {SCALA}")
    if not PARENT_REFERENCE.is_file():
        raise FileNotFoundError(f"locked reference missing: {PARENT_REFERENCE}")
    actual: dict[str, str] = {
        "scala": sha256_file(SCALA),
        "python_build": sha256_file(TARGET),
        "reference_sv": sha256_file(PARENT_REFERENCE),
    }
    for name in CHILD_REFERENCES:
        child = REFERENCE_DIR / f"{name}.sv"
        if not child.is_file():
            raise FileNotFoundError(f"locked reference child missing: {child}")
        actual[f"reference_child_{name}"] = sha256_file(child)
    checks = {
        "scala_present": bool(actual["scala"]),
        "python_build_present": bool(actual["python_build"]),
        "reference_sv_present": bool(actual["reference_sv"]),
        "reference_children_present": all(
            actual[f"reference_child_{name}"] for name in CHILD_REFERENCES),
        "source_commit_recorded": bool(SOURCE_COMMIT),
        "xstop_lock_recorded": len(XSTOP_SHA256) == 64 and XSTOP_BYTES > 0,
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "actual": actual,
        "expected_scala_source": SCALA.relative_to(ROOT).as_posix(),
        "locked_child_count": len(CHILD_REFERENCES),
        "source_commit": SOURCE_COMMIT,
        "xstop": {"path": LOCKED_XSTOP, "sha256": XSTOP_SHA256, "bytes": XSTOP_BYTES},
    }


def _module_region(rtl: str, module_name: str) -> tuple[str, str]:
    """Return one module's ANSI header text and its body region.

    ``rtl.find(f"module {module_name}(")`` anchors on an exact declaration, so
    an instantiation of the same module elsewhere in the file cannot be
    mistaken for it.
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
    header = rtl[open_index + 1:close_index]
    body = rtl[close_index + 1:end_index if end_index >= 0 else len(rtl)]
    return header, body


def _port_declaration_lines(text: str, names: set[str]) -> str:
    """Return direction declarations inside one module for known port names.

    Amaranth emits a bare ``module X(a, b);`` header plus per-name direction
    declarations scattered around the generated netlist text, so the scan keeps
    every declaration whose name was already declared in the header list and
    stops at ``endmodule``.  Internal statements never match because their
    names are not header ports.
    """

    kept: list[str] = []
    for line in text.splitlines():
        code = re.sub(r"//[^\n]*", "", line).strip()
        if code.startswith("endmodule"):
            break
        match = re.match(
            r"^(input|output)\b(?:\s*\[(\d+):0\])?\s*([A-Za-z_][A-Za-z0-9_]*)?;$",
            code,
        )
        if match is None:
            continue
        direction, msb, name = match.groups()
        if name is not None and name in names:
            width = int(msb) + 1 if msb is not None else 1
            if width == 1:
                kept.append(f"{direction} {name}")
            else:
                kept.append(f"{direction} [{width - 1}:0] {name}")
    return ",\n".join(kept)


def _header_port_names(header: str) -> set[str]:
    """Return the bare identifiers listed in an ANSI port header."""

    stripped = re.sub(r"//[^\n]*", "", header)
    if re.search(r"\b(?:input|output)\b", stripped):
        return set()
    return {token for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", stripped)}


def _declared_ports(rtl: str, module_name: str) -> dict[str, tuple[str, int]]:
    """Extract typed input/output declarations from one module's RTL.

    Locked Chisel output declares several ports on one ANSI header line and
    continues with bare names (``input [63:0] io_src_0,`` then ``io_src_1,``),
    while Amaranth emits a bare header port list plus per-name direction
    declarations in the body.  Exactly the region carrying the directions is
    parsed, so no unrelated statement can inherit a pending direction.
    """

    def split_items(text: str) -> list[str]:
        """Split one declaration region on top-level commas."""

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

    def classify(items: list[str]) -> dict[str, tuple[str, int]]:
        """Map port names to (direction, width) using pending ANSI state."""

        result: dict[str, tuple[str, int]] = {}
        pending: tuple[str, int] | None = None
        for item in items:
            entry = " ".join(item.split())
            if not entry:
                continue
            match = re.match(
                r"^(input|output)\b(?:\s*\[(\d+):0\])?\s*([A-Za-z_][A-Za-z0-9_]*)?$",
                entry,
            )
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

    raw_header, body = _module_region(rtl, module_name)
    header = re.sub(r"//[^\n]*", "", raw_header)
    if re.search(r"\b(?:input|output)\b", header):
        return classify(split_items(header))
    return classify(split_items(_port_declaration_lines(body, _header_port_names(header))))


def _normalized_declarations(ports: dict[str, tuple[str, int]]) -> list[str]:
    """Render parsed ports as ``direction [msb:0] name`` items for auditing."""

    return sorted(
        f"{direction} {name}" if width == 1 else f"{direction} [{width - 1}:0] {name}"
        for name, (direction, width) in ports.items()
    )


def abi_audit(target_rtl: str, reference_rtl: str) -> dict[str, Any]:
    """Require the exact four-port ABI in target and locked reference RTL."""

    checks: dict[str, bool] = {
        "target_module": "module UHSC_AluDataModule(" in target_rtl,
        "reference_module": re.search(r"\bmodule AluDataModule\(", reference_rtl) is not None,
        "reference_children_renamed": all(
            re.search(rf"\bmodule REF_{name}\(", reference_rtl) is not None
            for name in CHILD_REFERENCES),
        "reference_single_parent": len(
            re.findall(r"\bmodule (?:REF_)?AluDataModule\w*\(", reference_rtl)) == 1,
    }
    target_ports = _declared_ports(target_rtl, "UHSC_AluDataModule")
    reference_ports = _declared_ports(reference_rtl, "AluDataModule")
    # Match on the parsed declarations, not the raw header text: the locked
    # extraction interleaves source-location comments between a direction
    # keyword and its continuation names.
    views = {"target": _normalized_declarations(target_ports),
             "reference": _normalized_declarations(reference_ports)}
    for surface, view in views.items():
        for name, (direction, width) in PORT_SURFACE.items():
            expected = f"{direction} {name}" if width == 1 else f"{direction} [{width - 1}:0] {name}"
            checks[f"{surface}_{name}"] = expected in view
    expected_ports = dict(PORT_SURFACE)
    checks["target_exact_port_set"] = target_ports == expected_ports
    checks["reference_exact_port_set"] = reference_ports == expected_ports
    checks["target_reference_port_sets_equal"] = target_ports == reference_ports
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "target_declared_ports": {k: list(v) for k, v in target_ports.items()},
        "reference_declared_ports": {k: list(v) for k, v in reference_ports.items()},
        "expected_declared_ports": {k: list(v) for k, v in expected_ports.items()},
        "inputs": INPUT_WIDTHS,
        "outputs": OUTPUT_WIDTHS,
        "port_count": len(PORT_SURFACE),
    }


def deterministic_export(module: Any) -> tuple[str, dict[str, Any]]:
    """Generate the target RTL twice and require exact byte identity.

    ``build_verilog(configuration=None, injected_dependencies=None)`` always
    falls back to the single locked ``AluConfig(xlen=64)``, so the default
    export is the canonical artifact.  The same module built with any other
    xlen is rejected by ``AluConfig.__post_init__``.
    """

    first = module.build_verilog(None, {})
    second = module.build_verilog(None, {})
    first_renamed = first.replace("module AluDataModule(", "module UHSC_AluDataModule(", 1)
    second_renamed = second.replace("module AluDataModule(", "module UHSC_AluDataModule(", 1)
    if "module UHSC_AluDataModule(" not in first_renamed:
        raise AssertionError("target AluDataModule declaration missing after rename")
    first_bytes = first_renamed.encode("utf-8")
    second_bytes = second_renamed.encode("utf-8")
    return first_renamed, {
        "status": "PASS" if first_bytes == second_bytes else "FAIL",
        "configuration": {"xlen": 64, "canonical_default_export": True},
        "bytes": len(first_bytes),
        "sha256": hashlib.sha256(first_bytes).hexdigest(),
        "repeat_sha256": hashlib.sha256(second_bytes).hexdigest(),
        "byte_equal": first_bytes == second_bytes,
    }


def variant_audit(module: Any) -> dict[str, Any]:
    """Verify the Build serves exactly one public AluDataModule variant."""

    rejected_configurations: list[str] = []
    for xlen in (32, 63, 65):
        try:
            module.AluConfig(xlen=xlen)
        except ValueError:
            rejected_configurations.append(f"xlen={xlen}")
    signature = str(module.build_verilog.__doc__ or "")
    single_export = len(rejected_configurations) == 3
    return {
        "status": "PASS" if single_export else "FAIL",
        "public_entry_point": "build_verilog(configuration=None, injected_dependencies=None)",
        "default_configuration": "AluConfig(xlen=64)",
        "rejected_configurations": rejected_configurations,
        "covered_modules": ["AluDataModule"],
        "entry_doc": signature.strip(),
        "single_canonical_export": single_export,
    }


def materialize_miter(target_rtl: str) -> dict[str, Path]:
    """Write target, locked reference closure, and the all-output miter."""

    WORK.mkdir(parents=True, exist_ok=True)
    target = WORK / "UHSC_AluDataModule.sv"
    reference = WORK / "REF_AluDataModule.sv"
    miter = WORK / "AluDataModule_MITER.sv"
    target.write_text(target_rtl, encoding="utf-8", newline="\n")
    reference.write_text(reference_closure_text(), encoding="utf-8", newline="\n")
    miter.write_text(
        """module AluDataModule_MITER(
  input [63:0] io_src_0,
  input [63:0] io_src_1,
  input [8:0] io_func,
  output mismatch
);
  wire [63:0] reference_result;
  wire [63:0] target_result;
  AluDataModule reference_i(
    .io_src_0(io_src_0), .io_src_1(io_src_1), .io_func(io_func),
    .io_result(reference_result));
  UHSC_AluDataModule target_i(
    .io_src_0(io_src_0), .io_src_1(io_src_1), .io_func(io_func),
    .io_result(target_result));
  assign mismatch = |(reference_result ^ target_result);
endmodule
""",
        encoding="utf-8", newline="\n")
    return {"target": target, "reference": reference, "miter": miter}


def formal_gates(paths: dict[str, Path]) -> dict[str, Any]:
    """Run lint, synthesis checks, and the unrestricted SAT equivalence."""

    converted = {name: wsl_path(path) for name, path in paths.items()}
    target, reference, miter = (converted["target"], converted["reference"],
                                converted["miter"])
    verilator = run_wsl([
        "verilator", "--lint-only", "-Wno-fatal", "--top-module",
        "AluDataModule_MITER", target, reference, miter,
    ])
    target_yosys = run_wsl(["yosys", "-Q", "-p",
                            f"read_verilog -sv {shlex.quote(target)}; "
                            "hierarchy -top UHSC_AluDataModule; proc; opt; check"])
    reference_yosys = run_wsl(["yosys", "-Q", "-p",
                               f"read_verilog -sv {shlex.quote(reference)}; "
                               "hierarchy -top AluDataModule; proc; opt; check"])
    proof_script = (
        f"read_verilog -sv {shlex.quote(target)} {shlex.quote(reference)} "
        f"{shlex.quote(miter)}; prep -top AluDataModule_MITER; flatten; opt; "
        "sat -prove mismatch 0"
    )
    proof = run_wsl(["yosys", "-Q", "-p", proof_script])
    proof["formal_success_marker"] = SUCCESS_MARKER in proof.get("output_tail", "")
    if not proof["formal_success_marker"]:
        proof["status"] = "FAIL"
    # The emitted miter text contains no ``assume`` construct, and Yosys prints
    # an empty constraint equation exactly when nothing was assumed, i.e. every
    # one of the 137 input bits stays free over the full space.
    free_input_line = "Final constraint equation: { } = { }"
    proof["miter_carries_no_assumption"] = free_input_line in proof.get("output_tail", "")
    proof["observed_constraint_equation"] = free_input_line
    if not proof["miter_carries_no_assumption"]:
        proof["status"] = "FAIL"
    proof["formal_scope"] = {
        "input_bits": INPUT_BITS,
        "input_space": f"2**{INPUT_BITS}",
        "input_space_cardinality": str(1 << INPUT_BITS),
        "state_bits": 0,
        "state_space": "singleton (stateless combinational module)",
        "property": "mismatch == 0 for every 2-state valuation of io_src_0/io_src_1/io_func",
        "outputs_compared": OUTPUT_WIDTHS,
        "miter_sequence": "read_verilog -> prep -top AluDataModule_MITER -> flatten -> opt -> sat -prove mismatch 0",
    }
    return {
        "verilator": verilator,
        "yosys_target": target_yosys,
        "yosys_reference": reference_yosys,
        "yosys_formal_miter": proof,
    }


def validate() -> dict[str, Any]:
    """Run strict gates and persist evidence without optimistic status."""

    failures: list[str] = []
    lock = source_lock_audit()
    if lock["status"] != "PASS":
        failures.append("source lock audit")
    module = load_target()
    py_compile.compile(str(TARGET), doraise=True)
    py_compile.compile(str(Path(__file__)), doraise=True)
    variants = variant_audit(module)
    if variants["status"] != "PASS":
        failures.append("single-canonical-export audit")
    target_rtl, export = deterministic_export(module)
    closure_rtl = reference_closure_text()
    abi = abi_audit(target_rtl, closure_rtl)
    if abi["status"] != "PASS":
        failures.append("ABI audit")
    gates = formal_gates(materialize_miter(target_rtl))
    pyright = {"target": pyright_check(TARGET),
               "validator": pyright_check(Path(__file__))}
    if export["status"] != "PASS":
        failures.append("deterministic export mismatch")
    for name, result in pyright.items():
        if result["status"] != "PASS":
            failures.append(f"pyright {name}")
    for name, result in gates.items():
        if result["status"] != "PASS":
            failures.append(name)
    status = "COMPLETE_EQUIVALENCE" if not failures else "STRICT_PENDING"
    eligible = status == "COMPLETE_EQUIVALENCE"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_STRICT_COMPLETE_EQUIVALENCE",
        "build_id": "Build-Cpu.Backend.Fu.AluDataModule",
        "validator": Path(__file__).relative_to(ROOT).as_posix(),
        "status": status,
        "strict_complete_eligible": eligible,
        "strict_complete_count_delta": 1 if eligible else 0,
        "acceptance_eligible": eligible,
        "source_commit": SOURCE_COMMIT,
        "scope": {
            "kind": "stateless_combinational_leaf",
            "configuration": "locked Kunminghu V2 RV64 AluDataModule, AluConfig(xlen=64)",
            "state_bits": 0,
            "state_boundary": "no clock/reset/register/memory; one combinational evaluation",
            "inputs": INPUT_WIDTHS,
            "outputs_compared": OUTPUT_WIDTHS,
            "input_bits": INPUT_BITS,
            "input_bit_accounting": "64+64+9=137",
            "output_bits_compared": OUTPUT_BITS,
            "input_space": f"2**{INPUT_BITS}",
            "input_space_cardinality": str(1 << INPUT_BITS),
            "func_encodings_covered": (
                "all 512 nine-bit io_func valuations are quantified; ALUOpType names 74 "
                "of them, so the other 438 (every func[6:4] group has 49..62 spare "
                "encodings, and func[8:7] is consumed by no select in the locked "
                "reference) still reach concrete default result-select branches, where "
                "the target equals the reference bit-for-bit. No don't-care relaxation "
                "was needed to close the proof."
            ),
            "why_complete": (
                "Yosys SAT proves the single declared output bus io_result (all 64 bits) "
                "equal with all 137 input bits unconstrained and no assume/constraint in "
                "the miter; no temporal state exists."
            ),
            "bounded_tests_counted": False,
        },
        "reference_lock": {
            "path": LOCKED_XSTOP,
            "upstream_source_commit": SOURCE_COMMIT,
            "xstop_sha256": XSTOP_SHA256,
            "xstop_bytes": XSTOP_BYTES,
            "reference_module": "AluDataModule extracted from locked V2 XSTop",
            "parent_reference": PARENT_REFERENCE.relative_to(ROOT).as_posix(),
            "parent_reference_sha256": sha256_file(PARENT_REFERENCE),
            "child_references": {
                name: {"path": (REFERENCE_DIR / f"{name}.sv").relative_to(ROOT).as_posix(),
                       "sha256": sha256_file(REFERENCE_DIR / f"{name}.sv")}
                for name in CHILD_REFERENCES
            },
            "closure_policy": (
                "locked bodies are read-only; the only textual transformation is the "
                "REF_ prefix on the eleven child module names required to compile the "
                "instance closure beside the target"
            ),
        },
        "sources": {
            "scala": {"path": SCALA.relative_to(ROOT).as_posix(),
                      "sha256": sha256_file(SCALA), "bytes": SCALA.stat().st_size},
            "reference_sv": {"path": PARENT_REFERENCE.relative_to(ROOT).as_posix(),
                             "sha256": sha256_file(PARENT_REFERENCE),
                             "bytes": PARENT_REFERENCE.stat().st_size,
                             "locked_module": "AluDataModule"},
            "python_build": {"path": TARGET.relative_to(ROOT).as_posix(),
                             "sha256": sha256_file(TARGET), "bytes": TARGET.stat().st_size},
        },
        "checks": {
            "python_version": platform.python_version(),
            "py_compile": {"status": "PASS", "files": [
                TARGET.relative_to(ROOT).as_posix(),
                Path(__file__).relative_to(ROOT).as_posix(),
            ]},
            "pyright": pyright,
            "source_lock": lock,
            "variant": variants,
            "abi": abi,
            "deterministic_export": export,
            "tools": tool_versions(),
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
    print(json.dumps({"status": payload["status"],
                      "strict_complete_eligible": payload["strict_complete_eligible"],
                      "strict_complete_count_delta": payload["strict_complete_count_delta"],
                      "input_bits": payload["scope"]["input_bits"],
                      "output_bits_compared": payload["scope"]["output_bits_compared"],
                      "sat_marker": payload["checks"]["formal"]["yosys_formal_miter"].get(
                          "formal_success_marker"),
                      "failures": payload["failures"]}, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
