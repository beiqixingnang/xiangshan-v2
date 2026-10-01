"""UHSC V2 prefetch family aggregate.
昆明湖 V2 预取 family 聚合。

SMS, FDP, L1 framework, and filter members share a frozen explicit ANSI
catalog.  Bounded request routing is implemented where fields are available;
complete predictor training remains a parent differential obligation.
"""

from __future__ import annotations

from typing import Any, cast

from amaranth import Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
__all__ = ["COVERED_MODULES", "IMPLEMENTED_MEMBERS", "CONTRACT_ONLY_MEMBERS", "PrefetchFamily", "build_verilog", "main"]
COVERED_MODULES = ("ActiveGenerationTable", "PrefetchFilter", "SMSTrainFilter", "StridePF", "MutiLevelPrefetchFilter", "TrainFilter", "TrainFilter_1", "BloomFilter", "CounterFilter")
IMPLEMENTED_MEMBERS: tuple[str, ...] = (
    "BloomFilter",
    "CounterFilter",
    "SMSTrainFilter",
    "TrainFilter",
    "TrainFilter_1",
)
CONTRACT_ONLY_MEMBERS = tuple(member for member in COVERED_MODULES if member not in IMPLEMENTED_MEMBERS)
# CONTRACT_ONLY members remain explicit until locked differential evidence.

PortSpec = tuple[str, str, int]

