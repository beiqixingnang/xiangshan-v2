"""V2 reorder-buffer enqueue and dequeue pointer wrappers.
V2 重排序缓冲区入队与出队指针封装。
"""

from __future__ import annotations

from dataclasses import dataclass

from amaranth import Array, Cat, Const, Elaboratable, Module, Mux, Signal


# =============================================================================
# Module Contract
# =============================================================================
# This family aggregates RobEnqPtrWrapper.scala and NewRobDeqPtrWrapper.scala.
# Pointer arithmetic is modulo the configured ROB size; redirect and commit
# gates preserve the V2 state-update boundaries.
# 本 family 聚合两个 Scala 源；指针按 ROB 大小模运算，重定向和提交门控保持
# V2 状态更新边界。
__all__ = [
    "RobPtrConfig",
    "RobEnqPtrWrapper",
    "NewRobDeqPtrWrapper",
    "enq_reference",
    "deq_reference",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class RobPtrConfig:
    """V2 ROB pointer geometry. / V2 ROB 指针几何配置。"""

    rob_size: int = 64
    rename_width: int = 4
    commit_width: int = 4

    # Validate power-of-two ROB size and positive widths. / 校验二次幂 ROB 大小和正宽度。
    def __post_init__(self) -> None:
        if self.rob_size < 2 or self.rob_size & (self.rob_size - 1):
            raise ValueError("V2 ROB size must be a power of two")
        if self.rename_width < 1 or self.commit_width < 1:
            raise ValueError("V2 ROB widths must be positive")

    @property
    # Return the circular pointer width. / 返回循环指针位宽。
    def ptr_width(self) -> int:
        """Return ``log2(rob_size)``. / 返回 ``log2(rob_size)``。"""

        return self.rob_size.bit_length() - 1


# =============================================================================
# Implementation
# =============================================================================
def enq_reference(state: list[int], allow_enqueue: bool, blocked: bool,
                  enq: list[bool], redirect_valid: bool = False,
                  redirect_idx: int = 0, flush_itself: bool = False,
                  configuration: RobPtrConfig = RobPtrConfig()) -> list[int]:
    """Return next enqueue pointers independently. / 独立返回下一入队指针。"""

    c = configuration
    mask = c.rob_size - 1
    current = [value & mask for value in state]
    if redirect_valid:
        base = redirect_idx + (0 if flush_itself else 1)
        return [(base + index) & mask for index in range(c.rename_width)]
    advance = sum(bool(item) for item in enq) if allow_enqueue and not blocked else 0
    return [(value + advance) & mask for value in current]


def deq_reference(state: list[int], deq_v: list[bool], deq_w: list[bool],
                  has_committed: list[bool], allow_only_one: bool,
                  block_commit: bool, configuration: RobPtrConfig = RobPtrConfig()) -> tuple[list[int], int, bool]:
    """Return next dequeue pointers, count, and commit enable. / 返回下一出队指针、数量及提交使能。"""

    c = configuration
    mask = c.rob_size - 1
    can_commit = [bool(v and w) or bool(h) for v, w, h in zip(deq_v, deq_w, has_committed)]
    if allow_only_one:
        count = 1 if can_commit[0] else 0
    else:
        count = 0
        for item in can_commit:
            if not item:
                break
            count += 1
    enabled = not block_commit
    advance = count if enabled else 0
    return [((value + advance) & mask) for value in state], count, enabled


class RobEnqPtrWrapper(Elaboratable):
    """Registered V2 ROB enqueue pointer vector. / V2 寄存式 ROB 入队指针向量。"""

    # Construct redirect, enqueue, and pointer ports. / 构造重定向、入队及指针端口。
    def __init__(self, configuration: RobPtrConfig = RobPtrConfig()) -> None:
        self.configuration = configuration
        c = configuration
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.redirect_valid = Signal(name="io_redirect_valid")
        self.redirect_idx = Signal(c.ptr_width, name="io_redirect_robIdx")
        self.flush_itself = Signal(name="io_redirect_flushItself")
        self.allow_enqueue = Signal(name="io_allowEnqueue")
        self.has_block_backward = Signal(name="io_hasBlockBackward")
        self.enq = [Signal(name=f"io_enq_{index}") for index in range(c.rename_width)]
        self.out = [Signal(c.ptr_width, name=f"io_out_{index}") for index in range(c.rename_width)]

    # Elaborate redirect and circular enqueue increments. / 展开重定向和循环入队增量。
    def elaborate(self, platform) -> Module:
        del platform
        m = Module()
        c = self.configuration
        m.d.comb += [self.out[index].eq(self._state[index]) for index in range(c.rename_width)]
        advance = Const(0, c.ptr_width + 1)
        for signal in self.enq:
            advance = advance + signal
        can_accept = self.allow_enqueue & ~self.has_block_backward
        for index, state in enumerate(self._state):
            redirected = self.redirect_idx + index + Mux(self.flush_itself, 0, 1)
            next_value = Mux(self.redirect_valid, redirected, state + Mux(can_accept, advance, 0))
            m.d.sync += state.eq(next_value[:c.ptr_width])
        return m

    @property
    # Lazily allocate state signals for deterministic reset values. / 延迟分配具有确定复位值的状态信号。
    def _state(self) -> list[Signal]:
        if not hasattr(self, "_states"):
            self._states = [Signal(self.configuration.ptr_width, reset=index, name=f"enqPtr_{index}") for index in range(self.configuration.rename_width)]
        return self._states


class NewRobDeqPtrWrapper(Elaboratable):
    """Registered V2 ROB commit/dequeue pointer vector. / V2 寄存式 ROB 提交出队指针向量。"""

    # Construct commit controls and pointer outputs. / 构造提交控制及指针输出。
    def __init__(self, configuration: RobPtrConfig = RobPtrConfig()) -> None:
        self.configuration = configuration
        c = configuration
        self.state = Signal(2, name="io_state")
        self.deq_v = [Signal(name=f"io_deq_v_{index}") for index in range(c.commit_width)]
        self.deq_w = [Signal(name=f"io_deq_w_{index}") for index in range(c.commit_width)]
        self.has_committed = [Signal(name=f"io_hasCommitted_{index}") for index in range(c.commit_width)]
        self.allow_only_one = Signal(name="io_allowOnlyOneCommit")
        self.block_commit = Signal(name="io_blockCommit")
        self.out = [Signal(c.ptr_width, name=f"io_out_{index}") for index in range(c.commit_width)]
        self.next_out = [Signal(c.ptr_width, name=f"io_next_out_{index}") for index in range(c.commit_width)]
        self.commit_count = Signal(max(1, (c.commit_width + 1).bit_length()), name="io_commitCnt")
        self.commit_enable = Signal(name="io_commitEn")

    # Elaborate contiguous commit count and pointer advancement. / 展开连续提交计数和指针推进。
    def elaborate(self, platform) -> Module:
        del platform
        m = Module()
        c = self.configuration
        can_commit = [v & w | h for v, w, h in zip(self.deq_v, self.deq_w, self.has_committed)]
        count = Const(0, max(1, (c.commit_width + 1).bit_length()))
        for item in can_commit:
            count = Mux((count == count) & item, count + 1, count)
        count = Mux(self.allow_only_one, can_commit[0], count)
        m.d.comb += [self.commit_count.eq(count), self.commit_enable.eq((self.state == 0) & ~self.block_commit)]
        for index, state in enumerate(self._state):
            m.d.comb += [self.out[index].eq(state), self.next_out[index].eq(state + Mux(self.commit_enable, count, 0))]
            m.d.sync += state.eq(self.next_out[index])
        return m

    @property
    # Lazily allocate commit pointer state signals. / 延迟分配提交指针状态信号。
    def _state(self) -> list[Signal]:
        if not hasattr(self, "_states"):
            self._states = [Signal(self.configuration.ptr_width, reset=index, name=f"deqPtr_{index}") for index in range(self.configuration.commit_width)]
        return self._states


class RobPtrWrappers(Elaboratable):
    """Combined emission top for both V2 pointer wrappers. / 两个 V2 指针封装的组合生成顶层。"""

    # Construct both child wrappers. / 构造两个子封装。
    def __init__(self, configuration: RobPtrConfig = RobPtrConfig()) -> None:
        self.enq = RobEnqPtrWrapper(configuration)
        self.deq = NewRobDeqPtrWrapper(configuration)

    # Elaborate both independently visible child boundaries. / 展开两个独立可见的子边界。
    def elaborate(self, platform) -> Module:
        m = Module()
        m.submodules.enq = self.enq
        m.submodules.deq = self.deq
        return m


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration=None, injected_dependencies=None) -> str:
    """Emit combined ROB pointer-wrapper Verilog. / 输出组合 ROB 指针封装 Verilog。"""

    del injected_dependencies
    from amaranth.back import verilog

    c = configuration or RobPtrConfig()
    top = RobPtrWrappers(c)
    ports = [top.enq.clock, top.enq.reset, top.enq.redirect_valid, top.enq.redirect_idx,
             top.enq.flush_itself, top.enq.allow_enqueue, top.enq.has_block_backward,
             *top.enq.enq, *top.enq.out, top.deq.state, *top.deq.deq_v, *top.deq.deq_w,
             *top.deq.has_committed, top.deq.allow_only_one, top.deq.block_commit,
             *top.deq.out, *top.deq.next_out, top.deq.commit_count, top.deq.commit_enable]
    return verilog.convert(top, name="RobPtrWrappers", ports=ports)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    """Print the generated pointer-wrapper RTL. / 打印生成的指针封装 RTL。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
