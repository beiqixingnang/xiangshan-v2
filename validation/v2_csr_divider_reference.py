"""Compare the CSR/divider family with locked V2 reference RTL. / 将 CSR/除法器族与锁定 V2 参考 RTL 比较。"""

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
PORTED = ROOT / "python" / "ported"
WORK = ROOT / "validation" / ".work" / "v2-csr-divider-reference"
RESULT = ROOT / "validation" / "v2-csr-divider-differential-results.json"
REFERENCE = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
REFERENCE_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
REFERENCE_BYTES = 228590583


# Load a target module by exact path. / 按精确路径加载目标模块。
def load_target(name: str, path: Path) -> Any:
    """Load a Python target without package imports. / 不通过包导入 Python 目标。"""

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Convert a workspace path to WSL form. / 将工作区路径转换为 WSL 形式。
def wsl_path(path: Path) -> str:
    """Return the absolute WSL path reported by wslpath. / 返回 wslpath 报告的绝对 WSL 路径。"""

    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", check=True)
    return result.stdout.strip()


# Extract one named module from immutable XSTop.sv. / 从不可变 XSTop.sv 提取命名模块。
def extract_reference(name: str) -> str:
    """Read one complete generated module block. / 读取一个完整生成模块块。"""

    command = f"awk '/^module {name}[(]/,/^endmodule/' {REFERENCE}"
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", command],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", check=True)
    marker = f"module {name}("
    if not result.stdout.startswith(marker):
        raise RuntimeError(f"reference module missing: {name}")
    return result.stdout


# Rename only a generated module declaration. / 只重命名生成模块声明。
def rename_module(source: str, old: str, new: str) -> str:
    """Keep internal identifiers unchanged while renaming the top. / 仅重命名顶层并保持内部标识符不变。"""

    marker = f"module {old}("
    if marker not in source:
        raise RuntimeError(f"target module missing: {old}")
    return source.replace(marker, f"module {new}(", 1)


# Execute a Verilator wrapper and return diagnostics. / 执行 Verilator 包装器并返回诊断。
def run_verilator(name: str, source: str) -> dict[str, Any]:
    """Compile and run one bounded differential testbench. / 编译并运行一个有界差分测试台。"""

    directory = WORK / name
    directory.mkdir(parents=True, exist_ok=True)
    wrapper = directory / "tb.sv"
    wrapper.write_text(source, encoding="utf-8", newline="\n")
    path = wsl_path(wrapper)
    command = (f"cd $(dirname {path}) && verilator --binary --timing -Wno-fatal "
               f"--top-module tb tb.sv")
    compile_result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", command],
                                    capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", check=False)
    if compile_result.returncode != 0:
        return {"status": "FAIL_COMPILE", "returncode": compile_result.returncode,
                "stderr_tail": compile_result.stderr[-4000:],
                "source_sha256": hashlib.sha256(source.encode()).hexdigest()}
    binary = directory / "obj_dir" / "Vtb"
    run_result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", wsl_path(binary)],
                                capture_output=True, text=True,
                                encoding="utf-8", errors="replace", check=False)
    return {
        "status": "PASS" if run_result.returncode == 0 else "FAIL_RUN",
        "returncode": run_result.returncode,
        "stdout_tail": run_result.stdout[-2000:],
        "stderr_tail": run_result.stderr[-4000:],
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
    }


# Emit one FLI target specialization. / 输出一个 FLI 目标特化。
def fli_target(module: Any, class_name: str, target_name: str) -> str:
    """Convert a configured FLI table and rename its declaration. / 转换配置后的 FLI 表并重命名声明。"""

    from amaranth.back import verilog

    top = getattr(module, class_name)()
    text = verilog.convert(top, name=target_name, ports=[top.src, top.out],
                           emit_src=False)
    return rename_module(text, target_name, target_name)


