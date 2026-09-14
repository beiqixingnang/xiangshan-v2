"""V2 CryptoUtils Boolean and GF(2^8) helpers. / V2 CryptoUtils 布尔与 GF(2^8) 辅助器。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from amaranth import Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# This module follows the locked V2 CryptoUtils.scala equations.  The S-box
# stages are Boolean networks (not identity placeholders): AES/IAES/SM4 top
# stages produce 21 bits, SboxInv produces 18 bits, and each output stage
# produces an 8-bit byte.  Chisel Cat ordering is translated to Amaranth's
# least-significant-first Cat ordering at every packed boundary.
# 本模块遵循锁定 V2 CryptoUtils.scala 方程。S-box 阶段为真实布尔网络（不是
# 恒等透传）：AES/IAES/SM4 top 输出 21 位，SboxInv 输出 18 位，各输出阶段
# 输出 8 位字节；所有打包边界均将 Chisel Cat 顺序转换为 Amaranth 低位优先顺序。
__all__ = [
    "CryptoUtilsConfig", "CryptoUtilsProbe", "SHR32", "SHR64", "ROR32", "ROR64",
    "ForwardShiftRows", "InverseShiftRows", "XtN", "Xt2", "ByteEnc", "ByteDec",
    "MixFwd", "MixInv", "SboxAesTop", "SboxAesOut", "SboxIaesTop", "SboxIaesOut",
    "SboxSm4Top", "SboxSm4Out", "SboxInv", "SboxAes", "SboxIaes", "SboxSm4",
    "evaluate_bit_network", "build_verilog", "main",
]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class CryptoUtilsConfig:
    """Configuration for the XLEN=64 V2 helper surface. / XLEN=64 V2 辅助器配置。"""

    xlen: int = 64

    # Validate the fixed V2 scalar width. / 校验 V2 固定标量宽度。
    def __post_init__(self) -> None:
        if self.xlen != 64:
            raise ValueError("V2 CryptoUtils is defined for XLEN=64")


# =============================================================================
# Implementation
# =============================================================================
# Identify software integers without importing host-specific helpers. / 识别软件整数且不引入主机相关辅助器。
def is_integer(value: Any) -> bool:
    return isinstance(value, int)


# Evaluate a compact one-bit equation graph for both integers and Amaranth Values.
# 为整数与 Amaranth Value 求值紧凑的一位方程图。
# Evaluate the named output equations / 求值命名输出方程。
def evaluate_bit_network(inputs: Sequence[Any], equations: dict[str, tuple[Any, ...]],
                         outputs: Sequence[str]) -> list[Any]:
    values: dict[str, Any] = {f"i{index}": value for index, value in enumerate(inputs)}

    # Resolve one named equation recursively. / 递归解析一个命名方程。
    def resolve(name: Any) -> Any:
        if not isinstance(name, str):
            if isinstance(name, tuple):
                operation = name[0]
                if operation == "const":
                    return int(name[1]) & 1
                if operation == "not":
                    operand = resolve(name[1])
                    return (1 ^ operand) if is_integer(operand) else (Const(1, 1) ^ operand)
                if operation == "xor":
                    return resolve(name[1]) ^ resolve(name[2])
                if operation == "and":
                    return resolve(name[1]) & resolve(name[2])
            raise ValueError(f"invalid bit equation: {name!r}")
        if name in values:
            return values[name]
        if name not in equations:
            raise KeyError(name)
        values[name] = resolve(equations[name])
        return values[name]

    return [resolve(name) for name in outputs]


# Return a constant-width integer or Amaranth value slice. / 返回定宽整数或 Amaranth 值切片。
def slice_value(value: Any, start: int, width: int) -> Any:
    if is_integer(value):
        return (value >> start) & ((1 << width) - 1)
    return value.bit_select(start, width)


# 32-bit logical right shift with V2's 64-bit result width. / 32 位逻辑右移并按 V2 输出 64 位。
def SHR32(bits: Any, shamt: int) -> Any:
    if not 0 < shamt < 32:
        raise ValueError("SHR32 shift amount must be in 1..31")
    if is_integer(bits):
        return (bits & 0xFFFFFFFF) >> shamt
    return Cat(slice_value(bits, shamt, 32 - shamt), Const(0, 32 + shamt))


# 64-bit logical right shift preserving the V2 shamt=63 special Cat. / 64 位逻辑右移并保留 V2 的 63 特殊拼接。
def SHR64(bits: Any, shamt: int) -> Any:
    if not 0 < shamt < 64:
        raise ValueError("SHR64 shift amount must be in 1..63")
    if is_integer(bits):
        if shamt == 63:
            return (((bits & ((1 << 63) - 1)) << 1) | ((bits >> 63) & 1))
        return (bits & ((1 << 64) - 1)) >> shamt
    if shamt == 63:
        # Source: Cat(bits(62,0), bits(63)); Cat arguments are reversed here.
        return Cat(slice_value(bits, 63, 1), slice_value(bits, 0, 63))
    return Cat(slice_value(bits, shamt, 64 - shamt), Const(0, shamt))


# 32-bit rotate-right, zero extended to 64 bits. / 32 位循环右移并零扩展至 64 位。
def ROR32(bits: Any, shamt: int) -> Any:
    if not 0 < shamt < 32:
        raise ValueError("ROR32 shift amount must be in 1..31")
    if is_integer(bits):
        value = bits & 0xFFFFFFFF
        return ((value >> shamt) | (value << (32 - shamt))) & 0xFFFFFFFF
    return Cat(slice_value(bits, shamt, 32 - shamt), slice_value(bits, 0, shamt), Const(0, 32))


# 64-bit rotate-right. / 64 位循环右移。
def ROR64(bits: Any, shamt: int) -> Any:
    if not 0 < shamt < 64:
        raise ValueError("ROR64 shift amount must be in 1..63")
    if is_integer(bits):
        value = bits & ((1 << 64) - 1)
        return ((value >> shamt) | (value << (64 - shamt))) & ((1 << 64) - 1)
    if shamt == 63:
        return Cat(slice_value(bits, 63, 1), slice_value(bits, 0, 63))
    return Cat(slice_value(bits, shamt, 64 - shamt), slice_value(bits, 0, shamt))


# AES forward ShiftRows byte permutation. / AES 正向 ShiftRows 字节置换。
def ForwardShiftRows(src1: Sequence[Any], src2: Sequence[Any]) -> list[Any]:
    if len(src1) != 8 or len(src2) != 8:
        raise ValueError("ShiftRows requires two eight-byte sequences")
    return [src1[0], src1[5], src2[2], src2[7], src1[4], src2[1], src2[6], src1[3]]


# AES inverse ShiftRows byte permutation. / AES 逆向 ShiftRows 字节置换。
def InverseShiftRows(src1: Sequence[Any], src2: Sequence[Any]) -> list[Any]:
    if len(src1) != 8 or len(src2) != 8:
        raise ValueError("ShiftRows requires two eight-byte sequences")
    return [src1[0], src2[5], src2[2], src1[7], src1[4], src1[1], src2[6], src2[3]]


# GF(2^8) multiply-by-two primitive. / GF(2^8) 乘二原语。
def Xt2(byte: Any) -> Any:
    if is_integer(byte):
        value = byte & 0xFF
        return ((value << 1) ^ (0x1B if value & 0x80 else 0)) & 0xFF
    shifted = byte << 1
    return (shifted ^ Mux(byte[7], Const(0x1B, 9), Const(0, 9))).bit_select(0, 8)


# GF(2^8) selector used by AES MixColumns. / AES MixColumns 使用的 GF(2^8) 选择器。
def XtN(byte: Any, t: Any) -> Any:
    if is_integer(byte) and is_integer(t):
        value = byte & 0xFF
        selector = t & 0xF
        result = 0
        term = value
        for index in range(4):
            if selector & (1 << index):
                result ^= term
            term = Xt2(term)
        return result & 0xFF
    if is_integer(t):
        t = Const(t & 0xF, 4)
    byte1 = Xt2(byte)
    byte2 = Xt2(byte1)
    byte3 = Xt2(byte2)
    result = Mux(t[0], byte, Const(0, 8))
    result = result ^ Mux(t[1], byte1, Const(0, 8))
    result = result ^ Mux(t[2], byte2, Const(0, 8))
    result = result ^ Mux(t[3], byte3, Const(0, 8))
    return result.bit_select(0, 8)


# One forward AES MixColumns row. / AES 正向 MixColumns 的一行。
def ByteEnc(bytes_: Sequence[Any]) -> Any:
    if len(bytes_) != 4:
        raise ValueError("ByteEnc requires four bytes")
    return XtN(bytes_[0], 0x2) ^ XtN(bytes_[1], 0x3) ^ bytes_[2] ^ bytes_[3]


# One inverse AES MixColumns row. / AES 逆向 MixColumns 的一行。
def ByteDec(bytes_: Sequence[Any]) -> Any:
    if len(bytes_) != 4:
        raise ValueError("ByteDec requires four bytes")
    return (XtN(bytes_[0], 0xE) ^ XtN(bytes_[1], 0xB) ^ XtN(bytes_[2], 0xD) ^ XtN(bytes_[3], 0x9))


# Pack four forward MixColumns rows with source-compatible byte order. / 按源兼容字节序打包四行正向混列。
def MixFwd(bytes_: Sequence[Any]) -> Any:
    if len(bytes_) != 4:
        raise ValueError("MixFwd requires four bytes")
    rows = [ByteEnc([bytes_[3], bytes_[0], bytes_[1], bytes_[2]]),
            ByteEnc([bytes_[2], bytes_[3], bytes_[0], bytes_[1]]),
            ByteEnc([bytes_[1], bytes_[2], bytes_[3], bytes_[0]]),
            ByteEnc([bytes_[0], bytes_[1], bytes_[2], bytes_[3]])]
    if all(is_integer(item) for item in rows):
        return sum((int(item) & 0xFF) << (8 * index) for index, item in enumerate(rows))
    return Cat(*reversed(rows))


# Pack four inverse MixColumns rows with source-compatible byte order. / 按源兼容字节序打包四行逆向混列。
def MixInv(bytes_: Sequence[Any]) -> Any:
    if len(bytes_) != 4:
        raise ValueError("MixInv requires four bytes")
    rows = [ByteDec([bytes_[3], bytes_[0], bytes_[1], bytes_[2]]),
            ByteDec([bytes_[2], bytes_[3], bytes_[0], bytes_[1]]),
            ByteDec([bytes_[1], bytes_[2], bytes_[3], bytes_[0]]),
            ByteDec([bytes_[0], bytes_[1], bytes_[2], bytes_[3]])]
    if all(is_integer(item) for item in rows):
        return sum((int(item) & 0xFF) << (8 * index) for index, item in enumerate(rows))
    return Cat(*reversed(rows))


# AES S-box affine top network. / AES S-box 仿射顶层网络。
def SboxAesTop(i: Any) -> list[Any]:
    inputs = [(i >> index) & 1 for index in range(8)] if is_integer(i) else [i[index] for index in range(8)]
    equations: dict[str, tuple[Any, ...]] = {
        "t0": ("xor", "i3", "i1"), "t1": ("xor", "i6", "i5"), "t2": ("xor", "i6", "i2"),
        "t3": ("xor", "i5", "i2"), "t4": ("xor", "i4", "i0"), "t5": ("xor", "i1", "i0"),
        "o0": "i0", "o1": ("xor", "i7", "i4"), "o2": ("xor", "i7", "i2"),
        "o3": ("xor", "i7", "i1"), "o4": ("xor", "i4", "i2"), "o5": ("xor", "o1", "t0"),
        "o6": ("xor", "i0", "o5"), "o7": ("xor", "i0", "t1"), "o8": ("xor", "o5", "t1"),
        "o9": ("xor", "o3", "o4"), "o10": ("xor", "o5", "t2"), "o11": ("xor", "t0", "t2"),
        "o12": ("xor", "t0", "t3"), "o13": ("xor", "o7", "o12"), "o14": ("xor", "t1", "t4"),
        "o15": ("xor", "o1", "o14"), "o16": ("xor", "t1", "t5"), "o17": ("xor", "o2", "o16"),
        "o18": ("xor", "o2", "o8"), "o19": ("xor", "o15", "o13"), "o20": ("xor", "o1", "t3"),
    }
    return evaluate_bit_network(inputs, equations, [f"o{index}" for index in range(21)])


# AES inverse-affine top network. / AES 逆 S-box 仿射顶层网络。
def SboxIaesTop(i: Any) -> list[Any]:
    inputs = [(i >> index) & 1 for index in range(8)] if is_integer(i) else [i[index] for index in range(8)]
    equations: dict[str, tuple[Any, ...]] = {
        "t0": ("xor", "i1", "i0"), "t1": ("xor", "i6", "i1"),
        "t2": ("xor", "i5", ("not", "i2")), "t3": ("xor", "i2", ("not", "i1")),
        "t4": ("xor", "i5", ("not", "i3")), "o0": ("xor", "i7", "t2"),
        "o1": ("xor", "i4", "i3"), "o2": ("xor", "i7", ("not", "i6")),
        "o3": ("xor", "o1", "t0"), "o4": ("xor", "i3", "o6"),
        "o5": ("xor", "o16", "t2"), "o6": ("xor", "i6", ("not", "o17")),
        "o7": ("xor", "i0", ("not", "o1")), "o8": ("xor", "o2", "o18"),
        "o9": ("xor", "o2", "t0"), "o10": ("xor", "o8", "t3"),
        "o11": ("xor", "o8", "o20"), "o12": ("xor", "t1", "t4"),
        "o13": ("xor", "i5", ("not", "o14")), "o14": ("xor", "o16", "t0"),
        "o15": ("xor", "o18", "t1"), "o16": ("xor", "i6", ("not", "i4")),
        "o17": ("xor", "i7", "i4"), "o18": ("xor", "i3", ("not", "i0")),
        "o19": ("xor", "i5", ("not", "o1")), "o20": ("xor", "o1", "t3"),
    }
    return evaluate_bit_network(inputs, equations, [f"o{index}" for index in range(21)])


# SM4 S-box affine top network. / SM4 S-box 仿射顶层网络。
def SboxSm4Top(i: Any) -> list[Any]:
    inputs = [(i >> index) & 1 for index in range(8)] if is_integer(i) else [i[index] for index in range(8)]
    equations: dict[str, tuple[Any, ...]] = {
        "t0": ("xor", "i3", "i4"), "t1": ("xor", "i2", "i7"), "t2": ("xor", "i7", "o18"),
        "t3": ("xor", "i1", "t1"), "t4": ("xor", "i6", "i7"), "t5": ("xor", "i0", "o18"),
        "t6": ("xor", "i3", "i6"), "o0": ("xor", "i5", ("not", "o10")),
        "o1": ("xor", "t0", "t3"), "o2": ("xor", "i0", "t0"), "o3": ("xor", "i3", "o4"),
        "o4": ("xor", "i0", "t3"), "o5": ("xor", "i5", "t5"), "o6": ("xor", "i0", ("not", "i1")),
        "o7": ("xor", "t0", ("not", "o10")), "o8": ("xor", "t0", "t5"), "o9": "i3",
        "o10": ("xor", "i1", "o18"), "o11": ("xor", "t0", "t4"), "o12": ("xor", "i5", "t4"),
        "o13": ("xor", "i5", ("not", "o1")), "o14": ("xor", "i4", ("not", "t2")),
        "o15": ("xor", "i1", ("not", "t6")), "o16": ("xor", "i0", ("not", "t2")),
        "o17": ("xor", "t0", ("not", "t2")), "o18": ("xor", "i2", "i6"),
        "o19": ("xor", "i5", ("not", "o14")), "o20": ("xor", "i0", "t1"),
    }
    return evaluate_bit_network(inputs, equations, [f"o{index}" for index in range(21)])


# Shared 21-to-18 Boolean middle network. / 共用的 21 到 18 位布尔中间网络。
def SboxInv(i: Sequence[Any]) -> list[Any]:
    if len(i) != 21:
        raise ValueError("SboxInv requires 21 input bits")
    equations: dict[str, tuple[Any, ...]] = {
        "t0": ("xor", "i3", "i12"), "t1": ("and", "i9", "i5"), "t2": ("and", "i17", "i6"),
        "t3": ("xor", "i10", "t1"), "t4": ("and", "i14", "i0"), "t5": ("xor", "t4", "t1"),
        "t6": ("and", "i3", "i12"), "t7": ("and", "i16", "i7"), "t8": ("xor", "t0", "t6"),
        "t9": ("and", "i15", "i13"), "t10": ("xor", "t9", "t6"), "t11": ("and", "i1", "i11"),
        "t12": ("and", "i4", "i20"), "t13": ("xor", "t12", "t11"), "t14": ("and", "i2", "i8"),
        "t15": ("xor", "t14", "t11"), "t16": ("xor", "t3", "t2"), "t17": ("xor", "t5", "i18"),
        "t18": ("xor", "t8", "t7"), "t19": ("xor", "t10", "t15"), "t20": ("xor", "t16", "t13"),
        "t21": ("xor", "t17", "t15"), "t22": ("xor", "t18", "t13"), "t23": ("xor", "t19", "i19"),
        "t24": ("xor", "t22", "t23"), "t25": ("and", "t22", "t20"), "t26": ("xor", "t21", "t25"),
        "t27": ("xor", "t20", "t21"), "t28": ("xor", "t23", "t25"), "t29": ("and", "t28", "t27"),
        "t30": ("and", "t26", "t24"), "t31": ("and", "t20", "t23"), "t32": ("and", "t27", "t31"),
        "t33": ("xor", "t27", "t25"), "t34": ("and", "t21", "t22"), "t35": ("and", "t24", "t34"),
        "t36": ("xor", "t24", "t25"), "t37": ("xor", "t21", "t29"), "t38": ("xor", "t32", "t33"),
        "t39": ("xor", "t23", "t30"), "t40": ("xor", "t35", "t36"), "t41": ("xor", "t38", "t40"),
        "t42": ("xor", "t37", "t39"), "t43": ("xor", "t37", "t38"), "t44": ("xor", "t39", "t40"),
        "t45": ("xor", "t42", "t41"), "o0": ("and", "t38", "i7"), "o1": ("and", "t37", "i13"),
        "o2": ("and", "t42", "i11"), "o3": ("and", "t45", "i20"), "o4": ("and", "t41", "i8"),
        "o5": ("and", "t44", "i9"), "o6": ("and", "t40", "i17"), "o7": ("and", "t39", "i14"),
        "o8": ("and", "t43", "i3"), "o9": ("and", "t38", "i16"), "o10": ("and", "t37", "i15"),
        "o11": ("and", "t42", "i1"), "o12": ("and", "t45", "i4"), "o13": ("and", "t41", "i2"),
        "o14": ("and", "t44", "i5"), "o15": ("and", "t40", "i6"), "o16": ("and", "t39", "i0"),
        "o17": ("and", "t43", "i12"),
    }
    inputs = list(i)
    return evaluate_bit_network(inputs, equations, [f"o{index}" for index in range(18)])


# AES output affine network. / AES 输出仿射网络。
def SboxAesOut(i: Sequence[Any]) -> Any:
    if len(i) != 18:
        raise ValueError("SboxAesOut requires 18 input bits")
    equations: dict[str, tuple[Any, ...]] = {
        "t0": ("xor", "i11", "i12"), "t1": ("xor", "i0", "i6"), "t2": ("xor", "i14", "i16"),
        "t3": ("xor", "i15", "i5"), "t4": ("xor", "i4", "i8"), "t5": ("xor", "i17", "i11"),
        "t6": ("xor", "i12", "t5"), "t7": ("xor", "i14", "t3"), "t8": ("xor", "i1", "i9"),
        "t9": ("xor", "i2", "i3"), "t10": ("xor", "i3", "t4"), "t11": ("xor", "i10", "t2"),
        "t12": ("xor", "i16", "i1"), "t13": ("xor", "i0", "t0"), "t14": ("xor", "i2", "i11"),
        "t15": ("xor", "i5", "t1"), "t16": ("xor", "i6", "t0"), "t17": ("xor", "i7", "t1"),
        "t18": ("xor", "i8", "t8"), "t19": ("xor", "i13", "t4"), "t20": ("xor", "t0", "t1"),
        "t21": ("xor", "t1", "t7"), "t22": ("xor", "t3", "t12"), "t23": ("xor", "t18", "t2"),
        "t24": ("xor", "t15", "t9"), "t25": ("xor", "t6", "t10"), "t26": ("xor", "t7", "t9"),
        "t27": ("xor", "t8", "t10"), "t28": ("xor", "t11", "t14"), "t29": ("xor", "t11", "t17"),
        "o0": ("xor", "t6", ("not", "t23")), "o1": ("xor", "t13", ("not", "t27")),
        "o2": ("xor", "t25", "t29"), "o3": ("xor", "t20", "t22"), "o4": ("xor", "t6", "t21"),
        "o5": ("xor", "t19", ("not", "t28")), "o6": ("xor", "t16", ("not", "t26")), "o7": ("xor", "t6", "t24"),
    }
    outputs = evaluate_bit_network(list(i), equations, [f"o{index}" for index in range(8)])
    if all(is_integer(item) for item in outputs):
        return sum((int(item) & 1) << index for index, item in enumerate(outputs))
    return Cat(*outputs)


# IAES output affine network. / IAES 输出仿射网络。
def SboxIaesOut(i: Sequence[Any]) -> Any:
    if len(i) != 18:
        raise ValueError("SboxIaesOut requires 18 input bits")
    equations: dict[str, tuple[Any, ...]] = {
        "t0": ("xor", "i2", "i11"), "t1": ("xor", "i8", "i9"), "t2": ("xor", "i4", "i12"),
        "t3": ("xor", "i15", "i0"), "t4": ("xor", "i16", "i6"), "t5": ("xor", "i14", "i1"),
        "t6": ("xor", "i17", "i10"), "t7": ("xor", "t0", "t1"), "t8": ("xor", "i0", "i3"),
        "t9": ("xor", "i5", "i13"), "t10": ("xor", "i7", "t4"), "t11": ("xor", "t0", "t3"),
        "t12": ("xor", "i14", "i16"), "t13": ("xor", "i17", "i1"), "t14": ("xor", "i17", "i12"),
        "t15": ("xor", "i4", "i9"), "t16": ("xor", "i7", "i11"), "t17": ("xor", "i8", "t2"),
        "t18": ("xor", "i13", "t5"), "t19": ("xor", "t2", "t3"), "t20": ("xor", "t4", "t6"),
        "t21": ("const", 0), "t22": ("xor", "t2", "t7"), "t23": ("xor", "t7", "t8"),
        "t24": ("xor", "t5", "t7"), "t25": ("xor", "t6", "t10"), "t26": ("xor", "t9", "t11"),
        "t27": ("xor", "t10", "t18"), "t28": ("xor", "t11", "t25"), "t29": ("xor", "t15", "t20"),
        "o0": ("xor", "t9", "t16"), "o1": ("xor", "t14", "t23"), "o2": ("xor", "t19", "t24"),
        "o3": ("xor", "t23", "t27"), "o4": ("xor", "t12", "t22"), "o5": ("xor", "t17", "t28"),
        "o6": ("xor", "t26", "t29"), "o7": ("xor", "t13", "t22"),
    }
    outputs = evaluate_bit_network(list(i), equations, [f"o{index}" for index in range(8)])
    if all(is_integer(item) for item in outputs):
        return sum((int(item) & 1) << index for index, item in enumerate(outputs))
    return Cat(*outputs)


# SM4 output affine network. / SM4 输出仿射网络。
def SboxSm4Out(i: Sequence[Any]) -> Any:
    if len(i) != 18:
        raise ValueError("SboxSm4Out requires 18 input bits")
    equations: dict[str, tuple[Any, ...]] = {
        "t0": ("xor", "i4", "i7"), "t1": ("xor", "i13", "i15"), "t2": ("xor", "i2", "i16"),
        "t3": ("xor", "i6", "t0"), "t4": ("xor", "i12", "t1"), "t5": ("xor", "i9", "i10"),
        "t6": ("xor", "i11", "t2"), "t7": ("xor", "i1", "t4"), "t8": ("xor", "i0", "i17"),
        "t9": ("xor", "i3", "i17"), "t10": ("xor", "i8", "t3"), "t11": ("xor", "t2", "t5"),
        "t12": ("xor", "i14", "t6"), "t13": ("xor", "t7", "t9"), "t14": ("xor", "i0", "i6"),
        "t15": ("xor", "i7", "i16"), "t16": ("xor", "i5", "i13"), "t17": ("xor", "i3", "i15"),
        "t18": ("xor", "i10", "i12"), "t19": ("xor", "i9", "t1"), "t20": ("xor", "i4", "t4"),
        "t21": ("xor", "i14", "t3"), "t22": ("xor", "i16", "t5"), "t23": ("xor", "t7", "t14"),
        "t24": ("xor", "t8", "t11"), "t25": ("xor", "t0", "t12"), "t26": ("xor", "t17", "t3"),
        "t27": ("xor", "t18", "t10"), "t28": ("xor", "t19", "t6"), "t29": ("xor", "t8", "t10"),
        "o0": ("xor", "t11", ("not", "t13")), "o1": ("xor", "t15", ("not", "t23")),
        "o2": ("xor", "t20", "t24"), "o3": ("xor", "t16", "t25"), "o4": ("xor", "t26", ("not", "t22")),
        "o5": ("xor", "t21", "t13"), "o6": ("xor", "t27", ("not", "t12")), "o7": ("xor", "t28", ("not", "t29")),
    }
    outputs = evaluate_bit_network(list(i), equations, [f"o{index}" for index in range(8)])
    if all(is_integer(item) for item in outputs):
        return sum((int(item) & 1) << index for index, item in enumerate(outputs))
    return Cat(*outputs)


# Complete AES S-box composition. / 完整 AES S-box 组合。
def SboxAes(byte: Any) -> Any:
    return SboxAesOut(SboxInv(SboxAesTop(byte)))


# Complete inverse AES S-box composition. / 完整 AES 逆 S-box 组合。
def SboxIaes(byte: Any) -> Any:
    return SboxIaesOut(SboxInv(SboxIaesTop(byte)))


# Complete SM4 S-box composition. / 完整 SM4 S-box 组合。
def SboxSm4(byte: Any) -> Any:
    return SboxSm4Out(SboxInv(SboxSm4Top(byte)))


class CryptoUtilsProbe(Elaboratable):
    """Expose source helper observation points for deterministic checks. / 暴露源辅助器观测点供确定性检查。"""

    # Construct the fixed-width probe ports. / 构造固定宽度 probe 端口。
    def __init__(self, configuration: CryptoUtilsConfig | None = None) -> None:
        self.configuration = configuration or CryptoUtilsConfig()
        self.src1 = Signal(64, name="src1")
        self.src2 = Signal(64, name="src2")
        self.byte = Signal(8, name="input_byte")
        self.coeff = Signal(4, name="coeff")
        self.inv_input = Signal(21, name="inv_input")
        self.shr32 = Signal(64, name="shr32")
        self.shr64 = Signal(64, name="shr64")
        self.ror32 = Signal(64, name="ror32")
        self.ror64 = Signal(64, name="ror64")
        self.forward_rows = Signal(64, name="forward_rows")
        self.inverse_rows = Signal(64, name="inverse_rows")
        self.xt2 = Signal(8, name="xt2")
        self.xtn = Signal(8, name="xtn")
        self.byte_enc = Signal(8, name="byte_enc")
        self.byte_dec = Signal(8, name="byte_dec")
        self.mix_fwd = Signal(32, name="mix_fwd")
        self.mix_inv = Signal(32, name="mix_inv")
        self.aes_top = Signal(21, name="aes_top")
        self.iaes_top = Signal(21, name="iaes_top")
        self.sm4_top = Signal(21, name="sm4_top")
        self.inv_mid = Signal(18, name="inv_mid")
        self.aes_out = Signal(8, name="aes_out")
        self.iaes_out = Signal(8, name="iaes_out")
        self.sm4_out = Signal(8, name="sm4_out")
        self.aes = Signal(8, name="aes")
        self.iaes = Signal(8, name="iaes")
        self.sm4 = Signal(8, name="sm4")

    # Elaborate all combinational helper observation points. / 展开全部组合式辅助器观测点。
    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        src1_bytes = [slice_value(self.src1, index * 8, 8) for index in range(8)]
        src2_bytes = [slice_value(self.src2, index * 8, 8) for index in range(8)]
        fwd = ForwardShiftRows(src1_bytes, src2_bytes)
        inv = InverseShiftRows(src1_bytes, src2_bytes)
        mix_bytes = src1_bytes[:4]
        aes_top = SboxAesTop(self.byte)
        iaes_top = SboxIaesTop(self.byte)
        sm4_top = SboxSm4Top(self.byte)
        aes_top_wire = Signal(21, name="aes_top_wire")
        iaes_top_wire = Signal(21, name="iaes_top_wire")
        sm4_top_wire = Signal(21, name="sm4_top_wire")
        aes_mid_wire = Signal(18, name="aes_mid_wire")
        iaes_mid_wire = Signal(18, name="iaes_mid_wire")
        sm4_mid_wire = Signal(18, name="sm4_mid_wire")
        inv_mid = SboxInv(self.inv_input)
        module.d.comb += [
            self.shr32.eq(SHR32(slice_value(self.src1, 0, 32), 3)),
            self.shr64.eq(SHR64(self.src1, 7)), self.ror32.eq(ROR32(slice_value(self.src1, 0, 32), 2)),
            self.ror64.eq(ROR64(self.src1, 1)), self.forward_rows.eq(Cat(*fwd)),
            self.inverse_rows.eq(Cat(*inv)), self.xt2.eq(Xt2(self.byte)),
            self.xtn.eq(XtN(self.byte, self.coeff)), self.byte_enc.eq(ByteEnc(mix_bytes)),
            self.byte_dec.eq(ByteDec(mix_bytes)), self.mix_fwd.eq(MixFwd(mix_bytes)),
            self.mix_inv.eq(MixInv(mix_bytes)), aes_top_wire.eq(Cat(*aes_top)),
            iaes_top_wire.eq(Cat(*iaes_top)), sm4_top_wire.eq(Cat(*sm4_top)),
            aes_mid_wire.eq(Cat(*SboxInv([aes_top_wire[index] for index in range(21)]))),
            iaes_mid_wire.eq(Cat(*SboxInv([iaes_top_wire[index] for index in range(21)]))),
            sm4_mid_wire.eq(Cat(*SboxInv([sm4_top_wire[index] for index in range(21)]))),
            self.aes_top.eq(aes_top_wire), self.iaes_top.eq(iaes_top_wire),
            self.sm4_top.eq(sm4_top_wire), self.inv_mid.eq(Cat(*inv_mid)),
            self.aes_out.eq(SboxAesOut([aes_mid_wire[index] for index in range(18)])),
            self.iaes_out.eq(SboxIaesOut([iaes_mid_wire[index] for index in range(18)])),
            self.sm4_out.eq(SboxSm4Out([sm4_mid_wire[index] for index in range(18)])),
            self.aes.eq(self.aes_out), self.iaes.eq(self.iaes_out), self.sm4.eq(self.sm4_out),
        ]
        return module


class CryptoBlockProbe(Elaboratable):
    """Source-shaped AES/SM4 parent closure for reference differential tests. / 用于参考差分的源形 AES/SM4 父闭包。"""

    # Construct the one-cycle V2 BlockCipherModule interface. / 构造 V2 BlockCipherModule 的单周期接口。
    def __init__(self, configuration: CryptoUtilsConfig | None = None) -> None:
        self.configuration = configuration or CryptoUtilsConfig()
        self.clock = Signal(name="clock")
        self.clock_domain = ClockDomain("sync")
        self.clock_domain.clk = self.clock
        self.src0 = Signal(64, name="io_src_0")
        self.src1 = Signal(64, name="io_src_1")
        self.func = Signal(9, name="io_func")
        self.reg_enable = Signal(name="io_regEnable")
        self.out = Signal(64, name="io_out")

    # Elaborate the registered S-box, key-schedule, and SM4 closure. / 展开寄存式 S-box、密钥调度及 SM4 闭包。
    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        module.domains += self.clock_domain
        src1_bytes = [slice_value(self.src0, index * 8, 8) for index in range(8)]
        src2_bytes = [slice_value(self.src1, index * 8, 8) for index in range(8)]
        func_reg = Signal(9, name="funcReg")
        with module.If(self.reg_enable):
            module.d.sync += func_reg.eq(self.func)

        aes_in = ForwardShiftRows(src1_bytes, src2_bytes)
        iaes_in = InverseShiftRows(src1_bytes, src2_bytes)
        aes_top = [Signal(21, name=f"aesSboxTop_{index}") for index in range(8)]
        iaes_top = [Signal(21, name=f"iaesSboxTop_{index}") for index in range(8)]
        aes_mid = [Signal(18, name=f"aesSboxMid_{index}") for index in range(8)]
        iaes_mid = [Signal(18, name=f"iaesSboxMid_{index}") for index in range(8)]
        aes_out = [SboxAesOut([aes_mid[index][bit] for bit in range(18)]) for index in range(8)]
        iaes_out = [SboxIaesOut([iaes_mid[index][bit] for bit in range(18)]) for index in range(8)]
        for index in range(8):
            module.d.comb += [
                aes_top[index].eq(Cat(*SboxAesTop(aes_in[index]))),
                iaes_top[index].eq(Cat(*SboxIaesTop(iaes_in[index]))),
            ]
            with module.If(self.reg_enable):
                module.d.sync += [
                    aes_mid[index].eq(Cat(*SboxInv([aes_top[index][bit] for bit in range(21)]))),
                    iaes_mid[index].eq(Cat(*SboxInv([iaes_top[index][bit] for bit in range(21)]))),
                ]
        aes64es = Cat(*aes_out)
        aes64ds = Cat(*iaes_out)

        im_min = [Signal(8, name=f"imMinIn_{index}") for index in range(8)]
        with module.If(self.reg_enable):
            module.d.sync += [im_min[index].eq(src1_bytes[index]) for index in range(8)]
        aes64esm = Cat(MixFwd(aes_out[:4]), MixFwd(aes_out[4:8]))
        aes64dsm = Cat(MixInv(iaes_out[:4]), MixInv(iaes_out[4:8]))
        aes64im = Cat(MixInv(im_min[:4]), MixInv(im_min[4:8]))

        rcon_values = (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36, 0x00)
        ks_in = [Mux(src2_bytes[0][:4] == 0xA, src1_bytes[4 + index], src1_bytes[5 + index] if index < 3 else src1_bytes[4])
                 for index in range(4)]
        ks_top = [Signal(21, name=f"ksSboxTop_{index}") for index in range(4)]
        ks_out = [SboxAesOut([bit for bit in SboxInv([ks_top[index][b] for b in range(21)])]) for index in range(4)]
        with module.If(self.reg_enable):
            module.d.sync += [ks_top[index].eq(Cat(*SboxAesTop(ks_in[index]))) for index in range(4)]
        ks_idx = Signal(4, name="ks1Idx")
        with module.If(self.reg_enable):
            module.d.sync += ks_idx.eq(src2_bytes[0][:4])
        rcon = Const(0, 8)
        for index, value in enumerate(rcon_values):
            rcon = Mux(ks_idx == index, Const(value, 8), rcon)
        ks_word = Cat(*ks_out)
        aes64ks1i = Cat(ks_word ^ Cat(rcon, rcon, rcon, rcon), ks_word ^ Cat(rcon, rcon, rcon, rcon))
        ks2_temp = slice_value(self.src0, 32, 32) ^ slice_value(self.src1, 0, 32)
        ks2_reg = Signal(64, name="aes64ks2Reg")
        with module.If(self.reg_enable):
            module.d.sync += ks2_reg.eq(Cat(ks2_temp, slice_value(self.src0, 32, 32) ^ slice_value(self.src1, 32, 32)))

        aes_result = aes64es
        for index, expression in ((0x20, aes64es), (0x21, aes64esm), (0x22, aes64ds),
                                  (0x23, aes64dsm), (0x24, aes64im), (0x25, aes64ks1i),
                                  (0x26, ks2_reg)):
            aes_result = Mux(func_reg == index, expression, aes_result)

        sm4_index = self.func[:2]
        sm4_input = src2_bytes[0]
        for index in range(1, 4):
            sm4_input = Mux(sm4_index == index, src2_bytes[index], sm4_input)
        sm4_top = Signal(21, name="sm4SboxTop")
        with module.If(self.reg_enable):
            module.d.sync += sm4_top.eq(Cat(*SboxSm4Top(sm4_input)))
        sm4_sbox_out = SboxSm4Out([bit for bit in SboxInv([sm4_top[index] for index in range(21)])])
        sm4_wide = Cat(sm4_sbox_out, Const(0, 24))
        sm4ed = (sm4_wide ^ (sm4_wide << 8) ^ (sm4_wide << 2) ^ (sm4_wide << 18) ^
                 ((sm4_wide & Const(0x3F, 32)) << 26) ^ ((sm4_wide & Const(0xC0, 32)) << 10)).bit_select(0, 32)
        sm4ks = (sm4_wide ^ ((sm4_wide & Const(0x07, 32)) << 29) ^ ((sm4_wide & Const(0xFE, 32)) << 7) ^
                 ((sm4_wide & Const(0x01, 32)) << 23) ^ ((sm4_wide & Const(0xF8, 32)) << 13)).bit_select(0, 32)
        sm4_source = [
            sm4ed,
            Cat(sm4ed[8:32], sm4ed[0:8]), Cat(sm4ed[16:32], sm4ed[0:16]), Cat(sm4ed[24:32], sm4ed[0:24]),
            sm4ks,
            Cat(sm4ks[8:32], sm4ks[0:8]), Cat(sm4ks[16:32], sm4ks[0:16]), Cat(sm4ks[24:32], sm4ks[0:24]),
        ]
        sm4_src1_lo = Signal(32, name="sm4Src1Lo")
        with module.If(self.reg_enable):
            module.d.sync += sm4_src1_lo.eq(slice_value(self.src0, 0, 32))
        sm4_selected = sm4_source[0]
        for index in range(1, 8):
            sm4_selected = Mux(func_reg[:3] == index, sm4_source[index], sm4_selected)
        sm4_result = Cat((sm4_selected ^ sm4_src1_lo)[0:32], *[((sm4_selected ^ sm4_src1_lo)[31]) for _ in range(32)])
        module.d.comb += self.out.eq(Mux(func_reg[3], sm4_result, aes_result))
        return module


# =============================================================================
# Public Adapter
# =============================================================================
# Build deterministic helper Verilog with all declared observation ports. / 构建带全部观测端口的确定性辅助器 Verilog。
def build_verilog(configuration, injected_dependencies) -> str:
    del injected_dependencies
    if configuration is None:
        config = CryptoUtilsConfig()
    elif isinstance(configuration, CryptoUtilsConfig):
        config = configuration
    elif isinstance(configuration, dict):
        config = CryptoUtilsConfig(xlen=int(configuration.get("xlen", 64)))
    else:
        raise TypeError("configuration must be CryptoUtilsConfig, dict, or None")
    top = CryptoUtilsProbe(config)
    ports = [value for value in vars(top).values() if isinstance(value, Signal)]
    return verilog.convert(top, name="CryptoUtilsProbe", ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print the default helper export for bounded direct checks. / 输出默认辅助器导出供有界 direct 检查。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
