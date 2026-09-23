"""Diagnose public-output equivalence for the Rocket JTAG TAP controller.

The shared family rail compares all TAP outputs in one sequential miter.  That
is the correct strict gate, but its 11 unproven cells do not identify whether
the problem is the TAP state relation, the falling-edge TDO path, or the IR
register path.  This focused validator partitions the public ABI into small
same-clock wrappers and records each result without weakening the locked
reference or changing the product Build.

Partitioned proofs are diagnostic only.  Even if every partition proves, this
file keeps ``strict_complete_count_delta`` at zero because the aggregate
strict rail still requires the unpartitioned full-output proof.
"""

from __future__ import annotations

import json
import py_compile
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parent))
import v2_jtag_reference_view_validator as focused  # noqa: E402
import v2_strict_family_rail as rail  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
BUILD = focused.BUILD
DIRECT_TEST = focused.DIRECT_TEST
EVIDENCE = ROOT / "validation/v2-jtag-tap-public-results.json"
MODULE = "JtagTapController"

PARTITIONS: dict[str, tuple[str, ...]] = {
    "state_controls": (
        "io_output_tapIsInTestLogicReset",
        "io_dataChainOut_shift",
        "io_dataChainOut_capture",
        "io_dataChainOut_update",
    ),
    "instruction": ("io_output_instruction",),
    "tdo": ("io_jtag_TDO_data", "io_jtag_TDO_driven"),
    "data": ("io_dataChainOut_data",),
}

TEMP_ROOT = Path(__import__("tempfile").gettempdir())
WORK = TEMP_ROOT / "uhsc_jtag_tap_public_family"


def _wrapper(
    name: str,
    inner: str,
    inputs: dict[str, int],
    outputs: dict[str, int],
    selected: tuple[str, ...],
) -> str:
    """Wrap one locked or generated top and expose one output partition."""

    lines = [f"module {name}("]
    ports: list[str] = []
    for port, width in inputs.items():
        ports.append(f"  input [{width - 1}:0] {port}" if width > 1 else f"  input {port}")
    for port in selected:
        width = outputs[port]
        ports.append(f"  output [{width - 1}:0] {port}" if width > 1 else f"  output {port}")
    lines.append(",\n".join(ports))
    lines.append(");")
    for port, width in outputs.items():
        lines.append(f"  wire [{width - 1}:0] _out_{port};" if width > 1
                     else f"  wire _out_{port};")
    connections = [f".{port}({port})" for port in inputs]
    connections += [f".{port}(_out_{port})" for port in outputs]
    lines.append(f"  {inner} inner_i(")
    lines.append("    " + ", ".join(connections))
    lines.append("  );")
    lines.extend(f"  assign {port} = _out_{port};" for port in selected)
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def _mutated_wrapper(source: str, selected: tuple[str, ...]) -> str:
    """Invert the first selected output in a wrapper for a negative control."""

    port = selected[0]
    pattern = rf"assign\s+{re.escape(port)}\s*=\s*_out_{re.escape(port)};"
    mutated, count = re.subn(pattern, f"assign {port} = ~_out_{port};", source, count=1)
    if count != 1:
        raise AssertionError(f"cannot mutate wrapper output {port}")
    return mutated


def _formal_script(
    ref_wrapper: Path,
    dut_wrapper: Path,
    sources: tuple[Path, ...],
    equiv_name: str,
) -> str:
    """Return the shared-clock sequential equivalence script."""

    source_paths = " ".join(rail.wsl_path(path) for path in (*sources, ref_wrapper, dut_wrapper))
    return (
        f"read_verilog -sv {source_paths}; "
        "proc; async2sync; memory; opt; "
        f"flatten {ref_wrapper.stem}; "
        f"flatten {dut_wrapper.stem}; "
        f"equiv_make {ref_wrapper.stem} "
        f"{dut_wrapper.stem} {equiv_name}; "
        f"prep -top {equiv_name}; equiv_induct -undef; equiv_status -assert"
    )


