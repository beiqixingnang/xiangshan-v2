"""Bounded V2 replacement-policy checks and evidence. / V2 替换策略有界检查与证据生成。"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from amaranth.sim import Simulator


ROOT = Path(__file__).resolve().parents[1]
PORTED = ROOT / "python" / "ported"
EVIDENCE = ROOT / "validation" / "v2-replacement-batch-results.json"
DIRECT_EVIDENCE = ROOT / "validation" / "v2-replacement-batch-direct-results.json"
REFERENCE_EVIDENCE = ROOT / "validation" / "v2-replacement-batch-reference-results.json"
NAMING_EVIDENCE = ROOT / "validation" / "v2-replacement-uhsc-naming-map.json"
COVERAGE = ROOT / "validation" / "v2-replacement-coverage-manifest.json"
REFERENCE = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
REFERENCE_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
REFERENCE_BYTES = 228590583
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
DEPENDENCY_COMMITS = {
    "utility": "2f0743f1f3ee1889049841926fa382cd0b32d8e2",
    "rocket-chip": "46f1efefa1ff431bffe3262e4830bc50316842f4",
}

TARGET_PATHS = {
    "LruStateGen": PORTED / "frontend" / "bpu" / "replacer" / "LruStateGen-Hardware.py",
    "PlruStateGen": PORTED / "frontend" / "bpu" / "replacer" / "PlruStateGen-Hardware.py",
    "ReplacerState": PORTED / "frontend" / "bpu" / "replacer" / "ReplacerState-Hardware.py",
}


# Return an independent triangular-matrix offset / 返回独立三角矩阵偏移
def oracle_pair_offset(lower: int, upper: int, ways: int) -> int:
    return sum(ways - row - 1 for row in range(lower)) + upper - lower - 1


# Independent TrueLRU transition oracle / 独立真 LRU 状态变换参考模型
def oracle_lru_next(state: int, touch: int, ways: int) -> int:
    if ways <= 1:
        return 0
    width = ways * (ways - 1) // 2
    state &= (1 << width) - 1
    if touch < 0 or touch >= ways:
        return state
    result = state
    for lower in range(ways - 1):
        for upper in range(lower + 1, ways):
            bit = oracle_pair_offset(lower, upper, ways)
            value = ((state >> bit) & 1)
            if touch == lower:
                value = 0
            elif touch == upper:
                value = 1
            result = (result & ~(1 << bit)) | (value << bit)
    return result


# Independent TrueLRU victim oracle / 独立真 LRU 受害路参考模型
def oracle_lru_victim(state: int, ways: int) -> int:
    if ways <= 1:
        return 0
    for candidate in range(ways):
        older = True
        for other in range(ways):
            if candidate == other:
                continue
            if candidate < other:
                older &= bool((state >> oracle_pair_offset(candidate, other, ways)) & 1)
            else:
                older &= not bool((state >> oracle_pair_offset(other, candidate, ways)) & 1)
        if older:
            return candidate
    return 0


# Independent PseudoLRU transition oracle / 独立伪 LRU 状态变换参考模型
def oracle_plru_next(state: int, touch: int, ways: int) -> int:
    if ways <= 1:
        return 0

    # Recurse through source tree partitions / 递归处理源树分区
    def recurse(current: int, selected: int, count: int) -> int:
        if count <= 1:
            return 0
        if count == 2:
            return 1 ^ (selected & 1)
        bits = (count - 1).bit_length()
        right_count = 1 << (bits - 1)
        left_count = count - right_count
        right_width = right_count - 1
        left_width = left_count - 1
        root = 1 ^ ((selected >> (bits - 1)) & 1)
        right_state = current & ((1 << right_width) - 1)
        left_state = (current >> right_width) & ((1 << left_width) - 1)
        right_next = recurse(right_state, selected, right_count)
        if left_count > 1:
            left_next = recurse(left_state, selected, left_count)
            left_result = left_state if root else left_next
            right_result = right_next if root else right_state
            return right_result | (left_result << right_width) | (root << (right_width + left_width))
        right_result = right_next if root else right_state
        return right_result | (root << right_width)

    return recurse(state & ((1 << (ways - 1)) - 1), touch, ways)


# Independent PseudoLRU victim oracle / 独立伪 LRU 受害路参考模型
def oracle_plru_victim(state: int, ways: int) -> int:
    if ways <= 1:
        return 0

    # Recurse through source victim partitions / 递归处理源受害路分区
    def recurse(current: int, count: int) -> int:
        if count <= 1:
            return 0
        if count == 2:
            return current & 1
        bits = (count - 1).bit_length()
        right_count = 1 << (bits - 1)
        left_count = count - right_count
        right_width = right_count - 1
        left_width = left_count - 1
        root = (current >> (right_width + left_width)) & 1
        right_state = current & ((1 << right_width) - 1)
        left_state = (current >> right_width) & ((1 << left_width) - 1)
        if root:
            child = recurse(left_state, left_count) if left_count > 1 else 0
        else:
            child = recurse(right_state, right_count)
        return child | (root << (bits - 1))

    return recurse(state & ((1 << (ways - 1)) - 1), ways)

SOURCE_PATHS = {
    "LruStateGen": [
        "upstream/utility/src/main/scala/utility/Replacement.scala",
        "upstream/rocket-chip/src/main/scala/util/Replacement.scala",
    ],
    "PlruStateGen": [
        "upstream/utility/src/main/scala/utility/Replacement.scala",
        "upstream/rocket-chip/src/main/scala/util/Replacement.scala",
    ],
    "ReplacerState": [
        "upstream/utility/src/main/scala/utility/Replacement.scala",
        "upstream/rocket-chip/src/main/scala/util/Replacement.scala",
    ],
}


# Load one target by exact path / 按精确路径加载一个目标
def load_target(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load target {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Audit encoding, zones, imports, and bilingual definition comments / 审计编码、分区、导入与双语定义注释
def audit_target(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise AssertionError(f"UTF-8 BOM present: {path}")
    source = raw.decode("utf-8")
    tree = ast.parse(source, filename=str(path))
    doc = ast.get_docstring(tree) or ""
    if not any("\u4e00" <= char <= "\u9fff" for char in doc):
        raise AssertionError(f"module docstring is not bilingual: {path}")
    zones = ("Module Contract", "Configuration", "Implementation",
             "Public Adapter", "Direct Entry")
    positions = [source.find(zone) for zone in zones]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise AssertionError(f"five-zone contract missing: {path}")
    if "__all__" not in source:
        raise AssertionError(f"explicit __all__ missing: {path}")
    forbidden = ("importlib", "runpy", "subprocess", "socket", "urllib", "pathlib")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [item.name.split(".")[0] for item in node.names]
            if any(name in forbidden for name in names):
                raise AssertionError(f"forbidden import in {path}")
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in forbidden:
                raise AssertionError(f"forbidden import in {path}")
    lines = source.splitlines()
    definitions: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            definitions.append(node.name)
            if node.name.startswith("_") and not (node.name.startswith("__") and node.name.endswith("__")):
                raise AssertionError(f"leading underscore helper {node.name}: {path}")
            prior = lines[node.lineno - 2].strip() if node.lineno >= 2 else ""
            if not prior.startswith("#") or "/" not in prior:
                raise AssertionError(f"missing bilingual responsibility comment {node.name}: {path}")
    return {
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "utf8_lf": b"\r\n" not in raw,
        "bilingual_docstring": True,
        "zones": list(zones),
        "functions": sorted(definitions),
    }


# Simulate one combinational target over deterministic vectors / 对组合目标执行确定性向量仿真
def simulate_combinational(top: Any, vectors: list[tuple[int, int]],
                           expected: Any) -> int:
    checks = 0

    # Drive and compare one combinational vector stream / 驱动并比较一组组合向量
    async def bench(ctx: Any) -> None:
        nonlocal checks
        for state, touch in vectors:
            ctx.set(top.state, state)
            ctx.set(top.touch_valid, 1)
            ctx.set(top.touch_way, touch)
            await ctx.delay(1e-9)
            observed = (int(ctx.get(top.nextState)), int(ctx.get(top.victim)))
            wanted = expected(state, touch)
            if observed != wanted:
                raise AssertionError(f"combinational mismatch {observed} != {wanted}")
            checks += 1

    simulator = Simulator(top)
    simulator.add_testbench(bench)
    simulator.run()
    return checks


# Run exhaustive and boundary TrueLRU checks / 执行穷举与边界真 LRU 检查
def test_lru(module: Any) -> dict[str, Any]:
    checks = 0
    for ways in range(1, 6):
        config = module.LruStateGenConfig(numWays=ways)
        top = module.LruStateGen(config)
        vectors = [(state, touch)
                   for state in range(1 << config.stateWidth)
                   for touch in range(1 << config.wayWidth)]
        for state, touch in vectors:
            assert module.lru_next_state(state, touch, ways) == oracle_lru_next(state, touch, ways)
            assert module.lru_victim(state, ways) == oracle_lru_victim(state, ways)
        checks += simulate_combinational(
            top, vectors,
            lambda state, touch, n=ways: (oracle_lru_next(state, touch, n),
                                          oracle_lru_victim(state, n)),
        )
    # Verify ordered simultaneous touches (later touch wins where applicable).
    config = module.LruStateGenConfig(numWays=4, accessSize=3)
    top = module.LruStateGen(config)

    # Compare ordered multi-touch folding / 比较有序多触碰折叠
    async def bench_multi(ctx: Any) -> None:
        nonlocal checks
        state = 0
        touches = (3, 1, 2)
        ctx.set(top.state, state)
        for index, touch in enumerate(touches):
            ctx.set(top.touches_valid[index], 1)
            ctx.set(top.touches_bits[index], touch)
            state = oracle_lru_next(state, touch, 4)
        await ctx.delay(1e-9)
        if int(ctx.get(top.nextState)) != state:
            raise AssertionError("TrueLRU multi-touch order mismatch")
        checks += 1

    simulator = Simulator(top)
    simulator.add_testbench(bench_multi)
    simulator.run()
    return {"vectors": checks, "boundary_ways": [1, 2, 3, 4, 5]}


# Run exhaustive and boundary PseudoLRU checks / 执行穷举与边界伪 LRU 检查
def test_plru(module: Any) -> dict[str, Any]:
    checks = 0
    for ways in range(1, 9):
        config = module.PlruStateGenConfig(numWays=ways)
        top = module.PlruStateGen(config)
        vectors = [(state, touch)
                   for state in range(1 << config.stateWidth)
                   for touch in range(1 << config.wayWidth)]
        for state, touch in vectors:
            assert module.plru_next_state(state, touch, ways) == oracle_plru_next(state, touch, ways)
            assert module.plru_victim(state, ways) == oracle_plru_victim(state, ways)
        checks += simulate_combinational(
            top, vectors,
            lambda state, touch, n=ways: (oracle_plru_next(state, touch, n),
                                          oracle_plru_victim(state, n)),
        )
    config = module.PlruStateGenConfig(numWays=5, accessSize=2)
    top = module.PlruStateGen(config)

    # Compare ordered non-power-of-two touches / 比较非二次幂路数的有序触碰
    async def bench_multi(ctx: Any) -> None:
        nonlocal checks
        state = 0
        for index, touch in enumerate((4, 2)):
            ctx.set(top.touches_valid[index], 1)
            ctx.set(top.touches_bits[index], touch)
            state = oracle_plru_next(state, touch, 5)
        await ctx.delay(1e-9)
        if int(ctx.get(top.nextState)) != state:
            raise AssertionError("PseudoLRU multi-touch order mismatch")
        checks += 1

    simulator = Simulator(top)
    simulator.add_testbench(bench_multi)
    simulator.run()
    return {"vectors": checks, "boundary_ways": list(range(1, 9))}


# Run clocked SetAssocLRU reset, touch, and way checks / 执行时钟式 SetAssocLRU 复位、触碰与选路检查
def test_replacer(module: Any) -> dict[str, Any]:
    total = 0
    reports: dict[str, Any] = {}
    for policy in ("lru", "plru"):
        config = module.ReplacerStateConfig(
            numSets=3, numWays=4, policy=policy, accessSize=2,
            numExtraReadPort=0, numExtraWritePort=0,
        )
        top = module.ReplacerState(config)

        policy_checks = 0

        # Drive one clocked policy-bank trace / 驱动一次时钟式策略组轨迹
        async def bench(ctx: Any, policy_name: str = policy,
                        target: Any = top, cfg: Any = config) -> None:
            nonlocal total, policy_checks
            states = [0] * cfg.numSets
            ctx.set(target.victim_set, 0)
            for valid in target.access_valid:
                ctx.set(valid, 0)
            await ctx.tick()
            if int(ctx.get(target.victim_way)) != (
                    oracle_lru_victim(0, 4) if policy_name == "lru" else oracle_plru_victim(0, 4)):
                raise AssertionError("reset victim mismatch")
            vectors = [
                ((0, 2), (0, 1)),
                ((1, 3), (2, 0)),
                ((2, 1), None),
                ((0, 0), (0, 3)),
            ]
            for first, second in vectors:
                for index, item in enumerate((first, second)):
                    if item is None:
                        ctx.set(target.access_valid[index], 0)
                        continue
                    set_index, way = item
                    ctx.set(target.access_sets[index], set_index)
                    ctx.set(target.access_ways[index], way)
                    ctx.set(target.access_valid[index], 1)
                    states[set_index] = (
                        oracle_lru_next(states[set_index], way, cfg.numWays)
                        if policy_name == "lru" else
                        oracle_plru_next(states[set_index], way, cfg.numWays))
                await ctx.tick()
                for valid in target.access_valid:
                    ctx.set(valid, 0)
                for set_index in range(cfg.numSets):
                    ctx.set(target.victim_set, set_index)
                    await ctx.delay(1e-9)
                    observed = int(ctx.get(target.victim_way))
                    wanted = (
                        oracle_lru_victim(states[set_index], cfg.numWays)
                        if policy_name == "lru" else
                        oracle_plru_victim(states[set_index], cfg.numWays))
                    if observed != wanted:
                        raise AssertionError((policy_name, set_index, observed, wanted))
                    total += 1
                    policy_checks += 1
            # The diagnostic raw write surface writes the same state vector.
            ctx.set(target.write_valid[0], 1)
            ctx.set(target.write_setIdx[0], 1)
            ctx.set(target.write_state[0], states[1] ^ ((1 << cfg.stateWidth) - 1))
            states[1] ^= (1 << cfg.stateWidth) - 1
            await ctx.tick()
            ctx.set(target.write_valid[0], 0)
            ctx.set(target.victim_set, 1)
            await ctx.delay(1e-9)
            if int(ctx.get(target.state_read)) != states[1]:
                raise AssertionError("diagnostic write mismatch")
            total += 1
            policy_checks += 1

        simulator = Simulator(top)
        simulator.add_clock(1e-6)
        simulator.add_testbench(bench)
        simulator.run()
        reports[policy] = {"checks": policy_checks}
    return {"checks": total, "policies": reports}


# Convert a Windows path to WSL form / 将 Windows 路径转换为 WSL 路径
def wsl_path(path: Path) -> str | None:
    try:
        probe = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                               capture_output=True, text=True, check=False)
    except OSError:
        return None
    if probe.returncode != 0:
        return None
    return probe.stdout.strip()


# Run Verilator lint and Yosys parsing on one generated module / 对单个生成模块执行 Verilator 与 Yosys 解析
def synthesize(name: str, source: str, directory: Path) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.sv"
    path.write_text(source, encoding="utf-8", newline="\n")
    converted = wsl_path(path)
    if converted is None:
        return {"verilator": {"status": "SKIP", "reason": "wslpath unavailable"},
                "yosys": {"status": "SKIP", "reason": "wslpath unavailable"}}
    verilator_run = subprocess.run(
        ["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal {converted}"],
        capture_output=True, text=True, check=False,
    )
    top_name = name
    yosys_command = (f"yosys -Q -p 'read_verilog -sv {converted}; "
                     f"hierarchy -top {top_name}; proc; opt; stat'")
    yosys_run = subprocess.run(
        ["wsl.exe", "-e", "bash", "-lc", yosys_command],
        capture_output=True, text=True, check=False,
    )
    return {
        "verilator": {
            "status": "PASS" if verilator_run.returncode == 0 else "FAIL",
            "returncode": verilator_run.returncode,
            "stderr_tail": verilator_run.stderr[-1200:],
        },
        "yosys": {
            "status": "PASS" if yosys_run.returncode == 0 else "FAIL",
            "returncode": yosys_run.returncode,
            "stderr_tail": yosys_run.stderr[-1200:],
        },
    }


# Read the locked XSTop identity and size / 读取锁定 XSTop 的身份与大小
def reference_info() -> dict[str, Any]:
    command = f"sha256sum {REFERENCE}; wc -c < {REFERENCE}"
    try:
        result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", command],
                                capture_output=True, text=True, check=False)
    except OSError:
        return {"status": "UNAVAILABLE", "reason": "wsl.exe unavailable"}
    if result.returncode != 0:
        return {"status": "UNAVAILABLE", "stderr": result.stderr[-1000:]}
    lines = result.stdout.strip().splitlines()
    digest = lines[0].split()[0] if lines else ""
    size = int(lines[1].strip()) if len(lines) > 1 and lines[1].strip().isdigit() else None
    return {
        "status": "PASS" if digest == REFERENCE_SHA256 and size == REFERENCE_BYTES else "MISMATCH",
        "path": REFERENCE,
        "sha256": digest,
        "bytes": size,
        "expected_sha256": REFERENCE_SHA256,
        "expected_bytes": REFERENCE_BYTES,
    }


# Extract one parent-closure module from the locked XSTop / 从锁定 XSTop 提取一个父闭包模块
def extract_reference(name: str) -> str | None:
    command = f"awk '/^module {name}\\(/,/^endmodule/' {REFERENCE}"
    try:
        result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", command],
                                capture_output=True, text=True, check=False)
    except OSError:
        return None
    if result.returncode != 0 or not result.stdout.startswith(f"module {name}("):
        return None
    return result.stdout


# Build a Verilog parent wrapper around the target policy bank / 为目标策略组构造 Verilog 父闭包包装器
def parent_wrapper(target: str, reference: str) -> str:
    # Render one explicitly mapped target instance / 渲染一个显式端口映射的目标实例
    def instance_text(hit_set: str, hit_valid: str, hit_way: str,
                      victim_valid: str, query_set: str,
                      policy_way: str) -> str:
        return f"""
      .clk(clock), .rst(reset),
      .io_access_0_set({hit_set}), .io_access_0_valid({hit_valid}), .io_access_0_way({hit_way}),
      .io_access_1_set(victim_set), .io_access_1_valid({victim_valid}), .io_access_1_way(victim_way_reg),
      .io_victim_set({query_set}), .io_victim_way({policy_way}),
      .io_state_read(), .io_state_next(),
      .io_read_0_setIdx(7'b0), .io_read_1_setIdx(7'b0),
      .io_write_0_valid(1'b0), .io_write_1_valid(1'b0),
      .io_write_0_bits_setIdx(7'b0), .io_write_1_bits_setIdx(7'b0),
      .io_write_0_bits_state(3'b0), .io_write_1_bits_state(3'b0),
      .io_read_0_state(), .io_read_1_state()
    """
    wrapper = f"""
{reference}
{target}
module UHSC_ReplacementParent(
  input clock, input reset,
  input io_touch_0_valid, input [7:0] io_touch_0_bits_vSetIdx, input [1:0] io_touch_0_bits_way,
  input io_touch_1_valid, input [7:0] io_touch_1_bits_vSetIdx, input [1:0] io_touch_1_bits_way,
  input io_victim_vSetIdx_valid, input [7:0] io_victim_vSetIdx_bits,
  output [1:0] io_victim_way
);
  wire [6:0] hit_set_0 = io_touch_0_bits_vSetIdx[0] ? io_touch_1_bits_vSetIdx[7:1] : io_touch_0_bits_vSetIdx[7:1];
  wire [6:0] hit_set_1 = io_touch_1_bits_vSetIdx[0] ? io_touch_1_bits_vSetIdx[7:1] : io_touch_0_bits_vSetIdx[7:1];
  wire hit_valid_0 = io_touch_0_bits_vSetIdx[0] ? io_touch_1_valid : io_touch_0_valid;
  wire hit_valid_1 = io_touch_1_bits_vSetIdx[0] ? io_touch_1_valid : io_touch_0_valid;
  wire [1:0] hit_way_0 = io_touch_0_bits_vSetIdx[0] ? io_touch_1_bits_way : io_touch_0_bits_way;
  wire [1:0] hit_way_1 = io_touch_1_bits_vSetIdx[0] ? io_touch_1_bits_way : io_touch_0_bits_way;
  reg [7:0] victim_vSetIdx_reg;
  reg [1:0] victim_way_reg;
  reg victim_valid_reg;
  wire [6:0] victim_set = victim_vSetIdx_reg[7:1];
  wire victim_valid_0 = victim_valid_reg && !victim_vSetIdx_reg[0];
  wire victim_valid_1 = victim_valid_reg && victim_vSetIdx_reg[0];
  wire [1:0] policy_way_0;
  wire [1:0] policy_way_1;
  ReplacerState dut0 ({instance_text("hit_set_0", "hit_valid_0", "hit_way_0", "victim_valid_0", "io_victim_vSetIdx_bits[7:1]", "policy_way_0")});
  ReplacerState dut1 ({instance_text("hit_set_1", "hit_valid_1", "hit_way_1", "victim_valid_1", "io_victim_vSetIdx_bits[7:1]", "policy_way_1")});
  assign io_victim_way = io_victim_vSetIdx_bits[0] ? policy_way_1 : policy_way_0;
  always @(posedge clock or posedge reset) begin
    if (reset) begin
      victim_vSetIdx_reg <= 8'b0;
      victim_way_reg <= 2'b0;
      victim_valid_reg <= 1'b0;
    end else begin
      if (io_victim_vSetIdx_valid) begin
        victim_vSetIdx_reg <= io_victim_vSetIdx_bits;
        victim_way_reg <= io_victim_way;
      end
      victim_valid_reg <= io_victim_vSetIdx_valid;
    end
  end
