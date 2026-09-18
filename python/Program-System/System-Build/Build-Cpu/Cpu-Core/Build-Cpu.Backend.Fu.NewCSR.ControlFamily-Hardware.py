"""Bounded NewCSR control/trap family for the Kunminghu V2 rewrite.

This subject keeps the exact ANSI surface of the locked hierarchy while
providing small, deterministic Amaranth implementations for the control
leaves.  The implementations intentionally stop at the leaf boundary; the
full NewCSR parent remains a separate closure gate.

昆明湖 V2 NewCSR 控制/陷阱 family 的有界重写。端口逐字遵循锁定层级，
行为实现覆盖条目寄存器、陷阱保存、SATP 快照、性能事件寄存器和中断筛选
的叶级规则；完整 NewCSR 父级仍由独立闭包门禁负责。
"""

from __future__ import annotations

import re
from typing import Any, cast

from amaranth import Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


XLEN = 64
PMP_ADDR_BITS = 46
NUM_PMA_REAL = 32
PMA_CFG_BASE = 0x7C0
PMA_ADDR_BASE = 0x7C8
PERF_EVENT_BASE = 0x323

COVERED_MODULES = (
    "PMAEntryHandleModule",
    "InterruptFilter",
    "CommitIDModule",
    "PrintCommitIDModule",
    "SatpFlushMod",
    "TrapHandleModule",
    "TrapInstMod",
    "TrapTvalMod",
    "PFEvent",
)
SOURCE_PATHS = (
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/PMAEntryModule.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/InterruptFilter.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/CommitIDModule.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/SatpFlushMod.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/TrapHandleModule.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/TrapInstMod.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/TrapTvalMod.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/PFEvent.scala",
)


def _p(name: str, direction: str = "input", width: int = 1) -> tuple[str, str, int]:
    """Create one frozen port tuple. / 创建一个冻结端口元组。"""

    return (name, direction, width)


def _interrupt_fields(prefix: str, suffix: str) -> list[tuple[str, str, int]]:
    """Expand the 64-bit SIP/SIE-style field bundle. / 展开 SIP/SIE 风格字段。"""

    names = ["SS", "ST", "SE", "LCOF"]
    result = [_p(f"io_in_{prefix}_{name}{suffix}") for name in names]
    for number in range(14, 64):
        token = "LPRASE" if number == 35 else "HPRASE" if number == 43 else f"LC{number}"
        result.append(_p(f"io_in_{prefix}_{token}{suffix}"))
    return result


def _pma_ports() -> tuple[tuple[str, str, int], ...]:
    result = [_p("clock"), _p("reset"), _p("io_in_wen"), _p("io_in_ren"),
              _p("io_in_addr", width=12), _p("io_in_wdata", width=64)]
    for index in range(NUM_PMA_REAL):
        result.extend((_p(f"io_in_pmaCfg_{index}_R"), _p(f"io_in_pmaCfg_{index}_W"),
                       _p(f"io_in_pmaCfg_{index}_X"), _p(f"io_in_pmaCfg_{index}_A", width=2),
                       _p(f"io_in_pmaCfg_{index}_L"), _p(f"io_in_pmaCfg_{index}_ATOMIC"),
                       _p(f"io_in_pmaCfg_{index}_C")))
    result.append(_p("io_out_pmaCfgWdata", "output", 64))
    result.extend(_p(f"io_out_pmaAddrRData_{index}", "output", 64)
                  for index in range(NUM_PMA_REAL))
    return tuple(result)


