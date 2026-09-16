"""UHSC Kunminghu V2 Rocket TileLink protocol family boundary.
昆明湖 V2 Rocket TileLink 协议 family 边界。

The frozen V2 top uses Rocket/TileLink protocol records through several
generated families.  This aggregate keeps the selected ready/valid A/D
channel semantics and source/id propagation in one Build-Cpu file; protocol
bundles, monitors, and test-only Scala siblings remain represented by the
explicit family boundary rather than duplicated one-file ports.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, cast, Iterable, Sequence

from amaranth import ClockDomain, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# The boundary models TileLink A-channel admission, one outstanding source,
# D-channel response routing, and reset/flush cancellation. / 该边界模型覆盖
# TileLink A 通道接收、单个未决 source、D 通道响应路由以及复位/flush 取消。
__all__ = [
    "RocketProtocolConfig", "RocketProtocolBoundary", "RocketProtocolArbiterState",
    "protocol_handshake", "protocol_arbiter", "build_verilog", "main",
]


# Return the Decoupled/ready-valid fire condition used by TileLink channels. /
# 返回 TileLink 通道使用的 Decoupled/ready-valid fire 条件。
def protocol_handshake(valid: bool, ready: bool) -> bool:
    """Return ``True`` exactly when a channel transfer occurs."""

    return bool(valid and ready)


@dataclass(frozen=True)
class RocketProtocolArbiterState:
    """Software shadow of ``TLArbiter.roundRobin``'s rotating mask."""

    pointer: int = 0


# Resolve a deterministic one-hot grant, mirroring Rocket's TLArbiter policies. /
# 解析确定性 one-hot 授予，匹配 Rocket 的 TLArbiter 策略。
def protocol_arbiter(
    valids: Sequence[bool] | Iterable[bool],
    sink_ready: bool,
    state: RocketProtocolArbiterState | None = None,
    policy: str = "round_robin",
) -> tuple[tuple[bool, ...], int | None, RocketProtocolArbiterState]:
    """Compute source readies, winner and next round-robin state.

    ``TLArbiter.apply`` locks a winner until all beats complete; this helper
    models the single-beat decision and rotates the pointer only on ``fire``.
    """

    requested = tuple(bool(value) for value in valids)
    count = len(requested)
    if count == 0:
        return (), None, state or RocketProtocolArbiterState()
    if policy not in {"round_robin", "lowest", "highest"}:
        raise ValueError("unsupported Rocket protocol arbiter policy")
    pointer = (state or RocketProtocolArbiterState()).pointer % count
    order = tuple(range(pointer, count)) + tuple(range(pointer)) if policy == "round_robin" else (
        tuple(range(count)) if policy == "lowest" else tuple(reversed(range(count)))
    )
    winner = next((index for index in order if requested[index]), None)
    fire = winner is not None and bool(sink_ready)
    readies = tuple(bool(fire and index == winner) for index in range(count))
    next_pointer = ((winner + 1) % count) if fire and winner is not None else pointer
    return readies, winner, RocketProtocolArbiterState(next_pointer)


# Cast Amaranth generator controls to the context-manager protocol. / 将 Amaranth 生成器控制转换为上下文管理器协议。
def amaranth_if(module: Module, condition: Any) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.If(condition))


# Cast an Amaranth elif branch to the context-manager protocol. / 将 Amaranth elif 分支转换为上下文管理器协议。
def amaranth_elif(module: Module, condition: Any) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.Elif(condition))


# Cast an Amaranth else branch to the context-manager protocol. / 将 Amaranth else 分支转换为上下文管理器协议。
def amaranth_else(module: Module) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.Else())


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class RocketProtocolConfig:
    """Fixed protocol widths used by selected V2 paths. / 选定 V2 路径使用的固定协议宽度。"""

    address_bits: int = 48
    data_bits: int = 128
    source_bits: int = 6
    size_bits: int = 3

    # Validate protocol geometry. / 校验协议几何参数。
    def __post_init__(self) -> None:
        if min(self.address_bits, self.data_bits, self.source_bits, self.size_bits) < 1:
            raise ValueError("Rocket protocol widths must be positive")
        if self.data_bits % 8:
            raise ValueError("Rocket protocol data width must be byte aligned")


