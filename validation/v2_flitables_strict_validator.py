"""Complete Build-level equivalence validator for all V2 FLI table variants.

The Build publicly supplies FliHTable, FliSTable, and FliDTable.  This
validator proves each distinct 5-bit-to-16-bit decoder against its locked V2
SystemVerilog module.  A single Build-level COMPLETE_EQUIVALENCE result is
allowed only when all three unrestricted SAT miters succeed.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import platform
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
    "Build-Cpu.Backend.Fu.Fpu.FliTable-Hardware.py"
)
SCALA = ROOT / "upstream/src/main/scala/xiangshan/backend/fu/fpu/FliTable.scala"
REFERENCE = ROOT / "validation/reference-closures/FliTables-v2.sv"
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_flitables_strict"
EVIDENCE = ROOT / "validation/v2-flitables-strict-evidence.json"

VARIANTS = ("FliHTable", "FliSTable", "FliDTable")
INPUT_WIDTHS = {"src": 5}
OUTPUT_WIDTHS = {"out": 16}
INPUT_BITS = 5


# Hash exact source and reference bytes for durable evidence.
def sha256_file(path: Path) -> str:
    """Return a SHA-256 digest for an exact file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# Hash exact module slices in the extracted closure, preserving lock identity.
def reference_module_hashes() -> dict[str, Any]:
    """Return byte/hash records for each locked FLI module."""

    data = REFERENCE.read_bytes()
    records: dict[str, Any] = {}
    for name in VARIANTS:
        marker = f"module {name}(".encode("ascii")
        start = data.find(marker)
        if start < 0:
            raise AssertionError(f"missing locked module {name}")
        end = data.find(b"endmodule", start)
        if end < 0:
            raise AssertionError(f"missing endmodule for {name}")
        payload = data[start:end + len(b"endmodule")]
        records[name] = {"bytes": len(payload),
                         "sha256": hashlib.sha256(payload).hexdigest()}
    return records


# Load the precise Build without importing sibling candidates.
def load_target() -> Any:
    """Load the FLI table Build module."""

    spec = importlib.util.spec_from_file_location("strict_flitables_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load target: {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Convert one Windows path to a WSL absolute path.
def wsl_path(path: Path) -> str:
    """Return WSL's absolute spelling for a Windows path."""

    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                            capture_output=True, check=True)
    return result.stdout.decode("utf-8", "replace").strip()


# Run a WSL command with stable, bounded diagnostics.
def run_wsl(command: list[str]) -> dict[str, Any]:
    """Run an exact WSL command and collect its result."""

    rendered = " ".join(shlex.quote(item) for item in command)
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered],
                            capture_output=True, check=False)
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {"command": command, "returncode": result.returncode,
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "output_tail": output[-3000:],
            "output_sha256": hashlib.sha256(output.encode()).hexdigest()}


# Record tool versions from the exact proof environment.
def tool_versions() -> dict[str, Any]:
    """Collect Verilator and Yosys version records."""

    return {"verilator": run_wsl(["verilator", "--version"]),
            "yosys": run_wsl(["yosys", "--version"])}


# Run Pyright on a copy outside dot-directory auto-exclusion.
def pyright_check(source: Path) -> dict[str, Any]:
    """Run Pyright and return its summary."""

    temporary = Path(tempfile.mkdtemp(prefix="uhsc_flitables_pyright_"))
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
        return {"command": command, "returncode": result.returncode,
                "status": "PASS" if passed else "FAIL",
                "version": parsed.get("version") if isinstance(parsed, dict) else None,
                "files_analyzed": summary.get("filesAnalyzed"),
                "error_count": summary.get("errorCount"),
                "warning_count": summary.get("warningCount"),
                "output_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
                "stderr_tail": result.stderr[-1000:]}
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


