"""Strict sequential equivalence validator for the locked V2 Sstc leaf.

SstcInterruptGen has a fixed 17-port ABI and two asynchronously reset state
bits.  This validator reruns the existing focused bounded checks, compares the
complete ABI, and proves the full transition relation with Yosys
``equiv_make`` + ``equiv_induct -undef`` after ``async2sync``.
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
    "Build-Cpu.Backend.Fu.NewCSR.SstcInterruptGen-Hardware.py"
)
SCALA = ROOT / "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala"
REFERENCE = ROOT / "validation/reference-closures/SstcInterruptGen-v2.sv"
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_sstcinterruptgen_strict"
EVIDENCE = ROOT / "validation/v2-sstcinterruptgen-strict-evidence.json"

SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
SOURCE_SHA256 = "e9156dc6a0eb8041b6476f537a6ece689daa06143f87c3a387c0eea7891a9da7"
REFERENCE_SHA256 = "e1ab00c5a55a283e913d9ab1413cb77925344e616af5491a1844c38bda8c29bf"
XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
XSTOP_BYTES = 228590583
XSTOP_LINE_START = 1227143
XSTOP_LINE_END = 1227203

INPUT_WIDTHS = {
    "clock": 1,
    "reset": 1,
    "i_stime_valid": 1,
    "i_stime_bits": 64,
    "i_vstime_valid": 1,
    "i_vstime_bits": 64,
    "i_stimecmp_wen": 1,
    "i_stimecmp_rdata": 64,
    "i_vstimecmp_wen": 1,
    "i_vstimecmp_rdata": 64,
    "i_htimedeltaWen": 1,
    "i_menvcfg_wen": 1,
    "i_menvcfg_STCE": 1,
    "i_henvcfg_wen": 1,
    "i_henvcfg_STCE": 1,
}
OUTPUT_WIDTHS = {"o_STIP": 1, "o_VSTIP": 1}
INPUT_BITS = sum(INPUT_WIDTHS.values())
OUTPUT_BITS = sum(OUTPUT_WIDTHS.values())
PORT_NAMES = tuple(INPUT_WIDTHS) + tuple(OUTPUT_WIDTHS)
EQUIV_SUCCESS_MARKERS = ("0 are unproven.", "Equivalence successfully proven!")


def sha256_file(path: Path) -> str:
    """Hash exact bytes."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_module(path: Path, name: str) -> Any:
    """Load one exact Python module path."""

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_target() -> Any:
    """Load the selected Build module."""

    return load_module(TARGET, "strict_sstc_target")


def wsl_path(path: Path) -> str:
    """Convert a Windows path to WSL spelling."""

    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                            capture_output=True, check=True)
    return result.stdout.decode("utf-8", "replace").strip()


def run_wsl(command: list[str]) -> dict[str, Any]:
    """Run one WSL command with bounded diagnostics."""

    rendered = " ".join(shlex.quote(item) for item in command)
    try:
        result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered],
                                capture_output=True, check=False)
    except OSError as error:
        return {"command": command, "status": "FAIL", "error": repr(error)}
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    summaries = re.findall(r"Of those cells (\d+) are proven and (\d+) are unproven", output)
    proven_cells = unproven_cells = equiv_cells = None
    if summaries:
        proven_cells, unproven_cells = map(int, summaries[-1])
        equiv_cells = proven_cells + unproven_cells
    return {"command": command, "returncode": result.returncode,
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "equiv_success_markers": {marker: marker in output for marker in EQUIV_SUCCESS_MARKERS},
            "equiv_failure_marker": bool(
                re.search(r"ERROR:\s*Found\s+[1-9]\d*\s+unproven\s+\$equiv\s+cells", output)
                or re.search(r"Of those cells\s+\d+\s+are proven and\s+[1-9]\d*\s+are unproven", output)),
            "equiv_cells": equiv_cells,
            "proven_cells": proven_cells,
            "unproven_cells": unproven_cells,
            "output_tail": output[-6000:],
            "output_sha256": hashlib.sha256(output.encode()).hexdigest()}


def pyright_check(source: Path) -> dict[str, Any]:
    """Run Pyright on an ASCII temporary copy."""

    temporary = Path(tempfile.mkdtemp(prefix="uhsc_sstc_pyright_"))
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