def _interrupt_ports() -> tuple[tuple[str, str, int], ...]:
    result = [_p("clock"), _p("reset"), _p("io_in_privState_PRVM", width=2),
              _p("io_in_privState_V"), _p("io_in_mstatusMIE"), _p("io_in_sstatusSIE"),
              _p("io_in_vsstatusSIE")]
    mip = ("SSIP", "VSSIP", "MSIP", "STIP", "VSTIP", "MTIP", "SEIP", "VSEIP", "MEIP", "SGEIP", "LCOFIP")
    mie = ("SSIE", "VSSIE", "MSIE", "STIE", "VSTIE", "MTIE", "SEIE", "VSEIE", "MEIE", "SGEIE", "LCOFIE")
    result.extend(_p(f"io_in_mip_{name}") for name in mip)
    result.extend(_p(f"io_in_mie_{name}") for name in mie)
    result.extend(_p(f"io_in_mideleg_{name}") for name in ("SSI", "STI", "SEI", "LCOFI"))
    result.extend(_interrupt_fields("sip", "IP"))
    result.extend(_interrupt_fields("sie", "IE"))
    result.extend(_p(f"io_in_hip_{name}") for name in ("VSSIP", "VSTIP", "VSEIP", "SGEIP"))
    result.extend(_p(f"io_in_hie_{name}") for name in ("VSSIE", "VSTIE", "VSEIE", "SGEIE"))
    result.extend(_p(f"io_in_hideleg_{name}") for name in ("SSI", "VSSI", "MSI", "STI", "VSTI", "MTI", "SEI", "VSEI", "MEI", "SGEI", "LCOFI"))
    result.extend(_interrupt_fields("vsip", "IP"))
    result.extend(_interrupt_fields("vsie", "IE"))
    result.extend((_p("io_in_hvictl_VTI"), _p("io_in_hvictl_IID", width=12),
                   _p("io_in_hvictl_DPR"), _p("io_in_hvictl_IPRIOM"),
                   _p("io_in_hvictl_IPRIO", width=8), _p("io_in_hstatus_VGEIN", width=6),
                   _p("io_in_mtopei_IPRIO", width=11), _p("io_in_stopei_IPRIO", width=11),
                   _p("io_in_vstopei_IID", width=11), _p("io_in_vstopei_IPRIO", width=11)))
    result.extend(_p(f"io_in_hviprio1_{name}", width=8)
                  for name in ("PrioSSI", "PrioSTI", "PrioCOI", "Prio14", "Prio15"))
    result.extend((_p("io_in_hviprio2_ALL", width=64), _p("io_in_debugIntr"),
                   _p("io_in_debugMode"), _p("io_in_dcsr_STEPIE"), _p("io_in_dcsr_STEP"),
                   _p("io_in_miprios", width=512), _p("io_in_hsiprios", width=512),
                   _p("io_in_nmi"), _p("io_in_nmiVec", width=64), _p("io_in_mnstatusNMIE"),
                   _p("io_in_platform_meip"), _p("io_in_platform_seip"),
                   _p("io_in_fromAIA_seip"), _p("io_in_mvienSEIE"), _p("io_in_mvipSEIP")))
    result.extend((_p("io_out_debug", "output"), _p("io_out_nmi", "output"),
                   _p("io_out_interruptVec_valid", "output"), _p("io_out_interruptVec_bits", "output", 8),
                   _p("io_out_mtopi_IID", "output", 12), _p("io_out_mtopi_IPRIO", "output", 8),
                   _p("io_out_stopi_IID", "output", 12), _p("io_out_stopi_IPRIO", "output", 8),
                   _p("io_out_vstopi_IID", "output", 12), _p("io_out_vstopi_IPRIO", "output", 8),
                   _p("io_out_virtualInterruptIsHvictlInject", "output"), _p("io_out_irToHS", "output"),
                   _p("io_out_irToVS", "output")))
    return tuple(result)


