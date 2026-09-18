"""UHSC V2 uncache load-queue, TLB storage and vector-split memory family.
UHSC V2 非缓存加载队列、TLB 存储与向量分裂访存 family。

The selected Kunminghu V2 closure links 42 locked modules to the memory-side
families ``xiangshan/mem/lsqueue/LoadQueueUncache.scala`` (the parent plus its
16 ``UncacheEntry`` registers), ``xiangshan/mem/lsqueue/FreeList.scala`` (the
six circular free-list allocators), ``xiangshan/cache/mmu/TLBStorage.scala``
(the four 64-way ``TLBFA`` storages and four ``TlbStorageWrapper`` wrappers),
``xiangshan/mem/vector/VSplit.scala`` (the vector store/load split pipeline,
buffer and imp leaves) and the ``Repeater`` leaves of
``util/Repeater.scala`` / ``xiangshan/cache/mmu/Repeater.scala``.  One faithful
generator keeps the family in a single Build subject: queue depth (16 uncache
entries), allocator ordering (per-instance ``preAlloc``/``freeWidth``), TLB
bank geometry (64 ways, sector tags, level-matched lookup masking,
sfence/hfence invalidation) and split beat counting follow the pinned
artifact.  Catalog rows are machine-derived from
``validation/v2-locked-hierarchy.json`` and reproduce the exact ANSI port
surface of the pinned ``XSTop.sv``.

选定的 Kunminghu V2 闭包把 42 个锁定模块链接到访存侧 family：
``xiangshan/mem/lsqueue/LoadQueueUncache.scala``（父模块及 16 个
``UncacheEntry`` 表项寄存器）、``xiangshan/mem/lsqueue/FreeList.scala``（六个
环形空闲表分配器）、``xiangshan/cache/mmu/TLBStorage.scala``（四个 64 路
``TLBFA`` 存储与四个 ``TlbStorageWrapper`` 包装）、``xiangshan/mem/vector/VSplit.scala``
（向量存/取分裂流水线、缓冲与 Imp 叶子）以及
``util/Repeater.scala`` / ``xiangshan/cache/mmu/Repeater.scala`` 的 ``Repeater``
叶子。单一忠实生成器把整个 family 作为一个 Build 主题：队列深度（16 个非缓存
表项）、分配器顺序（逐实例 ``preAlloc``/``freeWidth``）、TLB 组几何（64 路、
sector tag、按 level 匹配的查找掩码、sfence/hfence 失效）与分裂 beat 计数均
遵循钉死产物。catalog 行由 ``validation/v2-locked-hierarchy.json`` 机器推导，
复现钉死 ``XSTop.sv`` 的精确 ANSI 端口面。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from amaranth import Array, Cat, ClockDomain, Const, Elaboratable, Mux, Module, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# Source families of this memory-side aggregate subject. / 本访存侧聚合主题的来源 family。
FAMILY_SOURCE_PATHS: tuple[str, ...] = (
    "src/main/scala/xiangshan/mem/lsqueue/LoadQueueUncache.scala",
    "src/main/scala/xiangshan/mem/lsqueue/FreeList.scala",
    "src/main/scala/xiangshan/cache/mmu/TLBStorage.scala",
    "src/main/scala/xiangshan/cache/mmu/MMUBundle.scala",
    "src/main/scala/xiangshan/mem/vector/VSplit.scala",
    "src/main/scala/xiangshan/cache/mmu/Repeater.scala",
    "rocket-chip/src/main/scala/util/Repeater.scala",
    "utility/src/main/scala/utility/CircularQueuePtr.scala",
    "utility/src/main/scala/utility/Sort.scala",
    "utility/src/main/scala/utility/ClockGatedReg.scala",
)

__all__ = [
    "FAMILY_SOURCE_PATHS",
    "CATALOG_ROWS",
    "FamilySpec",
    "catalog_specs",
    "family_spec",
    "LsqUncacheFreeList",
    "UncacheEntryModel",
    "RepeaterModel",
    "PtwRepeaterNbModel",
    "TlbFaModel",
    "TlbStorageWrapperModel",
    "VSplitPipelineModel",
    "VSplitBufferModel",
    "VSplitImpModel",
    "LsqUncacheBuffer",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
# Every covered locked module, one machine-derived catalog row each.
# 每个被覆盖的锁定模块一行机器推导的 catalog。
# Row: name|family|params|ports with ports ``name:direction:bits`` joined by ``;``.
CATALOG_ROWS: tuple[str, ...] = (
    "LoadQueueUncache|lquncache|entries=16|clock:i:1;reset:i:1;io_redirect_valid:i:1;io_redirect_bits_robIdx_flag:i:1;io_redirect_bits_robIdx_value:i:8;io_redirect_bits_level:i:1;io_rob_pendingMMIOld:i:1;io_rob_pendingPtr_flag:i:1;io_rob_pendingPtr_value:i:8;io_rob_loadMmio_0:o:1;io_rob_loadMmio_1:o:1;io_rob_loadMmio_2:o:1;io_rob_loadMmioUop_0_robIdx_value:o:8;io_rob_loadMmioUop_1_robIdx_value:o:8;io_rob_loadMmioUop_2_robIdx_value:o:8;io_req_0_valid:i:1;io_req_0_bits_uop_exceptionVec_3:i:1;io_req_0_bits_uop_exceptionVec_4:i:1;io_req_0_bits_uop_exceptionVec_5:i:1;io_req_0_bits_uop_exceptionVec_13:i:1;io_req_0_bits_uop_exceptionVec_19:i:1;io_req_0_bits_uop_exceptionVec_21:i:1;io_req_0_bits_uop_trigger:i:4;io_req_0_bits_uop_preDecodeInfo_isRVC:i:1;io_req_0_bits_uop_ftqPtr_flag:i:1;io_req_0_bits_uop_ftqPtr_value:i:6;io_req_0_bits_uop_ftqOffset:i:4;io_req_0_bits_uop_fuOpType:i:9;io_req_0_bits_uop_rfWen:i:1;io_req_0_bits_uop_fpWen:i:1;io_req_0_bits_uop_vpu_vstart:i:8;io_req_0_bits_uop_vpu_veew:i:2;io_req_0_bits_uop_uopIdx:i:7;io_req_0_bits_uop_pdest:i:8;io_req_0_bits_uop_robIdx_flag:i:1;io_req_0_bits_uop_robIdx_value:i:8;io_req_0_bits_uop_storeSetHit:i:1;io_req_0_bits_uop_waitForRobIdx_flag:i:1;io_req_0_bits_uop_waitForRobIdx_value:i:8;io_req_0_bits_uop_loadWaitBit:i:1;io_req_0_bits_uop_loadWaitStrict:i:1;io_req_0_bits_uop_lqIdx_flag:i:1;io_req_0_bits_uop_lqIdx_value:i:7;io_req_0_bits_uop_sqIdx_flag:i:1;io_req_0_bits_uop_sqIdx_value:i:6;io_req_0_bits_vaddr:i:50;io_req_0_bits_fullva:i:64;io_req_0_bits_paddr:i:48;io_req_0_bits_gpaddr:i:64;io_req_0_bits_mask:i:16;io_req_0_bits_nc:i:1;io_req_0_bits_mmio:i:1;io_req_0_bits_memBackTypeMM:i:1;io_req_0_bits_isHyper:i:1;io_req_0_bits_isForVSnonLeafPTE:i:1;io_req_0_bits_isvec:i:1;io_req_0_bits_is128bit:i:1;io_req_0_bits_vecActive:i:1;io_req_0_bits_schedIndex:i:7;io_req_0_bits_rep_info_cause_0:i:1;io_req_0_bits_rep_info_cause_1:i:1;io_req_0_bits_rep_info_cause_2:i:1;io_req_0_bits_rep_info_cause_3:i:1;io_req_0_bits_rep_info_cause_4:i:1;io_req_0_bits_rep_info_cause_5:i:1;io_req_0_bits_rep_info_cause_6:i:1;io_req_0_bits_rep_info_cause_7:i:1;io_req_0_bits_rep_info_cause_8:i:1;io_req_0_bits_rep_info_cause_9:i:1;io_req_0_bits_rep_info_cause_10:i:1;io_req_1_valid:i:1;io_req_1_bits_uop_exceptionVec_3:i:1;io_req_1_bits_uop_exceptionVec_4:i:1;io_req_1_bits_uop_exceptionVec_5:i:1;io_req_1_bits_uop_exceptionVec_13:i:1;io_req_1_bits_uop_exceptionVec_19:i:1;io_req_1_bits_uop_exceptionVec_21:i:1;io_req_1_bits_uop_trigger:i:4;io_req_1_bits_uop_preDecodeInfo_isRVC:i:1;io_req_1_bits_uop_ftqPtr_flag:i:1;io_req_1_bits_uop_ftqPtr_value:i:6;io_req_1_bits_uop_ftqOffset:i:4;io_req_1_bits_uop_fuOpType:i:9;io_req_1_bits_uop_rfWen:i:1;io_req_1_bits_uop_fpWen:i:1;io_req_1_bits_uop_vpu_vstart:i:8;io_req_1_bits_uop_vpu_veew:i:2;io_req_1_bits_uop_uopIdx:i:7;io_req_1_bits_uop_pdest:i:8;io_req_1_bits_uop_robIdx_flag:i:1;io_req_1_bits_uop_robIdx_value:i:8;io_req_1_bits_uop_storeSetHit:i:1;io_req_1_bits_uop_waitForRobIdx_flag:i:1;io_req_1_bits_uop_waitForRobIdx_value:i:8;io_req_1_bits_uop_loadWaitBit:i:1;io_req_1_bits_uop_loadWaitStrict:i:1;io_req_1_bits_uop_lqIdx_flag:i:1;io_req_1_bits_uop_lqIdx_value:i:7;io_req_1_bits_uop_sqIdx_flag:i:1;io_req_1_bits_uop_sqIdx_value:i:6;io_req_1_bits_vaddr:i:50;io_req_1_bits_fullva:i:64;io_req_1_bits_paddr:i:48;io_req_1_bits_gpaddr:i:64;io_req_1_bits_mask:i:16;io_req_1_bits_nc:i:1;io_req_1_bits_mmio:i:1;io_req_1_bits_memBackTypeMM:i:1;io_req_1_bits_isHyper:i:1;io_req_1_bits_isForVSnonLeafPTE:i:1;io_req_1_bits_isvec:i:1;io_req_1_bits_is128bit:i:1;io_req_1_bits_vecActive:i:1;io_req_1_bits_schedIndex:i:7;io_req_1_bits_rep_info_cause_0:i:1;io_req_1_bits_rep_info_cause_1:i:1;io_req_1_bits_rep_info_cause_2:i:1;io_req_1_bits_rep_info_cause_3:i:1;io_req_1_bits_rep_info_cause_4:i:1;io_req_1_bits_rep_info_cause_5:i:1;io_req_1_bits_rep_info_cause_6:i:1;io_req_1_bits_rep_info_cause_7:i:1;io_req_1_bits_rep_info_cause_8:i:1;io_req_1_bits_rep_info_cause_9:i:1;io_req_1_bits_rep_info_cause_10:i:1;io_req_2_valid:i:1;io_req_2_bits_uop_exceptionVec_3:i:1;io_req_2_bits_uop_exceptionVec_4:i:1;io_req_2_bits_uop_exceptionVec_5:i:1;io_req_2_bits_uop_exceptionVec_13:i:1;io_req_2_bits_uop_exceptionVec_19:i:1;io_req_2_bits_uop_exceptionVec_21:i:1;io_req_2_bits_uop_trigger:i:4;io_req_2_bits_uop_preDecodeInfo_isRVC:i:1;io_req_2_bits_uop_ftqPtr_flag:i:1;io_req_2_bits_uop_ftqPtr_value:i:6;io_req_2_bits_uop_ftqOffset:i:4;io_req_2_bits_uop_fuOpType:i:9;io_req_2_bits_uop_rfWen:i:1;io_req_2_bits_uop_fpWen:i:1;io_req_2_bits_uop_vpu_vstart:i:8;io_req_2_bits_uop_vpu_veew:i:2;io_req_2_bits_uop_uopIdx:i:7;io_req_2_bits_uop_pdest:i:8;io_req_2_bits_uop_robIdx_flag:i:1;io_req_2_bits_uop_robIdx_value:i:8;io_req_2_bits_uop_storeSetHit:i:1;io_req_2_bits_uop_waitForRobIdx_flag:i:1;io_req_2_bits_uop_waitForRobIdx_value:i:8;io_req_2_bits_uop_loadWaitBit:i:1;io_req_2_bits_uop_loadWaitStrict:i:1;io_req_2_bits_uop_lqIdx_flag:i:1;io_req_2_bits_uop_lqIdx_value:i:7;io_req_2_bits_uop_sqIdx_flag:i:1;io_req_2_bits_uop_sqIdx_value:i:6;io_req_2_bits_vaddr:i:50;io_req_2_bits_fullva:i:64;io_req_2_bits_paddr:i:48;io_req_2_bits_gpaddr:i:64;io_req_2_bits_mask:i:16;io_req_2_bits_nc:i:1;io_req_2_bits_mmio:i:1;io_req_2_bits_memBackTypeMM:i:1;io_req_2_bits_isHyper:i:1;io_req_2_bits_isForVSnonLeafPTE:i:1;io_req_2_bits_isvec:i:1;io_req_2_bits_is128bit:i:1;io_req_2_bits_vecActive:i:1;io_req_2_bits_schedIndex:i:7;io_req_2_bits_rep_info_cause_0:i:1;io_req_2_bits_rep_info_cause_1:i:1;io_req_2_bits_rep_info_cause_2:i:1;io_req_2_bits_rep_info_cause_3:i:1;io_req_2_bits_rep_info_cause_4:i:1;io_req_2_bits_rep_info_cause_5:i:1;io_req_2_bits_rep_info_cause_6:i:1;io_req_2_bits_rep_info_cause_7:i:1;io_req_2_bits_rep_info_cause_8:i:1;io_req_2_bits_rep_info_cause_9:i:1;io_req_2_bits_rep_info_cause_10:i:1;io_mmioOut_2_ready:i:1;io_mmioOut_2_valid:o:1;io_mmioOut_2_bits_uop_exceptionVec_3:o:1;io_mmioOut_2_bits_uop_exceptionVec_4:o:1;io_mmioOut_2_bits_uop_exceptionVec_5:o:1;io_mmioOut_2_bits_uop_exceptionVec_13:o:1;io_mmioOut_2_bits_uop_exceptionVec_19:o:1;io_mmioOut_2_bits_uop_exceptionVec_21:o:1;io_mmioOut_2_bits_uop_trigger:o:4;io_mmioOut_2_bits_uop_preDecodeInfo_isRVC:o:1;io_mmioOut_2_bits_uop_ftqPtr_flag:o:1;io_mmioOut_2_bits_uop_ftqPtr_value:o:6;io_mmioOut_2_bits_uop_ftqOffset:o:4;io_mmioOut_2_bits_uop_fuOpType:o:9;io_mmioOut_2_bits_uop_rfWen:o:1;io_mmioOut_2_bits_uop_fpWen:o:1;io_mmioOut_2_bits_uop_flushPipe:o:1;io_mmioOut_2_bits_uop_vpu_vstart:o:8;io_mmioOut_2_bits_uop_vpu_veew:o:2;io_mmioOut_2_bits_uop_uopIdx:o:7;io_mmioOut_2_bits_uop_pdest:o:8;io_mmioOut_2_bits_uop_robIdx_flag:o:1;io_mmioOut_2_bits_uop_robIdx_value:o:8;io_mmioOut_2_bits_uop_storeSetHit:o:1;io_mmioOut_2_bits_uop_waitForRobIdx_flag:o:1;io_mmioOut_2_bits_uop_waitForRobIdx_value:o:8;io_mmioOut_2_bits_uop_loadWaitBit:o:1;io_mmioOut_2_bits_uop_loadWaitStrict:o:1;io_mmioOut_2_bits_uop_lqIdx_flag:o:1;io_mmioOut_2_bits_uop_lqIdx_value:o:7;io_mmioOut_2_bits_uop_sqIdx_flag:o:1;io_mmioOut_2_bits_uop_sqIdx_value:o:6;io_mmioOut_2_bits_uop_replayInst:o:1;io_mmioRawData_2_lqData:o:64;io_mmioRawData_2_uop_fuOpType:o:9;io_mmioRawData_2_uop_fpWen:o:1;io_mmioRawData_2_addrOffset:o:3;io_ncOut_0_ready:i:1;io_ncOut_0_valid:o:1;io_ncOut_0_bits_uop_exceptionVec_4:o:1;io_ncOut_0_bits_uop_exceptionVec_19:o:1;io_ncOut_0_bits_uop_preDecodeInfo_isRVC:o:1;io_ncOut_0_bits_uop_ftqPtr_flag:o:1;io_ncOut_0_bits_uop_ftqPtr_value:o:6;io_ncOut_0_bits_uop_ftqOffset:o:4;io_ncOut_0_bits_uop_fuOpType:o:9;io_ncOut_0_bits_uop_rfWen:o:1;io_ncOut_0_bits_uop_fpWen:o:1;io_ncOut_0_bits_uop_vpu_vstart:o:8;io_ncOut_0_bits_uop_vpu_veew:o:2;io_ncOut_0_bits_uop_uopIdx:o:7;io_ncOut_0_bits_uop_pdest:o:8;io_ncOut_0_bits_uop_robIdx_flag:o:1;io_ncOut_0_bits_uop_robIdx_value:o:8;io_ncOut_0_bits_uop_storeSetHit:o:1;io_ncOut_0_bits_uop_waitForRobIdx_flag:o:1;io_ncOut_0_bits_uop_waitForRobIdx_value:o:8;io_ncOut_0_bits_uop_loadWaitBit:o:1;io_ncOut_0_bits_uop_loadWaitStrict:o:1;io_ncOut_0_bits_uop_lqIdx_flag:o:1;io_ncOut_0_bits_uop_lqIdx_value:o:7;io_ncOut_0_bits_uop_sqIdx_flag:o:1;io_ncOut_0_bits_uop_sqIdx_value:o:6;io_ncOut_0_bits_vaddr:o:50;io_ncOut_0_bits_paddr:o:48;io_ncOut_0_bits_data:o:129;io_ncOut_0_bits_isvec:o:1;io_ncOut_0_bits_is128bit:o:1;io_ncOut_0_bits_vecActive:o:1;io_ncOut_0_bits_schedIndex:o:7;io_ncOut_1_ready:i:1;io_ncOut_1_valid:o:1;io_ncOut_1_bits_uop_exceptionVec_4:o:1;io_ncOut_1_bits_uop_exceptionVec_19:o:1;io_ncOut_1_bits_uop_preDecodeInfo_isRVC:o:1;io_ncOut_1_bits_uop_ftqPtr_flag:o:1;io_ncOut_1_bits_uop_ftqPtr_value:o:6;io_ncOut_1_bits_uop_ftqOffset:o:4;io_ncOut_1_bits_uop_fuOpType:o:9;io_ncOut_1_bits_uop_rfWen:o:1;io_ncOut_1_bits_uop_fpWen:o:1;io_ncOut_1_bits_uop_vpu_vstart:o:8;io_ncOut_1_bits_uop_vpu_veew:o:2;io_ncOut_1_bits_uop_uopIdx:o:7;io_ncOut_1_bits_uop_pdest:o:8;io_ncOut_1_bits_uop_robIdx_flag:o:1;io_ncOut_1_bits_uop_robIdx_value:o:8;io_ncOut_1_bits_uop_storeSetHit:o:1;io_ncOut_1_bits_uop_waitForRobIdx_flag:o:1;io_ncOut_1_bits_uop_waitForRobIdx_value:o:8;io_ncOut_1_bits_uop_loadWaitBit:o:1;io_ncOut_1_bits_uop_loadWaitStrict:o:1;io_ncOut_1_bits_uop_lqIdx_flag:o:1;io_ncOut_1_bits_uop_lqIdx_value:o:7;io_ncOut_1_bits_uop_sqIdx_flag:o:1;io_ncOut_1_bits_uop_sqIdx_value:o:6;io_ncOut_1_bits_vaddr:o:50;io_ncOut_1_bits_paddr:o:48;io_ncOut_1_bits_data:o:129;io_ncOut_1_bits_isvec:o:1;io_ncOut_1_bits_is128bit:o:1;io_ncOut_1_bits_vecActive:o:1;io_ncOut_1_bits_schedIndex:o:7;io_ncOut_2_ready:i:1;io_ncOut_2_valid:o:1;io_ncOut_2_bits_uop_exceptionVec_4:o:1;io_ncOut_2_bits_uop_exceptionVec_19:o:1;io_ncOut_2_bits_uop_preDecodeInfo_isRVC:o:1;io_ncOut_2_bits_uop_ftqPtr_flag:o:1;io_ncOut_2_bits_uop_ftqPtr_value:o:6;io_ncOut_2_bits_uop_ftqOffset:o:4;io_ncOut_2_bits_uop_fuOpType:o:9;io_ncOut_2_bits_uop_rfWen:o:1;io_ncOut_2_bits_uop_fpWen:o:1;io_ncOut_2_bits_uop_vpu_vstart:o:8;io_ncOut_2_bits_uop_vpu_veew:o:2;io_ncOut_2_bits_uop_uopIdx:o:7;io_ncOut_2_bits_uop_pdest:o:8;io_ncOut_2_bits_uop_robIdx_flag:o:1;io_ncOut_2_bits_uop_robIdx_value:o:8;io_ncOut_2_bits_uop_storeSetHit:o:1;io_ncOut_2_bits_uop_waitForRobIdx_flag:o:1;io_ncOut_2_bits_uop_waitForRobIdx_value:o:8;io_ncOut_2_bits_uop_loadWaitBit:o:1;io_ncOut_2_bits_uop_loadWaitStrict:o:1;io_ncOut_2_bits_uop_lqIdx_flag:o:1;io_ncOut_2_bits_uop_lqIdx_value:o:7;io_ncOut_2_bits_uop_sqIdx_flag:o:1;io_ncOut_2_bits_uop_sqIdx_value:o:6;io_ncOut_2_bits_vaddr:o:50;io_ncOut_2_bits_paddr:o:48;io_ncOut_2_bits_data:o:129;io_ncOut_2_bits_isvec:o:1;io_ncOut_2_bits_is128bit:o:1;io_ncOut_2_bits_vecActive:o:1;io_ncOut_2_bits_schedIndex:o:7;io_uncache_req_ready:i:1;io_uncache_req_valid:o:1;io_uncache_req_bits_robIdx_flag:o:1;io_uncache_req_bits_robIdx_value:o:8;io_uncache_req_bits_cmd:o:5;io_uncache_req_bits_addr:o:48;io_uncache_req_bits_vaddr:o:50;io_uncache_req_bits_data:o:64;io_uncache_req_bits_mask:o:8;io_uncache_req_bits_id:o:7;io_uncache_req_bits_nc:o:1;io_uncache_req_bits_memBackTypeMM:o:1;io_uncache_idResp_valid:i:1;io_uncache_idResp_bits_mid:i:7;io_uncache_idResp_bits_sid:i:4;io_uncache_resp_valid:i:1;io_uncache_resp_bits_data:i:64;io_uncache_resp_bits_id:i:4;io_uncache_resp_bits_denied:i:1;io_uncache_resp_bits_corrupt:i:1;io_rollback_valid:o:1;io_rollback_bits_isRVC:o:1;io_rollback_bits_robIdx_flag:o:1;io_rollback_bits_robIdx_value:o:8;io_rollback_bits_ftqIdx_flag:o:1;io_rollback_bits_ftqIdx_value:o:6;io_rollback_bits_ftqOffset:o:4;io_rollback_bits_level:o:1;io_exception_valid:o:1;io_exception_bits_uop_exceptionVec_3:o:1;io_exception_bits_uop_exceptionVec_4:o:1;io_exception_bits_uop_exceptionVec_5:o:1;io_exception_bits_uop_exceptionVec_13:o:1;io_exception_bits_uop_exceptionVec_19:o:1;io_exception_bits_uop_exceptionVec_21:o:1;io_exception_bits_uop_uopIdx:o:7;io_exception_bits_uop_robIdx_flag:o:1;io_exception_bits_uop_robIdx_value:o:8;io_exception_bits_fullva:o:64;io_exception_bits_gpaddr:o:64;io_exception_bits_isHyper:o:1;io_exception_bits_isForVSnonLeafPTE:o:1",
    "UncacheEntry|entry|slaveId=0|clock:i:1;reset:i:1;io_redirect_valid:i:1;io_redirect_bits_robIdx_flag:i:1;io_redirect_bits_robIdx_value:i:8;io_redirect_bits_level:i:1;io_flush:o:1;io_rob_pendingMMIOld:i:1;io_rob_pendingPtr_flag:i:1;io_rob_pendingPtr_value:i:8;io_mmioSelect:o:1;io_slaveId_valid:o:1;io_slaveId_bits:o:4;io_req_valid:i:1;io_req_bits_uop_exceptionVec_3:i:1;io_req_bits_uop_exceptionVec_4:i:1;io_req_bits_uop_exceptionVec_13:i:1;io_req_bits_uop_exceptionVec_21:i:1;io_req_bits_uop_trigger:i:4;io_req_bits_uop_preDecodeInfo_isRVC:i:1;io_req_bits_uop_ftqPtr_flag:i:1;io_req_bits_uop_ftqPtr_value:i:6;io_req_bits_uop_ftqOffset:i:4;io_req_bits_uop_fuOpType:i:9;io_req_bits_uop_rfWen:i:1;io_req_bits_uop_fpWen:i:1;io_req_bits_uop_vpu_vstart:i:8;io_req_bits_uop_vpu_veew:i:2;io_req_bits_uop_uopIdx:i:7;io_req_bits_uop_pdest:i:8;io_req_bits_uop_robIdx_flag:i:1;io_req_bits_uop_robIdx_value:i:8;io_req_bits_uop_storeSetHit:i:1;io_req_bits_uop_waitForRobIdx_flag:i:1;io_req_bits_uop_waitForRobIdx_value:i:8;io_req_bits_uop_loadWaitBit:i:1;io_req_bits_uop_loadWaitStrict:i:1;io_req_bits_uop_lqIdx_flag:i:1;io_req_bits_uop_lqIdx_value:i:7;io_req_bits_uop_sqIdx_flag:i:1;io_req_bits_uop_sqIdx_value:i:6;io_req_bits_vaddr:i:50;io_req_bits_fullva:i:64;io_req_bits_paddr:i:48;io_req_bits_gpaddr:i:64;io_req_bits_mask:i:16;io_req_bits_nc:i:1;io_req_bits_mmio:i:1;io_req_bits_memBackTypeMM:i:1;io_req_bits_isHyper:i:1;io_req_bits_isForVSnonLeafPTE:i:1;io_req_bits_isvec:i:1;io_req_bits_is128bit:i:1;io_req_bits_vecActive:i:1;io_req_bits_schedIndex:i:7;io_mmioOut_ready:i:1;io_mmioOut_valid:o:1;io_mmioOut_bits_uop_exceptionVec_3:o:1;io_mmioOut_bits_uop_exceptionVec_4:o:1;io_mmioOut_bits_uop_exceptionVec_5:o:1;io_mmioOut_bits_uop_exceptionVec_13:o:1;io_mmioOut_bits_uop_exceptionVec_19:o:1;io_mmioOut_bits_uop_exceptionVec_21:o:1;io_mmioOut_bits_uop_trigger:o:4;io_mmioOut_bits_uop_preDecodeInfo_isRVC:o:1;io_mmioOut_bits_uop_ftqPtr_flag:o:1;io_mmioOut_bits_uop_ftqPtr_value:o:6;io_mmioOut_bits_uop_ftqOffset:o:4;io_mmioOut_bits_uop_fuOpType:o:9;io_mmioOut_bits_uop_rfWen:o:1;io_mmioOut_bits_uop_fpWen:o:1;io_mmioOut_bits_uop_flushPipe:o:1;io_mmioOut_bits_uop_vpu_vstart:o:8;io_mmioOut_bits_uop_vpu_veew:o:2;io_mmioOut_bits_uop_uopIdx:o:7;io_mmioOut_bits_uop_pdest:o:8;io_mmioOut_bits_uop_robIdx_flag:o:1;io_mmioOut_bits_uop_robIdx_value:o:8;io_mmioOut_bits_uop_storeSetHit:o:1;io_mmioOut_bits_uop_waitForRobIdx_flag:o:1;io_mmioOut_bits_uop_waitForRobIdx_value:o:8;io_mmioOut_bits_uop_loadWaitBit:o:1;io_mmioOut_bits_uop_loadWaitStrict:o:1;io_mmioOut_bits_uop_lqIdx_flag:o:1;io_mmioOut_bits_uop_lqIdx_value:o:7;io_mmioOut_bits_uop_sqIdx_flag:o:1;io_mmioOut_bits_uop_sqIdx_value:o:6;io_mmioOut_bits_uop_replayInst:o:1;io_mmioRawData_lqData:o:64;io_mmioRawData_uop_fuOpType:o:9;io_mmioRawData_uop_fpWen:o:1;io_mmioRawData_addrOffset:o:3;io_ncOut_ready:i:1;io_ncOut_valid:o:1;io_ncOut_bits_uop_exceptionVec_4:o:1;io_ncOut_bits_uop_exceptionVec_19:o:1;io_ncOut_bits_uop_preDecodeInfo_isRVC:o:1;io_ncOut_bits_uop_ftqPtr_flag:o:1;io_ncOut_bits_uop_ftqPtr_value:o:6;io_ncOut_bits_uop_ftqOffset:o:4;io_ncOut_bits_uop_fuOpType:o:9;io_ncOut_bits_uop_rfWen:o:1;io_ncOut_bits_uop_fpWen:o:1;io_ncOut_bits_uop_vpu_vstart:o:8;io_ncOut_bits_uop_vpu_veew:o:2;io_ncOut_bits_uop_uopIdx:o:7;io_ncOut_bits_uop_pdest:o:8;io_ncOut_bits_uop_robIdx_flag:o:1;io_ncOut_bits_uop_robIdx_value:o:8;io_ncOut_bits_uop_storeSetHit:o:1;io_ncOut_bits_uop_waitForRobIdx_flag:o:1;io_ncOut_bits_uop_waitForRobIdx_value:o:8;io_ncOut_bits_uop_loadWaitBit:o:1;io_ncOut_bits_uop_loadWaitStrict:o:1;io_ncOut_bits_uop_lqIdx_flag:o:1;io_ncOut_bits_uop_lqIdx_value:o:7;io_ncOut_bits_uop_sqIdx_flag:o:1;io_ncOut_bits_uop_sqIdx_value:o:6;io_ncOut_bits_vaddr:o:50;io_ncOut_bits_paddr:o:48;io_ncOut_bits_data:o:129;io_ncOut_bits_isvec:o:1;io_ncOut_bits_is128bit:o:1;io_ncOut_bits_vecActive:o:1;io_ncOut_bits_schedIndex:o:7;io_uncache_req_ready:i:1;io_uncache_req_valid:o:1;io_uncache_req_bits_robIdx_flag:o:1;io_uncache_req_bits_robIdx_value:o:8;io_uncache_req_bits_addr:o:48;io_uncache_req_bits_vaddr:o:50;io_uncache_req_bits_mask:o:8;io_uncache_req_bits_nc:o:1;io_uncache_req_bits_memBackTypeMM:o:1;io_uncache_idResp_valid:i:1;io_uncache_idResp_bits_mid:i:7;io_uncache_idResp_bits_sid:i:4;io_uncache_resp_valid:i:1;io_uncache_resp_bits_data:i:64;io_uncache_resp_bits_denied:i:1;io_uncache_resp_bits_corrupt:i:1;io_exception_valid:o:1;io_exception_bits_uop_exceptionVec_3:o:1;io_exception_bits_uop_exceptionVec_4:o:1;io_exception_bits_uop_exceptionVec_5:o:1;io_exception_bits_uop_exceptionVec_13:o:1;io_exception_bits_uop_exceptionVec_19:o:1;io_exception_bits_uop_exceptionVec_21:o:1;io_exception_bits_uop_uopIdx:o:7;io_exception_bits_uop_robIdx_flag:o:1;io_exception_bits_uop_robIdx_value:o:8;io_exception_bits_fullva:o:64;io_exception_bits_gpaddr:o:64;io_exception_bits_isHyper:o:1;io_exception_bits_isForVSnonLeafPTE:o:1",
    "UncacheEntry_1|entry|slaveId=1|clock:i:1;reset:i:1;io_redirect_valid:i:1;io_redirect_bits_robIdx_flag:i:1;io_redirect_bits_robIdx_value:i:8;io_redirect_bits_level:i:1;io_flush:o:1;io_rob_pendingMMIOld:i:1;io_rob_pendingPtr_flag:i:1;io_rob_pendingPtr_value:i:8;io_mmioSelect:o:1;io_slaveId_valid:o:1;io_slaveId_bits:o:4;io_req_valid:i:1;io_req_bits_uop_exceptionVec_3:i:1;io_req_bits_uop_exceptionVec_4:i:1;io_req_bits_uop_exceptionVec_13:i:1;io_req_bits_uop_exceptionVec_21:i:1;io_req_bits_uop_trigger:i:4;io_req_bits_uop_preDecodeInfo_isRVC:i:1;io_req_bits_uop_ftqPtr_flag:i:1;io_req_bits_uop_ftqPtr_value:i:6;io_req_bits_uop_ftqOffset:i:4;io_req_bits_uop_fuOpType:i:9;io_req_bits_uop_rfWen:i:1;io_req_bits_uop_fpWen:i:1;io_req_bits_uop_vpu_vstart:i:8;io_req_bits_uop_vpu_veew:i:2;io_req_bits_uop_uopIdx:i:7;io_req_bits_uop_pdest:i:8;io_req_bits_uop_robIdx_flag:i:1;io_req_bits_uop_robIdx_value:i:8;io_req_bits_uop_storeSetHit:i:1;io_req_bits_uop_waitForRobIdx_flag:i:1;io_req_bits_uop_waitForRobIdx_value:i:8;io_req_bits_uop_loadWaitBit:i:1;io_req_bits_uop_loadWaitStrict:i:1;io_req_bits_uop_lqIdx_flag:i:1;io_req_bits_uop_lqIdx_value:i:7;io_req_bits_uop_sqIdx_flag:i:1;io_req_bits_uop_sqIdx_value:i:6;io_req_bits_vaddr:i:50;io_req_bits_fullva:i:64;io_req_bits_paddr:i:48;io_req_bits_gpaddr:i:64;io_req_bits_mask:i:16;io_req_bits_nc:i:1;io_req_bits_mmio:i:1;io_req_bits_memBackTypeMM:i:1;io_req_bits_isHyper:i:1;io_req_bits_isForVSnonLeafPTE:i:1;io_req_bits_isvec:i:1;io_req_bits_is128bit:i:1;io_req_bits_vecActive:i:1;io_req_bits_schedIndex:i:7;io_mmioOut_ready:i:1;io_mmioOut_valid:o:1;io_mmioOut_bits_uop_exceptionVec_3:o:1;io_mmioOut_bits_uop_exceptionVec_4:o:1;io_mmioOut_bits_uop_exceptionVec_5:o:1;io_mmioOut_bits_uop_exceptionVec_13:o:1;io_mmioOut_bits_uop_exceptionVec_19:o:1;io_mmioOut_bits_uop_exceptionVec_21:o:1;io_mmioOut_bits_uop_trigger:o:4;io_mmioOut_bits_uop_preDecodeInfo_isRVC:o:1;io_mmioOut_bits_uop_ftqPtr_flag:o:1;io_mmioOut_bits_uop_ftqPtr_value:o:6;io_mmioOut_bits_uop_ftqOffset:o:4;io_mmioOut_bits_uop_fuOpType:o:9;io_mmioOut_bits_uop_rfWen:o:1;io_mmioOut_bits_uop_fpWen:o:1;io_mmioOut_bits_uop_flushPipe:o:1;io_mmioOut_bits_uop_vpu_vstart:o:8;io_mmioOut_bits_uop_vpu_veew:o:2;io_mmioOut_bits_uop_uopIdx:o:7;io_mmioOut_bits_uop_pdest:o:8;io_mmioOut_bits_uop_robIdx_flag:o:1;io_mmioOut_bits_uop_robIdx_value:o:8;io_mmioOut_bits_uop_storeSetHit:o:1;io_mmioOut_bits_uop_waitForRobIdx_flag:o:1;io_mmioOut_bits_uop_waitForRobIdx_value:o:8;io_mmioOut_bits_uop_loadWaitBit:o:1;io_mmioOut_bits_uop_loadWaitStrict:o:1;io_mmioOut_bits_uop_lqIdx_flag:o:1;io_mmioOut_bits_uop_lqIdx_value:o:7;io_mmioOut_bits_uop_sqIdx_flag:o:1;io_mmioOut_bits_uop_sqIdx_value:o:6;io_mmioOut_bits_uop_replayInst:o:1;io_mmioRawData_lqData:o:64;io_mmioRawData_uop_fuOpType:o:9;io_mmioRawData_uop_fpWen:o:1;io_mmioRawData_addrOffset:o:3;io_ncOut_ready:i:1;io_ncOut_valid:o:1;io_ncOut_bits_uop_exceptionVec_4:o:1;io_ncOut_bits_uop_exceptionVec_19:o:1;io_ncOut_bits_uop_preDecodeInfo_isRVC:o:1;io_ncOut_bits_uop_ftqPtr_flag:o:1;io_ncOut_bits_uop_ftqPtr_value:o:6;io_ncOut_bits_uop_ftqOffset:o:4;io_ncOut_bits_uop_fuOpType:o:9;io_ncOut_bits_uop_rfWen:o:1;io_ncOut_bits_uop_fpWen:o:1;io_ncOut_bits_uop_vpu_vstart:o:8;io_ncOut_bits_uop_vpu_veew:o:2;io_ncOut_bits_uop_uopIdx:o:7;io_ncOut_bits_uop_pdest:o:8;io_ncOut_bits_uop_robIdx_flag:o:1;io_ncOut_bits_uop_robIdx_value:o:8;io_ncOut_bits_uop_storeSetHit:o:1;io_ncOut_bits_uop_waitForRobIdx_flag:o:1;io_ncOut_bits_uop_waitForRobIdx_value:o:8;io_ncOut_bits_uop_loadWaitBit:o:1;io_ncOut_bits_uop_loadWaitStrict:o:1;io_ncOut_bits_uop_lqIdx_flag:o:1;io_ncOut_bits_uop_lqIdx_value:o:7;io_ncOut_bits_uop_sqIdx_flag:o:1;io_ncOut_bits_uop_sqIdx_value:o:6;io_ncOut_bits_vaddr:o:50;io_ncOut_bits_paddr:o:48;io_ncOut_bits_data:o:129;io_ncOut_bits_isvec:o:1;io_ncOut_bits_is128bit:o:1;io_ncOut_bits_vecActive:o:1;io_ncOut_bits_schedIndex:o:7;io_uncache_req_ready:i:1;io_uncache_req_valid:o:1;io_uncache_req_bits_robIdx_flag:o:1;io_uncache_req_bits_robIdx_value:o:8;io_uncache_req_bits_addr:o:48;io_uncache_req_bits_vaddr:o:50;io_uncache_req_bits_mask:o:8;io_uncache_req_bits_nc:o:1;io_uncache_req_bits_memBackTypeMM:o:1;io_uncache_idResp_valid:i:1;io_uncache_idResp_bits_mid:i:7;io_uncache_idResp_bits_sid:i:4;io_uncache_resp_valid:i:1;io_uncache_resp_bits_data:i:64;io_uncache_resp_bits_denied:i:1;io_uncache_resp_bits_corrupt:i:1;io_exception_valid:o:1;io_exception_bits_uop_exceptionVec_3:o:1;io_exception_bits_uop_exceptionVec_4:o:1;io_exception_bits_uop_exceptionVec_5:o:1;io_exception_bits_uop_exceptionVec_13:o:1;io_exception_bits_uop_exceptionVec_19:o:1;io_exception_bits_uop_exceptionVec_21:o:1;io_exception_bits_uop_uopIdx:o:7;io_exception_bits_uop_robIdx_flag:o:1;io_exception_bits_uop_robIdx_value:o:8;io_exception_bits_fullva:o:64;io_exception_bits_gpaddr:o:64;io_exception_bits_isHyper:o:1;io_exception_bits_isForVSnonLeafPTE:o:1",
    "UncacheEntry_2|entry|slaveId=2|clock:i:1;reset:i:1;io_redirect_valid:i:1;io_redirect_bits_robIdx_flag:i:1;io_redirect_bits_robIdx_value:i:8;io_redirect_bits_level:i:1;io_flush:o:1;io_rob_pendingMMIOld:i:1;io_rob_pendingPtr_flag:i:1;io_rob_pendingPtr_value:i:8;io_mmioSelect:o:1;io_slaveId_valid:o:1;io_slaveId_bits:o:4;io_req_valid:i:1;io_req_bits_uop_exceptionVec_3:i:1;io_req_bits_uop_exceptionVec_4:i:1;io_req_bits_uop_exceptionVec_13:i:1;io_req_bits_uop_exceptionVec_21:i:1;io_req_bits_uop_trigger:i:4;io_req_bits_uop_preDecodeInfo_isRVC:i:1;io_req_bits_uop_ftqPtr_flag:i:1;io_req_bits_uop_ftqPtr_value:i:6;io_req_bits_uop_ftqOffset:i:4;io_req_bits_uop_fuOpType:i:9;io_req_bits_uop_rfWen:i:1;io_req_bits_uop_fpWen:i:1;io_req_bits_uop_vpu_vstart:i:8;io_req_bits_uop_vpu_veew:i:2;io_req_bits_uop_uopIdx:i:7;io_req_bits_uop_pdest:i:8;io_req_bits_uop_robIdx_flag:i:1;io_req_bits_uop_robIdx_value:i:8;io_req_bits_uop_storeSetHit:i:1;io_req_bits_uop_waitForRobIdx_flag:i:1;io_req_bits_uop_waitForRobIdx_value:i:8;io_req_bits_uop_loadWaitBit:i:1;io_req_bits_uop_loadWaitStrict:i:1;io_req_bits_uop_lqIdx_flag:i:1;io_req_bits_uop_lqIdx_value:i:7;io_req_bits_uop_sqIdx_flag:i:1;io_req_bits_uop_sqIdx_value:i:6;io_req_bits_vaddr:i:50;io_req_bits_fullva:i:64;io_req_bits_paddr:i:48;io_req_bits_gpaddr:i:64;io_req_bits_mask:i:16;io_req_bits_nc:i:1;io_req_bits_mmio:i:1;io_req_bits_memBackTypeMM:i:1;io_req_bits_isHyper:i:1;io_req_bits_isForVSnonLeafPTE:i:1;io_req_bits_isvec:i:1;io_req_bits_is128bit:i:1;io_req_bits_vecActive:i:1;io_req_bits_schedIndex:i:7;io_mmioOut_ready:i:1;io_mmioOut_valid:o:1;io_mmioOut_bits_uop_exceptionVec_3:o:1;io_mmioOut_bits_uop_exceptionVec_4:o:1;io_mmioOut_bits_uop_exceptionVec_5:o:1;io_mmioOut_bits_uop_exceptionVec_13:o:1;io_mmioOut_bits_uop_exceptionVec_19:o:1;io_mmioOut_bits_uop_exceptionVec_21:o:1;io_mmioOut_bits_uop_trigger:o:4;io_mmioOut_bits_uop_preDecodeInfo_isRVC:o:1;io_mmioOut_bits_uop_ftqPtr_flag:o:1;io_mmioOut_bits_uop_ftqPtr_value:o:6;io_mmioOut_bits_uop_ftqOffset:o:4;io_mmioOut_bits_uop_fuOpType:o:9;io_mmioOut_bits_uop_rfWen:o:1;io_mmioOut_bits_uop_fpWen:o:1;io_mmioOut_bits_uop_flushPipe:o:1;io_mmioOut_bits_uop_vpu_vstart:o:8;io_mmioOut_bits_uop_vpu_veew:o:2;io_mmioOut_bits_uop_uopIdx:o:7;io_mmioOut_bits_uop_pdest:o:8;io_mmioOut_bits_uop_robIdx_flag:o:1;io_mmioOut_bits_uop_robIdx_value:o:8;io_mmioOut_bits_uop_storeSetHit:o:1;io_mmioOut_bits_uop_waitForRobIdx_flag:o:1;io_mmioOut_bits_uop_waitForRobIdx_value:o:8;io_mmioOut_bits_uop_loadWaitBit:o:1;io_mmioOut_bits_uop_loadWaitStrict:o:1;io_mmioOut_bits_uop_lqIdx_flag:o:1;io_mmioOut_bits_uop_lqIdx_value:o:7;io_mmioOut_bits_uop_sqIdx_flag:o:1;io_mmioOut_bits_uop_sqIdx_value:o:6;io_mmioOut_bits_uop_replayInst:o:1;io_mmioRawData_lqData:o:64;io_mmioRawData_uop_fuOpType:o:9;io_mmioRawData_uop_fpWen:o:1;io_mmioRawData_addrOffset:o:3;io_ncOut_ready:i:1;io_ncOut_valid:o:1;io_ncOut_bits_uop_exceptionVec_4:o:1;io_ncOut_bits_uop_exceptionVec_19:o:1;io_ncOut_bits_uop_preDecodeInfo_isRVC:o:1;io_ncOut_bits_uop_ftqPtr_flag:o:1;io_ncOut_bits_uop_ftqPtr_value:o:6;io_ncOut_bits_uop_ftqOffset:o:4;io_ncOut_bits_uop_fuOpType:o:9;io_ncOut_bits_uop_rfWen:o:1;io_ncOut_bits_uop_fpWen:o:1;io_ncOut_bits_uop_vpu_vstart:o:8;io_ncOut_bits_uop_vpu_veew:o:2;io_ncOut_bits_uop_uopIdx:o:7;io_ncOut_bits_uop_pdest:o:8;io_ncOut_bits_uop_robIdx_flag:o:1;io_ncOut_bits_uop_robIdx_value:o:8;io_ncOut_bits_uop_storeSetHit:o:1;io_ncOut_bits_uop_waitForRobIdx_flag:o:1;io_ncOut_bits_uop_waitForRobIdx_value:o:8;io_ncOut_bits_uop_loadWaitBit:o:1;io_ncOut_bits_uop_loadWaitStrict:o:1;io_ncOut_bits_uop_lqIdx_flag:o:1;io_ncOut_bits_uop_lqIdx_value:o:7;io_ncOut_bits_uop_sqIdx_flag:o:1;io_ncOut_bits_uop_sqIdx_value:o:6;io_ncOut_bits_vaddr:o:50;io_ncOut_bits_paddr:o:48;io_ncOut_bits_data:o:129;io_ncOut_bits_isvec:o:1;io_ncOut_bits_is128bit:o:1;io_ncOut_bits_vecActive:o:1;io_ncOut_bits_schedIndex:o:7;io_uncache_req_ready:i:1;io_uncache_req_valid:o:1;io_uncache_req_bits_robIdx_flag:o:1;io_uncache_req_bits_robIdx_value:o:8;io_uncache_req_bits_addr:o:48;io_uncache_req_bits_vaddr:o:50;io_uncache_req_bits_mask:o:8;io_uncache_req_bits_nc:o:1;io_uncache_req_bits_memBackTypeMM:o:1;io_uncache_idResp_valid:i:1;io_uncache_idResp_bits_mid:i:7;io_uncache_idResp_bits_sid:i:4;io_uncache_resp_valid:i:1;io_uncache_resp_bits_data:i:64;io_uncache_resp_bits_denied:i:1;io_uncache_resp_bits_corrupt:i:1;io_exception_valid:o:1;io_exception_bits_uop_exceptionVec_3:o:1;io_exception_bits_uop_exceptionVec_4:o:1;io_exception_bits_uop_exceptionVec_5:o:1;io_exception_bits_uop_exceptionVec_13:o:1;io_exception_bits_uop_exceptionVec_19:o:1;io_exception_bits_uop_exceptionVec_21:o:1;io_exception_bits_uop_uopIdx:o:7;io_exception_bits_uop_robIdx_flag:o:1;io_exception_bits_uop_robIdx_value:o:8;io_exception_bits_fullva:o:64;io_exception_bits_gpaddr:o:64;io_exception_bits_isHyper:o:1;io_exception_bits_isForVSnonLeafPTE:o:1",
    "UncacheEntry_3|entry|slaveId=3|clock:i:1;reset:i:1;io_redirect_valid:i:1;io_redirect_bits_robIdx_flag:i:1;io_redirect_bits_robIdx_value:i:8;io_redirect_bits_level:i:1;io_flush:o:1;io_rob_pendingMMIOld:i:1;io_rob_pendingPtr_flag:i:1;io_rob_pendingPtr_value:i:8;io_mmioSelect:o:1;io_slaveId_valid:o:1;io_slaveId_bits:o:4;io_req_valid:i:1;io_req_bits_uop_exceptionVec_3:i:1;io_req_bits_uop_exceptionVec_4:i:1;io_req_bits_uop_exceptionVec_13:i:1;io_req_bits_uop_exceptionVec_21:i:1;io_req_bits_uop_trigger:i:4;io_req_bits_uop_preDecodeInfo_isRVC:i:1;io_req_bits_uop_ftqPtr_flag:i:1;io_req_bits_uop_ftqPtr_value:i:6;io_req_bits_uop_ftqOffset:i:4;io_req_bits_uop_fuOpType:i:9;io_req_bits_uop_rfWen:i:1;io_req_bits_uop_fpWen:i:1;io_req_bits_uop_vpu_vstart:i:8;io_req_bits_uop_vpu_veew:i:2;io_req_bits_uop_uopIdx:i:7;io_req_bits_uop_pdest:i:8;io_req_bits_uop_robIdx_flag:i:1;io_req_bits_uop_robIdx_value:i:8;io_req_bits_uop_storeSetHit:i:1;io_req_bits_uop_waitForRobIdx_flag:i:1;io_req_bits_uop_waitForRobIdx_value:i:8;io_req_bits_uop_loadWaitBit:i:1;io_req_bits_uop_loadWaitStrict:i:1;io_req_bits_uop_lqIdx_flag:i:1;io_req_bits_uop_lqIdx_value:i:7;io_req_bits_uop_sqIdx_flag:i:1;io_req_bits_uop_sqIdx_value:i:6;io_req_bits_vaddr:i:50;io_req_bits_fullva:i:64;io_req_bits_paddr:i:48;io_req_bits_gpaddr:i:64;io_req_bits_mask:i:16;io_req_bits_nc:i:1;io_req_bits_mmio:i:1;io_req_bits_memBackTypeMM:i:1;io_req_bits_isHyper:i:1;io_req_bits_isForVSnonLeafPTE:i:1;io_req_bits_isvec:i:1;io_req_bits_is128bit:i:1;io_req_bits_vecActive:i:1;io_req_bits_schedIndex:i:7;io_mmioOut_ready:i:1;io_mmioOut_valid:o:1;io_mmioOut_bits_uop_exceptionVec_3:o:1;io_mmioOut_bits_uop_exceptionVec_4:o:1;io_mmioOut_bits_uop_exceptionVec_5:o:1;io_mmioOut_bits_uop_exceptionVec_13:o:1;io_mmioOut_bits_uop_exceptionVec_19:o:1;io_mmioOut_bits_uop_exceptionVec_21:o:1;io_mmioOut_bits_uop_trigger:o:4;io_mmioOut_bits_uop_preDecodeInfo_isRVC:o:1;io_mmioOut_bits_uop_ftqPtr_flag:o:1;io_mmioOut_bits_uop_ftqPtr_value:o:6;io_mmioOut_bits_uop_ftqOffset:o:4;io_mmioOut_bits_uop_fuOpType:o:9;io_mmioOut_bits_uop_rfWen:o:1;io_mmioOut_bits_uop_fpWen:o:1;io_mmioOut_bits_uop_flushPipe:o:1;io_mmioOut_bits_uop_vpu_vstart:o:8;io_mmioOut_bits_uop_vpu_veew:o:2;io_mmioOut_bits_uop_uopIdx:o:7;io_mmioOut_bits_uop_pdest:o:8;io_mmioOut_bits_uop_robIdx_flag:o:1;io_mmioOut_bits_uop_robIdx_value:o:8;io_mmioOut_bits_uop_storeSetHit:o:1;io_mmioOut_bits_uop_waitForRobIdx_flag:o:1;io_mmioOut_bits_uop_waitForRobIdx_value:o:8;io_mmioOut_bits_uop_loadWaitBit:o:1;io_mmioOut_bits_uop_loadWaitStrict:o:1;io_mmioOut_bits_uop_lqIdx_flag:o:1;io_mmioOut_bits_uop_lqIdx_value:o:7;io_mmioOut_bits_uop_sqIdx_flag:o:1;io_mmioOut_bits_uop_sqIdx_value:o:6;io_mmioOut_bits_uop_replayInst:o:1;io_mmioRawData_lqData:o:64;io_mmioRawData_uop_fuOpType:o:9;io_mmioRawData_uop_fpWen:o:1;io_mmioRawData_addrOffset:o:3;io_ncOut_ready:i:1;io_ncOut_valid:o:1;io_ncOut_bits_uop_exceptionVec_4:o:1;io_ncOut_bits_uop_exceptionVec_19:o:1;io_ncOut_bits_uop_preDecodeInfo_isRVC:o:1;io_ncOut_bits_uop_ftqPtr_flag:o:1;io_ncOut_bits_uop_ftqPtr_value:o:6;io_ncOut_bits_uop_ftqOffset:o:4;io_ncOut_bits_uop_fuOpType:o:9;io_ncOut_bits_uop_rfWen:o:1;io_ncOut_bits_uop_fpWen:o:1;io_ncOut_bits_uop_vpu_vstart:o:8;io_ncOut_bits_uop_vpu_veew:o:2;io_ncOut_bits_uop_uopIdx:o:7;io_ncOut_bits_uop_pdest:o:8;io_ncOut_bits_uop_robIdx_flag:o:1;io_ncOut_bits_uop_robIdx_value:o:8;io_ncOut_bits_uop_storeSetHit:o:1;io_ncOut_bits_uop_waitForRobIdx_flag:o:1;io_ncOut_bits_uop_waitForRobIdx_value:o:8;io_ncOut_bits_uop_loadWaitBit:o:1;io_ncOut_bits_uop_loadWaitStrict:o:1;io_ncOut_bits_uop_lqIdx_flag:o:1;io_ncOut_bits_uop_lqIdx_value:o:7;io_ncOut_bits_uop_sqIdx_flag:o:1;io_ncOut_bits_uop_sqIdx_value:o:6;io_ncOut_bits_vaddr:o:50;io_ncOut_bits_paddr:o:48;io_ncOut_bits_data:o:129;io_ncOut_bits_isvec:o:1;io_ncOut_bits_is128bit:o:1;io_ncOut_bits_vecActive:o:1;io_ncOut_bits_schedIndex:o:7;io_uncache_req_ready:i:1;io_uncache_req_valid:o:1;io_uncache_req_bits_robIdx_flag:o:1;io_uncache_req_bits_robIdx_value:o:8;io_uncache_req_bits_addr:o:48;io_uncache_req_bits_vaddr:o:50;io_uncache_req_bits_mask:o:8;io_uncache_req_bits_nc:o:1;io_uncache_req_bits_memBackTypeMM:o:1;io_uncache_idResp_valid:i:1;io_uncache_idResp_bits_mid:i:7;io_uncache_idResp_bits_sid:i:4;io_uncache_resp_valid:i:1;io_uncache_resp_bits_data:i:64;io_uncache_resp_bits_denied:i:1;io_uncache_resp_bits_corrupt:i:1;io_exception_valid:o:1;io_exception_bits_uop_exceptionVec_3:o:1;io_exception_bits_uop_exceptionVec_4:o:1;io_exception_bits_uop_exceptionVec_5:o:1;io_exception_bits_uop_exceptionVec_13:o:1;io_exception_bits_uop_exceptionVec_19:o:1;io_exception_bits_uop_exceptionVec_21:o:1;io_exception_bits_uop_uopIdx:o:7;io_exception_bits_uop_robIdx_flag:o:1;io_exception_bits_uop_robIdx_value:o:8;io_exception_bits_fullva:o:64;io_exception_bits_gpaddr:o:64;io_exception_bits_isHyper:o:1;io_exception_bits_isForVSnonLeafPTE:o:1",
    "UncacheEntry_4|entry|slaveId=4|clock:i:1;reset:i:1;io_redirect_valid:i:1;io_redirect_bits_robIdx_flag:i:1;io_redirect_bits_robIdx_value:i:8;io_redirect_bits_level:i:1;io_flush:o:1;io_rob_pendingMMIOld:i:1;io_rob_pendingPtr_flag:i:1;io_rob_pendingPtr_value:i:8;io_mmioSelect:o:1;io_slaveId_valid:o:1;io_slaveId_bits:o:4;io_req_valid:i:1;io_req_bits_uop_exceptionVec_3:i:1;io_req_bits_uop_exceptionVec_4:i:1;io_req_bits_uop_exceptionVec_13:i:1;io_req_bits_uop_exceptionVec_21:i:1;io_req_bits_uop_trigger:i:4;io_req_bits_uop_preDecodeInfo_isRVC:i:1;io_req_bits_uop_ftqPtr_flag:i:1;io_req_bits_uop_ftqPtr_value:i:6;io_req_bits_uop_ftqOffset:i:4;io_req_bits_uop_fuOpType:i:9;io_req_bits_uop_rfWen:i:1;io_req_bits_uop_fpWen:i:1;io_req_bits_uop_vpu_vstart:i:8;io_req_bits_uop_vpu_veew:i:2;io_req_bits_uop_uopIdx:i:7;io_req_bits_uop_pdest:i:8;io_req_bits_uop_robIdx_flag:i:1;io_req_bits_uop_robIdx_value:i:8;io_req_bits_uop_storeSetHit:i:1;io_req_bits_uop_waitForRobIdx_flag:i:1;io_req_bits_uop_waitForRobIdx_value:i:8;io_req_bits_uop_loadWaitBit:i:1;io_req_bits_uop_loadWaitStrict:i:1;io_req_bits_uop_lqIdx_flag:i:1;io_req_bits_uop_lqIdx_value:i:7;io_req_bits_uop_sqIdx_flag:i:1;io_req_bits_uop_sqIdx_value:i:6;io_req_bits_vaddr:i:50;io_req_bits_fullva:i:64;io_req_bits_paddr:i:48;io_req_bits_gpaddr:i:64;io_req_bits_mask:i:16;io_req_bits_nc:i:1;io_req_bits_mmio:i:1;io_req_bits_memBackTypeMM:i:1;io_req_bits_isHyper:i:1;io_req_bits_isForVSnonLeafPTE:i:1;io_req_bits_isvec:i:1;io_req_bits_is128bit:i:1;io_req_bits_vecActive:i:1;io_req_bits_schedIndex:i:7;io_mmioOut_ready:i:1;io_mmioOut_valid:o:1;io_mmioOut_bits_uop_exceptionVec_3:o:1;io_mmioOut_bits_uop_exceptionVec_4:o:1;io_mmioOut_bits_uop_exceptionVec_5:o:1;io_mmioOut_bits_uop_exceptionVec_13:o:1;io_mmioOut_bits_uop_exceptionVec_19:o:1;io_mmioOut_bits_uop_exceptionVec_21:o:1;io_mmioOut_bits_uop_trigger:o:4;io_mmioOut_bits_uop_preDecodeInfo_isRVC:o:1;io_mmioOut_bits_uop_ftqPtr_flag:o:1;io_mmioOut_bits_uop_ftqPtr_value:o:6;io_mmioOut_bits_uop_ftqOffset:o:4;io_mmioOut_bits_uop_fuOpType:o:9;io_mmioOut_bits_uop_rfWen:o:1;io_mmioOut_bits_uop_fpWen:o:1;io_mmioOut_bits_uop_flushPipe:o:1;io_mmioOut_bits_uop_vpu_vstart:o:8;io_mmioOut_bits_uop_vpu_veew:o:2;io_mmioOut_bits_uop_uopIdx:o:7;io_mmioOut_bits_uop_pdest:o:8;io_mmioOut_bits_uop_robIdx_flag:o:1;io_mmioOut_bits_uop_robIdx_value:o:8;io_mmioOut_bits_uop_storeSetHit:o:1;io_mmioOut_bits_uop_waitForRobIdx_flag:o:1;io_mmioOut_bits_uop_waitForRobIdx_value:o:8;io_mmioOut_bits_uop_loadWaitBit:o:1;io_mmioOut_bits_uop_loadWaitStrict:o:1;io_mmioOut_bits_uop_lqIdx_flag:o:1;io_mmioOut_bits_uop_lqIdx_value:o:7;io_mmioOut_bits_uop_sqIdx_flag:o:1;io_mmioOut_bits_uop_sqIdx_value:o:6;io_mmioOut_bits_uop_replayInst:o:1;io_mmioRawData_lqData:o:64;io_mmioRawData_uop_fuOpType:o:9;io_mmioRawData_uop_fpWen:o:1;io_mmioRawData_addrOffset:o:3;io_ncOut_ready:i:1;io_ncOut_valid:o:1;io_ncOut_bits_uop_exceptionVec_4:o:1;io_ncOut_bits_uop_exceptionVec_19:o:1;io_ncOut_bits_uop_preDecodeInfo_isRVC:o:1;io_ncOut_bits_uop_ftqPtr_flag:o:1;io_ncOut_bits_uop_ftqPtr_value:o:6;io_ncOut_bits_uop_ftqOffset:o:4;io_ncOut_bits_uop_fuOpType:o:9;io_ncOut_bits_uop_rfWen:o:1;io_ncOut_bits_uop_fpWen:o:1;io_ncOut_bits_uop_vpu_vstart:o:8;io_ncOut_bits_uop_vpu_veew:o:2;io_ncOut_bits_uop_uopIdx:o:7;io_ncOut_bits_uop_pdest:o:8;io_ncOut_bits_uop_robIdx_flag:o:1;io_ncOut_bits_uop_robIdx_value:o:8;io_ncOut_bits_uop_storeSetHit:o:1;io_ncOut_bits_uop_waitForRobIdx_flag:o:1;io_ncOut_bits_uop_waitForRobIdx_value:o:8;io_ncOut_bits_uop_loadWaitBit:o:1;io_ncOut_bits_uop_loadWaitStrict:o:1;io_ncOut_bits_uop_lqIdx_flag:o:1;io_ncOut_bits_uop_lqIdx_value:o:7;io_ncOut_bits_uop_sqIdx_flag:o:1;io_ncOut_bits_uop_sqIdx_value:o:6;io_ncOut_bits_vaddr:o:50;io_ncOut_bits_paddr:o:48;io_ncOut_bits_data:o:129;io_ncOut_bits_isvec:o:1;io_ncOut_bits_is128bit:o:1;io_ncOut_bits_vecActive:o:1;io_ncOut_bits_schedIndex:o:7;io_uncache_req_ready:i:1;io_uncache_req_valid:o:1;io_uncache_req_bits_robIdx_flag:o:1;io_uncache_req_bits_robIdx_value:o:8;io_uncache_req_bits_addr:o:48;io_uncache_req_bits_vaddr:o:50;io_uncache_req_bits_mask:o:8;io_uncache_req_bits_nc:o:1;io_uncache_req_bits_memBackTypeMM:o:1;io_uncache_idResp_valid:i:1;io_uncache_idResp_bits_mid:i:7;io_uncache_idResp_bits_sid:i:4;io_uncache_resp_valid:i:1;io_uncache_resp_bits_data:i:64;io_uncache_resp_bits_denied:i:1;io_uncache_resp_bits_corrupt:i:1;io_exception_valid:o:1;io_exception_bits_uop_exceptionVec_3:o:1;io_exception_bits_uop_exceptionVec_4:o:1;io_exception_bits_uop_exceptionVec_5:o:1;io_exception_bits_uop_exceptionVec_13:o:1;io_exception_bits_uop_exceptionVec_19:o:1;io_exception_bits_uop_exceptionVec_21:o:1;io_exception_bits_uop_uopIdx:o:7;io_exception_bits_uop_robIdx_flag:o:1;io_exception_bits_uop_robIdx_value:o:8;io_exception_bits_fullva:o:64;io_exception_bits_gpaddr:o:64;io_exception_bits_isHyper:o:1;io_exception_bits_isForVSnonLeafPTE:o:1",
    "UncacheEntry_5|entry|slaveId=5|clock:i:1;reset:i:1;io_redirect_valid:i:1;io_redirect_bits_robIdx_flag:i:1;io_redirect_bits_robIdx_value:i:8;io_redirect_bits_level:i:1;io_flush:o:1;io_rob_pendingMMIOld:i:1;io_rob_pendingPtr_flag:i:1;io_rob_pendingPtr_value:i:8;io_mmioSelect:o:1;io_slaveId_valid:o:1;io_slaveId_bits:o:4;io_req_valid:i:1;io_req_bits_uop_exceptionVec_3:i:1;io_req_bits_uop_exceptionVec_4:i:1;io_req_bits_uop_exceptionVec_13:i:1;io_req_bits_uop_exceptionVec_21:i:1;io_req_bits_uop_trigger:i:4;io_req_bits_uop_preDecodeInfo_isRVC:i:1;io_req_bits_uop_ftqPtr_flag:i:1;io_req_bits_uop_ftqPtr_value:i:6;io_req_bits_uop_ftqOffset:i:4;io_req_bits_uop_fuOpType:i:9;io_req_bits_uop_rfWen:i:1;io_req_bits_uop_fpWen:i:1;io_req_bits_uop_vpu_vstart:i:8;io_req_bits_uop_vpu_veew:i:2;io_req_bits_uop_uopIdx:i:7;io_req_bits_uop_pdest:i:8;io_req_bits_uop_robIdx_flag:i:1;io_req_bits_uop_robIdx_value:i:8;io_req_bits_uop_storeSetHit:i:1;io_req_bits_uop_waitForRobIdx_flag:i:1;io_req_bits_uop_waitForRobIdx_value:i:8;io_req_bits_uop_loadWaitBit:i:1;io_req_bits_uop_loadWaitStrict:i:1;io_req_bits_uop_lqIdx_flag:i:1;io_req_bits_uop_lqIdx_value:i:7;io_req_bits_uop_sqIdx_flag:i:1;io_req_bits_uop_sqIdx_value:i:6;io_req_bits_vaddr:i:50;io_req_bits_fullva:i:64;io_req_bits_paddr:i:48;io_req_bits_gpaddr:i:64;io_req_bits_mask:i:16;io_req_bits_nc:i:1;io_req_bits_mmio:i:1;io_req_bits_memBackTypeMM:i:1;io_req_bits_isHyper:i:1;io_req_bits_isForVSnonLeafPTE:i:1;io_req_bits_isvec:i:1;io_req_bits_is128bit:i:1;io_req_bits_vecActive:i:1;io_req_bits_schedIndex:i:7;io_mmioOut_ready:i:1;io_mmioOut_valid:o:1;io_mmioOut_bits_uop_exceptionVec_3:o:1;io_mmioOut_bits_uop_exceptionVec_4:o:1;io_mmioOut_bits_uop_exceptionVec_5:o:1;io_mmioOut_bits_uop_exceptionVec_13:o:1;io_mmioOut_bits_uop_exceptionVec_19:o:1;io_mmioOut_bits_uop_exceptionVec_21:o:1;io_mmioOut_bits_uop_trigger:o:4;io_mmioOut_bits_uop_preDecodeInfo_isRVC:o:1;io_mmioOut_bits_uop_ftqPtr_flag:o:1;io_mmioOut_bits_uop_ftqPtr_value:o:6;io_mmioOut_bits_uop_ftqOffset:o:4;io_mmioOut_bits_uop_fuOpType:o:9;io_mmioOut_bits_uop_rfWen:o:1;io_mmioOut_bits_uop_fpWen:o:1;io_mmioOut_bits_uop_flushPipe:o:1;io_mmioOut_bits_uop_vpu_vstart:o:8;io_mmioOut_bits_uop_vpu_veew:o:2;io_mmioOut_bits_uop_uopIdx:o:7;io_mmioOut_bits_uop_pdest:o:8;io_mmioOut_bits_uop_robIdx_flag:o:1;io_mmioOut_bits_uop_robIdx_value:o:8;io_mmioOut_bits_uop_storeSetHit:o:1;io_mmioOut_bits_uop_waitForRobIdx_flag:o:1;io_mmioOut_bits_uop_waitForRobIdx_value:o:8;io_mmioOut_bits_uop_loadWaitBit:o:1;io_mmioOut_bits_uop_loadWaitStrict:o:1;io_mmioOut_bits_uop_lqIdx_flag:o:1;io_mmioOut_bits_uop_lqIdx_value:o:7;io_mmioOut_bits_uop_sqIdx_flag:o:1;io_mmioOut_bits_uop_sqIdx_value:o:6;io_mmioOut_bits_uop_replayInst:o:1;io_mmioRawData_lqData:o:64;io_mmioRawData_uop_fuOpType:o:9;io_mmioRawData_uop_fpWen:o:1;io_mmioRawData_addrOffset:o:3;io_ncOut_ready:i:1;io_ncOut_valid:o:1;io_ncOut_bits_uop_exceptionVec_4:o:1;io_ncOut_bits_uop_exceptionVec_19:o:1;io_ncOut_bits_uop_preDecodeInfo_isRVC:o:1;io_ncOut_bits_uop_ftqPtr_flag:o:1;io_ncOut_bits_uop_ftqPtr_value:o:6;io_ncOut_bits_uop_ftqOffset:o:4;io_ncOut_bits_uop_fuOpType:o:9;io_ncOut_bits_uop_rfWen:o:1;io_ncOut_bits_uop_fpWen:o:1;io_ncOut_bits_uop_vpu_vstart:o:8;io_ncOut_bits_uop_vpu_veew:o:2;io_ncOut_bits_uop_uopIdx:o:7;io_ncOut_bits_uop_pdest:o:8;io_ncOut_bits_uop_robIdx_flag:o:1;io_ncOut_bits_uop_robIdx_value:o:8;io_ncOut_bits_uop_storeSetHit:o:1;io_ncOut_bits_uop_waitForRobIdx_flag:o:1;io_ncOut_bits_uop_waitForRobIdx_value:o:8;io_ncOut_bits_uop_loadWaitBit:o:1;io_ncOut_bits_uop_loadWaitStrict:o:1;io_ncOut_bits_uop_lqIdx_flag:o:1;io_ncOut_bits_uop_lqIdx_value:o:7;io_ncOut_bits_uop_sqIdx_flag:o:1;io_ncOut_bits_uop_sqIdx_value:o:6;io_ncOut_bits_vaddr:o:50;io_ncOut_bits_paddr:o:48;io_ncOut_bits_data:o:129;io_ncOut_bits_isvec:o:1;io_ncOut_bits_is128bit:o:1;io_ncOut_bits_vecActive:o:1;io_ncOut_bits_schedIndex:o:7;io_uncache_req_ready:i:1;io_uncache_req_valid:o:1;io_uncache_req_bits_robIdx_flag:o:1;io_uncache_req_bits_robIdx_value:o:8;io_uncache_req_bits_addr:o:48;io_uncache_req_bits_vaddr:o:50;io_uncache_req_bits_mask:o:8;io_uncache_req_bits_nc:o:1;io_uncache_req_bits_memBackTypeMM:o:1;io_uncache_idResp_valid:i:1;io_uncache_idResp_bits_mid:i:7;io_uncache_idResp_bits_sid:i:4;io_uncache_resp_valid:i:1;io_uncache_resp_bits_data:i:64;io_uncache_resp_bits_denied:i:1;io_uncache_resp_bits_corrupt:i:1;io_exception_valid:o:1;io_exception_bits_uop_exceptionVec_3:o:1;io_exception_bits_uop_exceptionVec_4:o:1;io_exception_bits_uop_exceptionVec_5:o:1;io_exception_bits_uop_exceptionVec_13:o:1;io_exception_bits_uop_exceptionVec_19:o:1;io_exception_bits_uop_exceptionVec_21:o:1;io_exception_bits_uop_uopIdx:o:7;io_exception_bits_uop_robIdx_flag:o:1;io_exception_bits_uop_robIdx_value:o:8;io_exception_bits_fullva:o:64;io_exception_bits_gpaddr:o:64;io_exception_bits_isHyper:o:1;io_exception_bits_isForVSnonLeafPTE:o:1",
    "UncacheEntry_6|entry|slaveId=6|clock:i:1;reset:i:1;io_redirect_valid:i:1;io_redirect_bits_robIdx_flag:i:1;io_redirect_bits_robIdx_value:i:8;io_redirect_bits_level:i:1;io_flush:o:1;io_rob_pendingMMIOld:i:1;io_rob_pendingPtr_flag:i:1;io_rob_pendingPtr_value:i:8;io_mmioSelect:o:1;io_slaveId_valid:o:1;io_slaveId_bits:o:4;io_req_valid:i:1;io_req_bits_uop_exceptionVec_3:i:1;io_req_bits_uop_exceptionVec_4:i:1;io_req_bits_uop_exceptionVec_13:i:1;io_req_bits_uop_exceptionVec_21:i:1;io_req_bits_uop_trigger:i:4;io_req_bits_uop_preDecodeInfo_isRVC:i:1;io_req_bits_uop_ftqPtr_flag:i:1;io_req_bits_uop_ftqPtr_value:i:6;io_req_bits_uop_ftqOffset:i:4;io_req_bits_uop_fuOpType:i:9;io_req_bits_uop_rfWen:i:1;io_req_bits_uop_fpWen:i:1;io_req_bits_uop_vpu_vstart:i:8;io_req_bits_uop_vpu_veew:i:2;io_req_bits_uop_uopIdx:i:7;io_req_bits_uop_pdest:i:8;io_req_bits_uop_robIdx_flag:i:1;io_req_bits_uop_robIdx_value:i:8;io_req_bits_uop_storeSetHit:i:1;io_req_bits_uop_waitForRobIdx_flag:i:1;io_req_bits_uop_waitForRobIdx_value:i:8;io_req_bits_uop_loadWaitBit:i:1;io_req_bits_uop_loadWaitStrict:i:1;io_req_bits_uop_lqIdx_flag:i:1;io_req_bits_uop_lqIdx_value:i:7;io_req_bits_uop_sqIdx_flag:i:1;io_req_bits_uop_sqIdx_value:i:6;io_req_bits_vaddr:i:50;io_req_bits_fullva:i:64;io_req_bits_paddr:i:48;io_req_bits_gpaddr:i:64;io_req_bits_mask:i:16;io_req_bits_nc:i:1;io_req_bits_mmio:i:1;io_req_bits_memBackTypeMM:i:1;io_req_bits_isHyper:i:1;io_req_bits_isForVSnonLeafPTE:i:1;io_req_bits_isvec:i:1;io_req_bits_is128bit:i:1;io_req_bits_vecActive:i:1;io_req_bits_schedIndex:i:7;io_mmioOut_ready:i:1;io_mmioOut_valid:o:1;io_mmioOut_bits_uop_exceptionVec_3:o:1;io_mmioOut_bits_uop_exceptionVec_4:o:1;io_mmioOut_bits_uop_exceptionVec_5:o:1;io_mmioOut_bits_uop_exceptionVec_13:o:1;io_mmioOut_bits_uop_exceptionVec_19:o:1;io_mmioOut_bits_uop_exceptionVec_21:o:1;io_mmioOut_bits_uop_trigger:o:4;io_mmioOut_bits_uop_preDecodeInfo_isRVC:o:1;io_mmioOut_bits_uop_ftqPtr_flag:o:1;io_mmioOut_bits_uop_ftqPtr_value:o:6;io_mmioOut_bits_uop_ftqOffset:o:4;io_mmioOut_bits_uop_fuOpType:o:9;io_mmioOut_bits_uop_rfWen:o:1;io_mmioOut_bits_uop_fpWen:o:1;io_mmioOut_bits_uop_flushPipe:o:1;io_mmioOut_bits_uop_vpu_vstart:o:8;io_mmioOut_bits_uop_vpu_veew:o:2;io_mmioOut_bits_uop_uopIdx:o:7;io_mmioOut_bits_uop_pdest:o:8;io_mmioOut_bits_uop_robIdx_flag:o:1;io_mmioOut_bits_uop_robIdx_value:o:8;io_mmioOut_bits_uop_storeSetHit:o:1;io_mmioOut_bits_uop_waitForRobIdx_flag:o:1;io_mmioOut_bits_uop_waitForRobIdx_value:o:8;io_mmioOut_bits_uop_loadWaitBit:o:1;io_mmioOut_bits_uop_loadWaitStrict:o:1;io_mmioOut_bits_uop_lqIdx_flag:o:1;io_mmioOut_bits_uop_lqIdx_value:o:7;io_mmioOut_bits_uop_sqIdx_flag:o:1;io_mmioOut_bits_uop_sqIdx_value:o:6;io_mmioOut_bits_uop_replayInst:o:1;io_mmioRawData_lqData:o:64;io_mmioRawData_uop_fuOpType:o:9;io_mmioRawData_uop_fpWen:o:1;io_mmioRawData_addrOffset:o:3;io_ncOut_ready:i:1;io_ncOut_valid:o:1;io_ncOut_bits_uop_exceptionVec_4:o:1;io_ncOut_bits_uop_exceptionVec_19:o:1;io_ncOut_bits_uop_preDecodeInfo_isRVC:o:1;io_ncOut_bits_uop_ftqPtr_flag:o:1;io_ncOut_bits_uop_ftqPtr_value:o:6;io_ncOut_bits_uop_ftqOffset:o:4;io_ncOut_bits_uop_fuOpType:o:9;io_ncOut_bits_uop_rfWen:o:1;io_ncOut_bits_uop_fpWen:o:1;io_ncOut_bits_uop_vpu_vstart:o:8;io_ncOut_bits_uop_vpu_veew:o:2;io_ncOut_bits_uop_uopIdx:o:7;io_ncOut_bits_uop_pdest:o:8;io_ncOut_bits_uop_robIdx_flag:o:1;io_ncOut_bits_uop_robIdx_value:o:8;io_ncOut_bits_uop_storeSetHit:o:1;io_ncOut_bits_uop_waitForRobIdx_flag:o:1;io_ncOut_bits_uop_waitForRobIdx_value:o:8;io_ncOut_bits_uop_loadWaitBit:o:1;io_ncOut_bits_uop_loadWaitStrict:o:1;io_ncOut_bits_uop_lqIdx_flag:o:1;io_ncOut_bits_uop_lqIdx_value:o:7;io_ncOut_bits_uop_sqIdx_flag:o:1;io_ncOut_bits_uop_sqIdx_value:o:6;io_ncOut_bits_vaddr:o:50;io_ncOut_bits_paddr:o:48;io_ncOut_bits_data:o:129;io_ncOut_bits_isvec:o:1;io_ncOut_bits_is128bit:o:1;io_ncOut_bits_vecActive:o:1;io_ncOut_bits_schedIndex:o:7;io_uncache_req_ready:i:1;io_uncache_req_valid:o:1;io_uncache_req_bits_robIdx_flag:o:1;io_uncache_req_bits_robIdx_value:o:8;io_uncache_req_bits_addr:o:48;io_uncache_req_bits_vaddr:o:50;io_uncache_req_bits_mask:o:8;io_uncache_req_bits_nc:o:1;io_uncache_req_bits_memBackTypeMM:o:1;io_uncache_idResp_valid:i:1;io_uncache_idResp_bits_mid:i:7;io_uncache_idResp_bits_sid:i:4;io_uncache_resp_valid:i:1;io_uncache_resp_bits_data:i:64;io_uncache_resp_bits_denied:i:1;io_uncache_resp_bits_corrupt:i:1;io_exception_valid:o:1;io_exception_bits_uop_exceptionVec_3:o:1;io_exception_bits_uop_exceptionVec_4:o:1;io_exception_bits_uop_exceptionVec_5:o:1;io_exception_bits_uop_exceptionVec_13:o:1;io_exception_bits_uop_exceptionVec_19:o:1;io_exception_bits_uop_exceptionVec_21:o:1;io_exception_bits_uop_uopIdx:o:7;io_exception_bits_uop_robIdx_flag:o:1;io_exception_bits_uop_robIdx_value:o:8;io_exception_bits_fullva:o:64;io_exception_bits_gpaddr:o:64;io_exception_bits_isHyper:o:1;io_exception_bits_isForVSnonLeafPTE:o:1",
    "UncacheEntry_7|entry|slaveId=7|clock:i:1;reset:i:1;io_redirect_valid:i:1;io_redirect_bits_robIdx_flag:i:1;io_redirect_bits_robIdx_value:i:8;io_redirect_bits_level:i:1;io_flush:o:1;io_rob_pendingMMIOld:i:1;io_rob_pendingPtr_flag:i:1;io_rob_pendingPtr_value:i:8;io_mmioSelect:o:1;io_slaveId_valid:o:1;io_slaveId_bits:o:4;io_req_valid:i:1;io_req_bits_uop_exceptionVec_3:i:1;io_req_bits_uop_exceptionVec_4:i:1;io_req_bits_uop_exceptionVec_13:i:1;io_req_bits_uop_exceptionVec_21:i:1;io_req_bits_uop_trigger:i:4;io_req_bits_uop_preDecodeInfo_isRVC:i:1;io_req_bits_uop_ftqPtr_flag:i:1;io_req_bits_uop_ftqPtr_value:i:6;io_req_bits_uop_ftqOffset:i:4;io_req_bits_uop_fuOpType:i:9;io_req_bits_uop_rfWen:i:1;io_req_bits_uop_fpWen:i:1;io_req_bits_uop_vpu_vstart:i:8;io_req_bits_uop_vpu_veew:i:2;io_req_bits_uop_uopIdx:i:7;io_req_bits_uop_pdest:i:8;io_req_bits_uop_robIdx_flag:i:1;io_req_bits_uop_robIdx_value:i:8;io_req_bits_uop_storeSetHit:i:1;io_req_bits_uop_waitForRobIdx_flag:i:1;io_req_bits_uop_waitForRobIdx_value:i:8;io_req_bits_uop_loadWaitBit:i:1;io_req_bits_uop_loadWaitStrict:i:1;io_req_bits_uop_lqIdx_flag:i:1;io_req_bits_uop_lqIdx_value:i:7;io_req_bits_uop_sqIdx_flag:i:1;io_req_bits_uop_sqIdx_value:i:6;io_req_bits_vaddr:i:50;io_req_bits_fullva:i:64;io_req_bits_paddr:i:48;io_req_bits_gpaddr:i:64;io_req_bits_mask:i:16;io_req_bits_nc:i:1;io_req_bits_mmio:i:1;io_req_bits_memBackTypeMM:i:1;io_req_bits_isHyper:i:1;io_req_bits_isForVSnonLeafPTE:i:1;io_req_bits_isvec:i:1;io_req_bits_is128bit:i:1;io_req_bits_vecActive:i:1;io_req_bits_schedIndex:i:7;io_mmioOut_ready:i:1;io_mmioOut_valid:o:1;io_mmioOut_bits_uop_exceptionVec_3:o:1;io_mmioOut_bits_uop_exceptionVec_4:o:1;io_mmioOut_bits_uop_exceptionVec_5:o:1;io_mmioOut_bits_uop_exceptionVec_13:o:1;io_mmioOut_bits_uop_exceptionVec_19:o:1;io_mmioOut_bits_uop_exceptionVec_21:o:1;io_mmioOut_bits_uop_trigger:o:4;io_mmioOut_bits_uop_preDecodeInfo_isRVC:o:1;io_mmioOut_bits_uop_ftqPtr_flag:o:1;io_mmioOut_bits_uop_ftqPtr_value:o:6;io_mmioOut_bits_uop_ftqOffset:o:4;io_mmioOut_bits_uop_fuOpType:o:9;io_mmioOut_bits_uop_rfWen:o:1;io_mmioOut_bits_uop_fpWen:o:1;io_mmioOut_bits_uop_flushPipe:o:1;io_mmioOut_bits_uop_vpu_vstart:o:8;io_mmioOut_bits_uop_vpu_veew:o:2;io_mmioOut_bits_uop_uopIdx:o:7;io_mmioOut_bits_uop_pdest:o:8;io_mmioOut_bits_uop_robIdx_flag:o:1;io_mmioOut_bits_uop_robIdx_value:o:8;io_mmioOut_bits_uop_storeSetHit:o:1;io_mmioOut_bits_uop_waitForRobIdx_flag:o:1;io_mmioOut_bits_uop_waitForRobIdx_value:o:8;io_mmioOut_bits_uop_loadWaitBit:o:1;io_mmioOut_bits_uop_loadWaitStrict:o:1;io_mmioOut_bits_uop_lqIdx_flag:o:1;io_mmioOut_bits_uop_lqIdx_value:o:7;io_mmioOut_bits_uop_sqIdx_flag:o:1;io_mmioOut_bits_uop_sqIdx_value:o:6;io_mmioOut_bits_uop_replayInst:o:1;io_mmioRawData_lqData:o:64;io_mmioRawData_uop_fuOpType:o:9;io_mmioRawData_uop_fpWen:o:1;io_mmioRawData_addrOffset:o:3;io_ncOut_ready:i:1;io_ncOut_valid:o:1;io_ncOut_bits_uop_exceptionVec_4:o:1;io_ncOut_bits_uop_exceptionVec_19:o:1;io_ncOut_bits_uop_preDecodeInfo_isRVC:o:1;io_ncOut_bits_uop_ftqPtr_flag:o:1;io_ncOut_bits_uop_ftqPtr_value:o:6;io_ncOut_bits_uop_ftqOffset:o:4;io_ncOut_bits_uop_fuOpType:o:9;io_ncOut_bits_uop_rfWen:o:1;io_ncOut_bits_uop_fpWen:o:1;io_ncOut_bits_uop_vpu_vstart:o:8;io_ncOut_bits_uop_vpu_veew:o:2;io_ncOut_bits_uop_uopIdx:o:7;io_ncOut_bits_uop_pdest:o:8;io_ncOut_bits_uop_robIdx_flag:o:1;io_ncOut_bits_uop_robIdx_value:o:8;io_ncOut_bits_uop_storeSetHit:o:1;io_ncOut_bits_uop_waitForRobIdx_flag:o:1;io_ncOut_bits_uop_waitForRobIdx_value:o:8;io_ncOut_bits_uop_loadWaitBit:o:1;io_ncOut_bits_uop_loadWaitStrict:o:1;io_ncOut_bits_uop_lqIdx_flag:o:1;io_ncOut_bits_uop_lqIdx_value:o:7;io_ncOut_bits_uop_sqIdx_flag:o:1;io_ncOut_bits_uop_sqIdx_value:o:6;io_ncOut_bits_vaddr:o:50;io_ncOut_bits_paddr:o:48;io_ncOut_bits_data:o:129;io_ncOut_bits_isvec:o:1;io_ncOut_bits_is128bit:o:1;io_ncOut_bits_vecActive:o:1;io_ncOut_bits_schedIndex:o:7;io_uncache_req_ready:i:1;io_uncache_req_valid:o:1;io_uncache_req_bits_robIdx_flag:o:1;io_uncache_req_bits_robIdx_value:o:8;io_uncache_req_bits_addr:o:48;io_uncache_req_bits_vaddr:o:50;io_uncache_req_bits_mask:o:8;io_uncache_req_bits_nc:o:1;io_uncache_req_bits_memBackTypeMM:o:1;io_uncache_idResp_valid:i:1;io_uncache_idResp_bits_mid:i:7;io_uncache_idResp_bits_sid:i:4;io_uncache_resp_valid:i:1;io_uncache_resp_bits_data:i:64;io_uncache_resp_bits_denied:i:1;io_uncache_resp_bits_corrupt:i:1;io_exception_valid:o:1;io_exception_bits_uop_exceptionVec_3:o:1;io_exception_bits_uop_exceptionVec_4:o:1;io_exception_bits_uop_exceptionVec_5:o:1;io_exception_bits_uop_exceptionVec_13:o:1;io_exception_bits_uop_exceptionVec_19:o:1;io_exception_bits_uop_exceptionVec_21:o:1;io_exception_bits_uop_uopIdx:o:7;io_exception_bits_uop_robIdx_flag:o:1;io_exception_bits_uop_robIdx_value:o:8;io_exception_bits_fullva:o:64;io_exception_bits_gpaddr:o:64;io_exception_bits_isHyper:o:1;io_exception_bits_isForVSnonLeafPTE:o:1",
    "UncacheEntry_8|entry|slaveId=8|clock:i:1;reset:i:1;io_redirect_valid:i:1;io_redirect_bits_robIdx_flag:i:1;io_redirect_bits_robIdx_value:i:8;io_redirect_bits_level:i:1;io_flush:o:1;io_rob_pendingMMIOld:i:1;io_rob_pendingPtr_flag:i:1;io_rob_pendingPtr_value:i:8;io_mmioSelect:o:1;io_slaveId_valid:o:1;io_slaveId_bits:o:4;io_req_valid:i:1;io_req_bits_uop_exceptionVec_3:i:1;io_req_bits_uop_exceptionVec_4:i:1;io_req_bits_uop_exceptionVec_13:i:1;io_req_bits_uop_exceptionVec_21:i:1;io_req_bits_uop_trigger:i:4;io_req_bits_uop_preDecodeInfo_isRVC:i:1;io_req_bits_uop_ftqPtr_flag:i:1;io_req_bits_uop_ftqPtr_value:i:6;io_req_bits_uop_ftqOffset:i:4;io_req_bits_uop_fuOpType:i:9;io_req_bits_uop_rfWen:i:1;io_req_bits_uop_fpWen:i:1;io_req_bits_uop_vpu_vstart:i:8;io_req_bits_uop_vpu_veew:i:2;io_req_bits_uop_uopIdx:i:7;io_req_bits_uop_pdest:i:8;io_req_bits_uop_robIdx_flag:i:1;io_req_bits_uop_robIdx_value:i:8;io_req_bits_uop_storeSetHit:i:1;io_req_bits_uop_waitForRobIdx_flag:i:1;io_req_bits_uop_waitForRobIdx_value:i:8;io_req_bits_uop_loadWaitBit:i:1;io_req_bits_uop_loadWaitStrict:i:1;io_req_bits_uop_lqIdx_flag:i:1;io_req_bits_uop_lqIdx_value:i:7;io_req_bits_uop_sqIdx_flag:i:1;io_req_bits_uop_sqIdx_value:i:6;io_req_bits_vaddr:i:50;io_req_bits_fullva:i:64;io_req_bits_paddr:i:48;io_req_bits_gpaddr:i:64;io_req_bits_mask:i:16;io_req_bits_nc:i:1;io_req_bits_mmio:i:1;io_req_bits_memBackTypeMM:i:1;io_req_bits_isHyper:i:1;io_req_bits_isForVSnonLeafPTE:i:1;io_req_bits_isvec:i:1;io_req_bits_is128bit:i:1;io_req_bits_vecActive:i:1;io_req_bits_schedIndex:i:7;io_mmioOut_ready:i:1;io_mmioOut_valid:o:1;io_mmioOut_bits_uop_exceptionVec_3:o:1;io_mmioOut_bits_uop_exceptionVec_4:o:1;io_mmioOut_bits_uop_exceptionVec_5:o:1;io_mmioOut_bits_uop_exceptionVec_13:o:1;io_mmioOut_bits_uop_exceptionVec_19:o:1;io_mmioOut_bits_uop_exceptionVec_21:o:1;io_mmioOut_bits_uop_trigger:o:4;io_mmioOut_bits_uop_preDecodeInfo_isRVC:o:1;io_mmioOut_bits_uop_ftqPtr_flag:o:1;io_mmioOut_bits_uop_ftqPtr_value:o:6;io_mmioOut_bits_uop_ftqOffset:o:4;io_mmioOut_bits_uop_fuOpType:o:9;io_mmioOut_bits_uop_rfWen:o:1;io_mmioOut_bits_uop_fpWen:o:1;io_mmioOut_bits_uop_flushPipe:o:1;io_mmioOut_bits_uop_vpu_vstart:o:8;io_mmioOut_bits_uop_vpu_veew:o:2;io_mmioOut_bits_uop_uopIdx:o:7;io_mmioOut_bits_uop_pdest:o:8;io_mmioOut_bits_uop_robIdx_flag:o:1;io_mmioOut_bits_uop_robIdx_value:o:8;io_mmioOut_bits_uop_storeSetHit:o:1;io_mmioOut_bits_uop_waitForRobIdx_flag:o:1;io_mmioOut_bits_uop_waitForRobIdx_value:o:8;io_mmioOut_bits_uop_loadWaitBit:o:1;io_mmioOut_bits_uop_loadWaitStrict:o:1;io_mmioOut_bits_uop_lqIdx_flag:o:1;io_mmioOut_bits_uop_lqIdx_value:o:7;io_mmioOut_bits_uop_sqIdx_flag:o:1;io_mmioOut_bits_uop_sqIdx_value:o:6;io_mmioOut_bits_uop_replayInst:o:1;io_mmioRawData_lqData:o:64;io_mmioRawData_uop_fuOpType:o:9;io_mmioRawData_uop_fpWen:o:1;io_mmioRawData_addrOffset:o:3;io_ncOut_ready:i:1;io_ncOut_valid:o:1;io_ncOut_bits_uop_exceptionVec_4:o:1;io_ncOut_bits_uop_exceptionVec_19:o:1;io_ncOut_bits_uop_preDecodeInfo_isRVC:o:1;io_ncOut_bits_uop_ftqPtr_flag:o:1;io_ncOut_bits_uop_ftqPtr_value:o:6;io_ncOut_bits_uop_ftqOffset:o:4;io_ncOut_bits_uop_fuOpType:o:9;io_ncOut_bits_uop_rfWen:o:1;io_ncOut_bits_uop_fpWen:o:1;io_ncOut_bits_uop_vpu_vstart:o:8;io_ncOut_bits_uop_vpu_veew:o:2;io_ncOut_bits_uop_uopIdx:o:7;io_ncOut_bits_uop_pdest:o:8;io_ncOut_bits_uop_robIdx_flag:o:1;io_ncOut_bits_uop_robIdx_value:o:8;io_ncOut_bits_uop_storeSetHit:o:1;io_ncOut_bits_uop_waitForRobIdx_flag:o:1;io_ncOut_bits_uop_waitForRobIdx_value:o:8;io_ncOut_bits_uop_loadWaitBit:o:1;io_ncOut_bits_uop_loadWaitStrict:o:1;io_ncOut_bits_uop_lqIdx_flag:o:1;io_ncOut_bits_uop_lqIdx_value:o:7;io_ncOut_bits_uop_sqIdx_flag:o:1;io_ncOut_bits_uop_sqIdx_value:o:6;io_ncOut_bits_vaddr:o:50;io_ncOut_bits_paddr:o:48;io_ncOut_bits_data:o:129;io_ncOut_bits_isvec:o:1;io_ncOut_bits_is128bit:o:1;io_ncOut_bits_vecActive:o:1;io_ncOut_bits_schedIndex:o:7;io_uncache_req_ready:i:1;io_uncache_req_valid:o:1;io_uncache_req_bits_robIdx_flag:o:1;io_uncache_req_bits_robIdx_value:o:8;io_uncache_req_bits_addr:o:48;io_uncache_req_bits_vaddr:o:50;io_uncache_req_bits_mask:o:8;io_uncache_req_bits_nc:o:1;io_uncache_req_bits_memBackTypeMM:o:1;io_uncache_idResp_valid:i:1;io_uncache_idResp_bits_mid:i:7;io_uncache_idResp_bits_sid:i:4;io_uncache_resp_valid:i:1;io_uncache_resp_bits_data:i:64;io_uncache_resp_bits_denied:i:1;io_uncache_resp_bits_corrupt:i:1;io_exception_valid:o:1;io_exception_bits_uop_exceptionVec_3:o:1;io_exception_bits_uop_exceptionVec_4:o:1;io_exception_bits_uop_exceptionVec_5:o:1;io_exception_bits_uop_exceptionVec_13:o:1;io_exception_bits_uop_exceptionVec_19:o:1;io_exception_bits_uop_exceptionVec_21:o:1;io_exception_bits_uop_uopIdx:o:7;io_exception_bits_uop_robIdx_flag:o:1;io_exception_bits_uop_robIdx_value:o:8;io_exception_bits_fullva:o:64;io_exception_bits_gpaddr:o:64;io_exception_bits_isHyper:o:1;io_exception_bits_isForVSnonLeafPTE:o:1",
    "UncacheEntry_9|entry|slaveId=9|clock:i:1;reset:i:1;io_redirect_valid:i:1;io_redirect_bits_robIdx_flag:i:1;io_redirect_bits_robIdx_value:i:8;io_redirect_bits_level:i:1;io_flush:o:1;io_rob_pendingMMIOld:i:1;io_rob_pendingPtr_flag:i:1;io_rob_pendingPtr_value:i:8;io_mmioSelect:o:1;io_slaveId_valid:o:1;io_slaveId_bits:o:4;io_req_valid:i:1;io_req_bits_uop_exceptionVec_3:i:1;io_req_bits_uop_exceptionVec_4:i:1;io_req_bits_uop_exceptionVec_13:i:1;io_req_bits_uop_exceptionVec_21:i:1;io_req_bits_uop_trigger:i:4;io_req_bits_uop_preDecodeInfo_isRVC:i:1;io_req_bits_uop_ftqPtr_flag:i:1;io_req_bits_uop_ftqPtr_value:i:6;io_req_bits_uop_ftqOffset:i:4;io_req_bits_uop_fuOpType:i:9;io_req_bits_uop_rfWen:i:1;io_req_bits_uop_fpWen:i:1;io_req_bits_uop_vpu_vstart:i:8;io_req_bits_uop_vpu_veew:i:2;io_req_bits_uop_uopIdx:i:7;io_req_bits_uop_pdest:i:8;io_req_bits_uop_robIdx_flag:i:1;io_req_bits_uop_robIdx_value:i:8;io_req_bits_uop_storeSetHit:i:1;io_req_bits_uop_waitForRobIdx_flag:i:1;io_req_bits_uop_waitForRobIdx_value:i:8;io_req_bits_uop_loadWaitBit:i:1;io_req_bits_uop_loadWaitStrict:i:1;io_req_bits_uop_lqIdx_flag:i:1;io_req_bits_uop_lqIdx_value:i:7;io_req_bits_uop_sqIdx_flag:i:1;io_req_bits_uop_sqIdx_value:i:6;io_req_bits_vaddr:i:50;io_req_bits_fullva:i:64;io_req_bits_paddr:i:48;io_req_bits_gpaddr:i:64;io_req_bits_mask:i:16;io_req_bits_nc:i:1;io_req_bits_mmio:i:1;io_req_bits_memBackTypeMM:i:1;io_req_bits_isHyper:i:1;io_req_bits_isForVSnonLeafPTE:i:1;io_req_bits_isvec:i:1;io_req_bits_is128bit:i:1;io_req_bits_vecActive:i:1;io_req_bits_schedIndex:i:7;io_mmioOut_ready:i:1;io_mmioOut_valid:o:1;io_mmioOut_bits_uop_exceptionVec_3:o:1;io_mmioOut_bits_uop_exceptionVec_4:o:1;io_mmioOut_bits_uop_exceptionVec_5:o:1;io_mmioOut_bits_uop_exceptionVec_13:o:1;io_mmioOut_bits_uop_exceptionVec_19:o:1;io_mmioOut_bits_uop_exceptionVec_21:o:1;io_mmioOut_bits_uop_trigger:o:4;io_mmioOut_bits_uop_preDecodeInfo_isRVC:o:1;io_mmioOut_bits_uop_ftqPtr_flag:o:1;io_mmioOut_bits_uop_ftqPtr_value:o:6;io_mmioOut_bits_uop_ftqOffset:o:4;io_mmioOut_bits_uop_fuOpType:o:9;io_mmioOut_bits_uop_rfWen:o:1;io_mmioOut_bits_uop_fpWen:o:1;io_mmioOut_bits_uop_flushPipe:o:1;io_mmioOut_bits_uop_vpu_vstart:o:8;io_mmioOut_bits_uop_vpu_veew:o:2;io_mmioOut_bits_uop_uopIdx:o:7;io_mmioOut_bits_uop_pdest:o:8;io_mmioOut_bits_uop_robIdx_flag:o:1;io_mmioOut_bits_uop_robIdx_value:o:8;io_mmioOut_bits_uop_storeSetHit:o:1;io_mmioOut_bits_uop_waitForRobIdx_flag:o:1;io_mmioOut_bits_uop_waitForRobIdx_value:o:8;io_mmioOut_bits_uop_loadWaitBit:o:1;io_mmioOut_bits_uop_loadWaitStrict:o:1;io_mmioOut_bits_uop_lqIdx_flag:o:1;io_mmioOut_bits_uop_lqIdx_value:o:7;io_mmioOut_bits_uop_sqIdx_flag:o:1;io_mmioOut_bits_uop_sqIdx_value:o:6;io_mmioOut_bits_uop_replayInst:o:1;io_mmioRawData_lqData:o:64;io_mmioRawData_uop_fuOpType:o:9;io_mmioRawData_uop_fpWen:o:1;io_mmioRawData_addrOffset:o:3;io_ncOut_ready:i:1;io_ncOut_valid:o:1;io_ncOut_bits_uop_exceptionVec_4:o:1;io_ncOut_bits_uop_exceptionVec_19:o:1;io_ncOut_bits_uop_preDecodeInfo_isRVC:o:1;io_ncOut_bits_uop_ftqPtr_flag:o:1;io_ncOut_bits_uop_ftqPtr_value:o:6;io_ncOut_bits_uop_ftqOffset:o:4;io_ncOut_bits_uop_fuOpType:o:9;io_ncOut_bits_uop_rfWen:o:1;io_ncOut_bits_uop_fpWen:o:1;io_ncOut_bits_uop_vpu_vstart:o:8;io_ncOut_bits_uop_vpu_veew:o:2;io_ncOut_bits_uop_uopIdx:o:7;io_ncOut_bits_uop_pdest:o:8;io_ncOut_bits_uop_robIdx_flag:o:1;io_ncOut_bits_uop_robIdx_value:o:8;io_ncOut_bits_uop_storeSetHit:o:1;io_ncOut_bits_uop_waitForRobIdx_flag:o:1;io_ncOut_bits_uop_waitForRobIdx_value:o:8;io_ncOut_bits_uop_loadWaitBit:o:1;io_ncOut_bits_uop_loadWaitStrict:o:1;io_ncOut_bits_uop_lqIdx_flag:o:1;io_ncOut_bits_uop_lqIdx_value:o:7;io_ncOut_bits_uop_sqIdx_flag:o:1;io_ncOut_bits_uop_sqIdx_value:o:6;io_ncOut_bits_vaddr:o:50;io_ncOut_bits_paddr:o:48;io_ncOut_bits_data:o:129;io_ncOut_bits_isvec:o:1;io_ncOut_bits_is128bit:o:1;io_ncOut_bits_vecActive:o:1;io_ncOut_bits_schedIndex:o:7;io_uncache_req_ready:i:1;io_uncache_req_valid:o:1;io_uncache_req_bits_robIdx_flag:o:1;io_uncache_req_bits_robIdx_value:o:8;io_uncache_req_bits_addr:o:48;io_uncache_req_bits_vaddr:o:50;io_uncache_req_bits_mask:o:8;io_uncache_req_bits_nc:o:1;io_uncache_req_bits_memBackTypeMM:o:1;io_uncache_idResp_valid:i:1;io_uncache_idResp_bits_mid:i:7;io_uncache_idResp_bits_sid:i:4;io_uncache_resp_valid:i:1;io_uncache_resp_bits_data:i:64;io_uncache_resp_bits_denied:i:1;io_uncache_resp_bits_corrupt:i:1;io_exception_valid:o:1;io_exception_bits_uop_exceptionVec_3:o:1;io_exception_bits_uop_exceptionVec_4:o:1;io_exception_bits_uop_exceptionVec_5:o:1;io_exception_bits_uop_exceptionVec_13:o:1;io_exception_bits_uop_exceptionVec_19:o:1;io_exception_bits_uop_exceptionVec_21:o:1;io_exception_bits_uop_uopIdx:o:7;io_exception_bits_uop_robIdx_flag:o:1;io_exception_bits_uop_robIdx_value:o:8;io_exception_bits_fullva:o:64;io_exception_bits_gpaddr:o:64;io_exception_bits_isHyper:o:1;io_exception_bits_isForVSnonLeafPTE:o:1",
    "UncacheEntry_10|entry|slaveId=16|clock:i:1;reset:i:1;io_redirect_valid:i:1;io_redirect_bits_robIdx_flag:i:1;io_redirect_bits_robIdx_value:i:8;io_redirect_bits_level:i:1;io_flush:o:1;io_rob_pendingMMIOld:i:1;io_rob_pendingPtr_flag:i:1;io_rob_pendingPtr_value:i:8;io_mmioSelect:o:1;io_slaveId_valid:o:1;io_slaveId_bits:o:4;io_req_valid:i:1;io_req_bits_uop_exceptionVec_3:i:1;io_req_bits_uop_exceptionVec_4:i:1;io_req_bits_uop_exceptionVec_13:i:1;io_req_bits_uop_exceptionVec_21:i:1;io_req_bits_uop_trigger:i:4;io_req_bits_uop_preDecodeInfo_isRVC:i:1;io_req_bits_uop_ftqPtr_flag:i:1;io_req_bits_uop_ftqPtr_value:i:6;io_req_bits_uop_ftqOffset:i:4;io_req_bits_uop_fuOpType:i:9;io_req_bits_uop_rfWen:i:1;io_req_bits_uop_fpWen:i:1;io_req_bits_uop_vpu_vstart:i:8;io_req_bits_uop_vpu_veew:i:2;io_req_bits_uop_uopIdx:i:7;io_req_bits_uop_pdest:i:8;io_req_bits_uop_robIdx_flag:i:1;io_req_bits_uop_robIdx_value:i:8;io_req_bits_uop_storeSetHit:i:1;io_req_bits_uop_waitForRobIdx_flag:i:1;io_req_bits_uop_waitForRobIdx_value:i:8;io_req_bits_uop_loadWaitBit:i:1;io_req_bits_uop_loadWaitStrict:i:1;io_req_bits_uop_lqIdx_flag:i:1;io_req_bits_uop_lqIdx_value:i:7;io_req_bits_uop_sqIdx_flag:i:1;io_req_bits_uop_sqIdx_value:i:6;io_req_bits_vaddr:i:50;io_req_bits_fullva:i:64;io_req_bits_paddr:i:48;io_req_bits_gpaddr:i:64;io_req_bits_mask:i:16;io_req_bits_nc:i:1;io_req_bits_mmio:i:1;io_req_bits_memBackTypeMM:i:1;io_req_bits_isHyper:i:1;io_req_bits_isForVSnonLeafPTE:i:1;io_req_bits_isvec:i:1;io_req_bits_is128bit:i:1;io_req_bits_vecActive:i:1;io_req_bits_schedIndex:i:7;io_mmioOut_ready:i:1;io_mmioOut_valid:o:1;io_mmioOut_bits_uop_exceptionVec_3:o:1;io_mmioOut_bits_uop_exceptionVec_4:o:1;io_mmioOut_bits_uop_exceptionVec_5:o:1;io_mmioOut_bits_uop_exceptionVec_13:o:1;io_mmioOut_bits_uop_exceptionVec_19:o:1;io_mmioOut_bits_uop_exceptionVec_21:o:1;io_mmioOut_bits_uop_trigger:o:4;io_mmioOut_bits_uop_preDecodeInfo_isRVC:o:1;io_mmioOut_bits_uop_ftqPtr_flag:o:1;io_mmioOut_bits_uop_ftqPtr_value:o:6;io_mmioOut_bits_uop_ftqOffset:o:4;io_mmioOut_bits_uop_fuOpType:o:9;io_mmioOut_bits_uop_rfWen:o:1;io_mmioOut_bits_uop_fpWen:o:1;io_mmioOut_bits_uop_flushPipe:o:1;io_mmioOut_bits_uop_vpu_vstart:o:8;io_mmioOut_bits_uop_vpu_veew:o:2;io_mmioOut_bits_uop_uopIdx:o:7;io_mmioOut_bits_uop_pdest:o:8;io_mmioOut_bits_uop_robIdx_flag:o:1;io_mmioOut_bits_uop_robIdx_value:o:8;io_mmioOut_bits_uop_storeSetHit:o:1;io_mmioOut_bits_uop_waitForRobIdx_flag:o:1;io_mmioOut_bits_uop_waitForRobIdx_value:o:8;io_mmioOut_bits_uop_loadWaitBit:o:1;io_mmioOut_bits_uop_loadWaitStrict:o:1;io_mmioOut_bits_uop_lqIdx_flag:o:1;io_mmioOut_bits_uop_lqIdx_value:o:7;io_mmioOut_bits_uop_sqIdx_flag:o:1;io_mmioOut_bits_uop_sqIdx_value:o:6;io_mmioOut_bits_uop_replayInst:o:1;io_mmioRawData_lqData:o:64;io_mmioRawData_uop_fuOpType:o:9;io_mmioRawData_uop_fpWen:o:1;io_mmioRawData_addrOffset:o:3;io_ncOut_ready:i:1;io_ncOut_valid:o:1;io_ncOut_bits_uop_exceptionVec_4:o:1;io_ncOut_bits_uop_exceptionVec_19:o:1;io_ncOut_bits_uop_preDecodeInfo_isRVC:o:1;io_ncOut_bits_uop_ftqPtr_flag:o:1;io_ncOut_bits_uop_ftqPtr_value:o:6;io_ncOut_bits_uop_ftqOffset:o:4;io_ncOut_bits_uop_fuOpType:o:9;io_ncOut_bits_uop_rfWen:o:1;io_ncOut_bits_uop_fpWen:o:1;io_ncOut_bits_uop_vpu_vstart:o:8;io_ncOut_bits_uop_vpu_veew:o:2;io_ncOut_bits_uop_uopIdx:o:7;io_ncOut_bits_uop_pdest:o:8;io_ncOut_bits_uop_robIdx_flag:o:1;io_ncOut_bits_uop_robIdx_value:o:8;io_ncOut_bits_uop_storeSetHit:o:1;io_ncOut_bits_uop_waitForRobIdx_flag:o:1;io_ncOut_bits_uop_waitForRobIdx_value:o:8;io_ncOut_bits_uop_loadWaitBit:o:1;io_ncOut_bits_uop_loadWaitStrict:o:1;io_ncOut_bits_uop_lqIdx_flag:o:1;io_ncOut_bits_uop_lqIdx_value:o:7;io_ncOut_bits_uop_sqIdx_flag:o:1;io_ncOut_bits_uop_sqIdx_value:o:6;io_ncOut_bits_vaddr:o:50;io_ncOut_bits_paddr:o:48;io_ncOut_bits_data:o:129;io_ncOut_bits_isvec:o:1;io_ncOut_bits_is128bit:o:1;io_ncOut_bits_vecActive:o:1;io_ncOut_bits_schedIndex:o:7;io_uncache_req_ready:i:1;io_uncache_req_valid:o:1;io_uncache_req_bits_robIdx_flag:o:1;io_uncache_req_bits_robIdx_value:o:8;io_uncache_req_bits_addr:o:48;io_uncache_req_bits_vaddr:o:50;io_uncache_req_bits_mask:o:8;io_uncache_req_bits_nc:o:1;io_uncache_req_bits_memBackTypeMM:o:1;io_uncache_idResp_valid:i:1;io_uncache_idResp_bits_mid:i:7;io_uncache_idResp_bits_sid:i:4;io_uncache_resp_valid:i:1;io_uncache_resp_bits_data:i:64;io_uncache_resp_bits_denied:i:1;io_uncache_resp_bits_corrupt:i:1;io_exception_valid:o:1;io_exception_bits_uop_exceptionVec_3:o:1;io_exception_bits_uop_exceptionVec_4:o:1;io_exception_bits_uop_exceptionVec_5:o:1;io_exception_bits_uop_exceptionVec_13:o:1;io_exception_bits_uop_exceptionVec_19:o:1;io_exception_bits_uop_exceptionVec_21:o:1;io_exception_bits_uop_uopIdx:o:7;io_exception_bits_uop_robIdx_flag:o:1;io_exception_bits_uop_robIdx_value:o:8;io_exception_bits_fullva:o:64;io_exception_bits_gpaddr:o:64;io_exception_bits_isHyper:o:1;io_exception_bits_isForVSnonLeafPTE:o:1",
    "UncacheEntry_11|entry|slaveId=17|clock:i:1;reset:i:1;io_redirect_valid:i:1;io_redirect_bits_robIdx_flag:i:1;io_redirect_bits_robIdx_value:i:8;io_redirect_bits_level:i:1;io_flush:o:1;io_rob_pendingMMIOld:i:1;io_rob_pendingPtr_flag:i:1;io_rob_pendingPtr_value:i:8;io_mmioSelect:o:1;io_slaveId_valid:o:1;io_slaveId_bits:o:4;io_req_valid:i:1;io_req_bits_uop_exceptionVec_3:i:1;io_req_bits_uop_exceptionVec_4:i:1;io_req_bits_uop_exceptionVec_13:i:1;io_req_bits_uop_exceptionVec_21:i:1;io_req_bits_uop_trigger:i:4;io_req_bits_uop_preDecodeInfo_isRVC:i:1;io_req_bits_uop_ftqPtr_flag:i:1;io_req_bits_uop_ftqPtr_value:i:6;io_req_bits_uop_ftqOffset:i:4;io_req_bits_uop_fuOpType:i:9;io_req_bits_uop_rfWen:i:1;io_req_bits_uop_fpWen:i:1;io_req_bits_uop_vpu_vstart:i:8;io_req_bits_uop_vpu_veew:i:2;io_req_bits_uop_uopIdx:i:7;io_req_bits_uop_pdest:i:8;io_req_bits_uop_robIdx_flag:i:1;io_req_bits_uop_robIdx_value:i:8;io_req_bits_uop_storeSetHit:i:1;io_req_bits_uop_waitForRobIdx_flag:i:1;io_req_bits_uop_waitForRobIdx_value:i:8;io_req_bits_uop_loadWaitBit:i:1;io_req_bits_uop_loadWaitStrict:i:1;io_req_bits_uop_lqIdx_flag:i:1;io_req_bits_uop_lqIdx_value:i:7;io_req_bits_uop_sqIdx_flag:i:1;io_req_bits_uop_sqIdx_value:i:6;io_req_bits_vaddr:i:50;io_req_bits_fullva:i:64;io_req_bits_paddr:i:48;io_req_bits_gpaddr:i:64;io_req_bits_mask:i:16;io_req_bits_nc:i:1;io_req_bits_mmio:i:1;io_req_bits_memBackTypeMM:i:1;io_req_bits_isHyper:i:1;io_req_bits_isForVSnonLeafPTE:i:1;io_req_bits_isvec:i:1;io_req_bits_is128bit:i:1;io_req_bits_vecActive:i:1;io_req_bits_schedIndex:i:7;io_mmioOut_ready:i:1;io_mmioOut_valid:o:1;io_mmioOut_bits_uop_exceptionVec_3:o:1;io_mmioOut_bits_uop_exceptionVec_4:o:1;io_mmioOut_bits_uop_exceptionVec_5:o:1;io_mmioOut_bits_uop_exceptionVec_13:o:1;io_mmioOut_bits_uop_exceptionVec_19:o:1;io_mmioOut_bits_uop_exceptionVec_21:o:1;io_mmioOut_bits_uop_trigger:o:4;io_mmioOut_bits_uop_preDecodeInfo_isRVC:o:1;io_mmioOut_bits_uop_ftqPtr_flag:o:1;io_mmioOut_bits_uop_ftqPtr_value:o:6;io_mmioOut_bits_uop_ftqOffset:o:4;io_mmioOut_bits_uop_fuOpType:o:9;io_mmioOut_bits_uop_rfWen:o:1;io_mmioOut_bits_uop_fpWen:o:1;io_mmioOut_bits_uop_flushPipe:o:1;io_mmioOut_bits_uop_vpu_vstart:o:8;io_mmioOut_bits_uop_vpu_veew:o:2;io_mmioOut_bits_uop_uopIdx:o:7;io_mmioOut_bits_uop_pdest:o:8;io_mmioOut_bits_uop_robIdx_flag:o:1;io_mmioOut_bits_uop_robIdx_value:o:8;io_mmioOut_bits_uop_storeSetHit:o:1;io_mmioOut_bits_uop_waitForRobIdx_flag:o:1;io_mmioOut_bits_uop_waitForRobIdx_value:o:8;io_mmioOut_bits_uop_loadWaitBit:o:1;io_mmioOut_bits_uop_loadWaitStrict:o:1;io_mmioOut_bits_uop_lqIdx_flag:o:1;io_mmioOut_bits_uop_lqIdx_value:o:7;io_mmioOut_bits_uop_sqIdx_flag:o:1;io_mmioOut_bits_uop_sqIdx_value:o:6;io_mmioOut_bits_uop_replayInst:o:1;io_mmioRawData_lqData:o:64;io_mmioRawData_uop_fuOpType:o:9;io_mmioRawData_uop_fpWen:o:1;io_mmioRawData_addrOffset:o:3;io_ncOut_ready:i:1;io_ncOut_valid:o:1;io_ncOut_bits_uop_exceptionVec_4:o:1;io_ncOut_bits_uop_exceptionVec_19:o:1;io_ncOut_bits_uop_preDecodeInfo_isRVC:o:1;io_ncOut_bits_uop_ftqPtr_flag:o:1;io_ncOut_bits_uop_ftqPtr_value:o:6;io_ncOut_bits_uop_ftqOffset:o:4;io_ncOut_bits_uop_fuOpType:o:9;io_ncOut_bits_uop_rfWen:o:1;io_ncOut_bits_uop_fpWen:o:1;io_ncOut_bits_uop_vpu_vstart:o:8;io_ncOut_bits_uop_vpu_veew:o:2;io_ncOut_bits_uop_uopIdx:o:7;io_ncOut_bits_uop_pdest:o:8;io_ncOut_bits_uop_robIdx_flag:o:1;io_ncOut_bits_uop_robIdx_value:o:8;io_ncOut_bits_uop_storeSetHit:o:1;io_ncOut_bits_uop_waitForRobIdx_flag:o:1;io_ncOut_bits_uop_waitForRobIdx_value:o:8;io_ncOut_bits_uop_loadWaitBit:o:1;io_ncOut_bits_uop_loadWaitStrict:o:1;io_ncOut_bits_uop_lqIdx_flag:o:1;io_ncOut_bits_uop_lqIdx_value:o:7;io_ncOut_bits_uop_sqIdx_flag:o:1;io_ncOut_bits_uop_sqIdx_value:o:6;io_ncOut_bits_vaddr:o:50;io_ncOut_bits_paddr:o:48;io_ncOut_bits_data:o:129;io_ncOut_bits_isvec:o:1;io_ncOut_bits_is128bit:o:1;io_ncOut_bits_vecActive:o:1;io_ncOut_bits_schedIndex:o:7;io_uncache_req_ready:i:1;io_uncache_req_valid:o:1;io_uncache_req_bits_robIdx_flag:o:1;io_uncache_req_bits_robIdx_value:o:8;io_uncache_req_bits_addr:o:48;io_uncache_req_bits_vaddr:o:50;io_uncache_req_bits_mask:o:8;io_uncache_req_bits_nc:o:1;io_uncache_req_bits_memBackTypeMM:o:1;io_uncache_idResp_valid:i:1;io_uncache_idResp_bits_mid:i:7;io_uncache_idResp_bits_sid:i:4;io_uncache_resp_valid:i:1;io_uncache_resp_bits_data:i:64;io_uncache_resp_bits_denied:i:1;io_uncache_resp_bits_corrupt:i:1;io_exception_valid:o:1;io_exception_bits_uop_exceptionVec_3:o:1;io_exception_bits_uop_exceptionVec_4:o:1;io_exception_bits_uop_exceptionVec_5:o:1;io_exception_bits_uop_exceptionVec_13:o:1;io_exception_bits_uop_exceptionVec_19:o:1;io_exception_bits_uop_exceptionVec_21:o:1;io_exception_bits_uop_uopIdx:o:7;io_exception_bits_uop_robIdx_flag:o:1;io_exception_bits_uop_robIdx_value:o:8;io_exception_bits_fullva:o:64;io_exception_bits_gpaddr:o:64;io_exception_bits_isHyper:o:1;io_exception_bits_isForVSnonLeafPTE:o:1",
    "UncacheEntry_12|entry|slaveId=18|clock:i:1;reset:i:1;io_redirect_valid:i:1;io_redirect_bits_robIdx_flag:i:1;io_redirect_bits_robIdx_value:i:8;io_redirect_bits_level:i:1;io_flush:o:1;io_rob_pendingMMIOld:i:1;io_rob_pendingPtr_flag:i:1;io_rob_pendingPtr_value:i:8;io_mmioSelect:o:1;io_slaveId_valid:o:1;io_slaveId_bits:o:4;io_req_valid:i:1;io_req_bits_uop_exceptionVec_3:i:1;io_req_bits_uop_exceptionVec_4:i:1;io_req_bits_uop_exceptionVec_13:i:1;io_req_bits_uop_exceptionVec_21:i:1;io_req_bits_uop_trigger:i:4;io_req_bits_uop_preDecodeInfo_isRVC:i:1;io_req_bits_uop_ftqPtr_flag:i:1;io_req_bits_uop_ftqPtr_value:i:6;io_req_bits_uop_ftqOffset:i:4;io_req_bits_uop_fuOpType:i:9;io_req_bits_uop_rfWen:i:1;io_req_bits_uop_fpWen:i:1;io_req_bits_uop_vpu_vstart:i:8;io_req_bits_uop_vpu_veew:i:2;io_req_bits_uop_uopIdx:i:7;io_req_bits_uop_pdest:i:8;io_req_bits_uop_robIdx_flag:i:1;io_req_bits_uop_robIdx_value:i:8;io_req_bits_uop_storeSetHit:i:1;io_req_bits_uop_waitForRobIdx_flag:i:1;io_req_bits_uop_waitForRobIdx_value:i:8;io_req_bits_uop_loadWaitBit:i:1;io_req_bits_uop_loadWaitStrict:i:1;io_req_bits_uop_lqIdx_flag:i:1;io_req_bits_uop_lqIdx_value:i:7;io_req_bits_uop_sqIdx_flag:i:1;io_req_bits_uop_sqIdx_value:i:6;io_req_bits_vaddr:i:50;io_req_bits_fullva:i:64;io_req_bits_paddr:i:48;io_req_bits_gpaddr:i:64;io_req_bits_mask:i:16;io_req_bits_nc:i:1;io_req_bits_mmio:i:1;io_req_bits_memBackTypeMM:i:1;io_req_bits_isHyper:i:1;io_req_bits_isForVSnonLeafPTE:i:1;io_req_bits_isvec:i:1;io_req_bits_is128bit:i:1;io_req_bits_vecActive:i:1;io_req_bits_schedIndex:i:7;io_mmioOut_ready:i:1;io_mmioOut_valid:o:1;io_mmioOut_bits_uop_exceptionVec_3:o:1;io_mmioOut_bits_uop_exceptionVec_4:o:1;io_mmioOut_bits_uop_exceptionVec_5:o:1;io_mmioOut_bits_uop_exceptionVec_13:o:1;io_mmioOut_bits_uop_exceptionVec_19:o:1;io_mmioOut_bits_uop_exceptionVec_21:o:1;io_mmioOut_bits_uop_trigger:o:4;io_mmioOut_bits_uop_preDecodeInfo_isRVC:o:1;io_mmioOut_bits_uop_ftqPtr_flag:o:1;io_mmioOut_bits_uop_ftqPtr_value:o:6;io_mmioOut_bits_uop_ftqOffset:o:4;io_mmioOut_bits_uop_fuOpType:o:9;io_mmioOut_bits_uop_rfWen:o:1;io_mmioOut_bits_uop_fpWen:o:1;io_mmioOut_bits_uop_flushPipe:o:1;io_mmioOut_bits_uop_vpu_vstart:o:8;io_mmioOut_bits_uop_vpu_veew:o:2;io_mmioOut_bits_uop_uopIdx:o:7;io_mmioOut_bits_uop_pdest:o:8;io_mmioOut_bits_uop_robIdx_flag:o:1;io_mmioOut_bits_uop_robIdx_value:o:8;io_mmioOut_bits_uop_storeSetHit:o:1;io_mmioOut_bits_uop_waitForRobIdx_flag:o:1;io_mmioOut_bits_uop_waitForRobIdx_value:o:8;io_mmioOut_bits_uop_loadWaitBit:o:1;io_mmioOut_bits_uop_loadWaitStrict:o:1;io_mmioOut_bits_uop_lqIdx_flag:o:1;io_mmioOut_bits_uop_lqIdx_value:o:7;io_mmioOut_bits_uop_sqIdx_flag:o:1;io_mmioOut_bits_uop_sqIdx_value:o:6;io_mmioOut_bits_uop_replayInst:o:1;io_mmioRawData_lqData:o:64;io_mmioRawData_uop_fuOpType:o:9;io_mmioRawData_uop_fpWen:o:1;io_mmioRawData_addrOffset:o:3;io_ncOut_ready:i:1;io_ncOut_valid:o:1;io_ncOut_bits_uop_exceptionVec_4:o:1;io_ncOut_bits_uop_exceptionVec_19:o:1;io_ncOut_bits_uop_preDecodeInfo_isRVC:o:1;io_ncOut_bits_uop_ftqPtr_flag:o:1;io_ncOut_bits_uop_ftqPtr_value:o:6;io_ncOut_bits_uop_ftqOffset:o:4;io_ncOut_bits_uop_fuOpType:o:9;io_ncOut_bits_uop_rfWen:o:1;io_ncOut_bits_uop_fpWen:o:1;io_ncOut_bits_uop_vpu_vstart:o:8;io_ncOut_bits_uop_vpu_veew:o:2;io_ncOut_bits_uop_uopIdx:o:7;io_ncOut_bits_uop_pdest:o:8;io_ncOut_bits_uop_robIdx_flag:o:1;io_ncOut_bits_uop_robIdx_value:o:8;io_ncOut_bits_uop_storeSetHit:o:1;io_ncOut_bits_uop_waitForRobIdx_flag:o:1;io_ncOut_bits_uop_waitForRobIdx_value:o:8;io_ncOut_bits_uop_loadWaitBit:o:1;io_ncOut_bits_uop_loadWaitStrict:o:1;io_ncOut_bits_uop_lqIdx_flag:o:1;io_ncOut_bits_uop_lqIdx_value:o:7;io_ncOut_bits_uop_sqIdx_flag:o:1;io_ncOut_bits_uop_sqIdx_value:o:6;io_ncOut_bits_vaddr:o:50;io_ncOut_bits_paddr:o:48;io_ncOut_bits_data:o:129;io_ncOut_bits_isvec:o:1;io_ncOut_bits_is128bit:o:1;io_ncOut_bits_vecActive:o:1;io_ncOut_bits_schedIndex:o:7;io_uncache_req_ready:i:1;io_uncache_req_valid:o:1;io_uncache_req_bits_robIdx_flag:o:1;io_uncache_req_bits_robIdx_value:o:8;io_uncache_req_bits_addr:o:48;io_uncache_req_bits_vaddr:o:50;io_uncache_req_bits_mask:o:8;io_uncache_req_bits_nc:o:1;io_uncache_req_bits_memBackTypeMM:o:1;io_uncache_idResp_valid:i:1;io_uncache_idResp_bits_mid:i:7;io_uncache_idResp_bits_sid:i:4;io_uncache_resp_valid:i:1;io_uncache_resp_bits_data:i:64;io_uncache_resp_bits_denied:i:1;io_uncache_resp_bits_corrupt:i:1;io_exception_valid:o:1;io_exception_bits_uop_exceptionVec_3:o:1;io_exception_bits_uop_exceptionVec_4:o:1;io_exception_bits_uop_exceptionVec_5:o:1;io_exception_bits_uop_exceptionVec_13:o:1;io_exception_bits_uop_exceptionVec_19:o:1;io_exception_bits_uop_exceptionVec_21:o:1;io_exception_bits_uop_uopIdx:o:7;io_exception_bits_uop_robIdx_flag:o:1;io_exception_bits_uop_robIdx_value:o:8;io_exception_bits_fullva:o:64;io_exception_bits_gpaddr:o:64;io_exception_bits_isHyper:o:1;io_exception_bits_isForVSnonLeafPTE:o:1",
    "UncacheEntry_13|entry|slaveId=19|clock:i:1;reset:i:1;io_redirect_valid:i:1;io_redirect_bits_robIdx_flag:i:1;io_redirect_bits_robIdx_value:i:8;io_redirect_bits_level:i:1;io_flush:o:1;io_rob_pendingMMIOld:i:1;io_rob_pendingPtr_flag:i:1;io_rob_pendingPtr_value:i:8;io_mmioSelect:o:1;io_slaveId_valid:o:1;io_slaveId_bits:o:4;io_req_valid:i:1;io_req_bits_uop_exceptionVec_3:i:1;io_req_bits_uop_exceptionVec_4:i:1;io_req_bits_uop_exceptionVec_13:i:1;io_req_bits_uop_exceptionVec_21:i:1;io_req_bits_uop_trigger:i:4;io_req_bits_uop_preDecodeInfo_isRVC:i:1;io_req_bits_uop_ftqPtr_flag:i:1;io_req_bits_uop_ftqPtr_value:i:6;io_req_bits_uop_ftqOffset:i:4;io_req_bits_uop_fuOpType:i:9;io_req_bits_uop_rfWen:i:1;io_req_bits_uop_fpWen:i:1;io_req_bits_uop_vpu_vstart:i:8;io_req_bits_uop_vpu_veew:i:2;io_req_bits_uop_uopIdx:i:7;io_req_bits_uop_pdest:i:8;io_req_bits_uop_robIdx_flag:i:1;io_req_bits_uop_robIdx_value:i:8;io_req_bits_uop_storeSetHit:i:1;io_req_bits_uop_waitForRobIdx_flag:i:1;io_req_bits_uop_waitForRobIdx_value:i:8;io_req_bits_uop_loadWaitBit:i:1;io_req_bits_uop_loadWaitStrict:i:1;io_req_bits_uop_lqIdx_flag:i:1;io_req_bits_uop_lqIdx_value:i:7;io_req_bits_uop_sqIdx_flag:i:1;io_req_bits_uop_sqIdx_value:i:6;io_req_bits_vaddr:i:50;io_req_bits_fullva:i:64;io_req_bits_paddr:i:48;io_req_bits_gpaddr:i:64;io_req_bits_mask:i:16;io_req_bits_nc:i:1;io_req_bits_mmio:i:1;io_req_bits_memBackTypeMM:i:1;io_req_bits_isHyper:i:1;io_req_bits_isForVSnonLeafPTE:i:1;io_req_bits_isvec:i:1;io_req_bits_is128bit:i:1;io_req_bits_vecActive:i:1;io_req_bits_schedIndex:i:7;io_mmioOut_ready:i:1;io_mmioOut_valid:o:1;io_mmioOut_bits_uop_exceptionVec_3:o:1;io_mmioOut_bits_uop_exceptionVec_4:o:1;io_mmioOut_bits_uop_exceptionVec_5:o:1;io_mmioOut_bits_uop_exceptionVec_13:o:1;io_mmioOut_bits_uop_exceptionVec_19:o:1;io_mmioOut_bits_uop_exceptionVec_21:o:1;io_mmioOut_bits_uop_trigger:o:4;io_mmioOut_bits_uop_preDecodeInfo_isRVC:o:1;io_mmioOut_bits_uop_ftqPtr_flag:o:1;io_mmioOut_bits_uop_ftqPtr_value:o:6;io_mmioOut_bits_uop_ftqOffset:o:4;io_mmioOut_bits_uop_fuOpType:o:9;io_mmioOut_bits_uop_rfWen:o:1;io_mmioOut_bits_uop_fpWen:o:1;io_mmioOut_bits_uop_flushPipe:o:1;io_mmioOut_bits_uop_vpu_vstart:o:8;io_mmioOut_bits_uop_vpu_veew:o:2;io_mmioOut_bits_uop_uopIdx:o:7;io_mmioOut_bits_uop_pdest:o:8;io_mmioOut_bits_uop_robIdx_flag:o:1;io_mmioOut_bits_uop_robIdx_value:o:8;io_mmioOut_bits_uop_storeSetHit:o:1;io_mmioOut_bits_uop_waitForRobIdx_flag:o:1;io_mmioOut_bits_uop_waitForRobIdx_value:o:8;io_mmioOut_bits_uop_loadWaitBit:o:1;io_mmioOut_bits_uop_loadWaitStrict:o:1;io_mmioOut_bits_uop_lqIdx_flag:o:1;io_mmioOut_bits_uop_lqIdx_value:o:7;io_mmioOut_bits_uop_sqIdx_flag:o:1;io_mmioOut_bits_uop_sqIdx_value:o:6;io_mmioOut_bits_uop_replayInst:o:1;io_mmioRawData_lqData:o:64;io_mmioRawData_uop_fuOpType:o:9;io_mmioRawData_uop_fpWen:o:1;io_mmioRawData_addrOffset:o:3;io_ncOut_ready:i:1;io_ncOut_valid:o:1;io_ncOut_bits_uop_exceptionVec_4:o:1;io_ncOut_bits_uop_exceptionVec_19:o:1;io_ncOut_bits_uop_preDecodeInfo_isRVC:o:1;io_ncOut_bits_uop_ftqPtr_flag:o:1;io_ncOut_bits_uop_ftqPtr_value:o:6;io_ncOut_bits_uop_ftqOffset:o:4;io_ncOut_bits_uop_fuOpType:o:9;io_ncOut_bits_uop_rfWen:o:1;io_ncOut_bits_uop_fpWen:o:1;io_ncOut_bits_uop_vpu_vstart:o:8;io_ncOut_bits_uop_vpu_veew:o:2;io_ncOut_bits_uop_uopIdx:o:7;io_ncOut_bits_uop_pdest:o:8;io_ncOut_bits_uop_robIdx_flag:o:1;io_ncOut_bits_uop_robIdx_value:o:8;io_ncOut_bits_uop_storeSetHit:o:1;io_ncOut_bits_uop_waitForRobIdx_flag:o:1;io_ncOut_bits_uop_waitForRobIdx_value:o:8;io_ncOut_bits_uop_loadWaitBit:o:1;io_ncOut_bits_uop_loadWaitStrict:o:1;io_ncOut_bits_uop_lqIdx_flag:o:1;io_ncOut_bits_uop_lqIdx_value:o:7;io_ncOut_bits_uop_sqIdx_flag:o:1;io_ncOut_bits_uop_sqIdx_value:o:6;io_ncOut_bits_vaddr:o:50;io_ncOut_bits_paddr:o:48;io_ncOut_bits_data:o:129;io_ncOut_bits_isvec:o:1;io_ncOut_bits_is128bit:o:1;io_ncOut_bits_vecActive:o:1;io_ncOut_bits_schedIndex:o:7;io_uncache_req_ready:i:1;io_uncache_req_valid:o:1;io_uncache_req_bits_robIdx_flag:o:1;io_uncache_req_bits_robIdx_value:o:8;io_uncache_req_bits_addr:o:48;io_uncache_req_bits_vaddr:o:50;io_uncache_req_bits_mask:o:8;io_uncache_req_bits_nc:o:1;io_uncache_req_bits_memBackTypeMM:o:1;io_uncache_idResp_valid:i:1;io_uncache_idResp_bits_mid:i:7;io_uncache_idResp_bits_sid:i:4;io_uncache_resp_valid:i:1;io_uncache_resp_bits_data:i:64;io_uncache_resp_bits_denied:i:1;io_uncache_resp_bits_corrupt:i:1;io_exception_valid:o:1;io_exception_bits_uop_exceptionVec_3:o:1;io_exception_bits_uop_exceptionVec_4:o:1;io_exception_bits_uop_exceptionVec_5:o:1;io_exception_bits_uop_exceptionVec_13:o:1;io_exception_bits_uop_exceptionVec_19:o:1;io_exception_bits_uop_exceptionVec_21:o:1;io_exception_bits_uop_uopIdx:o:7;io_exception_bits_uop_robIdx_flag:o:1;io_exception_bits_uop_robIdx_value:o:8;io_exception_bits_fullva:o:64;io_exception_bits_gpaddr:o:64;io_exception_bits_isHyper:o:1;io_exception_bits_isForVSnonLeafPTE:o:1",
    "UncacheEntry_14|entry|slaveId=20|clock:i:1;reset:i:1;io_redirect_valid:i:1;io_redirect_bits_robIdx_flag:i:1;io_redirect_bits_robIdx_value:i:8;io_redirect_bits_level:i:1;io_flush:o:1;io_rob_pendingMMIOld:i:1;io_rob_pendingPtr_flag:i:1;io_rob_pendingPtr_value:i:8;io_mmioSelect:o:1;io_slaveId_valid:o:1;io_slaveId_bits:o:4;io_req_valid:i:1;io_req_bits_uop_exceptionVec_3:i:1;io_req_bits_uop_exceptionVec_4:i:1;io_req_bits_uop_exceptionVec_13:i:1;io_req_bits_uop_exceptionVec_21:i:1;io_req_bits_uop_trigger:i:4;io_req_bits_uop_preDecodeInfo_isRVC:i:1;io_req_bits_uop_ftqPtr_flag:i:1;io_req_bits_uop_ftqPtr_value:i:6;io_req_bits_uop_ftqOffset:i:4;io_req_bits_uop_fuOpType:i:9;io_req_bits_uop_rfWen:i:1;io_req_bits_uop_fpWen:i:1;io_req_bits_uop_vpu_vstart:i:8;io_req_bits_uop_vpu_veew:i:2;io_req_bits_uop_uopIdx:i:7;io_req_bits_uop_pdest:i:8;io_req_bits_uop_robIdx_flag:i:1;io_req_bits_uop_robIdx_value:i:8;io_req_bits_uop_storeSetHit:i:1;io_req_bits_uop_waitForRobIdx_flag:i:1;io_req_bits_uop_waitForRobIdx_value:i:8;io_req_bits_uop_loadWaitBit:i:1;io_req_bits_uop_loadWaitStrict:i:1;io_req_bits_uop_lqIdx_flag:i:1;io_req_bits_uop_lqIdx_value:i:7;io_req_bits_uop_sqIdx_flag:i:1;io_req_bits_uop_sqIdx_value:i:6;io_req_bits_vaddr:i:50;io_req_bits_fullva:i:64;io_req_bits_paddr:i:48;io_req_bits_gpaddr:i:64;io_req_bits_mask:i:16;io_req_bits_nc:i:1;io_req_bits_mmio:i:1;io_req_bits_memBackTypeMM:i:1;io_req_bits_isHyper:i:1;io_req_bits_isForVSnonLeafPTE:i:1;io_req_bits_isvec:i:1;io_req_bits_is128bit:i:1;io_req_bits_vecActive:i:1;io_req_bits_schedIndex:i:7;io_mmioOut_ready:i:1;io_mmioOut_valid:o:1;io_mmioOut_bits_uop_exceptionVec_3:o:1;io_mmioOut_bits_uop_exceptionVec_4:o:1;io_mmioOut_bits_uop_exceptionVec_5:o:1;io_mmioOut_bits_uop_exceptionVec_13:o:1;io_mmioOut_bits_uop_exceptionVec_19:o:1;io_mmioOut_bits_uop_exceptionVec_21:o:1;io_mmioOut_bits_uop_trigger:o:4;io_mmioOut_bits_uop_preDecodeInfo_isRVC:o:1;io_mmioOut_bits_uop_ftqPtr_flag:o:1;io_mmioOut_bits_uop_ftqPtr_value:o:6;io_mmioOut_bits_uop_ftqOffset:o:4;io_mmioOut_bits_uop_fuOpType:o:9;io_mmioOut_bits_uop_rfWen:o:1;io_mmioOut_bits_uop_fpWen:o:1;io_mmioOut_bits_uop_flushPipe:o:1;io_mmioOut_bits_uop_vpu_vstart:o:8;io_mmioOut_bits_uop_vpu_veew:o:2;io_mmioOut_bits_uop_uopIdx:o:7;io_mmioOut_bits_uop_pdest:o:8;io_mmioOut_bits_uop_robIdx_flag:o:1;io_mmioOut_bits_uop_robIdx_value:o:8;io_mmioOut_bits_uop_storeSetHit:o:1;io_mmioOut_bits_uop_waitForRobIdx_flag:o:1;io_mmioOut_bits_uop_waitForRobIdx_value:o:8;io_mmioOut_bits_uop_loadWaitBit:o:1;io_mmioOut_bits_uop_loadWaitStrict:o:1;io_mmioOut_bits_uop_lqIdx_flag:o:1;io_mmioOut_bits_uop_lqIdx_value:o:7;io_mmioOut_bits_uop_sqIdx_flag:o:1;io_mmioOut_bits_uop_sqIdx_value:o:6;io_mmioOut_bits_uop_replayInst:o:1;io_mmioRawData_lqData:o:64;io_mmioRawData_uop_fuOpType:o:9;io_mmioRawData_uop_fpWen:o:1;io_mmioRawData_addrOffset:o:3;io_ncOut_ready:i:1;io_ncOut_valid:o:1;io_ncOut_bits_uop_exceptionVec_4:o:1;io_ncOut_bits_uop_exceptionVec_19:o:1;io_ncOut_bits_uop_preDecodeInfo_isRVC:o:1;io_ncOut_bits_uop_ftqPtr_flag:o:1;io_ncOut_bits_uop_ftqPtr_value:o:6;io_ncOut_bits_uop_ftqOffset:o:4;io_ncOut_bits_uop_fuOpType:o:9;io_ncOut_bits_uop_rfWen:o:1;io_ncOut_bits_uop_fpWen:o:1;io_ncOut_bits_uop_vpu_vstart:o:8;io_ncOut_bits_uop_vpu_veew:o:2;io_ncOut_bits_uop_uopIdx:o:7;io_ncOut_bits_uop_pdest:o:8;io_ncOut_bits_uop_robIdx_flag:o:1;io_ncOut_bits_uop_robIdx_value:o:8;io_ncOut_bits_uop_storeSetHit:o:1;io_ncOut_bits_uop_waitForRobIdx_flag:o:1;io_ncOut_bits_uop_waitForRobIdx_value:o:8;io_ncOut_bits_uop_loadWaitBit:o:1;io_ncOut_bits_uop_loadWaitStrict:o:1;io_ncOut_bits_uop_lqIdx_flag:o:1;io_ncOut_bits_uop_lqIdx_value:o:7;io_ncOut_bits_uop_sqIdx_flag:o:1;io_ncOut_bits_uop_sqIdx_value:o:6;io_ncOut_bits_vaddr:o:50;io_ncOut_bits_paddr:o:48;io_ncOut_bits_data:o:129;io_ncOut_bits_isvec:o:1;io_ncOut_bits_is128bit:o:1;io_ncOut_bits_vecActive:o:1;io_ncOut_bits_schedIndex:o:7;io_uncache_req_ready:i:1;io_uncache_req_valid:o:1;io_uncache_req_bits_robIdx_flag:o:1;io_uncache_req_bits_robIdx_value:o:8;io_uncache_req_bits_addr:o:48;io_uncache_req_bits_vaddr:o:50;io_uncache_req_bits_mask:o:8;io_uncache_req_bits_nc:o:1;io_uncache_req_bits_memBackTypeMM:o:1;io_uncache_idResp_valid:i:1;io_uncache_idResp_bits_mid:i:7;io_uncache_idResp_bits_sid:i:4;io_uncache_resp_valid:i:1;io_uncache_resp_bits_data:i:64;io_uncache_resp_bits_denied:i:1;io_uncache_resp_bits_corrupt:i:1;io_exception_valid:o:1;io_exception_bits_uop_exceptionVec_3:o:1;io_exception_bits_uop_exceptionVec_4:o:1;io_exception_bits_uop_exceptionVec_5:o:1;io_exception_bits_uop_exceptionVec_13:o:1;io_exception_bits_uop_exceptionVec_19:o:1;io_exception_bits_uop_exceptionVec_21:o:1;io_exception_bits_uop_uopIdx:o:7;io_exception_bits_uop_robIdx_flag:o:1;io_exception_bits_uop_robIdx_value:o:8;io_exception_bits_fullva:o:64;io_exception_bits_gpaddr:o:64;io_exception_bits_isHyper:o:1;io_exception_bits_isForVSnonLeafPTE:o:1",
    "UncacheEntry_15|entry|slaveId=21|clock:i:1;reset:i:1;io_redirect_valid:i:1;io_redirect_bits_robIdx_flag:i:1;io_redirect_bits_robIdx_value:i:8;io_redirect_bits_level:i:1;io_flush:o:1;io_rob_pendingMMIOld:i:1;io_rob_pendingPtr_flag:i:1;io_rob_pendingPtr_value:i:8;io_mmioSelect:o:1;io_slaveId_valid:o:1;io_slaveId_bits:o:4;io_req_valid:i:1;io_req_bits_uop_exceptionVec_3:i:1;io_req_bits_uop_exceptionVec_4:i:1;io_req_bits_uop_exceptionVec_13:i:1;io_req_bits_uop_exceptionVec_21:i:1;io_req_bits_uop_trigger:i:4;io_req_bits_uop_preDecodeInfo_isRVC:i:1;io_req_bits_uop_ftqPtr_flag:i:1;io_req_bits_uop_ftqPtr_value:i:6;io_req_bits_uop_ftqOffset:i:4;io_req_bits_uop_fuOpType:i:9;io_req_bits_uop_rfWen:i:1;io_req_bits_uop_fpWen:i:1;io_req_bits_uop_vpu_vstart:i:8;io_req_bits_uop_vpu_veew:i:2;io_req_bits_uop_uopIdx:i:7;io_req_bits_uop_pdest:i:8;io_req_bits_uop_robIdx_flag:i:1;io_req_bits_uop_robIdx_value:i:8;io_req_bits_uop_storeSetHit:i:1;io_req_bits_uop_waitForRobIdx_flag:i:1;io_req_bits_uop_waitForRobIdx_value:i:8;io_req_bits_uop_loadWaitBit:i:1;io_req_bits_uop_loadWaitStrict:i:1;io_req_bits_uop_lqIdx_flag:i:1;io_req_bits_uop_lqIdx_value:i:7;io_req_bits_uop_sqIdx_flag:i:1;io_req_bits_uop_sqIdx_value:i:6;io_req_bits_vaddr:i:50;io_req_bits_fullva:i:64;io_req_bits_paddr:i:48;io_req_bits_gpaddr:i:64;io_req_bits_mask:i:16;io_req_bits_nc:i:1;io_req_bits_mmio:i:1;io_req_bits_memBackTypeMM:i:1;io_req_bits_isHyper:i:1;io_req_bits_isForVSnonLeafPTE:i:1;io_req_bits_isvec:i:1;io_req_bits_is128bit:i:1;io_req_bits_vecActive:i:1;io_req_bits_schedIndex:i:7;io_mmioOut_ready:i:1;io_mmioOut_valid:o:1;io_mmioOut_bits_uop_exceptionVec_3:o:1;io_mmioOut_bits_uop_exceptionVec_4:o:1;io_mmioOut_bits_uop_exceptionVec_5:o:1;io_mmioOut_bits_uop_exceptionVec_13:o:1;io_mmioOut_bits_uop_exceptionVec_19:o:1;io_mmioOut_bits_uop_exceptionVec_21:o:1;io_mmioOut_bits_uop_trigger:o:4;io_mmioOut_bits_uop_preDecodeInfo_isRVC:o:1;io_mmioOut_bits_uop_ftqPtr_flag:o:1;io_mmioOut_bits_uop_ftqPtr_value:o:6;io_mmioOut_bits_uop_ftqOffset:o:4;io_mmioOut_bits_uop_fuOpType:o:9;io_mmioOut_bits_uop_rfWen:o:1;io_mmioOut_bits_uop_fpWen:o:1;io_mmioOut_bits_uop_flushPipe:o:1;io_mmioOut_bits_uop_vpu_vstart:o:8;io_mmioOut_bits_uop_vpu_veew:o:2;io_mmioOut_bits_uop_uopIdx:o:7;io_mmioOut_bits_uop_pdest:o:8;io_mmioOut_bits_uop_robIdx_flag:o:1;io_mmioOut_bits_uop_robIdx_value:o:8;io_mmioOut_bits_uop_storeSetHit:o:1;io_mmioOut_bits_uop_waitForRobIdx_flag:o:1;io_mmioOut_bits_uop_waitForRobIdx_value:o:8;io_mmioOut_bits_uop_loadWaitBit:o:1;io_mmioOut_bits_uop_loadWaitStrict:o:1;io_mmioOut_bits_uop_lqIdx_flag:o:1;io_mmioOut_bits_uop_lqIdx_value:o:7;io_mmioOut_bits_uop_sqIdx_flag:o:1;io_mmioOut_bits_uop_sqIdx_value:o:6;io_mmioOut_bits_uop_replayInst:o:1;io_mmioRawData_lqData:o:64;io_mmioRawData_uop_fuOpType:o:9;io_mmioRawData_uop_fpWen:o:1;io_mmioRawData_addrOffset:o:3;io_ncOut_ready:i:1;io_ncOut_valid:o:1;io_ncOut_bits_uop_exceptionVec_4:o:1;io_ncOut_bits_uop_exceptionVec_19:o:1;io_ncOut_bits_uop_preDecodeInfo_isRVC:o:1;io_ncOut_bits_uop_ftqPtr_flag:o:1;io_ncOut_bits_uop_ftqPtr_value:o:6;io_ncOut_bits_uop_ftqOffset:o:4;io_ncOut_bits_uop_fuOpType:o:9;io_ncOut_bits_uop_rfWen:o:1;io_ncOut_bits_uop_fpWen:o:1;io_ncOut_bits_uop_vpu_vstart:o:8;io_ncOut_bits_uop_vpu_veew:o:2;io_ncOut_bits_uop_uopIdx:o:7;io_ncOut_bits_uop_pdest:o:8;io_ncOut_bits_uop_robIdx_flag:o:1;io_ncOut_bits_uop_robIdx_value:o:8;io_ncOut_bits_uop_storeSetHit:o:1;io_ncOut_bits_uop_waitForRobIdx_flag:o:1;io_ncOut_bits_uop_waitForRobIdx_value:o:8;io_ncOut_bits_uop_loadWaitBit:o:1;io_ncOut_bits_uop_loadWaitStrict:o:1;io_ncOut_bits_uop_lqIdx_flag:o:1;io_ncOut_bits_uop_lqIdx_value:o:7;io_ncOut_bits_uop_sqIdx_flag:o:1;io_ncOut_bits_uop_sqIdx_value:o:6;io_ncOut_bits_vaddr:o:50;io_ncOut_bits_paddr:o:48;io_ncOut_bits_data:o:129;io_ncOut_bits_isvec:o:1;io_ncOut_bits_is128bit:o:1;io_ncOut_bits_vecActive:o:1;io_ncOut_bits_schedIndex:o:7;io_uncache_req_ready:i:1;io_uncache_req_valid:o:1;io_uncache_req_bits_robIdx_flag:o:1;io_uncache_req_bits_robIdx_value:o:8;io_uncache_req_bits_addr:o:48;io_uncache_req_bits_vaddr:o:50;io_uncache_req_bits_mask:o:8;io_uncache_req_bits_nc:o:1;io_uncache_req_bits_memBackTypeMM:o:1;io_uncache_idResp_valid:i:1;io_uncache_idResp_bits_mid:i:7;io_uncache_idResp_bits_sid:i:4;io_uncache_resp_valid:i:1;io_uncache_resp_bits_data:i:64;io_uncache_resp_bits_denied:i:1;io_uncache_resp_bits_corrupt:i:1;io_exception_valid:o:1;io_exception_bits_uop_exceptionVec_3:o:1;io_exception_bits_uop_exceptionVec_4:o:1;io_exception_bits_uop_exceptionVec_5:o:1;io_exception_bits_uop_exceptionVec_13:o:1;io_exception_bits_uop_exceptionVec_19:o:1;io_exception_bits_uop_exceptionVec_21:o:1;io_exception_bits_uop_uopIdx:o:7;io_exception_bits_uop_robIdx_flag:o:1;io_exception_bits_uop_robIdx_value:o:8;io_exception_bits_fullva:o:64;io_exception_bits_gpaddr:o:64;io_exception_bits_isHyper:o:1;io_exception_bits_isForVSnonLeafPTE:o:1",
    "FreeList|freelist|size=16,allocWidth=2,freeWidth=2,preAlloc=0,reqConst=1|clock:i:1;reset:i:1;io_allocateSlot_0:o:4;io_allocateSlot_1:o:4;io_doAllocate_0:i:1;io_doAllocate_1:i:1;io_free:i:16;io_validCount:o:5",
    "FreeList_1|freelist|size=16,allocWidth=1,freeWidth=1,preAlloc=0,reqConst=1|clock:i:1;reset:i:1;io_allocateSlot_0:o:4;io_doAllocate_0:i:1;io_free:i:16;io_validCount:o:5",
    "FreeList_3|freelist|size=72,allocWidth=3,freeWidth=4,preAlloc=0,reqConst=1|clock:i:1;reset:i:1;io_allocateSlot_0:o:7;io_allocateSlot_1:o:7;io_allocateSlot_2:o:7;io_canAllocate_0:o:1;io_canAllocate_1:o:1;io_canAllocate_2:o:1;io_doAllocate_0:i:1;io_doAllocate_1:i:1;io_doAllocate_2:i:1;io_free:i:72;io_empty:o:1",
    "FreeList_4|freelist|size=32,allocWidth=3,freeWidth=4,preAlloc=1,reqConst=1|clock:i:1;reset:i:1;io_allocateSlot_0:o:5;io_allocateSlot_1:o:5;io_allocateSlot_2:o:5;io_canAllocate_0:o:1;io_canAllocate_1:o:1;io_canAllocate_2:o:1;io_doAllocate_0:i:1;io_doAllocate_1:i:1;io_doAllocate_2:i:1;io_free:i:32;io_empty:o:1",
    "FreeList_5|freelist|size=72,allocWidth=3,freeWidth=4,preAlloc=1,reqConst=1|clock:i:1;reset:i:1;io_allocateSlot_0:o:7;io_allocateSlot_1:o:7;io_allocateSlot_2:o:7;io_canAllocate_0:o:1;io_canAllocate_1:o:1;io_canAllocate_2:o:1;io_doAllocate_0:i:1;io_doAllocate_1:i:1;io_doAllocate_2:i:1;io_free:i:72;io_empty:o:1",
    "FreeList_6|freelist|size=16,allocWidth=3,freeWidth=4,preAlloc=1,reqConst=1|clock:i:1;reset:i:1;io_allocateSlot_0:o:4;io_allocateSlot_1:o:4;io_allocateSlot_2:o:4;io_canAllocate_0:o:1;io_canAllocate_1:o:1;io_canAllocate_2:o:1;io_doAllocate_0:i:1;io_doAllocate_1:i:1;io_doAllocate_2:i:1;io_free:i:16",
    "TLBFA|tlbfa||clock:i:1;reset:i:1;io_sfence_valid:i:1;io_sfence_bits_rs1:i:1;io_sfence_bits_rs2:i:1;io_sfence_bits_addr:i:50;io_sfence_bits_id:i:16;io_sfence_bits_hv:i:1;io_sfence_bits_hg:i:1;io_csr_satp_asid:i:16;io_csr_vsatp_asid:i:16;io_csr_hgatp_vmid:i:16;io_csr_mbmc_BME:i:1;io_csr_mbmc_CMODE:i:1;io_csr_priv_virt:i:1;io_r_req_0_valid:i:1;io_r_req_0_bits_vpn:i:38;io_r_req_0_bits_s2xlate:i:2;io_r_req_1_valid:i:1;io_r_req_1_bits_vpn:i:38;io_r_req_1_bits_s2xlate:i:2;io_r_req_2_valid:i:1;io_r_req_2_bits_vpn:i:38;io_r_req_2_bits_s2xlate:i:2;io_r_resp_0_bits_hit:o:1;io_r_resp_0_bits_ppn_0:o:36;io_r_resp_0_bits_pbmt_0:o:2;io_r_resp_0_bits_g_pbmt_0:o:2;io_r_resp_0_bits_perm_0_pf:o:1;io_r_resp_0_bits_perm_0_af:o:1;io_r_resp_0_bits_perm_0_v:o:1;io_r_resp_0_bits_perm_0_a:o:1;io_r_resp_0_bits_perm_0_u:o:1;io_r_resp_0_bits_perm_0_x:o:1;io_r_resp_0_bits_perm_0_w:o:1;io_r_resp_0_bits_perm_0_r:o:1;io_r_resp_0_bits_g_perm_0_pf:o:1;io_r_resp_0_bits_g_perm_0_af:o:1;io_r_resp_0_bits_g_perm_0_a:o:1;io_r_resp_0_bits_g_perm_0_x:o:1;io_r_resp_0_bits_s2xlate_0:o:2;io_r_resp_1_bits_hit:o:1;io_r_resp_1_bits_ppn_0:o:36;io_r_resp_1_bits_pbmt_0:o:2;io_r_resp_1_bits_g_pbmt_0:o:2;io_r_resp_1_bits_perm_0_pf:o:1;io_r_resp_1_bits_perm_0_af:o:1;io_r_resp_1_bits_perm_0_v:o:1;io_r_resp_1_bits_perm_0_a:o:1;io_r_resp_1_bits_perm_0_u:o:1;io_r_resp_1_bits_perm_0_x:o:1;io_r_resp_1_bits_perm_0_w:o:1;io_r_resp_1_bits_perm_0_r:o:1;io_r_resp_1_bits_g_perm_0_pf:o:1;io_r_resp_1_bits_g_perm_0_af:o:1;io_r_resp_1_bits_g_perm_0_a:o:1;io_r_resp_1_bits_g_perm_0_x:o:1;io_r_resp_1_bits_s2xlate_0:o:2;io_r_resp_2_bits_hit:o:1;io_r_resp_2_bits_ppn_0:o:36;io_r_resp_2_bits_pbmt_0:o:2;io_r_resp_2_bits_g_pbmt_0:o:2;io_r_resp_2_bits_perm_0_pf:o:1;io_r_resp_2_bits_perm_0_af:o:1;io_r_resp_2_bits_perm_0_v:o:1;io_r_resp_2_bits_perm_0_a:o:1;io_r_resp_2_bits_perm_0_u:o:1;io_r_resp_2_bits_perm_0_x:o:1;io_r_resp_2_bits_perm_0_w:o:1;io_r_resp_2_bits_perm_0_r:o:1;io_r_resp_2_bits_g_perm_0_pf:o:1;io_r_resp_2_bits_g_perm_0_af:o:1;io_r_resp_2_bits_g_perm_0_a:o:1;io_r_resp_2_bits_g_perm_0_x:o:1;io_r_resp_2_bits_s2xlate_0:o:2;io_w_valid:i:1;io_w_bits_wayIdx:i:6;io_w_bits_data_s2xlate:i:2;io_w_bits_data_s1_entry_tag:i:35;io_w_bits_data_s1_entry_asid:i:16;io_w_bits_data_s1_entry_vmid:i:14;io_w_bits_data_s1_entry_n:i:1;io_w_bits_data_s1_entry_pbmt:i:2;io_w_bits_data_s1_entry_perm_d:i:1;io_w_bits_data_s1_entry_perm_a:i:1;io_w_bits_data_s1_entry_perm_g:i:1;io_w_bits_data_s1_entry_perm_u:i:1;io_w_bits_data_s1_entry_perm_x:i:1;io_w_bits_data_s1_entry_perm_w:i:1;io_w_bits_data_s1_entry_perm_r:i:1;io_w_bits_data_s1_entry_level:i:2;io_w_bits_data_s1_entry_v:i:1;io_w_bits_data_s1_entry_ppn:i:41;io_w_bits_data_s1_ppn_low_0:i:3;io_w_bits_data_s1_ppn_low_1:i:3;io_w_bits_data_s1_ppn_low_2:i:3;io_w_bits_data_s1_ppn_low_3:i:3;io_w_bits_data_s1_ppn_low_4:i:3;io_w_bits_data_s1_ppn_low_5:i:3;io_w_bits_data_s1_ppn_low_6:i:3;io_w_bits_data_s1_ppn_low_7:i:3;io_w_bits_data_s1_valididx_0:i:1;io_w_bits_data_s1_valididx_1:i:1;io_w_bits_data_s1_valididx_2:i:1;io_w_bits_data_s1_valididx_3:i:1;io_w_bits_data_s1_valididx_4:i:1;io_w_bits_data_s1_valididx_5:i:1;io_w_bits_data_s1_valididx_6:i:1;io_w_bits_data_s1_valididx_7:i:1;io_w_bits_data_s1_pteidx_0:i:1;io_w_bits_data_s1_pteidx_1:i:1;io_w_bits_data_s1_pteidx_2:i:1;io_w_bits_data_s1_pteidx_3:i:1;io_w_bits_data_s1_pteidx_4:i:1;io_w_bits_data_s1_pteidx_5:i:1;io_w_bits_data_s1_pteidx_6:i:1;io_w_bits_data_s1_pteidx_7:i:1;io_w_bits_data_s1_pf:i:1;io_w_bits_data_s1_af:i:1;io_w_bits_data_s2_entry_tag:i:38;io_w_bits_data_s2_entry_vmid:i:14;io_w_bits_data_s2_entry_n:i:1;io_w_bits_data_s2_entry_pbmt:i:2;io_w_bits_data_s2_entry_ppn:i:38;io_w_bits_data_s2_entry_perm_d:i:1;io_w_bits_data_s2_entry_perm_a:i:1;io_w_bits_data_s2_entry_perm_g:i:1;io_w_bits_data_s2_entry_perm_u:i:1;io_w_bits_data_s2_entry_perm_x:i:1;io_w_bits_data_s2_entry_perm_w:i:1;io_w_bits_data_s2_entry_perm_r:i:1;io_w_bits_data_s2_entry_level:i:2;io_w_bits_data_s2_gpf:i:1;io_w_bits_data_s2_gaf:i:1;io_access_0_touch_ways_valid:o:1;io_access_0_touch_ways_bits:o:6;io_access_1_touch_ways_valid:o:1;io_access_1_touch_ways_bits:o:6;io_access_2_touch_ways_valid:o:1;io_access_2_touch_ways_bits:o:6",
    "TLBFA_1|tlbfa||clock:i:1;reset:i:1;io_sfence_valid:i:1;io_sfence_bits_rs1:i:1;io_sfence_bits_rs2:i:1;io_sfence_bits_addr:i:50;io_sfence_bits_id:i:16;io_sfence_bits_hv:i:1;io_sfence_bits_hg:i:1;io_csr_satp_asid:i:16;io_csr_vsatp_asid:i:16;io_csr_hgatp_vmid:i:16;io_csr_mbmc_BME:i:1;io_csr_mbmc_CMODE:i:1;io_csr_priv_virt:i:1;io_r_req_0_valid:i:1;io_r_req_0_bits_vpn:i:38;io_r_req_0_bits_s2xlate:i:2;io_r_req_1_valid:i:1;io_r_req_1_bits_vpn:i:38;io_r_req_1_bits_s2xlate:i:2;io_r_req_2_valid:i:1;io_r_req_2_bits_vpn:i:38;io_r_req_2_bits_s2xlate:i:2;io_r_req_3_valid:i:1;io_r_req_3_bits_vpn:i:38;io_r_req_3_bits_s2xlate:i:2;io_r_resp_0_bits_hit:o:1;io_r_resp_0_bits_ppn_0:o:36;io_r_resp_0_bits_ppn_1:o:36;io_r_resp_0_bits_pbmt_0:o:2;io_r_resp_0_bits_g_pbmt_0:o:2;io_r_resp_0_bits_perm_0_pf:o:1;io_r_resp_0_bits_perm_0_af:o:1;io_r_resp_0_bits_perm_0_v:o:1;io_r_resp_0_bits_perm_0_d:o:1;io_r_resp_0_bits_perm_0_a:o:1;io_r_resp_0_bits_perm_0_u:o:1;io_r_resp_0_bits_perm_0_x:o:1;io_r_resp_0_bits_perm_0_w:o:1;io_r_resp_0_bits_perm_0_r:o:1;io_r_resp_0_bits_perm_1_pf:o:1;io_r_resp_0_bits_perm_1_af:o:1;io_r_resp_0_bits_perm_1_v:o:1;io_r_resp_0_bits_perm_1_x:o:1;io_r_resp_0_bits_perm_1_w:o:1;io_r_resp_0_bits_perm_1_r:o:1;io_r_resp_0_bits_g_perm_0_pf:o:1;io_r_resp_0_bits_g_perm_0_af:o:1;io_r_resp_0_bits_g_perm_0_d:o:1;io_r_resp_0_bits_g_perm_0_a:o:1;io_r_resp_0_bits_g_perm_0_x:o:1;io_r_resp_0_bits_g_perm_0_w:o:1;io_r_resp_0_bits_g_perm_0_r:o:1;io_r_resp_0_bits_s2xlate_0:o:2;io_r_resp_1_bits_hit:o:1;io_r_resp_1_bits_ppn_0:o:36;io_r_resp_1_bits_ppn_1:o:36;io_r_resp_1_bits_pbmt_0:o:2;io_r_resp_1_bits_g_pbmt_0:o:2;io_r_resp_1_bits_perm_0_pf:o:1;io_r_resp_1_bits_perm_0_af:o:1;io_r_resp_1_bits_perm_0_v:o:1;io_r_resp_1_bits_perm_0_d:o:1;io_r_resp_1_bits_perm_0_a:o:1;io_r_resp_1_bits_perm_0_u:o:1;io_r_resp_1_bits_perm_0_x:o:1;io_r_resp_1_bits_perm_0_w:o:1;io_r_resp_1_bits_perm_0_r:o:1;io_r_resp_1_bits_perm_1_pf:o:1;io_r_resp_1_bits_perm_1_af:o:1;io_r_resp_1_bits_perm_1_v:o:1;io_r_resp_1_bits_perm_1_x:o:1;io_r_resp_1_bits_perm_1_w:o:1;io_r_resp_1_bits_perm_1_r:o:1;io_r_resp_1_bits_g_perm_0_pf:o:1;io_r_resp_1_bits_g_perm_0_af:o:1;io_r_resp_1_bits_g_perm_0_d:o:1;io_r_resp_1_bits_g_perm_0_a:o:1;io_r_resp_1_bits_g_perm_0_x:o:1;io_r_resp_1_bits_g_perm_0_w:o:1;io_r_resp_1_bits_g_perm_0_r:o:1;io_r_resp_1_bits_s2xlate_0:o:2;io_r_resp_2_bits_hit:o:1;io_r_resp_2_bits_ppn_0:o:36;io_r_resp_2_bits_ppn_1:o:36;io_r_resp_2_bits_pbmt_0:o:2;io_r_resp_2_bits_g_pbmt_0:o:2;io_r_resp_2_bits_perm_0_pf:o:1;io_r_resp_2_bits_perm_0_af:o:1;io_r_resp_2_bits_perm_0_v:o:1;io_r_resp_2_bits_perm_0_d:o:1;io_r_resp_2_bits_perm_0_a:o:1;io_r_resp_2_bits_perm_0_u:o:1;io_r_resp_2_bits_perm_0_x:o:1;io_r_resp_2_bits_perm_0_w:o:1;io_r_resp_2_bits_perm_0_r:o:1;io_r_resp_2_bits_perm_1_pf:o:1;io_r_resp_2_bits_perm_1_af:o:1;io_r_resp_2_bits_perm_1_v:o:1;io_r_resp_2_bits_perm_1_x:o:1;io_r_resp_2_bits_perm_1_w:o:1;io_r_resp_2_bits_perm_1_r:o:1;io_r_resp_2_bits_g_perm_0_pf:o:1;io_r_resp_2_bits_g_perm_0_af:o:1;io_r_resp_2_bits_g_perm_0_d:o:1;io_r_resp_2_bits_g_perm_0_a:o:1;io_r_resp_2_bits_g_perm_0_x:o:1;io_r_resp_2_bits_g_perm_0_w:o:1;io_r_resp_2_bits_g_perm_0_r:o:1;io_r_resp_2_bits_s2xlate_0:o:2;io_r_resp_3_bits_hit:o:1;io_r_resp_3_bits_ppn_0:o:36;io_r_resp_3_bits_pbmt_0:o:2;io_r_resp_3_bits_g_pbmt_0:o:2;io_r_resp_3_bits_perm_0_pf:o:1;io_r_resp_3_bits_perm_0_af:o:1;io_r_resp_3_bits_perm_0_v:o:1;io_r_resp_3_bits_perm_0_d:o:1;io_r_resp_3_bits_perm_0_a:o:1;io_r_resp_3_bits_perm_0_u:o:1;io_r_resp_3_bits_perm_0_x:o:1;io_r_resp_3_bits_perm_0_w:o:1;io_r_resp_3_bits_perm_0_r:o:1;io_r_resp_3_bits_g_perm_0_pf:o:1;io_r_resp_3_bits_g_perm_0_af:o:1;io_r_resp_3_bits_g_perm_0_d:o:1;io_r_resp_3_bits_g_perm_0_a:o:1;io_r_resp_3_bits_g_perm_0_x:o:1;io_r_resp_3_bits_g_perm_0_w:o:1;io_r_resp_3_bits_g_perm_0_r:o:1;io_w_valid:i:1;io_w_bits_wayIdx:i:6;io_w_bits_data_s2xlate:i:2;io_w_bits_data_s1_entry_tag:i:35;io_w_bits_data_s1_entry_asid:i:16;io_w_bits_data_s1_entry_vmid:i:14;io_w_bits_data_s1_entry_n:i:1;io_w_bits_data_s1_entry_pbmt:i:2;io_w_bits_data_s1_entry_perm_d:i:1;io_w_bits_data_s1_entry_perm_a:i:1;io_w_bits_data_s1_entry_perm_g:i:1;io_w_bits_data_s1_entry_perm_u:i:1;io_w_bits_data_s1_entry_perm_x:i:1;io_w_bits_data_s1_entry_perm_w:i:1;io_w_bits_data_s1_entry_perm_r:i:1;io_w_bits_data_s1_entry_level:i:2;io_w_bits_data_s1_entry_v:i:1;io_w_bits_data_s1_entry_ppn:i:41;io_w_bits_data_s1_ppn_low_0:i:3;io_w_bits_data_s1_ppn_low_1:i:3;io_w_bits_data_s1_ppn_low_2:i:3;io_w_bits_data_s1_ppn_low_3:i:3;io_w_bits_data_s1_ppn_low_4:i:3;io_w_bits_data_s1_ppn_low_5:i:3;io_w_bits_data_s1_ppn_low_6:i:3;io_w_bits_data_s1_ppn_low_7:i:3;io_w_bits_data_s1_valididx_0:i:1;io_w_bits_data_s1_valididx_1:i:1;io_w_bits_data_s1_valididx_2:i:1;io_w_bits_data_s1_valididx_3:i:1;io_w_bits_data_s1_valididx_4:i:1;io_w_bits_data_s1_valididx_5:i:1;io_w_bits_data_s1_valididx_6:i:1;io_w_bits_data_s1_valididx_7:i:1;io_w_bits_data_s1_pteidx_0:i:1;io_w_bits_data_s1_pteidx_1:i:1;io_w_bits_data_s1_pteidx_2:i:1;io_w_bits_data_s1_pteidx_3:i:1;io_w_bits_data_s1_pteidx_4:i:1;io_w_bits_data_s1_pteidx_5:i:1;io_w_bits_data_s1_pteidx_6:i:1;io_w_bits_data_s1_pteidx_7:i:1;io_w_bits_data_s1_pf:i:1;io_w_bits_data_s1_af:i:1;io_w_bits_data_s2_entry_tag:i:38;io_w_bits_data_s2_entry_vmid:i:14;io_w_bits_data_s2_entry_n:i:1;io_w_bits_data_s2_entry_pbmt:i:2;io_w_bits_data_s2_entry_ppn:i:38;io_w_bits_data_s2_entry_perm_d:i:1;io_w_bits_data_s2_entry_perm_a:i:1;io_w_bits_data_s2_entry_perm_g:i:1;io_w_bits_data_s2_entry_perm_u:i:1;io_w_bits_data_s2_entry_perm_x:i:1;io_w_bits_data_s2_entry_perm_w:i:1;io_w_bits_data_s2_entry_perm_r:i:1;io_w_bits_data_s2_entry_level:i:2;io_w_bits_data_s2_gpf:i:1;io_w_bits_data_s2_gaf:i:1;io_access_0_touch_ways_valid:o:1;io_access_0_touch_ways_bits:o:6;io_access_1_touch_ways_valid:o:1;io_access_1_touch_ways_bits:o:6;io_access_2_touch_ways_valid:o:1;io_access_2_touch_ways_bits:o:6;io_access_3_touch_ways_valid:o:1;io_access_3_touch_ways_bits:o:6",
    "TLBFA_2|tlbfa||clock:i:1;reset:i:1;io_sfence_valid:i:1;io_sfence_bits_rs1:i:1;io_sfence_bits_rs2:i:1;io_sfence_bits_addr:i:50;io_sfence_bits_id:i:16;io_sfence_bits_hv:i:1;io_sfence_bits_hg:i:1;io_csr_satp_asid:i:16;io_csr_vsatp_asid:i:16;io_csr_hgatp_vmid:i:16;io_csr_mbmc_BME:i:1;io_csr_mbmc_CMODE:i:1;io_csr_priv_virt:i:1;io_r_req_0_valid:i:1;io_r_req_0_bits_vpn:i:38;io_r_req_0_bits_s2xlate:i:2;io_r_req_1_valid:i:1;io_r_req_1_bits_vpn:i:38;io_r_req_1_bits_s2xlate:i:2;io_r_resp_0_bits_hit:o:1;io_r_resp_0_bits_ppn_0:o:36;io_r_resp_0_bits_pbmt_0:o:2;io_r_resp_0_bits_g_pbmt_0:o:2;io_r_resp_0_bits_perm_0_pf:o:1;io_r_resp_0_bits_perm_0_af:o:1;io_r_resp_0_bits_perm_0_v:o:1;io_r_resp_0_bits_perm_0_d:o:1;io_r_resp_0_bits_perm_0_a:o:1;io_r_resp_0_bits_perm_0_u:o:1;io_r_resp_0_bits_perm_0_x:o:1;io_r_resp_0_bits_perm_0_w:o:1;io_r_resp_0_bits_perm_0_r:o:1;io_r_resp_0_bits_g_perm_0_pf:o:1;io_r_resp_0_bits_g_perm_0_af:o:1;io_r_resp_0_bits_g_perm_0_d:o:1;io_r_resp_0_bits_g_perm_0_a:o:1;io_r_resp_0_bits_g_perm_0_x:o:1;io_r_resp_0_bits_g_perm_0_w:o:1;io_r_resp_0_bits_g_perm_0_r:o:1;io_r_resp_0_bits_s2xlate_0:o:2;io_r_resp_1_bits_hit:o:1;io_r_resp_1_bits_ppn_0:o:36;io_r_resp_1_bits_pbmt_0:o:2;io_r_resp_1_bits_g_pbmt_0:o:2;io_r_resp_1_bits_perm_0_pf:o:1;io_r_resp_1_bits_perm_0_af:o:1;io_r_resp_1_bits_perm_0_v:o:1;io_r_resp_1_bits_perm_0_d:o:1;io_r_resp_1_bits_perm_0_a:o:1;io_r_resp_1_bits_perm_0_u:o:1;io_r_resp_1_bits_perm_0_x:o:1;io_r_resp_1_bits_perm_0_w:o:1;io_r_resp_1_bits_perm_0_r:o:1;io_r_resp_1_bits_g_perm_0_pf:o:1;io_r_resp_1_bits_g_perm_0_af:o:1;io_r_resp_1_bits_g_perm_0_d:o:1;io_r_resp_1_bits_g_perm_0_a:o:1;io_r_resp_1_bits_g_perm_0_x:o:1;io_r_resp_1_bits_g_perm_0_w:o:1;io_r_resp_1_bits_g_perm_0_r:o:1;io_r_resp_1_bits_s2xlate_0:o:2;io_w_valid:i:1;io_w_bits_wayIdx:i:6;io_w_bits_data_s2xlate:i:2;io_w_bits_data_s1_entry_tag:i:35;io_w_bits_data_s1_entry_asid:i:16;io_w_bits_data_s1_entry_vmid:i:14;io_w_bits_data_s1_entry_n:i:1;io_w_bits_data_s1_entry_pbmt:i:2;io_w_bits_data_s1_entry_perm_d:i:1;io_w_bits_data_s1_entry_perm_a:i:1;io_w_bits_data_s1_entry_perm_g:i:1;io_w_bits_data_s1_entry_perm_u:i:1;io_w_bits_data_s1_entry_perm_x:i:1;io_w_bits_data_s1_entry_perm_w:i:1;io_w_bits_data_s1_entry_perm_r:i:1;io_w_bits_data_s1_entry_level:i:2;io_w_bits_data_s1_entry_v:i:1;io_w_bits_data_s1_entry_ppn:i:41;io_w_bits_data_s1_ppn_low_0:i:3;io_w_bits_data_s1_ppn_low_1:i:3;io_w_bits_data_s1_ppn_low_2:i:3;io_w_bits_data_s1_ppn_low_3:i:3;io_w_bits_data_s1_ppn_low_4:i:3;io_w_bits_data_s1_ppn_low_5:i:3;io_w_bits_data_s1_ppn_low_6:i:3;io_w_bits_data_s1_ppn_low_7:i:3;io_w_bits_data_s1_valididx_0:i:1;io_w_bits_data_s1_valididx_1:i:1;io_w_bits_data_s1_valididx_2:i:1;io_w_bits_data_s1_valididx_3:i:1;io_w_bits_data_s1_valididx_4:i:1;io_w_bits_data_s1_valididx_5:i:1;io_w_bits_data_s1_valididx_6:i:1;io_w_bits_data_s1_valididx_7:i:1;io_w_bits_data_s1_pteidx_0:i:1;io_w_bits_data_s1_pteidx_1:i:1;io_w_bits_data_s1_pteidx_2:i:1;io_w_bits_data_s1_pteidx_3:i:1;io_w_bits_data_s1_pteidx_4:i:1;io_w_bits_data_s1_pteidx_5:i:1;io_w_bits_data_s1_pteidx_6:i:1;io_w_bits_data_s1_pteidx_7:i:1;io_w_bits_data_s1_pf:i:1;io_w_bits_data_s1_af:i:1;io_w_bits_data_s2_entry_tag:i:38;io_w_bits_data_s2_entry_vmid:i:14;io_w_bits_data_s2_entry_n:i:1;io_w_bits_data_s2_entry_pbmt:i:2;io_w_bits_data_s2_entry_ppn:i:38;io_w_bits_data_s2_entry_perm_d:i:1;io_w_bits_data_s2_entry_perm_a:i:1;io_w_bits_data_s2_entry_perm_g:i:1;io_w_bits_data_s2_entry_perm_u:i:1;io_w_bits_data_s2_entry_perm_x:i:1;io_w_bits_data_s2_entry_perm_w:i:1;io_w_bits_data_s2_entry_perm_r:i:1;io_w_bits_data_s2_entry_level:i:2;io_w_bits_data_s2_gpf:i:1;io_w_bits_data_s2_gaf:i:1;io_access_0_touch_ways_valid:o:1;io_access_0_touch_ways_bits:o:6;io_access_1_touch_ways_valid:o:1;io_access_1_touch_ways_bits:o:6",
    "TLBFA_3|tlbfa||clock:i:1;reset:i:1;io_sfence_valid:i:1;io_sfence_bits_rs1:i:1;io_sfence_bits_rs2:i:1;io_sfence_bits_addr:i:50;io_sfence_bits_id:i:16;io_sfence_bits_hv:i:1;io_sfence_bits_hg:i:1;io_csr_satp_asid:i:16;io_csr_vsatp_asid:i:16;io_csr_hgatp_vmid:i:16;io_csr_mbmc_BME:i:1;io_csr_mbmc_CMODE:i:1;io_csr_priv_virt:i:1;io_r_req_0_valid:i:1;io_r_req_0_bits_vpn:i:38;io_r_req_0_bits_s2xlate:i:2;io_r_req_1_valid:i:1;io_r_req_1_bits_vpn:i:38;io_r_req_1_bits_s2xlate:i:2;io_r_resp_0_bits_hit:o:1;io_r_resp_0_bits_ppn_0:o:36;io_r_resp_0_bits_pbmt_0:o:2;io_r_resp_0_bits_g_pbmt_0:o:2;io_r_resp_0_bits_perm_0_pf:o:1;io_r_resp_0_bits_perm_0_af:o:1;io_r_resp_0_bits_perm_0_v:o:1;io_r_resp_0_bits_perm_0_d:o:1;io_r_resp_0_bits_perm_0_a:o:1;io_r_resp_0_bits_perm_0_u:o:1;io_r_resp_0_bits_perm_0_x:o:1;io_r_resp_0_bits_perm_0_w:o:1;io_r_resp_0_bits_perm_0_r:o:1;io_r_resp_0_bits_g_perm_0_pf:o:1;io_r_resp_0_bits_g_perm_0_af:o:1;io_r_resp_0_bits_g_perm_0_d:o:1;io_r_resp_0_bits_g_perm_0_a:o:1;io_r_resp_0_bits_g_perm_0_x:o:1;io_r_resp_0_bits_g_perm_0_w:o:1;io_r_resp_0_bits_g_perm_0_r:o:1;io_r_resp_1_bits_hit:o:1;io_r_resp_1_bits_ppn_0:o:36;io_r_resp_1_bits_pbmt_0:o:2;io_r_resp_1_bits_g_pbmt_0:o:2;io_r_resp_1_bits_perm_0_pf:o:1;io_r_resp_1_bits_perm_0_af:o:1;io_r_resp_1_bits_perm_0_v:o:1;io_r_resp_1_bits_perm_0_d:o:1;io_r_resp_1_bits_perm_0_a:o:1;io_r_resp_1_bits_perm_0_u:o:1;io_r_resp_1_bits_perm_0_x:o:1;io_r_resp_1_bits_perm_0_w:o:1;io_r_resp_1_bits_perm_0_r:o:1;io_r_resp_1_bits_g_perm_0_pf:o:1;io_r_resp_1_bits_g_perm_0_af:o:1;io_r_resp_1_bits_g_perm_0_d:o:1;io_r_resp_1_bits_g_perm_0_a:o:1;io_r_resp_1_bits_g_perm_0_x:o:1;io_r_resp_1_bits_g_perm_0_w:o:1;io_r_resp_1_bits_g_perm_0_r:o:1;io_w_valid:i:1;io_w_bits_wayIdx:i:6;io_w_bits_data_s2xlate:i:2;io_w_bits_data_s1_entry_tag:i:35;io_w_bits_data_s1_entry_asid:i:16;io_w_bits_data_s1_entry_vmid:i:14;io_w_bits_data_s1_entry_n:i:1;io_w_bits_data_s1_entry_pbmt:i:2;io_w_bits_data_s1_entry_perm_d:i:1;io_w_bits_data_s1_entry_perm_a:i:1;io_w_bits_data_s1_entry_perm_g:i:1;io_w_bits_data_s1_entry_perm_u:i:1;io_w_bits_data_s1_entry_perm_x:i:1;io_w_bits_data_s1_entry_perm_w:i:1;io_w_bits_data_s1_entry_perm_r:i:1;io_w_bits_data_s1_entry_level:i:2;io_w_bits_data_s1_entry_v:i:1;io_w_bits_data_s1_entry_ppn:i:41;io_w_bits_data_s1_ppn_low_0:i:3;io_w_bits_data_s1_ppn_low_1:i:3;io_w_bits_data_s1_ppn_low_2:i:3;io_w_bits_data_s1_ppn_low_3:i:3;io_w_bits_data_s1_ppn_low_4:i:3;io_w_bits_data_s1_ppn_low_5:i:3;io_w_bits_data_s1_ppn_low_6:i:3;io_w_bits_data_s1_ppn_low_7:i:3;io_w_bits_data_s1_valididx_0:i:1;io_w_bits_data_s1_valididx_1:i:1;io_w_bits_data_s1_valididx_2:i:1;io_w_bits_data_s1_valididx_3:i:1;io_w_bits_data_s1_valididx_4:i:1;io_w_bits_data_s1_valididx_5:i:1;io_w_bits_data_s1_valididx_6:i:1;io_w_bits_data_s1_valididx_7:i:1;io_w_bits_data_s1_pteidx_0:i:1;io_w_bits_data_s1_pteidx_1:i:1;io_w_bits_data_s1_pteidx_2:i:1;io_w_bits_data_s1_pteidx_3:i:1;io_w_bits_data_s1_pteidx_4:i:1;io_w_bits_data_s1_pteidx_5:i:1;io_w_bits_data_s1_pteidx_6:i:1;io_w_bits_data_s1_pteidx_7:i:1;io_w_bits_data_s1_pf:i:1;io_w_bits_data_s1_af:i:1;io_w_bits_data_s2_entry_tag:i:38;io_w_bits_data_s2_entry_vmid:i:14;io_w_bits_data_s2_entry_n:i:1;io_w_bits_data_s2_entry_pbmt:i:2;io_w_bits_data_s2_entry_ppn:i:38;io_w_bits_data_s2_entry_perm_d:i:1;io_w_bits_data_s2_entry_perm_a:i:1;io_w_bits_data_s2_entry_perm_g:i:1;io_w_bits_data_s2_entry_perm_u:i:1;io_w_bits_data_s2_entry_perm_x:i:1;io_w_bits_data_s2_entry_perm_w:i:1;io_w_bits_data_s2_entry_perm_r:i:1;io_w_bits_data_s2_entry_level:i:2;io_w_bits_data_s2_gpf:i:1;io_w_bits_data_s2_gaf:i:1;io_access_0_touch_ways_valid:o:1;io_access_0_touch_ways_bits:o:6;io_access_1_touch_ways_valid:o:1;io_access_1_touch_ways_bits:o:6",
    "TlbStorageWrapper|tlbsw||clock:i:1;reset:i:1;io_sfence_valid:i:1;io_sfence_bits_rs1:i:1;io_sfence_bits_rs2:i:1;io_sfence_bits_addr:i:50;io_sfence_bits_id:i:16;io_sfence_bits_hv:i:1;io_sfence_bits_hg:i:1;io_csr_satp_asid:i:16;io_csr_vsatp_asid:i:16;io_csr_hgatp_vmid:i:16;io_csr_mbmc_BME:i:1;io_csr_mbmc_CMODE:i:1;io_csr_priv_virt:i:1;io_r_req_0_valid:i:1;io_r_req_0_bits_vpn:i:38;io_r_req_0_bits_s2xlate:i:2;io_r_req_1_valid:i:1;io_r_req_1_bits_vpn:i:38;io_r_req_1_bits_s2xlate:i:2;io_r_req_2_valid:i:1;io_r_req_2_bits_vpn:i:38;io_r_req_2_bits_s2xlate:i:2;io_r_resp_0_bits_hit:o:1;io_r_resp_0_bits_ppn_0:o:36;io_r_resp_0_bits_pbmt_0:o:2;io_r_resp_0_bits_g_pbmt_0:o:2;io_r_resp_0_bits_perm_0_pf:o:1;io_r_resp_0_bits_perm_0_af:o:1;io_r_resp_0_bits_perm_0_v:o:1;io_r_resp_0_bits_perm_0_a:o:1;io_r_resp_0_bits_perm_0_u:o:1;io_r_resp_0_bits_perm_0_x:o:1;io_r_resp_0_bits_perm_0_w:o:1;io_r_resp_0_bits_perm_0_r:o:1;io_r_resp_0_bits_g_perm_0_pf:o:1;io_r_resp_0_bits_g_perm_0_af:o:1;io_r_resp_0_bits_g_perm_0_a:o:1;io_r_resp_0_bits_g_perm_0_x:o:1;io_r_resp_0_bits_s2xlate_0:o:2;io_r_resp_1_bits_hit:o:1;io_r_resp_1_bits_ppn_0:o:36;io_r_resp_1_bits_pbmt_0:o:2;io_r_resp_1_bits_g_pbmt_0:o:2;io_r_resp_1_bits_perm_0_pf:o:1;io_r_resp_1_bits_perm_0_af:o:1;io_r_resp_1_bits_perm_0_v:o:1;io_r_resp_1_bits_perm_0_a:o:1;io_r_resp_1_bits_perm_0_u:o:1;io_r_resp_1_bits_perm_0_x:o:1;io_r_resp_1_bits_perm_0_w:o:1;io_r_resp_1_bits_perm_0_r:o:1;io_r_resp_1_bits_g_perm_0_pf:o:1;io_r_resp_1_bits_g_perm_0_af:o:1;io_r_resp_1_bits_g_perm_0_a:o:1;io_r_resp_1_bits_g_perm_0_x:o:1;io_r_resp_1_bits_s2xlate_0:o:2;io_r_resp_2_bits_hit:o:1;io_r_resp_2_bits_ppn_0:o:36;io_r_resp_2_bits_pbmt_0:o:2;io_r_resp_2_bits_g_pbmt_0:o:2;io_r_resp_2_bits_perm_0_pf:o:1;io_r_resp_2_bits_perm_0_af:o:1;io_r_resp_2_bits_perm_0_v:o:1;io_r_resp_2_bits_perm_0_a:o:1;io_r_resp_2_bits_perm_0_u:o:1;io_r_resp_2_bits_perm_0_x:o:1;io_r_resp_2_bits_perm_0_w:o:1;io_r_resp_2_bits_perm_0_r:o:1;io_r_resp_2_bits_g_perm_0_pf:o:1;io_r_resp_2_bits_g_perm_0_af:o:1;io_r_resp_2_bits_g_perm_0_a:o:1;io_r_resp_2_bits_g_perm_0_x:o:1;io_r_resp_2_bits_s2xlate_0:o:2;io_w_valid:i:1;io_w_bits_data_s2xlate:i:2;io_w_bits_data_s1_entry_tag:i:35;io_w_bits_data_s1_entry_asid:i:16;io_w_bits_data_s1_entry_vmid:i:14;io_w_bits_data_s1_entry_n:i:1;io_w_bits_data_s1_entry_pbmt:i:2;io_w_bits_data_s1_entry_perm_d:i:1;io_w_bits_data_s1_entry_perm_a:i:1;io_w_bits_data_s1_entry_perm_g:i:1;io_w_bits_data_s1_entry_perm_u:i:1;io_w_bits_data_s1_entry_perm_x:i:1;io_w_bits_data_s1_entry_perm_w:i:1;io_w_bits_data_s1_entry_perm_r:i:1;io_w_bits_data_s1_entry_level:i:2;io_w_bits_data_s1_entry_v:i:1;io_w_bits_data_s1_entry_ppn:i:41;io_w_bits_data_s1_ppn_low_0:i:3;io_w_bits_data_s1_ppn_low_1:i:3;io_w_bits_data_s1_ppn_low_2:i:3;io_w_bits_data_s1_ppn_low_3:i:3;io_w_bits_data_s1_ppn_low_4:i:3;io_w_bits_data_s1_ppn_low_5:i:3;io_w_bits_data_s1_ppn_low_6:i:3;io_w_bits_data_s1_ppn_low_7:i:3;io_w_bits_data_s1_valididx_0:i:1;io_w_bits_data_s1_valididx_1:i:1;io_w_bits_data_s1_valididx_2:i:1;io_w_bits_data_s1_valididx_3:i:1;io_w_bits_data_s1_valididx_4:i:1;io_w_bits_data_s1_valididx_5:i:1;io_w_bits_data_s1_valididx_6:i:1;io_w_bits_data_s1_valididx_7:i:1;io_w_bits_data_s1_pteidx_0:i:1;io_w_bits_data_s1_pteidx_1:i:1;io_w_bits_data_s1_pteidx_2:i:1;io_w_bits_data_s1_pteidx_3:i:1;io_w_bits_data_s1_pteidx_4:i:1;io_w_bits_data_s1_pteidx_5:i:1;io_w_bits_data_s1_pteidx_6:i:1;io_w_bits_data_s1_pteidx_7:i:1;io_w_bits_data_s1_pf:i:1;io_w_bits_data_s1_af:i:1;io_w_bits_data_s2_entry_tag:i:38;io_w_bits_data_s2_entry_vmid:i:14;io_w_bits_data_s2_entry_n:i:1;io_w_bits_data_s2_entry_pbmt:i:2;io_w_bits_data_s2_entry_ppn:i:38;io_w_bits_data_s2_entry_perm_d:i:1;io_w_bits_data_s2_entry_perm_a:i:1;io_w_bits_data_s2_entry_perm_g:i:1;io_w_bits_data_s2_entry_perm_u:i:1;io_w_bits_data_s2_entry_perm_x:i:1;io_w_bits_data_s2_entry_perm_w:i:1;io_w_bits_data_s2_entry_perm_r:i:1;io_w_bits_data_s2_entry_level:i:2;io_w_bits_data_s2_gpf:i:1;io_w_bits_data_s2_gaf:i:1",
    "TlbStorageWrapper_1|tlbsw||clock:i:1;reset:i:1;io_sfence_valid:i:1;io_sfence_bits_rs1:i:1;io_sfence_bits_rs2:i:1;io_sfence_bits_addr:i:50;io_sfence_bits_id:i:16;io_sfence_bits_hv:i:1;io_sfence_bits_hg:i:1;io_csr_satp_asid:i:16;io_csr_vsatp_asid:i:16;io_csr_hgatp_vmid:i:16;io_csr_mbmc_BME:i:1;io_csr_mbmc_CMODE:i:1;io_csr_priv_virt:i:1;io_r_req_0_valid:i:1;io_r_req_0_bits_vpn:i:38;io_r_req_0_bits_s2xlate:i:2;io_r_req_1_valid:i:1;io_r_req_1_bits_vpn:i:38;io_r_req_1_bits_s2xlate:i:2;io_r_req_2_valid:i:1;io_r_req_2_bits_vpn:i:38;io_r_req_2_bits_s2xlate:i:2;io_r_req_3_valid:i:1;io_r_req_3_bits_vpn:i:38;io_r_req_3_bits_s2xlate:i:2;io_r_resp_0_bits_hit:o:1;io_r_resp_0_bits_ppn_0:o:36;io_r_resp_0_bits_ppn_1:o:36;io_r_resp_0_bits_pbmt_0:o:2;io_r_resp_0_bits_g_pbmt_0:o:2;io_r_resp_0_bits_perm_0_pf:o:1;io_r_resp_0_bits_perm_0_af:o:1;io_r_resp_0_bits_perm_0_v:o:1;io_r_resp_0_bits_perm_0_d:o:1;io_r_resp_0_bits_perm_0_a:o:1;io_r_resp_0_bits_perm_0_u:o:1;io_r_resp_0_bits_perm_0_x:o:1;io_r_resp_0_bits_perm_0_w:o:1;io_r_resp_0_bits_perm_0_r:o:1;io_r_resp_0_bits_perm_1_pf:o:1;io_r_resp_0_bits_perm_1_af:o:1;io_r_resp_0_bits_perm_1_v:o:1;io_r_resp_0_bits_perm_1_x:o:1;io_r_resp_0_bits_perm_1_w:o:1;io_r_resp_0_bits_perm_1_r:o:1;io_r_resp_0_bits_g_perm_0_pf:o:1;io_r_resp_0_bits_g_perm_0_af:o:1;io_r_resp_0_bits_g_perm_0_d:o:1;io_r_resp_0_bits_g_perm_0_a:o:1;io_r_resp_0_bits_g_perm_0_x:o:1;io_r_resp_0_bits_g_perm_0_w:o:1;io_r_resp_0_bits_g_perm_0_r:o:1;io_r_resp_0_bits_s2xlate_0:o:2;io_r_resp_1_bits_hit:o:1;io_r_resp_1_bits_ppn_0:o:36;io_r_resp_1_bits_ppn_1:o:36;io_r_resp_1_bits_pbmt_0:o:2;io_r_resp_1_bits_g_pbmt_0:o:2;io_r_resp_1_bits_perm_0_pf:o:1;io_r_resp_1_bits_perm_0_af:o:1;io_r_resp_1_bits_perm_0_v:o:1;io_r_resp_1_bits_perm_0_d:o:1;io_r_resp_1_bits_perm_0_a:o:1;io_r_resp_1_bits_perm_0_u:o:1;io_r_resp_1_bits_perm_0_x:o:1;io_r_resp_1_bits_perm_0_w:o:1;io_r_resp_1_bits_perm_0_r:o:1;io_r_resp_1_bits_perm_1_pf:o:1;io_r_resp_1_bits_perm_1_af:o:1;io_r_resp_1_bits_perm_1_v:o:1;io_r_resp_1_bits_perm_1_x:o:1;io_r_resp_1_bits_perm_1_w:o:1;io_r_resp_1_bits_perm_1_r:o:1;io_r_resp_1_bits_g_perm_0_pf:o:1;io_r_resp_1_bits_g_perm_0_af:o:1;io_r_resp_1_bits_g_perm_0_d:o:1;io_r_resp_1_bits_g_perm_0_a:o:1;io_r_resp_1_bits_g_perm_0_x:o:1;io_r_resp_1_bits_g_perm_0_w:o:1;io_r_resp_1_bits_g_perm_0_r:o:1;io_r_resp_1_bits_s2xlate_0:o:2;io_r_resp_2_bits_hit:o:1;io_r_resp_2_bits_ppn_0:o:36;io_r_resp_2_bits_ppn_1:o:36;io_r_resp_2_bits_pbmt_0:o:2;io_r_resp_2_bits_g_pbmt_0:o:2;io_r_resp_2_bits_perm_0_pf:o:1;io_r_resp_2_bits_perm_0_af:o:1;io_r_resp_2_bits_perm_0_v:o:1;io_r_resp_2_bits_perm_0_d:o:1;io_r_resp_2_bits_perm_0_a:o:1;io_r_resp_2_bits_perm_0_u:o:1;io_r_resp_2_bits_perm_0_x:o:1;io_r_resp_2_bits_perm_0_w:o:1;io_r_resp_2_bits_perm_0_r:o:1;io_r_resp_2_bits_perm_1_pf:o:1;io_r_resp_2_bits_perm_1_af:o:1;io_r_resp_2_bits_perm_1_v:o:1;io_r_resp_2_bits_perm_1_x:o:1;io_r_resp_2_bits_perm_1_w:o:1;io_r_resp_2_bits_perm_1_r:o:1;io_r_resp_2_bits_g_perm_0_pf:o:1;io_r_resp_2_bits_g_perm_0_af:o:1;io_r_resp_2_bits_g_perm_0_d:o:1;io_r_resp_2_bits_g_perm_0_a:o:1;io_r_resp_2_bits_g_perm_0_x:o:1;io_r_resp_2_bits_g_perm_0_w:o:1;io_r_resp_2_bits_g_perm_0_r:o:1;io_r_resp_2_bits_s2xlate_0:o:2;io_r_resp_3_bits_hit:o:1;io_r_resp_3_bits_ppn_0:o:36;io_r_resp_3_bits_pbmt_0:o:2;io_r_resp_3_bits_g_pbmt_0:o:2;io_r_resp_3_bits_perm_0_pf:o:1;io_r_resp_3_bits_perm_0_af:o:1;io_r_resp_3_bits_perm_0_v:o:1;io_r_resp_3_bits_perm_0_d:o:1;io_r_resp_3_bits_perm_0_a:o:1;io_r_resp_3_bits_perm_0_u:o:1;io_r_resp_3_bits_perm_0_x:o:1;io_r_resp_3_bits_perm_0_w:o:1;io_r_resp_3_bits_perm_0_r:o:1;io_r_resp_3_bits_g_perm_0_pf:o:1;io_r_resp_3_bits_g_perm_0_af:o:1;io_r_resp_3_bits_g_perm_0_d:o:1;io_r_resp_3_bits_g_perm_0_a:o:1;io_r_resp_3_bits_g_perm_0_x:o:1;io_r_resp_3_bits_g_perm_0_w:o:1;io_r_resp_3_bits_g_perm_0_r:o:1;io_w_valid:i:1;io_w_bits_data_s2xlate:i:2;io_w_bits_data_s1_entry_tag:i:35;io_w_bits_data_s1_entry_asid:i:16;io_w_bits_data_s1_entry_vmid:i:14;io_w_bits_data_s1_entry_n:i:1;io_w_bits_data_s1_entry_pbmt:i:2;io_w_bits_data_s1_entry_perm_d:i:1;io_w_bits_data_s1_entry_perm_a:i:1;io_w_bits_data_s1_entry_perm_g:i:1;io_w_bits_data_s1_entry_perm_u:i:1;io_w_bits_data_s1_entry_perm_x:i:1;io_w_bits_data_s1_entry_perm_w:i:1;io_w_bits_data_s1_entry_perm_r:i:1;io_w_bits_data_s1_entry_level:i:2;io_w_bits_data_s1_entry_v:i:1;io_w_bits_data_s1_entry_ppn:i:41;io_w_bits_data_s1_ppn_low_0:i:3;io_w_bits_data_s1_ppn_low_1:i:3;io_w_bits_data_s1_ppn_low_2:i:3;io_w_bits_data_s1_ppn_low_3:i:3;io_w_bits_data_s1_ppn_low_4:i:3;io_w_bits_data_s1_ppn_low_5:i:3;io_w_bits_data_s1_ppn_low_6:i:3;io_w_bits_data_s1_ppn_low_7:i:3;io_w_bits_data_s1_valididx_0:i:1;io_w_bits_data_s1_valididx_1:i:1;io_w_bits_data_s1_valididx_2:i:1;io_w_bits_data_s1_valididx_3:i:1;io_w_bits_data_s1_valididx_4:i:1;io_w_bits_data_s1_valididx_5:i:1;io_w_bits_data_s1_valididx_6:i:1;io_w_bits_data_s1_valididx_7:i:1;io_w_bits_data_s1_pteidx_0:i:1;io_w_bits_data_s1_pteidx_1:i:1;io_w_bits_data_s1_pteidx_2:i:1;io_w_bits_data_s1_pteidx_3:i:1;io_w_bits_data_s1_pteidx_4:i:1;io_w_bits_data_s1_pteidx_5:i:1;io_w_bits_data_s1_pteidx_6:i:1;io_w_bits_data_s1_pteidx_7:i:1;io_w_bits_data_s1_pf:i:1;io_w_bits_data_s1_af:i:1;io_w_bits_data_s2_entry_tag:i:38;io_w_bits_data_s2_entry_vmid:i:14;io_w_bits_data_s2_entry_n:i:1;io_w_bits_data_s2_entry_pbmt:i:2;io_w_bits_data_s2_entry_ppn:i:38;io_w_bits_data_s2_entry_perm_d:i:1;io_w_bits_data_s2_entry_perm_a:i:1;io_w_bits_data_s2_entry_perm_g:i:1;io_w_bits_data_s2_entry_perm_u:i:1;io_w_bits_data_s2_entry_perm_x:i:1;io_w_bits_data_s2_entry_perm_w:i:1;io_w_bits_data_s2_entry_perm_r:i:1;io_w_bits_data_s2_entry_level:i:2;io_w_bits_data_s2_gpf:i:1;io_w_bits_data_s2_gaf:i:1",
    "TlbStorageWrapper_2|tlbsw||clock:i:1;reset:i:1;io_sfence_valid:i:1;io_sfence_bits_rs1:i:1;io_sfence_bits_rs2:i:1;io_sfence_bits_addr:i:50;io_sfence_bits_id:i:16;io_sfence_bits_hv:i:1;io_sfence_bits_hg:i:1;io_csr_satp_asid:i:16;io_csr_vsatp_asid:i:16;io_csr_hgatp_vmid:i:16;io_csr_mbmc_BME:i:1;io_csr_mbmc_CMODE:i:1;io_csr_priv_virt:i:1;io_r_req_0_valid:i:1;io_r_req_0_bits_vpn:i:38;io_r_req_0_bits_s2xlate:i:2;io_r_req_1_valid:i:1;io_r_req_1_bits_vpn:i:38;io_r_req_1_bits_s2xlate:i:2;io_r_resp_0_bits_hit:o:1;io_r_resp_0_bits_ppn_0:o:36;io_r_resp_0_bits_pbmt_0:o:2;io_r_resp_0_bits_g_pbmt_0:o:2;io_r_resp_0_bits_perm_0_pf:o:1;io_r_resp_0_bits_perm_0_af:o:1;io_r_resp_0_bits_perm_0_v:o:1;io_r_resp_0_bits_perm_0_d:o:1;io_r_resp_0_bits_perm_0_a:o:1;io_r_resp_0_bits_perm_0_u:o:1;io_r_resp_0_bits_perm_0_x:o:1;io_r_resp_0_bits_perm_0_w:o:1;io_r_resp_0_bits_perm_0_r:o:1;io_r_resp_0_bits_g_perm_0_pf:o:1;io_r_resp_0_bits_g_perm_0_af:o:1;io_r_resp_0_bits_g_perm_0_d:o:1;io_r_resp_0_bits_g_perm_0_a:o:1;io_r_resp_0_bits_g_perm_0_x:o:1;io_r_resp_0_bits_g_perm_0_w:o:1;io_r_resp_0_bits_g_perm_0_r:o:1;io_r_resp_0_bits_s2xlate_0:o:2;io_r_resp_1_bits_hit:o:1;io_r_resp_1_bits_ppn_0:o:36;io_r_resp_1_bits_pbmt_0:o:2;io_r_resp_1_bits_g_pbmt_0:o:2;io_r_resp_1_bits_perm_0_pf:o:1;io_r_resp_1_bits_perm_0_af:o:1;io_r_resp_1_bits_perm_0_v:o:1;io_r_resp_1_bits_perm_0_d:o:1;io_r_resp_1_bits_perm_0_a:o:1;io_r_resp_1_bits_perm_0_u:o:1;io_r_resp_1_bits_perm_0_x:o:1;io_r_resp_1_bits_perm_0_w:o:1;io_r_resp_1_bits_perm_0_r:o:1;io_r_resp_1_bits_g_perm_0_pf:o:1;io_r_resp_1_bits_g_perm_0_af:o:1;io_r_resp_1_bits_g_perm_0_d:o:1;io_r_resp_1_bits_g_perm_0_a:o:1;io_r_resp_1_bits_g_perm_0_x:o:1;io_r_resp_1_bits_g_perm_0_w:o:1;io_r_resp_1_bits_g_perm_0_r:o:1;io_r_resp_1_bits_s2xlate_0:o:2;io_w_valid:i:1;io_w_bits_data_s2xlate:i:2;io_w_bits_data_s1_entry_tag:i:35;io_w_bits_data_s1_entry_asid:i:16;io_w_bits_data_s1_entry_vmid:i:14;io_w_bits_data_s1_entry_n:i:1;io_w_bits_data_s1_entry_pbmt:i:2;io_w_bits_data_s1_entry_perm_d:i:1;io_w_bits_data_s1_entry_perm_a:i:1;io_w_bits_data_s1_entry_perm_g:i:1;io_w_bits_data_s1_entry_perm_u:i:1;io_w_bits_data_s1_entry_perm_x:i:1;io_w_bits_data_s1_entry_perm_w:i:1;io_w_bits_data_s1_entry_perm_r:i:1;io_w_bits_data_s1_entry_level:i:2;io_w_bits_data_s1_entry_v:i:1;io_w_bits_data_s1_entry_ppn:i:41;io_w_bits_data_s1_ppn_low_0:i:3;io_w_bits_data_s1_ppn_low_1:i:3;io_w_bits_data_s1_ppn_low_2:i:3;io_w_bits_data_s1_ppn_low_3:i:3;io_w_bits_data_s1_ppn_low_4:i:3;io_w_bits_data_s1_ppn_low_5:i:3;io_w_bits_data_s1_ppn_low_6:i:3;io_w_bits_data_s1_ppn_low_7:i:3;io_w_bits_data_s1_valididx_0:i:1;io_w_bits_data_s1_valididx_1:i:1;io_w_bits_data_s1_valididx_2:i:1;io_w_bits_data_s1_valididx_3:i:1;io_w_bits_data_s1_valididx_4:i:1;io_w_bits_data_s1_valididx_5:i:1;io_w_bits_data_s1_valididx_6:i:1;io_w_bits_data_s1_valididx_7:i:1;io_w_bits_data_s1_pteidx_0:i:1;io_w_bits_data_s1_pteidx_1:i:1;io_w_bits_data_s1_pteidx_2:i:1;io_w_bits_data_s1_pteidx_3:i:1;io_w_bits_data_s1_pteidx_4:i:1;io_w_bits_data_s1_pteidx_5:i:1;io_w_bits_data_s1_pteidx_6:i:1;io_w_bits_data_s1_pteidx_7:i:1;io_w_bits_data_s1_pf:i:1;io_w_bits_data_s1_af:i:1;io_w_bits_data_s2_entry_tag:i:38;io_w_bits_data_s2_entry_vmid:i:14;io_w_bits_data_s2_entry_n:i:1;io_w_bits_data_s2_entry_pbmt:i:2;io_w_bits_data_s2_entry_ppn:i:38;io_w_bits_data_s2_entry_perm_d:i:1;io_w_bits_data_s2_entry_perm_a:i:1;io_w_bits_data_s2_entry_perm_g:i:1;io_w_bits_data_s2_entry_perm_u:i:1;io_w_bits_data_s2_entry_perm_x:i:1;io_w_bits_data_s2_entry_perm_w:i:1;io_w_bits_data_s2_entry_perm_r:i:1;io_w_bits_data_s2_entry_level:i:2;io_w_bits_data_s2_gpf:i:1;io_w_bits_data_s2_gaf:i:1",
    "TlbStorageWrapper_3|tlbsw||clock:i:1;reset:i:1;io_sfence_valid:i:1;io_sfence_bits_rs1:i:1;io_sfence_bits_rs2:i:1;io_sfence_bits_addr:i:50;io_sfence_bits_id:i:16;io_sfence_bits_hv:i:1;io_sfence_bits_hg:i:1;io_csr_satp_asid:i:16;io_csr_vsatp_asid:i:16;io_csr_hgatp_vmid:i:16;io_csr_mbmc_BME:i:1;io_csr_mbmc_CMODE:i:1;io_csr_priv_virt:i:1;io_r_req_0_valid:i:1;io_r_req_0_bits_vpn:i:38;io_r_req_0_bits_s2xlate:i:2;io_r_req_1_valid:i:1;io_r_req_1_bits_vpn:i:38;io_r_req_1_bits_s2xlate:i:2;io_r_resp_0_bits_hit:o:1;io_r_resp_0_bits_ppn_0:o:36;io_r_resp_0_bits_pbmt_0:o:2;io_r_resp_0_bits_g_pbmt_0:o:2;io_r_resp_0_bits_perm_0_pf:o:1;io_r_resp_0_bits_perm_0_af:o:1;io_r_resp_0_bits_perm_0_v:o:1;io_r_resp_0_bits_perm_0_d:o:1;io_r_resp_0_bits_perm_0_a:o:1;io_r_resp_0_bits_perm_0_u:o:1;io_r_resp_0_bits_perm_0_x:o:1;io_r_resp_0_bits_perm_0_w:o:1;io_r_resp_0_bits_perm_0_r:o:1;io_r_resp_0_bits_g_perm_0_pf:o:1;io_r_resp_0_bits_g_perm_0_af:o:1;io_r_resp_0_bits_g_perm_0_d:o:1;io_r_resp_0_bits_g_perm_0_a:o:1;io_r_resp_0_bits_g_perm_0_x:o:1;io_r_resp_0_bits_g_perm_0_w:o:1;io_r_resp_0_bits_g_perm_0_r:o:1;io_r_resp_1_bits_hit:o:1;io_r_resp_1_bits_ppn_0:o:36;io_r_resp_1_bits_pbmt_0:o:2;io_r_resp_1_bits_g_pbmt_0:o:2;io_r_resp_1_bits_perm_0_pf:o:1;io_r_resp_1_bits_perm_0_af:o:1;io_r_resp_1_bits_perm_0_v:o:1;io_r_resp_1_bits_perm_0_d:o:1;io_r_resp_1_bits_perm_0_a:o:1;io_r_resp_1_bits_perm_0_u:o:1;io_r_resp_1_bits_perm_0_x:o:1;io_r_resp_1_bits_perm_0_w:o:1;io_r_resp_1_bits_perm_0_r:o:1;io_r_resp_1_bits_g_perm_0_pf:o:1;io_r_resp_1_bits_g_perm_0_af:o:1;io_r_resp_1_bits_g_perm_0_d:o:1;io_r_resp_1_bits_g_perm_0_a:o:1;io_r_resp_1_bits_g_perm_0_x:o:1;io_r_resp_1_bits_g_perm_0_w:o:1;io_r_resp_1_bits_g_perm_0_r:o:1;io_w_valid:i:1;io_w_bits_data_s2xlate:i:2;io_w_bits_data_s1_entry_tag:i:35;io_w_bits_data_s1_entry_asid:i:16;io_w_bits_data_s1_entry_vmid:i:14;io_w_bits_data_s1_entry_n:i:1;io_w_bits_data_s1_entry_pbmt:i:2;io_w_bits_data_s1_entry_perm_d:i:1;io_w_bits_data_s1_entry_perm_a:i:1;io_w_bits_data_s1_entry_perm_g:i:1;io_w_bits_data_s1_entry_perm_u:i:1;io_w_bits_data_s1_entry_perm_x:i:1;io_w_bits_data_s1_entry_perm_w:i:1;io_w_bits_data_s1_entry_perm_r:i:1;io_w_bits_data_s1_entry_level:i:2;io_w_bits_data_s1_entry_v:i:1;io_w_bits_data_s1_entry_ppn:i:41;io_w_bits_data_s1_ppn_low_0:i:3;io_w_bits_data_s1_ppn_low_1:i:3;io_w_bits_data_s1_ppn_low_2:i:3;io_w_bits_data_s1_ppn_low_3:i:3;io_w_bits_data_s1_ppn_low_4:i:3;io_w_bits_data_s1_ppn_low_5:i:3;io_w_bits_data_s1_ppn_low_6:i:3;io_w_bits_data_s1_ppn_low_7:i:3;io_w_bits_data_s1_valididx_0:i:1;io_w_bits_data_s1_valididx_1:i:1;io_w_bits_data_s1_valididx_2:i:1;io_w_bits_data_s1_valididx_3:i:1;io_w_bits_data_s1_valididx_4:i:1;io_w_bits_data_s1_valididx_5:i:1;io_w_bits_data_s1_valididx_6:i:1;io_w_bits_data_s1_valididx_7:i:1;io_w_bits_data_s1_pteidx_0:i:1;io_w_bits_data_s1_pteidx_1:i:1;io_w_bits_data_s1_pteidx_2:i:1;io_w_bits_data_s1_pteidx_3:i:1;io_w_bits_data_s1_pteidx_4:i:1;io_w_bits_data_s1_pteidx_5:i:1;io_w_bits_data_s1_pteidx_6:i:1;io_w_bits_data_s1_pteidx_7:i:1;io_w_bits_data_s1_pf:i:1;io_w_bits_data_s1_af:i:1;io_w_bits_data_s2_entry_tag:i:38;io_w_bits_data_s2_entry_vmid:i:14;io_w_bits_data_s2_entry_n:i:1;io_w_bits_data_s2_entry_pbmt:i:2;io_w_bits_data_s2_entry_ppn:i:38;io_w_bits_data_s2_entry_perm_d:i:1;io_w_bits_data_s2_entry_perm_a:i:1;io_w_bits_data_s2_entry_perm_g:i:1;io_w_bits_data_s2_entry_perm_u:i:1;io_w_bits_data_s2_entry_perm_x:i:1;io_w_bits_data_s2_entry_perm_w:i:1;io_w_bits_data_s2_entry_perm_r:i:1;io_w_bits_data_s2_entry_level:i:2;io_w_bits_data_s2_gpf:i:1;io_w_bits_data_s2_gaf:i:1",
    "VSSplitImp|vsplitimp_v|isVStore=1|clock:i:1;reset:i:1;io_redirect_valid:i:1;io_redirect_bits_robIdx_flag:i:1;io_redirect_bits_robIdx_value:i:8;io_redirect_bits_level:i:1;io_in_ready:o:1;io_in_valid:i:1;io_in_bits_uop_ftqPtr_flag:i:1;io_in_bits_uop_ftqPtr_value:i:6;io_in_bits_uop_ftqOffset:i:4;io_in_bits_uop_fuOpType:i:9;io_in_bits_uop_vecWen:i:1;io_in_bits_uop_v0Wen:i:1;io_in_bits_uop_vlWen:i:1;io_in_bits_uop_vpu_vma:i:1;io_in_bits_uop_vpu_vta:i:1;io_in_bits_uop_vpu_vsew:i:2;io_in_bits_uop_vpu_vlmul:i:3;io_in_bits_uop_vpu_vm:i:1;io_in_bits_uop_vpu_vstart:i:8;io_in_bits_uop_vpu_vuopIdx:i:7;io_in_bits_uop_vpu_vmask:i:128;io_in_bits_uop_vpu_nf:i:3;io_in_bits_uop_vpu_veew:i:2;io_in_bits_uop_pdest:i:8;io_in_bits_uop_robIdx_flag:i:1;io_in_bits_uop_robIdx_value:i:8;io_in_bits_uop_lqIdx_flag:i:1;io_in_bits_uop_lqIdx_value:i:7;io_in_bits_uop_sqIdx_flag:i:1;io_in_bits_uop_sqIdx_value:i:6;io_in_bits_src_0:i:128;io_in_bits_src_1:i:128;io_in_bits_src_2:i:128;io_in_bits_src_3:i:128;io_in_bits_src_4:i:128;io_in_bits_flowNum:i:5;io_in_bits_isVecPartReplay:i:1;io_in_bits_vecReplayMask:i:16;io_in_bits_vecReplayMbIdx:i:4;io_toMergeBuffer_req_ready:i:1;io_toMergeBuffer_req_valid:o:1;io_toMergeBuffer_req_bits_mask:o:16;io_toMergeBuffer_req_bits_vaddr:o:50;io_toMergeBuffer_req_bits_flowNum:o:5;io_toMergeBuffer_req_bits_uop_fuOpType:o:9;io_toMergeBuffer_req_bits_uop_vecWen:o:1;io_toMergeBuffer_req_bits_uop_v0Wen:o:1;io_toMergeBuffer_req_bits_uop_vlWen:o:1;io_toMergeBuffer_req_bits_uop_vpu_vma:o:1;io_toMergeBuffer_req_bits_uop_vpu_vta:o:1;io_toMergeBuffer_req_bits_uop_vpu_vsew:o:2;io_toMergeBuffer_req_bits_uop_vpu_vlmul:o:3;io_toMergeBuffer_req_bits_uop_vpu_vm:o:1;io_toMergeBuffer_req_bits_uop_vpu_vuopIdx:o:7;io_toMergeBuffer_req_bits_uop_vpu_vmask:o:128;io_toMergeBuffer_req_bits_uop_vpu_vl:o:8;io_toMergeBuffer_req_bits_uop_vpu_nf:o:3;io_toMergeBuffer_req_bits_uop_vpu_veew:o:2;io_toMergeBuffer_req_bits_uop_uopIdx:o:7;io_toMergeBuffer_req_bits_uop_pdest:o:8;io_toMergeBuffer_req_bits_uop_robIdx_flag:o:1;io_toMergeBuffer_req_bits_uop_robIdx_value:o:8;io_toMergeBuffer_req_bits_uop_lqIdx_flag:o:1;io_toMergeBuffer_req_bits_uop_lqIdx_value:o:7;io_toMergeBuffer_req_bits_uop_sqIdx_flag:o:1;io_toMergeBuffer_req_bits_uop_sqIdx_value:o:6;io_toMergeBuffer_req_bits_vlmax:o:8;io_toMergeBuffer_resp_valid:i:1;io_toMergeBuffer_resp_bits_mBIndex:i:4;io_out_ready:i:1;io_out_valid:o:1;io_out_bits_vaddr:o:64;io_out_bits_basevaddr:o:50;io_out_bits_mask:o:16;io_out_bits_reg_offset:o:4;io_out_bits_alignedType:o:3;io_out_bits_vecActive:o:1;io_out_bits_vecIsFirstActiveElement:o:1;io_out_bits_uop_exceptionVec_6:o:1;io_out_bits_uop_exceptionVec_19:o:1;io_out_bits_uop_trigger:o:4;io_out_bits_uop_preDecodeInfo_isRVC:o:1;io_out_bits_uop_ftqPtr_flag:o:1;io_out_bits_uop_ftqPtr_value:o:6;io_out_bits_uop_ftqOffset:o:4;io_out_bits_uop_fuOpType:o:9;io_out_bits_uop_rfWen:o:1;io_out_bits_uop_fpWen:o:1;io_out_bits_uop_vpu_vstart:o:8;io_out_bits_uop_vpu_veew:o:2;io_out_bits_uop_uopIdx:o:7;io_out_bits_uop_pdest:o:8;io_out_bits_uop_robIdx_flag:o:1;io_out_bits_uop_robIdx_value:o:8;io_out_bits_uop_storeSetHit:o:1;io_out_bits_uop_waitForRobIdx_flag:o:1;io_out_bits_uop_waitForRobIdx_value:o:8;io_out_bits_uop_loadWaitBit:o:1;io_out_bits_uop_loadWaitStrict:o:1;io_out_bits_uop_lqIdx_flag:o:1;io_out_bits_uop_lqIdx_value:o:7;io_out_bits_uop_sqIdx_flag:o:1;io_out_bits_uop_sqIdx_value:o:6;io_out_bits_mBIndex:o:4;io_out_bits_elemIdx:o:8;io_out_bits_elemIdxInsideVd:o:8;io_out_bits_splitIndex:o:5;io_vstd_valid:o:1;io_vstd_bits_uop_fuOpType:o:9;io_vstd_bits_uop_sqIdx_flag:o:1;io_vstd_bits_uop_sqIdx_value:o:6;io_vstd_bits_data:o:128;io_vstdMisalign_storeMisalignBufferEmpty:i:1;io_vstdMisalign_scalaIssueValid:i:1;io_vstdMisalign_scalaIssueRobIdx_flag:i:1;io_vstdMisalign_scalaIssueRobIdx_value:i:8;io_vstdMisalign_sqDeqIsVec:i:1;io_threshold_valid:i:1;io_threshold_bits_robIdx_flag:i:1;io_threshold_bits_robIdx_value:i:8;io_threshold_bits_uopIdx:i:7",
    "VSSplitBufferImp|vsplitbuf|isVStore=1|clock:i:1;reset:i:1;io_redirect_valid:i:1;io_redirect_bits_robIdx_flag:i:1;io_redirect_bits_robIdx_value:i:8;io_redirect_bits_level:i:1;io_in_ready:o:1;io_in_valid:i:1;io_in_bits_flowMask:i:16;io_in_bits_data:i:128;io_in_bits_baseAddr:i:64;io_in_bits_uopAddr:i:64;io_in_bits_stride:i:128;io_in_bits_flowNum:i:5;io_in_bits_eew:i:2;io_in_bits_sew:i:3;io_in_bits_emul:i:3;io_in_bits_lmul:i:3;io_in_bits_instType:i:3;io_in_bits_indexedSplitOffset:i:5;io_in_bits_uop_exceptionVec_19:i:1;io_in_bits_uop_trigger:i:4;io_in_bits_uop_preDecodeInfo_isRVC:i:1;io_in_bits_uop_ftqPtr_flag:i:1;io_in_bits_uop_ftqPtr_value:i:6;io_in_bits_uop_ftqOffset:i:4;io_in_bits_uop_fuOpType:i:9;io_in_bits_uop_rfWen:i:1;io_in_bits_uop_fpWen:i:1;io_in_bits_uop_vpu_vstart:i:8;io_in_bits_uop_vpu_vuopIdx:i:7;io_in_bits_uop_vpu_veew:i:2;io_in_bits_uop_uopIdx:i:7;io_in_bits_uop_pdest:i:8;io_in_bits_uop_robIdx_flag:i:1;io_in_bits_uop_robIdx_value:i:8;io_in_bits_uop_storeSetHit:i:1;io_in_bits_uop_waitForRobIdx_flag:i:1;io_in_bits_uop_waitForRobIdx_value:i:8;io_in_bits_uop_loadWaitBit:i:1;io_in_bits_uop_loadWaitStrict:i:1;io_in_bits_uop_lqIdx_flag:i:1;io_in_bits_uop_lqIdx_value:i:7;io_in_bits_uop_sqIdx_flag:i:1;io_in_bits_uop_sqIdx_value:i:6;io_in_bits_preIsSplit:i:1;io_in_bits_mBIndex:i:4;io_in_bits_alignedType:i:3;io_in_bits_indexVlMaxInVd:i:8;io_in_bits_usLowBitsAddr:i:4;io_in_bits_usAligned128:i:1;io_in_bits_usMask:i:32;io_in_bits_isVecPartReplay:i:1;io_in_bits_vecReplayFlowMask:i:16;io_out_ready:i:1;io_out_valid:o:1;io_out_bits_vaddr:o:64;io_out_bits_basevaddr:o:50;io_out_bits_mask:o:16;io_out_bits_reg_offset:o:4;io_out_bits_alignedType:o:3;io_out_bits_vecActive:o:1;io_out_bits_vecIsFirstActiveElement:o:1;io_out_bits_uop_exceptionVec_6:o:1;io_out_bits_uop_exceptionVec_19:o:1;io_out_bits_uop_trigger:o:4;io_out_bits_uop_preDecodeInfo_isRVC:o:1;io_out_bits_uop_ftqPtr_flag:o:1;io_out_bits_uop_ftqPtr_value:o:6;io_out_bits_uop_ftqOffset:o:4;io_out_bits_uop_fuOpType:o:9;io_out_bits_uop_rfWen:o:1;io_out_bits_uop_fpWen:o:1;io_out_bits_uop_vpu_vstart:o:8;io_out_bits_uop_vpu_veew:o:2;io_out_bits_uop_uopIdx:o:7;io_out_bits_uop_pdest:o:8;io_out_bits_uop_robIdx_flag:o:1;io_out_bits_uop_robIdx_value:o:8;io_out_bits_uop_storeSetHit:o:1;io_out_bits_uop_waitForRobIdx_flag:o:1;io_out_bits_uop_waitForRobIdx_value:o:8;io_out_bits_uop_loadWaitBit:o:1;io_out_bits_uop_loadWaitStrict:o:1;io_out_bits_uop_lqIdx_flag:o:1;io_out_bits_uop_lqIdx_value:o:7;io_out_bits_uop_sqIdx_flag:o:1;io_out_bits_uop_sqIdx_value:o:6;io_out_bits_mBIndex:o:4;io_out_bits_elemIdx:o:8;io_out_bits_elemIdxInsideVd:o:8;io_out_bits_splitIndex:o:5;io_vstd_valid:o:1;io_vstd_bits_uop_fuOpType:o:9;io_vstd_bits_uop_sqIdx_flag:o:1;io_vstd_bits_uop_sqIdx_value:o:6;io_vstd_bits_data:o:128;io_vstdMisalign_storeMisalignBufferEmpty:i:1;io_vstdMisalign_scalaIssueValid:i:1;io_vstdMisalign_scalaIssueRobIdx_flag:i:1;io_vstdMisalign_scalaIssueRobIdx_value:i:8;io_vstdMisalign_sqDeqIsVec:i:1",
    "VSSplitPipelineImp|vsplitpipe|isVStore=1|clock:i:1;reset:i:1;io_redirect_valid:i:1;io_redirect_bits_robIdx_flag:i:1;io_redirect_bits_robIdx_value:i:8;io_redirect_bits_level:i:1;io_in_ready:o:1;io_in_valid:i:1;io_in_bits_uop_ftqPtr_flag:i:1;io_in_bits_uop_ftqPtr_value:i:6;io_in_bits_uop_ftqOffset:i:4;io_in_bits_uop_fuOpType:i:9;io_in_bits_uop_vecWen:i:1;io_in_bits_uop_v0Wen:i:1;io_in_bits_uop_vlWen:i:1;io_in_bits_uop_vpu_vma:i:1;io_in_bits_uop_vpu_vta:i:1;io_in_bits_uop_vpu_vsew:i:2;io_in_bits_uop_vpu_vlmul:i:3;io_in_bits_uop_vpu_vm:i:1;io_in_bits_uop_vpu_vstart:i:8;io_in_bits_uop_vpu_vuopIdx:i:7;io_in_bits_uop_vpu_vmask:i:128;io_in_bits_uop_vpu_nf:i:3;io_in_bits_uop_vpu_veew:i:2;io_in_bits_uop_pdest:i:8;io_in_bits_uop_robIdx_flag:i:1;io_in_bits_uop_robIdx_value:i:8;io_in_bits_uop_lqIdx_flag:i:1;io_in_bits_uop_lqIdx_value:i:7;io_in_bits_uop_sqIdx_flag:i:1;io_in_bits_uop_sqIdx_value:i:6;io_in_bits_src_0:i:128;io_in_bits_src_1:i:128;io_in_bits_src_2:i:128;io_in_bits_src_3:i:128;io_in_bits_src_4:i:128;io_in_bits_flowNum:i:5;io_in_bits_isVecPartReplay:i:1;io_in_bits_vecReplayMask:i:16;io_in_bits_vecReplayMbIdx:i:4;io_toMergeBuffer_req_ready:i:1;io_toMergeBuffer_req_valid:o:1;io_toMergeBuffer_req_bits_mask:o:16;io_toMergeBuffer_req_bits_vaddr:o:50;io_toMergeBuffer_req_bits_flowNum:o:5;io_toMergeBuffer_req_bits_uop_fuOpType:o:9;io_toMergeBuffer_req_bits_uop_vecWen:o:1;io_toMergeBuffer_req_bits_uop_v0Wen:o:1;io_toMergeBuffer_req_bits_uop_vlWen:o:1;io_toMergeBuffer_req_bits_uop_vpu_vma:o:1;io_toMergeBuffer_req_bits_uop_vpu_vta:o:1;io_toMergeBuffer_req_bits_uop_vpu_vsew:o:2;io_toMergeBuffer_req_bits_uop_vpu_vlmul:o:3;io_toMergeBuffer_req_bits_uop_vpu_vm:o:1;io_toMergeBuffer_req_bits_uop_vpu_vuopIdx:o:7;io_toMergeBuffer_req_bits_uop_vpu_vmask:o:128;io_toMergeBuffer_req_bits_uop_vpu_vl:o:8;io_toMergeBuffer_req_bits_uop_vpu_nf:o:3;io_toMergeBuffer_req_bits_uop_vpu_veew:o:2;io_toMergeBuffer_req_bits_uop_uopIdx:o:7;io_toMergeBuffer_req_bits_uop_pdest:o:8;io_toMergeBuffer_req_bits_uop_robIdx_flag:o:1;io_toMergeBuffer_req_bits_uop_robIdx_value:o:8;io_toMergeBuffer_req_bits_uop_lqIdx_flag:o:1;io_toMergeBuffer_req_bits_uop_lqIdx_value:o:7;io_toMergeBuffer_req_bits_uop_sqIdx_flag:o:1;io_toMergeBuffer_req_bits_uop_sqIdx_value:o:6;io_toMergeBuffer_req_bits_vlmax:o:8;io_toMergeBuffer_resp_valid:i:1;io_toMergeBuffer_resp_bits_mBIndex:i:4;io_out_ready:i:1;io_out_valid:o:1;io_out_bits_flowMask:o:16;io_out_bits_data:o:128;io_out_bits_baseAddr:o:64;io_out_bits_uopAddr:o:64;io_out_bits_stride:o:128;io_out_bits_flowNum:o:5;io_out_bits_eew:o:2;io_out_bits_sew:o:3;io_out_bits_emul:o:3;io_out_bits_lmul:o:3;io_out_bits_instType:o:3;io_out_bits_indexedSplitOffset:o:5;io_out_bits_uop_ftqPtr_flag:o:1;io_out_bits_uop_ftqPtr_value:o:6;io_out_bits_uop_ftqOffset:o:4;io_out_bits_uop_fuOpType:o:9;io_out_bits_uop_vpu_vstart:o:8;io_out_bits_uop_vpu_vuopIdx:o:7;io_out_bits_uop_vpu_veew:o:2;io_out_bits_uop_uopIdx:o:7;io_out_bits_uop_pdest:o:8;io_out_bits_uop_robIdx_flag:o:1;io_out_bits_uop_robIdx_value:o:8;io_out_bits_uop_lqIdx_flag:o:1;io_out_bits_uop_lqIdx_value:o:7;io_out_bits_uop_sqIdx_flag:o:1;io_out_bits_uop_sqIdx_value:o:6;io_out_bits_preIsSplit:o:1;io_out_bits_mBIndex:o:4;io_out_bits_alignedType:o:3;io_out_bits_indexVlMaxInVd:o:8;io_out_bits_usLowBitsAddr:o:4;io_out_bits_usAligned128:o:1;io_out_bits_usMask:o:32;io_out_bits_isVecPartReplay:o:1;io_out_bits_vecReplayFlowMask:o:16;io_threshold_valid:i:1;io_threshold_bits_robIdx_flag:i:1;io_threshold_bits_robIdx_value:i:8;io_threshold_bits_uopIdx:i:7",
    "VLSplitImp|vsplitimp_l|isVStore=0|clock:i:1;reset:i:1;io_redirect_valid:i:1;io_redirect_bits_robIdx_flag:i:1;io_redirect_bits_robIdx_value:i:8;io_redirect_bits_level:i:1;io_in_ready:o:1;io_in_valid:i:1;io_in_bits_uop_ftqPtr_flag:i:1;io_in_bits_uop_ftqPtr_value:i:6;io_in_bits_uop_ftqOffset:i:4;io_in_bits_uop_fuOpType:i:9;io_in_bits_uop_vecWen:i:1;io_in_bits_uop_v0Wen:i:1;io_in_bits_uop_vlWen:i:1;io_in_bits_uop_vpu_vma:i:1;io_in_bits_uop_vpu_vta:i:1;io_in_bits_uop_vpu_vsew:i:2;io_in_bits_uop_vpu_vlmul:i:3;io_in_bits_uop_vpu_vm:i:1;io_in_bits_uop_vpu_vstart:i:8;io_in_bits_uop_vpu_vuopIdx:i:7;io_in_bits_uop_vpu_nf:i:3;io_in_bits_uop_vpu_veew:i:2;io_in_bits_uop_pdest:i:8;io_in_bits_uop_robIdx_flag:i:1;io_in_bits_uop_robIdx_value:i:8;io_in_bits_uop_lqIdx_flag:i:1;io_in_bits_uop_lqIdx_value:i:7;io_in_bits_uop_sqIdx_flag:i:1;io_in_bits_uop_sqIdx_value:i:6;io_in_bits_src_0:i:128;io_in_bits_src_1:i:128;io_in_bits_src_2:i:128;io_in_bits_src_3:i:128;io_in_bits_src_4:i:128;io_in_bits_flowNum:i:5;io_in_bits_isVecPartReplay:i:1;io_in_bits_vecReplayMask:i:16;io_in_bits_vecReplayMbIdx:i:4;io_toMergeBuffer_req_ready:i:1;io_toMergeBuffer_req_valid:o:1;io_toMergeBuffer_req_bits_mask:o:16;io_toMergeBuffer_req_bits_vaddr:o:50;io_toMergeBuffer_req_bits_flowNum:o:5;io_toMergeBuffer_req_bits_uop_fuOpType:o:9;io_toMergeBuffer_req_bits_uop_vecWen:o:1;io_toMergeBuffer_req_bits_uop_v0Wen:o:1;io_toMergeBuffer_req_bits_uop_vlWen:o:1;io_toMergeBuffer_req_bits_uop_vpu_vma:o:1;io_toMergeBuffer_req_bits_uop_vpu_vta:o:1;io_toMergeBuffer_req_bits_uop_vpu_vsew:o:2;io_toMergeBuffer_req_bits_uop_vpu_vlmul:o:3;io_toMergeBuffer_req_bits_uop_vpu_vm:o:1;io_toMergeBuffer_req_bits_uop_vpu_vuopIdx:o:7;io_toMergeBuffer_req_bits_uop_vpu_vl:o:8;io_toMergeBuffer_req_bits_uop_vpu_nf:o:3;io_toMergeBuffer_req_bits_uop_vpu_veew:o:2;io_toMergeBuffer_req_bits_uop_uopIdx:o:7;io_toMergeBuffer_req_bits_uop_pdest:o:8;io_toMergeBuffer_req_bits_uop_robIdx_flag:o:1;io_toMergeBuffer_req_bits_uop_robIdx_value:o:8;io_toMergeBuffer_req_bits_data:o:128;io_toMergeBuffer_req_bits_vdIdx:o:3;io_toMergeBuffer_req_bits_fof:o:1;io_toMergeBuffer_req_bits_vlmax:o:8;io_toMergeBuffer_resp_valid:i:1;io_toMergeBuffer_resp_bits_mBIndex:i:4;io_out_ready:i:1;io_out_valid:o:1;io_out_bits_vaddr:o:64;io_out_bits_basevaddr:o:50;io_out_bits_mask:o:16;io_out_bits_reg_offset:o:4;io_out_bits_alignedType:o:3;io_out_bits_vecActive:o:1;io_out_bits_vecIsFirstActiveElement:o:1;io_out_bits_uop_exceptionVec_4:o:1;io_out_bits_uop_exceptionVec_5:o:1;io_out_bits_uop_exceptionVec_13:o:1;io_out_bits_uop_exceptionVec_19:o:1;io_out_bits_uop_exceptionVec_21:o:1;io_out_bits_uop_trigger:o:4;io_out_bits_uop_preDecodeInfo_isRVC:o:1;io_out_bits_uop_ftqPtr_flag:o:1;io_out_bits_uop_ftqPtr_value:o:6;io_out_bits_uop_ftqOffset:o:4;io_out_bits_uop_fuOpType:o:9;io_out_bits_uop_rfWen:o:1;io_out_bits_uop_fpWen:o:1;io_out_bits_uop_vpu_vstart:o:8;io_out_bits_uop_vpu_veew:o:2;io_out_bits_uop_uopIdx:o:7;io_out_bits_uop_pdest:o:8;io_out_bits_uop_robIdx_flag:o:1;io_out_bits_uop_robIdx_value:o:8;io_out_bits_uop_storeSetHit:o:1;io_out_bits_uop_waitForRobIdx_flag:o:1;io_out_bits_uop_waitForRobIdx_value:o:8;io_out_bits_uop_loadWaitBit:o:1;io_out_bits_uop_loadWaitStrict:o:1;io_out_bits_uop_lqIdx_flag:o:1;io_out_bits_uop_lqIdx_value:o:7;io_out_bits_uop_sqIdx_flag:o:1;io_out_bits_uop_sqIdx_value:o:6;io_out_bits_mBIndex:o:4;io_out_bits_elemIdx:o:8;io_out_bits_elemIdxInsideVd:o:8;io_out_bits_splitIndex:o:5;io_threshold_valid:i:1;io_threshold_bits_robIdx_flag:i:1;io_threshold_bits_robIdx_value:i:8;io_threshold_bits_uopIdx:i:7;io_fromPipeline_0_valid:i:1;io_fromPipeline_0_bits_mBIndex:i:4;io_fromPipeline_1_valid:i:1;io_fromPipeline_1_bits_mBIndex:i:4;io_fromPipeline_2_valid:i:1;io_fromPipeline_2_bits_mBIndex:i:4",
    "VLSplitBufferImp|vsplitbuf|isVStore=0|clock:i:1;reset:i:1;io_redirect_valid:i:1;io_redirect_bits_robIdx_flag:i:1;io_redirect_bits_robIdx_value:i:8;io_redirect_bits_level:i:1;io_in_ready:o:1;io_in_valid:i:1;io_in_bits_flowMask:i:16;io_in_bits_baseAddr:i:64;io_in_bits_uopAddr:i:64;io_in_bits_stride:i:128;io_in_bits_flowNum:i:5;io_in_bits_eew:i:2;io_in_bits_sew:i:3;io_in_bits_emul:i:3;io_in_bits_lmul:i:3;io_in_bits_instType:i:3;io_in_bits_indexedSplitOffset:i:5;io_in_bits_uop_exceptionVec_5:i:1;io_in_bits_uop_exceptionVec_13:i:1;io_in_bits_uop_exceptionVec_19:i:1;io_in_bits_uop_exceptionVec_21:i:1;io_in_bits_uop_trigger:i:4;io_in_bits_uop_preDecodeInfo_isRVC:i:1;io_in_bits_uop_ftqPtr_flag:i:1;io_in_bits_uop_ftqPtr_value:i:6;io_in_bits_uop_ftqOffset:i:4;io_in_bits_uop_fuOpType:i:9;io_in_bits_uop_rfWen:i:1;io_in_bits_uop_fpWen:i:1;io_in_bits_uop_vpu_vstart:i:8;io_in_bits_uop_vpu_vuopIdx:i:7;io_in_bits_uop_vpu_veew:i:2;io_in_bits_uop_uopIdx:i:7;io_in_bits_uop_pdest:i:8;io_in_bits_uop_robIdx_flag:i:1;io_in_bits_uop_robIdx_value:i:8;io_in_bits_uop_storeSetHit:i:1;io_in_bits_uop_waitForRobIdx_flag:i:1;io_in_bits_uop_waitForRobIdx_value:i:8;io_in_bits_uop_loadWaitBit:i:1;io_in_bits_uop_loadWaitStrict:i:1;io_in_bits_uop_lqIdx_flag:i:1;io_in_bits_uop_lqIdx_value:i:7;io_in_bits_uop_sqIdx_flag:i:1;io_in_bits_uop_sqIdx_value:i:6;io_in_bits_preIsSplit:i:1;io_in_bits_mBIndex:i:4;io_in_bits_alignedType:i:3;io_in_bits_indexVlMaxInVd:i:8;io_in_bits_usLowBitsAddr:i:4;io_in_bits_usAligned128:i:1;io_in_bits_usMask:i:32;io_in_bits_isVecPartReplay:i:1;io_in_bits_vecReplayFlowMask:i:16;io_out_ready:i:1;io_out_valid:o:1;io_out_bits_vaddr:o:64;io_out_bits_basevaddr:o:50;io_out_bits_mask:o:16;io_out_bits_reg_offset:o:4;io_out_bits_alignedType:o:3;io_out_bits_vecActive:o:1;io_out_bits_vecIsFirstActiveElement:o:1;io_out_bits_uop_exceptionVec_4:o:1;io_out_bits_uop_exceptionVec_5:o:1;io_out_bits_uop_exceptionVec_13:o:1;io_out_bits_uop_exceptionVec_19:o:1;io_out_bits_uop_exceptionVec_21:o:1;io_out_bits_uop_trigger:o:4;io_out_bits_uop_preDecodeInfo_isRVC:o:1;io_out_bits_uop_ftqPtr_flag:o:1;io_out_bits_uop_ftqPtr_value:o:6;io_out_bits_uop_ftqOffset:o:4;io_out_bits_uop_fuOpType:o:9;io_out_bits_uop_rfWen:o:1;io_out_bits_uop_fpWen:o:1;io_out_bits_uop_vpu_vstart:o:8;io_out_bits_uop_vpu_veew:o:2;io_out_bits_uop_uopIdx:o:7;io_out_bits_uop_pdest:o:8;io_out_bits_uop_robIdx_flag:o:1;io_out_bits_uop_robIdx_value:o:8;io_out_bits_uop_storeSetHit:o:1;io_out_bits_uop_waitForRobIdx_flag:o:1;io_out_bits_uop_waitForRobIdx_value:o:8;io_out_bits_uop_loadWaitBit:o:1;io_out_bits_uop_loadWaitStrict:o:1;io_out_bits_uop_lqIdx_flag:o:1;io_out_bits_uop_lqIdx_value:o:7;io_out_bits_uop_sqIdx_flag:o:1;io_out_bits_uop_sqIdx_value:o:6;io_out_bits_mBIndex:o:4;io_out_bits_elemIdx:o:8;io_out_bits_elemIdxInsideVd:o:8;io_out_bits_splitIndex:o:5;io_fromPipeline_0_valid:i:1;io_fromPipeline_0_bits_mBIndex:i:4;io_fromPipeline_1_valid:i:1;io_fromPipeline_1_bits_mBIndex:i:4;io_fromPipeline_2_valid:i:1;io_fromPipeline_2_bits_mBIndex:i:4",
    "VLSplitPipelineImp|vsplitpipe|isVStore=0|clock:i:1;reset:i:1;io_redirect_valid:i:1;io_redirect_bits_robIdx_flag:i:1;io_redirect_bits_robIdx_value:i:8;io_redirect_bits_level:i:1;io_in_ready:o:1;io_in_valid:i:1;io_in_bits_uop_ftqPtr_flag:i:1;io_in_bits_uop_ftqPtr_value:i:6;io_in_bits_uop_ftqOffset:i:4;io_in_bits_uop_fuOpType:i:9;io_in_bits_uop_vecWen:i:1;io_in_bits_uop_v0Wen:i:1;io_in_bits_uop_vlWen:i:1;io_in_bits_uop_vpu_vma:i:1;io_in_bits_uop_vpu_vta:i:1;io_in_bits_uop_vpu_vsew:i:2;io_in_bits_uop_vpu_vlmul:i:3;io_in_bits_uop_vpu_vm:i:1;io_in_bits_uop_vpu_vstart:i:8;io_in_bits_uop_vpu_vuopIdx:i:7;io_in_bits_uop_vpu_nf:i:3;io_in_bits_uop_vpu_veew:i:2;io_in_bits_uop_pdest:i:8;io_in_bits_uop_robIdx_flag:i:1;io_in_bits_uop_robIdx_value:i:8;io_in_bits_uop_lqIdx_flag:i:1;io_in_bits_uop_lqIdx_value:i:7;io_in_bits_uop_sqIdx_flag:i:1;io_in_bits_uop_sqIdx_value:i:6;io_in_bits_src_0:i:128;io_in_bits_src_1:i:128;io_in_bits_src_2:i:128;io_in_bits_src_3:i:128;io_in_bits_src_4:i:128;io_in_bits_flowNum:i:5;io_in_bits_isVecPartReplay:i:1;io_in_bits_vecReplayMask:i:16;io_in_bits_vecReplayMbIdx:i:4;io_toMergeBuffer_req_ready:i:1;io_toMergeBuffer_req_valid:o:1;io_toMergeBuffer_req_bits_mask:o:16;io_toMergeBuffer_req_bits_vaddr:o:50;io_toMergeBuffer_req_bits_flowNum:o:5;io_toMergeBuffer_req_bits_uop_fuOpType:o:9;io_toMergeBuffer_req_bits_uop_vecWen:o:1;io_toMergeBuffer_req_bits_uop_v0Wen:o:1;io_toMergeBuffer_req_bits_uop_vlWen:o:1;io_toMergeBuffer_req_bits_uop_vpu_vma:o:1;io_toMergeBuffer_req_bits_uop_vpu_vta:o:1;io_toMergeBuffer_req_bits_uop_vpu_vsew:o:2;io_toMergeBuffer_req_bits_uop_vpu_vlmul:o:3;io_toMergeBuffer_req_bits_uop_vpu_vm:o:1;io_toMergeBuffer_req_bits_uop_vpu_vuopIdx:o:7;io_toMergeBuffer_req_bits_uop_vpu_vl:o:8;io_toMergeBuffer_req_bits_uop_vpu_nf:o:3;io_toMergeBuffer_req_bits_uop_vpu_veew:o:2;io_toMergeBuffer_req_bits_uop_uopIdx:o:7;io_toMergeBuffer_req_bits_uop_pdest:o:8;io_toMergeBuffer_req_bits_uop_robIdx_flag:o:1;io_toMergeBuffer_req_bits_uop_robIdx_value:o:8;io_toMergeBuffer_req_bits_data:o:128;io_toMergeBuffer_req_bits_vdIdx:o:3;io_toMergeBuffer_req_bits_fof:o:1;io_toMergeBuffer_req_bits_vlmax:o:8;io_toMergeBuffer_resp_valid:i:1;io_toMergeBuffer_resp_bits_mBIndex:i:4;io_out_ready:i:1;io_out_valid:o:1;io_out_bits_flowMask:o:16;io_out_bits_data:o:128;io_out_bits_baseAddr:o:64;io_out_bits_uopAddr:o:64;io_out_bits_stride:o:128;io_out_bits_flowNum:o:5;io_out_bits_eew:o:2;io_out_bits_sew:o:3;io_out_bits_emul:o:3;io_out_bits_lmul:o:3;io_out_bits_instType:o:3;io_out_bits_indexedSplitOffset:o:5;io_out_bits_uop_ftqPtr_flag:o:1;io_out_bits_uop_ftqPtr_value:o:6;io_out_bits_uop_ftqOffset:o:4;io_out_bits_uop_fuOpType:o:9;io_out_bits_uop_vpu_vstart:o:8;io_out_bits_uop_vpu_vuopIdx:o:7;io_out_bits_uop_vpu_veew:o:2;io_out_bits_uop_uopIdx:o:7;io_out_bits_uop_pdest:o:8;io_out_bits_uop_robIdx_flag:o:1;io_out_bits_uop_robIdx_value:o:8;io_out_bits_uop_lqIdx_flag:o:1;io_out_bits_uop_lqIdx_value:o:7;io_out_bits_uop_sqIdx_flag:o:1;io_out_bits_uop_sqIdx_value:o:6;io_out_bits_preIsSplit:o:1;io_out_bits_mBIndex:o:4;io_out_bits_alignedType:o:3;io_out_bits_indexVlMaxInVd:o:8;io_out_bits_usLowBitsAddr:o:4;io_out_bits_usAligned128:o:1;io_out_bits_usMask:o:32;io_out_bits_isVecPartReplay:o:1;io_out_bits_vecReplayFlowMask:o:16;io_threshold_valid:i:1;io_threshold_bits_robIdx_flag:i:1;io_threshold_bits_robIdx_value:i:8;io_threshold_bits_uopIdx:i:7",
    "Repeater|repeater||clock:i:1;reset:i:1;io_repeat:i:1;io_enq_ready:o:1;io_enq_valid:i:1;io_enq_bits_opcode:i:4;io_enq_bits_param:i:2;io_enq_bits_size:i:3;io_enq_bits_source:i:5;io_enq_bits_sink:i:1;io_enq_bits_denied:i:1;io_enq_bits_data:i:256;io_enq_bits_corrupt:i:1;io_deq_ready:i:1;io_deq_valid:o:1;io_deq_bits_opcode:o:4;io_deq_bits_param:o:2;io_deq_bits_size:o:3;io_deq_bits_source:o:5;io_deq_bits_sink:o:1;io_deq_bits_denied:o:1;io_deq_bits_data:o:256;io_deq_bits_corrupt:o:1",
    "Repeater_1|repeater||clock:i:1;reset:i:1;io_repeat:i:1;io_full:o:1;io_enq_ready:o:1;io_enq_valid:i:1;io_enq_bits_opcode:i:4;io_enq_bits_size:i:2;io_enq_bits_source:i:5;io_enq_bits_address:i:30;io_enq_bits_mask:i:4;io_deq_ready:i:1;io_deq_valid:o:1;io_deq_bits_opcode:o:4;io_deq_bits_size:o:2;io_deq_bits_source:o:5;io_deq_bits_address:o:30;io_deq_bits_mask:o:4",
    "Repeater_2|repeater||clock:i:1;reset:i:1;io_repeat:i:1;io_enq_ready:o:1;io_enq_valid:i:1;io_enq_bits_opcode:i:4;io_enq_bits_size:i:2;io_enq_bits_source:i:5;io_enq_bits_address:i:30;io_enq_bits_mask:i:8;io_enq_bits_data:i:64;io_deq_ready:i:1;io_deq_valid:o:1;io_deq_bits_opcode:o:4;io_deq_bits_size:o:2;io_deq_bits_source:o:5;io_deq_bits_address:o:30;io_deq_bits_mask:o:8;io_deq_bits_data:o:64",
    "Repeater_3|repeater||clock:i:1;reset:i:1;io_repeat:i:1;io_enq_ready:o:1;io_enq_valid:i:1;io_enq_bits_opcode:i:4;io_enq_bits_param:i:2;io_enq_bits_size:i:3;io_enq_bits_source:i:1;io_enq_bits_sink:i:6;io_enq_bits_denied:i:1;io_enq_bits_data:i:256;io_enq_bits_corrupt:i:1;io_deq_ready:i:1;io_deq_valid:o:1;io_deq_bits_opcode:o:4;io_deq_bits_param:o:2;io_deq_bits_size:o:3;io_deq_bits_source:o:1;io_deq_bits_sink:o:6;io_deq_bits_denied:o:1;io_deq_bits_data:o:256;io_deq_bits_corrupt:o:1",
    "PTWRepeaterNB|ptwrepeater||clock:i:1;reset:i:1;io_sfence_valid:i:1;io_csr_satp_changed:i:1;io_csr_vsatp_changed:i:1;io_csr_hgatp_changed:i:1;io_csr_priv_virt_changed:i:1;io_tlb_req_0_ready:o:1;io_tlb_req_0_valid:i:1;io_tlb_req_0_bits_vpn:i:38;io_tlb_req_0_bits_s2xlate:i:2;io_tlb_resp_ready:i:1;io_tlb_resp_valid:o:1;io_tlb_resp_bits_s2xlate:o:2;io_tlb_resp_bits_s1_entry_tag:o:35;io_tlb_resp_bits_s1_entry_asid:o:16;io_tlb_resp_bits_s1_entry_vmid:o:14;io_tlb_resp_bits_s1_entry_n:o:1;io_tlb_resp_bits_s1_entry_pbmt:o:2;io_tlb_resp_bits_s1_entry_perm_d:o:1;io_tlb_resp_bits_s1_entry_perm_a:o:1;io_tlb_resp_bits_s1_entry_perm_g:o:1;io_tlb_resp_bits_s1_entry_perm_u:o:1;io_tlb_resp_bits_s1_entry_perm_x:o:1;io_tlb_resp_bits_s1_entry_perm_w:o:1;io_tlb_resp_bits_s1_entry_perm_r:o:1;io_tlb_resp_bits_s1_entry_level:o:2;io_tlb_resp_bits_s1_entry_v:o:1;io_tlb_resp_bits_s1_entry_ppn:o:41;io_tlb_resp_bits_s1_addr_low:o:3;io_tlb_resp_bits_s1_ppn_low_0:o:3;io_tlb_resp_bits_s1_ppn_low_1:o:3;io_tlb_resp_bits_s1_ppn_low_2:o:3;io_tlb_resp_bits_s1_ppn_low_3:o:3;io_tlb_resp_bits_s1_ppn_low_4:o:3;io_tlb_resp_bits_s1_ppn_low_5:o:3;io_tlb_resp_bits_s1_ppn_low_6:o:3;io_tlb_resp_bits_s1_ppn_low_7:o:3;io_tlb_resp_bits_s1_valididx_0:o:1;io_tlb_resp_bits_s1_valididx_1:o:1;io_tlb_resp_bits_s1_valididx_2:o:1;io_tlb_resp_bits_s1_valididx_3:o:1;io_tlb_resp_bits_s1_valididx_4:o:1;io_tlb_resp_bits_s1_valididx_5:o:1;io_tlb_resp_bits_s1_valididx_6:o:1;io_tlb_resp_bits_s1_valididx_7:o:1;io_tlb_resp_bits_s1_pteidx_0:o:1;io_tlb_resp_bits_s1_pteidx_1:o:1;io_tlb_resp_bits_s1_pteidx_2:o:1;io_tlb_resp_bits_s1_pteidx_3:o:1;io_tlb_resp_bits_s1_pteidx_4:o:1;io_tlb_resp_bits_s1_pteidx_5:o:1;io_tlb_resp_bits_s1_pteidx_6:o:1;io_tlb_resp_bits_s1_pteidx_7:o:1;io_tlb_resp_bits_s1_pf:o:1;io_tlb_resp_bits_s1_af:o:1;io_tlb_resp_bits_s2_entry_tag:o:38;io_tlb_resp_bits_s2_entry_vmid:o:14;io_tlb_resp_bits_s2_entry_n:o:1;io_tlb_resp_bits_s2_entry_pbmt:o:2;io_tlb_resp_bits_s2_entry_ppn:o:38;io_tlb_resp_bits_s2_entry_perm_d:o:1;io_tlb_resp_bits_s2_entry_perm_a:o:1;io_tlb_resp_bits_s2_entry_perm_g:o:1;io_tlb_resp_bits_s2_entry_perm_u:o:1;io_tlb_resp_bits_s2_entry_perm_x:o:1;io_tlb_resp_bits_s2_entry_perm_w:o:1;io_tlb_resp_bits_s2_entry_perm_r:o:1;io_tlb_resp_bits_s2_entry_level:o:2;io_tlb_resp_bits_s2_gpf:o:1;io_tlb_resp_bits_s2_gaf:o:1;io_ptw_req_0_ready:i:1;io_ptw_req_0_valid:o:1;io_ptw_req_0_bits_vpn:o:38;io_ptw_req_0_bits_s2xlate:o:2;io_ptw_resp_ready:o:1;io_ptw_resp_valid:i:1;io_ptw_resp_bits_s2xlate:i:2;io_ptw_resp_bits_s1_entry_tag:i:35;io_ptw_resp_bits_s1_entry_asid:i:16;io_ptw_resp_bits_s1_entry_vmid:i:14;io_ptw_resp_bits_s1_entry_n:i:1;io_ptw_resp_bits_s1_entry_pbmt:i:2;io_ptw_resp_bits_s1_entry_perm_d:i:1;io_ptw_resp_bits_s1_entry_perm_a:i:1;io_ptw_resp_bits_s1_entry_perm_g:i:1;io_ptw_resp_bits_s1_entry_perm_u:i:1;io_ptw_resp_bits_s1_entry_perm_x:i:1;io_ptw_resp_bits_s1_entry_perm_w:i:1;io_ptw_resp_bits_s1_entry_perm_r:i:1;io_ptw_resp_bits_s1_entry_level:i:2;io_ptw_resp_bits_s1_entry_v:i:1;io_ptw_resp_bits_s1_entry_ppn:i:41;io_ptw_resp_bits_s1_addr_low:i:3;io_ptw_resp_bits_s1_ppn_low_0:i:3;io_ptw_resp_bits_s1_ppn_low_1:i:3;io_ptw_resp_bits_s1_ppn_low_2:i:3;io_ptw_resp_bits_s1_ppn_low_3:i:3;io_ptw_resp_bits_s1_ppn_low_4:i:3;io_ptw_resp_bits_s1_ppn_low_5:i:3;io_ptw_resp_bits_s1_ppn_low_6:i:3;io_ptw_resp_bits_s1_ppn_low_7:i:3;io_ptw_resp_bits_s1_valididx_0:i:1;io_ptw_resp_bits_s1_valididx_1:i:1;io_ptw_resp_bits_s1_valididx_2:i:1;io_ptw_resp_bits_s1_valididx_3:i:1;io_ptw_resp_bits_s1_valididx_4:i:1;io_ptw_resp_bits_s1_valididx_5:i:1;io_ptw_resp_bits_s1_valididx_6:i:1;io_ptw_resp_bits_s1_valididx_7:i:1;io_ptw_resp_bits_s1_pteidx_0:i:1;io_ptw_resp_bits_s1_pteidx_1:i:1;io_ptw_resp_bits_s1_pteidx_2:i:1;io_ptw_resp_bits_s1_pteidx_3:i:1;io_ptw_resp_bits_s1_pteidx_4:i:1;io_ptw_resp_bits_s1_pteidx_5:i:1;io_ptw_resp_bits_s1_pteidx_6:i:1;io_ptw_resp_bits_s1_pteidx_7:i:1;io_ptw_resp_bits_s1_pf:i:1;io_ptw_resp_bits_s1_af:i:1;io_ptw_resp_bits_s2_entry_tag:i:38;io_ptw_resp_bits_s2_entry_vmid:i:14;io_ptw_resp_bits_s2_entry_n:i:1;io_ptw_resp_bits_s2_entry_pbmt:i:2;io_ptw_resp_bits_s2_entry_ppn:i:38;io_ptw_resp_bits_s2_entry_perm_d:i:1;io_ptw_resp_bits_s2_entry_perm_a:i:1;io_ptw_resp_bits_s2_entry_perm_g:i:1;io_ptw_resp_bits_s2_entry_perm_u:i:1;io_ptw_resp_bits_s2_entry_perm_x:i:1;io_ptw_resp_bits_s2_entry_perm_w:i:1;io_ptw_resp_bits_s2_entry_perm_r:i:1;io_ptw_resp_bits_s2_entry_level:i:2;io_ptw_resp_bits_s2_gpf:i:1;io_ptw_resp_bits_s2_gaf:i:1",
)

# Fixed Kunminghu V2 MMU geometry constants of the pinned artifact.
# 钉死产物的固定 Kunminghu V2 MMU 几何常量。
TLB_SECTOR_WIDTH = 3
TLB_VPNN_LEN = 9
TLB_LEVEL = 3
TLB_CONTIGUOUS = 8


# =============================================================================
# Implementation
# =============================================================================
# Parse one catalog row into its module spec. / 把一条 catalog 行解析为模块 spec。
def parse_catalog_row(row: str) -> FamilySpec:
    """Decode one ``name|family|params|ports`` catalog row. / 解码一条 catalog 行。"""

    name, family, params_text, ports_text = row.split("|")
    params: dict[str, int] = {}
    if params_text:
        for item in params_text.split(","):
            key, value = item.split("=")
            params[key] = int(value)
    # The generated XSTop instances use the 4-bit TileLink slave-id directly
    # as the UncacheEntry module suffix (…_10 … _15 => ids 0xA … 0xF).
    # Older catalog rows carried the parent allocator's decimal 16…21 ids;
    # those can never match the pinned ``mid == 7'hF`` style compares.
    if family == "entry" and name.startswith("UncacheEntry_"):
        suffix = name.rsplit("_", 1)[1]
        if suffix.isdigit() and int(suffix) >= 10:
            params["slaveId"] = int(suffix)
    ports: list[tuple[str, str, int]] = []
    for item in ports_text.split(";"):
        port_name, direction, bits = item.split(":")
        ports.append((port_name, "input" if direction == "i" else "output", int(bits)))
    return FamilySpec(module=name, family=family, params=params, ports=tuple(ports))


@dataclass(frozen=True)
class FamilySpec:
    """One covered locked module with its exact pinned port surface. / 一个被覆盖锁定模块及其精确钉死端口面。"""

    module: str
    family: str
    params: dict[str, int]
    ports: tuple[tuple[str, str, int], ...]

    # Report the pinned bit width of one port by name. / 按名返回某个端口的钉死位宽。
    def width(self, name: str) -> int:
        """Return the pinned bit width of port ``name``. / 返回端口 ``name`` 的钉死位宽。"""

        for port_name, _, bits in self.ports:
            if port_name == name:
                return bits
        raise KeyError(name)

    # Report whether one pinned port exists on this instance. / 判断本实例是否存在某个钉死端口。
    def has(self, name: str) -> bool:
        """Return True when port ``name`` is present. / 端口 ``name`` 存在时返回 True。"""

        return any(port_name == name for port_name, _, _ in self.ports)

    # List the retained pinned ports below one prefix in pinned order. / 按钉死顺序列出某前缀下保留的钉死端口。
    def fields(self, prefix: str) -> tuple[str, ...]:
        """Return the port names starting with ``prefix``. / 返回以 ``prefix`` 开头的端口名。"""

        return tuple(name for name, _, _ in self.ports if name.startswith(prefix))


# Materialise every covered locked module at import time. / 在导入时物化所有被覆盖的锁定模块。
def catalog_specs() -> tuple[FamilySpec, ...]:
    """Return the spec of every locked module covered by this family file. / 返回本 family 文件覆盖的每个锁定模块 spec。"""

    return tuple(parse_catalog_row(row) for row in CATALOG_ROWS)


# Select one covered locked module by its pinned name. / 按钉死名选择一个被覆盖的锁定模块。
def family_spec(name: str) -> FamilySpec:
    """Return the spec of the locked module named ``name``. / 返回名为 ``name`` 的锁定模块 spec。"""

    for spec in catalog_specs():
        if spec.module == name:
            return spec
    raise KeyError(name)


class PortBound(Elaboratable):
    """Common base binding the exact pinned port surface of one module. / 绑定一个模块精确钉死端口面的公共基类。"""

    # Resolve runtime-created port attributes for static type checking. / 为静态类型检查解析运行时创建的端口属性。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    # Construct one named signal per pinned port in declaration order. / 按声明顺序为每个钉死端口构造一个命名信号。
    def __init__(self, spec: FamilySpec, top_name: str) -> None:
        self.spec = spec
        self.top_name = top_name
        self.ports: dict[str, Signal] = {}
        for port_name, _, bits in spec.ports:
            self.ports[port_name] = Signal(bits, name=port_name)
        self.port_surface: list[Signal] = [self.ports[name] for name, _, _ in spec.ports]

    # Return one bound port signal by pinned name. / 按钉死名返回一个绑定的端口信号。
    def sig(self, name: str) -> Signal:
        """Return the signal bound to port ``name``. / 返回绑定到端口 ``name`` 的信号。"""

        return self.ports[name]

    # Attach the pinned asynchronous-reset clock domain. / 附加钉死的异步复位时钟域。
    def attach_domain(self, m: Any) -> ClockDomain:
        """Create the ``ck`` domain driven by the pinned clock and reset. / 创建由钉死时钟与复位驱动的 ``ck`` 域。"""

        domain = ClockDomain("ck", async_reset=True)
        domain.clk = self.sig("clock")
        domain.rst = self.sig("reset")
        m.domains.ck = domain
        return domain


# Report the pinned ``CircularQueuePtr`` increment as flag/value pair. / 返回钉死 ``CircularQueuePtr`` 加法的 flag/value 对。
def ptr_add(flag: Any, value: Any, addend: Any, size: int) -> tuple[Any, Any]:
    """Return ``(flag, value)`` of ``ptr + addend``. / 返回 ``ptr + addend`` 的 ``(flag, value)``。"""

    if size & (size - 1) == 0:
        # Amaranth widens an addition by one carry bit.  Slice that carry off
        # before splitting the circular pointer; otherwise ``value`` absorbs
        # the old flag bit and all distance/slot calculations drift after the
        # first allocation.
        ptr_width = len(value) + len(flag)
        total = (Cat(value, flag) + addend)[:ptr_width]
        return total[ptr_width - 1], total[:ptr_width - 1]
    new_value = value + addend
    wrapped = new_value >= size
    return (flag != wrapped), Mux(wrapped, new_value - size, new_value)


# Report the pinned ``CircularQueuePtr`` ordering predicate. / 返回钉死 ``CircularQueuePtr`` 次序谓词。
def ptr_less(flag_a: Any, value_a: Any, flag_b: Any, value_b: Any) -> Any:
    """Return ``a < b`` with the pinned flag/value comparison. / 以钉死 flag/value 比较返回 ``a < b``。"""

    return (flag_a != flag_b) != (value_a < value_b)


# Report the pinned ``RobPtr.needFlush`` predicate. / 返回钉死的 ``RobPtr.needFlush`` 谓词。
def rob_need_flush(rob_flag: Any, rob_value: Any, redirect_valid: Any,
                   redirect_flag: Any, redirect_value: Any, redirect_level: Any) -> Any:
    """Return the pinned flush-self-or-after expression. / 返回钉死的 flush-self-or-after 表达式。"""

    flush_itself = redirect_level[0] & ((rob_flag == redirect_flag) & (rob_value == redirect_value))
    is_after = (rob_flag != redirect_flag) != (rob_value > redirect_value)
    return redirect_valid & (flush_itself | is_after)


# Report the pinned population count of one signal vector. / 返回一个信号向量的钉死置位计数。
def popcount_of(bits: list[Any]) -> Any:
    """Return the chained popcount sum. / 返回链式 popcount 和。"""

    if not bits:
        return Const(0, 1)
    total: Any = bits[0]
    for bit in bits[1:]:
        total = total + bit
    return total


class LsqUncacheFreeList(PortBound):
    """Faithful Amaranth model of the pinned lsq ``FreeList`` allocator. / 钉死 lsq ``FreeList`` 分配器的忠实 Amaranth 模型。"""

    # Construct the pinned port surface and allocator geometry. / 构造钉死端口面与分配器几何。
    def __init__(self, spec: FamilySpec, top_name: str = "UHSCFreeList") -> None:
        super().__init__(spec, top_name)
        self.size = spec.params["size"]
        self.alloc_width = spec.params["allocWidth"]
        self.free_width = spec.params["freeWidth"]
        self.pre_alloc = bool(spec.params["preAlloc"])
        self.req_const = bool(spec.params["reqConst"])
        self.ptr_bits = max(1, (self.size - 1).bit_length())

    # Decode one scattered one-hot slot vector into its ring index. / 把散射 one-hot 槽向量解码为环下标。
    def oh_to_uint(self, one_hot: Any) -> Any:
        """Return the priority index of the set slot bit. / 返回置位槽位的优先级下标。"""

        result: Any = Const(0, self.ptr_bits)
        for i in range(self.size):
            result = result | (Mux(one_hot[i], i, 0))
        return result

    # Elaborate the pinned free/allocate ordering. / 展开钉死的释放/分配顺序。
    def elaborate(self, platform: Any) -> Module:
        """Elaborate the free-list allocator equations. / 展开空闲表分配器方程。"""

        del platform
        spec = self.spec
        m: Any = Module()
        self.attach_domain(m)
        size = self.size

        self.free_list = Array(
            Signal(self.ptr_bits, name="freeList_%d" % i, reset=i) for i in range(size))
        head_flag = Signal(name="headPtr_flag", reset=0)
        head_value = Signal(self.ptr_bits, name="headPtr_value", reset=0)
        tail_flag = Signal(name="tailPtr_flag", reset=1)
        tail_value = Signal(self.ptr_bits, name="tailPtr_value", reset=0)
        free_mask = Signal(size, name="freeMask", reset=0)

        # ``FreeList.scala`` selects from the pending mask after removing the
        # selection that is currently being retired.  The old model selected
        # directly from ``free_mask``; that re-selected the same slot for one
        # extra cycle and quickly desynchronised the ring under random frees.
        # ``FreeList.scala`` 在移除当前正在退休的选择后才从 pending mask
        # 选择；旧模型直接从 ``free_mask`` 选择，导致同一 slot 多保留一拍。
        free_req: list[Signal] = [
            Signal(name="freeReq_next_nextVec_%d_r" % rem, reset=0)
            for rem in range(self.free_width)
        ]
        free_slot_oh: list[Signal] = [
            Signal(size, name="freeSlotOH_next_nextVec_%d_r" % rem, reset=0)
            for rem in range(self.free_width)
        ]
        # Keep the decoded value alongside the gated one-hot register.  Some
        # Verilator scheduling paths can otherwise re-evaluate the dynamic
        # Array write after ``freeSlotOH`` updates at the same edge, making the
        # first remainder write observe the *new* one-hot instead of the old
        # registered selection.  The pinned Chisel RTL effectively carries
        # this decoded value across the edge.
        free_value: list[Signal] = [
            Signal(self.ptr_bits, name="freeValue_next_nextVec_%d_r" % rem, reset=0)
            for rem in range(self.free_width)
        ]
        free_sel_mask: Any = Const(0, size)
        for rem in range(self.free_width):
            free_sel_mask = free_sel_mask | Mux(free_req[rem], free_slot_oh[rem], Const(0, size))
        pending_mask: Any = free_mask & ~free_sel_mask
        free_req_in: list[Any] = []
        free_slot_oh_in: list[Any] = []
        for rem in range(self.free_width):
            selected = Const(0, 1)
            one_hot = Const(0, size)
            found = Const(0, 1)
            for i in range(size // self.free_width):
                bit = pending_mask[rem + i * self.free_width]
                selected = selected | bit
                hit = bit & ~found
                # A one-bit Amaranth signal keeps its width when shifted;
                # shifting ``hit`` directly therefore discarded every bit
                # above position zero.  Materialise a full-width constant
                # one-hot under the hit predicate, matching Chisel's
                # PriorityEncoderOH expansion.
                one_hot = one_hot | Mux(
                    hit,
                    Const(1 << (i * self.free_width + rem), size),
                    Const(0, size),
                )
                found = found | hit
            free_req_in.append(selected)
            free_slot_oh_in.append(one_hot)
        for rem in range(self.free_width):
            m.d.ck += [free_req[rem].eq(free_req_in[rem]),
                       free_slot_oh[rem].eq(free_slot_oh_in[rem]),
                       free_value[rem].eq(self.oh_to_uint(free_slot_oh_in[rem]))]
        m.d.ck += free_mask.eq((self.sig("io_free") | free_mask) & ~free_sel_mask)

        do_free = free_req[0]
        for rem in range(1, self.free_width):
            do_free = do_free | free_req[rem]
        for rem in range(self.free_width):
            # ``PopCount(freeReq.take(rem))`` is zero for remainder 0;
            # seeding every row with freeReq(0) shifted the first write one
            # slot and made it collide with remainder 1.
            offset = Const(0, 1) if rem == 0 else free_req[0]
            for k in range(1, rem):
                offset = offset + free_req[k]
            enq_flag, enq_value = ptr_add(tail_flag, tail_value, offset, size)
            with m.If(free_req[rem]):
                m.d.ck += self.free_list[enq_value].eq(free_value[rem])
            del enq_flag
        free_count = free_req[0]
        for rem in range(1, self.free_width):
            free_count = free_count + free_req[rem]
        tail_flag_next, tail_value_next = ptr_add(tail_flag, tail_value, free_count, size)
        with m.If(do_free):
            m.d.ck += [tail_flag.eq(tail_flag_next), tail_value.eq(tail_value_next)]

        # allocate: pruned constant or ported allocateReq offsets, optional pre-alloc registers.
        # 分配：剪枝常量或端口的 allocateReq 偏移，可选 pre-alloc 寄存。
        do_allocate_bits = [self.sig("io_doAllocate_%d" % w) for w in range(self.alloc_width)]
        do_allocate = popcount_of(do_allocate_bits) != 0
        num_allocate = popcount_of(do_allocate_bits)
        for w in range(self.alloc_width):
            offset = Const(w, 4) if self.req_const else Const(w, 4)
            if self.pre_alloc:
                deq_flag, deq_value = ptr_add(head_flag, head_value, num_allocate + offset, size)
            else:
                deq_flag, deq_value = ptr_add(head_flag, head_value, offset, size)
            can_allocate = ptr_less(deq_flag, deq_value, tail_flag, tail_value)
            slot: Any = self.free_list[deq_value]
            if self.pre_alloc:
                slot_reg = Signal(self.ptr_bits, name="io_allocateSlot_%d_r" % w, reset=0)
                can_reg = Signal(name="io_canAllocate_%d_r" % w, reset=0)
                m.d.ck += [slot_reg.eq(self.free_list[deq_value]), can_reg.eq(can_allocate)]
                slot = slot_reg
                can_allocate = can_reg
            if spec.has("io_allocateSlot_%d" % w):
                m.d.comb += self.sig("io_allocateSlot_%d" % w).eq(slot)
            if spec.has("io_canAllocate_%d" % w):
                m.d.comb += self.sig("io_canAllocate_%d" % w).eq(can_allocate)
        head_flag_next, head_value_next = ptr_add(head_flag, head_value, num_allocate, size)
        with m.If(do_allocate):
            m.d.ck += [head_flag.eq(head_flag_next), head_value.eq(head_value_next)]
        # Keep the circular-distance arithmetic at exactly ``value_width+1``
        # bits.  Letting Amaranth infer widths here duplicates carry/flag bits
        # and can produce counts above the queue size (the reference uses the
        # same-width ``distanceBetween`` subtraction).
        value_width = len(tail_value_next)
        tail_value_ext = Cat(tail_value_next, Const(0, 1))
        head_value_ext = Cat(head_value_next, Const(0, 1))
        # In the equal-flag arm Chisel subtracts the value-width operands
        # first, then zero-extends the wrapped result.  Extending before the
        # subtraction would retain a borrow (e.g. 0-12 => 20 instead of 4).
        distance_same = Cat((tail_value_next - head_value_next)[:value_width], Const(0, 1))
        distance_wrap = (tail_value_ext - Const(size, value_width + 1)
                         - head_value_ext)[:value_width + 1]
        distance: Any = Mux(tail_flag_next == head_flag_next,
                             distance_same, distance_wrap)
        free_slot_cnt = Signal((size).bit_length(), name="freeSlotCnt", reset=size)
        m.d.ck += free_slot_cnt.eq(distance)
        if spec.has("io_validCount"):
            m.d.comb += self.sig("io_validCount").eq(size - free_slot_cnt)
        if spec.has("io_empty"):
            m.d.comb += self.sig("io_empty").eq(free_slot_cnt == 0)
        return m


class UncacheEntryModel(PortBound):
    """Faithful Amaranth model of one pinned ``UncacheEntry`` register. / 一个钉死 ``UncacheEntry`` 表项寄存器的忠实 Amaranth 模型。"""

    # Construct the pinned entry ports and the fixed slave id. / 构造钉死的表项端口与固定 slave id。
    def __init__(self, spec: FamilySpec, top_name: str = "UHSCUncacheEntry") -> None:
        super().__init__(spec, top_name)
        self.slave_id = spec.params["slaveId"]

    # Collect the retained request-bundle register fields of this entry. / 收集本表项保留的请求 bundle 寄存字段。
    def req_fields(self) -> tuple[str, ...]:
        """Return the ``io_req_bits_`` field suffixes in pinned order. / 按钉死顺序返回 ``io_req_bits_`` 字段后缀。"""

        return tuple(name[len("io_req_bits_"):] for name in self.spec.fields("io_req_bits_"))

    # Return the registered source of one writeback field suffix. / 返回某个写回字段后缀的已寄存来源。
    def writeback_source(self, suffix: str, req_regs: dict[str, Signal], data_reg: Signal,
                         denied: Signal, corrupt: Signal) -> Any:
        """Return the pinned writeback value of one ``bits_`` suffix. / 返回某个 ``bits_`` 后缀的钉死写回值。"""

        if suffix == "data":
            return data_reg
        if suffix == "nc":
            return Const(1, 1)
        # The pinned hierarchy flattens the exception bundle to numeric
        # fields (Vec index 5 = load access fault, 19 = hardware error), while
        # older generators used descriptive names.  Accept both spellings.
        if suffix in ("uop_exceptionVec_hardwareError", "uop_exceptionVec_19"):
            return corrupt & ~denied
        if suffix in ("uop_exceptionVec_loadAccessFault", "uop_exceptionVec_5"):
            return denied
        return req_regs.get(suffix)

    # Elaborate the pinned entry state machine. / 展开钉死的表项状态机。
    def elaborate(self, platform: Any) -> Module:
        """Elaborate the entry registers and uncache FSM. / 展开表项寄存器与 uncache 状态机。"""

        del platform
        spec = self.spec
        m: Any = Module()
        self.attach_domain(m)
        p = self.ports

        req_valid = Signal(name="req_valid", reset=0)
        slave_accept = Signal(name="slaveAccept", reset=0)
        slave_id = Signal(spec.width("io_slaveId_bits"), name="slaveId", reset=0)
        req_regs = {field: Signal(spec.width("io_req_bits_" + field), name="req_" + field, reset=0)
                    for field in self.req_fields()}
        state = Signal(2, name="uncacheState", reset=0)
        data_reg = Signal(spec.width("io_uncache_resp_bits_data"), name="uncacheData", reset=0)
        denied = Signal(name="denied", reset=0)
        corrupt = Signal(name="corrupt", reset=0)
        need_flush_reg = Signal(name="needFlushReg", reset=0)
        pending_ld = Signal(name="pendingld", reset=0)
        pending_flag = Signal(name="pendingPtr_flag", reset=0)
        pending_value = Signal(spec.width("io_rob_pendingPtr_value"), name="pendingPtr_value", reset=0)

        req_flag = req_regs.get("uop_robIdx_flag")
        req_value = req_regs.get("uop_robIdx_value")
        req_nc = req_regs.get("nc")
        req_mmio = req_regs.get("mmio")
        need_flush = Const(0, 1)
        if req_flag is not None and req_value is not None:
            need_flush = rob_need_flush(req_flag, req_value, p["io_redirect_valid"],
                                        p["io_redirect_bits_robIdx_flag"],
                                        p["io_redirect_bits_robIdx_value"],
                                        p["io_redirect_bits_level"])
            # The Chisel predicate is explicitly qualified by req_valid;
            # redirect traffic while the entry is idle must not flush it.
            need_flush = req_valid & need_flush
        can_send_req = req_valid & ~need_flush
        if req_nc is not None:
            pending_match = Const(1, 1)
            if req_flag is not None and req_value is not None:
                pending_match = (req_flag == pending_flag) & (req_value == pending_value)
            can_send_req = req_valid & ~need_flush & Mux(req_nc, Const(1, 1),
                                                         pending_ld & pending_match)
        uncache_req_fire = p["io_uncache_req_ready"] & p["io_uncache_req_valid"]
        resp_fire = p["io_uncache_resp_valid"]
        nc_fire = p["io_ncOut_ready"] & p["io_ncOut_valid"]
        mmio_fire = p["io_mmioOut_ready"] & p["io_mmioOut_valid"]
        writeback = Mux(req_nc if req_nc is not None else Const(0, 1), nc_fire, mmio_fire)

        # Use actual combinational signals for the FSM.  Assigning a Python
        # expression inside an Amaranth ``with m.If`` only overwrites the
        # elaboration-time variable; the old model consequently collapsed the
        # state machine to ``state=0`` and ``flush=1`` in generated Verilog.
        flush_sig = Signal(name="flush", reset=0)
        next_state = Signal(2, name="uncacheState_next", reset=0)
        m.d.comb += [next_state.eq(state), flush_sig.eq(0)]
        with m.Switch(state):
            with m.Case(0):
                with m.If(need_flush):
                    m.d.comb += [next_state.eq(0), flush_sig.eq(1)]
                with m.Elif(can_send_req):
                    m.d.comb += next_state.eq(1)
            with m.Case(1):
                with m.If(need_flush):
                    m.d.comb += [next_state.eq(0), flush_sig.eq(1)]
                with m.Elif(uncache_req_fire):
                    m.d.comb += next_state.eq(2)
            with m.Case(2):
                with m.If(resp_fire):
                    with m.If(need_flush | need_flush_reg):
                        m.d.comb += [next_state.eq(0), flush_sig.eq(1)]
                    with m.Else():
                        m.d.comb += next_state.eq(3)
            with m.Case(3):
                with m.If(need_flush | writeback):
                    m.d.comb += [next_state.eq(0), flush_sig.eq(1)]
        m.d.ck += state.eq(next_state)
        with m.If(flush_sig):
            m.d.ck += need_flush_reg.eq(0)
        with m.Elif(need_flush):
            m.d.ck += need_flush_reg.eq(1)

        slave_ack = req_valid & p["io_uncache_idResp_valid"] & (p["io_uncache_idResp_bits_mid"] == self.slave_id)
        with m.If(flush_sig):
            m.d.ck += [req_valid.eq(0), slave_accept.eq(0)]
        with m.Elif(p["io_req_valid"]):
            m.d.ck += [req_valid.eq(1), slave_accept.eq(0)]
            for field, reg in req_regs.items():
                m.d.ck += reg.eq(p["io_req_bits_" + field])
            m.d.ck += [denied.eq(0), corrupt.eq(0)]
        with m.Elif(slave_ack):
            m.d.ck += [slave_accept.eq(1), slave_id.eq(p["io_uncache_idResp_bits_sid"])]
        with m.Elif(writeback):
            m.d.ck += [req_valid.eq(0), slave_accept.eq(0)]
        m.d.ck += pending_ld.eq(p["io_rob_pendingMMIOld"])
        m.d.ck += [pending_flag.eq(p["io_rob_pendingPtr_flag"]),
                   pending_value.eq(p["io_rob_pendingPtr_value"])]
        with m.If(resp_fire):
            m.d.ck += [data_reg.eq(p["io_uncache_resp_bits_data"]),
                       denied.eq(p["io_uncache_resp_bits_denied"]),
                       corrupt.eq(p["io_uncache_resp_bits_corrupt"])]

        mmio_select = (state != Const(0, 2)) & (req_mmio if req_mmio is not None else Const(0, 1))
        m.d.comb += [p["io_flush"].eq(flush_sig),
                     p["io_mmioSelect"].eq(mmio_select),
                     p["io_slaveId_valid"].eq(slave_accept),
                     p["io_slaveId_bits"].eq(slave_id),
                     p["io_uncache_req_valid"].eq((state == Const(1, 2)) & ~need_flush)]
        if "io_uncache_resp_ready" in p:
            m.d.comb += p["io_uncache_resp_ready"].eq(Const(1, 1))
        req_paddr = req_regs.get("paddr")
        req_mask = req_regs.get("mask")
        if req_paddr is not None:
            m.d.comb += p["io_uncache_req_bits_addr"].eq(req_paddr)
            if req_mask is not None:
                m.d.comb += p["io_uncache_req_bits_mask"].eq(
                Mux(req_paddr[3], req_mask[8:16], req_mask[0:8]) if len(req_mask) >= 16 else req_mask[0:8])
        if req_flag is not None and req_value is not None and "io_uncache_req_bits_robIdx_flag" in p:
            m.d.comb += [p["io_uncache_req_bits_robIdx_flag"].eq(req_flag),
                         p["io_uncache_req_bits_robIdx_value"].eq(req_value)]
        if req_nc is not None and "io_uncache_req_bits_nc" in p:
            m.d.comb += p["io_uncache_req_bits_nc"].eq(req_nc)
        if req_regs.get("memBackTypeMM") is not None and "io_uncache_req_bits_memBackTypeMM" in p:
            m.d.comb += p["io_uncache_req_bits_memBackTypeMM"].eq(req_regs["memBackTypeMM"])
        if req_regs.get("vaddr") is not None and "io_uncache_req_bits_vaddr" in p:
            m.d.comb += p["io_uncache_req_bits_vaddr"].eq(req_regs["vaddr"])
        if "io_uncache_req_bits_id" in p:
            m.d.comb += p["io_uncache_req_bits_id"].eq(self.slave_id)
        nc_value: Any = req_nc if req_nc is not None else Const(0, 1)
        if req_nc is not None:
            m.d.comb += p["io_ncOut_valid"].eq((state == Const(3, 2)) & ~need_flush & nc_value)
        if req_mmio is not None:
            m.d.comb += p["io_mmioOut_valid"].eq((state == Const(3, 2)) & ~need_flush & ~nc_value)
        for field in spec.fields("io_ncOut_bits_"):
            source = self.writeback_source(field[len("io_ncOut_bits_"):], req_regs, data_reg, denied, corrupt)
            if source is not None:
                m.d.comb += p[field].eq(source)
        for field in spec.fields("io_mmioOut_bits_"):
            source = self.writeback_source(field[len("io_mmioOut_bits_"):], req_regs, data_reg, denied, corrupt)
            if source is not None:
                m.d.comb += p[field].eq(source)
        if spec.has("io_mmioRawData_lqData"):
            m.d.comb += p["io_mmioRawData_lqData"].eq(data_reg)
        for field in spec.fields("io_mmioRawData_uop_"):
            # Raw-data fields retain the ``uop_`` bundle prefix in req_regs.
            suffix = field[len("io_mmioRawData_uop_"):]
            source = req_regs.get("uop_" + suffix)
            if source is not None:
                m.d.comb += p[field].eq(source)
        if spec.has("io_mmioRawData_addrOffset") and req_paddr is not None:
            m.d.comb += p["io_mmioRawData_addrOffset"].eq(req_paddr)
        m.d.comb += p["io_exception_valid"].eq(writeback)
        for field in spec.fields("io_exception_bits_"):
            source = req_regs.get(field[len("io_exception_bits_"):])
            if source is not None:
                m.d.comb += p[field].eq(source)
        if "io_exception_bits_uop_exceptionVec_hardwareError" in p:
            m.d.comb += p["io_exception_bits_uop_exceptionVec_hardwareError"].eq(corrupt & ~denied)
        if "io_exception_bits_uop_exceptionVec_loadAccessFault" in p:
            m.d.comb += p["io_exception_bits_uop_exceptionVec_loadAccessFault"].eq(denied)
        if "io_exception_bits_uop_exceptionVec_19" in p:
            m.d.comb += p["io_exception_bits_uop_exceptionVec_19"].eq(corrupt & ~denied)
        if "io_exception_bits_uop_exceptionVec_5" in p:
            m.d.comb += p["io_exception_bits_uop_exceptionVec_5"].eq(denied)
        return m


class RepeaterModel(PortBound):
    """Faithful Amaranth model of the rocket-chip ``Repeater`` leaf. / rocket-chip ``Repeater`` 叶子的忠实 Amaranth 模型。"""

    # List the retained enqueue payload fields. / 列出保留的入队载荷字段。
    def payload_fields(self) -> tuple[str, ...]:
        """Return the ``io_enq_bits_`` field names in pinned order. / 按钉死顺序返回 ``io_enq_bits_`` 字段名。"""

        return self.spec.fields("io_enq_bits_")

    # Elaborate the pinned full/saved repeater registers. / 展开钉死的 full/saved repeater 寄存器。
    def elaborate(self, platform: Any) -> Module:
        """Elaborate the pass-through and repeat registers. / 展开直通与重复寄存器。"""

        del platform
        m: Any = Module()
        self.attach_domain(m)
        p = self.ports
        full = Signal(name="full", reset=0)
        saved = {name: Signal(self.spec.width(name), name="saved_" + name) for name in self.payload_fields()}
        enq_valid = p["io_enq_valid"] if self.spec.has("io_enq_valid") else Const(0, 1)
        deq_ready = p["io_deq_ready"] if self.spec.has("io_deq_ready") else Const(0, 1)
        enq_fire = p["io_enq_ready"] & enq_valid
        deq_fire = p["io_deq_ready"] & p["io_deq_valid"]
        m.d.comb += [p["io_deq_valid"].eq(enq_valid | full),
                     p["io_enq_ready"].eq(deq_ready & ~full)]
        if self.spec.has("io_full"):
            m.d.comb += p["io_full"].eq(full)
        for name, reg in saved.items():
            out_name = "io_deq_bits_" + name[len("io_enq_bits_"):]
            if out_name in p:
                m.d.comb += p[out_name].eq(Mux(full, reg, p[name]))
        with m.If(enq_fire & p["io_repeat"]):
            m.d.ck += full.eq(1)
            for name, reg in saved.items():
                m.d.ck += reg.eq(p[name])
        with m.If(deq_fire & ~p["io_repeat"]):
            m.d.ck += full.eq(0)
        return m


class PtwRepeaterNbModel(PortBound):
    """Faithful Amaranth model of the pinned ``PTWRepeaterNB`` stop-watch repeater. / 钉死 ``PTWRepeaterNB`` 停表转发器的忠实 Amaranth 模型。"""

    # Construct the pinned PTW repeater ports. / 构造钉死的 PTW 转发器端口。
    def __init__(self, spec: FamilySpec, top_name: str = "UHSCPTWRepeaterNB") -> None:
        super().__init__(spec, top_name)
        self.fence_delay = spec.params.get("fenceDelay", 2)

    # Elaborate the pinned sent/recv stop-watch shuttles. / 展开钉死的 sent/recv 停表摆渡。
    def elaborate(self, platform: Any) -> Module:
        """Elaborate the non-blocking PTW request/response paths. / 展开非阻塞 PTW 请求/响应通路。"""

        del platform
        m: Any = Module()
        self.attach_domain(m)
        p = self.ports
        flush_in: Any = Const(0, 1)
        for name in ("io_sfence_valid", "io_satp_changed", "io_vsatp_changed",
                     "io_hgatp_changed", "io_virt_changed"):
            if self.spec.has(name):
                flush_in = flush_in | p[name]
        stage: Any = flush_in
        for index in range(self.fence_delay):
            reg = Signal(name="delayN_%d" % index, reset=0)
            m.d.ck += reg.eq(stage)
            stage = reg
        delayed = stage
        req_fields = tuple(name[len("io_ptw_req_0_bits_"):] for name in self.spec.fields("io_ptw_req_0_bits_"))
        req_reg = {name: Signal(self.spec.width("io_ptw_req_0_bits_" + name), name="req_" + name, reset=0)
                   for name in req_fields}
        sent = Signal(name="sent", reset=0)
        req_in_fire = p["io_tlb_req_0_ready"] & p["io_tlb_req_0_valid"]
        m.d.comb += [p["io_tlb_req_0_ready"].eq(~sent | p["io_ptw_req_0_ready"]),
                     p["io_ptw_req_0_valid"].eq(sent)]
        for name, reg in req_reg.items():
            m.d.comb += p["io_ptw_req_0_bits_" + name].eq(reg)
        with m.If(req_in_fire):
            m.d.ck += sent.eq(1)
            for name, reg in req_reg.items():
                m.d.ck += reg.eq(p["io_tlb_req_0_bits_" + name])
        with m.If(p["io_ptw_req_0_ready"] & p["io_ptw_req_0_valid"]):
            m.d.ck += sent.eq(0)
        with m.If(delayed):
            m.d.ck += sent.eq(0)
        resp_fields = tuple(name[len("io_ptw_resp_bits_"):] for name in self.spec.fields("io_ptw_resp_bits_"))
        resp_reg = {name: Signal(self.spec.width("io_ptw_resp_bits_" + name), name="resp_" + name, reset=0)
                    for name in resp_fields}
        recv = Signal(name="recv", reset=0)
        resp_in_fire = p["io_ptw_resp_ready"] & p["io_ptw_resp_valid"]
        m.d.comb += [p["io_ptw_resp_ready"].eq(~recv | p["io_tlb_resp_ready"]),
                     p["io_tlb_resp_valid"].eq(recv)]
        for name, reg in resp_reg.items():
            m.d.comb += p["io_tlb_resp_bits_" + name].eq(reg)
        with m.If(resp_in_fire):
            m.d.ck += recv.eq(1)
            for name, reg in resp_reg.items():
                m.d.ck += reg.eq(p["io_ptw_resp_bits_" + name])
        with m.If(p["io_tlb_resp_ready"] & p["io_tlb_resp_valid"]):
            m.d.ck += recv.eq(0)
        with m.If(delayed):
            m.d.ck += recv.eq(0)
        return m


class TlbFaModel(PortBound):
    """Faithful Amaranth model of the pinned 48-way ``TLBFA`` storage. / 钉死 48 路 ``TLBFA`` 存储的忠实 Amaranth 模型。"""

    # Pinned Kunminghu V2 fully-associative geometry of the artifact. / 钉死工件的全相联几何。
    TLB_WAYS = 48
    TLB_SECTORS = 8
    TLB_VPNN_LEN = 9

    # Construct the pinned TLB storage ports and bank geometry. / 构造钉死的 TLB 存储端口与组几何。
    def __init__(self, spec: FamilySpec, top_name: str = "UHSCTLBFA") -> None:
        super().__init__(spec, top_name)
        self.num_ports = len(spec.fields("io_r_req_0_bits_vpn"))
        self.num_dups = len({name for name in spec.fields("io_r_resp_0_bits_ppn")})
        self.has_way_idx = spec.has("io_w_bits_wayIdx")
        self.n_ways = self.TLB_WAYS
        self.vpn_bits = spec.width("io_r_req_0_bits_vpn")
        self.has_vmid = spec.has("io_csr_hgatp_vmid")

    # Return the registered entry storage of one way. / 返回一路的已寄存表项存储。
    def entry_bank(self, way: int) -> dict[str, Signal]:
        """Return the pinned per-entry register map of one way. / 返回某一路的钉死逐字段表项寄存器映射。"""

        widths = {"tag": 35, "ppn": 33, "asid": 16, "vmid": 14, "level": 2,
                  "s2xlate": 2, "pbmt": 2, "g_pbmt": 2, "n": 1,
                  "perm_pf": 1, "perm_af": 1, "perm_v": 1, "perm_a": 1, "perm_u": 1,
                  "perm_x": 1, "perm_w": 1, "perm_r": 1, "perm_g": 1,
                  "g_perm_pf": 1, "g_perm_af": 1, "g_perm_a": 1, "g_perm_x": 1}
        fields = {name: Signal(width, name="entry_%d_%s" % (way, name), reset=0)
                  for name, width in widths.items()}
        for sector in range(self.TLB_SECTORS):
            fields["valididx_%d" % sector] = Signal(1, name="entry_%d_valididx_%d" % (way, sector), reset=0)
            fields["pteidx_%d" % sector] = Signal(1, name="entry_%d_pteidx_%d" % (way, sector), reset=0)
            fields["ppn_low_%d" % sector] = Signal(3, name="entry_%d_ppn_low_%d" % (way, sector), reset=0)
        return fields

    # Report the pinned sector-tag match of one way against a vpn. / 返回某一路对 vpn 的钉死 sector tag 匹配。
    def tag_match(self, entry: dict[str, Any], vpn: Any) -> Any:
        """Return the pinned four-level sector comparison. / 返回钉死的四级 sector 比较。"""

        tag = entry["tag"]
        level = entry["level"]
        low = Mux(entry["n"], tag[1:6] == vpn[4:9], tag[0:6] == vpn[3:9])
        return (tag[24:35] == vpn[27:38])             & ((tag[15:24] == vpn[18:27]) | (level == Const(3, 2)))             & ((tag[6:15] == vpn[9:18]) | level[1])             & (low | (level != Const(0, 2)))

    # Return the pinned sector ppn composition of one way. / 返回某一路的钉死 sector ppn 组合。
    def gen_ppn(self, entry: dict[str, Any], vpn: Any) -> Any:
        """Return the pinned 36-bit ``genPPN`` value. / 返回钉死的 36 位 ``genPPN`` 值。"""

        ppn = entry["ppn"]
        level = entry["level"]
        low_sel = Cat(*[entry["ppn_low_%d" % sector] for sector in range(self.TLB_SECTORS)])
        sector: Any = vpn[0:3]
        low_vec: Any = low_sel
        inner = Mux(level != Const(0, 2), vpn[0:9],
                    Mux(entry["n"], Cat(ppn[1:6], vpn[0:4]), Cat(ppn[0:6], low_vec.bit_select(sector, 3))))
        return Cat(inner,
                   Mux(level[1], vpn[9:18], ppn[6:15]),
                   Mux(level == Const(3, 2), vpn[18:27], ppn[15:24]),
                   ppn[24:33])

    # Select one per-way field by the registered hit vector. / 按已寄存命中向量选择某一路字段。
    def mux_by_hits(self, hit_reg: list[Signal], pick: Any) -> Any:
        """Return the one-hot selected value over the ways. / 返回各路上 one-hot 选择的值。"""

        result: Any = pick(0)
        for way in range(1, self.n_ways):
            result = result | Mux(hit_reg[way], pick(way), Const(0, len(pick(0))))
        return result

    # Return the pinned merged write image of one refill. / 返回一次 refill 的钉死合并写映像。
    def write_image(self, p: dict[str, Signal]) -> dict[str, Any]:
        """Return the pinned s1/s2 merged entry fields of ``io_w_*``. / 返回 ``io_w_*`` 的钉死 s1/s2 合并表项字段。"""

        w_s2x = p["io_w_bits_data_s2xlate"]
        s1_level = p["io_w_bits_data_s1_entry_level"]
        s2_level = p["io_w_bits_data_s2_entry_level"]
        s1_n = p["io_w_bits_data_s1_entry_n"]
        s2_n = p["io_w_bits_data_s2_entry_n"]
        s1_pf = p["io_w_bits_data_s1_pf"] if self.spec.has("io_w_bits_data_s1_pf") else Const(0, 1)
        s1_af = p["io_w_bits_data_s1_af"] if self.spec.has("io_w_bits_data_s1_af") else Const(0, 1)
        s2_gpf = p["io_w_bits_data_s2_gpf"] if self.spec.has("io_w_bits_data_s2_gpf") else Const(0, 1)
        s2_gaf = p["io_w_bits_data_s2_gaf"] if self.spec.has("io_w_bits_data_s2_gaf") else Const(0, 1)
        s1_v = p["io_w_bits_data_s1_entry_v"]
        vmid_t = w_s2x == Const(2, 2)
        ppn_t = w_s2x == Const(1, 2)
        inner_n_t = vmid_t
        merge_level = Mux(w_s2x != Const(0, 2),
                          Mux(w_s2x == Const(3, 2),
                              Mux(s1_level < s2_level, s1_level, s2_level),
                              Mux(inner_n_t, s2_level, s1_level)),
                          s1_level)
        all_stage_t3 = ~s1_pf & ~s1_v & ~s1_af
        s2_exception = s2_gpf | s2_gaf
        inner_level = Mux(w_s2x != Const(3, 2), merge_level,
                          Mux(((s1_pf | s1_af) & ~all_stage_t3)
                              | (s2_exception & ~((p["io_w_bits_data_s1_entry_perm_r"]
                                                   | p["io_w_bits_data_s1_entry_perm_x"]
                                                   | p["io_w_bits_data_s1_entry_perm_w"]) & s1_v)),
                              s1_level,
                              Mux(s2_exception & all_stage_t3, Const(3, 2), merge_level)))
        inner_n = Mux(w_s2x != Const(0, 2),
                      Mux(w_s2x == Const(3, 2),
                          (s1_n & (s2_level != Const(0, 2))) | (s2_n & (s1_level != Const(0, 2))) | (s1_n & s2_n),
                          Mux(inner_n_t, s2_n, s1_n)),
                      s1_n)
        is_super = (inner_level != Const(0, 2)) | inner_n
        s2_tag = p["io_w_bits_data_s2_entry_tag"]
        s2_ppn = p["io_w_bits_data_s2_entry_ppn"]
        g341 = [Cat(s2_tag[0:27], s2_ppn[27:36]), Cat(s2_tag[0:18], s2_ppn[18:36]),
                Cat(s2_tag[0:9], s2_ppn[9:36]),
                Mux(s2_n, Cat(s2_tag[0:4], s2_ppn[4:36]), s2_ppn[0:36])]
        g342 = [Cat(s2_tag[3:27], s2_ppn[27:36]), Cat(s2_tag[3:18], s2_ppn[18:36]),
                Cat(s2_tag[3:9], s2_ppn[9:36]),
                Mux(s2_n, Cat(s2_tag[3], s2_ppn[4:36]), s2_ppn[3:36])]
        g341_sel: Any = g341[0]
        g342_sel: Any = g342[0]
        for index in range(1, 4):
            g341_sel = Mux(s2_level == index, g341[index], g341_sel)
            g342_sel = Mux(s2_level == index, g342[index], g342_sel)
        image: dict[str, Any] = {
            "tag": Mux(vmid_t, s2_tag[3:38], p["io_w_bits_data_s1_entry_tag"]),
            "asid": p["io_w_bits_data_s1_entry_asid"],
            "vmid": p["io_w_bits_data_s2_entry_vmid"],
            "level": inner_level,
            "ppn": Mux((w_s2x == Const(0, 2)) | ppn_t, p["io_w_bits_data_s1_entry_ppn"][0:33], g342_sel),
            "n": inner_n,
            "pbmt": p["io_w_bits_data_s1_entry_pbmt"],
            "g_pbmt": p["io_w_bits_data_s2_entry_pbmt"],
            "s2xlate": w_s2x,
            "perm_pf": s1_pf, "perm_af": s1_af, "perm_v": s1_v,
            "perm_a": p["io_w_bits_data_s1_entry_perm_a"],
            "perm_u": p["io_w_bits_data_s1_entry_perm_u"],
            "perm_x": p["io_w_bits_data_s1_entry_perm_x"],
            "perm_w": p["io_w_bits_data_s1_entry_perm_w"],
            "perm_r": p["io_w_bits_data_s1_entry_perm_r"],
            "perm_g": p["io_w_bits_data_s1_entry_perm_g"],
            "g_perm_pf": s2_gpf, "g_perm_af": s2_gaf,
            "g_perm_a": p["io_w_bits_data_s2_entry_perm_a"],
            "g_perm_x": p["io_w_bits_data_s2_entry_perm_x"],
        }
        use_s1_low = (w_s2x == Const(0, 2)) | ppn_t
        for sector in range(self.TLB_SECTORS):
            one_hot = s2_tag[0:3] == sector if sector < self.TLB_SECTORS - 1 else (s2_tag[0:3] == Const(7, 3))
            image["ppn_low_%d" % sector] = Mux(use_s1_low, p["io_w_bits_data_s1_ppn_low_%d" % sector],
                                               g341_sel[0:3])
            image["valididx_%d" % sector] = is_super | Mux(vmid_t, one_hot,
                                                           p["io_w_bits_data_s1_valididx_%d" % sector])
            image["pteidx_%d" % sector] = Mux(vmid_t, one_hot,
                                              p["io_w_bits_data_s1_pteidx_%d" % sector])
        return image

    # Elaborate the valid banks, hit logic, refill and sfence rules. / 展开有效位组、命中逻辑、refill 与 sfence 规则。
    def elaborate(self, platform: Any) -> Module:
        """Elaborate the fully-associative TLB storage. / 展开全相联 TLB 存储。"""

        del platform
        m: Any = Module()
        self.attach_domain(m)
        p = self.ports
        ways = self.n_ways
        valid = Array(Signal(name="v_%d" % way, reset=0) for way in range(ways))
        entries = Array(self.entry_bank(way) for way in range(ways))
        image = self.write_image(p)
        if self.has_way_idx:
            refill_hit = [p["io_w_valid"] & (p["io_w_bits_wayIdx"] == way) for way in range(ways)]
        else:
            refill_ptr = Signal(6, name="refill_wayIdx_reg", reset=0)
            refill_hit = [p["io_w_valid"] & (refill_ptr == way) for way in range(ways)]
            with m.If(p["io_w_valid"]):
                m.d.ck += refill_ptr.eq(refill_ptr + 1)
        for way in range(ways):
            with m.If(refill_hit[way]):
                for name, reg in cast(dict[str, Any], entries[way]).items():
                    m.d.ck += reg.eq(image[name])
        for way in range(ways):
            with m.If(refill_hit[way]):
                m.d.ck += valid[way].eq(1)

        # Pinned sfence invalidation rules. / 钉死的 sfence 失效规则。
        sfence_id = p["io_sfence_bits_id"] if self.spec.has("io_sfence_bits_id") else Const(0, 16)
        sfence_addr = p["io_sfence_bits_addr"] if self.spec.has("io_sfence_bits_addr") else Const(0, 50)
        priv_virt = p["io_csr_priv_virt"] if self.spec.has("io_csr_priv_virt") else Const(0, 1)
        hgatp_vmid = p["io_csr_hgatp_vmid"] if self.has_vmid else Const(0, 16)
        for way in range(ways):
            entry = cast(dict[str, Any], entries[way])
            has_s2 = entry["s2xlate"] != Const(0, 2)
            vmid_eq = Cat(Const(0, 2), entry["vmid"]) == hgatp_vmid
            asid_eq = entry["asid"] == sfence_id
            vpn_match = self.tag_match(entry, sfence_addr[50 - self.vpn_bits:50])
            sector = sfence_addr[12:15]
            addr_vec: Any = Cat(*[entry["valididx_%d" % s] for s in range(self.TLB_SECTORS)])
            addr_hit = vpn_match & addr_vec.bit_select(sector, 1)
            with m.If(p["io_sfence_valid"] & p["io_sfence_bits_hg"]):
                with m.If(p["io_sfence_bits_rs2"]):
                    m.d.ck += valid[way].eq(valid[way] & ~has_s2)
                with m.Else():
                    m.d.ck += valid[way].eq(valid[way] & ~(has_s2 & vmid_eq))
            with m.Elif(p["io_sfence_valid"] & p["io_sfence_bits_hv"]):
                m.d.ck += valid[way].eq(valid[way] & ~(has_s2 & vmid_eq))
            with m.Elif(p["io_sfence_valid"]):
                cond_a = p["io_sfence_bits_rs1"] | priv_virt
                with m.If(cond_a):
                    with m.If(p["io_sfence_bits_rs2"]):
                        m.d.ck += valid[way].eq(valid[way] & ~(
                            (~priv_virt & ~has_s2) | (priv_virt & has_s2 & vmid_eq)))
                    with m.Else():
                        m.d.ck += valid[way].eq(valid[way] & ~(
                            ~entry["perm_g"] & ((~priv_virt & ~has_s2 & asid_eq)
                                                | (priv_virt & has_s2 & asid_eq & vmid_eq))))
                with m.Else():
                    m.d.ck += valid[way].eq(valid[way] & ~(~entry["perm_g"] & ~has_s2 & addr_hit))

        for port in range(self.num_ports):
            vpn = p["io_r_req_%d_bits_vpn" % port]
            s2xlate = p["io_r_req_%d_bits_s2xlate" % port]
            hit_x2 = Mux(s2xlate != Const(0, 2), p["io_csr_vsatp_asid"], p["io_csr_satp_asid"])
            s2_is_2 = (s2xlate != Const(0, 2)) & (s2xlate == Const(2, 2))
            pteidx_t331 = s2xlate != Const(1, 2)
            refill_mask = Mux(p["io_w_valid"],
                              Const(1, ways).bit_select(p["io_w_bits_wayIdx"], 1)
                              if self.has_way_idx else Const(0, 1).bit_select(Const(0, 1), 1),
                              Const(0, 1))
            hit_vec = []
            for way in range(ways):
                entry = cast(dict[str, Any], entries[way])
                valididx_vec: Any = Cat(*[entry["valididx_%d" % s] for s in range(self.TLB_SECTORS)])
                pteidx_vec: Any = Cat(*[entry["pteidx_%d" % s] for s in range(self.TLB_SECTORS)])
                sector: Any = vpn[0:3]
                hit = (entry["s2xlate"] == s2xlate) \
                    & (s2_is_2 | (entry["asid"] == hit_x2) | entry["perm_g"]) \
                    & self.tag_match(entry, vpn) \
                    & valididx_vec.bit_select(sector, 1) \
                    & ((s2xlate == Const(0, 2)) | vmid_match(entry, hgatp_vmid)) \
                    & (~((s2xlate != Const(0, 2)) & (entry["level"] == Const(0, 2))
                         & pteidx_t331 & ~entry["n"])
                       | pteidx_vec.bit_select(sector, 1)) \
                    & valid[way] & ~refill_mask
                hit_vec.append(hit)
            hit_reg = [Signal(name="hitVecReg_%d_%d" % (port, way), reset=0) for way in range(ways)]
            m.d.ck += [hit_reg[way].eq(hit_vec[way]) for way in range(ways)]
            if "io_r_resp_%d_valid" % port in p:
                m.d.ck += p["io_r_resp_%d_valid" % port].eq(p["io_r_req_%d_valid" % port])
            req_vpn = Signal(self.vpn_bits, name="reqVpn_%d" % port)
            m.d.ck += req_vpn.eq(vpn)
            hit_any = hit_reg[0]
            for way in range(1, ways):
                hit_any = hit_any | hit_reg[way]
            m.d.comb += p["io_r_resp_%d_bits_hit" % port].eq(hit_any)

            for dup in range(self.num_dups):
                m.d.comb += p["io_r_resp_%d_bits_ppn_%d" % (port, dup)].eq(
                    self.mux_by_hits(hit_reg, lambda way: self.gen_ppn(
                        cast(dict[str, Any], entries[way]), req_vpn)))
                m.d.comb += p["io_r_resp_%d_bits_pbmt_%d" % (port, dup)].eq(
                    self.mux_by_hits(hit_reg, lambda way: cast(dict[str, Any], entries[way])["pbmt"]))
                m.d.comb += p["io_r_resp_%d_bits_g_pbmt_%d" % (port, dup)].eq(
                    self.mux_by_hits(hit_reg, lambda way: cast(dict[str, Any], entries[way])["g_pbmt"]))
                for perm in ("pf", "af", "v", "a", "u", "x", "w", "r"):
                    out_name = "io_r_resp_%d_bits_perm_%d_%s" % (port, dup, perm)
                    if out_name in p:
                        m.d.comb += p[out_name].eq(
                            self.mux_by_hits(hit_reg, lambda way, q=perm: cast(dict[str, Any], entries[way])["perm_" + q]))
                for perm in ("pf", "af", "a", "x"):
                    out_name = "io_r_resp_%d_bits_g_perm_%d_%s" % (port, dup, perm)
                    if out_name in p:
                        m.d.comb += p[out_name].eq(
                            self.mux_by_hits(hit_reg, lambda way, q=perm: cast(dict[str, Any], entries[way])["g_perm_" + q]))
        return m


def vmid_match(entry: dict[str, Any], hgatp_vmid: Any) -> Any:
    """Return the pinned zero-extended vmid comparison. / 返回钉死的零扩展 vmid 比较。"""

    return Cat(Const(0, 2), entry["vmid"]) == hgatp_vmid


class TlbStorageWrapperModel(TlbFaModel):
    """Pinned ``TlbStorageWrapper`` pass-through over the same FA core. / 同一 FA 核之上的钉死 ``TlbStorageWrapper`` 透传。"""

    # Construct the wrapper ports; the refill way choice stays internal. / 构造包装端口；refill 路选择保持内部。
    def __init__(self, spec: FamilySpec, top_name: str = "UHSCTlbStorageWrapper") -> None:
        super().__init__(spec, top_name)

    # Elaborate the same FA storage without external way ports. / 展开无外部路端口的同一 FA 存储。
    def elaborate(self, platform: Any) -> Module:
        """Elaborate the wrapper as the FA core with an internal victim way. / 将包装展开为带内部替换路的 FA 核。"""

        return super().elaborate(platform)


class VSplitPipelineModel(PortBound):
    """Faithful Amaranth model of the pinned vector split pipeline stage. / 钉死向量分裂流水线级的忠实 Amaranth 模型。"""

    # Construct the pinned split pipeline ports. / 构造钉死的分裂流水线端口。
    def __init__(self, spec: FamilySpec, top_name: str = "UHSCVSplitPipeline") -> None:
        super().__init__(spec, top_name)
        self.is_v_store = bool(spec.params.get("isVStore", 0))

    # Return the in-flight uop robIdx flag field. / 返回在飞 uop 的 robIdx flag 字段。
    def uop_flag(self) -> Any:
        """Return the pinned uop robIdx flag or a constant. / 返回钉死的 uop robIdx flag 或常量。"""

        name = "io_in_bits_uop_robIdx_flag"
        return self.ports[name] if self.spec.has(name) else Const(0, 1)

    # Return the in-flight uop robIdx value field. / 返回在飞 uop 的 robIdx value 字段。
    def uop_value(self) -> Any:
        """Return the pinned uop robIdx value or a constant. / 返回钉死的 uop robIdx value 或常量。"""

        name = "io_in_bits_uop_robIdx_value"
        return self.ports[name] if self.spec.has(name) else Const(0, 1)

    # Elaborate the pinned s1 valid/kill/handshake structure. / 展开钉死的 s1 valid/kill/握手结构。
    def elaborate(self, platform: Any) -> Module:
        """Elaborate the pipeline register and merge-buffer handshake. / 展开流水线寄存器与 merge-buffer 握手。"""

        del platform
        m: Any = Module()
        self.attach_domain(m)
        p = self.ports
        s1_valid = Signal(name="s1_valid", reset=0)
        in_kill = rob_need_flush(self.uop_flag(), self.uop_value(), p["io_redirect_valid"],
                                 p["io_redirect_bits_robIdx_flag"], p["io_redirect_bits_robIdx_value"],
                                 p["io_redirect_bits_level"])
        in_fire = p["io_in_valid"] & p["io_in_ready"]
        out_fire = p["io_out_ready"] & p["io_out_valid"]
        threshold_ready = p["io_toMergeBuffer_req_ready"] if self.spec.has("io_toMergeBuffer_req_ready") else Const(1, 1)
        s1_can_go = p["io_out_ready"] & (threshold_ready | p["io_out_valid"])
        s1_ready = in_kill | ~s1_valid | s1_can_go
        m.d.comb += p["io_in_ready"].eq(s1_ready)
        with m.If(in_fire):
            m.d.ck += s1_valid.eq(1)
        with m.Elif(out_fire | in_kill):
            m.d.ck += s1_valid.eq(0)
        m.d.comb += p["io_out_valid"].eq(s1_valid)
        if self.spec.has("io_toMergeBuffer_req_valid"):
            m.d.comb += p["io_toMergeBuffer_req_valid"].eq(p["io_out_ready"] & s1_valid)
        for field in self.spec.fields("io_out_bits_"):
            source = "io_in_bits_" + field[len("io_out_bits_"):]
            if source in p:
                m.d.comb += p[field].eq(p[source])
        for field in self.spec.fields("io_toMergeBuffer_req_bits_"):
            source = "io_in_bits_" + field[len("io_toMergeBuffer_req_bits_"):]
            if source in p:
                m.d.comb += p[field].eq(p[source])
        return m


class VSplitBufferModel(PortBound):
    """Faithful Amaranth model of the pinned vector split buffer. / 钉死向量分裂缓冲的忠实 Amaranth 模型。"""

    # Construct the pinned split buffer ports and beat geometry. / 构造钉死的分裂缓冲端口与 beat 几何。
    def __init__(self, spec: FamilySpec, top_name: str = "UHSCVSplitBuffer") -> None:
        super().__init__(spec, top_name)
        self.is_v_store = bool(spec.params.get("isVStore", 0))
        self.flow_idx_bits = max(1, self.max_flow_num().bit_length())

    # Report the pinned maximum flow number of this buffer. / 返回本缓冲的钉死最大流数。
    def max_flow_num(self) -> int:
        """Return the retained splitIndex port range bound. / 返回保留的 splitIndex 端口范围上界。"""

        name = "io_out_bits_splitIndex"
        return self.spec.width(name) if self.spec.has(name) else 8

    # Return the buffered uop flow-number field or the bounded maximum. / 返回缓冲 uop 的流数字段或有界最大值。
    def flow_num_value(self) -> Any:
        """Return the retained ``flowNum`` field or the maximum. / 返回保留的 ``flowNum`` 字段或最大值。"""

        name = "io_out_bits_flowNum"
        return self.ports[name] if self.spec.has(name) else Const(self.max_flow_num(), self.flow_idx_bits + 1)

    # Return the pinned per-issue beat count of this buffer. / 返回本缓冲的钉死每次发射 beat 数。
    def issue_count(self) -> Any:
        """Return the pinned issueCount value of one issue. / 返回一次发射的钉死 issueCount。"""

        return Const(1, self.flow_idx_bits + 1)

    # Return the pinned per-flow activity flag of the current beat. / 返回当前 beat 的钉死逐流有效标志。
    def vec_active(self) -> Any:
        """Return the retained ``vecActive`` field when present. / 返回存在的 ``vecActive`` 字段。"""

        name = "io_out_bits_vecActive"
        return self.ports[name] if self.spec.has(name) else Const(1, 1)

    # Return the buffered uop robIdx flag field. / 返回缓冲 uop 的 robIdx flag 字段。
    def uopq_flag(self) -> Any:
        """Return the registered uop robIdx flag. / 返回已寄存的 uop robIdx flag。"""

        name = "io_out_bits_uop_robIdx_flag"
        return self.ports[name] if self.spec.has(name) else Const(0, 1)

    # Return the buffered uop robIdx value field. / 返回缓冲 uop 的 robIdx value 字段。
    def uopq_value(self) -> Any:
        """Return the registered uop robIdx value. / 返回已寄存的 uop robIdx value。"""

        name = "io_out_bits_uop_robIdx_value"
        return self.ports[name] if self.spec.has(name) else Const(0, 1)

    # Return the incoming uop robIdx flag field. / 返回入向 uop 的 robIdx flag 字段。
    def in_flag(self) -> Any:
        """Return the incoming uop robIdx flag. / 返回入向 uop 的 robIdx flag。"""

        name = "io_in_bits_uop_robIdx_flag"
        return self.ports[name] if self.spec.has(name) else Const(0, 1)

    # Return the incoming uop robIdx value field. / 返回入向 uop 的 robIdx value 字段。
    def in_value(self) -> Any:
        """Return the incoming uop robIdx value. / 返回入向 uop 的 robIdx value。"""

        name = "io_in_bits_uop_robIdx_value"
        return self.ports[name] if self.spec.has(name) else Const(0, 1)

    # Elaborate the pinned allocated/splitIdx beat counters. / 展开钉死的 allocated/splitIdx beat 计数。
    def elaborate(self, platform: Any) -> Module:
        """Elaborate the split state machine and issue counting. / 展开分裂状态机与发射计数。"""

        del platform
        m: Any = Module()
        self.attach_domain(m)
        p = self.ports
        allocated = Signal(name="allocated", reset=0)
        split_idx = Signal(self.flow_idx_bits, name="splitIdx", reset=0)
        stride_width = self.spec.width("io_out_bits_stride") if self.spec.has("io_out_bits_stride") else 16
        stride_offset = Signal(stride_width, name="strideOffsetReg", reset=0)
        in_kill = rob_need_flush(self.in_flag(), self.in_value(), p["io_redirect_valid"],
                                 p["io_redirect_bits_robIdx_flag"], p["io_redirect_bits_robIdx_value"],
                                 p["io_redirect_bits_level"])
        need_enqueue = p["io_in_valid"] & ~in_kill
        out_fire = p["io_out_ready"] & p["io_out_valid"]
        flow_num = self.flow_num_value()
        split_finish = split_idx >= (flow_num - self.issue_count())
        can_accept = ~allocated | (allocated & split_finish)
        do_enqueue = can_accept & need_enqueue
        m.d.comb += p["io_in_ready"].eq(can_accept)
        m.d.comb += p["io_out_valid"].eq(allocated & ~self.uopq_kill() & self.vec_active())
        with m.If(do_enqueue):
            m.d.ck += allocated.eq(1)
            for field in self.spec.fields("io_in_bits_"):
                target = "io_out_bits_" + field[len("io_in_bits_"):]
                if target in p:
                    m.d.ck += p[target].eq(p[field])
        with m.Elif(self.uopq_kill()):
            m.d.ck += [allocated.eq(0), split_idx.eq(0), stride_offset.eq(0)]
        with m.Elif(split_finish & out_fire):
            m.d.ck += [allocated.eq(0), split_idx.eq(0), stride_offset.eq(0)]
        with m.Elif(out_fire):
            m.d.ck += split_idx.eq(split_idx + self.issue_count())
            if self.spec.has("io_out_bits_stride"):
                m.d.ck += stride_offset.eq(Mux(split_finish, Const(0, stride_width),
                                               stride_offset + p["io_out_bits_stride"]))
        return m

    # Return the pinned needCancel predicate of the buffered uop. / 返回缓冲 uop 的钉死 needCancel 谓词。
    def uopq_kill(self) -> Any:
        """Return the registered uop needFlush predicate. / 返回已寄存 uop 的 needFlush 谓词。"""

        q = self.ports
        return rob_need_flush(self.uopq_flag(), self.uopq_value(), q["io_redirect_valid"],
                              q["io_redirect_bits_robIdx_flag"], q["io_redirect_bits_robIdx_value"],
                              q["io_redirect_bits_level"])


class VSplitImpModel(PortBound):
    """Faithful Amaranth model of the pinned vector split imp wrapper. / 钉死向量分裂 Imp 包装的忠实 Amaranth 模型。"""

    # Construct the pinned split imp ports. / 构造钉死的分裂 Imp 端口。
    def __init__(self, spec: FamilySpec, top_name: str = "UHSCVSplitImp") -> None:
        super().__init__(spec, top_name)
        self.is_v_store = bool(spec.params.get("isVStore", 0))

    # Elaborate the pinned skid-buffer connection and routing. / 展开钉死的 skid-buffer 连接与路由。
    def elaborate(self, platform: Any) -> Module:
        """Elaborate the skid register and the pass-through routing. / 展开 skid 寄存器与透传路由。"""

        del platform
        m: Any = Module()
        self.attach_domain(m)
        p = self.ports
        skid_valid = Signal(name="skid_valid", reset=0)
        skid_bits = {name: Signal(self.spec.width(name), name="skid_" + name, reset=0)
                     for name in self.spec.fields("io_out_bits_")}
        in_flag = p["io_in_bits_uop_robIdx_flag"] if self.spec.has("io_in_bits_uop_robIdx_flag") else Const(0, 1)
        in_value = p["io_in_bits_uop_robIdx_value"] if self.spec.has("io_in_bits_uop_robIdx_value") else Const(0, 1)
        in_kill = rob_need_flush(in_flag, in_value, p["io_redirect_valid"],
                                 p["io_redirect_bits_robIdx_flag"], p["io_redirect_bits_robIdx_value"],
                                 p["io_redirect_bits_level"])
        out_fire = p["io_out_ready"] & p["io_out_valid"]
        m.d.comb += p["io_in_ready"].eq(~skid_valid | out_fire)
        with m.If(p["io_in_valid"] & p["io_in_ready"] & ~in_kill):
            m.d.ck += skid_valid.eq(1)
            for name, reg in skid_bits.items():
                source = "io_in_bits_" + name[len("io_out_bits_"):]
                if source in p:
                    m.d.ck += reg.eq(p[source])
        with m.If(out_fire):
            m.d.ck += skid_valid.eq(0)
        m.d.comb += p["io_out_valid"].eq(skid_valid | p["io_in_valid"])
        for name, reg in skid_bits.items():
            source_name = "io_in_bits_" + name[len("io_out_bits_"):]
            if source_name in p:
                m.d.comb += p[name].eq(Mux(skid_valid, reg, p[source_name]))
        return m


class LsqUncacheBuffer(PortBound):
    """Faithful Amaranth model of the pinned ``LoadQueueUncache`` parent. / 钉死 ``LoadQueueUncache`` 父模块的忠实 Amaranth 模型。"""

    # Construct the pinned parent ports and entry geometry. / 构造钉死的父模块端口与表项几何。
    def __init__(self, spec: FamilySpec, top_name: str = "UHSCLoadQueueUncache") -> None:
        super().__init__(spec, top_name)
        self.entries_count = spec.params.get("entries", 16)
        self.pipe_width = len({name.split("_")[1] for name in spec.fields("io_req_")
                               if name.split("_")[1].isdigit()})
        self.entry_specs = [family_spec("UncacheEntry" if i == 0 else "UncacheEntry_%d" % i)
                            for i in range(self.entries_count)]
        self.free_spec = family_spec("FreeList_6")
        self.nc_wb_mod = 2

    # Return the retained request field suffixes of one pipeline port. / 返回某流水线端口保留的请求字段后缀。
    def req_fields(self, w: int) -> tuple[str, ...]:
        """Return the ``io_req_w_bits_`` suffixes in pinned order. / 按钉死顺序返回 ``io_req_w_bits_`` 后缀。"""

        return tuple(name[len("io_req_%d_bits_" % w):] for name in self.spec.fields("io_req_%d_bits_" % w))

    # Return one request field signal of one pipeline port. / 返回某流水线端口的一个请求字段信号。
    def req_bits(self, w: int, suffix: str) -> Any:
        """Return the pinned signal of ``io_req_w_bits_<suffix>``. / 返回 ``io_req_w_bits_<suffix>`` 的钉死信号。"""

        name = "io_req_%d_bits_%s" % (w, suffix)
        return self.ports[name] if self.spec.has(name) else Const(0, 1)

    # Return the pinned retained-exception zero predicate. / 返回钉死的保留异常为零谓词。
    def exception_zero(self, fields: dict[str, Signal]) -> Any:
        """Return the pinned AND of inverted retained exceptionVec fields. / 返回保留 exceptionVec 字段取反的钉死与。"""

        zero: Any = Const(1, 1)
        for name, signal in fields.items():
            if name.startswith("uop_exceptionVec_"):
                zero = zero & ~signal
        return zero

    # Return the pinned retained-replay zero predicate. / 返回钉死的保留重放为零谓词。
    def replay_zero(self, fields: dict[str, Signal]) -> Any:
        """Return the pinned AND of inverted retained rep_info causes. / 返回保留 rep_info cause 取反的钉死与。"""

        zero: Any = Const(1, 1)
        for name, signal in fields.items():
            if name.startswith("rep_info_cause_"):
                zero = zero & ~signal
        return zero

    # Return the pinned mmio-or-nc uncache predicate. / 返回钉死的 mmio-or-nc 非缓存谓词。
    def req_is_uncache(self, fields: dict[str, Signal]) -> Any:
        """Return ``req.mmio | req.nc`` of the retained fields. / 返回保留字段的 ``req.mmio | req.nc``。"""

        value: Any = Const(0, 1)
        if fields.get("mmio") is not None:
            value = value | fields["mmio"]
        if fields.get("nc") is not None:
            value = value | fields["nc"]
        return value

    # Return the pinned rank-based ``HwSort`` one-hot selection rows. / 返回钉死按 rank 的 ``HwSort`` one-hot 选择行。
    def sort_rows(self, valids: list[Any], flags: list[Any], values: list[Any]) -> list[list[Any]]:
        """Return one row per output slot of the pinned sorter. / 返回钉死排序器每个输出槽一行。"""

        size = len(valids)
        ranks: list[Any] = []
        for i in range(size):
            older_count: Any = Const(0, 3)
            for j in range(size):
                if i == j:
                    continue
                if j < i:
                    older = (flags[j] != flags[i]) != (values[j] > values[i])
                else:
                    older = (flags[j] != flags[i]) != (values[j] > values[i])
                older_count = older_count + Mux(valids[j] & ~valids[i], 1,
                                                Mux(valids[i] & valids[j] & older, 1, 0))
            ranks.append(older_count)
        rows: list[list[Any]] = []
        for k in range(size):
            row: list[Any] = []
            for i in range(size):
                row.append(ranks[i] == k)
            rows.append(row)
        return rows

    # Return the pinned oldest-selection one-hot of the rollback comparator. / 返回回滚比较器的钉死最老选择 one-hot。
    def oldest_rows(self, valids: list[Any], flags: list[Any], values: list[Any]) -> list[Any]:
        """Return the pinned ``selectOldestRedirect`` one-hot vector. / 返回钉死 ``selectOldestRedirect`` one-hot 向量。"""

        size = len(valids)
        result: list[Any] = []
        for i in range(size):
            terms: Any = valids[i]
            for j in range(size):
                if j == i:
                    continue
                older_j = (flags[j] != flags[i]) != (values[j] > values[i])
                terms = terms & (~valids[j] | ~older_j)
            result.append(terms)
        return result

    # Return the pinned round-robin cyclic gap of one candidate index. / 返回某个候选下标的钉死轮询循环间隔。
    def rr_gap(self, last_index: Any, index: int) -> Any:
        """Return ``(index - last - 1) mod N`` as a signal expression. / 返回信号表达式的 ``(index - last - 1) mod N``。"""

        if index == 0:
            return (self.entries_count - 1) - last_index
        return Mux(last_index <= index - 1, (index - 1) - last_index,
                   self.entries_count + index - 1 - last_index)

    # Elaborate the pinned allocator, entry array and uncache routing. / 展开钉死的分配器、表项阵列与 uncache 路由。
    def elaborate(self, platform: Any) -> Module:
        """Elaborate the uncache buffer parent behaviour. / 展开非缓存缓冲父模块行为。"""

        del platform
        m: Any = Module()
        self.attach_domain(m)
        p = self.ports
        width = self.pipe_width

        # pinned lastCycle/lastLastCycle redirect registers.
        # 钉死的 lastCycle/lastLastCycle 重定向寄存器。
        last_flag = Signal(name="lastCycleRedirect_flag", reset=0)
        last_value = Signal(8, name="lastCycleRedirect_value", reset=0)
        last_level = Signal(name="lastCycleRedirect_level", reset=0)
        last_valid = Signal(name="lastCycleRedirect_valid", reset=0)
        last2_flag = Signal(name="lastLastCycleRedirect_flag", reset=0)
        last2_value = Signal(8, name="lastLastCycleRedirect_value", reset=0)
        last2_level = Signal(name="lastLastCycleRedirect_level", reset=0)
        last2_valid = Signal(name="lastLastCycleRedirect_valid", reset=0)
        m.d.ck += [last_valid.eq(p["io_redirect_valid"]),
                   last_flag.eq(p["io_redirect_bits_robIdx_flag"]),
                   last_value.eq(p["io_redirect_bits_robIdx_value"]),
                   last_level.eq(p["io_redirect_bits_level"]),
                   last2_valid.eq(last_valid),
                   last2_flag.eq(last_flag),
                   last2_value.eq(last_value),
                   last2_level.eq(last_level)]

        # s1 hold and s2 enqueue registers per pipeline port (pinned 2-stage).
        # 每个流水线端口的 s1 保持与 s2 入队寄存（钉死两级）。
        s1_valid = [Signal(name="s1_valid_%d" % w, reset=0) for w in range(width)]
        s1_req: list[dict[str, Signal]] = []
        s2_valid = [Signal(name="s2_valid_%d" % w, reset=0) for w in range(width)]
        s2_req: list[dict[str, Signal]] = []
        redirect_flag = p["io_redirect_bits_robIdx_flag"]
        redirect_value = p["io_redirect_bits_robIdx_value"]
        redirect_level = p["io_redirect_bits_level"]
        redirect_valid = p["io_redirect_valid"]
        for w in range(width):
            fields = self.req_fields(w)
            s1_req.append({name: Signal(self.spec.width(name), name="s1_" + name, reset=0)
                           for name in fields})
            s2_req.append({name: Signal(self.spec.width(name), name="s2_" + name, reset=0)
                           for name in fields})
            for name, reg in s1_req[w].items():
                m.d.ck += reg.eq(p[name])
            for name, reg in s2_req[w].items():
                m.d.ck += reg.eq(s1_req[w][name])
            s1_flag = s1_req[w].get("uop_robIdx_flag")
            s1_value = s1_req[w].get("uop_robIdx_value")
            if s1_flag is None or s1_value is None:
                m.d.ck += [s1_valid[w].eq(p["io_req_%d_valid" % w]), s2_valid[w].eq(s1_valid[w])]
            else:
                kill = rob_need_flush(s1_flag, s1_value, redirect_valid, redirect_flag,
                                      redirect_value, redirect_level)
                kill = kill | rob_need_flush(s1_flag, s1_value, last_valid, last_flag,
                                             last_value, last_level)
                m.d.ck += s1_valid[w].eq(p["io_req_%d_valid" % w])
                m.d.ck += s2_valid[w].eq(s1_valid[w] & ~kill)
            m.d.comb += p["io_req_%d_ready" % w].eq(Const(1, 1))

        # pinned pre-alloc free-list allocator feeding the enqueuing ports.
        # 钉死 pre-alloc 空闲表分配器馈给入队端口。
        free_list = LsqUncacheFreeList(self.free_spec, top_name="freeList")
        m.submodules.freeList = free_list
        s2_enqueue: list[Any] = []
        for w in range(width):
            s2_enqueue.append(s2_valid[w] & self.exception_zero(s2_req[w])
                              & self.replay_zero(s2_req[w]) & self.req_is_uncache(s2_req[w]))
        enq_valid_vec: list[Any] = []
        enq_index_vec: list[Any] = []
        for w in range(width):
            offset_bits = [s2_enqueue[k] for k in range(w)]
            offset = popcount_of(offset_bits) if offset_bits else Const(0, 2)
            can_name = "io_canAllocate_%d" % offset
            can_allocate: Any = free_list.sig(can_name) if free_list.spec.has(can_name) else Const(1, 1)
            slot_name = "io_allocateSlot_%d" % offset
            enq_valid_vec.append(s2_enqueue[w] & can_allocate)
            enq_index_vec.append(free_list.sig(slot_name))
            m.d.comb += free_list.sig("io_doAllocate_%d" % w).eq(enq_valid_vec[w])

        # sixteen faithful entry registers with their pinned routing.
        # 十六个忠实表项寄存器及其钉死路由。
        entries: list[UncacheEntryModel] = []
        for i in range(self.entries_count):
            entry = UncacheEntryModel(self.entry_specs[i], top_name="entries_%d" % i)
            m.submodules["entries_%d" % i] = entry
            entries.append(entry)
        nderr_value = (p["io_uncache_resp_bits_nderr"] if "io_uncache_resp_bits_nderr" in p
                        else Const(0, 1))
        for i, entry in enumerate(entries):
            ep = entry.ports

            m.d.comb += [ep["io_redirect_valid"].eq(redirect_valid),
                         ep["io_redirect_bits_robIdx_flag"].eq(redirect_flag),
                         ep["io_redirect_bits_robIdx_value"].eq(redirect_value),
                         ep["io_redirect_bits_level"].eq(redirect_level),
                         ep["io_rob_pendingMMIOld"].eq(p["io_rob_pendingMMIOld"]),
                         ep["io_rob_pendingPtr_flag"].eq(p["io_rob_pendingPtr_flag"]),
                         ep["io_rob_pendingPtr_value"].eq(p["io_rob_pendingPtr_value"]),
                         ep["io_uncache_idResp_valid"].eq(p["io_uncache_idResp_valid"]),
                         ep["io_uncache_idResp_bits_mid"].eq(p["io_uncache_idResp_bits_mid"]),
                         ep["io_uncache_idResp_bits_sid"].eq(p["io_uncache_idResp_bits_sid"]),
                         ep["io_uncache_resp_valid"].eq(p["io_uncache_resp_valid"]
                                                        & (p["io_uncache_resp_bits_id"] == i)),
                         ep["io_uncache_resp_bits_data"].eq(p["io_uncache_resp_bits_data"]),
                         ep["io_uncache_resp_bits_denied"].eq(p["io_uncache_resp_bits_denied"]),
                         ep["io_uncache_resp_bits_corrupt"].eq(p["io_uncache_resp_bits_corrupt"]),
                         ep["io_mmioOut_ready"].eq(Const(0, 1))]
            if "io_uncache_resp_bits_nderr" in ep:
                m.d.comb += ep["io_uncache_resp_bits_nderr"].eq(
                    p["io_uncache_resp_bits_nderr"] if "io_uncache_resp_bits_nderr" in p
                    else Const(0, 1))
            write_term: Any = Const(0, 1)
            write_bits: dict[str, Any] = {}
            for w in range(width):
                hit = enq_valid_vec[w] & (Const(i, 4) == enq_index_vec[w])
                write_term = write_term | hit
                for name in self.req_fields(w):
                    if name in ep:
                        candidate: Any = s2_req[w][name]
                        write_bits[name] = candidate if name not in write_bits \
                            else Mux(hit, candidate, write_bits[name])
            m.d.comb += ep["io_req_valid"].eq(write_term)
            for name, value in write_bits.items():
                m.d.comb += ep["io_req_bits_" + name].eq(value)

        # pinned deallocation of fired or flushed entries.
        # 钉死的已发射或已冲刷表项释放。
        free_bits: list[Any] = []
        for entry in entries:
            ep = entry.ports
            nc_fire = ep["io_ncOut_valid"] & ep["io_ncOut_ready"]
            mmio_fire = ep["io_mmioSelect"] & ep["io_mmioOut_valid"] & ep["io_mmioOut_ready"]
            free_bits.append(mmio_fire | nc_fire | ep["io_flush"])
        m.d.comb += free_list.sig("io_free").eq(Cat(*free_bits))

        # uncache request: mmio-selected entry wins, otherwise the RR arbiter.
        # uncache 请求：mmio 选中表项优先，否则轮询仲裁。
        rr_last = Signal(self.entries_count, name="ncReqArb_last", reset=1)
        last_index: Any = Const(0, 5)
        for i in range(self.entries_count):
            last_index = last_index | Mux(rr_last[i], i, 0)
        req_valids = [entry.ports["io_uncache_req_valid"] for entry in entries]
        grant_vec: list[Any] = []
        for i in range(self.entries_count):
            own_gap = self.rr_gap(last_index, i)
            higher: Any = Const(0, 1)
            for k in range(self.entries_count):
                if k == i:
                    continue
                other_gap = self.rr_gap(last_index, k)
                higher = higher | (req_valids[k] & (other_gap < own_gap))
            grant_vec.append(req_valids[i] & ~higher)
        next_last: Any = rr_last
        for i in range(self.entries_count):
            next_last = Mux(grant_vec[i], 1 << i, next_last)
        m.d.ck += rr_last.eq(next_last)
        uncache_bits: dict[str, Any] = {}
        for i, entry in enumerate(entries):
            ep = entry.ports
            for name in ep:
                if name.startswith("io_uncache_req_bits_"):
                    suffix = name[len("io_uncache_req_bits_"):]
                    uncache_bits[suffix] = Mux(grant_vec[i], ep[name],
                                               uncache_bits.get(suffix, Const(0, 1)))
        uncache_in_ready = emit_reg(m, p, "io_uncache_req", popcount_of(grant_vec) != 0, uncache_bits)
        for i, entry in enumerate(entries):
            m.d.comb += entry.ports["io_uncache_req_ready"].eq(
                Mux(grant_vec[i], uncache_in_ready, Const(0, 1)))

        # mmio writeback with its pinned pipeline register and raw-data hold.
        # mmio 写回及其钉死流水线寄存器与原始数据保持。
        mmio_bits: dict[str, Any] = {}
        raw_bits: dict[str, Any] = {}
        for entry in entries:
            ep = entry.ports
            for name in ep:
                if name.startswith("io_mmioOut_bits_"):
                    suffix = name[len("io_mmioOut_bits_"):]
                    out_name = "io_mmioOut_2_bits_" + suffix
                    if out_name in p:
                        mmio_bits[suffix] = Mux(ep["io_mmioSelect"], ep[name],
                                                mmio_bits.get(suffix, Const(0, 1)))
                if name.startswith("io_mmioRawData_uop_"):
                    suffix = name[len("io_mmioRawData_uop_"):]
                    out_name = "io_mmioRawData_2_uop_" + suffix
                    if out_name in p:
                        raw_bits[suffix] = Mux(ep["io_mmioSelect"], ep[name],
                                               raw_bits.get(suffix, Const(0, 1)))
            raw_bits["lqData"] = Mux(ep["io_mmioSelect"], ep["io_mmioRawData_lqData"],
                                     raw_bits.get("lqData", Const(0, 1)))
        mmio_in_ready = emit_reg(m, p, "io_mmioOut_2", mmio_entry_valid(entries), mmio_bits)
        for entry in entries:
            m.d.comb += entry.ports["io_mmioOut_ready"].eq(
                Mux(entry.ports["io_mmioSelect"], mmio_in_ready, Const(0, 1)))
        for suffix, value in raw_bits.items():
            out_name = "io_mmioRawData_2_uop_" + suffix if suffix != "lqData" else "io_mmioRawData_2_lqData"
            if out_name in p:
                reg = Signal(self.spec.width(out_name), name="mmioRawData_" + suffix, reset=0)
                m.d.ck += reg.eq(value)
                m.d.comb += p[out_name].eq(reg)

        # nc writeback: two pinned priority ports over the sixteen entries.
        # nc 写回：十六个表项上的两个钉死优先端口。
        nc_valids = [entry.ports["io_ncOut_valid"] for entry in entries]
        for port in range(self.nc_wb_mod):
            out_valid_name = "io_ncOut_%d_valid" % port
            if out_valid_name not in p:
                continue
            base = port * (self.entries_count // self.nc_wb_mod)
            group_size = self.entries_count // self.nc_wb_mod
            selected: Any = Const(0, 1)
            index_value: Any = Const(0, max(1, (group_size - 1).bit_length()))
            found = Const(0, 1)
            for i in range(group_size):
                hit = nc_valids[base + i] & ~found
                selected = selected | hit
                index_value = index_value | Mux(hit, i, 0)
                found = found | hit
            nc_bits: dict[str, Any] = {}
            for i in range(group_size):
                ep = entries[base + i].ports
                for name in ep:
                    if name.startswith("io_ncOut_bits_"):
                        suffix = name[len("io_ncOut_bits_"):]
                        out_name = "io_ncOut_%d_bits_%s" % (port, suffix)
                        if out_name in p:
                            nc_bits[suffix] = Mux(index_value == i, ep[name],
                                                  nc_bits.get(suffix, Const(0, 1)))
            nc_in_ready = emit_reg(m, p, "io_ncOut_%d" % port, selected, nc_bits)
            for i in range(group_size):
                m.d.comb += entries[base + i].ports["io_ncOut_ready"].eq(
                    Mux(index_value == i, nc_in_ready, Const(0, 1)))

        # pinned exception OR and priority mux over the entries.
        # 表项上的钉死异常或与优先选择。
        exception_valid: Any = Const(0, 1)
        for entry in entries:
            exception_valid = exception_valid | entry.ports["io_exception_valid"]
        m.d.comb += p["io_exception_valid"].eq(exception_valid)
        exception_sel: dict[str, Any] = {}
        for i, entry in enumerate(entries):
            ep = entry.ports
            priority: Any = Const(1, 1)
            for k in range(i):
                priority = priority & ~entries[k].ports["io_exception_valid"]
            for name in ep:
                if name.startswith("io_exception_bits_"):
                    suffix = name[len("io_exception_bits_"):]
                    out_name = "io_exception_bits_" + suffix
                    if out_name in p:
                        exception_sel[suffix] = Mux(priority, ep[name],
                                                    exception_sel.get(suffix, Const(0, 1)))
        for suffix, value in exception_sel.items():
            m.d.comb += p["io_exception_bits_" + suffix].eq(value)

        # pinned rob mmio bookkeeping registers.
        # 钉死的 rob mmio 记账寄存器。
        for w in range(width):
            load_name = "io_rob_loadMmio_%d" % w
            if load_name in p:
                mmio_bit = s1_req[w].get("mmio")
                m.d.ck += p[load_name].eq(s1_valid[w] & (mmio_bit if mmio_bit is not None else Const(0, 1)))
            for name in self.spec.fields("io_rob_loadMmioUop_%d_" % w):
                suffix = name[len("io_rob_loadMmioUop_%d_" % w):]
                source = s1_req[w].get("uop_" + suffix)
                if source is not None:
                    m.d.ck += p[name].eq(source)

        # pinned rollback detection with the oldest-selection comparator.
        # 钉死的回滚检测与最老选择比较器。
        if "io_rollback_valid" in p:
            need_check = [s2_enqueue[w] & ~enq_valid_vec[w] for w in range(width)]
            flags = [s2_req[w].get("uop_robIdx_flag", Const(0, 1)) for w in range(width)]
            values = [s2_req[w].get("uop_robIdx_value", Const(0, 8)) for w in range(width)]
            rows = self.oldest_rows(need_check, flags, values)
            oldest_valid: Any = Const(0, 1)
            oldest_flag: Any = Const(0, 1)
            oldest_value: Any = Const(0, 8)
            for w in range(width):
                oldest_valid = oldest_valid | (rows[w] & s2_valid[w])
                oldest_flag = oldest_flag | Mux(rows[w], flags[w], Const(0, 1))
                oldest_value = oldest_value | Mux(rows[w], values[w], Const(0, 8))
            keep = ~rob_need_flush(oldest_flag, oldest_value, redirect_valid, redirect_flag,
                                   redirect_value, redirect_level)
            keep = keep & ~rob_need_flush(oldest_flag, oldest_value, last_valid, last_flag,
                                          last_value, last_level)
            keep = keep & ~rob_need_flush(oldest_flag, oldest_value, last2_valid, last2_flag,
                                          last2_value, last2_level)
            roll_valid = Signal(name="rollback_valid", reset=0)
            m.d.ck += roll_valid.eq(oldest_valid & keep)
            m.d.comb += p["io_rollback_valid"].eq(roll_valid)
            for name in self.spec.fields("io_rollback_bits_"):
                suffix = name[len("io_rollback_bits_"):]
                if suffix == "robIdx_flag":
                    reg = Signal(name="rollback_bits_flag", reset=0)
                    m.d.ck += reg.eq(oldest_flag)
                    m.d.comb += p[name].eq(reg)
                elif suffix == "robIdx_value":
                    reg = Signal(self.spec.width(name), name="rollback_bits_value", reset=0)
                    m.d.ck += reg.eq(oldest_value)
                    m.d.comb += p[name].eq(reg)
                elif suffix == "level":
                    m.d.comb += p[name].eq(Const(1, 1))
        return m


# Return the pinned mmio-selected entry valid of the writeback mux. / 返回写回选择器的钉死 mmio 选中表项 valid。
def mmio_entry_valid(entries: list[UncacheEntryModel]) -> Any:
    """Return the first mmio-selected entry request. / 返回第一个 mmio 选中的表项请求。"""

    selected: Any = Const(0, 1)
    for entry in entries:
        selected = selected | Mux(entry.ports["io_mmioSelect"],
                                  entry.ports["io_mmioOut_valid"], Const(0, 1))
    return selected


# Emit the pinned one-deep ``AddPipelineReg`` skid register on an output pair. / 在输出对上发出钉死的一级 ``AddPipelineReg`` skid 寄存器。
def emit_reg(m: Any, p: dict[str, Signal], prefix: str, in_valid: Any, in_bits: dict[str, Any]) -> Any:
    """Emit the pinned valid/bits pipeline register pair. / 发出钉死的 valid/bits 流水线寄存器对。"""

    if prefix + "_valid" not in p:
        return Const(1, 1)
    out_valid = p[prefix + "_valid"]
    out_ready = p[prefix + "_ready"] if prefix + "_ready" in p else Const(1, 1)
    reg_valid = Signal(name=prefix.replace("io_", "") + "_reg_valid", reset=0)
    in_ready = ~reg_valid | out_ready
    in_fire = in_valid & in_ready
    m.d.comb += out_valid.eq(reg_valid)
    out_fire = out_ready & out_valid
    with m.If(out_fire):
        m.d.ck += reg_valid.eq(0)
    with m.If(in_fire):
        m.d.ck += reg_valid.eq(1)
    for suffix, value in in_bits.items():
        out_name = prefix + "_bits_" + suffix
        if out_name in p:
            reg = Signal(self_width(p, out_name), name=prefix.replace("io_", "") + "_bits_" + suffix, reset=0)
            m.d.ck += reg.eq(Mux(in_fire, value, reg))
            m.d.comb += p[out_name].eq(reg)
    return in_ready


# Return the pinned bit width of one existing port. / 返回某个既有端口的钉死位宽。
def self_width(p: dict[str, Signal], name: str) -> int:
    """Return the bit width of port ``name``. / 返回端口 ``name`` 的位宽。"""

    return len(p[name])


# =============================================================================
# Public Adapter
# =============================================================================
# Emit deterministic UHSC-localized Verilog for one covered family member.
# 为一个被覆盖的 family 成员导出确定性的 UHSC Verilog。
def build_verilog(configuration, injected_dependencies):
    """Return Verilog text for the selected locked module. / 返回所选锁定模块的 Verilog 文本。"""

    del injected_dependencies
    if isinstance(configuration, str):
        module = configuration
    elif isinstance(configuration, dict):
        module = str(configuration.get("module", "FreeList"))
    elif configuration is None:
        module = "FreeList"
    else:
        raise TypeError("configuration must be a module name, a dict, or None")
    spec = family_spec(module)
    member = family_member(spec, "UHSC" + spec.module)
    ports = cast(Any, member).port_surface
    return verilog.convert(member, name="UHSC" + spec.module, ports=ports, emit_src=False)


# Construct the faithful elaboratable of one covered locked module. / 构造一个被覆盖锁定模块的忠实 elaboratable。
def family_member(spec: FamilySpec, top_name: str) -> PortBound:
    """Return the pinned family implementation of ``spec``. / 返回 ``spec`` 的钉死 family 实现。"""

    if spec.family == "freelist":
        return LsqUncacheFreeList(spec, top_name)
    if spec.family == "entry":
        return UncacheEntryModel(spec, top_name)
    if spec.family == "repeater":
        return RepeaterModel(spec, top_name)
    if spec.family == "ptwrepeater":
        return PtwRepeaterNbModel(spec, top_name)
    if spec.family == "tlbfa":
        return TlbFaModel(spec, top_name)
    if spec.family == "tlbsw":
        return TlbStorageWrapperModel(spec, top_name)
    if spec.family == "vsplitpipe":
        return VSplitPipelineModel(spec, top_name)
    if spec.family == "vsplitbuf":
        return VSplitBufferModel(spec, top_name)
    if spec.family == "vsplitimp_v" or spec.family == "vsplitimp_l":
        return VSplitImpModel(spec, top_name)
    return LsqUncacheBuffer(spec, top_name)


# =============================================================================
# Direct Entry
# =============================================================================
# Print a deterministic default export for direct smoke tests. / 为 direct smoke 测试打印确定性默认导出。
def main() -> None:
    """Print the default family export. / 打印默认 family 导出。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
