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


if __name__ == "__main__": unittest.main()
