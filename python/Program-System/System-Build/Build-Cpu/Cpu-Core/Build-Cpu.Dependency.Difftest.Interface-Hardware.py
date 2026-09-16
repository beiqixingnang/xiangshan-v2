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

from amaranth import Array, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
__all__ = [
    "DifftestConfig",
    "UHSCDifftestInterface",
    "DifftestInterface",
    "difftest_trace_step",
    "axi_lite_reference_step",
    "build_verilog",
    "main",
]


# Keep all selected hardware-bearing Difftest source paths auditable. / 显式记录选定的硬件相关 Difftest Scala 路径以便审计。
DIFFTEST_SOURCE_PATHS: tuple[str, ...] = (
    "Batch.scala", "Bundles.scala", "common/AXI4.scala", "common/AXI4Lite.scala",
    "common/AXI4Stream.scala", "common/FileControl.scala", "common/Flash.scala",
    "common/LogPerfControl.scala", "common/Mem.scala", "common/SDCard.scala",
    "common/WiringControl.scala", "Coverage.scala", "Delta.scala", "Difftest.scala",
    "DPIC.scala", "fpga/DifftestMemCtrl.scala", "fpga/Host.scala", "fpga/XDMAConfigBar.scala",
    "Gateway.scala", "plugin/topdown/TopdownDPI.scala", "plugin/topdown/TopdownIQInfo.scala",
    "plugin/topdown/TopdownRobInfo.scala", "Preprocess.scala", "Replay.scala", "SimTop.scala",
    "Squash.scala", "Trace.scala", "util/Compatibility.scala", "util/Delayer.scala",
    "util/Lookup.scala", "util/PipelineConnect.scala", "util/Profile.scala", "util/Query.scala",
    "util/SkidBufferConnect.scala", "Validate.scala",
)


# Cast Amaranth generator controls to the context-manager protocol. / 将 Amaranth 生成器控制转换为上下文管理器协议。
def amaranth_if(module: Module, condition: Any) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.If(condition))


# Cast an Amaranth elif branch to the context-manager protocol. / 将 Amaranth elif 分支转换为上下文管理器协议。
def amaranth_elif(module: Module, condition: Any) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.Elif(condition))


# Cast an Amaranth else branch to the context-manager protocol. / 将 Amaranth else 分支转换为上下文管理器协议。
def amaranth_else(module: Module) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.Else())


# Model one trace FIFO cycle with simultaneous push/pop. / 建模支持同周期入队/出队的 trace FIFO 周期。
def difftest_trace_step(queue: list[dict[str, int]], commit: Mapping[str, int] | None,
                        trace_ready: bool, depth: int) -> tuple[list[dict[str, int]], dict[str, int] | None, bool, bool]:
    """Return ``(next_queue, head, commit_ready, overflow)`` for a bounded trace queue. / 返回有界 trace 队列下一状态、队首、接收使能及溢出标志。"""

    if depth < 1:
        raise ValueError("trace depth must be positive")
    current = list(queue[:depth])
    head = current[0] if current else None
    pop = bool(head is not None and trace_ready)
    ready = len(current) < depth or pop
    overflow = bool(commit is not None and not ready)
    if pop:
        current.pop(0)
    if commit is not None and ready:
        current.append(dict(commit))
    return current, (current[0] if current else None), ready, overflow


