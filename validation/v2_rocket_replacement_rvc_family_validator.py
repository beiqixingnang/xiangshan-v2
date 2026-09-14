"""Independent V2 Rocket replacement/RVC family validator. / 独立 V2 Rocket 替换与 RVC family 验证器。"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import random
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUILD_CORE = ROOT / "python" / "Program-System" / "System-Build" / "Build-Cpu" / "Cpu-Core"
REFERENCE = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
REFERENCE_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
REFERENCE_BYTES = 228590583
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
ROCKET_REPLACEMENT_SHA256 = "811d0fa0fff97d66edc513b4385a5ee821859594282c95f972f5f4b483fac373"
ROCKET_RVC_SHA256 = "76b2a895ee9d29a1d65d5e14be267c6ebbc8c9c4d315acc9d0665e9944503db8"
UTILITY_REPLACEMENT_SHA256 = "ec8dcaab0a5bf90b9bb86452f4d4f9290dc29761ee6d0d38f6855937d27ea296"

REPLACEMENT_TARGETS = {
    "LruStateGen": BUILD_CORE / "Build-Cpu.Frontend.Bpu.Replacer.LruStateGen-Hardware.py",
    "PlruStateGen": BUILD_CORE / "Build-Cpu.Frontend.Bpu.Replacer.PlruStateGen-Hardware.py",
    "ReplacerState": BUILD_CORE / "Build-Cpu.Frontend.Bpu.Replacer.ReplacerState-Hardware.py",
}
RVC_TARGET = BUILD_CORE / "Build-Cpu.Frontend.Ifu.RvcExpander-Hardware.py"


# Load one exact-path target without modifying the target module. / 按精确路径加载目标且不修改目标模块。
def load_target(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load target: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Hash one local source file for the frozen V2 provenance record. / 计算冻结 V2 来源文件哈希。
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


# Audit the five-zone, bilingual, and import contract independently. / 独立审计五区、双语和导入契约。
def audit_target(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise AssertionError(f"UTF-8 BOM present: {path}")
    if b"\r\n" in raw:
        raise AssertionError(f"CRLF present: {path}")
    source = raw.decode("utf-8")
    tree = ast.parse(source, filename=str(path))
    docstring = ast.get_docstring(tree) or ""
    if not any("\u4e00" <= char <= "\u9fff" for char in docstring):
        raise AssertionError(f"module docstring is not bilingual: {path}")
    zones = ("Module Contract", "Configuration", "Implementation",
             "Public Adapter", "Direct Entry")
    positions = [source.find(zone) for zone in zones]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise AssertionError(f"five-zone contract missing: {path}")
    if "__all__" not in source:
        raise AssertionError(f"explicit __all__ missing: {path}")
    forbidden = {"importlib", "runpy", "subprocess", "socket", "urllib", "pathlib"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.split(".")[0] in forbidden for alias in node.names):
                raise AssertionError(f"forbidden import: {path}")
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in forbidden:
                raise AssertionError(f"forbidden import: {path}")
    lines = source.splitlines()
    functions: list[str] = []
    build_signatures: list[list[str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
            if node.name.startswith("_") and not (node.name.startswith("__") and node.name.endswith("__")):
                raise AssertionError(f"leading underscore helper: {path}:{node.lineno}")
            prior = lines[node.lineno - 2].strip() if node.lineno >= 2 else ""
            if not prior.startswith("#") or "/" not in prior:
                raise AssertionError(f"missing bilingual responsibility comment: {path}:{node.lineno}")
            if node.name == "build_verilog":
                build_signatures.append([argument.arg for argument in node.args.args])
    if build_signatures != [["configuration", "injected_dependencies"]]:
        raise AssertionError(f"build_verilog signature mismatch: {path}")
    return {
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "utf8_lf": True,
        "bilingual_docstring": True,
        "zones": list(zones),
        "functions": sorted(functions),
        "build_verilog_signature": build_signatures[0],
        "forbidden_imports": [],
    }


# Return the independent packed triangular offset used by Rocket TrueLRU. / 返回 Rocket TrueLRU 的独立三角矩阵偏移。
def oracle_pair_offset(lower: int, upper: int, ways: int) -> int:
    return sum(ways - row - 1 for row in range(lower)) + upper - lower - 1


# Compute an independent TrueLRU state transition. / 独立计算 TrueLRU 状态转移。
def oracle_lru_next(state: int, touch: int, ways: int) -> int:
    if ways <= 1:
        return 0
    width = ways * (ways - 1) // 2
    state &= (1 << width) - 1
    if not 0 <= touch < ways:
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


# Compute an independent least-recently-used victim. / 独立计算最久未使用路。
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


# Compute an independent unbalanced tree-PLRU transition. / 独立计算非平衡树 PLRU 状态转移。
def oracle_plru_next(state: int, touch: int, ways: int) -> int:
    if ways <= 1:
        return 0

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


# Compute an independent unbalanced tree-PLRU victim. / 独立计算非平衡树 PLRU 受害路。
def oracle_plru_victim(state: int, ways: int) -> int:
    if ways <= 1:
        return 0

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


# Exhaustively compare the exported pure Rocket policy equations. / 穷举比较导出的 Rocket 策略纯方程。
def exhaustive_policy_checks(lru: Any, plru: Any) -> dict[str, int]:
    lru_transition_checks = 0
    lru_victim_checks = 0
    for ways in range(1, 7):
        width = ways * (ways - 1) // 2
        for state in range(1 << width):
            for touch in range(ways + 1):
                expected = oracle_lru_next(state, touch, ways)
                actual = lru.lru_next_state(state, touch, ways)
                if actual != expected:
                    raise AssertionError(f"LRU transition mismatch ways={ways} state={state} touch={touch}")
                lru_transition_checks += 1
            expected_victim = oracle_lru_victim(state, ways)
            actual_victim = lru.lru_victim(state, ways)
            if actual_victim != expected_victim:
                raise AssertionError(f"LRU victim mismatch ways={ways} state={state}")
            lru_victim_checks += 1
    plru_transition_checks = 0
    plru_victim_checks = 0
    for ways in range(1, 9):
        width = max(0, ways - 1)
        for state in range(1 << width):
            for touch in range(ways + 1):
                expected = oracle_plru_next(state, touch, ways)
                actual = plru.plru_next_state(state, touch, ways)
                if actual != expected:
                    raise AssertionError(f"PLRU transition mismatch ways={ways} state={state} touch={touch}")
                plru_transition_checks += 1
            expected_victim = oracle_plru_victim(state, ways)
            actual_victim = plru.plru_victim(state, ways)
            if actual_victim != expected_victim:
                raise AssertionError(f"PLRU victim mismatch ways={ways} state={state}")
            plru_victim_checks += 1
    return {
        "lru_transition_checks": lru_transition_checks,
        "lru_victim_checks": lru_victim_checks,
        "plru_transition_checks": plru_transition_checks,
        "plru_victim_checks": plru_victim_checks,
    }


# Exhaustively exercise the pure RVC decoder for both floating-state modes. / 穷举两个浮点状态模式下的纯 RVC 解码器。
def exhaustive_rvc_checks(module: Any) -> dict[str, int]:
    checks = 0
    cfg = module.RvcExpanderConfig()
    for fs_is_off in (False, True):
        for value in range(1 << 16):
            bits, rd, rs1, rs2, rs3, illegal = module.decode_rvc(value, fs_is_off, cfg)
            if not 0 <= bits < (1 << 32):
                raise AssertionError(f"RVC bits width mismatch value={value}")
            if any(not 0 <= register < 32 for register in (rd, rs1, rs2, rs3)):
                raise AssertionError(f"RVC register width mismatch value={value}")
            if not isinstance(illegal, bool):
                raise AssertionError(f"RVC illegal flag type mismatch value={value}")
            checks += 1
    return {"vectors": checks, "fs_modes": 2, "encodings_per_mode": 65536}


# Convert a host path into a WSL path. / 将主机路径转换为 WSL 路径。
def wsl_path(path: Path) -> str:
    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                            capture_output=True, encoding="utf-8", errors="replace", check=True)
    return result.stdout.strip()


# Run one command in WSL with reproducible UTF-8 capture. / 在 WSL 中运行命令并稳定捕获 UTF-8 输出。
def run_wsl(command: str) -> dict[str, Any]:
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", command],
                            capture_output=True, encoding="utf-8", errors="replace", check=False)
    return {
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-2000:],
        "stderr_tail": result.stderr[-4000:],
        "stdout_sha256": hashlib.sha256(result.stdout.encode("utf-8")).hexdigest(),
        "stderr_sha256": hashlib.sha256(result.stderr.encode("utf-8")).hexdigest(),
    }


# Run Verilator and Yosys against freshly generated target RTL. / 对新生成的目标 RTL 运行 Verilator 与 Yosys。
def synthesize(name: str, rtl: str, directory: Path) -> dict[str, Any]:
    path = directory / f"{name}.sv"
    path.write_text(rtl, encoding="utf-8", newline="\n")
    converted = shlex.quote(wsl_path(path))
    verilator = run_wsl(f"verilator --lint-only -Wno-fatal {converted}")
    yosys = run_wsl(
        f"yosys -Q -p 'read_verilog -sv {converted}; hierarchy -top {shlex.quote(name)}; proc; opt; stat'"
    )
    return {"verilator": verilator, "yosys": yosys,
            "rtl_bytes": len(rtl.encode("utf-8")),
            "rtl_sha256": hashlib.sha256(rtl.encode("utf-8")).hexdigest()}


# Extract one locked module from XSTop without editing the artifact. / 从锁定 XSTop 提取模块且不编辑参考产物。
def extract_reference(name: str) -> str:
    # The quoted awk expression keeps the literal opening parenthesis in the module name.
    expression = f"awk '/^module {name}\\(/,/^endmodule/' {shlex.quote(REFERENCE)}"
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", expression],
                            capture_output=True, encoding="utf-8", errors="replace", check=True)
    if not result.stdout.startswith(f"module {name}("):
        raise RuntimeError(f"reference module not found: {name}")
    return result.stdout


# Rename a generated module declaration only at the wrapper boundary. / 仅在包装器边界重命名生成模块声明。
def rename_module(rtl: str, old: str, new: str) -> str:
    marker = f"module {old}("
    if marker not in rtl:
        raise RuntimeError(f"generated module not found: {old}")
    return rtl.replace(marker, f"module {new}(", 1)


# Compare all 16-bit RVC encodings with the locked generated reference. / 将全部 16 位 RVC 编码与锁定生成参考比较。
def rvc_reference_differential(module: Any, directory: Path) -> dict[str, Any]:
    from amaranth.back import verilog

    directory.mkdir(parents=True, exist_ok=True)
    top = module.RvcExpander(module.RvcExpanderConfig())
    target = verilog.convert(
        top,
        name="UHSC_RVCExpander",
        ports=[top.in_, top.fsIsOff, top.out_bits, top.out_rd, top.out_rs1,
               top.out_rs2, top.out_rs3, top.ill],
        emit_src=False,
    )
    reference = extract_reference("RVCExpander")
    wrapper = """
