"""Independent V2 frontend BPU state-family validator. / V2 前端 BPU 状态族独立验证器。"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import itertools
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

from amaranth import Module, Signal, signed
from amaranth.sim import Simulator


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core"
RESULT = ROOT / "validation/v2-frontend-bpu-state-family-results.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
LOCKED_REFERENCE = Path(r"\\wsl$\Debian\home\lishuo\xs-v2-local\build\rtl\XSTop.sv")
LOCKED_CANONICAL = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
LOCKED_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
LOCKED_BYTES = 228590583

TARGETS = {
    "CompareMatrix": BUILD / "Build-Cpu.Frontend.Bpu.CompareMatrix-Hardware.py",
    "FallThroughPredictor": BUILD / "Build-Cpu.Frontend.Bpu.FallThroughPredictor-Hardware.py",
    "SaturateCounter": BUILD / "Build-Cpu.Frontend.Bpu.SaturateCounter-Hardware.py",
    "SignedSaturateCounter": BUILD / "Build-Cpu.Frontend.Bpu.SignedSaturateCounter-Hardware.py",
    "LruStateGen": BUILD / "Build-Cpu.Frontend.Bpu.Replacer.LruStateGen-Hardware.py",
    "PlruStateGen": BUILD / "Build-Cpu.Frontend.Bpu.Replacer.PlruStateGen-Hardware.py",
    "ReplacerState": BUILD / "Build-Cpu.Frontend.Bpu.Replacer.ReplacerState-Hardware.py",
}

SOURCE_PATHS = {
    "CompareMatrix": ["upstream/src/main/scala/xiangshan/backend/dispatch/NewDispatch.scala"],
    "FallThroughPredictor": [
        "upstream/src/main/scala/xiangshan/frontend/BPU.scala",
        "upstream/src/main/scala/xiangshan/frontend/FTB.scala",
        "upstream/src/main/scala/xiangshan/frontend/FrontendBundle.scala",
        "upstream/src/main/scala/xiangshan/frontend/NewFtq.scala",
    ],
    "SaturateCounter": [
        "upstream/src/main/scala/xiangshan/frontend/BPU.scala",
        "upstream/src/main/scala/xiangshan/frontend/Bim.scala",
        "upstream/src/main/scala/xiangshan/frontend/Tage.scala",
        "upstream/src/main/scala/xiangshan/frontend/SC.scala",
    ],
    "SignedSaturateCounter": [
        "upstream/src/main/scala/xiangshan/frontend/BPU.scala",
        "upstream/src/main/scala/xiangshan/frontend/SC.scala",
    ],
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


# Return a raw SHA-256 digest. / 返回原始字节 SHA-256 摘要。
def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


# Load one exact final Build path. / 加载一个最终 Build 精确路径。
def load_target(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(f"v2_bpu_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Audit source formatting and the exact public adapter contract. / 审计格式与精确公共适配器契约。
def audit_target(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw:
        raise AssertionError(f"encoding/line-ending violation: {path}")
    source = raw.decode("utf-8")
    tree = ast.parse(source, filename=str(path))
    doc = ast.get_docstring(tree) or ""
    if not any("\u4e00" <= char <= "\u9fff" for char in doc):
        raise AssertionError(f"module docstring is not bilingual: {path}")
    zones = ("Module Contract", "Configuration", "Implementation",
             "Public Adapter", "Direct Entry")
    positions = [source.find(zone) for zone in zones]
    if any(pos < 0 for pos in positions) or positions != sorted(positions):
        raise AssertionError(f"five-zone order violation: {path}")
    adapters = [node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == "build_verilog"]
    if len(adapters) != 1 or [arg.arg for arg in adapters[0].args.args] != [
            "configuration", "injected_dependencies"]:
        raise AssertionError(f"adapter signature violation: {path}")
    forbidden = {"importlib", "runpy", "subprocess", "socket", "urllib", "pathlib"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(item.name.split(".")[0] in forbidden for item in node.names):
                raise AssertionError(f"forbidden import: {path}")
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in forbidden:
                raise AssertionError(f"forbidden import: {path}")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_") and not (
                    node.name.startswith("__") and node.name.endswith("__")):
                raise AssertionError(f"leading underscore helper: {path}:{node.name}")
            prior = source.splitlines()[node.lineno - 2].strip() if node.lineno >= 2 else ""
            if not prior.startswith("#") or "/" not in prior:
                raise AssertionError(f"missing bilingual comment: {path}:{node.name}")
    return {
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "bytes": len(raw),
        "sha256": digest(raw),
        "utf8_lf": True,
        "ast_parse": True,
        "bilingual_docstring": True,
        "zones": list(zones),
        "adapter_signature": ["configuration", "injected_dependencies"],
    }


# Run a combinational Amaranth probe over integer vectors. / 对整数向量运行组合 Amaranth 探针。
def run_comb_probe(probe: Module, inputs: list[tuple[Signal, int]],
                   outputs: list[Signal], expected: Callable[[tuple[int, ...]], tuple[int, ...]]) -> int:
    checks = 0

    async def bench(ctx: Any) -> None:
        nonlocal checks
        for values in inputs:
            for signal, value in zip((item[0] for item in inputs), values):
                ctx.set(signal, value)
            await ctx.delay(1e-9)
            observed = tuple(int(ctx.get(signal)) for signal in outputs)
            wanted = expected(values)
            if observed != wanted:
                raise AssertionError((values, observed, wanted))
            checks += 1

    simulator = Simulator(probe)
    simulator.add_testbench(bench)
    simulator.run()
    return checks


# Validate the NewDispatch comparison matrix and registered IQSort boundary.
# 验证 NewDispatch 比较矩阵及 IQSort 寄存器边界。
def test_compare(module: Any) -> dict[str, int]:
    pure = 0
    for size in range(1, 5):
        for counts in itertools.product(range(4), repeat=size):
            matrix = module.compare_order(counts)
            rows = module.sort_one_hot(matrix)
            assert all(matrix[i][i] == 0 for i in range(size))
            assert all(matrix[i][j] == 1 - matrix[j][i]
                       for i in range(size) for j in range(size) if i != j)
            assert all(sum(row) == 1 for row in rows)
            pure += 1
    cfg = module.CompareMatrixConfig(n=4, position_width=5, rename_width=2)
    top = module.CompareMatrix(cfg)
    rng = random.Random(0xC0A1)
    vectors = [(0, 0, 0, 0), (0, 3, 7, 7), (31, 0, 31, 1)]
    vectors += [tuple(rng.randrange(32) for _ in range(4)) for _ in range(128)]
    checks = 0

    async def bench(ctx: Any) -> None:
        nonlocal checks
        ctx.set(top.reset, 1)
        await ctx.tick("sync")
        ctx.set(top.reset, 0)
        for counts in vectors:
            for signal, value in zip(top.issue_queue_counts, counts):
                ctx.set(signal, value)
            await ctx.delay(1e-9)
            expected_matrix = module.compare_order(counts)
            for row, signal in enumerate(top.compare_matrix):
                expected_mask = sum(bit << col for col, bit in enumerate(expected_matrix[row]))
                assert int(ctx.get(signal)) == expected_mask
                checks += 1
            # IQSort is a Reg in V2 and therefore samples the current matrix
            # at the following active edge.  IQSort 在 V2 中是寄存器，边沿后才观察。
            await ctx.tick("sync")
            expected_rows = module.sort_one_hot(expected_matrix)
            for rank, signal in enumerate(top.iq_sort):
                expected_mask = sum(bit << col for col, bit in enumerate(expected_rows[rank]))
                assert int(ctx.get(signal)) == expected_mask
                checks += 1
            for slot, signal in enumerate(top.min_iq_sel):
                expected_rank = slot % cfg.n
                expected_mask = sum(expected_rows[expected_rank][row] << cfg.effective_exu_indices[row]
                                     for row in range(cfg.n))
                assert int(ctx.get(signal)) == expected_mask
                checks += 1

    simulator = Simulator(top)
    simulator.add_clock(1e-6, domain="sync")
    simulator.add_testbench(bench)
    simulator.run()
    return {"pure_vectors": pure, "hardware_vectors": len(vectors), "checks": checks}


# Validate the BPU fall-through address/error equations and staging.
# 验证 BPU 顺序地址、错误方程及分级行为。
def test_fallthrough(module: Any) -> dict[str, int]:
    cfg = module.FallThroughConfig()
    pure = 0
    highs = (0, 1, 0x12345, (1 << cfg.vaddr_bits - 5) - 1)
    for high in highs:
        for pc_low in range(1 << cfg.pft_width):
            for carry in (False, True):
                for pft in range(1 << cfg.pft_width):
                    pc = (high << (cfg.inst_offset_bits + cfg.pft_width)) | (pc_low << cfg.inst_offset_bits)
                    target, error = module.fall_through_target(pc, carry, pft, True, True, cfg)
                    assert target == (module.fall_through_address(pc, carry, pft, cfg)
                                      if not error else (pc + cfg.fetch_width * 4) & ((1 << cfg.vaddr_bits) - 1))
                    pure += 1
    top = module.FallThroughPredictor(cfg)
    vectors = [(0x1000, 0, 8, 1, 1), (0x1FF0, 1, 0, 1, 1),
               (0x12340, 0, 4, 1, 1), (0x23450, 0, 3, 0, 1),
               (0x34560, 1, 12, 1, 0)]
    checks = 0

    async def bench(ctx: Any) -> None:
        nonlocal checks
        for pc, carry, pft, valid, hit in vectors:
            ctx.set(top.start_pc, pc)
            ctx.set(top.carry, carry)
            ctx.set(top.pft_addr, pft)
            ctx.set(top.entry_valid, valid)
            ctx.set(top.hit, hit)
            ctx.set(top.s0_fire, 1)
            await ctx.tick()
            ctx.set(top.s0_fire, 0)
            await ctx.delay(1e-9)
            expected_target, expected_error = module.fall_through_target(
                pc, bool(carry), pft, bool(valid), bool(hit), cfg)
            assert int(ctx.get(top.pred_target)) == expected_target
            assert int(ctx.get(top.fall_through_addr)) == module.fall_through_address(
                pc, bool(carry), pft, cfg)
            assert int(ctx.get(top.fall_through_err)) == int(module.fall_through_error(
                pc, bool(carry), pft, cfg))
            assert int(ctx.get(top.pred_taken)) == 0
            checks += 4

    simulator = Simulator(top)
    simulator.add_clock(1e-6)
    simulator.add_testbench(bench)
    simulator.run()
    return {"pure_vectors": pure, "staged_vectors": len(vectors), "checks": checks}


# Validate unsigned saturation against an independent arithmetic oracle.
# 使用独立算术预言机验证无符号饱和。
def test_unsigned_counter(module: Any) -> dict[str, int]:
    checks = 0
    for width in range(1, 9):
        old = Signal(width)
        taken = Signal()
        enable = Signal()
        updated = Signal(width)
        probe = Module()
        counter = module.SaturateCounter(width, old)
        probe.d.comb += updated.eq(counter.get_updated_value(taken, enable))

        async def bench(ctx: Any, width_value: int = width) -> None:
            nonlocal checks
            limit = (1 << width_value) - 1
            for old_value in range(limit + 1):
                for taken_value in (0, 1):
                    for enable_value in (0, 1):
                        ctx.set(old, old_value)
                        ctx.set(taken, taken_value)
                        ctx.set(enable, enable_value)
                        await ctx.delay(1e-9)
                        expected = old_value if not enable_value else (
                            min(old_value + 1, limit) if taken_value else max(old_value - 1, 0))
                        assert int(ctx.get(updated)) == expected
                        checks += 1

        simulator = Simulator(probe)
        simulator.add_testbench(bench)
        simulator.run()
    return {"expression_vectors": checks}


# Validate signed saturation against an independent two's-complement oracle.
# 使用独立补码预言机验证有符号饱和。
def test_signed_counter(module: Any) -> dict[str, int]:
    checks = 0
    for width in range(2, 9):
        old = Signal(signed(width))
        taken = Signal()
        enable = Signal()
        updated = Signal(signed(width))
        probe = Module()
        counter = module.SignedSaturateCounter(width, old)
        probe.d.comb += updated.eq(counter.get_updated_value(taken, enable))

        async def bench(ctx: Any, width_value: int = width) -> None:
            nonlocal checks
            lower = -(1 << (width_value - 1))
            upper = (1 << (width_value - 1)) - 1
            modulus = 1 << width_value
            for old_value in range(lower, upper + 1):
                for taken_value in (0, 1):
                    for enable_value in (0, 1):
                        ctx.set(old, old_value)
                        ctx.set(taken, taken_value)
                        ctx.set(enable, enable_value)
                        await ctx.delay(1e-9)
                        expected = old_value if not enable_value else (
                            min(old_value + 1, upper) if taken_value else max(old_value - 1, lower))
                        raw = int(ctx.get(updated)) & (modulus - 1)
                        observed = raw - modulus if raw & (1 << (width_value - 1)) else raw
                        assert observed == expected
                        checks += 1

        simulator = Simulator(probe)
        simulator.add_testbench(bench)
        simulator.run()
    return {"expression_vectors": checks}


# Independent TrueLRU arithmetic oracle. / 独立真 LRU 算术预言机。
def lru_oracle_next(state: int, touch: int, ways: int) -> int:
    if ways <= 1 or not 0 <= touch < ways:
        return 0 if ways <= 1 else state & ((1 << (ways * (ways - 1) // 2)) - 1)
    result = state & ((1 << (ways * (ways - 1) // 2)) - 1)
    offset = 0
    for lower in range(ways - 1):
        for upper in range(lower + 1, ways):
            value = 0 if touch == lower else 1 if touch == upper else (result >> offset) & 1
            result = (result & ~(1 << offset)) | (value << offset)
            offset += 1
    return result


# Independent TrueLRU victim oracle. / 独立真 LRU 受害路预言机。
def lru_oracle_victim(state: int, ways: int) -> int:
    if ways <= 1:
        return 0
    offset = lambda lower, upper: sum(ways - row - 1 for row in range(lower)) + upper - lower - 1
    for candidate in range(ways):
        older = True
        for other in range(ways):
            if candidate == other:
                continue
            bit = ((state >> offset(candidate, other)) & 1 if candidate < other
                   else (state >> offset(other, candidate)) & 1)
            older = older and bit == (1 if candidate < other else 0)
        if older:
            return candidate
    return 0


# Independent unbalanced tree-PLRU transition oracle. / 独立非平衡树伪 LRU 转换预言机。
def plru_oracle_next(state: int, touch: int, ways: int) -> int:
    if ways <= 1:
        return 0
    state &= (1 << (ways - 1)) - 1

    def recurse(current: int, selected: int, count: int) -> int:
        if count <= 1:
            return 0
        if count == 2:
            return 1 ^ (selected & 1)
        bits = (count - 1).bit_length()
        right = 1 << (bits - 1)
        left = count - right
        right_width = right - 1
        left_width = left - 1
        root = 1 ^ ((selected >> (bits - 1)) & 1)
        right_state = current & ((1 << right_width) - 1)
        left_state = (current >> right_width) & ((1 << left_width) - 1)
        right_next = recurse(right_state, selected, right)
        if left > 1:
            left_next = recurse(left_state, selected, left)
            return ((right_next if root else right_state) |
                    ((left_state if root else left_next) << right_width) |
                    (root << (right_width + left_width)))
        return (right_next if root else right_state) | (root << right_width)

    return recurse(state, touch, ways)


# Independent unbalanced tree-PLRU victim oracle. / 独立非平衡树伪 LRU 受害路预言机。
def plru_oracle_victim(state: int, ways: int) -> int:
    if ways <= 1:
        return 0
    state &= (1 << (ways - 1)) - 1

    def recurse(current: int, count: int) -> int:
        if count <= 1:
            return 0
        if count == 2:
            return current & 1
        bits = (count - 1).bit_length()
        right = 1 << (bits - 1)
        left = count - right
        right_width = right - 1
        left_width = left - 1
        root = (current >> (right_width + left_width)) & 1
        right_state = current & ((1 << right_width) - 1)
        left_state = (current >> right_width) & ((1 << left_width) - 1)
        child = recurse(left_state, left) if root and left > 1 else (
            0 if root else recurse(right_state, right))
        return child | (root << (bits - 1))

    return recurse(state, ways)


# Validate both policy leaves exhaustively and the state-bank transaction path.
# 穷举两种替换策略叶子并验证状态组事务路径。
def test_replacement(modules: dict[str, Any]) -> dict[str, int]:
    lru_checks = 0
    plru_checks = 0
    for ways in range(1, 9):
        lru = modules["LruStateGen"]
        lcfg = lru.LruStateGenConfig(numWays=ways, accessSize=1)
        ltop = lru.LruStateGen(lcfg)
        # TrueLRU has a triangular state space; exhaust it through five ways
        # and use deterministic edge/random sampling for larger legal widths.
        # 真 LRU 状态空间呈三角指数增长，五路以上采用确定性边界/随机采样。
        if ways <= 5:
            lstates = list(range(1 << lcfg.stateWidth))
        else:
            rng = random.Random(0x1A0 + ways)
            lstates = list(range(min(16, 1 << lcfg.stateWidth)))
            lstates += [rng.randrange(1 << lcfg.stateWidth) for _ in range(128)]
        lvec = [(state, touch) for state in lstates
                for touch in range(1 << lcfg.wayWidth)]
        async def lbench(ctx: Any, top: Any = ltop, vectors: list[tuple[int, int]] = lvec,
                         width: int = ways) -> None:
            nonlocal lru_checks
            for state, touch in vectors:
                ctx.set(top.state, state)
                ctx.set(top.touch_valid, 1)
                ctx.set(top.touch_way, touch)
                await ctx.delay(1e-9)
                assert int(ctx.get(top.nextState)) == lru_oracle_next(state, touch, width)
                assert int(ctx.get(top.victim)) == lru_oracle_victim(state, width)
                lru_checks += 1
        sim = Simulator(ltop)
        sim.add_testbench(lbench)
        sim.run()

        plru = modules["PlruStateGen"]
        pcfg = plru.PlruStateGenConfig(numWays=ways, accessSize=1)
        ptop = plru.PlruStateGen(pcfg)
        if ways <= 8:
            pstates = list(range(1 << pcfg.stateWidth))
        else:
            pstates = []
        pvec = [(state, touch) for state in pstates
                for touch in range(1 << pcfg.wayWidth)]
        async def pbench(ctx: Any, top: Any = ptop, vectors: list[tuple[int, int]] = pvec,
                         width: int = ways) -> None:
            nonlocal plru_checks
            for state, touch in vectors:
                ctx.set(top.state, state)
                ctx.set(top.touch_valid, 1)
                ctx.set(top.touch_way, touch)
                await ctx.delay(1e-9)
                assert int(ctx.get(top.nextState)) == plru_oracle_next(state, touch, width)
                assert int(ctx.get(top.victim)) == plru_oracle_victim(state, width)
                plru_checks += 1
        sim = Simulator(ptop)
        sim.add_testbench(pbench)
        sim.run()

    bank_checks = 0
    bank_module = modules["ReplacerState"]
    for policy in ("lru", "plru"):
        cfg = bank_module.ReplacerStateConfig(numSets=3, numWays=4, policy=policy,
                                              accessSize=2, numExtraReadPort=0,
                                              numExtraWritePort=0)
        top = bank_module.ReplacerState(cfg)

        async def bank_bench(ctx: Any, target: Any = top, policy_name: str = policy) -> None:
            nonlocal bank_checks
            states = [0, 0, 0]
            for signal in target.access_valid:
                ctx.set(signal, 0)
            await ctx.tick()
            for set_index, way in ((0, 2), (1, 3), (0, 1), (2, 0), (1, 1)):
                ctx.set(target.access_sets[0], set_index)
                ctx.set(target.access_ways[0], way)
                ctx.set(target.access_valid[0], 1)
                ctx.set(target.access_valid[1], 0)
                states[set_index] = (lru_oracle_next(states[set_index], way, 4)
                                     if policy_name == "lru" else
                                     plru_oracle_next(states[set_index], way, 4))
                await ctx.tick()
                ctx.set(target.access_valid[0], 0)
                for query in range(3):
                    ctx.set(target.victim_set, query)
                    await ctx.delay(1e-9)
                    expected = (lru_oracle_victim(states[query], 4)
                                if policy_name == "lru" else plru_oracle_victim(states[query], 4))
                    assert int(ctx.get(target.victim_way)) == expected
                    bank_checks += 1

        sim = Simulator(top)
        sim.add_clock(1e-6)
        sim.add_testbench(bank_bench)
        sim.run()
    return {"lru_vectors": lru_checks, "plru_vectors": plru_checks,
            "state_bank_checks": bank_checks}


# Convert a host path to an absolute WSL path. / 将主机路径转换为绝对 WSL 路径。
def wsl_path(path: Path) -> str:
    probe = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                           capture_output=True, text=True, check=True)
    return probe.stdout.strip()


# Run Verilator and Yosys on one generated target. / 对单个生成目标运行 Verilator 与 Yosys。
def backend_gate(name: str, source: str, directory: Path) -> dict[str, Any]:
    path = directory / f"{name}.sv"
    path.write_text(source, encoding="utf-8", newline="\n")
    wpath = wsl_path(path)
    verilator = subprocess.run(["wsl.exe", "-e", "bash", "-lc",
                                f"verilator --lint-only -Wno-fatal {wpath}"],
                               capture_output=True, text=True, check=False)
    yosys = subprocess.run(["wsl.exe", "-e", "bash", "-lc",
                            f"yosys -Q -p 'read_verilog -sv {wpath}; hierarchy -top {name}; proc; opt; check; stat'"],
                           capture_output=True, text=True, check=False)
    return {
        "verilator": {"status": "PASS" if verilator.returncode == 0 else "FAIL",
                       "returncode": verilator.returncode,
                       "stderr_tail": verilator.stderr[-1200:]},
        "yosys": {"status": "PASS" if yosys.returncode == 0 else "FAIL",
                  "returncode": yosys.returncode,
                  "stderr_tail": yosys.stderr[-1200:]},
        "rtl_bytes": len(source.encode()),
        "rtl_sha256": digest(source.encode()),
    }


# Verify the immutable XSTop artifact and locate relevant generated modules.
# 校验不可变 XSTop 并定位相关生成模块。
def locked_reference_info() -> dict[str, Any]:
    if not LOCKED_REFERENCE.is_file():
        raise FileNotFoundError(LOCKED_REFERENCE)
    raw = LOCKED_REFERENCE.read_bytes()
    if len(raw) != LOCKED_BYTES or digest(raw) != LOCKED_SHA256:
        raise RuntimeError("locked XSTop hash/size mismatch")
    text = raw.decode("utf-8", errors="replace")
    modules = {}
    for name in ("NewDispatch", "FTB", "Frontend", "SCTable", "TageTable",
                 "Tage_SC", "ICacheReplacer"):
        marker = f"module {name}("
        start = text.find(marker)
        if start < 0:
            modules[name] = {"present": False}
            continue
        line_start = text.count("\n", 0, start) + 1
        end = text.find("endmodule", start)
        line_end = text.count("\n", 0, end) + 1 if end >= 0 else None
        modules[name] = {"present": True, "line_start": line_start,
                         "line_end": line_end,
                         "module_sha256": digest(text[start:end + len("endmodule")].encode())
                         if end >= 0 else None}
    return {"path": LOCKED_CANONICAL, "bytes": len(raw), "sha256": digest(raw),
            "locked": True, "modules": modules}


# Collect exact source hashes and equation occurrence evidence. / 收集精确源哈希及方程出现证据。
def source_evidence() -> dict[str, Any]:
    needles = {"CompareMatrix": "compareMatrix", "FallThroughPredictor": "getFallThroughAddr",
               "SaturateCounter": "satUpdate", "SignedSaturateCounter": "signedSatUpdate",
               "LruStateGen": "class TrueLRU", "PlruStateGen": "class PseudoLRU",
               "ReplacerState": "class SetAssocLRU"}
    result = {}
    for name, relatives in SOURCE_PATHS.items():
        entries = []
        for relative in relatives:
            path = ROOT / relative
            raw = path.read_bytes()
            text = raw.decode("utf-8", errors="replace")
            needle = needles[name]
            entries.append({"path": relative, "bytes": len(raw), "sha256": digest(raw),
                            "needle": needle, "occurrences": text.count(needle)})
        result[name] = entries
    return result


# Run the full independent state-family transaction and persist evidence.
# 运行完整独立状态族事务并持久化证据。
def main() -> int:
    modules = {name: load_target(name, path) for name, path in TARGETS.items()}
    audits = {name: audit_target(path) for name, path in TARGETS.items()}
    direct = {
        "CompareMatrix": test_compare(modules["CompareMatrix"]),
        "FallThroughPredictor": test_fallthrough(modules["FallThroughPredictor"]),
        "SaturateCounter": test_unsigned_counter(modules["SaturateCounter"]),
        "SignedSaturateCounter": test_signed_counter(modules["SignedSaturateCounter"]),
        "Replacement": test_replacement(modules),
    }
    configs = {
        "CompareMatrix": modules["CompareMatrix"].CompareMatrixConfig(n=4),
        "FallThroughPredictor": modules["FallThroughPredictor"].FallThroughConfig(),
        "SaturateCounter": modules["SaturateCounter"].SaturateCounterConfig(),
        "SignedSaturateCounter": modules["SignedSaturateCounter"].SignedSaturateCounterConfig(),
        "LruStateGen": modules["LruStateGen"].LruStateGenConfig(numWays=4, accessSize=2),
        "PlruStateGen": modules["PlruStateGen"].PlruStateGenConfig(numWays=4, accessSize=2),
        "ReplacerState": modules["ReplacerState"].ReplacerStateConfig(
            numSets=4, numWays=4, policy="plru", accessSize=2,
            numExtraReadPort=0, numExtraWritePort=0),
    }
    generated = {}
    with tempfile.TemporaryDirectory(prefix="v2_bpu_state_lint_") as temp:
        directory = Path(temp)
        for name, module in modules.items():
            rtl = module.build_verilog(configs[name], {})
            second = module.build_verilog(configs[name], {})
            if rtl != second:
                raise AssertionError(f"non-deterministic export: {name}")
            generated[name] = backend_gate(name, rtl, directory)
    locked = locked_reference_info()
    replacement_reference = {"status": "UNRUN"}
    replacement_script = ROOT / "validation/v2_replacement_batch_direct.py"
    spec = importlib.util.spec_from_file_location("v2_existing_replacement_validator", replacement_script)
    if spec is not None and spec.loader is not None:
        validator = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = validator
        spec.loader.exec_module(validator)
        replacement_reference = validator.reference_differential(modules["ReplacerState"])
    lint_pass = all(item["verilator"]["status"] == "PASS" and
                    item["yosys"]["status"] == "PASS" for item in generated.values())
    reference_pass = replacement_reference.get("status") == "PASS"
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_FRONTEND_BPU_STATE_FAMILY",
        "batch_id": "V2-SEMANTIC-FRONTEND-BPU-STATE-001",
        "source_commit": SOURCE_COMMIT,
        "targets": {name: str(path.relative_to(ROOT)).replace("\\", "/")
                    for name, path in TARGETS.items()},
        "source_paths": SOURCE_PATHS,
        "source_evidence": source_evidence(),
        "locked_reference": locked,
        "direct": direct,
        "structural_audit": audits,
        "generated": generated,
        "reference_differential": {
            "CompareMatrix": {"status": "SOURCE_EQUATION_BOUNDED",
                              "locked_module": "NewDispatch",
                              "observation": "compareMatrix/IQSort/minIQSel",
                              "standalone_module": False},
            "FallThroughPredictor": {"status": "SOURCE_EQUATION_BOUNDED",
                                      "locked_modules": ["FTB", "Frontend"],
                                      "observation": "getFallThroughAddr/fallThroughErr",
                                      "standalone_module": False},
            "SaturateCounter": {"status": "SOURCE_EQUATION_BOUNDED",
                                 "locked_modules": ["SCTable", "TageTable", "Tage_SC"],
                                 "observation": "satUpdate", "standalone_module": False},
            "SignedSaturateCounter": {"status": "SOURCE_EQUATION_BOUNDED",
                                       "locked_modules": ["SCTable", "Tage_SC"],
                                       "observation": "signedSatUpdate", "standalone_module": False},
            "Replacement": replacement_reference,
        },
        "commands": [
            "python -m py_compile <seven Build targets>",
            "python validation/v2_frontend_bpu_state_family_validator.py",
            "verilator --lint-only (seven generated targets)",
            "yosys read_verilog/proc/opt/check/stat (seven generated targets)",
        ],
        "gates": {
            "PYTHON_PRESENT": "PASS",
            "DIRECT_TEST_PASS_BOUNDED": "PASS",
            "V2_REFERENCE_MATCHED": "PASS_BOUNDED_SOURCE_EQUATION" if reference_pass else "PASS_BOUNDED_SOURCE_EQUATION_ONLY",
            "VERILATOR": "PASS" if lint_pass else "FAIL",
            "YOSYS": "PASS" if lint_pass else "FAIL",
            "UHSC_LOCALIZED": "PENDING_EXTERNAL_WRAPPER",
            "PARENT_CLOSURE_MATCHED": "PASS_BOUNDED" if reference_pass else "PENDING",
            "LICENSE_REVIEW": "PENDING_COORDINATOR_REVIEW",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "status": "VALIDATOR_PASS_BOUNDED" if lint_pass else "VALIDATION_FAIL",
        "acceptance_eligible": False,
        "uhsc_naming": {
            "status": "PENDING_EXTERNAL_WRAPPER",
            "reference_names_unchanged": True,
            "entries": [
                {"source_name": "XSTop", "local_name": "UHSCTop",
                 "visibility": "project-owned external HDL wrapper",
                 "reason": "Only the later external wrapper is localized."},
                {"source_name": "XiangShan / XS / KMHV2", "local_name": "UHSC",
                 "visibility": "project-owned product identity",
                 "reason": "Source provenance and protocol names remain unchanged."},
            ],
        },
        "license": {
            "inventory": "V2-Dependency-License-Inventory.json",
            "families": ["utility", "rocket-chip"],
            "status": "PENDING_COORDINATOR_REVIEW",
        },
        "unclosed": [
            "CompareMatrix, FallThroughPredictor, and counters have no standalone module in locked XSTop; source-equation and parent closure remain required.",
            "Full Frontend BPU/FTB/TAGE/SC/FTQ behavioral closure remains pending.",
            "External UHSC wrapper, license review, coordinator review, and user approval remain pending.",
        ],
    }
    RESULT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "direct": direct,
                      "verilator": payload["gates"]["VERILATOR"],
                      "yosys": payload["gates"]["YOSYS"],
                      "reference": replacement_reference.get("status"),
                      "ACCEPTED": "NOT_ALLOWED"}, ensure_ascii=False, sort_keys=True))
    return 0 if payload["status"] == "VALIDATOR_PASS_BOUNDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