def parse_header_ports(rtl: str, module: str = "SstcInterruptGen") -> set[str]:
    """Extract the exact names in the generated ANSI module header."""

    match = re.search(r"module\s+" + re.escape(module) + r"\s*\((.*?)\);", rtl, re.DOTALL)
    if match is None:
        raise AssertionError("SstcInterruptGen module header missing")
    header = match.group(1)
    return {name for name in PORT_NAMES
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", header)}


def deterministic_export(module: Any) -> tuple[str, dict[str, Any]]:
    """Generate exact default RTL twice and check the 17-port ABI."""

    first = module.build_verilog(None, {})
    second = module.build_verilog(None, {})
    first_bytes = first.encode("utf-8")
    second_bytes = second.encode("utf-8")
    observed = parse_header_ports(first)
    expected = set(PORT_NAMES)
    abi_ok = observed == expected
    return first, {"status": "PASS" if first_bytes == second_bytes and abi_ok else "FAIL",
                   "bytes": len(first_bytes),
                   "sha256": hashlib.sha256(first_bytes).hexdigest(),
                   "repeat_sha256": hashlib.sha256(second_bytes).hexdigest(),
                   "byte_equal": first_bytes == second_bytes,
                   "abi": {"expected_port_count": len(expected),
                           "observed_port_count": len(observed),
                           "exact_port_set": abi_ok}}


def abi_audit(target_rtl: str, reference_rtl: str) -> dict[str, Any]:
    """Require the exact locked 17-port surface on both sides."""

    expected = set(PORT_NAMES)
    target = parse_header_ports(target_rtl)
    reference = parse_header_ports(reference_rtl, "SstcInterruptGen_ref")
    checks = {"target_exact_port_set": target == expected,
              "reference_exact_port_set": reference == expected,
              "target_reference_equal": target == reference,
              "input_bits": INPUT_BITS == 267,
              "output_bits": OUTPUT_BITS == 2}
    return {"status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks, "target_ports": sorted(target),
            "reference_ports": sorted(reference)}


def locked_source_check() -> dict[str, Any]:
    """Validate locked Scala/reference provenance."""

    scala_hash = sha256_file(SCALA)
    reference_hash = sha256_file(REFERENCE)
    text = REFERENCE.read_text(encoding="utf-8")
    markers = ("module SstcInterruptGen(", "i_stime_bits", "i_vstime_bits",
               "output        o_STIP", "o_VSTIP", "posedge reset")
    return {"status": "PASS" if scala_hash == SOURCE_SHA256
            and reference_hash == REFERENCE_SHA256
            and all(marker in text for marker in markers) else "FAIL",
            "scala_sha256": scala_hash,
            "expected_scala_sha256": SOURCE_SHA256,
            "reference_sha256": reference_hash,
            "expected_reference_sha256": REFERENCE_SHA256,
            "source_commit": SOURCE_COMMIT,
            "xstop": {"sha256": XSTOP_SHA256, "bytes": XSTOP_BYTES,
                      "module": "SstcInterruptGen",
                      "line_start": XSTOP_LINE_START,
                      "line_end": XSTOP_LINE_END}}


def bounded_checks(module: Any) -> dict[str, Any]:
    """Rerun the existing focused direct and Verilator differential checks."""

    batch_path = ROOT / "validation/v2_csr_divider_batch.py"
    ref_path = ROOT / "validation/v2_csr_divider_reference.py"
    batch = load_module(batch_path, "strict_sstc_batch")
    reference = load_module(ref_path, "strict_sstc_reference")
    direct = batch.test_sstc(module)
    differential = reference.compare_sstc(module)
    passed = direct.get("cycles") == 2 and differential.get("status") == "PASS"
    return {"status": "PASS" if passed else "FAIL",
            "direct": direct,
            "reference_differential": differential,
            "note": "The aggregate v2_csr_divider_batch audit is not used because unrelated family files may fail its global comment gate."}


def materialize(target_rtl: str) -> dict[str, Path]:
    """Write renamed target/reference RTL into an ASCII temp directory."""

    WORK.mkdir(parents=True, exist_ok=True)
    target = WORK / "SstcInterruptGen-target.sv"
    reference = WORK / "SstcInterruptGen-reference.sv"
    target.write_text(target_rtl, encoding="utf-8", newline="\n")
    reference.write_text(REFERENCE.read_text(encoding="utf-8").replace(
        "module SstcInterruptGen(", "module SstcInterruptGen_ref(", 1),
        encoding="utf-8", newline="\n")
    return {"target": target, "reference": reference}


def formal_gates(paths: dict[str, Path]) -> dict[str, Any]:
    """Run backend lint and complete sequential equivalence."""

    target = wsl_path(paths["target"])
    reference = wsl_path(paths["reference"])
    target_verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal",
                                "--top-module", "SstcInterruptGen", target])
    reference_verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal",
                                   "--top-module", "SstcInterruptGen_ref", reference])
    target_yosys = run_wsl(["yosys", "-Q", "-p",
                            f"read_verilog -sv {shlex.quote(target)}; proc; async2sync; opt; "
                            "hierarchy -top SstcInterruptGen; check; stat"])
    reference_yosys = run_wsl(["yosys", "-Q", "-p",
                               f"read_verilog -sv {shlex.quote(reference)}; proc; async2sync; opt; "
                               "hierarchy -top SstcInterruptGen_ref; check; stat"])
    formal_script = (f"read_verilog -sv {shlex.quote(target)} {shlex.quote(reference)}; "
                     "proc; async2sync; memory; opt; "
                     "equiv_make SstcInterruptGen SstcInterruptGen_ref Sstc_equiv; "
                     "prep -top Sstc_equiv; equiv_induct -undef; equiv_status -assert")
    formal = run_wsl(["yosys", "-Q", "-p", formal_script])
    formal["markers_present"] = formal.get("equiv_success_markers", {})
    formal["formal_success_marker"] = all(
        formal.get("equiv_success_markers", {}).get(marker) is True
        for marker in EQUIV_SUCCESS_MARKERS)
    equiv_cells = formal.get("equiv_cells")
    if (not formal["formal_success_marker"]
            or not isinstance(equiv_cells, int) or isinstance(equiv_cells, bool)
            or equiv_cells <= 0 or formal.get("unproven_cells") != 0
            or formal.get("proven_cells") != equiv_cells):
        formal["status"] = "FAIL"
    formal["formal_scope"] = {"clock": "posedge clock",
                              "reset": "async reset normalized with async2sync",
                              "input_bits": INPUT_BITS,
                              "inputs_unconstrained": INPUT_WIDTHS,
                              "output_bits": OUTPUT_BITS,
                              "outputs_compared": OUTPUT_WIDTHS,
                              "state_bits": 2,
                              "property": "all two state bits and both outputs equivalent for every input sequence"}
    return {"target_verilator": target_verilator,
            "reference_verilator": reference_verilator,
            "target_yosys": target_yosys,
            "reference_yosys": reference_yosys,
            "yosys_equiv": formal}


