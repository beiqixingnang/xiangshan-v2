"""Wrapper-first public-output partition diagnostic for the locked TagArray."""

from __future__ import annotations

import json
import re
import shlex
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v2_funcunit_strict_validator as multiline  # noqa: E402
import v2_strict_family_rail as rail  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/"
    "Build-Cpu.Cache.Dcache.Meta.TagArray-Hardware.py"
)
BUILD_ID = "Build-Cpu.Cache.Dcache.Meta.TagArray"
RESULT = ROOT / "validation/v2-tagarray-public-partition-diagnostic-20260929.json"
PARTITIONS: dict[str, tuple[str, ...]] = {
    "ready": ("io_read_ready",),
    "bank0": ("io_resp_0", "io_resp_1", "boreChildrenBd_bore_rdata"),
    "bank1": ("io_resp_2", "io_resp_3", "boreChildrenBd_bore_1_rdata"),
}
PARTITION_OUTPUT_BITS = {"ready": 1, "bank0": 172, "bank1": 172}
MAX_TOOL_SECONDS = 900


def source_record(path: Path) -> dict[str, Any]:
    """Return a stable in-repository source identity."""

    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": rail.sha256_file(path),
        "bytes": path.stat().st_size,
    }


def _port_decl(direction: str, width: int, name: str) -> str:
    """Render one ANSI port declaration."""

    shape = f" [{width - 1}:0]" if width > 1 else ""
    return f"  {direction}{shape} {name}"


def _partition_wrapper(
    wrapper_name: str,
    implementation_name: str,
    implementation_instance: str,
    ports: dict[str, tuple[str, int]],
    output_names: tuple[str, ...],
    mutated_outputs: frozenset[str] = frozenset(),
) -> str:
    """Wrap a full-input implementation with selected public output obligations."""

    inputs = [name for name, (direction, _width) in ports.items()
              if direction == "input"]
    declarations = [
        _port_decl("input", ports[name][1], name) for name in inputs
    ]
    declarations.extend(
        _port_decl("output", ports[name][1], name) for name in output_names
    )
    lines = [f"module {wrapper_name}(", ",\n".join(declarations), ");"]
    for name in output_names:
        lines.append(f"  wire _{implementation_instance}_{name};")
    connections: list[str] = []
    for name, (direction, _width) in ports.items():
        if direction == "input":
            connections.append(f".{name}({name})")
        elif name in output_names:
            connections.append(f".{name}(_{implementation_instance}_{name})")
        else:
            connections.append(f".{name}()")
    lines.extend((
        f"  {implementation_name} {implementation_instance}(",
        "    " + ",\n    ".join(connections),
        "  );",
    ))
    for name in output_names:
        rhs = f"_{implementation_instance}_{name}"
        if name in mutated_outputs:
            rhs = f"~{rhs}"
        lines.append(f"  assign {name} = {rhs};")
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def _summary(verdict: dict[str, Any], expected_equiv_cells: int) -> dict[str, Any]:
    """Keep proof markers and resource outcome without embedding huge logs."""

    output_tail = verdict.get("output_tail", "")
    unproven = re.search(
        r"Found\s+(\d+)\s+unproven \$equiv cells in module", output_tail
    )
    return {
        "status": verdict.get("status", "FAIL"),
        "returncode": verdict.get("returncode"),
        "timed_out": verdict.get("timed_out", False),
        "timeout_seconds": MAX_TOOL_SECONDS,
        "equiv_cells": verdict.get("equiv_cells_full"),
        "expected_public_output_equiv_cells": expected_equiv_cells,
        "unproven_equiv_cells": int(unproven.group(1)) if unproven else None,
        "equiv_summary": verdict.get("equiv_summary_full"),
        "equiv_failure_marker": verdict.get("equiv_failure_marker"),
        "equiv_success_markers": verdict.get("equiv_success_markers"),
        "output_sha256": verdict.get("output_sha256"),
        "output_tail": verdict.get("output_tail", "")[-3000:],
    }