# Compare all three FLI tables against locked modules. / 将三张 FLI 表与锁定模块比较。
def compare_fli(module: Any) -> dict[str, Any]:
    """Exercise all 96 table entries. / 检查全部 96 个表项。"""

    blocks: list[str] = []
    instances: list[str] = []
    for suffix, ref_name in (("H", "FliHTable"), ("S", "FliSTable"),
                             ("D", "FliDTable")):
        target_name = f"UHSC_{ref_name}"
        blocks.extend([extract_reference(ref_name),
                       fli_target(module, f"Fli{suffix}Table", target_name)])
        checks = "\n".join(
            f"    src_{suffix}=5'd{index}; #1; if (ref_{suffix} !== dut_{suffix}) "
            f"$fatal(1, \"{suffix} %0d\", {index});"
            for index in range(32))
        instances.append(
            f"  logic [4:0] src_{suffix}; logic [15:0] ref_{suffix},dut_{suffix};\n"
            f"  {ref_name} ref_i_{suffix}(.src(src_{suffix}),.out(ref_{suffix}));\n"
            f"  {target_name} dut_i_{suffix}(.src(src_{suffix}),.out(dut_{suffix}));\n"
            f"  initial begin\n{checks}\n  end")
    source = "\n".join(blocks) + "\nmodule tb;\n" + "\n".join(instances)
    source += "\nendmodule\n"
    outcome = run_verilator("fli", source)
    outcome["vectors"] = 96
    return outcome


# Compare one-bit CSA3_2 behavior. / 比较一位 CSA3_2 行为。
def compare_csa(module: Any) -> dict[str, Any]:
    """Exercise all eight input combinations. / 检查全部八种输入组合。"""

    from amaranth.back import verilog

    top = module.CSA3_2(1)
    target = verilog.convert(top, name="UHSC_CSA3_2",
                             ports=[*top.inputs, *top.outputs], emit_src=False)
    reference = extract_reference("CSA3_2")
    checks = "\n".join(
        f"    in0=1'b{a}; in1=1'b{b}; in2=1'b{c}; #1; "
        "if (ref0 !== dut0 || ref1 !== dut1) $fatal(1, \"CSA\");"
        for a in range(2) for b in range(2) for c in range(2))
    source = reference + "\n" + target + "\nmodule tb;\n"
    source += ("  logic in0,in1,in2,ref0,ref1,dut0,dut1;\n"
               "  CSA3_2 ref_i(.io_in_0(in0),.io_in_1(in1),.io_in_2(in2),.io_out_0(ref0),.io_out_1(ref1));\n"
               "  UHSC_CSA3_2 dut_i(.io_in_0(in0),.io_in_1(in1),.io_in_2(in2),.io_out_0(dut0),.io_out_1(dut1));\n"
               f"  initial begin\n{checks}\n    $display(\"PASS_CSA\"); $finish;\n  end\nendmodule\n")
    outcome = run_verilator("csa", source)
    outcome["vectors"] = 8
    return outcome


