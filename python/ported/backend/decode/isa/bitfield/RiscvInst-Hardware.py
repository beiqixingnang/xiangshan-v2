"""RISC-V instruction bitfield accessors and opcode constants. / RISC-V 指令位域访问器与操作码常量。"""

from __future__ import annotations

from amaranth import Elaboratable, Module, Signal


# =============================================================================
# Module Contract
# =============================================================================
# Public symbols / 公开符号:
#   - OPCODE5Bit, OPCODE7Bit : opcode constant collections
#   - inst_field              : bitfield accessor on a 32-bit instruction value
#   - isAMOCAS, isVecStore, isVecLoad, isVecArith, isOPIVV... : field predicates
#   - build_verilog, main     : minimal probe adapter
# Source: decode/isa/bitfield/RiscvInst.scala. Pure constant/utility table.
# Status / 状态: PYTHON_PRESENT_UNVERIFIED (phase-2 direct audit / 阶段二直接审计)
__all__ = ["OPCODE5Bit", "OPCODE7Bit", "inst_field", "isAMOCAS", "isVecStore",
           "isVecLoad", "isVecArith", "isOPIVV", "isOPFVV", "isOPMVV",
           "isOPIVI", "isOPIVX", "isOPFVF", "isOPMVX", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
class OPCODE5Bit:
    # 5-bit opcode (inst[6:2]) constants / 5 位操作码常量
    LOAD = 0b00000
    LOAD_FP = 0b00001
    CUSTOM_0 = 0b00010
    MSIC_MEM = 0b00011
    OP_IMM = 0b00100
    AUIPC = 0b00101
    OP_IMM_32 = 0b00110
    INST48b_0 = 0b00111
    STORE = 0b01000
    STORE_FP = 0b01001
    CUSTOM_1 = 0b01010
    AMO = 0b01011
    OP = 0b01100
    LUI = 0b01101
    OP_32 = 0b01110
    INST64b = 0b01111
    MADD = 0b10000
    MSUB = 0b10001
    NMSUB = 0b10010
    NMADD = 0b10011
    OP_FP = 0b10100
    OP_V = 0b10101
    CUSTOM_2 = 0b10110
    INST48b_1 = 0b10111
    BRANCH = 0b11000
    JALR = 0b11001
    RESERVED_0 = 0b11010
    JAL = 0b11011
    SYSTEM = 0b11100
    RESERVED_1 = 0b11101
    CUSTOM_3 = 0b11110
    INSTge80b = 0b11111


class OPCODE7Bit:
    # 7-bit opcode (inst[6:0]) constants / 7 位操作码常量
    VECTOR_ARITH = 0b1010111


# =============================================================================
# Implementation
# =============================================================================
def inst_field(inst, name):
    # Extract a named RISC-V bitfield from an integer or Amaranth value / 提取整数或 Amaranth 指令位域
    ranges = {
        "OPCODE": (0, 7), "OPCODE5Bit": (2, 5),
        "RD": (7, 5), "VD": (7, 5), "VS3": (7, 5), "FD": (7, 5),
        "FUNCT3": (12, 3), "VCATEGORY": (12, 3), "WIDTH": (12, 3), "RM": (12, 3),
        "RS1": (15, 5), "FS1": (15, 5), "VS1": (15, 5), "CSRIMM": (15, 5),
        "UIMM_VSETIVLI": (15, 5), "IMM5_OPIVI": (15, 5),
        "RS2": (20, 5), "FS2": (20, 5), "VS2": (20, 5), "LUMOP": (20, 5),
        "SUMOP": (20, 5), "SHAMT5": (20, 5), "RNUM": (20, 4),
        "FUNCT7": (25, 7), "IMM7": (25, 7), "IMM12": (20, 12),
        "SHAMT6": (20, 6), "CSRIDX": (20, 12), "NF": (29, 3), "MEW": (28, 1),
        "MOP": (26, 2), "VM": (25, 1), "FS3": (27, 5), "CONV_SGN": (20, 5),
        "FMT": (25, 2), "TYP": (20, 2), "FUNCT6": (26, 6),
        "ZIMM_VSETVLI": (20, 11), "ZIMM_VSETIVLI": (20, 10),
    }
    if name == "ALL":
        return inst
    if name in ranges:
        lsb, width = ranges[name]
        if isinstance(inst, int):
            return (inst >> lsb) & ((1 << width) - 1)
        return inst[lsb:lsb + width]
    raise KeyError(f"unknown field {name!r}")


# Read one bit from an integer or hardware value / 读取整数或硬件值中的一位
def bit_value(value, index):
    if isinstance(value, int):
        return (value >> index) & 1
    return value[index]


def isAMOCAS(inst):
    # AMOCAS detection / AMOCAS 检测
    return (inst_field(inst, "OPCODE5Bit") == OPCODE5Bit.AMO) & \
           ((inst_field(inst, "FUNCT7") & 0b1111100) == 0b0010100)


def isVecStore(inst):
    # vector store detection / 向量存储检测
    width = inst_field(inst, "WIDTH")
    return (inst_field(inst, "OPCODE5Bit") == OPCODE5Bit.STORE_FP) & \
           ((width == 0) | (bit_value(width, 2) == 1))


def isVecLoad(inst):
    # vector load detection / 向量读取检测
    width = inst_field(inst, "WIDTH")
    return (inst_field(inst, "OPCODE5Bit") == OPCODE5Bit.LOAD_FP) & \
           ((width == 0) | (bit_value(width, 2) == 1))


def isVecArith(inst):
    # vector arithmetic detection / 向量算术检测
    return inst_field(inst, "OPCODE5Bit") == OPCODE5Bit.OP_V


def vec_arith_funct3(inst, funct3):
    # vector arith with funct3 match / 向量算术按 funct3 匹配
    return (inst_field(inst, "OPCODE") == OPCODE7Bit.VECTOR_ARITH) & \
           (inst_field(inst, "FUNCT3") == funct3)


def isOPIVV(inst):
    # OPIVV / OPIVV
    return vec_arith_funct3(inst, 0b000)


def isOPFVV(inst):
    # OPFVV / OPFVV
    return vec_arith_funct3(inst, 0b001)


def isOPMVV(inst):
    # OPMVV / OPMVV
    return vec_arith_funct3(inst, 0b010)


def isOPIVI(inst):
    # OPIVI / OPIVI
    return vec_arith_funct3(inst, 0b011)


def isOPIVX(inst):
    # OPIVX / OPIVX
    return vec_arith_funct3(inst, 0b100)


def isOPFVF(inst):
    # OPFVF / OPFVF
    return vec_arith_funct3(inst, 0b101)


def isOPMVX(inst):
    # OPMVX / OPMVX
    return vec_arith_funct3(inst, 0b110)


# =============================================================================
# Public Adapter
# =============================================================================
class RiscvInstProbe(Elaboratable):
    # Expose Scala bitfields and predicates for direct hardware checks / 暴露 Scala 位域与谓词供硬件直测
    def __init__(self):
        self.inst = Signal(32, name="inst")
        self.opcode = Signal(7, name="opcode")
        self.funct3 = Signal(3, name="funct3")
        self.funct7 = Signal(7, name="funct7")
        self.is_amo_cas = Signal(name="is_amo_cas")
        self.is_vec_store = Signal(name="is_vec_store")
        self.is_vec_load = Signal(name="is_vec_load")
        self.is_vec_arith = Signal(name="is_vec_arith")
        self.is_opivv = Signal(name="is_opivv")
        self.is_opmvv = Signal(name="is_opmvv")

    # Build field and predicate datapath / 构建位域及谓词数据通路
    def elaborate(self, platform):
        m = Module()
        m.d.comb += [
            self.opcode.eq(inst_field(self.inst, "OPCODE")),
            self.funct3.eq(inst_field(self.inst, "FUNCT3")),
            self.funct7.eq(inst_field(self.inst, "FUNCT7")),
            self.is_amo_cas.eq(isAMOCAS(self.inst)),
            self.is_vec_store.eq(isVecStore(self.inst)),
            self.is_vec_load.eq(isVecLoad(self.inst)),
            self.is_vec_arith.eq(isVecArith(self.inst)),
            self.is_opivv.eq(isOPIVV(self.inst)),
            self.is_opmvv.eq(isOPMVV(self.inst)),
        ]
        return m


def build_verilog(name: str = "RiscvInst") -> str:
    # Convert bitfield probe to Verilog / 将位域探针转换为 Verilog
    from amaranth.back import verilog
    top = RiscvInstProbe()
    return verilog.convert(top, name=name, ports=[top.inst, top.opcode, top.funct3,
                           top.funct7, top.is_amo_cas, top.is_vec_store,
                           top.is_vec_load, top.is_vec_arith, top.is_opivv,
                           top.is_opmvv])


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    # Entry point / 入口
    print(build_verilog())


if __name__ == "__main__":
    main()
