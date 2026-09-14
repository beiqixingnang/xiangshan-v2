"""V2 extension instruction patterns from XiangShan. / 香山 V2 扩展指令模式。"""

from __future__ import annotations

from typing import Any

from amaranth import Const, Elaboratable, Module, Signal


# =============================================================================
# Module Contract
# =============================================================================
# The pinned V2 source defines the Zvbb and Zimop BitPat objects in this file.
# Zabha is intentionally absent: it is not present in this V2 source path.
# 锁定 V2 源文件只定义 Zvbb 与 Zimop；Zabha 不在该源路径，不能臆造迁移。
__all__ = [
    "Zvbb",
    "Zimop",
    "PATTERNS",
    "pattern_mask_expected",
    "match32",
    "InstructionPatternProbe",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
PATTERNS = {
    "zvbb_vandn_vv": "b000001???????????000?????1010111",
    "zvbb_vandn_vx": "b000001???????????100?????1010111",
    "zvbb_vbrev_v": "b010010??????01010010?????1010111",
    "zvbb_vbrev8_v": "b010010??????01000010?????1010111",
    "zvbb_vrev8_v": "b010010??????01001010?????1010111",
    "zvbb_vclz_v": "b010010??????01100010?????1010111",
    "zvbb_vctz_v": "b010010??????01101010?????1010111",
    "zvbb_vcpop_v": "b010010??????01110010?????1010111",
    "zvbb_vrol_vv": "b010101???????????000?????1010111",
    "zvbb_vrol_vx": "b010101???????????100?????1010111",
    "zvbb_vror_vi": "b01010????????????011?????1010111",
    "zvbb_vror_vv": "b010100???????????000?????1010111",
    "zvbb_vror_vx": "b010100???????????100?????1010111",
    "zvbb_vwsll_vi": "b110101???????????011?????1010111",
    "zvbb_vwsll_vv": "b110101???????????000?????1010111",
    "zvbb_vwsll_vx": "b110101???????????100?????1010111",
    "zimop_mop_r": "b1?00??0111???????100?????1110011",
    "zimop_mop_rr": "b1?00??1??????????100?????1110011",
}


# =============================================================================
# Implementation
# =============================================================================
# Convert a Chisel BitPat string into a mask and expected value / 转换 Chisel 位模式。
def pattern_mask_expected(pattern: str) -> tuple[int, int]:
    """Return ``(mask, expected)`` for one 32-bit BitPat. / 转换位模式。"""

    text = pattern.replace("_", "")
    if text.startswith("b"):
        text = text[1:]
    if not text or len(text) > 32 or any(bit not in "01?" for bit in text):
        raise ValueError(f"invalid BitPat: {pattern!r}")
    text = text.rjust(32, "?")
    mask = 0
    expected = 0
    for bit in text:
        mask <<= 1
        expected <<= 1
        if bit != "?":
            mask |= 1
            expected |= int(bit)
    return mask, expected


# Match one BitPat against an integer instruction / 用整数匹配一个 BitPat。
def match32(pattern: str, value: int) -> bool:
    """Match a pattern against a 32-bit integer. / 将模式与 32 位整数匹配。"""

    if not isinstance(value, int):
        raise TypeError("match32 accepts an integer; use InstructionPatternProbe for hardware")
    mask, expected = pattern_mask_expected(pattern)
    return (value & 0xFFFFFFFF & mask) == expected


class Zvbb:
    """Zvbb instruction patterns. / Zvbb 指令模式集合。"""

    VANDN_VV = PATTERNS["zvbb_vandn_vv"]
    VANDN_VX = PATTERNS["zvbb_vandn_vx"]
    VBREV_V = PATTERNS["zvbb_vbrev_v"]
    VBREV8_V = PATTERNS["zvbb_vbrev8_v"]
    VREV8_V = PATTERNS["zvbb_vrev8_v"]
    VCLZ_V = PATTERNS["zvbb_vclz_v"]
    VCTZ_V = PATTERNS["zvbb_vctz_v"]
    VCPOP_V = PATTERNS["zvbb_vcpop_v"]
    VROL_VV = PATTERNS["zvbb_vrol_vv"]
    VROL_VX = PATTERNS["zvbb_vrol_vx"]
    VROR_VI = PATTERNS["zvbb_vror_vi"]
    VROR_VV = PATTERNS["zvbb_vror_vv"]
    VROR_VX = PATTERNS["zvbb_vror_vx"]
    VWSLL_VI = PATTERNS["zvbb_vwsll_vi"]
    VWSLL_VV = PATTERNS["zvbb_vwsll_vv"]
    VWSLL_VX = PATTERNS["zvbb_vwsll_vx"]


class Zimop:
    """Zimop instruction patterns. / Zimop 指令模式集合。"""

    MOP_R = PATTERNS["zimop_mop_r"]
    MOP_RR = PATTERNS["zimop_mop_rr"]


class InstructionPatternProbe(Elaboratable):
    """Expose all V2 pattern matches as combinational outputs. / 输出模式匹配。"""

    # Declare instruction input and one output per source BitPat / 声明输入与输出。
    def __init__(self) -> None:
        """Create the pattern probe ports. / 创建模式探针端口。"""

        self.instruction = Signal(32, name="instruction")
        self.matches = {name: Signal(name=name) for name in PATTERNS}

    # Build the mask comparisons / 构建掩码比较逻辑。
    def elaborate(self, platform: Any) -> Module:
        """Elaborate all pattern comparisons. / 展开全部模式比较。"""

        del platform
        module = Module()
        for name, pattern in PATTERNS.items():
            mask, expected = pattern_mask_expected(pattern)
            module.d.comb += self.matches[name].eq(
                (self.instruction & Const(mask, 32)) == Const(expected, 32)
            )
        return module


# =============================================================================
# Public Adapter
# =============================================================================
# Emit deterministic Verilog for the V2 pattern probe / 输出 V2 模式探针 Verilog。
def build_verilog(configuration: Any = None,
                  injected_dependencies: dict[str, Any] | None = None) -> str:
    """Build the standalone pattern probe. / 构建独立模式探针。"""

    del configuration, injected_dependencies
    from amaranth.back import verilog

    top = InstructionPatternProbe()
    return verilog.convert(
        top,
        name="Instructions",
        ports=[top.instruction, *top.matches.values()],
        emit_src=False,
    )


# =============================================================================
# Direct Entry
# =============================================================================
# Print the direct-entry Verilog / 打印直接入口 Verilog。
def main() -> None:
    """Print a deterministic probe. / 打印确定性探针。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
