"""V2 predecode instruction patterns and branch attributes.
V2 预译码指令模式与分支属性。
"""

from __future__ import annotations

from dataclasses import dataclass

from amaranth import Const, Elaboratable, Module, Mux, Signal


# =============================================================================
# Module Contract
# =============================================================================
# Patterns and priority follow backend/decode/isa/predecode/predecode.scala;
# the probe additionally exposes the branch/call/return attributes used by IFU.
# 模式及优先级遵循 predecode.scala；探针额外暴露 IFU 使用的分支/调用/返回属性。
__all__ = [
    "PATTERNS",
    "PreDecodeInstConfig",
    "PreDecodeInstProbe",
    "pattern_mask_expected",
    "match_pattern",
    "decode_branch",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
PATTERNS = {
    "C_J": "b????????????????_101_?_??_???_??_???_01",
    "C_EBREAK": "b????????????????_100_?_00_000_00_000_10",
    "C_JALR": "b????????????????_100_?_??_???_00_000_10",
    "C_BRANCH": "b????????????????_11?_?_??_???_??_???_01",
    "JAL": "b????????????????_???_?????_1101111",
    "JALR": "b????????????????_000_?????_1100111",
    "BRANCH": "b????????????????_???_?????_1100011",
    "NOP": "b???????????????0_100_01010_0000001",
}


@dataclass(frozen=True)
class PreDecodeInstConfig:
    """Probe output geometry. / 探针输出几何配置。"""

    instruction_width: int = 32

    # Validate the fixed RISC-V instruction width. / 校验固定 RISC-V 指令位宽。
    def __post_init__(self) -> None:
        if self.instruction_width != 32:
            raise ValueError("V2 predecode patterns require 32 instruction bits")


# =============================================================================
# Implementation
# =============================================================================
# Convert a Chisel BitPat string to mask and expected value. / 将 Chisel BitPat 字符串转换为掩码与期望值。
def pattern_mask_expected(pattern: str) -> tuple[int, int]:
    """Return ``(mask, expected)`` for a 32-bit pattern. / 返回 32 位模式的 ``(mask, expected)``。"""

    text = pattern.replace("_", "")
    if text.startswith("b"):
        text = text[1:]
    text = text.rjust(32, "?")
    if len(text) != 32 or any(bit not in "01?" for bit in text):
        raise ValueError(f"invalid BitPat: {pattern!r}")
    mask = 0
    expected = 0
    for bit in text:
        mask <<= 1
        expected <<= 1
        if bit != "?":
            mask |= 1
            expected |= int(bit)
    return mask, expected


PATTERN_VALUES = {name: pattern_mask_expected(value) for name, value in PATTERNS.items()}


# Match one pattern against an instruction integer. / 将一个模式与指令整数匹配。
def match_pattern(pattern: str, instruction: int) -> bool:
    """Return whether the fixed bits match. / 返回固定比特是否匹配。"""

    mask, expected = pattern_mask_expected(pattern)
    return (instruction & mask) == expected


# Decode the ordered branch table and RAS attributes. / 解码有序分支表及 RAS 属性。
def decode_branch(instruction: int) -> dict[str, int | bool | str]:
    """Model ``PreDecodeInst.brTable`` plus ``HasPdConst.brInfo``.
    建模 ``PreDecodeInst.brTable`` 与 ``HasPdConst.brInfo``。
    """

    instruction &= 0xFFFFFFFF
    ordered = ("C_EBREAK", "C_J", "C_JALR", "C_BRANCH", "JAL", "JALR", "BRANCH")
    branch_type = 0
    matched = "NONE"
    for name in ordered:
        if match_pattern(PATTERNS[name], instruction):
            matched = name
            branch_type = {"C_J": 2, "C_EBREAK": 0, "C_JALR": 3,
                           "C_BRANCH": 1, "JAL": 2, "JALR": 3,
                           "BRANCH": 1}[name]
            break
    is_rvc = (instruction & 0x3) != 0x3
    rd = ((instruction >> 12) & 1) if is_rvc else ((instruction >> 7) & 0x1F)
    rs = (0 if branch_type == 2 else ((instruction >> 7) & 0x1F)) if is_rvc else ((instruction >> 15) & 0x1F)
    is_call = (((branch_type == 2) and not is_rvc) or branch_type == 3) and rd in (1, 5)
    is_ret = branch_type == 3 and rs in (1, 5) and not is_call
    return {
        "matched": matched,
        "branch_type": branch_type,
        "is_rvc": is_rvc,
        "is_call": bool(is_call),
        "is_ret": bool(is_ret),
    }


class PreDecodeInstProbe(Elaboratable):
    """Combinational pattern and branch-attribute probe. / 组合模式与分支属性探针。"""

    # Construct instruction and observable output ports. / 构造指令及可观察输出端口。
    def __init__(self, configuration: PreDecodeInstConfig = PreDecodeInstConfig()) -> None:
        self.configuration = configuration
        self.instruction = Signal(32, name="io_instr")
        self.branch_type = Signal(2, name="io_branchType")
        self.is_rvc = Signal(name="io_isRVC")
        self.is_call = Signal(name="io_isCall")
        self.is_ret = Signal(name="io_isRet")
        self.pattern_matches = {
            name: Signal(name=f"io_match_{name}") for name in PATTERNS
        }

    # Elaborate ordered BitPat matching and RAS formulas. / 展开有序 BitPat 匹配及 RAS 方程。
    def elaborate(self, platform) -> Module:
        del platform
        m = Module()
        inst = self.instruction
        matches = {}
        for name, (mask, expected) in PATTERN_VALUES.items():
            matches[name] = (inst & mask) == expected
            m.d.comb += self.pattern_matches[name].eq(matches[name])

        branch = Const(0, 2)
        ordered = (("C_EBREAK", 0), ("C_J", 2), ("C_JALR", 3),
                   ("C_BRANCH", 1), ("JAL", 2), ("JALR", 3), ("BRANCH", 1))
        for name, value in reversed(ordered):
            branch = Mux(matches[name], value, branch)
        is_rvc = inst[:2] != 3
        rd = Mux(is_rvc, inst[12], inst[7:12])
        rs_rvc = Mux(branch == 2, 0, inst[7:12])
        rs = Mux(is_rvc, rs_rvc, inst[15:20])
        link_rd = (rd == 1) | (rd == 5)
        link_rs = (rs == 1) | (rs == 5)
        is_call = (((branch == 2) & ~is_rvc) | (branch == 3)) & link_rd
        is_ret = (branch == 3) & link_rs & ~is_call
        m.d.comb += [
            self.branch_type.eq(branch),
            self.is_rvc.eq(is_rvc),
            self.is_call.eq(is_call),
            self.is_ret.eq(is_ret),
        ]
        return m


# =============================================================================
# Public Adapter
# =============================================================================
# Emit deterministic Verilog for the pattern probe. / 为模式探针输出确定性 Verilog。
def build_verilog(configuration=None, injected_dependencies=None) -> str:
    """Build the standalone predecode probe. / 构建独立预译码探针。"""

    del injected_dependencies
    from amaranth.back import verilog

    top = PreDecodeInstProbe(configuration or PreDecodeInstConfig())
    return verilog.convert(
        top,
        name="PreDecodeInstProbe",
        ports=[top.instruction, top.branch_type, top.is_rvc, top.is_call,
               top.is_ret, *top.pattern_matches.values()],
    )


# =============================================================================
# Direct Entry
# =============================================================================
# Print generated predecode Verilog. / 打印生成的预译码 Verilog。
def main() -> None:
    """Print deterministic Verilog. / 打印确定性 Verilog。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
