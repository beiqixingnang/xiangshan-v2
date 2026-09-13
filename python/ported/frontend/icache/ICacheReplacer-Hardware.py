"""XiangShan ICache replacer rewritten in amaranth.
香山 ICache 替换器（双端口 set-PLRU，touch 与 victim 选择）的 amaranth 重写。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from amaranth import Array, Elaboratable, Module, Mux, Signal
from amaranth import Cat


# Module Contract
# ---------------------------------------------------------------------------
# Public symbols:
#   - ReplacerConfig : geometry config / 几何配置
#   - ICacheReplacer : dual-instance replacement policy unit (set PLRU)
# Ports:
#   touch_req_valid[2] / v_set_idx[2] / way[2] : hit updates from mainPipe
#   victim_req_valid / v_set_idx               : victim query from missUnit
#   victim_resp_way                            : chosen victim way (comb)
# Contract: two policy instances, selected by vSetIdx(0) (set interleaving);
# the victim query result is registered and touched back the next cycle.
__all__ = ["ReplacerConfig", "ICacheReplacer"]


# Configuration
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ReplacerConfig:
    n_sets: int = 256
    n_ways: int = 4
    idx_bits: int = 8
    way_bits: int = 2
    port_number: int = 2
    policy: str = "setplru"


# Implementation
# ---------------------------------------------------------------------------
class SetPlruState(Elaboratable):
    """4-way set-PLRU tree state for half the sets. / 半组集合的 4 路 PLRU 树状态。"""

    # construct ports / 构造端口
    def __init__(self, c: ReplacerConfig) -> None:
        self.c = c
        self.half_sets = c.n_sets // c.port_number
        self.touch_valid = Signal(name="touch_valid")
        self.touch_set = Signal(c.idx_bits - 1, name="touch_set")
        self.touch_way = Signal(c.way_bits, name="touch_way")
        self.victim_set = Signal(c.idx_bits - 1, name="victim_set")
        self.victim_way = Signal(c.way_bits, name="victim_way")
        # victim touch-back ports are driven by the parent replacer / victim 回触端口由父替换器驱动
        self.victim_touch_valid = Signal(name="victim_touch_valid")
        self.victim_touch_set = Signal(c.idx_bits - 1, name="victim_touch_set")
        self.victim_touch_way = Signal(c.way_bits, name="victim_touch_way")

    # PLRU bit update and victim compute / PLRU 位更新与 victim 计算
    def elaborate(self, platform) -> Module:
        m = Module()
        c = self.c
        # 3 PLRU bits per set: [0]=upper pair, [1]=left leaf, [2]=right leaf /
        # 每组 3 个 PLRU 位
        state = Array(Signal(3, name=f"plru_{i}") for i in range(self.half_sets))

        # victim: walk tree taking the "old" direction / victim：沿树取“旧”方向
        cur = state[self.victim_set]
        m.d.comb += self.victim_way.eq(Cat(
            Mux(cur[0], cur[2], cur[1]),  # low bit from leaf / 低位来自叶子
            cur[0],                        # high bit from root / 高位来自根
        ))

        # touch: point bits away from the used way / touch：位指向远离所用 way
        with cast(Any, m.If(self.touch_valid)):
            w = cast(Any, self.touch_way)
            new_bits = Signal(3, name="plru_new")
            target_state = cast(Any, state[self.touch_set])
            m.d.comb += new_bits.eq(Cat(
                ~w[1],
                Mux(w[1], target_state[1], ~w[0]),
                Mux(w[1], ~w[0], target_state[2]),
            ))
            m.d.sync += target_state.eq(new_bits)
        return m


class ICacheReplacer(Elaboratable):
    """Dual-instance replacer with interleaved sets. / 组交错的双实例替换器。"""

    # construct ports / 构造端口
    def __init__(self, cfg: ReplacerConfig | None = None) -> None:
        self.cfg = cfg or ReplacerConfig()
        c = self.cfg
        self.touch_req_valid = [Signal(name=f"t_valid_{p}") for p in range(c.port_number)]
        self.touch_req_v_set_idx = [Signal(c.idx_bits, name=f"t_set_{p}") for p in range(c.port_number)]
        self.touch_req_way = [Signal(c.way_bits, name=f"t_way_{p}") for p in range(c.port_number)]
        self.victim_req_valid = Signal(name="v_valid")
        self.victim_req_v_set_idx = Signal(c.idx_bits, name="v_set")
        self.victim_resp_way = Signal(c.way_bits, name="v_way")

    # route touches and victim query to the two policy instances / 将 touch 与 victim 路由到两个策略实例
    def elaborate(self, platform) -> Module:
        m = Module()
        c = self.cfg
        instances = []
        for p in range(c.port_number):
            inst = SetPlruState(c)
            # victim touch-back ports are explicit SetPlruState members / 使用显式成员连接 victim 回触
            m.submodules[f"replacer_{p}"] = inst
            instances.append(inst)

        # hit touch: the two touch reqs may target either half / 命中 touch：两个请求可能落在任意半组
        for p in range(c.port_number):
            # select by low bit of request p's own set index / 按请求自身组号低位选择
            sel_other = self.touch_req_v_set_idx[p][0]
            # Chisel's Mux(bit, req(1), req(0)) is intentionally shared by
            # both policy instances; the selector comes from each instance's
            # own request index. / 两个策略实例都使用 Mux(bit, req1, req0)，选择位来自各自请求
            hit_valid = Mux(sel_other == 1, self.touch_req_valid[1], self.touch_req_valid[0])
            hit_set = Mux(sel_other == 1,
                          self.touch_req_v_set_idx[1][1:],
                          self.touch_req_v_set_idx[0][1:])
            hit_way = Mux(sel_other == 1, self.touch_req_way[1], self.touch_req_way[0])
            m.d.comb += [
                instances[p].touch_valid.eq(hit_valid | (instances[p].victim_touch_valid)),
                instances[p].touch_set.eq(Mux(instances[p].victim_touch_valid,
                                              instances[p].victim_touch_set, hit_set)),
                instances[p].touch_way.eq(Mux(instances[p].victim_touch_valid,
                                              instances[p].victim_touch_way, hit_way)),
            ]

        # victim query / victim 查询
        for p in range(c.port_number):
            m.d.comb += instances[p].victim_set.eq(self.victim_req_v_set_idx[1:])
        m.d.comb += self.victim_resp_way.eq(
            Mux(self.victim_req_v_set_idx[0], instances[1].victim_way, instances[0].victim_way))

        # touch the victim back next cycle / 下拍回触 victim
        victim_set_reg = Signal(c.idx_bits, name="victim_set_reg")
        victim_way_reg = Signal(c.way_bits, name="victim_way_reg")
        victim_valid_reg = Signal(name="victim_valid_reg")
        with cast(Any, m.If(self.victim_req_valid)):
            m.d.sync += [
                victim_set_reg.eq(self.victim_req_v_set_idx),
                victim_way_reg.eq(self.victim_resp_way),
            ]
        m.d.sync += victim_valid_reg.eq(self.victim_req_valid)
        for p in range(c.port_number):
            m.d.comb += [
                instances[p].victim_touch_valid.eq(victim_valid_reg & (victim_set_reg[0] == p)),
                instances[p].victim_touch_set.eq(victim_set_reg[1:]),
                instances[p].victim_touch_way.eq(victim_way_reg),
            ]
        return m


# Public Adapter
# ---------------------------------------------------------------------------
# build verilog / 生成 Verilog
def build_verilog(configuration=None, injected_dependencies=None,
                  name: str = "ICacheReplacer") -> str:
    """Export the configured replacer as Verilog / 导出配置化替换器 Verilog。"""
    from amaranth.back import verilog

    del injected_dependencies
    if isinstance(configuration, ReplacerConfig):
        top = ICacheReplacer(configuration)
    elif isinstance(configuration, dict):
        top = ICacheReplacer(ReplacerConfig(**configuration))
    else:
        top = ICacheReplacer()
    ports = [top.victim_req_valid, top.victim_req_v_set_idx, top.victim_resp_way]
    ports += top.touch_req_valid + top.touch_req_v_set_idx + top.touch_req_way
    return verilog.convert(top, name=name, ports=ports)


# Direct Entry
# ---------------------------------------------------------------------------
# cli entry to emit verilog / 命令行入口：输出 Verilog
def main() -> None:
    print(build_verilog())


if __name__ == "__main__":
    main()
