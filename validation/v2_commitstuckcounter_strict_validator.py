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
EVIDENCE = ROOT / "validation/v2-commitstuckcounter-strict-evidence.json"
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_commitstuckcounter_strict"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
INPUT_WIDTHS = {"clock": 1, "reset": 1, "io_stuck": 1, "io_runtimeEnable": 1}
OUTPUT_WIDTHS = {"io_overflow": 1}


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
        return {"command": command, "status": "FAIL", "error": repr(error)}
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {"command": command, "returncode": result.returncode,
            "status": "PASS" if result.returncode == 0 else "FAIL",
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
    marker = "Equivalence successfully proven!"
    proof["formal_success_marker"] = marker in proof.get("output_tail", "")
    if not proof["formal_success_marker"]:
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


def validate() -> dict[str, Any]:
    failures: list[str] = []
    module = load_target()
    py_compile.compile(str(TARGET), doraise=True)
    py_compile.compile(str(Path(__file__)), doraise=True)
    target_rtl, deterministic = export(module)
    gates = formal(materialize(target_rtl))
    checks_pyright = {"target": pyright_check(TARGET), "validator": pyright_check(Path(__file__))}
    if deterministic["status"] != "PASS":
        failures.append("deterministic export")
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
        "scope": {"kind": "sequential_registered_leaf", "state_bits": 21,
                  "inputs": INPUT_WIDTHS, "outputs_compared": OUTPUT_WIDTHS,
                  "input_bits": 4, "transition_relation": "all input sequences, posedge clock, async reset",
                  "why_complete": "Yosys equiv_induct -undef proves all state/output equivalence cells"},
        "sources": {
            "scala": {"path": SCALA.relative_to(ROOT).as_posix(), "sha256": sha256_file(SCALA), "bytes": SCALA.stat().st_size},
            "reference_sv": {"path": REFERENCE.relative_to(ROOT).as_posix(), "sha256": sha256_file(REFERENCE), "bytes": REFERENCE.stat().st_size},
            "python_build": {"path": TARGET.relative_to(ROOT).as_posix(), "sha256": sha256_file(TARGET), "bytes": TARGET.stat().st_size},
        },
        "checks": {"py_compile": {"status": "PASS"}, "pyright": checks_pyright,
                    "deterministic_export": deterministic, "formal": gates},
        "failures": failures, "unclosed": [] if not failures else ["strict gates did not all pass"],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    return payload


if __name__ == "__main__":
    result = validate()
    print(json.dumps({"status": result["status"], "failures": result["failures"]}, ensure_ascii=False))
    raise SystemExit(0 if result["status"] == "COMPLETE_EQUIVALENCE" else 1)
