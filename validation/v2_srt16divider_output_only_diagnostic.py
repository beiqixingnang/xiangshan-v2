"""Run an isolated output-only sequential diagnostic for the V2 SRT16 divider.

This diagnostic reuses the strict rail's exact Build export, locked closure,
ABI reader, and the SRT16 multiline section-5C reference view. It intentionally
does not call ``FamilyRail.run`` and never writes strict evidence or progress.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v2_funcunit_strict_validator as multiline  # noqa: E402
import v2_strict_family_rail as rail  # noqa: E402


NAME = "SRT16DividerDataModule"
BUILD_ID = "Build-Cpu.Backend.Fu.SRT16Divider"
BUILD = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Build-Cpu.Backend.Fu.SRT16Divider-Hardware.py"
)
REFERENCE = ROOT / f"validation/reference-sv/{NAME}.sv"
EXPECTED_BUILD_SHA256 = "b7a5676f207c895ae4d7c152d04b87e24368560469e5717269f2fe0fb77d2900"
EXPECTED_REFERENCE_SHA256 = "71c183646518dd914a1569392ae993b5f20293579374178f573b1be4c8e15c7c"
EXPECTED_OUTPUT_BITS = 66
TIMEOUT_SECONDS = 900
EQUIV_MARKERS = ("0 are unproven.", "Equivalence successfully proven!")
FORMAL_COMMANDS = {
    "yosys", "abc", "verilator", "sby", "smtbmc", "boolector", "z3",
    "cvc5", "yices-smt2", "bitwuzla",
}


def sha256_file(path: Path) -> str:
    """Hash one exact file without changing it."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_record(path: Path) -> dict[str, Any]:
    """Record one proof input relative to the auxiliary repository."""

    return {
        "path": path.resolve().relative_to(ROOT).as_posix(),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def load_build() -> Any:
    """Import the current Build by exact path without invoking a build gate."""

    spec = importlib.util.spec_from_file_location("srt16_output_diag_build", BUILD)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Build: {BUILD}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def wrapper_text(
    wrapper: str,
    implementation: str,
    instance: str,
    inputs: dict[str, int],
    outputs: dict[str, int],
    flip_output: str | None = None,
) -> str:
    """Wrap one implementation with the complete public input/output ABI."""

    ports: list[str] = []
    for port, width in inputs.items():
        declaration = f"input [{width - 1}:0] {port}" if width > 1 else f"input {port}"
        ports.append(declaration)
    for port, width in outputs.items():
        declaration = f"output [{width - 1}:0] {port}" if width > 1 else f"output {port}"
        ports.append(declaration)

    lines = [f"module {wrapper}("]
    lines.extend(f"  {declaration}{',' if index + 1 < len(ports) else ''}"
                 for index, declaration in enumerate(ports))
    lines.append(");")
    for port, width in outputs.items():
        declaration = f"wire [{width - 1}:0] observed_{port}" if width > 1 else f"wire observed_{port}"
        lines.append(f"  {declaration};")
    connections = [f".{port}({port})" for port in inputs]
    connections.extend(f".{port}(observed_{port})" for port in outputs)
    lines.append(f"  {implementation} {instance}(")
    lines.append("    " + ", ".join(connections))
    lines.append("  );")
    for port in outputs:
        rhs = f"~observed_{port}" if port == flip_output else f"observed_{port}"
        lines.append(f"  assign {port} = {rhs};")
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def formal_processes() -> list[dict[str, str]]:
    """List active formal tools in WSL using executable names, not shell text."""

    command = "ps -eo comm=,pid=,etime=,rss="
    result = subprocess.run(
        ["wsl.exe", "-e", "bash", "-lc", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(f"WSL process-list check failed: {result.stderr[-500:]}")
    processes: list[dict[str, str]] = []
    for raw in result.stdout.splitlines():
        fields = raw.split(None, 3)
        if len(fields) == 4 and fields[0] in FORMAL_COMMANDS:
            processes.append({"name": fields[0], "pid": fields[1],
                              "elapsed": fields[2], "rss_kib": fields[3]})
    return processes


def assert_no_other_formal_process(owned_pid: int | None = None) -> None:
    """Refuse overlap; during a run, allow only the owned Yosys process."""

    processes = formal_processes()
    unexpected = [item for item in processes
                  if owned_pid is None or item["name"] != "yosys"
                  or item["pid"] != str(owned_pid)]
    if unexpected:
        raise RuntimeError(f"formal process overlap detected: {unexpected}")


def wsl_memory() -> dict[str, int]:
    """Read current and available memory from the single WSL environment."""

    command = (
        "awk '/^MemTotal:/ {print $2} /^MemAvailable:/ {print $2} "
        "/^SwapTotal:/ {print $2} /^SwapFree:/ {print $2}' /proc/meminfo"
    )
    result = subprocess.run(
        ["wsl.exe", "-e", "bash", "-lc", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(f"WSL memory check failed: {result.stderr[-500:]}")
    values = [int(value) for value in result.stdout.split()]
    if len(values) != 4:
        raise RuntimeError(f"unexpected WSL memory response: {result.stdout!r}")
    return {"mem_total_kib": values[0], "mem_available_kib": values[1],
            "swap_total_kib": values[2], "swap_free_kib": values[3]}


def run_wsl_proof(
    case: str,
    work: Path,
    sources: list[Path],
    expected_cell_count: int,
    induction_depth: int = 4,
) -> dict[str, Any]:
    """Run one output-only sequential proof in WSL with a hard 900s timeout."""

    assert_no_other_formal_process()
    paths = [rail.wsl_path(path) for path in sources]
    source_args = " ".join(shlex.quote(path) for path in paths)
    yosys_script = (
        f"read_verilog -sv {source_args}; proc; async2sync; memory; opt; "
        "flatten SRT16_REFERENCE_OUTPUT_ONLY; "
        "flatten SRT16_TARGET_OUTPUT_ONLY; "
        "equiv_make SRT16_REFERENCE_OUTPUT_ONLY SRT16_TARGET_OUTPUT_ONLY "
        "SRT16_OUTPUT_ONLY_EQUIV; prep -top SRT16_OUTPUT_ONLY_EQUIV; "
        f"equiv_induct -undef -seq {induction_depth}; equiv_status -assert"
    )
    shell_command = (
        "timeout --signal=TERM --kill-after=10s 900s yosys -Q -p "
        + shlex.quote(yosys_script)
    )
    log_path = work / f"{case}.log"
    print(f"FORMAL_START case={case} timeout_seconds={TIMEOUT_SECONDS}", flush=True)
    started = time.monotonic()
    max_rss_kib = 0
    next_heartbeat = 30
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            ["wsl.exe", "-e", "bash", "-lc", shell_command],
            stdout=log,
            stderr=subprocess.STDOUT,
            cwd=ROOT,
        )
        while process.poll() is None:
            time.sleep(1)
            elapsed = int(time.monotonic() - started)
            running = formal_processes()
            own = [item for item in running if item["name"] == "yosys"]
            if len(own) > 1 or any(item["name"] != "yosys" for item in running):
                raise RuntimeError(f"formal overlap during {case}: {running}")
            if own:
                max_rss_kib = max(max_rss_kib, int(own[0]["rss_kib"]))
            if elapsed >= next_heartbeat:
                memory = wsl_memory()
                print(
                    f"FORMAL_HEARTBEAT case={case} elapsed_seconds={elapsed} "
                    f"wsl_mem_available_kib={memory['mem_available_kib']} "
                    f"yosys_rss_peak_kib={max_rss_kib}",
                    flush=True,
                )
                next_heartbeat += 30
            if elapsed > TIMEOUT_SECONDS + 30:
                process.terminate()
                raise TimeoutError(f"{case} exceeded its 900 second Linux timeout")
        returncode = process.returncode
    elapsed_seconds = round(time.monotonic() - started, 3)
    assert_no_other_formal_process()
    output = log_path.read_text(encoding="utf-8", errors="replace")
    cell_counts = [int(value) for value in re.findall(r"Found (\d+) \$equiv cells in", output)]
    summaries = re.findall(
        r"Of those cells (\d+) are proven and (\d+) are unproven", output
    )
    failed_counts = [int(value) for value in re.findall(
        r"Found (\d+) unproven \$equiv cells in 'equiv_status -assert'", output
    )]
    success_markers = {marker: marker in output for marker in EQUIV_MARKERS}
    equiv_failure_marker = bool(
        re.search(r"ERROR:\s*Found\s+[1-9]\d*\s+unproven\s+\$equiv\s+cells", output)
        or "model found: FAIL!" in output
    )
    tool_errors = re.sub(
        r"ERROR:\s*Found\s+[1-9]\d*\s+unproven\s+\$equiv\s+cells "
        r"in 'equiv_status -assert'\.?",
        "",
        output,
    )
    tool_error_marker = bool(re.search(
        r"ERROR:|FATAL:|command not found|failed to run command|"
        r"No such file or directory|can't open input file",
        tool_errors,
        re.IGNORECASE,
    ))
    final_cells = cell_counts[-1] if cell_counts else None
    final_summary = [int(value) for value in summaries[-1]] if summaries else None
    proven = final_summary[0] if final_summary else None
    unproven = failed_counts[-1] if failed_counts else (final_summary[1] if final_summary else None)
    output_cell_guard = final_cells == expected_cell_count
    proof_complete = (
        returncode == 0
        and output_cell_guard
        and proven == expected_cell_count
        and unproven == 0
        and all(success_markers.values())
    )
    return {
        "case": case,
        "induction_depth": induction_depth,
        "command": ["yosys", "-Q", "-p", yosys_script],
        "returncode": returncode,
        "elapsed_seconds": elapsed_seconds,
        "max_rss_kib_sampled": max_rss_kib if max_rss_kib else None,
        "equiv_cells": final_cells,
        "expected_output_equiv_cells": expected_cell_count,
        "output_only_cell_guard": output_cell_guard,
        "proven_output_cells": proven,
        "unproven_output_cells": unproven,
        "success_markers": success_markers,
        "equiv_failure_marker": equiv_failure_marker,
        "tool_error_marker": tool_error_marker,
        "counterexample_marker": "model found: FAIL!" in output,
        "timeout_marker": "Command exited with non-zero status 124" in output,
        "log_sha256": sha256_file(log_path),
        "log_tail": output[-5000:],
        "output_only_proof_pass": proof_complete,
    }


def main() -> int:
    """Prepare the isolated wrappers, run one proof and both side controls."""

    rail.synthesizable_view = multiline.synthesizable_view
    if not BUILD.is_file() or not REFERENCE.is_file():
        raise FileNotFoundError("current Build or locked reference is missing")
    build_hash = sha256_file(BUILD)
    reference_hash = sha256_file(REFERENCE)
    if build_hash != EXPECTED_BUILD_SHA256 or reference_hash != EXPECTED_REFERENCE_SHA256:
        raise RuntimeError("proof input hash changed from the strict evidence lock")

    build = load_build()
    target_text = rail.export_member(build, NAME)
    reference_text, children, view_audits = rail.locked_closure(NAME)
    target_ports = rail.declared_ports(target_text, f"DUT_{NAME}")
    reference_ports = rail.declared_ports(reference_text, f"REF_{NAME}")
    if not target_ports or target_ports != reference_ports:
        raise RuntimeError("Build and frozen 5C reference do not have an exact ABI")
    inputs = {port: width for port, (direction, width) in target_ports.items()
              if direction == "input"}
    outputs = {port: width for port, (direction, width) in target_ports.items()
               if direction == "output"}
    output_bits = sum(outputs.values())
    if output_bits != EXPECTED_OUTPUT_BITS:
        raise RuntimeError(f"unexpected public output width: {output_bits}")
    if not view_audits or not all(item["view_trusted"] for item in view_audits):
        raise RuntimeError("the locked reference 5C view is not trusted")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    work = Path("C:/Temp") / f"uhsc_srt16divider_output_only_{stamp}"
    if not work.as_posix().isascii():
        raise RuntimeError("formal work path is not ASCII")
    work.mkdir(parents=True, exist_ok=False)
    reference_file = work / "reference.sv"
    target_file = work / "target.sv"
    reference_wrapper = work / "reference_output_only.sv"
    target_wrapper = work / "target_output_only.sv"
    reference_mutant = work / "reference_output_only_mutant.sv"
    target_mutant = work / "target_output_only_mutant.sv"
    reference_file.write_text(reference_text, encoding="utf-8", newline="\n")
    target_file.write_text(target_text, encoding="utf-8", newline="\n")
    reference_wrapper.write_text(
        wrapper_text("SRT16_REFERENCE_OUTPUT_ONLY", f"REF_{NAME}",
                     "reference_private", inputs, outputs),
        encoding="utf-8", newline="\n",
    )
    target_wrapper.write_text(
        wrapper_text("SRT16_TARGET_OUTPUT_ONLY", f"DUT_{NAME}",
                     "target_private", inputs, outputs),
        encoding="utf-8", newline="\n",
    )
    control_port = "io_in_ready"
    reference_mutant.write_text(
        wrapper_text("SRT16_REFERENCE_OUTPUT_ONLY", f"REF_{NAME}",
                     "reference_private", inputs, outputs, control_port),
        encoding="utf-8", newline="\n",
    )
    target_mutant.write_text(
        wrapper_text("SRT16_TARGET_OUTPUT_ONLY", f"DUT_{NAME}",
                     "target_private", inputs, outputs, control_port),
        encoding="utf-8", newline="\n",
    )

    memory_before = wsl_memory()
    formal_input_paths = [target_file, reference_file, reference_wrapper, target_wrapper,
                          reference_mutant, target_mutant]
    if not all(rail.wsl_path(path).isascii() for path in formal_input_paths):
        raise RuntimeError("one or more formal input paths are not ASCII")
    assert_no_other_formal_process()
    print(json.dumps({
        "phase": "prepared_before_formal",
        "stamp_utc": stamp,
        "work_path_windows": work.as_posix(),
        "work_path_wsl": rail.wsl_path(work),
        "memory_before": memory_before,
        "active_formal_processes": formal_processes(),
        "build": source_record(BUILD),
        "locked_reference": source_record(REFERENCE),
        "strict_family_rail": source_record(Path(rail.__file__)),
        "multiline_reference_view": source_record(Path(multiline.__file__)),
        "reference_children": children,
        "view_trusted": all(item["view_trusted"] for item in view_audits),
        "input_bits": sum(inputs.values()),
        "inputs": inputs,
        "output_bits": output_bits,
        "outputs": outputs,
        "wrapper_instance_names": ["reference_private", "target_private"],
        "planned_formal_runs": ["output_only_equivalence", "reference_side_negative_control",
                                 "target_side_negative_control"],
        "timeout_seconds_per_run": TIMEOUT_SECONDS,
    }, ensure_ascii=False), flush=True)

    source_common = [target_file, reference_file]
    baseline = run_wsl_proof(
        "output_only_equivalence", work,
        source_common + [reference_wrapper, target_wrapper], output_bits,
    )
    reference_control = run_wsl_proof(
        "reference_side_negative_control", work,
        source_common + [reference_mutant, target_wrapper], output_bits,
    )
    target_control = run_wsl_proof(
        "target_side_negative_control", work,
        source_common + [reference_wrapper, target_mutant], output_bits,
    )
    controls = {
        "reference": reference_control,
        "target": target_control,
    }
    for control in controls.values():
        control["detected_expected_inequivalence"] = bool(
            control["output_only_cell_guard"]
            and control["returncode"] != 0
            and control["equiv_failure_marker"]
            and not control["tool_error_marker"]
            and control["unproven_output_cells"] is not None
            and control["unproven_output_cells"] > 0
            and not all(control["success_markers"].values())
        )
    if baseline["output_only_proof_pass"]:
        diagnosis = "INTERNAL_MATCHING_LIMITATION_SUPPORTED"
    elif baseline["counterexample_marker"]:
        diagnosis = "PUBLIC_OUTPUT_DIFFERENCE_COUNTEREXAMPLE"
    elif baseline["returncode"] != 0 and baseline["unproven_output_cells"]:
        diagnosis = "OUTPUT_ONLY_PROOF_UNRESOLVED"
    else:
        diagnosis = "OUTPUT_ONLY_PROOF_INCONCLUSIVE"
    summary = {
        "phase": "formal_complete",
        "stamp_utc": stamp,
        "work_path_windows": work.as_posix(),
        "diagnosis": diagnosis,
        "output_only_equivalence": baseline,
        "negative_controls": controls,
        "both_side_negative_controls_detected": all(
            item["detected_expected_inequivalence"] for item in controls.values()
        ),
        "all_three_formal_runs_serial": True,
        "canonical_strict_evidence_written": False,
        "strict_progress_written": False,
    }
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if (baseline["output_only_proof_pass"]
                 and summary["both_side_negative_controls_detected"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
