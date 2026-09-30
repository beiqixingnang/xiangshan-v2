"""V2 asynchronous-read issue data array.
V2 异步读发射数据阵列。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from amaranth import Array, Elaboratable, Module, Mux, Signal


# =============================================================================
# Module Contract
# =============================================================================
# DataArray.scala wraps an asynchronous multi-read, multi-write register
# array. Reads are combinational; writes occur on the active clock edge.
# DataArray.scala 封装异步多读多写寄存器阵列：读为组合逻辑，写在时钟沿发生。
__all__ = ["DataArrayConfig", "DataArray", "data_array_reference", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class DataArrayConfig:
    """V2 data-array geometry. / V2 数据阵列几何配置。"""

    data_width: int = 32
    num_read: int = 2
    num_write: int = 2
    num_entries: int = 8

    # Validate all array dimensions. / 校验所有阵列尺寸。
    def __post_init__(self) -> None:
        if min(self.data_width, self.num_read, self.num_write, self.num_entries) < 1:
            raise ValueError("V2 data array dimensions must be positive")


# =============================================================================
# Implementation
# =============================================================================
def data_array_reference(state: list[int], reads: list[int], writes: list[tuple[bool, int, int]], width: int) -> tuple[list[int], list[int]]:
    """Model combinational reads and next-state writes. / 建模组合读取及下一状态写入。"""

    mask = (1 << width) - 1
    read_values = [state[address] & mask for address in reads]
    next_state = list(state)
    seen: set[int] = set()
    for enable, address, value in writes:
        if enable and address not in seen:
            next_state[address] = value & mask
            seen.add(address)
    return read_values, next_state


class DataArray(Elaboratable):
    """Multi-port asynchronous-read register array. / 多端口异步读寄存器阵列。"""

    # Construct array ports and storage. / 构造阵列端口及存储。
    def __init__(self, configuration: DataArrayConfig = DataArrayConfig()) -> None:
        self.configuration = configuration
        c = configuration
        addr_width = max(1, (c.num_entries - 1).bit_length())
        self.read_addr = [Signal(addr_width, name=f"io_read_{i}_addr") for i in range(c.num_read)]
        self.read_data = [Signal(c.data_width, name=f"io_read_{i}_data") for i in range(c.num_read)]
        self.write_enable = [Signal(name=f"io_write_{i}_en") for i in range(c.num_write)]
        self.write_addr = [Signal(addr_width, name=f"io_write_{i}_addr") for i in range(c.num_write)]
        self.write_data = [Signal(c.data_width, name=f"io_write_{i}_data") for i in range(c.num_write)]

    # Elaborate asynchronous reads and edge-triggered writes. / 展开异步读取和时钟沿写入。
    def elaborate(self, platform) -> Module:
        del platform
        m = Module()
        c = self.configuration
        storage = Array(Signal(c.data_width, reset=0, name=f"entry_{i}") for i in range(c.num_entries))
        for port in range(c.num_read):
            read_value = storage[0]
            for index in range(1, c.num_entries):
                read_value = Mux(self.read_addr[port] == index, storage[index], read_value)
            m.d.comb += self.read_data[port].eq(read_value)
        for port in range(c.num_write):
            for index in range(c.num_entries):
                with cast(Any, m.If(self.write_enable[port] & (self.write_addr[port] == index))):
                    m.d.sync += storage[index].eq(self.write_data[port])
        return m


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration=None, injected_dependencies=None) -> str:
    """Emit deterministic DataArray Verilog. / 输出确定性的 DataArray Verilog。"""

    del injected_dependencies
    from amaranth.back import verilog

    top = DataArray(configuration or DataArrayConfig())
    return verilog.convert(top, name="DataArray", ports=[*top.read_addr, *top.read_data,
                        *top.write_enable, *top.write_addr, *top.write_data])


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    """Print the generated data array. / 打印生成的数据阵列。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
