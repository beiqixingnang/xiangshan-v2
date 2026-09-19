"""Complete Build-level equivalence for every locked V2 EnqPolicy variant.

The four generated instances differ only in IssueBlockParams geometry.  This
validator renders each geometry from the shared Build class, proves every
input valuation against its locked SV module, and also proves one aggregate
miter containing all four variants.  No bounded sample is used.
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
    "Build-Cpu.Backend.Issue.EnqPolicy-Hardware.py"
)
SCALA = ROOT / "upstream/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala"
SCALA_PARAMS = ROOT / "upstream/src/main/scala/xiangshan/backend/issue/IssueBlockParams.scala"
SCALA_CONFIG = ROOT / "upstream/src/main/scala/xiangshan/Parameters.scala"
REFERENCE_DIR = ROOT / "validation/reference-sv"
REFERENCE_CLOSURE = ROOT / "validation/reference-closures/EnqPolicies-v2.sv"
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_enqpolicy_strict"
EVIDENCE = ROOT / "validation/v2-enqpolicy-strict-evidence.json"

# Widths are read from the locked ports; numEnq is two in all parent configs.
VARIANTS = ("EnqPolicy", "EnqPolicy_8", "EnqPolicy_14", "EnqPolicy_18")
CONFIGS = {
    "EnqPolicy": {"num_entries": 24, "num_enq": 2, "free_slots": 22,
                  "parents": ["EntriesAluMulBkuBrhJmp", "EntriesAluBrhJmpI2fVsetriwiVsetriwvfI2v", "EntriesAluCsrFenceDiv"],
                  "source_refs": ["Parameters.scala:402,406,410,414; IssueQueueSize=24", "Entries.scala:72-73"]},
    "EnqPolicy_8": {"num_entries": 18, "num_enq": 2, "free_slots": 16,
                    "parents": ["EntriesFaluFcvtF2vFmacFdiv", "EntriesFaluFmacFdiv", "EntriesFaluFmac"],
                    "source_refs": ["Parameters.scala:429,433,436; numEntries=18", "Entries.scala:72-73"]},
    "EnqPolicy_14": {"num_entries": 16, "num_enq": 2, "free_slots": 14,
                     "parents": ["EntriesVfmaVialuFixVimacVppuVfaluVfcvtVipuVsetrvfwvf", "EntriesVfmaVialuFixVfalu", "EntriesStaMou", "EntriesLdu", "EntriesVlduVstuVseglduVsegstu", "EntriesVlduVstu", "EntriesStdMoud"],
                     "source_refs": ["Parameters.scala:451,455,474,477,480,483,486,489,492,495,498; numEntries=16", "Entries.scala:72-73"]},
    "EnqPolicy_18": {"num_entries": 10, "num_enq": 2, "free_slots": 8,
                     "parents": ["EntriesVfdivVidiv"],
                     "source_refs": ["Parameters.scala:458; numEntries=10", "Entries.scala:72-73"]},
}
LOCKED_LINES = {"EnqPolicy": [821033, 821317], "EnqPolicy_8": [897526, 897684],
                "EnqPolicy_14": [937214, 937338], "EnqPolicy_18": [972554, 972600]}
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
SUCCESS_MARKER = "SAT proof finished - no model found: SUCCESS!"
MODEL_FOUND_MARKER = "SAT proof finished - model found: FAIL!"
FREE_INPUT_MARKER = "Final constraint equation: { } = { }"
EXPECTED_HASHES = {
    "python_build": "b08f386e7dc5c6b2e1ab9115d1afc23c517644ebca6200a6b2854461a9aba45a",
    "scala": "e0218e99d01c9073f38ba8d039ea611c98bf25c83bceb560415e044fc8789caf",
    "scala_params": "205889be81f4b38dfa3cf8b0ba0dd287e9cf45bd4b859234ac1de249580188c9",
    "scala_config": "c05cdbbce53b1900724604e572e4f2a46b84b10da0e4ff17f005d8f68a25ac82",
    "reference_closure": "0856b5c89a4ad271f4413315678771df96531080e523ff370d2fb6e6805102fd",
}
EXPECTED_REFERENCE_HASHES = {
    "EnqPolicy": "a90196183e60966582956fd8bbb524e780091015eaa844b1913afef85dd1e002",
    "EnqPolicy_8": "19903908e68824e4ad8e5b7294758e92b80c25c63ea6608b54dcdd668acf0c4a",
    "EnqPolicy_14": "ee5adda91cbb492b85f3f8edc183321b813282d50a795dc5ed892efaf1cdd84e",
    "EnqPolicy_18": "8b5eca1ea67a9393fb92030ed05414ee6df6bddaa5d33dfeaeb22b7b89f5ede6",
}


# Hash exact bytes for reproducible source and closure identity.
def sha256_file(path: Path) -> str:
    """Return one file's SHA-256 digest."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# Return hashes of each exact module slice in the locked closure.
