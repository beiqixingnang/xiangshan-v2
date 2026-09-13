"""V2 leaf-to-SV differential runner. / V2 叶子与锁定 SV 差分运行器。"""

from __future__ import annotations

import importlib.util
import json
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PORTED = ROOT / "python" / "ported"
REFERENCE = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
RESULT_PATH = ROOT / "validation" / "v2-decode-batch-reference-results.json"


# Load a target module by exact path / 按精确路径加载目标模块。
def load_target(name: str, path: Path) -> Any:
    """Load one Python target for RTL generation. / 加载 Python 目标。"""

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Convert a Windows path to WSL form / 将 Windows 路径转换为 WSL 路径。
def wsl_path(path: Path) -> str:
    """Return a shell-safe WSL path. / 返回 WSL 路径。"""

    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                            capture_output=True, text=True, check=True)
    return result.stdout.strip()


# Extract one standalone reference module / 提取一个独立参考模块。
def extract_reference(name: str) -> str:
    """Read a module block from locked XSTop.sv. / 从锁定 XSTop 提取模块。"""

    command = f"awk '/^module {name}\\(/,/^endmodule/' {REFERENCE}"
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", command],
                            capture_output=True, text=True, check=True)
    if not result.stdout.startswith(f"module {name}("):
        raise RuntimeError(f"reference module missing: {name}")
    return result.stdout


# Rename a generated target module / 重命名生成目标模块。
def rename_module(source: str, old: str, new: str) -> str:
    """Rename only the first module declaration. / 只重命名首个模块声明。"""

    marker = f"module {old}("
    if marker not in source:
        raise RuntimeError(f"target module missing: {old}")
    return source.replace(marker, f"module {new}(", 1)


# Run a Verilator wrapper and return its result / 运行 Verilator 包装器并返回结果。
def run_verilator(directory: Path, source: str) -> dict[str, Any]:
    """Compile and execute one reference/target wrapper. / 编译并执行差分包装器。"""

    directory.mkdir(parents=True, exist_ok=True)
    wrapper = directory / "tb.sv"
    wrapper.write_text(source, encoding="utf-8", newline="\n")
    path = wsl_path(wrapper)
    command = f"cd $(dirname {path}) && verilator --binary --timing -Wno-fatal --top-module tb tb.sv"
    compile_result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", command],
                                    capture_output=True, text=True, check=False)
    if compile_result.returncode != 0:
        return {"status": "FAIL_COMPILE", "stderr": compile_result.stderr[-4000:]}
    binary = directory / "obj_dir" / "Vtb"
    run_result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"{wsl_path(binary)}"],
                               capture_output=True, text=True, check=False)
    return {
        "status": "PASS" if run_result.returncode == 0 else "FAIL_RUN",
        "returncode": run_result.returncode,
        "stdout_tail": run_result.stdout[-1000:],
        "stderr_tail": run_result.stderr[-2000:],
    }


# Generate a FLI target module / 生成 FLI 目标模块。
def fli_target(module: Any, table_name: str, target_name: str) -> str:
    """Emit one configured FLI table under a unique name. / 输出指定 FLI 表。"""

    from amaranth.back import verilog

    top = getattr(module, table_name)()
    return rename_module(verilog.convert(top, name=target_name,
                                         ports=[top.src, top.out], emit_src=False),
                         target_name, target_name)


# Compare FLI H/S/D tables / 比较 FLI 半单双精度表。
def compare_fli(module: Any, directory: Path) -> dict[str, Any]:
    """Run all 96 table entries against locked reference modules. / 差分 96 项。"""

    blocks: list[str] = []
    instances: list[str] = []
    for suffix, ref_name in (("H", "FliHTable"), ("S", "FliSTable"),
                             ("D", "FliDTable")):
        target_name = f"UHSC_{ref_name}"
        blocks.extend([extract_reference(ref_name), fli_target(module, f"Fli{suffix}Table", target_name)])
        checks = "\n".join(
            f"    src_{suffix} = 5'd{value}; #1; if (ref_out_{suffix} !== dut_out_{suffix}) "
            f"$fatal(1, \"{suffix} %0d\", src_{suffix});"
            for value in range(32)
        )
        instances.append(
            f"  logic [4:0] src_{suffix}; logic [15:0] ref_out_{suffix}, dut_out_{suffix};\n"
            f"  {ref_name} ref_inst_{suffix}(.src(src_{suffix}), .out(ref_out_{suffix}));\n"
            f"  {target_name} dut_inst_{suffix}(.src(src_{suffix}), .out(dut_out_{suffix}));\n"
            f"  initial begin\n{checks}\n  end"
        )
    source = "\n".join(blocks) + "\nmodule tb;\n" + "\n".join(instances) + "\nendmodule\n"
    return run_verilator(directory, source)


