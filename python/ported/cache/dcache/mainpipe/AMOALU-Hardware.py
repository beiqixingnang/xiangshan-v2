"""V2 AMO arithmetic/logic unit. / V2 AMO 算术逻辑单元。"""

from __future__ import annotations

from dataclasses import dataclass

from amaranth import Cat, Const, Module, Mux, Signal
from amaranth.lib.wiring import Component, In, Out


# =============================================================================
# Module Contract
# =============================================================================
# Public symbols / 公开符号:
#   - AMOALUConfig, AMOALU, build_verilog, main
# Port contract / 端口契约:
#   - mask(operandBits/8), cmd(M_SZ=5), lhs/rhs/out/out_unmasked
# Real logic / 真实逻辑 (verbatim):
#   - max/min/add/or/and/xor decode from cmd; adder with lane partitioning
#     (carry cut at masked wide lanes); lane-wide compare for narrow widths,
#     hierarchical compare for wide; result merged with lhs through the
#     byte-replicated wmask into out, with the raw result on out_unmasked.
#   / 与 Scala AMOALU 一致的解码、分段加法器、比较器与掩码合并。
# Status / 状态: PYTHON_PRESENT_UNVERIFIED (phase-1 bulk port / 阶段一批量重写)
__all__ = ["AMOALUConfig", "AMOALU", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
M_XA_ADD, M_XA_XOR, M_XA_OR = 0b01000, 0b01001, 0b01010
M_XA_AND, M_XA_MIN, M_XA_MAX = 0b01011, 0b01100, 0b01101
M_XA_MINU, M_XA_MAXU = 0b01110, 0b01111


@dataclass(frozen=True)
class AMOALUConfig:
    # frozen config / 冻结配置
    operandBits: int = 64
    minXLen: int = 32

    # Validate the widths used by the V2 AMOALU implementation. / 校验 V2 AMOALU 使用的位宽。
    def __post_init__(self) -> None:
        if self.operandBits < self.minXLen:
            raise ValueError("operandBits must be at least minXLen")
        if self.minXLen != 32:
            raise ValueError("V2 AMOALU has a fixed 32-bit minimum XLEN")
        if self.operandBits % self.minXLen:
            raise ValueError("operandBits must be a multiple of minXLen")
        ratio = self.operandBits // self.minXLen
        if ratio & (ratio - 1):
            raise ValueError("operandBits/minXLen must be a power of two")


# =============================================================================
# Implementation
# =============================================================================
class AMOALU(Component):
    # AMO arithmetic-logic unit / AMO 运算逻辑单元
    def __init__(self, cfg: AMOALUConfig | None = None):
        c = cfg or AMOALUConfig()
        self.cfg = c
        super().__init__({
            "io_mask": In(c.operandBits // 8),
            "io_cmd": In(5),
            "io_lhs": In(c.operandBits),
            "io_rhs": In(c.operandBits),
            "io_out": Out(c.operandBits),
            "io_out_unmasked": Out(c.operandBits),
        })
        self.mask = self.io_mask
        self.cmd = self.io_cmd
        self.lhs = self.io_lhs
        self.rhs = self.io_rhs
        self.out = self.io_out
        self.out_unmasked = self.io_out_unmasked

    # Elaborate the V2 command decoder and masked arithmetic datapath. / 展开 V2 命令译码与按掩码算术数据通路。
    def elaborate(self, platform):
        # verbatim AMO result selection / 逐字对应 AMO 结果选择
        m = Module()
        c = self.cfg
        bits = c.operandBits
        lhs = self.lhs
        rhs = self.rhs
        cmd = self.cmd

        # Compare command constants at the full five-bit width. / 以完整五位宽度比较命令常量。
        def cmd_eq(value: int):
            # Return a width-safe command equality expression. / 返回宽度安全的命令相等表达式。
            return cmd == Const(value, 5)

        isMax = cmd_eq(M_XA_MAX) | cmd_eq(M_XA_MAXU)
        isMin = cmd_eq(M_XA_MIN) | cmd_eq(M_XA_MINU)
        isAdd = cmd_eq(M_XA_ADD)
        logicAnd = cmd_eq(M_XA_OR) | cmd_eq(M_XA_AND)
        logicXor = cmd_eq(M_XA_XOR) | cmd_eq(M_XA_OR)
        signed = (cmd & Const(0b10, 5)) == Const(M_XA_MIN & 0b10, 5)

        # Partition carries only at V2's XLEN boundaries. / 仅在 V2 XLEN 边界切断进位。
        cut_bits = Const(0, bits)
        widths = [self.cfg.minXLen << index
                  for index in range((bits // self.cfg.minXLen).bit_length())]
        for width in widths[:-1]:
            boundary_mask_bit = width // 8 - 1
            cut_bits = cut_bits | Mux(
                self.mask[boundary_mask_bit],
                Const(0, bits),
                Const(1 << (width - 1), bits),
            )
        adder_mask = ~cut_bits
        adderOut = (lhs & adder_mask) + (rhs & adder_mask)
        logic = Mux(logicAnd, lhs & rhs, 0) | Mux(logicXor, lhs ^ rhs, 0)

        # Build the source's recursive unsigned comparator. / 构造源代码的递归无符号比较器。
        def less_unsigned(left, right, width):
            # Compare high halves before low halves, matching Chisel CSE structure. / 先比较高半部再比较低半部，匹配 Chisel 结构。
            if width == self.cfg.minXLen:
                return left[:width] < right[:width]
            half = width // 2
            high_less = left[half:width] < right[half:width]
            high_equal = left[half:width] == right[half:width]
            return high_less | (high_equal & less_unsigned(left, right, half))

        # Apply signedness only when the operand sign bits differ. / 仅在操作数符号位不同时应用有符号规则。
        def less_signed(left, right, width):
            # Match AMOALU.isLess exactly for signed and unsigned commands. / 精确匹配 AMOALU.isLess 的有符号与无符号命令。
            return Mux(left[width - 1] == right[width - 1],
                       less_unsigned(left, right, width),
                       Mux(signed, left[width - 1], right[width - 1]))

        # PriorityMux(widths.reverse) gives the largest enabled operation width. / PriorityMux(widths.reverse) 选择启用的最大操作宽度。
        # Chisel PriorityMux defaults to its final (smallest-width) value. / Chisel PriorityMux 在无选择时默认最后一个（最小宽度）值。
        less = less_signed(lhs, rhs, widths[0])
        for width in widths[1:]:
            less = Mux(self.mask[width // 8 // 2],
                       less_signed(lhs, rhs, width), less)
        minmax = Mux(Mux(less, isMin, isMax), lhs, rhs)
        out = Mux(isAdd, adderOut, Mux(logicAnd | logicXor, logic, minmax))
        # Expand each byte-lane mask in hardware; the Python helper above is
        # only for constant callers and cannot shift a Signal.
        wmask = Cat(*[self.mask[i].replicate(8) for i in range(bits // 8)])
        m.d.comb += self.out.eq((wmask & out) | (~wmask & lhs))
        m.d.comb += self.out_unmasked.eq(out)
        return m


# =============================================================================
# Public Adapter
# =============================================================================
# Build deterministic AMOALU Verilog for the requested configuration. / 为请求配置构建确定性 AMOALU Verilog。
def build_verilog(configuration, injected_dependencies):
    # Export only the reference top-level ports; out_unmasked is optimized away
    # by the pinned Chisel design because no enclosing module observes it.
    # / 仅导出参考顶层端口；钉定 Chisel 设计未使用 out_unmasked，因此该端口被优化掉。
    from amaranth.back import verilog
    del injected_dependencies
    if configuration is None:
        config = AMOALUConfig()
        name = "AMOALU"
    elif isinstance(configuration, AMOALUConfig):
        config = configuration
        name = "AMOALU"
    elif isinstance(configuration, dict):
        values = {key: value for key, value in configuration.items()
                  if key in {"operandBits", "minXLen"}}
        config = AMOALUConfig(**values)
        name = str(configuration.get("name", "AMOALU"))
    else:
        raise TypeError("configuration must be AMOALUConfig, dict, or None")
    top = AMOALU(config)
    ports = [top.mask, top.cmd, top.lhs, top.rhs, top.out]
    return verilog.convert(top, name=name, ports=ports)


# =============================================================================
# Direct Entry
# =============================================================================
# Print the default deterministic AMOALU export. / 打印默认确定性 AMOALU 导出。
def main() -> None:
    # direct elaboration entry / 直接入口
    print(build_verilog(None, None))


if __name__ == "__main__":
    main()
