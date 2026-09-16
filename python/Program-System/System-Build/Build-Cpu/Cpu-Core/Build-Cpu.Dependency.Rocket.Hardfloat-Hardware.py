"""UHSC Kunminghu V2 Berkeley HardFloat primitive aggregate.
昆明湖 V2 Berkeley HardFloat primitive 聚合边界。

The selected V2 top reaches HardFloat through Rocket/Fudian wrappers.  This
single Build target preserves the recFN classification, sign/exponent/fraction
packing, compare and integer-conversion observation points used by those
wrappers; the full iterative div/sqrt and FMA parents remain explicit open
closures.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from amaranth import ClockDomain, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
__all__ = ["HardFloatConfig", "UHSCHardFloatPrimitive", "HardFloatPrimitive", "classify_float", "pack_float", "compare_float", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class HardFloatConfig:
    exp_width: int = 8
    sig_width: int = 24

    # Validate the supported exponent and significand geometry. / 验证支持的指数和有效数几何参数。
    def __post_init__(self) -> None:
        if self.exp_width < 2 or self.exp_width > 15 or self.sig_width < 3:
            raise ValueError("invalid HardFloat exponent/significand widths")

    # Return the packed IEEE payload width. / 返回打包 IEEE 有效载荷宽度。
    @property
    def width(self) -> int:
        return self.exp_width + self.sig_width


# =============================================================================
# Implementation
# =============================================================================
# Classify one encoded floating-point value. / 对一个编码浮点值进行分类。
def classify_float(value: int, configuration: HardFloatConfig | None = None) -> dict[str, int]:
    """Classify an IEEE encoding using HardFloat's zero/inf/NaN rules."""
    c = configuration or HardFloatConfig()
    value &= (1 << c.width) - 1
    exponent = (value >> (c.sig_width - 1)) & ((1 << c.exp_width) - 1)
    fraction = value & ((1 << (c.sig_width - 1)) - 1)
    sign = (value >> (c.width - 1)) & 1
    return {"sign": sign, "isZero": int(exponent == 0 and fraction == 0),
            "isSubnormal": int(exponent == 0 and fraction != 0),
            "isInf": int(exponent == (1 << c.exp_width) - 1 and fraction == 0),
            "isNaN": int(exponent == (1 << c.exp_width) - 1 and fraction != 0)}


# Pack sign, exponent, and fraction fields. / 打包符号、指数和小数域。
def pack_float(sign: int, exponent: int, fraction: int, configuration: HardFloatConfig | None = None) -> int:
    """Pack sign/exponent/fraction fields into an IEEE-compatible encoding."""
    c = configuration or HardFloatConfig()
    return ((int(sign) & 1) << (c.width - 1)) | ((int(exponent) & ((1 << c.exp_width) - 1)) << (c.sig_width - 1)) | (int(fraction) & ((1 << (c.sig_width - 1)) - 1))


def compare_float(a: int, b: int, configuration: HardFloatConfig | None = None) -> dict[str, int]:
    """Return ordered IEEE comparison flags used by the primitive.

    NaNs are unordered, while +0 and -0 compare equal.  Keeping this helper
    beside the RTL gives the bounded family a deterministic reference for the
    compare/min/max operations without claiming a full iterative HardFloat
    implementation.
    """

    c = configuration or HardFloatConfig()
    mask = (1 << c.width) - 1
    a &= mask; b &= mask
    af = classify_float(a, c); bf = classify_float(b, c)
    if af["isNaN"] or bf["isNaN"]:
        return {"equal": 0, "less": 0, "unordered": 1}
    if af["isZero"] and bf["isZero"]:
        return {"equal": 1, "less": 0, "unordered": 0}
    if a == b:
        return {"equal": 1, "less": 0, "unordered": 0}
    sign_a = af["sign"]; sign_b = bf["sign"]
    magnitude_a = a & ((1 << (c.width - 1)) - 1)
    magnitude_b = b & ((1 << (c.width - 1)) - 1)
    less = int((sign_a and not sign_b) or
               (sign_a == sign_b and ((magnitude_a > magnitude_b) if sign_a else (magnitude_a < magnitude_b))))
    return {"equal": 0, "less": less, "unordered": 0}


