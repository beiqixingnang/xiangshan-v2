"""Independent validator for V2 issue queue selector/data-array leaves.
V2 发射队列选择器/数据阵列叶子独立验证器。
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
OUT = ROOT / "validation/v2-core-leaf-a3-validator-results.json"
TARGETS = {"DeqPolicy": BUILD / "Build-Cpu.Backend.Issue.DeqPolicy-Hardware.py", "DataArray": BUILD / "Build-Cpu.Backend.Issue.DataArray-Hardware.py"}
SOURCES = {"DeqPolicy": ROOT / "upstream/src/main/scala/xiangshan/backend/issue/DeqPolicy.scala", "DataArray": ROOT / "upstream/src/main/scala/xiangshan/backend/issue/DataArray.scala"}


def load(path: Path, name: str):
    """Load an exact Build target. / 加载精确 Build 目标。"""

    spec = importlib.util.spec_from_file_location(f"a3_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def tool_gate(source: str, top: str, work: Path) -> dict[str, object]:
    """Run Verilator/Yosys on one generated source. / 对生成源运行 Verilator/Yosys。"""

    sv = work / f"{top}.sv"
    sv.write_text(source, encoding="utf-8", newline="\n")
    p = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(sv)], capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    wpath = p.stdout.strip()
    vl = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal '{wpath}'"], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    ys = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p 'read_verilog -sv {wpath}; hierarchy -top {top}; proc; opt; stat'"], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    return {"verilator": "PASS" if vl.returncode == 0 else "FAIL", "yosys": "PASS" if ys.returncode == 0 else "FAIL", "verilator_returncode": vl.returncode, "yosys_returncode": ys.returncode, "stderr_tail": (vl.stderr + ys.stderr)[-500:]}


def main() -> int:
    """Run deterministic direct and tool checks. / 运行确定性直接和工具检查。"""

    modules = {name: load(path, name) for name, path in TARGETS.items()}
    deq = modules["DeqPolicy"]
    deq_vectors = [(deq.select_nth(mask, rank, 8)) for mask in (0, 1, 0b101101, 0xFF) for rank in (1, 2, 3)]
    deq_pass = deq_vectors == [(False, 0), (False, 0), (False, 0), (True, 1), (False, 0), (False, 0), (True, 1), (True, 4), (True, 8), (True, 1), (True, 2), (True, 4)]
    array = modules["DataArray"]
    state = [0, 1, 2, 3]
    reads, next_state = array.data_array_reference(state, [0, 3], [(True, 1, 55), (True, 2, 99)], 8)
    array_pass = reads == [0, 3] and next_state == [0, 55, 99, 3]
    generated = {}
    with tempfile.TemporaryDirectory(prefix="v2_a3_validator_") as temp:
        work = Path(temp)
        for name, module in modules.items():
            source = module.build_verilog(None, {})
            generated[name] = {"bytes": len(source.encode()), "sha256": hashlib.sha256(source.encode()).hexdigest(), "module_decl": f"module {name}" in source, "tools": tool_gate(source, name, work)}
    passed = deq_pass and array_pass and all(v["module_decl"] and v["tools"]["verilator"] == "PASS" and v["tools"]["yosys"] == "PASS" for v in generated.values())
    payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_CORE_LEAF_A3_VALIDATOR", "batch_id": "V2-SCAN-A3-CORE-ISSUE-DATA", "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af", "targets": {k: {"path": str(v.relative_to(ROOT)).replace("\\", "/"), "sha256": hashlib.sha256(v.read_bytes()).hexdigest()} for k, v in TARGETS.items()}, "sources": {k: {"path": str(v.relative_to(ROOT)).replace("\\", "/"), "sha256": hashlib.sha256(v.read_bytes()).hexdigest()} for k, v in SOURCES.items()}, "direct": {"DeqPolicy": {"vectors": len(deq_vectors), "pass": deq_pass}, "DataArray": {"vectors": 1, "pass": array_pass}}, "generated": generated, "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": "PASS" if passed else "FAIL", "V2_REFERENCE_MATCHED": "SOURCE_LEVEL_PENDING", "PARENT_CLOSURE_MATCHED": "PENDING", "UHSC_LOCALIZED": "NO_PROJECT_FACING_RENAME", "ACCEPTED": "NOT_ALLOWED"}, "status": "VALIDATOR_PASS_BOUNDED" if passed else "VALIDATOR_FAIL", "acceptance_eligible": False}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "targets": len(TARGETS)}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
