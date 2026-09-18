"""Register completed bounded family subjects in the V2 core inventory."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "V2-Core-Rewrite-Inventory.json"

NEW = [
    {
        "id": "DebugTriggerFamily",
        "source_scala": ["scala/src/main/scala/xiangshan/backend/fu/NewCSR/Debug.scala"],
        "build_path": "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Fu.NewCSR.DebugFamily-Hardware.py",
        "family_id": "core.backend.newcsr.debug",
        "closure_root": "core.backend.newcsr",
        "classification": "REWRITTEN",
        "disposition": "STRUCTURE_VERIFIED_DIRECT_BOUNDED",
        "v2_status": "VALIDATOR_PASS_BOUNDED",
        "reference_surface": ["upstream/src/main/scala/xiangshan/backend/fu/NewCSR/Debug.scala", "validation/v2-debug-family-results.json"],
    },
    {
        "id": "PrefetchFamily",
        "source_scala": ["scala/src/main/scala/xiangshan/mem/prefetch/SMSPrefetcher.scala", "scala/src/main/scala/xiangshan/mem/prefetch/L1PrefetchComponent.scala", "scala/src/main/scala/xiangshan/mem/prefetch/FDP.scala"],
        "build_path": "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Memory.Prefetch.Family-Hardware.py",
        "family_id": "core.memory.prefetch",
        "closure_root": "core.memory.prefetch",
        "classification": "REWRITTEN",
        "disposition": "STRUCTURE_VERIFIED_DIRECT_BOUNDED",
        "v2_status": "VALIDATOR_PASS_BOUNDED",
        "reference_surface": ["validation/v2-prefetch-family-results.json"],
    },
    {
        "id": "PMPFamily",
        "source_scala": ["scala/src/main/scala/xiangshan/backend/fu/PMP.scala", "scala/src/main/scala/xiangshan/backend/fu/NewCSR/PMPEntryModule.scala"],
        "build_path": "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Fu.PMP.Family-Hardware.py",
        "family_id": "core.backend.newcsr.pmp",
        "closure_root": "core.backend.newcsr",
        "classification": "REWRITTEN",
        "disposition": "STRUCTURE_VERIFIED_DIRECT_BOUNDED",
        "v2_status": "VALIDATOR_PASS_BOUNDED",
        "reference_surface": ["validation/v2-pmp-family-results.json"],
    },
    {
        "id": "StoreFamily",
        "source_scala": ["scala/src/main/scala/xiangshan/mem/sbuffer/Sbuffer.scala", "scala/src/main/scala/xiangshan/mem/lsqueue/StoreQueue.scala", "scala/src/main/scala/xiangshan/mem/lsqueue/StoreMisalignBuffer.scala", "scala/src/main/scala/xiangshan/mem/pipeline/StoreUnit.scala"],
        "build_path": "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Memory.Store.Family-Hardware.py",
        "family_id": "core.memory.store",
        "closure_root": "core.memory",
        "classification": "REWRITTEN",
        "disposition": "STRUCTURE_VERIFIED_DIRECT_BOUNDED",
        "v2_status": "VALIDATOR_PASS_BOUNDED",
        "reference_surface": ["validation/v2-store-family-results.json"],
    },
    {
        "id": "DecodeControlFamily",
        "source_scala": ["scala/src/main/scala/xiangshan/backend/Backend.scala", "scala/src/main/scala/xiangshan/backend/decode/DecodeUnit.scala", "scala/src/main/scala/xiangshan/backend/decode/FusionDecoder.scala", "scala/src/main/scala/xiangshan/backend/decode/UopInfoGen.scala", "scala/src/main/scala/xiangshan/backend/decode/FPDecoder.scala", "scala/src/main/scala/xiangshan/backend/decode/VTypeGen.scala", "scala/src/main/scala/xiangshan/backend/decode/VecExceptionGen.scala", "scala/src/main/scala/xiangshan/backend/fu/wrapper/VIPU.scala"],
        "build_path": "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Decode.ControlFamily-Hardware.py",
        "family_id": "core.backend.decode.control",
        "closure_root": "core.backend",
        "classification": "REWRITTEN",
        "disposition": "STRUCTURE_VERIFIED_DIRECT_BOUNDED",
        "v2_status": "VALIDATOR_PASS_BOUNDED",
        "reference_surface": ["validation/v2-decode-control-family-results.json"],
    },
    {
        "id": "BypassPipeFamily",
        "source_scala": ["scala/src/main/scala/xiangshan/backend/datapath/BypassNetwork.scala", "scala/src/main/scala/xiangshan/backend/PipeGroupConnect.scala"],
        "build_path": "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Datapath.BypassPipeFamily-Hardware.py",
        "family_id": "core.backend.datapath.bypass_pipe",
        "closure_root": "core.backend.datapath",
        "classification": "REWRITTEN",
        "disposition": "STRUCTURE_VERIFIED_DIRECT_BOUNDED",
        "v2_status": "VALIDATOR_PASS_BOUNDED",
        "reference_surface": ["validation/v2-bypass-pipe-family-results.json"],
    },
    {
        "id": "DcacheMissQueueFamily",
        "source_scala": ["scala/src/main/scala/xiangshan/cache/dcache/mainpipe/MissQueue.scala", "scala/src/main/scala/xiangshan/cache/dcache/DCacheWrapper.scala", "scala/src/main/scala/xiangshan/cache/dcache/mainpipe/Probe.scala", "scala/src/main/scala/xiangshan/cache/dcache/mainpipe/WritebackQueue.scala"],
        "build_path": "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Memory.Dcache.MissQueue.Family-Hardware.py",
        "family_id": "core.memory.dcache.miss_queue",
        "closure_root": "core.memory.dcache",
        "classification": "REWRITTEN",
        "disposition": "STRUCTURE_VERIFIED_DIRECT_BOUNDED",
        "v2_status": "VALIDATOR_PASS_BOUNDED",
        "reference_surface": ["validation/v2-dcache-miss-family-results.json"],
    },
    {
        "id": "CSRControlFamily",
        "source_scala": ["scala/src/main/scala/xiangshan/backend/fu/NewCSR/PMAEntryModule.scala", "scala/src/main/scala/xiangshan/backend/fu/NewCSR/InterruptFilter.scala", "scala/src/main/scala/xiangshan/backend/fu/NewCSR/CommitIDModule.scala", "scala/src/main/scala/xiangshan/backend/fu/NewCSR/SatpFlushMod.scala", "scala/src/main/scala/xiangshan/backend/fu/NewCSR/TrapHandleModule.scala", "scala/src/main/scala/xiangshan/backend/fu/NewCSR/TrapInstMod.scala", "scala/src/main/scala/xiangshan/backend/fu/NewCSR/TrapTvalMod.scala", "scala/src/main/scala/xiangshan/backend/fu/NewCSR/PFEvent.scala"],
        "build_path": "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Fu.NewCSR.ControlFamily-Hardware.py",
        "family_id": "core.backend.newcsr.control",
        "closure_root": "core.backend.newcsr",
        "classification": "REWRITTEN",
        "disposition": "STRUCTURE_VERIFIED_DIRECT_BOUNDED",
        "v2_status": "VALIDATOR_PASS_BOUNDED",
        "reference_surface": ["validation/v2-newcsr-control-family-results.json"],
    },
    {
        "id": "VectorMemoryFamily",
        "source_scala": ["scala/src/main/scala/xiangshan/mem/vector/VMergeBuffer.scala", "scala/src/main/scala/xiangshan/mem/vector/VSegmentUnit.scala", "scala/src/main/scala/xiangshan/mem/vector/VfofBuffer.scala", "scala/src/main/scala/xiangshan/mem/lsqueue/VirtualLoadQueue.scala", "scala/src/main/scala/xiangshan/backend/datapath/VldMergeUnit.scala", "scala/src/main/scala/xiangshan/backend/fu/Vsetu.scala"],
        "build_path": "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Memory.Vector.Family-Hardware.py",
        "family_id": "core.memory.vector",
        "closure_root": "core.memory.vector",
        "classification": "REWRITTEN",
        "disposition": "STRUCTURE_VERIFIED_DIRECT_BOUNDED",
        "v2_status": "VALIDATOR_PASS_BOUNDED",
        "reference_surface": ["validation/v2-vector-memory-family-results.json"],
    },
    {
        "id": "FloatingPointFamily",
        "source_scala": ["scala/src/main/scala/yunsuan/fpu/FloatAdder.scala", "scala/src/main/scala/yunsuan/fpu/FloatDivider.scala", "scala/src/main/scala/yunsuan/fpu/FloatFMA.scala", "scala/src/main/scala/yunsuan/fpu/fqrt/fpsqrt_r16.scala", "scala/src/main/scala/xiangshan/backend/fu/Multiplier.scala", "scala/src/main/scala/xiangshan/backend/fu/fpu/IntToFP.scala"],
        "build_path": "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Fu.FloatingPoint.Family-Hardware.py",
        "family_id": "core.backend.fu.floating_point",
        "closure_root": "core.backend.fu",
        "classification": "REWRITTEN",
        "disposition": "STRUCTURE_VERIFIED_DIRECT_BOUNDED",
        "v2_status": "VALIDATOR_PASS_BOUNDED",
        "reference_surface": ["validation/v2-floating-point-family-results.json"],
    },
    {
        "id": "VectorDatapathFamily",
        "source_scala": ["scala/src/main/scala/xiangshan/backend/datapath/Og2ForVector.scala", "scala/src/main/scala/xiangshan/backend/rob/VTypeBuffer.scala", "scala/src/main/scala/xiangshan/backend/VecExcpDataMergeModule.scala"],
        "build_path": "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Datapath.VectorFamily-Hardware.py",
        "family_id": "core.backend.datapath.vector",
        "closure_root": "core.backend.datapath",
        "classification": "REWRITTEN",
        "disposition": "STRUCTURE_VERIFIED_DIRECT_BOUNDED",
        "v2_status": "VALIDATOR_PASS_BOUNDED",
        "reference_surface": ["validation/v2-backend-vector-datapath-family-results.json"],
    },
    {
        "id": "IcachePrefetchFamily",
        "source_scala": ["scala/src/main/scala/xiangshan/frontend/icache/ICacheMainPipe.scala", "scala/src/main/scala/xiangshan/frontend/icache/IPrefetch.scala", "scala/src/main/scala/xiangshan/frontend/icache/WayLookup.scala", "scala/src/main/scala/xiangshan/frontend/icache/InstrUncache.scala", "scala/src/main/scala/xiangshan/cache/mmu/L2TlbPrefetch.scala", "scala/src/main/scala/xiangshan/cache/mmu/L2TLBMissQueue.scala", "scala/src/main/scala/xiangshan/mem/prefetch/PrefetcherMonitor.scala"],
        "build_path": "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Frontend.Icache.Prefetch.Family-Hardware.py",
        "family_id": "core.frontend.icache.prefetch",
        "closure_root": "core.frontend.icache",
        "classification": "REWRITTEN",
        "disposition": "STRUCTURE_VERIFIED_DIRECT_BOUNDED",
        "v2_status": "VALIDATOR_PASS_BOUNDED",
        "reference_surface": ["validation/v2-frontend-icache-prefetch-family-results.json"],
    },
    {
        "id": "DifftestStateFamily",
        "source_scala": ["scala/src/main/scala/difftest/ArchEvent.scala", "scala/src/main/scala/difftest/CSRState.scala", "scala/src/main/scala/difftest/InstrCommit.scala", "scala/src/main/scala/difftest/TrapEvent.scala"],
        "build_path": "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Dependency.Difftest.StateFamily-Hardware.py",
        "family_id": "dependency.difftest.state",
        "closure_root": "dependency.difftest",
        "classification": "REWRITTEN",
        "disposition": "STRUCTURE_VERIFIED_DIRECT_BOUNDED",
        "v2_status": "VALIDATOR_PASS_BOUNDED",
        "reference_surface": ["validation/v2-difftest-state-family-results.json"],
        "covered_modules": ["DiffExtArchEvent", "DiffExtArchFpRenameTable", "DiffExtArchIntRenameTable", "DiffExtArchVecRenameTable", "DiffExtCSRState", "DiffExtCriticalErrorEvent", "DiffExtDebugMode", "DiffExtFpCSRState", "DiffExtHCSRState", "DiffExtInstrCommit", "DiffExtLrScEvent", "DiffExtMhpmeventOverflowEvent", "DiffExtNonRegInterruptPendingEvent", "DiffExtPhyFpRegState", "DiffExtPhyIntRegState", "DiffExtPhyVecRegState", "DiffExtSyncAIAEvent", "DiffExtSyncCustomMflushpwrEvent", "DiffExtTrapEvent", "DiffExtTriggerCSRState", "DiffExtVecCSRState"],
    },
]

data = json.loads(PATH.read_text(encoding="utf-8"))
ids = {entry["id"] for entry in data["entries"]}
for entry in NEW:
    if entry["id"] not in ids:
        data["entries"].append(entry)
data["entries_status_counts"] = {}
for entry in data["entries"]:
    status = entry.get("v2_status", entry.get("disposition", "UNKNOWN"))
    data["entries_status_counts"][status] = data["entries_status_counts"].get(status, 0) + 1
data["status"] = "IMPLEMENTATION_WAVES_VALIDATED_BOUNDED_HIERARCHY_WAVE1"
data["acceptance_eligible"] = False
PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
print("registered", [entry["id"] for entry in NEW if entry["id"] in ids or entry in data["entries"]])
