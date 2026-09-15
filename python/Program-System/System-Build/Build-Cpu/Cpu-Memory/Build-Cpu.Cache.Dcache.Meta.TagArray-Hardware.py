"""V2 data-cache tag array. / V2 数据缓存标签阵列。"""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import AbstractContextManager
from typing import Protocol, cast

from amaranth import ClockDomain, Module, Mux, Signal
from amaranth.lib.memory import Memory
from amaranth.lib.wiring import Component, In, Out


# =============================================================================
# Module Contract
# =============================================================================
# The V2 TagArray contains two two-way TagSRAMBank instances for the default
# four-way cache. Each bank clears all 256 sets after reset, blocks reads and
# writes while clearing, accepts one masked write per cycle, and returns a
# synchronous read result one cycle after a fire. The adapter keeps a packed
# ``rdata`` probe while also exposing per-way response signals for differential
# checks; MBIST/DFT ports are injected dependencies at this leaf.
# V2 TagArray 默认由两个双路 TagSRAMBank 组成；复位后清零 256 个组，清零期间
# 屏蔽读写，每周期接受一次按路掩码写入，并在读握手后一个时钟返回同步结果。
__all__ = ["TagArrayConfig", "TagArray", "build_verilog", "main"]


class _MemoryReadPort(Protocol):
    """Typed view of an Amaranth memory read port. / Amaranth 存储器读端口的类型视图。"""

    addr: Signal
    data: Signal


class _MemoryWritePort(Protocol):
    """Typed view of an Amaranth memory write port. / Amaranth 存储器写端口的类型视图。"""

    addr: Signal
    data: Signal
    en: Signal


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class TagArrayConfig:
    # Serializable V2 tag-array geometry. / 可序列化的 V2 标签阵列几何参数。
    nSets: int = 256
    nWays: int = 4
    tagBits: int = 36
    tagECCBits: int = 7

    # Validate the SRAM dimensions and source-compatible ECC geometry. / 校验 SRAM 维度及源兼容 ECC 几何参数。
    def __post_init__(self) -> None:
        if self.nSets < 1 or self.nWays < 1:
            raise ValueError("nSets and nWays must be positive")
        if self.nSets & (self.nSets - 1):
            raise ValueError("nSets must be a power of two")
        if self.tagBits < 1 or self.tagECCBits < 0:
            raise ValueError("tag and ECC widths must be non-negative/positive")
        if self.nWays & (self.nWays - 1):
            raise ValueError("nWays must be a power of two")