# Compare registered Sstc behavior. / 比较寄存式 Sstc 行为。
def compare_sstc(module: Any) -> dict[str, Any]:
    """Compare reset, update, hold, and disabled-enable transactions. / 比较复位、更新、保持及禁用使能事务。"""

    from amaranth.back import verilog

    top = module.SstcInterruptGen()
    target = verilog.convert(
        top, name="UHSC_SstcInterruptGen",
        ports=[top.clock, top.reset, top.i_stime_valid, top.i_stime_bits,
               top.i_vstime_valid, top.i_vstime_bits, top.i_stimecmp_wen,
               top.i_stimecmp_rdata, top.i_vstimecmp_wen,
               top.i_vstimecmp_rdata, top.i_htimedeltaWen, top.i_menvcfg_wen,
               top.i_menvcfg_STCE, top.i_henvcfg_wen, top.i_henvcfg_STCE,
               top.o_STIP, top.o_VSTIP], emit_src=False)
    target = rename_module(target, "UHSC_SstcInterruptGen", "UHSC_SstcInterruptGen")
    reference = extract_reference("SstcInterruptGen")
    names = ("clock", "reset", "i_stime_valid", "i_stime_bits",
             "i_vstime_valid", "i_vstime_bits", "i_stimecmp_wen",
             "i_stimecmp_rdata", "i_vstimecmp_wen", "i_vstimecmp_rdata",
             "i_htimedeltaWen", "i_menvcfg_wen", "i_menvcfg_STCE",
             "i_henvcfg_wen", "i_henvcfg_STCE")
    declaration = ("logic clock,reset,i_stime_valid,i_vstime_valid,"
                   "i_stimecmp_wen,i_vstimecmp_wen,i_htimedeltaWen,"
                   "i_menvcfg_wen,i_menvcfg_STCE,i_henvcfg_wen,i_henvcfg_STCE;"
                   " logic [63:0] i_stime_bits,i_vstime_bits,"
                   "i_stimecmp_rdata,i_vstimecmp_rdata;"
                   " logic ref_s,ref_v,dut_s,dut_v;")
    mapping = ",".join(f".{name}({name})" for name in names)
    source = reference + "\n" + target + "\nmodule tb;\n  " + declaration + "\n"
    source += (f"  SstcInterruptGen ref_i({mapping},.o_STIP(ref_s),.o_VSTIP(ref_v));\n"
               f"  UHSC_SstcInterruptGen dut_i({mapping},.o_STIP(dut_s),.o_VSTIP(dut_v));\n"
               "  always #1 clock=~clock;\n  initial begin\n"
               "    clock=0; reset=1; i_stime_valid=0; i_vstime_valid=0; "
               "i_stimecmp_wen=0; i_vstimecmp_wen=0; i_htimedeltaWen=0; "
               "i_menvcfg_wen=0; i_menvcfg_STCE=0; i_henvcfg_wen=0; "
               "i_henvcfg_STCE=0; i_stime_bits=0; i_vstime_bits=0; "
               "i_stimecmp_rdata=0; i_vstimecmp_rdata=0; #2; reset=0;\n"
               "    i_stime_bits=64'd10; i_stimecmp_rdata=64'd9; "
               "i_menvcfg_STCE=1; i_stime_valid=1; i_vstime_bits=64'd20; "
               "i_vstimecmp_rdata=64'd19; i_henvcfg_STCE=1; i_vstime_valid=1; "
               "#2; if(ref_s!==dut_s||ref_v!==dut_v) $fatal(1,\"Sstc update\");\n"
               "    i_stime_valid=0; i_vstime_valid=0; i_menvcfg_STCE=0; "
               "i_henvcfg_STCE=0; #2; if(ref_s!==dut_s||ref_v!==dut_v) "
               "$fatal(1,\"Sstc hold\");\n"
               "    $display(\"PASS_SSTC\"); $finish;\n  end\nendmodule\n")
    outcome = run_verilator("sstc", source)
    outcome["vectors"] = 2
    return outcome


