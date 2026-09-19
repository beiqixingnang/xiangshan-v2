"""Complete input-space equivalence validator for the V2 AddrAddModule leaf.

AddrAddModule is a stateless branch-target adder.  The proof miter leaves all
89 input bits unconstrained and compares its complete 64-bit target output.
The reference is the exact locked V2 XSTop extraction, not a hand-written
behavioral oracle.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import platform
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
    "Build-Cpu.Backend.SmallControl.Family-Hardware.py"
)
SCALA = ROOT / "upstream/src/main/scala/xiangshan/backend/fu/wrapper/BranchUnit.scala"
REFERENCE = ROOT / "validation/reference-closures/AddrAddModule-v2.sv"
EVIDENCE = ROOT / "validation/v2-addraddmodule-formal-evidence.json"
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_addraddmodule_strict"

SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
LOCKED_XSTOP = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
XSTOP_BYTES = 228590583
XSTOP_MODULE_LINES = [1198238, 1198253]
EXPECTED_SCALA_SHA256 = "f2ccc62b6e544ec33994d3f93198c9608143db580db7fd8e26a4faaf1b77fa06"
EXPECTED_TARGET_SHA256 = "6ee5773e63e88368f199c08cd91415eeee45d63b4f3bfe5033bf0fbeee19bc65"
EXPECTED_REFERENCE_SHA256 = "3e5343619fb56860b42b5bccfac9fefac4a20dc547e8a7f87867695524dca178"

INPUT_WIDTHS = {
    "io_pcExtend": 51,
    "io_taken": 1,
    "io_imm": 32,
    "io_nextPcOffset": 5,
}
OUTPUT_WIDTHS = {"io_target": 64}
INPUT_BITS = sum(INPUT_WIDTHS.values())


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one exact file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_target() -> Any:
    """Load only the selected Build module by exact path."""

    spec = importlib.util.spec_from_file_location("strict_addraddmodule_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load target: {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def wsl_path(path: Path) -> str:
    """Convert a Windows path to an absolute WSL path."""

    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                            capture_output=True, check=True)
    return result.stdout.decode("utf-8", "replace").strip()


def run_wsl(command: list[str]) -> dict[str, Any]:
    """Run one WSL command and retain bounded diagnostics."""

    rendered = " ".join(shlex.quote(item) for item in command)
    try:
        result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered],
                                capture_output=True, check=False)
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

    return {"verilator": run_wsl(["verilator", "--version"]),
            "yosys": run_wsl(["yosys", "--version"])}


def pyright_check(source: Path) -> dict[str, Any]:
    """Run Pyright on an exact visible copy of one source file."""

    temporary = Path(tempfile.mkdtemp(prefix="uhsc_addraddmodule_pyright_"))
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


def source_lock_audit() -> dict[str, Any]:
    """Check every locked source/closure digest before elaboration."""

    actual = {
        "scala": sha256_file(SCALA),
        "python_build": sha256_file(TARGET),
        "reference_sv": sha256_file(REFERENCE),
    }
    expected = {
        "scala": EXPECTED_SCALA_SHA256,
        "python_build": EXPECTED_TARGET_SHA256,
        "reference_sv": EXPECTED_REFERENCE_SHA256,
    }
    checks = {name: actual[name] == expected[name] for name in actual}
    checks["source_commit_recorded"] = bool(SOURCE_COMMIT)
    checks["xstop_lock_recorded"] = len(XSTOP_SHA256) == 64 and XSTOP_BYTES > 0
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "expected": expected,
        "actual": actual,
        "source_commit": SOURCE_COMMIT,
        "xstop": {"path": LOCKED_XSTOP, "sha256": XSTOP_SHA256, "bytes": XSTOP_BYTES},
    }


def _port_pattern(direction: str, name: str, width: int) -> str:
    """Build an exact ANSI declaration pattern for ABI auditing."""

    if width == 1:
        return rf"\b{direction}\s+{name}\b"
    return rf"\b{direction}\s+\[{width - 1}:0\]\s+{name}\b"


def _declared_ports(rtl: str) -> dict[str, tuple[str, int]]:
    """Extract typed input/output declarations from one module's RTL."""

    module_start = rtl.find("module AddrAddModule")
    module_end = rtl.find("endmodule", module_start)
    body = rtl[module_start:module_end if module_end >= 0 else len(rtl)]
    # Strip trailing comments so words in source-location annotations cannot
    # be mistaken for declarations.
    body = re.sub(r"//[^\n]*", "", body)
    result: dict[str, tuple[str, int]] = {}
    pattern = re.compile(
        r"\b(input|output)\s+(?:\[(\d+):0\]\s+)?([A-Za-z_][A-Za-z0-9_]*)\b"
    )
    for match in pattern.finditer(body):
        direction, msb, name = match.groups()
        result[name] = (direction, int(msb) + 1 if msb is not None else 1)
    return result


