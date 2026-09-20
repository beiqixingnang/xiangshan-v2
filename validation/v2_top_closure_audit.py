"""Read-only audit of the reduced Kunminghu V2 top closure.

This audit explains why the top-generation probe can pass an RTL/port envelope
while the complete gate remains blocked.  It joins the probe evidence with the
locked hierarchy and the landed Build targets, then emits concrete follow-up
mapping/closure tasks.  It deliberately does not edit product Build files or
claim a complete child closure.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "validation"
BUILD_ROOT = ROOT / "python/Program-System/System-Build/Build-Cpu"
PROBE_PATH = VALIDATION / "v2-top-generation-probe-results.json"
HIERARCHY_PATH = VALIDATION / "v2-locked-hierarchy.json"
COMPACT_XSTOP_PATH = VALIDATION / "reference-sv/XSTop.sv"
ROOTS_PATH = BUILD_ROOT / "Cpu-Core/Build-Cpu.Top.UHSC.Roots-Hardware.py"
TOP_PATH = BUILD_ROOT / "Cpu-Core/Build-Cpu.Top.UHSCTop-GenerationProbe-Hardware.py"
EXTRACTOR_PATH = VALIDATION / "v2_locked_hierarchy_extract.py"
OUTPUT = VALIDATION / "v2-top-closure-audit.json"


ROOT_NAMES = ("XSCore", "L2Top", "XSTile", "XSTop")


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def class_inventory() -> dict[str, list[str]]:
    """Return source-named classes and the Build file that defines them."""
    result: dict[str, list[str]] = {}
    for path in sorted(BUILD_ROOT.rglob("Build-*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        classes = re.findall(r"^class\s+([A-Za-z_][A-Za-z0-9_]*)\b", text, re.MULTILINE)
        for name in classes:
            result.setdefault(name, []).append(
                str(path.relative_to(ROOT)).replace("\\", "/")
            )
    return result


def compact_xstop_children() -> list[dict[str, str]]:
    """Parse direct XSTop instances without the extractor's case filter.

    ``v2_locked_hierarchy_extract.py`` currently keeps only module names whose
    first character is uppercase.  The compact immutable reference is enough
    to expose lower-case system modules such as ``imsic_bus_top`` for audit.
    """
    if not COMPACT_XSTOP_PATH.is_file():
        return []
    text = COMPACT_XSTOP_PATH.read_text(encoding="utf-8", errors="replace")
    start = text.find("module XSTop(")
    if start < 0:
        return []
    end = text.find("endmodule", start)
    body = text[start:] if end < 0 else text[start:end]
    pattern = re.compile(
        r"(?m)^\s{2}([A-Za-z_][A-Za-z0-9_]*)\s+"
        r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:#\s*\(.*?\)\s*)?\("
    )
    return [{"module": m.group(1), "instance": m.group(2)} for m in pattern.finditer(body)]


def evidence_summary(relative: str) -> dict[str, Any]:
    path = ROOT / relative
    if not path.is_file():
        return {"path": relative, "present": False}
    try:
        payload = load(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return {"path": relative, "present": True, "parseable": False}
    gates = payload.get("gates", {})
    pending = sorted(
        f"{key}={value}"
        for key, value in gates.items()
        if isinstance(value, str) and "PENDING" in value
    )
    return {
        "path": relative,
        "present": True,
        "status": payload.get("status"),
        "pending_gates": pending,
    }


def locked_child_rows(hierarchy: dict[str, Any], root: str) -> list[dict[str, Any]]:
    modules = hierarchy.get("modules", {})
    node = modules.get(root, {})
    rows: list[dict[str, Any]] = []
    for child in node.get("children", []):
        name = str(child.get("module", ""))
        if not name:
            continue
        child_node = modules.get(name, {})
        rows.append(
            {
                "module": name,
                "instance": child.get("instance", ""),
                "ports": child_node.get("port_count", 0),
                "sources": child_node.get("scala_sources", [])[:4],
            }
        )
    return rows


def root_impl_state(root_text: str, root: str) -> dict[str, Any]:
    class_match = re.search(rf"^class\s+{re.escape(root)}\b[^:]*:", root_text, re.MULTILINE)
    constant_missing = bool(re.search(r"self\.closure_missing\.eq\(1\)", root_text))
    return {
        "class_declared": class_match is not None,
        "implementation": "_RootBoundary",
        "constant_closure_missing": constant_missing,
        "child_bindings_in_root_file": [],
        "interpretation": "diagnostic boundary/tie-off; no root child closure is installed",
    }


def mapping_catalog() -> dict[str, dict[str, Any]]:
    """Explicit, reviewable source-child -> landed-local mapping candidates."""
    return {
        "Frontend": {
            "local_symbols": ["FrontendParent"],
            "build_files": [
                "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Frontend.Top-Hardware.py"
            ],
            "port_envelope": 371,
            "mapping_kind": "parent_boundary_available",
            "evidence": [evidence_summary("validation/v2-frontend-parent-differential-results.json")],
        },
        "Backend": {
            "local_symbols": ["BackendTop", "BackendParent"],
            "build_files": [
                "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Top-Hardware.py"
            ],
            "port_envelope": 1165,
            "mapping_kind": "parent_boundary_available",
            "evidence": [evidence_summary("validation/v2-backend-parent-differential-results.json")],
        },
        "MemBlock": {
            "local_symbols": ["UHSCMemoryMemBlock", "MemBlockParent"],
            "build_files": [
                "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Memory.MemBlock-Hardware.py"
            ],
            "port_envelope": 1326,
            "mapping_kind": "parent_boundary_available",
            "evidence": [evidence_summary("validation/v2-memblock-parent-differential-results.json")],
        },
        "TL2TLCoupledL2": {
            "local_symbols": ["TL2TLCoupledL2Parent"],
            "build_files": [
                "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Dependency.CoupledL2.Directory-Hardware.py"
            ],
            "port_envelope": 540,
            "mapping_kind": "selected_parent_boundary_available",
            "evidence": [evidence_summary("validation/v2-coupledL2-tl2tl-parent-results.json")],
        },
        "HuanCun": {
            "local_symbols": [
                "HuanCunCacheBoundary",
                "InclusiveMshrBoundary",
                "HuanCunBridgeBoundary",
            ],
            "build_files": [
                "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Dependency.HuanCun.Cache-Hardware.py",
                "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Dependency.HuanCun.Inclusive-Mshr-Hardware.py",
                "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Dependency.HuanCun.Noninclusive-Bridge-Hardware.py",
            ],
            "port_envelope": 328,
            "mapping_kind": "family_boundaries_only; no exact HuanCun parent",
            "evidence": [
                evidence_summary("validation/v2-huancun-cache-family-results.json"),
                evidence_summary("validation/v2-huancun-mshr-family-results.json"),
                evidence_summary("validation/v2-huancun-bridge-family-results.json"),
            ],
        },
        "ValidIOBroadcast": {
            "local_symbols": ["ValidIOBroadcast"],
            "build_files": [
                "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Dependency.Chisel.Arbiter-Hardware.py"
            ],
            "port_envelope": 28,
            "mapping_kind": "family_subject_available",
            "evidence": [evidence_summary("validation/v2-chisel-arbiter-family-results.json")],
        },
        "AsyncQueueSink_3": {
            "local_symbols": ["AsyncQueueSink"],
            "build_files": [
                "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Dependency.Chisel.Arbiter-Hardware.py"
            ],
            "port_envelope": 18,
            "mapping_kind": "family_subject_available",
            "evidence": [evidence_summary("validation/v2-chisel-arbiter-family-results.json")],
        },
    }


def main() -> int:
    probe = load(PROBE_PATH)
    hierarchy = load(HIERARCHY_PATH)
    root_text = ROOTS_PATH.read_text(encoding="utf-8", errors="replace")
    top_text = TOP_PATH.read_text(encoding="utf-8", errors="replace")
    extractor_text = EXTRACTOR_PATH.read_text(encoding="utf-8", errors="replace")
    classes = class_inventory()
    catalog = mapping_catalog()

    source_xstop_children = compact_xstop_children()
    inventory_xstop_children = [
        {"module": c.get("module", ""), "instance": c.get("instance", "")}
        for c in hierarchy.get("modules", {}).get("XSTop", {}).get("children", [])
    ]
    source_names = {x["module"] for x in source_xstop_children}
    inventory_names = {x["module"] for x in inventory_xstop_children}
    uncaptured = sorted(source_names - inventory_names)

    roots: list[dict[str, Any]] = []
    for root in ROOT_NAMES:
        node = hierarchy.get("modules", {}).get(root, {})
        children = locked_child_rows(hierarchy, root)
        mappings: list[dict[str, Any]] = []
        for child in children:
            name = child["module"]
            entry = catalog.get(name)
            if entry is None:
                mappings.append(
                    {
                        "source_child": name,
                        "ports": child["ports"],
                        "mapping_kind": "no exact landed local symbol",
                        "local_symbols": [],
                        "build_files": [],
                        "evidence": [],
                    }
                )
            else:
                mappings.append({"source_child": name, **entry})
        # Add the lower-case XSTop child omitted by the machine inventory.
        if root == "XSTop":
            for child in source_xstop_children:
                if child["module"] in uncaptured:
                    node_child = hierarchy.get("modules", {}).get(child["module"], {})
                    mappings.append(
                        {
                            "source_child": child["module"],
                            "instance": child["instance"],
                            "ports": node_child.get("port_count", 0),
                            "mapping_kind": "inventory_child_capture_gap",
                            "local_symbols": [],
                            "build_files": [],
                            "evidence": [],
                        }
                    )
        roots.append(
            {
                "root": root,
                "locked_ports": node.get("port_count", 0),
                "locked_child_instances": children,
                "locked_child_count": len(children),
                "implementation": root_impl_state(root_text, root),
                "child_mapping_candidates": mappings,
                "available_local_class_hits": {
                    symbol: classes.get(symbol, [])
                    for symbol in sorted({s for m in mappings for s in m.get("local_symbols", [])})
                },
            }
        )

    full_hierarchy = probe.get("single_full_hierarchy", {})
    locked_inventory = probe.get("locked_module_inventory", {})
    direct = probe.get("direct_probe_observation", {})
    report = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_TOP_CLOSURE_AUDIT",
        "read_only": True,
        "source": {
            "probe": "validation/v2-top-generation-probe-results.json",
            "probe_status": probe.get("status"),
            "complete_gate": probe.get("complete_gate"),
            "reference_sha256": probe.get("locked_baseline", {}).get("reference_xstop_sha256"),
            "source_commit": probe.get("locked_baseline", {}).get("source_commit"),
            "probe_sha256": sha256(PROBE_PATH),
        },
        "root_findings": roots,
        "extractor_child_capture_gap": {
            "extractor": "validation/v2_locked_hierarchy_extract.py",
            "filter": (
                "legacy child_module[:1].isupper() filter still present"
                if "child_module[:1].isupper()" in extractor_text
                else "lowercase child names retained by current extractor"
            ),
            "source_xstop_direct_child_count": len(source_xstop_children),
            "inventory_xstop_direct_child_count": len(inventory_xstop_children),
            "uncaptured_children": uncaptured,
            "inventory_snapshot_stale": bool(uncaptured)
            and "child_module[:1].isupper()" not in extractor_text,
            "impact": (
                "locked hierarchy JSON predates the lowercase-child extractor fix; regenerate it before using XSTop child count"
                if uncaptured and "child_module[:1].isupper()" not in extractor_text
                else "lower-case system child is absent from locked XSTop child topology; do not use inventory child count as complete"
            ),
        },
        "metric_root_cause": {
            "locked_module_count": locked_inventory.get("locked_module_count", 0),
            "generated_module_count": locked_inventory.get("generated_module_count", 0),
            "raw_missing_module_count": locked_inventory.get("missing_module_count", 0),
            "raw_extra_module_count": locked_inventory.get("extra_module_count", 0),
            "raw_comparison_interpretation": "NON_COMPARABLE_WITHOUT_INSTANCE_NORMALIZATION",
            "why": [
                "locked Chisel names are flat and include generated suffixes; local Amaranth names are hierarchical UHSC paths",
                "the local full hierarchy contains reduced parent/root envelopes, not the 1976 locked child modules",
                "there is no source_name -> local_name/instance normalization map in the probe",
            ],
            "structural_port_envelopes": probe.get("full_parent_envelopes", {}),
            "single_hierarchy_status": full_hierarchy.get("status"),
            "direct_probe_observation": direct,
        },
        "actionable_tasks": [
            {
                "id": "TOP-ROOT-STATUS-001",
                "priority": "P0",
                "scope": [
                    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Top.UHSCTop-GenerationProbe-Hardware.py",
                    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Top.UHSC.Roots-Hardware.py",
                ],
                "mapping": "aggregate xs_core/l2_top/xs_tile closure_missing into UHSCTop closure_missing/count/complete",
                "current_failure": "root children are bound as objects but remain _RootBoundary tie-offs; UHSCTop reports complete from only four parent injections + 204 ports",
                "evidence": "validation/v2-top-generation-probe-results.json",
                "done_when": "reduced hierarchy cannot report closure_complete while any source-named root child asserts closure_missing",
            },
            {
                "id": "TOP-XSCORE-CHILD-002",
                "priority": "P1",
                "scope": [
                    "XSCore <- Frontend/Backend/MemBlock",
                    "Build-Cpu.Top.UHSC.Roots-Hardware.py",
                ],
                "mapping": "FrontendParent(371) + BackendTop(1165) + UHSCMemoryMemBlock(1326) -> XSCore(308)",
                "available_evidence": [
                    "validation/v2-frontend-parent-differential-results.json",
                    "validation/v2-backend-parent-differential-results.json",
                    "validation/v2-memblock-parent-differential-results.json",
                ],
                "blocker": "parent behavior/child closures remain bounded; implement explicit 308-port bridge before semantic promotion",
            },
            {
                "id": "TOP-L2TOP-TL2TL-003",
                "priority": "P1",
                "scope": [
                    "L2Top <- TL2TLCoupledL2 + TLXbar_7/8/9 + TLClientsMerger_1 + BusErrorUnit + buffers",
                    "Build-Cpu.Dependency.CoupledL2.Directory-Hardware.py",
                ],
                "mapping": "TL2TLCoupledL2Parent is a 540-port selected parent boundary; Rocket protocol/Chisel families supply bounded relay primitives",
                "available_evidence": [
                    "validation/v2-coupledL2-tl2tl-parent-results.json",
                    "validation/v2-top-l2top-tl2tl-results.json",
                    "validation/v2-top-l2top-tl-children-results.json",
                    "validation/v2-rocket-protocol-family-results.json",
                    "validation/v2-chisel-decoupled-family-results.json",
                    "validation/v2-chisel-arbiter-family-results.json",
                ],
                "blocker": "441-port L2Top bridge, selected TL2TL parent, and 11 exact TL child families are bounded and tool-clean; full MSHR/SRAM/prefetch/diplomacy parent behavior remains pending",
            },
            {
                "id": "TOP-XSTILE-INTBUFFER-004",
                "priority": "P2",
                "scope": ["XSTile <- XSCore/L2Top/IntBuffer variants"],
                "mapping": "bind the two root adapters and add IntBuffer 4-port, 6-port, and reordered 6-port subjects from utility/IntBuffer.scala",
                "reference_shapes": {
                    "IntBuffer": 4,
                    "IntBuffer_1": 6,
                    "IntBuffer_2": 6,
                },
                "available_evidence": [
                    "validation/v2-intbuffer-family-results.json",
                    "validation/v2-top-xstile-intbuffer-family-results.json",
                    "validation/v2-top-xstile-parent-results.json",
                ],
                "blocker": "153-port XSTile parent bridge and six explicit child slots are tool-clean; XSCore/L2Top/IntBuffer child behavior and full XSTile differential remain pending",
            },
            {
                "id": "TOP-XSTOP-UHSC-IO-005",
                "priority": "P2",
                "scope": ["XSTop -> UHSCTop localization and system I/O children"],
                "mapping": "freeze XSTop->UHSCTop external map, capture lower-case imsic_bus_top, then stage AXI4Map/AIA, TLToAXI4, ResetGen, AsyncQueueSink_3, ValidIOBroadcast, and HuanCun/SoCMisc adapters",
                "available_evidence": [
                    "validation/v2-full-top-contract-comparison-results.json",
                    "validation/v2-chisel-aia-interface-family-results.json",
                    "validation/v2-chisel-arbiter-family-results.json",
                    "validation/v2-huancun-cache-family-results.json",
                    "validation/v2-top-xstop-io-aia-results.json",
                ],
                "blocker": "UHSC naming manifest is still PLANNED/non-atomic and AIA explicitly defers TL/AXI/multi-hart wrapper closure",
            },
        ],
        "acceptance": {
            "accepted": False,
            "acceptance_eligible": False,
            "note": "This audit is evidence/task decomposition only; it does not alter BLOCKED_MISSING_CLOSURES.",
        },
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({
        "output": str(OUTPUT.relative_to(ROOT)).replace("\\", "/"),
        "roots": len(roots),
        "xstop_uncaptured_children": uncaptured,
        "actionable_tasks": len(report["actionable_tasks"]),
        "probe_status": probe.get("status"),
        "complete_gate": probe.get("complete_gate"),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