def negative_control(paths: dict[str, Path]) -> dict[str, Any]:
    """Mutate target and reference independently and require unproven cells."""

    results: dict[str, Any] = {}
    for side in ("target", "reference"):
        source = paths[side].read_text(encoding="utf-8")
        if side == "target":
            mutated, count = re.subn(r"else\s+o_STIP\s*<=\s*[^;]+;",
                                     "else o_STIP <= 1'b1;", source, count=1)
        else:
            mutated, count = re.subn(r"assign\s+o_STIP\s*=\s*[^;]+;",
                                     "assign o_STIP = 1'b0;", source, count=1)
        if count != 1:
            results[side] = {"status": "FAIL", "mutation_applied": False}
            continue
        mutant = WORK / f"MUTANT_{side}.sv"
        mutant.write_text(mutated, encoding="utf-8", newline="\n")
        selected = {**paths, side: mutant}
        target = wsl_path(selected["target"])
        reference = wsl_path(selected["reference"])
        script = (f"read_verilog -sv {target} {reference}; proc; async2sync; memory; opt; "
                  "equiv_make SstcInterruptGen SstcInterruptGen_ref Sstc_equiv; "
                  "prep -top Sstc_equiv; equiv_induct -undef; equiv_status -assert")
        verdict = run_wsl(["yosys", "-Q", "-p", script])
        explicit = (verdict.get("equiv_failure_marker") is True
                    or (isinstance(verdict.get("unproven_cells"), int)
                        and verdict.get("unproven_cells", 0) > 0))
        still = all(verdict.get("equiv_success_markers", {}).values())
        detected = isinstance(verdict.get("returncode"), int) and explicit and not still
        results[side] = {"status": "PASS" if detected else "FAIL",
                         "mutation_applied": True,
                         "explicit_unproven_cells": explicit,
                         "success_marker_still_present": still,
                         "returncode": verdict.get("returncode"),
                         "unproven_cells": verdict.get("unproven_cells")}
    return {"status": "PASS" if all(item["status"] == "PASS" for item in results.values()) else "FAIL",
            "sides": results, "two_sided": True}


