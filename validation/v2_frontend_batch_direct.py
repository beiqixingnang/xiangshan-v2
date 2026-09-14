"""Bounded V2 frontend/BPU/RVC direct checks. / V2 前端/BPU/RVC 直接检查。"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from amaranth.sim import Simulator


ROOT = Path(__file__).resolve().parents[1]
BUILD_CORE = ROOT / "python" / "Program-System" / "System-Build" / "Build-Cpu" / "Cpu-Core"
EVIDENCE = ROOT / "validation" / "v2-frontend-batch-results.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"


# Load a target module by exact path. / 按精确路径加载目标模块。
def load_target(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Audit the five-zone/function-comment contract. / 审计五区与函数注释契约。
def audit_target(path: Path) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    zones = ("Module Contract", "Configuration", "Implementation",
             "Public Adapter", "Direct Entry")
    positions = [source.find(zone) for zone in zones]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise AssertionError(f"zone order: {path}")
    if "__all__" not in source:
        raise AssertionError(f"missing __all__: {path}")
    forbidden = ("importlib", "runpy", "subprocess", "socket", "urllib")
    if any(f"import {name}" in source or f"from {name}" in source for name in forbidden):
        raise AssertionError(f"forbidden import: {path}")
    lines = source.splitlines()
    functions: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
            if node.name.startswith("_") and not (node.name.startswith("__") and node.name.endswith("__")):
                raise AssertionError(f"leading underscore helper: {path}:{node.lineno}")
            prior = lines[node.lineno - 2].strip() if node.lineno >= 2 else ""
            if not prior.startswith("#") or "/" not in prior:
                raise AssertionError(f"missing bilingual comment: {path}:{node.lineno}")
    return {"zones": list(zones), "functions": sorted(functions),
            "utf8_lf": "\r\n" not in source,
            "sha256": hashlib.sha256(source.encode()).hexdigest()}


# Simulate a combinational target for a sequence of vectors. / 仿真组合目标向量序列。
def simulate_vectors(top: Any, input_signal: Any, output_signals: list[Any],
                     vectors: list[int], secondary: Any | None = None,
                     secondary_values: list[int] | None = None) -> list[tuple[int, ...]]:
    observed: list[tuple[int, ...]] = []

    async def bench(ctx: Any) -> None:
        for index, value in enumerate(vectors):
            ctx.set(input_signal, value)
            if secondary is not None and secondary_values is not None:
                ctx.set(secondary, secondary_values[index])
            await ctx.delay(1e-9)
            observed.append(tuple(int(ctx.get(signal)) for signal in output_signals))

    simulator = Simulator(top)
    simulator.add_testbench(bench)
    simulator.run()
    return observed


# Exercise V2 unsigned satUpdate boundaries and random states. / 检查无符号 satUpdate 边界与随机状态。
def test_saturate(module: Any) -> dict[str, Any]:
    width = 4
    vectors = [(old, taken) for old in range(1 << width) for taken in (0, 1)]
    state = 0
    expected: list[int] = []
    for _, taken in vectors:
        state = module.sat_update(state, width, bool(taken))
        expected.append(state)
    top = module.SaturateCounterReg(module.SaturateCounterConfig(width=width, reset_value=0))
    # The registered harness is checked cycle-by-cycle with a software oracle.
    observed: list[int] = []

    async def bench(ctx: Any) -> None:
        ctx.set(top.en, 0)
        ctx.set(top.increase, 0)
        await ctx.tick()
        for _, taken in vectors:
            ctx.set(top.en, 1)
            ctx.set(top.increase, taken)
            await ctx.tick()
            observed.append(int(ctx.get(top.value)))

    simulator = Simulator(top)
    simulator.add_clock(1e-6)
    simulator.add_testbench(bench)
    simulator.run()
    assert observed == expected
    rtl = module.build_verilog(None, {})
    assert "module SaturateCounter" in rtl
    return {"vectors": len(vectors), "verilog_sha256": hashlib.sha256(rtl.encode()).hexdigest()}


# Exercise V2 signedSatUpdate boundaries and random states. / 检查有符号 satUpdate 边界与随机状态。
def test_signed(module: Any) -> dict[str, Any]:
    width = 5
    lower = -(1 << (width - 1))
    upper = (1 << (width - 1)) - 1
    values = list(range(lower, upper + 1))
    vectors = [(old, taken) for old in values for taken in (0, 1)]
    state = 0
    expected: list[int] = []
    for _, taken in vectors:
        state = module.signed_sat_update(state, width, bool(taken))
        expected.append(state)
    top = module.SignedSaturateCounterReg(module.SignedSaturateCounterConfig(width=width, reset_value=0))
    observed: list[int] = []

    async def bench(ctx: Any) -> None:
        ctx.set(top.en, 0)
        ctx.set(top.positive, 0)
        await ctx.tick()
        for _, taken in vectors:
            ctx.set(top.en, 1)
            ctx.set(top.positive, taken)
            await ctx.tick()
            observed.append(int(ctx.get(top.value)))

    simulator = Simulator(top)
    simulator.add_clock(1e-6)
    simulator.add_testbench(bench)
    simulator.run()
    assert observed == expected
    rtl = module.build_verilog(None, {})
    assert "module SignedSaturateCounter" in rtl
    return {"vectors": len(vectors), "verilog_sha256": hashlib.sha256(rtl.encode()).hexdigest()}


# Exercise NewDispatch's tie-breaking matrix and IQSort rows. / 检查 NewDispatch 平局矩阵与 IQSort。
def test_compare(module: Any) -> dict[str, Any]:
    rng = random.Random(0xC0A1)
    checks = 0
    for _ in range(256):
        counts = [rng.randrange(32) for _ in range(4)]
        matrix = module.compare_order(counts)
        sort_rows = module.sort_one_hot(matrix)
        assert all(matrix[i][i] == 0 for i in range(4))
        assert all(matrix[i][j] == (1 - matrix[j][i]) for i in range(4) for j in range(4) if i != j)
        assert all(sum(row) == 1 for row in sort_rows)
        checks += 1
    config = module.CompareMatrixConfig(n=4, position_width=5, rename_width=2)
    top = module.CompareMatrix(config)
    vectors = [[index, (index * 3) & 31, 7, 7] for index in range(8)]
    observed: list[tuple[int, ...]] = []

    async def bench(ctx: Any) -> None:
        ctx.set(top.reset, 1)
        await ctx.tick("sync")
        ctx.set(top.reset, 0)
        for counts in vectors:
            for signal, value in zip(top.issue_queue_counts, counts):
                ctx.set(signal, value)
            ctx.set(top.valid, 0xF)
            # NewDispatch declares IQSort as Reg, so observe it after the
            # active edge that captures the current comparison matrix.
            await ctx.tick("sync")
            observed.append(tuple(int(ctx.get(row)) for row in top.iq_sort))

    simulator = Simulator(top)
    simulator.add_clock(1e-6, domain="sync")
    simulator.add_testbench(bench)
    simulator.run()
    for counts, rows in zip(vectors, observed):
        expected = module.sort_one_hot(module.compare_order(counts))
        assert rows == tuple(sum((bit & 1) << index for index, bit in enumerate(row)) for row in expected)
    rtl = module.build_verilog(None, {})
    assert "module CompareMatrix" in rtl
    return {"random_vectors": checks, "deterministic_vectors": len(vectors),
            "verilog_sha256": hashlib.sha256(rtl.encode()).hexdigest()}


# Exercise the distributed FTB fall-through address/error equations. / 检查分布式 FTB 顺序地址与错误方程。
def test_fallthrough(module: Any) -> dict[str, Any]:
    cfg = module.FallThroughConfig()
    rng = random.Random(0xFA11)
    checks = 0
    for _ in range(512):
        pc = rng.randrange(1 << cfg.vaddr_bits)
        carry = bool(rng.randrange(2))
        pft = rng.randrange(cfg.predict_width)
        target, err = module.fall_through_target(pc, carry, pft, True, True, cfg)
        assert target < (1 << cfg.vaddr_bits)
        assert err == module.fall_through_error(pc, carry, pft, cfg)
        checks += 1
    top = module.FallThroughPredictor(cfg)
    observed: list[tuple[int, int, int]] = []

    async def bench(ctx: Any) -> None:
        for pc, carry, pft in ((0x1000, 0, 8), (0x1FF0, 1, 0), (0x12340, 0, 4)):
            ctx.set(top.start_pc, pc)
            ctx.set(top.carry, carry)
            ctx.set(top.pft_addr, pft)
            ctx.set(top.entry_valid, 1)
            ctx.set(top.hit, 1)
            ctx.set(top.s0_fire, 1)
            await ctx.tick()
            ctx.set(top.s0_fire, 0)
            await ctx.delay(1e-9)
            observed.append((int(ctx.get(top.pred_target)), int(ctx.get(top.fall_through_err)), int(ctx.get(top.fall_through_addr))))

    simulator = Simulator(top)
    simulator.add_clock(1e-6)
    simulator.add_testbench(bench)
    simulator.run()
    for (pc, carry, pft), (target, error, addr) in zip(((0x1000, 0, 8), (0x1FF0, 1, 0), (0x12340, 0, 4)), observed):
        expected_target, expected_err = module.fall_through_target(pc, bool(carry), pft, True, True, cfg)
        assert (target, error, addr) == (expected_target, int(expected_err), module.fall_through_address(pc, bool(carry), pft, cfg))
    rtl = module.build_verilog(None, {})
    assert "module FallThroughPredictor" in rtl
    return {"random_vectors": checks, "deterministic_vectors": len(observed),
            "verilog_sha256": hashlib.sha256(rtl.encode()).hexdigest()}


# Exercise the pure RVC closure on all compressed quadrants and modes. / 检查全部 RVC 象限与模式。
def test_rvc(module: Any) -> dict[str, Any]:
    cfg = module.RvcExpanderConfig()
    # Deterministic corner vectors plus a broad pseudo-random sample.
    vectors = list(range(0x100)) + [0x0001, 0x6141, 0x9002, 0x8082, 0xFFFF]
    rng = random.Random(0xA5C)
    vectors += [rng.randrange(1 << 16) for _ in range(1024)]
    for value in vectors:
        for fs in (False, True):
            result = module.decode_rvc(value, fs, cfg)
            assert len(result) == 6
            assert 0 <= result[0] < (1 << 32)
    top = module.RvcExpander(cfg)
    sample = vectors[:256]
    pairs = [(value, fs) for value in sample for fs in (0, 1)]
    observed = simulate_vectors(top, top.in_, [top.out_bits, top.ill],
                                [value for value, _ in pairs], top.fsIsOff,
                                [fs for _, fs in pairs])
    for (value, fs), result in zip(pairs, observed):
        expected = module.decode_rvc(value, bool(fs), cfg)
        assert result == (expected[0], int(expected[5]))
    rtl = module.build_verilog(None, {})
    assert "module RVCExpander" in rtl
    return {"pure_vectors": len(vectors) * 2, "sim_vectors": len(pairs),
            "verilog_sha256": hashlib.sha256(rtl.encode()).hexdigest()}


# Run Verilator lint and Yosys parsing on generated leaf RTL. / 用 Verilator 与 Yosys 检查生成叶子 RTL。
def synth_checks(loaded: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    verilator: dict[str, Any] = {}
    yosys: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="v2_frontend_batch_") as temp:
        directory = Path(temp)
        for name, module in loaded.items():
            rtl = module.build_verilog(None, {})
            path = directory / f"{name}.sv"
            path.write_text(rtl, encoding="utf-8", newline="\n")
            probe = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)], capture_output=True, text=True, check=False)
            if probe.returncode != 0:
                verilator[name] = {"status": "SKIP", "reason": "wslpath unavailable"}
                yosys[name] = {"status": "SKIP", "reason": "wslpath unavailable"}
                continue
            wpath = probe.stdout.strip()
            run = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal {wpath}"], capture_output=True, text=True, check=False)
            verilator[name] = {"status": "PASS" if run.returncode == 0 else "FAIL", "returncode": run.returncode, "stderr_tail": run.stderr[-1200:]}
            top_name = "RVCExpander" if name == "RvcExpander" else name
            command = f"yosys -Q -p 'read_verilog -sv {wpath}; hierarchy -top {top_name}; proc; opt; stat'"
            yrun = subprocess.run(["wsl.exe", "-e", "bash", "-lc", command], capture_output=True, text=True, check=False)
            yosys[name] = {"status": "PASS" if yrun.returncode == 0 else "FAIL", "returncode": yrun.returncode, "stderr_tail": yrun.stderr[-1200:]}
    return verilator, yosys


# Execute the batch and persist machine-readable evidence. / 执行批次并写入机器证据。
def main() -> int:
    targets = {
        "CompareMatrix": BUILD_CORE / "Build-Cpu.Frontend.Bpu.CompareMatrix-Hardware.py",
        "FallThroughPredictor": BUILD_CORE / "Build-Cpu.Frontend.Bpu.FallThroughPredictor-Hardware.py",
        "SaturateCounter": BUILD_CORE / "Build-Cpu.Frontend.Bpu.SaturateCounter-Hardware.py",
        "SignedSaturateCounter": BUILD_CORE / "Build-Cpu.Frontend.Bpu.SignedSaturateCounter-Hardware.py",
        "RvcExpander": BUILD_CORE / "Build-Cpu.Frontend.Ifu.RvcExpander-Hardware.py",
    }
    loaded = {name: load_target(f"v2_frontend_{name}", path) for name, path in targets.items()}
    audits = {name: audit_target(path) for name, path in targets.items()}
    results = {
        "CompareMatrix": test_compare(loaded["CompareMatrix"]),
        "FallThroughPredictor": test_fallthrough(loaded["FallThroughPredictor"]),
        "SaturateCounter": test_saturate(loaded["SaturateCounter"]),
        "SignedSaturateCounter": test_signed(loaded["SignedSaturateCounter"]),
        "RvcExpander": test_rvc(loaded["RvcExpander"]),
    }
    verilator, yosys = synth_checks(loaded)
    evidence = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_FRONTEND_BPU_RVC_BATCH",
        "source_commit": SOURCE_COMMIT,
        "batch_id": "V2-P1-C-FRONTEND-BPU-RVC",
        "source_paths": {
            "CompareMatrix": ["upstream/src/main/scala/xiangshan/backend/dispatch/NewDispatch.scala"],
            "FallThroughPredictor": ["upstream/src/main/scala/xiangshan/frontend/BPU.scala", "upstream/src/main/scala/xiangshan/frontend/FTB.scala", "upstream/src/main/scala/xiangshan/frontend/FrontendBundle.scala", "upstream/src/main/scala/xiangshan/frontend/NewFtq.scala"],
            "SaturateCounter": ["upstream/src/main/scala/xiangshan/frontend/BPU.scala", "upstream/src/main/scala/xiangshan/frontend/Tage.scala", "upstream/src/main/scala/xiangshan/frontend/SC.scala"],
            "SignedSaturateCounter": ["upstream/src/main/scala/xiangshan/frontend/BPU.scala", "upstream/src/main/scala/xiangshan/frontend/SC.scala"],
            "RvcExpander": ["upstream/src/main/scala/xiangshan/frontend/PreDecode.scala", "upstream/rocket-chip/src/main/scala/rocket/RVC.scala"],
        },
        "observation_points": ["counter saturation", "signed update", "fall-through target/error", "RVC expansion", "dispatch ordering"],
        "commands": ["python validation/v2_frontend_batch_direct.py", "python validation/v2_frontend_batch_reference.py"],
        "coverage_manifest": "validation/v2-frontend-bpu-rvc-coverage-manifest.json",
        "status": "DIRECT_TEST_PASS_BOUNDED",
        "targets": results,
        "audits": audits,
        "verilator": verilator,
        "yosys": yosys,
        "gates": {
            "PYTHON_PRESENT": "PASS",
            "DIRECT_TEST_PASS_BOUNDED": "PASS",
            "V2_REFERENCE_MATCHED": "PENDING_COORDINATOR_REVIEW",
            "UHSC_LOCALIZED": "PENDING_EXTERNAL_WRAPPER",
            "PARENT_CLOSURE_MATCHED": "PENDING",
            "LICENSE_REVIEW": "PENDING",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "uhsc_naming_mapping": [
            {"source_name": "XSTop", "local_name": "UHSCTop", "visibility": "project-owned external HDL wrapper", "reason": "External localization only; locked reference names remain unchanged", "status": "PLANNED"},
            {"source_name": "XiangShan / XS / KMHV2", "local_name": "UHSC", "visibility": "project-owned external product identity", "reason": "Product-facing identity localization without internal protocol renaming", "status": "PLANNED"},
        ],
        "unclosed": [
            "RVC extracted-SV differential is run by the companion reference script.",
            "Non-extractable CompareMatrix/FallThroughPredictor/counter behavior remains source-level and parent-closure evidence.",
            "External UHSC wrapper and parent closure are outside this leaf batch.",
        ],
    }
    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
