"""UHSC V2 prefetch family aggregate.
昆明湖 V2 预取 family 聚合。

SMS, FDP, L1 framework, and filter members share a frozen explicit ANSI
catalog.  Bounded request routing is implemented where fields are available;
complete predictor training remains a parent differential obligation.
"""

from __future__ import annotations

from typing import Any, cast

from amaranth import Elaboratable, Module, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
__all__ = ["COVERED_MODULES", "IMPLEMENTED_MEMBERS", "CONTRACT_ONLY_MEMBERS", "PrefetchFamily", "build_verilog", "main"]
COVERED_MODULES = ("ActiveGenerationTable", "PrefetchFilter", "SMSTrainFilter", "StridePF", "MutiLevelPrefetchFilter", "TrainFilter", "TrainFilter_1", "BloomFilter", "CounterFilter")
IMPLEMENTED_MEMBERS: tuple[str, ...] = ()
CONTRACT_ONLY_MEMBERS = COVERED_MODULES
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
class PrefetchFamily(Elaboratable):
    """One exact prefetch member. / 一个精确预取成员。"""

    def __init__(self, member: str = "PrefetchFilter") -> None:
        """Declare frozen ports. / 声明冻结端口。"""

        if member not in PORT_SPECS: raise ValueError(member)
        self.member = member; self.specs = PORT_SPECS[member]; self.ports = {n: Signal(w, name=n) for n, _d, w in self.specs}

    def elaborate(self, platform: Any) -> Module:
        """Expose an ABI-only contract without guessed prefetch behavior. / 暴露不猜测预取行为的 ABI 合约。"""

        del platform
        module = Module()
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
