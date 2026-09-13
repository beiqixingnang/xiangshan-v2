"""Bounded direct checks for the V2 ICache worker batch.
V2 指令缓存工作批次的有界 direct 检查。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from amaranth.sim import Settle, Simulator, Tick


ROOT = Path(__file__).resolve().parents[1]
TARGET_DIR = ROOT / "python/ported/frontend/icache"
RESULT = ROOT / "validation/v2-p1-b-icache-direct-results.json"
SCALA = {
    "mshr": ROOT / "upstream/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala",
    "replacer": ROOT / "upstream/src/main/scala/xiangshan/frontend/icache/ICache.scala",
    "utility": ROOT / "upstream/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala",
    "fifo": ROOT / "upstream/src/main/scala/xiangshan/frontend/icache/FIFO.scala",
}


# Hash one file for reproducible evidence. / 对文件计算可复现证据摘要。
def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Load a target through an exact path, independent of package imports.
# 通过精确路径加载目标，独立于包导入。
def load_target(filename: str, module_name: str) -> Any:
    path = TARGET_DIR / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# Return a deterministic xorshift stream used by all stateful checks.
# 返回所有有状态检查共用的确定性 xorshift 流。
def xorshift(seed: int) -> int:
    seed &= 0xFFFFFFFF
    seed ^= (seed << 13) & 0xFFFFFFFF
    seed ^= seed >> 17
    seed ^= (seed << 5) & 0xFFFFFFFF
    return seed & 0xFFFFFFFF


# Check the V2 demultiplexer exhaustively for representative payloads.
# 对代表性载荷穷举检查 V2 解复用器。
def run_demux(module: Any, n: int) -> dict[str, Any]:
    dut = module.DeMultiplexer(50, n)
    payloads = [0, 1, (1 << 50) - 1, 0x2A123456789AB & ((1 << 50) - 1)]
    observations: list[dict[str, int]] = []

    def bench():
        for payload in payloads:
            for ready in range(1 << n):
                for valid in (0, 1):
                    yield dut.in_bits.eq(payload)
                    yield dut.in_valid.eq(valid)
                    for index in range(n):
                        yield dut.out_ready[index].eq((ready >> index) & 1)
                    yield Settle()
                    out_valid = 0
                    for index in range(n):
                        out_valid |= int((yield dut.out_valid[index])) << index
                    observations.append({
                        "bits": payload,
                        "ready": ready,
                        "valid": valid,
                        "in_ready": int((yield dut.in_ready)),
                        "out_valid": out_valid,
                        "chosen": int((yield dut.chosen)),
                    })
    sim = Simulator(dut)
    sim.add_process(bench)
    sim.run()
    for row in observations:
        ready = row["ready"]
        expected = row["valid"]
        mask = 0
        seen = False
        for index in range(n):
            if seen:
                bit = 0
            else:
                bit = row["valid"]
            mask |= bit << index
            if (ready >> index) & 1:
                seen = True
        expected_chosen = next((i for i in range(n) if (ready >> i) & 1), n - 1)
        assert row["in_ready"] == int(bool(ready))
        assert row["out_valid"] == mask
        assert row["chosen"] == expected_chosen
    return {"module": "DeMultiplexer", "variant": f"n{n}", "vectors": len(observations),
            "trace_sha256": hashlib.sha256(json.dumps(observations, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


# Check the selector mux for every valid mask and out-of-range selector.
# 对每个有效掩码及越界选择器检查选择复用器。
def run_mux(module: Any) -> dict[str, Any]:
    dut = module.MuxBundle(60, 10)
    observations: list[dict[str, int]] = []

    def bench():
        for seed in (0, 0x5A):
            payloads = [
                ((seed + index) & 0xF)
                | (((0x123456789000 + index + (seed << 20)) & ((1 << 48) - 1)) << 4)
                | (((0x80 + index + seed) & 0xFF) << 52)
                for index in range(10)
            ]
            for valid_mask in range(1024):
                for selector in range(16):
                    for ready in (0, 1):
                        yield dut.sel.eq(selector)
                        yield dut.out_ready.eq(ready)
                        for index in range(10):
                            yield dut.in_valid[index].eq((valid_mask >> index) & 1)
                            yield dut.in_bits[index].eq(payloads[index])
                        yield Settle()
                        selected = selector if selector < 10 else 0
                        in_ready = 0
                        for index in range(10):
                            in_ready |= int((yield dut.in_ready[index])) << index
                        observations.append({
                            "seed": seed,
                            "valid_mask": valid_mask,
                            "sel": selector,
                            "ready": ready,
                            "in_ready": in_ready,
                            "out_valid": int((yield dut.out_valid)),
                            "out_bits": int((yield dut.out_bits)),
                        })
                        assert observations[-1]["out_valid"] == ((valid_mask >> selected) & 1)
                        assert observations[-1]["out_bits"] == payloads[selected]
                        assert in_ready == ((ready << selector) if selector < 10 else 0)
    sim = Simulator(dut)
    sim.add_process(bench)
    sim.run()
    return {"module": "MuxBundle", "variant": "n10", "vectors": len(observations),
            "trace_sha256": hashlib.sha256(json.dumps(observations, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


# Check FIFO ordering, wraparound, simultaneous operations, and flush.
# 检查 FIFO 顺序、回绕、同时操作及 flush。
def run_fifo(module: Any) -> dict[str, Any]:
    dut = module.FIFOReg(4, 10, pipe=False, has_flush=True)
    events: list[tuple[int, int, int, int]] = []
    for value in range(10):
        events.append((1, value, 0, 0))
    events.extend([(1, 0xF, 0, 0), (0, 0, 1, 0), (0, 0, 1, 0), (1, 9, 1, 0), (0, 0, 0, 1)])
    state = 0x13579BDF
    for cycle in range(512):
        state = xorshift(state)
        enq = state & 1
        deq = (state >> 1) & 1
        flush = (state >> 2) & 1
        if cycle % 64 == 0:
            flush = 1
        if cycle % 37 == 0:
            enq = deq = 1
        events.append((enq, (state >> 8) & 0xF, deq, flush))

    observations: list[dict[str, int]] = []
    queue: list[int] = []

    def bench():
        for cycle, (enq, bits, deq, flush) in enumerate(events):
            yield dut.enq_valid.eq(enq)
            yield dut.enq_bits.eq(bits)
            yield dut.deq_ready.eq(deq)
            yield dut.flush.eq(flush)
            yield Settle()
            enq_ready = int((yield dut.enq_ready))
            deq_valid = int((yield dut.deq_valid))
            deq_bits = int((yield dut.deq_bits))
            observations.append({"cycle": cycle, "enq": enq, "bits": bits, "deq": deq, "flush": flush,
                                 "enq_ready": enq_ready, "deq_valid": deq_valid, "deq_bits": deq_bits})
            expected_ready = int(len(queue) < 10)
            assert enq_ready == expected_ready
            assert deq_valid == int(bool(queue))
            if queue:
                assert deq_bits == queue[0]
            if enq and enq_ready:
                queue.append(bits)
            if deq and deq_valid:
                queue.pop(0)
            if flush:
                queue.clear()
            yield Tick()

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_process(bench)
    sim.run()
    return {"module": "FIFOReg", "variant": "entries10-flush", "vectors": len(observations),
            "trace_sha256": hashlib.sha256(json.dumps(observations, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


# Compute the V2 four-way PLRU transition used by SetAssocLRU.
# 计算 SetAssocLRU 使用的 V2 四路 PLRU 转移。
def plru_next(state: int, way: int) -> int:
    root = 1 ^ ((way >> 1) & 1)
    left = ((state >> 1) & 1) if root else (1 ^ (way & 1))
    right = (1 ^ (way & 1)) if root else (state & 1)
    return (root << 2) | (left << 1) | right


# Compute the V2 four-way PLRU victim. / 计算 V2 四路 PLRU victim。
def plru_victim(state: int) -> int:
    root = (state >> 2) & 1
    child = ((state >> 1) & 1) if root else (state & 1)
    return (root << 1) | child


# Check both interleaved replacement banks against a transaction model.
# 对两个交错替换库与事务模型进行检查。
def run_replacer(module: Any) -> dict[str, Any]:
    dut = module.ICacheReplacer()
    events = []
    state = 0xC001D00D
    for cycle in range(320):
        state = xorshift(state)
        events.append({"tv0": state & 1, "ts0": (state >> 1) & 0xFF, "tw0": (state >> 9) & 3,
                       "tv1": (state >> 11) & 1, "ts1": (state >> 12) & 0xFF, "tw1": (state >> 20) & 3,
                       "vv": (state >> 22) & 1, "vs": (state >> 23) & 0xFF})
    policies = [[0 for _ in range(128)] for _ in range(2)]
    victim_reg_valid = 0
    victim_reg_set = 0
    victim_reg_way = 0
    observations = []

    def bench():
        nonlocal victim_reg_valid, victim_reg_set, victim_reg_way
        for cycle, event in enumerate(events):
            yield dut.touch_req_valid[0].eq(event["tv0"])
            yield dut.touch_req_valid[1].eq(event["tv1"])
            yield dut.touch_req_v_set_idx[0].eq(event["ts0"])
            yield dut.touch_req_v_set_idx[1].eq(event["ts1"])
            yield dut.touch_req_way[0].eq(event["tw0"])
            yield dut.touch_req_way[1].eq(event["tw1"])
            yield dut.victim_req_valid.eq(event["vv"])
            yield dut.victim_req_v_set_idx.eq(event["vs"])
            yield Settle()
            victim = int((yield dut.victim_resp_way))
            expected = plru_victim(policies[event["vs"] & 1][(event["vs"] >> 1) & 0x7F])
            if victim != expected:
                print("REPLACER_MISMATCH", cycle, event, victim, expected, "states", policies[0][event["vs"] >> 1], policies[1][event["vs"] >> 1])
                raise AssertionError((cycle, victim, expected))
            observations.append({**event, "cycle": cycle, "victim_way": victim})

            # Apply hit touch slot zero to each bank, exactly as ICache.scala.
            for bank in range(2):
                selected = event["ts0" if bank == 0 else "ts1"] & 1
                selected_event = (event["tv1"], event["ts1"], event["tw1"]) if selected else (event["tv0"], event["ts0"], event["tw0"])
                if selected_event[0]:
                    index = selected_event[1] >> 1
                    policies[bank][index] = plru_next(policies[bank][index], selected_event[2])
                if victim_reg_valid and (victim_reg_set & 1) == bank:
                    policies[bank][victim_reg_set >> 1] = plru_next(policies[bank][victim_reg_set >> 1], victim_reg_way)
            victim_reg_valid = event["vv"]
            if event["vv"]:
                victim_reg_set = event["vs"]
                victim_reg_way = victim
            yield Tick()

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_process(bench)
    sim.run()
    return {"module": "ICacheReplacer", "variant": "setplru-256x4-port2", "vectors": len(observations),
            "trace_sha256": hashlib.sha256(json.dumps(observations, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


# Check fetch and prefetch MSHR specializations at all V2 observation points.
# 检查 fetch 与 prefetch MSHR 特化版本的全部 V2 观测点。
def run_mshr(module: Any, is_fetch: bool) -> dict[str, Any]:
    dut = module.ICacheMSHR(entry_id=0 if is_fetch else 4, is_fetch=is_fetch)
    events = []
    state = 0xA5A55A5A
    for cycle in range(320):
        state = xorshift(state)
        events.append({"fencei": state & 1, "flush": 0 if is_fetch else ((state >> 1) & 1), "wfi": (state >> 2) & 1,
                       "req": (state >> 3) & 1, "blk": (state >> 4) & ((1 << 42) - 1), "set": (state >> 10) & 0xFF,
                       "lk0_blk": (state >> 12) & ((1 << 42) - 1), "lk0_set": (state >> 18) & 0xFF,
                       "lk1_blk": (state >> 20) & ((1 << 42) - 1), "lk1_set": (state >> 26) & 0xFF,
                       "acq_ready": (state >> 27) & 1, "victim": (state >> 28) & 3, "invalid": (state >> 30) & 1})
    valid = flush_reg = fencei_reg = issue = 0
    blk = set_idx = way = latency = 0
    observations = []

    def bench():
        nonlocal valid, flush_reg, fencei_reg, issue, blk, set_idx, way, latency
        for cycle, event in enumerate(events):
            yield dut.fencei.eq(event["fencei"])
            yield dut.flush.eq(event["flush"])
            yield dut.wfi_req.eq(event["wfi"])
            yield dut.req_valid.eq(event["req"])
            yield dut.req_blk_paddr.eq(event["blk"])
            yield dut.req_v_set_idx.eq(event["set"])
            for index in range(2):
                yield dut.lookup_blk_paddr[index].eq(event[f"lk{index}_blk"])
                yield dut.lookup_v_set_idx[index].eq(event[f"lk{index}_set"])
                yield dut.lookup_valid[index].eq(1)
            yield dut.acquire_ready.eq(event["acq_ready"])
            yield dut.victim_way.eq(event["victim"])
            yield dut.invalid.eq(event["invalid"])
            yield Settle()
            effective_flush = event["flush"] if not is_fetch else 0
            req_ready = int(not valid and not effective_flush and not event["fencei"])
            acquire_valid = int(valid and not issue and not effective_flush and not event["fencei"] and not event["wfi"])
            row = {"cycle": cycle, **event,
                   "req_ready": int((yield dut.req_ready)), "acquire_valid": int((yield dut.acquire_valid)),
                   "acquire_address": int((yield dut.acquire_address)), "acquire_v_set_idx": int((yield dut.acquire_v_set_idx)),
                   "lookup_hit0": int((yield dut.lookup_hit[0])), "lookup_hit1": int((yield dut.lookup_hit[1])),
                   "info_valid": int((yield dut.info_valid)), "info_blk_paddr": int((yield dut.info_blk_paddr)),
                   "info_v_set_idx": int((yield dut.info_v_set_idx)), "info_way": int((yield dut.info_way)),
                   "wfi_safe": int((yield dut.wfi_safe)), "perf_latency": int((yield dut.perf_latency))}
            assert row["req_ready"] == req_ready
            assert row["acquire_valid"] == acquire_valid
            assert row["acquire_address"] == ((blk << 6) & ((1 << 48) - 1))
            assert row["acquire_v_set_idx"] == set_idx
            assert row["lookup_hit0"] == int(valid and not fencei_reg and not flush_reg and event["lk0_blk"] == blk and event["lk0_set"] == set_idx)
            assert row["lookup_hit1"] == int(valid and not fencei_reg and not flush_reg and event["lk1_blk"] == blk and event["lk1_set"] == set_idx)
            observations.append(row)
            req_fire = bool(event["req"] and req_ready)
            acquire_fire = bool(acquire_valid and event["acq_ready"])
            if event["fencei"] or effective_flush:
                fencei_reg = flush_reg = 1
                if not issue:
                    valid = 0
            if req_fire:
                valid = 1
                flush_reg = fencei_reg = issue = 0
                blk = event["blk"]
                set_idx = event["set"]
            if acquire_fire:
                issue = 1
                way = event["victim"]
                latency = 0
            if valid and issue:
                latency = (latency + 1) & 0xFFFF
            if event["invalid"]:
                valid = 0
            yield Tick()

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_process(bench)
    sim.run()
    return {"module": "ICacheMSHR", "variant": "fetch-id0" if is_fetch else "prefetch-id4", "vectors": len(observations),
            "trace_sha256": hashlib.sha256(json.dumps(observations, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


# Run every family and persist machine-readable bounded evidence.
# 运行每个族并写入机器可读的有界证据。
def main() -> None:
    mshr = load_target("ICacheMshr-Hardware.py", "v2_icache_mshr_direct")
    replacer = load_target("ICacheReplacer-Hardware.py", "v2_icache_replacer_direct")
    utility = load_target("Utils-Hardware.py", "v2_icache_utils_direct")
    records = [run_demux(utility, 4), run_demux(utility, 10), run_mux(utility), run_fifo(utility),
               run_replacer(replacer), run_mshr(mshr, True), run_mshr(mshr, False)]
    payload = {
        "schema_version": 1,
        "kind": "V2_P1_B_ICACHE_DIRECT_EVIDENCE",
        "status": "PASS_BOUNDED_DIRECT",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "families": records,
        "target_paths": {key: path.relative_to(ROOT).as_posix() for key, path in {
            "ICacheMSHR": TARGET_DIR / "ICacheMshr-Hardware.py",
            "ICacheReplacer": TARGET_DIR / "ICacheReplacer-Hardware.py",
            "Utils": TARGET_DIR / "Utils-Hardware.py",
        }.items()},
        "target_sha256": {key: sha256(path) for key, path in {
            "ICacheMSHR": TARGET_DIR / "ICacheMshr-Hardware.py",
            "ICacheReplacer": TARGET_DIR / "ICacheReplacer-Hardware.py",
            "Utils": TARGET_DIR / "Utils-Hardware.py",
        }.items()},
        "source_paths": {key: path.relative_to(ROOT).as_posix() for key, path in SCALA.items()},
        "source_sha256": {key: sha256(path) for key, path in SCALA.items()},
        "acceptance_eligible": False,
        "reference_differential": "PENDING",
        "parent_closure": "PENDING",
        "uhsc_localization": {"status": "NO_PROJECT_FACING_RENAME", "manifest": "UHSC-Naming-Manifest.json"},
    }
    RESULT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "families": len(records)}, sort_keys=True))


if __name__ == "__main__":
    main()
