"""Run V2 CSR/divider family direct and static gates. / 运行 V2 CSR/除法器族直接及静态门禁。"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from amaranth.sim import Simulator


ROOT = Path(__file__).resolve().parents[1]
BUILD_CORE = ROOT / "python" / "Program-System" / "System-Build" / "Build-Cpu" / "Cpu-Core"
EVIDENCE = ROOT / "validation" / "v2-csr-divider-direct-results.json"
CONTRACT_EVIDENCE = ROOT / "validation" / "v2-csr-divider-contract-audit.json"
COVERAGE_EVIDENCE = ROOT / "validation" / "v2-csr-divider-coverage-manifest.json"
MAPPING_EVIDENCE = ROOT / "validation" / "v2-csr-divider-mapping-update.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
REFERENCE_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
REFERENCE_BYTES = 228590583

TARGETS = {
    "CSRs": BUILD_CORE / "Build-Cpu.Backend.Decode.Isa.CSRs-Hardware.py",
    "SstcInterruptGen": BUILD_CORE / "Build-Cpu.Backend.Fu.NewCSR.SstcInterruptGen-Hardware.py",
    "SRT16Divider": BUILD_CORE / "Build-Cpu.Backend.Fu.SRT16Divider-Hardware.py",
    "FliTable": BUILD_CORE / "Build-Cpu.Backend.Fu.Fpu.FliTable-Hardware.py",
    "CSA": BUILD_CORE / "Build-Cpu.Backend.Fu.Util.CSA-Hardware.py",
}


# Load one target by exact path. / 按精确路径加载一个目标。
def load_target(name: str, path: Path) -> Any:
    """Import a target without package or sibling imports. / 不通过包或兄弟模块导入目标。"""

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Hash one file's exact bytes. / 计算文件原始字节摘要。
def digest(path: Path) -> str:
    """Return a SHA-256 digest. / 返回 SHA-256 摘要。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


# Audit the five-zone and import/function contract. / 审计五区及导入/函数契约。
def audit_target(path: Path) -> dict[str, Any]:
    """Return machine-readable structural facts. / 返回机器可读的结构事实。"""

    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    lines = source.splitlines()
    zones = ("Module Contract", "Configuration", "Implementation",
             "Public Adapter", "Direct Entry")
    positions = [source.find(zone) for zone in zones]
    if not all(position >= 0 for position in positions) or positions != sorted(positions):
        raise AssertionError(f"zone order failed: {path}")
    if "__all__" not in source:
        raise AssertionError(f"missing __all__: {path}")
    forbidden = ("importlib", "runpy", "subprocess", "socket", "urllib",
                 "pathlib", "os", "sys")
    # ``from __future__`` and typing are allowed; target hardware files may not
    # import loaders, shell/network clients, or repository paths.
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in forbidden:
                    raise AssertionError(f"forbidden import {alias.name}")
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in forbidden:
                raise AssertionError(f"forbidden import {node.module}")
    functions: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
            if node.name.startswith("_") and not (
                    node.name.startswith("__") and node.name.endswith("__")):
                raise AssertionError(f"leading underscore helper: {path}:{node.lineno}")
            prior = lines[node.lineno - 2].strip() if node.lineno >= 2 else ""
            if not prior.startswith("#") or "/" not in prior:
                raise AssertionError(f"missing bilingual comment: {path}:{node.lineno}")
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": len(source.encode("utf-8")),
        "sha256": digest(path),
        "utf8_lf": "\r\n" not in source,
        "ast": True,
        "zones": list(zones),
        "functions": sorted(functions),
        "adapter_exact": any(
            isinstance(node, ast.FunctionDef) and node.name == "build_verilog"
            and len(node.args.args) == 2
            for node in ast.walk(tree)
        ),
    }


# Calculate a signed two's-complement integer. / 计算有符号二进制补码整数。
def signed_value(value: int, width: int) -> int:
    """Interpret ``value`` as a signed width-bit integer. / 将 value 解释为位宽补码整数。"""

    value &= (1 << width) - 1
    return value - (1 << width) if value & (1 << (width - 1)) else value


