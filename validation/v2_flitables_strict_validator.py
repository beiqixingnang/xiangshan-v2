"""Complete Build-level equivalence validator for all V2 FLI table variants.

The Build publicly supplies FliHTable, FliSTable, and FliDTable.  This
validator proves each distinct 5-bit-to-16-bit decoder against its locked V2
SystemVerilog module.  A single Build-level COMPLETE_EQUIVALENCE result is
allowed only when all three unrestricted SAT miters succeed.
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
    "Build-Cpu.Backend.Fu.Fpu.FliTable-Hardware.py"
)
SCALA = ROOT / "upstream/src/main/scala/xiangshan/backend/fu/fpu/FliTable.scala"
REFERENCE = ROOT / "validation/reference-closures/FliTables-v2.sv"
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_flitables_strict"
EVIDENCE = ROOT / "validation/v2-flitables-strict-evidence.json"

VARIANTS = ("FliHTable", "FliSTable", "FliDTable")
INPUT_WIDTHS = {"src": 5}
OUTPUT_WIDTHS = {"out": 16}
INPUT_BITS = 5
OUTPUT_BITS = 16
PORT_SURFACE = {"src": ("input", 5), "out": ("output", 16)}
BUILD_ID = "Build-Cpu.Backend.Fu.Fpu.FliTable"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
LOCKED_XSTOP = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
XSTOP_BYTES = 228590583
EXPECTED_SCALA_SHA256 = "3614c54ac9f61c4c97a2d1e2ac767509a669fcc8ae85de94f5c3a447ce1fcfda"
EXPECTED_REFERENCE_SHA256 = "0f9660f6a14a15436fce623a9bfd91fb8c9980880046bf19ef236315c155d0dc"
EXPECTED_TARGET_SHA256 = "383a9880a8e7b4cce8ec118e8f0fa3634128b4b1661aa39f001797e035166ebf"
EXPECTED_MODULE_SHA256 = {
    "FliHTable": "1d950a48fe8c4b79844aa3b51ca6bc3ac21fbd46161ff0562f17b9acef864988",
    "FliSTable": "6cf9a3923d45cf5bc5a8d76b754f88b5fca6b9e3ff084d96aa0be9619b6780c6",
    "FliDTable": "5f4b161fa370fcac30ea8eb6c61b1843f63546592c028590f682ea55cacf7682",
}
SUCCESS_MARKER = "SAT proof finished - no model found: SUCCESS!"
FREE_INPUT_MARKER = "Final constraint equation: { } = { }"
TARGET_RELATIVE = TARGET.relative_to(ROOT).as_posix()
REFERENCE_RELATIVE = REFERENCE.relative_to(ROOT).as_posix()
SCALA_RELATIVE = SCALA.relative_to(ROOT).as_posix()
VALIDATOR_RELATIVE = Path(__file__).relative_to(ROOT).as_posix()


# Hash exact source and reference bytes for durable evidence.
def sha256_file(path: Path) -> str:
    """Return a SHA-256 digest for an exact file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# Hash exact module slices in the extracted closure, preserving lock identity.
def reference_module_hashes() -> dict[str, Any]:
    """Return byte/hash records for each locked FLI module."""

    data = REFERENCE.read_bytes()
    records: dict[str, Any] = {}
    for name in VARIANTS:
        marker = f"module {name}(".encode("ascii")
        start = data.find(marker)
        if start < 0:
            raise AssertionError(f"missing locked module {name}")
        end = data.find(b"endmodule", start)
        if end < 0:
            raise AssertionError(f"missing endmodule for {name}")
        payload = data[start:end + len(b"endmodule")]
        records[name] = {"bytes": len(payload),
                         "sha256": hashlib.sha256(payload).hexdigest()}
    return records


# Load the precise Build without importing sibling candidates.
def load_target() -> Any:
    """Load the FLI table Build module."""

    spec = importlib.util.spec_from_file_location("strict_flitables_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load target: {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Convert one Windows path to a WSL absolute path.
def wsl_path(path: Path) -> str:
    """Return WSL's absolute spelling for a Windows path."""

    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                            capture_output=True, check=True)
    return result.stdout.decode("utf-8", "replace").strip()