def reference_module_hashes() -> dict[str, Any]:
    """Return byte/hash records for every EnqPolicy module."""

    records: dict[str, Any] = {}
    for name in VARIANTS:
        path = REFERENCE_DIR / f"{name}.sv"
        if not path.is_file():
            raise AssertionError(f"missing module {name}")
        body = path.read_bytes()
        records[name] = {"bytes": len(body),
                         "sha256": hashlib.sha256(body).hexdigest(),
                         "path": path.relative_to(ROOT).as_posix()}
    return records


# Load the precise Build module.
def load_target() -> Any:
    """Load EnqPolicy Build by exact path."""

    spec = importlib.util.spec_from_file_location("strict_enqpolicy_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Convert one Windows path to WSL spelling.
def wsl_path(path: Path) -> str:
    """Return WSL absolute path."""

    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                            capture_output=True, check=True)
    return result.stdout.decode("utf-8", "replace").strip()


# Execute one WSL command with bounded machine-readable output.
def run_wsl(command: list[str]) -> dict[str, Any]:
    """Run a WSL command."""

    rendered = " ".join(shlex.quote(item) for item in command)
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered],
                            capture_output=True, check=False)
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    equiv_totals = re.findall(r"Found (\d+) \$equiv cells in", output)
    equiv_summary = re.findall(r"Of those cells (\d+) are proven and (\d+) are unproven", output)
    sat_counts = re.findall(r"Solving problem with (\d+) variables and (\d+) clauses", output)
    return {"command": command, "returncode": result.returncode,
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "sat_success_marker": SUCCESS_MARKER in output,
            "sat_counterexample_marker": MODEL_FOUND_MARKER in output,
            "unconstrained_marker": FREE_INPUT_MARKER in output,
            "equiv_success_markers": {
                "0 are unproven.": "0 are unproven." in output,
                "Equivalence successfully proven!": "Equivalence successfully proven!" in output,
            },
            "equiv_cells_full": int(equiv_totals[-1]) if equiv_totals else None,
            "equiv_summary_full": [int(v) for v in equiv_summary[-1]] if equiv_summary else None,
            "sat_counts_full": [int(v) for v in sat_counts[-1]] if sat_counts else None,
            "output_tail": output[-3000:],
            "output_sha256": hashlib.sha256(output.encode()).hexdigest()}


# Collect exact backend versions.
def tool_versions() -> dict[str, Any]:
    """Return Verilator/Yosys version records."""

    return {"verilator": run_wsl(["verilator", "--version"]),
            "yosys": run_wsl(["yosys", "--version"])}


# Run Pyright on a visible copy.
def pyright_check(source: Path) -> dict[str, Any]:
    """Run Pyright and return its summary."""

    temporary = Path(tempfile.mkdtemp(prefix="uhsc_enqpolicy_pyright_"))
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


# Render one configured variant directly from the Build's public class.
def render_variant(module: Any, name: str) -> str:
    """Return deterministic Verilog for one locked geometry."""

    from amaranth.back import verilog

    cfg = CONFIGS[name]
    top = module.EnqPolicy(module.EnqPolicyConfig(
        num_entries=cfg["num_entries"], num_enq=cfg["num_enq"]))
    return verilog.convert(top, name=name,
                           ports=[top.can_enq, *top.selection_valid,
                                  *top.selection_bits], emit_src=False)


