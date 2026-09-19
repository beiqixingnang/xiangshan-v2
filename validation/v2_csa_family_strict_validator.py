"""Strict complete-equivalence proof for the whole locked CSA family.

The CSA Build exposes bit-parallel 2:2, 3:2 and 5:3 compressors plus their
one-bit aliases.  The locked corpus contains exactly thirteen specializations of
that family, so this validator proves every one of them individually and again
through a single aggregate miter, which is what makes the whole Build file
countable rather than a single member of it.

Module names are reconciled by renaming: every Build-generated top becomes
``DUT_<tag>``, every locked top becomes ``REF_<stem>``, and locked child bodies
keep their original names so an instance such as C53's internal CSA3_2 still
resolves.  Locked references are read verbatim from validation/reference-sv and
are never written.
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
    "Build-Cpu.Backend.Fu.Util.CSA-Hardware.py"
)
SCALA = ROOT / "upstream/src/main/scala/xiangshan/backend/fu/util/CSA.scala"
REF_DIR = ROOT / "validation/reference-sv"
EVIDENCE = ROOT / "validation/v2-csa-family-strict-evidence.json"
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_csa_family_strict"

SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
SAT_SUCCESS_MARKER = "SAT proof finished - no model found: SUCCESS!"
ANSI_PORT = re.compile(r"^(input|output)\s+(?:\[(\d+):0\]\s*)?(.+)$")

# Locked CSA3_2 specializations are emitted with a suffix per width.
CSA3_2_WIDTHS: dict[int, str | None] = {
    1: None, 8: "3988", 9: "3992", 10: "3956", 11: "4017",
    13: "3962", 22: "3987", 38: "4111", 68: "3960", 70: "4173",
}


def locked_targets() -> list[dict[str, Any]]:
    """Return the thirteen locked CSA specializations this Build must cover."""

    entries: list[dict[str, Any]] = []
    for length, suffix in sorted(CSA3_2_WIDTHS.items(), key=lambda item: item[1] or ""):
        stem = "CSA3_2" if suffix is None else f"CSA3_2_{suffix}"
        entries.append({"tag": stem, "member": "CSA3_2", "length": length,
                        "locked": stem, "children": []})
    entries.append({"tag": "C22", "member": "C22", "length": 1, "locked": "C22", "children": []})
    entries.append({"tag": "C32", "member": "C32", "length": 1, "locked": "C32", "children": []})
    entries.append({"tag": "C53", "member": "C53", "length": 1, "locked": "C53",
                    "children": ["CSA3_2"]})
    return entries


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one exact file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_target() -> Any:
    """Load the CSA Build by exact path."""

    spec = importlib.util.spec_from_file_location("strict_csa_family_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load target: {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def wsl_path(path: Path) -> str:
    """Convert a Windows path into an absolute WSL path."""

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
        "output_tail": output[-3000:],
        "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
    }


def pyright_check(source: Path) -> dict[str, Any]:
    """Run Pyright on an exact visible copy of one source file."""

    temporary = Path(tempfile.mkdtemp(prefix="uhsc_csa_family_pyright_"))
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
            "stderr_tail": result.stderr[-800:],
        }
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def strip_line(line: str) -> str:
    """Drop a SystemVerilog line comment."""

    return re.sub(r"//.*", "", line).strip()


def ansi_ports(rtl: str, module: str) -> dict[str, tuple[str, int]]:
    """Read a Chisel ANSI declaration, letting grouped names inherit width."""

    header = re.search(r"module\s+" + re.escape(module) + r"\s*\((.*?)\)\s*[;:]", rtl, re.S)
    if header is None:
        return {}
    ports: dict[str, tuple[str, int]] = {}
    direction: str | None = None
    width = 1
    for raw in header.group(1).splitlines():
        line = strip_line(raw).rstrip(",").strip()
        if not line:
            continue
        declared = ANSI_PORT.match(line)
        if declared is not None:
            direction = str(declared.group(1))
            width = int(declared.group(2)) + 1 if declared.group(2) else 1
            names: list[str] = [item.strip() for item in declared.group(3).split(",") if item.strip()]
        else:
            if direction is None:
                continue
            names = [item.strip() for item in line.split(",") if item.strip()]
        for name in names:
            ports[name] = (direction, width)
    return ports


def nonansi_ports(rtl: str, module: str) -> dict[str, tuple[str, int]]:
    """Read an Amaranth header-plus-body declaration."""

    header = re.search(r"module\s+" + re.escape(module) + r"\s*\(([^)]*)\)\s*;", rtl, re.S)
    if header is None:
        return {}
    wanted = [item for item in (name.strip() for name in
                                strip_line(header.group(1)).replace("\n", " ").split(",")) if item]
    ports: dict[str, tuple[str, int]] = {}
    for raw in rtl[header.end():].splitlines():
        declared = ANSI_PORT.match(strip_line(raw).rstrip(";").strip())
        if declared is None:
            continue
        width = int(declared.group(2)) + 1 if declared.group(2) else 1
        for name in [item.strip() for item in declared.group(3).split(",") if item.strip()]:
            if name in wanted and name not in ports:
                ports[name] = (str(declared.group(1)), width)
    return ports


def declared_ports(rtl: str, module: str) -> dict[str, tuple[str, int]]:
    """Return whichever declaration style one module actually uses."""

    return ansi_ports(rtl, module) or nonansi_ports(rtl, module)


def rename_module(rtl: str, old: str, new: str) -> str:
    """Rename one module declaration and any instantiations of it."""

    renamed = rtl.replace(f"module {old}(", f"module {new}(", 1)
    return re.sub(rf"(?m)(^\s*){re.escape(old)}(\s+\S+\s*\()", rf"\g<1>{new}\g<2>", renamed)


def build_target_rtl(module: Any, entry: dict[str, Any]) -> str:
    """Emit the Build's version of one locked specialization, renamed per tag."""

    config = module.CSAConfig(length=entry["length"], member=entry["member"])
    rtl = module.build_verilog(config, None)
    return rename_module(rtl, entry["member"], f"DUT_{entry['tag']}")


