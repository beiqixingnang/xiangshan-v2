"""Complete formal equivalence validator for the locked V2 CSA3_2 leaf.

The selected Build is the one-bit CSA3_2 specialization emitted in the locked
V2 XSTop hierarchy.  It is stateless and combinational: all three one-bit
inputs are left unconstrained in a Yosys SAT miter and both output bits are
compared.  A successful proof therefore covers all eight input valuations,
not merely the bounded vectors used by the older differential harness.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import py_compile
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
    "Build-Cpu.Backend.Fu.Util.CSA-Hardware.py"
)
SCALA = ROOT / "upstream/src/main/scala/xiangshan/backend/fu/util/CSA.scala"
# Tracked closure extracted from the locked V2 XSTop module.  The ignored
# reference-sv/CSA3_2.sv is checked when present as an independent extraction.
REFERENCE = ROOT / "validation/reference-closures/CSA3_2-v2.sv"
EXTRACTED_REFERENCE = ROOT / "validation/reference-sv/CSA3_2.sv"
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_csa_strict"
# This proof closes the one-bit CSA3_2 specialization only.  The Build file
# exposes additional CSA classes/widths, so the evidence deliberately avoids
# the coordinator's Build-level ``*-strict-evidence.json`` completion glob.
EVIDENCE = ROOT / "validation/v2-csa3_2-formal-evidence.json"

INPUT_WIDTHS = {"io_in_0": 1, "io_in_1": 1, "io_in_2": 1}
OUTPUT_WIDTHS = {"io_out_0": 1, "io_out_1": 1}
INPUT_BITS = sum(INPUT_WIDTHS.values())

SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
REFERENCE_XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
REFERENCE_XSTOP_BYTES = 228590583
EXPECTED_SCALA_SHA256 = "b41fce188f098caacb7c4825e9ae622b7a535dc35a3945f09a37eea812954df3"
EXPECTED_REFERENCE_SHA256 = "a0bee4720d459f9382a8323442e8b7d2eb962fc3a80f0fd0c2b75dc876f74a21"


def sha256_file(path: Path) -> str:
    """Hash exact file bytes for source/artifact provenance."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_target() -> Any:
    """Load only the selected Build module by exact path."""

    spec = importlib.util.spec_from_file_location("strict_csa_target", TARGET)
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
    """Run one WSL command and retain stable diagnostics."""

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
        "output_tail": output[-4000:],
        "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
    }


def tool_versions() -> dict[str, Any]:
    """Record the exact Verilator/Yosys binaries used by the proof."""

    return {
        "verilator": run_wsl(["verilator", "--version"]),
        "yosys": run_wsl(["yosys", "--version"]),
    }


def pyright_check(source: Path) -> dict[str, Any]:
    """Run Pyright on an ASCII temporary copy of one source file."""

    temporary = Path(tempfile.mkdtemp(prefix="uhsc_csa_pyright_"))
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


def deterministic_export(module: Any) -> tuple[str, dict[str, Any]]:
    """Generate the exact one-bit target RTL twice and require byte identity."""

    configuration = module.CSAConfig(length=1)
    first = module.build_verilog(configuration, {})
    second = module.build_verilog(configuration, {})
    first_bytes = first.encode("utf-8")
    second_bytes = second.encode("utf-8")
    return first, {
        "status": "PASS" if first_bytes == second_bytes else "FAIL",
        "configuration": {"length": 1},
        "bytes": len(first_bytes),
        "sha256": hashlib.sha256(first_bytes).hexdigest(),
        "repeat_sha256": hashlib.sha256(second_bytes).hexdigest(),
        "byte_equal": first_bytes == second_bytes,
    }