module tb;
  logic [31:0] in_word;
  logic fs;
  wire [31:0] ref_bits;
  wire ref_ill;
  wire [31:0] dut_bits;
  wire [4:0] dut_rd, dut_rs1, dut_rs2, dut_rs3;
  wire dut_ill;
  RVCExpander ref_inst(.io_in(in_word), .io_fsIsOff(fs),
                       .io_out_bits(ref_bits), .io_ill(ref_ill));
  UHSC_RVCExpander dut_inst(.io_in(in_word), .io_fsIsOff(fs),
                            .io_out_bits(dut_bits), .io_out_rd(dut_rd),
                            .io_out_rs1(dut_rs1), .io_out_rs2(dut_rs2),
                            .io_out_rs3(dut_rs3), .io_ill(dut_ill));
  integer i;
  initial begin
    fs = 1'b0;
    for (i = 0; i < 65536; i = i + 1) begin
      in_word = i[31:0]; #1;
      if (ref_bits !== dut_bits || ref_ill !== dut_ill)
        $fatal(1, "rvc fs0 mismatch %0d ref=%h/%b dut=%h/%b", i, ref_bits, ref_ill, dut_bits, dut_ill);
    end
    fs = 1'b1;
    for (i = 0; i < 65536; i = i + 1) begin
      in_word = i[31:0]; #1;
      if (ref_bits !== dut_bits || ref_ill !== dut_ill)
        $fatal(1, "rvc fs1 mismatch %0d ref=%h/%b dut=%h/%b", i, ref_bits, ref_ill, dut_bits, dut_ill);
    end
    $display("RVC_EXHAUSTIVE_PASS %0d", i);
    $finish;
  end
