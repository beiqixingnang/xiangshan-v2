"""V2 circular enqueue-slot selector.
V2 循环入队槽选择器。
"""

from __future__ import annotations

from dataclasses import dataclass

from amaranth import Const, Elaboratable, Module, Mux, Signal


# =============================================================================
# Module Contract
# =============================================================================
# SelectOne("circ") emits odd-ranked free slots from low to high and
# even-ranked slots from high to low, while validity is population based.
# SelectOne("circ") 奇数序号从低到高、偶数序号从高到低选择空槽，valid 由人口计数决定。
__all__ = ["EnqPolicyConfig", "EnqPolicy", "select_circular", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class EnqPolicyConfig:
    """Issue-queue entry and enqueue-port geometry. / 发射队列项与入队端口几何。"""

    num_entries: int = 24
    num_enq: int = 2

    # Validate the source IssueBlockParams relationship. / 校验源 IssueBlockParams 关系。
    def __post_init__(self) -> None:
        if self.num_entries < 1 or self.num_enq < 1 or self.num_enq > self.num_entries:
            raise ValueError("num_entries and num_enq are out of range")

    @property
    # Compute the free-slot vector width. / 计算空槽向量位宽。
    def free_slots(self) -> int:
        """Return ``numEntries - numEnq``. / 返回 ``numEntries - numEnq``。"""

        return self.num_entries - self.num_enq


# =============================================================================
# Implementation
# =============================================================================
# Return one circular rank selection in Python for deterministic checking. / 以 Python 返回一个循环序号选择用于确定性检查。
def select_circular(mask: int, num_enq: int, rank: int) -> tuple[bool, int]:
    """Mirror ``CircSelectOne.getNthOH`` exactly. / 精确镜像 ``CircSelectOne.getNthOH``。"""

    if rank < 1 or rank > num_enq:
        raise ValueError("rank is outside the enqueue-port range")
    indices = [index for index in range(mask.bit_length()) if (mask >> index) & 1]
    valid = len(indices) >= rank
    if not valid:
        return False, 0
    if rank & 1:
        index = indices[(rank - 1) // 2]
    else:
        index = indices[-(rank // 2)]
    return True, 1 << index


class EnqPolicy(Elaboratable):
    """Combinational circular selector with V2-compatible ports. / 带 V2 端口的组合循环选择器。"""

    # Construct free-slot and valid/one-hot output ports. / 构造空槽及 valid/独热输出端口。
    def __init__(self, configuration: EnqPolicyConfig = EnqPolicyConfig()) -> None:
        self.configuration = configuration
        width = max(1, configuration.free_slots)
        self.can_enq = Signal(width, name="io_canEnq")
        self.selection_valid = [Signal(name=f"io_enqSelOHVec_{index}_valid")
                                for index in range(configuration.num_enq)]
        self.selection_bits = [Signal(width, name=f"io_enqSelOHVec_{index}_bits")
                               for index in range(configuration.num_enq)]

    # Elaborate the low/high alternating circular rank equations. / 展开低高交替的循环序号方程。
    def elaborate(self, platform) -> Module:
        del platform
        m = Module()
        width = max(1, self.configuration.free_slots)
        available = [self.can_enq[index] for index in range(width)]
        for rank_index in range(self.configuration.num_enq):
            rank = rank_index + 1
            count_width = max(1, (width + 1).bit_length())
            count = Signal(count_width, name=f"count_{rank_index}")
            m.d.comb += count.eq(sum(available, 0))
            m.d.comb += self.selection_valid[rank_index].eq(count >= rank)
            if rank & 1:
                ordinal = (rank + 1) // 2
                ordered = list(range(width))
            else:
                ordinal = rank // 2
                ordered = list(range(width - 1, -1, -1))
            prior = Const(0, count_width) if False else None
            del prior
            chosen = Const(0, width)
            seen = Const(0, count_width)
            # Build a priority chain; each term sees the number of set bits
            # before it in the selected direction.
            # 构造优先链；每项依据选定方向此前的置位数。
            for index in ordered:
                is_choice = available[index] & (seen == (ordinal - 1))
                chosen = Mux(is_choice, 1 << index, chosen)
                seen = seen + available[index]
            m.d.comb += self.selection_bits[rank_index].eq(chosen)
        return m


# =============================================================================
# Public Adapter
# =============================================================================
# Emit deterministic Verilog for the V2 DefaultConfig geometry. / 为 V2 DefaultConfig 几何生成确定性 Verilog。
def build_verilog(configuration=None, injected_dependencies=None) -> str:
    """Build the standalone EnqPolicy module. / 构建独立 EnqPolicy 模块。"""

    del injected_dependencies
    from amaranth.back import verilog

    config = configuration or EnqPolicyConfig()
    top = EnqPolicy(config)
    return verilog.convert(top, name="EnqPolicy",
                           ports=[top.can_enq, *top.selection_valid, *top.selection_bits])


# =============================================================================
# Direct Entry
# =============================================================================
# Print generated selector Verilog. / 打印生成的选择器 Verilog。
def main() -> None:
    """Print the deterministic selector. / 打印确定性选择器。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
