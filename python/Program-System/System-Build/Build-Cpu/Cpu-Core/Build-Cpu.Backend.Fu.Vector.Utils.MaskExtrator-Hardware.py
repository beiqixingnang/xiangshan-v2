"""Expand a vector mask bit for the selected element width.
按选定元素宽度展开向量掩码位。
"""

from __future__ import annotations

from dataclasses import dataclass

from amaranth import Cat, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# The canonical V2 MaskExtractor.scala accepts a numBytes-bit mask and a
# two-bit VSew, then repeats each source bit 1/2/4/8 times.  Assignment to the
# numBytes-bit output truncates the intermediate vlen-bit UInt exactly as in
# Chisel. V2 MaskExtractor.scala 接受 numBytes 位掩码与两位 VSew，并将每个源位
# 重复 1/2/4/8 次；中间 vlen 位 UInt 赋给 numBytes 位输出时按 Chisel 截断。
__all__ = ["MaskExtractorConfig", "VSew", "MaskExtractor", "expand_mask_integer", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class MaskExtractorConfig:
    """Vector length used by the V2 mask helper. / V2 掩码辅助器的向量长度。"""

    vlen: int = 128

    # Validate the widths needed by every V2 element encoding. / 校验所有 V2 编码所需位宽。
    def __post_init__(self) -> None:
        if self.vlen < 64 or self.vlen % 64:
            raise ValueError("vlen must be a positive multiple of 64")


class VSew:
    """Canonical V2 element-width encodings. / V2 标准元素宽度编码。"""

    e8 = 0
    e16 = 1
    e32 = 2
    e64 = 3


# =============================================================================
# Implementation
# =============================================================================
# Repeat each source mask bit in least-significant-first order. / 按最低位优先顺序重复每个源掩码位。
def expand_mask(mask: Signal, width: int, repeat: int) -> object:
    if repeat < 1 or width % repeat:
        raise ValueError("repeat must divide mask width")
    return Cat(*[
        mask[index]
        for index in range(width // repeat)
        for _ in range(repeat)
    ])


def expand_mask_integer(mask: int, vsew: int, num_bytes: int) -> int:
    """Expand a packed mask using the four Scala VSew arms. / 以 Scala 四种 VSew 分支展开整数掩码。"""

    repeat = 1 << int(vsew)
    if repeat not in (1, 2, 4, 8) or num_bytes < 1:
        raise ValueError("invalid VSew or byte width")
    source = int(mask) & ((1 << num_bytes) - 1)
    result = 0
    for index in range(num_bytes // repeat):
        bit = (source >> index) & 1
        result |= ((1 << repeat) - 1) * bit << (index * repeat)
    return result & ((1 << num_bytes) - 1)


class MaskExtractor(Elaboratable):
    """Replicate mask bits according to VSew. / 按 VSew 复制掩码位。"""

    # Construct the source-compatible V2 ports. / 构造与 V2 源兼容的端口。
    def __init__(self, configuration: MaskExtractorConfig | None = None):
        config = configuration or MaskExtractorConfig()
        self.config = config
        self.num_bytes = config.vlen // 8
        self.in_mask = Signal(self.num_bytes, name="io_in_mask")
        self.in_vsew = Signal(2, name="io_in_vsew")
        self.out_mask = Signal(self.num_bytes, name="io_out_mask")

    # Elaborate the four canonical Mux1H arms. / 展开四个标准 Mux1H 分支。
    def elaborate(self, platform):
        del platform
        module = Module()
        width = self.num_bytes
        e8 = expand_mask(self.in_mask, width, 1)
        e16 = expand_mask(self.in_mask, width, 2)
        e32 = expand_mask(self.in_mask, width, 4)
        e64 = expand_mask(self.in_mask, width, 8)
        selected = Mux(
            self.in_vsew == VSew.e8,
            e8,
            Mux(
                self.in_vsew == VSew.e16,
                e16,
                Mux(self.in_vsew == VSew.e32, e32, e64),
            ),
        )
        module.d.comb += self.out_mask.eq(selected)
        return module


# =============================================================================
# Public Adapter
# =============================================================================
# Emit deterministic V2-compatible Verilog. / 输出确定性的 V2 兼容 Verilog。
def build_verilog(configuration, injected_dependencies) -> str:
    del injected_dependencies
    top = MaskExtractor(configuration)
    return verilog.convert(
        top, name="MaskExtractor", ports=[top.in_mask, top.in_vsew, top.out_mask],
        emit_src=False,
    )


# =============================================================================
# Direct Entry
# =============================================================================
# Print the default standalone helper. / 直接打印默认独立辅助器。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
