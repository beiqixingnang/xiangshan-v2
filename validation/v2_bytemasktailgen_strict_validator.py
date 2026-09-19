"""Complete formal equivalence validator for the V2 ByteMaskTailGen leaf.

The locked XSTop extraction contains ByteMaskTailGen and its exact three
combinational children (MaskExtractor, UIntToContLow0s, UIntToContLow1s).  The
flattened public ABI has 39 input bits and 32 output bits; the miter leaves all
39 bits unconstrained and compares both output buses.  This is a complete
stateless proof, not a bounded differential-vector result.
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
    "Build-Cpu.Backend.Fu.Vector.ByteMaskTailGen-Hardware.py"
)
SCALA = ROOT / (
    "upstream/src/main/scala/xiangshan/backend/fu/vector/"
    "ByteMaskTailGen.scala"
)
REFERENCE = ROOT / "validation/reference-closures/ByteMaskTailGen-v2.sv"
MANIFEST = ROOT / "validation/reference-closures/ByteMaskTailGen-v2.json"
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_bytemasktailgen_strict"
EVIDENCE = ROOT / "validation/v2-bytemasktailgen-strict-evidence.json"

# Locked V2 generation identity.  The closure manifest is produced directly
# from this immutable XSTop.sv and checked again before the formal run.
LOCKED_XSTOP = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
XSTOP_BYTES = 228590583
EXPECTED_MODULES = [
    "ByteMaskTailGen",
    "MaskExtractor",
    "UIntToContLow0s",
    "UIntToContLow1s",
]

# Honest flattened ABI accounting: 8+8+1+1+2+16+3 = 39 bits.
INPUT_WIDTHS = {
    "io_in_begin": 8,
    "io_in_end": 8,
    "io_in_vma": 1,
    "io_in_vta": 1,
    "io_in_vsew": 2,
    "io_in_maskUsed": 16,
    "io_in_vdIdx": 3,
}
OUTPUT_WIDTHS = {"io_out_activeEn": 16, "io_out_agnosticEn": 16}
INPUT_BITS = sum(INPUT_WIDTHS.values())
OUTPUT_BITS = sum(OUTPUT_WIDTHS.values())

# Frozen source/reference identities.  A proof is not countable if any input
# artifact is silently replaced between runs.
EXPECTED_TARGET_SHA256 = "7620de4e059c23e5a3f643f188282ef28613db1468f1b53284cba6946dbbfd43"
EXPECTED_SCALA_SHA256 = "2a6792444632182bff89f907c58fda06fa6e50aa48a8b3454f5c2562cd73e4fe"
EXPECTED_CLOSURE_SHA256 = "9a3de3d2c4bc437648ad502089abbc6b19c5ce3c13b41f35f0a77df583228cd3"
EXPECTED_MANIFEST_SHA256 = "b225e8ce51572da15a93fc86e53e9f463264feb04bee1b3348709fd9eda60501"
EXPECTED_REFERENCE_SHA256 = {
    "ByteMaskTailGen": "83a0ebe835eeec55fb729aec16fb93c5432f50130fb86f3b570d26ba727bc2de",
    "MaskExtractor": "ce0ca7d18915ed4cb27c1766fd8e56c4a19523dfc15bcb4a2add08092092a13a",
    "UIntToContLow0s": "aebda041355c132d9e1b2876dcc0bd719b1cc2efb7199765eb605272258d97ac",
    "UIntToContLow1s": "5db2a1ab3b5234c81d91b19f52caf43d214350a2ad1f6c88e1ef344692914d98",
}
SUCCESS_MARKER = "SAT proof finished - no model found: SUCCESS!"
MODEL_FOUND_MARKER = "SAT proof finished - model found: FAIL!"
FREE_INPUT_MARKER = "Final constraint equation: { } = { }"


def sha256_file(path: Path) -> str:
    """Return SHA-256 of exact file bytes."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_target() -> Any:
    """Load only the selected Build module by exact path."""

    spec = importlib.util.spec_from_file_location("strict_bytemasktailgen_target", TARGET)
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
    """Run one WSL command and retain bounded, hashed diagnostics."""

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
        # Decide formal gates from the complete process output; a bounded tail
        # is diagnostic-only and may omit the decisive SAT line.
        "sat_success_marker": SUCCESS_MARKER in output,
        "sat_counterexample_marker": MODEL_FOUND_MARKER in output,
        "unconstrained_marker": FREE_INPUT_MARKER in output,
        "output_tail": output[-5000:],
        "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
    }


