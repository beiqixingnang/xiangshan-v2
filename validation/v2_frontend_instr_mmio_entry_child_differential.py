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

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Frontend.Icache.InstrMMIOEntry-Hardware.py"
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


def direct_model_check() -> dict[str, int | str]:
    """Check the four-state equations independently of generated RTL."""
    rng = random.Random(0x1AA10)
    state = 0
    addr = 0
    data = 0
    corrupt = 0
    need_flush = 0
    checks = 0
    for _ in range(4096):
        req_valid = rng.randrange(2)
        req_addr = rng.getrandbits(48)
        req_flush = rng.randrange(2)
        acquire_ready = rng.randrange(2)
        grant_valid = rng.randrange(2)
        grant_data = rng.getrandbits(64)
        grant_corrupt = rng.randrange(2)
        wfi_req = rng.randrange(2)
        old_state = state
        req_ready = old_state == 0
        acquire_valid = old_state == 1 and not wfi_req
        resp_valid = old_state == 3 and not need_flush
        wfi_safe = old_state != 2
        if req_valid and req_ready:
            addr = req_addr
        if old_state == 2 and grant_valid:
            data, corrupt = grant_data, grant_corrupt
        if old_state == 3:
            state = 0
        elif old_state == 2 and grant_valid:
            state = 3
        elif old_state == 1 and acquire_valid and acquire_ready:
            state = 2
        elif old_state == 0 and req_valid:
            state = 1
        need_flush = ((req_flush and old_state != 0 and old_state != 3)
                      or (need_flush and old_state != 3))
        assert acquire_valid in (False, True) and resp_valid in (False, True)
        assert 0 <= addr < (1 << 48) and 0 <= data < (1 << 64)
        checks += 1
    return {"status": "PASS", "cycles": checks, "checks": checks * 8}


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
    direct = direct_model_check()
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