def abi_audit(target_rtl: str) -> dict[str, Any]:
    """Require the exact five-port ABI in target and locked reference RTL."""

    reference_rtl = REFERENCE.read_text(encoding="utf-8")
    surface = {
        "io_pcExtend": ("input", 51),
        "io_taken": ("input", 1),
        "io_imm": ("input", 32),
        "io_target": ("output", 64),
        "io_nextPcOffset": ("input", 5),
    }
    checks: dict[str, bool] = {
        "target_module": "module AddrAddModule(" in target_rtl,
        "reference_module": "module AddrAddModule(" in reference_rtl,
    }
    for name, (direction, width) in surface.items():
        pattern = _port_pattern(direction, name, width)
        checks[f"target_{name}"] = re.search(pattern, target_rtl) is not None
        checks[f"reference_{name}"] = re.search(pattern, reference_rtl) is not None
    target_ports = _declared_ports(target_rtl)
    reference_ports = _declared_ports(reference_rtl)
    expected_ports = dict(surface)
    checks["target_exact_port_set"] = target_ports == expected_ports
    checks["reference_exact_port_set"] = reference_ports == expected_ports
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "target_declared_ports": target_ports,
        "reference_declared_ports": reference_ports,
        "expected_declared_ports": expected_ports,
        "inputs": INPUT_WIDTHS,
        "outputs": OUTPUT_WIDTHS,
        "port_count": len(surface),
    }


def deterministic_export(module: Any) -> tuple[str, dict[str, Any]]:
    """Generate the target RTL twice and require exact byte identity."""

    first = module.build_verilog(None, {})
    second = module.build_verilog(None, {})
    first_bytes = first.encode("utf-8")
    second_bytes = second.encode("utf-8")
    return first, {
        "status": "PASS" if first_bytes == second_bytes else "FAIL",
        "bytes": len(first_bytes),
        "sha256": hashlib.sha256(first_bytes).hexdigest(),
        "repeat_sha256": hashlib.sha256(second_bytes).hexdigest(),
        "byte_equal": first_bytes == second_bytes,
    }


def materialize_miter(target_rtl: str) -> dict[str, Path]:
    """Write target, renamed locked closure, and one-output miter."""

    reference_text = REFERENCE.read_text(encoding="utf-8")
    marker = "module AddrAddModule("
    if marker not in reference_text:
        raise AssertionError("locked AddrAddModule closure declaration missing")
    WORK.mkdir(parents=True, exist_ok=True)
    target = WORK / "UHSC_AddrAddModule.sv"
    reference = WORK / "REF_AddrAddModule.sv"
    miter = WORK / "AddrAddModule_MITER.sv"
    target.write_text(target_rtl, encoding="utf-8", newline="\n")
    reference.write_text(reference_text.replace(marker, "module REF_AddrAddModule(", 1),
                          encoding="utf-8", newline="\n")
    miter.write_text(
        """module AddrAddModule_MITER(
  input [50:0] io_pcExtend,
  input io_taken,
  input [31:0] io_imm,
  input [4:0] io_nextPcOffset,
  output mismatch
);
  wire [63:0] reference_target;
  wire [63:0] target_target;
  REF_AddrAddModule reference_i(
    .io_pcExtend(io_pcExtend), .io_taken(io_taken), .io_imm(io_imm),
    .io_target(reference_target), .io_nextPcOffset(io_nextPcOffset));
  AddrAddModule target_i(
    .io_pcExtend(io_pcExtend), .io_taken(io_taken), .io_imm(io_imm),
    .io_target(target_target), .io_nextPcOffset(io_nextPcOffset));
  assign mismatch = |(reference_target ^ target_target);
endmodule
""",
        encoding="utf-8", newline="\n")
    return {"target": target, "reference": reference, "miter": miter}


def formal_gates(paths: dict[str, Path]) -> dict[str, Any]:
    """Run lint, synthesis checks, and unrestricted SAT equivalence."""

    converted = {name: wsl_path(path) for name, path in paths.items()}
    target, reference, miter = (converted["target"], converted["reference"],
                                converted["miter"])
    verilator = run_wsl([
        "verilator", "--lint-only", "-Wno-fatal", "--top-module",
        "AddrAddModule_MITER", target, reference, miter,
    ])
    target_yosys = run_wsl(["yosys", "-Q", "-p",
                            f"read_verilog -sv {shlex.quote(target)}; "
                            "hierarchy -top AddrAddModule; proc; opt; check"])
    reference_yosys = run_wsl(["yosys", "-Q", "-p",
                               f"read_verilog -sv {shlex.quote(reference)}; "
                               "hierarchy -top REF_AddrAddModule; proc; opt; check"])
    proof_script = (
        f"read_verilog -sv {shlex.quote(target)} {shlex.quote(reference)} "
        f"{shlex.quote(miter)}; prep -top AddrAddModule_MITER; flatten; opt; "
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
        "property": "mismatch == 0 for every 2-state input valuation",
        "outputs_compared": OUTPUT_WIDTHS,
    }
    return {
        "verilator": verilator,
        "yosys_target": target_yosys,
        "yosys_reference": reference_yosys,
        "yosys_formal_miter": proof,
    }