# Render all variants twice, plus the generic adapter smoke.
def deterministic_exports(module: Any) -> tuple[dict[str, str], dict[str, Any]]:
    """Return target RTL and deterministic evidence."""

    rendered: dict[str, str] = {}
    evidence: dict[str, Any] = {}
    for name in VARIANTS:
        first, second = render_variant(module, name), render_variant(module, name)
        first_bytes, second_bytes = first.encode(), second.encode()
        rendered[name] = first
        evidence[name] = {"status": "PASS" if first_bytes == second_bytes else "FAIL",
                          "bytes": len(first_bytes),
                          "sha256": hashlib.sha256(first_bytes).hexdigest(),
                          "repeat_sha256": hashlib.sha256(second_bytes).hexdigest(),
                          "byte_equal": first_bytes == second_bytes}
    first = module.build_verilog(None, {})
    second = module.build_verilog(None, {})
    evidence["build_verilog_adapter"] = {
        "status": "PASS" if first == second else "FAIL", "module": "EnqPolicy",
        "bytes": len(first.encode()), "sha256": hashlib.sha256(first.encode()).hexdigest(),
        "repeat_sha256": hashlib.sha256(second.encode()).hexdigest(),
        "byte_equal": first == second}
    return rendered, evidence


# Write one variant's target/reference/miter files.
def materialize_variant(name: str, target_rtl: str) -> dict[str, Path]:
    """Materialize one exact formal miter."""

    WORK.mkdir(parents=True, exist_ok=True)
    target = WORK / f"UHSC_{name}.sv"
    reference = WORK / f"REF_{name}.sv"
    miter = WORK / f"{name}_MITER.sv"
    target.write_text(target_rtl, encoding="utf-8", newline="\n")
    source = (REFERENCE_DIR / f"{name}.sv").read_text(encoding="utf-8")
    source = source.replace(f"module {name}(", f"module REF_{name}(", 1)
    reference.write_text(source, encoding="utf-8", newline="\n")
    width = CONFIGS[name]["free_slots"]
    outputs = (f"  wire ref_v0, ref_v1, dut_v0, dut_v1;\n"
               f"  wire [{width - 1}:0] ref_b0, ref_b1, dut_b0, dut_b1;\n")
    miter.write_text(
        f"module {name}_MITER(input [{width - 1}:0] io_canEnq, output mismatch);\n"
        + outputs +
        f"  REF_{name} ref_i(.io_canEnq(io_canEnq), .io_enqSelOHVec_0_valid(ref_v0), .io_enqSelOHVec_0_bits(ref_b0), .io_enqSelOHVec_1_valid(ref_v1), .io_enqSelOHVec_1_bits(ref_b1));\n"
        f"  {name} dut_i(.io_canEnq(io_canEnq), .io_enqSelOHVec_0_valid(dut_v0), .io_enqSelOHVec_0_bits(dut_b0), .io_enqSelOHVec_1_valid(dut_v1), .io_enqSelOHVec_1_bits(dut_b1));\n"
        "  assign mismatch = (ref_v0 ^ dut_v0) | (ref_v1 ^ dut_v1) | |(ref_b0 ^ dut_b0) | |(ref_b1 ^ dut_b1);\nendmodule\n",
        encoding="utf-8", newline="\n")
    return {"target": target, "reference": reference, "miter": miter}


def _module_region(rtl: str, module: str) -> tuple[str, str]:
    """Return one module header and body."""

    match = re.search(r"module\s+" + re.escape(module) + r"\s*\(", rtl)
    if match is None:
        return "", ""
    open_index = rtl.find("(", match.start())
    depth = 0
    close_index = -1
    for index in range(open_index, len(rtl)):
        if rtl[index] == "(":
            depth += 1
        elif rtl[index] == ")":
            depth -= 1
            if depth == 0:
                close_index = index
                break
    if close_index < 0:
        return "", ""
    end = rtl.find("endmodule", close_index)
    return rtl[open_index + 1:close_index], rtl[close_index + 1:end if end >= 0 else len(rtl)]


