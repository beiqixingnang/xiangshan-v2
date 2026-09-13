"""CryptoUtils (AES/SM4 helpers: shifts, shift-rows, GF(2^8) mix, S-box tables). / 密码助手（AES/SM4：移位、行移位、GF(2^8) 混列、S-box 表）。"""

from __future__ import annotations

from typing import Any, cast

from amaranth import Cat, Const, Mux


# =============================================================================
# Module Contract
# =============================================================================
# Public symbols / 公开符号:
#   - SHR32/SHR64/ROR32/ROR64 : constant-amount shift/rotate (zero/sign-extend)
#   - ForwardShiftRows/InverseShiftRows : AES byte permutations (real)
#   - XtN/Xt2/ByteEnc/ByteDec/MixFwd/MixInv : GF(2^8) AES mix columns (real)
#   - SboxAesTop/Out, SboxIaesTop/Out, SboxSm4Top/Out, SboxInv, SboxAes/Iaes/Sm4
#     : S-box ROM lookups (CONTRACT — truth-table values external)
#   - build_verilog, main
# Real logic: SHR/ROR are constant-amount barrel ops returning XLEN (zero or
# sign extended per source). ForwardShiftRows/InverseShiftRows permute 8 bytes
# from (src1, src2). Xt2 = (byte<<1) ^ (byte[7] ? 0x1b : 0) truncated to 8;
# XtN selects byte/byte<<1/<<2/<<3 by a 4-bit selector t; ByteEnc/ByteDec
# XOR-combine XtN with constant coeffs (2,3 / e,b,d,9); MixFwd/MixInv pack 4
# ByteEnc/Dec results (rotated input). The S-box lookups are TruthTable ROMs
# whose concrete values are CONTRACT (external injection); passthrough identity.
# / 真实逻辑：SHR/ROR 为常量桶形操作返回 XLEN（按源符号或零扩展）。
# ForwardShiftRows/InverseShiftRows 对 (src1,src2) 的 8 字节置换。Xt2 =
# (byte<<1)^(byte[7]?0x1b:0) 截 8 位；XtN 按 4 位 t 选 byte/<<1/<<2/<<3；
# ByteEnc/ByteDec 用常量系数（2,3 / e,b,d,9）异或组合 XtN；MixFwd/MixInv
# 打包 4 个 ByteEnc/Dec 结果（输入旋转）。S-box 查表为 TruthTable ROM，
# 具体值为契约（外部注入），此处透传。
# Status / 状态: PYTHON_PRESENT_UNVERIFIED (phase-1 bulk port / 阶段一批量重写)
__all__ = ["SHR32", "SHR64", "ROR32", "ROR64", "ForwardShiftRows",
           "InverseShiftRows", "XtN", "Xt2", "ByteEnc", "ByteDec",
           "MixFwd", "MixInv", "SboxAesTop", "SboxAesOut", "SboxIaesTop",
           "SboxIaesOut", "SboxSm4Top", "SboxSm4Out", "SboxInv",
           "SboxAes", "SboxIaes", "SboxSm4", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
# (no tunable configuration at this granularity / 本粒度无可调配置)

# =============================================================================
# Implementation
# =============================================================================
def SHR32(bits, shamt):
    # 32-bit logical right, zero-extended to 64 / 逻辑右移零扩展至 64
    assert 0 < shamt < 32
    if shamt == 31:
        return Cat(Const(0, 63), bits.bit_select(31, 1))
    return Cat(Const(0, 32 + shamt), bits.bit_select(shamt, 32 - shamt))


def SHR64(bits, shamt):
    assert 0 < shamt < 64
    if shamt == 63:
        return Cat(bits.bit_select(0, 63), bits.bit_select(63, 1))
    return Cat(Const(0, shamt), bits.bit_select(shamt, 64 - shamt))


def ROR32(bits, shamt):
    # 32-bit rotate, zero-extended high 32 / 32 位循环右移高 32 位补零
    assert 0 < shamt < 32
    if shamt == 1:
        return Cat(Const(0, 32), bits.bit_select(0, 1), bits.bit_select(1, 31))
    if shamt == 31:
        return Cat(Const(0, 32), bits.bit_select(0, 31), bits.bit_select(31, 1))
    return Cat(Const(0, 32), bits.bit_select(0, shamt), bits.bit_select(shamt, 32 - shamt))


def ROR64(bits, shamt):
    assert 0 < shamt < 64
    if shamt == 1:
        return Cat(bits.bit_select(0, 1), bits.bit_select(1, 63))
    if shamt == 63:
        return Cat(bits.bit_select(0, 63), bits.bit_select(63, 1))
    return Cat(bits.bit_select(0, shamt), bits.bit_select(shamt, 64 - shamt))


def ForwardShiftRows(src1, src2):
    # AES forward shift-rows byte permutation / AES 行移位置换
    return [src1[0], src1[5], src2[2], src2[7],
            src1[4], src2[1], src2[6], src1[3]]


def InverseShiftRows(src1, src2):
    return [src1[0], src2[5], src2[2], src1[7],
            src1[4], src1[1], src2[6], src2[3]]


def Xt2(byte):
    # GF(2^8) xtime / GF 乘 2
    return ((byte << 1) ^ Mux(byte.bit_select(7, 1), Const(0x1b, 9), Const(0, 9))).bit_select(0, 8)


def XtN(byte, t):
    # byte * (1 + t0*2 + t1*4 + t2*8) selector / 按 t 选择
    byte1 = Xt2(byte)
    byte2 = Xt2(byte1)
    byte3 = Xt2(byte2)
    res = Mux(t.bit_select(0, 1), byte, Const(0, 8))
    res = res ^ Mux(t.bit_select(1, 1), byte1, Const(0, 8))
    res = res ^ Mux(t.bit_select(2, 1), byte2, Const(0, 8))
    res = res ^ Mux(t.bit_select(3, 1), byte3, Const(0, 8))
    return res.bit_select(0, 8)


def ByteEnc(bytes_):
    # MixColumns forward row / 正向混列行
    a = cast(Any, XtN(bytes_[0], Const(0x2, 4)))
    b = cast(Any, XtN(bytes_[1], Const(0x3, 4)))
    return a ^ b ^ cast(Any, bytes_[2]) ^ cast(Any, bytes_[3])


def ByteDec(bytes_):
    # InvMixColumns row / 逆向混列行
    a = cast(Any, XtN(bytes_[0], Const(0xe, 4)))
    b = cast(Any, XtN(bytes_[1], Const(0xb, 4)))
    c = cast(Any, XtN(bytes_[2], Const(0xd, 4)))
    d = cast(Any, XtN(bytes_[3], Const(0x9, 4)))
    return a ^ b ^ c ^ d


def MixFwd(bytes_):
    # 4 rotated ByteEnc packed little-endian / 4 行正向混列小端打包
    return Cat(ByteEnc([bytes_[3], bytes_[0], bytes_[1], bytes_[2]]),
               ByteEnc([bytes_[2], bytes_[3], bytes_[0], bytes_[1]]),
               ByteEnc([bytes_[1], bytes_[2], bytes_[3], bytes_[0]]),
               ByteEnc([bytes_[0], bytes_[1], bytes_[2], bytes_[3]]))


def MixInv(bytes_):
    return Cat(ByteDec([bytes_[3], bytes_[0], bytes_[1], bytes_[2]]),
               ByteDec([bytes_[2], bytes_[3], bytes_[0], bytes_[1]]),
               ByteDec([bytes_[1], bytes_[2], bytes_[3], bytes_[0]]),
               ByteDec([bytes_[0], bytes_[1], bytes_[2], bytes_[3]]))


# ---- S-box lookups: CONTRACT (truth-table ROM values external) ----
# / S-box 查表：契约（真值表 ROM 外部注入），此处透传
def SboxAesTop(i):
    # 8-bit -> 18-bit top ROM (CONTRACT passthrough) / 顶 ROM 透传
    return [i.bit_select(b, 1) for b in range(8)] + [Const(0, 10)]


def SboxIaesTop(i):
    return [i.bit_select(b, 1) for b in range(8)] + [Const(0, 10)]


def SboxSm4Top(i):
    return [i.bit_select(b, 1) for b in range(8)] + [Const(0, 13)]


def SboxInv(i):
    # 21-bit -> 21-bit inverse stage (CONTRACT passthrough) / 逆阶段透传
    return list(i) + [Const(0, 21 - len(i))] if len(i) < 21 else list(i)


def SboxAesOut(i):
    # 18-bit -> 8-bit out (CONTRACT passthrough) / 出 ROM 透传
    return Cat(*[i[b] for b in range(8)]) if len(i) >= 8 else Const(0, 8)


def SboxIaesOut(i):
    return Cat(*[i[b] for b in range(8)]) if len(i) >= 8 else Const(0, 8)


def SboxSm4Out(i):
    return Cat(*[i[b] for b in range(8)]) if len(i) >= 8 else Const(0, 8)


def SboxAes(byte):
    return byte  # CONTRACT passthrough / 契约透传


def SboxIaes(byte):
    return byte


def SboxSm4(byte):
    return byte


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(config=None, name: str = "CryptoUtils") -> str:
    return "// CryptoUtils is a pure helper module (no hardware).\n"


def main() -> None:
    print(build_verilog())


if __name__ == "__main__":
    main()


# =============================================================================
# Direct Entry
# =============================================================================
# ``main`` provides the bounded direct entry used by static and smoke checks.
