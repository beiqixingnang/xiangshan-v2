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

from amaranth import ClockDomain, Elaboratable, Module, Signal
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

    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        domain = ClockDomain("sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.sync = domain

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
            self.cf_valid.eq(0),
            self.cf_instr.eq(0),
            self.cf_pc.eq(0),
            self.redirect_valid.eq(0),
            self.redirect_pc.eq(0),
            self.backend_can_accept.eq(0),
            self.mem_a_ready.eq(0),
            self.mem_d_ready.eq(0),
            self.cpu_halted.eq(1),
            self.critical_error.eq(0),
            self.closure_missing.eq(1),
            self.closure_missing_count.eq(3),
        ]
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
    ]
    return verilog.convert(top, name="UHSCTop", ports=ports, emit_src=False)


def main() -> None:
    print(build_verilog())


if __name__ == "__main__":
    main()
