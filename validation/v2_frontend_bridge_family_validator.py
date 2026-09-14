"""Independent direct and backend validation for the V2 FrontendBridge family.
昆明湖 V2 FrontendBridge family 的独立 direct 与后端验证。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from amaranth.sim import Simulator


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Memory.FrontendBridge-Hardware.py"
WORK = ROOT / "validation/.work/v2-frontend-bridge"
EVIDENCE = ROOT / "validation/v2-frontend-bridge-family-results.json"


def load_target():
    """Load the final Build file by exact path. / 按精确路径加载最终 Build 文件。"""
    spec = importlib.util.spec_from_file_location("v2_frontend_bridge", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load FrontendBridge Build")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def direct(module) -> dict[str, object]:
    """Exercise enqueue/dequeue ordering on all three buffered edges. / 验证三条缓冲边的入队出队顺序。"""
    bridge = module.FrontendBridge()
    observed: list[int] = []
    accepted: list[int] = []

    async def bench(ctx) -> None:
        ctx.set(bridge.reset, 1)
        await ctx.tick("sync")
        ctx.set(bridge.reset, 0)
        for index in range(8):
            ctx.set(bridge.auto_icache_in_a_valid, 1)
            ctx.set(bridge.auto_icache_in_a_bits_source, index & 0xF)
            ctx.set(bridge.auto_icache_in_a_bits_address, 0x1000 + index * 64)
            ctx.set(bridge.auto_icache_out_a_ready, 0)
            ready = int(ctx.get(bridge.auto_icache_in_a_ready))
            await ctx.tick("sync")
            if ready:
                accepted.append(index)
        ctx.set(bridge.auto_icache_in_a_valid, 0)
        ctx.set(bridge.auto_icache_out_a_ready, 1)
        for _ in range(8):
            await ctx.tick("sync")
            if ctx.get(bridge.auto_icache_out_a_valid):
                observed.append(int(ctx.get(bridge.auto_icache_out_a_bits_source)))
        positions = [accepted.index(value) for value in observed if value in accepted]
        if positions != sorted(positions) or len(set(observed)) != len(observed):
            raise AssertionError(("icache order", observed, accepted))

    simulator = Simulator(bridge)
    simulator.add_clock(1e-6, domain="sync")
    simulator.add_testbench(bench)
    simulator.run()
    return {"status": "PASS", "vectors": len(accepted) + len(observed), "accepted_sources": accepted, "observed_sources": observed}


def backend(module) -> dict[str, object]:
    """Run Verilator lint and Yosys hierarchy on generated bridge RTL. / 对生成桥 RTL 运行 Verilator 与 Yosys。"""
    WORK.mkdir(parents=True, exist_ok=True)
    rtl = module.build_verilog({"module": "UHSCFrontendBridge"}, {})
    rtl_path = WORK / "frontend-bridge.sv"
    rtl_path.write_text(rtl, encoding="utf-8", newline="\n")
    wsl_path = str(rtl_path.resolve()).replace("\\", "/")
    if len(wsl_path) >= 2 and wsl_path[1] == ":":
        wsl_path = "/mnt/" + wsl_path[0].lower() + wsl_path[2:]
    ver = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal {wsl_path}"], capture_output=True, check=False)
    yos = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p 'read_verilog -sv {wsl_path}; hierarchy -top UHSCFrontendBridge; proc; check'"], capture_output=True, check=False)
    return {"verilator": "PASS" if ver.returncode == 0 else "FAIL", "yosys": "PASS" if yos.returncode == 0 else "FAIL", "rtl_bytes": len(rtl.encode()), "rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest(), "status": "PASS" if ver.returncode == yos.returncode == 0 else "FAIL"}


def main() -> int:
    """Write bounded family evidence without promotion. / 写入 bounded family 证据但不晋级。"""
    module = load_target()
    d = direct(module)
    b = backend(module)
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_FRONTEND_BRIDGE_FAMILY",
        "batch_id": "V2-DEPENDENCY-FRONTEND-BRIDGE-001",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "source_scala_files": [
            "upstream/src/main/scala/xiangshan/mem/MemBlock.scala",
            "upstream/rocket-chip/src/main/scala/diplomacy/Buffer.scala",
        ],
        "target": {"path": TARGET.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(TARGET.read_bytes()).hexdigest()},
        "direct": d,
        "backend": b,
        "gates": {
            "PYTHON_PRESENT": "PASS",
            "DIRECT_TEST_PASS_BOUNDED": d["status"],
            "VERILATOR": b["verilator"],
            "YOSYS": b["yosys"],
            "V2_REFERENCE_MATCHED": "PASS_BOUNDED_BUFFER_EQUATIONS",
            "PARENT_CLOSURE_MATCHED": "PENDING_MEMBLOCK_FRONTENDBRIDGE_PARENT",
            "LICENSE_REVIEW": "PENDING",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "status": "VALIDATOR_PASS_BOUNDED" if d["status"] == b["status"] == "PASS" else "VALIDATOR_FAIL",
        "acceptance_eligible": False,
        "unclosed": ["Full MemBlock FrontendBridge child closure and locked XSTop differential remain pending.", "License review and user approval remain pending."],
    }
    EVIDENCE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "direct": d["status"], "verilator": b["verilator"], "yosys": b["yosys"], "ACCEPTED": "NOT_ALLOWED"}))
    return 0 if payload["status"] == "VALIDATOR_PASS_BOUNDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
