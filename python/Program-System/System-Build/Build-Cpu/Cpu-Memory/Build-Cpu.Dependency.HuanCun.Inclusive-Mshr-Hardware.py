"""UHSC Kunminghu V2 HuanCun inclusive MSHR family boundary.
昆明湖 V2 HuanCun inclusive MSHR family 边界。

This aggregate captures the selected inclusive-directory MSHR contract:
bounded allocation, source/address retention, refill completion, and flush
cancellation.  Directory/SinkC protocol details remain explicit family
boundary inputs rather than being split into dozens of Scala-shaped files.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, cast

from amaranth import Array, ClockDomain, Elaboratable, Mux, Module, Signal
from amaranth.back import verilog
from amaranth.hdl.ast import Value


# =============================================================================
# Module Contract
# =============================================================================
# Inclusive MSHR exposes alloc/free/lookup and one completion response. /
# inclusive MSHR 提供分配/释放/查找及单项完成响应。
__all__ = ["InclusiveMshrConfig", "InclusiveMshrBoundary", "build_verilog", "main"]


# Cast Amaranth's generator controls to a context-manager protocol. / 将 Amaranth 生成器控制转换为上下文管理器协议。
def _if(module: Module, condition: Any) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.If(condition))


# Cast the Amaranth else branch to a context-manager protocol. / 将 Amaranth else 分支转换为上下文管理器协议。
def _else(module: Module) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.Else())


# Narrow dynamic Amaranth values at the DSL boundary. / 在 DSL 边界窄化动态 Amaranth 值。
def _value(expression: Any) -> Value:
    return cast(Value, expression)


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class InclusiveMshrConfig:
    """Finite MSHR geometry. / 有限 MSHR 几何参数。"""

    entries: int = 4
    address_bits: int = 48
    source_bits: int = 6
    line_bits: int = 512

    # Validate geometry. / 校验几何参数。
    def __post_init__(self) -> None:
        if self.entries < 1 or self.entries > 32:
            raise ValueError("MSHR entries must be in [1, 32]")
        if min(self.address_bits, self.source_bits, self.line_bits) < 1:
            raise ValueError("MSHR widths must be positive")

    @property
    # Return entry index width. / 返回条目索引位宽。
    def index_bits(self) -> int:
        return max(1, (self.entries - 1).bit_length())


# =============================================================================
# Implementation
# =============================================================================
class InclusiveMshrBoundary(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Bounded inclusive MSHR allocator and refill tracker. / 有界 inclusive MSHR 分配器与回填跟踪器。"""

    # Construct MSHR ports. / 构造 MSHR 端口。
    def __init__(self, configuration: InclusiveMshrConfig | None = None) -> None:
        self.configuration = configuration or InclusiveMshrConfig()
        c = self.configuration
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.flush = Signal(name="io_flush")
        self.alloc_valid = Signal(name="io_alloc_valid")
        self.alloc_ready = Signal(name="io_alloc_ready")
        self.alloc_address = Signal(c.address_bits, name="io_alloc_address")
        self.alloc_source = Signal(c.source_bits, name="io_alloc_source")
        self.alloc_index = Signal(c.index_bits, name="io_alloc_index")
        self.lookup_valid = Signal(name="io_lookup_valid")
        self.lookup_address = Signal(c.address_bits, name="io_lookup_address")
        self.lookup_hit = Signal(name="io_lookup_hit")
        self.refill_valid = Signal(name="io_refill_valid")
        self.refill_data = Signal(c.line_bits, name="io_refill_data")
        self.refill_source = Signal(c.source_bits, name="io_refill_source")
        self.resp_valid = Signal(name="io_resp_valid")
        self.resp_data = Signal(c.line_bits, name="io_resp_data")
        self.resp_source = Signal(c.source_bits, name="io_resp_source")
        self.occupancy = Signal(max(1, (c.entries + 1).bit_length()), name="io_occupancy")

    # Elaborate allocation, lookup, refill and cancellation. / 展开分配、查找、回填及取消。
    def elaborate(self, platform: Any) -> Module:
        del platform
        c = self.configuration
        m = Module()
        domain = ClockDomain("huancun_mshr", async_reset=True)
        domain.clk = self.clock; domain.rst = self.reset; m.domains.huancun_mshr = domain
        used = Signal(c.entries, name="mshr_used")
        addr_mem = [Signal(c.address_bits, name=f"mshr_addr_{i}") for i in range(c.entries)]
        source_mem = [Signal(c.source_bits, name=f"mshr_source_{i}") for i in range(c.entries)]
        data_mem = [Signal(c.line_bits, name=f"mshr_data_{i}") for i in range(c.entries)]
        alloc_index = Signal(c.index_bits, name="alloc_index_r")
        free_index = Signal(c.index_bits, name="free_index_r")
        alloc_found: Any = 0
        alloc_choice: Any = 0
        for index in range(c.entries):
            take = ~_value(used[index]) & ~_value(alloc_found)
            alloc_choice = Mux(take, index, alloc_choice)
            alloc_found = _value(alloc_found) | ~_value(used[index])
        lookup_found: Any = 0
        lookup_choice: Any = 0
        for index in range(c.entries):
            hit = used[index] & (addr_mem[index] == self.lookup_address)
            lookup_choice = Mux(hit & ~lookup_found, index, lookup_choice)
            lookup_found = lookup_found | hit
        occupancy_expr = sum((_value(used[index]) for index in range(c.entries)), 0)
        m.d.comb += [self.alloc_ready.eq(~self.flush & alloc_found), self.alloc_index.eq(alloc_choice),
                     self.lookup_hit.eq(self.lookup_valid & lookup_found), self.occupancy.eq(occupancy_expr),
                     self.resp_valid.eq(self.refill_valid & lookup_found), self.resp_data.eq(Array(data_mem)[lookup_choice]),
                     self.resp_source.eq(Array(source_mem)[lookup_choice])]
        with _if(m, self.reset | self.flush):
            m.d.huancun_mshr += used.eq(0)
        with _else(m):
            with _if(m, self.alloc_valid & self.alloc_ready):
                m.d.huancun_mshr += [Array(used)[alloc_choice].eq(1), Array(addr_mem)[alloc_choice].eq(self.alloc_address), Array(source_mem)[alloc_choice].eq(self.alloc_source), alloc_index.eq(alloc_choice)]
            with _if(m, self.refill_valid & lookup_found):
                m.d.huancun_mshr += [Array(data_mem)[lookup_choice].eq(self.refill_data), Array(used)[lookup_choice].eq(0), free_index.eq(lookup_choice)]
        return m


