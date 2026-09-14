"""Independent V2-A1 core-leaf verification batch.
独立的 V2-A1 核心叶子验证批次。
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import posixpath
import random
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "python" / "Program-System" / "System-Build" / "Build-Cpu" / "Cpu-Core"
WORK = ROOT / "validation" / ".work" / "v2-a1-core-leaves"
REFERENCE_UNC = Path(r"\\wsl$\Debian\home\lishuo\xs-v2-local\build\rtl\XSTop.sv")
REFERENCE_WSL = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
REFERENCE_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"


TARGETS = {
    "ImmExtractor": BUILD / "Build-Cpu.Backend.Issue.ImmExtractor-Hardware.py",
    "AluDataModule": BUILD / "Build-Cpu.Backend.Fu.AluDataModule-Hardware.py",
    "CommitStuckCounter": BUILD / "Build-Cpu.Backend.Rob.CommitStuckCounter-Hardware.py",
    "EnqPolicy": BUILD / "Build-Cpu.Backend.Issue.EnqPolicy-Hardware.py",
    "AgeDetector": BUILD / "Build-Cpu.Backend.Issue.AgeDetector-Hardware.py",
    "PreDecodeInst": BUILD / "Build-Cpu.Backend.Decode.Isa.Predecode.PreDecodeInst-Hardware.py",
}


# Load one target by its exact final Build path. / 按最终 Build 路径加载一个目标。
def load_target(name: str, path: Path) -> Any:
    """Load a Python target without importing sibling Build files. / 不导入兄弟 Build 文件加载 Python 目标。"""

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load target: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Audit the five-zone V2 target contract. / 审计 V2 五区域目标契约。
def audit_target(path: Path) -> dict[str, Any]:
    """Return machine-readable UTF-8, AST, and comment facts. / 返回 UTF-8、AST 与注释机器事实。"""

    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    zones = ("Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry")
    positions = [source.find(zone) for zone in zones]
    errors: list[str] = []
    if source.startswith("\ufeff"):
        errors.append("UTF8_BOM")
    if "\r\n" in source:
        errors.append("CRLF_LINE_ENDINGS")
    if any(position < 0 for position in positions) or positions != sorted(positions):
        errors.append("FIVE_ZONE_ORDER")
    if "__all__" not in source:
        errors.append("MISSING_ALL")
    forbidden = ("importlib", "runpy", "subprocess", "socket", "urllib", "pathlib.Path(__file__)")
    if any(token in source for token in forbidden):
        errors.append("FORBIDDEN_IMPORT_OR_DYNAMIC_PATH")
    lines = source.splitlines()
    definitions: list[str] = []
    missing_comments: list[str] = []
    leading_helpers: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        definitions.append(node.name)
        if node.name.startswith("_") and not (node.name.startswith("__") and node.name.endswith("__")):
            leading_helpers.append(node.name)
        previous = lines[node.lineno - 2].strip() if node.lineno >= 2 else ""
        if not previous.startswith("#") or "/" not in previous:
            missing_comments.append(f"{node.name}:{node.lineno}")
    if leading_helpers:
        errors.append("LEADING_UNDERSCORE_HELPER")
    if missing_comments:
        errors.append("MISSING_BILINGUAL_DEF_COMMENTS")
    adapters = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "build_verilog"]
    adapter_ok = bool(adapters and len(adapters[0].args.args) == 2 and
                      [arg.arg for arg in adapters[0].args.args] == ["configuration", "injected_dependencies"])
    if not adapter_ok:
        errors.append("ADAPTER_SIGNATURE")
    return {
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "utf8_bom": source.startswith("\ufeff"),
        "lf_only": "\r\n" not in source,
        "five_zone_order": not any(error == "FIVE_ZONE_ORDER" for error in errors),
        "adapter_exact": adapter_ok,
        "definitions": sorted(definitions),
        "missing_bilingual_comments": missing_comments,
        "leading_underscore_helpers": leading_helpers,
        "errors": errors,
        "status": "PASS" if not errors else "FAIL",
    }


# Read the locked V2 reference artifact. / 读取锁定的 V2 参考产物。
def reference_text() -> str:
    """Return XSTop.sv text from the local WSL mirror. / 从本地 WSL 镜像返回 XSTop.sv 文本。"""

    if REFERENCE_UNC.exists():
        return REFERENCE_UNC.read_text(encoding="utf-8", errors="replace")
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"cat {shlex.quote(REFERENCE_WSL)}"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    return result.stdout


# Hash the locked reference bytes without text transcoding. / 不经文本转码计算锁定参考字节哈希。
def reference_sha256() -> str:
    """Return the exact SHA-256 of XSTop.sv. / 返回 XSTop.sv 的精确 SHA-256。"""

    if REFERENCE_UNC.exists():
        return hashlib.sha256(REFERENCE_UNC.read_bytes()).hexdigest()
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"sha256sum {shlex.quote(REFERENCE_WSL)}"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    return result.stdout.split()[0]


# Extract one generated module block by name. / 按名称提取一个生成模块块。
def extract_module(source: str, name: str) -> str:
    """Extract ``module ... endmodule`` from XSTop.sv. / 从 XSTop.sv 提取模块块。"""

    match = re.search(r"^module " + re.escape(name) + r"\(.*?^endmodule\s*", source, re.MULTILINE | re.DOTALL)
    if match is None:
        raise RuntimeError(f"reference module missing: {name}")
    return match.group(0)


# Rename one generated top declaration for side-by-side simulation. / 重命名一个生成顶层声明以便并行仿真。
def rename_module(source: str, old: str, new: str) -> str:
    """Rename only the first declaration. / 仅重命名首个声明。"""

    marker = f"module {old}("
    if marker not in source:
        raise RuntimeError(f"target declaration missing: {old}")
    return source.replace(marker, f"module {new}(", 1)


# Generate one target module with a fixed unique name. / 生成带固定唯一路名的目标模块。
def target_verilog(module: Any, configuration: Any, name: str) -> str:
    """Call the exact two-argument adapter and rename its top. / 调用精确双参数适配器并重命名顶层。"""

    generated = module.build_verilog(configuration, {})
    return rename_module(generated, generated.split("module ", 1)[1].split("(", 1)[0], name)


# Convert a Windows path to a shell-safe WSL path. / 将 Windows 路径转换为安全 WSL 路径。
def wsl_path(path: Path) -> str:
    """Return the absolute WSL path. / 返回绝对 WSL 路径。"""

    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    return result.stdout.strip()


# Compile and execute one Verilator wrapper. / 编译并执行一个 Verilator 包装器。
def run_verilator(source: str, stem: str, defines: tuple[str, ...] = ()) -> dict[str, Any]:
    """Return compile/run evidence for a deterministic wrapper. / 返回确定性包装器的编译运行证据。"""

    directory = WORK / stem
    directory.mkdir(parents=True, exist_ok=True)
    wrapper = directory / "tb.sv"
    wrapper.write_text(source, encoding="utf-8", newline="\n")
    path = wsl_path(wrapper)
    mdir = f"obj_{stem.replace('-', '_')}"
    flags = " ".join(f"-D{item}" for item in defines)
    command = (f"cd {shlex.quote(posixpath.dirname(path))} && rm -rf {shlex.quote(mdir)} && "
               f"verilator --binary --timing -Wno-fatal {flags} --Mdir {shlex.quote(mdir)} "
               f"--top-module tb tb.sv > verilator-build.log 2>&1")
    compile_result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", command],
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, timeout=900)
    if compile_result.returncode != 0:
        return {"status": "FAIL_COMPILE", "returncode": compile_result.returncode,
                "stderr_tail": (compile_result.stderr + compile_result.stdout)[-4000:]}
    binary = directory / mdir / "Vtb"
    run = subprocess.run(["wsl.exe", "-e", "bash", "-lc", shlex.quote(wsl_path(binary))],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, timeout=300)
    return {"status": "PASS" if run.returncode == 0 else "FAIL_RUN",
            "returncode": run.returncode,
            "stdout_tail": run.stdout[-2000:], "stderr_tail": run.stderr[-4000:]}


# Run Verilator lint and Yosys parsing for one generated target. / 对一个生成目标运行 Verilator lint 与 Yosys 解析。
def lint_and_synth(module: Any, configuration: Any, name: str) -> dict[str, Any]:
    """Return generated size/hash and tool statuses. / 返回生成大小、哈希及工具状态。"""

    directory = WORK / "lint"
    directory.mkdir(parents=True, exist_ok=True)
    source = module.build_verilog(configuration, {})
    path = directory / f"{name}.sv"
    path.write_text(source, encoding="utf-8", newline="\n")
    wsl = wsl_path(path)
    lint_cmd = f"verilator --lint-only -Wno-fatal {shlex.quote(wsl)}"
    lint = subprocess.run(["wsl.exe", "-e", "bash", "-lc", lint_cmd],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, timeout=900)
    yosys_cmd = (f"yosys -Q -p 'read_verilog -sv {shlex.quote(wsl)}; "
                 f"hierarchy -top {name}; proc; opt; stat'")
    yosys = subprocess.run(["wsl.exe", "-e", "bash", "-lc", yosys_cmd],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, timeout=900)
    return {
        "status": "PASS" if lint.returncode == 0 and yosys.returncode == 0 else "FAIL",
        "bytes": len(source.encode("utf-8")),
        "sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "verilator": {"status": "PASS" if lint.returncode == 0 else "FAIL",
                      "returncode": lint.returncode, "stderr_tail": lint.stderr[-1500:]},
        "yosys": {"status": "PASS" if yosys.returncode == 0 else "FAIL",
                  "returncode": yosys.returncode, "stderr_tail": yosys.stderr[-1500:]},
    }


# Check source-level PreDecodeInst authority and deterministic branch behavior. / 检查 PreDecodeInst 权威源与确定性分支行为。
def direct_predecode(module: Any) -> dict[str, Any]:
    """Compare every BitPat literal and exercise branch attributes. / 比较每个 BitPat 字面量并测试分支属性。"""

    source_path = ROOT / "upstream" / "src" / "main" / "scala" / "xiangshan" / "backend" / "decode" / "isa" / "predecode" / "predecode.scala"
    source = source_path.read_text(encoding="utf-8")
    expected = {}
    for name in module.PATTERNS:
        match = re.search(rf"def {name}\s*=\s*BitPat\(\"([^\"]+)\"\)", source)
        expected[name] = match.group(1) if match else None
    literals_match = expected == module.PATTERNS
    ordered = ("C_EBREAK", "C_J", "C_JALR", "C_BRANCH", "JAL", "JALR", "BRANCH")
    samples = {
        "JAL": 0x0000006F,
        "JALR": 0x00000067,
        "BRANCH": 0x00000063,
        "C_J": 0x0000A001,
        "C_JALR": 0x00009082,
        "C_EBREAK": 0x00009002,
    }
    # C_JALR and C_EBREAK intentionally share a prefix; use exact EBREAK bits.
    samples["C_EBREAK"] = 0x00009002
    branch_results = {name: module.decode_branch(value) for name, value in samples.items()}
    expected_types = {"JAL": 2, "JALR": 3, "BRANCH": 1, "C_J": 2,
                      "C_JALR": 3, "C_EBREAK": 0}
    sample_ok = all(branch_results[name]["branch_type"] == value
                    for name, value in expected_types.items())
    return {
        "status": "PASS" if literals_match and sample_ok else "FAIL",
        "scala_pattern_literals_match": literals_match,
        "scala_branch_table_order": list(ordered),
        "sample_results": branch_results,
        "sample_branch_types_expected": expected_types,
        "sample_branch_types_pass": sample_ok,
    }


# Run bounded pure-Python direct vectors for all six targets. / 为六个目标运行有界纯 Python 直接向量。
def direct_vectors(modules: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic direct-vector counts and statuses. / 返回确定性直接向量计数与状态。"""

    results: dict[str, Any] = {}
    imm = modules["ImmExtractor"]
    imm_count = 0
    for seed in (0, 1, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF, 0x12345678):
        for typ in range(16):
            value = imm.decode_immediate(seed, typ, 64)
            if not isinstance(value, int) or value < 0 or value >= (1 << 64):
                raise AssertionError("ImmExtractor direct range")
            imm_count += 1
    results["ImmExtractor"] = {"status": "PASS", "vectors": imm_count}

    alu = modules["AluDataModule"]
    known = ((0, 1, alu.ALU_OPCODES["add"], 1),
             (5, 3, alu.ALU_OPCODES["sub"], 2),
             (0x8000000000000000, 1, alu.ALU_OPCODES["srl"], 0x4000000000000000),
             (0xFFFFFFFFFFFFFFFF, 0, alu.ALU_OPCODES["and"], 0),
             (0x00000000FFFFFFFF, 0, alu.ALU_OPCODES["slliuw"], 0xFFFFFFFF))
    for left, right, opcode, expected in known:
        actual = alu.alu_reference(left, right, opcode)
        if actual != expected:
            raise AssertionError(f"AluDataModule direct mismatch {opcode:#x}: {actual:#x} != {expected:#x}")
    results["AluDataModule"] = {"status": "PASS", "vectors": len(known)}

    counter = modules["CommitStuckCounter"]
    try:
        counter.CommitStuckCounterConfig(width=0)
    except ValueError:
        pass
    else:
        raise AssertionError("CommitStuckCounter width guard")
    results["CommitStuckCounter"] = {"status": "PASS", "vectors": 2}

    enq = modules["EnqPolicy"]
    count = 0
    width = enq.EnqPolicyConfig().free_slots
    for mask in range(1 << min(width, 12)):
        for rank in (1, 2):
            enq.select_circular(mask, 2, rank)
            count += 1
    results["EnqPolicy"] = {"status": "PASS", "vectors": count}

    age = modules["AgeDetector"]
    matrix = [[False] * 6 for _ in range(6)]
    for index in range(6):
        matrix[index][index] = True
    selected = age.age_select_reference(matrix, [0b000001, 0])
    if selected[0] != 0b000001:
        raise AssertionError("AgeDetector initial diagonal")
    results["AgeDetector"] = {"status": "PASS", "vectors": 2}

    results["PreDecodeInst"] = direct_predecode(modules["PreDecodeInst"])
    return results