PORT_SPECS: dict[str, tuple[PortSpec, ...]] = {
    'ActiveGenerationTable': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_agt_en', 'input', 1),
        ('io_s0_lookup_valid', 'input', 1),
        ('io_s0_lookup_bits_region_tag', 'input', 11),
        ('io_s0_lookup_bits_region_p1_tag', 'input', 11),
        ('io_s0_lookup_bits_region_m1_tag', 'input', 11),
        ('io_s0_lookup_bits_region_offset', 'input', 4),
        ('io_s0_lookup_bits_pht_index', 'input', 5),
        ('io_s0_lookup_bits_pht_tag', 'input', 13),
        ('io_s0_lookup_bits_allow_cross_region_p1', 'input', 1),
        ('io_s0_lookup_bits_allow_cross_region_m1', 'input', 1),
        ('io_s0_lookup_bits_region_paddr', 'input', 40),
        ('io_s0_lookup_bits_region_vaddr', 'input', 40),
        ('io_s0_dcache_evict_valid', 'input', 1),
        ('io_s0_dcache_evict_bits_vaddr', 'input', 50),
        ('io_s1_sel_stride', 'output', 1),
        ('io_s2_pht_lookup_valid', 'output', 1),
        ('io_s2_pht_lookup_bits_pht_index', 'output', 5),
        ('io_s2_pht_lookup_bits_pht_tag', 'output', 13),
        ('io_s2_pht_lookup_bits_region_paddr', 'output', 40),
        ('io_s2_pht_lookup_bits_region_vaddr', 'output', 40),
        ('io_s2_pht_lookup_bits_region_offset', 'output', 4),
        ('io_s2_evict_valid', 'output', 1),
        ('io_s2_evict_bits_pht_index', 'output', 5),
        ('io_s2_evict_bits_pht_tag', 'output', 13),
        ('io_s2_evict_bits_region_bits', 'output', 16),
        ('io_s2_evict_bits_region_bit_single', 'output', 16),
        ('io_s2_evict_bits_region_offset', 'output', 4),
        ('io_s2_evict_bits_access_cnt', 'output', 4),
        ('io_s2_evict_bits_decr_mode', 'output', 1),
        ('io_s2_evict_bits_single_update', 'output', 1),
        ('io_s2_evict_bits_has_been_signal_updated', 'output', 1),
        ('io_act_threshold', 'input', 4),
        ('io_act_stride', 'input', 6),
    ),
    'PrefetchFilter': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_gen_req_valid', 'input', 1),
        ('io_gen_req_bits_region_tag', 'input', 11),
        ('io_gen_req_bits_region_addr', 'input', 40),
        ('io_gen_req_bits_region_bits', 'input', 16),
        ('io_gen_req_bits_paddr_valid', 'input', 1),
        ('io_gen_req_bits_decr_mode', 'input', 1),
        ('io_tlb_req_req_valid', 'output', 1),
        ('io_tlb_req_req_bits_vaddr', 'output', 50),
        ('io_tlb_req_req_bits_fullva', 'output', 64),
        ('io_tlb_req_req_bits_checkfullva', 'output', 1),
        ('io_tlb_req_req_bits_cmd', 'output', 3),
        ('io_tlb_req_req_bits_hyperinst', 'output', 1),
        ('io_tlb_req_req_bits_hlvx', 'output', 1),
        ('io_tlb_req_req_bits_kill', 'output', 1),
        ('io_tlb_req_req_bits_isPrefetch', 'output', 1),
        ('io_tlb_req_req_bits_no_translate', 'output', 1),
        ('io_tlb_req_req_bits_pmp_addr', 'output', 48),
        ('io_tlb_req_req_bits_frm_mabuf', 'output', 1),
        ('io_tlb_req_req_bits_debug_robIdx_flag', 'output', 1),
        ('io_tlb_req_req_bits_debug_robIdx_value', 'output', 8),
        ('io_tlb_req_resp_valid', 'input', 1),
        ('io_tlb_req_resp_bits_paddr_0', 'input', 48),
        ('io_tlb_req_resp_bits_pbmt_0', 'input', 2),
        ('io_tlb_req_resp_bits_miss', 'input', 1),
        ('io_tlb_req_resp_bits_excp_0_gpf_ld', 'input', 1),
        ('io_tlb_req_resp_bits_excp_0_pf_ld', 'input', 1),
        ('io_tlb_req_resp_bits_excp_0_af_ld', 'input', 1),
        ('io_pmp_resp_ld', 'input', 1),
        ('io_pmp_resp_mmio', 'input', 1),
        ('io_l2_pf_addr_valid', 'output', 1),
        ('io_l2_pf_addr_bits', 'output', 48),
    ),
    'SMSTrainFilter': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_ld_in_0_valid', 'input', 1),
        ('io_ld_in_0_bits_uop_pc', 'input', 50),
        ('io_ld_in_0_bits_uop_robIdx_flag', 'input', 1),
        ('io_ld_in_0_bits_uop_robIdx_value', 'input', 8),
        ('io_ld_in_0_bits_vaddr', 'input', 50),
        ('io_ld_in_0_bits_paddr', 'input', 48),
        ('io_ld_in_1_valid', 'input', 1),
        ('io_ld_in_1_bits_uop_pc', 'input', 50),
        ('io_ld_in_1_bits_uop_robIdx_flag', 'input', 1),
        ('io_ld_in_1_bits_uop_robIdx_value', 'input', 8),
        ('io_ld_in_1_bits_vaddr', 'input', 50),
        ('io_ld_in_1_bits_paddr', 'input', 48),
        ('io_ld_in_2_valid', 'input', 1),
        ('io_ld_in_2_bits_uop_pc', 'input', 50),
        ('io_ld_in_2_bits_uop_robIdx_flag', 'input', 1),
        ('io_ld_in_2_bits_uop_robIdx_value', 'input', 8),
        ('io_ld_in_2_bits_vaddr', 'input', 50),
        ('io_ld_in_2_bits_paddr', 'input', 48),
        ('io_train_req_valid', 'output', 1),
        ('io_train_req_bits_vaddr', 'output', 50),
        ('io_train_req_bits_paddr', 'output', 48),
        ('io_train_req_bits_pc', 'output', 50),
    ),
    'StridePF': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_s0_lookup_valid', 'input', 1),
        ('io_s0_lookup_bits_pc', 'input', 10),
        ('io_s1_valid', 'input', 1),
    ),
    'MutiLevelPrefetchFilter': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_enable', 'input', 1),
        ('io_l1_prefetch_req_valid', 'input', 1),
        ('io_l1_prefetch_req_bits_region', 'input', 40),
        ('io_l1_prefetch_req_bits_bit_vec', 'input', 16),
        ('io_l1_prefetch_req_bits_source_value', 'input', 3),
        ('io_l2_l3_prefetch_req_valid', 'input', 1),
        ('io_l2_l3_prefetch_req_bits_region', 'input', 40),
        ('io_l2_l3_prefetch_req_bits_bit_vec', 'input', 16),
        ('io_l2_l3_prefetch_req_bits_sink', 'input', 2),
        ('io_l2_l3_prefetch_req_bits_source_value', 'input', 3),
        ('io_tlb_req_req_valid', 'output', 1),
        ('io_tlb_req_req_bits_vaddr', 'output', 50),
        ('io_tlb_req_req_bits_fullva', 'output', 64),
        ('io_tlb_req_req_bits_checkfullva', 'output', 1),
        ('io_tlb_req_req_bits_cmd', 'output', 3),
        ('io_tlb_req_req_bits_hyperinst', 'output', 1),
        ('io_tlb_req_req_bits_hlvx', 'output', 1),
        ('io_tlb_req_req_bits_kill', 'output', 1),
        ('io_tlb_req_req_bits_isPrefetch', 'output', 1),
        ('io_tlb_req_req_bits_no_translate', 'output', 1),
        ('io_tlb_req_req_bits_pmp_addr', 'output', 48),
        ('io_tlb_req_req_bits_frm_mabuf', 'output', 1),
        ('io_tlb_req_req_bits_debug_robIdx_flag', 'output', 1),
        ('io_tlb_req_req_bits_debug_robIdx_value', 'output', 8),
        ('io_tlb_req_resp_valid', 'input', 1),
        ('io_tlb_req_resp_bits_paddr_0', 'input', 48),
        ('io_tlb_req_resp_bits_pbmt_0', 'input', 2),
        ('io_tlb_req_resp_bits_miss', 'input', 1),
        ('io_tlb_req_resp_bits_excp_0_gpf_ld', 'input', 1),
        ('io_tlb_req_resp_bits_excp_0_pf_ld', 'input', 1),
        ('io_tlb_req_resp_bits_excp_0_af_ld', 'input', 1),
        ('io_pmp_resp_ld', 'input', 1),
        ('io_pmp_resp_mmio', 'input', 1),
        ('io_l1_req_ready', 'input', 1),
        ('io_l1_req_valid', 'output', 1),
        ('io_l1_req_bits_paddr', 'output', 48),
        ('io_l1_req_bits_alias', 'output', 2),
        ('io_l1_req_bits_confidence', 'output', 1),
        ('io_l1_req_bits_is_store', 'output', 1),
        ('io_l1_req_bits_pf_source_value', 'output', 3),
        ('io_l2_pf_addr_valid', 'output', 1),
        ('io_l2_pf_addr_bits_addr', 'output', 48),
        ('io_l2_pf_addr_bits_source', 'output', 5),
        ('io_l3_pf_addr_valid', 'output', 1),
        ('io_l3_pf_addr_bits', 'output', 48),
        ('io_confidence', 'input', 1),
    ),
    'TrainFilter': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_enable', 'input', 1),
        ('io_ld_in_0_valid', 'input', 1),
        ('io_ld_in_0_bits_uop_pc', 'input', 50),
        ('io_ld_in_0_bits_uop_robIdx_flag', 'input', 1),
        ('io_ld_in_0_bits_uop_robIdx_value', 'input', 8),
        ('io_ld_in_0_bits_vaddr', 'input', 50),
        ('io_ld_in_1_valid', 'input', 1),
        ('io_ld_in_1_bits_uop_pc', 'input', 50),
        ('io_ld_in_1_bits_uop_robIdx_flag', 'input', 1),
        ('io_ld_in_1_bits_uop_robIdx_value', 'input', 8),
        ('io_ld_in_1_bits_vaddr', 'input', 50),
        ('io_ld_in_2_valid', 'input', 1),
        ('io_ld_in_2_bits_uop_pc', 'input', 50),
        ('io_ld_in_2_bits_uop_robIdx_flag', 'input', 1),
        ('io_ld_in_2_bits_uop_robIdx_value', 'input', 8),
        ('io_ld_in_2_bits_vaddr', 'input', 50),
        ('io_train_req_ready', 'input', 1),
        ('io_train_req_valid', 'output', 1),
        ('io_train_req_bits_vaddr', 'output', 50),
        ('io_train_req_bits_pc', 'output', 50),
    ),
    'TrainFilter_1': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_enable', 'input', 1),
        ('io_ld_in_0_valid', 'input', 1),
        ('io_ld_in_0_bits_uop_robIdx_flag', 'input', 1),
        ('io_ld_in_0_bits_uop_robIdx_value', 'input', 8),
        ('io_ld_in_0_bits_vaddr', 'input', 50),
        ('io_ld_in_0_bits_miss', 'input', 1),
        ('io_ld_in_0_bits_meta_prefetch', 'input', 3),
        ('io_ld_in_1_valid', 'input', 1),
        ('io_ld_in_1_bits_uop_robIdx_flag', 'input', 1),
        ('io_ld_in_1_bits_uop_robIdx_value', 'input', 8),
        ('io_ld_in_1_bits_vaddr', 'input', 50),
        ('io_ld_in_1_bits_miss', 'input', 1),
        ('io_ld_in_1_bits_meta_prefetch', 'input', 3),
        ('io_ld_in_2_valid', 'input', 1),
        ('io_ld_in_2_bits_uop_robIdx_flag', 'input', 1),
        ('io_ld_in_2_bits_uop_robIdx_value', 'input', 8),
        ('io_ld_in_2_bits_vaddr', 'input', 50),
        ('io_ld_in_2_bits_miss', 'input', 1),
        ('io_ld_in_2_bits_meta_prefetch', 'input', 3),
        ('io_train_req_ready', 'input', 1),
        ('io_train_req_valid', 'output', 1),
        ('io_train_req_bits_vaddr', 'output', 50),
        ('io_train_req_bits_miss', 'output', 1),
        ('io_train_req_bits_pfHitStream', 'output', 1),
    ),
    'BloomFilter': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_set_valid', 'input', 1),
        ('io_set_bits_addr', 'input', 12),
        ('io_clr_valid', 'input', 1),
        ('io_clr_bits_addr', 'input', 12),
    ),
    'CounterFilter': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_ld_in_0_valid', 'input', 1),
        ('io_ld_in_0_bits_idx', 'input', 8),
        ('io_ld_in_0_bits_way', 'input', 2),
        ('io_ld_in_1_valid', 'input', 1),
        ('io_ld_in_1_bits_idx', 'input', 8),
        ('io_ld_in_1_bits_way', 'input', 2),
        ('io_ld_in_2_valid', 'input', 1),
        ('io_ld_in_2_bits_idx', 'input', 8),
        ('io_ld_in_2_bits_way', 'input', 2),
        ('io_query_0_req_valid', 'input', 1),
        ('io_query_0_req_bits_idx', 'input', 8),
        ('io_query_0_req_bits_way', 'input', 2),
        ('io_query_0_resp', 'output', 1),
        ('io_query_1_req_valid', 'input', 1),
        ('io_query_1_req_bits_idx', 'input', 8),
        ('io_query_1_req_bits_way', 'input', 2),
        ('io_query_1_resp', 'output', 1),
        ('io_query_2_req_valid', 'input', 1),
        ('io_query_2_req_bits_idx', 'input', 8),
        ('io_query_2_req_bits_way', 'input', 2),
        ('io_query_2_resp', 'output', 1),
    ),
}

# =============================================================================
# Implementation
# =============================================================================

def _log2_up(value: int) -> int:
    """Return the source parameter's ceiling log2. / 返回源参数的上取整 log2。"""

    return max(1, (value - 1).bit_length())


def _prefetch_domain(module: Module, ports: dict[str, Signal]) -> None:
    """Bind the external clock and asynchronous reset. / 绑定外部时钟与异步复位。"""

    domain = ClockDomain("prefetch", async_reset=True)
    domain.clk = ports["clock"]
    domain.rst = ports["reset"]
    module.domains += domain


def _or(values: list[Any]) -> Any:
    """OR a nonempty or empty expression list. / 对表达式列表执行或归约。"""

    result: Any = Const(0, 1)
    for value in values:
        result = result | value
    return result


def _sum_small(values: list[Any], width: int) -> Any:
    """Add a bounded set of one-bit terms. / 求和有界的一位项。"""

    result: Any = Const(0, width)
    for value in values:
        result = result + Mux(value, Const(1, width), Const(0, width))
    return result


def _select(values: list[Any], index: Any, width: int) -> Any:
    """Build a deterministic indexed mux with a zero default. / 生成零默认值的确定性索引多路器。"""

    result: Any = Const(0, width)
    for slot in reversed(range(len(values))):
        result = Mux(index == Const(slot, len(index)), values[slot], result)
    return result