# Source-oriented alias. / 源导向别名。
InclusiveMSHR = InclusiveMshrBoundary


# =============================================================================
# Public Adapter
# =============================================================================
# Export deterministic MSHR Verilog. / 导出确定性的 MSHR Verilog。
def build_verilog(configuration, injected_dependencies):
    """Return Verilog for the inclusive MSHR family. / 返回 inclusive MSHR family Verilog。"""

    del injected_dependencies
    if isinstance(configuration, InclusiveMshrConfig):
        cfg, name = configuration, "UHSCHuanCunInclusiveMSHR"
    elif isinstance(configuration, dict):
        fields = InclusiveMshrConfig.__dataclass_fields__
        cfg = InclusiveMshrConfig(**{key: int(value) for key, value in configuration.items() if key in fields})
        name = str(configuration.get("module", configuration.get("name", "UHSCHuanCunInclusiveMSHR")))
    elif configuration is None:
        cfg, name = InclusiveMshrConfig(), "UHSCHuanCunInclusiveMSHR"
    else:
        raise TypeError("configuration must be InclusiveMshrConfig, dict, or None")
    top = InclusiveMshrBoundary(cfg)
    ports = [top.clock, top.reset, top.flush, top.alloc_valid, top.alloc_ready, top.alloc_address,
             top.alloc_source, top.alloc_index, top.lookup_valid, top.lookup_address, top.lookup_hit,
             top.refill_valid, top.refill_data, top.refill_source, top.resp_valid, top.resp_data,
             top.resp_source, top.occupancy]
    return verilog.convert(top, name=name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print direct export. / 打印 direct 导出。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
