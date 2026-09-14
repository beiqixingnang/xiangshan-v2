"""V2 jump target and link-result unit.
V2 跳转目标与链接结果单元。
"""

from __future__ import annotations

from dataclasses import dataclass

from amaranth import Cat, Const, Elaboratable, Module, Mux, Signal


# =============================================================================
# Module Contract
# =============================================================================
# JumpDataModule follows Jump.scala: jalr selects src+offset, jal selects
# pc+offset, AUIPC returns the target while other jumps return sequential PC.
# JumpDataModule 遵循 Jump.scala：jalr 选择 src+offset，jal 选择 pc+offset，
# AUIPC 返回目标，其余跳转返回顺序 PC。
__all__ = ["JUMP_OPCODES", "JumpConfig", "JumpDataModule", "jump_reference", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
JUMP_OPCODES = {"jal": 0b1111000, "jalr": 0b1111001, "auipc": 0b1111010}


@dataclass(frozen=True)
class JumpConfig:
    """V2 jump geometry. / V2 跳转几何配置。"""

    xlen: int = 64
    imm_width: int = 33
    next_pc_offset_width: int = 9
    inst_offset_bits: int = 1

    # Validate V2 widths and compressed-instruction offset scaling. / 校验 V2 位宽及压缩指令偏移缩放。
    def __post_init__(self) -> None:
        if self.xlen not in (32, 64):
            raise ValueError("V2 jump XLEN must be 32 or 64")
        if self.imm_width < 2 or self.next_pc_offset_width < 1:
            raise ValueError("V2 jump widths must be positive")
        if self.inst_offset_bits < 0:
            raise ValueError("V2 instruction offset bits must be non-negative")


# =============================================================================
# Implementation
# =============================================================================
def jump_reference(src: int, pc: int, imm: int, next_pc_offset: int, func: int,
                   configuration: JumpConfig = JumpConfig()) -> tuple[int, int, bool]:
    """Return target/result/AUIPC independently. / 独立返回目标、结果及 AUIPC 标志。"""

    c = configuration
    mask = (1 << c.xlen) - 1
    imm_mask = (1 << c.imm_width) - 1
    imm_value = imm & imm_mask
    if imm_value & (1 << (c.imm_width - 1)):
        imm_value -= 1 << c.imm_width
    offset = imm_value & mask
    is_jalr = bool(func & 1)
    is_auipc = bool(func & 2)
    target = ((src if is_jalr else pc) + offset) & mask
    target &= ~1
    snpc = (pc + ((next_pc_offset & ((1 << c.next_pc_offset_width) - 1)) << c.inst_offset_bits)) & mask
    result = ((src if is_jalr else pc) + offset) & mask if is_auipc else snpc
    return target, result, is_auipc


class JumpDataModule(Elaboratable):
    """Combinational V2 jump data path. / V2 组合跳转数据通路。"""

    # Construct source, PC, immediate, function, and output ports. / 构造源、PC、立即数、功能码及输出端口。
    def __init__(self, configuration: JumpConfig = JumpConfig()) -> None:
        self.configuration = configuration
        c = configuration
        self.src = Signal(c.xlen, name="io_src")
        self.pc = Signal(c.xlen, name="io_pc")
        self.imm = Signal(c.imm_width, name="io_imm")
        self.next_pc_offset = Signal(c.next_pc_offset_width, name="io_nextPcOffset")
        self.func = Signal(7, name="io_func")
        self.result = Signal(c.xlen, name="io_result")
        self.target = Signal(c.xlen, name="io_target")
        self.is_auipc = Signal(name="io_isAuipc")

    # Elaborate sign extension, target alignment, and link selection. / 展开符号扩展、目标对齐及链接选择。
    def elaborate(self, platform) -> Module:
        del platform
        m = Module()
        c = self.configuration
        imm_signed = self.imm.as_signed()
        offset = imm_signed.as_unsigned()
        target_full = Mux(self.func[0], self.src + offset, self.pc + offset)
        target = Cat(Const(0, 1), target_full[1:c.xlen])
        snpc = self.pc + (self.next_pc_offset << c.inst_offset_bits)
        auipc_target = Mux(self.func[1], target_full, snpc)
        m.d.comb += [self.target.eq(target), self.result.eq(auipc_target),
                     self.is_auipc.eq(self.func[1])]
        return m


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration=None, injected_dependencies=None) -> str:
    """Emit deterministic JumpDataModule Verilog. / 输出确定性的 JumpDataModule Verilog。"""

    del injected_dependencies
    from amaranth.back import verilog

    top = JumpDataModule(configuration or JumpConfig())
    return verilog.convert(top, name="JumpDataModule", ports=[top.src, top.pc, top.imm,
                        top.next_pc_offset, top.func, top.result, top.target, top.is_auipc])


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    """Print the generated jump data path. / 打印生成的跳转数据通路。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
