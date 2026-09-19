"""Complete formal equivalence validator for the locked V2 DeMultiplexer leaf.

The selected Build specialization is the ten-lane, 50-bit scalarized utility.
The locked XSTop instance uses the same geometry, with the source bundle
flattened as a 42-bit block address followed by an 8-bit set index.  The
generated target and the extracted ``DeMultiplexer_1`` closure are connected
through that packing boundary and compared on every observable output.
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
    "Build-Cpu.Frontend.Icache.Utils-Hardware.py"
)
SCALA = ROOT / "upstream/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala"
REFERENCE = ROOT / "validation/reference-closures/DeMultiplexer_1.sv"
REFERENCE_INDEX = ROOT / "validation/v2-p1-b-icache-reference-index.json"
DIRECT_RESULT = ROOT / "validation/v2-p1-b-icache-direct-results.json"
DIFFERENTIAL_RESULT = ROOT / "validation/v2-p1-b-icache-differential-results.json"
EVIDENCE = ROOT / "validation/v2-demultiplexer-formal-evidence.json"
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_demultiplexer_strict"

SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
SOURCE_SHA256 = "12489d704c86b65f6d4bc15e64b659bb2fa94f236eb93350d9dee012a22ba926"
XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
XSTOP_BYTES = 228590583
REFERENCE_SHA256 = "71f94459f54714ad7e4b37e5cd8a96cfd24ea2b1eec7a4ffbb0c6c2a1446e67d"

LANES = 10
PAYLOAD_WIDTH = 50
INPUT_WIDTHS = {
    "io_in_bits": PAYLOAD_WIDTH,
    "io_in_valid": 1,
    **{f"io_out_{index}_ready": 1 for index in range(LANES)},
}
OUTPUT_WIDTHS = {
    "io_in_ready": 1,
    "io_chosen": 4,
    **{f"io_out_{index}_valid": 1 for index in range(LANES)},
    **{f"io_out_{index}_bits": PAYLOAD_WIDTH for index in range(LANES)},
}
INPUT_BITS = sum(INPUT_WIDTHS.values())
OUTPUT_BITS = sum(OUTPUT_WIDTHS.values())


def sha256_file(path: Path) -> str:
    """Hash exact file bytes for reproducible provenance."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_target() -> Any:
    """Load the utility Build module by exact path."""

    spec = importlib.util.spec_from_file_location("strict_demultiplexer_target", TARGET)
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


def pyright_check(source: Path) -> dict[str, Any]:
    """Run Pyright on an ASCII temporary copy of one source file."""

    temporary = Path(tempfile.mkdtemp(prefix="uhsc_demultiplexer_pyright_"))
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


def tool_versions() -> dict[str, Any]:
    """Record exact formal-tool versions."""

    return {
        "verilator": run_wsl(["verilator", "--version"]),
        "yosys": run_wsl(["yosys", "--version"]),
    }


def deterministic_export(module: Any) -> tuple[str, dict[str, Any]]:
    """Export the locked n=10 specialization twice and audit its ABI."""

    configuration = {"module": "DeMultiplexer", "bits_width": PAYLOAD_WIDTH, "n": LANES}
    first = module.build_verilog(configuration, {})
    second = module.build_verilog(configuration, {})
    expected = {"io_in_bits", "io_in_valid", "io_in_ready", "io_chosen"}
    expected.update({f"io_out_{index}_{suffix}" for index in range(LANES) for suffix in ("ready", "valid", "bits")})
    header = first.split(";", 1)[0]
    observed = {name for name in expected if name in header}
    return first, {
        "status": "PASS" if first == second and observed == expected else "FAIL",
        "bytes": len(first.encode()),
        "sha256": hashlib.sha256(first.encode()).hexdigest(),
        "repeat_sha256": hashlib.sha256(second.encode()).hexdigest(),
        "byte_equal": first == second,
        "abi": {
            "expected_port_count": len(expected),
            "observed_port_count": len(observed),
            "exact_port_set": observed == expected,
            "configuration": configuration,
        },
    }


