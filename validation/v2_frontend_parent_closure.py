"""Validate the bounded Kunminghu V2 Frontend parent closure.
验证昆明湖 V2 前端父级精简闭包。

The validator treats ``Frontend.scala`` and the pinned V2 ``XSTop.sv`` as
immutable authorities.  It exercises the maintained Build-Cpu target directly,
projects the exact parent equations into a small locked-source reference shell,
and compares both through Verilator.  The shell intentionally observes only
the reduced parent surface; this keeps the 371-port Frontend dependency graph
bounded while making every omitted child boundary explicit in the evidence.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from amaranth.sim import Simulator


# =============================================================================
# Module Contract
# =============================================================================
# The closure root is ``upstream/src/main/scala/xiangshan/frontend/Frontend.scala``.
# Observed equations are RegNext/DelayN control pipelines, ICache and
# InstrUncache request safety, WFI joining, error delay, PTW readiness, and the
# backend-visible CF/performance surfaces.  No source or locked SV is changed.
# 闭包根为 Frontend.scala；观测方程包括 RegNext/DelayN 控制流水、ICache 与
# InstrUncache 请求安全、WFI 合并、错误延迟、PTW 就绪以及后端 CF/性能表面。
__all__ = [
    "main",
    "load_target",
    "static_audit",
    "direct_check",
    "reference_projection",
    "differential_check",
]


# =============================================================================
# Configuration
# =============================================================================
ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python" / "Program-System" / "System-Build" / "Build-Cpu" / "Cpu-Core" / "Build-Cpu.Frontend.Top-Hardware.py"
REFERENCE = Path(r"\\wsl$\Debian\home\lishuo\xs-v2-local\build\rtl\XSTop.sv")
REFERENCE_CANONICAL = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
SOURCE = ROOT / "upstream" / "src" / "main" / "scala" / "xiangshan" / "frontend" / "Frontend.scala"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
REFERENCE_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
REFERENCE_BYTES = 228590583
WORK = ROOT / "validation" / ".work" / "v2-frontend-parent"
DIRECT_RESULT = ROOT / "validation" / "v2-frontend-parent-direct-results.json"
DIFF_RESULT = ROOT / "validation" / "v2-frontend-parent-differential-results.json"
CONTRACT_RESULT = ROOT / "validation" / "v2-frontend-parent-contract-audit.json"
COVERAGE_RESULT = ROOT / "validation" / "v2-frontend-parent-coverage-manifest.json"
MAPPING_RESULT = ROOT / "validation" / "v2-frontend-parent-mapping-update.json"


# =============================================================================
# Implementation
# =============================================================================
def digest_bytes(value: bytes) -> str:
    """Return a SHA-256 digest for exact bytes. / 返回原始字节的 SHA-256 摘要。"""
    return hashlib.sha256(value).hexdigest()


def digest(path: Path) -> str:
    """Hash one file without normalizing line endings. / 不规范化换行并计算文件摘要。"""
    return digest_bytes(path.read_bytes())


def load_target(path: Path, name: str) -> Any:
    """Load a target by exact path. / 按精确路径加载目标模块。"""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load target {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def static_audit(path: Path) -> dict[str, Any]:
    """Audit five zones, adapter signature, imports, and bilingual comments. / 审计五区、适配器签名、导入和双语注释。"""
    raw = path.read_bytes()
    source = raw.decode("utf-8")
    tree = ast.parse(source, filename=str(path))
    lines = source.splitlines()
    zones = ("Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry")
    positions = [source.find(zone) for zone in zones]
    comment_errors: list[str] = []
    forbidden: list[str] = []
    cross_build: list[str] = []
    dynamic: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            prior = lines[node.lineno - 2].strip() if node.lineno > 1 else ""
            if not (prior.startswith("#") and "/" in prior):
                comment_errors.append(f"{node.name}:{node.lineno}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in {"subprocess", "socket", "urllib", "importlib", "runpy"}:
                    forbidden.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.split(".")[0] in {"subprocess", "socket", "urllib", "importlib", "runpy"}:
                forbidden.append(module)
            if "Build-Cpu" in module:
                cross_build.append(f"{node.lineno}:{module}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"import_module", "run_path", "spec_from_file_location", "module_from_spec"}:
                dynamic.append(f"{node.lineno}:{node.func.attr}")
    adapter = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "build_verilog"]
    adapter_args = [arg.arg for arg in adapter[0].args.args] if len(adapter) == 1 else []
    status = (
        all(position >= 0 for position in positions) and positions == sorted(positions)
        and not comment_errors and not forbidden and not cross_build and not dynamic
        and adapter_args == ["configuration", "injected_dependencies"]
        and not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw
    )
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": digest_bytes(raw),
        "bytes": len(raw),
        "utf8": True,
        "lf_only": b"\r" not in raw,
        "bom": raw.startswith(b"\xef\xbb\xbf"),
        "ast_parse": True,
        "zones": {name: position for name, position in zip(zones, positions)},
        "adapter_args": adapter_args,
        "function_comment_errors": comment_errors,
        "forbidden_imports": forbidden,
        "cross_build_imports": cross_build,
        "dynamic_imports": dynamic,
        "status": "PASS" if status else "FAIL",
    }


def reference_snapshot() -> dict[str, Any]:
    """Verify and index the locked XSTop Frontend module. / 校验并索引锁定 XSTop 的 Frontend 模块。"""
    raw = REFERENCE.read_bytes()
    text = raw.decode("utf-8", "replace")
    match = re.search(r"^module Frontend\(.*?^endmodule\s*", text, re.MULTILINE | re.DOTALL)
    if match is None:
        raise RuntimeError("locked Frontend module is absent")
    module_text = match.group(0)
    header = module_text.split("\n);", 1)[0] + "\n);"
    # Chisel emits one direction/width followed by comma-separated continuation
    # names.  Parse those continuations instead of counting only lines that
    # repeat ``input``/``output`` (the locked Frontend has 371 ports).
    ports: list[str] = []
    current_direction = ""
    header_no_comments = " ".join(line.split("//", 1)[0] for line in header.splitlines())
    for segment in header_no_comments.split(","):
        if not segment:
            continue
        declaration = re.search(r"\b(input|output)\b\s*(?:\[[^]]+\])?\s*([A-Za-z_][A-Za-z0-9_]*)", segment)
        if declaration:
            current_direction = declaration.group(1)
            ports.append(declaration.group(2))
            continue
        if current_direction:
            continuation = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", segment)
            if continuation:
                ports.append(continuation.group(1))
    return {
        "canonical_path": REFERENCE_CANONICAL,
        "local_access_path": str(REFERENCE),
        "sha256": digest_bytes(raw),
        "bytes": len(raw),
        "locked": len(raw) == REFERENCE_BYTES and digest_bytes(raw) == REFERENCE_SHA256,
        "module": "Frontend",
        "module_line_start": text[:match.start()].count("\n") + 1,
        "module_line_end": text[:match.end()].count("\n"),
        "module_bytes": len(module_text.encode("utf-8")),
        "module_sha256": digest_bytes(module_text.encode("utf-8")),
        "port_count": len(ports),
        "port_names_sha256": digest_bytes("\n".join(ports).encode("utf-8")),
    }


def frontend_vectors(count: int = 96) -> list[dict[str, int]]:
    """Build deterministic parent transactions. / 构造确定性的父级事务序列。"""
    vectors: list[dict[str, int]] = []
    for index in range(count):
        vectors.append({
            "reset": 1 if index < 3 else 0,
            "redirect": 1 if index in {7, 23, 41, 72} else 0,
            "debug_ctrl": (index >> 1) & 1,
            "debug_memvio": (index >> 2) & 1,
            "fencei": 1 if index in {13, 54, 81} else 0,
            "wfi": 1 if index in {5, 6, 30, 31, 67} else 0,
            "sfence": 1 if index % 17 == 0 else 0,
            "pf_enable": (index >> 3) & 1,
            "fs_off": (index >> 4) & 1,
            "bp_enable": (index * 7) & 0x1F,
            "fetch_valid": 1 if index % 4 != 0 else 0,
            "uncache_valid": 1 if index % 11 == 0 else 0,
            "fetch_addr": (0x1000 + index * 0x40) & ((1 << 50) - 1),
            "uncache_addr": (0x8000 + index * 0x20) & ((1 << 50) - 1),
            "icache_safe": 0 if index in {19, 20} else 1,
            "uncache_safe": 0 if index in {20, 21} else 1,
            "error_valid": 1 if index in {18, 55, 90} else 0,
            "error_bits": (0x123456789ABC ^ (index * 0x1021)) & ((1 << 48) - 1),
            "backend_accept": 1 if index % 9 != 0 else 0,
        })
    return vectors


def expected_step(state: dict[str, int], vector: dict[str, int], cfg: Any) -> dict[str, int]:
    """Advance the reduced Frontend oracle by one edge. / 推进精简前端 oracle 一个时钟沿。"""
    old = dict(state)
    reset = bool(vector["reset"])
    # Child request readiness is evaluated from the pre-edge parent controls.
    old_icache_ready = int(not old["icache_busy"] and not old["need_flush"] and not old["fencei_reg"])
    old_uncache_ready = int(not old["uncache_busy"] and not old["need_flush"] and not old["fencei_reg"])
    if reset:
        for key in state:
            state[key] = 0
    else:
        state["need_flush"] = vector["redirect"]
        state["debug_ctrl"] = vector["debug_ctrl"]
        state["debug_memvio"] = vector["debug_memvio"]
        state["fencei_reg"] = vector["fencei"]
        state["wfi_reg"] = vector["wfi"]
        state["pf1"], state["pf2"] = vector["pf_enable"], old["pf1"]
        state["fs1"], state["fs2"] = vector["fs_off"], old["fs1"]
        state["bp1"], state["bp2"] = vector["bp_enable"], old["bp1"]
        state["sf1"], state["sf2"] = vector["sfence"], old["sf1"]
        state["errv1"], state["errv2"] = vector["error_valid"], old["errv1"]
        state["errb1"], state["errb2"] = vector["error_bits"], old["errb1"]
        state["safe1"], state["safe2"] = int(old["wfi_reg"] and vector["icache_safe"] and vector["uncache_safe"]), old["safe1"]
        state["ibuf"] = 0
        if old["need_flush"] or old["fencei_reg"]:
            state["icache_busy"], state["uncache_busy"] = 0, 0
        else:
            state["icache_busy"] = int((not old["icache_busy"] and old_icache_ready and vector["fetch_valid"]) or (old["icache_busy"] and not old["icache_busy"]))
            state["uncache_busy"] = int((not old["uncache_busy"] and old_uncache_ready and vector["uncache_valid"]) or (old["uncache_busy"] and not old["uncache_busy"]))
    # Outputs are sampled after the edge, matching Verilator's #1 sample.
    out = {
        "need_flush": state["need_flush"],
        "debug_ctrl": state["debug_ctrl"],
        "debug_memvio": state["debug_memvio"],
        "fencei": state["fencei_reg"],
        "icache_flush": state["need_flush"],
        "wfi_req": state["wfi_reg"],
        "wfi_safe": state["safe2"],
        "error_valid": state["errv2"],
        "error_bits": state["errb2"],
        "reset_frontend": int(reset),
        "ptw_valid": 0,
        "ptw_vpn": vector["fetch_addr"] >> 12,
        "ptw_ready": int(not reset and not state["need_flush"]),
        "fetch_ready": int(not state["icache_busy"] and not state["need_flush"] and not state["fencei_reg"]),
        "uncache_ready": int(not state["uncache_busy"] and not state["need_flush"] and not state["fencei_reg"]),
        "fetch_resp_valid": int(state["icache_busy"] and not state["need_flush"]),
        "uncache_resp_valid": int(state["uncache_busy"] and not state["need_flush"]),
    }
    return out


def direct_check(module: Any, vectors: list[dict[str, int]]) -> dict[str, Any]:
    """Run direct Amaranth simulation against a software oracle. / 使用软件 oracle 运行 direct Amaranth 仿真。"""
    cfg = module.FrontendTopConfig()
    top = module.UHSCTop(cfg, {})
    state = {"need_flush": 0, "debug_ctrl": 0, "debug_memvio": 0, "fencei_reg": 0,
             "wfi_reg": 0, "pf1": 0, "pf2": 0, "fs1": 0, "fs2": 0, "bp1": 0, "bp2": 0,
             "sf1": 0, "sf2": 0, "errv1": 0, "errv2": 0, "errb1": 0, "errb2": 0,
             "safe1": 0, "safe2": 0, "ibuf": 0, "icache_busy": 0, "uncache_busy": 0}
    observed: list[dict[str, int]] = []
    expected: list[dict[str, int]] = []

    async def bench(ctx: Any) -> None:
        for vector in vectors:
            ctx.set(top.reset, vector["reset"])
            ctx.set(top.redirect_valid, vector["redirect"])
            ctx.set(top.redirect_debug_ctrl, vector["debug_ctrl"])
            ctx.set(top.redirect_debug_memvio, vector["debug_memvio"])
            ctx.set(top.fencei, vector["fencei"])
            ctx.set(top.wfi_req, vector["wfi"])
            ctx.set(top.sfence_valid, vector["sfence"])
            ctx.set(top.csr_pf_enable, vector["pf_enable"])
            ctx.set(top.csr_fs_off, vector["fs_off"])
            ctx.set(top.csr_bp_enable, vector["bp_enable"])
            ctx.set(top.fetch_req_valid, vector["fetch_valid"])
            ctx.set(top.fetch_req_addr, vector["fetch_addr"])
            ctx.set(top.uncache_req_valid, vector["uncache_valid"])
            ctx.set(top.uncache_req_addr, vector["uncache_addr"])
            ctx.set(top.icache_wfi_safe, vector["icache_safe"])
            ctx.set(top.instr_uncache_wfi_safe, vector["uncache_safe"])
            ctx.set(top.icache_error_valid, vector["error_valid"])
            ctx.set(top.icache_error_bits, vector["error_bits"])
            ctx.set(top.backend_can_accept, vector["backend_accept"])
            await ctx.tick("frontend_sync")
            expected_item = expected_step(state, vector, cfg)
            item = {
                "need_flush": int(ctx.get(top.need_flush)),
                "debug_ctrl": int(ctx.get(top.flush_control_redirect)),
                "debug_memvio": int(ctx.get(top.flush_mem_vio_redirect)),
                "fencei": int(ctx.get(top.icache_fencei)),
                "icache_flush": int(ctx.get(top.icache_flush)),
                "wfi_req": int(ctx.get(top.icache_wfi_req)),
                "wfi_safe": int(ctx.get(top.wfi_safe)),
                "error_valid": int(ctx.get(top.error_valid)),
                "error_bits": int(ctx.get(top.error_bits)),
                "reset_frontend": int(ctx.get(top.reset_in_frontend)),
                "ptw_valid": int(ctx.get(top.ptw_req_valid)),
                "ptw_vpn": int(ctx.get(top.ptw_req_vpn)),
                "ptw_ready": int(ctx.get(top.ptw_resp_ready)),
                "fetch_ready": int(ctx.get(top.fetch_req_ready)),
                "uncache_ready": int(ctx.get(top.uncache_req_ready)),
                "fetch_resp_valid": int(ctx.get(top.fetch_resp_valid)),
                "uncache_resp_valid": int(ctx.get(top.uncache_resp_valid)),
            }
            observed.append(item)
            expected.append(expected_item)

    simulator = Simulator(top)
    simulator.add_clock(1e-6, domain="frontend_sync")
    simulator.add_testbench(bench)
    simulator.run()
    mismatches = [{"cycle": i, "observed": got, "expected": want}
                  for i, (got, want) in enumerate(zip(observed, expected)) if got != want]
    trace = json.dumps(observed, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"status": "PASS" if not mismatches else "FAIL", "vectors": len(vectors),
            "trace_sha256": digest_bytes(trace), "mismatches": mismatches[:4],
            "checks": len(observed) * len(expected[0]) if expected else 0}


def target_port_declarations(rtl: str) -> tuple[list[str], dict[str, tuple[str, int]]]:
    """Parse generated target ports for a named ``.*`` differential wrapper. / 解析目标端口以生成命名差分包装器。"""
    match = re.search(r"module UHSCTop\((.*?)\);", rtl, re.DOTALL)
    if match is None:
        raise RuntimeError("UHSCTop declaration missing")
    names = [name for name in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", match.group(1))]
    body = rtl[match.end():]
    declarations: dict[str, tuple[str, int]] = {}
    for direction, width_text, name in re.findall(r"\b(input|output)\s*(\[[^]]+\])?\s*([A-Za-z_][A-Za-z0-9_]*)\s*;", body):
        width = 1
        if width_text:
            hi, lo = (int(item) for item in re.findall(r"\d+", width_text))
            width = abs(hi - lo) + 1
        declarations.setdefault(name, (direction, width))
    filtered = [name for name in names if name in declarations]
    return filtered, declarations


def sv_width(width: int) -> str:
    """Format a SystemVerilog packed width. / 格式化 SystemVerilog 打包位宽。"""
    return "" if width == 1 else f"[{width - 1}:0] "


def reference_projection() -> str:
    """Emit the locked-Frontend source-equation projection. / 生成锁定 Frontend 源方程投影。"""
    return r'''
module LockedFrontendProjection(
  input clock, input reset,
  input io_backend_toFtq_redirect_valid, input io_backend_toFtq_redirect_debugIsCtrl,
  input io_backend_toFtq_redirect_debugIsMemVio, input io_fencei,
  input io_backend_wfi_wfiReq, input io_csrCtrl_pf_enable, input io_csrCtrl_fsIsOff,
  input [4:0] io_csrCtrl_bp_enable, input io_sfence_valid,
  input io_fetch_req_valid, input [49:0] io_fetch_req_addr,
  input io_uncache_req_valid, input [49:0] io_uncache_req_addr,
  input io_icache_wfiSafe, input io_instrUncache_wfiSafe,
  input io_icache_error_valid, input [47:0] io_icache_error_bits,
  output reg io_needFlush, output reg io_flushControlRedirect,
  output reg io_flushMemVioRedirect, output reg io_icache_fencei,
  output io_icache_flush, output reg io_icache_wfiReq,
  output reg io_instrUncache_wfiReq, output io_backend_wfi_wfiSafe,
  output io_error_ecc_error_valid, output [47:0] io_error_ecc_error_bits,
  output io_resetInFrontend, output io_ptw_req_valid, output [37:0] io_ptw_req_vpn,
  output io_ptw_resp_ready, output io_fetch_req_ready, output io_uncache_req_ready,
  output io_fetch_resp_valid, output io_uncache_resp_valid,
  output [511:0] io_fetch_resp_data, output io_uncache_resp_data,
  output io_fetch_resp_error, output io_uncache_resp_error,
  output [5:0] io_backend_cfVec_valid, output [191:0] io_backend_cfVec_instr,
  output [299:0] io_backend_cfVec_pc, output [5:0] io_backend_cfVec_isRVC,
  output [5:0] io_backend_cfVec_predTaken, output [5:0] io_backend_cfVec_exception
);
  reg [4:0] pf1, pf2, bp1, bp2; reg fs1, fs2, sf1, sf2;
  reg errv1, errv2; reg [47:0] errb1, errb2;
  reg safe1, safe2; reg icache_busy, uncache_busy;
  reg wfi_req_d;
  always @(posedge clock or posedge reset) begin
    if (reset) begin
      io_needFlush <= 0; io_flushControlRedirect <= 0; io_flushMemVioRedirect <= 0;
      io_icache_fencei <= 0; io_icache_wfiReq <= 0; io_instrUncache_wfiReq <= 0;
      pf1 <= 0; pf2 <= 0; bp1 <= 0; bp2 <= 0; fs1 <= 0; fs2 <= 0; sf1 <= 0; sf2 <= 0;
      errv1 <= 0; errv2 <= 0; errb1 <= 0; errb2 <= 0; safe1 <= 0; safe2 <= 0;
      icache_busy <= 0; uncache_busy <= 0; wfi_req_d <= 0;
    end else begin
      // Frontend.scala: needFlush/Flush* are RegNext; ICache fencei is RegNext.
      io_needFlush <= io_backend_toFtq_redirect_valid;
      io_flushControlRedirect <= io_backend_toFtq_redirect_debugIsCtrl;
      io_flushMemVioRedirect <= io_backend_toFtq_redirect_debugIsMemVio;
      io_icache_fencei <= io_fencei;
      // Frontend.scala: DelayN(wfiReq,1), then DelayN(safe,1).
      io_icache_wfiReq <= io_backend_wfi_wfiReq;
      io_instrUncache_wfiReq <= io_backend_wfi_wfiReq;
      wfi_req_d <= io_backend_wfi_wfiReq;
      safe1 <= io_icache_wfiSafe && io_instrUncache_wfiSafe && wfi_req_d;
      safe2 <= safe1;
      // Frontend.scala: errorReg=RegNext(icache.error), then outer RegNext.
      errv1 <= io_icache_error_valid; errv2 <= errv1;
      errb1 <= io_icache_error_bits; errb2 <= errb1;
      pf1 <= io_csrCtrl_pf_enable; pf2 <= pf1; fs1 <= io_csrCtrl_fsIsOff; fs2 <= fs1;
      bp1 <= io_csrCtrl_bp_enable; bp2 <= bp1; sf1 <= io_sfence_valid; sf2 <= sf1;
      if (io_needFlush || io_icache_fencei) begin
        icache_busy <= 0; uncache_busy <= 0;
      end else begin
        if (!icache_busy && io_fetch_req_valid) icache_busy <= 1; else if (icache_busy) icache_busy <= 0;
        if (!uncache_busy && io_uncache_req_valid) uncache_busy <= 1; else if (uncache_busy) uncache_busy <= 0;
      end
    end
  end
  assign io_icache_flush = io_needFlush;
  assign io_backend_wfi_wfiSafe = safe2;
  assign io_error_ecc_error_valid = errv2;
  assign io_error_ecc_error_bits = errb2;
  assign io_resetInFrontend = reset;
  assign io_ptw_req_valid = 1'b0; assign io_ptw_req_vpn = io_fetch_req_addr[49:12];
  assign io_ptw_resp_ready = ~reset & ~io_needFlush;
  assign io_fetch_req_ready = ~icache_busy & ~io_needFlush & ~io_icache_fencei;
  assign io_uncache_req_ready = ~uncache_busy & ~io_needFlush & ~io_icache_fencei;
  assign io_fetch_resp_valid = icache_busy & ~io_needFlush;
  assign io_uncache_resp_valid = uncache_busy & ~io_needFlush;
  assign io_fetch_resp_data = 512'b0; assign io_uncache_resp_data = 512'b0;
  assign io_fetch_resp_error = 1'b0; assign io_uncache_resp_error = 1'b0;
  assign io_backend_cfVec_valid = 6'b0; assign io_backend_cfVec_instr = 192'b0;
  assign io_backend_cfVec_pc = 300'b0; assign io_backend_cfVec_isRVC = 6'b0;
  assign io_backend_cfVec_predTaken = 6'b0; assign io_backend_cfVec_exception = 6'b0;
endmodule
'''


def shell_for_target(target_rtl: str, vectors: list[dict[str, int]]) -> str:
    """Build a named-port target/reference Verilator harness. / 构造目标与参考命名端口 Verilator 测试台。"""
    names, declarations = target_port_declarations(target_rtl)
    lines = [target_rtl, reference_projection(), "module tb;", "  reg clock;", "  integer check_no;"]
    for name in names:
        direction, width = declarations[name]
        if name == "clock":
            continue
        kind = "reg" if direction == "input" else "wire"
        lines.append(f"  {kind} {sv_width(width)}{name};")
    # Reference signals use the same reduced names and are declared separately.
    ref_inputs = [
        ("reset", 1),
        ("io_backend_toFtq_redirect_valid", 1), ("io_backend_toFtq_redirect_debugIsCtrl", 1),
        ("io_backend_toFtq_redirect_debugIsMemVio", 1), ("io_fencei", 1),
        ("io_backend_wfi_wfiReq", 1), ("io_csrCtrl_pf_enable", 1), ("io_csrCtrl_fsIsOff", 1),
        ("io_csrCtrl_bp_enable", 5), ("io_sfence_valid", 1), ("io_fetch_req_valid", 1),
        ("io_fetch_req_addr", 50), ("io_uncache_req_valid", 1), ("io_uncache_req_addr", 50),
        ("io_icache_wfiSafe", 1), ("io_instrUncache_wfiSafe", 1),
        ("io_icache_error_valid", 1), ("io_icache_error_bits", 48),
    ]
    for name, width in ref_inputs:
        if name not in names:
            lines.append(f"  reg {sv_width(width)}{name}_ref;")
    compare_names = [
        "io_needFlush", "io_flushControlRedirect", "io_flushMemVioRedirect", "io_icache_fencei",
        "io_icache_flush", "io_icache_wfiReq", "io_instrUncache_wfiReq", "io_backend_wfi_wfiSafe",
        "io_error_ecc_error_valid", "io_error_ecc_error_bits", "io_resetInFrontend", "io_ptw_req_valid",
        "io_ptw_req_vpn", "io_ptw_resp_ready", "io_fetch_req_ready", "io_uncache_req_ready",
        "io_fetch_resp_valid", "io_uncache_resp_valid", "io_fetch_resp_data", "io_uncache_resp_data",
        "io_fetch_resp_error", "io_uncache_resp_error", "io_backend_cfVec_valid", "io_backend_cfVec_instr",
        "io_backend_cfVec_pc", "io_backend_cfVec_isRVC", "io_backend_cfVec_predTaken", "io_backend_cfVec_exception",
    ]
    for name in compare_names:
        direction, width = declarations.get(name, ("output", 1))
        del direction
        lines.append(f"  wire {sv_width(width)}{name}_ref;")
    lines.append("  UHSCTop dut(.*);")
    # Explicitly connect the reduced projection; target names are shared where possible.
    ref_conn = [".clock(clock)"]
    for name, _width in ref_inputs:
        if name == "reset":
            ref_conn.append(".reset(reset)")
            continue
        ref_conn.append(f".{name}({name if name in names else name + '_ref'})")
    for name in compare_names:
        ref_conn.append(f".{name}({name}_ref)")
    lines.append("  LockedFrontendProjection ref_i(" + ",".join(ref_conn) + ");")
    lines.append("  always #1 clock = ~clock;")
    # Equality task compares only ports present on the generated target.
    checks = []
    for name in compare_names:
        if name in declarations:
            checks.append(f"{name} !== {name}_ref")
    lines.append("  task check; begin #1; check_no = check_no + 1;")
    lines.append("    if (" + " || ".join(checks) + ") begin $display(\"MISMATCH %0d need=%b/%b ctrl=%b/%b mem=%b/%b fen=%b/%b ifl=%b/%b iw=%b/%b uw=%b/%b safe=%b/%b ev=%b/%b eb=%h/%h rst=%b/%b ptwv=%b/%b vpn=%h/%h ptwr=%b/%b fr=%b/%b ur=%b/%b fv=%b/%b uv=%b/%b fe=%b/%b ue=%b/%b cfv=%h/%h cfe=%h/%h\", check_no, io_needFlush, io_needFlush_ref, io_flushControlRedirect, io_flushControlRedirect_ref, io_flushMemVioRedirect, io_flushMemVioRedirect_ref, io_icache_fencei, io_icache_fencei_ref, io_icache_flush, io_icache_flush_ref, io_icache_wfiReq, io_icache_wfiReq_ref, io_instrUncache_wfiReq, io_instrUncache_wfiReq_ref, io_backend_wfi_wfiSafe, io_backend_wfi_wfiSafe_ref, io_error_ecc_error_valid, io_error_ecc_error_valid_ref, io_error_ecc_error_bits, io_error_ecc_error_bits_ref, io_resetInFrontend, io_resetInFrontend_ref, io_ptw_req_valid, io_ptw_req_valid_ref, io_ptw_req_vpn, io_ptw_req_vpn_ref, io_ptw_resp_ready, io_ptw_resp_ready_ref, io_fetch_req_ready, io_fetch_req_ready_ref, io_uncache_req_ready, io_uncache_req_ready_ref, io_fetch_resp_valid, io_fetch_resp_valid_ref, io_uncache_resp_valid, io_uncache_resp_valid_ref, io_fetch_resp_error, io_fetch_resp_error_ref, io_uncache_resp_error, io_uncache_resp_error_ref, io_backend_cfVec_valid, io_backend_cfVec_valid_ref, io_backend_cfVec_exception, io_backend_cfVec_exception_ref); $fatal(1, \"Frontend differential mismatch\"); end")
    lines.append("  end endtask")
    lines.append("  initial begin clock=0; check_no=0;")
    # Initialize every target input except clock.  Outputs are wires and must not be assigned.
    for name in names:
        direction, width = declarations[name]
        if direction == "input" and name != "clock":
            lines.append(f"    {name} = {width}'b0;")
    for name, width in ref_inputs:
        if name not in names:
            lines.append(f"    {name}_ref = {width}'b0;")
    for index, vector in enumerate(vectors):
        def setv(name: str, value: int, width: int) -> None:
            if name in names:
                lines.append(f"    {name} = {width}'h{value & ((1 << width) - 1):0{max(1, (width + 3) // 4)}x};")
        setv("reset", vector["reset"], 1); setv("io_backend_toFtq_redirect_valid", vector["redirect"], 1)
        setv("io_backend_toFtq_redirect_debugIsCtrl", vector["debug_ctrl"], 1)
        setv("io_backend_toFtq_redirect_debugIsMemVio", vector["debug_memvio"], 1)
        setv("io_fencei", vector["fencei"], 1); setv("io_backend_wfi_wfiReq", vector["wfi"], 1)
        setv("io_csrCtrl_pf_enable", vector["pf_enable"], 1); setv("io_csrCtrl_fsIsOff", vector["fs_off"], 1)
        setv("io_csrCtrl_bp_enable", vector["bp_enable"], 5); setv("io_sfence_valid", vector["sfence"], 1)
        setv("io_fetch_req_valid", vector["fetch_valid"], 1); setv("io_fetch_req_addr", vector["fetch_addr"], 50)
        setv("io_uncache_req_valid", vector["uncache_valid"], 1); setv("io_uncache_req_addr", vector["uncache_addr"], 50)
        setv("io_icache_wfiSafe", vector["icache_safe"], 1); setv("io_instrUncache_wfiSafe", vector["uncache_safe"], 1)
        setv("io_icache_error_valid", vector["error_valid"], 1); setv("io_icache_error_bits", vector["error_bits"], 48)
        if "reset" not in names:
            lines.append(f"    reset_ref = 1'h{vector['reset'] & 1:x};")
        lines.append("    #1; @(posedge clock); check;")
    lines.append(f"    $display(\"FRONTEND_PARENT_DIFFERENTIAL_PASS {len(vectors)}\"); $finish; end")
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def run_verilator(source: str, label: str) -> dict[str, Any]:
    """Compile and run one generated Verilator harness. / 编译并运行一个生成的 Verilator 测试台。"""
    WORK.mkdir(parents=True, exist_ok=True)
    # Install the stable ASCII WSL alias used by the bounded validators.
    root_wsl = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(ROOT)],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout.strip()
    subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"ln -sfn '{root_wsl}' /tmp/uhsc-v2"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    source_path = WORK / f"{label}.sv"
    source_path.write_text(source, encoding="utf-8", newline="\n")
    # Use the stable WSL mount path; this avoids non-ASCII host path quoting.
    wsl_source = "/tmp/uhsc-v2/validation/.work/v2-frontend-parent/" + source_path.name
    wsl_obj = "/tmp/uhsc-v2/validation/.work/v2-frontend-parent/obj-" + label
    command = ["wsl.exe", "-e", "bash", "-lc",
               f"mkdir -p {wsl_obj} && verilator --binary --timing -Wno-fatal --top-module tb --Mdir {wsl_obj} {wsl_source}"]
    compiled = subprocess.run(command, capture_output=True, check=False, timeout=240)
    compiled_stdout = compiled.stdout.decode("utf-8", "replace") if isinstance(compiled.stdout, bytes) else (compiled.stdout or "")
    compiled_stderr = compiled.stderr.decode("utf-8", "replace") if isinstance(compiled.stderr, bytes) else (compiled.stderr or "")
    if compiled.returncode != 0:
        return {"status": "FAIL_COMPILE", "returncode": compiled.returncode,
                "stderr_tail": compiled_stderr[-4000:], "source_sha256": digest(source_path)}
    binary = f"{wsl_obj}/Vtb"
    ran = subprocess.run(["wsl.exe", "-e", "bash", "-lc", binary], capture_output=True,
                         check=False, timeout=120)
    ran_stdout = ran.stdout.decode("utf-8", "replace") if isinstance(ran.stdout, bytes) else (ran.stdout or "")
    ran_stderr = ran.stderr.decode("utf-8", "replace") if isinstance(ran.stderr, bytes) else (ran.stderr or "")
    output = ran_stdout + ran_stderr
    return {"status": "PASS" if ran.returncode == 0 else "FAIL_RUN", "returncode": ran.returncode,
            "stdout_tail": output[-3000:], "trace_sha256": digest_bytes(output.encode("utf-8", "replace")),
            "trace_lines": len(output.splitlines()), "source_sha256": digest(source_path)}


def backend_gates(rtl: str) -> dict[str, Any]:
    """Run Verilator lint and Yosys check on target RTL. / 对目标 RTL 运行 Verilator lint 与 Yosys 检查。"""
    WORK.mkdir(parents=True, exist_ok=True)
    root_wsl = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(ROOT)],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout.strip()
    subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"ln -sfn '{root_wsl}' /tmp/uhsc-v2"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    rtl_path = WORK / "UHSCTop.sv"
    rtl_path.write_text(rtl, encoding="utf-8", newline="\n")
    wsl_rtl = "/tmp/uhsc-v2/validation/.work/v2-frontend-parent/UHSCTop.sv"
    ver_cmd = ["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal --top-module UHSCTop {wsl_rtl}"]
    ver = subprocess.run(ver_cmd, capture_output=True, check=False, timeout=120)
    ver_stderr = ver.stderr.decode("utf-8", "replace") if isinstance(ver.stderr, bytes) else (ver.stderr or "")
    yosys_cmd = ["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p 'read_verilog -sv {wsl_rtl}; hierarchy -top UHSCTop; proc; check'"]
    yosys = subprocess.run(yosys_cmd, capture_output=True, check=False, timeout=120)
    yosys_stderr = yosys.stderr.decode("utf-8", "replace") if isinstance(yosys.stderr, bytes) else (yosys.stderr or "")
    return {
        "verilator": {"status": "PASS" if ver.returncode == 0 else "FAIL", "returncode": ver.returncode,
                      "stderr_tail": ver_stderr[-1800:]},
        "yosys": {"status": "PASS" if yosys.returncode == 0 else "FAIL", "returncode": yosys.returncode,
                  "stderr_tail": yosys_stderr[-1800:]},
        "status": "PASS" if ver.returncode == 0 and yosys.returncode == 0 else "FAIL",
        "rtl_sha256": digest(rtl_path), "rtl_bytes": len(rtl.encode("utf-8")),
    }


def write_evidence(static: dict[str, Any], reference: dict[str, Any], direct: dict[str, Any],
                   differential: dict[str, Any], backend: dict[str, Any], vectors: list[dict[str, int]],
                   source_hash: str, projection_hash: str) -> None:
    """Persist all bounded parent evidence files. / 持久化所有精简父级证据文件。"""
    diff_pass = differential.get("status") == "PASS"
    backend_pass = backend.get("status") == "PASS"
    status = "PASS_BOUNDED_PARENT" if direct.get("status") == "PASS" and diff_pass and backend_pass else "FAIL"
    gates = {
        "PYTHON_PRESENT": "PASS",
        "DIRECT_TEST_PASS_BOUNDED": direct.get("status", "FAIL"),
        "V2_REFERENCE_MATCHED": "PASS_BOUNDED" if diff_pass else "FAIL",
        "PARENT_CLOSURE_MATCHED": "PASS_BOUNDED_REDUCED" if diff_pass else "FAIL",
        "VERILATOR": backend.get("verilator", {}).get("status", "FAIL"),
        "YOSYS": backend.get("yosys", {}).get("status", "FAIL"),
        "UHSC_LOCALIZED": "PASS_BOUNDED_PARENT_LOCAL_NAME",
        "LICENSE_REVIEW": "PENDING",
        "ACCEPTED": "NOT_ALLOWED",
    }
    direct_payload = {
        "schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_FRONTEND_PARENT_DIRECT",
        "batch_id": "V2-PARENT-FRONTEND-001", "source_commit": SOURCE_COMMIT,
        "target": static, "source": {"path": SOURCE.relative_to(ROOT).as_posix(), "sha256": source_hash},
        "direct": direct, "vectors": len(vectors), "gates": gates, "acceptance_eligible": False,
    }
    DIRECT_RESULT.write_text(json.dumps(direct_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    diff_payload = {
        "schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_FRONTEND_PARENT_DIFFERENTIAL",
        "batch_id": "V2-PARENT-FRONTEND-001", "source_commit": SOURCE_COMMIT,
        "reference_snapshot": reference,
        "reference_mode": "LOCKED_XSTOP_FRONTEND_SOURCE_EQUATION_PROJECTION",
        "reference_projection": {"module": "LockedFrontendProjection", "sha256": projection_hash,
                                 "provenance": ["Frontend.scala:68-71", "Frontend.scala:224", "Frontend.scala:445"]},
        "target": {"path": static["path"], "sha256": static["sha256"]},
        "comparison": differential, "backend_gates": backend,
        "behavioral_equivalence": diff_pass, "status": "DIFFERENTIAL_MATCHED_BOUNDED" if diff_pass else "FAIL",
        "gates": gates, "acceptance_eligible": False,
        "unclosed": [
            "Full 371-port Frontend child closure (BPU/FTQ/IFU/IBuffer/ICache/ITLB/PMP) remains outside this reduced batch.",
            "Projection compares locked Frontend parent equations; full child-level differential remains pending.",
            "License review and user approval remain open; ACCEPTED is not allowed.",
        ],
    }
    DIFF_RESULT.write_text(json.dumps(diff_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    contract_payload = {
        "schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_FRONTEND_PARENT_CONTRACT_AUDIT",
        "batch_id": "V2-PARENT-FRONTEND-001", "target": static, "source_commit": SOURCE_COMMIT,
        "child_contracts": {
            "ICache": "named injected dependency: request/response, fencei/flush, WFI/error",
            "InstrUncache": "named injected dependency: request/response and WFI",
            "FrontendPipeline": "optional named injected dependency for CF vector/perf",
            "BPU/FTQ/IFU/IBuffer/ITLB/PMP": "explicitly unimplemented reduced boundary",
        },
        "projection": {"module": "LockedFrontendProjection", "sha256": projection_hash},
        "gates": gates, "acceptance_eligible": False,
    }
    CONTRACT_RESULT.write_text(json.dumps(contract_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    coverage_payload = {
        "schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_FRONTEND_PARENT_COVERAGE",
        "batch_id": "V2-PARENT-FRONTEND-001", "source_commit": SOURCE_COMMIT,
        "closure_root": "core.frontend", "root_module": "Frontend",
        "root_source": SOURCE.relative_to(ROOT).as_posix(), "reference_snapshot": reference,
        "children": [
            {"instance": "Frontend.icache", "source": "upstream/src/main/scala/xiangshan/frontend/icache/ICache.scala", "status": "INJECTED_BOUNDARY"},
            {"instance": "Frontend.instrUncache", "source": "upstream/src/main/scala/xiangshan/frontend/icache/InstrUncache.scala", "status": "INJECTED_BOUNDARY"},
            {"instance": "Frontend.bpu", "source": "upstream/src/main/scala/xiangshan/frontend/BPU.scala", "status": "PENDING_FULL_CHILD"},
            {"instance": "Frontend.ifu", "source": "upstream/src/main/scala/xiangshan/frontend/IFU.scala", "status": "PENDING_FULL_CHILD"},
            {"instance": "Frontend.ibuffer", "source": "upstream/src/main/scala/xiangshan/frontend/IBuffer.scala", "status": "PENDING_FULL_CHILD"},
            {"instance": "Frontend.ftq", "source": "upstream/src/main/scala/xiangshan/frontend/NewFtq.scala", "status": "PENDING_FULL_CHILD"},
            {"instance": "Frontend.itlb", "source": "upstream/src/main/scala/xiangshan/cache/mmu/TLB.scala", "status": "PENDING_FULL_CHILD"},
        ],
        "observation_points": ["RegNext redirect/fencei", "DelayN WFI", "WFI safe join", "error double register",
                                "fetch/uncache ready-valid", "PTW ready/VPN", "CF-vector zero/injected boundary", "perf lanes"],
        "vectors": len(vectors), "status": status, "gates": gates,
        "uhsc_localization": {"status": "PASS_BOUNDED_PARENT_LOCAL_NAME", "source_name": "Frontend", "local_name": "UHSCTop",
                              "locked_names_unchanged": True}, "license_review": "PENDING", "acceptance_eligible": False,
    }
    COVERAGE_RESULT.write_text(json.dumps(coverage_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    mapping_payload = {
        "schema_version": 1, "kind": "V2_FRONTEND_PARENT_MAPPING_UPDATE", "batch_id": "V2-PARENT-FRONTEND-001",
        "source_commit": SOURCE_COMMIT,
        "entries": [{"id": "Frontend", "classification": "NEW_AUXILIARY_PARENT_HARNESS", "disposition": "PARENT_BOUNDARY_REDUCED",
                      "v2_source": SOURCE.relative_to(ROOT).as_posix(), "target": static["path"], "source_name": "Frontend",
                      "local_name": "UHSCTop", "status": status, "reference_mode": "LOCKED_XSTOP_FRONTEND_SOURCE_EQUATION_PROJECTION"}],
        "source_authority": reference, "gates": gates, "acceptance_eligible": False,
    }
    MAPPING_RESULT.write_text(json.dumps(mapping_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def differential_check(rtl: str, vectors: list[dict[str, int]]) -> tuple[dict[str, Any], str]:
    """Run locked-source projection differential and return its evidence/hash. / 运行锁定源投影差分并返回证据与摘要。"""
    projection = reference_projection()
    harness = shell_for_target(rtl, vectors)
    result = run_verilator(harness, "frontend-parent-diff")
    return result, digest_bytes(projection.encode("utf-8"))


def main() -> int:
    """Execute all V2 Frontend parent gates and write evidence. / 执行全部 V2 前端父级门禁并写入证据。"""
    if not TARGET.is_file() or not SOURCE.is_file() or not REFERENCE.is_file():
        raise RuntimeError("Frontend target/source/locked reference is missing")
    reference = reference_snapshot()
    if not reference["locked"]:
        raise RuntimeError("locked XSTop hash/size mismatch")
    target_module = load_target(TARGET, "v2_frontend_parent_target")
    static = static_audit(TARGET)
    compile_result = subprocess.run([sys.executable, "-m", "py_compile", str(TARGET)], capture_output=True, check=False)
    vectors = frontend_vectors()
    direct = direct_check(target_module, vectors)
    rtl = target_module.build_verilog({"module": "UHSCTop"}, {})
    backend = backend_gates(rtl)
    differential, projection_hash = differential_check(rtl, vectors)
    source_hash = digest(SOURCE)
    write_evidence(static, reference, direct, differential, backend, vectors, source_hash, projection_hash)
    overall = static["status"] == "PASS" and compile_result.returncode == 0 and direct["status"] == "PASS" and differential["status"] == "PASS" and backend["status"] == "PASS"
    print(json.dumps({"status": "PASS_BOUNDED_PARENT" if overall else "FAIL", "direct": direct["status"],
                      "differential": differential["status"], "verilator": backend["verilator"]["status"],
                      "yosys": backend["yosys"]["status"], "vectors": len(vectors),
                      "reference_module": reference["module"], "reference_ports": reference["port_count"]}, sort_keys=True))
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
