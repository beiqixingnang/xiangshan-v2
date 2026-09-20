"""UHSC Kunminghu V2 frontend TileLink bridge closure.
昆明湖 V2 前端 TileLink 桥闭包。

The V2 ``FrontendBridge`` in ``MemBlock.scala`` is intentionally small: each
of its three edges is implemented as two ``BufferParams.default`` queues.
This aggregate keeps that topology and the width/constant transformations
visible, without importing another Build file or the generated reference.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Iterable, Sequence, cast

from amaranth import ClockDomain, Elaboratable, Module, ResetSignal, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
__all__ = [
    'FrontendBridgeConfig',
    'FrontendBridge',
    'ICacheBuffer',
    'ICacheCtrlBuffer',
    'InstrUncacheBuffer',
    'build_verilog',
    'main',
]


# Frozen V2 source boundary for the frontend bridge aggregate. /
# 前端桥聚合的冻结 V2 源边界。


# Cast Amaranth generator controls to the context-manager protocol. / 将 Amaranth 生成器控制转换为上下文管理器协议。
def amaranth_if(module: Module, condition: Any) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.If(condition))


# Cast an Amaranth elif branch to the context-manager protocol. / 将 Amaranth elif 分支转换为上下文管理器协议。
def amaranth_elif(module: Module, condition: Any) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.Elif(condition))


# Cast an Amaranth else branch to the context-manager protocol. / 将 Amaranth else 分支转换为上下文管理器协议。
def amaranth_else(module: Module) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.Else())


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class FrontendBridgeConfig:
    """Fixed V2 widths for the three frontend TileLink edges. / 前端三条 TileLink 边的固定 V2 位宽。"""

    address_bits: int = 48
    instruction_data_bits: int = 256
    control_data_bits: int = 64
    source_bits: int = 4

    # Validate the widths captured from the selected V2 DefaultConfig. / 校验选定 V2 DefaultConfig 捕获的位宽。
    def __post_init__(self) -> None:
        if self.address_bits != 48 or self.instruction_data_bits != 256:
            raise ValueError("Kunminghu V2 frontend bridge requires 48-bit addresses and 256-bit I-cache data")
        if self.control_data_bits != 64 or self.source_bits != 4:
            raise ValueError("Kunminghu V2 frontend bridge requires 64-bit control data and four-bit I-cache source")


# =============================================================================
# Implementation
# =============================================================================
class TwoEntryQueue(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """A fall-through-free two-entry Decoupled queue. / 无旁路的两项 Decoupled 队列。"""

    # Construct a queue with one signal per packed payload field. / 按每个打包字段构造队列信号。
    def __init__(self, widths: Sequence[int], prefix: str) -> None:
        if not widths or any(int(width) < 1 for width in widths):
            raise ValueError("TwoEntryQueue requires positive payload widths")
        self.widths = tuple(int(width) for width in widths)
        self.prefix = prefix
        self.enq_valid = Signal(name=f"{prefix}_enq_valid")
        self.enq_ready = Signal(name=f"{prefix}_enq_ready")
        self.deq_valid = Signal(name=f"{prefix}_deq_valid")
        self.deq_ready = Signal(name=f"{prefix}_deq_ready")
        self.enq_bits = [Signal(width, name=f"{prefix}_enq_{index}")
                         for index, width in enumerate(self.widths)]
        self.deq_bits = [Signal(width, name=f"{prefix}_deq_{index}")
                         for index, width in enumerate(self.widths)]

    # Elaborate count-based storage with simultaneous enqueue/dequeue support. / 展开支持同拍入队出队的计数存储。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        count = Signal(2, name=f"{self.prefix}_count")
        valid = count != 0
        pop = valid & self.deq_ready
        # Chisel ``Queue(2)`` exposes ``~full`` on enqueue; it does not
        # advertise a same-cycle replacement when both slots are occupied.
        # This detail is observable at the FrontendBridge boundary.
        push = self.enq_valid & (count < 2)
        m.d.comb += [self.enq_ready.eq(count < 2),
                     self.deq_valid.eq(valid)]
        # The two data registers keep payload widths explicit and deterministic.
        data0 = [Signal(width, name=f"{self.prefix}_data0_{index}")
                 for index, width in enumerate(self.widths)]
        data1 = [Signal(width, name=f"{self.prefix}_data1_{index}")
                 for index, width in enumerate(self.widths)]
        for output, source in zip(self.deq_bits, data0):
            m.d.comb += output.eq(source)

        with amaranth_if(m, pop):
            with amaranth_if(m, count == 2):
                for dst, src in zip(data0, data1):
                    m.d.sync += dst.eq(src)
                with amaranth_if(m, push):
                    for dst, src in zip(data1, self.enq_bits):
                        m.d.sync += dst.eq(src)
                    m.d.sync += count.eq(2)
                with amaranth_else(m):
                    m.d.sync += count.eq(1)
            with amaranth_else(m):
                with amaranth_if(m, push):
                    for dst, src in zip(data0, self.enq_bits):
                        m.d.sync += dst.eq(src)
                    m.d.sync += count.eq(1)
                with amaranth_else(m):
                    m.d.sync += count.eq(0)
        with amaranth_elif(m, push):
            with amaranth_if(m, count == 0):
                for dst, src in zip(data0, self.enq_bits):
                    m.d.sync += dst.eq(src)
                m.d.sync += count.eq(1)
            with amaranth_else(m):
                for dst, src in zip(data1, self.enq_bits):
                    m.d.sync += dst.eq(src)
                m.d.sync += count.eq(2)
        with amaranth_if(m, ResetSignal("sync")):
            m.d.sync += count.eq(0)
        return m


class BufferedEdge(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Two queues in series, matching ``Buffer(default(default(edge)))``. / 两级串联队列，对应双重默认 Buffer。"""

    # Construct the two queue stages and expose edge-level handshakes. / 构造两级队列并暴露边界握手。
    def __init__(self, widths: Sequence[int], prefix: str) -> None:
        self.widths = tuple(int(width) for width in widths)
        self.prefix = prefix
        self.in_valid = Signal(name=f"{prefix}_in_valid")
        self.in_ready = Signal(name=f"{prefix}_in_ready")
        self.out_valid = Signal(name=f"{prefix}_out_valid")
        self.out_ready = Signal(name=f"{prefix}_out_ready")
        self.in_bits = [Signal(width, name=f"{prefix}_in_{index}")
                        for index, width in enumerate(self.widths)]
        self.out_bits = [Signal(width, name=f"{prefix}_out_{index}")
                         for index, width in enumerate(self.widths)]
        self.first = TwoEntryQueue(self.widths, f"{prefix}_q0")
        self.second = TwoEntryQueue(self.widths, f"{prefix}_q1")

    # Elaborate the ordered two-stage flow path. / 展开有序双级流通路径。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        m.submodules.q0 = self.first
        m.submodules.q1 = self.second
        m.d.comb += [self.first.enq_valid.eq(self.in_valid),
                     self.in_ready.eq(self.first.enq_ready),
                     self.second.deq_ready.eq(self.out_ready),
                     self.out_valid.eq(self.second.deq_valid),
                     self.first.deq_ready.eq(self.second.enq_ready),
                     self.second.enq_valid.eq(self.first.deq_valid)]
        for queue_signal, edge_signal in zip(self.first.enq_bits, self.in_bits):
            m.d.comb += queue_signal.eq(edge_signal)
        for queue_signal, edge_signal in zip(self.second.deq_bits, self.out_bits):
            m.d.comb += edge_signal.eq(queue_signal)
        for first_signal, second_signal in zip(self.first.deq_bits, self.second.enq_bits):
            m.d.comb += second_signal.eq(first_signal)
        return m