# Render exactly one public FLI variant from its Build-owned class.
def render_variant(module: Any, name: str) -> str:
    """Return deterministic Verilog for a named public FLI table variant."""

    from amaranth.back import verilog

    table_class = getattr(module, name)
    top = table_class()
    return verilog.convert(top, name=name, ports=[top.src, top.out], emit_src=False)


# Export every public variant twice and require byte-for-byte repeatability.
def deterministic_exports(module: Any) -> tuple[dict[str, str], dict[str, Any]]:
    """Return per-variant RTL and deterministic-export evidence."""

    rendered: dict[str, str] = {}
    evidence: dict[str, Any] = {}
    for name in VARIANTS:
        first = render_variant(module, name)
        second = render_variant(module, name)
        first_bytes = first.encode("utf-8")
        second_bytes = second.encode("utf-8")
        rendered[name] = first
        evidence[name] = {
            "status": "PASS" if first_bytes == second_bytes else "FAIL",
            "bytes": len(first_bytes),
            "sha256": hashlib.sha256(first_bytes).hexdigest(),
            "repeat_sha256": hashlib.sha256(second_bytes).hexdigest(),
            "byte_equal": first_bytes == second_bytes,
        }
    generic_first = module.build_verilog(None, {})
    generic_second = module.build_verilog(None, {})
    evidence["build_verilog_adapter"] = {
        "status": "PASS" if generic_first == generic_second else "FAIL",
        "module": "FliTable",
        "bytes": len(generic_first.encode("utf-8")),
        "sha256": hashlib.sha256(generic_first.encode("utf-8")).hexdigest(),
        "repeat_sha256": hashlib.sha256(generic_second.encode("utf-8")).hexdigest(),
        "byte_equal": generic_first == generic_second,
    }
    return rendered, evidence


# Materialize a one-variant miter while retaining the three-module closure.
def materialize_variant(name: str, target_rtl: str) -> dict[str, Path]:
    """Write target/reference/miter files for one public variant."""

    WORK.mkdir(parents=True, exist_ok=True)
    target = WORK / f"UHSC_{name}.sv"
    reference = WORK / f"REF_{name}.sv"
    miter = WORK / f"{name}_MITER.sv"
    target.write_text(target_rtl, encoding="utf-8", newline="\n")
    source = REFERENCE.read_text(encoding="utf-8")
    source = source.replace(f"module {name}(", f"module REF_{name}(", 1)
    reference.write_text(source, encoding="utf-8", newline="\n")
    miter.write_text(
        f"""module {name}_MITER(input [4:0] src, output mismatch);
  wire [15:0] reference_out;
  wire [15:0] target_out;
  REF_{name} reference_i(.src(src), .out(reference_out));
  {name} target_i(.src(src), .out(target_out));
  assign mismatch = |(reference_out ^ target_out);
endmodule
""",
        encoding="utf-8", newline="\n")
    return {"target": target, "reference": reference, "miter": miter}


# Run tool gates and one full 2**5 SAT miter proof.
def formal_variant(name: str, target_rtl: str) -> dict[str, Any]:
    """Run full-space formal equivalence for one FLI table variant."""

    paths = materialize_variant(name, target_rtl)
    converted = {key: wsl_path(path) for key, path in paths.items()}
    target, reference, miter = (converted["target"], converted["reference"],
                                converted["miter"])
    verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal",
                         target, reference, miter])
    target_yosys = run_wsl(["yosys", "-Q", "-p",
                            f"read_verilog -sv {shlex.quote(target)}; "
                            f"hierarchy -top {name}; proc; opt; check"])
    reference_yosys = run_wsl(["yosys", "-Q", "-p",
                               f"read_verilog -sv {shlex.quote(reference)}; "
                               f"hierarchy -top REF_{name}; proc; opt; check"])
    proof_script = (
        f"read_verilog -sv {shlex.quote(target)} {shlex.quote(reference)} "
        f"{shlex.quote(miter)}; prep -top {name}_MITER; flatten; opt; "
        "sat -prove mismatch 0"
    )
    proof = run_wsl(["yosys", "-Q", "-p", proof_script])
    marker = "SAT proof finished - no model found: SUCCESS!"
    proof["formal_success_marker"] = marker in proof.get("output_tail", "")
    if not proof["formal_success_marker"]:
        proof["status"] = "FAIL"
    proof["formal_scope"] = {
        "input_bits": INPUT_BITS,
        "input_space": "2**5",
        "input_space_cardinality": "32",
        "state_bits": 0,
        "state_space": "singleton (stateless combinational module)",
        "property": "mismatch == 0 for every 2-state src valuation",
    }
    return {"verilator": verilator, "yosys_target": target_yosys,
            "yosys_reference": reference_yosys, "yosys_formal_miter": proof}


