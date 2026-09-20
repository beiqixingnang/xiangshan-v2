# pyright: reportGeneralTypeIssues=false, reportAttributeAccessIssue=false

"""Bounded XiangShan backend/small-control aggregate with locked V2 ports.

带锁定 V2 端口面的香山后端小控制有界聚合。

This aggregate keeps the eight residual leaf contracts in one deterministic
Build entry.  Port names, directions, and widths are taken from the pinned V2
XSTop hierarchy (digest ``8f279a...b473d``); the implementations below are
deliberately bounded behavioural envelopes until the reference differential
and parent-closure gates are run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amaranth import Array, Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog

__all__ = [
    "PortSpec",
    "COVERED_MODULES",
    "COMPATIBILITY_MEMBERS",
    "SOURCE_PATHS",
    "LOCKED_REFERENCE_SHA256",
    "LOCKED_PORT_SPECS",
    "PORT_SPECS",
    "BackendSmallControlFamily",
    "SmallControlFamily",
    "build_verilog",
    "main",
]

# Module Contract
# Locked V2 source/port identity is declared above and below. / 上下文声明锁定 V2 来源与端口身份。


@dataclass(frozen=True)
class PortSpec:
    """One locked ANSI port tuple. / 一个锁定 ANSI 端口元组。"""

    name: str
    direction: str
    width: int


COVERED_MODULES: tuple[str, ...] = (
    "AddrAddModule",
    "GPAMem",
    "RedirectGenerator",
    "RegCache",
    "RegCacheTagTable",
    "RASStack",
    "FauFTBWay",
    "VectorCvtTop",
)

# These adapters remain import-compatible, but strict ownership belongs to
# Build-Cpu.Backend.FinalTwo.Family and must not be claimed twice.
COMPATIBILITY_MEMBERS: tuple[str, ...] = (
    "DatamoduleResultBuffer",
    "RegionWays",
)

SOURCE_PATHS: tuple[str, ...] = (
    "upstream/src/main/scala/xiangshan/backend/fu/wrapper/BranchUnit.scala",
    "upstream/src/main/scala/xiangshan/mem/sbuffer/DatamoduleResultBuffer.scala",
    "upstream/src/main/scala/xiangshan/backend/GPAMem.scala",
    "upstream/src/main/scala/xiangshan/backend/ctrlblock/RedirectGenerator.scala",
    "upstream/src/main/scala/xiangshan/backend/regcache/RegCache.scala",
    "upstream/src/main/scala/xiangshan/backend/regcache/RegCacheTagTable.scala",
    "upstream/src/main/scala/xiangshan/frontend/ITTAGE.scala",
    "upstream/src/main/scala/xiangshan/frontend/newRAS.scala",
    "upstream/src/main/scala/xiangshan/frontend/FauFTB.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/wrapper/VCVT.scala",
)

LOCKED_REFERENCE_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"


# Create one normalized port record. / 创建一个规范化端口记录。
def _p(name: str, direction: str, width: int = 1) -> PortSpec:
    """Create a normalized port specification. / 创建规范化端口规格。"""

    return PortSpec(name, direction, width)


# Build the exact locked port catalog. / 构建精确锁定端口目录。
def _build_port_specs() -> dict[str, tuple[PortSpec, ...]]:
    """Build the explicit locked XSTop port catalog. / 构建显式锁定 XSTop 端口目录。"""

    addr = (
        _p("io_pcExtend", "input", 51), _p("io_taken", "input"),
        _p("io_imm", "input", 32), _p("io_target", "output", 64),
        _p("io_nextPcOffset", "input", 5),
    )
    data_buffer: list[PortSpec] = [_p("clock", "input"), _p("reset", "input")]
    for i in range(2):
        data_buffer.extend((
            _p(f"io_enq_{i}_ready", "output"), _p(f"io_enq_{i}_valid", "input"),
            _p(f"io_enq_{i}_bits_addr", "input", 48), _p(f"io_enq_{i}_bits_vaddr", "input", 50),
            _p(f"io_enq_{i}_bits_data", "input", 128), _p(f"io_enq_{i}_bits_mask", "input", 16),
            _p(f"io_enq_{i}_bits_wline", "input"), _p(f"io_enq_{i}_bits_sqPtr_value", "input", 6),
            _p(f"io_enq_{i}_bits_vecValid", "input"),
        ))
        if i == 0:
            data_buffer.append(_p("io_enq_0_bits_sqNeedDeq", "input"))
    for i in range(2):
        data_buffer.extend((
            _p(f"io_deq_{i}_ready", "input"), _p(f"io_deq_{i}_valid", "output"),
            _p(f"io_deq_{i}_bits_addr", "output", 48), _p(f"io_deq_{i}_bits_vaddr", "output", 50),
            _p(f"io_deq_{i}_bits_data", "output", 128), _p(f"io_deq_{i}_bits_mask", "output", 16),
            _p(f"io_deq_{i}_bits_wline", "output"), _p(f"io_deq_{i}_bits_sqPtr_value", "output", 6),
            _p(f"io_deq_{i}_bits_vecValid", "output"), _p(f"io_deq_{i}_bits_sqNeedDeq", "output"),
        ))
    gpa = (
        _p("clock", "input"), _p("reset", "input"),
        _p("io_fromIFU_gpaddrMem_wen", "input"),
        _p("io_fromIFU_gpaddrMem_waddr", "input", 6),
        _p("io_fromIFU_gpaddrMem_wdata_gpaddr", "input", 56),
        _p("io_fromIFU_gpaddrMem_wdata_isForVSnonLeafPTE", "input"),
        _p("io_exceptionReadAddr_valid", "input"),
        _p("io_exceptionReadAddr_bits_ftqPtr_value", "input", 6),
        _p("io_exceptionReadAddr_bits_ftqOffset", "input", 4),
        _p("io_exceptionReadData_gpaddr", "output", 56),
        _p("io_exceptionReadData_isForVSnonLeafPTE", "output"),
    )
    redirect_inputs = (
        _p("clock", "input"), _p("reset", "input"),
        _p("io_oldestExuRedirect_valid", "input"),
        _p("io_oldestExuRedirect_bits_robIdx_flag", "input"),
        _p("io_oldestExuRedirect_bits_robIdx_value", "input", 8),
        _p("io_oldestExuRedirect_bits_ftqIdx_flag", "input"),
        _p("io_oldestExuRedirect_bits_ftqIdx_value", "input", 6),
        _p("io_oldestExuRedirect_bits_ftqOffset", "input", 4),
        _p("io_oldestExuRedirect_bits_level", "input"),
        _p("io_oldestExuRedirect_bits_cfiUpdate_pc", "input", 50),
        _p("io_oldestExuRedirect_bits_cfiUpdate_target", "input", 50),
        _p("io_oldestExuRedirect_bits_cfiUpdate_taken", "input"),
        _p("io_oldestExuRedirect_bits_cfiUpdate_isMisPred", "input"),
        _p("io_oldestExuRedirect_bits_cfiUpdate_backendIGPF", "input"),
        _p("io_oldestExuRedirect_bits_cfiUpdate_backendIPF", "input"),
        _p("io_oldestExuRedirect_bits_cfiUpdate_backendIAF", "input"),
        _p("io_oldestExuRedirect_bits_fullTarget", "input", 64),
        _p("io_oldestExuRedirect_bits_satpFlush", "input"),
        _p("io_oldestExuRedirect_bits_isVlsException", "input"),
        _p("io_oldestExuRedirectIsCSR", "input"),
        _p("io_instrAddrTransType_bare", "input"),
        _p("io_instrAddrTransType_sv39", "input"),
        _p("io_instrAddrTransType_sv39x4", "input"),
        _p("io_instrAddrTransType_sv48", "input"),
        _p("io_instrAddrTransType_sv48x4", "input"),
        _p("io_loadReplay_valid", "input"),
        _p("io_loadReplay_bits_robIdx_flag", "input"),
        _p("io_loadReplay_bits_robIdx_value", "input", 8),
        _p("io_loadReplay_bits_ftqIdx_flag", "input"),
        _p("io_loadReplay_bits_ftqIdx_value", "input", 6),
        _p("io_loadReplay_bits_ftqOffset", "input", 4),
        _p("io_loadReplay_bits_level", "input"),
        _p("io_loadReplay_bits_cfiUpdate_pc", "input", 50),
        _p("io_loadReplay_bits_cfiUpdate_target", "input", 50),
        _p("io_robFlush_valid", "input"),
        _p("io_robFlush_bits_robIdx_flag", "input"),
        _p("io_robFlush_bits_robIdx_value", "input", 8),
        _p("io_robFlush_bits_level", "input"),
    )
    redirect_outputs = (
        _p("io_stage2Redirect_valid", "output"),
        _p("io_stage2Redirect_bits_robIdx_flag", "output"),
        _p("io_stage2Redirect_bits_robIdx_value", "output", 8),
        _p("io_stage2Redirect_bits_ftqIdx_flag", "output"),
        _p("io_stage2Redirect_bits_ftqIdx_value", "output", 6),
        _p("io_stage2Redirect_bits_ftqOffset", "output", 4),
        _p("io_stage2Redirect_bits_level", "output"),
        _p("io_stage2Redirect_bits_cfiUpdate_pc", "output", 50),
        _p("io_stage2Redirect_bits_cfiUpdate_target", "output", 50),
        _p("io_stage2Redirect_bits_cfiUpdate_taken", "output"),
        _p("io_stage2Redirect_bits_cfiUpdate_isMisPred", "output"),
        _p("io_stage2Redirect_bits_cfiUpdate_backendIGPF", "output"),
        _p("io_stage2Redirect_bits_cfiUpdate_backendIPF", "output"),
        _p("io_stage2Redirect_bits_cfiUpdate_backendIAF", "output"),
        _p("io_stage2Redirect_bits_fullTarget", "output", 64),
        _p("io_stage2Redirect_bits_satpFlush", "output"),
        _p("io_stage2Redirect_bits_isVlsException", "output"),
        _p("io_stage2oldestOH", "output", 2),
    )
    redirect = redirect_inputs + redirect_outputs

    regcache: list[PortSpec] = [_p("clock", "input"), _p("reset", "input")]
    for i in range(23):
        regcache.extend((_p(f"io_readPorts_{i}_ren", "input"),
                         _p(f"io_readPorts_{i}_addr", "input", 5),
                         _p(f"io_readPorts_{i}_data", "output", 64)))
    for i in range(7):
        regcache.extend((_p(f"io_writePorts_{i}_wen", "input"),
                         _p(f"io_writePorts_{i}_data", "input", 64)))
    regcache.extend(_p(f"io_toWakeupQueueRCIdx_{i}", "output", 5) for i in range(7))

    tagtable: list[PortSpec] = [_p("clock", "input"), _p("reset", "input")]
    for i in range(12):
        tagtable.extend((_p(f"io_readPorts_{i}_ren", "input"),
                         _p(f"io_readPorts_{i}_tag", "input", 8),
                         _p(f"io_readPorts_{i}_valid", "output"),
                         _p(f"io_readPorts_{i}_addr", "output", 5)))
    # The locked hierarchy orders wakeup ports from 6 down to 0.
    for i in range(6, -1, -1):
        tagtable.extend((_p(f"io_wakeupFromIQ_{i}_valid", "input"),
                         _p(f"io_wakeupFromIQ_{i}_bits_rfWen", "input"),
                         _p(f"io_wakeupFromIQ_{i}_bits_pdest", "input", 8)))
        if i <= 3:
            tagtable.extend(_p(f"io_wakeupFromIQ_{i}_bits_loadDependency_{k}", "input", 2) for k in range(3))
        if i <= 1:
            tagtable.append(_p(f"io_wakeupFromIQ_{i}_bits_is0Lat", "input"))
        tagtable.append(_p(f"io_wakeupFromIQ_{i}_bits_rcDest", "input", 5))
    for i in range(6):
        tagtable.extend((_p(f"io_allocPregs_{i}_valid", "input"), _p(f"io_allocPregs_{i}_bits", "input", 8)))
    tagtable.extend(_p(f"io_og0Cancel_{i}", "input") for i in (0, 2, 4, 6))
    tagtable.extend(_p(f"io_ldCancel_{i}_ld2Cancel", "input") for i in range(3))

    region_ways = [_p("clock", "input"), _p("reset", "input")]
    region_ways.extend(_p(f"io_req_pointer_{i}", "input", 4) for i in range(5))
    region_ways.extend(_p(f"io_resp_hit_{i}", "output") for i in range(5))
    region_ways.extend(_p(f"io_resp_region_{i}", "output", 30) for i in range(5))
    region_ways.extend(_p(f"io_update_region_{i}", "input", 30) for i in range(2))
    region_ways.extend((_p("io_update_hit_0", "output"), _p("io_update_hit_1", "output")))
    region_ways.extend((_p("io_update_pointer_0", "output", 4), _p("io_update_pointer_1", "output", 4)))
    region_ways.extend((_p("io_write_valid", "input"), _p("io_write_region", "input", 30), _p("io_write_pointer", "output", 4)))

    ras = (
        _p("clock", "input"), _p("reset", "input"),
        _p("io_spec_push_valid", "input"), _p("io_spec_pop_valid", "input"),
        _p("io_spec_push_addr", "input", 50), _p("io_s2_fire", "input"),
        _p("io_s3_fire", "input"), _p("io_s3_cancel", "input"),
        _p("io_s3_meta_ssp", "input", 4), _p("io_s3_meta_sctr", "input", 3),
        _p("io_s3_meta_TOSW_flag", "input"), _p("io_s3_meta_TOSW_value", "input", 5),
        _p("io_s3_meta_TOSR_flag", "input"), _p("io_s3_meta_TOSR_value", "input", 5),
        _p("io_s3_meta_NOS_flag", "input"), _p("io_s3_meta_NOS_value", "input", 5),
        _p("io_s3_missed_pop", "input"), _p("io_s3_missed_push", "input"),
        _p("io_s3_pushAddr", "input", 50), _p("io_spec_pop_addr", "output", 50),
        _p("io_commit_valid", "input"), _p("io_commit_push_valid", "input"),
        _p("io_commit_pop_valid", "input"), _p("io_commit_meta_TOSW_flag", "input"),
        _p("io_commit_meta_TOSW_value", "input", 5), _p("io_commit_meta_ssp", "input", 4),
        _p("io_redirect_valid", "input"), _p("io_redirect_isCall", "input"),
        _p("io_redirect_isRet", "input"), _p("io_redirect_meta_ssp", "input", 4),
        _p("io_redirect_meta_sctr", "input", 3), _p("io_redirect_meta_TOSW_flag", "input"),
        _p("io_redirect_meta_TOSW_value", "input", 5), _p("io_redirect_meta_TOSR_flag", "input"),
        _p("io_redirect_meta_TOSR_value", "input", 5), _p("io_redirect_meta_NOS_flag", "input"),
        _p("io_redirect_meta_NOS_value", "input", 5), _p("io_redirect_callAddr", "input", 50),
        _p("io_ssp", "output", 4), _p("io_sctr", "output", 3),
        _p("io_TOSR_flag", "output"), _p("io_TOSR_value", "output", 5),
        _p("io_TOSW_flag", "output"), _p("io_TOSW_value", "output", 5),
        _p("io_NOS_flag", "output"), _p("io_NOS_value", "output", 5),
        _p("io_spec_near_overflow", "output"),
    )
    fau = (
        _p("clock", "input"), _p("reset", "input"), _p("io_req_tag", "input", 16),
        _p("io_resp_isCall", "output"), _p("io_resp_isRet", "output"), _p("io_resp_isJalr", "output"),
        _p("io_resp_valid", "output"), _p("io_resp_brSlots_0_offset", "output", 4),
        _p("io_resp_brSlots_0_sharing", "output"), _p("io_resp_brSlots_0_valid", "output"),
        _p("io_resp_brSlots_0_lower", "output", 12), _p("io_resp_brSlots_0_tarStat", "output", 2),
        _p("io_resp_tailSlot_offset", "output", 4), _p("io_resp_tailSlot_sharing", "output"),
        _p("io_resp_tailSlot_valid", "output"), _p("io_resp_tailSlot_lower", "output", 20),
        _p("io_resp_tailSlot_tarStat", "output", 2), _p("io_resp_pftAddr", "output", 4),
        _p("io_resp_carry", "output"), _p("io_resp_last_may_be_rvi_call", "output"),
        _p("io_resp_strong_bias_0", "output"), _p("io_resp_strong_bias_1", "output"),
        _p("io_resp_hit", "output"), _p("io_update_req_tag", "input", 16),
        _p("io_update_hit", "output"), _p("io_write_valid", "input"), _p("io_write_entry_isCall", "input"),
        _p("io_write_entry_isRet", "input"), _p("io_write_entry_isJalr", "input"),
        _p("io_write_entry_valid", "input"), _p("io_write_entry_brSlots_0_offset", "input", 4),
        _p("io_write_entry_brSlots_0_sharing", "input"), _p("io_write_entry_brSlots_0_valid", "input"),
        _p("io_write_entry_brSlots_0_lower", "input", 12), _p("io_write_entry_brSlots_0_tarStat", "input", 2),
        _p("io_write_entry_tailSlot_offset", "input", 4), _p("io_write_entry_tailSlot_sharing", "input"),
        _p("io_write_entry_tailSlot_valid", "input"), _p("io_write_entry_tailSlot_lower", "input", 20),
        _p("io_write_entry_tailSlot_tarStat", "input", 2), _p("io_write_entry_pftAddr", "input", 4),
        _p("io_write_entry_carry", "input"), _p("io_write_entry_last_may_be_rvi_call", "input"),
        _p("io_write_entry_strong_bias_0", "input"), _p("io_write_entry_strong_bias_1", "input"),
        _p("io_write_tag", "input", 16),
    )
    vector = (
        _p("clock", "input"), _p("reset", "input"), _p("io_fire", "input"),
        _p("io_uopIdx", "input"), _p("io_src_0", "input", 64), _p("io_src_1", "input", 64),
        _p("io_opType", "input", 8), _p("io_sew", "input", 2), _p("io_rm", "input", 3),
        _p("io_outputWidth1H", "input", 4), _p("io_isWiden", "input"), _p("io_isNarrow", "input"),
        _p("io_result", "output", 128), _p("io_fflags", "output", 40),
    )
    return {
        "AddrAddModule": addr, "GPAMem": gpa, "RedirectGenerator": redirect,
        "DatamoduleResultBuffer": tuple(data_buffer), "RegCache": tuple(regcache),
        "RegCacheTagTable": tuple(tagtable), "RegionWays": tuple(region_ways),
        "RASStack": ras, "FauFTBWay": fau, "VectorCvtTop": vector,
    }


LOCKED_PORT_SPECS: dict[str, tuple[PortSpec, ...]] = _build_port_specs()
PORT_SPECS = LOCKED_PORT_SPECS

# Configuration
# Aggregate members and immutable locked surface are configuration facts. / 聚合成员与不可变锁定端口面属于配置事实。

# Implementation

class BackendSmallControlFamily(Elaboratable):
    """One selected leaf with the exact locked V2 ANSI surface."""

    # Construct one selected leaf surface. / 构造一个选定叶子的端口面。
    def __init__(self, member: str = "AddrAddModule") -> None:
        if member not in PORT_SPECS:
            raise ValueError(f"unknown small-control member: {member}")
        self.member = member
        self.specs = PORT_SPECS[member]
        self.ports: dict[str, Signal] = {
            spec.name: Signal(spec.width, name=spec.name) for spec in self.specs
        }
        self.ordered = [self.ports[spec.name] for spec in self.specs]

# Attach locked clock/reset ports. / 接入锁定时钟与复位端口。
    def _clock_domain(self, module: Module) -> None:
        """Attach locked clock/reset ports to sync logic. / 将锁定时钟/复位端口接入同步逻辑。"""

        if "clock" in self.ports:
            domain = ClockDomain("sync", async_reset=True)
            domain.clk = self.ports["clock"]
            domain.rst = self.ports["reset"]
            module.domains.sync = domain

# Tie unimplemented outputs off. / 固定未实现输出。
    def _zero_outputs(self, module: Module) -> None:
        """Tie unimplemented outputs to deterministic zero. / 将未实现输出固定为确定性零。"""

        for spec in self.specs:
            if spec.direction == "output":
                module.d.comb += self.ports[spec.name].eq(Const(0, spec.width))

# Compute branch and sequential targets. / 计算分支与顺序目标。
    def _addr_add(self, module: Module) -> None:
        """Compute branch target or sequential next PC. / 计算分支目标或顺序下一 PC。"""

        pc = self.ports["io_pcExtend"]
        imm = self.ports["io_imm"]
        # Branch immediates are sign-extended from the low 15 bits in the
        # locked wrapper; the sequential path advances by halfword units.
        imm15 = Cat(imm[:15], imm[14].replicate(36))
        # ``Cat`` places its first argument in the least-significant bits;
        # put the explicit zero first so the sequential offset is shifted by
        # one (the Chisel ``<< instOffsetBits`` operation).
        seq = Cat(Const(0, 1), self.ports["io_nextPcOffset"])
        target_sum = Signal(51, name="addr_target_sum")
        target = Mux(self.ports["io_taken"], pc + imm15, pc + seq)
        # The generated Chisel leaf truncates the adder carry to VAddrBits+1
        # and then sign-extends that 51-bit result to XLEN.
        module.d.comb += [
            target_sum.eq(target[:51]),
            self.ports["io_target"].eq(Cat(target_sum, target_sum[50].replicate(13))),
        ]

# Implement the locked banked GPA storage. / 实现锁定的分 bank GPA 存储。
    def _gpa_mem(self, module: Module) -> None:
        """Mirror SyncDataModuleTemplate's four banks and write pipeline."""

        gpaddr_banks = [
            Array(Signal(56, name=f"mem.dataBanks_{bank}.data_{entry}_gpaddr",
                         reset_less=True) for entry in range(16))
            for bank in range(4)
        ]
        pte_banks = [
            Array(Signal(name=f"mem.dataBanks_{bank}.data_{entry}_isForVSnonLeafPTE",
                         reset_less=True) for entry in range(16))
            for bank in range(4)
        ]
        read_addrs = [
            Signal(6, name="mem.raddr_dup_0" if bank == 0 else f"mem.raddr_dup_0_{bank}",
                   reset_less=True)
            for bank in range(4)
        ]
        read_bank = Signal(6, name="mem.raddr_dup", reset_less=True)
        read_offset = Signal(4, name="ftqOffset", reset_less=True)
        write_valid = [
            Signal(name="mem.wen_dup_last_REG" if bank == 0
                   else f"mem.wen_dup_last_REG_{bank}")
            for bank in range(4)
        ]
        write_addrs = [
            Signal(6, name="mem.waddr_dup_0" if bank == 0 else f"mem.waddr_dup_0_{bank}",
                   reset_less=True)
            for bank in range(4)
        ]
        write_gpaddr = [
            Signal(56, name="mem.r_gpaddr" if bank == 0 else f"mem.r_{bank}_gpaddr",
                   reset_less=True)
            for bank in range(4)
        ]
        write_pte = [
            Signal(name="mem.r_isForVSnonLeafPTE" if bank == 0
                   else f"mem.r_{bank}_isForVSnonLeafPTE", reset_less=True)
            for bank in range(4)
        ]

        for bank in range(4):
            pending_bank = write_addrs[bank][4:6] == bank
            with module.If(write_valid[bank] & pending_bank):
                module.d.sync += [
                    gpaddr_banks[bank][write_addrs[bank][:4]].eq(write_gpaddr[bank]),
                    pte_banks[bank][write_addrs[bank][:4]].eq(write_pte[bank]),
                ]
            module.d.sync += write_valid[bank].eq(
                self.ports["io_fromIFU_gpaddrMem_wen"])
            with module.If(self.ports["io_fromIFU_gpaddrMem_wen"]):
                module.d.sync += [
                    write_addrs[bank].eq(self.ports["io_fromIFU_gpaddrMem_waddr"]),
                    write_gpaddr[bank].eq(
                        self.ports["io_fromIFU_gpaddrMem_wdata_gpaddr"]),
                    write_pte[bank].eq(
                        self.ports["io_fromIFU_gpaddrMem_wdata_isForVSnonLeafPTE"]),
                ]
        with module.If(self.ports["io_exceptionReadAddr_valid"]):
            for read_addr in read_addrs:
                module.d.sync += read_addr.eq(
                    self.ports["io_exceptionReadAddr_bits_ftqPtr_value"])
            module.d.sync += [
                read_bank.eq(self.ports["io_exceptionReadAddr_bits_ftqPtr_value"]),
                read_offset.eq(self.ports["io_exceptionReadAddr_bits_ftqOffset"]),
            ]
        bank_gpaddr = Array(
            Mux(
                write_valid[bank]
                & (write_addrs[bank][4:6] == bank)
                & (write_addrs[bank][:4] == read_addrs[bank][:4]),
                write_gpaddr[bank],
                gpaddr_banks[bank][read_addrs[bank][:4]],
            )
            for bank in range(4)
        )
        bank_pte = Array(
            Mux(
                write_valid[bank]
                & (write_addrs[bank][4:6] == bank)
                & (write_addrs[bank][:4] == read_addrs[bank][:4]),
                write_pte[bank],
                pte_banks[bank][read_addrs[bank][:4]],
            )
            for bank in range(4)
        )
        selected_gpaddr = bank_gpaddr[read_bank[4:6]]
        selected_pte = bank_pte[read_bank[4:6]]
        module.d.comb += [
            self.ports["io_exceptionReadData_gpaddr"].eq(
                selected_gpaddr + Cat(Const(0, 1), read_offset)),
            self.ports["io_exceptionReadData_isForVSnonLeafPTE"].eq(selected_pte),
        ]

    # Implement two bounded enqueue/dequeue lanes. / 实现两个有界入队/出队通道。
    def _data_buffer(self, module: Module) -> None:
        """Retain one result per lane under ready/valid backpressure. / 在 ready/valid 回压下每通道保留一个结果。"""

        fields = (("addr", 48), ("vaddr", 50), ("data", 128), ("mask", 16),
                  ("wline", 1), ("sqPtr_value", 6), ("vecValid", 1), ("sqNeedDeq", 1))
        for lane in range(2):
            full = Signal(name=f"db_full_{lane}")
            regs = {name: Signal(width, name=f"db_{lane}_{name}") for name, width in fields}
            pop = self.ports[f"io_deq_{lane}_ready"] & full
            push = self.ports[f"io_enq_{lane}_valid"] & (self.ports[f"io_enq_{lane}_ready"])
            module.d.comb += self.ports[f"io_enq_{lane}_ready"].eq(~full | pop)
            module.d.comb += self.ports[f"io_deq_{lane}_valid"].eq(full)
            for name, _width in fields:
                module.d.comb += self.ports[f"io_deq_{lane}_bits_{name}"].eq(regs[name])
            with module.If(pop & ~push):
                module.d.sync += full.eq(0)
            with module.If(push):
                module.d.sync += full.eq(1)
                for name, _width in fields:
                    source = self.ports.get(f"io_enq_{lane}_bits_{name}", Const(0, len(regs[name])))
                    module.d.sync += regs[name].eq(source)

    # Implement region tag hits and write pointer allocation. / 实现区域标签命中与写指针分配。
    def _region_ways(self, module: Module) -> None:
        """Expose five probes over a sixteen-entry region table. / 暴露十六项区域表的五个探针。"""

        regions = Array(Signal(30, name=f"region_{i}") for i in range(16))
        valid = Array(Signal(name=f"region_valid_{i}") for i in range(16))
        write_pointer = Signal(4, name="region_write_pointer")
        module.d.comb += self.ports["io_write_pointer"].eq(write_pointer)
        for i in range(5):
            hit = Const(0, 1)
            value = Const(0, 30)
            for entry in range(15, -1, -1):
                hit_entry = valid[entry] & (regions[entry] == self.ports[f"io_req_pointer_{i}"])
                hit = hit | hit_entry
                value = Mux(hit_entry, regions[entry], value)
            module.d.comb += [
                self.ports[f"io_resp_hit_{i}"].eq(hit),
                self.ports[f"io_resp_region_{i}"].eq(value),
            ]
        for i in range(2):
            update_hit = Const(0, 1)
            update_ptr = Const(0, 4)
            for entry in range(15, -1, -1):
                hit_entry = valid[entry] & (regions[entry] == self.ports[f"io_update_region_{i}"])
                update_hit = update_hit | hit_entry
                update_ptr = Mux(hit_entry, Const(entry, 4), update_ptr)
            module.d.comb += [
                self.ports[f"io_update_hit_{i}"].eq(update_hit),
                self.ports[f"io_update_pointer_{i}"].eq(update_ptr),
            ]
        with module.If(self.ports["io_write_valid"]):
            module.d.sync += [
                regions[write_pointer].eq(self.ports["io_write_region"]),
                valid[write_pointer].eq(1),
                write_pointer.eq(write_pointer + 1),
            ]

