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

from amaranth import Array, Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog
from amaranth.hdl.ast import Value


# =============================================================================
# Module Contract
# =============================================================================
# HuanCun cache contract: lookup, hit response, miss request, refill, and
# dirty eviction. / HuanCun 缓存契约：查找、命中响应、缺失请求、回填及脏逐出。
__all__ = [
    "HuanCunConfig", "HuanCunCacheBoundary", "cache_transaction_observation",
    "build_verilog", "main", "HUANCUN_CACHE_SOURCE_PATHS",
]


# This bounded cache follows the request-buffer dependency, metadata victim,
# and refill/writeback boundaries from the frozen HuanCun sources.  It does
# not claim to implement a complete banked coherent L2. / 此有界缓存遵循冻结
# HuanCun 源码的请求缓冲依赖、元数据 victim、回填/写回边界；它不声称实现完整的
# 分 bank 一致性 L2。
HUANCUN_CACHE_SOURCE_PATHS: tuple[str, ...] = (
    "upstream/huancun/src/main/scala/huancun/RequestBuffer.scala",
    "upstream/huancun/src/main/scala/huancun/MetaData.scala",
    "upstream/huancun/src/main/scala/huancun/DataStorage.scala",
    "upstream/huancun/src/main/scala/huancun/HuanCun.scala",
)


def cache_transaction_observation(*, req_valid: bool, req_ready: bool,
                                  miss_valid: bool, miss_ready: bool,
                                  evict_valid: bool, evict_ready: bool,
                                  refill_valid: bool, refill_ready: bool,
                                  resp_valid: bool, resp_ready: bool,
                                  flush: bool = False) -> dict[str, int]:
    """Return one source-backed bounded cache transaction observation.

    The request/refill/response channels advance only on Decoupled fire; a
    dirty victim blocks miss issuance until its write-back fires.  This mirrors
    RequestBuffer's fire-based dequeue and the HuanCun slice's Decoupled
    wiring, while remaining intentionally one-entry. / request/refill/response
    通道只在 Decoupled fire 时推进；脏 victim 在其写回 fire 前阻塞 miss 发出。
    这对应 RequestBuffer 基于 fire 的出队和 HuanCun slice 的 Decoupled 接线，
    同时刻意保持单项有界。
    """
    blocked = bool(flush)
    return {
        "req_fire": int(bool(req_valid) and bool(req_ready) and not blocked),
        "miss_fire": int(bool(miss_valid) and bool(miss_ready) and not blocked),
        "evict_fire": int(bool(evict_valid) and bool(evict_ready) and not blocked),
        "refill_fire": int(bool(refill_valid) and bool(refill_ready) and not blocked),
        "resp_fire": int(bool(resp_valid) and bool(resp_ready) and not blocked),
        "flush_cancel": int(blocked and any((req_valid, miss_valid, evict_valid, refill_valid, resp_valid))),
    }


# Cast Amaranth's generator controls to a context-manager protocol. / 将 Amaranth 生成器控制转换为上下文管理器协议。
def amaranth_if(module: Module, condition: Any) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.If(condition))


# Cast the Amaranth else branch to a context-manager protocol. / 将 Amaranth else 分支转换为上下文管理器协议。
def amaranth_else(module: Module) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.Else())


# Narrow dynamic Amaranth values at the DSL boundary. / 在 DSL 边界窄化动态 Amaranth 值。
def amaranth_value(expression: Any) -> Value:
    return cast(Value, expression)


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

    # Return the byte offset width carried by a cache-line address. /
    # 返回缓存行地址携带的字节偏移位宽。
    @property
    # Return offset bits. /
    def offset_bits(self) -> int:
        line_bytes = self.line_bits // 8
        return max(0, (line_bytes - 1).bit_length())

    # Validate selected V2 cache geometry. / 校验选定 V2 缓存几何参数。
    def __post_init__(self) -> None:
        if self.sets < 1 or self.sets & (self.sets - 1):
            raise ValueError("HuanCun sets must be a power of two")
        line_bytes = self.line_bits // 8
        if self.ways < 1 or self.ways > 16 or self.line_bits < 8 or self.line_bits % 8:
            raise ValueError("invalid HuanCun cache geometry")
        if line_bytes & (line_bytes - 1):
            raise ValueError("HuanCun line size must be a power of two")
        if self.address_bits <= self.offset_bits + self.set_bits:
            raise ValueError("HuanCun address width leaves no tag bits")

    @property
    # Return set-index width. / 返回组索引位宽。
    def set_bits(self) -> int:
        return max(1, (self.sets - 1).bit_length())

    @property
    # Return tag width. / 返回标签位宽。
    def tag_bits(self) -> int:
        return max(1, self.address_bits - self.set_bits - self.offset_bits)

    @property
    # Return the byte mask width used by partial line writes. /
    # 返回部分缓存行写入使用的字节掩码位宽。
    # Return mask bits. /
    def mask_bits(self) -> int:
        return self.line_bits // 8

    @property
    # Return the replacement-way index width. / 返回替换路索引位宽。
    # Return way bits. /
    def way_bits(self) -> int:
        return max(1, (self.ways - 1).bit_length())