def _run_partition(
    item: dict[str, Any],
    selected: tuple[str, ...],
    label: str,
) -> dict[str, Any]:
    """Run Verilator and Yosys for one selected public-output partition."""

    inputs = item["inputs"]
    outputs = item["outputs"]
    ref_name = f"REF_{MODULE}_Public_{label}"
    dut_name = f"DUT_{MODULE}_Public_{label}"
    ref_wrapper = WORK / f"{ref_name}.sv"
    dut_wrapper = WORK / f"{dut_name}.sv"
    ref_wrapper.write_text(_wrapper(ref_name, "REF_JtagTapController", inputs, outputs, selected),
                           encoding="utf-8", newline="\n")
    dut_wrapper.write_text(_wrapper(dut_name, "DUT_JtagTapController", inputs, outputs, selected),
                           encoding="utf-8", newline="\n")

    ref_source = WORK / "REF_JtagTapController.sv"
    dut_source = WORK / "DUT_JtagTapController.sv"
    files = [ref_source, dut_source, ref_wrapper, dut_wrapper]
    lint = rail.run_wsl([
        "verilator", "--lint-only", "-Wno-fatal", "--top-module", dut_name,
        *(rail.wsl_path(path) for path in files),
    ])
    script = _formal_script(ref_wrapper, dut_wrapper, (ref_source, dut_source), f"{label}_EQUIV")
    proof = rail.run_wsl(["yosys", "-Q", "-p", script])
    markers = proof.get("equiv_success_markers", {})
    proof["formal_success_marker"] = all(markers.values())
    if isinstance(proof.get("equiv_cells_full"), int):
        proof["equiv_cells"] = proof["equiv_cells_full"]
    summary = proof.get("equiv_summary_full")
    if isinstance(summary, list) and len(summary) == 2:
        proof["proven_cells"], proof["unproven_cells"] = summary
    if isinstance(proof.get("equiv_failed_full"), int):
        proof["unproven_cells"] = proof["equiv_failed_full"]
    proof["status"] = (
        "PASS"
        if proof.get("returncode") == 0 and proof.get("formal_success_marker") is True
        else "FAIL"
    )
    return {
        "partition": label,
        "outputs": {name: outputs[name] for name in selected},
        "verilator": lint,
        "yosys_equiv": proof,
        "status": (
            "PASS"
            if lint.get("status") == "PASS" and proof.get("status") == "PASS"
            else "PENDING"
        ),
    }


def _negative_control(item: dict[str, Any], selected: tuple[str, ...], label: str) -> dict[str, Any]:
    """Run target-side and reference-side mutations for one partition."""

    inputs = item["inputs"]
    outputs = item["outputs"]
    cases: dict[str, Any] = {}
    for side in ("target", "reference"):
        ref_inner = "REF_JtagTapController"
        dut_inner = "DUT_JtagTapController"
        ref_name = f"REF_{MODULE}_Negative_{label}"
        dut_name = f"DUT_{MODULE}_Negative_{label}"
        ref_text = _wrapper(ref_name, ref_inner, inputs, outputs, selected)
        dut_text = _wrapper(dut_name, dut_inner, inputs, outputs, selected)
        if side == "target":
            dut_text = _mutated_wrapper(dut_text, selected)
        else:
            ref_text = _mutated_wrapper(ref_text, selected)
        ref_path = WORK / f"{ref_name}.sv"
        dut_path = WORK / f"{dut_name}.sv"
        ref_path.write_text(ref_text, encoding="utf-8", newline="\n")
        dut_path.write_text(dut_text, encoding="utf-8", newline="\n")
        script = _formal_script(
            ref_path,
            dut_path,
            (WORK / "REF_JtagTapController.sv", WORK / "DUT_JtagTapController.sv"),
            f"{label}_{side}_NEGATIVE_EQUIV",
        )
        result = rail.run_wsl(["yosys", "-Q", "-p", script])
        markers = result.get("equiv_success_markers", {})
        explicit_failure = result.get("equiv_failure_marker") is True
        still_success = all(markers.values())
        cases[side] = {
            "mutation_applied": True,
            "returncode": result.get("returncode"),
            "explicit_failure_marker": explicit_failure,
            "success_marker_still_present": still_success,
            "status": "PASS" if explicit_failure and not still_success else "FAIL",
            "output_tail": result.get("output_tail", "")[-1200:],
        }
    return {
        "status": "PASS" if all(case["status"] == "PASS" for case in cases.values()) else "FAIL",
        "cases": cases,
    }