endmodule
"""
    target = rename_module(target, "UHSC_RVCExpander", "UHSC_RVCExpander")
    source = reference + "\n" + target + "\n" + wrapper
    path = directory / "rvc_tb.sv"
    path.write_text(source, encoding="utf-8", newline="\n")
    converted = shlex.quote(wsl_path(path))
    compile_result = run_wsl(
        f"cd $(dirname {converted}) && verilator --binary --timing -Wno-fatal --top-module tb rvc_tb.sv"
    )
    if compile_result["status"] != "PASS":
        return {"status": "FAIL_COMPILE", "reference_module": "RVCExpander", "compile": compile_result}
    binary = path.parent / "obj_dir" / "Vtb"
    run_result = run_wsl(shlex.quote(wsl_path(binary)))
    return {
        "status": "PASS" if run_result["status"] == "PASS" else "FAIL_RUN",
        "reference_module": "RVCExpander",
        "vectors": 131072,
        "compile": compile_result,
        "run": run_result,
        "reference_sha256": hashlib.sha256(reference.encode("utf-8")).hexdigest(),
        "reference_bytes": len(reference.encode("utf-8")),
    }


# Build the explicit ICacheReplacer parent around the target state bank. / 为目标状态组构造显式 ICacheReplacer 父闭包。
def replacement_parent_wrapper(target: str, reference: str, checks: list[tuple[int, int, int, int, int, int, int, int, int]]) -> str:
    instance = """
      .clk(clock), .rst(reset),
      .io_access_0_set(hit_set_0), .io_access_0_valid(hit_valid_0), .io_access_0_way(hit_way_0),
      .io_access_1_set(victim_set), .io_access_1_valid(victim_valid_0), .io_access_1_way(victim_way_reg),
      .io_victim_set(io_victim_vSetIdx_bits[7:1]), .io_victim_way(policy_way_0),
      .io_state_read(), .io_state_next(),
      .io_read_0_setIdx(7'b0), .io_read_1_setIdx(7'b0),
      .io_write_0_valid(1'b0), .io_write_1_valid(1'b0),
      .io_write_0_bits_setIdx(7'b0), .io_write_1_bits_setIdx(7'b0),
      .io_write_0_bits_state(3'b0), .io_write_1_bits_state(3'b0),
      .io_read_0_state(), .io_read_1_state()
    """
    # The second bank receives the odd virtual-set half. / 第二状态组接收奇数虚拟组半区。
    instance_1 = instance.replace("hit_set_0", "hit_set_1").replace("hit_valid_0", "hit_valid_1").replace("hit_way_0", "hit_way_1").replace("victim_valid_0", "victim_valid_1").replace("policy_way_0", "policy_way_1")
    lines: list[str] = []
    for index, values in enumerate(checks):
        t0_valid, t1_valid, victim_valid, t0_set, t1_set, victim_set, t0_way, t1_way, _ = values
        lines.append(
            f"    io_touch_0_valid = 1'b{t0_valid}; io_touch_1_valid = 1'b{t1_valid}; "
            f"io_victim_vSetIdx_valid = 1'b{victim_valid}; "
            f"io_touch_0_bits_vSetIdx = 8'd{t0_set}; io_touch_1_bits_vSetIdx = 8'd{t1_set}; "
            f"io_victim_vSetIdx_bits = 8'd{victim_set}; io_touch_0_bits_way = 2'd{t0_way}; "
            f"io_touch_1_bits_way = 2'd{t1_way}; #2; "
            f"if (ref_way !== dut_way) $fatal(1, \"replacement differential cycle {index}\");"
        )
    return f"""
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
  ReplacerState dut0 ({instance});
  ReplacerState dut1 ({instance_1});
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
    .io_touch_0_valid(io_touch_0_valid), .io_touch_1_valid(io_touch_1_valid), .io_victim_vSetIdx_valid(io_victim_vSetIdx_valid),
    .io_touch_0_bits_vSetIdx(io_touch_0_bits_vSetIdx), .io_touch_1_bits_vSetIdx(io_touch_1_bits_vSetIdx), .io_victim_vSetIdx_bits(io_victim_vSetIdx_bits),
    .io_touch_0_bits_way(io_touch_0_bits_way), .io_touch_1_bits_way(io_touch_1_bits_way), .io_victim_way(dut_way));
  always #1 clock = ~clock;
  initial begin
    clock = 0; reset = 1; io_touch_0_valid = 0; io_touch_1_valid = 0; io_victim_vSetIdx_valid = 0;
    io_touch_0_bits_vSetIdx = 0; io_touch_1_bits_vSetIdx = 0; io_victim_vSetIdx_bits = 0;
    io_touch_0_bits_way = 0; io_touch_1_bits_way = 0;
    #4; reset = 0;
{chr(10).join(lines)}
    $display("REPLACEMENT_PARENT_PASS {len(checks)}");
    $finish;
  end