def tool_versions() -> dict[str, Any]:
    """Record versions of the formal back-end tools."""

    return {
        "verilator": run_wsl(["verilator", "--version"]),
        "yosys": run_wsl(["yosys", "--version"]),
    }


def pyright_check(source: Path) -> dict[str, Any]:
    """Run Pyright on an exact visible copy of one source file."""

    temporary = Path(tempfile.mkdtemp(prefix="uhsc_bytemasktailgen_pyright_"))
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


def deterministic_export(module: Any) -> tuple[str, dict[str, Any]]:
    """Generate target RTL twice and require exact byte identity."""

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


def closure_audit() -> dict[str, Any]:
    """Validate the extracted closure against the locked-source manifest."""

    if not REFERENCE.is_file() or not MANIFEST.is_file():
        return {"status": "FAIL", "reason": "closure or manifest missing"}
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {"status": "FAIL", "reason": repr(error)}
    actual_modules = [item.get("name") for item in manifest.get("modules", [])]
    closure_hash = sha256_file(REFERENCE)
    manifest_hash = sha256_file(MANIFEST)
    reference_hashes = {
        name: sha256_file(ROOT / "validation/reference-sv" / f"{name}.sv")
        if (ROOT / "validation/reference-sv" / f"{name}.sv").is_file() else None
        for name in EXPECTED_MODULES
    }
    checks = {
        "target": manifest.get("target") == "ByteMaskTailGen",
        "source_sha256": manifest.get("source_sha256") == XSTOP_SHA256,
        "source": manifest.get("source") == "//wsl$/Debian/home/lishuo/xs-v2-local/build/rtl/XSTop.sv",
        "closure_complete": manifest.get("closure_complete") is True,
        "module_count": manifest.get("module_count") == len(EXPECTED_MODULES),
        "modules": actual_modules == EXPECTED_MODULES,
        "extracted_sha256": manifest.get("extracted_sha256") == closure_hash,
        "manifest_sha256_locked": manifest_hash == EXPECTED_MANIFEST_SHA256,
        "closure_sha256_locked": closure_hash == EXPECTED_CLOSURE_SHA256,
        "variant_reference_hashes_locked": reference_hashes == EXPECTED_REFERENCE_SHA256,
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "manifest_path": MANIFEST.relative_to(ROOT).as_posix(),
        "manifest_sha256": manifest_hash,
        "closure_path": REFERENCE.relative_to(ROOT).as_posix(),
        "closure_sha256": closure_hash,
        "closure_bytes": REFERENCE.stat().st_size,
        "modules": actual_modules,
        "source": manifest.get("source"),
        "source_sha256": manifest.get("source_sha256"),
        "source_bytes": XSTOP_BYTES,
        "reference_hashes": reference_hashes,
    }


def _module_region(rtl: str, module: str) -> tuple[str, str]:
    """Return one module header and body without trusting declaration style."""

    match = re.search(r"module\s+" + re.escape(module) + r"\s*\(", rtl)
    if match is None:
        return "", ""
    open_index = rtl.find("(", match.start())
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
    end = rtl.find("endmodule", close_index)
    return rtl[open_index + 1:close_index], rtl[close_index + 1:end if end >= 0 else len(rtl)]