def lock_audit() -> dict[str, Any]:
    """Verify the immutable XSTop extraction and exact source closure hash."""

    checks: dict[str, bool] = {
        "scala_present": SCALA.is_file(),
        "scala_hash": SCALA.is_file() and sha256_file(SCALA) == SOURCE_SHA256,
        "reference_present": REFERENCE.is_file(),
        "reference_hash": REFERENCE.is_file() and sha256_file(REFERENCE) == REFERENCE_SHA256,
        "index_present": REFERENCE_INDEX.is_file(),
    }
    index: dict[str, Any] = {}
    if REFERENCE_INDEX.is_file():
        index = json.loads(REFERENCE_INDEX.read_text(encoding="utf-8"))
    module_record = next(
        (item for item in index.get("modules", []) if item.get("module") == "DeMultiplexer_1"),
        {},
    )
    checks.update({
        "index_source_commit": index.get("source_commit") == SOURCE_COMMIT,
        "index_xstop_hash": index.get("xstop", {}).get("sha256") == XSTOP_SHA256,
        "index_xstop_bytes": index.get("xstop", {}).get("bytes") == XSTOP_BYTES,
        "index_module_hash": module_record.get("sha256") == REFERENCE_SHA256,
        "index_module_path": module_record.get("path") == "validation/reference-closures/DeMultiplexer_1.sv",
        "index_extraction": index.get("extraction") == "PASS",
    })
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "source_commit": SOURCE_COMMIT,
        "scala_sha256": SOURCE_SHA256,
        "xstop": {
            "canonical_path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv",
            "sha256": XSTOP_SHA256,
            "bytes": XSTOP_BYTES,
        },
        "reference": {
            "path": REFERENCE.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(REFERENCE) if REFERENCE.is_file() else None,
            "locked_module": "DeMultiplexer_1",
            "packing": "target scalar [49:0] maps to locked blkPaddr[41:0] and vSetIdx[7:0]",
            "xstop_lines": [module_record.get("xstop_line_start"), module_record.get("xstop_line_end")],
        },
    }


