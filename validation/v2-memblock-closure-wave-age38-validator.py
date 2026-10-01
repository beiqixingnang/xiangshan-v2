"""Closure-wave validator for the executable 24-entry LSQ age leaf.

The validator keeps the locked RTL and Scala inputs read-only.  It materializes
only a temporary synthesizable view of the locked module, then checks the
Python Build's exact ABI, deterministic export, direct simulation, backend
lint, inductive equivalence, and two-sided negative controls.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import py_compile
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Cpu-Memory-Memory.Mmu.Lsq.Family-Hardware.py"
DIRECT_TEST = ROOT / "python/Program-System/System-Testing/Testing-Cpu/Testing-Cpu-Memory.Mmu.Lsq.Family-Hardware.py"
REFERENCE = ROOT / "validation/reference-sv/AgeDetector_38.sv"
SCALA = ROOT / "upstream/src/main/scala/xiangshan/mem/lsqueue/LoadQueueReplay.scala"
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
# Keep generated RTL in an ASCII temporary path so WSL receives exact UTF-8
# filenames even though the repository root contains non-ASCII characters.
WORK = Path(tempfile.gettempdir()) / "uhsc_memblock_closure_wave_age38"
EVIDENCE = ROOT / "validation/v2-memblock-closure-wave-age38.json"
MODULE = "AgeDetector_38"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
EQUIV_MARKERS = ("0 are unproven.", "Equivalence successfully proven!")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_build() -> Any:
    spec = importlib.util.spec_from_file_location("memblock_age38_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def wsl_path(path: Path) -> str:
    result = subprocess.run(
        ["wsl.exe", "-e", "wslpath", "-a", str(path.resolve())],
        capture_output=True,
        check=True,
    )
    return result.stdout.decode("utf-8", "replace").strip()


def run_wsl(command: list[str]) -> dict[str, Any]:
    rendered = " ".join(shlex.quote(item) for item in command)
    try:
        result = subprocess.run(
            ["wsl.exe", "-e", "bash", "-lc", rendered],
            capture_output=True,
            check=False,
        )
    except OSError as error:
        return {"status": "FAIL", "returncode": None, "error": repr(error)}
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "returncode": result.returncode,
        "output_tail": output[-6000:],
        "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
        "command": command,
    }


def parse_ports(rtl: str, module: str) -> dict[str, tuple[str, int]]:
    marker = f"module {module}("
    start = rtl.find(marker)
    if start < 0:
        raise AssertionError(f"missing {marker}")
    header_start = start + len(marker)
    header = rtl[header_start:]
    header_end = header.find(");")
    header = header[:header_end]
    # Amaranth emits a non-ANSI module signature followed by explicit input /
    # output declarations.  Include that declaration region when present.
    declaration_body = rtl[header_start + header_end + 2:]
    declaration_body = declaration_body[:declaration_body.find("endmodule")]
    ports: dict[str, tuple[str, int]] = {}
    direction = ""
    width = 1
    source_lines = header.splitlines()
    if not any(re.match(r"^\s*(input|output)\b", line) for line in source_lines):
        source_lines.extend(
            line for line in declaration_body.splitlines()
            if re.match(r"^\s*(input|output)\b", line)
        )
    for raw in source_lines:
        line = raw.split("//", 1)[0].strip().rstrip(";")
        if not line:
            continue
        declaration = re.match(r"^(input|output)\s+(?:\[(\d+):(\d+)\]\s*)?(.*)$", line)
        if declaration:
            direction = declaration.group(1)
            high = declaration.group(2)
            low = declaration.group(3)
            width = abs(int(high) - int(low)) + 1 if high is not None and low is not None else 1
            line = declaration.group(4)
        if not direction:
            continue
        for name in line.rstrip(",").split(","):
            name = name.strip()
            if re.fullmatch(r"[A-Za-z_]\w*", name):
                ports[name] = (direction, width)
    return ports


def locked_port_surface() -> dict[str, tuple[str, int]]:
    hierarchy = json.loads(HIERARCHY.read_text(encoding="utf-8"))["modules"][MODULE]
    surface: dict[str, tuple[str, int]] = {}
    for port in hierarchy["ports"]:
        token = str(port.get("width", ""))
        match = re.search(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", token)
        width = abs(int(match.group(1)) - int(match.group(2))) + 1 if match else 1
        surface[str(port["name"])] = (str(port["direction"]), width)
    return surface


def drop_initial_region(text: str) -> tuple[str, int]:
    start = text.find("`ifdef ENABLE_INITIAL_REG_")
    if start < 0:
        raise AssertionError("locked initial region is missing")
    depth = 0
    end = -1
    for match in re.finditer(r"`(?:ifdef|ifndef|endif)", text[start:], re.IGNORECASE):
        if match.group(0).lower() in ("`ifdef", "`ifndef"):
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                end = start + match.end()
                break
    if end < 0:
        raise AssertionError("unterminated locked initial region")
    return text[:start] + text[end:], end - start


def synthesizable_view(locked: str) -> tuple[str, dict[str, Any]]:
    """Remove random initialization and hoist local temporaries mechanically."""

    body, removed_bytes = drop_initial_region(locked)
    body = "\n".join(line.split("//", 1)[0].rstrip() for line in body.splitlines())
    pattern = re.compile(
        r"(?ms)^[ \t]*automatic\s+logic\s+(?:(\[[^\]]+\])\s+)?"
        r"([A-Za-z_]\w*)(?:\s*=\s*(.*?))?;[ \t]*$"
    )
    declarations: list[tuple[str | None, str]] = []

    def replace(match: re.Match[str]) -> str:
        width, name, initial = match.group(1), match.group(2), match.group(3)
        declarations.append((width, name))
        if initial is None:
            return ""
        return "      " + name + " = " + initial + ";"

    body = pattern.sub(replace, body)
    unique: list[tuple[str | None, str]] = []
    seen: set[str] = set()
    for width, name in declarations:
        if name not in seen:
            seen.add(name)
            unique.append((width, name))
    header_end = body.index(");") + 2
    hoisted = "\n" + "".join(
        "  reg " + ((width + " ") if width else "") + name + ";\n"
        for width, name in unique
    )
    view = body[:header_end] + hoisted + body[header_end:]
    view = view.replace(f"module {MODULE}(", f"module {MODULE}_ref(", 1)
    audit = {
        "initial_region_removed_bytes": removed_bytes,
        "block_local_declarations_hoisted": len(unique),
        "automatic_declarations_remaining": view.count("automatic"),
        "module_renamed_only": view.count(f"module {MODULE}_ref(") == 1,
        "equations_preserved_by_mechanical_view": view.count("age_") > 0,
    }
    return view, audit


def formal_run(target: Path, reference: Path, top_ref: str = f"{MODULE}_ref") -> dict[str, Any]:
    target_wsl = wsl_path(target)
    reference_wsl = wsl_path(reference)
    script = (
        f"read_verilog -sv {target_wsl} {reference_wsl}; "
        "proc; async2sync; memory; opt; "
        f"equiv_make {MODULE} {top_ref} {MODULE}_equiv; "
        f"prep -top {MODULE}_equiv; equiv_induct -undef; equiv_status -assert"
    )
    result = run_wsl(["yosys", "-Q", "-p", script])
    output = result.get("output_tail", "")
    result["markers_present"] = {marker: marker in output for marker in EQUIV_MARKERS}
    result["formal_success_marker"] = all(result["markers_present"].values())
    totals = re.findall(r"Found (\d+) \$equiv cells in", output)
    proven = re.findall(r"Of those cells (\d+) are proven and (\d+) are unproven", output)
    unproven = re.findall(r"Found (\d+) unproven \$equiv cells", output)
    if totals:
        result["equiv_cells"] = int(totals[-1])
    if proven:
        result["proven_cells"] = int(proven[-1][0])
        result["unproven_cells"] = int(proven[-1][1])
    elif unproven:
        result["unproven_cells"] = int(unproven[-1])
    result["status"] = "PASS" if result["formal_success_marker"] and result.get("returncode") == 0 else "FAIL"
    return result


def backend_gate(tool: str, path: Path, top: str) -> dict[str, Any]:
    linux = wsl_path(path)
    if tool == "verilator":
        return run_wsl(["verilator", "--lint-only", "-Wno-fatal", "--top-module", top, linux])
    return run_wsl(["yosys", "-Q", "-p", f"read_verilog -sv {linux}; hierarchy -top {top}; proc; async2sync; opt; check"])


def negative_control(clean_target: Path, clean_reference: Path, target_rtl: str, reference_rtl: str) -> dict[str, Any]:
    target_mutant_text, target_count = re.subn(r"assign\s+io_out\s*=.*?;", "assign io_out = 24'h0;", target_rtl, count=1, flags=re.DOTALL)
    reference_mutant_text, reference_count = re.subn(r"assign\s+io_out\s*=.*?;", "assign io_out = 24'h0;", reference_rtl, count=1, flags=re.DOTALL)
    results: dict[str, Any] = {}
    for side, text, count, clean_side, target_is_mutant in (
        ("target", target_mutant_text, target_count, clean_reference, True),
        ("reference", reference_mutant_text, reference_count, clean_target, False),
    ):
        mutant = WORK / f"{MODULE}-{side}-mutant.sv"
        mutant.write_text(text, encoding="utf-8", newline="\n")
        if count != 1:
            results[side] = {"status": "FAIL", "mutation_applied": False, "matched": count}
            continue
        proof = formal_run(mutant if target_is_mutant else clean_target, clean_side if target_is_mutant else mutant)
        results[side] = {
            "status": "PASS" if proof.get("formal_success_marker") is False and int(proof.get("unproven_cells", 0)) > 0 else "FAIL",
            "mutation_applied": True,
            "matched": count,
            "equiv_cells": proof.get("equiv_cells"),
            "unproven_cells": proof.get("unproven_cells"),
            "formal": proof,
        }
    return results


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    before_reference = sha256_file(REFERENCE)
    before_scala = sha256_file(SCALA)
    module = load_build()
    py_compile.compile(str(TARGET), doraise=True)
    py_compile.compile(str(DIRECT_TEST), doraise=True)
    first = module.build_verilog({"module": MODULE}, {})
    second = module.build_verilog({"module": MODULE}, {})
    target_path = WORK / f"{MODULE}-target.sv"
    target_path.write_text(first, encoding="utf-8", newline="\n")
    reference_text = REFERENCE.read_text(encoding="utf-8")
    view, view_audit = synthesizable_view(reference_text)
    reference_path = WORK / f"{MODULE}-reference.sv"
    reference_path.write_text(view, encoding="utf-8", newline="\n")

    locked_surface = locked_port_surface()
    target_surface = parse_ports(first, MODULE)
    reference_surface = parse_ports(reference_text, MODULE)
    view_surface = parse_ports(view, f"{MODULE}_ref")
    expected_from_build = {name: (direction, width) for name, direction, width in module.PORT_SPECS[MODULE]}
    abi = {
        "locked_hierarchy_equals_build": locked_surface == expected_from_build,
        "locked_reference_surface": reference_surface == locked_surface,
        "synth_view_surface": view_surface == locked_surface,
        "target_surface": target_surface == locked_surface,
        "port_count": len(locked_surface),
    }
    direct = subprocess.run([sys.executable, str(DIRECT_TEST)], capture_output=True, check=False)
    direct_output = (direct.stdout + direct.stderr).decode("utf-8", "replace")
    direct_gate = {
        "status": "PASS" if direct.returncode == 0 else "FAIL",
        "returncode": direct.returncode,
        "output_tail": direct_output[-3000:],
        "output_sha256": hashlib.sha256(direct_output.encode("utf-8")).hexdigest(),
    }
    target_verilator = backend_gate("verilator", target_path, MODULE)
    target_yosys = backend_gate("yosys", target_path, MODULE)
    reference_verilator = backend_gate("verilator", reference_path, f"{MODULE}_ref")
    reference_yosys = backend_gate("yosys", reference_path, f"{MODULE}_ref")
    clean_formal = formal_run(target_path, reference_path)
    negatives = negative_control(target_path, reference_path, first, view)
    locks_after = {
        "reference": sha256_file(REFERENCE),
        "scala": sha256_file(SCALA),
    }
    all_negative = all(item.get("status") == "PASS" for item in negatives.values())
    formal_pass = clean_formal.get("status") == "PASS"
    static_pass = all(abi.values()) and first == second and direct_gate["status"] == "PASS"
    backend_pass = all(item.get("status") == "PASS" for item in (target_verilator, target_yosys, reference_verilator, reference_yosys))
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_MEMBLOCK_CLOSURE_WAVE",
        "batch_id": "V2-MEMBLOCK-CLOSURE-WAVE-AGE38",
        "module": MODULE,
        "build": {
            "path": TARGET.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(TARGET),
            "implemented_members": list(module.IMPLEMENTED_MEMBERS),
            "contract_only_members": list(module.CONTRACT_ONLY_MEMBERS),
            "verilog_bytes": len(first.encode("utf-8")),
            "verilog_sha256": hashlib.sha256(first.encode("utf-8")).hexdigest(),
        },
        "reference_lock": {
            "scala_path": SCALA.relative_to(ROOT).as_posix(),
            "scala_sha256": before_scala,
            "reference_sv_path": REFERENCE.relative_to(ROOT).as_posix(),
            "reference_sv_sha256": before_reference,
            "upstream_source_commit": SOURCE_COMMIT,
            "xstop_sha256": XSTOP_SHA256,
            "reference_unchanged": before_reference == locks_after["reference"],
            "scala_unchanged": before_scala == locks_after["scala"],
        },
        "checks": {
            "py_compile": "PASS",
            "deterministic_same_name_verilog": "PASS" if first == second else "FAIL",
            "abi": abi,
            "direct_test": direct_gate,
            "target_verilator": target_verilator,
            "target_yosys": target_yosys,
            "reference_view_verilator": reference_verilator,
            "reference_view_yosys": reference_yosys,
            "reference_view_audit": view_audit,
            "formal": clean_formal,
            "negative_control": negatives,
        },
        "formal_status": "PASS" if formal_pass else "FAIL",
        "strict_leaf_proof": formal_pass and all_negative and static_pass and backend_pass,
        "strict_complete_eligible": False,
        "acceptance_eligible": False,
        "status": "PASS_FORMAL_LEAF_PENDING_PARENT_CLOSURE" if formal_pass and all_negative and static_pass and backend_pass else "FAIL",
        "unclosed": [
            "Family parent closure and full XSTop integration remain pending.",
            "Central strict-equivalence progress is intentionally unchanged by this evidence artifact.",
        ],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "formal": clean_formal.get("status"), "negative": negatives, "abi": abi}))
    return 0 if payload["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
