"""V2 DebugCSR dcsr layout and constants. / V2 DebugCSR dcsr 布局与常量。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amaranth import Elaboratable, Module, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# DebugCSR.scala defines a 32-bit DcsrStruct bundle.  The field positions and
# reset constant below are kept source-compatible, including reserved fields;
# no newer NewCSR DcsrBundle fields are silently substituted.  ``value`` is an
# observation input and every bundle field is a combinational output.
# DebugCSR.scala 定义 32 位 DcsrStruct 束。以下字段位置与复位常量保持源兼容，
# 包括保留字段；不会静默替换为更新的 NewCSR DcsrBundle 字段。value 为观测
# 输入，所有束字段均为组合输出。
__all__ = [
    "DcsrConfig", "DcsrStruct", "DEBUGVER_NONE", "DEBUGVER_SPEC", "DEBUGVER_CUSTOM",
    "CAUSE_EBREAK", "CAUSE_TRIGGER", "CAUSE_HALTREQ", "CAUSE_STEP",
    "CAUSE_RESETHALTREQ", "MODE_M", "field_values", "build_verilog", "main",
]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class DcsrConfig:
    """Fixed-width V2 dcsr configuration. / 固定宽度的 V2 dcsr 配置。"""

    width: int = 32

    # Validate the source bundle width. / 校验源束宽度。
    def __post_init__(self) -> None:
        if self.width != 32:
            raise ValueError("V2 DcsrStruct width is fixed at 32")


# =============================================================================
# Implementation
# =============================================================================
DEBUGVER_NONE = 0
DEBUGVER_SPEC = 4
DEBUGVER_CUSTOM = 15
CAUSE_EBREAK = 1
CAUSE_TRIGGER = 2
CAUSE_HALTREQ = 3
CAUSE_STEP = 4
CAUSE_RESETHALTREQ = 5
MODE_M = 0x3


# Decode every source DcsrStruct field from an integer value. / 从整数值解码源 DcsrStruct 的全部字段。
def field_values(value: int) -> dict[str, int]:
    if not isinstance(value, int) or value < 0 or value >= (1 << 32):
        raise ValueError("dcsr value must be an unsigned 32-bit integer")
    return {
        "debugver": (value >> 28) & 0xF,
        "pad1": (value >> 18) & 0x3FF,
        "ebreakvs": (value >> 17) & 1,
        "ebreakvu": (value >> 16) & 1,
        "ebreakm": (value >> 15) & 1,
        "pad0": (value >> 14) & 1,
        "ebreaks": (value >> 13) & 1,
        "ebreaku": (value >> 12) & 1,
        "stepie": (value >> 11) & 1,
        "stopcount": (value >> 10) & 1,
        "stoptime": (value >> 9) & 1,
        "cause": (value >> 6) & 0x7,
        "v": (value >> 5) & 1,
        "mprven": (value >> 4) & 1,
        "nmip": (value >> 3) & 1,
        "step": (value >> 2) & 1,
        "prv": value & 0x3,
    }


class DcsrStruct(Elaboratable):
    """Combinational 32-bit source-compatible dcsr bundle. / 组合式、源兼容的 32 位 dcsr 束。"""

    DEBUGVER_NONE = DEBUGVER_NONE
    DEBUGVER_SPEC = DEBUGVER_SPEC
    DEBUGVER_CUSTOM = DEBUGVER_CUSTOM
    CAUSE_EBREAK = CAUSE_EBREAK
    CAUSE_TRIGGER = CAUSE_TRIGGER
    CAUSE_HALTREQ = CAUSE_HALTREQ
    CAUSE_STEP = CAUSE_STEP
    CAUSE_RESETHALTREQ = CAUSE_RESETHALTREQ
    ModeM = MODE_M

    # Construct the input and all source-layout output fields. / 构造输入及源布局的全部输出字段。
    def __init__(self, configuration: DcsrConfig | None = None) -> None:
        self.configuration = configuration or DcsrConfig()
        self.value = Signal(32, name="dcsr")
        self.debugver = Signal(4, name="debugver")
        self.pad1 = Signal(10, name="pad1")
        self.ebreakvs = Signal(name="ebreakvs")
        self.ebreakvu = Signal(name="ebreakvu")
        self.ebreakm = Signal(name="ebreakm")
        self.pad0 = Signal(name="pad0")
        self.ebreaks = Signal(name="ebreaks")
        self.ebreaku = Signal(name="ebreaku")
        self.stepie = Signal(name="stepie")
        self.stopcount = Signal(name="stopcount")
        self.stoptime = Signal(name="stoptime")
        self.cause = Signal(3, name="cause")
        self.v = Signal(name="v")
        self.mprven = Signal(name="mprven")
        self.nmip = Signal(name="nmip")
        self.step = Signal(name="step")
        self.prv = Signal(2, name="prv")

    # Return the source DcsrStruct reset value. / 返回源 DcsrStruct 复位值。
    @staticmethod
    # Return the reset encoding / 返回复位编码。
    def init() -> int:
        return (DEBUGVER_SPEC << 28) | MODE_M

    # Elaborate exact source bit slices as combinational assignments. / 将源位切片精确展开为组合赋值。
    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        value = self.value
        module.d.comb += [
            self.debugver.eq(value[28:32]), self.pad1.eq(value[18:28]),
            self.ebreakvs.eq(value[17]), self.ebreakvu.eq(value[16]),
            self.ebreakm.eq(value[15]), self.pad0.eq(value[14]),
            self.ebreaks.eq(value[13]), self.ebreaku.eq(value[12]),
            self.stepie.eq(value[11]), self.stopcount.eq(value[10]),
            self.stoptime.eq(value[9]), self.cause.eq(value[6:9]),
            self.v.eq(value[5]), self.mprven.eq(value[4]), self.nmip.eq(value[3]),
            self.step.eq(value[2]), self.prv.eq(value[0:2]),
        ]
        return module


# =============================================================================
# Public Adapter
# =============================================================================
# Build deterministic Verilog for the complete DcsrStruct field surface. / 为完整 DcsrStruct 字段面构建确定性 Verilog。
def build_verilog(configuration, injected_dependencies) -> str:
    del injected_dependencies
    if configuration is None:
        config = DcsrConfig()
    elif isinstance(configuration, DcsrConfig):
        config = configuration
    elif isinstance(configuration, dict):
        config = DcsrConfig(width=int(configuration.get("width", 32)))
    else:
        raise TypeError("configuration must be DcsrConfig, dict, or None")
    top = DcsrStruct(config)
    ports = [value for value in vars(top).values() if isinstance(value, Signal)]
    return verilog.convert(top, name="DcsrStruct", ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print the default deterministic dcsr export. / 输出默认确定性的 dcsr 导出。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