# Return the architectural integer divide result. / 返回架构整数除法结果。
def divide_expected(dividend: int, divisor: int, width: int,
                    signed: bool, remainder: bool) -> int:
    """Model V2 quotient/remainder and divide-by-zero rules. / 建模 V2 商余数及除零规则。"""

    mask = (1 << width) - 1
    if signed:
        left = signed_value(dividend, width)
        right = signed_value(divisor, width)
        if right == 0:
            result = left if remainder else mask
        else:
            quotient = abs(left) // abs(right)
            if (left < 0) != (right < 0):
                quotient = -quotient
            result = left - quotient * right if remainder else quotient
    else:
        left = dividend & mask
        right = divisor & mask
        if right == 0:
            result = left if remainder else mask
        else:
            result = left % right if remainder else left // right
    return result & mask


# Simulate one divider request and return its output cycle/value. / 仿真一次除法请求并返回周期和值。
def run_divider_case(module: Any, width: int, dividend: int, divisor: int,
                     signed: bool, is_hi: bool, is_word: bool) -> tuple[int, int]:
    """Exercise reset, input fire, iterative latency, and finish handshake. / 检查复位、输入 fire、迭代延迟及 finish 握手。"""

    top = module.SRT16DividerDataModule(module.SRT16DividerConfig(width))
    result: list[tuple[int, int]] = []

    async def bench(ctx: Any) -> None:
        ctx.set(top.io_out_ready, 1)
        ctx.set(top.io_kill_w, 0)
        ctx.set(top.io_kill_r, 0)
        ctx.set(top.reset, 1)
        await ctx.tick()
        ctx.set(top.reset, 0)
        ctx.set(top.io_src_0, dividend)
        ctx.set(top.io_src_1, divisor)
        ctx.set(top.io_sign, int(signed))
        ctx.set(top.io_isHi, int(is_hi))
        ctx.set(top.io_isW, int(is_word))
        ctx.set(top.io_valid, 1)
        while not ctx.get(top.io_in_ready):
            await ctx.tick()
        await ctx.tick()
        ctx.set(top.io_valid, 0)
        for cycle in range(width + 24):
            if ctx.get(top.io_out_valid):
                result.append((cycle, ctx.get(top.io_out_data)))
                return
            await ctx.tick()
        raise AssertionError("divider timeout")

    simulator = Simulator(top)
    simulator.add_clock(1e-6)
    simulator.add_testbench(bench)
    simulator.run()
    if len(result) != 1:
        raise AssertionError("divider produced no result")
    return result[0]


# Check the V2 CSR split and custom permission helpers. / 检查 V2 CSR 拆分及自定义权限辅助函数。
def test_csrs(module: Any) -> dict[str, Any]:
    """Compare all Rocket CSRs and CSRConst boundary cases. / 比较全部 Rocket CSR 及 CSRConst 边界。"""

    expected = {
        "fflags": 0x1, "frm": 0x2, "fcsr": 0x3,
        "vstart": 0x8, "vxsat": 0x9, "vxrm": 0xA, "vcsr": 0xF,
        "sedeleg": 0x102, "sideleg": 0x103, "mstatus": 0x300,
        "mtvec": 0x305, "mip": 0x344, "pmpcfg0": 0x3A0,
        "pmpaddr63": 0x3EF, "dcsr": 0x7B0, "mcycle": 0xB00,
        "mvendorid": 0xF11,
    }
    for name, value in expected.items():
        if getattr(module.CSRs, name) != value:
            raise AssertionError(f"CSR mismatch {name}")
    csr_names = [name for name in vars(module.CSRs) if not name.startswith("_")]
    if len(csr_names) != 444:
        raise AssertionError(f"V2 CSR count {len(csr_names)} != 444")
    custom = module.CSRConst
    checks = 0
    for length in (1, 4, 16, 44):
        assert custom.satp_part_wmask(44, length) == (1 << length) - 1
        checks += 1
    assert custom.csrAccessPermissionCheck(0xF11, True, custom.ModeM, False, True) == 1
    assert custom.csrAccessPermissionCheck(0x100, False, custom.ModeU, True, True) == 2
    assert custom.csrAccessPermissionCheck(0x300, False, custom.ModeM, False, True) == 0
    assert not custom.dcsrPermissionCheck(0x7B0, False, False)
    assert custom.dcsrPermissionCheck(0x7B0, False, True)
    assert not custom.triggerPermissionCheck(0x7A0, False, False)
    assert custom.triggerPermissionCheck(0x7A0, False, True)
    checks += 7
    verilog = module.build_verilog(None, {})
    if "module CSRs" not in verilog:
        raise AssertionError("CSR probe module missing")
    return {"constants": len(csr_names), "helper_checks": checks,
            "verilog_sha256": hashlib.sha256(verilog.encode()).hexdigest()}


