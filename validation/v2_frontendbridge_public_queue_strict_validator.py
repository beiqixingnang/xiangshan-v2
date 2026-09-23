"""Audit FrontendBridge through public-output queue wrappers.

The general strict family rail flattens the V2 FrontendBridge before it calls
``equiv_make``.  Its RAM-backed Chisel queues and the Python count/data queues
then expose differently named internal state to the matcher.  That is useful
for an implementation-state proof, but it is not an ABI proof and it made the
result hard to diagnose.  This focused rail creates wrappers first, calls
``equiv_make`` while each wrapper exposes only public outputs, and only then
flattens the pair for sequential reasoning.

The six queue partitions are diagnostic views of the three public TileLink
edges.  A seventh wrapper covers every public output, so a passing result can
only be considered for strict promotion when the full ABI, locked view,
full-output proof, and both wrapper-output mutations all meet the existing
strict policy.  It never edits the Build, locked reference, shared rail, or
strict-progress ledger.
"""

from __future__ import annotations

import hashlib
import json
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/"
    "Build-Cpu.Memory.FrontendBridge-Hardware.py"
)
DIRECT_TEST = ROOT / (
    "python/Program-System/System-Testing/Testing-Cpu/"
    "Testing-Cpu.Memory.FrontendBridge-Hardware.py"
)
EVIDENCE = ROOT / "validation/v2-frontendbridge-public-queue-strict-results.json"
MODULE = "FrontendBridge"
FORMAL_PARTITION = "instr_uncache_a"
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_frontendbridge_public_queue_strict"

if str(ROOT / "validation") not in sys.path:
    sys.path.insert(0, str(ROOT / "validation"))
import v2_strict_family_rail as rail  # noqa: E402


def sha256_text(text: str) -> str:
    """Return the SHA-256 digest of deterministic generated text."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def queue_partitions(outputs: dict[str, int]) -> dict[str, tuple[str, ...]]:
    """Split every public output into the A or D queue it observes."""

    prefixes = (
        ("instr_uncache", "auto_instr_uncache_"),
        ("icachectrl", "auto_icachectrl_"),
        ("icache", "auto_icache_"),
    )
    selected: dict[str, list[str]] = {
        f"{edge}_{channel}": []
        for edge, _prefix in prefixes
        for channel in ("a", "d")
    }
    unmatched: list[str] = []
    for port in outputs:
        matching = next(((edge, prefix) for edge, prefix in prefixes if port.startswith(prefix)), None)
        if matching is None:
            unmatched.append(port)
            continue
        edge, _prefix = matching
        if "_in_a_" in port or "_out_a_" in port:
            selected[f"{edge}_a"].append(port)
        elif "_in_d_" in port or "_out_d_" in port:
            selected[f"{edge}_d"].append(port)
        else:
            unmatched.append(port)
    duplicates = [port for port in outputs if sum(port in values for values in selected.values()) != 1]
    if unmatched or duplicates or any(not values for values in selected.values()):
        raise AssertionError({"unmatched": unmatched, "duplicates": duplicates, "partitions": selected})
    return {name: tuple(values) for name, values in selected.items()}


def signal_declaration(direction: str, port: str, width: int) -> str:
    """Return one ANSI SystemVerilog port declaration."""

    if width == 1:
        return f"  {direction} {port}"
    return f"  {direction} [{width - 1}:0] {port}"


def wrapper_text(
    name: str,
    inner: str,
    inputs: dict[str, int],
    outputs: dict[str, int],
    selected: tuple[str, ...],
) -> str:
    """Expose all inputs and exactly one public-output queue partition.

    Unselected output ports are deliberately left unconnected at ``inner_i``.
    The wrapper has no access to queue registers, RAM ports, or child signals.
    """

    lines = [f"module {name}("]
    ports = [signal_declaration("input", port, width) for port, width in inputs.items()]
    ports.extend(signal_declaration("output", port, outputs[port]) for port in selected)
    lines.extend([",\n".join(ports), ");"])
    for port in selected:
        width = outputs[port]
        lines.append(f"  wire [{width - 1}:0] _out_{port};" if width > 1 else f"  wire _out_{port};")
    connections = [f".{port}({port})" for port in inputs]
    connections.extend(f".{port}(_out_{port})" for port in selected)
    lines.extend([f"  {inner} inner_i(", "    " + ", ".join(connections), "  );"])
    lines.extend(f"  assign {port} = _out_{port};" for port in selected)
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def static_wrapper_record(
    name: str,
    source: str,
    inputs: dict[str, int],
    outputs: dict[str, int],
    selected: tuple[str, ...],
) -> dict[str, Any]:
    """Check that a wrapper's public ABI and connections are exact before tools run."""

    declared = rail.declared_ports(source, name)
    expected = {port: ("input", width) for port, width in inputs.items()}
    expected.update({port: ("output", outputs[port]) for port in selected})
    selected_set = set(selected)
    connected_inputs = all(source.count(f".{port}({port})") == 1 for port in inputs)
    connected_outputs = all(source.count(f".{port}(_out_{port})") == 1 for port in selected)
    omitted_outputs = all(f".{port}(" not in source for port in outputs if port not in selected_set)
    direct_assignments = all(
        re.search(rf"^\s*assign\s+{re.escape(port)}\s*=\s*_out_{re.escape(port)};\s*$", source, re.MULTILINE)
        is not None
        for port in selected
    )
    output_bits = sum(outputs[port] for port in selected)
    passed = declared == expected and connected_inputs and connected_outputs and omitted_outputs and direct_assignments
    return {
        "status": "PASS" if passed else "FAIL",
        "wrapper": name,
        "input_count": len(inputs),
        "selected_output_count": len(selected),
        "selected_output_bits": output_bits,
        "declared_abi_exact": declared == expected,
        "all_inputs_connected": connected_inputs,
        "selected_outputs_connected": connected_outputs,
        "unselected_outputs_unconnected": omitted_outputs,
        "direct_output_assignments": direct_assignments,
        "sha256": sha256_text(source),
        "bytes": len(source.encode("utf-8")),
    }