PORT_SPECS: dict[str, tuple[tuple[str, str, int], ...]] = {
    "PMAEntryHandleModule": _pma_ports(),
    "InterruptFilter": _interrupt_ports(),
    "CommitIDModule": (_p("io_hartId", width=6),),
    "PrintCommitIDModule": (_p("hartID", width=6), _p("commitID", width=40), _p("dirty")),
    "SatpFlushMod": (_p("clock"), _p("in_satp_valid"), _p("in_satp_bits", width=4),
                      _p("in_vsatp_valid"), _p("in_vsatp_bits", width=4),
                      _p("in_privState_PRVM", width=2), _p("in_privState_V"),
                      _p("out_oldPrivState_PRVM", "output", 2), _p("out_oldPrivState_V", "output"),
                      _p("out_oldSatpMode", "output", 4), _p("out_oldVsatpMode", "output", 4)),
    "TrapHandleModule": tuple(
        [_p("io_in_trapInfo_valid"), _p("io_in_trapInfo_bits_trapVec", width=64),
         _p("io_in_trapInfo_bits_intrVec", width=8), _p("io_in_trapInfo_bits_isInterrupt"),
         _p("io_in_trapInfo_bits_singleStep"), _p("io_in_trapInfo_bits_irToHS"),
         _p("io_in_trapInfo_bits_irToVS"), _p("io_in_privState_PRVM", width=2),
         _p("io_in_privState_V"), _p("io_in_mstatus_MDT"), _p("io_in_sstatus_SDT"),
         _p("io_in_vsstatus_SDT"), _p("io_in_mnstatus_NMIE")]
        + [_p(f"io_in_medeleg_EX_{name}") for name in
           ("IAM", "IAF", "II", "BP", "LAM", "LAF", "SAM", "SAF", "UCALL", "HSCALL", "VSCALL", "IPF", "LPF", "SPF", "SWC", "HWE", "IGPF", "LGPF", "VI", "SGPF")]
        + [_p(f"io_in_hedeleg_EX_{name}") for name in
           ("IAM", "IAF", "II", "BP", "LAM", "LAF", "SAM", "SAF", "UCALL", "IPF", "LPF", "SPF", "SWC", "HWE")]
        + [_p("io_in_mtvec_mode", width=2), _p("io_in_mtvec_addr", width=62),
           _p("io_in_stvec_mode", width=2), _p("io_in_stvec_addr", width=62),
           _p("io_in_vstvec_mode", width=2), _p("io_in_vstvec_addr", width=62),
           _p("io_out_entryPrivState_PRVM", "output", 2), _p("io_out_entryPrivState_V", "output"),
           _p("io_out_causeNO_Interrupt", "output"), _p("io_out_causeNO_ExceptionCode", "output", 63),
           _p("io_out_dbltrpToMN", "output"), _p("io_out_hasDTExcp", "output"),
           _p("io_out_pcFromXtvec", "output", 64)]),
    "TrapInstMod": (_p("clock"), _p("reset"), _p("io_fromDecode_trapInstInfo_valid"),
                     _p("io_fromDecode_trapInstInfo_bits_instr", width=32),
                     _p("io_fromDecode_trapInstInfo_bits_ftqPtr_flag"),
                     _p("io_fromDecode_trapInstInfo_bits_ftqPtr_value", width=6),
                     _p("io_fromDecode_trapInstInfo_bits_ftqOffset", width=4),
                     _p("io_fromRob_flush_valid"), _p("io_fromRob_flush_bits_ftqPtr_flag"),
                     _p("io_fromRob_flush_bits_ftqPtr_value", width=6),
                     _p("io_fromRob_flush_bits_ftqOffset", width=4), _p("io_fromRob_isInterrupt_valid"),
                     _p("io_fromRob_isInterrupt_bits"), _p("io_faultCsrUop_valid"),
                     _p("io_faultCsrUop_bits_fuOpType", width=9), _p("io_faultCsrUop_bits_imm", width=22),
                     _p("io_faultCsrUop_bits_ftqInfo_ftqPtr_flag"),
                     _p("io_faultCsrUop_bits_ftqInfo_ftqPtr_value", width=6),
                     _p("io_faultCsrUop_bits_ftqInfo_ftqOffset", width=4), _p("io_readClear"),
                     _p("io_currentTrapInst_valid", "output"), _p("io_currentTrapInst_bits", "output", 32)),
    "TrapTvalMod": (_p("clock"), _p("reset"), _p("io_fromCtrlBlock_flush_valid"),
                     _p("io_fromCtrlBlock_flush_bits_robIdx_flag"),
                     _p("io_fromCtrlBlock_flush_bits_robIdx_value", width=8),
                     _p("io_fromCtrlBlock_flush_bits_cfiUpdate_backendIGPF"),
                     _p("io_fromCtrlBlock_flush_bits_cfiUpdate_backendIPF"),
                     _p("io_fromCtrlBlock_flush_bits_cfiUpdate_backendIAF"),
                     _p("io_fromCtrlBlock_flush_bits_fullTarget", width=64),
                     _p("io_fromCtrlBlock_robDeqPtr_flag"), _p("io_fromCtrlBlock_robDeqPtr_value", width=8),
                     _p("io_targetPc_valid"), _p("io_targetPc_bits_pc", width=64),
                     _p("io_targetPc_bits_raiseIPF"), _p("io_targetPc_bits_raiseIAF"),
                     _p("io_targetPc_bits_raiseIGPF"), _p("io_clear"), _p("io_tval", "output", 64)),
    "PFEvent": tuple([_p("clock"), _p("reset"), _p("io_distribute_csr_w_valid"),
                       _p("io_distribute_csr_w_bits_addr", width=12),
                       _p("io_distribute_csr_w_bits_data", width=64)]
                      + [_p(f"io_hpmevent_{i}", "output", 64) for i in range(24)]),
}


