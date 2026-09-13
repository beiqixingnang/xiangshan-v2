"""Pairwise compare matrix for selecting the least/greatest valid element (XiangShan BPU).
香山 BPU 两两比较矩阵：选出最小/最大有效元素的 amaranth 重写。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amaranth import Cat, Elaboratable, Module, Signal
from amaranth.back import verilog


# ============================================================================
# Module Contract
# ============================================================================
# Public symbols / 公开符号:
#   CompareMatrix - Elaboratable: positions in, lower/least/greatest masks out
#   build_verilog / main
# Contract: m(i)(j) = position(i) < position(j) for i != j; masks follow the
# original semantics: least OH requires the element itself valid.
__all__ = [
    "CompareMatrixConfig",
    "CompareMatrix",
    "build_verilog",
    "main",
]


# ============================================================================
# Configuration
# ============================================================================
@dataclass(frozen=True)
class CompareMatrixConfig:
    # Matrix size and element width / 矩阵大小与元素宽度
    n: int = 4
    position_width: int = 5


# ============================================================================
# Implementation
# ============================================================================
class CompareMatrix(Elaboratable):
    # Compare matrix over n positions / n 个位置的两两比较矩阵
    def __init__(self, config: CompareMatrixConfig = CompareMatrixConfig()) -> None:
        super().__init__()
        self.config = config
        n = config.n
        self.positions = [Signal(config.position_width, name=f"pos{i}") for i in range(n)]
        self.valid = Signal(n)
        self.lower_element_mask = Signal(n)
        self.least_element_oh = Signal(n)
        self.greatest_element_oh = Signal(n)

    # Elaborate the pairwise matrix and the three masks / 展开两两矩阵与三种掩码
    def elaborate(self, platform) -> Module:
        m = Module()
        n = self.config.n
        # m[i][j] = position(i) < position(j), antisymmetric, diagonal = 0
        # m[i][j] = 位置(i) < 位置(j)，反对称，对角线为 0
        matrix: list[list[Any]] = [[None] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if i == j:
                    matrix[i][j] = 0
                elif i < j:
                    matrix[i][j] = self.positions[i] < self.positions[j]
                else:
                    matrix[i][j] = ~matrix[j][i]

        # lower mask: every valid j has order(i, j) / 下元素掩码：所有有效 j 都满足 order(i, j)
        lower: list[Any] = []
        least: list[Any] = []
        greatest: list[Any] = []
        for i in range(n):
            lower_terms: list[Any] = []
            for j in range(n):
                if j != i:
                    valid_j: Any = self.valid[j]
                    lower_terms.append((~valid_j) | matrix[i][j])
            lower_i = 1
            for t in lower_terms:
                lower_i = lower_i & t
            lower.append(lower_i)
            valid_i: Any = self.valid[i]
            least.append(valid_i & lower_i)
            greater_terms: list[Any] = []
            for j in range(n):
                if j != i:
                    valid_j = self.valid[j]
                    greater_terms.append((~valid_j) | matrix[j][i])
            greater_i = 1
            for t in greater_terms:
                greater_i = greater_i & t
            greatest.append(valid_i & greater_i)

        m.d.comb += [
            self.lower_element_mask.eq(Cat(*lower)),
            self.least_element_oh.eq(Cat(*least)),
            self.greatest_element_oh.eq(Cat(*greatest)),
        ]
        return m


# ============================================================================
# Public Adapter
# ============================================================================
# Build Verilog for the compare matrix / 为比较矩阵生成 Verilog
def build_verilog(config: CompareMatrixConfig = CompareMatrixConfig()) -> str:
    top = CompareMatrix(config)
    ports = (top.positions + [top.valid, top.lower_element_mask,
                              top.least_element_oh, top.greatest_element_oh])
    return verilog.convert(top, ports=ports)


# ============================================================================
# Direct Entry
# ============================================================================
# Direct entry: print generated Verilog / 直接入口：打印生成的 Verilog
def main() -> None:
    print(build_verilog())


if __name__ == "__main__":
    main()
