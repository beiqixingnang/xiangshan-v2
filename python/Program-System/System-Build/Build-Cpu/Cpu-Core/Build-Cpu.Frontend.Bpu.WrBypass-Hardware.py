"""V2 frontend write-bypass CAM with pseudo-LRU replacement.
V2 前端带伪 LRU 替换的写旁路 CAM。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amaranth import Array, ClockDomain, Elaboratable, Mux, Module, Signal


# Module Contract
# ---------------------------------------------------------------------------
# WrBypass keeps recently written predictor rows in a small indexed CAM and
# exposes valid per-way data for same-cycle table read/write bypassing.
# WrBypass 在小型索引 CAM 中保存最近写入的预测器行，并输出逐路有效数据。
__all__ = [
    "WrBypassConfig",
    "WrBypass",
    "plru_victim_reference",
    "plru_next_reference",
    "build_verilog",
    "main",
]


# Configuration
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class WrBypassConfig:
    """Geometry of one V2 WrBypass specialization. / V2 WrBypass 特化几何。"""

    num_entries: int = 8
    idx_width: int = 9
    data_width: int = 3
    num_ways: int = 1
    tag_width: int = 0

    # Validate the finite CAM geometry. / 校验有限 CAM 几何参数。
    def __post_init__(self) -> None:
        if self.num_entries < 2 or self.num_entries & (self.num_entries - 1):
            raise ValueError("num_entries must be a power of two >= 2")
        if self.idx_width < 1 or self.data_width < 1:
            raise ValueError("idx_width and data_width must be positive")
        if self.num_ways < 1 or self.tag_width < 0:
            raise ValueError("num_ways must be positive and tag_width non-negative")


# Pure reference equations are intentionally public for deterministic direct
# checks and for documenting Rocket-Chip PseudoLRU bit orientation.
# 公开纯参考方程用于确定性 direct 检查并记录 Rocket-Chip PseudoLRU 位方向。


# Compute the V2 PLRU victim for a power-of-two tree. / 计算二次幂树的 V2 PLRU 受害路。
def plru_victim_reference(state: int, num_entries: int = 8) -> int:
    """Return the encoded oldest way. / 返回编码后的最老路。"""

    if num_entries == 2:
        return state & 1
    half = num_entries // 2
    root = (state >> (num_entries - 2)) & 1
    left_state = (state >> (half - 1)) & ((1 << (half - 1)) - 1)
    right_state = state & ((1 << (half - 1)) - 1)
    child = plru_victim_reference(left_state if root else right_state, half)
    return (root << (num_entries.bit_length() - 1 - 1)) | child


# Compute the V2 PLRU next state for a touched way. / 计算触碰某路后的 V2 PLRU 状态。
def plru_next_reference(state: int, way: int, num_entries: int = 8) -> int:
    """Return the packed next tree state. / 返回打包后的下一棵树状态。"""

    if num_entries == 2:
        return (~way) & 1
    half = num_entries // 2
    root_bit = num_entries - 2
    set_left_older = 1 ^ ((way >> (num_entries.bit_length() - 2)) & 1)
    subtree_bits = half - 1
    left_state = (state >> subtree_bits) & ((1 << subtree_bits) - 1)
    right_state = state & ((1 << subtree_bits) - 1)
    if set_left_older:
        left_next = left_state
        right_next = plru_next_reference(right_state, way & (half - 1), half)
    else:
        left_next = plru_next_reference(left_state, way & (half - 1), half)
        right_next = right_state
    return (set_left_older << root_bit) | (left_next << subtree_bits) | right_next


# Implementation
# ---------------------------------------------------------------------------
class WrBypass(Elaboratable):
    """Indexed write-bypass CAM and shared PLRU state. / 索引写旁路 CAM 与共享 PLRU 状态。"""

    # Construct exact V2 clock, reset, write, and hit ports. / 构造精确 V2 时钟、复位、写入及命中端口。
    def __init__(self, configuration: WrBypassConfig = WrBypassConfig()) -> None:
        self.configuration = configuration
        c = configuration
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.clock_domain = ClockDomain("sync", async_reset=True)
        self.clock_domain.clk = self.clock
        self.clock_domain.rst = self.reset
        self.wen = Signal(name="io_wen")
        self.write_idx = Signal(c.idx_width, name="io_write_idx")
        self.write_tag = Signal(c.tag_width, name="io_write_tag") if c.tag_width else None
        self.write_data = [
            Signal(c.data_width, name=f"io_write_data_{way}")
            for way in range(c.num_ways)
        ]
        self.write_way_mask = (
            [Signal(name=f"io_write_way_mask_{way}") for way in range(c.num_ways)]
            if c.num_ways > 1
            else None
        )
        self.hit = Signal(name="io_hit")
        self.hit_data_valid = [
            Signal(name=f"io_hit_data_{way}_valid") for way in range(c.num_ways)
        ]
        self.hit_data_bits = [
            Signal(c.data_width, name=f"io_hit_data_{way}_bits")
            for way in range(c.num_ways)
        ]

    # Build CAM compares, data muxes, valid state, and PLRU updates.
    # 构造 CAM 比较、数据复用、有效状态及 PLRU 更新逻辑。
    def elaborate(self, platform) -> Module:
        del platform
        # The branch API is a generated context manager in Amaranth; type it
        # locally while retaining the exact Module object at runtime.
        m: Any = Module()
        m.domains += self.clock_domain
        c = self.configuration
        entry_bits = max(1, (c.num_entries - 1).bit_length())
        state_bits = max(1, c.num_entries - 1)

        # CAM tags intentionally have no reset, matching IndexableCAMTemplate;
        # ever_written gates all observable comparisons until a real enqueue.
        # CAM 标签不复位，与 IndexableCAMTemplate 一致；ever_written 在实际入队前屏蔽比较。
        idx_store = Array(
            Signal(c.idx_width, name=f"idx_store_{entry}")
            for entry in range(c.num_entries)
        )
        tag_store = (
            Array(
                Signal(c.tag_width, name=f"tag_store_{entry}")
                for entry in range(c.num_entries)
            )
            if c.tag_width
            else None
        )
        data_store = [
            Array(
                Signal(c.data_width, name=f"data_store_{way}_{entry}")
                for entry in range(c.num_entries)
            )
            for way in range(c.num_ways)
        ]
        valids = [
            [
                Signal(name=f"valid_{way}_{entry}", reset=0)
                for entry in range(c.num_entries)
            ]
            for way in range(c.num_ways)
        ]
        ever_written = [
            Signal(name=f"ever_written_{entry}", reset=0)
            for entry in range(c.num_entries)
        ]
        state_reg = Signal(state_bits, name="state_reg", reset=0)

        # Form one-hot CAM hits and a deterministic one-hot index reduction.
        # 形成独热 CAM 命中，并确定性归约为索引。
        hits = []
        for entry in range(c.num_entries):
            same_idx = self.write_idx == idx_store[entry]
            same_tag = 1 if tag_store is None else self.write_tag == tag_store[entry]
            hits.append(same_idx & same_tag & ever_written[entry])
        hit_expr = hits[0]
        for entry in range(1, c.num_entries):
            hit_expr = hit_expr | hits[entry]
        hit_idx = 0
        for entry in range(c.num_entries - 1, -1, -1):
            hit_idx = Mux(hits[entry], entry, hit_idx)
        enq_idx = self.plru_victim_expr(state_reg, c.num_entries)
        selected_idx = Mux(hit_expr, hit_idx, enq_idx)
        m.d.comb += self.hit.eq(hit_expr)

        for way in range(c.num_ways):
            valid_expr = hits[0] & valids[way][0]
            bits_expr = data_store[way][0]
            for entry in range(1, c.num_entries):
                valid_expr = valid_expr | (hits[entry] & valids[way][entry])
                bits_expr = Mux(hit_idx == entry, data_store[way][entry], bits_expr)
            m.d.comb += [
                self.hit_data_valid[way].eq(valid_expr),
                self.hit_data_bits[way].eq(bits_expr),
            ]

        # Write-through data and CAM insertion happen on every enabled write.
        # 每次使能写入都执行数据写穿与 CAM 插入。
        with m.If(self.wen):
            for way in range(c.num_ways):
                write_enable = (
                    1 if self.write_way_mask is None else self.write_way_mask[way]
                )
                with m.If(write_enable):
                    for entry in range(c.num_entries):
                        with m.If(selected_idx == entry):
                            m.d.sync += data_store[way][entry].eq(self.write_data[way])
            with m.If(~hit_expr):
                for entry in range(c.num_entries):
                    with m.If(enq_idx == entry):
                        m.d.sync += idx_store[entry].eq(self.write_idx)
                        if tag_store is not None:
                            m.d.sync += tag_store[entry].eq(self.write_tag)

            # Hit writes only enable selected way(s); misses clear then set mask.
            # 命中写仅置位选中路；未命中先清零再按掩码置位。
            for entry in range(c.num_entries):
                with m.If(hit_expr & (hit_idx == entry)):
                    for way in range(c.num_ways):
                        way_enable = (
                            1 if self.write_way_mask is None else self.write_way_mask[way]
                        )
                        with m.If(way_enable):
                            m.d.sync += valids[way][entry].eq(1)
                with m.Elif(~hit_expr & (enq_idx == entry)):
                    m.d.sync += ever_written[entry].eq(1)
                    for way in range(c.num_ways):
                        way_enable = (
                            1 if self.write_way_mask is None else self.write_way_mask[way]
                        )
                        m.d.sync += valids[way][entry].eq(way_enable)

            m.d.sync += state_reg.eq(
                self.plru_next_expr(state_reg, selected_idx, c.num_entries)
            )

        return m

    # Return a combinational PLRU victim expression for a tree state.
    # 返回树状态对应的组合 PLRU 受害路表达式。
    def plru_victim_expr(self, state, num_entries: int):
        if num_entries == 2:
            return state[0]
        half = num_entries // 2
        root = state[num_entries - 2]
        left_state = state[half - 1 : num_entries - 2]
        right_state = state[0 : half - 1]
        left_child = self.plru_victim_expr(left_state, half)
        right_child = self.plru_victim_expr(right_state, half)
        return (root << (num_entries.bit_length() - 2)) | Mux(root, left_child, right_child)

    # Return a combinational PLRU next-state expression for a touched way.
    # 返回触碰某路后的组合 PLRU 下一状态表达式。
    def plru_next_expr(self, state, way, num_entries: int):
        if num_entries == 2:
            return ~way[0]
        half = num_entries // 2
        root_index = num_entries.bit_length() - 2
        set_left_older = ~way[root_index]
        left_state = state[half - 1 : num_entries - 2]
        right_state = state[0 : half - 1]
        child_way = way[:root_index]
        left_next = Mux(
            set_left_older,
            left_state,
            self.plru_next_expr(left_state, child_way, half),
        )
        right_next = Mux(
            set_left_older,
            self.plru_next_expr(right_state, child_way, half),
            right_state,
        )
        from amaranth import Cat

        return Cat(right_next, left_next, set_left_older)


# Public Adapter
# ---------------------------------------------------------------------------
# Emit one deterministic WrBypass specialization at the final Build path.
# 在最终 Build 路径导出一个确定性的 WrBypass 特化。


# Build standalone Verilog with the exact V2 public port names.
# 使用精确 V2 公共端口名构建独立 Verilog。
def build_verilog(configuration, injected_dependencies):
    """Return generated WrBypass RTL. / 返回生成的 WrBypass RTL。"""

    del injected_dependencies
    from amaranth.back import verilog

    if isinstance(configuration, WrBypassConfig):
        config = configuration
    elif isinstance(configuration, dict):
        config = WrBypassConfig(
            num_entries=int(configuration.get("num_entries", 8)),
            idx_width=int(configuration.get("idx_width", 9)),
            data_width=int(configuration.get("data_width", 3)),
            num_ways=int(configuration.get("num_ways", 1)),
            tag_width=int(configuration.get("tag_width", 0)),
        )
    else:
        config = WrBypassConfig()
    top = WrBypass(config)
    ports = [top.clock, top.reset, top.wen, top.write_idx]
    if top.write_tag is not None:
        ports.append(top.write_tag)
    ports += top.write_data
    if top.write_way_mask is not None:
        ports += top.write_way_mask
    ports += [top.hit, *top.hit_data_valid, *top.hit_data_bits]
    return verilog.convert(top, ports=ports, name="WrBypass")


# Direct Entry
# ---------------------------------------------------------------------------
# Print the default standalone RTL for reproducible command-line smoke tests.
# 打印默认独立 RTL 以支持可复现命令行冒烟测试。


# Print generated default RTL. / 打印生成的默认 RTL。
def main() -> None:
    """Print default WrBypass Verilog. / 打印默认 WrBypass Verilog。"""

    print(build_verilog(None, None))


if __name__ == "__main__":
    main()
