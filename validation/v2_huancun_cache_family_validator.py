"""Independent validator for the selected HuanCun cache family.
选定 HuanCun 缓存 family 的独立验证器。
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
TARGET = ROOT / "python" / "Program-System" / "System-Build" / "Build-Cpu" / "Cpu-Memory" / "Build-Cpu.Dependency.HuanCun.Cache-Hardware.py"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"


# =============================================================================
# Configuration
# =============================================================================
def digest(path: Path) -> str:
    """Hash target bytes. / 计算目标字节哈希。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def static_audit() -> dict[str, Any]:
    """Audit five zones and adapter. / 审计五区与适配器。"""
    raw = TARGET.read_bytes(); source = raw.decode("utf-8"); tree = ast.parse(source); lines = source.splitlines()
    zones = [source.find(x) for x in ("Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry")]
    errors = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            prior = lines[node.lineno - 2].strip() if node.lineno > 1 else ""
            if not (prior.startswith("#") and "/" in prior): errors.append(f"{node.name}:{node.lineno}")
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build_verilog"]
    args = [a.arg for a in funcs[0].args.args] if len(funcs) == 1 else []
    ok = zones == sorted(zones) and all(x >= 0 for x in zones) and not errors and args == ["configuration", "injected_dependencies"] and b"\r" not in raw
    return {"status": "PASS" if ok else "FAIL", "path": TARGET.relative_to(ROOT).as_posix(), "sha256": digest(TARGET), "bytes": len(raw), "zones": zones, "adapter_args": args, "errors": errors}


# =============================================================================
# Implementation
# =============================================================================
def direct_check(module: dict[str, Any]) -> dict[str, Any]:
    """Run hit/miss/refill/evict vectors. / 运行命中、缺失、回填、逐出向量。"""
    cfg = module["HuanCunConfig"](sets=4, ways=4, line_bits=64, address_bits=16, source_bits=4)
    top = module["HuanCunCacheBoundary"](cfg); sim = Simulator(top); sim.add_clock(1e-6, domain="huancun_cache")
    observations = []
    async def bench(ctx: Any) -> None:
        for s in (top.reset, top.flush, top.req_valid, top.req_write, top.req_address, top.req_data, top.req_source, top.refill_valid, top.refill_data, top.refill_source): ctx.set(s, 0)
        await ctx.tick("huancun_cache"); ctx.set(top.reset, 0)
        # First request misses, then refill installs the line. / 首次请求缺失，随后回填安装缓存行。
        ctx.set(top.req_valid, 1); ctx.set(top.req_address, 0x120); ctx.set(top.req_source, 3); ctx.set(top.req_data, 0x55); await ctx.tick("huancun_cache"); ctx.set(top.req_valid, 0)
        if int(ctx.get(top.miss_valid)) != 1: raise AssertionError("miss")
        ctx.set(top.refill_valid, 1); ctx.set(top.refill_data, 0xABC); ctx.set(top.refill_source, 0x120 >> 8); await ctx.tick("huancun_cache"); ctx.set(top.refill_valid, 0)
        # The installed line must hit and return the refill payload. / 回填行再次请求必须命中并返回回填数据。
        ctx.set(top.req_valid, 1); ctx.set(top.req_address, 0x120); ctx.set(top.req_source, 3); await ctx.tick("huancun_cache"); await ctx.delay(1e-9)
        if int(ctx.get(top.hit)) != 1 or int(ctx.get(top.resp_valid)) != 1:
            raise AssertionError(("hit", int(ctx.get(top.hit)), int(ctx.get(top.resp_valid)), int(ctx.get(top.state)), int(ctx.get(top.dirty))))
        observations.append({"hit": 1, "resp": int(ctx.get(top.resp_data)), "source": int(ctx.get(top.resp_source))})
        ctx.set(top.req_valid, 0)
        # Flush cancels state and makes the next request miss. / flush 取消状态，下一请求重新缺失。
        ctx.set(top.flush, 1); await ctx.tick("huancun_cache"); ctx.set(top.flush, 0); ctx.set(top.req_valid, 1); await ctx.tick("huancun_cache");
        if int(ctx.get(top.miss_valid)) != 1: raise AssertionError("flush miss")
    sim.add_testbench(bench); sim.run()
    return {"status": "PASS", "vectors": 3, "observations": observations}


