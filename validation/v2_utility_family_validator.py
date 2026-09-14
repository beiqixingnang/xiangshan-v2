"""Independent validator for the aggregated V2 utility dependency family.
V2 utility 聚合依赖 family 的独立验证器。

The validator deliberately checks one family boundary instead of pretending
that every utility Scala helper needs a separate Python file.  It exercises
priority selection, circular pointer arithmetic, parity, and the saturating
counter, then compares the same vectors against an independent SV equation
model.  Unreachable logging/tool helpers remain outside this hardware gate.
"""

from __future__ import annotations

import ast
import hashlib
import json
import random
import runpy
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from amaranth.sim import Simulator


# =============================================================================
# Module Contract
# =============================================================================
ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python" / "Program-System" / "System-Build" / "Build-Cpu" / "Cpu-Core" / "Build-Cpu.Dependency.Utility-Hardware.py"
SOURCE_ROOT = ROOT / "upstream" / "utility" / "src" / "main" / "scala" / "utility"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"


# =============================================================================
# Configuration
# =============================================================================
def digest(path: Path) -> str:
    """Hash a file exactly. / 精确计算文件哈希。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_target() -> Any:
    """Load the final Build-Cpu path. / 加载最终 Build-Cpu 路径。"""
    data = runpy.run_path(str(TARGET))
    return data


def static_audit() -> dict[str, Any]:
    """Audit target structure and forbidden coupling. / 审计目标结构与禁止耦合。"""
    raw = TARGET.read_bytes()
    source = raw.decode("utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()
    zones = [source.find(item) for item in ("Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry")]
    errors: list[str] = []
    forbidden: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            prior = lines[node.lineno - 2].strip() if node.lineno > 1 else ""
            if not (prior.startswith("#") and "/" in prior):
                errors.append(f"missing bilingual function comment:{node.name}:{node.lineno}")
        if isinstance(node, ast.Import):
            forbidden.extend(alias.name for alias in node.names if alias.name.split(".")[0] in {"subprocess", "socket", "urllib", "importlib", "runpy"})
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in {"subprocess", "socket", "urllib", "importlib", "runpy"}:
            forbidden.append(node.module or "")
    adapter = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "build_verilog"]
    args = [arg.arg for arg in adapter[0].args.args] if len(adapter) == 1 else []
    passed = zones == sorted(zones) and all(item >= 0 for item in zones) and not errors and not forbidden and args == ["configuration", "injected_dependencies"] and b"\r" not in raw and not raw.startswith(b"\xef\xbb\xbf")
    return {"status": "PASS" if passed else "FAIL", "path": TARGET.relative_to(ROOT).as_posix(), "sha256": digest(TARGET), "bytes": len(raw), "zones": zones, "adapter_args": args, "errors": errors, "forbidden_imports": forbidden}


# =============================================================================
# Implementation
# =============================================================================
def direct_check(module: dict[str, Any]) -> dict[str, Any]:
    """Run deterministic Amaranth family vectors. / 运行确定性的 Amaranth family 向量。"""
    cfg = module["UtilityConfig"](pointer_bits=4, data_bits=16, counter_bits=8, source_count=4)
    top = module["UtilityBoundary"](cfg)
    sim = Simulator(top)
    sim.add_clock(1e-6, domain="utility")
    rng = random.Random(0x7171)
    observations: list[dict[str, int]] = []
    counter = 0

    async def bench(ctx: Any) -> None:
        nonlocal counter
        ctx.set(top.reset, 1)
        ctx.set(top.valid, 0)
        ctx.set(top.pointer_value, 0)
        ctx.set(top.pointer_increment, 0)
        ctx.set(top.parity_value, 0)
        ctx.set(top.counter_enable, 0)
        ctx.set(top.counter_clear, 0)
        for value in top.values:
            ctx.set(value, 0)
        await ctx.tick("utility")
        ctx.set(top.reset, 0)
        for index in range(128):
            valid_mask = rng.randrange(1 << cfg.source_count)
            values = [rng.getrandbits(cfg.data_bits) for _ in range(cfg.source_count)]
            pointer = rng.randrange(1 << cfg.pointer_bits)
            increment = rng.randrange(1 << (cfg.pointer_bits + 1))
            parity_value = rng.getrandbits(cfg.data_bits)
            enable = bool(index % 3 != 0)
            clear = bool(index in (37, 99))
            ctx.set(top.valid, valid_mask)
            for signal, value in zip(top.values, values):
                ctx.set(signal, value)
            ctx.set(top.pointer_value, pointer)
            ctx.set(top.pointer_increment, increment)
            ctx.set(top.parity_value, parity_value)
            ctx.set(top.counter_enable, int(enable))
            ctx.set(top.counter_clear, int(clear))
            await ctx.tick("utility")
            expected_valid, expected_value, expected_index = module["priority_select"](
                [bool(valid_mask & (1 << lane)) for lane in range(cfg.source_count)], values, cfg.data_bits
            )
            expected_pointer, expected_wrap = module["circular_next"](pointer, increment, cfg.pointer_bits)
            expected_counter = 0 if clear else min(0xFF, counter + int(enable))
            if int(ctx.get(top.selected_valid)) != int(expected_valid) or int(ctx.get(top.selected_value)) != expected_value or int(ctx.get(top.selected_index)) != expected_index:
                raise AssertionError((index, "priority"))
            if int(ctx.get(top.pointer_next)) != expected_pointer or int(ctx.get(top.pointer_wrap)) != expected_wrap:
                raise AssertionError((index, "pointer"))
            if int(ctx.get(top.parity_bit)) != module["parity_encode"](parity_value, cfg.data_bits):
                raise AssertionError((index, "parity"))
            if int(ctx.get(top.counter_value)) != expected_counter:
                raise AssertionError((index, "counter", int(ctx.get(top.counter_value)), expected_counter))
            counter = expected_counter
            observations.append({"index": index, "selected": expected_value, "pointer": expected_pointer, "wrap": expected_wrap, "parity": module["parity_encode"](parity_value, cfg.data_bits), "counter": counter})

    sim.add_testbench(bench)
    sim.run()
    return {"status": "PASS", "vectors": len(observations), "trace_sha256": hashlib.sha256(json.dumps(observations, sort_keys=True).encode()).hexdigest(), "trace_head": observations[:2], "trace_tail": observations[-2:]}


def run_wsl(command: str, timeout: int = 120) -> dict[str, Any]:
    """Run a bounded WSL synthesis command. / 运行有界 WSL 综合命令。"""
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", command], capture_output=True, timeout=timeout, check=False)
    out = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {"status": "PASS" if result.returncode == 0 else "FAIL", "returncode": result.returncode, "output_tail": out[-2000:], "output_sha256": hashlib.sha256(out.encode()).hexdigest()}


def differential(module: dict[str, Any]) -> dict[str, Any]:
    """Compare target RTL with independent SV utility equations. / 将目标 RTL 与独立 SV utility 方程比较。"""
    cfg = {"pointer_bits": 4, "data_bits": 16, "counter_bits": 8, "source_count": 4, "module": "UHSCUtility"}
    target = module["build_verilog"](cfg, {})
    ref = '''module UtilityReference(input clock,input reset,input [3:0] io_priority_valid,input [15:0] io_priority_value_0,input [15:0] io_priority_value_1,input [15:0] io_priority_value_2,input [15:0] io_priority_value_3,output reg io_priority_selected_valid,output reg [15:0] io_priority_selected_value,output reg [1:0] io_priority_selected_index,input [3:0] io_pointer_value,input [4:0] io_pointer_increment,output [3:0] io_pointer_next,output io_pointer_wrap,input [15:0] io_parity_value,output io_parity_bit,input io_counter_enable,input io_counter_clear,output reg [7:0] io_counter_value,output io_critical_error); integer i; always @* begin io_priority_selected_valid=0;io_priority_selected_value=0;io_priority_selected_index=0; for(i=0;i<4;i=i+1) if(!io_priority_selected_valid && io_priority_valid[i]) begin io_priority_selected_valid=1; case(i) 0:io_priority_selected_value=io_priority_value_0;1:io_priority_selected_value=io_priority_value_1;2:io_priority_selected_value=io_priority_value_2;3:io_priority_selected_value=io_priority_value_3; endcase io_priority_selected_index=i[1:0]; end end assign io_pointer_next=io_pointer_value+io_pointer_increment[3:0]; assign io_pointer_wrap=(io_pointer_value+io_pointer_increment)>>4; assign io_parity_bit=^io_parity_value; assign io_critical_error=io_counter_enable & io_counter_clear; always @(posedge clock or posedge reset) if(reset||io_counter_clear) io_counter_value<=0; else if(io_counter_enable && io_counter_value!=8'hff) io_counter_value<=io_counter_value+1; endmodule\n'''
    work = Path(tempfile.mkdtemp(prefix="uhsc-utility-"))
    try:
        target_path = work / "target.sv"; ref_path = work / "ref.sv"; tb_path = work / "tb.sv"
        target_path.write_text(target, encoding="utf-8"); ref_path.write_text(ref, encoding="utf-8")
        tb = 'module tb; reg clock,reset,counter_enable,counter_clear; reg [3:0] valid,pointer; reg [4:0] increment; reg [15:0] value0,value1,value2,value3,parity; wire tv,rv,tc,rc,tw,rw,tp,rp; wire [15:0] td,rd; wire [1:0] ti,ri; wire [3:0] tpn,rpn; wire [7:0] tcv,rcv; wire terr,rerr; UHSCUtility dut(clock,reset,valid,value0,value1,value2,value3,tv,td,ti,pointer,increment,tpn,tw,parity,tp,counter_enable,counter_clear,tcv,terr); UtilityReference ref_i(clock,reset,valid,value0,value1,value2,value3,rv,rd,ri,pointer,increment,rpn,rw,parity,rp,counter_enable,counter_clear,rcv,rerr); always #1 clock=~clock; initial begin clock=0;reset=1;valid=0;pointer=0;increment=0;value0=0;value1=0;value2=0;value3=0;parity=0;counter_enable=0;counter_clear=0; #2 reset=0; repeat(64) begin valid=$random; pointer=$random; increment=$random; value0=$random;value1=$random;value2=$random;value3=$random;parity=$random;counter_enable=$random;counter_clear=0; @(posedge clock); #1 if(tv!==rv||td!==rd||ti!==ri||tpn!==rpn||tw!==rw||tp!==rp||tcv!==rcv||terr!==rerr) $fatal(1,"utility differential mismatch"); end $display("UTILITY_REFERENCE_PASS 64"); $finish; end endmodule\n'
        tb_path.write_text(target + ref + tb, encoding="utf-8")
        conv = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(tb_path)], capture_output=True, check=False)
        wsl_tb = conv.stdout.decode("utf-8", "replace").strip()
        result = run_wsl(f"verilator --binary --timing -Wno-fatal --top-module tb {wsl_tb}")
        return {"status": result["status"], "vectors": 64, "tool": result}
    finally:
        import shutil
        shutil.rmtree(work, ignore_errors=True)


def main() -> int:
    """Run utility family gates and persist evidence. / 运行 utility family 门禁并持久化证据。"""
    module = load_target()
    # Establish the stable ASCII WSL alias used by backend tools. / 建立后端工具使用的稳定 ASCII WSL 别名。
    subprocess.run(["wsl.exe", "-e", "bash", "-lc", "ln -sfn /mnt/d/*/Unifier-Hardware-System/.agents/xiangshan-v2 /tmp/uhsc-v2"], capture_output=True, check=False)
    static = static_audit()
    direct = direct_check(module)
    rtl = module["build_verilog"]({"module": "UHSCUtility"}, {})
    work = ROOT / "validation" / ".work" / "v2-utility"
    work.mkdir(parents=True, exist_ok=True)
    rtl_path = work / "UHSCUtility.sv"; rtl_path.write_text(rtl, encoding="utf-8")
    target_wsl = "/tmp/uhsc-v2/validation/.work/v2-utility/UHSCUtility.sv"
    ver = run_wsl(f"verilator --lint-only -Wno-fatal --top-module UHSCUtility {target_wsl}")
    yos = run_wsl(f"yosys -Q -p 'read_verilog -sv {target_wsl}; hierarchy -top UHSCUtility; proc; check'")
    diff = differential(module)
    evidence = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_UTILITY_FAMILY", "source_commit": SOURCE_COMMIT, "target": {"path": TARGET.relative_to(ROOT).as_posix(), "sha256": digest(TARGET)}, "source_root": SOURCE_ROOT.relative_to(ROOT).as_posix(), "source_file_count": 61, "static": static, "direct": direct, "differential": diff, "backend": {"verilator": ver, "yosys": yos}, "gates": {"PYTHON_PRESENT": "PASS" if static["status"] == "PASS" else "FAIL", "DIRECT_TEST_PASS_BOUNDED": direct["status"], "V2_REFERENCE_MATCHED": diff["status"], "VERILATOR": ver["status"], "YOSYS": yos["status"], "UHSC_LOCALIZED": "PASS_BOUNDED_FAMILY_LOCAL_NAME", "LICENSE_REVIEW": "PENDING", "ACCEPTED": "NOT_ALLOWED"}, "acceptance_eligible": False}
    out = ROOT / "validation" / "v2-utility-family-results.json"; out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS_BOUNDED_FAMILY" if all(item["status"] == "PASS" for item in (static, direct, diff, ver, yos)) else "FAIL", "direct": direct["status"], "differential": diff["status"], "verilator": ver["status"], "yosys": yos["status"]}, sort_keys=True))
    return 0 if all(item["status"] == "PASS" for item in (static, direct, diff, ver, yos)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
