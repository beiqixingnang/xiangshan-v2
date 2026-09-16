"""UHSC V2 utility dependency family boundary.
UHSC V2 utility 依赖 family 边界。

The selected Kunminghu V2 closure uses a small, stable subset of the vendored
utility tree (bit helpers, priority selection, circular pointers, parity/ECC
observation, and performance counting).  This single Build-Cpu file keeps
those hardware semantics together instead of creating one Python file per
Scala helper.  Non-hardware logging, test, macro, and unreachable utility
sources remain excluded by the frozen dependency inventory.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, cast

from amaranth import Array, Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# Source family: utility BitUtils/UIntUtils/PriorityMuxDefault/CircularQueuePtr,
# ECC, CriticalErrorUtils, and PerfCounterUtils.  The public boundary exposes
# deterministic combinational helpers plus a synchronous saturating counter.
# 来源 family：utility BitUtils/UIntUtils/PriorityMuxDefault/CircularQueuePtr、
# ECC、CriticalErrorUtils、PerfCounterUtils；公共边界提供确定性组合辅助逻辑及
# 同步饱和计数器。
__all__ = [
    "UtilityConfig",
    "UtilityBoundary",
    "priority_select",
    "circular_next",
    "circular_queue_state",
    "multi_flag_next",
    "mimo_queue_step",
    "utility_reference_step",
    "parity_encode",
    "secded_encode",
    "secded_check",
    "build_verilog",
    "main",
]


# Keep the selected hardware-bearing Scala provenance explicit. / 显式保留选定硬件逻辑的 Scala 来源路径。
UTILITY_SOURCE_PATHS: tuple[str, ...] = (
    "BitUtils.scala",
    "UIntUtils.scala",
    "PriorityMuxDefault.scala",
    "CircularQueuePtr.scala",
    "MultiFlagCircualQueuePtr.scala",
    "MIMOQueue.scala",
    "ECC.scala",
    "CriticalErrorUtils.scala",
    "PerfCounterUtils.scala",
    "FastArbiter.scala",
    "ParallelMux.scala",
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


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class UtilityConfig:
    """Fixed widths used by the selected V2 utility closure. / 选定 V2 utility 闭包使用的固定宽度。"""

    pointer_bits: int = 6
    data_bits: int = 64
    counter_bits: int = 32
    source_count: int = 8
    queue_entries: int = 8
    queue_enable: bool = False
    ecc_enable: bool = False

    # Validate finite hardware geometry. / 校验有限硬件几何参数。
    def __post_init__(self) -> None:
        if self.pointer_bits < 1 or self.data_bits < 1 or self.counter_bits < 1:
            raise ValueError("utility widths must be positive")
        if self.source_count < 1 or self.source_count > 32:
            raise ValueError("utility source_count must be in [1, 32]")
        if self.queue_entries < 2 or self.queue_entries > 256:
            raise ValueError("utility queue_entries must be in [2, 256]")
        if self.queue_entries & (self.queue_entries - 1):
            raise ValueError("utility queue_entries must be a power of two")


# =============================================================================
# Implementation
# =============================================================================
# Select the lowest-index valid value. / 选择最低索引的有效值。
def priority_select(valid: list[bool], values: list[int], width: int = 64) -> tuple[bool, int, int]:
    """Select the lowest-index valid value, matching PriorityMuxDefault. / 选择最低索引有效值，匹配 PriorityMuxDefault。"""

    if len(valid) != len(values):
        raise ValueError("valid/value lengths must match")
    mask = (1 << width) - 1
    for index, enabled in enumerate(valid):
        if enabled:
            return True, values[index] & mask, index
    return False, 0, 0


# Advance a modulo pointer and expose wrap. / 推进模指针并输出回绕。
def circular_next(value: int, increment: int, pointer_bits: int = 6) -> tuple[int, int]:
    """Advance a modulo pointer and return value plus wrap bit. / 推进模指针并返回值与回绕位。"""

    if pointer_bits < 1:
        raise ValueError("pointer_bits must be positive")
    limit = 1 << pointer_bits
    total = (value & (limit - 1)) + max(0, int(increment))
    return total & (limit - 1), int(total >= limit)


# Return CircularQueuePtr empty/full/distance/free state. / 返回 CircularQueuePtr 的空、满、距离及空闲状态。
def circular_queue_state(enq_flag: int, enq_value: int, deq_flag: int, deq_value: int,
                         entries: int) -> tuple[bool, bool, int, int]:
    """Model ``HasCircularQueuePtrHelper`` for arbitrary queue geometry. / 建模任意队列几何的指针辅助 trait。"""

    if entries < 2 or entries & (entries - 1):
        raise ValueError("entries must be a power of two and at least two")
    mask = entries - 1
    ef, df = int(bool(enq_flag)), int(bool(deq_flag))
    ev, dv = int(enq_value) & mask, int(deq_value) & mask
    empty = ef == df and ev == dv
    full = ef != df and ev == dv
    distance = (ev - dv) & mask
    if ef != df:
        distance += entries
    distance = min(distance, entries)
    return empty, full, distance, entries - distance


# Model MultiFlagCircularQueuePtr addition and wrap flags. / 建模 MultiFlagCircularQueuePtr 加法及回绕标志。
def multi_flag_next(first_flag: int, second_flag: int, value: int, increment: int,
                    entries: int, multiple: int) -> tuple[int, int, int, int]:
    """Return next ``(first_flag, second_flag, value, wraps)`` for a multi-flag pointer. / 返回多标志指针下一状态及回绕次数。"""

    if entries < 1 or multiple < 2:
        raise ValueError("entries must be positive and multiple must exceed one")
    total_entries = entries * multiple
    operation = (int(second_flag) % multiple) * entries + (int(value) % entries)
    absolute = operation + max(0, int(increment))
    wraps = absolute // total_entries
    next_operation = absolute % total_entries
    flag_index = (int(bool(first_flag)) * multiple + int(second_flag) % multiple + wraps) % (2 * multiple)
    return int(flag_index >= multiple), flag_index % multiple, next_operation % entries, wraps


# Model the simultaneous MIMOQueue enqueue/dequeue update. / 建模 MIMOQueue 同周期多入队/多出队更新。
def mimo_queue_step(queue: list[int], enqueues: list[int], dequeue_count: int,
                    entries: int) -> tuple[list[int], list[int], int]:
    """Return ``(next_queue, accepted, dequeued_count)`` with FIFO ordering. / 返回保持 FIFO 顺序的下一队列、接收项及出队数。"""

    if entries < 1:
        raise ValueError("queue entries must be positive")
    if dequeue_count < 0:
        raise ValueError("dequeue_count must be non-negative")
    current = list(queue[:entries])
    actual_deq = min(len(current), dequeue_count)
    current = current[actual_deq:]
    free = entries - len(current)
    accepted = list(enqueues[:free])
    current.extend(accepted)
    return current, accepted, actual_deq


# Combine utility observations into an independent cycle oracle. / 将 utility 观测组合为独立周期参考模型。
def utility_reference_step(valid: list[bool], values: list[int], pointer: int, increment: int,
                           parity_value: int, counter: int, enable: bool, clear: bool,
                           configuration: UtilityConfig) -> dict[str, int]:
    """Return one deterministic utility cycle result for differential checks. / 返回用于 differential 检查的确定性 utility 周期结果。"""

    selected_valid, selected_value, selected_index = priority_select(valid, values, configuration.data_bits)
    pointer_next, pointer_wrap = circular_next(pointer, increment, configuration.pointer_bits)
    next_counter = 0 if clear else min((1 << configuration.counter_bits) - 1, counter + int(enable))
    return {
        "selected_valid": int(selected_valid),
        "selected_value": selected_value,
        "selected_index": selected_index,
        "pointer_next": pointer_next,
        "pointer_wrap": pointer_wrap,
        "parity_bit": parity_encode(parity_value, configuration.data_bits),
        "counter_value": next_counter,
        "critical_error": int(enable and clear),
    }


# Compute even parity. / 计算偶校验。
def parity_encode(value: int, width: int = 64) -> int:
    """Return even parity over a fixed-width word. / 返回固定宽度字的偶校验位。"""

    if width < 1:
        raise ValueError("parity width must be positive")
    return (value & ((1 << width) - 1)).bit_count() & 1


# Encode a SECDED codeword in systematic software form. / 以系统化软件形式编码 SECDED 码字。
def secded_encode(value: int, width: int = 64) -> int:
    """Encode a word with SECDED Hamming parity bits.

    The returned code packs the data and seven Hamming parity bits followed
    by one overall parity bit.  This mirrors the ECC helper used by the V2
    utility closure while keeping the software oracle deterministic.
    """
    if width < 1:
        raise ValueError("ECC width must be positive")
    parity_count = 0
    while (1 << parity_count) < width + parity_count + 1:
        parity_count += 1
    code_bits = width + parity_count
    code = 0
    data_index = 0
    for position in range(1, code_bits + 1):
        if position & (position - 1):
            code |= ((value >> data_index) & 1) << (position - 1)
            data_index += 1
    for bit in range(parity_count):
        parity_position = 1 << bit
        parity = 0
        for position in range(1, code_bits + 1):
            if position & parity_position and position != parity_position:
                parity ^= (code >> (position - 1)) & 1
        code |= parity << (parity_position - 1)
    overall = code.bit_count() & 1
    return code | (overall << code_bits)


# Check and correct a SECDED codeword. / 检查并纠正 SECDED 码字。
def secded_check(code: int, width: int = 64) -> tuple[int, int, int]:
    """Return ``(corrected_data, corrected, uncorrectable)`` for SECDED code."""
    if width < 1:
        raise ValueError("ECC width must be positive")
    parity_count = 0
    while (1 << parity_count) < width + parity_count + 1:
        parity_count += 1
    code_bits = width + parity_count
    raw = code & ((1 << code_bits) - 1)
    syndrome = 0
    for bit in range(parity_count):
        parity_position = 1 << bit
        parity = 0
        for position in range(1, code_bits + 1):
            if position & parity_position:
                parity ^= (raw >> (position - 1)) & 1
        if parity:
            syndrome |= parity_position
    overall_error = ((code >> code_bits) ^ (code & ((1 << code_bits) - 1)).bit_count()) & 1
    corrected = 0
    uncorrectable = 0
    if overall_error and syndrome:
        raw ^= 1 << (syndrome - 1)
        corrected = 1
    elif not overall_error and syndrome:
        uncorrectable = 1
    data = 0
    data_index = 0
    for position in range(1, code_bits + 1):
        if position & (position - 1):
            data |= ((raw >> (position - 1)) & 1) << data_index
            data_index += 1
    return data, corrected, uncorrectable


class UtilityBoundary(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Aggregated hardware boundary for selected V2 utility helpers. / 选定 V2 utility 辅助逻辑的聚合硬件边界。"""

    # Construct the aggregated utility boundary. / 构造聚合 utility 边界。
    def __init__(self, configuration: UtilityConfig | None = None) -> None:
        self.configuration = configuration or UtilityConfig()
        c = self.configuration
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.valid = Signal(c.source_count, name="io_priority_valid")
        self.values = [Signal(c.data_bits, name=f"io_priority_value_{index}") for index in range(c.source_count)]
        self.selected_valid = Signal(name="io_priority_selected_valid")
        self.selected_value = Signal(c.data_bits, name="io_priority_selected_value")
        self.selected_index = Signal(max(1, (c.source_count - 1).bit_length()), name="io_priority_selected_index")
        self.pointer_value = Signal(c.pointer_bits, name="io_pointer_value")
        self.pointer_increment = Signal(c.pointer_bits + 1, name="io_pointer_increment")
        self.pointer_next = Signal(c.pointer_bits, name="io_pointer_next")
        self.pointer_wrap = Signal(name="io_pointer_wrap")
        self.parity_value = Signal(c.data_bits, name="io_parity_value")
        self.parity_bit = Signal(name="io_parity_bit")
        self.counter_enable = Signal(name="io_counter_enable")
        self.counter_clear = Signal(name="io_counter_clear")
        self.counter_value = Signal(c.counter_bits, name="io_counter_value")
        self.critical_error = Signal(name="io_critical_error")
        # Optional MIMOQueue surface; omitted from the default export to keep
        # the frozen V2 positional boundary stable. / 可选 MIMOQueue 接口；默认导出省略以保持 V2 固定位置边界稳定。
        queue_ptr_bits = max(1, (c.queue_entries - 1).bit_length())
        self.queue_push = Signal(name="io_queue_push")
        self.queue_pop = Signal(name="io_queue_pop")
        self.queue_push_value = Signal(c.data_bits, name="io_queue_push_value")
        self.queue_head_valid = Signal(name="io_queue_head_valid")
        self.queue_head_value = Signal(c.data_bits, name="io_queue_head_value")
        self.queue_level = Signal(max(1, (c.queue_entries + 1).bit_length()), name="io_queue_level")
        self.queue_full = Signal(name="io_queue_full")
        self.queue_empty = Signal(name="io_queue_empty")
        # Optional ECC decoder surface. / 可选 ECC 解码接口。
        parity_count = 0
        while (1 << parity_count) < c.data_bits + parity_count + 1:
            parity_count += 1
        self.ecc_width = c.data_bits + parity_count + 1
        self.ecc_code = Signal(self.ecc_width, name="io_ecc_code")
        self.ecc_data = Signal(c.data_bits, name="io_ecc_data")
        self.ecc_corrected = Signal(name="io_ecc_corrected")
        self.ecc_uncorrectable = Signal(name="io_ecc_uncorrectable")

    # Elaborate priority, pointer, parity, and saturating counter equations. / 展开优先级、指针、校验及饱和计数器方程。
    # Elaborate utility combinational and sequential logic. / 展开 utility 组合与时序逻辑。
    def elaborate(self, platform: Any) -> Module:
        del platform
        c = self.configuration
        m = Module()
        domain = ClockDomain("utility", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.utility = domain
        # Build expressions without feeding a signal back into itself. / 构造无信号自反馈的表达式。
        chosen_valid: Any = Const(0, 1)
        chosen_value: Any = Const(0, c.data_bits)
        chosen_index: Any = Const(0, len(self.selected_index))
        for index, value in enumerate(self.values):
            take = self.valid[index] & ~chosen_valid
            chosen_value = Mux(take, value, chosen_value)
            chosen_index = Mux(take, index, chosen_index)
            chosen_valid = chosen_valid | self.valid[index]
        m.d.comb += [self.selected_valid.eq(chosen_valid), self.selected_value.eq(chosen_value),
                     self.selected_index.eq(chosen_index)]
        m.d.comb += [self.pointer_next.eq(self.pointer_value + self.pointer_increment[:c.pointer_bits]),
                     self.pointer_wrap.eq((self.pointer_value + self.pointer_increment) >= (1 << c.pointer_bits)),
                     self.parity_bit.eq(self.parity_value.xor()),
                     self.critical_error.eq(self.counter_enable & self.counter_clear)]

        # Materialize the MIMOQueue ring only when requested by the selected
        # top.  It supports simultaneous enqueue/dequeue and exposes the same
        # occupancy invariants as MIMOQueue.scala. / 仅在选定顶层请求时实例化
        # MIMOQueue 环形存储，支持同周期入出队并暴露与 MIMOQueue.scala 一致的占用不变量。
        if c.queue_enable:
            queue_ptr_bits = max(1, (c.queue_entries - 1).bit_length())
            queue_mem = Array(Signal(c.data_bits, name=f"utility_queue_mem_{i}") for i in range(c.queue_entries))
            enq_ptr = Signal(queue_ptr_bits)
            deq_ptr = Signal(queue_ptr_bits)
            level = self.queue_level
            can_push = ~self.queue_full | self.queue_pop
            push_fire = self.queue_push & can_push
            pop_fire = self.queue_pop & self.queue_head_valid
            m.d.comb += [self.queue_empty.eq(level == 0),
                         self.queue_full.eq(level == c.queue_entries),
                         self.queue_head_valid.eq(level != 0),
                         self.queue_head_value.eq(queue_mem[deq_ptr])]
            with amaranth_if(m, self.reset):
                m.d.utility += [enq_ptr.eq(0), deq_ptr.eq(0), level.eq(0)]
            with amaranth_else(m):
                with amaranth_if(m, push_fire):
                    m.d.utility += [queue_mem[enq_ptr].eq(self.queue_push_value),
                                    enq_ptr.eq(enq_ptr + 1)]
                with amaranth_if(m, pop_fire):
                    m.d.utility += deq_ptr.eq(deq_ptr + 1)
                with amaranth_if(m, push_fire & ~pop_fire):
                    m.d.utility += level.eq(level + 1)
                with amaranth_elif(m, pop_fire & ~push_fire):
                    m.d.utility += level.eq(level - 1)
        else:
            # Keep optional outputs deterministic when the queue is not part
            # of the selected closure. / 未选队列闭包时保持可选输出确定。
            m.d.comb += [self.queue_head_valid.eq(0), self.queue_head_value.eq(0),
                         self.queue_level.eq(0), self.queue_full.eq(0), self.queue_empty.eq(1)]

        # Combinational SECDED decoder corresponding to ECC.scala. / 实现与
        # ECC.scala 对应的组合 SECDED 解码器。
        if c.ecc_enable:
            parity_count = self.ecc_width - c.data_bits - 1
            code_bits = c.data_bits + parity_count
            syndrome: Any = Const(0, max(1, parity_count))
            for bit in range(parity_count):
                parity_position = 1 << bit
                parity_term: Any = Const(0)
                for position in range(1, code_bits + 1):
                    if position & parity_position:
                        parity_term = parity_term ^ self.ecc_code[position - 1]
                syndrome = Mux(parity_term, syndrome | parity_position, syndrome)
            overall = self.ecc_code.xor()
            corrected_bits: list[Any] = [self.ecc_code[index] for index in range(code_bits)]
            for position in range(1, code_bits + 1):
                corrected_bits[position - 1] = Mux(cast(Any, overall) & (syndrome == position),
                                                    ~cast(Any, self.ecc_code[position - 1]), self.ecc_code[position - 1])
            data_expr: Any = Const(0, c.data_bits)
            data_index = 0
            for position in range(1, code_bits + 1):
                if position & (position - 1):
                    data_expr = data_expr | (corrected_bits[position - 1] << data_index)
                    data_index += 1
            m.d.comb += [self.ecc_data.eq(data_expr),
                         self.ecc_corrected.eq(overall & (syndrome != 0)),
                         self.ecc_uncorrectable.eq(~overall & (syndrome != 0))]
        else:
            m.d.comb += [self.ecc_data.eq(0), self.ecc_corrected.eq(0), self.ecc_uncorrectable.eq(0)]
        with amaranth_if(m, self.reset | self.counter_clear):
            m.d.utility += self.counter_value.eq(0)
        with amaranth_elif(m, self.counter_enable):
            with amaranth_if(m, self.counter_value != Const((1 << c.counter_bits) - 1, c.counter_bits)):
                m.d.utility += self.counter_value.eq(self.counter_value + 1)
        return m


# Source-compatible alias for internal family consumers. / 供 family 内部消费者使用的源兼容别名。
Utility = UtilityBoundary


# =============================================================================
# Public Adapter
# =============================================================================
# Emit deterministic UHSC-localized utility Verilog. / 导出确定性的 UHSC utility Verilog。
# Export deterministic utility Verilog. / 导出确定性的 utility Verilog。
def build_verilog(configuration, injected_dependencies):
    """Return Verilog for the aggregated utility boundary. / 返回聚合 utility 边界的 Verilog。"""

    del injected_dependencies
    if isinstance(configuration, UtilityConfig):
        cfg = configuration
        name = "UHSCUtility"
    elif isinstance(configuration, dict):
        fields = UtilityConfig.__dataclass_fields__
        kwargs: dict[str, Any] = {}
        for key, value in configuration.items():
            if key in fields:
                kwargs[key] = bool(value) if key in {"queue_enable", "ecc_enable"} else int(value)
        cfg = UtilityConfig(**kwargs)
        name = str(configuration.get("module", configuration.get("name", "UHSCUtility")))
    elif configuration is None:
        cfg = UtilityConfig()
        name = "UHSCUtility"
    else:
        raise TypeError("configuration must be UtilityConfig, dict, or None")
    top = UtilityBoundary(cfg)
    ports = [top.clock, top.reset, top.valid, *top.values, top.selected_valid,
             top.selected_value, top.selected_index, top.pointer_value,
             top.pointer_increment, top.pointer_next, top.pointer_wrap,
             top.parity_value, top.parity_bit, top.counter_enable,
             top.counter_clear, top.counter_value, top.critical_error]
    if cfg.queue_enable:
        ports.extend([top.queue_push, top.queue_pop, top.queue_push_value,
                      top.queue_head_valid, top.queue_head_value, top.queue_level,
                      top.queue_full, top.queue_empty])
    if cfg.ecc_enable:
        ports.extend([top.ecc_code, top.ecc_data, top.ecc_corrected,
                      top.ecc_uncorrectable])
    return verilog.convert(top, name=name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print a deterministic default export for direct smoke tests. / 为 direct smoke 测试打印确定性默认导出。
# Print a direct default export. / 打印 direct 默认导出。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
