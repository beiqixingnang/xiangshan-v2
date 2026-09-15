"""UHSC Kunminghu V2 Difftest hardware-facing interface aggregate.
昆明湖 V2 Difftest 硬件接口聚合边界。

The 35 vendored Difftest Scala sources are represented by one explicit
trace/commit and AXI-lite control boundary. Simulation-only DPI/C++ harnesses
remain outside this Build target.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Mapping, cast

from amaranth import Array, ClockDomain, Elaboratable, Module, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
__all__ = ["DifftestConfig", "UHSCDifftestInterface", "DifftestInterface", "build_verilog", "main"]


# Cast Amaranth generator controls to the context-manager protocol. / 将 Amaranth 生成器控制转换为上下文管理器协议。
def amaranth_if(module: Module, condition: Any) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.If(condition))


# Cast an Amaranth else branch to the context-manager protocol. / 将 Amaranth else 分支转换为上下文管理器协议。
def amaranth_else(module: Module) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.Else())


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class DifftestConfig:
    xlen: int = 64
    pc_bits: int = 50
    trace_depth: int = 4
    axi_addr_bits: int = 32
    axi_data_bits: int = 32

    def __post_init__(self) -> None:
        if self.xlen != 64 or self.pc_bits < 32:
            raise ValueError("V2 Difftest requires XLEN=64 and PC width >= 32")
        if self.trace_depth < 1 or self.trace_depth > 16:
            raise ValueError("trace_depth must be in [1, 16]")
        if self.axi_data_bits != 32 or self.axi_addr_bits < 8:
            raise ValueError("AXI-lite geometry is fixed at 32-bit data")


# =============================================================================
# Implementation
# =============================================================================
class UHSCDifftestInterface(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Trace FIFO and AXI-lite status/control boundary."""

    def __init__(self, configuration: DifftestConfig | None = None) -> None:
        self.config = configuration or DifftestConfig()
        c = self.config
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.commit_valid = Signal(name="io_commit_valid")
        self.commit_pc = Signal(c.pc_bits, name="io_commit_pc")
        self.commit_inst = Signal(32, name="io_commit_inst")
        self.commit_priv = Signal(2, name="io_commit_priv")
        self.commit_wen = Signal(name="io_commit_wen")
        self.commit_rd = Signal(5, name="io_commit_rd")
        self.commit_data = Signal(c.xlen, name="io_commit_data")
        self.commit_ready = Signal(name="io_commit_ready")
        self.trace_valid = Signal(name="io_trace_valid")
        self.trace_pc = Signal(c.pc_bits, name="io_trace_pc")
        self.trace_inst = Signal(32, name="io_trace_inst")
        self.trace_priv = Signal(2, name="io_trace_priv")
        self.trace_wen = Signal(name="io_trace_wen")
        self.trace_rd = Signal(5, name="io_trace_rd")
        self.trace_data = Signal(c.xlen, name="io_trace_data")
        self.trace_ready = Signal(name="io_trace_ready")
        self.axi_aw_valid = Signal(name="io_axi_aw_valid")
        self.axi_aw_ready = Signal(name="io_axi_aw_ready")
        self.axi_aw_addr = Signal(c.axi_addr_bits, name="io_axi_aw_addr")
        self.axi_w_valid = Signal(name="io_axi_w_valid")
        self.axi_w_ready = Signal(name="io_axi_w_ready")
        self.axi_w_data = Signal(c.axi_data_bits, name="io_axi_w_data")
        self.axi_b_valid = Signal(name="io_axi_b_valid")
        self.axi_b_ready = Signal(name="io_axi_b_ready")
        self.axi_ar_valid = Signal(name="io_axi_ar_valid")
        self.axi_ar_ready = Signal(name="io_axi_ar_ready")
        self.axi_ar_addr = Signal(c.axi_addr_bits, name="io_axi_ar_addr")
        self.axi_r_valid = Signal(name="io_axi_r_valid")
        self.axi_r_ready = Signal(name="io_axi_r_ready")
        self.axi_r_data = Signal(c.axi_data_bits, name="io_axi_r_data")
        self.halted = Signal(name="io_halted")
        self.error = Signal(name="io_error")
        self.trace_count = Signal(max(1, (c.trace_depth + 1).bit_length()), name="io_trace_count")

    def elaborate(self, platform: Any) -> Module:
        del platform
        c = self.config
        m = Module()
        domain = ClockDomain("difftest", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.difftest = domain
        count = Signal.like(self.trace_count)
        pc_mem = Array(Signal(c.pc_bits, name=f"trace_pc_{i}") for i in range(c.trace_depth))
        inst_mem = Array(Signal(32, name=f"trace_inst_{i}") for i in range(c.trace_depth))
        rd_mem = Array(Signal(5, name=f"trace_rd_{i}") for i in range(c.trace_depth))
        data_mem = Array(Signal(c.xlen, name=f"trace_data_{i}") for i in range(c.trace_depth))
        m.d.comb += [
            self.commit_ready.eq(count < c.trace_depth),
            self.trace_valid.eq(count != 0),
            self.trace_pc.eq(pc_mem[0]), self.trace_inst.eq(inst_mem[0]),
            self.trace_priv.eq(self.commit_priv), self.trace_wen.eq(self.commit_wen),
            self.trace_rd.eq(rd_mem[0]), self.trace_data.eq(data_mem[0]),
            self.axi_aw_ready.eq(~self.axi_b_valid), self.axi_w_ready.eq(~self.axi_b_valid),
            self.axi_b_valid.eq(self.axi_aw_valid & self.axi_w_valid),
            self.axi_ar_ready.eq(~self.axi_r_valid), self.axi_r_valid.eq(self.axi_ar_valid),
            self.axi_r_data.eq(self.trace_count), self.halted.eq(0), self.error.eq(0),
            self.trace_count.eq(count),
        ]
        with amaranth_if(m, self.reset):
            m.d.difftest += count.eq(0)
        with amaranth_else(m):
            with amaranth_if(m, self.commit_valid & self.commit_ready):
                m.d.difftest += [count.eq(count + 1), pc_mem[count].eq(self.commit_pc),
                                 inst_mem[count].eq(self.commit_inst), rd_mem[count].eq(self.commit_rd),
                                 data_mem[count].eq(self.commit_data)]
            with amaranth_if(m, self.trace_valid & self.trace_ready):
                m.d.difftest += count.eq(count - 1)
        return m


DifftestInterface = UHSCDifftestInterface


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration: DifftestConfig | Mapping[str, Any] | None,
                  injected_dependencies: Mapping[str, Any]) -> str:
    del injected_dependencies
    if configuration is None:
        cfg, name = DifftestConfig(), "UHSCDifftestInterface"
    elif isinstance(configuration, DifftestConfig):
        cfg, name = configuration, "UHSCDifftestInterface"
    else:
        cfg = DifftestConfig(**{k: v for k, v in dict(configuration).items() if k in DifftestConfig.__dataclass_fields__})
        name = str(configuration.get("module", "UHSCDifftestInterface"))
    top = UHSCDifftestInterface(cfg)
    ports = [top.clock, top.reset, top.commit_valid, top.commit_pc, top.commit_inst, top.commit_priv,
             top.commit_wen, top.commit_rd, top.commit_data, top.commit_ready, top.trace_valid,
             top.trace_pc, top.trace_inst, top.trace_priv, top.trace_wen, top.trace_rd, top.trace_data,
             top.trace_ready, top.axi_aw_valid, top.axi_aw_ready, top.axi_aw_addr, top.axi_w_valid,
             top.axi_w_ready, top.axi_w_data, top.axi_b_valid, top.axi_b_ready, top.axi_ar_valid,
             top.axi_ar_ready, top.axi_ar_addr, top.axi_r_valid, top.axi_r_ready, top.axi_r_data,
             top.halted, top.error, top.trace_count]
    return verilog.convert(top, name=name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