def declared_ports(rtl: str, module: str) -> dict[str, tuple[str, int]]:
    """Parse grouped ANSI or Amaranth bare-header port declarations."""

    header, body = _module_region(rtl, module)
    if not header:
        return {}
    header = re.sub(r"//[^\n]*", "", header)
    items = [item.strip() for item in header.replace("\n", " ").split(",") if item.strip()]
    typed = any(re.match(r"^(input|output)\b", item) for item in items)
    lines = items if typed else [line.strip() for line in body.splitlines()
                                  if re.match(r"^\s*(?:input|output)\b", line)]
    ports: dict[str, tuple[str, int]] = {}
    pending: tuple[str, int] | None = None
    for raw in lines:
        entry = re.sub(r"//[^\n]*", "", raw).strip().rstrip(",;").strip()
        match = re.match(r"^(input|output)\b(?:\s*\[(\d+):0\])?\s*(.*)$", entry)
        if match:
            direction, msb, tail = match.groups()
            pending = (direction, int(msb) + 1 if msb is not None else 1)
            if tail:
                for name in (item.strip() for item in tail.split(",")):
                    if re.fullmatch(r"[A-Za-z_]\w*", name):
                        ports[name] = pending
            continue
        if pending is not None and re.fullmatch(r"[A-Za-z_]\w*", entry):
            ports[entry] = pending
    return ports


def variant_abi_audit(name: str, target_rtl: str, reference_rtl: str) -> dict[str, Any]:
    """Require the exact four-surface ABI for one locked variant."""

    width = CONFIGS[name]["free_slots"]
    expected = {"io_canEnq": ("input", width),
                "io_enqSelOHVec_0_valid": ("output", 1),
                "io_enqSelOHVec_0_bits": ("output", width),
                "io_enqSelOHVec_1_valid": ("output", 1),
                "io_enqSelOHVec_1_bits": ("output", width)}
    target = declared_ports(target_rtl, name)
    reference = declared_ports(reference_rtl, f"REF_{name}")
    checks = {"target_exact_port_set": target == expected,
              "reference_exact_port_set": reference == expected,
              "target_reference_port_sets_equal": target == reference}
    return {"status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks,
            "target_declared_ports": {k: list(v) for k, v in target.items()},
            "reference_declared_ports": {k: list(v) for k, v in reference.items()},
            "expected_declared_ports": {k: list(v) for k, v in expected.items()},
            "inputs": {"io_canEnq": width},
            "outputs": {k: v[1] for k, v in expected.items() if v[0] == "output"},
            "port_count": len(expected)}


def miter_selfcheck(text: str, name: str) -> dict[str, Any]:
    """Check that one variant miter declares/compares all connected nets."""

    required = {"io_canEnq", "ref_v0", "ref_v1", "dut_v0", "dut_v1",
                "ref_b0", "ref_b1", "dut_b0", "dut_b1"}
    checks = {"required_nets_present": all(name in text for name in required),
              "outputs_compared": "ref_v0 ^ dut_v0" in text and
                                  "ref_v1 ^ dut_v1" in text and
                                  "ref_b0 ^ dut_b0" in text and
                                  "ref_b1 ^ dut_b1" in text,
              "no_assume": "assume" not in text.lower(),
              "module_named": f"module {name}_MITER" in text}
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}


# Run each variant's complete input-space proof and tool gates.
def formal_variant(name: str, target_rtl: str) -> dict[str, Any]:
    """Run Yosys SAT and Verilator for one EnqPolicy geometry."""

    paths = materialize_variant(name, target_rtl)
    converted = {key: wsl_path(value) for key, value in paths.items()}
    target, reference, miter = converted["target"], converted["reference"], converted["miter"]
    verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal", target, reference, miter])
    target_yosys = run_wsl(["yosys", "-Q", "-p", f"read_verilog -sv {shlex.quote(target)}; hierarchy -top {name}; proc; opt; check"])
    reference_yosys = run_wsl(["yosys", "-Q", "-p", f"read_verilog -sv {shlex.quote(reference)}; hierarchy -top REF_{name}; proc; opt; check"])
    proof_script = (f"read_verilog -sv {shlex.quote(target)} {shlex.quote(reference)} {shlex.quote(miter)}; "
                    f"prep -top {name}_MITER; flatten; opt; sat -prove mismatch 0")
    proof = run_wsl(["yosys", "-Q", "-p", proof_script])
    proof["formal_success_marker"] = proof.get("sat_success_marker") is True
    proof["unconstrained"] = proof.get("unconstrained_marker") is True
    counts = proof.get("sat_counts_full")
    if isinstance(counts, list) and len(counts) == 2:
        proof["sat_variables"], proof["sat_clauses"] = counts
    if not proof["formal_success_marker"] or not proof["unconstrained"]:
        proof["status"] = "FAIL"
    width = CONFIGS[name]["free_slots"]
    proof["formal_scope"] = {"input_bits": width, "input_space": f"2**{width}",
                             "input_space_cardinality": str(1 << width),
                             "state_bits": 0,
                             "state_space": "singleton (stateless combinational module)",
                             "outputs_compared": {"io_enqSelOHVec_0_valid": 1,
                                                   "io_enqSelOHVec_0_bits": width,
                                                   "io_enqSelOHVec_1_valid": 1,
                                                   "io_enqSelOHVec_1_bits": width}}
    target_text = Path(paths["target"]).read_text(encoding="utf-8")
    reference_text = Path(paths["reference"]).read_text(encoding="utf-8")
    abi = variant_abi_audit(name, target_text, reference_text)
    miter_audit = miter_selfcheck(Path(paths["miter"]).read_text(encoding="utf-8"), name)
    return {"verilator": verilator, "yosys_target": target_yosys,
            "yosys_reference": reference_yosys, "yosys_formal_miter": proof,
            "abi": abi, "miter_selfcheck": miter_audit,
            "locked_reference_lint": {"status": reference_yosys.get("status")}}


