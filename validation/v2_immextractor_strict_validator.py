"""Complete formal equivalence validator for all locked V2 ImmExtractor ABIs.

The XSTop snapshot contains five public parameter-specialized ImmExtractor
modules.  This validator derives each Build configuration from the exact
locked equations, leaves all 32 immediate and four type bits unconstrained,
and proves every output bit of every variant.  A sixth aggregate miter shares
the same 36-bit symbolic input across all five variants.  No bounded vectors
contribute to the strict verdict.
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
    "Build-Cpu.Backend.Issue.ImmExtractor-Hardware.py"
)
SCALA = ROOT / "upstream/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala"
REFERENCE = ROOT / "validation/reference-closures/ImmExtractor-v2.sv"
MANIFEST = ROOT / "validation/reference-closures/ImmExtractor-v2.json"
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_immextractor_strict"
EVIDENCE = ROOT / "validation/v2-immextractor-strict-evidence.json"

SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
XSTOP_BYTES = 228590583
LOCKED_XSTOP = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
INPUT_WIDTHS = {"io_in_imm": 32, "io_in_immType": 4}
INPUT_BITS = sum(INPUT_WIDTHS.values())
SAT_SUCCESS_MARKER = "SAT proof finished - no model found: SUCCESS!"
SAT_FREE_INPUT_MARKER = "Final constraint equation: { } = { }"
SAT_MODEL_MARKER = "model found: FAIL!"

# Each specialization's exact width and selector subset, read from the locked
# equations and represented with the same SelImm literals as the Scala map.
VARIANTS: dict[str, dict[str, Any]] = {
    "ImmExtractor": {
        "data_bits": 64,
        "imm_type_set": (2, 4, 11),
        "imm_type_names": ("U", "I", "LUI32"),
        "equation_selectors": (2, 4, 11),
    },
    "ImmExtractor_2": {
        "data_bits": 64,
        "imm_type_set": (1, 2, 3, 4),
        "imm_type_names": ("SB", "U", "UJ", "I"),
        "equation_selectors": (1, 2, 3, 4),
    },
    "ImmExtractor_12": {
        "data_bits": 128,
        "imm_type_set": (1, 2, 3, 4, 9, 10, 12, 13, 15),
        "imm_type_names": (
            "SB", "U", "UJ", "I", "OPIVIS", "OPIVIU", "VSETVLI",
            "VSETIVLI", "VRORVI",
        ),
        "equation_selectors": (1, 2, 3, 4, 9, 10, 12, 13, 15),
    },
    "ImmExtractor_37": {
        "data_bits": 128,
        "imm_type_set": (12, 13),
        "imm_type_names": ("VSETVLI", "VSETIVLI"),
        "equation_selectors": (12, 13),
    },
    "ImmExtractor_57": {
        "data_bits": 64,
        "imm_type_set": (14,),
        "imm_type_names": ("S",),
        "equation_selectors": (14,),
    },
}


def sha256_file(path: Path) -> str:
    """Return SHA-256 of exact file bytes."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_target() -> Any:
    """Load only the selected Build module by exact path."""

    spec = importlib.util.spec_from_file_location("strict_immextractor_target", TARGET)
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
    """Run one WSL command and retain bounded, hashed diagnostics."""

    rendered = " ".join(shlex.quote(item) for item in command)
    try:
        result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered],
                                capture_output=True, check=False)
    except OSError as error:
        return {"command": command, "status": "FAIL", "error": repr(error)}
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    counts = re.findall(r"Solving problem with (\d+) variables and (\d+) clauses", output)
    return {
        "command": command,
        "returncode": result.returncode,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "sat_success_marker": SAT_SUCCESS_MARKER in output,
        "sat_counterexample_marker": SAT_MODEL_MARKER in output,
        "unconstrained_marker": SAT_FREE_INPUT_MARKER in output,
        "sat_counts_full": ([int(value) for value in counts[-1]] if counts else None),
        "output_tail": output[-5000:],
        "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
    }


def tool_versions() -> dict[str, Any]:
    """Record versions of the formal back-end tools."""

    return {
        "verilator": run_wsl(["verilator", "--version"]),
        "yosys": run_wsl(["yosys", "--version"]),
    }


def pyright_check(source: Path) -> dict[str, Any]:
    """Run Pyright on an exact visible copy of one source file."""

    temporary = Path(tempfile.mkdtemp(prefix="uhsc_immextractor_pyright_"))
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