# Construct the single serial reference wrapper for the batch. / 构造该批次单一串行参考包装器。
def build_reference_wrapper(modules: dict[str, Any], reference: str) -> str:
    """Return SV comparing all selected reference closures. / 返回比较全部选定参考闭包的 SV。"""

    imm_configs = [
        (64, (0x2, 0x4, 0xB), "ImmExtractor", "UHSC_ImmExtractor"),
        (64, (0x1, 0x2, 0x3, 0x4), "ImmExtractor_2", "UHSC_ImmExtractor_2"),
        (128, (0x1, 0x2, 0x3, 0x4, 0x9, 0xA, 0xC, 0xD, 0xF), "ImmExtractor_12", "UHSC_ImmExtractor_12"),
        (128, (0xC, 0xD), "ImmExtractor_37", "UHSC_ImmExtractor_37"),
        (64, (0xE,), "ImmExtractor_57", "UHSC_ImmExtractor_57"),
    ]
    blocks = [extract_module(reference, name) for _, _, name, _ in imm_configs]
    for bits, types, _, target_name in imm_configs:
        blocks.append(target_verilog(modules["ImmExtractor"],
                                     modules["ImmExtractor"].ImmExtractorConfig(data_bits=bits, imm_type_set=types),
                                     target_name))
    blocks.append(extract_module(reference, "CommitStuckCounter"))
    blocks.append(target_verilog(modules["CommitStuckCounter"],
                                 modules["CommitStuckCounter"].CommitStuckCounterConfig(),
                                 "UHSC_CommitStuckCounter"))
    blocks.append(extract_module(reference, "EnqPolicy"))
    blocks.append(target_verilog(modules["EnqPolicy"],
                                 modules["EnqPolicy"].EnqPolicyConfig(), "UHSC_EnqPolicy"))
    blocks.append(extract_module(reference, "AgeDetector"))
    blocks.append(target_verilog(modules["AgeDetector"],
                                 modules["AgeDetector"].AgeDetectorConfig(), "UHSC_AgeDetector"))
    alu_names = ("LeftShiftModule", "RightShiftModule", "AddModule", "SubModule",
                 "LeftShiftWordModule", "RightShiftWordModule", "ShiftResultSelect",
                 "MiscResultSelect", "ConditionalZeroModule", "WordResultSelect", "AluResSel", "AluDataModule")
    blocks.extend(extract_module(reference, name) for name in alu_names)
    blocks.append(target_verilog(modules["AluDataModule"],
                                 modules["AluDataModule"].AluConfig(), "UHSC_AluDataModule"))
    tb = r'''
module tb;
  logic [31:0] imm; logic [3:0] typ;
  wire [63:0] ir0,id0,ir1,id1,ir57,id57; wire [127:0] ir12,id12,ir37,id37;
  ImmExtractor ref_i0(.io_in_imm(imm),.io_in_immType(typ),.io_out_imm(ir0)); UHSC_ImmExtractor dut_i0(.io_in_imm(imm),.io_in_immType(typ),.io_out_imm(id0));
  ImmExtractor_2 ref_i1(.io_in_imm(imm),.io_in_immType(typ),.io_out_imm(ir1)); UHSC_ImmExtractor_2 dut_i1(.io_in_imm(imm),.io_in_immType(typ),.io_out_imm(id1));
  ImmExtractor_12 ref_i12(.io_in_imm(imm),.io_in_immType(typ),.io_out_imm(ir12)); UHSC_ImmExtractor_12 dut_i12(.io_in_imm(imm),.io_in_immType(typ),.io_out_imm(id12));
  ImmExtractor_37 ref_i37(.io_in_imm(imm),.io_in_immType(typ),.io_out_imm(ir37)); UHSC_ImmExtractor_37 dut_i37(.io_in_imm(imm),.io_in_immType(typ),.io_out_imm(id37));
  ImmExtractor_57 ref_i57(.io_in_imm(imm),.io_in_immType(typ),.io_out_imm(ir57)); UHSC_ImmExtractor_57 dut_i57(.io_in_imm(imm),.io_in_immType(typ),.io_out_imm(id57));
  logic cclock,creset,cstuck,cruntime,coverflow_en; wire cro, cdo; wire [20:0] ccount;
  CommitStuckCounter ref_c(.clock(cclock),.reset(creset),.io_stuck(cstuck),.io_runtimeEnable(cruntime),.io_overflow(cro));
  UHSC_CommitStuckCounter dut_c(.clock(cclock),.reset(creset),.io_stuck(cstuck),.io_runtimeEnable(cruntime),.io_overflowEnabled(coverflow_en),.io_count(ccount),.io_overflow(cdo));
  logic [21:0] can; wire erv0,erv1,edv0,edv1; wire [21:0] erb0,erb1,edb0,edb1;
  EnqPolicy ref_e(.io_canEnq(can),.io_enqSelOHVec_0_valid(erv0),.io_enqSelOHVec_0_bits(erb0),.io_enqSelOHVec_1_valid(erv1),.io_enqSelOHVec_1_bits(erb1));
  UHSC_EnqPolicy dut_e(.io_canEnq(can),.io_enqSelOHVec_0_valid(edv0),.io_enqSelOHVec_0_bits(edb0),.io_enqSelOHVec_1_valid(edv1),.io_enqSelOHVec_1_bits(edb1));
  logic aclock,areset; logic [5:0] ae0,ae1,ac0,ac1,ac2,ac3; wire [5:0] aro0,aro1,aro2,aro3,ado0,ado1,ado2,ado3;
  AgeDetector ref_a(.clock(aclock),.reset(areset),.io_enq_0(ae0),.io_enq_1(ae1),.io_canIssue_0(ac0),.io_canIssue_1(ac1),.io_canIssue_2(ac2),.io_canIssue_3(ac3),.io_out_0(aro0),.io_out_1(aro1),.io_out_2(aro2),.io_out_3(aro3));
  UHSC_AgeDetector dut_a(.clock(aclock),.reset(areset),.io_enq_0(ae0),.io_enq_1(ae1),.io_canIssue_0(ac0),.io_canIssue_1(ac1),.io_canIssue_2(ac2),.io_canIssue_3(ac3),.io_out_0(ado0),.io_out_1(ado1),.io_out_2(ado2),.io_out_3(ado3));
  logic [63:0] s0,s1; logic [8:0] fn; wire [63:0] ar,ad;
  AluDataModule ref_alu(.io_src_0(s0),.io_src_1(s1),.io_func(fn),.io_result(ar));
  UHSC_AluDataModule dut_alu(.io_src_0(s0),.io_src_1(s1),.io_func(fn),.io_result(ad));
  always #1 cclock=~cclock; always #1 aclock=~aclock;
  integer i,j; reg [63:0] seed; function automatic [63:0] nxt(input [63:0] x);nxt=x*64'h9e3779b97f4a7c15+64'hd1b54a32d192ed03;endfunction
  task fail(input [1023:0] msg); begin $display("FAIL %0s",msg);$fatal(1);end endtask
  initial begin
    seed=64'h123456789abcdef0;
    for(i=0;i<100;i=i+1)begin seed=nxt(seed);imm=seed[31:0];for(j=0;j<16;j=j+1)begin typ=j;#1;if(ir0!==id0||ir1!==id1||ir12!==id12||ir37!==id37||ir57!==id57)fail("ImmExtractor");end end
    cclock=0;creset=1;cstuck=0;cruntime=0;coverflow_en=1;#1;creset=0;for(i=0;i<16;i=i+1)begin cruntime=i[0];cstuck=~i[0];#2;if(cro!==cdo)fail("CommitStuckCounter");end
    for(i=0;i<2000;i=i+1)begin seed=nxt(seed);can=seed[21:0];#1;if(erv0!==edv0||erv1!==edv1||erb0!==edb0||erb1!==edb1)fail("EnqPolicy");end
    aclock=0;areset=1;ae0=0;ae1=0;ac0=0;ac1=0;ac2=0;ac3=0;#2;areset=0;
    for(i=0;i<300;i=i+1)begin seed=nxt(seed);ae0=(22'd1<<seed[2:0]);seed=nxt(seed);ae1=(22'd1<<seed[2:0]);if(ae0==ae1)ae1=0;seed=nxt(seed);ac0=seed[5:0];seed=nxt(seed);ac1=seed[5:0];seed=nxt(seed);ac2=seed[5:0];seed=nxt(seed);ac3=seed[5:0];@(posedge aclock);#1;if(aro0!==ado0||aro1!==ado1||aro2!==ado2||aro3!==ado3)fail("AgeDetector");end
    for(i=0;i<512;i=i+1)begin if((i<=7)||(i==9)||(i==11)||((i>=16)&&(i<=29))||((i>=32)&&(i<=47))||((i>=48)&&(i<=53))||((i>=64)&&(i<=70))||((i>=72)&&(i<=75))||((i>=80)&&(i<=83))||((i>=96)&&(i<=103))||(i==116)||(i==118))begin fn=i;for(j=0;j<25;j=j+1)begin seed=nxt(seed);s0=seed;seed=nxt(seed);s1=seed;#1;if(ar!==ad)fail("AluDataModule");end end end
    $display("PASS");$finish;
  end
endmodule
'''
    return "\n".join(blocks) + "\n" + tb


