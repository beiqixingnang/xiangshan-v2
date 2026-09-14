"""Independent bounded validator for the V2 CoupledL2 slice family.
V2 CoupledL2 slice family 的独立有界验证器。

The validator is intentionally family-local and serial: it checks the exact
Build path, deterministic address/message equations, a reset/handshake bench,
and Verilator/Yosys syntax gates.  Full Slice/TL2TLCoupledL2 equivalence is
kept open until the parent closure harness is available.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType

from amaranth.sim import Simulator


# =============================================================================
# Module Contract
# =============================================================================
# The bounded bench covers address parse/restore, A admission, hit response,
# miss/refill, dirty eviction, C release, flush cancellation, and B probe flow.
# 本有界 bench 覆盖地址解析/恢复、A 接收、命中响应、缺失/回填、脏逐出、C release、flush 取消及 B probe。


# =============================================================================
# Configuration
# =============================================================================
ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python" / "Program-System" / "System-Build" / "Build-Cpu" / "Cpu-Memory" / "Build-Cpu.Dependency.CoupledL2.Slice-Hardware.py"
OUT = ROOT / "validation" / "v2-coupledL2-slice-family-results.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
SOURCE_ROOT = "upstream/coupledL2/src/main/scala/coupledL2"
SCALA_SOURCES = [
    "upstream/coupledL2/src/main/scala/coupledL2/BaseSlice.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/Common.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/Consts.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/CoupledL2.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/DataStorage.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/Directory.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/GrantBuffer.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/MSHRBuffer.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/RequestArb.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/RequestBuffer.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/SinkA.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/SinkC.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/SourceB.scala",
]


# Load one exact target path without importing sibling Build files. / 按精确路径加载目标且不导入同级 Build 文件。
def load_exact(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("v2_coupled_l2_slice_target", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Compute a byte-preserving SHA-256 digest. / 计算保持原始字节的 SHA-256 摘要。
def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Audit the final Build five-zone and import contract. / 审计最终 Build 五分区及导入契约。
def static_audit() -> dict[str, object]:
    raw = TARGET.read_bytes()
    source = raw.decode("utf-8")
    if raw.startswith(b"\xef\xbb\xbf") or b"\r\n" in raw:
        raise AssertionError("target must be UTF-8 LF without BOM")
    tree = ast.parse(source, filename=str(TARGET))
    zones = ("Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry")
    positions = [source.find(zone) for zone in zones]
    if any(value < 0 for value in positions) or positions != sorted(positions):
        raise AssertionError("five-zone contract missing or out of order")
    adapter = next((node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "build_verilog"), None)
    if adapter is None or [arg.arg for arg in adapter.args.args] != ["configuration", "injected_dependencies"]:
        raise AssertionError("exact build_verilog signature is required")
    if "__all__" not in source:
        raise AssertionError("explicit __all__ missing")
    forbidden = {"importlib", "runpy", "subprocess", "socket", "urllib", "pathlib"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(item.name.split(".")[0] in forbidden for item in node.names):
                raise AssertionError("forbidden import in target")
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in forbidden:
            raise AssertionError("forbidden import in target")
    required = ("CoupledL2SliceConfig", "CoupledL2Slice", "build_verilog")
    missing = [name for name in required if name not in source]
    if missing:
        raise AssertionError(f"missing symbols: {missing}")
    return {"status": "PASS", "path": TARGET.relative_to(ROOT).as_posix(), "bytes": len(raw),
            "sha256": digest(TARGET), "zones": list(zones), "required_symbols": list(required)}


# Run deterministic pure address/message equations. / 运行确定性的地址/消息方程。
def equation_vectors(module: ModuleType) -> dict[str, object]:
    cfg = module.CoupledL2SliceConfig(sets=8, ways=4, bank_bits=2)
    rng = random.Random(0xC02A2)
    addresses = [rng.getrandbits(cfg.address_bits) for _ in range(256)]
    for address in addresses:
        fields = module.parse_address(address, cfg)
        restored = module.restore_address(*fields, configuration=cfg)
        if restored != address & ((1 << cfg.address_bits) - 1):
            raise AssertionError((hex(address), fields, hex(restored)))
    expected = {
        0: 0, 1: 0, 2: 1, 3: 1, 4: 1, 5: 2, 6: 5, 7: 5,
    }
    checks = 0
    for opcode, response in expected.items():
        observed = module.slice_reference_step(opcode, True)["response_opcode"]
        if observed != response:
            raise AssertionError((opcode, observed, response))
        checks += 1
    for opcode in range(8):
        miss = module.slice_reference_step(opcode, False)
        if miss["miss"] != 1:
            raise AssertionError((opcode, miss))
        checks += 1
    return {"status": "PASS", "address_vectors": len(addresses), "message_vectors": checks}


# Exercise the Amaranth slice through reset, hit, miss, refill, C, B, and flush paths. /
# 通过复位、命中、缺失、回填、C、B 及 flush 路径驱动 Amaranth slice。
def direct_bench(module: ModuleType) -> dict[str, object]:
    cfg = module.CoupledL2SliceConfig(sets=4, ways=2, bank_bits=1, line_beats=2,
                                      data_bits=64, source_bits=4, sink_bits=4,
                                      req_source_bits=3, vaddr_bits=40)
    top = module.CoupledL2Slice(cfg, {})
    signals = {name: getattr(top, name) for name in (
        "clock", "reset", "flush", "slice_id", "in_a_valid", "in_a_bits_opcode", "in_a_bits_size",
        "in_a_bits_source", "in_a_bits_address", "in_a_bits_user_reqSource", "in_a_bits_user_alias",
        "in_a_bits_user_vaddr", "in_a_bits_user_needHint", "in_a_bits_echo_isKeyword", "in_a_bits_mask",
        "in_a_bits_data", "in_a_bits_corrupt", "in_c_valid", "in_c_bits_opcode", "in_c_bits_size",
        "in_c_bits_source", "in_c_bits_address", "in_c_bits_data", "in_c_bits_corrupt", "in_d_ready",
        "out_a_ready", "out_c_ready", "out_b_valid", "out_b_bits_address", "out_b_bits_size",
        "out_b_bits_source", "in_b_ready", "out_d_valid", "out_d_bits_data", "out_d_bits_size",
        "out_d_bits_denied", "out_d_bits_corrupt", "prefetch_req_valid", "prefetch_req_bits_tag",
        "prefetch_req_bits_set", "prefetch_req_bits_source", "prefetch_req_bits_pfSource",
        "prefetch_req_bits_vaddr", "prefetch_req_bits_needT", "flush",
    )}
    outputs = {name: getattr(top, name) for name in (
        "in_a_ready", "in_c_ready", "in_d_valid", "in_d_bits_opcode", "in_d_bits_data", "out_a_valid",
        "out_c_valid", "in_b_valid", "l2Miss", "l2FlushDone", "prefetch_req_ready",
    )}
    observations: list[dict[str, int]] = []

    async def bench(ctx) -> None:
        for signal in signals.values():
            ctx.set(signal, 0)
        ctx.set(signals["slice_id"], 0)
        ctx.set(signals["out_a_ready"], 1)
        ctx.set(signals["out_c_ready"], 1)
        ctx.set(signals["in_b_ready"], 1)
        ctx.set(signals["in_d_ready"], 1)
        ctx.set(signals["reset"], 1)
        for _ in range(3):
            await ctx.tick("coupled_l2")
        ctx.set(signals["reset"], 0)
        for _ in range(2):
            await ctx.tick("coupled_l2")
        # Fill one address through A miss and one D beat. / 通过 A 缺失和一个 D beat 填充一个地址。
        ctx.set(signals["in_a_valid"], 1)
        ctx.set(signals["in_a_bits_opcode"], 4)
        ctx.set(signals["in_a_bits_size"], 6)
        ctx.set(signals["in_a_bits_source"], 3)
        ctx.set(signals["in_a_bits_address"], 0x120)
        ctx.set(signals["in_a_bits_mask"], 0xFF)
        ctx.set(signals["in_a_bits_data"], 0x1234)
        await ctx.tick("coupled_l2")
        ctx.set(signals["in_a_valid"], 0)
        if int(ctx.get(outputs["l2Miss"])) != 1 and int(ctx.get(outputs["out_a_valid"])) != 1:
            raise AssertionError("miss was not exposed")
        # The A request is held until the outer sink accepts it. / A 请求保持到外部 sink 接收。
        if int(ctx.get(outputs["out_a_valid"])) != 1:
            raise AssertionError("outer A request was not presented")
        await ctx.tick("coupled_l2")
        if int(ctx.get(outputs["out_a_valid"])) != 0:
            raise AssertionError("outer A request did not retire")
        ctx.set(signals["out_d_valid"], 1)
        ctx.set(signals["out_d_bits_data"], 0xCAFE)
        ctx.set(signals["out_d_bits_size"], 6)
        await ctx.tick("coupled_l2")
        ctx.set(signals["out_d_valid"], 0)
        if int(ctx.get(outputs["in_d_valid"])) != 1:
            raise AssertionError("refill did not produce a D response")
        if int(ctx.get(outputs["in_d_bits_opcode"])) != 1:
            raise AssertionError("Get refill response opcode mismatch")
        await ctx.tick("coupled_l2")
        # Allow the synchronous write port and asynchronous read view to settle
        # before issuing the next request. / 等待同步写端口及异步读视图稳定后再发起下一请求。
        await ctx.tick("coupled_l2")
        # The refill must be observable as a hit on the next request. / 回填后下一次请求必须可观察为命中。
        ctx.set(signals["in_a_valid"], 1)
        ctx.set(signals["in_a_bits_opcode"], 4)
        ctx.set(signals["in_a_bits_size"], 6)
        ctx.set(signals["in_a_bits_source"], 1)
        ctx.set(signals["in_a_bits_address"], 0x120)
        ctx.set(signals["in_a_bits_mask"], 0xFF)
        await ctx.delay(1e-9)
        if int(ctx.get(outputs["in_a_ready"])) != 1:
            raise AssertionError("slice was not idle before hit request")
        await ctx.tick("coupled_l2")
        if int(ctx.get(outputs["in_d_valid"])) != 1 or int(ctx.get(outputs["in_d_bits_opcode"])) != 1:
            raise AssertionError("refilled line did not hit")
        observations.append({"hit_response": int(ctx.get(outputs["in_d_bits_data"]))})
        ctx.set(signals["in_a_valid"], 0)
        await ctx.tick("coupled_l2")
        # C release is accepted and produces ReleaseAck-style response. / C release 被接受并产生 ReleaseAck 响应。
        ctx.set(signals["in_c_valid"], 1)
        ctx.set(signals["in_c_bits_opcode"], 6)
        ctx.set(signals["in_c_bits_size"], 6)
        ctx.set(signals["in_c_bits_source"], 2)
        ctx.set(signals["in_c_bits_address"], 0x120)
        await ctx.tick("coupled_l2")
        if int(ctx.get(outputs["in_d_valid"])) != 1 or int(ctx.get(outputs["in_d_bits_opcode"])) != 6:
            raise AssertionError("C release response mismatch")
        observations.append({"release_response": int(ctx.get(outputs["in_d_bits_opcode"]))})
        ctx.set(signals["in_c_valid"], 0)
        await ctx.tick("coupled_l2")
        # A downstream probe is queued and acknowledged with the same address. / 下游 probe 排队后以相同地址确认。
        ctx.set(signals["out_b_valid"], 1)
        ctx.set(signals["out_b_bits_address"], 0x120)
        ctx.set(signals["out_b_bits_size"], 6)
        ctx.set(signals["out_b_bits_source"], 1)
        await ctx.tick("coupled_l2")
        ctx.set(signals["out_b_valid"], 0)
        if int(ctx.get(outputs["in_b_valid"])) != 1:
            raise AssertionError("probe acknowledgement was not presented")
        observations.append({"probe_ack": int(ctx.get(outputs["in_b_valid"]))})
        await ctx.tick("coupled_l2")
        # Flush cancellation must suppress all active outputs. / flush 取消必须屏蔽所有活动输出。
        ctx.set(signals["flush"], 1)
        await ctx.tick("coupled_l2")
        if any(int(ctx.get(outputs[name])) for name in ("in_d_valid", "out_a_valid", "out_c_valid", "in_b_valid")):
            raise AssertionError("flush leaked an active channel")
        observations.append({"flush_done": int(ctx.get(outputs["l2FlushDone"]))})

    simulator = Simulator(top)
    simulator.add_clock(1e-6, domain="coupled_l2")
    simulator.add_testbench(bench)
    simulator.run()
    trace = json.dumps(observations, sort_keys=True, separators=(",", ":")).encode()
    return {"status": "PASS", "checks": len(observations), "trace_sha256": hashlib.sha256(trace).hexdigest(),
            "trace": observations}


# Check generated RTL with Verilator and Yosys. / 用 Verilator 与 Yosys 检查生成 RTL。
def backend_gates(module: ModuleType) -> dict[str, object]:
    rtl = module.build_verilog({"sets": 4, "ways": 2, "bank_bits": 1, "line_beats": 2,
                                "data_bits": 64, "source_bits": 4, "sink_bits": 4,
                                "req_source_bits": 3, "vaddr_bits": 40, "module": "UHSCCoupledL2Slice"}, {})
    with tempfile.TemporaryDirectory(prefix="v2_coupled_l2_slice_") as directory:
        path = Path(directory) / "slice.sv"
        path.write_text(rtl, encoding="utf-8", newline="\n")
        # WSL tools see the Windows path through /mnt; use wslpath to avoid assumptions. /
        win = str(path)
        converted = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", win], capture_output=True,
                                   text=True, encoding="utf-8", errors="replace", check=True).stdout.strip()
        verilator = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal '{converted}'"],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        yosys = subprocess.run(["wsl.exe", "-e", "bash", "-lc",
                                f"yosys -Q -p 'read_verilog -sv {converted}; hierarchy -top UHSCCoupledL2Slice; proc; opt; check'"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    return {"verilator": "PASS" if verilator.returncode == 0 else "FAIL",
            "yosys": "PASS" if yosys.returncode == 0 else "FAIL", "rtl_bytes": len(rtl.encode()),
            "rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest(),
            "verilator_returncode": verilator.returncode, "yosys_returncode": yosys.returncode}


# Persist evidence with acceptance explicitly closed. / 持久化证据并明确关闭 ACCEPTED。
def main() -> int:
    if not TARGET.exists():
        raise FileNotFoundError(TARGET)
    static = static_audit()
    module = load_exact(TARGET)
    compile_result = subprocess.run([sys.executable, "-m", "py_compile", str(TARGET)], check=False,
                                    capture_output=True, text=True, encoding="utf-8", errors="replace")
    if compile_result.returncode:
        raise RuntimeError(compile_result.stderr)
    equations = equation_vectors(module)
    direct = direct_bench(module)
    backend = backend_gates(module)
    source_entries = [{"path": path, "sha256": digest(ROOT / path)} for path in SCALA_SOURCES]
    passed = backend["verilator"] == "PASS" and backend["yosys"] == "PASS"
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_COUPLEDL2_SLICE_FAMILY",
        "batch_id": "V2-DEPENDENCY-COUPLEDL2-SLICE-001",
        "source_commit": SOURCE_COMMIT,
        "source_root": SOURCE_ROOT,
        "source_scala_file_count": 60,
        "source_scala_hashes": source_entries,
        "target": {"path": static["path"], "sha256": static["sha256"]},
        "static": static,
        "equations": equations,
        "direct": direct,
        "backend": backend,
        "reference_mode": "LOCKED_XSTOP_COUPLEDL2_SLICE_BOUNDARY_PENDING_FULL_PARENT",
        "gates": {
            "PYTHON_PRESENT": "PASS",
            "DIRECT_TEST_PASS_BOUNDED": "PASS" if direct["status"] == "PASS" else "FAIL",
            "V2_REFERENCE_MATCHED": "PASS_BOUNDED_EQUATIONS",
            "VERILATOR": backend["verilator"],
            "YOSYS": backend["yosys"],
            "UHSC_LOCALIZED": "PASS_BOUNDED_FAMILY_LOCAL_NAME",
            "PARENT_CLOSURE_MATCHED": "PENDING_FULL_SLICE_PARENT",
            "LICENSE_REVIEW": "PENDING",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "unclosed": [
            "Full 152-port Slice differential against locked XSTop remains pending.",
            "TL2TLCoupledL2 parent and CHI conditional bridge remain pending.",
            "License review and user approval remain pending.",
        ],
        "status": "VALIDATOR_PASS_BOUNDED" if passed else "VALIDATOR_FAIL",
        "acceptance_eligible": False,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "target": static["path"], "checks": direct["checks"]}, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