# Run a WSL command with stable, bounded diagnostics.
def run_wsl(command: list[str]) -> dict[str, Any]:
    """Run an exact WSL command and collect its result."""

    rendered = " ".join(shlex.quote(item) for item in command)
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered],
                            capture_output=True, check=False)
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {"command": command, "returncode": result.returncode,
            "status": "PASS" if result.returncode == 0 else "FAIL",
            # Compute verdict markers before truncating diagnostics.  A SAT
            # model is printed after the verdict and can exceed the tail.
            "success_marker": SUCCESS_MARKER in output,
            "counterexample_marker": "model found: FAIL!" in output,
            "unconstrained_marker": FREE_INPUT_MARKER in output,
            "output_tail": output[-3000:],
            "output_sha256": hashlib.sha256(output.encode()).hexdigest()}


# Record tool versions from the exact proof environment.
def tool_versions() -> dict[str, Any]:
    """Collect Verilator and Yosys version records."""

    return {"verilator": run_wsl(["verilator", "--version"]),
            "yosys": run_wsl(["yosys", "--version"])}


# Run Pyright on a copy outside dot-directory auto-exclusion.
def pyright_check(source: Path) -> dict[str, Any]:
    """Run Pyright and return its summary."""

    temporary = Path(tempfile.mkdtemp(prefix="uhsc_flitables_pyright_"))
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
    """Return one module header/body without crossing its endmodule."""

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
    """Split declarations on top-level commas."""

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


def declared_ports(rtl: str, module_name: str) -> dict[str, tuple[str, int]]:
    """Parse input/output direction and width for one target/reference module."""

    header, body = _module_region(rtl, module_name)
    clean_header = re.sub(r"//[^\n]*", "", header)
    names = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", clean_header))
    result: dict[str, tuple[str, int]] = {}
    pending: tuple[str, int] | None = None

    def consume(item: str) -> None:
        nonlocal pending
        entry = " ".join(re.sub(r"//[^\n]*", "", item).split()).rstrip(";")
        if not entry:
            return
        match = re.match(
            r"^(input|output)\b(?:\s*\[(\d+):0\])?\s*"
            r"([A-Za-z_][A-Za-z0-9_]*)?$", entry)
        if match:
            direction, msb, name = match.groups()
            pending = (direction, int(msb) + 1 if msb is not None else 1)
            if name:
                result[name] = pending
            return
        if pending is not None and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", entry):
            result[entry] = pending
            return
        pending = None

    if re.search(r"\b(?:input|output)\b", clean_header):
        for item in _split_items(clean_header):
            consume(item)
    else:
        for line in body.splitlines():
            code = re.sub(r"//[^\n]*", "", line).strip()
            match = re.match(
                r"^(input|output)\b(?:\s*\[(\d+):0\])?\s*"
                r"([A-Za-z_][A-Za-z0-9_]*)?;?$", code)
            if match and match.group(3) in names:
                consume(code)
    return result


def source_lock_audit() -> dict[str, Any]:
    """Hash and provenance-check Scala, closure, and Build inputs."""

    paths = {"scala": SCALA, "reference_sv": REFERENCE, "python_build": TARGET}
    missing = [name for name, path in paths.items() if not path.is_file()]
    actual = {name: sha256_file(path) for name, path in paths.items() if path.is_file()}
    modules_ok = False
    if REFERENCE.is_file():
        text = REFERENCE.read_text(encoding="utf-8")
        modules_ok = all(f"module {name}(" in text for name in VARIANTS)
    module_hashes = reference_module_hashes() if not missing else {}
    checks = {
        "all_sources_present": not missing,
        "scala_hash_locked": actual.get("scala") == EXPECTED_SCALA_SHA256,
        "reference_hash_locked": actual.get("reference_sv") == EXPECTED_REFERENCE_SHA256,
        "python_build_hash_recorded": actual.get("python_build") == EXPECTED_TARGET_SHA256,
        "reference_modules_present": modules_ok,
        "variant_reference_hashes_locked": all(
            module_hashes.get(name, {}).get("sha256") == EXPECTED_MODULE_SHA256[name]
            for name in VARIANTS),
        "source_commit_recorded": bool(SOURCE_COMMIT),
        "xstop_lock_recorded": len(XSTOP_SHA256) == 64 and XSTOP_BYTES > 0,
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks, "missing": missing, "actual": actual,
            "expected": {"scala": EXPECTED_SCALA_SHA256,
                          "reference_sv": EXPECTED_REFERENCE_SHA256,
                          "python_build": EXPECTED_TARGET_SHA256},
            "source_commit": SOURCE_COMMIT,
            "xstop": {"path": LOCKED_XSTOP, "sha256": XSTOP_SHA256,
                      "bytes": XSTOP_BYTES},
            "module_hashes": module_hashes}


