"""ShiftUtils (barrel shift/rotate helpers). / 移位旋转桶形助手。"""

from __future__ import annotations

from amaranth import Cat, Const, Mux


# =============================================================================
# Module Contract
# =============================================================================
# Public symbols / 公开符号:
#   - doShiftLeft, doShiftRightArith, doShiftRotateLeft, doShiftRotateRight,
#     doShiftRotateLeftWord, doShiftRotateRightWord : barrel helpers
#   - build_verilog, main
# Real logic: MSB-first barrel recursion over shift bits (mirrors
# backend/fu/util/ShiftUtils.scala). Chisel Cat(a, b) is MSB-first, amaranth
# Cat is LSB-first — argument order reversed accordingly. Word variants
# sign-extend the rotated result by the shift amount width.
# / 真实逻辑：按移位位 MSB 优先的桶形递归（镜像 ShiftUtils.scala）。Chisel
# Cat(a,b) 高位在前，amaranth Cat 低位在前——参数顺序相应反转。字宽变体
# 按移位宽度对旋转结果符号扩展。
# Status / 状态: PYTHON_PRESENT_UNVERIFIED (phase-1 bulk port / 阶段一批量重写)
__all__ = ["doShiftLeft", "doShiftRightArith", "doShiftRotateLeft",
           "doShiftRotateRight", "doShiftRotateLeftWord",
           "doShiftRotateRightWord", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
# (no tunable configuration at this granularity / 本粒度无可调配置)

# =============================================================================
# Implementation
# =============================================================================
def doShiftLeft(in_v, shift):
    # Cat(in.tail(amount), 0(amount)) MSB-first -> amaranth Cat(0, low)
    # / 高位在前拼接，amaranth 反转为低位在前
    w = in_v.shape().width
    L = shift.shape().width
    out = in_v
    for bit in range(L):
        amount = 1 << (L - 1 - bit)
        if amount >= w:
            continue
        tail = out.bit_select(0, w - amount)
        cat = Cat(Const(0, amount), tail)
        out = Mux(shift.bit_select(L - 1 - bit, 1), cat, out)
    return out


def doShiftRightArith(in_v, shift):
    w = in_v.shape().width
    L = shift.shape().width
    out = in_v
    for bit in range(L):
        amount = 1 << (L - 1 - bit)
        if amount >= w:
            continue
        head = out.bit_select(amount, w - amount)
        sign = out.bit_select(w - 1, 1)
        cat = Cat(head, *[sign for _ in range(amount)])
        out = Mux(shift.bit_select(L - 1 - bit, 1), cat, out)
    return out


def doShiftRotateLeft(in_v, shift):
    w = in_v.shape().width
    L = shift.shape().width
    out = in_v
    for bit in range(L):
        amount = 1 << (L - 1 - bit)
        if amount >= w:
            continue
        low = out.bit_select(0, w - amount)
        high = out.bit_select(w - amount, amount)
        cat = Cat(high, low)
        out = Mux(shift.bit_select(L - 1 - bit, 1), cat, out)
    return out


def doShiftRotateRight(in_v, shift):
    w = in_v.shape().width
    L = shift.shape().width
    out = in_v
    for bit in range(L):
        amount = 1 << (L - 1 - bit)
        if amount >= w:
            continue
        low = out.bit_select(0, amount)
        high = out.bit_select(amount, w - amount)
        # Chisel ``Cat(low_bits, high_bits)`` places the low source bit in
        # the destination MSB; reverse arguments for Amaranth's LSB-first
        # ``Cat`` so this is a numerical rotate-right.
        cat = Cat(high, low)
        out = Mux(shift.bit_select(L - 1 - bit, 1), cat, out)
    return out


def doShiftRotateLeftWord(in_v, shamt):
    # rotate then sign-extend by amount / 旋转后按量符号扩展
    w = in_v.shape().width
    L = shamt.shape().width
    amount = 1 << L
    rotated = doShiftRotateLeft(in_v, shamt)
    sign = rotated.bit_select(w - 1, 1)
    return Cat(rotated, *[sign for _ in range(amount)])


def doShiftRotateRightWord(in_v, shamt):
    w = in_v.shape().width
    L = shamt.shape().width
    amount = 1 << L
    rotated = doShiftRotateRight(in_v, shamt)
    sign = rotated.bit_select(w - 1, 1)
    return Cat(rotated, *[sign for _ in range(amount)])


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(config=None, name: str = "ShiftUtils") -> str:
    return "// ShiftUtils is a pure helper module (no hardware).\n"


def main() -> None:
    print(build_verilog())


if __name__ == "__main__":
    main()


# =============================================================================
# Direct Entry
# =============================================================================
# ``main`` provides the bounded direct entry used by static and smoke checks.