# Build one aggregate miter with four independent free-slot vectors.
def formal_aggregate(rendered: dict[str, str]) -> dict[str, Any]:
    """Prove all four variants in one 60-input SAT problem."""

    WORK.mkdir(parents=True, exist_ok=True)
    target = WORK / "UHSC_EnqPolicies.sv"
    reference = WORK / "REF_EnqPolicies.sv"
    miter = WORK / "EnqPolicies_MITER.sv"
    target.write_text("\n".join(rendered[name] for name in VARIANTS), encoding="utf-8", newline="\n")
    source = REFERENCE_CLOSURE.read_text(encoding="utf-8")
    for name in VARIANTS:
        source = source.replace(f"module {name}(", f"module REF_{name}(", 1)
    reference.write_text(source, encoding="utf-8", newline="\n")
    ports = ", ".join(f"input [{CONFIGS[n]['free_slots'] - 1}:0] src_{i}" for i, n in enumerate(VARIANTS))
    lines = [f"module EnqPolicies_MITER({ports}, output mismatch);", "  wire mismatch_h, mismatch_s, mismatch_v, mismatch_m;"]
    for i, name in enumerate(VARIANTS):
        w = CONFIGS[name]["free_slots"]
        lines += [f"  wire v0_{i},v1_{i},rv0_{i},rv1_{i};", f"  wire [{w-1}:0] b0_{i},b1_{i},rb0_{i},rb1_{i};",
                  f"  REF_{name} r{i}(.io_canEnq(src_{i}),.io_enqSelOHVec_0_valid(rv0_{i}),.io_enqSelOHVec_0_bits(rb0_{i}),.io_enqSelOHVec_1_valid(rv1_{i}),.io_enqSelOHVec_1_bits(rb1_{i}));",
                  f"  {name} d{i}(.io_canEnq(src_{i}),.io_enqSelOHVec_0_valid(v0_{i}),.io_enqSelOHVec_0_bits(b0_{i}),.io_enqSelOHVec_1_valid(v1_{i}),.io_enqSelOHVec_1_bits(b1_{i}));",
                  f"  assign mismatch_{['h','s','v','m'][i]}=(rv0_{i}^v0_{i})|(rv1_{i}^v1_{i})||(rb0_{i}^b0_{i})||(rb1_{i}^b1_{i});"]
    lines += ["  assign mismatch=mismatch_h|mismatch_s|mismatch_v|mismatch_m;", "endmodule"]
    miter.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    converted = {key: wsl_path(value) for key, value in {"target": target, "reference": reference, "miter": miter}.items()}
    target_wsl, reference_wsl, miter_wsl = converted["target"], converted["reference"], converted["miter"]
    verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal", target_wsl, reference_wsl, miter_wsl])
    script = f"read_verilog -sv {shlex.quote(target_wsl)} {shlex.quote(reference_wsl)} {shlex.quote(miter_wsl)}; prep -top EnqPolicies_MITER; flatten; opt; sat -prove mismatch 0"
    proof = run_wsl(["yosys", "-Q", "-p", script])
    proof["formal_success_marker"] = proof.get("sat_success_marker") is True
    proof["unconstrained"] = proof.get("unconstrained_marker") is True
    proof["mitered_variants"] = len(VARIANTS)
    counts = proof.get("sat_counts_full")
    if isinstance(counts, list) and len(counts) == 2:
        proof["sat_variables"], proof["sat_clauses"] = counts
    if not proof["formal_success_marker"] or not proof["unconstrained"]:
        proof["status"] = "FAIL"
    proof["formal_scope"] = {"input_bits": sum(CONFIGS[n]["free_slots"] for n in VARIANTS),
                             "input_space": "2**60", "input_space_cardinality": str(1 << 60),
                             "state_bits": 0, "state_space": "singleton (four stateless modules)",
                             "variants": list(VARIANTS)}
    return {"verilator": verilator, "yosys_formal_miter": proof}


