"""V2 carry-save adders. / V2 进位保存加法器。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from amaranth import Cat, Elaboratable, Module, Signal


# =============================================================================
# Module Contract
# =============================================================================
# CSA.scala defines bit-parallel 2:2, 3:2, and 5:3 compressors.  Each output
# vector keeps the source bit index, so integer reference models are exact.
# CSA.scala 定义逐位并行 2:2、3:2、5:3 压缩器；输出向量保持位索引。
__all__ = [
    "PUBLIC_MEMBERS",
    "C_MEMBERS",
    "CSAConfig",
    "CarrySaveAdderMToN",
    "CSA2_2",
    "CSA3_2",
    "CSA5_3",
    "C22",
    "C32",
    "C53",
    "csa2_2",
    "csa3_2",
    "csa5_3",
    "csa_observation",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
PUBLIC_MEMBERS: tuple[str, ...] = ("CSA2_2", "CSA3_2", "CSA5_3", "C22", "C32", "C53")
C_MEMBERS: frozenset[str] = frozenset({"C22", "C32", "C53"})


@dataclass(frozen=True)
class CSAConfig:
    """Width and public member for one compressor family. / 压缩器族的位宽与公开成员。"""

    length: int = 10
    member: str = "CSA3_2"

    # Validate the compressor width / 校验压缩器位宽。
    def __post_init__(self) -> None:
        """Reject non-positive widths and unknown members. / 拒绝非正位宽与未知成员。"""

        if self.length < 1:
            raise ValueError("CSA length must be positive")
        if self.member not in PUBLIC_MEMBERS:
            raise ValueError(f"unknown CSA member: {self.member}")


# =============================================================================
# Implementation
# =============================================================================
# Compute a 2:2 compressor in the integer reference domain / 计算整数 2:2 压缩器。
def csa2_2(a: int, b: int, length: int) -> tuple[int, int]:
    """Return sum and carry vectors for two operands. / 返回两输入和与进位。"""

    limit = (1 << length) - 1
    return (a ^ b) & limit, (a & b) & limit


# Compute a 3:2 full-adder compressor / 计算三输入全加器压缩结果。
def csa3_2(a: int, b: int, cin: int, length: int) -> tuple[int, int]:
    """Return bitwise sum and carry vectors. / 返回逐位和与进位向量。"""

    limit = (1 << length) - 1
    xor_value = (a ^ b) & limit
    return ((xor_value ^ cin) & limit,
            ((a & b) | (xor_value & cin)) & limit)


# Compute the two-stage 5:3 compressor / 计算两级五输入三输出压缩器。
def csa5_3(a: int, b: int, c: int, d: int, e: int,
           length: int) -> tuple[int, int, int]:
    """Return the CSA5_3 output tuple. / 返回 CSA5_3 输出元组。"""

    first_sum, first_carry = csa3_2(a, b, c, length)
    second_sum, second_carry = csa3_2(first_sum, d, e, length)
    return second_sum, first_carry, second_carry


def csa_observation(values: list[int], length: int) -> dict[str, int]:
    """Return compressor outputs and reconstructed modulo sum. / 返回压缩输出与重构和。"""

    if len(values) == 2:
        result = csa2_2(values[0], values[1], length)
    elif len(values) == 3:
        result = csa3_2(values[0], values[1], values[2], length)
    elif len(values) == 5:
        result = csa5_3(values[0], values[1], values[2], values[3], values[4], length)
    else:
        raise ValueError("CSA observation expects 2, 3, or 5 operands")
    return {"sum": result[0], "carry": result[1],
            "reconstructed": sum(result) & ((1 << length) - 1)}


class CarrySaveAdderMToN(Elaboratable):
    """Base M-to-N bit-parallel compressor. / M 到 N 位并行压缩器基类。"""

    # Declare vector input and output ports / 声明向量输入输出端口。
    def __init__(self, input_count: int, output_count: int,
                 length: int) -> None:
        """Create validated compressor vectors. / 创建经过校验的压缩器向量。"""

        if input_count < 1 or output_count < 1 or length < 1:
            raise ValueError("CSA geometry must be positive")
        self.input_count = input_count
        self.output_count = output_count
        self.length = length
        self.inputs = [
            Signal(length, name=f"io_in_{index}")
            for index in range(input_count)
        ]
        self.outputs = [
            Signal(length, name=f"io_out_{index}")
            for index in range(output_count)
        ]


class CSA2_2(CarrySaveAdderMToN):
    """Two-input carry-save compressor. / 双输入进位保存压缩器。"""

    # Configure the 2:2 geometry / 配置 2:2 几何结构。
    def __init__(self, length: int) -> None:
        """Create a width-``length`` 2:2 compressor. / 创建指定宽度压缩器。"""

        super().__init__(2, 2, length)

    # Elaborate 2:2 bit equations / 展开 2:2 逐位方程。
    def elaborate(self, platform: Any) -> Module:
        """Connect sum and carry outputs. / 连接和与进位输出。"""

        del platform
        module = Module()
        sums: list[Any] = [cast(Any, self.inputs[0][index]) ^ cast(Any, self.inputs[1][index])
                for index in range(self.length)]
        carries: list[Any] = [cast(Any, self.inputs[0][index]) & cast(Any, self.inputs[1][index])
                   for index in range(self.length)]
        module.d.comb += [self.outputs[0].eq(Cat(*sums)),
                          self.outputs[1].eq(Cat(*carries))]
        return module


class CSA3_2(CarrySaveAdderMToN):
    """Three-input full-adder compressor. / 三输入全加器压缩器。"""

    # Configure the 3:2 geometry / 配置 3:2 几何结构。
    def __init__(self, length: int) -> None:
        """Create a width-``length`` 3:2 compressor. / 创建指定宽度压缩器。"""

        super().__init__(3, 2, length)

    # Elaborate 3:2 bit equations / 展开 3:2 逐位方程。
    def elaborate(self, platform: Any) -> Module:
        """Connect full-adder sum and carry outputs. / 连接全加器输出。"""

        del platform
        module = Module()
        sums = []
        carries = []
        for index in range(self.length):
            first_xor: Any = cast(Any, self.inputs[0][index]) ^ cast(Any, self.inputs[1][index])
            sums.append(cast(Any, first_xor) ^ cast(Any, self.inputs[2][index]))
            carries.append((cast(Any, self.inputs[0][index]) & cast(Any, self.inputs[1][index])) |
                           (cast(Any, first_xor) & cast(Any, self.inputs[2][index])))
        module.d.comb += [self.outputs[0].eq(Cat(*sums)),
                          self.outputs[1].eq(Cat(*carries))]
        return module


class CSA5_3(CarrySaveAdderMToN):
    """Five-input, three-output compressor. / 五输入三输出压缩器。"""

    # Configure the 5:3 geometry / 配置 5:3 几何结构。
    def __init__(self, length: int) -> None:
        """Create a width-``length`` 5:3 compressor. / 创建指定宽度压缩器。"""

        super().__init__(5, 3, length)

    # Elaborate the two cascaded full-adder stages / 展开两级全加器。
    def elaborate(self, platform: Any) -> Module:
        """Connect CSA5_3 outputs in source order. / 按源顺序连接输出。"""

        del platform
        module = Module()
        first_sum = Signal(self.length, name="csa53_first_sum")
        first_carry = Signal(self.length, name="csa53_first_carry")
        second_sum = Signal(self.length, name="csa53_second_sum")
        second_carry = Signal(self.length, name="csa53_second_carry")
        module.submodules.first = first = CSA3_2(self.length)
        module.submodules.second = second = CSA3_2(self.length)
        module.d.comb += [
            first.inputs[0].eq(self.inputs[0]),
            first.inputs[1].eq(self.inputs[1]),
            first.inputs[2].eq(self.inputs[2]),
            first_sum.eq(first.outputs[0]),
            first_carry.eq(first.outputs[1]),
            second.inputs[0].eq(first_sum),
            second.inputs[1].eq(self.inputs[3]),
            second.inputs[2].eq(self.inputs[4]),
            second_sum.eq(second.outputs[0]),
            second_carry.eq(second.outputs[1]),
            self.outputs[0].eq(second_sum),
            self.outputs[1].eq(first_carry),
            self.outputs[2].eq(second_carry),
        ]
        return module


class C22(CSA2_2):
    """One-bit 2:2 compressor. / 一位 2:2 压缩器。"""

    # Configure one-bit width / 配置一位宽度。
    def __init__(self) -> None:
        """Create the one-bit C22. / 创建一位 C22。"""

        super().__init__(1)


class C32(CSA3_2):
    """One-bit 3:2 compressor. / 一位 3:2 压缩器。"""

    # Configure one-bit width / 配置一位宽度。
    def __init__(self) -> None:
        """Create the one-bit C32. / 创建一位 C32。"""

        super().__init__(1)


class C53(CSA5_3):
    """One-bit 5:3 compressor. / 一位 5:3 压缩器。"""

    # Configure one-bit width / 配置一位宽度。
    def __init__(self) -> None:
        """Create the one-bit C53. / 创建一位 C53。"""

        super().__init__(1)


# =============================================================================
# Public Adapter
# =============================================================================
# =============================================================================
# Emit a deterministic CSA3_2 module / 输出确定性的 CSA3_2 模块。
def build_verilog(configuration: CSAConfig | None = None,
                  injected_dependencies: dict[str, Any] | None = None) -> str:
    """Build the selected public compressor. / 构建选定的公开压缩器。"""

    del injected_dependencies
    from amaranth.back import verilog

    config = configuration or CSAConfig()
    member = config.member
    if member in C_MEMBERS:
        top = {"C22": C22, "C32": C32, "C53": C53}[member]()
    else:
        top = {"CSA2_2": CSA2_2, "CSA3_2": CSA3_2, "CSA5_3": CSA5_3}[member](config.length)
    return verilog.convert(
        top,
        name=member,
        ports=[*top.inputs, *top.outputs],
        emit_src=False,
    )


# =============================================================================
# Direct Entry
# =============================================================================
# Print the direct-entry Verilog / 打印直接入口 Verilog。
def main() -> None:
    """Print generated CSA Verilog. / 打印生成的 CSA Verilog。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
