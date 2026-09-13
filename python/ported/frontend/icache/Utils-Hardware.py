"""XiangShan ICache utility modules rewritten in amaranth.
香山 ICache 工具模块（DeMultiplexer / MuxBundle / FIFOReg）的 amaranth 重写。
"""
from __future__ import annotations

from typing import Any, cast

from amaranth import Array, Elaboratable, Module, Mux, Signal


# Module Contract
# ---------------------------------------------------------------------------
# Public symbols:
#   - DeMultiplexer : 1-producer to n-consumer decoupled demux, priority to
#     lower index (used by MissUnit to dispatch fetch/prefetch reqs to MSHRs)
#   - MuxBundle     : n-input decoupled mux selected by `sel`
#   - FIFOReg       : circular FIFO of `entries` registers with optional flush
# Ports: each module exposes `in_*` / `out_*` decoupled signal groups created
# in __init__; connect by assigning .valid/.ready/.bits attributes.
__all__ = ["DeMultiplexer", "MuxBundle", "FIFOReg"]


# Configuration
# ---------------------------------------------------------------------------
# no dataclass config needed; widths passed via constructor / 位宽由构造参数传入


# Implementation
# ---------------------------------------------------------------------------
class DeMultiplexer(Elaboratable):
    """Decoupled 1->n demux with lower-index priority. / 低索引优先的 1->n 解复用器。"""

    # construct ports / 构造端口
    def __init__(self, bits_width: int, n: int) -> None:
        assert n >= 2
        self.n = n
        self.in_valid = Signal(name="in_valid")
        self.in_ready = Signal(name="in_ready")
        self.in_bits = Signal(bits_width, name="in_bits")
        self.out_valid = [Signal(name=f"out_valid_{i}") for i in range(n)]
        self.out_ready = [Signal(name=f"out_ready_{i}") for i in range(n)]
        self.out_bits = [Signal(bits_width, name=f"out_bits_{i}") for i in range(n)]
        self.chosen = Signal(max(1, (n - 1).bit_length()), name="chosen")

    # route input to first ready output / 将输入路由到首个就绪输出
    def elaborate(self, platform) -> Module:
        m = Module()
        grant = []
        for i in range(self.n):
            if i == 0:
                grant.append(0)
            else:
                g = self.out_ready[0]
                for j in range(1, i):
                    g = g | self.out_ready[j]
                grant.append(g)
        for i in range(self.n):
            m.d.comb += [
                self.out_bits[i].eq(self.in_bits),
                self.out_valid[i].eq(~grant[i] & self.in_valid),
            ]
        m.d.comb += self.in_ready.eq(grant[-1] | self.out_ready[-1])
        # chosen = low-index priority encoder of out_ready / chosen 为就绪向量的低位优先编码
        # Chisel PriorityEncoder selects the first asserted bit.  Its generated
        # n=10 reference uses the final legal index for an all-zero vector, so
        # preserve that deterministic fallback instead of inventing a new one.
        chosen_val = self.n - 1
        for i in range(self.n - 1, -1, -1):
            chosen_val = Mux(self.out_ready[i], i, chosen_val)
        m.d.comb += self.chosen.eq(chosen_val)
        return m


class MuxBundle(Elaboratable):
    """Decoupled n->1 mux selected by sel. / 由 sel 选择的 n->1 复用器。"""

    # construct ports / 构造端口
    def __init__(self, bits_width: int, n: int) -> None:
        assert n >= 2
        self.n = n
        self.sel = Signal(max(1, (n - 1).bit_length()), name="sel")
        self.in_valid = [Signal(name=f"in_valid_{i}") for i in range(n)]
        self.in_ready = [Signal(name=f"in_ready_{i}") for i in range(n)]
        self.in_bits = [Signal(bits_width, name=f"in_bits_{i}") for i in range(n)]
        self.out_valid = Signal(name="out_valid")
        self.out_ready = Signal(name="out_ready")
        self.out_bits = Signal(bits_width, name="out_bits")

    # select input by sel / 按 sel 选择输入
    def elaborate(self, platform) -> Module:
        m = Module()
        # Chisel's ``io.out <> DontCare`` leaves input zero as the generated
        # fallback for an out-of-range selector.  Seed both outputs from input
        # zero, then override only valid selector encodings.
        out_v = self.in_valid[0]
        out_b = self.in_bits[0]
        m.d.comb += self.in_ready[0].eq((self.sel == 0) & self.out_ready)
        for i in range(1, self.n):
            hit = self.sel == i
            out_v = Mux(hit, self.in_valid[i], out_v)
            out_b = Mux(hit, self.in_bits[i], out_b)
            m.d.comb += self.in_ready[i].eq(hit & self.out_ready)
        m.d.comb += [
            self.out_valid.eq(out_v),
            self.out_bits.eq(out_b),
        ]
        return m