# Select the oldest redirect. / 选择最老重定向。
    def _redirect(self, module: Module) -> None:
        """Implement the registered oldest-redirect and flush-after window."""

        p = self.ports
        exu_valid = p["io_oldestExuRedirect_valid"]
        load_valid = p["io_loadReplay_valid"]
        exu_flag = p["io_oldestExuRedirect_bits_robIdx_flag"]
        exu_value = p["io_oldestExuRedirect_bits_robIdx_value"]
        load_flag = p["io_loadReplay_bits_robIdx_flag"]
        load_value = p["io_loadReplay_bits_robIdx_value"]
        compare = exu_flag ^ load_flag ^ (exu_value > load_value)
        choose_exu = exu_valid & (~load_valid | ~compare)
        choose_load = load_valid & (~exu_valid | compare)

        flush_valid = Signal(name="flushAfter_valid")
        flush_flag = Signal(name="flushAfter_bits_robIdx_flag")
        flush_value = Signal(8, name="flushAfter_bits_robIdx_value")
        flush_level = Signal(name="flushAfter_bits_level")
        flush_counter = Signal(3, name="flushAfterCounter", reset_less=True)

        def need_flush(flag: Any, value: Any, level: Any) -> Any:
            pointer_equal = Cat(value, flag) == Cat(flush_value, flush_flag)
            at_or_after = flag ^ flush_flag ^ (value > flush_value)
            return flush_valid & ((flush_level & pointer_equal) | at_or_after) \
                | p["io_robFlush_valid"]

        exu_accept = choose_exu & ~need_flush(
            exu_flag, exu_value, p["io_oldestExuRedirect_bits_level"])
        load_accept = choose_load & ~need_flush(
            load_flag, load_value, p["io_loadReplay_bits_level"])
        oldest_valid = exu_accept | load_accept

        selected_flag = Mux(choose_exu, exu_flag, Mux(choose_load, load_flag, 0))
        selected_value = Mux(choose_exu, exu_value, Mux(choose_load, load_value, 0))
        selected_level = Mux(
            choose_exu,
            p["io_oldestExuRedirect_bits_level"],
            Mux(choose_load, p["io_loadReplay_bits_level"], 0),
        )
        flush_event = oldest_valid | p["io_robFlush_valid"]
        module.d.sync += flush_valid.eq(
            flush_event | (flush_counter[0] & flush_valid))
        with module.If(flush_event):
            module.d.sync += [
                flush_flag.eq(Mux(p["io_robFlush_valid"],
                                  p["io_robFlush_bits_robIdx_flag"], selected_flag)),
                flush_value.eq(Mux(p["io_robFlush_valid"],
                                   p["io_robFlush_bits_robIdx_value"], selected_value)),
                flush_level.eq(Mux(p["io_robFlush_valid"],
                                   p["io_robFlush_bits_level"], selected_level)),
                flush_counter.eq(7),
            ]
        with module.Elif(flush_counter[0]):
            module.d.sync += flush_counter.eq(flush_counter >> 1)

        stage_valid = Signal(name="s1_redirect_valid_reg_last_REG")
        stage_exu = Signal(name="s1_redirect_onehot_last_REG")
        stage_load = Signal(name="s1_redirect_onehot_last_REG_1")
        module.d.sync += [
            stage_valid.eq(oldest_valid),
            stage_exu.eq(choose_exu),
            stage_load.eq(choose_load),
        ]

        exu_target = p["io_oldestExuRedirect_bits_cfiUpdate_target"]
        exu_full = p["io_oldestExuRedirect_bits_fullTarget"]
        upper_16 = Cat(exu_target[48:50], exu_full[50:64])
        noncanonical_39 = Cat(exu_target[39:50], exu_full[50:64]) \
            != exu_target[38].replicate(25)
        noncanonical_48 = upper_16 != exu_target[47].replicate(16)
        csr = p["io_oldestExuRedirectIsCSR"]
        exu_igpf = Mux(
            csr,
            p["io_oldestExuRedirect_bits_cfiUpdate_backendIGPF"],
            (p["io_instrAddrTransType_sv39x4"]
             & Cat(exu_target[41:50], exu_full[50:64]).any())
            | (p["io_instrAddrTransType_sv48x4"] & exu_full[50:64].any()),
        )
        exu_ipf = Mux(
            csr,
            p["io_oldestExuRedirect_bits_cfiUpdate_backendIPF"],
            (p["io_instrAddrTransType_sv39"] & noncanonical_39)
            | (p["io_instrAddrTransType_sv48"] & noncanonical_48),
        )
        exu_iaf = Mux(
            csr,
            p["io_oldestExuRedirect_bits_cfiUpdate_backendIAF"],
            p["io_instrAddrTransType_bare"] & upper_16.any(),
        )
        special_exu: dict[str, Any] = {
            "cfiUpdate_backendIGPF": exu_igpf,
            "cfiUpdate_backendIPF": exu_ipf,
            "cfiUpdate_backendIAF": exu_iaf,
            "fullTarget": Cat(exu_target, exu_full[50:64]),
        }
        load_fields = {
            "robIdx_flag", "robIdx_value", "ftqIdx_flag", "ftqIdx_value",
            "ftqOffset", "level", "cfiUpdate_pc", "cfiUpdate_target",
        }
        fields = (
            "robIdx_flag", "robIdx_value", "ftqIdx_flag", "ftqIdx_value",
            "ftqOffset", "level", "cfiUpdate_pc", "cfiUpdate_target",
            "cfiUpdate_taken", "cfiUpdate_isMisPred", "cfiUpdate_backendIGPF",
            "cfiUpdate_backendIPF", "cfiUpdate_backendIAF", "fullTarget",
            "satpFlush", "isVlsException",
        )
        stage_fields: dict[str, Signal] = {}
        for suffix in fields:
            output = p[f"io_stage2Redirect_bits_{suffix}"]
            register = Signal(len(output), name=f"s1_redirect_bits_reg_{suffix}",
                              reset_less=True)
            stage_fields[suffix] = register
            exu_name = f"io_oldestExuRedirect_bits_{suffix}"
            source_exu = special_exu.get(suffix, p[exu_name])
            load_name = f"io_loadReplay_bits_{suffix}"
            source_load: Any = p[load_name] if suffix in load_fields else Const(0, len(output))
            with module.If(oldest_valid):
                module.d.sync += register.eq(
                    Mux(choose_exu, source_exu,
                        Mux(choose_load, source_load, Const(0, len(output)))))
            module.d.comb += output.eq(register)

        module.d.comb += [
            p["io_stage2Redirect_valid"].eq(
                stage_valid & ~p["io_robFlush_valid"]),
            p["io_stage2oldestOH"].eq(Cat(stage_exu, stage_load)),
        ]

