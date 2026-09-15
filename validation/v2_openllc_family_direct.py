"""Bounded direct checks for the OpenLLC aggregate families.
OpenLLC 聚合 family 的有界 direct 检查。

These checks exercise deterministic equations and boundary cases without
claiming a complete locked-XSTop behavioural closure.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Callable


# =============================================================================
# Module Contract
# =============================================================================
ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory"
TARGETS = {
    "cache": BUILD / "Build-Cpu.Dependency.OpenLLC.Cache-Hardware.py",
    "sram": BUILD / "Build-Cpu.Dependency.OpenLLC.Sram-Hardware.py",
    "bridge": BUILD / "Build-Cpu.Dependency.OpenLLC.Bridge-Hardware.py",
    "ncb": BUILD / "Build-Cpu.Dependency.OpenLLC.OpenNCB-Hardware.py",
}
OUT = ROOT / "validation/v2-openllc-family-direct-results.json"


# =============================================================================
# Configuration
# =============================================================================
def load(path: Path, key: str) -> Any:
    """Load a family by exact path. / 按精确路径加载 family。"""

    name = f"v2_openllc_direct_{key}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# =============================================================================
# Implementation
# =============================================================================
def cache_checks(module: Any) -> dict[str, object]:
    """Check address decomposition and replacement equations. / 检查地址分解和替换方程。"""

    cfg = module.OpenLLCConfig(sets=8, ways=4, banks=2, full_address_bits=24)
    vectors = [0, 1, 63, 64, 127, 0x12345, (1 << 23) - 1]
    roundtrip = all(module.compose_address(*module.parse_address(value, cfg), cfg) == value for value in vectors)
    return {"address_roundtrip": roundtrip,
            "replacement_invalid_first": module.select_replacement_way(0b0101, 3, 4) == 1,
            "replacement_full_uses_policy": module.select_replacement_way(0b1111, 7, 4) == 3,
            "beat_ids": [module.beat_data_id(index, cfg) for index in range(cfg.beat_count)]}


def sram_checks(module: Any) -> dict[str, object]:
    """Check bank/MMIO/mask utility equations. / 检查 bank/MMIO/掩码工具方程。"""

    cfg = module.OpenLLCSramConfig(address_bits=16, data_bits=64, depth=16, banks=4, txn_bits=8)
    return {"bank_sequence": [module.route_bank(index << 6, cfg) for index in range(4)],
            "mmio_split": module.is_mmio_transaction(0x80, cfg) and not module.is_mmio_transaction(0x7F, cfg),
            "mask": module.byte_mask(0x1FF, cfg) == 0xFF}


def bridge_checks(module: Any) -> dict[str, object]:
    """Check CHI layouts, link states and credits. / 检查 CHI 布局、链路状态和信用。"""

    cfg = module.OpenLLCChiConfig(issue="E.b", node_id_bits=7, txn_id_bits=8, data_bits=64)
    widths = module.chi_layout(cfg)["req"]
    values = [0 for _ in widths]
    packed = module.pack_fields(values, widths)
    return {"layout_nonempty": all(width > 0 for width in widths),
            "pack_roundtrip": module.unpack_fields(packed, widths) == tuple(values),
            "link_table": [module.next_link_state(False, False), module.next_link_state(True, False),
                           module.next_link_state(True, True), module.next_link_state(False, True)] == [0, 1, 2, 3],
            "credit_events": [module.credit_update(0, True, False), module.credit_update(1, False, True)] == [1, 0]}


def ncb_checks(module: Any) -> dict[str, object]:
    """Check NCB ID, parity, rotation and ordering equations. / 检查 NCB ID、校验、旋转及排序方程。"""

    cfg = module.NCBConfig(outstanding_depth=8)
    selected = module.select_rotational((False, False, True, False), 3)
    return {"id_roundtrip": module.decode_axi_id(module.encode_axi_id(3, cfg), cfg) == 3,
            "parity": module.odd_parity(0, 8) == 1 and module.odd_parity(1, 8) == 0,
            "rotation": selected == (True, 2),
            "overlap": module.address_overlap(0x100, 16, 0x10C, 8) and not module.address_overlap(0x100, 8, 0x108, 8),
            "age": module.age_matrix_step((0, 1, 2), allocate=2) == (1, 2, 0)}


# Run all bounded family checks and write evidence. / 运行全部有界 family 检查并写入证据。
def main() -> int:
    """Write machine-readable direct evidence. / 写入机器可读的 direct 证据。"""

    checks: dict[str, Callable[[Any], dict[str, object]]] = {
        "cache": cache_checks, "sram": sram_checks, "bridge": bridge_checks, "ncb": ncb_checks,
    }
    records: dict[str, object] = {}
    for key, path in TARGETS.items():
        module = load(path, key)
        result = checks[key](module)
        records[key] = {"path": path.relative_to(ROOT).as_posix(),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "checks": result, "pass": all(bool(value) for value in result.values()
                                                         if isinstance(value, bool))}
    passed = all(bool(record["pass"]) for record in records.values())
    payload = {"schema_version": 1,
               "kind": "XIANGSHAN_KUNMINGHU_V2_OPENLLC_FAMILY_DIRECT",
               "phase": "BATCH_VALIDATION", "records": records,
               "gates": {"DIRECT_TEST_PASS_BOUNDED": "PASS" if passed else "FAIL",
                         "V2_REFERENCE_MATCHED": "PENDING_LOCKED_REFERENCE",
                         "BEHAVIOR_VERIFIED_openLLC": "PENDING_PARENT_CLOSURE",
                         "ACCEPTED": "NOT_ALLOWED"},
               "status": "DIRECT_TEST_PASS_BOUNDED" if passed else "DIRECT_TEST_FAIL_BOUNDED",
               "acceptance_eligible": False}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "families": len(records)}))
    return 0 if passed else 1


# =============================================================================
# Public Adapter
# =============================================================================
if __name__ == "__main__":
    raise SystemExit(main())
