"""V2 per-set replacement policy state bank. / V2 每组替换策略状态寄存器组。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amaranth import (Array, Cat, ClockDomain, ClockSignal, Const,
                      Elaboratable, Module, Mux, ResetSignal, Signal)


# Module Contract / 模块契约
# This module is the explicit Python boundary for Rocket-Chip SetAssocLRU:
# state_vec contains one policy state per set, reads are combinational, and
# valid touches update a set on the active clock edge in input order, and the
# active-high reset is asynchronous as in the generated V2 RegInit closure.  The
# policy is either ``lru`` (TrueLRU triangular state) or ``plru`` (PseudoLRU
# tree state).  Raw read/write ports are retained as named diagnostics and do
# not replace the policy access contract.
# 该模块保留每组状态、组合 victim 读取及按顺序提交的有效触碰。
__all__ = [
    "ReplacerStateConfig",
    "ReplacerState",
    "SetAssocLRU",
    "ReplacerStateGen",
    "policy_next_state",
    "policy_victim",
    "build_verilog",
    "main",
]


# Configuration / 配置
@dataclass(frozen=True)
class ReplacerStateConfig:
    """Geometry and policy selection for SetAssocLRU. / SetAssocLRU 的几何与策略选择。"""

    numSets: int = 64
    numWays: int = 4
    policy: str = "plru"
    accessSize: int = 1
    # An explicit stateBits value is accepted only when it equals the policy
    # width; it makes the old register-bank contract auditable without hiding
    # a geometry mismatch.
    stateBits: int | None = None
    numExtraReadPort: int = 1
    numExtraWritePort: int = 0

    # Validate replacement-bank geometry / 校验替换寄存器组几何参数
    def __post_init__(self) -> None:
        if self.numSets < 1:
            raise ValueError("numSets must be positive")
        if self.numWays < 1:
            raise ValueError("numWays must be positive")
        if self.accessSize < 1:
            raise ValueError("accessSize must be positive")
        if self.numExtraReadPort < 0 or self.numExtraWritePort < 0:
            raise ValueError("extra port counts cannot be negative")
        if self.policy.lower() not in ("lru", "setlru", "plru", "setplru"):
            raise ValueError("policy must be lru/setlru/plru/setplru")
        natural = (self.numWays * (self.numWays - 1) // 2
                   if self.policy.lower() in ("lru", "setlru")
                   else self.numWays - 1)
        if self.stateBits is not None and self.stateBits != max(1, natural):
            raise ValueError("stateBits does not match selected policy width")

    @property
    # Return the normalized policy name / 返回规范化策略名称
    def policyName(self) -> str:
        return "lru" if self.policy.lower() in ("lru", "setlru") else "plru"

    @property
    # Return the packed state width / 返回打包状态位宽
    def stateWidth(self) -> int:
        if self.policyName == "lru":
            return max(1, self.numWays * (self.numWays - 1) // 2)
        return max(1, self.numWays - 1)

    @property
    # Return the set-index width / 返回组索引位宽
    def setWidth(self) -> int:
        return max(1, (self.numSets - 1).bit_length())

    @property
    # Return the encoded way width / 返回路编号编码位宽
    def wayWidth(self) -> int:
        return max(1, (self.numWays - 1).bit_length())


# Normalize adapter configuration mappings / 规范化适配器配置映射
def normalize_configuration(configuration: Any) -> ReplacerStateConfig:
    if configuration is None:
        return ReplacerStateConfig()
    if isinstance(configuration, ReplacerStateConfig):
        return configuration
    if isinstance(configuration, dict):
        values = dict(configuration)
        for source, target in (("n_sets", "numSets"),
                               ("n_ways", "numWays"),
                               ("access_size", "accessSize"),
                               ("state_bits", "stateBits"),
                               ("policy_name", "policy"),
                               ("num_extra_read_port", "numExtraReadPort"),
                               ("num_extra_write_port", "numExtraWritePort")):
            if source in values and target not in values:
                values[target] = values.pop(source)
        return ReplacerStateConfig(**values)
    raise TypeError("configuration must be ReplacerStateConfig, dict, or None")


# Return mathematical ceil(log2(value)) / 返回数学上的 ceil(log2(value))
def ceil_log2(value: int) -> int:
    if value < 1:
        raise ValueError("value must be positive")
    return (value - 1).bit_length()


# Return one packed triangular pair offset / 返回三角矩阵路对偏移
def pair_offset(lower_way: int, upper_way: int, num_ways: int) -> int:
    if not (0 <= lower_way < upper_way < num_ways):
        raise ValueError("pair must satisfy 0 <= lower < upper < num_ways")
    return sum(num_ways - row - 1 for row in range(lower_way)) + upper_way - lower_way - 1


# Compute one integer TrueLRU transition / 计算一次整数真 LRU 状态变换
def true_lru_next(state: int, touch_way: int, num_ways: int) -> int:
    if num_ways < 1:
        raise ValueError("num_ways must be positive")
    if num_ways == 1:
        return 0
    width = num_ways * (num_ways - 1) // 2
    state &= (1 << width) - 1
    if not 0 <= touch_way < num_ways:
        return state
    result = state
    for lower in range(num_ways - 1):
        for upper in range(lower + 1, num_ways):
            bit = pair_offset(lower, upper, num_ways)
            value = (0 if touch_way == lower else
                     1 if touch_way == upper else (state >> bit) & 1)
            result = (result & ~(1 << bit)) | (value << bit)
    return result


# Compute one integer TrueLRU victim / 计算一次整数真 LRU 受害路
def true_lru_victim(state: int, num_ways: int) -> int:
    if num_ways < 1:
        raise ValueError("num_ways must be positive")
    if num_ways == 1:
        return 0
    for candidate in range(num_ways):
        older = True
        for other in range(num_ways):
            if other == candidate:
                continue
            bit = ((state >> pair_offset(candidate, other, num_ways)) & 1
                   if candidate < other else
                   (state >> pair_offset(other, candidate, num_ways)) & 1)
            older &= bit == (1 if candidate < other else 0)
        if older:
            return candidate
    return 0


# Compute one integer PseudoLRU transition / 计算一次整数伪 LRU 状态变换
def pseudo_lru_next(state: int, touch_way: int, num_ways: int) -> int:
    if num_ways < 1:
        raise ValueError("num_ways must be positive")
    if num_ways == 1:
        return 0
    state &= (1 << (num_ways - 1)) - 1

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
            return right_result | (left_result << right_width) | (root << (right_width + left_width))
        right_result = right_next if root else right_state
        return right_result | (root << right_width)

    return recurse(state, touch_way, num_ways)


# Compute one integer PseudoLRU victim / 计算一次整数伪 LRU 受害路
def pseudo_lru_victim(state: int, num_ways: int) -> int:
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
        child = (recurse(left_state, left_ways) if root and left_ways > 1
                 else 0 if root else recurse(right_state, right_ways))
        return child | (root << (bits - 1))

    return recurse(state, num_ways)


# Compute a policy transition independently / 独立计算策略状态变换
def policy_next_state(state: int, touch_way: int, num_ways: int, policy: str) -> int:
    if policy.lower() in ("lru", "setlru"):
        return true_lru_next(state, touch_way, num_ways)
    if policy.lower() in ("plru", "setplru"):
        return pseudo_lru_next(state, touch_way, num_ways)
    raise ValueError("policy must be lru/setlru/plru/setplru")


# Compute a policy victim independently / 独立计算策略受害路
def policy_victim(state: int, num_ways: int, policy: str) -> int:
    if policy.lower() in ("lru", "setlru"):
        return true_lru_victim(state, num_ways)
    if policy.lower() in ("plru", "setplru"):
        return pseudo_lru_victim(state, num_ways)
    raise ValueError("policy must be lru/setlru/plru/setplru")


# Implementation / 实现
class ReplacerState(Elaboratable):
    """Clocked SetAssocLRU state bank with explicit observation ports. / 带显式观测端口的时钟式 SetAssocLRU 状态组。"""

    # Construct policy, access, and diagnostic ports / 构造策略、访问与诊断端口
    def __init__(self, configuration: ReplacerStateConfig | dict | None = None) -> None:
        config = normalize_configuration(configuration)
        self.config = config
        self.cfg = config
        self.nBits = config.stateWidth
        self.perSet = True
        self.clock = ClockSignal("sync")
        self.reset = ResetSignal("sync")

        self.state_vec = [
            Signal(config.stateWidth, name=f"state_vec_{index}", reset=0)
            for index in range(config.numSets)
        ]
        self.states = self.state_vec

        self.access_sets = [
            Signal(config.setWidth, name=f"io_access_{index}_set")
            for index in range(config.accessSize)
        ]
        self.access_valid = [
            Signal(name=f"io_access_{index}_valid")
            for index in range(config.accessSize)
        ]
        self.access_ways = [
            Signal(config.wayWidth, name=f"io_access_{index}_way")
            for index in range(config.accessSize)
        ]
        self.touches = [
            {"valid": valid, "set": set_index, "way": way}
            for valid, set_index, way in zip(self.access_valid,
                                             self.access_sets,
                                             self.access_ways)
        ]
        self.touch_valid = self.access_valid[0]
        self.touch_set = self.access_sets[0]
        self.touch_way = self.access_ways[0]

        self.victim_set = Signal(config.setWidth, name="io_victim_set")
        self.victim_way = Signal(config.wayWidth, name="io_victim_way")
        self.way = self.victim_way
        self.state_read = Signal(config.stateWidth, name="io_state_read")
        self.state_next = Signal(config.stateWidth, name="io_state_next")

        # Explicit diagnostic register-bank ports retained from the candidate
        # surface; they observe/write the same policy state vector.
        read_count = 2 + config.numExtraReadPort
        write_count = 2 + config.numExtraWritePort
        self.read_setIdx = [
            Signal(config.setWidth, name=f"io_read_{index}_setIdx")
            for index in range(read_count)
        ]
        self.read_state = [
            Signal(config.stateWidth, name=f"io_read_{index}_state")
            for index in range(read_count)
        ]
        self.write_valid = [
            Signal(name=f"io_write_{index}_valid")
            for index in range(write_count)
        ]
        self.write_setIdx = [
            Signal(config.setWidth, name=f"io_write_{index}_bits_setIdx")
            for index in range(write_count)
        ]
        self.write_state = [
            Signal(config.stateWidth, name=f"io_write_{index}_bits_state")
            for index in range(write_count)
        ]

    # Return a selected state with deterministic out-of-range fallback / 返回选定状态并确定性处理越界索引
    def select_state(self, index: Any) -> Any:
        # Array indexing emits a balanced mux and returns zero for an encoded
        # index outside numSets, matching a bounded Vec access.
        return Array(self.state_vec)[index]

    # Build one hardware TrueLRU transition / 构造一次硬件真 LRU 状态变换
    def true_lru_next_expr(self, state: Any, touch_way: Any) -> Any:
        config = self.config
        if isinstance(state, int):
            state = Const(state, config.stateWidth)
        if isinstance(touch_way, int):
            touch_way = Const(touch_way, config.wayWidth)
        if config.numWays == 1:
            return Const(0, config.stateWidth)
        bits = []
        for lower in range(config.numWays - 1):
            for upper in range(lower + 1, config.numWays):
                offset = pair_offset(lower, upper, config.numWays)
                bits.append(Mux(touch_way == lower, Const(0),
                                Mux(touch_way == upper, Const(1), state[offset])))
        return Cat(*bits)

    # Build one hardware PseudoLRU transition recursively / 递归构造一次硬件伪 LRU 状态变换
    def pseudo_lru_next_tree(self, state: Any, touch_way: Any, tree_ways: int) -> Any:
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
        right_state = state[:right_width]
        left_state = state[right_width:right_width + left_width]
        right_touch = touch_way[:ceil_log2(right_ways)]
        right_next = self.pseudo_lru_next_tree(right_state, right_touch, right_ways)
        if left_ways > 1:
            left_touch = touch_way[:ceil_log2(left_ways)]
            left_next = self.pseudo_lru_next_tree(left_state, left_touch, left_ways)
            return Cat(Mux(root, right_next, right_state),
                       Mux(root, left_state, left_next), root)
        return Cat(Mux(root, right_next, right_state), root)

    # Build one hardware policy transition / 构造一次硬件策略状态变换
    def next_state_for_touch(self, state: Any, touch_way: Any) -> Any:
        if self.config.policyName == "lru":
            return self.true_lru_next_expr(state, touch_way)
        return self.pseudo_lru_next_tree(state, touch_way, self.config.numWays)

    # Expose the Rocket-Chip transition name / 暴露 Rocket-Chip 状态变换名称
    def get_next_state(self, state: Any, touch_way: Any) -> Any:
        return self.next_state_for_touch(state, touch_way)

    # Build one hardware TrueLRU victim expression / 构造一次硬件真 LRU 受害路表达式
    def true_lru_victim_expr(self, state: Any) -> Any:
        config = self.config
        if isinstance(state, int):
            state = Const(state, config.stateWidth)
        if config.numWays == 1:
            return Const(0, config.wayWidth)
        candidates = []
        for candidate in range(config.numWays):
            condition = Const(1)
            for other in range(config.numWays):
                if other == candidate:
                    continue
                if candidate < other:
                    term = state[pair_offset(candidate, other, config.numWays)]
                else:
                    term = ~state[pair_offset(other, candidate, config.numWays)]
                condition = condition & term
            candidates.append(condition)
        result = Const(0, config.wayWidth)
        for candidate in range(config.numWays - 1, -1, -1):
            result = Mux(candidates[candidate], Const(candidate, config.wayWidth), result)
        return result

    # Build one hardware PseudoLRU victim expression recursively / 递归构造一次硬件伪 LRU 受害路表达式
    def pseudo_lru_victim_tree(self, state: Any, tree_ways: int) -> Any:
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
        right_state = state[:right_width]
        left_state = state[right_width:right_width + left_width]
        right_victim = self.pseudo_lru_victim_tree(right_state, right_ways)
        if left_ways > 1:
            left_victim = self.pseudo_lru_victim_tree(left_state, left_ways)
            return Cat(Mux(root, left_victim, right_victim), root)
        return Cat(Mux(root, Const(0, 1), right_victim), root)

    # Build one hardware policy victim expression / 构造一次硬件策略受害路表达式
    def victim_for_state(self, state: Any) -> Any:
        if self.config.policyName == "lru":
            return self.true_lru_victim_expr(state)
        return self.pseudo_lru_victim_tree(state, self.config.numWays)

    # Expose the Rocket-Chip victim name / 暴露 Rocket-Chip 受害路名称
    def get_replace_way(self, state: Any) -> Any:
        return self.victim_for_state(state)

    # Elaborate state reads, ordered updates, and victim output / 展开状态读取、有序更新与受害路输出
    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        module.domains.sync = ClockDomain(async_reset=True)
        selected = self.select_state(self.victim_set)
        module.d.comb += [
            self.state_read.eq(selected),
            self.state_next.eq(selected),
            self.victim_way.eq(self.victim_for_state(selected)),
        ]
        for index, read_index in enumerate(self.read_setIdx):
            module.d.comb += self.read_state[index].eq(self.select_state(read_index))

        for set_index, current in enumerate(self.state_vec):
            next_value = current
            for valid, set_signal, way_signal in zip(self.access_valid,
                                                      self.access_sets,
                                                      self.access_ways):
                condition = valid & (set_signal == set_index)
                next_value = Mux(condition,
                                 self.next_state_for_touch(next_value, way_signal),
                                 next_value)
            # Diagnostic writes are applied after policy touches; later ports
            # override earlier ports, matching ordered Chisel assignments.
            for valid, set_signal, state_signal in zip(self.write_valid,
                                                       self.write_setIdx,
                                                       self.write_state):
                condition = valid & (set_signal == set_index)
                next_value = Mux(condition, state_signal, next_value)
            module.d.sync += current.eq(next_value)
        return module


# Explicit V2 SetAssocLRU adapter / 显式 V2 SetAssocLRU 适配器
class SetAssocLRU(ReplacerState):
    """Named set-associative LRU policy boundary. / 具名组相联 LRU 策略边界。"""

    # Construct a set-associative policy from source-style arguments / 用源风格参数构造组相联策略
    def __init__(self, n_sets: int = 64, n_ways: int = 4,
                 policy: str = "lru", access_size: int = 1) -> None:
        super().__init__(ReplacerStateConfig(numSets=n_sets, numWays=n_ways,
                                             policy=policy, accessSize=access_size))


# Explicit candidate-name adapter / 显式候选名称适配器
class ReplacerStateGen(ReplacerState):
    """Source-traceable ReplacerState generator. / 可追溯源路径的 ReplacerState 生成器。"""

    # Construct the generator with the regular configuration / 用标准配置构造生成器
    def __init__(self, configuration: ReplacerStateConfig | dict | None = None) -> None:
        super().__init__(configuration)


# Public Adapter / 公共适配器
# Export deterministic Verilog for the configured sequential policy bank. / 导出配置化时序策略组的确定性 Verilog。
def build_verilog(configuration: Any = None, injected_dependencies: Any = None) -> str:
    del injected_dependencies
    from amaranth.back import verilog

    config = normalize_configuration(configuration)
    top = ReplacerState(config)
    ports = [
        top.clock,
        top.reset,
        *top.access_sets,
        *top.access_valid,
        *top.access_ways,
        top.victim_set,
        top.victim_way,
        top.state_read,
        top.state_next,
        *top.read_setIdx,
        *top.read_state,
        *top.write_valid,
        *top.write_setIdx,
        *top.write_state,
    ]
    return verilog.convert(top, name="ReplacerState", ports=ports, emit_src=False)


# Direct Entry / 直接入口
# Print the default generated policy for command-line inspection. / 打印默认生成策略供命令行检查。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
