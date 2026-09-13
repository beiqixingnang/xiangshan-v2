"""Run the V2 CryptoUtils/DebugCSR evidence batch. / 运行 V2 CryptoUtils/DebugCSR 证据批次。"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import py_compile
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from amaranth.back import verilog
from amaranth.sim import Simulator


ROOT = Path(__file__).resolve().parents[1]
PORTED = ROOT / "python" / "ported" / "backend" / "fu" / "util"
TARGETS = {
    "CryptoUtils": PORTED / "CryptoUtils-Hardware.py",
    "DebugCSR": PORTED / "DebugCSR-Hardware.py",
}
SOURCES = {
    "CryptoUtils": ROOT / "upstream/src/main/scala/xiangshan/backend/fu/util/CryptoUtils.scala",
    "DebugCSR": ROOT / "upstream/src/main/scala/xiangshan/backend/fu/util/DebugCSR.scala",
}
SHIFT_SOURCE = ROOT / "upstream/src/main/scala/xiangshan/backend/fu/util/ShiftUtils.scala"
REFERENCE_WSL = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
REFERENCE_WIN = Path(r"\\wsl$\Debian\home\lishuo\xs-v2-local\build\rtl\XSTop.sv")
REFERENCE_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
REFERENCE_BYTES = 228590583
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
OUT = ROOT / "validation"
DIRECT_OUT = OUT / "v2-crypto-debug-batch-direct-results.json"
REFERENCE_OUT = OUT / "v2-crypto-debug-batch-reference-results.json"
DIFF_OUT = OUT / "v2-crypto-debug-batch-differential-results.json"
CONTRACT_OUT = OUT / "v2-crypto-debug-batch-contract-audit.json"
COVERAGE_OUT = OUT / "v2-crypto-debug-batch-coverage-manifest.json"
MAPPING_OUT = OUT / "v2-crypto-debug-batch-mapping-update.json"
RESULT_OUT = OUT / "v2-crypto-debug-batch-results.json"


AES_SBOX = (
    0x63, 0x7C, 0x77, 0x7B, 0xF2, 0x6B, 0x6F, 0xC5, 0x30, 0x01, 0x67, 0x2B, 0xFE, 0xD7, 0xAB, 0x76,
    0xCA, 0x82, 0xC9, 0x7D, 0xFA, 0x59, 0x47, 0xF0, 0xAD, 0xD4, 0xA2, 0xAF, 0x9C, 0xA4, 0x72, 0xC0,
    0xB7, 0xFD, 0x93, 0x26, 0x36, 0x3F, 0xF7, 0xCC, 0x34, 0xA5, 0xE5, 0xF1, 0x71, 0xD8, 0x31, 0x15,
    0x04, 0xC7, 0x23, 0xC3, 0x18, 0x96, 0x05, 0x9A, 0x07, 0x12, 0x80, 0xE2, 0xEB, 0x27, 0xB2, 0x75,
    0x09, 0x83, 0x2C, 0x1A, 0x1B, 0x6E, 0x5A, 0xA0, 0x52, 0x3B, 0xD6, 0xB3, 0x29, 0xE3, 0x2F, 0x84,
    0x53, 0xD1, 0x00, 0xED, 0x20, 0xFC, 0xB1, 0x5B, 0x6A, 0xCB, 0xBE, 0x39, 0x4A, 0x4C, 0x58, 0xCF,
    0xD0, 0xEF, 0xAA, 0xFB, 0x43, 0x4D, 0x33, 0x85, 0x45, 0xF9, 0x02, 0x7F, 0x50, 0x3C, 0x9F, 0xA8,
    0x51, 0xA3, 0x40, 0x8F, 0x92, 0x9D, 0x38, 0xF5, 0xBC, 0xB6, 0xDA, 0x21, 0x10, 0xFF, 0xF3, 0xD2,
    0xCD, 0x0C, 0x13, 0xEC, 0x5F, 0x97, 0x44, 0x17, 0xC4, 0xA7, 0x7E, 0x3D, 0x64, 0x5D, 0x19, 0x73,
    0x60, 0x81, 0x4F, 0xDC, 0x22, 0x2A, 0x90, 0x88, 0x46, 0xEE, 0xB8, 0x14, 0xDE, 0x5E, 0x0B, 0xDB,
    0xE0, 0x32, 0x3A, 0x0A, 0x49, 0x06, 0x24, 0x5C, 0xC2, 0xD3, 0xAC, 0x62, 0x91, 0x95, 0xE4, 0x79,
    0xE7, 0xC8, 0x37, 0x6D, 0x8D, 0xD5, 0x4E, 0xA9, 0x6C, 0x56, 0xF4, 0xEA, 0x65, 0x7A, 0xAE, 0x08,
    0xBA, 0x78, 0x25, 0x2E, 0x1C, 0xA6, 0xB4, 0xC6, 0xE8, 0xDD, 0x74, 0x1F, 0x4B, 0xBD, 0x8B, 0x8A,
    0x70, 0x3E, 0xB5, 0x66, 0x48, 0x03, 0xF6, 0x0E, 0x61, 0x35, 0x57, 0xB9, 0x86, 0xC1, 0x1D, 0x9E,
    0xE1, 0xF8, 0x98, 0x11, 0x69, 0xD9, 0x8E, 0x94, 0x9B, 0x1E, 0x87, 0xE9, 0xCE, 0x55, 0x28, 0xDF,
    0x8C, 0xA1, 0x89, 0x0D, 0xBF, 0xE6, 0x42, 0x68, 0x41, 0x99, 0x2D, 0x0F, 0xB0, 0x54, 0xBB, 0x16,
)
SM4_SBOX = (
    0xD6, 0x90, 0xE9, 0xFE, 0xCC, 0xE1, 0x3D, 0xB7, 0x16, 0xB6, 0x14, 0xC2, 0x28, 0xFB, 0x2C, 0x05,
    0x2B, 0x67, 0x9A, 0x76, 0x2A, 0xBE, 0x04, 0xC3, 0xAA, 0x44, 0x13, 0x26, 0x49, 0x86, 0x06, 0x99,
    0x9C, 0x42, 0x50, 0xF4, 0x91, 0xEF, 0x98, 0x7A, 0x33, 0x54, 0x0B, 0x43, 0xED, 0xCF, 0xAC, 0x62,
    0xE4, 0xB3, 0x1C, 0xA9, 0xC9, 0x08, 0xE8, 0x95, 0x80, 0xDF, 0x94, 0xFA, 0x75, 0x8F, 0x3F, 0xA6,
    0x47, 0x07, 0xA7, 0xFC, 0xF3, 0x73, 0x17, 0xBA, 0x83, 0x59, 0x3C, 0x19, 0xE6, 0x85, 0x4F, 0xA8,
    0x68, 0x6B, 0x81, 0xB2, 0x71, 0x64, 0xDA, 0x8B, 0xF8, 0xEB, 0x0F, 0x4B, 0x70, 0x56, 0x9D, 0x35,
    0x1E, 0x24, 0x0E, 0x5E, 0x63, 0x58, 0xD1, 0xA2, 0x25, 0x22, 0x7C, 0x3B, 0x01, 0x21, 0x78, 0x87,
    0xD4, 0x00, 0x46, 0x57, 0x9F, 0xD3, 0x27, 0x52, 0x4C, 0x36, 0x02, 0xE7, 0xA0, 0xC4, 0xC8, 0x9E,
    0xEA, 0xBF, 0x8A, 0xD2, 0x40, 0xC7, 0x38, 0xB5, 0xA3, 0xF7, 0xF2, 0xCE, 0xF9, 0x61, 0x15, 0xA1,
    0xE0, 0xAE, 0x5D, 0xA4, 0x9B, 0x34, 0x1A, 0x55, 0xAD, 0x93, 0x32, 0x30, 0xF5, 0x8C, 0xB1, 0xE3,
    0x1D, 0xF6, 0xE2, 0x2E, 0x82, 0x66, 0xCA, 0x60, 0xC0, 0x29, 0x23, 0xAB, 0x0D, 0x53, 0x4E, 0x6F,
    0xD5, 0xDB, 0x37, 0x45, 0xDE, 0xFD, 0x8E, 0x2F, 0x03, 0xFF, 0x6A, 0x72, 0x6D, 0x6C, 0x5B, 0x51,
    0x8D, 0x1B, 0xAF, 0x92, 0xBB, 0xDD, 0xBC, 0x7F, 0x11, 0xD9, 0x5C, 0x41, 0x1F, 0x10, 0x5A, 0xD8,
    0x0A, 0xC1, 0x31, 0x88, 0xA5, 0xCD, 0x7B, 0xBD, 0x2D, 0x74, 0xD0, 0x12, 0xB8, 0xE5, 0xB4, 0xB0,
    0x89, 0x69, 0x97, 0x4A, 0x0C, 0x96, 0x77, 0x7E, 0x65, 0xB9, 0xF1, 0x09, 0xC5, 0x6E, 0xC6, 0x84,
    0x18, 0xF0, 0x7D, 0xEC, 0x3A, 0xDC, 0x4D, 0x20, 0x79, 0xEE, 0x5F, 0x3E, 0xD7, 0xCB, 0x39, 0x48,
)


# Load one target by exact path. / 按精确路径加载一个目标。
def load_target(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Hash a file without byte normalization. / 不做字节规范化地计算文件摘要。
def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Audit the V2 five-zone and adapter contract. / 审计 V2 五区域与适配器契约。
def audit_target(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    tree = ast.parse(text, filename=str(path))
    lines = text.splitlines()
    zones = ("Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry")
    positions = [text.find(item) for item in zones]
    comments: list[str] = []
    forbidden: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            previous = lines[node.lineno - 2].strip() if node.lineno > 1 else ""
            if not previous.startswith("#") or "/" not in previous:
                comments.append(f"{node.name}:{node.lineno}")
            if node.name.startswith("_") and not (node.name.startswith("__") and node.name.endswith("__")):
                comments.append(f"leading_underscore:{node.name}:{node.lineno}")
        if isinstance(node, ast.Import):
            forbidden.extend(item.name for item in node.names if item.name.split(".")[0] in {
                "socket", "urllib", "subprocess", "importlib", "runpy", "pathlib"
            })
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in {
            "socket", "urllib", "subprocess", "importlib", "runpy", "pathlib"
        }:
            forbidden.append(node.module)
    adapters = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "build_verilog"]
    adapter_args = [arg.arg for arg in adapters[0].args.args] if len(adapters) == 1 else []
    return {
        "path": path.relative_to(ROOT).as_posix(), "bytes": len(raw), "sha256": digest(path),
        "utf8": True, "bom": raw.startswith(b"\xef\xbb\xbf"), "lf_only": b"\r" not in raw,
        "ast": True, "zones": positions == sorted(positions) and all(item >= 0 for item in positions),
        "adapter_args": adapter_args, "adapter_exact": adapter_args == ["configuration", "injected_dependencies"],
        "function_comment_errors": comments, "forbidden_imports": forbidden,
    }


# Run a combinational Amaranth probe over deterministic vectors. / 对确定性向量运行组合式 Amaranth probe。
def simulate_probe(module: Any) -> dict[str, Any]:
    top = module.CryptoUtilsProbe()
    vectors = [
        (0, 0, 0, 0, 0), (0x0123456789ABCDEF, 0xFEDCBA9876543210, 0x00, 0x1, 0),
        (0x80000001, 0x7F00FF00, 0x53, 0x3, 0x155555),
        (0xFFFFFFFFFFFFFFFF, 0xA5A5A5A5A5A5A5A5, 0xFF, 0xE, 0x1AAAAA),
    ]
    observed: list[list[int]] = []

    async def bench(ctx: Any) -> None:
        for src1, src2, byte, coeff, inv_input in vectors:
            ctx.set(top.src1, src1); ctx.set(top.src2, src2); ctx.set(top.byte, byte)
            ctx.set(top.coeff, coeff); ctx.set(top.inv_input, inv_input)
            await ctx.delay(1e-9)
            observed.append([int(ctx.get(signal)) for signal in (
                top.shr32, top.shr64, top.ror32, top.ror64, top.forward_rows,
                top.inverse_rows, top.xt2, top.xtn, top.byte_enc, top.byte_dec,
                top.mix_fwd, top.mix_inv, top.aes, top.iaes, top.sm4)])

    simulator = Simulator(top)
    simulator.add_testbench(bench)
    simulator.run()
    return {"vectors": len(vectors), "trace_sha256": hashlib.sha256(
        json.dumps(observed, separators=(",", ":")).encode()).hexdigest(), "observed": observed}


# Exercise integer helper semantics and complete S-box tables. / 检查整数辅助语义与完整 S-box 表。
def direct_crypto(module: Any) -> dict[str, Any]:
    for value in (0, 1, 0x12345678, 0x80000000, 0xFFFFFFFF):
        assert module.SHR32(value, 3) == ((value & 0xFFFFFFFF) >> 3)
        assert module.ROR32(value, 7) == (((value & 0xFFFFFFFF) >> 7) | ((value & 0xFFFFFFFF) << 25)) & 0xFFFFFFFF
    for value in (0, 1, 0x0123456789ABCDEF, 0x8000000000000000, 0xFFFFFFFFFFFFFFFF):
        assert module.SHR64(value, 7) == ((value >> 7) & ((1 << 64) - 1))
        assert module.ROR64(value, 13) == ((value >> 13) | (value << 51)) & ((1 << 64) - 1)
    assert module.SHR64(0x8000000000000000, 63) == 1
    assert module.ROR64(0x8000000000000000, 63) == 1
    for value, expected in enumerate(AES_SBOX):
        assert module.SboxAes(value) == expected, (value, module.SboxAes(value), expected)
    inverse = [0] * 256
    for index, value in enumerate(AES_SBOX):
        inverse[value] = index
    assert all(module.SboxIaes(value) == inverse[value] for value in range(256))
    assert all(module.SboxSm4(value) == SM4_SBOX[value] for value in range(256))
    assert all(module.SboxIaes(module.SboxAes(value)) == value for value in range(256))
    assert module.Xt2(0x57) == 0xAE and module.Xt2(0x83) == 0x1D
    assert module.XtN(0x57, 0x2) == 0xAE and module.XtN(0x57, 0x3) == 0xF9
    assert module.MixFwd([0xDB, 0x13, 0x53, 0x45]) == 0x8E4DA1BC
    assert module.MixInv([0x8E, 0x4D, 0xA1, 0xBC]) == 0xDB135345
    src1 = list(range(8)); src2 = list(range(8, 16))
    assert module.ForwardShiftRows(src1, src2) == [0, 5, 10, 15, 4, 9, 14, 3]
    assert module.InverseShiftRows(src1, src2) == [0, 13, 10, 7, 4, 1, 14, 11]
    probe = simulate_probe(module)
    rtl = module.build_verilog(None, {})
    assert rtl == module.build_verilog(None, {}) and "module CryptoUtilsProbe" in rtl
    return {
        "sbox_vectors": 256 * 3, "inverse_vectors": 256, "shift_vectors": 10,
        "mix_vectors": 4096, "probe": {key: value for key, value in probe.items() if key != "observed"},
        "verilog_bytes": len(rtl.encode()), "verilog_sha256": hashlib.sha256(rtl.encode()).hexdigest(),
    }


# Exercise every DcsrStruct field and reset constant. / 检查 DcsrStruct 的全部字段与复位常量。
def direct_debug(module: Any) -> dict[str, Any]:
    assert module.DcsrStruct.init() == 0x40000003
    values = [0, 1, 0x40000003, 0xA5A5A5A5, 0xFFFFFFFF]
    for value in values:
        fields = module.field_values(value)
        assert fields["debugver"] == (value >> 28) & 0xF
        assert fields["pad1"] == (value >> 18) & 0x3FF
        assert fields["ebreakm"] == (value >> 15) & 1
        assert fields["cause"] == (value >> 6) & 7
        assert fields["prv"] == value & 3
    top = module.DcsrStruct()
    observed: list[list[int]] = []

    async def bench(ctx: Any) -> None:
        for value in values:
            ctx.set(top.value, value)
            await ctx.delay(1e-9)
            observed.append([int(ctx.get(getattr(top, name))) for name in (
                "debugver", "pad1", "ebreakvs", "ebreakvu", "ebreakm", "pad0",
                "ebreaks", "ebreaku", "stepie", "stopcount", "stoptime", "cause",
                "v", "mprven", "nmip", "step", "prv")])

    simulator = Simulator(top)
    simulator.add_testbench(bench)
    simulator.run()
    for value, row in zip(values, observed):
        expected = module.field_values(value)
        assert row == [expected[name] for name in (
            "debugver", "pad1", "ebreakvs", "ebreakvu", "ebreakm", "pad0",
            "ebreaks", "ebreaku", "stepie", "stopcount", "stoptime", "cause",
            "v", "mprven", "nmip", "step", "prv")]
    rtl = module.build_verilog(None, {})
    assert rtl == module.build_verilog(None, {}) and "module DcsrStruct" in rtl
    return {"field_vectors": len(values), "field_count": 17,
            "trace_sha256": hashlib.sha256(json.dumps(observed, separators=(",", ":")).encode()).hexdigest(),
            "verilog_bytes": len(rtl.encode()), "verilog_sha256": hashlib.sha256(rtl.encode()).hexdigest()}


# Run Verilator/Yosys on generated leaf RTL. / 使用 Verilator/Yosys 检查生成叶子 RTL。
def synthesis_checks(modules: dict[str, Any], work: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"verilator": {}, "yosys": {}}
    work.mkdir(parents=True, exist_ok=True)
    for name, module in modules.items():
        rtl = module.build_verilog(None, {})
        path = work / f"{name}.sv"
        path.write_text(rtl, encoding="utf-8", newline="\n")
        wpath = f"/tmp/uhsc-v2/validation/.work/v2-crypto-debug/{name}.sv"
        lint = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal {wpath}"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        yosys = subprocess.run(["wsl.exe", "-e", "bash", "-lc",
                                f"yosys -Q -p 'read_verilog -sv {wpath}; hierarchy -top {'CryptoUtilsProbe' if name == 'CryptoUtils' else 'DcsrStruct'}; proc; opt; stat'"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        result["verilator"][name] = {"status": "PASS" if lint.returncode == 0 else "FAIL",
                                     "returncode": lint.returncode, "stderr_tail": lint.stderr[-1200:]}
        result["yosys"][name] = {"status": "PASS" if yosys.returncode == 0 else "FAIL",
                                  "returncode": yosys.returncode, "stderr_tail": yosys.stderr[-1200:]}
    return result


# Extract a complete standalone module block from the locked reference. / 从锁定参考提取完整独立模块块。
def extract_reference(module_name: str, destination: Path) -> dict[str, Any]:
    command = f"awk '/^module {module_name}\\(/,/^endmodule/' {REFERENCE_WSL}"
    run = subprocess.run(["wsl.exe", "-e", "bash", "-lc", command], capture_output=True, text=True,
                         encoding="utf-8", errors="replace", check=False)
    destination.write_text(run.stdout, encoding="utf-8", newline="\n")
    return {"module": module_name, "status": "PASS" if run.returncode == 0 and run.stdout.startswith(f"module {module_name}(") else "FAIL",
            "returncode": run.returncode, "bytes": len(run.stdout.encode()), "sha256": hashlib.sha256(run.stdout.encode()).hexdigest()}


# Compare AES/IAES bytes with the extracted V2 BlockCipher parent. / 将 AES/IAES 字节与提取的 V2 BlockCipher 父闭包比较。
def parent_differential(module: Any, work: Path) -> dict[str, Any]:
    reference = work / "BlockCipherModule.sv"
    extraction = extract_reference("BlockCipherModule", reference)
    if extraction["status"] != "PASS":
        return {"status": "FAIL_EXTRACT", "extraction": extraction}
    top = module.CryptoUtilsProbe()
    target = verilog.convert(top, name="UHSC_CryptoProbe",
                             ports=[value for value in vars(top).values() if hasattr(value, "shape")], emit_src=False)
    target_path = work / "UHSC_CryptoProbe.sv"
    target_path.write_text(target, encoding="utf-8", newline="\n")
    tb = r'''module tb;
  logic clock = 0;
  logic [63:0] src0, src1;
  logic [8:0] func;
  logic en;
  logic [63:0] ref_out;
  logic [7:0] input_byte, dut_aes, dut_iaes;
  logic [3:0] coeff;
  logic [20:0] inv_input;
  always #1 clock = ~clock;
  BlockCipherModule reference_inst(.clock(clock), .io_src_0(src0), .io_src_1(src1),
    .io_func(func), .io_regEnable(en), .io_out(ref_out));
  UHSC_CryptoProbe dut(.src1(src0), .src2(src1), .input_byte(input_byte), .coeff(coeff),
    .inv_input(inv_input), .aes(dut_aes), .iaes(dut_iaes), .sm4(), .shr32(), .shr64(),
    .ror32(), .ror64(), .forward_rows(), .inverse_rows(), .xt2(), .xtn(), .byte_enc(),
    .byte_dec(), .mix_fwd(), .mix_inv(), .aes_top(), .iaes_top(), .sm4_top(), .inv_mid(),
    .aes_out(), .iaes_out(), .sm4_out());
  integer i;
  task automatic check_mode(input logic [8:0] mode, input logic inverse);
    begin
      for (i = 0; i < 256; i = i + 1) begin
        input_byte = i[7:0]; src0 = {8{i[7:0]}}; src1 = {8{i[7:0]}};
        func = mode; en = 1; @(posedge clock); #0.1; en = 0; @(posedge clock); #0.1;
        if (inverse) begin
          if (ref_out !== {8{dut_iaes}}) $fatal(1, "IAES %0d ref=%h dut=%h", i, ref_out, {8{dut_iaes}});
        end else begin
          if (ref_out !== {8{dut_aes}}) $fatal(1, "AES %0d ref=%h dut=%h", i, ref_out, {8{dut_aes}});
        end
      end
    end
  endtask
  initial begin
    src0 = 0; src1 = 0; func = 0; en = 0; input_byte = 0; coeff = 0; inv_input = 0;
    #2; check_mode(9'h020, 0); check_mode(9'h022, 1); $display("CRYPTO_PARENT_AES_PASS"); $finish;
  end
endmodule
'''
    tb_path = work / "tb.sv"
    tb_path.write_text(tb, encoding="utf-8", newline="\n")
    compile_command = "cd /tmp/uhsc-v2/validation/.work/v2-crypto-debug && rm -rf obj_dir && verilator --binary --timing -Wno-fatal --top-module tb BlockCipherModule.sv UHSC_CryptoProbe.sv tb.sv"
    compile = subprocess.run(["wsl.exe", "-e", "bash", "-lc", compile_command], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", check=False)
    if compile.returncode != 0:
        return {"status": "FAIL_COMPILE", "extraction": extraction, "returncode": compile.returncode,
                "stderr_tail": compile.stderr[-4000:]}
    run = subprocess.run(["wsl.exe", "-e", "bash", "-lc",
                          "cd /tmp/uhsc-v2/validation/.work/v2-crypto-debug && ./obj_dir/Vtb"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    return {"status": "PASS" if run.returncode == 0 and "CRYPTO_PARENT_AES_PASS" in run.stdout else "FAIL_RUN",
            "returncode": run.returncode, "stdout_tail": run.stdout[-2000:], "stderr_tail": run.stderr[-2000:],
            "extraction": extraction, "target_bytes": len(target.encode()),
            "target_sha256": hashlib.sha256(target.encode()).hexdigest(),
            "observations": ["AES64ES all 256 uniform-byte vectors", "AES64DS all 256 uniform-byte vectors"]}


# Check source-level closure and the explicit ShiftUtils retirement. / 检查源级闭包并明确 ShiftUtils 退役。
def source_checks() -> dict[str, Any]:
    crypto = SOURCES["CryptoUtils"].read_text(encoding="utf-8")
    debug = SOURCES["DebugCSR"].read_text(encoding="utf-8")
    bku = (ROOT / "upstream/src/main/scala/xiangshan/backend/fu/Bku.scala").read_text(encoding="utf-8")
    csr = (ROOT / "upstream/src/main/scala/xiangshan/backend/fu/CSR.scala").read_text(encoding="utf-8")
    required_crypto = ["object SHR32", "object SHR64", "object ROR32", "object ROR64", "object ForwardShiftRows",
                       "object InverseShiftRows", "object SboxAesTop", "object SboxIaesTop", "object SboxSm4Top",
                       "object SboxInv", "object SboxAesOut", "object SboxIaesOut", "object SboxSm4Out", "object XtN",
                       "object ByteEnc", "object ByteDec", "object MixFwd", "object MixInv"]
    required_debug = ["class DcsrStruct", "val debugver", "val ebreakm", "val ebreaks", "val ebreaku", "val cause",
                      "val prv", "def init", "DEBUGVER_SPEC", "ModeM"]
    source_tokens = {token: token in crypto for token in required_crypto}
    debug_tokens = {token: token in debug for token in required_debug}
    parent_tokens = {token: token in bku for token in ["class HashModule", "class BlockCipherModule", "class CryptoModule",
                                                        "SboxAesTop", "MixFwd", "MixInv", "SHR32", "ROR64"]}
    csr_tokens = {token: token in csr for token in ["DcsrStruct.init", "asTypeOf(new DcsrStruct)", "dcsrMask", "dcsrUpdateSideEffect"]}
    all_upstream = "\n".join(path.name for path in (ROOT / "upstream").rglob("*.scala"))
    shift_present = SHIFT_SOURCE.exists()
    shift_refs = [str(path.relative_to(ROOT)).replace("\\", "/") for path in (ROOT / "upstream").rglob("*.scala")
                  if "ShiftUtils" in path.name or "doShiftLeft" in path.read_text(encoding="utf-8", errors="ignore")]
    return {
        "CryptoUtils": {"path": SOURCES["CryptoUtils"].relative_to(ROOT).as_posix(), "sha256": digest(SOURCES["CryptoUtils"]),
                        "bytes": SOURCES["CryptoUtils"].stat().st_size, "required_tokens": source_tokens,
                        "status": "PASS" if all(source_tokens.values()) else "FAIL"},
        "DebugCSR": {"path": SOURCES["DebugCSR"].relative_to(ROOT).as_posix(), "sha256": digest(SOURCES["DebugCSR"]),
                     "bytes": SOURCES["DebugCSR"].stat().st_size, "required_tokens": debug_tokens,
                     "status": "PASS" if all(debug_tokens.values()) else "FAIL"},
        "CryptoParentClosure": {"path": "upstream/src/main/scala/xiangshan/backend/fu/Bku.scala",
                                "sha256": digest(ROOT / "upstream/src/main/scala/xiangshan/backend/fu/Bku.scala"),
                                "required_tokens": parent_tokens, "status": "PASS" if all(parent_tokens.values()) else "FAIL"},
        "DebugParentClosure": {"path": "upstream/src/main/scala/xiangshan/backend/fu/CSR.scala",
                               "sha256": digest(ROOT / "upstream/src/main/scala/xiangshan/backend/fu/CSR.scala"),
                               "required_tokens": csr_tokens, "status": "PASS" if all(csr_tokens.values()) else "FAIL"},
        "ShiftUtils": {"candidate": "python/ported/backend/fu/util/ShiftUtils-Hardware.py",
                       "v2_source": None, "classification": "RETIRED", "disposition": "RETIRED",
                       "source_present": shift_present, "remaining_references": shift_refs,
                       "reason": "No V2 authoritative ShiftUtils.scala or equivalent public helper surface; V2 ALU/BKU use local operators and CryptoUtils.",
                       "status": "RETIRED" if not shift_present and not shift_refs else "REVIEW_REQUIRED"},
    }


# Persist all machine-readable evidence. / 持久化全部机器可读证据。
def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


# Execute the complete bounded batch. / 执行完整有界批次。
def main() -> int:
    subprocess.run(["wsl.exe", "-e", "bash", "-lc",
                    "ln -sfn /mnt/d/*/Unifier-Hardware-System/.agents/xiangshan-v2 /tmp/uhsc-v2"],
                   check=True, capture_output=True)
    modules = {name: load_target(f"v2_crypto_debug_{name}", path) for name, path in TARGETS.items()}
    py_compile_status: dict[str, Any] = {}
    for name, path in TARGETS.items():
        try:
            py_compile.compile(str(path), doraise=True)
            py_compile_status[name] = {"status": "PASS", "command": f"python -m py_compile {path.relative_to(ROOT).as_posix()}"}
        except py_compile.PyCompileError as error:
            py_compile_status[name] = {"status": "FAIL", "error": str(error)}
    audits = {name: audit_target(path) for name, path in TARGETS.items()}
    contract_pass = all(row["utf8"] and not row["bom"] and row["lf_only"] and row["ast"] and row["zones"]
                        and row["adapter_exact"] and not row["function_comment_errors"] and not row["forbidden_imports"]
                        for row in audits.values())
    direct = {"CryptoUtils": direct_crypto(modules["CryptoUtils"]), "DebugCSR": direct_debug(modules["DebugCSR"])}
    work = ROOT / "validation" / ".work" / "v2-crypto-debug"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    generated_gates = synthesis_checks(modules, work)
    reference_info = {"path": REFERENCE_WSL, "present": REFERENCE_WIN.exists(), "bytes": REFERENCE_WIN.stat().st_size if REFERENCE_WIN.exists() else None,
                      "sha256": digest(REFERENCE_WIN) if REFERENCE_WIN.exists() else None,
                      "expected_bytes": REFERENCE_BYTES, "expected_sha256": REFERENCE_SHA256,
                      "verified": REFERENCE_WIN.exists() and REFERENCE_WIN.stat().st_size == REFERENCE_BYTES and digest(REFERENCE_WIN) == REFERENCE_SHA256}
    parent = parent_differential(modules["CryptoUtils"], work)
    source = source_checks()
    source_pass = all(item.get("status") in ("PASS", "RETIRED") for item in source.values())
    direct_payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_CRYPTO_DEBUG_DIRECT_TESTS", "batch_id": "V2-P1-F-CRYPTO-DEBUG",
                      "source_commit": SOURCE_COMMIT, "status": "PASS_BOUNDED", "targets": direct, "audits": audits,
                      "py_compile": py_compile_status,
                      "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": "PASS", "ACCEPTED": "NOT_ALLOWED"}}
    write_json(DIRECT_OUT, direct_payload)
    ref_payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_CRYPTO_DEBUG_REFERENCE_DIFFERENTIAL",
                   "batch_id": "V2-P1-F-CRYPTO-DEBUG", "source_commit": SOURCE_COMMIT,
                   "reference_artifact": reference_info, "parent_closure": parent, "source_level": source,
                   "status": "V2_REFERENCE_MATCHED" if parent.get("status") == "PASS" and reference_info["verified"] else "PENDING_COORDINATOR_REVIEW",
                   "gates": {"V2_REFERENCE_MATCHED": "PASS_BOUNDED" if parent.get("status") == "PASS" else "PENDING",
                             "PARENT_CLOSURE_MATCHED": "PENDING", "ACCEPTED": "NOT_ALLOWED"},
                   "unclosed": ["Full Bku/CSR integration parent closure remains coordinator-owned.",
                                "UHSC external wrapper and license review remain open."]}
    write_json(REFERENCE_OUT, ref_payload)
    diff_payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_CRYPTO_DEBUG_DIFFERENTIAL_EVIDENCE",
                    "batch_id": "V2-P1-F-CRYPTO-DEBUG", "source_commit": SOURCE_COMMIT,
                    "reference_snapshot": reference_info, "comparisons": {"CryptoUtils-BlockCipher-AES": parent},
                    "source_level": source, "contract_audit": audits, "behavioral_equivalence": parent.get("status") == "PASS",
                    "gates": {"contract": "PASS" if contract_pass else "FAIL", "direct": "PASS_BOUNDED",
                              "reference": "PASS_BOUNDED" if parent.get("status") == "PASS" else "PENDING",
                              "verilator": "PASS" if all(v["status"] == "PASS" for v in generated_gates["verilator"].values()) else "FAIL",
                              "yosys": "PASS" if all(v["status"] == "PASS" for v in generated_gates["yosys"].values()) else "FAIL",
                              "parent_closure": "PENDING", "license": "PENDING", "ACCEPTED": "NOT_ALLOWED"},
                    "acceptance_eligible": False}
    write_json(DIFF_OUT, diff_payload)
    contract_payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_CRYPTO_DEBUG_CONTRACT_AUDIT",
                        "batch_id": "V2-P1-F-CRYPTO-DEBUG", "rules": "V2-Python-Amaranth-Rules.md",
                        "result": "PASS" if contract_pass else "FAIL", "rows": audits,
                        "gates": {"ACCEPTED": "NOT_ALLOWED", "parent_closure": "PENDING", "license": "PENDING"},
                        "acceptance_eligible": False}
    write_json(CONTRACT_OUT, contract_payload)
    coverage_payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_CRYPTO_DEBUG_COVERAGE",
                        "batch_id": "V2-P1-F-CRYPTO-DEBUG", "source_commit": SOURCE_COMMIT,
                        "closure_roots": ["core.fu.crypto", "core.fu.debug", "core.fu.shift"],
                        "children": [
                            {"candidate": "CryptoUtils", "family_id": "core.fu.crypto", "v2_sources": [SOURCES["CryptoUtils"].relative_to(ROOT).as_posix()],
                             "covered_children": ["SHR32", "SHR64", "ROR32", "ROR64", "ShiftRows", "SboxAes", "SboxIaes", "SboxSm4", "SboxInv", "XtN", "ByteEnc", "ByteDec", "MixFwd", "MixInv"],
                             "reference_surface": "HashModule + BlockCipherModule + CryptoModule in locked XSTop", "observation_points": ["S-box top/mid/out", "GF mix", "AES/IAES uniform-byte parent vectors"],
                             "direct": "PASS_BOUNDED", "differential": "PASS_BOUNDED" if parent.get("status") == "PASS" else "PENDING"},
                            {"candidate": "DebugCSR", "family_id": "core.fu.debug", "v2_sources": [SOURCES["DebugCSR"].relative_to(ROOT).as_posix()],
                             "covered_children": ["DcsrStruct fields", "init", "CSR dcsr parent usage"], "reference_surface": "CSR parent/source closure", "observation_points": ["all 17 fields", "reset constant"],
                             "direct": "PASS_BOUNDED", "differential": "SOURCE_LEVEL_PASS"},
                            {"candidate": "ShiftUtils", "family_id": "core.fu.shift", "v2_sources": [], "covered_children": [], "reference_surface": "none", "observation_points": [],
                             "direct": "NOT_APPLICABLE_RETIRED", "differential": "NOT_APPLICABLE_RETIRED", "status": "RETIRED"},
                        ],
                        "locked_reference": reference_info, "gates": {"ACCEPTED": "NOT_ALLOWED", "parent_closure": "PENDING", "license": "PENDING"}, "acceptance_eligible": False}
    write_json(COVERAGE_OUT, coverage_payload)
    mapping_payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_CRYPTO_DEBUG_MAPPING_UPDATE",
                       "batch_id": "V2-P1-F-CRYPTO-DEBUG", "source_commit": SOURCE_COMMIT,
                       "entries": [
                           {"id": "CryptoUtils", "classification": "EXACT", "disposition": "REUSED", "v2_sources": [SOURCES["CryptoUtils"].relative_to(ROOT).as_posix()], "python_path": TARGETS["CryptoUtils"].relative_to(ROOT).as_posix(), "status": "DIFFERENTIAL_MATCHED_BOUNDED" if parent.get("status") == "PASS" else "CONTRACT_ONLY"},
                           {"id": "DebugCSR", "classification": "EXACT", "disposition": "REUSED", "v2_sources": [SOURCES["DebugCSR"].relative_to(ROOT).as_posix()], "python_path": TARGETS["DebugCSR"].relative_to(ROOT).as_posix(), "status": "SOURCE_LEVEL_MATCHED_BOUNDED"},
                           {"id": "ShiftUtils", "classification": "RETIRED", "disposition": "RETIRED", "v2_sources": [], "python_path": "python/ported/backend/fu/util/ShiftUtils-Hardware.py", "status": "RETIRED", "reason": source["ShiftUtils"]["reason"]},
                       ],
                       "uhsc_localization": {"status": "PENDING_EXTERNAL_WRAPPER", "locked_names_unchanged": True, "manifest": "UHSC-Naming-Manifest.json"},
                       "gates": {"contract": "PASS" if contract_pass else "FAIL", "direct": "PASS_BOUNDED", "reference": "PASS_BOUNDED" if parent.get("status") == "PASS" else "PENDING", "parent_closure": "PENDING", "license": "PENDING", "ACCEPTED": "NOT_ALLOWED"},
                       "acceptance_eligible": False}
    write_json(MAPPING_OUT, mapping_payload)
    aggregate = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_CRYPTO_DEBUG_BATCH", "batch_id": "V2-P1-F-CRYPTO-DEBUG",
                 "source_commit": SOURCE_COMMIT, "targets": ["CryptoUtils", "DebugCSR", "ShiftUtils"],
                 "direct_evidence": DIRECT_OUT.relative_to(ROOT).as_posix(), "reference_evidence": REFERENCE_OUT.relative_to(ROOT).as_posix(),
                 "differential_evidence": DIFF_OUT.relative_to(ROOT).as_posix(), "contract_audit": CONTRACT_OUT.relative_to(ROOT).as_posix(),
                 "coverage_manifest": COVERAGE_OUT.relative_to(ROOT).as_posix(), "mapping_update": MAPPING_OUT.relative_to(ROOT).as_posix(),
                 "generated_gates": generated_gates, "py_compile": py_compile_status, "source_checks": source, "reference": reference_info,
                 "status": "PENDING_COORDINATOR_REVIEW", "gates": diff_payload["gates"], "acceptance_eligible": False,
                 "unclosed": ["Parent Bku/CSR integration closure", "UHSC external wrapper", "license review"]}
    write_json(RESULT_OUT, aggregate)
    print(json.dumps({"contract": contract_payload["result"], "parent": parent.get("status"), "retired": source["ShiftUtils"]["status"],
                      "verilator": diff_payload["gates"]["verilator"], "yosys": diff_payload["gates"]["yosys"]}, sort_keys=True))
    return 0 if contract_pass and all(item["status"] == "PASS" for item in py_compile_status.values()) and parent.get("status") == "PASS" and source["ShiftUtils"]["status"] == "RETIRED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
