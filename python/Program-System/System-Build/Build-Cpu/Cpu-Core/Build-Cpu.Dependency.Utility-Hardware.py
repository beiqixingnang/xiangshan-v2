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

from dataclasses import dataclass
from typing import Any

from amaranth import Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
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
    "parity_encode",
    "build_verilog",
    "main",
]


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

    # Validate finite hardware geometry. / 校验有限硬件几何参数。
    def __post_init__(self) -> None:
        if self.pointer_bits < 1 or self.data_bits < 1 or self.counter_bits < 1:
            raise ValueError("utility widths must be positive")
        if self.source_count < 1 or self.source_count > 32:
            raise ValueError("utility source_count must be in [1, 32]")


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


# Compute even parity. / 计算偶校验。
def parity_encode(value: int, width: int = 64) -> int:
    """Return even parity over a fixed-width word. / 返回固定宽度字的偶校验位。"""

    if width < 1:
        raise ValueError("parity width must be positive")
    return (value & ((1 << width) - 1)).bit_count() & 1


class UtilityBoundary(Elaboratable):
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
        with m.If(self.reset | self.counter_clear):
            m.d.utility += self.counter_value.eq(0)
        with m.Elif(self.counter_enable):
            with m.If(self.counter_value != Const((1 << c.counter_bits) - 1, c.counter_bits)):
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
        cfg = UtilityConfig(**{key: int(value) for key, value in configuration.items() if key in fields})
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