def existing_behavior() -> dict[str, Any]:
    """Require the prior bounded direct/differential checks as supporting evidence."""

    try:
        direct = json.loads(DIRECT_RESULT.read_text(encoding="utf-8"))
        differential = json.loads(DIFFERENTIAL_RESULT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {"status": "FAIL", "error": repr(error)}
    comparison = next(
        (row for row in differential.get("comparisons", []) if row.get("name") == "demux10"),
        {},
    )
    passed = (
        direct.get("status") == "PASS_BOUNDED_DIRECT"
        and differential.get("v2_status") == "DIFFERENTIAL_MATCHED"
        and comparison.get("comparison") == "PASS"
        and comparison.get("behavioral_equivalence") is True
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "direct": {
            "path": DIRECT_RESULT.relative_to(ROOT).as_posix(),
            "status": direct.get("status"),
            "sha256": sha256_file(DIRECT_RESULT),
        },
        "differential": {
            "path": DIFFERENTIAL_RESULT.relative_to(ROOT).as_posix(),
            "status": differential.get("v2_status"),
            "comparison": comparison.get("comparison"),
            "behavioral_equivalence": comparison.get("behavioral_equivalence"),
            "vectors": comparison.get("target_vectors"),
            "sha256": sha256_file(DIFFERENTIAL_RESULT),
        },
    }


def miter_text() -> str:
    """Build a packed-ABI miter for the target and locked n=10 closure."""

    target_ready = "dut_in_ready"
    target_chosen = "dut_chosen"
    reference_ready = "ref_in_ready"
    reference_chosen = "ref_chosen"
    lines = [
        "module DeMultiplexer_MITER(",
        "  input [49:0] io_in_bits,",
        "  input io_in_valid,",
    ]
    lines.extend(f"  input io_out_{index}_ready," for index in range(LANES))
    lines.append("  output mismatch")
    lines.append(");")
    lines.extend([
        "  wire dut_in_ready, ref_in_ready;",
        "  wire [3:0] dut_chosen, ref_chosen;",
    ])
    for index in range(LANES):
        lines.extend([
            f"  wire dut_out_{index}_valid, ref_out_{index}_valid;",
            f"  wire [49:0] dut_out_{index}_bits;",
            f"  wire [41:0] ref_out_{index}_paddr;",
            f"  wire [7:0] ref_out_{index}_vset;",
        ])
    target_ports = [
        ".io_in_bits(io_in_bits)",
        *[f".io_out_{index}_ready(io_out_{index}_ready)" for index in range(LANES)],
        ".io_in_ready(dut_in_ready)",
        ".io_chosen(dut_chosen)",
        *[f".io_out_{index}_valid(dut_out_{index}_valid)" for index in range(LANES)],
        *[f".io_out_{index}_bits(dut_out_{index}_bits)" for index in range(LANES)],
        ".io_in_valid(io_in_valid)",
    ]
    lines.append("  DeMultiplexer target_i(")
    lines.append("    " + ", ".join(target_ports))
    lines.append("  );")
    reference_ports = [
        ".io_in_ready(ref_in_ready)",
        ".io_in_valid(io_in_valid)",
        ".io_in_bits_blkPaddr(io_in_bits[41:0])",
        ".io_in_bits_vSetIdx(io_in_bits[49:42])",
        *[f".io_out_{index}_ready(io_out_{index}_ready)" for index in range(LANES)],
        *[f".io_out_{index}_valid(ref_out_{index}_valid)" for index in range(LANES)],
        *[f".io_out_{index}_bits_blkPaddr(ref_out_{index}_paddr)" for index in range(LANES)],
        *[f".io_out_{index}_bits_vSetIdx(ref_out_{index}_vset)" for index in range(LANES)],
        ".io_chosen(ref_chosen)",
    ]
    lines.append("  DeMultiplexer_ref reference_i(")
    lines.append("    " + ", ".join(reference_ports))
    lines.append("  );")
    # Reduction-OR every vector difference before combining it with the
    # scalar mismatch terms.  A plain binary ``|`` here would truncate the
    # 4/50-bit expression when it is assigned to the one-bit mismatch port.
    mismatches = [f"(dut_in_ready ^ ref_in_ready)", f"(|(dut_chosen ^ ref_chosen))"]
    for index in range(LANES):
        mismatches.extend([
            f"(|(dut_out_{index}_valid ^ ref_out_{index}_valid))",
            f"(|(dut_out_{index}_bits ^ {{ref_out_{index}_vset, ref_out_{index}_paddr}}))",
        ])
    lines.append("  assign mismatch = " + " | ".join(mismatches) + ";")
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def materialize(target_rtl: str) -> dict[str, Path]:
    """Write target, renamed locked closure, and packed miter."""

    WORK.mkdir(parents=True, exist_ok=True)
    target = WORK / "UHSC_DeMultiplexer.sv"
    reference = WORK / "REF_DeMultiplexer.sv"
    miter = WORK / "DeMultiplexer_MITER.sv"
    target.write_text(target_rtl, encoding="utf-8", newline="\n")
    reference.write_text(
        REFERENCE.read_text(encoding="utf-8").replace(
            "module DeMultiplexer_1(", "module DeMultiplexer_ref(", 1
        ),
        encoding="utf-8",
        newline="\n",
    )
    miter.write_text(miter_text(), encoding="utf-8", newline="\n")
    return {"target": target, "reference": reference, "miter": miter}


def formal_gates(paths: dict[str, Path]) -> dict[str, Any]:
    """Run Verilator/Yosys lint and unrestricted SAT equivalence."""

    target = wsl_path(paths["target"])
    reference = wsl_path(paths["reference"])
    miter = wsl_path(paths["miter"])
    verilator = run_wsl([
        "verilator", "--lint-only", "-Wno-fatal", "--top-module", "DeMultiplexer_MITER",
        target, reference, miter,
    ])
    target_yosys = run_wsl([
        "yosys", "-Q", "-p",
        f"read_verilog -sv {shlex.quote(target)}; hierarchy -top DeMultiplexer; proc; opt; check",
    ])
    reference_yosys = run_wsl([
        "yosys", "-Q", "-p",
        f"read_verilog -sv {shlex.quote(reference)}; hierarchy -top DeMultiplexer_ref; proc; opt; check",
    ])
    proof = run_wsl([
        "yosys", "-Q", "-p",
        f"read_verilog -sv {shlex.quote(target)} {shlex.quote(reference)} {shlex.quote(miter)}; "
        "prep -top DeMultiplexer_MITER; flatten; opt; sat -prove mismatch 0",
    ])
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
        "outputs_compared": OUTPUT_WIDTHS,
        "output_bits": OUTPUT_BITS,
        "property": "mismatch == 0 for every 2-state valuation of all packed n=10 inputs",
    }
    return {
        "verilator": verilator,
        "yosys_target": target_yosys,
        "yosys_reference": reference_yosys,
        "yosys_formal_miter": proof,
    }