def _ptr_ge(left_flag: Any, left_value: Any, right_flag: Any, right_value: Any) -> Any:
    """Compare circular queue pointers with their wrap flags. / 按回绕标志比较环形队列指针。"""

    return (left_flag ^ right_flag) ^ (left_value >= right_value)


def _ptr_add(flag: Any, value: Any, amount: Any, size: int) -> tuple[Any, Any]:
    """Advance a circular pointer for power-of-two and irregular sizes.

    处理二次幂与非二次幂队列大小的环形指针加法。
    """

    value_width = len(value)
    if size & (size - 1) == 0:
        advanced = Cat(value, flag) + amount
        return advanced[value_width], advanced[:value_width]
    extended_width = value_width + 2
    advanced = Cat(value, Const(0, 2)) + amount
    wraps = advanced >= Const(size, extended_width)
    reduced = Mux(wraps, advanced - Const(size, extended_width), advanced)
    return flag ^ wraps, reduced[:value_width]


def _bloom_filter(module: Module, ports: dict[str, Signal], bits: Signal) -> None:
    """Implement the 4096-bit set/clear bitmap with clear priority.

    实现 4096 位置位/清除位图，且同位同时操作时清除优先。
    """

    _prefetch_domain(module, ports)
    set_mask = Mux(
        ports["io_set_valid"],
        Const(1, 4096) << ports["io_set_bits_addr"],
        Const(0, 4096),
    )
    clear_mask = Mux(
        ports["io_clr_valid"],
        Const(1, 4096) << ports["io_clr_bits_addr"],
        Const(0, 4096),
    )
    module.d.prefetch += bits.eq((bits | set_mask) & ~clear_mask)


def _counter_filter(module: Module, ports: dict[str, Signal]) -> None:
    """Implement the 15-slot delayed-free set/way duplicate filter.

    实现 15 槽 set/way 重复查询过滤器以及三级分配延迟释放。
    """

    _prefetch_domain(module, ports)
    size = 15
    lanes = 3
    pointer_width = _log2_up(size)
    entries_idx = [Signal(8, name=f"counter_filter_idx_{slot}") for slot in range(size)]
    entries_way = [Signal(2, name=f"counter_filter_way_{slot}") for slot in range(size)]
    valid = [Signal(init=0, name=f"counter_filter_valid_{slot}") for slot in range(size)]
    enq_flag = [Signal(init=0, name=f"counter_filter_enq_flag_{lane}") for lane in range(lanes)]
    enq_value = [Signal(pointer_width, init=lane, name=f"counter_filter_enq_value_{lane}") for lane in range(lanes)]
    deq_flag = [Signal(init=0, name=f"counter_filter_deq_flag_{lane}") for lane in range(lanes)]
    deq_value = [Signal(pointer_width, init=lane, name=f"counter_filter_deq_value_{lane}") for lane in range(lanes)]
    delay0 = Signal(2, init=0, name="counter_filter_alloc_delay0")
    delay1 = Signal(2, init=0, name="counter_filter_alloc_delay1")
    delay2 = Signal(2, init=0, name="counter_filter_alloc_delay2")
    delayed_alloc = Signal(2, init=0, name="counter_filter_delayed_alloc")

    need_alloc = [ports[f"io_ld_in_{lane}_valid"] for lane in range(lanes)]
    allocate: list[Any] = []
    allocated_pointer: list[Any] = []
    for lane in range(lanes):
        index = _sum_small(need_alloc[:lane], 2)
        chosen_flag = _select(enq_flag, index, 1)
        chosen_value = _select(enq_value, index, pointer_width)
        can_allocate = need_alloc[lane] & _ptr_ge(chosen_flag, chosen_value, deq_flag[0], deq_value[0])
        allocate.append(can_allocate)
        allocated_pointer.append((chosen_flag, chosen_value))

    allocation_count = _sum_small(allocate, 2)
    any_allocate = _or(allocate)
    for lane in range(lanes):
        new_flag, new_value = _ptr_add(enq_flag[lane], enq_value[lane], allocation_count, size)
        module.d.prefetch += enq_flag[lane].eq(Mux(any_allocate, new_flag, enq_flag[lane]))
        module.d.prefetch += enq_value[lane].eq(Mux(any_allocate, new_value, enq_value[lane]))
        deq_new_flag, deq_new_value = _ptr_add(deq_flag[lane], deq_value[lane], delayed_alloc, size)
        module.d.prefetch += deq_flag[lane].eq(deq_new_flag)
        module.d.prefetch += deq_value[lane].eq(deq_new_value)

    for slot in range(size):
        next_valid: Any = valid[slot]
        next_idx: Any = entries_idx[slot]
        next_way: Any = entries_way[slot]
        for lane in range(lanes):
            ptr_flag, ptr_value = allocated_pointer[lane]
            allocate_here = allocate[lane] & (ptr_value == Const(slot, pointer_width))
            next_valid = Mux(allocate_here, Const(1, 1), next_valid)
            next_idx = Mux(allocate_here, ports[f"io_ld_in_{lane}_bits_idx"], next_idx)
            next_way = Mux(allocate_here, ports[f"io_ld_in_{lane}_bits_way"], next_way)
        for lane in range(lanes):
            retire_here = (Const(lane, 2) < delayed_alloc) & (deq_value[lane] == Const(slot, pointer_width))
            next_valid = Mux(retire_here, Const(0, 1), next_valid)
        module.d.prefetch += valid[slot].eq(next_valid)
        module.d.prefetch += entries_idx[slot].eq(next_idx)
        module.d.prefetch += entries_way[slot].eq(next_way)

    module.d.prefetch += delay0.eq(allocation_count)
    module.d.prefetch += delay1.eq(delay0)
    module.d.prefetch += delay2.eq(delay1)
    module.d.prefetch += delayed_alloc.eq(delay2)

    for lane in range(lanes):
        matches = [
            valid[slot]
            & (ports[f"io_query_{lane}_req_bits_idx"] == entries_idx[slot])
            & (ports[f"io_query_{lane}_req_bits_way"] == entries_way[slot])
            for slot in range(size)
        ]
        module.d.comb += ports[f"io_query_{lane}_resp"].eq(
            ports[f"io_query_{lane}_req_valid"] & _or(matches)
        )


def _block_hash(vaddr: Any) -> Any:
    """Return the frozen L1 prefetch block hash. / 返回锁定的 L1 预取块哈希。"""

    folded = vaddr[16:21] ^ vaddr[21:26] ^ vaddr[26:31]
    return Cat(vaddr[6:16], folded)


def _region_hash(region_addr: Any) -> Any:
    """Fold the three hashed groups of a region address. / 折叠 region 地址的三组哈希字段。"""

    folded = region_addr[10:15] ^ region_addr[15:20] ^ region_addr[20:25]
    return Cat(region_addr[0:6], folded)


def _plru_replace_way(state: Any, ways: int) -> Any:
    """Select the victim represented by a binary tree PLRU state.

    根据二叉树 PLRU 状态选择替换项。
    """

    if ways <= 1:
        return Const(0, 1)
    if ways == 2:
        return state[0]
    right_ways = 1 << (_log2_up(ways) - 1)
    left_ways = ways - right_ways
    left_older = state[ways - 2]
    left_state = state[right_ways - 1:ways - 2]
    right_state = state[0:right_ways - 1]
    if left_ways > 1:
        child = Mux(
            left_older,
            _plru_replace_way(left_state, left_ways),
            _plru_replace_way(right_state, right_ways),
        )
    else:
        child = Mux(left_older, Const(0, 1), _plru_replace_way(right_state, right_ways))
    return Cat(child, left_older)


def _plru_touch(state: Any, touch_way: Any, ways: int) -> Any:
    """Update the touched path in the binary tree PLRU state.

    更新二叉树 PLRU 中被访问的路径。
    """

    if ways <= 1:
        return Const(0, 1)
    if ways == 2:
        return ~touch_way[0]
    right_ways = 1 << (_log2_up(ways) - 1)
    left_ways = ways - right_ways
    touch_left = ~touch_way[_log2_up(ways) - 1]
    left_state = state[right_ways - 1:ways - 2]
    right_state = state[0:right_ways - 1]
    if left_ways > 1:
        left_next = Mux(
            touch_left,
            left_state,
            _plru_touch(left_state, touch_way[:_log2_up(left_ways)], left_ways),
        )
    else:
        left_next = Const(0, 1)
    right_next = Mux(
        touch_left,
        _plru_touch(right_state, touch_way[:_log2_up(right_ways)], right_ways),
        right_state,
    )
    return Cat(right_next, left_next, touch_left)