def reference_lock() -> dict[str, Any]:
    """Validate the locked Scala/reference closure and its provenance."""

    if not SCALA.is_file():
        raise FileNotFoundError(f"locked Scala source missing: {SCALA}")
    if not REFERENCE.is_file():
        raise FileNotFoundError(f"locked reference closure missing: {REFERENCE}")
    scala_hash = sha256_file(SCALA)
    reference_hash = sha256_file(REFERENCE)
    reference_text = REFERENCE.read_text(encoding="utf-8")
    required_markers = (
        "module CSA3_2(",
        "input  io_in_0",
        "io_in_1",
        "io_in_2",
        "output io_out_0",
        "io_out_1",
        "endmodule",
    )
    markers_ok = all(marker in reference_text for marker in required_markers)
    extracted_match: bool | None = None
    extracted_hash: str | None = None
    if EXTRACTED_REFERENCE.is_file():
        extracted_hash = sha256_file(EXTRACTED_REFERENCE)
        extracted_match = EXTRACTED_REFERENCE.read_bytes() == REFERENCE.read_bytes()
    return {
        "status": "PASS" if scala_hash == EXPECTED_SCALA_SHA256
        and reference_hash == EXPECTED_REFERENCE_SHA256 and markers_ok
        and extracted_match in (True, None) else "FAIL",
        "scala_sha256": scala_hash,
        "expected_scala_sha256": EXPECTED_SCALA_SHA256,
        "reference_sha256": reference_hash,
        "expected_reference_sha256": EXPECTED_REFERENCE_SHA256,
        "reference_module": "CSA3_2",
        "interface": {
            "inputs": INPUT_WIDTHS,
            "outputs": OUTPUT_WIDTHS,
            "markers_present": markers_ok,
        },
        "extracted_reference": {
            "path": EXTRACTED_REFERENCE.relative_to(ROOT).as_posix(),
            "present": extracted_match is not None,
            "sha256": extracted_hash,
            "byte_equal": extracted_match,
        },
        "source_authority": (
            "upstream/src/main/scala/xiangshan/backend/fu/util/CSA.scala "
            f"at locked kunminghu-v2 commit {SOURCE_COMMIT}"
        ),
        "xstop_lock": {
            "sha256": REFERENCE_XSTOP_SHA256,
            "bytes": REFERENCE_XSTOP_BYTES,
            "module_extraction": "CSA3_2 one-bit leaf from locked V2 XSTop.sv",
        },
    }


def materialize_miter(target_rtl: str) -> dict[str, Path]:
    """Write renamed reference, target, and all-output miter sources."""

    reference_text = REFERENCE.read_text(encoding="utf-8")
    marker = "module CSA3_2("
    if marker not in target_rtl or marker not in reference_text:
        raise AssertionError("CSA3_2 module declaration missing")
    WORK.mkdir(parents=True, exist_ok=True)
    target = WORK / "UHSC_CSA3_2.sv"
    reference = WORK / "REF_CSA3_2.sv"
    miter = WORK / "CSA3_2_MITER.sv"
    target.write_text(target_rtl.replace(marker, "module UHSC_CSA3_2(", 1),
                      encoding="utf-8", newline="\n")
    reference.write_text(reference_text.replace(marker, "module REF_CSA3_2(", 1),
                          encoding="utf-8", newline="\n")
    miter.write_text(
        """module CSA3_2_MITER(
  input io_in_0,
  input io_in_1,
  input io_in_2,
  output mismatch
);
  wire ref_out_0;
  wire ref_out_1;
  wire dut_out_0;
  wire dut_out_1;
  REF_CSA3_2 reference_i(
    .io_in_0(io_in_0), .io_in_1(io_in_1), .io_in_2(io_in_2),
    .io_out_0(ref_out_0), .io_out_1(ref_out_1));
  UHSC_CSA3_2 target_i(
    .io_in_0(io_in_0), .io_in_1(io_in_1), .io_in_2(io_in_2),
    .io_out_0(dut_out_0), .io_out_1(dut_out_1));
  assign mismatch = (ref_out_0 != dut_out_0) || (ref_out_1 != dut_out_1);
endmodule
""",
        encoding="utf-8",
        newline="\n",
    )
    return {"target": target, "reference": reference, "miter": miter}


