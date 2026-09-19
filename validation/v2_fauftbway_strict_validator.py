"""Strict sequential equivalence validator for the locked V2 FauFTBWay leaf.

The Build is a registered one-way FTB entry.  Its payload and tag registers
are intentionally reset-less while ``valid`` alone has the asynchronous reset
visible in the locked XSTop closure.  The validator compares the complete
locked ABI and uses Yosys ``equiv_make`` + ``equiv_induct -undef`` after
``async2sync``.  Thus every input sequence and every initial state represented
by the two-state transition system are covered; this is not a trace sample.
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
    "Build-Cpu.Frontend.Bpu.FauFTBWay-Hardware.py"
)
SCALA = ROOT / "upstream/src/main/scala/xiangshan/frontend/FauFTB.scala"
REFERENCE = ROOT / "validation/reference-closures/FauFTBWay.sv"
REFERENCE_INDEX = ROOT / "validation/v2-frontend-fauftbway-reference-index.json"
DIRECT_RESULT = ROOT / "validation/v2-frontend-fauftbway-direct-results.json"
DIFFERENTIAL_RESULT = ROOT / "validation/v2-frontend-fauftbway-differential-results.json"
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_fauftbway_strict"
EVIDENCE = ROOT / "validation/v2-fauftbway-strict-evidence.json"

SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
SOURCE_SHA256 = "05960e23660ebb2b44c1b7273c935f1afae39e381e283e2560c222d667d16580"
REFERENCE_SHA256 = "5bb9be2dc0cd27246b275f621eded9e28203028be17b0ddb1ad957bbef665451"
XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
XSTOP_BYTES = 228590583

INPUT_WIDTHS = {
    "clock": 1,
    "reset": 1,
    "io_req_tag": 16,
    "io_update_req_tag": 16,
    "io_write_valid": 1,
    "io_write_entry_isCall": 1,
    "io_write_entry_isRet": 1,
    "io_write_entry_isJalr": 1,
    "io_write_entry_valid": 1,
    "io_write_entry_brSlots_0_offset": 4,
    "io_write_entry_brSlots_0_sharing": 1,
    "io_write_entry_brSlots_0_valid": 1,
    "io_write_entry_brSlots_0_lower": 12,
    "io_write_entry_brSlots_0_tarStat": 2,
    "io_write_entry_tailSlot_offset": 4,
    "io_write_entry_tailSlot_sharing": 1,
    "io_write_entry_tailSlot_valid": 1,
    "io_write_entry_tailSlot_lower": 20,
    "io_write_entry_tailSlot_tarStat": 2,
    "io_write_entry_pftAddr": 4,
    "io_write_entry_carry": 1,
    "io_write_entry_last_may_be_rvi_call": 1,
    "io_write_entry_strong_bias_0": 1,
    "io_write_entry_strong_bias_1": 1,
    "io_write_tag": 16,
}

OUTPUT_WIDTHS = {
    "io_resp_isCall": 1,
    "io_resp_isRet": 1,
    "io_resp_isJalr": 1,
    "io_resp_valid": 1,
    "io_resp_brSlots_0_offset": 4,
    "io_resp_brSlots_0_sharing": 1,
    "io_resp_brSlots_0_valid": 1,
    "io_resp_brSlots_0_lower": 12,
    "io_resp_brSlots_0_tarStat": 2,
    "io_resp_tailSlot_offset": 4,
    "io_resp_tailSlot_sharing": 1,
    "io_resp_tailSlot_valid": 1,
    "io_resp_tailSlot_lower": 20,
    "io_resp_tailSlot_tarStat": 2,
    "io_resp_pftAddr": 4,
    "io_resp_carry": 1,
    "io_resp_last_may_be_rvi_call": 1,
    "io_resp_strong_bias_0": 1,
    "io_resp_strong_bias_1": 1,
    "io_resp_hit": 1,
    "io_update_hit": 1,
}

INPUT_BITS = sum(INPUT_WIDTHS.values())
OUTPUT_BITS = sum(OUTPUT_WIDTHS.values())
# data payload (60), tag (16), and valid (1) in the locked reference.
REFERENCE_STATE_BITS = 77
PORT_NAMES = tuple(INPUT_WIDTHS) + tuple(OUTPUT_WIDTHS)


def sha256_file(path: Path) -> str:
    """Hash exact file bytes for reproducible provenance."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_target() -> Any:
    """Load the selected Build module by exact path."""

    spec = importlib.util.spec_from_file_location("strict_fauftbway_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load target: {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def wsl_path(path: Path) -> str:
    """Convert a Windows path to an absolute WSL path."""

    result = subprocess.run(
        ["wsl.exe", "-e", "wslpath", "-a", str(path)],
        capture_output=True,
        check=True,
    )
    return result.stdout.decode("utf-8", "replace").strip()


def run_wsl(command: list[str]) -> dict[str, Any]:
    """Run one WSL command and retain bounded diagnostics."""

    rendered = " ".join(shlex.quote(item) for item in command)
    try:
        result = subprocess.run(
            ["wsl.exe", "-e", "bash", "-lc", rendered],
            capture_output=True,
            check=False,
        )
    except OSError as error:
        return {"command": command, "status": "FAIL", "error": repr(error)}
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {
        "command": command,
        "returncode": result.returncode,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "output_tail": output[-6000:],
        "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
    }


def tool_versions() -> dict[str, Any]:
    """Record exact Verilator/Yosys versions used by the strict run."""

    return {
        "verilator": run_wsl(["verilator", "--version"]),
        "yosys": run_wsl(["yosys", "--version"]),
    }


def pyright_check(source: Path) -> dict[str, Any]:
    """Run Pyright on an ASCII temporary copy of one source file."""

    temporary = Path(tempfile.mkdtemp(prefix="uhsc_fauftbway_pyright_"))
    try:
        copied = temporary / source.name
        shutil.copyfile(source, copied)
        command = ["cmd.exe", "/d", "/c", "pyright", "--outputjson", str(copied)]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
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


def parse_header_ports(rtl: str) -> set[str]:
    """Return the exact names in the generated ANSI module header."""

    match = re.search(r"module\s+FauFTBWay\s*\((.*?)\);", rtl, re.DOTALL)
    if match is None:
        raise AssertionError("FauFTBWay module header missing")
    header = match.group(1)
    return {
        name for name in PORT_NAMES
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", header)
    }


def deterministic_export(module: Any) -> tuple[str, dict[str, Any]]:
    """Generate the locked default RTL twice and check ABI/determinism."""

    first = module.build_verilog(None, {})
    second = module.build_verilog(None, {})
    first_bytes = first.encode("utf-8")
    second_bytes = second.encode("utf-8")
    expected_ports = set(PORT_NAMES)
    observed_ports = parse_header_ports(first)
    abi_ok = observed_ports == expected_ports and "io_write_fire" not in first
    return first, {
        "status": "PASS" if first_bytes == second_bytes and abi_ok else "FAIL",
        "bytes": len(first_bytes),
        "sha256": hashlib.sha256(first_bytes).hexdigest(),
        "repeat_sha256": hashlib.sha256(second_bytes).hexdigest(),
        "byte_equal": first_bytes == second_bytes,
        "abi": {
            "expected_port_count": len(expected_ports),
            "observed_port_count": len(observed_ports),
            "exact_port_set": abi_ok,
            "extra_removed": "io_write_fire" not in first,
        },
    }


def locked_source_check() -> dict[str, Any]:
    """Check Scala/reference hashes and the immutable XSTop extraction record."""

    if not SCALA.is_file() or not REFERENCE.is_file():
        raise FileNotFoundError("locked FauFTBWay source or closure is missing")
    scala_hash = sha256_file(SCALA)
    reference_hash = sha256_file(REFERENCE)
    index: dict[str, Any] = {}
    if REFERENCE_INDEX.is_file():
        index = json.loads(REFERENCE_INDEX.read_text(encoding="utf-8"))
    index_ref = index.get("reference", {}) if isinstance(index, dict) else {}
    return {
        "status": "PASS" if scala_hash == SOURCE_SHA256
        and reference_hash == REFERENCE_SHA256
        and index.get("source_commit") == SOURCE_COMMIT
        and index_ref.get("sha256") == REFERENCE_SHA256 else "FAIL",
        "scala_sha256": scala_hash,
        "expected_scala_sha256": SOURCE_SHA256,
        "reference_sha256": reference_hash,
        "expected_reference_sha256": REFERENCE_SHA256,
        "source_commit": SOURCE_COMMIT,
        "xstop": {
            "sha256": XSTOP_SHA256,
            "bytes": XSTOP_BYTES,
            "module": "FauFTBWay",
            "extraction_index": REFERENCE_INDEX.relative_to(ROOT).as_posix(),
            "line_start": index_ref.get("xstop_line_start"),
            "line_end": index_ref.get("xstop_line_end"),
        },
    }


def existing_behavior_evidence() -> dict[str, Any]:
    """Require the refreshed bounded direct and locked differential checks."""

    direct = json.loads(DIRECT_RESULT.read_text(encoding="utf-8"))
    differential = json.loads(DIFFERENTIAL_RESULT.read_text(encoding="utf-8"))
    comparison = differential.get("comparison", {})
    backend = differential.get("backend", {})
    backend_pass = all(
        backend.get(side, {}).get(tool, {}).get("status") == "PASS"
        for side in ("target", "reference")
        for tool in ("verilator", "yosys")
    )
    passed = (
        direct.get("status") == "DIRECT_PASS_BOUNDED"
        and differential.get("status") == "PENDING_COORDINATOR_REVIEW"
        and comparison.get("behavioral_equivalence") is True
        and backend_pass
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "direct": {
            "path": DIRECT_RESULT.relative_to(ROOT).as_posix(),
            "status": direct.get("status"),
            "vectors": direct.get("direct", {}).get("vectors"),
            "sha256": sha256_file(DIRECT_RESULT),
        },
        "differential": {
            "path": DIFFERENTIAL_RESULT.relative_to(ROOT).as_posix(),
            "status": differential.get("status"),
            "comparison": comparison.get("comparison"),
            "behavioral_equivalence": comparison.get("behavioral_equivalence"),
            "vectors": comparison.get("target_vectors"),
            "sha256": sha256_file(DIFFERENTIAL_RESULT),
        },
        "backend_pass": backend_pass,
    }


def materialize_equivalence(target_rtl: str) -> dict[str, Path]:
    """Write target/reference copies with distinct tops for ``equiv_make``."""

    WORK.mkdir(parents=True, exist_ok=True)
    target = WORK / "FauFTBWay-target.sv"
    reference = WORK / "FauFTBWay-reference.sv"
    target.write_text(target_rtl, encoding="utf-8", newline="\n")
    reference.write_text(
        REFERENCE.read_text(encoding="utf-8").replace(
            "module FauFTBWay(", "module FauFTBWay_ref(", 1
        ),
        encoding="utf-8",
        newline="\n",
    )
    return {"target": target, "reference": reference}


def formal_gates(paths: dict[str, Path]) -> dict[str, Any]:
    """Run lint and complete sequential equivalence with Yosys."""

    target = wsl_path(paths["target"])
    reference = wsl_path(paths["reference"])
    target_verilator = run_wsl([
        "verilator", "--lint-only", "-Wno-fatal", "--top-module", "FauFTBWay", target
    ])
    reference_verilator = run_wsl([
        "verilator", "--lint-only", "-Wno-fatal", "--top-module", "FauFTBWay_ref", reference
    ])
    target_yosys = run_wsl([
        "yosys", "-Q", "-p",
        f"read_verilog -sv {shlex.quote(target)}; proc; async2sync; opt; "
        "hierarchy -top FauFTBWay; check; stat",
    ])
    reference_yosys = run_wsl([
        "yosys", "-Q", "-p",
        f"read_verilog -sv {shlex.quote(reference)}; proc; async2sync; opt; "
        "hierarchy -top FauFTBWay_ref; check; stat",
    ])
    formal_script = (
        f"read_verilog -sv {shlex.quote(target)} {shlex.quote(reference)}; "
        "proc; async2sync; memory; opt; "
        "equiv_make FauFTBWay FauFTBWay_ref FauFTBWay_equiv; "
        "prep -top FauFTBWay_equiv; equiv_induct -undef; equiv_status -assert"
    )
    formal = run_wsl(["yosys", "-Q", "-p", formal_script])
    marker = "Equivalence successfully proven!"
    formal["formal_success_marker"] = marker in formal.get("output_tail", "")
    if not formal["formal_success_marker"]:
        formal["status"] = "FAIL"
    match = re.search(r"Found (\d+) \$equiv cells in [^:]+:", formal.get("output_tail", ""))
    formal["equiv_cells"] = int(match.group(1)) if match else None
    formal["formal_scope"] = {
        "clock": "posedge clock",
        "reset": "async reset normalized with async2sync; only valid is reset",
        "input_bits": INPUT_BITS,
        "inputs_unconstrained": INPUT_WIDTHS,
        "output_bits": OUTPUT_BITS,
        "outputs_compared": OUTPUT_WIDTHS,
        "architectural_state_bits": REFERENCE_STATE_BITS,
        "property": (
            "all matched output and state equivalence cells hold for every input "
            "sequence and every initial state under the normalized transition system"
        ),
    }
    return {
        "target_verilator": target_verilator,
        "reference_verilator": reference_verilator,
        "target_yosys": target_yosys,
        "reference_yosys": reference_yosys,
        "yosys_equiv": formal,
    }


def validate() -> dict[str, Any]:
    """Run strict gates and write evidence without optimistic promotion."""

    failures: list[str] = []
    lock: dict[str, Any] = {"status": "FAIL"}
    behavior: dict[str, Any] = {"status": "FAIL"}
    export: dict[str, Any] = {"status": "FAIL"}
    gates: dict[str, Any] = {}
    try:
        lock = locked_source_check()
        if lock["status"] != "PASS":
            failures.append("locked source/reference provenance")
        behavior = existing_behavior_evidence()
        if behavior["status"] != "PASS":
            failures.append("refreshed direct/differential evidence")
        module = load_target()
        py_compile.compile(str(TARGET), doraise=True)
        py_compile.compile(str(Path(__file__)), doraise=True)
        target_rtl, export = deterministic_export(module)
        gates = formal_gates(materialize_equivalence(target_rtl))
    except Exception as error:
        failures.append(f"exception: {type(error).__name__}: {error}")
    pyright = {
        "target": pyright_check(TARGET),
        "validator": pyright_check(Path(__file__)),
    }
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
        "build_id": "Build-Cpu.Frontend.Bpu.FauFTBWay",
        "validator": Path(__file__).relative_to(ROOT).as_posix(),
        "status": status,
        "strict_complete_eligible": status == "COMPLETE_EQUIVALENCE",
        "strict_complete_count_delta": 1 if status == "COMPLETE_EQUIVALENCE" else 0,
        "acceptance_eligible": status == "COMPLETE_EQUIVALENCE",
        "source_commit": SOURCE_COMMIT,
        "scope": {
            "kind": "sequential_registered_leaf",
            "configuration": "locked V2 FauFTBWay default widths",
            "state_bits": REFERENCE_STATE_BITS,
            "state_boundary": (
                "one posedge-clocked FTB entry; payload/tag reset-less; valid only "
                "has asynchronous reset"
            ),
            "inputs": INPUT_WIDTHS,
            "outputs_compared": OUTPUT_WIDTHS,
            "input_bits": INPUT_BITS,
            "output_bits": OUTPUT_BITS,
            "transition_relation": "all input sequences, posedge clock, async reset normalized by async2sync",
            "why_complete": (
                "Yosys equiv_make + equiv_induct -undef proves every matched state "
                "and ABI output cell; no bounded trace assumption is used."
            ),
            "bounded_tests_counted": False,
        },
        "reference_lock": lock,
        "sources": {
            "scala": {
                "path": SCALA.relative_to(ROOT).as_posix(),
                "sha256": sha256_file(SCALA),
                "bytes": SCALA.stat().st_size,
            },
            "reference_sv": {
                "path": REFERENCE.relative_to(ROOT).as_posix(),
                "sha256": sha256_file(REFERENCE),
                "bytes": REFERENCE.stat().st_size,
                "locked_module": "FauFTBWay",
            },
            "python_build": {
                "path": TARGET.relative_to(ROOT).as_posix(),
                "sha256": sha256_file(TARGET),
                "bytes": TARGET.stat().st_size,
            },
        },
        "checks": {
            "py_compile": {
                "status": "PASS" if not any(item.startswith("exception:") for item in failures) else "FAIL",
                "files": [
                    TARGET.relative_to(ROOT).as_posix(),
                    Path(__file__).relative_to(ROOT).as_posix(),
                ],
            },
            "pyright": pyright,
            "deterministic_export": export,
            "existing_behavior": behavior,
            "tools": tool_versions(),
            "formal": gates,
        },
        "failures": failures,
        "unclosed": [] if not failures else ["strict sequential equivalence gates did not all pass"],
    }
    EVIDENCE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return payload


def main() -> int:
    """Print strict status and return nonzero until every gate passes."""

    payload = validate()
    print(json.dumps({
        "status": payload["status"],
        "strict_complete_eligible": payload["strict_complete_eligible"],
        "failures": payload["failures"],
    }, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