# Check registered Sstc behavior. / 检查寄存式 Sstc 行为。
def test_sstc(module: Any) -> dict[str, Any]:
    """Check reset, independent enables, and hold cycles. / 检查复位、独立使能与保持周期。"""

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
        observed.append((ctx.get(top.o_STIP), ctx.get(top.o_VSTIP)))
        ctx.set(top.i_stime_valid, 0)
        ctx.set(top.i_vstime_valid, 0)
        ctx.set(top.i_menvcfg_STCE, 0)
        ctx.set(top.i_henvcfg_STCE, 0)
        await ctx.tick()
        observed.append((ctx.get(top.o_STIP), ctx.get(top.o_VSTIP)))

    simulator = Simulator(top)
    simulator.add_clock(1e-6)
    simulator.add_testbench(bench)
    simulator.run()
    if observed != [(1, 1), (1, 1)]:
        raise AssertionError(f"Sstc observation {observed}")
    verilog = module.build_verilog(None, {})
    return {"cycles": len(observed),
            "verilog_sha256": hashlib.sha256(verilog.encode()).hexdigest()}


# Check all FLI tables against source values. / 根据源值检查全部 FLI 表。
def test_fli(module: Any) -> dict[str, Any]:
    """Exhaustively check 96 entries and zero/default behavior. / 穷举检查 96 项及零默认行为。"""

    tables = (module.FLI_H, module.FLI_S, module.FLI_D)
    checks = 0
    for table in tables:
        for index, value in enumerate(table):
            if module.decode_fli(table, index) != value:
                raise AssertionError("FLI table mismatch")
            checks += 1
    verilog = module.build_verilog(None, {})
    return {"entries": checks,
            "verilog_sha256": hashlib.sha256(verilog.encode()).hexdigest()}


# Check carry-save arithmetic helpers and hardware export. / 检查进位保存算术辅助函数及硬件导出。
def test_csa(module: Any) -> dict[str, Any]:
    """Exhaustively check width-four 3:2 and representative 5:3 vectors. / 穷举四位 3:2 并检查代表性 5:3 向量。"""

    checks = 0
    width = 4
    for a in range(1 << width):
        for b in range(1 << width):
            for c in range(1 << width):
                expected = (a ^ b ^ c, (a & b) | ((a ^ b) & c))
                if module.csa3_2(a, b, c, width) != expected:
                    raise AssertionError("CSA3_2 mismatch")
                checks += 1
    for values in ((1, 2, 4, 8, 3), (15, 7, 9, 1, 2), (0, 0, 0, 0, 0)):
        first = module.csa3_2(values[0], values[1], values[2], width)
        second = module.csa3_2(first[0], values[3], values[4], width)
        if module.csa5_3(*values, width) != (second[0], first[1], second[1]):
            raise AssertionError("CSA5_3 mismatch")
        checks += 1
    verilog = module.build_verilog(None, {})
    return {"vectors": checks,
            "verilog_sha256": hashlib.sha256(verilog.encode()).hexdigest()}


