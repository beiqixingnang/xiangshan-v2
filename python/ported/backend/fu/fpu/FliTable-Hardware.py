"""V2 FLI immediate tables. / V2 FLI 浮点立即数表。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from amaranth import Const, Elaboratable, Module, Mux, Signal


# =============================================================================
# Module Contract
# =============================================================================
# FliTable.scala maps every 5-bit source to a 16-bit table value.  The three
# concrete tables below are copied byte-for-byte from the pinned V2 source.
# FliTable.scala 将 5 位输入映射到 16 位值；以下三张表逐项来自锁定 V2 源码。
__all__ = [
    "FliTableConfig",
    "FliTable",
    "FliHTable",
    "FliSTable",
    "FliDTable",
    "decode_fli",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
FLI_H = (
    0xBC00, 0x0400, 0x0100, 0x0200, 0x1C00, 0x2000, 0x2C00, 0x3000,
    0x3400, 0x3500, 0x3600, 0x3700, 0x3800, 0x3900, 0x3A00, 0x3B00,
    0x3C00, 0x3D00, 0x3E00, 0x3F00, 0x4000, 0x4100, 0x4200, 0x4400,
    0x4800, 0x4C00, 0x5800, 0x5C00, 0x7800, 0x7C00, 0x7C00, 0x7E00,
)
FLI_S = (
    0xBF80, 0x0080, 0x3780, 0x3800, 0x3B80, 0x3C00, 0x3D80, 0x3E00,
    0x3E80, 0x3EA0, 0x3EC0, 0x3EE0, 0x3F00, 0x3F20, 0x3F40, 0x3F60,
    0x3F80, 0x3FA0, 0x3FC0, 0x3FE0, 0x4000, 0x4020, 0x4040, 0x4080,
    0x4100, 0x4180, 0x4300, 0x4380, 0x4700, 0x4780, 0x7F80, 0x7FC0,
)
FLI_D = (
    0xBFF0, 0x0010, 0x3EF0, 0x3F00, 0x3F70, 0x3F80, 0x3FB0, 0x3FC0,
    0x3FD0, 0x3FD4, 0x3FD8, 0x3FDC, 0x3FE0, 0x3FE4, 0x3FE8, 0x3FEC,
    0x3FF0, 0x3FF4, 0x3FF8, 0x3FFC, 0x4000, 0x4004, 0x4008, 0x4010,
    0x4020, 0x4030, 0x4060, 0x4070, 0x40E0, 0x40F0, 0x7FF0, 0x7FF8,
)


@dataclass(frozen=True)
class FliTableConfig:
    """Widths and values for one FLI decoder. / FLI 解码器宽度与值。"""

    src_width: int = 5
    out_width: int = 16
    table: tuple[int, ...] = FLI_H

    # Validate table geometry / 校验表格几何约束。
    def __post_init__(self) -> None:
        """Reject impossible widths and values. / 拒绝非法宽度和值。"""

        if self.src_width < 1 or self.out_width < 1:
            raise ValueError("FLI widths must be positive")
        if len(self.table) > (1 << self.src_width):
            raise ValueError("FLI table is larger than the source domain")
        limit = 1 << self.out_width
        if any(value < 0 or value >= limit for value in self.table):
            raise ValueError("FLI value exceeds output width")


# =============================================================================
# Implementation
# =============================================================================
# Decode a table using the PLA's zero default / 用 PLA 的零默认值解码表。
def decode_fli(table: Sequence[int], source: int,
               src_width: int = 5, out_width: int = 16) -> int:
    """Return one deterministic table entry. / 返回一个确定的表项。"""

    if source < 0 or source >= (1 << src_width):
        raise ValueError("source is outside the FLI input domain")
    value = table[source] if source < len(table) else 0
    return value & ((1 << out_width) - 1)


class FliTable(Elaboratable):
    """Combinational FLI table decoder. / 组合式 FLI 表解码器。"""

    # Declare the source and output ports / 声明输入输出端口。
    def __init__(self, configuration: FliTableConfig | None = None) -> None:
        """Create a configured table decoder. / 创建配置好的表解码器。"""

        self.configuration = configuration or FliTableConfig()
        self.src = Signal(self.configuration.src_width, name="src")
        self.out = Signal(self.configuration.out_width, name="out")

    # Elaborate the priority-equivalent PLA / 展开等价 PLA。
    def elaborate(self, platform: Any) -> Module:
        """Connect every source value to its table constant. / 连接所有表项。"""

        del platform
        module = Module()
        expression = 0
        for source in range(1 << self.configuration.src_width):
            value = decode_fli(
                self.configuration.table,
                source,
                self.configuration.src_width,
                self.configuration.out_width,
            )
            expression = Mux(
                self.src == Const(source, self.configuration.src_width),
                Const(value, self.configuration.out_width),
                expression,
            )
        module.d.comb += self.out.eq(expression)
        return module


class FliHTable(FliTable):
    """Half-precision FLI table. / 半精度 FLI 表。"""

    # Select the V2 half-precision table / 选择 V2 半精度表。
    def __init__(self) -> None:
        """Create the half-precision decoder. / 创建半精度解码器。"""

        super().__init__(FliTableConfig(table=FLI_H))


class FliSTable(FliTable):
    """Single-precision FLI table. / 单精度 FLI 表。"""

    # Select the V2 single-precision table / 选择 V2 单精度表。
    def __init__(self) -> None:
        """Create the single-precision decoder. / 创建单精度解码器。"""

        super().__init__(FliTableConfig(table=FLI_S))


class FliDTable(FliTable):
    """Double-precision FLI table. / 双精度 FLI 表。"""

    # Select the V2 double-precision table / 选择 V2 双精度表。
    def __init__(self) -> None:
        """Create the double-precision decoder. / 创建双精度解码器。"""

        super().__init__(FliTableConfig(table=FLI_D))


# =============================================================================
# Public Adapter
# =============================================================================
# =============================================================================
# Emit the configured generic table / 输出配置好的通用表。
def build_verilog(configuration: FliTableConfig | None = None,
                  injected_dependencies: dict[str, Any] | None = None) -> str:
    """Build deterministic FLI Verilog. / 构建确定性的 FLI Verilog。"""

    del injected_dependencies
    from amaranth.back import verilog

    top = FliTable(configuration)
    return verilog.convert(top, name="FliTable", ports=[top.src, top.out], emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print a default half-precision table / 打印默认半精度表。
def main() -> None:
    """Print generated Verilog. / 打印生成的 Verilog。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