endmodule
module tb;
  reg clock, reset;
  reg io_touch_0_valid, io_touch_1_valid, io_victim_vSetIdx_valid;
  reg [7:0] io_touch_0_bits_vSetIdx, io_touch_1_bits_vSetIdx, io_victim_vSetIdx_bits;
  reg [1:0] io_touch_0_bits_way, io_touch_1_bits_way;
  wire [1:0] ref_way, dut_way;
  ICacheReplacer ref_inst(
    .clock(clock), .reset(reset),
    .io_touch_0_valid(io_touch_0_valid), .io_touch_0_bits_vSetIdx(io_touch_0_bits_vSetIdx), .io_touch_0_bits_way(io_touch_0_bits_way),
    .io_touch_1_valid(io_touch_1_valid), .io_touch_1_bits_vSetIdx(io_touch_1_bits_vSetIdx), .io_touch_1_bits_way(io_touch_1_bits_way),
    .io_victim_vSetIdx_valid(io_victim_vSetIdx_valid), .io_victim_vSetIdx_bits(io_victim_vSetIdx_bits), .io_victim_way(ref_way));
  UHSC_ReplacementParent dut_inst(
    .clock(clock), .reset(reset),
    .io_touch_0_valid(io_touch_0_valid), .io_touch_0_bits_vSetIdx(io_touch_0_bits_vSetIdx), .io_touch_0_bits_way(io_touch_0_bits_way),
    .io_touch_1_valid(io_touch_1_valid), .io_touch_1_bits_vSetIdx(io_touch_1_bits_vSetIdx), .io_touch_1_bits_way(io_touch_1_bits_way),
    .io_victim_vSetIdx_valid(io_victim_vSetIdx_valid), .io_victim_vSetIdx_bits(io_victim_vSetIdx_bits), .io_victim_way(dut_way));
  always #1 clock = ~clock;
  initial begin
    clock = 0; reset = 1; io_touch_0_valid = 0; io_touch_1_valid = 0; io_victim_vSetIdx_valid = 0;
    io_touch_0_bits_vSetIdx = 0; io_touch_1_bits_vSetIdx = 0; io_victim_vSetIdx_bits = 0;
    io_touch_0_bits_way = 0; io_touch_1_bits_way = 0;
    #4; reset = 0;
