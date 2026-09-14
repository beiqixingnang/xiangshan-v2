"""Bounded V2 decode/arithmetic direct checks. / V2 解码算术批次直接检查。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import random
import shutil
import subprocess
import sys
import tempfile
import ast
from pathlib import Path
from typing import Any

from amaranth.sim import Simulator


ROOT = Path(__file__).resolve().parents[1]
BUILD_CORE = ROOT / "python" / "Program-System" / "System-Build" / "Build-Cpu" / "Cpu-Core"
EVIDENCE = ROOT / "validation" / "v2-decode-batch-results.json"
REFERENCE_SV = Path("/home/lishuo/xs-v2-local/build/rtl/XSTop.sv")


# Load a target by exact path / 按精确路径加载目标模块。
def load_target(name: str, path: Path) -> Any:
    """Load one target without adding repository imports. / 精确加载目标。"""

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Compare pattern strings using an independent matcher / 用独立匹配器比较模式。
def independent_match(pattern: str, value: int) -> bool:
    """Evaluate a BitPat without target helper code. / 独立计算 BitPat。"""

    text = pattern.replace("_", "").removeprefix("b").rjust(32, "?")
    return all(bit == "?" or int(bit) == ((value >> (31 - index)) & 1)
               for index, bit in enumerate(text))


# Run combinational target simulation / 运行组合目标仿真。
def simulate_combination(top: Any, assignments: list[tuple[Any, int]],
                         outputs: list[Any]) -> list[int]:
    """Drive one vector and return outputs. / 驱动向量并返回输出。"""

    result: list[int] = []

    async def bench(ctx: Any) -> None:
        for signal, value in assignments:
            ctx.set(signal, value)
        await ctx.delay(1e-9)
        result.extend(int(ctx.get(signal)) for signal in outputs)

    simulator = Simulator(top)
    simulator.add_testbench(bench)
    simulator.run()
    return result


# Test the source pattern closure / 测试源模式闭包。
def test_instructions(module: Any) -> dict[str, Any]:
    """Check every Zvbb/Zimop pattern against an independent model. / 检查模式。"""

    rng = random.Random(0x51A)
    vectors = [0, 0xFFFFFFFF] + [rng.getrandbits(32) for _ in range(256)]
    checks = 0
    for pattern in module.PATTERNS.values():
        mask, expected = module.pattern_mask_expected(pattern)
        assert 0 <= mask <= 0xFFFFFFFF
        for value in vectors:
            expected_match = independent_match(pattern, value)
            assert module.match32(pattern, value) == expected_match
            assert module.match32(pattern, value) == ((value & mask) == expected)
            checks += 1
    verilog = module.build_verilog(None, {})
    assert "module Instructions" in verilog
    return {"vectors": checks, "verilog_sha256": hashlib.sha256(verilog.encode()).hexdigest()}


# Test RISC-V field geometry / 测试 RISC-V 位域几何。
def test_riscv(module: Any) -> dict[str, Any]:
    """Check fields and all vector predicates. / 检查字段与全部向量谓词。"""

    rng = random.Random(0xB17)
    checks = 0
    for _ in range(512):
        value = rng.getrandbits(32)
        for name, (lsb, width) in module.FIELD_RANGES.items():
            expected = (value >> lsb) & ((1 << width) - 1)
            assert module.inst_field(value, name) == expected
        opcode5 = (value >> 2) & 0x1F
        width = (value >> 12) & 0x7
        assert bool(module.isVecStore(value)) == (opcode5 == module.OPCODE5Bit.STORE_FP and
                                                   (width == 0 or ((width >> 2) & 1) == 1))
        assert bool(module.isVecLoad(value)) == (opcode5 == module.OPCODE5Bit.LOAD_FP and
                                                  (width == 0 or ((width >> 2) & 1) == 1))
        assert bool(module.isVecArith(value)) == (opcode5 == module.OPCODE5Bit.OP_V)
        for index, predicate in enumerate((module.isOPIVV, module.isOPFVV, module.isOPMVV,
                                           module.isOPIVI, module.isOPIVX, module.isOPFVF,
                                           module.isOPMVX)):
            assert bool(predicate(value)) == (((value & 0x7F) == module.OPCODE7Bit.VECTOR_ARITH)
                                               and (((value >> 12) & 0x7) == index))
        checks += 1
    assert module.Riscv32BitInst(0).get_inst_vtype().vlmul == 0
    verilog = module.build_verilog(None, {})
    assert "module RiscvInst" in verilog
    return {"vectors": checks, "verilog_sha256": hashlib.sha256(verilog.encode()).hexdigest()}


# Test FLI table values / 测试 FLI 表值。
def test_fli(module: Any) -> dict[str, Any]:
    """Exhaustively compare all three locked tables. / 穷举三张锁定表。"""

    tables = {"H": module.FLI_H, "S": module.FLI_S, "D": module.FLI_D}
    for table in tables.values():
        for index, value in enumerate(table):
            assert module.decode_fli(table, index) == value
    verilog = module.build_verilog(None, {})
    assert "module FliTable" in verilog
    return {"entries": sum(len(table) for table in tables.values()),
            "verilog_sha256": hashlib.sha256(verilog.encode()).hexdigest()}


# Test carry-save equations / 测试进位保存方程。
def test_csa(module: Any) -> dict[str, Any]:
    """Exhaustively test width-four compressor equations. / 穷举四位压缩器。"""

    checks = 0
    width = 4
    for a in range(1 << width):
        for b in range(1 << width):
            for c in range(1 << width):
                result = module.csa3_2(a, b, c, width)
                assert result == ((a ^ b ^ c), ((a & b) | ((a ^ b) & c)))
                checks += 1
    for values in ((1, 2, 4, 8, 3), (15, 7, 9, 1, 2), (0, 0, 0, 0, 0)):
        expected_first = module.csa3_2(values[0], values[1], values[2], width)
        expected_second = module.csa3_2(expected_first[0], values[3], values[4], width)
        assert module.csa5_3(*values, width) == (expected_second[0], expected_first[1], expected_second[1])
    verilog = module.build_verilog(None, {})
    assert "module CSA3_2" in verilog
    return {"vectors": checks, "verilog_sha256": hashlib.sha256(verilog.encode()).hexdigest()}


# Test registered Sstc behavior / 测试寄存式 Sstc 行为。
def test_sstc(module: Any) -> dict[str, Any]:
    """Check reset, enable, and hold behavior over deterministic cycles. / 检查复位使能保持。"""

    top = module.SstcInterruptGen()
    observed: list[tuple[int, int]] = []

    async def bench(ctx: Any) -> None:
        ctx.set(top.reset, 1)
        await ctx.tick()
        ctx.set(top.reset, 0)
        ctx.set(top.i_stime_bits, 10)
        ctx.set(top.i_stimecmp_rdata, 9)
        ctx.set(top.i_menvcfg_STCE, 1)
        ctx.set(top.i_stime_valid, 1)
        ctx.set(top.i_vstime_bits, 20)
        ctx.set(top.i_vstimecmp_rdata, 19)
        ctx.set(top.i_henvcfg_STCE, 1)
        ctx.set(top.i_vstime_valid, 1)
        await ctx.tick()
        observed.append((int(ctx.get(top.o_STIP)), int(ctx.get(top.o_VSTIP))))
        ctx.set(top.i_stime_valid, 0)
        ctx.set(top.i_vstime_valid, 0)
        ctx.set(top.i_menvcfg_STCE, 0)
        ctx.set(top.i_henvcfg_STCE, 0)
        await ctx.tick()
        observed.append((int(ctx.get(top.o_STIP)), int(ctx.get(top.o_VSTIP))))

    simulator = Simulator(top)
    simulator.add_clock(1e-6)
    simulator.add_testbench(bench)
    simulator.run()
    assert observed == [(1, 1), (1, 1)]
    verilog = module.build_verilog(None, {})
    assert "module SstcInterruptGen" in verilog
    return {"cycles": len(observed), "verilog_sha256": hashlib.sha256(verilog.encode()).hexdigest()}


# Inspect the locked reference modules / 检查锁定参考模块。
def inspect_reference() -> dict[str, Any]:
    """Record source/reference availability without copying generated SV. / 记录参考可用性。"""

    result: dict[str, Any] = {
        "path": str(REFERENCE_SV),
        "present": False,
        "sha256": None,
        "modules": [],
    }
    # The reference is built in WSL; invoke wslpath/sha256sum so this check
    # also works from the Windows coordinator checkout.
    probe = subprocess.run(
        ["wsl.exe", "-e", "bash", "-lc",
         "if test -s /home/lishuo/xs-v2-local/build/rtl/XSTop.sv; then "
         "sha256sum /home/lishuo/xs-v2-local/build/rtl/XSTop.sv; "
         "grep -oE '^module (CSA3_2|FliHTable|FliSTable|FliDTable|SstcInterruptGen)\\(' "
         "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv | sort -u; fi"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode == 0 and probe.stdout.strip():
        lines = probe.stdout.splitlines()
        digest = lines[0].split()[0]
        result["present"] = True
        result["sha256"] = digest
        result["modules"] = [
            line.removeprefix("module ").removesuffix("(")
            for line in lines[1:] if line.startswith("module ")
        ]
    return result


# Audit the five-zone and import contract / 审计五区与导入契约。
def audit_target(path: Path) -> dict[str, Any]:
    """Return structural audit facts for one target. / 返回目标结构审计事实。"""

    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    required = ("Module Contract", "Configuration", "Implementation",
                "Public Adapter", "Direct Entry")
    positions = [source.find(zone) for zone in required]
    assert all(position >= 0 for position in positions)
    assert positions == sorted(positions)
    assert "__all__" in source
    forbidden = ("importlib", "runpy", "subprocess", "socket", "urllib")
    assert not any(f"import {name}" in source or f"from {name}" in source
                   for name in forbidden)
    definitions = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            definitions.append(node.name)
            if node.name.startswith("_") and not (node.name.startswith("__") and node.name.endswith("__")):
                raise AssertionError(f"leading underscore helper: {node.name}")
            lines = source.splitlines()
            prior = lines[node.lineno - 2].strip() if node.lineno >= 2 else ""
            if not prior.startswith("#") or "/" not in prior:
                raise AssertionError(f"missing bilingual responsibility comment: {path}:{node.lineno}")
    return {"zones": list(required), "functions": sorted(definitions), "utf8_lf": "\r\n" not in source}


# Lint generated target Verilog with the available WSL Verilator.
def lint_generated_verilog(loaded: dict[str, Any]) -> dict[str, Any]:
    """Run Verilator lint on generated leaves. / 用 Verilator 检查生成叶子。"""

    temp_dir = Path(tempfile.mkdtemp(prefix="v2_decode_batch_"))
    outcomes: dict[str, Any] = {}
    try:
        for name, module in loaded.items():
            if not hasattr(module, "build_verilog"):
                continue
            target = temp_dir / f"{name}.sv"
            target.write_text(module.build_verilog(None, {}), encoding="utf-8", newline="\n")
            path_probe = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(target)],
                                        capture_output=True, text=True, check=False)
            if path_probe.returncode != 0:
                outcomes[name] = {"status": "SKIP", "reason": "wslpath unavailable"}
                continue
            wsl_path = path_probe.stdout.strip()
            run = subprocess.run(
                ["wsl.exe", "-e", "bash", "-lc",
                 f"verilator --lint-only -Wno-fatal {wsl_path}"],
                capture_output=True, text=True, check=False,
            )
            outcomes[name] = {"status": "PASS" if run.returncode == 0 else "FAIL",
                              "returncode": run.returncode,
                              "stderr_tail": run.stderr[-1000:]}
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    return outcomes


# Run Yosys synthesis parsing on generated leaves / 用 Yosys 解析合成生成叶子。
def yosys_check(loaded: dict[str, Any]) -> dict[str, Any]:
    """Parse and optimize each generated module with Yosys. / 用 Yosys 检查模块。"""

    temp_dir = Path(tempfile.mkdtemp(prefix="v2_decode_yosys_"))
    outcomes: dict[str, Any] = {}
    try:
        for name, module in loaded.items():
            target = temp_dir / f"{name}.sv"
            target.write_text(module.build_verilog(None, {}), encoding="utf-8", newline="\n")
            path_probe = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(target)],
                                        capture_output=True, text=True, check=False)
            if path_probe.returncode != 0:
                outcomes[name] = {"status": "SKIP", "reason": "wslpath unavailable"}
                continue
            wsl_path = path_probe.stdout.strip()
            top_name = "CSA3_2" if name == "CSA" else name
            command = (f"yosys -Q -p 'read_verilog -sv {wsl_path}; "
                       f"hierarchy -top {top_name}; proc; opt; stat'")
            run = subprocess.run(["wsl.exe", "-e", "bash", "-lc", command],
                                 capture_output=True, text=True, check=False)
            outcomes[name] = {"status": "PASS" if run.returncode == 0 else "FAIL",
                              "returncode": run.returncode,
                              "stderr_tail": run.stderr[-1000:]}
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    return outcomes


# Run the batch and write machine-readable evidence / 运行批次并写入机器证据。
def main() -> int:
    """Execute direct checks and persist pending-gate evidence. / 执行检查并持久化证据。"""

    targets = {
        "Instructions": BUILD_CORE / "Build-Cpu.Backend.Decode.Instructions-Hardware.py",
        "RiscvInst": BUILD_CORE / "Build-Cpu.Backend.Decode.Isa.Bitfield.RiscvInst-Hardware.py",
        "FliTable": BUILD_CORE / "Build-Cpu.Backend.Fu.Fpu.FliTable-Hardware.py",
        "CSA": BUILD_CORE / "Build-Cpu.Backend.Fu.Util.CSA-Hardware.py",
        "SstcInterruptGen": BUILD_CORE / "Build-Cpu.Backend.Fu.NewCSR.SstcInterruptGen-Hardware.py",
    }
    loaded = {name: load_target(f"v2_batch_{name}", path) for name, path in targets.items()}
    audits = {name: audit_target(path) for name, path in targets.items()}
    results = {
        "Instructions": test_instructions(loaded["Instructions"]),
        "RiscvInst": test_riscv(loaded["RiscvInst"]),
        "FliTable": test_fli(loaded["FliTable"]),
        "CSA": test_csa(loaded["CSA"]),
        "SstcInterruptGen": test_sstc(loaded["SstcInterruptGen"]),
    }
    evidence = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_DECODE_ARITHMETIC_BATCH",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "batch": ["Instructions", "RiscvInst", "FliTable", "CSA", "SstcInterruptGen"],
        "source_paths": {
            "Instructions": "upstream/src/main/scala/xiangshan/backend/decode/Instructions.scala",
            "RiscvInst": "upstream/src/main/scala/xiangshan/backend/decode/isa/bitfield/RiscvInst.scala",
            "FliTable": "upstream/src/main/scala/xiangshan/backend/fu/fpu/FliTable.scala",
            "CSA": "upstream/src/main/scala/xiangshan/backend/fu/util/CSA.scala",
            "SstcInterruptGen": "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala",
        },
        "commands": [
            "python validation/v2_decode_batch_direct.py",
            "python validation/v2_decode_batch_reference.py",
        ],
        "reference_differential_evidence": "validation/v2-decode-batch-reference-results.json",
        "status": "DIRECT_TEST_PASS_BOUNDED",
        "targets": results,
        "audits": audits,
        "verilator": lint_generated_verilog(loaded),
        "yosys": yosys_check(loaded),
        "reference": inspect_reference(),
        "gates": {
            "PYTHON_PRESENT": "PASS",
            "DIRECT_TEST_PASS_BOUNDED": "PASS",
            "V2_REFERENCE_MATCHED": "PENDING_COORDINATOR_REVIEW",
            "UHSC_LOCALIZED": "NOT_APPLICABLE_FOR_INTERNAL_LEAVES",
            "PARENT_CLOSURE_MATCHED": "PENDING",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "unclosed": [
            "Independent Amaranth-vs-extracted-SV transaction differential must be rerun by coordinator in WSL.",
            "Parent closure and UHSC external wrapper evidence are not part of this leaf batch.",
        ],
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
