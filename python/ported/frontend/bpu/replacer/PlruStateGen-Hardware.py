"""Tree pseudo-LRU state generator. / 二叉树伪 LRU 状态生成器。"""

from __future__ import annotations

from dataclasses import dataclass

from amaranth import Cat, Const, Elaboratable, Module, Mux, Signal


# =============================================================================
# Module Contract
# =============================================================================
# Public symbols / 公开符号:
#   - PlruStateGenConfig, PlruStateGen, build_verilog, main
# Port contract / 端口契约:
#   - state: NumWays-1 tree bits
#   - touches_i_valid/touches_i_bits: valid way touches, applied in order
#   - nextState: tree state after all valid touches
#   - victim: encoded way selected by the tree (retained on the Python object)
# This is the recursive tree algorithm from XiangShan's PlruStateGen, with no
# per-set storage or clocked state in this helper.
# Status / 状态: PYTHON_PRESENT_UNVERIFIED (phase-2 structural alignment)
__all__ = ["PlruStateGenConfig", "PlruStateGen", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class PlruStateGenConfig:
    # PLRU geometry / PLRU 几何配置
    numWays: int = 4
    numSets: int = 256  # retained for compatibility; this unit is per-set
    accessSize: int = 1
    fixedTouchWays: bool = False  # adapter specialization may tie way constants

    @property
    def stateWidth(self) -> int:
        # One direction bit per internal tree node / 每个树节点一个方向位
        return max(1, self.numWays - 1)

    @property
    def wayWidth(self) -> int:
        # Encoded way width / 路编号编码位宽
        return max(1, (self.numWays - 1).bit_length())


# =============================================================================
# Implementation
# =============================================================================
class PlruStateGen(Elaboratable):
    # Combinational tree-PLRU generator / 组合树形伪 LRU 生成器
    def __init__(self, cfg: PlruStateGenConfig | None = None):
        c = cfg or PlruStateGenConfig()
        if c.numWays < 2:
            raise ValueError("PlruStateGen requires at least two ways")
        if c.accessSize < 1:
            raise ValueError("PlruStateGen accessSize must be positive")
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

    def ceil_log2(self, value: int) -> int:
        # Return the minimum encoded width / 求最小编码位宽
        return max(1, (value - 1).bit_length())

    def split_state(self, state, tree_ways: int):
        # Split root, left subtree, and right subtree / 分解根、左右子树状态
        if tree_ways <= 2:
            return None, None, None
        right_ways = 1 << (self.ceil_log2(tree_ways) - 1)
        left_ways = tree_ways - right_ways
        right_width = right_ways - 1
        left_width = left_ways - 1
        root = state[tree_ways - 2]
        right_state = state[:right_width]
        left_state = state[right_width:right_width + left_width]
        return root, left_state, right_state

    def next_tree(self, state, touch, tree_ways: int):
        # Recursively update one tree with a way touch / 递归更新一次路触碰
        if tree_ways <= 1:
            return Const(0, 1)
        if tree_ways == 2:
            return ~(touch[0])
        root, left_state, right_state = self.split_state(state, tree_ways)
        right_ways = 1 << (self.ceil_log2(tree_ways) - 1)
        left_ways = tree_ways - right_ways
        set_left_older = ~touch[self.ceil_log2(tree_ways) - 1]
        right_touch = touch[:self.ceil_log2(right_ways)]
        right_next = self.next_tree(right_state, right_touch, right_ways)
        if left_ways > 1:
            left_touch = touch[:self.ceil_log2(left_ways)]
            left_next = self.next_tree(left_state, left_touch, left_ways)
            left_result = Mux(set_left_older, left_state, left_next)
            right_result = Mux(set_left_older, right_next, right_state)
            return Cat(right_result, left_result, set_left_older)
        right_result = Mux(set_left_older, right_next, right_state)
        return Cat(right_result, set_left_older)

    def victim_tree(self, state, tree_ways: int):
        # Recursively select the tree's victim way / 递归选择树形受害路
        if tree_ways <= 1:
            return Const(0, 1)
        if tree_ways == 2:
            return state[0]
        root, left_state, right_state = self.split_state(state, tree_ways)
        right_ways = 1 << (self.ceil_log2(tree_ways) - 1)
        left_ways = tree_ways - right_ways
        right_victim = self.victim_tree(right_state, right_ways)
        if left_ways > 1:
            left_victim = self.victim_tree(left_state, left_ways)
            chosen = Mux(root, left_victim, right_victim)
        else:
            chosen = Mux(root, Const(0, 1), right_victim)
        return Cat(chosen, root)

    def elaborate(self, platform):
        # Fold touches and decode current victim / 折叠触碰并解码当前受害路
        m = Module()
        if self.cfg.fixedTouchWays:
            # The reference MainBTB specialization wires four touches to
            # constant way indices and exposes only their valid bits.
            for i, bits in enumerate(self.touches_bits):
                m.d.comb += bits.eq(i)
        folded = self.state
        for valid, bits in zip(self.touches_valid, self.touches_bits):
            folded = Mux(valid, self.next_tree(folded, bits, self.cfg.numWays), folded)
        m.d.comb += [self.nextState.eq(folded),
                     self.victim.eq(self.victim_tree(self.state, self.cfg.numWays))]
        return m


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(config: PlruStateGenConfig | None = None,
                  name: str = "PlruStateGen") -> str:
    # Convert the real state generator to Verilog / 导出真实状态生成器
    from amaranth.back import verilog
    # Match the pinned four-way specialization: valid-only touches represent
    # fixed ways 0..3; explicit configs retain the generic touch-bit surface.
    export_config = config or PlruStateGenConfig(numWays=4, accessSize=4,
                                                  fixedTouchWays=True)
    top = PlruStateGen(export_config)
    ports = [top.state]
    for item in top.touches:
        ports.append(item["valid"])
        if not export_config.fixedTouchWays:
            ports.append(item["bits"])
    ports.append(top.nextState)
    if not export_config.fixedTouchWays:
        ports.append(top.victim)
    return verilog.convert(top, name=name, ports=ports)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    # Direct elaboration entry / 直接入口
    print(build_verilog())


if __name__ == "__main__":
    main()