def module_body(text: str, name: str) -> str:
    """Return the exact body for one module from the five-module closure."""

    match = re.search(
        r"(?ms)^module\s+" + re.escape(name) + r"\b.*?^endmodule\b", text
    )
    if match is None:
        raise AssertionError(f"reference module missing: {name}")
    return match.group(0)


def reference_module_hashes() -> dict[str, dict[str, Any]]:
    """Hash each exact module body inside the locked family closure."""

    text = REFERENCE.read_text(encoding="utf-8")
    records: dict[str, dict[str, Any]] = {}
    for name in VARIANTS:
        body = module_body(text, name).encode("utf-8")
        records[name] = {"bytes": len(body),
                         "sha256": hashlib.sha256(body).hexdigest()}
    return records


def closure_audit() -> dict[str, Any]:
    """Audit exact five-module closure and selector subsets before proof."""

    if not REFERENCE.is_file() or not MANIFEST.is_file():
        return {"status": "FAIL", "reason": "closure or manifest missing"}
    try:
        closure_text = REFERENCE.read_text(encoding="utf-8")
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {"status": "FAIL", "reason": repr(error)}
    manifest_names = [item.get("name") for item in manifest.get("modules", [])]
    rows: dict[str, Any] = {}
    for name, spec in VARIANTS.items():
        body = module_body(closure_text, name)
        literal_selectors = {
            int(value, 16)
            for value in re.findall(r"io_in_immType\s*==\s*4'h([0-9A-Fa-f]+)", body)
        }
        if re.search(r"\(&io_in_immType\)", body):
            literal_selectors.add(15)
        width_match = re.search(r"output\s+\[(\d+):0\]\s+io_out_imm", body)
        output_width = int(width_match.group(1)) + 1 if width_match else None
        expected = set(spec["equation_selectors"])
        rows[name] = {
            "output_width": output_width,
            "selectors_from_locked_equation": sorted(literal_selectors),
            "expected_selectors": sorted(expected),
            "selector_match": literal_selectors == expected,
            "width_match": output_width == spec["data_bits"],
            "scala_imm_type_names": list(spec["imm_type_names"]),
        }
    checks = {
        "target": manifest.get("target") == "ImmExtractor family variants",
        "source_sha256": manifest.get("source_sha256") == XSTOP_SHA256,
        "closure_complete": manifest.get("closure_complete") is True,
        "module_count": manifest.get("module_count") == len(VARIANTS),
        "module_order": manifest_names == list(VARIANTS),
        "closure_hash": manifest.get("extracted_sha256") == sha256_file(REFERENCE),
        "all_variant_equations": all(
            row["selector_match"] and row["width_match"] for row in rows.values()
        ),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "rows": rows,
        "closure_path": REFERENCE.relative_to(ROOT).as_posix(),
        "closure_sha256": sha256_file(REFERENCE),
        "closure_bytes": REFERENCE.stat().st_size,
        "manifest_path": MANIFEST.relative_to(ROOT).as_posix(),
        "manifest_sha256": sha256_file(MANIFEST),
        "source": manifest.get("source"),
        "source_sha256": manifest.get("source_sha256"),
    }


def export_targets(module: Any) -> tuple[dict[str, str], dict[str, Any]]:
    """Export every exact Build configuration twice and audit determinism."""

    exported: dict[str, str] = {}
    records: dict[str, Any] = {}
    for name, spec in VARIANTS.items():
        config = module.ImmExtractorConfig(
            data_bits=spec["data_bits"], imm_type_set=tuple(spec["imm_type_set"])
        )
        first = module.build_verilog(config, {})
        second = module.build_verilog(config, {})
        first_bytes = first.encode("utf-8")
        second_bytes = second.encode("utf-8")
        exported[name] = first
        records[name] = {
            "status": "PASS" if first_bytes == second_bytes else "FAIL",
            "configuration": {
                "data_bits": spec["data_bits"],
                "imm_type_set": list(spec["imm_type_set"]),
                "imm_type_names": list(spec["imm_type_names"]),
            },
            "bytes": len(first_bytes),
            "sha256": hashlib.sha256(first_bytes).hexdigest(),
            "repeat_sha256": hashlib.sha256(second_bytes).hexdigest(),
            "byte_equal": first_bytes == second_bytes,
        }
    return exported, records


def rename_target(text: str, target_name: str) -> str:
    """Rename exactly the generated target's top declaration."""

    marker = "module ImmExtractor("
    if marker not in text:
        raise AssertionError("generated ImmExtractor declaration missing")
    return text.replace(marker, f"module {target_name}(", 1)


