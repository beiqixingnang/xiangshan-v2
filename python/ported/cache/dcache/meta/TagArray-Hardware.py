"""TagArray: per-way tag SRAM banks with ECC field. / TagArray：带 ECC 字段的按路 tag SRAM 组。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from amaranth import Cat, ClockDomain, Module, Mux, Signal
from amaranth.lib.memory import Memory
from amaranth.lib.wiring import Component, In, Out


# =============================================================================
# Module Contract
# =============================================================================
# Public symbols / 公开符号:
#   - TagArrayConfig, TagArray, build_verilog, main
# Port contract / 端口契约 (flattened validation adapter):
#   - clock/reset are explicit; read_valid/read_idx form a one-cycle request;
#     read_ready is low while reset clearing is in progress or a write is active.
#   - write_valid/write_idx/write_way_en/write_tag/write_ecc perform a masked
#     multi-way write.  rdata packs one encoded tag per way, low way first.
# Real logic / 真实逻辑:
#   - TagSRAMBank per way: single-port tag SRAM addressed by set index;
#     write stores tag+ecc (asECCTag concatenation), read returns per-way
#     tags for hit comparison.
#   / 每路一个 TagSRAMBank；按组索引读写 tag+ecc。
# Status / 状态: PYTHON_PRESENT_UNVERIFIED (phase-1 bulk port / 阶段一批量重写)
__all__ = ["TagArrayConfig", "TagArray", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class TagArrayConfig:
    # frozen config / 冻结配置
    # The pinned kunminghu-v3 reference instantiates a 256-set, four-way,
    # 36-bit tag plus 7-bit ECC array (43 encoded bits per way).
    nSets: int = 256
    nWays: int = 4
    tagBits: int = 36
    tagECCBits: int = 7


# =============================================================================
# Implementation
# =============================================================================
class TagArray(Component):
    # per-way tag SRAM array / 按路 tag SRAM 阵列
    def __init__(self, cfg: TagArrayConfig | None = None):
        c = cfg or TagArrayConfig()
        if c.nSets < 1 or c.nWays < 1 or c.tagBits < 1 or c.tagECCBits < 0:
            raise ValueError("TagArray dimensions must be positive")
        if c.nSets & (c.nSets - 1):
            raise ValueError("nSets must be a power of two for the SRAM address")
        self.cfg = c
        idxBits = max(1, c.nSets.bit_length() - 1)
        wayBits = max(1, c.nWays.bit_length() - 1)
        self.idxBits = idxBits
        self.clock: Signal
        self.reset: Signal
        self.read_idx: Signal
        self.read_valid: Signal
        self.read_way_en: Signal
        self.read_ready: Signal
        self.write_valid: Signal
        self.write_idx: Signal
        self.write_way_en: Signal
        self.write_way: Signal
        self.write_tag: Signal
        self.write_ecc: Signal
        self.rdata: Signal
        super().__init__({
            "clock": In(1),
            "reset": In(1),
            "read_idx": In(idxBits),
            "read_valid": In(1),
            "read_way_en": In(c.nWays),
            "read_ready": Out(1),
            "write_valid": In(1),
            "write_idx": In(idxBits),
            "write_way_en": In(c.nWays),
            # Kept as an explicit compatibility port for old phase-1 callers;
            # the source contract uses the write_way_en mask.
            "write_way": In(wayBits),
            "write_tag": In(c.tagBits),
            "write_ecc": In(c.tagECCBits),
            "rdata": Out(c.nWays * (c.tagBits + c.tagECCBits)),
        })
        self.banks = [Memory(shape=c.tagBits + c.tagECCBits, depth=c.nSets,
                             init=[0] * c.nSets) for _ in range(c.nWays)]
        self.reset_count = Signal(max(1, (c.nSets + 1).bit_length()), reset=0)

    def elaborate(self, platform):
        # Clear every SRAM row, then arbitrate masked writes over synchronous reads
        # / 先清空每个 SRAM 行，再在同步读之上执行按路掩码写入仲裁
        m = Module()
        c = self.cfg
        domain = ClockDomain("sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.sync = domain
        encoded_bits = c.tagBits + c.tagECCBits
        initializing = self.reset_count < c.nSets
        write_active = initializing | self.write_valid
        m.d.comb += self.read_ready.eq(~write_active)
        read_fire = self.read_valid & self.read_ready
        write_data = Cat(self.write_tag, self.write_ecc)
        for i in range(c.nWays):
            m.submodules[f"bank{i}"] = self.banks[i]
            r = cast(Any, self.banks[i].read_port(domain="sync", transparent_for=()))
            m.d.comb += r.addr.eq(self.read_idx)
            m.d.comb += r.en.eq(read_fire)
            lo = i * encoded_bits
            m.d.comb += cast(Any, self.rdata)[lo:lo + encoded_bits].eq(r.data)
            w = cast(Any, self.banks[i].write_port())
            m.d.comb += w.addr.eq(Mux(initializing, self.reset_count, self.write_idx))
            m.d.comb += w.data.eq(Mux(initializing, 0, write_data))
            m.d.comb += w.en.eq(initializing | (self.write_valid & self.write_way_en[i]))
        with cast(Any, m.If(initializing)):
            m.d.sync += self.reset_count.eq(self.reset_count + 1)
        return m


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(config: TagArrayConfig | None = None,
                  injected_dependencies: dict | None = None,
                  name: str = "TagArray") -> str:
    # minimal public adapter generating Verilog via amaranth / 最小公开适配器，用 amaranth 生成 Verilog
    from amaranth.back import verilog
    del injected_dependencies
    top = TagArray(config)
    return verilog.convert(top, name=name,
                           ports=[top.clock, top.reset, top.read_idx,
                                  top.read_valid, top.read_way_en, top.read_ready,
                                  top.write_valid, top.write_idx,
                                  top.write_way_en, top.write_way, top.write_tag,
                                  top.write_ecc, top.rdata], emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    # direct elaboration entry / 直接入口
    print(build_verilog())


if __name__ == "__main__":
    main()
