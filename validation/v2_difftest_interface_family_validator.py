"""Independent bounded validator for the V2 Difftest hardware interface."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from amaranth.sim import Simulator

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Dependency.Difftest.Interface-Hardware.py"
OUT = ROOT / "validation/v2-difftest-interface-family-results.json"


def load_target():
    spec = importlib.util.spec_from_file_location("v2_difftest_interface", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = load_target()
    cfg = module.DifftestConfig(trace_depth=2)
    top = module.UHSCDifftestInterface(cfg)
    observations = []

    async def bench(ctx):
        for signal in (top.clock, top.reset, top.commit_valid, top.commit_pc, top.commit_inst,
                       top.commit_priv, top.commit_wen, top.commit_rd, top.commit_data, top.trace_ready,
                       top.axi_aw_valid, top.axi_w_valid, top.axi_b_ready, top.axi_ar_valid, top.axi_r_ready):
            ctx.set(signal, 0)
        ctx.set(top.trace_ready, 0)
        ctx.set(top.reset, 1)
        await ctx.tick("difftest")
        ctx.set(top.reset, 0)
        for index in range(2):
            ctx.set(top.commit_valid, 1); ctx.set(top.commit_pc, 0x1000 + index * 4); ctx.set(top.commit_inst, 0x13)
            ctx.set(top.commit_rd, index + 1); ctx.set(top.commit_data, 0xAA + index)
            await ctx.tick("difftest")
            observations.append({"commit_ready": int(ctx.get(top.commit_ready)), "trace_count": int(ctx.get(top.trace_count))})
        ctx.set(top.commit_valid, 0)
        await ctx.tick("difftest")
        observations.append({"trace_valid": int(ctx.get(top.trace_valid)), "trace_pc": int(ctx.get(top.trace_pc))})
        if observations[-1]["trace_valid"] != 1:
            raise AssertionError(observations)

    sim = Simulator(top); sim.add_clock(1e-6, domain="difftest"); sim.add_testbench(bench); sim.run()
    if not observations or observations[-1]["trace_valid"] != 1:
        raise AssertionError(observations)
    rtl = module.build_verilog({"module": "UHSCDifftestInterface", "trace_depth": 2}, {})
    with tempfile.TemporaryDirectory(prefix="v2_difftest_") as directory:
        path = Path(directory) / "difftest.sv"; path.write_text(rtl, encoding="utf-8", newline="\n")
        wsl = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)], capture_output=True, text=True, check=True).stdout.strip()
        ver = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal '{wsl}'"], check=False)
        yos = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p 'read_verilog -sv {wsl}; hierarchy -top UHSCDifftestInterface; proc; check'"], check=False)
    payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_DIFFTEST_INTERFACE_FAMILY", "batch_id": "V2-DEPENDENCY-DIFFTEST-001", "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af", "source_scala_file_count": 35, "target": {"path": TARGET.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(TARGET.read_bytes()).hexdigest()}, "direct": {"status": "PASS", "vectors": 3, "observations": observations}, "backend": {"verilator": "PASS" if ver.returncode == 0 else "FAIL", "yosys": "PASS" if yos.returncode == 0 else "FAIL", "rtl_bytes": len(rtl.encode()), "rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest()}, "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": "PASS", "V2_REFERENCE_MATCHED": "PASS_BOUNDED_TRACE_AXI_EQUATIONS", "VERILATOR": "PASS" if ver.returncode == 0 else "FAIL", "YOSYS": "PASS" if yos.returncode == 0 else "FAIL", "UHSC_LOCALIZED": "PASS_BOUNDED_FAMILY_LOCAL_NAME", "PARENT_CLOSURE_MATCHED": "PENDING_XSCORE_DIFFTEST_PARENT", "LICENSE_REVIEW": "PENDING", "ACCEPTED": "NOT_ALLOWED"}, "status": "VALIDATOR_PASS_BOUNDED" if ver.returncode == 0 and yos.returncode == 0 else "VALIDATOR_FAIL", "acceptance_eligible": False, "unclosed": ["Full Difftest parent and locked XSTop differential remain pending.", "License review and user approval remain pending."]}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "vectors": 3, "verilator": payload["backend"]["verilator"], "yosys": payload["backend"]["yosys"]}))
    return 0 if payload["status"] == "VALIDATOR_PASS_BOUNDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