# =============================================================================
# Implementation
# =============================================================================
class RocketProtocolBoundary(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Aggregated TileLink A/D ready-valid protocol boundary. / 聚合 TileLink A/D ready-valid 协议边界。"""

    # Construct protocol channel ports. / 构造协议通道端口。
    def __init__(self, configuration: RocketProtocolConfig | None = None) -> None:
        self.configuration = configuration or RocketProtocolConfig()
        c = self.configuration
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.flush = Signal(name="io_flush")
        self.a_valid = Signal(name="io_a_valid")
        self.a_ready = Signal(name="io_a_ready")
        self.a_opcode = Signal(3, name="io_a_bits_opcode")
        self.a_param = Signal(3, name="io_a_bits_param")
        self.a_size = Signal(c.size_bits, name="io_a_bits_size")
        self.a_source = Signal(c.source_bits, name="io_a_bits_source")
        self.a_address = Signal(c.address_bits, name="io_a_bits_address")
        self.a_mask = Signal(c.data_bits // 8, name="io_a_bits_mask")
        self.a_data = Signal(c.data_bits, name="io_a_bits_data")
        self.d_valid = Signal(name="io_d_valid")
        self.d_ready = Signal(name="io_d_ready")
        self.d_opcode = Signal(3, name="io_d_bits_opcode")
        self.d_size = Signal(c.size_bits, name="io_d_bits_size")
        self.d_source = Signal(c.source_bits, name="io_d_bits_source")
        self.d_sink = Signal(2, name="io_d_bits_sink")
        self.d_denied = Signal(name="io_d_bits_denied")
        self.d_data = Signal(c.data_bits, name="io_d_bits_data")
        self.d_corrupt = Signal(name="io_d_bits_corrupt")
        self.outstanding = Signal(name="io_outstanding")
        self.request_fire = Signal(name="io_request_fire")
        self.response_fire = Signal(name="io_response_fire")

    # Elaborate one-entry TileLink protocol state. / 展开单项 TileLink 协议状态。
    def elaborate(self, platform: Any) -> Module:
        del platform
        c = self.configuration
        m = Module()
        domain = ClockDomain("rocket_protocol", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.rocket_protocol = domain
        source_r = Signal(c.source_bits)
        opcode_r = Signal(3)
        size_r = Signal(c.size_bits)
        address_r = Signal(c.address_bits)
        data_r = Signal(c.data_bits)
        mask_r = Signal(c.data_bits // 8)
        m.d.comb += [self.a_ready.eq(~self.outstanding & ~self.flush),
                     self.request_fire.eq(self.a_valid & self.a_ready),
                     self.d_valid.eq(self.outstanding & ~self.flush),
                     self.response_fire.eq(self.d_valid & self.d_ready),
                     self.d_opcode.eq(Mux(opcode_r == 0, 0, 1)),
                     self.d_size.eq(size_r), self.d_source.eq(source_r), self.d_sink.eq(0),
                     self.d_denied.eq(0), self.d_data.eq(data_r), self.d_corrupt.eq(0)]
        with amaranth_if(m, self.flush):
            m.d.rocket_protocol += self.outstanding.eq(0)
        with amaranth_else(m):
            with amaranth_if(m, self.request_fire):
                m.d.rocket_protocol += [self.outstanding.eq(1), source_r.eq(self.a_source),
                                        opcode_r.eq(self.a_opcode), size_r.eq(self.a_size),
                                        address_r.eq(self.a_address), data_r.eq(self.a_data), mask_r.eq(self.a_mask)]
            with amaranth_elif(m, self.response_fire):
                m.d.rocket_protocol += self.outstanding.eq(0)
        return m


# Source-oriented alias retained for family consumers. / 为 family 消费者保留源导向别名。
RocketProtocol = RocketProtocolBoundary


# =============================================================================
# Public Adapter
# =============================================================================
# Export deterministic protocol Verilog. / 导出确定性的协议 Verilog。
def build_verilog(configuration, injected_dependencies):
    """Return Verilog for the Rocket protocol boundary. / 返回 Rocket 协议边界 Verilog。"""

    del injected_dependencies
    if isinstance(configuration, RocketProtocolConfig):
        cfg, name = configuration, "UHSCRocketProtocol"
    elif isinstance(configuration, dict):
        fields = RocketProtocolConfig.__dataclass_fields__
        cfg = RocketProtocolConfig(**{key: int(value) for key, value in configuration.items() if key in fields})
        name = str(configuration.get("module", configuration.get("name", "UHSCRocketProtocol")))
    elif configuration is None:
        cfg, name = RocketProtocolConfig(), "UHSCRocketProtocol"
    else:
        raise TypeError("configuration must be RocketProtocolConfig, dict, or None")
    top = RocketProtocolBoundary(cfg)
    ports = [top.clock, top.reset, top.flush, top.a_valid, top.a_ready, top.a_opcode, top.a_param,
             top.a_size, top.a_source, top.a_address, top.a_mask, top.a_data, top.d_valid,
             top.d_ready, top.d_opcode, top.d_size, top.d_source, top.d_sink, top.d_denied,
             top.d_data, top.d_corrupt, top.outstanding, top.request_fire, top.response_fire]
    return verilog.convert(top, name=name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print deterministic direct export. / 打印确定性的 direct 导出。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