class ICacheBuffer(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Buffered L1-I to L2 TileLink edge. / 带缓冲的 L1-I 至 L2 TileLink 边。"""

    # Construct the exact reduced ICache edge payload. / 构造精确的 ICache 边界载荷。
    def __init__(self, config: FrontendBridgeConfig | None = None) -> None:
        self.config = config or FrontendBridgeConfig()
        c = self.config
        self.in_a_valid = Signal(name="icache_in_a_valid")
        self.in_a_ready = Signal(name="icache_in_a_ready")
        self.in_a_source = Signal(c.source_bits, name="icache_in_a_source")
        self.in_a_address = Signal(c.address_bits, name="icache_in_a_address")
        self.out_a_valid = Signal(name="icache_out_a_valid")
        self.out_a_ready = Signal(name="icache_out_a_ready")
        self.out_a_opcode = Signal(4, name="icache_out_a_opcode")
        self.out_a_param = Signal(3, name="icache_out_a_param")
        self.out_a_size = Signal(3, name="icache_out_a_size")
        self.out_a_source = Signal(c.source_bits, name="icache_out_a_source")
        self.out_a_address = Signal(c.address_bits, name="icache_out_a_address")
        self.out_a_alias = Signal(2, name="icache_out_a_alias")
        self.out_a_req_source = Signal(5, name="icache_out_a_req_source")
        self.out_a_need_hint = Signal(name="icache_out_a_need_hint")
        self.out_a_mask = Signal(32, name="icache_out_a_mask")
        self.out_a_data = Signal(c.instruction_data_bits, name="icache_out_a_data")
        self.out_a_corrupt = Signal(name="icache_out_a_corrupt")
        self.in_d_valid = Signal(name="icache_in_d_valid")
        self.in_d_opcode = Signal(4, name="icache_in_d_opcode")
        self.in_d_size = Signal(3, name="icache_in_d_size")
        self.in_d_source = Signal(c.source_bits, name="icache_in_d_source")
        self.in_d_data = Signal(c.instruction_data_bits, name="icache_in_d_data")
        self.in_d_corrupt = Signal(name="icache_in_d_corrupt")
        self.out_d_valid = Signal(name="icache_out_d_valid")
        self.out_d_ready = Signal(name="icache_out_d_ready")
        self.out_d_opcode = Signal(4, name="icache_out_d_opcode")
        self.out_d_param = Signal(2, name="icache_out_d_param")
        self.out_d_size = Signal(3, name="icache_out_d_size")
        self.out_d_source = Signal(c.source_bits, name="icache_out_d_source")
        self.out_d_sink = Signal(10, name="icache_out_d_sink")
        self.out_d_denied = Signal(name="icache_out_d_denied")
        self.out_d_data = Signal(c.instruction_data_bits, name="icache_out_d_data")
        self.out_d_corrupt = Signal(name="icache_out_d_corrupt")
        self.a_edge = BufferedEdge((4, 3, 3, 4, 48, 2, 5, 1, 32, 256, 1), "icache_a")
        self.d_edge = BufferedEdge((4, 2, 3, 4, 10, 1, 256, 1), "icache_d")

    # Elaborate I-cache A/D queues and source-defined constants. / 展开 I-cache A/D 队列及源级常量。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        m.submodules.a_edge = self.a_edge
        m.submodules.d_edge = self.d_edge
        m.d.comb += [self.a_edge.in_valid.eq(self.in_a_valid),
                     self.in_a_ready.eq(self.a_edge.in_ready),
                     self.a_edge.out_ready.eq(self.out_a_ready),
                     self.out_a_valid.eq(self.a_edge.out_valid),
                     self.a_edge.in_bits[0].eq(4), self.a_edge.in_bits[1].eq(0),
                     self.a_edge.in_bits[2].eq(6), self.a_edge.in_bits[3].eq(self.in_a_source),
                     self.a_edge.in_bits[4].eq(self.in_a_address), self.a_edge.in_bits[5].eq(0),
                     # ``ICacheBuffer`` tags requests with reqSource=1 in the
                     # V2 MemBlock bridge (the reference emits 5'h1).
                     self.a_edge.in_bits[6].eq(1), self.a_edge.in_bits[7].eq(0),
                     self.a_edge.in_bits[8].eq((1 << 32) - 1), self.a_edge.in_bits[9].eq(0),
                     self.a_edge.in_bits[10].eq(0),
                     self.out_a_opcode.eq(self.a_edge.out_bits[0]), self.out_a_param.eq(self.a_edge.out_bits[1]),
                     self.out_a_size.eq(self.a_edge.out_bits[2]), self.out_a_source.eq(self.a_edge.out_bits[3]),
                     self.out_a_address.eq(self.a_edge.out_bits[4]), self.out_a_alias.eq(self.a_edge.out_bits[5]),
                     self.out_a_req_source.eq(self.a_edge.out_bits[6]), self.out_a_need_hint.eq(self.a_edge.out_bits[7]),
                     self.out_a_mask.eq(self.a_edge.out_bits[8]), self.out_a_data.eq(self.a_edge.out_bits[9]),
                     self.out_a_corrupt.eq(self.a_edge.out_bits[10]),
                     self.d_edge.in_valid.eq(self.out_d_valid), self.out_d_ready.eq(self.d_edge.in_ready),
                     self.d_edge.out_ready.eq(1), self.in_d_valid.eq(self.d_edge.out_valid),
                     self.d_edge.in_bits[0].eq(self.out_d_opcode), self.d_edge.in_bits[1].eq(self.out_d_param),
                     self.d_edge.in_bits[2].eq(self.out_d_size), self.d_edge.in_bits[3].eq(self.out_d_source),
                     self.d_edge.in_bits[4].eq(self.out_d_sink), self.d_edge.in_bits[5].eq(self.out_d_denied),
                     self.d_edge.in_bits[6].eq(self.out_d_data), self.d_edge.in_bits[7].eq(self.out_d_corrupt),
                     self.in_d_opcode.eq(self.d_edge.out_bits[0]), self.in_d_size.eq(self.d_edge.out_bits[2]),
                     self.in_d_source.eq(self.d_edge.out_bits[3]), self.in_d_data.eq(self.d_edge.out_bits[6]),
                     self.in_d_corrupt.eq(self.d_edge.out_bits[7])]
        return m


class ICacheCtrlBuffer(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Buffered I-cache control TileLink edge. / 带缓冲的 I-cache 控制 TileLink 边。"""

    # Construct control-edge fields with the V2 width adaptations. / 按 V2 位宽适配构造控制边界字段。
    def __init__(self) -> None:
        self.in_a_valid = Signal(name="icachectrl_in_a_valid")
        self.in_a_ready = Signal(name="icachectrl_in_a_ready")
        self.in_a_opcode = Signal(4, name="icachectrl_in_a_opcode")
        self.in_a_param = Signal(3, name="icachectrl_in_a_param")
        self.in_a_size = Signal(2, name="icachectrl_in_a_size")
        self.in_a_source = Signal(5, name="icachectrl_in_a_source")
        self.in_a_address = Signal(30, name="icachectrl_in_a_address")
        self.in_a_mask = Signal(8, name="icachectrl_in_a_mask")
        self.in_a_data = Signal(64, name="icachectrl_in_a_data")
        self.in_a_corrupt = Signal(name="icachectrl_in_a_corrupt")
        self.out_a_valid = Signal(name="icachectrl_out_a_valid")
        self.out_a_ready = Signal(name="icachectrl_out_a_ready")
        self.out_a_opcode = Signal(4, name="icachectrl_out_a_opcode")
        self.out_a_size = Signal(2, name="icachectrl_out_a_size")
        self.out_a_source = Signal(5, name="icachectrl_out_a_source")
        self.out_a_address = Signal(30, name="icachectrl_out_a_address")
        self.out_a_mask = Signal(8, name="icachectrl_out_a_mask")
        self.out_a_data = Signal(64, name="icachectrl_out_a_data")
        self.out_d_valid = Signal(name="icachectrl_out_d_valid")
        self.out_d_ready = Signal(name="icachectrl_out_d_ready")
        self.out_d_opcode = Signal(4, name="icachectrl_out_d_opcode")
        self.out_d_size = Signal(2, name="icachectrl_out_d_size")
        self.out_d_source = Signal(5, name="icachectrl_out_d_source")
        self.out_d_data = Signal(64, name="icachectrl_out_d_data")
        self.in_d_ready = Signal(name="icachectrl_in_d_ready")
        self.in_d_valid = Signal(name="icachectrl_in_d_valid")
        self.in_d_opcode = Signal(4, name="icachectrl_in_d_opcode")
        self.in_d_param = Signal(2, name="icachectrl_in_d_param")
        self.in_d_size = Signal(2, name="icachectrl_in_d_size")
        self.in_d_source = Signal(5, name="icachectrl_in_d_source")
        self.in_d_sink = Signal(name="icachectrl_in_d_sink")
        self.in_d_denied = Signal(name="icachectrl_in_d_denied")
        self.in_d_data = Signal(64, name="icachectrl_in_d_data")
        self.in_d_corrupt = Signal(name="icachectrl_in_d_corrupt")
        self.a_edge = BufferedEdge((4, 2, 5, 30, 8, 64, 1), "icachectrl_a")
        self.d_edge = BufferedEdge((4, 2, 5, 64), "icachectrl_d")

    # Elaborate control A/D buffering while dropping optimized-away fields. / 展开控制 A/D 缓冲并丢弃综合优化字段。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        m.submodules.a_edge = self.a_edge
        m.submodules.d_edge = self.d_edge
        m.d.comb += [self.a_edge.in_valid.eq(self.in_a_valid), self.in_a_ready.eq(self.a_edge.in_ready),
                     self.a_edge.out_ready.eq(self.out_a_ready), self.out_a_valid.eq(self.a_edge.out_valid),
                     self.a_edge.in_bits[0].eq(self.in_a_opcode), self.a_edge.in_bits[1].eq(self.in_a_size),
                     self.a_edge.in_bits[2].eq(self.in_a_source), self.a_edge.in_bits[3].eq(self.in_a_address),
                     self.a_edge.in_bits[4].eq(self.in_a_mask), self.a_edge.in_bits[5].eq(self.in_a_data),
                     self.a_edge.in_bits[6].eq(self.in_a_corrupt), self.out_a_opcode.eq(self.a_edge.out_bits[0]),
                     self.out_a_size.eq(self.a_edge.out_bits[1]), self.out_a_source.eq(self.a_edge.out_bits[2]),
                     self.out_a_address.eq(self.a_edge.out_bits[3]), self.out_a_mask.eq(self.a_edge.out_bits[4]),
                     self.out_a_data.eq(self.a_edge.out_bits[5]),
                     self.d_edge.in_valid.eq(self.out_d_valid), self.out_d_ready.eq(self.d_edge.in_ready),
                     self.d_edge.out_ready.eq(self.in_d_ready), self.in_d_valid.eq(self.d_edge.out_valid),
                     self.d_edge.in_bits[0].eq(self.out_d_opcode), self.d_edge.in_bits[1].eq(self.out_d_size),
                     self.d_edge.in_bits[2].eq(self.out_d_source), self.d_edge.in_bits[3].eq(self.out_d_data),
                     self.in_d_opcode.eq(self.d_edge.out_bits[0]), self.in_d_param.eq(0),
                     self.in_d_size.eq(self.d_edge.out_bits[1]), self.in_d_source.eq(self.d_edge.out_bits[2]),
                     self.in_d_sink.eq(0), self.in_d_denied.eq(0), self.in_d_data.eq(self.d_edge.out_bits[3]),
                     self.in_d_corrupt.eq(0)]
        return m


class InstrUncacheBuffer(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Buffered instruction-MMIO TileLink edge. / 带缓冲的指令 MMIO TileLink 边。"""

    # Construct the optimized instruction-uncache fields. / 构造优化后的指令非缓存字段。
    def __init__(self) -> None:
        self.in_a_valid = Signal(name="instr_uncache_in_a_valid")
        self.in_a_ready = Signal(name="instr_uncache_in_a_ready")
        self.in_a_address = Signal(48, name="instr_uncache_in_a_address")
        self.out_a_valid = Signal(name="instr_uncache_out_a_valid")
        self.out_a_ready = Signal(name="instr_uncache_out_a_ready")
        self.out_a_param = Signal(3, name="instr_uncache_out_a_param")
        self.out_a_address = Signal(48, name="instr_uncache_out_a_address")
        self.out_a_corrupt = Signal(name="instr_uncache_out_a_corrupt")
        self.out_d_valid = Signal(name="instr_uncache_out_d_valid")
        self.out_d_ready = Signal(name="instr_uncache_out_d_ready")
        self.out_d_opcode = Signal(4, name="instr_uncache_out_d_opcode")
        self.out_d_param = Signal(2, name="instr_uncache_out_d_param")
        self.out_d_size = Signal(3, name="instr_uncache_out_d_size")
        self.out_d_source = Signal(name="instr_uncache_out_d_source")
        self.out_d_sink = Signal(name="instr_uncache_out_d_sink")
        self.out_d_denied = Signal(name="instr_uncache_out_d_denied")
        self.out_d_data = Signal(64, name="instr_uncache_out_d_data")
        self.out_d_corrupt = Signal(name="instr_uncache_out_d_corrupt")
        self.in_d_valid = Signal(name="instr_uncache_in_d_valid")
        self.in_d_source = Signal(name="instr_uncache_in_d_source")
        self.in_d_data = Signal(64, name="instr_uncache_in_d_data")
        self.in_d_corrupt = Signal(name="instr_uncache_in_d_corrupt")
        self.a_edge = BufferedEdge((3, 48, 1), "instr_uncache_a")
        self.d_edge = BufferedEdge((4, 2, 3, 1, 1, 1, 64, 1), "instr_uncache_d")

    # Elaborate instruction-MMIO buffering and source-level Get constants. / 展开指令 MMIO 缓冲及源级 Get 常量。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        m.submodules.a_edge = self.a_edge
        m.submodules.d_edge = self.d_edge
        m.d.comb += [self.a_edge.in_valid.eq(self.in_a_valid), self.in_a_ready.eq(self.a_edge.in_ready),
                     self.a_edge.out_ready.eq(self.out_a_ready), self.out_a_valid.eq(self.a_edge.out_valid),
                     self.a_edge.in_bits[0].eq(0), self.a_edge.in_bits[1].eq(self.in_a_address),
                     self.a_edge.in_bits[2].eq(0), self.out_a_param.eq(self.a_edge.out_bits[0]),
                     self.out_a_address.eq(self.a_edge.out_bits[1]), self.out_a_corrupt.eq(self.a_edge.out_bits[2]),
                     self.d_edge.in_valid.eq(self.out_d_valid), self.out_d_ready.eq(self.d_edge.in_ready),
                     self.d_edge.out_ready.eq(1), self.in_d_valid.eq(self.d_edge.out_valid),
                     self.d_edge.in_bits[0].eq(self.out_d_opcode), self.d_edge.in_bits[1].eq(self.out_d_param),
                     self.d_edge.in_bits[2].eq(self.out_d_size), self.d_edge.in_bits[3].eq(self.out_d_source),
                     self.d_edge.in_bits[4].eq(self.out_d_sink), self.d_edge.in_bits[5].eq(self.out_d_denied),
                     self.d_edge.in_bits[6].eq(self.out_d_data), self.d_edge.in_bits[7].eq(self.out_d_corrupt),
                     self.in_d_source.eq(self.d_edge.out_bits[3]), self.in_d_data.eq(self.d_edge.out_bits[6]),
                     self.in_d_corrupt.eq(self.d_edge.out_bits[7])]
        return m


class FrontendBridge(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """The three-edge V2 frontend bridge. / 三条边组成的 V2 前端桥。"""

    # Construct all 91 source-generated boundary signals. / 构造源生成的全部 91 个边界信号。
    def __init__(self, configuration: FrontendBridgeConfig | None = None,
                 injected_dependencies: dict[str, Any] | None = None) -> None:
        del injected_dependencies
        self.config = configuration or FrontendBridgeConfig()
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.declare_ports()
        self.icache = ICacheBuffer(self.config)
        self.icachectrl = ICacheCtrlBuffer()
        self.instr_uncache = InstrUncacheBuffer()

    # Declare ports in the exact locked XSTop order. / 按锁定 XSTop 顺序声明端口。
    def declare_ports(self) -> None:
        specs = (
            ("auto_instr_uncache_in_a_ready", 1), ("auto_instr_uncache_in_a_valid", 1),
            ("auto_instr_uncache_in_a_bits_address", 48), ("auto_instr_uncache_in_d_valid", 1),
            ("auto_instr_uncache_in_d_bits_source", 1), ("auto_instr_uncache_in_d_bits_data", 64),
            ("auto_instr_uncache_in_d_bits_corrupt", 1), ("auto_instr_uncache_out_a_ready", 1),
            ("auto_instr_uncache_out_a_valid", 1), ("auto_instr_uncache_out_a_bits_param", 3),
            ("auto_instr_uncache_out_a_bits_address", 48), ("auto_instr_uncache_out_a_bits_corrupt", 1),
            ("auto_instr_uncache_out_d_ready", 1), ("auto_instr_uncache_out_d_valid", 1),
            ("auto_instr_uncache_out_d_bits_opcode", 4), ("auto_instr_uncache_out_d_bits_param", 2),
            ("auto_instr_uncache_out_d_bits_size", 3), ("auto_instr_uncache_out_d_bits_source", 1),
            ("auto_instr_uncache_out_d_bits_sink", 1), ("auto_instr_uncache_out_d_bits_denied", 1),
            ("auto_instr_uncache_out_d_bits_data", 64), ("auto_instr_uncache_out_d_bits_corrupt", 1),
            ("auto_icachectrl_in_a_ready", 1), ("auto_icachectrl_in_a_valid", 1),
            ("auto_icachectrl_in_a_bits_opcode", 4), ("auto_icachectrl_in_a_bits_param", 3),
            ("auto_icachectrl_in_a_bits_size", 2), ("auto_icachectrl_in_a_bits_source", 5),
            ("auto_icachectrl_in_a_bits_address", 30), ("auto_icachectrl_in_a_bits_mask", 8),
            ("auto_icachectrl_in_a_bits_data", 64), ("auto_icachectrl_in_a_bits_corrupt", 1),
            ("auto_icachectrl_in_d_ready", 1), ("auto_icachectrl_in_d_valid", 1),
            ("auto_icachectrl_in_d_bits_opcode", 4), ("auto_icachectrl_in_d_bits_param", 2),
            ("auto_icachectrl_in_d_bits_size", 2), ("auto_icachectrl_in_d_bits_source", 5),
            ("auto_icachectrl_in_d_bits_sink", 1), ("auto_icachectrl_in_d_bits_denied", 1),
            ("auto_icachectrl_in_d_bits_data", 64), ("auto_icachectrl_in_d_bits_corrupt", 1),
            ("auto_icachectrl_out_a_ready", 1), ("auto_icachectrl_out_a_valid", 1),
            ("auto_icachectrl_out_a_bits_opcode", 4), ("auto_icachectrl_out_a_bits_size", 2),
            ("auto_icachectrl_out_a_bits_source", 5), ("auto_icachectrl_out_a_bits_address", 30),
            ("auto_icachectrl_out_a_bits_mask", 8), ("auto_icachectrl_out_a_bits_data", 64),
            ("auto_icachectrl_out_d_ready", 1), ("auto_icachectrl_out_d_valid", 1),
            ("auto_icachectrl_out_d_bits_opcode", 4), ("auto_icachectrl_out_d_bits_size", 2),
            ("auto_icachectrl_out_d_bits_source", 5), ("auto_icachectrl_out_d_bits_data", 64),
            ("auto_icache_in_a_ready", 1), ("auto_icache_in_a_valid", 1),
            ("auto_icache_in_a_bits_source", 4), ("auto_icache_in_a_bits_address", 48),
            ("auto_icache_in_d_valid", 1), ("auto_icache_in_d_bits_opcode", 4),
            ("auto_icache_in_d_bits_size", 3), ("auto_icache_in_d_bits_source", 4),
            ("auto_icache_in_d_bits_data", 256), ("auto_icache_in_d_bits_corrupt", 1),
            ("auto_icache_out_a_ready", 1), ("auto_icache_out_a_valid", 1),
            ("auto_icache_out_a_bits_opcode", 4), ("auto_icache_out_a_bits_param", 3),
            ("auto_icache_out_a_bits_size", 3), ("auto_icache_out_a_bits_source", 4),
            ("auto_icache_out_a_bits_address", 48), ("auto_icache_out_a_bits_user_alias", 2),
            ("auto_icache_out_a_bits_user_reqSource", 5), ("auto_icache_out_a_bits_user_needHint", 1),
            ("auto_icache_out_a_bits_mask", 32), ("auto_icache_out_a_bits_data", 256),
            ("auto_icache_out_a_bits_corrupt", 1), ("auto_icache_out_d_ready", 1),
            ("auto_icache_out_d_valid", 1), ("auto_icache_out_d_bits_opcode", 4),
            ("auto_icache_out_d_bits_param", 2), ("auto_icache_out_d_bits_size", 3),
            ("auto_icache_out_d_bits_source", 4), ("auto_icache_out_d_bits_sink", 10),
            ("auto_icache_out_d_bits_denied", 1), ("auto_icache_out_d_bits_data", 256),
            ("auto_icache_out_d_bits_corrupt", 1),
        )
        for name, width in specs:
            setattr(self, name, Signal(width, name=name) if width > 1 else Signal(name=name))

    # Elaborate the three independent buffered paths on one resettable clock. / 在同一可复位时钟上展开三条独立缓冲路径。
    def elaborate(self, platform: Any) -> Module:
        del platform
        m = Module()
        domain = ClockDomain("sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.sync = domain
        m.submodules.icache = self.icache
        m.submodules.icachectrl = self.icachectrl
        m.submodules.instr_uncache = self.instr_uncache
        # Instruction uncache path. / 指令非缓存路径。
        m.d.comb += [self.instr_uncache.in_a_valid.eq(self.auto_instr_uncache_in_a_valid),
                     self.auto_instr_uncache_in_a_ready.eq(self.instr_uncache.in_a_ready),
                     self.instr_uncache.in_a_address.eq(self.auto_instr_uncache_in_a_bits_address),
                     self.instr_uncache.out_a_ready.eq(self.auto_instr_uncache_out_a_ready),
                     self.auto_instr_uncache_out_a_valid.eq(self.instr_uncache.out_a_valid),
                     self.auto_instr_uncache_out_a_bits_param.eq(self.instr_uncache.out_a_param),
                     self.auto_instr_uncache_out_a_bits_address.eq(self.instr_uncache.out_a_address),
                     self.auto_instr_uncache_out_a_bits_corrupt.eq(self.instr_uncache.out_a_corrupt),
                     self.instr_uncache.out_d_valid.eq(self.auto_instr_uncache_out_d_valid),
                     self.auto_instr_uncache_out_d_ready.eq(self.instr_uncache.out_d_ready),
                     self.instr_uncache.out_d_opcode.eq(self.auto_instr_uncache_out_d_bits_opcode),
                     self.instr_uncache.out_d_param.eq(self.auto_instr_uncache_out_d_bits_param),
                     self.instr_uncache.out_d_size.eq(self.auto_instr_uncache_out_d_bits_size),
                     self.instr_uncache.out_d_source.eq(self.auto_instr_uncache_out_d_bits_source),
                     self.instr_uncache.out_d_sink.eq(self.auto_instr_uncache_out_d_bits_sink),
                     self.instr_uncache.out_d_denied.eq(self.auto_instr_uncache_out_d_bits_denied),
                     self.instr_uncache.out_d_data.eq(self.auto_instr_uncache_out_d_bits_data),
                     self.instr_uncache.out_d_corrupt.eq(self.auto_instr_uncache_out_d_bits_corrupt),
                     self.auto_instr_uncache_in_d_valid.eq(self.instr_uncache.in_d_valid),
                     self.auto_instr_uncache_in_d_bits_source.eq(self.instr_uncache.in_d_source),
                     self.auto_instr_uncache_in_d_bits_data.eq(self.instr_uncache.in_d_data),
                     self.auto_instr_uncache_in_d_bits_corrupt.eq(self.instr_uncache.in_d_corrupt)]
        # I-cache control path. / I-cache 控制路径。
        m.d.comb += [self.icachectrl.in_a_valid.eq(self.auto_icachectrl_in_a_valid),
                     self.auto_icachectrl_in_a_ready.eq(self.icachectrl.in_a_ready),
                     self.icachectrl.in_a_opcode.eq(self.auto_icachectrl_in_a_bits_opcode),
                     self.icachectrl.in_a_param.eq(self.auto_icachectrl_in_a_bits_param),
                     self.icachectrl.in_a_size.eq(self.auto_icachectrl_in_a_bits_size),
                     self.icachectrl.in_a_source.eq(self.auto_icachectrl_in_a_bits_source),
                     self.icachectrl.in_a_address.eq(self.auto_icachectrl_in_a_bits_address),
                     self.icachectrl.in_a_mask.eq(self.auto_icachectrl_in_a_bits_mask),
                     self.icachectrl.in_a_data.eq(self.auto_icachectrl_in_a_bits_data),
                     self.icachectrl.in_a_corrupt.eq(self.auto_icachectrl_in_a_bits_corrupt),
                     self.icachectrl.out_a_ready.eq(self.auto_icachectrl_out_a_ready),
                     self.auto_icachectrl_out_a_valid.eq(self.icachectrl.out_a_valid),
                     self.auto_icachectrl_out_a_bits_opcode.eq(self.icachectrl.out_a_opcode),
                     self.auto_icachectrl_out_a_bits_size.eq(self.icachectrl.out_a_size),
                     self.auto_icachectrl_out_a_bits_source.eq(self.icachectrl.out_a_source),
                     self.auto_icachectrl_out_a_bits_address.eq(self.icachectrl.out_a_address),
                     self.auto_icachectrl_out_a_bits_mask.eq(self.icachectrl.out_a_mask),
                     self.auto_icachectrl_out_a_bits_data.eq(self.icachectrl.out_a_data),
                     self.icachectrl.out_d_valid.eq(self.auto_icachectrl_out_d_valid),
                     self.auto_icachectrl_out_d_ready.eq(self.icachectrl.out_d_ready),
                     self.icachectrl.out_d_opcode.eq(self.auto_icachectrl_out_d_bits_opcode),
                     self.icachectrl.out_d_size.eq(self.auto_icachectrl_out_d_bits_size),
                     self.icachectrl.out_d_source.eq(self.auto_icachectrl_out_d_bits_source),
                     self.icachectrl.out_d_data.eq(self.auto_icachectrl_out_d_bits_data),
                     self.icachectrl.in_d_ready.eq(self.auto_icachectrl_in_d_ready),
                     self.auto_icachectrl_in_d_valid.eq(self.icachectrl.in_d_valid),
                     self.auto_icachectrl_in_d_bits_opcode.eq(self.icachectrl.in_d_opcode),
                     self.auto_icachectrl_in_d_bits_param.eq(self.icachectrl.in_d_param),
                     self.auto_icachectrl_in_d_bits_size.eq(self.icachectrl.in_d_size),
                     self.auto_icachectrl_in_d_bits_source.eq(self.icachectrl.in_d_source),
                     self.auto_icachectrl_in_d_bits_sink.eq(self.icachectrl.in_d_sink),
                     self.auto_icachectrl_in_d_bits_denied.eq(self.icachectrl.in_d_denied),
                     self.auto_icachectrl_in_d_bits_data.eq(self.icachectrl.in_d_data),
                     self.auto_icachectrl_in_d_bits_corrupt.eq(self.icachectrl.in_d_corrupt)]
        # L1 I-cache path. / L1 I-cache 路径。
        m.d.comb += [self.icache.in_a_valid.eq(self.auto_icache_in_a_valid),
                     self.auto_icache_in_a_ready.eq(self.icache.in_a_ready),
                     self.icache.in_a_source.eq(self.auto_icache_in_a_bits_source),
                     self.icache.in_a_address.eq(self.auto_icache_in_a_bits_address),
                     self.icache.out_a_ready.eq(self.auto_icache_out_a_ready),
                     self.auto_icache_out_a_valid.eq(self.icache.out_a_valid),
                     self.auto_icache_out_a_bits_opcode.eq(self.icache.out_a_opcode),
                     self.auto_icache_out_a_bits_param.eq(self.icache.out_a_param),
                     self.auto_icache_out_a_bits_size.eq(self.icache.out_a_size),
                     self.auto_icache_out_a_bits_source.eq(self.icache.out_a_source),
                     self.auto_icache_out_a_bits_address.eq(self.icache.out_a_address),
                     self.auto_icache_out_a_bits_user_alias.eq(self.icache.out_a_alias),
                     self.auto_icache_out_a_bits_user_reqSource.eq(self.icache.out_a_req_source),
                     self.auto_icache_out_a_bits_user_needHint.eq(self.icache.out_a_need_hint),
                     self.auto_icache_out_a_bits_mask.eq(self.icache.out_a_mask),
                     self.auto_icache_out_a_bits_data.eq(self.icache.out_a_data),
                     self.auto_icache_out_a_bits_corrupt.eq(self.icache.out_a_corrupt),
                     self.icache.out_d_valid.eq(self.auto_icache_out_d_valid),
                     self.auto_icache_out_d_ready.eq(self.icache.out_d_ready),
                     self.icache.out_d_opcode.eq(self.auto_icache_out_d_bits_opcode),
                     self.icache.out_d_param.eq(self.auto_icache_out_d_bits_param),
                     self.icache.out_d_size.eq(self.auto_icache_out_d_bits_size),
                     self.icache.out_d_source.eq(self.auto_icache_out_d_bits_source),
                     self.icache.out_d_sink.eq(self.auto_icache_out_d_bits_sink),
                     self.icache.out_d_denied.eq(self.auto_icache_out_d_bits_denied),
                     self.icache.out_d_data.eq(self.auto_icache_out_d_bits_data),
                     self.icache.out_d_corrupt.eq(self.auto_icache_out_d_bits_corrupt),
                     self.auto_icache_in_d_valid.eq(self.icache.in_d_valid),
                     self.auto_icache_in_d_bits_opcode.eq(self.icache.in_d_opcode),
                     self.auto_icache_in_d_bits_size.eq(self.icache.in_d_size),
                     self.auto_icache_in_d_bits_source.eq(self.icache.in_d_source),
                     self.auto_icache_in_d_bits_data.eq(self.icache.in_d_data),
                     self.auto_icache_in_d_bits_corrupt.eq(self.icache.in_d_corrupt)]
        return m


# Source-compatible aliases for closure manifests. / 为闭包清单保留源兼容别名。
ICacheBuffer = ICacheBuffer
ICacheCtrlBuffer = ICacheCtrlBuffer
InstrUncacheBuffer = InstrUncacheBuffer


# =============================================================================
# Public Adapter
# =============================================================================
# Emit the deterministic 91-port FrontendBridge artifact. / 输出确定性的 91 端口 FrontendBridge 产物。
def build_verilog(configuration: FrontendBridgeConfig | dict[str, Any] | None = None,
                  injected_dependencies: dict[str, Any] | None = None) -> str:
    if isinstance(configuration, FrontendBridgeConfig):
        config = configuration
    else:
        values = configuration if isinstance(configuration, dict) else {}
        config = FrontendBridgeConfig(
            address_bits=int(values.get("address_bits", 48)),
            instruction_data_bits=int(values.get("instruction_data_bits", 256)),
            control_data_bits=int(values.get("control_data_bits", 64)),
            source_bits=int(values.get("source_bits", 4)),
        )
    top = FrontendBridge(config, injected_dependencies)
    ports = [top.clock, top.reset] + [getattr(top, name) for name, _width in port_schema()]
    module_name = str(configuration.get("module", "FrontendBridge")) if isinstance(configuration, dict) else "FrontendBridge"
    return verilog.convert(top, name=module_name, ports=ports, emit_src=False)


# Return the frozen 91-port schema for validators and parent adapters. / 返回供验证器和父级适配器使用的冻结 91 端口模式。
def port_schema() -> tuple[tuple[str, int], ...]:
    probe = FrontendBridge()
    names = [name for name, value in probe.__dict__.items()
             if isinstance(value, Signal) and name not in {"clock", "reset"}]
    return tuple((name, len(getattr(probe, name))) for name in names)


# =============================================================================
# Direct Entry
# =============================================================================
# Print the default frontend bridge artifact. / 打印默认前端桥产物。
def main() -> None:
    print(build_verilog())


if __name__ == "__main__":
    main()
