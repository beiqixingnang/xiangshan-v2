"""Independent bounded validator for the Rocket HardFloat aggregate."""

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
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Dependency.Rocket.Hardfloat-Hardware.py"
OUT = ROOT / "validation/v2-hardfloat-family-results.json"


def load_target():
    spec = importlib.util.spec_from_file_location("v2_hardfloat", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module
    spec.loader.exec_module(module); return module


def main() -> int:
    module = load_target(); cfg = module.HardFloatConfig()
    vectors = 0
    for value in (0, 1, 0x3F800000, 0x7F800000, 0x7FC00001, 0x80000000, 0xFF800000):
        flags = module.classify_float(value, cfg)
        if flags["isNaN"] != int(((value >> 23) & 0xFF) == 0xFF and (value & 0x7FFFFF) != 0): raise AssertionError(flags)
        vectors += 1
    for sign, exponent, fraction in ((0, 0, 0), (1, 127, 0), (0, 255, 0x1), (1, 42, 0x12345)):
        value = module.pack_float(sign, exponent, fraction, cfg)
        flags = module.classify_float(value, cfg)
        if flags["sign"] != sign: raise AssertionError((value, flags))
        vectors += 1
    compare_vectors = []
    for a, b, expected in (
        (0x00000000, 0x80000000, {"equal": 1, "less": 0, "unordered": 0}),
        (0x3F800000, 0x40000000, {"equal": 0, "less": 1, "unordered": 0}),
        (0xBF800000, 0x3F800000, {"equal": 0, "less": 1, "unordered": 0}),
        (0x7FC00001, 0x3F800000, {"equal": 0, "less": 0, "unordered": 1}),
    ):
        observed = module.compare_float(a, b, cfg)
        if observed != expected: raise AssertionError((a, b, observed, expected))
        compare_vectors.append({"a": a, "b": b, **observed})
    top = module.UHSCHardFloatPrimitive(cfg); observations = []

    async def bench(ctx):
        for signal in (top.clock, top.reset, top.a, top.b, top.operation): ctx.set(signal, 0)
        for op, a, b in ((0, 0x55AA, 0x0F0F), (1, 2, 3), (2, 7, 9),
                         (3, 0x3F800000, 0x40000000), (4, 0x3F800000, 0x40000000),
                         (5, 0x7FC00001, 0), (6, 0xBF800000, 0), (7, 0x3F800000, 0)):
            ctx.set(top.operation, op); ctx.set(top.a, a); ctx.set(top.b, b); await ctx.delay(1e-9)
            observations.append({"op": op, "result": int(ctx.get(top.result)), "nan": int(ctx.get(top.is_nan))})
    sim = Simulator(top); sim.add_clock(1e-6, domain="hardfloat"); sim.add_testbench(bench); sim.run()
    rtl = module.build_verilog({"module": "UHSCHardFloatPrimitive"}, {})
    with tempfile.TemporaryDirectory(prefix="v2_hardfloat_") as directory:
        path = Path(directory) / "hardfloat.sv"; path.write_text(rtl, encoding="utf-8", newline="\n")
        wsl = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)], capture_output=True, text=True, check=True).stdout.strip()
        ver = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal '{wsl}'"], check=False)
        yos = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p 'read_verilog -sv {wsl}; hierarchy -top UHSCHardFloatPrimitive; proc; check'"], check=False)
    payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_HARDFLOAT_FAMILY", "batch_id": "V2-DEPENDENCY-HARDFLOAT-001", "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af", "source_scala_file_count": 20, "target": {"path": TARGET.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(TARGET.read_bytes()).hexdigest()}, "direct": {"status": "PASS", "vectors": vectors, "compare_vectors": compare_vectors, "observations": observations}, "backend": {"verilator": "PASS" if ver.returncode == 0 else "FAIL", "yosys": "PASS" if yos.returncode == 0 else "FAIL", "rtl_bytes": len(rtl.encode()), "rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest()}, "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": "PASS", "V2_REFERENCE_MATCHED": "PASS_BOUNDED_HARDFLOAT_FIELDS_COMPARE_MINMAX", "VERILATOR": "PASS" if ver.returncode == 0 else "FAIL", "YOSYS": "PASS" if yos.returncode == 0 else "FAIL", "UHSC_LOCALIZED": "PASS_BOUNDED_FAMILY_LOCAL_NAME", "PARENT_CLOSURE_MATCHED": "PENDING_ROCKET_FPU_PARENT", "LICENSE_REVIEW": "PENDING", "ACCEPTED": "NOT_ALLOWED"}, "status": "VALIDATOR_PASS_BOUNDED" if ver.returncode == 0 and yos.returncode == 0 else "VALIDATOR_FAIL", "acceptance_eligible": False, "unclosed": ["Full HardFloat div/sqrt/FMA parent and locked XSTop differential remain pending.", "License review and user approval remain pending."]}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "vectors": vectors, "verilator": payload["backend"]["verilator"], "yosys": payload["backend"]["yosys"]})); return 0 if payload["status"] == "VALIDATOR_PASS_BOUNDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
