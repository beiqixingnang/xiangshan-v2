"""XiangShan ICache MSHR rewritten in amaranth.
香山 ICache MSHR（缺失状态保持寄存器：登记请求、发 acquire、等 grant、上报信息）的 amaranth 重写。
"""
from __future__ import annotations

from dataclasses import dataclass

from amaranth import Cat, Elaboratable, Module, Signal


# Module Contract
# ---------------------------------------------------------------------------
# Public symbols:
#   - MshrConfig   : geometry config / 几何配置
#   - ICacheMshr   : one miss-status-holding-register entry
# Ports:
#   fencei, flush, wfi_req (inputs)
#   req_valid/ready/blk_paddr/v_set_idx         : request from demux
#   lookup_valid[2]/blk_paddr[2]/v_set_idx[2]   : snoop from mainPipe/prefetchPipe
#   lookup_hit[2]                               : same-cycle hit result
#   acquire_valid/ready/acquire_*/v_set_idx     : TileLink-A like issue channel
#   victim_way (input)                          : way selected at acquire fire
#   info_valid/info_blk_paddr/info_v_set_idx/info_way : response info
#   invalid (input)                             : clear entry after grant
#   wfi_safe, perf_latency                      : status outputs
__all__ = ["MshrConfig", "ICacheMshr"]


# Configuration
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MshrConfig:
    paddr_bits: int = 48
    block_off_bits: int = 6
    idx_bits: int = 8
    way_bits: int = 2
    alias_tag_bits: int = 2
    latency_bits: int = 16

    @property
    # blk_paddr_bits responsibility. / blk_paddr_bits 函数职责。
    def blk_paddr_bits(self) -> int:
        return self.paddr_bits - self.block_off_bits