def _mutate_output(text: str, module: str, port: str, width: int) -> tuple[str, bool]:
    """Pin one output in one selected module to zero."""

    start = text.find(f"module {module}(")
    if start < 0:
        return text, False
    end = text.find("endmodule", start)
    if end < 0:
        return text, False
    body = text[start:end]
    mutated, count = re.subn(
        rf"assign\s+{re.escape(port)}\s*=.*?;",
        f"assign {port} = {width}'h0;", body, count=1, flags=re.S)
    if count != 1:
        return text, False
    return text[:start] + mutated + text[end:], True


def negative_control() -> dict[str, Any]:
    """Mutate one representative target and reference and require SAT models."""

    name = "EnqPolicy_8"
    width = CONFIGS[name]["free_slots"]
    clean_target = WORK / f"UHSC_{name}.sv"
    clean_reference = WORK / f"REF_{name}.sv"
    clean_miter = WORK / f"{name}_MITER.sv"
    if not clean_target.is_file() or not clean_reference.is_file() or not clean_miter.is_file():
        return {"status": "FAIL", "sides": {
            "target": {"status": "FAIL", "mutation_applied": False},
            "reference": {"status": "FAIL", "mutation_applied": False}},
            "two_sided": True}
    results: dict[str, Any] = {}
    for side in ("target", "reference"):
        source_path = clean_target if side == "target" else clean_reference
        module_name = name if side == "target" else f"REF_{name}"
        mutated, applied = _mutate_output(
            source_path.read_text(encoding="utf-8"), module_name,
            "io_enqSelOHVec_0_bits", width)
        mutant = WORK / f"EnqPolicy-{side}-mutant.sv"
        mutant.write_text(mutated, encoding="utf-8", newline="\n")
        if not applied:
            results[side] = {"status": "FAIL", "mutation_applied": False,
                             "clean_proof_marker_disappeared": False,
                             "counterexample_or_unproven": False}
            continue
        target = mutant if side == "target" else clean_target
        reference = clean_reference if side == "target" else mutant
        converted = {k: wsl_path(v) for k, v in
                     {"target": target, "reference": reference,
                      "miter": clean_miter}.items()}
        script = (f"read_verilog -sv {shlex.quote(converted['target'])} "
                  f"{shlex.quote(converted['reference'])} {shlex.quote(converted['miter'])}; "
                  f"prep -top {name}_MITER; flatten; opt; sat -prove mismatch 0")
        verdict = run_wsl(["yosys", "-Q", "-p", script])
        marker_disappeared = not bool(verdict.get("sat_success_marker"))
        counterexample = bool(verdict.get("sat_counterexample_marker"))
        detected = isinstance(verdict.get("returncode"), int) and marker_disappeared and counterexample
        results[side] = {"status": "PASS" if detected else "FAIL",
                         "mutation_applied": True,
                         "control_port": "io_enqSelOHVec_0_bits",
                         "clean_proof_marker_disappeared": marker_disappeared,
                         "counterexample_marker": counterexample,
                         "counterexample_or_unproven": counterexample,
                         "success_marker_still_present": verdict.get("sat_success_marker"),
                         "output_tail": verdict.get("output_tail", "")[-1200:]}
    all_pass = all(item.get("status") == "PASS" for item in results.values())
    return {"status": "PASS" if all_pass else "FAIL", "sides": results,
            "control_variant": name, "two_sided": True,
            "mutation_applied": all(item.get("mutation_applied") is True for item in results.values()),
            "clean_proof_marker_disappeared": all(item.get("clean_proof_marker_disappeared") is True for item in results.values()),
            "counterexample_or_unproven": all(item.get("counterexample_or_unproven") is True for item in results.values())}


