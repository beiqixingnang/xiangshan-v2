"""Reusable bounded tests for the UHSC V2 ICache/prefetch family."""

from __future__ import annotations

import importlib.util
import random
import sys
import unittest
from pathlib import Path
from typing import Any

from amaranth.sim import Settle, Simulator, Tick

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Cpu-Core-Frontend.Icache.Prefetch.Family-Hardware.py"


def load_subject() -> Any:
    spec = importlib.util.spec_from_file_location("testing_icache_prefetch", TARGET)
    if spec is None or spec.loader is None: raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); return module


class IcachePrefetchFamilyTest(unittest.TestCase):
    def test_all_members_export(self) -> None:
        module = load_subject()
        for member in module.COVERED_MODULES: self.assertIn(f"module {member}", module.build_verilog({"module": member}, {}))

    def test_l2tlb_miss_queue_fifo_and_flush(self) -> None:
        module = load_subject()
        dut = module.IcachePrefetchFamily("L2TlbMissQueue")
        observed: list[tuple[int, int, int, int]] = []

        def process():
            yield dut.ports["reset"].eq(1)
            yield Tick()
            yield dut.ports["reset"].eq(0)
            yield dut.ports["io_out_ready"].eq(0)
            for vpn, s2xlate, source, is_llptw in ((11, 1, 2, 0), (22, 2, 1, 1), (33, 3, 0, 0)):
                yield dut.ports["io_in_valid"].eq(1)
                yield dut.ports["io_in_bits_req_info_vpn"].eq(vpn)
                yield dut.ports["io_in_bits_req_info_s2xlate"].eq(s2xlate)
                yield dut.ports["io_in_bits_req_info_source"].eq(source)
                yield dut.ports["io_in_bits_isLLptw"].eq(is_llptw)
                yield Tick()
            yield dut.ports["io_in_valid"].eq(0)
            yield Settle()
            for expected in ((11, 1, 2, 0), (22, 2, 1, 1), (33, 3, 0, 0)):
                observed.append((
                    int((yield dut.ports["io_out_bits_req_info_vpn"])),
                    int((yield dut.ports["io_out_bits_req_info_s2xlate"])),
                    int((yield dut.ports["io_out_bits_req_info_source"])),
                    int((yield dut.ports["io_out_bits_isLLptw"])),
                ))
                self.assertEqual(expected, observed[-1])
                yield dut.ports["io_out_ready"].eq(1)
                yield Tick()
                yield dut.ports["io_out_ready"].eq(0)
                yield Settle()
            self.assertEqual(0, int((yield dut.ports["io_out_valid"])))

            yield dut.ports["io_in_valid"].eq(1)
            yield dut.ports["io_in_bits_req_info_vpn"].eq(99)
            yield Tick()
            yield dut.ports["io_in_valid"].eq(0)
            yield dut.ports["io_sfence_valid"].eq(1)
            yield Tick()
            yield dut.ports["io_sfence_valid"].eq(0)
            yield Settle()
            self.assertEqual(0, int((yield dut.ports["io_out_valid"])))

        sim = Simulator(dut)
        sim.add_clock(1e-6)
        sim.add_process(process)
        sim.run()

    def test_monitor_quality_window_and_recovery_cycles(self) -> None:
        """Check observable disable thresholds and both recovery delays."""

        module = load_subject()
        dut = module.IcachePrefetchFamily("PrefetcherMonitor")
        p = dut.ports

        async def bench(ctx):
            ctx.set(p["reset"], 1)
            await ctx.tick()
            ctx.set(p["reset"], 0)
            self.assertEqual((1, 1), (ctx.get(p["io_pf_ctrl_enable"]),
                                     ctx.get(p["io_pf_ctrl_confidence"])))
            ctx.set(p["io_validity_bad_prefetch"], 1)
            await ctx.tick().repeat(1000)
            self.assertEqual(1, ctx.get(p["io_pf_ctrl_enable"]))
            ctx.set(p["io_validity_bad_prefetch"], 0)
            await ctx.tick()
            self.assertEqual((0, 0), (ctx.get(p["io_pf_ctrl_enable"]),
                                     ctx.get(p["io_pf_ctrl_confidence"])))
            await ctx.tick().repeat(100000)
            self.assertEqual(0, ctx.get(p["io_pf_ctrl_enable"]))
            await ctx.tick()
            self.assertEqual((1, 0), (ctx.get(p["io_pf_ctrl_enable"]),
                                     ctx.get(p["io_pf_ctrl_confidence"])))
            await ctx.tick().repeat(99999)
            self.assertEqual(0, ctx.get(p["io_pf_ctrl_confidence"]))
            await ctx.tick()
            self.assertEqual(1, ctx.get(p["io_pf_ctrl_confidence"]))

            # At a timely window boundary, 200 late misses take priority
            # over the 900 late hits that would otherwise disable prefetch.
            ctx.set(p["reset"], 1)
            await ctx.tick()
            ctx.set(p["reset"], 0)
            ctx.set(p["io_timely_total_prefetch"], 1)
            ctx.set(p["io_timely_late_hit_prefetch"], 1)
            ctx.set(p["io_timely_late_miss_prefetch"], 1)
            await ctx.tick().repeat(200)
            ctx.set(p["io_timely_late_miss_prefetch"], 0)
            await ctx.tick().repeat(700)
            ctx.set(p["io_timely_late_hit_prefetch"], 0)
            await ctx.tick().repeat(100)
            ctx.set(p["io_timely_total_prefetch"], 0)
            await ctx.tick()
            self.assertEqual((1, 1), (ctx.get(p["io_pf_ctrl_enable"]),
                                     ctx.get(p["io_pf_ctrl_confidence"])))

            # A second window of late hits alone disables both sticky states.
            ctx.set(p["io_timely_late_hit_prefetch"], 1)
            await ctx.tick().repeat(1000)
            ctx.set(p["io_timely_late_hit_prefetch"], 0)
            await ctx.tick()
            self.assertEqual((0, 0), (ctx.get(p["io_pf_ctrl_enable"]),
                                     ctx.get(p["io_pf_ctrl_confidence"])))

        sim = Simulator(dut)
        sim.add_clock(1e-6)
        sim.add_testbench(bench)
        sim.run()

    def test_mmio_lane_alignment_backpressure_and_flush(self) -> None:
        module = load_subject()
        dut = module.IcachePrefetchFamily("InstrMMIOEntry")
        p = dut.ports

        async def bench(ctx):
            rng = random.Random(0x1CA)
            ctx.set(p["reset"], 1)
            await ctx.tick()
            ctx.set(p["reset"], 0)
            for lane in range(4):
                for flush in (0, 1):
                    address = 0x12345678A000 + lane * 2
                    data = rng.getrandbits(64)
                    ctx.set(p["io_req_valid"], 1)
                    ctx.set(p["io_req_bits_addr"], address)
                    self.assertEqual(1, ctx.get(p["io_req_ready"]))
                    await ctx.tick()
                    ctx.set(p["io_req_valid"], 0)
                    ctx.set(p["io_wfi_wfiReq"], 1)
                    self.assertEqual(0, ctx.get(p["io_mmio_acquire_valid"]))
                    self.assertEqual(address & ~7, ctx.get(p["io_mmio_acquire_bits_address"]))
                    await ctx.tick()
                    ctx.set(p["io_wfi_wfiReq"], 0)
                    self.assertEqual(1, ctx.get(p["io_mmio_acquire_valid"]))
                    ctx.set(p["io_mmio_acquire_ready"], 0)
                    await ctx.tick()
                    self.assertEqual(1, ctx.get(p["io_mmio_acquire_valid"]))
                    ctx.set(p["io_mmio_acquire_ready"], 1)
                    await ctx.tick()
                    self.assertEqual(0, ctx.get(p["io_wfi_wfiSafe"]))
                    ctx.set(p["io_req_bits_flush"], flush)
                    await ctx.tick()
                    ctx.set(p["io_req_bits_flush"], 0)
                    ctx.set(p["io_mmio_grant_valid"], 1)
                    ctx.set(p["io_mmio_grant_bits_data"], data)
                    ctx.set(p["io_mmio_grant_bits_corrupt"], lane & 1)
                    await ctx.tick()
                    ctx.set(p["io_mmio_grant_valid"], 0)
                    self.assertEqual(1 - flush, ctx.get(p["io_resp_valid"]))
                    self.assertEqual((data >> (lane * 16)) & 0xFFFFFFFF,
                                     ctx.get(p["io_resp_bits_data"]))
                    self.assertEqual(lane & 1, ctx.get(p["io_resp_bits_corrupt"]))
                    # Flush at SEND_RESP must clear, so the next allocation
                    # can complete normally without inheriting stale flush.
                    ctx.set(p["io_req_bits_flush"], 1)
                    await ctx.tick()
                    ctx.set(p["io_req_bits_flush"], 0)
                    self.assertEqual(1, ctx.get(p["io_req_ready"]))
                    self.assertEqual(0, ctx.get(p["io_resp_valid"]))

        sim = Simulator(dut)
        sim.add_clock(1e-6)
        sim.add_testbench(bench)
        sim.run()

    def test_tlb_prefetch_recent_history_and_translation_stages(self) -> None:
        module = load_subject()
        dut = module.IcachePrefetchFamily("L2TlbPrefetch")
        p = dut.ports

        async def bench(ctx):
            rng = random.Random(0x7B)
            recent: list[int | None] = [None] * 4
            index, current, valid = 0, 0, False
            ctx.set(p["clock"], 0)
            flush_names = ("io_sfence_valid", "io_csr_satp_changed", "io_csr_vsatp_changed",
                           "io_csr_hgatp_changed", "io_csr_priv_virt_changed")
            for cycle in range(350):
                reset = cycle in (0, 170)
                if reset:
                    recent = [None] * 4
                    index, valid = 0, False
                ctx.set(p["reset"], int(reset))
                vpn = rng.choice([0x1000, 0x1007, 0x1008, 0x1010, 0x1020, (1 << 38) - 1])
                incoming, ready = rng.randrange(4) != 0, rng.randrange(3) != 0
                flush_index = rng.randrange(5) if cycle % 23 == 0 else -1
                vsatp, hgatp, virt = rng.randrange(16), rng.randrange(16), rng.randrange(2)
                for i, name in enumerate(flush_names):
                    ctx.set(p[name], int(i == flush_index))
                ctx.set(p["io_in_valid"], int(incoming))
                ctx.set(p["io_out_ready"], int(ready))
                ctx.set(p["io_in_bits_vpn"], vpn)
                ctx.set(p["io_csr_vsatp_mode"], vsatp)
                ctx.set(p["io_csr_hgatp_mode"], hgatp)
                ctx.set(p["io_csr_priv_virt"], virt)
                await ctx.delay(1e-9)
                self.assertEqual(int(valid), ctx.get(p["io_out_valid"]), cycle)
                self.assertEqual(current, ctx.get(p["io_out_bits_req_info_vpn"]), cycle)
                self.assertEqual((int(virt and vsatp != 0) | (int(virt and hgatp != 0) << 1)),
                                 ctx.get(p["io_out_bits_req_info_s2xlate"]))
                next_vpn = (((vpn >> 3) + 1) << 3) & ((1 << 38) - 1)
                duplicate = any(old is not None and (old >> 3) == (next_vpn >> 3)
                                for old in recent)
                fire = valid and ready
                previous = current
                if incoming:
                    current = next_vpn
                if not reset:
                    valid = flush_index < 0 and ((incoming and not duplicate) or (not fire and valid))
                    if fire:
                        recent[index] = previous
                        index = (index + 1) % 4
                    if flush_index >= 0:
                        recent = [None] * 4
                ctx.set(p["clock"], 1)
                await ctx.delay(1e-9)
                ctx.set(p["clock"], 0)
                await ctx.delay(1e-9)

        sim = Simulator(dut)
        sim.add_testbench(bench)
        sim.run()


    def test_waylookup_ring_refill_updates_and_guest_faults(self) -> None:
        module = load_subject()
        dut = module.IcachePrefetchFamily("WayLookup")
        p = dut.ports
        rng = random.Random(0x32A7)
        widths = {name.removeprefix("io_write_bits_entry_"): width
                  for name, direction, width in dut.specs
                  if direction == "input" and name.startswith("io_write_bits_entry_")}

        def entry(seed):
            result = {key: (seed * 13 + index * 7) & ((1 << width) - 1)
                      for index, (key, width) in enumerate(widths.items())}
            result.update(itlb_exception_0=0, itlb_exception_1=0)
            return result

        async def bench(ctx):
            slots = [dict.fromkeys(widths, 0) for _ in range(32)]
            head = tail = 0
            fault_valid, fault_slot, fault_addr, fault_nonleaf = False, 0, 0, 0
            ctx.set(p["clock"], 0)

            async def step(incoming=None, ready=False, update=None, flush=False, reset=False,
                           gpaddr=0x123456789ABCD, nonleaf=1):
                nonlocal slots, head, tail, fault_valid, fault_slot, fault_addr, fault_nonleaf
                data = entry(91) if incoming is None else dict(incoming)
                ctx.set(p["reset"], int(reset))
                ctx.set(p["io_flush"], int(flush))
                ctx.set(p["io_read_ready"], int(ready))
                ctx.set(p["io_write_valid"], int(incoming is not None))
                for key, value in data.items():
                    ctx.set(p["io_write_bits_entry_" + key], value)
                ctx.set(p["io_write_bits_gpf_gpaddr"], gpaddr)
                ctx.set(p["io_write_bits_gpf_isForVSnonLeafPTE"], nonleaf)
                ctx.set(p["io_update_valid"], int(update is not None))
                vset, tag, mask, corrupt = update or (0, 0, 0, False)
                ctx.set(p["io_update_bits_vSetIdx"], vset)
                ctx.set(p["io_update_bits_blkPaddr"], (tag << 6) | 0x25)
                ctx.set(p["io_update_bits_waymask"], mask)
                ctx.set(p["io_update_bits_corrupt"], int(corrupt))
                if reset:
                    slots = [dict.fromkeys(widths, 0) for _ in range(32)]
                    head = tail = 0
                    fault_valid, fault_slot, fault_addr, fault_nonleaf = False, 0, 0, 0
                await ctx.delay(1e-9)
                occupancy = (tail - head) % 64
                bypass = occupancy == 0 and incoming is not None
                valid = occupancy != 0 or incoming is not None
                reading = ready and valid
                fault_hit = fault_valid and head % 64 == fault_slot
                writable = occupancy != 32 and (not fault_valid or (reading and fault_hit))
                writing = incoming is not None and writable
                expected = data if bypass else slots[head % 32]
                self.assertEqual(int(valid), ctx.get(p["io_read_valid"]))
                self.assertEqual(int(writable), ctx.get(p["io_write_ready"]))
                for key, value in expected.items():
                    self.assertEqual(value, ctx.get(p["io_read_bits_entry_" + key]), key)
                expected_gpf = (gpaddr, nonleaf) if bypass else (
                    (fault_addr, fault_nonleaf) if fault_hit else (0, 0))
                self.assertEqual(expected_gpf, (ctx.get(p["io_read_bits_gpf_gpaddr"]),
                                                ctx.get(p["io_read_bits_gpf_isForVSnonLeafPTE"])))
                if not reset:
                    # Refill updates affect retained slots as well as queued
                    # entries; an enqueue owns its entire physical slot.
                    for index, stored in enumerate(slots):
                        if writing and index == tail % 32:
                            slots[index] = dict(data)
                        elif update is not None and not corrupt:
                            for lane in range(2):
                                if stored[f"vSetIdx_{lane}"] != vset:
                                    continue
                                if stored[f"ptag_{lane}"] == tag:
                                    stored[f"waymask_{lane}"] = mask
                                    stored[f"meta_codes_{lane}"] = tag.bit_count() % 2
                                elif stored[f"waymask_{lane}"] == mask:
                                    stored[f"waymask_{lane}"] = 0
                    if writing and any(data[f"itlb_exception_{lane}"] == 2 for lane in range(2)):
                        fault_valid = not (bypass and reading)
                        fault_slot, fault_addr, fault_nonleaf = tail % 64, gpaddr, nonleaf
                    elif flush:
                        fault_valid, fault_addr, fault_nonleaf = False, 0, 0
                    elif reading and fault_hit and not bypass:
                        fault_valid = False
                    head, tail = ((0, 0) if flush else (head + int(reading), tail + int(writing)))
                ctx.set(p["clock"], 1)
                await ctx.delay(1e-9)
                ctx.set(p["clock"], 0)
                await ctx.delay(1e-9)
                return writable, valid

            await step(reset=True)
            await step(entry(1), ready=True)  # Empty bypass consumes immediately.
            self.assertEqual(head % 64, tail % 64)
            for index in range(32):
                writable, _ = await step(entry(index + 10))
                self.assertTrue(writable)
            self.assertFalse((await step(entry(99), ready=True))[0])  # Full pop cannot enqueue.
            for index in range(90):
                await step(entry(index + 100), ready=True)
            for _ in range(32):
                await step(ready=True)
            await step(flush=True)
            sample = entry(45)
            sample.update(vSetIdx_0=17, vSetIdx_1=18, ptag_0=0x123456789, ptag_1=0x456789ABC,
                          waymask_0=3, waymask_1=6, meta_codes_0=0, meta_codes_1=1)
            await step(sample)
            await step(update=(17, 0x123456789, 9, False))  # Hit restores way and parity.
            await step(update=(18, 0xDEADBEEF, 6, False))  # Replacement clears only lane 1.
            await step(update=(17, 0x123456789, 4, True))
            await step(update=(99, 0x123456789, 4, False))
            await step(ready=True)
            await step(flush=True)
            # Write and update target the same retained slot; whole write wins.
            await step(sample, update=(17, 0xDEADBEEF, 3, False))
            await step(ready=True)
            await step(flush=True)
            fault = dict(sample, itlb_exception_1=2)
            await step(fault)
            self.assertFalse((await step(entry(77)))[0])
            self.assertTrue((await step(entry(78), ready=True))[0])  # Consume fault and replace.
            await step(ready=True)
            await step(fault, ready=True)  # GPF bypass never leaves a pending fault.
            self.assertFalse(fault_valid)
            await step(fault, flush=True)  # New capture wins over flush clearing.
            self.assertTrue(fault_valid)
            await step(flush=True)
            self.assertFalse(fault_valid)
            for cycle in range(500):
                data = {key: rng.getrandbits(width) for key, width in widths.items()}
                if cycle % 7:
                    data.update(itlb_exception_0=0, itlb_exception_1=0)
                selected = slots[rng.randrange(32)]
                lane = rng.randrange(2)
                update = (selected[f"vSetIdx_{lane}"],
                          selected[f"ptag_{lane}"] if cycle % 3 else rng.getrandbits(36),
                          rng.randrange(16), cycle % 11 == 0) if cycle % 4 == 0 else None
                await step(data if rng.randrange(4) else None, bool(rng.randrange(2)), update,
                           flush=cycle % 37 == 0, reset=cycle == 251,
                           gpaddr=rng.getrandbits(56), nonleaf=rng.randrange(2))

        sim = Simulator(dut)
        sim.add_testbench(bench)
        sim.run()


if __name__ == "__main__": unittest.main()