class FIFOReg(Elaboratable):
    """Register-file FIFO with circular pointers. / 环形指针寄存器堆 FIFO。"""

    # construct ports / 构造端口
    def __init__(self, bits_width: int, entries: int, has_flush: bool = True) -> None:
        assert entries > 0
        self.bits_width = bits_width
        self.entries = entries
        self.enq_valid = Signal(name="enq_valid")
        self.enq_ready = Signal(name="enq_ready")
        self.enq_bits = Signal(bits_width, name="enq_bits")
        self.deq_valid = Signal(name="deq_valid")
        self.deq_ready = Signal(name="deq_ready")
        self.deq_bits = Signal(bits_width, name="deq_bits")
        self.flush = Signal(name="flush") if has_flush else None

    # circular FIFO logic / 环形 FIFO 逻辑
    def elaborate(self, platform) -> Module:
        m = Module()
        ptr_bits = max(1, (self.entries - 1).bit_length())
        regs = Array(Signal(self.bits_width, name=f"fifo_reg_{i}") for i in range(self.entries))
        enq_val = Signal(ptr_bits, name="enq_ptr_val")
        enq_flag = Signal(name="enq_ptr_flag")
        deq_val = Signal(ptr_bits, name="deq_ptr_val")
        deq_flag = Signal(name="deq_ptr_flag")
        empty = (enq_val == deq_val) & (enq_flag == deq_flag)
        full = (enq_val == deq_val) & (enq_flag != deq_flag)

        enq_fire = self.enq_valid & self.enq_ready
        deq_fire = self.deq_valid & self.deq_ready

        # The Scala source writes the register file independently of flush;
        # flush has priority only over pointer updates.
        with cast(Any, m.If(enq_fire)):
            m.d.sync += regs[enq_val].eq(self.enq_bits)

        if self.flush is not None:
            with cast(Any, m.If(self.flush)):
                m.d.sync += [enq_val.eq(0), enq_flag.eq(0), deq_val.eq(0), deq_flag.eq(0)]
            with cast(Any, m.Else()):
                self.emit_pointer_updates(m, enq_val, enq_flag, deq_val, deq_flag,
                                          enq_fire, deq_fire)
        else:
            self.emit_pointer_updates(m, enq_val, enq_flag, deq_val, deq_flag,
                                      enq_fire, deq_fire)

        m.d.comb += [
            self.deq_bits.eq(regs[deq_val]),
            self.deq_valid.eq(~empty),
            self.enq_ready.eq(~full),
        ]
        return m

    def emit_pointer_updates(self, m, enq_val, enq_flag, deq_val, deq_flag,
                             enq_fire, deq_fire):
        """Emit pointer updates for one non-flush cycle."""
        with m.If(enq_fire):
            nv, nf = self.increment_pointer(enq_val, enq_flag)
            m.d.sync += [enq_val.eq(nv), enq_flag.eq(nf)]
        with m.If(deq_fire):
            nv, nf = self.increment_pointer(deq_val, deq_flag)
            m.d.sync += [deq_val.eq(nv), deq_flag.eq(nf)]

    def increment_pointer(self, value, flag):
        """Advance a circular pointer and toggle its wrap flag."""
        next_value = Mux(value == self.entries - 1, 0, value + 1)
        next_flag = Mux(value == self.entries - 1, ~flag, flag)
        return next_value, next_flag


# Public Adapter
# ---------------------------------------------------------------------------
# build verilog for the utility modules / 生成工具模块的 Verilog
def build_verilog(width: int = 8, n: int = 4, entries: int = 4) -> str:
    from amaranth.back import verilog

    top = FIFOReg(width, entries)
    ports = [top.enq_valid, top.enq_ready, top.enq_bits,
             top.deq_valid, top.deq_ready, top.deq_bits]
    if top.flush is not None:
        ports.append(top.flush)
    return verilog.convert(top, ports=ports)


# Direct Entry
# ---------------------------------------------------------------------------
# cli entry to emit verilog / 命令行入口：输出 Verilog
def main() -> None:
    print(build_verilog())


if __name__ == "__main__":
    main()