def identity_audit() -> dict[str, Any]:
    """Ensure Build ID and provenance paths cannot drift."""

    checks = {
        "build_id_exact": BUILD_ID == "Build-Cpu.Backend.Fu.Fpu.FliTable",
        "validator_path_exact": VALIDATOR_RELATIVE == "validation/v2_flitables_strict_validator.py",
        "target_path_exact": TARGET_RELATIVE == (
            "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
            "Build-Cpu.Backend.Fu.Fpu.FliTable-Hardware.py"),
        "reference_path_exact": REFERENCE_RELATIVE == "validation/reference-closures/FliTables-v2.sv",
        "scala_path_exact": SCALA_RELATIVE == "upstream/src/main/scala/xiangshan/backend/fu/fpu/FliTable.scala",
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks, "build_id": BUILD_ID,
            "validator": VALIDATOR_RELATIVE, "target": TARGET_RELATIVE,
            "reference": REFERENCE_RELATIVE, "scala": SCALA_RELATIVE}


def abi_audit(rendered: dict[str, str], reference_text: str,
              miter_text: str) -> dict[str, Any]:
    """Require exact src/out ABI for all variants and aggregate wiring."""

    rows: dict[str, Any] = {}
    expected = dict(PORT_SURFACE)
    all_ok = True
    for name in VARIANTS:
        target_ports = declared_ports(rendered[name], name)
        ref_ports = declared_ports(reference_text, f"REF_{name}")
        suffix = {"FliHTable": "h", "FliSTable": "s", "FliDTable": "d"}[name]
        checks = {
            "target_exact_port_set": target_ports == expected,
            "reference_exact_port_set": ref_ports == expected,
            "target_reference_equal": target_ports == ref_ports,
            "aggregate_variant_instance": f"{name} dut_{suffix}" in miter_text,
            "aggregate_reference_instance": f"REF_{name} ref_{suffix}" in miter_text,
            "aggregate_output_term": f"r{suffix} ^ t{suffix}" in miter_text,
        }
        rows[name] = {"status": "PASS" if all(checks.values()) else "FAIL",
                      "checks": checks,
                      "target_ports": {k: list(v) for k, v in target_ports.items()},
                      "reference_ports": {k: list(v) for k, v in ref_ports.items()}}
        all_ok = all_ok and rows[name]["status"] == "PASS"
    aggregate_checks = {
        "aggregate_variant_count": all(f"{name} dut_" in miter_text for name in VARIANTS),
        "aggregate_all_output_terms": all(token in miter_text
                                            for token in ("rh ^ th", "rs ^ ts", "rd ^ td")),
    }
    status = "PASS" if all_ok and all(aggregate_checks.values()) else "FAIL"
    return {"status": status, "rows": rows, "aggregate_checks": aggregate_checks,
            "expected_ports": {k: list(v) for k, v in expected.items()},
            "variant_count": len(VARIANTS), "output_bits_compared": OUTPUT_BITS}


# Render exactly one public FLI variant from its Build-owned class.
def render_variant(module: Any, name: str) -> str:
    """Return deterministic Verilog for a named public FLI table variant."""

    from amaranth.back import verilog

    table_class = getattr(module, name)
    top = table_class()
    return verilog.convert(top, name=name, ports=[top.src, top.out], emit_src=False)


