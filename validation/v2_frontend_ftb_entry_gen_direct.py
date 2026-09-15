"""Bounded direct checks for the V2 FTBEntryGen closure.
V2 FTBEntryGen 闭包的有界 direct 检查。
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from amaranth.sim import Settle, Simulator


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Frontend.Bpu.FTBEntryGen-Hardware.py"
SOURCE = ROOT / "upstream/src/main/scala/xiangshan/frontend/NewFtq.scala"
RESULT = ROOT / "validation/v2-frontend-ftb-entry-gen-direct-results.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"


# Load the exact Build path without package imports. / 不通过包导入加载精确 Build 路径。
def load_target() -> Any:
    """Load the FTBEntryGen target module. / 加载 FTBEntryGen 目标模块。"""

    spec = importlib.util.spec_from_file_location("v2_ftb_entry_gen_target", TARGET)
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


# Audit the five-zone, adapter, and source-format contract.
# 审计五区、适配器及源代码格式契约。
def audit_target(path: Path) -> dict[str, Any]:
    """Validate the maintained target file. / 校验受维护的目标文件。"""

    raw = path.read_bytes()
    text = raw.decode("utf-8")
    tree = ast.parse(text, filename=str(path))
    zones = ("Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry")
    positions = [text.find(zone) for zone in zones]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise AssertionError("five-zone order mismatch")
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw:
        raise AssertionError("target must be UTF-8 without BOM and LF-only")
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
    return {"utf8": True, "bom": False, "lf_only": True, "ast_parse": True,
            "zones": list(zones), "functions": sorted(functions), "bytes": len(raw),
            "sha256": digest_bytes(raw)}


# Generate deterministic input vectors spanning all branch/update cases.
# 生成覆盖所有分支/更新情形的确定性输入向量。
def make_vectors(count: int = 1024) -> list[dict[str, int]]:
    """Return deterministic FTBEntryGen vectors. / 返回确定性的 FTBEntryGen 向量。"""

    rows: list[dict[str, int]] = []
    state = 0x6D2B79F5
    for index in range(count):
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= state >> 17
        state ^= (state << 5) & 0xFFFFFFFF
        state &= 0xFFFFFFFF
        state2 = (state * 0x9E3779B1 + index * 0x7F4A7C15) & 0xFFFFFFFF
        start = ((state << 18) ^ (state2 << 3) ^ (index * 0x10001)) & ((1 << 50) - 1)
        target = ((state2 << 19) ^ (state * 0x45D9F3B) ^ (index * 0x101)) & ((1 << 50) - 1)
        pd_target = ((state2 << 11) ^ (state * 0x27D4EB2D)) & ((1 << 50) - 1)
        old_tail_lower = (state2 >> 2) & ((1 << 20) - 1)
        old_br_lower = (state >> 4) & ((1 << 12) - 1)
        # Force representative hit/new-branch/jump cases in the first rows.
        hit = int((index % 5) != 0)
        br_valid = int((index % 3) != 0)
        tail_valid = int((index % 4) != 0)
        tail_sharing = int((index % 2) == 0)
        cfi = (index * 7 + (state >> 7)) & 0xF
        jmp_offset = (index * 5 + (state2 >> 9)) & 0xF
        if index % 8 == 1:
            cfi = 3
            jmp_offset = cfi
        if index % 8 == 2:
            br_valid = 1
            tail_valid = 1
            tail_sharing = 1
            cfi = 12
            jmp_offset = 4
        if index % 8 == 3:
            hit = 0
            cfi = 7
            jmp_offset = 7
        pd_br = (state ^ (state2 << 1) ^ (1 << cfi)) & 0xFFFF
        pd_rvc = (state2 ^ (state << 2)) & 0xFFFF
        if index % 8 == 1:
            pd_br |= 1 << cfi
        rows.append({
            "start_addr": start,
            "old_is_call": (state >> 0) & 1,
            "old_is_ret": (state >> 1) & 1,
            "old_is_jalr": (state >> 2) & 1,
            "old_valid": (state >> 3) & 1,
            "old_br_offset": (state >> 5) & 0xF,
            "old_br_sharing": (state >> 9) & 1,
            "old_br_valid": br_valid,
            "old_br_lower": old_br_lower,
            "old_br_tar_stat": (state >> 15) & 3,
            "old_tail_offset": (state2 >> 5) & 0xF,
            "old_tail_sharing": tail_sharing,
            "old_tail_valid": tail_valid,
            "old_tail_lower": old_tail_lower,
            "old_tail_tar_stat": (state2 >> 13) & 3,
            "old_pft_addr": (state2 >> 18) & 0xF,
            "old_carry": (state2 >> 22) & 1,
            "old_last_rvi_call": (state2 >> 23) & 1,
            "old_strong_bias_0": (state2 >> 24) & 1,
            "old_strong_bias_1": (state2 >> 25) & 1,
            "pd_br_mask": pd_br,
            "pd_jmp_info_valid": int((index % 6) != 0),
            "pd_jmp_info_0": (state2 >> 26) & 1,
            "pd_jmp_info_1": (state2 >> 27) & 1,
            "pd_jmp_info_2": (state2 >> 28) & 1,
            "pd_jmp_offset": jmp_offset,
            "pd_jal_target": pd_target,
            "pd_rvc_mask": pd_rvc,
            "cfi_index_valid": int((index % 7) != 0),
            "cfi_index_bits": cfi,
            "target": target,
            "hit": hit,
            "mispredict_vec": (state ^ (state2 << 3) ^ index) & 0xFFFF,
        })
    return rows


# Compute an independent integer oracle for one vector.
# 计算单个向量的独立整数预言机结果。
def model_event(event: dict[str, int]) -> dict[str, int]:
    """Evaluate the locked NewFtq equations in Python. / 用 Python 计算锁定 NewFtq 方程。"""

    bit = lambda value, index: (value >> index) & 1
    mask = lambda value, width: value & ((1 << width) - 1)
    start = event["start_addr"]
    cfi = event["cfi_index_bits"]
    cfi_valid = event["cfi_index_valid"]
    jmp_valid = event["pd_jmp_info_valid"]
    br_mask = event["pd_br_mask"]
    rvc_mask = event["pd_rvc_mask"]
    cfi_is_br = bit(br_mask, cfi) & cfi_valid
    init_jalr = jmp_valid & event["pd_jmp_info_0"] & cfi_valid
    last_jmp_rvi = jmp_valid & int(event["pd_jmp_offset"] == 15) & (1 - bit(rvc_mask, 15))
    cfi_jalr = int(cfi == event["pd_jmp_offset"]) & init_jalr
    gen0 = (event["target"] >> 1) if cfi_jalr else (event["pd_jal_target"] >> 1)
    start_low = (start >> 1) & 0xF
    jmp_pft = mask(start_low + event["pd_jmp_offset"] + (1 if bit(rvc_mask, event["pd_jmp_offset"]) else 2), 5)
    old_br_valid = event["old_br_valid"]
    old_tail_valid = event["old_tail_valid"]
    old_br_offset = event["old_br_offset"]
    old_tail_offset = event["old_tail_offset"]
    rec0 = old_br_valid & int(old_br_offset == cfi)
    rec1 = old_tail_valid & int(old_tail_offset == cfi) & event["old_tail_sharing"]
    is_new_br = cfi_is_br & int(not (rec0 | rec1))
    insert0 = int((not old_br_valid) or cfi < old_br_offset)
    insert1 = old_br_valid & int(cfi > old_br_offset) & int((not old_tail_valid) or cfi < old_tail_offset)
    insert_br_after = int(cfi > old_br_offset)
    gen3 = int(cfi > old_tail_offset)
    gen4 = gen3 | int(not old_br_valid)
    pft_need = is_new_br & old_br_valid & old_tail_valid
    new_pft_offset = old_tail_offset if (insert0 or insert1) else cfi
    old_tail_stat = event["old_tail_tar_stat"]
    if old_tail_stat == 1:
        old_hi_br = ((start >> 13) & ((1 << 37) - 1)) + 1
        old_hi_jmp = ((start >> 21) & ((1 << 29) - 1)) + 1
    elif old_tail_stat == 2:
        old_hi_br = ((start >> 13) & ((1 << 37) - 1)) - 1
        old_hi_jmp = ((start >> 21) & ((1 << 29) - 1)) - 1
    elif old_tail_stat == 0:
        old_hi_br = (start >> 13) & ((1 << 37) - 1)
        old_hi_jmp = (start >> 21) & ((1 << 29) - 1)
    else:
        old_hi_br = old_hi_jmp = 0
    old_target_shared = mask((old_hi_br << 13) | ((event["old_tail_lower"] & 0xFFF) << 1), 50)
    old_target_jmp = mask((old_hi_jmp << 21) | ((event["old_tail_lower"] & ((1 << 20) - 1)) << 1), 50)
    old_target = old_target_shared if event["old_tail_sharing"] else old_target_jmp
    jalr_modified = cfi_jalr & int(old_target != event["target"]) & int(not event["old_tail_sharing"])
    strong_tail = old_tail_valid & event["old_tail_sharing"]
    old_strong0 = (event["old_strong_bias_0"] & cfi_valid & old_br_valid & int(cfi == old_br_offset)) if rec0 else (int(not rec1) & event["old_strong_bias_0"])
    old_strong1 = (rec0 | int(not rec1) | (cfi_valid & strong_tail & int(cfi == old_tail_offset))) & event["old_strong_bias_1"]
    gen5 = int(not is_new_br) | int(not pft_need)
    gen6 = is_new_br & insert0
    gen7 = is_new_br & pft_need
    target_hi_br = event["target"] >> 13
    start_hi_br = start >> 13
    br_stat = 1 if target_hi_br > start_hi_br else 2 if target_hi_br < start_hi_br else 0
    target_hi_jmp = event["target"] >> 21
    start_hi_jmp = start >> 21
    jmp_stat = 1 if target_hi_jmp > start_hi_jmp else 2 if target_hi_jmp < start_hi_jmp else 0
    init_hi = gen0 >> 20
    init_stat = 1 if init_hi > start_hi_jmp else 2 if init_hi < start_hi_jmp else 0
    new_br_offset = (cfi if gen6 else old_br_offset) if event["hit"] else (cfi if cfi_is_br else 0)
    new_br_valid = (gen6 | old_br_valid) if event["hit"] else cfi_is_br
    new_br_sharing = event["hit"] & (int(not is_new_br) | int(not insert0)) & event["old_br_sharing"]
    new_br_lower = ((event["target"] >> 1) & 0xFFF) if (event["hit"] and gen6) else ((event["old_br_lower"] if event["hit"] else ((event["target"] >> 1) & 0xFFF)) if (event["hit"] or cfi_is_br) else 0)
    if event["hit"]:
        new_br_stat = br_stat if gen6 else event["old_br_tar_stat"]
    else:
        new_br_stat = br_stat if cfi_is_br else 0
    if event["hit"]:
        new_tail_offset = cfi if (is_new_br and insert1) else (old_tail_offset if (not is_new_br or gen4) else old_br_offset)
    else:
        new_tail_offset = event["pd_jmp_offset"] if jmp_valid else 0
    if event["hit"]:
        new_tail_sharing = int(is_new_br and (insert1 or ((not gen3) and old_br_valid) or event["old_tail_sharing"]) or (not is_new_br and (not jalr_modified) and event["old_tail_sharing"]))
    else:
        new_tail_sharing = 0
    if event["hit"]:
        new_tail_valid = int((insert1 or (old_tail_valid if gen4 else old_br_valid)) if is_new_br else old_tail_valid)
    else:
        new_tail_valid = jmp_valid & int((jmp_valid and (not event["pd_jmp_info_0"]) and cfi_valid) or init_jalr)
    if event["hit"]:
        if is_new_br:
            new_tail_lower = ((event["target"] >> 1) & 0xFFF) if insert1 else (event["old_tail_lower"] if gen4 else event["old_br_lower"])
        else:
            new_tail_lower = ((event["target"] >> 1) & ((1 << 20) - 1)) if jalr_modified else event["old_tail_lower"]
    else:
        new_tail_lower = (gen0 & ((1 << 20) - 1)) if jmp_valid else 0
    if event["hit"]:
        if is_new_br:
            new_tail_stat = br_stat if insert1 else (event["old_tail_tar_stat"] if gen4 else event["old_br_tar_stat"])
        else:
            new_tail_stat = jmp_stat if jalr_modified else event["old_tail_tar_stat"]
    else:
        new_tail_stat = init_stat if jmp_valid else 0
    new_pft_addr = ((start_low + new_pft_offset) & 0xF) if (event["hit"] and gen7) else (event["old_pft_addr"] if event["hit"] else (jmp_pft & 0xF if (jmp_valid and not last_jmp_rvi) else start_low))
    new_carry = (((start_low + new_pft_offset) >> 4) & 1) if (event["hit"] and gen7) else (event["old_carry"] if event["hit"] else int(not (jmp_valid and not last_jmp_rvi)) | ((jmp_pft >> 4) & 1))
    new_last = (gen5 & event["old_last_rvi_call"]) if event["hit"] else (int(event["pd_jmp_offset"] == 15) & int(not bit(rvc_mask, 15)))
    if event["hit"]:
        new_bias0 = (insert0 | (int(not insert_br_after) & event["old_strong_bias_0"])) if is_new_br else ((int(not jalr_modified) & event["old_strong_bias_0"]) if jalr_modified else old_strong0)
        new_bias1 = (insert1 | (int(not gen3) & event["old_strong_bias_1"])) if is_new_br else ((int(not jalr_modified) & event["old_strong_bias_1"]) if jalr_modified else old_strong1)
    else:
        new_bias0 = cfi_is_br
        new_bias1 = jmp_valid & init_jalr
    mispred = event["mispredict_vec"]
    tail_marker = new_tail_valid & new_tail_sharing
    return {
        "new_is_call": (gen5 & event["old_is_call"]) if event["hit"] else (jmp_valid & event["pd_jmp_info_1"] & cfi_valid),
        "new_is_ret": (gen5 & event["old_is_ret"]) if event["hit"] else (jmp_valid & event["pd_jmp_info_2"] & cfi_valid),
        "new_is_jalr": (gen5 & event["old_is_jalr"]) if event["hit"] else init_jalr,
        "new_valid": int((not event["hit"]) or event["old_valid"]),
        "new_br_offset": new_br_offset,
        "new_br_sharing": new_br_sharing,
        "new_br_valid": new_br_valid,
        "new_br_lower": new_br_lower,
        "new_br_tar_stat": new_br_stat,
        "new_tail_offset": new_tail_offset,
        "new_tail_sharing": new_tail_sharing,
        "new_tail_valid": new_tail_valid,
        "new_tail_lower": new_tail_lower,
        "new_tail_tar_stat": new_tail_stat,
        "new_pft_addr": new_pft_addr,
        "new_carry": new_carry,
        "new_last_rvi_call": new_last,
        "new_strong_bias_0": new_bias0,
        "new_strong_bias_1": new_bias1,
        "taken_mask_0": int(cfi == new_br_offset and cfi_valid and new_br_valid),
        "taken_mask_1": int(cfi == new_tail_offset and cfi_valid and tail_marker),
        "jmp_taken": int(new_tail_valid and not new_tail_sharing and new_tail_offset == cfi),
        "mispred_mask_0": int(new_br_valid and bit(mispred, new_br_offset)),
        "mispred_mask_1": int(tail_marker and bit(mispred, new_tail_offset)),
        "mispred_mask_2": int(new_tail_valid and not new_tail_sharing and bit(mispred, event["pd_jmp_offset"])),
        "is_old_entry": int(event["hit"] and not is_new_br and not jalr_modified and not ((event["old_strong_bias_0"] and old_br_valid and not old_strong0) or (event["old_strong_bias_1"] and strong_tail and not old_strong1))),
    }


# Run direct Amaranth simulation against the independent integer oracle.
# 运行 Amaranth direct 仿真并与独立整数预言机比较。
def run_direct(module: Any, vectors: list[dict[str, int]]) -> dict[str, Any]:
    """Exercise all target ports and return trace evidence. / 激励全部目标端口并返回轨迹证据。"""

    dut = module.FTBEntryGen(module.FTBEntryGenConfig())
    input_map = {
        "start_addr": dut.start_addr, "old_is_call": dut.old_is_call, "old_is_ret": dut.old_is_ret,
        "old_is_jalr": dut.old_is_jalr, "old_valid": dut.old_valid, "old_br_offset": dut.old_br_offset,
        "old_br_sharing": dut.old_br_sharing, "old_br_valid": dut.old_br_valid, "old_br_lower": dut.old_br_lower,
        "old_br_tar_stat": dut.old_br_tar_stat, "old_tail_offset": dut.old_tail_offset,
        "old_tail_sharing": dut.old_tail_sharing, "old_tail_valid": dut.old_tail_valid,
        "old_tail_lower": dut.old_tail_lower, "old_tail_tar_stat": dut.old_tail_tar_stat,
        "old_pft_addr": dut.old_pft_addr, "old_carry": dut.old_carry,
        "old_last_rvi_call": dut.old_last_rvi_call, "old_strong_bias_0": dut.old_strong_bias_0,
        "old_strong_bias_1": dut.old_strong_bias_1, "pd_jmp_info_valid": dut.pd_jmp_info_valid,
        "pd_jmp_info_0": dut.pd_jmp_info_0, "pd_jmp_info_1": dut.pd_jmp_info_1,
        "pd_jmp_info_2": dut.pd_jmp_info_2, "pd_jmp_offset": dut.pd_jmp_offset,
        "pd_jal_target": dut.pd_jal_target, "cfi_index_valid": dut.cfi_index_valid,
        "cfi_index_bits": dut.cfi_index_bits, "target": dut.target, "hit": dut.hit,
    }
    for index, signal in enumerate(dut.pd_br_mask):
        input_map[f"pd_br_mask_{index}"] = signal
    for index, signal in enumerate(dut.pd_rvc_mask):
        input_map[f"pd_rvc_mask_{index}"] = signal
    for index, signal in enumerate(dut.mispredict_vec):
        input_map[f"mispredict_vec_{index}"] = signal
    output_map = {
        "new_is_call": dut.new_is_call, "new_is_ret": dut.new_is_ret, "new_is_jalr": dut.new_is_jalr,
        "new_valid": dut.new_valid, "new_br_offset": dut.new_br_offset, "new_br_sharing": dut.new_br_sharing,
        "new_br_valid": dut.new_br_valid, "new_br_lower": dut.new_br_lower, "new_br_tar_stat": dut.new_br_tar_stat,
        "new_tail_offset": dut.new_tail_offset, "new_tail_sharing": dut.new_tail_sharing,
        "new_tail_valid": dut.new_tail_valid, "new_tail_lower": dut.new_tail_lower,
        "new_tail_tar_stat": dut.new_tail_tar_stat, "new_pft_addr": dut.new_pft_addr,
        "new_carry": dut.new_carry, "new_last_rvi_call": dut.new_last_rvi_call,
        "new_strong_bias_0": dut.new_strong_bias_0, "new_strong_bias_1": dut.new_strong_bias_1,
        "taken_mask_0": dut.taken_mask_0, "taken_mask_1": dut.taken_mask_1, "jmp_taken": dut.jmp_taken,
        "mispred_mask_0": dut.mispred_mask_0, "mispred_mask_1": dut.mispred_mask_1,
        "mispred_mask_2": dut.mispred_mask_2, "is_old_entry": dut.is_old_entry,
    }
    observations: list[dict[str, int]] = []
    failures: list[dict[str, Any]] = []

    def bench():
        for index, event in enumerate(vectors):
            yield input_map["start_addr"].eq(event["start_addr"])
            for name, signal in input_map.items():
                if name == "start_addr":
                    continue
                if name.startswith("pd_br_mask_"):
                    value = (event["pd_br_mask"] >> int(name.rsplit("_", 1)[1])) & 1
                elif name.startswith("pd_rvc_mask_"):
                    value = (event["pd_rvc_mask"] >> int(name.rsplit("_", 1)[1])) & 1
                elif name.startswith("mispredict_vec_"):
                    value = (event["mispredict_vec"] >> int(name.rsplit("_", 1)[1])) & 1
                else:
                    value = event[name]
                yield signal.eq(value)
            yield Settle()
            actual: dict[str, int] = {}
            for name, signal in output_map.items():
                actual[name] = int((yield signal))
            expected = model_event(event)
            observations.append(actual)
            if actual != expected and len(failures) < 8:
                failures.append({"index": index, "actual": actual, "expected": expected,
                                 "input_snapshot": {"hit": int((yield dut.hit)),
                                                     "cfi_index_valid": int((yield dut.cfi_index_valid)),
                                                     "cfi_index_bits": int((yield dut.cfi_index_bits)),
                                                     "old_br_offset": int((yield dut.old_br_offset)),
                                                     "old_br_valid": int((yield dut.old_br_valid)),
                                                     "old_tail_offset": int((yield dut.old_tail_offset)),
                                                     "old_tail_valid": int((yield dut.old_tail_valid))}})

    simulator = Simulator(dut)
    simulator.add_process(bench)
    simulator.run()
    trace = json.dumps(observations, sort_keys=True, separators=(",", ":")).encode()
    return {"vectors": len(vectors), "observations": len(observations), "checks": len(vectors) * len(output_map),
            "trace_sha256": digest_bytes(trace), "failures": failures, "pass": not failures}


# Emit machine-readable direct evidence. / 输出机器可读 direct 证据。
def main() -> int:
    """Run direct checks and write JSON. / 运行 direct 检查并写入 JSON。"""

    module = load_target()
    audit = audit_target(TARGET)
    vectors = make_vectors()
    direct = run_direct(module, vectors)
    rtl = module.build_verilog(None, {})
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_FRONTEND_FTB_ENTRY_GEN_DIRECT",
        "batch_id": "V2-SEMANTIC-FRONTEND-FTB-ENTRY-GEN",
        "source_commit": SOURCE_COMMIT,
        "target": {"path": str(TARGET.relative_to(ROOT)).replace("\\", "/"), "audit": audit},
        "source": {"path": str(SOURCE.relative_to(ROOT)).replace("\\", "/"), "sha256": digest_bytes(SOURCE.read_bytes())},
        "direct": direct,
        "generated": {"module": "FTBEntryGen", "bytes": len(rtl.encode()), "sha256": digest_bytes(rtl.encode()), "module_decl": "module FTBEntryGen" in rtl},
        "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": "PASS" if direct["pass"] else "FAIL", "V2_REFERENCE_MATCHED": "PENDING", "UHSC_LOCALIZED": "NO_PROJECT_FACING_RENAME", "PARENT_CLOSURE_MATCHED": "PENDING", "ACCEPTED": "NOT_ALLOWED"},
        "status": "DIRECT_PASS_BOUNDED" if direct["pass"] else "DIRECT_FAIL",
        "acceptance_eligible": False,
        "unclosed": ["Locked XSTop differential, independent validator, and full FTB/BPU parent closure remain pending."],
    }
    RESULT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "vectors": direct["vectors"], "checks": direct["checks"]}, sort_keys=True))
    return 0 if direct["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
