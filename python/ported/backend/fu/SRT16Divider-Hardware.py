"""SRT16Divider (radix-4 SRT divide data module with 7-state FSM). / SRT16 除法器（基 4 SRT 除法数据模块，7 状态机）。"""

from __future__ import annotations

from dataclasses import dataclass

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
# CSA3_2(len) = 3:2 carry-save adder (full adder per bit). PriorityEncoder
# finds the MSB-most zero (reverse-bit priority). m tables mirrored verbatim.
# / 真实逻辑：SRT16DividerDataModule 的忠实移植。7 状态独热机（idle→pre_0→
# pre_1→iter→post_0→post_1→finish）、LZC 归一化、SRT 基 4 数位选择（-m 查表
# +CSA3_2 压缩器+DetectSign）、推测 qNext2、商即时转换 OTFC、余数修正+
# RightShifter、特殊情形处理（d=1/-1/0、a 过小）。CSA3_2(len) 为 3:2 进位
# 保存加法器（逐位全加器）。PriorityEncoder 反位序优先编码。m 表原样镜像。
# Status / 状态: PYTHON_PRESENT_UNVERIFIED (phase-1 bulk port / 阶段一批量重写)
__all__ = ["SRT16DividerConfig", "SRT16DividerDataModule", "RightShifter",
           "mLookUpTable2", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class SRT16DividerConfig:
    len: int = 64


# =============================================================================
# Implementation
# =============================================================================
def csa3_2(a, b, cin, w):
    # 3:2 carry-save adder (full adder per bit) / 3:2 进位保存加法器
    axb = a ^ b
    s = axb ^ cin
    c = (a & b) | (axb & cin)
    return (s.bit_select(0, w), c.bit_select(0, w))


# Find the first asserted bit from the MSB side / 从最高位侧查找首个置位位
def priority_encoder(bits, w):
    # PriorityEncoder of reversed bits -> MSB-first zero / 反位序优先编码
    idx = Const(0, w)
    for i in range(w):
        idx = Mux(bits.bit_select(w - 1 - i, 1), Const(i, w), idx)
    return idx


# Sign extend an expression to a target width / 将表达式符号扩展到目标位宽
def sign_ext(v, vw, tw):
    if tw <= vw:
        return v.bit_select(0, tw)
    s = v.bit_select(vw - 1, 1)
    return Cat(v, *[s for _ in range(tw - vw)])


# Select a constant from an indexed lookup table / 按索引从常量查找表选择
def mux_lookup(idx, default, table, w):
    # MuxLookup(idx, default)(table) / 查表
    res = Const(default, w)
    for k, v in table:
        res = Mux(idx == k, Const(v, w), res)
    return res


# Multiplex values under one-hot selectors / 在独热选择信号下复用值
def mux1h(sels, vals):
    # Mux1H over one-hot selectors / 独热选择
    res = vals[0] & Cat(*[sels[0] for _ in range(vals[0].shape().width)]) \
        if False else (vals[0] & replicate(sels[0], vals[0].shape().width))
    for i in range(1, len(sels)):
        res = res | (vals[i] & replicate(sels[i], vals[i].shape().width))
    return res


# Replicate a one-bit expression / 复制单比特表达式
def replicate(bit, w):
    return Cat(*[bit for _ in range(w)])


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
    def __init__(self, length, lzc_width):
        self.length = length
        self.lzc_width = lzc_width
        self.shiftNum = Signal(lzc_width, name="rs_shiftNum")
        self.in_ = Signal(length, name="rs_in")
        self.msb = Signal(name="rs_msb")
        self.out = Signal(length, name="rs_out")

    # Elaborate the right-shifter combinational network / 展开右移器组合网络
    def elaborate(self, platform):
        m = Module()
        length = self.length
        shift = self.shiftNum
        msb = self.msb
        s = self.in_
        for bit in range(min(self.lzc_width, 6)):
            amt = 1 << bit
            if amt >= length:
                break
            padded = Cat(*[msb for _ in range(amt)], s.bit_select(amt, length - amt))
            s = Mux(shift.bit_select(bit, 1), padded, s)
        m.d.comb += self.out.eq(s)
        return m


class SRT16DividerDataModule(Elaboratable):
    # radix-4 SRT divider / 基 4 SRT 除法器
    def __init__(self, config):
        self.config = config
        c = config
        ln = c.len
        self.src = [Signal(ln, name=f"srt_src{i}") for i in range(2)]
        self.valid = Signal(name="srt_valid")
        self.sign = Signal(name="srt_sign")
        self.kill_w = Signal(name="srt_kill_w")
        self.kill_r = Signal(name="srt_kill_r")
        self.isHi = Signal(name="srt_isHi")
        self.isW = Signal(name="srt_isW")
        self.in_ready = Signal(name="srt_in_ready")
        self.out_valid = Signal(name="srt_out_valid")
        self.out_validNext = Signal(name="srt_out_validNext")
        self.out_data = Signal(ln, name="srt_out_data")
        self.out_ready = Signal(name="srt_out_ready")
        self.outValidAhead3Cycle = Signal(name="srt_outValidAhead3Cycle")

    # Elaborate the iterative SRT divider datapath / 展开迭代式 SRT 除法数据通路
    def elaborate(self, platform):
        m = Module()
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
        state = Signal(7, name="srt_state", reset=(1 << S_IDLE))

        # quotient digit OH / 商数位独热
        Q_N2, Q_N1, Q_0, Q_P1, Q_P2 = range(5)

        # regs / 寄存器
        quotIterReg = Signal(ln, name="srt_quotIterReg")
        quotM1IterReg = Signal(ln, name="srt_quotM1IterReg")
        specialReg = Signal(name="srt_specialReg", reset=0)
        aReg = Signal(ln, name="srt_aReg")
        dSignReg = Signal(name="srt_dSignReg")
        aAbsReg = Signal(ln, name="srt_aAbsReg")
        dAbsReg = Signal(ln, name="srt_dAbsReg")
        aNormReg = Signal(ln, name="srt_aNormReg")
        dNormReg = Signal(ln, name="srt_dNormReg")
        aLZCReg = Signal(lzc_width + 1, name="srt_aLZCReg")
        dLZCReg = Signal(lzc_width + 1, name="srt_dLZCReg")
        quotSpecialReg = Signal(ln, name="srt_quotSpecialReg")
        remSpecialReg = Signal(ln, name="srt_remSpecialReg")
        quotSignReg = Signal(name="srt_quotSignReg")
        rSignReg = Signal(name="srt_rSignReg")
        iterNumReg = Signal(max(1, lzc_width - 2), name="srt_iterNumReg")
        udNegReg = [Signal(itn_len, name=f"srt_udNegReg_{i}") for i in range(5)]
        rudPmNegReg = [[Signal(10, name=f"srt_rudPmNegReg_{i}_{j}") for j in range(4)]
                       for i in range(5)]
        r2udPmNegReg = [[Signal(13, name=f"srt_r2udPmNegReg_{i}_{j}") for j in range(4)]
                        for i in range(5)]
        qPrevReg = Signal(5, name="srt_qPrevReg")
        rSumReg = Signal(itn_len, name="srt_rSumReg")
        rCarryReg = Signal(itn_len, name="srt_rCarryReg")
        rNextReg = Signal(ln, name="srt_rNextReg")
        rNextPdReg = Signal(ln, name="srt_rNextPdReg")
        rFinal = Signal(ln, name="srt_rFinal")
        qFinal = Signal(ln, name="srt_qFinal")
        aTooSmallStorage = Signal(name="srt_aTooSmall_storage")

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
        aNorm = barrel_lsh(aAbsReg, aLZCReg.bit_select(0, lzc_width), ln)
        dNorm = barrel_lsh(dAbsReg, dLZCReg.bit_select(0, lzc_width), ln)
        # LZC / 前导零检测
        m.d.comb += aLZC.eq(priority_encoder(aAbsReg, ln))
        m.d.comb += dLZC.eq(priority_encoder(dAbsReg, ln))
        lzcWireDiff = (Cat(Const(0, 1), dLZCReg.bit_select(0, lzc_width))
                       - Cat(Const(0, 1), aLZC.bit_select(0, lzc_width)))
        lzcRegDiff = (Cat(Const(0, 1), dLZCReg.bit_select(0, lzc_width))
                      - Cat(Const(0, 1), aLZCReg.bit_select(0, lzc_width)))
        # special / 特殊
        dIsOne = and_reduce(dLZC.bit_select(0, lzc_width), lzc_width)
        dIsZero = ~or_reduce(dNormReg, ln)
        aTooSmall = aLZC.bit_select(lzc_width, 1)
        m.d.comb += special.eq(dIsOne | dIsZero | aTooSmall)
        quotSpecial = Mux(dIsZero, Const(-1, ln),
                          Mux(aTooSmall, Const(0, ln),
                              Mux(dSignReg, (-aReg).bit_select(0, ln), aReg)))
        remSpecial = Mux(dIsZero | aTooSmall, aReg, Const(0, ln))
        # signs / 符号
        quotSign = Mux(state.bit_select(S_IDLE, 1), aSign ^ dSign, Const(1, 1))
        rSign = aSign
        rShift = lzcRegDiff.bit_select(0, 1)
        oddIter = lzcRegDiff.bit_select(1, 1) ^ lzcRegDiff.bit_select(0, 1)
        iterNum = Signal(max(1, lzc_width - 2), name="srt_iterNum")
        iterNumNext = Mux(state.bit_select(S_PRE1, 1),
                          (Cat(Const(0, 1), lzcRegDiff.bit_select(0, lzc_width)) + 1).bit_select(2, max(1, lzc_width - 2)),
                          (iterNumReg - 1).bit_select(0, max(1, lzc_width - 2)))
        m.d.comb += iterNum.eq(iterNumNext)
        m.d.comb += finalIter.eq(iterNumReg == 0)

        # init sums / 初始和
        aNormShifted = Mux(rShift, Cat(Const(0, 1), aNormReg), Cat(aNormReg, Const(0, 1)))
        rSumInit = Cat(Const(0, 3), aNormShifted)
        rSumInit = rSumInit.bit_select(0, itn_len)
        rCarryInit = Const(0, itn_len)
        rSumInitTrunc = Cat(Const(0, 1), rSumInit.bit_select(itn_len - 4, 5))
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
        dPos = Cat(Const(0, 1), dNormReg)
        dNeg = (-Cat(Const(0, 1), dNormReg)).bit_select(0, ln + 1)
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
        rudPmNeg = [[(sign_ext(rudNeg[i].bit_select(1, 9), 9, 10)
                      + mNeg[j].bit_select(1, 10)).bit_select(0, 10)
                     for j in range(4)] for i in range(5)]
        r2udPmNeg = [[(sign_ext(r2udNeg[i], 12, 13) + sign_ext(mNeg[j], 12, 13)).bit_select(0, 13)
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
        def otfc(q, quot, quotM1):
            qn = Mux(q.bit_select(Q_P2, 1), (Cat(quot, Const(0b10, 2)) << 0),
                      Mux(q.bit_select(Q_P1, 1), Cat(quot, Const(0b01, 2)),
                          Mux(q.bit_select(Q_0, 1), Cat(quot, Const(0b00, 2)),
                              Mux(q.bit_select(Q_N1, 1), Cat(quotM1, Const(0b11, 2)),
                                  Cat(quotM1, Const(0b10, 2))))))
            qmn = Mux(q.bit_select(Q_P2, 1), Cat(quot, Const(0b01, 2)),
                      Mux(q.bit_select(Q_P1, 1), Cat(quot, Const(0b00, 2)),
                          Mux(q.bit_select(Q_0, 1), Cat(quotM1, Const(0b11, 2)),
                              Mux(q.bit_select(Q_N1, 1), Cat(quotM1, Const(0b10, 2)),
                                  Cat(quotM1, Const(0b01, 2))))))
            return (qn.bit_select(0, ln), qmn.bit_select(0, ln))
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
        dNormExt = Cat(Const(0, 1), dNormReg, Const(0, 3))
        with m.If(rSignReg):
            m.d.comb += rNext.eq((~rSumReg + ~rCarryReg + 2).bit_select(0, itn_len))
            m.d.comb += rNextPd.eq((~rSumReg + ~rCarryReg + ~dNormExt + 3).bit_select(0, itn_len))
        with m.Else():
            m.d.comb += rNext.eq(rSumReg + rCarryReg)
            m.d.comb += rNextPd.eq(rSumReg + rCarryReg + dNormExt)
        # right shifter / 右移
        m.submodules.rightShifter = rs = RightShifter(ln, lzc_width)
        r = rNextReg
        rPd = rNextPdReg
        rIsZero = ~or_reduce(r, ln)
        needCorr = Mux(rSignReg, ~r.bit_select(ln - 1, 1) & ~rIsZero, r.bit_select(ln - 1, 1))
        rPreShifted = Mux(needCorr, rPd, r)
        m.d.comb += rs.in_.eq(rPreShifted)
        m.d.comb += rs.shiftNum.eq(dLZCReg.bit_select(0, lzc_width))
        m.d.comb += rs.msb.eq(Mux(~or_reduce(rPreShifted, ln), Const(0, 1), rSignReg))
        # output mux / 输出选择
        res = Mux(isHi, rFinal, qFinal)
        m.d.comb += self.out_data.eq(Mux(isW, sign_ext(res.bit_select(0, ln // 2), ln // 2, ln), res))
        m.d.comb += self.in_ready.eq(state.bit_select(S_IDLE, 1))
        m.d.comb += self.out_valid.eq(state.bit_select(S_FINISH, 1) & ~specialReg)
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
        with m.Elif(state.bit_select(S_FINISH, 1) & ~specialReg):
            m.d.sync += state.eq(Const(1 << S_IDLE, 7))
        # register enables / 寄存使能
        with m.If(state.bit_select(S_PRE1, 1) | state.bit_select(S_ITER, 1) | state.bit_select(S_POST0, 1)):
            m.d.sync += quotIterReg.eq(quotIter)
            m.d.sync += quotM1IterReg.eq(quotM1Iter)
        with m.If(state.bit_select(S_PRE1, 1) | state.bit_select(S_FINISH, 1)):
            m.d.sync += specialReg.eq(Mux(state.bit_select(S_FINISH, 1), Const(0, 1), special))
        with m.If(in_fire):
            m.d.sync += aReg.eq(a)
            m.d.sync += dSignReg.eq(dSign)
            m.d.sync += quotSignReg.eq(quotSign)
            m.d.sync += rSignReg.eq(rSign)
        with m.If(in_fire | state.bit_select(S_IDLE, 1)):
            m.d.sync += aAbsReg.eq(aAbs)
            m.d.sync += dAbsReg.eq(dAbs)
        with m.If(state.bit_select(S_PRE0, 1)):
            m.d.sync += aNormReg.eq(aNorm)
            m.d.sync += dNormReg.eq(dNorm)
            m.d.sync += aLZCReg.eq(aLZC)
            m.d.sync += dLZCReg.eq(dLZC)
            m.d.sync += aTooSmallStorage.eq(aLZC.bit_select(lzc_width, 1) | lzcWireDiff.bit_select(lzc_width, 1))
        with m.If(state.bit_select(S_PRE1, 1) | state.bit_select(S_ITER, 1)):
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
            m.d.sync += rNextReg.eq(rNext.bit_select(3, ln))
            m.d.sync += rNextPdReg.eq(rNextPd.bit_select(3, ln))
        with m.If(state.bit_select(S_POST1, 1)):
            m.d.sync += rFinal.eq(Mux(specialReg, remSpecialReg, rs.out))
            m.d.sync += qFinal.eq(Mux(specialReg, quotSpecialReg,
                                      Mux(needCorr, quotM1IterReg, quotIterReg)))
        return m


class SRT16DividerReferenceAdapter(Elaboratable):
    # Exact pinned Scala IO shell; internal convenience aliases stay private.
    # 精确匹配锁定 Scala 接口；内部便捷别名保持私有。
    def __init__(self, config: SRT16DividerConfig):
        self.config = config
        width = config.len
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.io_src_0 = Signal(width, name="io_src_0")
        self.io_src_1 = Signal(width, name="io_src_1")
        self.io_valid = Signal(name="io_valid")
        self.io_sign = Signal(name="io_sign")
        self.io_kill_w = Signal(name="io_kill_w")
        self.io_kill_r = Signal(name="io_kill_r")
        self.io_isHi = Signal(name="io_isHi")
        self.io_isW = Signal(name="io_isW")
        self.io_in_ready = Signal(name="io_in_ready")
        self.io_out_valid = Signal(name="io_out_valid")
        self.io_out_data = Signal(width, name="io_out_data")
        self.io_outValidAhead3Cycle = Signal(name="io_outValidAhead3Cycle")

    def elaborate(self, platform):
        # Adapt the exact Chisel names to the translated core. / 将精确 Chisel 名称连接到移植核心。
        m = Module()
        # Preserve the pinned top-level clock/reset names. / 保持锁定顶层时钟/复位名称。
        clock_domain = ClockDomain("sync")
        clock_domain.clk = self.clock
        clock_domain.rst = self.reset
        m.domains.sync = clock_domain
        core = SRT16DividerDataModule(self.config)
        m.submodules.core = core
        m.d.comb += [
            core.src[0].eq(self.io_src_0),
            core.src[1].eq(self.io_src_1),
            core.valid.eq(self.io_valid),
            core.sign.eq(self.io_sign),
            core.kill_w.eq(self.io_kill_w),
            core.kill_r.eq(self.io_kill_r),
            core.isHi.eq(self.io_isHi),
            core.isW.eq(self.io_isW),
            core.out_ready.eq(1),
            self.io_in_ready.eq(core.in_ready),
            self.io_out_valid.eq(core.out_valid),
            self.io_out_data.eq(core.out_data),
            self.io_outValidAhead3Cycle.eq(core.outValidAhead3Cycle),
        ]
        return m


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
def build_verilog(config=None, name: str = "SRT16Divider") -> str:
    from amaranth.back import verilog
    if config is None:
        config = SRT16DividerConfig(len=64)
    top = SRT16DividerReferenceAdapter(config)
    ports = [top.clock, top.reset, top.io_src_0, top.io_src_1, top.io_valid, top.io_sign,
             top.io_kill_w, top.io_kill_r, top.io_isHi, top.io_isW,
             top.io_in_ready, top.io_out_valid, top.io_out_data,
             top.io_outValidAhead3Cycle]
    return verilog.convert(top, name=name, ports=ports)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    print(build_verilog())


if __name__ == "__main__":
    main()
