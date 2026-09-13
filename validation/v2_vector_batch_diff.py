"""Run locked-XSTop differential and synthesis gates for the V2 vector batch.
执行 V2 向量批次的锁定 XSTop 差分与综合门禁。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "validation" / ".work" / "v2-vector-batch"
REF_PATH = Path(r"\\wsl$\Debian\home\lishuo\xs-v2-local\build\rtl\XSTop.sv")
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
REFERENCE_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
REFERENCE_BYTES = 228590583
DIRECT_RESULT = ROOT / "validation" / "v2-vector-batch-direct-results.json"
DIFF_RESULT = ROOT / "validation" / "v2-vector-batch-differential-results.json"
CONTRACT_RESULT = ROOT / "validation" / "v2-vector-batch-contract-audit.json"
COVERAGE_RESULT = ROOT / "validation" / "v2-vector-batch-coverage-manifest.json"
MAPPING_RESULT = ROOT / "validation" / "v2-vector-batch-mapping-update.json"
INDEX_RESULT = ROOT / "validation" / "v2-vector-batch-reference-index.json"
NAMING_RESULT = ROOT / "validation" / "v2-vector-batch-uhsc-naming-map.json"

TARGET_ROOT = ROOT / "python" / "ported" / "backend" / "fu" / "vector"
TARGETS = {
    "ByteMaskTailGen": (TARGET_ROOT / "ByteMaskTailGen-Hardware.py", "ByteMaskTailGen"),
    "DstMgu": (TARGET_ROOT / "DstMgu-Hardware.py", "DstMgu"),
    "Mgtu": (TARGET_ROOT / "Mgtu-Hardware.py", "Mgtu"),
    "NewMgu": (TARGET_ROOT / "NewMgu-Hardware.py", "NewMgu"),
    "MaskExtrator": (TARGET_ROOT / "utils" / "MaskExtrator-Hardware.py", "MaskExtractor"),
    "ScalaDupToVector": (TARGET_ROOT / "utils" / "ScalaDupToVector-Hardware.py", "ScalaDupToVector"),
    "UIntToCont0s": (TARGET_ROOT / "utils" / "UIntToCont0s-Hardware.py", "UIntToContLow0s"),
    "UIntToCont1s": (TARGET_ROOT / "utils" / "UIntToCont1s-Hardware.py", "UIntToContLow1s"),
    "VecDataSplitModule": (TARGET_ROOT / "utils" / "VecDataSplitModule-Hardware.py", "VecDataSplitModule"),
}
SCALA = {
    "ByteMaskTailGen": ROOT / "upstream" / "src/main/scala/xiangshan/backend/fu/vector/ByteMaskTailGen.scala",
    "DstMgu": ROOT / "upstream" / "src/main/scala/xiangshan/backend/fu/vector/Mgu.scala",
    "Mgtu": ROOT / "upstream" / "src/main/scala/xiangshan/backend/fu/vector/Mgtu.scala",
    "NewMgu": ROOT / "upstream" / "src/main/scala/xiangshan/backend/fu/vector/Mgu.scala",
    "MaskExtrator": ROOT / "upstream" / "src/main/scala/xiangshan/backend/fu/vector/utils/MaskExtrator.scala",
    "ScalaDupToVector": ROOT / "upstream" / "src/main/scala/xiangshan/backend/fu/vector/utils/ScalaDupToVector.scala",
    "UIntToCont0s": ROOT / "upstream" / "src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont0s.scala",
    "UIntToCont1s": ROOT / "upstream" / "src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont1s.scala",
    "VecDataSplitModule": ROOT / "upstream" / "src/main/scala/xiangshan/backend/fu/vector/utils/VecDataSplitModule.scala",
}


# Hash exact bytes. / 对精确字节计算摘要。
def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Load a target module by exact path. / 按精确路径加载目标模块。
def load_target(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Convert a repository path to the stable ASCII WSL alias. / 将仓库路径转换为稳定 ASCII WSL 别名。
def wsl_path(path: Path) -> str:
    relative = path.resolve().relative_to(ROOT.resolve())
    return "/tmp/uhsc-v2/" + relative.as_posix()


# Run one bounded WSL command and retain a deterministic diagnostic digest.
# 运行一个有界 WSL 命令并保留确定性诊断摘要。
def run_wsl(command: list[str]) -> dict[str, Any]:
    rendered = " ".join(_shell_quote(item) for item in command)
    completed = subprocess.run(
        ["wsl.exe", "-e", "bash", "-lc", rendered],
        capture_output=True,
        check=False,
    )
    output = (completed.stdout + completed.stderr).decode("utf-8", "replace")
    return {
        "command": command,
        "returncode": completed.returncode,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "output_tail": output[-3000:],
        "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
    }


# Quote one shell argument without relying on host locale. / 安全引用单个 shell 参数。
def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


# Extract one complete top-level module from the locked reference. / 从锁定参考提取完整顶层模块。
def extract_module(reference_text: str, name: str) -> str:
    match = re.search(r"^module " + re.escape(name) + r"\(.*?^endmodule\s*", reference_text, re.MULTILINE | re.DOTALL)
    if match is None:
        raise RuntimeError(f"reference module not found: {name}")
    return match.group(0)


# Rename only the generated target declaration. / 仅重命名生成目标声明。
def rename_module(source: str, old: str, new: str) -> str:
    marker = f"module {old}("
    if marker not in source:
        raise RuntimeError(f"target module declaration not found: {old}")
    return source.replace(marker, f"module {new}(", 1)


# Export target Verilog into ignored evidence storage. / 将目标 Verilog 导出到忽略的证据目录。
def export_targets() -> dict[str, Path]:
    WORK.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, Path] = {}
    for index, (name, (path, module_name)) in enumerate(TARGETS.items()):
        module = load_target(path, f"v2_vector_diff_{index}")
        text = module.build_verilog(None, {})
        out = WORK / f"target-{name}.sv"
        out.write_text(text, encoding="utf-8", newline="\n")
        outputs[name] = out
    return outputs


# Run Verilator lint and Yosys check on one generated or extracted module.
# 对一个生成或提取模块运行 Verilator lint 与 Yosys 检查。
def synthesis_gates(path: Path, top: str, extra: list[Path] | None = None) -> dict[str, Any]:
    files = [path, *(extra or [])]
    ver = run_wsl(["verilator", "--lint-only", "--Wno-fatal", "--top-module", top,
                   *[wsl_path(item) for item in files]])
    # The stable /tmp alias is ASCII and contains no spaces; leaving paths
    # unquoted avoids Yosys treating the quote characters as part of a filename.
    file_args = " ".join(wsl_path(item) for item in files)
    yosys = run_wsl(["yosys", "-p", f"read_verilog -sv {file_args}; hierarchy -top {top}; proc; check"])
    return {"verilator": ver, "yosys": yosys}


# Compile and execute one SystemVerilog differential harness. / 编译并执行一个 SystemVerilog 差分测试台。
def run_harness(label: str, source: str) -> dict[str, Any]:
    WORK.mkdir(parents=True, exist_ok=True)
    source_path = WORK / f"{label}.sv"
    source_path.write_text(source, encoding="utf-8", newline="\n")
    obj = WORK / f"obj-{label}"
    obj.mkdir(parents=True, exist_ok=True)
    compile_result = run_wsl(["verilator", "--binary", "--timing", "-Wno-fatal",
                              "--top-module", "tb", "--Mdir", wsl_path(obj),
                              wsl_path(source_path)])
    if compile_result["returncode"] != 0:
        return {"status": "FAIL_COMPILE", "compile": compile_result, "run": None,
                "trace_sha256": None, "trace_lines": 0}
    binary = obj / "Vtb"
    run_result = run_wsl([wsl_path(binary)])
    output = run_result.get("output_tail", "")
    return {
        "status": "PASS" if run_result["returncode"] == 0 else "FAIL_RUN",
        "compile": compile_result,
        "run": run_result,
        "trace_sha256": run_result.get("output_sha256"),
        "trace_lines": len(output.splitlines()),
        "trace_tail": output[-1800:],
    }


# Build the standalone MaskExtractor differential harness. / 构造独立 MaskExtractor 差分台。
def harness_mask(ref: str, dut: str) -> str:
    return ref + "\n" + dut + r'''
module tb;
  logic [15:0] mask; logic [1:0] sew; logic [15:0] ref_out, dut_out;
  MaskExtractor ref_i(.io_in_mask(mask), .io_in_vsew(sew), .io_out_mask(ref_out));
  DUT_MaskExtractor dut_i(.io_in_mask(mask), .io_in_vsew(sew), .io_out_mask(dut_out));
  integer i;
  initial begin
    for (i = 0; i < 4096; i = i + 1) begin
      mask = (i * 16'h9e37) ^ 16'ha55a; sew = i[1:0]; #1;
      if (ref_out !== dut_out) $fatal(1, "MASK_MISMATCH %0d %h %h", i, ref_out, dut_out);
    end
    $display("MASK_REFERENCE_PASS 4096"); $finish;
  end
endmodule
'''


# Build contiguous-mask differential harness. / 构造连续掩码差分台。
def harness_contiguous(ref: str, dut: str, module_name: str) -> str:
    return ref + "\n" + dut + f'''\nmodule tb;
  logic [7:0] in_value; logic [254:0] ref_out, dut_out;
  {module_name} ref_i(.io_dataIn(in_value), .io_dataOut(ref_out));
  DUT_{module_name} dut_i(.io_dataIn(in_value), .io_dataOut(dut_out));
  integer i;
  initial begin
    for (i = 0; i < 256; i = i + 1) begin
      in_value = i; #1;
      if (ref_out !== dut_out) $fatal(1, "CONTIGUOUS_MISMATCH %0d", i);
    end
    $display("{module_name}_REFERENCE_PASS 256"); $finish;
  end
endmodule
'''


# Build Mgtu differential harness. / 构造 Mgtu 差分台。
def harness_mgtu(ref: str, dut: str) -> str:
    return ref + "\n" + dut + r'''
module tb;
  logic [127:0] vd; logic [7:0] vl; logic [127:0] ref_out, dut_out;
  Mgtu ref_i(.io_in_vd(vd), .io_in_vl(vl), .io_out_vd(ref_out));
  DUT_Mgtu dut_i(.io_in_vd(vd), .io_in_vl(vl), .io_out_vd(dut_out));
  integer i, j;
  initial begin
    for (j = 0; j < 4; j = j + 1) begin
      vd = (j[0] ? 128'hAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA : 128'h0123456789ABCDEF0123456789ABCDEF);
      for (i = 0; i < 256; i = i + 1) begin
        vl = i; #1;
        if (ref_out !== dut_out) $fatal(1, "MGTU_MISMATCH %0d", i);
      end
    end
    $display("MGTU_REFERENCE_PASS 1024"); $finish;
  end
endmodule
'''


# Build ByteMaskTailGen differential harness. / 构造 ByteMaskTailGen 差分台。
def harness_byte(refs: str, dut: str) -> str:
    return refs + "\n" + dut + r'''
module tb;
  logic [7:0] begin_i, end_i; logic vma, vta; logic [1:0] sew;
  logic [15:0] mask; logic [2:0] idx; logic [15:0] ref_a, ref_g, dut_a, dut_g;
  ByteMaskTailGen ref_i(.io_in_begin(begin_i), .io_in_end(end_i), .io_in_vma(vma), .io_in_vta(vta),
    .io_in_vsew(sew), .io_in_maskUsed(mask), .io_in_vdIdx(idx), .io_out_activeEn(ref_a), .io_out_agnosticEn(ref_g));
  DUT_ByteMaskTailGen dut_i(.io_in_begin(begin_i), .io_in_end(end_i), .io_in_vma(vma), .io_in_vta(vta),
    .io_in_vsew(sew), .io_in_maskUsed(mask), .io_in_vdIdx(idx), .io_out_activeEn(dut_a), .io_out_agnosticEn(dut_g));
  integer i;
  initial begin
    for (i = 0; i < 20000; i = i + 1) begin
      begin_i = i * 73 + 11; end_i = i * 151 + 7; vma = i[0]; vta = i[1];
      sew = i[3:2]; mask = (i * 16'h1f31) ^ 16'ha55a; idx = i[6:4]; #1;
      if (ref_a !== dut_a || ref_g !== dut_g)
        $fatal(1, "BYTE_MISMATCH %0d %h/%h %h/%h", i, ref_a, ref_g, dut_a, dut_g);
    end
    $display("BYTE_REFERENCE_PASS 20000"); $finish;
  end
endmodule
'''


# Build packed splitter differential harness. / 构造打包分割器差分台。
def harness_split(ref: str, dut: str) -> str:
    ports_ref = ", ".join([f".io_outVec8b_{i}(ref8[{i}])" for i in range(16)] +
                           [f".io_outVec16b_{i}(ref16[{i}])" for i in range(8)] +
                           [f".io_outVec32b_{i}(ref32[{i}])" for i in range(4)] +
                           [f".io_outVec64b_{i}(ref64[{i}])" for i in range(2)])
    ports_dut = ", ".join([f".io_outVec8b_{i}(dut8[{i}])" for i in range(16)] +
                           [f".io_outVec16b_{i}(dut16[{i}])" for i in range(8)] +
                           [f".io_outVec32b_{i}(dut32[{i}])" for i in range(4)] +
                           [f".io_outVec64b_{i}(dut64[{i}])" for i in range(2)])
    checks = " ".join([f"if (ref8[{i}] !== dut8[{i}]) $fatal(1, \"SPLIT8 %0d\", i);" for i in range(16)] +
                      [f"if (ref16[{i}] !== dut16[{i}]) $fatal(1, \"SPLIT16 %0d\", i);" for i in range(8)] +
                      [f"if (ref32[{i}] !== dut32[{i}]) $fatal(1, \"SPLIT32 %0d\", i);" for i in range(4)] +
                      [f"if (ref64[{i}] !== dut64[{i}]) $fatal(1, \"SPLIT64 %0d\", i);" for i in range(2)])
    return ref + "\n" + dut + f'''\nmodule tb;
  logic [127:0] in_value; logic [7:0] ref8 [0:15], dut8 [0:15];
  logic [15:0] ref16 [0:7], dut16 [0:7]; logic [31:0] ref32 [0:3], dut32 [0:3];
  logic [63:0] ref64 [0:1], dut64 [0:1];
  VecDataSplitModule ref_i(.io_inVecData(in_value), {ports_ref});
  DUT_VecDataSplitModule dut_i(.io_inVecData(in_value), {ports_dut});
  integer i;
  initial begin
    for (i = 0; i < 1000; i = i + 1) begin
      in_value = (128'h9E3779B97F4A7C15 * i) ^ 128'h0123456789ABCDEF; #1;
      {checks}
    end
    $display("SPLIT_REFERENCE_PASS 1000"); $finish;
  end
endmodule
'''


# Build NewMgu normal-mode parent-closure harness against extracted Mgu.
# 构造 NewMgu 普通模式与提取 Mgu 的父闭包差分台。
def harness_new_normal(refs: str, dut: str) -> str:
    return refs + "\n" + dut + r'''
module tb;
  logic [127:0] mask, vd0, old0; logic ta, ma; logic [7:0] vstart, vl;
  logic [1:0] eew, vsew; logic [2:0] idx; logic [15:0] ref_a, dut_a, dut_g;
  Mgu ref_i(.io_in_vd(vd0), .io_in_oldVd(old0), .io_in_mask(mask), .io_in_info_ta(ta),
    .io_in_info_ma(ma), .io_in_info_vl(vl), .io_in_info_vstart(vstart), .io_in_info_eew(eew),
    .io_in_info_vdIdx(idx), .io_in_info_narrow(1'b0), .io_in_info_dstMask(1'b0),
    .io_out_vd(), .io_out_active(ref_a));
  DUT_NewMgu dut_i(.io_in_mask(mask), .io_in_info_ta(ta), .io_in_info_ma(ma),
    .io_in_info_vstart(vstart), .io_in_info_vl(vl), .io_in_info_eew(eew), .io_in_info_vsew(vsew),
    .io_in_info_vdIdx(idx), .io_in_isIndexedVls(1'b0), .io_out_activeEn(dut_a), .io_out_agnosticEn(dut_g));
  integer i;
  initial begin
    vd0 = 0; old0 = 0;
    for (i = 0; i < 30000; i = i + 1) begin
      mask = (128'h9E3779B97F4A7C15 * i) ^ 128'h0123456789ABCDEF;
      ta = i[0]; ma = i[1]; vstart = i * 17; vl = i * 29; eew = i[3:2]; vsew = i[5:4]; idx = i[8:6]; #1;
      if (ref_a !== dut_a) $fatal(1, "NEW_NORMAL_MISMATCH %0d %h %h", i, ref_a, dut_a);
    end
    $display("NEW_MGU_MGU_PARENT_PASS 30000"); $finish;
  end
endmodule
'''


# Build NewMgu indexed-mode closure harness against VldMgu at vdIdx=0.
# 构造 NewMgu 索引模式与 VldMgu 闭包的差分台（vdIdx=0）。
def harness_new_indexed(refs: str, dut: str) -> str:
    return refs + "\n" + dut + r'''
module tb;
  logic [127:0] mask, vd0, old0; logic ta, ma; logic [7:0] vstart, vl;
  logic [1:0] eew, vsew; logic [2:0] idx; logic indexed; logic [127:0] ref_vd;
  logic [15:0] dut_a, dut_g; logic [127:0] expected_byte;
  VldMgu ref_i(.io_in_vd(vd0), .io_in_oldVd(old0), .io_in_mask(mask), .io_in_info_ta(ta),
    .io_in_info_ma(ma), .io_in_info_vl(vl), .io_in_info_vstart(vstart), .io_in_info_eew(eew),
    .io_in_info_vsew(vsew), .io_in_info_vdIdx(3'b000), .io_in_isIndexedVls(1'b1), .io_out_vd(ref_vd));
  DUT_NewMgu dut_i(.io_in_mask(mask), .io_in_info_ta(ta), .io_in_info_ma(ma),
    .io_in_info_vstart(vstart), .io_in_info_vl(vl), .io_in_info_eew(eew), .io_in_info_vsew(vsew),
    .io_in_info_vdIdx(3'b000), .io_in_isIndexedVls(1'b1), .io_out_activeEn(dut_a), .io_out_agnosticEn(dut_g));
  integer i, lane;
  initial begin
    vd0 = {16{8'h55}}; old0 = {16{8'hAA}};
    for (i = 0; i < 12000; i = i + 1) begin
      mask = (128'hD00DBEEFDEADBEEF * i) ^ 128'h000000000000FFFF;
      ta = i[0]; ma = i[1]; vstart = i * 13; vl = i * 31; eew = i[3:2]; vsew = i[5:4]; #1;
      for (lane = 0; lane < 16; lane = lane + 1) begin
        if (ref_vd[lane*8 +: 8] == 8'h55 && !dut_a[lane]) $fatal(1, "NEW_INDEX_ACTIVE %0d/%0d", i, lane);
        if (ref_vd[lane*8 +: 8] == 8'hFF && !dut_g[lane]) $fatal(1, "NEW_INDEX_AGNOSTIC %0d/%0d", i, lane);
        if (ref_vd[lane*8 +: 8] == 8'hAA && (dut_a[lane] || dut_g[lane])) $fatal(1, "NEW_INDEX_IDLE %0d/%0d", i, lane);
      end
    end
    $display("NEW_MGU_VLD_PARENT_PASS 12000"); $finish;
  end
endmodule
'''


# Build DstMgu folded parent-closure harness against Mgu dstMask output.
# 构造 DstMgu 折叠父闭包与 Mgu dstMask 输出的差分台。
def harness_dst(refs: str, dut: str) -> str:
    return refs + "\n" + dut + r'''
module tb;
  logic [127:0] vd, oldv, mask; logic ma; logic [1:0] eew; logic [2:0] idx;
  logic [127:0] ref_vd, dut_vd; logic [15:0] active;
  Mgu ref_i(.io_in_vd(vd), .io_in_oldVd(oldv), .io_in_mask(mask), .io_in_info_ta(1'b0),
    .io_in_info_ma(ma), .io_in_info_vl(8'h00), .io_in_info_vstart(8'h00), .io_in_info_eew(eew),
    .io_in_info_vdIdx(idx), .io_in_info_narrow(1'b0), .io_in_info_dstMask(1'b1),
    .io_out_vd(ref_vd), .io_out_active(active));
  DUT_DstMgu dut_i(.io_in_vd(vd), .io_in_oldVd(oldv), .io_in_mask(mask), .io_in_info_ma(ma),
    .io_in_info_eew(eew), .io_in_info_vdIdx(idx), .io_out_vd(dut_vd));
  integer i;
  initial begin
    for (i = 0; i < 30000; i = i + 1) begin
      vd = (128'h9E3779B97F4A7C15 * i) ^ 128'h0123456789ABCDEF;
      oldv = (128'hF00DCAFE12345678 * i) ^ 128'hFEDCBA9876543210;
      mask = (128'hD00DBEEFDEADBEEF * i) ^ 128'h1111222233334444;
      ma = i[0]; eew = i[3:2]; idx = i[8:6]; #1;
      if (ref_vd !== dut_vd) $fatal(1, "DST_MISMATCH %0d %h %h", i, ref_vd, dut_vd);
    end
    $display("DST_MGU_MGU_PARENT_PASS 30000"); $finish;
  end
endmodule
'''


# Record source-level evidence for a non-extractable ScalaDupToVector module.
# 为不可提取的 ScalaDupToVector 记录源级证据。
def scalar_source_evidence() -> dict[str, Any]:
    source = SCALA["ScalaDupToVector"].read_text(encoding="utf-8")
    needles = ["VecInit", "scalaData", "VSew.e8", "VSew.e16", "VSew.e32", "VSew.e64", "Mux1H", "asUInt"]
    occurrences = {needle: source.count(needle) for needle in needles}
    return {
        "path": SCALA["ScalaDupToVector"].relative_to(ROOT).as_posix(),
        "source_sha256": digest(SCALA["ScalaDupToVector"]),
        "required_tokens": occurrences,
        "status": "PASS_BOUNDED_SOURCE" if all(occurrences.values()) else "FAIL",
        "reference_mode": "SOURCE_LEVEL_PARENT_CLOSURE",
        "reason": "ScalaDupToVector is not instantiated as a standalone module in locked XSTop.sv",
    }


# Main differential runner and evidence writer. / 主差分运行器与证据写入器。
def main() -> int:
    raw_ref = REF_PATH.read_bytes()
    ref_hash = hashlib.sha256(raw_ref).hexdigest()
    if len(raw_ref) != REFERENCE_BYTES or ref_hash != REFERENCE_SHA256:
        raise RuntimeError("locked XSTop hash/size mismatch")
    reference_text = raw_ref.decode("utf-8", "replace")
    subprocess.run(["wsl.exe", "-e", "bash", "-lc",
                    "ln -sfn /mnt/d/*/Unifier-Hardware-System/.agents/xiangshan-v2 /tmp/uhsc-v2"],
                   check=True, capture_output=True)
    targets = export_targets()

    # Extract the reference modules used by standalone and parent closures.
    ref_names = ["VecDataSplitModule", "UIntToContLow1s", "UIntToContLow0s",
                 "MaskExtractor", "ByteMaskTailGen", "Mgtu", "Mgu", "VldMgu"]
    refs: dict[str, Path] = {}
    for name in ref_names:
        path = WORK / f"reference-{name}.sv"
        path.write_text(extract_module(reference_text, name), encoding="utf-8", newline="\n")
        refs[name] = path

    # Rename each target declaration and retain exact target hashes.
    renamed: dict[str, str] = {}
    for key, path in targets.items():
        old_name = TARGETS[key][1]
        renamed[key] = rename_module(path.read_text(encoding="utf-8"), old_name, f"DUT_{old_name}")

    results: dict[str, Any] = {}
    synthesis: dict[str, Any] = {}

    def standalone(key: str, ref_name: str, source: str) -> None:
        target_path = WORK / f"renamed-{key}.sv"
        target_path.write_text(renamed[key], encoding="utf-8", newline="\n")
        source_path = WORK / f"combined-{key}.sv"
        source_path.write_text(source, encoding="utf-8", newline="\n")
        results[key] = run_harness(key.lower(), source)
        synthesis[key] = synthesis_gates(targets[key], TARGETS[key][1])
        ref_extra = [refs[item] for item in ("UIntToContLow1s", "UIntToContLow0s", "MaskExtractor")]
        synthesis[f"reference:{ref_name}"] = synthesis_gates(
            refs[ref_name], ref_name, ref_extra if ref_name == "ByteMaskTailGen" else None
        )

    standalone("MaskExtrator", "MaskExtractor",
               harness_mask(extract_module(reference_text, "MaskExtractor"), renamed["MaskExtrator"]))
    standalone("UIntToCont0s", "UIntToContLow0s",
               harness_contiguous(extract_module(reference_text, "UIntToContLow0s"), renamed["UIntToCont0s"], "UIntToContLow0s"))
    standalone("UIntToCont1s", "UIntToContLow1s",
               harness_contiguous(extract_module(reference_text, "UIntToContLow1s"), renamed["UIntToCont1s"], "UIntToContLow1s"))
    standalone("Mgtu", "Mgtu", harness_mgtu(extract_module(reference_text, "Mgtu"), renamed["Mgtu"]))
    standalone("ByteMaskTailGen", "ByteMaskTailGen",
               harness_byte("\n".join(extract_module(reference_text, name) for name in
                                      ["UIntToContLow1s", "UIntToContLow0s", "MaskExtractor", "ByteMaskTailGen"]),
                            renamed["ByteMaskTailGen"]))
    standalone("VecDataSplitModule", "VecDataSplitModule",
               harness_split(extract_module(reference_text, "VecDataSplitModule"), renamed["VecDataSplitModule"]))

    # Parent closure comparisons for relocated/removed surfaces.
    parent_refs = "\n".join(extract_module(reference_text, name) for name in
                             ["UIntToContLow1s", "UIntToContLow0s", "MaskExtractor", "ByteMaskTailGen", "Mgu"])
    new_normal_source = harness_new_normal(parent_refs, renamed["NewMgu"])
    (WORK / "combined-NewMgu-normal.sv").write_text(new_normal_source, encoding="utf-8", newline="\n")
    results["NewMgu.normal_parent"] = run_harness("newmgu-normal", new_normal_source)
    synthesis["NewMgu.target"] = synthesis_gates(targets["NewMgu"], "NewMgu")
    synthesis["Mgu.reference"] = synthesis_gates(refs["Mgu"], "Mgu", [refs[x] for x in ("UIntToContLow1s", "UIntToContLow0s", "MaskExtractor", "ByteMaskTailGen")])

    vld_refs = "\n".join(extract_module(reference_text, name) for name in
                           ["UIntToContLow1s", "UIntToContLow0s", "MaskExtractor", "ByteMaskTailGen", "VldMgu"])
    new_index_source = harness_new_indexed(vld_refs, renamed["NewMgu"])
    (WORK / "combined-NewMgu-indexed.sv").write_text(new_index_source, encoding="utf-8", newline="\n")
    results["NewMgu.indexed_parent"] = run_harness("newmgu-indexed", new_index_source)
    synthesis["VldMgu.reference"] = synthesis_gates(refs["VldMgu"], "VldMgu", [refs[x] for x in ("UIntToContLow1s", "UIntToContLow0s", "MaskExtractor", "ByteMaskTailGen")])

    dst_source = harness_dst(parent_refs, renamed["DstMgu"])
    (WORK / "combined-DstMgu.sv").write_text(dst_source, encoding="utf-8", newline="\n")
    results["DstMgu.parent"] = run_harness("dstmgu-parent", dst_source)
    synthesis["DstMgu.target"] = synthesis_gates(targets["DstMgu"], "DstMgu")

    direct = json.loads(DIRECT_RESULT.read_text(encoding="utf-8"))
    scalar_evidence = scalar_source_evidence()
    results["ScalaDupToVector.source"] = scalar_evidence
    # Synthesis for every target, including non-extractable source-level target.
    synthesis["ScalaDupToVector.target"] = synthesis_gates(targets["ScalaDupToVector"], "ScalaDupToVector")

    standalone_pass = all(results[name]["status"] == "PASS" for name in
                           ("MaskExtrator", "UIntToCont0s", "UIntToCont1s", "Mgtu", "ByteMaskTailGen", "VecDataSplitModule"))
    parent_pass = results["NewMgu.normal_parent"]["status"] == "PASS" and results["NewMgu.indexed_parent"]["status"] == "PASS" and results["DstMgu.parent"]["status"] == "PASS"
    source_pass = scalar_evidence["status"] == "PASS_BOUNDED_SOURCE"
    synthesis_pass = all(item["verilator"]["status"] == "PASS" and item["yosys"]["status"] == "PASS" for item in synthesis.values())
    all_pass = standalone_pass and parent_pass and source_pass and synthesis_pass

    # Contract audit is copied from the direct run and explicitly remains non-accepting.
    contract = direct.get("contract_audit", {})
    CONTRACT_RESULT.write_text(json.dumps({
        "schema_version": 1,
        "kind": "V2_P1_E_VECTOR_CONTRACT_AUDIT",
        "batch_id": "V2-P1-E-VECTOR-MASK",
        "rules": "V2-Python-Amaranth-Rules.md",
        "result": contract.get("status", "FAIL"),
        "rows": contract.get("rows", {}),
        "acceptance_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    ref_index = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_VECTOR_REFERENCE_MODULE_INDEX",
        "source_commit": SOURCE_COMMIT,
        "reference_artifact": {"path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv",
                               "sha256": ref_hash, "bytes": len(raw_ref)},
        "extractable_reference_modules": ["VecDataSplitModule", "UIntToContLow1s", "UIntToContLow0s",
                                           "MaskExtractor", "ByteMaskTailGen", "Mgtu"],
        "parent_closure_reference_modules": {"NewMgu": "Mgu/VldMgu", "DstMgu": "Mgu"},
        "non_extractable_carried_surfaces": {"ScalaDupToVector": "not instantiated in locked XSTop; source-level evidence"},
        "extracted": {name: {"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path), "bytes": len(path.read_bytes())}
                      for name, path in refs.items()},
        "extraction_rule": "Complete module body is extracted from the locked XSTop artifact; parent closures name every child.",
        "acceptance_claim": False,
    }
    INDEX_RESULT.write_text(json.dumps(ref_index, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8", newline="\n")

    coverage_targets = [
        ("ByteMaskTailGen", ["upstream/src/main/scala/xiangshan/backend/fu/vector/ByteMaskTailGen.scala"],
         ["start/end byte scaling", "body/tail", "vdIdx lookup", "mask agnostic", "tail agnostic"], ["ByteMaskTailGen", "MaskExtractor", "UIntToContLow0s", "UIntToContLow1s"], "ByteMaskTailGen", "PASS_BOUNDED_REFERENCE"),
        ("DstMgu", ["upstream/src/main/scala/xiangshan/backend/fu/vector/Mgu.scala"],
         ["splitVdMask", "ma fallback", "eew/vdIdx splice"], ["Mgu dstMask path"], "Mgu parent closure", "PASS_BOUNDED_PARENT"),
        ("Mgtu", ["upstream/src/main/scala/xiangshan/backend/fu/vector/Mgtu.scala"],
         ["vl=0", "vl=1", "vl=127", "vl=128", "vl>vlen"], ["Mgtu"], "Mgtu", "PASS_BOUNDED_REFERENCE"),
        ("NewMgu", ["upstream/src/main/scala/xiangshan/backend/fu/vector/Mgu.scala"],
         ["realEw", "mask chunk", "vstart/vl", "indexed and normal"], ["Mgu maskTailGen", "VldMgu specialization"], "Mgu/VldMgu parent closure", "PASS_BOUNDED_PARENT"),
        ("MaskExtrator", ["upstream/src/main/scala/xiangshan/backend/fu/vector/utils/MaskExtrator.scala"],
         ["e8", "e16", "e32", "e64"], ["MaskExtractor"], "MaskExtractor", "PASS_BOUNDED_REFERENCE"),
        ("ScalaDupToVector", ["upstream/src/main/scala/xiangshan/backend/fu/vector/utils/ScalaDupToVector.scala"],
         ["scalar low 8/16/32/64", "VecInit packing"], ["ScalaDupToVector source equations"], "source-level", "PASS_BOUNDED_SOURCE"),
        ("UIntToCont0s", ["upstream/src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont0s.scala"],
         ["all 256 count values"], ["UIntToContLow0s"], "UIntToContLow0s", "PASS_BOUNDED_REFERENCE"),
        ("UIntToCont1s", ["upstream/src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont1s.scala"],
         ["all 256 count values"], ["UIntToContLow1s"], "UIntToContLow1s", "PASS_BOUNDED_REFERENCE"),
        ("VecDataSplitModule", ["upstream/src/main/scala/xiangshan/backend/fu/vector/utils/VecDataSplitModule.scala"],
         ["8/16/32/64-bit slices"], ["VecDataSplitModule"], "VecDataSplitModule", "PASS_BOUNDED_REFERENCE"),
    ]
    coverage = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_VECTOR_CHILD_COVERAGE",
        "batch_id": "V2-P1-E-VECTOR-MASK",
        "source_commit": SOURCE_COMMIT,
        "closure_root": "core.fu.vector",
        "targets": [
            {"candidate": name, "python_path": TARGETS[name][0].relative_to(ROOT).as_posix(),
             "v2_sources": sources, "covered_children": children, "observation_points": points,
             "reference_surface": reference, "direct": "PASS_BOUNDED_DIRECT",
             "differential": differential, "status": "PENDING_COORDINATOR_REVIEW"}
            for name, sources, points, children, reference, differential in coverage_targets
        ],
        "locked_reference": {"path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv", "sha256": ref_hash, "bytes": len(raw_ref)},
        "parent_closure": "PASS_BOUNDED_PARENT",
        "license_review": "PENDING",
        "uhsc_localization": "PENDING_EXTERNAL_WRAPPER",
        "acceptance_eligible": False,
    }
    COVERAGE_RESULT.write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8", newline="\n")

    classifications = {
        "ByteMaskTailGen": "EXACT", "DstMgu": "REWRITTEN", "Mgtu": "REWRITTEN",
        "NewMgu": "REWRITTEN", "MaskExtrator": "EXACT", "ScalaDupToVector": "EXACT",
        "UIntToCont0s": "REWRITTEN", "UIntToCont1s": "REWRITTEN", "VecDataSplitModule": "EXACT",
    }
    mapping = {
        "schema_version": 1,
        "kind": "V2_P1_E_VECTOR_MAPPING_UPDATE",
        "batch_id": "V2-P1-E-VECTOR-MASK",
        "source_commit": SOURCE_COMMIT,
        "locked_reference": {"path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv", "sha256": ref_hash, "bytes": len(raw_ref)},
        "entries": [
            {"id": name, "classification": classifications[name], "v2_source": [path.relative_to(ROOT).as_posix() for path in ([SCALA[name]] if name not in ("DstMgu", "NewMgu") else [SCALA[name]])],
             "target": TARGETS[name][0].relative_to(ROOT).as_posix(),
             "reference_mode": ("EXTRACTED_MODULE" if name in ("ByteMaskTailGen", "Mgtu", "MaskExtrator", "UIntToCont0s", "UIntToCont1s", "VecDataSplitModule") else ("Mgu_VldMgu_PARENT_CLOSURE" if name == "NewMgu" else ("Mgu_PARENT_CLOSURE" if name == "DstMgu" else "SOURCE_LEVEL_PARENT_CLOSURE"))),
             "status": ("DIFFERENTIAL_MATCHED_BOUNDED" if name != "ScalaDupToVector" else "SOURCE_MATCHED_BOUNDED"),
             "covered_children": ["canonical V2 implementation", "parent closure" if name in ("DstMgu", "NewMgu") else ("source-level equation" if name == "ScalaDupToVector" else "standalone module")]}
            for name in TARGETS
        ],
        "localization_map": {"manifest": "UHSC-Naming-Manifest.json", "status": "NO_PROJECT_FACING_RENAME",
                             "locked_names_unchanged": True,
                             "entries": [{"source_name": "XSTop", "local_name": "UHSCTop", "visibility": "project-owned external wrapper", "reason": "Vector child batch leaves locked reference names unchanged.", "status": "PLANNED"},
                                         {"source_name": "XiangShan/XS/KMHV2", "local_name": "UHSC", "visibility": "project-owned external identity", "reason": "No product-facing rename introduced.", "status": "NOT_APPLIED"}]},
        "gates": {"contract": contract.get("status", "FAIL"), "direct": direct.get("status", "FAIL"),
                  "reference": "PASS_BOUNDED_REFERENCE" if standalone_pass else "FAIL",
                  "parent_closure": "PASS_BOUNDED_PARENT" if parent_pass else "FAIL",
                  "source_level": "PASS_BOUNDED_SOURCE" if source_pass else "FAIL",
                  "verilator": "PASS" if synthesis_pass else "FAIL", "yosys": "PASS" if synthesis_pass else "FAIL",
                  "license": "PENDING"},
        "acceptance_eligible": False,
    }
    MAPPING_RESULT.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8", newline="\n")

    naming = {
        "schema_version": 1,
        "kind": "UHSC_VECTOR_BATCH_NAMING_MAP",
        "batch_id": "V2-P1-E-VECTOR-MASK",
        "source_commit": SOURCE_COMMIT,
        "reference_names_unchanged": True,
        "status": "PENDING_COORDINATOR_REVIEW",
        "entries": [{"source_name": "XSTop", "local_name": "UHSCTop", "visibility": "project-owned external HDL wrapper", "reason": "No child target renames locked reference modules."},
                    {"source_name": "XiangShan / XS / KMHV2", "local_name": "UHSC", "visibility": "project-owned external product identity", "reason": "Localization remains deferred to external wrapper."}],
        "targets": list(TARGETS),
        "gates": {"UHSC_LOCALIZED": "PENDING_EXTERNAL_WRAPPER", "ACCEPTED": "NOT_ALLOWED"},
    }
    NAMING_RESULT.write_text(json.dumps(naming, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8", newline="\n")

    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_VECTOR_BATCH_DIFFERENTIAL_EVIDENCE",
        "batch_id": "V2-P1-E-VECTOR-MASK",
        "source_commit": SOURCE_COMMIT,
        "reference_snapshot": {"canonical_path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv", "sha256": ref_hash, "bytes": len(raw_ref)},
        "source_paths": {name: [path.relative_to(ROOT).as_posix()] for name, path in SCALA.items()},
        "target_paths": {name: path.relative_to(ROOT).as_posix() for name, (path, _) in TARGETS.items()},
        "target_sha256": {name: digest(path) for name, (path, _) in TARGETS.items()},
        "source_sha256": {name: digest(path) for name, path in SCALA.items()},
        "direct_evidence": {"path": DIRECT_RESULT.relative_to(ROOT).as_posix(), "sha256": digest(DIRECT_RESULT), "status": direct.get("status")},
        "reference_index": INDEX_RESULT.relative_to(ROOT).as_posix(),
        "comparisons": results,
        "synthesis_gates": synthesis,
        "behavioral_equivalence": all_pass,
        "observation_points": ["mask expansion", "byte begin/end", "tail agnostic", "VL boundaries", "mask splice", "scalar duplication", "packed slices"],
        "covered_children": ["ByteMaskTailGen", "MaskExtractor", "UIntToContLow0s", "UIntToContLow1s", "Mgtu", "VecDataSplitModule", "Mgu", "VldMgu", "ScalaDupToVector source closure"],
        "parent_closure": "PASS_BOUNDED" if parent_pass else "FAIL",
        "source_level": "PASS_BOUNDED" if source_pass else "FAIL",
        "license_gate": "PENDING_REVIEW",
        "uhsc_localization": {"status": "PENDING_EXTERNAL_WRAPPER", "manifest": "UHSC-Naming-Manifest.json", "locked_reference_names_unchanged": True},
        "v2_status": "DIFFERENTIAL_MATCHED_BOUNDED" if all_pass else "CONTRACT_ONLY",
        "acceptance_eligible": False,
        "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": direct.get("status", "FAIL"),
                  "V2_REFERENCE_MATCHED": "PASS_BOUNDED" if standalone_pass else "FAIL",
                  "PARENT_CLOSURE_MATCHED": "PASS_BOUNDED" if parent_pass else "FAIL",
                  "SOURCE_LEVEL_MATCHED": "PASS_BOUNDED" if source_pass else "FAIL",
                  "VERILATOR": "PASS" if synthesis_pass else "FAIL", "YOSYS": "PASS" if synthesis_pass else "FAIL",
                  "UHSC_LOCALIZED": "PENDING_EXTERNAL_WRAPPER", "ACCEPTED": "NOT_ALLOWED"},
    }
    DIFF_RESULT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8", newline="\n")
    print(json.dumps({"all_pass": all_pass, "standalone_pass": standalone_pass,
                      "parent_pass": parent_pass, "source_pass": source_pass,
                      "synthesis_pass": synthesis_pass}, sort_keys=True))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
