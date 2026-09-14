"""V2 integer ALU data path translated from XiangShan Alu.scala.
从香山 Alu.scala 转译的 V2 整数 ALU 数据通路。
"""

from __future__ import annotations

from dataclasses import dataclass

from amaranth import Cat, Const, Elaboratable, Module, Mux, Signal


# =============================================================================
# Module Contract
# =============================================================================
# The module preserves the 64-bit src0/src1, nine-bit FuOpType, and result
# boundary.  Internal helper blocks are algebraically represented in one RTL.
# 模块保留 64 位源操作数、九位 FuOpType 与结果边界，内部辅助块以等价 RTL 表达。
__all__ = [
    "ALU_OPCODES",
    "AluConfig",
    "AluDataModule",
    "alu_reference",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
ALU_OPCODES = {
    "slliuw": 0x00, "sll": 0x01, "bclr": 0x02, "bset": 0x03,
    "binv": 0x04, "srl": 0x05, "bext": 0x06, "sra": 0x07,
    "rol": 0x09, "ror": 0x0B,
    "addw": 0x10, "oddaddw": 0x11, "subw": 0x12, "lui32addw": 0x13,
    "addwbit": 0x14, "addwbyte": 0x15, "addwzexth": 0x16,
    "addwsexth": 0x17, "sllw": 0x18, "srlw": 0x19, "sraw": 0x1A,
    "rolw": 0x1C, "rorw": 0x1D,
    "adduw": 0x20, "add": 0x21, "oddadd": 0x22, "lui32add": 0x23,
    "sr29add": 0x24, "sr30add": 0x25, "sr31add": 0x26, "sr32add": 0x27,
    "sh1adduw": 0x28, "sh1add": 0x29, "sh2adduw": 0x2A, "sh2add": 0x2B,
    "sh3adduw": 0x2C, "sh3add": 0x2D, "sh4add": 0x2F,
    "sub": 0x30, "sltu": 0x31, "slt": 0x32, "maxu": 0x34,
    "minu": 0x35, "max": 0x36, "min": 0x37,
    "and": 0x40, "andn": 0x41, "or": 0x42, "orn": 0x43,
    "xor": 0x44, "xnor": 0x45, "orcb": 0x46,
    "sextb": 0x48, "packh": 0x49, "sexth": 0x4A, "packw": 0x4B,
    "revb": 0x50, "rev8": 0x51, "pack": 0x52, "orh48": 0x53,
    "szewl1": 0x58, "szewl2": 0x59, "szewl3": 0x5A, "byte2": 0x5B,
    "andlsb": 0x60, "andzexth": 0x61, "orlsb": 0x62, "orzexth": 0x63,
    "xorlsb": 0x64, "xorzexth": 0x65, "orcblsb": 0x66, "orcbzexth": 0x67,
    "czero_eqz": 0x74, "czero_nez": 0x76,
}


@dataclass(frozen=True)
class AluConfig:
    """V2 ALU width configuration. / V2 ALU 位宽配置。"""

    xlen: int = 64

    # Validate the pinned Kunminghu V2 integer width. / 校验锁定昆明湖 V2 整数位宽。
    def __post_init__(self) -> None:
        if self.xlen != 64:
            raise ValueError("the locked Kunminghu V2 ALU is RV64")


# =============================================================================
# Implementation
# =============================================================================
# Replicate a one-bit expression. / 复制一个单比特表达式。
def replicate(bit, count: int):
    """Return ``count`` copies of one bit. / 返回一个比特的 ``count`` 份复制。"""

    return Cat(*[bit for _ in range(count)]) if count else Const(0, 1)


# Sign-extend an Amaranth value. / 对 Amaranth 值进行符号扩展。
def sign_extend(value, width: int):
    """Return a value with the requested width. / 返回指定宽度的值。"""

    current = len(value)
    if current >= width:
        return value[:width]
    return Cat(value, replicate(value[current - 1], width - current))


# Zero-extend an Amaranth value. / 对 Amaranth 值进行零扩展。
def zero_extend(value, width: int):
    """Return a zero-extended value. / 返回零扩展值。"""

    current = len(value)
    if current >= width:
        return value[:width]
    return Cat(value, Const(0, width - current))


# Rotate left using the V2 dynamic-shift equations. / 使用 V2 动态移位方程循环左移。
def rotate_left(value, amount, width: int):
    """Return a width-bit rotate-left result. / 返回指定宽度的循环左移结果。"""

    amount_width = max(1, (width + 1).bit_length())
    complement = (Const(width, amount_width) - amount).as_unsigned()
    return ((value << amount) | (value >> complement))[:width]


# Rotate right using the V2 dynamic-shift equations. / 使用 V2 动态移位方程循环右移。
def rotate_right(value, amount, width: int):
    """Return a width-bit rotate-right result. / 返回指定宽度的循环右移结果。"""

    amount_width = max(1, (width + 1).bit_length())
    complement = (Const(width, amount_width) - amount).as_unsigned()
    return ((value >> amount) | (value << complement))[:width]


# Reverse every bit in each byte. / 反转每个字节中的全部比特。
def reverse_bytes_bits(value, width: int):
    """Return byte-local bit reversal. / 返回按字节的比特反转结果。"""

    byte_count = width // 8
    bytes_out = []
    for byte_index in range(byte_count):
        byte = value[byte_index * 8:(byte_index + 1) * 8]
        bits = [byte[7 - bit] for bit in range(8)]
        bytes_out.append(Cat(*bits))
    return Cat(*bytes_out)


# Compute a pure integer ALU result for the differential oracle. / 计算纯整数 ALU 结果作为差分预言机。
def alu_reference(src0: int, src1: int, func: int, xlen: int = 64) -> int:
    """Model the V2 AluDataModule with finite-width integer arithmetic.
    使用有限宽整数运算建模 V2 AluDataModule。
    """

    mask = (1 << xlen) - 1
    src0 &= mask
    src1 &= mask
    func &= 0x1FF
    shamt = src1 & 0x3F
    shamt5 = src1 & 0x1F
    signed = lambda value, bits: value - (1 << bits) if value & (1 << (bits - 1)) else value
    sext = lambda value, bits: signed(value & ((1 << bits) - 1), bits) & mask
    zext = lambda value, bits: value & ((1 << bits) - 1)
    low32 = src0 & 0xFFFFFFFF
    src1_low32 = src1 & 0xFFFFFFFF
    # Shift family. / 移位族。
    sll_src = src0 if (func & 1) else low32
    sll = (sll_src << shamt) & mask
    bit_shift = (1 << shamt) & mask
    srl = src0 >> shamt
    sra = (signed(src0, xlen) >> shamt) & mask
    rol = ((src0 << shamt) | (src0 >> ((xlen - shamt) & (xlen - 1)))) & mask
    ror = ((src0 >> shamt) | (src0 << ((xlen - shamt) & (xlen - 1)))) & mask
    # Widen/add family. / 字宽与加法族。
    f3, f2, f1, f0 = (func >> 3) & 1, (func >> 2) & 1, (func >> 1) & 1, func & 1
    word_mask = src0 if f0 else low32
    odd_src = src0 & 1
    lui_src1 = sext(src1 & 0xFFF, 12)
    lui_src2 = src1 & ~0xFFF
    addw_src1 = src0 if ((not f3 and not f2 and not f0) or f2) else (odd_src if (not f3 and not f2 and f0 and not f1) else lui_src1)
    # The explicit source predicates are clearer for the four low opcodes.
    if (func >> 4) & 0x7 == 1 and (func & 0xF) == 1:
        addw_src1 = odd_src
    elif (func >> 4) & 0x7 == 1 and (func & 0xF) == 3:
        addw_src1 = lui_src1
    elif (func >> 4) & 0x7 == 1:
        addw_src1 = src0
    addw_src2 = lui_src2 if (func & 0xF) == 3 else src1
    addw_half = (addw_src1 + addw_src2) & 0xFFFFFFFF
    addw_all = [addw_half & 1, addw_half & 0xFF, addw_half & 0xFFFF, sext(addw_half, 16)]
    addw = addw_all[(func >> 1) & 3] if f2 else sext(addw_half, 32)
    sub_full = (src0 - src1) & ((1 << (xlen + 1)) - 1)
    subw = sub_full & 0xFFFFFFFF
    sllw = (low32 << shamt5) & 0xFFFFFFFF
    srlw = low32 >> shamt5
    sraw = (signed(low32, 32) >> shamt5) & 0xFFFFFFFF
    rolw32 = ((low32 << shamt5) | (low32 >> ((32 - shamt5) & 31))) & 0xFFFFFFFF
    rorw32 = ((low32 >> shamt5) | (low32 << ((32 - shamt5) & 31))) & 0xFFFFFFFF
    # Add-op family. / 加法操作族。
    add_src1 = word_mask
    if f1:
        add_src1 = sext(src1 & 0xFFF, 12) if f0 else odd_src
    if f2:
        sr_sources = [src0 >> 29, src0 >> 30, src0 >> 31, src0 >> 32]
        add_src1 = sr_sources[func & 3] if not f3 else add_src1
    if f3:
        shmask = src0 if f0 else low32
        add_src1 = (shmask << (1 << ((func >> 1) & 3))) & mask
    add_src2 = lui_src2 if (func & 0xF) == 3 else src1
    add = (add_src1 + add_src2) & mask
    sradd = (add_src1 + src1) & mask
    shadd = (add_src1 + src1) & mask
    # Comparison family. / 比较族。
    sub_signed = signed(src0, xlen) - signed(src1, xlen)
    sltu = 1 if src0 >= src1 else 0
    slt = 1 if signed(src0, xlen) < signed(src1, xlen) else 0
    maxmin = src1 if (slt ^ f0) else src0
    maxminu = src1 if (sltu ^ f0) else src0
    compare = sub_full & mask
    if f2:
        compare = maxmin if f1 else maxminu
    elif f1:
        compare = slt
    elif f0:
        compare = sltu
    # Misc family. / 杂项族。
    logic_src1 = src1 ^ (mask if ((not ((func >> 5) & 1)) and f0) else 0)
    and_v, or_v, xor_v = src0 & logic_src1, src0 | logic_src1, src0 ^ logic_src1
    orcb = 0
    for index in range(8):
        byte = (src0 >> (index * 8)) & 0xFF
        orcb |= (0xFF if byte else 0) << (index * 8)
    orh48 = (src0 & ~0xFF) | src1
    sextb = sext(src0, 8)
    packh = ((src1 & 0xFF) << 8) | (src0 & 0xFF)
    sexth = sext(src0, 16)
    packw = sext(((src1 & 0xFFFF) << 16) | (src0 & 0xFFFF), 32)
    revb = 0
    for index in range(8):
        byte = (src0 >> (index * 8)) & 0xFF
        revb |= int(f"{byte:08b}"[::-1], 2) << (index * 8)
    rev8 = int.from_bytes(src0.to_bytes(8, "little"), "big")
    pack = ((src1 & 0xFFFFFFFF) << 32) | (src0 & 0xFFFFFFFF)
    logic_vec = [and_v, or_v, xor_v, orcb]
    pair_vec = [sextb, packh, sexth, packw]
    rev_vec = [revb, rev8, pack, orh48]
    custom_vec = [(src0 & 0xFFFFFFFF) << 1, (src0 & 0xFFFFFFFF) << 2,
                  (src0 & 0xFFFFFFFF) << 3, (src0 >> 8) & 0xFF]
    misc_logic = logic_vec[(func >> 1) & 3]
    misc = pair_vec[func & 3] if f3 else misc_logic
    if (func >> 4) & 1:
        misc = custom_vec[func & 3] if f3 else rev_vec[func & 3]
    if (func >> 5) & 1:
        misc = (misc_logic & (0xFFFF if f0 else 1)) & 0xFFFF
    # Final AluResSel group. / 最终 AluResSel 分组选择。
    group = (func >> 4) & 7
    if group == 0:
        result = sll if not f3 else (sllw if not f0 else 0)
        if f3:
            result = rolw32 if (f2 and not f0) else (rorw32 if (f2 and f0) else (sraw if f1 else (srlw if f0 else sllw)))
            result = sext(result, 32)
        elif f0:
            result = sll
    elif group == 1:
        result = sext(addw_half, 32)
        if f2:
            result = addw
        elif f3:
            result = sext(rolw32 if not f0 else rorw32, 32)
        elif f2:
            result = sext(subw, 32)
    elif group == 2:
        result = shadd if f3 else (sradd if f2 else add)
    elif group == 3:
        result = compare
    elif group in (4, 5, 6):
        result = misc
    elif group == 7:
        condition_zero = src1 == 0
        result = 0 if ((not f1 and condition_zero) or (f1 and not condition_zero)) else src0
    else:
        result = 0
    # Exact named word cases override the compact group expression.
    # 精确命名字宽操作覆盖紧凑分组表达式。
    if func == ALU_OPCODES["subw"]:
        result = sext(subw, 32)
    elif func == ALU_OPCODES["sllw"]:
        result = sext(sllw, 32)
    elif func == ALU_OPCODES["srlw"]:
        result = sext(srlw, 32)
    elif func == ALU_OPCODES["sraw"]:
        result = sext(sraw, 32)
    elif func == ALU_OPCODES["rolw"]:
        result = sext(rolw32, 32)
    elif func == ALU_OPCODES["rorw"]:
        result = sext(rorw32, 32)
    return result & mask


class AluDataModule(Elaboratable):
    """Combinational V2 ALU datapath. / V2 组合 ALU 数据通路。"""

    # Construct the source, operation, and result ports. / 构造源操作数、操作码与结果端口。
    def __init__(self, configuration: AluConfig = AluConfig()) -> None:
        self.configuration = configuration
        self.src = [Signal(configuration.xlen, name=f"io_src_{index}") for index in range(2)]
        self.func = Signal(9, name="io_func")
        self.result = Signal(configuration.xlen, name="io_result")

    # Elaborate the V2 ALU equations and result-group mux. / 展开 V2 ALU 方程及结果分组多路器。
    def elaborate(self, platform) -> Module:
        del platform
        m = Module()
        width = self.configuration.xlen
        src0, src1 = self.src
        func = self.func
        half = width // 2
        shamt = src1[:6]
        shamt5 = src1[:5]
        f0, f1, f2, f3 = func[0], func[1], func[2], func[3]
        group = func[4:7]
        low32 = src0[:32]

        # Primitive shift and add sources. / 基础移位与加法源。
        sll_src = Mux(f0, src0, zero_extend(low32, width))
        sll = (sll_src << shamt)[:width]
        bit_shift = (Const(1, width) << shamt)[:width]
        srl = src0 >> shamt
        sra = (src0.as_signed() >> shamt.as_unsigned())[:width]
        bext = srl[:1]
        rol = rotate_left(src0, shamt, width)
        ror = rotate_right(src0, shamt, width)
        bclr, bset, binv = src0 & ~bit_shift, src0 | bit_shift, src0 ^ bit_shift

        # Widen/word arithmetic. / 字宽与扩展算术。
        odd_src = zero_extend(src0[:1], width)
        lui_src1 = sign_extend(src1[:12], width)
        lui_src2 = Cat(Const(0, 12), src1[12:width])
        word_mask = Mux(f0, src0, zero_extend(low32, width))
        addw_src1 = Mux(
            ((~f3 & ~f2 & ~f0) | f2),
            src0,
            Mux((group == 1) & (func[:4] == 1), odd_src, lui_src1),
        )
        addw_src1 = Mux((group == 1) & (func[:4] == 3), lui_src1, addw_src1)
        addw_src2 = Mux(func[:4] == 3, lui_src2, src1)
        addw_half = (addw_src1[:32] + addw_src2[:32])[:32]
        addw_all = [zero_extend(addw_half[:1], width), zero_extend(addw_half[:8], width),
                    zero_extend(addw_half[:16], width), sign_extend(addw_half[:16], width)]
        addw_sel = Mux(func[1], Mux(func[0], addw_all[3], addw_all[2]),
                       Mux(func[0], addw_all[1], addw_all[0]))
        addw = Mux(f2, addw_sel, sign_extend(addw_half, width))
        # Chisel's ``+& (~b) + 1`` retains the carry bit used by SLTU.
        # Chisel 的 ``+& (~b) + 1`` 保留 SLTU 使用的进位位。
        sub_full = (Cat(src0, Const(0, 1)) + Cat(~src1, Const(0, 1)) + 1)[:width + 1]
        subw = sub_full[:32]
        sllw = (low32 << shamt5)[:32]
        srlw = low32 >> shamt5
        sraw = (low32.as_signed() >> shamt5.as_unsigned())[:32]
        rolw = rotate_left(low32, shamt5, 32)
        rorw = rotate_right(low32, shamt5, 32)

        # Add-op sources and results. / 加法操作源与结果。
        sr_sources = [zero_extend(src0[29:64], width), zero_extend(src0[30:64], width),
                      zero_extend(src0[31:64], width), zero_extend(src0[32:64], width)]
        sradd_src = Mux(func[:2] == 0, sr_sources[0],
                        Mux(func[:2] == 1, sr_sources[1],
                            Mux(func[:2] == 2, sr_sources[2], sr_sources[3])))
        shmask = Mux(f0, src0, zero_extend(low32, width))
        shadd_src = Mux(func[1:3] == 0, (shmask << 1)[:width],
                        Mux(func[1:3] == 1, (shmask << 2)[:width],
                            Mux(func[1:3] == 2, (shmask << 3)[:width], (shmask << 4)[:width])))
        add_src = Mux(f3, shadd_src,
                      Mux(f2, sradd_src,
                          Mux(f1, Mux(f0, lui_src1, odd_src), word_mask)))
        add_src2 = Mux(func[:4] == 3, lui_src2, src1)
        add_result = (add_src + add_src2)[:width]
        sradd_result = (sradd_src + src1)[:width]
        shadd_result = (shadd_src + src1)[:width]

        # Compare and min/max results. / 比较及最小最大结果。
        sltu = ~sub_full[width]
        slt = src0[width - 1] ^ src1[width - 1] ^ sltu
        max_min = Mux(slt ^ f0, src1, src0)
        max_min_u = Mux(sltu ^ f0, src1, src0)
        compare = Mux(f2, Mux(f1, max_min, max_min_u),
                      Mux(f1, zero_extend(slt, width), Mux(f0, zero_extend(sltu, width), sub_full[:width])))

        # Miscellaneous bit-manipulation results. / 杂项位操作结果。
        logic_src2 = Mux(~func[5] & f0, ~src1, src1)
        and_v, or_v, xor_v = src0 & logic_src2, src0 | logic_src2, src0 ^ logic_src2
        orcb_bytes = []
        for index in range(8):
            byte = src0[index * 8:(index + 1) * 8]
            any_bit = byte[0]
            for bit_index in range(1, 8):
                any_bit = any_bit | byte[bit_index]
            orcb_bytes.append(replicate(any_bit, 8))
        orcb = Cat(*orcb_bytes)
        orh48 = Cat(Const(0, 8), src0[8:64]) | src1
        sextb = sign_extend(src0[:8], width)
        packh = Cat(src0[:8], src1[:8], Const(0, 48))
        sexth = sign_extend(src0[:16], width)
        packw = sign_extend(Cat(src0[:16], src1[:16]), width)
        revb = reverse_bytes_bits(src0, width)
        rev8 = Cat(*[src0[index * 8:(index + 1) * 8] for index in reversed(range(8))])
        pack = Cat(src0[:32], src1[:32])
        misc_logic = Mux(func[1:3] == 0, and_v,
                          Mux(func[1:3] == 1, or_v,
                              Mux(func[1:3] == 2, xor_v, orcb)))
        misc_pair = Mux(func[:2] == 0, sextb,
                        Mux(func[:2] == 1, packh,
                            Mux(func[:2] == 2, sexth, packw)))
        rev_pair = Mux(func[:2] == 0, revb,
                       Mux(func[:2] == 1, rev8,
                           Mux(func[:2] == 2, pack, orh48)))
        custom_pair = Mux(func[:2] == 0, Cat(src0[:32], Const(0, 32)) << 1,
                          Mux(func[:2] == 1, Cat(src0[:32], Const(0, 32)) << 2,
                              Mux(func[:2] == 2, Cat(src0[:32], Const(0, 32)) << 3,
                                  zero_extend(src0[8:16], width))))
        misc = Mux(func[5], zero_extend(misc_logic[:16] & Mux(f0, Const(0xFFFF, 16), Const(1, 16)), width),
                   Mux(func[4], Mux(f3, custom_pair[:width], rev_pair),
                       Mux(f3, misc_pair, misc_logic)))
        cond_result = Mux((~f1 & (src1 == 0)) | (f1 & (src1 != 0)), Const(0, width), src0)

        # Final group mux mirrors AluResSel.scala. / 最终分组多路器镜像 AluResSel.scala。
        simple_shift = Mux(func[:3] == 0, sll,
                           Mux(func[:3] == 1, sll,
                               Mux(func[:3] == 2, bclr,
                                   Mux(func[:3] == 3, bset,
                                       Mux(func[:3] == 4, binv,
                                           Mux(func[:3] == 5, srl,
                                               Mux(func[:3] == 6, zero_extend(bext, width), sra)))))))
        shift_result = Mux(f3, Mux(f1, ror, rol), simple_shift)
        word_result = Mux(f3,
                          Mux(f2, Mux(f0, rorw, rolw), Mux(f1, sraw, Mux(f0, srlw, sllw))),
                          Mux((~f2 & f1 & ~f0), subw, addw))
        word_result = sign_extend(word_result[:32], width)
        result = Mux(group[1:3] == 0,
                     Mux(group[0], word_result, shift_result),
                     Mux(group[2],
                         Mux(group[1] & group[0], cond_result, misc),
                         Mux(group[0], compare, add_result)))
        m.d.comb += self.result.eq(result)
        return m


# =============================================================================
# Public Adapter
# =============================================================================
# Emit deterministic V2 ALU Verilog. / 输出确定性的 V2 ALU Verilog。
def build_verilog(configuration=None, injected_dependencies=None) -> str:
    """Build the standalone AluDataModule. / 构建独立 AluDataModule。"""

    del injected_dependencies
    from amaranth.back import verilog

    top = AluDataModule(configuration or AluConfig())
    return verilog.convert(top, name="AluDataModule", ports=[*top.src, top.func, top.result], emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print generated ALU RTL. / 打印生成的 ALU RTL。
def main() -> None:
    """Print deterministic Verilog. / 打印确定性 Verilog。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
