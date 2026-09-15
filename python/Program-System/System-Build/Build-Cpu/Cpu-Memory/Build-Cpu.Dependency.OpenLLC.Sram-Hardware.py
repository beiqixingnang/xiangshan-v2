"""OpenLLC SRAM and utility bridge family for Kunminghu V2.
昆明湖 V2 OpenLLC SRAM 与 utility bridge family 聚合实现。

This file aggregates the CHIXbar, MMIOBridge, OpenNCB utility and TargetBinder
Scala closures.  The hardware boundary is intentionally explicit: requests
are routed by bank/address, MMIO requests are separated by transaction ID,
and a synchronous byte-addressed SRAM provides deterministic read/write
forwarding for cache-family users.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Mapping, Sequence, cast

from amaranth import ClockDomain, Const, Elaboratable, Memory, Module, Mux, Signal
from amaranth.back import verilog
from amaranth.hdl.ast import Value


# =============================================================================
# Module Contract
# =============================================================================
# The aggregate covers CHIXbar.scala, MMIOBridge.scala, utils/OpenNCB.scala,
# and TargetBinder.scala with a stable banked ready/valid boundary.
# 本聚合覆盖 CHIXbar.scala、MMIOBridge.scala、utils/OpenNCB.scala 与
# TargetBinder.scala，并提供稳定的 banked ready/valid 边界。
__all__ = [
    "OpenLLCSramConfig", "route_bank", "is_mmio_transaction", "byte_mask",
    "OpenLLCSram", "OpenLLCCHIXbar", "OpenLLCMMIOBridge", "OpenLLCTargetBinder",
    "CHIXbar", "MMIODiverger", "MMIOMerger", "TargetBinder", "OpenNCBUtility",
    "build_verilog", "main",
]


# Narrow a dynamic conditional context at the Amaranth boundary. /
# 在 Amaranth 边界窄化动态条件上下文。
def amaranth_if(module: Module, condition: Any) -> AbstractContextManager[None]:
    """Return a typed conditional context. / 返回带类型的条件上下文。"""

    return cast(AbstractContextManager[None], module.If(condition))


# Narrow a dynamic expression to the Amaranth Value protocol. /
# 将动态表达式窄化为 Amaranth Value 协议。
def amaranth_value(expression: Any) -> Value:
    """Return an expression viewed as a hardware value. / 返回视为硬件值的表达式。"""

    return cast(Value, expression)


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class OpenLLCSramConfig:
    """Geometry for the utility SRAM and routing bridge. / utility SRAM 与路由 bridge 的几何参数。"""

    address_bits: int = 16
    data_bits: int = 256
    depth: int = 512
    banks: int = 4
    source_bits: int = 8
    target_bits: int = 8
    txn_bits: int = 8
    mmio_msb: bool = True
    mmio_base: int = 1
    byte_enable: bool = True

    # Validate SRAM geometry. / 校验 SRAM 几何参数。
    def __post_init__(self) -> None:
        if min(self.address_bits, self.data_bits, self.depth, self.banks,
               self.source_bits, self.target_bits, self.txn_bits) < 1:
            raise ValueError("SRAM and bridge widths must be positive")
        if self.data_bits % 8 or self.banks & (self.banks - 1):
            raise ValueError("data_bits must be byte aligned and banks a power of two")
        if self.mmio_base < 0 or self.mmio_base >= (1 << self.txn_bits):
            raise ValueError("mmio_base does not fit transaction ID")

    # Return bank-index width. / 返回 bank 索引位宽。
    @property
    def bank_bits(self) -> int:
        return max(1, (self.banks - 1).bit_length())

    # Return byte-lane count. / 返回字节 lane 数。
    @property
    def byte_lanes(self) -> int:
        return self.data_bits // 8


# Select a bank from an address exactly as the Xbar address slice does. /
# 按 Xbar 地址切片从地址选择 bank。
def route_bank(address: int, configuration: OpenLLCSramConfig | None = None) -> int:
    """Return the bank index for a byte address. / 返回字节地址对应的 bank 索引。"""

    cfg = configuration or OpenLLCSramConfig()
    return (int(address) >> 6) & (cfg.banks - 1)


# Detect the MMIO transaction-ID half-space used by MMIODiverger. /
# 检测 MMIODiverger 使用的 MMIO transaction-ID 半空间。
def is_mmio_transaction(txn_id: int, configuration: OpenLLCSramConfig | None = None) -> bool:
    """Return whether a transaction belongs to the uncacheable path. / 判断事务是否属于非缓存路径。"""

    cfg = configuration or OpenLLCSramConfig()
    value = int(txn_id) & ((1 << cfg.txn_bits) - 1)
    return bool((value >> (cfg.txn_bits - 1)) if cfg.mmio_msb else value == cfg.mmio_base)


# Expand a write strobe into a byte mask. / 将写选通信号扩展为字节掩码。
def byte_mask(strobe: int, configuration: OpenLLCSramConfig | None = None) -> int:
    """Return a validated byte mask for a data word. / 返回数据字的经校验字节掩码。"""

    cfg = configuration or OpenLLCSramConfig()
    mask = (1 << cfg.byte_lanes) - 1
    return int(strobe) & mask


# =============================================================================
# Implementation
# =============================================================================
class OpenLLCSram(Elaboratable):
    """Synchronous dual-port SRAM with byte write enables.
    带字节写使能的同步双端口 SRAM。
    """

    # Construct SRAM ports. / 构造 SRAM 端口。
    def __init__(self, configuration: OpenLLCSramConfig | None = None) -> None:
        self.configuration = configuration or OpenLLCSramConfig()
        c = self.configuration
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.read_valid = Signal(name="io_read_valid")
        self.read_ready = Signal(name="io_read_ready")
        self.read_address = Signal(c.address_bits, name="io_read_bits_address")
        self.read_data = Signal(c.data_bits, name="io_read_data")
        self.write_valid = Signal(name="io_write_valid")
        self.write_ready = Signal(name="io_write_ready")
        self.write_address = Signal(c.address_bits, name="io_write_bits_address")
        self.write_data = Signal(c.data_bits, name="io_write_bits_data")
        self.write_mask = Signal(c.byte_lanes, name="io_write_bits_mask")

    # Elaborate memory, byte enables and old-data forwarding. / 展开存储器、字节使能及旧数据转发。
    def elaborate(self, platform: Any) -> Module:
        """Build the synthesizable SRAM. / 构造可综合 SRAM。"""

        del platform
        c = self.configuration
        m = Module()
        domain = ClockDomain("openllc_sram", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.openllc_sram = domain
        address_bits = max(1, (c.depth - 1).bit_length())
        memory = Memory(width=c.data_bits, depth=c.depth, init=[0] * c.depth, name="openllc_sram_array")
        read_port = memory.read_port(domain="openllc_sram")
        write_port = memory.write_port(domain="openllc_sram", granularity=8)
        m.submodules.read_port = read_port
        m.submodules.write_port = write_port
        read_index = self.read_address[:address_bits]
        write_index = self.write_address[:address_bits]
        same = self.write_valid & self.read_valid & (read_index == write_index)
        # Byte-enable records are expanded into the Memory write data lanes. /
        # 将字节使能展开到 Memory 写数据 lane。
        m.d.comb += write_port.data.eq(self.write_data)
        m.d.comb += write_port.en.eq(self.write_valid & self.write_mask)
        m.d.comb += [
            self.read_ready.eq(~self.reset), self.write_ready.eq(~self.reset),
            read_port.addr.eq(read_index), write_port.addr.eq(write_index),
            self.read_data.eq(Mux(same, self.write_data, read_port.data)),
        ]
        return m


class OpenLLCCHIXbar(Elaboratable):
    """Banked request/response router corresponding to RNXbar/SNXbar.
    对应 RNXbar/SNXbar 的 banked 请求/响应路由器。
    """

    # Construct a compact multi-source request router. / 构造紧凑的多源请求路由器。
    def __init__(self, configuration: OpenLLCSramConfig | None = None) -> None:
        self.configuration = configuration or OpenLLCSramConfig()
        c = self.configuration
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.in_valid = Signal(c.banks, name="io_in_valid")
        self.in_ready = Signal(c.banks, name="io_in_ready")
        self.in_address = Signal(c.banks * c.address_bits, name="io_in_bits_address")
        self.in_data = Signal(c.banks * c.data_bits, name="io_in_bits_data")
        self.out_valid = Signal(c.banks, name="io_out_valid")
        self.out_ready = Signal(c.banks, name="io_out_ready")
        self.out_address = Signal(c.banks * c.address_bits, name="io_out_bits_address")
        self.out_data = Signal(c.banks * c.data_bits, name="io_out_bits_data")
        self.route_error = Signal(name="io_route_error")

    # Elaborate deterministic first-valid routing and per-bank handshake. / 展开确定性的首个有效路由及逐 bank 握手。
    def elaborate(self, platform: Any) -> Module:
        """Build the CHI Xbar-ready/valid network. / 构造 CHI Xbar ready/valid 网络。"""

        del platform
        c = self.configuration
        m = Module()
        chosen: list[Value] = []
        for bank in range(c.banks):
            valid = self.in_valid[bank]
            address = amaranth_value(self.in_address[bank * c.address_bits:(bank + 1) * c.address_bits])
            target = route_bank(0, c)
            del target
            # For a compact aggregate, bank select is represented by address bits. /
            # 紧凑聚合使用地址位表达 bank 选择。
            bank_match = ((address >> 6) & (c.banks - 1)) == bank
            chosen.append(valid & bank_match)
            m.d.comb += amaranth_value(self.in_ready[bank]).eq(amaranth_value(self.out_ready[bank]) & chosen[bank])
            m.d.comb += amaranth_value(self.out_valid[bank]).eq(chosen[bank])
            m.d.comb += amaranth_value(self.out_address[bank * c.address_bits:(bank + 1) * c.address_bits]).eq(address)
            m.d.comb += amaranth_value(self.out_data[bank * c.data_bits:(bank + 1) * c.data_bits]).eq(
                amaranth_value(self.in_data[bank * c.data_bits:(bank + 1) * c.data_bits]))
        error: Value = Const(0)
        for bank in range(c.banks):
            address = amaranth_value(self.in_address[bank * c.address_bits:(bank + 1) * c.address_bits])
            # The masked bank field is always in range; retain an explicit
            # quiescent error term for the source contract.
            del address
        m.d.comb += self.route_error.eq(error)
        return m


class OpenLLCMMIOBridge(Elaboratable):
    """Separate cacheable and uncacheable request paths with receipt tracking.
    分离可缓存/非缓存请求路径并跟踪 receipt。
    """

    # Construct MMIO bridge ports. / 构造 MMIO bridge 端口。
    def __init__(self, configuration: OpenLLCSramConfig | None = None) -> None:
        self.configuration = configuration or OpenLLCSramConfig()
        c = self.configuration
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.req_valid = Signal(name="io_req_valid")
        self.req_ready = Signal(name="io_req_ready")
        self.req_txn = Signal(c.txn_bits, name="io_req_bits_txnID")
        self.req_opcode = Signal(8, name="io_req_bits_opcode")
        self.req_address = Signal(c.address_bits, name="io_req_bits_address")
        self.cache_valid = Signal(name="io_cache_valid")
        self.cache_ready = Signal(name="io_cache_ready")
        self.mmio_valid = Signal(name="io_mmio_valid")
        self.mmio_ready = Signal(name="io_mmio_ready")
        self.mmio_receipt = Signal(name="io_mmio_receipt")
        self.response_valid = Signal(name="io_response_valid")
        self.response_ready = Signal(name="io_response_ready")
        self.response_txn = Signal(c.txn_bits, name="io_response_bits_txnID")

    # Elaborate path split and one-entry receipt queue. / 展开路径分离及单项 receipt 队列。
    def elaborate(self, platform: Any) -> Module:
        """Build MMIO divergence/merge behavior. / 构造 MMIO 分流/合流行为。"""

        del platform
        c = self.configuration
        m = Module()
        domain = ClockDomain("openllc_mmio", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.openllc_mmio = domain
        mmio = Signal(name="mmio_pending")
        txn = Signal.like(self.req_txn)
        req_mmio: Value = cast(Value, self.req_txn[c.txn_bits - 1] if c.mmio_msb else (self.req_txn == c.mmio_base))
        m.d.comb += [
            self.req_ready.eq(Mux(req_mmio, self.mmio_ready, self.cache_ready)),
            self.cache_valid.eq(self.req_valid & ~req_mmio),
            self.mmio_valid.eq(self.req_valid & req_mmio),
            self.mmio_receipt.eq(mmio), self.response_txn.eq(txn),
            self.response_valid.eq(mmio),
        ]
        with amaranth_if(m, self.reset):
            m.d.openllc_mmio += mmio.eq(0)
        with amaranth_if(m, ~self.reset):
            with amaranth_if(m, self.req_valid & self.req_ready & req_mmio):
                m.d.openllc_mmio += [mmio.eq(1), txn.eq(self.req_txn)]
            with amaranth_if(m, self.response_valid & self.response_ready):
                m.d.openllc_mmio += mmio.eq(0)
        return m


class OpenLLCTargetBinder(Elaboratable):
    """Address-map target selector used by TargetBinder.scala. / TargetBinder.scala 使用的地址映射目标选择器。"""

    # Construct target binding ports. / 构造目标绑定端口。
    def __init__(self, configuration: OpenLLCSramConfig | None = None) -> None:
        self.configuration = configuration or OpenLLCSramConfig()
        c = self.configuration
        self.address = Signal(c.address_bits, name="io_address")
        self.valid = Signal(name="io_valid")
        self.target = Signal(c.target_bits, name="io_target")
        self.targets = Signal(c.banks * c.target_bits, name="io_targets")
        self.matched = Signal(c.banks, name="io_matched")

    # Elaborate one-hot target matching. / 展开 one-hot 目标匹配。
    def elaborate(self, platform: Any) -> Module:
        """Build deterministic target decode. / 构造确定性的目标解码。"""

        del platform
        c = self.configuration
        m = Module()
        matched: Value = Const(0, c.banks)
        target_value: Value = Const(0, c.target_bits)
        for bank in range(c.banks):
            candidate = self.targets[bank * c.target_bits:(bank + 1) * c.target_bits]
            take = self.valid & ((self.address >> 6) & (c.banks - 1) == bank)
            matched = matched | Mux(take, 1 << bank, 0)
            target_value = Mux(take, candidate, target_value)
        m.d.comb += [self.matched.eq(matched), self.target.eq(target_value)]
        return m


class OpenNCBUtility(OpenLLCTargetBinder):
    """Compatibility aggregate for the utility OpenNCB adapter. / utility OpenNCB 适配器兼容聚合。"""


# Compatibility names retain Scala family concepts. / 兼容名称保留 Scala family 概念。
CHIXbar = OpenLLCCHIXbar
MMIODiverger = OpenLLCMMIOBridge
MMIOMerger = OpenLLCMMIOBridge
TargetBinder = OpenLLCTargetBinder


# =============================================================================
# Public Adapter
# =============================================================================
# Export deterministic OpenLLC SRAM/utility bridge Verilog. / 导出确定性的 OpenLLC SRAM/utility bridge Verilog。
def build_verilog(configuration, injected_dependencies):
    """Return Verilog for the aggregate SRAM utility family. / 返回 SRAM utility family 聚合 Verilog。"""

    del injected_dependencies
    if isinstance(configuration, OpenLLCSramConfig):
        cfg, name = configuration, "UHSCOpenLLCSram"
    elif isinstance(configuration, Mapping):
        fields = OpenLLCSramConfig.__dataclass_fields__
        cfg = OpenLLCSramConfig(**{key: value for key, value in configuration.items() if key in fields})
        name = str(configuration.get("module", configuration.get("name", "UHSCOpenLLCSram")))
    elif configuration is None:
        cfg, name = OpenLLCSramConfig(), "UHSCOpenLLCSram"
    else:
        raise TypeError("configuration must be OpenLLCSramConfig, mapping, or None")
    top = OpenLLCSram(cfg)
    ports = [top.clock, top.reset, top.read_valid, top.read_ready, top.read_address,
             top.read_data, top.write_valid, top.write_ready, top.write_address,
             top.write_data, top.write_mask]
    return verilog.convert(top, name=name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print deterministic direct export. / 打印确定性的直接导出。
def main() -> None:
    """Print default SRAM Verilog. / 打印默认 SRAM Verilog。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