# =============================================================================
# Implementation
# =============================================================================
class TagArray(Component):
    # Construct flattened V2 TagArray ports and per-way memories. / 构造扁平化 V2 TagArray 端口及各路存储器。
    # Resolve Component's runtime-created ports for static type checkers. / 为静态类型检查器解析 Component 运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    def __init__(self, cfg: TagArrayConfig | None = None):
        c = cfg or TagArrayConfig()
        self.cfg = c
        self.idxBits = max(1, c.nSets.bit_length() - 1)
        self.wayBits = max(1, c.nWays.bit_length() - 1)
        self.encodedBits = c.tagBits + c.tagECCBits
        super().__init__({
            "clock": In(1),
            "reset": In(1),
            "io_read_ready": Out(1),
            "io_read_valid": In(1),
            "io_read_bits_idx": In(self.idxBits),
            "io_read_bits_way_en": In(c.nWays),
            "io_write_valid": In(1),
            "io_write_bits_idx": In(self.idxBits),
            "io_write_bits_way_en": In(c.nWays),
            "io_write_bits_way": In(self.wayBits),
            "io_write_bits_tag": In(c.tagBits),
            "io_write_bits_ecc": In(c.tagECCBits),
            "io_rdata": Out(c.nWays * self.encodedBits),
        })
        self.read_ready = self.io_read_ready
        self.read_valid = self.io_read_valid
        self.read_idx = self.io_read_bits_idx
        self.read_way_en = self.io_read_bits_way_en
        self.write_valid = self.io_write_valid
        self.write_idx = self.io_write_bits_idx
        self.write_way_en = self.io_write_bits_way_en
        self.write_way = self.io_write_bits_way
        self.write_tag = self.io_write_bits_tag
        self.write_ecc = self.io_write_bits_ecc
        self.rdata = self.io_rdata
        self.resp = [Signal(self.encodedBits, name=f"io_resp_{i}")
                     for i in range(c.nWays)]
        self.read_addr = Signal(self.idxBits, reset=0, name="read_addr_reg")
        self.reset_count = Signal(max(1, (c.nSets + 1).bit_length()), reset=0)
        self.banks = [Memory(shape=self.encodedBits, depth=c.nSets,
                             init=[0] * c.nSets) for _ in range(c.nWays)]

    # Elaborate reset clearing, masked writes, and synchronous per-way reads. / 展开复位清零、按路写入及同步逐路读取逻辑。
    def elaborate(self, platform):
        del platform
        c = self.cfg
        m = Module()
        domain = ClockDomain("sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.sync = domain

        initializing = self.reset_count < c.nSets
        write_active = initializing | self.write_valid
        read_fire = self.read_valid & ~write_active
        encoded_write = self.write_tag | (self.write_ecc << c.tagBits)

        m.d.comb += self.read_ready.eq(~write_active)
        for way, memory in enumerate(self.banks):
            m.submodules[f"bank{way}"] = memory
            # The generated SRAM captures an address on a read fire and exposes
            # the selected row combinationally thereafter. / 生成的 SRAM 在读握手时锁存地址，随后组合输出选中行。
            read_port = cast(_MemoryReadPort, memory.read_port(domain="comb", transparent_for=()))
            m.d.comb += [
                read_port.addr.eq(self.read_addr),
                self.resp[way].eq(read_port.data),
            ]
            write_port = cast(_MemoryWritePort, memory.write_port(domain="sync"))
            m.d.comb += [
                write_port.addr.eq(Mux(initializing, self.reset_count,
                                       self.write_idx)),
                write_port.data.eq(Mux(initializing, 0, encoded_write)),
                write_port.en.eq(initializing |
                                 (self.write_valid & self.write_way_en[way])),
            ]

        # Pack responses low-way first, matching Chisel Vec flattening. / 按低路优先打包响应，匹配 Chisel Vec 展平顺序。
        for way in range(c.nWays):
            lo = way * self.encodedBits
            m.d.comb += cast(Signal, self.rdata[lo:lo + self.encodedBits]).eq(self.resp[way])

        with cast(AbstractContextManager[None], m.If(initializing)):
            m.d.sync += self.reset_count.eq(self.reset_count + 1)
        with cast(AbstractContextManager[None], m.If(read_fire)):
            m.d.sync += self.read_addr.eq(self.read_idx)
        return m


# =============================================================================
# Public Adapter
# =============================================================================
# Build deterministic TagArray Verilog for the requested configuration. / 为请求配置构建确定性 TagArray Verilog。
def build_verilog(configuration, injected_dependencies):
    # Export a deterministic flattened probe; external MBIST controls are injected at parent closure. / 导出确定性扁平探针，外部 MBIST 控制由父闭包注入。
    from amaranth.back import verilog

    del injected_dependencies
    if configuration is None:
        config = TagArrayConfig()
        name = "TagArray"
    elif isinstance(configuration, TagArrayConfig):
        config = configuration
        name = "TagArray"
    elif isinstance(configuration, dict):
        keys = {"nSets", "nWays", "tagBits", "tagECCBits"}
        config = TagArrayConfig(**{key: value for key, value in configuration.items()
                                   if key in keys})
        name = str(configuration.get("name", "TagArray"))
    else:
        raise TypeError("configuration must be TagArrayConfig, dict, or None")
    top = TagArray(config)
    ports = [top.clock, top.reset, top.read_ready, top.read_valid,
             top.read_idx, top.read_way_en, top.write_valid, top.write_idx,
             top.write_way_en, top.write_way, top.write_tag, top.write_ecc,
             top.rdata]
    return verilog.convert(top, name=name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print the default deterministic TagArray export. / 打印默认确定性 TagArray 导出。
def main() -> None:
    # Print the default deterministic Verilog export. / 打印默认确定性 Verilog 导出。
    print(build_verilog(None, None))


if __name__ == "__main__":
    main()
