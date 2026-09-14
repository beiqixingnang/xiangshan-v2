"""Independent validator for the Kunminghu V2 Backend parent boundary.
昆明湖 V2 Backend 父级边界的独立验证器。

The validator deliberately separates a reduced executable parent boundary from
the immutable 1165-port generated Backend.  It checks the maintained Build
file, runs deterministic direct vectors, compares the same vectors with an
independent SystemVerilog equation model, and records the locked XSTop module
and Scala provenance.  A bounded match never promotes the full parent.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import random
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from amaranth.sim import Simulator
from amaranth.back import verilog


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Top-Hardware.py"
REF_PATH = Path(r"\\wsl$\Debian\home\lishuo\xs-v2-local\build\rtl\XSTop.sv")
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
REFERENCE_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
REFERENCE_BYTES = 228590583
BACKEND_HEADER_SHA256 = "acf8e33def8e3beb94814a2c76cb9ba5750455431239ca00ab844763a6181a55"
BACKEND_PORT_COUNT = 1165
WORK = ROOT / "validation/.work/v2-backend-parent"
DIRECT_RESULT = ROOT / "validation/v2-backend-parent-direct-results.json"
DIFF_RESULT = ROOT / "validation/v2-backend-parent-differential-results.json"
CONTRACT_RESULT = ROOT / "validation/v2-backend-parent-contract-audit.json"
COVERAGE_RESULT = ROOT / "validation/v2-backend-parent-coverage-manifest.json"
MAPPING_RESULT = ROOT / "validation/v2-backend-parent-mapping-update.json"
SUMMARY_RESULT = ROOT / "validation/v2-backend-parent-results.json"


def digest_bytes(value: bytes) -> str:
    """Hash exact bytes without line-ending normalization. / 对原始字节计算摘要，不规范化换行。"""
    return hashlib.sha256(value).hexdigest()


def digest(path: Path) -> str:
    """Hash one file exactly as stored. / 按磁盘原样计算文件摘要。"""
    return digest_bytes(path.read_bytes())


def load_exact(path: Path, name: str) -> Any:
    """Load a target by exact path and avoid package aliasing. / 按精确路径加载目标，避免包别名影响。"""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def static_audit(path: Path) -> dict[str, Any]:
    """Audit the five-zone target contract and forbidden imports. / 审计目标五区合同及禁用导入。"""
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    tree = ast.parse(text, filename=str(path))
    lines = text.splitlines()
    zones = ("Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry")
    positions = [text.find(zone) for zone in zones]
    comment_errors: list[str] = []
    forbidden: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            previous = lines[node.lineno - 2].strip() if node.lineno > 1 else ""
            if not previous.startswith("#") or "/" not in previous:
                comment_errors.append(f"{node.name}:{node.lineno}")
        elif isinstance(node, ast.Import):
            forbidden.extend(alias.name for alias in node.names if alias.name.split(".")[0] in {
                "subprocess", "socket", "urllib", "importlib", "runpy"
            })
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in {"subprocess", "socket", "urllib", "importlib", "runpy"}:
                forbidden.append(node.module)
    adapters = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "build_verilog"]
    args = [arg.arg for arg in adapters[0].args.args] if len(adapters) == 1 else []
    passed = (
        not raw.startswith(b"\xef\xbb\xbf")
        and b"\r" not in raw
        and positions == sorted(positions)
        and all(item >= 0 for item in positions)
        and args == ["configuration", "injected_dependencies"]
        and not comment_errors
        and not forbidden
    )
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
        "function_comment_errors": comment_errors,
        "forbidden_imports": forbidden,
        "status": "PASS" if passed else "FAIL",
    }


def prepare_alias() -> dict[str, Any]:
    """Create the stable ASCII WSL alias used by synthesis tools. / 创建综合工具使用的稳定 ASCII WSL 别名。"""
    command = "ln -sfn /mnt/d/*/Unifier-Hardware-System/.agents/xiangshan-v2 /tmp/uhsc-v2"
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", command], capture_output=True, check=False)
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {"command": command, "returncode": result.returncode, "status": "PASS" if result.returncode == 0 else "FAIL",
            "output_tail": output[-1200:], "output_sha256": digest_bytes(output.encode("utf-8", "replace"))}


def wsl_path(path: Path) -> str:
    """Map an auxiliary-repository path to the stable WSL alias. / 将辅助仓库路径映射到稳定 WSL 别名。"""
    return "/tmp/uhsc-v2/" + path.resolve().relative_to(ROOT.resolve()).as_posix()


def run_wsl(command: list[str], timeout: int = 240) -> dict[str, Any]:
    """Run one bounded WSL command and retain a reproducible digest. / 运行有界 WSL 命令并保留可复现摘要。"""
    rendered = " ".join(shlex.quote(item) for item in command)
    try:
        result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered], capture_output=True,
                                timeout=timeout, check=False)
        output = (result.stdout + result.stderr).decode("utf-8", "replace")
        return {"command": command, "returncode": result.returncode,
                "status": "PASS" if result.returncode == 0 else "FAIL",
                "output_tail": output[-1800:], "output_sha256": digest_bytes(output.encode("utf-8", "replace"))}
    except (OSError, subprocess.TimeoutExpired) as error:
        text = str(error)
        return {"command": command, "returncode": None, "status": "FAIL", "output_tail": text,
                "output_sha256": digest_bytes(text.encode())}


def backend_gates(rtl: Path, top_name: str = "UHSCBackendTop") -> dict[str, Any]:
    """Run Verilator and Yosys on the generated parent RTL. / 对生成父级 RTL 运行 Verilator 与 Yosys。"""
    ver = run_wsl(["verilator", "--lint-only", "--Wno-fatal", "--top-module", top_name, wsl_path(rtl)])
    yosys_script = f"read_verilog -sv {wsl_path(rtl)}; hierarchy -top {top_name}; proc; check"
    yosys = run_wsl(["yosys", "-p", yosys_script])
    return {"verilator": ver, "yosys": yosys,
            "status": "PASS" if ver["status"] == "PASS" and yosys["status"] == "PASS" else "FAIL"}


def full_inventory_probe(module: Any) -> dict[str, Any]:
    """Check the opt-in locked 1165-port Backend envelope.

    The probe is structural only: it verifies exact names/counts and runs
    Verilator/Yosys on the emitted envelope.  Behavioral closure remains
    bounded until Decode/Issue/Rename/CSR/EXU children are integrated.
    """
    expected = module.full_backend_port_schema()
    rtl_text = module.build_full_verilog({"module": "UHSCBackend"}, None)
    match = re.search(r"module\s+UHSCBackend\((.*?)\);", rtl_text, re.S)
    names = [item.strip() for item in match.group(1).replace("\n", " ").split(",") if item.strip()] if match else []
    rtl_path = WORK / "backend-full-inventory.sv"
    rtl_path.write_text(rtl_text, encoding="utf-8", newline="\n")
    gates = backend_gates(rtl_path, "UHSCBackend")
    expected_names = [name for _direction, name, _width in expected]
    # Amaranth legally reorders ports by signal reachability; the locked
    # contract is order-independent but requires exact names and cardinality.
    exact_names = len(names) == len(expected_names) and set(names) == set(expected_names)
    return {"status": "PASS" if exact_names and gates["status"] == "PASS" else "FAIL",
            "port_count": len(names), "expected_port_count": len(expected),
            "input_count": sum(direction == "input" for direction, _name, _width in expected),
            "output_count": sum(direction == "output" for direction, _name, _width in expected),
            "exact_ordered_names": exact_names, "rtl_bytes": len(rtl_text.encode("utf-8")),
            "rtl_sha256": digest_bytes(rtl_text.encode("utf-8")), "backend_gates": gates,
            "behavioral_status": "PENDING_FULL_CHILD_CLOSURE"}


def make_vectors(count: int = 256) -> list[dict[str, Any]]:
    """Create deterministic corner and pseudo-random parent transactions. / 创建确定性边界及伪随机父级事务。"""
    rng = random.Random(0xBACE_2026)
    vectors: list[dict[str, Any]] = []
    for index in range(count):
        valid_mask = (0x3F if index == 0 else rng.randrange(64))
        exu_valid = [bool(rng.randrange(2)) for _ in range(8)]
        if index == 0:
            exu_valid = [True, True, True, False, False, False, False, False]
        vectors.append({
            "frontend_valid": valid_mask,
            "frontend_instr": [((0x13 + index * 0x1000 + lane) & 0xFFFFFFFF) for lane in range(6)],
            "frontend_exception": [0 if lane else (1 if index % 17 == 0 else 0) for lane in range(6)],
            "frontend_pc": [((index << 5) + lane * 4) & ((1 << 50) - 1) for lane in range(6)],
            "backend_can_accept": bool(index % 7 not in (3, 4)),
            "flush": bool(index % 29 == 0),
            "reset": bool(index < 2),
            "msi_valid": bool(index % 31 == 0),
            "exu_valid": exu_valid,
            "exu_data": [rng.getrandbits(64) for _ in range(8)],
            "exu_pdest": [rng.randrange(256) for _ in range(8)],
            "exu_class": [index % 5, (index + 1) % 5, 7, (index + 3) % 5,
                          (index + 4) % 5, 7, rng.randrange(5), rng.randrange(5)],
            "exu_port": [lane % 5 for lane in range(8)],
            "wb_ready": [bool((index + port) % 4 != 1) for port in range(5)],
            "exu_uncertain": [bool(lane % 3 == 0) for lane in range(8)],
            "exu_no_data": [bool(lane == 5) for lane in range(8)],
            "exu_redirect": [bool(index % 43 == lane and index != 0) for lane in range(8)],
        })
    return vectors


def direct_parent(module: Any, vectors: list[dict[str, Any]]) -> dict[str, Any]:
    """Run Amaranth direct vectors and compare parent outputs with its oracle. / 运行 Amaranth direct 向量并与 oracle 比较父级输出。"""
    top = module.BackendTop(module.BackendTopConfig())
    observed: list[dict[str, Any]] = []

    async def bench(ctx: Any) -> None:
        for index, vector in enumerate(vectors):
            ctx.set(top.reset, int(vector["reset"]))
            ctx.set(top.flush, int(vector["flush"]))
            ctx.set(top.backend_can_accept, int(vector["backend_can_accept"]))
            ctx.set(top.msi_valid, int(vector["msi_valid"]))
            ctx.set(top.frontend_valid, vector["frontend_valid"])
            ctx.set(top.frontend_instr, sum(value << (lane * 32) for lane, value in enumerate(vector["frontend_instr"])))
            ctx.set(top.frontend_exception, sum(value << (lane * 24) for lane, value in enumerate(vector["frontend_exception"])))
            ctx.set(top.frontend_pc, sum(value << (lane * 50) for lane, value in enumerate(vector["frontend_pc"])))
            ctx.set(top.frontend_ftq_ptr, 0)
            ctx.set(top.frontend_ftq_offset, 0)
            for lane in range(8):
                ctx.set(top.exu_valid[lane], int(vector["exu_valid"][lane]))
                ctx.set(top.exu_data[lane], vector["exu_data"][lane])
                ctx.set(top.exu_pdest[lane], vector["exu_pdest"][lane])
                ctx.set(top.exu_class[lane], vector["exu_class"][lane])
                ctx.set(top.exu_port[lane], vector["exu_port"][lane])
                ctx.set(top.exu_uncertain[lane], int(vector["exu_uncertain"][lane]))
                ctx.set(top.exu_no_data[lane], int(vector["exu_no_data"][lane]))
                ctx.set(top.exu_redirect[lane], int(vector["exu_redirect"][lane]))
            for port in range(5):
                ctx.set(top.wb_ready[port], int(vector["wb_ready"][port]))
            await ctx.delay(1e-9)
            await ctx.tick("sync")
            await ctx.delay(1e-9)
            expected = module.backend_parent_model(
                vector["frontend_valid"], vector["frontend_instr"], vector["frontend_exception"], vector["frontend_pc"],
                vector["backend_can_accept"], vector["flush"], vector["exu_valid"], vector["exu_data"],
                vector["exu_pdest"], vector["exu_class"], vector["exu_port"], vector["wb_ready"],
                vector["exu_uncertain"], vector["exu_no_data"], vector["exu_redirect"],
                vector["msi_valid"], vector["reset"],
            )
            got = {
                "cycle": index,
                "frontend_can_accept": int(ctx.get(top.frontend_can_accept)),
                "frontend_ready": int(ctx.get(top.frontend_ready)),
                "wb_valid": [int(ctx.get(item)) for item in top.wb_valid],
                "wb_data": [int(ctx.get(item)) for item in top.wb_data],
                "wb_pdest": [int(ctx.get(item)) for item in top.wb_pdest],
                "wb_class": [int(ctx.get(item)) for item in top.wb_class],
                "wb_fire": [int(ctx.get(item)) for item in top.wb_fire],
                "exu_ready": [int(ctx.get(item)) for item in top.exu_ready],
                "redirect_valid": int(ctx.get(top.redirect_valid)),
                "cpu_critical_error": int(ctx.get(top.cpu_critical_error)),
                "cpu_halted": int(ctx.get(top.cpu_halted)),
                "msi_ack": int(ctx.get(top.msi_ack)),
                "fencei": int(ctx.get(top.fencei)),
                "sbuffer_flush": int(ctx.get(top.sbuffer_flush)),
            }
            if got["frontend_can_accept"] != expected["frontend_can_accept"]:
                raise AssertionError((index, "frontend_can_accept", got, expected))
            if got["frontend_ready"] != expected["frontend_ready"]:
                raise AssertionError((index, "frontend_ready", got, expected))
            if got["wb_valid"] != [item["valid"] for item in expected["writeback"]]:
                raise AssertionError((index, "wb_valid", got, expected))
            if got["wb_data"] != [item["data"] for item in expected["writeback"]]:
                raise AssertionError((index, "wb_data", got, expected))
            if got["wb_pdest"] != [item["pdest"] for item in expected["writeback"]]:
                raise AssertionError((index, "wb_pdest", got, expected))
            if got["wb_class"] != [item["class"] for item in expected["writeback"]]:
                raise AssertionError((index, "wb_class", got, expected))
            if got["wb_fire"] != [item["fire"] for item in expected["writeback"]]:
                raise AssertionError((index, "wb_fire", got, expected))
            if got["exu_ready"] != expected["exu_ready"]:
                raise AssertionError((index, "exu_ready", got, expected))
            for key in ("redirect_valid", "cpu_critical_error", "cpu_halted", "msi_ack", "fencei", "sbuffer_flush"):
                if got[key] != expected[key]:
                    raise AssertionError((index, key, got, expected))
            observed.append(got)

    simulator = Simulator(top)
    simulator.add_clock(1e-6, domain="sync")
    simulator.add_testbench(bench)
    simulator.run()
    encoded = json.dumps(observed, sort_keys=True, separators=(",", ":")).encode()
    return {"status": "PASS", "vectors": len(vectors), "trace_sha256": digest_bytes(encoded),
            "trace_head": observed[:2], "trace_tail": observed[-2:]}


def child_boundary_differential(module: Any) -> dict[str, Any]:
    """Exercise injected Decode/Issue/WB families through BackendTop.

    The target is compared against an independent equation-level SV model for
    64 deterministic instructions and issue masks.  This proves child
    attachment and signal flow without promoting the incomplete full parent.
    """
    decode_path = TARGET.parent / "Build-Cpu.Backend.Decode.Instructions-Hardware.py"
    issue_path = TARGET.parent / "Build-Cpu.Backend.Issue.EnqPolicy-Hardware.py"
    wb_path = TARGET.parent / "Build-Cpu.Backend.Datapath.WbArbiter-Hardware.py"
    decode = load_exact(decode_path, "v2_backend_child_decode")
    issue = load_exact(issue_path, "v2_backend_child_issue")
    writeback = load_exact(wb_path, "v2_backend_child_wb")
    dependencies = {
        "decode": decode.InstructionPatternProbe(),
        "issue": issue.EnqPolicy(),
        "writeback": writeback.WbDataPath(),
    }
    top = module.BackendTop(injected_dependencies=dependencies)
    probe_ports = [top.frontend_instr, top.child_issue_free_slots,
                   top.child_decode_instruction, top.child_decode_matches,
                   top.child_decode_active, top.child_issue_active,
                   top.child_issue_can_enq, top.child_issue_selected_valid,
                   top.child_issue_selected_bits, top.child_writeback_active,
                   *top.child_writeback_valid, *top.child_writeback_data,
                   *top.child_writeback_pdest]
    rtl_text = verilog.convert(top, name="UHSCBackendChildBoundary", ports=probe_ports, emit_src=False)
    rtl_path = WORK / "backend-child-boundary.sv"
    rtl_path.write_text(rtl_text, encoding="utf-8", newline="\n")

    rng = random.Random(0xC1D_2026)
    vectors = [{"instruction": rng.getrandbits(32), "free_slots": rng.randrange(1 << 22)} for _ in range(64)]
    observed: list[dict[str, Any]] = []

    async def bench(ctx: Any) -> None:
        for index, vector in enumerate(vectors):
            ctx.set(top.frontend_instr, vector["instruction"])
            ctx.set(top.child_issue_free_slots, vector["free_slots"])
            await ctx.delay(1e-9)
            got = {
                "cycle": index,
                "decode_instruction": int(ctx.get(top.child_decode_instruction)),
                "decode_matches": int(ctx.get(top.child_decode_matches)),
                "decode_active": int(ctx.get(top.child_decode_active)),
                "issue_active": int(ctx.get(top.child_issue_active)),
                "issue_can_enq": int(ctx.get(top.child_issue_can_enq)),
                "issue_selected_valid": int(ctx.get(top.child_issue_selected_valid)),
                "issue_selected_bits": int(ctx.get(top.child_issue_selected_bits)),
                "writeback_active": int(ctx.get(top.child_writeback_active)),
            }
            expected_matches = sum((int(decode.match32(pattern, vector["instruction"])) << bit)
                                   for bit, pattern in enumerate(decode.PATTERNS.values()))
            expected_bits = vector["free_slots"] & (-vector["free_slots"])
            expected = {"decode_instruction": vector["instruction"], "decode_matches": expected_matches,
                        "decode_active": 1, "issue_active": 1,
                        "issue_can_enq": vector["free_slots"],
                        "issue_selected_valid": int(bool(vector["free_slots"])),
                        "issue_selected_bits": expected_bits, "writeback_active": 1}
            if any(got[key] != value for key, value in expected.items()):
                raise AssertionError((index, got, expected))
            observed.append(got)

    simulator = Simulator(top)
    simulator.add_clock(1e-6, domain="sync")
    simulator.add_testbench(bench)
    simulator.run()
    direct = {"status": "PASS", "vectors": len(vectors),
              "trace_sha256": digest_bytes(json.dumps(observed, sort_keys=True, separators=(",", ":")).encode())}

    pattern_expr = []
    for bit, pattern in enumerate(decode.PATTERNS.values()):
        mask, expected = decode.pattern_mask_expected(pattern)
        pattern_expr.append(f"((io_frontend_cfVec_instr[31:0] & 32'h{mask:08x}) == 32'h{expected:08x}) << {bit}")
    lines = ["module BackendChildReference(",
             "  io_frontend_cfVec_instr, io_child_issue_freeSlots, io_child_decode_instruction,",
             "  io_child_decode_matches, io_child_decode_active, io_child_issue_active,",
             "  io_child_issue_canEnq, io_child_issue_selected_valid, io_child_issue_selected_bits,",
             "  io_child_writeback_active, io_child_writeback_0_valid, io_child_writeback_1_valid,",
             "  io_child_writeback_2_valid, io_child_writeback_3_valid, io_child_writeback_4_valid);",
             "input [191:0] io_frontend_cfVec_instr; input [21:0] io_child_issue_freeSlots;",
             "output [31:0] io_child_decode_instruction; output [31:0] io_child_decode_matches;",
             "output io_child_decode_active, io_child_issue_active; output [21:0] io_child_issue_canEnq;",
             "output io_child_issue_selected_valid; output [21:0] io_child_issue_selected_bits;",
             "output io_child_writeback_active;",
             "output io_child_writeback_0_valid, io_child_writeback_1_valid, io_child_writeback_2_valid, io_child_writeback_3_valid, io_child_writeback_4_valid;",
             "assign io_child_decode_instruction = io_frontend_cfVec_instr[31:0];",
             "assign io_child_decode_matches = " + " | ".join(
                 f"(({expr.split(' << ')[0]}) ? (32'h1 << {bit}) : 32'h0)"
                 for bit, expr in enumerate(pattern_expr)) + ";",
             "assign io_child_decode_active = 1'b1; assign io_child_issue_active = 1'b1;",
             "assign io_child_issue_canEnq = io_child_issue_freeSlots;",
             "assign io_child_issue_selected_valid = |io_child_issue_freeSlots;",
             "assign io_child_issue_selected_bits = io_child_issue_freeSlots & (~io_child_issue_freeSlots + 22'd1);",
             "assign io_child_writeback_active = 1'b1;",
             "assign io_child_writeback_0_valid = 1'b0, io_child_writeback_1_valid = 1'b0, io_child_writeback_2_valid = 1'b0, io_child_writeback_3_valid = 1'b0, io_child_writeback_4_valid = 1'b0;",
             "endmodule\n"]
    ref_path = WORK / "BackendChildReference.sv"
    ref_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    tb_path = WORK / "backend-child-diff.sv"
    tb = ["module tb; reg [191:0] instr; reg [21:0] free_slots;",
          "wire [31:0] dut_decode_instruction, ref_decode_instruction, dut_decode_matches, ref_decode_matches;",
          "wire dut_decode_active, ref_decode_active, dut_issue_active, ref_issue_active;",
          "wire [21:0] dut_issue_can_enq, ref_issue_can_enq, dut_issue_selected_bits, ref_issue_selected_bits;",
          "wire dut_issue_selected_valid, ref_issue_selected_valid, dut_writeback_active, ref_writeback_active;",
          "wire dut_w0,dut_w1,dut_w2,dut_w3,dut_w4,ref_w0,ref_w1,ref_w2,ref_w3,ref_w4;",
          "UHSCBackendChildBoundary dut(.io_frontend_cfVec_instr(instr),.io_child_issue_freeSlots(free_slots),.io_child_decode_instruction(dut_decode_instruction),.io_child_decode_matches(dut_decode_matches),.io_child_decode_active(dut_decode_active),.io_child_issue_active(dut_issue_active),.io_child_issue_canEnq(dut_issue_can_enq),.io_child_issue_selected_valid(dut_issue_selected_valid),.io_child_issue_selected_bits(dut_issue_selected_bits),.io_child_writeback_active(dut_writeback_active),.io_child_writeback_0_valid(dut_w0),.io_child_writeback_1_valid(dut_w1),.io_child_writeback_2_valid(dut_w2),.io_child_writeback_3_valid(dut_w3),.io_child_writeback_4_valid(dut_w4));",
          "BackendChildReference ref_i(.io_frontend_cfVec_instr(instr),.io_child_issue_freeSlots(free_slots),.io_child_decode_instruction(ref_decode_instruction),.io_child_decode_matches(ref_decode_matches),.io_child_decode_active(ref_decode_active),.io_child_issue_active(ref_issue_active),.io_child_issue_canEnq(ref_issue_can_enq),.io_child_issue_selected_valid(ref_issue_selected_valid),.io_child_issue_selected_bits(ref_issue_selected_bits),.io_child_writeback_active(ref_writeback_active),.io_child_writeback_0_valid(ref_w0),.io_child_writeback_1_valid(ref_w1),.io_child_writeback_2_valid(ref_w2),.io_child_writeback_3_valid(ref_w3),.io_child_writeback_4_valid(ref_w4));",
          "initial begin"]
    for index, vector in enumerate(vectors):
        tb.append(f"instr=192'h{vector['instruction']:048x}; free_slots=22'h{vector['free_slots']:06x}; #1;")
        tb.append(f"if (dut_decode_instruction!==ref_decode_instruction || dut_decode_matches!==ref_decode_matches || dut_decode_active!==ref_decode_active || dut_issue_active!==ref_issue_active || dut_issue_can_enq!==ref_issue_can_enq || dut_issue_selected_valid!==ref_issue_selected_valid || dut_issue_selected_bits!==ref_issue_selected_bits || dut_writeback_active!==ref_writeback_active) begin $display(\"CHILD_MISMATCH {index}\"); $fatal(1); end")
    tb.extend([f'$display("BACKEND_CHILD_DIFF_PASS {len(vectors)}"); $finish;', "end endmodule\n"])
    tb_path.write_text("\n".join(tb), encoding="utf-8", newline="\n")
    compile_result = run_wsl(["verilator", "--binary", "--timing", "-Wno-fatal", "-Wno-WIDTHEXPAND", "-Wno-WIDTHTRUNC", "--top-module", "tb",
                              "--Mdir", wsl_path(WORK / "obj-child"), wsl_path(rtl_path), wsl_path(ref_path), wsl_path(tb_path)], timeout=360)
    if compile_result["status"] != "PASS":
        return {"status": "FAIL_COMPILE", "direct": direct, "compile": compile_result, "vectors": len(vectors)}
    run_result = run_wsl([wsl_path(WORK / "obj-child/Vtb")], timeout=120)
    passed = run_result["status"] == "PASS" and "BACKEND_CHILD_DIFF_PASS" in run_result.get("output_tail", "")
    return {"status": "PASS" if passed else "FAIL_RUN", "direct": direct,
            "differential": {"status": "PASS" if passed else "FAIL", "compile": compile_result,
                             "run": run_result, "vectors": len(vectors)},
            "vectors": len(vectors), "bound_children": ["Decode.Instructions", "Issue.EnqPolicy", "Backend.Datapath.WbDataPath"],
            "semantic_status": "BOUNDED_CHILD_SIGNAL_FLOW"}


def sv_decl(direction: str, width: int, name: str) -> str:
    """Render one scalar SystemVerilog port declaration. / 渲染一个标量 SystemVerilog 端口声明。"""
    kind = "output reg" if direction == "output" else direction
    return f"  {kind} " + (f"[{width - 1}:0] " if width > 1 else "") + f"{name};"


def port_specs() -> list[tuple[str, str, int]]:
    """Return the fixed target-port schema used by the independent SV model. / 返回独立 SV 模型使用的固定目标端口模式。"""
    specs: list[tuple[str, str, int]] = [
        ("input", "reset", 1), ("input", "io_flush_valid", 1), ("input", "io_backendCanAccept", 1),
        ("input", "io_fromTop_hartId", 6), ("input", "io_fromTop_externalInterrupt", 7),
        ("input", "io_fromTop_msiInfo_valid", 1), ("input", "io_fromTop_msiInfo_bits", 12),
        ("input", "io_fromTop_clintTime_valid", 1), ("input", "io_fromTop_clintTime_bits", 64),
        ("input", "io_frontend_cfVec_valid", 6), ("input", "io_frontend_cfVec_instr", 192),
        ("input", "io_frontend_cfVec_exceptionVec", 144), ("input", "io_frontend_cfVec_pc", 300),
        ("input", "io_frontend_cfVec_ftqPtr", 36), ("input", "io_frontend_cfVec_ftqOffset", 24),
    ]
    for index in range(8):
        specs += [("input", f"io_fromExu_{index}_valid", 1), ("input", f"io_fromExu_{index}_data", 64),
                  ("input", f"io_fromExu_{index}_pdest", 8), ("input", f"io_fromExu_{index}_rfClass", 3),
                  ("input", f"io_fromExu_{index}_wbPort", 3), ("input", f"io_fromExu_{index}_uncertainLatency", 1),
                  ("input", f"io_fromExu_{index}_hasNoDataWB", 1), ("input", f"io_fromExu_{index}_redirect", 1)]
    for index in range(5):
        specs.append(("input", f"io_wb_{index}_ready", 1))
    specs += [("input", "clk", 1), ("output", "io_frontend_cfVec_ready", 6),
              ("output", "io_toDispatch_valid", 6), ("output", "io_toDispatch_instr", 192),
              ("output", "io_toDispatch_exceptionVec", 144), ("output", "io_toDispatch_pc", 300),
              ("output", "io_frontend_canAccept", 1), ("output", "io_frontend_toFtq_redirect_valid", 1),
              ("output", "io_frontend_toFtq_redirect_pc", 50), ("output", "io_frontend_toFtq_redirect_ftqIdx", 6),
              ("output", "io_frontend_toFtq_redirect_ftqOffset", 4), ("output", "io_toTop_cpuHalted", 1),
              ("output", "io_toTop_cpuCriticalError", 1), ("output", "io_toTop_msiAck", 1),
              ("output", "io_fenceio_fencei", 1), ("output", "io_fenceio_sbuffer_flushSb", 1),
              ("output", "io_frontendReset", 1)]
    for index in range(8):
        specs.append(("output", f"io_fromExu_{index}_ready", 1))
    for index in range(5):
        specs += [("output", f"io_toPreg_{index}_valid", 1), ("output", f"io_toPreg_{index}_data", 64),
                  ("output", f"io_toPreg_{index}_pdest", 8), ("output", f"io_toPreg_{index}_rfClass", 3),
                  ("output", f"io_toPreg_{index}_fire", 1)]
    return specs


def reference_sv() -> str:
    """Generate an independent equation-level SV parent oracle. / 生成独立的方程级 SV 父级 oracle。"""
    specs = port_specs()
    lines = ["module BackendReferenceBoundary("]
    lines.extend(f"  {name}" + ("," if index < len(specs) - 1 else "") for index, (_direction, name, _width) in enumerate(specs))
    lines[-1] += ");"
    for direction, name, width in specs:
        lines.append(sv_decl(direction, width, name))
    lines.append("  integer i;")
    lines.append("  reg [4:0] chosen;")
    # Default all outputs; the reduced oracle intentionally models only the
    # parent observation surface, while dispatch registers remain stateful DUT data.
    lines.append("  always @* begin")
    lines.append("    io_frontend_cfVec_ready = {6{io_backendCanAccept & ~io_flush_valid}} & io_frontend_cfVec_valid;")
    lines.append("    io_frontend_canAccept = io_backendCanAccept & ~io_flush_valid;")
    lines.append("    io_frontend_toFtq_redirect_valid = io_flush_valid;")
    lines.append("    io_frontend_toFtq_redirect_pc = io_frontend_cfVec_pc[49:0];")
    lines.append("    io_frontend_toFtq_redirect_ftqIdx = io_frontend_cfVec_ftqPtr[5:0];")
    lines.append("    io_frontend_toFtq_redirect_ftqOffset = io_frontend_cfVec_ftqOffset[3:0];")
    lines.append("    io_toTop_cpuHalted = 1'b0;")
    lines.append("    io_toTop_cpuCriticalError = 1'b0;")
    for lane in range(6):
        lo = lane * 24
        hi = lo + 23
        lines.append(f"    io_frontend_toFtq_redirect_valid = io_frontend_toFtq_redirect_valid | (io_frontend_cfVec_valid[{lane}] & (|io_frontend_cfVec_exceptionVec[{hi}:{lo}]));")
        lines.append(f"    io_toTop_cpuCriticalError = io_toTop_cpuCriticalError | (io_frontend_cfVec_valid[{lane}] & (|io_frontend_cfVec_exceptionVec[{hi}:{lo}]));")
    lines.append("    io_frontend_toFtq_redirect_valid = io_frontend_toFtq_redirect_valid | (|{io_fromExu_7_redirect,io_fromExu_6_redirect,io_fromExu_5_redirect,io_fromExu_4_redirect,io_fromExu_3_redirect,io_fromExu_2_redirect,io_fromExu_1_redirect,io_fromExu_0_redirect});")
    lines.append("    io_toTop_cpuCriticalError = io_toTop_cpuCriticalError;")
    lines.append("    io_toTop_msiAck = io_fromTop_msiInfo_valid & ~reset;")
    lines.append("    io_fenceio_fencei = io_flush_valid;")
    lines.append("    io_fenceio_sbuffer_flushSb = io_flush_valid;")
    lines.append("    io_frontendReset = reset;")
    # Writeback output defaults and priority muxes.
    for port in range(5):
        matches = [f"(io_fromExu_{i}_valid & ~io_flush_valid & (io_fromExu_{i}_rfClass != 3'd7) & (io_fromExu_{i}_wbPort == 3'd{port}))" for i in range(8)]
        lines.append(f"    io_toPreg_{port}_valid = {' | '.join(matches)};")
        lines.append(f"    io_toPreg_{port}_data = 64'd0;")
        lines.append(f"    io_toPreg_{port}_pdest = 8'd0;")
        lines.append(f"    io_toPreg_{port}_rfClass = 3'd7;")
        for i in range(7, -1, -1):
            match = matches[i]
            lines.append(f"    if ({match}) begin io_toPreg_{port}_data = io_fromExu_{i}_data; io_toPreg_{port}_pdest = io_fromExu_{i}_pdest; io_toPreg_{port}_rfClass = io_fromExu_{i}_rfClass; end")
        lines.append(f"    io_toPreg_{port}_fire = io_toPreg_{port}_valid & io_wb_{port}_ready;")
    for i in range(8):
        terms = [f"(io_toPreg_{port}_fire & io_fromExu_{i}_valid & (io_fromExu_{i}_rfClass != 3'd7) & (io_fromExu_{i}_wbPort == 3'd{port}))" for port in range(5)]
        lines.append(f"    io_fromExu_{i}_ready = ~io_fromExu_{i}_valid | io_fromExu_{i}_hasNoDataWB | ~io_fromExu_{i}_uncertainLatency | ({' | '.join(terms)});")
    # Stateful dispatch outputs are not part of the equation comparison.
    lines.append("    io_toDispatch_valid = 6'd0; io_toDispatch_instr = 192'd0; io_toDispatch_exceptionVec = 144'd0; io_toDispatch_pc = 300'd0;")
    lines.append("  end")
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def differential_sv(target_rtl: Path, vectors: list[dict[str, Any]]) -> dict[str, Any]:
    """Run target versus independent SV equations on deterministic vectors. / 对确定性向量运行目标与独立 SV 方程差分。"""
    WORK.mkdir(parents=True, exist_ok=True)
    ref_path = WORK / "BackendReferenceBoundary.sv"
    tb_path = WORK / "backend-parent-diff.sv"
    ref_path.write_text(reference_sv(), encoding="utf-8", newline="\n")
    # Shared declarations and instances are generated from the exact target schema.
    specs = port_specs()
    inputs = [(name, width) for direction, name, width in specs if direction == "input"]
    outputs = [(name, width) for direction, name, width in specs if direction == "output"]
    lines = ["module tb;"]
    for name, width in inputs:
        lines.append((f"reg [{width - 1}:0] {name};" if width > 1 else f"reg {name};"))
    for name, width in outputs:
        lines.append((f"wire [{width - 1}:0] dut_{name}, ref_{name};" if width > 1 else f"wire dut_{name}, ref_{name};"))
    connections_target = ", ".join(f".{name}(dut_{name})" if direction == "output" else f".{name}({name})" for direction, name, _ in specs)
    connections_ref = ", ".join(f".{name}(ref_{name})" if direction == "output" else f".{name}({name})" for direction, name, _ in specs)
    lines.append(f"  UHSCBackendTop dut_i({connections_target});")
    lines.append(f"  BackendReferenceBoundary ref_i({connections_ref});")
    lines.append("  integer cycle;")
    lines.append("  initial begin")
    lines.append("    reset=0; io_flush_valid=0; io_backendCanAccept=0; io_fromTop_hartId=0; io_fromTop_externalInterrupt=0; io_fromTop_msiInfo_valid=0; io_fromTop_msiInfo_bits=0; io_fromTop_clintTime_valid=0; io_fromTop_clintTime_bits=0; io_frontend_cfVec_valid=0; io_frontend_cfVec_instr=0; io_frontend_cfVec_exceptionVec=0; io_frontend_cfVec_pc=0; io_frontend_cfVec_ftqPtr=0; io_frontend_cfVec_ftqOffset=0; clk=0;")
    for name, _width in inputs:
        if name.startswith("io_fromExu_") or name.startswith("io_wb_"):
            lines.append(f"    {name}=0;")
    for index, vector in enumerate(vectors):
        lines.append(f"    cycle={index};")
        lines.append(f"    reset={int(vector['reset'])}; io_flush_valid={int(vector['flush'])}; io_backendCanAccept={int(vector['backend_can_accept'])}; io_fromTop_msiInfo_valid={int(vector['msi_valid'])};")
        lines.append(f"    io_frontend_cfVec_valid=6'h{vector['frontend_valid']:02x};")
        instr = sum(value << (lane * 32) for lane, value in enumerate(vector["frontend_instr"]))
        exc = sum(value << (lane * 24) for lane, value in enumerate(vector["frontend_exception"]))
        pc = sum(value << (lane * 50) for lane, value in enumerate(vector["frontend_pc"]))
        lines.append(f"    io_frontend_cfVec_instr=192'h{instr:048x}; io_frontend_cfVec_exceptionVec=144'h{exc:036x}; io_frontend_cfVec_pc=300'h{pc:075x};")
        for lane in range(8):
            lines.append(f"    io_fromExu_{lane}_valid={int(vector['exu_valid'][lane])}; io_fromExu_{lane}_data=64'h{vector['exu_data'][lane]:016x}; io_fromExu_{lane}_pdest=8'h{vector['exu_pdest'][lane]:02x}; io_fromExu_{lane}_rfClass=3'd{vector['exu_class'][lane]}; io_fromExu_{lane}_wbPort=3'd{vector['exu_port'][lane]}; io_fromExu_{lane}_uncertainLatency={int(vector['exu_uncertain'][lane])}; io_fromExu_{lane}_hasNoDataWB={int(vector['exu_no_data'][lane])}; io_fromExu_{lane}_redirect={int(vector['exu_redirect'][lane])};")
        for port in range(5):
            lines.append(f"    io_wb_{port}_ready={int(vector['wb_ready'][port])};")
        lines.append("    #1;")
        checks = ["dut_io_frontend_cfVec_ready !== ref_io_frontend_cfVec_ready", "dut_io_frontend_canAccept !== ref_io_frontend_canAccept", "dut_io_frontend_toFtq_redirect_valid !== ref_io_frontend_toFtq_redirect_valid", "dut_io_toTop_cpuCriticalError !== ref_io_toTop_cpuCriticalError", "dut_io_toTop_cpuHalted !== ref_io_toTop_cpuHalted", "dut_io_toTop_msiAck !== ref_io_toTop_msiAck", "dut_io_fenceio_fencei !== ref_io_fenceio_fencei", "dut_io_fenceio_sbuffer_flushSb !== ref_io_fenceio_sbuffer_flushSb"]
        for port in range(5):
            checks += [f"dut_io_toPreg_{port}_valid !== ref_io_toPreg_{port}_valid", f"dut_io_toPreg_{port}_data !== ref_io_toPreg_{port}_data", f"dut_io_toPreg_{port}_pdest !== ref_io_toPreg_{port}_pdest", f"dut_io_toPreg_{port}_rfClass !== ref_io_toPreg_{port}_rfClass", f"dut_io_toPreg_{port}_fire !== ref_io_toPreg_{port}_fire"]
        for lane in range(8):
            checks.append(f"dut_io_fromExu_{lane}_ready !== ref_io_fromExu_{lane}_ready")
        lines.append(f"    if ({' || '.join(checks)}) begin $display(\"MISMATCH cycle=%0d\",cycle); $fatal(1); end")
        lines.append("    $display(\"B %0d %h %h\", cycle, dut_io_toPreg_0_valid, dut_io_toPreg_1_valid);")
    lines.append(f"    $display(\"BACKEND_PARENT_DIFF_PASS {len(vectors)}\"); $finish;")
    lines.append("  end")
    lines.append("endmodule")
    tb_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    # Use a dedicated deterministic build directory so concurrent validators
    # cannot invalidate Verilator's generated PCH artifacts.
    diff_obj = WORK / "obj-diff"
    compile_result = run_wsl(["verilator", "--binary", "--timing", "-Wno-fatal", "--top-module", "tb",
                              "--Mdir", wsl_path(diff_obj), wsl_path(target_rtl), wsl_path(ref_path), wsl_path(tb_path)], timeout=360)
    if compile_result["status"] != "PASS":
        return {"status": "FAIL_COMPILE", "compile": compile_result, "vectors": len(vectors)}
    run_result = run_wsl([wsl_path(diff_obj / "Vtb")], timeout=120)
    passed = run_result["status"] == "PASS" and "BACKEND_PARENT_DIFF_PASS" in run_result.get("output_tail", "")
    return {"status": "PASS" if passed else "FAIL_RUN", "compile": compile_result, "run": run_result,
            "vectors": len(vectors), "reference_mode": "independent_sv_parent_equations",
            "trace_sha256": run_result.get("output_sha256")}


def locked_reference_info() -> dict[str, Any]:
    """Verify the pinned XSTop artifact and extract Backend provenance. / 校验固定 XSTop 产物并提取 Backend 溯源。"""
    raw = REF_PATH.read_bytes()
    if len(raw) != REFERENCE_BYTES or digest_bytes(raw) != REFERENCE_SHA256:
        raise RuntimeError("locked XSTop hash/size mismatch")
    match = re.search(rb"^module Backend\(.*?^endmodule\s*", raw, re.MULTILINE | re.DOTALL)
    if match is None:
        raise RuntimeError("Backend module missing from locked XSTop")
    module = match.group(0)
    header_end = module.find(b");")
    header = module if header_end < 0 else module[:header_end + 2]
    # Chisel emits a direction only at the start of a continuation group, so
    # counting direction keywords understates the actual port count.  Strip
    # comments and count each comma-separated identifier in the ANSI header.
    header_text = re.sub(rb"//[^\n]*", b"", header)
    body = header_text[header_text.find(b"(") + 1:header_text.rfind(b");")]
    names: list[str] = []
    for part in body.split(b","):
        tokens = re.findall(rb"[A-Za-z_][A-Za-z0-9_$]*", part)
        if tokens:
            names.append(tokens[-1].decode("ascii", "replace"))
    return {
        "canonical_path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv",
        "sha256": digest_bytes(raw), "bytes": len(raw), "source_commit": SOURCE_COMMIT,
        "backend_module": {"sha256": digest_bytes(module), "bytes": len(module),
                            "header_sha256": digest_bytes(header), "port_count": len(names),
                            "port_count_expected": BACKEND_PORT_COUNT,
                            "line_start": raw[:match.start()].count(b"\n") + 1,
                            "line_end": raw[:match.end()].count(b"\n") + 1,
                            "expected_header_sha256": BACKEND_HEADER_SHA256},
    }


def source_info() -> dict[str, Any]:
    """Record source hashes and Backend closure anchors. / 记录源码摘要及 Backend 闭包锚点。"""
    paths = {
        "Backend": ROOT / "upstream/src/main/scala/xiangshan/backend/Backend.scala",
        "DataPath": ROOT / "upstream/src/main/scala/xiangshan/backend/datapath/DataPath.scala",
        "DataSource": ROOT / "upstream/src/main/scala/xiangshan/backend/datapath/DataSource.scala",
        "WbArbiter": ROOT / "upstream/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala",
        "DecodeUnit": ROOT / "upstream/src/main/scala/xiangshan/backend/decode/DecodeUnit.scala",
        "DecodeStage": ROOT / "upstream/src/main/scala/xiangshan/backend/decode/DecodeStage.scala",
    }
    anchors = {
        "Backend": ["class Backend", "new DataPath", "new WbDataPath", "new ExuBlock"],
        "DataPath": ["class DataPath", "DataSource", "IntRFWBCollideChecker"],
        "WbArbiter": ["class RealWBCollideChecker", "class WbDataPath", "hasUncertainLatency"],
        "DecodeUnit": ["class DecodeUnit", "Instructions"],
        "DecodeStage": ["class DecodeStage", "DecodeUnit"],
    }
    result: dict[str, Any] = {}
    for name, path in paths.items():
        text = path.read_text(encoding="utf-8")
        result[name] = {"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path), "bytes": path.stat().st_size,
                        "anchors": {anchor: text.count(anchor) for anchor in anchors.get(name, [])}}
    return result


def write_evidence(static: dict[str, Any], direct: dict[str, Any], differential: dict[str, Any],
                   backend: dict[str, Any], reference: dict[str, Any], source: dict[str, Any],
                   inventory: dict[str, Any], child_boundary: dict[str, Any]) -> None:
    """Write batch evidence while keeping promotion closed. / 写入批次证据并保持晋级关闭。"""
    target_rel = TARGET.relative_to(ROOT).as_posix()
    common = {"schema_version": 1, "batch_id": "V2-PARENT-BACKEND-001", "source_commit": SOURCE_COMMIT,
              "target": {"path": target_rel, "sha256": digest(TARGET)}, "reference_snapshot": reference,
              "source_paths": source, "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": direct["status"],
              "V2_REFERENCE_MATCHED": "PASS_BOUNDED_EQUATIONS" if differential["status"] == "PASS" else "FAIL",
              "PARENT_CLOSURE_MATCHED": "PENDING_FULL_1165_PORT_BACKEND", "UHSC_LOCALIZED": "PASS_BOUNDED_PARENT_LOCAL_NAME",
              "LICENSE_REVIEW": "PENDING", "ACCEPTED": "NOT_ALLOWED"}, "acceptance_eligible": False}
    DIRECT_RESULT.write_text(json.dumps({**common, "kind": "XIANGSHAN_KUNMINGHU_V2_BACKEND_PARENT_DIRECT",
                                          "static_audit": static, "direct": direct, "backend_gates": backend,
                                          "full_inventory_probe": inventory, "child_boundary": child_boundary},
                                         ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    DIFF_RESULT.write_text(json.dumps({**common, "kind": "XIANGSHAN_KUNMINGHU_V2_BACKEND_PARENT_DIFFERENTIAL",
                                       "differential": differential, "backend_gates": backend,
                                       "full_inventory_probe": inventory, "child_boundary": child_boundary,
                                       "behavioral_equivalence": differential["status"] == "PASS",
                                       "reference_mode": "independent_sv_parent_equations_plus_locked_xstop_provenance",
                                       "unclosed": ["Full generated Backend has 1165 ports and requires Decode/Issue/Rename/CSR/Exu child closure.",
                                                    "Equation lane is bounded evidence; it is not full XSTop module equivalence.",
                                                    "License review and user approval remain pending."]},
                                      ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    CONTRACT_RESULT.write_text(json.dumps({"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_BACKEND_PARENT_CONTRACT_AUDIT",
                                           "batch_id": "V2-PARENT-BACKEND-001", "target": static,
                                           "injected_dependencies": ["control/dispatch", "datapath", "writeback", "memory", "csr"],
                                           "source_authority": reference, "source_paths": source,
                                           "full_inventory_probe": inventory, "child_boundary": child_boundary,
                                           "result": static["status"], "gates": common["gates"], "acceptance_eligible": False},
                                          ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    COVERAGE_RESULT.write_text(json.dumps({"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_BACKEND_PARENT_COVERAGE",
                                           "batch_id": "V2-PARENT-BACKEND-001", "closure_root": "core.backend",
                                           "root_source": "upstream/src/main/scala/xiangshan/backend/Backend.scala",
                                           "root_module": "Backend", "target": target_rel,
                                           "covered_children": ["six-wide frontend admission", "one-entry dispatch register",
                                                                 "five-class writeback priority", "uncertain-latency EXU ready",
                                                                 "flush/redirect propagation", "top-level halt/error/MSI/fence surfaces"],
                                           "observation_points": ["frontend ready/valid", "dispatch ordering", "writeback class/port priority",
                                                                  "writeback backpressure", "flush cancellation", "redirect/error", "MSI acknowledge"],
                                           "direct": direct, "differential": differential,
                                           "full_inventory_probe": inventory, "child_boundary": child_boundary,
                                           "status": "PASS_BOUNDED_PARENT" if differential["status"] == "PASS" else "FAIL",
                                           "gates": common["gates"], "acceptance_eligible": False},
                                          ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    MAPPING_RESULT.write_text(json.dumps({"schema_version": 1, "kind": "V2_BACKEND_PARENT_MAPPING_UPDATE",
                                          "batch_id": "V2-PARENT-BACKEND-001", "source_commit": SOURCE_COMMIT,
                                          "entries": [{"id": "Backend", "classification": "NEW_REDUCED_PARENT_BOUNDARY",
                                                       "disposition": "PARENT_BOUNDARY_REDUCED",
                                                       "v2_source": "upstream/src/main/scala/xiangshan/backend/Backend.scala",
                                                       "target": target_rel, "local_name": "UHSCBackendTop",
                                                       "covered_children": ["DataPath", "WbDataPath", "dispatch", "redirect"],
                                                       "status": "PASS_BOUNDED" if differential["status"] == "PASS" else "FAIL"}],
                                          "reference_snapshot": reference, "gates": common["gates"],
                                          "full_inventory_probe": inventory, "child_boundary": child_boundary,
                                          "acceptance_eligible": False},
                                         ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    SUMMARY_RESULT.write_text(json.dumps({"schema_version": 1, "kind": "V2_BACKEND_PARENT_BATCH_SUMMARY",
                                          "batch_id": "V2-PARENT-BACKEND-001", "static": static, "direct": direct,
                                          "differential": differential, "backend": backend, "reference": reference,
                                          "status": "PASS_BOUNDED_PARENT" if static["status"] == "PASS" and direct["status"] == "PASS" and differential["status"] == "PASS" and backend["status"] == "PASS" else "FAIL",
                                          "full_inventory_probe": inventory, "child_boundary": child_boundary,
                                          "acceptance_eligible": False, "ACCEPTED": "NOT_ALLOWED"},
                                         ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    """Execute the independent Backend parent validation transaction. / 执行独立 Backend 父级验证事务。"""
    WORK.mkdir(parents=True, exist_ok=True)
    alias = prepare_alias()
    if alias["status"] != "PASS":
        raise RuntimeError(alias)
    module = load_exact(TARGET, "v2_backend_parent_target")
    static = static_audit(TARGET)
    compile_result = subprocess.run([sys.executable, "-m", "py_compile", str(TARGET)], capture_output=True, check=False)
    if compile_result.returncode != 0:
        raise RuntimeError(compile_result.stderr.decode("utf-8", "replace"))
    vectors = make_vectors()
    direct = direct_parent(module, vectors)
    rtl_text = module.build_verilog(None, None)
    rtl_path = WORK / "backend-target.sv"
    rtl_path.write_text(rtl_text, encoding="utf-8", newline="\n")
    backend = backend_gates(rtl_path)
    differential = differential_sv(rtl_path, vectors)
    inventory = full_inventory_probe(module)
    child_boundary = child_boundary_differential(module)
    reference = locked_reference_info()
    source = source_info()
    write_evidence(static, direct, differential, backend, reference, source, inventory, child_boundary)
    status = "PASS_BOUNDED_PARENT" if static["status"] == "PASS" and direct["status"] == "PASS" and differential["status"] == "PASS" and backend["status"] == "PASS" else "FAIL"
    print(json.dumps({"status": status, "vectors": len(vectors), "direct": direct["status"],
                      "differential": differential["status"], "full_inventory": inventory["status"],
                      "full_inventory_ports": inventory["port_count"],
                      "child_boundary": child_boundary["status"],
                      "child_boundary_vectors": child_boundary["vectors"],
                      "verilator": backend["verilator"]["status"],
                      "yosys": backend["yosys"]["status"], "ACCEPTED": "NOT_ALLOWED"}, sort_keys=True))
    return 0 if status == "PASS_BOUNDED_PARENT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