# Build one aggregate miter with independent inputs for all three variants.
def formal_aggregate(rendered: dict[str, str]) -> dict[str, Any]:
    """Prove the complete three-variant Build closure in one SAT problem."""

    WORK.mkdir(parents=True, exist_ok=True)
    target = WORK / "UHSC_FliTables.sv"
    reference = WORK / "REF_FliTables.sv"
    miter = WORK / "FliTables_MITER.sv"
    target.write_text("\n".join(rendered[name] for name in VARIANTS),
                      encoding="utf-8", newline="\n")
    source = REFERENCE.read_text(encoding="utf-8")
    for name in VARIANTS:
        source = source.replace(f"module {name}(",
                                f"module REF_{name}(", 1)
    reference.write_text(source, encoding="utf-8", newline="\n")
    miter.write_text(
        """module FliTables_MITER(
  input [4:0] src_h, input [4:0] src_s, input [4:0] src_d,
  output mismatch
);
  wire [15:0] rh, rs, rd, th, ts, td;
  REF_FliHTable ref_h(.src(src_h), .out(rh));
  REF_FliSTable ref_s(.src(src_s), .out(rs));
  REF_FliDTable ref_d(.src(src_d), .out(rd));
  FliHTable dut_h(.src(src_h), .out(th));
  FliSTable dut_s(.src(src_s), .out(ts));
  FliDTable dut_d(.src(src_d), .out(td));
  assign mismatch = |(rh ^ th) | |(rs ^ ts) | |(rd ^ td);
endmodule
""",
        encoding="utf-8", newline="\n")
    converted = {key: wsl_path(path) for key, path in {
        "target": target, "reference": reference, "miter": miter}.items()}
    target_wsl, reference_wsl, miter_wsl = (converted["target"],
                                            converted["reference"],
                                            converted["miter"])
    verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal",
                         target_wsl, reference_wsl, miter_wsl])
    proof_script = (
        f"read_verilog -sv {shlex.quote(target_wsl)} "
        f"{shlex.quote(reference_wsl)} {shlex.quote(miter_wsl)}; "
        "prep -top FliTables_MITER; flatten; opt; sat -prove mismatch 0"
    )
    proof = run_wsl(["yosys", "-Q", "-p", proof_script])
    marker = "SAT proof finished - no model found: SUCCESS!"
    proof["formal_success_marker"] = marker in proof.get("output_tail", "")
    if not proof["formal_success_marker"]:
        proof["status"] = "FAIL"
    proof["formal_scope"] = {
        "input_bits": 15,
        "input_space": "2**15",
        "input_space_cardinality": "32768",
        "state_bits": 0,
        "state_space": "singleton (three stateless combinational modules)",
        "property": "OR of H/S/D output mismatches is zero for every valuation",
        "variants": list(VARIANTS),
    }
    return {"verilator": verilator, "yosys_formal_miter": proof}


