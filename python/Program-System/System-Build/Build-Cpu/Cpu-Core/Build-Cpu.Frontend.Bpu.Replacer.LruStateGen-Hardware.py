"""V2 true-LRU state transform and victim decoder. / V2 真 LRU 状态变换与受害路译码器。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amaranth import Cat, Const, Elaboratable, Module, Mux, Signal


# Module Contract / 模块契约
# The packed state uses the Rocket-Chip triangular layout: bit (i,j) is one
# when way j is newer than way i, for 0 <= i < j < numWays.  Every valid touch
# is folded from first to last, exactly as ReplacementPolicy.get_next_state.
# 公共端口为 state、touches_*、nextState、victim；该单元是组合策略变换器。
__all__ = [
    "LruStateGenConfig",
    "LruStateGen",
    "TrueLRU",
    "lru_next_state",
    "lru_victim",
    "build_verilog",
    "main",
]


# Configuration / 配置
@dataclass(frozen=True)
class LruStateGenConfig:
    """Geometry of one V2 TrueLRU policy instance. / 单个 V2 真 LRU 策略实例的几何参数。"""

    numWays: int = 4
    numSets: int = 256
    accessSize: int = 1

    # Validate policy geometry / 校验策略几何参数
    def __post_init__(self) -> None:
        if self.numWays < 1:
            raise ValueError("numWays must be positive")
        if self.numSets < 1:
            raise ValueError("numSets must be positive")
        if self.accessSize < 1:
            raise ValueError("accessSize must be positive")

    @property
    # Return the packed triangular state width / 返回三角矩阵打包状态位宽
    def stateWidth(self) -> int:
        return max(1, self.numWays * (self.numWays - 1) // 2)

    @property
    # Return the encoded way width / 返回路编号编码位宽
    def wayWidth(self) -> int:
        return max(1, (self.numWays - 1).bit_length())


# Normalize adapter configuration mappings / 规范化适配器配置映射
def normalize_configuration(configuration: Any) -> LruStateGenConfig:
    if configuration is None:
        return LruStateGenConfig()
    if isinstance(configuration, LruStateGenConfig):
        return configuration
    if isinstance(configuration, dict):
        values = dict(configuration)
        # Accept source-style spellings at the adapter boundary only.
        for source, target in (("n_ways", "numWays"),
                               ("n_sets", "numSets"),
                               ("access_size", "accessSize")):
            if source in values and target not in values:
                values[target] = values.pop(source)
        return LruStateGenConfig(**values)
    raise TypeError("configuration must be LruStateGenConfig, dict, or None")


# Return one packed pair offset / 返回一对路在打包状态中的偏移
def pair_offset(lower_way: int, upper_way: int, num_ways: int) -> int:
    if not (0 <= lower_way < upper_way < num_ways):
        raise ValueError("pair must satisfy 0 <= lower < upper < num_ways")
    offset = 0
    for row in range(lower_way):
        offset += num_ways - row - 1
    return offset + upper_way - lower_way - 1


# Compute one V2 TrueLRU state transition independently / 独立计算一次 V2 真 LRU 状态变换
def lru_next_state(state: int, touch_way: int, num_ways: int) -> int:
    if num_ways < 1:
        raise ValueError("num_ways must be positive")
    if num_ways == 1:
        return 0
    width = num_ways * (num_ways - 1) // 2
    state &= (1 << width) - 1
    # UIntToOH emits zero for an out-of-range encoded way; in that case the
    # Scala implementation leaves every matrix entry unchanged.
    if not 0 <= touch_way < num_ways:
        return state
    result = state
    for lower in range(num_ways - 1):
        for upper in range(lower + 1, num_ways):
            bit = pair_offset(lower, upper, num_ways)
            if touch_way == lower:
                value = 0
            elif touch_way == upper:
                value = 1
            else:
                value = (state >> bit) & 1
            result = (result & ~(1 << bit)) | (value << bit)
    return result


# Compute the least-recently-used way independently / 独立计算最久未使用路
def lru_victim(state: int, num_ways: int) -> int:
    if num_ways < 1:
        raise ValueError("num_ways must be positive")
    if num_ways == 1:
        return 0
    for candidate in range(num_ways):
        older_than_all = True
        for other in range(num_ways):
            if other == candidate:
                continue
            if candidate < other:
                # Pair bit is one when the higher way is newer.
                newer = (state >> pair_offset(candidate, other, num_ways)) & 1
                older_than_all &= newer == 1
            else:
                newer = (state >> pair_offset(other, candidate, num_ways)) & 1
                older_than_all &= newer == 0
        if older_than_all:
            return candidate
    # OHToUInt on a malformed/non-transitive matrix has an implementation-
    # defined priority; zero is the safe deterministic fallback.
    return 0


# Implementation / 实现
class LruStateGen(Elaboratable):
    """Combinational TrueLRU transform matching Rocket-Chip V2. / 匹配 V2 Rocket-Chip 的组合真 LRU 变换器。"""

    # Construct the state and touch ports / 构造状态与触碰端口
    def __init__(self, configuration: LruStateGenConfig | dict | None = None) -> None:
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

    # Reconstruct source-style triangular rows / 重建源风格三角矩阵行
    def extract_mru_rows(self, state: Any) -> list[Any]:
        rows = []
        offset = 0
        for row in range(self.config.numWays - 1):
            width = self.config.numWays - row - 1
            rows.append(Cat(Const(0, row + 1), state[offset:offset + width]))
            offset += width
        return rows

    # Pack source-style triangular rows / 打包源风格三角矩阵行
    def pack_rows(self, rows: list[Any]) -> Any:
        if self.config.numWays <= 1:
            return Const(0, self.config.stateWidth)
        return Cat(*(rows[row][row + 1:self.config.numWays]
                     for row in range(self.config.numWays - 1)))

    # Build one hardware transition for one touch / 构造一次硬件单触碰变换
    def next_single(self, state: Any, touch_way: Any) -> Any:
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
                current = state[offset]
                bits.append(
                    Mux(
                        touch_way == lower,
                        Const(0),
                        Mux(touch_way == upper, Const(1), current),
                    )
                )
        return Cat(*bits)

    # Expose the Rocket-Chip transition name / 暴露 Rocket-Chip 状态变换名称
    def get_next_state(self, state: Any, touch_way: Any) -> Any:
        return self.next_single(state, touch_way)

    # Decode one hardware victim expression / 解码一次硬件受害路表达式
    def victim_expr(self, state: Any) -> Any:
        config = self.config
        if isinstance(state, int):
            state = Const(state, config.stateWidth)
        if config.numWays == 1:
            return Const(0, config.wayWidth)
        candidates = []
        for candidate in range(config.numWays):
            terms = []
            for other in range(config.numWays):
                if other == candidate:
                    continue
                if candidate < other:
                    terms.append(state[pair_offset(candidate, other, config.numWays)])
                else:
                    terms.append(~state[pair_offset(other, candidate, config.numWays)])
            condition = Const(1)
            for term in terms:
                condition = condition & term
            candidates.append(condition)
        result = Const(0, config.wayWidth)
        for candidate in range(config.numWays - 1, -1, -1):
            result = Mux(candidates[candidate], Const(candidate, config.wayWidth), result)
        return result

    # Expose the Rocket-Chip victim name / 暴露 Rocket-Chip 受害路名称
    def get_replace_way(self, state: Any) -> Any:
        return self.victim_expr(state)

    # Elaborate folded touches and victim decode / 展开折叠触碰与受害路译码
    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        folded = self.state
        for valid, bits in zip(self.touches_valid, self.touches_bits):
            folded = Mux(valid, self.next_single(folded, bits), folded)
        module.d.comb += [
            self.nextState.eq(folded),
            self.victim.eq(self.victim_expr(self.state)),
        ]
        return module


# Explicit V2 policy surface / 显式 V2 策略表面
class TrueLRU(LruStateGen):
    """Named TrueLRU policy adapter. / 具名真 LRU 策略适配器。"""

    # Construct a TrueLRU policy with source-style arguments / 用源风格参数构造真 LRU 策略
    def __init__(self, n_ways: int = 4, access_size: int = 1) -> None:
        super().__init__(LruStateGenConfig(numWays=n_ways, accessSize=access_size))


# Public Adapter / 公共适配器
# Export deterministic Verilog for the configured combinational policy. / 导出配置化组合策略的确定性 Verilog。
def build_verilog(configuration: Any = None, injected_dependencies: Any = None) -> str:
    del injected_dependencies
    from amaranth.back import verilog

    config = normalize_configuration(configuration)
    top = LruStateGen(config)
    ports = [top.state, *top.touches_valid, *top.touches_bits,
             top.nextState, top.victim]
    return verilog.convert(top, name="LruStateGen", ports=ports, emit_src=False)


# Direct Entry / 直接入口
# Print the default generated policy for command-line inspection. / 打印默认生成策略供命令行检查。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