def materialize_sources(exported: dict[str, str]) -> dict[str, Any]:
    """Write all five target variants, shared reference closure, and miters."""

    WORK.mkdir(parents=True, exist_ok=True)
    reference = WORK / "REF_ImmExtractor_closure.sv"
    reference.write_text(REFERENCE.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    targets: dict[str, Path] = {}
    miters: dict[str, Path] = {}
    target_names: dict[str, str] = {}
    aggregate_terms: list[str] = []
    aggregate_instances: list[str] = []
    for name, spec in VARIANTS.items():
        target_name = f"DUT_{name}"
        target_names[name] = target_name
        target = WORK / f"{target_name}.sv"
        target.write_text(rename_target(exported[name], target_name),
                          encoding="utf-8", newline="\n")
        targets[name] = target
        width = spec["data_bits"]
        miter = WORK / f"{name}_MITER.sv"
        miter.write_text(
            f"""module {name}_MITER(
  input [31:0] io_in_imm,
  input [3:0] io_in_immType,
  output mismatch
);
  wire [{width - 1}:0] reference_out;
  wire [{width - 1}:0] target_out;
  {name} reference_i(
    .io_in_imm(io_in_imm), .io_in_immType(io_in_immType),
    .io_out_imm(reference_out));
  {target_name} target_i(
    .io_in_imm(io_in_imm), .io_in_immType(io_in_immType),
    .io_out_imm(target_out));
  assign mismatch = |(reference_out ^ target_out);
endmodule
""",
            encoding="utf-8", newline="\n")
        miters[name] = miter
        aggregate_instances.append(
            f"  wire [{width - 1}:0] ref_{name}, dut_{name};\n"
            f"  {name} ref_i_{name}(.io_in_imm(io_in_imm), .io_in_immType(io_in_immType), .io_out_imm(ref_{name}));\n"
            f"  {target_name} dut_i_{name}(.io_in_imm(io_in_imm), .io_in_immType(io_in_immType), .io_out_imm(dut_{name}));"
        )
        aggregate_terms.append(f"|(ref_{name} ^ dut_{name})")
    aggregate = WORK / "ImmExtractor_ALL_MITER.sv"
    aggregate.write_text(
        "module ImmExtractor_ALL_MITER(\n"
        "  input [31:0] io_in_imm,\n"
        "  input [3:0] io_in_immType,\n"
        "  output mismatch\n);\n"
        + "\n".join(aggregate_instances)
        + "\n  assign mismatch = " + "\n                  | ".join(aggregate_terms) + ";\nendmodule\n",
        encoding="utf-8", newline="\n")
    return {
        "reference": reference,
        "targets": targets,
        "miters": miters,
        "aggregate": aggregate,
        "target_names": target_names,
    }


def formal_one(name: str, paths: dict[str, Any]) -> dict[str, Any]:
    """Run lint/check and one full 36-bit symbolic miter proof."""

    target = wsl_path(paths["targets"][name])
    reference = wsl_path(paths["reference"])
    miter = wsl_path(paths["miters"][name])
    target_name = paths["target_names"][name]
    top = f"{name}_MITER"
    verilator = run_wsl([
        "verilator", "--lint-only", "-Wno-fatal", "--top-module", top,
        target, reference, miter,
    ])
    yosys_target = run_wsl(["yosys", "-Q", "-p",
                             f"read_verilog -sv {shlex.quote(target)}; "
                             f"hierarchy -top {target_name}; proc; opt; check"])
    yosys_reference = run_wsl(["yosys", "-Q", "-p",
                                f"read_verilog -sv {shlex.quote(reference)}; "
                                f"hierarchy -top {name}; proc; opt; check"])
    proof = run_wsl(["yosys", "-Q", "-p",
                     f"read_verilog -sv {shlex.quote(target)} {shlex.quote(reference)} "
                     f"{shlex.quote(miter)}; prep -top {top}; flatten; opt; "
                     "sat -prove mismatch 0"])
    proof["formal_success_marker"] = proof.get("sat_success_marker") is True
    proof["unconstrained"] = proof.get("unconstrained_marker") is True
    counts = proof.get("sat_counts_full")
    if isinstance(counts, list) and len(counts) == 2:
        proof["sat_variables"], proof["sat_clauses"] = counts
    if not proof["formal_success_marker"] or not proof["unconstrained"]:
        proof["status"] = "FAIL"
    proof["formal_scope"] = {
        "input_bits": INPUT_BITS,
        "input_space": f"2**{INPUT_BITS}",
        "input_space_cardinality": str(1 << INPUT_BITS),
        "state_bits": 0,
        "state_space": "singleton (stateless combinational module)",
        "outputs_compared": {"io_out_imm": VARIANTS[name]["data_bits"]},
        "property": "mismatch == 0 for every 2-state valuation of io_in_imm/io_in_immType",
    }
    return {
        "verilator": verilator,
        "yosys_target": yosys_target,
        "yosys_reference": yosys_reference,
        "yosys_formal_miter": proof,
    }


def formal_aggregate(paths: dict[str, Any]) -> dict[str, Any]:
    """Prove all five variants simultaneously over the same full input space."""

    reference = wsl_path(paths["reference"])
    aggregate = wsl_path(paths["aggregate"])
    targets = [wsl_path(paths["targets"][name]) for name in VARIANTS]
    all_sources = [*targets, reference, aggregate]
    source_args = " ".join(shlex.quote(path) for path in all_sources)
    verilator = run_wsl([
        "verilator", "--lint-only", "-Wno-fatal", "--top-module",
        "ImmExtractor_ALL_MITER", *all_sources,
    ])
    yosys_check = run_wsl(["yosys", "-Q", "-p",
                           f"read_verilog -sv {source_args}; "
                           "hierarchy -top ImmExtractor_ALL_MITER; proc; opt; check"])
    proof = run_wsl(["yosys", "-Q", "-p",
                     f"read_verilog -sv {source_args}; prep -top ImmExtractor_ALL_MITER; "
                     "flatten; opt; sat -prove mismatch 0"])
    proof["formal_success_marker"] = proof.get("sat_success_marker") is True
    proof["unconstrained"] = proof.get("unconstrained_marker") is True
    proof["mitered_variants"] = len(VARIANTS)
    counts = proof.get("sat_counts_full")
    if isinstance(counts, list) and len(counts) == 2:
        proof["sat_variables"], proof["sat_clauses"] = counts
    if not proof["formal_success_marker"] or not proof["unconstrained"]:
        proof["status"] = "FAIL"
    proof["formal_scope"] = {
        "input_bits": INPUT_BITS,
        "input_space": f"2**{INPUT_BITS}",
        "input_space_cardinality": str(1 << INPUT_BITS),
        "state_bits": 0,
        "state_space": "five stateless combinational variants sharing one input valuation",
        "outputs_compared": {
            name: {"io_out_imm": spec["data_bits"]} for name, spec in VARIANTS.items()
        },
        "total_compared_output_bits": sum(spec["data_bits"] for spec in VARIANTS.values()),
        "property": "OR of all five variant mismatches == 0 for every 2-state input valuation",
    }
    return {
        "status": "PASS" if all(item["status"] == "PASS" for item in
                                  (verilator, yosys_check, proof)) else "FAIL",
        "verilator": verilator,
        "yosys_check": yosys_check,
        "yosys_formal_miter": proof,
    }


def abi_audit(paths: dict[str, Any]) -> dict[str, Any]:
    """Check every target/reference ABI and complete-output miter."""

    reference = paths["reference"].read_text(encoding="utf-8")
    rows: dict[str, Any] = {}
    for name, spec in VARIANTS.items():
        target = paths["targets"][name].read_text(encoding="utf-8")
        miter = paths["miters"][name].read_text(encoding="utf-8")
        width = spec["data_bits"]
        checks = {
            "target_module": f"module DUT_{name}(" in target,
            "reference_module": f"module {name}(" in reference,
            "target_inputs": bool(re.search(r"input\s+\[31:0\]\s+io_in_imm", target))
                             and bool(re.search(r"input\s+\[3:0\]\s+io_in_immType", target)),
            "reference_inputs": "io_in_imm" in module_body(reference, name)
                                and "io_in_immType" in module_body(reference, name),
            "target_output": bool(re.search(
                rf"output\s+\[{width - 1}:0\]\s+io_out_imm", target)),
            "reference_output": bool(re.search(
                rf"output\s+\[{width - 1}:0\]\s+io_out_imm", module_body(reference, name))),
            "inputs_connected_twice": miter.count(".io_in_imm(io_in_imm)") == 2
                                      and miter.count(".io_in_immType(io_in_immType)") == 2,
            "complete_output_compared": "reference_out ^ target_out" in miter,
            "no_assume": "assume" not in miter.lower(),
        }
        rows[name] = {"status": "PASS" if all(checks.values()) else "FAIL",
                      "checks": checks}
    return {"status": "PASS" if all(row["status"] == "PASS" for row in rows.values()) else "FAIL",
            "rows": rows}


def negative_control(paths: dict[str, Any]) -> dict[str, Any]:
    """Mutate one representative variant on both sides and require SAT models."""

    name = "ImmExtractor"
    results: dict[str, Any] = {}
    for side in ("target", "reference"):
        source_path = paths["targets"][name] if side == "target" else paths["reference"]
        source = source_path.read_text(encoding="utf-8")
        module = f"DUT_{name}" if side == "target" else name
        start = source.find(f"module {module}(")
        end = source.find("endmodule", start)
        body = source[start:end] if start >= 0 and end >= 0 else ""
        mutated_body, count = re.subn(r"assign\s+io_out_imm\s*=\s*.*?;",
                                      "assign io_out_imm = 64'h0;", body,
                                      count=1, flags=re.S)
        if count != 1:
            results[side] = {"status": "FAIL", "mutation_applied": False}
            continue
        mutant = WORK / f"MUTANT_{side}_{name}.sv"
        mutant.write_text(source[:start] + mutated_body + source[end:],
                          encoding="utf-8", newline="\n")
        target = mutant if side == "target" else paths["targets"][name]
        reference = paths["reference"] if side == "target" else mutant
        converted = {"target": wsl_path(target), "reference": wsl_path(reference),
                     "miter": wsl_path(paths["miters"][name])}
        script = (f"read_verilog -sv {converted['target']} {converted['reference']} {converted['miter']}; "
                  f"prep -top {name}_MITER; flatten; opt; sat -prove mismatch 0")
        verdict = run_wsl(["yosys", "-Q", "-p", script])
        detected = (isinstance(verdict.get("returncode"), int)
                    and verdict.get("sat_counterexample_marker") is True
                    and verdict.get("sat_success_marker") is not True)
        results[side] = {"status": "PASS" if detected else "FAIL",
                         "mutation_applied": True,
                         "counterexample_marker": verdict.get("sat_counterexample_marker"),
                         "success_marker_still_present": verdict.get("sat_success_marker")}
    return {"status": "PASS" if all(item["status"] == "PASS" for item in results.values()) else "FAIL",
            "sides": results, "control_variant": name, "two_sided": True}


def validate() -> dict[str, Any]:
    """Run all strict gates; only five proofs plus aggregate can pass status."""

    closure = closure_audit()
    failures: list[str] = []
    if closure["status"] != "PASS":
        failures.append("closure/configuration audit")
    module = load_target()
    py_compile.compile(str(TARGET), doraise=True)
    py_compile.compile(str(Path(__file__)), doraise=True)
    exported, deterministic = export_targets(module)
    paths = materialize_sources(exported)
    abi = abi_audit(paths)
    variant_formal = {name: formal_one(name, paths) for name in VARIANTS}
    aggregate = formal_aggregate(paths)
    control = negative_control(paths)
    pyright = {"target": pyright_check(TARGET),
               "validator": pyright_check(Path(__file__))}
    for name, result in deterministic.items():
        if result["status"] != "PASS":
            failures.append(f"deterministic export {name}")
    if abi["status"] != "PASS":
        failures.append("ABI/miter audit")
    if control["status"] != "PASS":
        failures.append("two-sided negative control")
    for name, result in pyright.items():
        if result["status"] != "PASS":
            failures.append(f"pyright {name}")
    for name, gates in variant_formal.items():
        for gate_name, result in gates.items():
            if result["status"] != "PASS":
                failures.append(f"{name} {gate_name}")
    if aggregate["status"] != "PASS":
        failures.append("aggregate formal gates")
    status = "COMPLETE_EQUIVALENCE" if not failures else "STRICT_PENDING"
    closure_hash = sha256_file(REFERENCE)
    module_hashes = reference_module_hashes()
    variant_claims = {
        name: {
            "method": "sat_miter",
            "sequential": False,
            "locked_reference": REFERENCE.relative_to(ROOT).as_posix(),
            "locked_sha256": closure_hash,
            "locked_module_sha256": module_hashes[name]["sha256"],
            "inputs": INPUT_WIDTHS,
            "outputs_compared": {"io_out_imm": spec["data_bits"]},
            "input_bits": INPUT_BITS,
            "output_bits": spec["data_bits"],
            "abi_exact": abi["rows"][name]["status"] == "PASS",
            "deterministic": deterministic[name]["status"] == "PASS",
            "miter_selfcheck": abi["rows"][name]["status"] == "PASS",
            "sat": variant_formal[name]["yosys_formal_miter"],
            "data_bits": spec["data_bits"],
            "imm_type_set": list(spec["imm_type_set"]),
            "imm_type_names": list(spec["imm_type_names"]),
        }
        for name, spec in VARIANTS.items()
    }
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_STRICT_COMPLETE_EQUIVALENCE",
        "build_id": "Build-Cpu.Backend.Issue.ImmExtractor",
        "validator": Path(__file__).relative_to(ROOT).as_posix(),
        "status": status,
        "strict_complete_eligible": status == "COMPLETE_EQUIVALENCE",
        "strict_complete_count_delta": 1 if status == "COMPLETE_EQUIVALENCE" else 0,
        "acceptance_eligible": status == "COMPLETE_EQUIVALENCE",
        "source_commit": SOURCE_COMMIT,
        "audit_policy": {"require_negative_control": True,
                         "require_two_sided_negative_control": True,
                         "require_unconstrained_sat": True,
                         "require_all_variants_and_outputs_compared": True,
                         "scope_source": "locked ImmExtractor family closure"},
        "scope": {
            "kind": "five_locked_stateless_combinational_specializations",
            "public_variants": list(VARIANTS),
            "variant_count": len(VARIANTS),
            "inputs": INPUT_WIDTHS,
            "input_bits": INPUT_BITS,
            "input_space": f"2**{INPUT_BITS}",
            "input_space_cardinality": str(1 << INPUT_BITS),
            "state_bits": 0,
            "state_boundary": "no clock/reset/register/memory in any reference or target variant",
            "variants": variant_claims,
            "outputs_compared": {
                name: {"io_out_imm": spec["data_bits"]}
                for name, spec in VARIANTS.items()
            },
            "aggregate_compared_output_bits": sum(
                spec["data_bits"] for spec in VARIANTS.values()
            ),
            "why_complete": (
                "Each individual SAT miter and an aggregate OR-miter prove zero mismatch "
                "with all 36 ABI input bits unconstrained."
            ),
            "bounded_tests_counted": False,
        },
        "reference_lock": {
            "path": LOCKED_XSTOP,
            "upstream_source_commit": SOURCE_COMMIT,
            "xstop_sha256": XSTOP_SHA256,
            "xstop_bytes": XSTOP_BYTES,
            "closure_audit": closure,
            "abi": abi,
            "extraction_rule": "exact five public ImmExtractor module bodies copied from immutable XSTop.sv; no dependencies",
        },
        "sources": {
            "scala": {"path": SCALA.relative_to(ROOT).as_posix(),
                      "sha256": sha256_file(SCALA), "bytes": SCALA.stat().st_size},
            "python_build": {"path": TARGET.relative_to(ROOT).as_posix(),
                             "sha256": sha256_file(TARGET), "bytes": TARGET.stat().st_size},
            "reference_sv": {"path": REFERENCE.relative_to(ROOT).as_posix(),
                             "sha256": sha256_file(REFERENCE), "bytes": REFERENCE.stat().st_size,
                             "modules": list(VARIANTS)},
            "reference_manifest": {"path": MANIFEST.relative_to(ROOT).as_posix(),
                                   "sha256": sha256_file(MANIFEST), "bytes": MANIFEST.stat().st_size},
        },
        "checks": {
            "py_compile": {"status": "PASS", "files": [
                TARGET.relative_to(ROOT).as_posix(),
                Path(__file__).relative_to(ROOT).as_posix(),
            ]},
            "pyright": pyright,
            "deterministic_export": deterministic,
            "closure_audit": closure,
            "tools": tool_versions(),
            "variants": variant_formal,
            "formal": aggregate,
            "aggregate_sat_miter": aggregate,
            "negative_control": control,
        },
        "failures": failures,
        "unclosed": [] if not failures else ["strict gates did not all pass"],
        "acceptance_unclosed": [
            "Backend/Issue parent closure, license review and user approval remain outside this proof."
        ],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    return payload


def main() -> int:
    """Print strict status and return nonzero until all gates pass."""

    payload = validate()
    print(json.dumps({"status": payload["status"],
                      "strict_complete_eligible": payload["strict_complete_eligible"],
                      "failures": payload["failures"]}, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