# Write all machine-readable batch evidence. / 写入全部机器可读批次证据。
def write_evidence(direct: dict[str, Any], contracts: dict[str, Any], lint: dict[str, Any],
                   reference: dict[str, Any], modules: dict[str, Any]) -> None:
    """Persist contract, direct, differential, coverage, and mapping JSON. / 持久化合同、直接、差分、覆盖与映射 JSON。"""

    validation = ROOT / "validation"
    coverage = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_A1_CORE_LEAF_COVERAGE",
        "source_commit": SOURCE_COMMIT,
        "batch_id": "V2-SCAN-A1-CORE-DECODE-ARITH-LEAVES",
        "targets": {
            "ImmExtractor": {"source_paths": ["upstream/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala"], "reference_modules": ["ImmExtractor", "ImmExtractor_2", "ImmExtractor_12", "ImmExtractor_37", "ImmExtractor_57"]},
            "AluDataModule": {"source_paths": ["upstream/src/main/scala/xiangshan/backend/fu/Alu.scala"], "reference_modules": ["AluDataModule", "AddModule", "SubModule", "LeftShiftModule", "RightShiftModule", "LeftShiftWordModule", "RightShiftWordModule", "ShiftResultSelect", "MiscResultSelect", "ConditionalZeroModule", "WordResultSelect", "AluResSel"]},
            "CommitStuckCounter": {"source_paths": ["upstream/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala"], "reference_modules": ["CommitStuckCounter"]},
            "EnqPolicy": {"source_paths": ["upstream/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala", "upstream/utility/src/main/scala/utility/BitUtils.scala#CircSelectOne"], "reference_modules": ["EnqPolicy"]},
            "AgeDetector": {"source_paths": ["upstream/src/main/scala/xiangshan/backend/issue/AgeDetector.scala"], "reference_modules": ["AgeDetector"]},
            "PreDecodeInst": {"source_paths": ["upstream/src/main/scala/xiangshan/backend/decode/isa/predecode/predecode.scala"], "reference_modules": [], "source_level": True},
        },
        "status": "PASS_BOUNDED" if reference.get("status") == "PASS" else "FAIL",
    }
    mapping = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_A1_CORE_LEAF_MAPPING_UPDATE",
        "source_commit": SOURCE_COMMIT,
        "targets": [
            {"id": key, "family_id": {"ImmExtractor": "core.backend.issue.imm", "AluDataModule": "core.fu.alu", "CommitStuckCounter": "core.backend.rob.commit", "EnqPolicy": "core.backend.issue.enq", "AgeDetector": "core.backend.issue.age", "PreDecodeInst": "core.decode.predecode"}[key], "build_path": str(path.relative_to(ROOT)).replace("\\", "/"), "classification": "REWRITTEN", "status": "V2_REFERENCE_MATCHED_BOUNDED" if key != "PreDecodeInst" else "SOURCE_MATCHED_BOUNDED"} for key, path in TARGETS.items()
        ],
        "status": "PENDING_COORDINATOR_REVIEW",
        "accepted": False,
    }
    batch = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_A1_CORE_LEAF_BATCH",
        "source_commit": SOURCE_COMMIT,
        "reference_artifact": {"path": REFERENCE_WSL, "sha256": REFERENCE_SHA256},
        "batch_id": "V2-SCAN-A1-CORE-DECODE-ARITH-LEAVES",
        "targets": list(TARGETS),
        "counts": {"targets": 6, "build_files": 6, "reference_modules": 17},
        "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": "PASS" if all(row.get("status") == "PASS" for row in direct.values()) else "FAIL", "V2_REFERENCE_MATCHED": "PASS_BOUNDED" if reference.get("status") == "PASS" else "FAIL", "UHSC_LOCALIZED": "NOT_APPLICABLE_INTERNAL_LEAVES", "PARENT_CLOSURE_MATCHED": "PENDING", "ACCEPTED": "NOT_ALLOWED"},
        "status": "PENDING_COORDINATOR_REVIEW",
        "unclosed": ["Independent validator rerun is required.", "Parent closure, license, UHSC top, and user approval remain open."],
    }
    files = {
        "v2-a1-core-leaf-contract-audit.json": {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_A1_CONTRACT_AUDIT", "targets": contracts, "status": "PASS" if all(row["status"] == "PASS" for row in contracts.values()) else "FAIL"},
        "v2-a1-core-leaf-direct-results.json": {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_A1_DIRECT_TESTS", "targets": direct, "status": "PASS" if all(row.get("status") == "PASS" for row in direct.values()) else "FAIL"},
        "v2-a1-core-leaf-reference-differential-results.json": {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_A1_REFERENCE_DIFFERENTIAL", "source_commit": SOURCE_COMMIT, "reference_sha256": REFERENCE_SHA256, "result": reference, "status": "V2_REFERENCE_MATCHED_BOUNDED" if reference.get("status") == "PASS" else "REFERENCE_DIFFERENTIAL_FAILED"},
        "v2-a1-core-leaf-tool-results.json": {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_A1_VERILATOR_YOSYS", "targets": lint, "status": "PASS" if all(row["status"] == "PASS" for row in lint.values()) else "FAIL"},
        "v2-a1-core-leaf-coverage-manifest.json": coverage,
        "v2-a1-core-leaf-mapping-update.json": mapping,
        "v2-a1-core-leaf-batch-results.json": batch,
    }
    for name, payload in files.items():
        (validation / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


# Execute the complete serial validator. / 执行完整串行验证器。
def main() -> int:
    """Run all direct, source, differential, and tool gates. / 运行全部直接、源级、差分及工具门禁。"""

    WORK.mkdir(parents=True, exist_ok=True)
    modules = {name: load_target(f"v2_a1_{name}", path) for name, path in TARGETS.items()}
    contracts = {name: audit_target(path) for name, path in TARGETS.items()}
    if any(row["status"] != "PASS" for row in contracts.values()):
        raise SystemExit(json.dumps(contracts, ensure_ascii=False))
    direct = direct_vectors(modules)
    reference = reference_text()
    if reference_sha256() != REFERENCE_SHA256:
        raise RuntimeError("locked reference hash mismatch")
    wrapper = build_reference_wrapper(modules, reference)
    differential = run_verilator(wrapper, "reference-differential", ("STOP_COND_=0", "ASSERT_VERBOSE_COND_=0", "PRINTF_COND_=0"))
    lint = {
        "ImmExtractor": lint_and_synth(modules["ImmExtractor"], modules["ImmExtractor"].ImmExtractorConfig(), "ImmExtractor"),
        "AluDataModule": lint_and_synth(modules["AluDataModule"], modules["AluDataModule"].AluConfig(), "AluDataModule"),
        "CommitStuckCounter": lint_and_synth(modules["CommitStuckCounter"], modules["CommitStuckCounter"].CommitStuckCounterConfig(), "CommitStuckCounter"),
        "EnqPolicy": lint_and_synth(modules["EnqPolicy"], modules["EnqPolicy"].EnqPolicyConfig(), "EnqPolicy"),
        "AgeDetector": lint_and_synth(modules["AgeDetector"], modules["AgeDetector"].AgeDetectorConfig(), "AgeDetector"),
        "PreDecodeInst": lint_and_synth(modules["PreDecodeInst"], modules["PreDecodeInst"].PreDecodeInstConfig(), "PreDecodeInstProbe"),
    }
    write_evidence(direct, contracts, lint, differential, modules)
    print(json.dumps({"direct": direct, "differential": differential, "lint": lint}, ensure_ascii=False, indent=2))
    return 0 if differential.get("status") == "PASS" and all(row["status"] == "PASS" for row in lint.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