# Implement the bounded register cache. / 实现有界寄存缓存。
    def _regcache(self, module: Module) -> None:
        """Provide a bounded 32-entry data cache and replacement indices. / 提供有界 32 项数据缓存和替换索引。"""

        storage = Array(Signal(64, name=f"rc_data_{i}") for i in range(32))
        pointers = [Signal(5, name=f"rc_wp_{i}") for i in range(7)]
        for i in range(23):
            module.d.comb += self.ports[f"io_readPorts_{i}_data"].eq(
                Mux(self.ports[f"io_readPorts_{i}_ren"], storage[self.ports[f"io_readPorts_{i}_addr"]], Const(0, 64))
            )
        for i, pointer in enumerate(pointers):
            module.d.comb += self.ports[f"io_toWakeupQueueRCIdx_{i}"].eq(pointer)
            with module.If(self.ports[f"io_writePorts_{i}_wen"]):
                module.d.sync += storage[pointer].eq(self.ports[f"io_writePorts_{i}_data"])
                module.d.sync += pointer.eq(pointer + 1)

# Implement tag wakeups and probes. / 实现标签唤醒与探针。
    def _tagtable(self, module: Module) -> None:
        """Mirror the 16-entry integer and 12-entry memory tag tables."""

        p = self.ports

        def or_all(values: list[Any], width: int = 1) -> Any:
            result: Any = Const(0, width)
            for value in values:
                result = result | value
            return result

        int_write_enable: list[Any] = []
        for write in range(4):
            dependency_cancel = or_all([
                p[f"io_ldCancel_{dep}_ld2Cancel"]
                & p[f"io_wakeupFromIQ_{write}_bits_loadDependency_{dep}"][1]
                for dep in range(3)
            ])
            og_cancel = p[f"io_og0Cancel_{write * 2}"]
            if write < 2:
                og_cancel = og_cancel & p[f"io_wakeupFromIQ_{write}_bits_is0Lat"]
            int_write_enable.append(
                p[f"io_wakeupFromIQ_{write}_valid"]
                & p[f"io_wakeupFromIQ_{write}_bits_rfWen"]
                & ~dependency_cancel & ~og_cancel
            )
        mem_write_enable = [
            p[f"io_wakeupFromIQ_{write}_valid"]
            & p[f"io_wakeupFromIQ_{write}_bits_rfWen"]
            for write in range(4, 7)
        ]

        int_valid = [Signal(name=f"IntRCTagTable.v_{entry}") for entry in range(16)]
        int_tags = [Signal(8, name=f"IntRCTagTable.tag_{entry}", reset_less=True)
                    for entry in range(16)]
        int_deps = [
            [Signal(2, name=f"IntRCTagTable.loadDependency_{entry}_{dep}",
                    reset_less=True) for dep in range(3)]
            for entry in range(16)
        ]
        mem_valid = [Signal(name=f"MemRCTagTable.v_{entry}") for entry in range(12)]
        mem_tags = [Signal(8, name=f"MemRCTagTable.tag_{entry}", reset_less=True)
                    for entry in range(12)]
        mem_deps = [
            [Signal(2, name=f"MemRCTagTable.loadDependency_{entry}_{dep}",
                    reset_less=True) for dep in range(3)]
            for entry in range(12)
        ]

        for entry in range(16):
            hits = [
                int_write_enable[write]
                & (p[f"io_wakeupFromIQ_{write}_bits_rcDest"][:4] == entry)
                for write in range(4)
            ]
            any_hit = or_all(hits)
            allocation_cancel = or_all([
                p[f"io_allocPregs_{alloc}_valid"]
                & (p[f"io_allocPregs_{alloc}_bits"] == int_tags[entry])
                for alloc in range(6)
            ])
            duplicate_cancel = or_all([
                int_write_enable[write]
                & (p[f"io_wakeupFromIQ_{write}_bits_pdest"] == int_tags[entry])
                for write in range(4)
            ])
            dependency_cancel = or_all([
                p[f"io_ldCancel_{dep}_ld2Cancel"] & int_deps[entry][dep][1]
                for dep in range(3)
            ])
            cancel = (allocation_cancel | duplicate_cancel | dependency_cancel) \
                & int_valid[entry]
            module.d.sync += int_valid[entry].eq(
                any_hit | (~cancel & int_valid[entry]))
            tag_value = or_all([
                Mux(hits[write], p[f"io_wakeupFromIQ_{write}_bits_pdest"],
                    Const(0, 8))
                for write in range(4)
            ], 8)
            with module.If(any_hit):
                module.d.sync += int_tags[entry].eq(tag_value)
            any_dependency = or_all([
                int_deps[entry][dep].any() for dep in range(3)
            ])
            for dep in range(3):
                new_dependency = or_all([
                    Mux(
                        hits[write],
                        Cat(Const(0, 1),
                            p[f"io_wakeupFromIQ_{write}_bits_loadDependency_{dep}"][0]),
                        Const(0, 2),
                    )
                    for write in range(4)
                ], 2)
                shifted = Cat(Const(0, 1), int_deps[entry][dep][0])
                module.d.sync += int_deps[entry][dep].eq(
                    Mux(any_hit, new_dependency,
                        Mux(cancel | ~any_dependency,
                            int_deps[entry][dep], shifted)))

        for entry in range(12):
            hits = [
                mem_write_enable[index]
                & (p[f"io_wakeupFromIQ_{index + 4}_bits_rcDest"][:4] == entry)
                for index in range(3)
            ]
            any_hit = or_all(hits)
            allocation_cancel = or_all([
                p[f"io_allocPregs_{alloc}_valid"]
                & (p[f"io_allocPregs_{alloc}_bits"] == mem_tags[entry])
                for alloc in range(6)
            ])
            duplicate_cancel = or_all([
                mem_write_enable[index]
                & (p[f"io_wakeupFromIQ_{index + 4}_bits_pdest"] == mem_tags[entry])
                for index in range(3)
            ])
            dependency_cancel = or_all([
                p[f"io_ldCancel_{dep}_ld2Cancel"] & mem_deps[entry][dep][1]
                for dep in range(3)
            ])
            cancel = (allocation_cancel | duplicate_cancel | dependency_cancel) \
                & mem_valid[entry]
            module.d.sync += mem_valid[entry].eq(
                any_hit | (~cancel & mem_valid[entry]))
            tag_value = or_all([
                Mux(hits[index], p[f"io_wakeupFromIQ_{index + 4}_bits_pdest"],
                    Const(0, 8))
                for index in range(3)
            ], 8)
            with module.If(any_hit):
                module.d.sync += mem_tags[entry].eq(tag_value)
            any_dependency = or_all([
                mem_deps[entry][dep].any() for dep in range(3)
            ])
            for dep in range(3):
                new_dependency = Mux(
                    hits[dep], Const(1, 2), Const(0, 2))
                shifted = Cat(Const(0, 1), mem_deps[entry][dep][0])
                module.d.sync += mem_deps[entry][dep].eq(
                    Mux(any_hit, new_dependency,
                        Mux(cancel | ~any_dependency,
                            mem_deps[entry][dep], shifted)))

        for read in range(12):
            query = p[f"io_readPorts_{read}_tag"]
            int_matches = [int_valid[entry] & (int_tags[entry] == query)
                           for entry in range(16)]
            mem_matches = [mem_valid[entry] & (mem_tags[entry] == query)
                           for entry in range(12)]
            int_found = p[f"io_readPorts_{read}_ren"] & or_all(int_matches)
            mem_found = p[f"io_readPorts_{read}_ren"] & or_all(mem_matches)
            allocated = or_all([
                p[f"io_allocPregs_{alloc}_valid"]
                & (query == p[f"io_allocPregs_{alloc}_bits"])
                for alloc in range(6)
            ])
            int_address: Any = Const(0, 4)
            for entry in range(16):
                int_address = int_address | Mux(
                    int_matches[entry], Const(entry, 4), Const(0, 4))
            mem_address: Any = Const(0, 4)
            for entry in range(12):
                mem_address = mem_address | Mux(
                    mem_matches[entry], Const(entry, 4), Const(0, 4))
            module.d.comb += [
                p[f"io_readPorts_{read}_valid"].eq(
                    (int_found | mem_found) & ~allocated),
                p[f"io_readPorts_{read}_addr"].eq(
                    Mux(int_found,
                        Cat(int_address, Const(0, 1)),
                        Cat(mem_address, Const(1, 1)))),
            ]