def main() -> int:
    """Run focused output partitions and persist diagnostic evidence."""

    py_compile.compile(str(BUILD), doraise=True)
    py_compile.compile(str(DIRECT_TEST), doraise=True)
    py_compile.compile(str(Path(__file__)), doraise=True)
    rail.synthesizable_view = focused.synthesizable_view
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)
    module = rail.load_module("jtag_tap_public_validator", BUILD)
    family = rail.FamilyRail(BUILD, "JtagTapPublic", EVIDENCE)
    shutil.rmtree(family.work, ignore_errors=True)
    family.work.mkdir(parents=True, exist_ok=True)
    item = family.prepare(module, MODULE)
    # FamilyRail.prepare wrote the exact view/reference and DUT files under
    # the shared temporary family directory.  Copying is unnecessary; all
    # partition wrappers refer to those immutable temporary inputs.
    shutil.copyfile(item["reference"], WORK / "REF_JtagTapController.sv")
    shutil.copyfile(item["target"], WORK / "DUT_JtagTapController.sv")

    direct = subprocess.run(
        [sys.executable, str(DIRECT_TEST), "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=120,
    )
    records = [
        _run_partition(item, selected, label)
        for label, selected in PARTITIONS.items()
    ]
    negative = _negative_control(item, PARTITIONS["state_controls"], "state_controls")
    failures = [record["partition"] for record in records if record["status"] != "PASS"]
    if negative["status"] != "PASS":
        failures.append("negative_control")
    if direct.returncode != 0:
        failures.append("direct_test")
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_JTAG_TAP_PUBLIC_PARTITION_DIAGNOSTIC",
        "status": "PASS_PUBLIC_PARTITIONS_NOT_COUNTED" if not failures else "STRICT_PENDING",
        "strict_complete_count_delta": 0,
        "acceptance_eligible": False,
        "build": BUILD.relative_to(ROOT).as_posix(),
        "direct_test": DIRECT_TEST.relative_to(ROOT).as_posix(),
        "direct_test_status": "PASS" if direct.returncode == 0 else "FAIL",
        "partition_policy": {
            "full_output_strict_required": True,
            "partitioned_results_are_diagnostic_only": True,
            "locked_sources_written": False,
        },
        "records": records,
        "negative_control": negative,
        "reference_lock": {
            "directory": "validation/reference-sv",
            "locked_references_written": False,
            "sha256_by_module": {
                MODULE: rail.sha256_file(ROOT / "validation/reference-sv/JtagTapController.sv"),
                "JtagStateMachine": rail.sha256_file(ROOT / "validation/reference-sv/JtagStateMachine.sv"),
                "CaptureUpdateChain_2": rail.sha256_file(ROOT / "validation/reference-sv/CaptureUpdateChain_2.sv"),
            },
            "xstop_sha256": rail.XSTOP_SHA256,
        },
        "sources": {
            "validator": {
                "path": Path(__file__).relative_to(ROOT).as_posix(),
                "sha256": rail.sha256_file(Path(__file__).resolve()),
                "bytes": Path(__file__).stat().st_size,
            },
            "focused_view_validator": {
                "path": Path(focused.__file__).relative_to(ROOT).as_posix(),
                "sha256": rail.sha256_file(Path(focused.__file__).resolve()),
                "bytes": Path(focused.__file__).stat().st_size,
            },
            "python_build": {
                "path": BUILD.relative_to(ROOT).as_posix(),
                "sha256": rail.sha256_file(BUILD),
                "bytes": BUILD.stat().st_size,
            },
        },
        "failures": failures,
        "unclosed": [
            "The aggregate all-output JtagTapController formal rail remains pending; partition proofs do not increment strict progress."
        ],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({
        "status": payload["status"],
        "partitions": {record["partition"]: record["status"] for record in records},
        "negative_control": negative["status"],
        "strict_complete_count_delta": 0,
        "failures": failures,
    }, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
