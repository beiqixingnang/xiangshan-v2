"""V2 ICache decoupled utility modules in Amaranth.
香山 V2 指令缓存解耦工具模块的 Amaranth 重写。
"""
from __future__ import annotations

from typing import Any

from amaranth import Array, ClockDomain, Const, Elaboratable, Module, Mux, Signal


# Module Contract
# ---------------------------------------------------------------------------
# This family covers the exact V2 DeMultiplexer and MuxBundle declarations in
# ICacheMissUnit.scala plus FIFOReg in FIFO.scala.  Payloads are intentionally
# scalarized at this boundary; callers choose the packed width of their bundle.
__all__ = [
    "COVERED_MODULES", "DeMultiplexer", "MuxBundle", "FIFOReg",
    "fifo_observation", "build_verilog", "main",
]

COVERED_MODULES: tuple[str, ...] = (
    "DeMultiplexer", "DeMultiplexer_1", "MuxBundle", "FIFOReg",
)
SOURCE_PATHS: tuple[str, ...] = (
    "upstream/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala",
    "upstream/src/main/scala/xiangshan/frontend/icache/FIFO.scala",
)


# Configuration
# ---------------------------------------------------------------------------
# Width and entry parameters are explicit constructor values; no host probing
# or sibling-module imports are used.


def fifo_observation(occupancy: int, entries: int, enq_valid: bool,
                     deq_ready: bool, pipe: bool = False,
                     flush: bool = False) -> dict[str, int]:
    """Return FIFO ready/valid/fire and next occupancy for one cycle. / 返回 FIFO 单周期握手与占用量。"""

    if entries < 1 or not 0 <= occupancy <= entries:
        raise ValueError("invalid FIFO occupancy")
    deq_valid = occupancy > 0
    enq_ready = occupancy < entries or (pipe and deq_ready)
    enq_fire = bool(enq_valid and enq_ready and not flush)
    deq_fire = bool(deq_valid and deq_ready and not flush)
    next_occupancy = 0 if flush else occupancy + int(enq_fire) - int(deq_fire)
    return {"enq_ready": int(enq_ready), "deq_valid": int(deq_valid),
            "enq_fire": int(enq_fire), "deq_fire": int(deq_fire),
            "next_occupancy": next_occupancy}


# Implementation
# ---------------------------------------------------------------------------
class DeMultiplexer(Elaboratable):
    """Priority 1-to-n decoupled demultiplexer. / 低索引优先的一对多解复用器。"""

    # Construct the producer and consumer channels. / 构造生产者和消费者通道。
    def __init__(self, bits_width: int, n: int) -> None:
        if bits_width < 1 or n < 2:
            raise ValueError("bits_width must be positive and n must be >= 2")
        self.bits_width = int(bits_width)
        self.n = int(n)
        self.in_valid = Signal(name="io_in_valid")
        self.in_ready = Signal(name="io_in_ready")
        self.in_bits = Signal(bits_width, name="io_in_bits")
        self.out_valid = [Signal(name=f"io_out_{i}_valid") for i in range(n)]
        self.out_ready = [Signal(name=f"io_out_{i}_ready") for i in range(n)]
        self.out_bits = [Signal(bits_width, name=f"io_out_{i}_bits") for i in range(n)]
        self.chosen = Signal(max(1, (n - 1).bit_length()), name="io_chosen")

    # Elaborate ready-priority routing and chosen encoding. / 实例化 ready 优先路由及 chosen 编码。
    def elaborate(self, platform) -> Module:
        del platform
        # The branch API is decorator-generated in Amaranth; keep this local
        # adapter dynamic while preserving the exact runtime Module.
        m: Any = Module()
        prior_ready = 0
        for index in range(self.n):
            m.d.comb += [
                self.out_bits[index].eq(self.in_bits),
                self.out_valid[index].eq(self.in_valid & ~prior_ready),
            ]
            prior_ready = prior_ready | self.out_ready[index]
        m.d.comb += self.in_ready.eq(prior_ready)

        # Chisel PriorityEncoder's generated n=10 specialization has the last
        # legal index as the all-zero fallback; preserve that deterministic V2
        # behavior while selecting the lowest asserted ready bit.
        chosen_value = self.n - 1
        for index in range(self.n - 1, -1, -1):
            chosen_value = Mux(self.out_ready[index], index, chosen_value)
        m.d.comb += self.chosen.eq(chosen_value)
        return m