def declared_ports(rtl: str, module: str) -> dict[str, tuple[str, int]]:
    """Parse grouped ANSI or Amaranth bare-header input/output declarations."""

    header, body = _module_region(rtl, module)
    if not header:
        return {}
    header = re.sub(r"//[^\n]*", "", header)
    items = [item.strip() for item in header.replace("\n", " ").split(",") if item.strip()]
    typed = any(re.match(r"^(input|output)\b", item) for item in items)
    ports: dict[str, tuple[str, int]] = {}
    pending: tuple[str, int] | None = None
    if typed:
        lines = items
    else:
        names = set(re.findall(r"[A-Za-z_]\w*", header))
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        lines = [line for line in lines
                 if re.match(r"^(?:input|output)\b", re.sub(r"//[^\n]*", "", line).strip())
                 or (pending is not None and re.sub(r"//[^\n]*", "", line).strip().rstrip(";").strip() in names)]
    for raw in lines:
        entry = re.sub(r"//[^\n]*", "", raw).strip().rstrip(",;").strip()
        if not entry:
            continue
        match = re.match(r"^(input|output)\b(?:\s*\[(\d+):0\])?\s*(.*)$", entry)
        if match:
            direction, msb, tail = match.groups()
            pending = (direction, int(msb) + 1 if msb is not None else 1)
            if tail:
                for name in (item.strip() for item in tail.split(",")):
                    if re.fullmatch(r"[A-Za-z_]\w*", name):
                        ports[name] = pending
            continue
        if pending is not None and re.fullmatch(r"[A-Za-z_]\w*", entry):
            ports[entry] = pending
    return ports


def abi_audit(target_rtl: str, reference_rtl: str) -> dict[str, Any]:
    """Require exact locked top-level ABI on target and reference surfaces."""

    expected = {**{name: ("input", width) for name, width in INPUT_WIDTHS.items()},
                **{name: ("output", width) for name, width in OUTPUT_WIDTHS.items()}}
    target = declared_ports(target_rtl, "ByteMaskTailGen")
    reference = declared_ports(reference_rtl, "REF_ByteMaskTailGen")
    checks = {
        "target_module": bool(target),
        "reference_module": bool(reference),
        "target_exact_port_set": target == expected,
        "reference_exact_port_set": reference == expected,
        "target_reference_port_sets_equal": target == reference,
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks,
            "target_declared_ports": {k: list(v) for k, v in target.items()},
            "reference_declared_ports": {k: list(v) for k, v in reference.items()},
            "expected_declared_ports": {k: list(v) for k, v in expected.items()},
            "port_count": len(expected), "inputs": INPUT_WIDTHS,
            "outputs": OUTPUT_WIDTHS}


def miter_selfcheck(text: str) -> dict[str, Any]:
    """Ensure every miter net is declared and both output buses are compared."""

    declarations = set()
    for line in text.splitlines():
        match = re.match(r"^\s*(?:input|output|wire)\s+(?:\[[^]]+\]\s*)?(.+?);\s*$", line)
        if match:
            declarations.update(item.strip() for item in match.group(1).split(",")
                                if re.fullmatch(r"[A-Za-z_]\w*", item.strip()))
    connected = set(re.findall(r"\.\w+\(([^()]+)\)", text))
    # Instance connections are the only meaningful net references here; the
    # miter's own output/input declarations are checked separately.
    required = {"io_in_begin", "io_in_end", "io_in_vma", "io_in_vta",
                "io_in_vsew", "io_in_maskUsed", "io_in_vdIdx",
                "ref_active", "ref_agnostic", "dut_active", "dut_agnostic"}
    checks = {
        "declared_connection_nets": all(re.search(rf"\b{re.escape(name)}\b", text)
                                         for name in required) and bool(connected),
        "active_output_compared": "ref_active ^ dut_active" in text,
        "agnostic_output_compared": "ref_agnostic ^ dut_agnostic" in text,
        "no_assume": "assume" not in text.lower(),
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}


