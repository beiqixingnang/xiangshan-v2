"""UHSC Kunminghu V2 CoupledL2 directory family boundary.
昆明湖 V2 CoupledL2 目录 family 边界。

This aggregate keeps the stateful Directory.scala contract in one
parameterised Amaranth module: two-stage tag/meta lookup, invalid-way and
replacement selection, MSHR occupancy exclusion, metadata/tag writes, and
refill replacement reporting.  Nested SRAM/ECC helpers remain represented by
the explicit family boundary instead of being fabricated as unrelated files.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amaranth import Array, ClockDomain, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# Directory.scala performs a pipelined lookup and chooses a hit/invalid/LRU
# way; this aggregate exposes the same observable decisions and write ports.
# Directory.scala 执行流水化查找并选择命中/无效/LRU 路；本聚合暴露相同的
# 可观察决策和写端口。
__all__ = [
    "CoupledL2DirectoryConfig",
    "CoupledL2Directory",
    "Directory",
    "directory_reference_step",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class CoupledL2DirectoryConfig:
    """Finite V2 directory geometry. / 有限 V2 目录几何参数。"""

    sets: int = 512
    ways: int = 8
    tag_bits: int = 31
    state_bits: int = 2
    client_bits: int = 1
    alias_bits: int = 2
    prefetch_src_bits: int = 3
    mshr_entries: int = 16
    mshr_id_bits: int = 8
    req_source_bits: int = 5
    replacement: str = "drrip"
    enable_tag_ecc: bool = False

    # Validate the locked Kunminghu V2 directory geometry. / 校验锁定昆明湖 V2 目录几何。
    def __post_init__(self) -> None:
        if self.sets < 1 or self.sets & (self.sets - 1):
            raise ValueError("sets must be a positive power of two")
        if self.ways < 1 or self.ways > 32:
            raise ValueError("ways must be in the range 1..32")
        if min(self.tag_bits, self.state_bits, self.client_bits, self.mshr_entries) < 1:
            raise ValueError("directory widths and entry count must be positive")
        if self.alias_bits < 0 or self.prefetch_src_bits < 0:
            raise ValueError("optional metadata widths must be non-negative")
        if self.replacement not in {"random", "plru", "drrip", "srrip", "rr"}:
            raise ValueError("unsupported replacement policy")

    # Return the set-index width. / 返回组索引位宽。
    @property
    def set_bits(self) -> int:
        return max(1, (self.sets - 1).bit_length())

    # Return the way-index width. / 返回路索引位宽。
    @property
    def way_bits(self) -> int:
        return max(1, (self.ways - 1).bit_length())

    # Return the packed metadata width. / 返回打包元数据位宽。
    @property
    def meta_bits(self) -> int:
        return (1 + self.state_bits + self.client_bits + self.alias_bits
                + 1 + self.prefetch_src_bits + 1 + 1 + 1)


# =============================================================================
# Implementation
# =============================================================================
def directory_reference_step(
    request_tag: int,
    tags: list[int],
    states: list[int],
    replacement_way: int,
    way_mask: int,
    occupied_mask: int = 0,
    cmo_all: bool = False,
    cmo_way: int = 0,
) -> dict[str, int]:
    """Compute the deterministic Directory.scala way equations.
    计算确定性的 Directory.scala 路选择方程。
    """

    ways = len(tags)
    if len(states) != ways:
        raise ValueError("tags/states length mismatch")
    valid = [int(state != 0) for state in states]
    hits = [int(valid[index] and tags[index] == request_tag) for index in range(ways)]
    hit_count = sum(hits)
    hit = int((hit_count == 1) or (cmo_all and 0 <= cmo_way < ways and valid[cmo_way]))
    invalid = next((index for index, value in enumerate(valid) if not value), 0)
    free = (~occupied_mask) & ((1 << ways) - 1)
    selected = cmo_way if cmo_all else (hits.index(1) if hit_count == 1 else replacement_way)
    selected &= (1 << max(1, (ways - 1).bit_length())) - 1
    if not (free & (1 << selected)):
        selected = next((index for index in range(ways) if free & (1 << index)), selected)
    if not (way_mask & (1 << selected)) and way_mask:
        selected = next((index for index in range(ways) if way_mask & (1 << index) and free & (1 << index)), selected)
    retry = int(free == 0)
    if hit_count > 1:
        hit = 0
    return {
        "hit": hit,
        "way": selected,
        "invalid_way": invalid,
        "retry": retry,
        "multi_hit": int(hit_count > 1),
        "hit_count": hit_count,
    }


class CoupledL2Directory(Elaboratable):
    """Two-stage metadata directory with V2 replacement decisions.
    带 V2 替换决策的两级元数据目录。
    """

    # Construct the explicit directory lookup, write, and MSHR ports. / 构造显式目录查找、写入及 MSHR 端口。
    def __init__(self, configuration: CoupledL2DirectoryConfig | None = None) -> None:
        self.configuration = configuration or CoupledL2DirectoryConfig()
        c = self.configuration
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")

        # Read request and replacement context. / 读取请求及替换上下文。
        self.read_valid = Signal(name="io_read_valid")
        self.read_ready = Signal(name="io_read_ready")
        self.read_tag = Signal(c.tag_bits, name="io_read_bits_tag")
        self.read_set = Signal(c.set_bits, name="io_read_bits_set")
        self.read_way_mask = Signal(c.ways, name="io_read_bits_wayMask")
        self.read_replacer_channel = Signal(3, name="io_read_bits_replacerInfo_channel")
        self.read_replacer_opcode = Signal(3, name="io_read_bits_replacerInfo_opcode")
        self.read_replacer_req_source = Signal(c.req_source_bits, name="io_read_bits_replacerInfo_reqSource")
        self.read_replacer_refill_prefetch = Signal(name="io_read_bits_replacerInfo_refill_prefetch")
        self.read_refill = Signal(name="io_read_bits_refill")
        self.read_mshr_id = Signal(c.mshr_id_bits, name="io_read_bits_mshrId")
        self.read_cmo_all = Signal(name="io_read_bits_cmoAll")
        self.read_cmo_way = Signal(c.way_bits, name="io_read_bits_cmoWay")

        # Directory response. / 目录响应。
        self.resp_valid = Signal(name="io_resp_valid")
        self.resp_hit = Signal(name="io_resp_bits_hit")
        self.resp_tag = Signal(c.tag_bits, name="io_resp_bits_tag")
        self.resp_set = Signal(c.set_bits, name="io_resp_bits_set")
        self.resp_way = Signal(c.way_bits, name="io_resp_bits_way")
        self.resp_meta_dirty = Signal(name="io_resp_bits_meta_dirty")
        self.resp_meta_state = Signal(c.state_bits, name="io_resp_bits_meta_state")
        self.resp_meta_clients = Signal(c.client_bits, name="io_resp_bits_meta_clients")
        self.resp_meta_alias = Signal(c.alias_bits, name="io_resp_bits_meta_alias") if c.alias_bits else Signal(1, name="io_resp_bits_meta_alias")
        self.resp_meta_prefetch = Signal(name="io_resp_bits_meta_prefetch")
        self.resp_meta_prefetch_src = Signal(c.prefetch_src_bits, name="io_resp_bits_meta_prefetchSrc") if c.prefetch_src_bits else Signal(1, name="io_resp_bits_meta_prefetchSrc")
        self.resp_meta_accessed = Signal(name="io_resp_bits_meta_accessed")
        self.resp_meta_tag_err = Signal(name="io_resp_bits_meta_tagErr")
        self.resp_meta_data_err = Signal(name="io_resp_bits_meta_dataErr")
        self.resp_error = Signal(name="io_resp_bits_error")
        self.resp_replacer_channel = Signal(3, name="io_resp_bits_replacerInfo_channel")
        self.resp_replacer_opcode = Signal(3, name="io_resp_bits_replacerInfo_opcode")
        self.resp_replacer_req_source = Signal(c.req_source_bits, name="io_resp_bits_replacerInfo_reqSource")
        self.resp_replacer_refill_prefetch = Signal(name="io_resp_bits_replacerInfo_refill_prefetch")

        # Metadata and tag write requests. / 元数据及标签写请求。
        self.meta_write_valid = Signal(name="io_metaWReq_valid")
        self.meta_write_set = Signal(c.set_bits, name="io_metaWReq_bits_set")
        self.meta_write_way_oh = Signal(c.ways, name="io_metaWReq_bits_wayOH")
        self.meta_write_dirty = Signal(name="io_metaWReq_bits_wmeta_dirty")
        self.meta_write_state = Signal(c.state_bits, name="io_metaWReq_bits_wmeta_state")
        self.meta_write_clients = Signal(c.client_bits, name="io_metaWReq_bits_wmeta_clients")
        self.meta_write_alias = Signal(c.alias_bits, name="io_metaWReq_bits_wmeta_alias") if c.alias_bits else Signal(1, name="io_metaWReq_bits_wmeta_alias")
        self.meta_write_prefetch = Signal(name="io_metaWReq_bits_wmeta_prefetch")
        self.meta_write_prefetch_src = Signal(c.prefetch_src_bits, name="io_metaWReq_bits_wmeta_prefetchSrc") if c.prefetch_src_bits else Signal(1, name="io_metaWReq_bits_wmeta_prefetchSrc")
        self.meta_write_accessed = Signal(name="io_metaWReq_bits_wmeta_accessed")
        self.meta_write_tag_err = Signal(name="io_metaWReq_bits_wmeta_tagErr")
        self.meta_write_data_err = Signal(name="io_metaWReq_bits_wmeta_dataErr")
        self.tag_write_valid = Signal(name="io_tagWReq_valid")
        self.tag_write_set = Signal(c.set_bits, name="io_tagWReq_bits_set")
        self.tag_write_way = Signal(c.way_bits, name="io_tagWReq_bits_way")
        self.tag_write_tag = Signal(c.tag_bits, name="io_tagWReq_bits_wtag")

        # Refill/replacement response. / 回填/替换响应。
        self.repl_resp_valid = Signal(name="io_replResp_valid")
        self.repl_resp_tag = Signal(c.tag_bits, name="io_replResp_bits_tag")
        self.repl_resp_set = Signal(c.set_bits, name="io_replResp_bits_set")
        self.repl_resp_way = Signal(c.way_bits, name="io_replResp_bits_way")
        self.repl_resp_meta_dirty = Signal(name="io_replResp_bits_meta_dirty")
        self.repl_resp_meta_state = Signal(c.state_bits, name="io_replResp_bits_meta_state")
        self.repl_resp_meta_clients = Signal(c.client_bits, name="io_replResp_bits_meta_clients")
        self.repl_resp_meta_alias = Signal(c.alias_bits, name="io_replResp_bits_meta_alias") if c.alias_bits else Signal(1, name="io_replResp_bits_meta_alias")
        self.repl_resp_meta_prefetch = Signal(name="io_replResp_bits_meta_prefetch")
        self.repl_resp_meta_prefetch_src = Signal(c.prefetch_src_bits, name="io_replResp_bits_meta_prefetchSrc") if c.prefetch_src_bits else Signal(1, name="io_replResp_bits_meta_prefetchSrc")
        self.repl_resp_meta_accessed = Signal(name="io_replResp_bits_meta_accessed")
        self.repl_resp_meta_tag_err = Signal(name="io_replResp_bits_meta_tagErr")
        self.repl_resp_meta_data_err = Signal(name="io_replResp_bits_meta_dataErr")
        self.repl_resp_mshr_id = Signal(c.mshr_id_bits, name="io_replResp_bits_mshrId")
        self.repl_resp_retry = Signal(name="io_replResp_bits_retry")
        self.repl_resp_error = Signal(name="io_replResp_bits_error")

        # Flattened MSHR occupancy context; one bit per active MSHR. / 展平 MSHR 占用上下文，每个活动 MSHR 一位。
        self.mshr_valid = Signal(c.mshr_entries, name="io_msInfo_valid")
        self.mshr_set = Signal(c.mshr_entries * c.set_bits, name="io_msInfo_bits_set")
        self.mshr_way = Signal(c.mshr_entries * c.way_bits, name="io_msInfo_bits_way")
        self.mshr_block_refill = Signal(c.mshr_entries, name="io_msInfo_bits_blockRefill")
        self.mshr_dir_hit = Signal(c.mshr_entries, name="io_msInfo_bits_dirHit")
        self.mshr_will_free = Signal(c.mshr_entries, name="io_msInfo_bits_willFree")

    # Elaborate storage, lookup pipeline, replacement selection, and writes. / 展开存储、查找流水线、替换选择及写入。
    def elaborate(self, platform: Any) -> Module:
        del platform
        c = self.configuration
        m = Module()
        domain = ClockDomain("coupled_l2_directory", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.coupled_l2_directory = domain

        depth = c.sets * c.ways
        tags = [Signal(c.tag_bits, name=f"directory_tag_{index}") for index in range(depth)]
        dirty = [Signal(name=f"directory_dirty_{index}") for index in range(depth)]
        states = [Signal(c.state_bits, name=f"directory_state_{index}") for index in range(depth)]
        clients = [Signal(c.client_bits, name=f"directory_clients_{index}") for index in range(depth)]
        aliases = [Signal(max(1, c.alias_bits), name=f"directory_alias_{index}") for index in range(depth)]
        prefetch = [Signal(name=f"directory_prefetch_{index}") for index in range(depth)]
        prefetch_src = [Signal(max(1, c.prefetch_src_bits), name=f"directory_prefetch_src_{index}") for index in range(depth)]
        accessed = [Signal(name=f"directory_accessed_{index}") for index in range(depth)]
        tag_err = [Signal(name=f"directory_tag_err_{index}") for index in range(depth)]
        data_err = [Signal(name=f"directory_data_err_{index}") for index in range(depth)]
        replacement = [Signal(c.way_bits, name=f"directory_replacement_{index}") for index in range(c.sets)]

        # Decode the flattened MSHR context for the current set. / 解码当前组的展平 MSHR 上下文。
        occupied_mask: Any = 0
        for index in range(c.mshr_entries):
            set_lo = index * c.set_bits
            way_lo = index * c.way_bits
            same_set = self.mshr_set[set_lo:set_lo + c.set_bits] == self.read_set
            active = self.mshr_valid[index] & ~self.mshr_will_free[index]
            occupies = active & same_set & (self.mshr_block_refill[index] | self.mshr_dir_hit[index])
            way_value = self.mshr_way[way_lo:way_lo + c.way_bits]
            way_one_hot: Any = 0
            for way in range(c.ways):
                way_one_hot = way_one_hot | Mux(way_value == way, 1 << way, 0)
            occupied_mask = occupied_mask | Mux(occupies, way_one_hot, 0)

        # Writes are synchronous and block a simultaneous read, as in the V2 SRAM path.
        # 写入为同步操作并阻塞同周期读取，符合 V2 SRAM 路径。
        read_fire = self.read_valid & self.read_ready
        m.d.comb += self.read_ready.eq(~self.reset & ~self.meta_write_valid & ~self.tag_write_valid)
        write_index = self.meta_write_set * c.ways + self.tag_write_way
        meta_base = self.meta_write_set * c.ways
        for way in range(c.ways):
            meta_index = meta_base + way
            with m.If(self.meta_write_valid & self.meta_write_way_oh[way]):
                m.d.coupled_l2_directory += [
                    Array(dirty)[meta_index].eq(self.meta_write_dirty),
                    Array(states)[meta_index].eq(self.meta_write_state),
                    Array(clients)[meta_index].eq(self.meta_write_clients),
                    Array(aliases)[meta_index].eq(self.meta_write_alias),
                    Array(prefetch)[meta_index].eq(self.meta_write_prefetch),
                    Array(prefetch_src)[meta_index].eq(self.meta_write_prefetch_src),
                    Array(accessed)[meta_index].eq(self.meta_write_accessed),
                    Array(tag_err)[meta_index].eq(self.meta_write_tag_err),
                    Array(data_err)[meta_index].eq(self.meta_write_data_err),
                ]
        with m.If(self.tag_write_valid):
            m.d.coupled_l2_directory += Array(tags)[write_index].eq(self.tag_write_tag)

        # Stage one captures all ways and request metadata at the read edge. / 一级在读取边沿捕获所有路及请求元数据。
        req1_valid = Signal(name="directory_req1_valid")
        req1_tag = Signal(c.tag_bits, name="directory_req1_tag")
        req1_set = Signal(c.set_bits, name="directory_req1_set")
        req1_way_mask = Signal(c.ways, name="directory_req1_way_mask")
        req1_refill = Signal(name="directory_req1_refill")
        req1_mshr_id = Signal(c.mshr_id_bits, name="directory_req1_mshr_id")
        req1_cmo_all = Signal(name="directory_req1_cmo_all")
        req1_cmo_way = Signal(c.way_bits, name="directory_req1_cmo_way")
        req1_channel = Signal(3, name="directory_req1_channel")
        req1_opcode = Signal(3, name="directory_req1_opcode")
        req1_req_source = Signal(c.req_source_bits, name="directory_req1_req_source")
        req1_refill_prefetch = Signal(name="directory_req1_refill_prefetch")
        tags1 = [Signal(c.tag_bits, name=f"directory_tags1_{way}") for way in range(c.ways)]
        dirty1 = [Signal(name=f"directory_dirty1_{way}") for way in range(c.ways)]
        states1 = [Signal(c.state_bits, name=f"directory_states1_{way}") for way in range(c.ways)]
        clients1 = [Signal(c.client_bits, name=f"directory_clients1_{way}") for way in range(c.ways)]
        aliases1 = [Signal(max(1, c.alias_bits), name=f"directory_aliases1_{way}") for way in range(c.ways)]
        prefetch1 = [Signal(name=f"directory_prefetch1_{way}") for way in range(c.ways)]
        prefetch_src1 = [Signal(max(1, c.prefetch_src_bits), name=f"directory_prefetch_src1_{way}") for way in range(c.ways)]
        accessed1 = [Signal(name=f"directory_accessed1_{way}") for way in range(c.ways)]
        tag_err1 = [Signal(name=f"directory_tag_err1_{way}") for way in range(c.ways)]
        data_err1 = [Signal(name=f"directory_data_err1_{way}") for way in range(c.ways)]

        # Stage two is the externally visible response stage. / 二级是对外可见的响应级。
        req2_valid = Signal(name="directory_req2_valid")
        req2_tag = Signal(c.tag_bits, name="directory_req2_tag")
        req2_set = Signal(c.set_bits, name="directory_req2_set")
        req2_way_mask = Signal(c.ways, name="directory_req2_way_mask")
        req2_refill = Signal(name="directory_req2_refill")
        req2_mshr_id = Signal(c.mshr_id_bits, name="directory_req2_mshr_id")
        req2_cmo_all = Signal(name="directory_req2_cmo_all")
        req2_cmo_way = Signal(c.way_bits, name="directory_req2_cmo_way")
        req2_channel = Signal(3, name="directory_req2_channel")
        req2_opcode = Signal(3, name="directory_req2_opcode")
        req2_req_source = Signal(c.req_source_bits, name="directory_req2_req_source")
        req2_refill_prefetch = Signal(name="directory_req2_refill_prefetch")
        tags2 = [Signal(c.tag_bits, name=f"directory_tags2_{way}") for way in range(c.ways)]
        dirty2 = [Signal(name=f"directory_dirty2_{way}") for way in range(c.ways)]
        states2 = [Signal(c.state_bits, name=f"directory_states2_{way}") for way in range(c.ways)]
        clients2 = [Signal(c.client_bits, name=f"directory_clients2_{way}") for way in range(c.ways)]
        aliases2 = [Signal(max(1, c.alias_bits), name=f"directory_aliases2_{way}") for way in range(c.ways)]
        prefetch2 = [Signal(name=f"directory_prefetch2_{way}") for way in range(c.ways)]
        prefetch_src2 = [Signal(max(1, c.prefetch_src_bits), name=f"directory_prefetch_src2_{way}") for way in range(c.ways)]
        accessed2 = [Signal(name=f"directory_accessed2_{way}") for way in range(c.ways)]
        tag_err2 = [Signal(name=f"directory_tag_err2_{way}") for way in range(c.ways)]
        data_err2 = [Signal(name=f"directory_data_err2_{way}") for way in range(c.ways)]

        # Stage one read and stage two transfer. / 一级读取及二级传递。
        m.d.coupled_l2_directory += [
            req1_valid.eq(read_fire),
            req1_tag.eq(self.read_tag),
            req1_set.eq(self.read_set),
            req1_way_mask.eq(self.read_way_mask),
            req1_refill.eq(self.read_refill),
            req1_mshr_id.eq(self.read_mshr_id),
            req1_cmo_all.eq(self.read_cmo_all),
            req1_cmo_way.eq(self.read_cmo_way),
            req1_channel.eq(self.read_replacer_channel),
            req1_opcode.eq(self.read_replacer_opcode),
            req1_req_source.eq(self.read_replacer_req_source),
            req1_refill_prefetch.eq(self.read_replacer_refill_prefetch),
            req2_valid.eq(req1_valid),
            req2_tag.eq(req1_tag),
            req2_set.eq(req1_set),
            req2_way_mask.eq(req1_way_mask),
            req2_refill.eq(req1_refill),
            req2_mshr_id.eq(req1_mshr_id),
            req2_cmo_all.eq(req1_cmo_all),
            req2_cmo_way.eq(req1_cmo_way),
            req2_channel.eq(req1_channel),
            req2_opcode.eq(req1_opcode),
            req2_req_source.eq(req1_req_source),
            req2_refill_prefetch.eq(req1_refill_prefetch),
        ]
        for way in range(c.ways):
            index_expr = self.read_set * c.ways + way
            m.d.coupled_l2_directory += [
                tags1[way].eq(Array(tags)[index_expr]),
                dirty1[way].eq(Array(dirty)[index_expr]),
                states1[way].eq(Array(states)[index_expr]),
                clients1[way].eq(Array(clients)[index_expr]),
                aliases1[way].eq(Array(aliases)[index_expr]),
                prefetch1[way].eq(Array(prefetch)[index_expr]),
                prefetch_src1[way].eq(Array(prefetch_src)[index_expr]),
                accessed1[way].eq(Array(accessed)[index_expr]),
                tag_err1[way].eq(Array(tag_err)[index_expr]),
                data_err1[way].eq(Array(data_err)[index_expr]),
                tags2[way].eq(tags1[way]),
                dirty2[way].eq(dirty1[way]),
                states2[way].eq(states1[way]),
                clients2[way].eq(clients1[way]),
                aliases2[way].eq(aliases1[way]),
                prefetch2[way].eq(prefetch1[way]),
                prefetch_src2[way].eq(prefetch_src1[way]),
                accessed2[way].eq(accessed1[way]),
                tag_err2[way].eq(tag_err1[way]),
                data_err2[way].eq(data_err1[way]),
            ]

        # Hit/invalid/replacement equations at stage two. / 二级命中、无效及替换方程。
        hit_vec: list[Any] = []
        invalid_vec: list[Any] = []
        for way in range(c.ways):
            valid = states2[way] != 0
            hit_vec.append(valid & (tags2[way] == req2_tag))
            invalid_vec.append(~valid)
        hit_count = sum(hit_vec)
        multi_hit = hit_count > 1
        hit_any = (hit_count == 1) & ~multi_hit
        hit_way: Any = 0
        for way in range(c.ways):
            hit_way = Mux(hit_vec[way], way, hit_way)
        invalid_way: Any = 0
        invalid_seen: Any = 0
        for way in range(c.ways):
            take = invalid_vec[way] & ~invalid_seen
            invalid_way = Mux(take, way, invalid_way)
            invalid_seen = invalid_seen | invalid_vec[way]
        repl_index = req2_set
        repl_way = Array(replacement)[repl_index]
        free_mask = (~occupied_mask) & ((1 << c.ways) - 1)
        selected_way: Any = repl_way
        selected_way = Mux(invalid_seen, invalid_way, selected_way)
        selected_way = Mux(hit_any, hit_way, selected_way)
        selected_way = Mux(req2_cmo_all, req2_cmo_way, selected_way)
        # Respect MSHR free-way exclusion and caller way mask. / 遵守 MSHR 空闲路排除及调用者路掩码。
        free_selected = free_mask.bit_select(selected_way, 1)
        first_free: Any = 0
        first_free_seen: Any = 0
        for way in range(c.ways):
            take = free_mask[way] & ~first_free_seen
            first_free = Mux(take, way, first_free)
            first_free_seen = first_free_seen | take
        selected_way = Mux(~free_selected, first_free, selected_way)
        masked_selected = self.read_way_mask.bit_select(selected_way, 1)
        first_masked: Any = 0
        first_masked_seen: Any = 0
        for way in range(c.ways):
            take = self.read_way_mask[way] & free_mask[way] & ~first_masked_seen
            first_masked = Mux(take, way, first_masked)
            first_masked_seen = first_masked_seen | take
        selected_way = Mux(~masked_selected & (self.read_way_mask != 0), first_masked, selected_way)
        retry = ~free_mask.any()
        selected_meta = lambda values: Array(values)[selected_way]

        # Public response and refill response fields. / 对外响应及回填响应字段。
        m.d.comb += [
            self.resp_valid.eq(req2_valid),
            self.resp_hit.eq((hit_any | (req2_cmo_all & ~Array(invalid_vec)[req2_cmo_way])) & ~multi_hit),
            self.resp_tag.eq(selected_meta(tags2)),
            self.resp_set.eq(req2_set),
            self.resp_way.eq(selected_way),
            self.resp_meta_dirty.eq(selected_meta(dirty2)),
            self.resp_meta_state.eq(selected_meta(states2)),
            self.resp_meta_clients.eq(selected_meta(clients2)),
            self.resp_meta_alias.eq(selected_meta(aliases2)),
            self.resp_meta_prefetch.eq(selected_meta(prefetch2)),
            self.resp_meta_prefetch_src.eq(selected_meta(prefetch_src2)),
            self.resp_meta_accessed.eq(selected_meta(accessed2)),
            self.resp_meta_tag_err.eq(selected_meta(tag_err2)),
            self.resp_meta_data_err.eq(selected_meta(data_err2)),
            self.resp_error.eq((selected_meta(tag_err2) | selected_meta(data_err2) | multi_hit) & req2_valid),
            self.resp_replacer_channel.eq(req2_channel),
            self.resp_replacer_opcode.eq(req2_opcode),
            self.resp_replacer_req_source.eq(req2_req_source),
            self.resp_replacer_refill_prefetch.eq(req2_refill_prefetch),
            self.repl_resp_valid.eq(req2_valid & req2_refill),
            self.repl_resp_tag.eq(selected_meta(tags2)),
            self.repl_resp_set.eq(req2_set),
            self.repl_resp_way.eq(selected_way),
            self.repl_resp_meta_dirty.eq(selected_meta(dirty2)),
            self.repl_resp_meta_state.eq(selected_meta(states2)),
            self.repl_resp_meta_clients.eq(selected_meta(clients2)),
            self.repl_resp_meta_alias.eq(selected_meta(aliases2)),
            self.repl_resp_meta_prefetch.eq(selected_meta(prefetch2)),
            self.repl_resp_meta_prefetch_src.eq(selected_meta(prefetch_src2)),
            self.repl_resp_meta_accessed.eq(selected_meta(accessed2)),
            self.repl_resp_meta_tag_err.eq(selected_meta(tag_err2)),
            self.repl_resp_meta_data_err.eq(selected_meta(data_err2)),
            self.repl_resp_mshr_id.eq(req2_mshr_id),
            self.repl_resp_retry.eq(retry & req2_refill),
            self.repl_resp_error.eq((selected_meta(tag_err2) | selected_meta(data_err2) | multi_hit) & req2_valid),
        ]

        # Round-robin update is a deterministic bounded stand-in for V2 PLRU/DRRIP state.
        # 轮询更新是 V2 PLRU/DRRIP 状态的确定性有界实现。
        with m.If(self.reset):
            m.d.coupled_l2_directory += [req1_valid.eq(0), req2_valid.eq(0)]
            for pointer in replacement:
                m.d.coupled_l2_directory += pointer.eq(0)
        with m.Elif(req2_valid & (hit_any | (req2_refill & ~retry))):
            m.d.coupled_l2_directory += Array(replacement)[req2_set].eq(selected_way + 1)

        return m


# Source-oriented alias retained for the Scala family name. / 保留源导向别名以对应 Scala family 名称。
Directory = CoupledL2Directory


# =============================================================================
# Public Adapter
# =============================================================================
# Convert the aggregate directory to deterministic SystemVerilog. / 将聚合目录转换为确定性 SystemVerilog。
def build_verilog(configuration, injected_dependencies):
    """Return Verilog for the CoupledL2 Directory family. / 返回 CoupledL2 Directory family Verilog。"""

    del injected_dependencies
    if isinstance(configuration, CoupledL2DirectoryConfig):
        cfg, name = configuration, "UHSCCoupledL2Directory"
    elif isinstance(configuration, dict):
        fields = CoupledL2DirectoryConfig.__dataclass_fields__
        values = {key: value for key, value in configuration.items() if key in fields}
        cfg = CoupledL2DirectoryConfig(**values)
        name = str(configuration.get("module", configuration.get("name", "UHSCCoupledL2Directory")))
    elif configuration is None:
        cfg, name = CoupledL2DirectoryConfig(), "UHSCCoupledL2Directory"
    else:
        raise TypeError("configuration must be CoupledL2DirectoryConfig, dict, or None")
    top = CoupledL2Directory(cfg)
    ports = [
        top.clock, top.reset, top.read_valid, top.read_ready, top.read_tag, top.read_set,
        top.read_way_mask, top.read_replacer_channel, top.read_replacer_opcode,
        top.read_replacer_req_source, top.read_replacer_refill_prefetch, top.read_refill,
        top.read_mshr_id, top.read_cmo_all, top.read_cmo_way, top.resp_valid, top.resp_hit,
        top.resp_tag, top.resp_set, top.resp_way, top.resp_meta_dirty, top.resp_meta_state,
        top.resp_meta_clients, top.resp_meta_alias, top.resp_meta_prefetch,
        top.resp_meta_prefetch_src, top.resp_meta_accessed, top.resp_meta_tag_err,
        top.resp_meta_data_err, top.resp_error, top.resp_replacer_channel,
        top.resp_replacer_opcode, top.resp_replacer_req_source, top.resp_replacer_refill_prefetch,
        top.meta_write_valid, top.meta_write_set, top.meta_write_way_oh, top.meta_write_dirty,
        top.meta_write_state, top.meta_write_clients, top.meta_write_alias,
        top.meta_write_prefetch, top.meta_write_prefetch_src, top.meta_write_accessed,
        top.meta_write_tag_err, top.meta_write_data_err, top.tag_write_valid,
        top.tag_write_set, top.tag_write_way, top.tag_write_tag, top.repl_resp_valid,
        top.repl_resp_tag, top.repl_resp_set, top.repl_resp_way, top.repl_resp_meta_dirty,
        top.repl_resp_meta_state, top.repl_resp_meta_clients, top.repl_resp_meta_alias,
        top.repl_resp_meta_prefetch, top.repl_resp_meta_prefetch_src, top.repl_resp_meta_accessed,
        top.repl_resp_meta_tag_err, top.repl_resp_meta_data_err, top.repl_resp_mshr_id,
        top.repl_resp_retry, top.repl_resp_error, top.mshr_valid, top.mshr_set, top.mshr_way,
        top.mshr_block_refill, top.mshr_dir_hit, top.mshr_will_free,
    ]
    return verilog.convert(top, name=name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print deterministic direct export for manual generation. / 打印确定性的 direct 导出以便手工生成。
def main() -> None:
    """Print the default directory RTL. / 打印默认目录 RTL。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