def _first_true_index(valids: list[Any], width: int) -> Any:
    """Select the lowest asserted lane, defaulting to the last lane. / 选择最低有效 lane，无效时默认末 lane。"""

    result: Any = Const(len(valids) - 1, width)
    for lane in reversed(range(len(valids))):
        result = Mux(valids[lane], Const(lane, width), result)
    return result


def _rr_index(valids: list[Any], last_grant: Any, width: int) -> Any:
    """Select the first valid lane after the previous grant, wrapping once.

    从前一次 grant 的下一个有效 lane 开始选择，并在末尾回绕。
    """

    after = [valids[lane] & (Const(lane, width) > last_grant) for lane in range(len(valids))]
    return Mux(_or(after), _first_true_index(after, width), _first_true_index(valids, width))


def _prefetch_filter(module: Module, ports: dict[str, Signal]) -> None:
    """Implement the SMS region filter, TLB rail, and pending-address rail.

    实现 SMS region filter、TLB 翻译轨和待发物理地址轨。
    """

    _prefetch_domain(module, ports)
    # Retained only as an historical local implementation while the active
    # source-backed function below owns this member.  Keep its intermediate
    # containers explicit so static analysis cannot treat dead legacy code as
    # an undeclared hardware dependency.
    s3_tlb_fire_mask = [Const(0, 1) for _ in range(16)]
    entry_widths = {"region_tag": 11, "region_addr": 40, "region_bits": 16,
                    "filter_bits": 16, "paddr_valid": 1, "decr_mode": 1,
                    "alias_bits": 2, "debug_source_type": 3}
    entries = {field: [Signal(width) for _ in range(16)]
               for field, width in entry_widths.items()}
    size = 16
    slot_width = 4
    entry_widths = {
        "region_tag": 11,
        "region_addr": 40,
        "region_bits": 16,
        "filter_bits": 16,
        "paddr_valid": 1,
        "decr_mode": 1,
        "alias_bits": 2,
        "debug_source_type": 3,
    }
    entries = {
        field: [Signal(width, name=f"sms_pf_{field}_{slot}") for slot in range(size)]
        for field, width in entry_widths.items()
    }
    valids = [Signal(init=0, name=f"sms_pf_valid_{slot}") for slot in range(size)]
    plru = Signal(size - 1, init=0, name="sms_pf_plru_state")
    tlb_last_grant = Signal(slot_width, init=0, name="sms_pf_tlb_last_grant")
    pf_last_grant = Signal(slot_width, init=0, name="sms_pf_addr_last_grant")

    gen_valid = ports["io_gen_req_valid"]
    gen_tag = ports["io_gen_req_bits_region_tag"]
    prev_gen_valid = Signal(init=0, name="sms_pf_prev_gen_valid")
    prev_gen_tag = Signal(11, init=0, name="sms_pf_prev_gen_tag")
    gen_valid_d = gen_valid & ~(prev_gen_valid & (gen_tag == prev_gen_tag))
    module.d.prefetch += prev_gen_valid.eq(gen_valid)
    module.d.prefetch += prev_gen_tag.eq(Mux(gen_valid, gen_tag, prev_gen_tag))

    replace_way = _plru_replace_way(plru, size)
    replace_mask = Const(1, size) << replace_way
    s1_valid = Signal(init=0, name="sms_pf_s1_valid")
    s1_hit = Signal(init=0, name="sms_pf_s1_hit")
    s1_replace_vec = Signal(size, init=0, name="sms_pf_s1_replace_vec")
    s1_update_vec = Signal(size, init=0, name="sms_pf_s1_update_vec")
    s1_gen = {
        "region_tag": Signal(11, init=0, name="sms_pf_s1_region_tag"),
        "region_addr": Signal(40, init=0, name="sms_pf_s1_region_addr"),
        "region_bits": Signal(16, init=0, name="sms_pf_s1_region_bits"),
        "paddr_valid": Signal(init=0, name="sms_pf_s1_paddr_valid"),
        "decr_mode": Signal(init=0, name="sms_pf_s1_decr_mode"),
    }
    s1_tlb_fire_mask = Signal(size, init=0, name="sms_pf_s1_tlb_fire_mask")
    s2_tlb_fire_mask = Signal(size, init=0, name="sms_pf_s2_tlb_fire_mask")
    s3_tlb_fire_mask = Signal(size, init=0, name="sms_pf_s3_tlb_fire_mask")
    no_tlb_inflight = [
        ~cast(Any, s1_tlb_fire_mask[i]) & ~cast(Any, s2_tlb_fire_mask[i]) & ~cast(Any, s3_tlb_fire_mask[i])
        for i in range(size)
    ]
    replacing = [s1_valid & ~s1_hit & s1_replace_vec[i] for i in range(size)]
    tlb_eligible = [
        valids[i] & no_tlb_inflight[i] & ~cast(Any, entries["paddr_valid"][i]) & ~cast(Any, replacing[i])
        for i in range(size)
    ]
    tlb_index = _rr_index(tlb_eligible, tlb_last_grant, slot_width)
    tlb_any = _or(tlb_eligible)
    tlb_fire_mask = [tlb_any & (tlb_index == Const(i, slot_width)) for i in range(size)]
    module.d.prefetch += s1_tlb_fire_mask.eq(Cat(*tlb_fire_mask))
    module.d.prefetch += s2_tlb_fire_mask.eq(s1_tlb_fire_mask)
    module.d.prefetch += s3_tlb_fire_mask.eq(s2_tlb_fire_mask)
    module.d.prefetch += tlb_last_grant.eq(Mux(tlb_any, tlb_index, tlb_last_grant))

    tlb_req_valid = Signal(init=0, name="sms_pf_tlb_req_valid")
    tlb_req_vaddr = Signal(50, init=0, name="sms_pf_tlb_req_vaddr")
    tlb_req_is_prefetch = Signal(init=0, name="sms_pf_tlb_req_is_prefetch")
    tlb_req_blocked_by_replace = cast(Any, _or([
        cast(Any, s1_tlb_fire_mask[i]) & cast(Any, s1_replace_vec[i]) for i in range(size)
    ])) & cast(Any, s1_valid) & ~cast(Any, s1_hit)
    module.d.comb += ports["io_tlb_req_req_valid"].eq(tlb_req_valid & ~tlb_req_blocked_by_replace)
    module.d.comb += ports["io_tlb_req_req_bits_vaddr"].eq(tlb_req_vaddr)
    module.d.comb += ports["io_tlb_req_req_bits_fullva"].eq(0)
    module.d.comb += ports["io_tlb_req_req_bits_checkfullva"].eq(0)
    module.d.comb += ports["io_tlb_req_req_bits_cmd"].eq(0)
    module.d.comb += ports["io_tlb_req_req_bits_hyperinst"].eq(0)
    module.d.comb += ports["io_tlb_req_req_bits_hlvx"].eq(0)
    module.d.comb += ports["io_tlb_req_req_bits_kill"].eq(0)
    module.d.comb += ports["io_tlb_req_req_bits_isPrefetch"].eq(tlb_req_is_prefetch)
    module.d.comb += ports["io_tlb_req_req_bits_no_translate"].eq(0)
    module.d.comb += ports["io_tlb_req_req_bits_pmp_addr"].eq(0)
    module.d.comb += ports["io_tlb_req_req_bits_frm_mabuf"].eq(0)
    module.d.comb += ports["io_tlb_req_req_bits_debug_robIdx_flag"].eq(0)
    module.d.comb += ports["io_tlb_req_req_bits_debug_robIdx_value"].eq(0)
    selected_tlb_vaddr = _select(
        [Cat(Const(0, 10), entries["region_addr"][i]) for i in range(size)],
        tlb_index,
        50,
    )
    module.d.prefetch += tlb_req_valid.eq(tlb_any)
    module.d.prefetch += tlb_req_vaddr.eq(Mux(tlb_any, selected_tlb_vaddr, tlb_req_vaddr))
    module.d.prefetch += tlb_req_is_prefetch.eq(tlb_any | tlb_req_is_prefetch)

    # Generate the first pending block from each translated region.
    pending = [entries["region_bits"][i] & ~entries["filter_bits"][i] for i in range(size)]
    pf_eligible = [valids[i] & (pending[i] != Const(0, 16)) & entries["paddr_valid"][i] & ~replacing[i] for i in range(size)]
    pf_index = _rr_index(pf_eligible, pf_last_grant, slot_width)
    pf_any = _or(pf_eligible)
    pf_first: list[Any] = []
    pf_last: list[Any] = []
    for entry_index in range(size):
        first: Any = Const(0, 4)
        last: Any = Const(0, 4)
        for bit_index in reversed(range(16)):
            first = Mux(pending[entry_index][bit_index], Const(bit_index, 4), first)
        for bit_index in range(16):
            last = Mux(pending[entry_index][bit_index], Const(bit_index, 4), last)
        pf_first.append(first)
        pf_last.append(last)
    selected_offset = Mux(
        _select(entries["decr_mode"], pf_index, 1),
        _select(pf_last, pf_index, 4),
        _select(pf_first, pf_index, 4),
    )
    selected_region_addr = _select(entries["region_addr"], pf_index, 40)
    selected_pf_addr = Cat(selected_region_addr[0:38], selected_offset, Const(0, 6))
    module.d.comb += ports["io_l2_pf_addr_valid"].eq(pf_any)
    module.d.comb += ports["io_l2_pf_addr_bits"].eq(selected_pf_addr)
    pf_fire_mask = [pf_any & (pf_index == Const(i, slot_width)) for i in range(size)]
    module.d.prefetch += pf_last_grant.eq(Mux(pf_any, pf_index, pf_last_grant))

    # Pipeline the allocated generation request, replacement, and update mask.
    prev_match = prev_gen_valid & (gen_tag == prev_gen_tag)
    s0_gen_req_valid = gen_valid_d
    s0_match = [
        valids[i] & (entries["region_tag"][i] == gen_tag) & ~replacing[i]
        for i in range(size)
    ]
    any_match = _or(s0_match)
    s0_hit = s0_gen_req_valid & any_match
    s0_replace_vec = replace_mask
    s0_access_way = Mux(s0_hit, _first_true_index(s0_match, slot_width), replace_way)
    touched_state = _plru_touch(plru, s0_access_way, size)
    module.d.prefetch += plru.eq(Mux(s0_gen_req_valid, touched_state, plru))
    module.d.prefetch += s1_valid.eq(s0_gen_req_valid)
    module.d.prefetch += s1_hit.eq(Mux(s0_gen_req_valid, s0_hit, s1_hit))
    module.d.prefetch += s1_replace_vec.eq(
        Mux(s0_gen_req_valid & ~s0_hit, s0_replace_vec, s1_replace_vec)
    )
    module.d.prefetch += s1_update_vec.eq(Mux(s0_gen_req_valid & s0_hit, Cat(*s0_match), s1_update_vec))
    for field in s1_gen:
        input_signal = ports[f"io_gen_req_bits_{field}"]
        module.d.prefetch += s1_gen[field].eq(Mux(s0_gen_req_valid, input_signal, s1_gen[field]))

    # Translate responses retire or update the entry that issued that request.
    response_fire = Signal(init=0, name="sms_pf_resp_fire")
    resp_paddr = Signal(48, init=0, name="sms_pf_resp_paddr")
    resp_pbmt = Signal(2, init=0, name="sms_pf_resp_pbmt")
    resp_miss = Signal(init=0, name="sms_pf_resp_miss")
    resp_gpf = Signal(init=0, name="sms_pf_resp_gpf")
    resp_pf = Signal(init=0, name="sms_pf_resp_pf")
    resp_af = Signal(init=0, name="sms_pf_resp_af")
    module.d.prefetch += response_fire.eq(ports["io_tlb_req_resp_valid"])
    for signal, port_name in (
        (resp_paddr, "io_tlb_req_resp_bits_paddr_0"),
        (resp_pbmt, "io_tlb_req_resp_bits_pbmt_0"),
        (resp_miss, "io_tlb_req_resp_bits_miss"),
        (resp_gpf, "io_tlb_req_resp_bits_excp_0_gpf_ld"),
        (resp_pf, "io_tlb_req_resp_bits_excp_0_pf_ld"),
        (resp_af, "io_tlb_req_resp_bits_excp_0_af_ld"),
    ):
        module.d.prefetch += signal.eq(Mux(ports["io_tlb_req_resp_valid"], ports[port_name], signal))
    response_updated = response_fire & ~resp_miss
    response_drop = response_updated & (
        resp_gpf
        | resp_pf
        | resp_af
        | ports["io_pmp_resp_mmio"]
        | ((resp_pbmt == Const(1, 2)) | (resp_pbmt == Const(2, 2)))
        | ports["io_pmp_resp_ld"]
    )

    for slot in range(size):
        next_valid: Any = valids[slot]
        next_fields: dict[str, Any] = {field: entries[field][slot] for field in entry_widths}
        tlb_fired = s3_tlb_fire_mask[slot] & response_updated
        next_valid = Mux(tlb_fired & response_drop, Const(0, 1), next_valid)
        physical_region_addr = Cat(resp_paddr[10:48], Const(0, 2))
        next_fields["paddr_valid"] = Mux(tlb_fired & ~response_drop, Const(1, 1), next_fields["paddr_valid"])
        next_fields["region_addr"] = Mux(tlb_fired & ~response_drop, physical_region_addr, next_fields["region_addr"])
        update_here = s1_valid & s1_hit & s1_update_vec[slot]
        next_fields["region_bits"] = Mux(update_here, next_fields["region_bits"] | s1_gen["region_bits"], next_fields["region_bits"])
        pf_fire = pf_fire_mask[slot]
        current_offset = selected_offset
        next_fields["filter_bits"] = Mux(
            pf_fire,
            next_fields["filter_bits"] | (Const(1, 16) << current_offset),
            next_fields["filter_bits"],
        )
        allocate_here = s1_valid & ~s1_hit & s1_replace_vec[slot]
        next_valid = Mux(allocate_here, Const(1, 1), next_valid)
        for field in ("region_tag", "region_addr", "region_bits", "paddr_valid", "decr_mode"):
            next_fields[field] = Mux(allocate_here, s1_gen[field], next_fields[field])
        next_fields["filter_bits"] = Mux(allocate_here, Const(0, 16), next_fields["filter_bits"])
        module.d.prefetch += valids[slot].eq(next_valid)
        for field, signal in entries.items():
            module.d.prefetch += signal[slot].eq(next_fields[field])


