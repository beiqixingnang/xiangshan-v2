"""V2 circular issue-queue dequeue selector.
V2 循环发射队列出队选择器。
"""

from __future__ import annotations

from dataclasses import dataclass

from amaranth import Const, Elaboratable, Module, Mux, Signal


# =============================================================================
# Module Contract
# =============================================================================
# DeqPolicy.scala selects the first and second requested entries in circular
# scan order; outputs are valid plus one-hot masks.
# DeqPolicy.scala 按循环扫描顺序选择第一、第二个请求项，并输出有效位和独热掩码。
__all__ = ["DeqPolicyConfig", "DeqPolicy", "select_nth", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class DeqPolicyConfig:
    """V2 dequeue geometry. / V2 出队几何配置。"""

    num_entries: int = 16
    num_deq: int = 2

    # Validate entry and port counts. / 校验条目数和端口数。
    def __post_init__(self) -> None:
        if self.num_entries < 1 or self.num_deq < 1:
            raise ValueError("V2 dequeue dimensions must be positive")


# =============================================================================
# Implementation
# =============================================================================
def select_nth(request: int, rank: int, num_entries: int) -> tuple[bool, int]:
    """Return circular rank-th requested bit. / 返回循环第 rank 个请求位。"""

    if rank < 1:
        raise ValueError("rank is one-based")
    request &= (1 << num_entries) - 1
    found = 0
    for index in range(num_entries):
        if request & (1 << index):
            found += 1
            if found == rank:
                return True, 1 << index
    return False, 0


class DeqPolicy(Elaboratable):
    """Combinational circular dequeue policy. / V2 组合循环出队策略。"""

    # Construct request and valid/one-hot outputs. / 构造请求及有效/独热输出。
    def __init__(self, configuration: DeqPolicyConfig = DeqPolicyConfig()) -> None:
        self.configuration = configuration
        c = configuration
        self.request = Signal(c.num_entries, name="io_request")
        self.valid = [Signal(name=f"io_deqSelOHVec_{i}_valid") for i in range(c.num_deq)]
        self.bits = [Signal(c.num_entries, name=f"io_deqSelOHVec_{i}_bits") for i in range(c.num_deq)]

    # Elaborate rank counters and one-hot output equations. / 展开秩计数器和独热输出方程。
    def elaborate(self, platform) -> Module:
        del platform
        m = Module()
        for rank in range(1, self.configuration.num_deq + 1):
            count = Const(0, max(1, (self.configuration.num_entries + 1).bit_length()))
            chosen = Const(0, self.configuration.num_entries)
            valid = Const(0, 1)
            for index in range(self.configuration.num_entries):
                hit = self.request[index] & (count == rank - 1)
                chosen = chosen | Mux(hit, Const(1 << index, self.configuration.num_entries), Const(0, self.configuration.num_entries))
                valid = valid | hit
                count = count + self.request[index]
            m.d.comb += [self.valid[rank - 1].eq(valid), self.bits[rank - 1].eq(chosen)]
        return m


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration=None, injected_dependencies=None) -> str:
    """Emit deterministic DeqPolicy Verilog. / 输出确定性的 DeqPolicy Verilog。"""

    del injected_dependencies
    from amaranth.back import verilog

    top = DeqPolicy(configuration or DeqPolicyConfig())
    return verilog.convert(top, name="DeqPolicy", ports=[top.request, *top.valid, *top.bits])


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    """Print the generated dequeue policy. / 打印生成的出队策略。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
