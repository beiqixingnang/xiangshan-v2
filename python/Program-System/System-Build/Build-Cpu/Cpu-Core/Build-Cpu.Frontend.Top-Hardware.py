"""UHSC Kunminghu V2 Frontend parent closure.
昆明湖 V2 前端父级闭包的 UHSC Amaranth 实现。

The locked V2 ``Frontend`` is a 371-port integration boundary.  This file
keeps the parent-visible control and transaction equations executable while
leaving large child families (ICache, InstrUncache, IFU, BPU, FTQ, IBuffer,
and ITLB) behind explicit constructor injection points.  The reduced surface
is intentional: it is a bounded parent closure, not a claim that every
Diplomacy/SRAM port has already been rewritten.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amaranth import ClockDomain, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# Frontend.scala delays redirect/fence/WFI controls, joins ICache and
# InstrUncache safety, pipelines ICache errors, and exposes the backend CF
# vector plus frontend information.  The parent below preserves those
# equations and names every unfinished child as an injected dependency.
# Frontend.scala 延迟 redirect/fence/WFI 控制，合并 ICache 与 InstrUncache
# 安全状态，流水化 ICache 错误，并输出后端 CF 向量及前端信息；本父级保留这些
# 方程，并将未完成子级全部声明为显式注入依赖。
__all__ = [
    "FrontendTopConfig",
    "FrontendChildBoundary",
    "FrontendParent",
    "UHSCTop",
    "Frontend",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class FrontendTopConfig:
    """Finite V2 geometry for the parent-visible Frontend boundary. / V2 前端父边界的有限几何。"""

    vaddr_bits: int = 50
    paddr_bits: int = 48
    ftq_idx_bits: int = 6
    ftq_offset_bits: int = 4
    fetch_width: int = 6
    instr_bits: int = 32
    error_bits: int = 48
    perf_bits: int = 6
    perf_count: int = 8
    soft_prefetch_count: int = 3

    # Validate the widths used by the locked Kunminghu V2 Frontend. / 校验锁定昆明湖 V2 前端使用的位宽。
    def __post_init__(self) -> None:
        if self.vaddr_bits < self.paddr_bits or self.paddr_bits < 8:
            raise ValueError("V2 virtual/physical address widths are inconsistent")
        if self.ftq_idx_bits < 1 or self.ftq_offset_bits < 1:
            raise ValueError("FTQ widths must be positive")
        if self.fetch_width != 6:
            raise ValueError("Kunminghu V2 Frontend backend width is six")
        if self.instr_bits != 32:
            raise ValueError("the V2 instruction width is 32")
        if self.error_bits < 1 or self.perf_bits < 1 or self.perf_count < 1:
            raise ValueError("error/performance widths must be positive")
        if self.soft_prefetch_count != 3:
            raise ValueError("V2 Frontend exposes three soft-prefetch lanes")


# =============================================================================
# Implementation
# =============================================================================
class FrontendChildBoundary(Elaboratable):
    """Small injectable child contract for ICache-like frontend units. / 可注入 ICache 类前端子级合同。"""

    # Construct a named child request/status surface. / 构造带名称的子级请求与状态表面。
    def __init__(self, configuration: FrontendTopConfig | None = None,
                 child_name: str = "child") -> None:
        self.configuration = configuration or FrontendTopConfig()
        cfg = self.configuration
        self.child_name = child_name
        self.clock = Signal(name=f"{child_name}_clock")
        self.reset = Signal(name=f"{child_name}_reset")
        self.flush = Signal(name=f"{child_name}_flush")
        self.fencei = Signal(name=f"{child_name}_fencei")
        self.wfi_req = Signal(name=f"{child_name}_wfiReq")
        self.req_valid = Signal(name=f"{child_name}_req_valid")
        self.req_ready = Signal(name=f"{child_name}_req_ready")
        self.req_addr = Signal(cfg.vaddr_bits, name=f"{child_name}_req_addr")
        self.req_nextline = Signal(cfg.vaddr_bits, name=f"{child_name}_req_nextline")
        self.resp_valid = Signal(name=f"{child_name}_resp_valid")
        self.resp_data = Signal(cfg.instr_bits * 16, name=f"{child_name}_resp_data")
        self.resp_error = Signal(name=f"{child_name}_resp_error")
        self.wfi_safe = Signal(name=f"{child_name}_wfiSafe")
        self.error_valid = Signal(name=f"{child_name}_error_valid")
        self.error_bits = Signal(cfg.error_bits, name=f"{child_name}_error_bits")
        self.ibuffer_full = Signal(name=f"{child_name}_ibufferFull")
        self.bp_right = Signal(cfg.instr_bits, name=f"{child_name}_bpRight")
        self.bp_wrong = Signal(cfg.instr_bits, name=f"{child_name}_bpWrong")
        self.cf_valid = Signal(cfg.fetch_width, name=f"{child_name}_cf_valid")
        self.cf_instr = Signal(cfg.fetch_width * cfg.instr_bits, name=f"{child_name}_cf_instr")
        self.cf_pc = Signal(cfg.fetch_width * cfg.vaddr_bits, name=f"{child_name}_cf_pc")
        self.cf_is_rvc = Signal(cfg.fetch_width, name=f"{child_name}_cf_isRVC")
        self.cf_pred_taken = Signal(cfg.fetch_width, name=f"{child_name}_cf_predTaken")
        self.cf_exception = Signal(cfg.fetch_width, name=f"{child_name}_cf_exception")

    # Elaborate a deterministic one-entry child fallback for standalone use. / 为独立使用展开确定性单项子级回退。
    def elaborate(self, platform: Any) -> Module:
        del platform
        cfg = self.configuration
        module = Module()
        domain = ClockDomain(f"{self.child_name}_sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        setattr(module.domains, f"{self.child_name}_sync", domain)
        busy = Signal(name=f"{self.child_name}_busy")
        saved_addr = Signal(cfg.vaddr_bits, name=f"{self.child_name}_saved_addr")
        request_fire = self.req_valid & self.req_ready
        module.d.comb += [
            self.req_ready.eq(~busy & ~self.flush & ~self.fencei),
            self.resp_valid.eq(busy & ~self.flush),
            self.resp_data.eq(0),
            self.resp_error.eq(0),
            self.wfi_safe.eq(~busy),
            self.error_valid.eq(0),
            self.error_bits.eq(0),
            self.ibuffer_full.eq(0),
            self.bp_right.eq(0),
            self.bp_wrong.eq(0),
            self.cf_valid.eq(0),
            self.cf_instr.eq(0),
            self.cf_pc.eq(0),
            self.cf_is_rvc.eq(0),
            self.cf_pred_taken.eq(0),
            self.cf_exception.eq(0),
        ]
        with module.If(self.reset | self.flush | self.fencei):
            module.d[f"{self.child_name}_sync"] += busy.eq(0)
        with module.Elif(request_fire):
            module.d[f"{self.child_name}_sync"] += [busy.eq(1), saved_addr.eq(self.req_addr)]
        with module.Elif(busy):
            module.d[f"{self.child_name}_sync"] += busy.eq(0)
        return module


class FrontendParent(Elaboratable):
    """Reduced executable V2 Frontend parent closure. / 可执行的精简 V2 前端父级闭包。"""

    # Construct parent controls, child boundaries, and observable frontend lanes. / 构造父级控制、子级边界及可观察前端通道。
    def __init__(self, configuration: FrontendTopConfig | dict[str, Any] | None = None,
                 injected_dependencies: dict[str, Any] | None = None) -> None:
        if configuration is None:
            self.configuration = FrontendTopConfig()
        elif isinstance(configuration, FrontendTopConfig):
            self.configuration = configuration
        else:
            fields = FrontendTopConfig.__dataclass_fields__
            self.configuration = FrontendTopConfig(**{key: value for key, value in dict(configuration).items()
                                                       if key in fields})
        cfg = self.configuration
        dependencies = injected_dependencies if isinstance(injected_dependencies, dict) else {}
        self.injected_dependencies = dependencies
        self.icache = dependencies.get("icache") or dependencies.get("ICache") or FrontendChildBoundary(cfg, "icache")
        self.instr_uncache = (dependencies.get("instr_uncache") or dependencies.get("InstrUncache")
                              or FrontendChildBoundary(cfg, "instr_uncache"))
        self.pipeline = dependencies.get("pipeline") or dependencies.get("FrontendPipeline")

        # Clock/reset and source-level Frontend.scala controls. / 时钟、复位及 Frontend.scala 源级控制。
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.reset_vector = Signal(cfg.paddr_bits, name="io_reset_vector")
        self.fencei = Signal(name="io_fencei")
        self.redirect_valid = Signal(name="io_backend_toFtq_redirect_valid")
        self.redirect_ftq_idx = Signal(cfg.ftq_idx_bits, name="io_backend_toFtq_redirect_ftqIdx")
        self.redirect_ftq_offset = Signal(cfg.ftq_offset_bits, name="io_backend_toFtq_redirect_ftqOffset")
        self.redirect_level = Signal(name="io_backend_toFtq_redirect_level")
        self.redirect_pc = Signal(cfg.vaddr_bits, name="io_backend_toFtq_redirect_pc")
        self.redirect_cfi_taken = Signal(name="io_backend_toFtq_redirect_cfiTaken")
        self.redirect_debug_ctrl = Signal(name="io_backend_toFtq_redirect_debugIsCtrl")
        self.redirect_debug_memvio = Signal(name="io_backend_toFtq_redirect_debugIsMemVio")
        self.backend_can_accept = Signal(name="io_backend_canAccept")
        self.wfi_req = Signal(name="io_backend_wfi_wfiReq")

        # Delayed CSR/SFENCE controls used by ICache/ITLB. / 提供给 ICache/ITLB 的延迟 CSR/SFENCE 控制。
        self.csr_pf_enable = Signal(name="io_csrCtrl_pf_enable")
        self.csr_fs_off = Signal(name="io_csrCtrl_fsIsOff")
        self.csr_bp_enable = Signal(5, name="io_csrCtrl_bp_enable")
        self.sfence_valid = Signal(name="io_sfence_valid")

        # Reduced fetch and uncache transactions. / 精简取指与非缓存事务。
        self.fetch_req_valid = Signal(name="io_fetch_req_valid")
        self.fetch_req_addr = Signal(cfg.vaddr_bits, name="io_fetch_req_addr")
        self.fetch_req_nextline = Signal(cfg.vaddr_bits, name="io_fetch_req_nextline")
        self.fetch_req_ready = Signal(name="io_fetch_req_ready")
        self.fetch_resp_valid = Signal(name="io_fetch_resp_valid")
        self.fetch_resp_data = Signal(cfg.instr_bits * 16, name="io_fetch_resp_data")
        self.fetch_resp_error = Signal(name="io_fetch_resp_error")
        self.uncache_req_valid = Signal(name="io_uncache_req_valid")
        self.uncache_req_addr = Signal(cfg.vaddr_bits, name="io_uncache_req_addr")
        self.uncache_req_ready = Signal(name="io_uncache_req_ready")
        self.uncache_resp_valid = Signal(name="io_uncache_resp_valid")
        self.uncache_resp_data = Signal(cfg.instr_bits * 2, name="io_uncache_resp_data")
        self.uncache_resp_error = Signal(name="io_uncache_resp_error")

        # Explicit parent-visible child status overrides. / 显式父级可见子级状态覆盖。
        self.icache_wfi_safe = Signal(name="io_icache_wfiSafe")
        self.instr_uncache_wfi_safe = Signal(name="io_instrUncache_wfiSafe")
        self.icache_error_valid = Signal(name="io_icache_error_valid")
        self.icache_error_bits = Signal(cfg.error_bits, name="io_icache_error_bits")
        self.ibuffer_full_in = Signal(name="io_ibuffer_full")
        self.bp_right_in = Signal(cfg.instr_bits, name="io_bp_right")
        self.bp_wrong_in = Signal(cfg.instr_bits, name="io_bp_wrong")

        # Parent outputs and observation points. / 父级输出及观测点。
        self.need_flush = Signal(name="io_needFlush")
        self.flush_control_redirect = Signal(name="io_flushControlRedirect")
        self.flush_mem_vio_redirect = Signal(name="io_flushMemVioRedirect")
        self.icache_fencei = Signal(name="io_icache_fencei")
        self.icache_flush = Signal(name="io_icache_flush")
        self.icache_wfi_req = Signal(name="io_icache_wfiReq")
        self.instr_uncache_wfi_req = Signal(name="io_instrUncache_wfiReq")
        self.wfi_safe = Signal(name="io_backend_wfi_wfiSafe")
        self.error_valid = Signal(name="io_error_ecc_error_valid")
        self.error_bits = Signal(cfg.error_bits, name="io_error_ecc_error_bits")
        self.reset_in_frontend = Signal(name="io_resetInFrontend")
        self.frontend_info_ibuf_full = Signal(name="io_frontendInfo_ibufFull")
        self.frontend_info_bp_right = Signal(cfg.instr_bits, name="io_frontendInfo_bpRight")
        self.frontend_info_bp_wrong = Signal(cfg.instr_bits, name="io_frontendInfo_bpWrong")
        self.cf_valid = Signal(cfg.fetch_width, name="io_backend_cfVec_valid")
        self.cf_instr = Signal(cfg.fetch_width * cfg.instr_bits, name="io_backend_cfVec_instr")
        self.cf_pc = Signal(cfg.fetch_width * cfg.vaddr_bits, name="io_backend_cfVec_pc")
        self.cf_is_rvc = Signal(cfg.fetch_width, name="io_backend_cfVec_isRVC")
        self.cf_pred_taken = Signal(cfg.fetch_width, name="io_backend_cfVec_predTaken")
        self.cf_exception = Signal(cfg.fetch_width, name="io_backend_cfVec_exception")
        self.ptw_req_valid = Signal(name="io_ptw_req_valid")
        self.ptw_req_vpn = Signal(max(1, cfg.vaddr_bits - 12), name="io_ptw_req_vpn")
        self.ptw_resp_ready = Signal(name="io_ptw_resp_ready")
        self.perf = [Signal(cfg.perf_bits, name=f"io_perf_{index}_value") for index in range(cfg.perf_count)]

    # Connect a child signal when the injected object implements the named contract. / 当注入对象实现命名合同时连接子级信号。
    def connect_child_signal(self, module: Module, child: Any, child_name: str,
                             attribute: str, value: Any) -> None:
        signal = getattr(child, attribute, None)
        if signal is not None:
            module.d.comb += signal.eq(value)
        del child_name

    # Elaborate delayed controls, child handshakes, error pipeline, and CF observations. / 展开延迟控制、子级握手、错误流水和 CF 观测。
    def elaborate(self, platform: Any) -> Module:
        del platform
        cfg = self.configuration
        module = Module()
        domain = ClockDomain("frontend_sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        module.domains.frontend_sync = domain
        module.submodules.icache = self.icache
        module.submodules.instr_uncache = self.instr_uncache
        if self.pipeline is not None:
            module.submodules.pipeline = self.pipeline

        # Child request/status wiring is intentionally attribute-based so a
        # future full child can be injected without importing a sibling Build.
        # 子级请求/状态连接仅按属性进行，以便未来完整子级注入且无需跨 Build 导入。
        for child, name, valid, addr, nextline in (
            (self.icache, "icache", self.fetch_req_valid, self.fetch_req_addr, self.fetch_req_nextline),
            (self.instr_uncache, "instr_uncache", self.uncache_req_valid, self.uncache_req_addr, self.uncache_req_addr),
        ):
            self.connect_child_signal(module, child, name, "clock", self.clock)
            self.connect_child_signal(module, child, name, "reset", self.reset)
            self.connect_child_signal(module, child, name, "flush", self.need_flush)
            self.connect_child_signal(module, child, name, "fencei", self.icache_fencei)
            self.connect_child_signal(module, child, name, "wfi_req",
                                      self.icache_wfi_req if name == "icache" else self.instr_uncache_wfi_req)
            self.connect_child_signal(module, child, name, "req_valid", valid)
            self.connect_child_signal(module, child, name, "req_addr", addr)
            self.connect_child_signal(module, child, name, "req_nextline", nextline)

        child_icache_ready = getattr(self.icache, "req_ready", self.fetch_req_ready)
        child_uncache_ready = getattr(self.instr_uncache, "req_ready", self.uncache_req_ready)
        child_fetch_resp_valid = getattr(self.icache, "resp_valid", self.fetch_resp_valid)
        child_fetch_resp_data = getattr(self.icache, "resp_data", self.fetch_resp_data)
        child_fetch_resp_error = getattr(self.icache, "resp_error", self.fetch_resp_error)
        child_uncache_resp_valid = getattr(self.instr_uncache, "resp_valid", self.uncache_resp_valid)
        child_uncache_resp_data = getattr(self.instr_uncache, "resp_data", self.uncache_resp_data)
        child_uncache_resp_error = getattr(self.instr_uncache, "resp_error", self.uncache_resp_error)
        module.d.comb += [
            self.fetch_req_ready.eq(child_icache_ready),
            self.fetch_resp_valid.eq(child_fetch_resp_valid),
            self.fetch_resp_data.eq(child_fetch_resp_data[:len(self.fetch_resp_data)]),
            self.fetch_resp_error.eq(child_fetch_resp_error),
            self.uncache_req_ready.eq(child_uncache_ready),
            self.uncache_resp_valid.eq(child_uncache_resp_valid),
            self.uncache_resp_data.eq(child_uncache_resp_data[:len(self.uncache_resp_data)]),
            self.uncache_resp_error.eq(child_uncache_resp_error),
        ]

        # Source Frontend.scala uses RegNext for redirect/fence and DelayN(1)
        # for WFI, then a second DelayN(1) for the returned safe indication.
        # Frontend.scala 对 redirect/fence 使用 RegNext，对 WFI 使用 DelayN(1)，
        # safe 返回再经过一个 DelayN(1)。
        need_flush_reg = Signal(name="needFlush_reg")
        control_redirect_reg = Signal(name="flushControlRedirect_reg")
        mem_vio_redirect_reg = Signal(name="flushMemVioRedirect_reg")
        fencei_reg = Signal(name="fencei_reg")
        wfi_req_reg = Signal(name="wfiReq_reg")
        csr_pf_reg_1 = Signal(name="csr_pf_reg_1")
        csr_pf_reg_2 = Signal(name="csr_pf_reg_2")
        csr_fs_reg_1 = Signal(name="csr_fs_reg_1")
        csr_fs_reg_2 = Signal(name="csr_fs_reg_2")
        csr_bp_reg_1 = Signal(5, name="csr_bp_reg_1")
        csr_bp_reg_2 = Signal(5, name="csr_bp_reg_2")
        sfence_reg_1 = Signal(name="sfence_reg_1")
        sfence_reg_2 = Signal(name="sfence_reg_2")
        error_valid_reg_1 = Signal(name="error_valid_reg_1")
        error_valid_reg_2 = Signal(name="error_valid_reg_2")
        error_bits_reg_1 = Signal(cfg.error_bits, name="error_bits_reg_1")
        error_bits_reg_2 = Signal(cfg.error_bits, name="error_bits_reg_2")
        wfi_safe_reg_1 = Signal(name="wfi_safe_reg_1")
        wfi_safe_reg_2 = Signal(name="wfi_safe_reg_2")
        ibuffer_full_reg = Signal(name="ibuffer_full_reg")
        module.d.frontend_sync += [
            need_flush_reg.eq(self.redirect_valid),
            control_redirect_reg.eq(self.redirect_debug_ctrl),
            mem_vio_redirect_reg.eq(self.redirect_debug_memvio),
            fencei_reg.eq(self.fencei),
            wfi_req_reg.eq(self.wfi_req),
            csr_pf_reg_1.eq(self.csr_pf_enable),
            csr_pf_reg_2.eq(csr_pf_reg_1),
            csr_fs_reg_1.eq(self.csr_fs_off),
            csr_fs_reg_2.eq(csr_fs_reg_1),
            csr_bp_reg_1.eq(self.csr_bp_enable),
            csr_bp_reg_2.eq(csr_bp_reg_1),
            sfence_reg_1.eq(self.sfence_valid),
            sfence_reg_2.eq(sfence_reg_1),
            error_valid_reg_1.eq(self.icache_error_valid),
            error_valid_reg_2.eq(error_valid_reg_1),
            error_bits_reg_1.eq(self.icache_error_bits),
            error_bits_reg_2.eq(error_bits_reg_1),
            wfi_safe_reg_1.eq(wfi_req_reg & self.icache_wfi_safe & self.instr_uncache_wfi_safe),
            wfi_safe_reg_2.eq(wfi_safe_reg_1),
            ibuffer_full_reg.eq(self.ibuffer_full_in),
        ]

        module.d.comb += [
            self.need_flush.eq(need_flush_reg),
            self.flush_control_redirect.eq(control_redirect_reg),
            self.flush_mem_vio_redirect.eq(mem_vio_redirect_reg),
            self.icache_fencei.eq(fencei_reg),
            self.icache_flush.eq(need_flush_reg),
            self.icache_wfi_req.eq(wfi_req_reg),
            self.instr_uncache_wfi_req.eq(wfi_req_reg),
            self.wfi_safe.eq(wfi_safe_reg_2),
            self.error_valid.eq(error_valid_reg_2),
            self.error_bits.eq(error_bits_reg_2),
            self.reset_in_frontend.eq(self.reset),
            self.frontend_info_ibuf_full.eq(ibuffer_full_reg),
            self.frontend_info_bp_right.eq(self.bp_right_in),
            self.frontend_info_bp_wrong.eq(self.bp_wrong_in),
            self.ptw_req_valid.eq(0),
            self.ptw_req_vpn.eq(self.fetch_req_addr[12:]),
            self.ptw_resp_ready.eq(~self.reset & ~need_flush_reg),
        ]

        # Forward a pipeline child when supplied; otherwise expose the ICache
        # child as the bounded CF-vector source and keep all metadata explicit.
        # 若提供 pipeline 子级则转发其 CF 向量，否则以 ICache 子级作为精简来源。
        source = self.pipeline if self.pipeline is not None else self.icache
        module.d.comb += [
            self.cf_valid.eq(getattr(source, "cf_valid", 0)),
            self.cf_instr.eq(getattr(source, "cf_instr", 0)),
            self.cf_pc.eq(getattr(source, "cf_pc", 0)),
            self.cf_is_rvc.eq(getattr(source, "cf_is_rvc", 0)),
            self.cf_pred_taken.eq(getattr(source, "cf_pred_taken", 0)),
            self.cf_exception.eq(getattr(source, "cf_exception", 0)),
        ]
        for index, perf_signal in enumerate(self.perf):
            # The reduced parent reports deterministic event lanes; injected
            # pipelines may override them through an optional ``perf`` array.
            # 精简父级报告确定性事件通道；注入 pipeline 可通过可选 perf 数组覆盖。
            external_perf = getattr(source, "perf", None)
            if isinstance(external_perf, (list, tuple)) and index < len(external_perf):
                module.d.comb += perf_signal.eq(external_perf[index])
            else:
                module.d.comb += perf_signal.eq(0)
        return module


# Preserve source-oriented aliases while exposing the project-facing UHSCTop. / 保留源导向别名并暴露项目侧 UHSCTop。
UHSCTop = FrontendParent
Frontend = FrontendParent


# =============================================================================
# Public Adapter
# =============================================================================
# Emit deterministic RTL using the final project-facing external name. / 使用最终项目侧外部名称输出确定性 RTL。
def build_verilog(configuration, injected_dependencies):
    """Return Verilog for the configured bounded Frontend parent. / 返回配置后的精简前端父级 Verilog。"""
    dependencies = injected_dependencies if isinstance(injected_dependencies, dict) else {}
    if isinstance(configuration, FrontendTopConfig):
        cfg = configuration
        options: dict[str, Any] = {}
    elif isinstance(configuration, dict):
        options = dict(configuration)
        fields = FrontendTopConfig.__dataclass_fields__
        cfg = FrontendTopConfig(**{key: value for key, value in options.items() if key in fields})
    else:
        options = {}
        cfg = FrontendTopConfig()
    top = UHSCTop(cfg, dependencies)
    ports: list[Any] = [
        top.clock, top.reset, top.reset_vector, top.fencei, top.redirect_valid,
        top.redirect_ftq_idx, top.redirect_ftq_offset, top.redirect_level,
        top.redirect_pc, top.redirect_cfi_taken, top.redirect_debug_ctrl,
        top.redirect_debug_memvio, top.backend_can_accept, top.wfi_req,
        top.csr_pf_enable, top.csr_fs_off, top.csr_bp_enable, top.sfence_valid,
        top.fetch_req_valid, top.fetch_req_addr, top.fetch_req_nextline,
        top.fetch_req_ready, top.fetch_resp_valid, top.fetch_resp_data,
        top.fetch_resp_error, top.uncache_req_valid, top.uncache_req_addr,
        top.uncache_req_ready, top.uncache_resp_valid, top.uncache_resp_data,
        top.uncache_resp_error, top.icache_wfi_safe, top.instr_uncache_wfi_safe,
        top.icache_error_valid, top.icache_error_bits, top.ibuffer_full_in,
        top.bp_right_in, top.bp_wrong_in, top.need_flush,
        top.flush_control_redirect, top.flush_mem_vio_redirect, top.icache_fencei,
        top.icache_flush, top.icache_wfi_req, top.instr_uncache_wfi_req,
        top.wfi_safe, top.error_valid, top.error_bits, top.reset_in_frontend,
        top.frontend_info_ibuf_full, top.frontend_info_bp_right,
        top.frontend_info_bp_wrong, top.cf_valid, top.cf_instr, top.cf_pc,
        top.cf_is_rvc, top.cf_pred_taken, top.cf_exception, top.ptw_req_valid,
        top.ptw_req_vpn, top.ptw_resp_ready,
    ] + top.perf
    name = str(options.get("module", options.get("name", "UHSCTop")))
    return verilog.convert(top, name=name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print the default parent export for a direct smoke invocation. / 直接 smoke 调用时打印默认父级导出。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