# =============================================================================
# Implementation
# =============================================================================
class HuanCunCacheBoundary(Elaboratable):
    # Resolve runtime-created ports for static type checking. / 为静态类型检查解析运行时创建的端口。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    """Set-associative HuanCun cache protocol boundary.

    The implementation is intentionally bounded, but it materializes the
    state that the Scala ``DataStorage``/``MetaData``/``RequestBuffer``
    closure observes: valid/dirty/tag/data arrays, round-robin replacement,
    one outstanding miss, write-back eviction, and a refill-to-response
    transition.  The legacy ``refill_source`` tag convention is accepted when
    ``refill_has_address`` is low; selected top-level users can provide a full
    line address through the new address port.
    每个 set/way 都有有效位、脏位、标签和数据阵列，并实现轮询替换、单未决
    缺失、写回逐出以及回填到响应的状态迁移；当 ``refill_has_address`` 为零
    时兼容旧版将 ``refill_source`` 作为标签的约定。
    """

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
        self.resp_ready = Signal(name="io_resp_ready", init=1)
        self.resp_data = Signal(c.line_bits, name="io_resp_data")
        self.resp_source = Signal(c.source_bits, name="io_resp_source")
        self.miss_valid = Signal(name="io_miss_valid")
        self.miss_ready = Signal(name="io_miss_ready", init=1)
        self.miss_address = Signal(c.address_bits, name="io_miss_address")
        self.miss_source = Signal(c.source_bits, name="io_miss_source")
        self.evict_valid = Signal(name="io_evict_valid")
        self.evict_ready = Signal(name="io_evict_ready", init=1)
        self.evict_address = Signal(c.address_bits, name="io_evict_address")
        self.evict_data = Signal(c.line_bits, name="io_evict_data")
        self.refill_valid = Signal(name="io_refill_valid")
        self.refill_data = Signal(c.line_bits, name="io_refill_data")
        self.refill_source = Signal(c.source_bits, name="io_refill_source")
        # A full refill address removes ambiguity between source IDs and tags.
        # 完整回填地址消除 source ID 与标签之间的歧义。
        self.refill_address = Signal(c.address_bits, name="io_refill_address")
        self.refill_has_address = Signal(name="io_refill_has_address")
        self.refill_tag = Signal(c.tag_bits, name="io_refill_tag")
        self.refill_ready = Signal(name="io_refill_ready")
        self.req_mask = Signal(c.mask_bits, name="io_req_mask")
        self.req_fire = Signal(name="io_req_fire")
        self.miss_fire = Signal(name="io_miss_fire")
        self.refill_fire = Signal(name="io_refill_fire")
        self.evict_fire = Signal(name="io_evict_fire")
        self.resp_fire = Signal(name="io_resp_fire")
        self.hit = Signal(name="io_hit")
        self.dirty = Signal(name="io_dirty")
        self.state = Signal(2, name="io_state")
        self.miss_set = Signal(c.set_bits, name="io_miss_set")
        self.miss_tag = Signal(c.tag_bits, name="io_miss_tag")
        self.evict_way = Signal(c.way_bits, name="io_evict_way")

    # Elaborate cache lookup, replacement, write-back, and refill state.
    # 展开缓存查找、替换、写回及回填状态。
    # Elaborate cache lookup and replacement state. /
    def elaborate(self, platform: Any) -> Module:
        del platform
        c = self.configuration
        m = Module()
        domain = ClockDomain("huancun_cache", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.huancun_cache = domain
        # Materialize one metadata/data row per set and way.  Array indexing is
        # dynamic on the set field and synthesizes into a bounded mux/RAM.
        # 每个 set/way 物化一行元数据及数据；动态 set 索引综合为有界 mux/RAM。
        entries = c.sets * c.ways
        index_width = max(1, (entries - 1).bit_length())
        valid_mem = Array(Signal(name=f"valid_{index}", init=0) for index in range(entries))
        dirty_mem = Array(Signal(name=f"dirty_{index}", init=0) for index in range(entries))
        tag_mem = Array(Signal(c.tag_bits, name=f"tag_{index}", init=0) for index in range(entries))
        data_mem = Array(Signal(c.line_bits, name=f"data_{index}", init=0) for index in range(entries))
        rr_mem = Array(Signal(c.way_bits, name=f"rr_{index}", init=0) for index in range(c.sets))

        # Decode a byte address into line offset, set, and tag. / 将字节地址译码为
        # 行偏移、set 和标签。
        line_address = self.req_address >> c.offset_bits
        req_set = line_address[:c.set_bits]
        req_tag = line_address[c.set_bits:c.set_bits + c.tag_bits]
        # The arithmetic width includes a spare high bit, avoiding truncation
        # when ``ways`` is not a power of two. / 算术宽度多保留一位，避免 ways
        # 非二次幂时被截断。
        req_entry_base = Signal(index_width, name="req_entry_base")
        m.d.comb += req_entry_base.eq(amaranth_value(req_set) * c.ways)

        hit_vec = []
        dirty_vec = []
        data_vec = []
        for way in range(c.ways):
            entry = req_entry_base + way
            valid_at = valid_mem[entry]
            tag_at = tag_mem[entry]
            hit_vec.append(valid_at & (tag_at == req_tag))
            dirty_vec.append(dirty_mem[entry])
            data_vec.append(data_mem[entry])
        hit = Const(0)
        hit_way = Signal(c.way_bits, name="hit_way")
        hit_dirty = Signal(name="hit_dirty")
        hit_data = Signal(c.line_bits, name="hit_data")
        m.d.comb += [hit_way.eq(0), hit_dirty.eq(0), hit_data.eq(0)]
        for way, way_hit in enumerate(hit_vec):
            # Priority order is deterministic if malformed state has duplicate
            # tags. / 即使异常状态出现重复标签，优先级仍是确定的。
            with amaranth_if(m, way_hit & ~hit):
                m.d.comb += [hit_way.eq(way), hit_dirty.eq(dirty_vec[way]),
                             hit_data.eq(data_vec[way])]
            hit = hit | way_hit

        # Pick an invalid way first, otherwise use the per-set round-robin way.
        # 优先选择无效路，否则使用每个 set 的轮询路。
        rr_way = rr_mem[req_set]
        victim_way = Signal(c.way_bits, name="victim_way")
        victim_valid = Signal(name="victim_valid")
        victim_dirty = Signal(name="victim_dirty")
        victim_tag = Signal(c.tag_bits, name="victim_tag")
        victim_data = Signal(c.line_bits, name="victim_data")
        m.d.comb += [victim_way.eq(rr_way), victim_valid.eq(0), victim_dirty.eq(0),
                     victim_tag.eq(0), victim_data.eq(0)]
        found_invalid = Const(0)
        for way in range(c.ways):
            entry = req_entry_base + way
            valid_at = valid_mem[entry]
            choose = ~amaranth_value(found_invalid) & ~amaranth_value(valid_at)
            with amaranth_if(m, choose):
                m.d.comb += [victim_way.eq(way), victim_valid.eq(valid_at),
                             victim_dirty.eq(dirty_mem[entry]), victim_tag.eq(tag_mem[entry]),
                             victim_data.eq(data_mem[entry])]
            found_invalid = amaranth_value(found_invalid) | ~amaranth_value(valid_at)
        # If every way was valid, the round-robin way supplies victim metadata.
        rr_entry = req_entry_base + rr_way
        with amaranth_if(m, ~amaranth_value(found_invalid)):
            m.d.comb += [victim_valid.eq(valid_mem[rr_entry]), victim_dirty.eq(dirty_mem[rr_entry]),
                         victim_tag.eq(tag_mem[rr_entry]), victim_data.eq(data_mem[rr_entry])]

        source = Signal(c.source_bits, name="pending_source")
        pending_addr = Signal(c.address_bits, name="pending_address")
        pending_set = Signal(c.set_bits, name="pending_set")
        pending_tag = Signal(c.tag_bits, name="pending_tag")
        pending_way = Signal(c.way_bits, name="pending_way")
        pending_write = Signal(name="pending_write")
        pending_data = Signal(c.line_bits, name="pending_data")
        pending_mask = Signal(c.mask_bits, name="pending_mask")
        pending = Signal(name="pending")
        # A miss cannot accept a refill before the outgoing request has fired.
        # This is the one-entry counterpart of RequestBuffer's issue-fire
        # discipline. / miss 在其向外请求 fire 前不能接收 refill；这是
        # RequestBuffer issue-fire 纪律的单项对应物。
        miss_issued = Signal(name="miss_issued")
        evict_pending = Signal(name="evict_pending")
        # Capture eviction metadata with the accepted miss.  The request bus
        # may change while the write-back is pending, so live victim muxes are
        # not a stable eviction transaction.
        # 在接收 miss 时锁存逐出元数据；写回未决期间请求总线可能变化，因此
        # 不能把实时 victim mux 当作稳定的逐出事务。
        evict_tag_r = Signal(c.tag_bits, name="evict_tag_r")
        evict_data_r = Signal(c.line_bits, name="evict_data_r")
        response_pending = Signal(name="response_pending")
        response_data = Signal(c.line_bits, name="response_data")
        response_source = Signal(c.source_bits, name="response_source")

        # A zero mask is the legacy full-line write convention. / 零掩码沿用旧版
        # 的整行写入约定。
        full_mask = (1 << c.mask_bits) - 1
        effective_mask = Mux(self.req_mask == 0, full_mask, self.req_mask)
        req_fire = self.req_valid & self.req_ready
        miss_fire = self.miss_valid & self.miss_ready
        refill_fire = self.refill_valid & self.refill_ready
        evict_fire = self.evict_valid & self.evict_ready
        resp_fire = self.resp_valid & self.resp_ready

        # Refill address may be supplied explicitly; otherwise retain the
        # pending set and interpret ``refill_source`` as the legacy tag.
        # 回填可提供完整地址；否则保留 pending set 并将 refill_source 解释为旧版标签。
        refill_line_address = self.refill_address >> c.offset_bits
        refill_set = Mux(self.refill_has_address, refill_line_address[:c.set_bits], pending_set)
        refill_tag = Mux(self.refill_has_address,
                         refill_line_address[c.set_bits:c.set_bits + c.tag_bits],
                         Mux(self.refill_tag != 0, self.refill_tag, pending_tag))
        refill_entry = Signal(index_width, name="refill_entry")
        m.d.comb += refill_entry.eq(amaranth_value(refill_set) * c.ways + pending_way)

        # Merge a partial write into the refilled line. / 将部分写入合并到回填行。
        merged_refill = Signal(c.line_bits, name="merged_refill")
        merge_parts = []
        bytes_per_line = c.mask_bits
        for byte in range(bytes_per_line):
            old_byte = self.refill_data[byte * 8:(byte + 1) * 8]
            new_byte = pending_data[byte * 8:(byte + 1) * 8]
            choose_new = pending_mask[byte]
            merge_parts.append(Mux(choose_new, new_byte, old_byte))
        # Cat takes the first item as the least-significant part. / Cat 首项是最低有效片段。
        m.d.comb += merged_refill.eq(Cat(*merge_parts))

        # A dirty victim must leave before the replacement miss is issued, and
        # a refill must wait for that miss's Decoupled fire.  Likewise, retain
        # responses until the receiver accepts them.  This is the concrete
        # ready/valid boundary missing from the earlier valid-only model.
        # 脏 victim 必须先离开才能发出替换 miss，refill 必须等待该 miss 的
        # Decoupled fire；同样，response 必须保留到接收方接受。这补上了此前
        # 仅 valid 模型缺失的具体 ready/valid 边界。
        m.d.comb += [self.req_ready.eq(~pending & ~response_pending & ~self.flush), self.req_fire.eq(req_fire),
                     self.miss_valid.eq(pending & ~evict_pending & ~miss_issued & ~self.flush),
                     self.miss_fire.eq(miss_fire),
                     self.refill_ready.eq(pending & miss_issued & ~evict_pending & ~self.flush),
                     self.refill_fire.eq(refill_fire), self.evict_fire.eq(evict_fire),
                     self.resp_valid.eq(response_pending & ~self.flush), self.resp_fire.eq(resp_fire),
                     self.hit.eq(self.req_valid & hit),
                     self.dirty.eq(Mux(hit, hit_dirty, victim_dirty)),
                     self.state.eq(Mux(response_pending, 3,
                                       Mux(evict_pending, 1, Mux(pending, 2, 0)))),
                     self.resp_data.eq(response_data), self.resp_source.eq(response_source),
                     self.miss_address.eq(pending_addr),
                     self.miss_source.eq(source), self.miss_set.eq(pending_set), self.miss_tag.eq(pending_tag),
                     self.evict_valid.eq(evict_pending & ~self.flush),
                     self.evict_address.eq((evict_tag_r << (c.set_bits + c.offset_bits)) |
                                          (pending_set << c.offset_bits)),
                     self.evict_data.eq(evict_data_r), self.evict_way.eq(pending_way)]

        # Reset/flush invalidates all ways, as DataStorage's metadata reset does.
        # 复位/flush 使所有路无效，对应 DataStorage 元数据复位。
        with amaranth_if(m, self.reset | self.flush):
            m.d.huancun_cache += [pending.eq(0), miss_issued.eq(0), evict_pending.eq(0), response_pending.eq(0)]
            for index in range(entries):
                m.d.huancun_cache += [valid_mem[index].eq(0), dirty_mem[index].eq(0)]
            for index in range(c.sets):
                m.d.huancun_cache += rr_mem[index].eq(0)
        with amaranth_else(m):
            # Keep responses stable under backpressure; only the concrete
            # response handshake retires them. / 在反压下保持 response 稳定；
            # 仅实际 response 握手将其退休。
            with amaranth_if(m, resp_fire):
                m.d.huancun_cache += response_pending.eq(0)
            # Write-back is also Decoupled.  A stalled sink retains the victim
            # and prevents the miss/refill path from overtaking it. / 写回同样
            # 是 Decoupled；停滞 sink 保留 victim 并阻止 miss/refill 路径超越它。
            with amaranth_if(m, evict_fire):
                m.d.huancun_cache += evict_pending.eq(0)
            with amaranth_if(m, miss_fire):
                m.d.huancun_cache += miss_issued.eq(1)
            with amaranth_if(m, req_fire):
                with amaranth_if(m, hit):
                    with amaranth_if(m, self.req_write):
                        # Byte-enable writes model PutPartialData and PutFullData.
                        # 字节使能写同时覆盖 PutPartialData/PutFullData。
                        for byte in range(bytes_per_line):
                            old_byte = data_mem[req_entry_base + hit_way][byte * 8:(byte + 1) * 8]
                            new_byte = self.req_data[byte * 8:(byte + 1) * 8]
                            with amaranth_if(m, effective_mask[byte]):
                                m.d.huancun_cache += old_byte.eq(new_byte)
                        m.d.huancun_cache += dirty_mem[req_entry_base + hit_way].eq(1)
                    # A hit response is registered so data/source remain
                    # stable until ``resp.fire``. / 命中 response 被寄存，
                    # 使 data/source 在 ``resp.fire`` 前保持稳定。
                    m.d.huancun_cache += [response_data.eq(Mux(self.req_write, self.req_data, hit_data)),
                                          response_source.eq(self.req_source), response_pending.eq(1)]
                with amaranth_else(m):
                    m.d.huancun_cache += [pending.eq(1), pending_addr.eq(self.req_address),
                                          pending_set.eq(req_set), pending_tag.eq(req_tag),
                                          pending_way.eq(victim_way), pending_write.eq(self.req_write),
                                          pending_data.eq(self.req_data), pending_mask.eq(effective_mask),
                                          source.eq(self.req_source), evict_tag_r.eq(victim_tag),
                                          evict_data_r.eq(victim_data), miss_issued.eq(0),
                                          evict_pending.eq(victim_dirty)]
                    with amaranth_if(m, ~victim_valid):
                        # Invalid victims cannot produce a write-back transaction.
                        m.d.huancun_cache += evict_pending.eq(0)
                    with amaranth_if(m, victim_way == (c.ways - 1)):
                        m.d.huancun_cache += rr_mem[req_set].eq(0)
                    with amaranth_else(m):
                        m.d.huancun_cache += rr_mem[req_set].eq(victim_way + 1)
            with amaranth_if(m, refill_fire):
                m.d.huancun_cache += [data_mem[refill_entry].eq(merged_refill),
                                      tag_mem[refill_entry].eq(refill_tag), valid_mem[refill_entry].eq(1),
                                      dirty_mem[refill_entry].eq(pending_write), pending.eq(0),
                                      miss_issued.eq(0), evict_pending.eq(0),
                                      response_data.eq(Mux(pending_write, pending_data, self.refill_data)),
                                      response_source.eq(source), response_pending.eq(1)]
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
             top.resp_source, top.resp_ready, top.miss_valid, top.miss_ready, top.miss_address,
             top.miss_source, top.evict_valid, top.evict_ready,
             top.evict_address, top.evict_data, top.refill_valid, top.refill_data,
             top.refill_source, top.refill_address, top.refill_has_address, top.refill_tag,
             top.refill_ready, top.req_mask, top.req_fire, top.miss_fire, top.refill_fire,
             top.evict_fire, top.resp_fire, top.hit, top.dirty, top.state, top.miss_set,
             top.miss_tag, top.evict_way]
    return verilog.convert(top, name=name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print deterministic direct export. / 打印确定性的 direct 导出。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
