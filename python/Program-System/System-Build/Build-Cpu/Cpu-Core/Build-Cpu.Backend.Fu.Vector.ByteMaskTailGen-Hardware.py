"""Generate active and agnostic byte enables for a vector destination.
为向量目的生成 active 与 agnostic 字节使能。
"""

from __future__ import annotations

from dataclasses import dataclass

from amaranth import Cat, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# ByteMaskTailGen.scala maps element begin/end to byte positions, forms the
# [begin,end) body and >=end tail masks over maxVLMAX=128 bytes, selects one
# 16-byte destination by vdIdx, expands maskUsed by EEW, and applies vma/vta.
# The guard begin>=end clears both outputs.  V2 ByteMaskTailGen.scala 将元素
# begin/end 映射到字节位置，在 128 字节范围构造 [begin,end) body 与 >=end tail，
# 按 vdIdx 选择 16 字节目的，按 EEW 展开 maskUsed，并应用 vma/vta；begin>=end
# 时两个输出均清零。 Ports below are the flattened locked-reference ports.
__all__ = ["ByteMaskTailGenConfig", "VSew", "ByteMaskTailGen", "byte_mask_model", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class ByteMaskTailGenConfig:
    """Geometry of the canonical V2 instance. / 标准 V2 实例的几何参数。"""

    vlen: int = 128
    max_vlmax: int = 128
    index_width: int = 8

    # Validate the fixed V2 closure geometry. / 校验固定 V2 闭包几何。
    def __post_init__(self) -> None:
        if self.vlen != 128 or self.max_vlmax != 128:
            raise ValueError("V2 ByteMaskTailGen requires vlen=max_vlmax=128")
        if self.index_width != 8:
            raise ValueError("V2 element index width is 8")


class VSew:
    """Canonical two-bit V2 element-width encodings. / V2 两位元素宽度编码。"""

    e8 = 0
    e16 = 1
    e32 = 2
    e64 = 3


# Compute the integer contract used by direct and differential tests. / 计算 direct 与差分测试使用的整数合同。
def byte_mask_model(
    begin: int,
    end: int,
    vma: bool,
    vta: bool,
    vsew: int,
    mask_used: int,
    vd_idx: int,
) -> tuple[int, int]:
    if vsew not in (VSew.e8, VSew.e16, VSew.e32, VSew.e64):
        return (0, 0)
    begin &= 0xFF
    end &= 0xFF
    start_bytes = (begin << vsew) & 0xFF
    vl_bytes = (end << vsew) & 0xFF
    base = (vd_idx & 0x7) * 16
    active = 0
    agnostic = 0
    for lane in range(16):
        position = base + lane
        body = start_bytes <= position < vl_bytes
        tail = position >= vl_bytes
        source = (lane >> vsew) if vsew < 4 else 0
        mask_bit = (mask_used >> source) & 1
        if begin < end and body and mask_bit:
            active |= 1 << lane
        if begin < end and ((vma and body and not mask_bit) or (vta and tail)):
            agnostic |= 1 << lane
    return active, agnostic


# =============================================================================
# Implementation
# =============================================================================
class ByteMaskTailGen(Elaboratable):
    """Combinational V2 byte-enable generator. / V2 组合式字节使能生成器。"""

    # Declare the flattened locked-reference ports. / 声明锁定参考扁平端口。
    def __init__(self, configuration: ByteMaskTailGenConfig | None = None):
        config = configuration or ByteMaskTailGenConfig()
        self.config = config
        self.in_begin = Signal(8, name="io_in_begin")
        self.in_end = Signal(8, name="io_in_end")
        self.in_vma = Signal(name="io_in_vma")
        self.in_vta = Signal(name="io_in_vta")
        self.in_vsew = Signal(2, name="io_in_vsew")
        self.in_maskUsed = Signal(16, name="io_in_maskUsed")
        self.in_vdIdx = Signal(3, name="io_in_vdIdx")
        self.out_activeEn = Signal(16, name="io_out_activeEn")
        self.out_agnosticEn = Signal(16, name="io_out_agnosticEn")

    # Elaborate byte masks, destination lookup, and agnostic policy. / 展开字节掩码、目的查找与 agnostic 策略。
    def elaborate(self, platform):
        del platform
        module = Module()
        full_width = self.config.max_vlmax
        start_bytes = Signal(8, name="startBytes")
        vl_bytes = Signal(8, name="vlBytes")
        module.d.comb += [
            start_bytes.eq(self.in_begin << self.in_vsew),
            vl_bytes.eq(self.in_end << self.in_vsew),
        ]

        body = Signal(full_width, name="bodyEn")
        tail = Signal(full_width, name="tailEn")
        for index in range(full_width):
            module.d.comb += [
                body[index].eq((start_bytes <= index) & (index < vl_bytes)),
                tail[index].eq(vl_bytes <= index),
            ]

        body_selected = body[:16]
        tail_selected = tail[:16]
        for index in range(1, 8):
            body_selected = Mux(self.in_vdIdx == index, body[index * 16:(index + 1) * 16], body_selected)
            tail_selected = Mux(self.in_vdIdx == index, tail[index * 16:(index + 1) * 16], tail_selected)

        # Expand one mask bit over 1/2/4/8 byte lanes, matching MaskExtractor.
        # 按 1/2/4/8 字节通道展开一个掩码位，与 MaskExtractor 一致。
        expanded = Signal(16, name="maskEn")
        arms = [
            self.in_maskUsed,
            Cat(*[self.in_maskUsed[index] for index in range(8) for _ in range(2)]),
            Cat(*[self.in_maskUsed[index] for index in range(4) for _ in range(4)]),
            Cat(*[self.in_maskUsed[index] for index in range(2) for _ in range(8)]),
        ]
        expanded_expr = arms[3]
        for index in range(2, -1, -1):
            expanded_expr = Mux(self.in_vsew == index, arms[index], expanded_expr)
        module.d.comb += expanded.eq(expanded_expr)

        valid_range = self.in_begin < self.in_end
        active = Mux(valid_range, body_selected & expanded, Const(0, 16))
        agnostic = Mux(
            valid_range,
            ((~expanded) & body_selected & Mux(self.in_vma, Const(0xFFFF, 16), Const(0, 16)))
            | (tail_selected & Mux(self.in_vta, Const(0xFFFF, 16), Const(0, 16))),
            Const(0, 16),
        )
        module.d.comb += [self.out_activeEn.eq(active), self.out_agnosticEn.eq(agnostic)]
        return module


# =============================================================================
# Public Adapter
# =============================================================================
# Emit deterministic V2-compatible Verilog. / 输出确定性的 V2 兼容 Verilog。
def build_verilog(configuration, injected_dependencies) -> str:
    del injected_dependencies
    top = ByteMaskTailGen(configuration)
    return verilog.convert(
        top, name="ByteMaskTailGen",
        ports=[top.in_begin, top.in_end, top.in_vma, top.in_vta,
               top.in_vsew, top.in_maskUsed, top.in_vdIdx,
               top.out_activeEn, top.out_agnosticEn], emit_src=False,
    )


# =============================================================================
# Direct Entry
# =============================================================================
# Print the default standalone helper. / 直接打印默认独立辅助器。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