def build_reference_rtl(entry: dict[str, Any]) -> str:
    """Read the locked reference verbatim, renaming only its top module."""

    locked = (REF_DIR / f"{entry['locked']}.sv").read_text(encoding="utf-8")
    renamed = locked.replace(f"module {entry['locked']}(", f"module REF_{entry['locked']}(", 1)
    children = []
    for child in entry["children"]:
        child_text = (REF_DIR / f"{child}.sv").read_text(encoding="utf-8")
        if f"module {child}(" not in child_text:
            raise AssertionError(f"locked child {child} declaration missing")
        children.append(child_text)
    return "\n".join(children) + "\n" + renamed


def miter_text(entry: dict[str, Any], inputs: dict[str, int], outputs: dict[str, int]) -> str:
    """Emit a miter whose mismatch ORs every declared output lane."""

    dut, ref = f"DUT_{entry['tag']}", f"REF_{entry['locked']}"
    lines = [f"module {entry['tag']}_MITER("]
    for name, width in inputs.items():
        lines.append(f"  input [{width - 1}:0] {name}," if width > 1 else f"  input {name},")
    lines.append("  output mismatch")
    lines.append(");")
    for name, width in outputs.items():
        lines.append(f"  wire [{width - 1}:0] ref_{name};")
        lines.append(f"  wire [{width - 1}:0] dut_{name};")
    for prefix, instance, top in (("ref_", "reference_i", ref), ("dut_", "target_i", dut)):
        connections = [f".{name}({name})" for name in inputs]
        connections += [f".{name}({prefix}{name})" for name in outputs]
        lines.append(f"  {top} {instance}(")
        lines.append("    " + ", ".join(connections))
        lines.append("  );")
    terms = [f"(ref_{name} != dut_{name})" for name in outputs]
    lines.append("  assign mismatch = " + " | ".join(terms) + ";")
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def prepare(module: Any) -> list[dict[str, Any]]:
    """Materialize every target/reference/miter triple and audit each surface."""

    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)
    prepared: list[dict[str, Any]] = []
    for entry in locked_targets():
        target_rtl = build_target_rtl(module, entry)
        reference_rtl = build_reference_rtl(entry)
        reference_ports = declared_ports((REF_DIR / f"{entry['locked']}.sv").read_text(encoding="utf-8"),
                                         entry["locked"])
        target_ports = declared_ports(target_rtl, f"DUT_{entry['tag']}")
        inputs = {name: width for name, (direction, width) in reference_ports.items()
                  if direction == "input"}
        outputs = {name: width for name, (direction, width) in reference_ports.items()
                   if direction == "output"}
        first, second = build_target_rtl(module, entry), build_target_rtl(module, entry)
        target_path = WORK / f"DUT_{entry['tag']}.sv"
        reference_path = WORK / f"REF_{entry['tag']}.sv"
        miter_path = WORK / f"{entry['tag']}_MITER.sv"
        target_path.write_text(target_rtl, encoding="utf-8", newline="\n")
        reference_path.write_text(reference_rtl, encoding="utf-8", newline="\n")
        miter_text_value = miter_text(entry, inputs, outputs)
        miter_path.write_text(miter_text_value, encoding="utf-8", newline="\n")
        declared = set(re.findall(r"^\s*(?:input|output|wire)\s+(?:\[\d+:0\]\s*)?([A-Za-z_]\w*)",
                                  miter_text_value, re.M))
        connected = {net for net in re.findall(r"\.\w+\(([^()]+)\)", miter_text_value)}
        prepared.append({
            "entry": entry, "inputs": inputs, "outputs": outputs,
            "abi_ok": target_ports == reference_ports,
            "deterministic_ok": first.encode("utf-8") == second.encode("utf-8"),
            "miter_selfcheck": bool(connected) and connected <= declared,
            "target": target_path, "reference": reference_path, "miter": miter_path,
        })
    return prepared


