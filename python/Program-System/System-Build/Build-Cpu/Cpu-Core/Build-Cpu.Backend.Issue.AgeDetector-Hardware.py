"""V2 issue-queue age matrix and oldest-issue selector.
V2 发射队列年龄矩阵与最老项选择器。
"""

from __future__ import annotations

from dataclasses import dataclass

from amaranth import ClockDomain, Const, Elaboratable, Module, Mux, Signal


# =============================================================================
# Module Contract
# =============================================================================
# AgeDetector tracks pairwise enqueue age, updates the upper triangular matrix
# on each enqueue, and emits one-hot oldest eligible entries per dequeue port.
# AgeDetector 跟踪成对入队年龄，每次入队更新上三角矩阵，并为每个出队端口输出最老可发射项。
__all__ = ["AgeDetectorConfig", "AgeDetector", "age_select_reference", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class AgeDetectorConfig:
    """Age matrix geometry. / 年龄矩阵几何配置。"""

    num_entries: int = 6
    num_enq: int = 2
    num_deq: int = 4

    # Validate matrix and port dimensions. / 校验矩阵及端口尺寸。
    def __post_init__(self) -> None:
        if self.num_entries < 1 or self.num_enq < 1 or self.num_deq < 1:
            raise ValueError("all dimensions must be positive")


# =============================================================================
# Implementation
# =============================================================================
# Compute oldest one-hot selections from an age matrix. / 根据年龄矩阵计算最老项独热选择。
def age_select_reference(age: list[list[bool]], can_issue: list[int]) -> list[int]:
    """Return one selection mask per dequeue port. / 返回每个出队端口的选择掩码。"""

    n = len(age)
    outputs: list[int] = []
    for eligible in can_issue:
        selected = 0
        for row in range(n):
            if not ((eligible >> row) & 1):
                continue
            oldest = True
            for col in range(n):
                relation = True if row == col else (age[row][col] if row < col else not age[col][row])
                if ((eligible >> col) & 1) and not relation:
                    oldest = False
                    break
            if oldest:
                selected |= 1 << row
        outputs.append(selected)
    return outputs


class AgeDetector(Elaboratable):
    """Registered upper-triangular age detector. / 寄存式上三角年龄检测器。"""

    # Construct matrix, enqueue, issue, and output ports. / 构造矩阵、入队、发射及输出端口。
    def __init__(self, configuration: AgeDetectorConfig = AgeDetectorConfig()) -> None:
        self.configuration = configuration
        c = configuration
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.clock_domain = ClockDomain("sync", async_reset=True)
        self.clock_domain.clk = self.clock
        self.clock_domain.rst = self.reset
        self.enq = [Signal(c.num_entries, name=f"io_enq_{index}") for index in range(c.num_enq)]
        self.can_issue = [Signal(c.num_entries, name=f"io_canIssue_{index}") for index in range(c.num_deq)]
        self.out = [Signal(c.num_entries, name=f"io_out_{index}") for index in range(c.num_deq)]

    # Elaborate age update and oldest-eligible equations. / 展开年龄更新与最老可发射方程。
    def elaborate(self, platform) -> Module:
        del platform
        m = Module()
        m.domains += self.clock_domain
        c = self.configuration
        age = [[Signal(reset=0, name=f"age_{row}_{col}") if row < col else None
                for col in range(c.num_entries)] for row in range(c.num_entries)]

        # Enqueue presence for each entry and port-prefix presence. / 计算每项入队及端口前缀入队标志。
        entry_enq = [None] * c.num_entries
        for entry in range(c.num_entries):
            present = Const(0)
            for port in range(c.num_enq):
                present = present | self.enq[port][entry]
            entry_enq[entry] = present

        # Update upper matrix entries exactly as AgeDetector.scala. / 按 AgeDetector.scala 精确更新上三角矩阵。
        for row in range(c.num_entries):
            for col in range(row + 1, c.num_entries):
                old = age[row][col]
                both_terms = Const(0)
                for port in range(c.num_enq):
                    earlier_ports = Const(0)
                    for prior_port in range(port):
                        earlier_ports = earlier_ports | self.enq[prior_port][col]
                    both_terms = both_terms | (self.enq[port][row] & earlier_ports)
                both_value = ~both_terms
                age_value = Mux(
                    entry_enq[row] & entry_enq[col],
                    both_value,
                    Mux(entry_enq[row], 0, Mux(entry_enq[col], 1, old)),
                )
                m.d.sync += old.eq(age_value)

        # Emit oldest eligible one-hot masks for each dequeue port. / 为每个出队端口输出最老可发射独热掩码。
        for deq, eligible in enumerate(self.can_issue):
            result = Const(0, c.num_entries)
            for row in range(c.num_entries):
                older_than_all = Const(1)
                for col in range(c.num_entries):
                    if row == col:
                        relation = Const(1)
                    elif row < col:
                        relation = age[row][col]
                    else:
                        relation = ~age[col][row]
                    older_than_all = older_than_all & (relation | ~eligible[col])
                selected = eligible[row] & older_than_all
                result = Mux(selected, 1 << row, result)
            m.d.comb += self.out[deq].eq(result)
        return m


# =============================================================================
# Public Adapter
# =============================================================================
# Emit deterministic Verilog for the default V2 issue geometry. / 为 V2 默认发射几何生成确定性 Verilog。
def build_verilog(configuration=None, injected_dependencies=None) -> str:
    """Build the standalone AgeDetector module. / 构建独立 AgeDetector 模块。"""

    del injected_dependencies
    from amaranth.back import verilog

    config = configuration or AgeDetectorConfig()
    top = AgeDetector(config)
    return verilog.convert(top, name="AgeDetector",
                           ports=[top.clock, top.reset, *top.enq,
                                  *top.can_issue, *top.out])


# =============================================================================
# Direct Entry
# =============================================================================
# Print generated age detector RTL. / 打印生成的年龄检测器 RTL。
def main() -> None:
    """Print deterministic Verilog. / 打印确定性 Verilog。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