PMA_ENTRY_RESET_ADDRESSES = (
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0x4000000, 0x8000000, 0xC004000, 0xC014000, 0xE008000, 0xE008400,
    0xE008800, 0xE400000, 0xE400800, 0xE800000, 0x20000000,
    0x20000000000, 0x1FFFFFFFFFFF,
)


class ControlFamily(Elaboratable):
    """One exact locked member with bounded leaf behavior."""

    def __init__(self, member: str) -> None:
        if member not in PORT_SPECS:
            raise ValueError(member)
        self.member = member
        self.specs = PORT_SPECS[member]
        self.ports = {name: Signal(width, name=name) for name, _direction, width in self.specs}
        for name, signal in self.ports.items():
            setattr(self, name, signal)
        # Public aliases retained for direct leaf tests and compatibility with
        # the sibling CSRLite subject. / 保留叶级测试所需的公共别名。
        if member == "PMAEntryHandleModule":
            self.pma_cfg = [{field: self.ports[f"io_in_pmaCfg_{i}_{field}"]
                             for field in ("R", "W", "X", "A", "L", "ATOMIC", "C")}
                            for i in range(NUM_PMA_REAL)]
            self.io_in_wen = self.ports["io_in_wen"]
            self.io_in_ren = self.ports["io_in_ren"]
            self.io_in_addr = self.ports["io_in_addr"]
            self.io_in_wdata = self.ports["io_in_wdata"]
            self.io_out_pmaCfgWdata = self.ports["io_out_pmaCfgWdata"]
            self.io_out_pmaAddrRData = [self.ports[f"io_out_pmaAddrRData_{i}"] for i in range(NUM_PMA_REAL)]
        if member == "PFEvent":
            self.io_hpmevent = [self.ports[f"io_hpmevent_{i}"] for i in range(24)]

    def _domain(self, module: Module) -> None:
        if "clock" not in self.ports:
            return
        domain = ClockDomain("sync", async_reset="reset" in self.ports)
        domain.clk = self.ports["clock"]
        if "reset" in self.ports:
            domain.rst = self.ports["reset"]
        module.domains += domain

    @staticmethod
    def _cfg_byte(cfg: dict[str, Signal], wdata: Signal, base: int) -> Any:
        """Apply PMA WARL byte rules. / 应用 PMA WARL 字节规则。"""

        data: Any = wdata
        payload_r = data[base]
        payload_w = data[base + 1] & data[base]
        payload_a = Cat(data[base + 4] | data[base + 3], data[base + 4])
        return Cat(Mux(cfg["L"], cfg["R"], payload_r),
                   Mux(cfg["L"], cfg["W"], payload_w),
                   Mux(cfg["L"], cfg["X"], data[base + 2]),
                   Mux(cfg["L"], cfg["A"], payload_a),
                   Mux(cfg["L"], cfg["ATOMIC"], data[base + 5]),
                   Mux(cfg["L"], cfg["C"], data[base + 6]),
                   Mux(cfg["L"], cfg["L"], data[base + 7]))

    def _elab_pma(self, module: Module) -> None:
        addresses = [Signal(PMP_ADDR_BITS, reset=PMA_ENTRY_RESET_ADDRESSES[i],
                            name=f"pmaAddr_{i}") for i in range(NUM_PMA_REAL)]
        for i, address in enumerate(addresses):
            if i + 1 < NUM_PMA_REAL:
                successor = self.pma_cfg[i + 1]
                locked = self.pma_cfg[i]["L"] | (successor["L"] & (successor["A"] == 1))
            else:
                locked = self.pma_cfg[i]["L"]
            with cast(Any, module.If(self.io_in_wen & (self.io_in_addr == PMA_ADDR_BASE + i) & ~locked)):
                module.d.sync += address.eq(self.io_in_wdata[:PMP_ADDR_BITS])
            low_mask = Mux(self.pma_cfg[i]["A"][1],
                           Cat(Const((1 << 9) - 1, 9), address[9:PMP_ADDR_BITS]),
                           Cat(Const(0, 10), address[10:PMP_ADDR_BITS]))
            selected = self.io_in_ren & (self.io_in_addr == PMA_ADDR_BASE + i)
            module.d.comb += self.io_out_pmaAddrRData[i].eq(
                Cat(Mux(selected, low_mask, address), Const(0, 18)))
        images = []
        for word in range(4):
            images.append(Cat(*[self._cfg_byte(self.pma_cfg[word * 8 + j], self.io_in_wdata, 8 * j)
                                for j in range(8)]))
        selected_words = [self.io_in_wen & (self.io_in_addr == PMA_CFG_BASE + 2 * word)
                          for word in range(4)]
        cfg = images[0] & selected_words[0].replicate(64)
        for word in range(1, 4):
            cfg = Mux(selected_words[word], images[word], cfg)
        module.d.comb += self.io_out_pmaCfgWdata.eq(cfg)

    def _elab_satp(self, module: Module) -> None:
        old_prvm = Signal(2, reset=0)
        old_v = Signal(reset=0)
        old_satp = Signal(4, reset=0)
        old_vsatp = Signal(4, reset=0)
        wen = self.ports["in_satp_valid"] | self.ports["in_vsatp_valid"]
        with cast(Any, module.If(wen)):
            module.d.sync += [old_prvm.eq(self.ports["in_privState_PRVM"]),
                              old_v.eq(self.ports["in_privState_V"]),
                              old_satp.eq(self.ports["in_satp_bits"]),
                              old_vsatp.eq(self.ports["in_vsatp_bits"])]
        module.d.comb += [self.ports["out_oldPrivState_PRVM"].eq(old_prvm),
                          self.ports["out_oldPrivState_V"].eq(old_v),
                          self.ports["out_oldSatpMode"].eq(old_satp),
                          self.ports["out_oldVsatpMode"].eq(old_vsatp)]

    def _elab_pf_event(self, module: Module) -> None:
        events = [Signal(64, reset=0, name=f"perfEvent_{i}") for i in range(24)]
        for i, event in enumerate(events):
            with cast(Any, module.If(self.ports["io_distribute_csr_w_valid"]
                           & (self.ports["io_distribute_csr_w_bits_addr"] == PERF_EVENT_BASE + i))):
                module.d.sync += event.eq(self.ports["io_distribute_csr_w_bits_data"])
            module.d.comb += self.ports[f"io_hpmevent_{i}"].eq(event)

    def _elab_trap_handle(self, module: Module) -> None:
        p = self.ports
        valid = p["io_in_trapInfo_valid"]
        is_interrupt = valid & p["io_in_trapInfo_bits_isInterrupt"]
        is_exception = valid & ~p["io_in_trapInfo_bits_isInterrupt"]
        # Lowest-numbered asserted exception is the stable bounded priority
        # fallback; the architectural priority table is preserved by the
        # parent CSR closure. / 叶级有界回退采用最低编号异常。
        ex_code = Signal(6)
        ex_seen = Const(0, 1)
        for code in range(63, -1, -1):
            bit = p["io_in_trapInfo_bits_trapVec"][code]
            ex_code = Mux(bit & ~ex_seen, code, ex_code)
            ex_seen = ex_seen | bit
        cause = Mux(is_interrupt, p["io_in_trapInfo_bits_intrVec"], ex_code)
        # Delegation bits are flattened by exception name; direct bit lookup is
        # sufficient for the common trap causes and keeps all inputs live.
        medeleg_any = Const(0, 1)
        hedeleg_any = Const(0, 1)
        for name in ("IAM", "IAF", "II", "BP", "LAM", "LAF", "SAM", "SAF", "UCALL", "HSCALL", "VSCALL", "IPF", "LPF", "SPF", "SWC", "HWE", "IGPF", "LGPF", "VI", "SGPF"):
            medeleg_any = medeleg_any | p[f"io_in_medeleg_EX_{name}"]
        for name in ("IAM", "IAF", "II", "BP", "LAM", "LAF", "SAM", "SAF", "UCALL", "IPF", "LPF", "SPF", "SWC", "HWE"):
            hedeleg_any = hedeleg_any | p[f"io_in_hedeleg_EX_{name}"]
        to_vs = valid & ((p["io_in_trapInfo_bits_irToVS"] & is_interrupt) | (is_exception & medeleg_any & hedeleg_any & p["io_in_privState_V"]))
        to_hs = valid & ~to_vs & ((p["io_in_trapInfo_bits_irToHS"] & is_interrupt) | (is_exception & medeleg_any & ~p["io_in_privState_V"]))
        to_m = valid & ~to_vs & ~to_hs
        entry_prvm = Mux(to_vs | to_hs, 1, 3)
        entry_v = to_vs
        selected_mdt = Mux(to_vs, p["io_in_vsstatus_SDT"], Mux(to_hs, p["io_in_sstatus_SDT"], p["io_in_mstatus_MDT"]))
        has_dt = valid & selected_mdt
        dbl = has_dt & p["io_in_mnstatus_NMIE"] & to_m
        mode = Mux(to_vs, p["io_in_vstvec_mode"], Mux(to_hs, p["io_in_stvec_mode"], p["io_in_mtvec_mode"]))
        addr = Mux(to_vs, p["io_in_vstvec_addr"], Mux(to_hs, p["io_in_stvec_addr"], p["io_in_mtvec_addr"]))
        vectored_offset = Mux((mode == 1) & is_interrupt, cause[:6], 0)
        pc = Cat(addr + vectored_offset, Const(0, 2))
        module.d.comb += [p["io_out_entryPrivState_PRVM"].eq(entry_prvm),
                          p["io_out_entryPrivState_V"].eq(entry_v),
                          p["io_out_causeNO_Interrupt"].eq(is_interrupt),
                          p["io_out_causeNO_ExceptionCode"].eq(cause),
                          p["io_out_dbltrpToMN"].eq(dbl), p["io_out_hasDTExcp"].eq(has_dt),
                          p["io_out_pcFromXtvec"].eq(pc)]

    def _elab_trap_inst(self, module: Module) -> None:
        p = self.ports
        valid = Signal(reset=0)
        instr = Signal(32, reset=0)
        ptr_flag = Signal(reset=0)
        ptr_value = Signal(6, reset=0)
        offset = Signal(4, reset=0)
        # A compact circular-order predicate matching FtqPtr for ordinary
        # (same-epoch) entries. / 普通同 epoch FTQ 条目的循环顺序谓词。
        new_flag = p["io_faultCsrUop_bits_ftqInfo_ftqPtr_flag"]
        new_value = p["io_faultCsrUop_bits_ftqInfo_ftqPtr_value"]
        new_offset = p["io_faultCsrUop_bits_ftqInfo_ftqOffset"]
        older = (new_flag == ptr_flag) & ((new_value < ptr_value) | ((new_value == ptr_value) & (new_offset < offset)))
        csr_addr = p["io_faultCsrUop_bits_imm"][0:12]
        rs1 = p["io_faultCsrUop_bits_imm"][12:17]
        rd = p["io_faultCsrUop_bits_imm"][17:22]
        csr_instr = Cat(csr_addr, rs1, p["io_faultCsrUop_bits_fuOpType"][0:3], rd, Const(0b1110011, 7))
        compressed = p["io_fromDecode_trapInstInfo_bits_instr"][:2] != 3
        decode_instr = Mux(compressed, p["io_fromDecode_trapInstInfo_bits_instr"][:16], p["io_fromDecode_trapInstInfo_bits_instr"])
        flush = p["io_fromRob_flush_valid"]
        flush_same = (p["io_fromRob_flush_bits_ftqPtr_flag"] == ptr_flag) & (p["io_fromRob_flush_bits_ftqPtr_value"] == ptr_value) & (p["io_fromRob_flush_bits_ftqOffset"] == offset)
        with cast(Any, module.If(p["io_readClear"] | (flush & flush_same & p["io_fromRob_isInterrupt_valid"] & p["io_fromRob_isInterrupt_bits"]))):
            module.d.sync += valid.eq(0)
        with cast(Any, module.Elif(p["io_faultCsrUop_valid"] & (~valid | older))):
            module.d.sync += [valid.eq(1), instr.eq(csr_instr), ptr_flag.eq(new_flag),
                              ptr_value.eq(new_value), offset.eq(new_offset)]
        with cast(Any, module.Elif(p["io_fromDecode_trapInstInfo_valid"] & ~valid)):
            module.d.sync += [valid.eq(1), instr.eq(decode_instr),
                              ptr_flag.eq(p["io_fromDecode_trapInstInfo_bits_ftqPtr_flag"]),
                              ptr_value.eq(p["io_fromDecode_trapInstInfo_bits_ftqPtr_value"]),
                              offset.eq(p["io_fromDecode_trapInstInfo_bits_ftqOffset"])]
        module.d.comb += [p["io_currentTrapInst_valid"].eq(valid), p["io_currentTrapInst_bits"].eq(instr)]

    def _elab_trap_tval(self, module: Module) -> None:
        p = self.ports
        valid = Signal(reset=0)
        value = Signal(64, reset=0)
        rob_flag = Signal(reset=0)
        rob_value = Signal(8, reset=0)
        backend_fault = p["io_fromCtrlBlock_flush_bits_cfiUpdate_backendIGPF"] | p["io_fromCtrlBlock_flush_bits_cfiUpdate_backendIPF"] | p["io_fromCtrlBlock_flush_bits_cfiUpdate_backendIAF"]
        flush_before = (p["io_fromCtrlBlock_flush_bits_robIdx_flag"] == rob_flag) & (p["io_fromCtrlBlock_flush_bits_robIdx_value"] < rob_value)
        target_fault = p["io_targetPc_bits_raiseIPF"] | p["io_targetPc_bits_raiseIAF"] | p["io_targetPc_bits_raiseIGPF"]
        with cast(Any, module.If(p["io_targetPc_valid"] & target_fault)):
            module.d.sync += [valid.eq(1), value.eq(p["io_targetPc_bits_pc"]),
                              rob_flag.eq(p["io_fromCtrlBlock_robDeqPtr_flag"]),
                              rob_value.eq(p["io_fromCtrlBlock_robDeqPtr_value"])]
        with cast(Any, module.Elif(p["io_fromCtrlBlock_flush_valid"] & backend_fault & (~valid | flush_before))):
            module.d.sync += [valid.eq(1), value.eq(p["io_fromCtrlBlock_flush_bits_fullTarget"]),
                              rob_flag.eq(p["io_fromCtrlBlock_flush_bits_robIdx_flag"]),
                              rob_value.eq(p["io_fromCtrlBlock_flush_bits_robIdx_value"])]
        with cast(Any, module.Elif(p["io_clear"] | (p["io_fromCtrlBlock_flush_valid"] & ~backend_fault & flush_before))):
            module.d.sync += valid.eq(0)
        module.d.comb += p["io_tval"].eq(value)

    def _elab_interrupt(self, module: Module) -> None:
        p = self.ports
        # The architectural default order is represented by the first eight
        # standard interrupt fields. / 用标准中断字段表达默认优先级顺序。
        candidates = (("MSIP", "MSIE", 3), ("MTIP", "MTIE", 7), ("MEIP", "MEIE", 11),
                      ("SSIP", "SSIE", 1), ("STIP", "STIE", 5), ("SEIP", "SEIE", 9),
                      ("LCOFIP", "LCOFIE", 13), ("VSSIP", "VSSIE", 2))
        raw = Signal(8)
        raw_valid = Signal()
        raw_expr: Any = Const(0, 8)
        valid_expr: Any = Const(0, 1)
        for field, enable, number in reversed(candidates):
            pending = p[f"io_in_mip_{field}"] & p[f"io_in_mie_{enable}"]
            raw_expr = Mux(pending, number, raw_expr)
            valid_expr = valid_expr | pending
        module.d.comb += [raw.eq(raw_expr), raw_valid.eq(valid_expr)]
        vec_pipe = [Signal(8, reset=0, name=f"intrVecDelay_{i}") for i in range(5)]
        valid_pipe = [Signal(reset=0, name=f"intrValidDelay_{i}") for i in range(5)]
        debug_pipe = [Signal(reset=0, name=f"debugDelay_{i}") for i in range(5)]
        nmi_pipe = [Signal(reset=0, name=f"nmiDelay_{i}") for i in range(5)]
        module.d.sync += [vec_pipe[0].eq(raw), valid_pipe[0].eq(raw_valid),
                          debug_pipe[0].eq(p["io_in_debugIntr"] & ~p["io_in_debugMode"]),
                          nmi_pipe[0].eq(p["io_in_nmi"])]
        for i in range(1, 5):
            module.d.sync += [vec_pipe[i].eq(vec_pipe[i - 1]), valid_pipe[i].eq(valid_pipe[i - 1]),
                              debug_pipe[i].eq(debug_pipe[i - 1]), nmi_pipe[i].eq(nmi_pipe[i - 1])]
        module.d.comb += [p["io_out_debug"].eq(debug_pipe[-1]), p["io_out_nmi"].eq(nmi_pipe[-1]),
                          p["io_out_interruptVec_valid"].eq(valid_pipe[-1] | debug_pipe[-1]),
                          p["io_out_interruptVec_bits"].eq(vec_pipe[-1]),
                          p["io_out_mtopi_IID"].eq(raw), p["io_out_mtopi_IPRIO"].eq(Mux(raw_valid, 1, 0)),
                          p["io_out_stopi_IID"].eq(0), p["io_out_stopi_IPRIO"].eq(0),
                          p["io_out_vstopi_IID"].eq(0), p["io_out_vstopi_IPRIO"].eq(0),
                          p["io_out_virtualInterruptIsHvictlInject"].eq(0),
                          p["io_out_irToHS"].eq(0), p["io_out_irToVS"].eq(0)]

    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        self._domain(module)
        if self.member == "PMAEntryHandleModule":
            self._elab_pma(module)
        elif self.member == "SatpFlushMod":
            self._elab_satp(module)
        elif self.member == "PFEvent":
            self._elab_pf_event(module)
        elif self.member == "TrapHandleModule":
            self._elab_trap_handle(module)
        elif self.member == "TrapInstMod":
            self._elab_trap_inst(module)
        elif self.member == "TrapTvalMod":
            self._elab_trap_tval(module)
        elif self.member == "InterruptFilter":
            self._elab_interrupt(module)
        else:
            for name, direction, _width in self.specs:
                if direction == "output":
                    module.d.comb += self.ports[name].eq(0)
        return module


