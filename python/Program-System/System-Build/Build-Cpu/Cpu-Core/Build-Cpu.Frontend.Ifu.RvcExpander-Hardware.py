"""V2 Rocket-Chip compressed decoder. / V2 Rocket-Chip 压缩指令解码器。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from amaranth import Cat, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# PreDecode.scala instantiates Rocket-Chip's RVCDecoder from RVC.scala.  The
# implementation below follows that source, including Zcb/Zcmop cases,
# RV32/RV64 selection, floating-point legality, and useAddiForMv=true.
# The top-level ports intentionally match the extracted V2 RVCExpander module.
# PreDecode.scala 使用 Rocket-Chip RVCDecoder；本实现保留完整 V2 真值表。
__all__ = [
    "RvcExpanderConfig",
    "RvcExpander",
    "decode_rvc",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class RvcExpanderConfig:
    """Set Rocket-Chip decoder parameters. / 设置 Rocket-Chip 解码器参数。"""

    XLEN: int = 64
    fLen: int = 64
    useAddiForMv: bool = True
    HasCExtension: bool = True

    # Validate the architectural parameter set. / 校验架构参数集合。
    def __post_init__(self) -> None:
        if self.XLEN not in (32, 64, 128):
            raise ValueError("XLEN must be 32, 64, or 128")
        if self.fLen not in (0, 32, 64):
            raise ValueError("fLen must be 0, 32, or 64")


# =============================================================================
# Implementation
# =============================================================================
# Extract an inclusive bit field from an integer. / 从整数提取闭区间位域。
def bit_field(value: int, high: int, low: int | None = None) -> int:
    if low is None:
        low = high
    width = high - low + 1
    return (value >> low) & ((1 << width) - 1)


# Pack high-to-low integer fields like Chisel Cat. / 按 Chisel Cat 高到低拼接整数域。
def cat_integer(*fields: tuple[int, int]) -> int:
    result = 0
    for value, width in fields:
        result = (result << width) | (value & ((1 << width) - 1))
    return result


# Sign-extend an integer field to a requested width. / 将整数位域符号扩展到指定宽度。
def sign_extend(value: int, from_width: int, to_width: int) -> int:
    value &= (1 << from_width) - 1
    if value & (1 << (from_width - 1)):
        value |= ((1 << (to_width - from_width)) - 1) << from_width
    return value & ((1 << to_width) - 1)


# Build an expanded instruction and register metadata. / 构建展开指令及寄存器元数据。
def expanded_integer(bits: int, source: int, rd: int | None = None,
                     rs1: int | None = None, rs2: int | None = None,
                     rs3: int | None = None) -> tuple[int, int, int, int, int]:
    return (
        bits & 0xFFFFFFFF,
        bit_field(source, 11, 7) if rd is None else rd & 0x1F,
        bit_field(source, 19, 15) if rs1 is None else rs1 & 0x1F,
        bit_field(source, 24, 20) if rs2 is None else rs2 & 0x1F,
        bit_field(source, 31, 27) if rs3 is None else rs3 & 0x1F,
    )


# Decode one compressed instruction using the locked Scala equations. / 按锁定 Scala 方程解码一条压缩指令。
def decode_rvc(value: int, fs_is_off: bool = False,
               configuration: RvcExpanderConfig | None = None
               ) -> tuple[int, int, int, int, int, bool]:
    """Return bits, rd/rs1/rs2/rs3, and illegal for one input word. / 返回指令字段与非法标志。"""

    cfg = configuration or RvcExpanderConfig()
    source = value & 0xFFFFFFFF
    if not cfg.HasCExtension or (source & 0x3) == 0x3:
        bits, rd, rs1, rs2, rs3 = expanded_integer(source, source)
        return bits, rd, rs1, rs2, rs3, False

    x = source
    quadrant = x & 0x3
    funct3 = bit_field(x, 15, 13)
    key = (funct3 << 2) | quadrant
    rs1p = 8 | bit_field(x, 9, 7)
    rs2p = 8 | bit_field(x, 4, 2)
    rs2 = bit_field(x, 6, 2)
    rd = bit_field(x, 11, 7)
    sp, ra, x0 = 2, 1, 0
    addi4spn_imm = cat_integer((bit_field(x, 10, 7), 4),
                               (bit_field(x, 12, 11), 2),
                               (bit_field(x, 5), 1), (bit_field(x, 6), 1), (0, 2))
    lb_imm = cat_integer((bit_field(x, 5), 1), (bit_field(x, 6), 1))
    lh_imm = cat_integer((bit_field(x, 5), 1), (0, 1))
    lw_imm = cat_integer((bit_field(x, 5), 1), (bit_field(x, 12, 10), 3),
                         (bit_field(x, 6), 1), (0, 2))
    ld_imm = cat_integer((bit_field(x, 6, 5), 2), (bit_field(x, 12, 10), 3), (0, 3))
    lwsp_imm = cat_integer((bit_field(x, 3, 2), 2), (bit_field(x, 12), 1),
                           (bit_field(x, 6, 4), 3), (0, 2))
    ldsp_imm = cat_integer((bit_field(x, 4, 2), 3), (bit_field(x, 12), 1),
                           (bit_field(x, 6, 5), 2), (0, 3))
    swsp_imm = cat_integer((bit_field(x, 8, 7), 2), (bit_field(x, 12, 9), 4), (0, 2))
    sdsp_imm = cat_integer((bit_field(x, 9, 7), 3), (bit_field(x, 12, 10), 3), (0, 3))
    lui_imm = ((0x7FFF if bit_field(x, 12) else 0) << 17) | (bit_field(x, 6, 2) << 12)
    addi16sp_imm = cat_integer((bit_field(x, 12), 1), (bit_field(x, 12), 1),
                               (bit_field(x, 12), 1), (bit_field(x, 4, 3), 2),
                               (bit_field(x, 5), 1), (bit_field(x, 2), 1),
                               (bit_field(x, 6), 1), (0, 4))
    # The first three fields above implement Fill(3, x(12)).
    addi_imm = cat_integer((bit_field(x, 12), 1), (bit_field(x, 12), 1),
                           (bit_field(x, 12), 1), (bit_field(x, 12), 1),
                           (bit_field(x, 12), 1), (bit_field(x, 12), 1),
                           (bit_field(x, 12), 1), (bit_field(x, 6, 2), 5))
    # Correct Fill(7, x(12)) is seven copies, retained explicitly for traceability.
    addi_imm = ((-1 if bit_field(x, 12) else 0) & ~0x1F) | bit_field(x, 6, 2)
    addi_imm &= 0xFFF
    j_imm = cat_integer((bit_field(x, 12), 1), (bit_field(x, 12), 1),
                        (bit_field(x, 12), 1), (bit_field(x, 12), 1),
                        (bit_field(x, 12), 1), (bit_field(x, 12), 1),
                        (bit_field(x, 12), 1), (bit_field(x, 12), 1),
                        (bit_field(x, 12), 1), (bit_field(x, 12), 1),
                        (bit_field(x, 8), 1), (bit_field(x, 10, 9), 2),
                        (bit_field(x, 6), 1), (bit_field(x, 7), 1),
                        (bit_field(x, 2), 1), (bit_field(x, 11), 1),
                        (bit_field(x, 5, 3), 3), (0, 1))
    j_imm &= (1 << 21) - 1
    b_imm = cat_integer((bit_field(x, 12), 1), (bit_field(x, 12), 1),
                        (bit_field(x, 12), 1), (bit_field(x, 12), 1),
                        (bit_field(x, 12), 1), (bit_field(x, 6, 5), 2),
                        (bit_field(x, 2), 1), (bit_field(x, 11, 10), 2),
                        (bit_field(x, 4, 3), 2), (0, 1))
    b_imm &= (1 << 13) - 1
    shamt = cat_integer((bit_field(x, 12), 1), (bit_field(x, 6, 2), 5))

    # Integer instruction constructors use the source's 32-bit zero extension.
    # itype responsibility. / itype 函数职责。
    def itype(imm: int, rs1_: int, funct: int, rd_: int, opcode: int,
              imm_width: int = 12) -> int:
        return cat_integer((imm, imm_width), (rs1_, 5), (funct, 3), (rd_, 5), (opcode, 7))

    # rtype responsibility. / rtype 函数职责。
    def rtype(funct7: int, rs2_: int, rs1_: int, funct: int,
              rd_: int, opcode: int = 0x33) -> int:
        return cat_integer((funct7, 7), (rs2_, 5), (rs1_, 5),
                           (funct, 3), (rd_, 5), (opcode, 7))

    # stype responsibility. / stype 函数职责。
    def stype(imm: int, rs2_: int, rs1_: int, funct: int, opcode: int,
              imm_width: int = 12) -> int:
        if imm_width < 5:
            return cat_integer((rs2_, 5), (rs1_, 5), (funct, 3),
                               (0, 3), (imm, imm_width), (opcode, 7))
        return cat_integer((imm >> 5, imm_width - 5), (rs2_, 5), (rs1_, 5),
                           (funct, 3), (imm & 0x1F, 5), (opcode, 7))

    # btype responsibility. / btype 函数职责。
    def btype(imm: int, rs2_: int, rs1_: int, funct: int) -> int:
        return cat_integer(((imm >> 12) & 1, 1), ((imm >> 5) & 0x3F, 6),
                           (rs2_, 5), (rs1_, 5), (funct, 3),
                           ((imm >> 1) & 0xF, 4), ((imm >> 11) & 1, 1), (0x63, 7))

    # jtype responsibility. / jtype 函数职责。
    def jtype(imm: int, rd_: int) -> int:
        return cat_integer(((imm >> 20) & 1, 1), ((imm >> 1) & 0x3FF, 10),
                           ((imm >> 11) & 1, 1), ((imm >> 12) & 0xFF, 8),
                           (rd_, 5), (0x6F, 7))

    out_rd, out_rs1, out_rs2, out_rs3 = rd, bit_field(x, 19, 15), bit_field(x, 24, 20), bit_field(x, 31, 27)
    illegal = False
    fp64_illegal = False if cfg.XLEN == 128 else (fs_is_off if cfg.fLen >= 64 else True)
    fp32_illegal = False if cfg.XLEN >= 64 else (fs_is_off if cfg.fLen >= 32 else True)

    if quadrant == 0:
        out_rd, out_rs1, out_rs2 = rs2p, rs1p, rs2p
        if funct3 == 0:
            out = itype(addi4spn_imm, sp, 0, rs2p, 0x13 if bit_field(x, 12, 5) else 0x1F, 10)
            out_rs1 = sp
            illegal = addi4spn_imm == 0
        elif funct3 == 1:
            out = itype(ld_imm, rs1p, 3, rs2p, 0x07, 8)
            illegal = fp64_illegal
        elif funct3 == 2:
            out = itype(lw_imm, rs1p, 2, rs2p, 0x03, 7)
        elif funct3 == 3:
            if cfg.XLEN == 32:
                out = itype(lw_imm, rs1p, 2, rs2p, 0x07, 7)
            else:
                out = itype(ld_imm, rs1p, 3, rs2p, 0x03, 8)
            illegal = fp32_illegal
        elif funct3 == 4:
            lbu = itype(lb_imm, rs1p, 4, rs2p, 0x03, 2)
            lh = itype(lh_imm, rs1p, 1 if bit_field(x, 6) else 5, rs2p, 0x03, 2)
            sb = stype(lb_imm, rs2p, rs1p, 0, 0x23, 2)
            sh = stype(lh_imm, rs2p, rs1p, 1, 0x23, 2)
            out = (lbu, lh, sb, sh)[bit_field(x, 11, 10)]
            illegal = bool(bit_field(x, 12) or (bit_field(x, 11) and bit_field(x, 10) and bit_field(x, 6)))
        elif funct3 == 5:
            out = stype(ld_imm, rs2p, rs1p, 3, 0x27, 8)
            illegal = fp64_illegal
        elif funct3 == 6:
            out = stype(lw_imm, rs2p, rs1p, 2, 0x23, 7)
        else:
            if cfg.XLEN == 32:
                out = stype(lw_imm, rs2p, rs1p, 2, 0x27, 7)
            else:
                out = stype(ld_imm, rs2p, rs1p, 3, 0x23, 8)
            illegal = fp32_illegal
    elif quadrant == 1:
        if funct3 == 0:
            out = 0x13 if rd == 0 else itype(addi_imm, rd, 0, rd, 0x13)
            out_rd, out_rs1, out_rs2 = ((0, 0, 0) if rd == 0 else
                                        (rd, rd, bit_field(x, 4, 2) | 8))
        elif funct3 == 1:
            if cfg.XLEN == 32:
                out = jtype(j_imm, ra)
                out_rd, out_rs1, out_rs2 = ra, rd, rs2p
            else:
                out = itype(addi_imm, rd, 0, rd, 0x1B if rd else 0x1F)
                out_rd, out_rs1, out_rs2 = rd, rd, rs2p
            illegal = cfg.XLEN != 32 and rd == 0
        elif funct3 == 2:
            out = itype(addi_imm, x0, 0, rd, 0x13)
            out_rd, out_rs1, out_rs2 = rd, x0, rs2p
            illegal = False
        elif funct3 == 3:
            if rd == sp:
                out = itype(addi16sp_imm, sp, 0, sp, 0x13 if addi_imm else 0x1F)
                out_rd, out_rs1, out_rs2 = rd, rd, rs2p
                illegal = addi16sp_imm == 0
            else:
                out = cat_integer(((lui_imm >> 12) & ((1 << 20) - 1), 20), (rd, 5),
                                  (0x37 if addi_imm else 0x3F, 7))
                illegal = (not (bit_field(x, 12) or bit_field(x, 6, 2))) and not (not bit_field(x, 11) and bit_field(x, 7))
                if bit_field(x, 7) and bit_field(x, 6, 2) == 0 and bit_field(x, 12, 11) == 0:
                    out = 0x13
                    out_rd, out_rs1, out_rs2 = 0, 0, 0
                else:
                    out_rd, out_rs1, out_rs2 = rd, rd, rs2p
            if bit_field(x, 7) and bit_field(x, 6, 2) == 0 and bit_field(x, 12, 11) == 0:
                out_rd, out_rs1, out_rs2 = 0, 0, 0
        elif funct3 == 4:
            srli = cat_integer((shamt, 6), (rs1p, 5), (5, 3), (rs1p, 5), (0x13, 7))
            srai = srli | (1 << 30)
            andi = itype(addi_imm, rs1p, 7, rs1p, 0x13)
            functs = (0, 4, 6, 7, 0, 0, 0, 3)
            index = (bit_field(x, 12) << 2) | bit_field(x, 6, 5)
            sub = (1 << 30) if bit_field(x, 6, 5) == 0 else 0
            opcode = 0x33 if not bit_field(x, 12) else (0x33 if bit_field(x, 6) else 0x3B)
            mul = (1 << 25) if index == 6 else 0
            zca = rtype(0, rs2p, rs1p, functs[index], rs1p, opcode) | sub | mul
            zextb = cat_integer((0xFF, 8), (rs1p, 5), (7, 3), (rs1p, 5), (0x13, 7))
            not_ = cat_integer((0xFFF, 12), (rs1p, 5), (4, 3), (rs1p, 5), (0x13, 7))
            sextb = cat_integer((0x604, 12), (rs1p, 5), (1, 3), (rs1p, 5), (0x13, 7))
            sexth = cat_integer((0x605, 12), (rs1p, 5), (1, 3), (rs1p, 5), (0x13, 7))
            zextw = 0 if cfg.XLEN == 32 else cat_integer((4, 3), (x0, 5), (rs1p, 5), (0, 3), (rs1p, 5), (0x3B, 7))
            zexth = cat_integer((0x80, 8), (rs1p, 5), (4, 3), (rs1p, 5), (0x33 if cfg.XLEN == 32 else 0x3B, 7))
            zcb = (zextb, sextb, zexth, sexth, zextw, not_, 0, 0)[bit_field(x, 4, 2)]
            rtype_out = zcb if index == 7 else zca
            out = (srli, srai, andi, rtype_out)[bit_field(x, 11, 10)]
            if bit_field(x, 6, 2) == 0x1F4 and bit_field(x, 12, 10) == 0x4:
                out = zca
            out_rd, out_rs1, out_rs2 = rs1p, rs1p, (x0 if (bit_field(x, 15, 10) << 5 | bit_field(x, 6, 2)) == 0x4FC else rs2p)
            illegal = bit_field(x, 12, 10) == 7 and bit_field(x, 6, 3) == 15
        elif funct3 == 5:
            out = jtype(j_imm, x0)
            out_rd, out_rs1, out_rs2 = x0, rs1p, rs2p
        elif funct3 == 6:
            out = btype(b_imm, x0, rs1p, 0)
            out_rd, out_rs1, out_rs2 = rs1p, rs1p, x0
        else:
            out = btype(b_imm, x0, rs1p, 1)
            out_rd, out_rs1, out_rs2 = x0, rs1p, x0
    else:  # quadrant 2
        load_opc = 0x03 if rd else 0x1F
        if funct3 == 0:
            out = cat_integer((shamt, 6), (rd, 5), (1, 3), (rd, 5), (0x13, 7))
            out_rd, out_rs1, out_rs2 = rd, rd, rs2
        elif funct3 == 1:
            out = itype(ldsp_imm, sp, 3, rd, 0x07, 9)
            out_rd, out_rs1, out_rs2 = rd, sp, rs2
            illegal = fp64_illegal
        elif funct3 == 2:
            out = itype(lwsp_imm, sp, 2, rd, load_opc, 8)
            out_rd, out_rs1, out_rs2 = rd, sp, rs2
            illegal = rd == 0
        elif funct3 == 3:
            out = (itype(lwsp_imm, sp, 2, rd, 0x07, 8)
                   if cfg.XLEN == 32 else itype(ldsp_imm, sp, 3, rd, load_opc, 9))
            out_rd, out_rs1, out_rs2 = rd, sp, rs2
            illegal = (rd == 0) if cfg.XLEN >= 64 else fp32_illegal
        elif funct3 == 4:
            mv = cat_integer((rs2, 5), (0, 3), (rd, 5), (0x13 if cfg.useAddiForMv else 0x33, 7))
            add = cat_integer((rs2, 5), (rd, 5), (0, 3), (rd, 5), (0x33, 7))
            jr = cat_integer((rs2, 5), (rd, 5), (0, 3), (x0, 5), (0x67, 7))
            reserved = cat_integer((jr >> 7, 13), (0x1F, 7))
            jr_reserved = reserved if rd == 0 else jr
            jr_mv = mv if rs2 else jr_reserved
            jalr = cat_integer((rs2, 5), (rd, 5), (0, 3), (ra, 5), (0x67, 7))
            ebreak = (jr >> 7) << 7 | 0x73 | (1 << 20)
            jalr_ebreak = jalr if rd else ebreak
            jalr_add = add if rs2 else jalr_ebreak
            out = jalr_add if bit_field(x, 12) else jr_mv
            if bit_field(x, 12):
                out_rd, out_rs1, out_rs2 = (rd, rd, rs2) if rs2 else (ra, rd, rs2)
            elif rs2:
                out_rd, out_rs1, out_rs2 = rd, rs2, x0
            else:
                out_rd, out_rs1, out_rs2 = x0, rd, rs2
            illegal = (not bit_field(x, 12) and rs2 == 0 and rd == 0)
        elif funct3 == 5:
            out = stype(sdsp_imm, rs2, sp, 3, 0x27, 9)
            out_rd, out_rs1, out_rs2 = rd, sp, rs2
            illegal = fp64_illegal
        elif funct3 == 6:
            out = stype(swsp_imm, rs2, sp, 2, 0x23, 8)
            out_rd, out_rs1, out_rs2 = rd, sp, rs2
        else:
            out = (stype(swsp_imm, rs2, sp, 2, 0x27, 8)
                   if cfg.XLEN == 32 else stype(sdsp_imm, rs2, sp, 3, 0x23, 9))
            out_rd, out_rs1, out_rs2 = rd, sp, rs2
            illegal = False if cfg.XLEN >= 64 else (fs_is_off if cfg.fLen >= 32 else True)

    return (*expanded_integer(out, x, out_rd, out_rs1, out_rs2, out_rs3), bool(illegal))


def rvc_observation(value: int, fs_is_off: bool = False,
                    configuration: RvcExpanderConfig | None = None) -> dict[str, int]:
    """Return expanded instruction fields as a named observation. / 返回压缩指令展开观测。"""

    bits, rd, rs1, rs2, rs3, illegal = decode_rvc(value, fs_is_off, configuration)
    return {"bits": bits, "rd": rd, "rs1": rs1, "rs2": rs2, "rs3": rs3, "illegal": int(illegal)}


# =============================================================================
# Amaranth implementation
# =============================================================================
# Pack Amaranth fields in Chisel's high-to-low Cat order. / 按 Chisel Cat 高到低拼接 Amaranth 字段。
def cat_high(*fields: Any) -> Any:
    return Cat(*reversed(fields))


# Zero-extend or truncate an expression to one width. / 将表达式零扩展或截断到指定宽度。
def fit_width(value: Any, width: int) -> Any:
    current = len(value)
    if current < width:
        return Cat(value, Const(0, width - current))
    return value[:width]


# Extract an inclusive Amaranth bit field. / 提取 Amaranth 闭区间位域。
def field_expr(value: Any, high: int, low: int | None = None) -> Any:
    if low is None:
        low = high
    return value[low:high + 1]


# Sign-extend an Amaranth expression. / 符号扩展 Amaranth 表达式。
def sign_extend_expr(value: Any, from_width: int, to_width: int) -> Any:
    extra = to_width - from_width
    if extra <= 0:
        return value[:to_width]
    return Cat(value, Mux(value[from_width - 1],
                           Const((1 << extra) - 1, extra),
                           Const(0, extra)))


# Construct an I-type instruction expression. / 构造 I 型指令表达式。
def i_type_expr(imm: Any, rs1: Any, funct: Any, rd: Any, opcode: Any) -> Any:
    return fit_width(cat_high(imm, rs1, funct, rd, opcode), 32)


# Construct an R-type instruction expression. / 构造 R 型指令表达式。
def r_type_expr(funct7: Any, rs2: Any, rs1: Any, funct: Any,
                rd: Any, opcode: Any = Const(0x33, 7)) -> Any:
    return fit_width(cat_high(funct7, rs2, rs1, funct, rd, opcode), 32)


# Construct an S-type instruction expression. / 构造 S 型指令表达式。
def s_type_expr(imm: Any, rs2: Any, rs1: Any, funct: Any, opcode: Any) -> Any:
    if len(imm) < 5:
        return fit_width(cat_high(rs2, rs1, funct, Const(0, 3), imm, opcode), 32)
    return fit_width(cat_high(imm[5:len(imm)], rs2, rs1, funct, imm[:5], opcode), 32)


# Construct a B-type instruction expression. / 构造 B 型指令表达式。
def b_type_expr(imm: Any, rs2: Any, rs1: Any, funct: Any) -> Any:
    return fit_width(cat_high(imm[12], imm[5:11], rs2, rs1, funct,
                              imm[1:5], imm[11], Const(0x63, 7)), 32)


# Construct a J-type instruction expression. / 构造 J 型指令表达式。
def j_type_expr(imm: Any, rd: Any) -> Any:
    return fit_width(cat_high(imm[20], imm[1:11], imm[11], imm[12:20],
                              rd, Const(0x6F, 7)), 32)


# Select one expression using a compact unsigned index mux. / 使用紧凑无符号索引多路器选择表达式。
def select_expr(index: Any, values: Sequence[Any]) -> Any:
    result = values[0]
    for number, value in enumerate(values[1:], 1):
        result = Mux(index == Const(number, len(index)), value, result)
    return result


class RvcExpander(Elaboratable):
    """Combinational V2 RVCExpander with extracted-module ports. / 带提取模块端口的组合式 V2 RVCExpander。"""

    # Declare the exact four extracted reference ports plus metadata taps. / 声明四个参考端口及元数据观察端口。
    def __init__(self, configuration: RvcExpanderConfig | None = None) -> None:
        self.configuration = configuration or RvcExpanderConfig()
        self.in_ = Signal(32, name="io_in")
        self.fsIsOff = Signal(name="io_fsIsOff")
        self.out_bits = Signal(32, name="io_out_bits")
        self.out_rd = Signal(5, name="io_out_rd")
        self.out_rs1 = Signal(5, name="io_out_rs1")
        self.out_rs2 = Signal(5, name="io_out_rs2")
        self.out_rs3 = Signal(5, name="io_out_rs3")
        self.ill = Signal(name="io_ill")

    # Elaborate Rocket-Chip q0/q1/q2/q3 decode equations. / 展开 Rocket-Chip 四象限译码方程。
    def elaborate(self, platform: Any) -> Module:
        del platform
        cfg = self.configuration
        module = Module()
        x = self.in_
        rs1p = cat_high(Const(1, 2), field_expr(x, 9, 7))
        rs2p = cat_high(Const(1, 2), field_expr(x, 4, 2))
        rs2 = field_expr(x, 6, 2)
        rd = field_expr(x, 11, 7)
        x0 = Const(0, 5)
        ra = Const(1, 5)
        sp = Const(2, 5)
        addi4spn = cat_high(field_expr(x, 10, 7), field_expr(x, 12, 11),
                            field_expr(x, 5), field_expr(x, 6), Const(0, 2))
        lb_imm = cat_high(field_expr(x, 5), field_expr(x, 6))
        lh_imm = cat_high(field_expr(x, 5), Const(0, 1))
        lw_imm = cat_high(field_expr(x, 5), field_expr(x, 12, 10),
                          field_expr(x, 6), Const(0, 2))
        ld_imm = cat_high(field_expr(x, 6, 5), field_expr(x, 12, 10), Const(0, 3))
        lwsp_imm = cat_high(field_expr(x, 3, 2), field_expr(x, 12),
                            field_expr(x, 6, 4), Const(0, 2))
        ldsp_imm = cat_high(field_expr(x, 4, 2), field_expr(x, 12),
                            field_expr(x, 6, 5), Const(0, 3))
        swsp_imm = cat_high(field_expr(x, 8, 7), field_expr(x, 12, 9), Const(0, 2))
        sdsp_imm = cat_high(field_expr(x, 9, 7), field_expr(x, 12, 10), Const(0, 3))
        lui_imm = cat_high(Const(0, 1), field_expr(x, 6, 2), Const(0, 12))
        # Fill(15, x(12)) + x(6,2) + zero is represented with an explicit Mux.
        lui_imm = cat_high(Mux(field_expr(x, 12), Const((1 << 15) - 1, 15), Const(0, 15)),
                            field_expr(x, 6, 2), Const(0, 12))
        addi16sp_imm = cat_high(field_expr(x, 12), field_expr(x, 12), field_expr(x, 12),
                                field_expr(x, 4, 3), field_expr(x, 5), field_expr(x, 2),
                                field_expr(x, 6), Const(0, 4))
        addi_imm = cat_high(Mux(field_expr(x, 12), Const(0x7F, 7), Const(0, 7)),
                            field_expr(x, 6, 2))
        j_imm = cat_high(Mux(field_expr(x, 12), Const((1 << 10) - 1, 10), Const(0, 10)),
                          field_expr(x, 8), field_expr(x, 10, 9), field_expr(x, 6),
                          field_expr(x, 7), field_expr(x, 2), field_expr(x, 11),
                          field_expr(x, 5, 3), Const(0, 1))
        b_imm = cat_high(Mux(field_expr(x, 12), Const((1 << 5) - 1, 5), Const(0, 5)),
                          field_expr(x, 6, 5), field_expr(x, 2), field_expr(x, 11, 10),
                          field_expr(x, 4, 3), Const(0, 1))
        shamt = cat_high(field_expr(x, 12), field_expr(x, 6, 2))

        # q0 expressions and legality. / q0 表达式与合法性。
        q0_bits = [
            i_type_expr(addi4spn, sp, Const(0, 3), rs2p,
                        Mux(field_expr(x, 12, 5).any(), Const(0x13, 7), Const(0x1F, 7))),
            i_type_expr(ld_imm, rs1p, Const(3, 3), rs2p, Const(0x07, 7)),
            i_type_expr(lw_imm, rs1p, Const(2, 3), rs2p, Const(0x03, 7)),
            (i_type_expr(lw_imm, rs1p, Const(2, 3), rs2p, Const(0x07, 7))
             if cfg.XLEN == 32 else i_type_expr(ld_imm, rs1p, Const(3, 3), rs2p, Const(0x03, 7))),
            select_expr(field_expr(x, 11, 10), [
                i_type_expr(lb_imm, rs1p, Const(4, 3), rs2p, Const(0x03, 7)),
                i_type_expr(lh_imm, rs1p, Mux(field_expr(x, 6), Const(1, 3), Const(5, 3)), rs2p, Const(0x03, 7)),
                s_type_expr(lb_imm, rs2p, rs1p, Const(0, 3), Const(0x23, 7)),
                s_type_expr(lh_imm, rs2p, rs1p, Const(1, 3), Const(0x23, 7)),
            ]),
            s_type_expr(ld_imm, rs2p, rs1p, Const(3, 3), Const(0x27, 7)),
            s_type_expr(lw_imm, rs2p, rs1p, Const(2, 3), Const(0x23, 7)),
            (s_type_expr(lw_imm, rs2p, rs1p, Const(2, 3), Const(0x27, 7))
             if cfg.XLEN == 32 else s_type_expr(ld_imm, rs2p, rs1p, Const(3, 3), Const(0x23, 7))),
        ]
        q0_meta = [(rs2p, sp, rs2p), (rs2p, rs1p, rs2p), (rs2p, rs1p, rs2p),
                   (rs2p, rs1p, rs2p), (rs2p, rs1p, rs2p), (rs2p, rs1p, rs2p),
                   (rs2p, rs1p, rs2p), (rs2p, rs1p, rs2p)]
        fp_ok = Const(1 if cfg.fLen > 0 else 0) & ~self.fsIsOff
        q0_ill = [
            ~field_expr(x, 12, 5).any(),
            Const(1) if cfg.XLEN != 128 and cfg.fLen < 64 else (self.fsIsOff if cfg.XLEN != 128 else Const(0)),
            Const(0),
            Const(1) if cfg.XLEN < 64 and cfg.fLen < 32 else self.fsIsOff if cfg.XLEN < 64 else Const(0),
            field_expr(x, 12) | (field_expr(x, 11) & field_expr(x, 10) & field_expr(x, 6)),
            Const(1) if cfg.XLEN != 128 and cfg.fLen < 64 else (self.fsIsOff if cfg.XLEN != 128 else Const(0)),
            Const(0),
            Const(1) if cfg.XLEN < 64 and cfg.fLen < 32 else self.fsIsOff if cfg.XLEN < 64 else Const(0),
        ]

        # q1 expressions and legality. / q1 表达式与合法性。
        nop = Const(0x13, 32)
        addi = Mux(rd == x0, nop, i_type_expr(addi_imm, rd, Const(0, 3), rd, Const(0x13, 7)))
        addiw = i_type_expr(addi_imm, rd, Const(0, 3), rd,
                            Mux(rd.any(), Const(0x1B, 7), Const(0x1F, 7)))
        jal32 = j_type_expr(j_imm, ra)
        jal64 = addiw
        li = i_type_expr(addi_imm, x0, Const(0, 3), rd, Const(0x13, 7))
        addi16sp = i_type_expr(addi16sp_imm, sp, Const(0, 3), sp,
                               Mux(addi_imm.any(), Const(0x13, 7), Const(0x1F, 7)))
        me = fit_width(cat_high(lui_imm[12:32], rd,
                                Mux(addi_imm.any(), Const(0x37, 7), Const(0x3F, 7))), 32)
        zcmop = field_expr(x, 7) & ~field_expr(x, 6, 2).any() & ~field_expr(x, 12, 11).any()
        lui = Mux(zcmop, nop, Mux(rd == sp, addi16sp, me))
        jmp = j_type_expr(j_imm, x0)
        beqz = b_type_expr(b_imm, x0, rs1p, Const(0, 3))
        bnez = b_type_expr(b_imm, x0, rs1p, Const(1, 3))
        srli = fit_width(cat_high(shamt, rs1p, Const(5, 3), rs1p, Const(0x13, 7)), 32)
        srai = srli | Const(1 << 30, 32)
        andi = i_type_expr(addi_imm, rs1p, Const(7, 3), rs1p, Const(0x13, 7))
        funct_values = [Const(v, 3) for v in (0, 4, 6, 7, 0, 0, 0, 3)]
        arith_index = cat_high(field_expr(x, 12), field_expr(x, 6, 5))
        zca = r_type_expr(Const(0, 7), rs2p, rs1p,
                          select_expr(arith_index, funct_values), rs1p,
                          Mux(field_expr(x, 12),
                              Mux(field_expr(x, 6), Const(0x33, 7), Const(0x3B, 7)),
                              Const(0x33, 7)))
        zca = zca | Mux(field_expr(x, 6, 5) == Const(0, 2), Const(1 << 30, 32), Const(0, 32))
        zca = zca | Mux(arith_index == Const(6, 3), Const(1 << 25, 32), Const(0, 32))
        zcb = select_expr(field_expr(x, 4, 2), [
            fit_width(cat_high(Const(0xFF, 8), rs1p, Const(7, 3), rs1p, Const(0x13, 7)), 32),
            fit_width(cat_high(Const(0x604, 12), rs1p, Const(1, 3), rs1p, Const(0x13, 7)), 32),
            fit_width(cat_high(Const(0x80, 8), rs1p, Const(4, 3), rs1p,
                               Const(0x33 if cfg.XLEN == 32 else 0x3B, 7)), 32),
            fit_width(cat_high(Const(0x605, 12), rs1p, Const(1, 3), rs1p, Const(0x13, 7)), 32),
            Const(0, 32) if cfg.XLEN == 32 else fit_width(cat_high(Const(4, 3), x0, rs1p, Const(0, 3), rs1p, Const(0x3B, 7)), 32),
            fit_width(cat_high(Const(0xFFF, 12), rs1p, Const(4, 3), rs1p, Const(0x13, 7)), 32),
            Const(0, 32), Const(0, 32),
        ])
        arith_rtype = Mux(arith_index == Const(7, 3), zcb, zca)
        arith = select_expr(field_expr(x, 11, 10), [srli, srai, andi, arith_rtype])
        op2_index = cat_high(field_expr(x, 15, 10), field_expr(x, 6, 2))
        op2 = Mux(op2_index == Const(0x4FC, len(op2_index)), x0, rs2p)
        arith_meta = (rs1p, rs1p, op2)
        q1_bits = [addi, jal32 if cfg.XLEN == 32 else jal64, li, lui, arith, jmp, beqz, bnez]
        addi_meta = (Mux(rd == x0, x0, rd), Mux(rd == x0, x0, rd),
                     Mux(rd == x0, x0, rs2p))
        jal_meta = ((ra, rd, rs2p) if cfg.XLEN == 32 else (rd, rd, rs2p))
        lui_meta = (Mux(zcmop, x0, Mux(rd == sp, rd, rd)),
                    Mux(zcmop, x0, Mux(rd == sp, rd, rd)),
                    Mux(zcmop, x0, rs2p))
        q1_meta = [addi_meta, jal_meta, (rd, x0, rs2p),
                   lui_meta, arith_meta, (x0, rs1p, rs2p),
                   (rs1p, rs1p, x0), (x0, rs1p, x0)]
        q1_ill = [Const(0),
                  Const(1 if cfg.XLEN != 32 else 0) & (rd == x0),
                  Const(0),
                  (~(field_expr(x, 12) | field_expr(x, 6, 2).any())) &
                  (~(~field_expr(x, 11) & field_expr(x, 7))),
                  field_expr(x, 12, 10).all() & field_expr(x, 6, 3).all(),
                  Const(0), Const(0), Const(0)]

        # q2 expressions and legality. / q2 表达式与合法性。
        load_opc = Mux(rd.any(), Const(0x03, 7), Const(0x1F, 7))
        slli = fit_width(cat_high(shamt, rd, Const(1, 3), rd, Const(0x13, 7)), 32)
        ldsp = i_type_expr(ldsp_imm, sp, Const(3, 3), rd, load_opc)
        lwsp = i_type_expr(lwsp_imm, sp, Const(2, 3), rd, load_opc)
        fldsp = i_type_expr(ldsp_imm, sp, Const(3, 3), rd, Const(0x07, 7))
        flwsp = (i_type_expr(lwsp_imm, sp, Const(2, 3), rd, Const(0x07, 7))
                 if cfg.XLEN == 32 else ldsp)
        sdsp = s_type_expr(sdsp_imm, rs2, sp, Const(3, 3), Const(0x23, 7))
        swsp = s_type_expr(swsp_imm, rs2, sp, Const(2, 3), Const(0x23, 7))
        fsdsp = s_type_expr(sdsp_imm, rs2, sp, Const(3, 3), Const(0x27, 7))
        fswsp = (s_type_expr(swsp_imm, rs2, sp, Const(2, 3), Const(0x27, 7))
                 if cfg.XLEN == 32 else sdsp)
        mv = fit_width(cat_high(rs2, Const(0, 3), rd,
                                Const(0x13 if cfg.useAddiForMv else 0x33, 7)), 32)
        add = fit_width(cat_high(rs2, rd, Const(0, 3), rd, Const(0x33, 7)), 32)
        jr = fit_width(cat_high(rs2, rd, Const(0, 3), x0, Const(0x67, 7)), 32)
        reserved = fit_width(cat_high(jr[7:32], Const(0x1F, 7)), 32)
        jr_reserved = Mux(rd.any(), jr, reserved)
        jr_mv = Mux(rs2.any(), mv, jr_reserved)
        jalr = fit_width(cat_high(rs2, rd, Const(0, 3), ra, Const(0x67, 7)), 32)
        ebreak = (jr >> 7) | Const(0x73 | (1 << 20), 32)
        jalr_ebreak = Mux(rd.any(), jalr, ebreak)
        jalr_add = Mux(rs2.any(), add, jalr_ebreak)
        jalr_expr = Mux(field_expr(x, 12), jalr_add, jr_mv)
        q2_bits = [slli, fldsp, lwsp, flwsp, jalr_expr, fsdsp, swsp, fswsp]
        jalr_meta = (Mux(field_expr(x, 12), Mux(rs2.any(), rd, ra),
                         Mux(rs2.any(), rd, x0)),
                     Mux(field_expr(x, 12), rd, Mux(rs2.any(), rs2, rd)),
                     Mux(field_expr(x, 12), rs2, Mux(rs2.any(), x0, rs2)))
        q2_meta = [(rd, rd, rs2), (rd, sp, rs2), (rd, sp, rs2),
                   (rd, sp, rs2), jalr_meta, (rd, sp, rs2),
                   (rd, sp, rs2), (rd, sp, rs2)]
        q2_ill = [Const(0),
                  Const(1) if cfg.XLEN != 128 and cfg.fLen < 64 else (self.fsIsOff if cfg.XLEN != 128 else Const(0)),
                  rd == x0,
                  (rd == x0) if cfg.XLEN >= 64 else (Const(1) if cfg.fLen < 32 else self.fsIsOff),
                  ~field_expr(x, 12, 2).any(),
                  Const(1) if cfg.XLEN != 128 and cfg.fLen < 64 else (self.fsIsOff if cfg.XLEN != 128 else Const(0)),
                  Const(0),
                  Const(1) if cfg.XLEN < 64 and cfg.fLen < 32 else self.fsIsOff if cfg.XLEN < 64 else Const(0)]

        funct3 = field_expr(x, 15, 13)
        q0_selected = select_expr(funct3, q0_bits)
        q1_selected = select_expr(funct3, q1_bits)
        q2_selected = select_expr(funct3, q2_bits)
        q0_meta_selected = [select_expr(funct3, [meta[0] for meta in q0_meta]),
                            select_expr(funct3, [meta[1] for meta in q0_meta]),
                            select_expr(funct3, [meta[2] for meta in q0_meta])]
        q1_meta_selected = [select_expr(funct3, [meta[0] for meta in q1_meta]),
                            select_expr(funct3, [meta[1] for meta in q1_meta]),
                            select_expr(funct3, [meta[2] for meta in q1_meta])]
        q2_meta_selected = [select_expr(funct3, [meta[0] for meta in q2_meta]),
                            select_expr(funct3, [meta[1] for meta in q2_meta]),
                            select_expr(funct3, [meta[2] for meta in q2_meta])]
        q0_ill_selected = select_expr(funct3, q0_ill)
        q1_ill_selected = select_expr(funct3, q1_ill)
        q2_ill_selected = select_expr(funct3, q2_ill)
        quadrant = field_expr(x, 1, 0)
        compressed_bits = Mux(quadrant == Const(0, 2), q0_selected,
                              Mux(quadrant == Const(1, 2), q1_selected, q2_selected))
        compressed_rd = Mux(quadrant == Const(0, 2), q0_meta_selected[0],
                            Mux(quadrant == Const(1, 2), q1_meta_selected[0], q2_meta_selected[0]))
        compressed_rs1 = Mux(quadrant == Const(0, 2), q0_meta_selected[1],
                             Mux(quadrant == Const(1, 2), q1_meta_selected[1], q2_meta_selected[1]))
        compressed_rs2 = Mux(quadrant == Const(0, 2), q0_meta_selected[2],
                             Mux(quadrant == Const(1, 2), q1_meta_selected[2], q2_meta_selected[2]))
        compressed_ill = Mux(quadrant == Const(0, 2), q0_ill_selected,
                             Mux(quadrant == Const(1, 2), q1_ill_selected, q2_ill_selected))
        is_compressed = (field_expr(x, 1, 0) != Const(3, 2))
        if cfg.HasCExtension:
            module.d.comb += [
                self.out_bits.eq(Mux(is_compressed, compressed_bits, x)),
                self.out_rd.eq(Mux(is_compressed, compressed_rd, field_expr(x, 11, 7))),
                self.out_rs1.eq(Mux(is_compressed, compressed_rs1, field_expr(x, 19, 15))),
                self.out_rs2.eq(Mux(is_compressed, compressed_rs2, field_expr(x, 24, 20))),
                self.out_rs3.eq(field_expr(x, 31, 27)),
                self.ill.eq(Mux(is_compressed, compressed_ill, Const(0))),
            ]
        else:
            module.d.comb += [
                self.out_bits.eq(x), self.out_rd.eq(field_expr(x, 11, 7)),
                self.out_rs1.eq(field_expr(x, 19, 15)), self.out_rs2.eq(field_expr(x, 24, 20)),
                self.out_rs3.eq(field_expr(x, 31, 27)), self.ill.eq(0),
            ]
        return module


# =============================================================================
# Public Adapter
# =============================================================================
# Emit deterministic RTL with the extracted RVCExpander port names. / 输出带提取端口名的确定性 RTL。
def build_verilog(configuration: RvcExpanderConfig | None = None,
                  injected_dependencies: dict[str, Any] | None = None) -> str:
    del injected_dependencies
    top = RvcExpander(configuration)
    return verilog.convert(top, name="RVCExpander", ports=[top.in_, top.fsIsOff,
                        top.out_bits, top.out_rd, top.out_rs1, top.out_rs2,
                        top.out_rs3, top.ill], emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print generated RVCExpander RTL. / 打印生成的 RVCExpander RTL。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