class MuxBundle(Elaboratable):
    """Selector-based n-to-1 decoupled mux. / 按选择信号工作的多对一解耦复用器。"""

    # Construct the selected input and output channels. / 构造输入及输出通道。
    def __init__(self, bits_width: int, n: int) -> None:
        if bits_width < 1 or n < 2:
            raise ValueError("bits_width must be positive and n must be >= 2")
        self.bits_width = int(bits_width)
        self.n = int(n)
        self.sel = Signal(max(1, (n - 1).bit_length()), name="io_sel")
        self.in_valid = [Signal(name=f"io_in_{i}_valid") for i in range(n)]
        self.in_ready = [Signal(name=f"io_in_{i}_ready") for i in range(n)]
        self.in_bits = [Signal(bits_width, name=f"io_in_{i}_bits") for i in range(n)]
        self.out_valid = Signal(name="io_out_valid")
        self.out_ready = Signal(name="io_out_ready")
        self.out_bits = Signal(bits_width, name="io_out_bits")

    # Elaborate selector routing and ready gating. / 实例化选择路由及 ready 门控。
    def elaborate(self, platform) -> Module:
        del platform
        # The branch API is decorator-generated in Amaranth; keep this local
        # adapter dynamic while preserving the exact runtime Module.
        m: Any = Module()
        out_valid = self.in_valid[0]
        out_bits = self.in_bits[0]
        m.d.comb += self.in_ready[0].eq((self.sel == 0) & self.out_ready)
        for index in range(1, self.n):
            selected = self.sel == index
            out_valid = Mux(selected, self.in_valid[index], out_valid)
            out_bits = Mux(selected, self.in_bits[index], out_bits)
            m.d.comb += self.in_ready[index].eq(selected & self.out_ready)
        m.d.comb += [self.out_valid.eq(out_valid), self.out_bits.eq(out_bits)]
        return m


class _LockedDeMultiplexer(Elaboratable):
    """Exact flattened ICacheMissReq specialization from the locked hierarchy."""

    def __init__(self, n: int, expose_chosen: bool) -> None:
        self.n = n
        self.in_ready = Signal(name="io_in_ready")
        self.in_valid = Signal(name="io_in_valid")
        self.in_blk_paddr = Signal(42, name="io_in_bits_blkPaddr")
        self.in_vset_idx = Signal(8, name="io_in_bits_vSetIdx")
        self.out_ready = [Signal(name=f"io_out_{i}_ready") for i in range(n)]
        self.out_valid = [Signal(name=f"io_out_{i}_valid") for i in range(n)]
        self.out_blk_paddr = [
            Signal(42, name=f"io_out_{i}_bits_blkPaddr") for i in range(n)
        ]
        self.out_vset_idx = [
            Signal(8, name=f"io_out_{i}_bits_vSetIdx") for i in range(n)
        ]
        self.chosen = Signal(4, name="io_chosen") if expose_chosen else None

    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        prior_ready: Any = Const(0)
        chosen: Any = Const(self.n - 1, 4)
        for index in range(self.n):
            module.d.comb += [
                self.out_valid[index].eq(self.in_valid & ~prior_ready),
                self.out_blk_paddr[index].eq(self.in_blk_paddr),
                self.out_vset_idx[index].eq(self.in_vset_idx),
            ]
            prior_ready = prior_ready | self.out_ready[index]
        for index in range(self.n - 1, -1, -1):
            chosen = Mux(self.out_ready[index], index, chosen)
        module.d.comb += self.in_ready.eq(prior_ready)
        if self.chosen is not None:
            module.d.comb += self.chosen.eq(chosen)
        return module

    def ports(self) -> list[Signal]:
        values = [self.in_ready, self.in_valid, self.in_blk_paddr, self.in_vset_idx]
        for index in range(self.n):
            values.extend((self.out_ready[index], self.out_valid[index],
                           self.out_blk_paddr[index], self.out_vset_idx[index]))
        if self.chosen is not None:
            values.append(self.chosen)
        return values


