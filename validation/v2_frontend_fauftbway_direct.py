"""Bounded direct checks for the V2 FauFTBWay child closure.
V2 FauFTBWay 子闭包的有界 direct 检查。
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from amaranth.sim import Settle, Simulator, Tick


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Frontend.Bpu.FauFTBWay-Hardware.py"
SOURCE = ROOT / "upstream/src/main/scala/xiangshan/frontend/FauFTB.scala"
RESULT = ROOT / "validation/v2-frontend-fauftbway-direct-results.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"


# Load one exact Build path without package imports. / 不通过包导入加载精确 Build 路径。
def load_target() -> Any:
    """Load FauFTBWay target. / 加载 FauFTBWay 目标。"""

    spec = importlib.util.spec_from_file_location("v2_fauftbway_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Return a stable SHA-256 digest. / 返回稳定的 SHA-256 摘要。
def digest_bytes(payload: bytes) -> str:
    """Hash raw bytes. / 计算原始字节摘要。"""

    return hashlib.sha256(payload).hexdigest()


# Audit the target's five-zone and function-comment contract.
# 审计目标的五区及函数注释契约。
def audit_target(path: Path) -> dict[str, Any]:
    """Validate source formatting and adapter shape. / 校验源格式与适配器形状。"""

    raw = path.read_bytes()
    text = raw.decode("utf-8")
    tree = ast.parse(text, filename=str(path))
    zones = ("Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry")
    positions = [text.find(zone) for zone in zones]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise AssertionError("five-zone order mismatch")
    if "__all__" not in text:
        raise AssertionError("missing __all__")
    for forbidden in ("importlib", "runpy", "subprocess", "socket", "urllib"):
        if f"import {forbidden}" in text or f"from {forbidden}" in text:
            raise AssertionError(f"forbidden import: {forbidden}")
    lines = text.splitlines()
    functions: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
            if node.name.startswith("_") and not (node.name.startswith("__") and node.name.endswith("__")):
                raise AssertionError(f"leading underscore helper: {node.name}")
            prior = lines[node.lineno - 2].strip() if node.lineno >= 2 else ""
            if not prior.startswith("#") or "/" not in prior:
                raise AssertionError(f"missing bilingual comment: {node.name}")
    adapters = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "build_verilog"]
    if len(adapters) != 1 or [arg.arg for arg in adapters[0].args.args] != ["configuration", "injected_dependencies"]:
        raise AssertionError("adapter signature mismatch")
    return {"utf8": True, "bom": raw.startswith(b"\xef\xbb\xbf"), "lf_only": b"\r" not in raw, "ast_parse": True, "zones": list(zones), "functions": sorted(functions), "bytes": len(raw), "sha256": digest_bytes(raw)}


# Build deterministic entry payloads for direct cycle checks.
# 构造 direct 周期检查所需的确定性条目载荷。
def make_events() -> list[dict[str, int]]:
    """Return 96 write/read vectors. / 返回 96 个写入/读取向量。"""

    rows: list[dict[str, int]] = []
    state = 0x5A17C0DE
    for cycle in range(96):
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= state >> 17
        state ^= (state << 5) & 0xFFFFFFFF
        payload = ((state << 32) | (state ^ 0x9E3779B9)) & ((1 << 64) - 1)
        rows.append({
            "req_tag": (state >> 3) & 0xFFFF,
            "update_tag": (state >> 11) & 0xFFFF,
            "write_valid": int((state >> 28) & 3 != 0),
            "write_tag": (state >> 17) & 0xFFFF,
            "payload": payload,
        })
    rows[:4] = [
        {"req_tag": 0, "update_tag": 0x1234, "write_valid": 1, "write_tag": 0x1234, "payload": 0x0123456789ABCDEF},
        {"req_tag": 0x1234, "update_tag": 0x1234, "write_valid": 0, "write_tag": 0, "payload": 0},
        {"req_tag": 0x7777, "update_tag": 0x7777, "write_valid": 1, "write_tag": 0x7777, "payload": 0x0FEDCBA987654321},
        {"req_tag": 0x1234, "update_tag": 0x7777, "write_valid": 1, "write_tag": 0x7777, "payload": 0x1111222233334444},
    ]
    return rows


# Return all packed FauFTB entry fields from one 64-bit payload.
# 从一个 64 位载荷返回全部打包 FauFTB 条目字段。
def entry_values(payload: int) -> dict[str, int]:
    """Decode V2 entry fields. / 解码 V2 条目字段。"""

    return {
        "is_call": (payload >> 0) & 1,
        "is_ret": (payload >> 1) & 1,
        "is_jalr": (payload >> 2) & 1,
        "valid": (payload >> 3) & 1,
        "br_offset": (payload >> 4) & 0xF,
        "br_sharing": (payload >> 8) & 1,
        "br_valid": (payload >> 9) & 1,
        "br_lower": (payload >> 10) & 0xFFF,
        "br_tar_stat": (payload >> 22) & 3,
        "tail_offset": (payload >> 24) & 0xF,
        "tail_sharing": (payload >> 28) & 1,
        "tail_valid": (payload >> 29) & 1,
        "tail_lower": (payload >> 30) & 0xFFFFF,
        "tail_tar_stat": (payload >> 50) & 3,
        "pft_addr": (payload >> 52) & 0xF,
        "carry": (payload >> 56) & 1,
        "last_rvi_call": (payload >> 57) & 1,
        "strong_bias_0": (payload >> 58) & 1,
        "strong_bias_1": (payload >> 59) & 1,
    }


# Read all response fields as a packed dictionary.
# 将全部响应字段读取为打包字典。
def read_response(ctx: Any, dut: Any) -> dict[str, int]:
    """Return response observations. / 返回响应观测。"""

    return {
        "is_call": int(ctx.get(dut.resp_is_call)),
        "is_ret": int(ctx.get(dut.resp_is_ret)),
        "is_jalr": int(ctx.get(dut.resp_is_jalr)),
        "valid": int(ctx.get(dut.resp_valid)),
        "br_offset": int(ctx.get(dut.resp_br_offset)),
        "br_sharing": int(ctx.get(dut.resp_br_sharing)),
        "br_valid": int(ctx.get(dut.resp_br_valid)),
        "br_lower": int(ctx.get(dut.resp_br_lower)),
        "br_tar_stat": int(ctx.get(dut.resp_br_tar_stat)),
        "tail_offset": int(ctx.get(dut.resp_tail_offset)),
        "tail_sharing": int(ctx.get(dut.resp_tail_sharing)),
        "tail_valid": int(ctx.get(dut.resp_tail_valid)),
        "tail_lower": int(ctx.get(dut.resp_tail_lower)),
        "tail_tar_stat": int(ctx.get(dut.resp_tail_tar_stat)),
        "pft_addr": int(ctx.get(dut.resp_pft_addr)),
        "carry": int(ctx.get(dut.resp_carry)),
        "last_rvi_call": int(ctx.get(dut.resp_last_rvi_call)),
        "strong_bias_0": int(ctx.get(dut.resp_strong_bias_0)),
        "strong_bias_1": int(ctx.get(dut.resp_strong_bias_1)),
    }


# Simulate writes, response reads, and pending-write update bypass.
# 仿真写入、响应读取及待写更新旁路。
def run_registered(module: Any) -> dict[str, Any]:
    """Run the cycle-accurate direct oracle. / 运行逐周期 direct 预言机。"""

    dut = module.FauFTBWay(module.FauFTBWayConfig())
    events = make_events()
    stored: dict[str, int] | None = None
    stored_tag = 0
    stored_valid = False
    observations: list[dict[str, int]] = []

    def bench():
        nonlocal stored, stored_tag, stored_valid
        yield dut.reset.eq(1)
        yield Tick()
        yield dut.reset.eq(0)
        for cycle, event in enumerate(events):
            yield dut.req_tag.eq(event["req_tag"])
            yield dut.update_req_tag.eq(event["update_tag"])
            yield dut.write_valid.eq(event["write_valid"])
            yield dut.write_tag.eq(event["write_tag"])
            fields = entry_values(event["payload"])
            for signal, value in (
                (dut.write_is_call, fields["is_call"]), (dut.write_is_ret, fields["is_ret"]),
                (dut.write_is_jalr, fields["is_jalr"]), (dut.write_entry_valid, fields["valid"]),
                (dut.write_br_offset, fields["br_offset"]), (dut.write_br_sharing, fields["br_sharing"]),
                (dut.write_br_valid, fields["br_valid"]), (dut.write_br_lower, fields["br_lower"]),
                (dut.write_br_tar_stat, fields["br_tar_stat"]), (dut.write_tail_offset, fields["tail_offset"]),
                (dut.write_tail_sharing, fields["tail_sharing"]), (dut.write_tail_valid, fields["tail_valid"]),
                (dut.write_tail_lower, fields["tail_lower"]), (dut.write_tail_tar_stat, fields["tail_tar_stat"]),
                (dut.write_pft_addr, fields["pft_addr"]), (dut.write_carry, fields["carry"]),
                (dut.write_last_rvi_call, fields["last_rvi_call"]),
                (dut.write_strong_bias_0, fields["strong_bias_0"]), (dut.write_strong_bias_1, fields["strong_bias_1"]),
            ):
                yield signal.eq(value)
            yield Settle()
            expected_resp_hit = int(stored_valid and stored_tag == event["req_tag"])
            expected_update_hit = int((stored_valid and stored_tag == event["update_tag"]) or (event["write_valid"] and event["write_tag"] == event["update_tag"]))
            actual = {"cycle": cycle, "phase": 0, "resp_hit": int((yield dut.resp_hit)), "update_hit": int((yield dut.update_hit))}
            assert actual["resp_hit"] == expected_resp_hit, (cycle, actual, expected_resp_hit)
            assert actual["update_hit"] == expected_update_hit, (cycle, actual, expected_update_hit)
            observations.append(actual)
            yield Tick()
            if event["write_valid"]:
                stored = fields
                stored_tag = event["write_tag"]
                stored_valid = True
            # A synchronous write becomes visible on the following cycle;
            # do not sample the pre-edge response on the same write event.
            if stored is not None and not event["write_valid"]:
                yield dut.req_tag.eq(stored_tag)
                yield dut.update_req_tag.eq(stored_tag)
                yield dut.write_valid.eq(0)
                yield Settle()
                # Generator API reads signals directly after Settle.
                actual_response = {"cycle": cycle, "phase": 1}
                actual_response["resp_hit"] = int((yield dut.resp_hit))
                actual_response["update_hit"] = int((yield dut.update_hit))
                for key, signal in (
                    ("is_call", dut.resp_is_call), ("is_ret", dut.resp_is_ret), ("is_jalr", dut.resp_is_jalr),
                    ("valid", dut.resp_valid), ("br_offset", dut.resp_br_offset), ("br_sharing", dut.resp_br_sharing),
                    ("br_valid", dut.resp_br_valid), ("br_lower", dut.resp_br_lower), ("br_tar_stat", dut.resp_br_tar_stat),
                    ("tail_offset", dut.resp_tail_offset), ("tail_sharing", dut.resp_tail_sharing), ("tail_valid", dut.resp_tail_valid),
                    ("tail_lower", dut.resp_tail_lower), ("tail_tar_stat", dut.resp_tail_tar_stat), ("pft_addr", dut.resp_pft_addr),
                    ("carry", dut.resp_carry), ("last_rvi_call", dut.resp_last_rvi_call),
                    ("strong_bias_0", dut.resp_strong_bias_0), ("strong_bias_1", dut.resp_strong_bias_1),
                ):
                    actual_response[key] = int((yield signal))
                assert actual_response["resp_hit"] == 1
                assert actual_response["update_hit"] == 1
                for key, expected in stored.items():
                    assert actual_response[key] == expected, (cycle, key, actual_response[key], expected)
                observations.append(actual_response)
            yield Tick()

    # The generator process above intentionally uses the classic Amaranth API.
    # 上述生成器进程刻意使用经典 Amaranth API。
    simulator = Simulator(dut)
    simulator.add_clock(1e-6)
    simulator.add_process(bench)
    simulator.run()
    trace = json.dumps(observations, sort_keys=True, separators=(",", ":")).encode()
    return {"vectors": len(events), "observations": len(observations), "checks": len(observations) * 2, "trace_sha256": digest_bytes(trace), "pass": True}


# Emit machine-readable direct evidence. / 输出机器可读 direct 证据。
def main() -> int:
    """Run direct checks and write JSON. / 运行 direct 检查并写入 JSON。"""

    module = load_target()
    audit = audit_target(TARGET)
    registered = run_registered(module)
    rtl = module.build_verilog(None, {})
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_FRONTEND_FAUFTBWAY_DIRECT",
        "batch_id": "V2-SEMANTIC-FRONTEND-FAUFTBWAY",
        "source_commit": SOURCE_COMMIT,
        "target": {"path": str(TARGET.relative_to(ROOT)).replace("\\", "/"), "audit": audit},
        "source": {"path": str(SOURCE.relative_to(ROOT)).replace("\\", "/"), "sha256": digest_bytes(SOURCE.read_bytes())},
        "direct": registered,
        "generated": {"module": "FauFTBWay", "bytes": len(rtl.encode()), "sha256": digest_bytes(rtl.encode()), "module_decl": "module FauFTBWay" in rtl},
        "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": "PASS", "V2_REFERENCE_MATCHED": "PENDING_COORDINATOR_REVIEW", "UHSC_LOCALIZED": "NO_PROJECT_FACING_RENAME", "PARENT_CLOSURE_MATCHED": "PENDING", "ACCEPTED": "NOT_ALLOWED"},
        "status": "DIRECT_PASS_BOUNDED",
        "acceptance_eligible": False,
        "unclosed": ["Locked XSTop differential and independent validator review remain required.", "Full FTB/BPU parent closure, UHSC wrapper, and license review remain pending."],
    }
    RESULT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "vectors": registered["vectors"], "observations": registered["observations"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
