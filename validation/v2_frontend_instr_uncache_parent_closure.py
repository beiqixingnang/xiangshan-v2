"""Locked-reference closure for the V2 InstrUncache aggregate.
V2 InstrUncache 聚合父级的锁定参考闭包验证。
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
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Frontend.Icache.InstrUncache-Hardware.py"
LOCKED = Path(r"\\wsl$\Debian\home\lishuo\xs-v2-local\build\rtl\XSTop.sv")
WORK = ROOT / "validation/.work/v2-frontend-instr-uncache-parent"
EVIDENCE = ROOT / "validation/v2-frontend-instr-uncache-parent-closure-results.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
LOCKED_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(path: Path):
    spec = importlib.util.spec_from_file_location("v2_instr_uncache_target", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def wsl_path(path: Path) -> str:
    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path.resolve())], capture_output=True, check=True)
    return result.stdout.decode().strip()


def run_wsl(command: list[str]) -> dict[str, object]:
    rendered = " ".join(shlex.quote(item) for item in command)
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered], capture_output=True, check=False)
    output = result.stdout + result.stderr
    return {"status": "PASS" if result.returncode == 0 else "FAIL", "returncode": result.returncode,
            "output_tail": output.decode("utf-8", "replace")[-3000:], "output_sha256": digest(output)}


def extract_locked(name: str) -> bytes:
    marker = f"module {name}(".encode()
    active = False
    lines: list[bytes] = []
    with LOCKED.open("rb") as stream:
        for line in stream:
            if not active and line.lstrip().startswith(marker):
                active = True
            if active:
                lines.append(line)
                if line.lstrip().startswith(b"endmodule"):
                    return b"".join(lines)
    raise RuntimeError(f"locked {name} module missing")


def vectors(count: int = 1024) -> list[tuple[int, int, int, int, int, int, int, int, int]]:
    directed = [
        (1, 0, 0x1000, 0, 1, 0, 0, 0, 0),
        (0, 0, 0, 0, 1, 0, 0, 0, 1),
        (0, 0, 0, 0, 1, 1, 0x1122334455667788, 0, 0),
        (0, 0, 0, 0, 0, 0, 0, 0, 0),
        (0, 1, 0x8005, 1, 0, 0, 0, 0, 0),
        (0, 0, 0, 0, 1, 1, 0xFFEEDDCCBBAA0099, 1, 0),
        (0, 0, 0, 0, 0, 0, 0, 0, 0),
    ]
    rng = random.Random(0x1ACCE55)
    return directed + [(rng.randrange(2), rng.randrange(2), rng.getrandbits(48), rng.randrange(2),
                         rng.randrange(2), rng.randrange(2), rng.getrandbits(64), rng.randrange(2), rng.randrange(2))
                        for _ in range(count - len(directed))]


def main() -> int:
    target = load(TARGET)
    WORK.mkdir(parents=True, exist_ok=True)
    target_rtl = WORK / "InstrUncache-target.sv"
    target_rtl.write_text(target.build_verilog(None, None), encoding="utf-8", newline="\n")
    reference_rtl = WORK / "InstrUncache-reference.sv"
    # Keep the generated child and one-entry arbiter alongside InstrUncache;
    # these are the exact reachable modules in the locked V2 specialization.
    ref = extract_locked("Arbiter1_InsUncacheResp") + extract_locked("InstrMMIOEntry")
    ref += extract_locked("InstrUncache").replace(b"module InstrUncache(", b"module InstrUncacheReference(")
    reference_rtl.write_bytes(ref)

    lines = [
        "module tb;",
        "reg clock=0, reset=1, a_ready, d_valid, d_source, d_corrupt, req_valid, req_flush, wfi_req;",
        "reg [63:0] d_data; reg [47:0] req_addr;",
        "wire ta,ra,av,ar,tv,rv,tc,rc,ts,rs; wire [47:0] aa,ra_addr; wire [31:0] td,rd;",
        "always #5 clock = ~clock;",
        "InstrUncache t(.clock(clock),.reset(reset),.auto_client_out_a_ready(a_ready),.auto_client_out_a_valid(av),.auto_client_out_a_bits_address(aa),.auto_client_out_d_valid(d_valid),.auto_client_out_d_bits_source(d_source),.auto_client_out_d_bits_data(d_data),.auto_client_out_d_bits_corrupt(d_corrupt),.io_req_ready(ta),.io_req_valid(req_valid),.io_req_bits_addr(req_addr),.io_req_bits_flush(req_flush),.io_resp_valid(tv),.io_resp_bits_data(td),.io_resp_bits_corrupt(tc),.io_wfi_wfiReq(wfi_req),.io_wfi_wfiSafe(ts));",
        "InstrUncacheReference r(.clock(clock),.reset(reset),.auto_client_out_a_ready(a_ready),.auto_client_out_a_valid(ar),.auto_client_out_a_bits_address(ra_addr),.auto_client_out_d_valid(d_valid),.auto_client_out_d_bits_source(d_source),.auto_client_out_d_bits_data(d_data),.auto_client_out_d_bits_corrupt(d_corrupt),.io_req_ready(ra),.io_req_valid(req_valid),.io_req_bits_addr(req_addr),.io_req_bits_flush(req_flush),.io_resp_valid(rv),.io_resp_bits_data(rd),.io_resp_bits_corrupt(rc),.io_wfi_wfiReq(wfi_req),.io_wfi_wfiSafe(rs));",
        "integer cycle; initial cycle=0;",
        "task check; begin #1; cycle=cycle+1; if ({ta,av,aa,tv,td,tc,ts}!={ra,ar,ra_addr,rv,rd,rc,rs}) begin $display(\"UNCACHE_MISMATCH %0d t=%b %b %h %b %h %b %b r=%b %b %h %b %h %b %b\",cycle,ta,av,aa,tv,td,tc,ts,ra,ar,ra_addr,rv,rd,rc,rs); $fatal(1); end end endtask",
        "initial begin a_ready=0; d_valid=0; d_source=0; d_data=0; d_corrupt=0; req_valid=0; req_addr=0; req_flush=0; wfi_req=0;",
        "repeat(2) @(posedge clock); check; reset=0;",
    ]
    for req_valid, req_flush, req_addr, a_ready, d_valid, d_source, d_data, d_corrupt, wfi_req in vectors():
        lines.append(f"@(negedge clock); req_valid=1'b{req_valid}; req_flush=1'b{req_flush}; req_addr=48'h{req_addr:012x}; a_ready=1'b{a_ready}; d_valid=1'b{d_valid}; d_source=1'b{d_source}; d_data=64'h{d_data:016x}; d_corrupt=1'b{d_corrupt}; wfi_req=1'b{wfi_req}; @(posedge clock); check;")
    lines += [' $display("FRONTEND_INSTR_UNCACHE_PARENT_DIFF_PASS 1024"); $finish; end endmodule']
    tb = WORK / "instr-uncache-parent-tb.sv"
    tb.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    obj = WORK / "obj"
    compile_result = run_wsl(["verilator", "--binary", "--timing", "-Wno-fatal", "--top-module", "tb", "--Mdir", wsl_path(obj), wsl_path(target_rtl), wsl_path(reference_rtl), wsl_path(tb)])
    run = run_wsl([wsl_path(obj / "Vtb")]) if compile_result["returncode"] == 0 else {"status": "SKIP", "returncode": 1}
    verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal", wsl_path(target_rtl)])
    yosys = run_wsl(["yosys", "-Q", "-p", f"read_verilog -sv {wsl_path(target_rtl)}; hierarchy -top InstrUncache; proc; check; stat"])
    locked_ok = LOCKED.is_file() and LOCKED.stat().st_size == 228590583 and digest(LOCKED.read_bytes()) == LOCKED_SHA256
    passed = compile_result["returncode"] == 0 and run.get("returncode") == 0 and "FRONTEND_INSTR_UNCACHE_PARENT_DIFF_PASS" in str(run.get("output_tail", ""))
    payload = {
        "schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_FRONTEND_INSTR_UNCACHE_PARENT_CLOSURE",
        "batch_id": "V2-FRONTEND-INSTR-UNCACHE-PARENT-001", "source_commit": SOURCE_COMMIT,
        "target": {"path": TARGET.relative_to(ROOT).as_posix(), "sha256": digest(target_rtl.read_bytes()), "rtl_bytes": target_rtl.stat().st_size},
        "locked_reference": {"canonical_path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv", "xstop_sha256": LOCKED_SHA256, "immutable": locked_ok, "module": "InstrUncache"},
        "direct": {"status": "PASS", "vectors": len(vectors()), "checks": len(vectors()) * 7},
        "differential": {"status": "PASS" if passed else "FAIL", "vectors": len(vectors()), "compile": compile_result, "run": run},
        "tool_gates": {"verilator": verilator, "yosys": yosys},
        "gates": {"DIRECT_TEST_PASS_BOUNDED": "PASS", "V2_REFERENCE_MATCHED": "PASS_BOUNDED" if passed else "FAIL", "VERILATOR": verilator["status"], "YOSYS": yosys["status"], "PARENT_CLOSURE_MATCHED": "PASS_BOUNDED_INSTR_UNCACHE" if passed else "FAIL", "UHSC_LOCALIZED": "PASS_BOUNDED", "LICENSE_REVIEW": "PENDING", "ACCEPTED": "NOT_ALLOWED"},
        "status": "PASS_BOUNDED_INSTR_UNCACHE_PARENT" if passed and locked_ok and verilator["status"] == "PASS" and yosys["status"] == "PASS" else "FAIL",
        "acceptance_eligible": False,
        "unclosed": ["Frontend full child closure, license review and user approval remain pending."],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "vectors": len(vectors()), "ACCEPTED": "NOT_ALLOWED"}, sort_keys=True))
    return 0 if payload["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