def source_lock_audit() -> dict[str, Any]:
    """Verify Build, Scala, closure and every exact variant reference hash."""

    actual = {
        "python_build": sha256_file(TARGET),
        "scala": sha256_file(SCALA),
        "scala_params": sha256_file(SCALA_PARAMS),
        "scala_config": sha256_file(SCALA_CONFIG),
        "reference_closure": sha256_file(REFERENCE_CLOSURE),
    }
    refs = reference_module_hashes()
    observed_refs = {name: str(record["sha256"]) for name, record in refs.items()}
    checks = {f"{name}_hash_locked": actual[name] == expected
              for name, expected in EXPECTED_HASHES.items()}
    checks["variant_reference_hashes_locked"] = observed_refs == EXPECTED_REFERENCE_HASHES
    checks["variant_count"] = len(refs) == len(VARIANTS)
    return {"status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks, "actual": actual, "reference_hashes": refs,
            "source_commit": SOURCE_COMMIT,
            "audit_policy": {"require_negative_control": True,
                             "require_two_sided_negative_control": True,
                             "require_unconstrained_sat": True,
                             "require_locked_reference_lint": True,
                             "scope_source": "Build variant configuration catalog"},
            "xstop": {"path": "validation/reference-closures/EnqPolicies-v2.sv",
                      "sha256": XSTOP_SHA256}}


