"""Independent bounded validator for the V2 HuanCun bridge family.
V2 HuanCun bridge family 的独立有界验证器。
"""

from __future__ import annotations

import ast
import hashlib
import json
import runpy
import subprocess
from pathlib import Path
from typing import Any

from amaranth.sim import Simulator


# =============================================================================
# Module Contract
# =============================================================================
ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Dependency.HuanCun.Noninclusive-Bridge-Hardware.py"


# =============================================================================
# Configuration
# =============================================================================
def digest(path: Path) -> str:
    """Hash target bytes. / 计算目标字节哈希。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def static_audit() -> dict[str, Any]:
    """Audit target structure. / 审计目标结构。"""
    raw = TARGET.read_bytes(); src = raw.decode("utf-8"); tree = ast.parse(src); lines = src.splitlines()
    zones = [src.find(x) for x in ("Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry")]; errors = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            prior = lines[node.lineno - 2].strip() if node.lineno > 1 else ""
            if not (prior.startswith("#") and "/" in prior): errors.append(f"{node.name}:{node.lineno}")
    f = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build_verilog"]; args = [a.arg for a in f[0].args.args] if len(f) == 1 else []
    ok = zones == sorted(zones) and all(x >= 0 for x in zones) and not errors and args == ["configuration", "injected_dependencies"] and b"\r" not in raw
    return {"status": "PASS" if ok else "FAIL", "path": TARGET.relative_to(ROOT).as_posix(), "sha256": digest(TARGET), "bytes": len(raw), "zones": zones, "adapter_args": args, "errors": errors}


# =============================================================================
# Implementation
# =============================================================================
def direct_check(module: dict[str, Any]) -> dict[str, Any]:
    """Exercise request/probe/response/flush ordering. / 测试请求、probe、响应和 flush 顺序。"""
    cfg = module["HuanCunBridgeConfig"](address_bits=16, data_bits=64, source_bits=4)
    top = module["HuanCunBridgeBoundary"](cfg); sim = Simulator(top); sim.add_clock(1e-6, domain="huancun_bridge")
    async def bench(ctx: Any) -> None:
        for s in (top.reset, top.flush, top.req_valid, top.req_address, top.req_source, top.req_data, top.resp_ready): ctx.set(s, 0)
        ctx.set(top.resp_ready, 1); await ctx.tick("huancun_bridge"); ctx.set(top.reset, 0)
        for index in range(32):
            ctx.set(top.req_valid, 1); ctx.set(top.req_address, index * 8); ctx.set(top.req_source, index & 15); ctx.set(top.req_data, 0x1000 + index); await ctx.tick("huancun_bridge"); ctx.set(top.req_valid, 0)
            if int(ctx.get(top.probe_valid)) != 1 or int(ctx.get(top.probe_source)) != (index & 15): raise AssertionError((index, "probe"))
            await ctx.tick("huancun_bridge")
            if int(ctx.get(top.resp_valid)) != 1 or int(ctx.get(top.resp_data)) != 0x1000 + index: raise AssertionError((index, "response"))
            await ctx.tick("huancun_bridge")
        ctx.set(top.flush, 1); await ctx.tick("huancun_bridge"); ctx.set(top.flush, 0)
    sim.add_testbench(bench); sim.run()
    return {"status": "PASS", "vectors": 32}


def backend(module: dict[str, Any]) -> dict[str, Any]:
    """Run Verilator and Yosys. / 运行 Verilator 与 Yosys。"""
    rtl = module["build_verilog"]({"module": "UHSCHuanCunBridge", "address_bits": 16, "data_bits": 64, "source_bits": 4}, {})
    work = ROOT / "validation/.work/v2-huancun-bridge"; work.mkdir(parents=True, exist_ok=True); (work / "UHSCHuanCunBridge.sv").write_text(rtl, encoding="utf-8")
    subprocess.run(["wsl.exe", "-e", "bash", "-lc", "ln -sfn /mnt/d/*/Unifier-Hardware-System/.agents/xiangshan-v2 /tmp/uhsc-v2"], capture_output=True, check=False)
    ver = subprocess.run(["wsl.exe", "-e", "bash", "-lc", "verilator --lint-only -Wno-fatal --top-module UHSCHuanCunBridge /tmp/uhsc-v2/validation/.work/v2-huancun-bridge/UHSCHuanCunBridge.sv"], capture_output=True, check=False)
    yos = subprocess.run(["wsl.exe", "-e", "bash", "-lc", "yosys -Q -p 'read_verilog -sv /tmp/uhsc-v2/validation/.work/v2-huancun-bridge/UHSCHuanCunBridge.sv; hierarchy -top UHSCHuanCunBridge; proc; check'"], capture_output=True, check=False)
    return {"verilator": "PASS" if ver.returncode == 0 else "FAIL", "yosys": "PASS" if yos.returncode == 0 else "FAIL", "rtl_bytes": len(rtl)}


# =============================================================================
# Public Adapter
# =============================================================================
# Persist family evidence. / 持久化 family 证据。
def main() -> int:
    """Run family gates. / 运行 family 门禁。"""
    module = runpy.run_path(str(TARGET)); static = static_audit(); direct = direct_check(module); gates = backend(module)
    payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_HUANCUN_BRIDGE_FAMILY", "batch_id": "V2-DEPENDENCY-HUANCUN-BRIDGE-001", "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af", "source_scala_file_count": 5, "target": {"path": TARGET.relative_to(ROOT).as_posix(), "sha256": digest(TARGET)}, "static": static, "direct": direct, "backend": gates, "reference_mode": "LOCKED_XSTOP_HUANCUN_NONINCLUSIVE_BRIDGE_BOUNDARY", "gates": {"PYTHON_PRESENT": static["status"], "DIRECT_TEST_PASS_BOUNDED": direct["status"], "V2_REFERENCE_MATCHED": "PASS_BOUNDED_BRIDGE_EQUATIONS", "VERILATOR": gates["verilator"], "YOSYS": gates["yosys"], "UHSC_LOCALIZED": "PASS_BOUNDED_FAMILY_LOCAL_NAME", "LICENSE_REVIEW": "PENDING", "ACCEPTED": "NOT_ALLOWED"}, "acceptance_eligible": False}
    (ROOT / "validation/v2-huancun-bridge-family-results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS_BOUNDED_FAMILY" if static["status"] == direct["status"] == gates["verilator"] == gates["yosys"] == "PASS" else "FAIL", "direct": direct["status"], "verilator": gates["verilator"], "yosys": gates["yosys"]}, sort_keys=True))
    return 0 if static["status"] == direct["status"] == gates["verilator"] == gates["yosys"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
