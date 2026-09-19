"""Strict complete-equivalence proof for the locked V2 commit watchdog.

The reference closure and Build expose the same five-port ABI.  Yosys proves
the complete transition relation after normalizing asynchronous reset; no
bounded vector set is used as the strict acceptance criterion.
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
    "Build-Cpu.Backend.Rob.CommitStuckCounter-Hardware.py"
)
SCALA = ROOT / "upstream/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala"
REFERENCE = ROOT / "validation/reference-closures/CommitStuckCounter-v2.sv"
LOCKED_REFERENCE = ROOT / "validation/reference-sv/CommitStuckCounter.sv"
LOCKED_HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
EVIDENCE = ROOT / "validation/v2-commitstuckcounter-strict-evidence.json"
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_commitstuckcounter_strict"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
INPUT_WIDTHS = {"clock": 1, "reset": 1, "io_stuck": 1, "io_runtimeEnable": 1}
OUTPUT_WIDTHS = {"io_overflow": 1}
LOCKED_PORTS = {**INPUT_WIDTHS, **OUTPUT_WIDTHS}
EQUIV_SUCCESS_MARKERS = ("0 are unproven.", "Equivalence successfully proven!")
MODEL_FOUND_MARKER = "model found: FAIL!"
FREE_INPUT_MARKER = "Final constraint equation: { } = { }"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_target() -> Any:
    spec = importlib.util.spec_from_file_location("strict_commitstuckcounter_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_wsl(command: list[str]) -> dict[str, Any]:
    rendered = " ".join(shlex.quote(item) for item in command)
    try:
        result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered],
                                capture_output=True, check=False)
    except OSError as error:
        return {"command": command, "returncode": None, "status": "FAIL",
                "error": repr(error), "output_tail": repr(error),
                "equiv_success_markers": {marker: False for marker in EQUIV_SUCCESS_MARKERS},
                "equiv_failure_marker": False, "counterexample_marker": False,
                "unconstrained_marker": False}
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    summaries = re.findall(r"Of those cells (\d+) are proven and (\d+) are unproven", output)
    proven_cells = unproven_cells = equiv_cells = None
    if summaries:
        proven_cells, unproven_cells = map(int, summaries[-1])
        equiv_cells = proven_cells + unproven_cells
    return {"command": command, "returncode": result.returncode,
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "success_marker": all(marker in output for marker in EQUIV_SUCCESS_MARKERS),
            "equiv_success_markers": {marker: marker in output
                                       for marker in EQUIV_SUCCESS_MARKERS},
            "equiv_failure_marker": bool(
                re.search(r"ERROR:\s*Found\s+[1-9]\d*\s+unproven\s+\$equiv\s+cells", output)
                or re.search(r"Of those cells\s+\d+\s+are proven and\s+[1-9]\d*\s+are unproven", output)),
            "equiv_cells": equiv_cells, "proven_cells": proven_cells,
            "unproven_cells": unproven_cells,
            "counterexample_marker": MODEL_FOUND_MARKER in output,
            "unconstrained_marker": FREE_INPUT_MARKER in output,
            "output_tail": output[-6000:],
            "output_sha256": hashlib.sha256(output.encode()).hexdigest()}


def wsl_path(path: Path) -> str:
    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                            capture_output=True, check=True)
    return result.stdout.decode("utf-8", "replace").strip()


def pyright_check(source: Path) -> dict[str, Any]:
    """Run Pyright on an exact visible copy of one source file."""

    temporary = Path(tempfile.mkdtemp(prefix="uhsc_commitstuckcounter_pyright_"))
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


def export(module: Any) -> tuple[str, dict[str, Any]]:
    first = module.build_verilog(None, {})
    second = module.build_verilog(None, {})
    first_bytes = first.encode("utf-8")
    second_bytes = second.encode("utf-8")
    return first, {"status": "PASS" if first_bytes == second_bytes else "FAIL",
                   "bytes": len(first_bytes),
                   "sha256": hashlib.sha256(first_bytes).hexdigest(),
                   "repeat_sha256": hashlib.sha256(second_bytes).hexdigest(),
                   "byte_equal": first_bytes == second_bytes}


def declared_ports(rtl: str, module: str) -> dict[str, tuple[str, int]]:
    """Parse both ANSI/grouped and Amaranth header-plus-body port surfaces."""

    clean = re.sub(r"//.*", "", rtl)
    header = re.search(r"module\s+" + re.escape(module) + r"\s*\((.*?)\)\s*;", clean, re.S)
    if header is None:
        return {}
    ports: dict[str, tuple[str, int]] = {}
    header_items = [item.strip() for item in header.group(1).replace("\n", " ").split(",")]
    direction = ""
    width = 1
    for item in header_items:
        item = item.strip()
        match = re.match(r"^(input|output)\s*(?:\[(\d+):0\])?\s*([A-Za-z_]\w*)?$", item)
        if match:
            parsed_direction, msb, name = match.groups()
            if parsed_direction is None:
                continue
            direction = parsed_direction
            width = int(msb) + 1 if msb else 1
            if name:
                ports[name] = (direction, width)
        elif direction and re.fullmatch(r"[A-Za-z_]\w*", item):
            ports[item] = (direction, width)
    for line in clean[header.end():].splitlines():
        match = re.match(r"\s*(input|output)\s*(?:\[(\d+):0\])?\s*([A-Za-z_]\w*)", line)
        if match:
            parsed_direction, msb, name = match.groups()
            if parsed_direction is None:
                continue
            direction = parsed_direction
            ports[name] = (direction, int(msb) + 1 if msb else 1)
    return ports


def abi_audit(target_rtl: str, reference_rtl: str) -> dict[str, Any]:
    """Require target and locked reference to expose exactly the five ports."""

    target = declared_ports(target_rtl, "CommitStuckCounter")
    reference = declared_ports(reference_rtl, "CommitStuckCounter_ref")
    expected = {name: ("input" if name in INPUT_WIDTHS else "output", width)
                for name, width in LOCKED_PORTS.items()}
    checks = {
        "target_module": "module CommitStuckCounter(" in target_rtl,
        "reference_module": "module CommitStuckCounter_ref(" in reference_rtl,
        "target_exact_port_set": target == expected,
        "reference_exact_port_set": reference == expected,
        "target_reference_equal": target == reference,
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks,
            "target_declared_ports": {k: list(v) for k, v in target.items()},
            "reference_declared_ports": {k: list(v) for k, v in reference.items()},
            "expected_declared_ports": {k: list(v) for k, v in expected.items()}}


def materialize(target_rtl: str) -> dict[str, Path]:
    WORK.mkdir(parents=True, exist_ok=True)
    target = WORK / "CommitStuckCounter.sv"
    reference = WORK / "CommitStuckCounter_ref.sv"
    target.write_text(target_rtl, encoding="utf-8", newline="\n")
    reference_text = REFERENCE.read_text(encoding="utf-8")
    marker = "module CommitStuckCounter("
    if marker not in reference_text:
        raise AssertionError("reference module marker missing")
    reference.write_text(reference_text.replace(marker, "module CommitStuckCounter_ref(", 1),
                          encoding="utf-8", newline="\n")
    return {"target": target, "reference": reference}


def projection_audit() -> dict[str, Any]:
    """Bind the five-port proof to the exact locked-XSTop specialization."""

    hierarchy = json.loads(LOCKED_HIERARCHY.read_text(encoding="utf-8"))
    record = hierarchy["modules"]["CommitStuckCounter"]
    observed = {item["name"]: 1 if not item["width"] else int(item["width"].split(":")[0][1:]) + 1
                for item in record["ports"]}
    scala = SCALA.read_text(encoding="utf-8")
    locked = LOCKED_REFERENCE.read_text(encoding="utf-8")
    checks = {
        "locked_hierarchy_port_count": record.get("port_count") == 5,
        "locked_hierarchy_ports": observed == LOCKED_PORTS,
        "locked_reference_ports": all(name in locked for name in LOCKED_PORTS),
        "scala_declares_pruned_count": "val count = Output" in scala,
        "scala_declares_pruned_overflow_enable": "val overflowEnabled = Input" in scala,
        "locked_force_enable_false": "io_runtimeEnable & io_stuck" in locked,
        "locked_overflow_enable_true": "assign io_overflow = &count" in locked,
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks,
            "authority": "locked DefaultConfig XSTop specialization",
            "pruned_scala_ports": ["io_count", "io_overflowEnabled"],
            "constant_specializations": {"forceEnable": False, "overflowEnabled": True},
            "locked_reference": {"path": LOCKED_REFERENCE.relative_to(ROOT).as_posix(),
                                 "sha256": sha256_file(LOCKED_REFERENCE)}}


def formal(paths: dict[str, Path]) -> dict[str, Any]:
    target = wsl_path(paths["target"])
    reference = wsl_path(paths["reference"])
    lint_target = run_wsl(["verilator", "--lint-only", "-Wno-fatal", target])
    lint_reference = run_wsl(["verilator", "--lint-only", "-Wno-fatal", reference])
    target_yosys = run_wsl(["yosys", "-Q", "-p",
                            f"read_verilog -sv {shlex.quote(target)}; "
                            "proc; async2sync; opt; hierarchy -top CommitStuckCounter; check"])
    reference_yosys = run_wsl(["yosys", "-Q", "-p",
                               f"read_verilog -sv {shlex.quote(reference)}; "
                               "proc; async2sync; opt; hierarchy -top CommitStuckCounter_ref; check"])
    script = (f"read_verilog -sv {shlex.quote(target)} {shlex.quote(reference)}; "
              "proc; async2sync; memory; opt; "
              "equiv_make CommitStuckCounter CommitStuckCounter_ref CommitStuckCounter_equiv; "
              "prep -top CommitStuckCounter_equiv; equiv_induct -undef; equiv_status -assert")
    proof = run_wsl(["yosys", "-Q", "-p", script])
    proof["formal_success_marker"] = all(
        proof.get("equiv_success_markers", {}).get(marker) is True
        for marker in EQUIV_SUCCESS_MARKERS)
    proof["markers_present"] = proof.get("equiv_success_markers", {})
    if not proof["formal_success_marker"]:
        proof["status"] = "FAIL"
    proof["proven_cells"] = proof.get("proven_cells")
    proof["unproven_cells"] = proof.get("unproven_cells")
    proof["equiv_cells"] = proof.get("equiv_cells")
    equiv_cells = proof.get("equiv_cells")
    if (not isinstance(equiv_cells, int) or isinstance(equiv_cells, bool)
            or equiv_cells <= 0 or proof.get("unproven_cells") != 0):
        proof["status"] = "FAIL"
    proof["formal_scope"] = {
        "clock": "posedge clock", "reset": "async reset normalized with async2sync",
        "inputs": INPUT_WIDTHS, "outputs_compared": OUTPUT_WIDTHS,
        "state_bits": 21, "input_bits": 4,
        "property": "all 21 counter state bits and io_overflow equivalent for every input sequence",
    }
    return {"target_verilator": lint_target, "reference_verilator": lint_reference,
            "target_yosys": target_yosys, "reference_yosys": reference_yosys,
            "yosys_equiv": proof}


def negative_control(paths: dict[str, Path]) -> dict[str, Any]:
    """Mutate target and reference outputs and require both proofs to fail."""

    results: dict[str, Any] = {}
    for side in ("target", "reference"):
        source = paths[side].read_text(encoding="utf-8")
        mutated, count = re.subn(r"assign\s+io_overflow\s*=.*?;",
                                 "assign io_overflow = 1'b0;", source,
                                 count=1, flags=re.S)
        if count != 1:
            results[side] = {"status": "FAIL", "mutation_applied": False}
            continue
        mutant = WORK / f"MUTANT_{side}.sv"
        mutant.write_text(mutated, encoding="utf-8", newline="\n")
        selected = {**paths, side: mutant}
        result = formal(selected)["yosys_equiv"]
        explicit_unproven = result.get("equiv_failure_marker") is True \
            or (isinstance(result.get("unproven_cells"), int)
                and result.get("unproven_cells", 0) > 0)
        detected = (isinstance(result.get("returncode"), int) and explicit_unproven
                    and result.get("formal_success_marker") is not True)
        results[side] = {"status": "PASS" if detected else "FAIL",
                         "mutation_applied": True,
                         "explicit_unproven_cells": explicit_unproven,
                         "counterexample_marker": result.get("counterexample_marker") is True,
                         "success_marker_still_present": result.get("formal_success_marker") is True,
                         "returncode": result.get("returncode"),
                         "equiv_cells": result.get("equiv_cells"),
                         "unproven_cells": result.get("unproven_cells")}
    return {"status": "PASS" if all(item["status"] == "PASS"
                                      for item in results.values()) else "FAIL",
            "sides": results}


def validate() -> dict[str, Any]:
    failures: list[str] = []
    module = load_target()
    projection = projection_audit()
    py_compile.compile(str(TARGET), doraise=True)
    py_compile.compile(str(Path(__file__)), doraise=True)
    target_rtl, deterministic = export(module)
    paths = materialize(target_rtl)
    abi = abi_audit(target_rtl, paths["reference"].read_text(encoding="utf-8"))
    gates = formal(paths)
    control = negative_control(paths)
    checks_pyright = {"target": pyright_check(TARGET), "validator": pyright_check(Path(__file__))}
    if deterministic["status"] != "PASS":
        failures.append("deterministic export")
    if projection["status"] != "PASS":
        failures.append("locked specialization projection")
    if abi["status"] != "PASS":
        failures.append("ABI audit")
    if control["status"] != "PASS":
        failures.append("negative control")
    for name, result in checks_pyright.items():
        if result["status"] != "PASS":
            failures.append(f"pyright {name}")
    for name, result in gates.items():
        if result.get("status") != "PASS":
            failures.append(name)
    status = "COMPLETE_EQUIVALENCE" if not failures else "STRICT_PENDING"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_STRICT_COMPLETE_EQUIVALENCE",
        "build_id": "Build-Cpu.Backend.Rob.CommitStuckCounter",
        "validator": Path(__file__).relative_to(ROOT).as_posix(),
        "status": status,
        "strict_complete_eligible": status == "COMPLETE_EQUIVALENCE",
        "strict_complete_count_delta": 1 if status == "COMPLETE_EQUIVALENCE" else 0,
        "acceptance_eligible": status == "COMPLETE_EQUIVALENCE",
        "source_commit": SOURCE_COMMIT,
        "audit_policy": {"require_negative_control": True,
                         "two_sided_negative_control": True,
                         "full_output_markers": True,
                         "scope_source": "locked XSTop specialization"},
        "scope": {"kind": "sequential_registered_leaf", "state_bits": 21,
                  "authority": "locked DefaultConfig XSTop specialization",
                  "scala_class_claimed": False,
                  "inputs": INPUT_WIDTHS, "outputs_compared": OUTPUT_WIDTHS,
                  "input_bits": 4, "transition_relation": "all input sequences, posedge clock, async reset",
                  "why_complete": "Yosys equiv_induct -undef proves all state/output equivalence cells"},
        "sources": {
            "scala": {"path": SCALA.relative_to(ROOT).as_posix(), "sha256": sha256_file(SCALA), "bytes": SCALA.stat().st_size},
            "reference_sv": {"path": REFERENCE.relative_to(ROOT).as_posix(), "sha256": sha256_file(REFERENCE), "bytes": REFERENCE.stat().st_size},
            "python_build": {"path": TARGET.relative_to(ROOT).as_posix(), "sha256": sha256_file(TARGET), "bytes": TARGET.stat().st_size},
        },
        "reference_lock": projection,
        "checks": {"py_compile": {"status": "PASS"}, "pyright": checks_pyright,
                    "abi": abi,
                    "deterministic_export": deterministic,
                    "negative_control": control, "formal": gates},
        "failures": failures, "unclosed": [] if not failures else ["strict gates did not all pass"],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    return payload


if __name__ == "__main__":
    result = validate()
    print(json.dumps({"status": result["status"], "failures": result["failures"]}, ensure_ascii=False))
    raise SystemExit(0 if result["status"] == "COMPLETE_EQUIVALENCE" else 1)