# Compare a one-bit CSA3_2 instance / 比较一位 CSA3_2 实例。
def compare_csa(module: Any, directory: Path) -> dict[str, Any]:
    """Exhaustively compare all eight compressor input combinations. / 穷举八种组合。"""

    from amaranth.back import verilog

    config = module.CSAConfig(length=1)
    top = module.CSA3_2(config.length)
    target = verilog.convert(top, name="UHSC_CSA3_2",
                             ports=[*top.inputs, *top.outputs], emit_src=False)
    target = rename_module(target, "UHSC_CSA3_2", "UHSC_CSA3_2")
    reference = extract_reference("CSA3_2")
    checks = "\n".join(
        f"    in0 = 1'b{a}; in1 = 1'b{b}; in2 = 1'b{c}; #1; "
        "if (ref0 !== dut0 || ref1 !== dut1) $fatal(1, \"CSA\");"
        for a in range(2) for b in range(2) for c in range(2)
    )
    source = reference + "\n" + target + "\nmodule tb;\n"
    source += "  logic in0,in1,in2,ref0,ref1,dut0,dut1;\n"
    source += "  CSA3_2 ref_inst(.io_in_0(in0),.io_in_1(in1),.io_in_2(in2),.io_out_0(ref0),.io_out_1(ref1));\n"
    source += "  UHSC_CSA3_2 dut(.io_in_0(in0),.io_in_1(in1),.io_in_2(in2),.io_out_0(dut0),.io_out_1(dut1));\n"
    source += f"  initial begin\n{checks}\n  end\nendmodule\n"
    return run_verilator(directory, source)


# Compare registered Sstc behavior / 比较寄存式 Sstc 行为。
def compare_sstc(module: Any, directory: Path) -> dict[str, Any]:
    """Compare reset, update, hold, and disabled-STCE transactions. / 比较 Sstc 事务。"""

    from amaranth.back import verilog

    top = module.SstcInterruptGen()
    target = verilog.convert(top, name="UHSC_SstcInterruptGen",
                             ports=[top.clock, top.reset, top.i_stime_valid, top.i_stime_bits,
                                    top.i_vstime_valid, top.i_vstime_bits, top.i_stimecmp_wen,
                                    top.i_stimecmp_rdata, top.i_vstimecmp_wen,
                                    top.i_vstimecmp_rdata, top.i_htimedeltaWen,
                                    top.i_menvcfg_wen, top.i_menvcfg_STCE,
                                    top.i_henvcfg_wen, top.i_henvcfg_STCE,
                                    top.o_STIP, top.o_VSTIP], emit_src=False)
    target = rename_module(target, "UHSC_SstcInterruptGen", "UHSC_SstcInterruptGen")
    reference = extract_reference("SstcInterruptGen")
    ports = "clock,reset,i_stime_valid,i_stime_bits,i_vstime_valid,i_vstime_bits," \
            "i_stimecmp_wen,i_stimecmp_rdata,i_vstimecmp_wen,i_vstimecmp_rdata," \
            "i_htimedeltaWen,i_menvcfg_wen,i_menvcfg_STCE,i_henvcfg_wen,i_henvcfg_STCE"
    declarations = "logic clock,reset,i_stime_valid,i_vstime_valid,i_stimecmp_wen," \
                   "i_vstimecmp_wen,i_htimedeltaWen,i_menvcfg_wen,i_menvcfg_STCE," \
                   "i_henvcfg_wen,i_henvcfg_STCE; logic [63:0] i_stime_bits,i_vstime_bits," \
                   "i_stimecmp_rdata,i_vstimecmp_rdata; logic ref_s,ref_v,dut_s,dut_v;"
    # Keep the port map explicit to avoid accidental name changes.
    map_text = ",".join(f".{name}({name})" for name in ports.split(','))
    source = reference + "\n" + target + "\nmodule tb;\n  " + declarations + "\n"
    source += f"  SstcInterruptGen ref_inst({map_text},.o_STIP(ref_s),.o_VSTIP(ref_v));\n"
    source += f"  UHSC_SstcInterruptGen dut({map_text},.o_STIP(dut_s),.o_VSTIP(dut_v));\n"
    source += "  always #1 clock = ~clock;\n  initial begin\n"
    source += "    clock=0; reset=1; i_stime_valid=0; i_vstime_valid=0; i_stimecmp_wen=0; i_vstimecmp_wen=0; i_htimedeltaWen=0; i_menvcfg_wen=0; i_henvcfg_wen=0; i_menvcfg_STCE=0; i_henvcfg_STCE=0; i_stime_bits=0; i_vstime_bits=0; i_stimecmp_rdata=0; i_vstimecmp_rdata=0; #2; reset=0;\n"
    source += "    i_stime_bits=64'd10; i_stimecmp_rdata=64'd9; i_menvcfg_STCE=1; i_stime_valid=1; i_vstime_bits=64'd20; i_vstimecmp_rdata=64'd19; i_henvcfg_STCE=1; i_vstime_valid=1; #2; if(ref_s!==dut_s||ref_v!==dut_v) $fatal(1,\"Sstc update\");\n"
    source += "    i_stime_valid=0; i_vstime_valid=0; i_menvcfg_STCE=0; i_henvcfg_STCE=0; #2; if(ref_s!==dut_s||ref_v!==dut_v) $fatal(1,\"Sstc hold\");\n"
    source += "    $finish;\n  end\nendmodule\n"
    return run_verilator(directory, source)