# Run every variant gate and permit Build-level success only if all pass.
def validate() -> dict[str, Any]:
    """Run the FLI Build's complete three-variant equivalence suite."""

    module = load_target()
    py_compile.compile(str(TARGET), doraise=True)
    py_compile.compile(str(Path(__file__)), doraise=True)
    rendered, exports = deterministic_exports(module)
    variants = {name: formal_variant(name, rendered[name]) for name in VARIANTS}
    aggregate = formal_aggregate(rendered)
    pyright = {"target": pyright_check(TARGET),
               "validator": pyright_check(Path(__file__))}
    failures: list[str] = []
    for name, result in exports.items():
        if result["status"] != "PASS":
            failures.append(f"deterministic_export:{name}")
    for name, result in pyright.items():
        if result["status"] != "PASS":
            failures.append(f"pyright:{name}")
    for name, gates in variants.items():
        for gate_name, result in gates.items():
            if result["status"] != "PASS":
                failures.append(f"{name}:{gate_name}")
    for gate_name, result in aggregate.items():
        if result["status"] != "PASS":
            failures.append(f"aggregate:{gate_name}")
    status = "COMPLETE_EQUIVALENCE" if not failures else "STRICT_PENDING"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_STRICT_COMPLETE_EQUIVALENCE",
        "build_id": "Build-Cpu.Backend.Fu.Fpu.FliTable",
        "validator": Path(__file__).relative_to(ROOT).as_posix(),
        "status": status,
        "strict_complete_eligible": status == "COMPLETE_EQUIVALENCE",
        "strict_complete_count_delta": 1 if status == "COMPLETE_EQUIVALENCE" else 0,
        "acceptance_eligible": status == "COMPLETE_EQUIVALENCE",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "scope": {
            "kind": "stateless_combinational_multi_variant_build",
            "public_variants": list(VARIANTS),
            "state_bits": 0,
            "state_boundary": "each table has no clock/reset/register/memory",
            "inputs": {name: {"src": 5} for name in VARIANTS},
            "outputs_compared": {name: {"out": 16} for name in VARIANTS},
            "input_bits": 15,
            "input_space": "2**15",
            "input_space_cardinality": "32768",
            "inputs_per_variant": INPUT_WIDTHS,
            "outputs_compared_per_variant": OUTPUT_WIDTHS,
            "input_bits_per_variant": INPUT_BITS,
            "input_space_per_variant": "2**5",
            "input_space_cardinality_per_variant": "32",
            "aggregate_complete_cases": "3 * 32 = 96",
            "why_complete": (
                "All three declared public variants have independent Yosys SAT "
                "miters proving all 16 output bits equal for every 5-bit input; "
                "the variants are stateless."
            ),
        },
        "sources": {
            "scala": {"path": SCALA.relative_to(ROOT).as_posix(),
                      "sha256": sha256_file(SCALA), "bytes": SCALA.stat().st_size},
            "reference_sv": {"path": REFERENCE.relative_to(ROOT).as_posix(),
                             "sha256": sha256_file(REFERENCE), "bytes": REFERENCE.stat().st_size,
                             "locked_modules": list(VARIANTS),
                             "module_hashes": reference_module_hashes(),
                             "locked_xstop_sha256": "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d",
                             "locked_xstop_module_lines": {
                                 "FliHTable": [1200613, 1200670],
                                 "FliSTable": [1200672, 1200758],
                                 "FliDTable": [1200760, 1200867],
                             }},
            "python_build": {"path": TARGET.relative_to(ROOT).as_posix(),
                             "sha256": sha256_file(TARGET), "bytes": TARGET.stat().st_size},
        },
        "checks": {"python_version": platform.python_version(),
                    "py_compile": {"status": "PASS"}, "pyright": pyright,
                    "deterministic_exports": exports, "tools": tool_versions(),
                    "variants": variants, "formal": aggregate},
        "failures": failures,
        "unclosed": [] if not failures else [
            "all three public FLI variants must pass before Build-level promotion"],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    return payload


# Print compact CI status and use a nonzero exit while proof is incomplete.
def main() -> int:
    """Run the Build-level strict FLI validator."""

    payload = validate()
    print(json.dumps({"status": payload["status"],
                      "strict_complete_eligible": payload["strict_complete_eligible"],
                      "failures": payload["failures"]}, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