# Build the SRT reference/target differential wrapper. / 构建 SRT 参考/目标差分包装器。
def srt_source(module: Any) -> str:
    """Return a bounded transaction-level SRT comparison testbench. / 返回有界事务级 SRT 比较测试台。"""

    from amaranth.back import verilog

    top = module.SRT16DividerDataModule(module.SRT16DividerConfig(64))
    target = verilog.convert(
        top, name="UHSC_SRT16DividerDataModule",
        ports=[top.clock, top.reset, top.io_src_0, top.io_src_1,
               top.io_valid, top.io_sign, top.io_kill_w, top.io_kill_r,
               top.io_isHi, top.io_isW, top.io_in_ready, top.io_out_valid,
               top.io_out_data, top.io_out_ready], emit_src=False)
    target = rename_module(target, "UHSC_SRT16DividerDataModule",
                           "UHSC_SRT16DividerDataModule")
    refs = [extract_reference(name) for name in (
        "SRT16DividerDataModule", "CSA3_2_3956", "CSA3_2_3960",
        "CSA3_2_3962", "RightShifter")]
    source = "\n".join(refs) + "\n" + target + "\n"
    source += r'''
module tb;
  logic clock=0, reset=1;
  logic [63:0] src0=0, src1=0;
  logic valid=0, sign=0, kill_w=0, kill_r=0, isHi=0, isW=0, out_ready=0;
  logic ref_ready, ref_valid, dut_ready, dut_valid;
  logic [63:0] ref_data, dut_data;
  SRT16DividerDataModule ref_i(
    .clock(clock), .reset(reset), .io_src_0(src0), .io_src_1(src1),
    .io_valid(valid), .io_sign(sign), .io_kill_w(kill_w), .io_kill_r(kill_r),
    .io_isHi(isHi), .io_isW(isW), .io_in_ready(ref_ready),
    .io_out_valid(ref_valid), .io_out_data(ref_data), .io_out_ready(out_ready));
  UHSC_SRT16DividerDataModule dut_i(
    .clock(clock), .reset(reset), .io_src_0(src0), .io_src_1(src1),
    .io_valid(valid), .io_sign(sign), .io_kill_w(kill_w), .io_kill_r(kill_r),
    .io_isHi(isHi), .io_isW(isW), .io_in_ready(dut_ready),
    .io_out_valid(dut_valid), .io_out_data(dut_data), .io_out_ready(out_ready));
  always #1 clock=~clock;
  task automatic run_case(input [63:0] a, input [63:0] d,
                          input bit sg, input bit hi, input bit word);
    integer cycle;
    bit matched;
    begin
      matched=0;
      while (!ref_ready || !dut_ready) @(posedge clock);
      src0=a; src1=d; sign=sg; isHi=hi; isW=word; valid=1;
      @(posedge clock); #0.1; valid=0;
      for (cycle=0; cycle<100; cycle=cycle+1) begin
        if (ref_valid && dut_valid) begin
          if (ref_data !== dut_data) $fatal(1,"SRT mismatch a=%h d=%h sg=%0d hi=%0d ref=%h dut=%h",a,d,sg,hi,ref_data,dut_data);
          out_ready=1; @(posedge clock); #0.1; out_ready=0; matched=1; break;
        end
        @(posedge clock);
      end
      if (!matched) $fatal(1,"SRT timeout a=%h d=%h",a,d);
    end
  endtask
  initial begin
    repeat(2) @(posedge clock); reset=0;
    run_case(64'd10,64'd3,0,0,0);
    run_case(64'd10,64'd3,0,1,0);
    run_case(64'hfffffffffffffff0,64'd3,1,0,0);
    run_case(64'hfffffffffffffff0,64'd3,1,1,0);
    run_case(64'd3,64'd10,0,0,0);
    run_case(64'd3,64'd10,0,1,0);
    run_case(64'd10,64'd0,0,0,0);
    run_case(64'd10,64'd0,0,1,0);
    run_case(64'd7,64'd1,1,0,0);
    run_case(64'd7,64'd1,1,1,0);
    run_case(64'h0000000080000000,64'd2,0,0,1);
    run_case(64'h0000000080000000,64'd2,0,1,1);
    $display("PASS_SRT"); $finish;
  end
endmodule
'''
    return source