def _active_generation_table(module: Module, ports: dict[str, Signal]) -> None:
    """Implement the 16-entry active-generation table.

    实现 16 项 active-generation table、PHT 查询和 eviction 输出。
    """

    _prefetch_domain(module, ports)
    size = 16
    entry_widths = {
        "pht_index": 5,
        "pht_tag": 13,
        "region_bits": 16,
        "region_bit_single": 16,
        "region_tag": 11,
        "region_offset": 4,
        "access_cnt": 4,
        "decr_mode": 1,
        "has_been_signal_updated": 1,
    }
    entries = {
        field: [Signal(width, name=f"agt_{field}_{slot}") for slot in range(size)]
        for field, width in entry_widths.items()
    }
    valids = [Signal(init=0, name=f"agt_valid_{slot}") for slot in range(size)]
    plru = Signal(size - 1, init=0, name="agt_plru_state")

    lookup_valid = ports["io_s0_lookup_valid"]
    region_tag = ports["io_s0_lookup_bits_region_tag"]
    region_p1_tag = ports["io_s0_lookup_bits_region_p1_tag"]
    region_m1_tag = ports["io_s0_lookup_bits_region_m1_tag"]
    lookup_offset = ports["io_s0_lookup_bits_region_offset"]
    region_match = [valids[i] & (entries["region_tag"][i] == region_tag) for i in range(size)]
    region_p1_match = [valids[i] & (entries["region_tag"][i] == region_p1_tag) for i in range(size)]
    region_m1_match = [valids[i] & (entries["region_tag"][i] == region_m1_tag) for i in range(size)]
    any_region = _or(region_match)
    any_p1 = _or(region_p1_match) & ports["io_s0_lookup_bits_allow_cross_region_p1"]
    any_m1 = _or(region_m1_match) & ports["io_s0_lookup_bits_allow_cross_region_m1"]
    cross_region = any_p1 | any_m1

    dcache_vaddr = ports["io_s0_dcache_evict_bits_vaddr"]
    dcache_region_tag = Cat(
        dcache_vaddr[10:16],
        cast(Any, dcache_vaddr[16:21]) ^ cast(Any, dcache_vaddr[21:26]) ^ cast(Any, dcache_vaddr[26:31]),
    )
    dcache_match = [valids[i] & (entries["region_tag"][i] == dcache_region_tag) for i in range(size)]

    prev_valid = Signal(init=0, name="agt_prev_lookup_valid")
    prev_region_tag = Signal(11, init=0, name="agt_prev_lookup_region_tag")
    match_prev = prev_valid & (region_tag == prev_region_tag)
    replace_way = _plru_replace_way(plru, size)
    replace_mask = Const(1, size) << replace_way
    s1_alloc = Signal(init=0, name="agt_s1_alloc")
    s1_update = Signal(init=0, name="agt_s1_update")
    s1_dcache_evict = Signal(init=0, name="agt_s1_dcache_evict")
    s1_replace_mask_reg = Signal(size, init=0, name="agt_s1_replace_mask")
    s1_dcache_mask_reg = Signal(size, init=0, name="agt_s1_dcache_mask")
    s1_update_mask = Signal(size, init=0, name="agt_s1_update_mask")
    s1_pf_match_mask = Signal(size, init=0, name="agt_s1_pf_match_mask")
    s1_cross_region = Signal(init=0, name="agt_s1_cross_region")
    s1_entry = {
        field: Signal(width, init=0, name=f"agt_s1_{field}")
        for field, width in entry_widths.items()
    }
    s1_region_paddr = Signal(40, init=0, name="agt_s1_region_paddr")
    s1_region_vaddr = Signal(40, init=0, name="agt_s1_region_vaddr")
    s1_region_offset = Signal(4, init=0, name="agt_s1_pf_region_offset")

    pending_replace_mask = Mux(s1_dcache_evict, s1_dcache_mask_reg, s1_replace_mask_reg)
    pending_replace_active = s1_alloc | s1_dcache_evict
    s0_update_conflict = _or([
        region_match[i] & pending_replace_mask[i] & pending_replace_active
        for i in range(size)
    ])
    s0_update = lookup_valid & any_region & ~s0_update_conflict
    s0_alloc = lookup_valid & ~any_region & ~match_prev
    s0_dcache_conflict = _or([
        dcache_match[i] & pending_replace_mask[i] & pending_replace_active
        for i in range(size)
    ])
    dcache_ready = ~lookup_valid & ~s0_dcache_conflict
    dcache_fire = ports["io_s0_dcache_evict_valid"] & dcache_ready
    s0_dcache_evict = dcache_fire & _or(dcache_match)

    pf_match = [
        Mux(any_region, region_match[i], Mux(any_m1, region_m1_match[i], region_p1_match[i]))
        for i in range(size)
    ]
    region_onehot = Const(1, 16) << lookup_offset
    s0_entry = {
        "pht_index": ports["io_s0_lookup_bits_pht_index"],
        "pht_tag": ports["io_s0_lookup_bits_pht_tag"],
        "region_bits": region_onehot,
        "region_bit_single": region_onehot,
        "region_tag": region_tag,
        "region_offset": lookup_offset,
        "access_cnt": Const(1, 4),
        "decr_mode": ~any_region & ~any_m1 & any_p1,
        "has_been_signal_updated": Const(0, 1),
    }
    matched_way: Any = Const(0, 4)
    for i in reversed(range(size)):
        matched_way = Mux(region_match[i], Const(i, 4), matched_way)
    access_way = Mux(s0_update, matched_way, replace_way)
    touched_plru = _plru_touch(plru, access_way, size)
    module.d.prefetch += plru.eq(Mux(s0_update | s0_alloc, touched_plru, plru))

    # Register the lookup request and its association masks.
    module.d.prefetch += prev_valid.eq(lookup_valid)
    module.d.prefetch += prev_region_tag.eq(Mux(lookup_valid, region_tag, prev_region_tag))
    module.d.prefetch += s1_alloc.eq(s0_alloc)
    module.d.prefetch += s1_update.eq(s0_update)
    module.d.prefetch += s1_dcache_evict.eq(s0_dcache_evict)
    module.d.prefetch += s1_replace_mask_reg.eq(Mux(lookup_valid, replace_mask, s1_replace_mask_reg))
    module.d.prefetch += s1_dcache_mask_reg.eq(Mux(s0_dcache_evict, Cat(*dcache_match), s1_dcache_mask_reg))
    module.d.prefetch += s1_update_mask.eq(Mux(lookup_valid, Cat(*region_match), s1_update_mask))
    module.d.prefetch += s1_pf_match_mask.eq(Mux(lookup_valid, Cat(*pf_match), s1_pf_match_mask))
    module.d.prefetch += s1_cross_region.eq(Mux(lookup_valid, cross_region, s1_cross_region))
    for field, signal in s1_entry.items():
        module.d.prefetch += signal.eq(Mux(lookup_valid, s0_entry[field], signal))
    for input_name, signal, width in (
        ("region_paddr", s1_region_paddr, 40),
        ("region_vaddr", s1_region_vaddr, 40),
        ("region_offset", s1_region_offset, 4),
    ):
        del width
        module.d.prefetch += signal.eq(
            Mux(lookup_valid, ports[f"io_s0_lookup_bits_{input_name}"], signal)
        )

    active_replace = s1_alloc | s1_dcache_evict
    s1_replace_mask = pending_replace_mask & Mux(active_replace, Const((1 << size) - 1, size), Const(0, size))
    evict_valid = _or([s1_replace_mask[i] & valids[i] for i in range(size)])
    evict_entry: dict[str, Any] = {}
    update_entry: dict[str, Any] = {}
    for field, slots in entries.items():
        width = entry_widths[field]
        evicted: Any = Const(0, width)
        updated: Any = Const(0, width)
        for i in range(size):
            evicted = evicted | Mux(s1_replace_mask[i], slots[i], Const(0, width))
            updated = updated | Mux(s1_update_mask[i], slots[i], Const(0, width))
        evict_entry[field] = evicted
        update_entry[field] = updated

    for i in range(size):
        allocate_here = s1_alloc & s1_replace_mask[i]
        update_here = s1_update & s1_update_mask[i]
        added_bits = s1_entry["region_bits"] & ~entries["region_bits"][i]
        add_new_access = _or([added_bits[bit] for bit in range(16)])
        next_entry: dict[str, Any] = {}
        for field, slots in entries.items():
            current = slots[i]
            if field == "region_bits":
                current = Mux(update_here, current | s1_entry[field], current)
            elif field == "region_bit_single":
                current = Mux(update_here, s1_entry[field], current)
            elif field == "access_cnt":
                incremented = Mux(
                    current == Const(15, 4),
                    current,
                    current + Mux(add_new_access, Const(1, 4), Const(0, 4)),
                )
                current = Mux(update_here, incremented, current)
            elif field == "has_been_signal_updated":
                current = Mux(
                    update_here,
                    current | (~(active_replace & evict_valid)),
                    current,
                )
            current = Mux(allocate_here, s1_entry[field], current)
            next_entry[field] = current
        for field, slots in entries.items():
            module.d.prefetch += slots[i].eq(next_entry[field])
        module.d.prefetch += valids[i].eq(valids[i] | allocate_here)

    # PHT lookup is a two-stage, stride-suppressible output. / PHT 查询经过两级流水且可被 stride hit 抑制。
    selected_access_cnt: Any = Const(0, 4)
    update_decr_mode: Any = Const(0, 1)
    for i in range(size):
        selected_access_cnt = selected_access_cnt | Mux(
            s1_pf_match_mask[i], entries["access_cnt"][i], Const(0, 4)
        )
        update_decr_mode = update_decr_mode | Mux(
            s1_update_mask[i], entries["decr_mode"][i], Const(0, 1)
        )
    active_page = selected_access_cnt > ports["io_act_threshold"]
    s1_decr_mode = Mux(s1_update, update_decr_mode, s1_entry["decr_mode"])
    pfgen_transaction = (s1_alloc & s1_cross_region) | s1_update
    region_window = Cat(s1_region_offset, s1_region_vaddr[0:11], Const(0, 1))
    incremented = region_window + ports["io_act_stride"]
    decremented = region_window - ports["io_act_stride"]
    crosses_address_limit = Mux(s1_decr_mode, decremented[15], incremented[15])
    pfgen_valid = (
        prev_valid
        & pfgen_transaction
        & ~crosses_address_limit
        & active_page
        & ports["io_agt_en"]
    )
    pht_lookup_valid = prev_valid & ~pfgen_valid
    module.d.comb += ports["io_s1_sel_stride"].eq(
        prev_valid & pfgen_transaction & ~active_page
    )

    pht_valid_reg = Signal(init=0, name="agt_pht_valid_reg")
    pht_index_reg = Signal(5, init=0, name="agt_pht_index_reg")
    pht_tag_reg = Signal(13, init=0, name="agt_pht_tag_reg")
    pht_paddr_reg = Signal(40, init=0, name="agt_pht_paddr_reg")
    pht_vaddr_reg = Signal(40, init=0, name="agt_pht_vaddr_reg")
    pht_offset_reg = Signal(4, init=0, name="agt_pht_offset_reg")
    module.d.prefetch += pht_valid_reg.eq(pht_lookup_valid)
    module.d.prefetch += pht_index_reg.eq(Mux(pht_lookup_valid, s1_entry["pht_index"], pht_index_reg))
    module.d.prefetch += pht_tag_reg.eq(Mux(pht_lookup_valid, s1_entry["pht_tag"], pht_tag_reg))
    module.d.prefetch += pht_paddr_reg.eq(Mux(pht_lookup_valid, s1_region_paddr, pht_paddr_reg))
    module.d.prefetch += pht_vaddr_reg.eq(Mux(pht_lookup_valid, s1_region_vaddr, pht_vaddr_reg))
    module.d.prefetch += pht_offset_reg.eq(Mux(pht_lookup_valid, s1_region_offset, pht_offset_reg))
    stride_hit = ports.get("io_s2_stride_hit", Const(0, 1))
    module.d.comb += ports["io_s2_pht_lookup_valid"].eq(pht_valid_reg & ~stride_hit)
    module.d.comb += ports["io_s2_pht_lookup_bits_pht_index"].eq(pht_index_reg)
    module.d.comb += ports["io_s2_pht_lookup_bits_pht_tag"].eq(pht_tag_reg)
    module.d.comb += ports["io_s2_pht_lookup_bits_region_paddr"].eq(pht_paddr_reg)
    module.d.comb += ports["io_s2_pht_lookup_bits_region_vaddr"].eq(pht_vaddr_reg)
    module.d.comb += ports["io_s2_pht_lookup_bits_region_offset"].eq(pht_offset_reg)

    # Eviction/update is registered one stage after the table write. / 驱逐与更新在表写入后再流水一级。
    replace_fire = active_replace & evict_valid
    evict_trigger = replace_fire | s1_update
    s2_evict_valid = Signal(init=0, name="agt_s2_evict_valid")
    s2_update = Signal(init=0, name="agt_s2_update")
    s2_real_update = Signal(init=0, name="agt_s2_real_update")
    s2_entry = {
        field: Signal(width, init=0, name=f"agt_s2_{field}")
        for field, width in entry_widths.items()
    }
    for field, signal in s2_entry.items():
        send_value = Mux(replace_fire, evict_entry[field], update_entry[field])
        module.d.prefetch += signal.eq(Mux(evict_trigger, send_value, signal))
    module.d.prefetch += s2_evict_valid.eq(evict_trigger)
    module.d.prefetch += s2_update.eq(s1_update)
    module.d.prefetch += s2_real_update.eq(replace_fire)
    module.d.comb += ports["io_s2_evict_valid"].eq(
        Mux(s2_real_update, s2_evict_valid & (s2_entry["access_cnt"] > Const(1, 4)), s2_evict_valid)
    )
    for field, signal in s2_entry.items():
        output_name = f"io_s2_evict_bits_{field}"
        if output_name in ports:
            module.d.comb += ports[output_name].eq(signal)
    module.d.comb += ports["io_s2_evict_bits_single_update"].eq(s2_update & ~s2_real_update)