# Model independent AXI-lite write/read control state. / 建模独立 AXI-lite 写/读控制状态。
def axi_lite_reference_step(state: Mapping[str, int], aw_valid: bool, aw_addr: int,
                            w_valid: bool, w_data: int, b_ready: bool,
                            ar_valid: bool, ar_addr: int, r_ready: bool,
                            trace_count: int) -> dict[str, int]:
    """Return next control handshakes and status data for one cycle. / 返回单周期控制握手及状态数据。"""

    next_state = {key: int(value) for key, value in state.items()}
    next_state.setdefault("aw_hold", 0); next_state.setdefault("w_hold", 0)
    next_state.setdefault("halted", 0); next_state.setdefault("error", 0)
    next_state.setdefault("b_valid", 0); next_state.setdefault("r_valid", 0)
    aw_ready = int(not next_state["aw_hold"] and not next_state["b_valid"])
    w_ready = int(not next_state["w_hold"] and not next_state["b_valid"])
    ar_ready = int(not next_state["r_valid"])
    if aw_valid and aw_ready:
        next_state["aw_hold"] = 1; next_state["aw_addr"] = int(aw_addr)
    if w_valid and w_ready:
        next_state["w_hold"] = 1; next_state["w_data"] = int(w_data)
    if next_state["aw_hold"] and next_state["w_hold"]:
        address = next_state.get("aw_addr", 0) & 0xFFFF
        data = next_state.get("w_data", 0)
        if address == 4:
            next_state["halted"] = data & 1
        elif address == 8 and data & 1:
            next_state["error"] = 0
        next_state["aw_hold"] = 0; next_state["w_hold"] = 0; next_state["b_valid"] = 1
    if next_state["b_valid"] and b_ready:
        next_state["b_valid"] = 0
    if ar_valid and ar_ready:
        address = int(ar_addr) & 0xFFFF
        next_state["r_data"] = trace_count if address == 0 else ((next_state["halted"] & 1) | ((next_state["error"] & 1) << 1))
        next_state["r_valid"] = 1
    if next_state["r_valid"] and r_ready:
        next_state["r_valid"] = 0
    next_state.update({"aw_ready": aw_ready, "w_ready": w_ready, "ar_ready": ar_ready})
    return next_state


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
        # Pointer-indexed storage mirrors MIMOQueue/CircularQueuePtr semantics
        # while retaining the original trace bundle ports. / 以指针索引存储
        # 对应 MIMOQueue/CircularQueuePtr 语义，同时保持原 trace bundle 端口。
        ptr_bits = max(1, (c.trace_depth - 1).bit_length())
        count = Signal.like(self.trace_count)
        head_ptr = Signal(ptr_bits, name="trace_head_ptr")
        tail_ptr = Signal(ptr_bits, name="trace_tail_ptr")
        pc_mem = Array(Signal(c.pc_bits, name=f"trace_pc_{i}") for i in range(c.trace_depth))
        inst_mem = Array(Signal(32, name=f"trace_inst_{i}") for i in range(c.trace_depth))
        rd_mem = Array(Signal(5, name=f"trace_rd_{i}") for i in range(c.trace_depth))
        data_mem = Array(Signal(c.xlen, name=f"trace_data_{i}") for i in range(c.trace_depth))
        priv_mem = Array(Signal(2, name=f"trace_priv_{i}") for i in range(c.trace_depth))
        wen_mem = Array(Signal(name=f"trace_wen_{i}") for i in range(c.trace_depth))

        # Independent AW/W holding registers implement AXI4-Lite's decoupled
        # channels; writes may arrive in either order. / 独立 AW/W 暂存寄存器
        # 实现 AXI4-Lite 解耦通道，允许任意顺序到达。
        aw_hold = Signal(name="axi_aw_hold")
        aw_addr_r = Signal(c.axi_addr_bits, name="axi_aw_addr_r")
        w_hold = Signal(name="axi_w_hold")
        w_data_r = Signal(c.axi_data_bits, name="axi_w_data_r")
        b_pending = Signal(name="axi_b_pending")
        ar_pending = Signal(name="axi_ar_pending")
        ar_addr_r = Signal(c.axi_addr_bits, name="axi_ar_addr_r")
        read_data = Signal(c.axi_data_bits, name="axi_read_data")
        halt_reg = Signal(name="difftest_halted")
        error_reg = Signal(name="difftest_error")

        pop = self.trace_valid & self.trace_ready
        # A full queue may accept a commit in the same cycle as a trace pop.
        # / 队列满时允许与 trace 出队同周期接收 commit。
        m.d.comb += [
            self.commit_ready.eq(~halt_reg & ((count < c.trace_depth) | pop)),
            self.trace_valid.eq(count != 0),
            self.trace_pc.eq(pc_mem[head_ptr]), self.trace_inst.eq(inst_mem[head_ptr]),
            self.trace_priv.eq(priv_mem[head_ptr]), self.trace_wen.eq(wen_mem[head_ptr]),
            self.trace_rd.eq(rd_mem[head_ptr]), self.trace_data.eq(data_mem[head_ptr]),
            self.trace_count.eq(count), self.halted.eq(halt_reg), self.error.eq(error_reg),
            self.axi_aw_ready.eq(~aw_hold & ~b_pending), self.axi_w_ready.eq(~w_hold & ~b_pending),
            self.axi_b_valid.eq(b_pending), self.axi_ar_ready.eq(~ar_pending),
            self.axi_r_valid.eq(ar_pending), self.axi_r_data.eq(read_data),
        ]
        aw_accept = self.axi_aw_valid & self.axi_aw_ready
        w_accept = self.axi_w_valid & self.axi_w_ready
        write_complete = (aw_hold | aw_accept) & (w_hold | w_accept)
        write_addr = Mux(aw_hold, aw_addr_r, self.axi_aw_addr)
        write_data = Mux(w_hold, w_data_r, self.axi_w_data)
        control_flush = write_complete & (write_addr[:4] == 0) & write_data[0]
        push = self.commit_valid & self.commit_ready

        def ptr_inc(ptr: Signal) -> Any:
            """Wrap a trace pointer at a non-power-of-two depth. / 在非二次幂深度处回绕 trace 指针。"""

            return Mux(ptr == c.trace_depth - 1, 0, ptr + 1)

        with amaranth_if(m, self.reset):
            m.d.difftest += [count.eq(0), head_ptr.eq(0), tail_ptr.eq(0),
                             aw_hold.eq(0), w_hold.eq(0), b_pending.eq(0),
                             ar_pending.eq(0), halt_reg.eq(0), error_reg.eq(0),
                             read_data.eq(0)]
        with amaranth_else(m):
            # A control write at address zero flushes only trace storage; the
            # AXI response still completes normally. / 地址零控制写仅清空
            # trace 存储，AXI 响应仍正常完成。
            with amaranth_if(m, control_flush):
                m.d.difftest += [count.eq(0), head_ptr.eq(0), tail_ptr.eq(0)]
            with amaranth_if(m, push & ~control_flush):
                m.d.difftest += [pc_mem[tail_ptr].eq(self.commit_pc),
                                 inst_mem[tail_ptr].eq(self.commit_inst), rd_mem[tail_ptr].eq(self.commit_rd),
                                 data_mem[tail_ptr].eq(self.commit_data), priv_mem[tail_ptr].eq(self.commit_priv),
                                 wen_mem[tail_ptr].eq(self.commit_wen), tail_ptr.eq(ptr_inc(tail_ptr))]
            with amaranth_if(m, pop & ~control_flush):
                m.d.difftest += head_ptr.eq(ptr_inc(head_ptr))
            with amaranth_if(m, push & ~pop & ~control_flush):
                m.d.difftest += count.eq(count + 1)
            with amaranth_elif(m, pop & ~push & ~control_flush):
                m.d.difftest += count.eq(count - 1)
            # Sticky overflow/error state catches a commit blocked by halt or
            # a full queue. / 粘滞错误状态捕获 halt 或满队列导致的阻塞提交。
            with amaranth_if(m, self.commit_valid & ~self.commit_ready):
                m.d.difftest += error_reg.eq(1)

            with amaranth_if(m, aw_accept):
                m.d.difftest += [aw_hold.eq(1), aw_addr_r.eq(self.axi_aw_addr)]
            with amaranth_if(m, w_accept):
                m.d.difftest += [w_hold.eq(1), w_data_r.eq(self.axi_w_data)]
            with amaranth_if(m, write_complete):
                m.d.difftest += [aw_hold.eq(0), w_hold.eq(0), b_pending.eq(1)]
                with amaranth_if(m, (write_addr[:4] == 4) & cast(Any, write_data[0])):
                    m.d.difftest += halt_reg.eq(1)
                with amaranth_if(m, (write_addr[:4] == 8) & cast(Any, write_data[0])):
                    m.d.difftest += halt_reg.eq(0)
                with amaranth_if(m, (write_addr[:4] == 12) & cast(Any, write_data[0])):
                    m.d.difftest += error_reg.eq(0)
            with amaranth_if(m, self.axi_b_valid & self.axi_b_ready):
                m.d.difftest += b_pending.eq(0)
            with amaranth_if(m, self.axi_ar_valid & self.axi_ar_ready):
                m.d.difftest += [ar_pending.eq(1), ar_addr_r.eq(self.axi_ar_addr),
                                 read_data.eq(Mux(self.axi_ar_addr[:4] == 0, self.trace_count,
                                                  (halt_reg | (error_reg << 1))))]
            with amaranth_if(m, self.axi_r_valid & self.axi_r_ready):
                m.d.difftest += ar_pending.eq(0)
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