def source_lock_audit() -> dict[str, Any]:
    """Check all source, closure and per-module reference hashes."""

    actual = {
        "scala": sha256_file(SCALA), "python_build": sha256_file(TARGET),
        "reference_sv": sha256_file(REFERENCE), "closure_manifest": sha256_file(MANIFEST),
    }
    refs = {name: sha256_file(ROOT / "validation/reference-sv" / f"{name}.sv")
            for name in EXPECTED_MODULES}
    checks = {
        "scala_hash_locked": actual["scala"] == EXPECTED_SCALA_SHA256,
        "python_build_hash_locked": actual["python_build"] == EXPECTED_TARGET_SHA256,
        "reference_hash_locked": actual["reference_sv"] == EXPECTED_CLOSURE_SHA256,
        "closure_manifest_hash_locked": actual["closure_manifest"] == EXPECTED_MANIFEST_SHA256,
        "variant_reference_hashes_locked": refs == EXPECTED_REFERENCE_SHA256,
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks, "actual": actual, "reference_hashes": refs,
            "source_commit": SOURCE_COMMIT,
            "audit_policy": {"require_negative_control": True,
                             "require_two_sided_negative_control": True,
                             "require_unconstrained_sat": True,
                             "scope_source": "locked ByteMaskTailGen closure"},
            "xstop": {"path": LOCKED_XSTOP, "sha256": XSTOP_SHA256,
                      "bytes": XSTOP_BYTES}}


def materialize_miter(target_rtl: str) -> dict[str, Path]:
    """Write target, renamed closure top, and both-output miter."""

    closure_text = REFERENCE.read_text(encoding="utf-8")
    marker = "module ByteMaskTailGen("
    if marker not in closure_text:
        raise AssertionError("locked ByteMaskTailGen closure declaration missing")
    WORK.mkdir(parents=True, exist_ok=True)
    target = WORK / "UHSC_ByteMaskTailGen.sv"
    reference = WORK / "REF_ByteMaskTailGen_closure.sv"
    miter = WORK / "ByteMaskTailGen_MITER.sv"
    target.write_text(target_rtl, encoding="utf-8", newline="\n")
    reference.write_text(closure_text.replace(marker, "module REF_ByteMaskTailGen(", 1),
                          encoding="utf-8", newline="\n")
    miter.write_text(
        """module ByteMaskTailGen_MITER(
  input [7:0] io_in_begin,
  input [7:0] io_in_end,
  input io_in_vma,
  input io_in_vta,
  input [1:0] io_in_vsew,
  input [15:0] io_in_maskUsed,
  input [2:0] io_in_vdIdx,
  output mismatch
);
  wire [15:0] ref_active, ref_agnostic;
  wire [15:0] dut_active, dut_agnostic;
  REF_ByteMaskTailGen reference_i(
    .io_in_begin(io_in_begin), .io_in_end(io_in_end),
    .io_in_vma(io_in_vma), .io_in_vta(io_in_vta),
    .io_in_vsew(io_in_vsew), .io_in_maskUsed(io_in_maskUsed),
    .io_in_vdIdx(io_in_vdIdx), .io_out_activeEn(ref_active),
    .io_out_agnosticEn(ref_agnostic));
  ByteMaskTailGen target_i(
    .io_in_begin(io_in_begin), .io_in_end(io_in_end),
    .io_in_vma(io_in_vma), .io_in_vta(io_in_vta),
    .io_in_vsew(io_in_vsew), .io_in_maskUsed(io_in_maskUsed),
    .io_in_vdIdx(io_in_vdIdx), .io_out_activeEn(dut_active),
    .io_out_agnosticEn(dut_agnostic));
  assign mismatch = |(ref_active ^ dut_active)
                  | |(ref_agnostic ^ dut_agnostic);
endmodule
""",
        encoding="utf-8", newline="\n")
    return {"target": target, "reference": reference, "miter": miter}


