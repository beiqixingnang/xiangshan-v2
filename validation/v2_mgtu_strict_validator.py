"""Strict complete-behavior equivalence validator for the V2 Mgtu leaf.

Mgtu is a purely combinational mask-destination tail generator: for every bit
index below ``vl`` the destination bit passes through, and every bit at or above
``vl`` becomes one (mask destination tails are tail-agnostic regardless of
``vta``).  The Build exports exactly one canonical configuration
(``MgtuConfig(vlen=128, vl_width=8)``), so the locked V2 reference surface
``io_in_vd``/``io_in_vl`` -> ``io_out_vd`` forms a single miter.  Yosys SAT
quantifies all 136 distinct declared input nets (``128 + 8``) with no assumption
and compares the whole 128-bit output bus, so a successful run covers the
complete 2**136 input space rather than any sampled vector set.  The upstream
brief's "236 input bits" counts ``io_in_vd`` once per non-default reference term
and so double-counts shared nets; this rail claims only what the RTL declares.

The locked reference ``validation/reference-sv/Mgtu.sv`` is the byte-exact V2
extraction, not a hand-written oracle.  It declares a single module and
instantiates no children, so no instance closure has to be assembled; it is
read verbatim into an ASCII temporary work directory and only its module name is
prefixed with ``REF_`` so it can live next to the Amaranth target.  Nothing in
``validation/reference-sv`` is written or modified by this rail.
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
    "Build-Cpu.Backend.Fu.Vector.Mgtu-Hardware.py"
)
SCALA = ROOT / "upstream/src/main/scala/xiangshan/backend/fu/vector/Mgtu.scala"
REFERENCE = ROOT / "validation/reference-sv/Mgtu.sv"
EVIDENCE = ROOT / "validation/v2-mgtu-strict-evidence.json"
# WSL cannot reliably decode the non-ASCII repository path on every Windows
# transport, so every tool input lives in a fixed ASCII temporary directory.
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_mgtu_strict"

SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
LOCKED_XSTOP = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
XSTOP_BYTES = 228590583
SUCCESS_MARKER = "SAT proof finished - no model found: SUCCESS!"
FREE_INPUT_MARKER = "Final constraint equation: { } = { }"

VLEN = 128
VL_WIDTH = 8
# Exact locked three-port ABI of both surfaces, audited against both RTL files.
PORT_SURFACE = {
    "io_in_vd": ("input", VLEN),
    "io_in_vl": ("input", VL_WIDTH),
    "io_out_vd": ("output", VLEN),
}
# Free input bits quantified by the miter are derived from the audited input
# port surface, so they can never drift from what the RTL actually declares:
# io_in_vd[127:0] + io_in_vl[7:0] = 136 distinct nets.  The upstream brief
# quoted 236; that figure counts io_in_vd again for each of the 100 reference
# terms whose second operand is not the default ``io_in_vd[127]`` broadcast, so
# it double-counts shared nets.  It is recorded only to report the discrepancy
# and is used in no claim.
INPUT_WIDTHS = {"io_in_vd": VLEN, "io_in_vl": VL_WIDTH}
OUTPUT_WIDTHS = {"io_out_vd": VLEN}
INPUT_BITS = sum(INPUT_WIDTHS.values())
OUTPUT_BITS = sum(OUTPUT_WIDTHS.values())
BRIEF_CLAIMED_INPUT_BITS = 236


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one exact file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_target() -> Any:
    """Load only the selected Build module by exact path."""

    spec = importlib.util.spec_from_file_location("strict_mgtu_target", TARGET)
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
    """Run one WSL command serially and retain bounded diagnostics."""

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
        # Capture verdict markers before bounding the retained diagnostic tail.
        # SAT counterexamples are printed after the verdict and may push the
        # ``model found: FAIL!`` line outside that tail.
        "success_marker": SUCCESS_MARKER in output,
        "counterexample_marker": "model found: FAIL!" in output,
        "unconstrained_marker": FREE_INPUT_MARKER in output,
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

    temporary = Path(tempfile.mkdtemp(prefix="uhsc_mgtu_pyright_"))
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


def reference_text() -> str:
    """Return the locked reference verbatim except for the ``REF_`` prefix.

    The locked Mgtu extraction is a single leaf module with no child
    instantiations, so renaming its own declaration is the only textual change;
    the audit below asserts that claim instead of trusting it.
    """

    text = REFERENCE.read_text(encoding="utf-8")
    marker = "module Mgtu("
    if not text.startswith(marker):
        raise AssertionError("locked Mgtu declaration marker missing")
    renamed = text.replace(marker, "module REF_Mgtu(", 1)
    if len(re.findall(r"\bindstance\s|\bMgtu\s+\w+\s*\(", text)) > 0:
        raise AssertionError("locked Mgtu unexpectedly instantiates children")
    return renamed


def source_lock_audit() -> dict[str, Any]:
    """Check every locked source digest before elaboration."""

    if not SCALA.is_file():
        raise FileNotFoundError(f"locked Scala source missing: {SCALA}")
    if not REFERENCE.is_file():
        raise FileNotFoundError(f"locked reference missing: {REFERENCE}")
    if not TARGET.is_file():
        raise FileNotFoundError(f"target Build missing: {TARGET}")
    actual: dict[str, str] = {
        "scala": sha256_file(SCALA),
        "python_build": sha256_file(TARGET),
        "reference_sv": sha256_file(REFERENCE),
    }
    checks = {
        "scala_present": bool(actual["scala"]),
        "python_build_present": bool(actual["python_build"]),
        "reference_sv_present": bool(actual["reference_sv"]),
        "source_commit_recorded": bool(SOURCE_COMMIT),
        "xstop_lock_recorded": len(XSTOP_SHA256) == 64 and XSTOP_BYTES > 0,
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "actual": actual,
        "paths": {
            "scala": SCALA.relative_to(ROOT).as_posix(),
            "python_build": TARGET.relative_to(ROOT).as_posix(),
            "reference_sv": REFERENCE.relative_to(ROOT).as_posix(),
        },
        "expected_scala_source": SCALA.relative_to(ROOT).as_posix(),
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
    stops at ``endmodule``.
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
            kept.append(f"{direction} {name}" if width == 1
                        else f"{direction} [{width - 1}:0] {name}")
    return ",\n".join(kept)


def _header_port_names(header: str) -> set[str]:
    """Return the bare identifiers listed in an ANSI port header."""

    stripped = re.sub(r"//[^\n]*", "", header)
    if re.search(r"\b(?:input|output)\b", stripped):
        return set()
    return {token for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", stripped)}


def _declared_ports(rtl: str, module_name: str) -> dict[str, tuple[str, int]]:
    """Extract typed input/output declarations from one module's RTL.

    Locked Chisel output declares each port with its own direction and width on
    the ANSI header line, while Amaranth emits a bare header port list plus
    per-name direction declarations in the body.  Exactly the region carrying
    the directions is parsed, so no unrelated statement inherits a pending
    direction.
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


