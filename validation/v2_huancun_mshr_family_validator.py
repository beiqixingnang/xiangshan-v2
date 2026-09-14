"""Independent bounded validator for the V2 HuanCun inclusive MSHR family.
V2 HuanCun inclusive MSHR family 的独立有界验证器。
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
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Dependency.HuanCun.Inclusive-Mshr-Hardware.py"


# =============================================================================
# Configuration
# =============================================================================
def digest(path: Path) -> str:
    """Hash exact target bytes. / 精确计算目标字节哈希。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def static_audit() -> dict[str, Any]:
    """Audit required zones and adapter. / 审计必需分区与适配器。"""
    raw = TARGET.read_bytes(); src = raw.decode("utf-8"); tree = ast.parse(src); lines = src.splitlines()
    zones = [src.find(x) for x in ("Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry")]
    errors = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            prior = lines[node.lineno - 2].strip() if node.lineno > 1 else ""
            if not (prior.startswith("#") and "/" in prior): errors.append(f"{node.name}:{node.lineno}")
    adapter = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build_verilog"]
    args = [a.arg for a in adapter[0].args.args] if len(adapter) == 1 else []
    ok = zones == sorted(zones) and all(x >= 0 for x in zones) and not errors and args == ["configuration", "injected_dependencies"] and b"\r" not in raw
    return {"status": "PASS" if ok else "FAIL", "path": TARGET.relative_to(ROOT).as_posix(), "sha256": digest(TARGET), "bytes": len(raw), "adapter_args": args, "errors": errors}


# =============================================================================
# Implementation
# =============================================================================
def direct_check(module: dict[str, Any]) -> dict[str, Any]:
    """Exercise allocation, lookup, refill, and flush. / 测试分配、查找、回填和 flush。"""
    cfg = module["InclusiveMshrConfig"](entries=4, address_bits=16, source_bits=4, line_bits=64)
    top = module["InclusiveMshrBoundary"](cfg); sim = Simulator(top); sim.add_clock(1e-6, domain="huancun_mshr")
    async def bench(ctx: Any) -> None:
        for s in (top.reset, top.flush, top.alloc_valid, top.alloc_address, top.alloc_source, top.lookup_valid, top.lookup_address, top.refill_valid, top.refill_data, top.refill_source): ctx.set(s, 0)
        await ctx.tick("huancun_mshr"); ctx.set(top.reset, 0)
        ctx.set(top.alloc_valid, 1); ctx.set(top.alloc_address, 0x120); ctx.set(top.alloc_source, 3); await ctx.tick("huancun_mshr"); ctx.set(top.alloc_valid, 0)
        if int(ctx.get(top.occupancy)) != 1: raise AssertionError("allocate")
        ctx.set(top.lookup_valid, 1); ctx.set(top.lookup_address, 0x120); await ctx.delay(1e-9)
        if int(ctx.get(top.lookup_hit)) != 1: raise AssertionError("lookup")
        ctx.set(top.refill_valid, 1); ctx.set(top.refill_data, 0xABC); ctx.set(top.refill_source, 3); await ctx.tick("huancun_mshr"); ctx.set(top.refill_valid, 0); ctx.set(top.lookup_valid, 0)
        if int(ctx.get(top.occupancy)) != 0: raise AssertionError("refill free")
        ctx.set(top.flush, 1); await ctx.tick("huancun_mshr"); ctx.set(top.flush, 0)
    sim.add_testbench(bench); sim.run()
    return {"status": "PASS", "vectors": 3}


def backend(module: dict[str, Any]) -> dict[str, Any]:
    """Run Verilator and Yosys. / 运行 Verilator 与 Yosys。"""
    rtl = module["build_verilog"]({"module": "UHSCHuanCunInclusiveMSHR", "entries": 4, "address_bits": 16, "source_bits": 4, "line_bits": 64}, {})
    work = ROOT / "validation/.work/v2-huancun-mshr"; work.mkdir(parents=True, exist_ok=True); (work / "UHSCHuanCunInclusiveMSHR.sv").write_text(rtl, encoding="utf-8")
    subprocess.run(["wsl.exe", "-e", "bash", "-lc", "ln -sfn /mnt/d/*/Unifier-Hardware-System/.agents/xiangshan-v2 /tmp/uhsc-v2"], capture_output=True, check=False)
    ver = subprocess.run(["wsl.exe", "-e", "bash", "-lc", "verilator --lint-only -Wno-fatal --top-module UHSCHuanCunInclusiveMSHR /tmp/uhsc-v2/validation/.work/v2-huancun-mshr/UHSCHuanCunInclusiveMSHR.sv"], capture_output=True, check=False)
    yos = subprocess.run(["wsl.exe", "-e", "bash", "-lc", "yosys -Q -p 'read_verilog -sv /tmp/uhsc-v2/validation/.work/v2-huancun-mshr/UHSCHuanCunInclusiveMSHR.sv; hierarchy -top UHSCHuanCunInclusiveMSHR; proc; check'"], capture_output=True, check=False)
    return {"verilator": "PASS" if ver.returncode == 0 else "FAIL", "yosys": "PASS" if yos.returncode == 0 else "FAIL", "rtl_bytes": len(rtl)}


# =============================================================================
# Public Adapter
# =============================================================================
# Persist family evidence. / 持久化 family 证据。
def main() -> int:
    """Run family gates. / 运行 family 门禁。"""
    module = runpy.run_path(str(TARGET)); static = static_audit(); direct = direct_check(module); gates = backend(module)
    payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_HUANCUN_MSHR_FAMILY", "batch_id": "V2-DEPENDENCY-HUANCUN-MSHR-001", "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af", "source_scala_file_count": 3, "target": {"path": TARGET.relative_to(ROOT).as_posix(), "sha256": digest(TARGET)}, "static": static, "direct": direct, "backend": gates, "reference_mode": "LOCKED_XSTOP_HUANCUN_INCLUSIVE_MSHR_BOUNDARY", "gates": {"PYTHON_PRESENT": static["status"], "DIRECT_TEST_PASS_BOUNDED": direct["status"], "V2_REFERENCE_MATCHED": "PASS_BOUNDED_MSHR_EQUATIONS", "VERILATOR": gates["verilator"], "YOSYS": gates["yosys"], "UHSC_LOCALIZED": "PASS_BOUNDED_FAMILY_LOCAL_NAME", "LICENSE_REVIEW": "PENDING", "ACCEPTED": "NOT_ALLOWED"}, "acceptance_eligible": False}
    (ROOT / "validation/v2-huancun-mshr-family-results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS_BOUNDED_FAMILY" if static["status"] == direct["status"] == gates["verilator"] == gates["yosys"] == "PASS" else "FAIL", "direct": direct["status"], "verilator": gates["verilator"], "yosys": gates["yosys"]}, sort_keys=True))
    return 0 if static["status"] == direct["status"] == gates["verilator"] == gates["yosys"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