def formal_gates(paths: dict[str, Path]) -> dict[str, Any]:
    """Run Verilator/Yosys lint and unrestricted SAT equivalence."""

    converted = {name: wsl_path(path) for name, path in paths.items()}
    target, reference, miter = (converted["target"], converted["reference"],
                                converted["miter"])
    verilator = run_wsl([
        "verilator", "--lint-only", "-Wno-fatal", "--top-module",
        "ByteMaskTailGen_MITER", target, reference, miter,
    ])
    target_yosys = run_wsl(["yosys", "-Q", "-p",
                            f"read_verilog -sv {shlex.quote(target)}; "
                            "hierarchy -top ByteMaskTailGen; proc; opt; check"])
    reference_yosys = run_wsl(["yosys", "-Q", "-p",
                               f"read_verilog -sv {shlex.quote(reference)}; "
                               "hierarchy -top REF_ByteMaskTailGen; proc; opt; check"])
    proof_script = (
        f"read_verilog -sv {shlex.quote(target)} {shlex.quote(reference)} "
        f"{shlex.quote(miter)}; prep -top ByteMaskTailGen_MITER; flatten; opt; "
        "sat -prove mismatch 0"
    )
    proof = run_wsl(["yosys", "-Q", "-p", proof_script])
    proof["formal_success_marker"] = proof.get("sat_success_marker") is True
    proof["unconstrained"] = proof.get("unconstrained_marker") is True
    proof["mitered_variants"] = 1
    if not proof["formal_success_marker"] or not proof["unconstrained"]:
        proof["status"] = "FAIL"
    proof["formal_scope"] = {
        "input_bits": INPUT_BITS,
        "input_bit_accounting": "8+8+1+1+2+16+3=39 (locked flattened ABI; no padding inputs)",
        "input_space": f"2**{INPUT_BITS}",
        "input_space_cardinality": str(1 << INPUT_BITS),
        "state_bits": 0,
        "state_space": "singleton (stateless combinational module and children)",
        "property": "mismatch == 0 for every 2-state valuation of all ByteMaskTailGen inputs",
        "outputs_compared": OUTPUT_WIDTHS,
        "output_bits": OUTPUT_BITS,
    }
    return {
        "verilator": verilator,
        "yosys_target": target_yosys,
        "yosys_reference": reference_yosys,
        "yosys_formal_miter": proof,
    }


def _mutate_output(text: str, module: str, port: str, width: int) -> tuple[str, bool]:
    """Pin one top-level output low without touching closure children."""

    start = text.find(f"module {module}(")
    if start < 0:
        return text, False
    end = text.find("endmodule", start)
    if end < 0:
        return text, False
    body = text[start:end]
    mutated, count = re.subn(
        rf"assign\s+{re.escape(port)}\s*=.*?;",
        f"assign {port} = {width}'h0;", body, count=1, flags=re.S)
    if count != 1:
        return text, False
    return text[:start] + mutated + text[end:], True


def _sat_run(paths: dict[str, Path], target: Path, reference: Path) -> dict[str, Any]:
    """Run the same unrestricted miter with one selected side mutated."""

    converted = {name: wsl_path(path) for name, path in
                 {"target": target, "reference": reference,
                  "miter": paths["miter"]}.items()}
    script = (f"read_verilog -sv {shlex.quote(converted['target'])} "
              f"{shlex.quote(converted['reference'])} {shlex.quote(converted['miter'])}; "
              "prep -top ByteMaskTailGen_MITER; flatten; opt; sat -prove mismatch 0")
    verdict = run_wsl(["yosys", "-Q", "-p", script])
    verdict["formal_success_marker"] = verdict.get("sat_success_marker") is True
    verdict["unconstrained"] = verdict.get("unconstrained_marker") is True
    if verdict.get("returncode") != 0 or verdict["formal_success_marker"]:
        verdict["status"] = "FAIL" if verdict.get("returncode") != 0 else "PASS"
    return verdict