def prove(item: dict[str, Any]) -> dict[str, Any]:
    """Lint, check and prove one specialization."""

    entry = item["entry"]
    target = wsl_path(item["target"])
    reference = wsl_path(item["reference"])
    miter = wsl_path(item["miter"])
    lint = run_wsl(["verilator", "--lint-only", "-Wno-fatal", "--top-module",
                    f"{entry['tag']}_MITER", target, reference, miter])
    check_target = run_wsl(["yosys", "-Q", "-p",
                            f"read_verilog -sv {shlex.quote(target)}; hierarchy -top DUT_{entry['tag']}; proc; opt; check"])
    check_reference = run_wsl(["yosys", "-Q", "-p",
                               f"read_verilog -sv {shlex.quote(reference)}; "
                               f"hierarchy -top REF_{entry['locked']}; proc; opt; check"])
    script = (f"read_verilog -sv {shlex.quote(target)} {shlex.quote(reference)} "
              f"{shlex.quote(miter)}; prep -top {entry['tag']}_MITER; flatten; opt; "
              "sat -prove mismatch 0")
    proof = run_wsl(["yosys", "-Q", "-p", script])
    output = proof.get("output_tail", "")
    proof["formal_success_marker"] = SAT_SUCCESS_MARKER in output
    proof["unconstrained"] = "Final constraint equation: { } = { }" in output
    counts = re.findall(r"Solving problem with (\d+) variables and (\d+) clauses", output)
    if counts:
        proof["sat_variables"], proof["sat_clauses"] = (int(counts[-1][0]), int(counts[-1][1]))
    if not proof["formal_success_marker"] or not proof["unconstrained"]:
        proof["status"] = "FAIL"
    return {"verilator": lint, "yosys_check_target": check_target,
            "yosys_check_reference": check_reference, "sat_miter": proof}


