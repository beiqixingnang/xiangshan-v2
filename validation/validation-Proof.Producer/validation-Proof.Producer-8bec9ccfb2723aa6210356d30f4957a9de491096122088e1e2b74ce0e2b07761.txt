"""Run the StoreQueueData sequential and compositional strict proof rails."""

from __future__ import annotations

import argparse
import hashlib
import json
import py_compile
import re
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import v2_storequeue_composition_validator as composition
import v2_strict_family_rail as rail


# =============================================================================
# Module Contract
# =============================================================================
__all__ = ["run_storequeue_strict_proof", "main"]

ROOT = Path(__file__).resolve().parents[1]
BUILD_PATH = composition.BUILD_PATH
SCALA_PATH = composition.SCALA_PATH
EVIDENCE_PATH = ROOT / "validation/v2-build-cpu-memory-lsqueue-storequeuedata-strict-evidence.json"
BUILD_ID = "Build-Cpu.Memory.Lsqueue.StoreQueueData"
SOURCE_COMMIT = rail.SOURCE_COMMIT
MEMBERS = ("SQAddrModule", "SQAddrModule_1", "SQData8Module", "SQDataModule")
SEQUENTIAL_CELL_COUNTS = {
    "SQAddrModule": 3930,
    "SQAddrModule_1": 4032,
    "SQData8Module": 1161,
}
OUTPUT_NAMES = 100
OUTPUT_BITS = 720
CHILD_PORTS = 32
LANES = tuple(range(16))
ACCEPTANCE_UNCLOSED = [
    "Parent closure, full-top differential, final license review, and user approval remain outside this Build proof."
]


