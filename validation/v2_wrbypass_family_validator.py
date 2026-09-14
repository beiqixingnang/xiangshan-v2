"""Independent V2 WrBypass CAM/PLRU validation.
昆明湖 V2 WrBypass CAM/PLRU 独立验证。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import random
import subprocess
import sys
from pathlib import Path

from amaranth.sim import Simulator


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Frontend.Bpu.WrBypass-Hardware.py"
WORK = ROOT / "validation/.work/v2-wrbypass"
EVIDENCE = ROOT / "validation/v2-wrbypass-family-results.json"


def load_target():
    """Load the final WrBypass Build target. / 加载最终 WrBypass Build 目标。"""
    spec = importlib.util.spec_from_file_location("v2_wrbypass", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load WrBypass target")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def direct(module) -> dict[str, object]:
    """Compare CAM hit/data outputs against a software PLRU reference. / 将 CAM 命中与数据输出和软件 PLRU 参考比较。"""
    cfg = module.WrBypassConfig(num_entries=8, idx_width=9, data_width=3)
    top = module.WrBypass(cfg)
    rng = random.Random(0xB2A5)
    entries: list[tuple[int, int] | None] = [None] * 8
    state = 0
    checks = 0

    async def bench(ctx) -> None:
        nonlocal state, checks
        ctx.set(top.reset, 1)
        await ctx.tick("sync")
        ctx.set(top.reset, 0)
        for _ in range(256):
            idx = rng.randrange(32)
            data = rng.randrange(8)
            ctx.set(top.wen, 1)
            ctx.set(top.write_idx, idx)
            ctx.set(top.write_data[0], data)
            await ctx.tick("sync")
            victim = module.plru_victim_reference(state, 8)
            slot = next((pos for pos, entry in enumerate(entries) if entry is not None and entry[0] == idx), victim)
            entries[slot] = (idx, data)
            state = module.plru_next_reference(state, slot, 8)
            checks += 1
            # Probe after the write has committed; this is the observable
            # read phase of the CAM, not the write edge itself.
            ctx.set(top.wen, 0)
            ctx.set(top.write_idx, idx)
            await ctx.tick("sync")
            if int(ctx.get(top.hit)) != 1 or int(ctx.get(top.hit_data_valid[0])) != 1 or int(ctx.get(top.hit_data_bits[0])) != data:
                raise AssertionError(("readback", idx, data, int(ctx.get(top.hit)), int(ctx.get(top.hit_data_bits[0]))))
            checks += 1
        ctx.set(top.wen, 0)
        for idx, entry in enumerate(entries):
            if entry is None:
                continue
            ctx.set(top.write_idx, entry[0])
            await ctx.tick("sync")
            if int(ctx.get(top.hit)) != 1 or int(ctx.get(top.hit_data_bits[0])) != entry[1]:
                raise AssertionError(("final", idx, entry, int(ctx.get(top.hit)), int(ctx.get(top.hit_data_bits[0]))))
            checks += 1

    sim = Simulator(top)
    sim.add_clock(1e-6, domain="sync")
    sim.add_testbench(bench)
    sim.run()
    return {"status": "PASS", "vectors": checks, "entries": entries, "plru_state": state}


def backend(module) -> dict[str, object]:
    """Run Verilator and Yosys on the generated WrBypass RTL. / 对生成 RTL 运行 Verilator 与 Yosys。"""
    WORK.mkdir(parents=True, exist_ok=True)
    rtl = module.build_verilog({}, {})
    path = WORK / "wrbypass.sv"
    path.write_text(rtl, encoding="utf-8", newline="\n")
    wsl = str(path.resolve()).replace("\\", "/")
    if len(wsl) >= 2 and wsl[1] == ":":
        wsl = "/mnt/" + wsl[0].lower() + wsl[2:]
    ver = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal {wsl}"], capture_output=True, check=False)
    yos = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p 'read_verilog -sv {wsl}; hierarchy -top WrBypass; proc; check'"], capture_output=True, check=False)
    return {"status": "PASS" if ver.returncode == yos.returncode == 0 else "FAIL", "verilator": "PASS" if ver.returncode == 0 else "FAIL", "yosys": "PASS" if yos.returncode == 0 else "FAIL", "rtl_bytes": len(rtl.encode()), "rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest()}


def main() -> int:
    """Write bounded WrBypass evidence. / 写入 WrBypass bounded 证据。"""
    module = load_target()
    d = direct(module)
    b = backend(module)
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_WRBYPASS_FAMILY",
        "batch_id": "V2-DEPENDENCY-WRBYPASS-001",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "source_scala_files": ["upstream/src/main/scala/xiangshan/frontend/WrBypass.scala", "upstream/src/main/scala/xiangshan/frontend/Bim.scala", "upstream/src/main/scala/xiangshan/frontend/Tage.scala", "upstream/src/main/scala/xiangshan/frontend/SC.scala"],
        "target": {"path": TARGET.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(TARGET.read_bytes()).hexdigest()},
        "direct": d,
        "backend": b,
        "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": d["status"], "V2_REFERENCE_MATCHED": "PASS_BOUNDED_PLRU_CAM_EQUATIONS", "VERILATOR": b["verilator"], "YOSYS": b["yosys"], "PARENT_CLOSURE_MATCHED": "PENDING_FRONTEND_BPU_PARENT", "LICENSE_REVIEW": "PENDING", "ACCEPTED": "NOT_ALLOWED"},
        "status": "VALIDATOR_PASS_BOUNDED" if d["status"] == b["status"] == "PASS" else "VALIDATOR_FAIL",
        "acceptance_eligible": False,
        "unclosed": ["Full BPU/TAGE/SC parent closure and locked XSTop behavioral differential remain pending.", "License review and user approval remain pending."],
    }
    EVIDENCE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "direct": d["status"], "vectors": d["vectors"], "verilator": b["verilator"], "yosys": b["yosys"], "ACCEPTED": "NOT_ALLOWED"}))
    return 0 if payload["status"] == "VALIDATOR_PASS_BOUNDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