def validate() -> dict[str, Any]:
    """Run strict gates and persist machine-readable evidence."""

    locks = source_lock_audit()
    module = load_target()
    py_compile.compile(str(TARGET), doraise=True)
    py_compile.compile(str(Path(__file__)), doraise=True)
    target_rtl, export = deterministic_export(module)
    abi = abi_audit(target_rtl)
    gates = formal_gates(materialize_miter(target_rtl))
    pyright = {"target": pyright_check(TARGET),
               "validator": pyright_check(Path(__file__))}
    failures: list[str] = []
    if locks["status"] != "PASS":
        failures.append("source lock audit")
    if abi["status"] != "PASS":
        failures.append("ABI audit")
    if export["status"] != "PASS":
        failures.append("deterministic export mismatch")
    for name, result in pyright.items():
        if result["status"] != "PASS":
            failures.append(f"pyright {name}")
    for name, result in gates.items():
        if result["status"] != "PASS":
            failures.append(name)
    status = ("COMPLETE_EQUIVALENCE_VARIANT_ONLY" if not failures
              else "STRICT_PENDING")
    uncovered_members = [name for name in module.COVERED_MODULES if name != "AddrAddModule"]
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_STRICT_COMPLETE_EQUIVALENCE",
        "build_id": "Build-Cpu.Backend.SmallControl.AddrAddModule",
        "validator": Path(__file__).relative_to(ROOT).as_posix(),
        "status": status,
        "strict_complete_eligible": False,
        "strict_complete_count_delta": 0,
        "acceptance_eligible": False,
        "variant_only_reason": (
            "This SAT miter closes the AddrAddModule member only. The target Build is the "
            "SmallControl aggregate, whose build_verilog(configuration) selects one of "
            f"{len(module.COVERED_MODULES)} locked members, so no single member can complete it."
        ),
        "uncovered_public_variants": uncovered_members,
        "source_commit": SOURCE_COMMIT,
        "scope": {
            "kind": "stateless_combinational_leaf",
            "configuration": "locked V2 branch target address adder, XLEN=64",
            "state_bits": 0,
            "state_boundary": "no clock/reset/register/memory; one combinational evaluation",
            "inputs": INPUT_WIDTHS,
            "outputs_compared": OUTPUT_WIDTHS,
            "input_bits": INPUT_BITS,
            "input_bit_accounting": "51+1+32+5=89",
            "input_space": f"2**{INPUT_BITS}",
            "input_space_cardinality": str(1 << INPUT_BITS),
            "why_complete": (
                "Yosys SAT proves the 64-bit target miter mismatch is zero with "
                "all 89 input bits unconstrained; no temporal state exists."
            ),
            "bounded_tests_counted": False,
        },
        "reference_lock": {
            "path": LOCKED_XSTOP,
            "upstream_source_commit": SOURCE_COMMIT,
            "xstop_sha256": XSTOP_SHA256,
            "xstop_bytes": XSTOP_BYTES,
            "xstop_module_lines": XSTOP_MODULE_LINES,
            "reference_module": "AddrAddModule extracted from locked V2 XSTop",
            "closure_sha256": EXPECTED_REFERENCE_SHA256,
        },
        "sources": {
            "scala": {"path": SCALA.relative_to(ROOT).as_posix(),
                      "sha256": sha256_file(SCALA), "bytes": SCALA.stat().st_size},
            "reference_sv": {"path": REFERENCE.relative_to(ROOT).as_posix(),
                             "sha256": sha256_file(REFERENCE), "bytes": REFERENCE.stat().st_size,
                             "locked_module": "AddrAddModule"},
            "python_build": {"path": TARGET.relative_to(ROOT).as_posix(),
                             "sha256": sha256_file(TARGET), "bytes": TARGET.stat().st_size},
        },
        "checks": {
            "python_version": platform.python_version(),
            "py_compile": {"status": "PASS", "files": [
                TARGET.relative_to(ROOT).as_posix(),
                Path(__file__).relative_to(ROOT).as_posix(),
            ]},
            "pyright": pyright,
            "source_lock": locks,
            "abi": abi,
            "deterministic_export": export,
            "tools": tool_versions(),
            "formal": gates,
        },
        "failures": failures,
        "unclosed": [] if not failures else ["strict gates did not all pass"],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    return payload


def main() -> int:
    """Print formal status and return nonzero until the member proof closes."""

    payload = validate()
    print(json.dumps({"status": payload["status"],
                      "strict_complete_eligible": payload["strict_complete_eligible"],
                      "failures": payload["failures"]}, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE_VARIANT_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