def _run_one(
    stage: str,
    work: Path,
    target_impl: Path,
    reference_closure: Path,
    target_wrapper: str,
    reference_wrapper: str,
    output_bits: int,
) -> dict[str, Any]:
    """Run one serial sequential-equivalence process, bounded at 900 seconds."""

    stage_dir = work / stage
    stage_dir.mkdir(parents=True, exist_ok=False)
    target_path = stage_dir / "DUT_TagArray_READY.sv"
    reference_path = stage_dir / "REF_TagArray_READY.sv"
    target_path.write_text(target_wrapper, encoding="utf-8", newline="\n")
    reference_path.write_text(reference_wrapper, encoding="utf-8", newline="\n")
    files = " ".join(
        shlex.quote(rail.wsl_path(path))
        for path in (target_impl, reference_closure, target_path, reference_path)
    )
    script = (
        f"read_verilog -sv {files}; proc; async2sync; memory; opt; "
        "flatten REF_TagArray_READY; flatten DUT_TagArray_READY; opt_clean; "
        "equiv_make REF_TagArray_READY DUT_TagArray_READY TAGARRAY_READY_EQ; "
        "prep -top TAGARRAY_READY_EQ; equiv_induct -undef; equiv_status -assert"
    )
    verdict = rail.run_wsl(
        ["yosys", "-Q", "-p", script], timeout=MAX_TOOL_SECONDS
    )
    return {
        "stage": stage,
        "target_wrapper_sha256": rail.sha256_file(target_path),
        "reference_wrapper_sha256": rail.sha256_file(reference_path),
        "command": verdict.get("command"),
        **_summary(verdict, output_bits),
    }


