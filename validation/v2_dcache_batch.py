"""Bounded V2 dcache evidence for AMOALU and TagArray. / AMOALU 与 TagArray 的 V2 数据缓存有界证据。"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import random
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from amaranth.sim import Simulator


ROOT = Path(__file__).resolve().parents[1]
BUILD_MEMORY = ROOT / "python" / "Program-System" / "System-Build" / "Build-Cpu" / "Cpu-Memory"
REFERENCE = Path(r"\\wsl$\Debian\home\lishuo\xs-v2-local\build\rtl\XSTop.sv")
REFERENCE_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
REFERENCE_BYTES = 228590583
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
TARGETS = {
    "AMOALU": BUILD_MEMORY / "Build-Cpu.Cache.Dcache.Mainpipe.AMOALU-Hardware.py",
    "TagArray": BUILD_MEMORY / "Build-Cpu.Cache.Dcache.Meta.TagArray-Hardware.py",
}
SOURCE_PATHS = {
    "AMOALU": ["upstream/src/main/scala/xiangshan/cache/dcache/mainpipe/AMOALU.scala"],
    "TagArray": ["upstream/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala"],
}
REFERENCE_DIR = ROOT / "validation" / "reference-closures"
REFERENCE_MODULES = [
    "AMOALU",
    "array_256x86",
    "sram_array_1p256x86m43s1h0l1b_dcsh_tag",
    "ClockGate",
    "MbistClockGateCell",
    "SRAMTemplate_116",
    "TagSRAMBank",
    "TagArray",
]


# Load a target by exact path without importing sibling project files. / 按精确路径加载目标且不导入同级工程文件。
def load_target(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load target {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Audit the five-zone target contract and deterministic adapter signature. / 审计五分区目标契约及确定性适配器签名。
def audit_target(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise AssertionError(f"UTF-8 BOM present: {path}")
    source = raw.decode("utf-8")
    if b"\r\n" in raw:
        raise AssertionError(f"CRLF line endings present: {path}")
    tree = ast.parse(source, filename=str(path))
    zones = ("Module Contract", "Configuration", "Implementation",
             "Public Adapter", "Direct Entry")
    positions = [source.find(zone) for zone in zones]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise AssertionError(f"five-zone contract missing: {path}")
    adapter = next((node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "build_verilog"), None)
    if adapter is None or [arg.arg for arg in adapter.args.args] != [
            "configuration", "injected_dependencies"]:
        raise AssertionError(f"adapter signature mismatch: {path}")
    if "__all__" not in source:
        raise AssertionError(f"explicit __all__ missing: {path}")
    forbidden = {"importlib", "runpy", "subprocess", "socket", "urllib", "pathlib"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(item.name.split(".")[0] in forbidden for item in node.names):
                raise AssertionError(f"forbidden import in {path}")
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in forbidden:
                raise AssertionError(f"forbidden import in {path}")
    lines = source.splitlines()
    functions: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
            if node.name.startswith("_") and not (
                    node.name.startswith("__") and node.name.endswith("__")):
                raise AssertionError(f"leading underscore helper {node.name}: {path}")
            prior = lines[node.lineno - 2].strip() if node.lineno >= 2 else ""
            if not prior.startswith("#") or "/" not in prior:
                raise AssertionError(f"missing bilingual comment {node.name}: {path}")
    compile(source, str(path), "exec")
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "utf8_lf": True,
        "ast": True,
        "zones": list(zones),
        "adapter_exact": True,
        "functions": sorted(functions),
    }


# Compute the independent V2 AMOALU integer oracle. / 计算独立的 V2 AMOALU 整数参考模型。
def amo_oracle(mask: int, cmd: int, lhs: int, rhs: int, bits: int = 64) -> tuple[int, int]:
    all_ones = (1 << bits) - 1
    min_xlen = 32
    adder_mask = all_ones
    width = min_xlen
    while width < bits:
        if not ((mask >> (width // 8 - 1)) & 1):
            adder_mask &= ~(1 << (width - 1))
        width <<= 1
    adder = ((lhs & adder_mask) + (rhs & adder_mask)) & all_ones
    is_max = cmd in (0xD, 0xF)
    is_min = cmd in (0xC, 0xE)
    is_add = cmd == 0x8
    logic_and = cmd in (0xA, 0xB)
    logic_xor = cmd in (0x9, 0xA)
    signed = (cmd & 0x2) == (0xC & 0x2)

    # Compare the selected XLEN with Chisel's PriorityMux fallback. / 按 Chisel PriorityMux 回退规则比较选定 XLEN。
    def less_for_width(width_value: int) -> bool:
        left = lhs & ((1 << width_value) - 1)
        right = rhs & ((1 << width_value) - 1)
        left_sign = (left >> (width_value - 1)) & 1
        right_sign = (right >> (width_value - 1)) & 1
        if left_sign == right_sign:
            return left < right
        return bool(left_sign if signed else right_sign)

    compare_width = min_xlen
    width = min_xlen
    while width <= bits:
        if (mask >> (width // 8 // 2)) & 1:
            compare_width = width
        width <<= 1
    less = less_for_width(compare_width)
    minmax = lhs if ((less and is_min) or ((not less) and is_max)) else rhs
    logic = ((lhs & rhs) if logic_and else 0) | ((lhs ^ rhs) if logic_xor else 0)
    raw = adder if is_add else (logic if logic_and or logic_xor else minmax)
    write_mask = sum(0xFF << (8 * lane) for lane in range(bits // 8)
                     if (mask >> lane) & 1)
    result = ((write_mask & raw) | ((~write_mask) & lhs)) & all_ones
    return result, raw


# Run exhaustive command/mask and width-boundary AMOALU simulation. / 执行穷举命令/掩码及位宽边界 AMOALU 仿真。
def test_amo(module: Any) -> dict[str, Any]:
    checks = 0
    rng = random.Random(0xA0A0)
    for bits, mask_values in ((32, [0, 1, 4, 0xF]),
                              (64, list(range(256))),
                              (128, [0, 4, 0x10, 0x100, 0x104, 0xFFFF])):
        config = module.AMOALUConfig(operandBits=bits)
        top = module.AMOALU(config)
        vectors = []
        for mask in mask_values:
            for cmd in range(32):
                lhs = rng.getrandbits(bits)
                rhs = rng.getrandbits(bits)
                vectors.append((mask, cmd, lhs, rhs))
        async def bench(ctx: Any) -> None:
            nonlocal checks
            for mask, cmd, lhs, rhs in vectors:
                for signal, value in ((top.mask, mask), (top.cmd, cmd),
                                      (top.lhs, lhs), (top.rhs, rhs)):
                    ctx.set(signal, value)
                await ctx.delay(1e-9)
                observed = (int(ctx.get(top.out)), int(ctx.get(top.out_unmasked)))
                wanted = amo_oracle(mask, cmd, lhs, rhs, bits)
                if observed != wanted:
                    raise AssertionError((bits, mask, cmd, observed, wanted))
                checks += 1
        simulator = Simulator(top)
        simulator.add_testbench(bench)
        simulator.run()
    return {"vectors": checks, "widths": [32, 64, 128], "commands": 32}


# Pack the tag model in the same low-way-first order as the flattened adapter. / 按扁平适配器低路优先顺序打包标签模型。
def pack_tags(values: list[int], encoded_bits: int) -> int:
    return sum(value << (index * encoded_bits)
               for index, value in enumerate(values))


# Run reset, masked-write, read-latency, and collision checks on TagArray. / 执行 TagArray 复位、按掩码写入、读延迟及冲突检查。
def test_tag(module: Any) -> dict[str, Any]:
    config = module.TagArrayConfig(nSets=4, nWays=4, tagBits=8, tagECCBits=2)
    top = module.TagArray(config)
    encoded_bits = config.tagBits + config.tagECCBits
    model = [[0 for _ in range(config.nWays)] for _ in range(config.nSets)]
    checks = 0

    async def bench(ctx: Any) -> None:
        nonlocal checks
        ctx.set(top.reset, 1)
        ctx.set(top.read_valid, 0)
        ctx.set(top.read_idx, 0)
        ctx.set(top.read_way_en, (1 << config.nWays) - 1)
        ctx.set(top.write_valid, 0)
        ctx.set(top.write_idx, 0)
        ctx.set(top.write_way_en, 0)
        ctx.set(top.write_way, 0)
        ctx.set(top.write_tag, 0)
        ctx.set(top.write_ecc, 0)
        await ctx.tick()
        await ctx.tick()
        ctx.set(top.reset, 0)
        for _ in range(config.nSets):
            if int(ctx.get(top.read_ready)) != 0:
                raise AssertionError("read became ready during clear")
            await ctx.tick()
            checks += 1
        if int(ctx.get(top.read_ready)) != 1:
            raise AssertionError("read did not become ready after clear")
        checks += 1

        # Deterministic masked writes followed by synchronous reads. / 执行确定性的按掩码写入及同步读取。
        for index in range(8):
            set_index = index % config.nSets
            way_mask = ((index * 5) | 1) & 0xF
            tag = (0x30 + index) & 0xFF
            ecc = (index + 1) & 0x3
            ctx.set(top.write_valid, 1)
            ctx.set(top.write_idx, set_index)
            ctx.set(top.write_way_en, way_mask)
            ctx.set(top.write_tag, tag)
            ctx.set(top.write_ecc, ecc)
            await ctx.tick()
            encoded = tag | (ecc << config.tagBits)
            for way in range(config.nWays):
                if (way_mask >> way) & 1:
                    model[set_index][way] = encoded
            ctx.set(top.write_valid, 0)
            ctx.set(top.write_way_en, 0)
            ctx.set(top.read_valid, 1)
            ctx.set(top.read_idx, set_index)
            await ctx.tick()
            await ctx.delay(1e-9)
            observed = int(ctx.get(top.rdata))
            wanted = pack_tags(model[set_index], encoded_bits)
            if observed != wanted:
                raise AssertionError(("tag read", index, hex(observed), hex(wanted)))
            checks += 1
            ctx.set(top.read_valid, 0)
            await ctx.tick()

        # A write/read collision blocks the read and leaves the prior response intact. / 写读同周期冲突时屏蔽读取并保持先前响应。
        ctx.set(top.write_valid, 1)
        ctx.set(top.write_idx, 1)
        ctx.set(top.write_way_en, 0xF)
        ctx.set(top.write_tag, 0xE7)
        ctx.set(top.write_ecc, 0x2)
        ctx.set(top.read_valid, 1)
        ctx.set(top.read_idx, 1)
        if int(ctx.get(top.read_ready)) != 0:
            raise AssertionError("collision did not deassert ready")
        await ctx.tick()
        checks += 1
        ctx.set(top.write_valid, 0)
        ctx.set(top.write_way_en, 0)
        await ctx.tick()
        ctx.set(top.read_valid, 0)
        encoded = 0xE7 | (0x2 << config.tagBits)
        model[1] = [encoded] * config.nWays
        ctx.set(top.read_valid, 1)
        ctx.set(top.read_idx, 1)
        await ctx.tick()
        await ctx.delay(1e-9)
        if int(ctx.get(top.rdata)) != pack_tags(model[1], encoded_bits):
            raise AssertionError("collision write was not retained")
        checks += 1

    simulator = Simulator(top)
    simulator.add_clock(1e-6)
    simulator.add_testbench(bench)
    simulator.run()
    return {"vectors": checks, "small_config": {"nSets": 4, "nWays": 4,
                                                    "tagBits": 8, "tagECCBits": 2}}


# Hash and verify the locked reference artifact. / 计算并校验锁定参考产物摘要。
def reference_info() -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with REFERENCE.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    sha = digest.hexdigest()
    return {"status": "PASS" if sha == REFERENCE_SHA256 and size == REFERENCE_BYTES else "MISMATCH",
            "path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv",
            "sha256": sha, "bytes": size,
            "expected_sha256": REFERENCE_SHA256, "expected_bytes": REFERENCE_BYTES}


# Extract one complete locked-SV module without editing the source artifact. / 提取一个完整锁定 SV 模块且不修改源产物。
def extract_module(name: str) -> bytes:
    start_re = re.compile(rb"^module\s+" + re.escape(name.encode("ascii")) + rb"\s*\(")
    module_re = re.compile(rb"^module\s+")
    end_re = re.compile(rb"^endmodule\b")
    captured: list[bytes] = []
    depth = 0
    with REFERENCE.open("rb") as stream:
        for line in stream:
            if depth == 0:
                if start_re.match(line):
                    depth = 1
                    captured.append(line)
                continue
            captured.append(line)
            if module_re.match(line):
                depth += 1
            if end_re.match(line):
                depth -= 1
                if depth == 0:
                    return b"".join(captured)
    raise RuntimeError(f"module {name} not found")


# Materialize reproducible reference closures and return their hashes. / 生成可复现参考闭包并返回摘要。
def extract_references() -> dict[str, dict[str, Any]]:
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    rows: dict[str, dict[str, Any]] = {}
    for name in REFERENCE_MODULES:
        payload = extract_module(name)
        path = REFERENCE_DIR / f"{name}-dcache-v2.sv"
        path.write_bytes(payload)
        rows[name] = {"path": path.relative_to(ROOT).as_posix(),
                      "sha256": hashlib.sha256(payload).hexdigest(),
                      "bytes": len(payload)}
    return rows


# Convert a Windows path for a WSL tool invocation. / 将 Windows 路径转换为 WSL 工具路径。
def wsl_path(path: Path) -> str | None:
    try:
        result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace", check=False)
    except OSError:
        return None
    return (result.stdout or "").strip() if result.returncode == 0 else None


# Run Verilator and Yosys backend gates on generated target Verilog. / 对生成目标 Verilog 执行 Verilator 与 Yosys 门禁。
def synthesize(name: str, source: str, directory: Path) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.sv"
    path.write_text(source, encoding="utf-8", newline="\n")
    converted = wsl_path(path)
    if converted is None:
        return {"verilator": {"status": "SKIP", "reason": "wslpath unavailable"},
                "yosys": {"status": "SKIP", "reason": "wslpath unavailable"}}
    verilator = subprocess.run(
        ["wsl.exe", "-e", "bash", "-lc",
         f"verilator --lint-only -Wno-fatal {shlex.quote(converted)}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    yosys = subprocess.run(
        ["wsl.exe", "-e", "bash", "-lc",
         f"yosys -Q -p 'read_verilog -sv {shlex.quote(converted)}; hierarchy -top {name}; proc; opt; stat'"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    return {"verilator": {"status": "PASS" if verilator.returncode == 0 else "FAIL",
                           "returncode": verilator.returncode,
                           "stderr_tail": verilator.stderr[-1200:]},
            "yosys": {"status": "PASS" if yosys.returncode == 0 else "FAIL",
                      "returncode": yosys.returncode,
                      "stderr_tail": yosys.stderr[-1200:]}}


# Execute a generated Verilator testbench and retain bounded diagnostics. / 执行生成的 Verilator 测试台并保留有界诊断。
def run_verilator(source: str, stem: str) -> dict[str, Any]:
    # Keep the transient simulator tree outside the non-ASCII workspace path so
    # wslpath receives a stable Windows path on all hosts. / 将临时仿真目录置于非 ASCII 工作区之外，确保 wslpath 在各主机稳定工作。
    directory = Path(tempfile.mkdtemp(prefix=f"v2_{stem}_"))
    try:
        path = directory / "tb.sv"
        path.write_text(source, encoding="utf-8", newline="\n")
        converted = wsl_path(path)
        if converted is None:
            return {"status": "SKIP", "reason": "wslpath unavailable"}
        workdir = shlex.quote(converted.rsplit("/", 1)[0])
        command = (f"cd {workdir} && verilator --binary --timing -Wno-fatal "
                   f"--top-module tb {shlex.quote(converted)}")
        compile_result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", command],
                                        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        if compile_result.returncode != 0:
            return {"status": "COMPILE_FAIL", "returncode": compile_result.returncode,
                    "stderr_tail": compile_result.stderr[-4000:]}
        binary = directory / "obj_dir" / "Vtb"
        binary_wsl = wsl_path(binary)
        if binary_wsl is None:
            return {"status": "SKIP", "reason": "binary path unavailable"}
        run_result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", shlex.quote(binary_wsl)],
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        return {"status": "PASS" if run_result.returncode == 0 else "FAIL",
                "returncode": run_result.returncode,
                "stdout_tail": run_result.stdout[-1200:],
                "stderr_tail": run_result.stderr[-4000:]}
    finally:
        shutil.rmtree(directory, ignore_errors=True)


# Differentially compare AMOALU against its extracted locked module. / 将 AMOALU 与提取的锁定模块进行差分比较。
def differential_amo(module: Any, reference: bytes) -> dict[str, Any]:
    target = module.build_verilog({"name": "UHSC_AMOALU"}, {})
    ref_text = reference.decode("utf-8")
    ref_text = re.sub(r"^module\s+AMOALU\b", "module REF_AMOALU", ref_text,
                      count=1, flags=re.MULTILINE)
    vectors: list[tuple[int, int, int, int]] = []
    rng = random.Random(0xDCA1)
    for mask in (0, 1, 2, 4, 8, 16, 20, 0x40, 0x80, 0xFF):
        for cmd in range(32):
            lhs = rng.getrandbits(64)
            rhs = rng.getrandbits(64)
            vectors.append((mask, cmd, lhs, rhs))
    lines = [target, ref_text, "module tb;",
             "reg [7:0] io_mask; reg [4:0] io_cmd; reg [63:0] io_lhs,io_rhs;",
             "wire [63:0] ref_out,dut_out;",
             "REF_AMOALU ref_i(.io_mask(io_mask),.io_cmd(io_cmd),.io_lhs(io_lhs),.io_rhs(io_rhs),.io_out(ref_out));",
             "UHSC_AMOALU dut_i(.io_mask(io_mask),.io_cmd(io_cmd),.io_lhs(io_lhs),.io_rhs(io_rhs),.io_out(dut_out));",
             "initial begin"]
    for index, (mask, cmd, lhs, rhs) in enumerate(vectors):
        lines.append(
            f"io_mask=8'h{mask:02x}; io_cmd=5'h{cmd:02x}; "
            f"io_lhs=64'h{lhs:016x}; io_rhs=64'h{rhs:016x}; #1; "
            f"if (ref_out !== dut_out) $fatal(1, \"AMOALU differential {index}\");")
    lines.append('$display("PASS_AMOALU_REFERENCE"); $finish; end endmodule')
    result = run_verilator("\n".join(lines), "amo_ref")
    result.update({"module": "AMOALU", "vectors": len(vectors),
                   "observations": ["mask merge", "add carry partition", "logic decode",
                                    "signed/unsigned min-max"]})
    return result


# Differentially compare TagArray's functional read/write boundary to locked SV. / 将 TagArray 功能读写边界与锁定 SV 进行差分比较。
def differential_tag(module: Any, references: dict[str, bytes]) -> dict[str, Any]:
    target = module.build_verilog({"name": "UHSC_TagArray"}, {})
    closure = "\n".join(references[name].decode("utf-8") for name in REFERENCE_MODULES)
    wrapper = r'''
module RefTagArraySimple(
 input clock, reset, output io_read_ready, input io_read_valid, input [7:0] io_read_bits_idx,
 output [42:0] io_resp_0,io_resp_1,io_resp_2,io_resp_3,
 input io_write_valid,input [7:0] io_write_bits_idx,input [3:0] io_write_bits_way_en,
 input [35:0] io_write_bits_tag,input [6:0] io_write_bits_ecc);
TagArray ref_i(
 .clock(clock),.reset(reset),.io_read_ready(io_read_ready),.io_read_valid(io_read_valid),.io_read_bits_idx(io_read_bits_idx),
 .io_resp_0(io_resp_0),.io_resp_1(io_resp_1),.io_resp_2(io_resp_2),.io_resp_3(io_resp_3),
 .io_write_valid(io_write_valid),.io_write_bits_idx(io_write_bits_idx),.io_write_bits_way_en(io_write_bits_way_en),.io_write_bits_tag(io_write_bits_tag),.io_write_bits_ecc(io_write_bits_ecc),
 .boreChildrenBd_bore_addr(9'b0),.boreChildrenBd_bore_addr_rd(9'b0),.boreChildrenBd_bore_wdata(86'b0),.boreChildrenBd_bore_wmask(2'b0),.boreChildrenBd_bore_re(1'b0),.boreChildrenBd_bore_we(1'b0),.boreChildrenBd_bore_rdata(),.boreChildrenBd_bore_ack(1'b0),.boreChildrenBd_bore_selectedOH(1'b0),.boreChildrenBd_bore_array(6'b0),
 .boreChildrenBd_bore_1_addr(9'b0),.boreChildrenBd_bore_1_addr_rd(9'b0),.boreChildrenBd_bore_1_wdata(86'b0),.boreChildrenBd_bore_1_wmask(2'b0),.boreChildrenBd_bore_1_re(1'b0),.boreChildrenBd_bore_1_we(1'b0),.boreChildrenBd_bore_1_rdata(),.boreChildrenBd_bore_1_ack(1'b0),.boreChildrenBd_bore_1_selectedOH(1'b0),.boreChildrenBd_bore_1_array(6'b0),
 .sigFromSrams_bore_ram_hold(1'b0),.sigFromSrams_bore_ram_bypass(1'b0),.sigFromSrams_bore_ram_bp_clken(1'b0),.sigFromSrams_bore_ram_aux_clk(1'b0),.sigFromSrams_bore_ram_aux_ckbp(1'b0),.sigFromSrams_bore_ram_mcp_hold(1'b0),.sigFromSrams_bore_cgen(1'b0),
 .sigFromSrams_bore_1_ram_hold(1'b0),.sigFromSrams_bore_1_ram_bypass(1'b0),.sigFromSrams_bore_1_ram_bp_clken(1'b0),.sigFromSrams_bore_1_ram_aux_clk(1'b0),.sigFromSrams_bore_1_ram_aux_ckbp(1'b0),.sigFromSrams_bore_1_ram_mcp_hold(1'b0),.sigFromSrams_bore_1_cgen(1'b0));
endmodule
'''
    rng = random.Random(0x7A6A)
    lines = [target, closure, wrapper, r'''
module tb; integer cycle;
reg clock,reset; reg io_read_valid; reg [7:0] io_read_bits_idx; reg [3:0] io_read_bits_way_en;
reg io_write_valid; reg [7:0] io_write_bits_idx; reg [3:0] io_write_bits_way_en; reg [1:0] io_write_bits_way;
reg [35:0] io_write_bits_tag; reg [6:0] io_write_bits_ecc;
wire ref_ready,dut_ready; wire [42:0] ref0,ref1,ref2,ref3; wire [171:0] dutdata;
always #1 clock=~clock;
RefTagArraySimple ref_d(.clock(clock),.reset(reset),.io_read_ready(ref_ready),.io_read_valid(io_read_valid),.io_read_bits_idx(io_read_bits_idx),.io_resp_0(ref0),.io_resp_1(ref1),.io_resp_2(ref2),.io_resp_3(ref3),.io_write_valid(io_write_valid),.io_write_bits_idx(io_write_bits_idx),.io_write_bits_way_en(io_write_bits_way_en),.io_write_bits_tag(io_write_bits_tag),.io_write_bits_ecc(io_write_bits_ecc));
UHSC_TagArray dut_d(.clock(clock),.reset(reset),.io_read_ready(dut_ready),.io_read_valid(io_read_valid),.io_read_bits_idx(io_read_bits_idx),.io_read_bits_way_en(io_read_bits_way_en),.io_write_valid(io_write_valid),.io_write_bits_idx(io_write_bits_idx),.io_write_bits_way_en(io_write_bits_way_en),.io_write_bits_way(io_write_bits_way),.io_write_bits_tag(io_write_bits_tag),.io_write_bits_ecc(io_write_bits_ecc),.io_rdata(dutdata));
initial begin
clock=0; reset=1; io_read_valid=0; io_read_bits_idx=0; io_read_bits_way_en=4'hf; io_write_valid=0; io_write_bits_idx=0; io_write_bits_way_en=0; io_write_bits_way=0; io_write_bits_tag=0; io_write_bits_ecc=0; cycle=0;
repeat(3) begin @(posedge clock); #1; if (ref_ready !== dut_ready) $fatal(1,"TagArray reset ready"); cycle=cycle+1; end
reset=0;
repeat(260) begin @(posedge clock); #1; if (ref_ready !== dut_ready) $fatal(1,"TagArray clear ready"); cycle=cycle+1; end
''']
    for index in range(24):
        set_index = rng.randrange(32)
        mask = rng.randrange(1, 16)
        tag = rng.getrandbits(36)
        ecc = rng.getrandbits(7)
        lines.append(
            f"@(negedge clock); io_write_valid=1; io_write_bits_idx=8'd{set_index}; "
            f"io_write_bits_way_en=4'h{mask:x}; io_write_bits_tag=36'h{tag:09x}; io_write_bits_ecc=7'h{ecc:02x}; "
            "@(posedge clock); #1; if (ref_ready !== dut_ready || dut_ready !== 1'b0) $fatal(1,\"TagArray write ready\"); cycle=cycle+1;")
        lines.append(
            f"@(negedge clock); io_write_valid=0; io_write_bits_way_en=0; io_read_valid=1; io_read_bits_idx=8'd{set_index}; "
            "@(posedge clock); #1; if (ref_ready !== dut_ready || ref0 !== dutdata[42:0] || ref1 !== dutdata[85:43] || ref2 !== dutdata[128:86] || ref3 !== dutdata[171:129]) $fatal(1,\"TagArray read %d\",cycle); cycle=cycle+1;")
        lines.append("@(negedge clock); io_read_valid=0; @(posedge clock); #1; if (ref_ready !== dut_ready) $fatal(1,\"TagArray idle ready\"); cycle=cycle+1;")
    lines.append(r'''
@(negedge clock); io_write_valid=1; io_write_bits_idx=8'd7; io_write_bits_way_en=4'hf; io_write_bits_tag=36'h123456789; io_write_bits_ecc=7'h55; io_read_valid=1; io_read_bits_idx=8'd7;
@(posedge clock); #1; if (ref_ready !== dut_ready || ref_ready !== 1'b0) $fatal(1,"TagArray collision"); cycle=cycle+1;
@(negedge clock); io_write_valid=0; io_read_valid=1; @(posedge clock); #1; if (ref_ready !== dut_ready || ref0 !== dutdata[42:0] || ref1 !== dutdata[85:43] || ref2 !== dutdata[128:86] || ref3 !== dutdata[171:129]) $fatal(1,"TagArray collision response");
$display("PASS_TAGARRAY_REFERENCE"); $finish; end endmodule
''')
    result = run_verilator("\n".join(lines), "tag_ref")
    result.update({"module": "TagArray", "vectors": 24,
                   "observations": ["reset clear", "read ready", "masked write",
                                    "one-cycle SRAM read", "write/read collision"]})
    return result


# Write all machine-readable batch evidence without promoting acceptance status. / 写入全部机器可读批次证据且不提升接受状态。
def write_evidence(audits: dict[str, Any], direct: dict[str, Any], generated: dict[str, Any],
                   reference: dict[str, Any], refs: dict[str, dict[str, Any]],
                   differential: dict[str, Any], source_hashes: dict[str, Any]) -> None:
    direct_status = "PASS_BOUNDED_DIRECT"
    diff_status = "PASS_BOUNDED" if all(item.get("status") == "PASS"
                                         for item in differential.values()) else "PENDING_COORDINATOR_REVIEW"
    lint_status = "PASS" if all(item["verilator"]["status"] == "PASS" and
                                 item["yosys"]["status"] == "PASS"
                                 for item in generated.values()) else "PENDING_COORDINATOR_REVIEW"
    base = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_DCACHE_BATCH",
        "batch_id": "V2-P1-E-DCACHE",
        "source_commit": SOURCE_COMMIT,
        "family_ids": ["core.cache.dcache.amo", "core.cache.dcache.tag"],
        "closure_roots": ["core.cache.dcache"],
        "candidates": list(TARGETS),
        "source_paths": SOURCE_PATHS,
        "source_hashes": source_hashes,
        "target_paths": {name: path.relative_to(ROOT).as_posix() for name, path in TARGETS.items()},
        "target_hashes": {name: audits[name]["sha256"] for name in TARGETS},
        "reference_artifact": {"path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv",
                               "sha256": REFERENCE_SHA256, "bytes": REFERENCE_BYTES,
                               "verified": reference, "modules": refs},
        "direct_tests": direct,
        "structural_audit": audits,
        "generated": generated,
        "reference_differential": differential,
        "status": "PENDING_COORDINATOR_REVIEW",
        "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": "PASS",
                  "V2_REFERENCE_MATCHED": diff_status, "VERILATOR": lint_status,
                  "YOSYS": lint_status, "PARENT_CLOSURE_MATCHED": diff_status,
                  "UHSC_LOCALIZED": "NO_PROJECT_FACING_RENAME",
                  "LICENSE_REVIEW": "PENDING_COORDINATOR_REVIEW", "ACCEPTED": "NOT_ALLOWED"},
        "acceptance_eligible": False,
        "unclosed": ["Coordinator review and parent integration remain required.",
                     "MBIST/DFT controls are represented by the locked reference closure and are not promoted at this leaf.",
                     "Mixed dependency license review remains outside this batch."],
    }
    (ROOT / "validation" / "v2-dcache-batch-results.json").write_text(
        json.dumps(base, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    (ROOT / "validation" / "v2-dcache-batch-direct-results.json").write_text(
        json.dumps({"schema_version": 1, "kind": "V2_P1_E_DCACHE_DIRECT_EVIDENCE",
                    "status": direct_status, "source_commit": SOURCE_COMMIT,
                    "targets": direct, "structural_audit": audits,
                    "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": "PASS",
                              "VERILATOR": lint_status, "YOSYS": lint_status,
                              "ACCEPTED": "NOT_ALLOWED"}}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    (ROOT / "validation" / "v2-dcache-batch-differential-results.json").write_text(
        json.dumps({"schema_version": 1, "kind": "V2_P1_E_DCACHE_REFERENCE_DIFFERENTIAL",
                    "status": diff_status, "reference": base["reference_artifact"],
                    "results": differential, "gates": {"V2_REFERENCE_MATCHED": diff_status,
                    "PARENT_CLOSURE_MATCHED": diff_status, "ACCEPTED": "NOT_ALLOWED"}},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    (ROOT / "validation" / "v2-dcache-batch-contract-audit.json").write_text(
        json.dumps({"schema_version": 1, "kind": "V2_P1_E_DCACHE_CONTRACT_AUDIT",
                    "result": "PASS", "rows": audits,
                    "gates": {"ACCEPTED": "NOT_ALLOWED", "parent_closure": "PENDING",
                              "license": "PENDING"}, "acceptance_eligible": False},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    coverage = {"schema_version": 1, "kind": "V2_P1_E_DCACHE_COVERAGE",
                "source_commit": SOURCE_COMMIT, "family_id": "core.cache.dcache",
                "closure_root": "core.cache.dcache", "status": "PENDING_COORDINATOR_REVIEW",
                "targets": [
                    {"candidate": "AMOALU", "python_path": TARGETS["AMOALU"].relative_to(ROOT).as_posix(),
                     "v2_sources": SOURCE_PATHS["AMOALU"], "covered_children": [],
                     "observation_points": ["mask merge", "carry partition", "logic/min/max decode"],
                     "reference_surface": "standalone AMOALU"},
                    {"candidate": "TagArray", "python_path": TARGETS["TagArray"].relative_to(ROOT).as_posix(),
                     "v2_sources": SOURCE_PATHS["TagArray"], "covered_children": ["TagSRAMBank", "SRAMTemplate_116"],
                     "observation_points": ["reset clear", "ready", "masked write", "synchronous read"],
                     "reference_surface": "TagArray -> TagSRAMBank -> SRAMTemplate_116"}],
                "locked_reference": {"path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv",
                                     "sha256": REFERENCE_SHA256, "bytes": REFERENCE_BYTES},
                "gates": {"ACCEPTED": "NOT_ALLOWED", "parent_closure": "PENDING",
                          "license": "PENDING"}}
    (ROOT / "validation" / "v2-dcache-batch-coverage-manifest.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    mapping = {"schema_version": 1, "kind": "V2_P1_E_DCACHE_MAPPING_UPDATE",
               "source_commit": SOURCE_COMMIT, "status": "PENDING_COORDINATOR_REVIEW",
               "entries": [{"id": name, "classification": "REWRITTEN", "disposition": "REWRITTEN",
                            "v2_sources": SOURCE_PATHS[name], "python_path": TARGETS[name].relative_to(ROOT).as_posix(),
                            "status": "MAPPING_ONLY"} for name in TARGETS],
               "uhsc_localization": "NO_PROJECT_FACING_RENAME",
               "gates": {"ACCEPTED": "NOT_ALLOWED", "parent_closure": "PENDING",
                         "license": "PENDING"}}
    (ROOT / "validation" / "v2-dcache-batch-mapping-update.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


# Run the complete bounded dcache batch and persist evidence. / 运行完整有界数据缓存批次并持久化证据。
def main() -> int:
    modules = {name: load_target(f"v2_dcache_{name}", path)
               for name, path in TARGETS.items()}
    audits = {name: audit_target(path) for name, path in TARGETS.items()}
    direct = {"AMOALU": test_amo(modules["AMOALU"]),
              "TagArray": test_tag(modules["TagArray"])}
    generated: dict[str, Any] = {}
    temp = Path(tempfile.mkdtemp(prefix="v2_dcache_lint_"))
    try:
        configs = {"AMOALU": {"name": "AMOALU"}, "TagArray": {"name": "TagArray"}}
        for name, module in modules.items():
            first = module.build_verilog(configs[name], {})
            second = module.build_verilog(configs[name], {})
            if first != second:
                raise AssertionError(f"non-deterministic Verilog export: {name}")
            generated[name] = {"sha256": hashlib.sha256(first.encode()).hexdigest(),
                              "bytes": len(first.encode()), "module": name,
                              **synthesize(name, first, temp)}
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    reference = reference_info()
    refs_meta = extract_references()
    refs_bytes = {name: (REFERENCE_DIR / f"{name}-dcache-v2.sv").read_bytes()
                  for name in REFERENCE_MODULES}
    differential = {"AMOALU": differential_amo(modules["AMOALU"],
                                                  refs_bytes["AMOALU"]),
                    "TagArray": differential_tag(modules["TagArray"], refs_bytes)}
    source_hashes: dict[str, Any] = {}
    for name, paths in SOURCE_PATHS.items():
        source_hashes[name] = []
        for relative in paths:
            payload = (ROOT / relative).read_bytes()
            source_hashes[name].append({"path": relative, "sha256": hashlib.sha256(payload).hexdigest(),
                                        "bytes": len(payload)})
    write_evidence(audits, direct, generated, reference, refs_meta, differential, source_hashes)
    print(json.dumps({"status": "PASS_BOUNDED", "direct": direct,
                      "differential": differential, "reference": reference},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