# Implement the bounded return-address stack. / 实现有界返回地址栈。
    def _ras(self, module: Module) -> None:
        """Maintain a bounded speculative return-address stack. / 维护有界推测返回地址栈。"""

        stack = Array(Signal(50, name=f"ras_entry_{i}") for i in range(16))
        top = Signal(4, name="ras_top")
        module.d.comb += [
            self.ports["io_spec_pop_addr"].eq(stack[top]),
            self.ports["io_spec_near_overflow"].eq(top >= 14),
            self.ports["io_ssp"].eq(0), self.ports["io_sctr"].eq(0),
            self.ports["io_TOSR_flag"].eq(0), self.ports["io_TOSR_value"].eq(top),
            self.ports["io_TOSW_flag"].eq(0), self.ports["io_TOSW_value"].eq(top),
            self.ports["io_NOS_flag"].eq(0), self.ports["io_NOS_value"].eq(top - 1),
        ]
        with module.If(self.ports["io_spec_push_valid"]):
            module.d.sync += [stack[top].eq(self.ports["io_spec_push_addr"]), top.eq(top + 1)]
        with module.Elif(self.ports["io_spec_pop_valid"]):
            module.d.sync += top.eq(top - 1)
        # Redirect metadata is observable even while the bounded stack is idle.
        with module.If(self.ports["io_redirect_valid"]):
            module.d.comb += [
                self.ports["io_ssp"].eq(self.ports["io_redirect_meta_ssp"]),
                self.ports["io_sctr"].eq(self.ports["io_redirect_meta_sctr"]),
                self.ports["io_TOSR_flag"].eq(self.ports["io_redirect_meta_TOSR_flag"]),
                self.ports["io_TOSR_value"].eq(self.ports["io_redirect_meta_TOSR_value"]),
                self.ports["io_TOSW_flag"].eq(self.ports["io_redirect_meta_TOSW_flag"]),
                self.ports["io_TOSW_value"].eq(self.ports["io_redirect_meta_TOSW_value"]),
                self.ports["io_NOS_flag"].eq(self.ports["io_redirect_meta_NOS_flag"]),
                self.ports["io_NOS_value"].eq(self.ports["io_redirect_meta_NOS_value"]),
            ]

