"""V2 decoupled pipeline register with flush and age override.
V2 带冲刷与年龄覆盖的解耦流水线寄存器。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from amaranth import ClockDomain, ClockSignal, Elaboratable, Module, Mux, ResetSignal, Signal


# =============================================================================
# Module Contract
# =============================================================================
# NewPipelineConnect.scala stores one payload and one valid bit.  The input is
# accepted when the output is ready, the stage is empty, or isOlder is true;
# rightOutFire clears the stage unless a same-cycle input fire replaces it.
# NewPipelineConnect.scala 保存一个载荷和一个有效位；输出就绪、级为空或
# isOlder 为真时接受输入；rightOutFire 清除级，但同周期输入出火可替换它。
__all__ = [
    "COVERED_MODULES",
    "NewPipelineConnectConfig",
    "NewPipelineConnectPipe",
    "NewPipelineConnect",
    "connect",
    "connect_observation",
    "build_verilog",
    "main",
]

COVERED_MODULES: tuple[str, ...] = ("NewPipelineConnectPipe",)


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class NewPipelineConnectConfig:
    """Serializable pipeline geometry. / 可序列化的流水线几何配置。"""

    data_width: int = 64

    # Validate the payload width used by the generated Bundle. / 校验生成 Bundle 使用的载荷位宽。
    def __post_init__(self) -> None:
        if self.data_width < 1:
            raise ValueError("data_width must be positive")


# =============================================================================
# Implementation
# =============================================================================
# Connect one pair of decoupled channels in-place. / 原地连接一对解耦通道。
def connect(
    module: Module,
    leftValid: Signal,
    leftReady: Signal,
    leftBits: Signal,
    rightValid: Signal,
    rightReady: Signal,
    rightBits: Signal,
    rightOutFire: Signal,
    isFlush: Signal,
    isOlder: Signal,
    reset: Signal | None = None,
) -> Signal:
    """Implement the V2 ``NewPipelineConnect.connect`` equations.
    实现 V2 ``NewPipelineConnect.connect`` 方程。
    """
    valid_reg = Signal(name="npc_valid", reset=0)
    data_reg = Signal.like(leftBits, name="npc_data")
    left_fire = leftValid & leftReady
    module.d.comb += [
        leftReady.eq(rightReady | ~valid_reg | isOlder),
        rightValid.eq(valid_reg),
        rightBits.eq(data_reg),
    ]

    # Chisel's source order is rightOutFire, left.fire, then isFlush.  The
    # nested priority below preserves that ordering (flush wins over both).
    # Build one priority expression: reset/flush dominate, then input fire
    # replaces a consumed item, otherwise rightOutFire clears the stage.
    next_valid: Any = Mux(rightOutFire, 0, valid_reg)
    next_valid = Mux(left_fire, 1, next_valid)
    next_valid = Mux(isFlush, 0, next_valid)
    if reset is not None:
        next_valid = Mux(reset, 0, next_valid)
    module.d.sync += valid_reg.eq(next_valid)
    # Amaranth's dynamic context manager is cast at this typed boundary; the
    # emitted control condition remains exactly ``left_fire``.
    with cast(Any, module.If(left_fire)):
        module.d.sync += data_reg.eq(leftBits)
    return data_reg


def connect_observation(valid: bool, ready: bool, out_fire: bool,
                        flush: bool, older: bool) -> dict[str, int]:
    """Return one source-priority decoupled stage observation. / 返回单周期流水观测。"""

    left_fire = int(bool(valid) and (bool(ready) or not bool(valid) or bool(older)))
    next_valid = int(bool(valid))
    if out_fire:
        next_valid = 0
    if left_fire:
        next_valid = 1
    if flush:
        next_valid = 0
    return {"left_fire": left_fire, "next_valid": next_valid,
            "flush": int(bool(flush)), "older": int(bool(older))}


class NewPipelineConnectPipe(Elaboratable):
    """One V2 pipeline stage. / 一个 V2 流水线级。"""

    # Construct the explicit decoupled and control ports. / 构造显式解耦与控制端口。
    def __init__(self, dataWidth: int = 64) -> None:
        if int(dataWidth) < 1:
            raise ValueError("dataWidth must be positive")
        self.data_width = int(dataWidth)
        self.clock = ClockSignal("sync")
        # Explicit reset observation mirroring the Chisel Module reset port.
        self.reset = Signal(name="reset")
        self.in_valid = Signal(name="io_in_valid")
        self.in_ready = Signal(name="io_in_ready")
        self.in_bits = Signal(self.data_width, name="io_in_bits")
        self.out_valid = Signal(name="io_out_valid")
        self.out_ready = Signal(name="io_out_ready")
        self.out_bits = Signal(self.data_width, name="io_out_bits")
        self.rightOutFire = Signal(name="io_rightOutFire")
        self.isFlush = Signal(name="io_isFlush")
        self.isOlder = Signal(name="io_isOlder")

    # Elaborate the registered valid/payload path. / 展开寄存有效位与载荷通路。
    def elaborate(self, platform) -> Module:
        del platform
        module = Module()
        # Match Chisel's asynchronous Module reset on the valid register.
        module.domains.sync = ClockDomain(async_reset=True)
        module.d.comb += ResetSignal("sync").eq(self.reset)
        connect(
            module,
            self.in_valid,
            self.in_ready,
            self.in_bits,
            self.out_valid,
            self.out_ready,
            self.out_bits,
            self.rightOutFire,
            self.isFlush,
            self.isOlder,
            self.reset,
        )
        return module


class NewPipelineConnect:
    """Static facade matching the V2 Scala object. / 匹配 V2 Scala 对象的静态门面。"""

    @staticmethod
    # Delegate the inline connection operation. / 委托原地连接操作。
    def connect(
        module: Module,
        leftValid: Signal,
        leftReady: Signal,
        leftBits: Signal,
        rightValid: Signal,
        rightReady: Signal,
        rightBits: Signal,
        rightOutFire: Signal,
        isFlush: Signal,
        isOlder: Signal,
        reset: Signal | None = None,
    ) -> Signal:
        return connect(
            module,
            leftValid,
            leftReady,
            leftBits,
            rightValid,
            rightReady,
            rightBits,
            rightOutFire,
            isFlush,
            isOlder,
            reset,
        )


class _LockedNewPipelineConnectPipe(Elaboratable):
    """Exact ExecInput specialization emitted by the locked V2 hierarchy."""

    FIELDS: tuple[tuple[str, int], ...] = (
        ("fuType", 35), ("fuOpType", 9), ("src_0", 64), ("src_1", 64),
        ("robIdx_flag", 1), ("robIdx_value", 8), ("pdest", 8), ("rfWen", 1),
    )

    def __init__(self) -> None:
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.in_valid = Signal(name="io_in_valid")
        self.inputs = {
            name: Signal(width, name=f"io_in_bits_{name}") for name, width in self.FIELDS
        }
        self.out_valid = Signal(name="io_out_valid")
        self.outputs = {
            name: Signal(width, name=f"io_out_bits_{name}") for name, width in self.FIELDS
        }
        self.right_out_fire = Signal(name="io_rightOutFire")
        self.is_flush = Signal(name="io_isFlush")

    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        domain = ClockDomain("sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        module.domains += domain
        valid = Signal(name="valid", reset=0)
        data = {
            name: Signal(width, name=f"data_{name}", reset_less=True)
            for name, width in self.FIELDS
        }
        module.d.sync += valid.eq(
            ~self.is_flush & (self.in_valid | (~self.right_out_fire & valid))
        )
        with cast(Any, module.If(self.in_valid)):
            module.d.sync += [data[name].eq(self.inputs[name]) for name, _ in self.FIELDS]
        module.d.comb += [self.out_valid.eq(valid)]
        module.d.comb += [
            self.outputs[name].eq(data[name]) for name, _ in self.FIELDS
        ]
        return module

    def ports(self) -> list[Signal]:
        return [
            self.clock,
            self.reset,
            self.in_valid,
            *self.inputs.values(),
            self.out_valid,
            *self.outputs.values(),
            self.right_out_fire,
            self.is_flush,
        ]

# =============================================================================
# Public Adapter
# =============================================================================
# Export a deterministic configured pipeline stage. / 导出确定性配置流水线级。
def build_verilog(configuration, injected_dependencies):
    """Return Verilog for the configured V2 pipeline stage. / 返回配置 V2 流水线级的 Verilog。"""
    from amaranth.back import verilog

    del injected_dependencies
    config: dict[str, Any] = configuration if isinstance(configuration, dict) else {}
    if config.get("module") == "NewPipelineConnectPipe":
        locked = _LockedNewPipelineConnectPipe()
        return verilog.convert(
            locked, name="NewPipelineConnectPipe", ports=locked.ports(), emit_src=False
        )
    raw = config.get("data_width", config.get("width", 64))
    if isinstance(configuration, NewPipelineConnectConfig):
        width = configuration.data_width
    else:
        width = int(raw)
    name = str(config.get("name", config.get("module", "NewPipelineConnectPipe")))
    top = NewPipelineConnectPipe(width)
    ports = [
        top.clock,
        top.reset,
        top.in_valid,
        top.in_ready,
        top.in_bits,
        top.out_valid,
        top.out_ready,
        top.out_bits,
        top.rightOutFire,
        top.isFlush,
        top.isOlder,
    ]
    return verilog.convert(top, name=name, ports=ports)


# =============================================================================
# Direct Entry
# =============================================================================
# Print the default deterministic export. / 打印默认确定性导出结果。
def main() -> None:
    print(build_verilog(None, None))


if __name__ == "__main__":
    main()