class _LockedMuxBundle(Elaboratable):
    """Exact ten-way MSHRAcquire mux emitted by locked Kunminghu V2."""

    def __init__(self) -> None:
        self.sel = Signal(4, name="io_sel")
        self.in_ready = [Signal(name=f"io_in_{i}_ready") for i in range(10)]
        self.in_valid = [Signal(name=f"io_in_{i}_valid") for i in range(10)]
        self.in_address = [
            Signal(48, name=f"io_in_{i}_bits_acquire_address") for i in range(10)
        ]
        self.in_vset_idx = [
            Signal(8, name=f"io_in_{i}_bits_vSetIdx") for i in range(10)
        ]
        self.out_ready = Signal(name="io_out_ready")
        self.out_valid = Signal(name="io_out_valid")
        self.out_source = Signal(4, name="io_out_bits_acquire_source")
        self.out_address = Signal(48, name="io_out_bits_acquire_address")
        self.out_vset_idx = Signal(8, name="io_out_bits_vSetIdx")

    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        valid: Any = self.in_valid[0]
        source: Any = Const(4, 4)
        address: Any = self.in_address[0]
        vset_idx: Any = self.in_vset_idx[0]
        for index in range(10):
            selected = self.sel == index
            module.d.comb += self.in_ready[index].eq(selected & self.out_ready)
            if index:
                valid = Mux(selected, self.in_valid[index], valid)
                source = Mux(selected, Const(index + 4, 4), source)
                address = Mux(selected, self.in_address[index], address)
                vset_idx = Mux(selected, self.in_vset_idx[index], vset_idx)
        module.d.comb += [
            self.out_valid.eq(valid),
            self.out_source.eq(source),
            self.out_address.eq(address),
            self.out_vset_idx.eq(vset_idx),
        ]
        return module

    def ports(self) -> list[Signal]:
        values = [self.sel]
        for index in range(10):
            values.extend((self.in_ready[index], self.in_valid[index],
                           self.in_address[index], self.in_vset_idx[index]))
        values.extend((self.out_ready, self.out_valid, self.out_source,
                       self.out_address, self.out_vset_idx))
        return values


