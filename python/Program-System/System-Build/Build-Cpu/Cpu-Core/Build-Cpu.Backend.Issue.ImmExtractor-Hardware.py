"""V2 immediate extractor for the XiangShan issue boundary.
V2 香山发射边界的立即数提取器。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from amaranth import Cat, Const, Elaboratable, Module, Mux, Signal


# =============================================================================
# Module Contract
# =============================================================================
# ImmExtractor.scala selects one ImmUnion encoding from a 32-bit instruction
# fragment and sign/zero extends it to the configured integer data width.
# ImmExtractor.scala 从 32 位指令片段选择 ImmUnion 编码，并扩展到数据宽度。
__all__ = [
    "IMM_TYPES",
    "ImmExtractorConfig",
    "ImmExtractor",
    "decode_immediate",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
IMM_TYPES = {
    "X": 0x7,
    "S": 0xE,
    "SB": 0x1,
    "U": 0x2,
    "UJ": 0x3,
    "I": 0x4,
    "Z": 0x5,
    "B6": 0x8,
    "OPIVIS": 0x9,
    "OPIVIU": 0xA,
    "LUI32": 0xB,
    "VSETVLI": 0xC,
    "VSETIVLI": 0xD,
    "VRORVI": 0xF,
}


@dataclass(frozen=True)
class ImmExtractorConfig:
    """Serializable immediate extractor geometry. / 可序列化立即数几何配置。"""

    data_bits: int = 64
    imm_type_set: tuple[int, ...] = tuple(sorted(set(IMM_TYPES.values())))

    # Validate the V2 width and four-bit selector. / 校验 V2 位宽与四位选择器。
    def __post_init__(self) -> None:
        if self.data_bits < 32:
            raise ValueError("data_bits must be at least 32")
        if any(value < 0 or value > 0xF for value in self.imm_type_set):
            raise ValueError("imm_type_set values must fit four bits")


# =============================================================================
# Implementation
# =============================================================================
# Replicate a one-bit expression. / 复制一个单比特表达式。
def replicate(bit, count: int):
    """Return ``count`` copies of one bit. / 返回一个比特的 ``count`` 份复制。"""

    return Cat(*[bit for _ in range(count)]) if count else Const(0, 0)


# Sign-extend an Amaranth value to the configured width. / 将 Amaranth 值符号扩展到配置宽度。
def sign_extend(value, width: int):
    """Return a width-bit sign extension. / 返回指定宽度的符号扩展值。"""

    value_width = len(value)
    if value_width > width:
        return value[:width]
    return Cat(value, replicate(value[value_width - 1], width - value_width))


# Zero-extend an Amaranth value to the configured width. / 将 Amaranth 值零扩展到配置宽度。
def zero_extend(value, width: int):
    """Return a width-bit zero extension. / 返回指定宽度的零扩展值。"""

    value_width = len(value)
    if value_width > width:
        return value[:width]
    return Cat(value, Const(0, width - value_width))


# Extract one immediate union from a Python integer. / 从 Python 整数提取一种立即数联合编码。
def decode_immediate(instruction: int, imm_type: int, data_bits: int = 64) -> int:
    """Model the V2 ``ImmUnion`` table for deterministic tests.
    为确定性测试建模 V2 ``ImmUnion`` 表。
    """

    instruction &= 0xFFFFFFFF

    # Return a signed value represented in an unsigned data-width word.
    # 返回以无符号数据宽度字表示的有符号值。
    def signed(value: int, bits: int) -> int:
        value &= (1 << bits) - 1
        if value & (1 << (bits - 1)):
            value -= 1 << bits
        return value & ((1 << data_bits) - 1)

    # Return a zero-extended value. / 返回零扩展值。
    def unsigned(value: int, bits: int) -> int:
        return value & ((1 << bits) - 1)

    if imm_type == IMM_TYPES["I"]:
        return signed(instruction >> 20, 12)
    if imm_type == IMM_TYPES["S"]:
        value = ((instruction >> 25) << 5) | ((instruction >> 7) & 0x1F)
        return signed(value, 12)
    if imm_type == IMM_TYPES["SB"]:
        value = (
            ((instruction >> 31) & 1) << 11
            | ((instruction >> 7) & 1) << 10
            | ((instruction >> 25) & 0x3F) << 4
            | ((instruction >> 8) & 0xF) << 0
        ) << 1
        return signed(value, 13)
    if imm_type == IMM_TYPES["U"]:
        return signed(instruction & 0xFFFFF000, 32)
    if imm_type == IMM_TYPES["UJ"]:
        value = (
            ((instruction >> 31) & 1) << 19
            | ((instruction >> 12) & 0xFF) << 11
            | ((instruction >> 20) & 1) << 10
            | ((instruction >> 25) & 0x3F) << 4
            | ((instruction >> 21) & 0xF) << 0
        ) << 1
        return signed(value, 21)
    if imm_type == IMM_TYPES["Z"]:
        value = ((instruction >> 7) & 0x1F) << 17
        value |= ((instruction >> 15) & 0x1F) << 12
        value |= (instruction >> 20) & 0xFFF
        return signed(value, 22)
    if imm_type == IMM_TYPES["B6"]:
        return unsigned(instruction >> 20, 6)
    if imm_type == IMM_TYPES["OPIVIS"]:
        return signed(instruction >> 15, 5)
    if imm_type == IMM_TYPES["OPIVIU"]:
        return unsigned(instruction >> 15, 5)
    if imm_type == IMM_TYPES["VSETVLI"]:
        return signed(instruction >> 20, 11)
    if imm_type == IMM_TYPES["VSETIVLI"]:
        value = ((instruction >> 15) & 0x1F) << 10
        value |= (instruction >> 20) & 0x3FF
        return signed(value, 15)
    if imm_type == IMM_TYPES["LUI32"]:
        return signed(instruction, 32)
    if imm_type == IMM_TYPES["VRORVI"]:
        value = (((instruction >> 26) & 1) << 5) | ((instruction >> 15) & 0x1F)
        return unsigned(value, 6)
    return 0


class ImmExtractor(Elaboratable):
    """Combinational V2 immediate selector. / V2 组合立即数选择器。"""

    # Construct the explicit V2 ports. / 构造显式 V2 端口。
    def __init__(self, configuration: ImmExtractorConfig = ImmExtractorConfig()) -> None:
        self.configuration = configuration
        self.instruction = Signal(32, name="io_in_imm")
        self.imm_type = Signal(4, name="io_in_immType")
        self.immediate = Signal(configuration.data_bits, name="io_out_imm")

    # Elaborate all ImmUnion extraction equations. / 展开全部 ImmUnion 提取方程。
    def elaborate(self, platform) -> Module:
        del platform
        m = Module()
        c = self.configuration
        inst = self.instruction
        values = {
            IMM_TYPES["I"]: sign_extend(inst[20:32], c.data_bits),
            IMM_TYPES["S"]: sign_extend(Cat(inst[7:12], inst[25:32]), c.data_bits),
            IMM_TYPES["SB"]: sign_extend(
                Cat(Const(0, 1), inst[8:12], inst[25:31], inst[7], inst[31]),
                c.data_bits,
            ),
            IMM_TYPES["U"]: sign_extend(Cat(Const(0, 12), inst[12:32]), c.data_bits),
            IMM_TYPES["UJ"]: sign_extend(
                Cat(Const(0, 1), inst[21:25], inst[25:31], inst[20], inst[12:20], inst[31]),
                c.data_bits,
            ),
            IMM_TYPES["Z"]: sign_extend(Cat(inst[20:32], inst[15:20], inst[7:12]), c.data_bits),
            IMM_TYPES["B6"]: zero_extend(inst[20:26], c.data_bits),
            IMM_TYPES["OPIVIS"]: sign_extend(inst[15:20], c.data_bits),
            IMM_TYPES["OPIVIU"]: zero_extend(inst[15:20], c.data_bits),
            IMM_TYPES["VSETVLI"]: sign_extend(inst[20:31], c.data_bits),
            IMM_TYPES["VSETIVLI"]: sign_extend(Cat(inst[20:30], inst[15:20]), c.data_bits),
            IMM_TYPES["LUI32"]: sign_extend(inst, c.data_bits),
            IMM_TYPES["VRORVI"]: zero_extend(Cat(inst[15:20], inst[26]), c.data_bits),
        }
        result = Const(0, c.data_bits)
        for selector in sorted(c.imm_type_set):
            if selector in values:
                result = Mux(self.imm_type == selector, values[selector], result)
        m.d.comb += self.immediate.eq(result)
        return m


# =============================================================================
# Public Adapter
# =============================================================================
# Build deterministic Verilog from the explicit adapter contract. / 按显式适配器契约生成确定性 Verilog。
def build_verilog(configuration=None, injected_dependencies=None) -> str:
    """Emit the standalone ImmExtractor module. / 输出独立 ImmExtractor 模块。"""

    del injected_dependencies
    from amaranth.back import verilog

    config = configuration or ImmExtractorConfig()
    top = ImmExtractor(config)
    return verilog.convert(top, name="ImmExtractor", ports=[top.instruction, top.imm_type, top.immediate])


# =============================================================================
# Direct Entry
# =============================================================================
# Run the direct adapter and print generated Verilog. / 运行直接适配器并打印生成的 Verilog。
def main() -> None:
    """Print the deterministic module. / 打印确定性模块。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