# Export every public variant twice and require byte-for-byte repeatability.
def deterministic_exports(module: Any) -> tuple[dict[str, str], dict[str, Any]]:
    """Return per-variant RTL and deterministic-export evidence."""

    rendered: dict[str, str] = {}
    evidence: dict[str, Any] = {}
    for name in VARIANTS:
        first = render_variant(module, name)
        second = render_variant(module, name)
        first_bytes = first.encode("utf-8")
        second_bytes = second.encode("utf-8")
        rendered[name] = first
        evidence[name] = {
            "status": "PASS" if first_bytes == second_bytes else "FAIL",
            "bytes": len(first_bytes),
            "sha256": hashlib.sha256(first_bytes).hexdigest(),
            "repeat_sha256": hashlib.sha256(second_bytes).hexdigest(),
            "byte_equal": first_bytes == second_bytes,
        }
    generic_first = module.build_verilog(None, {})
    generic_second = module.build_verilog(None, {})
    evidence["build_verilog_adapter"] = {
        "status": "PASS" if generic_first == generic_second else "FAIL",
        "module": "FliTable",
        "bytes": len(generic_first.encode("utf-8")),
        "sha256": hashlib.sha256(generic_first.encode("utf-8")).hexdigest(),
        "repeat_sha256": hashlib.sha256(generic_second.encode("utf-8")).hexdigest(),
        "byte_equal": generic_first == generic_second,
    }
    return rendered, evidence


# Materialize a one-variant miter while retaining the three-module closure.
def materialize_variant(name: str, target_rtl: str) -> dict[str, Path]:
    """Write target/reference/miter files for one public variant."""

    WORK.mkdir(parents=True, exist_ok=True)
    target = WORK / f"UHSC_{name}.sv"
    reference = WORK / f"REF_{name}.sv"
    miter = WORK / f"{name}_MITER.sv"
    target.write_text(target_rtl, encoding="utf-8", newline="\n")
    source = REFERENCE.read_text(encoding="utf-8")
    source = source.replace(f"module {name}(", f"module REF_{name}(", 1)
    reference.write_text(source, encoding="utf-8", newline="\n")
    miter.write_text(
        f"""module {name}_MITER(input [4:0] src, output mismatch);
  wire [15:0] reference_out;
  wire [15:0] target_out;
  REF_{name} reference_i(.src(src), .out(reference_out));
  {name} target_i(.src(src), .out(target_out));
  assign mismatch = |(reference_out ^ target_out);
endmodule
""",
        encoding="utf-8", newline="\n")
    return {"target": target, "reference": reference, "miter": miter}


# Run tool gates and one full 2**5 SAT miter proof.
def formal_variant(name: str, target_rtl: str) -> dict[str, Any]:
    """Run full-space formal equivalence for one FLI table variant."""

    paths = materialize_variant(name, target_rtl)
    converted = {key: wsl_path(path) for key, path in paths.items()}
    target, reference, miter = (converted["target"], converted["reference"],
                                converted["miter"])
    verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal",
                         target, reference, miter])
    target_yosys = run_wsl(["yosys", "-Q", "-p",
                            f"read_verilog -sv {shlex.quote(target)}; "
                            f"hierarchy -top {name}; proc; opt; check"])
    reference_yosys = run_wsl(["yosys", "-Q", "-p",
                               f"read_verilog -sv {shlex.quote(reference)}; "
                               f"hierarchy -top REF_{name}; proc; opt; check"])
    proof_script = (
        f"read_verilog -sv {shlex.quote(target)} {shlex.quote(reference)} "
        f"{shlex.quote(miter)}; prep -top {name}_MITER; flatten; opt; "
        "sat -prove mismatch 0"
    )
    proof = run_wsl(["yosys", "-Q", "-p", proof_script])
    tail = proof.get("output_tail", "")
    proof["formal_success_marker"] = bool(proof.get(
        "success_marker", SUCCESS_MARKER in tail))
    proof["unconstrained"] = bool(proof.get(
        "unconstrained_marker", FREE_INPUT_MARKER in tail))
    proof["miter_carries_no_assumption"] = proof["unconstrained"]
    if (proof.get("returncode") != 0 or not proof["formal_success_marker"]
            or not proof["unconstrained"]):
        proof["status"] = "FAIL"
    proof["formal_scope"] = {
        "input_bits": INPUT_BITS,
        "input_space": "2**5",
        "input_space_cardinality": "32",
        "state_bits": 0,
        "state_space": "singleton (stateless combinational module)",
        "property": "mismatch == 0 for every 2-state src valuation",
        "no_assumptions": True,
        "outputs_compared": OUTPUT_WIDTHS,
    }
    return {"verilator": verilator, "yosys_target": target_yosys,
            "yosys_reference": reference_yosys, "yosys_formal_miter": proof}


