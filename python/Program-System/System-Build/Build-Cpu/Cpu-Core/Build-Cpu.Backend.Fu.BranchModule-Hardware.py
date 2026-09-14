"""V2 branch compare and misprediction unit.
V2 分支比较与误预测单元。
"""

from __future__ import annotations

from dataclasses import dataclass

from amaranth import Const, Elaboratable, Module, Mux, Signal


# =============================================================================
# Module Contract
# =============================================================================
# BranchModule follows Branch.scala: unsigned/signed compare and equality are
# selected by func[3:1], then func[0] inverts the predicate.
# BranchModule 遵循 Branch.scala：func[3:1] 选择无符号/有符号/相等比较，
# func[0] 再执行谓词取反。
__all__ = ["BRANCH_OPCODES", "BranchConfig", "BranchModule", "branch_reference", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
BRANCH_OPCODES = {
    "beq": 0b000000,
    "bne": 0b000001,
    "blt": 0b000100,
    "bge": 0b000101,
    "bltu": 0b001000,
    "bgeu": 0b001001,
}


@dataclass(frozen=True)
class BranchConfig:
    """V2 branch geometry. / V2 分支几何配置。"""

    xlen: int = 64
    func_width: int = 7

    # Validate the V2 XLEN and FuOpType width. / 校验 V2 XLEN 和 FuOpType 位宽。
    def __post_init__(self) -> None:
        if self.xlen not in (32, 64):
            raise ValueError("V2 branch XLEN must be 32 or 64")
        if self.func_width < 4:
            raise ValueError("V2 branch func width must expose bits 3:0")


# =============================================================================
# Implementation
# =============================================================================
def branch_reference(src0: int, src1: int, func: int, xlen: int = 64) -> bool:
    """Return the V2 branch predicate independently. / 独立返回 V2 分支谓词。"""

    mask = (1 << xlen) - 1
    a = src0 & mask
    b = src1 & mask
    signed_a = a - (1 << xlen) if a & (1 << (xlen - 1)) else a
    signed_b = b - (1 << xlen) if b & (1 << (xlen - 1)) else b
    branch_type = (func >> 1) & 0b111
    base = {0: a == b, 2: signed_a < signed_b, 4: a < b}.get(branch_type, False)
    return bool(base) ^ bool(func & 1)


class BranchModule(Elaboratable):
    """Combinational V2 branch resolver. / V2 组合分支解析器。"""

    # Construct the source, function, prediction, and result ports. / 构造源操作数、功能码、预测及结果端口。
    def __init__(self, configuration: BranchConfig = BranchConfig()) -> None:
        self.configuration = configuration
        c = configuration
        self.src0 = Signal(c.xlen, name="io_src_0")
        self.src1 = Signal(c.xlen, name="io_src_1")
        self.func = Signal(c.func_width, name="io_func")
        self.pred_taken = Signal(name="io_pred_taken")
        self.taken = Signal(name="io_taken")
        self.mispredict = Signal(name="io_mispredict")

    # Elaborate equality and signed/unsigned branch equations. / 展开相等、有符号及无符号分支方程。
    def elaborate(self, platform) -> Module:
        del platform
        m = Module()
        a = self.src0
        b = self.src1
        branch_type = self.func[1:4]
        equal = a == b
        signed_less = a.as_signed() < b.as_signed()
        unsigned_less = a < b
        base = Mux(branch_type == 0, equal, Mux(branch_type == 2, signed_less,
                   Mux(branch_type == 4, unsigned_less, Const(0, 1))))
        m.d.comb += self.taken.eq(base ^ self.func[0])
        m.d.comb += self.mispredict.eq(self.pred_taken ^ self.taken)
        return m


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration=None, injected_dependencies=None) -> str:
    """Emit deterministic BranchModule Verilog. / 输出确定性的 BranchModule Verilog。"""

    del injected_dependencies
    from amaranth.back import verilog

    top = BranchModule(configuration or BranchConfig())
    return verilog.convert(top, name="BranchModule", ports=[top.src0, top.src1, top.func,
                        top.pred_taken, top.taken, top.mispredict])


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    """Print the generated branch resolver. / 打印生成的分支解析器。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