def formal_script(
    reference_wrapper: Path,
    target_wrapper: Path,
    reference_source: Path,
    target_source: Path,
    equiv_name: str,
) -> str:
    """Return an output-only, same-clock sequential equivalence proof script."""

    paths = (target_source, reference_source, reference_wrapper, target_wrapper)
    source_paths = " ".join(rail.wsl_path(path) for path in paths)
    # ``equiv_make`` intentionally precedes flattening.  At that point the
    # wrapper has only public outputs, so no differently represented queue
    # pointers, RAM data, or Amaranth count registers become proof obligations.
    return (
        f"read_verilog -sv {source_paths}; proc; async2sync; memory; opt; "
        f"equiv_make {reference_wrapper.stem} {target_wrapper.stem} {equiv_name}; "
        f"prep -top {equiv_name}; flatten; opt; "
        "equiv_induct -undef; equiv_status -assert"
    )


def extract_proof_counts(proof: dict[str, Any], expected_bits: int) -> None:
    """Normalize shared-rail output and assert the public-obligation count."""

    markers = proof.get("equiv_success_markers", {})
    proof["formal_success_marker"] = all(markers.values())
    if isinstance(proof.get("equiv_cells_full"), int):
        proof["equiv_cells"] = proof["equiv_cells_full"]
    summary = proof.get("equiv_summary_full")
    if isinstance(summary, list) and len(summary) == 2:
        proof["proven_cells"], proof["unproven_cells"] = summary
    if isinstance(proof.get("equiv_failed_full"), int):
        proof["unproven_cells"] = proof["equiv_failed_full"]
    proof["expected_public_output_bits"] = expected_bits
    proof["output_only_obligations"] = proof.get("equiv_cells") == expected_bits
    proof["status"] = (
        "PASS"
        if proof.get("returncode") == 0
        and proof.get("formal_success_marker") is True
        and proof.get("output_only_obligations") is True
        else "FAIL"
    )


