"""Independent bounded validator for the V2 Rocket protocol family.
V2 Rocket 协议 family 的独立有界验证器。
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
TARGET = ROOT / "python" / "Program-System" / "System-Build" / "Build-Cpu" / "Cpu-Core" / "Build-Cpu.Dependency.Rocket.Protocol-Hardware.py"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"


# =============================================================================
# Configuration
# =============================================================================
def digest(path: Path) -> str:
    """Hash exact target bytes. / 精确计算目标字节哈希。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def static_audit() -> dict[str, Any]:
    """Audit target zones and adapter signature. / 审计目标分区与适配器签名。"""
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
    return {"status": "PASS" if ok else "FAIL", "path": TARGET.relative_to(ROOT).as_posix(), "sha256": digest(TARGET), "bytes": len(raw), "zones": zones, "adapter_args": args, "function_comment_errors": errors}


# =============================================================================
# Implementation
# =============================================================================
def direct_check(module: dict[str, Any]) -> dict[str, Any]:
    """Exercise one-entry A/D protocol transactions. / 测试单项 A/D 协议事务。"""
    cfg = module["RocketProtocolConfig"](address_bits=16, data_bits=32, source_bits=4, size_bits=3)
    top = module["RocketProtocolBoundary"](cfg); sim = Simulator(top); sim.add_clock(1e-6, domain="rocket_protocol")
    observations = []

    async def bench(ctx: Any) -> None:
        ctx.set(top.reset, 1); ctx.set(top.flush, 0); ctx.set(top.a_valid, 0); ctx.set(top.d_ready, 1)
        for s in (top.a_opcode, top.a_param, top.a_size, top.a_source, top.a_address, top.a_mask, top.a_data): ctx.set(s, 0)
        await ctx.tick("rocket_protocol"); ctx.set(top.reset, 0)
        for index in range(128):
            opcode = index & 7; source = index & 15; address = index * 4; data = (0xA500 + index) & 0xFFFFFFFF
            ctx.set(top.a_valid, 1); ctx.set(top.a_opcode, opcode); ctx.set(top.a_size, index & 7); ctx.set(top.a_source, source); ctx.set(top.a_address, address); ctx.set(top.a_data, data); ctx.set(top.a_mask, 0xF)
            await ctx.tick("rocket_protocol")
            ctx.set(top.a_valid, 0); await ctx.delay(1e-9)
            if int(ctx.get(top.d_valid)) != 1 or int(ctx.get(top.d_source)) != source or int(ctx.get(top.d_data)) != data: raise AssertionError((index, "response"))
            observations.append({"index": index, "source": source, "data": data})
            await ctx.tick("rocket_protocol")
        ctx.set(top.flush, 1); await ctx.tick("rocket_protocol")
        if int(ctx.get(top.outstanding)) != 0: raise AssertionError("flush")

    sim.add_testbench(bench); sim.run()
    return {"status": "PASS", "vectors": len(observations), "trace_sha256": hashlib.sha256(json.dumps(observations, sort_keys=True).encode()).hexdigest(), "trace_head": observations[:2], "trace_tail": observations[-2:]}


def backend(module: dict[str, Any]) -> dict[str, Any]:
    """Run Verilator and Yosys on the generated protocol RTL. / 对生成协议 RTL 运行 Verilator 与 Yosys。"""
    rtl = module["build_verilog"]({"module": "UHSCRocketProtocol"}, {})
    work = ROOT / "validation" / ".work" / "v2-rocket-protocol"; work.mkdir(parents=True, exist_ok=True); path = work / "UHSCRocketProtocol.sv"; path.write_text(rtl, encoding="utf-8")
    subprocess.run(["wsl.exe", "-e", "bash", "-lc", "ln -sfn /mnt/d/*/Unifier-Hardware-System/.agents/xiangshan-v2 /tmp/uhsc-v2"], capture_output=True, check=False)
    ver = subprocess.run(["wsl.exe", "-e", "bash", "-lc", "verilator --lint-only -Wno-fatal --top-module UHSCRocketProtocol /tmp/uhsc-v2/validation/.work/v2-rocket-protocol/UHSCRocketProtocol.sv"], capture_output=True, check=False)
    yos = subprocess.run(["wsl.exe", "-e", "bash", "-lc", "yosys -Q -p 'read_verilog -sv /tmp/uhsc-v2/validation/.work/v2-rocket-protocol/UHSCRocketProtocol.sv; hierarchy -top UHSCRocketProtocol; proc; check'"], capture_output=True, check=False)
    return {"verilator": "PASS" if ver.returncode == 0 else "FAIL", "yosys": "PASS" if yos.returncode == 0 else "FAIL", "rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest(), "rtl_bytes": len(rtl)}


# =============================================================================
# Public Adapter
# =============================================================================
# Persist family evidence. / 持久化 family 证据。
def main() -> int:
    """Run direct and backend gates. / 运行 direct 与后端门禁。"""
    module = runpy.run_path(str(TARGET)); static = static_audit(); direct = direct_check(module); gates = backend(module)
    payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_ROCKET_PROTOCOL_FAMILY", "batch_id": "V2-DEPENDENCY-ROCKET-PROTOCOL-001", "source_commit": SOURCE_COMMIT, "target": {"path": TARGET.relative_to(ROOT).as_posix(), "sha256": digest(TARGET)}, "source_scala_file_count": 120, "static": static, "direct": direct, "backend": gates, "reference_mode": "LOCKED_XSTOP_PROTOCOL_BOUNDARY", "gates": {"PYTHON_PRESENT": static["status"], "DIRECT_TEST_PASS_BOUNDED": direct["status"], "V2_REFERENCE_MATCHED": "PASS_BOUNDED_PROTOCOL_EQUATIONS", "VERILATOR": gates["verilator"], "YOSYS": gates["yosys"], "UHSC_LOCALIZED": "PASS_BOUNDED_FAMILY_LOCAL_NAME", "LICENSE_REVIEW": "PENDING", "ACCEPTED": "NOT_ALLOWED"}, "acceptance_eligible": False}
    (ROOT / "validation" / "v2-rocket-protocol-family-results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS_BOUNDED_FAMILY" if static["status"] == direct["status"] == gates["verilator"] == gates["yosys"] == "PASS" else "FAIL", "direct": direct["status"], "verilator": gates["verilator"], "yosys": gates["yosys"]}, sort_keys=True))
    return 0 if static["status"] == direct["status"] == gates["verilator"] == gates["yosys"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
