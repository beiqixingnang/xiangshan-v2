"""True-LRU state generator used by the BPU replacer. / BPU 替换器真 LRU 状态生成器。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from amaranth import Cat, Const, Elaboratable, Module, Mux, Signal


# =============================================================================
# Module Contract
# =============================================================================
# Public symbols / 公开符号:
#   - LruStateGenConfig, LruStateGen, build_verilog, main
# Port contract / 端口契约:
#   - state: packed triangular recency matrix (6 bits for four ways)
#   - touches_0_valid/touches_0_bits: one valid way touch (configurable)
#   - nextState: state after sequentially applying valid touches
#   - victim: least-recently-used way index
# The implementation follows XiangShan's ReplacerStateGen/LruStateGen
# triangular matrix algorithm and is purely combinational.
# Status / 状态: PYTHON_PRESENT_UNVERIFIED (phase-2 structural alignment)
__all__ = ["LruStateGenConfig", "LruStateGen", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class LruStateGenConfig:
    # LRU geometry / LRU 几何配置
    numWays: int = 4
    numSets: int = 256  # retained for compatibility; this unit is per-set
    accessSize: int = 1

    @property
    def stateWidth(self) -> int:
        # Triangular matrix storage width / 三角矩阵存储位宽
        return max(1, self.numWays * (self.numWays - 1) // 2)

    @property
    def wayWidth(self) -> int:
        # Encoded way width / 路编号编码位宽
        return max(1, (self.numWays - 1).bit_length())


# =============================================================================
# Implementation
# =============================================================================
class LruStateGen(Elaboratable):
    # Combinational true-LRU state generator / 组合真 LRU 状态生成器
    def __init__(self, cfg: LruStateGenConfig | None = None):
        c = cfg or LruStateGenConfig()
        if c.numWays < 2:
            raise ValueError("LruStateGen requires at least two ways")
        if c.accessSize < 1:
            raise ValueError("LruStateGen accessSize must be positive")
        self.cfg = c
        self.state = Signal(c.stateWidth, name="io_state")
        self.touches = []
        self.touches_valid = []
        self.touches_bits = []
        for i in range(c.accessSize):
            valid = Signal(name=f"io_touches_{i}_valid")
            bits = Signal(c.wayWidth, name=f"io_touches_{i}_bits")
            self.touches.append({"valid": valid, "bits": bits})
            self.touches_valid.append(valid)
            self.touches_bits.append(bits)
        self.nextState = Signal(c.stateWidth, name="io_nextState")
        self.victim = Signal(c.wayWidth, name="io_victim")

    def extract_mru_rows(self, state):
        # Reconstruct the lower-triangular recency rows / 重建下三角新近矩阵行
        c = self.cfg
        rows = []
        lsb = 0
        for i in range(c.numWays - 1):
            row_width = c.numWays - i - 1
            # Chisel Cat(state_slice, zero) is MSB-first; reverse operands for
            # Amaranth's least-significant-first Cat.
            rows.append(Cat(Const(0, i + 1), state[lsb:lsb + row_width]))
            lsb += row_width
        return rows

    def pack_rows(self, rows):
        # Pack row high portions into the Scala state layout / 按 Scala 布局打包行
        c = self.cfg
        return Cat(*(rows[i][i + 1:c.numWays] for i in range(c.numWays - 1)))

    def next_single(self, state, touch):
        # Apply one way touch to each packed pair bit. Bit (i,j) is one when
        # higher-index way j is more recent than lower-index way i.
        c = self.cfg
        bits = []
        offset = 0
        for i in range(c.numWays - 1):
            for j in range(i + 1, c.numWays):
                current = state.bit_select(offset, 1)
                bits.append(Mux(touch == i, Const(0, 1),
                                Mux(touch == j, Const(1, 1), current)))
                offset += 1
        return Cat(*bits)

    def victim_expr(self, state):
        # Decode the least-recently-used way / 解码最久未使用路
        c = self.cfg
        rows = self.extract_mru_rows(state)
        victim_oh = []
        for i in range(c.numWays):
            upper = (Const(1) if i == c.numWays - 1
                     else cast(Any, rows[i][i + 1:c.numWays]).all())
            lower = (Const(1) if i == 0
                     else cast(Any, Cat(*[~rows[j][i] for j in range(i)])).all())
            victim_oh.append(upper & lower)
        result = Const(0, c.wayWidth)
        for i in range(c.numWays):
            result = Mux(victim_oh[i], i, result)
        return result

    def elaborate(self, platform):
        # Wire folded touches and victim decode / 连接触碰折叠与受害路解码
        m = Module()
        folded = self.state
        for valid, bits in zip(self.touches_valid, self.touches_bits):
            folded = Mux(valid, self.next_single(folded, bits), folded)
        m.d.comb += [self.nextState.eq(folded), self.victim.eq(self.victim_expr(self.state))]
        return m


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(config: LruStateGenConfig | None = None,
                  name: str = "LruStateGen") -> str:
    # Convert the real state generator to Verilog / 导出真实状态生成器
    from amaranth.back import verilog
    top = LruStateGen(config)
    ports = [top.state]
    ports.extend(signal for item in top.touches for signal in (item["valid"], item["bits"]))
    ports.extend([top.nextState, top.victim])
    return verilog.convert(top, name=name, ports=ports)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    # Direct elaboration entry / 直接入口
    print(build_verilog())


if __name__ == "__main__":
    main()
