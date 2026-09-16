"""V2 tree pseudo-LRU state transform and victim decoder. / V2 二叉树伪 LRU 状态变换与受害路译码器。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amaranth import Cat, Const, Elaboratable, Module, Mux, Signal


# Module Contract / 模块契约
# State bit tree_nways-2 is the root; lower bits contain the right (lower-way)
# subtree followed by the left (higher-way) subtree, matching
# freechips.rocketchip.util.PseudoLRU.  A root value of one selects the left
# subtree as older.  Multi-touch updates are folded in input order.
# 状态树根位为最高位，触碰按输入顺序依次折叠，端口保持源协议语义。
__all__ = [
    "PlruStateGenConfig",
    "PlruStateGen",
    "PseudoLRU",
    "plru_next_state",
    "plru_victim",
    "plru_observation",
    "build_verilog",
    "main",
]


# Configuration / 配置
@dataclass(frozen=True)
class PlruStateGenConfig:
    """Geometry of one V2 PseudoLRU policy instance. / 单个 V2 伪 LRU 策略实例的几何参数。"""

    numWays: int = 4
    numSets: int = 256
    accessSize: int = 1
    fixedTouchWays: bool = False

    # Validate policy geometry / 校验策略几何参数
    def __post_init__(self) -> None:
        if self.numWays < 1:
            raise ValueError("numWays must be positive")
        if self.numSets < 1:
            raise ValueError("numSets must be positive")
        if self.accessSize < 1:
            raise ValueError("accessSize must be positive")

    @property
    # Return the packed tree state width / 返回树状态打包位宽
    def stateWidth(self) -> int:
        return max(1, self.numWays - 1)

    @property
    # Return the encoded way width / 返回路编号编码位宽
    def wayWidth(self) -> int:
        return max(1, (self.numWays - 1).bit_length())


# Normalize adapter configuration mappings / 规范化适配器配置映射
def normalize_configuration(configuration: Any) -> PlruStateGenConfig:
    if configuration is None:
        return PlruStateGenConfig()
    if isinstance(configuration, PlruStateGenConfig):
        return configuration
    if isinstance(configuration, dict):
        values = dict(configuration)
        for source, target in (("n_ways", "numWays"),
                               ("n_sets", "numSets"),
                               ("access_size", "accessSize"),
                               ("fixed_touch_ways", "fixedTouchWays")):
            if source in values and target not in values:
                values[target] = values.pop(source)
        return PlruStateGenConfig(**values)
    raise TypeError("configuration must be PlruStateGenConfig, dict, or None")


# Return mathematical ceil(log2(value)) / 返回数学上的 ceil(log2(value))
def ceil_log2(value: int) -> int:
    if value < 1:
        raise ValueError("value must be positive")
    return (value - 1).bit_length()


# Compute one V2 PseudoLRU state transition independently / 独立计算一次 V2 伪 LRU 状态变换
def plru_next_state(state: int, touch_way: int, num_ways: int) -> int:
    if num_ways < 1:
        raise ValueError("num_ways must be positive")
    if num_ways == 1:
        return 0
    width = num_ways - 1
    state &= (1 << width) - 1

    # Recurse through one integer PLRU tree / 递归处理整数伪 LRU 树
    def recurse(current: int, touch: int, ways: int) -> int:
        if ways <= 1:
            return 0
        if ways == 2:
            return 1 ^ (touch & 1)
        bits = ceil_log2(ways)
        right_ways = 1 << (bits - 1)
        left_ways = ways - right_ways
        right_width = right_ways - 1
        left_width = left_ways - 1
        root = 1 ^ ((touch >> (bits - 1)) & 1)
        right_state = current & ((1 << right_width) - 1)
        left_state = (current >> right_width) & ((1 << left_width) - 1)
        right_touch = touch & ((1 << ceil_log2(right_ways)) - 1)
        right_next = recurse(right_state, right_touch, right_ways)
        if left_ways > 1:
            left_touch = touch & ((1 << ceil_log2(left_ways)) - 1)
            left_next = recurse(left_state, left_touch, left_ways)
            left_result = left_state if root else left_next
            right_result = right_next if root else right_state
            return (right_result | (left_result << right_width) |
                    (root << (right_width + left_width)))
        right_result = right_next if root else right_state
        return right_result | (root << right_width)

    return recurse(state, touch_way, num_ways)


# Compute one V2 PseudoLRU victim independently / 独立计算一次 V2 伪 LRU 受害路
def plru_victim(state: int, num_ways: int) -> int:
    if num_ways < 1:
        raise ValueError("num_ways must be positive")
    if num_ways == 1:
        return 0
    state &= (1 << (num_ways - 1)) - 1

    # Recurse through one integer victim tree / 递归处理整数受害路树
    def recurse(current: int, ways: int) -> int:
        if ways <= 1:
            return 0
        if ways == 2:
            return current & 1
        bits = ceil_log2(ways)
        right_ways = 1 << (bits - 1)
        left_ways = ways - right_ways
        right_width = right_ways - 1
        left_width = left_ways - 1
        root = (current >> (right_width + left_width)) & 1
        right_state = current & ((1 << right_width) - 1)
        left_state = (current >> right_width) & ((1 << left_width) - 1)
        if root:
            child = recurse(left_state, left_ways) if left_ways > 1 else 0
        else:
            child = recurse(right_state, right_ways)
        return child | (root << (bits - 1))

    return recurse(state, num_ways)


def plru_observation(state: int, touches: list[tuple[bool, int]], num_ways: int) -> dict[str, int]:
    """Return pre-access victim and folded post-access PLRU state.

    This keeps the Rocket PseudoLRU observation atomic for parent differential
    benches while preserving the existing RTL ports. / 原子返回访问前受害路
    与按输入顺序折叠后的伪 LRU 状态。
    """

    next_state = int(state)
    for valid, way in touches:
        if valid:
            next_state = plru_next_state(next_state, int(way), num_ways)
    return {"victim": plru_victim(int(state), num_ways), "next_state": next_state}


# Implementation / 实现
class PlruStateGen(Elaboratable):
    """Combinational PseudoLRU transform matching Rocket-Chip V2. / 匹配 V2 Rocket-Chip 的组合伪 LRU 变换器。"""

    # Construct the state and touch ports / 构造状态与触碰端口
    def __init__(self, configuration: PlruStateGenConfig | dict | None = None) -> None:
        config = normalize_configuration(configuration)
        self.config = config
        self.cfg = config
        self.state = Signal(config.stateWidth, name="io_state")
        self.touches_valid = [
            Signal(name=f"io_touches_{index}_valid")
            for index in range(config.accessSize)
        ]
        self.touches_bits = [
            Signal(config.wayWidth, name=f"io_touches_{index}_bits")
            for index in range(config.accessSize)
        ]
        self.touches = [
            {"valid": valid, "bits": bits}
            for valid, bits in zip(self.touches_valid, self.touches_bits)
        ]
        self.nextState = Signal(config.stateWidth, name="io_nextState")
        self.victim = Signal(config.wayWidth, name="io_victim")
        self.touch_valid = self.touches_valid[0]
        self.touch_way = self.touches_bits[0]

    # Expose the source ceil-log2 helper / 暴露源实现的 ceil-log2 辅助函数
    def ceil_log2(self, value: int) -> int:
        return ceil_log2(value)

    # Split one source-style tree state / 分解一个源风格树状态
    def split_state(self, state: Any, tree_ways: int) -> tuple[Any, Any, Any]:
        if tree_ways <= 2:
            return None, None, None
        right_ways = 1 << (ceil_log2(tree_ways) - 1)
        left_ways = tree_ways - right_ways
        right_width = right_ways - 1
        left_width = left_ways - 1
        root = state[tree_ways - 2]
        right_state = state[:right_width]
        left_state = state[right_width:right_width + left_width]
        return root, left_state, right_state

    # Slice and zero-extend a touch path / 截取并零扩展触碰路径
    def touch_slice(self, touch: Any, width: int) -> Any:
        if width <= 0:
            return Const(0, 1)
        available = len(touch)
        if available >= width:
            return touch[:width]
        return Cat(touch, Const(0, width - available))

    # Slice a subtree state with a non-zero width / 截取非零宽度的子树状态
    def state_slice(self, state: Any, start: int, width: int) -> Any:
        if width <= 0:
            return Const(0, 1)
        return state[start:start + width]

    # Recursively build one hardware state transition / 递归构造一次硬件状态变换
    def next_tree(self, state: Any, touch_way: Any, tree_ways: int) -> Any:
        if isinstance(state, int):
            state = Const(state, max(1, tree_ways - 1))
        if isinstance(touch_way, int):
            touch_way = Const(touch_way, max(1, ceil_log2(tree_ways)))
        if tree_ways <= 1:
            return Const(0, 1)
        if tree_ways == 2:
            return ~touch_way[0]
        bits = ceil_log2(tree_ways)
        right_ways = 1 << (bits - 1)
        left_ways = tree_ways - right_ways
        right_width = right_ways - 1
        left_width = left_ways - 1
        root = ~touch_way[bits - 1]
        right_state = self.state_slice(state, 0, right_width)
        left_state = self.state_slice(state, right_width, left_width)
        right_touch = self.touch_slice(touch_way, ceil_log2(right_ways))
        right_next = self.next_tree(right_state, right_touch, right_ways)
        if left_ways > 1:
            left_touch = self.touch_slice(touch_way, ceil_log2(left_ways))
            left_next = self.next_tree(left_state, left_touch, left_ways)
            left_result = Mux(root, left_state, left_next)
            right_result = Mux(root, right_next, right_state)
            # Amaranth Cat is least-significant-first; root must be the MSB.
            return Cat(right_result, left_result, root)
        right_result = Mux(root, right_next, right_state)
        return Cat(right_result, root)

    # Expose the Rocket-Chip transition name / 暴露 Rocket-Chip 状态变换名称
    def get_next_state(self, state: Any, touch_way: Any) -> Any:
        return self.next_tree(state, touch_way, self.config.numWays)

    # Recursively build one hardware victim expression / 递归构造一次硬件受害路表达式
    def victim_tree(self, state: Any, tree_ways: int) -> Any:
        if isinstance(state, int):
            state = Const(state, max(1, tree_ways - 1))
        if tree_ways <= 1:
            return Const(0, 1)
        if tree_ways == 2:
            return state[0]
        bits = ceil_log2(tree_ways)
        right_ways = 1 << (bits - 1)
        left_ways = tree_ways - right_ways
        right_width = right_ways - 1
        left_width = left_ways - 1
        root = state[right_width + left_width]
        right_state = self.state_slice(state, 0, right_width)
        left_state = self.state_slice(state, right_width, left_width)
        right_victim = self.victim_tree(right_state, right_ways)
        if left_ways > 1:
            left_victim = self.victim_tree(left_state, left_ways)
            chosen = Mux(root, left_victim, right_victim)
        else:
            chosen = Mux(root, Const(0, 1), right_victim)
        return Cat(chosen, root)

    # Expose the Rocket-Chip victim name / 暴露 Rocket-Chip 受害路名称
    def get_replace_way(self, state: Any) -> Any:
        return self.victim_tree(state, self.config.numWays)

    # Elaborate folded touches and victim decode / 展开折叠触碰与受害路译码
    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        if self.config.fixedTouchWays:
            for index, bits in enumerate(self.touches_bits):
                module.d.comb += bits.eq(index)
        folded = self.state
        for valid, bits in zip(self.touches_valid, self.touches_bits):
            folded = Mux(valid, self.next_tree(folded, bits, self.config.numWays), folded)
        module.d.comb += [
            self.nextState.eq(folded),
            self.victim.eq(self.victim_tree(self.state, self.config.numWays)),
        ]
        return module


# Explicit V2 policy surface / 显式 V2 策略表面
class PseudoLRU(PlruStateGen):
    """Named PseudoLRU policy adapter. / 具名伪 LRU 策略适配器。"""

    # Construct a PseudoLRU policy with source-style arguments / 用源风格参数构造伪 LRU 策略
    def __init__(self, n_ways: int = 4, access_size: int = 1) -> None:
        super().__init__(PlruStateGenConfig(numWays=n_ways, accessSize=access_size))


# Public Adapter / 公共适配器
# Export deterministic Verilog for the configured combinational policy. / 导出配置化组合策略的确定性 Verilog。
def build_verilog(configuration, injected_dependencies):
    del injected_dependencies
    from amaranth.back import verilog

    config = normalize_configuration(configuration)
    top = PlruStateGen(config)
    ports = [top.state, *top.touches_valid, *top.touches_bits,
             top.nextState, top.victim]
    return verilog.convert(top, name="PlruStateGen", ports=ports, emit_src=False)


# Direct Entry / 直接入口
# Print the default generated policy for command-line inspection. / 打印默认生成策略供命令行检查。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