# Build one aggregate miter with independent inputs for all three variants.
def formal_aggregate(rendered: dict[str, str]) -> dict[str, Any]:
    """Prove the complete three-variant Build closure in one SAT problem."""

    WORK.mkdir(parents=True, exist_ok=True)
    target = WORK / "UHSC_FliTables.sv"
    reference = WORK / "REF_FliTables.sv"
    miter = WORK / "FliTables_MITER.sv"
    target.write_text("\n".join(rendered[name] for name in VARIANTS),
                      encoding="utf-8", newline="\n")
    source = REFERENCE.read_text(encoding="utf-8")
    for name in VARIANTS:
        source = source.replace(f"module {name}(",
                                f"module REF_{name}(", 1)
    reference.write_text(source, encoding="utf-8", newline="\n")
    miter.write_text(
        """module FliTables_MITER(
  input [4:0] src_h, input [4:0] src_s, input [4:0] src_d,
  output mismatch
);
  wire [15:0] rh, rs, rd, th, ts, td;
  REF_FliHTable ref_h(.src(src_h), .out(rh));
  REF_FliSTable ref_s(.src(src_s), .out(rs));
  REF_FliDTable ref_d(.src(src_d), .out(rd));
  FliHTable dut_h(.src(src_h), .out(th));
  FliSTable dut_s(.src(src_s), .out(ts));
  FliDTable dut_d(.src(src_d), .out(td));
  assign mismatch = |(rh ^ th) | |(rs ^ ts) | |(rd ^ td);
endmodule
""",
        encoding="utf-8", newline="\n")
    converted = {key: wsl_path(path) for key, path in {
        "target": target, "reference": reference, "miter": miter}.items()}
    target_wsl, reference_wsl, miter_wsl = (converted["target"],
                                            converted["reference"],
                                            converted["miter"])
    verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal",
                         target_wsl, reference_wsl, miter_wsl])
    proof_script = (
        f"read_verilog -sv {shlex.quote(target_wsl)} "
        f"{shlex.quote(reference_wsl)} {shlex.quote(miter_wsl)}; "
        "prep -top FliTables_MITER; flatten; opt; sat -prove mismatch 0"
    )
    proof = run_wsl(["yosys", "-Q", "-p", proof_script])
    tail = proof.get("output_tail", "")
    proof["formal_success_marker"] = bool(proof.get(
        "success_marker", SUCCESS_MARKER in tail))
    proof["unconstrained"] = bool(proof.get(
        "unconstrained_marker", FREE_INPUT_MARKER in tail))
    proof["miter_carries_no_assumption"] = proof["unconstrained"]
    if (proof.get("returncode") != 0 or not proof["formal_success_marker"]
            or not proof["unconstrained"]):
        proof["status"] = "FAIL"
    proof["formal_scope"] = {
        "input_bits": 15,
        "input_space": "2**15",
        "input_space_cardinality": "32768",
        "state_bits": 0,
        "state_space": "singleton (three stateless combinational modules)",
        "property": "OR of H/S/D output mismatches is zero for every valuation",
        "variants": list(VARIANTS),
        "outputs_compared": {name: OUTPUT_WIDTHS for name in VARIANTS},
        "no_assumptions": True,
    }
    proof["aggregate_variant_count"] = len(VARIANTS)
    proof["mitered_variants"] = len(VARIANTS)
    return {"verilator": verilator, "yosys_formal_miter": proof}


def _mutate_output(text: str, module: str) -> tuple[str, bool]:
    """Replace one FLI table output driver with a constant-zero vector."""

    start = text.find(f"module {module}(")
    if start < 0:
        return text, False
    end = text.find("endmodule", start)
    if end < 0:
        return text, False
    body = text[start:end]
    mutated, count = re.subn(
        r"assign\s+out\s*=\s*.*?;", "assign out = 16'h0;",
        body, count=1, flags=re.S)
    if count != 1:
        return text, False
    return text[:start] + mutated + text[end:], True