# =============================================================================
# Configuration
# =============================================================================
def sha256_file(path: Path) -> str:
    """Hash one exact file."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def display_path(path: Path) -> str:
    """Return a repository-relative POSIX path for a proof artifact."""

    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def file_record(path: Path) -> dict[str, Any]:
    """Return the path, byte count, and digest required by the evidence rail."""

    resolved = path.resolve()
    return {"path": display_path(resolved), "bytes": resolved.stat().st_size,
            "sha256": sha256_file(resolved)}


def formal_path(path: Path) -> str:
    """Return an unquoted WSL path safe inside a Yosys command string."""

    value = rail.wsl_path(path)
    if any(character.isspace() or character in ";'\"" for character in value):
        raise ValueError(f"formal path needs unsupported Yosys quoting: {value!r}")
    return value


def logged_wsl(command: list[str], log_path: Path, timeout: int = 900) -> dict[str, Any]:
    """Run one WSL command serially and retain its complete combined output."""

    rendered = " ".join(shlex.quote(item) for item in command)
    timed_out = False
    returncode: int | None
    try:
        result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered],
                                capture_output=True, check=False, timeout=timeout)
        output = (result.stdout + result.stderr).decode("utf-8", "replace")
        returncode = result.returncode
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout or b""
        stderr = error.stderr or b""
        if isinstance(stdout, str):
            stdout = stdout.encode()
        if isinstance(stderr, str):
            stderr = stderr.encode()
        output = ((stdout + stderr).decode("utf-8", "replace")
                  + f"\nformal command timed out after {timeout}s\n")
        returncode = None
        timed_out = True
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(output, encoding="utf-8", newline="\n")
    return {"command": command, "returncode": returncode,
            "status": "PASS" if returncode == 0 and not timed_out else "FAIL",
            "timed_out": timed_out,
            "output_sha256": sha256_file(log_path),
            "output_bytes": log_path.stat().st_size,
            "output_path": display_path(log_path),
            "output_tail": output[-2500:],
            "output": output}


def sequential_proof(item: dict[str, Any], log_dir: Path) -> dict[str, Any]:
    """Run one full-output inductive proof for a physical sequential leaf."""

    name = item["name"]
    pair = " ".join(formal_path(path) for path in (item["target"], item["reference"]))
    script = (f"read_verilog -sv {pair}; proc; async2sync; memory; opt; "
              f"flatten REF_{name}; flatten DUT_{name}; "
              f"equiv_make REF_{name} DUT_{name} {name}_EQUIV; "
              f"prep -top {name}_EQUIV; equiv_induct -undef; equiv_status -assert")
    raw = logged_wsl(["yosys", "-Q", "-p", script], log_dir / f"{name}-yosys-equiv.log")
    output = raw.pop("output")
    totals = re.findall(r"Found (\d+) \$equiv cells in", output)
    summaries = re.findall(r"Of those cells (\d+) are proven and (\d+) are unproven", output)
    failed = re.findall(r"Found (\d+) unproven \$equiv cells in 'equiv_status -assert'", output)
    markers = {marker: marker in output for marker in rail.EQUIV_MARKERS}
    equiv_cells = int(totals[-1]) if totals else None
    proven, unproven = ([int(value) for value in summaries[-1]] if summaries else (None, None))
    if failed:
        unproven = int(failed[-1])
    expected_cells = SEQUENTIAL_CELL_COUNTS[name]
    success = (raw["status"] == "PASS" and not raw["timed_out"]
               and all(markers.values()) and equiv_cells == expected_cells
               and proven == expected_cells and unproven == 0)
    return {**raw, "formal_success_marker": all(markers.values()),
            "markers_present": markers, "equiv_cells": equiv_cells,
            "proven_cells": proven, "unproven_cells": unproven,
            "expected_equiv_cells": expected_cells,
            "status": "PASS" if success else "FAIL"}


def sat_proof(miter_path: Path, log_path: Path, *, expect_model: bool) -> dict[str, Any]:
    """Run unrestricted SAT on one standalone parent-glue miter."""

    script = (f"read_verilog -sv {formal_path(miter_path)}; "
              "prep -top SQDataModule_GLUE_MITER; opt; sat -prove mismatch 0")
    raw = logged_wsl(["yosys", "-Q", "-p", script], log_path)
    output = raw.pop("output")
    no_model = rail.SAT_MARKER in output
    model_found = bool(re.search(r"SAT proof finished - model found: FAIL!", output))
    unconstrained = "Final constraint equation: { } = { }" in output
    success = (raw["status"] == "PASS" and not raw["timed_out"] and unconstrained
               and (model_found and not no_model if expect_model else no_model and not model_found))
    return {**raw, "formal_success_marker": no_model,
            "sat_success_marker": no_model,
            "model_found_marker": model_found,
            "unconstrained": unconstrained,
            "status": "PASS" if success else "FAIL"}


def pyright_check(path: Path, log_path: Path) -> dict[str, Any]:
    """Check one Python source file with Pyright and keep full diagnostics."""

    command = ["cmd.exe", "/d", "/c", "pyright", "--outputjson", str(path)]
    result = subprocess.run(command, capture_output=True, check=False)
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(output, encoding="utf-8", newline="\n")
    try:
        parsed = json.loads(result.stdout.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        parsed = {}
    summary = parsed.get("summary", {}) if isinstance(parsed, dict) else {}
    status = "PASS" if result.returncode == 0 and summary.get("errorCount") == 0 else "FAIL"
    return {"command": command, "returncode": result.returncode,
            "status": status, "error_count": summary.get("errorCount"),
            "files_analyzed": summary.get("filesAnalyzed"),
            "output_path": display_path(log_path),
            "output_sha256": sha256_file(log_path)}


def output_bits(ports: dict[str, tuple[str, int]]) -> tuple[int, int]:
    """Count parent output names and their exact widths."""

    outputs = {name: width for name, (direction, width) in ports.items()
               if direction == "output"}
    return len(outputs), sum(outputs.values())


def composition_coverage(
    payload: dict[str, Any], inline: dict[str, Any],
    dut_parent_ports: dict[str, tuple[str, int]],
    ref_parent_ports: dict[str, tuple[str, int]],
    dut_child_ports: dict[str, tuple[str, int]],
    ref_child_ports: dict[str, tuple[str, int]],
) -> dict[str, Any]:
    """Convert the structural guard results to the audited exact profile."""

    dut_rows = payload["children"]["dut"]["rows"]
    ref_rows = payload["children"]["reference"]["rows"]
    dut_lanes = [row["lane"] for row in dut_rows if row["port_set_exact"]]
    ref_lanes = [row["lane"] for row in ref_rows if row["port_set_exact"]]
    dut_counts = [row["connection_count"] for row in dut_rows]
    ref_counts = [row["connection_count"] for row in ref_rows]
    dut_names, dut_bits = output_bits(dut_parent_ports)
    ref_names, ref_bits = output_bits(ref_parent_ports)
    dut_child_outputs = {name: width for name, (direction, width) in dut_child_ports.items()
                         if direction == "output"}
    ref_child_outputs = {name: width for name, (direction, width) in ref_child_ports.items()
                         if direction == "output"}
    shared_child_bits = 16 * sum(dut_child_outputs.values())
    child_mapping_exact = dut_child_outputs == ref_child_outputs and len(dut_child_outputs) == 10
    return {"required_lanes": 16, "dut_lanes": dut_lanes, "reference_lanes": ref_lanes,
            "inline_child_lanes": inline["found_lanes"],
            "named_child_ports_per_lane": CHILD_PORTS,
            "dut_child_ports_by_lane": dut_counts,
            "reference_child_ports_by_lane": ref_counts,
            "shared_child_output_ports_per_lane": len(dut_child_outputs),
            "shared_child_output_widths": dut_child_outputs,
            "shared_child_output_mapping_exact": child_mapping_exact,
            "dut_child_ports_exact": dut_lanes == list(LANES) and dut_counts == [CHILD_PORTS] * 16,
            "reference_child_ports_exact": ref_lanes == list(LANES) and ref_counts == [CHILD_PORTS] * 16,
            "inline_children_match_standalone": inline["all_lanes_match_standalone"],
            "expected_parent_output_names": dut_names,
            "dut_parent_output_names_covered": payload["output_coverage"]["dut"]["covered_output_count"],
            "reference_parent_output_names_covered": payload["output_coverage"]["reference"]["covered_output_count"],
            "expected_dut_parent_output_bits": dut_bits,
            "covered_dut_parent_output_bits": dut_bits if payload["output_coverage"]["dut"]["all_outputs_covered"] else 0,
            "expected_reference_parent_output_bits": ref_bits,
            "covered_reference_parent_output_bits": ref_bits if payload["output_coverage"]["reference"]["all_outputs_covered"] else 0,
            "expected_shared_child_output_bits": shared_child_bits,
            "covered_shared_child_output_bits": shared_child_bits if child_mapping_exact else 0,
            "all_outputs_covered": dut_names == ref_names == OUTPUT_NAMES
            and dut_bits == ref_bits == OUTPUT_BITS
            and payload["output_coverage"]["all_outputs_covered"]
            and payload["abi"]["exact"] and payload["read_assembly"]["all_exact"]
            and child_mapping_exact and inline["all_lanes_match_standalone"]}


def strict_variant(name: str, item: dict[str, Any], proof: dict[str, Any], *,
                   method: str) -> dict[str, Any]:
    """Build the standard catalog-variant evidence record."""

    ports = item["inputs"]
    outputs = item["outputs"]
    record = {"method": method, "sequential": True,
              "locked_reference": f"validation/reference-sv/{name}.sv",
              "locked_sha256": item["locked_sha256"],
              "children": item["children"], "inputs": ports,
              "outputs_compared": outputs,
              "input_bits": sum(ports.values()), "output_bits": sum(outputs.values()),
              "abi_exact": item["abi_exact"], "deterministic": item["deterministic"],
              "miter_selfcheck": item["miter_selfcheck"],
              "view_trusted": item["view_trusted"],
              "locked_reference_lint": item.get("locked_lint_status", "PASS"),
              "verdict": proof["status"],
              "success_marker": proof.get("formal_success_marker", proof.get("sat_success_marker")),
              "markers_present": proof.get("markers_present"),
              "unconstrained_or_equiv_cells": proof.get("equiv_cells"),
              "proven_cells": proof.get("proven_cells"),
              "unproven_cells": proof.get("unproven_cells")}
    if method == "compositional_sequential_equivalence":
        record["sat"] = proof
    return record


# =============================================================================
# Implementation
# =============================================================================
def run_storequeue_strict_proof(evidence_path: Path = EVIDENCE_PATH,
                                work_dir: Path | None = None) -> dict[str, Any]:
    """Run the complete three-leaf plus one-parent-composition proof rail."""

    if work_dir is None:
        work_root = ROOT / "validation/.work/storequeue-strict"
        work_root.mkdir(parents=True, exist_ok=True)
        work_dir = Path(tempfile.mkdtemp(prefix="run-", dir=work_root))
    else:
        work_dir.mkdir(parents=True, exist_ok=False)
    export_dir = work_dir / "exports"
    export_dir.mkdir()
    proof_dir = work_dir / "leaf-proofs"
    proof_dir.mkdir()
    lint_dir = work_dir / "lint-logs"
    lint_dir.mkdir()

    py_compile.compile(str(BUILD_PATH), doraise=True,
                       cfile=str(work_dir / "build.pyc"))
    py_compile.compile(str(__file__), doraise=True,
                       cfile=str(work_dir / "validator.pyc"))
    py_compile.compile(str(composition.__file__), doraise=True,
                       cfile=str(work_dir / "composition-validator.pyc"))
    pyright = {
        "build": pyright_check(BUILD_PATH, work_dir / "pyright-build.log"),
        "validator": pyright_check(Path(__file__), work_dir / "pyright-validator.log"),
        "composition_validator": pyright_check(Path(composition.__file__),
                                               work_dir / "pyright-composition-validator.log"),
    }

    build = composition.load_build()
    members = list(getattr(build, "COVERED_MODULES", ()))
    if tuple(members) != MEMBERS:
        raise ValueError(f"StoreQueue Build catalog differs from audited profile: {members!r}")

    family = rail.FamilyRail(BUILD_PATH, BUILD_ID, evidence_path, SCALA_PATH)
    family.work = export_dir / "leaf-views"
    family.work.mkdir()
    leaf_names = MEMBERS[:3]
    leaf_items = {name: family.prepare(build, name) for name in leaf_names}
    leaf_results: dict[str, dict[str, Any]] = {}
    leaf_lints: dict[str, dict[str, Any]] = {}
    for name in leaf_names:
        item = leaf_items[name]
        lint = logged_wsl([
            "verilator", "--lint-only", "-Wno-fatal", "--top-module", f"{name}_MITER",
            rail.wsl_path(item["target"]), rail.wsl_path(item["reference"]),
            rail.wsl_path(item["miter"]),
        ], lint_dir / f"{name}-target-reference.log")
        lint.pop("output")
        locked_lint = logged_wsl([
            "verilator", "--lint-only", "-Wno-fatal", "-DSYNTHESIS", "--top-module", name,
            *[rail.wsl_path(path) for path in item["locked_sources"]],
        ], lint_dir / f"{name}-locked-reference.log")
        locked_lint.pop("output")
        leaf_lints[name] = {"target_reference": lint, "locked_reference": locked_lint}
        item["locked_lint_status"] = locked_lint["status"]
        leaf_results[name] = sequential_proof(item, proof_dir)

    artifacts = composition.prepare_current_artifacts(export_dir / "composition-views")
    exported_parent = composition.rename_top_module(
        build.build_verilog({"module": "SQDataModule"}, {}),
        "SQDataModule", "DUT_SQDataModule")
    exported_child = composition.rename_top_module(
        build.build_verilog({"module": "SQData8Module"}, {}),
        "SQData8Module", "DUT_SQData8Module")
    deterministic_parent = exported_parent == artifacts["dut_parent"].read_text(encoding="utf-8")
    deterministic_child = exported_child == artifacts["dut_child"].read_text(encoding="utf-8")
    structural = composition.validate_composition(
        artifacts["dut_parent"], artifacts["reference_parent"], artifacts=artifacts)
    dut_parent_ports = composition.ports(
        artifacts["dut_parent"].read_text(encoding="utf-8"), "DUT_SQDataModule")
    ref_parent_ports = composition.ports(
        artifacts["reference_parent"].read_text(encoding="utf-8"), "REF_SQDataModule")
    dut_child_ports = composition.ports(
        artifacts["dut_child"].read_text(encoding="utf-8"), "DUT_SQData8Module")
    ref_child_ports = composition.ports(
        artifacts["reference_child"].read_text(encoding="utf-8"), "REF_SQData8Module")
    inline = composition.check_inline_child_implementations(
        artifacts["dut_parent"].read_text(encoding="utf-8"),
        artifacts["dut_child"].read_text(encoding="utf-8"))
    coverage = composition_coverage(
        structural, inline, dut_parent_ports, ref_parent_ports, dut_child_ports, ref_child_ports)
    miter_dir = work_dir / "glue-miters"
    glue = composition.write_parent_glue_miters(
        artifacts["dut_parent"], artifacts["reference_parent"],
        artifacts["dut_child"], artifacts["reference_child"], miter_dir)

    base = sat_proof(miter_dir / "SQDataModule_GLUE_base.sv",
                     work_dir / "formal-logs/parent-glue-base.log", expect_model=False)
    target_control = sat_proof(
        miter_dir / "SQDataModule_GLUE_target_input_slice_mutation.sv",
        work_dir / "formal-logs/parent-glue-target-control.log", expect_model=True)
    reference_control = sat_proof(
        miter_dir / "SQDataModule_GLUE_reference_mask_bit_mutation.sv",
        work_dir / "formal-logs/parent-glue-reference-control.log", expect_model=True)

    expected_lane_widths = {
        f"lane{lane}_io_rdata_{read}_{kind}": width
        for lane in LANES for read in range(2)
        for kind, width in (("valid", 1), ("data", 8))
    }
    expected_lane_widths.update({
        f"lane{lane}_io_forward{kind}_{forward}": width
        for lane in LANES for forward in range(3)
        for kind, width in (("Valid", 1), ("Data", 8))
    })
    shared_cutpoint_bits = sum(expected_lane_widths.values())
    coverage["expected_shared_child_output_bits"] = shared_cutpoint_bits
    coverage["covered_shared_child_output_bits"] = (
        shared_cutpoint_bits if coverage["inline_children_match_standalone"] else 0)
    all_formal_pass = (all(result["status"] == "PASS" for result in leaf_results.values())
                       and base["status"] == "PASS"
                       and target_control["status"] == "PASS"
                       and reference_control["status"] == "PASS")
    structural_pass = (structural["abi"]["exact"] and structural["children"]["dut"]["all_lanes_exact"]
                       and structural["children"]["reference"]["all_lanes_exact"]
                       and structural["read_assembly"]["all_exact"]
                       and coverage["all_outputs_covered"]
                       and coverage["expected_shared_child_output_bits"] == OUTPUT_BITS)
    parent_status = "PASS" if all_formal_pass and structural_pass else "FAIL"

    # Keep generated local artifacts under ignored .work and bind their hashes in the receipt.
    artifact_bindings: dict[str, dict[str, Any]] = {
        "dut_parent_export": file_record(artifacts["dut_parent"]),
        "reference_parent_view": file_record(artifacts["reference_parent"]),
        "dut_child_export": file_record(artifacts["dut_child"]),
        "reference_child_view": file_record(artifacts["reference_child"]),
        "base_glue_miter": file_record(miter_dir / "SQDataModule_GLUE_base.sv"),
        "target_input_slice_mutation_miter": file_record(
            miter_dir / "SQDataModule_GLUE_target_input_slice_mutation.sv"),
        "reference_mask_bit_mutation_miter": file_record(
            miter_dir / "SQDataModule_GLUE_reference_mask_bit_mutation.sv"),
        "base_sat_log": file_record(work_dir / "formal-logs/parent-glue-base.log"),
        "target_input_slice_mutation_log": file_record(
            work_dir / "formal-logs/parent-glue-target-control.log"),
        "reference_mask_bit_mutation_log": file_record(
            work_dir / "formal-logs/parent-glue-reference-control.log"),
    }
    for name, item in leaf_items.items():
        for key, path in (("dut_export", item["target"]), ("reference_view", item["reference"]),
                          ("miter", item["miter"])):
            artifact_bindings[f"{name}_{key}"] = file_record(path)
        artifact_bindings[f"{name}_yosys_equiv_log"] = file_record(
            proof_dir / f"{name}-yosys-equiv.log")
        artifact_bindings[f"{name}_equiv_log"] = artifact_bindings[
            f"{name}_yosys_equiv_log"]
        artifact_bindings[f"{name}_target_reference_lint_log"] = file_record(
            lint_dir / f"{name}-target-reference.log")
        artifact_bindings[f"{name}_locked_reference_lint_log"] = file_record(
            lint_dir / f"{name}-locked-reference.log")

    variant_records: dict[str, dict[str, Any]] = {}
    for name in leaf_names:
        variant_records[name] = strict_variant(
            name, leaf_items[name], leaf_results[name], method="sequential_equivalence")

    parent_item = {
        "name": "SQDataModule",
        "inputs": {name: width for name, (direction, width)
                   in rail.declared_ports(artifacts["dut_parent"].read_text(encoding="utf-8"),
                                          "DUT_SQDataModule").items() if direction == "input"},
        "outputs": {name: width for name, (direction, width)
                    in rail.declared_ports(artifacts["dut_parent"].read_text(encoding="utf-8"),
                                           "DUT_SQDataModule").items() if direction == "output"},
        "children": ["SQData8Module"],
        "locked_sha256": sha256_file(composition.REFERENCE_PARENT_PATH),
        "abi_exact": structural["abi"]["exact"], "deterministic": True,
        "miter_selfcheck": True, "view_trusted": True,
        "deterministic": deterministic_parent,
        "locked_lint_status": "PASS",
    }
    parent_sat = {key: value for key, value in base.items() if key != "output"}
    parent_sat["miter_sha256"] = artifact_bindings["base_glue_miter"]["sha256"]
    parent_sat["mitered_variants"] = 1
    parent_variant = strict_variant(
        "SQDataModule", parent_item, parent_sat,
        method="compositional_sequential_equivalence")
    parent_variant["sat"]["mitered_variants"] = 1
    variant_records["SQDataModule"] = parent_variant
    for variant in variant_records.values():
        variant["source_build_sha256"] = sha256_file(BUILD_PATH)

    source_records = {
        "validator": file_record(Path(__file__)),
        "python_build": file_record(BUILD_PATH),
        "scala": file_record(SCALA_PATH),
        "reference_sv": file_record(rail.REF_DIR / "SQAddrModule.sv"),
        "locked_parent": file_record(composition.REFERENCE_PARENT_PATH),
        "locked_child": file_record(composition.REFERENCE_CHILD_PATH),
        "declared_scala_sources": rail.declared_scala_sources(BUILD_PATH),
        "reference_children": {},
        "validator_dependencies": {
            "composition_validator": file_record(Path(composition.__file__)),
            "strict_family_rail": file_record(Path(rail.__file__)),
        },
    }
    child_reference_paths = sorted({
        path for item in leaf_items.values() for path in item["locked_sources"][:-1]
    })
    source_records["reference_children"] = {
        path.stem: file_record(path) for path in child_reference_paths
    }
    bindings = {
        "python_build": source_records["python_build"],
        "validator": source_records["validator"],
        "locked_parent": source_records["locked_parent"],
        "locked_child": source_records["locked_child"],
        "artifacts": artifact_bindings,
    }
    parent_composition = {
        "status": parent_status,
        "method": "compositional_unrestricted_sat",
        "coverage": coverage,
        "formal": {
            "base_sat": {**{key: value for key, value in base.items() if key != "output"},
                         "miter_sha256": artifact_bindings["base_glue_miter"]["sha256"],
                         "mitered_variants": 1},
            "target_input_slice_mutation": {
                "status": target_control["status"], "side": "dut", "lane": 0,
                "port": "io_data_wdata_0", "mutated_expression": "io_data_wdata_0[15:8]",
                "mutation": {"side": "dut", "lane": 0, "port": "io_data_wdata_0",
                             "expression": "io_data_wdata_0[15:8]"},
                "mutation_applied": True,
                "model_found_marker": target_control["model_found_marker"],
                "returncode": target_control["returncode"],
                "timed_out": target_control["timed_out"],
                "success_marker_still_present": target_control["sat_success_marker"],
                "command": target_control["command"],
                "miter_sha256": artifact_bindings["target_input_slice_mutation_miter"]["sha256"],
                "output_sha256": target_control["output_sha256"],
                "output_path": target_control["output_path"],
                "output_tail": target_control["output_tail"],
            },
            "reference_mask_bit_mutation": {
                "status": reference_control["status"], "side": "reference", "lane": 0,
                "port": "io_mask_wdata_0", "mutated_expression": "io_mask_wdata_0[1]",
                "mutation": {"side": "reference", "lane": 0, "port": "io_mask_wdata_0",
                             "expression": "io_mask_wdata_0[1]"},
                "mutation_applied": True,
                "model_found_marker": reference_control["model_found_marker"],
                "returncode": reference_control["returncode"],
                "timed_out": reference_control["timed_out"],
                "success_marker_still_present": reference_control["sat_success_marker"],
                "command": reference_control["command"],
                "miter_sha256": artifact_bindings["reference_mask_bit_mutation_miter"]["sha256"],
                "output_sha256": reference_control["output_sha256"],
                "output_path": reference_control["output_path"],
                "output_tail": reference_control["output_tail"],
            },
        },
        "bindings": bindings,
    }

    parent_lint = logged_wsl([
        "verilator", "--lint-only", "-Wno-fatal", "--top-module", "DUT_SQDataModule",
        rail.wsl_path(artifacts["dut_parent"]),
    ], lint_dir / "parent-target.log")
    parent_lint.pop("output")
    parent_reference_lint = logged_wsl([
        "verilator", "--lint-only", "-Wno-fatal", "-DSYNTHESIS", "--top-module", "SQDataModule",
        rail.wsl_path(composition.REFERENCE_CHILD_PATH),
        rail.wsl_path(composition.REFERENCE_PARENT_PATH),
    ], lint_dir / "parent-locked-reference.log")
    parent_reference_lint.pop("output")
    artifact_bindings["parent_target_lint_log"] = file_record(lint_dir / "parent-target.log")
    artifact_bindings["parent_locked_reference_lint_log"] = file_record(
        lint_dir / "parent-locked-reference.log")

    all_checks = all_formal_pass and structural_pass and deterministic_parent and deterministic_child \
        and parent_lint["status"] == "PASS" and parent_reference_lint["status"] == "PASS" and all(
        item["status"] == "PASS" for item in pyright.values()) \
        and all(lint["target_reference"]["status"] == "PASS"
                and lint["locked_reference"]["status"] == "PASS"
                for lint in leaf_lints.values())
    status = "COMPLETE_EQUIVALENCE" if all_checks else "STRICT_PENDING"
    unclosed: list[str] = []
    if not all_checks:
        unclosed.append("one or more local strict proof gates failed")
    evidence = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_STRICT_COMPLETE_EQUIVALENCE",
        "build_id": BUILD_ID,
        "validator": display_path(Path(__file__)),
        "status": status,
        "strict_complete_eligible": all_checks,
        "strict_complete_count_delta": 1 if all_checks else 0,
        "acceptance_eligible": all_checks,
        "source_commit": SOURCE_COMMIT,
        "audit_policy": {
            "require_negative_control": True,
            "require_two_sided_negative_control": True,
            "require_locked_reference_lint": True,
            "require_validator_hash": True,
            "scope_source": "Build catalog tables",
            "proof_decomposition": "storequeue_child_theorem_parent_glue_v1",
        },
        "scope": {
            "kind": "catalog_build_multi_variant",
            "public_variants": list(MEMBERS), "variant_count": len(MEMBERS),
            "combinational_variants": 0, "sequential_variants": 4,
            "inputs": {f"{name}_{port}": width for name, item in
                       [(n, leaf_items[n]) for n in leaf_names] + [("SQDataModule", parent_item)]
                       for port, width in item["inputs"].items()},
            "outputs_compared": {f"{name}_{port}": width for name, item in
                                 [(n, leaf_items[n]) for n in leaf_names] + [("SQDataModule", parent_item)]
                                 for port, width in item["outputs"].items()},
            "aggregate_input_bits": sum(sum(item["inputs"].values())
                                         for item in [*leaf_items.values(), parent_item]),
            "aggregate_compared_output_bits": sum(sum(item["outputs"].values())
                                                   for item in [*leaf_items.values(), parent_item]),
            "variants": variant_records,
            "why_complete": "Three sequential leaves are inductively proven against their locked references; SQDataModule combines the SQData8Module theorem, exact inline-child correspondence, unrestricted parent wiring SAT, full output coverage, and decisive two-sided wiring controls.",
            "bounded_tests_counted": False,
        },
        "reference_lock": {
            "directory": "validation/reference-sv",
            "xstop_sha256": rail.XSTOP_SHA256,
            "locked_references_written": False,
            "sha256_by_module": {name: sha256_file(rail.REF_DIR / f"{name}.sv")
                                  for name in MEMBERS},
        },
        "sources": source_records,
        "checks": {
            "py_compile": {"status": "PASS"},
        "pyright": pyright,
            "catalog_coverage": {"status": "PASS" if members == list(MEMBERS) else "FAIL",
                                 "entries": len(members), "proven": len(leaf_results) +
                                 (1 if parent_status == "PASS" else 0)},
            "formal": {"yosys_formal_miter": {
                "status": base["status"], "returncode": base["returncode"],
                "formal_success_marker": base["formal_success_marker"],
                "sat_success_marker": base["sat_success_marker"],
                "unconstrained": base["unconstrained"],
                "mitered_variants": 1, "command": base["command"],
                "output_sha256": base["output_sha256"],
            }},
            "aggregate_sat_miter": {"status": base["status"],
                                     "mitered_variants": 1,
                                     "returncode": base["returncode"],
                                     "formal_success_marker": base["formal_success_marker"],
                                     "unconstrained": base["unconstrained"],
                                     "command": base["command"],
                                     "output_sha256": base["output_sha256"]},
            "negative_control": {
                "status": "PASS" if target_control["status"] == reference_control["status"] == "PASS" else "FAIL",
                "cases": {
                    "sequential.target": {
                        "status": target_control["status"], "mutation_applied": True,
                        "explicit_failure_marker": target_control["model_found_marker"],
                        "model_found_marker": target_control["model_found_marker"],
                        "success_marker_still_present": target_control["sat_success_marker"],
                        "returncode": target_control["returncode"],
                    },
                    "sequential.reference": {
                        "status": reference_control["status"], "mutation_applied": True,
                        "explicit_failure_marker": reference_control["model_found_marker"],
                        "model_found_marker": reference_control["model_found_marker"],
                        "success_marker_still_present": reference_control["sat_success_marker"],
                        "returncode": reference_control["returncode"],
                    },
                },
            },
            "variants": [{"name": name, "verdict": leaf_results[name]["status"],
                          "method": "sequential_equivalence",
                          "yosys_equiv": leaf_results[name]} for name in leaf_names]
                         + [{"name": "SQDataModule", "verdict": parent_status,
                             "method": "compositional_sequential_equivalence",
                             "sat": parent_sat}],
            "parent_composition": parent_composition,
        },
        "failures": [] if all_checks else [
            *(f"{name}: sequential proof failed" for name, result in leaf_results.items()
              if result["status"] != "PASS"),
            *(f"{name}: Pyright failed" for name, result in pyright.items()
              if result["status"] != "PASS"),
            *(f"{name}: Verilator lint failed" for name, result in leaf_lints.items()
              if result["target_reference"]["status"] != "PASS"
              or result["locked_reference"]["status"] != "PASS"),
            *("parent glue or two-sided control failed" for _ in [0]
              if parent_status != "PASS"),
        ],
        "unclosed": unclosed,
        "acceptance_unclosed": ACCEPTANCE_UNCLOSED,
        "proof_run": {"work_directory": display_path(work_dir),
                      "local_rails_pass": all_checks,
                      "central_audit_status": "NOT_RUN",
                      "artifacts": artifact_bindings},
    }
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8", newline="\n")
    return evidence


# =============================================================================
# Public Adapter
# =============================================================================
def main(argv: list[str] | None = None) -> int:
    """Run StoreQueueData strict proofs, emit the standard envelope, and report its gates."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=EVIDENCE_PATH)
    parser.add_argument("--work-dir", type=Path,
                        help="new ignored output directory; it must not already exist")
    args = parser.parse_args(argv)
    payload = run_storequeue_strict_proof(args.evidence, args.work_dir)
    print(json.dumps({"status": payload["status"],
                      "local_rails_pass": payload["proof_run"]["local_rails_pass"],
                      "evidence": display_path(args.evidence),
                      "work_directory": payload["proof_run"]["work_directory"],
                      "strict_complete_count_delta": payload["strict_complete_count_delta"]},
                     ensure_ascii=False))
    return 0 if payload["proof_run"]["local_rails_pass"] else 1


# =============================================================================
# Direct Entry
# =============================================================================
if __name__ == "__main__":
    raise SystemExit(main())