# Implement one fast-target-buffer entry. / 实现单条快速目标缓冲。
    def _fauftb(self, module: Module) -> None:
        """Store one fast-target-buffer entry with write bypass. / 存储单条快速目标缓冲并旁路写入。"""

        p = self.ports
        fields = (
            ("isCall", 1), ("isRet", 1), ("isJalr", 1), ("valid", 1),
            ("brSlots_0_offset", 4), ("brSlots_0_sharing", 1), ("brSlots_0_valid", 1),
            ("brSlots_0_lower", 12), ("brSlots_0_tarStat", 2), ("tailSlot_offset", 4),
            ("tailSlot_sharing", 1), ("tailSlot_valid", 1), ("tailSlot_lower", 20),
            ("tailSlot_tarStat", 2), ("pftAddr", 4), ("carry", 1),
            ("last_may_be_rvi_call", 1), ("strong_bias_0", 1), ("strong_bias_1", 1),
        )
        # Mirrors the proven standalone FauFTBWay Build: only ``valid`` is reset,
        # payload and tag keep their contents, and the names follow the locked
        # netlist so induction pairs every register instead of leaving state free
        # and unmatched.
        # 命名与复位对齐锁定网表及已独立证明的同名模块。
        regs = {name: Signal(width, name=f"data_{name}", reset_less=True)
                for name, width in fields}
        tag = Signal(16, name="tag", reset_less=True)
        valid = Signal(name="valid", reset=0)
        for name, width in fields:
            out = p[f"io_resp_{name}"]
            module.d.comb += out.eq(regs[name])
        module.d.comb += [
            p["io_resp_hit"].eq((tag == p["io_req_tag"]) & valid),
            p["io_update_hit"].eq(((tag == p["io_update_req_tag"]) & valid) | (p["io_write_valid"] & (p["io_write_tag"] == p["io_update_req_tag"]))),
        ]
        with module.If(p["io_write_valid"]):
            module.d.sync += tag.eq(p["io_write_tag"])
            for name, _width in fields:
                module.d.sync += regs[name].eq(p[f"io_write_entry_{name}"])
        with module.If(p["io_write_valid"] & ~valid):
            module.d.sync += valid.eq(1)