def negative_control(rendered: dict[str, str]) -> dict[str, Any]:
    """Mutate target and reference sides of one variant and require SAT models."""

    name = VARIANTS[0]
    paths = materialize_variant(name, rendered[name])
    results: dict[str, Any] = {}
    for side in ("target", "reference"):
        module = name if side == "target" else f"REF_{name}"
        source = paths[side].read_text(encoding="utf-8")
        mutated, applied = _mutate_output(source, module)
        if not applied:
            results[side] = {"status": "FAIL", "mutation_applied": False}
            continue
        mutant = WORK / f"MUTANT_{side}_{name}.sv"
        mutant.write_text(mutated, encoding="utf-8", newline="\n")
        selected = {**paths, side: mutant}
        converted = {key: wsl_path(value) for key, value in selected.items()}
        script = (f"read_verilog -sv {shlex.quote(converted['target'])} "
                  f"{shlex.quote(converted['reference'])} {shlex.quote(converted['miter'])}; "
                  f"prep -top {name}_MITER; flatten; opt; sat -prove mismatch 0")
        verdict = run_wsl(["yosys", "-Q", "-p", script])
        tail = verdict.get("output_tail", "")
        success_marker = bool(verdict.get(
            "success_marker", SUCCESS_MARKER in tail))
        counterexample_marker = bool(verdict.get(
            "counterexample_marker", "model found: FAIL!" in tail))
        detected = (verdict.get("returncode") == 0 and not success_marker
                    and counterexample_marker)
        results[side] = {
            "status": "PASS" if detected else "FAIL",
            "mutation_applied": True,
            "mutated_variant": name,
            "mutated_output": "out",
            "counterexample_marker": counterexample_marker,
            "success_marker_still_present": success_marker,
            "output_tail": tail[-1200:],
        }
    return {"status": "PASS" if all(item["status"] == "PASS"
                                     for item in results.values()) else "FAIL",
            "control_variant": name, "sides": results,
            "aggregate_variant_count": len(VARIANTS)}