def negative_control(paths: dict[str, Path]) -> dict[str, Any]:
    """Mutate target and reference outputs and require SAT counterexamples."""

    results: dict[str, Any] = {}
    for side in ("target", "reference"):
        source = paths[side].read_text(encoding="utf-8")
        module = "ByteMaskTailGen" if side == "target" else "REF_ByteMaskTailGen"
        mutated, applied = _mutate_output(source, module, "io_out_activeEn", 16)
        mutant = WORK / f"ByteMaskTailGen-{side}-mutant.sv"
        mutant.write_text(mutated, encoding="utf-8", newline="\n")
        if not applied:
            results[side] = {"status": "FAIL", "mutation_applied": False,
                             "clean_proof_marker_disappeared": False,
                             "counterexample_or_unproven": False}
            continue
        target = mutant if side == "target" else paths["target"]
        reference = mutant if side == "reference" else paths["reference"]
        verdict = _sat_run(paths, target, reference)
        marker_disappeared = not bool(verdict.get("formal_success_marker"))
        counterexample = bool(verdict.get("sat_counterexample_marker"))
        detected = (isinstance(verdict.get("returncode"), int)
                    and marker_disappeared and counterexample)
        results[side] = {
            "status": "PASS" if detected else "FAIL",
            "mutation_applied": True,
            "control_port": "io_out_activeEn",
            "clean_proof_marker_disappeared": marker_disappeared,
            "counterexample_marker": counterexample,
            "counterexample_or_unproven": counterexample,
            "success_marker_still_present": verdict.get("formal_success_marker"),
            "output_tail": verdict.get("output_tail", "")[-1200:],
        }
    all_pass = all(item.get("status") == "PASS" for item in results.values())
    return {"status": "PASS" if all_pass else "FAIL", "sides": results,
            "two_sided": True,
            "mutation_applied": all(item.get("mutation_applied") is True for item in results.values()),
            "clean_proof_marker_disappeared": all(item.get("clean_proof_marker_disappeared") is True for item in results.values()),
            "counterexample_or_unproven": all(item.get("counterexample_or_unproven") is True for item in results.values())}


