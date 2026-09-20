"""Bounded validator for TOP-XSTILE-INTBUFFER-004.

The validator is intentionally a child-family gate.  It proves the three
source-backed IntBuffer surfaces, one-stage async-reset behavior, and backend
lintability, while recording the XSTile/XSCore/L2Top parent closure as
pending.  A passing bounded gate is therefore not an acceptance claim for
the complete XSTile or XSTop hierarchy.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import py_compile
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from v2_build_provenance import source_paths_for_build

from amaranth.sim import Settle, Simulator, Tick

ROOT = Path.cwd() / ".agents" / "xiangshan-v2"
if not (ROOT / "V2-Snapshot.json").exists():
    ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Top.XSTile.IntBuffer.Family-Hardware.py"
LOCKED = ROOT / "validation/v2-locked-hierarchy.json"
RESULT = ROOT / "validation/v2-top-xstile-intbuffer-family-results.json"
WORK = ROOT / "validation/.work/v2-top-xstile-intbuffer"
TOOL_WORK = Path("C:/top_xstile_intbuffer_004")
TOP_LEVEL_EVIDENCE = Path("Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Top.XSTile.IntBuffer.Family-Hardware.evidence.json")
MEMBERS = ("IntBuffer", "IntBuffer_1", "IntBuffer_2")
LOCKED_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"


def load_target() -> Any:
    spec = importlib.util.spec_from_file_location("v2_top_xstile_intbuffer_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def width(token: Any) -> int:
    text = str(token or "").strip()
    if text.startswith("[") and text.endswith("]") and ":" in text:
        high, low = text[1:-1].split(":", 1)
        return abs(int(high) - int(low)) + 1
    return 1


def wsl_path(path: Path) -> str:
    result = subprocess.run(
        ["wsl.exe", "-e", "wslpath", "-a", str(path)],
        capture_output=True,
        check=True,
    )
    return result.stdout.decode("utf-8", "replace").strip()


def run_wsl(command: list[str]) -> dict[str, Any]:
    rendered = " ".join(shlex.quote(item) for item in command)
    result = subprocess.run(
        ["wsl.exe", "-e", "bash", "-lc", rendered],
        capture_output=True,
        check=False,
    )
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {
        "command": command,
        "returncode": result.returncode,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "output_tail": output[-1200:],
        "output_sha256": digest(output.encode()),
    }


def run_pyright() -> dict[str, Any]:
    """Run Pyright only on this family, independent of unrelated snapshot debt."""
    result = subprocess.run(
        ["pyright.cmd", str(TARGET), "--outputjson"],
        capture_output=True,
        check=False,
    )
    raw = (result.stdout + result.stderr).decode("utf-8", "replace")
    try:
        parsed = json.loads(result.stdout.decode("utf-8", "replace"))
        errors = int(parsed.get("summary", {}).get("errorCount", 0))
    except (ValueError, json.JSONDecodeError):
        errors = result.returncode
    status = "PASS" if result.returncode == 0 and errors == 0 else "FAIL"
    return {
        "status": status,
        "returncode": result.returncode,
        "error_count": errors,
        "output_tail": raw[-800:],
        "output_sha256": digest(raw.encode()),
    }


def static_contract() -> dict[str, Any]:
    """Audit the Build five zones, exact adapter, and bilingual comments."""
    raw = TARGET.read_bytes()
    source = raw.decode("utf-8")
    tree = ast.parse(source, filename=str(TARGET))
    lines = source.splitlines()
    zone_names = ("Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry")
    positions = [source.find(f"# {name}") for name in zone_names]
    missing: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        index = node.lineno - 2
        while index >= 0 and not lines[index].strip():
            index -= 1
        if index < 0 or not lines[index].lstrip().startswith("#") or "/" not in lines[index]:
            missing.append(f"{node.name}:{node.lineno}")
    adapters = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "build_verilog"]
    adapter_args = [arg.arg for arg in adapters[0].args.args] if len(adapters) == 1 else []
    adapter_exact = bool(
        len(adapters) == 1
        and adapter_args == ["configuration", "injected_dependencies"]
        and adapters[0].args.vararg is None
        and adapters[0].args.kwarg is None
        and not adapters[0].args.defaults
    )
    result = {
        "utf8_lf": not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw,
        "ast": True,
        "zones": dict(zip(zone_names, positions, strict=True)),
        "five_zone_order": all(position >= 0 for position in positions) and positions == sorted(positions),
        "adapter_args": adapter_args,
        "adapter_exact": adapter_exact,
        "missing_bilingual_comments": missing,
    }
    result["status"] = "PASS" if result["utf8_lf"] and result["five_zone_order"] and adapter_exact and not missing else "FAIL"
    return result


def direct_member(module: Any, member: str) -> dict[str, Any]:
    """Exercise reset, one-cycle latency, and independent lane mapping."""
    dut = module.IntBufferFamily(member)
    inputs = list(dut.input_names)
    outputs = list(dut.output_names)
    observed: list[list[int]] = []
    vectors = [
        [((index + 1) & 1) for index in range(len(inputs))],
        [((index + 0) & 1) for index in range(len(inputs))],
    ]

    def process():
        yield dut.ports["reset"].eq(1)
        yield Settle()
        reset_values: list[int] = []
        for name in outputs:
            reset_values.append(int((yield dut.ports[name])))
        if reset_values != [0] * len(outputs):
            raise AssertionError(f"{member}: reset outputs {reset_values}")
        yield dut.ports["reset"].eq(0)
        for vector in vectors:
            for name, value in zip(inputs, vector):
                yield dut.ports[name].eq(value)
            yield Tick()
            yield Settle()
            values: list[int] = []
            for name in outputs:
                values.append(int((yield dut.ports[name])))
            observed.append(values)
            if values != vector:
                raise AssertionError(f"{member}: expected {vector}, observed {values}")

    simulator = Simulator(dut)
    simulator.add_clock(1e-6)
    simulator.add_process(process)
    simulator.run()
    return {"member": member, "vectors": len(vectors), "observed": observed, "status": "PASS"}


def main() -> int:
    module = load_target()
    hierarchy = json.loads(LOCKED.read_text(encoding="utf-8"))
    failures: list[str] = []
    if hierarchy.get("reference_sha256") != LOCKED_SHA256:
        failures.append("locked hierarchy digest changed")

    py_compile.compile(str(TARGET), doraise=True)
    static = static_contract()
    if static["status"] != "PASS":
        failures.append("static contract")
    pyright = run_pyright()
    if pyright["status"] != "PASS":
        failures.append("pyright")

    surfaces: dict[str, Any] = {}
    exports: dict[str, Any] = {}
    direct: dict[str, Any] = {}
    tools: dict[str, Any] = {}
    WORK.mkdir(parents=True, exist_ok=True)
    TOOL_WORK.mkdir(parents=True, exist_ok=True)

    for member in MEMBERS:
        expected = [
            (str(item["name"]), str(item["direction"]), width(item.get("width")))
            for item in hierarchy["modules"][member]["ports"]
        ]
        actual = [(item.name, item.direction, item.width) for item in module.PORT_SPECS[member]]
        match = expected == actual
        surfaces[member] = {
            "locked": len(expected),
            "catalog": len(actual),
            "match": match,
            "ports": [{"name": n, "direction": d, "width": w} for n, d, w in actual],
        }
        if not match:
            failures.append(f"port surface: {member}")

        rtl = module.build_verilog({"module": member}, {})
        repeat = module.build_verilog({"module": member}, {})
        deterministic = rtl == repeat
        path = WORK / f"{member}.sv"
        path.write_text(rtl, encoding="utf-8", newline="\n")
        tool_path = TOOL_WORK / f"{member}.sv"
        tool_path.write_text(rtl, encoding="utf-8", newline="\n")
        linux_path = wsl_path(tool_path)
        verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal", linux_path])
        yosys = run_wsl(["yosys", "-Q", "-p", f"read_verilog -sv {shlex.quote(linux_path)}; hierarchy -top {member}; proc; check"])
        exports[member] = {
            "bytes": len(rtl.encode()),
            "sha256": digest(rtl.encode()),
            "deterministic": deterministic,
        }
        tools[member] = {"verilator": verilator, "yosys": yosys}
        if not deterministic:
            failures.append(f"nondeterministic export: {member}")
        if verilator["status"] != "PASS":
            failures.append(f"verilator: {member}")
        if yosys["status"] != "PASS":
            failures.append(f"yosys: {member}")
        try:
            direct[member] = direct_member(module, member)
        except Exception as error:  # noqa: BLE001 - preserve bounded evidence
            direct[member] = {"member": member, "status": "FAIL", "error": repr(error)}
            failures.append(f"direct: {member}")

    status = "VALIDATOR_PASS_BOUNDED" if not failures else "VALIDATOR_FAIL"
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_TOP_XSTILE_INTBUFFER_FAMILY",
        "batch_id": "TOP-XSTILE-INTBUFFER-004",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "source_paths": list(source_paths_for_build(TARGET)),
        "target": {"path": str(TARGET.relative_to(ROOT)).replace("\\", "/"), "sha256": digest(TARGET.read_bytes())},
        "locked_reference": {"path": "validation/v2-locked-hierarchy.json", "sha256": LOCKED_SHA256},
        "covered_modules": list(MEMBERS),
        "port_surface": surfaces,
        "exports": exports,
        "direct": direct,
        "static_contract": static,
        "tool_gates": tools,
        "gates": {
            "PY_COMPILE": "PASS",
            "FIVE_ZONE_BILINGUAL_AUDIT": static["status"],
            "ADAPTER_EXACT": "PASS" if static["adapter_exact"] else "FAIL",
            "PYRIGHT": pyright["status"],
            "BUILD_VERILOG": "PASS" if not any(x.startswith("nondeterministic") for x in failures) else "FAIL",
            "DIRECT_TEST_PASS_BOUNDED": "PASS" if not any(x.startswith("direct:") for x in failures) else "FAIL",
            "LOCKED_PORT_CATALOG": "PASS" if not any(x.startswith("port surface") for x in failures) else "FAIL",
            "VERILATOR": "PASS" if not any(x.startswith("verilator:") for x in failures) else "FAIL",
            "YOSYS": "PASS" if not any(x.startswith("yosys:") for x in failures) else "FAIL",
            "REFERENCE_DIFFERENTIAL": "PENDING_LOCKED_REFERENCE_DIFFERENTIAL",
            "PARENT_XSTILE_CLOSURE": "PENDING",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "status": status,
        "acceptance_eligible": False,
        "parent_closure": "PENDING",
        "failures": failures,
        "unclosed": [
            "XSCore/L2Top/XSTile parent binding and full XSTop closure remain pending.",
            "Reference differential and license review remain pending; this is bounded child evidence only.",
        ],
    }
    RESULT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    if TOP_LEVEL_EVIDENCE.parent.exists():
        evidence = {
            "schema_version": 1,
            "kind": "XIANGSHAN_TOP_XSTILE_INTBUFFER_FAMILY_EVIDENCE",
            "batch_id": "TOP-XSTILE-INTBUFFER-004",
            "target": str(TARGET.relative_to(ROOT)).replace("\\", "/"),
            "covered_modules": list(MEMBERS),
            "port_counts": {name: len(module.PORT_SPECS[name]) for name in MEMBERS},
            "checks": payload["gates"],
            "status": status,
            "acceptance_eligible": False,
            "parent_closure": "PENDING",
            "result": str(RESULT.relative_to(ROOT)).replace("\\", "/"),
        }
        TOP_LEVEL_EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": status, "covered": len(MEMBERS), "failures": failures}, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
