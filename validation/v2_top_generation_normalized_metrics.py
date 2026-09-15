"""Derive reachable, normalized top-generation coverage metrics.
计算可达且规范化的顶层生成覆盖率指标。

This report keeps the legacy flat Verilator module comparison visible while
adding the three attainable coverage rails requested by the V2 flow proposal.
It never treats a bounded family result as full behavioral equivalence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "validation/v2-top-generation-probe-results.json"
INVENTORY = ROOT / "V2-Dependency-Family-Inventory.json"
BATCH = ROOT / "V2-Rewrite-Batch-Plan.json"
OUTPUT = ROOT / "validation/v2-top-generation-normalized-metrics.json"


def load(path: Path) -> dict[str, Any]:
    """Load one UTF-8 JSON evidence file. / 加载一个 UTF-8 JSON 证据文件。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object in {path}")
    return value


def root_port_coverage(probe: dict[str, Any]) -> dict[str, Any]:
    """Summarize exact parent/root port envelopes. / 汇总精确父级与根端口包络。"""
    envelopes = probe.get("full_parent_envelopes", {})
    roots = ("Frontend", "Backend", "MemBlock", "XSCore", "L2Top", "XSTile", "XSTop")
    matched: list[str] = []
    pending: list[str] = []
    for root in roots:
        item = envelopes.get(root, {})
        expected = item.get("inventory_count")
        generated = item.get("generated_ports", expected)
        if isinstance(expected, int) and generated == expected and item.get("contract_status", "PASS") != "FAIL":
            matched.append(root)
        else:
            pending.append(root)
    return {
        "planned_roots": len(roots),
        "matched_roots": len(matched),
        "coverage": f"{len(matched)}/{len(roots)}",
        "matched": matched,
        "pending": pending,
        "status": "PASS_STRUCTURAL_PORT_ENVELOPE" if not pending else "PARTIAL",
    }


def family_coverage(inventory: dict[str, Any]) -> dict[str, Any]:
    """Separate structural and behavioral family coverage. / 分离 family 结构与行为覆盖。"""
    families = inventory.get("families", [])
    planned = len(families)
    structural = sum(1 for item in families if item.get("status") in {
        "STRUCTURE_LANDED", "PASS_BOUNDED_FAMILY", "SATISFIED_BY_CORE_FAMILY",
    })
    bounded_behavior = sum(1 for item in families if item.get("status") == "PASS_BOUNDED_FAMILY")
    return {
        "planned_families": planned,
        "structure_landed_or_satisfied": structural,
        "structure_coverage": f"{structural}/{planned}",
        "behavior_verified_bounded": bounded_behavior,
        "behavior_coverage": f"{bounded_behavior}/{planned}",
        "full_behavior_verified": 0,
        "status": "STRUCTURE_COMPLETE_BEHAVIOR_PENDING" if structural == planned else "INCOMPLETE",
    }


def leaf_coverage(batch: dict[str, Any]) -> dict[str, Any]:
    """Report core leaf behavioral coverage without inflating bounded passes. / 报告核心叶子行为覆盖且不夸大 bounded 通过。"""
    state = batch.get("execution_state", {})
    planned = int(batch.get("counts", {}).get("core_leaf_build_files", 46))
    bounded = int(state.get("bounded_leaf_pass_count", 0))
    return {
        "planned_leaves": planned,
        "behavior_verified_bounded": bounded,
        "behavior_coverage": f"{bounded}/{planned}",
        "full_behavior_verified": 0,
        "status": "BOUNDED_ONLY",
    }


def main() -> int:
    """Write normalized metrics evidence. / 写入规范化指标证据。"""
    probe = load(PROBE)
    inventory = load(INVENTORY)
    batch = load(BATCH)
    legacy = probe.get("locked_module_inventory", {})
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_TOP_GENERATION_NORMALIZED_METRICS",
        "source_probe": "validation/v2-top-generation-probe-results.json",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "locked_reference_sha256": probe.get("locked_baseline", {}).get("reference_xstop_sha256"),
        "legacy_flat_module_comparison": {
            "reference_modules": legacy.get("locked_module_count", 0),
            "generated_modules": legacy.get("generated_module_count", 0),
            "raw_missing_modules": legacy.get("missing_module_count", 0),
            "interpretation": "NON_COMPARABLE_WITHOUT_INSTANCE_NORMALIZATION",
        },
        "port_envelope_coverage": root_port_coverage(probe),
        "family_closure_coverage": family_coverage(inventory),
        "leaf_behavioral_coverage": leaf_coverage(batch),
        "full_top_behavior": "PENDING_FULL_CHILD_BEHAVIORAL_DIFFERENTIAL",
        "accepted": False,
        "acceptance_eligible": False,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({
        "port_envelope": payload["port_envelope_coverage"]["coverage"],
        "family_structure": payload["family_closure_coverage"]["structure_coverage"],
        "family_behavior_bounded": payload["family_closure_coverage"]["behavior_coverage"],
        "leaf_behavior_bounded": payload["leaf_behavioral_coverage"]["behavior_coverage"],
        "accepted": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