def run_partition(
    label: str,
    selected: tuple[str, ...],
    inputs: dict[str, int],
    outputs: dict[str, int],
    target_source: Path,
    reference_source: Path,
    formal: bool,
) -> dict[str, Any]:
    """Generate, statically audit, lint, and optionally prove one queue view."""

    reference_name = f"REF_FrontendBridge_Public_{label}"
    target_name = f"DUT_FrontendBridge_Public_{label}"
    reference_text = wrapper_text(reference_name, "REF_FrontendBridge", inputs, outputs, selected)
    target_text = wrapper_text(target_name, "DUT_FrontendBridge", inputs, outputs, selected)
    reference_wrapper = WORK / f"{reference_name}.sv"
    target_wrapper = WORK / f"{target_name}.sv"
    reference_wrapper.write_text(reference_text, encoding="utf-8", newline="\n")
    target_wrapper.write_text(target_text, encoding="utf-8", newline="\n")
    static = {
        "reference": static_wrapper_record(reference_name, reference_text, inputs, outputs, selected),
        "target": static_wrapper_record(target_name, target_text, inputs, outputs, selected),
    }
    lint_reference = rail.run_wsl([
        "verilator", "--lint-only", "-Wno-fatal", "--top-module", reference_name,
        rail.wsl_path(reference_source), rail.wsl_path(reference_wrapper),
    ])
    lint_target = rail.run_wsl([
        "verilator", "--lint-only", "-Wno-fatal", "--top-module", target_name,
        rail.wsl_path(target_source), rail.wsl_path(target_wrapper),
    ])
    expected_bits = sum(outputs[port] for port in selected)
    proof: dict[str, Any]
    if formal:
        script = formal_script(
            reference_wrapper,
            target_wrapper,
            reference_source,
            target_source,
            f"FrontendBridge_{label}_EQUIV",
        )
        proof = rail.run_wsl(["yosys", "-Q", "-p", script])
        extract_proof_counts(proof, expected_bits)
        proof["script_sha256"] = sha256_text(script)
    else:
        proof = {
            "status": "NOT_RUN",
            "expected_public_output_bits": expected_bits,
            "output_only_obligations": None,
            "note": "static wrappers were generated before optional WSL formal",
        }
    status = (
        "PASS"
        if all(record["status"] == "PASS" for record in static.values())
        and lint_reference.get("status") == "PASS"
        and lint_target.get("status") == "PASS"
        and proof.get("status") == "PASS"
        else "STRICT_PENDING"
    )
    return {
        "partition": label,
        "outputs": {port: outputs[port] for port in selected},
        "output_bits": expected_bits,
        "static_wrappers": static,
        "verilator": {"reference": lint_reference, "target": lint_target},
        "yosys_equiv": proof,
        "status": status,
    }


def mutate_wrapper_output(source: str, selected: tuple[str, ...]) -> tuple[str, str]:
    """Invert one known wrapper assignment without touching a locked source."""

    port = selected[0]
    pattern = rf"assign\s+{re.escape(port)}\s*=\s*_out_{re.escape(port)};"
    mutated, count = re.subn(pattern, f"assign {port} = ~_out_{port};", source, count=1)
    if count != 1:
        raise AssertionError(f"cannot mutate wrapper output {port}")
    return mutated, port


def wrapper_negative_control(
    selected: tuple[str, ...],
    label: str,
    inputs: dict[str, int],
    outputs: dict[str, int],
    target_source: Path,
    reference_source: Path,
    formal: bool,
) -> dict[str, Any]:
    """Mutate one generated queue-wrapper output on both comparison sides."""

    cases: dict[str, Any] = {}
    for side in ("target", "reference"):
        reference_name = f"REF_FrontendBridge_Negative_{side}"
        target_name = f"DUT_FrontendBridge_Negative_{side}"
        reference_text = wrapper_text(reference_name, "REF_FrontendBridge", inputs, outputs, selected)
        target_text = wrapper_text(target_name, "DUT_FrontendBridge", inputs, outputs, selected)
        if side == "target":
            target_text, port = mutate_wrapper_output(target_text, selected)
        else:
            reference_text, port = mutate_wrapper_output(reference_text, selected)
        reference_wrapper = WORK / f"{reference_name}.sv"
        target_wrapper = WORK / f"{target_name}.sv"
        reference_wrapper.write_text(reference_text, encoding="utf-8", newline="\n")
        target_wrapper.write_text(target_text, encoding="utf-8", newline="\n")
        static = {
            "reference": static_wrapper_record(reference_name, reference_text, inputs, outputs, selected),
            "target": static_wrapper_record(target_name, target_text, inputs, outputs, selected),
        }
        if not formal:
            cases[side] = {
                "status": "NOT_RUN",
                "mutation_applied": True,
                "control_port": port,
                "static_wrappers": static,
            }
            continue
        script = formal_script(
            reference_wrapper,
            target_wrapper,
            reference_source,
            target_source,
            f"FrontendBridge_{side}_WRAPPER_NEGATIVE_EQUIV",
        )
        result = rail.run_wsl(["yosys", "-Q", "-p", script])
        markers = result.get("equiv_success_markers", {})
        explicit_failure = result.get("equiv_failure_marker") is True
        still_success = all(markers.values())
        process_ran = isinstance(result.get("returncode"), int) and result.get("timed_out") is not True
        detected = process_ran and explicit_failure and not still_success
        cases[side] = {
            "status": "PASS" if detected else "FAIL",
            "mutation_applied": True,
            "control_port": port,
            "explicit_failure_marker": explicit_failure,
            "success_marker_still_present": still_success,
            "returncode": result.get("returncode"),
            "output_tail": result.get("output_tail", "")[-1200:],
            "static_wrappers": static,
            "script_sha256": sha256_text(script),
        }
    detected = bool(cases) and all(case["status"] == "PASS" for case in cases.values())
    return {
        "status": "PASS" if detected else "FAIL",
        "partition": label,
        "cases": cases,
        "note": "Both mutations alter a generated wrapper assignment; no locked reference text is edited.",
    }


