"""Bounded locked-reference differential for the V2 InstrMMIOEntry child.
V2 指令 MMIO 单项表项的有界锁定参考差分验证。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import random
import shlex
import subprocess
import sys
from pathlib import Path

from amaranth.sim import Simulator

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Cpu-Core-Frontend.Icache.InstrMMIOEntry-Hardware.py"
LOCKED = Path(r"\\wsl$\Debian\home\lishuo\xs-v2-local\build\rtl\XSTop.sv")
WORK = ROOT / "validation/.work/v2-frontend-instr-mmio-entry-child"
EVIDENCE = ROOT / "validation/v2-frontend-instr-mmio-entry-child-differential-results.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
LOCKED_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(path: Path):
    spec = importlib.util.spec_from_file_location("v2_instr_mmio_target", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def wsl_path(path: Path) -> str:
    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path.resolve())],
                            capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", "replace"))
    value = result.stdout.decode("utf-8", "replace").strip()
    if not value.startswith("/"):
        raise RuntimeError(value)
    return value


def run_wsl(command: list[str]) -> dict[str, object]:
    rendered = " ".join(shlex.quote(item) for item in command)
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered],
                            capture_output=True, check=False)
    output = result.stdout + result.stderr
    return {"command": command, "returncode": result.returncode,
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "output_tail": output.decode("utf-8", "replace")[-1800:],
            "output_sha256": digest(output)}


def extract(name: str) -> bytes:
    marker = f"module {name}(".encode()
    active = False
    depth = 0
    lines: list[bytes] = []
    with LOCKED.open("rb") as stream:
        for line in stream:
            if not active and line.lstrip().startswith(marker):
                active, depth = True, 1
            if active:
                lines.append(line)
                if line.lstrip().startswith(b"module ") and not line.lstrip().startswith(marker):
                    depth += 1
                if line.lstrip().startswith(b"endmodule"):
                    depth -= 1
                    if depth == 0:
                        return b"".join(lines)
    raise RuntimeError(name)


def direct_model_check(module) -> dict[str, int | str]:
    """Drive the real Amaranth state machine against a source-backed oracle."""
    dut = module.InstrMMIOEntry(module.InstrMMIOEntryConfig())
    stimulus = vectors()
    checks = 0
    model = {"state": 0, "addr": 0, "data": 0, "corrupt": 0, "need_flush": 0}

    def expected_outputs() -> dict[str, int]:
        state = model["state"]
        addr = model["addr"]
        data = model["data"]
        lane = (addr >> 1) & 0x3
        words = (data & 0xFFFFFFFF, (data >> 16) & 0xFFFFFFFF,
                 (data >> 32) & 0xFFFFFFFF, (data >> 48) & 0xFFFF)
        return {
            "req_ready": int(state == 0),
            "acquire_valid": int(state == 1 and not model["wfi_req"]),
            "acquire_address": addr & ~0x7,
            "resp_valid": int(state == 3 and not model["need_flush"]),
            "resp_data": words[lane],
            "resp_corrupt": model["corrupt"],
            "wfi_safe": int(state != 2),
        }

    def update_model(event: tuple[int, int, int, int, int, int, int, int]) -> None:
        req_valid, req_addr, req_flush, acquire_ready, grant_valid, grant_data, grant_corrupt, wfi_req = event
        state = model["state"]
        model["wfi_req"] = wfi_req
        req_fire = bool(req_valid and state == 0)
        acquire_fire = bool(state == 1 and not wfi_req and acquire_ready)
        grant_fire = bool(state == 2 and grant_valid)
        if req_fire:
            model["addr"] = req_addr
        if grant_fire:
            model["data"] = grant_data
            model["corrupt"] = grant_corrupt
        if state == 3:
            model["state"] = 0
        elif grant_fire:
            model["state"] = 3
        elif acquire_fire:
            model["state"] = 2
        elif req_fire:
            model["state"] = 1
        model["need_flush"] = int(
            (req_flush and state not in (0, 3))
            or (model["need_flush"] and state != 3)
        )

    async def bench(ctx) -> None:
        nonlocal checks
        ctx.set(dut.reset, 1)
        ctx.set(dut.req_valid, 0)
        ctx.set(dut.req_flush, 0)
        ctx.set(dut.mmio_acquire_ready, 0)
        ctx.set(dut.mmio_grant_valid, 0)
        ctx.set(dut.mmio_grant_data, 0)
        ctx.set(dut.mmio_grant_corrupt, 0)
        ctx.set(dut.wfi_req, 0)
        await ctx.tick()
        await ctx.tick()
        ctx.set(dut.reset, 0)
        model.update({"state": 0, "addr": 0, "data": 0, "corrupt": 0, "need_flush": 0})
        model["wfi_req"] = 0
        for event in stimulus:
            req_valid, req_addr, req_flush, acquire_ready, grant_valid, grant_data, grant_corrupt, wfi_req = event
            ctx.set(dut.req_valid, req_valid)
            ctx.set(dut.req_addr, req_addr)
            ctx.set(dut.req_flush, req_flush)
            ctx.set(dut.mmio_acquire_ready, acquire_ready)
            ctx.set(dut.mmio_grant_valid, grant_valid)
            ctx.set(dut.mmio_grant_data, grant_data)
            ctx.set(dut.mmio_grant_corrupt, grant_corrupt)
            ctx.set(dut.wfi_req, wfi_req)
            model["wfi_req"] = wfi_req
            await ctx.delay(1e-9)
            wanted = expected_outputs()
            observed = {
                "req_ready": int(ctx.get(dut.req_ready)),
                "acquire_valid": int(ctx.get(dut.mmio_acquire_valid)),
                "acquire_address": int(ctx.get(dut.mmio_acquire_address)),
                "resp_valid": int(ctx.get(dut.resp_valid)),
                "resp_data": int(ctx.get(dut.resp_data)),
                "resp_corrupt": int(ctx.get(dut.resp_corrupt)),
                "wfi_safe": int(ctx.get(dut.wfi_safe)),
            }
            if observed != wanted:
                raise AssertionError({"event": event, "observed": observed, "expected": wanted, "model": dict(model)})
            checks += len(wanted)
            await ctx.tick()
            update_model(event)

    simulator = Simulator(dut)
    simulator.add_clock(1e-6)
    simulator.add_testbench(bench)
    simulator.run()
    return {"status": "PASS", "cycles": len(stimulus), "checks": checks}


def vectors() -> list[tuple[int, int, int, int, int, int, int, int]]:
    """Produce directed handshake coverage followed by deterministic random cycles."""
    directed = [
        (1, 0x123456789ABC, 0, 1, 0, 0, 0, 0),  # allocate
        (0, 0, 0, 1, 0, 0, 0, 1),               # acquire while WFI blocks
        (0, 0, 0, 1, 1, 0x1122334455667788, 1, 0),
        (0, 0, 0, 0, 0, 0, 0, 0),               # response
        (1, 0x000000000005, 0, 0, 0, 0, 0, 0),
        (0, 0, 1, 1, 0, 0, 0, 0),               # flush in refill request
        (0, 0, 0, 1, 1, 0xFFEEDDCCBBAA0099, 0, 0),
        (0, 0, 0, 0, 0, 0, 0, 0),
    ]
    rng = random.Random(0x1AA10C)
    return directed + [(rng.randrange(2), rng.getrandbits(48), rng.randrange(2),
                         rng.randrange(2), rng.randrange(2), rng.getrandbits(64),
                         rng.randrange(2), rng.randrange(2)) for _ in range(1016)]


def main() -> int:
    target = load(TARGET)
    WORK.mkdir(parents=True, exist_ok=True)
    target_rtl = WORK / "InstrMMIOEntry-target.sv"
    target_rtl.write_text(target.build_verilog(None, None), encoding="utf-8", newline="\n")
    reference_rtl = WORK / "InstrMMIOEntry-reference.sv"
    reference_rtl.write_bytes(extract("InstrMMIOEntry").replace(
        b"module InstrMMIOEntry(", b"module InstrMMIOEntryReference("))

    lines = [
        "module tb;",
        "reg clock=0, reset=1, req_valid, req_flush, acquire_ready, grant_valid, grant_corrupt, wfi_req;",
        "reg [47:0] req_addr; reg [63:0] grant_data;",
        "wire tr,rr,tav,rav,tv,rv,tc,rc,ts,rs; wire [47:0] taa,raa; wire [31:0] td,rd;",
        "always #5 clock = ~clock;",
        "InstrMMIOEntry t(.clock(clock),.reset(reset),.io_req_ready(tr),.io_req_valid(req_valid),.io_req_bits_addr(req_addr),.io_req_bits_flush(req_flush),.io_resp_valid(tv),.io_resp_bits_data(td),.io_resp_bits_corrupt(tc),.io_mmio_acquire_ready(acquire_ready),.io_mmio_acquire_valid(tav),.io_mmio_acquire_bits_address(taa),.io_mmio_grant_valid(grant_valid),.io_mmio_grant_bits_data(grant_data),.io_mmio_grant_bits_corrupt(grant_corrupt),.io_wfi_wfiReq(wfi_req),.io_wfi_wfiSafe(ts));",
        "InstrMMIOEntryReference r(.clock(clock),.reset(reset),.io_req_ready(rr),.io_req_valid(req_valid),.io_req_bits_addr(req_addr),.io_req_bits_flush(req_flush),.io_resp_valid(rv),.io_resp_bits_data(rd),.io_resp_bits_corrupt(rc),.io_mmio_acquire_ready(acquire_ready),.io_mmio_acquire_valid(rav),.io_mmio_acquire_bits_address(raa),.io_mmio_grant_valid(grant_valid),.io_mmio_grant_bits_data(grant_data),.io_mmio_grant_bits_corrupt(grant_corrupt),.io_wfi_wfiReq(wfi_req),.io_wfi_wfiSafe(rs));",
        "integer cycle; initial cycle=0;",
        "task check; begin #1; cycle=cycle+1; if ({tr,tav,tv,tc,ts,taa,td}!={rr,rav,rv,rc,rs,raa,rd}) begin $display(\"MMIO_MISMATCH cycle=%0d t=%b%b%b%b%b %h %h r=%b%b%b%b%b %h %h\",cycle,tr,tav,tv,tc,ts,taa,td,rr,rav,rv,rc,rs,raa,rd); $fatal(1); end end endtask",
        "initial begin req_valid=0; req_addr=0; req_flush=0; acquire_ready=0; grant_valid=0; grant_data=0; grant_corrupt=0; wfi_req=0;",
        "repeat(2) @(posedge clock); check; reset=0;",
    ]
    for req_valid, req_addr, req_flush, acquire_ready, grant_valid, grant_data, grant_corrupt, wfi_req in vectors():
        lines.append(f"@(negedge clock); req_valid=1'b{req_valid}; req_addr=48'h{req_addr:012x}; req_flush=1'b{req_flush}; acquire_ready=1'b{acquire_ready}; grant_valid=1'b{grant_valid}; grant_data=64'h{grant_data:016x}; grant_corrupt=1'b{grant_corrupt}; wfi_req=1'b{wfi_req}; @(posedge clock); check;")
    lines += [' $display("FRONTEND_INSTR_MMIO_ENTRY_DIFF_PASS 1024"); $finish; end endmodule']
    tb = WORK / "instr-mmio-entry-child-tb.sv"
    tb.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    obj = WORK / "obj"
    compile_result = run_wsl(["verilator", "--binary", "--timing", "-Wno-fatal", "--top-module", "tb", "--Mdir", wsl_path(obj), wsl_path(target_rtl), wsl_path(reference_rtl), wsl_path(tb)])
    run = run_wsl([wsl_path(obj / "Vtb")]) if compile_result["returncode"] == 0 else {"status": "SKIP", "returncode": 1}
    verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal", wsl_path(target_rtl)])
    yosys = run_wsl(["yosys", "-Q", "-p", f"read_verilog -sv {wsl_path(target_rtl)}; hierarchy -top InstrMMIOEntry; proc; check; stat"])
    passed = compile_result["returncode"] == 0 and run.get("returncode") == 0 and "FRONTEND_INSTR_MMIO_ENTRY_DIFF_PASS" in str(run.get("output_tail", ""))
    locked_ok = LOCKED.is_file() and LOCKED.stat().st_size == 228590583 and digest(LOCKED.read_bytes()) == LOCKED_SHA256
    direct = direct_model_check(target)
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_FRONTEND_INSTR_MMIO_ENTRY_CHILD_DIFFERENTIAL",
        "source_commit": SOURCE_COMMIT,
        "targets": {"InstrMMIOEntry": str(TARGET.relative_to(ROOT)).replace("\\", "/")},
        "locked_reference": {"canonical_path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv", "xstop_sha256": LOCKED_SHA256, "immutable": locked_ok, "modules": ["InstrMMIOEntry"]},
        "direct": direct,
        "differential": {"status": "PASS" if passed else "FAIL", "vectors": 1024, "compile": compile_result, "run": run},
        "tool_gates": {"verilator": verilator, "yosys": yosys},
        "gates": {"DIRECT_TEST_PASS_BOUNDED": direct["status"], "V2_REFERENCE_MATCHED": "PASS_BOUNDED" if passed else "FAIL", "VERILATOR": verilator["status"], "YOSYS": yosys["status"], "PARENT_CLOSURE_MATCHED": "PENDING", "ACCEPTED": "NOT_ALLOWED"},
        "status": "PASS_BOUNDED_INSTR_MMIO_ENTRY_CHILD" if passed and locked_ok else "FAIL",
        "acceptance_eligible": False,
        "unclosed": ["InstrUncache/Frontend parent integration remains pending.", "License review and user approval remain pending."],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "vectors": 1024, "ACCEPTED": "NOT_ALLOWED"}, sort_keys=True))
    return 0 if payload["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
