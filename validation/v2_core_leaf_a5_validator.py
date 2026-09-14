"""Independent validator for the V2 ROB pointer-wrapper family.
V2 ROB 指针封装 family 的独立验证器。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core"
TARGET = BUILD / "Build-Cpu.Backend.Rob.PtrWrappers-Hardware.py"
OUT = ROOT / "validation/v2-core-leaf-a5-validator-results.json"
SOURCES = [ROOT / "upstream/src/main/scala/xiangshan/backend/rob/RobEnqPtrWrapper.scala", ROOT / "upstream/src/main/scala/xiangshan/backend/rob/RobDeqPtrWrapper.scala"]


def load(path: Path):
    """Load exact target path. / 加载精确目标路径。"""

    spec = importlib.util.spec_from_file_location("a5_rob", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    """Run pointer arithmetic, reset, and tool gates. / 运行指针算术、复位和工具门禁。"""

    module = load(TARGET)
    cfg = module.RobPtrConfig(rob_size=16, rename_width=4, commit_width=4)
    initial = list(range(cfg.rename_width))
    enq = module.enq_reference(initial, True, False, [True, False, True, False], configuration=cfg)
    redirect = module.enq_reference(initial, True, False, [False] * 4, True, 7, False, cfg)
    deq = module.deq_reference(list(range(cfg.commit_width)), [True, True, False, True], [True, True, True, True], [False] * 4, False, False, cfg)
    direct = {"enqueue_increment": {"result": enq, "expected": [2, 3, 4, 5], "pass": enq == [2, 3, 4, 5]}, "enqueue_redirect": {"result": redirect, "expected": [8, 9, 10, 11], "pass": redirect == [8, 9, 10, 11]}, "dequeue_contiguous": {"result": deq, "expected_count": 2, "pass": deq[1] == 2 and deq[2]}}
    source = module.build_verilog(cfg, {})
    with tempfile.TemporaryDirectory(prefix="v2_a5_validator_") as temp:
        sv = Path(temp) / "RobPtrWrappers.sv"
        sv.write_text(source, encoding="utf-8", newline="\n")
        wsl = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(sv)], capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout.strip()
        vl = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal '{wsl}'"], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        ys = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p 'read_verilog -sv {wsl}; hierarchy -top RobPtrWrappers; proc; opt; stat'"], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    passed = all(item["pass"] for item in direct.values()) and vl.returncode == 0 and ys.returncode == 0
    payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_CORE_LEAF_A5_VALIDATOR", "batch_id": "V2-SCAN-A5-CORE-ROB-PTR", "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af", "target": {"path": str(TARGET.relative_to(ROOT)).replace("\\", "/"), "sha256": hashlib.sha256(TARGET.read_bytes()).hexdigest()}, "sources": [{"path": str(p.relative_to(ROOT)).replace("\\", "/"), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in SOURCES], "direct": direct, "generated": {"bytes": len(source.encode()), "sha256": hashlib.sha256(source.encode()).hexdigest(), "module_decl": "module RobPtrWrappers" in source}, "tools": {"verilator": "PASS" if vl.returncode == 0 else "FAIL", "yosys": "PASS" if ys.returncode == 0 else "FAIL"}, "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": "PASS" if passed else "FAIL", "V2_REFERENCE_MATCHED": "SOURCE_LEVEL_PENDING", "PARENT_CLOSURE_MATCHED": "PENDING", "UHSC_LOCALIZED": "NO_PROJECT_FACING_RENAME", "ACCEPTED": "NOT_ALLOWED"}, "status": "VALIDATOR_PASS_BOUNDED" if passed else "VALIDATOR_FAIL", "acceptance_eligible": False}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "direct": len(direct)}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