def aggregate_proof(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Instantiate every specialization miter and OR their mismatches once."""

    sources = " ".join(shlex.quote(wsl_path(path))
                       for item in items
                       for path in (item["target"], item["reference"], item["miter"]))
    lines = ["module CSA_FAMILY_MITER("]
    declarations: list[str] = []
    for item in items:
        tag = item["entry"]["tag"]
        for name, width in item["inputs"].items():
            lines.append(f"  input [{width - 1}:0] {tag}_{name}," if width > 1
                         else f"  input {tag}_{name},")
    lines.append("  output mismatch")
    lines.append(");")
    terms: list[str] = []
    for index, item in enumerate(items):
        tag = item["entry"]["tag"]
        term = f"m{index}"
        terms.append(term)
        lines.append(f"  wire {term};")
        connections = [f".{name}({tag}_{name})" for name in item["inputs"]]
        connections.append(f".mismatch({term})")
        lines.append(f"  {tag}_MITER mit{index}(")
        lines.append("    " + ", ".join(connections))
        lines.append("  );")
    lines.append("  assign mismatch = " + " | ".join(terms) + ";")
    lines.append("endmodule")
    glue = WORK / "CSA_FAMILY_MITER.sv"
    glue.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    script = (f"read_verilog -sv {sources} {shlex.quote(wsl_path(glue))}; "
              "prep -top CSA_FAMILY_MITER; flatten; opt; sat -prove mismatch 0")
    proof = run_wsl(["yosys", "-Q", "-p", script])
    output = proof.get("output_tail", "")
    proof["formal_success_marker"] = SAT_SUCCESS_MARKER in output
    proof["unconstrained"] = "Final constraint equation: { } = { }" in output
    proof["mitered_variants"] = len(items)
    counts = re.findall(r"Solving problem with (\d+) variables and (\d+) clauses", output)
    if counts:
        proof["sat_variables"], proof["sat_clauses"] = (int(counts[-1][0]), int(counts[-1][1]))
    if not proof["formal_success_marker"] or not proof["unconstrained"]:
        proof["status"] = "FAIL"
    return proof


def negative_control(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Perturb the target and the reference and require the proof to break."""

    widest = max(items, key=lambda item: item["entry"]["length"])
    entry = widest["entry"]
    output_name = sorted(widest["outputs"])[0]
    verdicts: dict[str, Any] = {}
    for side, path in (("target", widest["target"]), ("reference", widest["reference"])):
        source = path.read_text(encoding="utf-8")
        mutated, count = re.subn(rf"assign\s+{re.escape(output_name)}\s*=\s*[^;]+;",
                                 lambda _match: f"assign {output_name} = 1'b0;",
                                 source, count=1)
        if count != 1:
            return {"status": "FAIL", "side": side, "mutation_applied": False,
                    "note": "the control driver was not uniquely found, so the harness "
                            "was never challenged"}
        mutant = WORK / f"MUTANT_{side}_{entry['tag']}.sv"
        mutant.write_text(mutated, encoding="utf-8", newline="\n")
        if side == "target":
            files = [mutant, widest["reference"], widest["miter"]]
        else:
            files = [widest["target"], mutant, widest["miter"]]
        script = ("read_verilog -sv " + " ".join(shlex.quote(wsl_path(item)) for item in files)
                  + f"; prep -top {entry['tag']}_MITER; flatten; opt; sat -prove mismatch 0")
        verdict = run_wsl(["yosys", "-Q", "-p", script])
        output = verdict.get("output_tail", "")
        verdicts[side] = {
            "status": "PASS" if SAT_SUCCESS_MARKER not in output else "FAIL",
            "control_port": output_name,
            "mutation_applied": True,
            "success_marker_still_present": SAT_SUCCESS_MARKER in output,
            "output_tail": output[-700:],
        }
    detected = all(item["status"] == "PASS" for item in verdicts.values())
    return {
        "status": "PASS" if detected else "FAIL",
        "control_target": entry["tag"],
        "sides": verdicts,
        "note": "pinning one output lane on either side must produce a model; a "
                "reference-side mutation that still 'proves' equality means the "
                "reference is not actually reaching the comparison",
    }


def validate() -> dict[str, Any]:
    """Prove the whole locked CSA family and persist the evidence."""

    failures: list[str] = []
    module = load_target()
    py_compile.compile(str(TARGET), doraise=True)
    py_compile.compile(str(Path(__file__)), doraise=True)
    items = prepare(module)
    results = [prove(item) for item in items]
    aggregate = aggregate_proof(items)
    control = negative_control(items)
    pyright = {"target": pyright_check(TARGET), "validator": pyright_check(Path(__file__))}
    for item, result in zip(items, results):
        tag = item["entry"]["tag"]
        if not item["abi_ok"]:
            failures.append(f"ABI mismatch: {tag}")
        if not item["deterministic_ok"]:
            failures.append(f"non-deterministic export: {tag}")
        if not item["miter_selfcheck"]:
            failures.append(f"miter drives implicit nets: {tag}")
        for name, gate in result.items():
            if gate.get("status") != "PASS":
                failures.append(f"{tag}:{name}")
    if aggregate["status"] != "PASS":
        failures.append("aggregate SAT miter")
    if control["status"] != "PASS":
        failures.append("negative control did not detect a mutated target")
    for name, result in pyright.items():
        if result["status"] != "PASS":
            failures.append(f"pyright {name}")
    status = "COMPLETE_EQUIVALENCE" if not failures else "STRICT_PENDING"
    variants: dict[str, Any] = {}
    for index, item in enumerate(items):
        sat = results[index]["sat_miter"]
        entry = item["entry"]
        variants[entry["tag"]] = {
            "member": entry["member"],
            "length": entry["length"],
            "locked_reference": f"validation/reference-sv/{entry['locked']}.sv",
            "locked_sha256": sha256_file(REF_DIR / f"{entry['locked']}.sv"),
            "children": entry["children"],
            "inputs": item["inputs"],
            "outputs_compared": item["outputs"],
            "input_bits": sum(item["inputs"].values()),
            "output_bits": sum(item["outputs"].values()),
            "abi_exact": item["abi_ok"],
            "deterministic": item["deterministic_ok"],
            "sat": {
                "returncode": sat.get("returncode"),
                "status": sat.get("status"),
                "formal_success_marker": sat.get("formal_success_marker"),
                "unconstrained": sat.get("unconstrained"),
                "sat_variables": sat.get("sat_variables"),
                "sat_clauses": sat.get("sat_clauses"),
            },
        }
    total_input_bits = sum(sum(item["inputs"].values()) for item in items)
    total_output_bits = sum(sum(item["outputs"].values()) for item in items)
    aggregate_inputs = {f"{item['entry']['tag']}_{name}": width
                        for item in items for name, width in item["inputs"].items()}
    aggregate_outputs = {f"{item['entry']['tag']}_{name}": width
                         for item in items for name, width in item["outputs"].items()}
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_STRICT_COMPLETE_EQUIVALENCE",
        "build_id": "Build-Cpu.Backend.Fu.Util.CSA",
        "validator": Path(__file__).relative_to(ROOT).as_posix(),
        "status": status,
        "strict_complete_eligible": status == "COMPLETE_EQUIVALENCE",
        "strict_complete_count_delta": 1 if status == "COMPLETE_EQUIVALENCE" else 0,
        "acceptance_eligible": status == "COMPLETE_EQUIVALENCE",
        "source_commit": SOURCE_COMMIT,
        "scope": {
            "kind": "stateless_combinational_multi_variant_build",
            "public_variants": [item["entry"]["tag"] for item in items],
            "variant_count": len(items),
            "state_bits": 0,
            "state_boundary": "no clock/reset/register/memory in any variant; each is one combinational evaluation",
            "variants": variants,
            "inputs": aggregate_inputs,
            "outputs_compared": aggregate_outputs,
            "aggregate_input_bits": total_input_bits,
            "aggregate_compared_output_bits": total_output_bits,
            "aggregate_input_space": f"2**{total_input_bits}",
            "why_complete": "Every one of the thirteen locked CSA specializations is proven "
                            "individually by an unrestricted SAT miter and again through one "
                            "aggregate miter, so no member of this Build file is left unproven.",
            "bounded_tests_counted": False,
        },
        "reference_lock": {
            "directory": "validation/reference-sv",
            "xstop_sha256": XSTOP_SHA256,
            "locked_modules": [item["entry"]["locked"] for item in items],
            "sha256_by_module": {item["entry"]["locked"]:
                                 sha256_file(REF_DIR / f"{item['entry']['locked']}.sv")
                                 for item in items},
            "locked_references_written": False,
        },
        "sources": {
            "scala": {"path": SCALA.relative_to(ROOT).as_posix(), "sha256": sha256_file(SCALA),
                      "bytes": SCALA.stat().st_size},
            "reference_sv": {"path": "validation/reference-sv/CSA3_2.sv",
                             "sha256": sha256_file(REF_DIR / "CSA3_2.sv"),
                             "bytes": (REF_DIR / "CSA3_2.sv").stat().st_size},
            "python_build": {"path": TARGET.relative_to(ROOT).as_posix(),
                             "sha256": sha256_file(TARGET), "bytes": TARGET.stat().st_size},
        },
        "checks": {
            "py_compile": {"status": "PASS"},
            "pyright": pyright,
            "coverage": {
                "locked_csa_specializations": 13,
                "proven": sum(1 for item in items
                              if results[items.index(item)]["sat_miter"].get("status") == "PASS"),
                "surface_derivation": "each compared lane set is parsed from the locked reference file",
            },
            "aggregate_sat_miter": aggregate,
            "formal": {"yosys_formal_miter": aggregate,
                       "variant_sat_miters": len(items)},
            "negative_control": control,
            "variants": results,
        },
        "failures": failures,
        "unclosed": [] if not failures else ["strict gates did not all pass"],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    return payload


def main() -> int:
    """Print strict status and return nonzero until every variant closes."""

    payload = validate()
    scope = payload["scope"]
    print(json.dumps({
        "status": payload["status"],
        "strict_complete_eligible": payload["strict_complete_eligible"],
        "strict_complete_count_delta": payload["strict_complete_count_delta"],
        "variants": scope["variant_count"],
        "aggregate_input_bits": scope["aggregate_input_bits"],
        "aggregate_output_bits": scope["aggregate_compared_output_bits"],
        "negative_control": payload["checks"]["negative_control"]["status"],
        "failures": payload["failures"],
    }, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
