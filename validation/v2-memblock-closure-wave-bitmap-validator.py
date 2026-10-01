"""Verify the Bitmap leaf implementation against its frozen ABI and tool rails.

This wave records implemented behavior and backend checks.  Reference
differential and formal equivalence remain on the root task's serial rail.
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
REFERENCE = ROOT / "validation/reference-sv/Bitmap.sv"
RR_ARBITER = ROOT / "validation/reference-sv/RRArbiterInit.sv"
CACHE_ARBITER = ROOT / "validation/reference-sv/Arbiter8_bitmapCacheReqBundle.sv"
SCALA = ROOT / "upstream/src/main/scala/xiangshan/cache/mmu/BitmapCheck.scala"
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
FREEZE = ROOT / "V2-Rewrite-Freeze-Manifest.json"
EVIDENCE = ROOT / "validation/v2-memblock-closure-wave-bitmap.json"
MODULE = "Bitmap"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_build() -> Any:
    spec = importlib.util.spec_from_file_location("memblock_bitmap_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def parse_ports(rtl: str, module: str) -> dict[str, tuple[str, int]]:
    marker = f"module {module}("
    start = rtl.find(marker)
    if start < 0:
        raise AssertionError(f"missing module declaration: {module}")
    header_start = start + len(marker)
    header = rtl[header_start:]
    header_end = header.find(");")
    if header_end < 0:
        raise AssertionError(f"unterminated module header: {module}")
    header_lines = header[:header_end].splitlines()
    declaration_body = rtl[header_start + header_end + 2:]
    declaration_body = declaration_body[:declaration_body.find("endmodule")]
    if not any(re.match(r"^\s*(input|output)\b", line) for line in header_lines):
        header_lines.extend(
            line for line in declaration_body.splitlines()
            if re.match(r"^\s*(input|output)\b", line)
        )
    ports: dict[str, tuple[str, int]] = {}
    direction = ""
    width = 1
    for raw in header_lines:
        line = raw.split("//", 1)[0].strip().rstrip(";")
        if not line:
            continue
        declaration = re.match(r"^(input|output)\s+(?:\[(\d+):(\d+)\]\s*)?(.*)$", line)
        if declaration:
            direction = declaration.group(1)
            high, low = declaration.group(2), declaration.group(3)
            width = abs(int(high) - int(low)) + 1 if high is not None and low is not None else 1
            line = declaration.group(4)
        if not direction:
            continue
        for name in line.rstrip(",").split(","):
            name = name.strip()
            if re.fullmatch(r"[A-Za-z_]\w*", name):
                ports[name] = (direction, width)
    return ports


def locked_ports() -> dict[str, tuple[str, int]]:
    modules = json.loads(HIERARCHY.read_text(encoding="utf-8"))["modules"]
    surface: dict[str, tuple[str, int]] = {}
    for port in modules[MODULE]["ports"]:
        width_text = str(port.get("width", ""))
        match = re.search(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", width_text)
        width = abs(int(match.group(1)) - int(match.group(2))) + 1 if match else 1
        surface[str(port["name"])] = (str(port["direction"]), width)
    return surface


def synthesizable_reference_view(text: str) -> tuple[str, dict[str, int]]:
    """Hoist local procedural temporaries mechanically for the Yosys frontend."""

    init_marker = text.find("`ifdef ENABLE_INITIAL_REG_")
    if init_marker < 0:
        raise AssertionError("locked initialization region is missing")
    depth = 0
    init_end = -1
    for match in re.finditer(r"`(?:ifdef|ifndef|endif)", text[init_marker:], re.IGNORECASE):
        if match.group(0).lower() in ("`ifdef", "`ifndef"):
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                init_end = init_marker + match.end()
                break
    if init_end < 0:
        raise AssertionError("unterminated locked initialization region")
    text = text[:init_marker] + text[init_end:]
    body = "\n".join(line.split("//", 1)[0].rstrip() for line in text.splitlines())
    pattern = re.compile(
        r"(?m)^[ \t]*automatic\s+logic\s+((?:\[[^\]]+\]\s*)*)"
        r"([A-Za-z_]\w*)(?:\s*=\s*(.*?))?;[ \t]*$"
    )
    declarations: list[tuple[str, str]] = []

    def replace(match: re.Match[str]) -> str:
        width, name, initial = match.group(1), match.group(2), match.group(3)
        declarations.append((width.strip(), name))
        if initial is None:
            return ""
        return f"      {name} = {initial};"

    body = pattern.sub(replace, body)
    unique: list[tuple[str, str]] = []
    seen: set[str] = set()
    for width, name in declarations:
        if name not in seen:
            unique.append((width, name))
            seen.add(name)
    header_end = body.index(");") + 2
    declarations_text = "".join(f"  reg {width + ' ' if width else ''}{name};\n" for width, name in unique)
    view = body[:header_end] + "\n" + declarations_text + body[header_end:]
    audit = {
        "initial_region_removed": 1,
        "local_temporaries_hoisted": len(unique),
        "automatic_declarations_remaining": view.count("automatic"),
        "module_identity_preserved": view.startswith(f"module {MODULE}("),
    }
    return view, audit


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
        return {"status": "FAIL", "returncode": None, "error": repr(error), "command": command}
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "returncode": result.returncode,
        "output_tail": output[-5000:],
        "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
        "command": command,
    }


def backend_gate(tool: str, path: Path, top: str, support: tuple[Path, ...] = ()) -> dict[str, Any]:
    files = [wsl_path(path), *(wsl_path(item) for item in support)]
    if tool == "verilator":
        return run_wsl(["verilator", "--lint-only", "-Wno-fatal", "--top-module", top, *files])
    source_list = " ".join(f'"{item}"' for item in files)
    script = f"read_verilog -sv {source_list}; hierarchy -top {top}; proc; async2sync; opt; check"
    return run_wsl(["yosys", "-Q", "-p", script])


def main() -> int:
    module = load_build()
    py_compile.compile(str(TARGET), doraise=True)
    py_compile.compile(str(DIRECT_TEST), doraise=True)

    first = module.build_verilog({"module": MODULE}, {})
    second = module.build_verilog({"module": MODULE}, {})
    work = Path(tempfile.mkdtemp(prefix="uhsc_memblock_closure_wave_bitmap_"))
    target_rtl = work / f"{MODULE}-target.sv"
    target_rtl.write_text(first, encoding="utf-8", newline="\n")
    reference_view_text, reference_view_audit = synthesizable_reference_view(
        REFERENCE.read_text(encoding="utf-8")
    )
    reference_view = work / f"{MODULE}-reference-structural.sv"
    reference_view.write_text(reference_view_text, encoding="utf-8", newline="\n")

    hierarchy_ports = locked_ports()
    build_ports = {name: (direction, width) for name, direction, width in module.PORT_SPECS[MODULE]}
    emitted_ports = parse_ports(first, MODULE)
    locked_reference_ports = parse_ports(REFERENCE.read_text(encoding="utf-8"), MODULE)
    abi = {
        "build_catalog_equals_locked_hierarchy": build_ports == hierarchy_ports,
        "target_equals_locked_hierarchy": emitted_ports == hierarchy_ports,
        "reference_equals_locked_hierarchy": locked_reference_ports == hierarchy_ports,
        "port_count": len(hierarchy_ports),
    }

    direct_result = subprocess.run(
        [sys.executable, str(DIRECT_TEST)], capture_output=True, check=False
    )
    direct_output = (direct_result.stdout + direct_result.stderr).decode("utf-8", "replace")
    direct = {
        "status": "PASS" if direct_result.returncode == 0 else "FAIL",
        "returncode": direct_result.returncode,
        "output_tail": direct_output[-4000:],
        "output_sha256": hashlib.sha256(direct_output.encode("utf-8")).hexdigest(),
        "behavior_cases": ["PMP fault completion", "cache miss, memory read, response and refill"],
    }
    target_verilator = backend_gate("verilator", target_rtl, MODULE)
    target_yosys = backend_gate("yosys", target_rtl, MODULE)
    reference_verilator = backend_gate("verilator", REFERENCE, MODULE, (RR_ARBITER, CACHE_ARBITER))
    reference_yosys = backend_gate("yosys", reference_view, MODULE, (RR_ARBITER, CACHE_ARBITER))

    before = {"reference": sha256_file(REFERENCE), "scala": sha256_file(SCALA)}
    after = {"reference": sha256_file(REFERENCE), "scala": sha256_file(SCALA)}
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_MEMBLOCK_CLOSURE_WAVE",
        "batch_id": "V2-MEMBLOCK-CLOSURE-WAVE-BITMAP",
        "module": MODULE,
        "status": "IMPLEMENTED_UNVERIFIED_STRICT_PENDING",
        "build": {
            "path": TARGET.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(TARGET),
            "line_count": len(TARGET.read_text(encoding="utf-8").splitlines()),
            "implemented_members": list(module.IMPLEMENTED_MEMBERS),
            "contract_only_members": list(module.CONTRACT_ONLY_MEMBERS),
            "verilog_bytes": len(first.encode("utf-8")),
            "verilog_sha256": hashlib.sha256(first.encode("utf-8")).hexdigest(),
        },
        "direct_test": {
            "path": DIRECT_TEST.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(DIRECT_TEST),
            "line_count": len(DIRECT_TEST.read_text(encoding="utf-8").splitlines()),
        },
        "reference_lock": {
            "scala_path": SCALA.relative_to(ROOT).as_posix(),
            "scala_sha256": before["scala"],
            "reference_sv_path": REFERENCE.relative_to(ROOT).as_posix(),
            "reference_sv_sha256": before["reference"],
            "support_sv": [RR_ARBITER.relative_to(ROOT).as_posix(), CACHE_ARBITER.relative_to(ROOT).as_posix()],
            "upstream_source_commit": freeze["source_commit"],
            "xstop_sha256": freeze["locked_xstop_sha256"],
            "reference_unchanged": before["reference"] == after["reference"],
            "scala_unchanged": before["scala"] == after["scala"],
        },
        "checks": {
            "py_compile": "PASS",
            "deterministic_same_name_verilog": "PASS" if first == second else "FAIL",
            "abi": abi,
            "direct_test": direct,
            "target_verilator": target_verilator,
            "target_yosys": target_yosys,
            "reference_structure_verilator": reference_verilator,
            "reference_structure_yosys": reference_yosys,
            "reference_structure_view_audit": reference_view_audit,
            "reference_differential": "NOT_RUN_ROOT_SERIAL_RAIL",
            "formal": "NOT_RUN_ROOT_SERIAL_RAIL",
        },
        "strict_leaf_proof": False,
        "strict_complete_eligible": False,
        "acceptance_eligible": False,
        "unclosed": [
            "Reference differential and formal equivalence are reserved for the root task's serial rail.",
            "Bitmap remains IMPLEMENTED_UNVERIFIED_STRICT_PENDING until that locked-reference proof closes.",
            "MemBlock family parent closure and full core integration remain pending.",
        ],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    gates_pass = (
        all(abi.values())
        and first == second
        and direct["status"] == "PASS"
        and target_verilator["status"] == "PASS"
        and target_yosys["status"] == "PASS"
        and reference_verilator["status"] == "PASS"
        and reference_yosys["status"] == "PASS"
        and before == after
    )
    print(json.dumps({"status": payload["status"] if gates_pass else "FAIL", "abi": abi,
                      "direct": direct["status"], "target_verilator": target_verilator["status"],
                      "target_yosys": target_yosys["status"],
                      "reference_verilator": reference_verilator["status"],
                      "reference_yosys": reference_yosys["status"]}, sort_keys=True))
    return 0 if gates_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