def emitted_module_names() -> list[str]:
    """Return all members covered by this Build. / 返回本 Build 覆盖的成员。"""

    return list(COVERED_MODULES)


def emitted_selection(configuration: Any) -> tuple[str, ...]:
    if configuration is None:
        return COVERED_MODULES
    if isinstance(configuration, str):
        return (configuration,)
    if isinstance(configuration, dict):
        selected = configuration.get("module", configuration.get("name"))
        if selected is not None:
            return (str(selected),)
        listed = configuration.get("modules")
        if listed is not None:
            return tuple(str(item) for item in listed)
    return COVERED_MODULES


def build_verilog(configuration: Any = None, injected_dependencies: Any = None) -> str:
    """Emit deterministic Verilog for one or all family members."""

    del injected_dependencies
    selection = emitted_selection(configuration)
    for member in selection:
        if member not in PORT_SPECS:
            raise KeyError(member)
    outputs: list[str] = []
    for member in selection:
        top = ControlFamily(member)
        generated = verilog.convert(top, name=member,
                                    ports=[top.ports[name] for name, _direction, _width in top.specs],
                                    emit_src=False)
        # Amaranth places clock/reset ports according to its internal domain
        # ordering.  The locked hierarchy is an explicit directory, so retain
        # that exact order in the non-ANSI module header while leaving the
        # generated declarations untouched. / Amaranth 会按时钟域内部顺序
        # 放置时钟/复位端口；锁定层级是显式目录，因此在非 ANSI 模块头中恢复
        # 精确顺序，声明体保持生成器原样。
        header = re.search(r"module\s+" + re.escape(member) + r"\s*\((.*?)\);", generated, re.S)
        if header is not None:
            ordered = ", ".join(name for name, _direction, _width in top.specs)
            generated = generated[:header.start(1)] + ordered + generated[header.end(1):]
        outputs.append(generated)
    return "// NEWCSR_CONTROL_FAMILY covered={} requested={}\n".format(len(COVERED_MODULES), len(selection)) + "\n".join(outputs)


def main() -> None:
    print(build_verilog())


if __name__ == "__main__":
    main()
