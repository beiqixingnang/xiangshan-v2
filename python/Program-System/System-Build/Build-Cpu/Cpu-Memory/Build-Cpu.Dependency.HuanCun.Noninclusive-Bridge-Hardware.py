"""UHSC Kunminghu V2 HuanCun non-inclusive bridge family boundary.
昆明湖 V2 HuanCun non-inclusive bridge family 边界。

The selected cache closure uses a bridge between non-inclusive slice control,
probe/snoop traffic, and TileLink-like request/response records.  This single
aggregate preserves ready/valid ordering, source propagation, and flush
cancellation while keeping helper records inside the family boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amaranth import ClockDomain, Elaboratable, Module, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# Bridge contract: request admission, probe forwarding, response return, and
# one-entry backpressure. / bridge 契约：请求接收、probe 转发、响应返回及单项反压。
__all__ = ["HuanCunBridgeConfig", "HuanCunBridgeBoundary", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class HuanCunBridgeConfig:
    """Finite bridge widths. / 有限 bridge 宽度。"""

    address_bits: int = 48
    data_bits: int = 512
    source_bits: int = 6

    # Validate bridge geometry. / 校验 bridge 几何参数。
    def __post_init__(self) -> None:
        if min(self.address_bits, self.data_bits, self.source_bits) < 1 or self.data_bits % 8:
            raise ValueError("invalid HuanCun bridge geometry")


# =============================================================================
# Implementation
# =============================================================================
class HuanCunBridgeBoundary(Elaboratable):
    """Ready/valid bridge for request, probe, and response channels. / 请求、probe、响应通道的 ready/valid bridge。"""

    # Construct bridge ports. / 构造 bridge 端口。
    def __init__(self, configuration: HuanCunBridgeConfig | None = None) -> None:
        self.configuration = configuration or HuanCunBridgeConfig()
        c = self.configuration
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.flush = Signal(name="io_flush")
        self.req_valid = Signal(name="io_req_valid")
        self.req_ready = Signal(name="io_req_ready")
        self.req_address = Signal(c.address_bits, name="io_req_address")
        self.req_source = Signal(c.source_bits, name="io_req_source")
        self.req_data = Signal(c.data_bits, name="io_req_data")
        self.probe_valid = Signal(name="io_probe_valid")
        self.probe_ready = Signal(name="io_probe_ready")
        self.probe_address = Signal(c.address_bits, name="io_probe_address")
        self.probe_source = Signal(c.source_bits, name="io_probe_source")
        self.resp_valid = Signal(name="io_resp_valid")
        self.resp_ready = Signal(name="io_resp_ready")
        self.resp_source = Signal(c.source_bits, name="io_resp_source")
        self.resp_data = Signal(c.data_bits, name="io_resp_data")
        self.busy = Signal(name="io_busy")
        self.forward_valid = Signal(name="io_forward_valid")

    # Elaborate one-entry bridge state and ordering. / 展开单项 bridge 状态及顺序逻辑。
    def elaborate(self, platform: Any) -> Module:
        del platform
        c = self.configuration
        m = Module()
        domain = ClockDomain("huancun_bridge", async_reset=True)
        domain.clk = self.clock; domain.rst = self.reset; m.domains.huancun_bridge = domain
        address_r = Signal(c.address_bits, name="address_r")
        source_r = Signal(c.source_bits, name="source_r")
        data_r = Signal(c.data_bits, name="data_r")
        pending = Signal(name="pending")
        response = Signal(name="response")
        m.d.comb += [self.req_ready.eq(~pending & ~self.flush), self.probe_ready.eq(~self.flush),
                     self.busy.eq(pending), self.forward_valid.eq(pending & ~self.flush),
                     self.probe_valid.eq(pending & ~self.flush), self.probe_address.eq(address_r),
                     self.probe_source.eq(source_r), self.resp_valid.eq(response & ~self.flush),
                     self.resp_source.eq(source_r), self.resp_data.eq(data_r)]
        with m.If(self.reset | self.flush):
            m.d.huancun_bridge += [pending.eq(0), response.eq(0)]
        with m.Else():
            m.d.huancun_bridge += response.eq(0)
            with m.If(self.req_valid & self.req_ready):
                m.d.huancun_bridge += [pending.eq(1), address_r.eq(self.req_address), source_r.eq(self.req_source), data_r.eq(self.req_data)]
            with m.If(self.probe_valid & self.probe_ready):
                m.d.huancun_bridge += [pending.eq(0), response.eq(1)]
            with m.If(response & self.resp_ready):
                m.d.huancun_bridge += response.eq(0)
        return m


# Source-oriented alias. / 源导向别名。
HuanCunBridge = HuanCunBridgeBoundary


# =============================================================================
# Public Adapter
# =============================================================================
# Export deterministic bridge Verilog. / 导出确定性的 bridge Verilog。
def build_verilog(configuration, injected_dependencies):
    """Return Verilog for the non-inclusive bridge family. / 返回 non-inclusive bridge family Verilog。"""

    del injected_dependencies
    if isinstance(configuration, HuanCunBridgeConfig):
        cfg, name = configuration, "UHSCHuanCunBridge"
    elif isinstance(configuration, dict):
        fields = HuanCunBridgeConfig.__dataclass_fields__
        cfg = HuanCunBridgeConfig(**{key: int(value) for key, value in configuration.items() if key in fields})
        name = str(configuration.get("module", configuration.get("name", "UHSCHuanCunBridge")))
    elif configuration is None:
        cfg, name = HuanCunBridgeConfig(), "UHSCHuanCunBridge"
    else:
        raise TypeError("configuration must be HuanCunBridgeConfig, dict, or None")
    top = HuanCunBridgeBoundary(cfg)
    ports = [top.clock, top.reset, top.flush, top.req_valid, top.req_ready, top.req_address, top.req_source, top.req_data,
             top.probe_valid, top.probe_ready, top.probe_address, top.probe_source, top.resp_valid, top.resp_ready,
             top.resp_source, top.resp_data, top.busy, top.forward_valid]
    return verilog.convert(top, name=name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print direct export. / 打印 direct 导出。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