class FIFOReg(Elaboratable):
    """Register-file circular FIFO with V2 flush semantics.
    带 V2 flush 语义的寄存器文件环形 FIFO。
    """

    # Construct FIFO channels and optional controls. / 构造 FIFO 通道及可选控制。
    def __init__(
        self,
        bits_width: int,
        entries: int,
        pipe: bool = False,
        has_flush: bool = False,
    ) -> None:
        if bits_width < 1 or entries < 1:
            raise ValueError("bits_width and entries must be positive")
        self.bits_width = int(bits_width)
        self.entries = int(entries)
        self.pipe = bool(pipe)
        self.has_flush = bool(has_flush)
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.enq_valid = Signal(name="io_enq_valid")
        self.enq_ready = Signal(name="io_enq_ready")
        self.enq_bits = Signal(bits_width, name="io_enq_bits")
        self.deq_valid = Signal(name="io_deq_valid")
        self.deq_ready = Signal(name="io_deq_ready")
        self.deq_bits = Signal(bits_width, name="io_deq_bits")
        self.flush = Signal(name="io_flush") if has_flush else None

    # Elaborate circular pointers, storage, and flush priority. / 实例化环形指针、存储及 flush 优先级逻辑。
    def elaborate(self, platform) -> Module:
        del platform
        # The branch API is decorator-generated in Amaranth; keep this local
        # adapter dynamic while preserving the exact runtime Module.
        m: Any = Module()
        domain = ClockDomain("sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains += domain
        ptr_bits = max(1, (self.entries - 1).bit_length())
        regs = Array(
            Signal(self.bits_width, name=f"regFiles_{index}")
            for index in range(self.entries)
        )
        enq_value = Signal(ptr_bits, name="enq_ptr_value")
        enq_flag = Signal(name="enq_ptr_flag")
        deq_value = Signal(ptr_bits, name="deq_ptr_value")
        deq_flag = Signal(name="deq_ptr_flag")

        empty = (enq_value == deq_value) & (enq_flag == deq_flag)
        full = (enq_value == deq_value) & (enq_flag != deq_flag)
        read_regs = Array([*regs, *([regs[0]] * ((1 << ptr_bits) - self.entries))])
        m.d.comb += [
            self.deq_bits.eq(read_regs[deq_value]),
            self.deq_valid.eq(~empty),
            self.enq_ready.eq(~full | (self.pipe & self.deq_ready)),
        ]
        enq_fire = self.enq_valid & self.enq_ready
        deq_fire = self.deq_valid & self.deq_ready

        # The V2 source writes a register independently; flush only wins over
        # pointer updates, so an enqueue during flush still updates storage.
        with m.If(enq_fire):
            m.d.sync += regs[enq_value].eq(self.enq_bits)

        flush = self.flush if self.flush is not None else 0
        with m.If(flush):
            m.d.sync += [
                enq_value.eq(0),
                enq_flag.eq(0),
                deq_value.eq(0),
                deq_flag.eq(0),
            ]
        with m.If(~flush):
            with m.If(enq_fire):
                extended = enq_value + 1
                wraps = extended >= self.entries
                next_value = Mux(wraps, extended - self.entries, extended)
                next_flag = enq_flag ^ wraps
                m.d.sync += [enq_value.eq(next_value), enq_flag.eq(next_flag)]
            with m.If(deq_fire):
                extended = deq_value + 1
                wraps = extended >= self.entries
                next_value = Mux(wraps, extended - self.entries, extended)
                next_flag = deq_flag ^ wraps
                m.d.sync += [deq_value.eq(next_value), deq_flag.eq(next_flag)]
        return m


# Public Adapter
# ---------------------------------------------------------------------------
# Export one selected utility deterministically. / 确定性导出所选工具模块。
def build_verilog(configuration, injected_dependencies):
    """Return Verilog for a configured utility. / 返回配置工具模块的 Verilog。"""
    from amaranth.back import verilog

    del injected_dependencies
    config = configuration if isinstance(configuration, dict) else {}
    module_name = str(config.get("module", "FIFOReg"))
    if module_name in {"DeMultiplexer", "DeMultiplexer_1"}:
        top = _LockedDeMultiplexer(4 if module_name == "DeMultiplexer" else 10,
                                   module_name == "DeMultiplexer_1")
        ports = top.ports()
    elif module_name == "MuxBundle":
        top = _LockedMuxBundle()
        ports = top.ports()
    else:
        top = FIFOReg(
            int(config.get("bits_width", 4)),
            int(config.get("entries", 10)),
            bool(config.get("pipe", False)),
            bool(config.get("has_flush", True)),
        )
        ports = [
            top.clock,
            top.reset,
            top.enq_valid,
            top.enq_ready,
            top.enq_bits,
            top.deq_valid,
            top.deq_ready,
            top.deq_bits,
        ]
        if top.flush is not None:
            ports.append(top.flush)
    return verilog.convert(top, ports=ports, name=module_name)


# Direct Entry
# ---------------------------------------------------------------------------
# Print the default FIFO export when invoked directly. / 直接调用时打印默认 FIFO 导出结果。
def main() -> None:
    """Print the default utility Verilog. / 打印默认工具 Verilog。"""
    print(build_verilog(None, None))


if __name__ == "__main__":
    main()
