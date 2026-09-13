"""CSA (carry-save adders: CSA2_2/CSA3_2/CSA5_3 and 1-bit C22/C32/C53). / 进位保存加法器（2:2/3:2/5:3 及 1 位压缩器）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from amaranth import Cat, Const, Elaboratable, Module, Signal


# =============================================================================
# Module Contract
# =============================================================================
# Public symbols / 公开符号:
#   - CSA2_2, CSA3_2, CSA5_3, C22, C32, C53 : carry-save adders
#   - build_verilog, main
# Real logic: per-bit compressors. CSA2_2 (a,b)->(sum=a^b, cout=a&b);
# CSA3_2 (a,b,cin)->(sum=a^b^cin, cout=a&b | (a^b)&cin) full adder;
# CSA5_3 two cascaded full adders on 5 inputs -> 3 outputs (sum, c0, c1).
# Wide variants iterate the 1-bit compressor across `len` bits, outputs are
# little-endian (amaranth Cat low-first, matching Chisel Cat reversed).
# / 真实逻辑：逐位压缩器。CSA2_2 (a,b)->(sum=a^b, cout=a&b)；CSA3_2 全加器；
# CSA5_3 两级级联全加器，5 入 3 出。宽位变体逐位迭代，输出小端
# （amaranth Cat 低位在前，对应 Chisel Cat 反转）。
# Status / 状态: PYTHON_PRESENT_UNVERIFIED (phase-1 bulk port / 阶段一批量重写)
__all__ = ["CSA2_2", "CSA3_2", "CSA5_3", "C22", "C32", "C53",
           "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class CSAConfig:
    length: int = 8


# =============================================================================
# Implementation
# =============================================================================
class CarrySaveAdderMToN(Elaboratable):
    # base m->n carry-save adder / 基类 m->n 进位保存加法器
    def __init__(self, m, n, length):
        self.m, self.n, self.length = m, n, length
        self.in_ = [Signal(length, name=f"io_in_{i}") for i in range(m)]
        self.out = [Signal(length, name=f"io_out_{i}") for i in range(n)]


# Cast a one-bit Amaranth view for static analysis / 为静态分析标注单比特视图
def bit_view(signal: Signal, index: int) -> Any:
    return cast(Any, signal.bit_select(index, 1))


class CSA2_2(CarrySaveAdderMToN):
    def __init__(self, length):
        super().__init__(2, 2, length)

    def elaborate(self, platform):
        m = Module()
        length = self.length
        a, b = self.in_[0], self.in_[1]
        sums = []
        couts = []
        for i in range(length):
            ai = bit_view(a, i)
            bi = bit_view(b, i)
            sums.append(ai ^ bi)
            couts.append(ai & bi)
        # Chisel Cat(temp.reverse) => LSB-first Cat / 小端拼接
        m.d.comb += self.out[0].eq(Cat(*sums))
        m.d.comb += self.out[1].eq(Cat(*couts))
        return m


class CSA3_2(CarrySaveAdderMToN):
    def __init__(self, length):
        super().__init__(3, 2, length)

    def elaborate(self, platform):
        m = Module()
        length = self.length
        a, b, cin = self.in_[0], self.in_[1], self.in_[2]
        sums = []
        couts = []
        for i in range(length):
            ai = bit_view(a, i)
            bi = bit_view(b, i)
            ci = bit_view(cin, i)
            axb = ai ^ bi
            sums.append(axb ^ ci)
            couts.append((ai & bi) | (axb & ci))
        m.d.comb += self.out[0].eq(Cat(*sums))
        m.d.comb += self.out[1].eq(Cat(*couts))
        return m


class CSA5_3(CarrySaveAdderMToN):
    def __init__(self, length):
        super().__init__(5, 3, length)

    def elaborate(self, platform):
        m = Module()
        length = self.length
        # FA1 on (in0,in1,in2) -> (s0,c0); FA2 on (s0,in3,in4) -> (s1,c1)
        # out = (s1, c0, c1) / 两级级联全加器
        s0 = Signal(length, name="csa53_s0")
        c0 = Signal(length, name="csa53_c0")
        for i in range(length):
            i0 = bit_view(self.in_[0], i)
            i1 = bit_view(self.in_[1], i)
            i2 = bit_view(self.in_[2], i)
            axb = i0 ^ i1
            m.d.comb += bit_view(s0, i).eq(axb ^ i2)
            m.d.comb += bit_view(c0, i).eq((i0 & i1) | (axb & i2))
        s1 = Signal(length, name="csa53_s1")
        c1 = Signal(length, name="csa53_c1")
        for i in range(length):
            s0i = bit_view(s0, i)
            i3 = bit_view(self.in_[3], i)
            i4 = bit_view(self.in_[4], i)
            axb = s0i ^ i3
            m.d.comb += bit_view(s1, i).eq(axb ^ i4)
            m.d.comb += bit_view(c1, i).eq((s0i & i3) | (axb & i4))
        m.d.comb += self.out[0].eq(s1)
        m.d.comb += self.out[1].eq(c0)
        m.d.comb += self.out[2].eq(c1)
        return m


class C22(CSA2_2):
    def __init__(self):
        super().__init__(1)


class C32(CSA3_2):
    def __init__(self):
        super().__init__(1)


class C53(CSA5_3):
    def __init__(self):
        super().__init__(1)


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(config=None, name: str = "CSA3_2") -> str:
    from amaranth.back import verilog
    if config is None:
        # The pinned reference CSA3_2 instance is ten bits wide.
        config = CSAConfig(length=10)
    top = CSA3_2(config.length)
    ports = top.in_ + top.out
    return verilog.convert(top, name=name, ports=ports)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    print(build_verilog())


if __name__ == "__main__":
    main()
