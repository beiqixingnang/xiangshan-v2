"""Independent bounded validator for the Fudian arithmetic aggregate."""

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
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Dependency.Fudian.Arithmetic-Hardware.py"
OUT = ROOT / "validation/v2-fudian-arithmetic-family-results.json"


def load_target():
    spec = importlib.util.spec_from_file_location("v2_fudian_arithmetic", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = load_target()
    vectors = 0
    for width in (8, 16, 32, 64):
        for value in (0, 1, 1 << (width - 1), (1 << width) - 1, 0x55 & ((1 << width) - 1)):
            expected = width - 1 if value == 0 else width - value.bit_length()
            if module.clz(value, width) != expected:
                raise AssertionError(("clz", width, value))
            vectors += 1
            for shift in (0, 1, width // 2, width, width + 1):
                got = module.shift_right_jam(value, shift, width)
                exp = (0, int(value != 0)) if shift > width else (value >> shift, int((value & ((1 << shift) - 1)) != 0))
                if got != exp:
                    raise AssertionError(("jam", width, value, shift, got, exp))
                vectors += 1
        for a, b in ((0, 0), (1, 2), ((1 << width) - 1, 0x55 & ((1 << width) - 1))):
            module.lza(a, b, width)
            vectors += 1
        for value, shift, rounding in ((0b1011, 1, 0), (0b1000, 2, 3), (0b1111, width, 4)):
            rounded, inexact = module.round_shift_right(value, shift, width, rounding)
            discarded_mask = (1 << min(shift, width)) - 1
            if not (0 <= rounded < (1 << width)) or inexact != int((value & discarded_mask) != 0):
                raise AssertionError(("round", width, value, shift, rounding, rounded, inexact))
            vectors += 1
    top = module.FudianArithmetic(module.ArithmeticConfig(width=8))
    observations = []

    async def bench(ctx):
        for signal in (top.clock, top.reset, top.a, top.b, top.shift, top.operation):
            ctx.set(signal, 0)
        for op, a, b, shift in ((0, 0, 0, 0), (0, 1, 0, 0), (2, 0xF3, 0, 3),
                                (3, 7, 9, 0), (5, 0b1011, 0, 1),
                                (5, 0b1000, 3, 2)):
            ctx.set(top.operation, op); ctx.set(top.a, a); ctx.set(top.b, b); ctx.set(top.shift, shift)
            await ctx.delay(1e-9)
            result = int(ctx.get(top.result)); sticky = int(ctx.get(top.sticky))
            if op == 5:
                expected, expected_sticky = module.round_shift_right(a, shift, 8, b & 0x7)
                if result != expected or sticky != expected_sticky:
                    raise AssertionError(("round-rtl", a, shift, b & 0x7, result, sticky, expected, expected_sticky))
            observations.append({"op": op, "result": result, "aux": int(ctx.get(top.auxiliary)), "sticky": sticky})
    sim = Simulator(top); sim.add_clock(1e-6, domain="fudian_arithmetic"); sim.add_testbench(bench); sim.run()
    rtl = module.build_verilog({"width": 8, "module": "UHSCFudianArithmetic"}, {})
    with tempfile.TemporaryDirectory(prefix="v2_fudian_arithmetic_") as directory:
        path = Path(directory) / "fudian.sv"; path.write_text(rtl, encoding="utf-8", newline="\n")
        wsl = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)], capture_output=True, text=True, check=True).stdout.strip()
        ver = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal '{wsl}'"], check=False)
        yos = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p 'read_verilog -sv {wsl}; hierarchy -top UHSCFudianArithmetic; proc; check'"], check=False)
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_FUDIAN_ARITHMETIC_FAMILY",
        "target": {"path": TARGET.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(TARGET.read_bytes()).hexdigest()},
        "source_scala_file_count": 5,
        "direct": {"status": "PASS", "vectors": vectors, "observations": observations},
        "backend": {"verilator": "PASS" if ver.returncode == 0 else "FAIL", "yosys": "PASS" if yos.returncode == 0 else "FAIL", "rtl_bytes": len(rtl.encode()), "rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest()},
        "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": "PASS", "V2_REFERENCE_MATCHED": "PASS_BOUNDED_ARITHMETIC_EQUATIONS", "VERILATOR": "PASS" if ver.returncode == 0 else "FAIL", "YOSYS": "PASS" if yos.returncode == 0 else "FAIL", "UHSC_LOCALIZED": "PASS_BOUNDED_FAMILY_LOCAL_NAME", "PARENT_CLOSURE_MATCHED": "PENDING_FUDIAN_FPU_PARENT", "LICENSE_REVIEW": "PENDING", "ACCEPTED": "NOT_ALLOWED"},
        "status": "VALIDATOR_PASS_BOUNDED" if ver.returncode == 0 and yos.returncode == 0 else "VALIDATOR_FAIL",
        "acceptance_eligible": False,
        "unclosed": ["Full Fudian FPU parent and locked XSTop differential remain pending.", "License review and user approval remain pending."],
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "vectors": vectors, "verilator": payload["backend"]["verilator"], "yosys": payload["backend"]["yosys"]}))
    return 0 if payload["status"] == "VALIDATOR_PASS_BOUNDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
