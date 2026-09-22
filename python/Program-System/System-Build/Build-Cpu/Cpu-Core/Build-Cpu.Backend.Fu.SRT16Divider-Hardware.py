"""SRT16Divider (radix-4 SRT divide data module with 7-state FSM). / SRT16 除法器（基 4 SRT 除法数据模块，7 状态机）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from amaranth import Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal


# =============================================================================
# Module Contract
# =============================================================================
# Public symbols / 公开符号:
#   - SRT16DividerConfig, SRT16DividerDataModule, RightShifter
#   - mLookUpTable2 : SRT -m selection tables (4×8)
#   - build_verilog, main
# Real logic: faithful port of SRT16DividerDataModule. 7-state one-hot FSM
# (idle→pre_0→pre_1→iter→post_0→post_1→finish), LZC normalization, SRT radix-4
# digit selection via -m lookup tables + CSA3_2 compressors + DetectSign,
# speculative qNext2, on-the-fly quotient conversion (OTFC), remainder
# correction + RightShifter, special-case handling (d=1/-1/0, a too small).
# CSA3_2(len) = 3:2 carry-save adder (full adder per bit). The leading-zero
# counter scans from the most-significant bit. The finite m tables are used by
# the quotient-selection equations below.
# / 真实逻辑：SRT16DividerDataModule 的忠实移植。7 状态独热机（idle→pre_0→
# pre_1→iter→post_0→post_1→finish）、LZC 归一化、SRT 基 4 数位选择（-m 查表
# +CSA3_2 压缩器+DetectSign）、推测 qNext2、商即时转换 OTFC、余数修正+
# RightShifter、特殊情形处理（d=1/-1/0、a 过小）。CSA3_2(len) 为 3:2 进位
# 保存加法器（逐位全加器）。PriorityEncoder 反位序优先编码。m 表原样镜像。
# Status / 状态: STRICT_PENDING
__all__ = ["COVERED_MODULES", "SRT16DividerConfig", "SRT16DividerDataModule",
           "SRT16DividerReferenceAdapter", "RightShifter", "mLookUpTable2",
           "build_verilog", "main"]

COVERED_MODULES: tuple[str, ...] = ("SRT16DividerDataModule",)


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class SRT16DividerConfig:
    len: int = 64

    def __post_init__(self) -> None:
        if self.len not in (32, 64):
            raise ValueError("SRT16Divider V2 supports len=32 or len=64")


# =============================================================================
# Implementation
# =============================================================================
def csa3_2(a: Any, b: Any, cin: Any, w: int) -> tuple[Any, Any]:
    # 3:2 carry-save adder (full adder per bit) / 3:2 进位保存加法器
    axb = a ^ b
    s = axb ^ cin
    c = (a & b) | (axb & cin)
    return (s.bit_select(0, w), c.bit_select(0, w))


# Find the first asserted bit from the MSB side / 从最高位侧查找首个置位位
def priority_encoder(bits: Any, w: int) -> Any:
    """Return the first asserted bit when scanning MSB to LSB.

    The encoded result is the leading-zero count, including ``w`` for an
    all-zero input. Later matches must not overwrite the first match.
    """

    count_width = max(1, w.bit_length())
    result: Any = Const(w, count_width)
    found: Any = Const(0, 1)
    for index in range(w):
        bit = bits.bit_select(w - index - 1, 1)
        first = cast(Any, Mux(found, Const(0, 1), Const(1, 1))) & bit
        result = Mux(first, Const(index, count_width), result)
        found = cast(Any, found) | bit
    return result


# Sign extend an expression to a target width / 将表达式符号扩展到目标位宽
def sign_ext(v: Any, vw: int, tw: int) -> Any:
    if tw <= vw:
        return v.bit_select(0, tw)
    s = v.bit_select(vw - 1, 1)
    return Cat(v, *[s for _ in range(tw - vw)])


# Select a constant from an indexed lookup table / 按索引从常量查找表选择
def mux_lookup(idx: Any, default: int,
               table: list[tuple[int, int]], w: int) -> Any:
    # MuxLookup(idx, default)(table) / 查表
    res = Const(default, w)
    for k, v in table:
        res = Mux(idx == k, Const(v, w), res)
    return res


# Multiplex values under one-hot selectors / 在独热选择信号下复用值
def mux1h(sels: Any, vals: list[Any]) -> Any:
    # Mux1H over one-hot selectors / 独热选择
    res = vals[0] & Cat(*[sels[0] for _ in range(vals[0].shape().width)]) \
        if False else (vals[0] & replicate(sels[0], vals[0].shape().width))
    for i in range(1, len(sels)):
        res = res | (vals[i] & replicate(sels[i], vals[i].shape().width))
    return res


# Replicate a one-bit expression / 复制单比特表达式
def replicate(bit: Any, w: int) -> Any:
    return Cat(*[bit for _ in range(w)])


def _data_register(width: int = 1, *, name: str) -> Signal:
    """Create a data register without an implicit asynchronous reset.

    The locked divider resets only its one-hot state machine.  All datapath
    registers are written by the ordinary clocked process and therefore must
    not acquire a reset branch merely because the Amaranth clock domain uses
    an asynchronous reset for the state register.
    """

    return Signal(width, name=name, reset_less=True)


class mLookUpTable2:
    # SRT -m selection tables (4 sets × 8 entries) / SRT -m 选择表
    minus_m = [
        # -m[-1] / 索引 0
        [(0, 0b00_11010), (1, 0b00_11110), (2, 0b01_00000), (3, 0b01_00100),
         (4, 0b01_00110), (5, 0b01_01010), (6, 0b01_01100), (7, 0b01_10000)],
        # -m[0] / 索引 1
        [(0, 0b000_0100), (1, 0b000_0110), (2, 0b000_0110), (3, 0b000_0110),
         (4, 0b000_1000), (5, 0b000_1000), (6, 0b000_1000), (7, 0b000_1000)],
        # -m[1] / 索引 2
        [(0, 0b111_1101), (1, 0b111_1100), (2, 0b111_1100), (3, 0b111_1100),
         (4, 0b111_1011), (5, 0b111_1010), (6, 0b111_1010), (7, 0b111_1010)],
        # -m[2] / 索引 3
        [(0, 0b11_01000), (1, 0b11_00100), (2, 0b11_00010), (3, 0b10_11110),
         (4, 0b10_11100), (5, 0b10_11000), (6, 0b10_10110), (7, 0b10_10010)],
    ]


class RightShifter(Elaboratable):
    # barrel right shifter with msb fill / 带 msb 填充的桶形右移
    def __init__(self, length: int, lzc_width: int) -> None:
        self.length = length
        self.lzc_width = lzc_width
        self.shiftNum = Signal(lzc_width, name="rs_shiftNum")
        self.in_ = Signal(length, name="rs_in")
        self.msb = Signal(name="rs_msb")
        self.out = Signal(length, name="rs_out")

    # Elaborate the right-shifter combinational network / 展开右移器组合网络
    def elaborate(self, platform: Any) -> Any:
        m: Any = Module()
        length = self.length
        shift = self.shiftNum
        msb = self.msb
        s = self.in_
        for bit in range(min(self.lzc_width, 6)):
            amt = 1 << bit
            if amt >= length:
                break
            padded = Cat(s.bit_select(amt, length - amt),
                         *[msb for _ in range(amt)])
            s = Mux(shift.bit_select(bit, 1), padded, s)
        m.d.comb += self.out.eq(s)
        return m


class SRT16DividerDataModule(Elaboratable):
    # radix-4 SRT divider / 基 4 SRT 除法器
    def __init__(self, config: SRT16DividerConfig | int | None = None,
                 *, len: int | None = None):
        if len is not None:
            if config is not None:
                raise TypeError("provide config or len, not both")
            config = len
        if config is None:
            config = SRT16DividerConfig()
        elif isinstance(config, int):
            config = SRT16DividerConfig(config)
        self.config = config
        c = config
        ln = c.len
        # Keep exact locked-reference port names at the public boundary.
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.io_src_0 = Signal(ln, name="io_src_0")
        self.io_src_1 = Signal(ln, name="io_src_1")
        self.io_valid = Signal(name="io_valid")
        self.io_sign = Signal(name="io_sign")
        self.io_kill_w = Signal(name="io_kill_w")
        self.io_kill_r = Signal(name="io_kill_r")
        self.io_isHi = Signal(name="io_isHi")
        self.io_isW = Signal(name="io_isW")
        self.io_in_ready = Signal(name="io_in_ready")
        self.io_out_valid = Signal(name="io_out_valid")
        self.io_out_data = Signal(ln, name="io_out_data")
        self.io_out_ready = Signal(name="io_out_ready")
        self.outValidAhead3Cycle = Signal(name="outValidAhead3Cycle")
        self.io_outValidAhead3Cycle = self.outValidAhead3Cycle
        # Source-style aliases used by parent adapters.
        self.src = [self.io_src_0, self.io_src_1]
        self.valid = self.io_valid
        self.sign = self.io_sign
        self.kill_w = self.io_kill_w
        self.kill_r = self.io_kill_r
        self.isHi = self.io_isHi
        self.isW = self.io_isW
        self.in_ready = self.io_in_ready
        self.out_valid = self.io_out_valid
        self.out_data = self.io_out_data
        self.out_ready = self.io_out_ready
        self.out_validNext = Signal(name="out_validNext")

    # Elaborate the iterative SRT divider datapath / 展开迭代式 SRT 除法数据通路
    def elaborate(self, platform: Any) -> Any:
        m: Any = Module()
        domain = ClockDomain("sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains += domain
        c = self.config
        ln = c.len
        lzc_width = max(1, (ln - 1).bit_length())
        itn_len = 1 + ln + 2 + 1
        a, d = self.src[0], self.src[1]
        sign, valid, kill_w, kill_r, isHi, isW = (
            self.sign, self.valid, self.kill_w, self.kill_r, self.isHi, self.isW)
        in_fire = valid & self.in_ready

        # states one-hot / 状态独热
        S_IDLE, S_PRE0, S_PRE1, S_ITER, S_POST0, S_POST1, S_FINISH = range(7)
        state = Signal(7, name="state", reset=(1 << S_IDLE))

        # quotient digit OH / 商数位独热
        Q_N2, Q_N1, Q_0, Q_P1, Q_P2 = range(5)

        # regs / 寄存器
        quotIterReg = _data_register(ln, name="quotIterReg")
        quotM1IterReg = _data_register(ln, name="quotM1IterReg")
        specialReg = _data_register(name="specialReg")
        aReg = _data_register(ln, name="aReg")
        dSignReg = _data_register(name="dSignReg")
        aAbsReg = _data_register(ln, name="aAbsReg")
        dAbsReg = _data_register(ln, name="dAbsReg")
        aNormReg = _data_register(ln, name="aNormReg")
        dNormReg = _data_register(ln, name="dNormReg")
        aLZCReg = _data_register(lzc_width + 1, name="aLZCReg")
        dLZCReg = _data_register(lzc_width + 1, name="dLZCReg")
        quotSpecialReg = _data_register(ln, name="quotSpecialReg")
        remSpecialReg = _data_register(ln, name="remSpecialReg")
        quotSignReg = _data_register(name="quotSignReg")
        rSignReg = _data_register(name="rSignReg")
        iterNumReg = _data_register(max(1, lzc_width - 2), name="iterNumReg")
        udNegReg = [_data_register(itn_len, name=f"udNegReg_{i}") for i in range(5)]
        rudPmNegReg = [[_data_register(10, name=f"rudPmNegReg_{i}_{j}") for j in range(4)]
                       for i in range(5)]
        r2udPmNegReg = [[_data_register(13, name=f"r2udPmNegReg_{i}_{j}") for j in range(4)]
                        for i in range(5)]
        qPrevReg = _data_register(5, name="qPrevReg")
        rSumReg = _data_register(itn_len, name="rSumReg")
        rCarryReg = _data_register(itn_len, name="rCarryReg")
        # The locked RTL retains the sign bit through post_0 (len+1 bits).
        rNextReg = _data_register(ln + 1, name="rNextReg")
        rNextPdReg = _data_register(ln + 1, name="rNextPdReg")
        rFinal = _data_register(ln, name="rFinal")
        qFinal = _data_register(ln, name="qFinal")
        aTooSmallStorage = _data_register(name="aTooSmall")

        # wires / 连线
        quotIter = Signal(ln, name="srt_quotIter")
        quotM1Iter = Signal(ln, name="srt_quotM1Iter")
        aLZC = Signal(lzc_width + 1, name="srt_aLZC")
        dLZC = Signal(lzc_width + 1, name="srt_dLZC")
        rNext = Signal(itn_len, name="srt_rNext")
        rNextPd = Signal(itn_len, name="srt_rNextPd")
        finalIter = Signal(name="srt_finalIter")
        special = Signal(name="srt_special")

        # aInverter/dInverter / 反相器
        aInverter = (-Mux(state.bit_select(S_IDLE, 1), a, quotIterReg)).bit_select(0, ln)
        dInverter = (-Mux(state.bit_select(S_IDLE, 1), d, quotM1IterReg)).bit_select(0, ln)
        aSign = sign & a.bit_select(ln - 1, 1)
        dSign = sign & d.bit_select(ln - 1, 1)
        aAbs = Mux(aSign, aInverter, a)
        dAbs = Mux(dSign, dInverter, d)
        # Normalization uses the combinational LZC in pre_0; the normalized
        # values are captured on that same edge.
        aNorm = barrel_lsh(aAbsReg, aLZC, ln)
        dNorm = barrel_lsh(dAbsReg, dLZC, ln)
        # LZC / 前导零检测
        m.d.comb += aLZC.eq(priority_encoder(aAbsReg, ln))
        m.d.comb += dLZC.eq(priority_encoder(dAbsReg, ln))
        lzcWireDiff = (cast(Any, Cat(dLZC.bit_select(0, lzc_width), Const(0, 1)))
                       - cast(Any, Cat(aLZC.bit_select(0, lzc_width), Const(0, 1))))
        lzcRegDiff = (cast(Any, Cat(dLZCReg.bit_select(0, lzc_width), Const(0, 1)))
                      - cast(Any, Cat(aLZCReg.bit_select(0, lzc_width), Const(0, 1))))
        # special / 特殊
        dIsOne = and_reduce(dLZC.bit_select(0, lzc_width), lzc_width)
        dIsZero = ~or_reduce(dNormReg, ln)
        aTooSmall = aTooSmallStorage
        m.d.comb += special.eq(dIsOne | dIsZero | aTooSmall)
        quotSpecial = Mux(dIsZero, Const(-1, ln),
                          Mux(aTooSmall, Const(0, ln),
                              Mux(dSignReg, (-aReg).bit_select(0, ln), aReg)))
        remSpecial = Mux(dIsZero | aTooSmall, aReg, Const(0, ln))
        # signs / 符号
        quotSign = Mux(state.bit_select(S_IDLE, 1), aSign ^ dSign, Const(1, 1))
        rSign = aSign
        rShift = lzcRegDiff.bit_select(0, 1)
        oddIter = (cast(Any, lzcRegDiff.bit_select(1, 1))
                   ^ cast(Any, lzcRegDiff.bit_select(0, 1)))
        iterNum = Signal(max(1, lzc_width - 2), name="srt_iterNum")
        iterNumNext = Mux(state.bit_select(S_PRE1, 1),
                          cast(Any, (cast(Any, lzcRegDiff) + 1)).bit_select(
                              2, max(1, lzc_width - 2)),
                          cast(Any, iterNumReg - 1).bit_select(0, max(1, lzc_width - 2)))
        m.d.comb += iterNum.eq(iterNumNext)
        m.d.comb += finalIter.eq(iterNumReg == 0)

        # init sums / 初始和
        aNormShifted = Mux(rShift, Cat(aNormReg, Const(0, 1)),
                           Cat(Const(0, 1), aNormReg))
        rSumInit = cast(Any, Cat(aNormShifted, Const(0, 3))).bit_select(0, itn_len)
        rCarryInit = Const(0, itn_len)
        rSumInitTrunc = Cat(rSumInit.bit_select(itn_len - 7, 4), Const(0, 1))
        dForLookup = dNormReg.bit_select(ln - 4, 3)
        mInitPos1 = mux_lookup(dForLookup, 0b00100,
                                [(0, 0b00100), (1, 0b00100), (2, 0b00100), (3, 0b00110),
                                 (4, 0b00110), (5, 0b00110), (6, 0b00110), (7, 0b01000)], 5)
        mInitPos2 = mux_lookup(dForLookup, 0b01100,
                                [(0, 0b01100), (1, 0b01110), (2, 0b01111), (3, 0b10000),
                                 (4, 0b10010), (5, 0b10100), (6, 0b10110), (7, 0b10110)], 5)
        initCmpPos1 = rSumInitTrunc >= mInitPos1
        initCmpPos2 = rSumInitTrunc >= mInitPos2
        qInit = Mux(initCmpPos2, uint_to_oh(Q_P2, 5),
                    Mux(initCmpPos1, uint_to_oh(Q_P1, 5), uint_to_oh(Q_0, 5)))

        # d pos/neg / d 正负
        dPos = cast(Any, Cat(dNormReg, Const(0, 1)))
        dNeg = (-cast(Any, Cat(dNormReg, Const(0, 1)))).bit_select(0, ln + 1)
        # mNeg / -m 表
        mNeg = []
        for j in range(4):
            mv = mux_lookup(dForLookup, 0, mLookUpTable2.minus_m[j], 7)
            ext_bits = [11, 10, 10, 11][j]
            pad_bits = [1, 2, 2, 1][j]
            mNeg.append(Cat(Const(0, pad_bits), sign_ext(mv, 7, ext_bits)))
        # udNeg / u*d
        udNeg = [
            Cat(Const(0, 2), sign_ext(dPos, ln + 1, itn_len - 2)),
            Cat(Const(0, 1), sign_ext(dPos, ln + 1, itn_len - 1)),
            Const(0, itn_len),
            Cat(Const(0, 1), sign_ext(dNeg, ln + 1, itn_len - 1)),
            Cat(Const(0, 2), sign_ext(dNeg, ln + 1, itn_len - 2)),
        ]
        rudNeg = [udNeg[i].bit_select(itn_len - 11, 10) for i in range(5)]
        r2udNeg = [udNeg[i].bit_select(itn_len - 13, 12) for i in range(5)]
        rudPmNeg = [[(cast(Any, sign_ext(rudNeg[i].bit_select(1, 9), 9, 10))
                      + cast(Any, mNeg[j].bit_select(1, 10))).bit_select(0, 10)
                     for j in range(4)] for i in range(5)]
        r2udPmNeg = [[(cast(Any, sign_ext(r2udNeg[i], 12, 13)) + cast(Any, sign_ext(mNeg[j], 12, 13))).bit_select(0, 13)
                      for j in range(4)] for i in range(5)]
        r3ws = rSumReg.bit_select(itn_len - 13, 13)
        r3wc = rCarryReg.bit_select(itn_len - 13, 13)
        r2ws = rSumReg.bit_select(itn_len - 10, 10)
        r2wc = rCarryReg.bit_select(itn_len - 10, 10)

        # selection block / 选择块
        # Decode SRT sign probes into a one-hot quotient digit / 将 SRT 符号探针译为独热商位
        def detect_sign(signs):
            qVec = [Signal(name=f"qVec_{k}") for k in range(5)]
            m.d.comb += qVec[Q_N2].eq(signs.bit_select(0, 1) & signs.bit_select(1, 1) & signs.bit_select(2, 1))
            m.d.comb += qVec[Q_N1].eq(~signs.bit_select(0, 1) & signs.bit_select(1, 1) & signs.bit_select(2, 1))
            m.d.comb += qVec[Q_0].eq(signs.bit_select(2, 1) & ~signs.bit_select(1, 1))
            m.d.comb += qVec[Q_P1].eq(signs.bit_select(3, 1) & ~signs.bit_select(2, 1) & ~signs.bit_select(1, 1))
            m.d.comb += qVec[Q_P2].eq(~signs.bit_select(3, 1) & ~signs.bit_select(2, 1) & ~signs.bit_select(1, 1))
            return Cat(*qVec)

        signsVec = []
        for i in range(4):
            rudPmSel = mux1h(qPrevReg, [rudPmNegReg[k][i] for k in range(5)])
            s, c = csa3_2(r2ws, r2wc, rudPmSel, 10)
            sumFull = (s + (c.bit_select(0, 9) << 1))
            signsVec.append(sumFull.bit_select(9, 1))
        signsVal = Cat(*signsVec)
        qNext = detect_sign(signsVal)
        # wide CSA / 宽 CSA
        udPrev = mux1h(qPrevReg, udNegReg)
        s1, c1 = csa3_2(rSumReg << 2, rCarryReg << 2, udPrev << 2, itn_len)
        udNext = mux1h(qNext, udNegReg)
        s2, c2 = csa3_2(s1 << 2, (c1 << 1).bit_select(0, itn_len) << 2, udNext << 2, itn_len)
        rSumIter = Mux(~oddIter & finalIter, s1, s2)
        rCarryIter = Mux(~oddIter & finalIter,
                         (c1 << 1).bit_select(0, itn_len),
                         (c2 << 1).bit_select(0, itn_len))
        # speculative / 推测
        qSpec = []
        for qspec in range(5):
            s1p, c1p = csa3_2(r3ws, r3wc,
                               sign_ext(udNegReg[qspec].bit_select(itn_len - 11, 10), 10, 13), 13)
            signs2Vec = []
            for i in range(4):
                r2sel = mux1h(qPrevReg, [r2udPmNegReg[k][i] for k in range(5)])
                s2p, c2p = csa3_2(s1p, (c1p << 1).bit_select(0, 13), r2sel, 13)
                sf = (s2p + (c2p.bit_select(0, 12) << 1))
                signs2Vec.append(sf.bit_select(12, 1))
            qSpec.append(detect_sign(Cat(*signs2Vec)))
        qNext2 = mux1h(qNext, qSpec)

        # OTFC / 商即时转换
        # Convert quotient digit to on-the-fly quotient pair / 将商位转换为即时商及前一商
        def otfc(q: Any, quot: Any, quotM1: Any) -> tuple[Any, Any]:
            quot_shifted = quot.bit_select(0, ln - 2)
            quot_m1_shifted = quotM1.bit_select(0, ln - 2)
            qn = Mux(q.bit_select(Q_P2, 1),
                     Cat(Const(0b10, 2), quot_shifted),
                     Mux(q.bit_select(Q_P1, 1),
                         Cat(Const(0b01, 2), quot_shifted),
                         Mux(q.bit_select(Q_0, 1),
                             Cat(Const(0b00, 2), quot_shifted),
                             Mux(q.bit_select(Q_N1, 1),
                                 Cat(Const(0b11, 2), quot_m1_shifted),
                                 Cat(Const(0b10, 2), quot_m1_shifted)))))
            qmn = Mux(q.bit_select(Q_P2, 1),
                      Cat(Const(0b01, 2), quot_shifted),
                      Mux(q.bit_select(Q_P1, 1),
                          Cat(Const(0b00, 2), quot_shifted),
                          Mux(q.bit_select(Q_0, 1),
                              Cat(Const(0b11, 2), quot_m1_shifted),
                              Mux(q.bit_select(Q_N1, 1),
                                  Cat(Const(0b10, 2), quot_m1_shifted),
                                  Cat(Const(0b01, 2), quot_m1_shifted)))))
            return qn, qmn
        quotHalfIter, quotM1HalfIter = otfc(qPrevReg, quotIterReg, quotM1IterReg)
        qi2, qmi2 = otfc(qNext, quotHalfIter, quotM1HalfIter)
        quotIterNext = Mux(~oddIter & finalIter, quotHalfIter, qi2)
        quotM1IterNext = Mux(~oddIter & finalIter, quotM1HalfIter, qmi2)
        m.d.comb += quotIter.eq(Mux(state.bit_select(S_ITER, 1), quotIterNext,
                                     Mux(state.bit_select(S_PRE1, 1), Const(0, ln),
                                         Mux(quotSignReg, aInverter, quotIterReg))))
        m.d.comb += quotM1Iter.eq(Mux(state.bit_select(S_ITER, 1), quotM1IterNext,
                                       Mux(state.bit_select(S_PRE1, 1), Const(0, ln),
                                           Mux(quotSignReg, dInverter, quotM1IterReg))))

        # rNext / 余数次态
        dNormExt = cast(Any, Cat(Const(0, 3), dNormReg, Const(0, 1)))
        with m.If(rSignReg):
            m.d.comb += rNext.eq((cast(Any, ~rSumReg) + cast(Any, ~rCarryReg) + 2).bit_select(0, itn_len))
            m.d.comb += rNextPd.eq((cast(Any, ~rSumReg) + cast(Any, ~rCarryReg) + cast(Any, ~dNormExt) + 3).bit_select(0, itn_len))
        with m.Else():
            m.d.comb += rNext.eq(rSumReg + rCarryReg)
            m.d.comb += rNextPd.eq(rSumReg + rCarryReg + dNormExt)
        # right shifter / 右移
        m.submodules.rightShifter = rs = RightShifter(ln, lzc_width)
        r = rNextReg
        rPd = rNextPdReg
        rIsZero = Mux(or_reduce(r, ln + 1), Const(0, 1), Const(1, 1))
        needCorr = Mux(rSignReg,
                       Mux(r.bit_select(ln, 1), Const(0, 1), Const(1, 1))
                       & Mux(rIsZero, Const(0, 1), Const(1, 1)),
                       r.bit_select(ln, 1))
        rPreShifted = cast(Any, Mux(needCorr, rPd, r))
        m.d.comb += rs.in_.eq(rPreShifted)
        m.d.comb += rs.shiftNum.eq(dLZCReg.bit_select(0, lzc_width))
        m.d.comb += rs.msb.eq(Mux(~or_reduce(rPreShifted, ln + 1),
                                  Const(0, 1), rSignReg))
        # output mux / 输出选择
        res = Mux(isHi, rFinal, qFinal)
        m.d.comb += self.out_data.eq(Mux(isW, sign_ext(res.bit_select(0, ln // 2), ln // 2, ln), res))
        m.d.comb += self.in_ready.eq(state.bit_select(S_IDLE, 1))
        m.d.comb += self.out_valid.eq(state.bit_select(S_FINISH, 1))
        m.d.comb += self.outValidAhead3Cycle.eq(
            (finalIter & state.bit_select(S_ITER, 1)) | (special & state.bit_select(S_PRE1, 1)))
        m.d.comb += self.out_validNext.eq(state.bit_select(S_POST1, 1))

        # FSM + regs / 状态机与寄存器
        with m.If(kill_r):
            m.d.sync += state.eq(Const(1 << S_IDLE, 7))
        with m.Elif(state.bit_select(S_IDLE, 1) & in_fire & ~kill_w):
            m.d.sync += state.eq(Const(1 << S_PRE0, 7))
        with m.Elif(state.bit_select(S_PRE0, 1)):
            m.d.sync += state.eq(Const(1 << S_PRE1, 7))
        with m.Elif(state.bit_select(S_PRE1, 1)):
            m.d.sync += state.eq(Mux(special, Const(1 << S_POST1, 7), Const(1 << S_ITER, 7)))
        with m.Elif(state.bit_select(S_ITER, 1)):
            m.d.sync += state.eq(Mux(finalIter, Const(1 << S_POST0, 7), Const(1 << S_ITER, 7)))
        with m.Elif(state.bit_select(S_POST0, 1)):
            m.d.sync += state.eq(Const(1 << S_POST1, 7))
        with m.Elif(state.bit_select(S_POST1, 1)):
            m.d.sync += state.eq(Const(1 << S_FINISH, 7))
        with m.Elif(state.bit_select(S_FINISH, 1) & self.out_ready):
            m.d.sync += state.eq(Const(1 << S_IDLE, 7))
        # register enables / 寄存使能
        with m.If(cast(Any, state.bit_select(S_PRE1, 1))
                  | cast(Any, state.bit_select(S_ITER, 1))
                  | cast(Any, state.bit_select(S_POST0, 1))):
            m.d.sync += quotIterReg.eq(quotIter)
            m.d.sync += quotM1IterReg.eq(quotM1Iter)
        with m.If(state.bit_select(S_PRE1, 1)):
            m.d.sync += specialReg.eq(special)
        with m.If(in_fire):
            m.d.sync += aReg.eq(a)
            m.d.sync += dSignReg.eq(dSign)
            m.d.sync += rSignReg.eq(rSign)
        with m.If(in_fire | (state.bit_select(S_PRE1, 1) & dIsZero)):
            m.d.sync += quotSignReg.eq(quotSign)
        with m.If(in_fire):
            m.d.sync += aAbsReg.eq(aAbs)
            m.d.sync += dAbsReg.eq(dAbs)
        with m.If(state.bit_select(S_PRE0, 1)):
            m.d.sync += aNormReg.eq(aNorm)
            m.d.sync += dNormReg.eq(dNorm)
            m.d.sync += aLZCReg.eq(aLZC)
            m.d.sync += dLZCReg.eq(dLZC)
            m.d.sync += aTooSmallStorage.eq(Mux(
                aLZC.bit_select(lzc_width, 1), Const(1, 1),
                lzcWireDiff.bit_select(lzc_width, 1)))
        with m.If(cast(Any, state.bit_select(S_PRE1, 1))
                  | cast(Any, state.bit_select(S_ITER, 1))):
            m.d.sync += iterNumReg.eq(iterNumNext)
        # init regs / 初始寄存
        with m.If(state.bit_select(S_PRE1, 1)):
            m.d.sync += qPrevReg.eq(qInit)
            m.d.sync += rSumReg.eq(rSumInit)
            m.d.sync += rCarryReg.eq(rCarryInit)
            m.d.sync += quotSpecialReg.eq(quotSpecial)
            m.d.sync += remSpecialReg.eq(remSpecial)
            for i in range(5):
                m.d.sync += udNegReg[i].eq(udNeg[i])
                for j in range(4):
                    m.d.sync += rudPmNegReg[i][j].eq(rudPmNeg[i][j])
                    m.d.sync += r2udPmNegReg[i][j].eq(r2udPmNeg[i][j])
        with m.Elif(state.bit_select(S_ITER, 1)):
            m.d.sync += qPrevReg.eq(qNext2)
            m.d.sync += rSumReg.eq(rSumIter)
            m.d.sync += rCarryReg.eq(rCarryIter)
        with m.If(state.bit_select(S_POST0, 1)):
            m.d.sync += rNextReg.eq(rNext.bit_select(3, ln + 1))
            m.d.sync += rNextPdReg.eq(rNextPd.bit_select(3, ln + 1))
        with m.If(state.bit_select(S_POST1, 1)):
            m.d.sync += rFinal.eq(Mux(specialReg, remSpecialReg, rs.out))
            m.d.sync += qFinal.eq(Mux(specialReg, quotSpecialReg,
                                      Mux(needCorr, quotM1IterReg, quotIterReg)))
        return m


class SRT16DividerReferenceAdapter(SRT16DividerDataModule):
    """Compatibility constructor retaining the exact public IO shell."""

    def __init__(self, configuration: SRT16DividerConfig | int | None = None) -> None:
        super().__init__(configuration)


# Barrel left shift with bounded width / 按有界位宽执行桶形左移
def barrel_lsh(in_v, shift, w):
    L = shift.shape().width
    out = in_v
    bit = 0
    while (1 << bit) < w:
        amt = 1 << bit
        sel = shift.bit_select(bit, 1) if bit < L else Const(0, 1)
        out = Mux(sel, Cat(Const(0, amt), out.bit_select(0, w - amt)), out)
        bit += 1
    return out


# Encode a static index as one-hot / 将静态索引编码为独热值
def uint_to_oh(idx, w):
    # one-hot constant for static idx / 静态索引独热常量
    return Const(1 << idx, w)


# Reduce an expression with OR / 对表达式执行或归约
def or_reduce(v, w):
    acc = Const(0, 1)
    for i in range(w):
        acc = acc | v.bit_select(i, 1)
    return acc


# Reduce an expression with AND / 对表达式执行与归约
def and_reduce(v, w):
    acc = Const(1, 1)
    for i in range(w):
        acc = acc & v.bit_select(i, 1)
    return acc


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration=None,
                  injected_dependencies: dict[str, Any] | None = None) -> str:
    """Emit deterministic RTL with the locked module name and full ABI."""

    del injected_dependencies
    from amaranth.back import verilog
    if isinstance(configuration, dict):
        config = SRT16DividerConfig(int(configuration.get("len", 64)))
    elif configuration is None:
        config = SRT16DividerConfig()
    elif isinstance(configuration, SRT16DividerConfig):
        config = configuration
    else:
        config = SRT16DividerConfig(int(configuration))
    top = SRT16DividerDataModule(config)
    ports = [top.clock, top.reset, top.io_src_0, top.io_src_1, top.io_valid,
             top.io_sign, top.io_kill_w, top.io_kill_r, top.io_isHi, top.io_isW,
             top.io_in_ready, top.io_out_valid, top.io_out_data, top.io_out_ready]
    return verilog.convert(top, name="SRT16DividerDataModule", ports=ports,
                           emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