def _rob_before(left_flag: Any, left_value: Any, right_flag: Any, right_value: Any) -> Any:
    """Compare wrapped reorder-buffer indices. / 比较带回绕位的 ROB 索引。"""

    return (left_flag ^ right_flag) ^ (left_value < right_value)


def _train_input_rows(
    module: Module,
    ports: dict[str, Signal],
    has_pc: bool,
    has_paddr: bool,
    has_miss: bool,
    has_meta: bool,
) -> list[dict[str, Any]]:
    """Build the three-stage ROB-ordered input network from source fields.

    根据源字段构造三级 ROB 顺序排序网络。
    """

    fields: dict[str, int] = {
        "rob_flag": 1,
        "rob_value": 8,
        "vaddr": 50,
    }
    if has_pc:
        fields["pc"] = 50
    if has_paddr:
        fields["paddr"] = 48
    if has_miss:
        fields["miss"] = 1
    if has_meta:
        fields["meta"] = 3

    input_rows: list[dict[str, Any]] = []
    for lane in range(3):
        prefix = f"io_ld_in_{lane}_bits_"
        row: dict[str, Any] = {
            "valid": ports[f"io_ld_in_{lane}_valid"],
            "rob_flag": ports[prefix + "uop_robIdx_flag"],
            "rob_value": ports[prefix + "uop_robIdx_value"],
            "vaddr": ports[prefix + "vaddr"],
        }
        if has_pc:
            row["pc"] = ports[prefix + "uop_pc"]
        if has_paddr:
            row["paddr"] = ports[prefix + "paddr"]
        if has_miss:
            row["miss"] = ports[prefix + "miss"]
        if has_meta:
            row["meta"] = ports[prefix + "meta_prefetch"]
        input_rows.append(row)

    def ordered_pair(left: dict[str, Any], right: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        swap = (
            left["valid"]
            & right["valid"]
            & _rob_before(right["rob_flag"], right["rob_value"], left["rob_flag"], left["rob_value"])
        )
        first: dict[str, Any] = {"valid": Mux(swap, right["valid"], left["valid"])}
        second: dict[str, Any] = {"valid": Mux(swap, left["valid"], right["valid"])}
        for field in fields:
            first[field] = Mux(swap, right[field], left[field])
            second[field] = Mux(swap, left[field], right[field])
        return first, second

    def register_row(row: dict[str, Any], stage: int, slot: int) -> dict[str, Signal]:
        stored: dict[str, Signal] = {}
        stored["valid"] = Signal(init=0, name=f"train_reorder_{stage}_{slot}_valid")
        for field, width in fields.items():
            stored[field] = Signal(width, init=0, name=f"train_reorder_{stage}_{slot}_{field}")
        for field, signal in stored.items():
            module.d.prefetch += signal.eq(row[field])
        return stored

    row01_0, row01_1 = ordered_pair(input_rows[0], input_rows[1])
    stage1 = [
        register_row(row01_0, 0, 0),
        register_row(row01_1, 0, 1),
        register_row(input_rows[2], 0, 2),
    ]
    row12_1, row12_2 = ordered_pair(stage1[1], stage1[2])
    stage2 = [
        register_row(stage1[0], 1, 0),
        register_row(row12_1, 1, 1),
        register_row(row12_2, 1, 2),
    ]
    row01_final_0, row01_final_1 = ordered_pair(stage2[0], stage2[1])
    stage3 = [
        register_row(row01_final_0, 2, 0),
        register_row(row01_final_1, 2, 1),
        register_row(stage2[2], 2, 2),
    ]
    return stage3


def _train_queue(
    module: Module,
    ports: dict[str, Signal],
    member: str,
    size: int,
    *,
    is_sms: bool,
    has_pc: bool,
    has_paddr: bool,
    has_miss: bool,
    has_meta: bool,
) -> None:
    """Implement one ROB-ordered, duplicate-suppressing train FIFO.

    实现 ROB 排序、块地址去重的预取训练 FIFO。
    """

    _prefetch_domain(module, ports)
    rows = _train_input_rows(module, ports, has_pc, has_paddr, has_miss, has_meta)
    pointer_width = _log2_up(size)
    lane_count = 3
    enq_flag = [Signal(init=0, name=f"{member}_enq_flag_{lane}") for lane in range(lane_count)]
    enq_value = [Signal(pointer_width, init=lane, name=f"{member}_enq_value_{lane}") for lane in range(lane_count)]
    deq_flag = Signal(init=0, name=f"{member}_deq_flag")
    deq_value = Signal(pointer_width, init=0, name=f"{member}_deq_value")
    valid = [Signal(init=0, name=f"{member}_valid_{slot}") for slot in range(size)]
    field_widths: dict[str, int] = {"vaddr": 50}
    if has_pc:
        field_widths["pc"] = 50
    if has_paddr:
        field_widths["paddr"] = 48
    if has_miss:
        field_widths["miss"] = 1
    if has_meta:
        field_widths["pf_hit_stream"] = 1
    entry_fields = {
        field: [Signal(width, name=f"{member}_{field}_{slot}") for slot in range(size)]
        for field, width in field_widths.items()
    }

    need_alloc: list[Any] = []
    can_alloc: list[Any] = []
    alloc_ptr_value: list[Any] = []
    for lane in range(lane_count):
        row = rows[lane]
        duplicate_slots = [
            valid[slot] & (_block_hash(entry_fields["vaddr"][slot]) == _block_hash(row["vaddr"]))
            for slot in range(size)
        ]
        duplicate_earlier = [
            rows[prior]["valid"] & (_block_hash(rows[prior]["vaddr"]) == _block_hash(row["vaddr"]))
            for prior in range(lane)
        ]
        needed = row["valid"] & ~_or(duplicate_slots) & ~_or(duplicate_earlier)
        need_alloc.append(needed)
        index = _sum_small(need_alloc[:lane], 2)
        ptr_flag = _select(enq_flag, index, 1)
        ptr_value = _select(enq_value, index, pointer_width)
        alloc_ptr_value.append(ptr_value)
        enabled = Const(1, 1) if is_sms else ports["io_enable"]
        can_alloc.append(needed & _ptr_ge(ptr_flag, ptr_value, deq_flag, deq_value) & enabled)

    allocation_count = _sum_small(can_alloc, 2)
    allocate_any = _or(can_alloc)
    next_enq_ptrs = [
        _ptr_add(enq_flag[lane], enq_value[lane], allocation_count, size)
        for lane in range(lane_count)
    ]
    deq_enable = _or([valid[slot] & (deq_value == Const(slot, pointer_width)) for slot in range(size)])
    if is_sms:
        deq_fire = deq_enable
    else:
        deq_fire = deq_enable & ports["io_train_req_ready"] & ports["io_enable"]

    output_valid = deq_enable if is_sms else deq_enable & ports["io_enable"]
    module.d.comb += ports["io_train_req_valid"].eq(output_valid)
    output_field_map = {
        "vaddr": "io_train_req_bits_vaddr",
        "pc": "io_train_req_bits_pc",
        "paddr": "io_train_req_bits_paddr",
        "miss": "io_train_req_bits_miss",
        "pf_hit_stream": "io_train_req_bits_pfHitStream",
    }
    for field, output_name in output_field_map.items():
        if output_name in ports:
            module.d.comb += ports[output_name].eq(_select(entry_fields[field], deq_value, field_widths[field]))

    flush_delay = None
    if not is_sms:
        flush_delay = Signal(init=0, name=f"{member}_flush_delay")
        flush_input = ports.get("io_flush", Const(0, 1))
        module.d.prefetch += flush_delay.eq(flush_input)

    for lane in range(lane_count):
        new_flag, new_value = next_enq_ptrs[lane]
        ptr_flag_next: Any = Mux(allocate_any, new_flag, enq_flag[lane])
        ptr_value_next: Any = Mux(allocate_any, new_value, enq_value[lane])
        if flush_delay is not None:
            ptr_flag_next = Mux(flush_delay, Const(0, 1), ptr_flag_next)
            ptr_value_next = Mux(flush_delay, Const(lane, pointer_width), ptr_value_next)
        module.d.prefetch += enq_flag[lane].eq(ptr_flag_next)
        module.d.prefetch += enq_value[lane].eq(ptr_value_next)

    next_deq_flag, next_deq_value = _ptr_add(deq_flag, deq_value, Const(1, 1), size)
    deq_flag_next: Any = Mux(deq_fire, next_deq_flag, deq_flag)
    deq_value_next: Any = Mux(deq_fire, next_deq_value, deq_value)
    if flush_delay is not None:
        deq_flag_next = Mux(flush_delay, Const(0, 1), deq_flag_next)
        deq_value_next = Mux(flush_delay, Const(0, pointer_width), deq_value_next)
    module.d.prefetch += deq_flag.eq(deq_flag_next)
    module.d.prefetch += deq_value.eq(deq_value_next)

    for slot in range(size):
        next_valid: Any = valid[slot]
        next_fields: dict[str, Any] = {field: entry_fields[field][slot] for field in entry_fields}
        for lane, row in enumerate(rows):
            allocate_here = can_alloc[lane] & (alloc_ptr_value[lane] == Const(slot, pointer_width))
            next_valid = Mux(allocate_here, Const(1, 1), next_valid)
            for field in field_widths:
                if field == "pf_hit_stream":
                    new_field = row["meta"] == Const(3, 3)
                else:
                    new_field = row[field]
                next_fields[field] = Mux(allocate_here, new_field, next_fields[field])
        retire_here = deq_fire & (deq_value == Const(slot, pointer_width))
        next_valid = Mux(retire_here, Const(0, 1), next_valid)
        if flush_delay is not None:
            next_valid = Mux(flush_delay, Const(0, 1), next_valid)
        module.d.prefetch += valid[slot].eq(next_valid)
        for field in field_widths:
            module.d.prefetch += entry_fields[field][slot].eq(next_fields[field])


def _implemented_prefetch_member(
    module: Module,
    member: str,
    ports: dict[str, Signal],
    private_state: dict[str, Signal],
) -> bool:
    """Elaborate a member with closed observable leaf behavior.

    展开已闭合可观测行为的成员。
    """

    if member == "ActiveGenerationTable":
        _active_generation_table(module, ports)
        return True
    if member == "PrefetchFilter":
        _prefetch_filter(module, ports)
        return True
    if member == "BloomFilter":
        _bloom_filter(module, ports, private_state["bloom_bits"])
        return True
    if member == "CounterFilter":
        _counter_filter(module, ports)
        return True
    if member == "SMSTrainFilter":
        _train_queue(module, ports, member, 8, is_sms=True, has_pc=True, has_paddr=True, has_miss=False, has_meta=False)
        return True
    if member == "TrainFilter":
        _train_queue(module, ports, member, 6, is_sms=False, has_pc=True, has_paddr=False, has_miss=False, has_meta=False)
        return True
    if member == "TrainFilter_1":
        _train_queue(module, ports, member, 4, is_sms=False, has_pc=False, has_paddr=False, has_miss=True, has_meta=True)
        return True
    return False


class PrefetchFamily(Elaboratable):
    """One exact prefetch member. / 一个精确预取成员。"""

    def __init__(self, member: str = "PrefetchFilter") -> None:
        """Declare frozen ports. / 声明冻结端口。"""

        if member not in PORT_SPECS: raise ValueError(member)
        self.member = member
        self.specs = PORT_SPECS[member]
        self.ports = {n: Signal(w, name=n) for n, _d, w in self.specs}
        self._private_state: dict[str, Signal] = {}
        if member == "BloomFilter":
            self._private_state["bloom_bits"] = Signal(4096, init=0, name="bloom_filter_bits")

    def elaborate(self, platform: Any) -> Module:
        """Expose an ABI-only contract without guessed prefetch behavior. / 暴露不猜测预取行为的 ABI 合约。"""

        del platform
        module = Module()
        implemented = _implemented_prefetch_member(module, self.member, self.ports, self._private_state)
        if not implemented:
            for name, direction, _w in self.specs:
                if direction == "output":
                    module.d.comb += self.ports[name].eq(0)
        return module


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration: Any, injected_dependencies: Any) -> str:
    """Export one deterministic same-name prefetch member. / 导出确定性的同名预取成员。"""

    del injected_dependencies; member = "PrefetchFilter"
    if isinstance(configuration, dict): member = str(configuration.get("module", member))
    elif isinstance(configuration, str): member = configuration
    top = PrefetchFamily(member); return verilog.convert(top, name=member, ports=[top.ports[n] for n, _d, _w in top.specs], emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    """Print default prefetch RTL. / 打印默认预取 RTL。"""

    print(build_verilog({"module": "PrefetchFilter"}, {}))


if __name__ == "__main__": main()
