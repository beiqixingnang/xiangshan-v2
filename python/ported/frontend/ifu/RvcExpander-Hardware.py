"""RVC expander (compressed instruction decoder). / RVC 扩展器（压缩指令译码器）。"""

from __future__ import annotations

from dataclasses import dataclass

from amaranth import Cat, Const, Elaboratable, Module, Mux, Signal


# =============================================================================
# Module Contract
# =============================================================================
# Public symbols / 公开符号:
#   - RvcExpanderConfig: frozen config (xlen/fLen/useAddiForMv)
#   - RvcExpander      : Elaboratable RVC decoder mirroring rocket RVCDecoder
# Ports / 端口:
#   in_ (in, 32b): raw instruction (low 16 bits used when compressed)
#   fsIsOff (in): floating-point status off (FP ops illegal)
#   out_bits (out, 32b): expanded instruction
#   out_rd/out_rs1/out_rs2/out_rs3 (out, 5b each): register fields for tracking
#   ill (out): illegal compressed instruction
# The full quadrant/funct3 truth table of the RISC-V C extension is
# implemented; passthrough when low bits are 2'b11.
# 实现 RISC-V C 扩展完整象限/funct3 真值表；低两位为 2'b11 时直通。
# Status / 状态: PYTHON_PRESENT_UNVERIFIED (phase-1 bulk port / 阶段一批量重写)
__all__ = ["RvcExpanderConfig", "RvcExpander", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class RvcExpanderConfig:
    # RVC expander configuration / RVC 扩展器配置
    XLEN: int = 64
    fLen: int = 64
    useAddiForMv: bool = True
    HasCExtension: bool = True


# =============================================================================
# Implementation
# =============================================================================
# sext responsibility. / sext 函数职责。
def sext(value, fromWidth: int, toWidth: int):
    # Sign-extend amaranth value / 符号扩展 amaranth 值
    return Cat(value, Mux(value[fromWidth - 1], Const((1 << (toWidth - fromWidth)) - 1, toWidth - fromWidth), Const(0, toWidth - fromWidth)))


class RvcExpander(Elaboratable):
    # RVC decoder (quadrant 0/1/2 truth table) / RVC 译码器（象限 0/1/2 真值表）
    def __init__(self, config: RvcExpanderConfig = RvcExpanderConfig()):
        self.config = config
        # ports / 端口
        self.in_ = Signal(32, name="io_in")
        self.fsIsOff = Signal(name="io_fsIsOff")
        self.out_bits = Signal(32, name="io_out_bits")
        self.out_rd = Signal(5)
        self.out_rs1 = Signal(5)
        self.out_rs2 = Signal(5)
        self.out_rs3 = Signal(5)
        self.ill = Signal(name="io_ill")

    # Elaborate hardware behavior / 展开硬件行为
    def elaborate(self, platform):
        # Build RVC decoder / 构建 RVC 译码器
        m = Module()
        c = self.config
        x = self.in_[0:16]
        inst = self.in_
        rs1p = Cat(Const(1, 2), x[7:10])
        rs2p = Cat(Const(1, 2), x[2:5])
        rdp = rs2p
        rd = x[7:12]
        rs1 = x[7:12]
        rs2 = x[2:7]
        x2 = Const(2, 5)
        x0 = Const(0, 5)
        x1 = Const(1, 5)

        out = Signal(32)
        ill = Signal()
        outRd = Signal(5)
        outRs1 = Signal(5)
        outRs2 = Signal(5)
        outRs3 = Signal(5)
        m.d.comb += [
            out.eq(self.in_),
            ill.eq(0),
            outRd.eq(x[7:12]),
            outRs1.eq(x[15:20]),
            outRs2.eq(x[20:25]),
            outRs3.eq(x[27:32]),
        ]
        fpOk = Const(1 if c.fLen > 0 else 0) & ~self.fsIsOff

        # immediates (all padded to the 12-bit field they feed) / 立即数（统一补齐到 12 位域）
        immAddi4spn = Cat(Const(0, 2), x[6], x[5], x[11:13], x[7:11], Const(0, 2))
        immLw = Cat(Const(0, 2), x[6], x[10:13], x[5], Const(0, 5))
        immLd = Cat(Const(0, 3), x[10:13], x[6:8], Const(0, 4))
        immI = sext(Cat(x[2:7], x[12]), 6, 12)
        imm16sp = sext(Cat(Const(0, 4), x[6], x[2], x[5], x[4], x[3], x[12]), 10, 12)
        immLui = sext(Cat(x[2:7], x[12]), 6, 20)
        immB = sext(Cat(Const(0, 1), x[3], x[4], x[10], x[11], x[2], x[5], x[6], x[12]), 9, 13)
        immJ = sext(Cat(Const(0, 1), x[3], x[4], x[5], x[11], x[2], x[7], x[6], x[9], x[10], x[8], x[12]), 12, 21)
        immLwsp = Cat(Const(0, 2), x[4:7], x[12], x[2:4], Const(0, 4))
        immLdsp = Cat(Const(0, 3), x[5:7], x[12], x[2:5], Const(0, 3))
        immSwsp = Cat(Const(0, 2), x[9:13], x[7:9], Const(0, 4))
        immSdsp = Cat(Const(0, 3), x[10:13], x[7:10], Const(0, 3))
        shamt = Cat(x[2:7], x[12])

        # encoding helpers / 编码辅助
        def iType(imm, rs1_, funct3, rd_, opcode):
            return Cat(opcode, rd_, funct3, rs1_, imm)

        # rType responsibility. / rType 函数职责。
        def rType(funct7, rs2_, rs1_, funct3, rd_, opcode=Const(0b0110011, 7)):
            return Cat(opcode, rd_, funct3, rs1_, rs2_, funct7)

        # sType responsibility. / sType 函数职责。
        def sType(imm, rs2_, rs1_, funct3, opcode):
            return Cat(opcode, imm[0:5], funct3, rs1_, rs2_, imm[5:12])

        # bType responsibility. / bType 函数职责。
        def bType(imm, rs2_, rs1_, funct3):
            return Cat(Const(0b1100011, 7), imm[11], imm[1:5], funct3, rs1_, rs2_, imm[5:11], imm[12])

        # jType responsibility. / jType 函数职责。
        def jType(imm, rd_):
            return Cat(Const(0b1101111, 7), rd_, imm[12:20], imm[11], imm[1:11], imm[20])

        with m.If(inst[0:2] == 0b00):
            # quadrant 0 / 象限 0
            m.d.comb += outRd.eq(rdp)
            m.d.comb += outRs1.eq(rs1p)
            m.d.comb += outRs2.eq(rs2p)
            with m.Switch(x[13:16]):
                with m.Case(0b000):
                    # c.addi4spn / c.addi4spn
                    m.d.comb += out.eq(iType(immAddi4spn, x2, Const(0, 3), rdp, Const(0b0010011, 7)))
                    m.d.comb += ill.eq(immAddi4spn == 0)
                with m.Case(0b001):
                    # c.fld / c.fld
                    m.d.comb += out.eq(iType(immLd, rs1p, Const(0b011, 3), rdp, Const(0b0000111, 7)))
                    m.d.comb += ill.eq(~fpOk)
                with m.Case(0b010):
                    # c.lw / c.lw
                    m.d.comb += out.eq(iType(immLw, rs1p, Const(0b010, 3), rdp, Const(0b0000011, 7)))
                with m.Case(0b011):
                    # c.ld (rv64) / c.ld
                    m.d.comb += out.eq(iType(immLd, rs1p, Const(0b011, 3), rdp, Const(0b0000011, 7)))
                    m.d.comb += ill.eq(Const(1 if c.XLEN < 64 else 0))
                with m.Case(0b100):
                    # reserved / 保留
                    m.d.comb += ill.eq(1)
                with m.Case(0b101):
                    # c.fsd / c.fsd
                    m.d.comb += out.eq(sType(immLd, rs2p, rs1p, Const(0b011, 3), Const(0b0100111, 7)))
                    m.d.comb += ill.eq(~fpOk)
                with m.Case(0b110):
                    # c.sw / c.sw
                    m.d.comb += out.eq(sType(immLw, rs2p, rs1p, Const(0b010, 3), Const(0b0100011, 7)))
                with m.Case(0b111):
                    # c.sd (rv64) / c.sd
                    m.d.comb += out.eq(sType(immLd, rs2p, rs1p, Const(0b011, 3), Const(0b0100011, 7)))
                    m.d.comb += ill.eq(Const(1 if c.XLEN < 64 else 0))
        with m.Elif(inst[0:2] == 0b01):
            # quadrant 1 / 象限 1
            m.d.comb += outRd.eq(rd)
            m.d.comb += outRs1.eq(rs1)
            m.d.comb += outRs2.eq(rs2)
            with m.Switch(x[13:16]):
                with m.Case(0b000):
                    # c.addi / c.nop / c.addi 与 c.nop
                    m.d.comb += out.eq(iType(immI, rs1, Const(0, 3), rd, Const(0b0010011, 7)))
                with m.Case(0b001):
                    # c.addiw (rv64) / c.addiw
                    m.d.comb += out.eq(iType(immI, rs1, Const(0, 3), rd, Const(0b0011011, 7)))
                    m.d.comb += ill.eq((rd == 0) | Const(1 if c.XLEN < 64 else 0))
                with m.Case(0b010):
                    # c.li / c.li
                    m.d.comb += out.eq(iType(immI, x0, Const(0, 3), rd, Const(0b0010011, 7)))
                    m.d.comb += ill.eq(rd == 0)
                with m.Case(0b011):
                    with m.If(rd == 2):
                        # c.addi16sp / c.addi16sp
                        m.d.comb += out.eq(iType(imm16sp, x2, Const(0, 3), x2, Const(0b0010011, 7)))
                        m.d.comb += ill.eq(imm16sp == 0)
                    with m.Else():
                        # c.lui / c.lui
                        m.d.comb += out.eq(Cat(Const(0b0110111, 7), rd, immLui))
                        m.d.comb += ill.eq((rd == 0) | (immLui == 0))
                with m.Case(0b100):
                    # misc-alu group / 杂项运算组
                    m.d.comb += outRd.eq(rdp)
                    m.d.comb += outRs1.eq(rs1p)
                    m.d.comb += outRs2.eq(rs2p)
                    with m.Switch(x[10:12]):
                        with m.Case(0b00):
                            # c.srli / c.srli
                            m.d.comb += out.eq(iType(Cat(shamt, Const(0, 6)), rs1p, Const(0b101, 3), rdp, Const(0b0010011, 7)))
                        with m.Case(0b01):
                            # c.srai / c.srai
                            m.d.comb += out.eq(iType(Cat(shamt, Const(0b010000, 6)), rs1p, Const(0b101, 3), rdp, Const(0b0010011, 7)))
                        with m.Case(0b10):
                            # c.andi / c.andi
                            m.d.comb += out.eq(iType(immI, rs1p, Const(0b111, 3), rdp, Const(0b0010011, 7)))
                        with m.Case(0b11):
                            with m.If(x[12] == 0):
                                with m.Switch(x[5:7]):
                                    with m.Case(0b00):
                                        # c.sub / c.sub
                                        m.d.comb += out.eq(rType(Const(0b0100000, 7), rs2p, rs1p, Const(0, 3), rdp))
                                    with m.Case(0b01):
                                        # c.xor / c.xor
                                        m.d.comb += out.eq(rType(Const(0, 7), rs2p, rs1p, Const(0b100, 3), rdp))
                                    with m.Case(0b10):
                                        # c.or / c.or
                                        m.d.comb += out.eq(rType(Const(0, 7), rs2p, rs1p, Const(0b110, 3), rdp))
                                    with m.Case(0b11):
                                        # c.and / c.and
                                        m.d.comb += out.eq(rType(Const(0, 7), rs2p, rs1p, Const(0b111, 3), rdp))
                            with m.Else():
                                with m.Switch(x[5:7]):
                                    with m.Case(0b00):
                                        # c.subw (rv64) / c.subw
                                        m.d.comb += out.eq(rType(Const(0b0100000, 7), rs2p, rs1p, Const(0, 3), rdp, Const(0b0111011, 7)))
                                        m.d.comb += ill.eq(Const(1 if c.XLEN < 64 else 0))
                                    with m.Case(0b01):
                                        # c.addw (rv64) / c.addw
                                        m.d.comb += out.eq(rType(Const(0, 7), rs2p, rs1p, Const(0, 3), rdp, Const(0b0111011, 7)))
                                        m.d.comb += ill.eq(Const(1 if c.XLEN < 64 else 0))
                                    with m.Default():
                                        # reserved / 保留
                                        m.d.comb += ill.eq(1)
                with m.Case(0b101):
                    # c.j / c.j
                    m.d.comb += out.eq(jType(immJ, x0))
                with m.Case(0b110):
                    # c.beqz / c.beqz
                    m.d.comb += out.eq(bType(immB, x0, rs1p, Const(0, 3)))
                with m.Case(0b111):
                    # c.bnez / c.bnez
                    m.d.comb += out.eq(bType(immB, x0, rs1p, Const(1, 3)))
        with m.Elif(inst[0:2] == 0b10):
            # quadrant 2 / 象限 2
            m.d.comb += outRd.eq(rd)
            m.d.comb += outRs1.eq(rs1)
            m.d.comb += outRs2.eq(rs2)
            with m.Switch(x[13:16]):
                with m.Case(0b000):
                    # c.slli / c.slli
                    m.d.comb += out.eq(iType(Cat(shamt, Const(0, 6)), rs1, Const(1, 3), rd, Const(0b0010011, 7)))
                    m.d.comb += ill.eq(rd == 0)
                with m.Case(0b001):
                    # c.fldsp / c.fldsp
                    m.d.comb += out.eq(iType(immLdsp, x2, Const(0b011, 3), rd, Const(0b0000111, 7)))
                    m.d.comb += ill.eq(~fpOk)
                with m.Case(0b010):
                    # c.lwsp / c.lwsp
                    m.d.comb += out.eq(iType(immLwsp, x2, Const(0b010, 3), rd, Const(0b0000011, 7)))
                    m.d.comb += ill.eq(rd == 0)
                with m.Case(0b011):
                    # c.ldsp (rv64) / c.ldsp
                    m.d.comb += out.eq(iType(immLdsp, x2, Const(0b011, 3), rd, Const(0b0000011, 7)))
                    m.d.comb += ill.eq((rd == 0) | Const(1 if c.XLEN < 64 else 0))
                with m.Case(0b100):
                    with m.If(x[12] == 0):
                        with m.If(rs2 == 0):
                            # c.jr / c.jr
                            m.d.comb += out.eq(iType(Const(0, 12), rs1, Const(0, 3), x0, Const(0b1100111, 7)))
                            m.d.comb += ill.eq(rs1 == 0)
                        with m.Else():
                            # c.mv as addi rd, rs2, 0 / c.mv 以 addi 实现
                            m.d.comb += out.eq(iType(Const(0, 12), rs2, Const(0, 3), rd, Const(0b0010011, 7)))
                            m.d.comb += outRs1.eq(rs2)
                    with m.Else():
                        with m.If(rs2 == 0):
                            with m.If(rs1 == 0):
                                # c.ebreak / c.ebreak
                                m.d.comb += out.eq(Const(0x00100073, 32))
                            with m.Else():
                                # c.jalr / c.jalr
                                m.d.comb += out.eq(iType(Const(0, 12), rs1, Const(0, 3), x1, Const(0b1100111, 7)))
                        with m.Else():
                            # c.add / c.add
                            m.d.comb += out.eq(rType(Const(0, 7), rs2, rs1, Const(0, 3), rd))
                with m.Case(0b101):
                    # c.fsdsp / c.fsdsp
                    m.d.comb += out.eq(sType(immSdsp, rs2, x2, Const(0b011, 3), Const(0b0100111, 7)))
                    m.d.comb += ill.eq(~fpOk)
                with m.Case(0b110):
                    # c.swsp / c.swsp
                    m.d.comb += out.eq(sType(immSwsp, rs2, x2, Const(0b010, 3), Const(0b0100011, 7)))
                with m.Case(0b111):
                    # c.sdsp (rv64) / c.sdsp
                    m.d.comb += out.eq(sType(immSdsp, rs2, x2, Const(0b011, 3), Const(0b0100011, 7)))
                    m.d.comb += ill.eq(Const(1 if c.XLEN < 64 else 0))

        with m.If(inst[0:2] == 0b11):
            # not compressed: passthrough / 非压缩指令：直通
            m.d.comb += out.eq(self.in_)
            m.d.comb += ill.eq(0)

        with m.If(~Const(1 if c.HasCExtension else 0)):
            # C extension disabled: passthrough, never illegal / 未使能 C 扩展：直通且合法
            m.d.comb += out.eq(self.in_)
            m.d.comb += ill.eq(0)

        m.d.comb += [
            self.out_bits.eq(out),
            self.out_rd.eq(outRd),
            self.out_rs1.eq(outRs1),
            self.out_rs2.eq(outRs2),
            self.out_rs3.eq(outRs3),
            self.ill.eq(ill),
        ]
        return m


# =============================================================================
# Public Adapter
# =============================================================================
# build_verilog responsibility. / build_verilog 函数职责。
def build_verilog(config: RvcExpanderConfig = RvcExpanderConfig(), name: str = "RvcExpander") -> str:
    # Convert RvcExpander to verilog / 转换 RvcExpander 为 Verilog
    from amaranth.back import verilog

    top = RvcExpander(config)
    # The Scala module exposes only instruction and legality ports.  Register
    # tracking fields remain available on the Python object for parent logic
    # but are intentionally not top-level ports.
    ports = [top.in_, top.fsIsOff, top.out_bits, top.ill]
    return verilog.convert(top, name=name, ports=ports)


# =============================================================================
# Direct Entry
# =============================================================================
# main responsibility. / main 函数职责。
def main() -> None:
    # Entry point / 入口
    print(build_verilog())


if __name__ == "__main__":
    main()