# Implementation
# ---------------------------------------------------------------------------
class ICacheMshr(Elaboratable):
    """One MSHR entry. / 单个 MSHR 表项。"""

    # construct ports / 构造端口
    def __init__(self, entry_id: int = 0, is_fetch: bool = True, cfg: MshrConfig | None = None) -> None:
        self.cfg = cfg or MshrConfig()
        self.entry_id = entry_id
        self.is_fetch = is_fetch
        c = self.cfg
        self.fencei = Signal(name="fencei")
        self.flush = Signal(name="flush")
        self.wfi_req = Signal(name="wfi_req")
        self.req_valid = Signal(name="req_valid")
        self.req_ready = Signal(name="req_ready")
        self.req_blk_paddr = Signal(c.blk_paddr_bits, name="req_blk_paddr")
        self.req_v_set_idx = Signal(c.idx_bits, name="req_v_set_idx")
        self.lookup_valid = [Signal(name=f"lk_valid_{i}") for i in range(2)]
        self.lookup_blk_paddr = [Signal(c.blk_paddr_bits, name=f"lk_blk_{i}") for i in range(2)]
        self.lookup_v_set_idx = [Signal(c.idx_bits, name=f"lk_set_{i}") for i in range(2)]
        self.lookup_hit = [Signal(name=f"lk_hit_{i}") for i in range(2)]
        self.acquire_valid = Signal(name="acq_valid")
        self.acquire_ready = Signal(name="acq_ready")
        self.acquire_opcode = Signal(3, name="acq_opcode")
        self.acquire_size = Signal(3, name="acq_size")
        self.acquire_source = Signal(5, name="acq_source")
        self.acquire_address = Signal(c.paddr_bits, name="acq_address")
        self.acquire_alias_tag = Signal(c.alias_tag_bits, name="acq_alias_tag")
        self.acquire_v_set_idx = Signal(c.idx_bits, name="acq_v_set_idx")
        self.victim_way = Signal(c.way_bits, name="victim_way")
        self.info_valid = Signal(name="info_valid")
        self.info_blk_paddr = Signal(c.blk_paddr_bits, name="info_blk_paddr")
        self.info_v_set_idx = Signal(c.idx_bits, name="info_v_set_idx")
        self.info_way = Signal(c.way_bits, name="info_way")
        self.invalid = Signal(name="invalid")
        self.wfi_safe = Signal(name="wfi_safe")
        self.perf_latency = Signal(c.latency_bits, name="perf_latency")

    # MSHR state machine / MSHR 状态机
    def elaborate(self, platform) -> Module:
        m = Module()
        c = self.cfg
        valid = Signal(name="mshr_valid")
        flush_r = Signal(name="mshr_flush")
        fencei_r = Signal(name="mshr_fencei")
        issue = Signal(name="mshr_issue")
        blk_paddr = Signal(c.blk_paddr_bits, name="mshr_blk_paddr")
        v_set_idx = Signal(c.idx_bits, name="mshr_v_set_idx")
        way = Signal(c.way_bits, name="mshr_way")
        latency = Signal(c.latency_bits, name="mshr_latency")

        # same-cycle lookup / 同拍查询
        for i in range(2):
            m.d.comb += self.lookup_hit[i].eq(
                valid & ~fencei_r & ~flush_r
                & (self.lookup_v_set_idx[i] == v_set_idx)
                & (self.lookup_blk_paddr[i] == blk_paddr))

        # external flush/fencei / 外部冲刷
        with m.If(self.fencei | self.flush):
            m.d.sync += [fencei_r.eq(1), flush_r.eq(1)]
            with m.If(~issue):
                m.d.sync += valid.eq(0)

        # accept request / 接收请求
        m.d.comb += self.req_ready.eq(~valid & ~self.flush & ~self.fencei)
        with m.If(self.req_valid & self.req_ready):
            m.d.sync += [
                valid.eq(1), flush_r.eq(0), issue.eq(0), fencei_r.eq(0),
                blk_paddr.eq(self.req_blk_paddr), v_set_idx.eq(self.req_v_set_idx),
            ]

        # issue acquire (TileLink Get) / 发出 acquire
        m.d.comb += [
            self.acquire_valid.eq(valid & ~issue & ~self.flush & ~self.fencei & ~self.wfi_req),
            self.acquire_opcode.eq(4),  # TL Get / TL Get 操作码
            self.acquire_size.eq(c.block_off_bits),
            self.acquire_source.eq(self.entry_id),
            self.acquire_address.eq(blk_paddr << c.block_off_bits),
            self.acquire_alias_tag.eq(v_set_idx[c.idx_bits - c.alias_tag_bits:]),
            self.acquire_v_set_idx.eq(v_set_idx),
        ]
        with m.If(self.acquire_valid & self.acquire_ready):
            m.d.sync += [issue.eq(1), way.eq(self.victim_way), latency.eq(0)]

        # latency counter / 延迟计数
        with m.If(valid & issue):
            m.d.sync += latency.eq(latency + 1)

        # invalidation after grant / grant 完成后失效
        with m.If(self.invalid):
            m.d.sync += valid.eq(0)

        # info output / 信息输出
        m.d.comb += [
            self.info_valid.eq(valid & ~flush_r & ~fencei_r),
            self.info_blk_paddr.eq(blk_paddr),
            self.info_v_set_idx.eq(v_set_idx),
            self.info_way.eq(way),
            self.wfi_safe.eq(~(valid & issue)),
            self.perf_latency.eq(latency),
        ]
        return m


# Public Adapter
# ---------------------------------------------------------------------------
# build verilog / 生成 Verilog
def build_verilog() -> str:
    from amaranth.back import verilog

    top = ICacheMshr()
    ports = [top.fencei, top.flush, top.wfi_req, top.req_valid, top.req_ready,
             top.req_blk_paddr, top.req_v_set_idx, top.acquire_valid, top.acquire_ready,
             top.acquire_opcode, top.acquire_size, top.acquire_source, top.acquire_address,
             top.acquire_alias_tag, top.acquire_v_set_idx, top.victim_way,
             top.info_valid, top.info_blk_paddr, top.info_v_set_idx, top.info_way,
             top.invalid, top.wfi_safe, top.perf_latency]
    ports += top.lookup_valid + top.lookup_blk_paddr + top.lookup_v_set_idx + top.lookup_hit
    return verilog.convert(top, ports=ports)


# Direct Entry
# ---------------------------------------------------------------------------
# cli entry to emit verilog / 命令行入口：输出 Verilog
def main() -> None:
    print(build_verilog())


if __name__ == "__main__":
    main()