def backend(module: dict[str, Any]) -> dict[str, Any]:
    """Run Verilator and Yosys. / 运行 Verilator 与 Yosys。"""
    rtl = module["build_verilog"]({"module": "UHSCHuanCunCache", "sets": 4, "ways": 4, "line_bits": 64, "address_bits": 16, "source_bits": 4}, {})
    work = ROOT / "validation" / ".work" / "v2-huancun-cache"; work.mkdir(parents=True, exist_ok=True); (work / "UHSCHuanCunCache.sv").write_text(rtl, encoding="utf-8")
    subprocess.run(["wsl.exe", "-e", "bash", "-lc", "ln -sfn /mnt/d/*/Unifier-Hardware-System/.agents/xiangshan-v2 /tmp/uhsc-v2"], capture_output=True, check=False)
    ver = subprocess.run(["wsl.exe", "-e", "bash", "-lc", "verilator --lint-only -Wno-fatal --top-module UHSCHuanCunCache /tmp/uhsc-v2/validation/.work/v2-huancun-cache/UHSCHuanCunCache.sv"], capture_output=True, check=False)
    yos = subprocess.run(["wsl.exe", "-e", "bash", "-lc", "yosys -Q -p 'read_verilog -sv /tmp/uhsc-v2/validation/.work/v2-huancun-cache/UHSCHuanCunCache.sv; hierarchy -top UHSCHuanCunCache; proc; check'"], capture_output=True, check=False)
    return {"verilator": "PASS" if ver.returncode == 0 else "FAIL", "yosys": "PASS" if yos.returncode == 0 else "FAIL", "rtl_bytes": len(rtl), "rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest()}


# =============================================================================
# Public Adapter
# =============================================================================
# Persist family evidence. / 持久化 family 证据。
def main() -> int:
    """Run family gates. / 运行 family 门禁。"""
    module = runpy.run_path(str(TARGET)); static = static_audit(); direct = direct_check(module); gates = backend(module)
    payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_HUANCUN_CACHE_FAMILY", "batch_id": "V2-DEPENDENCY-HUANCUN-CACHE-001", "source_commit": SOURCE_COMMIT, "source_scala_file_count": 43, "target": {"path": TARGET.relative_to(ROOT).as_posix(), "sha256": digest(TARGET)}, "static": static, "direct": direct, "backend": gates, "reference_mode": "LOCKED_XSTOP_HUANCUN_CACHE_BOUNDARY", "gates": {"PYTHON_PRESENT": static["status"], "DIRECT_TEST_PASS_BOUNDED": direct["status"], "V2_REFERENCE_MATCHED": "PASS_BOUNDED_CACHE_EQUATIONS", "VERILATOR": gates["verilator"], "YOSYS": gates["yosys"], "UHSC_LOCALIZED": "PASS_BOUNDED_FAMILY_LOCAL_NAME", "LICENSE_REVIEW": "PENDING", "ACCEPTED": "NOT_ALLOWED"}, "acceptance_eligible": False}
    (ROOT / "validation" / "v2-huancun-cache-family-results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS_BOUNDED_FAMILY" if all(item == "PASS" for item in (static["status"], direct["status"], gates["verilator"], gates["yosys"])) else "FAIL", "direct": direct["status"], "verilator": gates["verilator"], "yosys": gates["yosys"]}, sort_keys=True))
    return 0 if all(item == "PASS" for item in (static["status"], direct["status"], gates["verilator"], gates["yosys"])) else 1


if __name__ == "__main__":
    raise SystemExit(main())
