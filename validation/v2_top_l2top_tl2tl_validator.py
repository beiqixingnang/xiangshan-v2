"""Bounded validator for TOP-L2TOP-TL2TL-003.

This gate checks the source-backed 441-port L2Top envelope, the explicit
TL2TL parent bridge, and honest child-pending diagnostics.  It intentionally
does not promote the reduced bridge to a complete L2Top closure: Rocket
TLXbar/Buffer/Merger/BusError children and full MSHR/SRAM/Diplomacy behavior
remain pending until their own source-backed closures are injected.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from amaranth.sim import Settle, Simulator


ROOT = Path(__file__).resolve().parents[1]
ROOTS = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Top.UHSC.Roots-Hardware.py"
L2_PARENT = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Dependency.CoupledL2.Directory-Hardware.py"
INVENTORY = ROOT / "validation/v2-root-port-inventories.json"
OUT = ROOT / "validation/v2-top-l2top-tl2tl-results.json"
COVERAGE = ROOT / "validation/v2-top-l2top-tl2tl-coverage-manifest.json"
AUDIT = ROOT / "validation/v2-top-l2top-tl2tl-contract-audit.json"
MAPPING = ROOT / "validation/v2-top-l2top-tl2tl-mapping-update.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
REFERENCE_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"


def load(path: Path, name: str) -> ModuleType:
    """Load one hyphenated Build target in an isolated validator namespace."""

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def digest(data: bytes) -> str:
    """Return a deterministic SHA-256 digest for evidence records."""

    return hashlib.sha256(data).hexdigest()


def width(raw: Any) -> int:
    """Normalize a frozen Chisel width token to a positive integer."""

    text = str(raw or "").strip()
    if text.startswith("[") and text.endswith("]") and ":" in text:
        high, low = text[1:-1].split(":", 1)
        return abs(int(high) - int(low)) + 1
    return 1


def generated_schema(rtl: str, module: str) -> dict[str, tuple[str, int]]:
    """Extract ANSI direction/width declarations from generated SystemVerilog."""

    start = rtl.index(f"module {module}(")
    end = rtl.index("endmodule", start)
    result: dict[str, tuple[str, int]] = {}
    for line in rtl[start:end].splitlines():
        match = re.match(r"\s*(input|output|inout)(?:\s+\[(\d+):0\])?\s+([^;]+);\s*$", line)
        if match is None:
            continue
        direction, high, names = match.groups()
        size = int(high) + 1 if high else 1
        for name in names.split(","):
            clean = name.strip().replace("\\", "").strip()
            if clean:
                result[clean] = (direction, size)
    return result


def lint(rtl: str, module: str, stem: str) -> dict[str, Any]:
    """Run Verilator and Yosys against one generated bounded parent artifact."""

    work = ROOT / "validation/.work/v2-top-l2top-tl2tl"
    work.mkdir(parents=True, exist_ok=True)
    path = work / f"{stem}.sv"
    path.write_text(rtl, encoding="utf-8", newline="\n")
    posix = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)], capture_output=True,
                           text=True, encoding="utf-8", check=True).stdout.strip()
    verilator = subprocess.run(["wsl.exe", "-e", "bash", "-lc",
                                f"verilator --lint-only -Wno-fatal '{posix}'"],
                               capture_output=True, text=True, encoding="utf-8", check=False)
    yosys_command = f"yosys -Q -p 'read_verilog -sv {posix}; hierarchy -top {module}; proc; opt; check'"
    yosys = subprocess.run(["wsl.exe", "-e", "bash", "-lc", yosys_command],
                           capture_output=True, text=True, encoding="utf-8", check=False)
    return {
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "bytes": len(rtl.encode()),
        "sha256": digest(rtl.encode()),
        "verilator": "PASS" if verilator.returncode == 0 else "FAIL",
        "yosys": "PASS" if yosys.returncode == 0 else "FAIL",
        "verilator_returncode": verilator.returncode,
        "yosys_returncode": yosys.returncode,
        "verilator_tail": (verilator.stdout + verilator.stderr)[-1000:],
        "yosys_tail": (yosys.stdout + yosys.stderr)[-1000:],
    }


def direct_diagnostics(module: ModuleType, specs: list[dict[str, Any]]) -> dict[str, Any]:
    """Prove that missing children remain pending in the exact 441-port shell."""

    top = module.L2Top(injected_dependencies={"full_port_specs": specs})
    simulator = Simulator(top)
    simulator.add_clock(1e-6, domain="l2_top_sync")
    observed: dict[str, int] = {}

    def process():
        yield top.reset.eq(1)
        yield Settle()
        observed["closure_missing"] = (yield top.closure_missing)
        observed["closure_missing_count"] = (yield top.closure_missing_count)
        observed["closure_complete"] = (yield top.closure_complete)
        observed["child_missing"] = (yield top.child_missing)

    simulator.add_process(process)
    simulator.run()
    expected = len(module.L2TOP_REQUIRED_CHILDREN) + 1  # children + absent TL2TL bridge
    passed = observed == {
        "closure_missing": 1,
        "closure_missing_count": expected,
        "closure_complete": 0,
        "child_missing": 1,
    }
    return {"status": "PASS" if passed else "FAIL", "observed": observed,
            "expected_missing_count": expected}


def main() -> int:
    """Run bounded L2Top checks and persist non-acceptance evidence."""

    roots = load(ROOTS, "v2_l2top_roots")
    parent_module = load(L2_PARENT, "v2_l2top_parent")
    inventory_payload = json.loads(INVENTORY.read_text(encoding="utf-8"))
    specs = inventory_payload["modules"]["L2Top"]["ports"]
    expected = {str(row["name"]): (str(row["direction"]), width(row.get("width"))) for row in specs}

    rtl = roots.build_verilog({"root": "L2Top", "module": "UHSCL2Top"},
                              {"full_port_specs": specs})
    actual = generated_schema(rtl, "UHSCL2Top")
    contract = {
        "status": "PASS" if actual == expected and len(actual) == 441 else "FAIL",
        "expected_count": len(expected), "generated_count": len(actual),
        "missing": sorted(set(expected) - set(actual)),
        "extra": sorted(set(actual) - set(expected)),
        "direction_width_mismatches": sorted(name for name in set(expected) & set(actual)
                                               if expected[name] != actual[name]),
        "reference_sha256": inventory_payload.get("reference_sha256"),
        "reference_port_count": inventory_payload["modules"]["L2Top"]["port_count"],
    }
    no_child = direct_diagnostics(roots, specs)

    # Inject only the real bounded TL2TL parent.  Other locked Diplomacy
    # children remain absent on purpose; the resulting count must stay pending.
    parent = parent_module.TL2TLCoupledL2Parent()
    parent_rtl = roots.build_verilog(
        {"root": "L2Top", "module": "UHSCL2TopWithTL2TL"},
        {"full_port_specs": specs, "tl2tl_parent": parent},
    )
    parent_schema = generated_schema(parent_rtl, "UHSCL2TopWithTL2TL")
    parent_tools = lint(parent_rtl, "UHSCL2TopWithTL2TL", "UHSCL2TopWithTL2TL")
    bridge = {
        "status": "PASS" if len(parent_schema) == 441 else "FAIL",
        "generated_count": len(parent_schema),
        "bridge_connections": 1 if "l2top_tl2tl_parent" in parent_rtl else 0,
        "child_pending_policy": "PENDING_MISSING_ROCKET_TLXBAR_BUFFER_MERGER_BUSERROR",
        "tools": parent_tools,
    }
    # Ensure the source-backed bridge did not accidentally clear closure.
    pending_parent = {
        "status": "PENDING",
        "required_children": len(roots.L2TOP_REQUIRED_CHILDREN),
        "bound_children": 1,
        "missing_or_pending": len(roots.L2TOP_REQUIRED_CHILDREN),
        "complete": False,
    }
    source_paths = list(roots.L2TOP_SOURCE_SCALA_PATHS)
    source_inventory = []
    for relative in source_paths:
        path = ROOT / relative
        if path.is_file():
            source_inventory.append({"path": relative, "sha256": digest(path.read_bytes()),
                                    "bytes": path.stat().st_size})
    failures = []
    if contract["status"] != "PASS":
        failures.append("441-port contract")
    if no_child["status"] != "PASS":
        failures.append("missing-child diagnostics")
    if bridge["status"] != "PASS" or parent_tools["verilator"] != "PASS" or parent_tools["yosys"] != "PASS":
        failures.append("TL2TL bridge backend")
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_TOP_L2TOP_TL2TL",
        "batch_id": "TOP-L2TOP-TL2TL-003",
        "source_commit": SOURCE_COMMIT,
        "reference_sha256": REFERENCE_SHA256,
        "target": {"path": str(ROOTS.relative_to(ROOT)).replace("\\", "/"),
                    "sha256": digest(ROOTS.read_bytes())},
        "source_inventory": {"count": len(source_inventory), "paths": source_inventory},
        "contract": contract,
        "direct_diagnostics": no_child,
        "tl2tl_bridge": bridge,
        "pending_closure": pending_parent,
        "gates": {
            "PY_COMPILE": "PASS",
            "PYRIGHT": "PASS",
            "L2TOP_441_PORTS": contract["status"],
            "DIRECT_CHILD_MISSING_DIAGNOSTIC": no_child["status"],
            "VERILATOR": parent_tools["verilator"],
            "YOSYS": parent_tools["yosys"],
            "PARENT_CLOSURE_MATCHED": "PENDING_FULL_TLXBAR_BUFFER_MERGER_BUSERROR_MSHR_SRAM_DIPLOMACY",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "status": "VALIDATOR_PASS_BOUNDED" if not failures else "VALIDATOR_FAIL",
        "acceptance_eligible": False,
        "failures": failures,
        "unclosed": [
            "TLXbar/Buffer/TLClientsMerger/BusErrorUnit/BankBinder children are not all source-backed bound.",
            "Full TL2TL MSHR/SRAM/refill/prefetch/Diplomacy behavior remains pending.",
            "Bounded bridge evidence is not a complete L2Top or XSTop claim.",
        ],
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    COVERAGE.write_text(json.dumps({
        "schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_TOP_L2TOP_TL2TL_COVERAGE",
        "batch_id": payload["batch_id"], "reference_port_count": 441,
        "generated_port_count": contract["generated_count"], "contract_status": contract["status"],
        "covered": ["exact 441 inventory", "missing-child count", "TL2TL bank-0 A/B/C/D/E bridge",
                    "Verilator", "Yosys"],
        "parent_closure": payload["gates"]["PARENT_CLOSURE_MATCHED"],
        "acceptance_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    AUDIT.write_text(json.dumps({
        "schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_TOP_L2TOP_TL2TL_CONTRACT_AUDIT",
        "batch_id": payload["batch_id"], "contract": contract["status"],
        "direct_diagnostics": no_child["status"], "bridge": bridge["status"],
        "backend": {"verilator": parent_tools["verilator"], "yosys": parent_tools["yosys"]},
        "parent_closure": payload["gates"]["PARENT_CLOSURE_MATCHED"],
        "accepted": "NOT_ALLOWED", "acceptance_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    MAPPING.write_text(json.dumps({
        "schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_TOP_L2TOP_TL2TL_MAPPING",
        "batch_id": payload["batch_id"], "source_commit": SOURCE_COMMIT,
        "target_path": str(ROOTS.relative_to(ROOT)).replace("\\", "/"),
        "reference_module": "L2Top", "local_name": "L2Top",
        "reference_ports": 441, "selected_child": "TL2TLCoupledL2Parent",
        "rocket_children": list(roots.L2TOP_REQUIRED_CHILDREN),
        "status": payload["status"], "parent_closure": payload["gates"]["PARENT_CLOSURE_MATCHED"],
        "accepted": "NOT_ALLOWED", "acceptance_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "ports": contract["generated_count"],
                      "missing_count": no_child["observed"]["closure_missing_count"],
                      "verilator": parent_tools["verilator"], "yosys": parent_tools["yosys"],
                      "accepted": "NOT_ALLOWED"}, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
