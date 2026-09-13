"""AMOALU: AMO arithmetic unit (add/logic/min-max with byte lanes). / AMOALU：AMO 运算单元（按字节通道的加/逻辑/最值）。"""

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
    minWidth: int = 8
    comparatorLeafWidth: int = 32


# =============================================================================
# Implementation
# =============================================================================
def _interleave_mask(mask: int, operand_bits: int) -> int:
    # FillInterleaved(8): byte mask to bit mask / 字节掩码展开为位掩码
    out = 0
    for i in range(operand_bits // 8):
        if (mask >> i) & 1:
            out |= 0xFF << (8 * i)
    return out


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

    def elaborate(self, platform):
        # verbatim AMO result selection / 逐字对应 AMO 结果选择
        m = Module()
        c = self.cfg
        bits = c.operandBits
        lhs = self.lhs
        rhs = self.rhs
        cmd = self.cmd
        isMax = (cmd == M_XA_MAX) | (cmd == M_XA_MAXU)
        isMin = (cmd == M_XA_MIN) | (cmd == M_XA_MINU)
        isAdd = cmd == M_XA_ADD
        logicAnd = (cmd == M_XA_OR) | (cmd == M_XA_AND)
        logicXor = (cmd == M_XA_XOR) | (cmd == M_XA_OR)
        signed = (cmd == M_XA_MIN) | (cmd == M_XA_MAX)
        byte_count = Const(0, max(1, (bits // 8 + 1).bit_length()))
        for lane in range(bits // 8):
            byte_count = byte_count + self.mask[lane]
        lane_add8 = Cat(*[
            (lhs.word_select(lane, 8) + rhs.word_select(lane, 8))[:8]
            for lane in range(bits // 8)
        ])
        lane_add16 = Cat(*[
            (lhs.word_select(lane, 16) + rhs.word_select(lane, 16))[:16]
            for lane in range(bits // 16)
        ])
        # The wide path cuts the carry at the 32-bit boundary when the
        # corresponding mask byte is not active, matching AMOALU.scala.
        # / 宽通路在对应掩码字节未激活时于 32 位边界切断进位，与 AMOALU.scala 一致。
        carry_cut = Mux(self.mask[3], (1 << bits) - 1, ((1 << bits) - 1) ^ (1 << 31))
        wide_add = (lhs & carry_cut) + (rhs & carry_cut)
        narrow_add = Mux(byte_count == 1, lane_add8,
                         Mux(byte_count == 2, lane_add16, 0))
        adderOut = Mux(byte_count < 4, narrow_add, wide_add)
        logic = Mux(logicAnd, lhs & rhs, 0) | Mux(logicXor, lhs ^ rhs, 0)
        # signed/unsigned hierarchical lane compare / 有符号/无符号分层通道比较
        def less_for_width(left, right, width):
            # Match AMOALU's sign-aware hierarchical comparator / 匹配 AMOALU 的有符号分层比较器
            unsigned_less = left[:width] < right[:width]
            return Mux(left[width - 1] == right[width - 1], unsigned_less,
                       Mux(signed, left[width - 1], right[width - 1]))

        narrow_less8 = Const(0, 1)
        for lane in range(bits // 8):
            narrow_less8 = narrow_less8 | (self.mask[lane] & less_for_width(
                lhs.word_select(lane, 8), rhs.word_select(lane, 8), 8))
        narrow_less16 = Const(0, 1)
        for lane in range(bits // 16):
            narrow_less16 = narrow_less16 | (self.mask[lane * 2] & less_for_width(
                lhs.word_select(lane, 16), rhs.word_select(lane, 16), 16))
        narrow_less = Mux(byte_count == 1, narrow_less8,
                          Mux(byte_count == 2, narrow_less16, 0))
        wide_less = Mux(self.mask[bits // 16], less_for_width(lhs, rhs, bits),
                        Mux(self.mask[bits // 32], less_for_width(lhs, rhs, 32), 0))
        less = Mux(byte_count < 4, narrow_less, wide_less)
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
def build_verilog(config: AMOALUConfig | None = None,
                  name: str = "AMOALU") -> str:
    # Export only the reference top-level ports; out_unmasked is optimized away
    # by the pinned Chisel design because no enclosing module observes it.
    # / 仅导出参考顶层端口；钉定 Chisel 设计未使用 out_unmasked，因此该端口被优化掉。
    from amaranth.back import verilog
    top = AMOALU(config)
    ports = [top.mask, top.cmd, top.lhs, top.rhs, top.out]
    return verilog.convert(top, name=name, ports=ports)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    # direct elaboration entry / 直接入口
    print(build_verilog())


if __name__ == "__main__":
    main()
