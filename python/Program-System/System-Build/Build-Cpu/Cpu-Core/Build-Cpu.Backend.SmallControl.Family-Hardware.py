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
    "DatamoduleResultBuffer",
    "GPAMem",
    "RedirectGenerator",
    "RegCache",
    "RegCacheTagTable",
    "RegionWays",
    "RASStack",
    "FauFTBWay",
    "VectorCvtTop",
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

# Implement bounded GPA storage. / 实现有界 GPA 存储。
    def _gpa_mem(self, module: Module) -> None:
        """Implement bounded FTQ-indexed GPA storage. / 实现有界 FTQ 索引 GPA 存储。"""

        storage = Array(Signal(57, name=f"gpa_slot_{i}") for i in range(64))
        read_addr = Signal(6, name="gpa_read_addr")
        read_offset = Signal(4, name="gpa_read_offset")
        with module.If(self.ports["io_fromIFU_gpaddrMem_wen"]):
            module.d.sync += storage[self.ports["io_fromIFU_gpaddrMem_waddr"]].eq(
                Cat(self.ports["io_fromIFU_gpaddrMem_wdata_gpaddr"], self.ports["io_fromIFU_gpaddrMem_wdata_isForVSnonLeafPTE"])
            )
        with module.If(self.ports["io_exceptionReadAddr_valid"]):
            module.d.sync += [
                read_addr.eq(self.ports["io_exceptionReadAddr_bits_ftqPtr_value"]),
                read_offset.eq(self.ports["io_exceptionReadAddr_bits_ftqOffset"]),
            ]
        entry = storage[read_addr]
        module.d.comb += [
            self.ports["io_exceptionReadData_gpaddr"].eq(entry[:56] + (read_offset << 1)),
            self.ports["io_exceptionReadData_isForVSnonLeafPTE"].eq(entry[56]),
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
        """Select the oldest redirect with ROB circular ordering. / 按 ROB 环序选择最老重定向。"""

        p = self.ports
        exu = p["io_oldestExuRedirect_valid"]
        load = p["io_loadReplay_valid"]
        same = p["io_oldestExuRedirect_bits_robIdx_flag"] == p["io_loadReplay_bits_robIdx_flag"]
        exu_older = Mux(same,
                        p["io_oldestExuRedirect_bits_robIdx_value"] < p["io_loadReplay_bits_robIdx_value"],
                        p["io_oldestExuRedirect_bits_robIdx_value"] > p["io_loadReplay_bits_robIdx_value"])
        choose_exu = exu & (~load | exu_older)
        choose_load = load & (~exu | ~exu_older)
        valid = (choose_exu | choose_load) & ~p["io_robFlush_valid"]
        module.d.comb += [
            p["io_stage2Redirect_valid"].eq(valid),
            p["io_stage2oldestOH"].eq(Cat(choose_exu, choose_load)),
        ]
        pairs = (
            ("robIdx_flag", "robIdx_flag"), ("robIdx_value", "robIdx_value"),
            ("ftqIdx_flag", "ftqIdx_flag"), ("ftqIdx_value", "ftqIdx_value"),
            ("ftqOffset", "ftqOffset"), ("level", "level"),
            ("cfiUpdate_pc", "cfiUpdate_pc"), ("cfiUpdate_target", "cfiUpdate_target"),
            ("cfiUpdate_taken", "cfiUpdate_taken"), ("cfiUpdate_isMisPred", "cfiUpdate_isMisPred"),
            ("cfiUpdate_backendIGPF", "cfiUpdate_backendIGPF"),
            ("cfiUpdate_backendIPF", "cfiUpdate_backendIPF"),
            ("cfiUpdate_backendIAF", "cfiUpdate_backendIAF"),
            ("fullTarget", "fullTarget"), ("satpFlush", "satpFlush"),
            ("isVlsException", "isVlsException"),
        )
        for suffix, _ in pairs:
            out = p[f"io_stage2Redirect_bits_{suffix}"]
            exu_name = f"io_oldestExuRedirect_bits_{suffix}"
            load_name = f"io_loadReplay_bits_{suffix}"
            exu_value = p[exu_name] if exu_name in p else Const(0, len(out))
            load_value = p[load_name] if load_name in p else Const(0, len(out))
            module.d.comb += out.eq(Mux(choose_exu, exu_value, Mux(choose_load, load_value, Const(0, len(out)))))

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
        """Track tag wakeups and answer twelve read probes. / 跟踪标签唤醒并响应十二个读探针。"""

        tags = Array(Signal(8, name=f"rct_tag_{i}") for i in range(32))
        valids = Array(Signal(name=f"rct_valid_{i}") for i in range(32))
        for i in range(12):
            hit = Signal(32, name=f"rct_hit_{i}")
            for entry in range(32):
                module.d.comb += hit[entry].eq(valids[entry] & (tags[entry] == self.ports[f"io_readPorts_{i}_tag"]))
            # Priority encode the first matching entry with a small mux tree.
            addr = Const(0, 5)
            found = Const(0, 1)
            for entry in range(31, -1, -1):
                addr = Mux(hit[entry], Const(entry, 5), addr)
                found = found | hit[entry]
            module.d.comb += [
                self.ports[f"io_readPorts_{i}_valid"].eq(self.ports[f"io_readPorts_{i}_ren"] & found),
                self.ports[f"io_readPorts_{i}_addr"].eq(addr),
            ]
        for i in range(7):
            valid = self.ports[f"io_wakeupFromIQ_{i}_valid"]
            wen = self.ports[f"io_wakeupFromIQ_{i}_bits_rfWen"]
            idx = self.ports[f"io_wakeupFromIQ_{i}_bits_rcDest"]
            with module.If(valid & wen):
                module.d.sync += [tags[idx].eq(self.ports[f"io_wakeupFromIQ_{i}_bits_pdest"]), valids[idx].eq(1)]
        for i in range(6):
            with module.If(self.ports[f"io_allocPregs_{i}_valid"]):
                for entry in range(32):
                    with module.If(tags[entry] == self.ports[f"io_allocPregs_{i}_bits"]):
                        module.d.sync += valids[entry].eq(0)

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
        regs = {name: Signal(width, name=f"fau_{name}") for name, width in fields}
        tag = Signal(16, name="fau_tag")
        for name, width in fields:
            out = p[f"io_resp_{name}"]
            module.d.comb += out.eq(regs[name])
        module.d.comb += [
            p["io_resp_hit"].eq((tag == p["io_req_tag"]) & regs["valid"]),
            p["io_update_hit"].eq(((tag == p["io_update_req_tag"]) & regs["valid"]) | (p["io_write_valid"] & (p["io_write_tag"] == p["io_update_req_tag"]))),
        ]
        with module.If(p["io_write_valid"]):
            module.d.sync += tag.eq(p["io_write_tag"])
            for name, _width in fields:
                module.d.sync += regs[name].eq(p[f"io_write_entry_{name}"])

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