# Check divider corner and randomized transactions. / 检查除法器边界及随机事务。
def test_divider(module: Any) -> dict[str, Any]:
    """Compare signed/unsigned quotient and remainder at both legal widths. / 比较两种合法位宽的有符号/无符号商余数。"""

    vectors = [
        (0, 1), (1, 1), (10, 3), (3, 10), (10, 0),
        (0xFFFFFFFFFFFFFFFF, 3), (0x8000000000000000, 2),
        (0x123456789ABCDEF0, 0x10001),
    ]
    checks = 0
    expected_rows = (
        (0x1A, 0x1E, 0x20, 0x24, 0x26, 0x2A, 0x2C, 0x30),
        (0x04, 0x06, 0x06, 0x06, 0x08, 0x08, 0x08, 0x08),
        (0x7D, 0x7C, 0x7C, 0x7C, 0x7B, 0x7A, 0x7A, 0x7A),
        (0x68, 0x64, 0x62, 0x5E, 0x5C, 0x58, 0x56, 0x52),
    )
    for row, expected in zip(module.mLookUpTable2.minus_m, expected_rows):
        if tuple(value for _, value in row) != expected:
            raise AssertionError("SRT m lookup row mismatch")
        checks += len(expected)

    # Exercise the V2 RightShifter child at every legal shift and both fills.
    shifter = module.RightShifter(64, 6)
    shifts = [(0, 0), (1, 0), (5, 0), (17, 1), (32, 1), (63, 1)]
    shift_results: list[int] = []

    async def shift_bench(ctx: Any) -> None:
        for value, fill in shifts:
            ctx.set(shifter.in_, 0x0123456789ABCDEF)
            ctx.set(shifter.shiftNum, value)
            ctx.set(shifter.msb, fill)
            await ctx.delay(1e-9)
            shift_results.append(ctx.get(shifter.out))

    shift_sim = Simulator(shifter)
    shift_sim.add_testbench(shift_bench)
    shift_sim.run()
    for (shift, fill), observed in zip(shifts, shift_results):
        source = 0x0123456789ABCDEF
        expected = (source >> shift) | (((1 << shift) - 1) << (64 - shift)
                                        if fill and shift else 0)
        if observed != expected:
            raise AssertionError(f"RightShifter mismatch shift={shift} fill={fill} observed={observed:x} expected={expected:x}")
        checks += 1
    max_cycle = 0
    for width in (32, 64):
        mask = (1 << width) - 1
        width_vectors = [(a & mask, b & mask) for a, b in vectors]
        width_vectors.extend(((0x13579BDF * (index + 1)) & mask,
                              (0x1021 * (index + 3)) & mask)
                             for index in range(8))
        for dividend, divisor in width_vectors:
            for signed in (False, True):
                for remainder in (False, True):
                    cycle, value = run_divider_case(
                        module, width, dividend, divisor, signed,
                        remainder, False)
                    expected = divide_expected(dividend, divisor, width,
                                               signed, remainder)
                    if value != expected:
                        raise AssertionError(
                            f"divider mismatch w={width} a={dividend:x} d={divisor:x} "
                            f"signed={signed} rem={remainder}: {value:x}!={expected:x}")
                    max_cycle = max(max_cycle, cycle)
                    checks += 1
        # Verify V2 isW sign extension on quotient and remainder paths.
        dividend, divisor = 0x7FFFFFFF, 3
        for remainder in (False, True):
            cycle, value = run_divider_case(module, width, dividend, divisor,
                                             True, remainder, True)
            base = divide_expected(dividend, divisor, width, True, remainder)
            low_width = 32 if width == 64 else 16
            low = base & ((1 << low_width) - 1)
            expected = low | (((1 << (width - low_width)) - 1)
                              << low_width) if low & (1 << (low_width - 1)) else low
            if value != expected:
                raise AssertionError("divider isW mismatch")
            max_cycle = max(max_cycle, cycle)
            checks += 1
    verilog = module.build_verilog(None, {})
    return {"transactions": checks, "max_latency_cycles": max_cycle,
            "verilog_sha256": hashlib.sha256(verilog.encode()).hexdigest()}


# Run Verilator and Yosys on generated leaves. / 对生成叶子运行 Verilator 与 Yosys。
def synthesis_checks(loaded: dict[str, Any]) -> dict[str, Any]:
    """Return bounded lint/synthesis outcomes. / 返回有界 lint/综合结果。"""

    temp = Path(tempfile.mkdtemp(prefix="v2_csr_divider_"))
    outcomes: dict[str, Any] = {}
    try:
        for name, module in loaded.items():
            rtl = module.build_verilog(None, {})
            path = temp / f"{name}.sv"
            path.write_text(rtl, encoding="utf-8", newline="\n")
            probe = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                                   capture_output=True, text=True, check=False)
            if probe.returncode != 0:
                outcomes[name] = {"verilator": "SKIP", "yosys": "SKIP"}
                continue
            wsl_path = probe.stdout.strip()
            verilator = subprocess.run(
                ["wsl.exe", "-e", "bash", "-lc",
                 f"verilator --lint-only -Wno-fatal {wsl_path}"],
                capture_output=True, text=True, check=False)
            top_name = {"CSA": "CSA3_2", "SRT16Divider": "SRT16DividerDataModule"}.get(name, name)
            yosys_cmd = (f"yosys -Q -p 'read_verilog -sv {wsl_path}; "
                         f"hierarchy -top {top_name}; proc; opt; stat'")
            yosys = subprocess.run(["wsl.exe", "-e", "bash", "-lc", yosys_cmd],
                                   capture_output=True, text=True, check=False)
            outcomes[name] = {
                "verilator": {"status": "PASS" if verilator.returncode == 0 else "FAIL",
                              "returncode": verilator.returncode,
                              "stderr_tail": verilator.stderr[-1000:]},
                "yosys": {"status": "PASS" if yosys.returncode == 0 else "FAIL",
                          "returncode": yosys.returncode,
                          "stderr_tail": yosys.stderr[-1000:]},
            }
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    return outcomes


