"""Independent validator for the V2 FU busy-table leaf.
V2 FU 忙表叶子的独立验证器。
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
TARGET = BUILD / "Build-Cpu.Backend.Issue.FuBusyTableRead-Hardware.py"
SOURCE = ROOT / "upstream/src/main/scala/xiangshan/backend/issue/FuBusyTableRead.scala"
OUT = ROOT / "validation/v2-core-leaf-a4-validator-results.json"


def load(path: Path):
    """Load the target by exact path. / 按精确路径加载目标。"""

    spec = importlib.util.spec_from_file_location("a4_busy", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    """Run deterministic direct and synthesis checks. / 运行确定性直接和综合检查。"""

    module = load(TARGET)
    cfg = module.FuBusyTableReadConfig(num_entries=4, latency_by_type=(1, 2, 3, 4))
    vectors = [(0, [0, 1, 2, 3]), (1 << 1, [0, 1, 2, 3]), (1 << 4, [3, 3, 1, 0]), ((1 << 2) | (1 << 4), [0, 1, 2, 3])]
    direct = [module.busy_mask_reference(busy, types, cfg) for busy, types in vectors]
    direct_pass = direct == [0, 0b0001, 0b0011, 0b1010]
    source = module.build_verilog(cfg, {})
    with tempfile.TemporaryDirectory(prefix="v2_a4_validator_") as temp:
        sv = Path(temp) / "FuBusyTableRead.sv"
        sv.write_text(source, encoding="utf-8", newline="\n")
        wsl = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(sv)], capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout.strip()
        vl = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal '{wsl}'"], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        ys = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p 'read_verilog -sv {wsl}; hierarchy -top FuBusyTableRead; proc; opt; stat'"], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    passed = direct_pass and vl.returncode == 0 and ys.returncode == 0
    payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_CORE_LEAF_A4_VALIDATOR", "batch_id": "V2-SCAN-A4-CORE-FU-BUSY", "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af", "target": {"path": str(TARGET.relative_to(ROOT)).replace("\\", "/"), "sha256": hashlib.sha256(TARGET.read_bytes()).hexdigest()}, "source": {"path": str(SOURCE.relative_to(ROOT)).replace("\\", "/"), "sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest()}, "direct": {"vectors": len(vectors), "results": direct, "pass": direct_pass}, "generated": {"bytes": len(source.encode()), "sha256": hashlib.sha256(source.encode()).hexdigest(), "module_decl": "module FuBusyTableRead" in source}, "tools": {"verilator": "PASS" if vl.returncode == 0 else "FAIL", "yosys": "PASS" if ys.returncode == 0 else "FAIL"}, "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": "PASS" if passed else "FAIL", "V2_REFERENCE_MATCHED": "SOURCE_LEVEL_PENDING", "PARENT_CLOSURE_MATCHED": "PENDING", "UHSC_LOCALIZED": "NO_PROJECT_FACING_RENAME", "ACCEPTED": "NOT_ALLOWED"}, "status": "VALIDATOR_PASS_BOUNDED" if passed else "VALIDATOR_FAIL", "acceptance_eligible": False}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "vectors": len(vectors)}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
