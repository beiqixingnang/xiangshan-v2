"""V2 RISC-V instruction fields. / 香山 V2 RISC-V 指令位域。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amaranth import Const, Elaboratable, Module, Signal


# =============================================================================
# Module Contract
# =============================================================================
# This module mirrors the locked ``RiscvInst.scala`` field geometry and vector
# predicates.  It does not rename internal RISC-V protocol fields.
# 本模块镜像锁定的 RiscvInst.scala 位域几何与向量谓词，不重命名内部协议字段。
__all__ = [
    "FIELD_RANGES",
    "OPCODE5Bit",
    "OPCODE7Bit",
    "InstVType",
    "Riscv32BitInst",
    "XSInstBitFields",
    "inst_field",
    "bit_value",
    "isAMOCAS",
    "isVecStore",
    "isVecLoad",
    "isVecArith",
    "isOPIVV",
    "isOPFVV",
    "isOPMVV",
    "isOPIVI",
    "isOPIVX",
    "isOPFVF",
    "isOPMVX",
    "RiscvInstProbe",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
FIELD_RANGES = {
    "ALL": (0, 32),
    "OPCODE": (0, 7),
    "OPCODE5Bit": (2, 5),
    "OPCODE7Bit": (0, 7),
    "RD": (7, 5),
    "FUNCT3": (12, 3),
    "RS1": (15, 5),
    "RS2": (20, 5),
    "FUNCT7": (25, 7),
    "IMM12": (20, 12),
    "SHAMT6": (20, 6),
    "SHAMT5": (20, 5),
    "IMM5": (7, 5),
    "IMM7": (25, 7),
    "CSRIDX": (20, 12),
    "CSRIMM": (15, 5),
    "FD": (7, 5),
    "FS1": (15, 5),
    "FS2": (20, 5),
    "FS3": (27, 5),
    "RM": (12, 3),
    "CONV_SGN": (20, 5),
    "FMT": (25, 2),
    "TYP": (20, 2),
    "VCATEGORY": (12, 3),
    "NF": (29, 3),
    "MEW": (28, 1),
    "MOP": (26, 2),
    "VM": (25, 1),
    "LUMOP": (20, 5),
    "SUMOP": (20, 5),
    "WIDTH": (12, 3),
    "VD": (7, 5),
    "VS1": (15, 5),
    "VS2": (20, 5),
    "VS3": (7, 5),
    "FUNCT6": (26, 6),
    "ZIMM_VSETVLI": (20, 11),
    "ZIMM_VSETIVLI": (20, 10),
    "UIMM_VSETIVLI": (15, 5),
    "IMM5_OPIVI": (15, 5),
    "RNUM": (20, 4),
}


# =============================================================================
# Implementation
# =============================================================================
class OPCODE5Bit:
    """Five-bit opcode constants. / 五位操作码常量。"""

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
    """Seven-bit opcode constants. / 七位操作码常量。"""

    VECTOR_ARITH = 0b1010111


@dataclass(frozen=True)
class InstVType:
    """Decoded vector type fields. / 解码后的向量类型字段。"""

    reserved: int = 0
    vma: int = 0
    vta: int = 0
    vsew: int = 0
    vlmul: int = 0


# Extract a field from an integer or Amaranth value / 提取整数或硬件位域。
def inst_field(inst: Any, name: str) -> Any:
    """Extract one named source field. / 提取指定名称的源位域。"""

    if name not in FIELD_RANGES:
        raise KeyError(f"unknown field {name!r}")
    lsb, width = FIELD_RANGES[name]
    if isinstance(inst, int):
        return (inst >> lsb) & ((1 << width) - 1)
    return inst[lsb:lsb + width]


# Read a single bit from an integer or hardware value / 读取整数或硬件值的一位。
def bit_value(value: Any, index: int) -> Any:
    """Return one bit at ``index``. / 返回指定索引的一位。"""

    if isinstance(value, int):
        return (value >> index) & 1
    return value[index]


# Detect AMOCAS according to the V2 BitPat / 按 V2 BitPat 检测 AMOCAS。
def isAMOCAS(inst: Any) -> Any:
    """Return true for AMO with FUNCT7 ``00101??``. / 检测 AMOCAS。"""

    funct7 = inst_field(inst, "FUNCT7")
    opcode5 = inst_field(inst, "OPCODE5Bit")
    if isinstance(inst, int):
        return ((opcode5 == OPCODE5Bit.AMO) and
                ((funct7 & 0b1111100) == 0b0010100))
    return ((opcode5 == Const(OPCODE5Bit.AMO, 5)) &
            ((funct7 & Const(0b1111100, 7)) == Const(0b0010100, 7)))


# Detect vector stores / 检测向量存储指令。
def isVecStore(inst: Any) -> Any:
    """Apply the V2 STORE_FP and WIDTH predicate. / 应用 V2 存储谓词。"""

    width = inst_field(inst, "WIDTH")
    opcode5 = inst_field(inst, "OPCODE5Bit")
    if isinstance(inst, int):
        return ((opcode5 == OPCODE5Bit.STORE_FP) and
                (width == 0 or bit_value(width, 2) == 1))
    return ((opcode5 == Const(OPCODE5Bit.STORE_FP, 5)) &
            ((width == Const(0, 3)) | (bit_value(width, 2) == Const(1, 1))))


# Detect vector loads / 检测向量加载指令。
def isVecLoad(inst: Any) -> Any:
    """Apply the V2 LOAD_FP and WIDTH predicate. / 应用 V2 加载谓词。"""

    width = inst_field(inst, "WIDTH")
    opcode5 = inst_field(inst, "OPCODE5Bit")
    if isinstance(inst, int):
        return ((opcode5 == OPCODE5Bit.LOAD_FP) and
                (width == 0 or bit_value(width, 2) == 1))
    return ((opcode5 == Const(OPCODE5Bit.LOAD_FP, 5)) &
            ((width == Const(0, 3)) | (bit_value(width, 2) == Const(1, 1))))


# Detect any vector arithmetic opcode / 检测向量算术操作码。
def isVecArith(inst: Any) -> Any:
    """Return true when OPCODE5Bit is OP_V. / 检测 OP_V。"""

    opcode5 = inst_field(inst, "OPCODE5Bit")
    return (opcode5 == OPCODE5Bit.OP_V if isinstance(inst, int)
            else opcode5 == Const(OPCODE5Bit.OP_V, 5))


# Match a vector arithmetic funct3 / 匹配向量算术 funct3。
def vec_arith_funct3(inst: Any, funct3: Any) -> Any:
    """Match opcode 0x57 and a funct3 value. / 匹配向量算术类别。"""

    opcode = inst_field(inst, "OPCODE")
    funct = inst_field(inst, "FUNCT3")
    if isinstance(inst, int):
        return (opcode == OPCODE7Bit.VECTOR_ARITH) and (funct == funct3)
    return ((opcode == Const(OPCODE7Bit.VECTOR_ARITH, 7)) &
            (funct == Const(funct3, 3)))


# Match OPIVV / 匹配 OPIVV。
def isOPIVV(inst: Any) -> Any:
    """Return true for OPIVV. / 检测 OPIVV。"""

    return vec_arith_funct3(inst, 0b000)


# Match OPFVV / 匹配 OPFVV。
def isOPFVV(inst: Any) -> Any:
    """Return true for OPFVV. / 检测 OPFVV。"""

    return vec_arith_funct3(inst, 0b001)


# Match OPMVV / 匹配 OPMVV。
def isOPMVV(inst: Any) -> Any:
    """Return true for OPMVV. / 检测 OPMVV。"""

    return vec_arith_funct3(inst, 0b010)


# Match OPIVI / 匹配 OPIVI。
def isOPIVI(inst: Any) -> Any:
    """Return true for OPIVI. / 检测 OPIVI。"""

    return vec_arith_funct3(inst, 0b011)


# Match OPIVX / 匹配 OPIVX。
def isOPIVX(inst: Any) -> Any:
    """Return true for OPIVX. / 检测 OPIVX。"""

    return vec_arith_funct3(inst, 0b100)


# Match OPFVF / 匹配 OPFVF。
def isOPFVF(inst: Any) -> Any:
    """Return true for OPFVF. / 检测 OPFVF。"""

    return vec_arith_funct3(inst, 0b101)


# Match OPMVX / 匹配 OPMVX。
def isOPMVX(inst: Any) -> Any:
    """Return true for OPMVX. / 检测 OPMVX。"""

    return vec_arith_funct3(inst, 0b110)


class Riscv32BitInst:
    """Integer façade for the Scala 32-bit instruction bundle. / 指令束门面。"""

    # Store a 32-bit instruction value / 保存 32 位指令值。
    def __init__(self, inst: int = 0) -> None:
        """Create a masked instruction value. / 创建并截断指令值。"""

        self.inst = inst & 0xFFFFFFFF

    # Extract a named field / 提取命名位域。
    def field(self, name: str) -> int:
        """Return one field from the stored instruction. / 返回指令位域。"""

        return int(inst_field(self.inst, name))

    # Decode the vector type immediate / 解码向量类型立即数。
    def get_inst_vtype(self) -> InstVType:
        """Decode ZIMM_VSETVLI into InstVType. / 解码 VTYPE。"""

        zimm = self.field("ZIMM_VSETVLI")
        return InstVType(
            reserved=0,
            vma=(zimm >> 7) & 1,
            vta=(zimm >> 6) & 1,
            vsew=(zimm >> 3) & 0x7,
            vlmul=zimm & 0x7,
        )

    # Check the RVK RNUM legality rule / 检查 RVK RNUM 合法性。
    def is_rnum_illegal(self) -> bool:
        """Return true when RNUM exceeds ten. / 检测非法 RNUM。"""

        return self.field("RNUM") > 0xA


class XSInstBitFields(Riscv32BitInst):
    """Complete V2 instruction field façade. / 完整 V2 指令位域门面。"""


class RiscvInstProbe(Elaboratable):
    """Expose fields and predicates for hardware differential tests. / 硬件探针。"""

    # Declare probe ports / 声明探针端口。
    def __init__(self) -> None:
        """Create the instruction probe signals. / 创建指令探针信号。"""

        self.inst = Signal(32, name="inst")
        self.opcode = Signal(7, name="opcode")
        self.opcode5 = Signal(5, name="opcode5")
        self.rd = Signal(5, name="rd")
        self.funct3 = Signal(3, name="funct3")
        self.rs1 = Signal(5, name="rs1")
        self.rs2 = Signal(5, name="rs2")
        self.funct7 = Signal(7, name="funct7")
        self.width = Signal(3, name="width")
        self.rnum = Signal(4, name="rnum")
        self.is_amo_cas = Signal(name="is_amo_cas")
        self.is_vec_store = Signal(name="is_vec_store")
        self.is_vec_load = Signal(name="is_vec_load")
        self.is_vec_arith = Signal(name="is_vec_arith")
        self.is_opivv = Signal(name="is_opivv")
        self.is_opfvv = Signal(name="is_opfvv")
        self.is_opmvv = Signal(name="is_opmvv")
        self.is_opivi = Signal(name="is_opivi")
        self.is_opivx = Signal(name="is_opivx")
        self.is_opfvf = Signal(name="is_opfvf")
        self.is_opmvx = Signal(name="is_opmvx")

    # Connect all source field slices / 连接全部源位域切片。
    def elaborate(self, platform: Any) -> Module:
        """Elaborate field and predicate outputs. / 展开位域与谓词输出。"""

        del platform
        module = Module()
        module.d.comb += [
            self.opcode.eq(inst_field(self.inst, "OPCODE")),
            self.opcode5.eq(inst_field(self.inst, "OPCODE5Bit")),
            self.rd.eq(inst_field(self.inst, "RD")),
            self.funct3.eq(inst_field(self.inst, "FUNCT3")),
            self.rs1.eq(inst_field(self.inst, "RS1")),
            self.rs2.eq(inst_field(self.inst, "RS2")),
            self.funct7.eq(inst_field(self.inst, "FUNCT7")),
            self.width.eq(inst_field(self.inst, "WIDTH")),
            self.rnum.eq(inst_field(self.inst, "RNUM")),
            self.is_amo_cas.eq(isAMOCAS(self.inst)),
            self.is_vec_store.eq(isVecStore(self.inst)),
            self.is_vec_load.eq(isVecLoad(self.inst)),
            self.is_vec_arith.eq(isVecArith(self.inst)),
            self.is_opivv.eq(isOPIVV(self.inst)),
            self.is_opfvv.eq(isOPFVV(self.inst)),
            self.is_opmvv.eq(isOPMVV(self.inst)),
            self.is_opivi.eq(isOPIVI(self.inst)),
            self.is_opivx.eq(isOPIVX(self.inst)),
            self.is_opfvf.eq(isOPFVF(self.inst)),
            self.is_opmvx.eq(isOPMVX(self.inst)),
        ]
        return module


# =============================================================================
# Public Adapter
# =============================================================================
# Emit deterministic Verilog for the bitfield probe / 输出位域探针 Verilog。
def build_verilog(configuration: Any = None,
                  injected_dependencies: dict[str, Any] | None = None) -> str:
    """Build the standalone RISC-V field probe. / 构建独立 RISC-V 位域探针。"""

    del configuration, injected_dependencies
    from amaranth.back import verilog

    top = RiscvInstProbe()
    ports = [
        top.inst, top.opcode, top.opcode5, top.rd, top.funct3, top.rs1,
        top.rs2, top.funct7, top.width, top.rnum, top.is_amo_cas,
        top.is_vec_store, top.is_vec_load, top.is_vec_arith, top.is_opivv,
        top.is_opfvv, top.is_opmvv, top.is_opivi, top.is_opivx, top.is_opfvf,
        top.is_opmvx,
    ]
    return verilog.convert(top, name="RiscvInst", ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print the direct-entry Verilog / 打印直接入口 Verilog。
def main() -> None:
    """Print a deterministic field probe. / 打印确定性位域探针。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
