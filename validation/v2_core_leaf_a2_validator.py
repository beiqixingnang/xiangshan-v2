"""Independent validator for V2 control-flow leaves.
V2 控制流叶子独立验证器。
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
OUT = ROOT / "validation/v2-core-leaf-a2-validator-results.json"
TARGETS = {
    "BranchModule": BUILD / "Build-Cpu.Backend.Fu.BranchModule-Hardware.py",
    "JumpDataModule": BUILD / "Build-Cpu.Backend.Fu.JumpDataModule-Hardware.py",
}
SOURCES = {
    "BranchModule": ROOT / "upstream/src/main/scala/xiangshan/backend/fu/Branch.scala",
    "JumpDataModule": ROOT / "upstream/src/main/scala/xiangshan/backend/fu/Jump.scala",
}


def load(path: Path, name: str):
    """Load one exact target path. / 加载一个精确目标路径。"""

    spec = importlib.util.spec_from_file_location(f"a2_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def tools_gate(verilog: str, top: str, work: Path) -> dict[str, object]:
    """Run Verilator and Yosys for one module. / 对单个模块运行 Verilator 与 Yosys。"""

    sv = work / f"{top}.sv"
    sv.write_text(verilog, encoding="utf-8", newline="\n")
    probe = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"wslpath -a '{sv}'"], capture_output=True, text=True, check=False)
    if probe.returncode:
        return {"verilator": "SKIP", "yosys": "SKIP"}
    wpath = probe.stdout.strip()
    vl = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal '{wpath}'"], capture_output=True, text=True, check=False)
    ys = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p 'read_verilog -sv {wpath}; hierarchy -top {top}; proc; opt; stat'"], capture_output=True, text=True, check=False)
    return {"verilator": "PASS" if vl.returncode == 0 else "FAIL", "yosys": "PASS" if ys.returncode == 0 else "FAIL", "verilator_returncode": vl.returncode, "yosys_returncode": ys.returncode, "stderr_tail": (vl.stderr + ys.stderr)[-600:]}


def main() -> int:
    """Run deterministic control-flow checks. / 运行确定性的控制流检查。"""

    modules = {name: load(path, name) for name, path in TARGETS.items()}
    branch = modules["BranchModule"]
    branch_vectors = [(0, 0, branch.BRANCH_OPCODES["beq"], True), (1, 0, branch.BRANCH_OPCODES["beq"], False), (1, 2, branch.BRANCH_OPCODES["blt"], True), (2, 1, branch.BRANCH_OPCODES["bltu"], False)]
    branch_pass = all(branch.branch_reference(a, b, op) == expected for a, b, op, expected in branch_vectors)
    jump = modules["JumpDataModule"]
    jump_vectors = [(5, 0x100, 4, 2, jump.JUMP_OPCODES["jal"], (0x104, 0x104, False)), (0x201, 0x100, 4, 2, jump.JUMP_OPCODES["jalr"], (0x204, 0x104, False)), (5, 0x100, 8, 2, jump.JUMP_OPCODES["auipc"], (0x108, 0x108, True))]
    jump_pass = all(jump.jump_reference(*args) == expected for args, expected in [(v[:5], v[5]) for v in jump_vectors])
    generated = {}
    with tempfile.TemporaryDirectory(prefix="v2_a2_validator_") as temp:
        work = Path(temp)
        for name, module in modules.items():
            verilog = module.build_verilog(None, {})
            generated[name] = {"bytes": len(verilog.encode()), "sha256": hashlib.sha256(verilog.encode()).hexdigest(), "module_decl": f"module {name}" in verilog, "tools": tools_gate(verilog, name, work)}
    passed = branch_pass and jump_pass and all(v["module_decl"] and v["tools"]["verilator"] == "PASS" and v["tools"]["yosys"] == "PASS" for v in generated.values())
    payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_CORE_LEAF_A2_VALIDATOR", "batch_id": "V2-SCAN-A2-CORE-CONTROLFLOW", "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af", "targets": {k: {"path": str(v.relative_to(ROOT)).replace("\\", "/"), "sha256": hashlib.sha256(v.read_bytes()).hexdigest()} for k, v in TARGETS.items()}, "sources": {k: {"path": str(v.relative_to(ROOT)).replace("\\", "/"), "sha256": hashlib.sha256(v.read_bytes()).hexdigest()} for k, v in SOURCES.items()}, "direct": {"BranchModule": {"vectors": len(branch_vectors), "pass": branch_pass}, "JumpDataModule": {"vectors": len(jump_vectors), "pass": jump_pass}}, "generated": generated, "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": "PASS" if passed else "FAIL", "V2_REFERENCE_MATCHED": "SOURCE_LEVEL_PENDING", "PARENT_CLOSURE_MATCHED": "PENDING", "UHSC_LOCALIZED": "NO_PROJECT_FACING_RENAME", "ACCEPTED": "NOT_ALLOWED"}, "status": "VALIDATOR_PASS_BOUNDED" if passed else "VALIDATOR_FAIL", "acceptance_eligible": False}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "targets": len(TARGETS)}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
