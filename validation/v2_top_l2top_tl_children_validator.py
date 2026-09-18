"""Validator for the source-backed TL child batch of TOP-L2TOP-TL2TL-003.

The gate compares the eleven selected Rocket child ANSI contracts against the
locked hierarchy, exercises deterministic bounded equations, and runs
Verilator/Yosys on every generated child. It intentionally leaves the 441-port
L2Top parent closure pending.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import py_compile
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Build-Cpu.Dependency.Rocket.TLChildren.Family-Hardware.py"
)
TEST = ROOT / (
    "python/Program-System/System-Testing/Testing-Cpu/"
    "Testing-Cpu.Dependency.Rocket.TLChildren.Family-Hardware.py"
)
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
WORK = ROOT / "validation/.work/v2-top-l2top-tl-children"
RESULTS = ROOT / "validation/v2-top-l2top-tl-children-results.json"
COVERAGE = ROOT / "validation/v2-top-l2top-tl-children-coverage-manifest.json"
AUDIT = ROOT / "validation/v2-top-l2top-tl-children-contract-audit.json"
MAPPING = ROOT / "validation/v2-top-l2top-tl-children-mapping-update.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
PARENT_PENDING = "PENDING_FULL_TLXBAR_BUFFER_MERGER_BUSERROR_MSHR_SRAM_DIPLOMACY"


def load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def width(raw: Any) -> int:
    text = str(raw or "")
    if text.startswith("[") and ":" in text:
        high, low = text[1:-1].split(":", 1)
        return abs(int(high) - int(low)) + 1
    return 1


def generated_schema(rtl: str, module: str) -> dict[str, tuple[str, int]]:
    start = rtl.index(f"module {module}(")
    end = rtl.index("endmodule", start)
    schema: dict[str, tuple[str, int]] = {}
    for line in rtl[start:end].splitlines():
        match = re.match(r"\s*(input|output|inout)(?:\s+\[(\d+):0\])?\s+([^;]+);\s*$", line)
        if match is None:
            continue
        direction, high, names = match.groups()
        size = int(high) + 1 if high else 1
        name = names.strip().split()[0]
        schema[name] = (direction, size)
    return schema


def run_tool(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(command, capture_output=True, text=True,
                            encoding="utf-8", check=False)
    output = result.stdout + result.stderr
    return {
        "command": command,
        "returncode": result.returncode,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "output_tail": output[-1200:],
        "output_sha256": sha256(output.encode()),
    }


def tool_gate(rtl: str, module: str) -> dict[str, Any]:
    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / f"{module}.sv"
    encoded = rtl.encode()
    path.write_bytes(encoded)
    wsl_path = subprocess.run(
        ["wsl.exe", "-e", "wslpath", "-a", str(path)],
        capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout.strip()
    verilator = run_tool([
        "wsl.exe", "-e", "bash", "-lc",
        f"verilator --lint-only -Wno-fatal '{wsl_path}'",
    ])
    yosys = run_tool([
        "wsl.exe", "-e", "bash", "-lc",
        f"yosys -Q -p 'read_verilog -sv {wsl_path}; hierarchy -top {module}; proc; opt; check'",
    ])
    return {
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "bytes": len(encoded), "sha256": sha256(encoded),
        "verilator": verilator, "yosys": yosys,
    }


def direct_gate(module: ModuleType) -> dict[str, Any]:
    vectors = [
        module.relay_observation(valid=False, ready=False),
        module.relay_observation(valid=True, ready=False),
        module.relay_observation(valid=True, ready=True),
        module.relay_observation(valid=True, ready=True, reset=True),
    ]
    assert vectors[-1]["fire"] == 0
    mergers = [
        module.merge_source_ids([], starts=[]),
        module.merge_source_ids([4, 8], starts=[0, 8]),
        module.merge_source_ids([1, 1, 2], starts=[0, 1, 2]),
    ]
    assert mergers[1]["max_id"] == 16
    bus = module.bus_error_observation(
        [False, True, True], [True, True, False],
        [True, False, True], [False, True, True],
    )
    assert bus == {
        "cause_valid": 1, "cause": 1,
        "global_interrupt": 0, "local_interrupt": 1,
    }
    return {"status": "PASS", "relay_vectors": vectors,
            "merger_vectors": mergers, "bus_error": bus}


def static_contract() -> dict[str, Any]:
    """Audit five Build zones, exact adapter, and bilingual function comments."""

    raw = BUILD.read_bytes()
    source = raw.decode("utf-8")
    tree = ast.parse(source, filename=str(BUILD))
    lines = source.splitlines()
    zone_names = ("Module Contract", "Configuration", "Implementation",
                  "Public Adapter", "Direct Entry")
    positions = [source.find(f"# {name}") for name in zone_names]
    missing_comments: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        index = node.lineno - 2
        while index >= 0 and not lines[index].strip():
            index -= 1
        if index < 0 or not lines[index].lstrip().startswith("#") or "/" not in lines[index]:
            missing_comments.append(f"{node.name}:{node.lineno}")
    adapters = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "build_verilog"
    ]
    adapter_args = [arg.arg for arg in adapters[0].args.args] if len(adapters) == 1 else []
    adapter_exact = bool(
        len(adapters) == 1
        and adapter_args == ["configuration", "injected_dependencies"]
        and adapters[0].args.vararg is None
        and adapters[0].args.kwarg is None
        and not adapters[0].args.defaults
    )
    compiled = True
    try:
        py_compile.compile(str(BUILD), doraise=True)
    except py_compile.PyCompileError:
        compiled = False
    passed = (
        not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw
        and all(position >= 0 for position in positions)
        and positions == sorted(positions)
        and adapter_exact and not missing_comments and compiled
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "utf8_lf": not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw,
        "compiled": compiled,
        "zones": dict(zip(zone_names, positions)),
        "five_zone_order": all(position >= 0 for position in positions)
        and positions == sorted(positions),
        "adapter_args": adapter_args,
        "adapter_exact": adapter_exact,
        "missing_bilingual_comments": missing_comments,
    }


def static_gate() -> dict[str, Any]:
    command = [sys.executable, "-m", "py_compile", str(BUILD), str(TEST)]
    result = subprocess.run(command, capture_output=True, text=True,
                            encoding="utf-8", check=False)
    output = result.stdout + result.stderr
    return {"command": command, "returncode": result.returncode,
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "output_tail": output[-1200:], "output_sha256": sha256(output.encode())}


def pyright_gate() -> dict[str, Any]:
    executable = "pyright.cmd" if shutil.which("pyright.cmd") else "pyright"
    command = [
        executable, "--outputjson",
        str(BUILD.relative_to(ROOT)), str(TEST.relative_to(ROOT)),
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", check=False)
    output = result.stdout + result.stderr
    try:
        parsed = json.loads(result.stdout)
        summary = parsed.get("summary", {})
    except json.JSONDecodeError:
        summary = {}
    return {"command": command, "returncode": result.returncode,
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "summary": summary, "output_tail": output[-1200:],
            "output_sha256": sha256(output.encode())}


def main() -> int:
    module = load(BUILD, "v2_tl_children")
    hierarchy = json.loads(HIERARCHY.read_text(encoding="utf-8"))
    members = tuple(module.COVERED_MODULES)
    contract_rows: dict[str, Any] = {}
    tool_rows: dict[str, Any] = {}
    failures: list[str] = []
    for member in members:
        expected = tuple(
            (str(row["name"]), str(row["direction"]), width(row.get("width")))
            for row in hierarchy["modules"][member]["ports"]
        )
        actual = tuple(module.PORT_SPECS[member])
        rtl = module.build_verilog({"module": member}, {})
        generated = generated_schema(rtl, member)
        expected_schema = {name: (direction, port_width)
                           for name, direction, port_width in expected}
        contract_rows[member] = {
            "reference_ports": len(expected), "local_ports": len(actual),
            "reference_bits": sum(port_width for _, _, port_width in expected),
            "local_bits": sum(port.width for port in actual),
            "ports_match": actual == expected,
            "generated_ports": len(generated),
            "generated_contract": generated == expected_schema,
            "generated_bytes": len(rtl.encode()),
            "generated_sha256": sha256(rtl.encode()),
        }
        if not contract_rows[member]["ports_match"]:
            failures.append(f"{member}: frozen port mismatch")
        if not contract_rows[member]["generated_contract"]:
            failures.append(f"{member}: generated port mismatch")
        tool_rows[member] = tool_gate(rtl, member)
        if tool_rows[member]["verilator"]["status"] != "PASS":
            failures.append(f"{member}: Verilator")
        if tool_rows[member]["yosys"]["status"] != "PASS":
            failures.append(f"{member}: Yosys")
        # Deterministic export check is repeated independently from the test.
        if rtl != module.build_verilog({"module": member}, {}):
            failures.append(f"{member}: nondeterministic export")
    direct = direct_gate(module)
    contract_static = static_contract()
    compile_static = static_gate()
    pyright = pyright_gate()
    if direct["status"] != "PASS":
        failures.append("direct equations")
    if contract_static["status"] != "PASS":
        failures.append("static contract")
    if compile_static["status"] != "PASS":
        failures.append("py_compile")
    if pyright["status"] != "PASS":
        failures.append("pyright")

    source_inventory = []
    for paths in module.SOURCE_PATHS.values():
        for relative in paths:
            path = ROOT / relative
            if path.is_file():
                source_inventory.append({
                    "path": relative, "bytes": path.stat().st_size,
                    "sha256": sha256(path.read_bytes()),
                })
            else:
                failures.append(f"missing source: {relative}")
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_TOP_L2TOP_TL_CHILDREN",
        "batch_id": "TOP-L2TOP-TL2TL-003",
        "child_batch": "TLXBAR-TLBUFFER-MERGER-BUSERROR-001",
        "source_commit": SOURCE_COMMIT,
        "covered_modules": list(members),
        "source_inventory": source_inventory,
        "contracts": contract_rows,
        "tools": tool_rows,
        "direct": direct, "static_contract": contract_static,
        "static": compile_static, "pyright": pyright,
        "gates": {
            "PY_COMPILE": compile_static["status"],
            "STATIC_CONTRACT": contract_static["status"],
            "PYRIGHT": pyright["status"],
            "EXACT_SOURCE_PORTS": "PASS" if not any(
                not row["ports_match"] for row in contract_rows.values()) else "FAIL",
            "DETERMINISTIC_EXPORT": "PASS" if not any(
                "nondeterministic export" in item for item in failures) else "FAIL",
            "DIRECT": direct["status"],
            "VERILATOR": "PASS" if all(
                row["verilator"]["status"] == "PASS" for row in tool_rows.values()) else "FAIL",
            "YOSYS": "PASS" if all(
                row["yosys"]["status"] == "PASS" for row in tool_rows.values()) else "FAIL",
            "PARENT_CLOSURE": PARENT_PENDING,
            "L2TOP_441_PORT_PARENT": "PENDING",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "status": "PASS_BOUNDED" if not failures else "FAIL",
        "acceptance_eligible": False,
        "failures": failures,
        "unclosed": [
            "441-port L2Top parent closure remains pending.",
            "Full TLXbar address/routing and TLBuffer queue semantics remain pending.",
            "Full TLClientsMerger Diplomacy and BusErrorUnit register-map closure remain pending.",
            "TL2TL MSHR/SRAM/refill/prefetch/Diplomacy behavior remains pending.",
        ],
    }
    RESULTS.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8", newline="\n")
    COVERAGE.write_text(json.dumps({
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_TOP_L2TOP_TL_CHILDREN_COVERAGE",
        "batch_id": payload["batch_id"], "child_batch": payload["child_batch"],
        "covered_modules": list(members),
        "reference_port_counts": {key: value["reference_ports"]
                                  for key, value in contract_rows.items()},
        "source_backed": True, "bounded_relay": True,
        "parent_closure": PARENT_PENDING, "l2top_reference_ports": 441,
        "acceptance_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    AUDIT.write_text(json.dumps({
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_TOP_L2TOP_TL_CHILDREN_CONTRACT_AUDIT",
        "batch_id": payload["batch_id"], "status": payload["status"],
        "contracts": {key: value["ports_match"]
                      for key, value in contract_rows.items()},
        "verilator": payload["gates"]["VERILATOR"],
        "yosys": payload["gates"]["YOSYS"],
        "direct": direct["status"], "parent_closure": PARENT_PENDING,
        "accepted": "NOT_ALLOWED", "acceptance_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    MAPPING.write_text(json.dumps({
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_TOP_L2TOP_TL_CHILDREN_MAPPING",
        "batch_id": payload["batch_id"], "child_batch": payload["child_batch"],
        "target_path": str(BUILD.relative_to(ROOT)).replace("\\", "/"),
        "source_paths": dict(module.SOURCE_PATHS),
        "reference_modules": list(members), "reference_parent_ports": 441,
        "parent_closure": PARENT_PENDING, "status": payload["status"],
        "accepted": "NOT_ALLOWED", "acceptance_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({
        "status": payload["status"], "modules": len(members),
        "ports": {key: value["reference_ports"] for key, value in contract_rows.items()},
        "verilator": payload["gates"]["VERILATOR"],
        "yosys": payload["gates"]["YOSYS"], "direct": direct["status"],
        "parent_closure": PARENT_PENDING, "accepted": "NOT_ALLOWED",
        "failures": failures,
    }, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
