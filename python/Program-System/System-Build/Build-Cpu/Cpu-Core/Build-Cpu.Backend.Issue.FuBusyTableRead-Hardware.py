"""V2 functional-unit busy-table latency mask.
V2 功能单元忙表延迟掩码。
"""

from __future__ import annotations

from dataclasses import dataclass

from amaranth import Const, Elaboratable, Module, Mux, Signal


# =============================================================================
# Module Contract
# =============================================================================
# FuBusyTableRead.scala maps each registered FU type to its latency and ORs
# busy latency entries into an issue-entry mask.
# FuBusyTableRead.scala 将每个登记的 FU 类型映射到延迟，并把忙延迟项或入发射条目掩码。
__all__ = ["FuBusyTableReadConfig", "FuBusyTableRead", "busy_mask_reference", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class FuBusyTableReadConfig:
    """V2 busy-table geometry and latency map. / V2 忙表几何与延迟映射。"""

    num_entries: int = 16
    fu_type_width: int = 8
    latency_by_type: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8)

    # Validate latency map and dimensions. / 校验延迟映射及尺寸。
    def __post_init__(self) -> None:
        if self.num_entries < 1 or self.fu_type_width < 1:
            raise ValueError("V2 busy-table dimensions must be positive")
        if not self.latency_by_type or min(self.latency_by_type) < 0:
            raise ValueError("V2 FU latencies must be non-negative")


# =============================================================================
# Implementation
# =============================================================================
def busy_mask_reference(busy_table: int, fu_types: list[int], configuration: FuBusyTableReadConfig = FuBusyTableReadConfig()) -> int:
    """Return entries blocked by currently busy FU latencies. / 返回当前 FU 延迟忙状态阻塞的条目掩码。"""

    result = 0
    for index, fu_type in enumerate(fu_types):
        latency = configuration.latency_by_type[fu_type % len(configuration.latency_by_type)]
        if busy_table & (1 << latency):
            result |= 1 << index
    return result


class FuBusyTableRead(Elaboratable):
    """Combinational FU busy mask reader. / 组合 FU 忙掩码读取器。"""

    # Construct busy table, FU type, and output mask ports. / 构造忙表、FU 类型及输出掩码端口。
    def __init__(self, configuration: FuBusyTableReadConfig = FuBusyTableReadConfig()) -> None:
        self.configuration = configuration
        c = configuration
        self.latency_width = max(c.latency_by_type) + 1
        self.busy_table = Signal(self.latency_width, name="io_in_fuBusyTable")
        self.fu_types = [Signal(c.fu_type_width, name=f"io_in_fuTypeRegVec_{i}") for i in range(c.num_entries)]
        self.busy_mask = Signal(c.num_entries, name="io_out_fuBusyTableMask")

    # Elaborate latency-map comparisons and OR reduction. / 展开延迟映射比较和或归约。
    def elaborate(self, platform) -> Module:
        del platform
        m = Module()
        c = self.configuration
        result = Const(0, c.num_entries)
        for index, fu_type in enumerate(self.fu_types):
            blocked = Const(0, 1)
            for type_index, latency in enumerate(c.latency_by_type):
                if latency < self.latency_width:
                    blocked = blocked | ((fu_type == type_index) & self.busy_table[latency])
            result = result | Mux(blocked, Const(1 << index, c.num_entries), Const(0, c.num_entries))
        m.d.comb += self.busy_mask.eq(result)
        return m


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration=None, injected_dependencies=None) -> str:
    """Emit deterministic FuBusyTableRead Verilog. / 输出确定性的 FuBusyTableRead Verilog。"""

    del injected_dependencies
    from amaranth.back import verilog

    top = FuBusyTableRead(configuration or FuBusyTableReadConfig())
    return verilog.convert(top, name="FuBusyTableRead", ports=[top.busy_table, *top.fu_types, top.busy_mask])


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    """Print the generated busy mask reader. / 打印生成的忙掩码读取器。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