# Implement the vector conversion envelope. / 实现向量转换封装。
    def _vector(self, module: Module) -> None:
        """Provide deterministic two-lane vector conversion envelope. / 提供确定性的双通道向量转换封装。"""

        # The full VectorCvt arithmetic remains a separate closure; retaining
        # source lanes and a zero flag bundle keeps this leaf synthesizable and
        # preserves the exact ABI for parent wiring.
        module.d.comb += [
            self.ports["io_result"].eq(Cat(self.ports["io_src_0"], self.ports["io_src_1"])),
            self.ports["io_fflags"].eq(0),
        ]

# Elaborate the selected member. / 展开选定成员。
    def elaborate(self, platform: Any) -> Module:
        """Elaborate selected bounded leaf. / 展开选定的有界叶模块。"""

        del platform
        module = Module()
        self._clock_domain(module)
        self._zero_outputs(module)
        if self.member == "AddrAddModule":
            self._addr_add(module)
        elif self.member == "GPAMem":
            self._gpa_mem(module)
        elif self.member == "DatamoduleResultBuffer":
            self._data_buffer(module)
        elif self.member == "RedirectGenerator":
            self._redirect(module)
        elif self.member == "RegCache":
            self._regcache(module)
        elif self.member == "RegCacheTagTable":
            self._tagtable(module)
        elif self.member == "RegionWays":
            self._region_ways(module)
        elif self.member == "RASStack":
            self._ras(module)
        elif self.member == "FauFTBWay":
            self._fauftb(module)
        elif self.member == "VectorCvtTop":
            self._vector(module)
        return module


SmallControlFamily = BackendSmallControlFamily

# Public Adapter

# Emit one selected locked member. / 导出一个选定的锁定成员。
def build_verilog(configuration: Any = None, injected_dependencies: Any = None) -> str:
    """Emit one selected member with exact locked ports. / 导出精确锁定端口的选定成员。"""

    del injected_dependencies
    member = "AddrAddModule"
    if isinstance(configuration, dict):
        member = str(configuration.get("module", configuration.get("member", member)))
    elif isinstance(configuration, str):
        member = configuration
    elif configuration is not None:
        member = str(getattr(configuration, "module", getattr(configuration, "member", member)))
    top = BackendSmallControlFamily(member)
    return verilog.convert(top, name=member, ports=top.ordered, emit_src=False)


# Print the default aggregate export. / 打印默认聚合导出。
# Direct Entry
# Print the default aggregate export. / 打印默认聚合导出。
def main() -> None:
    """Print the default aggregate export. / 打印默认聚合导出。"""

    print(build_verilog())


if __name__ == "__main__":
    main()