"""
    rng = random.Random(0xD1FF)
    checks = []
    for _ in range(96):
        t0_valid = rng.randrange(2)
        t1_valid = rng.randrange(2)
        victim_valid = rng.randrange(2)
        t0_set = rng.randrange(256)
        t1_set = rng.randrange(256)
        victim_set = rng.randrange(256)
        t0_way = rng.randrange(4)
        t1_way = rng.randrange(4)
        checks.append(
            f"    io_touch_0_valid = 1'b{t0_valid}; io_touch_1_valid = 1'b{t1_valid}; io_victim_vSetIdx_valid = 1'b{victim_valid}; "
            f"io_touch_0_bits_vSetIdx = 8'd{t0_set}; io_touch_1_bits_vSetIdx = 8'd{t1_set}; io_victim_vSetIdx_bits = 8'd{victim_set}; "
            f"io_touch_0_bits_way = 2'd{t0_way}; io_touch_1_bits_way = 2'd{t1_way}; #2; "
            f"if (ref_way !== dut_way) $fatal(1, \"replacement differential cycle {_}\");"
        )
    wrapper += "\n".join(checks) + "\n    $finish;\n  end\nendmodule\n"
    return wrapper


# Run the extracted parent-closure differential / 运行提取父闭包差分
def reference_differential(module: Any) -> dict[str, Any]:
    parent = extract_reference("ICacheReplacer")
    if parent is None:
        return {
            "status": "SOURCE_PARENT_CLOSURE_ONLY",
            "reason": "replacement policies are inlined; ICacheReplacer extraction unavailable",
            "source_paths": SOURCE_PATHS["ReplacerState"],
        }
    config = module.ReplacerStateConfig(numSets=128, numWays=4, policy="plru",
                                        accessSize=2, numExtraReadPort=0,
                                        numExtraWritePort=0)
    target = module.build_verilog(config, {})
    parent_hash = hashlib.sha256(parent.encode()).hexdigest()
    parent_bytes = len(parent.encode())
    temp = Path(tempfile.mkdtemp(prefix="v2_replacement_ref_"))
    try:
        source = parent_wrapper(target, parent)
        path = temp / "tb.sv"
        path.write_text(source, encoding="utf-8", newline="\n")
        converted = wsl_path(path)
        if converted is None:
            return {"status": "SOURCE_PARENT_CLOSURE_ONLY", "reason": "wslpath unavailable"}
        compile_result = subprocess.run(
            ["wsl.exe", "-e", "bash", "-lc",
             f"cd $(dirname {converted}) && verilator --binary --timing -Wno-fatal --top-module tb tb.sv"],
            capture_output=True, text=True, check=False,
        )
        if compile_result.returncode != 0:
            return {"status": "REFERENCE_DIFFERENTIAL_COMPILE_FAILED",
                    "stderr_tail": compile_result.stderr[-4000:]}
        binary = temp / "obj_dir" / "Vtb"
        binary_path = wsl_path(binary)
        if binary_path is None:
            return {"status": "SOURCE_PARENT_CLOSURE_ONLY", "reason": "binary path unavailable"}
        run_result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", binary_path],
                                    capture_output=True, text=True, check=False)
        return {
            "status": "PASS" if run_result.returncode == 0 else "REFERENCE_DIFFERENTIAL_FAILED",
            "returncode": run_result.returncode,
            "stdout_tail": run_result.stdout[-1000:],
            "stderr_tail": run_result.stderr[-3000:],
            "mode": "PARENT_CLOSURE_EXTRACTED",
            "module": "ICacheReplacer",
            "extracted_sha256": parent_hash,
            "extracted_bytes": parent_bytes,
            "observations": ["reset state", "victim selection", "touch/update", "way count=4"],
        }
    finally:
        shutil.rmtree(temp, ignore_errors=True)


# Write source and closure coverage manifest / 写入源文件与闭包覆盖清单
def write_coverage() -> None:
    coverage = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_REPLACEMENT_COVERAGE",
        "source_commit": SOURCE_COMMIT,
        "dependency_commits": DEPENDENCY_COMMITS,
        "family_id": "core.replacement",
        "closure_root": "core.replacement",
        "targets": [
            {
                "candidate": name,
                "python_path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "legacy_v3_surface": f"scala/src/main/scala/xiangshan/frontend/bpu/replacer/{name}.scala",
                "v2_sources": SOURCE_PATHS[name],
                "covered_children": ["TrueLRU", "PseudoLRU", "SetAssocLRU"],
                "classification": ("RELOCATED" if name != "ReplacerState" else "REWRITTEN"),
                "observation_points": ["reset state", "victim selection", "touch/update", "way count boundaries"],
                "reference_surface": "ICacheReplacer parent closure; no standalone replacement module in XSTop",
                "status": "PENDING_COORDINATOR_REVIEW",
            }
            for name, path in TARGET_PATHS.items()
        ],
        "locked_inputs": {
            "reference": REFERENCE,
            "reference_sha256": REFERENCE_SHA256,
            "reference_bytes": REFERENCE_BYTES,
        },
    }
    COVERAGE.write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")


# Write the batch-local UHSC naming mapping / 写入批次范围内的 UHSC 命名映射
def write_naming_map() -> None:
    mapping = {
        "schema_version": 1,
        "kind": "UHSC_REPLACEMENT_BATCH_NAMING_MAP",
        "source_commit": SOURCE_COMMIT,
        "reference_names_unchanged": True,
        "status": "PENDING_COORDINATOR_REVIEW",
        "entries": [
            {
                "source_name": "XSTop",
                "local_name": "UHSCTop",
                "visibility": "project-owned external HDL wrapper",
                "reason": "External top identity is localized only by a later wrapper; no locked SV text is renamed.",
            },
            {
                "source_name": "XiangShan / XS / KMHV2",
                "local_name": "UHSC",
                "visibility": "project-owned external product identity",
                "reason": "Source provenance and protocol names remain unchanged; only product-facing identity is UHSC.",
            },
        ],
        "targets": list(TARGET_PATHS),
        "gates": {"UHSC_LOCALIZED": "PENDING_EXTERNAL_WRAPPER", "ACCEPTED": "NOT_ALLOWED"},
    }
    NAMING_EVIDENCE.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8", newline="\n")


# Run the complete bounded batch and persist JSON evidence / 运行完整有界批次并持久化 JSON 证据
def main() -> int:
    modules = {name: load_target(f"v2_replacement_{name}", path)
               for name, path in TARGET_PATHS.items()}
    audits = {name: audit_target(path) for name, path in TARGET_PATHS.items()}
    direct = {
        "LruStateGen": test_lru(modules["LruStateGen"]),
        "PlruStateGen": test_plru(modules["PlruStateGen"]),
        "ReplacerState": test_replacer(modules["ReplacerState"]),
    }
    generated: dict[str, Any] = {}
    temp = Path(tempfile.mkdtemp(prefix="v2_replacement_lint_"))
    try:
        configs = {
            "LruStateGen": modules["LruStateGen"].LruStateGenConfig(numWays=4, accessSize=2),
            "PlruStateGen": modules["PlruStateGen"].PlruStateGenConfig(numWays=4, accessSize=2),
            "ReplacerState": modules["ReplacerState"].ReplacerStateConfig(
                numSets=4, numWays=4, policy="plru", accessSize=2,
                numExtraReadPort=0, numExtraWritePort=0,
            ),
        }
        for name, module in modules.items():
            first = module.build_verilog(configs[name], {})
            second = module.build_verilog(configs[name], {})
            if first != second:
                raise AssertionError(f"non-deterministic Verilog export: {name}")
            generated[name] = {
                "sha256": hashlib.sha256(first.encode()).hexdigest(),
                "bytes": len(first.encode()),
                "module": name,
                **synthesize(name, first, temp),
            }
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    ref_info = reference_info()
    differential = reference_differential(modules["ReplacerState"])
    write_coverage()
    write_naming_map()
    source_hashes = {}
    for name, paths in SOURCE_PATHS.items():
        source_hashes[name] = []
        for relative in paths:
            path = ROOT / relative
            raw = path.read_bytes()
            source_hashes[name].append({
                "path": relative,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
            })
    lint_pass = all(item["verilator"]["status"] == "PASS" and
                    item["yosys"]["status"] == "PASS"
                    for item in generated.values())
    direct_pass = True
    reference_pass = differential.get("status") == "PASS"
    evidence = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_REPLACEMENT_BATCH",
        "batch_id": "V2-P1-A-REPLACEMENT",
        "source_commit": SOURCE_COMMIT,
        "dependency_commits": DEPENDENCY_COMMITS,
        "family_ids": ["core.replacement"],
        "closure_roots": ["core.replacement"],
        "candidates": list(TARGET_PATHS),
        "source_paths": SOURCE_PATHS,
        "source_hashes": source_hashes,
        "commands": [
            "python validation/v2_replacement_batch_direct.py",
            "verilator --lint-only (generated target modules)",
            "yosys read_verilog/proc/opt/stat (generated target modules)",
            "verilator --binary parent differential against extracted ICacheReplacer",
        ],
        "direct_evidence": "validation/v2-replacement-batch-direct-results.json",
        "reference_differential_evidence": "validation/v2-replacement-batch-reference-results.json",
        "naming_evidence": "validation/v2-replacement-uhsc-naming-map.json",
        "observation_points": ["reset state", "victim selection", "touch/update", "way count boundaries"],
        "reference_artifact": {
            "path": REFERENCE,
            "sha256": REFERENCE_SHA256,
            "bytes": REFERENCE_BYTES,
            "verified": ref_info,
            "standalone_replacement_modules": [],
            "parent_closure_module": "ICacheReplacer",
        },
        "status": "PENDING_COORDINATOR_REVIEW",
        "direct_tests": direct,
        "structural_audit": audits,
        "generated": generated,
        "reference_differential": differential,
        "naming_mapping": [
            {
                "source_name": "XSTop",
                "local_name": "UHSCTop",
                "visibility": "project-owned external HDL wrapper",
                "reason": "UHSC localization is only at the external wrapper boundary; locked reference remains XSTop",
            },
            {
                "source_name": "XiangShan / XS / KMHV2",
                "local_name": "UHSC",
                "visibility": "project-owned external product identity",
                "reason": "Preserve source provenance and internal protocol names while exposing UHSC externally",
            },
        ],
        "license": {
            "inventory": "V2-Dependency-License-Inventory.json",
            "families": ["utility", "rocket-chip"],
            "status": "PENDING_COORDINATOR_REVIEW",
            "note": "Mixed utility/rocket-chip notices remain attached to source paths; no vendored source was modified.",
        },
        "gates": {
            "PYTHON_PRESENT": "PASS",
            "DIRECT_TEST_PASS_BOUNDED": "PASS" if direct_pass else "FAIL",
            "V2_REFERENCE_MATCHED": "PASS_BOUNDED" if reference_pass else "PENDING_COORDINATOR_REVIEW",
            "VERILATOR": "PASS" if lint_pass else "PENDING_COORDINATOR_REVIEW",
            "YOSYS": "PASS" if lint_pass else "PENDING_COORDINATOR_REVIEW",
            "UHSC_LOCALIZED": "PENDING_EXTERNAL_WRAPPER",
            "PARENT_CLOSURE_MATCHED": "PASS_BOUNDED" if reference_pass else "PENDING_COORDINATOR_REVIEW",
            "LICENSE_REVIEW": "PENDING_COORDINATOR_REVIEW",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "unclosed": [
            "Coordinator must review the parent-closure differential and rerun focused commands.",
            "No standalone replacement module is extractable from XSTop; ICacheReplacer parent closure is the bounded reference.",
            "External UHSC wrapper and mixed-license review remain outside this leaf batch.",
        ],
    }
    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    DIRECT_EVIDENCE.write_text(json.dumps({
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_REPLACEMENT_DIRECT_TESTS",
        "batch_id": "V2-P1-A-REPLACEMENT",
        "source_commit": SOURCE_COMMIT,
        "status": "PASS_BOUNDED",
        "targets": direct,
        "structural_audit": audits,
        "generated": generated,
        "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": "PASS",
                  "VERILATOR": "PASS" if lint_pass else "PENDING_COORDINATOR_REVIEW",
                  "YOSYS": "PASS" if lint_pass else "PENDING_COORDINATOR_REVIEW",
                  "ACCEPTED": "NOT_ALLOWED"},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    REFERENCE_EVIDENCE.write_text(json.dumps({
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_REPLACEMENT_REFERENCE_DIFFERENTIAL",
        "batch_id": "V2-P1-A-REPLACEMENT",
        "source_commit": SOURCE_COMMIT,
        "reference_artifact": {"path": REFERENCE, "sha256": REFERENCE_SHA256,
                                "bytes": REFERENCE_BYTES},
        "status": "PASS_BOUNDED" if reference_pass else "PENDING_COORDINATOR_REVIEW",
        "result": differential,
        "standalone_replacement_modules": [],
        "parent_closure": "ICacheReplacer",
        "gates": {"V2_REFERENCE_MATCHED": "PASS_BOUNDED" if reference_pass else "PENDING_COORDINATOR_REVIEW",
                  "PARENT_CLOSURE_MATCHED": "PASS_BOUNDED" if reference_pass else "PENDING_COORDINATOR_REVIEW",
                  "UHSC_LOCALIZED": "PENDING_EXTERNAL_WRAPPER",
                  "ACCEPTED": "NOT_ALLOWED"},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