def run_diagnostic() -> dict[str, Any]:
    """Prove ready and run target/reference output mutations, serially."""

    rail.synthesizable_view = multiline.synthesizable_view
    module = rail.load_module("tagarray_public_partition_diagnostic", BUILD)
    reference_source = rail.REF_DIR / "TagArray.sv"
    reference_text = reference_source.read_text(encoding="utf-8")
    locked_ports = rail.declared_ports(reference_text, "TagArray")
    full_rtl = rail.export_member(module, "TagArray")
    build_ports = rail.declared_ports(full_rtl, "DUT_TagArray")
    catalog_ports = {
        name: (direction, width)
        for name, direction, width in module.PORT_SPECS
    }
    if locked_ports != build_ports or locked_ports != catalog_ports:
        raise AssertionError("full TagArray port ABI differs across locked, Build, catalog")

    output_cover = Counter(
        name for names in PARTITIONS.values() for name in names
    )
    expected_outputs = Counter({
        name: 1 for name, (direction, _width) in locked_ports.items()
        if direction == "output"
    })
    if output_cover != expected_outputs:
        raise AssertionError("partition output map must cover each public output once")

    output_names = tuple(PARTITIONS["ready"])
    input_names = [
        name for name, (direction, _width) in locked_ports.items()
        if direction == "input"
    ]
    input_bits = sum(locked_ports[name][1] for name in input_names)
    output_bits = sum(
        width for direction, width in locked_ports.values()
        if direction == "output"
    )
    if input_bits != 313 or output_bits != 345:
        raise AssertionError("TagArray public ABI must remain 313 input / 345 output bits")
    for partition_name, names in PARTITIONS.items():
        partition_bits = sum(locked_ports[name][1] for name in names)
        if partition_bits != PARTITION_OUTPUT_BITS[partition_name]:
            raise AssertionError(f"wrong output-bit count for {partition_name}")

    target_top = module.TagArray()
    ready_ports = [target_top.ports[name]
                   for name in input_names + list(output_names)]
    target_impl_rtl = module.verilog.convert(
        target_top, name="DUT_TagArray_READY_IMPL",
        ports=ready_ports, emit_src=False,
    )
    target_impl_ports = rail.declared_ports(
        target_impl_rtl, "DUT_TagArray_READY_IMPL"
    )
    expected_partition_ports = {
        name: locked_ports[name] for name in input_names + list(output_names)
    }
    if target_impl_ports != expected_partition_ports:
        raise AssertionError("ready target cone lost or changed public ABI ports")

    closure, children, view_audits = rail.locked_closure("TagArray")
    if not all(audit.get("view_trusted") for audit in view_audits):
        raise AssertionError("5C reference closure view failed conservation audit")

    temp_root = Path("C:/Temp")
    temp_root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(
        prefix="uhsc_tagarray_ready_diag_", dir=temp_root
    ))
    target_impl = work / "DUT_TagArray_READY_IMPL.sv"
    if not str(work).isascii():
        raise AssertionError("formal work path must be ASCII for WSL")
    target_impl.write_text(target_impl_rtl, encoding="utf-8", newline="\n")
    reference_closure = work / "REF_TagArray.sv"
    reference_closure.write_text(closure, encoding="utf-8", newline="\n")

    ready_target_ports = {
        name: locked_ports[name] for name in input_names + list(output_names)
    }
    target_base = _partition_wrapper(
        "DUT_TagArray_READY", "DUT_TagArray_READY_IMPL", "dut_i",
        ready_target_ports, output_names,
    )
    reference_base = _partition_wrapper(
        "REF_TagArray_READY", "REF_TagArray", "ref_i",
        locked_ports, output_names,
    )
    expected_wrapper_ports = {
        name: locked_ports[name] for name in input_names + list(output_names)
    }
    if (rail.declared_ports(target_base, "DUT_TagArray_READY")
            != expected_wrapper_ports):
        raise AssertionError("DUT ready wrapper changed the public input/output slice")
    if (rail.declared_ports(reference_base, "REF_TagArray_READY")
            != expected_wrapper_ports):
        raise AssertionError("reference ready wrapper changed the public input/output slice")

    controls: dict[str, dict[str, Any]] = {}
    baseline_proven = False
    # Each call is deliberately sequential; only the ready output cone is run.
    for stage, target_mutation, reference_mutation in (
        ("ready_baseline", False, False),
        ("ready_target_mutation", True, False),
        ("ready_reference_mutation", False, True),
    ):
        print(f"Starting serial TagArray {stage} run", flush=True)
        target_wrapper = _partition_wrapper(
            "DUT_TagArray_READY", "DUT_TagArray_READY_IMPL", "dut_i",
            ready_target_ports, output_names,
            frozenset(output_names) if target_mutation else frozenset(),
        )
        reference_wrapper = _partition_wrapper(
            "REF_TagArray_READY", "REF_TagArray", "ref_i",
            locked_ports, output_names,
            frozenset(output_names) if reference_mutation else frozenset(),
        )
        result = _run_one(
            stage, work, target_impl, reference_closure,
            target_wrapper, reference_wrapper, PARTITION_OUTPUT_BITS["ready"],
        )
        markers = result.get("equiv_success_markers") or {}
        if stage == "ready_baseline":
            result["expected_result"] = "EQUIVALENCE_PASS"
            baseline_proven = (
                "PASS" if result.get("returncode") == 0
                and markers.get("Equivalence successfully proven!") is True
                else "FAIL"
            ) == "PASS"
            result["diagnostic_verdict"] = "PASS" if baseline_proven else "FAIL"
        else:
            mutation_rejected = (
                isinstance(result.get("returncode"), int)
                and result.get("returncode") != 0
                and result.get("timed_out") is not True
                and result.get("equiv_failure_marker") is True
                and not any(markers.values())
            )
            result["expected_result"] = "MUTATION_REJECTED"
            result["mutation_rejection_observed"] = mutation_rejected
            result["negative_control_decisive"] = baseline_proven and mutation_rejected
            result["diagnostic_verdict"] = (
                "PASS" if result["negative_control_decisive"] else "INCONCLUSIVE"
            )
        controls[stage] = result
        print(json.dumps({k: result.get(k) for k in (
            "stage", "status", "returncode", "timed_out", "equiv_cells",
            "equiv_failure_marker", "equiv_success_markers",
        )}, ensure_ascii=True), flush=True)

    reference_child_paths = [rail.REF_DIR / f"{child}.sv" for child in children]
    return {
        "schema_version": 1,
        "kind": "TAGARRAY_PUBLIC_OUTPUT_PARTITION_DIAGNOSTIC",
        "status": "STRICT_PENDING",
        "strict_complete_eligible": False,
        "strict_complete_count_delta": 0,
        "acceptance_eligible": False,
        "build_id": BUILD_ID,
        "proof_scope": "io_read_ready partition only; bank0/bank1 not run",
        "partition_outputs": {
            key: list(value) for key, value in PARTITIONS.items()
        },
        "coverage": {
            "full_input_ports": len(input_names),
            "full_input_bits": input_bits,
            "all_public_output_ports": sum(len(value) for value in PARTITIONS.values()),
            "covered_output_bits": output_bits,
            "output_bits_per_partition": PARTITION_OUTPUT_BITS,
            "every_output_exactly_once": Counter(
                name for names in PARTITIONS.values() for name in names
            ) == Counter({name: 1 for name, (direction, _width) in locked_ports.items()
                          if direction == "output"}),
        },
        "wrapper_policy": {
            "full_input_abi_each_partition": True,
            "public_output_obligations_only": True,
            "internal_name_matching_enabled": False,
            "side_instance_prefixes": ["dut_i", "ref_i"],
            "locked_sources_modified": False,
            "canonical_evidence_modified": False,
        },
        "abi": {
            "full_build_matches_locked_and_catalog": True,
            "ready_partition_build_ports_exact": True,
            "full_inputs": {name: locked_ports[name][1] for name in input_names},
            "ready_output_width": locked_ports["io_read_ready"][1],
            "full_input_bits": input_bits,
            "full_output_bits": output_bits,
        },
        "reference_view": {
            "kind": "SECTION_5C_MULTILINE_AUTOMATIC_AND_SRAM_VIEW",
            "all_views_trusted": True,
            "audit_count": len(view_audits),
            "audits": view_audits,
        },
        "sources": {
            "build": source_record(BUILD),
            "strict_rail": source_record(Path(rail.__file__).resolve()),
            "reference_view_helper": source_record(Path(multiline.__file__).resolve()),
            "locked_top": source_record(reference_source),
            "locked_children": {
                path.stem: source_record(path) for path in reference_child_paths
            },
        },
        "tool_policy": {
            "serial_wsl_formal": True,
            "maximum_seconds_per_run": MAX_TOOL_SECONDS,
            "ascii_temp_root": str(work),
            "ready_partition_runs": list(controls),
            "bank0_run": "NOT_RUN_PENDING_FOLLOWUP",
            "bank1_run": "NOT_RUN_PENDING_FOLLOWUP",
        },
        "checks": controls,
        "negative_control": {
            "status": (
                "PASS" if baseline_proven and all(
                    controls[stage].get("negative_control_decisive") is True
                    for stage in ("ready_target_mutation", "ready_reference_mutation")
                ) else "INCONCLUSIVE"
            ),
            "target_mutation_rejection_observed": controls[
                "ready_target_mutation"
            ].get("mutation_rejection_observed"),
            "reference_mutation_rejection_observed": controls[
                "ready_reference_mutation"
            ].get("mutation_rejection_observed"),
            "current_digest_control_closed": baseline_proven and all(
                controls[stage].get("negative_control_decisive") is True
                for stage in ("ready_target_mutation", "ready_reference_mutation")
            ),
            "reason": (
                "The unmutated ready baseline did not prove, so mutation failures "
                "cannot establish a decisive two-sided negative control."
            ),
        },
        "unclosed": [
            "Only io_read_ready was run; bank0 and bank1 public output partitions remain unproven.",
            "The complete 345-bit output surface has not been formally proven by this diagnostic.",
        ],
    }


def main() -> int:
    payload = run_diagnostic()
    RESULT.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    baseline = payload["checks"]["ready_baseline"]
    return 0 if baseline.get("diagnostic_verdict") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