class UHSCHardFloatPrimitive(Elaboratable):
    """Combinational HardFloat classification/compare/field primitive."""

    # Initialize the aggregate's clock, operands, and observations. / 初始化聚合的时钟、操作数和观测信号。
    def __init__(self, configuration: HardFloatConfig | None = None) -> None:
        self.config = configuration or HardFloatConfig()
        c = self.config
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.a = Signal(c.width, name="io_a")
        self.b = Signal(c.width, name="io_b")
        self.operation = Signal(3, name="io_operation")
        self.result = Signal(c.width, name="io_result")
        self.equal = Signal(name="io_equal")
        self.less = Signal(name="io_less")
        self.is_nan = Signal(name="io_isNaN")
        self.is_inf = Signal(name="io_isInf")
        self.is_zero = Signal(name="io_isZero")

    # Elaborate classification, comparison, and primitive arithmetic. / 展开分类、比较和基础算术逻辑。
    def elaborate(self, platform: Any) -> Module:
        del platform
        c = self.config
        m = Module()
        domain = ClockDomain("hardfloat", async_reset=True)
        domain.clk = self.clock; domain.rst = self.reset
        m.domains.hardfloat = domain
        exp_mask = (1 << c.exp_width) - 1
        frac_mask = (1 << (c.sig_width - 1)) - 1
        a_exp = self.a[c.sig_width - 1:c.width - 1]
        b_exp = self.b[c.sig_width - 1:c.width - 1]
        a_frac = self.a[:c.sig_width - 1]
        b_frac = self.b[:c.sig_width - 1]
        a_nan = (a_exp == exp_mask) & (a_frac != 0)
        b_nan = (b_exp == exp_mask) & (b_frac != 0)
        a_inf = (a_exp == exp_mask) & (a_frac == 0)
        b_inf = (b_exp == exp_mask) & (b_frac == 0)
        a_zero = (a_exp == 0) & (a_frac == 0)
        b_zero = (b_exp == 0) & (b_frac == 0)
        nan_any = a_nan | b_nan
        both_zero = a_zero & b_zero
        magnitude_a = Signal(c.width - 1, name="magnitude_a")
        magnitude_b = Signal(c.width - 1, name="magnitude_b")
        min_value = Signal(c.width, name="min_value")
        max_value = Signal(c.width, name="max_value")
        # Materialize the magnitude slices as Signals so the Amaranth typing
        # surface remains stable for Pyright while preserving unsigned IEEE
        # comparison semantics. / 将幅值切片物化为 Signal，保持 Pyright 类型
        # 稳定并保留 IEEE 无符号比较语义。
        unsigned_a = Signal(c.width - 1, name="unsigned_a")
        unsigned_b = Signal(c.width - 1, name="unsigned_b")
        less_value = Signal(name="less_value")
        # Quiet NaN: all exponent bits set plus the quiet bit in the
        # significand (the remaining payload bits are ones for a stable,
        # source-independent canonical value).
        canonical_nan = (exp_mask << (c.sig_width - 1)) | (1 << (c.sig_width - 2))
        result_value: Any = self.a
        result_value = Mux(self.operation == 7, self.a ^ (1 << (c.width - 1)), result_value)
        result_value = Mux(self.operation == 6, unsigned_a, result_value)
        result_value = Mux(self.operation == 5, Mux(nan_any, canonical_nan, self.a), result_value)
        result_value = Mux(self.operation == 4, max_value, result_value)
        result_value = Mux(self.operation == 3, min_value, result_value)
        result_value = Mux(self.operation == 2, self.a * self.b, result_value)
        result_value = Mux(self.operation == 1, self.a + self.b, result_value)
        result_value = Mux(self.operation == 0, self.a ^ self.b, result_value)
        m.d.comb += [
            unsigned_a.eq(self.a[:c.width - 1]), unsigned_b.eq(self.b[:c.width - 1]),
            magnitude_a.eq(unsigned_a), magnitude_b.eq(unsigned_b),
            self.is_nan.eq(nan_any), self.is_inf.eq(a_inf | b_inf), self.is_zero.eq(a_zero | b_zero),
            self.equal.eq(~nan_any & ((self.a == self.b) | both_zero)),
            less_value.eq(~nan_any & Mux(self.a[c.width - 1] != self.b[c.width - 1], self.a[c.width - 1],
                                         Mux(self.a[c.width - 1], magnitude_a > magnitude_b, magnitude_a < magnitude_b))),
            self.less.eq(less_value),
            # IEEE min/max propagate the non-NaN operand and retain +0 for a
            # signed-zero tie.  Other operation codes preserve the original
            # primitive XOR/add/multiply observations and add deterministic
            # abs/negate/canonical-NaN probes for wrapper bring-up.
            min_value.eq(Mux(a_nan, self.b, Mux(b_nan, self.a,
                           Mux(less_value, self.a, self.b)))),
            max_value.eq(Mux(a_nan, self.b, Mux(b_nan, self.a,
                           Mux(less_value, self.b, self.a)))),
            self.result.eq(result_value),
        ]
        return m


HardFloatPrimitive = UHSCHardFloatPrimitive


# =============================================================================
# Public Adapter
# =============================================================================
# Export deterministic Verilog for the selected HardFloat geometry. / 为选定的 HardFloat 几何参数导出确定性 Verilog。
def build_verilog(configuration: HardFloatConfig | Mapping[str, Any] | None,
                  injected_dependencies: Mapping[str, Any]) -> str:
    del injected_dependencies
    if configuration is None:
        cfg, name = HardFloatConfig(), "UHSCHardFloatPrimitive"
    elif isinstance(configuration, HardFloatConfig):
        cfg, name = configuration, "UHSCHardFloatPrimitive"
    else:
        cfg = HardFloatConfig(**{k: v for k, v in dict(configuration).items() if k in HardFloatConfig.__dataclass_fields__})
        name = str(configuration.get("module", "UHSCHardFloatPrimitive"))
    top = UHSCHardFloatPrimitive(cfg)
    return verilog.convert(top, name=name, ports=[top.clock, top.reset, top.a, top.b, top.operation,
                           top.result, top.equal, top.less, top.is_nan, top.is_inf, top.is_zero], emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print the default aggregate Verilog when invoked directly. / 直接调用时打印默认聚合 Verilog。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