def formal_gates(paths: dict[str, Path]) -> dict[str, Any]:
    """Run Verilator/Yosys lint and an unrestricted all-output SAT proof."""

    converted = {name: wsl_path(path) for name, path in paths.items()}
    target, reference, miter = (
        converted["target"], converted["reference"], converted["miter"]
    )
    verilator = run_wsl([
        "verilator", "--lint-only", "-Wno-fatal", "--top-module",
        "CSA3_2_MITER", target, reference, miter,
    ])
    target_yosys = run_wsl([
        "yosys", "-Q", "-p",
        f"read_verilog -sv {shlex.quote(target)}; "
        "hierarchy -top UHSC_CSA3_2; proc; opt; check",
    ])
    reference_yosys = run_wsl([
        "yosys", "-Q", "-p",
        f"read_verilog -sv {shlex.quote(reference)}; "
        "hierarchy -top REF_CSA3_2; proc; opt; check",
    ])
    proof_script = (
        f"read_verilog -sv {shlex.quote(target)} {shlex.quote(reference)} "
        f"{shlex.quote(miter)}; prep -top CSA3_2_MITER; flatten; opt; "
        "sat -prove mismatch 0"
    )
    proof = run_wsl(["yosys", "-Q", "-p", proof_script])
    marker = "SAT proof finished - no model found: SUCCESS!"
    proof["formal_success_marker"] = marker in proof.get("output_tail", "")
    if not proof["formal_success_marker"]:
        proof["status"] = "FAIL"
    proof["formal_scope"] = {
        "input_bits": INPUT_BITS,
        "input_space": f"2**{INPUT_BITS}",
        "input_space_cardinality": str(1 << INPUT_BITS),
        "state_bits": 0,
        "state_space": "singleton (stateless combinational module)",
        "property": (
            "mismatch == 0 for every 2-state valuation of io_in_0/io_in_1/io_in_2"
        ),
        "outputs_compared": OUTPUT_WIDTHS,
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
    module: Any | None = None
    target_rtl = ""
    export: dict[str, Any] = {"status": "FAIL"}
    gates: dict[str, Any] = {}
    lock: dict[str, Any] = {"status": "FAIL"}
    try:
        lock = reference_lock()
        if lock["status"] != "PASS":
            failures.append("locked Scala/reference provenance")
        module = load_target()
        py_compile.compile(str(TARGET), doraise=True)
        py_compile.compile(str(Path(__file__)), doraise=True)
        target_rtl, export = deterministic_export(module)
        gates = formal_gates(materialize_miter(target_rtl))
    except Exception as error:  # Keep a failure evidence record for diagnosis.
        failures.append(f"exception: {type(error).__name__}: {error}")
    pyright = {
        "target": pyright_check(TARGET),
        "validator": pyright_check(Path(__file__)),
    }
    if export.get("status") != "PASS":
        failures.append("deterministic export mismatch")
    for name, result in pyright.items():
        if result["status"] != "PASS":
            failures.append(f"pyright {name}")
    for name, result in gates.items():
        if result.get("status") != "PASS":
            failures.append(name)
    formal = gates.get("yosys_formal_miter", {})
    if not formal.get("formal_success_marker", False):
        if "yosys_formal_miter" not in failures:
            failures.append("formal SAT proof")
    proof_pass = not failures
    status = "COMPLETE_EQUIVALENCE_VARIANT_ONLY" if proof_pass else "STRICT_PENDING"
    uncovered_variants = [
        "CSA2_2(length=any)",
        "CSA3_2(length!=1)",
        "CSA5_3(length=any)",
        "C22(length=1 alias)",
        "C32(length=1 alias)",
        "C53(length=1 alias)",
        "csa2_2/csa3_2/csa5_3 integer helper outputs",
    ]
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_STRICT_COMPLETE_EQUIVALENCE",
        "build_id": "Build-Cpu.Backend.Fu.Util.CSA.CSA3_2",
        "validator": Path(__file__).relative_to(ROOT).as_posix(),
        "status": status,
        "strict_complete_eligible": False,
        "strict_complete_count_delta": 0,
        "acceptance_eligible": False,
        "variant_only_reason": (
            "SAT closes only CSA3_2(length=1), while this Build exports multiple "
            "public CSA classes and configurable widths."
        ),
        "uncovered_public_variants": uncovered_variants,
        "source_commit": SOURCE_COMMIT,
        "scope": {
            "kind": "stateless_combinational_leaf",
            "configuration": "CSAConfig(length=1), locked V2 CSA3_2 specialization",
            "state_bits": 0,
            "state_boundary": "no clock/reset/register/memory; one combinational evaluation",
            "inputs": INPUT_WIDTHS,
            "outputs_compared": OUTPUT_WIDTHS,
            "input_bits": INPUT_BITS,
            "input_space": f"2**{INPUT_BITS}",
            "input_space_cardinality": str(1 << INPUT_BITS),
            "why_complete": (
                "Yosys SAT proves the all-output miter mismatch is zero with all "
                "three input bits unconstrained; no temporal state exists."
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
                "locked_module": "CSA3_2",
            },
            "python_build": {
                "path": TARGET.relative_to(ROOT).as_posix(),
                "sha256": sha256_file(TARGET),
                "bytes": TARGET.stat().st_size,
            },
        },
        "checks": {
            "py_compile": {
                "status": "PASS" if not any(item.startswith("exception:") for item in failures)
                else "FAIL",
                "files": [
                    TARGET.relative_to(ROOT).as_posix(),
                    Path(__file__).relative_to(ROOT).as_posix(),
                ],
            },
            "pyright": pyright,
            "deterministic_export": export,
            "tools": tool_versions(),
            "formal": gates,
        },
        "failures": failures,
        "unclosed": uncovered_variants + ([] if not failures else ["strict gates did not all pass"]),
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
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE_VARIANT_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
