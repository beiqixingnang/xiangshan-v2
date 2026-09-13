"""UInt to a low-contiguous-one mask.

Amaranth port of ``UIntToContLow1s`` from the pinned XiangShan snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from amaranth import Cat, Const, Elaboratable, Module, Mux, Signal


# =============================================================================
# Module Contract
# =============================================================================
# ``UIntToContLow1s`` returns (2**uintWidth - 1) bits. For input ``n`` the low
# ``n`` bits are one and all higher bits are zero; zero yields all zeros and
# the maximum input yields all ones. ``UIntToContHigh1s`` reverses the bits.
__all__ = [
    "UIntToContConfig",
    "UIntToContLow1s",
    "UIntToContHigh1s",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class UIntToContConfig:
    """Width of the unsigned priority input / 无符号优先编码输入宽度。"""

    uintWidth: int = 8


# =============================================================================
# Implementation
# =============================================================================
def bit_view(value: Any, index: int) -> Any:
    """Return one bit while keeping Amaranth's view type out of Pyright."""

    return cast(Any, value.bit_select(index, 1))


def ones_constant(width: int) -> Any:
    """Create a width-sized all-one constant / 创建指定宽度全一常量。"""

    return cast(Any, Const((1 << width) - 1, width))


def zeros_constant(width: int) -> Any:
    """Create a width-sized all-zero constant / 创建指定宽度全零常量。"""

    return cast(Any, Const(0, width))


def reverse_value(value: Any, width: int) -> Any:
    """Reverse bit order, matching Chisel ``Reverse``."""

    return cast(Any, Cat(*[bit_view(value, width - 1 - index)
                           for index in range(width)]))


def contiguous_low1s(data: Any) -> Any:
    """Recursively build the low-contiguous-one mask."""

    width = data.shape().width
    if width < 1:
        raise ValueError("data width must be positive")
    if width == 1:
        return cast(Any, Mux(bit_view(data, 0), ones_constant(1),
                             zeros_constant(1)))

    half = 1 << (width - 1)
    low = contiguous_low1s(data.bit_select(0, width - 1))
    # Chisel's two branches place the helper on opposite sides of the
    # constant. Account for Amaranth's least-significant-first Cat order.
    return cast(Any, Mux(
        bit_view(data, width - 1),
        Cat(ones_constant(half), low),
        Cat(low, zeros_constant(half)),
    ))


class UIntToContLow1s(Elaboratable):
    """Generate ``2**uintWidth - 1`` low-contiguous-one bits."""

    def __init__(self, configuration: UIntToContConfig | None = None):
        config = configuration or UIntToContConfig()
        if config.uintWidth < 1:
            raise ValueError("uintWidth must be positive")
        self.config = config
        self.outWidth = (1 << config.uintWidth) - 1
        self.dataIn = Signal(config.uintWidth, name="io_dataIn")
        self.dataOut = Signal(self.outWidth, name="io_dataOut")

    def elaborate(self, platform):
        module = Module()
        module.d.comb += self.dataOut.eq(contiguous_low1s(self.dataIn))
        return module


def UIntToContHigh1s(uint: Any) -> Any:
    """Return the bit-reversed low-one mask for an existing value."""

    width = uint.shape().width
    return reverse_value(contiguous_low1s(uint), (1 << width) - 1)


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(
    configuration: UIntToContConfig | None = None,
    injected_dependencies: dict | None = None,
    name: str = "UIntToContLow1s",
) -> str:
    """Emit deterministic Verilog for the low-one implementation."""

    del injected_dependencies
    from amaranth.back import verilog

    top = UIntToContLow1s(configuration)
    return verilog.convert(top, name=name,
                           ports=[top.dataIn, top.dataOut], emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    """Print the default generated Verilog / 输出默认生成的 Verilog。"""

    print(build_verilog())


if __name__ == "__main__":
    main()