# Run every variant gate and permit Build-level success only if all pass.
def validate() -> dict[str, Any]:
    """Run the FLI Build's complete three-variant equivalence suite."""

    locks = source_lock_audit()
    identity = identity_audit()
    module = load_target()
    py_compile.compile(str(TARGET), doraise=True)
    py_compile.compile(str(Path(__file__)), doraise=True)
    rendered, exports = deterministic_exports(module)
    variants = {name: formal_variant(name, rendered[name]) for name in VARIANTS}
    aggregate = formal_aggregate(rendered)
    # Build a static ABI/miter audit from the same rendered/reference closure
    # used by the formal gates; no separate oracle is introduced.
    aggregate_paths = {
        "target": WORK / "UHSC_FliTables.sv",
        "reference": WORK / "REF_FliTables.sv",
        "miter": WORK / "FliTables_MITER.sv",
    }
    abi = abi_audit(rendered,
                    aggregate_paths["reference"].read_text(encoding="utf-8"),
                    aggregate_paths["miter"].read_text(encoding="utf-8"))
    control = negative_control(rendered)
    pyright = {"target": pyright_check(TARGET),
               "validator": pyright_check(Path(__file__))}
    failures: list[str] = []
    if locks["status"] != "PASS":
        failures.append("source lock audit")
    if identity["status"] != "PASS":
        failures.append("Build ID/path identity audit")
    if abi["status"] != "PASS":
        failures.append("ABI/miter audit")
    if control["status"] != "PASS":
        failures.append("two-sided negative control")
    for name, result in exports.items():
        if result["status"] != "PASS":
            failures.append(f"deterministic_export:{name}")
    for name, result in pyright.items():
        if result["status"] != "PASS":
            failures.append(f"pyright:{name}")
    for name, gates in variants.items():
        for gate_name, result in gates.items():
            if result["status"] != "PASS":
                failures.append(f"{name}:{gate_name}")
    for gate_name, result in aggregate.items():
        if result["status"] != "PASS":
            failures.append(f"aggregate:{gate_name}")
    status = "COMPLETE_EQUIVALENCE" if not failures else "STRICT_PENDING"
    module_hashes = reference_module_hashes()
    variant_claims = {
        name: {
            "method": "sat_miter",
            "sequential": False,
            "locked_reference": REFERENCE.relative_to(ROOT).as_posix(),
            "locked_sha256": sha256_file(REFERENCE),
            "locked_module_sha256": module_hashes[name]["sha256"],
            "inputs": INPUT_WIDTHS,
            "outputs_compared": OUTPUT_WIDTHS,
            "input_bits": INPUT_BITS,
            "output_bits": sum(OUTPUT_WIDTHS.values()),
            "abi_exact": abi.get("rows", {}).get(name, {}).get("status") == "PASS",
            "deterministic": exports.get(name, {}).get("status") == "PASS",
            "miter_selfcheck": abi.get("rows", {}).get(name, {}).get("status") == "PASS",
            "verdict": variants[name].get("yosys_formal_miter", {}).get("status"),
            "success_marker": variants[name].get("yosys_formal_miter", {}).get(
                "formal_success_marker"),
            "unconstrained_or_cells": variants[name].get(
                "yosys_formal_miter", {}).get("unconstrained"),
        }
        for name in VARIANTS
    }
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
        "audit_policy": {
            "require_negative_control": True,
            "two_sided_negative_control": True,
            "require_unconstrained_sat": True,
            "require_all_variants_and_outputs_compared": True,
            "scope_source": "locked FliTables reference closure",
        },
        "scope": {
            "kind": "stateless_combinational_multi_variant_build",
            "public_variants": list(VARIANTS),
            "variant_count": len(VARIANTS),
            "variants": variant_claims,
            "state_bits": 0,
            "state_boundary": "each table has no clock/reset/register/memory",
            "inputs": {name: {"src": 5} for name in VARIANTS},
            "outputs_compared": {name: {"out": 16} for name in VARIANTS},
            "input_bits": 15,
            "input_space": "2**15",
            "input_space_cardinality": "32768",
            "inputs_per_variant": INPUT_WIDTHS,
            "outputs_compared_per_variant": OUTPUT_WIDTHS,
            "input_bits_per_variant": INPUT_BITS,
            "input_space_per_variant": "2**5",
            "input_space_cardinality_per_variant": "32",
            "aggregate_complete_cases": "3 * 32 = 96",
            "aggregate_variant_count": len(VARIANTS),
            "why_complete": (
                "All three declared public variants have independent Yosys SAT "
                "miters proving all 16 output bits equal for every 5-bit input; "
                "the variants are stateless."
            ),
        },
        "sources": {
            "scala": {"path": SCALA.relative_to(ROOT).as_posix(),
                      "sha256": sha256_file(SCALA), "bytes": SCALA.stat().st_size},
            "reference_sv": {"path": REFERENCE.relative_to(ROOT).as_posix(),
                             "sha256": sha256_file(REFERENCE), "bytes": REFERENCE.stat().st_size,
                             "locked_modules": list(VARIANTS),
                             "module_hashes": reference_module_hashes(),
                             "locked_xstop_sha256": "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d",
                             "locked_xstop_module_lines": {
                                 "FliHTable": [1200613, 1200670],
                                 "FliSTable": [1200672, 1200758],
                                 "FliDTable": [1200760, 1200867],
                             }},
            "python_build": {"path": TARGET.relative_to(ROOT).as_posix(),
                             "sha256": sha256_file(TARGET), "bytes": TARGET.stat().st_size},
        },
        "reference_lock": {
            "path": REFERENCE_RELATIVE,
            "upstream_source_commit": SOURCE_COMMIT,
            "xstop_sha256": XSTOP_SHA256,
            "xstop_bytes": XSTOP_BYTES,
            "scala_path": SCALA_RELATIVE,
            "scala_sha256": locks["actual"].get("scala"),
            "reference_sha256": locks["actual"].get("reference_sv"),
            "module_hashes": reference_module_hashes(),
            "closure_policy": "locked module bodies are copied verbatim and only top names are prefixed REF_ in temporary work files",
        },
        "checks": {"python_version": platform.python_version(),
                    "py_compile": {"status": "PASS", "files": [
                        TARGET.relative_to(ROOT).as_posix(),
                        Path(__file__).relative_to(ROOT).as_posix()]},
                    "pyright": pyright, "source_lock": locks,
                    "identity": identity, "abi": abi,
                    "deterministic_exports": exports, "tools": tool_versions(),
                    "variants": variants, "formal": {**aggregate,
                        "negative_control": control},
                    "negative_control": control},
        "failures": failures,
        "unclosed": [] if not failures else [
            "all three public FLI variants must pass before Build-level promotion"],
        "acceptance_unclosed": [],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    return payload


# Print compact CI status and use a nonzero exit while proof is incomplete.
def main() -> int:
    """Run the Build-level strict FLI validator."""

    payload = validate()
    print(json.dumps({"status": payload["status"],
                      "strict_complete_eligible": payload["strict_complete_eligible"],
                      "failures": payload["failures"]}, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
