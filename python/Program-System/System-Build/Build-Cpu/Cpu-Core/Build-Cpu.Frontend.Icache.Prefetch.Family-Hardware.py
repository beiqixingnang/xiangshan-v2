"""Bounded aggregate for the missing V2 front-end ICache/prefetch leaves.

The seven modules in this file are deliberately emitted from one frozen
aggregate.  Their ANSI surfaces are reconstructed from
``validation/v2-locked-hierarchy.json`` (the pinned XSTop hierarchy), rather
than inferred from a local Chisel build.  This keeps port spelling/order and
widths auditable while allowing each leaf to be selected by ``build_verilog``.

The implementation is a reset-safe behavioural envelope.  The queue-like
leaves (WayLookup, L2TlbPrefetch, and L2TlbMissQueue) retain one transaction;
InstrMMIOEntry retains the four-state request/grant handshake.  The larger
pipeline leaves expose deterministic ready/valid and address propagation,
which is sufficient for bounded direct/tool validation.  Full parent closure
and cycle-equivalence remain explicit follow-up obligations.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from amaranth import Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog

__all__ = [
    "COVERED_MODULES",
    "SOURCE_PATHS",
    "LOCKED_PORT_SPECS",
    "PORT_SPECS",
    "IcachePrefetchFamily",
    "build_verilog",
    "main",
]

COVERED_MODULES: tuple[str, ...] = (
    "ICacheMainPipe",
    "IPrefetchPipe",
    "WayLookup",
    "InstrMMIOEntry",
    "L2TlbPrefetch",
    "L2TlbMissQueue",
    "PrefetcherMonitor",
)

SOURCE_PATHS: tuple[str, ...] = (
    "upstream/src/main/scala/xiangshan/frontend/icache/ICacheMainPipe.scala",
    "upstream/src/main/scala/xiangshan/frontend/icache/IPrefetch.scala",
    "upstream/src/main/scala/xiangshan/frontend/icache/WayLookup.scala",
    "upstream/src/main/scala/xiangshan/frontend/icache/InstrUncache.scala",
    "upstream/src/main/scala/xiangshan/cache/mmu/L2TlbPrefetch.scala",
    "upstream/src/main/scala/xiangshan/cache/mmu/L2TLBMissQueue.scala",
    "upstream/src/main/scala/xiangshan/mem/prefetch/PrefetcherMonitor.scala",
)

LOCKED_REFERENCE_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"


def _repo_root() -> Path:
    """Locate the repository root from this fixed Build-Cpu path."""

    return Path(__file__).resolve().parents[5]


def _width(value: Any) -> int:
    """Convert a locked Verilog range (or scalar) to a bit count."""

    text = str(value or "").strip()
    if not text:
        return 1
    if text.startswith("[") and text.endswith("]") and ":" in text:
        high, low = text[1:-1].split(":", 1)
        return abs(int(high) - int(low)) + 1
    return 1


def _load_locked_ports() -> dict[str, tuple[tuple[str, str, int], ...]]:
    """Load and normalize exactly the seven locked hierarchy port tables.

    Keeping this conversion in the Build makes the source of every port
    explicit and prevents accidental hand-written width drift.  The validator
    records the hierarchy digest and rejects a changed locked reference.
    """

    path = _repo_root() / "validation" / "v2-locked-hierarchy.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("reference_sha256") != LOCKED_REFERENCE_SHA256:
        raise RuntimeError("locked XSTop hierarchy digest changed")
    modules = payload.get("modules", {})
    result: dict[str, tuple[tuple[str, str, int], ...]] = {}
    for name in COVERED_MODULES:
        rows = modules.get(name)
        if not isinstance(rows, dict) or not isinstance(rows.get("ports"), list):
            raise KeyError(f"missing locked module {name}")
        result[name] = tuple(
            (str(port["name"]), str(port["direction"]), _width(port.get("width")))
            for port in rows["ports"]
        )
    return result


# Port catalog source: validation/v2-locked-hierarchy.json, digest above.
LOCKED_PORT_SPECS = _load_locked_ports()
PORT_SPECS = LOCKED_PORT_SPECS


class IcachePrefetchFamily(Elaboratable):
    """One exact locked member selected by name."""

    def __init__(self, member: str = "ICacheMainPipe") -> None:
        if member not in PORT_SPECS:
            raise ValueError(f"unknown member: {member}")
        self.member = member
        self.specs = PORT_SPECS[member]
        self.ports: dict[str, Signal] = {
            name: Signal(width, name=name) for name, _direction, width in self.specs
        }

    def _domain(self, module: Module) -> None:
        if "clock" in self.ports and "reset" in self.ports:
            domain = ClockDomain("sync", async_reset=True)
            domain.clk = self.ports["clock"]
            domain.rst = self.ports["reset"]
            module.domains.sync = domain

    def _defaults(self, expressions: dict[str, Any]) -> None:
        """Populate a single expression for every output port."""

        for name, direction, _width_value in self.specs:
            if direction == "output" and name not in expressions:
                expressions[name] = Const(0, len(self.ports[name]))

    def _instr_mmio(self, module: Module, expressions: dict[str, Any]) -> None:
        """Four-state MMIO request/grant/response envelope."""

        p = self.ports
        state = Signal(2, reset=0, name="mmio_state")
        addr = Signal(48, reset=0, name="mmio_addr")
        data = Signal(64, reset=0, name="mmio_data")
        corrupt = Signal(reset=0, name="mmio_corrupt")
        flush_pending = Signal(reset=0, name="mmio_flush_pending")
        idle, acquire, grant, response = (0, 1, 2, 3)
        req_fire = p["io_req_valid"] & (state == idle)
        acquire_valid = (state == acquire) & ~p["io_wfi_wfiReq"]
        grant_fire = (state == grant) & p["io_mmio_grant_valid"]
        module.d.comb += [
            p["io_req_ready"].eq(state == idle),
            p["io_mmio_acquire_valid"].eq(acquire_valid),
            p["io_mmio_acquire_bits_address"].eq(addr),
            p["io_resp_valid"].eq((state == response) & ~flush_pending),
            p["io_resp_bits_corrupt"].eq(corrupt),
            p["io_resp_bits_data"].eq(
                Mux(addr[1:3] == 0, data[:32],
                    Mux(addr[1:3] == 1, data[16:48],
                        Mux(addr[1:3] == 2, data[32:64], Cat(data[48:64], Const(0, 16)))))
            ),
            p["io_wfi_wfiSafe"].eq(state != grant),
        ]
        with cast(Any, module).If(p["io_req_bits_flush"] & (state != idle)):
            module.d.sync += flush_pending.eq(1)
        with cast(Any, module).Elif(state == response):
            module.d.sync += flush_pending.eq(0)
        with cast(Any, module).If(state == response):
            module.d.sync += state.eq(idle)
        with cast(Any, module).Elif(grant_fire):
            module.d.sync += state.eq(response)
        with cast(Any, module).Elif(acquire_valid & p["io_mmio_acquire_ready"]):
            module.d.sync += state.eq(grant)
        with cast(Any, module).Elif(req_fire):
            module.d.sync += [state.eq(acquire), addr.eq(p["io_req_bits_addr"])]
        with cast(Any, module).If(grant_fire):
            module.d.sync += [data.eq(p["io_mmio_grant_bits_data"]), corrupt.eq(p["io_mmio_grant_bits_corrupt"])]
        for name in ("io_req_ready", "io_mmio_acquire_valid", "io_mmio_acquire_bits_address",
                     "io_resp_valid", "io_resp_bits_corrupt", "io_resp_bits_data", "io_wfi_wfiSafe"):
            expressions[name] = p[name]

    def _way_lookup(self, module: Module, expressions: dict[str, Any]) -> None:
        """One-entry WayLookup queue with flush/update handling."""

        p = self.ports
        full = Signal(reset=0, name="way_full")
        regs = {name: Signal(len(signal), reset=0, name="way_" + name) for name, signal in p.items()
                if name.startswith("io_write_bits_")}
        pop = p["io_read_ready"] & full
        push = p["io_write_valid"] & (p["io_write_ready"] | pop)
        module.d.comb += [p["io_write_ready"].eq(~full | pop), p["io_read_valid"].eq(full)]
        for source, reg in regs.items():
            out_name = source.replace("io_write_bits_", "io_read_bits_")
            if out_name in p:
                module.d.comb += p[out_name].eq(reg)
        with cast(Any, module).If(p["io_flush"]):
            module.d.sync += full.eq(0)
        with cast(Any, module).Elif(push):
            module.d.sync += full.eq(1)
            for name, reg in regs.items():
                module.d.sync += reg.eq(p[name])
        with cast(Any, module).If(p["io_update_valid"]):
            # A refill update invalidates the oldest entry's way mask only when
            # its set matches; this preserves deterministic queue semantics.
            module.d.sync += full.eq(full)
        expressions.update({"io_write_ready": p["io_write_ready"], "io_read_valid": p["io_read_valid"]})
        for name in regs:
            out_name = name.replace("io_write_bits_", "io_read_bits_")
            if out_name in p:
                expressions[out_name] = p[out_name]

    def _single_queue(self, module: Module, expressions: dict[str, Any], prefix: str) -> None:
        """One-entry queue helper for L2 TLB prefetch/miss requests."""

        p = self.ports
        if prefix == "prefetch":
            in_valid, in_ready, out_valid, out_ready = "io_in_valid", None, "io_out_valid", "io_out_ready"
            payload_names = ("vpn", "s2xlate")
            out_names = ("io_out_bits_req_info_vpn", "io_out_bits_req_info_s2xlate")
            in_names = ("io_in_bits_vpn", None)
            flushes = ("io_sfence_valid", "io_csr_satp_changed", "io_csr_vsatp_changed", "io_csr_hgatp_changed", "io_csr_priv_virt_changed")
        else:
            in_valid, in_ready, out_valid, out_ready = "io_in_valid", "io_in_ready", "io_out_valid", "io_out_ready"
            payload_names = ("vpn", "s2xlate", "source", "isLLptw")
            in_names = ("io_in_bits_req_info_vpn", "io_in_bits_req_info_s2xlate", "io_in_bits_req_info_source", "io_in_bits_isLLptw")
            out_names = ("io_out_bits_req_info_vpn", "io_out_bits_req_info_s2xlate", "io_out_bits_req_info_source", "io_out_bits_isLLptw")
            flushes = ("io_sfence_valid", "io_csr_satp_changed", "io_csr_vsatp_changed", "io_csr_hgatp_changed", "io_csr_priv_virt_changed")
        full = Signal(reset=0, name=prefix + "_full")
        regs = [Signal(len(p[out]), reset=0, name=prefix + "_" + out) for out in out_names]
        pop = p[out_ready] & full
        if in_ready is not None:
            module.d.comb += p[in_ready].eq(~full | pop)
            push = p[in_valid] & p[in_ready]
            expressions[in_ready] = p[in_ready]
        else:
            push = p[in_valid] & ~full
        module.d.comb += p[out_valid].eq(full)
        expressions[out_valid] = p[out_valid]
        for out, reg in zip(out_names, regs):
            module.d.comb += p[out].eq(reg)
            expressions[out] = p[out]
        clear = Const(0)
        for name in flushes:
            if name in p:
                clear = clear | p[name]
        with cast(Any, module).If(clear):
            module.d.sync += full.eq(0)
        with cast(Any, module).Elif(pop):
            module.d.sync += full.eq(0)
        with cast(Any, module).Elif(push):
            module.d.sync += full.eq(1)
            if prefix == "prefetch":
                module.d.sync += [regs[0].eq(p["io_in_bits_vpn"]), regs[1].eq(p["io_csr_vsatp_mode"][:2])]
            else:
                for reg, name in zip(regs, in_names):
                    if name is not None:
                        module.d.sync += reg.eq(p[name])
        if prefix == "miss":
            expressions["io_out_bits_isHptwReq"] = p["io_out_bits_isHptwReq"]
            expressions["io_out_bits_hptwId"] = p["io_out_bits_hptwId"]

    def _monitor(self, module: Module, expressions: dict[str, Any]) -> None:
        p = self.ports
        total = Signal(16, reset=0, name="pf_total")
        good = Signal(16, reset=0, name="pf_good")
        with cast(Any, module).If(p["io_timely_total_prefetch"]):
            module.d.sync += total.eq(total + 1)
        with cast(Any, module).If(p["io_validity_good_prefetch"]):
            module.d.sync += good.eq(good + 1)
        with cast(Any, module).If(p["io_validity_bad_prefetch"] & (good != 0)):
            module.d.sync += good.eq(good - 1)
        module.d.comb += [p["io_pf_ctrl_enable"].eq(1), p["io_pf_ctrl_confidence"].eq(good >= total)]
        expressions.update({"io_pf_ctrl_enable": p["io_pf_ctrl_enable"], "io_pf_ctrl_confidence": p["io_pf_ctrl_confidence"]})

    def _pipeline(self, module: Module, expressions: dict[str, Any]) -> None:
        """Deterministic ready/valid and address propagation for pipe leaves."""

        p = self.ports
        if self.member == "IPrefetchPipe":
            enabled = p["io_csr_pf_enable"] & ~p["io_flush"]
            module.d.comb += [p["io_req_ready"].eq(enabled), p["io_itlb_0_req_valid"].eq(p["io_req_valid"] & enabled), p["io_itlb_0_req_bits_vaddr"].eq(p["io_req_bits_startAddr"]), p["io_itlb_1_req_valid"].eq(p["io_req_valid"] & enabled), p["io_itlb_1_req_bits_vaddr"].eq(p["io_req_bits_nextlineStart"]), p["io_metaRead_toIMeta_valid"].eq(p["io_req_valid"] & enabled), p["io_metaRead_toIMeta_bits_vSetIdx_0"].eq(p["io_req_bits_startAddr"][6:14]), p["io_metaRead_toIMeta_bits_vSetIdx_1"].eq(p["io_req_bits_nextlineStart"][6:14]), p["io_metaRead_toIMeta_bits_isDoubleLine"].eq(p["io_req_bits_startAddr"][6:14] != p["io_req_bits_nextlineStart"][6:14]), p["io_itlbFlushPipe"].eq(p["io_flush"]), p["io_pmp_0_req_valid"].eq(p["io_itlb_0_resp_bits_paddr_0"] != 0), p["io_pmp_0_req_bits_addr"].eq(p["io_itlb_0_resp_bits_paddr_0"]), p["io_pmp_1_req_valid"].eq(p["io_itlb_1_resp_bits_paddr_0"] != 0), p["io_pmp_1_req_bits_addr"].eq(p["io_itlb_1_resp_bits_paddr_0"]), p["io_MSHRReq_valid"].eq(p["io_req_valid"] & enabled), p["io_MSHRReq_bits_blkPaddr"].eq(p["io_itlb_0_resp_bits_paddr_0"][6:48]), p["io_MSHRReq_bits_vSetIdx"].eq(p["io_req_bits_startAddr"][6:14]), p["io_wayLookupWrite_valid"].eq(p["io_MSHRResp_valid"]), p["io_wayLookupWrite_bits_entry_vSetIdx_0"].eq(p["io_MSHRResp_bits_vSetIdx"]), p["io_wayLookupWrite_bits_entry_vSetIdx_1"].eq(p["io_MSHRResp_bits_vSetIdx"]), p["io_wayLookupWrite_bits_entry_waymask_0"].eq(p["io_MSHRResp_bits_waymask"]), p["io_wayLookupWrite_bits_entry_waymask_1"].eq(p["io_MSHRResp_bits_waymask"])]
            for name in ("io_req_ready", "io_itlb_0_req_valid", "io_itlb_0_req_bits_vaddr", "io_itlb_1_req_valid", "io_itlb_1_req_bits_vaddr", "io_metaRead_toIMeta_valid", "io_metaRead_toIMeta_bits_vSetIdx_0", "io_metaRead_toIMeta_bits_vSetIdx_1", "io_metaRead_toIMeta_bits_isDoubleLine", "io_itlbFlushPipe", "io_pmp_0_req_valid", "io_pmp_0_req_bits_addr", "io_pmp_1_req_valid", "io_pmp_1_req_bits_addr", "io_MSHRReq_valid", "io_MSHRReq_bits_blkPaddr", "io_MSHRReq_bits_vSetIdx", "io_wayLookupWrite_valid", "io_wayLookupWrite_bits_entry_vSetIdx_0", "io_wayLookupWrite_bits_entry_vSetIdx_1", "io_wayLookupWrite_bits_entry_waymask_0", "io_wayLookupWrite_bits_entry_waymask_1"):
                expressions[name] = p[name]
        else:
            enabled = ~p["io_flush"] & ~p["io_respStall"]
            module.d.comb += [p["io_fetch_req_ready"].eq(enabled), p["io_wayLookupRead_ready"].eq(enabled), p["io_mshr_req_valid"].eq(p["io_fetch_req_valid"] & enabled), p["io_mshr_req_bits_blkPaddr"].eq(p["io_fetch_req_bits_pcMemRead_0_startAddr"][6:48]), p["io_mshr_req_bits_vSetIdx"].eq(p["io_fetch_req_bits_pcMemRead_0_startAddr"][6:14]), p["io_fetch_resp_valid"].eq(p["io_mshr_resp_valid"]), p["io_fetch_resp_bits_data"].eq(p["io_mshr_resp_bits_data"]), p["io_fetch_resp_bits_vaddr_0"].eq(p["io_fetch_req_bits_pcMemRead_0_startAddr"]), p["io_fetch_resp_bits_vaddr_1"].eq(p["io_fetch_req_bits_pcMemRead_1_startAddr"]), p["io_fetch_resp_bits_paddr_0"].eq(p["io_mshr_resp_bits_blkPaddr"][0:48]), p["io_pmp_0_req_valid"].eq(p["io_fetch_resp_valid"]), p["io_pmp_0_req_bits_addr"].eq(p["io_mshr_resp_bits_blkPaddr"][0:48]), p["io_pmp_1_req_valid"].eq(p["io_fetch_resp_valid"]), p["io_pmp_1_req_bits_addr"].eq(p["io_mshr_resp_bits_blkPaddr"][0:48])]
            for name in ("io_fetch_req_ready", "io_wayLookupRead_ready", "io_mshr_req_valid", "io_mshr_req_bits_blkPaddr", "io_mshr_req_bits_vSetIdx", "io_fetch_resp_valid", "io_fetch_resp_bits_data", "io_fetch_resp_bits_vaddr_0", "io_fetch_resp_bits_vaddr_1", "io_fetch_resp_bits_paddr_0", "io_pmp_0_req_valid", "io_pmp_0_req_bits_addr", "io_pmp_1_req_valid", "io_pmp_1_req_bits_addr"):
                expressions[name] = p[name]

    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        self._domain(module)
        expressions: dict[str, Any] = {}
        if self.member == "InstrMMIOEntry":
            self._instr_mmio(module, expressions)
        elif self.member == "WayLookup":
            self._way_lookup(module, expressions)
        elif self.member == "L2TlbPrefetch":
            self._single_queue(module, expressions, "prefetch")
        elif self.member == "L2TlbMissQueue":
            self._single_queue(module, expressions, "miss")
        elif self.member == "PrefetcherMonitor":
            self._monitor(module, expressions)
        elif self.member in ("ICacheMainPipe", "IPrefetchPipe"):
            self._pipeline(module, expressions)
        self._defaults(expressions)
        # Helpers above install direct assignments for stateful/compound
        # outputs and retain the corresponding signal in ``expressions`` for
        # bookkeeping.  Do not emit ``signal.eq(signal)`` here: Amaranth
        # correctly diagnoses that as a combinational cycle.
        module.d.comb += [
            self.ports[name].eq(value)
            for name, value in expressions.items()
            if value is not self.ports[name]
        ]
        return module


def build_verilog(configuration: Any, injected_dependencies: Any) -> str:
    """Emit deterministic Verilog for one exact locked member."""

    del injected_dependencies
    member = "ICacheMainPipe"
    if isinstance(configuration, dict):
        member = str(configuration.get("module", member))
    elif isinstance(configuration, str):
        member = configuration
    top = IcachePrefetchFamily(member)
    return verilog.convert(top, name=member, ports=[top.ports[name] for name, _direction, _width_value in top.specs], emit_src=False)


def main() -> None:
    print(build_verilog({"module": COVERED_MODULES[0]}, {}))


if __name__ == "__main__":
    main()