def validate() -> dict[str, Any]:
    """Run strict gates and persist evidence."""

    failures: list[str] = []
    lock: dict[str, Any] = {"status": "FAIL"}
    bounded: dict[str, Any] = {"status": "FAIL"}
    export: dict[str, Any] = {"status": "FAIL"}
    abi: dict[str, Any] = {"status": "FAIL"}
    gates: dict[str, Any] = {}
    control: dict[str, Any] = {"status": "FAIL"}
    try:
        lock = locked_source_check()
        if lock["status"] != "PASS":
            failures.append("locked source/reference provenance")
        module = load_target()
        bounded = bounded_checks(module)
        if bounded["status"] != "PASS":
            failures.append("bounded direct/reference checks")
        py_compile.compile(str(TARGET), doraise=True)
        py_compile.compile(str(Path(__file__)), doraise=True)
        target_rtl, export = deterministic_export(module)
        paths = materialize(target_rtl)
        abi = abi_audit(target_rtl, paths["reference"].read_text(encoding="utf-8"))
        if abi["status"] != "PASS":
            failures.append("exact ABI audit")
        gates = formal_gates(paths)
        control = negative_control(paths)
        if control["status"] != "PASS":
            failures.append("two-sided negative control")
    except Exception as error:
        failures.append(f"exception: {type(error).__name__}: {error}")
    pyright = {"target": pyright_check(TARGET),
               "validator": pyright_check(Path(__file__))}
    if export.get("status") != "PASS":
        failures.append("deterministic export/ABI")
    for name, result in pyright.items():
        if result["status"] != "PASS":
            failures.append(f"pyright {name}")
    for name, result in gates.items():
        if result.get("status") != "PASS":
            failures.append(name)
    status = "COMPLETE_EQUIVALENCE" if not failures else "STRICT_PENDING"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_STRICT_COMPLETE_EQUIVALENCE",
        "build_id": "Build-Cpu.Backend.Fu.NewCSR.SstcInterruptGen",
        "validator": Path(__file__).relative_to(ROOT).as_posix(),
        "status": status,
        "strict_complete_eligible": status == "COMPLETE_EQUIVALENCE",
        "strict_complete_count_delta": 1 if status == "COMPLETE_EQUIVALENCE" else 0,
        "acceptance_eligible": status == "COMPLETE_EQUIVALENCE",
        "source_commit": SOURCE_COMMIT,
        "audit_policy": {"require_negative_control": True,
                         "require_two_sided_negative_control": True,
                         "require_positive_equiv_cells": True,
                         "require_all_declared_outputs_compared": True,
                         "scope_source": "single locked SstcInterruptGen surface"},
        "scope": {"kind": "sequential_registered_leaf",
                  "configuration": "fixed V2 SstcInterruptGen IO",
                  "state_bits": 2,
                  "state_boundary": "two independently enabled async-reset TIP registers",
                  "semantics": {"stip_enable": "i_stime_valid | i_stimecmp_wen | i_menvcfg_wen",
                                 "vstip_enable": "i_vstime_valid | i_vstimecmp_wen | i_htimedeltaWen | i_menvcfg_wen | i_henvcfg_wen",
                                 "compare": "unsigned 64-bit >= with STCE/HSTCE gating",
                                 "reset_value": {"o_STIP": 0, "o_VSTIP": 0},
                                 "disabled_enable": "RegEnable hold"},
                  "inputs": INPUT_WIDTHS,
                  "outputs_compared": OUTPUT_WIDTHS,
                  "input_bits": INPUT_BITS,
                  "output_bits": OUTPUT_BITS,
                  "transition_relation": "all input sequences, posedge clock, async reset",
                  "why_complete": "Yosys equiv_induct -undef proves both state/output cells with all 267 input bits unconstrained",
                  "bounded_tests_counted": False},
        "reference_lock": lock,
        "sources": {"scala": {"path": SCALA.relative_to(ROOT).as_posix(),
                                "sha256": sha256_file(SCALA), "bytes": SCALA.stat().st_size},
                    "reference_sv": {"path": REFERENCE.relative_to(ROOT).as_posix(),
                                     "sha256": sha256_file(REFERENCE), "bytes": REFERENCE.stat().st_size,
                                     "locked_module": "SstcInterruptGen"},
                    "python_build": {"path": TARGET.relative_to(ROOT).as_posix(),
                                     "sha256": sha256_file(TARGET), "bytes": TARGET.stat().st_size}},
        "checks": {"py_compile": {"status": "PASS" if not any(x.startswith("exception:") for x in failures) else "FAIL",
                                    "files": [TARGET.relative_to(ROOT).as_posix(), Path(__file__).relative_to(ROOT).as_posix()]},
                    "pyright": pyright,
                    "source_lock": lock,
                    "abi": abi,
                    "deterministic_export": export,
                    "bounded_behavior": bounded,
                    "tools": {"verilator": run_wsl(["verilator", "--version"]),
                              "yosys": run_wsl(["yosys", "--version"])},
                    "formal": gates,
                    "negative_control": control},
        "failures": failures,
        "unclosed": [] if not failures else ["strict sequential equivalence gates did not all pass"],
        "acceptance_unclosed": [
            "CSR parent closure, license review and user approval remain outside this proof."
        ],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    return payload


def main() -> int:
    """Print strict status and return nonzero while pending."""

    payload = validate()
    print(json.dumps({"status": payload["status"],
                      "strict_complete_eligible": payload["strict_complete_eligible"],
                      "failures": payload["failures"]}, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
