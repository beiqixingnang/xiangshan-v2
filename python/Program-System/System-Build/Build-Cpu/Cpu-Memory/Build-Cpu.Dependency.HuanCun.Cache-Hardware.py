"""UHSC Kunminghu V2 HuanCun cache family boundary.
昆明湖 V2 HuanCun 缓存 family 边界。

The selected V2 DefaultConfig reaches HuanCun through the TileLink cache
closure.  This aggregate models the common cache-line request/refill/evict
contract, valid/dirty metadata, and one-entry miss handling in one file.  It
does not pretend that every debug/prefetch/SRAM helper is an independent
product module; those remain closure evidence behind this family boundary.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, cast

from amaranth import ClockDomain, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# HuanCun cache contract: lookup, hit response, miss request, refill, and
# dirty eviction. / HuanCun 缓存契约：查找、命中响应、缺失请求、回填及脏逐出。
__all__ = ["HuanCunConfig", "HuanCunCacheBoundary", "build_verilog", "main"]


# Cast Amaranth's generator controls to a context-manager protocol. / 将 Amaranth 生成器控制转换为上下文管理器协议。
def _if(module: Module, condition: Any) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.If(condition))


# Cast the Amaranth else branch to a context-manager protocol. / 将 Amaranth else 分支转换为上下文管理器协议。
def _else(module: Module) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.Else())


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class HuanCunConfig:
    """Finite HuanCun cache geometry. / 有限 HuanCun 缓存几何参数。"""

    sets: int = 256
    ways: int = 4
    line_bits: int = 512
    address_bits: int = 48
    source_bits: int = 6

    # Validate selected V2 cache geometry. / 校验选定 V2 缓存几何参数。
    def __post_init__(self) -> None:
        if self.sets < 1 or self.sets & (self.sets - 1):
            raise ValueError("HuanCun sets must be a power of two")
        if self.ways < 1 or self.line_bits < 8 or self.line_bits % 8:
            raise ValueError("invalid HuanCun cache geometry")

    @property
    # Return set-index width. / 返回组索引位宽。
    def set_bits(self) -> int:
        return max(1, (self.sets - 1).bit_length())

    @property
    # Return tag width. / 返回标签位宽。
    def tag_bits(self) -> int:
        return max(1, self.address_bits - self.set_bits - 6)


# =============================================================================
# Implementation
# =============================================================================
class HuanCunCacheBoundary(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """One-line-per-way HuanCun cache protocol boundary. / 每路单缓存行 HuanCun 协议边界。"""

    # Construct request/refill/eviction ports. / 构造请求、回填及逐出端口。
    def __init__(self, configuration: HuanCunConfig | None = None) -> None:
        self.configuration = configuration or HuanCunConfig()
        c = self.configuration
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.flush = Signal(name="io_flush")
        self.req_valid = Signal(name="io_req_valid")
        self.req_ready = Signal(name="io_req_ready")
        self.req_address = Signal(c.address_bits, name="io_req_address")
        self.req_write = Signal(name="io_req_write")
        self.req_data = Signal(c.line_bits, name="io_req_data")
        self.req_source = Signal(c.source_bits, name="io_req_source")
        self.resp_valid = Signal(name="io_resp_valid")
        self.resp_data = Signal(c.line_bits, name="io_resp_data")
        self.resp_source = Signal(c.source_bits, name="io_resp_source")
        self.miss_valid = Signal(name="io_miss_valid")
        self.miss_address = Signal(c.address_bits, name="io_miss_address")
        self.miss_source = Signal(c.source_bits, name="io_miss_source")
        self.evict_valid = Signal(name="io_evict_valid")
        self.evict_address = Signal(c.address_bits, name="io_evict_address")
        self.evict_data = Signal(c.line_bits, name="io_evict_data")
        self.refill_valid = Signal(name="io_refill_valid")
        self.refill_data = Signal(c.line_bits, name="io_refill_data")
        self.refill_source = Signal(c.source_bits, name="io_refill_source")
        self.hit = Signal(name="io_hit")
        self.dirty = Signal(name="io_dirty")
        self.state = Signal(2, name="io_state")

    # Elaborate cache lookup and one-outstanding miss state. / 展开缓存查找及单个未决缺失状态。
    def elaborate(self, platform: Any) -> Module:
        del platform
        c = self.configuration
        m = Module()
        domain = ClockDomain("huancun_cache", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.huancun_cache = domain
        valid = Signal(name="line_valid")
        dirty = Signal(name="line_dirty")
        tag = Signal(c.tag_bits, name="line_tag")
        line = Signal(c.line_bits, name="line_data")
        source = Signal(c.source_bits, name="pending_source")
        pending_addr = Signal(c.address_bits, name="pending_address")
        pending_write = Signal(name="pending_write")
        pending = Signal(name="pending")
        req_tag = self.req_address[c.address_bits - c.tag_bits:]
        hit = valid & (tag == req_tag)
        m.d.comb += [self.req_ready.eq(~pending & ~self.flush), self.hit.eq(hit), self.dirty.eq(dirty),
                     self.state.eq(Mux(pending, 2, Mux(valid, Mux(dirty, 1, 0), 0))),
                     self.resp_valid.eq(self.req_valid & self.req_ready & hit),
                     self.resp_data.eq(Mux(hit, Mux(self.req_write, self.req_data, line), 0)),
                     self.resp_source.eq(self.req_source), self.miss_valid.eq(pending & ~hit & ~self.flush),
                     self.miss_address.eq(pending_addr), self.miss_source.eq(source),
                     self.evict_valid.eq(pending & dirty & ~self.flush), self.evict_address.eq(pending_addr),
                     self.evict_data.eq(line)]
        with _if(m, self.reset | self.flush):
            m.d.huancun_cache += [valid.eq(0), dirty.eq(0), pending.eq(0)]
        with _else(m):
            with _if(m, self.req_valid & self.req_ready):
                with _if(m, hit):
                    with _if(m, self.req_write):
                        m.d.huancun_cache += [line.eq(self.req_data), dirty.eq(1)]
                with _else(m):
                    m.d.huancun_cache += [pending.eq(1), pending_addr.eq(self.req_address), pending_write.eq(self.req_write), source.eq(self.req_source)]
            with _if(m, self.refill_valid & pending):
                m.d.huancun_cache += [line.eq(self.refill_data), tag.eq(self.refill_source), valid.eq(1), dirty.eq(pending_write), pending.eq(0)]
        return m


# Source-oriented alias. / 源导向别名。
HuanCunCache = HuanCunCacheBoundary


# =============================================================================
# Public Adapter
# =============================================================================
# Export deterministic HuanCun cache Verilog. / 导出确定性的 HuanCun 缓存 Verilog。
def build_verilog(configuration, injected_dependencies):
    """Return Verilog for the HuanCun cache family. / 返回 HuanCun 缓存 family Verilog。"""

    del injected_dependencies
    if isinstance(configuration, HuanCunConfig):
        cfg, name = configuration, "UHSCHuanCunCache"
    elif isinstance(configuration, dict):
        fields = HuanCunConfig.__dataclass_fields__
        cfg = HuanCunConfig(**{key: int(value) for key, value in configuration.items() if key in fields})
        name = str(configuration.get("module", configuration.get("name", "UHSCHuanCunCache")))
    elif configuration is None:
        cfg, name = HuanCunConfig(), "UHSCHuanCunCache"
    else:
        raise TypeError("configuration must be HuanCunConfig, dict, or None")
    top = HuanCunCacheBoundary(cfg)
    ports = [top.clock, top.reset, top.flush, top.req_valid, top.req_ready, top.req_address,
             top.req_write, top.req_data, top.req_source, top.resp_valid, top.resp_data,
             top.resp_source, top.miss_valid, top.miss_address, top.miss_source, top.evict_valid,
             top.evict_address, top.evict_data, top.refill_valid, top.refill_data,
             top.refill_source, top.hit, top.dirty, top.state]
    return verilog.convert(top, name=name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print deterministic direct export. / 打印确定性的 direct 导出。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