# Run the complete four-variant Build suite and write evidence.
def validate() -> dict[str, Any]:
    """Run all EnqPolicy strict gates."""

    locks = source_lock_audit()
    module = load_target()
    py_compile.compile(str(TARGET), doraise=True)
    py_compile.compile(str(Path(__file__)), doraise=True)
    rendered, exports = deterministic_exports(module)
    variants = {name: formal_variant(name, rendered[name]) for name in VARIANTS}
    aggregate = formal_aggregate(rendered)
    control = negative_control()
    pyright = {"target": pyright_check(TARGET), "validator": pyright_check(Path(__file__))}
    failures: list[str] = []
    if locks["status"] != "PASS":
        failures.append("source lock audit")
    for name, result in exports.items():
        if result["status"] != "PASS": failures.append(f"deterministic_export:{name}")
    for name, result in pyright.items():
        if result["status"] != "PASS": failures.append(f"pyright:{name}")
    for name, gates in variants.items():
        for gate, result in gates.items():
            if result["status"] != "PASS": failures.append(f"{name}:{gate}")
        if gates.get("abi", {}).get("status") != "PASS": failures.append(f"ABI:{name}")
        if gates.get("miter_selfcheck", {}).get("status") != "PASS": failures.append(f"miter:{name}")
    for gate, result in aggregate.items():
        if result["status"] != "PASS": failures.append(f"aggregate:{gate}")
    if control["status"] != "PASS":
        failures.append("two-sided negative control")
    status = "COMPLETE_EQUIVALENCE" if not failures else "STRICT_PENDING"
    closure_hash = sha256_file(REFERENCE_CLOSURE)
    module_hashes = reference_module_hashes()
    variant_claims = {
        name: {
            "method": "sat_miter",
            "sequential": False,
            "locked_reference": REFERENCE_CLOSURE.relative_to(ROOT).as_posix(),
            "locked_sha256": closure_hash,
            "locked_module_sha256": module_hashes[name]["sha256"],
            "inputs": {"io_canEnq": CONFIGS[name]["free_slots"]},
            "outputs_compared": {
                "io_enqSelOHVec_0_valid": 1,
                "io_enqSelOHVec_0_bits": CONFIGS[name]["free_slots"],
                "io_enqSelOHVec_1_valid": 1,
                "io_enqSelOHVec_1_bits": CONFIGS[name]["free_slots"],
            },
            "input_bits": CONFIGS[name]["free_slots"],
            "output_bits": 2 + 2 * CONFIGS[name]["free_slots"],
            "abi_exact": variants[name]["abi"]["status"] == "PASS",
            "deterministic": exports[name]["status"] == "PASS",
            "miter_selfcheck": variants[name]["miter_selfcheck"]["status"] == "PASS",
            "locked_reference_lint": variants[name]["locked_reference_lint"]["status"],
            "sat": variants[name]["yosys_formal_miter"],
        }
        for name in VARIANTS
    }
    payload: dict[str, Any] = {
        "schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_STRICT_COMPLETE_EQUIVALENCE",
        "build_id": "Build-Cpu.Backend.Issue.EnqPolicy",
        "validator": Path(__file__).relative_to(ROOT).as_posix(), "status": status,
        "strict_complete_eligible": status == "COMPLETE_EQUIVALENCE",
        "strict_complete_count_delta": 1 if status == "COMPLETE_EQUIVALENCE" else 0,
        "acceptance_eligible": status == "COMPLETE_EQUIVALENCE",
        "source_commit": SOURCE_COMMIT,
        "audit_policy": locks["audit_policy"],
        "scope": {"kind": "stateless_combinational_multi_variant_build",
                  "public_variants": list(VARIANTS),
                  "variant_count": len(VARIANTS),
                  "variants": variant_claims,
                  "state_bits": 0, "state_boundary": "no clock/reset/register/memory",
                  "inputs": {n: {"io_canEnq": CONFIGS[n]["free_slots"]} for n in VARIANTS},
                  "outputs_compared": {n: {"io_enqSelOHVec_0_valid": 1, "io_enqSelOHVec_0_bits": CONFIGS[n]["free_slots"], "io_enqSelOHVec_1_valid": 1, "io_enqSelOHVec_1_bits": CONFIGS[n]["free_slots"]} for n in VARIANTS},
                  "input_bits": 60, "input_space": "2**60", "input_space_cardinality": str(1 << 60),
                  "aggregate_complete_cases": "2**22 + 2**16 + 2**14 + 2**8 per isolated variant; 2**60 aggregate",
                  "variant_configurations": CONFIGS,
                  "why_complete": "All four locked EnqPolicy variants have independent and aggregate unrestricted SAT miters comparing every valid/bits output; all are stateless."},
        "sources": {"scala": {"path": SCALA.relative_to(ROOT).as_posix(), "sha256": sha256_file(SCALA), "bytes": SCALA.stat().st_size},
                    "scala_params": {"path": SCALA_PARAMS.relative_to(ROOT).as_posix(), "sha256": sha256_file(SCALA_PARAMS), "bytes": SCALA_PARAMS.stat().st_size},
                    "scala_config": {"path": SCALA_CONFIG.relative_to(ROOT).as_posix(), "sha256": sha256_file(SCALA_CONFIG), "bytes": SCALA_CONFIG.stat().st_size},
                    "scala_dependencies": {
                        "issue_block_params": {"path": SCALA_PARAMS.relative_to(ROOT).as_posix(), "sha256": sha256_file(SCALA_PARAMS), "bytes": SCALA_PARAMS.stat().st_size},
                        "parameters": {"path": SCALA_CONFIG.relative_to(ROOT).as_posix(), "sha256": sha256_file(SCALA_CONFIG), "bytes": SCALA_CONFIG.stat().st_size}},
                    "reference_sv": {"path": REFERENCE_CLOSURE.relative_to(ROOT).as_posix(), "sha256": sha256_file(REFERENCE_CLOSURE), "bytes": REFERENCE_CLOSURE.stat().st_size, "locked_modules": list(VARIANTS), "module_hashes": reference_module_hashes(), "locked_xstop_sha256": XSTOP_SHA256, "locked_xstop_module_lines": LOCKED_LINES},
                    "python_build": {"path": TARGET.relative_to(ROOT).as_posix(), "sha256": sha256_file(TARGET), "bytes": TARGET.stat().st_size}},
        "checks": {"python_version": platform.python_version(), "py_compile": {"status": "PASS"}, "pyright": pyright, "source_lock": locks, "deterministic_exports": exports, "tools": tool_versions(), "variants": variants, "formal": aggregate, "negative_control": control},
        "failures": failures, "unclosed": [] if not failures else ["strict gates did not all pass"],
        "acceptance_unclosed": ["Backend/Issue parent closure, license review and user approval remain outside this proof."]}
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return payload


# Print compact status and fail closed when strict proof is incomplete.
def main() -> int:
    """Run EnqPolicy strict validation."""

    payload = validate()
    print(json.dumps({"status": payload["status"], "strict_complete_eligible": payload["strict_complete_eligible"], "failures": payload["failures"]}, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
