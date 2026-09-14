"""Generate contiguous low-zero masks from an unsigned count.
从无符号计数生成低位连续零掩码。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amaranth import Cat, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# V2 UIntToContLow0s emits 2**uintWidth-1 bits with the low input-count bits
# clear and all remaining bits set.  Its high companion is Chisel Reverse.
# V2 UIntToContLow0s 输出 2**uintWidth-1 位，输入计数对应的低位清零，其余置一；
# 高位伴随函数对应 Chisel Reverse。  The public ports preserve Scala names.
__all__ = [
    "UIntToContConfig",
    "UIntToContLow0s",
    "UIntToContHigh0s",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class UIntToContConfig:
    """Input width for the contiguous-mask helper. / 连续掩码输入宽度。"""

    uintWidth: int = 8

    # Validate the finite V2 parameter range. / 校验有限的 V2 参数范围。
    def __post_init__(self) -> None:
        if self.uintWidth < 1:
            raise ValueError("uintWidth must be positive")


# =============================================================================
# Implementation
# =============================================================================
# Build one low-contiguous-zero expression with Scala bit ordering. / 按 Scala 位序构造低位连续零表达式。
def contiguous_low_zeros(data: Any, output_width: int) -> Any:
    if output_width < 1:
        raise ValueError("output_width must be positive")
    return Cat(*[
        Mux(index < data, Const(0, 1), Const(1, 1))
        for index in range(output_width)
    ])


# Reverse a value in the same least-significant-first order as Chisel Reverse. / 按与 Chisel Reverse 相同的最低位优先顺序反转值。
def reverse_value(value: Any, width: int) -> Any:
    if width < 1:
        raise ValueError("width must be positive")
    return Cat(*[value[width - 1 - index] for index in range(width)])


class UIntToContLow0s(Elaboratable):
    """Emit a low-contiguous-zero mask. / 输出低位连续零掩码。"""

    # Construct the exact V2 input/output ports. / 构造精确的 V2 输入输出端口。
    def __init__(self, configuration: UIntToContConfig | None = None):
        config = configuration or UIntToContConfig()
        self.config = config
        self.outWidth = (1 << config.uintWidth) - 1
        self.dataIn = Signal(config.uintWidth, name="io_dataIn")
        self.dataOut = Signal(self.outWidth, name="io_dataOut")

    # Elaborate the combinational contiguous mask. / 展开组合连续掩码。
    def elaborate(self, platform):
        del platform
        module = Module()
        module.d.comb += self.dataOut.eq(
            contiguous_low_zeros(self.dataIn, self.outWidth)
        )
        return module


# Return a high-contiguous-zero expression for an existing Amaranth value. / 为已有 Amaranth 值返回高位连续零表达式。
def UIntToContHigh0s(uint: Any, width: int | None = None) -> Any:
    input_width = uint.shape().width
    base_width = (1 << input_width) - 1
    requested_width = base_width if width is None else width
    if requested_width < 1:
        raise ValueError("width must be positive")
    low = contiguous_low_zeros(uint, base_width)
    if requested_width <= base_width:
        selected = low[:requested_width]
    else:
        selected = Cat(low, Const(0, requested_width - base_width))
    return reverse_value(selected, requested_width)


# =============================================================================
# Public Adapter
# =============================================================================
# Emit deterministic Verilog with the required two-argument adapter. / 使用规定的双参数适配器输出确定性 Verilog。
def build_verilog(configuration, injected_dependencies) -> str:
    del injected_dependencies
    top = UIntToContLow0s(configuration)
    return verilog.convert(
        top, name="UIntToContLow0s", ports=[top.dataIn, top.dataOut], emit_src=False
    )


# =============================================================================
# Direct Entry
# =============================================================================
# Print the default V2 module for direct command-line use. / 直接打印默认 V2 模块。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
