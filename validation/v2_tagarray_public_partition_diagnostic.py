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
    "Cpu-Memory-Cache.Dcache.Meta.TagArray-Hardware.py"
)
BUILD_ID = "Build-Cpu.Cache.Dcache.Meta.TagArray"
RESULT = ROOT / "validation/v2-tagarray-reset-entry-ready-diagnostic-20260929-r2.json"
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
    reset_entry: bool = False,
) -> str:
    """Wrap full public inputs, selected outputs, and optional reset-entry contract."""

    inputs = [name for name, (direction, _width) in ports.items()
              if direction == "input"]
    declarations = [
        _port_decl("input", ports[name][1], name) for name in inputs
    ]
    declarations.extend(
        _port_decl("output", ports[name][1], name) for name in output_names
    )
    lines = [f"module {wrapper_name}(", ",\n".join(declarations), ");"]
    if reset_entry:
        if "clock" not in inputs or "reset" not in inputs:
            raise AssertionError("reset-entry wrapper requires clock/reset inputs")
        reset_entry_name = f"_{implementation_instance}_reset_entry"
        proof_reset_name = f"_{implementation_instance}_proof_reset"
        lines.extend((
            f"  reg {reset_entry_name} = 1'b1;",
            f"  always @(posedge clock) {reset_entry_name} <= 1'b0;",
            f"  wire {proof_reset_name} = reset | {reset_entry_name};",
        ))
    for name in output_names:
        lines.append(f"  wire _{implementation_instance}_{name};")
    connections: list[str] = []
    for name, (direction, _width) in ports.items():
        if direction == "input":
            connected = (
                f"_{implementation_instance}_proof_reset"
                if reset_entry and name == "reset" else name
            )
            connections.append(f".{name}({connected})")
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


def _counter_transition_audit() -> dict[str, Any]:
    """Check the locked source equations that justify reset-entry induction."""

    build_text = BUILD.read_text(encoding="utf-8")
    bank_text = (rail.REF_DIR / "TagSRAMBank.sv").read_text(encoding="utf-8")
    top_text = (rail.REF_DIR / "TagArray.sv").read_text(encoding="utf-8")
    bank_code = re.sub(r"//[^\n]*", "", bank_text)
    build_patterns = (
        r"rst_cnt\s*=\s*Signal\(9,\s*reset=0,",
        r"reset_done\s*=\s*cast\(Any,\s*rst_cnt\[8\]\)",
        r"module\.d\.sync\s*\+=\s*rst_cnt\.eq\(rst_cnt\s*\+\s*1\)",
        r"normal_write\s*=\s*~reset_done\s*\|\s*p\[\"io_write_valid\"\]",
        r"read_ready\s*=\s*~normal_write",
        r"\[\"io_read_ready\"\]\.eq\(ready1\)",
    )
    reference_patterns = (
        r"reg\s+\[8:0\]\s+rst_cnt",
        r"rst_cnt\s*<=\s*9'h0",
        r"else if\s*\(rst_cnt\[8\]\)\s*begin\s*end\s*else\s*rst_cnt\s*<=\s*rst_cnt\s*\+\s*9'h1",
        r"wire\s+wen\s*=\s*~\(rst_cnt\[8\]\)\s*\|\s*io_write_valid",
        r"assign\s+io_read_ready\s*=\s*~wen",
    )
    if not all(re.search(pattern, build_text, re.S) for pattern in build_patterns):
        raise AssertionError("Build reset/read-ready source relation no longer matches audited form")
    if not all(re.search(pattern, bank_code, re.S) for pattern in reference_patterns):
        raise AssertionError("locked bank reset/read-ready relation no longer matches audited form")
    if not re.search(r"TagSRAMBank\s+tag_arrays_1\s*\(", top_text):
        raise AssertionError("locked top no longer sources io_read_ready from bank 1")
    return {
        "status": "PASS_STATIC_SOURCE_AUDIT",
        "counter_width_bits": 9,
        "reset_value": 0,
        "build_next_state": "reset ? 0 : (rst_cnt[8] ? rst_cnt : rst_cnt + 1)",
        "reference_next_state": "reset ? 0 : (rst_cnt[8] ? rst_cnt : rst_cnt + 1)",
        "build_public_ready": "~(~rst_cnt[8] | io_write_valid)",
        "reference_public_ready": "~(~rst_cnt[8] | io_write_valid)",
        "source_equations_match": True,
        "reset_entry_harness": "assert reset through the first rising edge; then preserve the external reset input unchanged",
        "state_equality_assumed": False,
    }


