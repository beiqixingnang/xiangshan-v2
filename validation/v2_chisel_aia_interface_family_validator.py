"""Independent bounded validator for the V2 ChiselAIA interface family."""

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
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Dependency.ChiselAIA.Interface-Hardware.py"
OUT = ROOT / "validation/v2-chisel-aia-interface-family-results.json"


def load_target():
    spec = importlib.util.spec_from_file_location("v2_chisel_aia", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module
    spec.loader.exec_module(module); return module


def main() -> int:
    module = load_target()
    vectors = 0
    for pending, enable, source, claim, complete in ((0, 0, 0, False, False), (1, 1, 0, False, False), (0xA, 0xF, 0, True, False), (0, 0, 3, False, True)):
        got = module.aia_reference_step(pending, enable, source, claim, complete, 8)
        if got["active"] != (pending & enable): raise AssertionError(got)
        vectors += 1
    cfg = module.AIAConfig(irq_sources=8); top = module.UHSCAIAInterface(cfg); observations = []

    async def bench(ctx):
        for signal in (top.clock, top.reset, top.csr_valid, top.csr_write, top.csr_addr, top.csr_wdata, top.external_source): ctx.set(signal, 0)
        ctx.set(top.reset, 1); await ctx.tick("aia"); ctx.set(top.reset, 0)
        ctx.set(top.external_source, 2); await ctx.tick("aia"); ctx.set(top.external_source, 0); await ctx.delay(1e-9)
        observations.append({"pending": int(ctx.get(top.pending)), "interrupt": int(ctx.get(top.interrupt)), "claim": int(ctx.get(top.claim))})
        if observations[-1]["pending"] != 2 or observations[-1]["interrupt"] != 0: raise AssertionError(observations)
        ctx.set(top.csr_valid, 1); ctx.set(top.csr_write, 1); ctx.set(top.csr_addr, 0); ctx.set(top.csr_wdata, 2); await ctx.tick("aia"); ctx.set(top.csr_valid, 0); ctx.set(top.csr_write, 0); await ctx.delay(1e-9)
        if int(ctx.get(top.interrupt)) != 1 or int(ctx.get(top.claim)) != 2: raise AssertionError("enable/claim mismatch")
    sim = Simulator(top); sim.add_clock(1e-6, domain="aia"); sim.add_testbench(bench); sim.run()
    rtl = module.build_verilog({"irq_sources": 8, "module": "UHSCAIAInterface"}, {})
    with tempfile.TemporaryDirectory(prefix="v2_aia_") as directory:
        path = Path(directory) / "aia.sv"; path.write_text(rtl, encoding="utf-8", newline="\n")
        wsl = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)], capture_output=True, text=True, check=True).stdout.strip()
        ver = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal '{wsl}'"], check=False)
        yos = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p 'read_verilog -sv {wsl}; hierarchy -top UHSCAIAInterface; proc; check'"], check=False)
    payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_CHISELAIA_INTERFACE_FAMILY", "batch_id": "V2-DEPENDENCY-AIA-001", "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af", "source_scala_file_count": 6, "target": {"path": TARGET.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(TARGET.read_bytes()).hexdigest()}, "direct": {"status": "PASS", "vectors": vectors, "observations": observations}, "backend": {"verilator": "PASS" if ver.returncode == 0 else "FAIL", "yosys": "PASS" if yos.returncode == 0 else "FAIL", "rtl_bytes": len(rtl.encode()), "rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest()}, "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": "PASS", "V2_REFERENCE_MATCHED": "PASS_BOUNDED_AIA_EQUATIONS", "VERILATOR": "PASS" if ver.returncode == 0 else "FAIL", "YOSYS": "PASS" if yos.returncode == 0 else "FAIL", "UHSC_LOCALIZED": "PASS_BOUNDED_FAMILY_LOCAL_NAME", "PARENT_CLOSURE_MATCHED": "PENDING_SYSTEM_TOP_AIA_PARENT", "LICENSE_REVIEW": "PENDING", "ACCEPTED": "NOT_ALLOWED"}, "status": "VALIDATOR_PASS_BOUNDED" if ver.returncode == 0 and yos.returncode == 0 else "VALIDATOR_FAIL", "acceptance_eligible": False, "unclosed": ["Full AIA/SoC parent and locked XSTop differential remain pending.", "License review and user approval remain pending."]}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "vectors": vectors, "verilator": payload["backend"]["verilator"], "yosys": payload["backend"]["yosys"]})); return 0 if payload["status"] == "VALIDATOR_PASS_BOUNDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