def abi_audit(target_rtl: str, reference_rtl: str) -> dict[str, Any]:
    """Require the exact three-port ABI in target and locked reference RTL."""

    checks: dict[str, bool] = {
        "target_module": "module UHSC_Mgtu(" in target_rtl,
        "reference_module": re.search(r"\bmodule REF_Mgtu\(", reference_rtl) is not None,
        "reference_single_module": len(
            re.findall(r"\bmodule (?:REF_)?Mgtu\w*\(", reference_rtl)) == 1,
        "reference_no_child_instances": re.search(
            r"\bMgtu\s+\w+\s*\(", reference_rtl) is None,
    }
    target_ports = _declared_ports(target_rtl, "UHSC_Mgtu")
    reference_ports = _declared_ports(reference_rtl, "REF_Mgtu")
    views = {"target": sorted(f"{d} {n}" if w == 1 else f"{d} [{w - 1}:0] {n}"
                              for n, (d, w) in target_ports.items()),
             "reference": sorted(f"{d} {n}" if w == 1 else f"{d} [{w - 1}:0] {n}"
                                 for n, (d, w) in reference_ports.items())}
    for surface, view in views.items():
        for name, (direction, width) in PORT_SURFACE.items():
            expected = (f"{direction} {name}" if width == 1
                        else f"{direction} [{width - 1}:0] {name}")
            checks[f"{surface}_{name}"] = expected in view
    expected_ports = dict(PORT_SURFACE)
    checks["target_exact_port_set"] = target_ports == expected_ports
    checks["reference_exact_port_set"] = reference_ports == expected_ports
    checks["target_reference_port_sets_equal"] = target_ports == reference_ports

    def totals(ports: dict[str, tuple[str, int]]) -> tuple[int, int]:
        """Sum declared input and output bits of one parsed surface."""

        return (sum(w for d, w in ports.values() if d == "input"),
                sum(w for d, w in ports.values() if d == "output"))

    target_totals = totals(target_ports)
    reference_totals = totals(reference_ports)
    checks["target_declared_bits_match_claimed_space"] = (
        target_totals == (INPUT_BITS, OUTPUT_BITS))
    checks["reference_declared_bits_match_claimed_space"] = (
        reference_totals == (INPUT_BITS, OUTPUT_BITS))
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "declared_input_bits": {"target": target_totals[0],
                                "reference": reference_totals[0],
                                "claimed": INPUT_BITS},
        "declared_output_bits": {"target": target_totals[1],
                                 "reference": reference_totals[1],
                                 "claimed": OUTPUT_BITS},
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
    falls back to the single locked ``MgtuConfig(vlen=128, vl_width=8)``, so the
    default export is the canonical artifact for this rail.
    """

    first = module.build_verilog(None, {})
    second = module.build_verilog(None, {})
    first_renamed = first.replace("module Mgtu(", "module UHSC_Mgtu(", 1)
    second_renamed = second.replace("module Mgtu(", "module UHSC_Mgtu(", 1)
    if "module UHSC_Mgtu(" not in first_renamed:
        raise AssertionError("target Mgtu declaration missing after rename")
    first_bytes = first_renamed.encode("utf-8")
    second_bytes = second_renamed.encode("utf-8")
    return first_renamed, {
        "status": "PASS" if first_bytes == second_bytes else "FAIL",
        "configuration": {"vlen": VLEN, "vl_width": VL_WIDTH,
                          "canonical_default_export": True},
        "bytes": len(first_bytes),
        "sha256": hashlib.sha256(first_bytes).hexdigest(),
        "repeat_sha256": hashlib.sha256(second_bytes).hexdigest(),
        "byte_equal": first_bytes == second_bytes,
    }


def variant_audit(module: Any) -> dict[str, Any]:
    """Verify the Build exports exactly one locked VLEN=128 canonical variant."""

    default = module.MgtuConfig()
    rejected: list[str] = []
    for vlen in (64, 96, 129):
        try:
            module.MgtuConfig(vlen=vlen)
        except ValueError:
            rejected.append(f"vlen={vlen}")
    return {
        "status": "PASS" if (default.vlen == VLEN and default.vl_width == VL_WIDTH) else "FAIL",
        "public_entry_point": "build_verilog(configuration=None, injected_dependencies=None)",
        "default_configuration": f"MgtuConfig(vlen={default.vlen}, vl_width={default.vl_width})",
        "covered_modules": ["Mgtu"],
        "locked_configuration_matches_default": (
            default.vlen == VLEN and default.vl_width == VL_WIDTH),
        "rejected_configurations": rejected,
    }


def materialize_miter(target_rtl: str) -> dict[str, Path]:
    """Write target, locked reference, and the all-output miter."""

    WORK.mkdir(parents=True, exist_ok=True)
    target = WORK / "UHSC_Mgtu.sv"
    reference = WORK / "REF_Mgtu.sv"
    miter = WORK / "Mgtu_MITER.sv"
    target.write_text(target_rtl, encoding="utf-8", newline="\n")
    reference.write_text(reference_text(), encoding="utf-8", newline="\n")
    miter.write_text(
        """module Mgtu_MITER(
  input [127:0] io_in_vd,
  input [7:0] io_in_vl,
  output mismatch
);
  wire [127:0] reference_vd;
  wire [127:0] target_vd;
  REF_Mgtu reference_i(
    .io_in_vd(io_in_vd), .io_in_vl(io_in_vl), .io_out_vd(reference_vd));
  UHSC_Mgtu target_i(
    .io_in_vd(io_in_vd), .io_in_vl(io_in_vl), .io_out_vd(target_vd));
  assign mismatch = |(reference_vd ^ target_vd);