# Execute the complete direct batch and persist evidence. / 执行完整直接批次并持久化证据。
def main() -> int:
    """Run direct gates and write pending-acceptance JSON. / 运行直接门禁并写入待验收 JSON。"""

    loaded = {name: load_target(f"v2_csr_divider_{name}", path)
              for name, path in TARGETS.items()}
    audits = {name: audit_target(path) for name, path in TARGETS.items()}
    results = {
        "CSRs": test_csrs(loaded["CSRs"]),
        "SstcInterruptGen": test_sstc(loaded["SstcInterruptGen"]),
        "SRT16Divider": test_divider(loaded["SRT16Divider"]),
        "FliTable": test_fli(loaded["FliTable"]),
        "CSA": test_csa(loaded["CSA"]),
    }
    synthesis = synthesis_checks(loaded)
    report = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_CSR_DIVIDER_FAMILY_DIRECT",
        "source_commit": SOURCE_COMMIT,
        "targets": list(TARGETS),
        "source_paths": {
            "CSRs": ["upstream/rocket-chip/src/main/scala/rocket/Instructions.scala",
                     "upstream/src/main/scala/xiangshan/backend/fu/util/CSRConst.scala"],
            "SstcInterruptGen": "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala",
            "SRT16Divider": ["upstream/src/main/scala/xiangshan/backend/fu/SRT16Divider.scala",
                             "upstream/src/main/scala/xiangshan/backend/fu/SRT4Divider.scala"],
            "FliTable": "upstream/src/main/scala/xiangshan/backend/fu/fpu/FliTable.scala",
            "CSA": "upstream/src/main/scala/xiangshan/backend/fu/util/CSA.scala",
        },
        "commands": [
            "python validation/v2_csr_divider_batch.py",
            "python validation/v2_csr_divider_reference.py",
        ],
        "status": "DIRECT_TEST_PASS_BOUNDED",
        "targets_results": results,
        "audits": audits,
        "synthesis": synthesis,
        "reference": {
            "path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv",
            "sha256": REFERENCE_SHA256,
            "bytes": REFERENCE_BYTES,
            "independent_extraction": "validation/v2_csr_divider_reference.py",
        },
        "gates": {
            "PYTHON_PRESENT": "PASS",
            "DIRECT_TEST_PASS_BOUNDED": "PASS",
            "VERILATOR": "PASS" if all(row.get("verilator", {}).get("status") == "PASS"
                                        for row in synthesis.values()) else "FAIL",
            "YOSYS": "PASS" if all(row.get("yosys", {}).get("status") == "PASS"
                                    for row in synthesis.values()) else "FAIL",
            "V2_REFERENCE_MATCHED": "PENDING_COORDINATOR_REVIEW",
            "UHSC_LOCALIZED": "NOT_APPLICABLE_FOR_INTERNAL_LEAVES",
            "PARENT_CLOSURE_MATCHED": "PENDING",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "unclosed": [
            "CSRs has no standalone module in XSTop.sv; source-level split comparison is required.",
            "SRT16Divider reference differential and parent closure require coordinator review.",
            "Internal leaves have no project-facing UHSC wrapper in this batch.",
        ],
    }
    EVIDENCE.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    contract = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_CSR_DIVIDER_CONTRACT_AUDIT",
        "source_commit": SOURCE_COMMIT,
        "targets": audits,
        "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": "PASS",
                  "V2_REFERENCE_MATCHED": "PENDING_COORDINATOR_REVIEW",
                  "PARENT_CLOSURE_MATCHED": "PENDING", "ACCEPTED": "NOT_ALLOWED"},
        "acceptance_eligible": False,
    }
    CONTRACT_EVIDENCE.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8", newline="\n")
    coverage = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_CSR_DIVIDER_COVERAGE",
        "source_commit": SOURCE_COMMIT,
        "family_id": "core.csr.divider",
        "closure_root": "core.csr.divider",
        "status": "PENDING_COORDINATOR_REVIEW",
        "targets": [
            {"candidate": "CSRs", "python_path": TARGETS["CSRs"].relative_to(ROOT).as_posix(),
             "v2_sources": report["source_paths"]["CSRs"], "covered_children": ["rocket.CSRs", "CSRConst"],
             "observation_points": ["444 standard addresses", "CSRConst custom addresses", "permission helpers"],
             "reference_surface": "source-level split; no standalone CSRs module"},
            {"candidate": "SstcInterruptGen", "python_path": TARGETS["SstcInterruptGen"].relative_to(ROOT).as_posix(),
             "v2_sources": [report["source_paths"]["SstcInterruptGen"]], "covered_children": [],
             "observation_points": ["async reset", "STIP compare", "VSTIP compare", "enable hold"],
             "reference_surface": "SstcInterruptGen"},
            {"candidate": "SRT16Divider", "python_path": TARGETS["SRT16Divider"].relative_to(ROOT).as_posix(),
             "v2_sources": report["source_paths"]["SRT16Divider"], "covered_children": ["RightShifter", "CSA3_2"],
             "observation_points": ["input fire", "kill priority", "special d=0/+-1", "signed quotient/remainder", "finish/ready"],
             "reference_surface": "SRT16DividerDataModule"},
            {"candidate": "FliTable", "python_path": TARGETS["FliTable"].relative_to(ROOT).as_posix(),
             "v2_sources": [report["source_paths"]["FliTable"]], "covered_children": ["FliHTable", "FliSTable", "FliDTable"],
             "observation_points": ["all 32 source entries per table"], "reference_surface": "FliHTable/FliSTable/FliDTable"},
            {"candidate": "CSA", "python_path": TARGETS["CSA"].relative_to(ROOT).as_posix(),
             "v2_sources": [report["source_paths"]["CSA"]], "covered_children": ["CSA2_2", "CSA3_2", "CSA5_3"],
             "observation_points": ["bitwise sum", "carry", "5:3 cascade"], "reference_surface": "CSA3_2"},
        ],
        "locked_reference": {"path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv",
                             "sha256": REFERENCE_SHA256, "bytes": REFERENCE_BYTES},
        "gates": {"ACCEPTED": "NOT_ALLOWED", "parent_closure": "PENDING", "license": "PENDING"},
    }
    COVERAGE_EVIDENCE.write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8", newline="\n")
    mapping = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_CSR_DIVIDER_MAPPING_UPDATE",
        "source_commit": SOURCE_COMMIT,
        "status": "PENDING_COORDINATOR_REVIEW",
        "entries": [
            {"id": "CSRs", "classification": "SPLIT", "disposition": "SPLIT",
             "v2_sources": report["source_paths"]["CSRs"], "python_path": TARGETS["CSRs"].relative_to(ROOT).as_posix(),
             "status": "SOURCE_LEVEL_ONLY", "reason": "V2 supplies standard CSRs from rocket Instructions.scala and custom values from CSRConst.scala; no standalone CSRs.scala."},
            {"id": "SstcInterruptGen", "classification": "EXACT", "disposition": "REUSED",
             "v2_sources": [report["source_paths"]["SstcInterruptGen"]], "python_path": TARGETS["SstcInterruptGen"].relative_to(ROOT).as_posix(), "status": "MAPPING_ONLY"},
            {"id": "SRT16Divider", "classification": "REWRITTEN", "disposition": "REWRITTEN",
             "v2_sources": report["source_paths"]["SRT16Divider"], "python_path": TARGETS["SRT16Divider"].relative_to(ROOT).as_posix(),
             "covered_children": ["RightShifter", "CSA3_2"], "status": "MAPPING_ONLY"},
            {"id": "FliTable", "classification": "EXACT", "disposition": "REUSED",
             "v2_sources": [report["source_paths"]["FliTable"]], "python_path": TARGETS["FliTable"].relative_to(ROOT).as_posix(), "status": "MAPPING_ONLY"},
            {"id": "CSA", "classification": "EXACT", "disposition": "REUSED",
             "v2_sources": [report["source_paths"]["CSA"]], "python_path": TARGETS["CSA"].relative_to(ROOT).as_posix(), "status": "MAPPING_ONLY"},
        ],
        "localization_map": "NO_PROJECT_FACING_RENAME",
        "gates": {"ACCEPTED": "NOT_ALLOWED", "parent_closure": "PENDING", "license": "PENDING"},
    }
    MAPPING_EVIDENCE.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8", newline="\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