def _summary(verdict: dict[str, Any], expected_equiv_cells: int) -> dict[str, Any]:
    """Keep proof markers and resource outcome without embedding huge logs."""

    output_tail = verdict.get("output_tail", "")
    unproven = re.search(
        r"Found\s+(\d+)\s+unproven \$equiv cells in module", output_tail
    )
    equiv_stat = re.search(r"\$equiv\s+(\d+)\s*$", output_tail, re.M)
    observed_equiv_cells = int(equiv_stat.group(1)) if equiv_stat else None
    return {
        "status": verdict.get("status", "FAIL"),
        "returncode": verdict.get("returncode"),
        "timed_out": verdict.get("timed_out", False),
        "timeout_seconds": MAX_TOOL_SECONDS,
        "equiv_cells": verdict.get("equiv_cells_full"),
        "equiv_cells_observed_in_stats": observed_equiv_cells,
        "expected_public_output_equiv_cells": expected_equiv_cells,
        "one_public_output_obligation": observed_equiv_cells == expected_equiv_cells,
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
        ready_target_ports, output_names, reset_entry=True,
    )
    reference_base = _partition_wrapper(
        "REF_TagArray_READY", "REF_TagArray", "ref_i",
        locked_ports, output_names, reset_entry=True,
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

    def run_stage(stage: str, target_mutation: bool,
                  reference_mutation: bool) -> dict[str, Any]:
        print(f"Starting serial TagArray {stage} run", flush=True)
        target_wrapper = _partition_wrapper(
            "DUT_TagArray_READY", "DUT_TagArray_READY_IMPL", "dut_i",
            ready_target_ports, output_names,
            frozenset(output_names) if target_mutation else frozenset(),
            reset_entry=True,
        )
        reference_wrapper = _partition_wrapper(
            "REF_TagArray_READY", "REF_TagArray", "ref_i",
            locked_ports, output_names,
            frozenset(output_names) if reference_mutation else frozenset(),
            reset_entry=True,
        )
        result = _run_one(
            stage, work, target_impl, reference_closure,
            target_wrapper, reference_wrapper, PARTITION_OUTPUT_BITS["ready"],
        )
        markers = result.get("equiv_success_markers") or {}
        if stage == "ready_baseline":
            result["expected_result"] = "EQUIVALENCE_PASS"
            exact_public_obligation = (
                result.get("equiv_cells") == PARTITION_OUTPUT_BITS["ready"]
            )
            result["one_public_output_obligation"] = exact_public_obligation
            result["baseline_proven"] = bool(
                result.get("returncode") == 0
                and result.get("timed_out") is not True
                and result.get("equiv_failure_marker") is not True
                and markers.get("Equivalence successfully proven!") is True
                and exact_public_obligation
            )
            result["diagnostic_verdict"] = (
                "PASS" if result["baseline_proven"] else "FAIL"
            )
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
        return result

    controls: dict[str, dict[str, Any]] = {}
    # Reset-entry establishes a shared reachable start; only a proven baseline
    # can make either subsequent mutation a decisive negative control.
    baseline = run_stage("ready_baseline", False, False)
    baseline_proven = baseline.get("baseline_proven") is True
    controls["ready_baseline"] = baseline
    if baseline_proven:
        for stage, target_mutation, reference_mutation in (
            ("ready_target_mutation", True, False),
            ("ready_reference_mutation", False, True),
        ):
            result = run_stage(stage, target_mutation, reference_mutation)
            detected = result.get("mutation_rejection_observed") is True
            result["negative_control_decisive"] = detected
            result["diagnostic_verdict"] = "PASS" if detected else "FAIL"
            controls[stage] = result
    else:
        for stage, side in (
            ("ready_target_mutation", "target"),
            ("ready_reference_mutation", "reference"),
        ):
            controls[stage] = {
                "stage": stage,
                "status": "NOT_RUN_BASELINE_FAILED",
                "expected_result": "MUTATION_REJECTED",
                "diagnostic_verdict": "INCONCLUSIVE",
                "mutation_side": side,
                "negative_control_decisive": False,
            }
    for result in controls.values():
        print(json.dumps({k: result.get(k) for k in (
            "stage", "status", "returncode", "timed_out", "equiv_cells",
            "equiv_failure_marker", "equiv_success_markers",
            "diagnostic_verdict",
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
        "previous_diagnostic": {
            "path": "validation/v2-tagarray-public-partition-diagnostic-20260929.json",
            "status": "STRICT_PENDING",
            "runner_sha256_at_archive": "9d414722fb825ebe4a7002f2b2ba09000ee06e6e32ef4505a03622d1caedb981",
            "note": "The reset-entry runner is a later revision; the previous record is preserved unchanged.",
        },
        "proof_scope": "reset-entry io_read_ready partition only; bank0/bank1 not run",
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
            "reset_entry_contract": "both instances see reset high through the first rising edge; later reset follows the full external reset input",
            "counter_equality_assumed": False,
            "locked_sources_modified": False,
            "canonical_evidence_modified": False,
        },
        "counter_transition_audit": _counter_transition_audit(),
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
            "diagnostic_runner": source_record(Path(__file__).resolve()),
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
            "formal_runs": [
                stage for stage, result in controls.items()
                if result.get("status") != "NOT_RUN_BASELINE_FAILED"
            ],
            "not_run_after_baseline_failure": [
                stage for stage, result in controls.items()
                if result.get("status") == "NOT_RUN_BASELINE_FAILED"
            ],
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
                "Negative controls run only after the reset-entry baseline proves; "
                "otherwise both are marked NOT_RUN_BASELINE_FAILED."
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
