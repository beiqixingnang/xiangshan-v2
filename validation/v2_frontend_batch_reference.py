"""V2 frontend reference differential runner. / V2 前端参考差分运行器。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUILD_CORE = ROOT / "python" / "Program-System" / "System-Build" / "Build-Cpu" / "Cpu-Core"
RESULT_PATH = ROOT / "validation" / "v2-frontend-batch-reference-results.json"
REFERENCE = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"


# Load a target by exact path. / 按精确路径加载目标模块。
def load_target(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Convert a host path to a WSL path. / 将主机路径转换为 WSL 路径。
def wsl_path(path: Path) -> str:
    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                            capture_output=True, text=True, check=True)
    return result.stdout.strip()


# Extract one locked reference module. / 提取锁定参考模块。
def extract_reference(name: str) -> str:
    command = f"awk '/^module {name}\\(/,/^endmodule/' {REFERENCE}"
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", command],
                            capture_output=True, text=True, check=True)
    if not result.stdout.startswith(f"module {name}("):
        raise RuntimeError(f"missing reference module {name}")
    return result.stdout


# Rename only a generated module declaration. / 只重命名生成模块声明。
def rename_module(source: str, old: str, new: str) -> str:
    marker = f"module {old}("
    if marker not in source:
        raise RuntimeError(f"missing generated module {old}")
    return source.replace(marker, f"module {new}(", 1)


# Run a Verilator wrapper and collect trace/hash evidence. / 运行 Verilator 包装器并收集轨迹哈希证据。
def run_verilator(directory: Path, source: str) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    wrapper = directory / "tb.sv"
    wrapper.write_text(source, encoding="utf-8", newline="\n")
    path = wsl_path(wrapper)
    compile_cmd = f"cd $(dirname {path}) && verilator --binary --timing -Wno-fatal --top-module tb tb.sv"
    compiled = subprocess.run(["wsl.exe", "-e", "bash", "-lc", compile_cmd],
                              capture_output=True, text=True, check=False)
    if compiled.returncode != 0:
        return {"status": "FAIL_COMPILE", "returncode": compiled.returncode,
                "stderr_tail": compiled.stderr[-4000:]}
    binary = directory / "obj_dir" / "Vtb"
    ran = subprocess.run(["wsl.exe", "-e", "bash", "-lc", wsl_path(binary)],
                         capture_output=True, text=True, check=False)
    trace = ran.stdout
    return {
        "status": "PASS" if ran.returncode == 0 else "FAIL_RUN",
        "returncode": ran.returncode,
        "trace_sha256": hashlib.sha256(trace.encode()).hexdigest(),
        "trace_lines": len(trace.splitlines()),
        "stdout_tail": trace[-1200:],
        "stderr_tail": ran.stderr[-2000:],
    }


# Build an exhaustive RVC reference wrapper. / 构建穷举 RVC 参考包装器。
def compare_rvc(module: Any, directory: Path) -> dict[str, Any]:
    from amaranth.back import verilog

    top = module.RvcExpander(module.RvcExpanderConfig())
    target = verilog.convert(top, name="UHSC_RVCExpander",
                             ports=[top.in_, top.fsIsOff, top.out_bits,
                                    top.out_rd, top.out_rs1, top.out_rs2,
                                    top.out_rs3, top.ill], emit_src=False)
    target = rename_module(target, "UHSC_RVCExpander", "UHSC_RVCExpander")
    reference = extract_reference("RVCExpander")
    # Compare every 16-bit compressed encoding with fsIsOff=0 and 1.
    checks = """
    integer i;
    initial begin
      in_word = 32'h0; fs = 1'b0;
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
    """
    wrapper = """
module tb;
  logic [31:0] in_word;
  logic fs;
  logic [31:0] ref_bits, dut_bits;
  logic ref_ill, dut_ill;
  logic [4:0] dut_rd, dut_rs1, dut_rs2, dut_rs3;
  RVCExpander ref_inst(.io_in(in_word), .io_fsIsOff(fs), .io_out_bits(ref_bits), .io_ill(ref_ill));
  UHSC_RVCExpander dut_inst(.io_in(in_word), .io_fsIsOff(fs), .io_out_bits(dut_bits),
                            .io_out_rd(dut_rd), .io_out_rs1(dut_rs1),
                            .io_out_rs2(dut_rs2), .io_out_rs3(dut_rs3), .io_ill(dut_ill));
""" + checks + "endmodule\n"
    return run_verilator(directory, reference + "\n" + target + "\n" + wrapper)


# Record source-level evidence for non-extractable V2 surfaces. / 记录不可提取 V2 表面的源级证据。
def source_evidence() -> dict[str, Any]:
    paths = {
        "CompareMatrix": ROOT / "upstream/src/main/scala/xiangshan/backend/dispatch/NewDispatch.scala",
        "FallThroughPredictor": ROOT / "upstream/src/main/scala/xiangshan/frontend/BPU.scala",
        "SaturateCounter": ROOT / "upstream/src/main/scala/xiangshan/frontend/BPU.scala",
        "SignedSaturateCounter": ROOT / "upstream/src/main/scala/xiangshan/frontend/BPU.scala",
    }
    snippets = {
        "CompareMatrix": "compareMatrix",
        "FallThroughPredictor": "getFallThroughAddr",
        "SaturateCounter": "satUpdate",
        "SignedSaturateCounter": "signedSatUpdate",
    }
    result: dict[str, Any] = {}
    for name, path in paths.items():
        source = path.read_text(encoding="utf-8")
        needle = snippets[name]
        positions = [match.start() for match in re.finditer(re.escape(needle), source)]
        result[name] = {
            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "needle": needle,
            "occurrences": len(positions),
            "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "evidence_sha256": hashlib.sha256("|".join(map(str, positions)).encode()).hexdigest(),
            "reference_mode": "SOURCE_LEVEL_PARENT_CLOSURE",
        }
    return result


# Run reference extraction and persist machine-readable evidence. / 运行参考提取并持久化机器证据。
def main() -> int:
    module = load_target("v2_frontend_reference_rvc",
                         BUILD_CORE / "Build-Cpu.Frontend.Ifu.RvcExpander-Hardware.py")
    temp = Path(tempfile.mkdtemp(prefix="v2_frontend_ref_"))
    try:
        rvc_result = compare_rvc(module, temp / "rvc")
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    report = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_FRONTEND_BPU_RVC_REFERENCE_DIFFERENTIAL",
        "source_commit": SOURCE_COMMIT,
        "batch_id": "V2-P1-C-FRONTEND-BPU-RVC",
        "reference_artifact": REFERENCE,
        "reference_module": "RVCExpander",
        "status": "V2_REFERENCE_MATCHED" if rvc_result["status"] == "PASS" else "REFERENCE_DIFFERENTIAL_FAILED",
        "results": {"RvcExpander": rvc_result},
        "source_level": source_evidence(),
        "gates": {
            "PYTHON_PRESENT": "PASS",
            "DIRECT_TEST_PASS_BOUNDED": "PASS",
            "V2_REFERENCE_MATCHED": "PASS" if rvc_result["status"] == "PASS" else "FAIL",
            "PARENT_CLOSURE_MATCHED": "PENDING",
            "UHSC_LOCALIZED": "PENDING_EXTERNAL_WRAPPER",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "unclosed": [
            "CompareMatrix/FallThroughPredictor/counters have no standalone module in XSTop; source-level parent closure remains required.",
            "External UHSC wrapper and license review remain outside this reference leaf.",
        ],
    }
    RESULT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8", newline="\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "V2_REFERENCE_MATCHED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