def validate() -> dict[str, Any]:
    """Run all strict gates and persist evidence."""

    closure = closure_audit()
    failures: list[str] = []
    if closure["status"] != "PASS":
        failures.append("closure audit")
    locks = source_lock_audit()
    if locks["status"] != "PASS":
        failures.append("source lock audit")
    module = load_target()
    py_compile.compile(str(TARGET), doraise=True)
    py_compile.compile(str(Path(__file__)), doraise=True)
    target_rtl, export = deterministic_export(module)
    paths = materialize_miter(target_rtl)
    reference_view = paths["reference"].read_text(encoding="utf-8")
    abi = abi_audit(target_rtl, reference_view)
    miter = miter_selfcheck(paths["miter"].read_text(encoding="utf-8"))
    gates = formal_gates(paths)
    control = negative_control(paths)
    pyright = {"target": pyright_check(TARGET),
               "validator": pyright_check(Path(__file__))}
    if export["status"] != "PASS":
        failures.append("deterministic export mismatch")
    if abi["status"] != "PASS":
        failures.append("ABI audit")
    if miter["status"] != "PASS":
        failures.append("miter selfcheck")
    for name, result in pyright.items():
        if result["status"] != "PASS":
            failures.append(f"pyright {name}")
    for name, result in gates.items():
        if result["status"] != "PASS":
            failures.append(name)
    if control["status"] != "PASS":
        failures.append("two-sided negative control")
    status = "COMPLETE_EQUIVALENCE" if not failures else "STRICT_PENDING"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_STRICT_COMPLETE_EQUIVALENCE",
        "build_id": "Build-Cpu.Backend.Fu.Vector.ByteMaskTailGen",
        "validator": Path(__file__).relative_to(ROOT).as_posix(),
        "status": status,
        "strict_complete_eligible": status == "COMPLETE_EQUIVALENCE",
        "strict_complete_count_delta": 1 if status == "COMPLETE_EQUIVALENCE" else 0,
        "acceptance_eligible": status == "COMPLETE_EQUIVALENCE",
        "source_commit": SOURCE_COMMIT,
        "audit_policy": {"require_negative_control": True,
                         "require_two_sided_negative_control": True,
                         "require_unconstrained_sat": True,
                         "scope_source": "locked ByteMaskTailGen closure"},
        "scope": {
            "kind": "stateless_combinational_leaf_with_combinational_children",
            "configuration": "locked V2 vlen=128, maxVLMAX=128, 16-byte destination slice",
            "state_bits": 0,
            "state_boundary": "no clock/reset/register/memory in top or extracted children",
            "inputs": INPUT_WIDTHS,
            "input_bits": INPUT_BITS,
            "input_bit_accounting": "8+8+1+1+2+16+3=39",
            "input_space": f"2**{INPUT_BITS}",
            "input_space_cardinality": str(1 << INPUT_BITS),
            "outputs_compared": OUTPUT_WIDTHS,
            "output_bits": OUTPUT_BITS,
            "why_complete": (
                "Yosys SAT proves both 16-bit output buses equal for every valuation "
                "of all 39 flattened input bits; all four closure modules are purely combinational."
            ),
            "bounded_tests_counted": False,
        },
        "reference_lock": {
            "path": LOCKED_XSTOP,
            "upstream_source_commit": SOURCE_COMMIT,
            "xstop_sha256": XSTOP_SHA256,
            "xstop_bytes": XSTOP_BYTES,
            "closure_manifest": closure,
            "sha256_by_module": {
                name: EXPECTED_REFERENCE_SHA256[name] for name in EXPECTED_MODULES
            },
            "extraction_rule": "exact ByteMaskTailGen module plus instantiated MaskExtractor/UIntToContLow0s/UIntToContLow1s from immutable XSTop.sv",
        },
        "sources": {
            "scala": {"path": SCALA.relative_to(ROOT).as_posix(),
                      "sha256": sha256_file(SCALA), "bytes": SCALA.stat().st_size},
            "reference_sv": {"path": REFERENCE.relative_to(ROOT).as_posix(),
                             "sha256": sha256_file(REFERENCE), "bytes": REFERENCE.stat().st_size,
                             "modules": EXPECTED_MODULES,
                             "closure_manifest": MANIFEST.relative_to(ROOT).as_posix()},
            "reference_children": {
                name: {"path": f"validation/reference-sv/{name}.sv",
                       "sha256": EXPECTED_REFERENCE_SHA256[name],
                       "bytes": (ROOT / "validation/reference-sv" / f"{name}.sv").stat().st_size}
                for name in EXPECTED_MODULES[1:]},
            "closure_manifest": {"path": MANIFEST.relative_to(ROOT).as_posix(),
                                 "sha256": sha256_file(MANIFEST), "bytes": MANIFEST.stat().st_size},
            "python_build": {"path": TARGET.relative_to(ROOT).as_posix(),
                             "sha256": sha256_file(TARGET), "bytes": TARGET.stat().st_size},
        },
        "checks": {
            "py_compile": {"status": "PASS", "files": [
                TARGET.relative_to(ROOT).as_posix(),
                Path(__file__).relative_to(ROOT).as_posix(),
            ]},
            "pyright": pyright,
            "source_lock": locks,
            "abi": abi,
            "miter_selfcheck": miter,
            "deterministic_export": export,
            "closure_audit": closure,
            "tools": tool_versions(),
            "formal": {**gates, "negative_control": control},
            "negative_control": control,
        },
        "failures": failures,
        "unclosed": [] if not failures else ["strict gates did not all pass"],
        "acceptance_unclosed": [
            "Backend/Fu parent closure, license review and user approval remain outside this proof.",
        ],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    return payload


def main() -> int:
    """Print strict status and return nonzero until all gates pass."""

    payload = validate()
    print(json.dumps({"status": payload["status"],
                      "strict_complete_eligible": payload["strict_complete_eligible"],
                      "failures": payload["failures"]}, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