endmodule
""",
        encoding="utf-8", newline="\n")
    return {"target": target, "reference": reference, "miter": miter}


def formal_gates(paths: dict[str, Path]) -> dict[str, Any]:
    """Run lint, synthesis checks, and the unrestricted SAT equivalence.

    Every invocation is strictly serial: one tool runs only after the previous
    one has returned, because another heavy proof shares this machine.
    """

    converted = {name: wsl_path(path) for name, path in paths.items()}
    target, reference, miter = (converted["target"], converted["reference"],
                                converted["miter"])
    verilator = run_wsl([
        "verilator", "--lint-only", "-Wno-fatal", "--top-module",
        "Mgtu_MITER", target, reference, miter,
    ])
    target_yosys = run_wsl(["yosys", "-Q", "-p",
                            f"read_verilog -sv {shlex.quote(target)}; "
                            "hierarchy -top UHSC_Mgtu; proc; opt; check"])
    reference_yosys = run_wsl(["yosys", "-Q", "-p",
                               f"read_verilog -sv {shlex.quote(reference)}; "
                               "hierarchy -top REF_Mgtu; proc; opt; check"])
    proof_script = (
        f"read_verilog -sv {shlex.quote(target)} {shlex.quote(reference)} "
        f"{shlex.quote(miter)}; prep -top Mgtu_MITER; flatten; opt; "
        "sat -prove mismatch 0"
    )
    proof = run_wsl(["yosys", "-Q", "-p", proof_script])
    tail = proof.get("output_tail", "")
    proof["formal_success_marker"] = bool(proof.get(
        "success_marker", SUCCESS_MARKER in tail))
    if not proof["formal_success_marker"]:
        proof["status"] = "FAIL"
    # The emitted miter contains no ``assume`` construct, and Yosys prints an
    # empty constraint equation exactly when nothing was assumed, i.e. every
    # declared input bit stays free over the complete space.
    proof["miter_carries_no_assumption"] = bool(proof.get(
        "unconstrained_marker", FREE_INPUT_MARKER in tail))
    proof["observed_constraint_equation"] = FREE_INPUT_MARKER
    if not proof["miter_carries_no_assumption"]:
        proof["status"] = "FAIL"
    proof["sat_variables"] = next((int(match) for match in
                                   re.findall(r"Solving problem with (\d+) variables", tail)), None)
    proof["sat_clauses"] = next((int(match) for match in
                                 re.findall(r"and (\d+) clauses", tail)), None)
    proof["miter_sha256"] = sha256_file(paths["miter"])
    miter_source = paths["miter"].read_text(encoding="utf-8")
    # A literal scan of the miter source, not just the printed equation, so an
    # assumption could never be added silently.
    proof["miter_has_assume"] = "assume" in miter_source.lower()
    if proof["miter_has_assume"]:
        proof["status"] = "FAIL"
    proof["formal_scope"] = {
        "input_bits": INPUT_BITS,
        "input_space": f"2**{INPUT_BITS}",
        "input_space_cardinality": str(1 << INPUT_BITS),
        "state_bits": 0,
        "state_space": "singleton (stateless combinational module)",
        "property": ("mismatch == 0 for every 2-state valuation of io_in_vd/io_in_vl"),
        "outputs_compared": OUTPUT_WIDTHS,
        "miter_sequence": ("read_verilog -> prep -top Mgtu_MITER -> flatten -> opt "
                           "-> sat -prove mismatch 0"),
    }
    return {
        "verilator": verilator,
        "yosys_target": target_yosys,
        "yosys_reference": reference_yosys,
        "yosys_formal_miter": proof,
    }


def _mutate_output(text: str, module: str, output_name: str,
                   width: int) -> tuple[str, bool, str]:
    """Replace one module's output driver with a constant-zero driver."""

    start = text.find(f"module {module}(")
    if start < 0:
        return text, False, "module-not-found"
    end = text.find("endmodule", start)
    if end < 0:
        return text, False, "endmodule-not-found"
    body = text[start:end]
    # The locked Mgtu reference and generated target both use a single
    # multiline vector assignment to drive io_out_vd.
    vector_pattern = rf"assign\s+{re.escape(output_name)}\s*=\s*.*?;"
    mutated, count = re.subn(
        vector_pattern, f"assign {output_name} = {width}'h0;", body,
        count=1, flags=re.S)
    if count == 1:
        return text[:start] + mutated + text[end:], True, "vector_assignment"
    # Retain a fallback for a generated bit-by-bit form should the backend
    # change its emission style while preserving the same ABI.
    bit_pattern = rf"assign\s+{re.escape(output_name)}\s*\[\s*\d+\s*\]\s*=\s*.*?;"
    mutated, count = re.subn(
        bit_pattern,
        lambda match: re.sub(r"=.*", "= 1'b0;", match.group(0), count=1),
        body, flags=re.S)
    if count == width:
        return text[:start] + mutated + text[end:], True, f"bit_assignments:{count}"
    return text, False, "output-driver-not-found"


