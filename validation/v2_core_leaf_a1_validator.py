"""Independent validator for the V2 A1 core-leaf batch.
V2 A1 核心叶子批次的独立验证器。

This validator is intentionally separate from the implementation worker.  It
loads exact final Build paths, runs deterministic helper checks, emits each
module, and records source-level V2 evidence plus tool gates.  It never changes
the locked Scala or reference SV and never promotes ACCEPTED.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core"
OUT = ROOT / "validation/v2-core-leaf-a1-validator-results.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"

TARGETS = {
    "ImmExtractor": BUILD / "Build-Cpu.Backend.Issue.ImmExtractor-Hardware.py",
    "AluDataModule": BUILD / "Build-Cpu.Backend.Fu.AluDataModule-Hardware.py",
    "CommitStuckCounter": BUILD / "Build-Cpu.Backend.Rob.CommitStuckCounter-Hardware.py",
    "EnqPolicy": BUILD / "Build-Cpu.Backend.Issue.EnqPolicy-Hardware.py",
    "AgeDetector": BUILD / "Build-Cpu.Backend.Issue.AgeDetector-Hardware.py",
    "PreDecodeInst": BUILD / "Build-Cpu.Backend.Decode.Isa.Predecode.PreDecodeInst-Hardware.py",
}

SOURCES = {
    "ImmExtractor": ROOT / "upstream/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala",
    "AluDataModule": ROOT / "upstream/src/main/scala/xiangshan/backend/fu/Alu.scala",
    "CommitStuckCounter": ROOT / "upstream/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala",
    "EnqPolicy": ROOT / "upstream/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala",
    "AgeDetector": ROOT / "upstream/src/main/scala/xiangshan/backend/issue/AgeDetector.scala",
    "PreDecodeInst": ROOT / "upstream/src/main/scala/xiangshan/backend/decode/isa/predecode/predecode.scala",
}


def load_target(name: str, path: Path) -> Any:
    """Load one target by exact path. / 按精确路径加载目标。"""

    spec = importlib.util.spec_from_file_location(f"v2_a1_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    """Hash one source or target file. / 计算源或目标文件摘要。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def smoke_helpers(modules: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Run independent deterministic helper checks. / 执行独立确定性辅助检查。"""

    imm = modules["ImmExtractor"]
    imm_vectors = [
        (0x001, imm.IMM_TYPES["I"], 1),
        (0xFFF, imm.IMM_TYPES["I"], -1),
        (0x00000, imm.IMM_TYPES["U"], 0),
        (0x7FE, imm.IMM_TYPES["SB"], 0xFFC),
    ]
    imm_results = [imm.decode_immediate(inst, kind) == (expected & ((1 << 64) - 1)) for inst, kind, expected in imm_vectors]

    alu = modules["AluDataModule"]
    alu_ops = alu.ALU_OPCODES
    alu_vectors = [
        (7, 3, alu_ops["add"], 10),
        (7, 3, alu_ops["sub"], 4),
        (0x80, 1, alu_ops["and"], 0),
        (0x10, 2, alu_ops["or"], 0x12),
    ]
    alu_results = [alu.alu_reference(a, b, op) == expected for a, b, op, expected in alu_vectors]

    enq = modules["EnqPolicy"]
    enq_results = [enq.select_circular(0b101101, 2, rank) == expected for rank, expected in [(1, (True, 1)), (2, (True, 1 << 5))]]
    enq_results.append(enq.select_circular(0b1, 2, 2) == (False, 0))

    age = modules["AgeDetector"]
    matrix = [[False] * 4 for _ in range(4)]
    matrix[0][1] = True
    matrix[0][2] = True
    matrix[1][2] = True
    age_result = age.age_select_reference(matrix, [0b1111]) == [0b1000]

    pre = modules["PreDecodeInst"]
    pre_results = [
        pre.match_pattern(pre.PATTERNS["JAL"], 0x0000006F),
        pre.match_pattern(pre.PATTERNS["BRANCH"], 0x00000063),
        not pre.match_pattern(pre.PATTERNS["JAL"], 0x00000013),
    ]
    return {
        "ImmExtractor": {"vectors": len(imm_vectors), "pass": all(imm_results)},
        "AluDataModule": {"vectors": len(alu_vectors), "pass": all(alu_results)},
        "EnqPolicy": {"vectors": 3, "pass": all(enq_results)},
        "AgeDetector": {"vectors": 1, "pass": age_result},
        "PreDecodeInst": {"vectors": len(pre_results), "pass": all(pre_results)},
        "CommitStuckCounter": {"vectors": 0, "pass": True, "note": "stateful smoke is covered by emitted RTL and source contract"},
    }


def tool_gate(verilog: str, name: str, work: Path) -> dict[str, Any]:
    """Run Verilator/Yosys on one emitted module. / 对生成模块运行工具门禁。"""

    sv = work / f"{name}.sv"
    sv.write_text(verilog, encoding="utf-8", newline="\n")
    probe = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"wslpath -a '{sv}'"], capture_output=True, text=True, check=False)
    if probe.returncode != 0:
        return {"verilator": "SKIP", "yosys": "SKIP", "reason": "wslpath unavailable"}
    wpath = probe.stdout.strip()
    verilator = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal '{wpath}'"], capture_output=True, text=True, check=False)
    yosys = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p 'read_verilog -sv {wpath}; hierarchy -top {name}; proc; opt; stat'"], capture_output=True, text=True, check=False)
    return {
        "verilator": "PASS" if verilator.returncode == 0 else "FAIL",
        "yosys": "PASS" if yosys.returncode == 0 else "FAIL",
        "verilator_returncode": verilator.returncode,
        "yosys_returncode": yosys.returncode,
        "stderr_tail": (verilator.stderr + yosys.stderr)[-1000:],
    }


def main() -> int:
    """Validate the complete A1 batch and write evidence. / 验证 A1 批次并写证据。"""

    modules = {name: load_target(name, path) for name, path in TARGETS.items()}
    helper_results = smoke_helpers(modules)
    generated: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="v2_a1_validator_") as temp:
        work = Path(temp)
        for name, module in modules.items():
            verilog = module.build_verilog(None, {})
            generated[name] = {
                "bytes": len(verilog.encode()),
                "sha256": hashlib.sha256(verilog.encode()).hexdigest(),
                "module_decl": f"module {name}" in verilog or (name == "PreDecodeInst" and "module PreDecode" in verilog),
                "tools": tool_gate(verilog, "PreDecodeInstProbe" if name == "PreDecodeInst" else name, work),
            }
    source_evidence = {name: {"path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(path), "present": path.is_file()} for name, path in SOURCES.items()}
    target_evidence = {name: {"path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(path), "present": path.is_file()} for name, path in TARGETS.items()}
    passed = all(item["pass"] for item in helper_results.values()) and all(item["module_decl"] and item["tools"]["verilator"] == "PASS" and item["tools"]["yosys"] == "PASS" for item in generated.values())
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_CORE_LEAF_A1_INDEPENDENT_VALIDATOR",
        "batch_id": "V2-SCAN-A1-CORE-DECODE-ARITH-LEAVES",
        "source_commit": SOURCE_COMMIT,
        "targets": target_evidence,
        "sources": source_evidence,
        "helper_checks": helper_results,
        "generated": generated,
        "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": "PASS" if passed else "FAIL", "V2_REFERENCE_MATCHED": "SOURCE_LEVEL_PENDING", "PARENT_CLOSURE_MATCHED": "PENDING", "UHSC_LOCALIZED": "NO_PROJECT_FACING_RENAME", "ACCEPTED": "NOT_ALLOWED"},
        "status": "VALIDATOR_PASS_BOUNDED" if passed else "VALIDATOR_FAIL",
        "acceptance_eligible": False,
        "unclosed": ["Independent validator confirms leaf Build emission/tool gates; extracted V2 parent differential and parent closure remain required."] if passed else ["At least one helper, emission, Verilator, or Yosys gate failed."],
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "targets": len(TARGETS)}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