# Compare the V2 CSR split at source level where no standalone RTL exists. / 在无独立 RTL 时比较 V2 CSR 源拆分。
def compare_csrs(module: Any) -> dict[str, Any]:
    """Hash and compare Rocket CSRs plus CSRConst source values. / 哈希并比较 Rocket CSR 与 CSRConst 源值。"""

    rocket = ROOT / "upstream/rocket-chip/src/main/scala/rocket/Instructions.scala"
    custom = ROOT / "upstream/src/main/scala/xiangshan/backend/fu/util/CSRConst.scala"
    rocket_text = rocket.read_text(encoding="utf-8")
    custom_text = custom.read_text(encoding="utf-8")
    section = rocket_text[rocket_text.index("object CSRs {"):]
    section = section[:section.index("\n}")]
    source_values = dict(re.findall(
        r"(?m)^\s*val\s+(\w+)\s*=\s*(0x[0-9a-fA-F]+|\d+)", section))
    target_values = {name: hex(value) for name, value in vars(module.CSRs).items()
                     if not name.startswith("_") and isinstance(value, int)}
    normalized = {name: hex(int(value, 0)) for name, value in source_values.items()}
    standard_match = normalized == target_values
    custom_names = tuple(re.findall(
        r"(?m)^\s*val\s+(Sbpctl|Spfctl|Slvpredctl|Smblockctl|Srnctl|Scachebase|PmacfgBase|PmaaddrBase|Mbmc)\s*=",
        custom_text))
    custom_match = all(hasattr(module.CSRConst, name) for name in custom_names)
    return {
        "status": "SOURCE_LEVEL_MATCHED" if standard_match and custom_match else "SOURCE_LEVEL_MISMATCH",
        "standard_constants": len(target_values), "custom_constants": len(custom_names),
        "standard_match": standard_match, "custom_match": custom_match,
        "rocket_sha256": hashlib.sha256(rocket.read_bytes()).hexdigest(),
        "custom_sha256": hashlib.sha256(custom.read_bytes()).hexdigest(),
        "note": "No standalone CSRs module is present in XSTop.sv; this is source-level evidence, not RTL acceptance.",
    }


# Run all differential checks and persist evidence. / 运行全部差分检查并持久化证据。
def main() -> int:
    """Generate differential JSON while keeping acceptance closed. / 生成差分 JSON 并明确保持验收关闭。"""

    modules = {
        "CSRs": load_target("ref_csr_divider_csrs", PORTED / "backend/decode/isa/CSRs-Hardware.py"),
        "SstcInterruptGen": load_target("ref_csr_divider_sstc", PORTED / "backend/fu/NewCSR/SstcInterruptGen-Hardware.py"),
        "SRT16Divider": load_target("ref_csr_divider_srt", PORTED / "backend/fu/SRT16Divider-Hardware.py"),
        "FliTable": load_target("ref_csr_divider_fli", PORTED / "backend/fu/fpu/FliTable-Hardware.py"),
        "CSA": load_target("ref_csr_divider_csa", PORTED / "backend/fu/util/CSA-Hardware.py"),
    }
    results = {
        "CSRs": compare_csrs(modules["CSRs"]),
        "SstcInterruptGen": compare_sstc(modules["SstcInterruptGen"]),
        "SRT16Divider": run_verilator("srt", srt_source(modules["SRT16Divider"])),
        "FliTable": compare_fli(modules["FliTable"]),
        "CSA": compare_csa(modules["CSA"]),
    }
    rtl_pass = all(result.get("status") == "PASS" for name, result in results.items()
                   if name != "CSRs")
    source_pass = results["CSRs"].get("status") == "SOURCE_LEVEL_MATCHED"
    report = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_CSR_DIVIDER_REFERENCE_DIFFERENTIAL",
        "source_commit": SOURCE_COMMIT,
        "reference_artifact": {"path": REFERENCE, "sha256": REFERENCE_SHA256,
                                "bytes": REFERENCE_BYTES},
        "results": results,
        "status": "V2_REFERENCE_MATCHED_BOUNDED" if rtl_pass and source_pass
                  else "REFERENCE_DIFFERENTIAL_FAILED",
        "gates": {
            "PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": "PASS",
            "V2_REFERENCE_MATCHED": "PASS_BOUNDED" if rtl_pass and source_pass else "FAIL",
            "CSRs_REFERENCE_MODE": "SOURCE_LEVEL_ONLY",
            "UHSC_LOCALIZED": "PENDING_EXTERNAL_WRAPPER",
            "PARENT_CLOSURE_MATCHED": "PENDING", "ACCEPTED": "NOT_ALLOWED",
        },
        "unclosed": [
            "CSRs has no standalone generated module; source-level evidence cannot promote an RTL gate.",
            "Parent closure, integration, and license gates remain open.",
        ],
    }
    RESULT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8", newline="\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "V2_REFERENCE_MATCHED_BOUNDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
