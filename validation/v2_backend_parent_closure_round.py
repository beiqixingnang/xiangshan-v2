"""Independent Backend parent-child closure round for Kunminghu V2.
昆明湖 V2 Backend 父子闭包独立验证轮次。

This round exercises the existing BackendTop boundary with explicitly
configured Decode.Instructions, Issue.EnqPolicy, and WbDataPath children.
Unlike the original zero-child writeback probe, every EXU lane is wired into
all five register-class paths and deterministic payloads are compared with an
independent SystemVerilog equation model.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import random
import subprocess
import sys
from pathlib import Path
from typing import Any

from amaranth.sim import Simulator
from amaranth.back import verilog


ROOT = Path(__file__).resolve().parents[1]
CPU = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core"
TARGET = CPU / "Build-Cpu.Backend.Top-Hardware.py"
DECODE_PATH = CPU / "Build-Cpu.Backend.Decode.Instructions-Hardware.py"
ISSUE_PATH = CPU / "Build-Cpu.Backend.Issue.EnqPolicy-Hardware.py"
WB_PATH = CPU / "Build-Cpu.Backend.Datapath.WbArbiter-Hardware.py"
WORK = ROOT / "validation/.work/v2-backend-parent-closure-round"
RESULT = ROOT / "validation/v2-backend-parent-closure-round-results.json"
MAPPING = ROOT / "validation/v2-backend-parent-closure-round-mapping.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"


def digest_bytes(value: bytes) -> str:
    """Hash generated traces and tool output reproducibly. / 可复现地计算轨迹及工具输出摘要。"""
    return hashlib.sha256(value).hexdigest()


def load_exact(path: Path, name: str) -> Any:
    """Load a source file without package aliasing. / 无包别名地加载源文件。"""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def wsl_path(path: Path) -> str:
    """Map this auxiliary repository to the stable WSL alias. / 映射到稳定 WSL 别名。"""
    return "/tmp/uhsc-v2/" + path.resolve().relative_to(ROOT.resolve()).as_posix()


def run_wsl(command: list[str], timeout: int = 240) -> dict[str, Any]:
    """Run a bounded WSL command and retain a digest. / 有界运行 WSL 命令并保留摘要。"""
    rendered = " ".join(subprocess.list2cmdline([item]) for item in command)
    try:
        result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered], capture_output=True,
                                timeout=timeout, check=False)
        output = (result.stdout + result.stderr).decode("utf-8", "replace")
        return {"command": command, "returncode": result.returncode,
                "status": "PASS" if result.returncode == 0 else "FAIL",
                "output_tail": output[-1600:], "output_sha256": digest_bytes(output.encode())}
    except (OSError, subprocess.TimeoutExpired) as error:
        text = str(error)
        return {"command": command, "returncode": None, "status": "FAIL",
                "output_tail": text, "output_sha256": digest_bytes(text.encode())}


def make_vectors(count: int = 128) -> list[dict[str, Any]]:
    """Create deterministic Decode/Issue/WB vectors with collision coverage. / 创建覆盖冲突的确定性向量。"""
    rng = random.Random(0xBACE_2C26)
    vectors: list[dict[str, Any]] = []
    for index in range(count):
        # Two fixed vectors cover each register class and same-port priority.
        if index < 5:
            classes = [index, index, 7, 7, 7, 7, 7, 7]
            ports = [0, 0, 0, 0, 0, 0, 0, 0]
            valid = [True, True, False, False, False, False, False, False]
        else:
            classes = [rng.randrange(5) if rng.randrange(4) else 7 for _ in range(8)]
            ports = [rng.randrange(5) for _ in range(8)]
            valid = [bool(rng.randrange(2)) for _ in range(8)]
        vectors.append({
            "instruction": rng.getrandbits(32),
            "free_slots": rng.randrange(1 << 22),
            "flush": bool(index % 19 == 0),
            "exu_valid": valid,
            "exu_data": [rng.getrandbits(64) for _ in range(8)],
            "exu_pdest": [rng.randrange(256) for _ in range(8)],
            "exu_class": classes,
            "exu_port": ports,
        })
    return vectors


def model(vector: dict[str, Any], decode: Any) -> dict[str, Any]:
    """Compute independent child boundary equations. / 计算独立子边界方程。"""
    matches = sum(int(decode.match32(pattern, vector["instruction"])) << bit
                  for bit, pattern in enumerate(decode.PATTERNS.values()))
    writeback: list[dict[str, int]] = []
    # WbDataPath uses its configured physical-port map, not the parent's
    # dynamic wbPort field.  Port zero therefore receives EXU slots 0 and 5;
    # the child currently exposes only that first physical port per class.
    port_zero_slots = [0, 5]
    for rf_class in range(5):
        valid: list[int] = []
        for port in range(5):
            slots = [i for i in range(8) if [0, 1, 2, 3, 4, 0, 1, 2][i] == port]
            candidates = [i for i in slots if vector["exu_valid"][i] and vector["exu_class"][i] == rf_class]
            selected = candidates[0] if candidates else None
            valid.append(int(selected is not None))
        writeback.append({"valid": valid})
    selected_data: list[list[int]] = []
    selected_pdest: list[list[int]] = []
    for rf_class in range(5):
        data_row: list[int] = []
        pdest_row: list[int] = []
        for port in range(5):
            slots = [i for i in range(8) if [0, 1, 2, 3, 4, 0, 1, 2][i] == port]
            candidates = [i for i in slots if vector["exu_valid"][i] and vector["exu_class"][i] == rf_class]
            selected = candidates[0] if candidates else None
            fallback = slots[-1] if slots else 0
            data_row.append(vector["exu_data"][selected if selected is not None else fallback])
            pdest_row.append(vector["exu_pdest"][selected if selected is not None else fallback])
        selected_data.append(data_row)
        selected_pdest.append(pdest_row)
    return {
        "decode_instruction": vector["instruction"],
        "decode_matches": matches,
        "issue_can_enq": vector["free_slots"],
        "issue_selected_valid": int(bool(vector["free_slots"])),
        "issue_selected_bits": vector["free_slots"] & (-vector["free_slots"]),
        "writeback_valid": [item["valid"] for item in writeback],
        "writeback_data": selected_data,
        "writeback_pdest": selected_pdest,
    }


def direct_check(target: Any, decode: Any, issue_cls: Any, wb: Any,
                 vectors: list[dict[str, Any]]) -> dict[str, Any]:
    """Run Amaranth direct checks over all child observations. / 运行全部子观测的 Amaranth direct 检查。"""
    attrs = tuple(wb.WbExuAttr(name=f"exu{i}", writeIntRf=True, writeFpRf=True,
                               writeVfRf=True, writeV0Rf=True, writeVlRf=True)
                  for i in range(8))
    config = wb.WbDataPathConfig(intExus=attrs, fpExus=(), vfExus=(), memExus=(),
                                 intWbPorts=tuple([0, 1, 2, 3, 4, 0, 1, 2]), intPortMax=4,
                                 fpWbPorts=tuple([0, 1, 2, 3, 4, 0, 1, 2]), fpPortMax=4,
                                 vfWbPorts=tuple([0, 1, 2, 3, 4, 0, 1, 2]), vfPortMax=4,
                                 v0WbPorts=tuple([0, 1, 2, 3, 4, 0, 1, 2]), v0PortMax=4,
                                 vlWbPorts=tuple([0, 1, 2, 3, 4, 0, 1, 2]), vlPortMax=4)
    dependencies = {"decode": decode.InstructionPatternProbe(), "issue": issue_cls.EnqPolicy(),
                    "writeback": wb.WbDataPath(config)}
    top = target.BackendTop(injected_dependencies=dependencies)
    observed: list[dict[str, Any]] = []

    async def bench(ctx: Any) -> None:
        for index, vector in enumerate(vectors):
            ctx.set(top.frontend_instr, vector["instruction"])
            ctx.set(top.child_issue_free_slots, vector["free_slots"])
            ctx.set(top.flush, int(vector["flush"]))
            for lane in range(8):
                ctx.set(top.exu_valid[lane], int(vector["exu_valid"][lane]))
                ctx.set(top.exu_data[lane], vector["exu_data"][lane])
                ctx.set(top.exu_pdest[lane], vector["exu_pdest"][lane])
                ctx.set(top.exu_class[lane], vector["exu_class"][lane])
                ctx.set(top.exu_port[lane], vector["exu_port"][lane])
            await ctx.delay(1e-9)
            expected = model(vector, decode)
            got = {
                "decode_instruction": int(ctx.get(top.child_decode_instruction)),
                "decode_matches": int(ctx.get(top.child_decode_matches)),
                "issue_can_enq": int(ctx.get(top.child_issue_can_enq)),
                "issue_selected_valid": int(ctx.get(top.child_issue_selected_valid)),
                "issue_selected_bits": int(ctx.get(top.child_issue_selected_bits)),
                "writeback_valid": [[int(ctx.get(top.child_writeback_valid[c]))] for c in range(5)],
                "writeback_data": [[int(ctx.get(top.child_writeback_data[c]))] for c in range(5)],
                "writeback_pdest": [[int(ctx.get(top.child_writeback_pdest[c]))] for c in range(5)],
            }
            # Parent exposes the first physical port of each class at its child
            # observation point; compare that port and retain all five classes.
            expected_first = {
                "decode_instruction": expected["decode_instruction"],
                "decode_matches": expected["decode_matches"],
                "issue_can_enq": expected["issue_can_enq"],
                "issue_selected_valid": expected["issue_selected_valid"],
                "issue_selected_bits": expected["issue_selected_bits"],
                "writeback_valid": [[expected["writeback_valid"][c][0]] for c in range(5)],
                "writeback_data": [[expected["writeback_data"][c][0]] for c in range(5)],
                "writeback_pdest": [[expected["writeback_pdest"][c][0]] for c in range(5)],
            }
            if got != expected_first:
                raise AssertionError((index, got, expected_first))
            observed.append(got)

    simulator = Simulator(top)
    simulator.add_clock(1e-6, domain="sync")
    simulator.add_testbench(bench)
    simulator.run()
    trace = json.dumps(observed, sort_keys=True, separators=(",", ":")).encode()
    return {"status": "PASS", "vectors": len(vectors), "checks": len(vectors) * 8,
            "trace_sha256": digest_bytes(trace), "trace_head": observed[:2], "trace_tail": observed[-2:]}


def child_rtl(target: Any, decode: Any, issue_cls: Any, wb: Any) -> tuple[Path, Any]:
    """Emit the configured parent-child boundary RTL. / 导出配置化父子边界 RTL。"""
    attrs = tuple(wb.WbExuAttr(name=f"exu{i}", writeIntRf=True, writeFpRf=True,
                               writeVfRf=True, writeV0Rf=True, writeVlRf=True)
                  for i in range(8))
    config = wb.WbDataPathConfig(intExus=attrs, intWbPorts=(0, 1, 2, 3, 4, 0, 1, 2), intPortMax=4,
                                 fpWbPorts=(0, 1, 2, 3, 4, 0, 1, 2), fpPortMax=4,
                                 vfWbPorts=(0, 1, 2, 3, 4, 0, 1, 2), vfPortMax=4,
                                 v0WbPorts=(0, 1, 2, 3, 4, 0, 1, 2), v0PortMax=4,
                                 vlWbPorts=(0, 1, 2, 3, 4, 0, 1, 2), vlPortMax=4)
    dependencies = {"decode": decode.InstructionPatternProbe(), "issue": issue_cls.EnqPolicy(),
                    "writeback": wb.WbDataPath(config)}
    top = target.BackendTop(injected_dependencies=dependencies)
    ports = [top.frontend_instr, top.child_issue_free_slots, top.flush, top.child_decode_instruction,
             top.child_decode_matches, top.child_issue_can_enq, top.child_issue_selected_valid,
             top.child_issue_selected_bits, *top.child_writeback_valid, *top.child_writeback_data,
             *top.child_writeback_pdest, *top.exu_valid, *top.exu_data, *top.exu_pdest,
             *top.exu_class, *top.exu_port]
    rtl = verilog.convert(top, name="UHSCBackendParentClosureRound", ports=ports, emit_src=False)
    WORK.mkdir(parents=True, exist_ok=True)
    rtl_path = WORK / "backend-parent-closure-round.sv"
    rtl_path.write_text(rtl, encoding="utf-8", newline="\n")
    return rtl_path, top


def reference_sv(decode: Any) -> str:
    """Generate independent SV equations for Decode/Issue/WB observations. / 生成独立 SV 方程。"""
    patterns: list[str] = []
    for bit, pattern in enumerate(decode.PATTERNS.values()):
        mask, expected = decode.pattern_mask_expected(pattern)
        patterns.append(f"(((io_frontend_instr & 32'h{mask:08x}) == 32'h{expected:08x}) ? (32'h1 << {bit}) : 32'h0)")
    lines = ["module BackendParentClosureReference(",
             "io_frontend_instr,io_child_issue_freeSlots,io_flush_valid,io_child_decode_instruction,io_child_decode_matches,io_child_issue_canEnq,io_child_issue_selected_valid,io_child_issue_selected_bits,"]
    lines.append(",".join([f"io_child_writeback_{i}_valid" for i in range(5)] +
                           [f"io_child_writeback_{i}_data" for i in range(5)] +
                           [f"io_child_writeback_{i}_pdest" for i in range(5)] +
                           [f"io_fromExu_{i}_valid" for i in range(8)] +
                           [f"io_fromExu_{i}_data" for i in range(8)] +
                           [f"io_fromExu_{i}_pdest" for i in range(8)] +
                           [f"io_fromExu_{i}_rfClass" for i in range(8)] +
                           [f"io_fromExu_{i}_wbPort" for i in range(8)]) + ");")
    lines += ["input [31:0] io_frontend_instr; input [21:0] io_child_issue_freeSlots; input io_flush_valid;",
              "output [31:0] io_child_decode_instruction,io_child_decode_matches; output [21:0] io_child_issue_canEnq;",
              "output io_child_issue_selected_valid; output [21:0] io_child_issue_selected_bits;"]
    for i in range(5):
        lines += [f"output io_child_writeback_{i}_valid; output [63:0] io_child_writeback_{i}_data; output [7:0] io_child_writeback_{i}_pdest;"]
    for i in range(8):
        lines += [f"input io_fromExu_{i}_valid; input [63:0] io_fromExu_{i}_data; input [7:0] io_fromExu_{i}_pdest; input [2:0] io_fromExu_{i}_rfClass; input [2:0] io_fromExu_{i}_wbPort;"]
    lines += ["assign io_child_decode_instruction=io_frontend_instr;",
              "assign io_child_decode_matches=" + " | ".join(patterns) + ";",
              "assign io_child_issue_canEnq=io_child_issue_freeSlots;",
              "assign io_child_issue_selected_valid=|io_child_issue_freeSlots;",
              "assign io_child_issue_selected_bits=io_child_issue_freeSlots & (~io_child_issue_freeSlots + 22'd1);"]
    for c in range(5):
        terms = [f"(io_fromExu_{i}_valid && io_fromExu_{i}_rfClass==3'd{c})" for i in (0, 5)]
        lines.append(f"wire wb_{c}_0={' | '.join(terms)};")
        lines.append(f"assign io_child_writeback_{c}_valid=wb_{c}_0;")
        # RealWBArbiter defaults to its highest slot payload when no request
        # is valid, and otherwise chooses the lowest valid slot.
        data_expr = f"io_fromExu_5_data"
        pdest_expr = f"io_fromExu_5_pdest"
        data_expr = f"(io_fromExu_5_valid && io_fromExu_5_rfClass==3'd{c}) ? io_fromExu_5_data : ({data_expr})"
        pdest_expr = f"(io_fromExu_5_valid && io_fromExu_5_rfClass==3'd{c}) ? io_fromExu_5_pdest : ({pdest_expr})"
        data_expr = f"(io_fromExu_0_valid && io_fromExu_0_rfClass==3'd{c}) ? io_fromExu_0_data : ({data_expr})"
        pdest_expr = f"(io_fromExu_0_valid && io_fromExu_0_rfClass==3'd{c}) ? io_fromExu_0_pdest : ({pdest_expr})"
        lines.append(f"assign io_child_writeback_{c}_data={data_expr}; assign io_child_writeback_{c}_pdest={pdest_expr};")
    lines.append("endmodule\n")
    return "\n".join(lines)


def differential(rtl_path: Path, decode: Any, vectors: list[dict[str, Any]]) -> dict[str, Any]:
    """Compile and run configured parent-child RTL against independent SV. / 编译运行父子 RTL 差分。"""
    ref_path = WORK / "BackendParentClosureReference.sv"
    tb_path = WORK / "backend-parent-closure-round-tb.sv"
    ref_path.write_text(reference_sv(decode), encoding="utf-8", newline="\n")
    lines = ["module tb; reg [31:0] io_frontend_instr; reg [21:0] io_child_issue_freeSlots; reg io_flush_valid;"]
    for i in range(8):
        lines.append(f"reg io_fromExu_{i}_valid; reg [63:0] io_fromExu_{i}_data; reg [7:0] io_fromExu_{i}_pdest; reg [2:0] io_fromExu_{i}_rfClass; reg [2:0] io_fromExu_{i}_wbPort;")
    lines.append("wire [31:0] d_instr,r_instr,d_matches,r_matches; wire [21:0] d_can,r_can,d_bits,r_bits; wire d_sel,r_sel;")
    for i in range(5):
        lines.append(f"wire d_wv{i},r_wv{i}; wire [63:0] d_wd{i},r_wd{i}; wire [7:0] d_wp{i},r_wp{i};")
    ports = ["io_frontend_instr", "io_child_issue_freeSlots", "io_flush_valid", "io_child_decode_instruction", "io_child_decode_matches", "io_child_issue_canEnq", "io_child_issue_selected_valid", "io_child_issue_selected_bits"]
    ports += [f"io_child_writeback_{i}_valid" for i in range(5)] + [f"io_child_writeback_{i}_data" for i in range(5)] + [f"io_child_writeback_{i}_pdest" for i in range(5)]
    ports += [f"io_fromExu_{i}_valid" for i in range(8)] + [f"io_fromExu_{i}_data" for i in range(8)] + [f"io_fromExu_{i}_pdest" for i in range(8)] + [f"io_fromExu_{i}_rfClass" for i in range(8)] + [f"io_fromExu_{i}_wbPort" for i in range(8)]
    dut_conn = []
    ref_conn = []
    for p in ports:
        if p == "io_frontend_instr":
            dut_conn.append(".io_frontend_cfVec_instr(io_frontend_instr)")
            ref_conn.append(".io_frontend_instr(io_frontend_instr)")
            continue
        if p == "io_child_decode_instruction": dut_conn.append(f".{p}(d_instr)"); ref_conn.append(f".{p}(r_instr)")
        elif p == "io_child_decode_matches": dut_conn.append(f".{p}(d_matches)"); ref_conn.append(f".{p}(r_matches)")
        elif p == "io_child_issue_canEnq": dut_conn.append(f".{p}(d_can)"); ref_conn.append(f".{p}(r_can)")
        elif p == "io_child_issue_selected_valid": dut_conn.append(f".{p}(d_sel)"); ref_conn.append(f".{p}(r_sel)")
        elif p == "io_child_issue_selected_bits": dut_conn.append(f".{p}(d_bits)"); ref_conn.append(f".{p}(r_bits)")
        elif p.startswith("io_child_writeback_"):
            idx = p.split("_")[3]; field = p.split("_")[4]
            dut_conn.append(f".{p}(d_w{field[0]}{idx})"); ref_conn.append(f".{p}(r_w{field[0]}{idx})")
        else:
            dut_conn.append(f".{p}({p})"); ref_conn.append(f".{p}({p})")
    lines.append(f"UHSCBackendParentClosureRound dut_i({','.join(dut_conn)});")
    lines.append(f"BackendParentClosureReference ref_i({','.join(ref_conn)});")
    lines.append("initial begin io_frontend_instr=0; io_child_issue_freeSlots=0; io_flush_valid=0;")
    for i in range(8): lines.append(f"io_fromExu_{i}_valid=0; io_fromExu_{i}_data=0; io_fromExu_{i}_pdest=0; io_fromExu_{i}_rfClass=0; io_fromExu_{i}_wbPort=0;")
    checks = ["d_instr!==r_instr", "d_matches!==r_matches", "d_can!==r_can", "d_sel!==r_sel", "d_bits!==r_bits"]
    for i in range(5): checks += [f"d_wv{i}!==r_wv{i}", f"d_wd{i}!==r_wd{i}", f"d_wp{i}!==r_wp{i}"]
    for index, vector in enumerate(vectors):
        lines.append(f"io_frontend_instr=32'h{vector['instruction']:08x}; io_child_issue_freeSlots=22'h{vector['free_slots']:06x}; io_flush_valid={int(vector['flush'])};")
        for i in range(8):
            lines.append(f"io_fromExu_{i}_valid={int(vector['exu_valid'][i])}; io_fromExu_{i}_data=64'h{vector['exu_data'][i]:016x}; io_fromExu_{i}_pdest=8'h{vector['exu_pdest'][i]:02x}; io_fromExu_{i}_rfClass=3'd{vector['exu_class'][i]}; io_fromExu_{i}_wbPort=3'd{vector['exu_port'][i]};")
        lines.append("#1;")
        lines.append(f"if ({' || '.join(checks)}) begin $display(\"BACKEND_PARENT_CLOSURE_MISMATCH {index}\"); $fatal(1); end")
    lines += [f'$display("BACKEND_PARENT_CLOSURE_DIFF_PASS {len(vectors)}"); $finish;', "end endmodule\n"]
    tb_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    obj = WORK / "obj"
    compile_result = run_wsl(["verilator", "--binary", "--timing", "-Wno-fatal", "-Wno-WIDTHEXPAND", "-Wno-WIDTHTRUNC",
                              "--top-module", "tb", "--Mdir", wsl_path(obj), wsl_path(rtl_path), wsl_path(ref_path), wsl_path(tb_path)], timeout=360)
    if compile_result["status"] != "PASS":
        return {"status": "FAIL_COMPILE", "vectors": len(vectors), "compile": compile_result}
    run_result = run_wsl([wsl_path(obj / "Vtb")], timeout=120)
    passed = run_result["status"] == "PASS" and "BACKEND_PARENT_CLOSURE_DIFF_PASS" in run_result.get("output_tail", "")
    return {"status": "PASS" if passed else "FAIL_RUN", "vectors": len(vectors),
            "compile": compile_result, "run": run_result, "reference_mode": "independent_child_equations"}


def main() -> int:
    """Run the closure round and write evidence/mapping atomically. / 运行闭包轮次并写入证据映射。"""
    alias = run_wsl(["bash", "-lc", "ln -sfn /mnt/d/*/Unifier-Hardware-System/.agents/xiangshan-v2 /tmp/uhsc-v2"], timeout=60)
    if alias["status"] != "PASS":
        raise RuntimeError(alias)
    target = load_exact(TARGET, "v2_parent_closure_target")
    decode = load_exact(DECODE_PATH, "v2_parent_closure_decode")
    issue = load_exact(ISSUE_PATH, "v2_parent_closure_issue")
    wb = load_exact(WB_PATH, "v2_parent_closure_wb")
    vectors = make_vectors()
    direct = direct_check(target, decode, issue, wb, vectors)
    rtl_path, _top = child_rtl(target, decode, issue, wb)
    gates = {
        "verilator": run_wsl(["verilator", "--lint-only", "-Wno-fatal", wsl_path(rtl_path)], timeout=240),
        "yosys": run_wsl(["yosys", "-p", f"read_verilog -sv {wsl_path(rtl_path)}; hierarchy -top UHSCBackendParentClosureRound; proc; check"], timeout=240),
    }
    gates["status"] = "PASS" if all(gate["status"] == "PASS" for gate in gates.values()) else "FAIL"
    diff = differential(rtl_path, decode, vectors)
    status = "PASS_BOUNDED_PARENT_CLOSURE" if direct["status"] == "PASS" and diff["status"] == "PASS" and gates["status"] == "PASS" else "FAIL"
    payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_BACKEND_PARENT_CLOSURE_ROUND",
               "batch_id": "V2-PARENT-BACKEND-CLOSURE-002", "source_commit": SOURCE_COMMIT,
               "locked_reference": {"canonical_path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv", "sha256": XSTOP_SHA256, "immutable": True},
               "targets": {"parent": TARGET.relative_to(ROOT).as_posix(), "children": [DECODE_PATH.relative_to(ROOT).as_posix(), ISSUE_PATH.relative_to(ROOT).as_posix(), WB_PATH.relative_to(ROOT).as_posix()]},
               "direct": direct, "differential": diff, "tool_gates": gates,
               "child_wiring": {"decode": "PASS", "issue": "PASS", "writeback": "PASS", "writeback_classes": 5, "writeback_ports_checked": 1},
               "status": status, "behavioral_status": "BOUNDED_CHILD_SIGNAL_FLOW", "acceptance_eligible": False,
               "unclosed": ["Backend full 1165-port behavior still requires Rename/CSR/Exu/Memory closure.", "Only first physical port per register class is exposed by the parent child observation surface.", "License review and user approval remain pending."]}
    RESULT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    MAPPING.write_text(json.dumps({"schema_version": 1, "kind": "V2_BACKEND_PARENT_CLOSURE_MAPPING", "batch_id": payload["batch_id"], "source_commit": SOURCE_COMMIT,
                                   "entries": [{"source": "Backend.scala", "target": TARGET.relative_to(ROOT).as_posix(), "children": ["Decode.Instructions", "Issue.EnqPolicy", "WbDataPath"], "status": status}],
                                   "gates": {"STRUCTURE_VERIFIED": status, "BEHAVIOR_VERIFIED_BackendChild": status, "ACCEPTED": "NOT_ALLOWED"}, "acceptance_eligible": False}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": status, "vectors": len(vectors), "direct": direct["status"], "differential": diff["status"], "verilator": gates["verilator"]["status"], "yosys": gates["yosys"]["status"], "ACCEPTED": "NOT_ALLOWED"}, sort_keys=True))
    return 0 if status == "PASS_BOUNDED_PARENT_CLOSURE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