endmodule
"""


# Compare the two-bank target with the extracted V2 ICacheReplacer parent. / 比较双状态组目标与提取的 V2 ICacheReplacer 父闭包。
def replacement_reference_differential(module: Any, directory: Path) -> dict[str, Any]:
    from amaranth.back import verilog

    directory.mkdir(parents=True, exist_ok=True)
    config = module.ReplacerStateConfig(numSets=128, numWays=4, policy="plru",
                                        accessSize=2, numExtraReadPort=0,
                                        numExtraWritePort=0)
    top = module.ReplacerState(config)
    target = verilog.convert(
        top,
        name="ReplacerState",
        ports=[top.clock, top.reset, *top.access_sets, *top.access_valid,
               *top.access_ways, top.victim_set, top.victim_way, top.state_read,
               top.state_next, *top.read_setIdx, *top.read_state,
               *top.write_valid, *top.write_setIdx, *top.write_state],
        emit_src=False,
    )
    reference = extract_reference("ICacheReplacer")
    checks: list[tuple[int, int, int, int, int, int, int, int, int]] = []
    # Cover every virtual-set low bit, each way, both touch ports, and idle cycles.
    for index in range(256):
        checks.append((index & 1, (index >> 1) & 1, index & 1,
                       index, (index + 37) & 0xFF, (index * 3) & 0x7F,
                       index & 3, (index >> 2) & 3, index))
    rng = random.Random(0x525643)
    for _ in range(256):
        checks.append((rng.randrange(2), rng.randrange(2), rng.randrange(2),
                       rng.randrange(256), rng.randrange(256), rng.randrange(128),
                       rng.randrange(4), rng.randrange(4), 0))
    source = replacement_parent_wrapper(target, reference, checks)
    path = directory / "replacement_tb.sv"
    path.write_text(source, encoding="utf-8", newline="\n")
    converted = shlex.quote(wsl_path(path))
    compile_result = run_wsl(
        f"cd $(dirname {converted}) && verilator --binary --timing -Wno-fatal --top-module tb replacement_tb.sv"
    )
    if compile_result["status"] != "PASS":
        return {"status": "FAIL_COMPILE", "reference_module": "ICacheReplacer",
                "vectors": len(checks), "compile": compile_result}
    binary = path.parent / "obj_dir" / "Vtb"
    run_result = run_wsl(shlex.quote(wsl_path(binary)))
    return {
        "status": "PASS" if run_result["status"] == "PASS" else "FAIL_RUN",
        "reference_module": "ICacheReplacer",
        "vectors": len(checks),
        "compile": compile_result,
        "run": run_result,
        "reference_sha256": hashlib.sha256(reference.encode("utf-8")).hexdigest(),
        "reference_bytes": len(reference.encode("utf-8")),
        "coverage": ["reset", "victim selection", "touch/update", "all 128 virtual sets", "way values 0..3"],
    }


# Verify the frozen reference artifact identity through WSL. / 通过 WSL 校验冻结参考产物身份。
def reference_info() -> dict[str, Any]:
    result = run_wsl(f"sha256sum {shlex.quote(REFERENCE)}; wc -c < {shlex.quote(REFERENCE)}")
    lines = result["stdout_tail"].strip().splitlines()
    digest = lines[0].split()[0] if lines else ""
    try:
        size = int(lines[1].strip())
    except (IndexError, ValueError):
        size = None
    result.update({"path": REFERENCE, "sha256": digest, "bytes": size,
                   "expected_sha256": REFERENCE_SHA256, "expected_bytes": REFERENCE_BYTES,
                   "identity_status": "PASS" if digest == REFERENCE_SHA256 and size == REFERENCE_BYTES else "MISMATCH"})
    return result


# Read the mixed-license inventory without promoting its pending review. / 读取混合许可证清单且不提升待审状态。
def license_evidence() -> dict[str, Any]:
    inventory = json.loads((ROOT / "V2-Dependency-License-Inventory.json").read_text(encoding="utf-8"))
    packages = {entry["package_id"]: entry for entry in inventory.get("packages", [])}
    rocket = packages.get("rocket-chip")
    if rocket is None:
        raise AssertionError("rocket-chip license inventory entry missing")
    return {
        "inventory": "V2-Dependency-License-Inventory.json",
        "packages": ["rocket-chip", "utility"],
        "rocket_chip": {
            "commit": rocket.get("commit"),
            "license_files": rocket.get("license_files", []),
            "observed_licenses": rocket.get("observed_licenses", []),
            "license_review_required": rocket.get("license_review_required"),
        },
        "status": "PENDING_COORDINATOR_REVIEW",
        "reason": "Rocket-Chip and utility sources have mixed/per-file notices; preserve notices before promotion.",
    }


# Run the complete non-overlapping family verification transaction. / 执行完整的不重叠 family 验证事务。
def main() -> int:
    replacement_modules = {name: load_target(f"rocket_family_{name}", path)
                           for name, path in REPLACEMENT_TARGETS.items()}
    rvc_module = load_target("rocket_family_rvc", RVC_TARGET)
    target_audits = {name: audit_target(path) for name, path in REPLACEMENT_TARGETS.items()}
    target_audits["RvcExpander"] = audit_target(RVC_TARGET)

    source_paths = {
        "rocket_replacement": ROOT / "upstream" / "rocket-chip" / "src" / "main" / "scala" / "util" / "Replacement.scala",
        "rocket_rvc": ROOT / "upstream" / "rocket-chip" / "src" / "main" / "scala" / "rocket" / "RVC.scala",
        "utility_replacement_support": ROOT / "upstream" / "utility" / "src" / "main" / "scala" / "utility" / "Replacement.scala",
    }
    expected_sources = {
        "rocket_replacement": ROCKET_REPLACEMENT_SHA256,
        "rocket_rvc": ROCKET_RVC_SHA256,
        "utility_replacement_support": UTILITY_REPLACEMENT_SHA256,
    }
    source_hashes: dict[str, Any] = {}
    for name, path in source_paths.items():
        digest = sha256_file(path)
        source_hashes[name] = {"path": str(path.relative_to(ROOT)).replace("\\", "/"),
                               "sha256": digest, "expected_sha256": expected_sources[name],
                               "status": "PASS" if digest == expected_sources[name] else "MISMATCH",
                               "bytes": path.stat().st_size}
        if digest != expected_sources[name]:
            raise AssertionError(f"source hash mismatch: {path}")

    policy_checks = exhaustive_policy_checks(replacement_modules["LruStateGen"],
                                             replacement_modules["PlruStateGen"])
    rvc_checks = exhaustive_rvc_checks(rvc_module)
    generated: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="v2_rocket_family_synth_") as temp_name:
        temp = Path(temp_name)
        for name, module in replacement_modules.items():
            if name == "ReplacerState":
                config = module.ReplacerStateConfig(numSets=128, numWays=4,
                                                    policy="plru", accessSize=2,
                                                    numExtraReadPort=0,
                                                    numExtraWritePort=0)
                rtl = module.build_verilog(config, {})
            else:
                rtl = module.build_verilog(None, {})
            generated[name] = synthesize(name, rtl, temp)
        rvc_rtl = rvc_module.build_verilog(None, {})
        generated["RvcExpander"] = synthesize("RVCExpander", rvc_rtl, temp)
        reference_differential = replacement_reference_differential(
            replacement_modules["ReplacerState"], temp / "replacement_reference")
        rvc_differential = rvc_reference_differential(rvc_module, temp / "rvc_reference")

    reference = reference_info()
    if reference.get("identity_status") != "PASS":
        raise AssertionError("locked XSTop identity mismatch")
    license_result = license_evidence()
    all_synth_pass = all(
        generated[name][tool]["status"] == "PASS"
        for name in generated for tool in ("verilator", "yosys")
    )
    all_reference_pass = (reference_differential.get("status") == "PASS" and
                          rvc_differential.get("status") == "PASS")
    result = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_ROCKET_REPLACEMENT_RVC_FAMILY",
        "batch_id": "V2-DEPENDENCY-ROCKET-REPLACEMENT-RVC-001",
        "source_commit": SOURCE_COMMIT,
        "dependency_commits": {
            "rocket-chip": "46f1efefa1ff431bffe3262e4830bc50316842f4",
            "utility": "2f0743f1f3ee1889049841926fa382cd0b32d8e2",
        },
        "aggregation": {
            "disposition": "SATISFIED_BY_CORE_FAMILY",
            "additional_build_files": 0,
            "reason": "Both dependency surfaces are already covered by final core Build-Cpu files; a duplicate aggregate would overlap the core closure.",
        },
        "source_hashes": source_hashes,
        "reference_artifact": reference,
        "targets": {
            "replacement": {
                "files": {name: str(path.relative_to(ROOT)).replace("\\", "/")
                          for name, path in REPLACEMENT_TARGETS.items()},
                "covered_children": ["ReplacementPolicy", "RandomReplacement", "TrueLRU", "PseudoLRU", "ValidPseudoLRU", "SeqRandom", "SeqPLRU", "SetAssocLRU"],
                "pure_exhaustive": policy_checks,
                "reference_differential": reference_differential,
            },
            "rvc": {
                "file": str(RVC_TARGET.relative_to(ROOT)).replace("\\", "/"),
                "covered_children": ["RVCDecoder", "RVCExpander"],
                "pure_exhaustive": rvc_checks,
                "reference_differential": rvc_differential,
            },
        },
        "contract_audit": target_audits,
        "generated": generated,
        "license": license_result,
        "naming": {
            "status": "PASS_BOUNDED_FAMILY_LOCAL_NAME",
            "map": [
                {"source_name": "XSTop", "local_name": "UHSCTop", "visibility": "project-owned external wrapper", "reason": "External boundary only; locked reference remains XSTop"},
                {"source_name": "XiangShan / XS / KMHV2", "local_name": "UHSC", "visibility": "project-owned product identity", "reason": "Internal Rocket protocol names remain unchanged"},
            ],
        },
        "commands": [
            "python validation/v2_rocket_replacement_rvc_family_validator.py",
            "verilator --binary --timing exhaustive RVCExpander differential",
            "verilator --binary --timing ICacheReplacer parent differential",
            "verilator --lint-only and yosys read_verilog/proc/opt/stat for four generated targets",
        ],
        "gates": {
            "PYTHON_PRESENT": "PASS",
            "DIRECT_TEST_PASS_BOUNDED": "PASS",
            "V2_REFERENCE_MATCHED": "PASS_BOUNDED" if all_reference_pass else "FAIL",
            "VERILATOR": "PASS" if all_synth_pass else "FAIL",
            "YOSYS": "PASS" if all_synth_pass else "FAIL",
            "UHSC_LOCALIZED": "PASS_BOUNDED_FAMILY_LOCAL_NAME",
            "PARENT_CLOSURE_MATCHED": "PASS_BOUNDED" if reference_differential.get("status") == "PASS" else "PENDING",
            "LICENSE_REVIEW": "PENDING_COORDINATOR_REVIEW",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "status": "VALIDATOR_PASS_BOUNDED" if all_reference_pass and all_synth_pass else "VALIDATOR_FAILED",
        "acceptance_eligible": False,
        "unclosed": [
            "Full UHSC top integration and user approval remain outside this family.",
            "Mixed Rocket-Chip/utility license review remains pending coordinator review.",
            "Parent differential is bounded to the extracted ICacheReplacer surface; full CPU closure remains pending.",
        ],
    }
    output = ROOT / "validation" / "v2-rocket-replacement-rvc-family-results.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "VALIDATOR_PASS_BOUNDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