def direct_test() -> dict[str, Any]:
    """Run the Build's existing direct test without modifying its source."""

    try:
        result = subprocess.run(
            [sys.executable, str(DIRECT_TEST), "-q"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=180,
        )
    except subprocess.TimeoutExpired as error:
        return {"status": "FAIL_TIMEOUT", "returncode": None, "output_tail": str(error)}
    output = result.stdout + result.stderr
    return {
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "returncode": result.returncode,
        "output_tail": output[-1600:],
        "sha256": sha256_text(output),
    }


def main() -> int:
    """Write static and optional sequential public-queue strict evidence."""

    formal = "--formal" in sys.argv[1:]
    py_compile.compile(str(BUILD), doraise=True)
    py_compile.compile(str(DIRECT_TEST), doraise=True)
    py_compile.compile(str(Path(__file__)), doraise=True)
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)

    module = rail.load_module("frontendbridge_public_queue_validator", BUILD)
    family = rail.FamilyRail(BUILD, "Build-Cpu.Memory.FrontendBridge.PublicQueue", EVIDENCE)
    shutil.rmtree(family.work, ignore_errors=True)
    family.work.mkdir(parents=True, exist_ok=True)
    item = family.prepare(module, MODULE)
    target_source = WORK / "DUT_FrontendBridge.sv"
    reference_source = WORK / "REF_FrontendBridge.sv"
    shutil.copyfile(item["target"], target_source)
    shutil.copyfile(item["reference"], reference_source)

    inputs = item["inputs"]
    outputs = item["outputs"]
    partitions = queue_partitions(outputs)
    full_selected = tuple(outputs)
    records = [
        run_partition(
            label,
            selected,
            inputs,
            outputs,
            target_source,
            reference_source,
            formal and label == FORMAL_PARTITION,
        )
        for label, selected in partitions.items()
    ]
    full_record = run_partition(
        "full_public_outputs", full_selected, inputs, outputs, target_source, reference_source, False
    )
    negative = wrapper_negative_control(
        partitions[FORMAL_PARTITION],
        FORMAL_PARTITION,
        inputs,
        outputs,
        target_source,
        reference_source,
        formal,
    )
    direct = direct_test()

    covered = [port for record in records for port in record["outputs"]]
    complete_public_output_coverage = set(covered) == set(outputs) and len(covered) == len(set(covered))
    static_pass = all(
        wrapper["status"] == "PASS"
        for record in [*records, full_record]
        for wrapper in record["static_wrappers"].values()
    )
    full_proof = full_record["yosys_equiv"]
    strict_complete = bool(
        formal
        and item["abi_exact"]
        and item["deterministic"]
        and item["view_trusted"]
        and complete_public_output_coverage
        and static_pass
        and full_record["status"] == "PASS"
        and negative["status"] == "PASS"
        and direct["status"] == "PASS"
    )
    failures: list[str] = []
    if not item["abi_exact"]:
        failures.append("locked/public ABI mismatch")
    if not item["deterministic"]:
        failures.append("non-deterministic Build export")
    if not item["view_trusted"]:
        failures.append("locked reference view conservation failure")
    if not complete_public_output_coverage:
        failures.append("queue partitions do not cover every public output exactly once")
    if not static_pass:
        failures.append("static wrapper ABI or connection audit failed")
    if full_record["status"] != "PASS":
        failures.append("full public-output sequential proof is pending")
    if negative["status"] != "PASS":
        failures.append("two-sided wrapper-output negative control failed")
    if direct["status"] != "PASS":
        failures.append("existing direct test failed")
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_FRONTENDBRIDGE_PUBLIC_QUEUE_STRICT",
        "build_id": "Build-Cpu.Memory.FrontendBridge",
        "status": "COMPLETE_PUBLIC_OUTPUT_EQUIVALENCE" if strict_complete else "STRICT_PENDING",
        "strict_complete_eligible": strict_complete,
        "strict_complete_count_delta": 1 if strict_complete else 0,
        "acceptance_eligible": False,
        "formal_requested": formal,
        "formal_partition": FORMAL_PARTITION if formal else None,
        "validator": Path(__file__).relative_to(ROOT).as_posix(),
        "build": BUILD.relative_to(ROOT).as_posix(),
        "direct_test": DIRECT_TEST.relative_to(ROOT).as_posix(),
        "scope": {
            "module": MODULE,
            "public_input_count": len(inputs),
            "public_input_bits": sum(inputs.values()),
            "public_output_count": len(outputs),
            "public_output_bits": sum(outputs.values()),
            "queue_partition_count": len(records),
            "queue_partitions_cover_every_public_output_exactly_once": complete_public_output_coverage,
            "queue_partitions": {record["partition"]: record["outputs"] for record in records},
            "full_public_outputs": full_record["outputs"],
            "full_public_output_bits": full_record["output_bits"],
        },
        "audit_policy": {
            "wrapper_generated_before_formal": True,
            "compare_only_public_outputs": True,
            "equiv_make_before_flatten": True,
            "same_clock_and_reset_inputs_preserved": True,
            "require_full_public_output_proof": True,
            "require_exact_abi": True,
            "require_conservation_audited_locked_view": True,
            "require_two_sided_wrapper_output_negative_control": True,
            "initial_serial_formal_scope": FORMAL_PARTITION,
            "bounded_tests_counted": False,
        },
        "reference_lock": {
            "directory": "validation/reference-sv",
            "xstop_sha256": rail.XSTOP_SHA256,
            "locked_references_written": False,
            "sha256_by_module": {MODULE: item["locked_sha256"]},
            "children": item["children"],
        },
        "checks": {
            "py_compile": {"status": "PASS"},
            "build_abi_exact": item["abi_exact"],
            "deterministic_export": item["deterministic"],
            "locked_view_trusted": item["view_trusted"],
            "locked_view_audits": item["view_audits"],
            "static_wrapper_generation": {
                "status": "PASS" if static_pass else "FAIL",
                "work_directory": str(WORK),
            },
            "queue_behavior_partitions": records,
            "full_public_output_proof": full_record,
            "negative_control": negative,
            "direct_test": direct,
        },
        "sources": {
            "validator": {
                "path": Path(__file__).relative_to(ROOT).as_posix(),
                "sha256": rail.sha256_file(Path(__file__).resolve()),
                "bytes": Path(__file__).stat().st_size,
            },
            "python_build": {
                "path": BUILD.relative_to(ROOT).as_posix(),
                "sha256": rail.sha256_file(BUILD),
                "bytes": BUILD.stat().st_size,
            },
            "locked_reference": {
                "path": "validation/reference-sv/FrontendBridge.sv",
                "sha256": item["locked_sha256"],
            },
            "shared_rail_read_only": {
                "path": "validation/v2_strict_family_rail.py",
                "sha256": rail.sha256_file(ROOT / "validation/v2_strict_family_rail.py"),
            },
        },
        "failures": failures,
        "unclosed": [
            "This focused output/queue rail does not change the shared family rail or strict-progress ledger.",
            "Parent closure, full XSTop differential, license review, and user approval remain outside this Build proof.",
        ],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({
        "status": payload["status"],
        "formal_requested": formal,
        "queue_partitions": {record["partition"]: record["status"] for record in records},
        "full_public_output": full_record["status"],
        "negative_control": negative["status"],
        "strict_complete_count_delta": payload["strict_complete_count_delta"],
        "failures": failures,
    }, ensure_ascii=False))
    return 0 if strict_complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
