"""V2 ICache set-associative replacement policy in Amaranth.
香山 V2 指令缓存组相联替换策略的 Amaranth 重写。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amaranth import Array, Cat, ClockDomain, Elaboratable, Module, Mux, Signal


# Module Contract
# ---------------------------------------------------------------------------
# V2 places ICacheReplacer in ICache.scala and instantiates two
# SetAssocLRU(PseudoLRU) policies, one for each interleaved set bank.  Two hit
# touches and one delayed victim touch are retained as separate observations.
COVERED_MODULES = ("ICacheReplacer",)
SOURCE_PATHS = (
    "upstream/src/main/scala/xiangshan/frontend/icache/ICache.scala",
    "upstream/rocket-chip/src/main/scala/util/Replacement.scala",
)
__all__ = [
    "COVERED_MODULES", "SOURCE_PATHS", "ReplacerConfig", "ICacheReplacer",
    "replacer_request_observation", "build_verilog", "main",
]


# Configuration
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ReplacerConfig:
    """Serializable replacement geometry. / 可序列化的替换器几何配置。"""

    n_sets: int = 256
    n_ways: int = 4
    idx_bits: int = 8
    way_bits: int = 2
    port_number: int = 2
    policy: str = "setplru"

    # Validate V2's power-of-two interleaving assumptions. / 校验 V2 的二次幂交错假设。
    def __post_init__(self) -> None:
        if self.n_sets < 2 or self.n_sets & (self.n_sets - 1):
            raise ValueError("n_sets must be a power of two")
        if self.n_ways < 1 or self.n_ways & (self.n_ways - 1):
            raise ValueError("n_ways must be a power of two")
        if self.port_number != 2:
            raise ValueError("V2 ICacheReplacer has exactly two ports")
        if self.n_sets % self.port_number:
            raise ValueError("n_sets must divide evenly across ports")
        if self.idx_bits != self.n_sets.bit_length() - 1:
            raise ValueError("idx_bits must encode n_sets")
        if self.way_bits != max(1, (self.n_ways - 1).bit_length()):
            raise ValueError("way_bits must encode n_ways")
        if self.policy.lower() not in {"setplru", "setlru"}:
            raise ValueError("policy must be setplru or setlru")

    # Return the number of state bits per set. / 返回每组状态位数量。
    @property
    # Return the number of state bits per set. / 返回每组状态位数量。
    def state_bits(self) -> int:
        if self.policy.lower() == "setlru":
            return self.n_ways * (self.n_ways - 1) // 2
        return max(1, self.n_ways - 1)


def replacer_request_observation(v_set_idx: int, request_valid: bool,
                                 n_sets: int = 256, port_number: int = 2) -> dict[str, int]:
    """Return interleaved bank/set routing used by ICacheReplacer. / 返回 ICacheReplacer 的交错 bank/set 路由。"""

    if n_sets < 2 or port_number != 2 or n_sets % port_number:
        raise ValueError("ICacheReplacer requires two evenly interleaved banks")
    index = int(v_set_idx) & (n_sets - 1)
    return {"bank": index & 1, "bank_set": index >> 1, "request_valid": int(bool(request_valid))}


# Implementation
# ---------------------------------------------------------------------------
class SetAssocPolicy(Elaboratable):
    """One interleaved set-bank policy instance. / 一个交错组库策略实例。"""

    # Construct state and observation ports. / 构造状态及观测端口。
    def __init__(self, cfg: ReplacerConfig) -> None:
        self.cfg = cfg
        self.half_sets = cfg.n_sets // cfg.port_number
        self.set_bits = max(1, (self.half_sets - 1).bit_length())
        self.touch_valid = [Signal(name=f"touch_valid_{i}") for i in range(2)]
        self.touch_set = [
            Signal(self.set_bits, name=f"touch_set_{i}") for i in range(2)
        ]
        self.touch_way = [
            Signal(cfg.way_bits, name=f"touch_way_{i}") for i in range(2)
        ]
        self.victim_set = Signal(self.set_bits, name="victim_set")
        self.victim_way = Signal(cfg.way_bits, name="victim_way")

    # Return a PLRU victim expression for one packed tree. / 返回一个打包树的 PLRU victim 表达式。
    def plru_victim_expr(self, state, tree_ways: int, offset: int = 0):
        if tree_ways <= 1:
            return Signal(1, init=0)
        if tree_ways == 2:
            return state[offset]
        right_ways = tree_ways // 2
        left_ways = tree_ways - right_ways
        root = state[offset + tree_ways - 2]
        left = self.plru_victim_expr(state, left_ways, offset + right_ways - 1)
        right = self.plru_victim_expr(state, right_ways, offset)
        child_width = max(1, (right_ways - 1).bit_length())
        del child_width
        return Cat(Mux(root, left, right), root)

    # Return a PLRU next-state expression for one touch. / 返回一次触摸后的 PLRU 状态表达式。
    def plru_next_expr(self, state, touch_way, tree_ways: int, offset: int = 0):
        if tree_ways <= 1:
            return 0
        if tree_ways == 2:
            return ~touch_way[0]
        right_ways = tree_ways // 2
        left_ways = tree_ways - right_ways
        root_new = ~touch_way[tree_ways.bit_length() - 2]
        left_start = offset + right_ways - 1
        left_end = offset + tree_ways - 2
        right_start = offset
        right_end = offset + right_ways - 1
        left_state = state[left_start:left_end]
        right_state = state[right_start:right_end]
        left_touch = touch_way[: max(1, left_ways.bit_length() - 1)]
        right_touch = touch_way[: max(1, right_ways.bit_length() - 1)]
        left_next = self.plru_next_expr(left_state, left_touch, left_ways, 0)
        right_next = self.plru_next_expr(right_state, right_touch, right_ways, 0)
        left_result = Mux(root_new, left_state, left_next)
        right_result = Mux(root_new, right_next, right_state)
        return Cat(right_result, left_result, root_new)

    # Return an LRU victim expression from the triangular relation matrix. / 返回三角关系矩阵对应的 LRU victim 表达式。
    def lru_victim_expr(self, state):
        n = self.cfg.n_ways
        candidates = []
        for candidate in range(n):
            oldest = 1
            bit_index = 0
            for high in range(1, n):
                for low in range(high):
                    relation = state[bit_index]
                    if low == candidate:
                        oldest = oldest & relation
                    elif high == candidate:
                        oldest = oldest & ~relation
                    bit_index += 1
            candidates.append(oldest)
        result = 0
        for index in range(n - 1, -1, -1):
            result = Mux(candidates[index], index, result)
        return result

    # Return an LRU next-state expression for one touch. / 返回一次触摸后的 LRU 状态表达式。
    def lru_next_expr(self, state, touch_way):
        n = self.cfg.n_ways
        terms = []
        bit_index = 0
        for high in range(1, n):
            for low in range(high):
                terms.append(
                    Mux(
                        touch_way == high,
                        1,
                        Mux(touch_way == low, 0, state[bit_index]),
                    )
                )
                bit_index += 1
        return Cat(*terms) if terms else 0

    # Elaborate per-set state updates and combinational victim selection. / 实例化逐组状态更新和组合 victim 选择。
    def elaborate(self, platform) -> Module:
        del platform
        # Keep the runtime Module unchanged; its generated branch API is
        # locally dynamic for static checking purposes.
        m: Any = Module()
        c = self.cfg
        state = Array(
            Signal(c.state_bits, init=0, name=f"state_vec_{index}")
            for index in range(self.half_sets)
        )

        victim_state = state[self.victim_set]
        if c.policy.lower() == "setlru":
            m.d.comb += self.victim_way.eq(self.lru_victim_expr(victim_state))
        else:
            m.d.comb += self.victim_way.eq(self.plru_victim_expr(victim_state, c.n_ways))

        # V2's SetAssocLRU folds valid touches in array order for each set.
        for set_index in range(self.half_sets):
            current = state[set_index]
            next_state = current
            for slot in range(2):
                hit_set = self.touch_set[slot] == set_index
                update_state = (
                    self.lru_next_expr(next_state, self.touch_way[slot])
                    if c.policy.lower() == "setlru"
                    else self.plru_next_expr(next_state, self.touch_way[slot], c.n_ways)
                )
                next_state = Mux(self.touch_valid[slot] & hit_set, update_state, next_state)
            m.d.sync += current.eq(next_state)
        return m


class ICacheReplacer(Elaboratable):
    """Two-bank V2 ICache replacement unit. / 双库 V2 指令缓存替换单元。"""

    # Construct the parent-facing touch and victim ports. / 构造父级 touch 与 victim 端口。
    def __init__(self, cfg: ReplacerConfig | None = None) -> None:
        self.cfg = cfg or ReplacerConfig()
        c = self.cfg
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.touch_req_valid = [Signal(name=f"io_touch_{i}_valid") for i in range(2)]
        self.touch_req_v_set_idx = [
            Signal(c.idx_bits, name=f"io_touch_{i}_bits_vSetIdx") for i in range(2)
        ]
        self.touch_req_way = [
            Signal(c.way_bits, name=f"io_touch_{i}_bits_way") for i in range(2)
        ]
        self.victim_req_valid = Signal(name="io_victim_vSetIdx_valid")
        self.victim_req_v_set_idx = Signal(c.idx_bits, name="io_victim_vSetIdx_bits")
        self.victim_resp_way = Signal(c.way_bits, name="io_victim_way")

    # Return the flattened PLRU victim expression. / 返回扁平化 PLRU victim 表达式。
    def plru_victim_expr(self, state: Any, tree_ways: int, offset: int = 0) -> Any:
        if tree_ways <= 1:
            return 0
        if tree_ways == 2:
            return state[offset]
        right_ways = tree_ways // 2
        left_ways = tree_ways - right_ways
        root = state[offset + tree_ways - 2]
        left = self.plru_victim_expr(state, left_ways, offset + right_ways - 1)
        right = self.plru_victim_expr(state, right_ways, offset)
        return Cat(Mux(root, left, right), root)

    # Return the flattened PLRU next-state expression. / 返回扁平化 PLRU 下一状态表达式。
    def plru_next_expr(self, state: Any, touch_way: Any, tree_ways: int) -> Any:
        if tree_ways <= 1:
            return 0
        if tree_ways == 2:
            return ~touch_way[0]
        right_ways = tree_ways // 2
        left_ways = tree_ways - right_ways
        root_new = ~touch_way[tree_ways.bit_length() - 2]
        left_state = state[right_ways - 1 : tree_ways - 2]
        right_state = state[: right_ways - 1]
        left_touch = touch_way[: max(1, left_ways.bit_length() - 1)]
        right_touch = touch_way[: max(1, right_ways.bit_length() - 1)]
        left_next = self.plru_next_expr(left_state, left_touch, left_ways)
        right_next = self.plru_next_expr(right_state, right_touch, right_ways)
        return Cat(
            Mux(root_new, right_next, right_state),
            Mux(root_new, left_state, left_next),
            root_new,
        )

    # Route interleaved touches and delay victim touch-back by one cycle. / 路由交错 touch，并将 victim touch-back 延迟一个周期。
    def elaborate(self, platform) -> Module:
        del platform
        # Keep the runtime Module unchanged; its generated branch API is
        # locally dynamic for static checking purposes.
        m: Any = Module()
        c = self.cfg
        domain = ClockDomain("sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains += domain
        half_sets = c.n_sets // c.port_number
        states = [
            [
                Signal(
                    c.state_bits,
                    name=(f"state_vec_{index}" if bank == 0 else f"state_vec_1_{index}"),
                )
                for index in range(half_sets)
            ]
            for bank in range(c.port_number)
        ]

        hit_valid: list[Any] = []
        hit_set: list[Any] = []
        hit_way: list[Any] = []
        for bank in range(c.port_number):
            selector = self.touch_req_v_set_idx[bank][0]
            hit_valid.append(Mux(selector, self.touch_req_valid[1], self.touch_req_valid[0]))
            hit_set.append(Mux(
                selector,
                self.touch_req_v_set_idx[1][1:],
                self.touch_req_v_set_idx[0][1:],
            ))
            hit_way.append(Mux(selector, self.touch_req_way[1], self.touch_req_way[0]))

        # Victim output selects the bank using the low set-index bit.
        victim_set = self.victim_req_v_set_idx[1:]
        bank_victims = [
            self.plru_victim_expr(Array(states[bank])[victim_set], c.n_ways)
            for bank in range(c.port_number)
        ]
        m.d.comb += self.victim_resp_way.eq(
            Mux(self.victim_req_v_set_idx[0], bank_victims[1], bank_victims[0])
        )

        victim_set_reg = Signal(c.idx_bits, name="victim_vSetIdx_reg")
        victim_way_reg = Signal(c.way_bits, name="victim_way_reg")
        victim_valid_reg = [
            Signal(name=f"touch_ways_{bank}_1_valid_REG", reset_less=True)
            for bank in range(c.port_number)
        ]
        with m.If(self.victim_req_valid):
            m.d.sync += [
                victim_set_reg.eq(self.victim_req_v_set_idx),
                victim_way_reg.eq(self.victim_resp_way),
            ]
        for valid_reg in victim_valid_reg:
            m.d.sync += valid_reg.eq(self.victim_req_valid)

        for bank in range(c.port_number):
            victim_touch_valid = victim_valid_reg[bank] & (victim_set_reg[0] == bank)
            for set_index, current in enumerate(states[bank]):
                next_state: Any = current
                next_state = Mux(
                    hit_valid[bank] & (hit_set[bank] == set_index),
                    self.plru_next_expr(next_state, hit_way[bank], c.n_ways),
                    next_state,
                )
                next_state = Mux(
                    victim_touch_valid & (victim_set_reg[1:] == set_index),
                    self.plru_next_expr(next_state, victim_way_reg, c.n_ways),
                    next_state,
                )
                m.d.sync += current.eq(next_state)
        return m


# Public Adapter
# ---------------------------------------------------------------------------
# Export a deterministic configured module. / 导出确定性配置模块。
def build_verilog(configuration, injected_dependencies):
    """Return Verilog for the configured replacer. / 返回配置替换器的 Verilog。"""
    from amaranth.back import verilog

    del injected_dependencies
    if isinstance(configuration, ReplacerConfig):
        cfg = configuration
    elif isinstance(configuration, dict):
        cfg = ReplacerConfig(**{key: value for key, value in configuration.items()
                                if key in ReplacerConfig.__dataclass_fields__})
    else:
        cfg = ReplacerConfig()
    top = ICacheReplacer(cfg)
    ports = [top.clock, top.reset, top.victim_req_valid, top.victim_req_v_set_idx, top.victim_resp_way]
    ports += top.touch_req_valid + top.touch_req_v_set_idx + top.touch_req_way
    return verilog.convert(top, name="ICacheReplacer", ports=ports)


# Direct Entry
# ---------------------------------------------------------------------------
# Print the default configured export when invoked directly. / 直接调用时打印默认配置导出结果。
def main() -> None:
    """Print the default Verilog module. / 打印默认 Verilog 模块。"""
    print(build_verilog(None, None))


if __name__ == "__main__":
    main()
