"""Validate the reduced V2 VldMergeUnit parent closure.
验证 V2 精简 VldMergeUnit 父级闭包。

The runner is intentionally validation-only.  It loads the maintained vector
leaf targets by exact path, injects ``NewMgu`` into the parent harness, and
compares the resulting parent boundary with the corresponding modules sliced
from the immutable V2 XSTop snapshot.  A separate collision lane reuses the
existing RealWBCollideChecker reference closure to cover the named writeback
child boundary without pretending that the 861-port WbDataPath is complete.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from amaranth.sim import Simulator


# =============================================================================
# Module Contract
# =============================================================================
# This script records a reduced, executable parent closure rather than a full
# processor integration.  The authority is the V2 Scala source and locked
# generated XSTop; all promotion fields remain explicitly non-accepting.
# 本脚本记录可执行的精简父级闭包，而非整机集成。权威是 V2 Scala 源码及锁定
# 生成的 XSTop；所有晋级字段均明确保持不可接受状态。


# =============================================================================
# Configuration
# =============================================================================
ROOT = Path(__file__).resolve().parents[1]
REF_PATH = Path(r"\\wsl$\Debian\home\lishuo\xs-v2-local\build\rtl\XSTop.sv")
REFERENCE_CANONICAL = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
REFERENCE_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
REFERENCE_BYTES = 228590583
WORK = ROOT / "validation" / ".work" / "v2-vector-parent"
PARENT_TARGET = ROOT / "validation" / "v2_vector_parent_harness.py"
NEW_MGU_TARGET = ROOT / "python" / "ported" / "backend" / "fu" / "vector" / "NewMgu-Hardware.py"
WB_TARGET = ROOT / "python" / "ported" / "backend" / "datapath" / "WbArbiter-Hardware.py"
READINESS = ROOT / "validation" / "v2-parent-closure-readiness.json"
LEAF_DIRECT = ROOT / "validation" / "v2-vector-batch-direct-results.json"
LEAF_DIFF = ROOT / "validation" / "v2-vector-batch-differential-results.json"
DIRECT_RESULT = ROOT / "validation" / "v2-vector-parent-closure-direct-results.json"
DIFF_RESULT = ROOT / "validation" / "v2-vector-parent-closure-differential-results.json"
COVERAGE_RESULT = ROOT / "validation" / "v2-vector-parent-closure-coverage-manifest.json"
MAPPING_RESULT = ROOT / "validation" / "v2-vector-parent-closure-mapping-update.json"


# =============================================================================
# Implementation
# =============================================================================
# Hash exact bytes, preserving the authority artifact's line endings.
# 对精确字节计算摘要，保留权威产物的原始换行。/
def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


# Hash one path without normalizing its contents. / 对路径内容原样计算摘要。
def digest(path: Path) -> str:
    return digest_bytes(path.read_bytes())


# Load a Python target through its exact file path. / 通过精确文件路径加载 Python 目标。
def load_exact(path: Path, module_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load target: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# Check the five-zone and import contract for the maintained parent harness.
# 检查维护中的父级 harness 五区及导入合同。/
def static_audit(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    source = raw.decode("utf-8")
    tree = ast.parse(source, filename=str(path))
    lines = source.splitlines()
    zones = ("Module Contract", "Configuration", "Implementation",
             "Public Adapter", "Direct Entry")
    positions = [source.find(item) for item in zones]
    comments: list[str] = []
    forbidden: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            previous = lines[node.lineno - 2].strip() if node.lineno > 1 else ""
            if not previous.startswith("#") or "/" not in previous:
                comments.append(f"{node.name}:{node.lineno}")
        elif isinstance(node, ast.Import):
            forbidden.extend(alias.name for alias in node.names
                             if alias.name.split(".")[0] in {"subprocess", "socket", "urllib"})
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in {"subprocess", "socket", "urllib"}:
                forbidden.append(node.module)
    adapter_nodes = [node for node in tree.body
                     if isinstance(node, ast.FunctionDef) and node.name == "build_verilog"]
    args = [arg.arg for arg in adapter_nodes[0].args.args] if len(adapter_nodes) == 1 else []
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": digest(path),
        "bytes": len(raw),
        "utf8": True,
        "bom": raw.startswith(b"\xef\xbb\xbf"),
        "lf_only": b"\r" not in raw,
        "ast_parse": True,
        "zones": positions == sorted(positions) and all(item >= 0 for item in positions),
        "adapter_args": args,
        "adapter_exact": args == ["configuration", "injected_dependencies"],
        "function_comment_errors": comments,
        "forbidden_imports": forbidden,
        "status": "PASS" if (not comments and not forbidden and args == ["configuration", "injected_dependencies"]
                              and positions == sorted(positions) and all(item >= 0 for item in positions)
                              and not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw) else "FAIL",
    }


# Extract one complete emitted module from the locked reference text.
# 从锁定参考文本提取一个完整的发射模块。/
def extract_module(reference: str, name: str) -> str:
    import re

    match = re.search(r"^module " + re.escape(name) + r"\(.*?^endmodule\s*",
                      reference, re.MULTILINE | re.DOTALL)
    if match is None:
        raise RuntimeError(f"module {name} is absent from locked XSTop")
    return match.group(0)


# Rename only a generated target's declaration. / 仅重命名生成目标声明。
def rename_module(source: str, old: str, new: str) -> str:
    marker = f"module {old}("
    if marker not in source:
        raise RuntimeError(f"target declaration {old} is absent")
    return source.replace(marker, f"module {new}(", 1)


# Quote a command argument for the WSL bash invocation. / 为 WSL bash 调用引用参数。
def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


# Return the stable ASCII path visible inside WSL. / 返回 WSL 内可见的稳定 ASCII 路径。
def wsl_path(path: Path) -> str:
    return "/tmp/uhsc-v2/" + path.resolve().relative_to(ROOT.resolve()).as_posix()


# Run a bounded WSL command and retain a reproducible output digest.
# 运行有界 WSL 命令并保留可复现的输出摘要。/
def run_wsl(command: list[str], timeout: int = 240) -> dict[str, Any]:
    rendered = " ".join(shell_quote(item) for item in command)
    try:
        completed = subprocess.run(
            ["wsl.exe", "-e", "bash", "-lc", rendered],
            capture_output=True, timeout=timeout, check=False,
        )
        output = (completed.stdout + completed.stderr).decode("utf-8", "replace")
        return {
            "command": command,
            "returncode": completed.returncode,
            "status": "PASS" if completed.returncode == 0 else "FAIL",
            "output_tail": output[-1800:],
            "output_sha256": digest_bytes(output.encode("utf-8", "replace")),
        }
    except (OSError, subprocess.TimeoutExpired) as error:
        text = str(error)
        return {"command": command, "returncode": None, "status": "FAIL",
                "output_tail": text, "output_sha256": digest_bytes(text.encode())}


# Ensure the validation tree has the stable WSL alias used by every gate.
# 确保验证树具有所有门禁共用的稳定 WSL 别名。/
def prepare_wsl_alias() -> dict[str, Any]:
    # Avoid a wildcard here: multiple D: drive directories can make ``ln``
    # create a directory of links rather than the intended single alias.
    return run_wsl(["ln", "-sfn",
                    "/mnt/d/知识库开发/Unifier-Hardware-System/.agents/xiangshan-v2",
                    "/tmp/uhsc-v2"])


# Run Verilator lint and Yosys check on an exact RTL closure.
# 对精确 RTL 闭包运行 Verilator lint 与 Yosys check。/
def backend_gates(files: list[Path], top: str) -> dict[str, Any]:
    ver = run_wsl(["verilator", "--lint-only", "--Wno-fatal", "--top-module", top,
                   *[wsl_path(item) for item in files]])
    file_args = " ".join(wsl_path(item) for item in files)
    yosys = run_wsl(["yosys", "-p", f"read_verilog -sv {file_args}; hierarchy -top {top}; proc; check"])
    return {"verilator": ver, "yosys": yosys,
            "status": "PASS" if ver["status"] == "PASS" and yosys["status"] == "PASS" else "FAIL"}


# Compile and execute one generated SystemVerilog testbench.
# 编译并执行一个生成的 SystemVerilog 测试台。/
def run_harness(source: str, label: str) -> dict[str, Any]:
    WORK.mkdir(parents=True, exist_ok=True)
    source_path = WORK / f"{label}.sv"
    source_path.write_text(source, encoding="utf-8", newline="\n")
    obj = WORK / f"obj-{label}"
    compile_result = run_wsl(["verilator", "--binary", "--timing", "-Wno-fatal",
                              "--top-module", "tb", "--Mdir", wsl_path(obj),
                              wsl_path(source_path)])
    if compile_result["returncode"] != 0:
        return {"status": "FAIL_COMPILE", "compile": compile_result, "run": None,
                "trace_sha256": None, "trace_lines": 0}
    run_result = run_wsl([wsl_path(obj / "Vtb")])
    output = run_result.get("output_tail", "")
    return {"status": "PASS" if run_result["returncode"] == 0 else "FAIL_RUN",
            "compile": compile_result, "run": run_result,
            "trace_sha256": run_result.get("output_sha256"),
            "trace_lines": len(output.splitlines()), "trace_tail": output[-1800:]}


# Create deterministic parent transactions covering reset warm-up, vector
# widths, mask/tail policies, indexed selection, VL boundaries, and flush.
# 创建覆盖预热、宽度、掩码/尾策略、索引选择、VL 边界和 flush 的确定性事务。
def parent_vectors(count: int = 512) -> list[dict[str, int]]:
    vectors: list[dict[str, int]] = []
    corners = [
        {"data": 0x0123456789ABCDEF0123456789ABCDEF, "pdest": 3, "rob_flag": 0, "rob_value": 0,
         "vec_wen": 1, "v0_wen": 0, "vl_wen": 0, "vma": 0, "vta": 0, "vsew": 0, "vm": 0,
         "vstart": 0, "vmask": 0xFFFF, "vl": 16, "veew": 0, "vd_idx": 0, "is_indexed": 0,
         "is_masked": 0, "flush_valid": 0, "flush_flag": 0, "flush_value": 0, "flush_level": 0, "writeback_valid": 1},
        {"data": 0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA, "pdest": 7, "rob_flag": 0, "rob_value": 1,
         "vec_wen": 1, "v0_wen": 0, "vl_wen": 0, "vma": 1, "vta": 1, "vsew": 1, "vm": 0,
         "vstart": 2, "vmask": 0x00FF, "vl": 7, "veew": 1, "vd_idx": 1, "is_indexed": 0,
         "is_masked": 0, "flush_valid": 0, "flush_flag": 0, "flush_value": 0, "flush_level": 0, "writeback_valid": 1},
        {"data": 0x55555555555555555555555555555555, "pdest": 9, "rob_flag": 1, "rob_value": 2,
         "vec_wen": 0, "v0_wen": 1, "vl_wen": 1, "vma": 0, "vta": 0, "vsew": 3, "vm": 1,
         "vstart": 127, "vmask": 0, "vl": 128, "veew": 2, "vd_idx": 7, "is_indexed": 1,
         "is_masked": 0, "flush_valid": 0, "flush_flag": 0, "flush_value": 0, "flush_level": 0, "writeback_valid": 1},
        {"data": 0xDEADBEEF0123456789ABCDEF0F00DBAAD, "pdest": 11, "rob_flag": 1, "rob_value": 3,
         "vec_wen": 1, "v0_wen": 1, "vl_wen": 0, "vma": 1, "vta": 0, "vsew": 2, "vm": 0,
         "vstart": 8, "vmask": 0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA, "vl": 8, "veew": 3, "vd_idx": 2, "is_indexed": 1,
         "is_masked": 1, "flush_valid": 1, "flush_flag": 1, "flush_value": 3, "flush_level": 1, "writeback_valid": 1},
    ]
    vectors.extend(corners)
    for index in range(max(0, count - len(vectors))):
        vectors.append({
            "data": ((0x9E3779B97F4A7C15 * (index + 1)) ^ 0x0123456789ABCDEF) & ((1 << 128) - 1),
            "pdest": (index * 17 + 3) & 0x7F,
            "rob_flag": (index >> 3) & 1,
            "rob_value": (index * 29 + 7) & 0xFF,
            "vec_wen": index & 1, "v0_wen": (index >> 1) & 1, "vl_wen": (index % 11 == 0),
            "vma": (index >> 2) & 1, "vta": (index >> 3) & 1,
            "vsew": index & 3, "vm": (index >> 4) & 1,
            "vstart": (index * 13 + 1) & 0xFF,
            "vmask": ((0xD00DBEEFDEADBEEF * (index + 5)) ^ 0x1111222233334444) & ((1 << 128) - 1),
            "vl": (index * 31 + 2) & 0xFF, "veew": (index >> 2) & 3,
            "vd_idx": (index >> 5) & 7, "is_indexed": (index >> 6) & 1,
            "is_masked": (index >> 7) & 1,
            "flush_valid": 1 if index % 19 == 0 else 0,
            "flush_flag": (index >> 2) & 1, "flush_value": (index * 23 + 9) & 0xFF,
            "flush_level": (index >> 1) & 1,
            "writeback_valid": 0 if index % 23 == 0 else 1,
        })
    return vectors[:count]


# Convert one integer to a sized SystemVerilog literal. / 将整数转为定宽 SV 字面量。
def sv_lit(value: int, width: int) -> str:
    if width == 1:
        return f"1'b{value & 1}"
    digits = max(1, (width + 3) // 4)
    return f"{width}'h{value & ((1 << width) - 1):0{digits}X}"


# Build an SV parent comparison using one shared transaction stream.
# 构造使用共享事务流的 SV 父级比较。/
def parent_sv(reference_modules: str, target_module: str, vectors: list[dict[str, int]]) -> str:
    lines: list[str] = [reference_modules, target_module, "module tb;",
                        "  logic clock;",
                        "  logic flush_valid, flush_flag, flush_level, wb_valid, wb_rob_flag;",
                        "  logic [7:0] flush_value, wb_rob_value, wb_vstart, wb_vl;",
                        "  logic [127:0] wb_data, wb_vmask; logic [6:0] wb_pdest;",
                        "  logic wb_vec_wen, wb_v0_wen, wb_vl_wen, wb_vma, wb_vta, wb_vm;",
                        "  logic [1:0] wb_vsew, wb_veew; logic [2:0] wb_vd_idx;",
                        "  logic wb_is_indexed, wb_is_masked;",
                        "  logic ref_valid, dut_valid; logic [127:0] ref_data, dut_data;",
                        "  logic [6:0] ref_pdest, dut_pdest;",
                        "  logic ref_vec, dut_vec, ref_v0, dut_v0, ref_vl, dut_vl;",
                        "  VldMergeUnit ref_i(.clock(clock), .io_flush_valid(flush_valid),",
                        "    .io_flush_bits_robIdx_flag(flush_flag), .io_flush_bits_robIdx_value(flush_value),",
                        "    .io_flush_bits_level(flush_level), .io_writeback_valid(wb_valid),",
                        "    .io_writeback_bits_data_0(wb_data), .io_writeback_bits_pdest(wb_pdest),",
                        "    .io_writeback_bits_robIdx_flag(wb_rob_flag), .io_writeback_bits_robIdx_value(wb_rob_value),",
                        "    .io_writeback_bits_vecWen(wb_vec_wen), .io_writeback_bits_v0Wen(wb_v0_wen),",
                        "    .io_writeback_bits_vlWen(wb_vl_wen), .io_writeback_bits_vls_vpu_vma(wb_vma),",
                        "    .io_writeback_bits_vls_vpu_vta(wb_vta), .io_writeback_bits_vls_vpu_vsew(wb_vsew),",
                        "    .io_writeback_bits_vls_vpu_vm(wb_vm), .io_writeback_bits_vls_vpu_vstart(wb_vstart),",
                        "    .io_writeback_bits_vls_vpu_vmask(wb_vmask), .io_writeback_bits_vls_vpu_vl(wb_vl),",
                        "    .io_writeback_bits_vls_vpu_veew(wb_veew), .io_writeback_bits_vls_vdIdxInField(wb_vd_idx),",
                        "    .io_writeback_bits_vls_isIndexed(wb_is_indexed), .io_writeback_bits_vls_isMasked(wb_is_masked),",
                        "    .io_writebackAfterMerge_valid(ref_valid), .io_writebackAfterMerge_bits_data_0(ref_data),",
                        "    .io_writebackAfterMerge_bits_pdest(ref_pdest), .io_writebackAfterMerge_bits_vecWen(ref_vec),",
                        "    .io_writebackAfterMerge_bits_v0Wen(ref_v0), .io_writebackAfterMerge_bits_vlWen(ref_vl));",
                        "  VldMergeUnitParent dut_i(.clock_clk(clock), .io_flush_valid(flush_valid),",
                        "    .io_flush_bits_robIdx_flag(flush_flag), .io_flush_bits_robIdx_value(flush_value),",
                        "    .io_flush_bits_level(flush_level), .io_writeback_valid(wb_valid),",
                        "    .io_writeback_bits_data_0(wb_data), .io_writeback_bits_pdest(wb_pdest),",
                        "    .io_writeback_bits_robIdx_flag(wb_rob_flag), .io_writeback_bits_robIdx_value(wb_rob_value),",
                        "    .io_writeback_bits_vecWen(wb_vec_wen), .io_writeback_bits_v0Wen(wb_v0_wen),",
                        "    .io_writeback_bits_vlWen(wb_vl_wen), .io_writeback_bits_vls_vpu_vma(wb_vma),",
                        "    .io_writeback_bits_vls_vpu_vta(wb_vta), .io_writeback_bits_vls_vpu_vsew(wb_vsew),",
                        "    .io_writeback_bits_vls_vpu_vm(wb_vm), .io_writeback_bits_vls_vpu_vstart(wb_vstart),",
                        "    .io_writeback_bits_vls_vpu_vmask(wb_vmask), .io_writeback_bits_vls_vpu_vl(wb_vl),",
                        "    .io_writeback_bits_vls_vpu_veew(wb_veew), .io_writeback_bits_vls_vdIdxInField(wb_vd_idx),",
                        "    .io_writeback_bits_vls_isIndexed(wb_is_indexed), .io_writeback_bits_vls_isMasked(wb_is_masked),",
                        "    .io_writebackAfterMerge_valid(dut_valid), .io_writebackAfterMerge_bits_data_0(dut_data),",
                        "    .io_writebackAfterMerge_bits_pdest(dut_pdest), .io_writebackAfterMerge_bits_vecWen(dut_vec),",
                        "    .io_writebackAfterMerge_bits_v0Wen(dut_v0), .io_writebackAfterMerge_bits_vlWen(dut_vl));",
                        "  integer i; initial begin clock = 1'b0;"]
    for index, vector in enumerate(vectors):
        # Append one sized assignment to the generated testbench. / 向生成测试台追加定宽赋值。
        def assign(name: str, width: int, key: str) -> None:
            lines.append(f"    {name} = {sv_lit(vector[key], width)};")
        assign("wb_data", 128, "data"); assign("wb_pdest", 7, "pdest")
        assign("wb_rob_flag", 1, "rob_flag"); assign("wb_rob_value", 8, "rob_value")
        for name, key in (("wb_vec_wen", "vec_wen"), ("wb_v0_wen", "v0_wen"), ("wb_vl_wen", "vl_wen"),
                          ("wb_vma", "vma"), ("wb_vta", "vta"), ("wb_vm", "vm"),
                          ("wb_is_indexed", "is_indexed"), ("wb_is_masked", "is_masked"),
                          ("flush_valid", "flush_valid"), ("flush_flag", "flush_flag"),
                          ("flush_level", "flush_level"), ("wb_valid", "writeback_valid")):
            assign(name, 1, key)
        for name, width, key in (("wb_vsew", 2, "vsew"), ("wb_vstart", 8, "vstart"),
                                 ("wb_vmask", 128, "vmask"), ("wb_vl", 8, "vl"),
                                 ("wb_veew", 2, "veew"), ("wb_vd_idx", 3, "vd_idx"),
                                 ("flush_value", 8, "flush_value")):
            assign(name, width, key)
        lines.extend(["    #1; clock = 1'b1; #1;",
                      f"    if (ref_valid !== dut_valid) $fatal(1, \"PARENT_VALID {index}\");",
                      f"    if (ref_data !== dut_data || ref_pdest !== dut_pdest || ref_vec !== dut_vec || ref_v0 !== dut_v0 || ref_vl !== dut_vl) $fatal(1, \"PARENT_DATA {index} %h %h\", ref_data, dut_data);",
                      f"    $display(\"P %0d %b %h %h\", {index}, ref_valid, ref_data, dut_data);",
                      "    #1; clock = 1'b0; #1;"])
    lines.extend([f'    $display("VLD_MERGE_PARENT_PASS {len(vectors)}"); $finish;', "  end", "endmodule"])
    return "\n".join(lines) + "\n"


# Build a compact collision-child comparison against the locked extracted lane.
# 构造与锁定提取冲突子通路的紧凑比较。/
def collision_sv(reference: str, target: str, vectors: int = 256) -> str:
    # The target has explicit extra write-enable fields; the reference closure
    # exposes only the common rfWen/pdest/data fields.  Unused target fields are
    # tied low, while all 15 source lanes are driven identically.
    lines = [reference, target, "module tb;",
             "  logic [14:0] valid, rf; logic [14:0] fp, vec, v0, vl;",
             "  logic [7:0] pdest [0:14]; logic [63:0] data [0:14];",
             "  logic [7:0] ref_pdest [0:7], dut_pdest [0:7]; logic [63:0] ref_data [0:7], dut_data [0:7];",
             "  logic [7:0] ref_valid, dut_valid, ref_rf, dut_rf; integer i, j;",
             "  RealWBCollideChecker ref_i("]
    ref_names = set()
    import re
    # The full closure is prefixed with RealWBArbiter variants.  Select the
    # actual parent header so all fifteen parent input lanes are connected.
    header_match = re.search(r"module RealWBCollideChecker\(.*?\);", reference,
                             re.MULTILINE | re.DOTALL)
    if header_match is None:
        raise RuntimeError("RealWBCollideChecker header missing from reference closure")
    header = header_match.group(0)
    ref_names.update(re.findall(r"\b(io_[A-Za-z0-9_]+)\b", header))
    conns: list[str] = []
    for lane in range(15):
        for field, signal in (("valid", f"valid[{lane}]"), ("bits_rfWen", f"rf[{lane}]"),
                              ("bits_fpWen", f"fp[{lane}]"), ("bits_pdest", f"pdest[{lane}]"),
                              ("bits_data", f"data[{lane}]")):
            port = f"io_in_{lane}_{field}"
            if port in ref_names:
                conns.append(f".{port}({signal})")
    for port in range(8):
        for field, signal in (("valid", f"ref_valid[{port}]"), ("bits_rfWen", f"ref_rf[{port}]"),
                              ("bits_pdest", f"ref_pdest[{port}]"), ("bits_data", f"ref_data[{port}]")):
            conns.append(f".io_out_{port}_{field}({signal})")
    lines[-1] += ", ".join(conns) + ");"
    lines.append("  RealWBCollideChecker_DUT dut_i(")
    target_names = set(re.findall(r"\b(io_[A-Za-z0-9_]+)\b", target.split(");", 1)[0]))
    conns = []
    for lane in range(15):
        for field, signal in (("valid", f"valid[{lane}]"), ("bits_rfWen", f"rf[{lane}]"),
                              ("bits_fpWen", f"fp[{lane}]"), ("bits_vecWen", f"vec[{lane}]"),
                              ("bits_v0Wen", f"v0[{lane}]"), ("bits_vlWen", f"vl[{lane}]"),
                              ("bits_pdest", f"pdest[{lane}]"), ("bits_data", f"data[{lane}]")):
            port = f"io_in_{lane}_{field}"
            if port in target_names:
                conns.append(f".{port}({signal})")
    for port in range(8):
        for field, signal in (("valid", f"dut_valid[{port}]"), ("bits_rfWen", f"dut_rf[{port}]"),
                              ("bits_pdest", f"dut_pdest[{port}]"), ("bits_data", f"dut_data[{port}]")):
            conns.append(f".io_out_{port}_{field}({signal})")
    lines[-1] += ", ".join(conns) + ");"
    lines.extend(["  initial begin",
                  f"    for (i = 0; i < {vectors}; i = i + 1) begin",
                  "      valid = (i * 16'h9e37) ^ 15'h1555; rf = (i * 16'h71) ^ 15'h2a;",
                  "      fp = 0; vec = 0; v0 = 0; vl = 0;",
                  "      for (j = 0; j < 15; j = j + 1) begin pdest[j] = (i * 13 + j * 7) & 8'hff; data[j] = (64'h9e3779b97f4a7c15 * (i + j + 1)) ^ (64'h100 + j); end",
                  "      #1;",
                  "      for (j = 0; j < 8; j = j + 1) if (ref_valid[j] !== dut_valid[j] || ref_rf[j] !== dut_rf[j] || ref_pdest[j] !== dut_pdest[j] || ref_data[j] !== dut_data[j]) $fatal(1, \"COLLISION %0d/%0d\", i, j);",
                  "      $display(\"C %0d %h %h\", i, ref_valid, dut_valid);",
                  "    end",
                  f'    $display("VLD_MERGE_COLLISION_PASS {vectors}"); $finish;', "  end", "endmodule"])
    return "\n".join(lines) + "\n"


# Run direct Amaranth parent vectors against the executable Python oracle.
# 用可执行 Python oracle 运行 Amaranth 父级 direct 向量。/
def direct_parent(module: Any, vectors: list[dict[str, int]]) -> dict[str, Any]:
    leaf = load_exact(NEW_MGU_TARGET, "v2_parent_direct_new_mgu")
    child = leaf.NewMgu(leaf.NewMguConfig())
    top = module.VldMergeUnitParent(module.VldMergeUnitParentConfig(), {"mask_generator": child})
    observations: list[dict[str, int]] = []
    outputs = (top.out_valid, top.out_data, top.out_pdest, top.out_vec_wen, top.out_v0_wen, top.out_vl_wen)
    signals = {
        "flush_valid": top.flush_valid, "flush_flag": top.flush_rob_flag, "flush_value": top.flush_rob_value,
        "flush_level": top.flush_level, "writeback_valid": top.writeback_valid,
        "data": top.writeback_data, "pdest": top.writeback_pdest, "rob_flag": top.writeback_rob_flag,
        "rob_value": top.writeback_rob_value, "vec_wen": top.writeback_vec_wen, "v0_wen": top.writeback_v0_wen,
        "vl_wen": top.writeback_vl_wen, "vma": top.writeback_vma, "vta": top.writeback_vta,
        "vsew": top.writeback_vsew, "vm": top.writeback_vm, "vstart": top.writeback_vstart,
        "vmask": top.writeback_vmask, "vl": top.writeback_vl, "veew": top.writeback_veew,
        "vd_idx": top.writeback_vd_idx, "is_indexed": top.writeback_is_indexed,
        "is_masked": top.writeback_is_masked,
    }
    expected_module = module

    # Drive one parent transaction per clock and compare its observable tuple. / 每拍驱动一个父事务并比较可观察元组。
    async def bench(ctx: Any) -> None:
        for index, vector in enumerate(vectors):
            for key, signal in signals.items():
                ctx.set(signal, vector[key])
            await ctx.tick("clock")
            await ctx.delay(1e-9)
            observed = tuple(int(ctx.get(signal)) for signal in outputs)
            expected = expected_module.vld_merge_model(
                vector["data"], vector["pdest"], vector["rob_flag"], vector["rob_value"],
                bool(vector["vec_wen"]), bool(vector["v0_wen"]), bool(vector["vl_wen"]),
                bool(vector["vma"]), bool(vector["vta"]), vector["vsew"], bool(vector["vm"]),
                vector["vstart"], vector["vmask"], vector["vl"], vector["veew"], vector["vd_idx"],
                bool(vector["is_indexed"]), bool(vector["is_masked"]), bool(vector["flush_valid"]),
                vector["flush_flag"], vector["flush_value"], vector["flush_level"], bool(vector["writeback_valid"]),
            )
            # The parent exposes payload metadata even when valid is zero; the
            # reference initializes those fields to zero, so compare metadata
            # only for a valid emitted transaction.
            if observed[0] != expected[0]:
                raise AssertionError((index, "valid", observed, expected))
            if observed[0] and observed[1:] != expected[1:]:
                raise AssertionError((index, "payload", observed, expected))
            observations.append({"cycle": index, "valid": observed[0], "data": observed[1],
                                 "pdest": observed[2], "vec_wen": observed[3],
                                 "v0_wen": observed[4], "vl_wen": observed[5]})

    simulator = Simulator(top)
    simulator.add_clock(1e-6, domain="clock")
    simulator.add_testbench(bench)
    simulator.run()
    encoded = json.dumps(observations, sort_keys=True, separators=(",", ":")).encode()
    return {"status": "PASS", "vectors": len(vectors),
            "trace_sha256": digest_bytes(encoded), "trace_head": observations[:2],
            "trace_tail": observations[-2:]}


# Main runner: freeze inputs, run direct/reference/backend gates, and write
# non-accepting evidence files. / 主运行器：冻结输入、执行门禁并写入不可接受证据。
def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    alias = prepare_wsl_alias()
    reference_bytes = REF_PATH.read_bytes()
    reference_hash = digest_bytes(reference_bytes)
    if len(reference_bytes) != REFERENCE_BYTES or reference_hash != REFERENCE_SHA256:
        raise RuntimeError("locked XSTop hash/size mismatch")
    reference_text = reference_bytes.decode("utf-8", "replace")
    vectors = parent_vectors()

    parent_module = load_exact(PARENT_TARGET, "v2_vector_parent_harness_runner")
    static = static_audit(PARENT_TARGET)
    compile_result = subprocess.run([sys.executable, "-m", "py_compile", str(PARENT_TARGET)],
                                    capture_output=True, check=False)
    direct = direct_parent(parent_module, vectors)
    direct_payload = {
        "schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_VECTOR_PARENT_DIRECT",
        "batch_id": "V2-PARENT-VECTOR-001", "rules": "V2-Python-Amaranth-Rules.md",
        "status": direct["status"],
        "source_commit": SOURCE_COMMIT, "source_authority": {"path": REFERENCE_CANONICAL,
        "sha256": reference_hash, "bytes": len(reference_bytes)},
        "target": {"path": PARENT_TARGET.relative_to(ROOT).as_posix(), "sha256": digest(PARENT_TARGET)},
        "leaf_targets": {"NewMgu": NEW_MGU_TARGET.relative_to(ROOT).as_posix(),
                         "WbArbiter": WB_TARGET.relative_to(ROOT).as_posix()},
        "static_audit": static, "py_compile": {"returncode": compile_result.returncode,
        "status": "PASS" if compile_result.returncode == 0 else "FAIL"},
        "vectors": direct, "acceptance_eligible": False,
        "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": direct["status"],
                  "ACCEPTED": "NOT_ALLOWED"},
    }
    DIRECT_RESULT.write_text(json.dumps(direct_payload, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8", newline="\n")

    # Build target parent RTL and reference closure in ignored work storage.
    leaf = load_exact(NEW_MGU_TARGET, "v2_vector_parent_new_mgu_export")
    target_parent = parent_module.build_verilog(None, {"mask_generator": leaf.NewMgu(leaf.NewMguConfig())})
    target_parent_path = WORK / "target-VldMergeUnitParent.sv"
    target_parent_path.write_text(target_parent, encoding="utf-8", newline="\n")
    reference_parent = "\n".join(extract_module(reference_text, name) for name in
                                   ("UIntToContLow1s", "UIntToContLow0s", "MaskExtractor",
                                    "ByteMaskTailGen", "VldMgu", "VldMergeUnit"))
    reference_parent_path = WORK / "reference-VldMergeUnit-closure.sv"
    reference_parent_path.write_text(reference_parent, encoding="utf-8", newline="\n")
    renamed_parent = rename_module(target_parent, "VldMergeUnitParent", "VldMergeUnitParent")
    parent_sv_result = run_harness(parent_sv(reference_parent, renamed_parent, vectors), "vld-merge-parent")
    parent_backend = backend_gates([target_parent_path], "VldMergeUnitParent")
    reference_backend = backend_gates([reference_parent_path], "VldMergeUnit")

    # Reuse the existing locked RealWBCollideChecker closure as an explicit
    # child lane.  This is not a claim of full WbDataPath integration.
    wb = load_exact(WB_TARGET, "v2_vector_parent_wb_export")
    wb_config = {"module": "RealWBCollideChecker", "data_width": 64, "addr_width": 8,
                 "in_ports": [0, 0, 1, 1, 2, 4, 3, 4, 0, 1, 2, 1, 5, 6, 7],
                 "port_range": list(range(8)), "port_max": 7,
                 "priorities": [0, 1, 0, 1, 0, 0, 0, 1, 2, 3, 1, 2, 0, 0, 0]}
    target_collision = rename_module(wb.build_verilog(wb_config, {}),
                                     "RealWBCollideChecker", "RealWBCollideChecker_DUT")
    target_collision_path = WORK / "target-RealWBCollideChecker.sv"
    target_collision_path.write_text(target_collision, encoding="utf-8", newline="\n")
    collision_reference = extract_module(reference_text, "RealWBCollideChecker")
    collision_ref_path = WORK / "reference-RealWBCollideChecker-closure.sv"
    # Include the four arbiter variants required by the existing parent slice.
    collision_reference_full = "\n".join(extract_module(reference_text, name) for name in
                                           ("RealWBArbiter", "RealWBArbiter_1", "RealWBArbiter_2", "RealWBArbiter_3"))
    collision_reference_full += "\n" + collision_reference
    collision_ref_path.write_text(collision_reference_full, encoding="utf-8", newline="\n")
    collision_result = run_harness(collision_sv(collision_reference_full, target_collision), "vld-merge-collision")
    collision_backend_target = backend_gates([target_collision_path], "RealWBCollideChecker_DUT")
    collision_backend_reference = backend_gates([collision_ref_path], "RealWBCollideChecker")

    backend_pass = all(item["status"] == "PASS" for item in
                       (parent_backend, reference_backend, collision_backend_target, collision_backend_reference))
    differential_pass = parent_sv_result["status"] == "PASS" and collision_result["status"] == "PASS"
    overall = direct["status"] == "PASS" and differential_pass and backend_pass and static["status"] == "PASS" and compile_result.returncode == 0

    diff_payload = {
        "schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_VECTOR_PARENT_DIFFERENTIAL",
        "batch_id": "V2-PARENT-VECTOR-001", "source_commit": SOURCE_COMMIT,
        "reference_snapshot": {"canonical_path": REFERENCE_CANONICAL, "sha256": reference_hash, "bytes": len(reference_bytes)},
        "target_parent": {"path": PARENT_TARGET.relative_to(ROOT).as_posix(), "sha256": digest(PARENT_TARGET)},
        "target_leaf": {"NewMgu": {"path": NEW_MGU_TARGET.relative_to(ROOT).as_posix(), "sha256": digest(NEW_MGU_TARGET)},
                        "WbArbiter": {"path": WB_TARGET.relative_to(ROOT).as_posix(), "sha256": digest(WB_TARGET)}},
        "leaf_evidence": {"direct": {"path": LEAF_DIRECT.relative_to(ROOT).as_posix(), "sha256": digest(LEAF_DIRECT)},
                          "differential": {"path": LEAF_DIFF.relative_to(ROOT).as_posix(), "sha256": digest(LEAF_DIFF)}},
        "comparisons": {"VldMergeUnit_parent": parent_sv_result, "RealWBCollideChecker_child": collision_result},
        "backend_gates": {"parent_target": parent_backend, "parent_reference": reference_backend,
                           "collision_target": collision_backend_target, "collision_reference": collision_backend_reference},
        "locked_closure_modules": ["VldMergeUnit", "VldMgu", "Mgu", "ByteMaskTailGen",
                                    "MaskExtractor", "UIntToContLow0s", "UIntToContLow1s"],
        "observed_points": ["writeback valid capture", "ROB redirect kill", "VLWen bypass",
                            "vstart/vl/eew/vsew mask merge", "tail/mask agnostic bytes",
                            "physical destination metadata", "RealWBCollideChecker priority lane"],
        "behavioral_equivalence": overall, "status": "DIFFERENTIAL_MATCHED_BOUNDED" if overall else "CONTRACT_ONLY",
        "full_wbdatapath_integration": "PENDING_BACKEND_PARENT",
        "license_gate": "PENDING", "uhsc_localization": "PENDING_EXTERNAL_WRAPPER",
        "acceptance_eligible": False,
        "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": direct["status"],
                  "V2_REFERENCE_MATCHED": "PASS_BOUNDED" if parent_sv_result["status"] == "PASS" else "FAIL",
                  "PARENT_CLOSURE_MATCHED": "PASS_BOUNDED_REDUCED" if differential_pass else "FAIL",
                  "WBDATAPATH_FULL_PARENT": "PENDING_BACKEND_PARENT", "VERILATOR": "PASS" if backend_pass else "FAIL",
                  "YOSYS": "PASS" if backend_pass else "FAIL", "LICENSE": "PENDING",
                  "UHSC_LOCALIZED": "PENDING_EXTERNAL_WRAPPER", "ACCEPTED": "NOT_ALLOWED"},
        "blockers": ["Reduced closure intentionally excludes the full 861-port WbDataPath/Backend integration.",
                     "License review and project-facing UHSC wrapper localization remain open.",
                     "XSTop is used only as an immutable reference slice; no top-level acceptance is claimed."],
        "alias_gate": alias,
    }
    DIFF_RESULT.write_text(json.dumps(diff_payload, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8", newline="\n")

    coverage = {
        "schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_VECTOR_PARENT_COVERAGE",
        "batch_id": "V2-PARENT-VECTOR-001", "source_commit": SOURCE_COMMIT,
        "readiness_source": "validation/v2-parent-closure-readiness.json",
        "readiness_sha256": digest(READINESS) if READINESS.is_file() else None,
        "closure_id": "vector", "root_module": "VldMergeUnit",
        "root_source": "upstream/src/main/scala/xiangshan/backend/datapath/VldMergeUnit.scala",
        "reference_snapshot": {"path": REFERENCE_CANONICAL, "sha256": reference_hash, "bytes": len(reference_bytes)},
        "children": [
            {"instance": "VldMergeUnit.mgu", "source": "upstream/src/main/scala/xiangshan/backend/fu/vector/Mgu.scala",
             "emitted_module": "VldMgu", "target": "NewMgu-Hardware.py",
             "observation_points": ["active/agnostic byte enables", "indexed realEw selection"],
             "evidence": "VldMergeUnit_parent differential"},
            {"instance": "VldMgu.maskTailGen", "source": "upstream/src/main/scala/xiangshan/backend/fu/vector/ByteMaskTailGen.scala",
             "emitted_module": "ByteMaskTailGen", "target": "ByteMaskTailGen-Hardware.py",
             "observation_points": ["vstart/vl byte range", "vma/vta policy", "mask expansion"],
             "evidence": "existing v2-vector-batch differential plus parent trace"},
            {"instance": "ByteMaskTailGen.maskEn", "source": "upstream/src/main/scala/xiangshan/backend/fu/vector/utils/MaskExtrator.scala",
             "emitted_module": "MaskExtractor", "target": "MaskExtrator-Hardware.py",
             "observation_points": ["e8/e16/e32/e64 expansion"], "evidence": "existing leaf differential"},
            {"instance": "VldMergeUnit.writeback_collision_lane", "source": "upstream/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala",
             "emitted_module": "RealWBCollideChecker", "target": "WbArbiter-Hardware.py",
             "observation_points": ["15 input lanes", "8 output priority lanes"],
             "evidence": "reduced collision child differential", "full_parent_status": "PENDING_BACKEND_PARENT"},
        ],
        "vectors": {"parent": len(vectors), "collision": 256},
        "status": "PASS_BOUNDED_PARENT" if overall else "CONTRACT_ONLY",
        "license_review": "PENDING", "uhsc_localization": "PENDING_EXTERNAL_WRAPPER",
        "acceptance_eligible": False,
        "gates": {"DIRECT": direct["status"], "REFERENCE": "PASS_BOUNDED" if differential_pass else "FAIL",
                  "VERILATOR": "PASS" if backend_pass else "FAIL", "YOSYS": "PASS" if backend_pass else "FAIL",
                  "FULL_WBDATAPATH": "PENDING_BACKEND_PARENT", "ACCEPTED": "NOT_ALLOWED"},
    }
    COVERAGE_RESULT.write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8", newline="\n")

    mapping = {
        "schema_version": 1, "kind": "V2_VECTOR_PARENT_MAPPING_UPDATE",
        "batch_id": "V2-PARENT-VECTOR-001", "source_commit": SOURCE_COMMIT,
        "entries": [
            {"id": "VldMergeUnit", "classification": "NEW_AUXILIARY_PARENT_HARNESS",
             "v2_source": "upstream/src/main/scala/xiangshan/backend/datapath/VldMergeUnit.scala",
             "target": PARENT_TARGET.relative_to(ROOT).as_posix(), "closure_root": "core.fu.vector",
             "reference_mode": "EXTRACTED_LOCKED_XSTOP_PARENT", "status": coverage["status"]},
            {"id": "VldMergeUnit.mgu", "classification": "INJECTED_EXISTING_LEAF",
             "v2_source": "upstream/src/main/scala/xiangshan/backend/fu/vector/Mgu.scala",
             "target": NEW_MGU_TARGET.relative_to(ROOT).as_posix(), "reference_mode": "VldMgu_PARENT_CLOSURE",
             "status": "PASS_BOUNDED_REFERENCE" if parent_sv_result["status"] == "PASS" else "FAIL"},
            {"id": "VldMergeUnit.writeback_collision_lane", "classification": "REDUCED_CHILD_BOUNDARY",
             "v2_source": "upstream/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala",
             "target": WB_TARGET.relative_to(ROOT).as_posix(), "reference_mode": "EXTRACTED_REALWBCOLLIDECHECKER",
             "status": "PASS_BOUNDED_REFERENCE" if collision_result["status"] == "PASS" else "FAIL",
             "full_parent_status": "PENDING_BACKEND_PARENT"},
        ],
        "source_authority": {"canonical_path": REFERENCE_CANONICAL, "sha256": reference_hash, "bytes": len(reference_bytes)},
        "gates": {"contract": static["status"], "direct": direct["status"],
                  "reference": "PASS_BOUNDED" if differential_pass else "FAIL",
                  "parent_closure": "PASS_BOUNDED_REDUCED" if differential_pass else "FAIL",
                  "verilator": "PASS" if backend_pass else "FAIL", "yosys": "PASS" if backend_pass else "FAIL",
                  "license": "PENDING", "UHSC_LOCALIZED": "PENDING_EXTERNAL_WRAPPER",
                  "ACCEPTED": "NOT_ALLOWED"},
        "acceptance_eligible": False,
    }
    MAPPING_RESULT.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8", newline="\n")
    print(json.dumps({"status": diff_payload["status"], "direct": direct["status"],
                      "parent": parent_sv_result["status"], "collision": collision_result["status"],
                      "backend": "PASS" if backend_pass else "FAIL", "vectors": len(vectors)}, sort_keys=True))
    return 0 if overall else 1


# Direct entry for the validation command. / 验证命令的直接入口。
if __name__ == "__main__":
    raise SystemExit(main())