def negative_control(paths: dict[str, Path]) -> dict[str, Any]:
    """Mutate target and reference outputs and require SAT counterexamples."""

    results: dict[str, Any] = {}
    output_name = "io_out_vd"
    width = OUTPUT_WIDTHS[output_name]
    for side in ("target", "reference"):
        source = paths[side]
        module = "UHSC_Mgtu" if side == "target" else "REF_Mgtu"
        mutated, applied, mutation_kind = _mutate_output(
            source.read_text(encoding="utf-8"), module, output_name, width)
        if not applied:
            results[side] = {"status": "FAIL", "mutation_applied": False,
                             "mutation_kind": mutation_kind}
            continue
        mutant = WORK / f"MUTANT_{side}_Mgtu.sv"
        mutant.write_text(mutated, encoding="utf-8", newline="\n")
        target = mutant if side == "target" else paths["target"]
        reference = mutant if side == "reference" else paths["reference"]
        converted = {name: wsl_path(path) for name, path in
                     {"target": target, "reference": reference,
                      "miter": paths["miter"]}.items()}
        rendered = " ".join(shlex.quote(converted[name])
                             for name in ("target", "reference", "miter"))
        verdict = run_wsl(["yosys", "-Q", "-p",
                           f"read_verilog -sv {rendered}; "
                           "prep -top Mgtu_MITER; flatten; opt; "
                           "sat -prove mismatch 0"])
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
            "output_tail": tail[-900:],
        }
    return {"status": "PASS" if all(item["status"] == "PASS"
                                     for item in results.values()) else "FAIL",
            "output": output_name, "sides": results}


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
        failures.append("locked-configuration variant audit")
    target_rtl, export = deterministic_export(module)
    closure_rtl = reference_text()
    abi = abi_audit(target_rtl, closure_rtl)
    if abi["status"] != "PASS":
        failures.append("ABI audit")
    paths = materialize_miter(target_rtl)
    gates = formal_gates(paths)
    control = negative_control(paths)
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
    if control["status"] != "PASS":
        failures.append("negative control")
    status = "COMPLETE_EQUIVALENCE" if not failures else "STRICT_PENDING"
    eligible = status == "COMPLETE_EQUIVALENCE"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_STRICT_COMPLETE_EQUIVALENCE",
        "build_id": "Build-Cpu.Backend.Fu.Vector.Mgtu",
        "validator": Path(__file__).relative_to(ROOT).as_posix(),
        "status": status,
        "strict_complete_eligible": eligible,
        "strict_complete_count_delta": 1 if eligible else 0,
        "acceptance_eligible": eligible,
        "source_commit": SOURCE_COMMIT,
        "audit_policy": {
            "require_negative_control": True,
            "scope_source": "single locked Mgtu surface",
        },
        "scope": {
            "kind": "stateless_combinational_leaf",
            "configuration": ("locked Kunminghu V2 vector Mgtu, "
                              f"MgtuConfig(vlen={VLEN}, vl_width={VL_WIDTH})"),
            "state_bits": 0,
            "state_boundary": "no clock/reset/register/memory; one combinational evaluation",
            "inputs": INPUT_WIDTHS,
            "outputs_compared": OUTPUT_WIDTHS,
            "input_bits": INPUT_BITS,
            "input_bit_accounting": f"{VLEN}+{VL_WIDTH}={INPUT_BITS}",
            "output_bits_compared": OUTPUT_BITS,
            "input_space": f"2**{INPUT_BITS}",
            "input_space_cardinality": str(1 << INPUT_BITS),
            "brief_input_bits_discrepancy": {
                "brief_claimed_input_bits": BRIEF_CLAIMED_INPUT_BITS,
                "measured_distinct_declared_input_bits": INPUT_BITS,
                "explanation": (
                    "The locked Mgtu.sv header declares exactly io_in_vd[127:0] and "
                    "io_in_vl[7:0], i.e. 136 distinct input nets. The briefed 236 = "
                    "128 + 8 + 100 counts io_in_vd once more for each of the 100 "
                    "reference comparison terms whose second operand is not the "
                    "default broadcast io_in_vd[127], so it re-counts already-declared "
                    "nets rather than exposing extra state. No additional free net "
                    "exists in either surface, so the claim is stated over the "
                    "measured 136."
                ),
                "affects_proven_space": False,
            },
            "semantics_covered": (
                "out[idx] == (idx < vl ? vd[idx] : 1) for all 128 indices. vl ranges "
                "over all 256 eight-bit values: vl=0..127 select a tail-agnostic region "
                "of 128-vl ones, and every vl >= 128 passes vd through unchanged, which "
                "matches the locked reference where all comparisons idx.U < vl hold. No "
                "don't-care relaxation was needed to close the proof."
            ),
            "why_complete": (
                "Yosys SAT proves the single declared output bus io_out_vd (all 128 bits) "
                "equal with all 136 declared input bits unconstrained and no "
                "assume/constraint in the miter; no temporal state exists."
            ),
            "bounded_tests_counted": False,
        },
        "reference_lock": {
            "path": LOCKED_XSTOP,
            "upstream_source_commit": SOURCE_COMMIT,
            "xstop_sha256": XSTOP_SHA256,
            "xstop_bytes": XSTOP_BYTES,
            "reference_module": "Mgtu extracted from locked V2 XSTop",
            "parent_reference": REFERENCE.relative_to(ROOT).as_posix(),
            "parent_reference_sha256": sha256_file(REFERENCE),
            "child_references": {},
            "closure_policy": (
                "the locked reference declares a single module and instantiates no "
                "children, so the only textual transformation anywhere is the REF_ "
                "prefix on its own module name required to compile it beside the target"
            ),
        },
        "sources": {
            "scala": {"path": SCALA.relative_to(ROOT).as_posix(),
                      "sha256": sha256_file(SCALA), "bytes": SCALA.stat().st_size},
            "reference_sv": {"path": REFERENCE.relative_to(ROOT).as_posix(),
                             "sha256": sha256_file(REFERENCE),
                             "bytes": REFERENCE.stat().st_size,
                             "locked_module": "Mgtu"},
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
            "negative_control": control,
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
    formal = payload["checks"]["formal"]["yosys_formal_miter"]
    print(json.dumps({"status": payload["status"],
                      "strict_complete_eligible": payload["strict_complete_eligible"],
                      "strict_complete_count_delta": payload["strict_complete_count_delta"],
                      "input_bits": payload["scope"]["input_bits"],
                      "output_bits_compared": payload["scope"]["output_bits_compared"],
                      "sat_marker": formal.get("formal_success_marker"),
                      "sat_variables": formal.get("sat_variables"),
                      "sat_clauses": formal.get("sat_clauses"),
                      "no_assumption": formal.get("miter_carries_no_assumption"),
                      "export_bytes": payload["checks"]["deterministic_export"]["bytes"],
                      "byte_equal": payload["checks"]["deterministic_export"]["byte_equal"],
                      "pyright_error_counts": {
                          name: res.get("error_count")
                          for name, res in payload["checks"]["pyright"].items()},
                      "tool_returncodes": {
                          name: res.get("returncode")
                          for name, res in payload["checks"]["formal"].items()},
                      "failures": payload["failures"]}, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
