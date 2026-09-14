"""V2 dispatch issue-queue ordering matrix. / V2 dispatch 发射队列排序矩阵。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from amaranth import (Cat, ClockDomain, ClockSignal, Const, Elaboratable,
                      Module, Mux, ResetSignal, Signal)
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# NewDispatch.scala does not instantiate a standalone CompareMatrix. It builds
# an antisymmetric matrix from IQValidNumVec and derives IQSort/minIQSel in-line.
# This configurable leaf preserves those equations and exposes the old valid
# masks only as observation taps for source-compatible parent tests.
# NewDispatch.scala 内联构造矩阵、IQSort 与 minIQSel；本叶复现这些方程。
__all__ = [
    "CompareMatrixConfig",
    "CompareMatrix",
    "compare_order",
    "sort_one_hot",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class CompareMatrixConfig:
    """Describe the issue-queue comparison closure. / 描述发射队列比较闭包。"""

    n: int = 4
    position_width: int = 5
    count_width: int | None = None
    issue_queue_num: int | None = None
    rename_width: int = 2
    exu_indices: tuple[int, ...] | None = None
    register_sort: bool = True

    # Validate matrix dimensions and static index mapping. / 校验矩阵尺寸与索引映射。
    def __post_init__(self) -> None:
        if self.n < 1:
            raise ValueError("matrix size must be positive")
        if self.position_width < 1:
            raise ValueError("position width must be positive")
        if self.count_width is not None and self.count_width < 1:
            raise ValueError("count width must be positive")
        if self.issue_queue_num is not None and self.issue_queue_num < self.n:
            raise ValueError("issue queue count cannot be smaller than matrix size")
        if self.rename_width < 1:
            raise ValueError("rename width must be positive")
        if self.exu_indices is not None:
            if len(self.exu_indices) != self.n:
                raise ValueError("exu_indices must contain n entries")
            queue_count = self.issue_queue_num or self.n
            if any(index < 0 or index >= queue_count for index in self.exu_indices):
                raise ValueError("exu index is outside the issue queue domain")

    # Return the effective count width. / 返回有效计数位宽。
    @property
    # effective_count_width responsibility. / effective_count_width 函数职责。
    def effective_count_width(self) -> int:
        return self.count_width or self.position_width

    # Return the effective issue queue count. / 返回有效发射队列数量。
    @property
    # effective_issue_queue_num responsibility. / effective_issue_queue_num 函数职责。
    def effective_issue_queue_num(self) -> int:
        return self.issue_queue_num or self.n

    # Return the static EXU-to-IQ mapping. / 返回静态 EXU 到 IQ 映射。
    @property
    # effective_exu_indices responsibility. / effective_exu_indices 函数职责。
    def effective_exu_indices(self) -> tuple[int, ...]:
        return self.exu_indices or tuple(range(self.n))


# =============================================================================
# Implementation
# =============================================================================
# Evaluate NewDispatch's strict antisymmetric ordering in integers. / 整数域计算 NewDispatch 排序。
def compare_order(counts: Sequence[int]) -> tuple[tuple[int, ...], ...]:
    """Return ``matrix[i][j]`` with V2 tie priority. / 返回带 V2 平局优先级的矩阵。"""

    size = len(counts)
    if size < 1:
        raise ValueError("at least one count is required")
    matrix = [[0 for _ in range(size)] for _ in range(size)]
    for i in range(size):
        for j in range(size):
            if i == j:
                matrix[i][j] = 0
            elif i < j:
                matrix[i][j] = int(counts[i] < counts[j])
            else:
                matrix[i][j] = 1 - matrix[j][i]
    return tuple(tuple(row) for row in matrix)


# Derive IQSort rows from a comparison matrix. / 从比较矩阵导出 IQSort 行。
def sort_one_hot(matrix: Sequence[Sequence[int]]) -> tuple[tuple[int, ...], ...]:
    """Return rows ordered by ascending queue count. / 返回按队列计数升序的一热行。"""

    size = len(matrix)
    if size < 1 or any(len(row) != size for row in matrix):
        raise ValueError("matrix must be non-empty and square")
    return tuple(
        tuple(int(sum(int(bit) for bit in row) == size - 1 - rank)
              for row in matrix)
        for rank in range(size)
    )


class CompareMatrix(Elaboratable):
    """Combinational NewDispatch ordering closure. / NewDispatch 排序组合闭包。"""

    # Declare matrix, sort, and compatibility observation ports. / 声明矩阵、排序及观察端口。
    def __init__(self, configuration: CompareMatrixConfig | None = None) -> None:
        self.configuration = configuration or CompareMatrixConfig()
        cfg = self.configuration
        self.clock_domain = ClockDomain("sync", async_reset=True)
        self.clock = self.clock_domain.clk
        self.reset = self.clock_domain.rst
        width = cfg.effective_count_width
        queue_num = cfg.effective_issue_queue_num
        self.issue_queue_counts = [
            Signal(width, name=f"issue_queue_count_{index}")
            for index in range(queue_num)
        ]
        self.valid = Signal(cfg.n, name="valid")
        self.compare_matrix = [Signal(cfg.n, name=f"compare_matrix_{row}")
                               for row in range(cfg.n)]
        self.iq_sort = [Signal(cfg.n, name=f"iq_sort_{rank}")
                        for rank in range(cfg.n)]
        self.min_iq_sel = [Signal(queue_num, name=f"min_iq_sel_{slot}")
                           for slot in range(cfg.rename_width)]
        self.lower_element_mask = Signal(cfg.n, name="lower_element_mask")
        self.least_element_oh = Signal(cfg.n, name="least_element_oh")
        self.greatest_element_oh = Signal(cfg.n, name="greatest_element_oh")

    # Expose the historical positions view without creating a signal alias. / 暴露历史 positions 视图。
    @property
    # positions view responsibility. / positions 视图函数职责。
    def positions(self) -> list[Signal]:
        return self.issue_queue_counts[: self.configuration.n]

    # Elaborate the inlined NewDispatch equations. / 展开 NewDispatch 内联方程。
    def elaborate(self, platform: Any) -> Module:
        del platform
        cfg = self.configuration
        module = Module()
        module.domains.sync = self.clock_domain
        indices = cfg.effective_exu_indices
        queue_num = cfg.effective_issue_queue_num
        count_expr = [self.issue_queue_counts[index] for index in indices]
        matrix_expr: list[list[Any]] = [[Const(0) for _ in range(cfg.n)]
                                        for _ in range(cfg.n)]
        for i in range(cfg.n):
            for j in range(cfg.n):
                if i == j:
                    matrix_expr[i][j] = Const(0)
                elif i < j:
                    matrix_expr[i][j] = count_expr[i] < count_expr[j]
                else:
                    matrix_expr[i][j] = ~(count_expr[j] < count_expr[i])
                module.d.comb += self.compare_matrix[i][j].eq(matrix_expr[i][j])

        # NewDispatch stores IQSort in a register; preserve that one-cycle
        # boundary instead of exposing the combinational next value directly.
        # NewDispatch 将 IQSort 存入寄存器，保留该一级时序边界。
        next_sort: list[list[Any]] = []
        sum_width = (cfg.n + 1).bit_length()
        for rank in range(cfg.n):
            next_row: list[Any] = []
            for row in range(cfg.n):
                row_sum = Const(0, sum_width)
                for col in range(cfg.n):
                    bit = matrix_expr[row][col]
                    row_sum = row_sum + Cat(bit, Const(0, sum_width - 1))
                next_row.append(row_sum == Const(cfg.n - 1 - rank, sum_width))
            next_sort.append(next_row)
        module.d.sync += [
            self.iq_sort[rank][row].eq(next_sort[rank][row])
            for rank in range(cfg.n) for row in range(cfg.n)
        ]

        for slot in range(cfg.rename_width):
            rank = slot % cfg.n
            selected = cfg.effective_exu_indices
            for queue in range(queue_num):
                if queue in selected:
                    row = selected.index(queue)
                    module.d.comb += self.min_iq_sel[slot][queue].eq(self.iq_sort[rank][row])
                else:
                    module.d.comb += self.min_iq_sel[slot][queue].eq(0)

        # Historical masks use the same matrix but honor the valid input. / 历史掩码沿用矩阵并应用 valid。
        lower_terms: list[Any] = []
        least_terms: list[Any] = []
        greatest_terms: list[Any] = []
        for i in range(cfg.n):
            lower = Const(1)
            greater = Const(1)
            for j in range(cfg.n):
                if i == j:
                    continue
                lower = lower & ((~self.valid[j]) | matrix_expr[i][j])
                greater = greater & ((~self.valid[j]) | matrix_expr[j][i])
            lower_terms.append(lower)
            least_terms.append(self.valid[i] & lower)
            greatest_terms.append(self.valid[i] & greater)
        for i in range(cfg.n):
            module.d.comb += [
                self.lower_element_mask[i].eq(lower_terms[i]),
                self.least_element_oh[i].eq(least_terms[i]),
                self.greatest_element_oh[i].eq(greatest_terms[i]),
            ]
        return module


# =============================================================================
# Public Adapter
# =============================================================================
# Emit deterministic RTL for the ordering closure. / 输出确定性的排序闭包 RTL。
def build_verilog(configuration, injected_dependencies):
    del injected_dependencies
    top = CompareMatrix(configuration)
    ports: list[Any] = [top.clock, top.reset, *top.issue_queue_counts, top.valid]
    ports.extend(top.compare_matrix)
    ports.extend(top.iq_sort)
    ports.extend(top.min_iq_sel)
    ports.extend([top.lower_element_mask, top.least_element_oh,
                  top.greatest_element_oh])
    return verilog.convert(top, name="CompareMatrix", ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print generated RTL for a default matrix. / 打印默认矩阵 RTL。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