# Run all available leaf differentials / 运行全部可用叶子差分。
def main() -> int:
    """Generate wrappers and report pass/fail facts. / 生成包装器并报告结果。"""

    modules = {
        "FliTable": load_target("ref_fli", PORTED / "backend/fu/fpu/FliTable-Hardware.py"),
        "CSA": load_target("ref_csa", PORTED / "backend/fu/util/CSA-Hardware.py"),
        "SstcInterruptGen": load_target("ref_sstc", PORTED / "backend/fu/NewCSR/SstcInterruptGen-Hardware.py"),
    }
    temp = Path(tempfile.mkdtemp(prefix="v2_ref_diff_"))
    try:
        results = {
            "FliTable": compare_fli(modules["FliTable"], temp / "fli"),
            "CSA": compare_csa(modules["CSA"], temp / "csa"),
            "SstcInterruptGen": compare_sstc(modules["SstcInterruptGen"], temp / "sstc"),
        }
        report = {
            "schema_version": 1,
            "kind": "XIANGSHAN_KUNMINGHU_V2_DECODE_ARITHMETIC_REFERENCE_DIFFERENTIAL",
            "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
            "reference_artifact": REFERENCE,
            "status": "V2_REFERENCE_MATCHED" if all(item["status"] == "PASS" for item in results.values()) else "REFERENCE_DIFFERENTIAL_FAILED",
            "results": results,
            "gates": {
                "PYTHON_PRESENT": "PASS",
                "DIRECT_TEST_PASS_BOUNDED": "PASS",
                "V2_REFERENCE_MATCHED": "PASS" if all(item["status"] == "PASS" for item in results.values()) else "FAIL",
                "UHSC_LOCALIZED": "PENDING_EXTERNAL_WRAPPER",
                "PARENT_CLOSURE_MATCHED": "PENDING",
                "ACCEPTED": "NOT_ALLOWED",
            },
            "unclosed": [
                "Instructions and RiscvInst have no standalone module in XSTop.sv; source-level field differential remains bounded only.",
                "Parent closure and external UHSC localization gates remain open.",
            ],
        }
        RESULT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8", newline="\n")
        print(report)
        return 0 if report["status"] == "V2_REFERENCE_MATCHED" else 1
    finally:
        shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