def validate() -> dict[str, Any]:
    """Run every strict gate and persist machine-readable evidence."""

    failures: list[str] = []
    lock = lock_audit()
    if lock["status"] != "PASS":
        failures.append("locked source/reference provenance")
    behavior = existing_behavior()
    if behavior["status"] != "PASS":
        failures.append("refreshed direct/differential evidence")
    export: dict[str, Any] = {"status": "FAIL"}
    gates: dict[str, Any] = {}
    try:
        module = load_target()
        py_compile.compile(str(TARGET), doraise=True)
        py_compile.compile(str(Path(__file__)), doraise=True)
        target_rtl, export = deterministic_export(module)
        gates = formal_gates(materialize(target_rtl))
    except Exception as error:
        failures.append(f"exception: {type(error).__name__}: {error}")
    pyright = {"target": pyright_check(TARGET), "validator": pyright_check(Path(__file__))}
    if export.get("status") != "PASS":
        failures.append("deterministic export/ABI")
    for name, result in pyright.items():
        if result["status"] != "PASS":
            failures.append(f"pyright {name}")
    for name, result in gates.items():
        if result.get("status") != "PASS":
            failures.append(name)
    status = ("COMPLETE_EQUIVALENCE_VARIANT_ONLY" if not failures
              else "STRICT_PENDING")
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_STRICT_COMPLETE_EQUIVALENCE",
        "build_id": "Build-Cpu.Frontend.Icache.Utils.DeMultiplexer-n10",
        "validator": Path(__file__).relative_to(ROOT).as_posix(),
        "status": status,
        "strict_complete_eligible": False,
        "strict_complete_count_delta": 0,
        "acceptance_eligible": False,
        "variant_only_reason": (
            "This SAT miter closes the DeMultiplexer n=10/bits_width=50 specialization only. "
            "The target Build parameterizes DeMultiplexer and additionally serves MuxBundle "
            "and FIFOReg, which is its default export, so one configuration cannot complete it."
        ),
        "uncovered_public_variants": [
            "DeMultiplexer(n!=10 or bits_width!=50)",
            "DeMultiplexer default n=4 export",
            "MuxBundle(bits_width,n)",
            "FIFOReg(bits_width,entries,pipe,has_flush)",
        ],
        "source_commit": SOURCE_COMMIT,
        "scope": {
            "kind": "stateless_combinational_leaf",
            "configuration": "DeMultiplexer, n=10, scalar payload width=50",
            "packing": "io_*_bits[41:0]=blkPaddr; io_*_bits[49:42]=vSetIdx",
            "state_bits": 0,
            "state_boundary": "no clock/reset/register/memory; one combinational evaluation",
            "inputs": INPUT_WIDTHS,
            "outputs_compared": OUTPUT_WIDTHS,
            "input_bits": INPUT_BITS,
            "output_bits": OUTPUT_BITS,
            "input_space": f"2**{INPUT_BITS}",
            "input_space_cardinality": str(1 << INPUT_BITS),
            "why_complete": (
                "Yosys SAT proves the packed miter mismatch is zero with all 61 input bits "
                "unconstrained; all ten valid lanes, payload lanes, ready, and chosen are compared."
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
                "locked_module": "DeMultiplexer_1",
                "reference_index": REFERENCE_INDEX.relative_to(ROOT).as_posix(),
            },
            "python_build": {
                "path": TARGET.relative_to(ROOT).as_posix(),
                "sha256": sha256_file(TARGET),
                "bytes": TARGET.stat().st_size,
            },
        },
        "checks": {
            "py_compile": {"status": "PASS" if not any(item.startswith("exception:") for item in failures) else "FAIL"},
            "pyright": pyright,
            "deterministic_export": export,
            "existing_behavior": behavior,
            "tools": tool_versions(),
            "formal": gates,
        },
        "failures": failures,
        "unclosed": [] if not failures else ["strict gates did not all pass"],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return payload


def main() -> int:
    """Print formal status and return nonzero until the configuration proof closes."""

    payload = validate()
    print(json.dumps({
        "status": payload["status"],
        "strict_complete_eligible": payload["strict_complete_eligible"],
        "failures": payload["failures"],
    }, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE_VARIANT_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
