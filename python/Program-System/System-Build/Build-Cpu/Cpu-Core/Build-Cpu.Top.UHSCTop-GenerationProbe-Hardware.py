"""UHSC Kunminghu V2 top-level generation probe.
昆明湖 V2 顶层生成探针。

This target is intentionally a boundary probe.  It gives the eventual
``UHSCTop`` adapter a deterministic Amaranth surface and can be converted to
SystemVerilog today, while making the still-open XSCore/L2Top/XSTile closure
explicit.  It must not be treated as a complete Kunminghu implementation:
the independent evidence records ``BLOCKED_MISSING_CLOSURES`` until those
children are bound and the full XSTop inventory is matched.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amaranth import Elaboratable, Module, Signal
from amaranth.back import verilog


__all__ = ["UHSCTopConfig", "UHSCTop", "build_verilog", "main"]


@dataclass(frozen=True)
class UHSCTopConfig:
    """Locked DefaultConfig geometry used by the top-level probe.
    锁定 DefaultConfig 顶层探针所使用的几何参数。
    """

    xlen: int = 64
    vaddr_bits: int = 50
    paddr_bits: int = 48
    fetch_width: int = 6
    num_cores: int = 1

    def __post_init__(self) -> None:
        if self.xlen != 64:
            raise ValueError("Kunminghu V2 probe uses XLEN=64")
        if self.vaddr_bits < self.paddr_bits or self.paddr_bits < 8:
            raise ValueError("address widths are inconsistent")
        if self.fetch_width != 6:
            raise ValueError("Kunminghu V2 fetch width is six")
        if self.num_cores < 1:
            raise ValueError("num_cores must be positive")


class UHSCTop(Elaboratable):
    """Deterministic top adapter surface used by the full-generation gate.
    供完整生成门禁使用的确定性顶层适配器表面。

    The ports follow the top-level control, interrupt, trace, and memory
    observations needed to connect XSCore, L2Top, and XSTile.  Until those
    children are implemented, the probe drives quiescent values and exposes
    explicit ``closure_missing`` status rather than silently fabricating a
    core.  This makes the generated artifact useful for wiring/lint checks
    without overstating equivalence.
    """

    def __init__(
        self,
        configuration: UHSCTopConfig | dict[str, Any] | None = None,
        injected_dependencies: dict[str, Any] | None = None,
    ) -> None:
        if configuration is None:
            self.config = UHSCTopConfig()
        elif isinstance(configuration, UHSCTopConfig):
            self.config = configuration
        else:
            fields = UHSCTopConfig.__dataclass_fields__
            self.config = UHSCTopConfig(
                **{k: v for k, v in dict(configuration).items() if k in fields}
            )
        # Dependency objects are metadata only at the probe stage.  The
        # eventual closure binder will connect these names to real children.
        self.injected_dependencies = dict(injected_dependencies or {})
        self.frontend = self.injected_dependencies.get("frontend")
        self.backend = self.injected_dependencies.get("backend")
        self.mem_block = self.injected_dependencies.get("mem_block") or self.injected_dependencies.get("memblock")
        self.coupled_l2 = self.injected_dependencies.get("coupled_l2") or self.injected_dependencies.get("coupledL2")
        cfg = self.config

        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.reset_vector = Signal(cfg.paddr_bits, name="io_reset_vector")
        self.hart_id = Signal(6, name="io_hartId")
        self.external_interrupt = Signal(7, name="io_externalInterrupt")
        self.timer_interrupt = Signal(name="io_timerInterrupt")
        self.software_interrupt = Signal(name="io_softwareInterrupt")
        self.debug_req = Signal(name="io_debug_req_valid")
        self.debug_resp_ready = Signal(name="io_debug_resp_ready")

        # Frontend/backend observation lanes. / 前端、后端观测通道。
        self.cf_valid = Signal(cfg.fetch_width, name="io_cfVec_valid")
        self.cf_instr = Signal(cfg.fetch_width * 32, name="io_cfVec_instr")
        self.cf_pc = Signal(cfg.fetch_width * cfg.vaddr_bits, name="io_cfVec_pc")
        self.redirect_valid = Signal(name="io_redirect_valid")
        self.redirect_pc = Signal(cfg.vaddr_bits, name="io_redirect_pc")
        self.backend_can_accept = Signal(name="io_backend_canAccept")

        # Simplified TileLink-like memory boundary retained for top wiring.
        # 保留用于顶层连线的简化 TileLink 类存储边界。
        self.mem_a_valid = Signal(name="io_mem_a_valid")
        self.mem_a_ready = Signal(name="io_mem_a_ready")
        self.mem_a_address = Signal(cfg.paddr_bits, name="io_mem_a_address")
        self.mem_a_opcode = Signal(3, name="io_mem_a_opcode")
        self.mem_a_data = Signal(128, name="io_mem_a_data")
        self.mem_d_valid = Signal(name="io_mem_d_valid")
        self.mem_d_ready = Signal(name="io_mem_d_ready")
        self.mem_d_data = Signal(128, name="io_mem_d_data")
        self.mem_d_denied = Signal(name="io_mem_d_denied")

        # Top-level status and closure diagnostics. / 顶层状态及闭包诊断。
        self.cpu_halted = Signal(name="io_cpu_halted")
        self.critical_error = Signal(name="io_critical_error")
        self.closure_missing = Signal(name="io_closure_missing")
        self.closure_missing_count = Signal(3, name="io_closure_missing_count")
        self.closure_complete = Signal(name="io_closure_complete")

    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()

        # Bind supplied parent/family closures into one hierarchy.  The top
        # file does not import sibling Build files (the rewrite rules forbid
        # that); validators load those files and inject the Elaboratable
        # instances explicitly.  A missing child therefore remains visible as
        # a diagnostic instead of being silently replaced by a fake module.
        children = {
            "frontend": self.frontend,
            "backend": self.backend,
            "mem_block": self.mem_block,
            "coupled_l2": self.coupled_l2,
        }
        for name, child in children.items():
            if child is not None:
                setattr(m.submodules, name, child)

        def wire(dst: Any, src: Any) -> None:
            """Connect compatible Amaranth signals with source-width adaptation.
            连接兼容的 Amaranth 信号并自动适配位宽。
            """

            if dst is None or src is None:
                return
            try:
                m.d.comb += dst.eq(src)
            except (AttributeError, TypeError, ValueError):
                # A boundary may intentionally omit an optional lane; leave
                # the omission for the closure audit rather than failing
                # elaboration of the probe itself.
                return

        def sig(obj: Any, name: str) -> Any:
            return getattr(obj, name, None) if obj is not None else None

        # Clock/reset fanout and Frontend <-> Backend control/data path.
        for child in (self.frontend, self.backend, self.mem_block, self.coupled_l2):
            wire(sig(child, "clock"), self.clock)
            wire(sig(child, "reset"), self.reset)
        f, b, mem, l2 = self.frontend, self.backend, self.mem_block, self.coupled_l2
        for top_name, child_name in (("reset_vector", "reset_vector"), ("fencei", "fencei")):
            wire(sig(f, child_name), sig(self, top_name))
        wire(sig(b, "backend_can_accept"), self.backend_can_accept)
        # Backend receives the Frontend control-flow vector and returns
        # redirects/admission.  Width adaptation is intentional for the
        # bounded exception/metadata surfaces.
        for child_name, src_name in (("frontend_valid", "cf_valid"), ("frontend_instr", "cf_instr"),
                                     ("frontend_pc", "cf_pc"), ("frontend_exception", "cf_valid")):
            wire(sig(b, child_name), sig(f, src_name))
        wire(sig(f, "backend_can_accept"), sig(b, "frontend_can_accept"))
        wire(sig(f, "redirect_valid"), sig(b, "redirect_valid"))
        wire(sig(f, "redirect_pc"), sig(b, "redirect_pc"))
        wire(sig(self, "cf_valid"), sig(f, "cf_valid"))
        wire(sig(self, "cf_instr"), sig(f, "cf_instr"))
        wire(sig(self, "cf_pc"), sig(f, "cf_pc"))
        wire(sig(self, "redirect_valid"), sig(b, "redirect_valid"))
        wire(sig(self, "redirect_pc"), sig(b, "redirect_pc"))
        wire(self.cpu_halted, sig(b, "cpu_halted"))
        wire(self.critical_error, sig(b, "cpu_critical_error"))

        # MemBlock <-> CoupledL2 A/D transaction bridge.  The bridge keeps the
        # reduced TileLink channels executable while preserving explicit
        # injection points for the still-open Diplomacy closure.
        if mem is not None and l2 is not None:
            for suffix in ("valid", "opcode", "source", "address", "data", "mask"):
                wire(sig(l2, f"in_a_{'bits_' if suffix not in {'valid'} else ''}{suffix}"),
                     sig(mem, f"tl_a_{suffix}"))
            wire(sig(mem, "tl_a_ready"), sig(l2, "in_a_ready"))
            # External D response enters through UHSCTop and is forwarded to
            # both the MemBlock and CoupledL2 input boundary.  MemBlock has no
            # separate tl_d_ready lane, so the top-level ready is sourced from
            # the slice's in_d_ready observation.
            wire(sig(mem, "tl_d_valid"), self.mem_d_valid)
            wire(sig(mem, "tl_d_data"), self.mem_d_data)
            for suffix in ("valid", "opcode", "source", "address", "data", "mask"):
                wire(sig(self, f"mem_a_{'valid' if suffix == 'valid' else suffix}"),
                     sig(l2, f"out_a_{'bits_' if suffix != 'valid' else ''}{suffix}"))
            wire(sig(l2, "out_a_ready"), self.mem_a_ready)
            # The external D response is an input; only ready is driven by the
            # localized hierarchy.  Outgoing slice D fields remain internal
            # until the complete XSTile/L2Top adapter is available.

        # Consume every boundary input through a private sink so Amaranth
        # preserves its input direction in the generated ANSI port list.
        # 通过私有汇聚信号消费所有边界输入，确保生成 ANSI 端口方向稳定为 input。
        boundary_inputs = (
            self.reset_vector,
            self.hart_id,
            self.external_interrupt,
            self.timer_interrupt,
            self.software_interrupt,
            self.debug_req,
            self.debug_resp_ready,
            self.mem_a_valid,
            self.mem_a_address,
            self.mem_a_opcode,
            self.mem_a_data,
            self.mem_d_valid,
            self.mem_d_data,
            self.mem_d_denied,
        )
        for index, signal in enumerate(boundary_inputs):
            sink = Signal(len(signal), name=f"_boundary_input_sink_{index}")
            m.d.comb += sink.eq(signal)

        # The probe is quiescent by construction.  No unimplemented child is
        # represented as a fake datapath; the missing-closure flag remains
        # asserted until XSCore, L2Top, and XSTile are bound.
        m.d.comb += [
            self.mem_d_ready.eq(0),
            self.closure_missing.eq(1),
            self.closure_missing_count.eq(
                sum(1 for child in children.values() if child is None)
            ),
            self.closure_complete.eq(0),
        ]
        if self.frontend is None:
            m.d.comb += [self.cf_valid.eq(0), self.cf_instr.eq(0), self.cf_pc.eq(0)]
        if self.backend is None:
            m.d.comb += [self.redirect_valid.eq(0), self.redirect_pc.eq(0), self.backend_can_accept.eq(0),
                         self.cpu_halted.eq(1), self.critical_error.eq(0)]
        return m


def build_verilog(
    configuration: UHSCTopConfig | dict[str, Any] | None = None,
    injected_dependencies: dict[str, Any] | None = None,
) -> str:
    """Convert the deterministic top probe to SystemVerilog.
    将确定性顶层探针转换为 SystemVerilog。
    """

    top = UHSCTop(configuration, injected_dependencies)
    ports = [
        top.clock,
        top.reset,
        top.reset_vector,
        top.hart_id,
        top.external_interrupt,
        top.timer_interrupt,
        top.software_interrupt,
        top.debug_req,
        top.debug_resp_ready,
        top.cf_valid,
        top.cf_instr,
        top.cf_pc,
        top.redirect_valid,
        top.redirect_pc,
        top.backend_can_accept,
        top.mem_a_valid,
        top.mem_a_ready,
        top.mem_a_address,
        top.mem_a_opcode,
        top.mem_a_data,
        top.mem_d_valid,
        top.mem_d_ready,
        top.mem_d_data,
        top.mem_d_denied,
        top.cpu_halted,
        top.critical_error,
        top.closure_missing,
        top.closure_missing_count,
        top.closure_complete,
    ]
    options = configuration if isinstance(configuration, dict) else {}
    module_name = str(options.get("module", options.get("name", "UHSCTop")))
    return verilog.convert(top, name=module_name, ports=ports, emit_src=False)


def main() -> None:
    print(build_verilog())


if __name__ == "__main__":
    main()
