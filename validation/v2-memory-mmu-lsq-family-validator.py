"""Bounded exact-port validator for the V2 memory/MMU/LSQ aggregate.
V2 访存/MMU/LSQ 聚合的有界精确端口校验器。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import py_compile
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
TARGETS = (
    ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Memory.Mmu.Lsq.Family-Hardware.py",
    ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Memory.Prefetch.Metadata.Family-Hardware.py",
)
EVIDENCE = ROOT / "validation/v2-memory-mmu-lsq-family-results.json"

# Calculate a stable digest. / 计算稳定摘要。
def digest(data: bytes) -> str:
    # Return SHA-256. / 返回 SHA-256。
    return hashlib.sha256(data).hexdigest()

# Load one exact family Build. / 装载一个精确 family Build。
def load(path: Path, index: int) -> Any:
    # Use a unique isolated module identity. / 使用唯一隔离模块身份。
    spec = importlib.util.spec_from_file_location(f"v2_memory_mmu_lsq_{index}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

# Run all catalog and deterministic export gates. / 运行所有 catalog 与确定导出门禁。
def main() -> int:
    # Compare every aggregate member to the locked hierarchy. / 将每个聚合成员对照锁定层次。
    hierarchy = json.loads(HIERARCHY.read_text(encoding="utf-8"))["modules"]
    reports: list[dict[str, Any]] = []
    failures: list[str] = []
    for index, path in enumerate(TARGETS):
        py_compile.compile(str(path), doraise=True)
        module = load(path, index)
        for member in module.COVERED_MODULES:
            expected = tuple((p["name"], p["direction"], 1 if not p["width"] else int(p["width"][1:p["width"].find(":")]) - int(p["width"][p["width"].find(":") + 1:-1]) + 1) for p in hierarchy[member]["ports"])
            actual = tuple(tuple(row) for row in module.PORT_SPECS[member])
            rtl_one = module.build_verilog({"module": member}, {})
            rtl_two = module.build_verilog({"module": member}, {})
            item = {"member": member, "ports": len(expected), "port_surface": "PASS" if expected == actual else "FAIL", "deterministic": rtl_one == rtl_two, "verilog_bytes": len(rtl_one.encode()), "verilog_sha256": digest(rtl_one.encode()), "source_paths": list(module.SOURCE_PATHS)}
            reports.append(item)
            if expected != actual or rtl_one != rtl_two or not rtl_one.strip():
                failures.append(member)
    payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_MEMORY_MMU_LSQ_FAMILY", "batch_id": "V2-MEMORY-MMU-LSQ-001", "covered_modules": [r["member"] for r in reports], "reports": reports, "gates": {"PY_COMPILE": "PASS", "LOCKED_PORT_CATALOG": "PASS" if not failures else "FAIL", "DETERMINISTIC_VERILOG": "PASS" if not failures else "FAIL", "DIRECT_TEST_PASS_BOUNDED": "PASS" if not failures else "FAIL", "REFERENCE_DIFFERENTIAL": "PENDING", "ACCEPTED": "NOT_ALLOWED"}, "status": "VALIDATOR_PASS_BOUNDED" if not failures else "VALIDATOR_FAIL", "acceptance_eligible": False, "failures": failures, "unclosed": ["Full locked-parent behavioral differential remains pending.", "Bounded outputs preserve exact port surfaces but do not establish full MMU/LSQ semantic equivalence."]}
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "members": len(reports), "failures": failures}))
    return 0 if not failures else 1

if __name__ == "__main__":
    raise SystemExit(main())
